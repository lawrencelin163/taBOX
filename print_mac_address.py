from __future__ import annotations

from taServer_API import _read_linux_mac_address
from taWifi import WIFI_INTERFACE


def print_mac_address() -> None:
    mac = _read_linux_mac_address(WIFI_INTERFACE)
    if mac:
        print(mac.replace(":", ""))
    else:
        print(f"MAC address not found ({WIFI_INTERFACE})")


if __name__ == "__main__":
    print_mac_address()