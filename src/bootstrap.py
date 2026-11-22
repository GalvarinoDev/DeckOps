"""
bootstrap.py — DeckOps pre-launch asset fetcher

Downloads Steam portrait grid images into the assets folder before the Qt UI
initialises. Called from BootstrapScreen on a background thread so the UI
can show progress.

Russo One font is NOT downloaded here — it is bundled with the repo at
assets/fonts/RussoOne-Regular.ttf and is always available immediately.

Music is NOT downloaded here. If assets/music/background.mp3 is present it
will be played automatically. Users can drop any MP3 file there themselves.
"""

import os

from net import download

# ── paths ─────────────────────────────────────────────────────────────────────

from steam_common import PROJECT_ROOT
FONTS_DIR    = os.path.join(PROJECT_ROOT, "assets", "fonts")
HEADERS_DIR  = os.path.join(PROJECT_ROOT, "assets", "images", "headers")
MUSIC_DIR    = os.path.join(PROJECT_ROOT, "assets", "music")

os.makedirs(FONTS_DIR,   exist_ok=True)
os.makedirs(HEADERS_DIR, exist_ok=True)
os.makedirs(MUSIC_DIR,   exist_ok=True)

# ── font ──────────────────────────────────────────────────────────────────────
# Russo One is shipped with the repo in assets/fonts/ — no download needed.
# bootstrap.py does not download fonts. _load_font() in ui_qt.py loads it
# directly from disk on every launch.

FONT_FILE = "RussoOne-Regular.ttf"

# ── Steam portrait grid images ────────────────────────────────────────────────

_STEAM_CDN = "https://shared.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900_2x.jpg"

# Some games have separate appids for SP and MP but share the same store
# artwork. The MP appids below point to their SP counterpart's portrait image
# so we don't download duplicates or get the wrong art on the UI cards.
_HEADER_OVERRIDES = {
    2640:   "https://cdn2.steamgriddb.com/grid/3ead4e722d6df4d4d7e1c61fbdd66968.png",  # UO has no Steam portrait
    99000003: "https://cdn2.steamgriddb.com/grid/ebb4cd828b62543f83b337e48b333eb8.jpg",  # CoD3 has no Steam app, so this appid is a placeholder
    99000005: "https://cdn2.steamgriddb.com/grid/f0dda1e19cb7596fcb7430e4b3f4f0b5.png",  # Finest Hour, same
    99000004: "https://cdn2.steamgriddb.com/grid/3e5589b2df55552e7716818b29ba2a2d.png",  # Big Red One, same
    10190:  "https://shared.steamstatic.com/store_item_assets/steam/apps/10180/library_600x900_2x.jpg",   # MW2 MP -> MW2 SP art
    202990: "https://shared.steamstatic.com/store_item_assets/steam/apps/202970/library_600x900_2x.jpg",  # BO2 MP -> BO2 SP art
    42690:  "https://shared.steamstatic.com/store_item_assets/steam/apps/42680/library_600x900_2x.jpg",   # MW3 MP -> MW3 SP art
}

# Every appid that needs a portrait grid image cached locally.
# SP and MP appids are both listed so the UI can look up either one.
HEADER_APPIDS = [
    2620,     # CoD1
    2640,     # UO
    2630,     # CoD2
    99000003, # CoD3 (placeholder appid)
    99000004, # Big Red One (placeholder appid)
    99000005, # Finest Hour (placeholder appid)
    7940,
    10180,
    10190,
    42680,
    42690,
    10090,
    42700,
    202970,
    202990,
    311210,
    209160,   # Ghosts SP
    209650,   # Advanced Warfare SP
]


# ── helpers ───────────────────────────────────────────────────────────────────

def _download(url: str, dest: str, label: str, on_progress) -> bool:
    if os.path.exists(dest):
        on_progress(f"  checkmark  {label} (cached)")
        return True
    on_progress(f"  down  {label}...")
    try:
        download(url, dest, timeout=30)
    except Exception as e:
        on_progress(f"  fail  {label} failed: {e}")
        return False
    on_progress(f"  checkmark  {label}")
    return True


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
        dest = os.path.join(HEADERS_DIR, f"{appid}_grid.jpg")
        tasks.append((url, dest, f"Grid: {appid}_grid.jpg"))

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


def fonts_ready() -> bool:
    """Returns True if the bundled Russo One font file is present on disk."""
    return os.path.exists(os.path.join(FONTS_DIR, FONT_FILE))


def headers_ready() -> bool:
    return all(
        os.path.exists(os.path.join(HEADERS_DIR, f"{appid}_grid.jpg"))
        for appid in HEADER_APPIDS
    )


def all_ready() -> bool:
    return fonts_ready() and headers_ready()
