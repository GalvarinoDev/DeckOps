#!/usr/bin/env python3
"""
cache_cleanup.py — DeckOps LCD shader cache nuke + game launcher

Removes the entire shader cache directory for a game's appid before
launching through Heroic. LCD Plutonium games route through
cache_cleanup.py → flatpak → Heroic → Proton, so Steam's shader cache
for these appids only records activity from the Python/flatpak launcher
process — not the actual game. The cache is useless junk that
accumulates on every launch due to a Steam bug with non-Steam games.

See: https://github.com/ValveSoftware/steam-for-linux/issues/10486

Called from Steam launch options (Steam-owned games) or non-Steam shortcut
LaunchOptions (own games). Not used on OLED — OLED launches through
Steam's Proton directly and its shader cache is actually useful.

Usage:
    python3 cache_cleanup.py <game_key> <source>

    game_key  — Plutonium game key (t4sp, t4mp, t5sp, t5mp, t6mp, t6zm, iw5mp, iw5mp_ds)
    source    — "steam" or "own"

Steam source adds LD_PRELOAD to work around Steam's pinned libcurl
conflicting with the system flatpak binary.
"""

import base64
import binascii
import hashlib
import os
import shutil
import sys

from log import get_logger

_log = get_logger(__name__)



# ── Constants ────────────────────────────────────────────────────────────────

HEROIC_FLATPAK_ID = "com.heroicgameslauncher.hgl"

SHADERCACHE_DIR = os.path.expanduser(
    "~/.local/share/Steam/steamapps/shadercache"
)

# Map game key to Steam appid. Used to find the shadercache folder for
# Steam-owned games (whose cache is keyed on the Steam appid, not the
# shortcut appid).
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

# LCD own-game shortcut titles — must match HEROIC_PLUT_GAMES in
# plutonium_lcd.py exactly so the CRC-based appid resolves to the
# same shadercache directory that Steam creates for the shortcut.
_OWN_SHORTCUT_TITLES = {
    "t4sp":  "Call of Duty: World at War",
    "t4mp":  "Call of Duty: World at War - Multiplayer",
    "t5sp":  "Call of Duty: Black Ops",
    "t5mp":  "Call of Duty: Black Ops - Multiplayer",
    "t6mp":  "Call of Duty: Black Ops II - Multiplayer",
    "t6zm":  "Call of Duty: Black Ops II - Zombies",
    "iw5mp": "Call of Duty: Modern Warfare 3 (2011) - Multiplayer",
}


# ── Heroic app_name generation ───────────────────────────────────────────────
# Must match plutonium_lcd._heroic_app_name exactly.

def _heroic_app_name(game_key: str) -> str:
    digest = hashlib.sha256(f"deckops_plut_{game_key}".encode()).digest()
    b64 = base64.urlsafe_b64encode(digest)[:19].decode()
    return f"do_{b64}"


# ── Shortcut appid calculation ───────────────────────────────────────────────
# Must match shortcut._calc_shortcut_appid exactly.

def _calc_shortcut_appid(exe_path: str, name: str) -> int:
    key = (exe_path + name).encode("utf-8")
    crc = binascii.crc32(key) & 0xFFFFFFFF
    return (crc | 0x80000000) & 0xFFFFFFFF


# ── Shader cache cleanup ────────────────────────────────────────────────────

def _nuke_shader_cache_dir(appid_str: str):
    """
    Delete the entire shadercache/<appid>/ directory.

    LCD Plutonium games launch through cache_cleanup.py → flatpak →
    Heroic → Proton. Steam's shader cache for these appids only records
    Fossilize activity from the Python/flatpak launcher process, not the
    actual game (which runs inside Heroic's Proton instance). The cache
    is useless dead weight that accumulates on every launch and can
    potentially cause launch failures if it becomes corrupt.

    Safe to delete entirely — Steam recreates the directory structure
    on next launch, and the game's real shader work happens inside
    Heroic's Proton runtime which stores its cache elsewhere.
    """
    cache_dir = os.path.join(SHADERCACHE_DIR, appid_str)
    if os.path.isdir(cache_dir):
        try:
            shutil.rmtree(cache_dir)
        except OSError:
            _log.debug("cache dir removal failed", exc_info=True)


def cleanup_shader_cache(game_key: str, source: str):
    """
    Nuke the entire shader cache directory for a game. Handles both
    the Steam appid cache (for Steam-owned games) and the shortcut
    appid cache (for own games with non-Steam shortcuts).
    """
    # Always nuke the Steam appid cache if it exists
    steam_appid = STEAM_APPIDS.get(game_key)
    if steam_appid:
        _nuke_shader_cache_dir(steam_appid)

    # For own games, also nuke the shortcut appid cache. The shortcut
    # appid is CRC-derived from the exe path + title used when the
    # shortcut was created. Must match _create_heroic_steam_shortcut
    # in plutonium_lcd.py exactly.
    if source == "own":
        title = _OWN_SHORTCUT_TITLES.get(game_key)
        if title:
            appid_exe = '"/usr/bin/flatpak"'
            shortcut_appid = _calc_shortcut_appid(appid_exe, title)
            _nuke_shader_cache_dir(str(shortcut_appid))


# ── Game launch ──────────────────────────────────────────────────────────────

def launch_game(game_key: str, source: str):
    """
    Launch the Heroic flatpak for a Plutonium game and wait for it to
    finish. Uses subprocess instead of os.execv so the parent process
    (which Steam tracks as "the game") stays alive for the entire
    session. With os.execv the process becomes flatpak, which may exit
    quickly after handing off to Heroic inside the sandbox -- causing
    Steam to think the game closed immediately.

    Steam source: sets LD_PRELOAD to override Steam's pinned libcurl
    which conflicts with the system flatpak binary.
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

    env = os.environ.copy()
    if source == "steam":
        env["LD_PRELOAD"] = "/usr/lib/libcurl.so.4"

    # Kill any stale Heroic process so the flatpak launch gets a clean
    # instance. Electron's single-instance lock can cause a new flatpak
    # run to silently attach to an old instance or fail entirely.
    try:
        subprocess.run(
            ["flatpak", "kill", HEROIC_FLATPAK_ID],
            capture_output=True, timeout=5,
        )
        time.sleep(1)
    except Exception:
        _log.debug("cache rebuild trigger failed", exc_info=True)

    # Run flatpak and wait for it to exit. This keeps the parent
    # process alive so Steam sees the game as running. Without this,
    # Steam may report "launch failed" if flatpak hands off quickly.
    result = subprocess.run(flatpak_args, env=env)
    sys.exit(result.returncode)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <game_key> <source>")
        print(f"  game_key: t4sp, t4mp, t5sp, t5mp, t6mp, t6zm, iw5mp, iw5mp_ds")
        print(f"  source:   steam or own")
        sys.exit(1)

    game_key = sys.argv[1]
    source = sys.argv[2]

    if game_key not in STEAM_APPIDS:
        print(f"Unknown game key: {game_key}")
        sys.exit(1)

    if source not in ("steam", "own"):
        print(f"Unknown source: {source} (expected 'steam' or 'own')")
        sys.exit(1)

    # Nuke shader cache, then launch
    cleanup_shader_cache(game_key, source)
    launch_game(game_key, source)


if __name__ == "__main__":
    main()
