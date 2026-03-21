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
  8. Write a bash wrapper script that replaces the game exe, padded to the
     original exe size so Steam's file validation does not flag it.

Progress is reported via a callback:
    on_progress(percent: int, status: str)
"""

import os
import stat
import shutil
import json
import subprocess
import urllib.request


# ── dedicated prefix ──────────────────────────────────────────────────────────
# DeckOps manages its own Wine prefix for the initial Plutonium install.
# This avoids depending on Steam to create a non-Steam game entry and gives
# us a known, stable path to copy from.

DEDICATED_PREFIX = os.path.expanduser("~/.local/share/deckops/plutonium_prefix")
PLUT_BOOTSTRAPPER_URL = "https://cdn.plutonium.pw/updater/plutonium.exe"


# ── game metadata ─────────────────────────────────────────────────────────────
# Maps DeckOps game key → (appid, config.json path key, exe name to replace)

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

# DLLs dropped by the winetricks xact verb. We copy these directly between
# prefixes instead of re-running protontricks for each game.
XACT_DLLS = [
    "xactengine2_0.dll",
    "xactengine2_1.dll",
    "xactengine2_2.dll",
    "xactengine2_3.dll",
    "xactengine2_4.dll",
    "xactengine2_5.dll",
    "xactengine2_6.dll",
    "xactengine2_7.dll",
    "xactengine2_8.dll",
    "xactengine2_9.dll",
    "xactengine3_0.dll",
    "xactengine3_1.dll",
    "xactengine3_2.dll",
    "xactengine3_3.dll",
    "xactengine3_4.dll",
    "xactengine3_5.dll",
    "xactengine3_6.dll",
    "xactengine3_7.dll",
    "xact3.dll",
    "xaudio2_0.dll",
]


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

    # Proton needs pfx/ to exist , initialise a minimal prefix structure
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
    prog(15, "Launching Plutonium , please log in, then close the window when done.")

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
# We do a full copy of the Plutonium/ folder into each game's prefix rather
# than symlinking or sharing a single install. Each prefix is its own Wine
# environment and symlinks across prefixes can cause path resolution issues.
# Full copies keep each game isolated so one prefix can't break another.

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


def _find_protontricks() -> list[str] | None:
    """
    Locate protontricks, preferring the Flatpak version.
    Returns the command prefix as a list, or None if not found.

    Preference order:
      1. Flatpak protontricks (com.github.Matoking.protontricks)
      2. Native protontricks on PATH
    """
    # Check Flatpak first , most common on Steam Deck
    try:
        result = subprocess.run(
            ["flatpak", "info", "com.github.Matoking.protontricks"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return ["flatpak", "run", "com.github.Matoking.protontricks"]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fall back to native protontricks
    try:
        result = subprocess.run(
            ["protontricks", "--version"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return ["protontricks"]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def _ensure_protontricks_sd_access():
    """
    Grant the Flatpak protontricks access to /run/media so it can see
    games installed on the SD card. Safe to call multiple times.
    Errors are swallowed silently , this is best-effort and non-fatal
    since the game prefix may still be on internal storage.
    """
    try:
        subprocess.run(
            [
                "flatpak", "override", "--user",
                "com.github.Matoking.protontricks",
                "--filesystem=/run/media",
            ],
            capture_output=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _ensure_protontricks(on_progress=None) -> bool:
    """
    Ensure protontricks is available, installing it via Flatpak if needed.
    Also applies the /run/media filesystem override for SD card access.
    Returns True if protontricks is available after this call.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if _find_protontricks() is not None:
        _ensure_protontricks_sd_access()
        return True

    prog("Installing Protontricks (required for game audio)...")
    try:
        result = subprocess.run(
            [
                "flatpak", "install", "--user", "--noninteractive",
                "flathub", "com.github.Matoking.protontricks",
            ],
            capture_output=True,
        )
        if result.returncode == 0:
            prog("Protontricks installed successfully.")
            _ensure_protontricks_sd_access()
            return True
        else:
            prog(
                "Protontricks installation failed , XACT will be skipped. "
                "Install Protontricks from Discover and rerun setup."
            )
            return False
    except FileNotFoundError:
        prog("Flatpak not found , cannot install Protontricks.")
        return False


def _install_xact(compatdata_path: str, proton_path: str,
                  steam_root: str, appid: int, game_name: str = "",
                  on_progress=None):
    """
    Install XACT into the given Wine prefix using protontricks.
    Required for audio in World at War and Black Ops.
    Skips silently if already installed.

    compatdata_path , path to this game's compatdata prefix
    proton_path     , kept for API consistency, not used
    steam_root      , kept for API consistency, not used
    appid           , Steam appid for the game (protontricks requires this)
    game_name       , display name shown in progress messages
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    label = f" for {game_name}" if game_name else ""

    if _is_xact_installed(compatdata_path):
        prog(f"XACT already installed{label}, skipping.")
        return True

    prog(f"Installing XACT audio components{label}...")

    protontricks = _find_protontricks()
    if protontricks is None:
        prog(
            "protontricks not found , skipping XACT. "
            "Install via Discover (search Protontricks) and rerun setup."
        )
        return False

    # Ensure SD card access so protontricks can find the game prefix
    _ensure_protontricks_sd_access()

    cmd = protontricks + [str(appid), "-q", "xact"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=300,
        )
        if result.returncode == 0:
            prog("XACT installed successfully.")
            return True
        else:
            # A non-zero exit from protontricks/winetricks is often just
            # a warning rather than a hard failure , verify via DLL check.
            if _is_xact_installed(compatdata_path):
                prog("XACT installed successfully.")
                return True
            prog("XACT install finished with warnings , audio may still work.")
            return False
    except subprocess.TimeoutExpired:
        prog("XACT install timed out , skipping.")
        return False


def _copy_xact_dlls(src_compatdata: str, dst_compatdata: str, on_progress=None):
    """
    Copy XACT DLLs from one prefix's system32 to another's.
    Only copies files that actually exist in src — winetricks may not
    install all versions depending on the Wine build.
    """
    src_sys32 = _system32(src_compatdata)
    dst_sys32 = _system32(dst_compatdata)
    os.makedirs(dst_sys32, exist_ok=True)
    copied = 0
    for dll in XACT_DLLS:
        src = os.path.join(src_sys32, dll)
        if os.path.exists(src) and os.path.getsize(src) > 0:
            shutil.copy2(src, os.path.join(dst_sys32, dll))
            copied += 1
    if on_progress:
        on_progress(f"Copied {copied} XACT DLLs.")


def install_xact_once(
    xact_game_keys: list[str],
    steam_root: str,
    proton_path: str,
    on_progress=None,
) -> bool:
    """
    Install XACT into the first eligible prefix, then copy DLLs to all
    remaining XACT-requiring prefixes. Avoids re-running protontricks
    (which is slow) for every game that shares the same requirement.

    Prefixes are deduped by appid — t4sp and t4mp share appid 10090 so
    only one protontricks run is needed for both.

    Returns True if XACT is available in all target prefixes after this call.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if not xact_game_keys:
        return True

    if not _ensure_protontricks(on_progress=on_progress):
        return False

    # Build deduped list of (key, appid, compatdata_path) by appid.
    seen_appids = {}
    targets = []
    for key in xact_game_keys:
        if key not in GAME_META:
            continue
        appid = GAME_META[key][0]
        if appid not in seen_appids:
            compat = os.path.join(
                steam_root, "steamapps", "compatdata", str(appid)
            )
            seen_appids[appid] = compat
            targets.append((key, appid, compat))

    if not targets:
        return True

    # Install into the first prefix via protontricks.
    primary_key, primary_appid, primary_compat = targets[0]
    prog(f"Installing XACT into primary prefix (appid {primary_appid})...")
    success = _install_xact(
        primary_compat, proton_path, steam_root,
        appid=primary_appid,
        game_name=primary_key,
        on_progress=on_progress,
    )

    if not success:
        prog("XACT install failed on primary prefix — skipping copy step.")
        return False

    # Copy DLLs to remaining prefixes instead of re-running protontricks.
    for key, appid, compat in targets[1:]:
        if _is_xact_installed(compat):
            prog(f"XACT already present in prefix {appid}, skipping.")
            continue
        prog(f"Copying XACT DLLs to prefix {appid}...")
        _copy_xact_dlls(primary_compat, compat, on_progress=on_progress)

    return True


# ── config.json ───────────────────────────────────────────────────────────────

def _write_config(plut_dir: str, game_keys: list, installed_games: dict):
    """
    Write config.json inside a prefix with the correct game install paths.
    Reads the existing config from the dedicated prefix and updates path keys.
    game_keys   , list of game keys being installed into this prefix
    installed_games , dict from detect_games.find_installed_games()
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
            data[path_key] = _wine_path(install_dir)

    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)


# ── wrapper script ────────────────────────────────────────────────────────────

def _write_wrapper(game: dict, game_key: str, steam_root: str,
                   proton_path: str, compatdata_path: str, plut_dir: str):
    """
    Replace the game exe with a bash wrapper that launches
    plutonium-launcher-win32.exe through Proton using the correct protocol.

    The original exe is backed up as <exe>.bak.
    The wrapper is padded to the original file's size so Steam's
    file validation does not flag it as changed.
    """
    install_dir    = game["install_dir"]
    _, _, exe_name = GAME_META[game_key]
    exe_path       = os.path.join(install_dir, exe_name)
    backup_path    = exe_path + ".bak"
    launcher       = os.path.join(plut_dir, "bin", "plutonium-launcher-win32.exe")
    plut_url       = f"plutonium://play/{game_key}"

    # Read original size before we overwrite
    original_size = os.path.getsize(exe_path) if os.path.exists(exe_path) else 0

    # Back up original exe
    if not os.path.exists(backup_path) and os.path.exists(exe_path):
        shutil.copy2(exe_path, backup_path)
        original_size = os.path.getsize(backup_path)

    script = (
        "#!/bin/bash\n"
        f"export STEAM_COMPAT_DATA_PATH=\"{compatdata_path}\"\n"
        f"export STEAM_COMPAT_CLIENT_INSTALL_PATH=\"{steam_root}\"\n"
        f"exec \"{proton_path}\" run \"{launcher}\" \"{plut_url}\"\n"
    )

    script_bytes = script.encode("utf-8")
    if original_size > len(script_bytes):
        script_bytes += b"\x00" * (original_size - len(script_bytes))

    with open(exe_path, "wb") as f:
        f.write(script_bytes)

    os.chmod(exe_path, os.stat(exe_path).st_mode |
             stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


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
                      on_progress=None, installed_games: dict = None,
                      protontricks_ready: bool = False):
    """
    Full install flow for a single Plutonium game.

    Assumes the user has already logged in and closed Plutonium via
    launch_bootstrapper(), and is_plutonium_ready() has returned True.

    game               , entry from detect_games.find_installed_games()
    game_key           , one of: t4sp, t4mp, t5sp, t5mp, t6zm, t6mp, iw5mp
    steam_root         , path to Steam root
    proton_path        , path to the proton executable
    compatdata_path    , path to this game's compatdata prefix
    on_progress        , optional callback(percent: int, status: str)
    protontricks_ready , True if _ensure_protontricks() has already been called
                         by the caller. Avoids redundant detection per-game.
    """
    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    # Fall back to single-game dict if caller doesn't supply full installed_games.
    # Supplying the full dict is preferred so sibling keys get correct paths.
    if installed_games is None:
        installed_games = {game_key: game}

    src_plut_dir  = get_dedicated_plut_dir()
    dest_plut_dir = _plut_dir_in_compatdata(
        steam_root, GAME_META[game_key][0]
    )

    prog(10, f"Copying Plutonium into prefix for {game['name']}...")
    _copy_plut_to_prefix(
        src_plut_dir, dest_plut_dir,
        on_progress=lambda msg: prog(40, msg),
    )

    # Install XACT into this game's prefix if required.
    # Only runs for t4/t5 titles , skipped entirely for t6/iw5.
    if game_key in XACT_GAME_KEYS:
        prog(50, f"Installing XACT audio components for {game['name']}...")
        if protontricks_ready:
            _install_xact(
                compatdata_path, proton_path, steam_root,
                appid=GAME_META[game_key][0],
                game_name=game["name"],
                on_progress=lambda msg: prog(55, msg),
            )
        else:
            prog(55, "XACT skipped , Protontricks unavailable.")

    prog(60, "Writing game path to config.json...")
    # Pass all keys that share this appid so config has all paths for this prefix.
    # installed_games must contain ALL installed games, not just the current one,
    # so sibling keys (e.g. t4sp + t4mp share appid 10090) get their paths written too.
    appid = GAME_META[game_key][0]
    keys_for_appid = [k for k, v in GAME_META.items() if v[0] == appid]
    _write_config(dest_plut_dir, keys_for_appid, installed_games)

    prog(80, "Writing launcher wrapper...")
    _write_wrapper(game, game_key, steam_root, proton_path,
                   compatdata_path, dest_plut_dir)

    prog(95, "Saving metadata...")
    _write_metadata(game["install_dir"], {
        "game_key":    game_key,
        "plut_dir":    dest_plut_dir,
        "wrapper_exe": os.path.join(game["install_dir"],
                                    GAME_META[game_key][2]),
    })

    prog(100, f"Plutonium ready for {game['name']}!")


def uninstall_plutonium(game: dict, game_key: str):
    """
    Restore the original game exe from backup and remove the
    Plutonium folder from this game's prefix.
    """
    install_dir    = game["install_dir"]
    _, _, exe_name = GAME_META[game_key]
    exe_path       = os.path.join(install_dir, exe_name)
    backup_path    = exe_path + ".bak"

    if os.path.exists(backup_path):
        shutil.move(backup_path, exe_path)

    meta     = _read_metadata(install_dir)
    plut_dir = meta.get("plut_dir", "")
    if plut_dir and os.path.isdir(plut_dir):
        shutil.rmtree(plut_dir)

    meta_file = os.path.join(install_dir, METADATA_FILE)
    if os.path.exists(meta_file):
        os.remove(meta_file)
