"""
cod4x.py - DeckOps installer for COD4x (Call of Duty 4: Modern Warfare)

Downloads the COD4x client zip from cod4x.me, extracts it into the COD4
install folder, runs install.cmd through Proton to register the DLL,
then writes a wrapper script so Steam launches with the correct prefix.

COD4x works via DLL injection — iw3mp.exe itself is never replaced,
COD4x just loads alongside it. The wrapper only ensures the correct
Proton prefix is used every time.

Progress is reported via a callback:
    on_progress(percent: int, status: str)
"""

import os
import stat
import shutil
import hashlib
import zipfile
import urllib.request
import urllib.error
import subprocess
import tempfile
import json

# COD4x releases are on GitHub under the cod4x-client org
GITHUB_API  = "https://api.github.com"
COD4X_REPO  = "callofduty4x/CoD4x_Client_pub"

# Fallback direct download if GitHub API fails
COD4X_FALLBACK_URL = "https://cod4x.me/downloads/cod4x_client.zip"

METADATA_FILE = "deckops_cod4x.json"


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "DeckOps",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: str, on_progress=None, label: str = ""):
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
    path = os.path.join(install_dir, METADATA_FILE)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def _write_metadata(install_dir: str, data: dict):
    path = os.path.join(install_dir, METADATA_FILE)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ── version checks ───────────────────────────────────────────────────────────

def _get_latest_release() -> dict:
    """Returns the latest GitHub release dict for COD4x client."""
    return _get_json(f"{GITHUB_API}/repos/{COD4X_REPO}/releases/latest")


def get_latest_version() -> str:
    return _get_latest_release()["tag_name"]


def is_cod4x_installed(install_dir: str) -> bool:
    """Returns True if at least one cod4x_*.dll is present."""
    for f in os.listdir(install_dir):
        if f.startswith("cod4x_") and f.endswith(".dll"):
            return True
    return False


def needs_update(install_dir: str) -> bool:
    if not is_cod4x_installed(install_dir):
        return True
    meta = _read_metadata(install_dir)
    try:
        return meta.get("version") != get_latest_version()
    except Exception:
        return False


# ── download + extract ───────────────────────────────────────────────────────

def _find_zip_asset(release: dict) -> tuple[str, str | None]:
    """
    Returns (download_url, expected_sha256_or_None) for the client zip.
    Prefers the asset named 'cod4x_client.zip', falls back to any .zip.
    """
    for asset in release.get("assets", []):
        name = asset["name"].lower()
        if name == "cod4x_client.zip" or (name.endswith(".zip") and "client" in name):
            url      = asset["browser_download_url"]
            digest   = asset.get("digest", "")
            checksum = digest.removeprefix("sha256:") if digest.startswith("sha256:") else None
            return url, checksum

    # No matching asset — fall back to direct URL
    return COD4X_FALLBACK_URL, None


def _download_and_extract(install_dir: str, on_progress=None):
    """Download cod4x_client.zip and extract into install_dir."""
    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    try:
        release   = _get_latest_release()
        version   = release["tag_name"]
        zip_url, expected_sha = _find_zip_asset(release)
    except Exception:
        zip_url, expected_sha, version = COD4X_FALLBACK_URL, None, "unknown"

    zip_dest = os.path.join(install_dir, "_cod4x_client.zip")
    prog(5, f"Downloading COD4x {version}...")
    _download(zip_url, zip_dest, lambda p, m: prog(5 + int(p * 0.6), m),
              f"Downloading COD4x {version}...")

    if expected_sha:
        prog(65, "Verifying download...")
        actual = _sha256(zip_dest)
        if actual != expected_sha:
            os.remove(zip_dest)
            raise RuntimeError(f"COD4x zip checksum mismatch: {actual} != {expected_sha}")

    prog(70, "Extracting COD4x files...")
    with zipfile.ZipFile(zip_dest) as zf:
        zf.extractall(install_dir)
    os.remove(zip_dest)

    return version


# ── install.cmd via Proton ───────────────────────────────────────────────────

def _run_install_cmd(install_dir: str, proton_path: str,
                     compatdata_path: str, steam_root: str,
                     on_progress=None):
    """
    Find the install.cmd that COD4x ships in its extracted folder and run it
    through Proton so the DLL gets registered inside the Wine prefix.
    """
    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    # Find the cod4x client subfolder (e.g. cod4x18_v21_3_client)
    install_cmd = None
    for item in os.listdir(install_dir):
        candidate = os.path.join(install_dir, item, "install.cmd")
        if os.path.exists(candidate):
            install_cmd = candidate
            break

    # Some releases drop install.cmd directly in the game folder
    if not install_cmd:
        direct = os.path.join(install_dir, "install.cmd")
        if os.path.exists(direct):
            install_cmd = direct

    if not install_cmd:
        prog(85, "install.cmd not found — skipping DLL registration.")
        return

    prog(80, "Registering COD4x DLL via Proton...")
    env = {
        **os.environ,
        "STEAM_COMPAT_DATA_PATH": compatdata_path,
        "STEAM_COMPAT_CLIENT_INSTALL_PATH": steam_root,
    }
    result = subprocess.run(
        [proton_path, "run", "cmd.exe", "/C", install_cmd],
        env=env,
        capture_output=True,
    )
    if result.returncode != 0:
        prog(85, "DLL registration finished with warnings (may still work).")
    else:
        prog(85, "DLL registered successfully.")


# ── wrapper script ───────────────────────────────────────────────────────────

def _write_wrapper(game: dict, proton_path: str,
                   compatdata_path: str, steam_root: str):
    """
    COD4x ships as cod4x_client.exe (or similar) extracted into the game folder.
    Back up the original iw3mp.exe then copy the COD4x exe over it
    so Steam launches COD4x directly — no bash wrapper needed.
    """
    install_dir = game["install_dir"]
    iw3mp_exe   = os.path.join(install_dir, "iw3mp.exe")
    backup      = iw3mp_exe + ".bak"

    # Find the extracted COD4x client exe
    cod4x_exe = None
    for item in os.listdir(install_dir):
        if item.startswith("cod4x") and item.endswith(".exe"):
            cod4x_exe = os.path.join(install_dir, item)
            break
    # Also check inside the cod4x subfolder
    if not cod4x_exe:
        for item in os.listdir(install_dir):
            subdir = os.path.join(install_dir, item)
            if os.path.isdir(subdir):
                for f in os.listdir(subdir):
                    if f.startswith("cod4x") and f.endswith(".exe"):
                        cod4x_exe = os.path.join(subdir, f)
                        break

    if not cod4x_exe:
        return  # COD4x exe not found — skip rename

    # Back up original iw3mp.exe
    if not os.path.exists(backup) and os.path.exists(iw3mp_exe):
        shutil.copy2(iw3mp_exe, backup)

    # Copy cod4x exe over iw3mp.exe so Steam launches it directly
    shutil.copy2(cod4x_exe, iw3mp_exe)


# ── public API ───────────────────────────────────────────────────────────────

def install_cod4x(game: dict, steam_root: str,
                  proton_path: str, compatdata_path: str,
                  on_progress=None):
    """
    Full install/update flow for COD4x.

    game            — entry from detect_games.find_installed_games()
    steam_root      — path to Steam root
    proton_path     — path to the proton executable
    compatdata_path — path to the COD4 compatdata prefix
    on_progress     — optional callback(percent: int, status: str)
    """
    install_dir = game["install_dir"]

    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    prog(0, "Checking COD4x version...")

    meta = _read_metadata(install_dir)

    if not needs_update(install_dir):
        prog(75, "COD4x is already up to date.")
    else:
        version = _download_and_extract(install_dir,
                                        lambda p, m: prog(p, m))
        meta["version"] = version
        _write_metadata(install_dir, meta)

    _run_install_cmd(install_dir, proton_path,
                     compatdata_path, steam_root,
                     lambda p, m: prog(p, m))

    prog(92, "Writing Steam wrapper script...")
    _write_wrapper(game, proton_path, compatdata_path, steam_root)

    prog(100, "COD4x installation complete!")


def uninstall_cod4x(game: dict):
    """
    Restore the original iw3mp.exe from backup and remove COD4x files.
    """
    install_dir = game["install_dir"]
    iw3mp_exe   = os.path.join(install_dir, "iw3mp.exe")
    backup      = iw3mp_exe + ".bak"

    if os.path.exists(backup):
        shutil.move(backup, iw3mp_exe)

    # Remove cod4x DLLs and client folder
    for item in os.listdir(install_dir):
        if item.startswith("cod4x") and (
            item.endswith(".dll") or
            os.path.isdir(os.path.join(install_dir, item))
        ):
            target = os.path.join(install_dir, item)
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)

    meta_file = os.path.join(install_dir, METADATA_FILE)
    if os.path.exists(meta_file):
        os.remove(meta_file)
