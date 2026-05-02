from __future__ import annotations

import os
import subprocess


def _run_cmd(command: list[str], timeout: int) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env)
        return completed.returncode, completed.stdout.strip(), completed.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "command timeout"


def _run_systemctl(args: list[str], timeout: int) -> tuple[int, str, str]:
    # Guard against accidental duplicated token: ["systemctl", ...].
    if args and args[0] == "systemctl":
        args = args[1:]

    code, out, err = _run_cmd(["systemctl", *args], timeout=timeout)
    if code == 0:
        return code, out, err

    details = f"{err} {out}".lower()
    need_auth = "interactive authentication required" in details or "authentication is required" in details
    if not need_auth:
        return code, out, err

    sudo_code, sudo_out, sudo_err = _run_cmd(["sudo", "-n", "systemctl", *args], timeout=timeout)
    if sudo_code == 0:
        return sudo_code, sudo_out, sudo_err

    merged_err = sudo_err or err or out
    return sudo_code, sudo_out, merged_err
