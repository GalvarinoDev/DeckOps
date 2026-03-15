"""
shortcut.py — DeckOps non-Steam shortcut creator

Creates non-Steam game shortcuts in Steam for CoD4 Multiplayer (CoD4x) and
World at War Multiplayer (Plutonium). These shortcuts point to the original
game exes in the Steam library and use the original compatdata prefixes.

Only runs if the user selected these games during DeckOps setup and they
were successfully installed via the respective client installers.

Shortcuts include:
  - Proper artwork (icon, grid, wide, hero, logo) from SteamGridDB
  - Correct compatdata prefix via launch options
  - Controller template assignment based on gyro mode:
      * CoD4 MP → "other" template (other_hold / other_toggle)
      * WaW MP  → "standard" template (hold / toggle)
  - Steam Input enabled (AllowDesktopConfig)

Called at the end of InstallScreen._run() after client installation completes.
"""

import os
import re
import struct
import binascii
import shutil
import urllib.request

# ── Shortcut definitions ──────────────────────────────────────────────────────

SHORTCUTS = {
    "cod4mp": {
        "name":            "Call of Duty 4: Modern Warfare - Multiplayer",
        "exe_name":        "iw3mp.exe",
        "game_appid":      "7940",
        "template_type":   "other",  # Uses other_hold / other_toggle
        "icon_url":        "https://cdn2.steamgriddb.com/icon/59b109c700b500daa9ef3a6769bc8c6f.png",
        "grid_url":        "https://cdn2.steamgriddb.com/thumb/7a22b900577a6edbffd53153cea2999c.jpg",
        "wide_url":        "https://cdn2.steamgriddb.com/thumb/69a24bf40cd265fb00ae685cdaa040c7.jpg",
        "hero_url":        "https://cdn2.steamgriddb.com/hero_thumb/95bc8e097e09212ec0160a7bc0b46fd6.jpg",
        "logo_url":        "https://cdn2.steamgriddb.com/logo_thumb/0440169a43de927753429dd69ca8c735.png",
        "icon_ext":        "png",
        "grid_ext":        "jpg",
        "wide_ext":        "jpg",
        "hero_ext":        "jpg",
        "logo_ext":        "png",
    },
    "t4mp": {
        "name":            "Call of Duty: World at War - Multiplayer",
        "exe_name":        "CoDWaWmp.exe",
        "game_appid":      "10090",
        "template_type":   "standard",  # Uses hold / toggle
        "icon_url":        "https://cdn2.steamgriddb.com/icon/854d6fae5ee42911677c739ee1734486.png",
        "grid_url":        "https://cdn2.steamgriddb.com/grid/bb933c55afc6987ae406e48ff58786d6.png",
        "wide_url":        "https://cdn2.steamgriddb.com/thumb/a6a0076c7e1907a4555b17cc2a6ebc85.jpg",
        "hero_url":        "https://cdn2.steamgriddb.com/hero_thumb/e369853df766fa44e1ed0ff613f563bd.jpg",
        "logo_url":        "https://cdn2.steamgriddb.com/logo_thumb/0a32bfcf5c87aa42d2a0367c1f6bb17c.png",
        "icon_ext":        "png",
        "grid_ext":        "png",
        "wide_ext":        "jpg",
        "hero_ext":        "jpg",
        "logo_ext":        "png",
    },
}

# ── Paths ─────────────────────────────────────────────────────────────────────

STEAM_ROOT     = os.path.expanduser("~/.local/share/Steam")
USERDATA_DIR   = os.path.join(STEAM_ROOT, "userdata")
COMPAT_ROOT    = os.path.join(STEAM_ROOT, "steamapps", "compatdata")

_HERE          = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT   = os.path.dirname(_HERE)
ASSETS_DIR     = os.path.join(PROJECT_ROOT, "assets", "controllers")

MIN_UID = 10000

_BROWSER_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
}


# ── Steam user ID helpers ─────────────────────────────────────────────────────

def _find_all_steam_uids() -> list:
    """Return all valid Steam user ID folders from userdata/."""
    if not os.path.isdir(USERDATA_DIR):
        return []
    seen, uids = set(), []
    for entry in os.listdir(USERDATA_DIR):
        if not entry.isdigit() or int(entry) < MIN_UID:
            continue
        real = os.path.realpath(os.path.join(USERDATA_DIR, entry))
        if real in seen:
            continue
        seen.add(real)
        uids.append(entry)
    return uids


# ── Shortcut appid calculation ────────────────────────────────────────────────
# Steam generates a unique appid for non-Steam shortcuts using CRC32.
# Used for artwork filenames and controller config.

def _generate_shortcut_appid(exe_path: str, name: str) -> int:
    """
    Generate the Steam shortcut appid for a non-Steam game.
    This matches Steam's internal algorithm for artwork file naming.
    
    The formula is: (CRC32(utf8(exe + name)) | 0x80000000)
    Then for artwork we need the "legacy" format which is just the top 32 bits.
    """
    key = (exe_path + name).encode("utf-8")
    crc = binascii.crc32(key) & 0xFFFFFFFF
    # Steam's shortcut appid has the high bit set
    high = (crc | 0x80000000)
    # For artwork, Steam uses (high << 32) | 0x02000000, then takes top 32 bits
    # Simplified: we just need the artwork ID which is the high value
    return high


def _generate_artwork_id(exe_path: str, name: str) -> int:
    """
    Generate the artwork ID used for grid/hero/logo filenames.
    Steam uses a different calculation for artwork than the shortcut appid.
    """
    key = (exe_path + name).encode("utf-8")
    crc = binascii.crc32(key) & 0xFFFFFFFF
    return (crc << 32) | 0x02000000


# ── VDF binary format helpers ─────────────────────────────────────────────────
# shortcuts.vdf uses Valve's binary VDF format.

VDF_TYPE_MAP    = 0x00
VDF_TYPE_STRING = 0x01
VDF_TYPE_INT32  = 0x02
VDF_TYPE_END    = 0x08


def _read_shortcuts_vdf(path: str) -> list:
    """
    Parse Steam's binary shortcuts.vdf file.
    Returns a list of shortcut dicts preserving order.
    """
    if not os.path.exists(path):
        return []

    with open(path, "rb") as f:
        data = f.read()

    if len(data) < 2:
        return []

    shortcuts = []
    pos = 0

    def read_string():
        nonlocal pos
        end = data.index(b'\x00', pos)
        s = data[pos:end].decode("utf-8", errors="replace")
        pos = end + 1
        return s

    def read_int32():
        nonlocal pos
        val = struct.unpack("<I", data[pos:pos+4])[0]
        pos += 4
        return val

    def parse_entry():
        nonlocal pos
        result = {}
        while pos < len(data):
            if pos >= len(data):
                break
            type_byte = data[pos]
            pos += 1

            if type_byte == VDF_TYPE_END:
                break
            elif type_byte == VDF_TYPE_MAP:
                key = read_string()
                result[key] = parse_entry()
            elif type_byte == VDF_TYPE_STRING:
                key = read_string()
                result[key] = read_string()
            elif type_byte == VDF_TYPE_INT32:
                key = read_string()
                result[key] = read_int32()
            else:
                break

        return result

    # Root structure: \x00 "shortcuts" \x00 { entries... } \x08
    if data[pos:pos+1] == bytes([VDF_TYPE_MAP]):
        pos += 1
        root_key = read_string()  # "shortcuts"
        
        # Parse numbered entries
        while pos < len(data):
            if pos >= len(data):
                break
            type_byte = data[pos]
            
            if type_byte == VDF_TYPE_END:
                break
            elif type_byte == VDF_TYPE_MAP:
                pos += 1
                entry_key = read_string()  # "0", "1", etc.
                entry = parse_entry()
                entry["_index"] = entry_key
                shortcuts.append(entry)
            else:
                break

    return shortcuts


def _write_shortcuts_vdf(path: str, shortcuts: list):
    """
    Write shortcuts list back to binary VDF format.
    """
    def write_string(s: str) -> bytes:
        return s.encode("utf-8") + b'\x00'

    def write_int32(v: int) -> bytes:
        return struct.pack("<I", v & 0xFFFFFFFF)

    def write_entry(entry: dict) -> bytes:
        result = b''
        for key, value in entry.items():
            if key == "_index":
                continue
            if isinstance(value, dict):
                result += bytes([VDF_TYPE_MAP])
                result += write_string(key)
                result += write_entry(value)
                result += bytes([VDF_TYPE_END])
            elif isinstance(value, int):
                result += bytes([VDF_TYPE_INT32])
                result += write_string(key)
                result += write_int32(value)
            else:
                result += bytes([VDF_TYPE_STRING])
                result += write_string(key)
                result += write_string(str(value))
        return result

    data = bytes([VDF_TYPE_MAP])
    data += write_string("shortcuts")

    for i, entry in enumerate(shortcuts):
        data += bytes([VDF_TYPE_MAP])
        data += write_string(str(i))
        data += write_entry(entry)
        data += bytes([VDF_TYPE_END])

    data += bytes([VDF_TYPE_END])
    data += bytes([VDF_TYPE_END])

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


# ── Download helper ───────────────────────────────────────────────────────────

def _download(url: str, dest: str, on_progress=None) -> bool:
    """Download a file from URL to dest path. Returns True on success."""
    try:
        req = urllib.request.Request(url, headers=_BROWSER_UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            with open(dest, "wb") as f:
                f.write(r.read())
        return True
    except Exception as e:
        if on_progress:
            on_progress(f"  ⚠ Download failed: {e}")
        return False


# ── Artwork setup ─────────────────────────────────────────────────────────────

def _setup_artwork(uid: str, exe_path: str, shortcut_def: dict, on_progress=None):
    """
    Download and save artwork for a non-Steam shortcut.
    
    Steam artwork filenames for non-Steam shortcuts:
      - Grid (vertical):  <appid>p.ext
      - Grid (horizontal/wide): <appid>.ext  
      - Hero:             <appid>_hero.ext
      - Logo:             <appid>_logo.ext
      - Icon:             <appid>_icon.ext
    
    The appid for artwork is calculated from exe+name.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")
    os.makedirs(grid_dir, exist_ok=True)

    name = shortcut_def["name"]
    
    # Calculate the artwork appid
    # Steam uses a specific formula for non-Steam shortcut artwork IDs
    key = (exe_path + name).encode("utf-8")
    crc = binascii.crc32(key) & 0xFFFFFFFF
    appid = (crc | 0x80000000) & 0xFFFFFFFF

    # Download each artwork type
    artwork_map = [
        ("icon_url",  f"{appid}_icon.{shortcut_def['icon_ext']}",  "icon"),
        ("grid_url",  f"{appid}p.{shortcut_def['grid_ext']}",      "grid"),
        ("wide_url",  f"{appid}.{shortcut_def['wide_ext']}",       "wide"),
        ("hero_url",  f"{appid}_hero.{shortcut_def['hero_ext']}",  "hero"),
        ("logo_url",  f"{appid}_logo.{shortcut_def['logo_ext']}",  "logo"),
    ]

    for url_key, filename, label in artwork_map:
        url = shortcut_def.get(url_key)
        if not url:
            continue
        dest = os.path.join(grid_dir, filename)
        if os.path.exists(dest):
            prog(f"  ✓ {label} (cached)")
            continue
        if _download(url, dest):
            prog(f"  ✓ {label}")
        else:
            prog(f"  ⚠ {label} failed")


# ── Controller template assignment ────────────────────────────────────────────

def _get_template_filename(template_type: str, gyro_mode: str) -> str:
    """
    Return the controller template filename based on type and gyro mode.
    
    template_type: "standard" or "other"
    gyro_mode: "hold" or "toggle"
    """
    if template_type == "other":
        return f"controller_neptune_deckops_other_{gyro_mode}.vdf"
    else:
        return f"controller_neptune_deckops_{gyro_mode}.vdf"


def _assign_controller_config(uid: str, exe_path: str, shortcut_def: dict,
                               gyro_mode: str, on_progress=None):
    """
    Assign controller template for a non-Steam shortcut.
    
    Writes to:
      - Steam Controller Configs/<uid>/config/<appid>/controller_neptune.vdf
      - Patches configset_controller_neptune.vdf with the shortcut appid
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    name = shortcut_def["name"]
    template_type = shortcut_def["template_type"]
    template_filename = _get_template_filename(template_type, gyro_mode)

    # Source template
    src_template = os.path.join(ASSETS_DIR, template_filename)
    if not os.path.exists(src_template):
        prog(f"  ⚠ Template not found: {template_filename}")
        return

    # Calculate shortcut appid (same as artwork appid)
    key = (exe_path + name).encode("utf-8")
    crc = binascii.crc32(key) & 0xFFFFFFFF
    appid = str((crc | 0x80000000) & 0xFFFFFFFF)

    # Path 1: Steam Controller Configs/<uid>/config/<appid>/
    steam_cfg_root = os.path.join(
        STEAM_ROOT, "steamapps", "common",
        "Steam Controller Configs", uid, "config"
    )
    cfg_dir = os.path.join(steam_cfg_root, appid)
    os.makedirs(cfg_dir, exist_ok=True)
    shutil.copy2(src_template, os.path.join(cfg_dir, "controller_neptune.vdf"))

    # Path 2: Patch configset_controller_neptune.vdf
    configset_path = os.path.join(steam_cfg_root, "configset_controller_neptune.vdf")
    _patch_configset(configset_path, appid, template_filename)

    prog(f"  ✓ Controller: {template_filename}")


def _patch_configset(configset_path: str, key: str, template_name: str):
    """
    Patch configset_controller_neptune.vdf to set our template as default.
    """
    entry = f'\t"{key}"\n\t{{\n\t\t"template"\t\t"{template_name}"\n\t}}\n'

    if not os.path.exists(configset_path):
        os.makedirs(os.path.dirname(configset_path), exist_ok=True)
        with open(configset_path, "w", encoding="utf-8") as f:
            f.write('"controller_config"\n{\n' + entry + '}\n')
        return

    with open(configset_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # Replace existing key block if present
    pattern = rf'(\t"{re.escape(key)}"\n\t\{{[^\}}]*\}}\n?)'
    if re.search(pattern, content, re.MULTILINE):
        content = re.sub(pattern, entry, content, flags=re.MULTILINE)
    else:
        # Insert before closing brace
        content = content.rstrip()
        if content.endswith("}"):
            content = content[:-1].rstrip() + "\n" + entry + "}\n"

    with open(configset_path, "w", encoding="utf-8") as f:
        f.write(content)


# ── Shortcut creation ─────────────────────────────────────────────────────────

def _shortcut_exists(shortcuts: list, exe_path: str, name: str) -> bool:
    """Check if a shortcut with this exe and name already exists."""
    for entry in shortcuts:
        if entry.get("exe") == exe_path and entry.get("AppName") == name:
            return True
        # Also check quoted exe path
        if entry.get("exe") == f'"{exe_path}"' and entry.get("AppName") == name:
            return True
    return False


def _create_shortcut_entry(exe_path: str, start_dir: str, name: str,
                           compatdata_path: str, icon_path: str = "") -> dict:
    """
    Create a shortcut entry dict for shortcuts.vdf.
    """
    # Launch options to use the correct compatdata prefix
    launch_options = f'STEAM_COMPAT_DATA_PATH="{compatdata_path}" %command%'

    return {
        "AppName": name,
        "exe": f'"{exe_path}"',
        "StartDir": f'"{start_dir}"',
        "icon": icon_path,
        "ShortcutPath": "",
        "LaunchOptions": launch_options,
        "IsHidden": 0,
        "AllowDesktopConfig": 1,  # Enables Steam Input
        "AllowOverlay": 1,
        "OpenVR": 0,
        "Devkit": 0,
        "DevkitGameID": "",
        "DevkitOverrideAppID": 0,
        "LastPlayTime": 0,
        "FlatpakAppID": "",
        "tags": {},
    }


# ── Public API ────────────────────────────────────────────────────────────────

def create_shortcuts(installed_games: dict, selected_keys: list,
                     gyro_mode: str, on_progress=None):
    """
    Create non-Steam shortcuts for CoD4 MP and WaW MP if they were selected
    and installed.
    
    installed_games — dict from detect_games.find_installed_games()
    selected_keys   — list of game keys that were selected for install
    gyro_mode       — "hold" or "toggle"
    on_progress     — optional callback(msg: str)
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    # Filter to only the shortcuts we handle, and only if they were selected
    to_create = []
    for key, shortcut_def in SHORTCUTS.items():
        if key not in selected_keys:
            continue
        if key not in installed_games:
            continue
        game = installed_games[key]
        to_create.append((key, shortcut_def, game))

    if not to_create:
        prog("No shortcuts to create.")
        return

    uids = _find_all_steam_uids()
    if not uids:
        prog("⚠ No Steam user accounts found — shortcuts skipped.")
        return

    for uid in uids:
        prog(f"Creating shortcuts for Steam user {uid}...")
        
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        shortcuts = _read_shortcuts_vdf(shortcuts_path)

        for key, shortcut_def, game in to_create:
            name = shortcut_def["name"]
            install_dir = game["install_dir"]
            exe_path = os.path.join(install_dir, shortcut_def["exe_name"])
            appid = shortcut_def["game_appid"]
            compatdata_path = os.path.join(COMPAT_ROOT, appid)

            prog(f"  → {name}")

            # Check if shortcut already exists
            exists = _shortcut_exists(shortcuts, exe_path, name)

            if exists:
                prog(f"    ✓ Shortcut exists")
            else:
                # Calculate icon path (will be downloaded to grid folder)
                grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")
                crc_key = (exe_path + name).encode("utf-8")
                crc = binascii.crc32(crc_key) & 0xFFFFFFFF
                art_appid = (crc | 0x80000000) & 0xFFFFFFFF
                icon_path = os.path.join(grid_dir, f"{art_appid}_icon.{shortcut_def['icon_ext']}")

                # Create shortcut entry
                entry = _create_shortcut_entry(
                    exe_path, install_dir, name, compatdata_path, icon_path
                )
                shortcuts.append(entry)
                prog(f"    ✓ Shortcut created")

            # Download artwork
            _setup_artwork(uid, exe_path, shortcut_def, on_progress=prog)

            # Assign controller config
            _assign_controller_config(uid, exe_path, shortcut_def, gyro_mode,
                                       on_progress=prog)

        # Write updated shortcuts.vdf
        _write_shortcuts_vdf(shortcuts_path, shortcuts)
        prog(f"  ✓ shortcuts.vdf saved")

    prog("✓ Non-Steam shortcuts created.")


def remove_shortcuts(on_progress=None):
    """
    Remove DeckOps-created shortcuts from shortcuts.vdf.
    Used during uninstall.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    uids = _find_all_steam_uids()
    
    for uid in uids:
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        shortcuts = _read_shortcuts_vdf(shortcuts_path)
        
        # Filter out our shortcuts
        original_count = len(shortcuts)
        shortcuts = [
            s for s in shortcuts
            if s.get("AppName") not in [d["name"] for d in SHORTCUTS.values()]
        ]
        
        if len(shortcuts) < original_count:
            _write_shortcuts_vdf(shortcuts_path, shortcuts)
            prog(f"  ✓ Removed shortcuts for user {uid}")


# ── CLI for testing ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    from detect_games import find_steam_root, parse_library_folders, find_installed_games
    
    print("Finding installed games...")
    steam_root = find_steam_root()
    if not steam_root:
        print("Steam not found.")
        sys.exit(1)
    
    libs = parse_library_folders(steam_root)
    installed = find_installed_games(libs)
    
    print(f"Found {len(installed)} games")
    for key in SHORTCUTS:
        if key in installed:
            print(f"  ✓ {key}: {installed[key]['install_dir']}")
        else:
            print(f"  ✗ {key}: not installed")
    
    # Test with both keys selected and "hold" mode
    print("\nCreating shortcuts (test mode)...")
    create_shortcuts(
        installed_games=installed,
        selected_keys=list(SHORTCUTS.keys()),
        gyro_mode="hold",
        on_progress=lambda msg: print(msg)
    )