from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from tabox_config import load_config, resolve_project_path

taServer_API_Version = "V 260420 2222"

CONFIG = load_config()
WIFI_INTERFACE = CONFIG["wifi"]["interface"]
TA_SERVER_CONFIG = CONFIG["ta_server"]
TA_SERVER_URL = TA_SERVER_CONFIG["base_url"].rstrip("/")
MAC_TOKEN = TA_SERVER_CONFIG["mac_token"]
REQUEST_TIMEOUT = int(TA_SERVER_CONFIG["requests_timeout_seconds"])
MAC_ADDRESS = TA_SERVER_CONFIG.get("mac_address")
SELF_UPDATE_LOG_FILE = resolve_project_path(TA_SERVER_CONFIG.get("self_update_log_file", "Temp/self_update.log"))


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
