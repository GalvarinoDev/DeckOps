"""
save_backup.py — DeckOps save file backup and restore

Backs up player save data (configs, stats, custom classes, demos)
before uninstall and restores them after reinstall.

Backup location: ~/.local/share/deckops/save_backup/<group>/
This directory is outside the DeckOps install tree and survives uninstall.

Two public functions:

    backup_saves(steam_root, on_progress)
        Scan deckops.json for installed games, copy save dirs to backup.
        Called by the uninstaller before deletion.

    restore_saves(steam_root, installed_games, on_progress)
        If backups exist, copy them back to the correct locations.
        Called at the end of the install flow after game setup completes.
"""

import json
import os
import shutil
from datetime import datetime

from identity import CONFIG_PATH
from log import get_logger

_log = get_logger(__name__)


# ── Paths ─────────────────────────────────────────────────────────────────────

BACKUP_ROOT = os.path.expanduser("~/.local/share/deckops/save_backup")
STEAM_ROOT_DEFAULT = os.path.expanduser("~/.local/share/Steam")
HEROIC_PREFIX = os.path.expanduser("~/Games/Heroic/Prefixes/default")


# ── Save location map ────────────────────────────────────────────────────────
#
# Each group maps to one backup. Sibling keys (cod4mp/cod4sp) that share
# the same save directory are grouped together — only backed up once.
#
# Format: {
#   "group_name": {
#       "keys":        [list of game keys that share this save location],
#       "type":        "install_dir" | "plutonium_prefix",
#       "subdir":      relative path inside install_dir or prefix,
#       "appids":      [appids to search for prefix path] (prefix type only),
#       "plut_store":  Plutonium storage subdir (prefix type only),
#   }
# }

SAVE_GROUPS = {
    "cod4": {
        "keys": ["cod4mp", "cod4sp"],
        "type": "install_dir",
        "subdir": "players",
    },
    "mw2": {
        "keys": ["iw4mp", "iw4sp"],
        "type": "install_dir",
        "subdir": "players",
    },
    "mw3sp": {
        "keys": ["iw5sp"],
        "type": "install_dir",
        "subdir": "players2",
    },
    "ghosts": {
        "keys": ["iw6sp", "iw6mp"],
        "type": "install_dir",
        "subdir": "players2",
    },
    "aw": {
        "keys": ["s1sp", "s1mp"],
        "type": "install_dir",
        "subdir": "players2",
    },
    "bo3": {
        "keys": ["t7"],
        "type": "install_dir",
        "subdir": "players",
    },
    "t7x": {
        "keys": ["t7x"],
        "type": "t7x_sibling",
        "subdir": "players",
    },
    "t4": {
        "keys": ["t4sp", "t4mp"],
        "type": "plutonium_prefix",
        "appids": ["10090"],
        "plut_store": "t4",
    },
    "t5": {
        "keys": ["t5sp", "t5mp"],
        "type": "plutonium_prefix",
        "appids": ["42700", "42710"],
        "plut_store": "t5",
    },
    "t6": {
        "keys": ["t6mp", "t6zm"],
        "type": "plutonium_prefix",
        "appids": ["202990", "212910"],
        "plut_store": "t6",
    },
    "iw5": {
        "keys": ["iw5mp"],
        "type": "plutonium_prefix",
        "appids": ["42690"],
        "plut_store": "iw5",
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    """Load deckops.json, return empty dict on failure."""
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, OSError):
        return {}


def _find_all_compatdata_dirs(steam_root: str) -> list:
    """Return all compatdata directories across all Steam library folders."""
    dirs = []
    main = os.path.join(steam_root, "steamapps", "compatdata")
    if os.path.isdir(main):
        dirs.append(main)

    lf_vdf = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    if os.path.isfile(lf_vdf):
        try:
            import re
            with open(lf_vdf, "r") as f:
                content = f.read()
            for match in re.finditer(r'"path"\s+"([^"]+)"', content):
                cd = os.path.join(match.group(1), "steamapps", "compatdata")
                if os.path.isdir(cd) and cd not in dirs:
                    dirs.append(cd)
        except OSError:
            pass

    # SD card brute-force
    import glob
    for pattern in ["/run/media/deck/*/steamapps/compatdata",
                    "/run/media/deck/*/SteamLibrary/steamapps/compatdata"]:
        for d in glob.glob(pattern):
            if os.path.isdir(d) and d not in dirs:
                dirs.append(d)

    return dirs


def _find_plutonium_storage(steam_root: str, appids: list, plut_store: str) -> str | None:
    """Find the Plutonium storage directory for a game across all prefixes.

    Searches Steam compatdata prefixes and the Heroic shared prefix.
    Returns the first existing path, or None.
    """
    compat_dirs = _find_all_compatdata_dirs(steam_root)

    # Also search Heroic shared prefix (LCD)
    if os.path.isdir(HEROIC_PREFIX):
        compat_dirs.append(HEROIC_PREFIX)

    for compat_root in compat_dirs:
        for appid in appids:
            storage = os.path.join(
                compat_root, appid,
                "pfx", "drive_c", "users", "steamuser",
                "AppData", "Local", "Plutonium", "storage", plut_store,
            )
            if os.path.isdir(storage):
                return storage

    # Also check Heroic directly (it's not appid-based)
    heroic_storage = os.path.join(
        HEROIC_PREFIX,
        "pfx", "drive_c", "users", "steamuser",
        "AppData", "Local", "Plutonium", "storage", plut_store,
    )
    if os.path.isdir(heroic_storage):
        return heroic_storage

    return None


def _find_install_dir(keys: list, setup_games: dict, installed_games: dict = None) -> str | None:
    """Find the install directory for any of the given keys."""
    # First try installed_games (passed during install flow)
    if installed_games:
        for key in keys:
            if key in installed_games:
                d = installed_games[key].get("install_dir")
                if d and os.path.isdir(d):
                    return d

    # Fall back to setup_games from config (used during uninstall)
    for key in keys:
        entry = setup_games.get(key, {})
        d = entry.get("install_dir")
        if d and os.path.isdir(d):
            return d

    return None


def _find_t7x_players(keys: list, setup_games: dict, installed_games: dict = None) -> str | None:
    """Find the T7X sibling players directory."""
    # T7X lives in DeckOps-T7X/ next to the BO3 install dir.
    # We need to find BO3's install dir first.
    bo3_keys = ["t7", "t7x"]
    install_dir = _find_install_dir(bo3_keys, setup_games, installed_games)
    if not install_dir:
        return None

    sibling = os.path.join(os.path.dirname(install_dir), "DeckOps-T7X", "players")
    if os.path.isdir(sibling):
        return sibling
    return None


def _copytree_safe(src: str, dst: str, group: str, prog):
    """Copy a directory tree, creating dst if needed."""
    if not os.path.isdir(src):
        return False
    try:
        os.makedirs(dst, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return True
    except (OSError, shutil.Error) as ex:
        _log.warning("save backup copy failed for %s: %s", group, ex)
        prog(f"  ⚠ {group}: copy failed: {ex}")
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def backup_saves(steam_root: str = None, on_progress=None,
                 installed_games: dict = None) -> dict:
    """Back up save data for all installed games.

    steam_root       — Steam root path (defaults to ~/.local/share/Steam)
    on_progress      — callback(message: str)
    installed_games  — optional dict of key -> game info (from install flow)

    Returns a dict of {group_name: backup_path} for groups that were backed up.
    """
    if steam_root is None:
        steam_root = STEAM_ROOT_DEFAULT
    if on_progress is None:
        on_progress = lambda msg: None

    config = _load_config()
    setup_games = config.get("setup_games", {})

    if not setup_games and not installed_games:
        on_progress("No installed games found — nothing to back up.")
        return {}

    backed_up = {}
    on_progress("Backing up save data...")

    for group_name, group in SAVE_GROUPS.items():
        keys = group["keys"]

        # Check if any key in this group is installed
        has_key = any(k in setup_games for k in keys)
        if installed_games:
            has_key = has_key or any(k in installed_games for k in keys)
        if not has_key:
            continue

        src = None

        if group["type"] == "install_dir":
            install_dir = _find_install_dir(keys, setup_games, installed_games)
            if install_dir:
                src = os.path.join(install_dir, group["subdir"])

        elif group["type"] == "t7x_sibling":
            src = _find_t7x_players(keys, setup_games, installed_games)

        elif group["type"] == "plutonium_prefix":
            src = _find_plutonium_storage(
                steam_root,
                group["appids"],
                group["plut_store"],
            )

        if not src or not os.path.isdir(src):
            _log.debug("save backup: %s — source not found", group_name)
            continue

        # Check if there's actually anything to back up
        try:
            has_files = any(True for _ in os.scandir(src))
        except OSError:
            continue
        if not has_files:
            continue

        dst = os.path.join(BACKUP_ROOT, group_name)
        # Clear old backup for this group
        if os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)

        if _copytree_safe(src, dst, group_name, on_progress):
            backed_up[group_name] = dst
            on_progress(f"  ✓ {group_name}: backed up")
            _log.info("save backup: %s -> %s", src, dst)

    # Write metadata
    if backed_up:
        meta = {
            "backed_up_at": datetime.now().isoformat(),
            "groups": list(backed_up.keys()),
        }
        try:
            meta_path = os.path.join(BACKUP_ROOT, "backup_info.json")
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)
        except OSError:
            pass
        on_progress(f"Save backup complete — {len(backed_up)} group(s) saved.")
    else:
        on_progress("No save data found to back up.")

    return backed_up


def restore_saves(steam_root: str = None, installed_games: dict = None,
                  on_progress=None) -> dict:
    """Restore save data from backups into the correct game locations.

    steam_root       — Steam root path
    installed_games  — dict of key -> game info (install_dir, etc.)
    on_progress      — callback(message: str)

    Returns a dict of {group_name: dest_path} for groups that were restored.
    """
    if steam_root is None:
        steam_root = STEAM_ROOT_DEFAULT
    if on_progress is None:
        on_progress = lambda msg: None

    if not os.path.isdir(BACKUP_ROOT):
        return {}

    # Check metadata
    meta_path = os.path.join(BACKUP_ROOT, "backup_info.json")
    if not os.path.isfile(meta_path):
        return {}

    try:
        with open(meta_path, "r") as f:
            meta = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

    groups_to_restore = meta.get("groups", [])
    if not groups_to_restore:
        return {}

    config = _load_config()
    setup_games = config.get("setup_games", {})

    restored = {}
    on_progress("Checking for save data backups...")

    for group_name in groups_to_restore:
        if group_name not in SAVE_GROUPS:
            continue

        group = SAVE_GROUPS[group_name]
        keys = group["keys"]
        backup_dir = os.path.join(BACKUP_ROOT, group_name)

        if not os.path.isdir(backup_dir):
            continue

        # Check if backup has content
        try:
            has_files = any(True for _ in os.scandir(backup_dir))
        except OSError:
            continue
        if not has_files:
            continue

        dst = None

        if group["type"] == "install_dir":
            install_dir = _find_install_dir(keys, setup_games, installed_games)
            if install_dir:
                dst = os.path.join(install_dir, group["subdir"])

        elif group["type"] == "t7x_sibling":
            # For T7X, we need the BO3 install dir to find the sibling
            bo3_dir = _find_install_dir(["t7", "t7x"], setup_games, installed_games)
            if bo3_dir:
                dst = os.path.join(os.path.dirname(bo3_dir), "DeckOps-T7X", "players")

        elif group["type"] == "plutonium_prefix":
            # Restore to the first prefix that has a Plutonium dir
            dst = _find_plutonium_storage(
                steam_root,
                group["appids"],
                group["plut_store"],
            )
            # If prefix doesn't exist yet (fresh install), build the path
            # from the first appid — the installer will create it
            if dst is None:
                main_compat = os.path.join(
                    steam_root, "steamapps", "compatdata",
                    group["appids"][0],
                    "pfx", "drive_c", "users", "steamuser",
                    "AppData", "Local", "Plutonium", "storage",
                    group["plut_store"],
                )
                dst = main_compat

        if not dst:
            _log.debug("save restore: %s — dest not found, skipping", group_name)
            continue

        if _copytree_safe(backup_dir, dst, group_name, on_progress):
            restored[group_name] = dst
            on_progress(f"  ✓ {group_name}: saves restored")
            _log.info("save restore: %s -> %s", backup_dir, dst)

    if restored:
        on_progress(f"Save restore complete — {len(restored)} group(s) restored.")
    else:
        on_progress("No matching save backups found.")

    return restored


def has_backups() -> bool:
    """Return True if any save backups exist."""
    meta_path = os.path.join(BACKUP_ROOT, "backup_info.json")
    return os.path.isfile(meta_path)


def clear_backups(on_progress=None):
    """Remove all save backups."""
    if on_progress is None:
        on_progress = lambda msg: None
    if os.path.isdir(BACKUP_ROOT):
        shutil.rmtree(BACKUP_ROOT, ignore_errors=True)
        on_progress("Save backups cleared.")
        _log.info("save backups cleared")


# ── CLI for manual use / uninstaller ──────────────────────────────────────────

if __name__ == "__main__":
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "backup"
    steam = sys.argv[2] if len(sys.argv) > 2 else STEAM_ROOT_DEFAULT

    def _print(msg):
        print(msg)

    if action == "backup":
        result = backup_saves(steam_root=steam, on_progress=_print)
        if result:
            print(f"\nBacked up {len(result)} group(s) to {BACKUP_ROOT}")
        else:
            print("\nNo saves to back up.")
    elif action == "restore":
        result = restore_saves(steam_root=steam, on_progress=_print)
        if result:
            print(f"\nRestored {len(result)} group(s)")
    elif action == "clear":
        clear_backups(on_progress=_print)
    else:
        print(f"Usage: {sys.argv[0]} [backup|restore|clear] [steam_root]")
