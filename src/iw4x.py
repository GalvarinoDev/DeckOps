"""
iw4x.py - DeckOps installer for IW4x (Modern Warfare 2)

Downloads iw4x.dll, iw4x.exe and rawfiles from GitHub into the MW2 install
folder, then creates a wrapper script so Steam launches IW4x automatically.

Progress is reported via a callback so the PyQt5 UI can update its bar:
    on_progress(percent: int, status: str)
"""

import os
import stat
import shutil
import hashlib
import zipfile
import urllib.request
import urllib.error
import json
import tempfile

GITHUB_API   = "https://api.github.com"
CLIENT_REPO  = "iw4x/iw4x-client"
RAW_REPO     = "iw4x/iw4x-rawfiles"
METADATA_DIR = "iw4x-updoot"
METADATA_FILE = os.path.join(METADATA_DIR, "versions")
RAWLIST_FILE  = os.path.join(METADATA_DIR, "rawlist")


# ── helpers ──────────────────────────────────────────────────────────────────

def _get(url: str) -> bytes:
    """Simple HTTP GET, returns raw bytes."""
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "DeckOps",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _get_json(url: str) -> dict:
    return json.loads(_get(url))


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: str, on_progress=None, label: str = ""):
    """Download url to dest, calling on_progress(pct, label) as bytes arrive."""
    req = urllib.request.Request(url, headers={"User-Agent": "DeckOps"})
    with urllib.request.urlopen(req, timeout=60) as r:
        total = int(r.headers.get("Content-Length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if on_progress and total:
                    on_progress(int(downloaded / total * 100), label)


def _read_metadata(install_dir: str) -> dict:
    meta_path = os.path.join(install_dir, METADATA_FILE)
    result = {}
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            for line in f:
                if ":" in line:
                    k, v = line.strip().split(":", 1)
                    result[k.strip()] = v.strip()
    return result


def _write_metadata(install_dir: str, data: dict):
    meta_path = os.path.join(install_dir, METADATA_FILE)
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, "w") as f:
        for k, v in data.items():
            f.write(f"{k}: {v}\n")


# ── version checks ───────────────────────────────────────────────────────────

def get_latest_client_version() -> str:
    data = _get_json(f"{GITHUB_API}/repos/{CLIENT_REPO}/releases/latest")
    return data["name"]


def get_latest_rawfiles_version() -> str:
    data = _get_json(f"{GITHUB_API}/repos/{RAW_REPO}/releases/latest")
    return data["name"]


def is_iw4x_installed(install_dir: str) -> bool:
    """Returns True if iw4x.dll and iw4x.exe are present."""
    return (
        os.path.exists(os.path.join(install_dir, "iw4x.dll")) and
        os.path.exists(os.path.join(install_dir, "iw4x.exe"))
    )


def needs_update(install_dir: str) -> bool:
    """Returns True if installed versions differ from latest GitHub releases."""
    if not is_iw4x_installed(install_dir):
        return True
    meta = _read_metadata(install_dir)
    try:
        return (
            meta.get("client_version") != get_latest_client_version() or
            meta.get("rawfiles_version") != get_latest_rawfiles_version()
        )
    except Exception:
        return False  # if GitHub is unreachable, don't force update


# ── download steps ───────────────────────────────────────────────────────────

def _download_client(install_dir: str, on_progress=None):
    """Download iw4x.dll into install_dir and verify its checksum."""
    release = _get_json(f"{GITHUB_API}/repos/{CLIENT_REPO}/releases/latest")
    asset = next(a for a in release["assets"] if a["name"] == "iw4x.dll")
    url = asset["browser_download_url"]
    expected = asset["digest"].removeprefix("sha256:")

    dest = os.path.join(install_dir, "iw4x.dll")
    _download(url, dest, on_progress, "Downloading iw4x.dll...")
    actual = _sha256(dest)
    if actual != expected:
        os.remove(dest)
        raise RuntimeError(f"iw4x.dll checksum mismatch: {actual} != {expected}")


def _download_rawfiles(install_dir: str, on_progress=None):
    """Download iw4x.exe + rawfiles zip, verify checksums, extract."""
    release = _get_json(f"{GITHUB_API}/repos/{RAW_REPO}/releases/latest")
    assets = {a["name"]: a for a in release["assets"]}

    # Download iw4x.exe
    exe_asset = assets["iw4x.exe"]
    exe_dest = os.path.join(install_dir, "iw4x.exe")
    _download(exe_asset["browser_download_url"], exe_dest,
              on_progress, "Downloading iw4x.exe...")
    actual = _sha256(exe_dest)
    expected = exe_asset["digest"].removeprefix("sha256:")
    if actual != expected:
        os.remove(exe_dest)
        raise RuntimeError(f"iw4x.exe checksum mismatch")

    # Download release.zip (rawfiles)
    zip_asset = assets["release.zip"]
    zip_dest = os.path.join(install_dir, "release.zip")
    _download(zip_asset["browser_download_url"], zip_dest,
              on_progress, "Downloading rawfiles...")
    actual = _sha256(zip_dest)
    expected = zip_asset["digest"].removeprefix("sha256:")
    if actual != expected:
        os.remove(zip_dest)
        raise RuntimeError(f"release.zip checksum mismatch")

    # Record rawfile list before extracting so we can clean up later
    rawlist_path = os.path.join(install_dir, RAWLIST_FILE)
    os.makedirs(os.path.dirname(rawlist_path), exist_ok=True)
    with zipfile.ZipFile(zip_dest) as zf:
        with open(rawlist_path, "w") as rl:
            for name in zf.namelist():
                rl.write(name + "\n")
        if on_progress:
            on_progress(90, "Extracting rawfiles...")
        zf.extractall(install_dir)

    os.remove(zip_dest)


# ── wrapper script ───────────────────────────────────────────────────────────

def _write_wrapper(game: dict, proton_path: str,
                   compatdata_path: str, steam_root: str):
    """
    Back up the original iw4mp.exe then rename iw4x.exe to iw4mp.exe
    so Steam launches IW4x directly — no bash wrapper needed.
    """
    install_dir = game["install_dir"]
    iw4mp_exe   = os.path.join(install_dir, "iw4mp.exe")
    iw4x_exe    = os.path.join(install_dir, "iw4x.exe")

    # Back up original iw4mp.exe
    backup = iw4mp_exe + ".bak"
    if not os.path.exists(backup) and os.path.exists(iw4mp_exe):
        shutil.copy2(iw4mp_exe, backup)

    # Rename iw4x.exe → iw4mp.exe so it launches in place of the original
    if os.path.exists(iw4x_exe):
        shutil.copy2(iw4x_exe, iw4mp_exe)


# ── public API ───────────────────────────────────────────────────────────────

def install_iw4x(game: dict, steam_root: str,
                 proton_path: str, compatdata_path: str,
                 on_progress=None):
    """
    Full install/update flow for IW4x.

    game           — entry from detect_games.find_installed_games()
    steam_root     — path to Steam root
    proton_path    — path to the proton executable
    compatdata_path — path to the MW2 compatdata prefix
    on_progress    — optional callback(percent: int, status: str)
    """
    install_dir = game["install_dir"]

    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    prog(0, "Checking IW4x versions...")
    try:
        client_ver   = get_latest_client_version()
        rawfiles_ver = get_latest_rawfiles_version()
    except Exception as e:
        raise RuntimeError(f"Could not reach GitHub: {e}")

    meta = _read_metadata(install_dir)
    client_ok   = meta.get("client_version") == client_ver
    rawfiles_ok = meta.get("rawfiles_version") == rawfiles_ver

    if not client_ok:
        # Remove stale dll if present
        old_dll = os.path.join(install_dir, "iw4x.dll")
        if os.path.exists(old_dll):
            os.remove(old_dll)
        prog(10, f"Downloading iw4x client {client_ver}...")
        _download_client(install_dir, lambda p, m: prog(10 + p // 5, m))
        meta["client_version"] = client_ver
        prog(30, "Client downloaded.")
    else:
        prog(30, "IW4x client is up to date.")

    if not rawfiles_ok:
        prog(35, f"Downloading rawfiles {rawfiles_ver}...")
        _download_rawfiles(install_dir, lambda p, m: prog(35 + int(p * 0.55), m))
        meta["rawfiles_version"] = rawfiles_ver
        prog(90, "Rawfiles extracted.")
    else:
        prog(90, "IW4x rawfiles are up to date.")

    _write_metadata(install_dir, meta)

    prog(95, "Writing Steam wrapper script...")
    _write_wrapper(game, proton_path, compatdata_path, steam_root)

    prog(100, "IW4x installation complete!")


def uninstall_iw4x(game: dict):
    """
    Restore the original iw4mp.exe from backup and remove IW4x files.
    """
    install_dir = game["install_dir"]
    iw4mp_exe   = os.path.join(install_dir, "iw4mp.exe")
    backup      = iw4mp_exe + ".bak"

    if os.path.exists(backup):
        shutil.move(backup, iw4mp_exe)

    for fname in ["iw4x.dll", "iw4x.exe", "release.zip"]:
        p = os.path.join(install_dir, fname)
        if os.path.exists(p):
            os.remove(p)

    rawlist = os.path.join(install_dir, RAWLIST_FILE)
    if os.path.exists(rawlist):
        with open(rawlist) as f:
            for line in f:
                line = line.strip()
                if line and line != "zone/":
                    target = os.path.join(install_dir, line)
                    if os.path.exists(target):
                        if os.path.isdir(target):
                            shutil.rmtree(target, ignore_errors=True)
                        else:
                            os.remove(target)

    meta_dir = os.path.join(install_dir, METADATA_DIR)
    if os.path.exists(meta_dir):
        shutil.rmtree(meta_dir)
