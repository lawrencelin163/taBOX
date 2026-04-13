from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# taServer base URL and fixed mac token for registration/login.
taServer_URL = "https://tabox.onrender.com"
mac_token = "aa04-eaaf-d961-4f40"


def _read_mac_address(interface: str) -> str:
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


def taServer_API_mac_login() -> tuple[bool, str]:
    interface = os.getenv("WIFI_INTERFACE", "wlan0")
    mac_address = _read_mac_address(interface)
    api_url = f"{taServer_URL}/api/mac/{mac_token}:{mac_address}"
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
                    return True, f"{url_info} | taServer mac login 成功: {status_code} mac_id={mac_id}"
                return True, f"{url_info} | taServer mac login 成功: {status_code}"
            return False, f"{url_info} | taServer mac login 失敗: HTTP {status_code} body={body[:180]}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return False, f"{url_info} | taServer mac login HTTPError: {exc.code} body={body[:180]}"
    except urllib.error.URLError as exc:
        return False, f"{url_info} | taServer mac login URLError: {exc.reason}"
    except Exception as exc:  # pylint: disable=broad-except
        return False, f"{url_info} | taServer mac login 例外: {exc}"
