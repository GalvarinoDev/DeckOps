#!/bin/bash
# deckops_identity.sh — Branch identity for shell scripts
#
# Sourced by install.sh, launcher.sh, and deckops_uninstall.sh.
# Change BRANCH to switch between nightly and stable.
# Everything else derives from it.
#
# Usage in any shell script:
#   SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
#   source "$SCRIPT_DIR/deckops_identity.sh"

# ── The one value you change per branch ──────────────────────────────────────

BRANCH="stable"  # "nightly" or "stable"

# ── Everything below is derived ──────────────────────────────────────────────

GITHUB_USER="GalvarinoDev"

if [ "$BRANCH" = "nightly" ]; then
    GITHUB_REPO="DeckOps-Nightly"
    INSTALL_DIR_NAME="DeckOps-Nightly"
    XDG_ID="deckops-nightly"
    APP_TITLE="DeckOps Nightly"
    DESKTOP_COMMENT="DeckOps Nightly — Experimental build"
    BUILD_FALLBACK="nightly"
else
    GITHUB_REPO="DeckOps"
    INSTALL_DIR_NAME="DeckOps"
    XDG_ID="deckops"
    APP_TITLE="DeckOps"
    DESKTOP_COMMENT="DeckOps — Call of Duty on SteamOS"
    BUILD_FALLBACK="stable"
fi

GITHUB_RAW="https://raw.githubusercontent.com/$GITHUB_USER/$GITHUB_REPO/main"
INSTALL_DIR="$HOME/$INSTALL_DIR_NAME"
VENV_DIR="$INSTALL_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python3"
ENTRY_POINT="$INSTALL_DIR/src/main.py"
ICON_PATH="$INSTALL_DIR/assets/images/icon.png"
MUSIC_DIR="$INSTALL_DIR/assets/music"
DESKTOP_FILE="$HOME/.local/share/applications/${XDG_ID}.desktop"
DESKTOP_SHORTCUT="$HOME/Desktop/${INSTALL_DIR_NAME}.desktop"
