"""
save_backup.py: DeckOps save file backup and restore

Backs up player save data (configs, stats, custom classes, demos)
before uninstall and restores them after reinstall.

Backup location: ~/.local/share/deckops/save_backup/<group>/
This folder is outside the DeckOps install tree, so it survives uninstall.

Main functions:

    backup_saves(steam_root, on_progress)
        Finds installed games in deckops.json and copies their save dirs
        to the backup. The uninstaller calls it before it deletes anything.

    restore_saves(steam_root, installed_games, on_progress)
        Copies any backups back to the right places. The Restore button
        on the management screen calls it.
"""

import json
import os
import shutil
from datetime import datetime

from identity import CONFIG_PATH
from log import get_logger

_log = get_logger(__name__)


# --- Paths

BACKUP_ROOT = os.path.expanduser("~/.local/share/deckops/save_backup")
STEAM_ROOT_DEFAULT = os.path.expanduser("~/.local/share/Steam")
HEROIC_PREFIX = os.path.expanduser("~/Games/Heroic/Prefixes/default")


# --- Save location map
#
# Each group is one backup. Sibling keys (cod4mp/cod4sp) that share a save
# directory sit in one group, so it is backed up once.
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


# --- Helpers

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

    # Also glob SD card libraries directly
    import glob
    for pattern in ["/run/media/deck/*/steamapps/compatdata",
                    "/run/media/deck/*/SteamLibrary/steamapps/compatdata"]:
        for d in glob.glob(pattern):
            if os.path.isdir(d) and d not in dirs:
                dirs.append(d)

    return dirs


# Only these parts of Plutonium storage/<game>/ are user data. Everything
# else (zone/, map .iwd files, video/, ...) is Plutonium's and comes back
# on reinstall, so backing it up would cost hundreds of MB per game.
_PLUT_USER_PARTS = ("players", "mods")


def _plut_storage(prefix: str, plut_store: str) -> str:
    return os.path.join(prefix, "pfx", "drive_c", "users", "steamuser",
                        "AppData", "Local", "Plutonium", "storage", plut_store)


def _own_prefix(steam_root: str, key: str, game: dict) -> str | None:
    """Own-copy prefix, the same one shortcut.enrich_own_games uses."""
    try:
        from shortcut import own_plut_prefix
        return own_plut_prefix(key, game)
    except (ImportError, KeyError):
        return None


def _find_plutonium_storages(steam_root: str, group: dict, setup_games: dict) -> dict:
    """Every Plutonium storage dir for a group, as {tag: path}. Tags are the
    Steam appid, "heroic", or "own_<key>". SP and MP can live in different
    prefixes (BO1/BO2 Steam appids, own copies), so all of them are saved."""
    found, seen = {}, set()

    def _add(tag, path):
        real = os.path.realpath(path)
        if os.path.isdir(path) and real not in seen:
            seen.add(real); found[tag] = path

    for compat_root in _find_all_compatdata_dirs(steam_root):
        for appid in group["appids"]:
            _add(appid, _plut_storage(os.path.join(compat_root, appid), group["plut_store"]))
    _add("heroic", _plut_storage(HEROIC_PREFIX, group["plut_store"]))

    own_keys = [k for k in group["keys"] if setup_games.get(k, {}).get("source") == "own"]
    if own_keys:
        own = _detected_games()[1]
        for k in own_keys:
            prefix = _own_prefix(steam_root, k, own[k]) if k in own else None
            if prefix:
                _add(f"own_{k}", _plut_storage(prefix, group["plut_store"]))
            # WaW MP had its own prefix before it moved into the shared one
            if k == "t4mp" and k in own:
                old = _legacy_waw_mp_prefix(steam_root, own[k])
                if old:
                    _add("own_old_t4mp", _plut_storage(old, group["plut_store"]))
    return found


def _legacy_waw_mp_prefix(steam_root: str, game: dict) -> str | None:
    try:
        from shortcut import OWN_SHORTCUTS, COMPAT_ROOT
        from steam_common import calc_shortcut_appid
    except ImportError:
        return None
    appid = calc_shortcut_appid(f'"{game["exe_path"]}"', OWN_SHORTCUTS["t4mp"]["name"])
    return os.path.join(COMPAT_ROOT, str(appid))


def _plut_restore_dst(steam_root: str, group: dict, tag: str) -> str | None:
    """Where a tagged Plutonium backup goes back to."""
    if tag == "heroic":
        return _plut_storage(HEROIC_PREFIX, group["plut_store"])
    if tag.startswith("own_"):
        # own_old_t4mp restores into the shared WaW prefix like own_t4mp
        k = tag[4:].removeprefix("old_")
        own = _detected_games()[1]
        prefix = _own_prefix(steam_root, k, own[k]) if k in own else None
        return _plut_storage(prefix, group["plut_store"]) if prefix else None
    # Steam appid: prefer an existing prefix on any library, else internal
    # (DeckOps always creates Steam prefixes on internal storage)
    for compat_root in _find_all_compatdata_dirs(steam_root):
        path = _plut_storage(os.path.join(compat_root, tag), group["plut_store"])
        if os.path.isdir(path):
            return path
    return _plut_storage(os.path.join(steam_root, "steamapps", "compatdata", tag),
                         group["plut_store"])


_DETECTED = None

def _detected_games() -> tuple:
    """(steam, own) game dicts from detect_games, scanned once per run.
    deckops.json does not store install dirs, so backup/restore outside the
    install flow (uninstaller, Restore button) has to find the games itself."""
    global _DETECTED
    if _DETECTED is None:
        steam, own = {}, {}
        try:
            from detect_games import (find_steam_root, parse_library_folders,
                                      find_installed_games, find_own_installed)
            sr = find_steam_root() or STEAM_ROOT_DEFAULT
            steam = find_installed_games(parse_library_folders(sr), sr)
            own = find_own_installed()
        except Exception:
            _log.warning("save backup: game detection failed", exc_info=True)
        _DETECTED = (steam, own)
    return _DETECTED


def _find_install_dir(keys: list, setup_games: dict, installed_games: dict = None) -> str | None:
    """Find the install directory for any of the given keys."""
    # First try installed_games (passed during install flow)
    if installed_games:
        for key in keys:
            if key in installed_games:
                d = installed_games[key].get("install_dir")
                if d and os.path.isdir(d):
                    return d

    # Otherwise detect, using the source each key was set up from
    steam, own = _detected_games()
    for key in keys:
        src = own if setup_games.get(key, {}).get("source") == "own" else steam
        d = src.get(key, {}).get("install_dir")
        if d and os.path.isdir(d):
            return d

    return None


def _find_t7x_players(keys: list, setup_games: dict, installed_games: dict = None) -> str | None:
    """Find the T7X sibling players directory."""
    # T7X lives in DeckOps-T7X/ next to the BO3 install dir, so find that first
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


def _keep_pre_restore(path: str):
    """Copy the current save dir to <path>.pre-restore before a restore
    overwrites it, so stats earned since the backup aren't lost for good."""
    try:
        if not os.path.isdir(path) or not any(True for _ in os.scandir(path)):
            return
        keep = path.rstrip(os.sep) + ".pre-restore"
        shutil.rmtree(keep, ignore_errors=True)
        shutil.copytree(path, keep)
    except OSError as ex:
        _log.warning("save restore: could not keep %s: %s", path, ex)


# --- Public API

def backup_saves(steam_root: str = None, on_progress=None,
                 installed_games: dict = None) -> dict:
    """Back up save data for all installed games.

    steam_root       : Steam root path (defaults to ~/.local/share/Steam)
    on_progress      : callback(message: str)
    installed_games  : optional dict of key -> game info (from install flow)

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

        if group["type"] == "plutonium_prefix":
            dst = os.path.join(BACKUP_ROOT, group_name)
            storages = _find_plutonium_storages(steam_root, group, setup_games)
            parts = {(tag, p): os.path.join(path, p) for tag, path in storages.items()
                     for p in _PLUT_USER_PARTS if os.path.isdir(os.path.join(path, p))}
            if not parts:
                _log.debug("save backup: %s — no players/ or mods/ found", group_name)
                continue
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            ok = [_copytree_safe(s, os.path.join(dst, tag, p), group_name, on_progress)
                  for (tag, p), s in parts.items()]
            if any(ok):
                backed_up[group_name] = dst
                on_progress(f"  ✓ {group_name}: backed up players/ and mods/ "
                            f"from {len(storages)} prefix(es), other Plutonium files skipped")
                _log.info("save backup: %s -> %s (%s)", group_name, dst, sorted(storages))
            continue

        if group["type"] == "install_dir":
            install_dir = _find_install_dir(keys, setup_games, installed_games)
            if install_dir:
                src = os.path.join(install_dir, group["subdir"])

        elif group["type"] == "t7x_sibling":
            src = _find_t7x_players(keys, setup_games, installed_games)

        if not src or not os.path.isdir(src):
            _log.debug("save backup: %s — source not found", group_name)
            continue

        # Skip empty save dirs
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

    steam_root       : Steam root path
    installed_games  : dict of key -> game info (install_dir, etc.)
    on_progress      : callback(message: str)

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

        # Skip empty backups
        try:
            has_files = any(True for _ in os.scandir(backup_dir))
        except OSError:
            continue
        if not has_files:
            continue

        dst = None

        if group["type"] == "plutonium_prefix":
            # Backups made before per-prefix tags hold storage/<game>/ flat
            entries = os.listdir(backup_dir)
            is_tagged = all(e.isdigit() or e == "heroic" or e.startswith("own_")
                            for e in entries)
            if is_tagged:
                # Sorted so own_old_t4mp restores before own_t4mp and the
                # current shared-prefix data wins
                sources = {tag: os.path.join(backup_dir, tag) for tag in sorted(entries)}
            else:
                sources = {group["appids"][0]: backup_dir}
            dsts = []
            for tag, src_root in sources.items():
                tdst = _plut_restore_dst(steam_root, group, tag)
                if not tdst:
                    on_progress(f"  ⚠ {group_name}: {tag} game not found, skipped")
                    continue
                for p in _PLUT_USER_PARTS:
                    src = os.path.join(src_root, p)
                    if not os.path.isdir(src):
                        continue
                    # Once per destination: shared WaW gets two sources
                    if p == "players" and tdst not in dsts:
                        _keep_pre_restore(os.path.join(tdst, p))
                    if _copytree_safe(src, os.path.join(tdst, p), group_name, on_progress):
                        dsts.append(tdst)
            if dsts:
                restored[group_name] = dsts[0]
                on_progress(f"  ✓ {group_name}: saves restored")
                _log.info("save restore: %s -> %s", group_name, sorted(set(dsts)))
            continue

        if group["type"] == "install_dir":
            install_dir = _find_install_dir(keys, setup_games, installed_games)
            if install_dir:
                dst = os.path.join(install_dir, group["subdir"])

        elif group["type"] == "t7x_sibling":
            # T7X sits next to the BO3 install dir
            bo3_dir = _find_install_dir(["t7", "t7x"], setup_games, installed_games)
            if bo3_dir:
                dst = os.path.join(os.path.dirname(bo3_dir), "DeckOps-T7X", "players")

        if dst:
            _keep_pre_restore(dst)

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


# --- CLI (manual use and the uninstaller)

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
