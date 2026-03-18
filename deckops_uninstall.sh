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

echo ""
echo -e "${BOLD}  DeckOps -- Full Uninstaller${CLEAR}"
echo ""

zenity --question \
    --title="DeckOps Uninstaller" \
    --text="This will clear all DeckOps launch options, remove client files, and remove ALL DeckOps and Plutonium data from your Wine prefixes.\n\nContinue?" \
    --ok-label="Cancel" \
    --cancel-label="Yes, Uninstall" 2>/dev/null

if [ $? -eq 0 ]; then
    zenity --info --title="DeckOps" --text="Uninstall cancelled." 2>/dev/null
    exit 0
fi

echo ""

info "Closing Steam before uninstall..."

# Use pkill targeting the steam binary directly rather than `steam -shutdown`
# which on SteamOS hands control back to Game Mode.
if pgrep -x "steam" > /dev/null 2>&1 || pgrep -f "steam.sh" > /dev/null 2>&1; then
    pkill -TERM -f "steam.sh" 2>/dev/null
    pkill -TERM -x "steam"    2>/dev/null
    # Wait up to 15 seconds for Steam to exit cleanly
    deadline=$((SECONDS + 15))
    while pgrep -x "steam" > /dev/null 2>&1 || pgrep -f "steam.sh" > /dev/null 2>&1; do
        if [ $SECONDS -ge $deadline ]; then
            warn "Steam did not close in time — force killing..."
            pkill -9 -f "steam.sh" 2>/dev/null
            pkill -9 -x "steam"    2>/dev/null
            sleep 2
            break
        fi
        sleep 1
    done
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
    # Only Plutonium games (iw5mp, t4, t5, t6) use exe backups — iw3sp and iw4x
    # now use Steam launch options instead of renaming, so no restore needed there.
    declare -A GAME_EXES=(
        [42690]="iw5mp.exe"
    )
    declare -A GAME_EXES_MULTI=(
        [10090]="CoDWaW.exe CoDWaWmp.exe"
        [42700]="BlackOps.exe BlackOpsMP.exe"
        [202990]="t6mp.exe t6zm.exe"
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

info "Removing DeckOps launch options from localconfig.vdf..."

python3 - << 'PYEOF'
import os, re

# Appids and the launch option strings DeckOps sets
LAUNCH_OPTIONS = {
    "7940":  "bash -c 'exec \"${@/iw3sp.exe/iw3sp_mod.exe}\"' -- %command%",
    "10190": "bash -c 'exec \"${@/iw4mp.exe/iw4x.exe}\"' -- %command%",
}

steam_dir = os.path.expanduser("~/.local/share/Steam")
userdata  = os.path.join(steam_dir, "userdata")

if not os.path.isdir(userdata):
    print("  No Steam userdata found — skipping.")
    exit(0)

def find_block_end(text, start):
    """
    WARNING: Must skip braces inside quoted strings — bash substitutions
    like ${@/iw3sp.exe/iw3sp_mod.exe} contain } that must NOT be counted
    as block delimiters. Failure corrupts localconfig.vdf.
    """
    depth = 0
    i = start
    in_quote = False
    while i < len(text):
        c = text[i]
        if c == '"' and (i == 0 or text[i-1] != '\\'):
            in_quote = not in_quote
        elif not in_quote:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1

for uid in os.listdir(userdata):
    if not uid.isdigit() or int(uid) < 10000:
        continue
    vdf_path = os.path.join(userdata, uid, "config", "localconfig.vdf")
    if not os.path.exists(vdf_path):
        continue

    with open(vdf_path, "r", errors="replace") as f:
        content = f.read()

    modified = False
    for appid, option in LAUNCH_OPTIONS.items():
        key_match = re.search(r'"' + re.escape(appid) + r'"\s*\{', content, re.IGNORECASE)
        if not key_match:
            continue

        app_open  = key_match.end() - 1
        app_close = find_block_end(content, app_open)
        if app_close == -1:
            continue

        app_inner = content[app_open + 1:app_close]

        # Only remove from the flat block (before any sub-blocks)
        # Steam reads LaunchOptions from the flat block, not sub-blocks.
        subblock_match = re.search(r'"[^"]+"\s*\{', app_inner)
        flat_section = app_inner[:subblock_match.start()] if subblock_match else app_inner

        launch_pattern = re.compile(r'"LaunchOptions"\s*"[^"]*"', re.IGNORECASE)
        if re.search(launch_pattern, flat_section) and option in flat_section:
            new_flat = launch_pattern.sub('', flat_section)
            if subblock_match:
                new_app_inner = new_flat + app_inner[subblock_match.start():]
            else:
                new_app_inner = new_flat
            content = content[:app_open + 1] + new_app_inner + content[app_close:]
            modified = True
            print(f"  uid {uid}: cleared launch option for appid {appid}")

    if modified:
        with open(vdf_path, "w", errors="replace") as f:
            f.write(content)
    else:
        print(f"  uid {uid}: no DeckOps launch options found")
PYEOF

echo ""

if [ -n "$STEAM_ROOT" ]; then
    COMPATDATA="$STEAM_ROOT/steamapps/compatdata"
    if [ -d "$COMPATDATA" ]; then
        found_any=0
        for prefix_dir in "$COMPATDATA"/*/; do
            plut_dir="$prefix_dir/pfx/drive_c/users/steamuser/AppData/Local/Plutonium"
            if [ -d "$plut_dir" ]; then
                prefix_id=$(basename "$prefix_dir")
                rm -rf "$plut_dir" && success "Removed Plutonium from prefix $prefix_id" || warn "Failed to remove Plutonium from prefix $prefix_id"
                found_any=1
            fi
        done
        [ "$found_any" -eq 0 ] && skip "No Plutonium folders found in any prefix"
    else
        skip "compatdata directory not found"
    fi

    for appid in 42690 10090 42700 202990; do
        game_dir=$(find_install_dir "$appid") || true
        if [ -n "$game_dir" ] && [ -f "$game_dir/deckops_plutonium.json" ]; then
            rm -f "$game_dir/deckops_plutonium.json" && success "Removed DeckOps metadata for appid $appid" || warn "Failed to remove metadata for appid $appid"
        fi
    done
fi
echo ""

info "Stopping any leftover DeckOps audio..."
pkill -f "mpv" 2>/dev/null && success "mpv stopped" || skip "No audio process found"
echo ""

info "Removing DeckOps install directory and config..."

DECKOPS_DIRS=(
    "$HOME/DeckOps"
    "$HOME/.local/share/deckops"
    "$HOME/.config/deckops"
    "$HOME/.local/share/deckops/plutonium_prefix"
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

remove_steam_shortcuts() {
    python3 - << 'PYEOF'
import os, struct

SHORTCUT_NAMES = {
    "Call of Duty 4: Modern Warfare - Multiplayer",
    "Call of Duty: World at War - Multiplayer",
    "DeckOps",
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

    # Walk entries manually
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
        # Find end of entry: \x08 followed by next \x00 or outer \x08
        # Scan forward for \x08 that ends this entry
        depth = 1
        scan  = entry_body_start
        while scan < len(raw_entries) and depth > 0:
            b = raw_entries[scan:scan+1]
            if b == b'\x00':
                # dict start: read key, skip to value
                k_end = raw_entries.index(b'\x00', scan + 1)
                scan = k_end + 1
                depth += 1
            elif b == b'\x08':
                depth -= 1
                scan += 1
            else:
                # typed field
                ftype = raw_entries[scan]
                scan += 1
                k_end = raw_entries.index(b'\x00', scan)
                scan = k_end + 1
                if ftype == 1:   # string
                    v_end = raw_entries.index(b'\x00', scan)
                    scan = v_end + 1
                elif ftype == 2:  # int32
                    scan += 4
                else:
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

    new_data = header + b''.join(kept) + b'\x08\x08'
    with open(vdf_path, "wb") as f:
        f.write(new_data)
    print(f"  uid {uid}: shortcuts.vdf updated ({removed} removed)")

PYEOF
}

remove_steam_shortcuts && success "Steam shortcuts cleaned up." || warn "Could not clean Steam shortcuts — remove manually if needed."
echo ""

info "Removing non-Steam shortcut artwork from Steam grid..."

python3 - << 'PYEOF'
import os, re, binascii, glob

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

if not shortcut_appids:
    print("  No shortcut appids to clean up.")
    exit(0)

# Remove artwork files matching these appids
for uid in os.listdir(userdata):
    if not uid.isdigit() or int(uid) < 10000:
        continue
    grid_dir = os.path.join(userdata, uid, "config", "grid")
    if not os.path.isdir(grid_dir):
        continue
    for f in os.listdir(grid_dir):
        for appid in shortcut_appids:
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
    "controller_neptune_deckops_other_hold.vdf" \
    "controller_neptune_deckops_other_toggle.vdf" \
    "controller_neptune_deckops_other.vdf"; do
    target="$TEMPLATE_DIR/$f"
    if [ -f "$target" ]; then
        rm -f "$target" && success "Removed $f" || warn "Failed to remove $f"
    else
        skip "$f not found"
    fi
done
echo ""

info "Removing per-game controller configs..."

python3 - << 'PYEOF'
import os, shutil, re, binascii, glob

STEAM_DIR = os.path.expanduser("~/.local/share/Steam")
USERDATA  = os.path.join(STEAM_DIR, "userdata")
STEAM_CONFIG = os.path.join(STEAM_DIR, "config", "config.vdf")

# Standard Steam appids managed by DeckOps
MANAGED_STEAM_APPIDS = [
    "7940", "10090", "10180", "10190", "42680", "42690",
    "42700", "42710", "202970", "202990", "212910",
]

# Named game keys used in configset files — must match controller_profiles.py
APPID_NAMED_KEYS = {
    "7940":   ["call of duty 4 modern warfare (2007)"],
    "10090":  ["call of duty world at war",
               "call of duty world at war - multiplayer"],
    "10180":  ["call of duty modern warfare 2 (2009) - multiplayer"],
    "10190":  ["call of duty modern warfare 2 (2009) - multiplayer"],
    "42680":  ["call of duty modern warfare 3 - multiplayer"],
    "42690":  ["call of duty modern warfare 3 - multiplayer"],
    "42700":  ["call of duty black ops",
               "call of duty black ops - zombies"],
    "42710":  ["call of duty black ops - multiplayer"],
    "202970": [],
    "202990": ["call of duty black ops ii - multiplayer"],
    "212910": ["call of duty black ops ii - zombies"],
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
        
        # Clean configset files (neptune + serial-specific)
        configsets_to_clean = ["configset_controller_neptune.vdf"]
        if deck_serial:
            configsets_to_clean.append(f"configset_{deck_serial}.vdf")
        
        for configset in configsets_to_clean:
            configset_path = os.path.join(steam_cfg_root, configset)
            if clean_configset(configset_path, all_configset_keys):
                print(f"  uid {uid}: cleaned {configset}")
PYEOF

success "Per-game controller configs removed."
echo ""

info "Removing DeckOps CompatToolMapping entries from Steam config..."

python3 - << 'PYEOF'
import os, re, binascii, glob

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

# Standard Steam appids managed by DeckOps
MANAGED_STEAM_APPIDS = [
    "7940", "10090", "10180", "10190", "42680", "42690",
    "42700", "42710", "202970", "202990", "212910",
]

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

STEAM_CONFIG = os.path.expanduser("~/.local/share/Steam/config/config.vdf")
steam_root   = os.path.expanduser("~/.local/share/Steam")

if not os.path.exists(STEAM_CONFIG):
    print("  Steam config.vdf not found — skipping.")
    exit(0)

# Build list of all appids to remove: Steam appids + dynamic shortcut appids
all_appids = set(MANAGED_STEAM_APPIDS)

for key, info in SHORTCUTS.items():
    install_dir = find_install_dir(steam_root, info["game_appid"])
    if install_dir:
        exe_path = os.path.join(install_dir, info["exe_name"])
        appid = calc_shortcut_appid(exe_path, info["name"])
        all_appids.add(appid)

with open(STEAM_CONFIG, "r", encoding="utf-8") as f:
    data = f.read()

original = data
for appid in all_appids:
    pattern = rf'\t+"{re.escape(appid)}"\n\t+\{{[^}}]*\}}\n?'
    data = re.sub(pattern, "", data, flags=re.MULTILINE)

if data != original:
    with open(STEAM_CONFIG, "w", encoding="utf-8") as f:
        f.write(data)
    print("  CompatToolMapping entries removed from config.vdf")
else:
    print("  No DeckOps CompatToolMapping entries found")
PYEOF

echo ""

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

echo -e "${GREEN}${BOLD}  DeckOps fully uninstalled.${CLEAR}"
echo ""
echo "  Your Steam games are untouched. Steam launch options cleared."
echo "  All Plutonium data removed from Wine prefixes."
echo "  All IW3SP-MOD and IW4x client files removed."
echo "  All DeckOps controller templates and profiles removed."
echo ""

info "Relaunching Steam..."
nohup "$HOME/.local/share/Steam/steam.sh" > /dev/null 2>&1 &
success "Steam is starting."
echo ""

# Show summary dialog in background while countdown runs in terminal
zenity --info \
    --title="DeckOps Uninstaller" \
    --text="DeckOps fully uninstalled.\n\nYour Steam games are untouched. Steam launch options cleared.\nAll Plutonium data removed from Wine prefixes.\nAll IW3SP-MOD and IW4x client files removed.\nAll DeckOps controller templates and profiles removed." \
    --timeout=6 \
    2>/dev/null &

for i in 5 4 3 2 1; do
    printf "\r  Closing in %d seconds..." "$i"
    sleep 1
done
echo ""
