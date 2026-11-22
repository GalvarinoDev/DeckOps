"""
net.py: DeckOps shared network utilities

Provides a reusable download-with-retry helper used by mod client
installers (cod4x, iw3sp, iw4x, cleanops). Keeps the browser UA string
and retry/backoff logic in one place.
"""

import hashlib
import io
import json
import os
import time
import urllib.request
import zipfile

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
        url:   the URL that failed to download
        dest:  the local file path the download was targeting
        label: human-readable name (e.g. "Plutonium bootstrapper")
    """
    def __init__(self, url: str, dest: str, label: str, cause: Exception):
        self.url   = url
        self.dest  = dest
        self.label = label
        self.cause = cause
        super().__init__(
            f"{label} download failed after retries: {cause}"
        )


CHUNK      = 1024 * 1024
UPDATE_HZ  = 4          # cap on progress callbacks per second


def _fmt_size(n: int) -> str:
    if n >= 1 << 30: return f"{n / (1 << 30):.1f} GB"
    if n >= 100 << 20: return f"{n / (1 << 20):.0f} MB"
    if n >= 1 << 20: return f"{n / (1 << 20):.1f} MB"
    if n >= 1 << 10: return f"{n / (1 << 10):.0f} KB"
    return f"{n} B"


def _fmt_rate(bps: float) -> str:
    if bps >= 1 << 20: return f"{bps / (1 << 20):.1f} MB/s"
    if bps >= 1 << 10: return f"{bps / (1 << 10):.0f} KB/s"
    return f"{bps:.0f} B/s"


def _detail(label: str, done: int, total: int, rate: float) -> str:
    size = f"{_fmt_size(done)} / {_fmt_size(total)}" if total else _fmt_size(done)
    out = f"{label or 'Downloading'}  {size}"
    return f"{out}  ·  {_fmt_rate(rate)}" if rate else out


def download(url: str, dest: str, on_progress=None, label: str = "",
             timeout: int = 60, headers: dict = None, digest: str = None,
             tries: int = 3):
    """
    Download a URL to a local file with resume, progress and retry.

    Writes to <dest>.part and renames on success, so a failed attempt
    leaves a partial file that the next attempt resumes from with a
    Range request. The part file is kept on failure deliberately, which
    is what makes a retry cheap on the multi-gigabyte downloads.

    Progress is reported as on_progress(percent, message) where message
    is the label with transferred size and rate appended, e.g.
    "AlterWare launcher  412 MB / 1.2 GB  ·  8.4 MB/s". Callbacks are
    capped at UPDATE_HZ per second.

    url         : remote URL to fetch
    dest        : local file path to write
    on_progress : optional callback(percent: int, status: str)
    label       : human-readable name shown in progress messages
    timeout     : socket timeout in seconds (default 60)
    headers     : request headers, default BROWSER_UA
    digest      : optional "algo:hex" (e.g. GitHub's "sha256:..."); a
                  mismatch discards the part file and counts as a failed try
    tries       : attempts before giving up (1 for quick checks that must
                  not hold anything up, e.g. before a game launch)
    """
    part = dest + ".part"
    for attempt in range(tries):
        resume = 0
        if os.path.exists(part):
            try:
                resume = os.path.getsize(part)
            except OSError:
                resume = 0
        try:
            hdrs = dict(headers or BROWSER_UA)
            if resume:
                hdrs["Range"] = f"bytes={resume}-"
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                # 206 means the range was honored. Anything else (including
                # a plain 200) means the server sent the whole file, so the
                # part file has to be discarded rather than appended to.
                status = getattr(r, "status", None) or getattr(r, "code", None)
                if resume and status != 206:
                    resume = 0
                length = int(r.headers.get("Content-Length", 0) or 0)
                total  = resume + length if length else 0
                done   = resume
                t0     = time.monotonic()
                last   = 0.0
                with open(part, "ab" if resume else "wb") as f:
                    while True:
                        chunk = r.read(CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        now = time.monotonic()
                        if on_progress and now - last >= 1.0 / UPDATE_HZ:
                            last = now
                            rate = (done - resume) / max(now - t0, 0.001)
                            on_progress(int(done / total * 100) if total else 0,
                                        _detail(label, done, total, rate))
            # A stream that ends early must not be renamed into place.
            # Raise so the retry resumes from the part file.
            if total and done < total:
                raise IOError(f"incomplete download: {done} of {total} bytes")
            if digest:
                _check_digest(part, digest)
            os.replace(part, dest)
            if on_progress:
                on_progress(100, _detail(label, done, total or done, 0))
            return
        except Exception as ex:
            # 416: the part file is as long as the remote file or longer,
            # usually left from an older release. Start over from byte 0.
            if getattr(ex, "code", None) == 416:
                try: os.remove(part)
                except OSError: pass
            if attempt == tries - 1:
                raise
            _log.debug("download retry %d for %s", attempt + 1, url)
            time.sleep(2 ** attempt)


def _check_digest(path: str, digest: str):
    algo, want = digest.split(":", 1)
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    if h.hexdigest().lower() != want.lower():
        os.remove(path)
        raise IOError(f"{algo} mismatch for {os.path.basename(path)}")


class _Ranged(io.RawIOBase):
    """Seekable read-only view of a remote file through HTTP Range requests."""
    def __init__(self, url, timeout, seen):
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=BROWSER_UA), timeout=timeout) as r:
            self.url, self.size = r.geturl(), int(r.headers["Content-Length"])
        self.pos, self.timeout, self.seen = 0, timeout, seen

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=0):
        self.pos = (off, self.pos + off, self.size + off)[whence]
        return self.pos

    def readinto(self, b):
        n = min(len(b), self.size - self.pos)
        if n <= 0:
            return 0
        req = urllib.request.Request(self.url, headers={**BROWSER_UA, "Range": f"bytes={self.pos}-{self.pos + n - 1}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            if r.status != 206:
                raise IOError(f"server ignored the range request (HTTP {r.status})")
            d = r.read()
        b[:len(d)] = d
        self.pos += len(d)
        self.seen(len(d))
        return len(d)


def zip_member(url: str, member: str, sha256: str, on_progress=None, label: str = "",
               timeout: int = 60, tries: int = 3) -> bytes:
    """One file out of a remote zip, fetched with HTTP Range requests instead of
    the whole archive, and checked against its sha256 (hex). Raises DownloadError."""
    label = label or os.path.basename(member)
    last = None
    for attempt in range(tries):
        got, total = [0], [0]
        def seen(n):
            got[0] += n
            if on_progress and total[0]:
                on_progress(min(99, got[0] * 100 // total[0]), _detail(label, min(got[0], total[0]), total[0], 0))
        try:
            with zipfile.ZipFile(io.BufferedReader(_Ranged(url, timeout, seen), CHUNK)) as zf:
                total[0] = zf.getinfo(member).compress_size
                data = zf.read(member)
            if hashlib.sha256(data).hexdigest() != sha256.lower():
                raise IOError(f"sha256 mismatch for {member}")
            return data
        except Exception as ex:
            last = ex
            _log.warning(f"{label}: attempt {attempt + 1} of {tries} failed: {ex}")
            if attempt + 1 < tries:
                time.sleep(2 * (attempt + 1))
    raise DownloadError(url, member, label, last)


def github_asset(repo: str, suffix: str, fallback: str = None, timeout: int = 30,
                 prerelease: bool = False):
    """
    (url, digest) of the latest release asset of repo whose name ends with
    suffix. digest is GitHub's "sha256:..." or None. If the API lookup
    fails and fallback is given, returns (fallback, None) so an API outage
    or rate limit doesn't block the install, just skips verification.
    prerelease: take the newest release even if it is a pre-release.
    releases/latest skips those, and some repos only publish pre-releases.
    """
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/releases" + ("?per_page=1" if prerelease else "/latest"),
            headers={"Accept": "application/vnd.github+json", "User-Agent": "DeckOps"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        if prerelease:
            data = data[0] if data else {}
        for a in data.get("assets", []):
            if a["name"].endswith(suffix):
                return a["browser_download_url"], a.get("digest")
        raise RuntimeError(f"No *{suffix} asset in latest {repo} release")
    except Exception as ex:
        if fallback is None:
            raise
        _log.warning("GitHub lookup for %s failed, downloading unverified: %s", repo, ex)
        return fallback, None
