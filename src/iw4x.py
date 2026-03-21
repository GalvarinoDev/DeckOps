"""
iw4x.py - DeckOps installer for IW4x (Modern Warfare 2)

Downloads iw4x.dll, iw4x.exe, release.zip and iwd files directly from
the latest GitHub release into the MW2 install folder. Proton handles
the rest — no wrapper, no DLL registration, no exe replacement needed.

Progress is reported via a callback:
    on_progress(percent: int, status: str)
"""

import os
import zipfile
import urllib.request

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
    """Returns True if iw4x.dll and iw4x.exe are present."""
    return (
        os.path.exists(os.path.join(install_dir, "iw4x.dll")) and
        os.path.exists(os.path.join(install_dir, "iw4x.exe"))
    )


# ── public API ────────────────────────────────────────────────────────────────

def install_iw4x(game: dict, steam_root: str,
                 proton_path: str, compatdata_path: str,
                 on_progress=None):
    """
    Install or reinstall IW4x for Modern Warfare 2.

    game            — entry from detect_games.find_installed_games()
    steam_root      — path to Steam root (unused, kept for API consistency)
    proton_path     — path to the proton executable (unused, kept for API consistency)
    compatdata_path — path to the MW2 compatdata prefix (unused, kept for API consistency)
    on_progress     — optional callback(percent: int, status: str)
    """
    install_dir = game["install_dir"]
    iw4x_dir    = os.path.join(install_dir, "iw4x")
    os.makedirs(iw4x_dir, exist_ok=True)

    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    # iw4x.dll
    prog(5, "Downloading iw4x.dll...")
    _download(f"{BASE_URL}/iw4x.dll",
              os.path.join(install_dir, "iw4x.dll"),
              lambda p, m: prog(5 + int(p * 0.15), m),
              "Downloading iw4x.dll...")

    # iw4x.exe
    prog(20, "Downloading iw4x.exe...")
    _download(f"{RAW_URL}/iw4x.exe",
              os.path.join(install_dir, "iw4x.exe"),
              lambda p, m: prog(20 + int(p * 0.15), m),
              "Downloading iw4x.exe...")

    # Rename iw4mp.exe → iw4mp.exe.bak, then copy iw4x.exe → iw4mp.exe
    # This lets Steam launch iw4x transparently via the existing shortcut
    iw4mp     = os.path.join(install_dir, "iw4mp.exe")
    iw4mp_bak = os.path.join(install_dir, "iw4mp.exe.bak")
    iw4x_exe  = os.path.join(install_dir, "iw4x.exe")
    if os.path.exists(iw4mp) and not os.path.exists(iw4mp_bak):
        os.rename(iw4mp, iw4mp_bak)
    if os.path.exists(iw4x_exe):
        import shutil as _sh
        _sh.copy2(iw4x_exe, iw4mp)

    # release.zip — extract then delete
    prog(35, "Downloading rawfiles...")
    zip_dest = os.path.join(install_dir, "release.zip")
    _download(f"{RAW_URL}/release.zip",
              zip_dest,
              lambda p, m: prog(35 + int(p * 0.25), m),
              "Downloading release.zip...")
    prog(60, "Extracting rawfiles...")
    with zipfile.ZipFile(zip_dest) as zf:
        zf.extractall(install_dir)
    os.remove(zip_dest)

    # iwd files → iw4x/ subfolder — downloaded in parallel
    prog(65, "Downloading iwd files...")
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    errors = []
    completed = 0
    total_iwds = len(IWD_FILES)
    lock = threading.Lock()

    def _download_iwd(iwd):
        nonlocal completed
        _download(
            f"{RAW_URL}/{iwd}",
            os.path.join(iw4x_dir, iwd),
            None,
            f"Downloading {iwd}...",
        )
        with lock:
            completed += 1
            pct = 65 + int(completed / total_iwds * 30)
            prog(pct, f"Downloaded {completed}/{total_iwds} iwd files...")

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
    Remove all IW4x files from the MW2 install folder.
    Restores iw4mp.exe from iw4mp.exe.bak if present, then removes iw4x files.
    """
    import shutil
    install_dir = game["install_dir"]

    # Restore iw4mp.exe from backup before removing iw4x files
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
