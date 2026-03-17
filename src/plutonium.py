"""
plutonium.py - DeckOps installer for Plutonium
(Call of Duty: MW3, World at War, Black Ops, Black Ops II)

Flow:
  1. Download plutonium.exe into a dedicated DeckOps-managed Wine prefix.
  2. Launch it through Proton so the user can log in and let Plutonium
     download its full client.
  3. Wait for user confirmation that they have logged in and closed Plutonium.
  4. Verify by checking that the storage/ folder exists in the prefix.
  5. Copy the entire Plutonium/ folder into each selected game's prefix.
  6. If the game requires XACT (t4/t5 titles), install it into that prefix.
  7. Write config.json in each prefix with the correct game install paths.
  8. Set a Steam launch option on the game's appid that redirects the original
     exe to plutonium-launcher-win32.exe with the correct protocol URL.
     No exe replacement or backup needed — the original exe is untouched.

Progress is reported via a callback:
    on_progress(percent: int, status: str)
"""

import os
import shutil
import json
import subprocess
import urllib.request


# ── dedicated prefix ──────────────────────────────────────────────────────────
# DeckOps manages its own Wine prefix for the initial Plutonium install.
# This avoids depending on Steam to create a non-Steam game entry and gives
# us a known, stable path to copy from.

DEDICATED_PREFIX      = os.path.expanduser("~/.local/share/deckops/plutonium_prefix")
PLUT_BOOTSTRAPPER_URL = "https://cdn.plutonium.pw/updater/plutonium.exe"


# ── game metadata ─────────────────────────────────────────────────────────────
# Maps DeckOps game key -> (appid, config.json path key, original exe name)

GAME_META = {
    "t4sp":  (10090,  "t4Path",  "CoDWaW.exe"),
    "t4mp":  (10090,  "t4Path",  "CoDWaWmp.exe"),
    "t5sp":  (42700,  "t5Path",  "BlackOps.exe"),
    "t5mp":  (42710,  "t5Path",  "BlackOpsMP.exe"),
    "t6zm":  (212910, "t6Path",  "t6zm.exe"),
    "t6mp":  (202990, "t6Path",  "t6mp.exe"),
    "iw5mp": (42690,  "iw5Path", "iw5mp.exe"),
}

METADATA_FILE = "deckops_plutonium.json"

# Games that require XACT for audio to work correctly under Proton.
# Matches the xact=True flags in detect_games.py.
XACT_GAME_KEYS = {"t4sp", "t4mp", "t5sp", "t5mp"}

# WaW shares appid 10090 for SP and MP. We default to SP (t4sp) since
# MP is handled by the non-Steam shortcut.
WAW_DEFAULT_KEY = "t4sp"


# ── path helpers ──────────────────────────────────────────────────────────────

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


def _plut_launcher_in_compatdata(steam_root: str, appid: int) -> str:
    """Return the path to plutonium-launcher-win32.exe inside a compatdata prefix."""
    return os.path.join(
        _plut_dir_in_compatdata(steam_root, appid),
        "bin", "plutonium-launcher-win32.exe",
    )


def _wine_path(linux_path: str) -> str:
    """Convert a Linux path to Wine Z: drive notation."""
    return "Z:" + linux_path.replace("/", "\\")


def _system32(compatdata_path: str) -> str:
    """Return the system32 path inside a Wine prefix."""
    return os.path.join(compatdata_path, "pfx", "drive_c", "windows", "system32")


# ── dedicated prefix helpers ──────────────────────────────────────────────────

def get_dedicated_plut_dir() -> str:
    """Return the Plutonium/ folder inside DeckOps's dedicated prefix."""
    return _plut_dir_in_prefix(DEDICATED_PREFIX)


def is_plutonium_ready() -> bool:
    """
    Returns True if the user has logged in and Plutonium has downloaded
    its client files. We check for the storage/ folder which is only
    created after a successful login.
    """
    storage = os.path.join(get_dedicated_plut_dir(), "storage")
    if not os.path.isdir(storage):
        return False
    # Must have at least one game subfolder inside storage/
    return any(
        os.path.isdir(os.path.join(storage, d))
        for d in os.listdir(storage)
    )


# ── bootstrapper ──────────────────────────────────────────────────────────────

def launch_bootstrapper(proton_path: str, on_progress=None):
    """
    Download plutonium.exe into the dedicated prefix and launch it through
    Proton. Blocks until the user closes the Plutonium window.

    The UI should display instructions to the user before calling this,
    and show a confirmation button after it returns.
    """
    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    plut_dir = get_dedicated_plut_dir()
    os.makedirs(plut_dir, exist_ok=True)
    os.makedirs(DEDICATED_PREFIX, exist_ok=True)

    bootstrapper = os.path.join(plut_dir, "plutonium.exe")

    prog(5, "Downloading Plutonium bootstrapper...")
    _headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }
    import time
    for attempt in range(3):
        try:
            req = urllib.request.Request(PLUT_BOOTSTRAPPER_URL, headers=_headers)
            with urllib.request.urlopen(req, timeout=60) as r, open(bootstrapper, "wb") as f:
                f.write(r.read())
            break
        except Exception as ex:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

    prog(15, "Launching Plutonium — please log in, then close the window when done.")

    env = os.environ.copy()
    env["STEAM_COMPAT_DATA_PATH"]           = DEDICATED_PREFIX
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


# ── copy to game prefix ───────────────────────────────────────────────────────

def _copy_plut_to_prefix(src_plut_dir: str, dest_plut_dir: str,
                          on_progress=None):
    """Copy the entire Plutonium/ folder from src to dest."""
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if os.path.exists(dest_plut_dir):
        shutil.rmtree(dest_plut_dir)

    shutil.copytree(src_plut_dir, dest_plut_dir)
    prog(f"Copied Plutonium to {dest_plut_dir}")


# ── xact ──────────────────────────────────────────────────────────────────────

def _is_xact_installed(compatdata_path: str) -> bool:
    """
    Check whether XACT is installed in a given Wine prefix.
    We look for xactengine2_0.dll and xact3.dll in system32.
    Both must be present and non-empty to be considered installed.
    """
    sys32 = _system32(compatdata_path)
    dlls  = ["xactengine2_0.dll", "xact3.dll"]
    found = [
        os.path.join(sys32, dll) for dll in dlls
        if os.path.exists(os.path.join(sys32, dll))
           and os.path.getsize(os.path.join(sys32, dll)) > 0
    ]
    return len(found) == len(dlls)


def _install_xact(compatdata_path: str, proton_path: str,
                  steam_root: str, on_progress=None):
    """
    Install XACT into the given Wine prefix using winetricks.
    Required for audio in World at War and Black Ops.
    Skips silently if already installed.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if _is_xact_installed(compatdata_path):
        prog("XACT already installed - skipping.")
        return True

    prog("Installing XACT (required for game audio)...")

    env = os.environ.copy()
    env["STEAM_COMPAT_DATA_PATH"]           = compatdata_path
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = steam_root
    env["WINEPREFIX"]                       = os.path.join(compatdata_path, "pfx")

    try:
        result = subprocess.run(
            ["winetricks", "--unattended", "xact"],
            env=env,
            timeout=180,
        )
        if result.returncode == 0:
            prog("XACT installed successfully.")
            return True
        else:
            prog("XACT install finished with warnings - audio may still work.")
            return False
    except FileNotFoundError:
        prog("winetricks not found - skipping XACT. Install with: sudo pacman -S winetricks")
        return False
    except subprocess.TimeoutExpired:
        prog("XACT install timed out - skipping.")
        return False


# ── config.json ───────────────────────────────────────────────────────────────

def _write_config(plut_dir: str, game_keys: list, installed_games: dict):
    """
    Write config.json inside a prefix with the correct game install paths.
    Reads the existing config from the dedicated prefix and updates path keys.
    game_keys       — list of game keys being installed into this prefix
    installed_games — dict from detect_games.find_installed_games()
    """
    config_path = os.path.join(plut_dir, "config.json")

    if os.path.exists(config_path):
        with open(config_path) as f:
            data = json.load(f)
    else:
        data = {}

    for key in game_keys:
        if key not in GAME_META:
            continue
        _, path_key, _ = GAME_META[key]
        game        = installed_games.get(key, {})
        install_dir = game.get("install_dir", "")
        if install_dir:
            data[path_key] = _wine_path(install_dir)

    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)


# ── launch options ────────────────────────────────────────────────────────────

def _set_launch_option(steam_root: str, game_key: str, on_progress=None):
    """
    Set a Steam launch option on the game's appid that redirects the original
    exe to plutonium-launcher-win32.exe with the correct protocol URL.

    Uses the same bash substitution pattern as iw3sp and iw4x so the original
    exe is never touched. WaW (appid 10090) defaults to SP (t4sp) since MP
    is handled by the non-Steam shortcut.

    Must be called while Steam is closed.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    from wrapper import set_launch_options

    appid, _, exe_name = GAME_META[game_key]

    # WaW SP and MP share appid 10090 — always write the SP launch option
    # so the Steam play button defaults to Singleplayer/Campaign.
    if appid == 10090:
        effective_key = WAW_DEFAULT_KEY
        _, _, exe_name = GAME_META[effective_key]
    else:
        effective_key = game_key

    launcher = _plut_launcher_in_compatdata(steam_root, appid)
    plut_url = f"plutonium://play/{effective_key}"

    # Redirect the original exe to the Plutonium launcher via bash substitution.
    # The original exe is never modified.
    launch_option = (
        f"bash -c 'exec \"${{@/{exe_name}/{launcher}}}\" \"{plut_url}\"' -- %command%"
    )

    try:
        set_launch_options(steam_root, str(appid), launch_option)
        prog(f"  + Launch option set for appid {appid} ({effective_key})")
    except Exception as ex:
        prog(f"  - Could not set launch option for {game_key}: {ex}")


# ── metadata ──────────────────────────────────────────────────────────────────

def _write_metadata(install_dir: str, data: dict):
    path = os.path.join(install_dir, METADATA_FILE)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _read_metadata(install_dir: str) -> dict:
    path = os.path.join(install_dir, METADATA_FILE)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


# ── public API ────────────────────────────────────────────────────────────────

def install_plutonium(game: dict, game_key: str, steam_root: str,
                      proton_path: str, compatdata_path: str,
                      on_progress=None, installed_games: dict = None):
    """
    Full install flow for a single Plutonium game.

    Assumes the user has already logged in and closed Plutonium via
    launch_bootstrapper(), and is_plutonium_ready() has returned True.

    game            — entry from detect_games.find_installed_games()
    game_key        — one of: t4sp, t4mp, t5sp, t5mp, t6zm, t6mp, iw5mp
    steam_root      — path to Steam root
    proton_path     — path to the proton executable (kept for XACT)
    compatdata_path — path to this game's compatdata prefix
    on_progress     — optional callback(percent: int, status: str)
    """
    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    if installed_games is None:
        installed_games = {game_key: game}

    dest_plut_dir = _plut_dir_in_compatdata(
        steam_root, GAME_META[game_key][0]
    )

    prog(10, f"Copying Plutonium into prefix for {game['name']}...")
    _copy_plut_to_prefix(
        get_dedicated_plut_dir(), dest_plut_dir,
        on_progress=lambda msg: prog(40, msg),
    )

    # Install XACT into this game's prefix if required.
    # Only runs for t4/t5 titles - skipped entirely for t6/iw5.
    if game_key in XACT_GAME_KEYS:
        prog(50, f"Installing XACT audio components for {game['name']}...")
        _install_xact(
            compatdata_path, proton_path, steam_root,
            on_progress=lambda msg: prog(55, msg),
        )

    prog(60, "Writing game path to config.json...")
    appid          = GAME_META[game_key][0]
    keys_for_appid = [k for k, v in GAME_META.items() if v[0] == appid]
    _write_config(dest_plut_dir, keys_for_appid, installed_games)

    prog(80, "Setting Steam launch option...")
    _set_launch_option(
        steam_root, game_key,
        on_progress=lambda msg: prog(85, msg),
    )

    prog(95, "Saving metadata...")
    _write_metadata(game["install_dir"], {
        "game_key": game_key,
        "plut_dir": dest_plut_dir,
    })

    prog(100, f"Plutonium ready for {game['name']}!")


def uninstall_plutonium(game: dict, game_key: str):
    """
    Remove the Plutonium folder from this game's prefix and clear metadata.
    No exe restore needed — the original exe was never modified.
    """
    meta     = _read_metadata(game["install_dir"])
    plut_dir = meta.get("plut_dir", "")
    if plut_dir and os.path.isdir(plut_dir):
        shutil.rmtree(plut_dir)

    meta_file = os.path.join(game["install_dir"], METADATA_FILE)
    if os.path.exists(meta_file):
        os.remove(meta_file)
