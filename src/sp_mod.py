"""
sp_mod.py: IW-Pad for SP (controller support and aim assist)

Every game uses the same iw-pad.zip. It holds iw-pad.exe (the launcher, it
picks the DLL by the game's bitness), iw-pad.dll (64-bit), iw-pad32.dll
(32-bit) and a menu file each for CoD1 / UO / CoD2 under classic/.

MW2/MW3 Steam (x64): IW-Pad in the game root and a launch option. No AlterWare.

MW2/MW3 own (32-bit): IW-Pad and the AlterWare SP client. The 32-bit Steam
depot SP exes have no per-account CEG and exit silently on the DRM check.
AlterWare's clients run the original game code in their own process:

  MW2: iw4x-sp.exe + data/iw4sp.exe (the only iw4sp.exe build it accepts)
  MW3: iw5-mod.exe + iw5mp_server.exe + raw/scripts/sp/_cp.gsc

CoD1 / UO / CoD2: own copies, and Steam (2620 / 2640 / 2630) with the same launch
option. Steam keeps CoD1 and UO in one folder with one iw-pad.exe. The launcher
starts CoDSP.exe when SteamAppId is 2620, else CoDUOSP.exe.

IW-Pad's launcher prefers iw4x-sp.exe / iw5-mod.exe / CoDUOSP.exe when one is
there and passes -singleplayer itself, so the shortcut only has to swap in
iw-pad.exe.
"""

import os
import zipfile

from log import get_logger
from net import download, github_asset
from alterware import _CDN_BASE, cdn_digests

_log = get_logger(__name__)

_REPO = "GalvarinoDev/IW-Pad"
_LATEST = f"https://github.com/{_REPO}/releases/latest/download/"

_SP_MOD_CONFIG = {
    "iw4sp": {
        "cdn_files": [
            ("iw4/iw4x-sp.exe", "iw4x-sp.exe"),
            ("iw4/data/iw4sp.exe", "data/iw4sp.exe"),
        ],
        "original_exe": "iw4sp.exe",
        "appid": 10180,
    },
    "iw5sp": {
        "cdn_files": [
            ("iw5/iw5-mod.exe", "iw5-mod.exe"),
            ("iw5/iw5mp_server.exe", "iw5mp_server.exe"),
            ("iw5/raw/scripts/sp/_cp.gsc", "raw/scripts/sp/_cp.gsc"),
        ],
        "original_exe": "iw5sp.exe",
        "appid": 42680,
    },
    # CoD1 skips zz_ paks (a game bug), so its menu file is named z_.
    "cod1sp":  {"cdn_files": [], "original_exe": "CoDSP.exe",    "menu": ("classic/z_iwpad.pk3", "main"), "appid": 2620},
    "coduosp": {"cdn_files": [], "original_exe": "CoDUOSP.exe",  "menu": ("classic/zz_iwpad.pk3", "uo"), "appid": 2640},
    "cod2sp":  {"cdn_files": [], "original_exe": "CoD2SP_s.exe", "menu": ("classic/zz_iwpad.iwd", "main"), "appid": 2630},
}

SP_MOD_KEYS = tuple(_SP_MOD_CONFIG)
# Supported only from 0.1.0, so no fallback to the old per-arch zips
ZIP_ONLY_KEYS = ("cod1sp", "coduosp", "cod2sp")


def install_sp_mod(game_key: str, install_dir: str, on_progress=None,
                   source: str = "own", steam_root: str = ""):
    """Install IW-Pad into install_dir, plus AlterWare for own MW2/MW3. Raises on failure."""
    cfg = _SP_MOD_CONFIG[game_key]
    own = source == "own"
    files = cfg["cdn_files"] if own else []
    steps = len(files) + 1

    def prog(pct, msg):
        _log.info(msg)
        if on_progress:
            on_progress(pct, msg)

    digests = cdn_digests() if files else {}
    for i, (cdn_path, local_path) in enumerate(files):
        dst = os.path.join(install_dir, local_path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        name = os.path.basename(local_path)
        download(f"{_CDN_BASE}/{cdn_path}", dst,
                 lambda p, m, i=i: prog(int((i + p / 100) * 100 / steps), m), name,
                 digest=digests.get(cdn_path))
        _log.info("CDN: placed %s", local_path)

    _fetch_iw_pad(game_key, install_dir, own,
                  lambda p, m: prog(int((len(files) + p / 100) * 100 / steps), m))

    if not own:
        from wrapper import set_launch_options, clear_launch_options
        clear_launch_options(steam_root, cfg["appid"])
        set_launch_options(steam_root, cfg["appid"], build_sp_launch_option(game_key))
    prog(100, "IW-Pad installed.")


def _release(game_key, own, timeout=30, unverified=False):
    """(url, digest) of iw-pad.zip. Releases before 0.1.0 only have the per-arch
    zips, so MW2/MW3 fall back to those (0.1.0 still publishes copies for a while)."""
    try:
        return _asset("iw-pad.zip", timeout)
    except Exception:
        if game_key in ZIP_ONLY_KEYS:
            if unverified:
                return _LATEST + "iw-pad.zip", None
            raise
        name = f"iw-pad-{'x86' if own else 'x64'}.zip"
        if unverified:
            return github_asset(_REPO, name, fallback=_LATEST + name, timeout=timeout)
        return github_asset(_REPO, name, timeout=timeout)


def _asset(name, timeout):
    # github_asset matches by suffix. Comparing the full name rejects other assets
    # that end in iw-pad.zip.
    url, dg = github_asset(_REPO, name, timeout=timeout)
    if url.rsplit("/", 1)[-1] != name:
        raise RuntimeError(f"No {name} in the latest {_REPO} release")
    return url, dg


def _subdir(root, name):
    """The subfolder of root that matches name in any case, else root/name."""
    for d in os.listdir(root):
        if d.lower() == name and os.path.isdir(os.path.join(root, d)):
            return os.path.join(root, d)
    return os.path.join(root, name)


def _fetch_iw_pad(game_key, install_dir, own, prog, release=None):
    url, dg = release or _release(game_key, own, unverified=True)
    zip_dest = os.path.join(install_dir, url.rsplit("/", 1)[-1])
    download(url, zip_dest, prog, "IW-Pad", digest=dg)
    # Copy each file to its own place instead of extractall, which would drop all
    # three menu files in a classic/ folder. Only this game's menu file is copied,
    # so the CoD2 .iwd never reaches MW2/MW3. Both DLLs are copied, the unused one
    # never loads.
    with zipfile.ZipFile(zip_dest) as zf:
        names = set(zf.namelist())
        for n in ("iw-pad.exe", "iw-pad.dll", "iw-pad32.dll"):
            if n in names:
                zf.extract(n, install_dir)
        menu = _SP_MOD_CONFIG[game_key].get("menu")
        if menu:
            src, folder = menu
            dst_dir = _subdir(install_dir, folder)
            os.makedirs(dst_dir, exist_ok=True)
            with open(os.path.join(dst_dir, os.path.basename(src)), "wb") as f:
                f.write(zf.read(src))
    os.remove(zip_dest)
    # The tag comes from .../releases/download/<tag>/<asset>. An unverified
    # download saves no version, so the next launch fetches a verified copy.
    from config import set_iw_pad
    set_iw_pad(game_key, {"tag": url.split("/")[-2], "digest": dg} if dg else {})


def update_iw_pad(game_key: str, install_dir: str, log=_log.info):
    """Pre-launch: fetch IW-Pad only when the latest release differs from the saved one."""
    from config import get_iw_pad, get_setup_games
    own = get_setup_games().get(game_key, {}).get("source") == "own"
    # Verified downloads only. If the API fails or the release has no zip, the update is skipped.
    url, dg = _release(game_key, own, timeout=5)
    tag = url.split("/")[-2]
    saved = get_iw_pad(game_key)
    if not dg:
        log(f"IW-Pad {game_key}: {tag} has no digest, update skipped")
        return
    if saved == {"tag": tag, "digest": dg}:
        log(f"IW-Pad {game_key}: {tag} is current")
        return
    log(f"IW-Pad {game_key}: {saved.get('tag', 'unknown')} -> {tag}")
    _fetch_iw_pad(game_key, install_dir, own, lambda p, m: None, release=(url, dg))


def sp_exe(game_key: str) -> str:
    return _SP_MOD_CONFIG[game_key]["original_exe"]


def build_sp_launch_option(game_key: str) -> str:
    """Launch option for the Steam app or own shortcut. It swaps the original SP exe for iw-pad.exe."""
    from steam_common import prelaunch_prefix, GL_FIX, GL_FIX_KEYS
    fix = GL_FIX if game_key in GL_FIX_KEYS else ""
    return f"{fix}{prelaunch_prefix(game_key)}bash -c 'exec \"${{@/{sp_exe(game_key)}/iw-pad.exe}}\"' -- %command%"


if __name__ == "__main__":
    assert build_sp_launch_option("iw4sp").endswith(" iw4sp bash -c 'exec \"${@/iw4sp.exe/iw-pad.exe}\"' -- %command%")
    assert build_sp_launch_option("iw5sp").endswith(" iw5sp bash -c 'exec \"${@/iw5sp.exe/iw-pad.exe}\"' -- %command%")
    o = build_sp_launch_option("cod1sp")
    assert o.startswith("MESA_EXTENSION_MAX_YEAR=2003 bash ") and o.endswith(" cod1sp bash -c 'exec \"${@/CoDSP.exe/iw-pad.exe}\"' -- %command%"), o
    assert build_sp_launch_option("coduosp").startswith("MESA_EXTENSION_MAX_YEAR=2003 ")
    assert "MESA" not in build_sp_launch_option("cod2sp")
    assert "${@/CoD2SP_s.exe/iw-pad.exe}" in build_sp_launch_option("cod2sp")
    print("ok")
