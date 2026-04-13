#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   WIFI_INTERFACE="wlan0" ./scripts/connect_client_mode.sh "HomeWiFi" "password"

SSID="${1:-}"
PASSWORD="${2:-}"
WIFI_INTERFACE="${WIFI_INTERFACE:-wlan0}"

if [[ -z "${SSID}" ]]; then
  echo "SSID is required."
  exit 1
fi

if ! command -v nmcli >/dev/null 2>&1; then
  echo "nmcli not found. Please install NetworkManager first."
  exit 1
fi

nmcli connection down taBOX-AP >/dev/null 2>&1 || true
nmcli device disconnect "${WIFI_INTERFACE}" >/dev/null 2>&1 || true

if [[ -n "${PASSWORD}" ]]; then
  nmcli device wifi connect "${SSID}" ifname "${WIFI_INTERFACE}" password "${PASSWORD}"
else
  nmcli device wifi connect "${SSID}" ifname "${WIFI_INTERFACE}"
fi

echo "Connected to ${SSID}"
