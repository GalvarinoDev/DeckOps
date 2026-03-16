"""
iw3sp.py - DeckOps installer for IW3SP-MOD (Call of Duty 4: Modern Warfare Singleplayer)

Downloads the latest iw3sp_mod release zip from Gitea and extracts it into
the CoD4 install directory. Sets a Steam launch option on appid 7940 so that
Steam launches iw3sp_mod.exe directly — no exe renaming or backup needed.

CoD4 Multiplayer is unaffected because it runs as a non-Steam shortcut
pointing at iw3mp.exe, completely independent of appid 7940.

Progress is reported via a callback:
    on_progress(percent: int, status: str)
"""

import os
import json
import zipfile
import subprocess
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
    """Returns True if iw3sp_mod.exe is present in the install directory."""
    return os.path.exists(os.path.join(install_dir, "iw3sp_mod.exe"))


# ── public API ────────────────────────────────────────────────────────────────

def install_iw3sp(game: dict, steam_root: str,
                  proton_path: str, compatdata_path: str,
                  on_progress=None):
    """
    Install IW3SP-MOD for Call of Duty 4 singleplayer.

    Extracts the mod zip into the CoD4 install directory and sets a Steam
    launch option on appid 7940 to run iw3sp_mod.exe instead of iw3sp.exe.
    The original iw3sp.exe is left untouched.

    game            — entry from detect_games.find_installed_games()
    steam_root      — path to Steam root
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
        lambda p, m: prog(5 + int(p * 0.60), m),
        "Downloading IW3SP-MOD...",
    )

    # Extract into CoD4 root — leave all files in place, including the zip's extras
    prog(65, "Extracting IW3SP-MOD...")
    with zipfile.ZipFile(zip_dest) as zf:
        zf.extractall(install_dir)
    os.remove(zip_dest)

    # Write metadata
    prog(80, "Saving metadata...")
    meta_path = os.path.join(install_dir, METADATA_FILE)
    with open(meta_path, "w") as f:
        json.dump({"version": "4.1.5"}, f, indent=2)

    # Write launch option via xterm — konsole conflicts with Qt
    prog(90, "Setting Steam launch option...")
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "set_launch_iw3sp.sh")
    try:
        subprocess.run([
            "xterm", "-title", "DeckOps - Applying launch option...",
            "-e", "bash", script
        ], check=True)
    except Exception as ex:
        prog(90, f"Warning: could not set launch option: {ex}")

    prog(100, "IW3SP-MOD installation complete!")


def uninstall_iw3sp(game: dict):
    """
    Remove the DeckOps metadata file for IW3SP-MOD.
    Extracted mod files are left in place — they do not interfere with the
    base game and Steam will handle them via file validation if needed.
    """
    meta = os.path.join(game["install_dir"], METADATA_FILE)
    if os.path.exists(meta):
        os.remove(meta)
