"""
ge_proton.py - DeckOps GE-Proton installer

Downloads and installs the latest GE-Proton release from GitHub.
set_compat_tool (from wrapper) writes the CompatToolMapping entry in
Steam's config.vdf so each game uses it.

ensure_prefix_deps() copies the full dependency set (d3dx, vcrun, xinput,
partial xact) from GE-Proton's default_pfx into any game prefix that is
missing it, so users don't have to launch each game once before mods
can be installed.

Install path:
    ~/.local/share/Steam/compatibilitytools.d/GE-Proton<version>-<arch>/

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
from net import BROWSER_UA as _BROWSER_UA, download
from steam_common import nvme_compatdata as _nvme_compatdata, newest_proton_dir

_log = get_logger(__name__)


GITHUB_API   = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest"
COMPAT_DIR   = os.path.expanduser("~/.local/share/Steam/compatibilitytools.d")

# Steam appids DeckOps manages. All of them get GE-Proton.
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
    # Classics: DeckOps builds their prefixes from GE-Proton too. Under Steam's
    # Proton the compatibility script (CD key, uninstall) hangs in them.
    "2620",    # CoD1
    "2640",    # UO
    "2630",    # CoD2
]


# --- GitHub API

def _get_latest_release():
    """
    Query the GitHub API for the latest GE-Proton release.
    Returns (version, tarball_url, checksum_url, dir_name).
    """
    req = urllib.request.Request(GITHUB_API, headers=_BROWSER_UA)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    version = data["tag_name"]  # e.g. "GE-Proton11-7"
    tarball_url  = None
    checksum_url = None
    tarball_asset = None

    from detect_hw import detect_arch
    arch = detect_arch()

    for asset in data.get("assets", []):
        name = asset["name"]
        if name.endswith(f"-{arch}.tar.gz"):
            tarball_url = asset["browser_download_url"]
            tarball_asset = name
        elif name.endswith(f"-{arch}.sha512sum"):
            checksum_url = asset["browser_download_url"]

    if not tarball_url:
        raise RuntimeError(f"No {arch} .tar.gz asset found for {version}")

    # GE-Proton 11+ tarballs extract to the asset name minus .tar.gz
    # (e.g. "GE-Proton11-7-x86_64"), not the tag. Steam registers compat
    # tools by folder name, so dir_name has to match the extracted folder.
    dir_name = tarball_asset.removesuffix(".tar.gz")

    return version, tarball_url, checksum_url, dir_name


def _is_installed(version):
    """Returns True if this GE-Proton version is already extracted."""
    return os.path.isdir(os.path.join(COMPAT_DIR, version))


def _get_local_version() -> str | None:
    """
    Scan compatibilitytools.d for the newest installed GE-Proton version.
    Returns the version string (e.g. 'GE-Proton10-32') or None.
    Finds it however GE-Proton was installed (ProtonUp-Qt, by hand, etc.).
    """
    return newest_proton_dir(COMPAT_DIR, "GE-Proton")


# --- default_pfx lookup

def _find_default_pfx(ge_version: str | None) -> str | None:
    """
    Locate GE-Proton's default_pfx directory.

    Tries the exact version first, then the newest GE-Proton install
    that has one. Returns the path or None.
    """
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


# --- Install

def install_ge_proton(on_progress=None):
    """
    Download and install the latest GE-Proton to compatibilitytools.d.
    Returns the version string (e.g. 'GE-Proton10-34') for
    set_compat_tool().

    on_progress: optional callback(percent: int, msg: str)
    """
    prog = on_progress or (lambda *a: None)

    local_version = _get_local_version()
    prog(0, "Checking for GE-Proton updates...")

    version, tarball_url, checksum_url, dir_name = _get_latest_release()

    if local_version == dir_name:
        prog(100, f"GE-Proton {dir_name} is up to date.")
        return dir_name

    if _is_installed(dir_name):
        prog(100, f"GE-Proton {dir_name} is up to date.")
        return dir_name

    prog(5, f"New version available: {dir_name}")
    os.makedirs(COMPAT_DIR, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="deckops_ge_") as tmp:
        tarball_path = os.path.join(tmp, f"{dir_name}.tar.gz")

        digest = None
        if checksum_url:
            # Format: "<hash>  <filename>". net.download verifies it and
            # retries a mismatch instead of failing the install outright.
            req = urllib.request.Request(checksum_url, headers=_BROWSER_UA)
            with urllib.request.urlopen(req, timeout=15) as resp:
                digest = "sha512:" + resp.read().decode().split()[0]

        prog(10, f"Downloading {dir_name}...")
        download(tarball_url, tarball_path, on_progress=on_progress, label=dir_name,
                 digest=digest)

        # System tar, because Python's tarfile is much slower and uses more
        # memory on an archive as large as GE-Proton.
        prog(87, f"Extracting {dir_name}...")
        import subprocess
        result = subprocess.run(
            ["tar", "-xzf", tarball_path, "-C", COMPAT_DIR],
            capture_output=True,
        )
        if result.returncode != 0:
            # tar failed or is missing. Use Python's tarfile.
            with tarfile.open(tarball_path, "r:gz") as tar:
                tar.extractall(COMPAT_DIR)
        prog(100, f"GE-Proton {dir_name} installed.")

    return dir_name


# --- CompatToolMapping
# The real code is wrapper.set_compat_tool. Re-exported here so
# ge_proton.set_compat_tool also works.

from wrapper import set_compat_tool  # noqa: F401


# --- Prefix dependencies
# GE-Proton's default_pfx ships the d3dx, vcrun, xinput and xact DLLs
# these CoD games need. We copy them from default_pfx into each game's
# prefix instead of running winetricks or waiting for Steam to install
# them on first launch. Works for Steam and own games.

def _drop_dead_link(path):
    # Proton links prefix DLLs into its own folder. When that GE-Proton version is
    # removed the links point nowhere, and copy2 would follow one into the missing folder.
    if os.path.islink(path) and not os.path.exists(path):
        os.remove(path)


def _copy_dlls(src_dir: str, dest_dir: str) -> tuple[int, int]:
    """
    Copy .dll files from src_dir into dest_dir. Files already there with
    the same size are skipped.

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
            if os.path.isfile(dest_path):
                try:
                    if os.path.getsize(dest_path) == os.path.getsize(src_path):
                        skipped += 1
                        continue
                except OSError:
                    pass  # can't stat it, so copy it
            # Proton sometimes creates prefix files as 0o444. Make them
            # writable first.
            if os.path.isfile(dest_path):
                try:
                    os.chmod(dest_path, 0o644)
                except OSError:
                    pass
            _drop_dead_link(dest_path)
            shutil.copy2(src_path, dest_path)
            copied += 1
    return (copied, skipped)


def ensure_prefix_deps(ge_version: str | None, prefix_path: str,
                       on_progress=None, proton_path: str | None = None,
                       steam_root: str | None = None) -> bool:
    """
    Make sure a game's compatdata prefix is initialized and has the full
    dependency set from GE-Proton's default_pfx.

    Steps:
      1. No proton_path: copy the whole default_pfx and return.
      2. pfx/drive_c exists (prefix already initialized):
         - Copy any missing DLLs from default_pfx (fast, no Proton run)
         - Skip the slow `proton run cmd /c exit`
      3. pfx/drive_c missing (fresh prefix):
         - Create prefix_path so Proton has a folder to work in
         - Copy DLLs from default_pfx into system32 + syswow64
         - Run `proton run cmd /c exit` to finalize the prefix

    ge_version:  GE-Proton version string (e.g. "GE-Proton10-33")
    prefix_path: compatdata root (e.g. ~/.../compatdata/10090)
    on_progress: optional callback(msg: str) for log messages
    proton_path: path to the proton binary. If set, Proton finalizes the
                 prefix after the DLL copy. If not, default_pfx is copied.
    steam_root:  Steam root, used for STEAM_COMPAT_CLIENT_INSTALL_PATH.
                 If not set, it is derived from proton_path.

    Returns True if the deps are in place, False if not.
    """
    prog = on_progress or (lambda *a: None)

    default_pfx = _find_default_pfx(ge_version)
    if not default_pfx:
        prog("⚠ No GE-Proton default_pfx found — cannot install dependencies")
        return False

    pfx_dir      = os.path.join(prefix_path, "pfx")
    sys32_target = os.path.join(pfx_dir, "drive_c", "windows", "system32")
    wow64_target = os.path.join(pfx_dir, "drive_c", "windows", "syswow64")
    version_file = os.path.join(prefix_path, "version")

    # drive_c means Proton already initialized this prefix. Then we only
    # copy missing DLLs and skip the slow Proton run.
    prefix_exists = os.path.isdir(os.path.join(pfx_dir, "drive_c"))

    # --- Fallback: no proton_path
    # Proton can't finalize, so copy the whole default_pfx as a best effort.
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

    # STEAM_COMPAT_CLIENT_INSTALL_PATH must be the Steam root so Proton
    # can find steamclient.so. Without steam_root, go two levels up from
    # proton_path.
    _compat_install = steam_root or os.path.dirname(os.path.dirname(proton_path))

    # --- Step 1: make sure the prefix folder exists
    # Proton needs the compatdata folder before it can initialize. Don't
    # create pfx/ itself. Proton does that in the finalize step.
    if not prefix_exists:
        os.makedirs(prefix_path, exist_ok=True)

    # --- Step 2: always copy DLLs from default_pfx
    # Copy before Proton finalizes, so Proton sees the full dependency set
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

    # --- Step 3: finalize with Proton (new prefix only)
    # `proton run cmd /c exit` is the slow step (~60s per prefix). It
    # builds the Wine prefix, starts wineserver, writes the registry, etc.
    # An existing prefix only needs the DLL copy above.
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


def _finish_clone(source_pfx_dir: str, dest_prefix_path: str, ge_version: str | None):
    # The version file tells Proton which version initialized this prefix
    if ge_version:
        with open(os.path.join(dest_prefix_path, "version"), "w") as f:
            f.write(ge_version + "\n")
    # Copy tracked_files from the donor's compatdata root. Proton needs
    # it. Without it, prefix setup crashes with FileNotFoundError in
    # update_builtin_libs().
    donor_tracked = os.path.join(os.path.dirname(source_pfx_dir), "tracked_files")
    if os.path.isfile(donor_tracked):
        shutil.copy2(donor_tracked, os.path.join(dest_prefix_path, "tracked_files"))


def _clone_prefix(source_pfx_dir: str, dest_prefix_path: str,
                  ge_version: str | None, on_progress=None) -> bool:
    """
    Clone an initialized prefix to a new appid's compatdata directory.

    Copies the pfx/ tree from an initialized source prefix, writes the
    version file and copies tracked_files. That gives an identical prefix
    in ~2s, where `proton run cmd /c exit` takes ~60-180s.

    The donor already has every DLL from default_pfx, so clones skip the
    DLL top-up. That saves ~45s per prefix on SD card.

    source_pfx_dir:   the pfx/ folder inside the donor prefix
    dest_prefix_path: the compatdata root for the target appid
    ge_version:       GE-Proton version string for the version file
    on_progress:      optional callback(msg: str)

    Returns True on success, False on failure.
    """
    prog = on_progress or (lambda *a: None)

    dest_pfx_dir = os.path.join(dest_prefix_path, "pfx")
    try:
        import time
        os.makedirs(dest_prefix_path, exist_ok=True)
        prog(f"  Cloning: {source_pfx_dir} → {dest_pfx_dir}")
        start = time.time()
        shutil.copytree(source_pfx_dir, dest_pfx_dir, symlinks=True)
        elapsed = time.time() - start
        _finish_clone(source_pfx_dir, dest_prefix_path, ge_version)
        prog(f"  ✓ Prefix cloned from donor ({elapsed:.1f}s)")
        return True
    except Exception as ex:
        prog(f"  ⚠ Prefix clone failed: {ex}")
        return False


def _overlay_prefix(source_pfx_dir: str, dest_prefix_path: str,
                    ge_version: str | None, on_progress=None) -> bool:
    """
    Overlay a finalized donor prefix onto an existing prefix. Only files
    that are missing or differ in size are copied.

    A new prefix (no pfx/ yet) gets a full clone. An existing prefix gets
    its missing files without re-copying the ~1200 DLLs already there.

    Also copies tracked_files and writes the version file.

    source_pfx_dir:   the pfx/ folder inside the donor prefix
    dest_prefix_path: the compatdata root for the target appid
    ge_version:       GE-Proton version string for the version file
    on_progress:      optional callback(msg: str)

    Returns True on success, False on failure.
    """
    prog = on_progress or (lambda *a: None)

    import time

    dest_pfx_dir = os.path.join(dest_prefix_path, "pfx")
    is_new = not os.path.isdir(dest_pfx_dir)

    try:
        os.makedirs(dest_prefix_path, exist_ok=True)

        if is_new:
            # Fresh prefix: full clone (fastest path)
            prog(f"  Cloning: {source_pfx_dir} -> {dest_pfx_dir}")
            start = time.time()
            shutil.copytree(source_pfx_dir, dest_pfx_dir, symlinks=True)
            elapsed = time.time() - start
            prog(f"  ✓ Prefix cloned from donor ({elapsed:.1f}s)")
        else:
            # Existing prefix: copy only missing files
            start = time.time()
            copied = 0
            skipped = 0
            for src_dirpath, dirnames, filenames in os.walk(source_pfx_dir):
                rel = os.path.relpath(src_dirpath, source_pfx_dir)
                dst_dirpath = os.path.join(dest_pfx_dir, rel)
                os.makedirs(dst_dirpath, exist_ok=True)

                # Symlinked folders (e.g. dosdevices/c: -> ../drive_c,
                # d: -> /run/media/deck/...) are recreated as symlinks in the
                # destination. We don't walk into their targets.
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

                    # Symlinked files (e.g. dosdevices/h:: -> /dev/sda2).
                    # Proton maps drive letters and block devices as symlinks
                    # in dosdevices/. They vary by hardware (nvme, sda, mmcblk)
                    # and distro (SteamOS, Bazzite, CachyOS). Copy the link
                    # itself and never read the target.
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
                    # Skip existing read-only files. They are Proton prefix
                    # scaffolding (wordpad.exe, odbccp32.dll, etc.) that
                    # differs in size between Proton versions, and no game
                    # needs it. _copy_dlls handles the DLLs games need.
                    if os.path.exists(dst_file) and not os.access(dst_file, os.W_OK):
                        skipped += 1
                        continue
                    _drop_dead_link(dst_file)
                    shutil.copy2(src_file, dst_file)
                    copied += 1

            elapsed = time.time() - start
            if copied > 0:
                prog(f"  ✓ Overlaid {copied} files, skipped {skipped} ({elapsed:.1f}s)")
            else:
                prog(f"  ✓ All {skipped} files already present ({elapsed:.1f}s)")

        _finish_clone(source_pfx_dir, dest_prefix_path, ge_version)
        return True
    except Exception as ex:
        prog(f"  ⚠ Prefix overlay failed: {ex}")
        return False


# --- Shared DLL folder for symlinked prefixes
# One real copy of the 600MB+ of DLLs. Each prefix's system32/syswow64
# is a symlink to it. It lives in DeckOps's data dir so Steam can't
# touch it.

SHARED_DLL_DIR = os.path.expanduser("~/.local/share/deckops/shared_dlls")


def _ensure_shared_dlls(ge_version: str | None, on_progress=None) -> bool:
    """
    Make sure the shared DLL folder has the full DLL set from
    GE-Proton's default_pfx.

    Does nothing if the folder already has the expected DLL count.
    Otherwise copies system32 and syswow64 from default_pfx.

    Returns True if shared DLLs are ready, False on failure.
    """
    prog = on_progress or (lambda *a: None)

    default_pfx = _find_default_pfx(ge_version)
    if not default_pfx:
        prog("⚠ No GE-Proton default_pfx found -- cannot set up shared DLLs")
        return False

    shared_sys32 = os.path.join(SHARED_DLL_DIR, "system32")
    shared_wow64 = os.path.join(SHARED_DLL_DIR, "syswow64")
    src_sys32 = os.path.join(default_pfx, "drive_c", "windows", "system32")
    src_wow64 = os.path.join(default_pfx, "drive_c", "windows", "syswow64")

    # Already filled? Compare DLL counts in source and dest.
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
        # Copy the whole folders, not just DLLs. Wine also needs some
        # .exe, .drv, etc. files from them.
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
    Clone a donor prefix, with system32 and syswow64 as symlinks to the
    shared DLL folder instead of copies. Each clone drops from ~725MB to
    ~120MB.

    The donor prefix keeps real system32/syswow64 folders. All other
    prefixes get symlinks.

    source_pfx_dir:   the pfx/ folder inside the donor prefix
    dest_prefix_path: the compatdata root for the target appid
    ge_version:       GE-Proton version string for the version file
    on_progress:      optional callback(msg: str)

    Returns True on success, False on failure.
    """
    prog = on_progress or (lambda *a: None)

    import time

    dest_pfx_dir = os.path.join(dest_prefix_path, "pfx")

    try:
        os.makedirs(dest_prefix_path, exist_ok=True)
        start = time.time()

        # Copy the prefix skeleton: everything except the big DLL folders
        def _ignore_dll_dirs(directory, contents):
            # Only ignore at the windows/ level
            if os.path.basename(directory) == "windows":
                return [c for c in contents if c in ("system32", "syswow64")]
            return []

        prog(f"  Cloning skeleton: {source_pfx_dir} -> {dest_pfx_dir}")
        shutil.copytree(source_pfx_dir, dest_pfx_dir, symlinks=True,
                        ignore=_ignore_dll_dirs)

        # Point system32 and syswow64 at the shared DLLs
        windows_dir = os.path.join(dest_pfx_dir, "drive_c", "windows")
        shared_sys32 = os.path.join(SHARED_DLL_DIR, "system32")
        shared_wow64 = os.path.join(SHARED_DLL_DIR, "syswow64")

        os.symlink(shared_sys32, os.path.join(windows_dir, "system32"))
        os.symlink(shared_wow64, os.path.join(windows_dir, "syswow64"))

        elapsed = time.time() - start
        prog(f"  ✓ Prefix cloned with symlinked DLLs ({elapsed:.1f}s)")

        _finish_clone(source_pfx_dir, dest_prefix_path, ge_version)
        return True
    except Exception as ex:
        prog(f"  ⚠ Symlinked clone failed: {ex}")
        return False


def _cleanup_sd_card_prefixes(appids: list[str], on_progress=None):
    """
    Delete compatdata prefixes for managed appids on the SD card.
    Prefixes live on NVMe for speed, so SD card copies are stale.
    """
    import glob

    prog = on_progress or (lambda *a: None)

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


def ensure_all_prefix_deps(ge_version: str | None, prefix_paths: list[tuple[str, str]],
                           on_progress=None, proton_path: str | None = None,
                           steam_root: str | None = None) -> int:
    """
    Initialize and install dependencies for a list of game prefixes.

    All prefixes go on NVMe for speed, and SD card prefixes for managed
    appids are deleted. Each prefix's system32 and syswow64 are symlinks
    to one shared DLL copy, which cuts disk use from ~8GB to ~1.9GB.

    Flow:
      1. Set up the shared DLL folder from GE-Proton's default_pfx (once)
      2. Delete SD card prefixes for managed appids
      3. Move every prefix path to NVMe
      4. Use the first prefix as donor. Initialize it with Proton if new
      5. Clone the donor to the other prefixes with symlinked DLL folders

    prefix_paths: list of (label, compatdata_path) tuples
    on_progress:  optional callback(msg: str)
    proton_path:  path to the Proton binary for prefix initialization
    steam_root:   Steam root for STEAM_COMPAT_CLIENT_INSTALL_PATH

    Returns the number of prefixes that have their deps.
    """
    import subprocess
    import time

    prog = on_progress or (lambda *a: None)

    default_pfx = _find_default_pfx(ge_version)
    if not default_pfx:
        prog("⚠ No GE-Proton default_pfx found -- cannot install dependencies")
        return 0

    # --- Step 1: shared DLLs
    if not _ensure_shared_dlls(ge_version, on_progress=on_progress):
        prog("⚠ Shared DLL setup failed -- falling back to full copies")
        # Clones will be full copies instead of symlinks
        shared_available = False
    else:
        shared_available = True

    # --- Step 2: delete SD card prefixes
    prog("  Cleaning up SD card prefixes...")
    _cleanup_sd_card_prefixes(
        [str(a) for a in MANAGED_APPIDS],
        on_progress=on_progress,
    )

    # --- Step 3: drop duplicates and move paths to NVMe
    seen_paths = {}
    unique_paths = []
    for label, compat_path in prefix_paths:
        if not compat_path:
            prog(f"  {label}: no compatdata path -- skipped")
            continue
        # Take the appid from the path and use its NVMe location
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

    # --- Step 4: prepare the donor prefix
    donor_label, donor_path = unique_paths[0]
    donor_pfx_dir = os.path.join(donor_path, "pfx")
    donor_exists = os.path.isdir(os.path.join(donor_pfx_dir, "drive_c"))

    if donor_exists:
        # Donor already on NVMe. Check its DLLs if they are real folders, not symlinks
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
        # Donor needs Proton to initialize it
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

    # --- Step 5: clone the donor to the other prefixes
    for label, compat_path in unique_paths[1:]:
        dest_pfx = os.path.join(compat_path, "pfx")
        dest_exists = os.path.isdir(os.path.join(dest_pfx, "drive_c"))

        if dest_exists:
            # Existing NVMe prefix. Is it already symlinked?
            sys32_dir = os.path.join(dest_pfx, "drive_c", "windows", "system32")
            if os.path.islink(sys32_dir):
                prog(f"  {label}: already symlinked -- skipping")
                success += 1
                continue
            # Real DLL folders: overlay to fill any gaps
            prog(f"  {label}: overlaying from donor...")
            ok = _overlay_prefix(donor_pfx_dir, compat_path, ge_version,
                                 on_progress=on_progress)
        elif shared_available:
            # New prefix: clone with symlinked DLLs (fast)
            prog(f"  {label}: cloning with symlinked DLLs...")
            ok = _clone_with_symlinks(donor_pfx_dir, compat_path, ge_version,
                                      on_progress=on_progress)
        else:
            # No shared DLLs: full clone
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
