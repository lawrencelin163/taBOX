from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from taServer_API import _read_linux_mac_address
from taWifi import WIFI_INTERFACE


TA_AUTH_API = "http://192.168.0.101:5001"
REQUEST_TIMEOUT = 12

def _get_device_mac() -> str | None:
    mac = _read_linux_mac_address(WIFI_INTERFACE)
    if not mac:
        return None
    return mac.replace(":", "")


def init_mac(mac_id_prefix: str, sd_size: str) -> Path:
    mac_address = _get_device_mac()

    api_url = f"{TA_AUTH_API}/lawrence/Create_taBOX_json/{mac_address}/{mac_id_prefix}/{sd_size}"
    print(f"taAuth API URL: {api_url}")

    req = urllib.request.Request(api_url, method="GET")
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            status_code = resp.getcode()
            body = resp.read().decode("utf-8", errors="replace")
            #print(f"HTTP {status_code} \n body: {body}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        print(f"HTTP {exc.code} error body: {detail[:300]}")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"URL error: {exc.reason}") from exc

    if not body.strip():
        raise RuntimeError("taAuth response is empty")

    config_data = json.loads(body)
    if not isinstance(config_data, dict):
        raise RuntimeError("taAuth response is not a JSON object")

    ta_server = config_data.get("ta_server")
    if not isinstance(ta_server, dict):
        raise RuntimeError("taAuth response missing ta_server")

    mac_id = str(ta_server.get("mac_id", "")).strip()
    if not mac_id:
        raise RuntimeError("taAuth response missing ta_server.mac_id")

    output_path = Path(f"taBOX_{mac_id}.json")
    output_path.write_text(json.dumps(config_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"MAC address : {mac_address}")
    print(f"mac_id      : {mac_id}")
    print(f"Saved       : {output_path}")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python Init_Mac.py <mac_id_prefix>  (e.g. MR408)")
        raise SystemExit(1)
    if len(sys.argv) < 3:
        print("Usage: python Init_Mac.py <mac_id_prefix> <sd_size>  (e.g. MR408 32G)")
        raise SystemExit(1)
    try:
        init_mac(sys.argv[1])
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Init_Mac failed: {exc}")
        raise SystemExit(1)