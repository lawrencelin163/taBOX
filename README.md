# taBOX
ta-Agents BOX ( Based on OpenClaw )

## Raspberry Pi 4B Wi-Fi Setup Flow

This project now provides a simple Wi-Fi provisioning page:

1. Put Raspberry Pi into AP mode.
2. User connects to Raspberry Pi AP.
3. Open setup page in browser.
4. Select scanned SSID and enter password.
5. Click connect to switch Raspberry Pi to client mode.
6. On success, SSID and password are appended to `ssid_code_list.txt`.

### Prerequisites

- Raspberry Pi OS with NetworkManager (`nmcli` command available)
- Python environment with dependencies in `requirements.txt`

### Start AP Mode

```bash
cd /home/yf/GitPS/taBOX
AP_SSID="taBOX-Setup" AP_PASSWORD="12345678" WIFI_INTERFACE="wlan0" ./scripts/enter_ap_mode.sh
```

### Run Web Portal

```bash
cd /home/yf/GitPS/taBOX
source env/bin/activate
python app.py
```

### One Command: AP + Portal (Recommended)

```bash
cd /home/yf/GitPS/taBOX
WIFI_INTERFACE="wlan0" AP_SSID="taBOX-Setup" ./scripts/start_provisioning.sh
```

This command will:

1. Enter AP mode.
2. Print the phone URL (for example `http://10.42.0.1:5000`).
3. Start `app.py`.

Then open from a connected user device:

- `http://<raspberry-pi-ap-ip>:5000`

### Manual Client Switch Script (Optional)

```bash
cd /home/yf/GitPS/taBOX
WIFI_INTERFACE="wlan0" ./scripts/legacy/connect_client_mode.sh "YourSSID" "YourPassword"
```

`back_to_client.sh` is also archived under `scripts/legacy/` for manual maintenance use.

### Auto Start On Boot (systemd)

Service file is provided at `systemd/tabox-provision.service`.
Heartbeat service file is provided at `systemd/tabox-heartbeat.service`.

Install and enable:

```bash
cd /home/yf/GitPS/taBOX
sudo cp systemd/tabox-provision.service /etc/systemd/system/
sudo cp systemd/tabox-heartbeat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tabox-provision.service
sudo systemctl start tabox-provision.service
```

Check status:

```bash
sudo systemctl status tabox-provision.service
sudo systemctl status tabox-heartbeat.service
```

`tabox-provision.service` will auto-start `tabox-heartbeat.service` after provisioning exits successfully.
Heartbeat calls `taServer_API_mac_login()` every 10 minutes (configurable via `HEARTBEAT_INTERVAL_SEC`).

Monitor runing status:

```bash
sudo journalctl -u tabox-provision.service -f
```

If your user/path is different, edit `User`, `WorkingDirectory`, and `ExecStart` in the service file first.

### API Control: Start AP Mode

Flask endpoint:

- `POST /api/apmode/start`

This endpoint calls:

- `systemctl start apmode`

Response example:

```json
{"ok": true, "message": "已切回 AP mode"}
```

### Fallback Mechanism

If Wi-Fi connection fails in `/connect`, backend will automatically run AP fallback (`systemctl start apmode`) and append that result to the error message shown on the page.
