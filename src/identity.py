"""
identity.py — DeckOps branch identity

Single source of truth for everything that differs between Stable and
Nightly builds. Every module that needs a repo URL, install path, or
branding string imports from here instead of hardcoding it.

To switch between branches, change ONLY this file:
    BRANCH = "stable"  →  BRANCH = "stable"

Everything else derives from that one value.

Zero internal DeckOps imports so it can be loaded first without
circular-dependency risk (same pattern as log.py).
"""

import os

# ── The one value you change per branch ──────────────────────────────────────

BRANCH = "stable"  # "nightly" or "stable"

# ── Everything below is derived ──────────────────────────────────────────────

GITHUB_USER = "GalvarinoDev"

GITHUB_REPO = "DeckOps-Nightly" if BRANCH == "nightly" else "DeckOps"

GITHUB_RAW = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main"

GITHUB_API = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}"

# Local install directory name — no path, just the folder name
INSTALL_DIR_NAME = "DeckOps-Nightly" if BRANCH == "nightly" else "DeckOps"

# Full install path
INSTALL_DIR = os.path.expanduser(f"~/{INSTALL_DIR_NAME}")

# Config and log paths
CONFIG_PATH = os.path.join(INSTALL_DIR, "deckops.json")
LOG_DIR = os.path.join(INSTALL_DIR, "logs")

# XDG paths (ledger, save backups, plutonium prefix, shared DLLs)
_XDG_ID = "deckops-nightly" if BRANCH == "nightly" else "deckops"
LEDGER_PATH = os.path.expanduser(f"~/.config/{_XDG_ID}/vdf_edits.json")

# Desktop entry paths
DESKTOP_FILE = os.path.expanduser(
    f"~/.local/share/applications/{_XDG_ID}.desktop"
)
DESKTOP_SHORTCUT_NAME = f"{INSTALL_DIR_NAME}.desktop"

# Venv python path
VENV_PYTHON = os.path.join(INSTALL_DIR, ".venv", "bin", "python3")

# ── UI branding ──────────────────────────────────────────────────────────────

APP_TITLE = "DeckOps Nightly" if BRANCH == "nightly" else "DeckOps"

# Set to None for stable — the UI badge is omitted entirely
BUILD_BADGE = "NIGHTLY BUILD" if BRANCH == "nightly" else None

BUILD_HASH_FALLBACK = "nightly" if BRANCH == "nightly" else "stable"

DESKTOP_ENTRY_NAME = APP_TITLE
DESKTOP_ENTRY_COMMENT = (
    f"{APP_TITLE} — Experimental build"
    if BRANCH == "nightly"
    else f"{APP_TITLE} — Call of Duty on SteamOS"
)

# ── GitHub raw asset URLs ────────────────────────────────────────────────────

def asset_url(path: str) -> str:
    """Build a raw GitHub URL for a repo asset.

    Usage:
        from identity import asset_url
        url = asset_url("assets/images/icon.png")
        # → https://raw.githubusercontent.com/GalvarinoDev/DeckOps/refs/heads/main/assets/images/icon.png
    """
    return f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/refs/heads/main/{path}"


def api_url(endpoint: str) -> str:
    """Build a GitHub API URL.

    Usage:
        from identity import api_url
        url = api_url("commits/main")
        # → https://api.github.com/repos/GalvarinoDev/DeckOps/commits/main
    """
    return f"{GITHUB_API}/{endpoint}"
