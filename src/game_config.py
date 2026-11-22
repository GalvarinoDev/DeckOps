"""
game_config.py - DeckOps game config writer

Copies pre-built config files from assets/configs/ to where each game
reads them. The source folder depends on the user's device:

    OLED  -> assets/configs/OLED/
    LCD   -> assets/configs/LCD/
    Other -> assets/configs/Other/<resolution>/   (e.g. Other/1920x1200)

Existing files are overwritten.

After copying, the player name in `seta name "..."` is set to the user's
name from deckops.json.

Every device gets configs for MW1, MW2, WaW, BO1, MW3, BO2, BO3, Ghosts, AW,
CoD1, UO, CoD2 and CoD3.

LCD Plutonium configs are also copied into the Heroic shared default prefix
(~/Games/Heroic/Prefixes/default). LCD online play runs in Heroic's Wine
prefix and never reads Steam's per-game compatdata prefix. The compatdata
copy is still written, for future offline mode.
"""

import os
import shutil

from log import get_logger

_log = get_logger(__name__)


# --- Paths

from steam_common import PROJECT_ROOT
CONFIGS_DIR  = os.path.join(PROJECT_ROOT, "assets", "configs")

# Heroic shared default prefix. LCD online play uses it for every Plutonium
# game, so configs are copied here too.
HEROIC_DEFAULT_PFX = os.path.expanduser("~/Games/Heroic/Prefixes/default")


# --- Config map
#
# Each entry maps a game key to a list of (asset_subpath, dest) pairs.
#
# asset_subpath: path relative to assets/configs/<MODEL>/
# dest: None means _dest_from_install() works it out from install_dir.
#       A string is a fixed folder in the Wine prefix AppData.
#
# Files keep their original names.
#
# Only Plutonium games keep configs in the prefix AppData. The others
# (CoD4x, IW4x, vanilla Steam) keep them in the game install folder.

def _compatdata(steam_root, appid, game_install_dir=None):
    """
    Return the compatdata path for a given appid.

    wrapper.find_compatdata searches every Steam library (internal and SD
    card) and picks the prefix in the same library as the game. Falls back
    to steam_root when nothing is found.
    """
    try:
        from wrapper import find_compatdata
        result = find_compatdata(steam_root, str(appid),
                                  game_install_dir=game_install_dir)
        if result:
            return result
    except Exception:
        _log.debug("config dest lookup failed", exc_info=True)

    # The prefix may not exist yet. os.makedirs creates it later.
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
    Return a path inside drive_c/users/steamuser/AppData/Local/ of the
    Heroic shared default prefix.

    Same as _pfx_local but rooted at HEROIC_DEFAULT_PFX. There is no appid or
    library lookup, because all LCD Plutonium games share this one prefix.
    """
    return os.path.join(
        HEROIC_DEFAULT_PFX,
        "pfx", "drive_c", "users", "steamuser", "AppData", "Local",
        *parts
    )


def _heroic_mirror_path(compatdata_dest):
    """
    Map a folder under a compatdata pfx AppData/Local to the same folder in
    the Heroic shared default prefix.

    Returns None when the path has no '/AppData/Local/' in it. Install-folder
    destinations have no Heroic copy.
    """
    marker = os.path.join("AppData", "Local") + os.sep
    idx = compatdata_dest.find(marker)
    if idx == -1:
        return None
    tail = compatdata_dest[idx + len(marker):]
    return _heroic_pfx_local(*tail.split(os.sep))


def _offline_mirror_paths(compatdata_dest, key):
    """
    The same folder in the game's offline Plutonium copy (Offline Mode), so
    offline play gets the resolution, FOV, sensitivity and player name too.
    compatdata_dest is a folder under .../AppData/Local/Plutonium/. Returns []
    when Offline Mode is off or the copy isn't built yet. This function never
    builds it.
    """
    marker = os.path.join("AppData", "Local", "Plutonium") + os.sep
    idx = compatdata_dest.find(marker)
    if idx == -1:
        return []
    import config as cfg
    from plutonium import LAN_ROOT, LAN_MOD_PLAYERS, LAN_MOD_PROFILE, OLED_LAN_WRAPPER_NAMES, _plut_key
    if not cfg.get_offline_mode() or key not in OLED_LAN_WRAPPER_NAMES:
        return []
    mode = _plut_key(key)
    client = os.path.join(LAN_ROOT, mode, "client")
    if not os.path.isdir(client):
        return []
    dest = os.path.join(client, *compatdata_dest[idx + len(marker):].split(os.sep))
    # Offline with a mod: the game reads its settings from players/<mod>/
    if mode in LAN_MOD_PLAYERS and os.path.basename(dest) == "players":
        return [os.path.join(dest, LAN_MOD_PLAYERS[mode])]
    if mode in LAN_MOD_PROFILE:
        return [dest, os.path.join(dest, LAN_MOD_PROFILE[mode])]
    return [dest]


# The config map is built inside apply_game_configs, where steam_root is known.
# A key missing from a model's set is skipped.

_LCD_KEYS  = {"cod4sp", "cod4mp", "iw4sp", "iw4mp", "iw5sp", "iw5mp", "iw5mp_ds", "t4sp", "t4mp", "t5sp", "t5mp", "t6zm", "t6mp", "t6sp", "t7", "t7x", "iw6sp", "iw6mp", "s1sp", "s1mp", "cod1sp", "cod1mp", "coduosp", "coduomp", "cod2sp", "cod2mp", "cod3"}
_OLED_KEYS = {"cod4sp", "cod4mp", "iw4sp", "iw4mp", "t4sp", "t4mp", "t5sp", "t5mp", "iw5sp", "iw5mp", "iw5mp_ds", "t6zm", "t6mp", "t6sp", "t7", "t7x", "iw6sp", "iw6mp", "s1sp", "s1mp", "cod1sp", "cod1mp", "coduosp", "coduomp", "cod2sp", "cod2mp", "cod3"}


def _build_config_map(steam_root, installed_games=None):
    """
    Return a dict of game_key -> list of (asset_subpath, dest_dir) pairs.
    dest_dir is created if missing.

    installed_games gives each game's install folder, so find_compatdata
    picks the right library for SD card installs.
    """
    # install_dir for a game key
    def _game_dir(key):
        if installed_games and key in installed_games:
            return installed_games[key].get("install_dir")
        return None

    return {
        # --- MW1 SP (IW3SP-MOD)
        "cod4sp": [
            ("MW1/iw3sp_mod_config.cfg", None),
        ],

        # --- MW1 MP (CoD4x)
        # Config goes in install_dir/players/profiles/<profile>/, same as SP.
        # CoD4x copies it to AppData/Local/CallofDuty4MW/players/profiles/
        # on first launch. active.txt in profiles/ sets the player name shown
        # in game. _write_cod4_active_txt() writes it.
        # Not in the prefix AppData. Only Plutonium uses prefix paths.
        "cod4mp": [
            ("MW1/config_mp.cfg", None),
        ],

        # --- MW2 SP
        "iw4sp": [
            ("MW2/config.cfg", None),
            ("MW2/iw4x_sp_config.cfg", None),  # read by iw4x-sp (own installs) instead of config.cfg
        ],

        # --- MW2 MP (iw4x)
        "iw4mp": [
            ("MW2/iw4x_config.cfg", None),
        ],

        # --- WaW SP + MP (Plutonium t4)
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

        # --- BO1 SP (Plutonium t5, appid 42700)
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

        # --- BO1 MP (Plutonium t5, appid 42710)
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

        # --- MW3 SP (Steam, appid 42680)
        "iw5sp": [
            ("MW3/config.cfg", None),
        ],

        # --- MW3 MP (Plutonium iw5, appid 42690)
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

        # --- MW3 DS (Plutonium iw5 on the dedicated server app, appid 42750)
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

        # --- BO2 ZM (Plutonium t6, appid 212910)
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

        # --- BO2 MP (Plutonium t6, appid 202990)
        "t6mp": [
            (
                "BO2/plutonium_mp.cfg",
                _pfx_local(
                    steam_root, 202990,
                    "Plutonium", "storage", "t6", "players",
                    game_install_dir=_game_dir("t6mp"),
                ),
            ),
            # Without it the game auto-detects 800x600 and turns the gamepad off
            (
                "BO2/hardware_mp.chp",
                _pfx_local(
                    steam_root, 202990,
                    "Plutonium", "storage", "t6", "players",
                    game_install_dir=_game_dir("t6mp"),
                ),
            ),
        ],

        # --- BO2 SP (T6SP-MOD, stock BO2 install folder)
        # Binary settings profile, copied into install_dir/players/.
        "t6sp": [
            ("BO2/user_sp.cgp", None),
            ("BO2/hardware.chp", None),
        ],

        # --- Ghosts SP (AlterWare iw6, appid 209160)
        "iw6sp": [
            ("Ghosts/config.cfg", None),
        ],

        # --- Ghosts MP (AlterWare iw6, appid 209170)
        "iw6mp": [
            ("Ghosts/config_mp.cfg", None),
        ],

        # --- AW SP (AlterWare s1, appid 209650)
        "s1sp": [
            ("AW/config.cfg", None),
        ],

        # --- AW MP (AlterWare s1, appid 209660)
        "s1mp": [
            ("AW/config_mp.cfg", None),
        ],

        # --- BO3 (CleanOps t7)
        # CleanOps is a DLL overlay, so config.ini stays in the stock BO3
        # players/ folder, same as vanilla.
        "t7": [
            ("T7X/config.ini", None),
        ],

        # --- BO3 (T7X / AlterWare)
        # T7X keeps its config.ini in t7x/players/ inside the DeckOps-T7X
        # sibling folder.
        "t7x": [
            ("T7X/config.ini", None),
        ],

        # --- Classics. MP configs bind the keys the "other" controller
        # template sends.
        "cod1sp":  [("CoD1/config.cfg", None)],
        "cod1mp":  [("CoD1/config_mp.cfg", None)],
        "coduosp": [("UO/uoconfig.cfg", None)],
        "coduomp": [("UO/uoconfig_mp.cfg", None)],
        "cod2sp":  [("CoD2/config.cfg", None)],
        "cod2mp":  [("CoD2/config_mp.cfg", None)],
        # CoD3Recomp.ini is the same on every device (resolution = desktop)
        "cod3":    [("CoD3/CoD3Recomp.ini", None)],
    }


# --- Destinations under install_dir

def _cod4_profile_name(player_name):
    """CoD4 profile folder name as the game finds it on disk. Wine drops
    trailing dots and spaces from Windows path names, so a Steam name like
    "casimiro." makes the game use profiles/casimiro."""
    return (player_name or "").replace('"', '').rstrip(". ") or "Player"


def _dest_from_install(game_key, install_dir, player_name=None):
    """
    Return the absolute destination folder for game keys whose configs live
    under install_dir. Returns None for keys that use a fixed compatdata path.
    """
    if game_key in ("cod4sp", "cod4mp"):
        return os.path.join(install_dir, "players", "profiles",
                            _cod4_profile_name(player_name))
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
    if game_key == "cod1mp":
        # CoD1x reads its config where it runs (game folder or the 1.1 copy)
        from cod1x import client_dir
        d = client_dir(install_dir)
        return _child(d, "main") if os.path.isdir(d) else os.path.join(d, "Main")
    if game_key == "cod1sp":
        return _child(install_dir, "main")
    if game_key == "coduomp":
        # CoDUOx reads its config where it runs (game folder or the Steam copy)
        from coduox import client_dir
        d = client_dir(install_dir)
        return _child(d, "uo") if os.path.isdir(d) else os.path.join(d, "uo")
    if game_key == "coduosp":
        return _child(install_dir, "uo")
    if game_key in ("cod2sp", "cod2mp"):
        return _cod2_profile_dir(_child(_child(install_dir, "main"), "players"))
    if game_key == "cod3":
        return install_dir
    return None


def _child(parent, name):
    """parent/name, reusing a folder that differs only in case. Copies differ
    (main vs Main) and Linux would make a second folder the game never reads."""
    try:
        for e in os.listdir(parent):
            if e.lower() == name and os.path.isdir(os.path.join(parent, e)):
                return os.path.join(parent, e)
    except OSError:
        pass
    return os.path.join(parent, name)


def _cod2_profile_dir(players_dir):
    """The profile folder CoD2 loads: the name in players/active.txt, else
    Default (written to active.txt so the game picks the same folder)."""
    try:
        with open(os.path.join(players_dir, "active.txt"), encoding="utf-8", errors="replace") as f:
            name = f.read().strip()
    except OSError:
        name = ""
    if not name:
        name = "Default"
        try:
            os.makedirs(players_dir, exist_ok=True)
            with open(os.path.join(players_dir, "active.txt"), "w", encoding="utf-8") as f:
                f.write(name)
        except OSError:
            pass
    return os.path.join(players_dir, name)


# --- Player name

def _replace_player_name(filepath, player_name):
    """
    Set 'seta name "<anything>"' in a config file to the user's name.

    The regex matches any current name, not only the default "Player", so
    the Settings screen can rename the player later without copying the
    configs again.

    Only `seta name "..."` changes. Other cvars with "name" in them stay.

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
        pass  # Non-fatal. The config still works with the current name.


def _write_cod4_active_txt(profiles_dir, player_name):
    """
    Write active.txt in a CoD4 profiles folder.

    CoD4 / CoD4x reads active.txt for the profile name shown in game. If the
    file is missing or still says "Player", the game shows "Player" whatever
    the seta name cvar in config_mp.cfg says.

    profiles_dir: the .../players/profiles/ folder (not the profile
                  subfolder).
    player_name: the name to write. Does nothing if None or empty.
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


def _mark_iw3sp_cfg_initialized(profile_dir):
    """
    Pre-write IW3SP-MOD's first-run marker. Without it, the first SP launch
    on a profile rebuilds iw3sp_mod_config.cfg from the vanilla config.cfg
    (or defaults when there is none) and the deployed DeckOps settings are
    lost: 1024x768, 60 Hz, controller off. Text matches what the mod writes.
    """
    try:
        d = os.path.join(profile_dir, "iw3sp_mod_init_cfg")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "IW3SP_MOD_CONFIG_INIT_DONE"), "w", encoding="utf-8") as f:
            f.write("// INIT REALLOCATION THE SETTINGS FROM ORIGINAL 'config.cfg' to 'iw3sp_mod_config.cfg'")
    except (IOError, OSError):
        pass  # Non-fatal


# --- Public API

def apply_game_configs(selected_keys, installed_games, steam_root,
                       deck_model, on_progress=None):
    """
    Copy the pre-built configs for each selected game key, using the
    folder for the user's deck model.

    After copying, `seta name` is set to the player name from deckops.json
    (if set).

    On LCD, Plutonium configs (the ones with a fixed prefix AppData
    destination) are also copied into the Heroic shared default prefix at
    ~/Games/Heroic/Prefixes/default, because LCD online play runs in Heroic's
    Wine prefix instead of Steam's per-game prefix. The Heroic copy is
    best-effort and does not change the applied/failed counts. Those count
    the compatdata write only.

    selected_keys: game keys the user selected to install
    installed_games: dict from detect_games.find_installed_games()
    steam_root: path to Steam root
    deck_model: 'oled', 'lcd', or 'other'
    on_progress: optional callback(msg: str)

    Returns (applied, skipped, failed) counts.
    """
    prog = on_progress or (lambda *a: None)

    applied  = 0
    skipped  = 0
    failed   = 0

    # Read the player name once for the whole batch
    import config as cfg
    player_name = cfg.get_player_name()

    # --- Sibling keys
    # When an MP key is selected, add its SP key too so the SP display
    # config gets written. SP and MP share the same install_dir.
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
            # Reuse the MP game entry so the SP key has a valid install_dir
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
                # For own games, fixed_dest was built from the Steam appid's
                # compatdata path. Swap in the shortcut prefix from the game
                # dict so configs land in the right prefix.
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
                # Set the user's player name
                _replace_player_name(dest, player_name)
                prog(f"  + {key}: {os.path.basename(src)} -> {dest_dir}")
                applied += 1
                if os.path.basename(dest) == "iw3sp_mod_config.cfg":
                    _mark_iw3sp_cfg_initialized(dest_dir)

                # CoD4 / CoD4x takes the shown player name from active.txt in
                # the profiles folder. Write it after every config copy so the
                # profile name stays in sync, in both the install folder and
                # the AppData prefix. CoD4x creates its own active.txt from
                # the folder name on first launch, so writing the prefix copy
                # first gives the right name on the very first launch.
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

            # --- Heroic shared prefix copy (LCD only)
            # LCD online play runs in Heroic's default prefix and never reads
            # the per-game compatdata above, so copy the config there too.
            # Best-effort: failures are logged but don't count as applied or
            # failed. OLED and Other skip this because they launch directly.
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
                        prog(f"  + {key}: also mirrored to HGL prefix "
                             f"-> {heroic_dest_dir}")
                    except Exception as ex:
                        prog(f"  ! {key}: HGL mirror failed "
                             f"({os.path.basename(src)}): {ex}")

            # --- Offline copy (Offline Mode)
            # Offline play runs from DeckOps' own Plutonium copy (OLED and LCD),
            # so it gets the same configs. Best-effort, does not change the
            # applied/failed counts.
            if fixed_dest:
                for offline_dir in _offline_mirror_paths(dest_dir, key):
                    try:
                        os.makedirs(offline_dir, exist_ok=True)
                        offline_dest = os.path.join(
                            offline_dir, os.path.basename(src)
                        )
                        shutil.copy2(src, offline_dest)
                        _replace_player_name(offline_dest, player_name)
                        prog(f"  + {key}: also mirrored to the offline copy "
                             f"-> {offline_dir}")
                    except Exception as ex:
                        prog(f"  ! {key}: offline copy mirror failed "
                             f"({os.path.basename(src)}): {ex}")

    # --- BRO: an empty profile named after the player, only when it has none
    if "bro" in selected_keys:
        try:
            from bro import seed_profile
            if seed_profile(player_name):
                prog("  + bro: profile created")
        except Exception as ex:
            prog(f"  ! bro: profile not created: {ex}")

    prog(f"Game configs: {applied} applied, {skipped} skipped, {failed} failed.")
    return applied, skipped, failed


def rename_player(player_name, steam_root, installed_games=None,
                  on_progress=None):
    """
    Set the player name in every deployed config file without copying from
    assets again. Goes through all set-up game keys, finds their config
    folders, and runs _replace_player_name on each file found.

    Also updates the Heroic shared prefix copies of LCD Plutonium configs.

    Returns the number of files updated.
    """
    import config as cfg

    prog = on_progress or (lambda *a: None)

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
                # CoD4: find the old profile folder first ("Player" or an
                # earlier name) and rename it.
                if key in ("cod4sp", "cod4mp"):
                    profiles_dir = os.path.join(install_dir, "players", "profiles")
                    new_profile = _cod4_profile_name(player_name)
                    new_profile_dir = os.path.join(profiles_dir, new_profile)
                    # Find the current profile folder from active.txt, else
                    # take the only subfolder if there is exactly one.
                    old_profile_dir = None
                    active_path = os.path.join(profiles_dir, "active.txt")
                    if os.path.exists(active_path):
                        try:
                            with open(active_path, "r", encoding="utf-8") as f:
                                old_name = f.read().strip()
                            candidate = os.path.join(profiles_dir, _cod4_profile_name(old_name))
                            if os.path.isdir(candidate):
                                old_profile_dir = candidate
                        except (IOError, OSError):
                            pass
                    if not old_profile_dir:
                        # Fallback: any existing profile subfolder
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

            # CoD4x also reads the AppData prefix. Update active.txt there too
            # so the profile name is right after the first launch.
            if key in ("cod4sp", "cod4mp") and install_dir:
                appdata_profiles = _pfx_local(
                    steam_root, 7940,
                    "CallofDuty4MW", "players", "profiles",
                    game_install_dir=install_dir,
                )
                _write_cod4_active_txt(appdata_profiles, player_name)
                prog(f"  + {key}: updated active.txt in AppData prefix")

            # Heroic copy
            if fixed_dest:
                heroic_dest_dir = _heroic_mirror_path(dest_dir)
                if heroic_dest_dir:
                    heroic_dest = os.path.join(
                        heroic_dest_dir, os.path.basename(asset_subpath)
                    )
                    if os.path.exists(heroic_dest):
                        _replace_player_name(heroic_dest, player_name)
                        updated += 1
                        prog(f"  + {key}: renamed in HGL mirror")

            # Offline copy
            if fixed_dest:
                for offline_dir in _offline_mirror_paths(dest_dir, key):
                    offline_dest = os.path.join(
                        offline_dir, os.path.basename(asset_subpath)
                    )
                    if os.path.exists(offline_dest):
                        _replace_player_name(offline_dest, player_name)
                        updated += 1
                        prog(f"  + {key}: renamed in the offline copy")

    # --- T7X
    # T7X keeps its player name as JSON in t7x/players/properties.json,
    # not in a seta cvar, so it is handled outside the config map.
    if "t7x" in setup_keys:
        try:
            from t7x import set_player_name as _t7x_set_name, _get_sibling_dir
            game = (installed_games or {}).get("t7x", {})
            # The t7x install_dir is the sibling folder (set during install)
            sibling = game.get("install_dir", "")
            if not sibling:
                # Fallback: work it out from the t7 (BO3) install folder
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

    # --- BRO keeps the name in its signed profile file
    if "bro" in setup_keys:
        try:
            from bro import rename_profile
            if rename_profile(player_name):
                updated += 1
                prog("  + bro: renamed in the profile")
        except Exception as ex:
            prog(f"  ⚠ bro: rename failed: {ex}")

    updated += _rename_in_lan_scripts(player_name, installed_games, prog)

    prog(f"Player name updated in {updated} file(s).")
    return updated


def _rename_in_lan_scripts(player_name, installed_games, prog):
    """
    Plutonium offline scripts have the name written in as +name "...": the
    -lan .sh (used by the LAN launcher) and the LCD Steam replaced exe
    fallback. Rewrite it in each.
    """
    import re
    import config as cfg
    from plutonium_lcd import PLUT_GAME_EXES

    new = '+name "' + player_name.replace('"', '') + '"'
    updated = 0
    for key, entry in cfg.get_setup_games().items():
        lan = entry.get("lan_wrapper_path")
        if not lan:
            continue
        d = os.path.dirname(lan)
        paths = {lan}
        if key in PLUT_GAME_EXES and entry.get("source") != "own":
            paths.add(os.path.join(d, PLUT_GAME_EXES[key][1]))

        for p in paths:
            try:
                with open(p, "rb") as f:
                    raw = f.read()
            except OSError:
                continue
            if not raw.startswith(b"#!"):
                continue
            body = raw.rstrip(b"\x00")
            text = re.sub(r'\+name "[^"]*"', lambda m: new, body.decode("utf-8", "replace"), count=1)
            out = text.encode("utf-8")
            if out == body:
                continue
            # Replaced game exes are padded to the original size for Steam validation
            if len(body) < len(raw) and len(out) < len(raw):
                out += b"\x00" * (len(raw) - len(out))
            with open(p, "wb") as f:
                f.write(out)
            updated += 1
            prog(f"  + {key}: renamed in {os.path.basename(p)}")
    return updated
