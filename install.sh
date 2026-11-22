#!/bin/bash
# DeckOps Installer

# --- colours
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
CLEAR='\033[0m'

info()    { printf "${CYAN}${BOLD}[DeckOps]${CLEAR} %s\n" "$1"; }
success() { printf "${GREEN}${BOLD}[  OK  ]${CLEAR} %s\n" "$1"; }
warn()    { printf "${YELLOW}${BOLD}[ WARN ]${CLEAR} %s\n" "$1"; }
die()     {
    printf "${RED}${BOLD}[ERROR ]${CLEAR} %s\n" "$1"
    echo ""
    read -r -p "  Press Enter to close..."
    exit 1
}

# --- config
# Normal installs source deckops_identity.sh. Curl-piped installs don't have it on disk yet, so
# the fallback values below must match deckops_identity.sh and change together with it.
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
    VENV_DIR="$INSTALL_DIR/.venv"
    VENV_PYTHON="$VENV_DIR/bin/python3"
    ENTRY_POINT="$INSTALL_DIR/src/main.py"
    ICON_PATH="$INSTALL_DIR/assets/images/icon.png"
    MUSIC_DIR="$INSTALL_DIR/assets/music"
    APP_TITLE="DeckOps"
    DESKTOP_COMMENT="DeckOps — Call of Duty on SteamOS"
    BUILD_FALLBACK="stable"
    DESKTOP_FILE="$HOME/.local/share/applications/deckops.desktop"
    DESKTOP_SHORTCUT="$HOME/Desktop/DeckOps.desktop"
fi

MUSIC_URL="https://archive.org/download/adrenaline-klickaud/Adrenaline_KLICKAUD.mp3"
MUSIC_FILE="background.mp3"

# --- header
echo ""
echo -e "${BOLD}  ██████╗ ███████╗ ██████╗██╗  ██╗ ██████╗ ██████╗ ███████╗${CLEAR}"
echo -e "${BOLD}  ██╔══██╗██╔════╝██╔════╝██║ ██╔╝██╔═══██╗██╔══██╗██╔════╝${CLEAR}"
echo -e "${BOLD}  ██║  ██║█████╗  ██║     █████╔╝ ██║   ██║██████╔╝███████╗${CLEAR}"
echo -e "${BOLD}  ██║  ██║██╔══╝  ██║     ██╔═██╗ ██║   ██║██╔═══╝ ╚════██║${CLEAR}"
echo -e "${BOLD}  ██████╔╝███████╗╚██████╗██║  ██╗╚██████╔╝██║     ███████║${CLEAR}"
echo -e "${BOLD}  ╚═════╝ ╚══════╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚══════╝${CLEAR}"
echo ""
echo -e "  ${YELLOW}${APP_TITLE:-DeckOps} — Installer${CLEAR}"
echo ""

# --- step 1: check core dependencies
info "Checking dependencies..."

command -v python3 &>/dev/null || die "Python 3 is not installed."
command -v curl    &>/dev/null || die "curl is not installed."
command -v unzip   &>/dev/null || die "unzip is not installed."

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
success "Python $PYTHON_VER found."

# --- step 2: download latest release
info "Downloading DeckOps..."

TMPZIP="$(mktemp /tmp/deckops_XXXXXX.zip)"
curl -L --progress-bar "https://github.com/$GITHUB_USER/$GITHUB_REPO/archive/refs/heads/main.zip" -o "$TMPZIP" \
    || die "Download failed. Check your internet connection."
success "Download complete."

# --- step 3: extract
info "Installing to $INSTALL_DIR..."

TMPDIR_EXTRACT="$(mktemp -d /tmp/deckops_extract_XXXXXX)"
unzip -qq "$TMPZIP" -d "$TMPDIR_EXTRACT" || die "Failed to extract archive."
rm "$TMPZIP"

EXTRACTED=$(find "$TMPDIR_EXTRACT" -maxdepth 1 -mindepth 1 -type d | head -1)
[ -z "$EXTRACTED" ] && EXTRACTED="$TMPDIR_EXTRACT"

mkdir -p "$INSTALL_DIR"
cp -r "$EXTRACTED"/. "$INSTALL_DIR"/
rm -rf "$TMPDIR_EXTRACT"

chmod +x "$ENTRY_POINT" 2>/dev/null || true
success "DeckOps installed to $INSTALL_DIR"

# --- step 3b: write build info
# Short commit hash + date, read by the Settings screen's About section.
# Uses the downloaded archive's HEAD, not a local git repo.
BUILD_DATE=$(date '+%b %d, %Y')
BUILD_HASH="${BUILD_FALLBACK:-stable}"
if command -v git &>/dev/null && [ -d "$INSTALL_DIR/.git" ]; then
    BUILD_HASH=$(cd "$INSTALL_DIR" && git rev-parse --short HEAD 2>/dev/null || echo "${BUILD_FALLBACK:-stable}")
fi
echo "$BUILD_HASH ($BUILD_DATE)" > "$INSTALL_DIR/BUILD"
success "Build info written: $BUILD_HASH ($BUILD_DATE)"

# --- step 4: download background music
info "Downloading background music..."

mkdir -p "$MUSIC_DIR"

if [ ! -f "$MUSIC_DIR/$MUSIC_FILE" ]; then
    curl -sSL "$MUSIC_URL" -o "$MUSIC_DIR/$MUSIC_FILE" \
        && success "Background music downloaded." \
        || warn "Could not download background music — app will run without it."
else
    success "Background music already present."
fi

# --- step 5: set up Python venv + install packages
info "Setting up Python environment..."

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR" || die "Failed to create Python virtual environment."
    success "Virtual environment created."
else
    success "Virtual environment already exists."
fi

QT6_OK=0
if "$VENV_PYTHON" -c "from PyQt6.QtWidgets import QApplication" &>/dev/null; then
    QT6_OK=1
    success "PyQt6 (Qt $("$VENV_PYTHON" -c "from PyQt6.QtCore import QT_VERSION_STR; print(QT_VERSION_STR)")) already installed."
else
    info "Installing PyQt6 (this will take about a minute)..."
    if "$VENV_DIR/bin/pip" install --quiet --disable-pip-version-check PyQt6; then
        # A wheel that installs but can't load its platform plugin here would crash the app
        if ("$VENV_PYTHON" -c "from PyQt6.QtWidgets import QApplication; QApplication([])"; exit $?) &>/dev/null; then
            QT6_OK=1
            success "PyQt6 installed."
        else
            "$VENV_DIR/bin/pip" uninstall -y -q PyQt6 PyQt6-Qt6 PyQt6-sip &>/dev/null
            touch "$VENV_DIR/.qt6_unsupported"
            warn "PyQt6 can't open a window on this system, using PyQt5 instead."
        fi
    else
        warn "PyQt6 install failed, using PyQt5 instead."
    fi
fi

if [ "$QT6_OK" = 0 ] && ! "$VENV_PYTHON" -c "from PyQt5.QtWidgets import QApplication" &>/dev/null; then
    info "Installing PyQt5..."
    "$VENV_DIR/bin/pip" install --quiet --disable-pip-version-check PyQt5 \
        || die "Failed to install PyQt6 or PyQt5. Check your internet connection and try again."
    success "PyQt5 installed."
fi

# --- step 6: .desktop entry
info "Creating application shortcut..."

mkdir -p "$(dirname "$DESKTOP_FILE")"

cat > "$DESKTOP_FILE" << DEOF
[Desktop Entry]
Name=${APP_TITLE:-DeckOps}
Comment=${DESKTOP_COMMENT:-DeckOps — Call of Duty on SteamOS}
Exec=$VENV_PYTHON $ENTRY_POINT
Icon=$ICON_PATH
Terminal=false
Type=Application
Categories=Game;
StartupNotify=true
DEOF

chmod +x "$DESKTOP_FILE"
success "App launcher shortcut created."

if [ -d "$HOME/Desktop" ]; then
    cp "$DESKTOP_FILE" "$DESKTOP_SHORTCUT"
    chmod +x "$DESKTOP_SHORTCUT"
    success "Desktop shortcut created."
fi

# --- step 7: sweep stale plut_lan.sh sidecars
# Installs from before Pass 1 wrote <gametag>plut_lan.sh into game install dirs (OLED
# offline-mode plumbing). Pass 1 stopped creating them but left existing files on disk.
# This removes them from every known Steam library: internal, libraryfolders.vdf entries
# and SD card mounts.
info "Sweeping stale plut_lan.sh sidecars..."

STEAM_ROOT_FOR_SWEEP=""
for r in "$HOME/.local/share/Steam" "$HOME/.steam/steam" "$HOME/.steam/root"; do
    if [ -d "$r/steamapps" ]; then
        STEAM_ROOT_FOR_SWEEP="$r"
        break
    fi
done

LAN_SWEEP_DIRS=()
[ -n "$STEAM_ROOT_FOR_SWEEP" ] && LAN_SWEEP_DIRS+=("$STEAM_ROOT_FOR_SWEEP/steamapps/common")

LF_VDF_SWEEP="$STEAM_ROOT_FOR_SWEEP/steamapps/libraryfolders.vdf"
if [ -f "$LF_VDF_SWEEP" ]; then
    while IFS= read -r libpath; do
        [ -d "$libpath/steamapps/common" ] && LAN_SWEEP_DIRS+=("$libpath/steamapps/common")
        [ -d "$libpath/SteamLibrary/steamapps/common" ] && LAN_SWEEP_DIRS+=("$libpath/SteamLibrary/steamapps/common")
    done < <(sed -n 's/.*"path"[[:space:]]*"\([^"]*\)".*/\1/p' "$LF_VDF_SWEEP")
fi

for mount in /run/media/deck/*/steamapps/common /run/media/deck/*/SteamLibrary/steamapps/common; do
    [ -d "$mount" ] && LAN_SWEEP_DIRS+=("$mount")
done

lan_removed=0
for common_dir in "${LAN_SWEEP_DIRS[@]}"; do
    while IFS= read -r -d '' sidecar; do
        if rm -f "$sidecar" 2>/dev/null; then
            info "  Removed: $sidecar"
            lan_removed=$((lan_removed + 1))
        fi
    done < <(find "$common_dir" -maxdepth 2 -name "*plut_lan.sh" -print0 2>/dev/null)
done

if [ "$lan_removed" -gt 0 ]; then
    success "Removed $lan_removed stale plut_lan.sh sidecar(s)."
else
    success "No stale plut_lan.sh sidecars found."
fi

# --- step 8: write initial version SHA
# Without it the first launch would re-download everything.
info "Recording current version..."
INITIAL_SHA=$(curl -sf --max-time 10 \
    "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/commits/main" \
    | grep -m1 '"sha"' | cut -d'"' -f4)
if [ -n "$INITIAL_SHA" ]; then
    echo "$INITIAL_SHA" > "$INSTALL_DIR/VERSION"
    success "Version recorded."
else
    warn "Could not fetch version SHA — will be set on first update."
fi

# --- step 9: done
echo ""
echo -e "${GREEN}${BOLD}  Download Complete! Welcome to DeckOps.${CLEAR}"
echo ""
echo -e "  ${CYAN}Launching DeckOps...${CLEAR}"
echo ""

nohup "$VENV_PYTHON" "$ENTRY_POINT" > /dev/null 2>&1 &
disown
exit 0
