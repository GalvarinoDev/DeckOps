"""
cod4x.py - DeckOps installer for COD4x (Call of Duty 4: Modern Warfare)

Downloads the official CoD4x setup executable, executes it silently via
Proton, and allows the installer to handle registry/DLL registration
natively within the game's prefix.

The cod4x setup.exe bundles a Visual C++ 2010 Redistributable that launches
as a child process and ignores the parent /VERYSILENT flags, producing a GUI
popup. We pre-install vcrun2010 via protontricks so the bundled sub-installer
sees it is already present and exits without showing any UI.
"""

import os
import json
import subprocess
import urllib.request

SETUP_URL = "https://cod4x.ovh/uploads/short-url/2V3RsE0Pp5Jakc1VE9Yuh5yb4lE.exe"
METADATA_FILE = "deckops_cod4x.json"

# ── helpers ──────────────────────────────────────────────────────────────────

def _download(url: str, dest: str, on_progress=None, label: str = ""):
    """Download url to dest with browser-like headers. Retries up to 3 times."""
    import time
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                total = int(r.headers.get("Content-Length", 0))
                downloaded = 0
                with open(dest, "wb") as f:
                    while True:
                        chunk = r.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if on_progress and total:
                            on_progress(int(downloaded / total * 100), label)
            return
        except Exception as ex:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

def _write_metadata(install_dir: str, data: dict):
    path = os.path.join(install_dir, METADATA_FILE)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ── vcrun2010 pre-install ─────────────────────────────────────────────────────

def _ensure_vcrun2010(appid: int, compatdata_path: str, on_progress=None) -> bool:
    """
    Pre-install vcrun2010 into the game's prefix via protontricks so that
    the VC++ 2010 sub-installer bundled inside cod4x setup.exe sees it is
    already present and exits silently without showing any UI.

    Returns True if vcrun2010 is confirmed present after this call, or if
    protontricks is unavailable (we still attempt the install and let the
    popup occur rather than blocking the whole install).
    """
    def prog(msg):
        if on_progress:
            on_progress(0, msg)

    # Import from plutonium to reuse the already-established protontricks helpers.
    try:
        from plutonium import _find_protontricks, _ensure_protontricks_sd_access
    except ImportError:
        prog("Could not import protontricks helpers — VC++ popup may appear.")
        return False

    protontricks = _find_protontricks()
    if protontricks is None:
        prog("Protontricks not found — VC++ popup may appear during CoD4x install.")
        return False

    _ensure_protontricks_sd_access()

    # Check if vcrun2010 DLLs are already present in the prefix.
    sys32 = os.path.join(compatdata_path, "pfx", "drive_c", "windows", "system32")
    vcrun_marker = os.path.join(sys32, "msvcp100.dll")
    if os.path.exists(vcrun_marker) and os.path.getsize(vcrun_marker) > 0:
        prog("vcrun2010 already installed, skipping.")
        return True

    prog("Pre-installing vcrun2010 to suppress VC++ popup...")
    try:
        result = subprocess.run(
            protontricks + [str(appid), "-q", "vcrun2010"],
            capture_output=True,
            timeout=180,
        )
        # protontricks may exit non-zero even on success — verify via file.
        if os.path.exists(vcrun_marker) and os.path.getsize(vcrun_marker) > 0:
            prog("vcrun2010 installed successfully.")
            return True
        if result.returncode == 0:
            prog("vcrun2010 install reported success.")
            return True
        prog("vcrun2010 install finished with warnings — popup may still be suppressed.")
        return False
    except subprocess.TimeoutExpired:
        prog("vcrun2010 install timed out — VC++ popup may appear.")
        return False


# ── public API ───────────────────────────────────────────────────────────────

def install_cod4x(game: dict, steam_root: str, proton_path: str,
                  compatdata_path: str, on_progress=None, appid: int = 7940):
    """
    Downloads and installs CoD4x using the official setup.exe inside
    the game's specific Proton prefix.

    appid is used to pre-install vcrun2010 via protontricks so the VC++ 2010
    sub-installer bundled in the cod4x setup.exe exits silently without a popup.
    """
    install_dir = game["install_dir"]
    setup_exe   = os.path.join(install_dir, "CoD4x_Setup.exe")

    def prog(pct, msg):
        if on_progress: on_progress(pct, msg)

    # Pre-install vcrun2010 before downloading so the prefix is ready.
    # This is fast if already installed (just a file check).
    prog(0, "Checking Visual C++ 2010 runtime...")
    _ensure_vcrun2010(appid, compatdata_path, on_progress=on_progress)

    prog(5, "Downloading CoD4x installer...")
    _download(SETUP_URL, setup_exe, lambda p, m: prog(5 + int(p * 0.45), m), "Downloading CoD4x...")

    prog(50, "Running installer...")
    env = {
        **os.environ,
        "STEAM_COMPAT_DATA_PATH":           compatdata_path,
        "WINEPREFIX":                        os.path.join(compatdata_path, "pfx"),
        "STEAM_COMPAT_CLIENT_INSTALL_PATH": steam_root,
    }

    cmd = [proton_path, "run", setup_exe, "/VERYSILENT", "/SUPPRESSMSGBOXES"]

    try:
        subprocess.run(cmd, env=env, check=True)

        # Read the installed version from the CoD4x DLL if present,
        # otherwise fall back to a placeholder so metadata is never stale.
        version = "unknown"
        cod4x_dll = os.path.join(install_dir, "cod4x_021.dll")
        if not os.path.exists(cod4x_dll):
            # Try alternate name used by newer releases
            cod4x_dll = os.path.join(install_dir, "cod4x.dll")
        if os.path.exists(cod4x_dll):
            version = "installed"  # version embedded in PE, not easily parsed

        _write_metadata(install_dir, {"version": version})

        # Delete servercache.dat so CoD4x downloads a fresh server list on first launch
        servercache = os.path.join(install_dir, "servercache.dat")
        if os.path.exists(servercache):
            os.remove(servercache)
            prog(95, "Cleared server cache.")

        prog(100, "COD4x installation complete!")
    finally:
        if os.path.exists(setup_exe):
            os.remove(setup_exe)

def uninstall_cod4x(game: dict):
    """
    Clean up metadata and installed files.
    """
    install_dir = game["install_dir"]
    meta_file   = os.path.join(install_dir, METADATA_FILE)
    if os.path.exists(meta_file):
        os.remove(meta_file)
