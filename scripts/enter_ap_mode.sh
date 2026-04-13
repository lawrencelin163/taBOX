#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   AP_SSID="taBOX-Setup" WIFI_INTERFACE="wlan0" ./scripts/enter_ap_mode.sh

WIFI_INTERFACE="${WIFI_INTERFACE:-wlan0}"
AP_SSID="${AP_SSID:-taBOX-Setup}"
AP_IPV4_CIDR="${AP_IPV4_CIDR:-10.42.0.1/24}"

if ! command -v nmcli >/dev/null 2>&1; then
  echo "nmcli not found. Please install NetworkManager first."
  exit 1
fi

echo "Bringing up AP mode on ${WIFI_INTERFACE}..."
nmcli radio wifi on
nmcli device set "${WIFI_INTERFACE}" managed yes

# Avoid immediate fallback to saved client SSIDs while provisioning in AP mode.
while IFS=: read -r CONN_NAME CONN_TYPE; do
  if [[ "${CONN_TYPE}" == "802-11-wireless" && "${CONN_NAME}" != "taBOX-AP" ]]; then
    nmcli connection modify "${CONN_NAME}" connection.autoconnect no >/dev/null 2>&1 || true
  fi
done < <(nmcli -t -f NAME,TYPE connection show)

nmcli connection down taBOX-AP >/dev/null 2>&1 || true
nmcli connection delete taBOX-AP >/dev/null 2>&1 || true

nmcli connection add type wifi ifname "${WIFI_INTERFACE}" con-name taBOX-AP autoconnect yes ssid "${AP_SSID}"
nmcli connection modify taBOX-AP 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared ipv4.addresses "${AP_IPV4_CIDR}" ipv6.method ignore
nmcli connection modify taBOX-AP connection.autoconnect-priority 999
nmcli connection up taBOX-AP

echo "AP mode is ready. SSID=${AP_SSID}, IP=${AP_IPV4_CIDR}"
