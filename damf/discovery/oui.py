"""MAC Address OUI (Organizationally Unique Identifier) lookup for embedded devices."""

from __future__ import annotations

# Normalized 6-hex-char prefixes (uppercase, no colons) mapped to (Vendor, Default Board Type, Arch)
KNOWN_EMBEDDED_OUIS: dict[str, tuple[str, str, str]] = {
    # Raspberry Pi Foundation / Trading
    "B827EB": ("Raspberry Pi Foundation", "raspberry-pi-3", "arm64"),
    "DCA632": ("Raspberry Pi Trading", "raspberry-pi-4", "arm64"),
    "E45F01": ("Raspberry Pi Trading", "raspberry-pi-4", "arm64"),
    "28CD4C": ("Raspberry Pi Trading", "raspberry-pi-zero2", "arm64"),
    "2CCF67": ("Raspberry Pi Trading", "raspberry-pi-5", "arm64"),
    "D83ADD": ("Raspberry Pi Trading", "raspberry-pi-5", "arm64"),
    # Texas Instruments (Sitara AM335x / AM62x /Jacinto / LaunchPad / BeagleBone)
    "0017E9": ("Texas Instruments", "ti-sitara", "arm"),
    "001830": ("Texas Instruments", "ti-am335x", "arm"),
    "D0FF50": ("Texas Instruments", "ti-am62x", "arm64"),
    "C4EDBA": ("Texas Instruments", "ti-launchpad", "arm"),
    "F4B85E": ("Texas Instruments", "ti-evm", "arm64"),
    "04A316": ("Texas Instruments", "beaglebone-black", "arm"),
    "EC1127": ("Texas Instruments", "ti-jacinto", "arm64"),
    # Espressif (ESP32 / ESP8266)
    "240AC4": ("Espressif Inc.", "esp32", "xtensa"),
    "30AEA4": ("Espressif Inc.", "esp32", "xtensa"),
    "A4CF12": ("Espressif Inc.", "esp32-s3", "xtensa"),
    # NVIDIA Jetson
    "00044B": ("NVIDIA", "jetson-nano", "arm64"),
    "48B02D": ("NVIDIA", "jetson-orin", "arm64"),
    # Arduino
    "A8610A": ("Arduino AG", "arduino-portenta", "arm"),
    # Google / Android reference devices
    "3C5AB4": ("Google Inc.", "android-pixel", "arm64"),
}


def normalize_mac(mac: str) -> str:
    """Normalize a MAC address into standard colon-separated uppercase format (XX:XX:XX:XX:XX:XX)."""
    parts = [p.strip() for p in mac.replace("-", ":").split(":") if p.strip()]
    if len(parts) == 6:
        try:
            return ":".join(f"{int(p, 16):02X}" for p in parts)
        except ValueError:
            pass
    hex_chars = "".join(ch for ch in mac.upper() if ch in "0123456789ABCDEF")
    if len(hex_chars) != 12:
        return mac.upper()
    return ":".join(hex_chars[i : i + 2] for i in range(0, 12, 2))


def lookup_mac_vendor(mac: str) -> tuple[str, str, str] | None:
    """Return (vendor_name, board_type, arch) if the MAC OUI matches a known embedded vendor."""
    normalized = normalize_mac(mac)
    prefix = normalized.replace(":", "")[:6]
    return KNOWN_EMBEDDED_OUIS.get(prefix)
