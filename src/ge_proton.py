"""
ge_proton.py - DeckOps GE-Proton installer

Downloads and installs the latest GE-Proton release from GitHub, then
writes the CompatToolMapping entry in Steam's config.vdf so each game
uses it automatically.

Install path:
    ~/.steam/root/compatibilitytools.d/GE-ProtonX-XX/

CompatToolMapping written to:
    ~/.local/share/Steam/config/config.vdf
"""

import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.request

GITHUB_API   = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest"
COMPAT_DIR   = os.path.expanduser("~/.local/share/Steam/compatibilitytools.d")
STEAM_CONFIG = os.path.expanduser("~/.local/share/Steam/config/config.vdf")

# Steam appids that DeckOps manages — GE-Proton will be set for all of these
MANAGED_APPIDS = [
    "7940",    # CoD4
    "10090",   # WaW
    "10180",   # MW2 SP
    "10190",   # MW2 MP
    "42680",   # MW3 SP
    "42690",   # MW3 MP
    "42700",   # BO1 Campaign/Zombies
    "42710",   # BO1 Multiplayer
    "202970",  # BO2 Campaign
    "202990",  # BO2 Multiplayer
    "212910",  # BO2 Zombies
]

_BROWSER_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
}


# ── GitHub API ────────────────────────────────────────────────────────────────

def _get_latest_release():
    """
    Query the GitHub API for the latest GE-Proton release.
    Returns (version, tarball_url, checksum_url).
    """
    req = urllib.request.Request(GITHUB_API, headers=_BROWSER_UA)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    version = data["tag_name"]  # e.g. "GE-Proton10-28"
    tarball_url  = None
    checksum_url = None

    for asset in data.get("assets", []):
        name = asset["name"]
        if name.endswith(".tar.gz"):
            tarball_url = asset["browser_download_url"]
        elif name.endswith(".sha512sum"):
            checksum_url = asset["browser_download_url"]

    if not tarball_url:
        raise RuntimeError(f"No .tar.gz asset found for {version}")

    return version, tarball_url, checksum_url


def _is_installed(version):
    """Returns True if this GE-Proton version is already extracted."""
    return os.path.isdir(os.path.join(COMPAT_DIR, version))


# ── Download helpers ──────────────────────────────────────────────────────────

def _download(url, dest, on_progress=None):
    """Download a URL to dest with optional progress callback(percent, msg)."""
    req = urllib.request.Request(url, headers=_BROWSER_UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk = 1024 * 1024  # 1MB
        with open(dest, "wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                downloaded += len(buf)
                if on_progress and total:
                    pct = int(downloaded / total * 100)
                    mb = downloaded / 1024 / 1024
                    on_progress(pct, f"Downloading GE-Proton... {mb:.1f} MB")


def _verify_checksum(tarball_path, checksum_url):
    """Download the .sha512sum file and verify the tarball. Returns True if OK."""
    import hashlib
    req = urllib.request.Request(checksum_url, headers=_BROWSER_UA)
    with urllib.request.urlopen(req, timeout=15) as resp:
        checksum_data = resp.read().decode().strip()

    # Format: "<hash>  <filename>"
    expected_hash = checksum_data.split()[0]
    sha512 = hashlib.sha512()
    with open(tarball_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            sha512.update(chunk)
    return sha512.hexdigest() == expected_hash


# ── Install ───────────────────────────────────────────────────────────────────

def install_ge_proton(on_progress=None):
    """
    Download and install the latest GE-Proton to compatibilitytools.d.
    Returns the version string (e.g. 'GE-Proton10-28') so it can be
    passed to set_compat_tool().

    on_progress — optional callback(percent: int, msg: str)
    """
    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    prog(0, "Checking latest GE-Proton release...")
    version, tarball_url, checksum_url = _get_latest_release()
    prog(5, f"Latest: {version}")

    if _is_installed(version):
        prog(100, f"GE-Proton {version} already installed.")
        return version

    os.makedirs(COMPAT_DIR, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="deckops_ge_") as tmp:
        tarball_path = os.path.join(tmp, f"{version}.tar.gz")

        # Download
        prog(5, f"Downloading {version}...")
        _download(
            tarball_url,
            tarball_path,
            on_progress=lambda pct, msg: prog(5 + int(pct * 0.75), msg)
        )
        prog(80, "Download complete.")

        # Verify checksum if available
        if checksum_url:
            prog(82, "Verifying checksum...")
            if not _verify_checksum(tarball_path, checksum_url):
                raise RuntimeError("GE-Proton checksum verification failed — download may be corrupt.")
            prog(85, "Checksum OK.")
        else:
            prog(85, "No checksum file available — skipping verification.")

        # Extract
        prog(87, f"Extracting {version}...")
        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall(COMPAT_DIR)
        prog(100, f"GE-Proton {version} installed.")

    return version


# ── CompatToolMapping ─────────────────────────────────────────────────────────

def set_compat_tool(appids, version):
    """
    Write CompatToolMapping entries in Steam's config.vdf for each appid.
    Uses a simple text-based patch — finds or creates the CompatToolMapping
    block and inserts/updates each appid entry.

    appids  — list of appid strings, e.g. ["10190", "42690"]
    version — GE-Proton version string, e.g. "GE-Proton10-28"
    """
    if not os.path.exists(STEAM_CONFIG):
        raise FileNotFoundError(f"Steam config not found: {STEAM_CONFIG}")

    with open(STEAM_CONFIG, "r", encoding="utf-8") as f:
        data = f.read()

    for appid in appids:
        entry = (
            f'\t\t\t\t"{appid}"\n'
            f'\t\t\t\t{{\n'
            f'\t\t\t\t\t"name"\t\t"{version}"\n'
            f'\t\t\t\t\t"config"\t\t""\n'
            f'\t\t\t\t\t"Priority"\t\t"250"\n'
            f'\t\t\t\t}}\n'
        )

        # If appid block already exists, replace it
        pattern = rf'(\t+"{re.escape(appid)}"\n\t+\{{[^}}]*\}})'
        if re.search(pattern, data, re.MULTILINE):
            data = re.sub(pattern, entry.rstrip('\n'), data, flags=re.MULTILINE)
        else:
            # Insert before closing brace of CompatToolMapping block
            data = re.sub(
                r'("CompatToolMapping"\s*\{)',
                r'\1\n' + entry,
                data,
                count=1
            )

    # Create CompatToolMapping block if it doesn't exist at all
    if '"CompatToolMapping"' not in data:
        block = (
            '\t\t\t"CompatToolMapping"\n'
            '\t\t\t{\n'
        )
        for appid in appids:
            block += (
                f'\t\t\t\t"{appid}"\n'
                f'\t\t\t\t{{\n'
                f'\t\t\t\t\t"name"\t\t"{version}"\n'
                f'\t\t\t\t\t"config"\t\t""\n'
                f'\t\t\t\t\t"Priority"\t\t"250"\n'
                f'\t\t\t\t}}\n'
            )
        block += '\t\t\t}\n'
        # Insert before closing of Software/Valve/Steam block
        data = re.sub(
            r'("Steam"\s*\{)',
            r'\1\n' + block,
            data,
            count=1
        )

    with open(STEAM_CONFIG, "w", encoding="utf-8") as f:
        f.write(data)


# ── Public API ────────────────────────────────────────────────────────────────

def setup_ge_proton(on_progress=None):
    """
    Full setup: install latest GE-Proton and set it for all managed appids.
    Call this from ui_qt.py early in the install flow.

    Returns the installed version string.
    """
    def prog(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    version = install_ge_proton(on_progress=on_progress)
    prog(0, f"Setting GE-Proton {version} for all games...")
    set_compat_tool(MANAGED_APPIDS, version)
    prog(100, f"✓  GE-Proton {version} set for all games.")
    return version
