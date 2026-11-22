"""
iw4x.py - DeckOps installer for IW4x (Modern Warfare 2)

Downloads iw4x.dll, release.zip, and the IW4x launcher from GitHub.
release.zip contents are relocated to the launcher-compatible layout:
  iw4x/           → main/iw4x/x86/
  zone/patch/      → zone/iw4x/x86/patch/
  zone/zonebuilder/→ zone/iw4x/x86/zonebuilder/

The launcher (iw4x-launcher.exe) updates itself on every launch.
Steam games get a "Play IW4x" launch menu entry that runs the launcher.

Can also download the free DLC from cdn.iw4x.io:
  - MW2 DLC map packs (main/iw4x/x86/*.iwd)
  - CoD4 ported maps → zone/iw4x/x86/dlc/*.ff
  - Black Ops maps   → zone/iw4x/x86/dlc/*.ff
  - MW3 maps         → zone/iw4x/x86/dlc/*.ff
  - CoD Online maps  → zone/iw4x/x86/dlc/*.ff

Progress goes to a callback:
    on_progress(percent: int, status: str)
"""

import os
import json
import shutil
import zipfile
import threading

from net import download as _download, github_asset

from log import get_logger

_log = get_logger(__name__)


# iw4x.dll comes from the client repo, everything else from rawfiles.
# release.zip holds iw4x.exe, all iwd files, zone patches and the
# other assets, so they need no separate downloads.
DLL_URL = "https://github.com/iw4x/iw4x-client/releases/latest/download/iw4x.dll"
ZIP_URL = "https://github.com/iw4x/iw4x-rawfiles/releases/latest/download/release.zip"

# Free DLC from the CDN manifest (maps from CoD4, BO1, MW3, CoD Online, MW2 DLC).
# Size is approximate. The UI labels say "~3 GB" and preflight budgets for it.
DLC_SIZE_GB      = 3
DLC_MANIFEST_URL = "https://cdn.iw4x.io/update.json"
DLC_CDN_BASE     = "https://cdn.iw4x.io/"

MW2_MP_APPID = "10190"

# Manifest path prefixes that contain .ff files, all remapped to zone/iw4x/x86/dlc/.
_FF_PREFIXES = (
    "iw3/zone/dlc/",
    "t5/zone/dlc/",
    "iw5/zone/dlc/",
    "codo/zone/dlc/",
)


# --- helpers

# _download comes from net.py. Call sites pass timeout=120 for large files.


def _remap_dlc_path(manifest_path: str, install_dir: str) -> str:
    """
    Map a CDN manifest path to its local destination.

    .ff files from any game folder (iw3/, t5/, iw5/, codo/) all go to
    zone/iw4x/x86/dlc/, where IW4x expects them.
    .iwd files under iw4x/ go to main/iw4x/x86/ (launcher layout).
    """
    for prefix in _FF_PREFIXES:
        if manifest_path.startswith(prefix):
            filename = manifest_path[len(prefix):]
            return os.path.join(install_dir, "zone", "iw4x", "x86", "dlc", filename)
    # iw4x/*.iwd goes to main/iw4x/x86/ (launcher layout)
    if manifest_path.startswith("iw4x/"):
        return os.path.join(install_dir, "main", "iw4x", "x86", manifest_path[5:])
    return os.path.join(install_dir, manifest_path)


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


def _remove_dlc_ff(install_dir: str):
    """Remove DLC .ff files from zone/iw4x/x86/dlc/ (and legacy zone/dlc/)."""
    for dlc_dir in (
        os.path.join(install_dir, "zone", "iw4x", "x86", "dlc"),
        os.path.join(install_dir, "zone", "dlc"),
    ):
        if not os.path.isdir(dlc_dir):
            continue
        for fname in _DLC_FF_FILENAMES:
            p = os.path.join(dlc_dir, fname)
            if os.path.exists(p):
                os.remove(p)
        # Clean up empty parent directories
        d = dlc_dir
        while d != install_dir and os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
            d = os.path.dirname(d)


def is_iw4x_dlc_installed(install_dir: str) -> bool:
    """True if the DLC files look installed."""
    markers = [
        os.path.join(install_dir, "main", "iw4x", "x86", "iw_dlc3_00.iwd"),       # MW2 DLC iwd
        os.path.join(install_dir, "zone", "iw4x", "x86", "dlc", "mp_backlot.ff"),  # CoD4 ff
        os.path.join(install_dir, "zone", "iw4x", "x86", "dlc", "mp_nuked.ff"),    # BO1 ff
    ]
    if all(os.path.exists(m) for m in markers):
        return True
    # Check legacy paths for installs that haven't been migrated yet
    legacy = [
        os.path.join(install_dir, "iw4x", "iw_dlc3_00.iwd"),
        os.path.join(install_dir, "zone", "dlc", "mp_backlot.ff"),
        os.path.join(install_dir, "zone", "dlc", "mp_nuked.ff"),
    ]
    return all(os.path.exists(m) for m in legacy)


# --- DLC migration

def _migrate_dlc_ff(install_dir: str):
    """Move .ff files from legacy zone/dlc/ to zone/iw4x/x86/dlc/."""
    old_dir = os.path.join(install_dir, "zone", "dlc")
    if not os.path.isdir(old_dir):
        return
    new_dir = os.path.join(install_dir, "zone", "iw4x", "x86", "dlc")
    moved = 0
    for fname in _DLC_FF_FILENAMES:
        old = os.path.join(old_dir, fname)
        if os.path.isfile(old):
            os.makedirs(new_dir, exist_ok=True)
            shutil.move(old, os.path.join(new_dir, fname))
            moved += 1
    if moved:
        _log.info("Migrated %d DLC .ff files from zone/dlc/ to zone/iw4x/x86/dlc/", moved)
    # Clean up empty legacy directory
    d = old_dir
    while d != install_dir and os.path.isdir(d) and not os.listdir(d):
        os.rmdir(d)
        d = os.path.dirname(d)


def _migrate_old_layout(install_dir: str):
    """Migrate from old DeckOps layout to launcher-compatible layout."""
    # Undo the old exe swap: put iw4mp.exe back from its backup
    iw4mp_bak = os.path.join(install_dir, "iw4mp.exe.bak")
    if os.path.exists(iw4mp_bak):
        iw4mp = os.path.join(install_dir, "iw4mp.exe")
        if os.path.exists(iw4mp):
            os.remove(iw4mp)
        os.rename(iw4mp_bak, iw4mp)
        _log.info("Restored iw4mp.exe from backup")

    _moves = [
        ("iw4x", os.path.join("main", "iw4x", "x86")),
        (os.path.join("zone", "patch"), os.path.join("zone", "iw4x", "x86", "patch")),
        (os.path.join("zone", "zonebuilder"), os.path.join("zone", "iw4x", "x86", "zonebuilder")),
    ]
    for old_rel, new_rel in _moves:
        old_abs = os.path.join(install_dir, old_rel)
        new_abs = os.path.join(install_dir, new_rel)
        if not os.path.isdir(old_abs):
            continue
        os.makedirs(os.path.dirname(new_abs), exist_ok=True)
        if os.path.isdir(new_abs):
            for item in os.listdir(old_abs):
                shutil.move(os.path.join(old_abs, item), os.path.join(new_abs, item))
            shutil.rmtree(old_abs)
        else:
            shutil.move(old_abs, new_abs)
        _log.info("Migrated %s → %s", old_rel, new_rel)


def _relocate_extracted(install_dir: str):
    """Move release.zip dirs from flat layout to launcher-compatible layout."""
    _moves = [
        ("iw4x", os.path.join("main", "iw4x", "x86")),
        (os.path.join("zone", "patch"), os.path.join("zone", "iw4x", "x86", "patch")),
        (os.path.join("zone", "zonebuilder"), os.path.join("zone", "iw4x", "x86", "zonebuilder")),
    ]
    for old_rel, new_rel in _moves:
        old_abs = os.path.join(install_dir, old_rel)
        new_abs = os.path.join(install_dir, new_rel)
        if not os.path.isdir(old_abs):
            continue
        os.makedirs(os.path.dirname(new_abs), exist_ok=True)
        if os.path.isdir(new_abs):
            for item in os.listdir(old_abs):
                src = os.path.join(old_abs, item)
                dst = os.path.join(new_abs, item)
                if os.path.exists(dst):
                    if os.path.isdir(dst):
                        shutil.rmtree(dst)
                    else:
                        os.remove(dst)
                shutil.move(src, dst)
            shutil.rmtree(old_abs)
        else:
            shutil.move(old_abs, new_abs)


# Launch menu entry for the Steam copy. Since v1.1.8-b.20 the launcher ships
# x86 and x64 (mm) clients. Without --arch it can show a terminal picker
# that nobody can answer in Game Mode.
IW4X_MENU = [
    {"executable": "iw4x-launcher.exe", "arguments": "--arch x86", "description": "Play IW4x"},
]


# --- DLC install

def install_iw4x_dlc(install_dir: str, on_progress=None):
    """
    Download and install free DLC content from cdn.iw4x.io.

    Fetches the manifest (update.json) and downloads every file in it to
    its path under install_dir, 4 at a time. All .ff files go to
    zone/iw4x/x86/dlc/, whatever their manifest prefix.

    on_progress: optional callback(percent: int, status: str)
    """
    _migrate_dlc_ff(install_dir)
    _migrate_old_layout(install_dir)
    from concurrent.futures import ThreadPoolExecutor, as_completed

    prog = on_progress or (lambda *a: None)

    # --- Fetch manifest
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

    # --- Create destination directories
    prog(2, "Creating DLC directories...")
    dirs_needed = set()
    for entry in files:
        dest = _remap_dlc_path(entry["path"], install_dir)
        dirs_needed.add(os.path.dirname(dest))
    for d in dirs_needed:
        os.makedirs(d, exist_ok=True)

    # --- Download all files concurrently
    total_files = len(files)
    dl_done     = [0]
    dl_errors   = []
    dl_lock     = threading.Lock()

    def _dl_one(entry):
        rel_path = entry["path"]
        dest     = _remap_dlc_path(rel_path, install_dir)
        name     = entry.get("asset_name", os.path.basename(rel_path))
        url      = DLC_CDN_BASE + rel_path

        # Skip files that already exist at the expected size
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


# --- public API

def install_iw4x(game: dict, steam_root: str,
                 proton_path: str, compatdata_path: str,
                 on_progress=None, source: str = "steam",
                 install_dlc: bool = False,
                 remove_dlc: bool = False, force: bool = False):
    """
    Install or reinstall IW4x for Modern Warfare 2.

    Downloads iw4x.dll, release.zip, and the IW4x launcher concurrently.
    release.zip contents are relocated to the launcher-compatible layout.
    For Steam games, adds a "Play IW4x" launch menu entry (iw4x-launcher.exe --arch x86).
    """
    install_dir = game["install_dir"]
    _migrate_dlc_ff(install_dir)
    _migrate_old_layout(install_dir)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    base_end = 50 if install_dlc else 100

    def prog(pct, msg):
        if on_progress:
            scaled = int(pct / 100 * base_end)
            on_progress(scaled, msg)

    # The launcher updates the client and rawfiles at every start, so an existing
    # install (Reset Config, a re-run of the setup) skips the downloads. Update Games forces them.
    iw4x_dir = os.path.join(install_dir, "main", "iw4x", "x86")
    have = not force and not remove_dlc and os.path.isdir(iw4x_dir) and all(
        os.path.isfile(os.path.join(install_dir, f)) for f in ("iw4x.dll", "iw4x-launcher.exe"))
    if have:
        prog(70, "IW4x already installed, the launcher keeps it up to date.")
    else:
        # The launcher exe is extracted last, so it only exists after a finished
        # install. Removed first, a failed reinstall is not taken for a finished one.
        launcher_exe = os.path.join(install_dir, "iw4x-launcher.exe")
        if os.path.exists(launcher_exe):
            os.remove(launcher_exe)
        if os.path.exists(iw4x_dir):
            if remove_dlc:
                shutil.rmtree(iw4x_dir)
            else:
                for entry in os.listdir(iw4x_dir):
                    p = os.path.join(iw4x_dir, entry)
                    if os.path.isdir(p):
                        shutil.rmtree(p)
                    elif not entry.endswith(".iwd"):
                        os.remove(p)

        if remove_dlc:
            _remove_dlc_ff(install_dir)

        # --- Resolve URLs and sha256 digests
        # The launcher zip name is versioned, so its lookup has no fallback.
        prog(2, "Checking latest launcher version...")
        launcher_url, launcher_dg = github_asset("iw4x/launcher", "x86_64-windows.zip")
        dll_url, dll_dg = github_asset("iw4x/iw4x-client", "iw4x.dll", fallback=DLL_URL)
        zip_url, zip_dg = github_asset("iw4x/iw4x-rawfiles", "release.zip", fallback=ZIP_URL)

        # --- Download iw4x.dll, release.zip, and launcher concurrently
        prog(5, "Downloading iw4x files...")

        launcher_zip = os.path.join(install_dir, "launcher.zip")
        dl_tasks = [
            (dll_url,       os.path.join(install_dir, "iw4x.dll"), "iw4x.dll", dll_dg),
            (zip_url,       os.path.join(install_dir, "release.zip"), "release.zip", zip_dg),
            (launcher_url,  launcher_zip, "iw4x-launcher", launcher_dg),
        ]
        dl_errors = []
        dl_done   = [0]
        dl_lock   = threading.Lock()

        def _dl(url, dest, label, digest):
            _download(url, dest, None, f"Downloading {label}...", timeout=120, digest=digest)
            with dl_lock:
                dl_done[0] += 1
                prog(5 + int(dl_done[0] / len(dl_tasks) * 40), f"Downloaded {label}")

        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = {ex.submit(_dl, *t): t[2] for t in dl_tasks}
            for fut in as_completed(futs):
                try:
                    fut.result()
                except Exception as e:
                    dl_errors.append(f"{futs[fut]}: {e}")

        if dl_errors:
            raise RuntimeError("Download failed:\n" + "\n".join(dl_errors))

        # --- Extract release.zip and relocate to launcher layout
        prog(50, "Extracting release.zip...")
        zip_dest = os.path.join(install_dir, "release.zip")
        with zipfile.ZipFile(zip_dest) as zf:
            zf.extractall(install_dir)
        os.remove(zip_dest)

        prog(60, "Relocating files to launcher layout...")
        _relocate_extracted(install_dir)

        # --- Extract launcher
        prog(70, "Extracting iw4x-launcher...")
        with zipfile.ZipFile(launcher_zip) as zf:
            zf.extractall(install_dir)
        os.remove(launcher_zip)

    # --- Launch menu (Steam only)
    # The stock entry (tagged) stays vanilla MW2. "Play IW4x" runs the launcher
    # directly, which updates and then starts the x86 client. If Steam drops
    # the menu, the launch option's prelaunch.sh turns plain Play into IW4x.
    if source != "own":
        prog(80, "Adding IW4x to the Steam launch menu...")
        try:
            from wrapper import clear_launch_options, set_launch_options
            from steam_appinfo import add_launch_entries, VANILLA_TAG
            from steam_common import prelaunch_prefix
            clear_launch_options(steam_root, MW2_MP_APPID)
            set_launch_options(steam_root, MW2_MP_APPID,
                               'DECKOPS_MENU="iw4mp.exe=iw4x-launcher.exe" DECKOPS_MENU_ARGS="--arch x86" '
                               f'{prelaunch_prefix("menu")}%command%')
            if add_launch_entries(steam_root, MW2_MP_APPID,
                                  IW4X_MENU + [{"executable": "iw4mp.exe", "tag": VANILLA_TAG}]):
                prog(80, "  ✓ Launch menu: Play IW4x")
            else:
                prog(80, "  ⚠ Launch menu not added yet, will retry next time Steam is closed")
        except Exception as ex:
            prog(80, f"Could not add launch menu: {ex}")

    prog(100, "IW4x base installation complete!")

    # --- Optional DLC download
    if install_dlc:
        def dlc_prog(pct, msg):
            if on_progress:
                on_progress(50 + int(pct / 100 * 50), msg)
        install_iw4x_dlc(install_dir, on_progress=dlc_prog)
