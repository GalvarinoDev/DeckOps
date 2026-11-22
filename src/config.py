"""
config.py - DeckOps configuration manager

Reads and writes deckops.json in the install directory (path from
identity.py).

The config file tracks, among other things:
    - whether first-time setup is done
    - the device (oled, lcd, other, or steam_machine)
    - the resolution profile for 'other' and 'steam_machine' devices
    - which games are set up and when
    - the Steam root path found during setup
"""

import copy
import os
import json
import re
import threading
from datetime import datetime

from identity import CONFIG_PATH
from log import get_logger
from steam_common import write_json

_log = get_logger(__name__)

DEFAULTS = {
    "first_run_complete": False,
    "os_type": None,             # "steamos", "bazzite", "cachyos", "armada", or "other_linux"
    "deck_model": None,          # "oled", "lcd", "other", or "steam_machine"
    "other_device": None,         # resolution key for non-Deck devices and Steam Machine, e.g.
                                  # "1920x1200", "1920x1200_144hz", "1920x1080", "1280x720"
    "other_device_type": None,    # device type for controller profile selection:
                                  # "legion_go", "legion_go_2", "legion_go_s", "2btn", "generic", "steam_machine"
    "gyro_mode":  None,          # "on", "off", "hold", or "toggle"
    "play_mode":  None,          # "handheld" or "docked"
    "external_controller": None, # "playstation", "xbox", "steamcontroller", or "other". Only used when play_mode is "docked"
    "docked_resolution": None,   # "1280x720", "1280x800", "1920x1080", "1920x1200", or "own". Only used when play_mode is "docked"
                                 # Planned for future Bazzite, Steam Box, and other handheld support on SteamOS
    "ge_proton_version": None,   # e.g. "GE-Proton10-32"
    "steam_root": None,
    "setup_games": {},           # key: game key, value: { "client": ..., "source": "steam"|"own", "setup_at": timestamp,
                                 #   "lan_wrapper_path": path to -lan bash script for offline launcher (all sources) }
    "depot_patched": {},         # legacy (read-only): pre-receipt Ghosts/AW downgrade flag. Receipts now live in the game folder
    "game_source": None,         # "both" since the unified game list. Older installs may have "steam" or "own"
    "music_enabled": True,       # background music on/off
    "music_volume":  0.4,        # 0.0 to 1.0
    "player_name": None,         # in-game player name for configs and LCD Plutonium
    "iw_pad": {},                # sp_mod.py: { game key: { "tag", "digest" } } of the installed IW-Pad release
    "zd_installed": None,        # Zombies Declassified: { "manifest_hash": ..., "installed_at": ... } or None
    "offline_mode": None,        # Offline Mode (opt-in): offline launcher, Steam menu Offline entries,
                                 #   WaW/BO1/BO2/MW3 MP bot matches. None = not chosen yet (older installs)
    "manifest_mods": {},         # manifest_mods.py: { mod_id: { "option" (component mods: "a+b"), "games_root", "option_hash", "complete", "installed_at" } }
    "manifest_cdn":  None,       # manifest_mods.py: CDN base shared by all manifest mods, typed by the user
}


# --- In-memory cache
# Saves re-reading and re-parsing deckops.json on every getter call.
# save() clears it, and an mtime check catches changes made outside DeckOps.
# All cache access holds _lock.

_lock = threading.Lock()
_cache = None        # cached merged dict, or None if invalidated
_cache_mtime = 0.0   # mtime of CONFIG_PATH when _cache was populated


def load() -> dict:
    """
    Load config from disk with in-memory caching.

    Returns a fresh copy of the cached config if the file's mtime hasn't
    changed since the last read. Re-reads from disk if something else
    changed the file or save() cleared the cache.

    Returns defaults if the file is missing or corrupt.
    """
    global _cache, _cache_mtime

    with _lock:
        # Does the file exist?
        try:
            current_mtime = os.path.getmtime(CONFIG_PATH)
        except OSError:
            # Missing or can't be stat'd, so use defaults
            return copy.deepcopy(DEFAULTS)

        # File unchanged, use the cache
        if _cache is not None and current_mtime == _cache_mtime:
            return copy.deepcopy(_cache)

        # No cache or stale cache, re-read from disk
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("config root is not an object")
        except ValueError:
            # Unparseable (truncated by a power loss, bad hand edit). Move it
            # aside so the next save() can't overwrite the user's setup.
            bad = f"{CONFIG_PATH}.corrupt-{datetime.now():%Y%m%d-%H%M%S}"
            try: os.replace(CONFIG_PATH, bad); _log.warning("deckops.json unreadable, moved to %s", bad)
            except OSError as ex: _log.warning("deckops.json unreadable and could not be moved aside: %s", ex)
            return copy.deepcopy(DEFAULTS)
        except IOError:
            return copy.deepcopy(DEFAULTS)
        merged = copy.deepcopy(DEFAULTS)
        merged.update(data)
        _cache = merged
        _cache_mtime = current_mtime
        return copy.deepcopy(_cache)


def save(config: dict):
    """
    Write config to disk and clear the cache.
    Creates the directory if needed.
    """
    global _cache, _cache_mtime

    with _lock:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        write_json(CONFIG_PATH, config)
        _cache = None
        _cache_mtime = 0.0


def _set(key: str, value):
    config = load()
    config[key] = value
    save(config)


def is_first_run() -> bool:
    """Returns True if setup has never been completed."""
    return not load().get("first_run_complete", False)


def set_os_type(os_type: str):
    """Save the user's operating system type.

    os_type: 'steamos', 'bazzite', 'cachyos', 'armada', or 'other_linux'
    """
    config = load()
    config["os_type"] = os_type
    save(config)


def get_deck_model() -> str | None:
    """Returns 'oled', 'lcd', 'other', 'steam_machine', or None if not yet set."""
    return load().get("deck_model")


def set_deck_model(model: str):
    """Save the user's device model.

    model: 'oled', 'lcd', 'other', or 'steam_machine'
    """
    config = load()
    config["deck_model"] = model
    save(config)


def is_lcd() -> bool:
    """True only for Steam Deck LCD hardware (Heroic/LCD launch path)."""
    return load().get("deck_model") == "lcd"


def is_other() -> bool:
    """True for non-Deck SteamOS devices (Legion Go, ROG Ally, etc.)."""
    return load().get("deck_model") == "other"


def is_steam_machine() -> bool:
    """True for Valve Steam Machine hardware (triton controller)."""
    return load().get("deck_model") == "steam_machine"


def uses_oled_path() -> bool:
    """True for devices that launch Plutonium directly.

    OLED, Other, and Steam Machine launch Plutonium through the protocol
    URL in Steam's compatdata prefix. LCD uses Heroic instead.
    Use this for launch decisions, not for picking the config folder.
    """
    return load().get("deck_model") != "lcd"


def get_other_device() -> str | None:
    """Returns the resolution key for Other and Steam Machine devices,
    e.g. '1920x1200', '1920x1080', or None.

    Steam Machine stores the resolution the user picked here too.
    """
    return load().get("other_device")


def set_other_device(device: str):
    """Save the resolution key, e.g. '1920x1200_144hz'.

    Other devices get a preset per device. Steam Machine gets the one the
    user picks on the resolution screen.
    """
    config = load()
    config["other_device"] = device
    save(config)


def get_other_device_type() -> str | None:
    """Returns the device type for controller profile selection.

    Values: 'legion_go', 'legion_go_2', 'legion_go_s', '2btn', 'generic',
            'steam_machine', or None.
    controller_profiles.py uses it to pick the profile variant.
    """
    return load().get("other_device_type")


def set_other_device_type(device_type: str):
    """Save the device type for controller profile selection.

    device_type: 'legion_go' (Go 1), 'legion_go_2' (Go 2),
                 'legion_go_s', '2btn' (ROG Ally, MSI Claw),
                 'generic', or 'steam_machine'
    """
    config = load()
    config["other_device_type"] = device_type
    save(config)


def get_model_config_dir() -> str:
    """Return the asset subdirectory for the current device's configs.

    OLED          -> 'OLED'
    LCD           -> 'LCD'
    Other         -> 'Other/<resolution>'  (e.g. 'Other/1920x1200')
    Steam Machine -> 'Other/<resolution>'  (user-picked, same assets as Other)

    Falls back to 'OLED' if deck_model is unset.
    """
    model = load().get("deck_model") or "oled"
    if model in ("other", "steam_machine"):
        device = load().get("other_device") or "1920x1200"
        return f"Other/{device}"
    return "OLED" if model == "oled" else "LCD"


def get_gyro_mode() -> str | None:
    """Returns 'on', 'off', 'hold', or 'toggle', or None if not yet set."""
    return load().get("gyro_mode")


def set_gyro_mode(mode: str):
    """Save the user's gyro preference: 'on', 'off', 'hold', or 'toggle'."""
    _set("gyro_mode", mode)


def get_offline_mode() -> bool:
    """Offline Mode: the offline launcher, Steam menu Offline entries and the
    WaW/BO1/BO2/MW3 MP bot matches. Older installs set up offline for every
    Plutonium game, so they keep it on."""
    c = load()
    if c.get("offline_mode") is None:
        on = any(e.get("lan_wrapper_path") for e in c.get("setup_games", {}).values())
        _set("offline_mode", on)
        return on
    return bool(c["offline_mode"])


def set_offline_mode(on: bool):
    _set("offline_mode", bool(on))


def set_play_mode(mode: str):
    """Save the user's play mode: 'handheld' or 'docked'."""
    _set("play_mode", mode)


def is_docked() -> bool:
    return load().get("play_mode") == "docked"


def get_external_controller() -> str | None:
    """Returns 'playstation', 'xbox', 'steamcontroller', 'other', or None if not yet set."""
    return load().get("external_controller")


def set_external_controller(controller_type: str):
    """Save the user's external controller type: 'playstation', 'xbox', 'steamcontroller', or 'other'."""
    _set("external_controller", controller_type)


def set_docked_resolution(resolution: str):
    """Save the user's docked display resolution. 'own' means the user sets it in game."""
    _set("docked_resolution", resolution)


def set_game_source(source: str):
    """Save game source preference."""
    _set("game_source", source)


def get_music_enabled() -> bool:
    """Returns True if background music is enabled."""
    return load().get("music_enabled", True)


def set_music_enabled(enabled: bool):
    """Save background music on/off preference."""
    _set("music_enabled", enabled)


def get_music_volume() -> float:
    """Returns music volume as a float between 0.0 and 1.0."""
    return load().get("music_volume", 0.4)


def set_music_volume(volume: float):
    """Save music volume, clamped to 0.0 to 1.0."""
    _set("music_volume", max(0.0, min(1.0, volume)))


def get_ge_proton_version() -> str | None:
    """Returns the installed GE-Proton version string, e.g. 'GE-Proton10-32', or None."""
    return load().get("ge_proton_version")


def set_ge_proton_version(version: str):
    """Save the installed GE-Proton version after CompatToolMapping is applied."""
    _set("ge_proton_version", version)


def get_player_name() -> str | None:
    """Returns the player's chosen in-game name, or None if not yet set."""
    return load().get("player_name")


def set_player_name(name: str):
    """Save the player's chosen in-game name."""
    _set("player_name", name.strip() if name else None)


def get_steam_display_name(steam_root: str | None = None) -> str | None:
    """
    Read the active Steam user's display name from loginusers.vdf.

    Returns the PersonaName of the account with MostRecent=1, or of the
    first account if none has it. Returns None if the file can't be read
    or parsed.

    steam_root: path to the Steam root. Defaults to ~/.local/share/Steam
    """
    if not steam_root:
        steam_root = os.path.expanduser("~/.local/share/Steam")
    vdf_path = os.path.join(steam_root, "config", "loginusers.vdf")
    if not os.path.exists(vdf_path):
        return None
    try:
        with open(vdf_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, OSError):
        return None

    # Find PersonaName and MostRecent in each account block.
    # This VDF is simple enough for regex, no full parser needed.
    first_name = None
    most_recent_name = None
    # Split into account blocks at each Steam ID header
    blocks = re.split(r'"\d{17}"\s*\{', content)
    for block in blocks[1:]:  # skip the "users" { header
        persona = re.search(r'"PersonaName"\s+"([^"]*)"', block)
        recent = re.search(r'"MostRecent"\s+"1"', block)
        if persona:
            name = persona.group(1)
            if first_name is None:
                first_name = name
            if recent:
                most_recent_name = name

    return most_recent_name or first_name


def mark_game_setup(game_key: str, client: str, source: str = "steam",
                    wrapper_path: str = None,
                    lan_wrapper_path: str = None):
    """
    Record that a game was set up.
    game_key:         e.g. 'cod4mp', 'iw4mp', 't5sp'
    client:           e.g. 'cod4x', 'iw4x', 'plutonium'
    source:           'steam' or 'own' (the install path used)
    wrapper_path:     optional path to the online launcher wrapper script
                      (OLED own games, legacy callers)
    lan_wrapper_path: optional path to the -lan bash script for Offline
                      Mode. The offline launcher uses it for all sources
                      and both hardware models.
    """
    config = load()
    entry = {
        "client": client,
        "source": source,
        "setup_at": datetime.now().isoformat(),
    }
    if wrapper_path:
        entry["wrapper_path"] = wrapper_path
    if lan_wrapper_path:
        entry["lan_wrapper_path"] = lan_wrapper_path
    config["setup_games"][game_key] = entry
    save(config)


def is_game_setup(game_key: str) -> bool:
    """Returns True if this game key has been set up (any source)."""
    return game_key in load().get("setup_games", {})


def unmark_game_setup(game_keys):
    """
    Remove one or more game keys (a string or a list) from setup_games so
    they show as 'not set up' in ManagementScreen. Used for a clean
    reinstall of a game.
    """
    if isinstance(game_keys, str):
        game_keys = [game_keys]
    config = load()
    changed = False
    for key in game_keys:
        if key in config.get("setup_games", {}):
            del config["setup_games"][key]
            changed = True
    if changed:
        save(config)


def is_game_setup_for_source(game_key: str, source: str) -> bool:
    """Returns True if this game key has been set up from the given source.
    Entries without a 'source' field count as 'steam' (older configs)."""
    entry = load().get("setup_games", {}).get(game_key)
    if entry is None:
        return False
    return entry.get("source", "steam") == source


def get_setup_games() -> dict:
    """Returns the full setup_games dict."""
    return load().get("setup_games", {})


def is_depot_patched(game_id: str) -> bool:
    return game_id in load().get("depot_patched", {})


def clear_depot_patched(game_id: str):
    config = load()
    dp = config.get("depot_patched", {})
    if game_id in dp:
        del dp[game_id]
        save(config)


def get_cod4mp_profile_type(default: str = "other") -> str:
    """
    Return the controller profile type for the CoD4 MP shortcut, based on
    the client picked during setup.

    CoD4R has native controller support, so it gets the standard gamepad
    layout. CoD4x has none and needs the KB+M "other" layout through
    Steam Input.

    Returns `default` if setup state is unavailable or the client is
    unknown. This is the only place for this check. It used to be copied
    at five call sites in controller_profiles.py and shortcut.py.
    """
    try:
        client = get_setup_games().get("cod4mp", {}).get("client")
    except Exception:
        return default
    if client == "cod4r":
        return "standard"
    if client == "cod4x":
        return "other"
    return default


def get_iw_pad(game_key: str) -> dict:
    return load().get("iw_pad", {}).get(game_key) or {}


def set_iw_pad(game_key: str, info: dict):
    config = load()
    config.setdefault("iw_pad", {})[game_key] = info
    save(config)


def mark_zd_installed(manifest_hash: str = ""):
    """Record that Zombies Declassified is installed."""
    config = load()
    config["zd_installed"] = {
        "manifest_hash": manifest_hash,
        "installed_at": datetime.now().isoformat(),
    }
    save(config)


def is_zd_installed() -> bool:
    return load().get("zd_installed") is not None


def get_zd_info() -> dict:
    return load().get("zd_installed") or {}


def unmark_zd_installed():
    config = load()
    config["zd_installed"] = None
    save(config)


def complete_first_run(steam_root: str):
    """
    Marks first run as done. Call at the end of the setup wizard.
    """
    config = load()
    config["first_run_complete"] = True
    config["steam_root"] = steam_root
    save(config)


def reset():
    """
    Delete the config and start fresh. For testing or reinstalling.
    """
    global _cache, _cache_mtime

    with _lock:
        if os.path.exists(CONFIG_PATH):
            os.remove(CONFIG_PATH)
        _cache = None
        _cache_mtime = 0.0
