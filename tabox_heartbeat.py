from __future__ import annotations

import time

from tabox_config import load_config
from taServer_API import taServer_API_mac_heartbeat
from taWifi import _WiFi_Check, _wifi_is_connected, WIFI_INTERFACE
from taLog import log_heartbeat_line, log_bootstrap_start_once

CONFIG = load_config()
HEARTBEAT_CONFIG = CONFIG["heartbeat"]
TA_SERVER_CONFIG = CONFIG["ta_server"]

HEARTBEAT_INTERVAL_SEC = int(HEARTBEAT_CONFIG["interval_seconds"])
HEARTBEAT_REPLY_DEFAULT = TA_SERVER_CONFIG["heartbeat_reply"]
WIFI_POLL_SEC = 10  # check WiFi this often (seconds) during heartbeat sleep


def _interruptible_sleep(seconds: float) -> bool:
    """Sleep for `seconds`, waking every WIFI_POLL_SEC to check WiFi.

    Returns True if WiFi was lost and reconnected (caller should send
    heartbeat immediately instead of waiting out the remaining sleep).
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        chunk = min(WIFI_POLL_SEC, max(1.0, deadline - time.monotonic()))
        time.sleep(chunk)
        connected, _ = _wifi_is_connected(WIFI_INTERFACE)
        if not connected:
            log_heartbeat_line("[WiFiCheck] WiFi lost during sleep, reconnecting now...")
            _WiFi_Check()
            log_heartbeat_line("[WiFiCheck] WiFi restored, sending heartbeat immediately")
            return True
    return False


def run_heartbeat_forever() -> None:
    startup_msg = f"taBOX heartbeat started (interval={HEARTBEAT_INTERVAL_SEC}s)"
    log_heartbeat_line(startup_msg)
    log_bootstrap_start_once(startup_msg)
    while True:
        heartbeat_sec, message = taServer_API_mac_heartbeat(HEARTBEAT_REPLY_DEFAULT)
        log_heartbeat_line(f"{message}")
        if heartbeat_sec is not None and heartbeat_sec > 10:
            _interruptible_sleep(heartbeat_sec)
        else:
            _interruptible_sleep(HEARTBEAT_INTERVAL_SEC)


if __name__ == "__main__":
    run_heartbeat_forever()
