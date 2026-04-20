from __future__ import annotations

import time
from datetime import datetime

from tabox_config import load_config, resolve_project_path
from taServer_API import taServer_API_mac_heartbeat

CONFIG = load_config()
BOOTSTRAP_CONFIG = CONFIG["bootstrap"]
HEARTBEAT_CONFIG = CONFIG["heartbeat"]
TA_SERVER_CONFIG = CONFIG["ta_server"]

BOOTSTRAP_LOG_FILE = resolve_project_path(BOOTSTRAP_CONFIG["log_file"])
BOOTSTRAP_LOG_KEEP_LINES = int(BOOTSTRAP_CONFIG["log_keep_lines"])
HEARTBEAT_LOG_FILE = resolve_project_path(HEARTBEAT_CONFIG["log_file"])
HEARTBEAT_LOG_KEEP_LINES = int(HEARTBEAT_CONFIG["log_keep_lines"])
HEARTBEAT_INTERVAL_SEC = int(HEARTBEAT_CONFIG["interval_seconds"])
HEARTBEAT_REPLY_DEFAULT = TA_SERVER_CONFIG["heartbeat_reply"]


def _append_log(file_path, message: str, keep_lines: int) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if file_path.exists():
        with file_path.open("r", encoding="utf-8") as f:
            lines = [raw.rstrip("\n") for raw in f.readlines()]
    lines.append(message)
    lines = lines[-keep_lines:]
    with file_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        if lines:
            f.write("\n")


def log_heartbeat_line(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [heartbeat] {message}"
    print(line, flush=True)
    try:
        _append_log(HEARTBEAT_LOG_FILE, line, HEARTBEAT_LOG_KEEP_LINES)
    except OSError:
        pass


def log_bootstrap_start_once(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [heartbeat] {message}"
    try:
        _append_log(BOOTSTRAP_LOG_FILE, line, BOOTSTRAP_LOG_KEEP_LINES)
    except OSError:
        pass


def run_heartbeat_forever() -> None:
    startup_msg = f"taBOX heartbeat started (interval={HEARTBEAT_INTERVAL_SEC}s)"
    log_heartbeat_line(startup_msg)
    log_bootstrap_start_once(startup_msg)
    while True:
        heartbeat_sec, message = taServer_API_mac_heartbeat(HEARTBEAT_REPLY_DEFAULT)
        log_heartbeat_line(f"{message}")
        if heartbeat_sec is not None and heartbeat_sec > 10:
            time.sleep(heartbeat_sec)
        else:
            time.sleep(HEARTBEAT_INTERVAL_SEC)


if __name__ == "__main__":
    run_heartbeat_forever()
