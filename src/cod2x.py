"""
cod2x.py: Call of Duty 2 multiplayer through CoD2x (github.com/callofduty2x/CoD2x)

CoD2x is a proxy mss32.dll beside the stock one (mss32_original.dll, both from
the release zip). It does nothing in CoD2SP_s.exe, so it sits in the game
folder. Its own updater is replaced by the pre-launch check (update_cod2x).

Steam CoD2MP_s.exe is wrapped in Steam DRM, which shows "problem starting up
Steam" unless it runs as app 2630. SteamAppId=2630 in the launch option fixes
that, but Proton then tags the window as app 2630 and Game Mode keeps focus on
the empty shortcut. steam_appid.txt next to the exe gives the DRM its appid
and leaves the window on the shortcut (Deck, 2026-11-21).
"""

import json
import os
import re
import zipfile

from log import get_logger
from net import download, github_asset

_log = get_logger(__name__)

REPO = "callofduty2x/CoD2x"
SUFFIX = "_windows.zip"
META = "deckops_cod2x.json"
_DLLS = ("mss32.dll", "mss32_original.dll")

# The 32-bit game reads HKLM\SOFTWARE\Activision\Call of Duty 2\codkey
_REG_KEY = r"[Software\\Wow6432Node\\Activision\\Call of Duty 2]"

# Disc copies without a key get the placeholder CBServers' cb-launcher writes
# (GPL-3.0). It only gets past the game's start check and does not authorize
# on servers that check keys. Read from their source at a fixed commit, so no
# key is kept in DeckOps.
CB_KEYS = ("https://raw.githubusercontent.com/CBServers/cb-launcher/"
           "2d9a5b8839b5619962eacbd1209dac6fd39b75ec/src/launcher/commands/game_commands.cpp")


def cb_placeholder(game, timeout=5):
    """CB launcher's placeholder key for game ("Call of Duty 2" or
    "Call of Duty United Offensive"), or None when it can't be read."""
    import urllib.request
    try:
        req = urllib.request.Request(CB_KEYS, headers={"User-Agent": "DeckOps"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            src = r.read().decode(errors="replace")
    except Exception as ex:
        _log.warning("CoD2x: no CD key set for the disc copy (%s), the game asks for it", type(ex).__name__)
        return None
    m = re.search(r'Activision\\\\' + re.escape(game) + r'".*?L"([A-Z0-9]{20})"', src, re.S)
    return m.group(1) if m else None


def _has_codkey(s, section=_REG_KEY, names=("codkey",)):
    """(index, end) of section in system.reg text and whether it has any of names."""
    i = s.find("\n" + section + " ")
    if i < 0:
        return i, len(s), False
    end = s.find("\n\n", i + 1)
    end = len(s) if end < 0 else end
    return i, end, any(f'\n"{n}"=' in s[i:end] for n in names)


def _write_codkey(pfx, get_key, what, section=_REG_KEY, names=("codkey",)):
    """The key into the prefix registry (each of names under section) unless one
    is there (a real key is never overridden). get_key is only called when
    needed. Wine must not be running (it rewrites system.reg on exit). The key
    is never logged. Returns True when a key is there afterwards."""
    reg = os.path.join(pfx, "system.reg")
    if not os.path.isfile(reg):
        return False
    with open(reg, errors="surrogateescape") as f:
        s = f.read()
    i, end, has = _has_codkey(s, section, names)
    if has:
        return True
    key = get_key()
    if not key:
        return False
    line = "\n".join(f'"{n}"="{key}"' for n in names)
    if i >= 0:
        s = s[:end] + "\n" + line + s[end:]
    else:
        s = s.rstrip("\n") + f"\n\n{section} 0\n{line}\n"
    with open(reg, "w", errors="surrogateescape") as f:
        f.write(s)
    _log.info(f"CD key written ({what})")
    return True


def steam_codkey(pfx, steam_root, appid="2630", section=_REG_KEY, names=("codkey",)):
    """Steam copy: the owner's key from legacycompat/evaluatorscript_<appid>.vdf.
    Steam writes it only when the game runs as a Steam app."""
    def key():
        try:
            with open(os.path.join(steam_root, "legacycompat", f"evaluatorscript_{appid}.vdf"),
                      errors="replace") as f:
                m = re.search(r'"legacycdkey"\s+"([A-Z0-9]{20})"', f.read())
        except OSError:
            m = None
        if not m:
            _log.info("No Steam CD key yet (game not started from Steam), the game asks for it")
        return m.group(1) if m else None
    return _write_codkey(pfx, key, "from Steam", section, names)


def own_codkey(pfx):
    """Disc copy: CB launcher's placeholder, only when no key is there yet.
    A key typed in game replaces it."""
    return _write_codkey(pfx, lambda: cb_placeholder("Call of Duty 2"), "disc copy")


def _fetch(game_dir, prog, release=None):
    """Both DLLs from the release, skipped when tag and digest match the saved ones."""
    url, dg = release or github_asset(REPO, SUFFIX)
    tag = url.split("/")[-2]
    from cod3recomp import _saved
    have = all(os.path.isfile(os.path.join(game_dir, n)) for n in _DLLS)
    if dg and have and _saved(game_dir, META) == {"tag": tag, "digest": dg}:
        return
    z = os.path.join(game_dir, "deckops_cod2x.zip")
    download(url, z, prog, "CoD2x", digest=dg)
    with zipfile.ZipFile(z) as zf:
        for n in _DLLS:
            with open(os.path.join(game_dir, n), "wb") as out:
                out.write(zf.read(n))
    os.remove(z)
    # An unverified download saves no version, so the next launch fetches a verified copy
    with open(os.path.join(game_dir, META), "w") as f:
        json.dump({"tag": tag, "digest": dg} if dg else {}, f)


def _is_13(exe):
    """A disc CoD2MP_s.exe carries its version string. CoD2x needs 1.3."""
    try:
        with open(exe, "rb") as f:
            return b"pc_1.3_1_1" in f.read()
    except OSError:
        return False


def install_cod2x(game: dict, steam_root: str, on_progress=None, source="steam"):
    """CoD2x DLLs into the game folder. Raises on failure.

    Steam (1.3, DRM-wrapped exe): also steam_appid.txt, the Steam key goes into
    the prefix before each launch (update_cod2x). Own (disc): must be patched
    to 1.3, gets CB's placeholder key before launch when it has none."""
    def prog(pct, msg):
        _log.info(msg)
        if on_progress:
            on_progress(pct, msg)

    d = game["install_dir"]
    if source == "own" and not _is_13(os.path.join(d, "CoD2MP_s.exe")):
        raise RuntimeError("CoD2x needs Call of Duty 2 patch 1.3. Patch the game, then run Update.")
    prog(0, "Downloading CoD2x...")
    _fetch(d, lambda p, m: prog(int(p * 0.95), m))
    if source == "steam":
        with open(os.path.join(d, "steam_appid.txt"), "w") as f:
            f.write("2630")
    prog(100, "CoD2x installed.")


def update_cod2x(game_dir: str, log=_log.info):
    """Pre-launch: CD key into the prefix (Wine is not running yet), then a newer CoD2x if there is one."""
    pfx = os.environ.get("STEAM_COMPAT_DATA_PATH")
    sr = os.environ.get("STEAM_COMPAT_CLIENT_INSTALL_PATH") or os.path.expanduser("~/.local/share/Steam")
    # Steam copy: the owner's Steam key. Disc copy: CB's placeholder if no key yet.
    if pfx:
        if "/steamapps/common/" in game_dir.replace("\\", "/"):
            steam_codkey(os.path.join(pfx, "pfx"), sr)
        else:
            own_codkey(os.path.join(pfx, "pfx"))
    url, dg = github_asset(REPO, SUFFIX, timeout=5)
    tag = url.split("/")[-2]
    if not dg:
        log(f"CoD2x: {tag} has no digest, update skipped")
        return
    from cod3recomp import _saved
    saved = _saved(game_dir, META)
    if saved == {"tag": tag, "digest": dg}:
        log(f"CoD2x: {tag} is current")
        return
    log(f"CoD2x: {saved.get('tag', 'unknown')} -> {tag}")
    _fetch(game_dir, lambda p, m: None, release=(url, dg))
