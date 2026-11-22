"""
cleanops.py: DeckOps installer for the CleanOps mod (Black Ops III)

CleanOps is a lightweight DLL mod for BO3 that improves performance and
fixes various issues. Both Steam and own installs get d3d11.dll in the
install directory.

Steam games also get the launch option
WINEDLLOVERRIDES="d3d11=n,b" %command%. Own games get it from the
non-Steam shortcut instead.

Progress is reported via a callback:
    on_progress(percent: int, status: str)
"""

import json
import os

from net import download as _download

from log import get_logger

_log = get_logger(__name__)


# --- CleanOps constants

DLL_URL       = "https://raw.githubusercontent.com/notnightwolf/cleanopsT7/main/d3d11.dll"
DLL_NAME      = "d3d11.dll"
METADATA_FILE = "deckops_cleanops.json"
LAUNCH_OPTS   = 'WINEDLLOVERRIDES="d3d11=n,b" %command%'
APPID         = "311210"


# --- helpers

# --- CleanOps public API

def install_cleanops(game: dict, steam_root: str,
                     proton_path: str, compatdata_path: str,
                     on_progress=None, source: str = "steam"):
    """
    Install CleanOps for Call of Duty: Black Ops III.

    Downloads d3d11.dll from GitHub into the BO3 install directory. Steam
    copies also get the Wine DLL override launch option so the DLL loads
    under Proton.

    game            entry from detect_games
    steam_root      path to Steam root
    proton_path     path to the proton executable (unused, kept for API consistency)
    compatdata_path path to the BO3 compatdata prefix (unused, kept for API consistency)
    on_progress     optional callback(percent: int, status: str)
    source          "steam" or "own", controls whether launch options are set
    """
    install_dir = game["install_dir"]

    prog = on_progress or (lambda *a: None)

    # Download the DLL
    dll_dest = os.path.join(install_dir, DLL_NAME)
    prog(5, "Downloading CleanOps d3d11.dll...")
    _download(
        DLL_URL,
        dll_dest,
        lambda p, m: prog(5 + int(p * 0.65), m),
        "Downloading CleanOps d3d11.dll...",
    )

    # Set launch options for Steam copies
    if source != "own":
        prog(75, "Setting launch options...")
        try:
            from wrapper import set_launch_options
            set_launch_options(steam_root, APPID, LAUNCH_OPTS)
        except Exception as ex:
            prog(70, f"⚠ Could not set launch options: {ex}")

    # Write the metadata file
    prog(90, "Saving metadata...")
    meta_path = os.path.join(install_dir, METADATA_FILE)
    with open(meta_path, "w") as f:
        json.dump({"client": "cleanops", "dll": DLL_NAME}, f, indent=2)

    prog(100, "CleanOps installation complete!")
