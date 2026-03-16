#!/bin/bash
# Sets the Steam launch option for CoD4 SP (appid 7940) to run iw3sp_mod.exe
# Called by iw3sp.py after installation while Steam is closed.

VENV_PYTHON="$HOME/DeckOps/.venv/bin/python3"
SRC_DIR="$HOME/DeckOps/src"

"$VENV_PYTHON" - << 'EOF'
import sys, os
sys.path.insert(0, os.path.expanduser('~/DeckOps/src'))
from wrapper import set_launch_options
steam_root = os.path.expanduser('~/.local/share/Steam')
set_launch_options(steam_root, '7940', "bash -c 'exec \"${@/iw3sp.exe/iw3sp_mod.exe}\"' -- %command%")
EOF
