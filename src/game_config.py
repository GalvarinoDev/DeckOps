"""
game_config.py - DeckOps game config writer

Copies pre-built config files from assets/configs/ into the correct
destination paths for each game. The source folder is determined by the
user's device selection:

    OLED  -> assets/configs/OLED/
    LCD   -> assets/configs/LCD/
    Other -> assets/configs/Other/<resolution>/   (e.g. Other/1920x1200)

Overwrites whatever is currently there.

After copying, replaces the default player name ("Player") with the user's
chosen name from deckops.json in any config that has `seta name "Player"`.

LCD users receive MW1, MW2, MW3 SP, Ghosts, and AW configs.
OLED and Other users receive MW1, MW2, WaW, BO1, MW3, BO2, Ghosts, and AW configs.

LCD Plutonium games are additionally mirrored into the Heroic shared default
prefix (~/Games/Heroic/Prefixes/default), because LCD online play routes
through Heroic's Wine environment and never touches Steam's per-game
compatdata prefix. The compatdata write is preserved for future offline mode.
"""

import os
import glob
import shutil

from log import get_logger

_log = get_logger(__name__)


# ── Paths ─────────────────────────────────────────────────────────────────────

_HERE        = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_HERE)
CONFIGS_DIR  = os.path.join(PROJECT_ROOT, "assets", "configs")

# Heroic shared default prefix — used by LCD online play for all Plutonium
# games. Configs must be mirrored here so LCD online launches see them.
HEROIC_DEFAULT_PFX = os.path.expanduser("~/Games/Heroic/Prefixes/default")


# ── Config map ────────────────────────────────────────────────────────────────
#
# Each entry maps a game key to a list of (asset_subpath, dest_resolver) pairs.
#
# asset_subpath  — path relative to assets/configs/<MODEL>/
# dest_resolver  — callable(install_dir, steam_root) -> absolute destination directory
#
# Files are copied with their original filename preserved.
#
# Dest convention:
#   None  → resolved at runtime from install_dir via _dest_from_install()
#   str   → fixed path (used for Plutonium games whose configs live in prefix AppData)
#
# Only Plutonium games store configs inside the Wine prefix AppData.
# All other games (CoD4x, IW4x, vanilla Steam) store configs in the
# game install directory.

def _compatdata(steam_root, appid, game_install_dir=None):
    """
    Return the compatdata path for a given appid.

    Uses wrapper.find_compatdata which searches all Steam library folders
    (internal + SD card) and picks the prefix in the same library as the
    game install directory. Falls back to steam_root if not found.
    """
    try:
        from wrapper import find_compatdata
        result = find_compatdata(steam_root, str(appid),
                                  game_install_dir=game_install_dir)
        if result:
            return result
    except Exception:
        _log.debug("config dest lookup failed", exc_info=True)

    # Fallback — prefix may not exist yet (os.makedirs will create it later)
    return os.path.join(steam_root, "steamapps", "compatdata", str(appid))


def _pfx_local(steam_root, appid, *parts, game_install_dir=None):
    """Return a path inside pfx/drive_c/users/steamuser/AppData/Local/ for an appid."""
    return os.path.join(
        _compatdata(steam_root, appid, game_install_dir=game_install_dir),
        "pfx", "drive_c", "users", "steamuser", "AppData", "Local",
        *parts
    )


def _heroic_pfx_local(*parts):
    """
    Return a path inside the Heroic shared default prefix's
    drive_c/users/steamuser/AppData/Local/ tree.

    Mirrors _pfx_local but rooted at HEROIC_DEFAULT_PFX. No appid or library
    resolution — the Heroic prefix is a single shared location for all LCD
    Plutonium games.
    """
    return os.path.join(
        HEROIC_DEFAULT_PFX,
        "pfx", "drive_c", "users", "steamuser", "AppData", "Local",
        *parts
    )


def _heroic_mirror_path(compatdata_dest):
    """
    Given a destination path inside a compatdata pfx AppData/Local tree,
    return the equivalent path inside the Heroic shared default prefix.

    Returns None if the input does not contain '/AppData/Local/' (i.e. not
    a prefix-AppData path — install-dir destinations have no Heroic mirror).
    """
    marker = os.path.join("AppData", "Local") + os.sep
    idx = compatdata_dest.find(marker)
    if idx == -1:
        return None
    tail = compatdata_dest[idx + len(marker):]
    return _heroic_pfx_local(*tail.split(os.sep))


def _launcher_mirror_path(compatdata_dest):
    """
    Given a destination path inside a compatdata pfx AppData/Local tree,
    return the equivalent path inside the offline launcher's prefix.

    The launcher runs as a non-Steam shortcut with its own compatdata
    prefix. Plutonium configs must be mirrored there so the bootstrapper
    can find them when launched from the offline launcher.

    Returns None if the input does not contain '/AppData/Local/' or if
    the launcher appid cannot be determined.
    """
    marker = os.path.join("AppData", "Local") + os.sep
    idx = compatdata_dest.find(marker)
    if idx == -1:
        return None
    tail = compatdata_dest[idx + len(marker):]
    try:
        from shortcut import get_launcher_plut_dir
        # get_launcher_plut_dir returns .../AppData/Local/Plutonium
        # We need the AppData/Local base, then append the tail
        launcher_plut = get_launcher_plut_dir()
        # Strip "Plutonium" from the end to get the AppData/Local base
        launcher_local = os.path.dirname(launcher_plut)
        return os.path.join(launcher_local, *tail.split(os.sep))
    except Exception:
        _log.debug("launcher prefix config lookup failed", exc_info=True)
        return None


# The config map is built inside apply_game_configs so steam_root is available.
# Keys that are absent for a given model are simply not included.

_LCD_KEYS  = {"cod4sp", "cod4mp", "iw4sp", "iw4mp", "iw5sp", "iw5mp", "iw5mp_ds", "t4sp", "t4mp", "t5sp", "t5mp", "t6zm", "t6mp", "t6sp", "t7", "t7x", "iw6sp", "iw6mp", "s1sp", "s1mp"}
_OLED_KEYS = {"cod4sp", "cod4mp", "iw4sp", "iw4mp", "t4sp", "t4mp", "t5sp", "t5mp", "iw5sp", "iw5mp", "iw5mp_ds", "t6zm", "t6mp", "t6sp", "t7", "t7x", "iw6sp", "iw6mp", "s1sp", "s1mp"}


def _build_config_map(steam_root, installed_games=None):
    """
    Returns a dict mapping game_key -> list of (asset_subpath, dest_dir) pairs.
    dest_dir will be created if it does not exist.

    installed_games is used to resolve the correct compatdata for SD card
    installs (pass game_install_dir so find_compatdata picks the right library).
    """
    # Helper to get install_dir for a game key
    def _game_dir(key):
        if installed_games and key in installed_games:
            return installed_games[key].get("install_dir")
        return None

    return {
        # ── MW1 SP (IW3SP-MOD) ────────────────────────────────────────────────
        "cod4sp": [
            ("MW1/iw3sp_mod_config.cfg", None),
        ],

        # ── MW1 MP (CoD4x) ────────────────────────────────────────────────────
        # Config lives in install_dir/players/profiles/Player/ (same as SP).
        # CoD4x copies this to AppData/Local/CallofDuty4MW/players/profiles/
        # on first launch. active.txt in the profiles/ dir controls the
        # displayed player name — written by _write_cod4_active_txt().
        # NOT in prefix AppData — only Plutonium uses prefix paths.
        "cod4mp": [
            ("MW1/config_mp.cfg", None),
        ],

        # ── MW2 SP ────────────────────────────────────────────────────────────
        "iw4sp": [
            ("MW2/config.cfg", None),
        ],

        # ── MW2 MP (iw4x) ─────────────────────────────────────────────────────
        "iw4mp": [
            ("MW2/iw4x_config.cfg", None),
        ],

        # ── WaW SP + MP (Plutonium t4) ────────────────────────────────────────
        "t4sp": [
            (
                "WaW/config.cfg",
                _pfx_local(
                    steam_root, 10090,
                    "Plutonium", "storage", "t4", "players", "profiles", "$$$",
                    game_install_dir=_game_dir("t4sp"),
                ),
            ),
        ],
        "t4mp": [
            (
                "WaW/config_mp.cfg",
                _pfx_local(
                    steam_root, 10090,
                    "Plutonium", "storage", "t4", "players", "profiles", "$$$",
                    game_install_dir=_game_dir("t4mp"),
                ),
            ),
        ],

        # ── BO1 SP (Plutonium t5, appid 42700) ────────────────────────────────
        "t5sp": [
            (
                "BO1/config.cfg",
                _pfx_local(
                    steam_root, 42700,
                    "Plutonium", "storage", "t5", "players",
                    game_install_dir=_game_dir("t5sp"),
                ),
            ),
        ],

        # ── BO1 MP (Plutonium t5, appid 42710) ────────────────────────────────
        "t5mp": [
            (
                "BO1/config_mp.cfg",
                _pfx_local(
                    steam_root, 42710,
                    "Plutonium", "storage", "t5", "players",
                    game_install_dir=_game_dir("t5mp"),
                ),
            ),
        ],

        # ── MW3 SP (via Steam, appid 42690) ───────────────────────────────────
        "iw5sp": [
            ("MW3/config.cfg", None),
        ],

        # ── MW3 MP (Plutonium iw5, appid 42690) ───────────────────────────────
        "iw5mp": [
            (
                "MW3/config_mp.cfg",
                _pfx_local(
                    steam_root, 42690,
                    "Plutonium", "storage", "iw5", "players",
                    game_install_dir=_game_dir("iw5mp"),
                ),
            ),
        ],

        # ── MW3 DS (Plutonium iw5 via dedicated server, appid 42750) ──────────
        "iw5mp_ds": [
            (
                "MW3/config_mp.cfg",
                _pfx_local(
                    steam_root, 42750,
                    "Plutonium", "storage", "iw5", "players",
                    game_install_dir=_game_dir("iw5mp_ds"),
                ),
            ),
        ],

        # ── BO2 ZM (Plutonium t6, appid 212910) ───────────────────────────────
        "t6zm": [
            (
                "BO2/plutonium_zm.cfg",
                _pfx_local(
                    steam_root, 212910,
                    "Plutonium", "storage", "t6", "players",
                    game_install_dir=_game_dir("t6zm"),
                ),
            ),
        ],

        # ── BO2 MP (Plutonium t6, appid 202990) ───────────────────────────────
        "t6mp": [
            (
                "BO2/plutonium_mp.cfg",
                _pfx_local(
                    steam_root, 202990,
                    "Plutonium", "storage", "t6", "players",
                    game_install_dir=_game_dir("t6mp"),
                ),
            ),
        ],

        # ── BO2 SP (T6SP-MOD, uses stock BO2 install dir) ────────────────────
        # Binary settings profile — dropped into install_dir/players/.
        "t6sp": [
            ("BO2/user_sp.cgp", None),
        ],

        # ── Ghosts SP (AlterWare iw6, appid 209160) ──────────────────────────
        "iw6sp": [
            ("Ghosts/config.cfg", None),
        ],

        # ── Ghosts MP (AlterWare iw6, appid 209170) ──────────────────────────
        "iw6mp": [
            ("Ghosts/config_mp.cfg", None),
        ],

        # ── AW SP (AlterWare s1, appid 209650) ───────────────────────────────
        "s1sp": [
            ("AW/config.cfg", None),
        ],

        # ── AW MP (AlterWare s1, appid 209660) ───────────────────────────────
        "s1mp": [
            ("AW/config_mp.cfg", None),
        ],

        # ── BO3 (CleanOps t7) ────────────────────────────────────────────────
        # CleanOps is a DLL overlay — config.ini lives in the stock BO3
        # players/ directory, same as vanilla.
        "t7": [
            ("T7X/config.ini", None),
        ],

        # ── BO3 (T7X / AlterWare) ────────────────────────────────────────────
        # T7X stores its config.ini inside the t7x/players/ subdirectory
        # of the DeckOps-T7X sibling dir.
        "t7x": [
            ("T7X/config.ini", None),
        ],
    }


# ── Install-dir based dest resolvers ──────────────────────────────────────────

def _dest_from_install(game_key, install_dir, player_name=None):
    """
    For game keys whose destination is relative to install_dir,
    return the correct absolute destination directory.
    Returns None for keys that use a fixed compatdata path instead.
    """
    if game_key in ("cod4sp", "cod4mp"):
        profile = player_name.replace('"', '') if player_name else "Player"
        return os.path.join(install_dir, "players", "profiles", profile)
    if game_key in ("iw4sp", "iw4mp"):
        return os.path.join(install_dir, "players")
    if game_key == "iw5sp":
        return os.path.join(install_dir, "players2")
    if game_key in ("iw6sp", "iw6mp", "s1sp", "s1mp"):
        return os.path.join(install_dir, "players2")
    if game_key == "t7":
        return os.path.join(install_dir, "players")
    if game_key == "t7x":
        return os.path.join(install_dir, "t7x", "players")
    if game_key == "t6sp":
        return os.path.join(install_dir, "players")
    return None


# ── Player name replacement ───────────────────────────────────────────────────

def _replace_player_name(filepath, player_name):
    """
    Replace 'seta name "<anything>"' with the user's chosen name in a config file.

    Uses a regex to match any current name value, not just the default
    "Player". This allows the Settings screen to rename the player after
    initial install without needing to re-deploy configs from scratch.

    Only modifies lines that match `seta name "..."` exactly — other cvars
    that happen to contain "name" are not affected.

    Does nothing if player_name is None or empty.
    """
    if not player_name:
        return

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        import re as _re
        pattern = r'seta name ".*?"'
        safe_name = player_name.replace('"', '')
        replacement = f'seta name "{safe_name}"'

        new_content = _re.sub(pattern, replacement, content)
        if new_content == content:
            return

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
    except (IOError, OSError):
        pass  # Non-fatal — config still works with current name


def _write_cod4_active_txt(profiles_dir, player_name):
    """
    Write (or overwrite) the active.txt file in a CoD4 profiles directory.

    CoD4 / CoD4x reads active.txt to determine the active profile name
    displayed in-game. Without this file, or if it still says "Player",
    the player name will show as "Player" regardless of the seta name
    cvar in config_mp.cfg.

    profiles_dir — the .../players/profiles/ directory (not the profile
                   subfolder itself).
    player_name  — the name to write into active.txt. Does nothing if
                   None or empty.
    """
    if not player_name:
        return

    try:
        os.makedirs(profiles_dir, exist_ok=True)
        active_path = os.path.join(profiles_dir, "active.txt")
        safe_name = player_name.replace('"', '')
        with open(active_path, "w", encoding="utf-8") as f:
            f.write(safe_name)
    except (IOError, OSError):
        pass  # Non-fatal


# ── Public API ────────────────────────────────────────────────────────────────

def apply_game_configs(selected_keys, installed_games, steam_root,
                       deck_model, on_progress=None):
    """
    Copy pre-built config files into the correct destination for each
    selected game key, based on the user's deck model.

    After copying, replaces `seta name "Player"` with the user's chosen
    player name from deckops.json (if set).

    For LCD installs, Plutonium configs (those with a fixed prefix-AppData
    destination) are additionally mirrored into the Heroic shared default
    prefix at ~/Games/Heroic/Prefixes/default, since LCD online play routes
    through Heroic's Wine environment instead of Steam's per-game prefix.
    The Heroic mirror copy is best-effort and does not affect applied/failed
    counts — the compatdata write is the source of truth for those.

    selected_keys   — list of game keys the user selected to install
    installed_games — dict from detect_games.find_installed_games()
    steam_root      — path to Steam root
    deck_model      — 'oled', 'lcd', or 'other'
    on_progress     — optional callback(msg: str)

    Returns (applied, skipped, failed) counts.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    applied  = 0
    skipped  = 0
    failed   = 0

    # Read the player name once for the whole batch
    import config as cfg
    player_name = cfg.get_player_name()

    # ── Sibling key expansion ─────────────────────────────────────────────
    # MW2 SP (iw4sp) and MW3 SP (iw5sp) have config entries but aren't
    # tracked by detect_games / ALL_GAMES — they run through vanilla Steam.
    # When their MP sibling is selected, auto-include the SP key so its
    # display config also gets written.  The SP shares the same install_dir.
    _SIBLING_MAP = {
        "iw4mp": "iw4sp",      # MW2 MP  → MW2 SP
        "iw5mp": "iw5sp",      # MW3 MP  → MW3 SP
        "iw5mp_ds": "iw5sp",   # MW3 DS  → MW3 SP
        "iw6mp": "iw6sp",      # Ghosts MP → Ghosts SP
        "s1mp":  "s1sp",       # AW MP    → AW SP
    }
    expanded_keys = list(selected_keys)
    for mp_key, sp_key in _SIBLING_MAP.items():
        if mp_key in selected_keys and sp_key not in expanded_keys:
            expanded_keys.append(sp_key)
            # Re-use the MP game entry so the SP key has a valid install_dir
            if mp_key in installed_games and sp_key not in installed_games:
                installed_games[sp_key] = installed_games[mp_key]

    model_dir    = cfg.get_model_config_dir()
    allowed_keys = _LCD_KEYS if deck_model == "lcd" else _OLED_KEYS
    config_map  = _build_config_map(steam_root, installed_games)

    for key in expanded_keys:
        if key not in allowed_keys:
            continue
        if key not in config_map:
            prog(f"  - {key}: no config available yet, skipping")
            skipped += 1
            continue

        game       = installed_games.get(key, {})
        install_dir = game.get("install_dir", "")

        for asset_subpath, fixed_dest in config_map[key]:
            src = os.path.join(CONFIGS_DIR, model_dir, asset_subpath)

            if not os.path.exists(src):
                prog(f"  - {key}: asset not found ({asset_subpath}), skipping")
                skipped += 1
                continue

            # Resolve destination directory
            if fixed_dest:
                # For "own" games, fixed_dest was built using the Steam appid-based
                # compatdata path. Swap the base out for the actual shortcut prefix
                # stored in the game dict so configs land in the right prefix.
                if game.get("source") == "own" and game.get("compatdata_path"):
                    pfx_parts = fixed_dest.split("/pfx/", 1)
                    if len(pfx_parts) == 2:
                        fixed_dest = os.path.join(
                            game["compatdata_path"], "pfx", pfx_parts[1]
                        )
                dest_dir = fixed_dest
            else:
                if not install_dir:
                    prog(f"  - {key}: install_dir unknown, skipping")
                    skipped += 1
                    continue
                dest_dir = _dest_from_install(key, install_dir,
                                             player_name=player_name)
                if not dest_dir:
                    prog(f"  - {key}: could not resolve destination, skipping")
                    skipped += 1
                    continue

            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, os.path.basename(src))

            try:
                shutil.copy2(src, dest)
                # Replace default player name with user's chosen name
                _replace_player_name(dest, player_name)
                prog(f"  + {key}: {os.path.basename(src)} -> {dest_dir}")
                applied += 1

                # CoD4 / CoD4x uses active.txt in the profiles directory
                # to determine the displayed player name. Write it after
                # every config deploy so the profile name stays in sync.
                # Write to both the install dir AND the AppData prefix —
                # CoD4x creates its own active.txt on first launch from
                # the folder name, so pre-seeding the prefix ensures the
                # correct name is used even on the very first launch.
                if key in ("cod4sp", "cod4mp") and player_name:
                    _write_cod4_active_txt(os.path.dirname(dest_dir), player_name)
                    appdata_profiles = _pfx_local(
                        steam_root, 7940,
                        "CallofDuty4MW", "players", "profiles",
                        game_install_dir=install_dir,
                    )
                    _write_cod4_active_txt(appdata_profiles, player_name)

            except Exception as ex:
                prog(f"  - {key}: failed to copy {os.path.basename(src)}: {ex}")
                failed += 1
                continue

            # ── Heroic shared prefix mirror (LCD only) ────────────────────
            # LCD online play routes through Heroic's default prefix, which
            # never touches the per-game compatdata above. Mirror the same
            # config there so online launches see it. Best-effort: failures
            # here are logged but don't increment applied/failed.
            # OLED and Other devices skip this — they launch directly.
            if deck_model == "lcd" and fixed_dest:
                heroic_dest_dir = _heroic_mirror_path(dest_dir)
                if heroic_dest_dir:
                    try:
                        os.makedirs(heroic_dest_dir, exist_ok=True)
                        heroic_dest = os.path.join(
                            heroic_dest_dir, os.path.basename(src)
                        )
                        shutil.copy2(src, heroic_dest)
                        _replace_player_name(heroic_dest, player_name)
                        prog(f"  + {key}: also mirrored to Heroic prefix "
                             f"-> {heroic_dest_dir}")
                    except Exception as ex:
                        prog(f"  ! {key}: Heroic mirror failed "
                             f"({os.path.basename(src)}): {ex}")

            # ── Offline launcher prefix mirror (OLED / Other only) ────────
            # The offline launcher exe runs in its own Proton prefix.
            # Mirror Plutonium configs there so the bootstrapper finds
            # resolution, FOV, sensitivity, and player name settings.
            # LCD is skipped — both online and offline play use the
            # single Heroic shared prefix, not the launcher's own prefix.
            # Best-effort — does not affect applied/failed counts.
            if fixed_dest and deck_model != "lcd":
                launcher_dest_dir = _launcher_mirror_path(dest_dir)
                if launcher_dest_dir:
                    try:
                        os.makedirs(launcher_dest_dir, exist_ok=True)
                        launcher_dest = os.path.join(
                            launcher_dest_dir, os.path.basename(src)
                        )
                        shutil.copy2(src, launcher_dest)
                        _replace_player_name(launcher_dest, player_name)
                        prog(f"  + {key}: also mirrored to launcher prefix "
                             f"-> {launcher_dest_dir}")
                    except Exception as ex:
                        prog(f"  ! {key}: launcher mirror failed "
                             f"({os.path.basename(src)}): {ex}")

    prog(f"Game configs: {applied} applied, {skipped} skipped, {failed} failed.")
    return applied, skipped, failed


def rename_player(player_name, steam_root, installed_games=None,
                  on_progress=None):
    """
    Update the player name in all deployed config files without re-copying
    from assets. Scans all setup game keys, resolves their config
    destinations, and applies _replace_player_name to each file found.

    Also updates the Heroic shared prefix mirror for LCD Plutonium configs.

    Returns the number of files updated.
    """
    import config as cfg

    def prog(msg):
        if on_progress:
            on_progress(msg)

    if not player_name:
        prog("No player name provided.")
        return 0

    setup_keys = list(cfg.get_setup_games().keys())
    if not setup_keys:
        prog("No games set up yet.")
        return 0

    config_map = _build_config_map(steam_root, installed_games)
    updated = 0

    for key in setup_keys:
        if key not in config_map:
            continue

        game = (installed_games or {}).get(key, {})
        install_dir = game.get("install_dir", "")

        for asset_subpath, fixed_dest in config_map[key]:
            # Resolve destination
            if fixed_dest:
                if game.get("source") == "own" and game.get("compatdata_path"):
                    pfx_parts = fixed_dest.split("/pfx/", 1)
                    if len(pfx_parts) == 2:
                        fixed_dest = os.path.join(
                            game["compatdata_path"], "pfx", pfx_parts[1]
                        )
                dest_dir = fixed_dest
            else:
                if not install_dir:
                    continue
                # For CoD4, we need to find the OLD profile folder first
                # (could be "Player" or a previous custom name) and rename it.
                if key in ("cod4sp", "cod4mp"):
                    profiles_dir = os.path.join(install_dir, "players", "profiles")
                    new_profile = player_name.replace('"', '')
                    new_profile_dir = os.path.join(profiles_dir, new_profile)
                    # Find the existing profile folder — check active.txt first,
                    # then fall back to any single subfolder.
                    old_profile_dir = None
                    active_path = os.path.join(profiles_dir, "active.txt")
                    if os.path.exists(active_path):
                        try:
                            with open(active_path, "r", encoding="utf-8") as f:
                                old_name = f.read().strip()
                            candidate = os.path.join(profiles_dir, old_name)
                            if os.path.isdir(candidate):
                                old_profile_dir = candidate
                        except (IOError, OSError):
                            pass
                    if not old_profile_dir:
                        # Fall back: look for any existing profile subfolder
                        try:
                            subdirs = [
                                d for d in os.listdir(profiles_dir)
                                if os.path.isdir(os.path.join(profiles_dir, d))
                            ]
                            if len(subdirs) == 1:
                                old_profile_dir = os.path.join(profiles_dir, subdirs[0])
                        except (IOError, OSError):
                            pass

                    if old_profile_dir and old_profile_dir != new_profile_dir:
                        try:
                            os.rename(old_profile_dir, new_profile_dir)
                            prog(f"  + {key}: renamed profile folder "
                                 f"{os.path.basename(old_profile_dir)} -> {new_profile}")
                        except (IOError, OSError) as ex:
                            prog(f"  ⚠ {key}: could not rename profile folder: {ex}")

                    dest_dir = new_profile_dir
                else:
                    dest_dir = _dest_from_install(key, install_dir,
                                                 player_name=player_name)
                if not dest_dir:
                    continue

            dest = os.path.join(dest_dir, os.path.basename(asset_subpath))
            if os.path.exists(dest):
                _replace_player_name(dest, player_name)
                updated += 1
                prog(f"  + {key}: renamed in {os.path.basename(dest)}")

                # Update active.txt for CoD4 / CoD4x in the install dir
                if key in ("cod4sp", "cod4mp"):
                    _write_cod4_active_txt(os.path.dirname(dest_dir), player_name)

            # CoD4x also reads from the AppData prefix — update active.txt
            # there too so the profile name is correct after first launch.
            if key in ("cod4sp", "cod4mp") and install_dir:
                appdata_profiles = _pfx_local(
                    steam_root, 7940,
                    "CallofDuty4MW", "players", "profiles",
                    game_install_dir=install_dir,
                )
                _write_cod4_active_txt(appdata_profiles, player_name)
                prog(f"  + {key}: updated active.txt in AppData prefix")

            # Heroic mirror
            if fixed_dest:
                heroic_dest_dir = _heroic_mirror_path(dest_dir)
                if heroic_dest_dir:
                    heroic_dest = os.path.join(
                        heroic_dest_dir, os.path.basename(asset_subpath)
                    )
                    if os.path.exists(heroic_dest):
                        _replace_player_name(heroic_dest, player_name)
                        updated += 1
                        prog(f"  + {key}: renamed in Heroic mirror")

            # Launcher prefix mirror
            if fixed_dest:
                launcher_dest_dir = _launcher_mirror_path(dest_dir)
                if launcher_dest_dir:
                    launcher_dest = os.path.join(
                        launcher_dest_dir, os.path.basename(asset_subpath)
                    )
                    if os.path.exists(launcher_dest):
                        _replace_player_name(launcher_dest, player_name)
                        updated += 1
                        prog(f"  + {key}: renamed in launcher mirror")

    # ── T7X special case ─────────────────────────────────────────────────
    # T7X stores its player name in t7x/players/properties.json as JSON,
    # not as a seta cvar. Handled separately from the config map.
    if "t7x" in setup_keys:
        try:
            from t7x import set_player_name as _t7x_set_name, _get_sibling_dir
            game = (installed_games or {}).get("t7x", {})
            # t7x install_dir IS the sibling dir (set during install)
            sibling = game.get("install_dir", "")
            if not sibling:
                # Fall back: look up from the t7 (BO3) install dir
                t7_game = (installed_games or {}).get("t7", {})
                t7_dir = t7_game.get("install_dir", "")
                if t7_dir:
                    sibling = _get_sibling_dir(t7_dir)
            if sibling and os.path.isdir(sibling):
                _t7x_set_name(sibling, player_name)
                updated += 1
                prog(f"  + t7x: renamed in properties.json")
        except Exception as ex:
            prog(f"  ⚠ t7x: rename failed: {ex}")

    prog(f"Player name updated in {updated} file(s).")
    return updated
