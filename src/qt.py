"""
qt.py - Qt import shim

Loads PyQt6 when the venv has it, else PyQt5. UI code imports from here
and uses only names that work in both (fully scoped enums, exec()).
Keep the PyQt5 branch: venvs where the PyQt6 install failed still run on it.
"""

try:
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *
    from PyQt6.QtWidgets import *
    QT6 = True
except ImportError:
    from PyQt5.QtCore import *
    from PyQt5.QtGui import *
    from PyQt5.QtWidgets import *
    QT6 = False

# QtDBus is optional; inhibit.py treats a missing name as "no screensaver bus"
try:
    if QT6:
        from PyQt6.QtDBus import *
    else:
        from PyQt5.QtDBus import *
except ImportError:
    pass
