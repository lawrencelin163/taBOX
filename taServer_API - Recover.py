from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

# taServer base URL and fixed mac token for registration/login.
taServer_URL = "https://tabox.onrender.com/api/mac"
mac_token = "aa04-eaaf-d961-4f40" # yf 的 token
mac_token = "o3h3-4l81-i9i9-1r0z" # kl 的 token
kl_url= "https://tabox.onrender.com/api/mac/heartbeat/o3h3-4l81-i9i9-1r0z:88a29e867036:none"

def _read_mac_address(interface: str) -> str:
    return '88a29e867036'
    addr_path = f"/sys/class/net/{interface}/address"
    try:
        with open(addr_path, "r", encoding="utf-8") as f:
            mac_raw = f.read().strip().lower()
    except OSError as exc:
        raise RuntimeError(f"無法讀取 {interface} MAC 位址: {exc}") from exc

    mac_clean = mac_raw.replace(":", "")
    if len(mac_clean) != 12 or any(ch not in "0123456789abcdef" for ch in mac_clean):
        raise RuntimeError(f"MAC 位址格式異常: {mac_raw}")
    return mac_clean

def taServer_API_mac_login(typestr: str) -> tuple[bool, str]:
    # login or heartbeat 
    interface = os.getenv("WIFI_INTERFACE", "wlan0")
    mac_address = _read_mac_address(interface)
    api_url = f"{taServer_URL}/{typestr}/{mac_token}:{mac_address}"
    url_info = f"taServer API URL: {api_url}"

    req = urllib.request.Request(api_url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
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
                    return True, f"{url_info} | taServer mac login 成功, {status_code} mac_id={mac_id}"
                return True, f"{url_info} | taServer mac login 成功: {status_code}"
            return False, f"{url_info} | taServer mac login 失敗: HTTP {status_code} body={body[:180]}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return False, f"{url_info} | taServer mac login HTTPError: {exc.code} body={body[:180]}"
    except urllib.error.URLError as exc:
        return False, f"{url_info} | taServer mac login URLError: {exc.reason}"
    except Exception as exc:  # pylint: disable=broad-except
        return False, f"{url_info} | taServer mac login 例外: {exc}"

def taServer_API_mac_heartbeat(replystr: str) -> tuple[bool, str]:
    # login or heartbeat 
    interface = os.getenv("WIFI_INTERFACE", "wlan0")
    mac_address = _read_mac_address(interface)
    api_url = f"{taServer_URL}/heartbeat/{mac_token}:{mac_address}:{replystr}"
    url_info = f"taServer API URL: {api_url}"
    #print(f"[debug] {url_info}")

    req = urllib.request.Request(api_url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            status_code = resp.getcode()
            body = resp.read().decode("utf-8", errors="replace")
            mac_id = None
            action_type = None
            action_cmd = None
            action_value = None

            try:
                payload = json.loads(body)

                if isinstance(payload, dict):
                    mac_id = payload.get("mac_id")
                    heartbeat_count = payload.get("heartbeat_count")
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
                        api_url = f"{taServer_URL}/heartbeat/{mac_token}:{mac_address}:{replystr}"
                        url_info = f'reply to server: "{api_url}"'
                        req = urllib.request.Request(api_url, method="GET")
                        if os_exec_str == 'SELF':
                            print("Execute command: ", f"python3 {fname}")
                        else:                           
                            print("Execute command: ", os_exec_str)
                            
                        print(url_info)
                        with urllib.request.urlopen(req, timeout=8) as resp:
                            status_code = resp.getcode()
                            body = resp.read().decode("utf-8", errors="replace")
                            print(f"Reply to server: HTTP {status_code} body={body[:180]}")

            except json.JSONDecodeError:
                mac_id = None

            #if mac_id:
            #    print(f'taServer: "{mac_id}", "{action_type}", "{action_cmd}", "{action_value}"')

            if 200 <= status_code < 300:
                if mac_id:
                    return True, f"[{mac_id}] heartbeat 成功 ({heartbeat_count})"
                return True, f"{url_info} | http 成功: {status_code} | 沒有 mac_id 資訊 ???"
            return False, f"{url_info} | heartbeat 失敗: HTTP {status_code} body={body[:180]}"
        
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return False, f"{url_info} | heartbeat 失敗, HTTPError: {exc.code} body={body[:180]}"
    except urllib.error.URLError as exc:
        return False, f"{url_info} | heartbeat 失敗, URLError: {exc.reason}"
    except Exception as exc:  # pylint: disable=broad-except
        return False, f"{url_info} | heartbeat 失敗, 例外: {exc}"
