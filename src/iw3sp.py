"""
iw3sp.py - DeckOps installer for IW3SP-MOD (Call of Duty 4: Modern Warfare Singleplayer)

Downloads the latest iw3sp_mod release zip from Gitea, extracts it into
the CoD4 install directory, then:
  - Renames iw3sp.exe -> iw3sp.exe.bak
  - Renames iw3sp_mod.exe -> iw3sp.exe

This lets Steam launch IW3SP-MOD transparently via the existing SP shortcut
with no launch options or localconfig.vdf writes required.

Progress is reported via a callback:
    on_progress(percent: int, status: str)
"""

import os
import json
import shutil
import zipfile
import urllib.request

BASE_URL      = "https://gitea.com/JerryALT/iw3sp_mod/releases/download/v4.1.5/iw3sp_mod_v4.1.5.zip"
METADATA_FILE = "deckops_iw3sp.json"

_BROWSER_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _download(url: str, dest: str, on_progress=None, label: str = ""):
    """Download url to dest with progress callback. Retries up to 3 times."""
    import time
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=_BROWSER_UA)
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


def is_iw3sp_installed(install_dir: str) -> bool:
    """Returns True if iw3sp.exe.bak exists (meaning the mod rename is active)."""
    return os.path.exists(os.path.join(install_dir, "iw3sp.exe.bak"))


# ── public API ────────────────────────────────────────────────────────────────

def install_iw3sp(game: dict, steam_root: str,
                  proton_path: str, compatdata_path: str,
                  on_progress=None):
    """
    Install IW3SP-MOD for Call of Duty 4 singleplayer.

    Downloads and extracts the mod zip into the CoD4 install directory, then
    renames iw3sp.exe -> iw3sp.exe.bak and iw3sp_mod.exe -> iw3sp.exe so
    Steam launches the mod transparently. No launch options are written.

    game            — entry from detect_games.find_installed_games()
    steam_root      — path to Steam root (kept for API consistency)
    proton_path     — path to the proton executable (kept for API consistency)
    compatdata_path — path to the CoD4 compatdata prefix (kept for API consistency)
    on_progress     — optional callback(percent: int, status: str)
    """
    install_dir = game["install_dir"]
    zip_dest    = os.path.join(install_dir, "iw3sp_mod.zip")

    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    # Download zip
    prog(5, "Downloading IW3SP-MOD...")
    _download(
        BASE_URL,
        zip_dest,
        lambda p, m: prog(5 + int(p * 0.55), m),
        "Downloading IW3SP-MOD...",
    )

    # Extract into CoD4 root
    prog(60, "Extracting IW3SP-MOD...")
    with zipfile.ZipFile(zip_dest) as zf:
        zf.extractall(install_dir)
    os.remove(zip_dest)

    iw3sp     = os.path.join(install_dir, "iw3sp.exe")
    iw3sp_bak = os.path.join(install_dir, "iw3sp.exe.bak")
    iw3sp_mod = os.path.join(install_dir, "iw3sp_mod.exe")

    # Rename iw3sp.exe -> iw3sp.exe.bak (only if not already done)
    prog(80, "Replacing iw3sp.exe...")
    if os.path.exists(iw3sp) and not os.path.exists(iw3sp_bak):
        os.rename(iw3sp, iw3sp_bak)

    # Rename iw3sp_mod.exe -> iw3sp.exe
    if os.path.exists(iw3sp_mod):
        os.rename(iw3sp_mod, iw3sp)

    # Write metadata
    prog(95, "Saving metadata...")
    meta_path = os.path.join(install_dir, METADATA_FILE)
    with open(meta_path, "w") as f:
        json.dump({"version": "4.1.5"}, f, indent=2)

    prog(100, "IW3SP-MOD installation complete!")


def uninstall_iw3sp(game: dict):
    """
    Restore iw3sp.exe from iw3sp.exe.bak and remove IW3SP-MOD files.
    """
    install_dir = game["install_dir"]

    iw3sp     = os.path.join(install_dir, "iw3sp.exe")
    iw3sp_bak = os.path.join(install_dir, "iw3sp.exe.bak")

    # Restore original exe from backup
    if os.path.exists(iw3sp_bak):
        if os.path.exists(iw3sp):
            os.remove(iw3sp)
        os.rename(iw3sp_bak, iw3sp)

    # Remove metadata
    meta = os.path.join(install_dir, METADATA_FILE)
    if os.path.exists(meta):
        os.remove(meta)

    # Remove known IW3SP-MOD files dropped into the CoD4 root
    for fname in ["iw3sp_mod.exe", "iw3sp_mod.dll"]:
        p = os.path.join(install_dir, fname)
        if os.path.exists(p):
            os.remove(p)

    # Remove iw3sp_mod folder if present
    iw3sp_dir = os.path.join(install_dir, "iw3sp_mod")
    if os.path.exists(iw3sp_dir):
        shutil.rmtree(iw3sp_dir)
