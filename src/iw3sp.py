"""
iw3sp.py - DeckOps installer for IW3SP-MOD (Call of Duty 4: Modern Warfare Singleplayer)

Downloads the latest iw3sp_mod release zip from Gitea, extracts it into
the CoD4 install directory.

For Steam games:
  - Renames iw3sp.exe -> iw3sp.exe.bak
  - Renames iw3sp_mod.exe -> iw3sp.exe
  This lets Steam launch IW3SP-MOD transparently via the existing SP shortcut.

For own games:
  - Extracts the zip but skips the exe rename
  - The non-Steam shortcut already points at iw3sp_mod.exe directly

Progress is reported via a callback:
    on_progress(percent: int, status: str)
"""

import os
import json
import shutil
import urllib.request
import zipfile

from net import download as _download, BROWSER_UA as _BROWSER_UA

GITEA_API     = "https://gitea.com/api/v1/repos/JerryALT/iw3sp_mod/releases?limit=5"
METADATA_FILE = "deckops_iw3sp.json"


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_latest_release():
    """
    Query the Gitea API for the latest stable IW3SP-MOD release.

    Gitea doesn't have a /releases/latest endpoint like GitHub, so we
    fetch the most recent releases and pick the first one that is not a
    draft or prerelease.

    Returns (version, zip_url) or raises on failure.
    """
    req = urllib.request.Request(GITEA_API, headers=_BROWSER_UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        releases = json.loads(r.read().decode("utf-8"))

    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue

        tag = release.get("tag_name", "")
        version = tag.lstrip("v") if tag else "unknown"

        # Find the .zip asset (not source code archives)
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if name.endswith(".zip"):
                return version, asset["browser_download_url"]

        # No uploaded zip asset — fall back to the source zipball
        zipball = release.get("zipball_url")
        if zipball:
            return version, zipball

    raise RuntimeError("No stable IW3SP-MOD release found on Gitea")


# _download and _BROWSER_UA imported from net.py.


def is_iw3sp_installed(install_dir: str) -> bool:
    """Returns True if iw3sp.exe.bak exists (meaning the mod rename is active)."""
    return os.path.exists(os.path.join(install_dir, "iw3sp.exe.bak"))


# ── public API ────────────────────────────────────────────────────────────────

def install_iw3sp(game: dict, steam_root: str,
                  proton_path: str, compatdata_path: str,
                  on_progress=None, source: str = "steam"):
    """
    Install IW3SP-MOD for Call of Duty 4 singleplayer.

    Downloads and extracts the mod zip into the CoD4 install directory.
    For Steam games, renames iw3sp.exe -> iw3sp.exe.bak and
    iw3sp_mod.exe -> iw3sp.exe so Steam launches the mod transparently.
    For own games, skips the rename -- the shortcut points at
    iw3sp_mod.exe directly.

    game            — entry from detect_games
    steam_root      — path to Steam root (kept for API consistency)
    proton_path     — path to the proton executable (kept for API consistency)
    compatdata_path — path to the CoD4 compatdata prefix (kept for API consistency)
    on_progress     — optional callback(percent: int, status: str)
    source          — "steam" or "own", controls whether exe rename happens
    """
    install_dir = game["install_dir"]
    zip_dest    = os.path.join(install_dir, "iw3sp_mod.zip")

    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    # Fetch latest release info from Gitea API
    prog(2, "Checking for latest IW3SP-MOD release...")
    try:
        version, zip_url = _get_latest_release()
    except Exception as ex:
        raise RuntimeError(f"Failed to fetch IW3SP-MOD release info: {ex}")

    # Download zip
    prog(5, f"Downloading IW3SP-MOD v{version}...")
    _download(
        zip_url,
        zip_dest,
        lambda p, m: prog(5 + int(p * 0.55), m),
        f"Downloading IW3SP-MOD v{version}...",
    )

    # Extract into CoD4 root
    prog(60, "Extracting IW3SP-MOD...")
    with zipfile.ZipFile(zip_dest) as zf:
        zf.extractall(install_dir)
    os.remove(zip_dest)

    # Rename iw3sp.exe -> iw3sp.exe.bak and iw3sp_mod.exe -> iw3sp.exe
    # Steam games: swap so Steam launches the mod transparently.
    # Own games: skip -- the shortcut points at iw3sp_mod.exe directly
    # and the original exe may not even exist.
    if source != "own":
        iw3sp     = os.path.join(install_dir, "iw3sp.exe")
        iw3sp_bak = os.path.join(install_dir, "iw3sp.exe.bak")
        iw3sp_mod = os.path.join(install_dir, "iw3sp_mod.exe")

        prog(80, "Replacing iw3sp.exe...")
        if os.path.exists(iw3sp) and not os.path.exists(iw3sp_bak):
            os.rename(iw3sp, iw3sp_bak)

        if os.path.exists(iw3sp_mod):
            os.rename(iw3sp_mod, iw3sp)
    else:
        prog(80, "Own game -- skipping exe rename")

    # Write metadata
    prog(95, "Saving metadata...")
    meta_path = os.path.join(install_dir, METADATA_FILE)
    with open(meta_path, "w") as f:
        json.dump({"version": version}, f, indent=2)

    prog(100, f"IW3SP-MOD v{version} installation complete!")


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
