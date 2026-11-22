"""
t6sp_mod.py - DeckOps installer for T6SP-MOD (Call of Duty: Black Ops II Singleplayer)

Rattpak's T6SP-MOD, a dedicated singleplayer client for Black Ops II.
https://github.com/Rattpak/T6SP-Mod-Release

Downloads the mod exe and companion DLL from Rattpak's latest GitHub release
into the BO2 install directory.

The stock t6sp.exe is left untouched; T6SP-Mod.exe and t6sp-mod.dll go next to it.
Steam games get a launch option that swaps t6sp.exe for T6SP-Mod.exe (same as
IW3SP), so file verification and game updates can't undo the mod. Own games
get the same launch option on their t6sp.exe shortcut (shortcut.migrate_own_t6sp
moves older shortcuts that pointed at T6SP-Mod.exe).
Older installs replaced t6sp.exe and kept the original as t6sp.exe.bak. That
backup is moved back on install.

Progress is reported via a callback:
    on_progress(percent: int, status: str)
"""

import os
import json
import shutil

from net import download as _download, github_asset

# Rattpak's releases. The pinned URLs are only used if the GitHub API lookup fails
_REPO = "Rattpak/T6SP-Mod-Release"
_PIN = "https://github.com/Rattpak/T6SP-Mod-Release/releases/download/v1.0.0-Beta/"

MOD_EXE = "T6SP-Mod.exe"
APPID = 202970
LAUNCH_OPTS = "bash -c 'exec \"${@/t6sp.exe/T6SP-Mod.exe}\"' -- %command%"

METADATA_FILE = "deckops_t6sp_mod.json"


# --- helpers

# --- public API

def install_t6sp_mod(game: dict, steam_root: str,
                     proton_path: str, compatdata_path: str,
                     on_progress=None, source: str = "steam"):
    """
    Install T6SP-MOD for Call of Duty: Black Ops II singleplayer.

    Downloads the mod exe and DLL into the game directory, moves back an
    old t6sp.exe.bak if there is one, and sets the launch option for Steam games.

    game            : entry from detect_games
    steam_root      : path to Steam root (kept for API consistency)
    proton_path     : path to the proton executable (kept for API consistency)
    compatdata_path : path to the BO2 compatdata prefix (kept for API consistency)
    on_progress     : optional callback(percent: int, status: str)
    source          : "steam" or "own"
    """
    install_dir = game["install_dir"]

    prog = on_progress or (lambda *a: None)

    prog(2, "Installing Rattpak's T6SP-MOD (Beta)...")

    exe_url, exe_dg = github_asset(_REPO, "T6SP-Mod.exe", fallback=_PIN + "T6SP-Mod.exe")
    dll_url, dll_dg = github_asset(_REPO, "t6sp-mod.dll", fallback=_PIN + "t6sp-mod.dll")

    # Download mod exe
    exe_dest = os.path.join(install_dir, "t6sp_mod_tmp.exe")
    prog(5, "Downloading T6SP-MOD exe...")
    _download(
        exe_url,
        exe_dest,
        lambda p, m: prog(5 + int(p * 0.35), m),
        "Downloading T6SP-MOD exe...",
        digest=exe_dg,
    )

    # Download companion DLL
    dll_dest = os.path.join(install_dir, "t6sp-mod.dll")
    prog(45, "Downloading T6SP-MOD DLL...")
    _download(
        dll_url,
        dll_dest,
        lambda p, m: prog(45 + int(p * 0.30), m),
        "Downloading T6SP-MOD DLL...",
        digest=dll_dg,
    )

    shutil.move(exe_dest, os.path.join(install_dir, MOD_EXE))

    # Older installs replaced t6sp.exe: put the original back
    t6sp_bak = os.path.join(install_dir, "t6sp.exe.bak")
    if os.path.exists(t6sp_bak):
        prog(80, "Restoring original t6sp.exe...")
        shutil.move(t6sp_bak, os.path.join(install_dir, "t6sp.exe"))

    if source != "own":
        prog(85, "Setting launch options...")
        try:
            from wrapper import set_launch_options
            set_launch_options(steam_root, APPID, LAUNCH_OPTS)
        except Exception as ex:
            prog(85, f"⚠ Could not set launch options: {ex}")

    # Write metadata
    prog(95, "Saving metadata...")
    meta_path = os.path.join(install_dir, METADATA_FILE)
    with open(meta_path, "w") as f:
        json.dump({"client": "t6sp_mod", "source": source}, f, indent=2)

    prog(100, "T6SP-MOD (Beta) installation complete!")
