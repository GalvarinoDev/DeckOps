"""
main.py — DeckOps entry point

Initialises logging, then runs the bootstrap asset check before
handing off to the PyQt5 UI.
"""

import os
import sys

# Ensure src/ is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log import setup_logging
setup_logging()

from ui_qt import run

if __name__ == "__main__":
    run()
