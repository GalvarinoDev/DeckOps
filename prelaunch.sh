#!/bin/bash
# Steam launch option prefix for DeckOps-managed games:
#   bash "<install dir>/prelaunch.sh" <game key> <original command...>
# Updates the game's mod client silently, then starts the game exactly as
# Steam would have. The game always starts, even if the update fails,
# times out or there is no network.

DIR="$(dirname "$(readlink -f "$0")")"

# Steam's launch environment (overlay preload, runtime libraries) is meant
# for the game, not for the host Python, so it is dropped for the check only.
timeout 120 env -u LD_PRELOAD -u LD_LIBRARY_PATH -u PYTHONHOME -u PYTHONPATH \
    "$DIR/.venv/bin/python3" "$DIR/src/prelaunch.py" "$@" >/dev/null 2>&1

shift
# Plutonium Offline menu entry: its file opens the DeckOps Plutonium Offline
# launcher (plutonium.write_offline_menu_file). It runs here, on the host.
for a in "$@"; do
    case "$a" in *plut*_lan.exe) exec bash "$a" ;; esac
done

# Launch menu fallback (plutonium._setup_steam_menu, iw4x): DECKOPS_MENU holds
# "<stock exe>=<online file>" pairs. While our menu is in appinfo.vdf the stock entry
# carries -deckops_vanilla; Steam drops both on a refresh, so an untagged stock exe
# is swapped for its online file, the same command a menu pick would give.
# DECKOPS_MENU_ARGS is added after it (IW4x: --arch x86, like its menu entry).
if [ -n "$DECKOPS_MENU" ]; then
    args=(); tagged=
    for a in "$@"; do
        if [ "$a" = -deckops_vanilla ]; then tagged=1; else args+=("$a"); fi
    done
    [ -n "$tagged" ] && exec "${args[@]}"
    for p in $DECKOPS_MENU; do
        for i in "${!args[@]}"; do
            a=${args[$i]}
            if [ "${a##*/}" = "${p%%=*}" ] && [ -f "${a%/*}/${p#*=}" ]; then
                args[$i]="${a%/*}/${p#*=}"; exec "${args[@]}" $DECKOPS_MENU_ARGS
            fi
        done
    done
fi
exec "$@"
