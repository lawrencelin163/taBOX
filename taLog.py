from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from tabox_config import load_config, resolve_project_path

CONFIG = load_config()
_TA_SERVER_CONFIG = CONFIG["ta_server"]
_WIFI_CONFIG = CONFIG["wifi"]
_BOOTSTRAP_CONFIG = CONFIG["bootstrap"]
_HEARTBEAT_CONFIG = CONFIG["heartbeat"]

SELF_UPDATE_LOG_FILE = resolve_project_path(_TA_SERVER_CONFIG.get("self_update_log_file", "Temp/self_update.log"))
WIFI_CHECK_LOG_FILE = resolve_project_path(_WIFI_CONFIG.get("wifi_check_log_file", "Temp/wifi_check.log"))
BOOTSTRAP_LOG_FILE = resolve_project_path(_BOOTSTRAP_CONFIG["log_file"])
BOOTSTRAP_LOG_KEEP_LINES = int(_BOOTSTRAP_CONFIG["log_keep_lines"])
HEARTBEAT_LOG_FILE = resolve_project_path(_HEARTBEAT_CONFIG["log_file"])
HEARTBEAT_LOG_KEEP_LINES = 120


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


def _self_update_print(message: str) -> None:
    line = f"[SELF-UPDATE] {message}"
    print(line)
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = Path(SELF_UPDATE_LOG_FILE)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {line}\n")
    except Exception as log_exc:  # pylint: disable=broad-except
        print(f"[SELF-UPDATE] plain logging failed: {log_exc}")


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


def _wifi_check_log(message: str) -> None:
    line = f"[WiFiCheck] {message}"
    print(line, flush=True)
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = Path(WIFI_CHECK_LOG_FILE)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {line}\n")
    except Exception as log_exc:  # pylint: disable=broad-except
        print(f"[WiFiCheck] logging failed: {log_exc}")


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
