#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

WIFI_INTERFACE="${WIFI_INTERFACE:-wlan0}"
AP_SSID="${AP_SSID:-taBOX-Setup}"

if [[ ! -f ".venv/bin/activate" ]]; then
	echo "Python virtualenv not found at .venv/bin/activate"
	exit 1
fi

AP_IPV4="$(nmcli -g IP4.ADDRESS device show "${WIFI_INTERFACE}" | head -n 1 | cut -d/ -f1 || true)"

echo ""
echo "Starting provisioning service..."
if [[ -n "${AP_IPV4}" ]]; then
	echo "  Current ${WIFI_INTERFACE} IP: ${AP_IPV4}"
else
	echo "  Could not detect ${WIFI_INTERFACE} IP yet."
	echo "  Run: nmcli -f GENERAL.CONNECTION,IP4.ADDRESS device show ${WIFI_INTERFACE}"
fi
echo ""
echo "App will try saved SSIDs first; AP mode starts only if all saved credentials fail."
echo "If AP fallback occurs, app logs will print the exact portal URL."
echo "Keep this terminal open. Press Ctrl+C to stop."
echo ""

# 2) Start Flask provisioning portal.
source .venv/bin/activate
exec python app.py
