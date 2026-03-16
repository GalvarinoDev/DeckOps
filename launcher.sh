#!/bin/bash
# launcher.sh — DeckOps entry point

INSTALL_DIR="$HOME/DeckOps"
GITHUB_RAW="https://raw.githubusercontent.com/GalvarinoDev/DeckOps/main"
LOCKFILE="$HOME/.deckops_installing"

# ── Installing or first-time — run install directly ───────────────────────────
if [ ! -d "$INSTALL_DIR" ] || [ -f "$LOCKFILE" ]; then
    touch "$LOCKFILE"
    curl -sL "$GITHUB_RAW/install.sh" | bash
    rm -f "$LOCKFILE"
    exit 0
fi

# ── Already installed — ask what to do ───────────────────────────────────────
choice=$(zenity \
    --list \
    --title="DeckOps" \
    --text="DeckOps is already installed.\nWhat would you like to do?" \
    --column="Action" \
    --hide-header \
    "Launch DeckOps" \
    "Reinstall" \
    "Uninstall" \
    --width=300 --height=220 \
    2>/dev/null)

[ $? -ne 0 ] && exit 0

case "$choice" in
    "Launch DeckOps")
        VENV_PYTHON="$INSTALL_DIR/.venv/bin/python3"
        ENTRY_POINT="$INSTALL_DIR/src/main.py"
        if [ -f "$VENV_PYTHON" ] && [ -f "$ENTRY_POINT" ]; then
            exec "$VENV_PYTHON" "$ENTRY_POINT"
        else
            zenity --error --title="DeckOps" \
                --text="DeckOps installation appears incomplete.\nTry reinstalling." \
                2>/dev/null
        fi
        ;;
    "Reinstall")
        touch "$LOCKFILE"
        curl -sL "$GITHUB_RAW/install.sh" | bash
        rm -f "$LOCKFILE"
        exit 0
        ;;
    "Uninstall")
        if [ -f "$INSTALL_DIR/deckops_uninstall.sh" ]; then
            bash "$INSTALL_DIR/deckops_uninstall.sh"
        else
            curl -sL "$GITHUB_RAW/deckops_uninstall.sh" | bash
        fi
        exit 0
        ;;
esac
