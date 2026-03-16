#!/bin/bash
# Sets the Steam launch option for MW2 MP (appid 10190) to run iw4x.exe
# Called by iw4x.py after installation while Steam is closed.

VENV_PYTHON="$HOME/DeckOps/.venv/bin/python3"
SRC_DIR="$HOME/DeckOps/src"

"$VENV_PYTHON" - << 'EOF'
import sys, os
sys.path.insert(0, os.path.expanduser('~/DeckOps/src'))
from wrapper import set_launch_options
steam_root = os.path.expanduser('~/.local/share/Steam')
set_launch_options(steam_root, '10190', "bash -c 'exec \"${@/iw4mp.exe/iw4x.exe}\"' -- %command%")
EOF
