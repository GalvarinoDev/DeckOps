#!/bin/bash
# launcher_offline.sh - DeckOps Plutonium Offline Launcher wrapper
#
# Entry point for the non-Steam shortcut. Runs DeckOps_Offline.exe inside
# Proton (for XInput gamepad support), then reads an intent file written
# by the exe to find out which game to launch. If it finds an intent, it
# execs the game's LAN wrapper script, which uses the right per-game
# Proton prefix.
#
# Process chain (from Steam's perspective):
#   Steam -> launcher_offline.sh -> proton run DeckOps_Offline.exe (UI)
#                                -> exe exits, writes .lan_intent.json
#                                -> exec bash <lan_wrapper_path>
#                                -> lan wrapper execs proton run bootstrapper
#
# Steam sees launcher_offline.sh as the running process the entire time.
# The final exec replaces this shell with Proton running the game, so
# Steam tracks it correctly and shows the game as running.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# assets/LAN/launcher_offline.sh -> two levels up -> DeckOps[-Nightly]/
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

DECKOPS_JSON="$PROJECT_ROOT/deckops.json"
INTENT_FILE="$PROJECT_ROOT/.lan_intent.json"
LAUNCHER_EXE="$SCRIPT_DIR/DeckOps_Offline.exe"

# --- Read config

if [ ! -f "$DECKOPS_JSON" ]; then
    echo "ERROR: deckops.json not found at $DECKOPS_JSON" >&2
    exit 1
fi

# Parse GE-Proton version and Steam root from deckops.json
GE_VERSION=$(python3 -c "
import json, sys
try:
    with open('$DECKOPS_JSON') as f:
        d = json.load(f)
    print(d.get('ge_proton_version', ''))
except Exception:
    pass
" 2>/dev/null)

STEAM_ROOT=$(python3 -c "
import json, sys
try:
    with open('$DECKOPS_JSON') as f:
        d = json.load(f)
    print(d.get('steam_root', ''))
except Exception:
    pass
" 2>/dev/null)

if [ -z "$GE_VERSION" ] || [ -z "$STEAM_ROOT" ]; then
    echo "ERROR: Could not read ge_proton_version or steam_root from deckops.json" >&2
    exit 1
fi

PROTON_PATH="$STEAM_ROOT/compatibilitytools.d/$GE_VERSION/proton"

if [ ! -f "$PROTON_PATH" ]; then
    echo "ERROR: Proton not found at $PROTON_PATH" >&2
    exit 1
fi

if [ ! -f "$LAUNCHER_EXE" ]; then
    echo "ERROR: Launcher exe not found at $LAUNCHER_EXE" >&2
    exit 1
fi

# --- Clean up stale intent file

rm -f "$INTENT_FILE"

# --- Determine STEAM_COMPAT_DATA_PATH for the launcher exe
# The exe needs a Wine prefix. A fixed one under the DeckOps data directory
# survives reinstalls and does not depend on Steam shortcut appids, which
# change when the exe path changes.

LAUNCHER_PREFIX="$HOME/.local/share/deckops/launcher_prefix"
mkdir -p "$LAUNCHER_PREFIX"

export STEAM_COMPAT_DATA_PATH="$LAUNCHER_PREFIX"
export STEAM_COMPAT_CLIENT_INSTALL_PATH="$STEAM_ROOT"

# --- Launch the UI
# Run the exe inside Proton. The exe shows the game selection UI and
# writes .lan_intent.json when the user picks a game, then exits.
# PROTON_NO_FSYNC/ESYNC prevents hangs on older kernels.

PROTON_NO_FSYNC=1 PROTON_NO_ESYNC=1 "$PROTON_PATH" run "$LAUNCHER_EXE" "$@"

# --- Check for launch intent

if [ ! -f "$INTENT_FILE" ]; then
    # User quit without selecting a game
    exit 0
fi

# Read the lan_wrapper_path from the intent file
LAN_WRAPPER=$(python3 -c "
import json, sys
try:
    with open('$INTENT_FILE') as f:
        d = json.load(f)
    print(d.get('lan_wrapper_path', ''))
except Exception:
    pass
" 2>/dev/null)

# Clean up intent file
rm -f "$INTENT_FILE"

if [ -z "$LAN_WRAPPER" ]; then
    echo "ERROR: No lan_wrapper_path in intent file" >&2
    exit 1
fi

if [ ! -f "$LAN_WRAPPER" ]; then
    echo "ERROR: LAN wrapper not found: $LAN_WRAPPER" >&2
    exit 1
fi

# --- Launch the game
# exec replaces this shell with bash running the LAN wrapper. The wrapper
# in turn execs proton run bootstrapper, so the last process is Proton
# running the game, and Steam tracks it as the original shortcut.

exec bash "$LAN_WRAPPER"
