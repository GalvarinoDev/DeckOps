#!/bin/bash
# deckops_uninstall.sh

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

# ── Branch identity ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/deckops_identity.sh" ]; then
    source "$SCRIPT_DIR/deckops_identity.sh"
elif [ -f "$HOME/DeckOps-Nightly/deckops_identity.sh" ]; then
    source "$HOME/DeckOps-Nightly/deckops_identity.sh"
elif [ -f "$HOME/DeckOps/deckops_identity.sh" ]; then
    source "$HOME/DeckOps/deckops_identity.sh"
else
    INSTALL_DIR_NAME="DeckOps-Nightly"
    INSTALL_DIR="$HOME/DeckOps-Nightly"
    VENV_PYTHON="$INSTALL_DIR/.venv/bin/python3"
    APP_TITLE="DeckOps Nightly"
    XDG_ID="deckops-nightly"
    ENTRY_POINT="$INSTALL_DIR/src/main.py"
fi

echo ""
echo -e "${BOLD}  $APP_TITLE -- Full Uninstaller${CLEAR}"
echo ""

zenity --question \
    --title="$APP_TITLE Uninstaller" \
    --text="This will clear all DeckOps launch options, remove client files, and remove ALL DeckOps and Plutonium data from your Wine prefixes.\n\nContinue?" \
    --ok-label="Cancel" \
    --cancel-label="Yes, Uninstall" 2>/dev/null

if [ $? -eq 0 ]; then
    zenity --info --title="$APP_TITLE" --text="Uninstall cancelled." 2>/dev/null
    exit 0
fi

echo ""

info "Closing Steam..."

# Use Steam's own shutdown command for a clean exit. This ensures Steam
# flushes config files and syncs cloud saves before exiting.
if pgrep -x "steam" > /dev/null 2>&1 || pgrep -f "steam.sh" > /dev/null 2>&1; then
    steam -shutdown 2>/dev/null

    # Wait for Steam to finish closing
    deadline=$((SECONDS + 120))
    while pgrep -x "steam" > /dev/null 2>&1 || pgrep -f "steam.sh" > /dev/null 2>&1; do
        if [ $SECONDS -ge $deadline ]; then
            warn "Steam did not close within 120 seconds."
            warn "Please close Steam manually and re-run the uninstaller."
            exit 1
        fi
        sleep 1
    done
    sleep 3
    sync
    success "Steam closed."
else
    skip "Steam was not running."
fi

echo ""

STEAM_ROOTS=(
    "$HOME/.local/share/Steam"
    "$HOME/.steam/steam"
    "$HOME/.steam/root"
    "$HOME/.steam/debian-installation"
    "/run/media/mmcblk0p1/.local/share/Steam"
    "/home/deck/.local/share/Steam"
)

STEAM_ROOT=""
for r in "${STEAM_ROOTS[@]}"; do
    if [ -d "$r/steamapps" ]; then
        STEAM_ROOT="$r"
        break
    fi
done

if [ -z "$STEAM_ROOT" ]; then
    warn "Steam root not found -- skipping game restore steps."
else
    success "Steam found at $STEAM_ROOT"
fi

find_install_dir() {
    local appid="$1"
    local acf=""

    # Build list of all steamapps dirs to search
    local search_dirs=()
    [ -n "$STEAM_ROOT" ] && search_dirs+=("$STEAM_ROOT/steamapps")

    # Parse libraryfolders.vdf for additional library paths
    local vdf="$STEAM_ROOT/steamapps/libraryfolders.vdf"
    if [ -f "$vdf" ]; then
        while IFS= read -r line; do
            local libpath
            libpath=$(echo "$line" | sed -n 's/.*"path"[[:space:]]*"\([^"]*\)".*/\1/p')
            if [ -n "$libpath" ]; then
                search_dirs+=("$libpath/steamapps")
                search_dirs+=("$libpath/SteamLibrary/steamapps")
            fi
        done < "$vdf"
    fi

    # Brute-force SD card mount points
    for mount in /run/media/deck/*/SteamLibrary/steamapps /run/media/deck/*/steamapps; do
        [ -d "$mount" ] && search_dirs+=("$mount")
    done

    # Search all dirs for the app manifest
    for dir in "${search_dirs[@]}"; do
        local candidate="$dir/appmanifest_${appid}.acf"
        if [ -f "$candidate" ]; then
            acf="$candidate"
            break
        fi
    done

    if [ -f "$acf" ]; then
        local install_name
        install_name=$(sed -n 's/.*"installdir"[[:space:]]*"\([^"]*\)".*/\1/p' "$acf")
        if [ -n "$install_name" ]; then
            echo "$(dirname "$acf")/common/$install_name"
            return
        fi
    fi
    echo ""
}

restore_exe() {
    local install_dir="$1"
    local exe_name="$2"
    local exe_path="$install_dir/$exe_name"
    local bak_path="$exe_path.bak"
    local old_path="$exe_path.old"

    if [ -f "$bak_path" ]; then
        mv "$bak_path" "$exe_path" && success "Restored $exe_name (from .bak)" || warn "Failed to restore $exe_name"
    elif [ -f "$old_path" ]; then
        mv "$old_path" "$exe_path" && success "Restored $exe_name (from .old)" || warn "Failed to restore $exe_name"
    elif [ -f "$exe_path" ]; then
        skip "$exe_name -- no backup found (may already be original)"
    else
        skip "$exe_name -- not found"
    fi
}

info "Restoring original game executables..."

if [ -n "$STEAM_ROOT" ]; then
    # iw3sp and iw4x now use the rename scheme — restore from .bak alongside Plutonium games.
    declare -A GAME_EXES=(
        [7940]="iw3sp.exe"
        [10190]="iw4mp.exe"
        [42690]="iw5mp.exe"
        [42750]="iw5mp_server.exe"
        [202970]="t6sp.exe"
    )
    declare -A GAME_EXES_MULTI=(
        [10090]="CoDWaW.exe CoDWaWmp.exe"
        [42700]="BlackOps.exe BlackOpsMP.exe"
        [202990]="t6mp.exe t6zm.exe"
        [209160]="iw6sp64_ship.exe iw6mp64_ship.exe"
        [209650]="s1_sp64_ship.exe s1_mp64_ship.exe"
    )

    for appid in "${!GAME_EXES[@]}"; do
        dir=$(find_install_dir "$appid") || true
        if [ -n "$dir" ]; then
            for exe in ${GAME_EXES[$appid]}; do
                restore_exe "$dir" "$exe"
            done
        fi
    done

    for appid in "${!GAME_EXES_MULTI[@]}"; do
        dir=$(find_install_dir "$appid") || true
        if [ -n "$dir" ]; then
            for exe in ${GAME_EXES_MULTI[$appid]}; do
                restore_exe "$dir" "$exe"
            done
        fi
    done
fi
echo ""

info "Restoring non-Steam (My Own) game executables..."

# Scan shortcuts.vdf for games added via the My Own flow. These were
# detected by exe name and may have had their exes replaced with wrapper
# scripts. We restore from .bak the same way we do for Steam games.
python3 - << 'PYEOF'
import os, re

STEAM_DIR    = os.path.expanduser("~/.local/share/Steam")
USERDATA_DIR = os.path.join(STEAM_DIR, "userdata")

# Same exe list as detect_shortcuts.py EXE_TO_KEYS
KNOWN_EXES = [
    "iw3mp.exe", "iw3sp.exe", "iw4mp.exe", "iw4sp.exe",
    "iw5mp.exe", "iw5sp.exe", "CoDWaW.exe", "CoDWaWmp.exe",
    "BlackOps.exe", "BlackOpsMP.exe", "t6zm.exe", "t6mp.exe", "t6sp.exe",
    # Mod client exes (own shortcuts point at these, not original game exes)
    "iw4x.exe", "iw3sp_mod.exe",
    # AlterWare mod client exes (own shortcuts point at these)
    "iw6-mod.exe", "s1-mod.exe",
    # LCD own Plutonium wrapper exes (written by plutonium.py, not original game files)
    "t4plutsp.exe", "t4plutmp.exe", "t5plutsp.exe", "t5plutmp.exe",
    "t6plutmp.exe", "t6plutzm.exe", "iw5plutmp.exe",
]

def parse_shortcuts(path):
    """Pull exe and start_dir from shortcuts.vdf entries."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        return []
    results = []
    for m in re.finditer(b'\x01(?:exe|Exe)\x00([^\x00]+)\x00', data):
        exe = m.group(1).decode("utf-8", errors="replace").strip('"')
        results.append(exe)
    return results

if not os.path.isdir(USERDATA_DIR):
    print("  No userdata found, skipping.")
    exit(0)

restored = set()
for uid in os.listdir(USERDATA_DIR):
    if not uid.isdigit() or int(uid) < 10000:
        continue
    vdf_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
    for exe_path in parse_shortcuts(vdf_path):
        exe_name = os.path.basename(exe_path)
        # Check both exact case and lowercase since detect_shortcuts matches lowercase
        if exe_name not in KNOWN_EXES and exe_name.lower() not in [e.lower() for e in KNOWN_EXES]:
            continue
        if exe_path in restored:
            continue
        bak_path = exe_path + ".bak"
        if os.path.exists(bak_path):
            try:
                os.rename(bak_path, exe_path)
                print(f"  Restored {exe_name} (from .bak)")
                restored.add(exe_path)
            except Exception as ex:
                print(f"  Failed to restore {exe_name}: {ex}")
        else:
            # Also check in the start_dir for the exe
            install_dir = os.path.dirname(exe_path)
            for known in KNOWN_EXES:
                candidate = os.path.join(install_dir, known)
                candidate_bak = candidate + ".bak"
                if candidate_bak not in restored and os.path.exists(candidate_bak):
                    try:
                        if os.path.exists(candidate):
                            os.remove(candidate)
                        os.rename(candidate_bak, candidate)
                        print(f"  Restored {known} (from .bak)")
                        restored.add(candidate_bak)
                    except Exception as ex:
                        print(f"  Failed to restore {known}: {ex}")

if not restored:
    print("  No non-Steam game backups found.")
PYEOF
echo ""

info "Backing up player save data before cleanup..."

zenity --question \
    --title="$APP_TITLE Uninstaller" \
    --text="Would you like to back up your save data before uninstalling?\n\nThis preserves player configs, stats, and custom classes\nso they can be restored if you reinstall later." \
    --ok-label="Yes, Back Up" \
    --cancel-label="No, Skip" 2>/dev/null

if [ $? -ne 0 ]; then
    skip "Save backup skipped by user."
else

DECKOPS_SRC="$INSTALL_DIR/src"
DECKOPS_VENV="$VENV_PYTHON"

if [ -f "$DECKOPS_SRC/save_backup.py" ]; then
    # Prefer the venv Python (has PyQt5, all deps) but fall back to system
    if [ -x "$DECKOPS_VENV" ]; then
        _PYBIN="$DECKOPS_VENV"
    else
        _PYBIN="python3"
    fi

    cd "$DECKOPS_SRC" && "$_PYBIN" save_backup.py backup "$STEAM_ROOT" 2>&1 | while IFS= read -r line; do
        echo "         $line"
    done
    _backup_exit=${PIPESTATUS[0]}

    if [ "$_backup_exit" -eq 0 ]; then
        success "Save backup complete."
    else
        warn "Save backup had errors (saves may be incomplete)."
    fi
else
    skip "save_backup.py not found — skipping save backup."
fi

fi
echo ""

# ── (existing code continues below: info "Removing iw4x / cod4x client files...") ──

info "Removing iw4x / cod4x client files..."

if [ -n "$STEAM_ROOT" ]; then
    mw2_dir=$(find_install_dir 10190) || true
    if [ -n "$mw2_dir" ]; then
        for f in "iw4x.dll" "iw4x.exe"; do
            [ -f "$mw2_dir/$f" ] && rm -f "$mw2_dir/$f" && success "Removed $f" || skip "$f not found"
        done
        for d in "iw4x" "iw4x-updoot"; do
            [ -d "$mw2_dir/$d" ] && rm -rf "$mw2_dir/$d" && success "Removed $d/" || skip "$d/ not found"
        done
    fi

    cod4_dir=$(find_install_dir 7940) || true
    if [ -n "$cod4_dir" ]; then
        for f in "cod4x_021.dll" "cod4x_loader.exe" "cod4x.exe" "deckops_cod4x.json" "servercache.dat"; do
            [ -f "$cod4_dir/$f" ] && rm -f "$cod4_dir/$f" && success "Removed $f" || skip "$f not found"
        done
    fi

    # Remove CoD4 user profile/config directory from the Wine prefix
    info "Removing CoD4 Wine prefix user data..."
    COD4_APPDATA="$STEAM_ROOT/steamapps/compatdata/7940/pfx/drive_c/users/steamuser/AppData/Local/CallofDuty4MW"
    if [ -d "$COD4_APPDATA" ]; then
        rm -rf "$COD4_APPDATA" && success "Removed CoD4 Wine prefix AppData" || warn "Failed to remove CoD4 Wine prefix AppData"
    else
        skip "CoD4 Wine prefix AppData not found"
    fi

    # Remove CoD4x ProgramData staging area (setup.exe + GitHub fallback)
    COD4_PROGDATA="$STEAM_ROOT/steamapps/compatdata/7940/pfx/drive_c/ProgramData/CallofDuty4MW"
    if [ -d "$COD4_PROGDATA" ]; then
        rm -rf "$COD4_PROGDATA" && success "Removed CoD4 Wine prefix ProgramData" || warn "Failed to remove CoD4 Wine prefix ProgramData"
    else
        skip "CoD4 Wine prefix ProgramData not found"
    fi
fi
echo ""

info "Removing IW3SP-MOD files from CoD4 folder..."

if [ -n "$STEAM_ROOT" ]; then
    cod4_dir=$(find_install_dir 7940) || true
    if [ -n "$cod4_dir" ]; then
        for f in "iw3sp_mod.exe" "iw3sp_mod.dll" "deckops_iw3sp.json"; do
            [ -f "$cod4_dir/$f" ] && rm -f "$cod4_dir/$f" && success "Removed $f" || skip "$f not found"
        done
        [ -d "$cod4_dir/iw3sp_mod" ] && rm -rf "$cod4_dir/iw3sp_mod" && success "Removed iw3sp_mod/" || skip "iw3sp_mod/ not found"
    else
        skip "CoD4 install directory not found"
    fi
fi
echo ""

info "Removing Rattpak's T6SP-MOD files from Black Ops II folder..."

if [ -n "$STEAM_ROOT" ]; then
    bo2sp_dir=$(find_install_dir 202970) || true
    if [ -n "$bo2sp_dir" ]; then
        for f in "t6sp-mod.dll" "deckops_t6sp_mod.json"; do
            [ -f "$bo2sp_dir/$f" ] && rm -f "$bo2sp_dir/$f" && success "Removed $f" || skip "$f not found"
        done
    else
        skip "Black Ops II SP install directory not found"
    fi
fi
echo ""

info "Removing CleanOps files from Black Ops III folder..."

if [ -n "$STEAM_ROOT" ]; then
    bo3_dir=$(find_install_dir 311210) || true
    if [ -n "$bo3_dir" ]; then
        for f in "d3d11.dll" "deckops_cleanops.json"; do
            [ -f "$bo3_dir/$f" ] && rm -f "$bo3_dir/$f" && success "Removed $f" || skip "$f not found"
        done
    else
        skip "Black Ops III install directory not found"
    fi
fi
echo ""

info "Removing T7X (DeckOps-T7X sibling directory)..."

if [ -n "$STEAM_ROOT" ]; then
    bo3_dir=$(find_install_dir 311210) || true
    if [ -n "$bo3_dir" ]; then
        t7x_sibling="$(dirname "$bo3_dir")/DeckOps-T7X"
        if [ -d "$t7x_sibling" ]; then
            rm -rf "$t7x_sibling" && success "Removed DeckOps-T7X directory" || warn "Could not remove DeckOps-T7X"
        else
            skip "DeckOps-T7X directory not found"
        fi
        # Clean up legacy T7X files from stock BO3 dir (pre-sibling installs)
        for f in "t7x.exe" "deckops_t7x.json"; do
            [ -f "$bo3_dir/$f" ] && rm -f "$bo3_dir/$f" && success "Removed legacy $f"
        done
        [ -d "$bo3_dir/t7x" ] && rm -rf "$bo3_dir/t7x" && success "Removed legacy t7x/ directory"
    else
        skip "Black Ops III install directory not found"
    fi
fi
echo ""

info "Removing AlterWare files from Ghosts and Advanced Warfare folders..."

if [ -n "$STEAM_ROOT" ]; then
    # Ghosts (appid 209160 covers both SP and MP install dir)
    ghosts_dir=$(find_install_dir 209160) || true
    if [ -n "$ghosts_dir" ]; then
        for f in "iw6-mod.exe" "alterware-launcher.json" "awcache.json" "deckops_alterware.json"; do
            [ -f "$ghosts_dir/$f" ] && rm -f "$ghosts_dir/$f" && success "Removed $f (Ghosts)" || skip "$f not found"
        done
        # Remove AlterWare data/ subdirectories (mod scripts, not base game)
        for d in "data/dw" "data/maps" "data/scripts" "data/ui_scripts" "data/sound"; do
            [ -d "$ghosts_dir/$d" ] && rm -rf "$ghosts_dir/$d" && success "Removed $d/ (Ghosts)"
        done
        [ -f "$ghosts_dir/data/open_source_software_disclosure.txt" ] && rm -f "$ghosts_dir/data/open_source_software_disclosure.txt"
    else
        skip "Ghosts install directory not found"
    fi

    # Advanced Warfare (appid 209650 covers both SP and MP install dir)
    aw_dir=$(find_install_dir 209650) || true
    if [ -n "$aw_dir" ]; then
        for f in "s1-mod.exe" "alterware-launcher.json" "awcache.json" "deckops_alterware.json"; do
            [ -f "$aw_dir/$f" ] && rm -f "$aw_dir/$f" && success "Removed $f (AW)" || skip "$f not found"
        done
        for d in "data/dw" "data/maps" "data/scripts" "data/ui_scripts" "data/sound"; do
            [ -d "$aw_dir/$d" ] && rm -rf "$aw_dir/$d" && success "Removed $d/ (AW)"
        done
        [ -f "$aw_dir/data/open_source_software_disclosure.txt" ] && rm -f "$aw_dir/data/open_source_software_disclosure.txt"
    else
        skip "Advanced Warfare install directory not found"
    fi
fi
echo ""

info "Removing mod client files from non-Steam (My Own) game folders..."

# For games added via the My Own flow, the install dir isnt in any Steam
# library. We find them by scanning shortcuts.vdf for known exe names and
# cleaning up the same files we would for Steam installs.
python3 - << 'PYEOF'
import os, re, shutil

STEAM_DIR    = os.path.expanduser("~/.local/share/Steam")
USERDATA_DIR = os.path.join(STEAM_DIR, "userdata")

# Map exe filename (lowercase) to cleanup actions.
# "files" are removed, "dirs" are removed recursively.
# Must match what iw4x.py, cod4x.py, and iw3sp.py install.
OWN_CLEANUP = {
    "iw4mp.exe": {
        "files": ["iw4x.dll", "iw4x.exe"],
        "dirs":  ["iw4x", "iw4x-updoot"],
    },
    # Own shortcuts point at iw4x.exe, not iw4mp.exe
    "iw4x.exe": {
        "files": ["iw4x.dll", "iw4x.exe"],
        "dirs":  ["iw4x", "iw4x-updoot"],
    },
    "iw3mp.exe": {
        "files": ["cod4x_021.dll", "cod4x_loader.exe", "cod4x.exe",
                  "deckops_cod4x.json", "servercache.dat"],
        "dirs":  [],
    },
    "iw3sp.exe": {
        "files": ["iw3sp_mod.exe", "iw3sp_mod.dll", "deckops_iw3sp.json"],
        "dirs":  ["iw3sp_mod"],
    },
    # Own shortcuts point at iw3sp_mod.exe, not iw3sp.exe
    "iw3sp_mod.exe": {
        "files": ["iw3sp_mod.exe", "iw3sp_mod.dll", "deckops_iw3sp.json"],
        "dirs":  ["iw3sp_mod"],
    },
    # T6SP-MOD replaces t6sp.exe in place; DLL and metadata are the mod artifacts
    "t6sp.exe": {
        "files": ["t6sp-mod.dll", "deckops_t6sp_mod.json"],
        "dirs":  [],
    },
    "blackops3.exe": {
        "files": ["d3d11.dll", "deckops_cleanops.json"],
        "dirs":  [],
    },
    "t7x.exe": {
        "files": [],
        "dirs":  [],
        "remove_install_dir": True,   # DeckOps-T7X sibling dir — nuke entirely
    },
    # AlterWare mod client exes (Ghosts / Advanced Warfare)
    "iw6-mod.exe": {
        "files": ["iw6-mod.exe", "alterware-launcher.json", "awcache.json",
                  "deckops_alterware.json", "data/open_source_software_disclosure.txt"],
        "dirs":  ["data/dw", "data/maps", "data/scripts", "data/ui_scripts", "data/sound"],
    },
    "iw6mp64_ship.exe": {
        "files": ["iw6-mod.exe", "alterware-launcher.json", "awcache.json",
                  "deckops_alterware.json", "data/open_source_software_disclosure.txt"],
        "dirs":  ["data/dw", "data/maps", "data/scripts", "data/ui_scripts", "data/sound"],
    },
    "s1-mod.exe": {
        "files": ["s1-mod.exe", "alterware-launcher.json", "awcache.json",
                  "deckops_alterware.json", "data/open_source_software_disclosure.txt"],
        "dirs":  ["data/dw", "data/maps", "data/scripts", "data/ui_scripts", "data/sound"],
    },
    "s1_mp64_ship.exe": {
        "files": ["s1-mod.exe", "alterware-launcher.json", "awcache.json",
                  "deckops_alterware.json", "data/open_source_software_disclosure.txt"],
        "dirs":  ["data/dw", "data/maps", "data/scripts", "data/ui_scripts", "data/sound"],
    },
}

# LCD own Plutonium wrapper exes - these are DeckOps-created bash scripts,
# not original game files. Safe to delete. The shortcut exe field points at
# these so we find the game folder through them during cleanup.
PLUT_WRAPPER_EXES = [
    "t4plutsp.exe", "t4plutmp.exe", "t5plutsp.exe", "t5plutmp.exe",
    "t6plutmp.exe", "t6plutzm.exe", "iw5plutmp.exe",
]
# Add wrapper exes to cleanup map - each one just removes itself
for _wrapper in PLUT_WRAPPER_EXES:
    OWN_CLEANUP[_wrapper] = {
        "files": [_wrapper],
        "dirs":  [],
    }

if not os.path.isdir(USERDATA_DIR):
    print("  No userdata found, skipping.")
    exit(0)

cleaned = set()
for uid in os.listdir(USERDATA_DIR):
    if not uid.isdigit() or int(uid) < 10000:
        continue
    vdf_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
    if not os.path.exists(vdf_path):
        continue
    try:
        with open(vdf_path, "rb") as f:
            data = f.read()
    except Exception:
        continue

    # Pull exe paths and start dirs from shortcuts.vdf
    for exe_m in re.finditer(b'\x01(?:exe|Exe)\x00([^\x00]+)\x00', data):
        exe_raw = exe_m.group(1).decode("utf-8", errors="replace")
        exe_path = exe_raw.strip('"')
        exe_name = os.path.basename(exe_path).lower()

        cleanup = OWN_CLEANUP.get(exe_name)
        if not cleanup:
            continue

        install_dir = os.path.dirname(exe_path)
        if not install_dir or install_dir in cleaned:
            continue
        if not os.path.isdir(install_dir):
            continue
        cleaned.add(install_dir)

        print(f"  Cleaning {install_dir}...")

        # T7X uses a DeckOps-managed sibling dir — remove the entire directory.
        # Safety: only nuke if the directory is actually named DeckOps-T7X.
        # A stale shortcut from a pre-sibling install may still point at the
        # stock BO3 folder — we must never rmtree that.
        if cleanup.get("remove_install_dir"):
            if os.path.basename(install_dir) == "DeckOps-T7X":
                try:
                    shutil.rmtree(install_dir)
                    print(f"    Removed entire {os.path.basename(install_dir)}/ directory")
                except Exception as ex:
                    print(f"    Failed to remove {os.path.basename(install_dir)}/: {ex}")
            else:
                # Stale shortcut pointing at stock game dir — only remove
                # DeckOps-owned files, never the whole directory.
                for fname in ("t7x.exe", "deckops_t7x.json"):
                    fpath = os.path.join(install_dir, fname)
                    if os.path.exists(fpath):
                        try:
                            os.remove(fpath)
                            print(f"    Removed legacy {fname}")
                        except Exception as ex:
                            print(f"    Failed to remove {fname}: {ex}")
                t7x_data = os.path.join(install_dir, "t7x")
                if os.path.isdir(t7x_data):
                    try:
                        shutil.rmtree(t7x_data)
                        print(f"    Removed legacy t7x/ directory")
                    except Exception as ex:
                        print(f"    Failed to remove t7x/: {ex}")
            continue

        for fname in cleanup["files"]:
            fpath = os.path.join(install_dir, fname)
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                    print(f"    Removed {fname}")
                except Exception as ex:
                    print(f"    Failed to remove {fname}: {ex}")

        for dname in cleanup["dirs"]:
            dpath = os.path.join(install_dir, dname)
            if os.path.isdir(dpath):
                try:
                    shutil.rmtree(dpath)
                    print(f"    Removed {dname}/")
                except Exception as ex:
                    print(f"    Failed to remove {dname}/: {ex}")

        # Also remove plutonium metadata if present
        plut_meta = os.path.join(install_dir, "deckops_plutonium.json")
        if os.path.exists(plut_meta):
            try:
                os.remove(plut_meta)
                print(f"    Removed deckops_plutonium.json")
            except Exception:
                pass

if not cleaned:
    print("  No non-Steam game folders found to clean.")
PYEOF
echo ""

info "Removing DeckOps VDF edits using edit ledger (if available)..."

# The VDF edit ledger records every edit DeckOps made to localconfig.vdf and
# config.vdf at install time. If present, we use it for precise removal
# instead of regex-sweeping. The legacy regex blocks below still run as
# fallback for installs that predate the ledger.
python3 - << 'PYEOF'
import os, re, json, shutil

LEDGER_PATH = os.path.expanduser("~/.config/deckops-nightly/vdf_edits.json")
if not os.path.exists(LEDGER_PATH):
    LEDGER_PATH = os.path.expanduser("~/.config/deckops/vdf_edits.json")
steam_dir   = os.path.expanduser("~/.local/share/Steam")
userdata    = os.path.join(steam_dir, "userdata")

if not os.path.exists(LEDGER_PATH):
    print("  No VDF edit ledger found — falling back to legacy cleanup.")
    exit(0)

try:
    with open(LEDGER_PATH, "r", encoding="utf-8") as f:
        ledger = json.load(f)
except (json.JSONDecodeError, OSError) as ex:
    print(f"  Ledger read failed ({ex}) — falling back to legacy cleanup.")
    exit(0)

def validate_vdf(data):
    """Check brace balance using a quote-aware parser."""
    depth = 0; in_quote = False
    for i, c in enumerate(data):
        if c == '"' and (i == 0 or data[i-1] != '\\'):
            in_quote = not in_quote
        elif not in_quote:
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth < 0: return False
    return depth == 0

def find_block_end(text, start):
    depth = 0; i = start; in_quote = False
    while i < len(text):
        c = text[i]
        if c == '"' and (i == 0 or text[i-1] != '\\'):
            in_quote = not in_quote
        elif not in_quote:
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0: return i
        i += 1
    return -1

# ── localconfig.vdf edits ────────────────────────────────────────────────
lc_edits = ledger.get("localconfig", {})
for uid, apps in lc_edits.items():
    vdf_path = os.path.join(userdata, uid, "config", "localconfig.vdf")
    if not os.path.exists(vdf_path):
        continue

    with open(vdf_path, "r", errors="replace") as f:
        content = f.read()

    modified = False
    for appid, keys in apps.items():
        for key_name, recorded_value in keys.items():
            if key_name == "DefaultLaunchOption":
                # Remove the appid entry from the Deck configurator apps block
                interstitial_pattern = re.compile(
                    r'"Deck_ConfiguratorInterstitialApps_AppLauncherInteractionIssues"'
                    r'\s*"[^"]*"\s*"apps"\s*\{',
                    re.IGNORECASE
                )
                m = interstitial_pattern.search(content)
                if not m:
                    continue
                apps_open  = m.end() - 1
                apps_close = find_block_end(content, apps_open)
                if apps_close == -1:
                    continue
                apps_block = content[apps_open + 1:apps_close]
                appid_pat = re.compile(r'"' + re.escape(appid) + r'"\s*\{', re.IGNORECASE)
                am = appid_pat.search(apps_block)
                if not am:
                    continue
                entry_open  = am.start()
                entry_close = find_block_end(apps_block, am.end() - 1)
                if entry_close == -1:
                    continue
                apps_block = apps_block[:entry_open] + apps_block[entry_close + 1:]
                content = content[:apps_open + 1] + apps_block + content[apps_close:]
                modified = True
                print(f"  uid {uid}: [ledger] removed DefaultLaunchOption for appid {appid}")

            elif key_name in ("LaunchOptions", "UseSteamControllerConfig"):
                # Find the appid block, then blank or remove the key
                key_pattern = re.compile(
                    r'"' + re.escape(appid) + r'"\s*\{',
                    re.IGNORECASE
                )
                key_match = key_pattern.search(content)
                if not key_match:
                    continue
                app_open  = key_match.end() - 1
                app_close = find_block_end(content, app_open)
                if app_close == -1:
                    continue
                app_inner = content[app_open + 1:app_close]

                # Only touch the flat section, not inside sub-blocks
                subblock_match = re.search(r'"[^"]+"\s*\{', app_inner)
                flat_section = app_inner[:subblock_match.start()] if subblock_match else app_inner

                val_pattern = re.compile(
                    r'("' + re.escape(key_name) + r'"\s*")((?:[^"\\]|\\.)*)(")',
                    re.IGNORECASE
                )
                val_match = val_pattern.search(flat_section)
                if not val_match:
                    continue
                current_value = val_match.group(2)

                # For LaunchOptions, check if the recorded value is still in there
                if key_name == "LaunchOptions":
                    if recorded_value and recorded_value not in current_value:
                        print(f"  uid {uid}: [ledger] appid {appid} LaunchOptions changed — skipping")
                        continue
                    # Clear to empty
                    new_flat = val_pattern.sub(r'\g<1>\g<3>', flat_section, count=1)
                else:
                    # UseSteamControllerConfig — clear to empty
                    new_flat = val_pattern.sub(r'\g<1>\g<3>', flat_section, count=1)

                if subblock_match:
                    new_app_inner = new_flat + app_inner[subblock_match.start():]
                else:
                    new_app_inner = new_flat
                content = content[:app_open + 1] + new_app_inner + content[app_close:]
                modified = True
                print(f"  uid {uid}: [ledger] cleared {key_name} for appid {appid}")

    if modified:
        bak = vdf_path + ".deckops_uninstall.bak"
        if not os.path.exists(bak):
            try:
                shutil.copy2(vdf_path, bak)
            except Exception:
                pass
        with open(vdf_path, "w", errors="replace") as f:
            f.write(content)
        if not validate_vdf(content):
            print(f"  uid {uid}: [ledger] VDF validation FAILED — restoring backup")
            if os.path.exists(bak):
                try:
                    shutil.copy2(bak, vdf_path)
                except Exception:
                    print(f"  uid {uid}: backup restore also failed")

# ── config.vdf CompatToolMapping edits ────────────────────────────────────
cv_edits = ledger.get("config_vdf", {})
compat_edits = cv_edits.get("CompatToolMapping", {})
if compat_edits:
    config_vdf = os.path.join(steam_dir, "config", "config.vdf")
    if os.path.exists(config_vdf):
        with open(config_vdf, "r", encoding="utf-8") as f:
            data = f.read()
        cv_modified = False
        for appid in compat_edits:
            pattern = rf'\t+"{re.escape(appid)}"\n\t+\{{[^}}]*\}}\n?'
            if re.search(pattern, data, re.MULTILINE | re.DOTALL):
                data = re.sub(pattern, "", data, flags=re.MULTILINE | re.DOTALL)
                cv_modified = True
                print(f"  [ledger] removed CompatToolMapping for appid {appid}")
        if cv_modified:
            bak = config_vdf + ".bak"
            try:
                shutil.copy2(config_vdf, bak)
            except Exception:
                pass
            with open(config_vdf, "w", encoding="utf-8") as f:
                f.write(data)

# ── configset VDF edits ───────────────────────────────────────────────────
cs_edits = ledger.get("configsets", {})
for cs_filename, keys in cs_edits.items():
    # Search across all UIDs for this configset file
    if not os.path.isdir(userdata):
        break
    for uid in os.listdir(userdata):
        if not uid.isdigit() or int(uid) < 10000:
            continue
        steam_cfg_root = os.path.join(
            steam_dir, "steamapps", "common",
            "Steam Controller Configs", uid, "config"
        )
        cs_path = os.path.join(steam_cfg_root, cs_filename)
        if not os.path.exists(cs_path):
            continue
        with open(cs_path, "r", encoding="utf-8", errors="replace") as f:
            cs_content = f.read()
        cs_modified = False
        for key in keys:
            pattern = rf'\t"{re.escape(key)}"\n\t\{{[^}}]*\}}\n?'
            if re.search(pattern, cs_content, re.MULTILINE | re.DOTALL):
                cs_content = re.sub(pattern, "", cs_content, flags=re.MULTILINE | re.DOTALL)
                cs_modified = True
                print(f"  uid {uid}: [ledger] removed {key} from {cs_filename}")
        if cs_modified:
            with open(cs_path, "w", encoding="utf-8") as f:
                f.write(cs_content)

# Clean up the ledger file itself
try:
    os.remove(LEDGER_PATH)
    print("  Ledger file removed.")
except Exception:
    pass

print("  Ledger-based VDF cleanup complete.")
PYEOF

echo ""

info "Removing DeckOps Deck configurator launch defaults from localconfig.vdf..."

# Mirrors: wrapper.py set_default_launch_option()
python3 - << 'PYEOF'
import os, re, shutil

# Appids whose DefaultLaunchOption DeckOps writes via set_default_launch_option.
# These live in the Deck_ConfiguratorInterstitialApps "apps" block, not the
# standard LaunchOptions flat key, so they need separate removal.
# See: wrapper.py set_default_launch_option() for the write side.
DECK_APPIDS = {"7940", "10090"}

steam_dir = os.path.expanduser("~/.local/share/Steam")
userdata  = os.path.join(steam_dir, "userdata")

if not os.path.isdir(userdata):
    print("  No Steam userdata found — skipping.")
    exit(0)

def find_block_end(text, start):
    depth = 0; i = start; in_quote = False
    while i < len(text):
        c = text[i]
        if c == '"' and (i == 0 or text[i-1] != '\\'):
            in_quote = not in_quote
        elif not in_quote:
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0: return i
        i += 1
    return -1

def validate_vdf(data):
    """Check brace balance using the same quote-aware parser."""
    depth = 0; in_quote = False
    for i, c in enumerate(data):
        if c == '"' and (i == 0 or data[i-1] != '\\'):
            in_quote = not in_quote
        elif not in_quote:
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth < 0: return False
    return depth == 0

for uid in os.listdir(userdata):
    if not uid.isdigit() or int(uid) < 10000:
        continue
    vdf_path = os.path.join(userdata, uid, "config", "localconfig.vdf")
    if not os.path.exists(vdf_path):
        continue

    with open(vdf_path, "r", errors="replace") as f:
        content = f.read()

    # Find the Deck configurator apps block
    interstitial_pattern = re.compile(
        r'"Deck_ConfiguratorInterstitialApps_AppLauncherInteractionIssues"'
        r'\s*"[^"]*"\s*"apps"\s*\{',
        re.IGNORECASE
    )
    m = interstitial_pattern.search(content)
    if not m:
        print(f"  uid {uid}: no Deck configurator block found — skipping")
        continue

    apps_open  = m.end() - 1
    apps_close = find_block_end(content, apps_open)
    if apps_close == -1:
        continue

    apps_block = content[apps_open + 1:apps_close]
    modified   = False

    for appid in DECK_APPIDS:
        appid_pat = re.compile(r'"' + re.escape(appid) + r'"\s*\{', re.IGNORECASE)
        am = appid_pat.search(apps_block)
        if not am:
            continue
        entry_open  = am.start()
        entry_close = find_block_end(apps_block, am.end() - 1)
        if entry_close == -1:
            continue
        apps_block = apps_block[:entry_open] + apps_block[entry_close + 1:]
        modified = True
        print(f"  uid {uid}: removed DefaultLaunchOption for appid {appid}")

    if modified:
        new_content = content[:apps_open + 1] + apps_block + content[apps_close:]

        # Backup before writing
        bak = vdf_path + ".deckops_uninstall.bak"
        if not os.path.exists(bak):
            try:
                shutil.copy2(vdf_path, bak)
            except Exception:
                pass

        with open(vdf_path, "w", errors="replace") as f:
            f.write(new_content)

        # Validate — if corrupt, restore backup and leave edits in place
        if not validate_vdf(new_content):
            print(f"  uid {uid}: VDF validation FAILED — restoring backup")
            if os.path.exists(bak):
                try:
                    shutil.copy2(bak, vdf_path)
                except Exception:
                    print(f"  uid {uid}: backup restore also failed")
    else:
        print(f"  uid {uid}: no DeckOps configurator defaults found")
PYEOF

echo ""

info "Clearing DeckOps launch options from localconfig.vdf..."

# Mirrors: wrapper.py clear_launch_options()
# Clears LaunchOptions for ALL managed Steam appids so no stale launch
# commands survive uninstall. Covers AlterWare bash substitutions,
# CleanOps DLL injection, LCD Plutonium Heroic launch, and any future
# launch options DeckOps writes.
python3 - << 'PYEOF'
import os, re, shutil

MANAGED_STEAM_APPIDS = [
    "7940", "10090", "10180", "10190", "42680", "42690", "42750",
    "42700", "42710", "202970", "202990", "212910", "311210",
    "209160", "209170", "209650", "209660",
]

steam_dir = os.path.expanduser("~/.local/share/Steam")
userdata  = os.path.join(steam_dir, "userdata")

if not os.path.isdir(userdata):
    print("  No Steam userdata found — skipping.")
    exit(0)

def find_block_end(text, start):
    """Brace-depth parser that skips braces inside quoted strings."""
    depth = 0; i = start; in_quote = False
    while i < len(text):
        c = text[i]
        if c == '"' and (i == 0 or text[i-1] != '\\'):
            in_quote = not in_quote
        elif not in_quote:
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0: return i
        i += 1
    return -1

def validate_vdf(data):
    """Check brace balance using the same quote-aware parser."""
    depth = 0; in_quote = False
    for i, c in enumerate(data):
        if c == '"' and (i == 0 or data[i-1] != '\\'):
            in_quote = not in_quote
        elif not in_quote:
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth < 0: return False
    return depth == 0

cleared = 0
for uid in os.listdir(userdata):
    if not uid.isdigit() or int(uid) < 10000:
        continue
    vdf_path = os.path.join(userdata, uid, "config", "localconfig.vdf")
    if not os.path.exists(vdf_path):
        continue

    with open(vdf_path, "r", errors="replace") as f:
        content = f.read()

    modified = False
    for appid in MANAGED_STEAM_APPIDS:
        key_pattern = re.compile(
            r'"' + re.escape(appid) + r'"\s*\{',
            re.IGNORECASE
        )
        key_match = key_pattern.search(content)
        if not key_match:
            continue

        app_open  = key_match.end() - 1
        app_close = find_block_end(content, app_open)
        if app_close == -1:
            continue

        app_inner = content[app_open + 1:app_close]

        # Only touch LaunchOptions in the flat block, not inside sub-blocks.
        subblock_match = re.search(r'"[^"]+"\s*\{', app_inner)
        flat_section = app_inner[:subblock_match.start()] if subblock_match else app_inner

        launch_pattern = re.compile(
            r'("LaunchOptions"\s*")((?:[^"\\]|\\.)*)(")',
            re.IGNORECASE
        )
        launch_match = launch_pattern.search(flat_section)
        if not launch_match or not launch_match.group(2).strip():
            continue

        # Clear the value to empty string
        new_flat = launch_pattern.sub(r'\g<1>\g<3>', flat_section, count=1)
        if subblock_match:
            new_app_inner = new_flat + app_inner[subblock_match.start():]
        else:
            new_app_inner = new_flat

        content = (
            content[:app_open + 1] +
            new_app_inner +
            content[app_close:]
        )
        modified = True
        cleared += 1
        print(f"  uid {uid}: cleared LaunchOptions for appid {appid}")

    if modified:
        bak = vdf_path + ".deckops_uninstall.bak"
        if not os.path.exists(bak):
            try:
                shutil.copy2(vdf_path, bak)
            except Exception:
                pass

        with open(vdf_path, "w", errors="replace") as f:
            f.write(content)

        # Validate — if corrupt, restore backup and leave edits in place
        if not validate_vdf(content):
            print(f"  uid {uid}: VDF validation FAILED — restoring backup")
            if os.path.exists(bak):
                try:
                    shutil.copy2(bak, vdf_path)
                    cleared = 0  # don't report cleared if we had to restore
                except Exception:
                    print(f"  uid {uid}: backup restore also failed")

if cleared == 0:
    print("  No DeckOps launch options found — nothing to clear.")
else:
    print(f"  Cleared {cleared} launch option(s) total.")
PYEOF

echo ""

if [ -n "$STEAM_ROOT" ]; then
    # Close Heroic first if it's running, otherwise it may hold files in
    # ~/Games/Heroic/Prefixes/default open and the rm below will fail.
    info "Closing HGL if running..."
    if pgrep -f "com.heroicgameslauncher.hgl" > /dev/null 2>&1; then
        flatpak kill com.heroicgameslauncher.hgl 2>/dev/null
        sleep 1
        success "HGL closed"
    else
        skip "HGL was not running"
    fi
    echo ""

    # ── Sweep stale plut_lan.sh sidecars ──────────────────────────────────
    # Pre-Pass-1 OLED installs wrote <gametag>plut_lan.sh into each game's
    # install dir. Pass 1 stopped creating them but didn't sweep existing
    # files. Remove any that remain across all known Steam libraries.
    info "Sweeping stale plut_lan.sh sidecars..."

    LAN_SWEEP_DIRS=()
    [ -d "$STEAM_ROOT/steamapps/common" ] && LAN_SWEEP_DIRS+=("$STEAM_ROOT/steamapps/common")

    LF_VDF_SWEEP="$STEAM_ROOT/steamapps/libraryfolders.vdf"
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
        skip "No stale plut_lan.sh sidecars found."
    fi
    echo ""

    info "Removing Plutonium data from all Wine prefixes..."

    # Build list of all compatdata dirs (internal + SD card + any extra libraries)
    COMPAT_DIRS=()
    [ -d "$STEAM_ROOT/steamapps/compatdata" ] && COMPAT_DIRS+=("$STEAM_ROOT/steamapps/compatdata")

    # Parse libraryfolders.vdf for additional library paths
    LF_VDF="$STEAM_ROOT/steamapps/libraryfolders.vdf"
    if [ -f "$LF_VDF" ]; then
        while IFS= read -r libpath; do
            [ -d "$libpath/steamapps/compatdata" ] && COMPAT_DIRS+=("$libpath/steamapps/compatdata")
        done < <(sed -n 's/.*"path"[[:space:]]*"\([^"]*\)".*/\1/p' "$LF_VDF")
    fi

    # Brute-force SD card mount points
    for mount in /run/media/deck/*/steamapps/compatdata /run/media/deck/*/SteamLibrary/steamapps/compatdata; do
        [ -d "$mount" ] && COMPAT_DIRS+=("$mount")
    done

    # Heroic Games Launcher's shared prefix root (LCD Plutonium target).
    # The LCD path puts Plutonium at:
    #   ~/Games/Heroic/Prefixes/default/pfx/drive_c/users/steamuser/AppData/Local/Plutonium
    # which has the same shape as a Steam compatdata prefix, so the loop
    # below catches it without special-casing.
    [ -d "$HOME/Games/Heroic/Prefixes" ] && COMPAT_DIRS+=("$HOME/Games/Heroic/Prefixes")

    found_any=0
    for COMPATDATA in "${COMPAT_DIRS[@]}"; do
        for prefix_dir in "$COMPATDATA"/*/; do
            plut_dir="$prefix_dir/pfx/drive_c/users/steamuser/AppData/Local/Plutonium"
            if [ -d "$plut_dir" ]; then
                prefix_id=$(basename "$prefix_dir")
                rm -rf "$plut_dir" && success "Removed Plutonium from prefix $prefix_id" || warn "Failed to remove Plutonium from prefix $prefix_id"
                found_any=1
            fi
        done
    done
    [ "$found_any" -eq 0 ] && skip "No Plutonium folders found in any prefix"

    for appid in 42690 42750 10090 42700 202990 212910; do
        game_dir=$(find_install_dir "$appid") || true
        if [ -n "$game_dir" ] && [ -f "$game_dir/deckops_plutonium.json" ]; then
            rm -f "$game_dir/deckops_plutonium.json" && success "Removed DeckOps metadata for appid $appid" || warn "Failed to remove metadata for appid $appid"
        fi
    done
fi
echo ""

# ── Heroic Games Launcher state ───────────────────────────────────────────────
# LCD Plutonium installs use Heroic for the bootstrap login flow and to host
# Plutonium inside Heroic's shared default Wine prefix. The Wine-prefix walk
# above (extended with ~/Games/Heroic/Prefixes) already handles the
# AppData/Local/Plutonium dir inside that shared prefix. This block handles
# the remaining Heroic-specific artifacts that live OUTSIDE any Wine prefix:
#
#   1. ~/Games/Heroic/deckops_plutonium/  -- DeckOps' downloaded plutonium.exe
#                                            (a one-off, NOT a game install)
#   2. Heroic library.json sideload entries with app_name starting do_*
#      -- DeckOps-managed sideload registrations
#   3. Heroic GamesConfig do_*.json files -- per-entry config JSONs
#   4. ~/Games/Call of Duty * /deckops_plutonium.json metadata sentinels
#      from own-game (non-Steam) install dirs
#
# IMPORTANT: This block ONLY removes things matching "do_*" prefix (DeckOps
# naming convention) or files literally named deckops_plutonium.json. It
# does NOT touch any Heroic game install dirs, any other sideloaded games
# the user added themselves, or any non-DeckOps Heroic state. The user's
# own Heroic library is preserved completely.

info "Removing DeckOps artifacts from HGL..."

HGL_CONFIG="$HOME/.var/app/com.heroicgameslauncher.hgl/config/heroic"
HGL_LIB="$HGL_CONFIG/sideload_apps/library.json"
HGL_GAMESCONFIG="$HGL_CONFIG/GamesConfig"

# 1. DeckOps' downloaded plutonium.exe directory.
#    This is NOT a game install -- it's just where launch_bootstrapper_lcd
#    drops a copy of plutonium.exe so Heroic can sideload it. Safe to delete.
if [ -d "$HOME/Games/Heroic/deckops_plutonium" ]; then
    rm -rf "$HOME/Games/Heroic/deckops_plutonium" && success "Removed DeckOps plutonium.exe download dir" || warn "Failed to remove deckops_plutonium dir"
else
    skip "DeckOps plutonium download dir not found"
fi

# 2. Strip do_* sideload entries from Heroic's library.json.
#    Preserves any other sideloaded games the user added themselves --
#    we ONLY remove entries whose app_name starts with "do_" (DeckOps prefix).
if [ -f "$HGL_LIB" ]; then
    python3 - "$HGL_LIB" << 'PYEOF'
import json, sys
p = sys.argv[1]
try:
    with open(p) as f:
        data = json.load(f)
    games_before = data.get("games", [])
    games_after = [g for g in games_before
                   if not g.get("app_name", "").startswith("do_")]
    removed = len(games_before) - len(games_after)
    data["games"] = games_after
    with open(p, "w") as f:
        json.dump(data, f, indent=2)
    if removed > 0:
        print(f"Removed {removed} DeckOps sideload entries from library.json")
    else:
        print("No DeckOps sideload entries found in library.json")
except Exception as ex:
    print(f"library.json edit failed: {ex}")
    sys.exit(1)
PYEOF
    if [ $? -eq 0 ]; then
        success "Heroic library.json cleaned"
    else
        warn "Heroic library.json edit failed"
    fi
else
    skip "Heroic library.json not found (Heroic may not be installed)"
fi

# 3. Per-entry GamesConfig JSON files.
#    Each DeckOps sideload entry has a matching <app_name>.json in
#    GamesConfig/. We delete only files matching the do_* prefix.
if [ -d "$HGL_GAMESCONFIG" ]; then
    gc_count=0
    # Use nullglob-safe iteration so an empty match doesn't trip the loop
    shopt -s nullglob
    for f in "$HGL_GAMESCONFIG"/do_*.json; do
        if [ -f "$f" ]; then
            rm -f "$f" && gc_count=$((gc_count + 1))
        fi
    done
    shopt -u nullglob
    if [ "$gc_count" -gt 0 ]; then
        success "Removed $gc_count DeckOps GamesConfig file(s)"
    else
        skip "No DeckOps GamesConfig files found"
    fi
else
    skip "Heroic GamesConfig dir not found"
fi

# 4. deckops_plutonium.json metadata sentinels in own-game install dirs.
#    LCD installs put these in ~/Games/Call of Duty * (own-game source).
#    The earlier per-appid loop only covers Steam-installed games -- this
#    catches the own-game installs without touching the game files
#    themselves. We ONLY remove files literally named deckops_plutonium.json.
own_sentinel_count=0
shopt -s nullglob
for sentinel in "$HOME/Games/Call of Duty "*"/deckops_plutonium.json"; do
    if [ -f "$sentinel" ]; then
        rm -f "$sentinel" && own_sentinel_count=$((own_sentinel_count + 1))
    fi
done
shopt -u nullglob
if [ "$own_sentinel_count" -gt 0 ]; then
    success "Removed $own_sentinel_count own-game DeckOps metadata sentinel(s)"
else
    skip "No own-game DeckOps metadata sentinels found"
fi
echo ""

info "Stopping any leftover DeckOps audio..."
pkill -f "mpv" 2>/dev/null && success "mpv stopped" || skip "No audio process found"
echo ""

info "Removing DeckOps install directory and config..."

DECKOPS_DIRS=(
    "$HOME/DeckOps-Nightly"
    "$HOME/DeckOps"
    "$HOME/.local/share/deckops-nightly"
    "$HOME/.config/deckops-nightly"
    "$HOME/.local/share/deckops-nightly/plutonium_prefix"
    "$HOME/.local/share/deckops/plutonium_prefix"
    "$HOME/.local/share/deckops"
    "$HOME/.config/deckops"
)

for d in "${DECKOPS_DIRS[@]}"; do
    if [ -d "$d" ]; then
        rm -rf "$d" && success "Removed $d" || warn "Failed to remove $d"
    else
        skip "$d -- not found"
    fi
done
echo ""

info "Removing DeckOps non-Steam shortcuts from Steam library..."

# Mirrors: shortcut.py SHORTCUTS and the binary VDF format from _make_shortcut_entry()
remove_steam_shortcuts() {
    python3 - << 'PYEOF'
import os, struct

SHORTCUT_NAMES = {
    # Steam-path shortcuts (shortcut.py SHORTCUTS)
    "Call of Duty 4: Modern Warfare - Multiplayer",
    "Call of Duty: World at War - Multiplayer",
    "DeckOps",
    "DeckOps Nightly",
    # Plutonium offline launcher shortcut (shortcut.py LAUNCHER_TITLE)
    "DeckOps: Plutonium Offline",
    "DeckOps: Plutonium Launcher",  # old name, kept for migration
    # Own-path shortcuts (shortcut.py OWN_SHORTCUTS)
    "Call of Duty 4: Modern Warfare - Singleplayer",
    "Call of Duty: Modern Warfare 2 (2009) - Multiplayer",
    "Call of Duty: Modern Warfare 2 (2009) - Singleplayer",
    "Call of Duty: Modern Warfare 3 (2011) - Multiplayer",
    "Call of Duty: Modern Warfare 3 (2011) - Singleplayer",
    "Call of Duty: World at War",
    "Call of Duty: Black Ops",
    "Call of Duty: Black Ops - Multiplayer",
    "Call of Duty: Black Ops II - Singleplayer",
    "Call of Duty: Black Ops II - Zombies",
    "Call of Duty: Black Ops II - Multiplayer",
    "Call of Duty: Black Ops III",
    "Call of Duty: Black Ops 3 T7x",
    "Call of Duty: Ghosts - Singleplayer",
    "Call of Duty: Ghosts - Multiplayer",
    "Call of Duty: Advanced Warfare - Singleplayer",
    "Call of Duty: Advanced Warfare - Multiplayer",
}

steam_dir = os.path.expanduser("~/.local/share/Steam")
userdata  = os.path.join(steam_dir, "userdata")

if not os.path.isdir(userdata):
    print("No Steam userdata found — skipping.")
    exit(0)

for uid in os.listdir(userdata):
    vdf_path = os.path.join(userdata, uid, "config", "shortcuts.vdf")
    if not os.path.exists(vdf_path):
        continue

    with open(vdf_path, "rb") as f:
        data = f.read()

    # Find and remove entries whose AppName matches our shortcuts
    # Each entry starts with \x00<index>\x00 and ends with \x08\x08 (but
    # the outer \x08 is shared). We rebuild by finding AppName fields.
    removed = 0
    # Split on entry boundaries: \x00<single digit or two digits>\x00
    # Safer: rebuild the whole file keeping only entries not in our set
    import re

    # Extract all AppName values to check if we need to do anything
    names_found = re.findall(b'\x01(?:AppName|appname)\x00([^\x00]+)\x00', data)
    names_found = [n.decode('utf-8', errors='replace') for n in names_found]

    if not any(n in SHORTCUT_NAMES for n in names_found):
        print(f"  uid {uid}: no DeckOps shortcuts found")
        continue

    # Rebuild: walk entries, skip ones matching our names
    # Header is \x00shortcuts\x00, footer is \x08\x08
    header = b'\x00shortcuts\x00'
    pos = data.find(header)
    if pos == -1:
        continue

    # Collect raw entry blobs between \x00<N>\x00 ... \x08\x08 pattern
    # Each entry: \x00{index}\x00 ... \x08 (inner end) then next entry or \x08 (outer end)
    entries_start = pos + len(header)
    raw_entries   = data[entries_start:]

    # Walk entries manually using proper binary VDF type parsing.
    # Type bytes: 0x00 = sub-dict, 0x01 = string, 0x02 = int32,
    #             0x03 = float32, 0x07 = uint64, 0x08 = end-of-dict.
    kept   = []
    cursor = 0
    idx    = 0

    while cursor < len(raw_entries):
        if raw_entries[cursor:cursor+1] == b'\x08':
            break  # outer end marker

        # Find entry start: \x00<index_str>\x00
        if raw_entries[cursor:cursor+1] != b'\x00':
            cursor += 1
            continue

        # Read key (index string)
        key_end = raw_entries.index(b'\x00', cursor + 1)
        entry_body_start = key_end + 1
        # Walk through typed fields, tracking sub-dict depth.
        # Entry body starts at depth 1 (the entry itself is a dict).
        depth = 1
        scan  = entry_body_start
        while scan < len(raw_entries) and depth > 0:
            ftype = raw_entries[scan]
            if ftype == 0x00:
                # Sub-dict start: read key name, enter dict
                k_end = raw_entries.index(b'\x00', scan + 1)
                scan = k_end + 1
                depth += 1
            elif ftype == 0x08:
                # End-of-dict
                depth -= 1
                scan += 1
            elif ftype == 0x01:
                # String: type + key\x00 + value\x00
                scan += 1
                k_end = raw_entries.index(b'\x00', scan)
                scan = k_end + 1
                v_end = raw_entries.index(b'\x00', scan)
                scan = v_end + 1
            elif ftype == 0x02:
                # Int32: type + key\x00 + 4 bytes
                scan += 1
                k_end = raw_entries.index(b'\x00', scan)
                scan = k_end + 1 + 4
            elif ftype == 0x03:
                # Float32: type + key\x00 + 4 bytes
                scan += 1
                k_end = raw_entries.index(b'\x00', scan)
                scan = k_end + 1 + 4
            elif ftype == 0x07:
                # Uint64: type + key\x00 + 8 bytes
                scan += 1
                k_end = raw_entries.index(b'\x00', scan)
                scan = k_end + 1 + 8
            else:
                # Unknown type - skip one byte and hope for the best
                scan += 1

        entry_blob = raw_entries[cursor:scan]

        # Check AppName in this blob
        name_match = re.search(b'\x01(?:AppName|appname)\x00([^\x00]+)\x00', entry_blob)
        name = name_match.group(1).decode('utf-8', errors='replace') if name_match else ""

        if name in SHORTCUT_NAMES:
            print(f"  uid {uid}: removed shortcut \"{name}\"")
            removed += 1
        else:
            # Re-index
            new_entry = b'\x00' + str(idx).encode() + b'\x00' + entry_blob[key_end - cursor + 1:]
            kept.append(new_entry)
            idx += 1

        cursor = scan

    if removed == 0:
        print(f"  uid {uid}: nothing to remove")
        continue

    # Sanity check: if we have non-DeckOps shortcuts but kept is empty,
    # the parser desynchronized and we'd wipe the user's entire library.
    total_shortcuts = len(names_found)
    non_deckops = total_shortcuts - removed
    if non_deckops > 0 and len(kept) == 0:
        print(f"  uid {uid}: parser error — expected {non_deckops} non-DeckOps entries but kept 0, skipping write")
        continue

    # Backup before writing
    import shutil
    bak = vdf_path + ".deckops_uninstall.bak"
    if not os.path.exists(bak):
        try:
            shutil.copy2(vdf_path, bak)
        except Exception:
            pass

    new_data = header + b''.join(kept) + b'\x08\x08'
    with open(vdf_path, "wb") as f:
        f.write(new_data)
    print(f"  uid {uid}: shortcuts.vdf updated ({removed} removed)")

PYEOF
}

remove_steam_shortcuts && success "Steam shortcuts cleaned up." || warn "Could not clean Steam shortcuts — remove manually if needed."
echo ""

info "Removing non-Steam shortcut artwork from Steam grid..."

# Mirrors: shortcut.py _download_artwork() and _calc_shortcut_appid()
python3 - << 'PYEOF'
import os, re, binascii, glob

# Shortcut definitions — must match shortcut.py SHORTCUTS
SHORTCUTS = {
    "cod4mp": {
        "name":       "Call of Duty 4: Modern Warfare - Multiplayer",
        "exe_name":   "iw3mp.exe",
        "game_appid": "7940",
    },
    "t4mp": {
        "name":       "Call of Duty: World at War - Multiplayer",
        "exe_name":   "CoDWaWmp.exe",
        "game_appid": "10090",
    },
}

def find_install_dir(steam_root, appid):
    """Find the install directory for a Steam appid."""
    search_dirs = [os.path.join(steam_root, "steamapps")]
    
    # Parse libraryfolders.vdf
    vdf_path = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf_path):
        with open(vdf_path, "r", errors="replace") as f:
            for match in re.findall(r'"path"\s+"([^"]+)"', f.read()):
                search_dirs.append(os.path.join(match, "steamapps"))
                search_dirs.append(os.path.join(match, "SteamLibrary", "steamapps"))
    
    # SD card paths
    for pattern in ["/run/media/deck/*/SteamLibrary/steamapps", "/run/media/deck/*/steamapps"]:
        search_dirs.extend(glob.glob(pattern))
    
    for steamapps in search_dirs:
        acf = os.path.join(steamapps, f"appmanifest_{appid}.acf")
        if os.path.exists(acf):
            with open(acf, "r", errors="replace") as f:
                match = re.search(r'"installdir"\s+"([^"]+)"', f.read())
                if match:
                    return os.path.join(steamapps, "common", match.group(1))
    return None

def calc_shortcut_appid(exe_path, name):
    """Calculate Steam's shortcut appid from exe path and name."""
    key = (exe_path + name).encode("utf-8")
    crc = binascii.crc32(key) & 0xFFFFFFFF
    return str((crc | 0x80000000) & 0xFFFFFFFF)

steam_root = os.path.expanduser("~/.local/share/Steam")
userdata   = os.path.join(steam_root, "userdata")

if not os.path.isdir(userdata):
    print("  No Steam userdata found — skipping.")
    exit(0)

# Calculate actual shortcut appids based on installed game paths
shortcut_appids = set()
for key, info in SHORTCUTS.items():
    install_dir = find_install_dir(steam_root, info["game_appid"])
    if install_dir:
        exe_path = os.path.join(install_dir, info["exe_name"])
        appid = calc_shortcut_appid(exe_path, info["name"])
        shortcut_appids.add(appid)
        print(f"  Found {info['name']} → appid {appid}")

# Also find "own" game shortcut appids by scanning shortcuts.vdf for
# known exe names. These were renamed to canonical names by DeckOps so
# we calculate the appid from exe_path + canonical_name.
OWN_EXE_MAP = {
    "iw3mp.exe":      "Call of Duty 4: Modern Warfare - Multiplayer",
    "iw3sp.exe":      "Call of Duty 4: Modern Warfare - Singleplayer",
    "iw4mp.exe":      "Call of Duty: Modern Warfare 2 (2009) - Multiplayer",
    "iw4sp.exe":      "Call of Duty: Modern Warfare 2 (2009) - Singleplayer",
    "iw5mp.exe":      "Call of Duty: Modern Warfare 3 (2011) - Multiplayer",
    "iw5sp.exe":      "Call of Duty: Modern Warfare 3 (2011) - Singleplayer",
    "codwaw.exe":     "Call of Duty: World at War",
    "codwawmp.exe":   "Call of Duty: World at War - Multiplayer",
    "blackops.exe":   "Call of Duty: Black Ops",
    "blackopsmp.exe": "Call of Duty: Black Ops - Multiplayer",
    "t6sp.exe":       "Call of Duty: Black Ops II - Singleplayer",
    "t6zm.exe":       "Call of Duty: Black Ops II - Zombies",
    "t6mp.exe":       "Call of Duty: Black Ops II - Multiplayer",
    # Mod client exes (own shortcuts point at these, not original game exes)
    "iw4x.exe":       "Call of Duty: Modern Warfare 2 (2009) - Multiplayer",
    "iw3sp_mod.exe":  "Call of Duty 4: Modern Warfare - Singleplayer",
    # LCD own Plutonium wrapper exes
    "t4plutsp.exe":   "Call of Duty: World at War",
    "t4plutmp.exe":   "Call of Duty: World at War - Multiplayer",
    "t5plutsp.exe":   "Call of Duty: Black Ops",
    "t5plutmp.exe":   "Call of Duty: Black Ops - Multiplayer",
    "t6plutmp.exe":   "Call of Duty: Black Ops II - Multiplayer",
    "t6plutzm.exe":   "Call of Duty: Black Ops II - Zombies",
    "iw5plutmp.exe":  "Call of Duty: Modern Warfare 3 (2011) - Multiplayer",
    "blackops3.exe":  "Call of Duty: Black Ops III",
    "t7x.exe":        "Call of Duty: Black Ops 3 T7x",
}

for uid in os.listdir(userdata):
    if not uid.isdigit() or int(uid) < 10000:
        continue
    vdf_path = os.path.join(userdata, uid, "config", "shortcuts.vdf")
    if not os.path.exists(vdf_path):
        continue
    try:
        with open(vdf_path, "rb") as f:
            data = f.read()
        for m in re.finditer(b'\x01(?:exe|Exe)\x00([^\x00]+)\x00', data):
            exe_raw = m.group(1).decode("utf-8", errors="replace")
            exe_name = os.path.basename(exe_raw.strip('"')).lower()
            canonical = OWN_EXE_MAP.get(exe_name)
            if canonical:
                # Use exe_raw (with quotes) for appid calc to match Steam
                appid = calc_shortcut_appid(exe_raw, canonical)
                if appid not in shortcut_appids:
                    shortcut_appids.add(appid)
                    print(f"  Found own game {canonical} → appid {appid}")
    except Exception:
        pass

if not shortcut_appids:
    print("  No shortcut appids to clean up.")

# Add the DeckOps offline launcher shortcut appid. The launcher uses
# DeckOps_Offline.exe as its exe path, and its appid is calculated from
# the quoted exe path + title. We check both the current and old exe paths.
_LAUNCHER_TITLE = "DeckOps: Plutonium Offline"
_OLD_LAUNCHER_TITLE = "DeckOps: Plutonium Launcher"
_launcher_exe_new = os.path.join(os.path.expanduser("~"), "DeckOps-Nightly",
                                  "assets", "LAN", "DeckOps_Offline.exe")
_launcher_exe_old = os.path.join(os.path.expanduser("~"), "DeckOps-Nightly",
                                  ".venv", "bin", "python3")
# Also check stable branch paths
_launcher_exe_new_stable = os.path.join(os.path.expanduser("~"), "DeckOps",
                                         "assets", "LAN", "DeckOps_Offline.exe")
_launcher_exe_old_stable = os.path.join(os.path.expanduser("~"), "DeckOps",
                                         ".venv", "bin", "python3")
for _exe, _title in [
    (f'"{_launcher_exe_new}"', _LAUNCHER_TITLE),
    (f'"{_launcher_exe_old}"', _LAUNCHER_TITLE),
    (f'"{_launcher_exe_new}"', _OLD_LAUNCHER_TITLE),
    (f'"{_launcher_exe_old}"', _OLD_LAUNCHER_TITLE),
    (f'"{_launcher_exe_new_stable}"', _LAUNCHER_TITLE),
    (f'"{_launcher_exe_old_stable}"', _LAUNCHER_TITLE),
    (f'"{_launcher_exe_new_stable}"', _OLD_LAUNCHER_TITLE),
    (f'"{_launcher_exe_old_stable}"', _OLD_LAUNCHER_TITLE),
]:
    _appid = calc_shortcut_appid(_exe, _title)
    if _appid not in shortcut_appids:
        shortcut_appids.add(_appid)
        print(f"  Launcher shortcut → appid {_appid}")

# Also clean up custom artwork we applied to Steam MP/ZM games
STEAM_ART_APPIDS = {"10190", "42690", "42750", "42710", "202990", "212910"}
all_appids = shortcut_appids | STEAM_ART_APPIDS

if not all_appids:
    exit(0)

# Remove artwork files matching these appids
for uid in os.listdir(userdata):
    if not uid.isdigit() or int(uid) < 10000:
        continue
    grid_dir = os.path.join(userdata, uid, "config", "grid")
    if not os.path.isdir(grid_dir):
        continue
    for f in os.listdir(grid_dir):
        for appid in all_appids:
            if f.startswith(appid):
                path = os.path.join(grid_dir, f)
                os.remove(path)
                print(f"  Removed {f}")
PYEOF

echo ""

info "Removing DeckOps controller templates..."

TEMPLATE_DIR="$HOME/.steam/steam/controller_base/templates"
for f in \
    "controller_neptune_deckops_hold.vdf" \
    "controller_neptune_deckops_toggle.vdf" \
    "controller_neptune_deckops_ads.vdf" \
    "controller_neptune_deckops_off.vdf" \
    "controller_neptune_deckops_other_hold.vdf" \
    "controller_neptune_deckops_other_toggle.vdf" \
    "controller_neptune_deckops_other_ads.vdf" \
    "controller_neptune_deckops_other_off.vdf" \
    "controller_neptune_deckops_legion_ads.vdf" \
    "controller_neptune_deckops_legion_off.vdf" \
    "controller_neptune_deckops_legion_other_ads.vdf" \
    "controller_neptune_deckops_legion_other_off.vdf" \
    "controller_steamos_handheld_deckops_legion_ads.vdf" \
    "controller_steamos_handheld_deckops_legion_off.vdf" \
    "controller_steamos_handheld_deckops_legion_other_ads.vdf" \
    "controller_steamos_handheld_deckops_legion_other_off.vdf" \
    "controller_neptune_deckops_2btn_ads.vdf" \
    "controller_neptune_deckops_2btn_off.vdf" \
    "controller_neptune_deckops_2btn_other_ads.vdf" \
    "controller_neptune_deckops_2btn_other_off.vdf" \
    "controller_ps5_deckops.vdf" \
    "controller_ps5_deckops_ads.vdf" \
    "controller_ps5_deckops_other.vdf" \
    "controller_ps5_deckops_other_ads.vdf" \
    "controller_ps5_edge_deckops.vdf" \
    "controller_ps5_edge_deckops_ads.vdf" \
    "controller_ps5_edge_deckops_other.vdf" \
    "controller_ps5_edge_deckops_other_ads.vdf" \
    "controller_ps4_deckops.vdf" \
    "controller_ps4_deckops_ads.vdf" \
    "controller_ps4_deckops_other.vdf" \
    "controller_ps4_deckops_other_ads.vdf" \
    "controller_xbox360_deckops.vdf" \
    "controller_xbox360_deckops_other.vdf" \
    "controller_xboxone_deckops.vdf" \
    "controller_xboxone_deckops_other.vdf" \
    "controller_xboxelite_deckops.vdf" \
    "controller_xboxelite_deckops_other.vdf" \
    "controller_generic_deckops.vdf" \
    "controller_generic_deckops_other.vdf" \
    "controller_triton_deckops_ads.vdf" \
    "controller_triton_deckops_off.vdf" \
    "controller_triton_deckops_hold.vdf" \
    "controller_triton_deckops_toggle.vdf" \
    "controller_triton_deckops_other_ads.vdf" \
    "controller_triton_deckops_other_off.vdf" \
    "controller_triton_deckops_other_hold.vdf" \
    "controller_triton_deckops_other_toggle.vdf"; do
    target="$TEMPLATE_DIR/$f"
    if [ -f "$target" ]; then
        rm -f "$target" && success "Removed $f" || warn "Failed to remove $f"
    else
        skip "$f not found"
    fi
done
echo ""

info "Removing per-game controller configs..."

# Mirrors: controller_profiles.py assign_controller_profiles() and
#          shortcut.py _assign_controller_config()
# If you change APPID_NAMED_KEYS or MANAGED_STEAM_APPIDS in the source
# files, update the copies here too or uninstall will miss entries.
python3 - << 'PYEOF'
import os, shutil, re, binascii, glob

STEAM_DIR = os.path.expanduser("~/.local/share/Steam")
USERDATA  = os.path.join(STEAM_DIR, "userdata")
STEAM_CONFIG = os.path.join(STEAM_DIR, "config", "config.vdf")

# Standard Steam appids managed by DeckOps
MANAGED_STEAM_APPIDS = [
    "7940", "10090", "10180", "10190", "42680", "42690", "42750",
    "42700", "42710", "202970", "202990", "212910", "311210",
    "209160", "209170", "209650", "209660",
]

# Named game keys used in configset files — must match controller_profiles.py
# Includes BOTH old (pre-fix) and new named keys so uninstall cleans up
# regardless of which version the user installed with.
APPID_NAMED_KEYS = {
    "7940":   ["call of duty 4 modern warfare (2007)"],
    "10090":  ["call of duty world at war",
               "call of duty world at war - multiplayer"],
    "10180":  ["call of duty modern warfare 2 (2009)",
               "call of duty modern warfare 2 (2009) - multiplayer"],
    "10190":  ["call of duty modern warfare 2 (2009) - multiplayer"],
    "42680":  ["call of duty modern warfare 3",
               "call of duty modern warfare 3 - multiplayer"],
    "42690":  ["call of duty modern warfare 3 - multiplayer"],
    "42750":  ["call of duty modern warfare 3 - dedicated server"],
    "42700":  ["call of duty black ops",
               "call of duty black ops - zombies"],
    "42710":  ["call of duty black ops - multiplayer"],
    "202970": [],
    "202990": ["call of duty black ops ii - multiplayer"],
    "212910": ["call of duty black ops ii - zombies"],
    "311210": ["call of duty black ops iii"],
    "209160": ["call of duty ghosts"],
    "209170": ["call of duty ghosts - multiplayer"],
    "209650": ["call of duty advanced warfare"],
    "209660": ["call of duty advanced warfare - multiplayer"],
}

# Shortcut definitions — must match shortcut.py
SHORTCUTS = {
    "cod4mp": {
        "name":       "Call of Duty 4: Modern Warfare - Multiplayer",
        "exe_name":   "iw3mp.exe",
        "game_appid": "7940",
    },
    "t4mp": {
        "name":       "Call of Duty: World at War - Multiplayer",
        "exe_name":   "CoDWaWmp.exe",
        "game_appid": "10090",
    },
}

def get_deck_serial():
    """Read the Steam Deck serial number from Steam's config.vdf."""
    if not os.path.exists(STEAM_CONFIG):
        return None
    try:
        with open(STEAM_CONFIG, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        match = re.search(r'"SteamDeckRegisteredSerialNumber"\s+"([^"]+)"', content)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None

def find_install_dir(steam_root, appid):
    """Find the install directory for a Steam appid."""
    search_dirs = [os.path.join(steam_root, "steamapps")]
    
    vdf_path = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf_path):
        with open(vdf_path, "r", errors="replace") as f:
            for match in re.findall(r'"path"\s+"([^"]+)"', f.read()):
                search_dirs.append(os.path.join(match, "steamapps"))
                search_dirs.append(os.path.join(match, "SteamLibrary", "steamapps"))
    
    for pattern in ["/run/media/deck/*/SteamLibrary/steamapps", "/run/media/deck/*/steamapps"]:
        search_dirs.extend(glob.glob(pattern))
    
    for steamapps in search_dirs:
        acf = os.path.join(steamapps, f"appmanifest_{appid}.acf")
        if os.path.exists(acf):
            with open(acf, "r", errors="replace") as f:
                match = re.search(r'"installdir"\s+"([^"]+)"', f.read())
                if match:
                    return os.path.join(steamapps, "common", match.group(1))
    return None

def calc_shortcut_appid(exe_path, name):
    """Calculate Steam's shortcut appid from exe path and name."""
    key = (exe_path + name).encode("utf-8")
    crc = binascii.crc32(key) & 0xFFFFFFFF
    return str((crc | 0x80000000) & 0xFFFFFFFF)

def clean_configset(configset_path, keys_to_remove):
    """Remove all matching keys from a configset file."""
    if not os.path.exists(configset_path):
        return False
    
    with open(configset_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    
    original = content
    for key in keys_to_remove:
        pattern = rf'\t"{re.escape(key)}"\n\t\{{[^\}}]*\}}\n?'
        content = re.sub(pattern, "", content, flags=re.MULTILINE)
    
    if content != original:
        with open(configset_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    return False

if not os.path.isdir(USERDATA):
    print("  No Steam userdata found — skipping.")
    exit(0)

# Build list of all appids to remove: Steam appids + dynamic shortcut appids
all_appids = set(MANAGED_STEAM_APPIDS)

for key, info in SHORTCUTS.items():
    install_dir = find_install_dir(STEAM_DIR, info["game_appid"])
    if install_dir:
        exe_path = os.path.join(install_dir, info["exe_name"])
        appid = calc_shortcut_appid(exe_path, info["name"])
        all_appids.add(appid)

# Also find "own" game shortcut appids from shortcuts.vdf
OWN_EXE_MAP = {
    "iw3mp.exe":      "Call of Duty 4: Modern Warfare - Multiplayer",
    "iw3sp.exe":      "Call of Duty 4: Modern Warfare - Singleplayer",
    "iw4mp.exe":      "Call of Duty: Modern Warfare 2 (2009) - Multiplayer",
    "iw4sp.exe":      "Call of Duty: Modern Warfare 2 (2009) - Singleplayer",
    "iw5mp.exe":      "Call of Duty: Modern Warfare 3 (2011) - Multiplayer",
    "iw5sp.exe":      "Call of Duty: Modern Warfare 3 (2011) - Singleplayer",
    "codwaw.exe":     "Call of Duty: World at War",
    "codwawmp.exe":   "Call of Duty: World at War - Multiplayer",
    "blackops.exe":   "Call of Duty: Black Ops",
    "blackopsmp.exe": "Call of Duty: Black Ops - Multiplayer",
    "t6sp.exe":       "Call of Duty: Black Ops II - Singleplayer",
    "t6zm.exe":       "Call of Duty: Black Ops II - Zombies",
    "t6mp.exe":       "Call of Duty: Black Ops II - Multiplayer",
    # Mod client exes (own shortcuts point at these, not original game exes)
    "iw4x.exe":       "Call of Duty: Modern Warfare 2 (2009) - Multiplayer",
    "iw3sp_mod.exe":  "Call of Duty 4: Modern Warfare - Singleplayer",
    # LCD own Plutonium wrapper exes
    "t4plutsp.exe":   "Call of Duty: World at War",
    "t4plutmp.exe":   "Call of Duty: World at War - Multiplayer",
    "t5plutsp.exe":   "Call of Duty: Black Ops",
    "t5plutmp.exe":   "Call of Duty: Black Ops - Multiplayer",
    "t6plutmp.exe":   "Call of Duty: Black Ops II - Multiplayer",
    "t6plutzm.exe":   "Call of Duty: Black Ops II - Zombies",
    "iw5plutmp.exe":  "Call of Duty: Modern Warfare 3 (2011) - Multiplayer",
    "blackops3.exe":  "Call of Duty: Black Ops III",
    "t7x.exe":        "Call of Duty: Black Ops 3 T7x",
}

for uid in os.listdir(USERDATA):
    if not uid.isdigit() or int(uid) < 10000:
        continue
    vdf_path = os.path.join(USERDATA, uid, "config", "shortcuts.vdf")
    if not os.path.exists(vdf_path):
        continue
    try:
        with open(vdf_path, "rb") as f:
            data = f.read()
        for m in re.finditer(b'\x01(?:exe|Exe)\x00([^\x00]+)\x00', data):
            exe_raw = m.group(1).decode("utf-8", errors="replace")
            exe_name = os.path.basename(exe_raw.strip('"')).lower()
            canonical = OWN_EXE_MAP.get(exe_name)
            if canonical:
                # Use exe_raw (with quotes) for appid calc to match Steam
                appid = calc_shortcut_appid(exe_raw, canonical)
                all_appids.add(appid)
    except Exception:
        pass

# Build list of all keys to remove from configset files (appids + named keys)
all_configset_keys = set(all_appids)
for appid in MANAGED_STEAM_APPIDS:
    for named_key in APPID_NAMED_KEYS.get(appid, []):
        all_configset_keys.add(named_key)

# Get Deck serial for serial-specific configset cleanup
deck_serial = get_deck_serial()
if deck_serial:
    print(f"  Deck serial: {deck_serial}")

for uid in os.listdir(USERDATA):
    if not uid.isdigit() or int(uid) < 10000:
        continue
    
    # Path 1: userdata/<uid>/241100/remote/controller_config/<appid>/
    configs_root = os.path.join(USERDATA, uid, "241100", "remote", "controller_config")
    if os.path.isdir(configs_root):
        for appid in all_appids:
            appid_dir = os.path.join(configs_root, appid)
            if os.path.isdir(appid_dir):
                shutil.rmtree(appid_dir)
                print(f"  uid {uid}: removed controller_config for appid {appid}")
    
    # Path 2: Steam Controller Configs/<uid>/config/<appid>/ (used by shortcut.py)
    steam_cfg_root = os.path.join(
        STEAM_DIR, "steamapps", "common",
        "Steam Controller Configs", uid, "config"
    )
    if os.path.isdir(steam_cfg_root):
        for appid in all_appids:
            appid_dir = os.path.join(steam_cfg_root, appid)
            if os.path.isdir(appid_dir):
                shutil.rmtree(appid_dir)
                print(f"  uid {uid}: removed Steam Controller Config for appid {appid}")
        
        # Clean configset files (neptune + serial-specific + all external types)
        configsets_to_clean = [
            "configset_controller_neptune.vdf",
            "configset_controller_steamos_handheld.vdf",
            "configset_controller_ps5.vdf",
            "configset_controller_ps4.vdf",
            "configset_controller_ps5_edge.vdf",
            "configset_controller_xbox360.vdf",
            "configset_controller_xboxone.vdf",
            "configset_controller_xboxelite.vdf",
            "configset_controller_generic.vdf",
            "configset_controller_triton.vdf",
        ]
        if deck_serial:
            configsets_to_clean.append(f"configset_{deck_serial}.vdf")
        
        for configset in configsets_to_clean:
            configset_path = os.path.join(steam_cfg_root, configset)
            if clean_configset(configset_path, all_configset_keys):
                print(f"  uid {uid}: cleaned {configset}")
PYEOF

success "Per-game controller configs removed."
echo ""

echo ""

# ── LCD Plutonium / Heroic cleanup ───────────────────────────────────────────
# Catches LCD-specific residue: wrapper scripts, Steam shortcuts pointing at
# LCD wrappers or the Heroic native flatpak pattern, LCD-specific
# shadercache/artwork keyed on LCD appids, and residual Plutonium data dirs.
# Heroic sideload entries, GamesConfig, staged plutonium.exe, and Heroic
# prefix cleanup are handled earlier in this script.

# ── Scan shortcuts.vdf for LCD shortcut appids (old wrapper + new flatpak) ───

info "Scanning for DeckOps LCD shortcut appids..."

LCD_APPIDS_FILE="$(mktemp)"

if [ -n "$STEAM_ROOT" ] && [ -d "$STEAM_ROOT/userdata" ]; then
python3 - "$STEAM_ROOT" "$LCD_APPIDS_FILE" <<'PYEOF'
import os, re, sys, binascii

steam_root = sys.argv[1]
out_path   = sys.argv[2]
userdata   = os.path.join(steam_root, "userdata")

def calc_shortcut_appid(exe_path, name):
    key = (exe_path + name).encode("utf-8")
    crc = binascii.crc32(key) & 0xFFFFFFFF
    return str((crc | 0x80000000) & 0xFFFFFFFF)

found = set()
if os.path.isdir(userdata):
    for uid in os.listdir(userdata):
        if not uid.isdigit() or int(uid) < 10000:
            continue
        vdf = os.path.join(userdata, uid, "config", "shortcuts.vdf")
        if not os.path.exists(vdf):
            continue
        try:
            with open(vdf, "rb") as f:
                data = f.read()
        except Exception:
            continue

        # Extract AppName + Exe + LaunchOptions by position
        names = [(m.start(), m.group(1).decode("utf-8", "replace"))
                 for m in re.finditer(rb'\x01AppName\x00([^\x00]*)\x00', data)]
        exes = [(m.start(), m.group(1).decode("utf-8", "replace"))
                for m in re.finditer(rb'\x01(?:exe|Exe)\x00([^\x00]*)\x00', data)]
        launch_opts = [(m.start(), m.group(1).decode("utf-8", "replace"))
                       for m in re.finditer(rb'\x01LaunchOptions\x00([^\x00]*)\x00', data)]

        for name_pos, name in names:
            # Find closest following Exe
            best_exe = None
            best_exe_pos = None
            for exe_pos, exe in exes:
                if exe_pos > name_pos:
                    if best_exe_pos is None or exe_pos < best_exe_pos:
                        best_exe_pos = exe_pos
                        best_exe = exe
                    break
            if best_exe is None:
                continue

            exe_clean = best_exe.strip('"')

            # Pattern 1: old wrapper scripts
            if "/lcd_wrappers/plut_" in exe_clean and exe_clean.endswith(".sh"):
                appid = calc_shortcut_appid(best_exe, name)
                found.add(appid)
                continue

            # Pattern 2: old Heroic native (Exe="flatpak", LaunchOptions has heroic://)
            if exe_clean == "flatpak":
                # Find closest following LaunchOptions
                best_lo = None
                for lo_pos, lo in launch_opts:
                    if lo_pos > name_pos:
                        best_lo = lo
                        break
                if best_lo and "heroic://launch" in best_lo:
                    appid = calc_shortcut_appid(best_exe, name)
                    found.add(appid)
                    continue

            # Pattern 3: current Heroic native (Exe="/usr/bin/flatpak", LaunchOptions has heroic://)
            if exe_clean == "/usr/bin/flatpak":
                best_lo = None
                for lo_pos, lo in launch_opts:
                    if lo_pos > name_pos:
                        best_lo = lo
                        break
                if best_lo and "heroic://launch" in best_lo:
                    appid = calc_shortcut_appid(best_exe, name)
                    found.add(appid)

with open(out_path, "w") as f:
    for appid in sorted(found):
        f.write(appid + "\n")

print(f"  Found {len(found)} DeckOps LCD shortcut appid(s)")
PYEOF
fi

LCD_APPID_COUNT=$(wc -l <"$LCD_APPIDS_FILE" 2>/dev/null || echo 0)
if [ "$LCD_APPID_COUNT" -gt 0 ]; then
    success "Found $LCD_APPID_COUNT DeckOps LCD shortcut appid(s)."
else
    skip "No DeckOps LCD shortcut appids found."
fi
echo ""

# ── Remove stale shadercache and grid artwork for LCD appids ─────────────────

if [ -n "$STEAM_ROOT" ] && [ -s "$LCD_APPIDS_FILE" ]; then
    info "Removing LCD shadercache and grid artwork..."
    sc_count=0
    grid_count=0
    while IFS= read -r appid; do
        [ -z "$appid" ] && continue
        sc_dir="$STEAM_ROOT/steamapps/shadercache/$appid"
        if [ -d "$sc_dir" ]; then
            rm -rf "$sc_dir" 2>/dev/null && sc_count=$((sc_count + 1))
        fi
        for uid_dir in "$STEAM_ROOT/userdata"/*/config/grid; do
            [ -d "$uid_dir" ] || continue
            shopt -s nullglob
            for f in "$uid_dir/${appid}"*.{png,jpg,jpeg,webp,ico}; do
                if [ -f "$f" ]; then
                    rm -f "$f" 2>/dev/null && grid_count=$((grid_count + 1))
                fi
            done
            shopt -u nullglob
        done
    done <"$LCD_APPIDS_FILE"
    if [ "$sc_count" -gt 0 ]; then
        success "Removed $sc_count LCD shadercache dir(s)."
    else
        skip "No LCD shadercache dirs."
    fi
    if [ "$grid_count" -gt 0 ]; then
        success "Removed $grid_count LCD grid artwork file(s)."
    else
        skip "No LCD grid artwork."
    fi
else
    skip "No LCD appids for shadercache/grid cleanup."
fi
echo ""

# ── Remove LCD Steam shortcuts from shortcuts.vdf ────────────────────────────

if [ -n "$STEAM_ROOT" ] && [ -d "$STEAM_ROOT/userdata" ]; then
    info "Removing DeckOps LCD shortcuts from Steam..."
python3 - "$STEAM_ROOT" <<'PYEOF'
import os, re, sys

steam_root = sys.argv[1]
userdata   = os.path.join(steam_root, "userdata")

if not os.path.isdir(userdata):
    sys.exit(0)

removed_total = 0
for uid in os.listdir(userdata):
    if not uid.isdigit() or int(uid) < 10000:
        continue
    vdf = os.path.join(userdata, uid, "config", "shortcuts.vdf")
    if not os.path.exists(vdf):
        continue
    try:
        with open(vdf, "rb") as f:
            data = f.read()
    except Exception:
        continue

    if not data.startswith(b'\x00shortcuts\x00'):
        continue

    header = b'\x00shortcuts\x00'
    body = data[len(header):]
    parts = body.split(b'\x08\x08')

    kept = []
    removed_here = 0
    for part in parts:
        if not part:
            kept.append(part)
            continue
        m_exe = re.search(rb'\x01(?:exe|Exe)\x00([^\x00]*)\x00', part)
        if m_exe:
            exe = m_exe.group(1).decode("utf-8", "replace").strip('"')

            # Pattern 1: old wrapper scripts
            if "/lcd_wrappers/plut_" in exe and exe.endswith(".sh"):
                removed_here += 1
                continue

            # Pattern 2: old Heroic native (Exe=flatpak + heroic:// in LaunchOptions)
            if exe == "flatpak":
                m_lo = re.search(rb'\x01LaunchOptions\x00([^\x00]*)\x00', part)
                if m_lo:
                    lo = m_lo.group(1).decode("utf-8", "replace")
                    if "heroic://launch" in lo:
                        removed_here += 1
                        continue

            # Pattern 3: current Heroic native (Exe=/usr/bin/flatpak + heroic:// in LaunchOptions)
            if exe == "/usr/bin/flatpak":
                m_lo = re.search(rb'\x01LaunchOptions\x00([^\x00]*)\x00', part)
                if m_lo:
                    lo = m_lo.group(1).decode("utf-8", "replace")
                    if "heroic://launch" in lo:
                        removed_here += 1
                        continue

        kept.append(part)

    if removed_here == 0:
        continue

    # Reindex remaining entries
    new_parts = []
    idx = 0
    for part in kept:
        if not part:
            new_parts.append(part)
            continue
        new_part = re.sub(rb'^\x00\d+\x00', f'\x00{idx}\x00'.encode(), part, count=1)
        new_parts.append(new_part)
        idx += 1

    new_body = b'\x08\x08'.join(new_parts)
    new_data = header + new_body

    # Backup before writing
    bak = vdf + ".deckops_uninstall.bak"
    if not os.path.exists(bak):
        with open(bak, "wb") as f:
            f.write(data)

    with open(vdf, "wb") as f:
        f.write(new_data)
    removed_total += removed_here
    print(f"  uid {uid}: removed {removed_here} LCD shortcut(s)")

if removed_total > 0:
    print(f"  Total: {removed_total} LCD shortcut(s) removed")
else:
    print("  No DeckOps LCD shortcuts to remove")
PYEOF
    success "LCD shortcut cleanup done."
fi
echo ""

# ── Remove LCD wrapper dir (safety catch) ────────────────────────────────────
# The main DeckOps dir removal earlier (rm -rf ~/.local/share/deckops) should
# already have caught this dir. This is a safety net in case that dir was
# recreated or the earlier removal was skipped.

info "Removing DeckOps LCD wrapper directory..."
WRAPPER_DIR="$HOME/.local/share/deckops/lcd_wrappers"
if [ -d "$WRAPPER_DIR" ]; then
    rm -rf "$WRAPPER_DIR" && success "Removed $WRAPPER_DIR"
else
    skip "Wrapper dir not present."
fi
echo ""

# ── Broad sweep: known Plutonium data dirs ───────────────────────────────────
# Catches dirs outside Wine prefixes that the earlier compatdata walk misses.

info "Sweeping residual Plutonium data dirs..."

SWEEP_ROOTS=(
    "$HOME/.local/share/Plutonium"
    "$HOME/.local/share/plutonium"
    "$HOME/.config/Plutonium"
    "$HOME/.config/plutonium"
    "$HOME/.cache/Plutonium"
    "$HOME/.cache/plutonium"
)

sweep_hits=0
for path in "${SWEEP_ROOTS[@]}"; do
    if [ -e "$path" ]; then
        rm -rf "$path" && success "Removed $path" && sweep_hits=$((sweep_hits + 1))
    fi
done

# /tmp residue
shopt -s nullglob
for f in /tmp/plutonium* /tmp/Plutonium*; do
    if [ -e "$f" ]; then
        rm -rf "$f" 2>/dev/null && sweep_hits=$((sweep_hits + 1))
    fi
done
shopt -u nullglob

if [ "$sweep_hits" -eq 0 ]; then
    skip "No residual Plutonium data dirs."
fi

# Clean up temp file
rm -f "$LCD_APPIDS_FILE" 2>/dev/null

echo ""

# ── Decky plugin ──────────────────────────────────────────────────────────────
info "Removing DeckOps Decky plugin..."

DECKY_PLUGIN_DIR="$HOME/homebrew/plugins/DeckOps"

if [ -d "$DECKY_PLUGIN_DIR" ]; then
    sudo systemctl stop plugin_loader 2>/dev/null
    rm -rf "$DECKY_PLUGIN_DIR"
    success "Decky plugin removed."
    sudo systemctl start plugin_loader 2>/dev/null
else
    skip "Decky plugin not installed."
fi

echo ""

SHORTCUTS=(
    "$HOME/.local/share/applications/deckops-nightly.desktop"
    "$HOME/.local/share/applications/deckops.desktop"
    "$HOME/Desktop/DeckOps-Nightly.desktop"
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

echo -e "${GREEN}${BOLD}  DeckOps fully uninstalled.${CLEAR}"
echo ""
echo "  Your Steam games are untouched."
echo "  All Plutonium data removed from Wine prefixes."
echo "  All LCD HGL state and shortcuts removed."
echo "  All IW3SP-MOD and IW4x client files removed."
echo "  All DeckOps controller templates and profiles removed."
echo ""

info "Uninstall complete — restarting Steam..."
echo ""

# Restart Steam so the cleaned-up shortcuts and configs take effect.
# Launch before the countdown so Steam has time to spin up before the
# terminal window closes.
gtk-launch steam.desktop

# Show summary dialog in background while countdown runs in terminal
zenity --info \
    --title="$APP_TITLE Uninstaller" \
    --text="DeckOps fully uninstalled.\n\nYour Steam games are untouched.\nAll Plutonium data removed from Wine prefixes.\nAll LCD HGL state and shortcuts removed.\nAll IW3SP-MOD and IW4x client files removed.\nAll DeckOps controller templates and profiles removed.\n\nSteam is restarting." \
    --timeout=12 \
    2>/dev/null &

for i in 10 9 8 7 6 5 4 3 2 1; do
    printf "\r  Closing in %d seconds... " "$i"
    sleep 1
done
echo ""
