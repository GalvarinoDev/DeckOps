"""
finesthour.py: Call of Duty: Finest Hour through Finest Hour Remastered
(github.com/crazyriddler/FinestHourRemastered)

Finest Hour never came out on PC. The port is a static recompilation of the
original Xbox game (PAL release only) and runs under Proton. Games/finesthour holds:

  <disc image>            the user's own PAL Xbox disc (.iso, or a .zip, .7z or .rar with one inside)
  game/                   the port, installed by its own setup (about 10 GB).
                          CODFH.exe, settings in codfh.toml, saves in hdd/.
  game/version.txt        the port's update version, written last by its setup,
                          so it marks a finished install (CODFH.exe alone can be
                          from a stopped one)

The port is downloaded from its v1.0 release, checked against GitHub's sha256
digests, and never mirrored: the repo has no license. Its setup runs headless
with --source and --target. The game checks for updates itself at start and
offers them in its menu, so there is no prelaunch update. "Update Games" in
DeckOps runs the newest updater when update.json lists a newer version.

A disc image found loose in Games/ is moved into this folder first
(detect_games.move_disc_in).
"""

import json
import os
import shutil
import subprocess
import urllib.request

from log import get_logger
from net import download
from steam_common import linux_to_wine_path

_log = get_logger(__name__)

REPO = "crazyriddler/FinestHourRemastered"
EXE = "CODFH.exe"
VERSION = "version.txt"
SETUP = "FinestHourRemasteredSetup.exe"
UPDATER = "FinestHourRemasteredUpdate.exe"


def _assets(tag):
    """{name: (url, digest)} of one release."""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/tags/{tag}",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "DeckOps"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return {a["name"]: (a["browser_download_url"], a.get("digest")) for a in json.load(r)["assets"]}


def _latest_update():
    url, _ = _assets("update")["update.json"]
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "DeckOps"}), timeout=30) as r:
        return json.load(r)


def _installed_version(target):
    try:
        with open(os.path.join(target, VERSION)) as f:
            return f.read().strip() or None
    except OSError:
        return None


def _proton(cmd, cwd, proton_path, compatdata_path, steam_root, log_name):
    env = os.environ.copy()
    env["STEAM_COMPAT_DATA_PATH"] = compatdata_path
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = steam_root or os.path.dirname(os.path.dirname(proton_path))
    os.makedirs(compatdata_path, exist_ok=True)
    try:
        r = subprocess.run([proton_path, "run", *cmd], env=env, cwd=cwd, capture_output=True,
                           text=True, errors="replace", timeout=3600)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{log_name} timed out after 60 minutes")
    for line in (r.stdout + r.stderr).splitlines():
        if line.strip():
            _log.info("%s: %s", log_name, line.rstrip())
    return r.returncode


def _update(target, prog, proton_path, compatdata_path, steam_root):
    try:
        info = _latest_update()
    except Exception as ex:
        prog(100, f"Finest Hour Remastered update check skipped: {ex}")
        return
    saved = _installed_version(target)
    if saved == info["version"]:
        prog(100, f"Finest Hour Remastered is current ({saved})")
        return
    url, dg = _assets("update")[UPDATER]
    exe = os.path.join(os.path.dirname(target), UPDATER)
    download(url, exe, lambda p, m: prog(int(p * 0.8), m), "Finest Hour Remastered update", digest=dg)
    prog(85, "Installing the Finest Hour Remastered update...")
    try:
        code = _proton([exe, "--update", linux_to_wine_path(target)], os.path.dirname(exe),
                       proton_path, compatdata_path, steam_root, "FH update")
    finally:
        os.remove(exe)
    if code != 0:
        raise RuntimeError(f"Finest Hour Remastered update failed (exit {code})")
    # Same format the port writes, so a later check does not rerun the updater
    if _installed_version(target) != info["version"]:
        with open(os.path.join(target, VERSION), "w") as f:
            f.write(info["version"] + "\n")
    prog(100, f"Finest Hour Remastered updated to {info['version']}")


_WRONG_DISC = ("This disc is not the supported release. Finest Hour Remastered needs the "
               "PAL (Europe) Xbox disc, version 3.")


def _check_disc(disc):
    """Same check as the port's setup: the SHA-1 of default.xbe. disc is an image or a folder of its files."""
    from detect_games import FH_XBE_SHA1
    import hashlib
    if os.path.isdir(disc):
        with open(os.path.join(disc, "default.xbe"), "rb") as f:
            sha = hashlib.sha1(f.read()).hexdigest()
    else:
        from xdvdfs import walk
        from bro import _sha1_of
        xbe = {p.lower(): (o, n) for p, o, n in walk(disc, recursive=False)}.get("default.xbe")
        if not xbe:
            raise RuntimeError(f"{os.path.basename(disc)} is not an Xbox disc image")
        with open(disc, "rb") as f:
            sha = _sha1_of(f, *xbe)
    if sha != FH_XBE_SHA1:
        raise RuntimeError(f"{_WRONG_DISC} This one is a different release (default.xbe {sha[:12]}).")


def install_fh(game: dict, steam_root: str, proton_path: str, compatdata_path: str,
               on_progress=None):
    """Download the port and let its setup install it from the user's disc. Raises on failure.
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
    target = os.path.dirname(game["exe_path"])
    if os.path.isfile(game["exe_path"]) and _installed_version(target):
        _update(target, prog, proton_path, compatdata_path, steam_root)
        return

    # The setup also takes the disc's files copied in as they are
    disc = game.get("disc") or (d if os.path.isfile(os.path.join(d, "default.xbe")) else None)
    if not disc or not os.path.exists(disc):
        raise RuntimeError(f"No Call of Duty: Finest Hour disc image (.iso, .zip, .7z or .rar) in {d}")
    from detect_games import DISC_ARCHIVES
    from cod3recomp import _iso_from_archive, _drop_iso
    # The ISO unpacked from an archive is deleted after a finished install or a wrong
    # disc, and kept for a retry after any other failure. The user's own files stay.
    tmp_iso = None
    if disc.lower().endswith(DISC_ARCHIVES):
        tmp_iso = _iso_from_archive(disc, d, lambda p, m: prog(1, m), name="deckops_fh_disc.iso")
    # The disc is checked before the 5 GB download, so a wrong release fails in minutes
    try:
        _check_disc(tmp_iso or disc)
    except RuntimeError:
        _drop_iso(tmp_iso)
        raise
    # Kept on failure so a retry resumes the 5 GB download; deleted after a good install
    setup_dir = os.path.join(d, "deckops_fh_setup")
    os.makedirs(setup_dir, exist_ok=True)
    assets = _assets("v1.0")
    names = [n for n in assets if n == SETUP or n.startswith("FinestHourRemastered.data.")
             or n == "FinestHourRemastered.index"]
    for i, n in enumerate(sorted(names)):
        url, dg = assets[n]
        dest = os.path.join(setup_dir, n)
        # download() renames only after the digest matched, so a file here is complete
        if os.path.isfile(dest):
            continue
        lo, hi = 2 + i * 60 // len(names), 2 + (i + 1) * 60 // len(names)
        download(url, dest, lambda p, m: prog(lo + (hi - lo) * p // 100, m),
                 f"Finest Hour Remastered ({i + 1} of {len(names)})", digest=dg)
    prog(65, "Installing Finest Hour Remastered from your disc (about 10 GB, this takes a while)...")
    code = _proton([os.path.join(setup_dir, SETUP), "--source", linux_to_wine_path(tmp_iso or disc),
                    "--target", linux_to_wine_path(target),
                    "--log", linux_to_wine_path(os.path.join(d, "deckops_fh_install.log"))],
                   setup_dir, proton_path, compatdata_path, steam_root, "FH setup")
    if code == 2:
        _drop_iso(tmp_iso)
        raise RuntimeError(_WRONG_DISC)
    if code != 0 or not os.path.isfile(game["exe_path"]):
        raise RuntimeError(f"Finest Hour Remastered setup failed (exit {code}), see deckops_fh_install.log")
    shutil.rmtree(setup_dir, ignore_errors=True)
    _drop_iso(tmp_iso)
    prog(100, "Call of Duty: Finest Hour installed.")
    return True
