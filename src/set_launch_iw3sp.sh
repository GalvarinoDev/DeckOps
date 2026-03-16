#!/bin/bash
# DeckOps - Sets Steam launch option for CoD4 SP (appid 7940)
# Runs iw3sp_mod.exe instead of iw3sp.exe via bash substitution.
# Called by iw3sp.py while Steam is closed.

echo "DeckOps: Setting CoD4 SP launch option..."

~/DeckOps/.venv/bin/python3 - << 'EOF'
import sys, os
sys.path.insert(0, os.path.expanduser('~/DeckOps/src'))
from wrapper import set_launch_options
steam_root = os.path.expanduser('~/.local/share/Steam')
set_launch_options(steam_root, '7940', "bash -c 'exec \"${@/iw3sp.exe/iw3sp_mod.exe}\"' -- %command%")
print("Done.")
EOF
