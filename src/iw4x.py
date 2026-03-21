"""
iw4x.py - DeckOps installer for IW4x (Modern Warfare 2)

Downloads iw4x.dll, iw4x.exe, release.zip and iwd files directly from
the latest GitHub release into the MW2 install folder, then:
  - Renames iw4mp.exe -> iw4mp.exe.bak
  - Copies iw4x.exe -> iw4mp.exe

This lets Steam launch IW4x transparently via the existing shortcut
with no launch options or localconfig.vdf writes required.

Progress is reported via a callback:
    on_progress(percent: int, status: str)
"""

import os
import shutil
import zipfile
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://github.com/iw4x/iw4x-client/releases/latest/download"
RAW_URL  = "https://github.com/iw4x/iw4x-rawfiles/releases/latest/download"

IWD_FILES = [
    "iw4x_00.iwd",
    "iw4x_01.iwd",
    "iw4x_02.iwd",
    "iw4x_03.iwd",
    "iw4x_04.iwd",
    "iw4x_05.iwd",
]

_BROWSER_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _download(url: str, dest: str, on_progress=None, label: str = ""):
    """Download url to dest with optional progress callback. Retries up to 3 times."""
    import time
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=_BROWSER_UA)
            with urllib.request.urlopen(req, timeout=60) as r:
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
        except Exception as ex:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def is_iw4x_installed(install_dir: str) -> bool:
    """Returns True if iw4mp.exe.bak exists (meaning the mod rename is active)."""
    return os.path.exists(os.path.join(install_dir, "iw4mp.exe.bak"))


# ── public API ────────────────────────────────────────────────────────────────

def install_iw4x(game: dict, steam_root: str,
                 proton_path: str, compatdata_path: str,
                 on_progress=None):
    """
    Install or reinstall IW4x for Modern Warfare 2.

    Downloads iw4x.dll, iw4x.exe, release.zip, and iwd files concurrently,
    then renames iw4mp.exe -> iw4mp.exe.bak and copies iw4x.exe -> iw4mp.exe
    so Steam launches IW4x transparently. No launch options are written.

    game            — entry from detect_games.find_installed_games()
    steam_root      — path to Steam root (kept for API consistency)
    proton_path     — path to the proton executable (kept for API consistency)
    compatdata_path — path to the MW2 compatdata prefix (kept for API consistency)
    on_progress     — optional callback(percent: int, status: str)
    """
    install_dir = game["install_dir"]
    iw4x_dir    = os.path.join(install_dir, "iw4x")
    os.makedirs(iw4x_dir, exist_ok=True)

    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    # ── Download iw4x.dll, iw4x.exe, release.zip concurrently ────────────────
    prog(5, "Downloading iw4x files...")

    dl_tasks = [
        (f"{BASE_URL}/iw4x.dll",   os.path.join(install_dir, "iw4x.dll"),  "iw4x.dll"),
        (f"{RAW_URL}/iw4x.exe",    os.path.join(install_dir, "iw4x.exe"),   "iw4x.exe"),
        (f"{RAW_URL}/release.zip", os.path.join(install_dir, "release.zip"), "release.zip"),
    ]
    dl_errors = []
    dl_done   = [0]
    dl_lock   = threading.Lock()

    def _dl(url, dest, label):
        _download(url, dest, None, f"Downloading {label}...")
        with dl_lock:
            dl_done[0] += 1
            prog(5 + int(dl_done[0] / len(dl_tasks) * 45), f"Downloaded {label}")

    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(_dl, url, dest, label): label for url, dest, label in dl_tasks}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as e:
                dl_errors.append(f"{futs[fut]}: {e}")

    if dl_errors:
        raise RuntimeError("Download failed:\n" + "\n".join(dl_errors))

    # ── Extract release.zip ───────────────────────────────────────────────────
    prog(52, "Extracting rawfiles...")
    zip_dest = os.path.join(install_dir, "release.zip")
    with zipfile.ZipFile(zip_dest) as zf:
        zf.extractall(install_dir)
    os.remove(zip_dest)

    # ── Rename iw4mp.exe -> iw4mp.exe.bak, copy iw4x.exe -> iw4mp.exe ───────
    iw4mp     = os.path.join(install_dir, "iw4mp.exe")
    iw4mp_bak = os.path.join(install_dir, "iw4mp.exe.bak")
    iw4x_exe  = os.path.join(install_dir, "iw4x.exe")

    prog(57, "Replacing iw4mp.exe...")
    if os.path.exists(iw4mp) and not os.path.exists(iw4mp_bak):
        os.rename(iw4mp, iw4mp_bak)
    if os.path.exists(iw4x_exe):
        shutil.copy2(iw4x_exe, iw4mp)

    # ── iwd files -> iw4x/ subfolder concurrently ────────────────────────────
    prog(62, "Downloading iwd files...")
    errors    = []
    completed = [0]
    iwd_lock  = threading.Lock()

    def _download_iwd(iwd):
        dest = os.path.join(iw4x_dir, iwd)
        if not os.path.exists(dest):
            _download(f"{RAW_URL}/{iwd}", dest, None, f"Downloading {iwd}...")
        with iwd_lock:
            completed[0] += 1
            pct = 62 + int(completed[0] / len(IWD_FILES) * 33)
            prog(pct, f"Downloaded {completed[0]}/{len(IWD_FILES)} iwd files...")

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_download_iwd, iwd): iwd for iwd in IWD_FILES}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as ex:
                errors.append(f"{futures[future]}: {ex}")

    if errors:
        raise RuntimeError("iwd download failed:\n" + "\n".join(errors))

    prog(100, "IW4x installation complete!")


def uninstall_iw4x(game: dict):
    """
    Restore iw4mp.exe from iw4mp.exe.bak and remove all IW4x files.
    """
    install_dir = game["install_dir"]

    # Restore iw4mp.exe from backup
    iw4mp     = os.path.join(install_dir, "iw4mp.exe")
    iw4mp_bak = os.path.join(install_dir, "iw4mp.exe.bak")
    if os.path.exists(iw4mp_bak):
        if os.path.exists(iw4mp):
            os.remove(iw4mp)
        os.rename(iw4mp_bak, iw4mp)

    for fname in ["iw4x.dll", "iw4x.exe"]:
        p = os.path.join(install_dir, fname)
        if os.path.exists(p):
            os.remove(p)

    iw4x_dir = os.path.join(install_dir, "iw4x")
    if os.path.exists(iw4x_dir):
        shutil.rmtree(iw4x_dir)

    # Clean up old DeckOps metadata if upgrading from a previous install
    old_meta = os.path.join(install_dir, "iw4x-updoot")
    if os.path.exists(old_meta):
        shutil.rmtree(old_meta)
