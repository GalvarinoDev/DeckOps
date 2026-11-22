"""
log.py: DeckOps centralised logging

One rotating file logger that every module can import. It imports only
identity.py, which has no internal imports, so it loads early without
circular-import risk.

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
import re
from logging.handlers import RotatingFileHandler

from identity import LOG_DIR as _LOG_DIR

_LOG_PATH = os.path.join(_LOG_DIR, "install.log")

# 2 MB per file, keep 3 old copies (install.log.1, .2, .3)
_MAX_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 3

_FORMAT = "[%(asctime)s] %(name)s  %(levelname)s  %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

_setup_done = False

# Logs get pasted publicly (Copy Log -> Discord), so personal data is masked
# on the way out: Linux user name (home and media paths, native and Wine),
# Steam account name, Steam account IDs, Deck serial. Path structure stays.
_REDACT = [
    (re.compile(r"(?:/var)?/home/[^/\s'\"]+"), "~"),
    (re.compile(r"([A-Za-z]:\\+)(?:var\\+)?home\\+[^\\\s'\"]+"), r"\1~"),
    (re.compile(r"(/(?:run/)?media/)[^/\s'\"]+"), r"\1<user>"),
    (re.compile(r"(-username\s+)\S+"), r"\1***"),
    (re.compile(r"(Logging ')[^']+(' into Steam3)"), r"\1***\2"),
    (re.compile(r"((?:userdata|Steam Controller Configs)[/\\]+)\d+"), r"\1<uid>"),
    (re.compile(r"\b((?:uid|user) )\d{3,}\b"), r"\1<uid>"),
    (re.compile(r"(configset_)(?!controller_)[^./\s'\"]+(\.vdf)"), r"\1<serial>\2"),
]
_secrets = set()


def redact_also(word: str):
    """Mask this exact word in all later log output (e.g. a captured Steam
    account name). Ignored under 3 chars to avoid masking ordinary text."""
    if word and len(word) >= 3:
        _secrets.add(re.escape(word))


def redact(text: str) -> str:
    for pat, rep in _REDACT:
        text = pat.sub(rep, text)
    if _secrets:
        text = re.sub(r"\b(?:" + "|".join(_secrets) + r")\b", "***", text)
    return text


class _RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


def _scrub_old_logs():
    # One-time pass over logs written before masking existed.
    marker = os.path.join(_LOG_DIR, ".masked")
    if os.path.exists(marker):
        return
    for p in [_LOG_PATH] + [f"{_LOG_PATH}.{i}" for i in range(1, _BACKUP_COUNT + 1)]:
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                text = f.read()
            with open(p, "w", encoding="utf-8") as f:
                f.write(redact(text))
        except OSError:
            pass
    try:
        open(marker, "w").close()
    except OSError:
        pass


def setup_logging(level: int = logging.DEBUG):
    """Set up the 'deckops' logger with a rotating file handler and a
    stderr handler. Later calls do nothing.

    Call it at the top of every entry point, before any import that
    might log:

        from log import setup_logging
        setup_logging()
    """
    global _setup_done
    if _setup_done:
        return
    _setup_done = True

    os.makedirs(_LOG_DIR, exist_ok=True)
    _scrub_old_logs()

    root = logging.getLogger("deckops")
    root.setLevel(level)

    # Rotating file handler
    try:
        fh = RotatingFileHandler(
            _LOG_PATH,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(_RedactingFormatter(_FORMAT, datefmt=_DATE_FMT))
        root.addHandler(fh)
    except OSError:
        pass  # filesystem issue, stderr only

    # Stderr handler, visible when running from a terminal or SSH
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(_RedactingFormatter(_FORMAT, datefmt=_DATE_FMT))
    root.addHandler(sh)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'deckops' namespace.

    Typical call:  _log = get_logger(__name__)
    Produces loggers like 'deckops.shortcut', 'deckops.config', etc.
    """
    # Keep only the module name, drop the package path
    short = name.rsplit(".", 1)[-1] if "." in name else name
    return logging.getLogger(f"deckops.{short}")
