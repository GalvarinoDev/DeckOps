"""
config.py - DeckOps configuration manager

Handles reading and writing deckops.json which lives at:
    ~/DeckOps/deckops.json

The config file tracks:
    - Whether first-time setup has been completed
    - Which Deck model the user has (oled or lcd)
    - Which games have been set up and when
    - The Steam root path found during setup
"""

import os
import json
from datetime import datetime

CONFIG_PATH = os.path.expanduser("~/DeckOps/deckops.json")

DEFAULTS = {
    "first_run_complete": False,
    "deck_model": None,          # "oled" or "lcd"
    "gyro_mode":  None,          # "hold" or "toggle"
    "ge_proton_version": None,   # e.g. "GE-Proton10-32"
    "steam_root": None,
    "setup_games": {},           # key: game key, value: { "client": "cod4x"|"iw4x"|"plutonium", "setup_at": timestamp }
    "music_enabled": True,       # background music on/off
    "music_volume":  0.4,        # 0.0 to 1.0
}


def load() -> dict:
    """
    Load config from disk. Returns defaults if file doesn't exist yet.
    """
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        # Merge with defaults so new keys are always present
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, IOError):
        return dict(DEFAULTS)


def save(config: dict):
    """
    Write config to disk. Creates the directory if needed.
    """
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def is_first_run() -> bool:
    """Returns True if setup has never been completed."""
    return not load().get("first_run_complete", False)


def get_deck_model() -> str | None:
    """Returns 'oled', 'lcd', or None if not yet set."""
    return load().get("deck_model")


def set_deck_model(model: str):
    """Save the user's Deck model. model should be 'oled' or 'lcd'."""
    config = load()
    config["deck_model"] = model
    save(config)


def is_oled() -> bool:
    return load().get("deck_model") == "oled"


def get_gyro_mode() -> str | None:
    """Returns 'hold', 'toggle', or None if not yet set."""
    return load().get("gyro_mode")


def set_gyro_mode(mode: str):
    """Save the user's gyro preference. mode should be 'hold' or 'toggle'."""
    config = load()
    config["gyro_mode"] = mode
    save(config)


def get_music_enabled() -> bool:
    """Returns True if background music is enabled."""
    return load().get("music_enabled", True)


def set_music_enabled(enabled: bool):
    """Save background music on/off preference."""
    config = load()
    config["music_enabled"] = enabled
    save(config)


def get_music_volume() -> float:
    """Returns music volume as a float between 0.0 and 1.0."""
    return load().get("music_volume", 0.4)


def set_music_volume(volume: float):
    """Save music volume. Clamped to 0.0 - 1.0."""
    config = load()
    config["music_volume"] = max(0.0, min(1.0, volume))
    save(config)


def get_ge_proton_version() -> str | None:
    """Returns the installed GE-Proton version string, e.g. 'GE-Proton10-32', or None."""
    return load().get("ge_proton_version")


def set_ge_proton_version(version: str):
    """Save the installed GE-Proton version after CompatToolMapping is applied."""
    config = load()
    config["ge_proton_version"] = version
    save(config)


def mark_game_setup(game_key: str, client: str):
    """
    Record that a game has been set up successfully.
    game_key — e.g. 'cod4mp', 'iw4mp', 't5sp'
    client   — e.g. 'cod4x', 'iw4x', 'plutonium'
    """
    config = load()
    config["setup_games"][game_key] = {
        "client": client,
        "setup_at": datetime.now().isoformat(),
    }
    save(config)


def is_game_setup(game_key: str) -> bool:
    """Returns True if this game key has been set up."""
    return game_key in load().get("setup_games", {})


def get_setup_games() -> dict:
    """Returns the full setup_games dict."""
    return load().get("setup_games", {})


def complete_first_run(steam_root: str):
    """
    Call this at the end of the setup wizard to mark first run as done.
    """
    config = load()
    config["first_run_complete"] = True
    config["steam_root"] = steam_root
    save(config)


def reset():
    """
    Wipe the config and start fresh. Useful for testing or reinstalling.
    """
    if os.path.exists(CONFIG_PATH):
        os.remove(CONFIG_PATH)
