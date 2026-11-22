#!/bin/bash
# DeckOps offline launch for Plutonium games, run by each game's offline script
# (DeckOps_Offline.exe through launcher_offline.sh). Always on the host.
# The game runs from DeckOps' offline Plutonium copy in its own prefix, inside Steam
# Linux Runtime like Steam's own launches: straight on the host, BO2 stalls in Game Mode
# until its console window is switched to (Deck, 2026-10-08).
# WaW MP, BO1 MP, BO2 MP and MW3 MP also host a hidden local dedicated server and join it: plain -lan
# play can't create a private match without a Plutonium account.
# Usage: lan_server.sh <mode> <game dir, game prefix> +name "<player>" [<port> <game dir, server prefix> <server args...>]
# Extra game args: CLIENT_ARGS (word-split, no spaces inside an arg).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
J="$PROJECT_ROOT/deckops.json"
read -r GE SR < <(python3 -c "import json;d=json.load(open('$J'));print(d.get('ge_proton_version',''),d.get('steam_root',''))" 2>/dev/null)
PR="$SR/compatibilitytools.d/$GE/proton"
# Game and server need different prefixes: the game's waitforexitandrun waits for
# every wineserver on its prefix. The server uses the Offline launcher's prefix.
GP="$HOME/.local/share/deckops/lan_prefix"
SP="$HOME/.local/share/deckops/launcher_prefix"
MODE=$1 GAME=$2 NAME=$4; shift 4
PORT=$1 SGAME=$2; [ $# -ge 2 ] && shift 2
SV="$HOME/.local/share/deckops/lan/$MODE/server"
CL="$HOME/.local/share/deckops/lan/$MODE/client"
UNIT="deckops-lan-$MODE"

mkdir -p "$PROJECT_ROOT/logs"
exec >"$PROJECT_ROOT/logs/lan_$MODE.log" 2>&1
echo "$(date +%T) start $MODE $GAME${PORT:+, server on port $PORT: $*}"
[ -x "$PR" ] || { echo "Proton not found: $PR"; exit 1; }
# Relink the offline copies so mods added and Plutonium files updated since the install
# show up, and get the Steam Linux Runtime and the library mounts back.
# Steam's launch environment is meant for the game, not the host Python (as in prelaunch.sh).
IFS=$'\t' read -r SLR MOUNTS < <(timeout 60 env -u LD_PRELOAD -u LD_LIBRARY_PATH -u PYTHONHOME -u PYTHONPATH \
  "$PROJECT_ROOT/.venv/bin/python3" "$PROJECT_ROOT/src/prelaunch.py" lan "$MODE" 2>/dev/null)
echo "runtime: ${SLR:-none, running on the host}  mounts: ${MOUNTS:-none}"
[ -d "$CL" ] && { [ -z "$PORT" ] || [ -d "$SV" ]; } || { echo "Offline folders missing, add Offline Mode again in DeckOps"; exit 1; }

export STEAM_COMPAT_CLIENT_INSTALL_PATH="$SR"
# Steam's Stop button sends TERM: take the server down with the game
trap 'systemctl --user stop "$UNIT" 2>/dev/null' EXIT

# ---
# Server

CONNECT=()
if [ -n "$PORT" ]; then
  # Plutonium MW3 has no GSC file I/O: its menu logs every class save as DCAC;class;<guid>;<n>;<picks> and
  # the class in use as DCAC;use;<guid>;<n or ->. The last of each per player comes back here as dvars,
  # ahead of the map rotation.
  if [ "$MODE" = iw5mp ]; then
    SAVED=()
    while IFS=';' read -r _ T G A B; do
      case $T in
        class) SAVED+=(+set "dcac_${G}_$A" "$B") ;;
        use) SAVED+=(+set "dcac_use_$G" "$A") ;;
      esac
    done < <(grep -a -o 'DCAC;class;[^;]*;[0-4];[^;]*\|DCAC;use;[^;]*;[-0-4]' "$SV/storage/iw5/games_mp.log" 2>/dev/null \
      | awk -F';' '{k = $2 ";" $3; if ($2 == "class") k = k ";" $4; l[k] = $0} END {for (k in l) print l[k]}')
    set -- "${SAVED[@]}" "$@"
  fi
  # A random first map each start, then the normal rotation: base-game maps for BO1, BO2 and MW3 (DLC may be
  # missing), any installed map for WaW. Only maps installed here (dcac_maps) are picked.
  case $MODE in
    t4mp) POOL= ROT="gametype tdm map" ;;
    t5mp) POOL="mp_array mp_cracked mp_crisis mp_firingrange mp_duga mp_hanoi mp_cairo mp_havoc mp_cosmodrome mp_nuked mp_radiation mp_mountain mp_villa mp_russianbase" ROT="gametype tdm map" ;;
    t6mp) POOL="mp_la mp_dockside mp_carrier mp_drone mp_express mp_hijacked mp_meltdown mp_overflow mp_nightclub mp_raid mp_slums mp_village mp_turbine mp_socotra mp_nuketown_2020" ROT="execgts tdm.cfg map" ;;
    iw5mp) POOL="mp_alpha mp_bootleg mp_bravo mp_carbon mp_dome mp_exchange mp_hardhat mp_interchange mp_lambeth mp_mogadishu mp_paris mp_plaza2 mp_radar mp_seatown mp_underground mp_village" ROT="dsr TDM_default map" ;;
  esac
  HAVE=; PREV=; for a in "$@"; do [ "$PREV" = dcac_maps ] && HAVE=$a; PREV=$a; done
  MAP=$(if [ -z "$POOL" ]; then tr , '\n' <<<"$HAVE"; elif [ -z "$HAVE" ]; then tr ' ' '\n' <<<"$POOL"
    else tr ' ' '\n' <<<"$POOL" | grep -xF -f <(tr , '\n' <<<"$HAVE"); fi | grep . | shuf -n1)
  if [ -n "$MAP" ]; then
    ARGS=()
    for a in "$@"; do
      if [ "$a" = +map_rotate ] || [ "$a" = +start_map_rotate ]; then ARGS+=(+set sv_maprotationcurrent "$ROT $MAP"); fi
      ARGS+=("$a")
    done
    set -- "${ARGS[@]}"
  fi
  if ! ss -uln | grep -q ":$PORT "; then
    # A unit left over from an interrupted run blocks systemd-run from reusing the name
    systemctl --user stop "$UNIT" 2>/dev/null; systemctl --user reset-failed "$UNIT" 2>/dev/null
    # Started through systemd-run: a headless server stalls under Proton, and in Game Mode this keeps
    # its window out of the Steam launch so gamescope never focuses it. Game Mode's systemd user
    # environment has no DISPLAY, so the display is passed in.
    systemd-run --user --collect --unit="$UNIT" -p TimeoutStopSec=10 -E DISPLAY="${DISPLAY:-:0}" \
      -E WAYLAND_DISPLAY="$WAYLAND_DISPLAY" -E GAMESCOPE_WAYLAND_DISPLAY="$GAMESCOPE_WAYLAND_DISPLAY" \
      -E XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
      -E STEAM_COMPAT_DATA_PATH="$SP" -E STEAM_COMPAT_CLIENT_INSTALL_PATH="$SR" \
      --working-directory="$SV" \
      "$PR" run "$SV/bin/plutonium-bootstrapper-win32.exe" "$MODE" "$SGAME" -lan -dedicated +set net_port "$PORT" "$@" \
      || { echo "server failed to start"; exit 1; }
    for i in $(seq 180); do ss -uln | grep -q ":$PORT " && break; sleep 1; done
    echo "$(date +%T) server listening after ${i}s"
  fi
  # The port opens before the map has loaded, and WaW drops a +connect sent then (PC, 2026-10-09).
  # A server only answers getstatus once its map is up. MW3's never answers getstatus (a fixed 60 s wait), only getinfo.
  Q=getstatus; [ "$MODE" = iw5mp ] && Q=getinfo
  ready() { exec 3<>"/dev/udp/127.0.0.1/$PORT" || return 1; printf '\xff\xff\xff\xff%s' "$Q" >&3
    timeout 1 head -c4 <&3 >/dev/null; local r=$?; exec 3<&-; return $r; }
  for i in $(seq 60); do ready && break; done
  echo "$(date +%T) server map up after ${i} tries"
  CONNECT=(+set deckops_lan_port "$PORT" +connect "127.0.0.1:$PORT")
fi

# ---
# Game

cd "$CL" || exit 1
export STEAM_COMPAT_DATA_PATH="$GP" STEAM_COMPAT_MOUNTS="$MOUNTS"
# Steam's own launch: the runtime's entry point, then proton waitforexitandrun
if [ -n "$SLR" ]; then RUN=("$SLR/_v2-entry-point" --verb=waitforexitandrun -- "$PR" waitforexitandrun); else RUN=("$PR" run); fi
# Plutonium's own launcher passes a fresh random -token even in LAN mode
TOKEN=$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')
# Returns when the game exits; staying alive here also keeps the Steam session open
"${RUN[@]}" "$CL/bin/plutonium-bootstrapper-win32.exe" "$MODE" "$GAME" -token "$TOKEN" -lan +name "$NAME" \
  $CLIENT_ARGS "${CONNECT[@]}"
echo "$(date +%T) game closed${PORT:+, stopping server}"
