"""
detect_hw.py - detect OS, device, and CPU architecture

Reads DMI identity and os-release at import time. Results are cached
for the process lifetime. All reads are best-effort: a missing sysfs
node or unrecognized string returns None and never raises.

This is a leaf module with no DeckOps imports.
"""

import os
import platform


# --- DMI product_name -> DEVICES key
# Values come from /sys/class/dmi/id/product_name on each device.
# ASUS repeats the model code (e.g. "RC71L_RC71L"), so those use prefix matching.

_DMI_EXACT = {
    # Valve
    "Jupiter":  "sd_lcd",
    "Galileo":  "sd_oled",
    "Fremont":  "steam_machine",
    # Lenovo (opaque model codes)
    "83E1":     "legion_go",
    "83L3":     "legion_go_s",
    "83N0":     "legion_go_2",
    "83N1":     "legion_go_2",
}

_DMI_PREFIX = [
    # ASUS: product_name may carry a suffix like RC71L_RC71L
    ("RC71L",  "rog_ally"),
    ("RC72LA", "rog_ally_x"),
    ("RC73YA", "xbox_ally_x"),
    ("RC73XA", "xbox_ally_x"),
    ("RC74XA", "xbox_ally_x"),
]

# MSI uses board_name (MS-xxxx) more reliably than product_name.
_DMI_BOARD = {
    "MS-1T8K": "msi_claw_8",
    "MS-1T41": "msi_claw_8",
}

# ---
# ARM handhelds have no DMI. Model strings are the ones Armada matches
# in /usr/libexec/armada/device-env.
_DT_MODEL = {
    "Retroid Pocket 6":           "rp6",
    "Retroid Pocket 6 TOP-DPAD":  "rp6",
}

# --- os-release ID -> os_key

_OS_ID_MAP = {
    "steamos":  "steamos",
    "bazzite":  "bazzite",
    "cachyos":  "cachyos",
    "armada":   "armada",
}


def _read_dmi(field: str) -> str:
    try:
        with open(f"/sys/class/dmi/id/{field}") as f:
            return f.read().strip()
    except OSError:
        return ""


def _read_os_release() -> dict:
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            kv = {}
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    kv[k] = v.strip('"')
            return kv
        except OSError:
            continue
    return {}


def detect_os() -> str | None:
    """Returns 'steamos', 'bazzite', 'cachyos', 'armada', or None."""
    os_id = _read_os_release().get("ID", "").lower()
    return _OS_ID_MAP.get(os_id)


def detect_device() -> str | None:
    """Returns a DEVICES key ('sd_lcd', 'rog_ally', etc.) or None."""
    product = _read_dmi("product_name")
    hit = _DMI_EXACT.get(product)
    if hit:
        return hit
    for prefix, key in _DMI_PREFIX:
        if product.startswith(prefix):
            return key
    board = _read_dmi("board_name")
    hit = _DMI_BOARD.get(board)
    if hit:
        return hit
    try:
        with open("/sys/firmware/devicetree/base/model") as f:
            return _DT_MODEL.get(f.read().strip("\0\n "))
    except OSError:
        return None


def detect_arch() -> str:
    """Returns 'x86_64' or 'aarch64' (or whatever platform.machine() says)."""
    return platform.machine()


def is_arm() -> bool:
    return detect_arch() in ("aarch64", "arm64")
