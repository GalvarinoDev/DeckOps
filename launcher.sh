#!/bin/bash
# launcher.sh: DeckOps entry point

# Source deckops_identity.sh if present, otherwise use the defaults below
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/deckops_identity.sh" ]; then
    source "$SCRIPT_DIR/deckops_identity.sh"
elif [ -f "$HOME/DeckOps/deckops_identity.sh" ]; then
    source "$HOME/DeckOps/deckops_identity.sh"
elif [ -f "$HOME/DeckOps-Nightly/deckops_identity.sh" ]; then
    source "$HOME/DeckOps-Nightly/deckops_identity.sh"
else
    GITHUB_USER="GalvarinoDev"
    GITHUB_REPO="DeckOps"
    INSTALL_DIR="$HOME/DeckOps"
    VENV_PYTHON="$INSTALL_DIR/.venv/bin/python3"
    ENTRY_POINT="$INSTALL_DIR/src/main.py"
    APP_TITLE="DeckOps"
fi

GITHUB_RAW="https://raw.githubusercontent.com/$GITHUB_USER/$GITHUB_REPO/main"
LOCKFILE="$HOME/.deckops_installing"
VERSION_FILE="$INSTALL_DIR/VERSION"
UPDATE_DIR="$INSTALL_DIR/.update"

# --- Installing or first-time: run install directly
if [ ! -d "$INSTALL_DIR" ] || [ -f "$LOCKFILE" ]; then
    touch "$LOCKFILE"
    curl -sL "$GITHUB_RAW/install.sh" | bash
    rm -f "$LOCKFILE"
    exit 0
fi

# --- Update check
check_for_updates() {
    local LOCAL_SHA REMOTE_SHA CHANGED_FILES FILE_COUNT RESET_HINT=""
    local FORCE="${1:-}"

    # Read local version (commit SHA). "0" means never updated.
    LOCAL_SHA="0"
    [ -f "$VERSION_FILE" ] && LOCAL_SHA=$(cat "$VERSION_FILE" | tr -d '[:space:]')

    # Fetch latest commit SHA from GitHub API (unauthenticated, 60 req/hr)
    REMOTE_SHA=$(curl -sf --max-time 10 \
        "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/commits/main" \
        | grep -m1 '"sha"' | cut -d'"' -f4)

    # If fetch failed or same version, skip
    [ -z "$REMOTE_SHA" ] && return 0
    [ "$LOCAL_SHA" = "$REMOTE_SHA" ] && return 0

    # First install from install.sh won't have a real SHA, so do a full refresh
    if [ "$LOCAL_SHA" = "0" ]; then
        FILE_COUNT="unknown number of"
        CHANGED_FILES=""
    else
        # Get list of changed files from GitHub compare API
        CHANGED_FILES=$(curl -sf --max-time 15 \
            "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/compare/${LOCAL_SHA}...${REMOTE_SHA}" \
            | grep '"filename"' | cut -d'"' -f4)

        [ -z "$CHANGED_FILES" ] && return 0

        FILE_COUNT=$(echo "$CHANGED_FILES" | wc -l)
        # Mirrors ui_manage._reset_hint: config.py or more than 3 src/ files changed
        if echo "$CHANGED_FILES" | grep -qx 'src/config.py' || \
           [ "$(echo "$CHANGED_FILES" | grep -c '^src/')" -gt 3 ]; then
            RESET_HINT="\n\nThis update changed how DeckOps sets up games.\nIf anything acts up, open Settings and use Reset Config,\nthen set up your games again."
        fi
    fi

    # Ask user (skip if triggered from in-app update button)
    if [ "$FORCE" != "force" ]; then
        zenity --question \
            --title="$APP_TITLE Update" \
            --text="An update is available.\n${FILE_COUNT} file(s) changed.\n\nUpdate now?" \
            --ok-label="Update" \
            --cancel-label="Skip" \
            --width=300 \
            2>/dev/null

        [ $? -ne 0 ] && return 0
    fi

    # --- Download changed files to staging dir
    rm -rf "$UPDATE_DIR"
    mkdir -p "$UPDATE_DIR"

    local FAILED=0
    local REMOVED_FILES=""

    if [ "$LOCAL_SHA" = "0" ] || [ -z "$CHANGED_FILES" ]; then
        # No compare available, so download the full repo zip
        local TMPZIP
        TMPZIP="$(mktemp /tmp/deckops_update_XXXXXX.zip)"
        curl -sL --max-time 120 \
            "https://github.com/$GITHUB_USER/$GITHUB_REPO/archive/refs/heads/main.zip" \
            -o "$TMPZIP"

        if [ $? -ne 0 ]; then
            rm -f "$TMPZIP"
            rm -rf "$UPDATE_DIR"
            zenity --error --title="$APP_TITLE" \
                --text="Update download failed.\nContinuing with current version." \
                2>/dev/null
            return 0
        fi

        local TMPDIR_EXTRACT
        TMPDIR_EXTRACT="$(mktemp -d /tmp/deckops_extract_XXXXXX)"
        unzip -qq "$TMPZIP" -d "$TMPDIR_EXTRACT"
        rm -f "$TMPZIP"

        local EXTRACTED
        EXTRACTED=$(find "$TMPDIR_EXTRACT" -maxdepth 1 -mindepth 1 -type d | head -1)
        [ -z "$EXTRACTED" ] && EXTRACTED="$TMPDIR_EXTRACT"

        cp -r "$EXTRACTED"/. "$UPDATE_DIR"/
        rm -rf "$TMPDIR_EXTRACT"
    else
        # Download only changed files
        while IFS= read -r filepath; do
            # Skip protected paths
            case "$filepath" in
                logs/*) continue ;;
                assets/music/background.mp3) continue ;;
            esac

            local DEST_DIR
            DEST_DIR="$UPDATE_DIR/$(dirname "$filepath")"
            mkdir -p "$DEST_DIR"

            local HTTP_CODE
            HTTP_CODE=$(curl -s --max-time 30 -w '%{http_code}' \
                "$GITHUB_RAW/$filepath" \
                -o "$UPDATE_DIR/$filepath")

            if [ "$HTTP_CODE" = "404" ]; then
                # File was deleted or renamed upstream. The compare API lists
                # removed files (and old names of renamed files, via the
                # previous_filename key which the filename grep also matches),
                # and those 404 on raw.githubusercontent. Previously this
                # aborted the whole update, so any commit that deleted or renamed
                # a file blocked incremental updates for good.
                # Skip the download and delete the local copy at apply time.
                rm -f "$UPDATE_DIR/$filepath"
                REMOVED_FILES="${REMOVED_FILES}${filepath}
"
                continue
            elif [ "$HTTP_CODE" != "200" ]; then
                FAILED=1
                break
            fi
        done < <(echo "$CHANGED_FILES")
    fi

    if [ "$FAILED" -ne 0 ]; then
        rm -rf "$UPDATE_DIR"
        zenity --error --title="$APP_TITLE" \
            --text="Update download failed.\nContinuing with current version." \
            2>/dev/null
        return 0
    fi

    # --- Apply staged files
    # Protected paths are never overwritten
    if [ "$LOCAL_SHA" = "0" ] || [ -z "$CHANGED_FILES" ]; then
        # Full update: copy everything except protected paths.
        # Preserve user config with cp + mv (atomic rename) so a power loss can't leave a truncated config
        local SAVED_CONFIG=""
        if [ -f "$INSTALL_DIR/deckops.json" ]; then
            SAVED_CONFIG="$INSTALL_DIR/deckops.json.bak"
            cp "$INSTALL_DIR/deckops.json" "$SAVED_CONFIG"
        fi
        local SAVED_MUSIC=""
        if [ -f "$INSTALL_DIR/assets/music/background.mp3" ]; then
            SAVED_MUSIC="$INSTALL_DIR/assets/music/background.mp3.bak"
            cp "$INSTALL_DIR/assets/music/background.mp3" "$SAVED_MUSIC"
        fi

        # Copy updated files
        cp -r "$UPDATE_DIR"/. "$INSTALL_DIR"/

        # Restore protected files
        if [ -n "$SAVED_CONFIG" ] && [ -f "$SAVED_CONFIG" ]; then
            mv "$SAVED_CONFIG" "$INSTALL_DIR/deckops.json"
        fi
        if [ -n "$SAVED_MUSIC" ] && [ -f "$SAVED_MUSIC" ]; then
            mv "$SAVED_MUSIC" "$INSTALL_DIR/assets/music/background.mp3"
        fi
    else
        # Partial update: copy only changed files
        while IFS= read -r filepath; do
            case "$filepath" in
                logs/*) continue ;;
                assets/music/background.mp3) continue ;;
            esac

            if [ -f "$UPDATE_DIR/$filepath" ]; then
                mkdir -p "$INSTALL_DIR/$(dirname "$filepath")"
                cp "$UPDATE_DIR/$filepath" "$INSTALL_DIR/$filepath"
            fi
        done < <(echo "$CHANGED_FILES")

        # Delete local copies of files removed (or renamed away) upstream.
        # Only paths that the compare API listed and that 404 at HEAD reach
        # this list. Protected paths are never touched.
        if [ -n "$REMOVED_FILES" ]; then
            while IFS= read -r filepath; do
                [ -z "$filepath" ] && continue
                case "$filepath" in
                    logs/*) continue ;;
                    assets/music/background.mp3) continue ;;
                    deckops.json) continue ;;
                esac
                rm -f "$INSTALL_DIR/$filepath"
            done < <(echo "$REMOVED_FILES")
        fi
    fi

    rm -rf "$UPDATE_DIR"

    # Save new version SHA
    echo "$REMOTE_SHA" > "$VERSION_FILE"

    # Make scripts executable
    chmod +x "$INSTALL_DIR/launcher.sh" 2>/dev/null
    chmod +x "$INSTALL_DIR/deckops_uninstall.sh" 2>/dev/null
    chmod +x "$INSTALL_DIR/install.sh" 2>/dev/null

    zenity --info --title="$APP_TITLE" \
        --text="Update complete!${RESET_HINT}" \
        --width=300 \
        2>/dev/null

    return 0
}

# --- Already installed: ask what to do
choice=$(zenity \
    --list \
    --title="$APP_TITLE" \
    --text="$APP_TITLE is already installed.\nWhat would you like to do?" \
    --column="Action" \
    --hide-header \
    "Launch DeckOps" \
    "Uninstall" \
    --width=300 --height=200 \
    2>/dev/null)

[ $? -ne 0 ] && exit 0

case "$choice" in
    "Launch DeckOps")
        # Installs from before the PyQt6 move: rerun the installer in this terminal so
        # the download shows. It keeps deckops.json and the venv, then launches DeckOps itself.
        if ! "$INSTALL_DIR/.venv/bin/python3" -c "import PyQt6.QtWidgets" &>/dev/null \
           && [ ! -f "$INSTALL_DIR/.venv/.qt6_unsupported" ]; then
            zenity --info --title="$APP_TITLE Update" --width=360 \
                --text="DeckOps needs a one-time update (PyQt6, about 100 MB).\n\nIt downloads in the terminal window and can take several minutes.\n\nDo not close the terminal. DeckOps opens when it is done." \
                2>/dev/null
            touch "$LOCKFILE"
            curl -sL "$GITHUB_RAW/install.sh" | bash
            rm -f "$LOCKFILE"
            exit 0
        fi

        # Check for updates before launching
        check_for_updates

        VENV_PYTHON="$INSTALL_DIR/.venv/bin/python3"
        ENTRY_POINT="$INSTALL_DIR/src/main.py"
        if [ -f "$VENV_PYTHON" ] && [ -f "$ENTRY_POINT" ]; then
            setsid nohup "$VENV_PYTHON" "$ENTRY_POINT" > /dev/null 2>&1 &
            disown
            exit 0
        else
            zenity --error --title="$APP_TITLE" \
                --text="$APP_TITLE installation appears incomplete.\nTry reinstalling." \
                2>/dev/null
        fi
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
