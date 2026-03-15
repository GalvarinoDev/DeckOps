"""
shortcuts.py - DeckOps non-Steam shortcut installer

Creates non-Steam shortcuts for CoD4 Multiplayer and WaW Multiplayer so
they get independent controller configs from their SP counterparts.

Must be called while Steam is closed (same window as controller profiles).

Shortcut appids are deterministic:
  appid = (crc32(exe + name) | 0x80000000) & 0xffffffff
  CoD4 MP  ("iw3mp.exe"    + "Call of Duty 4: Modern Warfare - Multiplayer") = 3486055414
  WaW MP   ("CoDWaWmp.exe" + "Call of Duty: World at War - Multiplayer")     = 3884157948

Requires: pip install vdf
"""

import binascii
import os
import shutil
import time
import urllib.request

import vdf

STEAM_DIR = os.path.expanduser("~/.local/share/Steam")
MIN_UID   = 10000

# ── Shortcut definitions ──────────────────────────────────────────────────────

def _to_signed32(n):
    """Convert unsigned int32 appid to signed int32 for vdf binary format."""
    return n if n <= 2147483647 else n - 2**32

SHORTCUTS = {
    "cod4mp": {
        "appid":      _to_signed32(3486055414),
        "appid_unsigned": 3486055414,
        "name":       "Call of Duty 4: Modern Warfare - Multiplayer",
        "exe_name":   "iw3mp.exe",
        "game_appid": "7940",
        "icon_url":   "https://cdn2.steamgriddb.com/icon/59b109c700b500daa9ef3a6769bc8c6f.png",
        "grid_url":   "https://cdn2.steamgriddb.com/thumb/7a22b900577a6edbffd53153cea2999c.jpg",
        "wide_url":   "https://cdn2.steamgriddb.com/thumb/69a24bf40cd265fb00ae685cdaa040c7.jpg",
        "hero_url":   "https://cdn2.steamgriddb.com/hero_thumb/95bc8e097e09212ec0160a7bc0b46fd6.jpg",
        "logo_url":   "https://cdn2.steamgriddb.com/logo_thumb/0440169a43de927753429dd69ca8c735.png",
        "grid_ext":   "jpg",
        "logo_ext":   "png",
    },
    "t4mp": {
        "appid":      _to_signed32(3884157948),
        "appid_unsigned": 3884157948,
        "name":       "Call of Duty: World at War - Multiplayer",
        "exe_name":   "CoDWaWmp.exe",
        "game_appid": "10090",
        "icon_url":   "https://cdn2.steamgriddb.com/icon/854d6fae5ee42911677c739ee1734486.png",
        "grid_url":   "https://cdn2.steamgriddb.com/grid/bb933c55afc6987ae406e48ff58786d6.png",
        "wide_url":   "https://cdn2.steamgriddb.com/thumb/a6a0076c7e1907a4555b17cc2a6ebc85.jpg",
        "hero_url":   "https://cdn2.steamgriddb.com/hero_thumb/e369853df766fa44e1ed0ff613f563bd.jpg",
        "logo_url":   "https://cdn2.steamgriddb.com/logo_thumb/0a32bfcf5c87aa42d2a0367c1f6bb17c.png",
        "grid_ext":   "png",
        "logo_ext":   "png",
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_all_steam_uids():
    userdata = os.path.join(STEAM_DIR, "userdata")
    if not os.path.isdir(userdata):
        return []
    seen, uids = set(), []
    for entry in os.listdir(userdata):
        if not entry.isdigit() or int(entry) < MIN_UID:
            continue
        real = os.path.realpath(os.path.join(userdata, entry))
        if real in seen:
            continue
        seen.add(real)
        uids.append(entry)
    return uids


def _find_install_dir(appid, on_progress=None):
    library_paths = [os.path.join(STEAM_DIR, "steamapps")]
    vdf_path = os.path.join(STEAM_DIR, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf_path):
        with open(vdf_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"path"' in line:
                    parts = line.strip().split('"')
                    if len(parts) >= 4:
                        p = os.path.join(parts[3], "steamapps")
                        if os.path.isdir(p):
                            library_paths.append(p)

    for lib in library_paths:
        manifest = os.path.join(lib, f"appmanifest_{appid}.acf")
        if not os.path.exists(manifest):
            continue
        with open(manifest, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"installdir"' in line:
                    parts = line.strip().split('"')
                    if len(parts) >= 4:
                        install_dir = os.path.join(lib, "common", parts[3])
                        if os.path.isdir(install_dir):
                            return install_dir
    return None


def _download_file(url, dest_path, on_progress=None):
    def prog(msg):
        if on_progress:
            on_progress(msg)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp, \
             open(dest_path, "wb") as out:
            shutil.copyfileobj(resp, out)
        return True
    except Exception as e:
        prog(f"  ✗ Artwork download failed ({os.path.basename(dest_path)}): {e}")
        return False


# ── VDF read/write ────────────────────────────────────────────────────────────

def _read_shortcuts(path):
    """Return the shortcuts dict from shortcuts.vdf, or empty structure."""
    if not os.path.exists(path):
        return {"shortcuts": {}}
    try:
        with open(path, "rb") as f:
            return vdf.binary_load(f)
    except Exception:
        return {"shortcuts": {}}


def _write_shortcuts(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        vdf.binary_dump(data, f)


# ── Public API ────────────────────────────────────────────────────────────────

def install_shortcuts(game_keys, on_progress=None):
    """
    Create non-Steam shortcuts and download artwork for the given game keys.
    Must be called while Steam is closed.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    keys_to_process = [k for k in game_keys if k in SHORTCUTS]
    if not keys_to_process:
        return

    uids = _find_all_steam_uids()
    if not uids:
        prog("No Steam user accounts found — shortcuts skipped.")
        return

    for uid in uids:
        prog(f"Installing shortcuts for account {uid}...")

        shortcuts_path = os.path.join(
            STEAM_DIR, "userdata", uid, "config", "shortcuts.vdf"
        )
        grid_dir = os.path.join(STEAM_DIR, "userdata", uid, "config", "grid")
        os.makedirs(grid_dir, exist_ok=True)

        data    = _read_shortcuts(shortcuts_path)
        sc_dict = data.get("shortcuts", {})

        # Find next available index
        existing_indices = [int(k) for k in sc_dict.keys() if str(k).isdigit()]
        next_idx = max(existing_indices, default=-1) + 1

        for key in keys_to_process:
            sc_def = SHORTCUTS[key]

            install_dir = _find_install_dir(sc_def["game_appid"], on_progress)
            if not install_dir:
                prog(f"  ✗ Could not find install dir for {key} — skipping")
                continue

            exe_path   = os.path.join(install_dir, sc_def["exe_name"])
            exe_quoted = f'"{exe_path}"'

            # Check if shortcut already exists by AppName
            already = any(
                str(v.get("AppName", v.get("appname", ""))) == sc_def["name"]
                for v in sc_dict.values()
                if isinstance(v, dict)
            )
            if already:
                prog(f"  ✓ Shortcut already exists: {sc_def['name']}")
            else:
                compatdata = os.path.join(
                    STEAM_DIR, "steamapps", "compatdata", sc_def["game_appid"]
                )
                icon_path = os.path.join(grid_dir, f"{sc_def['appid_unsigned']}_icon.png")

                entry = {
                    "appid":              sc_def["appid"],
                    "AppName":            sc_def["name"],
                    "Exe":                exe_quoted,
                    "StartDir":           f'"{install_dir}"',
                    "icon":               icon_path,
                    "ShortcutPath":       "",
                    "LaunchOptions":      f"STEAM_COMPAT_DATA_PATH={compatdata} %command%",
                    "IsHidden":           0,
                    "AllowDesktopConfig": 1,
                    "AllowOverlay":       1,
                    "OpenVR":             0,
                    "Devkit":             0,
                    "DevkitGameID":       "",
                    "LastPlayTime":       int(time.time()),
                    "tags":               {"0": "DeckOps"},
                }

                sc_dict[str(next_idx)] = entry
                next_idx += 1
                prog(f"  ✓ Shortcut prepared: {sc_def['name']}")

            # ── Download artwork ──
            appid_str = str(sc_def["appid_unsigned"])
            artwork = [
                (sc_def["grid_url"],  f"{appid_str}p.{sc_def['grid_ext']}"),
                (sc_def["wide_url"],  f"{appid_str}.{sc_def['grid_ext']}"),
                (sc_def["hero_url"],  f"{appid_str}_hero.jpg"),
                (sc_def["icon_url"],  f"{appid_str}_icon.png"),
            ]
            if sc_def.get("logo_url") and sc_def.get("logo_ext"):
                artwork.append((sc_def["logo_url"], f"{appid_str}_logo.{sc_def['logo_ext']}"))

            for url, filename in artwork:
                if url and filename:
                    dest = os.path.join(grid_dir, filename)
                    if not os.path.exists(dest):
                        _download_file(url, dest, on_progress=on_progress)

        data["shortcuts"] = sc_dict

        try:
            _write_shortcuts(shortcuts_path, data)
            prog(f"  ✓ shortcuts.vdf written for uid {uid}")
        except Exception as e:
            prog(f"  ✗ Failed to write shortcuts.vdf: {e}")
