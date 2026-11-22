"""
bro.py: Call of Duty 2: Big Red One through the BRO Custom Engine
(github.com/SmokeDoggy044/CoD2-BRO-Native-Loader, GPL-2.0-or-later)

Big Red One never came out on PC. The engine is a native 32-bit Linux rewrite
that reads the game's files from the user's own Xbox disc. Games/bro holds:

  cod_bro, lib/, ...  the newest Linux release, checked against GitHub's sha256
  assets/             the disc's files. DeckOps copies them out of the image and
                      checks each one against the release's game_files.txt.
  deckops_bro.json    tag + digest of the installed release
  An install counts as finished when every file game_files.txt lists is in
  assets/ at its size. assets/ alone can be half copied when an install stops.

cod_bro finds assets/ next to itself (paths.cpp default_asset_dir). Settings
and saves live in ~/.local/share/cod_bro/. No Proton: the shortcut runs
cod_bro directly.

A disc image found loose in Games/ is moved into this folder first
(detect_games.move_disc_in).
"""

import hashlib
import json
import os
import tarfile

from log import get_logger
from net import download, github_asset

_log = get_logger(__name__)

REPO = "SmokeDoggy044/CoD2-BRO-Native-Loader"
ASSET = "-linux.tar.gz"
EXE = "cod_bro"
META = "deckops_bro.json"
CHUNK = 8 << 20


def is_installed(install_dir: str) -> bool:
    """Same check the engine uses (paths.cpp has_game_files): default.xbe and media/ in assets/."""
    a = os.path.join(install_dir, "assets")
    return os.path.isfile(os.path.join(a, "default.xbe")) and os.path.isdir(os.path.join(a, "media"))


def _fetch_release(install_dir, prog, release=None):
    url, dg = release or github_asset(REPO, ASSET)
    from cod3recomp import _saved
    if dg and os.path.isfile(os.path.join(install_dir, EXE)) and _saved(install_dir, META) == {"tag": url.split("/")[-2], "digest": dg}:
        return
    tgz = os.path.join(install_dir, "deckops_bro.tar.gz")
    download(url, tgz, prog, "Big Red One engine", digest=dg)
    try:
        with tarfile.open(tgz) as tf:
            # Drop the top folder (cod_bro-<ver>-linux/) so the files land next to assets/
            members = []
            for m in tf.getmembers():
                rest = m.name.split("/", 1)[1] if "/" in m.name else ""
                if rest:
                    members.append(m.replace(name=rest, deep=False))
            tf.extractall(install_dir, members=members, filter="data")
    finally:
        os.remove(tgz)
    with open(os.path.join(install_dir, META), "w") as f:
        json.dump({"tag": url.split("/")[-2], "digest": dg}, f)


def _editions(install_dir):
    """{default.xbe sha1: (label, [(sha1, size, path)])} from the release's game_files.txt."""
    out, cur = {}, None
    with open(os.path.join(install_dir, "game_files.txt")) as f:
        for line in f:
            p = line.split(None, 3)
            if not p or line.startswith("#"):
                continue
            if p[0] == "edition":
                cur = out.setdefault(p[2], (p[3].strip() if len(p) > 3 else p[1], []))[1]
            elif cur is not None and len(p) == 3:
                cur.append((p[0], int(p[1]), p[2].strip()))
    return out


def _complete(install_dir):
    """Every file of one edition in assets/ at its listed size (the same test extract_disc skips by)."""
    a = os.path.join(install_dir, "assets")
    try:
        eds = _editions(install_dir).values()
    except OSError:
        return False
    return any(files and all(os.path.isfile(p := os.path.join(a, rel)) and os.path.getsize(p) == size
                             for _, size, rel in files) for _, files in eds)


def _sha1_of(f, off, size):
    h = hashlib.sha1(); f.seek(off); left = size
    while left:
        b = f.read(min(CHUNK, left))
        if not b:
            break
        h.update(b); left -= len(b)
    return h.hexdigest()


def extract_disc(iso: str, install_dir: str, prog):
    """Copy the listed game files out of the disc image into assets/.
    Each file goes to <name>.part first and is renamed only when its SHA-1
    matches. Files already in place with the right size are kept, so a
    stopped install picks up where it left off."""
    from xdvdfs import walk
    on_disc = {p.lower(): (o, s) for p, o, s in walk(iso)}
    if "default.xbe" not in on_disc:
        raise RuntimeError(f"{os.path.basename(iso)} is not an Xbox disc image")
    editions = _editions(install_dir)
    with open(iso, "rb") as f:
        xbe = _sha1_of(f, *on_disc["default.xbe"])
        if xbe not in editions:
            raise RuntimeError(f"{os.path.basename(iso)} is not a known Big Red One disc "
                               f"(default.xbe {xbe}). Only the Xbox game works.")
        label, files = editions[xbe]
        total = sum(s for _, s, _ in files) or 1
        prog(0, f"Disc: {label}, {len(files)} files, {total / (1 << 30):.2f} GB")
        done = 0
        assets = os.path.join(install_dir, "assets")
        for i, (sha, size, rel) in enumerate(files):
            src = on_disc.get(rel.lower())
            if not src or src[1] != size:
                raise RuntimeError(f"{rel} is missing or the wrong size on the disc image")
            dest = os.path.join(assets, rel)
            if not (os.path.isfile(dest) and os.path.getsize(dest) == size):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                h = hashlib.sha1(); f.seek(src[0]); left = size
                with open(dest + ".part", "wb") as out:
                    while left:
                        b = f.read(min(CHUNK, left))
                        if not b:
                            raise RuntimeError(f"The disc image ends inside {rel}")
                        h.update(b); out.write(b); left -= len(b)
                if h.hexdigest() != sha:
                    os.remove(dest + ".part")
                    raise RuntimeError(f"{rel} does not match its checksum. The disc dump may be damaged.")
                os.replace(dest + ".part", dest)
            done += size
            prog(int(done * 100 / total), f"Extracting game files: {i + 1} of {len(files)}")


def install_bro(game: dict, steam_root: str = None, proton_path: str = None,
                compatdata_path: str = None, on_progress=None):
    """Download the engine and copy the user's disc into assets/. Raises on failure.
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
    os.makedirs(d, exist_ok=True)
    _fetch_release(d, lambda p, m: prog(int(p * 0.05), m))
    if is_installed(d) and _complete(d):
        prog(100, "Big Red One already installed, engine updated.")
        return

    disc = game.get("disc")
    if not disc or not os.path.isfile(disc):
        raise RuntimeError(f"No Big Red One disc image (.iso, .zip, .7z or .rar) in {d}")
    from detect_games import DISC_ARCHIVES
    # The ISO unpacked from an archive is deleted afterwards. It stays only when the
    # install is stopped, for the retry. The user's own files stay.
    from cod3recomp import _iso_from_archive, _drop_iso
    tmp_iso = None
    if disc.lower().endswith(DISC_ARCHIVES):
        tmp_iso = _iso_from_archive(disc, d, lambda p, m: prog(5, m), name="deckops_bro_disc.iso")
    try:
        extract_disc(tmp_iso or disc, d, lambda p, m: prog(5 + int(p * 0.95), m))
    finally:
        _drop_iso(tmp_iso)
    if not is_installed(d):
        raise RuntimeError("Big Red One files are incomplete after extraction")
    prog(100, "Call of Duty 2: Big Red One installed.")
    return True


def update_bro(install_dir: str, log=_log.info):
    """Pre-launch: download the engine again only when the newest release differs from the saved one."""
    url, dg = github_asset(REPO, ASSET, timeout=5)
    tag = url.split("/")[-2]
    from cod3recomp import _saved
    saved = _saved(install_dir, META)
    if not dg:
        log(f"Big Red One engine: {tag} has no digest, update skipped")
        return
    if saved == {"tag": tag, "digest": dg}:
        log(f"Big Red One engine: {tag} is current")
        return
    log(f"Big Red One engine: {saved.get('tag', 'unknown')} -> {tag}")
    _fetch_release(install_dir, lambda p, m: None, release=(url, dg))


# --- Profile
# BRO keeps its profiles in <data>/E/UDATA/41560051/1A0557BD26C8 (the folder
# name is the Xbox hash of the save name "Profiles", the same for everyone).
# Each Profiles* file is 16 KB: the name at 0x1C (16 bytes, latin-1) and an
# HMAC-SHA1 over everything before 0x3FE0, keyed with 16 zero bytes in the
# native loader (layout from its tools/profile_edit.py). DeckOps ships an empty
# profile named "Player" so the game starts without the create-profile screen.

_NAME, _SIGNED = 0x1C, 0x3FE0


def _save_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "cod_bro", "E", "UDATA", "41560051", "1A0557BD26C8")


def _set_name(path, name):
    import hmac
    d = bytearray(open(path, "rb").read())
    n = (name or "Player").encode("latin-1", "replace")[:15] or b"Player"
    d[_NAME:_NAME + 16] = n.ljust(16, b"\0")
    d[_SIGNED:_SIGNED + 20] = hmac.new(bytes(16), bytes(d[:_SIGNED]), hashlib.sha1).digest()
    with open(path, "wb") as f:
        f.write(d)


def seed_profile(player_name):
    """Copy the empty profile in when BRO has none yet, named after the player.
    An existing profile (and its progress) is never touched. Returns True when copied."""
    import shutil
    from steam_common import PROJECT_ROOT
    dest = _save_dir()
    # The engine starts in a 2x window without a settings file
    ini = os.path.normpath(os.path.join(dest, "..", "..", "..", "..", "settings.ini"))
    if not os.path.isfile(ini):
        os.makedirs(os.path.dirname(ini), exist_ok=True)
        with open(ini, "w") as f:
            f.write("fullscreen = true\n")
    if os.path.isfile(os.path.join(dest, "Profiles")):
        return False
    os.makedirs(dest, exist_ok=True)
    src = os.path.join(PROJECT_ROOT, "assets", "bro_profile")
    for f in os.listdir(src):
        shutil.copy2(os.path.join(src, f), os.path.join(dest, f))
    _set_name(os.path.join(dest, "Profiles"), player_name)
    return True


def rename_profile(player_name):
    """New player name into the first profile, progress kept. Returns True when renamed."""
    p = os.path.join(_save_dir(), "Profiles")
    if not (player_name and os.path.isfile(p) and os.path.getsize(p) == 0x4000):
        return False
    _set_name(p, player_name)
    return True
