"""
shortcut.py — DeckOps non-Steam shortcut creator

Creates non-Steam game shortcuts in Steam for CoD4 Multiplayer (CoD4x) and
World at War Multiplayer. These shortcuts point to the original game exes
in the Steam library and use the original compatdata prefixes.

Shortcuts include:
  - Proper artwork (icon, grid, wide, hero, logo) from SteamGridDB
  - Correct compatdata prefix via launch options
  - Controller template assignment based on gyro mode
  - Steam Input enabled (AllowDesktopConfig)

Called at the end of InstallScreen._run() after client installation completes.
Must be called while Steam is closed.

Requires: pip install vdf
"""

import binascii
import os
import re
import shutil
import time
import urllib.request

import vdf

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
    This is what Steam uses for artwork filenames and controller configs.
    """
    key = (exe_path + name).encode("utf-8")
    crc = binascii.crc32(key) & 0xFFFFFFFF
    return (crc | 0x80000000) & 0xFFFFFFFF


def _to_signed32(n):
    """Convert unsigned int32 appid to signed int32 for vdf binary format."""
    return n if n <= 2147483647 else n - 2**32


def _download(url: str, dest: str) -> bool:
    """Download a file from URL to dest path. Returns True on success."""
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        req = urllib.request.Request(url, headers=_BROWSER_UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            with open(dest, "wb") as f:
                f.write(r.read())
        return True
    except Exception:
        return False


# ── VDF read/write using vdf library ──────────────────────────────────────────

def _read_shortcuts(path: str) -> dict:
    """Return the shortcuts dict from shortcuts.vdf, or empty structure."""
    if not os.path.exists(path):
        return {"shortcuts": {}}
    try:
        with open(path, "rb") as f:
            return vdf.binary_load(f)
    except Exception:
        return {"shortcuts": {}}


def _write_shortcuts(path: str, data: dict):
    """Write shortcuts dict to binary vdf format."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        vdf.binary_dump(data, f)


# ── Artwork download ──────────────────────────────────────────────────────────

def _download_artwork(grid_dir: str, appid: int, shortcut_def: dict, prog):
    """Download all artwork for a shortcut to the grid directory."""
    appid_str = str(appid)
    
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
            continue  # Already have it
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


# ── Public API ────────────────────────────────────────────────────────────────

def create_shortcuts(installed_games: dict, selected_keys: list,
                     gyro_mode: str, on_progress=None):
    """
    Create non-Steam shortcuts for CoD4 MP and WaW MP if they were selected
    and installed. Creates shortcuts for ALL Steam user accounts.
    
    installed_games — dict from detect_games.find_installed_games()
    selected_keys   — list of game keys that were selected for install
    gyro_mode       — "hold" or "toggle"
    on_progress     — optional callback(msg: str)
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)
    
    # Filter to only the shortcuts we handle
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
    
    # Process each Steam user account
    for uid in uids:
        prog(f"Creating shortcuts for user {uid}...")
        
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")
        os.makedirs(grid_dir, exist_ok=True)
        
        data = _read_shortcuts(shortcuts_path)
        sc_dict = data.get("shortcuts", {})
        
        # Find next available index
        existing_indices = [int(k) for k in sc_dict.keys() if str(k).isdigit()]
        next_idx = max(existing_indices, default=-1) + 1
        
        for key, shortcut_def, install_dir in to_create:
            name = shortcut_def["name"]
            exe_path = os.path.join(install_dir, shortcut_def["exe_name"])
            game_appid = shortcut_def["game_appid"]
            compatdata_path = os.path.join(COMPAT_ROOT, game_appid)
            
            # Calculate the shortcut appid (used for artwork filenames)
            shortcut_appid = _calc_shortcut_appid(exe_path, name)
            
            prog(f"  → {name}")
            prog(f"    appid: {shortcut_appid}")
            
            # Check if shortcut already exists by AppName
            already_exists = any(
                str(v.get("AppName", v.get("appname", ""))) == name
                for v in sc_dict.values()
                if isinstance(v, dict)
            )
            
            if already_exists:
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
                
                sc_dict[str(next_idx)] = entry
                next_idx += 1
                prog(f"    ✓ Shortcut created")
            
            # Download artwork (always, for this UID)
            _download_artwork(grid_dir, shortcut_appid, shortcut_def, prog)
            
            # Assign controller config
            _assign_controller_config(uid, shortcut_appid, shortcut_def, gyro_mode, prog)
        
        # Write updated shortcuts.vdf
        data["shortcuts"] = sc_dict
        try:
            _write_shortcuts(shortcuts_path, data)
            prog(f"  ✓ shortcuts.vdf saved")
        except Exception as e:
            prog(f"  ⚠ Failed to write shortcuts.vdf: {e}")
    
    prog("✓ Non-Steam shortcuts created.")


def remove_shortcuts(on_progress=None):
    """Remove DeckOps-created shortcuts from shortcuts.vdf for all users."""
    def prog(msg):
        if on_progress:
            on_progress(msg)
    
    shortcut_names = {s["name"] for s in SHORTCUTS.values()}
    
    for uid in _find_all_steam_uids():
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        data = _read_shortcuts(shortcuts_path)
        sc_dict = data.get("shortcuts", {})
        
        original_count = len(sc_dict)
        sc_dict = {
            k: v for k, v in sc_dict.items()
            if not isinstance(v, dict) or v.get("AppName", v.get("appname", "")) not in shortcut_names
        }
        
        if len(sc_dict) < original_count:
            data["shortcuts"] = sc_dict
            _write_shortcuts(shortcuts_path, data)
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
