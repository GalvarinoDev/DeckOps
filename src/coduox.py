"""
coduox.py: United Offensive multiplayer through CoDUOx (CoDExtended UO client, 1.51x)

Upstream (github.com/xtnded/codextended-client-uo, GPL-3.0) publishes source
only, so the built CoDUOMP.exe + cod1x.dll come from CBServers' updater repo on
GitHub at a fixed commit, each checked against its sha1. Needs UO 1.51. Disc
copies and Steam UO both are (Steam's data matches the disc, only its exe is
the Steam DRM build, which CoDUOx replaces).

Disc copy: in place, like CoD1x on a 1.1 disc copy, the stock exe kept as
CoDUOMP_old.exe. Without a key, CB launcher's placeholder goes into the
registry before launch (cod2x.cb_placeholder), never over a real key.

Steam: a copy beside the game, so the Steam folder is never changed:

  <UO>/deckops_coduox/
    CoDUOMP.exe, cod1x.dll   CoDUOx
    root DLLs, miles/,       hard links to the game's files
    Main/*.pk3, uo/*.pk3,
    uo/*.dll
    pb/                      a real copy, PunkBuster writes into it

IW-Pad's menu paks stay out. The owner's Steam key goes into the prefix
before launch (cod2x.steam_codkey).
"""

import os
import shutil

from log import get_logger
from net import download
from steam_common import sha1_file

_log = get_logger(__name__)

_BASE = ("https://raw.githubusercontent.com/CBServers/updater/"
         "650f246fc51ea6c15a30242ea3f3448d4d1a664f/updater/coduox/")
FILES = {"cod1x.dll":   "1eda93961891ed8aa8cc6f7486ec50666759001f",
         "CoDUOMP.exe": "3c2cc379aefd68b7eec0cfb1c3b0fa8ae397a5f2"}
OLD = "CoDUOMP_old.exe"
COPY = "deckops_coduox"
_REG_KEY = r"[Software\\Wow6432Node\\Activision\\Call of Duty United Offensive]"


def is_151(game_dir):
    """uo/version.inf says ExtVersion=1.51."""
    from cod1x import _child
    try:
        with open(_child(_child(game_dir, "uo"), "version.inf"), errors="replace") as f:
            return "ExtVersion=1.51" in f.read()
    except OSError:
        return False


def _current(game_dir):
    return all(os.path.isfile(os.path.join(game_dir, n)) and sha1_file(os.path.join(game_dir, n)).lower() == h
               for n, h in FILES.items())


def is_steam(game_dir):
    return "/steamapps/common/" in game_dir.replace("\\", "/")


def client_dir(game_dir):
    """Folder CoDUOx runs from: the copy (Steam) or the game folder (disc)."""
    return os.path.join(game_dir, COPY) if is_steam(game_dir) else game_dir


def _link(src, dst):
    if not os.path.exists(dst):
        os.link(src, dst)


def build_copy(game_dir):
    """Build or refresh <game_dir>/deckops_coduox from the game's own files. Returns its path."""
    from cod1x import _child
    c = os.path.join(game_dir, COPY)
    os.makedirs(c, exist_ok=True)
    for e in os.listdir(game_dir):
        p, low = os.path.join(game_dir, e), e.lower()
        if os.path.isfile(p) and (low == "localization.txt" or
                                  low.endswith(".dll") and not low.startswith("iw-pad")):
            _link(p, os.path.join(c, e))
    miles = _child(game_dir, "miles")
    if os.path.isdir(miles):
        os.makedirs(os.path.join(c, "miles"), exist_ok=True)
        for f in os.listdir(miles):
            _link(os.path.join(miles, f), os.path.join(c, "miles", f))
    pb = _child(game_dir, "pb")
    if os.path.isdir(pb) and not os.path.exists(os.path.join(c, "pb")):
        shutil.copytree(pb, os.path.join(c, "pb"))
    # Paks and the MP DLLs only. Configs and caches the game writes stay real files
    for sub, keep in (("main", (".pk3",)), ("uo", (".pk3", ".dll", ".inf"))):
        src = _child(game_dir, sub)
        dst = os.path.join(c, os.path.basename(src))
        os.makedirs(dst, exist_ok=True)
        for f in os.listdir(src):
            if f.lower().endswith(keep) and "iwpad" not in f.lower():
                _link(os.path.join(src, f), os.path.join(dst, f))
    return c


def install_coduox(game: dict, on_progress=None, source="own"):
    """CoDUOx into a 1.51 disc copy's folder, or into the copy beside Steam UO. Raises on failure."""
    def prog(pct, msg):
        _log.info(msg)
        if on_progress:
            on_progress(pct, msg)

    d = game["install_dir"]
    if not is_151(d):
        raise RuntimeError("CoDUOx needs United Offensive 1.51. Patch the game, then run Update.")
    if source == "steam":
        prog(0, "Building the CoDUOx copy...")
        d = build_copy(d)
    else:
        old = os.path.join(d, OLD)
        if not os.path.isfile(old):
            os.replace(os.path.join(d, "CoDUOMP.exe"), old)
    if _current(d):
        prog(100, "CoDUOx already installed.")
        return
    for i, (n, h) in enumerate(FILES.items()):
        part = os.path.join(d, n + ".deckops_part")
        download(_BASE + n, part, lambda p, m: prog(i * 50 + p // 2, m), "CoDUOx")
        if sha1_file(part).lower() != h:
            os.remove(part)
            raise RuntimeError(f"CoDUOx {n}: checksum mismatch")
        os.replace(part, os.path.join(d, n))
    prog(100, "CoDUOx installed.")


def set_key(pfx, game_dir, steam_root=None):
    """Pre-launch: the UO key as "key" and "codkey" when the prefix has none yet
    (Wine is not running). Steam: the owner's key. Disc: CB's placeholder.
    Returns True when a key is there."""
    from cod2x import _write_codkey, cb_placeholder, steam_codkey
    if is_steam(game_dir):
        sr = steam_root or os.path.expanduser("~/.local/share/Steam")
        return steam_codkey(pfx, sr, appid="2640", section=_REG_KEY, names=("key", "codkey"))
    return _write_codkey(pfx, lambda: cb_placeholder("Call of Duty United Offensive"),
                         "disc copy", section=_REG_KEY, names=("key", "codkey"))
