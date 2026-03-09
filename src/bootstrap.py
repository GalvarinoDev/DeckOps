"""
bootstrap.py — DeckOps pre-launch asset fetcher

Downloads the Science Gothic variable font and Steam header images into the
assets folder before the PyQt5 UI initialises. Called from BootstrapScreen on
a background thread so the UI can show progress.

Music is NOT downloaded here. If assets/music/background.ogg is present it
will be played automatically. Users can drop any OGG file there themselves.
"""

import os
import urllib.request

# ── paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR    = os.path.join(PROJECT_ROOT, "assets", "fonts")
HEADERS_DIR  = os.path.join(PROJECT_ROOT, "assets", "images", "headers")
MUSIC_DIR    = os.path.join(PROJECT_ROOT, "assets", "music")

os.makedirs(FONTS_DIR,   exist_ok=True)
os.makedirs(HEADERS_DIR, exist_ok=True)
os.makedirs(MUSIC_DIR,   exist_ok=True)

# ── font sources ──────────────────────────────────────────────────────────────
# Science Gothic variable font — single file, stable path, SIL OFL licensed.
# Brackets in the filename are URL-encoded for urllib.

_VF_URL = (
    "https://raw.githubusercontent.com/googlefonts/science-gothic"
    "/main/fonts/variable/ScienceGothic%5BCTRS%2Cslnt%2Cwdth%2Cwght%5D.ttf"
)
_CNDBLK_URL = (
    "https://raw.githubusercontent.com/googlefonts/science-gothic"
    "/main/fonts/static/Instances/ScienceGothic-CndBlk.ttf"
)

FONT_FILE        = "ScienceGothic-VF.ttf"
FONT_FILE_CNDBLK = "ScienceGothic-CndBlk.ttf"

FONTS = {
    FONT_FILE:        _VF_URL,
    FONT_FILE_CNDBLK: _CNDBLK_URL,
}

# ── Steam header images ───────────────────────────────────────────────────────

_STEAM_CDN = "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"

# Games where the multiplayer appid differs from the SP appid on Steam CDN.
# We download from the SP appid URL but save under the game's appid filename.
_HEADER_OVERRIDES = {
    10190:  "https://shared.steamstatic.com/store_item_assets/steam/apps/10180/header.jpg",
    202990: "https://shared.steamstatic.com/store_item_assets/steam/apps/202970/header.jpg",
}

HEADER_APPIDS = [
    7940,    # CoD4
    10190,   # MW2  (downloads from SP appid 10180)
    42690,   # MW3
    10090,   # World at War
    42700,   # Black Ops
    202990,  # Black Ops II  (downloads from SP appid 202970)
]


# ── helpers ───────────────────────────────────────────────────────────────────

def _download(url: str, dest: str, label: str, on_progress) -> bool:
    """
    Download url to dest. Returns True on success, False on failure.
    on_progress(message: str) is called with status updates.
    """
    if os.path.exists(dest):
        on_progress(f"  checkmark  {label} (cached)")
        return True
    on_progress(f"  down  {label}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DeckOps"})
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
    """
    Download all required assets (font + Steam headers).

    on_progress(pct: int, message: str)  -- called during download
    on_complete(success: bool)           -- called when finished
    """
    if on_progress is None:
        on_progress = lambda pct, msg: print(f"[{pct:3d}%] {msg}")
    if on_complete is None:
        on_complete = lambda ok: None

    tasks = []

    # Variable font
    for filename, url in FONTS.items():
        dest = os.path.join(FONTS_DIR, filename)
        tasks.append((url, dest, f"Font: {filename}"))

    # Steam headers
    for appid in HEADER_APPIDS:
        url  = _HEADER_OVERRIDES.get(appid, _STEAM_CDN.format(appid=appid))
        dest = os.path.join(HEADERS_DIR, f"{appid}.jpg")
        tasks.append((url, dest, f"Header: {appid}.jpg"))

    total  = len(tasks)
    failed = 0

    for i, (url, dest, label) in enumerate(tasks):
        pct = int(i / total * 100)
        ok  = _download(url, dest, label,
                        lambda msg, _p=pct: on_progress(_p, msg))
        if not ok:
            failed += 1

    on_progress(100, "Assets ready.")
    on_complete(failed == 0)


def fonts_ready() -> bool:
    """Return True if both font files are present."""
    return (
        os.path.exists(os.path.join(FONTS_DIR, FONT_FILE)) and
        os.path.exists(os.path.join(FONTS_DIR, FONT_FILE_CNDBLK))
    )


def headers_ready() -> bool:
    """Return True if all Steam header images are present."""
    return all(
        os.path.exists(os.path.join(HEADERS_DIR, f"{appid}.jpg"))
        for appid in HEADER_APPIDS
    )


def all_ready() -> bool:
    return fonts_ready() and headers_ready()
