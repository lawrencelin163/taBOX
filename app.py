from __future__ import annotations

import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

from taServer_API import taServer_API_mac_login

app = Flask(__name__)

WIFI_INTERFACE = os.getenv("WIFI_INTERFACE", "wlan0")
SSID_STORE_FILE = Path(__file__).resolve().parent / "ssid_code_list.txt"
AP_MODE_SCRIPT = Path(__file__).resolve().parent / "scripts" / "enter_ap_mode.sh"
BOOTSTRAP_LOG_FILE = Path(__file__).resolve().parent / "Temp" / "bootstrap.log"

# Auto-try saved SSIDs should run only once at the beginning of a provisioning cycle.
BOOTSTRAP_ATTEMPTED = False
STARTUP_CONNECTED_SSID: str | None = None


def run_cmd(command: list[str], timeout: int = 20, extra_env: dict[str, str] | None = None) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    if extra_env:
        env.update(extra_env)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env)
        return completed.returncode, completed.stdout.strip(), completed.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "command timeout"


def get_interface_ipv4(interface: str) -> str | None:
    code, out, _ = run_cmd(["nmcli", "-g", "IP4.ADDRESS", "device", "show", interface], timeout=8)
    if code != 0 or not out:
        return None

    first = out.splitlines()[0].strip()
    if not first:
        return None
    return first.split("/", 1)[0]


def get_interface_connection_name(interface: str) -> str | None:
    code, out, _ = run_cmd(["nmcli", "-g", "GENERAL.CONNECTION", "device", "show", interface], timeout=8)
    if code != 0 or not out:
        return None
    name = out.splitlines()[0].strip()
    return name or None


def wait_for_ap_ipv4(interface: str, expected_connection: str = "taBOX-AP", timeout_sec: int = 20) -> str | None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        conn_name = get_interface_connection_name(interface)
        ip = get_interface_ipv4(interface)
        if conn_name == expected_connection and ip:
            return ip
        time.sleep(1)
    return None


def get_interface_general_state(interface: str) -> str:
    code, out, err = run_cmd(["nmcli", "-g", "GENERAL.STATE", "device", "show", interface], timeout=8)
    if code != 0:
        return f"unknown({err or out or 'nmcli error'})"
    return out.splitlines()[0].strip() if out else "unknown(empty)"


def is_password_error(stderr_or_stdout: str) -> bool:
    text = stderr_or_stdout.lower()
    keywords = [
        "secrets were required",
        "wrong password",
        "invalid key",
        "802-11-wireless-security.key-mgmt",
        "activation: failed",
    ]
    return any(keyword in text for keyword in keywords)


def scan_ssids() -> tuple[list[str], str | None]:
    # Prefer NetworkManager for predictable output on modern Raspberry Pi OS.
    code, out, err = run_cmd(
        ["nmcli", "-t", "-f", "SSID", "device", "wifi", "list", "ifname", WIFI_INTERFACE, "--rescan", "yes"]
    )
    if code != 0:
        return [], f"掃描失敗: {err or out or 'nmcli 掃描異常'}"

    ssids = sorted({line.strip() for line in out.splitlines() if line.strip()})
    return ssids, None


def connect_wifi(ssid: str, password: str, connection_name: str | None = None) -> tuple[bool, str]:
    if not ssid:
        return False, "SSID 不能為空"

    # Stop hotspot/AP profile if it exists, then connect as a station/client.
    run_cmd(["nmcli", "connection", "down", "taBOX-AP"], timeout=8)
    run_cmd(["nmcli", "device", "disconnect", WIFI_INTERFACE], timeout=8)

    if connection_name:
        # Ensure retries always use the provided credentials instead of an old profile secret.
        run_cmd(["nmcli", "connection", "delete", connection_name], timeout=8)
    else:
        # Remove stale SSID profile so a previous wrong password does not poison the next attempt.
        run_cmd(["nmcli", "connection", "delete", ssid], timeout=8)

    connect_cmd = ["nmcli", "--wait", "15", "device", "wifi", "connect", ssid, "ifname", WIFI_INTERFACE]
    if password:
        connect_cmd.extend(["password", password])
    if connection_name:
        connect_cmd.extend(["name", connection_name])

    code, out, err = run_cmd(connect_cmd, timeout=20)
    if code != 0:
        details = f"{err}\n{out}".strip()
        if code == 124:
            return False, "連線失敗（逾時），請確認密碼與訊號後再試一次。"
        if is_password_error(details):
            return False, "連線失敗（密碼錯誤）。請重新再試一次。"
        return False, f"連線失敗: {details or 'nmcli 回傳錯誤'}"

    verify_code, verify_out, verify_err = run_cmd(
        ["nmcli", "-t", "-f", "GENERAL.STATE", "device", "show", WIFI_INTERFACE],
        timeout=8,
    )
    if verify_code != 0:
        return False, f"連線狀態檢查失敗: {verify_err or verify_out}"
    if "100 (connected)" not in verify_out:
        return False, f"尚未連線成功，目前狀態: {verify_out}"

    # Consider Wi-Fi connected when interface has an IPv4 address on the new link.
    ip_addr = get_interface_ipv4(WIFI_INTERFACE)
    if not ip_addr:
        return False, f"已連上 {ssid}，但尚未取得 IP 位址"

    if connection_name:
        # Temporary auto-try profiles should never become future default autoconnect targets.
        run_cmd(["nmcli", "connection", "modify", connection_name, "connection.autoconnect", "no"], timeout=8)
        run_cmd(["nmcli", "connection", "modify", "taBOX-AP", "connection.autoconnect", "no"], timeout=8)
        return True, "連線成功"

    # Keep normal behavior after successful provisioning: prefer selected client SSID.
    run_cmd(["nmcli", "connection", "modify", ssid, "connection.autoconnect", "yes"], timeout=8)
    run_cmd(["nmcli", "connection", "modify", ssid, "connection.autoconnect-priority", "100"], timeout=8)
    run_cmd(["nmcli", "connection", "modify", "taBOX-AP", "connection.autoconnect", "no"], timeout=8)

    return True, "連線成功"


def schedule_exit_zero(delay_sec: float = 1.0) -> None:
    def _exit_ok() -> None:
        os._exit(0)

    # Exit in a timer so the current HTTP response can be sent first.
    threading.Timer(delay_sec, _exit_ok).start()


def save_wifi_credentials(ssid: str, password: str) -> None:
    SSID_STORE_FILE.touch(exist_ok=True)
    os.chmod(SSID_STORE_FILE, 0o600)
    with SSID_STORE_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{ssid}\t{password}\n")


def load_wifi_credentials() -> list[tuple[str, str]]:
    if not SSID_STORE_FILE.exists():
        return []

    credentials: list[tuple[str, str]] = []
    seen: set[str] = set()

    with SSID_STORE_FILE.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t", 1)
            ssid = parts[0].strip()
            password = parts[1].strip() if len(parts) == 2 else ""
            if not ssid or ssid in seen:
                continue

            seen.add(ssid)
            credentials.append((ssid, password))

    return credentials


def try_saved_ssids() -> tuple[bool, str | None, str | None]:
    credentials = load_wifi_credentials()
    if not credentials:
        return False, None, "沒有可嘗試的 SSID 紀錄"

    scan_list, scan_error = scan_ssids()
    if scan_error:
        return False, None, scan_error

    visible_ssids = set(scan_list)
    tried_any = False
    for idx, (ssid, password) in enumerate(credentials, start=1):
        if ssid not in visible_ssids:
            continue
        tried_any = True
        temp_name = f"taBOX-autotry-{idx}"
        success, _ = connect_wifi(ssid, password, connection_name=temp_name)
        if success:
            return True, ssid, None

    if not tried_any:
        return False, None, "已存 SSID 目前都不在可掃描範圍"
    return False, None, "已嘗試所有可見 SSID，皆無法連線"


def start_ap_mode() -> tuple[bool, str]:
    if not AP_MODE_SCRIPT.exists():
        return False, f"找不到 AP mode 腳本: {AP_MODE_SCRIPT}"

    code, out, err = run_cmd(
        ["bash", str(AP_MODE_SCRIPT)],
        timeout=35,
        extra_env={
            "WIFI_INTERFACE": WIFI_INTERFACE,
            "AP_SSID": os.getenv("AP_SSID", "taBOX-Setup"),
            "AP_PASSWORD": os.getenv("AP_PASSWORD", "12345678"),
            "AP_IPV4_CIDR": os.getenv("AP_IPV4_CIDR", "10.42.0.1/24"),
        },
    )
    if code == 0:
        return True, "已切回 AP mode"
    return False, f"切回 AP mode 失敗: {err or out or '未知錯誤'}"


def log_bootstrap(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    try:
        BOOTSTRAP_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        if BOOTSTRAP_LOG_FILE.exists():
            with BOOTSTRAP_LOG_FILE.open("r", encoding="utf-8") as f:
                lines = [raw.rstrip("\n") for raw in f.readlines()]
        lines.append(line)
        lines = lines[-500:]
        with BOOTSTRAP_LOG_FILE.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            if lines:
                f.write("\n")
    except OSError:
        # Keep startup resilient even if local log writing fails.
        pass


def log_connect_diagnostics(stage: str, ssid: str, start_monotonic: float, result_message: str) -> None:
    elapsed = time.monotonic() - start_monotonic
    state = get_interface_general_state(WIFI_INTERFACE)
    ip = get_interface_ipv4(WIFI_INTERFACE) or "none"
    log_bootstrap(
        f"[connect] stage={stage} ssid={ssid or '(empty)'} elapsed={elapsed:.2f}s "
        f"state={state} ip={ip} msg={result_message}"
    )


def finalize_connected_and_login(ssid: str, source: str) -> None:
    state = get_interface_general_state(WIFI_INTERFACE)
    ip = get_interface_ipv4(WIFI_INTERFACE) or "none"
    log_bootstrap(
        f"[finalize] source={source} ssid={ssid} state={state} ip={ip} "
        "next=wait 3s then taServer login"
    )
    time.sleep(10)
    api_ok, api_msg = taServer_API_mac_login('login')
    log_bootstrap(f"[taServer] {api_msg}")


def bootstrap_network_on_start() -> bool:
    global BOOTSTRAP_ATTEMPTED
    global STARTUP_CONNECTED_SSID

    if BOOTSTRAP_ATTEMPTED:
        return STARTUP_CONNECTED_SSID is None

    BOOTSTRAP_ATTEMPTED = True
    log_bootstrap("[bootstrap] checking saved Wi-Fi credentials...")
    success, connected_ssid, reason = try_saved_ssids()
    if success and connected_ssid:
        STARTUP_CONNECTED_SSID = connected_ssid
        log_bootstrap(f"[bootstrap] auto-connect success: SSID={connected_ssid}")
        finalize_connected_and_login(connected_ssid, "bootstrap")
        return False

    log_bootstrap(f"[bootstrap] auto-connect failed: {reason or 'unknown reason'}")
    ap_ok, ap_message = start_ap_mode()
    if ap_ok:
        log_bootstrap("[bootstrap] fallback to AP mode enabled")
        ap_ip = wait_for_ap_ipv4(WIFI_INTERFACE)
        if ap_ip:
            log_bootstrap(f"[bootstrap] AP portal URL: http://{ap_ip}:5000")
        else:
            log_bootstrap(
                "[bootstrap] AP IP not ready yet. Run: nmcli -f GENERAL.CONNECTION,IP4.ADDRESS device show "
                f"{WIFI_INTERFACE}"
            )
        return True
    else:
        log_bootstrap(f"[bootstrap] fallback to AP mode failed: {ap_message}")
        return True


def render_provision_page(message: str | None = None, message_type: str | None = None, selected_ssid: str | None = None):
    ssids, scan_error = scan_ssids()
    return render_template(
        "index.html",
        page_state="provision",
        ssids=ssids,
        scan_error=scan_error,
        message=message,
        message_type=message_type,
        selected_ssid=selected_ssid,
    )


@app.after_request
def add_no_cache_headers(response):
    # Captive probe requests should not be cached by clients.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/", methods=["GET"])
def index():
    if STARTUP_CONNECTED_SSID:
        return render_template(
            "index.html",
            page_state="connected",
            connected_ssid=STARTUP_CONNECTED_SSID,
            message="已自動連線到已儲存 Wi-Fi",
            message_type="success",
        )

    return render_provision_page()


@app.route("/provision", methods=["GET"])
def provision():
    return render_provision_page()


@app.route("/connect", methods=["POST"])
def connect():
    ssid = request.form.get("ssid", "").strip()
    password = request.form.get("password", "").strip()
    connect_started = time.monotonic()

    success, message = connect_wifi(ssid, password)
    if success:
        log_connect_diagnostics("success", ssid, connect_started, message)
        finalize_connected_and_login(ssid, "manual-connect")
        save_wifi_credentials(ssid, password)
        schedule_exit_zero(1.2)
        return render_template(
            "index.html",
            page_state="connected",
            connected_ssid=ssid,
            message="連線成功",
            message_type="success",
        )

    log_connect_diagnostics("failed", ssid, connect_started, message)
    # One-shot provisioning flow: do not switch back to AP for retries in this mode.
    schedule_exit_zero(1.2)

    return render_template(
        "index.html",
        page_state="finished",
        message="連線流程已執行，程式即將結束。",
        message_type="success" if success else "error",
    )
@app.route("/finish", methods=["POST"])
def finish():
    shutdown_func = request.environ.get("werkzeug.server.shutdown")
    if shutdown_func:
        shutdown_func()
    else:
        # Give the browser a short time window to receive the response first.
        threading.Timer(1.0, lambda: os._exit(0)).start()

    return render_template(
        "index.html",
        page_state="finished",
        message="程式已結束",
        message_type="success",
    )


@app.route("/refresh", methods=["POST"])
def refresh():
    return redirect(url_for("provision"))


@app.route("/api/apmode/start", methods=["POST"])
def api_start_apmode():
    success, message = start_ap_mode()
    status_code = 200 if success else 500
    return {"ok": success, "message": message}, status_code


@app.route("/api/device-info", methods=["GET"])
def api_device_info():
    host = os.uname().nodename
    ip = get_interface_ipv4(WIFI_INTERFACE)
    return {
        "ok": True,
        "hostname": host,
        "mdns": f"{host}.local",
        "wifi_interface": WIFI_INTERFACE,
        "wifi_ip": ip,
    }


# Common captive-portal probe paths on major mobile OSes.
@app.route("/generate_204", methods=["GET"])
@app.route("/gen_204", methods=["GET"])
@app.route("/hotspot-detect.html", methods=["GET"])
@app.route("/ncsi.txt", methods=["GET"])
@app.route("/connecttest.txt", methods=["GET"])
@app.route("/library/test/success.html", methods=["GET"])
@app.route("/success.txt", methods=["GET"])
@app.route("/success.html", methods=["GET"])
@app.route("/canonical.html", methods=["GET"])
@app.route("/redirect", methods=["GET"])
@app.route("/fwlink", methods=["GET"])
@app.route("/connectivity-check", methods=["GET"])
@app.route("/check_network_status.txt", methods=["GET"])
def captive_probe_redirect():
    return redirect(url_for("index"), code=302)


@app.route("/<path:_path>", methods=["GET"])
def captive_catch_all(_path: str):
    # Unknown GETs are usually OS probe URLs; send them to the portal page.
    return redirect(url_for("index"), code=302)


if __name__ == "__main__":
    should_start_portal = bootstrap_network_on_start()
    if not should_start_portal:
        log_bootstrap("[bootstrap] provisioning portal skipped (auto-connect already successful)")
        raise SystemExit(0)
    app.run(host="0.0.0.0", port=5000, debug=False)
