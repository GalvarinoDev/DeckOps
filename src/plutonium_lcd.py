"""
plutonium_lcd.py - LCD Plutonium install path (Heroic Games Launcher)

LCD Steam Decks can't launch Plutonium through Steam's Proton runtime
due to LCD compatibility issues. Heroic's Flatpak version doesn't have
this problem, so LCD users route their Plutonium games through Heroic.

This module owns the full LCD install flow. It is the LCD counterpart
to plutonium.py: on LCD, install_plutonium hands off to
install_plutonium_lcd at the top of the function.

Architecture (Shape A, shared Heroic default prefix):
  1. Install Heroic via Flatpak if not present.
  2. Download plutonium.exe into ~/Games/Heroic/deckops_plutonium/.
  3. Write a one-off "DeckOps Plutonium Setup" sideload entry into Heroic's
     library.json pointing at that exe. Its winePrefix is Heroic's default
     shared prefix at ~/Games/Heroic/Prefixes/default.
  4. Launch that sideload entry through Heroic via
     `flatpak run com.heroicgameslauncher.hgl --no-gui ... heroic://launch?...`.
     Heroic creates the shared prefix using its own GE-Proton runtime and
     runs Plutonium. The user logs in inside the same prefix that later
     launches the games, so the login state never drifts.
  5. After login, write Plutonium's config.json inside the shared prefix
     with all selected games' install paths. All Plutonium games share one
     config, one client and one login.
  6. For each selected game, write a per-game sideload entry with
     launcherArgs="plutonium://play/<key>" and winePrefix pointed at the
     same shared prefix. Steam games (launch options) and own games (Steam
     shortcut) both start through cache_cleanup.py, which launches the
     Heroic entry.

OLED Decks and other devices do not use this module. plutonium.py runs
their games directly through Steam's Proton runtime and a bash wrapper
per game.
"""

import binascii
import json
import os
import re
import shutil
import stat
import subprocess
import time

from identity import VENV_PYTHON
from depot_downgrade import plut_game_dir
from log import get_logger
from net import DownloadError, download

_log = get_logger(__name__)


from shortcut import add_shortcut
from steam_common import calc_shortcut_appid as _calc_shortcut_appid, heroic_app_name as _heroic_app_name


# --- Heroic Flatpak paths
# The Flatpak version keeps its config under ~/.var/app/, not ~/.config/

HEROIC_FLATPAK_ID = "com.heroicgameslauncher.hgl"

HEROIC_CONFIG_DIR = os.path.expanduser(
    f"~/.var/app/{HEROIC_FLATPAK_ID}/config/heroic"
)
HEROIC_LIBRARY_JSON = os.path.join(
    HEROIC_CONFIG_DIR, "sideload_apps", "library.json"
)
HEROIC_GAMES_CONFIG_DIR = os.path.join(HEROIC_CONFIG_DIR, "GamesConfig")
HEROIC_ICONS_DIR = os.path.join(HEROIC_CONFIG_DIR, "icons")


# --- Shape A: shared default Heroic prefix
# Heroic Flatpak creates ~/Games/Heroic/ on first launch and uses
# ~/Games/Heroic/Prefixes/default as the shared Wine prefix for sideloaded
# games. We use that prefix directly so Heroic manages the Wine state
# itself and our auth tokens don't drift between prefixes.
#
# The path is hardcoded because every Steam Deck Heroic install uses it by
# default and DeckOps doesn't change that setting. If a user sets another
# default prefix, this would need to read `defaultWinePrefix` from
# ~/.var/app/com.heroicgameslauncher.hgl/config/heroic/config.json.

HEROIC_GAMES_DIR           = os.path.expanduser("~/Games/Heroic")
HEROIC_DEFAULT_WINE_PREFIX = os.path.join(HEROIC_GAMES_DIR, "Prefixes", "default")
DECKOPS_PLUT_DIR           = os.path.join(HEROIC_GAMES_DIR, "deckops_plutonium")

PLUT_BOOTSTRAPPER_URL = "https://cdn.plutonium.pw/updater/plutonium.exe"
_PLUT_ARCHIVE_FALLBACK_URL = "https://archive.org/download/plutonium_202605/plutonium.exe"

# Fixed sideload app_name for the one-off login entry. Not hashed, so
# testers can spot it in Heroic's library when they debug.
BOOTSTRAP_APP_NAME = "do_plut_bootstrap"
BOOTSTRAP_TITLE    = "DeckOps Plutonium Setup"

# Game key -> the config.json field Plutonium reads for that game's install
# folder. Copied from plutonium.GAME_META so this module doesn't import
# plutonium.py for it.
PLUT_CONFIG_KEYS = {
    "t4sp":  "t4Path",
    "t4mp":  "t4Path",
    "t5sp":  "t5Path",
    "t5mp":  "t5Path",
    "t6zm":  "t6Path",
    "t6mp":  "t6Path",
    "iw5mp": "iw5Path",
    "iw5mp_ds": "iw5Path",
}
PLUT_GAME_KEYS = set(PLUT_CONFIG_KEYS.keys())

# Game key -> (appid, stock exe name), copied from plutonium.GAME_META. The
# appid drives launch options and shader cache cleanup here, and
# game_config.py reads the exe names.
PLUT_GAME_EXES = {
    "t4sp":  (10090,  "CoDWaW.exe"),
    "t4mp":  (10090,  "CoDWaWmp.exe"),
    "t5sp":  (42700,  "BlackOps.exe"),
    "t5mp":  (42710,  "BlackOpsMP.exe"),
    "t6zm":  (212910, "t6zm.exe"),
    "t6mp":  (202990, "t6mp.exe"),
    "iw5mp": (42690,  "iw5mp.exe"),
    "iw5mp_ds": (42750, "iw5mp_server.exe"),
}

# Standalone wrapper exe names for LCD own games. These are new files in
# the game folder, and the original exe stays untouched. shortcut.py points
# the non-Steam shortcut at these.
LCD_OWN_WRAPPER_EXES = {
    "t4sp":  "t4plutsp.exe",
    "t4mp":  "t4plutmp.exe",
    "t5sp":  "t5plutsp.exe",
    "t5mp":  "t5plutmp.exe",
    "t6mp":  "t6plutmp.exe",
    "t6zm":  "t6plutzm.exe",
    "iw5mp": "iw5plutmp.exe",
}

# Sidecar -lan wrapper script names for LCD offline mode (DeckOps_Offline.exe).
# Each game key needs its own filename. Older versions shared names between
# SP/MP and MP/ZM pairs, so whichever installed last overwrote the other's
# wrapper with the wrong game_key.
LCD_LAN_WRAPPER_NAMES = {
    "t4sp":  "t4plut_lan_sp.sh",
    "t4mp":  "t4plut_lan_mp.sh",
    "t5sp":  "t5plut_lan_sp.sh",
    "t5mp":  "t5plut_lan_mp.sh",
    "t6mp":  "t6plut_lan_mp.sh",
    "t6zm":  "t6plut_lan_zm.sh",
    "iw5mp": "iw5plut_lan.sh",
    "iw5mp_ds": "iw5plut_lan.sh",
}

# DeckOps client-side menu mods packaged as .iwd files (renamed .zip).
# Bundled with the repo at assets/mods/ and copied locally into Plutonium's
# storage/ path inside the shared Heroic prefix. The game loads them on
# launch, and they replace the default main menu.
#
# T6 uses one .iwd (deckops_bo2_menu.iwd) for both MP and ZM. Its Lua has
# both PopulateButtons_Multiplayer and PopulateButtons_Zombie, and the
# engine's CoD.isZombie check picks the right button set at runtime. t6mp
# and t6zm share the same source and destination, so installing both just
# copies the same file twice.
_LCD_HERE = os.path.dirname(os.path.abspath(__file__))
MENU_MOD_ASSETS_DIR = os.path.join(os.path.dirname(_LCD_HERE), "assets", "mods")
MENU_MOD_FILES = {
    "t6mp":  ("t6/deckops_bo2_menu.iwd", "storage/t6/raw/deckops_bo2_menu.iwd"),
    "t6zm":  ("t6/deckops_bo2_menu.iwd", "storage/t6/raw/deckops_bo2_menu.iwd"),
}


# --- Steam paths (same as shortcut.py)


# --- Plutonium game definitions for Heroic
# Titles and artwork URLs match shortcut.py OWN_SHORTCUTS so LCD users see
# the same game names as OLED users. The shortcut appid (from quoted_exe +
# title) differs between LCD and OLED because the exe path differs
# (flatpak vs wrapper script), but the visible name is the same.

HEROIC_PLUT_GAMES = {
    "t4sp": {
        "title":          "Call of Duty: World at War",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/10090/2bfb85222af4a01842baa5c3a16a080eb27ac6c3.jpg",
        "grid_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/10090/library_600x900_2x.jpg",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/10090/header.jpg",
        "hero_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/10090/library_hero_2x.jpg",
        "logo_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/10090/logo_2x.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "t4mp": {
        "title":          "Call of Duty: World at War - Multiplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn2.steamgriddb.com/icon/854d6fae5ee42911677c739ee1734486.png",
        "grid_url":       "https://cdn2.steamgriddb.com/grid/bb933c55afc6987ae406e48ff58786d6.png",
        "wide_url":       "https://cdn2.steamgriddb.com/thumb/a6a0076c7e1907a4555b17cc2a6ebc85.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero_thumb/e369853df766fa44e1ed0ff613f563bd.jpg",
        "logo_url":       "https://cdn2.steamgriddb.com/logo_thumb/0a32bfcf5c87aa42d2a0367c1f6bb17c.png",
        "icon_ext": "png", "grid_ext": "png", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "t5sp": {
        "title":          "Call of Duty: Black Ops",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/42700/ea744d59efded3feaeebcafed224be9eadde90ac.jpg",
        "grid_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/42700/library_600x900_2x.jpg",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/42700/header.jpg",
        "hero_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/42700/library_hero.jpg",
        "logo_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/42700/logo_2x.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "t5mp": {
        "title":          "Call of Duty: Black Ops - Multiplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/42710/d595fb4b01201cade09e1232f2c41c0866840628.jpg",
        "grid_url":       "https://cdn2.steamgriddb.com/thumb/978f9d25644371a4c4b8df8c994cd880.png",
        "wide_url":       "https://cdn2.steamgriddb.com/thumb/a6330e9317a50ccf2d79c295dd18046f.png",
        "hero_url":       "https://cdn2.steamgriddb.com/hero_thumb/dc82d632c9fcecb0778afbc7924494a6.png",
        "logo_url":       "https://cdn2.steamgriddb.com/logo_thumb/dfb84a11f431c62436cfb760e30a34fe.png",
        "icon_ext": "jpg", "grid_ext": "png", "wide_ext": "png", "hero_ext": "png", "logo_ext": "png",
    },
    "t6mp": {
        "title":          "Call of Duty: Black Ops II - Multiplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn2.steamgriddb.com/icon_thumb/715eb56d3f3b71792e230102d1da496d.png",
        "grid_url":       "https://cdn2.steamgriddb.com/thumb/7d3695ac5fbf55fb65ea261dd3a8577c.jpg",
        "wide_url":       "https://cdn2.steamgriddb.com/thumb/d841ee63e07b28f94920b81d2e4c21c9.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero_thumb/731c83db8d2ff01bdc000083fd3c3740.png",
        "logo_url":       "https://cdn2.steamgriddb.com/logo_thumb/6271faadeedd7626d661856b7a004e27.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "png", "logo_ext": "png",
    },
    "t6zm": {
        "title":          "Call of Duty: Black Ops II - Zombies",
        "template_type":  "standard",
        "icon_url":       "https://cdn2.steamgriddb.com/icon_thumb/743c11a9f3cb65cda4994bbdfb66c398.png",
        "grid_url":       "https://cdn2.steamgriddb.com/thumb/3d9ffc992e48d2aeb4b06f05471f619d.jpg",
        "wide_url":       "https://cdn2.steamgriddb.com/thumb/b87c4d009662bc436961d8f753a8de78.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero_thumb/e5e63da79fcd2bebbd7cb8bf1c1d0274.jpg",
        "logo_url":       "https://cdn2.steamgriddb.com/logo_thumb/79514e888b8f2acacc68738d0cbb803e.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "iw5mp": {
        "title":          "Call of Duty: Modern Warfare 3 (2011) - Multiplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn2.steamgriddb.com/icon_thumb/67b48cc32ab9f04633bd50656a4a26fc.png",
        "grid_url":       "https://cdn2.steamgriddb.com/thumb/54726e7600c9c297610f6ed9d7d19ca7.jpg",
        "wide_url":       "https://cdn2.steamgriddb.com/thumb/ce65f40e3a20ad19fe352c52ce3bcf51.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero_thumb/51770b1e6f66ba5d45e58a76e6a73dc2.jpg",
        "logo_url":       "https://cdn2.steamgriddb.com/logo_thumb/4a64d913220fca4c33c140c6952688a8.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "iw5mp_ds": {
        "title":          "Call of Duty: Modern Warfare 3 (2011) - Multiplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn2.steamgriddb.com/icon_thumb/67b48cc32ab9f04633bd50656a4a26fc.png",
        "grid_url":       "https://cdn2.steamgriddb.com/thumb/54726e7600c9c297610f6ed9d7d19ca7.jpg",
        "wide_url":       "https://cdn2.steamgriddb.com/thumb/ce65f40e3a20ad19fe352c52ce3bcf51.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero_thumb/51770b1e6f66ba5d45e58a76e6a73dc2.jpg",
        "logo_url":       "https://cdn2.steamgriddb.com/logo_thumb/4a64d913220fca4c33c140c6952688a8.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
}


# --- Shader cache cleanup (LCD only)
# LCD Plutonium games launch through cache_cleanup.py → flatpak → Heroic →
# Proton. Steam's shader cache for these appids only records Fossilize
# activity from the Python/flatpak launcher, not from the game, which runs
# inside Heroic's Proton runtime. The cache grows on every launch, does
# nothing, and can break launches if it gets corrupt. Deleting all of it
# is safe because Steam recreates the folder on the next launch.

SHADERCACHE_DIR = os.path.expanduser(
    "~/.local/share/Steam/steamapps/shadercache"
)

def _nuke_shader_cache(game_key: str, source: str, on_progress=None):
    """
    Delete the entire shadercache/<appid>/ directory for an LCD game.

    Always deletes the Steam appid cache. For own games it also deletes the
    shortcut appid cache (the CRC of the exe path + title the non-Steam
    shortcut was created with).
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    # Steam appid cache
    steam_appid = PLUT_GAME_EXES.get(game_key)
    if steam_appid:
        appid_str = str(steam_appid[0])
        cache_dir = os.path.join(SHADERCACHE_DIR, appid_str)
        if os.path.isdir(cache_dir):
            try:
                shutil.rmtree(cache_dir)
                prog(f"  Nuked shader cache for Steam appid {appid_str}")
            except OSError as ex:
                prog(f"  Could not remove shader cache {appid_str}: {ex}")

    # Own game shortcut appid cache
    if source == "own" and game_key in HEROIC_PLUT_GAMES:
        title = HEROIC_PLUT_GAMES[game_key]["title"]
        appid_exe = '"/usr/bin/flatpak"'
        shortcut_appid = str(_calc_shortcut_appid(appid_exe, title))
        cache_dir = os.path.join(SHADERCACHE_DIR, shortcut_appid)
        if os.path.isdir(cache_dir):
            try:
                shutil.rmtree(cache_dir)
                prog(f"  Nuked shader cache for shortcut appid {shortcut_appid}")
            except OSError as ex:
                prog(f"  Could not remove shader cache {shortcut_appid}: {ex}")


# --- Heroic install/detection

def is_heroic_installed() -> bool:
    """Check if Heroic Games Launcher Flatpak is installed."""
    try:
        result = subprocess.run(
            ["flatpak", "info", HEROIC_FLATPAK_ID],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _log.debug("heroic install check failed", exc_info=True)
        return False


def _ensure_flathub_remote(on_progress=None):
    """
    Make sure the Flathub remote is set up for the current user.
    SteamOS ships Flathub system-wide, but it can be missing or broken
    after an OS update or manual removal, and on other distros (Bazzite,
    CachyOS). --if-not-exists does nothing when Flathub is already there.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    try:
        result = subprocess.run(
            [
                "flatpak", "remote-add", "--user", "--if-not-exists",
                "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo",
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            prog("Flathub remote verified.")
        else:
            stderr = result.stderr.decode(errors="replace")
            prog(f"Flathub remote setup warning: {stderr[:200]}")
    except FileNotFoundError:
        prog("Flatpak not found - cannot configure Flathub.")
    except subprocess.TimeoutExpired:
        prog("Flathub remote setup timed out.")


def install_heroic(on_progress=None) -> bool:
    """
    Install Heroic Games Launcher via Flatpak from Flathub.
    Returns True if Heroic is available after this call.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if is_heroic_installed():
        prog("HGL already installed.")
        return True

    # Set up the Flathub remote first. It can be missing or broken after an
    # OS update, or on distros other than SteamOS.
    _ensure_flathub_remote(on_progress=on_progress)

    prog("Installing HGL from Flathub...")
    try:
        result = subprocess.run(
            [
                "flatpak", "install", "--user", "--noninteractive",
                "flathub", HEROIC_FLATPAK_ID,
            ],
            capture_output=True,
            timeout=300,
        )
        if result.returncode == 0:
            prog("HGL installed.")
            return True
        else:
            stderr = result.stderr.decode(errors="replace")
            prog(f"HGL install failed: {stderr[:200]}")
            return False
    except FileNotFoundError:
        prog("Flatpak not found - cannot install HGL.")
        return False
    except subprocess.TimeoutExpired:
        prog("HGL install timed out.")
        return False


def _grant_heroic_filesystem_access(paths: list, on_progress=None):
    """
    Grant Heroic's Flatpak sandbox access to the given paths so
    Heroic/Proton can read the game files. Safe to call more than once,
    flatpak override is idempotent.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    for path in paths:
        if not path:
            continue
        try:
            subprocess.run(
                [
                    "flatpak", "override", "--user",
                    HEROIC_FLATPAK_ID,
                    f"--filesystem={path}",
                ],
                capture_output=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            prog(f"  Warning: could not grant HGL access to {path}")

    # Always grant access to the DeckOps data dir and Steam compatibilitytools
    _always_grant = [
        os.path.expanduser("~/.local/share/deckops"),
        os.path.expanduser("~/.local/share/Steam/compatibilitytools.d"),
        os.path.expanduser("~/.local/share/Steam"),
        "/run/media",  # SD card access
    ]
    for path in _always_grant:
        try:
            subprocess.run(
                [
                    "flatpak", "override", "--user",
                    HEROIC_FLATPAK_ID,
                    f"--filesystem={path}",
                ],
                capture_output=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            _log.debug("heroic flatpak operation failed", exc_info=True)


# --- Heroic library.json

def _read_heroic_library() -> dict:
    """Read the Heroic sideload library. Returns the full JSON dict."""
    if not os.path.exists(HEROIC_LIBRARY_JSON):
        return {"games": []}
    try:
        with open(HEROIC_LIBRARY_JSON) as f:
            data = json.load(f)
        if "games" not in data:
            data["games"] = []
        return data
    except (json.JSONDecodeError, IOError):
        return {"games": []}


def _write_heroic_library(data: dict):
    """Write the Heroic sideload library back to disk."""
    os.makedirs(os.path.dirname(HEROIC_LIBRARY_JSON), exist_ok=True)
    with open(HEROIC_LIBRARY_JSON, "w") as f:
        json.dump(data, f, indent="\t")


def _add_heroic_sideload_entry(game_key: str, executable: str,
                                install_dir: str, on_progress=None):
    """
    Add or update a sideload entry in Heroic's library.json.

    executable:  full path to the Plutonium launcher exe inside the prefix
    install_dir: the game's install folder (folder_name in Heroic)
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if game_key not in HEROIC_PLUT_GAMES:
        prog(f"  Unknown game key: {game_key}")
        return

    app_name = _heroic_app_name(game_key)
    game_def = HEROIC_PLUT_GAMES[game_key]
    title = game_def["title"]

    # Sideload entry in the format Heroic expects
    entry = {
        "runner": "sideload",
        "app_name": app_name,
        "title": title,
        "install": {
            "executable": executable,
            "platform": "Windows",
            "is_dlc": False,
        },
        "folder_name": install_dir,
        "art_cover": game_def.get("grid_url", ""),
        "is_installed": True,
        "art_square": game_def.get("grid_url", ""),
        "canRunOffline": True,
        "browserUrl": "",
        "customUserAgent": "",
        "launchFullScreen": False,
    }

    library = _read_heroic_library()

    # Replace existing entry for this app_name, or append
    idx = next(
        (i for i, g in enumerate(library["games"]) if g.get("app_name") == app_name),
        None,
    )
    if idx is not None:
        library["games"][idx] = entry
        prog(f"  Updated HGL entry for {title}")
    else:
        library["games"].append(entry)
        prog(f"  Added HGL entry for {title}")

    _write_heroic_library(library)


# --- Heroic per-game config

def _write_heroic_game_config(game_key: str, ge_proton_version: str,
                               on_progress=None):
    """
    Write the per-game GamesConfig JSON for a Heroic sideload entry:
    GE-Proton, Heroic's shared default prefix, and plain defaults.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    from plutonium import _plut_key
    app_name = _heroic_app_name(game_key)
    config_path = os.path.join(HEROIC_GAMES_CONFIG_DIR, f"{app_name}.json")
    os.makedirs(HEROIC_GAMES_CONFIG_DIR, exist_ok=True)

    # Resolve the GE-Proton binary path
    proton_dir = os.path.expanduser(
        f"~/.local/share/Steam/compatibilitytools.d/{ge_proton_version}"
    )
    proton_bin = os.path.join(proton_dir, "proton")

    # Shape A: every Plutonium game points at Heroic's shared default prefix.
    # The user logs in once in this prefix during the bootstrapper step, and
    # all Plutonium games share that login, Plutonium install and Wine
    # environment.
    prefix_path = HEROIC_DEFAULT_WINE_PREFIX

    config = {
        app_name: {
            "autoInstallDxvk": True,
            "autoInstallDxvkNvapi": True,
            "autoInstallVkd3d": True,
            "preferSystemLibs": False,
            "enableEsync": True,
            "enableMsync": False,
            "enableFsync": True,
            "enableWineWayland": False,
            "enableHDR": False,
            "enableWoW64": False,
            "nvidiaPrime": False,
            "enviromentOptions": [],
            "wrapperOptions": [],
            "showFps": False,
            "useGameMode": True,
            "battlEyeRuntime": True,
            "eacRuntime": True,
            "language": "",
            "beforeLaunchScriptPath": "",
            "afterLaunchScriptPath": "",
            # Pass the Plutonium protocol URL to the launcher exe. Without it
            # the launcher opens its own UI (game picker / login screen)
            # instead of starting the game. The OLED bash wrapper does the
            # same with `plutonium-launcher-win32.exe "plutonium://play/<key>"`.
            "launcherArgs": f'"plutonium://play/{_plut_key(game_key)}"',
            "verboseLogs": False,
            "advertiseAvxForRosetta": False,
            "enableQuickSavesMenu": False,
            "wineVersion": {
                "bin": proton_bin,
                "name": ge_proton_version,
                "type": "proton",
            },
            "winePrefix": prefix_path,
            "wineCrossoverBottle": "",
        },
        "version": "v0",
        "explicit": True,
    }

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    prog(f"  HGL game config written for {game_key}")


# --- LCD Shape A helpers
# Everything below runs the LCD Plutonium install flow. On LCD,
# plutonium.install_plutonium hands off to install_plutonium_lcd at the top
# of the function, so these are the real entry points for LCD.

def get_shared_plut_dir() -> str:
    """
    Return the Plutonium/ folder inside Heroic's shared default prefix.
    The Plutonium client files land here after the bootstrapper login,
    and every LCD Plutonium game reads its config.json from here.
    """
    return os.path.join(
        HEROIC_DEFAULT_WINE_PREFIX,
        "pfx", "drive_c", "users", "steamuser",
        "AppData", "Local", "Plutonium",
    )


def is_plutonium_ready_lcd() -> bool:
    """
    LCD counterpart to plutonium.is_plutonium_ready. True once the user
    has logged in inside the shared Heroic prefix and Plutonium has
    downloaded its client files. Plutonium only creates storage/ after a
    successful login, so that folder is the check.
    """
    storage = os.path.join(get_shared_plut_dir(), "storage")
    if not os.path.isdir(storage):
        return False
    # Must have at least one game subfolder (t4, t5, t6, iw5, demonware)
    try:
        return any(
            os.path.isdir(os.path.join(storage, d))
            for d in os.listdir(storage)
        )
    except OSError:
        _log.debug("operation failed", exc_info=True)
        return False


def _wine_path_lcd(linux_path: str) -> str:
    """Convert a Linux path to Wine Z: drive notation (same as plutonium.py)."""
    return "Z:" + linux_path.replace("/", "\\")


def _write_plutonium_config_lcd(plut_dir: str, selected_keys: list,
                                  installed_games: dict,
                                  on_progress=None):
    """
    Write Plutonium's config.json inside the shared Heroic prefix with
    the install paths for every selected Plutonium game.

    Shape A writes one config.json that lists all selected games' paths
    (t4Path, t5Path, t6Path, iw5Path). Plutonium's Windows client is built
    to hold several games in one install.

    Idempotent, so calling it once per game in the install loop is fine.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    config_path = os.path.join(plut_dir, "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        data = {}
    if not isinstance(data, dict):
        data = {}

    for key in selected_keys:
        if key not in PLUT_CONFIG_KEYS:
            continue
        game = installed_games.get(key)
        if not game:
            continue
        install_dir = game.get("install_dir", "")
        if install_dir:
            # MW3 Steam: point at the downgrade/ subfolder
            install_dir = plut_game_dir(key, install_dir, game.get("source", "steam"))
            data[PLUT_CONFIG_KEYS[key]] = _wine_path_lcd(install_dir)

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)
    prog(f"  Wrote Plutonium config.json with {len(selected_keys)} game path(s)")


def _write_metadata_lcd(install_dir: str, data: dict):
    """
    Write the DeckOps metadata file into a game's install folder.
    Copy of plutonium._write_metadata, so this module doesn't import
    private helpers from plutonium.py.
    """
    if not install_dir:
        return
    path = os.path.join(install_dir, "deckops_plutonium.json")
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except OSError:
        _log.debug("operation failed", exc_info=True)


def _write_lcd_menu_files(game: dict, game_key: str, lan_wrapper_path: str = None):
    """
    Steam games: the files behind the launch menu entries (same names as OLED).
    Online is a placeholder: the launch option hands Steam's command to
    cache_cleanup.py, which launches the Heroic entry instead. Offline (with
    Offline Mode) opens the Offline launcher, which cache_cleanup.py runs.
    """
    from plutonium import STEAM_MENU_EXES, write_offline_menu_file
    online, offline = STEAM_MENU_EXES[game_key]
    with open(os.path.join(game["install_dir"], online), "w") as f:
        f.write("#!/bin/bash\n# DeckOps (LCD): cache_cleanup.py launches this entry through Heroic.\n")
    if lan_wrapper_path:
        write_offline_menu_file(os.path.join(game["install_dir"], offline))


def _install_menu_mod_lcd(plut_dir: str, game_key: str, on_progress=None):
    """
    Install the DeckOps menu mod for the given game key.

    LCD counterpart to plutonium._install_menu_mod. Copies the bundled
    mod file from assets/mods/ into Plutonium's storage path in the shared
    Heroic prefix, where the Plutonium client loads it on game launch.

    Does nothing for game keys without a menu mod.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if game_key not in MENU_MOD_FILES:
        return

    asset_rel, local_path = MENU_MOD_FILES[game_key]
    src_file = os.path.join(MENU_MOD_ASSETS_DIR, asset_rel)
    dest_file = os.path.join(plut_dir, local_path)

    prog(f"  Installing DeckOps menu mod for {game_key}...")

    if not os.path.isfile(src_file):
        prog(f"  ⚠ Menu mod asset missing: {src_file}")
        return  # Non-fatal, the game still works without the mod

    os.makedirs(os.path.dirname(dest_file), exist_ok=True)

    try:
        shutil.copy2(src_file, dest_file)
        prog(f"  ✓ Menu mod installed ({os.path.getsize(dest_file)} bytes)")
    except OSError as ex:
        prog(f"  ⚠ Menu mod copy failed: {ex}")


def _download_plutonium_exe(dest_dir: str, on_progress=None) -> str:
    """
    Download plutonium.exe into dest_dir and return its full path.
    Tries the Plutonium CDN, then the archive.org mirror, each up to 3 times.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, "plutonium.exe")

    # A non-empty file from an earlier run is taken as good
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        prog("  plutonium.exe already present, skipping download.")
        return dest

    prog("  Downloading Plutonium bootstrapper...")
    try:
        download(PLUT_BOOTSTRAPPER_URL, dest)
        prog(f"  Downloaded plutonium.exe ({os.path.getsize(dest)} bytes)")
        return dest
    except Exception as ex:
        _log.warning("Primary Plutonium download failed after 3 attempts: %s", ex)

    prog("  Falling back to archive.org mirror...")
    # Drop the primary's partial file or download() would resume the
    # mirror's copy on top of it.
    try: os.remove(dest + ".part")
    except OSError: pass
    try:
        download(_PLUT_ARCHIVE_FALLBACK_URL, dest)
    except Exception as ex2:
        raise DownloadError(
            url=_PLUT_ARCHIVE_FALLBACK_URL,
            dest=dest,
            label="Plutonium bootstrapper",
            cause=ex2,
        )
    _log.info("Plutonium bootstrapper downloaded from archive.org fallback")
    prog(f"  Downloaded plutonium.exe from archive.org ({os.path.getsize(dest)} bytes)")
    return dest


def _ensure_bootstrap_sideload_entry(plutonium_exe: str,
                                      ge_proton_version: str,
                                      on_progress=None):
    """
    Write the one-off "DeckOps Plutonium Setup" sideload entry into
    Heroic's library.json and its matching GamesConfig JSON.

    Heroic launches this entry through the heroic:// protocol during the
    bootstrapper step, so the user logs in inside the shared default Wine
    prefix. It stays after login so testers can launch it again from
    Heroic if their token expires.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    # library.json entry
    entry = {
        "runner": "sideload",
        "app_name": BOOTSTRAP_APP_NAME,
        "title": BOOTSTRAP_TITLE,
        "install": {
            "executable": plutonium_exe,
            "platform": "Windows",
            "is_dlc": False,
        },
        "folder_name": os.path.dirname(plutonium_exe),
        "art_cover": "",
        "is_installed": True,
        "art_square": "",
        "canRunOffline": True,
        "browserUrl": "",
        "customUserAgent": "",
        "launchFullScreen": False,
    }

    library = _read_heroic_library()
    idx = next(
        (i for i, g in enumerate(library["games"])
         if g.get("app_name") == BOOTSTRAP_APP_NAME),
        None,
    )
    if idx is not None:
        library["games"][idx] = entry
    else:
        library["games"].append(entry)
    _write_heroic_library(library)
    prog("  Bootstrap sideload entry written.")

    # GamesConfig JSON. Same shape as the per-game configs but without
    # launcherArgs, so plain plutonium.exe opens and the user can log in.
    os.makedirs(HEROIC_GAMES_CONFIG_DIR, exist_ok=True)
    config_path = os.path.join(HEROIC_GAMES_CONFIG_DIR,
                                f"{BOOTSTRAP_APP_NAME}.json")

    proton_dir = os.path.expanduser(
        f"~/.local/share/Steam/compatibilitytools.d/{ge_proton_version}"
    )
    proton_bin = os.path.join(proton_dir, "proton")

    config = {
        BOOTSTRAP_APP_NAME: {
            "autoInstallDxvk": True,
            "autoInstallDxvkNvapi": True,
            "autoInstallVkd3d": True,
            "preferSystemLibs": False,
            "enableEsync": True,
            "enableMsync": False,
            "enableFsync": True,
            "enableWineWayland": False,
            "enableHDR": False,
            "enableWoW64": False,
            "nvidiaPrime": False,
            "enviromentOptions": [],
            "wrapperOptions": [],
            "showFps": False,
            "useGameMode": True,
            "battlEyeRuntime": True,
            "eacRuntime": True,
            "language": "",
            "beforeLaunchScriptPath": "",
            "afterLaunchScriptPath": "",
            "launcherArgs": "",
            "verboseLogs": False,
            "advertiseAvxForRosetta": False,
            "enableQuickSavesMenu": False,
            "wineVersion": {
                "bin": proton_bin,
                "name": ge_proton_version,
                "type": "proton",
            },
            "winePrefix": HEROIC_DEFAULT_WINE_PREFIX,
            "wineCrossoverBottle": "",
        },
        "version": "v0",
        "explicit": True,
    }

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    prog("  Bootstrap GamesConfig written.")


def setup_heroic_game(game_key: str, game: dict, ge_proton_version: str,
                      plut_dir=None, on_progress=None, source: str = "steam"):
    """
    Set up a single Plutonium game to launch through Heroic on LCD.

    install_plutonium_lcd calls this once per selected game. It writes
    the per-game Heroic sideload entry, the per-game GamesConfig
    (winePrefix on the shared default prefix, launcherArgs set to
    plutonium://play/<game_key>), and for own games a non-Steam shortcut
    that launches through cache_cleanup.py.

    Steam games get no shortcut. Their library entry already launches
    through cache_cleanup.py via launch options.

    game_key:          one of t4sp, t4mp, t5sp, t5mp, t6zm, t6mp, iw5mp
    game:              dict with at least install_dir and name
    ge_proton_version: e.g. "GE-Proton10-34"
    plut_dir:          deprecated and ignored. Shape A always uses the
                       shared default Heroic prefix, so the launcher exe
                       path comes from get_shared_plut_dir(). Kept so
                       older call sites don't break.
    source:            "steam" or "own", decides whether a shortcut is made
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if game_key not in HEROIC_PLUT_GAMES:
        prog(f"Unknown game key for HGL: {game_key}")
        return

    install_dir = game.get("install_dir", "")
    game_def = HEROIC_PLUT_GAMES[game_key]

    # MW3 Steam: Heroic must point at the downgrade/ subfolder with the
    # 32-bit depot files, not the 64-bit game root.
    heroic_dir = plut_game_dir(game_key, install_dir, source)

    # Shape A: the launcher exe always lives inside the shared default
    # Heroic prefix. plut_dir (if passed) is ignored for compatibility.
    shared_plut_dir = get_shared_plut_dir()
    launcher_exe = os.path.join(shared_plut_dir, "bin",
                                "plutonium-launcher-win32.exe")

    prog(f"Setting up HGL for {game_def['title']}...")

    # 1. Grant Heroic filesystem access to this game's directory
    _grant_heroic_filesystem_access([install_dir], on_progress=on_progress)

    # 2. Write sideload entry in library.json
    _add_heroic_sideload_entry(game_key, launcher_exe, heroic_dir,
                                on_progress=on_progress)

    # 3. Write per-game config (GE-Proton, shared prefix, launcherArgs)
    _write_heroic_game_config(game_key, ge_proton_version,
                               on_progress=on_progress)

    # 4. Own games: Steam shortcut that launches the Heroic entry
    _create_heroic_steam_shortcut(game_key, on_progress=on_progress,
                                   source=source)

    prog(f"HGL setup complete for {game_def['title']}")


def _set_heroic_minimize_on_launch(on_progress=None):
    """
    Set Heroic's defaultSettings.minimizeOnLaunch to true in its config.json
    so the Heroic window minimizes as soon as it starts a game. Without it,
    Heroic stays on screen for about 10 seconds when a DeckOps LCD shortcut
    fires the heroic:// URL.

    Idempotent and safe on every install. Skips a missing config file and
    changes no setting other than minimizeOnLaunch.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    config_path = os.path.expanduser(
        "~/.var/app/com.heroicgameslauncher.hgl/config/heroic/config.json"
    )

    if not os.path.exists(config_path):
        prog("  HGL config.json not present yet; skipping minimize setting")
        return

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as ex:
        prog(f"  Could not read HGL config.json: {ex}")
        return

    if not isinstance(data, dict):
        prog("  HGL config.json has unexpected shape; skipping")
        return

    default_settings = data.get("defaultSettings")
    if not isinstance(default_settings, dict):
        default_settings = {}
        data["defaultSettings"] = default_settings

    if default_settings.get("minimizeOnLaunch") is True:
        prog("  HGL minimizeOnLaunch already true")
        return

    default_settings["minimizeOnLaunch"] = True

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        prog("  HGL minimizeOnLaunch set to true")
    except OSError as ex:
        prog(f"  Could not write HGL config.json: {ex}")


def launch_bootstrapper_lcd(on_progress=None):
    """
    LCD Plutonium bootstrapper. ui_install.py and ui_manage.py call it
    before any per-game setup. Steps:

      1. Install Heroic Flatpak (does nothing if it is already there).
      2. Grant Heroic access to ~/Games/Heroic and the DeckOps folders.
      3. Download plutonium.exe into ~/Games/Heroic/deckops_plutonium/.
      4. Write a one-off "DeckOps Plutonium Setup" sideload entry for that
         exe, with winePrefix set to Heroic's shared default prefix.
      5. Launch that entry through the heroic:// protocol. Heroic creates
         the shared prefix with its own GE-Proton runtime and runs Plutonium.

    It doesn't wait for Plutonium to exit. The UI already waits on a
    continue button (_plut_event.wait() in ui_install.py) that the user
    presses after closing the Plutonium window. Heroic's Flatpak process may not exit
    cleanly when the game does, and waiting on it could hang.

    Raises on download failure or if Heroic can't be installed.
    """
    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    # 1. Heroic installed
    prog(5, "Ensuring HGL is installed...")
    if not install_heroic(on_progress=lambda m: prog(5, m)):
        raise RuntimeError("HGL could not be installed.")

    # 2. Filesystem access. Heroic usually grants ~/Games itself on first
    #    launch, but override is idempotent, so granting it again costs
    #    nothing.
    prog(10, "Granting HGL filesystem access...")
    _grant_heroic_filesystem_access(
        [HEROIC_GAMES_DIR, DECKOPS_PLUT_DIR],
        on_progress=lambda m: prog(10, m),
    )

    # Make sure ~/Games/Heroic exists (Heroic creates it on first launch,
    # but DeckOps may run before the user has ever opened Heroic).
    os.makedirs(HEROIC_GAMES_DIR, exist_ok=True)

    # 2b. Make Heroic minimize its window when it launches a game, so it
    #     doesn't show for ~10s each time a DeckOps LCD shortcut fires the
    #     heroic:// URL in Game Mode.
    _set_heroic_minimize_on_launch(on_progress=lambda m: prog(12, m))

    # 3. Download plutonium.exe
    prog(15, "Downloading Plutonium bootstrapper...")
    try:
        plutonium_exe = _download_plutonium_exe(
            DECKOPS_PLUT_DIR,
            on_progress=lambda m: prog(15, m),
        )
    except DownloadError:
        raise
    except Exception as ex:
        raise RuntimeError(f"Failed to download plutonium.exe: {ex}")

    # 4. GE-Proton version for the bootstrap GamesConfig wineVersion block,
    #    so Heroic runs the login session with GE-Proton instead of its
    #    bundled UMU default. The per-game entries use the same version.
    try:
        import config as _cfg
        ge_version = _cfg.get_ge_proton_version()
    except Exception:
        ge_version = None
    if not ge_version:
        from ge_proton import _get_local_version
        ge_version = _get_local_version()
    if not ge_version:
        raise RuntimeError("No GE-Proton version found in config or on disk")

    # 5. Write the bootstrap sideload entry + its GamesConfig
    prog(20, "Registering bootstrap entry with HGL...")
    _ensure_bootstrap_sideload_entry(
        plutonium_exe, ge_version,
        on_progress=lambda m: prog(20, m),
    )

    # 6. Launch through the heroic:// protocol and don't wait. The UI waits
    #    for the user's continue click after this returns.
    prog(25, "Launching Plutonium through HGL -- please log in...")
    launch_uri = (
        f"heroic://launch?appName={BOOTSTRAP_APP_NAME}&runner=sideload"
    )
    try:
        subprocess.Popen(
            [
                "flatpak", "run", HEROIC_FLATPAK_ID,
                "--no-gui", "--no-sandbox",
                launch_uri,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise RuntimeError("flatpak command not found -- cannot launch HGL.")
    except Exception as ex:
        raise RuntimeError(f"Failed to launch HGL bootstrapper: {ex}")

    prog(30, "HGL is launching Plutonium. Log in and close when done.")


def install_plutonium_lcd(game: dict, game_key: str,
                           installed_games: dict,
                           on_progress=None,
                           steam_root: str = None,
                           proton_path: str = None,
                           compatdata_path: str = None,
                           source: str = "steam"):
    """
    LCD per-game Plutonium install. plutonium.install_plutonium hands off
    to it at the top of that function on LCD.

    Flow:
      1. Check the shared Heroic prefix is ready (user logged in, storage
         filled). Raises if not.
      2. Write Plutonium's config.json inside the shared prefix with all
         selected Plutonium games' install paths. Idempotent across calls.
     2b. Install the DeckOps menu mod into the shared prefix (T6 MP/ZM).
      3. Register the per-game Heroic sideload entry + GamesConfig, which
         online launches start. Own games also get their Steam shortcut.
      5. Write the offline script (Offline Mode only). Steam games keep
         the stock exe and get Plutonium Online / Offline launch menu
         entries. Own games launch through the shortcuts from step 3.
     5b. Steam games: launch options hand every launch to cache_cleanup.py,
         which starts the matching Heroic entry or the stock game.
      6. Delete the shader cache for this game's appid.
      7. Write the DeckOps metadata file.

    LCD no longer copies Plutonium into per-game compatdata prefixes or
    the offline launcher prefix, which saves hundreds of MB of storage/
    copies per game. Online play uses the single Heroic shared prefix, and
    offline runs from DeckOps' offline copy in its own prefix
    (plutonium.setup_lan).

    game:            entry from detect_games.find_installed_games()
    game_key:        one of t4sp, t4mp, t5sp, t5mp, t6zm, t6mp, iw5mp
    installed_games: full dict of installed games (all clients, not just
                     Plutonium). Used to resolve sibling paths.
    on_progress:     optional callback(percent: int, status: str)
    steam_root:      Steam root (passed on from plutonium.install_plutonium)
    proton_path:     path to the proton executable
    compatdata_path: this game's compatdata prefix
    source:          "steam" or "own". Own games get a shortcut, Steam
                     games get launch menu entries and launch options.
    """
    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    if game_key not in PLUT_GAME_KEYS:
        prog(100, f"Skipping {game_key}: not a Plutonium game.")
        return

    prog(5, f"LCD install for {game.get('name', game_key)}...")

    # 1. Shared Plutonium install + login state present
    shared_plut_dir = get_shared_plut_dir()
    if not is_plutonium_ready_lcd():
        raise RuntimeError(
            "Plutonium shared prefix is not ready. "
            "Expected storage/ inside " + shared_plut_dir + ". "
            "Did the bootstrapper login step complete successfully?"
        )

    # 2. config.json for all selected Plutonium games in the shared Heroic
    #    prefix. Runs once per game in the install loop and writes the same
    #    content each time.
    prog(15, "Writing Plutonium config.json in shared prefix...")
    selected_plut_keys = [
        k for k in installed_games.keys() if k in PLUT_GAME_KEYS
    ]
    _write_plutonium_config_lcd(
        shared_plut_dir, selected_plut_keys, installed_games,
        on_progress=lambda m: prog(20, m),
    )

    # 2b. Install DeckOps menu mod (BO2 menu .iwd).
    #     It goes in the shared Heroic prefix so all LCD games pick it up.
    #     A second copy just overwrites the file.
    prog(22, "Installing menu mod...")
    _install_menu_mod_lcd(shared_plut_dir, game_key,
                          on_progress=lambda m: prog(23, m))

    # 3. Per-game Heroic sideload entry + GamesConfig. Only own games get a
    #    Steam shortcut (_create_heroic_steam_shortcut returns early for
    #    Steam games).
    prog(25, "Registering game with HGL...")
    try:
        import config as _cfg
        ge_version = _cfg.get_ge_proton_version()
    except Exception:
        ge_version = None
    if not ge_version:
        from ge_proton import _get_local_version
        ge_version = _get_local_version()
    if not ge_version:
        raise RuntimeError("No GE-Proton version found in config or on disk")

    setup_heroic_game(
        game_key, game, ge_version,
        plut_dir=shared_plut_dir,
        on_progress=lambda m: prog(30, m),
        source=source,
    )

    # 5. Offline script and launch menu.
    #
    #    LCD no longer copies Plutonium into per-game compatdata prefixes.
    #    Online play reads from the single Heroic shared prefix at
    #    ~/Games/Heroic/Prefixes/default. Offline runs from DeckOps' offline
    #    copy in its own prefix (plutonium.setup_lan), same as OLED.
    #
    #    Migration: older DeckOps versions shared filenames between SP/MP
    #    and MP/ZM pairs (e.g. t4plut_lan.sh for both t4sp and t4mp), so
    #    whichever installed last overwrote the other's wrapper. Remove the
    #    old shared-name wrapper so it doesn't sit next to the new
    #    per-game-key scripts.
    wrapper_path = None
    _OLD_LAN_WRAPPER_NAMES = {
        "t4sp":  "t4plut_lan.sh",
        "t4mp":  "t4plut_lan.sh",
        "t5sp":  "t5plut_lan.sh",
        "t5mp":  "t5plut_lan.sh",
        "t6mp":  "t6plut_lan.sh",
        "t6zm":  "t6plut_lan.sh",
    }
    old_name = _OLD_LAN_WRAPPER_NAMES.get(game_key)
    new_name = LCD_LAN_WRAPPER_NAMES.get(game_key)
    if old_name and new_name and old_name != new_name:
        old_path = os.path.join(game["install_dir"], old_name)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
                prog(55, f"Removed stale shared wrapper: {old_name}")
            except OSError:
                _log.debug("stale wrapper removal failed", exc_info=True)

    lan_wrapper_path = None
    import config as _cfg_off
    from plutonium import remove_offline_files, _write_offline_wrapper
    offline = _cfg_off.get_offline_mode()
    if not offline:
        remove_offline_files(game, game_key)
    if source == "own":
        if offline:
            prog(60, "Own game — writing offline script...")
            lan_wrapper_path = _write_offline_wrapper(game, game_key, "own")
    elif proton_path and steam_root:
        # The game exe stays stock for plain Play; older versions replaced
        # it with an offline wrapper, so put the original back.
        from plutonium import _restore_original_exe, add_steam_menu
        _restore_original_exe(game, game_key)
        # The offline script is what DeckOps_Offline.exe and Plutonium Offline run
        if offline:
            prog(70, "Writing offline script...")
            lan_wrapper_path = _write_offline_wrapper(game, game_key, "steam")
        prog(75, "Adding Plutonium to the Steam launch menu...")
        _write_lcd_menu_files(game, game_key, lan_wrapper_path)
        add_steam_menu(game, game_key, steam_root, prog)
    else:
        prog(60, "Skipping wrapper -- missing proton_path or steam_root")

    # 5b. Launch options on the Steam library entry hand every launch to
    #     cache_cleanup.py, which starts the picked Plutonium entry or runs
    #     the stock game. t4sp and t4mp share appid 10090
    #     and so one launch option, the picked menu entry tells them apart.
    if source == "steam" and steam_root:
        prog(80, "Setting HGL launch options...")
        _set_heroic_steam_launch_options(
            game_key, steam_root, ge_version,
            on_progress=lambda m: prog(82, m),
        )

    # 6. Delete the whole shader cache folder for this game's appid.
    #    LCD games launch through cache_cleanup.py → flatpak → Heroic →
    #    Proton, so Steam's shader cache for these appids only holds data
    #    from the launcher process. Clearing it at install gives a clean
    #    start and stops a corrupt cache from blocking the launch.
    prog(90, "Clearing shader cache...")
    _nuke_shader_cache(
        game_key, source,
        on_progress=lambda m: prog(92, m),
    )

    # 7. Metadata file
    prog(95, "Saving metadata...")
    meta = {
        "game_key":   game_key,
        "plut_dir":   shared_plut_dir,
        "lcd_heroic": True,
    }
    if wrapper_path:
        meta["wrapper_path"] = wrapper_path
    _write_metadata_lcd(game.get("install_dir", ""), meta)

    import config as _cfg_lcd
    _cfg_lcd.mark_game_setup(
        game_key, "plutonium", source=source,
        lan_wrapper_path=lan_wrapper_path,
    )

    prog(100, f"Plutonium ready for {game.get('name', game_key)}!")
    return wrapper_path


def _set_heroic_steam_launch_options(game_key: str, steam_root: str,
                                      ge_proton_version: str,
                                      on_progress=None):
    """
    Set launch options on a Steam library entry so every launch goes
    through cache_cleanup.py with Steam's full command. cache_cleanup.py
    reads the picked launch menu entry from that command: Plutonium
    Online / Offline clean the Fossilize shader cache and launch the
    matching Heroic entry, anything else runs Steam's command (the stock
    game). LCD only.

    cache_cleanup.py handles LD_PRELOAD internally for Steam source.
    Launch options run outside Steam's runtime container, which is why the
    choice is made here: flatpak isn't reachable from inside it.

    Only called for Steam-owned games (not own). WaW SP and MP share appid
    10090 and so one launch option; the picked entry tells them apart.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if game_key not in PLUT_GAME_EXES:
        return

    appid = str(PLUT_GAME_EXES[game_key][0])

    cleanup_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "cache_cleanup.py"
    )
    venv_python = VENV_PYTHON

    launch_opts = (
        f'{venv_python} {cleanup_script} {game_key} steam '
        f'%command%'
    )

    try:
        from wrapper import set_launch_options, clear_compat_tool, set_compat_tool
        set_launch_options(steam_root, appid, launch_opts)
        prog(f"  HGL launch options set for appid {appid}")
        # Steam only resolves %command% when a compat tool is set, and plain
        # Play runs the stock game through it. So the game keeps a GE-Proton
        # compat tool entry, even though Heroic runs Proton for Plutonium
        # launches. Clear any stale entry, then set the current GE-Proton.
        try:
            clear_compat_tool([appid])
            set_compat_tool([appid], ge_proton_version)
            prog(f"  Compat tool set to {ge_proton_version} for appid {appid}")
        except Exception as ex:
            prog(f"  Could not set compat tool for appid {appid}: {ex}")
    except Exception as ex:
        prog(f"  Could not set HGL launch options for appid {appid}: {ex}")


def _create_heroic_steam_shortcut(game_key: str, on_progress=None,
                                   source: str = "steam"):
    """
    Create a non-Steam shortcut that launches an LCD Plutonium game through
    cache_cleanup.py, which cleans the Fossilize shader cache and then
    execs the Heroic flatpak launch. shortcut.add_shortcut does all the
    VDF, artwork and controller config work.

    Own games only. LCD Steam games are already in the Steam library with
    launch options from _set_heroic_steam_launch_options.

    The shortcut's Exe is the venv python, with LaunchOptions pointing at
    cache_cleanup.py. appid_exe_path stays the original "/usr/bin/flatpak"
    so the CRC-based appid doesn't change and existing artwork, controller
    configs and compat tool entries still match.
    """
    # Steam games need no HGL shortcut. Their library entry already
    # launches through its launch options.
    if source != "own":
        return

    def prog(msg):
        if on_progress:
            on_progress(msg)

    if game_key not in HEROIC_PLUT_GAMES:
        return

    game_def = HEROIC_PLUT_GAMES[game_key]
    title    = game_def["title"]

    cleanup_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "cache_cleanup.py"
    )
    venv_python = VENV_PYTHON

    exe_path  = f'"{venv_python}"'
    start_dir = f'"{os.path.dirname(cleanup_script)}"'
    launch_options = f'"{cleanup_script}" {game_key} own'

    # The CRC stays on the original flatpak path so existing shortcuts
    # aren't orphaned on upgrade.
    appid_exe = '"/usr/bin/flatpak"'

    # Gyro mode for the controller config
    try:
        import config as _cfg
        gyro_mode = _cfg.get_gyro_mode() or "hold"
    except Exception:
        gyro_mode = "hold"

    # LCD Plutonium shortcuts must not have a Steam compat tool. Steam runs
    # any non-Steam shortcut with a compat tool inside Steam Linux Runtime
    # (sniper), where the host's flatpak binary is invisible, so
    # "flatpak run ..." fails. HGL runs Proton itself later, so a Steam-side
    # compat tool would only break the launch.
    add_shortcut(
        name=title,
        exe_path=exe_path,
        start_dir=start_dir,
        launch_options=launch_options,
        artwork_def=game_def,
        template_type=game_def["template_type"],
        gyro_mode=gyro_mode,
        on_progress=on_progress,
        clear_compat_tool=True,
        appid_exe_path=appid_exe,
    )
