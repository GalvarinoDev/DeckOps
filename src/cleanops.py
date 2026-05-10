"""
cleanops.py - DeckOps installer for the CleanOps mod (Black Ops III)

CleanOps is a lightweight DLL mod that improves performance and fixes
various issues. Single d3d11.dll drop, no exe replacement.

For Steam games:
  - Drops d3d11.dll into the install directory
  - Sets launch options: WINEDLLOVERRIDES="d3d11=n,b" %command%

For own games:
  - Drops d3d11.dll into the install directory
  - Launch options are handled by the non-Steam shortcut instead

Progress is reported via a callback:
    on_progress(percent: int, status: str)
"""

import json
import os

from net import download as _download

from log import get_logger

_log = get_logger(__name__)


# ── CleanOps constants ────────────────────────────────────────────────────────

DLL_URL       = "https://raw.githubusercontent.com/notnightwolf/cleanopsT7/main/d3d11.dll"
DLL_NAME      = "d3d11.dll"
METADATA_FILE = "deckops_cleanops.json"
LAUNCH_OPTS   = 'WINEDLLOVERRIDES="d3d11=n,b" %command%'
APPID         = "311210"


# ── helpers ───────────────────────────────────────────────────────────────────

def is_cleanops_installed(install_dir: str) -> bool:
    """Returns True if the CleanOps DLL and metadata file are both present."""
    return (
        os.path.exists(os.path.join(install_dir, DLL_NAME))
        and os.path.exists(os.path.join(install_dir, METADATA_FILE))
    )


# ── CleanOps public API ──────────────────────────────────────────────────────

def install_cleanops(game: dict, steam_root: str,
                     proton_path: str, compatdata_path: str,
                     on_progress=None, source: str = "steam"):
    """
    Install CleanOps for Call of Duty: Black Ops III.

    Downloads d3d11.dll from GitHub and drops it into the BO3 install
    directory. For Steam copies, sets the Wine DLL override launch option
    so the DLL loads under Proton.

    game            — entry from detect_games
    steam_root      — path to Steam root
    proton_path     — path to the proton executable (kept for API consistency)
    compatdata_path — path to the BO3 compatdata prefix (kept for API consistency)
    on_progress     — optional callback(percent: int, status: str)
    source          — "steam" or "own", controls whether launch options are set
    """
    install_dir = game["install_dir"]

    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    # Download DLL
    dll_dest = os.path.join(install_dir, DLL_NAME)
    prog(5, "Downloading CleanOps d3d11.dll...")
    _download(
        DLL_URL,
        dll_dest,
        lambda p, m: prog(5 + int(p * 0.60), m),
        "Downloading CleanOps d3d11.dll...",
    )

    # Set launch options for Steam copies
    if source != "own":
        prog(70, "Setting launch options...")
        try:
            from wrapper import set_launch_options
            set_launch_options(steam_root, APPID, LAUNCH_OPTS)
        except Exception as ex:
            prog(70, f"⚠ Could not set launch options: {ex}")

    # Write metadata
    prog(90, "Saving metadata...")
    meta_path = os.path.join(install_dir, METADATA_FILE)
    with open(meta_path, "w") as f:
        json.dump({"client": "cleanops", "dll": DLL_NAME}, f, indent=2)

    prog(100, "CleanOps installation complete!")


def uninstall_cleanops(game: dict, steam_root: str = None):
    """
    Remove CleanOps from a BO3 install directory.

    Deletes d3d11.dll and the metadata file. Clears launch options
    for Steam copies if steam_root is provided.
    """
    install_dir = game["install_dir"]

    # Remove DLL
    dll_path = os.path.join(install_dir, DLL_NAME)
    if os.path.exists(dll_path):
        os.remove(dll_path)

    # Remove metadata
    meta_path = os.path.join(install_dir, METADATA_FILE)
    if os.path.exists(meta_path):
        os.remove(meta_path)

    # Clear launch options
    if steam_root:
        try:
            from wrapper import clear_launch_options
            clear_launch_options(steam_root, APPID)
        except Exception:
            _log.debug("failed to clear launch options", exc_info=True)
