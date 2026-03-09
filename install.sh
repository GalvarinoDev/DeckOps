#!/bin/bash
# DeckOps Installer

# ── colours ───────────────────────────────────────────────────────────────────
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

# ── config ────────────────────────────────────────────────────────────────────
GITHUB_USER="GalvarinoDev"
GITHUB_REPO="DeckOps"
INSTALL_DIR="$HOME/DeckOps"
ENTRY_POINT="$INSTALL_DIR/src/main.py"
ICON_PATH="$INSTALL_DIR/assets/images/icon.png"
FONTS_DIR="$INSTALL_DIR/assets/fonts"
DESKTOP_FILE="$HOME/.local/share/applications/deckops.desktop"
DESKTOP_SHORTCUT="$HOME/Desktop/DeckOps.desktop"

FONT_URL="https://raw.githubusercontent.com/googlefonts/science-gothic/main/fonts/variable/ScienceGothic%5BCTRS%2Cslnt%2Cwdth%2Cwght%5D.ttf"
FONT_FILE="ScienceGothic-VF.ttf"

# ── header ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}  ██████╗ ███████╗ ██████╗██╗  ██╗ ██████╗ ██████╗ ███████╗${CLEAR}"
echo -e "${BOLD}  ██╔══██╗██╔════╝██╔════╝██║ ██╔╝██╔═══██╗██╔══██╗██╔════╝${CLEAR}"
echo -e "${BOLD}  ██║  ██║█████╗  ██║     █████╔╝ ██║   ██║██████╔╝███████╗${CLEAR}"
echo -e "${BOLD}  ██║  ██║██╔══╝  ██║     ██╔═██╗ ██║   ██║██╔═══╝ ╚════██║${CLEAR}"
echo -e "${BOLD}  ██████╔╝███████╗╚██████╗██║  ██╗╚██████╔╝██║     ███████║${CLEAR}"
echo -e "${BOLD}  ╚═════╝ ╚══════╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚══════╝${CLEAR}"
echo ""
echo -e "  ${YELLOW}DeckOps — Installer${CLEAR}"
echo ""

# ── step 1: check core dependencies ──────────────────────────────────────────
info "Checking dependencies..."

command -v python3 &>/dev/null || die "Python 3 is not installed."
command -v curl    &>/dev/null || die "curl is not installed."
command -v unzip   &>/dev/null || die "unzip is not installed."

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
success "Python $PYTHON_VER found."

# ── step 2: download latest release (includes pre-releases) ──────────────────
info "Downloading DeckOps..."

TMPZIP="$(mktemp /tmp/deckops_XXXXXX.zip)"
curl -L --progress-bar "https://github.com/$GITHUB_USER/$GITHUB_REPO/archive/refs/heads/main.zip" -o "$TMPZIP" || die "Download failed. Check your internet connection."
success "Download complete."

# ── step 3: extract ───────────────────────────────────────────────────────────
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

# ── step 4: download variable font ───────────────────────────────────────────
info "Downloading fonts..."

mkdir -p "$FONTS_DIR"

FONT_DEST="$FONTS_DIR/$FONT_FILE"
if [ ! -f "$FONT_DEST" ]; then
    curl -sSL "$FONT_URL" -o "$FONT_DEST" \
        && success "Font downloaded." \
        || warn "Could not download font — text may look plain."
else
    success "Font already present."
fi

# ── step 5: check for PyQt5 ──────────────────────────────────────────────────
info "Checking for PyQt5..."

if ! python3 -c "from PyQt5.QtWidgets import QApplication" &>/dev/null 2>&1; then
    info "PyQt5 not found — installing now..."
    sudo apt-get install -y python3-pyqt5 2>/dev/null \
        || pip install PyQt5 --quiet --break-system-packages 2>/dev/null \
        || pip install PyQt5 --quiet 2>/dev/null \
        || die "Failed to install PyQt5. Try manually: sudo apt install python3-pyqt5"
    success "PyQt5 installed."
else
    PYQT5_VER=$(python3 -c "from PyQt5.QtCore import QT_VERSION_STR; print(QT_VERSION_STR)")
    success "PyQt5 (Qt $PYQT5_VER) already installed."
fi

# ── step 6: .desktop entry ────────────────────────────────────────────────────
info "Creating application shortcut..."

mkdir -p "$(dirname "$DESKTOP_FILE")"

cat > "$DESKTOP_FILE" << DEOF
[Desktop Entry]
Name=DeckOps
Comment=DeckOps — Community COD launcher for Steam Deck
Exec=python3 $ENTRY_POINT
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

# ── step 7: add to Steam ──────────────────────────────────────────────────────
info "Adding DeckOps to Steam library..."

IN_GAME_MODE=0
pgrep -x "gamescope" > /dev/null 2>&1 && IN_GAME_MODE=1

add_to_steam() {
    python3 - << PYEOF
import os, struct, time

def find_shortcuts_vdf():
    steam_paths = [
        os.path.expanduser("~/.local/share/Steam"),
        os.path.expanduser("~/.steam/steam"),
        os.path.expanduser("~/.steam/root"),
    ]
    for steam in steam_paths:
        userdata = os.path.join(steam, "userdata")
        if not os.path.exists(userdata):
            continue
        for uid in os.listdir(userdata):
            vdf = os.path.join(userdata, uid, "config", "shortcuts.vdf")
            cfg_dir = os.path.join(userdata, uid, "config")
            if os.path.exists(vdf) or os.path.exists(cfg_dir):
                return vdf
    return None

def string_field(key, val):
    return b'\x01' + key.encode() + b'\x00' + val.encode() + b'\x00'

def int_field(key, val):
    return b'\x02' + key.encode() + b'\x00' + struct.pack('<I', val)

def make_entry(index, name, exe, icon, start_dir):
    e  = b'\x00' + str(index).encode() + b'\x00'
    e += string_field('appname', name)
    e += string_field('exe', exe)
    e += string_field('StartDir', start_dir)
    e += string_field('icon', icon)
    e += string_field('ShortcutPath', '')
    e += string_field('LaunchOptions', '')
    e += int_field('IsHidden', 0)
    e += int_field('AllowDesktopConfig', 1)
    e += int_field('AllowOverlay', 1)
    e += int_field('OpenVR', 0)
    e += int_field('Devkit', 0)
    e += string_field('DevkitGameID', '')
    e += int_field('LastPlayTime', int(time.time()))
    e += b'\x00tags\x00\x08'
    e += b'\x08'
    return e

vdf = find_shortcuts_vdf()
if not vdf:
    print("WARN: shortcuts.vdf not found — add DeckOps to Steam manually.")
    exit(0)

name      = "DeckOps"
exe       = f"python3 {os.path.expanduser('~')}/DeckOps/src/main.py"
icon      = f"{os.path.expanduser('~')}/DeckOps/assets/images/icon.png"
start_dir = f"{os.path.expanduser('~')}/DeckOps"

if os.path.exists(vdf):
    data = open(vdf, 'rb').read()
    if b'DeckOps' in data:
        print("Already in Steam shortcuts.")
        exit(0)
    existing = data[:-2] if data.endswith(b'\x08\x08') else data
    index = existing.count(b'\x00appname\x00')
else:
    os.makedirs(os.path.dirname(vdf), exist_ok=True)
    existing = b'\x00shortcuts\x00'
    index = 0

updated = existing + make_entry(index, name, exe, icon, start_dir) + b'\x08\x08'
open(vdf, 'wb').write(updated)
print(f"Added as entry {index}.")
PYEOF
}

if [ "$IN_GAME_MODE" -eq 1 ]; then
    add_to_steam
    success "Steam shortcut written. Restart Steam to see DeckOps in your library."
else
    echo ""
    warn "Steam needs to be closed to add DeckOps to your library."
    read -r -p "  Is Steam closed? Press Y to add, N to skip: " answer
    case "$answer" in
        [yY]*)
            add_to_steam
            success "Steam shortcut written. Launch Steam and DeckOps will be in your library."
            ;;
        *)
            warn "Skipped. To add manually: Steam → Add a Non-Steam Game → $ENTRY_POINT"
            ;;
    esac
fi

# ── done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}  Installation complete! Welcome to DeckOps.${CLEAR}"
echo ""
echo -e "  ${CYAN}Find DeckOps in your app launcher or Steam library.${CLEAR}"
echo ""
read -r -p "  Press Enter to close..."
