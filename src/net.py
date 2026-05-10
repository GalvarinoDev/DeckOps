"""
net.py — DeckOps shared network utilities

Provides a reusable download-with-retry helper used by mod client
installers (cod4x, iw3sp, iw4x, cleanops). Centralises the browser
UA string and retry/backoff logic so changes propagate everywhere.
"""

import time
import urllib.request

from log import get_logger

_log = get_logger(__name__)



BROWSER_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
}


class DownloadError(RuntimeError):
    """
    Raised when a download fails after all retries.

    Carries the URL, destination path, and a human-readable label so the
    UI can offer a manual-download fallback dialog with a clickable link
    and a target folder for the user to place the file in.

    Attributes:
        url       -- the URL that failed to download
        dest      -- the local file path the download was targeting
        label     -- human-readable name (e.g. "Plutonium bootstrapper")
    """
    def __init__(self, url: str, dest: str, label: str, cause: Exception):
        self.url   = url
        self.dest  = dest
        self.label = label
        self.cause = cause
        super().__init__(
            f"{label} download failed after retries: {cause}"
        )


def download(url: str, dest: str, on_progress=None, label: str = "",
             timeout: int = 60):
    """
    Download a URL to a local file with chunked progress and retry.

    Reads in 1 MB chunks and reports download percentage via
    on_progress(percent: int, label: str).  Retries up to 3 times
    with exponential backoff on any network error.

    url         — remote URL to fetch
    dest        — local file path to write
    on_progress — optional callback(percent: int, label: str)
    label       — human-readable name shown in progress messages
    timeout     — socket timeout in seconds (default 60)
    """
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=BROWSER_UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                total = int(r.headers.get("Content-Length", 0))
                downloaded = 0
                with open(dest, "wb") as f:
                    while True:
                        chunk = r.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if on_progress and total:
                            on_progress(int(downloaded / total * 100), label)
            return
        except Exception:
            if attempt == 2:
                raise
            _log.debug("download retry %d for %s", attempt + 1, url)
            time.sleep(2 ** attempt)
