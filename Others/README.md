# taBOX
ta-Agents BOX ( Based on OpenClaw )

## Raspberry Pi 4B Wi-Fi Setup Flow

This project now provides a simple Wi-Fi provisioning page:

1. Put Raspberry Pi into AP mode.
2. User connects to Raspberry Pi AP.
3. Open setup page in browser.
4. Select scanned SSID and enter password.
5. Click connect to switch Raspberry Pi to client mode.
6. On success, SSID and password are stored in `taBOX.json` under `wifi.saved_networks`.

### Prerequisites

- Raspberry Pi OS with NetworkManager (`nmcli` command available)
- Python environment with dependencies in `requirements.txt`

### Configuration

All Python-side configuration now lives in `taBOX.json` at the project root.

This includes:

- Wi-Fi interface and saved Wi-Fi credentials
- AP mode SSID/password/IP settings
- Flask host/port/debug settings
- taServer URL, token, timeout, and MAC override
- Heartbeat interval and log paths
- Telegram bot settings
- Resend email settings

Edit `taBOX.json` before deploying to a new device.
Use `taBOX.template.json` as the placeholder-based schema reference for new devices or reviews.

Fields that are still normal config, but may contain sensitive values:

- `wifi.saved_networks[*].password`
- `ta_server.mac_token`
- `ta_server.mac_address`
- `telegram.default_recipient.bot_token`
- `telegram.default_recipient.chat_id`
- `telegram.demo.bots[*].bot_token`
- `telegram.demo.bots[*].chat_id`
- `resend.auth.api_key`
- `resend.defaults.to`

Service-like config sections use a consistent layout:

- `base_url`: endpoint root or API URL
- `auth`: secrets or tokens
- `requests`: timeout and request behavior
- `defaults`: default payload values
- `demo`: service-specific grouped settings

`taBOX.json` is treated as the runtime config file for this project, not only as an example file.

### Start AP Mode

```bash
cd /home/yf/GitPS/taBOX
AP_SSID="taBOX-Setup" AP_PASSWORD="12345678" WIFI_INTERFACE="wlan0" ./scripts/enter_ap_mode.sh
```

### Run Web Portal

```bash
cd /home/yf/GitPS/taBOX
source .venv/bin/activate
python app.py
```

### One Command: Portal Startup (Recommended)

```bash
cd /home/yf/GitPS/taBOX
./scripts/start_init.sh
```

This command will:

1. Activate the local `.venv`.
2. Start `app.py`.
3. Let the app try saved SSIDs first, then fall back to AP mode when needed.

Then open from a connected user device:

- `http://<raspberry-pi-ap-ip>:<flask.port>`

If your environment is still named `env`, use `./scripts/start_init_env.sh` instead.

### Manual Client Switch Script (Optional)

```bash
cd /home/yf/GitPS/taBOX
WIFI_INTERFACE="wlan0" ./scripts/legacy/connect_client_mode.sh "YourSSID" "YourPassword"
```

`back_to_client.sh` is also archived under `scripts/legacy/` for manual maintenance use.

### Auto Start On Boot (systemd)

Init service file is provided at `systemd/tabox-init.service`.
Heartbeat service file is provided at `systemd/tabox-heartbeat.service`.

Install and enable:

```bash
cd ~/GitPS/taBOX
./scripts/taBOX_Install.sh

這裏會把這兩個 service， copy 到 system 裏面去.
另外, openclaw-gateway.service, 也要 copy 哦 :

sudo cp /home/kl/GitPS/taBOX/systemd/openclaw-gateway.service /etc/systemd/system/

只有你安裝並 enable 之後，才會變成開機自動啟動
sudo systemctl enabled openclaw-gateway.service 
( 我們改成 由 tabox-provision 來啓動，所以，不要 enable 他)
```

Check status:

```bash
sudo systemctl status tabox-init.service
sudo systemctl status tabox-heartbeat.service
```

`tabox-init.service` is the init/provisioning service in this repo.
Heartbeat interval is configured in `taBOX.json` under `heartbeat.interval_seconds`.

Monitor runing status:

```bash
sudo journalctl -u tabox-init.service -f
```

If your user/path is different, edit `User`, `WorkingDirectory`, and `ExecStart` in the service file first.

### API Control: Start AP Mode

Flask endpoint:

- `POST /api/apmode/start`

This endpoint calls:

- `scripts/enter_ap_mode.sh`

Response example:

```json
{"ok": true, "message": "已切回 AP mode"}
```

### Fallback Mechanism

If Wi-Fi connection fails during bootstrap, backend will automatically run AP fallback through `scripts/enter_ap_mode.sh`.


### 如果要把 openclaw-gateway.service 刪掉：
```bash
sudo systemctl disable openclaw-gateway.service && sudo systemctl stop openclaw-gateway.service && sudo rm /etc/systemd/system/openclaw-gateway.service && sudo systemctl daemon-reload
```