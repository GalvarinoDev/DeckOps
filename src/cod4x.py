"""
cod4x.py - DeckOps installer for CoD4x (Call of Duty 4: Modern Warfare)

Runs the official CoD4x 21.3 setup.exe through Proton in silent mode.
ensure_all_prefix_deps sets up the prefix (7940) before this module runs,
so this module does no prefix management.

How the CoD4x chain-loader works:
  1. The CoD4x mss32.dll replaces the one in the game directory, and the
     original is kept as miles32.dll. CoD4 loads mss32.dll at startup
     through its PE imports, so this is where the mod gets in.
  2. The new mss32.dll loads launcher.dll from AppData/Local/CallofDuty4MW/bin/.
  3. launcher.dll loads cod4x_021.dll from AppData/Local/CallofDuty4MW/bin/cod4x_021/.
  4. cod4x_021.dll patches the game in memory to become CoD4x 21.3.

Install flow:
  1. Write registry keys so Steam skips the DirectX/Punkbuster first-launch installers
  1b. Write the CoD4 install path registry key so setup.exe can find the game
  2. Download the official CoD4x setup.exe
  3. Run setup.exe through Proton with /DIR= pointing at the game directory
  3b. Copy the Inno Setup log to the DeckOps logs folder
  3c. Move the chain-loader from the prefix to the game directory (fallback)
  4. Write the registry keys again, in case the Proton run replaced user.reg
  5. Check the chain-loader
  6. Delete servercache.dat
  7. Write metadata
"""

import os
import re
import glob
import shutil
import subprocess
import tempfile

from net import download as _download, DownloadError
from steam_common import nvme_compatdata as _nvme_compatdata, linux_to_wine_path as _linux_to_wine_path, write_json

from log import get_logger

_log = get_logger(__name__)


# --- constants

_SETUP_EXE_URL = "https://cod4x.ovh/uploads/short-url/2V3RsE0Pp5Jakc1VE9Yuh5yb4lE.exe"

METADATA_FILE = "deckops_cod4x.json"

# --- Archive.org fallback
# If the setup.exe download from cod4x.ovh fails (60 s timeout), download
# this archived copy of the official 21.3 installer instead. The rest of
# the setup.exe flow is the same.
_ARCHIVE_FALLBACK_URL = (
    "https://archive.org/download/co-d-4x.-21.3.-setup/CoD4x.21.3.Setup.exe"
)

# Both URLs serve the same 21.3 installer. If cod4x.ovh ever ships a new
# build, the mismatch drops to the archive.org copy. Update this hash then.
_SETUP_EXE_DIGEST = "sha256:bcda78657050e359d9116477758d1d8167410d6d60a6b40f1bb5ec9d0cafb1f7"

# --- GitHub fallback (disabled)
# The archive.org fallback above replaced this. Kept for reference.
#
# _GITHUB_RELEASE_BASE = (
#     "https://github.com/callofduty4x/CoD4x_Client_pub/releases/download/21.3"
# )
#
# # Maps GitHub asset name → (destination subdirectory, final filename)
# # relative to the AppData/Local/CallofDuty4MW tree inside the prefix.
# _GITHUB_ASSETS = {
#     "cod4x_021.dll":    ("bin/cod4x_021", "cod4x_021.dll"),
#     "core":             ("bin",           "launcher.dll"),
#     "jcod4x_00.iwd":   ("main",          "jcod4x_00.iwd"),
#     "cod4x_ambfix.ff":  ("zone",          "cod4x_ambfix.ff"),
#     "cod4x_patch.ff":   ("zone",          "cod4x_patch.ff"),
#     "cod4x_patchv2.ff": ("zone",          "cod4x_patchv2.ff"),
# }
#
# # The chain-loader DLL that replaces the game's mss32.dll.
# _GITHUB_MSS_ASSET = "mss"

# AppData subfolder inside the Wine prefix. The CoD4x launcher looks here
# for its DLLs, zone files and iwd assets.
_APPDATA_FOLDER = "CallofDuty4MW"

# Registry keys that tell Steam the first-launch installers already ran.
# Without them, Steam runs PunkBuster setup, DirectX setup and PunkBuster
# Vista setup on first launch, then validates the game files, which puts
# the original mss32.dll back over the CoD4x chain-loader.
#
# Source: installscript.vdf in the CoD4 game directory.
# Key path: HKEY_CURRENT_USER\Software\Valve\Steam\Apps\7940
_REGISTRY_VALUES = {
    "dxsetup":    "dword:00000001",
    "Installed":  "dword:00000001",
    "PB Setup":   "dword:00000002",   # MinimumHasRunValue in installscript.vdf is 2
    "Running":    "dword:00000001",
}

# DeckOps log directory. Inno Setup logs are copied here for debugging.
_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs",
)


# --- helpers

# _download comes from net.py. The call sites pass timeout=60 (cod4x.ovh)
# and timeout=300 (archive.org).


def _get_appdata_dir(compatdata_path: str) -> str:
    """
    Return the AppData/Local/CallofDuty4MW path inside a Wine prefix.

    Works for Steam and own game prefixes. install_cod4x() resolves
    compatdata_path from the appid (the NVMe compatdata, also for SD card
    games and own installs with a DeckOps shortcut appid) before calling this.
    """
    return os.path.join(
        compatdata_path,
        "pfx", "drive_c", "users", "steamuser",
        "AppData", "Local", _APPDATA_FOLDER,
    )


def _write_registry_keys(compatdata_path: str, on_progress=None):
    """
    Write registry keys into the Wine prefix's user.reg so Steam thinks
    the first-launch installers (Punkbuster, DirectX) have already run.

    If the key block [Software\\\\Valve\\\\Steam\\\\Apps\\\\7940] already exists,
    its values are updated or added. Otherwise the whole block is appended.

    Wine registry format in user.reg:
      [Software\\\\Valve\\\\Steam\\\\Apps\\\\7940] <timestamp>
      "dxsetup"=dword:00000001
      "Installed"=dword:00000001
      "PB Setup"=dword:00000002
      "Running"=dword:00000001
    """
    prog = on_progress or (lambda *a: None)

    user_reg = os.path.join(compatdata_path, "pfx", "user.reg")

    if not os.path.exists(user_reg):
        # Prefix not initialized yet. The setup.exe Proton run creates it,
        # and step 4 writes the keys after that run. Proton usually creates
        # user.reg during prefix init.
        prog("  ⚠ user.reg not found — registry keys will be written after prefix init")
        return False

    with open(user_reg, "r", errors="replace") as f:
        content = f.read()

    key_path = r"[Software\\Valve\\Steam\\Apps\\7940]"

    # Build the value lines
    value_lines = []
    for name, val in _REGISTRY_VALUES.items():
        value_lines.append(f'"{name}"={val}')
    values_text = "\n".join(value_lines)

    if key_path in content:
        # Key block exists. Find it and make sure all values are present.
        # The block starts at the key_path line and ends at the next
        # empty line or the next key block ([...]).
        pattern = re.compile(
            r'(\[Software\\\\Valve\\\\Steam\\\\Apps\\\\7940\][^\n]*\n)((?:(?!\[)[^\n]*\n)*)',
            re.MULTILINE
        )
        match = pattern.search(content)
        if match:
            header = match.group(1)
            existing_body = match.group(2)

            # Parse existing values to keep any we don't manage
            existing_values = {}
            for line in existing_body.strip().split("\n"):
                line = line.strip()
                if line and "=" in line:
                    k = line.split("=")[0]
                    existing_values[k] = line

            # Merge our values (overwrite if already present)
            for name, val in _REGISTRY_VALUES.items():
                existing_values[f'"{name}"'] = f'"{name}"={val}'

            new_body = "\n".join(existing_values.values()) + "\n"
            content = content[:match.start()] + header + new_body + content[match.end():]
    else:
        # No key block yet. Append it at the end.
        block = (
            f"\n{key_path}\n"
            f"{values_text}\n"
        )
        content += block

    with open(user_reg, "w", errors="replace") as f:
        f.write(content)

    prog("  ✓ Registry keys written (skip Punkbuster/DirectX first-launch)")
    return True


def _write_install_path_registry(compatdata_path: str, install_dir: str,
                                  on_progress=None):
    """
    Write the CoD4 install path into the Wine prefix's system.reg (HKLM)
    so the CoD4x setup.exe can auto-detect the game directory.

    The CoD4x Inno Setup installer finds the game through the standard
    Activision registry key. On Windows the original game installer sets
    it. A Steam Deck Wine prefix doesn't have it, so setup.exe falls back
    to Program Files.

    Both the native path and the Wow6432Node path get the key. setup.exe
    is a 32-bit Inno Setup binary, and on a 64-bit Wine prefix it may look
    under either one, depending on Wine's registry redirection.

    Wine system.reg format:
      Keys are relative to HKEY_LOCAL_MACHINE (no HKLM prefix).
      Path separators are double-backslash (\\\\).
      String values use Wine's escaped format with double backslashes.
    """
    prog = on_progress or (lambda *a: None)

    system_reg = os.path.join(compatdata_path, "pfx", "system.reg")

    if not os.path.exists(system_reg):
        prog("  ⚠ system.reg not found — install path registry key skipped")
        return False

    with open(system_reg, "r", errors="replace") as f:
        content = f.read()

    # Convert the Linux path to a Wine Z: drive path, then double the
    # backslashes for the .reg format. Wine's system.reg uses \\\\ as separator.
    wine_path = _linux_to_wine_path(install_dir)
    # In .reg files, backslashes inside string values are doubled
    reg_value_path = wine_path.replace("\\", "\\\\")

    # The two key paths to write. No HKLM prefix, because Wine's system.reg
    # keys are relative to HKEY_LOCAL_MACHINE.
    key_paths = [
        r"[Software\\Activision\\Call of Duty 4]",
        r"[Software\\Wow6432Node\\Activision\\Call of Duty 4]",
    ]

    for key_path in key_paths:
        values_text = (
            f'"InstallPath"="{reg_value_path}"\n'
            f'"InstallDrive"="Z:"\n'
            f'"Language"="enu"\n'
        )

        if key_path in content:
            # Key block exists. Update its values.
            # Match the key header and its body (everything up to the next key or EOF).
            escaped_key = re.escape(key_path)
            pattern = re.compile(
                rf'({escaped_key}[^\n]*\n)((?:(?!\[)[^\n]*\n)*)',
                re.MULTILINE
            )
            match = pattern.search(content)
            if match:
                header = match.group(1)
                existing_body = match.group(2)

                # Parse existing values
                existing_values = {}
                for line in existing_body.strip().split("\n"):
                    line = line.strip()
                    if line and "=" in line:
                        k = line.split("=", 1)[0]
                        existing_values[k] = line

                # Merge our values
                existing_values['"InstallPath"'] = f'"InstallPath"="{reg_value_path}"'
                existing_values['"InstallDrive"'] = '"InstallDrive"="Z:"'
                existing_values['"Language"'] = '"Language"="enu"'

                new_body = "\n".join(existing_values.values()) + "\n"
                content = (
                    content[:match.start()] + header + new_body +
                    content[match.end():]
                )
        else:
            # No key block yet. Append it.
            block = f"\n{key_path}\n{values_text}"
            content += block

    with open(system_reg, "w", errors="replace") as f:
        f.write(content)

    prog(f"  ✓ Install path registry key written ({wine_path})")
    return True


# Default install path setup.exe uses inside the Wine prefix when it can't
# find the game through the registry or /DIR. setup.exe runs with
# cwd=install_dir on the Linux side, but Wine maps that to Z:\home\deck\...,
# which Inno Setup doesn't see as a CoD4 install, so it falls back here.
# With /DIR and the registry key in place, this is only a last resort.
_PREFIX_GAME_RELPATH = os.path.join(
    "pfx", "drive_c", "Program Files (x86)",
    "Activision", "Call of Duty 4 - Modern Warfare",
)


def _relocate_chainloader(compatdata_path: str, install_dir: str,
                          on_progress=None):
    """
    Copy the CoD4x chain-loader from the prefix to the real game directory.

    Fallback for when /DIR didn't work and setup.exe put the files in the
    prefix's Program Files instead of the game directory. If /DIR worked,
    the prefix fallback directory doesn't exist and this does nothing.

    In that case setup.exe writes mss32.dll (chain-loader) and miles32.dll
    (original backup) into the prefix's Program Files path, because it
    can't see the Linux game directory. This copies them to install_dir,
    where CoD4 loads them from, and deletes the prefix copy.

    Returns True if the chain-loader was placed successfully or was
    already in the right place.
    """
    def log(msg):
        if on_progress:
            on_progress(msg)

    # If setup.exe already put the files in install_dir, /DIR worked and
    # there is nothing to move.
    real_mss = os.path.join(install_dir, "mss32.dll")
    real_miles = os.path.join(install_dir, "miles32.dll")
    if os.path.exists(real_miles) and os.path.exists(real_mss):
        mss_size = os.path.getsize(real_mss)
        miles_size = os.path.getsize(real_miles)
        if mss_size != miles_size:
            log("  ✓ Chain-loader already in game directory (/DIR worked)")
            return True

    # Fall back to the prefix location
    prefix_game_dir = os.path.join(compatdata_path, _PREFIX_GAME_RELPATH)
    prefix_mss = os.path.join(prefix_game_dir, "mss32.dll")

    if not os.path.exists(prefix_mss):
        # Neither /DIR nor prefix fallback has the chain-loader
        if os.path.exists(real_miles):
            # miles32.dll is there but mss32.dll is missing or the same size. It may still work.
            return True
        log("  ⚠ Chain-loader not found in prefix or game directory — setup.exe may have failed")
        return False

    log("  ℹ Chain-loader found in prefix fallback — relocating to game directory")

    # Back up the original mss32.dll as miles32.dll, unless that was already done
    if os.path.exists(real_mss) and not os.path.exists(real_miles):
        shutil.copy2(real_mss, real_miles)
        log("  ✓ Backed up original mss32.dll → miles32.dll")

    # Copy the chain-loader into the game directory
    shutil.copy2(prefix_mss, real_mss)
    log("  ✓ CoD4x chain-loader mss32.dll copied to game directory")

    # Delete the prefix's fake game directory. Nothing uses it at runtime.
    if os.path.isdir(prefix_game_dir):
        shutil.rmtree(prefix_game_dir, ignore_errors=True)
        log("  ✓ Cleaned up prefix fallback directory")

    return True


def _collect_inno_log(compatdata_path: str, on_progress=None):
    """
    Find the Inno Setup log file from the prefix's temp directory and
    copy it to the DeckOps logs directory for debugging.

    Inno Setup /LOG writes to the current user's TEMP directory, with a
    file name like Setup Log YYYY-MM-DD #NNN.txt. Inside Wine that is the
    prefix's drive_c/users/steamuser/Temp/.

    Returns the path to the copied log file, or None if not found.
    """
    def log(msg):
        if on_progress:
            on_progress(msg)

    # Wine temp directories to check (Proton uses steamuser)
    temp_dirs = [
        os.path.join(compatdata_path, "pfx", "drive_c", "users", "steamuser", "Temp"),
        os.path.join(compatdata_path, "pfx", "drive_c", "users", "steamuser", "AppData", "Local", "Temp"),
        os.path.join(compatdata_path, "pfx", "drive_c", "windows", "temp"),
    ]

    for temp_dir in temp_dirs:
        if not os.path.isdir(temp_dir):
            continue
        # Inno Setup log filename pattern: "Setup Log YYYY-MM-DD #NNN.txt"
        pattern = os.path.join(temp_dir, "Setup Log *.txt")
        matches = glob.glob(pattern)
        if matches:
            # Take the newest one
            latest = max(matches, key=os.path.getmtime)
            try:
                os.makedirs(_LOG_DIR, exist_ok=True)
                dest = os.path.join(_LOG_DIR, "cod4x_inno_setup.log")
                shutil.copy2(latest, dest)
                log(f"  ✓ Inno Setup log saved to logs/cod4x_inno_setup.log")
                return dest
            except Exception as ex:
                log(f"  ⚠ Could not copy Inno Setup log: {ex}")
                return None

    log("  ℹ No Inno Setup log found in prefix temp directories")
    return None


# --- GitHub fallback: manual install (disabled)
# The archive.org setup.exe fallback replaced this. Function body kept below.

# def _manual_install(install_dir: str, compatdata_path: str, on_progress=None):
#     """
#     Fallback installer: download individual CoD4x 21.3 assets from the
#     official GitHub release and place them manually.
#
#     This replicates the file layout created by setup.exe +
#     install-cod4x-userfiles.bat:
#
#       Game directory:
#         mss32.dll           ← chain-loader (original backed up as miles32.dll)
#
#       Prefix  AppData/Local/CallofDuty4MW/:
#         bin/launcher.dll
#         bin/cod4x_021/cod4x_021.dll
#         main/jcod4x_00.iwd
#         zone/cod4x_ambfix.ff
#         zone/cod4x_patch.ff
#         zone/cod4x_patchv2.ff
#
#       Prefix  ProgramData/CallofDuty4MW/:
#         (same files staged flat — runtime fallback location)
#     """
#     def prog(pct, msg):
#         if on_progress:
#             on_progress(pct, msg)
#
#     def log(msg):
#         if on_progress:
#             on_progress(0, msg)
#
#     log("  ℹ Setup.exe unavailable — using GitHub release fallback")
#
#     # ── AppData tree inside the prefix ────────────────────────────────────
#     appdata_base = os.path.join(
#         compatdata_path, "pfx", "drive_c", "users", "steamuser",
#         "AppData", "Local", _APPDATA_FOLDER,
#     )
#     # ── ProgramData staging area (matches setup.exe behaviour) ────────────
#     progdata_base = os.path.join(
#         compatdata_path, "pfx", "drive_c", "ProgramData", _APPDATA_FOLDER,
#     )
#
#     # Create all target directories
#     for subdir in ("bin/cod4x_021", "main", "zone"):
#         os.makedirs(os.path.join(appdata_base, subdir), exist_ok=True)
#     os.makedirs(progdata_base, exist_ok=True)
#
#     # ── Download and place the chain-loader mss32.dll ─────────────────────
#     prog(15, "Downloading CoD4x chain-loader...")
#     mss_url = f"{_GITHUB_RELEASE_BASE}/{_GITHUB_MSS_ASSET}"
#     mss_dest = os.path.join(install_dir, "mss32.dll")
#     miles_dest = os.path.join(install_dir, "miles32.dll")
#
#     # Back up the original mss32.dll before overwriting
#     if os.path.exists(mss_dest) and not os.path.exists(miles_dest):
#         shutil.copy2(mss_dest, miles_dest)
#         log("  ✓ Backed up original mss32.dll → miles32.dll")
#
#     _download(
#         mss_url, mss_dest,
#         on_progress=lambda pct, lbl: prog(15 + int(pct * 0.10), lbl),
#         label="CoD4x chain-loader (mss)",
#         timeout=60,
#     )
#     log("  ✓ Chain-loader mss32.dll placed")
#
#     # ── Download remaining assets ─────────────────────────────────────────
#     asset_names = list(_GITHUB_ASSETS.keys())
#     total = len(asset_names)
#
#     for idx, asset_name in enumerate(asset_names):
#         subdir, final_name = _GITHUB_ASSETS[asset_name]
#         pct_base = 25 + int(idx / total * 55)
#         prog(pct_base, f"Downloading {final_name}...")
#
#         url = f"{_GITHUB_RELEASE_BASE}/{asset_name}"
#
#         # Place into AppData tree (proper runtime location)
#         appdata_dest = os.path.join(appdata_base, subdir, final_name)
#         _download(
#             url, appdata_dest,
#             on_progress=lambda pct, lbl, _b=pct_base: prog(
#                 _b + int(pct * (55 // total) / 100), lbl),
#             label=final_name,
#             timeout=60,
#         )
#
#         # Also stage into ProgramData (flat — matches setup.exe layout)
#         progdata_dest = os.path.join(progdata_base, final_name)
#         shutil.copy2(appdata_dest, progdata_dest)
#
#         log(f"  ✓ {final_name}")
#
#     prog(85, "GitHub fallback install complete.")
#     log("  ✓ All CoD4x files placed via GitHub fallback")


# --- public API

def install_cod4x(game: dict, steam_root: str, proton_path: str,
                  compatdata_path: str, on_progress=None, appid: int = 7940):
    """
    Install CoD4x 21.3 using the official setup.exe through Proton.

    ensure_all_prefix_deps sets up the prefix before this runs, so this
    only writes registry keys, runs the installer and moves the chain-loader.

    Parameters:
      game            : dict from detect_games with install_dir, exe_path, etc.
      steam_root      : path to the Steam root directory
      proton_path     : path to the Proton executable
      compatdata_path : path to the game's compatdata prefix (can be None/empty)
      on_progress     : optional callback(percent: int, status: str)
      appid           : Steam appid (default 7940)
    """
    install_dir = game["install_dir"]

    prog = on_progress or (lambda *a: None)

    def log(msg):
        if on_progress:
            on_progress(0, msg)

    # Use the NVMe path. ensure_all_prefix_deps already put the prefix there.
    compatdata_path = _nvme_compatdata(str(appid))
    log(f"  Prefix path: {compatdata_path}")

    # --- Step 1: write registry keys (before setup)
    # Written before the setup.exe run so Steam skips the first-launch installers.
    prog(5, "Writing registry keys...")
    pre_reg_ok = _write_registry_keys(compatdata_path, on_progress=log)

    # --- Step 1b: write the install path registry key
    # Write the CoD4 install directory into HKLM so setup.exe can find it.
    # This is the main fix for setup.exe not finding the game inside the
    # Wine prefix. Both the native and Wow6432Node paths get it, because
    # setup.exe is 32-bit and Wine may redirect either way.
    prog(8, "Writing install path registry...")
    _write_install_path_registry(compatdata_path, install_dir, on_progress=log)

    # --- Step 2: download CoD4x setup.exe
    prog(10, "Downloading CoD4x installer...")
    setup_dir = tempfile.mkdtemp(prefix="deckops_cod4x_")
    setup_exe = os.path.join(setup_dir, "CoD4x_Setup.exe")
    _dl_source = "cod4x.ovh"
    try:
        _download(
            _SETUP_EXE_URL, setup_exe,
            on_progress=lambda pct, lbl: prog(10 + int(pct * 0.40), lbl),
            label="CoD4x installer",
            timeout=60, digest=_SETUP_EXE_DIGEST,
        )
    except Exception as e:
        log(f"  ⚠ Setup.exe download failed: {e}")
        log("  ℹ Falling back to archive.org mirror...")
        _dl_source = "archive.org"
        try:
            _download(
                _ARCHIVE_FALLBACK_URL, setup_exe,
                on_progress=lambda pct, lbl: prog(10 + int(pct * 0.40), lbl),
                label="CoD4x installer (archive.org)",
                timeout=300, digest=_SETUP_EXE_DIGEST,
            )
            log("  ✓ Archive.org fallback download complete")
        except Exception as e2:
            shutil.rmtree(setup_dir, ignore_errors=True)
            raise DownloadError(
                url=_ARCHIVE_FALLBACK_URL,
                dest=setup_exe,
                label="CoD4x installer",
                cause=RuntimeError(
                    f"Primary (cod4x.ovh): {e} — Fallback (archive.org): {e2}"
                ),
            )

    # --- Step 3: run setup.exe through Proton
    # /DIR= tells Inno Setup where to install. The registry key (step 1b)
    # covers the case where /DIR is ignored. /LOG writes a debug log to the
    # prefix temp dir.
    prog(55, "Running CoD4x installer...")
    _compat_install = steam_root or os.path.dirname(os.path.dirname(proton_path))

    wine_install_dir = _linux_to_wine_path(install_dir)
    log(f"  Install dir (Wine): {wine_install_dir}")

    env = os.environ.copy()
    env["STEAM_COMPAT_DATA_PATH"] = compatdata_path
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = _compat_install

    try:
        result = subprocess.run(
            [
                proton_path, "run", setup_exe,
                "/VERYSILENT", "/SUPPRESSMSGBOXES",
                f"/DIR={wine_install_dir}",
                "/LOG",
            ],
            env=env,
            capture_output=True,
            timeout=600,
            cwd=install_dir,
        )
        log("  ✓ CoD4x installer completed")
        if result.returncode != 0:
            log(f"  ℹ setup.exe exit code: {result.returncode} (non-zero is normal for Inno Setup)")
    except subprocess.TimeoutExpired:
        shutil.rmtree(setup_dir, ignore_errors=True)
        raise RuntimeError("CoD4x installer timed out after 10 minutes")
    except Exception as e:
        shutil.rmtree(setup_dir, ignore_errors=True)
        raise RuntimeError(f"CoD4x installer failed: {e}")
    finally:
        shutil.rmtree(setup_dir, ignore_errors=True)

    # --- Step 3b: collect the Inno Setup log
    _collect_inno_log(compatdata_path, on_progress=log)

    # --- Step 3c: move the chain-loader to the real game directory
    # Does nothing if /DIR worked. If /DIR was ignored, the files are in
    # the prefix's Program Files fallback path.
    prog(65, "Placing chain-loader...")
    relocated = _relocate_chainloader(compatdata_path, install_dir, on_progress=log)
    if not relocated:
        log("  ⚠ Chain-loader relocation failed — CoD4x may not work")
        log("  ℹ Check logs/cod4x_inno_setup.log for details")

    # --- Step 4: write registry keys (after setup)
    # The Proton run may have created a new user.reg, so write the keys
    # again for the next Steam launch.
    prog(80, "Finalizing registry...")
    _write_registry_keys(compatdata_path, on_progress=log)

    # --- Step 5: check the chain-loader is in place
    mss_path = os.path.join(install_dir, "mss32.dll")
    miles_path = os.path.join(install_dir, "miles32.dll")

    if os.path.exists(miles_path) and os.path.exists(mss_path):
        # mss32.dll should be the chain-loader and miles32.dll the original,
        # so their sizes should differ.
        mss_size = os.path.getsize(mss_path)
        miles_size = os.path.getsize(miles_path)
        if mss_size != miles_size:
            log("  ✓ Chain-loader mss32.dll in place (different size from original)")
        else:
            log("  ⚠ mss32.dll and miles32.dll are the same size — verifying...")
    elif not os.path.exists(miles_path):
        log("  ⚠ miles32.dll backup not found — setup.exe may not have run correctly")

    # --- Step 6: delete servercache.dat
    # Makes CoD4x download a fresh server list on first launch.
    appdata_dir = _get_appdata_dir(compatdata_path)
    for cache_path in [
        os.path.join(install_dir, "servercache.dat"),
        os.path.join(appdata_dir, "servercache.dat"),
    ]:
        if os.path.exists(cache_path):
            os.remove(cache_path)

    prog(90, "Cleared server cache.")

    # --- Step 7: write metadata
    prog(95, "Saving metadata...")
    write_json(os.path.join(install_dir, METADATA_FILE), {
        "version": "21.3",
        "method": "setup_exe",
        "download_source": _dl_source,
        "appdata_dir": appdata_dir,
        "compatdata_path": compatdata_path,
    })

    prog(100, "CoD4x installation complete!")
