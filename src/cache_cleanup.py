#!/usr/bin/env python3
"""
cache_cleanup.py: DeckOps LCD shader cache cleanup and game launcher

Deletes the whole shader cache folder for a game's appid, then launches
the game through Heroic. LCD Plutonium games run as
cache_cleanup.py → flatpak → Heroic → Proton, so Steam's shader cache
for these appids only records the Python/flatpak launcher process, not
the game. A Steam bug with non-Steam games makes this useless cache
grow on every launch.

Called from Steam launch options (Steam games) or non-Steam shortcut
LaunchOptions (own games). OLED does not use it. OLED launches through
Steam's Proton directly, where the shader cache does its job.

Usage:
    python3 cache_cleanup.py <game_key> <source> [Steam's %command%...]

    game_key: Plutonium game key (t4sp, t4mp, t5sp, t5mp, t6mp, t6zm, iw5mp, iw5mp_ds)
    source:   "steam" or "own"

When Steam passes its command (Steam games), the picked launch menu
entry decides what runs. Plutonium Online and Offline launch the matching
Heroic entry. Any other entry runs Steam's command unchanged (the stock
game).

For Steam source, LD_PRELOAD works around Steam's pinned libcurl, which
conflicts with the system flatpak binary.
"""

import binascii
import os
import shutil
import sys

from log import get_logger, setup_logging
from steam_common import calc_shortcut_appid as _calc_shortcut_appid, heroic_app_name as _heroic_app_name

_log = get_logger("cache_cleanup")



# --- Constants

HEROIC_FLATPAK_ID = "com.heroicgameslauncher.hgl"

SHADERCACHE_DIR = os.path.expanduser(
    "~/.local/share/Steam/steamapps/shadercache"
)

# Game key to Steam appid. Steam games keep their shadercache folder
# under the Steam appid, not the shortcut appid.
STEAM_APPIDS = {
    "t4sp":  "10090",
    "t4mp":  "10090",
    "t5sp":  "42700",
    "t5mp":  "42710",
    "t6zm":  "212910",
    "t6mp":  "202990",
    "iw5mp": "42690",
    "iw5mp_ds": "42750",
}

# LCD own-game shortcut titles. These must match HEROIC_PLUT_GAMES in
# plutonium_lcd.py exactly, so the CRC appid points at the same
# shadercache folder Steam creates for the shortcut.
_OWN_SHORTCUT_TITLES = {
    "t4sp":  "Call of Duty: World at War",
    "t4mp":  "Call of Duty: World at War - Multiplayer",
    "t5sp":  "Call of Duty: Black Ops",
    "t5mp":  "Call of Duty: Black Ops - Multiplayer",
    "t6mp":  "Call of Duty: Black Ops II - Multiplayer",
    "t6zm":  "Call of Duty: Black Ops II - Zombies",
    "iw5mp": "Call of Duty: Modern Warfare 3 (2011) - Multiplayer",
}


# --- Shortcut appid calculation
# Must match shortcut._calc_shortcut_appid exactly.

# --- Shader cache cleanup

def _nuke_shader_cache_dir(appid_str: str):
    """
    Delete the whole shadercache/<appid>/ folder.

    LCD Plutonium games launch through cache_cleanup.py → flatpak →
    Heroic → Proton. Steam's shader cache for these appids only records
    Fossilize activity from the Python/flatpak launcher process. The game
    itself runs inside Heroic's Proton. The cache grows on every launch
    and can cause launch failures if it gets corrupt.

    Deleting it is safe. Steam recreates the folders on the next launch,
    and Heroic's Proton keeps the game's real shader cache elsewhere.
    """
    cache_dir = os.path.join(SHADERCACHE_DIR, appid_str)
    if os.path.isdir(cache_dir):
        try:
            shutil.rmtree(cache_dir)
        except OSError:
            _log.debug("cache dir removal failed", exc_info=True)


def cleanup_shader_cache(game_key: str, source: str):
    """
    Delete a game's shader cache folders: the Steam appid cache (Steam
    games) and the shortcut appid cache (own games with non-Steam
    shortcuts).
    """
    # Steam appid cache, if there is one
    steam_appid = STEAM_APPIDS.get(game_key)
    if steam_appid:
        _nuke_shader_cache_dir(steam_appid)

    # Own games also have a shortcut appid cache. The shortcut appid is
    # a CRC of the exe path and title the shortcut was created with, so
    # this must match _create_heroic_steam_shortcut in plutonium_lcd.py
    # exactly.
    if source == "own":
        title = _OWN_SHORTCUT_TITLES.get(game_key)
        if title:
            appid_exe = '"/usr/bin/flatpak"'
            shortcut_appid = _calc_shortcut_appid(appid_exe, title)
            _nuke_shader_cache_dir(str(shortcut_appid))


# --- Steam shader pre-cache environment strip
# When Steam launches a Steam game through cache_cleanup.py, it adds its
# shader pre-caching environment (precompiled RADV pipeline DBs, DXVK
# state cache path, Fossilize capture layer, AMDVLK pipeline cache) for
# the vanilla game's appid. Those vars pass through flatpak run into
# Heroic's Proton, so the game loads shaders precompiled for the vanilla
# game on Steam's own Proton/mesa versions. On LCD this shows brief
# artifacts (small black/red/white squares) whenever Steam has
# downloaded precompiled shaders for the appid. Without these vars the
# game uses mesa's own cache inside the Heroic flatpak, which matches
# the runtime that renders the game.

_STEAM_SHADER_ENV_VARS = (
    "MESA_DISK_CACHE_READ_ONLY_FOZ_DBS",
    "MESA_DISK_CACHE_SINGLE_FILE",
    "MESA_SHADER_CACHE_DIR",
    "MESA_SHADER_CACHE_MAX_SIZE",
    "MESA_GLSL_CACHE_DIR",
    "MESA_GLSL_CACHE_MAX_SIZE",
    "DXVK_STATE_CACHE_PATH",
    "ENABLE_VK_LAYER_VALVE_steam_fossilize_1",
    "STEAM_FOSSILIZE_DUMP_PATH",
    "STEAM_FOSSILIZE_DUMP_PATH_READ_ONLY",
    "FOSSILIZE_APPLICATION_INFO_FILTER_PATH",
    "AMD_VK_PIPELINE_CACHE_PATH",
    "AMD_VK_PIPELINE_CACHE_FILENAME",
    "AMD_VK_USE_PIPELINE_CACHE",
    "__GL_SHADER_DISK_CACHE_APP_NAME",
    "__GL_SHADER_DISK_CACHE_PATH",
    "__GL_SHADER_DISK_CACHE_READ_ONLY_APP_NAME",
    "__GL_SHADER_DISK_CACHE_SKIP_CLEANUP",
)


def _strip_steam_shader_env(env: dict) -> dict:
    """
    Remove Steam's shader pre-cache vars and disable the Fossilize
    capture layer, so the game in Heroic uses only its own caches.
    Own-game launches don't have these vars, so nothing changes there.
    """
    for var in _STEAM_SHADER_ENV_VARS:
        env.pop(var, None)
    # Also disable the Fossilize layer outright, in case its manifest
    # gets loaded without the enable var.
    env["DISABLE_VK_LAYER_VALVE_steam_fossilize_1"] = "1"
    return env


# --- Game launch

def launch_game(game_key: str, source: str):
    """
    Launch the Heroic flatpak for a Plutonium game and wait for it to
    finish. subprocess keeps the parent process (which Steam tracks as
    "the game") alive for the whole session. With os.execv the process
    becomes flatpak, which can exit soon after it hands off to Heroic
    inside the sandbox, and Steam then thinks the game closed at once.

    For Steam source, LD_PRELOAD overrides Steam's pinned libcurl, which
    conflicts with the system flatpak binary.
    """
    import subprocess
    import time

    app_name = _heroic_app_name(game_key)

    heroic_url = f"heroic://launch?appName={app_name}&runner=sideload"

    flatpak_args = [
        "/usr/bin/flatpak", "run",
        HEROIC_FLATPAK_ID,
        "--no-gui", "--no-sandbox",
        heroic_url,
    ]

    env = _strip_steam_shader_env(os.environ.copy())
    if source == "steam":
        env["LD_PRELOAD"] = "/usr/lib/libcurl.so.4"

    # Kill any old Heroic process first. Electron's single-instance lock
    # can make a new flatpak run attach to an old instance without a
    # word, or fail.
    try:
        subprocess.run(
            ["flatpak", "kill", HEROIC_FLATPAK_ID],
            capture_output=True, timeout=5,
        )
        time.sleep(1)
    except Exception:
        _log.debug("cache rebuild trigger failed", exc_info=True)

    # Wait for flatpak to exit, so Steam sees the game as running.
    # Otherwise Steam can report "launch failed" when flatpak hands off
    # quickly.
    result = subprocess.run(flatpak_args, env=env)
    sys.exit(result.returncode)


# --- Main

def main():
    setup_logging()
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <game_key> <source>")
        print(f"  game_key: t4sp, t4mp, t5sp, t5mp, t6mp, t6zm, iw5mp, iw5mp_ds")
        print(f"  source:   steam or own")
        sys.exit(1)

    game_key = sys.argv[1]
    source = sys.argv[2]
    cmd = sys.argv[3:]

    if game_key not in STEAM_APPIDS:
        print(f"Unknown game key: {game_key}")
        sys.exit(1)

    if source not in ("steam", "own"):
        print(f"Unknown source: {source} (expected 'steam' or 'own')")
        sys.exit(1)

    lan = None
    if cmd:
        from plutonium import STEAM_MENU_EXES, GAME_META
        from steam_appinfo import VANILLA_TAG
        menu = {n: (k, i == 1) for k, names in STEAM_MENU_EXES.items()
                for i, n in enumerate(names)}
        # Stock exe without the tag means Steam dropped our menu (add_steam_menu tags
        # the stock entry), so plain Play runs that game's Plutonium Online
        if VANILLA_TAG not in cmd:
            for k in STEAM_MENU_EXES:
                a = next((a for a in cmd if os.path.basename(a) == GAME_META[k][2]), None)
                if a and os.path.exists(os.path.join(os.path.dirname(a), STEAM_MENU_EXES[k][0])):
                    menu[GAME_META[k][2]] = (k, False)
        hit = next(((menu[os.path.basename(a)], a) for a in cmd
                    if os.path.basename(a) in menu), None)
        if not hit:
            cmd = [a for a in cmd if a != VANILLA_TAG]
            os.execvp(cmd[0], cmd)  # stock launch menu entry
        (game_key, offline), path = hit  # WaW SP/MP share one appid and launch option
        lan = path if offline else None

    # Heroic's prefix holds the only real Plutonium copy. Never block the launch
    try:
        import plutonium_update as pu
        from plutonium_lcd import get_shared_plut_dir
        d = get_shared_plut_dir()
        if os.path.isdir(d):
            pu.update(d, _log.info)
    except Exception as ex:
        _log.warning("Plutonium update skipped: %s", ex)

    # Plutonium Offline: the entry's file opens the DeckOps: Plutonium Offline launcher.
    # It runs here on the host, not through Heroic.
    if lan:
        os.execvp("bash", ["bash", lan])

    # Clear the shader cache, then launch
    cleanup_shader_cache(game_key, source)
    launch_game(game_key, source)


if __name__ == "__main__":
    main()
