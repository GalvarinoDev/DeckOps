"""
shortcut.py — DeckOps non-Steam shortcut creator

Creates non-Steam game shortcuts in Steam for CoD4 Multiplayer (CoD4x) and
World at War Multiplayer. These shortcuts point to the original game exes
in the Steam library and use the original compatdata prefixes.

Shortcuts include:
  - Proper artwork (icon, grid, wide, hero, logo) from SteamGridDB
  - Correct compatdata prefix via launch options
  - Controller template assignment based on gyro mode
  - GE-Proton compat tool assignment
  - Steam Input enabled (AllowDesktopConfig)

Called at the end of InstallScreen._run() after client installation completes.
Must be called while Steam is closed.
"""

import binascii
import os
import re
import shutil
import struct
import time
import urllib.request

# ── Paths ─────────────────────────────────────────────────────────────────────

STEAM_ROOT     = os.path.expanduser("~/.local/share/Steam")
USERDATA_DIR   = os.path.join(STEAM_ROOT, "userdata")
COMPAT_ROOT    = os.path.join(STEAM_ROOT, "steamapps", "compatdata")
STEAM_CONFIG   = os.path.join(STEAM_ROOT, "config", "config.vdf")

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


# ── Shortcut definitions ──────────────────────────────────────────────────────

SHORTCUTS = {
    "cod4mp": {
        "name":            "Call of Duty 4: Modern Warfare - Multiplayer",
        "exe_name":        "iw3mp.exe",
        "game_appid":      "7940",
        "template_type":   "other",
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
        "template_type":   "standard",
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_all_steam_uids():
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


def _calc_shortcut_appid(exe_path: str, name: str) -> int:
    """
    Calculate the Steam shortcut appid from exe path and name.
    This matches Steam's algorithm exactly.
    """
    key = (exe_path + name).encode("utf-8")
    crc = binascii.crc32(key) & 0xFFFFFFFF
    return (crc | 0x80000000) & 0xFFFFFFFF


def _to_signed32(n):
    """Convert unsigned int32 appid to signed int32 for vdf binary format."""
    return n if n <= 2147483647 else n - 2**32


def _download(url: str, dest: str) -> bool:
    """Download a file from URL to dest path. Retries up to 3 times. Returns True on success."""
    import time
    for attempt in range(3):
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            req = urllib.request.Request(url, headers=_BROWSER_UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                with open(dest, "wb") as f:
                    f.write(r.read())
            return True
        except Exception:
            if attempt == 2:
                return False
            time.sleep(2 ** attempt)
    return False


# ── Binary VDF helpers ────────────────────────────────────────────────────────

def _vdf_string(key: str, val: str) -> bytes:
    """Encode a string field for binary VDF."""
    return b'\x01' + key.encode('utf-8') + b'\x00' + val.encode('utf-8') + b'\x00'


def _vdf_int(key: str, val: int) -> bytes:
    """Encode an int32 field for binary VDF."""
    return b'\x02' + key.encode('utf-8') + b'\x00' + struct.pack('<i', val)


def _make_shortcut_entry(index: int, entry: dict) -> bytes:
    """Build a single shortcut entry in binary VDF format."""
    data = b'\x00' + str(index).encode('utf-8') + b'\x00'
    
    data += _vdf_int('appid', entry.get('appid', 0))
    data += _vdf_string('AppName', entry.get('AppName', ''))
    data += _vdf_string('Exe', entry.get('Exe', ''))
    data += _vdf_string('StartDir', entry.get('StartDir', ''))
    data += _vdf_string('icon', entry.get('icon', ''))
    data += _vdf_string('ShortcutPath', entry.get('ShortcutPath', ''))
    data += _vdf_string('LaunchOptions', entry.get('LaunchOptions', ''))
    data += _vdf_int('IsHidden', entry.get('IsHidden', 0))
    data += _vdf_int('AllowDesktopConfig', entry.get('AllowDesktopConfig', 1))
    data += _vdf_int('AllowOverlay', entry.get('AllowOverlay', 1))
    data += _vdf_int('OpenVR', entry.get('OpenVR', 0))
    data += _vdf_int('Devkit', entry.get('Devkit', 0))
    data += _vdf_string('DevkitGameID', entry.get('DevkitGameID', ''))
    data += _vdf_int('DevkitOverrideAppID', entry.get('DevkitOverrideAppID', 0))
    data += _vdf_int('LastPlayTime', entry.get('LastPlayTime', 0))
    data += _vdf_string('FlatpakAppID', entry.get('FlatpakAppID', ''))
    
    # Tags submenu
    data += b'\x00tags\x00'
    tags = entry.get('tags', {})
    for k, v in tags.items():
        data += _vdf_string(str(k), str(v))
    data += b'\x08'  # End tags
    
    data += b'\x08'  # End entry
    return data


def _read_existing_shortcuts(path: str) -> list:
    """
    Read existing shortcuts from shortcuts.vdf.
    Returns list of AppName strings.
    """
    if not os.path.exists(path):
        return []
    
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except Exception:
        return []
    
    # Extract AppName values
    existing = []
    for match in re.finditer(b'\x01[Aa]pp[Nn]ame\x00([^\x00]+)\x00', data):
        existing.append(match.group(1).decode('utf-8', errors='replace'))
    
    return existing


def _read_shortcuts_raw(path: str) -> bytes:
    """Read the raw shortcuts.vdf content, stripping header/footer."""
    if not os.path.exists(path):
        return b''
    
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except Exception:
        return b''
    
    # Strip header (b'\x00shortcuts\x00') and footer (b'\x08\x08')
    header = b'\x00shortcuts\x00'
    if data.startswith(header):
        data = data[len(header):]
    if data.endswith(b'\x08\x08'):
        data = data[:-2]
    elif data.endswith(b'\x08'):
        data = data[:-1]
    
    return data


def _get_next_index(raw_data: bytes) -> int:
    """Find the next available index from raw shortcut data."""
    if not raw_data:
        return 0
    
    # Find all index markers: \x00<digit(s)>\x00
    indices = []
    i = 0
    while i < len(raw_data):
        if raw_data[i:i+1] == b'\x00':
            end = raw_data.find(b'\x00', i + 1)
            if end != -1:
                try:
                    idx_str = raw_data[i+1:end].decode('utf-8')
                    if idx_str.isdigit():
                        indices.append(int(idx_str))
                except:
                    pass
            i = end + 1 if end != -1 else i + 1
        else:
            i += 1
    
    return max(indices, default=-1) + 1


def _write_shortcuts_vdf(path: str, existing_raw: bytes, new_entries: list):
    """Write shortcuts.vdf with existing entries preserved and new ones appended."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    data = b'\x00shortcuts\x00'
    
    if existing_raw:
        data += existing_raw
    
    for entry_bytes in new_entries:
        data += entry_bytes
    
    data += b'\x08\x08'
    
    with open(path, 'wb') as f:
        f.write(data)


# ── Artwork download ──────────────────────────────────────────────────────────

def _download_artwork(grid_dir: str, appid: int, shortcut_def: dict, prog):
    """Download all artwork for a shortcut to the grid directory."""
    appid_str = str(appid)
    os.makedirs(grid_dir, exist_ok=True)
    
    artwork_map = [
        ("icon_url",  f"{appid_str}_icon.{shortcut_def['icon_ext']}",  "icon"),
        ("grid_url",  f"{appid_str}p.{shortcut_def['grid_ext']}",      "grid"),
        ("wide_url",  f"{appid_str}.{shortcut_def['wide_ext']}",       "wide"),
        ("hero_url",  f"{appid_str}_hero.{shortcut_def['hero_ext']}",  "hero"),
        ("logo_url",  f"{appid_str}_logo.{shortcut_def['logo_ext']}",  "logo"),
    ]
    
    for url_key, filename, label in artwork_map:
        url = shortcut_def.get(url_key)
        if not url:
            continue
        dest = os.path.join(grid_dir, filename)
        if os.path.exists(dest):
            prog(f"    ✓ {label} (cached)")
            continue
        if _download(url, dest):
            prog(f"    ✓ {label}")
        else:
            prog(f"    ⚠ {label} failed")


# ── Controller template assignment ────────────────────────────────────────────

def _get_template_filename(template_type: str, gyro_mode: str) -> str:
    """Return the controller template filename based on type and gyro mode."""
    if template_type == "other":
        return f"controller_neptune_deckops_other_{gyro_mode}.vdf"
    else:
        return f"controller_neptune_deckops_{gyro_mode}.vdf"


def _assign_controller_config(uid: str, appid: int, shortcut_def: dict,
                               gyro_mode: str, prog):
    """Assign controller template for a non-Steam shortcut."""
    template_type = shortcut_def["template_type"]
    template_filename = _get_template_filename(template_type, gyro_mode)
    
    src_template = os.path.join(ASSETS_DIR, template_filename)
    if not os.path.exists(src_template):
        prog(f"    ⚠ Template not found: {template_filename}")
        return
    
    appid_str = str(appid)
    
    # Path: Steam Controller Configs/<uid>/config/<appid>/
    steam_cfg_root = os.path.join(
        STEAM_ROOT, "steamapps", "common",
        "Steam Controller Configs", uid, "config"
    )
    cfg_dir = os.path.join(steam_cfg_root, appid_str)
    os.makedirs(cfg_dir, exist_ok=True)
    shutil.copy2(src_template, os.path.join(cfg_dir, "controller_neptune.vdf"))
    
    # Patch configset_controller_neptune.vdf
    configset_path = os.path.join(steam_cfg_root, "configset_controller_neptune.vdf")
    _patch_configset(configset_path, appid_str, template_filename)
    
    prog(f"    ✓ Controller: {template_filename}")


def _patch_configset(configset_path: str, key: str, template_name: str):
    """Patch configset_controller_neptune.vdf to set our template as default."""
    entry = f'\t"{key}"\n\t{{\n\t\t"template"\t\t"{template_name}"\n\t}}\n'
    
    if not os.path.exists(configset_path):
        os.makedirs(os.path.dirname(configset_path), exist_ok=True)
        with open(configset_path, "w", encoding="utf-8") as f:
            f.write('"controller_config"\n{\n' + entry + '}\n')
        return
    
    with open(configset_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    
    pattern = rf'(\t"{re.escape(key)}"\n\t\{{[^\}}]*\}}\n?)'
    if re.search(pattern, content, re.MULTILINE):
        content = re.sub(pattern, entry, content, flags=re.MULTILINE)
    else:
        content = content.rstrip()
        if content.endswith("}"):
            content = content[:-1].rstrip() + "\n" + entry + "}\n"
    
    with open(configset_path, "w", encoding="utf-8") as f:
        f.write(content)


# ── GE-Proton compat tool assignment ──────────────────────────────────────────

def _assign_compat_tool(appid: int, prog):
    """
    Set GE-Proton compat tool for a non-Steam shortcut.
    Reads the installed GE-Proton version from DeckOps config and writes
    a CompatToolMapping entry to Steam's config.vdf.
    """
    try:
        import config as cfg
        ge_version = cfg.get_ge_proton_version()
        
        if not ge_version:
            prog(f"    ⚠ No GE-Proton version found — skipping compat tool")
            return
        
        if not os.path.exists(STEAM_CONFIG):
            prog(f"    ⚠ Steam config.vdf not found — skipping compat tool")
            return
        
        appid_str = str(appid)
        
        with open(STEAM_CONFIG, "r", encoding="utf-8") as f:
            data = f.read()
        
        entry = (
            f'\t\t\t\t"{appid_str}"\n'
            f'\t\t\t\t{{\n'
            f'\t\t\t\t\t"name"\t\t"{ge_version}"\n'
            f'\t\t\t\t\t"config"\t\t""\n'
            f'\t\t\t\t\t"Priority"\t\t"250"\n'
            f'\t\t\t\t}}\n'
        )
        
        # If appid block already exists, replace it
        pattern = rf'(\t+"{re.escape(appid_str)}"\n\t+\{{[^}}]*\}})'
        if re.search(pattern, data, re.MULTILINE):
            data = re.sub(pattern, entry.rstrip('\n'), data, flags=re.MULTILINE)
        else:
            # Insert after CompatToolMapping opening brace
            data = re.sub(
                r'("CompatToolMapping"\s*\{)',
                r'\1\n' + entry,
                data,
                count=1
            )
        
        # Create CompatToolMapping block if it doesn't exist at all
        if '"CompatToolMapping"' not in data:
            block = (
                '\t\t\t"CompatToolMapping"\n'
                '\t\t\t{\n'
                + entry +
                '\t\t\t}\n'
            )
            # Insert before closing of Software/Valve/Steam block
            data = re.sub(
                r'("Steam"\s*\{)',
                r'\1\n' + block,
                data,
                count=1
            )
        
        with open(STEAM_CONFIG, "w", encoding="utf-8") as f:
            f.write(data)
        
        prog(f"    ✓ GE-Proton: {ge_version}")
        
    except Exception as ex:
        prog(f"    ⚠ Compat tool failed: {ex}")


# ── Public API ────────────────────────────────────────────────────────────────

def create_shortcuts(installed_games: dict, selected_keys: list,
                     gyro_mode: str, on_progress=None):
    """
    Create non-Steam shortcuts for CoD4 MP and WaW MP if they were selected
    and installed. Creates shortcuts for ALL Steam user accounts.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)
    
    to_create = []
    for key, shortcut_def in SHORTCUTS.items():
        if key not in selected_keys:
            continue
        if key not in installed_games:
            continue
        game = installed_games[key]
        install_dir = game.get("install_dir") or game.get("path")
        if not install_dir:
            continue
        to_create.append((key, shortcut_def, install_dir))
    
    if not to_create:
        prog("No shortcuts to create.")
        return
    
    uids = _find_all_steam_uids()
    if not uids:
        prog("⚠ No Steam user accounts found — shortcuts skipped.")
        return
    
    # Track which shortcut appids we've already assigned compat tools for
    # (only need to do this once per shortcut, not per user)
    compat_assigned = set()
    
    for uid in uids:
        prog(f"Creating shortcuts for user {uid}...")
        
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")
        
        existing_names = _read_existing_shortcuts(shortcuts_path)
        existing_raw = _read_shortcuts_raw(shortcuts_path)
        next_idx = _get_next_index(existing_raw)
        
        new_entries = []
        
        for key, shortcut_def, install_dir in to_create:
            name = shortcut_def["name"]
            exe_path = os.path.join(install_dir, shortcut_def["exe_name"])
            game_appid = shortcut_def["game_appid"]
            compatdata_path = os.path.join(COMPAT_ROOT, game_appid)
            
            shortcut_appid = _calc_shortcut_appid(exe_path, name)
            
            prog(f"  → {name}")
            prog(f"    appid: {shortcut_appid}")
            
            if name in existing_names:
                prog(f"    ✓ Shortcut exists")
            else:
                icon_path = os.path.join(grid_dir, f"{shortcut_appid}_icon.{shortcut_def['icon_ext']}")
                
                entry = {
                    "appid":              _to_signed32(shortcut_appid),
                    "AppName":            name,
                    "Exe":                f'"{exe_path}"',
                    "StartDir":           f'"{install_dir}"',
                    "icon":               icon_path,
                    "ShortcutPath":       "",
                    "LaunchOptions":      f'STEAM_COMPAT_DATA_PATH="{compatdata_path}" %command%',
                    "IsHidden":           0,
                    "AllowDesktopConfig": 1,
                    "AllowOverlay":       1,
                    "OpenVR":             0,
                    "Devkit":             0,
                    "DevkitGameID":       "",
                    "DevkitOverrideAppID": 0,
                    "LastPlayTime":       int(time.time()),
                    "FlatpakAppID":       "",
                    "tags":               {"0": "DeckOps"},
                }
                
                entry_bytes = _make_shortcut_entry(next_idx, entry)
                new_entries.append(entry_bytes)
                next_idx += 1
                prog(f"    ✓ Shortcut created")
            
            _download_artwork(grid_dir, shortcut_appid, shortcut_def, prog)
            _assign_controller_config(uid, shortcut_appid, shortcut_def, gyro_mode, prog)
            
            # Assign GE-Proton compat tool (only once per shortcut, not per user)
            if shortcut_appid not in compat_assigned:
                _assign_compat_tool(shortcut_appid, prog)
                compat_assigned.add(shortcut_appid)
        
        if new_entries:
            try:
                _write_shortcuts_vdf(shortcuts_path, existing_raw, new_entries)
                prog(f"  ✓ shortcuts.vdf saved")
            except Exception as e:
                prog(f"  ⚠ Failed to write shortcuts.vdf: {e}")
        else:
            prog(f"  ✓ No new shortcuts needed")
    
    prog("✓ Non-Steam shortcuts created.")


def remove_shortcuts(on_progress=None):
    """Remove DeckOps-created shortcuts from shortcuts.vdf for all users."""
    def prog(msg):
        if on_progress:
            on_progress(msg)
    
    shortcut_names = {s["name"] for s in SHORTCUTS.values()}
    
    for uid in _find_all_steam_uids():
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        if not os.path.exists(shortcuts_path):
            continue
        
        try:
            with open(shortcuts_path, 'rb') as f:
                data = f.read()
        except Exception:
            continue
        
        found = False
        for name in shortcut_names:
            if name.encode('utf-8') in data:
                found = True
                break
        
        if not found:
            continue
        
        prog(f"  ⚠ Manual removal may be needed for user {uid}")


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
            print(f"  ✓ {key}: {installed[key].get('install_dir', installed[key].get('path'))}")
        else:
            print(f"  ✗ {key}: not installed")
    
    print("\nCreating shortcuts (test mode)...")
    create_shortcuts(
        installed_games=installed,
        selected_keys=list(SHORTCUTS.keys()),
        gyro_mode="hold",
        on_progress=lambda msg: print(msg)
    )
