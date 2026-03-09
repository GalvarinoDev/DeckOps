#!/bin/bash
# deckops_uninstall.sh
# Fully removes everything DeckOps has ever touched:
#   - Restores original game .exe files from .bak backups
#   - Removes Plutonium folder from EVERY Wine prefix (including non-Steam prefix)
#   - Removes iw4x / cod4x downloaded files from game directories
#   - Removes DeckOps config, cache, and install directory
#   - Removes desktop shortcuts
#   - Kills any leftover audio processes
#
# Safe to run multiple times. Does NOT delete your Steam games.

set -e

RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
CLEAR='\033[0m'

info()    { printf "${CYAN}${BOLD}[DeckOps]${CLEAR} %s\n" "$1"; }
success() { printf "${GREEN}${BOLD}[  OK  ]${CLEAR} %s\n" "$1"; }
warn()    { printf "${YELLOW}${BOLD}[ WARN ]${CLEAR} %s\n" "$1"; }
skip()    { printf "         %s\n" "$1"; }

echo ""
echo -e "${BOLD}  DeckOps — Full Uninstaller${CLEAR}"
echo ""
warn "This will restore all original game exe files and remove ALL DeckOps"
warn "and Plutonium data from your Wine prefixes."
echo ""
read -r -p "  Continue? [y/N] " answer
case "$answer" in
    [yY]*) ;;
    *) echo "Aborted."; exit 0 ;;
esac
echo ""


# ── locate Steam ──────────────────────────────────────────────────────────────

STEAM_ROOTS=(
    "$HOME/.local/share/Steam"
    "$HOME/.steam/steam"
    "$HOME/.steam/root"
    "$HOME/.steam/debian-installation"
    "/run/media/mmcblk0p1/.local/share/Steam"   # SD card
    "/home/deck/.local/share/Steam"              # Steam Deck default
)

STEAM_ROOT=""
for r in "${STEAM_ROOTS[@]}"; do
    if [ -d "$r/steamapps" ]; then
        STEAM_ROOT="$r"
        break
    fi
done

if [ -z "$STEAM_ROOT" ]; then
    warn "Steam root not found — skipping game restore steps."
else
    success "Steam found at $STEAM_ROOT"
fi


# ── helper: find install dir from appid ───────────────────────────────────────

find_install_dir() {
    local appid="$1"
    local acf="$STEAM_ROOT/steamapps/appmanifest_${appid}.acf"
    if [ ! -f "$acf" ]; then
        local vdf="$STEAM_ROOT/steamapps/libraryfolders.vdf"
        if [ -f "$vdf" ]; then
            while IFS= read -r line; do
                local path
                path=$(echo "$line" | grep -oP '(?<="path"\s{0,4}"\s{0,4})[^"]+' 2>/dev/null || true)
                if [ -n "$path" ] && [ -f "$path/steamapps/appmanifest_${appid}.acf" ]; then
                    acf="$path/steamapps/appmanifest_${appid}.acf"
                    break
                fi
            done < "$vdf"
        fi
    fi
    if [ -f "$acf" ]; then
        local install_name
        install_name=$(grep -oP '(?<="installdir"\s{0,4}"\s{0,4})[^"]+' "$acf" 2>/dev/null || true)
        if [ -n "$install_name" ]; then
            local acf_dir
            acf_dir=$(dirname "$acf")
            echo "$acf_dir/common/$install_name"
            return
        fi
    fi
    echo ""
}


# ── helper: restore a single exe from .bak ───────────────────────────────────

restore_exe() {
    local install_dir="$1"
    local exe_name="$2"
    local exe_path="$install_dir/$exe_name"
    local bak_path="$exe_path.bak"
    local old_path="$exe_path.old"

    if [ -f "$bak_path" ]; then
        mv "$bak_path" "$exe_path"
        success "Restored $exe_name (from .bak)"
    elif [ -f "$old_path" ]; then
        mv "$old_path" "$exe_path"
        success "Restored $exe_name (from .old)"
    elif [ -f "$exe_path" ]; then
        skip "$exe_name — no backup found (may already be original)"
    else
        skip "$exe_name — not found"
    fi
}


# ── restore game executables ──────────────────────────────────────────────────

info "Restoring original game executables..."

if [ -n "$STEAM_ROOT" ]; then

    declare -A GAME_EXES=(
        [7940]="iw3mp.exe"
        [10190]="iw4mp.exe"
        [42690]="iw5mp.exe"
    )
    declare -A GAME_EXES_MULTI=(
        [10090]="CoDWaW.exe CoDWaWmp.exe"
        [42700]="BlackOps.exe BlackOpsMP.exe"
        [202990]="t6mp.exe t6zm.exe"
    )

    for appid in "${!GAME_EXES[@]}"; do
        dir=$(find_install_dir "$appid")
        [ -n "$dir" ] && restore_exe "$dir" "${GAME_EXES[$appid]}"
    done

    for appid in "${!GAME_EXES_MULTI[@]}"; do
        dir=$(find_install_dir "$appid")
        if [ -n "$dir" ]; then
            for exe in ${GAME_EXES_MULTI[$appid]}; do
                restore_exe "$dir" "$exe"
            done
        fi
    done

fi
echo ""


# ── remove Plutonium from ALL Wine prefixes ───────────────────────────────────
# Scans every folder under compatdata — covers game prefixes AND the dedicated
# non-Steam Plutonium prefix (which has a random auto-generated appid).

info "Scanning all Wine prefixes for Plutonium..."

if [ -n "$STEAM_ROOT" ]; then
    COMPATDATA="$STEAM_ROOT/steamapps/compatdata"
    if [ -d "$COMPATDATA" ]; then
        found_any=0
        for prefix_dir in "$COMPATDATA"/*/; do
            plut_dir="$prefix_dir/pfx/drive_c/users/steamuser/AppData/Local/Plutonium"
            if [ -d "$plut_dir" ]; then
                prefix_id=$(basename "$prefix_dir")
                rm -rf "$plut_dir"
                success "Removed Plutonium from prefix $prefix_id"
                found_any=1
            fi
        done
        [ "$found_any" -eq 0 ] && skip "No Plutonium folders found in any prefix"
    else
        skip "compatdata directory not found"
    fi

    # Remove DeckOps metadata markers from game install dirs
    for appid in 42690 10090 42700 202990; do
        game_dir=$(find_install_dir "$appid")
        if [ -n "$game_dir" ] && [ -f "$game_dir/deckops_plutonium.json" ]; then
            rm -f "$game_dir/deckops_plutonium.json"
            success "Removed DeckOps metadata for appid $appid"
        fi
    done
fi
echo ""


# ── remove iw4x / cod4x files ────────────────────────────────────────────────

info "Removing iw4x / cod4x client files..."

if [ -n "$STEAM_ROOT" ]; then
    # iw4x — MW2 (appid 10190)
    mw2_dir=$(find_install_dir 10190)
    if [ -n "$mw2_dir" ]; then
        for f in "iw4x.exe" "iw4x_client.dll" "iw4x_loader.exe" "iw4x.dll"; do
            [ -f "$mw2_dir/$f" ] && rm -f "$mw2_dir/$f" && success "Removed $f" || skip "$f not found"
        done
        for d in "iw4x" "iw4x-updoot"; do
            [ -d "$mw2_dir/$d" ] && rm -rf "$mw2_dir/$d" && success "Removed $d/" || skip "$d/ not found"
        done
    fi

    # cod4x — CoD4 (appid 7940)
    cod4_dir=$(find_install_dir 7940)
    if [ -n "$cod4_dir" ]; then
        for f in "cod4x_021.dll" "cod4x_loader.exe" "cod4x.exe"; do
            [ -f "$cod4_dir/$f" ] && rm -f "$cod4_dir/$f" && success "Removed $f" || skip "$f not found"
        done
    fi
fi
echo ""


# ── kill leftover audio ───────────────────────────────────────────────────────

info "Stopping any leftover DeckOps audio..."
if pkill -f "mpv" 2>/dev/null; then
    success "mpv stopped"
else
    skip "No DeckOps mpv process found"
fi
echo ""


# ── remove DeckOps install and config ────────────────────────────────────────

info "Removing DeckOps install directory and config..."

DECKOPS_DIRS=(
    "$HOME/DeckOps"
    "$HOME/.config/deckops"
    "$HOME/.local/share/deckops"
)

for d in "${DECKOPS_DIRS[@]}"; do
    if [ -d "$d" ]; then
        rm -rf "$d"
        success "Removed $d"
    else
        skip "$d — not found"
    fi
done
echo ""


# ── remove desktop shortcuts ─────────────────────────────────────────────────

info "Removing desktop shortcuts..."

SHORTCUTS=(
    "$HOME/.local/share/applications/deckops.desktop"
    "$HOME/.local/share/applications/dev.galvarino.deckops.desktop"
    "$HOME/Desktop/DeckOps.desktop"
    "$HOME/Desktop/deckops.desktop"
)

for s in "${SHORTCUTS[@]}"; do
    [ -f "$s" ] && rm -f "$s" && success "Removed $s" || skip "$(basename "$s") not found"
done

command -v update-desktop-database &>/dev/null && \
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null && \
    success "Desktop database refreshed" || true
echo ""


# ── done ─────────────────────────────────────────────────────────────────────

echo -e "${GREEN}${BOLD}  DeckOps fully uninstalled.${CLEAR}"
echo ""
echo "  Your Steam games are untouched. All original .exe files restored."
echo "  All Plutonium data removed from Wine prefixes."
echo ""
read -r -p "  Press Enter to close..." _
