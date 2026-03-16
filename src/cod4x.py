"""
cod4x.py - DeckOps installer for COD4x (Call of Duty 4: Modern Warfare)

Downloads the official CoD4x setup executable, executes it silently via
Proton, and allows the installer to handle registry/DLL registration
natively within the game's prefix.
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

# ── public API ───────────────────────────────────────────────────────────────

def install_cod4x(game: dict, steam_root: str, proton_path: str,
                  compatdata_path: str, on_progress=None):
    """
    Downloads and installs CoD4x using the official setup.exe inside
    the game's specific Proton prefix.
    """
    install_dir = game["install_dir"]
    setup_exe   = os.path.join(install_dir, "CoD4x_Setup.exe")

    def prog(pct, msg):
        if on_progress: on_progress(pct, msg)

    prog(0, "Downloading CoD4x installer...")
    _download(SETUP_URL, setup_exe, lambda p, m: prog(p, m), "Downloading CoD4x...")

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
