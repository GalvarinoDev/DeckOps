"""
log.py — DeckOps centralised logging

Provides a single rotating file logger that every module can import.
Only imports from identity.py (which itself has zero internal imports),
so it can still be loaded early without circular-dependency risk.

Usage in any module:

    from log import get_logger
    _log = get_logger(__name__)

    _log.info("prefix created")
    _log.debug("detail: %s", value)
    _log.warning("file missing: %s", path)
    _log.error("operation failed", exc_info=True)

Call setup_logging() once from each entry point (main.py,
launcher_plut_win.py) before any other work.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from identity import LOG_DIR as _LOG_DIR

_LOG_PATH = os.path.join(_LOG_DIR, "install.log")

# 2 MB per file, keep 3 old copies (install.log.1, .2, .3)
_MAX_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 3

_FORMAT = "[%(asctime)s] %(name)s  %(levelname)s  %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

_setup_done = False


def setup_logging(level: int = logging.DEBUG):
    """Initialise the root 'deckops' logger with a rotating file handler
    and a stderr stream handler.  Safe to call more than once (no-op on
    subsequent calls).

    Call this at the top of every entry-point script before any other
    import that might log:

        from log import setup_logging
        setup_logging()
    """
    global _setup_done
    if _setup_done:
        return
    _setup_done = True

    os.makedirs(_LOG_DIR, exist_ok=True)

    root = logging.getLogger("deckops")
    root.setLevel(level)

    # File handler — rotating
    try:
        fh = RotatingFileHandler(
            _LOG_PATH,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FMT))
        root.addHandler(fh)
    except OSError:
        pass  # filesystem issue — fall through to stderr only

    # Stderr handler — visible when running from terminal / SSH
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FMT))
    root.addHandler(sh)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'deckops' namespace.

    Typical call:  _log = get_logger(__name__)
    Produces loggers like 'deckops.shortcut', 'deckops.config', etc.
    """
    # Strip leading package path — we just want the module name
    short = name.rsplit(".", 1)[-1] if "." in name else name
    return logging.getLogger(f"deckops.{short}")
