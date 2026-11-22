"""
plutonium.py - DeckOps installer for Plutonium (every device except Steam Deck LCD)
(Call of Duty: MW3, World at War, Black Ops, Black Ops II)

install_plutonium() hands LCD Decks to plutonium_lcd.py early on. The rest
of this file covers OLED and Other (non-Deck) devices, which launch
Plutonium directly through Proton.

OLED / Other flow:
  1. Download plutonium.exe into a dedicated DeckOps Wine prefix.
  2. Run it through Proton so the user can log in and Plutonium can
     download its full client.
  3. Wait for the user to confirm they logged in and closed Plutonium.
  4. Check that the storage/ folder exists in the prefix.
  5. Set up Plutonium in each selected game's prefix: shared folders link
     to the dedicated prefix, the game's storage/ is copied.
  6. Write config.json in each prefix with the game install paths.
  7. Write the launch files. Steam games keep their exe and get Plutonium
     Online / Offline entries in the Steam launch menu. Own games get a
     standalone wrapper for their shortcut.

Progress is reported through a callback:
    on_progress(percent: int, status: str)
"""

import os
import stat
import shutil
import json
import subprocess
import time

from log import get_logger
from net import DownloadError, download
from depot_downgrade import plut_game_dir

_log = get_logger(__name__)



# --- dedicated prefix
# DeckOps keeps its own Wine prefix for the first Plutonium install, so it
# needs no non-Steam game entry from Steam and has a fixed path to copy from.

DEDICATED_PREFIX = os.path.expanduser("~/.local/share/deckops/plutonium_prefix")
PLUT_BOOTSTRAPPER_URL = "https://cdn.plutonium.pw/updater/plutonium.exe"
_PLUT_ARCHIVE_FALLBACK_URL = "https://archive.org/download/plutonium_202605/plutonium.exe"


# --- game metadata
# DeckOps game key -> (appid, config.json path key, stock exe name)

GAME_META = {
    "t4sp":  (10090,  "t4Path",  "CoDWaW.exe"),
    "t4mp":  (10090,  "t4Path",  "CoDWaWmp.exe"),
    "t5sp":  (42700,  "t5Path",  "BlackOps.exe"),
    "t5mp":  (42710,  "t5Path",  "BlackOpsMP.exe"),
    "t6zm":  (212910, "t6Path",  "t6zm.exe"),
    "t6mp":  (202990, "t6Path",  "t6mp.exe"),
    "iw5mp": (42690,  "iw5Path", "iw5mp.exe"),
    "iw5mp_ds": (42750, "iw5Path", "iw5mp_server.exe"),
}

METADATA_FILE = "deckops_plutonium.json"

# Standalone wrapper exe names for OLED own games. These are new files in
# the game folder and the original exe stays untouched. shortcut.py points
# the non-Steam shortcut at them. The names match LCD_OWN_WRAPPER_EXES in
# plutonium_lcd.py so the launcher treats both models the same.
OLED_OWN_WRAPPER_EXES = {
    "t4sp":  "t4plutsp.exe",
    "t4mp":  "t4plutmp.exe",
    "t5sp":  "t5plutsp.exe",
    "t5mp":  "t5plutmp.exe",
    "t6mp":  "t6plutmp.exe",
    "t6zm":  "t6plutzm.exe",
    "iw5mp": "iw5plutmp.exe",
}

# OLED Steam games: (online, offline) wrapper files written next to the
# untouched game exe. Steam launch menu entries point at these (see
# steam_appinfo.py). Offline opens the Offline launcher (write_offline_menu_file).
# Keys sharing an appid (WaW) appear in this order.
STEAM_MENU_EXES = {
    "t4sp":  ("t4plutsp.exe",  "t4plutsp_lan.exe"),
    "t4mp":  ("t4plutmp.exe",  "t4plutmp_lan.exe"),
    "t5sp":  ("t5plutsp.exe",  "t5plutsp_lan.exe"),
    "t5mp":  ("t5plutmp.exe",  "t5plutmp_lan.exe"),
    "t6mp":  ("t6plutmp.exe",  "t6plutmp_lan.exe"),
    "t6zm":  ("t6plutzm.exe",  "t6plutzm_lan.exe"),
    "iw5mp": ("iw5plutmp.exe", "iw5plutmp_lan.exe"),
    # DS shares MW3's folder, so its files need their own names
    "iw5mp_ds": ("iw5plutds.exe", "iw5plutds_lan.exe"),
}

# Menu labels where one appid holds two modes. Others get the defaults.
STEAM_MENU_LABELS = {
    "t4sp": ("Play Plutonium SP/ZM Online", "Play Plutonium SP/ZM Offline"),
    "t4mp": ("Play Plutonium Multiplayer Online", "Play Plutonium Multiplayer Offline"),
}
_DEFAULT_MENU_LABELS = ("Play Plutonium Online", "Play Plutonium Offline")

# Offline -lan script names (OLED and LCD). They sit next to the game files,
# replace nothing, and DeckOps_Offline.exe runs them for offline play. They
# are shell scripts, not .exe, so Steam's file validation ignores them.
OLED_LAN_WRAPPER_NAMES = {
    "t4sp":  "t4plut_lan_sp.sh",
    "t4mp":  "t4plut_lan_mp.sh",
    "t5sp":  "t5plut_lan_sp.sh",
    "t5mp":  "t5plut_lan_mp.sh",
    "t6mp":  "t6plut_lan_mp.sh",
    "t6zm":  "t6plut_lan_zm.sh",
    "iw5mp": "iw5plut_lan.sh",
    "iw5mp_ds": "iw5plut_lan.sh",
}

# Shared names older DeckOps versions used before each mode got its own.
# The install deletes these stale files.
_OLD_OLED_LAN_WRAPPER_NAMES = {
    "t4sp":  "t4plut_lan.sh",
    "t4mp":  "t4plut_lan.sh",
    "t5sp":  "t5plut_lan.sh",
    "t5mp":  "t5plut_lan.sh",
    "t6mp":  "t6plut_lan.sh",
    "t6zm":  "t6plut_lan.sh",
}

# DeckOps client-side menu mods, packed as .iwd files (renamed .zip). They
# ship in assets/mods/ and are copied into Plutonium's storage/ folder,
# which the game loads on launch.
#
# T6 uses one .iwd (deckops_bo2_menu.iwd) for MP and ZM. Its Lua holds both
# PopulateButtons_Multiplayer and PopulateButtons_Zombie, and the engine's
# CoD.isZombie check picks the button set at runtime. t6mp and t6zm share
# the source and destination, so installing both is harmless.
_OLED_HERE = os.path.dirname(os.path.abspath(__file__))
MENU_MOD_ASSETS_DIR = os.path.join(os.path.dirname(_OLED_HERE), "assets", "mods")
MENU_MOD_FILES = {
    "t6mp":  ("t6/deckops_bo2_menu.iwd", "storage/t6/raw/deckops_bo2_menu.iwd"),
    "t6zm":  ("t6/deckops_bo2_menu.iwd", "storage/t6/raw/deckops_bo2_menu.iwd"),
}


# --- path helpers

def _plut_dir_in_prefix(prefix_path: str) -> str:
    """Return the Plutonium/ folder path inside a given Wine prefix."""
    return os.path.join(
        prefix_path, "pfx", "drive_c", "users", "steamuser",
        "AppData", "Local", "Plutonium",
    )


def _plut_dir_in_compatdata(steam_root: str, appid: int) -> str:
    """Return the Plutonium/ folder path inside a Steam compatdata prefix."""
    return os.path.join(
        steam_root, "steamapps", "compatdata", str(appid),
        "pfx", "drive_c", "users", "steamuser",
        "AppData", "Local", "Plutonium",
    )


def _wine_path(linux_path: str) -> str:
    """Convert a Linux path to Wine Z: drive notation."""
    return "Z:" + linux_path.replace("/", "\\")


# --- dedicated prefix helpers

def get_dedicated_plut_dir() -> str:
    """Return the Plutonium/ folder inside DeckOps's dedicated prefix."""
    return _plut_dir_in_prefix(DEDICATED_PREFIX)


def is_plutonium_ready() -> bool:
    """
    True once the user has logged in and Plutonium has downloaded its
    client files. Plutonium creates storage/ only after a successful login.
    """
    storage = os.path.join(get_dedicated_plut_dir(), "storage")
    if not os.path.isdir(storage):
        return False
    # Must have at least one game subfolder inside storage/
    return any(
        os.path.isdir(os.path.join(storage, d))
        for d in os.listdir(storage)
    )


# --- bootstrapper

def launch_bootstrapper(proton_path: str, on_progress=None, steam_root: str = None):
    """
    Download plutonium.exe into the dedicated prefix and launch it through
    Proton. Blocks until the user closes the Plutonium window.

    The UI shows the user instructions before calling this and a
    confirmation button after it returns.
    """
    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    plut_dir = get_dedicated_plut_dir()
    os.makedirs(plut_dir, exist_ok=True)

    # Proton needs the prefix folder to exist. It sets up pfx/ inside.
    os.makedirs(DEDICATED_PREFIX, exist_ok=True)

    bootstrapper = os.path.join(plut_dir, "plutonium.exe")

    prog(5, "Downloading Plutonium bootstrapper...")
    try:
        download(PLUT_BOOTSTRAPPER_URL, bootstrapper)
    except Exception as ex:
        _log.warning("Primary Plutonium download failed after 3 attempts: %s", ex)
        prog(5, "Falling back to archive.org mirror...")
        # Drop the primary's partial file or download() would resume the
        # mirror's copy on top of it.
        try: os.remove(bootstrapper + ".part")
        except OSError: pass
        try:
            download(_PLUT_ARCHIVE_FALLBACK_URL, bootstrapper)
            _log.info("Plutonium bootstrapper downloaded from archive.org fallback")
        except Exception as ex2:
            raise DownloadError(
                url=_PLUT_ARCHIVE_FALLBACK_URL,
                dest=bootstrapper,
                label="Plutonium bootstrapper",
                cause=ex2,
            )

    prog(15, "Launching Plutonium , please log in, then close the window when done.")

    env = os.environ.copy()
    env["STEAM_COMPAT_DATA_PATH"]           = DEDICATED_PREFIX
    if steam_root:
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = steam_root
    else:
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = os.path.dirname(
            os.path.dirname(proton_path)
        )

    proc = subprocess.Popen(
        [proton_path, "run", bootstrapper],
        env=env,
        cwd=plut_dir,
    )
    proc.wait()
    prog(30, "Plutonium closed.")


# --- shared Plutonium folders
# bin/, launcher/ and games/ are the same in every prefix (~129MB total).
# Each prefix symlinks them to the master copy in the dedicated prefix, so
# pre-launch updates reach every prefix. Only storage/ is per-game.
_PLUT_SHARED_SUBDIRS = ("bin", "launcher", "games")

# Old copy of the shared dirs that prefixes used to link to. Update Plutonium
# removes it, then reinstalls every Plutonium game so they link to the master.
SHARED_PLUT_DIR = os.path.expanduser("~/.local/share/deckops/plutonium_shared")


_STORAGE_SUBDIRS = {
    "t4sp": "t4", "t4mp": "t4",
    "t5sp": "t5", "t5mp": "t5",
    "t6zm": "t6", "t6mp": "t6",
    "iw5mp": "iw5", "iw5mp_ds": "iw5",
}


def _link_to_master(master: str, plut_dir: str, prog):
    """
    Swap the Plutonium files just copied into plut_dir for links to the
    master, so each file is stored once and pre-launch updates reach every
    prefix. Best effort: without the manifest the copies stay and the first
    online launch links them instead.
    """
    def say(msg):
        _log.info(msg); prog(msg)
    try:
        import plutonium_update as pu
        _, info = pu.fetch()
        pu.link_prefix(master, plut_dir, info, say)
    except Exception as ex:
        say(f"  ⚠ Plutonium links skipped, copies kept: {ex}")


def _copy_plut_to_prefix(src_plut_dir: str, dest_plut_dir: str,
                          game_key: str = "", on_progress=None):
    """
    Set up Plutonium in a game prefix, with symlinks for the shared folders.

    bin/, launcher/ and games/ link to the master copy in the dedicated
    prefix. Only game_key's storage/ subfolder is copied as real files, so
    large mods (e.g. Zombies Declassified, ~9GB in storage/t6/) stay out
    of other prefixes.
    """

    def prog(msg):
        if on_progress:
            on_progress(msg)

    prog(f"  Copying Plutonium: {src_plut_dir} -> {dest_plut_dir}")

    # The fresh copy below wipes dest_plut_dir, which also holds the user's
    # stats (players/, e.g. WaW mpdata) and mods. Move those aside first and
    # put them back after, so reinstall/update never resets progress.
    keep_root = dest_plut_dir.rstrip(os.sep) + ".deckops_keep"
    _stash_user_storage(dest_plut_dir, keep_root, prog)
    try:
        _copy_plut_fresh(src_plut_dir, dest_plut_dir, game_key, prog)
    finally:
        _restore_user_storage(dest_plut_dir, keep_root, prog)


# storage/<game>/ parts that belong to the user, not to Plutonium.
# usermaps/ holds custom maps and Zombies Declassified (~9 GB).
_PLUT_USER_PARTS = ("players", "mods", "usermaps")

# Never copied from one prefix to another: each prefix keeps its own, and
# copying them is how ZD ended up in every BO2 prefix.
_PLUT_NO_COPY = ("mods", "usermaps")


def _skip_no_copy(root):
    return lambda d, names: [n for n in names if n in _PLUT_NO_COPY] if d == root else []


def _stash_user_storage(plut_dir: str, keep_root: str, prog):
    storage = os.path.join(plut_dir, "storage")
    if not os.path.isdir(storage):
        return
    for store in os.listdir(storage):
        for part in _PLUT_USER_PARTS:
            src = os.path.join(storage, store, part)
            dst = os.path.join(keep_root, store, part)
            # A keep dir left by an earlier failed run already holds the
            # user's data. What's in the prefix now is a fresh copy.
            if not os.path.isdir(src) or os.path.lexists(dst):
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            prog(f"  Kept storage/{store}/{part}")


def _restore_user_storage(plut_dir: str, keep_root: str, prog):
    if not os.path.isdir(keep_root):
        return
    try:
        for store in os.listdir(keep_root):
            for part in os.listdir(os.path.join(keep_root, store)):
                src = os.path.join(keep_root, store, part)
                dst = os.path.join(plut_dir, "storage", store, part)
                if os.path.lexists(dst):
                    shutil.rmtree(dst)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst)
        shutil.rmtree(keep_root)
    except OSError as ex:
        _log.error("Could not restore Plutonium user data from %s: %s", keep_root, ex)
        prog(f"  ⚠ Your Plutonium stats/mods are safe in {keep_root} but could not be moved back: {ex}")


def _copy_plut_fresh(src_plut_dir: str, dest_plut_dir: str, game_key: str, prog):
    if os.path.exists(dest_plut_dir):
        prog(f"  Removing existing Plutonium at {dest_plut_dir}...")
        shutil.rmtree(dest_plut_dir)

    start = time.time()

    os.makedirs(dest_plut_dir, exist_ok=True)

    # Symlink shared directories to the master
    for subdir in _PLUT_SHARED_SUBDIRS:
        shared_src = os.path.join(src_plut_dir, subdir)
        dest_sub = os.path.join(dest_plut_dir, subdir)
        if os.path.isdir(shared_src):
            os.symlink(shared_src, dest_sub)

    # Copy only the storage subdirectory for this game
    storage_src = os.path.join(src_plut_dir, "storage")
    if os.path.isdir(storage_src):
        storage_name = _STORAGE_SUBDIRS.get(game_key)
        if storage_name:
            sub_src = os.path.join(storage_src, storage_name)
            if os.path.isdir(sub_src):
                sub_dst = os.path.join(dest_plut_dir, "storage", storage_name)
                os.makedirs(os.path.join(dest_plut_dir, "storage"), exist_ok=True)
                shutil.copytree(sub_src, sub_dst, ignore=_skip_no_copy(sub_src))
        else:
            storage_dst = os.path.join(dest_plut_dir, "storage")
            shutil.copytree(storage_src, storage_dst)

    # Copy any remaining top-level files (config, etc.)
    for item in os.listdir(src_plut_dir):
        src_item = os.path.join(src_plut_dir, item)
        dst_item = os.path.join(dest_plut_dir, item)
        if os.path.exists(dst_item):
            continue  # already handled (symlink or storage)
        if os.path.isfile(src_item):
            shutil.copy2(src_item, dst_item)

    elapsed = time.time() - start
    prog(f"  Copied Plutonium with symlinks ({elapsed:.1f}s)")


# --- config.json

def _write_config(plut_dir: str, game_keys: list, installed_games: dict):
    """
    Write config.json in a prefix with the game install paths. Keeps the
    prefix's existing config (token etc.) and updates the path keys.
    game_keys:       game keys installed into this prefix
    installed_games: dict from detect_games.find_installed_games()
    """
    config_path = os.path.join(plut_dir, "config.json")

    # Read existing config (token etc.) from this prefix if present
    if os.path.exists(config_path):
        with open(config_path) as f:
            data = json.load(f)
    else:
        data = {}

    # Write the path key for each game in this prefix
    for key in game_keys:
        if key not in GAME_META:
            continue
        _, path_key, _ = GAME_META[key]
        game = installed_games.get(key, {})
        install_dir = game.get("install_dir", "")
        if install_dir:
            # MW3 Steam: point at the downgrade/ subfolder with the 32-bit
            # depot files. The 64-bit install stays untouched.
            install_dir = plut_game_dir(key, install_dir, game.get("source", "steam"))
            data[path_key] = _wine_path(install_dir)

    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)


# --- client-side menu mods

def _install_menu_mod(dest_plut_dir: str, game_key: str, on_progress=None):
    """
    Install the DeckOps menu mod for game_key.

    Copies the bundled file from assets/mods/ into raw/ in the prefix's
    Plutonium storage. Plutonium loads .iwd files from raw/ on every
    launch, so the DeckOps main menu (server connect, unlock all, reset
    stats buttons) replaces the default one.

    raw/ instead of mods/ keeps normal player stats (no separate mod
    stats) and keeps the menu across disconnects.

    Does nothing for game keys without a menu mod.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if game_key not in MENU_MOD_FILES:
        return

    asset_rel, local_path = MENU_MOD_FILES[game_key]
    src_file = os.path.join(MENU_MOD_ASSETS_DIR, asset_rel)
    dest_file = os.path.join(dest_plut_dir, local_path)

    prog(f"  Installing DeckOps menu mod for {game_key}...")

    if not os.path.isfile(src_file):
        prog(f"  ⚠ Menu mod asset missing: {src_file}")
        return  # Not fatal. The game works without the mod.

    os.makedirs(os.path.dirname(dest_file), exist_ok=True)

    try:
        shutil.copy2(src_file, dest_file)
        prog(f"  ✓ Menu mod installed ({os.path.getsize(dest_file)} bytes)")
    except OSError as ex:
        prog(f"  ⚠ Menu mod copy failed: {ex}")


# --- launcher prefix game configs
#
# Game key -> DeckOps asset config and the storage path inside the Plutonium
# folder where the bootstrapper looks for it. The one place that decides
# where game configs go in a Plutonium folder (a game's prefix and its
# offline copy). Runs on every Plutonium install or reinstall, so the
# configs land whichever install flow started it.

_LAUNCHER_CONFIG_MAP = {
    # game_key: (asset_subpath, storage_relpath)
    "t4sp":     ("WaW/config.cfg",          os.path.join("storage", "t4", "players", "profiles", "$$$")),
    "t4mp":     ("WaW/config_mp.cfg",       os.path.join("storage", "t4", "players", "profiles", "$$$")),
    "t5sp":     ("BO1/config.cfg",          os.path.join("storage", "t5", "players")),
    "t5mp":     ("BO1/config_mp.cfg",       os.path.join("storage", "t5", "players")),
    "t6mp":     ("BO2/plutonium_mp.cfg",    os.path.join("storage", "t6", "players")),
    "t6zm":     ("BO2/plutonium_zm.cfg",    os.path.join("storage", "t6", "players")),
    "iw5mp":    ("MW3/config_mp.cfg",       os.path.join("storage", "iw5", "players")),
    "iw5mp_ds": ("MW3/config_mp.cfg",       os.path.join("storage", "iw5", "players")),
}


def _apply_launcher_game_configs(launcher_plut_dir: str, game_key: str,
                                  on_progress=None):
    """
    Copy the DeckOps asset config for game_key into a Plutonium folder, so
    the game starts with the right resolution, FOV, sensitivity and player
    name whichever install flow ran.

    install_plutonium calls it on the game's prefix right after
    config.json, before the menu mod. The device model in deckops.json
    picks the asset folder.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if game_key not in _LAUNCHER_CONFIG_MAP:
        return

    import config as _cfg
    deck_model = _cfg.get_deck_model() or "oled"
    player_name = _cfg.get_player_name() or "Player"
    model_dir = _cfg.get_model_config_dir()

    _here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(_here)
    configs_dir = os.path.join(project_root, "assets", "configs")

    asset_subpath, storage_relpath = _LAUNCHER_CONFIG_MAP[game_key]
    src = os.path.join(configs_dir, model_dir, asset_subpath)

    if not os.path.exists(src):
        prog(f"  ⚠ Launcher config asset not found: {asset_subpath}")
        return

    dest_dir = os.path.join(launcher_plut_dir, storage_relpath)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(src))

    try:
        shutil.copy2(src, dest)

        # Apply player name
        from game_config import _replace_player_name
        _replace_player_name(dest, player_name)

        prog(f"  + {game_key}: launcher config -> {os.path.basename(src)}")
    except Exception as ex:
        prog(f"  ⚠ {game_key}: launcher config failed: {ex}")


# --- wrapper script

# DeckOps game key -> Plutonium protocol key, used in
# `plutonium://play/<key>` URLs and bootstrapper arguments. Most keys are
# the same. iw5mp_ds (the free dedicated server, appid 42750) runs the same
# Plutonium client as iw5mp (the full game, appid 42690).
_PLUT_KEY_MAP = {
    "iw5mp_ds": "iw5mp",
}

def _plut_key(game_key: str) -> str:
    """Return the Plutonium protocol key for a DeckOps game key."""
    return _PLUT_KEY_MAP.get(game_key, game_key)

def _write_oled_own_wrapper(game: dict, game_key: str, steam_root: str,
                             proton_path: str, compatdata_path: str,
                             plut_dir: str, wrapper_name: str = None) -> str | None:
    """
    Write a standalone wrapper exe for OLED own games.

    Creates a new file (e.g. t4plutmp.exe) in the game's install dir that
    starts the Plutonium launcher with a protocol URL. The original game
    exe stays untouched. shortcut.py points the non-Steam shortcut at this
    wrapper, and the launcher runs it from the stored wrapper_path. Steam
    games reuse it for their Online launch menu entry (wrapper_name from
    STEAM_MENU_EXES).

    Returns the wrapper's full path, or None if game_key has no entry in
    OLED_OWN_WRAPPER_EXES and no wrapper_name was given.
    """
    if not wrapper_name and game_key not in OLED_OWN_WRAPPER_EXES:
        return None

    install_dir  = game["install_dir"]
    wrapper_name = wrapper_name or OLED_OWN_WRAPPER_EXES[game_key]
    wrapper_path = os.path.join(install_dir, wrapper_name)

    launcher = os.path.join(plut_dir, "bin",
                            "plutonium-launcher-win32.exe")
    plut_url = f"plutonium://play/{_plut_key(game_key)}"
    from steam_common import prelaunch_prefix

    script = (
        "#!/bin/bash\n"
        f"export STEAM_COMPAT_DATA_PATH=\"{compatdata_path}\"\n"
        f"export STEAM_COMPAT_CLIENT_INSTALL_PATH=\"{steam_root}\"\n"
        # Silent Plutonium update. The launcher never updates on its own.
        f"{prelaunch_prefix(game_key)}true\n"
        f"\"{proton_path}\" run \"{launcher}\" \"{plut_url}\" &\n"
        "PROTON_PID=$!\n"
        "sleep 8\n"
        "while kill -0 $PROTON_PID 2>/dev/null || "
        f"pgrep -fa wineserver | grep -q \"{compatdata_path}\"; do\n"
        "  sleep 3\n"
        "done\n"
    )

    with open(wrapper_path, "wb") as f:
        f.write(script.encode("utf-8"))

    os.chmod(wrapper_path, os.stat(wrapper_path).st_mode |
             stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return wrapper_path


def _write_offline_wrapper(game: dict, game_key: str, source: str = "steam") -> str | None:
    """
    Write the game's offline script (e.g. t6plut_lan_mp.sh) next to the game files,
    OLED and LCD alike. DeckOps_Offline.exe runs it through launcher_offline.sh (the
    Steam launch menu's Plutonium Offline entry opens that launcher). It hands over to
    assets/LAN/lan_server.sh, which starts the game from the offline Plutonium copy
    in LAN_PREFIX; WaW MP, BO1 MP, BO2 MP and MW3 MP also host a local server with bots.

    The player name stays as +name "..." so game_config's rename finds it.
    Returns the script path, or None for a key without offline play.
    """
    if game_key not in OLED_LAN_WRAPPER_NAMES:
        return None
    install_dir = game["install_dir"]
    path = os.path.join(install_dir, OLED_LAN_WRAPPER_NAMES[game_key])

    # Older versions shared one name for SP/MP pairs. Drop the stale file.
    old_name = _OLD_OLED_LAN_WRAPPER_NAMES.get(game_key)
    if old_name and old_name != OLED_LAN_WRAPPER_NAMES[game_key]:
        old_path = os.path.join(install_dir, old_name)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                _log.debug("old wrapper cleanup failed", exc_info=True)

    import config as _cfg
    from steam_common import wine_path_for_prefix
    name = (_cfg.get_player_name() or "Player").replace('"', "")
    mode = _plut_key(game_key)
    game_dir = plut_game_dir(game_key, install_dir, source)
    q = lambda v: "'" + v.replace("'", "'\\''") + "'"
    run = (f'exec {q(os.path.join(os.path.dirname(_OLED_HERE), "assets", "LAN", "lan_server.sh"))} '
           f'{mode} {q(wine_path_for_prefix(game_dir, LAN_PREFIX))} +name "{name}"')
    lines = ["#!/bin/bash", f"# DeckOps offline {mode} (plutonium._write_offline_wrapper)"]
    if game_key in LAN_KEYS:
        run += f" {LAN_PORT} {q(wine_path_for_prefix(game_dir, LAN_SERVER_PREFIX))} " + _LAN_SERVER_ARGS[mode]
        if mode == "t6mp":
            # Map / Mode lists only the maps this install has
            lines += [f"G={q(game_dir)}", "M=$(cd \"$G/zone/all\" && ls mp_*.ff | sed 's/\\.ff$//' | paste -sd,)"]
            run = 'CLIENT_ARGS="+set fs_game mods/deckops_offline" ' + run
        elif mode in ("t4mp", "t5mp", "iw5mp"):
            # WaW keeps maps in zone/<language>/ next to their _load files, BO1 in zone/Common/,
            # MW3 in zone/<language>/ and zone/dlc/
            lines += [f"G={q(game_dir)}", "M=$(cd \"$G/zone\" && ls */mp_*.ff | sed 's|.*/||; s/\\.ff$//' | grep -v '_load$' | sort -u | paste -sd,)"]
            if mode == "t5mp":
                # BO1 crashes in FS_Startup switching to the server's mod mid-join: start in it
                run = 'CLIENT_ARGS="+set fs_game mods/mp_deckops_offline" ' + run
    with open(path, "w") as f:
        f.write("\n".join(lines + [run]) + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _write_wrapper(game: dict, game_key: str, steam_root: str,
                   proton_path: str, compatdata_path: str, plut_dir: str):
    """
    Replace the game exe with a bash wrapper that starts Plutonium through
    Proton. OLED / Other only. LCD uses plutonium_lcd.py.

    Calls plutonium-launcher-win32.exe with a protocol URL. The user must
    have logged in.

    The original exe is backed up as <exe>.bak. The wrapper is padded to
    the original file's size so Steam's file validation does not flag it.
    """
    install_dir    = game["install_dir"]
    _, _, exe_name = GAME_META[game_key]
    exe_path       = os.path.join(install_dir, exe_name)
    backup_path    = exe_path + ".bak"

    # No wrapper without the original exe. Steam games always ship the exe
    # we replace, so a missing one means detection returned the wrong key,
    # and writing here would leave a stray file that confuses later
    # detection runs.
    if not os.path.exists(exe_path) and not os.path.exists(backup_path):
        return

    # Original size, read before the overwrite
    original_size = os.path.getsize(exe_path) if os.path.exists(exe_path) else 0

    # Back up the original exe
    if not os.path.exists(backup_path) and os.path.exists(exe_path):
        shutil.copy2(exe_path, backup_path)
        original_size = os.path.getsize(backup_path)

    # OLED online mode: call the launcher with a protocol URL
    launcher = os.path.join(plut_dir, "bin", "plutonium-launcher-win32.exe")
    plut_url = f"plutonium://play/{_plut_key(game_key)}"
    script = (
        "#!/bin/bash\n"
        f"export STEAM_COMPAT_DATA_PATH=\"{compatdata_path}\"\n"
        f"export STEAM_COMPAT_CLIENT_INSTALL_PATH=\"{steam_root}\"\n"
        f"\"{proton_path}\" run \"{launcher}\" \"{plut_url}\" &\n"
        "PROTON_PID=$!\n"
        "sleep 8\n"
        "while kill -0 $PROTON_PID 2>/dev/null || "
        f"pgrep -fa wineserver | grep -q \"{compatdata_path}\"; do\n"
        "  sleep 3\n"
        "done\n"
    )

    script_bytes = script.encode("utf-8")
    if original_size > len(script_bytes):
        script_bytes += b"\x00" * (original_size - len(script_bytes))

    with open(exe_path, "wb") as f:
        f.write(script_bytes)

    os.chmod(exe_path, os.stat(exe_path).st_mode |
             stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _is_script(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"#!"
    except OSError:
        return False


def _restore_original_exe(game: dict, game_key: str):
    """
    Undo the old exe replacement: put <exe>.bak back over our wrapper.
    If Steam already restored the real exe (e.g. Verify), drop the stale .bak.
    """
    exe_path = os.path.join(game["install_dir"], GAME_META[game_key][2])
    bak_path = exe_path + ".bak"
    if not os.path.exists(bak_path):
        return
    if not os.path.exists(exe_path) or _is_script(exe_path):
        os.replace(bak_path, exe_path)
    else:
        os.remove(bak_path)


def _setup_steam_menu(game: dict, game_key: str, steam_root: str,
                      proton_path: str, compatdata_path: str, plut_dir: str,
                      lan_wrapper_path: str, prog) -> str | None:
    """
    OLED Steam games: keep the original exe and add Plutonium Online /
    Offline entries to the game's Steam launch menu, each pointing at its
    own wrapper file. Steam runs the chosen file through its Proton, as it
    ran the replaced exe in older versions. Returns the online wrapper path.
    """
    online_name, offline_name = STEAM_MENU_EXES[game_key]
    _restore_original_exe(game, game_key)

    online_path = _write_oled_own_wrapper(
        game, game_key, steam_root, proton_path,
        compatdata_path, plut_dir, wrapper_name=online_name,
    )
    if lan_wrapper_path and os.path.exists(lan_wrapper_path):
        write_offline_menu_file(os.path.join(game["install_dir"], offline_name))
    add_steam_menu(game, game_key, steam_root, prog)

    # Fallback for when Steam refreshes appinfo.vdf and drops our menu: prelaunch.sh
    # swaps an untagged stock exe for its online file (VANILLA_TAG marks a stock pick).
    from steam_common import prelaunch_prefix
    from wrapper import set_launch_options, clear_launch_options
    appid = GAME_META[game_key][0]
    pairs = " ".join(f"{GAME_META[k][2]}={STEAM_MENU_EXES[k][0]}"
                     for k in STEAM_MENU_EXES if GAME_META[k][0] == appid)
    clear_launch_options(steam_root, appid)
    set_launch_options(steam_root, appid, f'DECKOPS_MENU="{pairs}" {prelaunch_prefix("menu")}%command%')
    return online_path


def write_offline_menu_file(path: str):
    """Write the Steam menu's Plutonium Offline file (OLED and LCD). prelaunch.sh or
    cache_cleanup.py runs it on the host and it opens the DeckOps: Plutonium Offline launcher."""
    from shortcut import launcher_run_url
    with open(path, "w") as f:
        f.write(f'#!/bin/bash\nexec steam "{launcher_run_url()}"\n')
    os.chmod(path, 0o755)


def add_steam_menu(game: dict, game_key: str, steam_root: str, prog):
    """
    Rebuild our entries for this appid in STEAM_MENU_EXES order (Online
    before Offline, WaW SP before MP), whatever order the keys were
    installed in. A sibling key counts once its online file is on disk.
    LCD uses this too and writes its own files under the same names.
    """
    appid = GAME_META[game_key][0]
    keys = [k for k in STEAM_MENU_EXES if GAME_META[k][0] == appid and (
            k == game_key or os.path.exists(os.path.join(game["install_dir"], STEAM_MENU_EXES[k][0])))]
    entries = []
    for k in keys:
        on, off = STEAM_MENU_LABELS.get(k, _DEFAULT_MENU_LABELS)
        entries.append({"executable": STEAM_MENU_EXES[k][0], "description": on})
        # Offline entry only with Offline Mode on, which is exactly when its file exists
        if os.path.exists(os.path.join(game["install_dir"], STEAM_MENU_EXES[k][1])):
            entries.append({"executable": STEAM_MENU_EXES[k][1], "description": off})

    from steam_appinfo import add_launch_entries, remove_launch_entries, VANILLA_TAG
    entries += [{"executable": GAME_META[k][2], "tag": VANILLA_TAG} for k in keys]
    remove_launch_entries(steam_root, appid, [n for k in keys for n in STEAM_MENU_EXES[k]])
    added = add_launch_entries(steam_root, appid, entries)
    prog(92, "  ✓ Launch menu: " + " / ".join(e["description"] for e in entries if "tag" not in e) if added
             else "  ⚠ Launch menu not added yet, will retry next time Steam is closed")


def remove_offline_files(game: dict, game_key: str):
    """Offline Mode off: delete the game's -lan script and its Steam menu Offline file,
    so add_steam_menu leaves the Offline entry out (same names on OLED and LCD)."""
    d = game.get("install_dir", "")
    for n in (OLED_LAN_WRAPPER_NAMES.get(game_key), STEAM_MENU_EXES.get(game_key, ("", ""))[1]):
        if n and d and os.path.isfile(os.path.join(d, n)):
            os.remove(os.path.join(d, n))
    # MW3's offline server config (setup_lan). The .dsr recipes stay, they may be the user's own.
    if game_key in ("iw5mp", "iw5mp_ds") and d:
        for sub in ("downgrade", ""):
            cfg_path = os.path.join(d, sub, "admin", "deckops_lan.cfg")
            if os.path.isfile(cfg_path):
                os.remove(cfg_path)


# --- metadata

def _write_metadata(install_dir: str, data: dict):
    path = os.path.join(install_dir, METADATA_FILE)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def cleanup_zd_from_other_prefixes(installed_games: dict, steam_root: str,
                                    on_progress=None):
    """
    Remove Zombies Declassified from every storage/t6 except the t6zm
    prefix's. Older versions left copies in the MP prefix, the master and
    the launcher prefix. Nothing is removed unless the t6zm prefix has ZD,
    so the last copy is never lost.

    Returns the number of places cleaned.
    """
    from zombies_declassified import (resolve_zd_storage, is_zd_installed, t6_storage,
                                      uninstall_zd, _ZD_PARTS)
    from shortcut import get_launcher_plut_dir

    def prog(msg):
        if on_progress:
            on_progress(msg)

    keep = resolve_zd_storage(installed_games.get("t6zm"))
    if not keep or not is_zd_installed(keep):
        return 0

    places = {
        "MP prefix": t6_storage("t6mp", installed_games.get("t6mp")),
        "Plutonium master": os.path.join(get_dedicated_plut_dir(), "storage", "t6"),
        "launcher prefix": os.path.join(get_launcher_plut_dir(), "storage", "t6"),
    }
    cleaned = 0
    for label, t6 in places.items():
        if not t6 or os.path.realpath(t6) == os.path.realpath(keep):
            continue
        if not any(os.path.lexists(os.path.join(t6, p)) for p in _ZD_PARTS):
            continue
        uninstall_zd(t6)
        cleaned += 1
        prog(f"  ✓ Removed Zombies Declassified copy from {label}")
    return cleaned


def cleanup_plut_from_non_plut_prefixes(steam_root: str, on_progress=None):
    """
    Remove Plutonium folders that leaked into prefixes of non-Plutonium games.

    Old versions ran _copy_plut_to_prefix() with a full storage/ copy into
    every managed prefix. Non-Plutonium appids (CoD4, MW2, MW3 SP, BO2 Campaign,
    BO3, Ghosts, AW) should never hold Plutonium data.

    Returns the number of prefixes cleaned.
    """
    from ge_proton import MANAGED_APPIDS

    def prog(msg):
        if on_progress:
            on_progress(msg)

    plut_appids = {str(meta[0]) for meta in GAME_META.values()}
    cleaned = 0

    for appid_str in MANAGED_APPIDS:
        if appid_str in plut_appids:
            continue
        plut_dir = _plut_dir_in_compatdata(steam_root, int(appid_str))
        if not os.path.isdir(plut_dir):
            continue
        prog(f"  Removing leaked Plutonium data from appid {appid_str}...")
        shutil.rmtree(plut_dir, ignore_errors=True)
        cleaned += 1
        prog(f"  ✓ Cleaned Plutonium from appid {appid_str}")

    return cleaned


# --- public API

# --- Offline: local LAN server (WaW MP, BO1 MP, BO2 MP, MW3 MP), run by assets/LAN/lan_server.sh
#
# Plain -lan play can't create a private match without a Plutonium account, so
# these games host a hidden local dedicated server and join it. Opt-in
# (config offline_mode). Server and game each run from their own Plutonium copy
# under LAN_ROOT: Plutonium's files are hard links to the online copy, settings
# and stats are real LAN files, user mods come in as one link per mod, and our
# offline-only files are real files. Every folder is real, so nothing is ever
# written through a link into an online folder and online launches never see our files.

LAN_ROOT = os.path.expanduser("~/.local/share/deckops/lan")
LAN_ASSETS = os.path.join(os.path.dirname(_OLED_HERE), "assets", "LAN", "offline")
# The offline Rejoin Match buttons connect to this port (WaW mod.ff, BO1 mod.ff Play,
# BO2 raw/deckops_bo2_menu.iwd, MW3 ui_mp/main.lua).
LAN_PORT = 4986
LAN_KEYS = ("t4mp", "t5mp", "t6mp", "iw5mp", "iw5mp_ds")
# Offline games run in their own prefix and the server in the Offline launcher's.
# The game's runtime launch (waitforexitandrun) waits for every wineserver on its
# prefix, so the two can't share one.
LAN_PREFIX = os.path.expanduser("~/.local/share/deckops/lan_prefix")
LAN_SERVER_PREFIX = os.path.expanduser("~/.local/share/deckops/launcher_prefix")
_LAN_SERVER_ARGS = {
    # $M: the maps in zone/all, listed by the offline script.
    "t6mp": '+set fs_game mods/deckops_offline +set dcac_maps "$M" +exec deckops_lan_mp.cfg +map_rotate',
    "iw5mp": '+set dcac_maps "$M" +set sv_config deckops_lan.cfg +start_map_rotate',
    # BO1 runs +exec (storage/t5/deckops_lan_mp.cfg). Bot Warfare and the class script load as loose
    # scripts, the class menu (dcac_list) comes from the mod's mod.ff.
    "t5mp": '+set fs_game mods/mp_deckops_offline +set dcac_maps "$M" +exec deckops_lan_mp.cfg +map_rotate',
    # T4 ignores +exec on a server and Bot Warfare makes its dvars at runtime, so all of it goes here.
    # WaW MP mods must be named mp_*. sv_maxclients 13: 12 bots + the player (Bot Count).
    # sv_floodprotect 0: every click in the Map / Mode and Bot Warfare menus is a menu response, and fast clicks get dropped.
    "t4mp": ('+set fs_game mods/mp_deckops_offline +set dcac_maps "$M" +set sv_maxclients 13 '
             '+set sv_hostname "DeckOps Offline" +set sv_floodprotect 0 +set logfile 1 +set g_inactivity 0 +set bots_main 1 '
             '+set bots_main_firstIsHost 0 +set bots_manage_fill 10 +set bots_manage_fill_mode 0 +set bots_manage_fill_kick 1 '
             '+set bots_skill 2 +map_rotate'),
}

# Third-party server files, downloaded at install. Their repos show no license,
# so we never redistribute them. Pinned to a commit, or a release checked by digest.
_T6_BW = ("https://raw.githubusercontent.com/ineedbots/t6_bot_warfare/"
          "cafee7d585160b046dc928f90798a611683e6cd1/scripts/mp/")
# Bot Warfare T5: its 2021 release predates Plutonium, so the files come from the repo, each one checked.
_T5_BW = ("https://raw.githubusercontent.com/ineedbots/t5_bot_warfare/"
          "93b82d7720fce4059b272d6a907747bef55e5c6a/")
_T6_GS = ("https://raw.githubusercontent.com/xerxes-at/T6ServerConfigs/"
          "6d3b313acab5b5e21d61277bd1d2f3b234dc4918/localappdata/Plutonium/storage/t6/gamesettings/")
LAN_DOWNLOADS = {
    "t6mp": [(f"storage/t6/raw/scripts/mp/{f}", _T6_BW + f, None)
             for f in ("bots.gsc", "bots_adapter_pt6.gsc")]
          + [(f"storage/t6/gamesettings/{g}.cfg", _T6_GS + g + ".cfg", None)
             for g in "conf ctf dem dm dom gun hq koth oic oneflag sas sd shrp tdm".split()],
    # Release zip. Only z_svr_bots.iwd is taken from it.
    "iw5mp": [("storage/iw5/z_svr_bots.iwd",
               "https://github.com/ineedbots/iw5_bot_warfare/releases/download/v2.3.0/iw5bw230.zip",
               "sha256:733692aaeda839635d86f9752803b04ecfbd0057f9475661b8cadf084543cfaa")],
    "t5mp": [(f"storage/t5/{f}", _T5_BW + f, "sha256:" + d) for f, d in (
        ("maps/mp/bots/_bot_loadout.gsc", "c2ef1cb1ff64edf92c746b88c8ad84082242025490e4d371c899e5cc8ac08424"),
        ("maps/mp/bots/_bot_script.gsc", "5430775257fde3cdce9359a1745950f280e497dd7762c8f203e1c490a784dff4"),
        ("maps/mp/bots/_bot_utility.gsc", "1c9420df6ddc5dcdd2ad8e252b756f68f39dd97a8fd97c10f5d111266afb3d06"),
        ("maps/mp/gametypes/_bot.gsc", "58447f23bda78d8c9a1e65b27bab1b97973acdc3fe4a1aa161299e946721d17c"),
        ("scripts/mp/bots_adapter_pt5.gsc", "3f0662c5386074288c7ed6f8e01e1206b7f850be474acb822d33a37de6993096"))],
    "t4mp": [("storage/t4/mods/mp_deckops_offline/z_svr_bots.iwd",
              "https://github.com/ineedbots/t4_bot_warfare/releases/download/v2.3.0/t4bw230.zip",
              "sha256:266a183f6557f58c14808ef455ba009e5d763295f47695731978b88aa45c2d21")],
}

# Plutonium's online data per title (demonware). pub is linked from the online copy.
# user (stats) stays a real LAN folder so offline stats never reach online.
# 18301 is a guess for BO1: Plutonium's folder had it next to BO2's and MW3's after a
# login, with MP and SP data (Deck, 2026-10-08). WaW had none.
_LAN_DW_TITLE = {"t6": "18397", "iw5": "18409", "t5": "18301"}
# Never taken from the online folder. The LAN copy keeps its own settings, logs
# and stats, and user mods come in as one link per mod.
_LAN_TOP_OWN = ("console.log", "crashdumps", "storage")
_LAN_STORE_OWN = ("players", "mods", "usermaps", "main", "demo", "imgui.ini")
_LAN_USER_DIRS = ("mods", "usermaps")
# Games run offline with a mod (fs_game) read their settings from players/<mod>/, not
# players/. BO2 MP fell back to 800x600 without them (Deck, 2026-10-08). game_config mirrors there.
LAN_MOD_PLAYERS = {"t6mp": os.path.join("mods", "deckops_offline"),
                   "t5mp": os.path.join("mods", "mp_deckops_offline")}
# WaW MP starts from players/profiles/$$$/ and reads profiles/$$$/<server mod>/ once it joins
# the server (1920x1200 only in one of them, PC 2026-10-09): game_config mirrors to both.
LAN_MOD_PROFILE = {"t4mp": os.path.join("mods", "mp_deckops_offline")}
# Server files older builds shipped. BO2's server needs no mod.ff since the real menus (client only, 2026-10-14).
_LAN_STALE = {"t6mp": ("storage/t6/mods/deckops_offline/mod.ff",)}
# Real (not hard-linked) files under LAN_ROOT past this size mean something got copied
# by mistake (mods are only ever linked). Our own files are a few MB.
_LAN_DISK_WARN = 100 * 1024 * 1024


def _lan_link(src: str, dst: str):
    """Make dst a hard link to src's real file, or a copy if they're on different drives."""
    src = os.path.realpath(src)
    if os.path.lexists(dst):
        if not os.path.islink(dst) and os.path.samefile(src, dst):
            return
        os.remove(dst)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _lan_mirror(src: str, dst: str, rel: str, keep):
    """Hard-link src's files (following links in src) into real folders under dst.
    keep: paths relative to the LAN root that are never taken from src."""
    os.makedirs(dst, exist_ok=True)
    for n in os.listdir(src) if os.path.isdir(src) else ():
        r = f"{rel}/{n}" if rel else n
        if r in keep:
            continue
        s, d = os.path.join(src, n), os.path.join(dst, n)
        if os.path.isdir(s):
            _lan_mirror(s, d, r, keep)
        elif os.path.isfile(s):
            _lan_link(s, d)


def _lan_tree(root: str, user_plut: str, master: str, store: str, files: dict, client: bool):
    """Build one LAN Plutonium copy at root from the game's online folder user_plut.
    files {rel: source} are our offline files (source None means a download, kept as is)."""
    # Drop links from the last build (old layout, removed mods). Real files stay.
    for dp, dns, fns in os.walk(root):
        for n in dns + fns:
            if os.path.islink(os.path.join(dp, n)):
                os.remove(os.path.join(dp, n))
        dns[:] = [n for n in dns if os.path.isdir(os.path.join(dp, n))]
    st = f"storage/{store}"
    keep = set(files) | set(_LAN_TOP_OWN) | {f"{st}/{n}" for n in _LAN_STORE_OWN}
    _lan_mirror(user_plut, root, "", keep)
    _lan_mirror(os.path.join(user_plut, st), os.path.join(root, st), st, keep)
    os.makedirs(os.path.join(root, st, "players"), exist_ok=True)
    if client:
        for d in _LAN_USER_DIRS:
            src = os.path.join(user_plut, st, d)
            ours = {r.split("/")[3] for r in files if r.startswith(f"{st}/{d}/")}
            os.makedirs(os.path.join(root, st, d), exist_ok=True)
            for n in os.listdir(src) if os.path.isdir(src) else ():
                p = os.path.join(root, st, d, n)
                if n not in ours and not os.path.lexists(p):
                    os.symlink(os.path.join(src, n), p)
        title = _LAN_DW_TITLE.get(store)
        pub = title and next((p for p in (os.path.join(b, "storage", "demonware", title, "pub")
                                          for b in (master, user_plut)) if os.path.isdir(p)), None)
        dw = os.path.join(root, "storage", "demonware", title or "")
        # The game makes an empty pub when it has none. A link lets it see the online data.
        if pub:
            os.makedirs(os.path.join(dw, "user"), exist_ok=True)
            if os.path.isdir(os.path.join(dw, "pub")) and not os.path.islink(os.path.join(dw, "pub")):
                shutil.rmtree(os.path.join(dw, "pub"))
            if not os.path.lexists(os.path.join(dw, "pub")):
                os.symlink(pub, os.path.join(dw, "pub"))
    top = os.path.realpath(LAN_ROOT) + os.sep
    for rel, src in files.items():
        dst = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.realpath(os.path.dirname(dst)).startswith(top):
            raise RuntimeError(f"offline file would land outside {LAN_ROOT}: {dst}")
        if src and os.path.lexists(dst):
            os.remove(dst)
        if src:
            shutil.copyfile(src, dst)


def _lan_assets(mode: str, role: str) -> dict:
    base = os.path.join(LAN_ASSETS, mode, role)
    return {os.path.relpath(os.path.join(dp, f), base): os.path.join(dp, f)
            for dp, _, fns in os.walk(base) for f in fns}


def _lan_download(dst: str, url: str, digest, prog):
    if not url.endswith(".zip"):
        download(url, dst, digest=digest)
        return
    import tempfile, zipfile
    with tempfile.TemporaryDirectory() as tmp:
        z = os.path.join(tmp, "dl.zip")
        download(url, z, digest=digest)
        with zipfile.ZipFile(z) as zf:
            name = next(n for n in zf.namelist() if os.path.basename(n) == os.path.basename(dst))
            with zf.open(name) as fi, open(dst, "wb") as fo:
                shutil.copyfileobj(fi, fo)


def _lan_disk_check(prog):
    sizes = []
    for dp, _, fns in os.walk(LAN_ROOT):
        for f in fns:
            st = os.lstat(os.path.join(dp, f))
            if stat.S_ISREG(st.st_mode) and st.st_nlink == 1:
                sizes.append((st.st_size, os.path.relpath(os.path.join(dp, f), LAN_ROOT)))
    total = sum(n for n, _ in sizes)
    if total > _LAN_DISK_WARN:
        big = ", ".join(f"{p} ({n >> 20} MB)" for n, p in sorted(sizes, reverse=True)[:5])
        _log.warning("offline LAN folders hold %d MB of copies: %s", total >> 20, big)
        prog(f"  ⚠ Offline folders use {total >> 20} MB of copied files: {big}")


def lan_dirs(mode: str):
    return os.path.join(LAN_ROOT, mode, "server"), os.path.join(LAN_ROOT, mode, "client")


def refresh_lan(mode: str, prog=lambda m: None):
    """Rebuild the server and game copies from the online folder saved at install.
    Runs at every offline launch (prelaunch.py lan <mode>), so mods added and Plutonium
    files updated since the install show up offline too."""
    with open(os.path.join(LAN_ROOT, mode, "source.json")) as f:
        user_plut = json.load(f)["user_plut"]
    store = _STORAGE_SUBDIRS[mode]
    server, client = lan_dirs(mode)
    master = get_dedicated_plut_dir()
    # Real files from older builds stay in the copies, so drop the ones we stopped shipping.
    for rel in _LAN_STALE.get(mode, ()):
        if os.path.isfile(os.path.join(server, rel)):
            os.remove(os.path.join(server, rel))
    if mode in LAN_KEYS:
        dl = {rel: None for rel, _, _ in LAN_DOWNLOADS.get(mode, ())}
        _lan_tree(server, user_plut, master, store, {**dl, **_lan_assets(mode, "server")}, False)
    _lan_tree(client, user_plut, master, store, _lan_assets(mode, "client"), True)
    _lan_disk_check(prog)
    prog(f"  ✓ Offline server folders ready ({mode})")


def setup_lan(game: dict, game_key: str, user_plut: str, source: str, prog):
    """Set up offline play for a Plutonium game when Offline Mode is on: the offline
    prefixes and the game's offline Plutonium copy, plus the local server for
    t4mp / t5mp / t6mp / iw5mp. user_plut is the game's online Plutonium folder (OLED: its
    compatdata prefix, LCD: Heroic's). MW3 DS shares MW3's offline folders."""
    import config as _cfg
    if game_key not in OLED_LAN_WRAPPER_NAMES or not _cfg.get_offline_mode():
        return
    mode = _plut_key(game_key)
    try:
        _lan_prefixes(prog)
        # Offline BO2 stats and settings landed online through the old shared players/ (2026-10-08)
        leak = os.path.join(user_plut, "storage", "t6", "players", "mods", "deckops_offline")
        if mode == "t6mp" and os.path.isdir(leak) and not os.path.islink(leak):
            shutil.rmtree(leak)
        os.makedirs(os.path.join(LAN_ROOT, mode), exist_ok=True)
        with open(os.path.join(LAN_ROOT, mode, "source.json"), "w") as f:
            json.dump({"user_plut": user_plut}, f)
        # Folders first, so every download lands in a real folder of ours.
        refresh_lan(mode, prog)
        server, _ = lan_dirs(mode)
        for rel, url, digest in LAN_DOWNLOADS.get(mode, ()) if mode in LAN_KEYS else ():
            dst = os.path.join(server, rel)
            if not os.path.isfile(dst):
                prog(f"  Downloading {os.path.basename(rel)}...")
                _lan_download(dst, url, digest, prog)
        # MW3 server config + mode recipes live in the game's admin/ (sv_config).
        # Never overwrite: the user's own dedicated server may keep files there.
        admin = os.path.join(LAN_ASSETS, mode, "admin")
        if os.path.isdir(admin):
            dst_dir = os.path.join(plut_game_dir(game_key, game["install_dir"], source), "admin")
            os.makedirs(dst_dir, exist_ok=True)
            for n in os.listdir(admin):
                # deckops_lan.cfg is ours alone, so it is kept up to date (bot count 2026-10-09)
                if n == "deckops_lan.cfg" or not os.path.exists(os.path.join(dst_dir, n)):
                    shutil.copyfile(os.path.join(admin, n), os.path.join(dst_dir, n))
    except Exception as ex:
        _log.warning("offline setup failed for %s", game_key, exc_info=True)
        prog(f"  ⚠ Offline setup failed: {ex}")


def _lan_prefixes(prog):
    """Set up the offline game prefix and the Offline launcher's prefix (the server's)
    from GE-Proton's default prefix, like a game prefix on first install."""
    import config as _cfg
    from ge_proton import ensure_prefix_deps
    from steam_common import STEAM_ROOT
    from wrapper import get_proton_path
    for p in (LAN_PREFIX, LAN_SERVER_PREFIX):
        if not os.path.isdir(os.path.join(p, "pfx", "drive_c", "windows")):
            os.makedirs(p, exist_ok=True)
            ensure_prefix_deps(_cfg.get_ge_proton_version(), p, prog,
                               proton_path=get_proton_path(STEAM_ROOT), steam_root=STEAM_ROOT)


def lan_runtime() -> tuple:
    """(Steam Linux Runtime dir the GE-Proton asks for, Steam libraries outside home).
    The game runs inside that runtime like Steam's own launches. The container only
    sees home unless the other libraries are mounted. ("", ...) if not found."""
    import re
    import config as _cfg
    from detect_games import parse_library_folders, find_steam_root
    sr = _cfg.load().get("steam_root") or find_steam_root()
    libs = [os.path.join(l, "steamapps") for l in parse_library_folders(sr)]
    home = os.path.realpath(os.path.expanduser("~")) + os.sep
    mounts = ":".join(l for l in libs if not os.path.realpath(l).startswith(home))
    try:
        with open(os.path.join(sr, "compatibilitytools.d", _cfg.get_ge_proton_version(), "toolmanifest.vdf")) as f:
            tool = re.search(r'"require_tool_appid"\s*"(\d+)"', f.read()).group(1)
    except (OSError, AttributeError, TypeError):
        return "", mounts
    for lib in libs:
        try:
            with open(os.path.join(lib, f"appmanifest_{tool}.acf")) as f:
                d = os.path.join(lib, "common", re.search(r'"installdir"\s*"([^"]+)"', f.read()).group(1))
        except (OSError, AttributeError):
            continue
        if os.path.isfile(os.path.join(d, "_v2-entry-point")):
            return d, mounts
    return "", mounts


def _plut_compat(game_key: str, game: dict, source: str, steam_root: str) -> str:
    """The game's Proton prefix, picked like the install and update flows do."""
    import config as _cfg
    from wrapper import find_compatdata
    appid = str(GAME_META[game_key][0])
    compat = ""
    if source == "own":
        compat = game.get("compatdata_path", "")
        if not compat and not _cfg.is_lcd():
            from shortcut import own_plut_prefix
            compat = own_plut_prefix(game_key, game)
    if not compat:
        compat = find_compatdata(steam_root, appid, game_install_dir=game.get("install_dir"))
    if not compat and game.get("install_dir"):
        compat = os.path.join(os.path.dirname(os.path.dirname(game["install_dir"])), "compatdata", appid)
    return compat


def apply_offline_mode(on: bool, steam_root: str, prog=lambda pct, msg: None):
    """Add or remove Offline Mode for every set-up Plutonium game: rerun the
    Plutonium setup (the offline parts follow config offline_mode), then set up
    the offline launcher. The Plutonium bootstrapper does not run. Steam must be
    closed, because launch menu entries and shortcuts.vdf get rewritten."""
    import config as _cfg
    from detect_games import find_all_games
    from wrapper import get_proton_path
    import shortcut
    _cfg.set_offline_mode(on)
    if not on:
        remove_lan(lambda m: prog(5, m))
        shortcut.remove_launcher_shortcut(lambda m: prog(8, m))
        for p in (LAN_SERVER_PREFIX, LAN_PREFIX):
            if os.path.isdir(p):
                shutil.rmtree(p)
    found = find_all_games(steam_root)
    setup = _cfg.get_setup_games()
    games = {k: found[k] for k, e in setup.items()
             if e.get("client") == "plutonium" and k in GAME_META and k in found}
    proton = get_proton_path(steam_root)
    step = 80 // max(len(games), 1)
    for i, (k, g) in enumerate(games.items()):
        src = setup[k].get("source", "steam")
        base = 10 + i * step
        prog(base, f"{g.get('name', k)}...")
        try:
            install_plutonium(g, k, steam_root, proton, _plut_compat(k, g, src, steam_root),
                              on_progress=lambda pct, msg, b=base: prog(b + pct * step // 100, msg),
                              installed_games=games, source=src)
        except Exception as ex:
            _log.warning("offline mode: %s failed", k, exc_info=True)
            prog(base, f"  ⚠ {k}: {ex}")
    if on and games:
        # Configs last, like the install's finalize phase. game_config also fills the
        # offline copies (resolution, FOV, sensitivity, name) now that they exist.
        from game_config import apply_game_configs
        apply_game_configs(selected_keys=list(games), installed_games=games, steam_root=steam_root,
                           deck_model=_cfg.get_deck_model() or "oled", on_progress=lambda m: prog(93, m))
        shortcut.create_launcher_shortcut(on_progress=lambda m: prog(95, m))


def remove_lan(prog=lambda m: None):
    """Remove the offline folders after Offline Mode is turned off. rmtree never
    follows the links into online folders."""
    for mode in {_plut_key(k) for k in LAN_KEYS}:
        subprocess.run(["systemctl", "--user", "stop", f"deckops-lan-{mode}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.isdir(LAN_ROOT):
        shutil.rmtree(LAN_ROOT)
    prog("  ✓ Offline server folders removed")


def install_plutonium(game: dict, game_key: str, steam_root: str,
                      proton_path: str, compatdata_path: str,
                      on_progress=None, installed_games: dict = None,
                      source: str = "steam"):
    """
    Full install flow for a single Plutonium game.

    LCD Decks go to plutonium_lcd.py early on. Everything after that
    covers OLED and Other (non-Deck) devices.

    Assumes the user already logged in and closed Plutonium through
    launch_bootstrapper(), and is_plutonium_ready() returned True.

    game:            entry from detect_games.find_installed_games()
    game_key:        one of t4sp, t4mp, t5sp, t5mp, t6zm, t6mp, iw5mp, iw5mp_ds
    steam_root:      path to the Steam root
    proton_path:     path to the proton executable
    compatdata_path: path to this game's compatdata prefix
    on_progress:     optional callback(percent: int, status: str)
    """
    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    # Fall back to a single-game dict if the caller gives no installed_games.
    # The full dict is better, so sibling keys get their paths too.
    if installed_games is None:
        installed_games = {game_key: game}

    # --- LCD dispatch
    # LCD Decks use Heroic Games Launcher with one shared Wine prefix for
    # all Plutonium games. Everything from the bootstrapper download to the
    # per-game shortcuts lives in plutonium_lcd.py. OLED and Other devices
    # continue below and launch Plutonium directly.
    import config as _cfg_lcd
    if _cfg_lcd.is_lcd():
        from plutonium_lcd import install_plutonium_lcd, get_shared_plut_dir
        # Offline runs from its own prefix and Plutonium copy, not through Heroic
        # (Heroic is for online). First, so the offline script finds its prefix.
        setup_lan(game, game_key, get_shared_plut_dir(), source, lambda msg: prog(5, msg))
        return install_plutonium_lcd(
            game, game_key, installed_games,
            on_progress=on_progress,
            steam_root=steam_root,
            proton_path=proton_path,
            compatdata_path=compatdata_path,
            source=source,
        )

    src_plut_dir  = get_dedicated_plut_dir()

    # OLED / Other from here (LCD returned above). Plutonium files go into
    # the game's Steam compatdata prefix, because OLED/Other launch the game
    # through a bash wrapper that Steam runs in that same prefix. The
    # caller's compatdata_path comes from find_compatdata(), which handles
    # SD cards.
    dest_plut_dir = os.path.join(
        compatdata_path, "pfx", "drive_c", "users", "steamuser",
        "AppData", "Local", "Plutonium",
    )

    prog(10, f"Copying Plutonium into prefix for {game['name']}...")
    _copy_plut_to_prefix(
        src_plut_dir, dest_plut_dir, game_key=game_key,
        on_progress=lambda msg: prog(40, msg),
    )
    _link_to_master(src_plut_dir, dest_plut_dir, lambda msg: prog(45, msg))

    prog(60, "Writing game path to config.json...")
    # Pass every key that shares this appid so config.json has all paths for this
    # prefix. installed_games must hold every installed game, not only this one,
    # so sibling keys (e.g. t4sp + t4mp on appid 10090) get their paths written too.
    appid = GAME_META[game_key][0]
    keys_for_appid = [k for k, v in GAME_META.items() if v[0] == appid]
    _write_config(dest_plut_dir, keys_for_appid, installed_games)

    # Apply DeckOps game configs (resolution, FOV, sensitivity, name) to
    # the game's prefix before anything copies it to the launcher prefix.
    # Every prefix that gets a copy of storage/ then has the tuned configs
    # without a separate mirror step.
    _apply_launcher_game_configs(dest_plut_dir, game_key,
                                  on_progress=lambda msg: prog(62, msg))

    # DeckOps client-side menu mod (e.g. mainlobby.lua for T6 MP).
    # OLED / Other only. LCD does its own in plutonium_lcd.py.
    prog(65, "Installing menu mod...")
    _install_menu_mod(dest_plut_dir, game_key,
                      on_progress=lambda msg: prog(67, msg))
    setup_lan(game, game_key, dest_plut_dir, source, lambda msg: prog(68, msg))
    import config as _cfg_off
    offline = _cfg_off.get_offline_mode()
    if not offline:
        remove_offline_files(game, game_key)

    # --- OLED / Other launch files
    # LCD went to plutonium_lcd.py at the top. Here OLED/Other games get
    # their wrapper files and metadata.
    wrapper_path = None
    if source == "own":
        # OLED own games: standalone wrapper
        prog(80, "Writing launcher wrapper...")
        wrapper_path = _write_oled_own_wrapper(
            game, game_key, steam_root, proton_path,
            compatdata_path, dest_plut_dir,
        )

        prog(85, "Writing offline LAN wrapper...")
        # Offline -lan script next to the game files. It leaves the online
        # wrapper above alone. DeckOps_Offline.exe reads lan_wrapper_path
        # from config and runs this script with bash for offline play.
        lan_wrapper_path = _write_offline_wrapper(game, game_key, "own") if offline else None

        prog(95, "Saving metadata...")
        _write_metadata(game["install_dir"], {
            "game_key":    game_key,
            "plut_dir":    dest_plut_dir,
        })
        import config as _cfg_own
        _cfg_own.mark_game_setup(
            game_key, "plutonium", source="own",
            wrapper_path=wrapper_path,
            lan_wrapper_path=lan_wrapper_path,
        )
    else:
        wrapper_exe = os.path.join(game["install_dir"], GAME_META[game_key][2])
        if game_key not in STEAM_MENU_EXES:
            # Fallback for a key without a menu mapping: replace the exe
            prog(80, "Writing launcher wrapper...")
            _write_wrapper(game, game_key, steam_root, proton_path,
                           compatdata_path, dest_plut_dir)

        prog(85, "Writing offline LAN wrapper...")
        # Offline -lan script next to the game files. DeckOps_Offline.exe
        # reads lan_wrapper_path from config and runs this script with bash
        # for offline play.
        lan_wrapper_path = _write_offline_wrapper(game, game_key, "steam") if offline else None

        if game_key in STEAM_MENU_EXES:
            prog(88, "Adding Plutonium to the Steam launch menu...")
            wrapper_exe = _setup_steam_menu(
                game, game_key, steam_root, proton_path, compatdata_path,
                dest_plut_dir, lan_wrapper_path, prog,
            ) or wrapper_exe

        prog(95, "Saving metadata...")
        _write_metadata(game["install_dir"], {
            "game_key":    game_key,
            "plut_dir":    dest_plut_dir,
            "wrapper_exe": wrapper_exe,
        })
        import config as _cfg_steam
        _cfg_steam.mark_game_setup(
            game_key, "plutonium", source="steam",
            lan_wrapper_path=lan_wrapper_path,
        )

    prog(100, f"Plutonium ready for {game['name']}!")
    return wrapper_path
