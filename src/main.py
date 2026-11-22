"""
main.py: DeckOps entry point.

Sets up logging, then hands off to the Qt UI, which runs the
bootstrap asset check first.
"""

import os
import sys

# Put src/ on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log import setup_logging, get_logger
setup_logging()


def _ensure_qt6():
    # Updates only copy files, so venvs made before the PyQt6 move still
    # have PyQt5 alone. Any failure leaves the app on PyQt5 (qt.py).
    try:
        import PyQt6.QtWidgets  # noqa: F401
        return
    except ImportError:
        pass
    import shutil, subprocess
    log = get_logger(__name__)
    venv = os.path.dirname(os.path.dirname(sys.executable))
    pip = os.path.join(venv, "bin", "pip")
    # Set when the wheel installed but could not open a window here
    marker = os.path.join(venv, ".qt6_unsupported")
    if not os.path.exists(pip) or os.path.exists(marker):
        return
    z = None
    if shutil.which("zenity"):
        z = subprocess.Popen(["zenity", "--progress", "--pulsate", "--no-cancel", "--auto-close",
                              "--title=DeckOps", "--text=Updating DeckOps components...", "--width=320"],
                             stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        ok = subprocess.run([pip, "install", "--quiet", "--disable-pip-version-check", "PyQt6"],
                            capture_output=True, timeout=900).returncode == 0
        # A wheel that installs but can't load the platform plugin would abort the app, so test it in a child process first
        if ok and subprocess.run([sys.executable, "-c", "from PyQt6.QtWidgets import QApplication; QApplication([])"],
                                 capture_output=True, timeout=60).returncode != 0:
            subprocess.run([pip, "uninstall", "-y", "-q", "PyQt6", "PyQt6-Qt6", "PyQt6-sip"], capture_output=True)
            open(marker, "w").close()
            log.warning("PyQt6 installed but could not open a window, staying on PyQt5")
            return
        if ok:
            import importlib; importlib.invalidate_caches()
        log.info("PyQt6 installed" if ok else "PyQt6 install failed, staying on PyQt5 (retry next launch)")
    except Exception as ex:
        log.warning("PyQt6 install skipped: %s", ex)
    finally:
        if z:
            z.stdin.close(); z.terminate()


_ensure_qt6()

from ui_qt import run

if __name__ == "__main__":
    run()
