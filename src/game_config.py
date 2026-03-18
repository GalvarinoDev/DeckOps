"""
game_config.py - DeckOps game config writer

Copies pre-built config files from assets/configs/LCD or assets/configs/OLED
into the correct destination paths for each game. Overwrites whatever is
currently there.

LCD users only receive MW1 and MW2 configs.
OLED users receive MW1, MW2, WaW, BO1, MW3, and BO2 configs.
"""

import os
import glob
import shutil

# ── Paths ─────────────────────────────────────────────────────────────────────

_HERE        = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_HERE)
CONFIGS_DIR  = os.path.join(PROJECT_ROOT, "assets", "configs")


# ── Config map ────────────────────────────────────────────────────────────────
#
# Each entry maps a game key to a list of (asset_subpath, dest_resolver) pairs.
#
# asset_subpath  — path relative to assets/configs/<MODEL>/
# dest_resolver  — callable(install_dir, steam_root) -> absolute destination directory
#
# Files are copied with their original filename preserved.

def _compatdata(steam_root, appid):
    """Return the compatdata path for a given appid."""
    return os.path.join(steam_root, "steamapps", "compatdata", str(appid))


def _pfx_local(steam_root, appid, *parts):
    """Return a path inside pfx/drive_c/users/steamuser/AppData/Local/ for an appid."""
    return os.path.join(
        _compatdata(steam_root, appid),
        "pfx", "drive_c", "users", "steamuser", "AppData", "Local",
        *parts
    )


# The config map is built inside apply_game_configs so steam_root is available.
# Keys that are absent for a given model are simply not included.

_LCD_KEYS  = {"cod4sp", "cod4mp", "iw4sp", "iw4mp"}
_OLED_KEYS = {"cod4sp", "cod4mp", "iw4sp", "iw4mp", "t4sp", "t4mp", "t5sp", "t5mp", "iw5sp", "iw5mp", "t6zm", "t6mp"}


def _build_config_map(steam_root):
    """
    Returns a dict mapping game_key -> list of (asset_subpath, dest_dir) pairs.
    dest_dir will be created if it does not exist.
    """
    return {
        # ── MW1 SP (IW3SP-MOD) ────────────────────────────────────────────────
        # Config lands in players/profiles/Player/ inside the game install dir.
        # Resolved at call time via install_dir — see apply_game_configs().
        "cod4sp": [
            ("MW1/iw3sp_mod_config.cfg", None),  # dest resolved from install_dir
        ],

        # ── MW1 MP (CoD4x) ────────────────────────────────────────────────────
        # Lives inside the CoD4 compatdata prefix.
        "cod4mp": [
            (
                "MW1/config_mp.cfg",
                _pfx_local(
                    steam_root, 7940,
                    "CallofDuty4MW", "players", "profiles", "Player"
                ),
            ),
        ],

        # ── MW2 SP ────────────────────────────────────────────────────────────
        # Lives in players/ inside the game install dir.
        # Resolved at call time via install_dir — see apply_game_configs().
        "iw4sp": [
            ("MW2/config.cfg", None),
        ],

        # ── MW2 MP (iw4x) ─────────────────────────────────────────────────────
        # Lives in players/ inside the game install dir.
        # Resolved at call time via install_dir — see apply_game_configs().
        "iw4mp": [
            ("MW2/iw4x_config.cfg", None),
        ],

        # ── WaW SP + MP (Plutonium t4) ────────────────────────────────────────
        # Both configs live in the same Plutonium storage path.
        "t4sp": [
            (
                "WaW/config.cfg",
                _pfx_local(
                    steam_root, 10090,
                    "Plutonium", "storage", "t4", "players", "profiles", "$$$"
                ),
            ),
        ],
        "t4mp": [
            (
                "WaW/config_mp.cfg",
                _pfx_local(
                    steam_root, 10090,
                    "Plutonium", "storage", "t4", "players", "profiles", "$$$"
                ),
            ),
        ],

        # ── BO1 SP (Plutonium t5, appid 42700) ────────────────────────────────
        "t5sp": [
            (
                "BO1/config.cfg",
                _pfx_local(
                    steam_root, 42700,
                    "Plutonium", "storage", "t5", "players"
                ),
            ),
        ],

        # ── BO1 MP (Plutonium t5, appid 42710) ────────────────────────────────
        "t5mp": [
            (
                "BO1/config_mp.cfg",
                _pfx_local(
                    steam_root, 42710,
                    "Plutonium", "storage", "t5", "players"
                ),
            ),
        ],

        # ── MW3 SP (via Steam, appid 42690) ───────────────────────────────────
        # Config lands in players2/ inside the game install dir.
        # Resolved at call time via install_dir — see apply_game_configs().
        "iw5sp": [
            ("MW3/config.cfg", None),
        ],

        # ── MW3 MP (Plutonium iw5, appid 42690) ───────────────────────────────
        # Lives inside the Plutonium storage path for iw5.
        "iw5mp": [
            (
                "MW3/config_mp.cfg",
                _pfx_local(
                    steam_root, 42690,
                    "Plutonium", "storage", "iw5", "players"
                ),
            ),
        ],

        # ── BO2 ZM (Plutonium t6, appid 212910) ───────────────────────────────
        # BO2 uses separate appids for ZM and MP — each has its own compatdata
        # prefix. ZM lives under appid 212910.
        "t6zm": [
            (
                "BO2/plutonium_zm.cfg",
                _pfx_local(
                    steam_root, 212910,
                    "Plutonium", "storage", "t6", "players"
                ),
            ),
        ],

        # ── BO2 MP (Plutonium t6, appid 202990) ───────────────────────────────
        # MP lives under its own separate appid 202990.
        "t6mp": [
            (
                "BO2/plutonium_mp.cfg",
                _pfx_local(
                    steam_root, 202990,
                    "Plutonium", "storage", "t6", "players"
                ),
            ),
        ],
    }


# ── Install-dir based dest resolvers ──────────────────────────────────────────

def _dest_from_install(game_key, install_dir):
    """
    For game keys whose destination is relative to install_dir,
    return the correct absolute destination directory.
    Returns None for keys that use a fixed compatdata path instead.
    """
    if game_key == "cod4sp":
        return os.path.join(install_dir, "players", "profiles", "Player")
    if game_key in ("iw4sp", "iw4mp"):
        return os.path.join(install_dir, "players")
    if game_key == "iw5sp":
        return os.path.join(install_dir, "players2")
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def apply_game_configs(selected_keys, installed_games, steam_root,
                       deck_model, on_progress=None):
    """
    Copy pre-built config files into the correct destination for each
    selected game key, based on the user's deck model.

    selected_keys   — list of game keys the user selected to install
    installed_games — dict from detect_games.find_installed_games()
    steam_root      — path to Steam root
    deck_model      — 'oled' or 'lcd'
    on_progress     — optional callback(msg: str)

    Returns (applied, skipped, failed) counts.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    applied  = 0
    skipped  = 0
    failed   = 0

    model_dir   = "OLED" if deck_model == "oled" else "LCD"
    allowed_keys = _OLED_KEYS if deck_model == "oled" else _LCD_KEYS
    config_map  = _build_config_map(steam_root)

    for key in selected_keys:
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
                dest_dir = fixed_dest
            else:
                if not install_dir:
                    prog(f"  - {key}: install_dir unknown, skipping")
                    skipped += 1
                    continue
                dest_dir = _dest_from_install(key, install_dir)
                if not dest_dir:
                    prog(f"  - {key}: could not resolve destination, skipping")
                    skipped += 1
                    continue

            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, os.path.basename(src))

            try:
                shutil.copy2(src, dest)
                prog(f"  + {key}: {os.path.basename(src)} -> {dest_dir}")
                applied += 1
            except Exception as ex:
                prog(f"  - {key}: failed to copy {os.path.basename(src)}: {ex}")
                failed += 1

    prog(f"Game configs: {applied} applied, {skipped} skipped, {failed} failed.")
    return applied, skipped, failed
