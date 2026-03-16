"""
bootstrap.py — DeckOps pre-launch asset fetcher

Downloads Steam header images into the assets folder before the PyQt5 UI
initialises. Called from BootstrapScreen on a background thread so the UI
can show progress.

The Russo One font is bundled in the repo and does not need downloading.
Music is NOT downloaded here — if assets/music/background.mp3 is present
it will be played automatically.
"""

import os
import urllib.request

# ── paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS_DIR  = os.path.join(PROJECT_ROOT, "assets", "images", "headers")

os.makedirs(HEADERS_DIR, exist_ok=True)

# ── Steam header images ───────────────────────────────────────────────────────

_STEAM_CDN = "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"

_HEADER_OVERRIDES = {
    10190:  "https://shared.steamstatic.com/store_item_assets/steam/apps/10180/header.jpg",
    202990: "https://shared.steamstatic.com/store_item_assets/steam/apps/202970/header.jpg",
}

HEADER_APPIDS = [
    7940,
    10190,
    42690,
    10090,
    42700,
    202990,
]


# ── helpers ───────────────────────────────────────────────────────────────────

def _download(url: str, dest: str, label: str, on_progress) -> bool:
    if os.path.exists(dest):
        on_progress(f"  checkmark  {label} (cached)")
        return True
    on_progress(f"  down  {label}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            with open(dest, "wb") as f:
                f.write(r.read())
        on_progress(f"  checkmark  {label}")
        return True
    except Exception as e:
        on_progress(f"  fail  {label} failed: {e}")
        return False


# ── public API ────────────────────────────────────────────────────────────────

def run(on_progress=None, on_complete=None):
    if on_progress is None:
        on_progress = lambda pct, msg: print(f"[{pct:3d}%] {msg}")
    if on_complete is None:
        on_complete = lambda ok: None

    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    tasks = []

    for appid in HEADER_APPIDS:
        url  = _HEADER_OVERRIDES.get(appid, _STEAM_CDN.format(appid=appid))
        dest = os.path.join(HEADERS_DIR, f"{appid}.jpg")
        tasks.append((url, dest, f"Header: {appid}.jpg"))

    total     = len(tasks)
    failed    = 0
    completed = 0
    lock      = threading.Lock()

    def _run_task(args):
        nonlocal completed, failed
        url, dest, label = args
        ok = _download(url, dest, label, lambda msg, _l=label: on_progress(0, msg))
        with lock:
            completed += 1
            pct = int(completed / total * 100)
            on_progress(pct, label)
            if not ok:
                failed += 1

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_run_task, t) for t in tasks]
        for f in as_completed(futures):
            f.result()  # re-raise any exceptions

    on_progress(100, "Assets ready.")
    on_complete(failed == 0)


def headers_ready() -> bool:
    return all(
        os.path.exists(os.path.join(HEADERS_DIR, f"{appid}.jpg"))
        for appid in HEADER_APPIDS
    )


def all_ready() -> bool:
    return headers_ready()
