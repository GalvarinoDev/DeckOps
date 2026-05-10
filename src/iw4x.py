"""
iw4x.py - DeckOps installer for IW4x (Modern Warfare 2)

Downloads iw4x.dll and release.zip from the latest GitHub releases.
release.zip contains iw4x.exe, all iwd files, zone patches, and other
rawfile assets. Everything extracts directly into the game install folder.

Optionally downloads free DLC content from cdn.iw4x.io, including:
  - MW2 DLC map packs (iw4x/*.iwd)
  - CoD4 ported maps → zone/dlc/*.ff
  - Black Ops maps   → zone/dlc/*.ff
  - MW3 maps         → zone/dlc/*.ff
  - CoD Online maps  → zone/dlc/*.ff

All .ff files from the CDN (regardless of their manifest prefix) are
placed into zone/dlc/ to match the correct IW4x install layout.
All .iwd files from the CDN go into iw4x/ as the manifest specifies.

For Steam games:
  - Renames iw4mp.exe -> iw4mp.exe.bak
  - Copies iw4x.exe -> iw4mp.exe
  This lets Steam launch IW4x transparently via the existing shortcut.

For own games:
  - Downloads all files but skips the exe rename
  - The non-Steam shortcut already points at iw4x.exe directly

Progress is reported via a callback:
    on_progress(percent: int, status: str)
"""

import os
import json
import shutil
import zipfile
import threading

from net import download as _download

from log import get_logger

_log = get_logger(__name__)


# iw4x.dll comes from the client repo, everything else from rawfiles.
# release.zip contains iw4x.exe, all iwd files, zone patches,
# and other assets. No separate downloads needed.
DLL_URL = "https://github.com/iw4x/iw4x-client/releases/latest/download/iw4x.dll"
ZIP_URL = "https://github.com/iw4x/iw4x-rawfiles/releases/latest/download/release.zip"

# CDN manifest for free DLC content (maps from CoD4, BO1, MW3, CoD Online, MW2 DLC)
DLC_MANIFEST_URL = "https://cdn.iw4x.io/update.json"
DLC_CDN_BASE     = "https://cdn.iw4x.io/"

# Manifest path prefixes that contain .ff files, all remapped to zone/dlc/.
_FF_PREFIXES = (
    "iw3/zone/dlc/",
    "t5/zone/dlc/",
    "iw5/zone/dlc/",
    "codo/zone/dlc/",
)


# ── helpers ───────────────────────────────────────────────────────────────────

# _download imported from net.py; call sites pass timeout=120 for large files.


def _remap_dlc_path(manifest_path: str, install_dir: str) -> str:
    """
    Remap a CDN manifest path to the correct local destination.

    .ff files from any game-prefixed subdirectory (iw3/, t5/, iw5/, codo/)
    are all placed into zone/dlc/ to match the correct IW4x layout.
    .iwd files under iw4x/ are kept in iw4x/ as-is.
    """
    for prefix in _FF_PREFIXES:
        if manifest_path.startswith(prefix):
            filename = manifest_path[len(prefix):]
            return os.path.join(install_dir, "zone", "dlc", filename)
    # iw4x/*.iwd and anything else — use the manifest path directly
    return os.path.join(install_dir, manifest_path)


def is_iw4x_installed(install_dir: str) -> bool:
    """Returns True if iw4mp.exe.bak exists (meaning the mod rename is active)."""
    return os.path.exists(os.path.join(install_dir, "iw4mp.exe.bak"))


def is_iw4x_dlc_installed(install_dir: str) -> bool:
    """Returns True if DLC content appears to be present."""
    markers = [
        os.path.join(install_dir, "iw4x", "iw_dlc3_00.iwd"),       # MW2 DLC iwd
        os.path.join(install_dir, "zone", "dlc", "mp_backlot.ff"),  # CoD4 ff
        os.path.join(install_dir, "zone", "dlc", "mp_nuked.ff"),    # BO1 ff
    ]
    return all(os.path.exists(m) for m in markers)


# ── DLC install ──────────────────────────────────────────────────────────────

def install_iw4x_dlc(install_dir: str, on_progress=None):
    """
    Download and install free DLC content from cdn.iw4x.io.

    Fetches the manifest (update.json), then downloads every file listed
    in it to the correct relative path under install_dir. All .ff files
    are remapped into zone/dlc/ regardless of their manifest prefix.
    Files are downloaded with up to 4 concurrent workers.

    on_progress — optional callback(percent: int, status: str)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    # ── Fetch manifest ────────────────────────────────────────────────────
    prog(0, "Fetching DLC manifest...")
    manifest_path = os.path.join(install_dir, "update.json")
    _download(DLC_MANIFEST_URL, manifest_path, None, "DLC manifest", timeout=120)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    os.remove(manifest_path)

    files = manifest.get("files", [])
    if not files:
        prog(100, "No DLC files found in manifest.")
        return

    # ── Create destination directories ────────────────────────────────────
    prog(2, "Creating DLC directories...")
    dirs_needed = set()
    for entry in files:
        dest = _remap_dlc_path(entry["path"], install_dir)
        dirs_needed.add(os.path.dirname(dest))
    for d in dirs_needed:
        os.makedirs(d, exist_ok=True)

    # ── Download all files concurrently ───────────────────────────────────
    total_files = len(files)
    dl_done     = [0]
    dl_errors   = []
    dl_lock     = threading.Lock()

    def _dl_one(entry):
        rel_path = entry["path"]
        dest     = _remap_dlc_path(rel_path, install_dir)
        name     = entry.get("asset_name", os.path.basename(rel_path))
        url      = DLC_CDN_BASE + rel_path

        # Skip if file already exists and matches expected size
        expected_size = entry.get("size", 0)
        if os.path.exists(dest) and expected_size:
            try:
                actual = os.path.getsize(dest)
                if actual == expected_size:
                    with dl_lock:
                        dl_done[0] += 1
                        prog(2 + int(dl_done[0] / total_files * 96),
                             f"Skipped {name} (already exists)")
                    return
            except OSError:
                _log.debug("size check failed", exc_info=True)

        _download(url, dest, None, name, timeout=120)
        with dl_lock:
            dl_done[0] += 1
            prog(2 + int(dl_done[0] / total_files * 96),
                 f"Downloaded {name} ({dl_done[0]}/{total_files})")

    prog(3, f"Downloading {total_files} DLC files (~3 GB)...")

    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_dl_one, entry): entry for entry in files}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as e:
                name = futs[fut].get("asset_name", "unknown")
                dl_errors.append(f"{name}: {e}")

    if dl_errors:
        raise RuntimeError("DLC download failed:\n" + "\n".join(dl_errors))

    prog(100, "DLC installation complete!")


# ── public API ────────────────────────────────────────────────────────────────

def install_iw4x(game: dict, steam_root: str,
                 proton_path: str, compatdata_path: str,
                 on_progress=None, source: str = "steam",
                 install_dlc: bool = False):
    """
    Install or reinstall IW4x for Modern Warfare 2.

    Downloads iw4x.dll and release.zip concurrently. release.zip contains
    iw4x.exe, all iwd files, zone patches, and other rawfile assets.
    For Steam games, renames iw4mp.exe -> iw4mp.exe.bak and copies
    iw4x.exe -> iw4mp.exe so Steam launches IW4x transparently.
    For own games, skips the rename -- the shortcut points at iw4x.exe directly.

    game            — entry from detect_games
    steam_root      — path to Steam root (kept for API consistency)
    proton_path     — path to the proton executable (kept for API consistency)
    compatdata_path — path to the MW2 compatdata prefix (kept for API consistency)
    on_progress     — optional callback(percent: int, status: str)
    source          — "steam" or "own", controls whether exe rename happens
    install_dlc     — if True, download free DLC maps after base install
    """
    install_dir = game["install_dir"]
    iw4x_dir    = os.path.join(install_dir, "iw4x")
    if os.path.exists(iw4x_dir):
        shutil.rmtree(iw4x_dir)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    # When DLC is enabled, base install uses 0-50%, DLC uses 50-100%.
    # When DLC is disabled, base install uses 0-100%.
    base_end = 50 if install_dlc else 100

    def prog(pct, msg):
        if on_progress:
            scaled = int(pct / 100 * base_end)
            on_progress(scaled, msg)

    # ── Download iw4x.dll and release.zip concurrently ────────────────────
    prog(5, "Downloading iw4x files...")

    dl_tasks = [
        (DLL_URL, os.path.join(install_dir, "iw4x.dll"),    "iw4x.dll"),
        (ZIP_URL, os.path.join(install_dir, "release.zip"), "release.zip"),
    ]
    dl_errors = []
    dl_done   = [0]
    dl_lock   = threading.Lock()

    def _dl(url, dest, label):
        _download(url, dest, None, f"Downloading {label}...", timeout=120)
        with dl_lock:
            dl_done[0] += 1
            prog(5 + int(dl_done[0] / len(dl_tasks) * 45), f"Downloaded {label}")

    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(_dl, url, dest, label): label for url, dest, label in dl_tasks}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as e:
                dl_errors.append(f"{futs[fut]}: {e}")

    if dl_errors:
        raise RuntimeError("Download failed:\n" + "\n".join(dl_errors))

    # ── Extract release.zip ───────────────────────────────────────────────
    # release.zip contains:
    #   iw4x.exe          (root)
    #   iw4x/*.iwd        (iwd files)
    #   iw4x/html/        (server browser assets)
    #   iw4x/images/      (branding)
    #   iw4x/video/       (intro video)
    #   zone/patch/       (fastfile patches)
    #   zonebuilder.exe   (modding tool)
    prog(55, "Extracting release.zip...")
    zip_dest = os.path.join(install_dir, "release.zip")
    with zipfile.ZipFile(zip_dest) as zf:
        zf.extractall(install_dir)
    os.remove(zip_dest)

    # ── Rename iw4mp.exe -> iw4mp.exe.bak, copy iw4x.exe -> iw4mp.exe ───
    # Steam games: swap in iw4x.exe so Steam launches it transparently.
    # Own games: skip -- the shortcut points at iw4x.exe directly and the
    # original exe may not even exist (MS Store copies, old installs, etc).
    if source != "own":
        iw4mp     = os.path.join(install_dir, "iw4mp.exe")
        iw4mp_bak = os.path.join(install_dir, "iw4mp.exe.bak")
        iw4x_exe  = os.path.join(install_dir, "iw4x.exe")

        prog(80, "Replacing iw4mp.exe...")
        if os.path.exists(iw4mp) and not os.path.exists(iw4mp_bak):
            os.rename(iw4mp, iw4mp_bak)
        if os.path.exists(iw4x_exe):
            shutil.copy2(iw4x_exe, iw4mp)
    else:
        prog(80, "Own game -- skipping exe rename")

    prog(100, "IW4x base installation complete!")

    # ── Optional DLC download ─────────────────────────────────────────────
    if install_dlc:
        def dlc_prog(pct, msg):
            if on_progress:
                on_progress(50 + int(pct / 100 * 50), msg)
        install_iw4x_dlc(install_dir, on_progress=dlc_prog)


def uninstall_iw4x(game: dict):
    """
    Restore iw4mp.exe from iw4mp.exe.bak and remove all IW4x files,
    including DLC content.
    """
    install_dir = game["install_dir"]

    # Restore iw4mp.exe from backup
    iw4mp     = os.path.join(install_dir, "iw4mp.exe")
    iw4mp_bak = os.path.join(install_dir, "iw4mp.exe.bak")
    if os.path.exists(iw4mp_bak):
        if os.path.exists(iw4mp):
            os.remove(iw4mp)
        os.rename(iw4mp_bak, iw4mp)

    for fname in ["iw4x.dll", "iw4x.exe", "zonebuilder.exe"]:
        p = os.path.join(install_dir, fname)
        if os.path.exists(p):
            os.remove(p)

    iw4x_dir = os.path.join(install_dir, "iw4x")
    if os.path.exists(iw4x_dir):
        shutil.rmtree(iw4x_dir)

    # Clean up zone/patch directory added by release.zip
    zone_patch = os.path.join(install_dir, "zone", "patch")
    if os.path.exists(zone_patch):
        shutil.rmtree(zone_patch)

    # Remove DLC .ff files from zone/dlc/.
    # Only delete filenames that come from the CDN manifest — the base game
    # may have its own files in zone/dlc/ that we must not touch.
    _DLC_FF_FILENAMES = {
        # CoD4 (iw3)
        "mp_convoy_load.ff", "mp_backlot_load.ff", "mp_broadcast_load.ff",
        "mp_pipeline_load.ff", "mp_killhouse.ff", "mp_broadcast.ff",
        "mp_countdown.ff", "mp_showdown_load.ff", "mp_carentan.ff",
        "mp_citystreets_load.ff", "mp_convoy.ff", "mp_farm_load.ff",
        "mp_cargoship_load.ff", "mp_cargoship.ff", "mp_backlot.ff",
        "mp_carentan_load.ff", "mp_crash_snow.ff", "mp_cross_fire_load.ff",
        "mp_countdown_load.ff", "mp_bloc.ff", "mp_killhouse_load.ff",
        "mp_farm.ff", "mp_citystreets.ff", "mp_bloc_load.ff",
        "mp_cross_fire.ff", "mp_showdown.ff", "mp_crash_snow_load.ff",
        "mp_pipeline.ff",
        # Black Ops (t5)
        "mp_firingrange.ff", "mp_nuked_load.ff", "mp_firingrange_load.ff",
        "mp_nuked.ff",
        # MW3 (iw5)
        "mp_village.ff", "mp_bravo.ff", "mp_paris.ff", "mp_underground_load.ff",
        "mp_hardhat_load.ff", "mp_underground.ff", "mp_plaza2_load.ff",
        "mp_bravo_load.ff", "mp_paris_load.ff", "mp_hardhat.ff",
        "mp_plaza2.ff", "mp_seatown.ff", "mp_alpha_load.ff", "mp_dome.ff",
        "mp_dome_load.ff", "mp_seatown_load.ff", "mp_village_load.ff",
        "mp_alpha.ff",
        # CoD Online (codo)
        "mp_storm_spring_load.ff", "mp_fav_tropical.ff", "mp_estate_tropical.ff",
        "mp_fav_tropical_load.ff", "mp_cargoship_sh_load.ff", "mp_bloc_sh_load.ff",
        "mp_crash_tropical_load.ff", "mp_crash_tropical.ff", "mp_cargoship_sh.ff",
        "mp_estate_tropical_load.ff", "mp_shipment_load.ff", "mp_rust_long_load.ff",
        "mp_shipment_long_load.ff", "mp_rust_long.ff", "mp_storm_spring.ff",
        "mp_shipment.ff", "mp_shipment_long.ff", "mp_bog_sh_load.ff",
        "mp_bog_sh.ff", "mp_nuked_shaders.ff", "mp_bloc_sh.ff",
    }

    zone_dlc = os.path.join(install_dir, "zone", "dlc")
    if os.path.isdir(zone_dlc):
        for fname in _DLC_FF_FILENAMES:
            p = os.path.join(zone_dlc, fname)
            if os.path.exists(p):
                os.remove(p)
        # Remove zone/dlc/ if now empty, then zone/ if also empty
        if not os.listdir(zone_dlc):
            os.rmdir(zone_dlc)
            zone_dir = os.path.join(install_dir, "zone")
            if os.path.isdir(zone_dir) and not os.listdir(zone_dir):
                os.rmdir(zone_dir)

    # Clean up old DeckOps metadata if upgrading from a previous install
    old_meta = os.path.join(install_dir, "iw4x-updoot")
    if os.path.exists(old_meta):
        shutil.rmtree(old_meta)
