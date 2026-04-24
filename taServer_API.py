from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from tabox_config import load_config, resolve_project_path

taServer_API_Version = "V 260424 1138"  
# V 260424 1138 : 建立 Active Bot / Zip 檔案保留.。
# V 260423 1420 : 把 _WiFi_Check()，改成在 tabox-heartbeat.py 的 裏面做.
# V 260423 1330 : _WiFi_Check() 裏的 _wifi_connect() ，在連上后，重建 profile，并且設定 autoconnect
# V 260421 1713 : 改成 download 完成后，SystemExit(0), 由 systemd 來負責重啟服務，這樣可以確保在更新檔案後，新的程式碼能夠被載入並執行，而不需要依賴目前的程式碼來進行重啟，增加了更新的可靠性和成功率。
# V 260421 1635 : 多了 WiFi_Check 這個 副程式，會在每次 heartbeat 前檢查 WiFi 連線狀態，如果沒有連線就嘗試重新連線，直到成功為止。這樣可以確保在 WiFi 不穩定的環境下，taBOX 仍然能夠保持與 taServer 的連線，並且繼續正常運作。
# V 260420 2222 : 可以從 server 端收到 action_string 指令，並且下載更新檔案，替換目前的檔案，最後回報更新完成的時間戳記給 server 端。 action_string 格式為 "type|cmd|value"，例如 "File update|File update|https://example.com/taServer_API_test.py" 表示要下載 https://example.com/taServer_API_test.py 這個檔案，然後替換目前的 taServer_API_test.py。

CONFIG = load_config()
TA_SERVER_CONFIG = CONFIG["ta_server"]
TA_SERVER_URL = TA_SERVER_CONFIG["base_url"].rstrip("/")
MAC_TOKEN = TA_SERVER_CONFIG["mac_token"]
REQUEST_TIMEOUT = int(TA_SERVER_CONFIG["requests_timeout_seconds"])
MAC_ADDRESS = TA_SERVER_CONFIG.get("mac_address")
SELF_UPDATE_LOG_FILE = resolve_project_path(TA_SERVER_CONFIG.get("self_update_log_file", "Temp/self_update.log"))
WIFI_CONFIG = CONFIG["wifi"]
WIFI_CHECK_LOG_FILE = resolve_project_path(WIFI_CONFIG.get("wifi_check_log_file", "Temp/wifi_check.log"))
WIFI_INTERFACE = WIFI_CONFIG["interface"]
WIFI_SHORT_TIMEOUT = int(WIFI_CONFIG.get("short_timeout_seconds", 8))
WIFI_CONNECT_TIMEOUT = int(WIFI_CONFIG.get("connect_timeout_seconds", 20))
WIFI_NMCLI_WAIT = int(WIFI_CONFIG.get("nmcli_wait_seconds", 15))
WIFI_RETRY_ROUND_DELAY_SECONDS = 10


def _normalize_unix_path(raw_path: str) -> str:
    return raw_path.replace("\\", "/").strip()


def _extract_zip_to_target(zip_path: Path, target_dir: Path) -> int:
    target_dir.mkdir(parents=True, exist_ok=True)
    extracted_count = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            # Prevent zip-slip and ignore directory entries.
            normalized = Path(member.filename)
            if member.is_dir():
                continue

            safe_parts = [part for part in normalized.parts if part not in ("", ".")]
            if not safe_parts or any(part == ".." for part in safe_parts):
                continue

            dest_path = target_dir.joinpath(*safe_parts)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as src, dest_path.open("wb") as dst:
                dst.write(src.read())
            extracted_count += 1

    return extracted_count


def _service_suffix_from_target(target_path: str) -> str | None:
    normalized = _normalize_unix_path(target_path)
    match = re.search(r"(\d+)\s*$", normalized)
    return match.group(1) if match else None


def _activate_gateway_service_by_target(target_path: str) -> tuple[bool, str]:
    suffix = _service_suffix_from_target(target_path)
    if not suffix:
        return False, f"unable to parse service suffix from target_fname={target_path}"

    service_name = f"openclaw-gateway-{suffix}.service"

    reload_code, reload_out, reload_err = _run_systemctl(["daemon-reload"], timeout=20)
    if reload_code != 0:
        _self_update_print(f"daemon-reload warning: {reload_err or reload_out}")

    code, _, _ = _run_systemctl(["is-active", service_name], timeout=10)
    active = code == 0

    enable_code, enable_out, enable_err = _run_systemctl(["enable", service_name], timeout=20)
    if enable_code != 0:
        return False, f"enable failed: {enable_err or enable_out or service_name}"

    if active:
        action_cmd = ["systemctl", "restart", service_name]
        action_desc = "restart"
    else:
        action_cmd = ["systemctl", "start", service_name]
        action_desc = "start"

    run_code, run_out, run_err = _run_systemctl(action_cmd, timeout=20)
    if run_code != 0:
        return False, f"{action_desc} failed: {run_err or run_out or service_name}"

    return True, f"service {service_name} enabled and {action_desc}ed"


def _handle_bot_build(action_value: str | None, target_fname: str | None) -> tuple[bool, str]:
    if not action_value:
        return False, "missing action_value for bot build"
    if not target_fname:
        return False, "missing target_fname for bot build"

    normalized_target = _normalize_unix_path(target_fname)
    target_dir = Path(normalized_target)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_tmp = target_dir.parent / f"{target_dir.name}_bot_build_{ts}.zip"

    try:
        _self_update_print(f"bot build download: {action_value}")
        urllib.request.urlretrieve(action_value, str(zip_tmp))
        _self_update_print(f"bot build zip downloaded: {zip_tmp}")

        file_count = _extract_zip_to_target(zip_tmp, target_dir)
        _self_update_print(f"bot build extracted files={file_count} target={target_dir}")

        ok, service_msg = _activate_gateway_service_by_target(normalized_target)
        if not ok:
            return False, service_msg

        return True, f"bot build success ({file_count} files), {service_msg}"
    except Exception as exc:  # pylint: disable=broad-except
        return False, f"bot build exception: {exc}"


def _reply_action_timestamp(action_cmd: str) -> tuple[bool, str, str]:
    utc_time = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")
    replystr = f"{utc_time}"
    api_url = f"{TA_SERVER_URL}/heartbeat/{MAC_TOKEN}:{MAC_ADDRESS}:{replystr}"
    req = urllib.request.Request(api_url, method="GET")

    try:
        _self_update_print(f'reply to server ({action_cmd}): "{api_url}"')
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            status_code = resp.getcode()
            body = resp.read().decode("utf-8", errors="replace")
            return True, f"Reply to server ({action_cmd}): HTTP {status_code} body={body[:180]}", api_url
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return False, f"Reply HTTPError ({action_cmd}): {exc.code} body={body[:180]}", api_url
    except urllib.error.URLError as exc:
        return False, f"Reply URLError ({action_cmd}): {exc.reason}", api_url
    except Exception as exc:  # pylint: disable=broad-except
        return False, f"Reply exception ({action_cmd}): {exc}", api_url


def _finalize_action(action_cmd: str, ok: bool, detail: str) -> str:
    status_text = "success" if ok else "failed"
    _self_update_print(f"[{action_cmd}] {status_text}: {detail}")

    reply_ok, reply_msg, reply_api_url = _reply_action_timestamp(action_cmd)
    if reply_ok:
        _self_update_print(reply_msg)
    else:
        _self_update_print(f"[{action_cmd}] reply failed: {reply_msg}")
    return reply_api_url


def _append_self_update_log(payload: object, api_url: str) -> None:
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        line = f"[{timestamp}] api={api_url} payload={payload_text}"

        log_file = Path(SELF_UPDATE_LOG_FILE)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(line)
            f.write("\n")
        print(f"[SELF-UPDATE] payload logged to {SELF_UPDATE_LOG_FILE}")
    except Exception as payload_exc:  # pylint: disable=broad-except
        print(f"[SELF-UPDATE] payload logging failed: {payload_exc}")


def _self_update_print(message: str) -> None:
    line = f"[SELF-UPDATE] {message}"
    print(line)
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = Path(SELF_UPDATE_LOG_FILE)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {line}\n")
    except Exception as log_exc:  # pylint: disable=broad-except
        print(f"[SELF-UPDATE] plain logging failed: {log_exc}")


def _wifi_check_log(message: str) -> None:
    line = f"[WiFiCheck] {message}"
    print(line, flush=True)
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = Path(WIFI_CHECK_LOG_FILE)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {line}\n")
    except Exception as log_exc:  # pylint: disable=broad-except
        print(f"[WiFiCheck] logging failed: {log_exc}")


def _run_cmd(command: list[str], timeout: int) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env)
        return completed.returncode, completed.stdout.strip(), completed.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "command timeout"


def _run_systemctl(args: list[str], timeout: int) -> tuple[int, str, str]:
    code, out, err = _run_cmd(["systemctl", *args], timeout=timeout)
    if code == 0:
        return code, out, err

    details = f"{err} {out}".lower()
    need_auth = "interactive authentication required" in details or "authentication is required" in details
    if not need_auth:
        return code, out, err

    sudo_code, sudo_out, sudo_err = _run_cmd(["sudo", "-n", "systemctl", *args], timeout=timeout)
    if sudo_code == 0:
        return sudo_code, sudo_out, sudo_err

    merged_err = sudo_err or err or out
    return sudo_code, sudo_out, merged_err


def _wifi_ipv4(interface: str) -> str | None:
    code, out, _ = _run_cmd(["nmcli", "-g", "IP4.ADDRESS", "device", "show", interface], timeout=WIFI_SHORT_TIMEOUT)
    if code != 0 or not out:
        return None
    first = out.splitlines()[0].strip()
    if not first:
        return None
    return first.split("/", 1)[0]


def _wifi_is_connected(interface: str) -> tuple[bool, str]:
    code, out, err = _run_cmd(["nmcli", "-g", "GENERAL.STATE", "device", "show", interface], timeout=WIFI_SHORT_TIMEOUT)
    if code != 0:
        return False, f"state-check-failed: {err or out or 'nmcli error'}"

    state = out.splitlines()[0].strip() if out else "unknown"
    ip = _wifi_ipv4(interface)
    if "100 (connected)" in state and ip:
        return True, f"connected, ip={ip}"
    return False, f"state={state}, ip={ip or 'none'}"


def _normalize_saved_networks(raw_networks: object) -> list[dict[str, str]]:
    if not isinstance(raw_networks, list):
        return []

    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_networks:
        if not isinstance(item, dict):
            continue
        ssid = str(item.get("ssid_id", "")).strip()
        password = str(item.get("password", "")).strip()
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        result.append({"ssid_id": ssid, "password": password})
    return result


def _wifi_connect(ssid: str, password: str) -> tuple[bool, str]:
    _run_cmd(["nmcli", "device", "disconnect", WIFI_INTERFACE], timeout=WIFI_SHORT_TIMEOUT)
    _run_cmd(["nmcli", "connection", "delete", ssid], timeout=WIFI_SHORT_TIMEOUT)

    connect_cmd = ["nmcli", "--wait", str(WIFI_NMCLI_WAIT), "device", "wifi", "connect", ssid, "ifname", WIFI_INTERFACE]
    if password:
        connect_cmd.extend(["password", password])

    code, out, err = _run_cmd(connect_cmd, timeout=WIFI_CONNECT_TIMEOUT)
    if code != 0:
        details = (err or out or "nmcli connect failed").strip()
        lower = details.lower()
        if code == 124 or "timeout" in lower:
            return False, f"TIMEOUT: {details}"
        if "wrong password" in lower or "secrets were required" in lower or "802-11-wireless-security" in lower:
            return False, f"PASSWORD: {details}"
        if "no network with ssid" in lower or "ssid not found" in lower or "not found" in lower:
            return False, f"NO_AP: {details}"
        return False, f"OTHER: {details}"

    connected, state_detail = _wifi_is_connected(WIFI_INTERFACE)
    if connected:
        _run_cmd(["nmcli", "connection", "modify", ssid, "connection.autoconnect", "yes"], timeout=WIFI_SHORT_TIMEOUT)
        return True, "connected"
    return False, f"verify-failed: {state_detail}"


def _WiFi_Check() -> None:
    connected, detail = _wifi_is_connected(WIFI_INTERFACE)
    if connected:
        return

    _wifi_check_log(f"WiFi disconnected on {WIFI_INTERFACE}: {detail}")

    round_count = 0
    while True:
        saved_networks = _normalize_saved_networks(CONFIG.get("saved_networks", []))
        if not saved_networks:
            _wifi_check_log("saved_networks is empty, retry after 10 seconds")
            time.sleep(10)
            continue

        round_count += 1
        _wifi_check_log(f"reconnect round {round_count} start, candidates={len(saved_networks)}")
        for idx, network in enumerate(saved_networks, start=1):
            ssid = network["ssid_id"]
            password = network["password"]
            _wifi_check_log(f"round={round_count} try={idx}/{len(saved_networks)} ssid={ssid}")
            ok, msg = _wifi_connect(ssid, password)
            if ok:
                _wifi_check_log(f"connected round={round_count} try={idx} ssid={ssid}")
                return
            _wifi_check_log(f"failed round={round_count} try={idx} ssid={ssid} reason={msg}")

        _wifi_check_log(f"all saved SSIDs failed, sleep {WIFI_RETRY_ROUND_DELAY_SECONDS}s then retry")
        time.sleep(WIFI_RETRY_ROUND_DELAY_SECONDS)

def taServer_API_mac_login(typestr: str) -> tuple[bool, str]:
    # login or heartbeat 
    if not MAC_TOKEN:
        return False, "taServer mac login 失敗: 缺少 mac_token 設定"
    if not MAC_ADDRESS:
        return False, "taServer mac login 失敗: 缺少 mac_address 設定"

    api_url = f"{TA_SERVER_URL}/{typestr}/{MAC_TOKEN}:{MAC_ADDRESS}"
    url_info = f"taServer API URL: {api_url}"

    req = urllib.request.Request(api_url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            status_code = resp.getcode()
            body = resp.read().decode("utf-8", errors="replace")
            mac_id = None
            try:
                payload = json.loads(body)
                if isinstance(payload, dict):
                    mac_id = payload.get("mac_id")
            except json.JSONDecodeError:
                mac_id = None

            if mac_id:
                print(f"taServer mac_id: {mac_id}")

            if 200 <= status_code < 300:
                if mac_id:
                    return True, f"({taServer_API_Version}) {url_info} | Login 成功, {status_code} mac_id={mac_id}"
                return True, f"({taServer_API_Version}) {url_info} | Login 成功: {status_code}"
            return False, f"({taServer_API_Version}) {url_info} | Login 失敗: HTTP {status_code} body={body[:180]}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return False, f"({taServer_API_Version}) {url_info} | Login HTTPError: {exc.code} body={body[:180]}"
    except urllib.error.URLError as exc:
        return False, f"({taServer_API_Version}) {url_info} | Login URLError: {exc.reason}"
    except Exception as exc:  # pylint: disable=broad-except
        return False, f"({taServer_API_Version}) {url_info} | Login 例外: {exc}"

def taServer_API_mac_heartbeat(replystr: str) -> tuple[bool, str]:
    api_url = f"{TA_SERVER_URL}/heartbeat/{MAC_TOKEN}:{MAC_ADDRESS}:{replystr}"
    url_info = f"taServer API URL: {api_url}"
    #print(f"[debug] {url_info}")

    req = urllib.request.Request(api_url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            status_code = resp.getcode()
            body = resp.read().decode("utf-8", errors="replace")
            mac_id = None
            heartbeat_sec = None
            action_type = None
            action_cmd = None
            action_value = None

            try:
                payload = json.loads(body)

                if isinstance(payload, dict):
                    print
                    mac_id = payload.get("mac_id")
                    heartbeat_count = payload.get("heartbeat_count")
                    heartbeat_sec = payload.get("heartbeat_sec")
                    action_string = payload.get("action_string")
                    target_fname = payload.get("target_fname")
                    os_exec_str  = payload.get("os_exec_str")
                    if action_string:
                        parts = action_string.split("|", 2)  # limit to 3 parts
                        if len(parts) == 3:
                            action_type, action_cmd, action_value = parts
                        else:
                            # fallback handling if format is broken
                            action_type = action_string

                if action_type :
                    if action_cmd=='File update':
                        file_update_ok = False
                        file_update_msg = ""
                        fname = target_fname # "taServer_API_test.py"
                        try:
                            _self_update_print(f"Download....{fname}_tmp from [taServer file exchange center].\\n{action_value}")
                            urllib.request.urlretrieve(action_value, f"{fname}_tmp")
                            _self_update_print(f"Download complete : {fname}_tmp")
                            if os.path.exists(fname):
                                os.remove(fname)
                                #print("Old file removed:", fname)
                            os.rename(f"{fname}_tmp", fname)
                            file_update_ok = True
                            file_update_msg = f"updated file finished: {fname}"
                        except Exception as exc:  # pylint: disable=broad-except
                            file_update_msg = f"file update exception: {exc}"

                        reply_api_url = _finalize_action(action_cmd, file_update_ok, file_update_msg)

                        if file_update_ok and os_exec_str == 'SELF':
                            # Keep full payload in log before replacing current process.
                            _append_self_update_log(payload, reply_api_url)

                            _self_update_print("restart requested, exit now and let systemd restart service...")
                            raise SystemExit(0)

                    if action_cmd=='bot build':
                        ok, bot_build_msg = _handle_bot_build(action_value, target_fname)
                        _finalize_action(action_cmd, ok, bot_build_msg)
                        
            except json.JSONDecodeError:
                mac_id = None

            #if mac_id:
            #    print(f'taServer: "{mac_id}", "{action_type}", "{action_cmd}", "{action_value}"')

            if 200 <= status_code < 300:
                if mac_id:
                    return heartbeat_sec, f"({taServer_API_Version}) [{mac_id}] heartbeat 成功 (next interval={heartbeat_sec}secs, count={heartbeat_count})"
                return heartbeat_sec, f"({taServer_API_Version}) {url_info} | http 成功: {status_code} | 沒有 mac_id 資訊 ???"
            return False, f"({taServer_API_Version}) {url_info} | heartbeat 失敗: HTTP {status_code} body={body[:180]}"
        
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return False, f"({taServer_API_Version}) {url_info} | heartbeat 失敗, HTTPError: {exc.code} body={body[:180]}"
    except urllib.error.URLError as exc:
        return False, f"({taServer_API_Version}) {url_info} | heartbeat 失敗, URLError: {exc.reason}"
    except Exception as exc:  # pylint: disable=broad-except
        return False, f"({taServer_API_Version}) {url_info} | heartbeat 失敗, 例外: {exc}"
