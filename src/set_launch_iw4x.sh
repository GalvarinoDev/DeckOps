#!/bin/bash
# DeckOps - Sets Steam launch option for MW2 MP (appid 10190)
# Runs iw4x.exe instead of iw4mp.exe via bash substitution.
# Called by iw4x.py while Steam is closed.

echo "DeckOps: Setting MW2 MP launch option..."

~/DeckOps/.venv/bin/python3 - << 'EOF'
import sys, os
sys.path.insert(0, os.path.expanduser('~/DeckOps/src'))
from wrapper import set_launch_options
steam_root = os.path.expanduser('~/.local/share/Steam')
set_launch_options(steam_root, '10190', "bash -c 'exec \"${@/iw4mp.exe/iw4x.exe}\"' -- %command%")
print("Done.")
EOF
