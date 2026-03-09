import os
import re
import stat
import shutil
import subprocess


def get_proton_path(steam_root):
    """
    Find the newest Proton version installed in the Steam common folder.
    Uses numeric version sorting so Proton 10 ranks above Proton 9.
    """
    common = os.path.join(steam_root, "steamapps", "common")
    if not os.path.exists(common):
        return None

    def _version_key(name):
        # Extract all numeric parts for proper numeric comparison
        # e.g. "Proton 10.0" → (10, 0), "Proton 9.0" → (9, 0)
        parts = re.findall(r'\d+', name)
        return tuple(int(p) for p in parts)

    proton_dirs = [
        d for d in os.listdir(common)
        if d.startswith("Proton") and
        os.path.exists(os.path.join(common, d, "proton"))
    ]

    if not proton_dirs:
        return None

    proton_dirs.sort(key=_version_key, reverse=True)
    return os.path.join(common, proton_dirs[0], "proton")


def find_compatdata(steam_root, appid):
    """
    Find the Wine prefix folder for a given Steam appid.
    Returns the path or None if not found.
    """
    compatdata = os.path.join(
        steam_root, "steamapps", "compatdata", str(appid)
    )
    if os.path.exists(compatdata):
        return compatdata
    return None


def get_plutonium_launcher(compatdata_path):
    """
    Return the path to plutonium-launcher-win32.exe inside the given prefix,
    or None if not found.
    """
    launcher = os.path.join(
        compatdata_path,
        "pfx", "drive_c", "users", "steamuser",
        "AppData", "Local", "Plutonium", "bin",
        "plutonium-launcher-win32.exe"
    )
    if os.path.exists(launcher):
        return launcher
    return None


def write_wrapper_script(exe_path, script_content, original_size=None):
    """
    Write a bash wrapper script to replace the original exe.
    Backs up the original first, then writes and chmod's the script.
    Pads to original_size with null bytes so Steam's file validation passes.
    """
    backup_path = exe_path + ".bak"
    if not os.path.exists(backup_path) and os.path.exists(exe_path):
        shutil.copy2(exe_path, backup_path)

    script_bytes = script_content.encode("utf-8")

    if original_size and original_size > len(script_bytes):
        script_bytes += b"\x00" * (original_size - len(script_bytes))

    with open(exe_path, "wb") as f:
        f.write(script_bytes)

    os.chmod(exe_path, os.stat(exe_path).st_mode |
             stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
