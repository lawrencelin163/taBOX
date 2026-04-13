#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   TARGET_SSID="RubyJiro" TARGET_PASSWORD="0918911190" WIFI_INTERFACE="wlan0" ./scripts/back_to_client.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

WIFI_INTERFACE="${WIFI_INTERFACE:-wlan0}"
TARGET_SSID="${TARGET_SSID:-RubyJiro}"
TARGET_PASSWORD="${TARGET_PASSWORD:-0918911190}"

if ! command -v nmcli >/dev/null 2>&1; then
  echo "nmcli not found. Please install NetworkManager first."
  exit 1
fi

echo "Switching ${WIFI_INTERFACE} back to client mode..."
nmcli radio wifi on
nmcli device set "${WIFI_INTERFACE}" managed yes

# Stop AP profile first.
nmcli connection down taBOX-AP >/dev/null 2>&1 || true
nmcli connection modify taBOX-AP connection.autoconnect no >/dev/null 2>&1 || true

# Ensure target client profile can autoconnect again.
nmcli connection modify "${TARGET_SSID}" connection.autoconnect yes >/dev/null 2>&1 || true
nmcli connection modify "${TARGET_SSID}" connection.autoconnect-priority 200 >/dev/null 2>&1 || true

nmcli device disconnect "${WIFI_INTERFACE}" >/dev/null 2>&1 || true

if [[ -n "${TARGET_PASSWORD}" ]]; then
  nmcli --wait 20 device wifi connect "${TARGET_SSID}" ifname "${WIFI_INTERFACE}" password "${TARGET_PASSWORD}"
else
  nmcli --wait 20 device wifi connect "${TARGET_SSID}" ifname "${WIFI_INTERFACE}"
fi

echo "Client mode ready. Connected to ${TARGET_SSID}."
nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device status
