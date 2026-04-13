from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

from taServer_API import taServer_API_mac_login

BOOTSTRAP_LOG_FILE = Path(__file__).resolve().parent / "Temp" / "bootstrap.log"
HEARTBEAT_LOG_FILE = Path(__file__).resolve().parent / "Temp" / "hearbeat.log"
HEARTBEAT_INTERVAL_SEC = int(os.getenv("HEARTBEAT_INTERVAL_SEC", "600"))


def _append_log(file_path: Path, message: str, keep_lines: int) -> None:
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
        _append_log(HEARTBEAT_LOG_FILE, line, 1500)
    except OSError:
        pass


def log_bootstrap_start_once(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [heartbeat] {message}"
    try:
        _append_log(BOOTSTRAP_LOG_FILE, line, 500)
    except OSError:
        pass


def run_heartbeat_forever() -> None:
    startup_msg = f"taBOX heartbeat started (interval={HEARTBEAT_INTERVAL_SEC}s)"
    log_heartbeat_line(startup_msg)
    log_bootstrap_start_once(startup_msg)
    while True:
        ok, message = taServer_API_mac_login('heartbeat')
        status = "ok" if ok else "failed"
        log_heartbeat_line(f"mac_login {status}: {message}")
        time.sleep(HEARTBEAT_INTERVAL_SEC)


if __name__ == "__main__":
    run_heartbeat_forever()
