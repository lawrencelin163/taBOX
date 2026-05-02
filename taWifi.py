from __future__ import annotations

import time

from tabox_config import load_config, resolve_project_path
from taSystemCmd import _run_cmd
from taLog import _wifi_check_log

CONFIG = load_config()
WIFI_CONFIG = CONFIG["wifi"]
WIFI_INTERFACE = WIFI_CONFIG["interface"]
WIFI_SHORT_TIMEOUT = int(WIFI_CONFIG.get("short_timeout_seconds", 8))
WIFI_CONNECT_TIMEOUT = int(WIFI_CONFIG.get("connect_timeout_seconds", 20))
WIFI_NMCLI_WAIT = int(WIFI_CONFIG.get("nmcli_wait_seconds", 15))
WIFI_RETRY_ROUND_DELAY_SECONDS = 10


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
