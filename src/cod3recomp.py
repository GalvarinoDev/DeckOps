"""
cod3recomp.py: Call of Duty 3 through CoD3Recomp (github.com/FrankHUN88453/CoD3Recomp)

CoD3 never came out on PC. CoD3Recomp is a static recompilation of the Xbox 360
game and needs the user's own disc image. The Games/cod3 folder holds:

  CoD3SP_s.exe        from the newest GitHub release, checked against its
                      sha256 digest. Never mirrored: the repo has no license.
  game/               the disc's files, written by the exe's own setup
  deckops_cod3.json   tag + digest of the installed exe
  d3dcompiler_47.dll  Microsoft's redistributable, from the Windows SDK NuGet
                      package. Wine's own lacks SV_DepthLessEqual, so the game
                      showed a black screen.
  avcodec-62.dll, avutil-60.dll, swresample-6.dll, ffmpeg-LICENSE.txt
                      FFmpeg from CoD3Recomp's v0.4.0 zip (later releases ship
                      only the exe). It decodes the XMA audio. Without it: no sound.
  Only these files are fetched out of the two archives (net.zip_member).
  game/.cod3install   written last by the exe's own setup, so it marks a
                      finished install. game/ alone can be half written when
                      an install stops.

The exe looks for game/ next to itself (installer.cpp Locate), so DeckOps
writes no game.path. Its setup runs headless when --iso and --main are given.
--install-only makes it exit after setup without booting the game.

A disc image found loose in Games/ is moved into this folder first
(detect_games.move_disc_in).
"""

import hashlib
import json
import os
import subprocess

from log import get_logger
from net import download, github_asset
from steam_common import linux_to_wine_path

_log = get_logger(__name__)

REPO = "FrankHUN88453/CoD3Recomp"
EXE = "CoD3SP_s.exe"
META = "deckops_cod3.json"

# (archive url, member, sha256). Each member lands next to the exe under its base name.
_SDK = ("https://api.nuget.org/v3-flatcontainer/microsoft.windows.sdk.cpp/10.0.28000.2957/"
        "microsoft.windows.sdk.cpp.10.0.28000.2957.nupkg")
_PORT = "https://github.com/FrankHUN88453/CoD3Recomp/releases/download/v0.4.0/CoD3-PC-Port-0.4.0.zip"
_DEPS = [
    (_SDK, "c/Redist/D3D/x64/d3dcompiler_47.dll", "d28d341306db9067c779d2cfe5865c3840e3a863efa47a2e0b0d4a1b906f6158"),
    (_PORT, "avcodec-62.dll", "a263d00af13f55ab8ef960fa5475e392386f0c7749abab74695fdf9640c216b2"),
    (_PORT, "avutil-60.dll", "e48fe6b08dd074ceb20b90e3b42829eb73779454706362c774c366ec7af7d874"),
    (_PORT, "swresample-6.dll", "0cd2cb4695111a92395637726a459606065a38db5724409a0b2bf68c86509144"),
    (_PORT, "ffmpeg-LICENSE.txt", "8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903"),
]


def is_installed(install_dir: str) -> bool:
    """Same check the exe uses: default.xex and an sp folder, in game/ or in the folder itself."""
    return any(os.path.isfile(os.path.join(install_dir, sub, "default.xex"))
               and os.path.isdir(os.path.join(install_dir, sub, "sp")) for sub in ("game", ""))


def _setup_done(install_dir):
    return any(os.path.isfile(os.path.join(install_dir, sub, ".cod3install")) for sub in ("game", ""))


def _saved(install_dir, meta=META):
    try:
        with open(os.path.join(install_dir, meta)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _fetch_exe(install_dir, prog, release=None):
    # Every CoD3Recomp release so far is a pre-release, and releases/latest skips those.
    url, dg = release or github_asset(REPO, EXE, prerelease=True)
    exe = os.path.join(install_dir, EXE)
    if dg and os.path.isfile(exe) and _saved(install_dir) == {"tag": url.split("/")[-2], "digest": dg}:
        return
    download(url, exe + ".part", prog, "CoD3Recomp", digest=dg)
    os.replace(exe + ".part", exe)
    with open(os.path.join(install_dir, META), "w") as f:
        json.dump({"tag": url.split("/")[-2], "digest": dg}, f)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _fetch_deps(install_dir, prog):
    """Put the DLLs CoD3Recomp needs under Proton next to the exe. Files already
    there with the right checksum are kept, so only a missing one is fetched."""
    from net import zip_member
    todo = [x for x in _DEPS
            if not (os.path.isfile(p := os.path.join(install_dir, os.path.basename(x[1]))) and _sha256(p) == x[2])]
    for i, (url, member, sha) in enumerate(todo):
        data = zip_member(url, member, sha, lambda p, m: prog((i * 100 + p) // len(todo), m))
        dest = os.path.join(install_dir, os.path.basename(member))
        with open(dest + ".part", "wb") as f:
            f.write(data)
        os.replace(dest + ".part", dest)


def _iso_from_archive(archive, install_dir, prog, name="deckops_cod3_disc.iso"):
    """Unpack the disc image from its archive, or reuse the one a stopped install left.
    It is unpacked as .part and renamed when complete. The .src note names the archive,
    so a different archive is unpacked fresh."""
    from detect_games import unpack_iso
    dest = os.path.join(install_dir, name)
    src = f"{os.path.basename(archive)} {os.path.getsize(archive)}"
    try:
        with open(dest + ".src") as f:
            if os.path.isfile(dest) and f.read() == src:
                prog(10, "Using the disc image unpacked by the last install")
                return dest
    except OSError:
        pass
    unpack_iso(archive, dest + ".part", lambda m: prog(10, m))
    os.replace(dest + ".part", dest)
    with open(dest + ".src", "w") as f:
        f.write(src)
    return dest


def _drop_iso(iso):
    for p in (iso, iso and iso + ".src"):
        if p and os.path.exists(p):
            os.remove(p)


def install_cod3(game: dict, steam_root: str, proton_path: str, compatdata_path: str,
                 on_progress=None):
    """Download CoD3Recomp and let it extract the user's disc into game/. Raises on failure.
    True when the disc was installed now, None when it was already installed."""
    def prog(pct, msg):
        _log.info(msg)
        if on_progress:
            on_progress(pct, msg)

    d = game["install_dir"]
    if game.get("loose") and game.get("disc") and os.path.isfile(game["disc"]):
        from detect_games import move_disc_in
        game["disc"] = move_disc_in(game["disc"], d, lambda m: prog(0, m))
        game["loose"] = False
    _fetch_exe(d, lambda p, m: prog(int(p * 0.05), m))
    _fetch_deps(d, lambda p, m: prog(5 + int(p * 0.05), m))
    if is_installed(d) and _setup_done(d):
        prog(100, "Call of Duty 3 already installed, CoD3Recomp updated.")
        return

    disc = game.get("disc")
    if not disc or not os.path.isfile(disc):
        raise RuntimeError(f"No Call of Duty 3 disc image (.iso, .zip, .7z or .rar) in {d}")
    from detect_games import DISC_ARCHIVES
    # The ISO unpacked from an archive is deleted after a finished install and kept for a
    # retry after a failed one. The user's own files stay.
    tmp_iso = _iso_from_archive(disc, d, prog) if disc.lower().endswith(DISC_ARCHIVES) else None

    env = os.environ.copy()
    env["STEAM_COMPAT_DATA_PATH"] = compatdata_path
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = steam_root or os.path.dirname(os.path.dirname(proton_path))
    # Through cmd /c: the exe waits for Enter at exit when it is the only process on its
    # console (Kernel::Exit), and Proton gives it a console of its own. cmd shares it.
    # EXE is relative (cwd is d) because cmd /c strips the quotes off a quoted first word.
    cmd = [proton_path, "run", "cmd", "/c", EXE, "--no-update", "--install-only",
           "--iso", linux_to_wine_path(tmp_iso or disc),
           "--main", linux_to_wine_path(os.path.join(d, "game"))]
    prog(20, "Extracting the disc with CoD3Recomp (several GB, this takes a few minutes)...")
    try:
        r = subprocess.run(cmd, env=env, cwd=d, capture_output=True, text=True,
                           errors="replace", timeout=3600)
        for line in (r.stdout + r.stderr).splitlines():
            if line.strip():
                _log.info("CoD3Recomp: %s", line.rstrip())
    except subprocess.TimeoutExpired:
        raise RuntimeError("CoD3Recomp setup timed out after 60 minutes")

    # The exe also exits 0 when setup is cancelled, so check the files instead.
    if not is_installed(d):
        tail = " | ".join(l for l in (r.stdout + r.stderr).splitlines()[-3:] if l.strip())
        raise RuntimeError(f"CoD3Recomp setup did not finish (exit {r.returncode}): {tail}")
    _drop_iso(tmp_iso)
    prog(100, "Call of Duty 3 installed.")
    return True


def update_cod3(install_dir: str, log=_log.info):
    """Pre-launch: download the exe again only when the newest release differs from the saved one."""
    url, dg = github_asset(REPO, EXE, timeout=5, prerelease=True)
    tag = url.split("/")[-2]
    saved = _saved(install_dir)
    if not dg:
        log(f"CoD3Recomp: {tag} has no digest, update skipped")
        return
    if saved == {"tag": tag, "digest": dg}:
        log(f"CoD3Recomp: {tag} is current")
        return
    log(f"CoD3Recomp: {saved.get('tag', 'unknown')} -> {tag}")
    _fetch_exe(install_dir, lambda p, m: None, release=(url, dg))
