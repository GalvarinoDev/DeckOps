"""
t6sp_mod.py - DeckOps installer for T6SP-MOD (Call of Duty: Black Ops II Singleplayer)

Rattpak's T6SP-MOD — a dedicated singleplayer client for Black Ops II.
https://github.com/Rattpak/T6SP-Mod-Release

Downloads the mod exe and companion DLL from the DeckOps repo and drops
them into the BO2 install directory.

For Steam games:
  - Backs up t6sp.exe -> t6sp.exe.bak
  - Overwrites t6sp.exe with the mod exe
  - Drops t6sp-mod.dll alongside it
  This lets Steam launch T6SP-MOD transparently via the existing SP shortcut.

For own games:
  - Same backup and overwrite flow
  - The non-Steam shortcut already points at t6sp.exe

Progress is reported via a callback:
    on_progress(percent: int, status: str)
"""

import os
import json
import shutil

from identity import GITHUB_RAW
from net import download as _download

# T6SP-MOD files hosted on the DeckOps repo.
# When Rattpak publishes the beta on his own GitHub, update these URLs.
_BASE_URL = f"{GITHUB_RAW}/assets/T6SP_BETA"
_MOD_EXE_URL = f"{_BASE_URL}/t6sp.exe"
_MOD_DLL_URL = f"{_BASE_URL}/t6sp-mod.dll"

METADATA_FILE = "deckops_t6sp_mod.json"


# ── helpers ───────────────────────────────────────────────────────────────────

def is_t6sp_mod_installed(install_dir: str) -> bool:
    """Returns True if t6sp.exe.bak exists (meaning the mod is active)."""
    return os.path.exists(os.path.join(install_dir, "t6sp.exe.bak"))


# ── public API ────────────────────────────────────────────────────────────────

def install_t6sp_mod(game: dict, steam_root: str,
                     proton_path: str, compatdata_path: str,
                     on_progress=None, source: str = "steam"):
    """
    Install T6SP-MOD for Call of Duty: Black Ops II singleplayer.

    Downloads the mod exe and DLL, backs up the original t6sp.exe,
    and drops the mod files into the game directory.

    game            — entry from detect_games
    steam_root      — path to Steam root (kept for API consistency)
    proton_path     — path to the proton executable (kept for API consistency)
    compatdata_path — path to the BO2 compatdata prefix (kept for API consistency)
    on_progress     — optional callback(percent: int, status: str)
    source          — "steam" or "own"
    """
    install_dir = game["install_dir"]

    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    prog(2, "Installing Rattpak's T6SP-MOD (Beta)...")

    # Download mod exe
    exe_dest = os.path.join(install_dir, "t6sp_mod_tmp.exe")
    prog(5, "Downloading T6SP-MOD exe...")
    _download(
        _MOD_EXE_URL,
        exe_dest,
        lambda p, m: prog(5 + int(p * 0.35), m),
        "Downloading T6SP-MOD exe...",
    )

    # Download companion DLL
    dll_dest = os.path.join(install_dir, "t6sp-mod.dll")
    prog(45, "Downloading T6SP-MOD DLL...")
    _download(
        _MOD_DLL_URL,
        dll_dest,
        lambda p, m: prog(45 + int(p * 0.30), m),
        "Downloading T6SP-MOD DLL...",
    )

    # Backup original t6sp.exe and replace with mod exe
    t6sp     = os.path.join(install_dir, "t6sp.exe")
    t6sp_bak = os.path.join(install_dir, "t6sp.exe.bak")

    prog(80, "Backing up original t6sp.exe...")
    if os.path.exists(t6sp) and not os.path.exists(t6sp_bak):
        shutil.copy2(t6sp, t6sp_bak)

    prog(85, "Replacing t6sp.exe with T6SP-MOD...")
    shutil.move(exe_dest, t6sp)

    # Write metadata
    prog(95, "Saving metadata...")
    meta_path = os.path.join(install_dir, METADATA_FILE)
    with open(meta_path, "w") as f:
        json.dump({"client": "t6sp_mod", "source": source}, f, indent=2)

    prog(100, "T6SP-MOD (Beta) installation complete!")


def uninstall_t6sp_mod(game: dict):
    """
    Restore t6sp.exe from backup and remove T6SP-MOD files.
    """
    install_dir = game["install_dir"]

    t6sp     = os.path.join(install_dir, "t6sp.exe")
    t6sp_bak = os.path.join(install_dir, "t6sp.exe.bak")

    # Restore original exe from backup
    if os.path.exists(t6sp_bak):
        if os.path.exists(t6sp):
            os.remove(t6sp)
        os.rename(t6sp_bak, t6sp)

    # Remove mod DLL
    dll_path = os.path.join(install_dir, "t6sp-mod.dll")
    if os.path.exists(dll_path):
        os.remove(dll_path)

    # Remove metadata
    meta = os.path.join(install_dir, METADATA_FILE)
    if os.path.exists(meta):
        os.remove(meta)
