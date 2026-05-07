from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from tabox_config import load_config
from taSystemCmd import _run_cmd, _run_systemctl
from taWifi import WIFI_INTERFACE
from taLog import _self_update_print, _append_self_update_log

taServer_API_Version = "V 260502-1613"
# V 260502b    : action_cmd / action_value 直接從 payload 讀取，不再用 action_string | split。
# V 260502b    : server_request 改名為 CopyFiles。
# V 260502 SRQ : 增加 server_request.json 執行流程，支援 file_copy 覆蓋與 exec_comd 執行。
# V 260502     : heartbeat 只處理 server_request，移除其他舊 cmd 流程。

CONFIG = load_config()
TA_SERVER_CONFIG = CONFIG["ta_server"]
TA_SERVER_URL = TA_SERVER_CONFIG["base_url"].rstrip("/")
MAC_TOKEN = TA_SERVER_CONFIG["mac_token"]
REQUEST_TIMEOUT = int(TA_SERVER_CONFIG["requests_timeout_seconds"])


def _read_linux_mac_address(preferred_interface: str | None = None) -> str | None:
    sys_class_net = Path("/sys/class/net")
    if not sys_class_net.exists():
        return None

    interfaces: list[str] = []
    if preferred_interface:
        interfaces.append(preferred_interface)

    try:
        for nic in sorted(os.listdir(sys_class_net)):
            if nic == "lo" or nic in interfaces:
                continue
            interfaces.append(nic)
    except OSError:
        return None

    mac_pattern = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")
    for nic in interfaces:
        addr_file = sys_class_net / nic / "address"
        try:
            mac = addr_file.read_text(encoding="utf-8").strip().lower()
        except OSError:
            continue

        if mac_pattern.match(mac) and mac != "00:00:00:00:00:00":
            return mac

    return None


MAC_ADDRESS = str(TA_SERVER_CONFIG.get("mac_address") or "").strip() or _read_linux_mac_address(WIFI_INTERFACE)


def _normalize_unix_path(raw_path: str) -> str:
    return raw_path.replace("\\", "/").strip()


def _normalize_file_copy_items(raw_items: object) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []

    if isinstance(raw_items, list) and len(raw_items) == 2 and all(isinstance(x, str) for x in raw_items):
        src = raw_items[0].strip()
        dst = raw_items[1].strip()
        if src and dst:
            return [(src, dst)]

    if not isinstance(raw_items, list):
        return items

    for item in raw_items:
        if isinstance(item, list) and len(item) == 2:
            src = str(item[0]).strip()
            dst = str(item[1]).strip()
            if src and dst:
                items.append((src, dst))
        elif isinstance(item, dict):
            src = str(item.get("src", "")).strip()
            dst = str(item.get("des", item.get("dst", ""))).strip()
            if src and dst:
                items.append((src, dst))

    return items


def _extract_zip_to_target(zip_path: Path, target_dir: Path) -> int:
    target_dir.mkdir(parents=True, exist_ok=True)
    extracted_count = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
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


def _find_extracted_source_file(search_root: Path, src_name: str) -> Path | None:
    normalized_src = _normalize_unix_path(src_name)
    direct = (search_root / normalized_src).resolve()
    if direct.exists() and direct.is_file():
        return direct

    normalized_parts = tuple(part for part in Path(normalized_src).parts if part not in ("", "."))
    basename = Path(normalized_src).name
    matches: list[Path] = []

    for candidate in search_root.rglob("*"):
        if not candidate.is_file():
            continue
        if candidate.name != basename:
            continue

        relative_parts = candidate.relative_to(search_root).parts
        if normalized_parts and tuple(relative_parts[-len(normalized_parts):]) == normalized_parts:
            return candidate
        matches.append(candidate)

    return sorted(matches)[0] if matches else None


def _normalize_exec_commands(raw_exec: object) -> tuple[bool, list[str], str]:
    if isinstance(raw_exec, str):
        exec_list = [raw_exec.strip()] if raw_exec.strip() else []
        return True, exec_list, ""

    if isinstance(raw_exec, list):
        exec_list = [str(cmd).strip() for cmd in raw_exec if str(cmd).strip()]
        return True, exec_list, ""

    return False, [], "exec_comd must be a string or list"


def _resolve_named_exec_command(cmd_text: str) -> tuple[str, str]:
    normalized = cmd_text.strip()
    named_commands = {
        "Restart-taBOX-heartbeat": "deferred:restart-self",
    }
    resolved = named_commands.get(normalized, "")
    return normalized, resolved

#現在可以這樣寫 exec_comd
#只 copy 檔案, 沒有 command 執行
#  "exec_comd": []
#}只重啟 heartbeat，自動在 finalize 後退出
#  "exec_comd": [ "Restart-taBOX-heartbeat" ]
#直接使用原本 shell / systemctl 指令也可以
#  "exec_comd": [
#    "sudo systemctl stop openclaw-gateway-1.service",
#    "sudo systemctl restart openclaw-gateway-1.service"
#  ]



def _run_exec_command(cmd_text: str) -> tuple[bool, str]:
    _, named_target = _resolve_named_exec_command(cmd_text)
    actual_cmd = named_target or cmd_text.strip()

    if actual_cmd.startswith("deferred:"):
        return True, actual_cmd

    if actual_cmd.startswith("systemctl:"):
        parts = shlex.split(actual_cmd.split(":", 1)[1])
        code, out, err = _run_systemctl(parts, timeout=30)
        if code != 0:
            return False, err or out or str(code)
        return True, actual_cmd

    normalized_cmd = actual_cmd.strip()
    if normalized_cmd.startswith("sudo "):
        normalized_cmd = normalized_cmd[5:].strip()

    if normalized_cmd.startswith("systemctl "):
        parts = shlex.split(normalized_cmd)
        code, out, err = _run_systemctl(parts[1:], timeout=30)
    else:
        parts = shlex.split(actual_cmd)
        code, out, err = _run_cmd(parts, timeout=30)

    if code != 0:
        return False, err or out or str(code)
    return True, actual_cmd


def _run_deferred_exec_commands(deferred_exec_list: list[str]) -> None:
    for deferred_cmd in deferred_exec_list:
        if deferred_cmd == "deferred:restart-self":
            _self_update_print("deferred exec: restart tabox-heartbeat after finalize")
            raise SystemExit(0)


def _handle_copyfiles_request(action_value: str | None) -> tuple[bool, str, list[str]]:
    if not action_value:
        return False, "missing action_value for server request", []

    request_payload: object
    tmp_zip_path: Path | None = None
    extract_dir: Path | None = None
    raw_url = action_value.strip()
    deferred_exec_list: list[str] = []

    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        tmp_dir = Path("Temp")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_zip_path = tmp_dir / f"server_request_{ts}.zip"
        extract_dir = tmp_dir / f"server_request_{ts}_extracted"

        _self_update_print(f"server request download: {raw_url}")
        urllib.request.urlretrieve(raw_url, str(tmp_zip_path))                               # 下載檔案
        file_count = _extract_zip_to_target(tmp_zip_path, extract_dir)                       # 解壓縮檔案到 tmp_zip_path
        _self_update_print(f"server request extracted files={file_count} to {extract_dir}")  # 存到 log

        request_json_path = _find_extracted_source_file(extract_dir, "server_request.json")  # server 檔案的描述，server 提供給 mac 的
        if request_json_path is None:
            return False, "server_request.json not found in downloaded package", []

        request_payload = json.loads(request_json_path.read_text(encoding="utf-8"))

        if not isinstance(request_payload, dict):
            return False, "server request payload must be an object", []

        copy_items = _normalize_file_copy_items(request_payload.get("file_copy"))
        if not copy_items:
            return False, "server request missing valid file_copy entries", []

        copied_count = 0
        for src_raw, dst_raw in copy_items:
            src_path = _find_extracted_source_file(extract_dir, src_raw)
            dst_path = Path(_normalize_unix_path(dst_raw)).expanduser()

            if not dst_path.is_absolute():
                dst_path = (Path.cwd() / dst_path).resolve()

            if src_path is None:
                return False, f"copy source missing in extracted package: {src_raw}", []

            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
            copied_count += 1
            _self_update_print(f"server request copy: {src_path} -> {dst_path}")

        exec_ok, exec_list, exec_error = _normalize_exec_commands(request_payload.get("exec_comd", []))
        if not exec_ok:
            return False, exec_error, []

        exec_count = 0
        for cmd_text in exec_list:
            run_ok, run_result = _run_exec_command(cmd_text)
            if not run_ok:
                return False, f"exec failed ({cmd_text}): {run_result}", deferred_exec_list

            if run_result.startswith("deferred:"):
                deferred_exec_list.append(run_result)
                _self_update_print(f"server request defer exec: {cmd_text}")
                continue

            exec_count += 1
            _self_update_print(f"server request exec ok: {cmd_text}")

        return True, f"server request done (copied={copied_count}, exec={exec_count}, deferred={len(deferred_exec_list)})", deferred_exec_list
    except json.JSONDecodeError as exc:
        return False, f"server request json decode error: {exc}", deferred_exec_list
    except zipfile.BadZipFile as exc:
        return False, f"server request zip error: {exc}", deferred_exec_list
    except Exception as exc:  # pylint: disable=broad-except
        return False, f"server request exception: {exc}", deferred_exec_list
    finally:
        try:
            if extract_dir and extract_dir.exists():
                shutil.rmtree(extract_dir)
        except Exception:  # pylint: disable=broad-except
            pass
        try:
            if tmp_zip_path and tmp_zip_path.exists():
                tmp_zip_path.unlink()
        except Exception:  # pylint: disable=broad-except
            pass


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


def taServer_API_mac_login(typestr: str) -> tuple[bool, str]:
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
    req = urllib.request.Request(api_url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            status_code = resp.getcode()
            body = resp.read().decode("utf-8", errors="replace")
            mac_id = None
            heartbeat_count = None
            heartbeat_sec = None
            action_cmd = None
            action_value = None

            try:
                payload = json.loads(body)
                #Server payload 預期格式：
                #{
                #"mac_id": "...",
                #"heartbeat_count": 1,
                #"heartbeat_sec": 30,
                #"action_cmd": "CopyFiles",
                #"action_value": "https://your-server.com/path/to/package.zip"
                #}
                if isinstance(payload, dict):
                    mac_id = payload.get("mac_id")
                    heartbeat_count = payload.get("heartbeat_count")
                    heartbeat_sec = payload.get("heartbeat_sec")
                    action_cmd = payload.get("action_cmd")
                    action_value = payload.get("action_value")

                if action_cmd == "CopyFiles":
                    ok, server_request_msg, deferred_exec_list = _handle_copyfiles_request(action_value)
                    _finalize_action(action_cmd, ok, server_request_msg)
                    if ok:
                        _run_deferred_exec_commands(deferred_exec_list)
                        
            except json.JSONDecodeError:
                mac_id = None

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
