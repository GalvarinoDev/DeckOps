"""
inhibit.py - keep the device awake during long operations

Installs can run for hours, and a Deck that suspends mid-install leaves
a half-written prefix behind. DeckOps takes two locks: logind blocks
suspend and idle actions (the one that matters in Game Mode), and
org.freedesktop.ScreenSaver blocks the KDE screen locker in Desktop Mode.

Both are best effort. A missing binary, bus or service is never fatal.
"""

import atexit
import subprocess

from log import get_logger

_log = get_logger(__name__)

# Capped so a leaked child process can't keep the machine awake forever.
MAX_HOLD = "6h"

_proc = None
_cookie = None


def _ss_iface():
    from qt import QDBusConnection, QDBusInterface
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return None
    iface = QDBusInterface("org.freedesktop.ScreenSaver",
                           "/org/freedesktop/ScreenSaver",
                           "org.freedesktop.ScreenSaver", bus)
    return iface if iface.isValid() else None


def _ss_inhibit(why):
    try:
        iface = _ss_iface()
        if iface is None:
            return None
        args = iface.call("Inhibit", "DeckOps", why).arguments()
        return args[0] if args else None
    except Exception as ex:
        _log.debug("screensaver inhibit unavailable: %s", ex)
        return None


def _ss_uninhibit(cookie):
    try:
        iface = _ss_iface()
        if iface is not None:
            iface.call("UnInhibit", cookie)
    except Exception as ex:
        _log.debug("screensaver uninhibit failed: %s", ex)


def start(why="DeckOps is installing"):
    """Take the locks. Safe to call when they are already held."""
    global _proc, _cookie
    if _proc is None:
        try:
            # Not detached on purpose. Every other subprocess here uses
            # start_new_session so it outlives DeckOps, but this one has
            # to die with it, or the lock outlasts the install.
            _proc = subprocess.Popen(
                ["systemd-inhibit",
                 "--what=idle:sleep:handle-lid-switch",
                 "--who=DeckOps", f"--why={why}", "--mode=block",
                 "sleep", MAX_HOLD],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _log.info("sleep inhibited (%s)", why)
        except Exception as ex:
            _log.debug("systemd-inhibit unavailable: %s", ex)
            _proc = None
    if _cookie is None:
        _cookie = _ss_inhibit(why)
    return bool(_proc or _cookie)


def stop():
    """Release both locks. Safe to call when nothing is held."""
    global _proc, _cookie
    if _proc is not None:
        try:
            _proc.terminate()
            _proc.wait(timeout=5)
        except Exception:
            try: _proc.kill()
            except Exception: pass
        _proc = None
        _log.info("sleep inhibit released")
    if _cookie is not None:
        _ss_uninhibit(_cookie)
        _cookie = None


atexit.register(stop)
