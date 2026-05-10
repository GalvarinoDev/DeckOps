"""
ge_proton.py - DeckOps GE-Proton installer

Downloads and installs the latest GE-Proton release from GitHub, then
writes the CompatToolMapping entry in Steam's config.vdf so each game
uses it automatically.

Also provides ensure_prefix_deps() which copies the full dependency set
(d3dx, vcrun, xinput, partial xact) from GE-Proton's default_pfx into
any game prefix that's missing them. This eliminates the need for users
to launch each game once before mods can be installed.

Install path:
    ~/.steam/root/compatibilitytools.d/GE-ProtonX-XX/

CompatToolMapping written to:
    ~/.local/share/Steam/config/config.vdf
"""

import json
import os
import shutil
import tarfile
import tempfile
import urllib.request

from log import get_logger

_log = get_logger(__name__)


GITHUB_API   = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest"
COMPAT_DIR   = os.path.expanduser("~/.local/share/Steam/compatibilitytools.d")

# Steam appids that DeckOps manages — GE-Proton will be set for all of these
MANAGED_APPIDS = [
    "7940",    # CoD4
    "10090",   # WaW
    "10180",   # MW2 SP
    "10190",   # MW2 MP
    "42680",   # MW3 SP
    "42690",   # MW3 MP
    "42750",   # MW3 Dedicated Server
    "42700",   # BO1 Campaign/Zombies
    "42710",   # BO1 Multiplayer
    "202970",  # BO2 Campaign
    "202990",  # BO2 Multiplayer
    "212910",  # BO2 Zombies
    "311210",  # BO3
    "209160",  # Ghosts SP
    "209170",  # Ghosts MP
    "209650",  # AW SP
    "209660",  # AW MP
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


def _get_local_version() -> str | None:
    """
    Scan compatibilitytools.d for the newest installed GE-Proton version.
    Returns the version string (e.g. 'GE-Proton10-32') or None if not found.
    Works regardless of how GE-Proton was installed (ProtonUp-Qt, manual, etc.)
    """
    import re
    if not os.path.isdir(COMPAT_DIR):
        return None

    def _version_key(name):
        parts = re.findall(r'\d+', name)
        return tuple(int(p) for p in parts)

    candidates = [
        d for d in os.listdir(COMPAT_DIR)
        if d.startswith("GE-Proton") and
        os.path.exists(os.path.join(COMPAT_DIR, d, "proton"))
    ]
    if not candidates:
        return None

    candidates.sort(key=_version_key, reverse=True)
    return candidates[0]


# ── default_pfx resolution ───────────────────────────────────────────────────

def _find_default_pfx(ge_version: str | None) -> str | None:
    """
    Locate GE-Proton's default_pfx directory.

    Tries the exact version first, then falls back to scanning for the
    newest available GE-Proton install. Returns the path or None.
    """
    # Try exact version first
    if ge_version:
        candidate = os.path.join(COMPAT_DIR, ge_version, "files", "share", "default_pfx")
        if os.path.isdir(candidate):
            return candidate

    # Fallback: newest GE-Proton that has a default_pfx
    if os.path.isdir(COMPAT_DIR):
        for entry in sorted(os.listdir(COMPAT_DIR), reverse=True):
            if not entry.startswith("GE-Proton"):
                continue
            candidate = os.path.join(COMPAT_DIR, entry, "files", "share", "default_pfx")
            if os.path.isdir(candidate):
                return candidate

    return None


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

    # Check if a local GE-Proton install already exists before hitting GitHub.
    # This handles both previous DeckOps installs and external tools like ProtonUp-Qt.
    local_version = _get_local_version()
    if local_version:
        prog(5, f"Found local GE-Proton: {local_version}. Checking for updates...")
    else:
        prog(0, "Checking latest GE-Proton release...")

    version, tarball_url, checksum_url = _get_latest_release()
    prog(5, f"Latest: {version}")

    if local_version == version:
        prog(100, f"GE-Proton {version} already installed — skipping download.")
        return version

    if _is_installed(version):
        prog(100, f"GE-Proton {version} already installed.")
        return version

    os.makedirs(COMPAT_DIR, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="deckops_ge_") as tmp:
        tarball_path = os.path.join(tmp, f"{version}.tar.gz")

        prog(10, f"Downloading GE-Proton {version}...")
        _download(tarball_url, tarball_path, on_progress=on_progress)

        if checksum_url:
            prog(85, "Verifying checksum...")
            if not _verify_checksum(tarball_path, checksum_url):
                raise RuntimeError("GE-Proton checksum mismatch — download may be corrupt")
            prog(87, "Checksum OK.")

        # Use system tar for speed and memory efficiency — Python's tarfile
        # module is noticeably slower and more memory-hungry when extracting
        # Python's tarfile module for large archives like GE-Proton.
        prog(87, f"Extracting {version}...")
        import subprocess
        result = subprocess.run(
            ["tar", "-xzf", tarball_path, "-C", COMPAT_DIR],
            capture_output=True,
        )
        if result.returncode != 0:
            # Fall back to Python tarfile if tar isn't available
            with tarfile.open(tarball_path, "r:gz") as tar:
                tar.extractall(COMPAT_DIR)
        prog(100, f"GE-Proton {version} installed.")

    return version


# ── CompatToolMapping ─────────────────────────────────────────────────────────
# Canonical implementation lives in wrapper.set_compat_tool.
# Imported here so callers can use ge_proton.set_compat_tool as before.

from wrapper import set_compat_tool  # noqa: F401


# ── Prefix dependency management ─────────────────────────────────────────────
# GE-Proton's default_pfx ships with the full d3dx, vcrun, xinput, and
# xact dependency set that these CoD games need. Instead of running
# winetricks verbs or relying on Steam to install them on first launch,
# we copy the DLLs directly from default_pfx into each game's prefix.
# This works for both Steam and own games.

def _copy_dlls(src_dir: str, dest_dir: str) -> tuple[int, int]:
    """
    Copy .dll files from src_dir into dest_dir, skipping files that
    already exist with a matching file size.

    Returns (copied, skipped) counts.
    """
    if not os.path.isdir(src_dir):
        return (0, 0)
    os.makedirs(dest_dir, exist_ok=True)
    copied = 0
    skipped = 0
    for fname in os.listdir(src_dir):
        if fname.lower().endswith(".dll"):
            src_path = os.path.join(src_dir, fname)
            dest_path = os.path.join(dest_dir, fname)
            # Skip if dest exists and matches source file size
            if os.path.isfile(dest_path):
                try:
                    if os.path.getsize(dest_path) == os.path.getsize(src_path):
                        skipped += 1
                        continue
                except OSError:
                    pass  # can't stat -- copy it
            # Unlock read-only files (Proton sometimes creates prefix
            # files with 0o444 permissions)
            if os.path.isfile(dest_path):
                try:
                    os.chmod(dest_path, 0o644)
                except OSError:
                    pass
            shutil.copy2(src_path, dest_path)
            copied += 1
    return (copied, skipped)


def ensure_prefix_deps(ge_version: str | None, prefix_path: str,
                       on_progress=None, proton_path: str | None = None,
                       steam_root: str | None = None) -> bool:
    """
    Make sure a game's compatdata prefix is fully initialized and has
    the complete dependency set from GE-Proton's default_pfx.

    Logic:
      1. If no proton_path, fall back to copytree from default_pfx and return.
      2. If pfx/drive_c already exists (prefix previously initialized):
         - Copy any missing DLLs from default_pfx (fast, no Proton run)
         - Skip the slow `proton run cmd /c exit` step entirely
      3. If pfx/drive_c does NOT exist (fresh prefix):
         - Create prefix_path so Proton has a directory to work with
         - Copy DLLs from default_pfx into system32 + syswow64
         - Run `proton run cmd /c exit` to finalize the prefix

    ge_version  -- GE-Proton version string (e.g. "GE-Proton10-33")
    prefix_path -- compatdata root (e.g. ~/.../compatdata/10090)
    on_progress -- optional callback(msg: str) for log messages
    proton_path -- path to the proton binary. When provided, the prefix is
                   finalized by Proton after DLL copy. Falls back to copytree
                   if not provided.
    steam_root  -- path to Steam root. Used for STEAM_COMPAT_CLIENT_INSTALL_PATH.
                   Falls back to deriving from proton_path if not provided.

    Returns True if deps are now in place, False if we couldn't do it.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    default_pfx = _find_default_pfx(ge_version)
    if not default_pfx:
        prog("⚠ No GE-Proton default_pfx found — cannot install dependencies")
        return False

    pfx_dir      = os.path.join(prefix_path, "pfx")
    sys32_target = os.path.join(pfx_dir, "drive_c", "windows", "system32")
    wow64_target = os.path.join(pfx_dir, "drive_c", "windows", "syswow64")
    version_file = os.path.join(prefix_path, "version")

    # Check if the prefix has already been initialized by Proton.
    # If drive_c exists, the prefix structure is in place — we only need
    # to copy any missing DLLs and can skip the slow Proton run.
    prefix_exists = os.path.isdir(os.path.join(pfx_dir, "drive_c"))

    # ── Fallback: no proton_path ───────────────────────────────────────
    # Can't run Proton to finalize — copy entire default_pfx as a best effort.
    if not proton_path:
        try:
            os.makedirs(prefix_path, exist_ok=True)
            if not os.path.isdir(pfx_dir):
                shutil.copytree(default_pfx, pfx_dir, symlinks=True)
            if ge_version and not os.path.isfile(version_file):
                with open(version_file, "w") as f:
                    f.write(ge_version + "\n")
            prog("  ✓ Prefix created from default_pfx (no Proton path — fallback)")
            return True
        except Exception as ex:
            prog(f"  ⚠ Prefix creation failed: {ex}")
            return False

    # STEAM_COMPAT_CLIENT_INSTALL_PATH should be the Steam root so Proton
    # can find steamclient.so. Fall back to dirname trick if not provided.
    _compat_install = steam_root or os.path.dirname(os.path.dirname(proton_path))

    # ── Step 1: Ensure the prefix directory exists ─────────────────────
    # Proton needs the compatdata directory to exist before it can initialize.
    # Don't create pfx/ itself — Proton does that in the finalize step.
    if not prefix_exists:
        os.makedirs(prefix_path, exist_ok=True)

    # ── Step 2: Always copy DLLs from default_pfx ─────────────────────
    # Copy before Proton finalizes so Proton sees the full dependency set
    # when it writes its management files.
    sys32_src = os.path.join(default_pfx, "drive_c", "windows", "system32")
    wow64_src = os.path.join(default_pfx, "drive_c", "windows", "syswow64")

    try:
        c32, s32 = _copy_dlls(sys32_src, sys32_target)
        c64, s64 = _copy_dlls(wow64_src, wow64_target)
        total_copied = c32 + c64
        total_skipped = s32 + s64
        if total_copied > 0:
            prog(f"  ✓ Copied {total_copied} DLLs, skipped {total_skipped} (already present)")
        else:
            prog(f"  ✓ All {total_skipped} DLLs already present")
    except Exception as ex:
        prog(f"  ⚠ DLL copy failed: {ex}")
        return False

    # ── Step 3: Finalize via Proton (only if prefix is new) ───────────
    # Only run `proton run cmd /c exit` when the prefix hasn't been
    # initialized yet. This is the slow step (~60s per prefix) that
    # creates the Wine prefix structure, wineserver, registry, etc.
    # For existing prefixes, the DLL copy above is sufficient.
    if prefix_exists:
        prog("  ✓ Prefix already initialized — skipped Proton run")
        return True

    import subprocess
    try:
        env = os.environ.copy()
        env["STEAM_COMPAT_DATA_PATH"]           = prefix_path
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = _compat_install
        subprocess.run(
            [proton_path, "run", "cmd", "/c", "exit"],
            env=env, capture_output=True, timeout=180,
        )
        prog("  ✓ Prefix finalized by Proton")
        return True
    except Exception as ex:
        prog(f"  ⚠ Proton prefix finalize failed: {ex}")
        return False


def _clone_prefix(source_pfx_dir: str, dest_prefix_path: str,
                  ge_version: str | None, on_progress=None) -> bool:
    """
    Clone an initialized prefix to a new appid's compatdata directory.

    Copies the pfx/ directory tree from a fully initialized source prefix,
    writes the version file, and copies tracked_files. This produces an
    identical prefix in ~2s instead of running `proton run cmd /c exit`
    (~60-180s).

    The donor prefix already contains all DLLs from default_pfx, so
    clones do NOT need a DLL top-up — skipping it saves ~45s per prefix
    on SD card.

    source_pfx_dir   -- the pfx/ directory inside the donor prefix
    dest_prefix_path -- the compatdata root for the target appid
    ge_version       -- GE-Proton version string for the version file
    on_progress      -- optional callback(msg: str)

    Returns True on success, False on failure.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    dest_pfx_dir = os.path.join(dest_prefix_path, "pfx")
    try:
        import time
        os.makedirs(dest_prefix_path, exist_ok=True)
        prog(f"  Cloning: {source_pfx_dir} → {dest_pfx_dir}")
        start = time.time()
        shutil.copytree(source_pfx_dir, dest_pfx_dir, symlinks=True)
        elapsed = time.time() - start
        # Write version file so Proton knows which version initialized this prefix
        if ge_version:
            version_file = os.path.join(dest_prefix_path, "version")
            with open(version_file, "w") as f:
                f.write(ge_version + "\n")
        # Copy tracked_files from the donor's parent directory.
        # Proton requires this file to exist — without it, prefix setup
        # crashes with FileNotFoundError on update_builtin_libs().
        donor_root = os.path.dirname(source_pfx_dir)
        donor_tracked = os.path.join(donor_root, "tracked_files")
        if os.path.isfile(donor_tracked):
            shutil.copy2(donor_tracked, os.path.join(dest_prefix_path, "tracked_files"))
        prog(f"  ✓ Prefix cloned from donor ({elapsed:.1f}s)")
        return True
    except Exception as ex:
        prog(f"  ⚠ Prefix clone failed: {ex}")
        return False


def _overlay_prefix(source_pfx_dir: str, dest_prefix_path: str,
                    ge_version: str | None, on_progress=None) -> bool:
    """
    Overlay a finalized donor prefix onto an existing prefix, copying
    only files that are missing or differ in size.

    For new prefixes (no pfx/ dir yet), this is equivalent to a full clone.
    For existing prefixes, this fills in any missing files without
    re-copying the ~1200 DLLs that are already there.

    Also copies tracked_files and writes the version file.

    source_pfx_dir   -- the pfx/ directory inside the donor prefix
    dest_prefix_path -- the compatdata root for the target appid
    on_progress      -- optional callback(msg: str)

    Returns True on success, False on failure.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    import time

    dest_pfx_dir = os.path.join(dest_prefix_path, "pfx")
    is_new = not os.path.isdir(dest_pfx_dir)

    try:
        os.makedirs(dest_prefix_path, exist_ok=True)

        if is_new:
            # Fresh prefix -- full clone (fastest path)
            prog(f"  Cloning: {source_pfx_dir} -> {dest_pfx_dir}")
            start = time.time()
            shutil.copytree(source_pfx_dir, dest_pfx_dir, symlinks=True)
            elapsed = time.time() - start
            prog(f"  ✓ Prefix cloned from donor ({elapsed:.1f}s)")
        else:
            # Existing prefix -- overlay missing files only
            start = time.time()
            copied = 0
            skipped = 0
            for src_dirpath, dirnames, filenames in os.walk(source_pfx_dir):
                rel = os.path.relpath(src_dirpath, source_pfx_dir)
                dst_dirpath = os.path.join(dest_pfx_dir, rel)
                os.makedirs(dst_dirpath, exist_ok=True)

                # Handle symlinked directories (e.g. dosdevices/c: -> ../drive_c,
                # d: -> /run/media/deck/...). Recreate as symlinks in the
                # destination instead of descending into the target.
                real_dirnames = []
                for dname in dirnames:
                    src_dir = os.path.join(src_dirpath, dname)
                    if os.path.islink(src_dir):
                        dst_dir = os.path.join(dst_dirpath, dname)
                        link_target = os.readlink(src_dir)
                        if os.path.islink(dst_dir) or os.path.exists(dst_dir):
                            skipped += 1
                        else:
                            os.symlink(link_target, dst_dir)
                            copied += 1
                    else:
                        real_dirnames.append(dname)
                dirnames[:] = real_dirnames

                for fname in filenames:
                    src_file = os.path.join(src_dirpath, fname)
                    dst_file = os.path.join(dst_dirpath, fname)

                    # Handle symlinked files (e.g. dosdevices/h:: -> /dev/sda2).
                    # Proton maps drive letters and block devices as symlinks
                    # in dosdevices/. These vary by hardware (nvme, sda, mmcblk)
                    # and distro (SteamOS, Bazzite, CachyOS). Copy them as
                    # symlinks rather than trying to read the target.
                    if os.path.islink(src_file):
                        link_target = os.readlink(src_file)
                        if os.path.islink(dst_file) or os.path.exists(dst_file):
                            skipped += 1
                        else:
                            os.symlink(link_target, dst_file)
                            copied += 1
                        continue

                    if os.path.exists(dst_file):
                        try:
                            if os.path.getsize(dst_file) == os.path.getsize(src_file):
                                skipped += 1
                                continue
                        except OSError:
                            pass
                    # Skip existing read-only files -- these are Proton
                    # prefix scaffolding (wordpad.exe, odbccp32.dll, etc.)
                    # that differ in size between Proton versions but are
                    # not needed by any game.  Game-critical DLLs are
                    # handled separately by _copy_dlls.
                    if os.path.exists(dst_file) and not os.access(dst_file, os.W_OK):
                        skipped += 1
                        continue
                    shutil.copy2(src_file, dst_file)
                    copied += 1

            elapsed = time.time() - start
            if copied > 0:
                prog(f"  ✓ Overlaid {copied} files, skipped {skipped} ({elapsed:.1f}s)")
            else:
                prog(f"  ✓ All {skipped} files already present ({elapsed:.1f}s)")

        # Write version file
        if ge_version:
            version_file = os.path.join(dest_prefix_path, "version")
            with open(version_file, "w") as f:
                f.write(ge_version + "\n")

        # Copy tracked_files from the donor's parent directory.
        # Proton requires this file -- without it, prefix setup
        # crashes with FileNotFoundError on update_builtin_libs().
        donor_root = os.path.dirname(source_pfx_dir)
        donor_tracked = os.path.join(donor_root, "tracked_files")
        if os.path.isfile(donor_tracked):
            shutil.copy2(donor_tracked, os.path.join(dest_prefix_path, "tracked_files"))

        return True
    except Exception as ex:
        prog(f"  ⚠ Prefix overlay failed: {ex}")
        return False


# ── Shared DLL directory for symlinked prefixes ───────────────────────────────
# Instead of copying 600MB+ of identical DLLs into every prefix, we keep
# one real copy and symlink each prefix's system32/syswow64 to it.
# This lives under DeckOps's data dir so Steam can't touch it.

SHARED_DLL_DIR = os.path.expanduser("~/.local/share/deckops/shared_dlls")


def _ensure_shared_dlls(ge_version: str | None, on_progress=None) -> bool:
    """
    Ensure the shared DLL directory exists with the full set of DLLs
    from GE-Proton's default_pfx.

    If the directory already has the expected file count, this is a no-op.
    Otherwise it copies system32 and syswow64 from default_pfx.

    Returns True if shared DLLs are ready, False on failure.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    default_pfx = _find_default_pfx(ge_version)
    if not default_pfx:
        prog("⚠ No GE-Proton default_pfx found -- cannot set up shared DLLs")
        return False

    shared_sys32 = os.path.join(SHARED_DLL_DIR, "system32")
    shared_wow64 = os.path.join(SHARED_DLL_DIR, "syswow64")
    src_sys32 = os.path.join(default_pfx, "drive_c", "windows", "system32")
    src_wow64 = os.path.join(default_pfx, "drive_c", "windows", "syswow64")

    # Check if already populated -- count DLLs in source vs dest
    if os.path.isdir(shared_sys32) and os.path.isdir(shared_wow64):
        src_count = sum(1 for f in os.listdir(src_sys32) if f.lower().endswith(".dll"))
        dst_count = sum(1 for f in os.listdir(shared_sys32) if f.lower().endswith(".dll"))
        if dst_count >= src_count:
            prog(f"  ✓ Shared DLLs verified ({dst_count} files)")
            return True

    import time
    prog("  Setting up shared DLL directory...")
    start = time.time()

    try:
        # Copy full directories from default_pfx -- includes all file types
        # not just DLLs (some .exe, .drv, etc. are also needed by Wine)
        if os.path.isdir(shared_sys32):
            shutil.rmtree(shared_sys32)
        if os.path.isdir(shared_wow64):
            shutil.rmtree(shared_wow64)
        os.makedirs(SHARED_DLL_DIR, exist_ok=True)
        shutil.copytree(src_sys32, shared_sys32)
        shutil.copytree(src_wow64, shared_wow64)
        elapsed = time.time() - start
        prog(f"  ✓ Shared DLLs ready ({elapsed:.1f}s)")
        return True
    except Exception as ex:
        prog(f"  ⚠ Shared DLL setup failed: {ex}")
        return False


def _clone_with_symlinks(source_pfx_dir: str, dest_prefix_path: str,
                         ge_version: str | None, on_progress=None) -> bool:
    """
    Clone a donor prefix but symlink system32 and syswow64 to the shared
    DLL directory instead of copying them. This reduces each clone from
    ~725MB to ~120MB.

    For the donor prefix itself, system32/syswow64 are real directories.
    All other prefixes get symlinks.

    source_pfx_dir   -- the pfx/ directory inside the donor prefix
    dest_prefix_path -- the compatdata root for the target appid
    ge_version       -- GE-Proton version string for the version file
    on_progress      -- optional callback(msg: str)

    Returns True on success, False on failure.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    import time

    dest_pfx_dir = os.path.join(dest_prefix_path, "pfx")

    try:
        os.makedirs(dest_prefix_path, exist_ok=True)
        start = time.time()

        # Copy the prefix skeleton -- everything except the heavy DLL dirs
        def _ignore_dll_dirs(directory, contents):
            # Only ignore at the windows/ level
            if os.path.basename(directory) == "windows":
                return [c for c in contents if c in ("system32", "syswow64")]
            return []

        prog(f"  Cloning skeleton: {source_pfx_dir} -> {dest_pfx_dir}")
        shutil.copytree(source_pfx_dir, dest_pfx_dir, symlinks=True,
                        ignore=_ignore_dll_dirs)

        # Create symlinks for system32 and syswow64 pointing to shared DLLs
        windows_dir = os.path.join(dest_pfx_dir, "drive_c", "windows")
        shared_sys32 = os.path.join(SHARED_DLL_DIR, "system32")
        shared_wow64 = os.path.join(SHARED_DLL_DIR, "syswow64")

        os.symlink(shared_sys32, os.path.join(windows_dir, "system32"))
        os.symlink(shared_wow64, os.path.join(windows_dir, "syswow64"))

        elapsed = time.time() - start
        prog(f"  ✓ Prefix cloned with symlinked DLLs ({elapsed:.1f}s)")

        # Write version file
        if ge_version:
            version_file = os.path.join(dest_prefix_path, "version")
            with open(version_file, "w") as f:
                f.write(ge_version + "\n")

        # Copy tracked_files
        donor_root = os.path.dirname(source_pfx_dir)
        donor_tracked = os.path.join(donor_root, "tracked_files")
        if os.path.isfile(donor_tracked):
            shutil.copy2(donor_tracked, os.path.join(dest_prefix_path, "tracked_files"))

        return True
    except Exception as ex:
        prog(f"  ⚠ Symlinked clone failed: {ex}")
        return False


def _cleanup_sd_card_prefixes(appids: list[str], on_progress=None):
    """
    Delete compatdata prefixes for managed appids from SD card locations.
    Prefixes now live on NVMe for performance. SD card copies are stale.
    """
    import glob

    def prog(msg):
        if on_progress:
            on_progress(msg)

    sd_patterns = [
        "/run/media/deck/*/steamapps/compatdata",
        "/run/media/deck/*/SteamLibrary/steamapps/compatdata",
        "/run/media/mmcblk0p1/steamapps/compatdata",
        "/run/media/mmcblk0p1/SteamLibrary/steamapps/compatdata",
    ]

    cleaned = 0
    for pattern in sd_patterns:
        for compat_dir in glob.glob(pattern):
            for appid in appids:
                prefix_dir = os.path.join(compat_dir, str(appid))
                if os.path.isdir(prefix_dir):
                    try:
                        shutil.rmtree(prefix_dir)
                        prog(f"  ✓ Removed SD card prefix for {appid}")
                        cleaned += 1
                    except Exception as ex:
                        prog(f"  ⚠ Failed to remove SD card prefix {appid}: {ex}")

    if cleaned > 0:
        prog(f"  ✓ Cleaned {cleaned} SD card prefix(es)")
    else:
        prog("  No SD card prefixes to clean up")


def _nvme_compatdata(appid: str) -> str:
    """Return the NVMe compatdata path for a given appid."""
    return os.path.join(
        os.path.expanduser("~/.local/share/Steam"),
        "steamapps", "compatdata", str(appid),
    )


def ensure_all_prefix_deps(ge_version: str | None, prefix_paths: list[tuple[str, str]],
                           on_progress=None, proton_path: str | None = None,
                           steam_root: str | None = None) -> int:
    """
    Initialize and install dependencies for a list of game prefixes.

    All prefixes are created on NVMe for performance. SD card prefixes
    for managed appids are deleted. Each prefix uses symlinked system32
    and syswow64 directories pointing to a shared DLL copy, reducing
    disk usage from ~8GB to ~1.9GB.

    Flow:
      1. Set up shared DLL directory from GE-Proton's default_pfx (one-time)
      2. Clean up any SD card prefixes for managed appids
      3. Override all prefix paths to NVMe
      4. Pick first prefix as donor -- initialize via Proton if new
      5. Clone donor to remaining prefixes using symlinked DLL dirs

    prefix_paths -- list of (label, compatdata_path) tuples
    on_progress  -- optional callback(msg: str)
    proton_path  -- path to the Proton binary for prefix initialization
    steam_root   -- path to Steam root for STEAM_COMPAT_CLIENT_INSTALL_PATH

    Returns the number of prefixes that now have deps installed.
    """
    import subprocess
    import time

    def prog(msg):
        if on_progress:
            on_progress(msg)

    default_pfx = _find_default_pfx(ge_version)
    if not default_pfx:
        prog("⚠ No GE-Proton default_pfx found -- cannot install dependencies")
        return 0

    # ── Step 1: Ensure shared DLLs exist ──────────────────────────────────
    if not _ensure_shared_dlls(ge_version, on_progress=on_progress):
        prog("⚠ Shared DLL setup failed -- falling back to full copies")
        # Fall back to the old approach if shared DLLs can't be set up
        shared_available = False
    else:
        shared_available = True

    # ── Step 2: Clean up SD card prefixes ─────────────────────────────────
    prog("  Cleaning up SD card prefixes...")
    _cleanup_sd_card_prefixes(
        [str(a) for a in MANAGED_APPIDS],
        on_progress=on_progress,
    )

    # ── Step 3: Deduplicate and override paths to NVMe ────────────────────
    seen_paths = {}
    unique_paths = []
    for label, compat_path in prefix_paths:
        if not compat_path:
            prog(f"  {label}: no compatdata path -- skipped")
            continue
        # Extract appid from the path and force NVMe location
        appid = os.path.basename(os.path.normpath(compat_path))
        nvme_path = _nvme_compatdata(appid)
        norm = os.path.normpath(nvme_path)
        if norm in seen_paths:
            prog(f"  {label}: shares prefix with {seen_paths[norm]} -- skipped")
            continue
        seen_paths[norm] = label
        unique_paths.append((label, nvme_path))

    if not unique_paths:
        return 0

    success = 0

    # ── Step 4: Prepare donor prefix ──────────────────────────────────────
    donor_label, donor_path = unique_paths[0]
    donor_pfx_dir = os.path.join(donor_path, "pfx")
    donor_exists = os.path.isdir(os.path.join(donor_pfx_dir, "drive_c"))

    if donor_exists:
        # Donor already on NVMe -- verify DLLs if it has real dirs (not symlinks)
        sys32_dir = os.path.join(donor_pfx_dir, "drive_c", "windows", "system32")
        if os.path.islink(sys32_dir):
            prog(f"  {donor_label}: donor already has symlinked DLLs -- ready")
        else:
            prog(f"  {donor_label}: verifying donor DLLs...")
            sys32_src = os.path.join(default_pfx, "drive_c", "windows", "system32")
            wow64_src = os.path.join(default_pfx, "drive_c", "windows", "syswow64")
            wow64_dir = os.path.join(donor_pfx_dir, "drive_c", "windows", "syswow64")
            try:
                c32, s32 = _copy_dlls(sys32_src, sys32_dir)
                c64, s64 = _copy_dlls(wow64_src, wow64_dir)
                total_copied = c32 + c64
                total_skipped = s32 + s64
                if total_copied > 0:
                    prog(f"  ✓ Donor: copied {total_copied} missing DLLs, {total_skipped} already present")
                else:
                    prog(f"  ✓ Donor: all {total_skipped} DLLs verified")
            except Exception as ex:
                prog(f"  ⚠ {donor_label}: donor DLL check failed: {ex}")
        success += 1
    else:
        # Donor needs Proton initialization
        if not proton_path:
            for label, compat_path in unique_paths:
                prog(f"  {label}: checking dependencies...")
                ok = ensure_prefix_deps(ge_version, compat_path,
                                        on_progress=on_progress,
                                        proton_path=None,
                                        steam_root=steam_root)
                if ok:
                    success += 1
            return success

        _compat_install = steam_root or os.path.dirname(os.path.dirname(proton_path))
        prog(f"  {donor_label}: initializing donor prefix on NVMe...")
        os.makedirs(donor_path, exist_ok=True)

        try:
            env = os.environ.copy()
            env["STEAM_COMPAT_DATA_PATH"]           = donor_path
            env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = _compat_install
            start = time.time()
            subprocess.run(
                [proton_path, "run", "cmd", "/c", "exit"],
                env=env, capture_output=True, timeout=600,
            )
            elapsed = time.time() - start
            prog(f"  ✓ Donor prefix finalized by Proton ({elapsed:.1f}s)")
            success += 1
        except Exception as ex:
            prog(f"  ⚠ Donor prefix finalize failed: {ex}")
            for label, compat_path in unique_paths[1:]:
                ok = ensure_prefix_deps(ge_version, compat_path,
                                        on_progress=on_progress,
                                        proton_path=proton_path,
                                        steam_root=steam_root)
                if ok:
                    success += 1
            return success

    # ── Step 5: Clone donor to remaining prefixes ─────────────────────────
    for label, compat_path in unique_paths[1:]:
        dest_pfx = os.path.join(compat_path, "pfx")
        dest_exists = os.path.isdir(os.path.join(dest_pfx, "drive_c"))

        if dest_exists:
            # Existing NVMe prefix -- check if already symlinked
            sys32_dir = os.path.join(dest_pfx, "drive_c", "windows", "system32")
            if os.path.islink(sys32_dir):
                prog(f"  {label}: already symlinked -- skipping")
                success += 1
                continue
            # Existing with real dirs -- overlay to fill in any gaps
            prog(f"  {label}: overlaying from donor...")
            ok = _overlay_prefix(donor_pfx_dir, compat_path, ge_version,
                                 on_progress=on_progress)
        elif shared_available:
            # New prefix -- clone with symlinked DLLs (fast)
            prog(f"  {label}: cloning with symlinked DLLs...")
            ok = _clone_with_symlinks(donor_pfx_dir, compat_path, ge_version,
                                      on_progress=on_progress)
        else:
            # Fallback -- full clone if shared DLLs aren't available
            prog(f"  {label}: cloning from donor (full copy)...")
            ok = _clone_prefix(donor_pfx_dir, compat_path, ge_version,
                               on_progress=on_progress)

        if not ok:
            prog(f"  {label}: clone failed, falling back to individual init...")
            ok = ensure_prefix_deps(ge_version, compat_path,
                                    on_progress=on_progress,
                                    proton_path=proton_path,
                                    steam_root=steam_root)
        if ok:
            success += 1

    return success


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
