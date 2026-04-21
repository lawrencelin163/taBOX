from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from tabox_config import load_config, resolve_project_path

taServer_API_Version = "V 260421 1635" 
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
WIFI_INTERFACE = WIFI_CONFIG["interface"]
WIFI_SHORT_TIMEOUT = int(WIFI_CONFIG.get("short_timeout_seconds", 8))
WIFI_CONNECT_TIMEOUT = int(WIFI_CONFIG.get("connect_timeout_seconds", 20))
WIFI_NMCLI_WAIT = int(WIFI_CONFIG.get("nmcli_wait_seconds", 15))
WIFI_RETRY_ROUND_DELAY_SECONDS = 10


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


def _run_cmd(command: list[str], timeout: int) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env)
        return completed.returncode, completed.stdout.strip(), completed.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "command timeout"


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
        return True, "connected"
    return False, f"verify-failed: {state_detail}"


def _WiFi_Check() -> None:
    connected, detail = _wifi_is_connected(WIFI_INTERFACE)
    if connected:
        return

    print(f"[WiFiCheck] WiFi disconnected on {WIFI_INTERFACE}: {detail}")

    round_count = 0
    while True:
        saved_networks = _normalize_saved_networks(CONFIG.get("saved_networks", []))
        if not saved_networks:
            print("[WiFiCheck] saved_networks is empty, retry after 10 seconds")
            time.sleep(10)
            continue

        round_count += 1
        print(f"[WiFiCheck] reconnect round {round_count} start, candidates={len(saved_networks)}")
        for idx, network in enumerate(saved_networks, start=1):
            ssid = network["ssid_id"]
            password = network["password"]
            print(f"[WiFiCheck] round={round_count} try={idx}/{len(saved_networks)} ssid={ssid}")
            ok, msg = _wifi_connect(ssid, password)
            if ok:
                print(f"[WiFiCheck] connected round={round_count} try={idx} ssid={ssid}")
                return
            print(f"[WiFiCheck] failed round={round_count} try={idx} ssid={ssid} reason={msg}")

        print(f"[WiFiCheck] all saved SSIDs failed, sleep {WIFI_RETRY_ROUND_DELAY_SECONDS}s then retry")
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
    # login or heartbeat 
    _WiFi_Check()

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
                        fname = target_fname # "taServer_API_test.py"
                        print(f"Download....{fname}_tmp from [taServer file exchange center].\n{action_value}")
                        urllib.request.urlretrieve(action_value, f"{fname}_tmp")
                        print("Download complete : ", f"{fname}_tmp")
                        if os.path.exists(fname):
                            os.remove(fname)
                            #print("Old file removed:", fname)
                        os.rename(f"{fname}_tmp", fname)
                        print("Updated file finished: ", fname)

                        utc_time = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")
                        replystr = f"{utc_time}"
                        api_url = f"{TA_SERVER_URL}/heartbeat/{MAC_TOKEN}:{MAC_ADDRESS}:{replystr}"
                        url_info = f'reply to server: "{api_url}"'
                        req = urllib.request.Request(api_url, method="GET")

                        print(url_info)
                        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                            status_code = resp.getcode()
                            body = resp.read().decode("utf-8", errors="replace")
                            print(f"Reply to server: HTTP {status_code} body={body[:180]}")

                        if os_exec_str == 'SELF':
                            # Keep full payload in log before replacing current process.
                            _append_self_update_log(payload, url_info)

                            print("[SELF-UPDATE] restarting current process...")
                            os.execv(sys.executable, [sys.executable] + sys.argv)

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
