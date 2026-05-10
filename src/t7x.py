"""
t7x.py - DeckOps installer for the T7X mod client (Black Ops III)

T7X is an AlterWare standalone client for BO3. Instead of dropping files
into the stock BO3 directory, DeckOps creates a sibling directory
("DeckOps-T7X") next to the BO3 install and builds a symlink farm that
mirrors the game's file tree. BlackOps3.exe is copied as a real file
(T7X hash-checks it), and t7x.exe is downloaded into the sibling dir.

This keeps the Steam-managed BO3 directory completely clean. T7X writes
its runtime data (t7x/ subdirectory, ext.dll, mods/, usermaps/) into
the sibling dir as real files — symlinks are never written through.

T7X is always launched via its own non-Steam shortcut with GE-Proton
as the compat tool. No launch options are needed.

Progress is reported via a callback:
    on_progress(percent: int, status: str)
"""

import json
import os
import shutil

from net import download as _download

# ── T7X constants ─────────────────────────────────────────────────────────────

T7X_URL           = "https://master.bo3.eu/t7x/t7x.exe"
T7X_EXE           = "t7x.exe"
T7X_METADATA_FILE = "deckops_t7x.json"
T7X_DATA_DIR      = "t7x"               # created by t7x.exe on first run
T7X_SIBLING_DIR   = "DeckOps-T7X"       # sibling dir name (next to BO3 install)
BO3_EXE           = "BlackOps3.exe"      # copied (not symlinked) — T7X hash-checks it


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_sibling_dir(install_dir: str) -> str:
    """Return the path to the DeckOps-T7X sibling directory."""
    return os.path.join(os.path.dirname(install_dir), T7X_SIBLING_DIR)


def _build_symlink_farm(src_dir: str, dst_dir: str, copy_files: set = None):
    """
    Mirror *src_dir* into *dst_dir* using symlinks for files and real
    directories for the tree structure.

    Files whose basename is in *copy_files* are copied as real files
    instead of symlinked (e.g. BlackOps3.exe which T7X hash-checks).
    """
    if copy_files is None:
        copy_files = set()

    for dirpath, dirnames, filenames in os.walk(src_dir):
        # Mirror the directory structure
        rel = os.path.relpath(dirpath, src_dir)
        dst_subdir = os.path.join(dst_dir, rel) if rel != "." else dst_dir
        os.makedirs(dst_subdir, exist_ok=True)

        for fname in filenames:
            src_file = os.path.join(dirpath, fname)
            dst_file = os.path.join(dst_subdir, fname)

            # Skip if destination already exists (re-run safety)
            if os.path.exists(dst_file) or os.path.islink(dst_file):
                continue

            if fname in copy_files:
                shutil.copy2(src_file, dst_file)
            else:
                os.symlink(src_file, dst_file)


def is_t7x_installed(install_dir: str) -> bool:
    """
    Returns True if the T7X sibling directory exists and contains
    both the T7X exe and the metadata file.

    install_dir — the stock BO3 install directory (from detect_games).
    """
    sibling = _get_sibling_dir(install_dir)
    return (
        os.path.isdir(sibling)
        and os.path.exists(os.path.join(sibling, T7X_EXE))
        and os.path.exists(os.path.join(sibling, T7X_METADATA_FILE))
    )


# ── T7X public API ────────────────────────────────────────────────────────────

def install_t7x(game: dict, on_progress=None):
    """
    Install T7X (AlterWare) for Call of Duty: Black Ops III.

    Creates a sibling directory next to the BO3 install, builds a symlink
    farm of the stock game files, copies BlackOps3.exe as a real file,
    and downloads t7x.exe from the AlterWare master server.

    Returns the path to the sibling directory so the caller can update
    game["install_dir"] for shortcut creation.

    game        — entry from detect_games with install_dir
    on_progress — optional callback(percent: int, status: str)
    """
    install_dir = game["install_dir"]
    sibling     = _get_sibling_dir(install_dir)

    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    # Create sibling directory
    prog(2, "Creating T7X game directory...")
    os.makedirs(sibling, exist_ok=True)

    # Build symlink farm (copy BlackOps3.exe, symlink everything else)
    prog(5, "Building symlink farm...")
    _build_symlink_farm(install_dir, sibling, copy_files={BO3_EXE})

    # Download t7x.exe
    exe_dest = os.path.join(sibling, T7X_EXE)
    prog(30, "Downloading T7X client...")
    _download(
        T7X_URL,
        exe_dest,
        lambda p, m: prog(30 + int(p * 0.55), m),
        "Downloading T7X client...",
    )

    # Write metadata
    prog(90, "Saving metadata...")
    meta_path = os.path.join(sibling, T7X_METADATA_FILE)
    with open(meta_path, "w") as f:
        json.dump({
            "client":       "t7x",
            "exe":          T7X_EXE,
            "original_dir": install_dir,
        }, f, indent=2)

    # Set player name from DeckOps config
    prog(95, "Setting player name...")
    try:
        import config as _cfg
        name = _cfg.get_player_name()
        if name:
            set_player_name(sibling, name)
    except Exception:
        pass  # Non-fatal — user can set it later in Settings

    prog(100, "T7X installation complete!")
    return sibling


def set_player_name(sibling_dir: str, player_name: str):
    """
    Write or update the player name in T7X's properties.json.

    T7X stores the player name in t7x/players/properties.json as:
        {"playerName": "<name>"}

    Creates the file and parent directories if they don't exist.
    Preserves any other keys already in the file.
    """
    props_path = os.path.join(sibling_dir, "t7x", "players", "properties.json")
    os.makedirs(os.path.dirname(props_path), exist_ok=True)

    # Read existing properties if present
    data = {}
    if os.path.exists(props_path):
        try:
            with open(props_path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = {}

    data["playerName"] = player_name

    with open(props_path, "w") as f:
        json.dump(data, f)


def uninstall_t7x(game: dict):
    """
    Remove T7X from a BO3 install.

    Deletes the entire DeckOps-T7X sibling directory (symlinks + any
    real files T7X created at runtime). The original BO3 install
    directory is untouched.
    """
    install_dir = game["install_dir"]
    sibling     = _get_sibling_dir(install_dir)

    if os.path.isdir(sibling):
        shutil.rmtree(sibling, ignore_errors=True)
