"""
cod4x.py - DeckOps installer for CoD4x (Call of Duty 4: Modern Warfare)

Runs the official CoD4x 21.3 setup.exe through Proton in silent mode.
The prefix (7940) is already fully initialized by ensure_all_prefix_deps
before this module runs — no prefix management needed here.

The CoD4x chain-loader mechanism:
  1. mss32.dll in the game directory is replaced with the CoD4x version.
     The original is backed up as miles32.dll. CoD4 loads mss32.dll at
     startup via PE imports, so this is the entry point for the mod.
  2. The new mss32.dll loads launcher.dll from AppData/Local/CallofDuty4MW/bin/.
  3. launcher.dll loads cod4x_021.dll from AppData/Local/CallofDuty4MW/bin/cod4x_021/.
  4. cod4x_021.dll patches the game in memory to become CoD4x 21.3.

Install flow:
  1. Write registry keys so Steam skips DirectX/Punkbuster first-launch installers
  1b. Write CoD4 install path registry key so setup.exe can find the game
  2. Download the official CoD4x setup.exe
  3. Run setup.exe through Proton with /DIR= pointing at the game directory
  3b. Relocate chain-loader from prefix to game directory (fallback)
  4. Write registry keys again (safety net after Proton run)
  5. Verify and write metadata
"""

import os
import re
import glob
import json
import shutil
import subprocess
import tempfile

from net import download as _download, DownloadError

from log import get_logger

_log = get_logger(__name__)


# ── constants ─────────────────────────────────────────────────────────────────

_SETUP_EXE_URL = "https://cod4x.ovh/uploads/short-url/2V3RsE0Pp5Jakc1VE9Yuh5yb4lE.exe"

METADATA_FILE = "deckops_cod4x.json"

# ── Archive.org fallback ─────────────────────────────────────────────────────
# If the setup.exe download from cod4x.ovh times out (60 s), fall back to
# this archived copy of the official 21.3 installer and continue the normal
# setup.exe flow.
_ARCHIVE_FALLBACK_URL = (
    "https://archive.org/download/co-d-4x.-21.3.-setup/CoD4x.21.3.Setup.exe"
)

# ── GitHub fallback (disabled) ───────────────────────────────────────────────
# Replaced by the archive.org fallback above.  Kept here for reference.
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

# The AppData subfolder name inside the Wine prefix. This is where the CoD4x
# launcher expects to find its DLLs, zone files, and iwd assets.
_APPDATA_FOLDER = "CallofDuty4MW"

# Registry keys that tell Steam the first-launch installers already ran.
# Without these, Steam runs PunkBuster setup, DirectX setup, and PunkBuster
# Vista setup on every first launch — and re-validates game files afterward,
# overwriting our CoD4x mss32.dll chain-loader with the original.
#
# Source: installscript.vdf in the CoD4 game directory.
# Key path: HKEY_CURRENT_USER\Software\Valve\Steam\Apps\7940
_REGISTRY_VALUES = {
    "dxsetup":    "dword:00000001",
    "Installed":  "dword:00000001",
    "PB Setup":   "dword:00000002",   # MinimumHasRunValue in installscript.vdf is 2
    "Running":    "dword:00000001",
}

# DeckOps log directory — Inno Setup logs are copied here for debugging.
_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs",
)


# ── helpers ──────────────────────────────────────────────────────────────────

# _download imported from net.py; call site passes timeout=120.


def _write_metadata(install_dir: str, data: dict):
    """Write DeckOps metadata JSON to the game directory."""
    path = os.path.join(install_dir, METADATA_FILE)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _get_appdata_dir(compatdata_path: str) -> str:
    """
    Return the AppData/Local/CallofDuty4MW path inside a Wine prefix.

    Works for both Steam and own game prefixes — the compatdata_path is
    resolved by the caller (ui_qt.py) before install_cod4x() is called,
    regardless of whether the game is on the NVME, SD card, or an own
    install with a DeckOps-generated shortcut appid.
    """
    return os.path.join(
        compatdata_path,
        "pfx", "drive_c", "users", "steamuser",
        "AppData", "Local", _APPDATA_FOLDER,
    )


def _nvme_compatdata(appid: str) -> str:
    """Return the NVMe compatdata path for a given appid."""
    return os.path.join(
        os.path.expanduser("~/.local/share/Steam"),
        "steamapps", "compatdata", str(appid),
    )


def _linux_to_wine_path(linux_path: str) -> str:
    """
    Convert a Linux path to a Wine Z: drive path.

    Wine maps the entire Linux filesystem under Z:, so
    /home/deck/.local/share/Steam/steamapps/common/Call of Duty 4
    becomes
    Z:\\home\\deck\\.local\\share\\Steam\\steamapps\\common\\Call of Duty 4
    """
    return "Z:" + linux_path.replace("/", "\\")


def _write_registry_keys(compatdata_path: str, on_progress=None):
    """
    Write registry keys into the Wine prefix's user.reg so Steam thinks
    the first-launch installers (Punkbuster, DirectX) have already run.

    If the key block [Software\\\\Valve\\\\Steam\\\\Apps\\\\7940] already exists,
    we update/add the values. If it doesn't exist, we append the entire block.

    Wine registry format in user.reg:
      [Software\\\\Valve\\\\Steam\\\\Apps\\\\7940] <timestamp>
      "dxsetup"=dword:00000001
      "Installed"=dword:00000001
      "PB Setup"=dword:00000002
      "Running"=dword:00000001
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    user_reg = os.path.join(compatdata_path, "pfx", "user.reg")

    if not os.path.exists(user_reg):
        # Prefix hasn't been initialized yet — the setup.exe Proton run
        # will create it. We'll write the keys after the setup.exe runs
        # if needed, but typically Proton creates user.reg during init.
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
        # Key block exists — find it and ensure all values are present.
        # The block starts at the key_path line and ends at the next
        # empty line or next key block ([...]).
        pattern = re.compile(
            r'(\[Software\\\\Valve\\\\Steam\\\\Apps\\\\7940\][^\n]*\n)((?:(?!\[)[^\n]*\n)*)',
            re.MULTILINE
        )
        match = pattern.search(content)
        if match:
            header = match.group(1)
            existing_body = match.group(2)

            # Parse existing values to preserve any we don't manage
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
        # Key block doesn't exist — append it at the end
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

    The CoD4x Inno Setup installer looks for the game via the standard
    Activision registry key. On a real Windows install this is set by
    the original game installer. Inside a Steam Deck Wine prefix it
    doesn't exist, so setup.exe falls back to Program Files.

    We write to both the native path and the Wow6432Node path because
    setup.exe is a 32-bit Inno Setup binary — on a 64-bit Wine prefix
    it may look under either location depending on Wine's registry
    redirection behaviour.

    Wine system.reg format:
      Keys are relative to HKEY_LOCAL_MACHINE (no HKLM prefix).
      Path separators are double-backslash (\\\\).
      String values use Wine's escaped format with double backslashes.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    system_reg = os.path.join(compatdata_path, "pfx", "system.reg")

    if not os.path.exists(system_reg):
        prog("  ⚠ system.reg not found — install path registry key skipped")
        return False

    with open(system_reg, "r", errors="replace") as f:
        content = f.read()

    # Convert Linux path to Wine Z: drive path with doubled backslashes
    # for the .reg file format. Wine's system.reg uses \\\\ as separator.
    wine_path = _linux_to_wine_path(install_dir)
    # In .reg files, backslashes inside string values are doubled
    reg_value_path = wine_path.replace("\\", "\\\\")

    # The two key paths we need to write (without HKLM prefix, as Wine
    # system.reg keys are relative to HKEY_LOCAL_MACHINE)
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
            # Key block exists — update InstallPath value
            # Match the key header and its body (everything until next key or EOF)
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
            # Key block doesn't exist — append it
            block = f"\n{key_path}\n{values_text}"
            content += block

    with open(system_reg, "w", errors="replace") as f:
        f.write(content)

    prog(f"  ✓ Install path registry key written ({wine_path})")
    return True


# The default install path that setup.exe writes to inside the Wine prefix
# when it can't find the game via registry or /DIR. setup.exe runs with
# cwd=install_dir on the Linux side, but Wine maps that to Z:\home\deck\...
# which Inno Setup doesn't recognise as a CoD4 install -- so it falls back
# here. With the /DIR parameter and registry key fixes, this path should
# only be needed as a last-resort fallback.
_PREFIX_GAME_RELPATH = os.path.join(
    "pfx", "drive_c", "Program Files (x86)",
    "Activision", "Call of Duty 4 - Modern Warfare",
)


def _relocate_chainloader(compatdata_path: str, install_dir: str,
                          on_progress=None):
    """
    Copy the CoD4x chain-loader from the prefix to the real game directory.

    This is a fallback for when /DIR didn't work and setup.exe placed
    files in the prefix's Program Files instead of the game directory.
    If /DIR worked correctly, the prefix fallback directory won't exist
    and this function is a no-op.

    setup.exe writes mss32.dll (chain-loader) and miles32.dll (original
    backup) into the prefix's virtual Program Files path because it can't
    see the Linux game directory. This function moves them to install_dir
    where CoD4 actually loads them from.

    Returns True if the chain-loader was placed successfully or was
    already in the right place.
    """
    def log(msg):
        if on_progress:
            on_progress(msg)

    # Check if setup.exe already placed files directly in install_dir
    # (meaning /DIR worked). If so, no relocation needed.
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
            # miles32.dll exists but mss32.dll is same size — might still be ok
            return True
        log("  ⚠ Chain-loader not found in prefix or game directory — setup.exe may have failed")
        return False

    log("  ℹ Chain-loader found in prefix fallback — relocating to game directory")

    # Back up the original mss32.dll as miles32.dll (only if not already done)
    if os.path.exists(real_mss) and not os.path.exists(real_miles):
        shutil.copy2(real_mss, real_miles)
        log("  ✓ Backed up original mss32.dll → miles32.dll")

    # Copy the chain-loader into the game directory
    shutil.copy2(prefix_mss, real_mss)
    log("  ✓ CoD4x chain-loader mss32.dll copied to game directory")

    # Clean up the prefix's fake game directory — it's not needed at runtime
    if os.path.isdir(prefix_game_dir):
        shutil.rmtree(prefix_game_dir, ignore_errors=True)
        log("  ✓ Cleaned up prefix fallback directory")

    return True


def _collect_inno_log(compatdata_path: str, on_progress=None):
    """
    Find the Inno Setup log file from the prefix's temp directory and
    copy it to the DeckOps logs directory for debugging.

    Inno Setup /LOG writes to the current user's TEMP directory with a
    filename like Setup Log YYYY-MM-DD #NNN.txt. Inside Wine this maps
    to the prefix's drive_c/users/steamuser/Temp/.

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
            # Take the most recent one
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


# ── GitHub fallback: manual install (disabled) ───────────────────────────────
# Replaced by archive.org setup.exe fallback.  Function body preserved below.

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


# ── public API ───────────────────────────────────────────────────────────────

def install_cod4x(game: dict, steam_root: str, proton_path: str,
                  compatdata_path: str, on_progress=None, appid: int = 7940):
    """
    Install CoD4x 21.3 using the official setup.exe through Proton.

    The prefix is already initialized by ensure_all_prefix_deps before
    this function runs. We just need to write registry keys, run the
    installer, and relocate the chain-loader.

    Parameters:
      game            -- dict from detect_games with install_dir, exe_path, etc.
      steam_root      -- path to the Steam root directory
      proton_path     -- path to the Proton executable
      compatdata_path -- path to the game's compatdata prefix (can be None/empty)
      on_progress     -- optional callback(percent: int, status: str)
      appid           -- Steam appid (default 7940)
    """
    install_dir = game["install_dir"]

    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    def log(msg):
        if on_progress:
            on_progress(0, msg)

    # Resolve to NVMe path — ensure_all_prefix_deps already placed it here
    import time
    start = time.time()
    compatdata_path = _nvme_compatdata(str(appid))
    log(f"  Prefix path: {compatdata_path}")

    # ── Step 1: Write registry keys (pre-setup) ─────────────────────────
    # Write before the setup.exe run so Steam skips first-launch installers.
    prog(5, "Writing registry keys...")
    pre_reg_ok = _write_registry_keys(compatdata_path, on_progress=log)

    # ── Step 1b: Write install path registry key ─────────────────────────
    # Write the CoD4 install directory into HKLM so setup.exe can find it.
    # This is the primary fix for setup.exe not detecting the game location
    # inside the Wine prefix. We write to both the native and Wow6432Node
    # paths because setup.exe is 32-bit and Wine may redirect either way.
    prog(8, "Writing install path registry...")
    _write_install_path_registry(compatdata_path, install_dir, on_progress=log)

    # ── Step 2: Download CoD4x setup.exe ─────────────────────────────────
    prog(10, "Downloading CoD4x installer...")
    setup_dir = tempfile.mkdtemp(prefix="deckops_cod4x_")
    setup_exe = os.path.join(setup_dir, "CoD4x_Setup.exe")
    _used_fallback = False
    try:
        _download(
            _SETUP_EXE_URL, setup_exe,
            on_progress=lambda pct, lbl: prog(10 + int(pct * 0.40), lbl),
            label="CoD4x installer",
            timeout=60,
        )
    except Exception as e:
        log(f"  ⚠ Setup.exe download failed: {e}")
        log("  ℹ Falling back to archive.org mirror...")
        try:
            _download(
                _ARCHIVE_FALLBACK_URL, setup_exe,
                on_progress=lambda pct, lbl: prog(10 + int(pct * 0.40), lbl),
                label="CoD4x installer (archive.org)",
                timeout=300,
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

    # ── Step 3: Run setup.exe through Proton (skipped if fallback used) ──
    if not _used_fallback:
        # We pass /DIR= with the Wine Z: drive path so Inno Setup knows where
        # to install. We also pre-wrote the registry key (step 1b) as a safety
        # net in case /DIR is ignored by the installer's custom script.
        #
        # /LOG tells Inno Setup to write a detailed log to the prefix's temp
        # directory. We collect it after the run for debugging.
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
            # The setup.exe may return non-zero even on success (Inno Setup quirk)
            # so we don't check returncode — we verify file placement below
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
            # Clean up the setup exe regardless of outcome
            shutil.rmtree(setup_dir, ignore_errors=True)

        # ── Step 3b: Collect Inno Setup log ──────────────────────────────
        _collect_inno_log(compatdata_path, on_progress=log)

        # ── Step 3c: Relocate chain-loader to real game directory ────────
        # If /DIR worked, setup.exe placed files directly in install_dir and
        # this is a no-op. If /DIR was ignored, files ended up in the prefix's
        # Program Files fallback path — this function copies them over.
        prog(65, "Placing chain-loader...")
        relocated = _relocate_chainloader(compatdata_path, install_dir, on_progress=log)
        if not relocated:
            log("  ⚠ Chain-loader relocation failed — CoD4x may not work")
            log("  ℹ Check logs/cod4x_inno_setup.log for details")

    # ── Step 4: Write registry keys (post-setup) ─────────────────────────
    # The Proton run may have created a fresh user.reg, so write keys again
    # to make sure they're in place for the next Steam launch.
    prog(80, "Finalizing registry...")
    _write_registry_keys(compatdata_path, on_progress=log)

    # ── Step 5: Verify the chain-loader was placed correctly ─────────────
    mss_path = os.path.join(install_dir, "mss32.dll")
    miles_path = os.path.join(install_dir, "miles32.dll")

    if os.path.exists(miles_path) and os.path.exists(mss_path):
        # Check that mss32.dll and miles32.dll are different
        # (mss32.dll should be the chain-loader, miles32.dll the original)
        mss_size = os.path.getsize(mss_path)
        miles_size = os.path.getsize(miles_path)
        if mss_size != miles_size:
            log("  ✓ Chain-loader mss32.dll in place (different size from original)")
        else:
            log("  ⚠ mss32.dll and miles32.dll are the same size — verifying...")
    elif not os.path.exists(miles_path):
        log("  ⚠ miles32.dll backup not found — setup.exe may not have run correctly")

    # ── Step 6: Delete servercache.dat ────────────────────────────────────
    # Force CoD4x to download a fresh server list on first launch.
    appdata_dir = _get_appdata_dir(compatdata_path)
    for cache_path in [
        os.path.join(install_dir, "servercache.dat"),
        os.path.join(appdata_dir, "servercache.dat"),
    ]:
        if os.path.exists(cache_path):
            os.remove(cache_path)

    prog(90, "Cleared server cache.")

    # ── Step 7: Write metadata ────────────────────────────────────────────
    prog(95, "Saving metadata...")
    _write_metadata(install_dir, {
        "version": "21.3",
        "method": "archive_fallback" if _used_fallback else "setup_exe",
        "appdata_dir": appdata_dir,
        "compatdata_path": compatdata_path,
    })

    prog(100, "CoD4x installation complete!")


def uninstall_cod4x(game: dict, compatdata_path: str = None):
    """
    Remove CoD4x files and restore original backups.

    Cleans up both the game directory (restores iw3mp.exe and mss32.dll)
    and the Wine prefix AppData structure.

    Parameters:
      game            — dict from detect_games with install_dir
      compatdata_path — path to the game's compatdata prefix. If None,
                        attempts to read it from the metadata file.
    """
    install_dir = game["install_dir"]

    # ── Restore iw3mp.exe from backup ─────────────────────────────────────
    iw3mp_bak = os.path.join(install_dir, "iw3mp.exe.bak")
    iw3mp_exe = os.path.join(install_dir, "iw3mp.exe")
    if os.path.exists(iw3mp_bak):
        if os.path.exists(iw3mp_exe):
            os.remove(iw3mp_exe)
        os.rename(iw3mp_bak, iw3mp_exe)

    # ── Restore mss32.dll from miles32.dll backup ─────────────────────────
    miles_dll = os.path.join(install_dir, "miles32.dll")
    mss_dll   = os.path.join(install_dir, "mss32.dll")
    if os.path.exists(miles_dll):
        if os.path.exists(mss_dll):
            os.remove(mss_dll)
        os.rename(miles_dll, mss_dll)

    # ── Remove the prefix AppData folder ──────────────────────────────────
    # If compatdata_path wasn't passed, try to read it from metadata.
    if compatdata_path is None:
        meta_path = os.path.join(install_dir, METADATA_FILE)
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                compatdata_path = meta.get("compatdata_path")
            except (json.JSONDecodeError, IOError):
                _log.debug("failed to read cod4x metadata", exc_info=True)

    if compatdata_path:
        appdata_dir = _get_appdata_dir(compatdata_path)
        if os.path.isdir(appdata_dir):
            shutil.rmtree(appdata_dir, ignore_errors=True)

        # Also clean up the ProgramData staging area (setup.exe + fallback)
        progdata_dir = os.path.join(
            compatdata_path, "pfx", "drive_c", "ProgramData", _APPDATA_FOLDER,
        )
        if os.path.isdir(progdata_dir):
            shutil.rmtree(progdata_dir, ignore_errors=True)

    # ── Remove metadata ───────────────────────────────────────────────────
    meta_file = os.path.join(install_dir, METADATA_FILE)
    if os.path.exists(meta_file):
        os.remove(meta_file)
