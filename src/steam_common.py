"""
steam_common.py: shared Steam helpers for DeckOps

These helpers used to be copy-pasted across shortcut.py,
controller_profiles.py, plutonium_lcd.py, and cache_cleanup.py, and the
copies had drifted (int vs str return types, different file-creation
endings). Keeping one copy here stops that.

This is a leaf module. It imports only the standard library and log,
plus a lazy wrapper import inside record_configset_edit, so any DeckOps
module can import it without a cycle. That includes cache_cleanup.py,
which runs as a standalone script.

Consumers import with underscore aliases to keep their existing call
sites unchanged, e.g.:

    from steam_common import (
        calc_shortcut_appid as _calc_shortcut_appid,
        find_all_steam_uids as _find_all_steam_uids,
    )
"""

import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import tempfile

from log import get_logger

_log = get_logger(__name__)


# --- Paths and constants

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEAM_ROOT   = os.path.expanduser("~/.local/share/Steam")
USERDATA_DIR = os.path.join(STEAM_ROOT, "userdata")
STEAM_CONFIG = os.path.join(STEAM_ROOT, "config", "config.vdf")

# Steam user IDs below this are system/placeholder folders, not accounts.
MIN_UID = 10000


# --- Shortcut appid

def calc_shortcut_appid(exe_path: str, name: str) -> int:
    """
    Calculate the Steam shortcut appid from exe path and name.

    This must match Steam's internal algorithm exactly. If the CRC or
    bitmask changes, shortcuts will not resolve and artwork/controller
    configs will point to the wrong appid. Do not modify.

    Callers that need the appid as a string (configset keys, path
    segments) must wrap the result in str() themselves.
    """
    key = (exe_path + name).encode("utf-8")
    crc = binascii.crc32(key) & 0xFFFFFFFF
    return (crc | 0x80000000) & 0xFFFFFFFF


# --- Steam account discovery

def backup_file(path: str):
    """Write a .bak copy before modifying a Steam config file."""
    if os.path.exists(path):
        try:
            shutil.copy2(path, path + ".bak")
        except OSError:
            _log.debug("backup failed for %s", path, exc_info=True)


def write_json(path: str, data, indent: int = 2):
    # tmp + rename so a crash or sleep mid-write can't leave a half-written file
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=indent)
        os.replace(tmp, path)
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise


def sha1_file(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha(path: str) -> str:
    """The file's git object id, as GitHub's contents API reports it."""
    h = hashlib.sha1(b"blob %d\0" % os.path.getsize(path))
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def heroic_app_name(game_key: str) -> str:
    # Deterministic so DeckOps can find its own Heroic library.json entries
    # (Heroic only needs unique app_names, not random ones). Do not change:
    # existing LCD installs and their Steam shortcuts are keyed by it.
    digest = hashlib.sha256(f"deckops_plut_{game_key}".encode()).digest()
    return "do_" + base64.urlsafe_b64encode(digest)[:19].decode()


def newest_proton_dir(parent: str, prefix: str) -> str | None:
    """
    Name of the newest <prefix>* folder in parent that contains a proton
    script, or None. Numeric sort so GE-Proton9-28 > GE-Proton9-5 and
    Proton 10 > Proton 9.
    """
    if not os.path.isdir(parent):
        return None
    names = [
        d for d in os.listdir(parent)
        if d.startswith(prefix) and os.path.exists(os.path.join(parent, d, "proton"))
    ]
    return max(names, key=lambda n: tuple(int(p) for p in re.findall(r'\d+', n)), default=None)


def find_all_steam_uids() -> list[str]:
    """Return all valid Steam user ID folders from userdata/.

    Deduplicates symlinked entries by realpath and skips non-numeric or
    sub-MIN_UID folders.
    """
    if not os.path.isdir(USERDATA_DIR):
        return []
    seen, uids = set(), []
    for entry in os.listdir(USERDATA_DIR):
        if not entry.isdigit() or int(entry) < MIN_UID:
            continue
        real = os.path.realpath(os.path.join(USERDATA_DIR, entry))
        if real in seen:
            continue
        seen.add(real)
        uids.append(entry)
    return uids


def get_deck_serial() -> str | None:
    """Read the Steam Deck serial, or None.

    Tries "SteamDeckRegisteredSerialNumber" in config.vdf, then the DMI
    product serial. The config.vdf key is missing on at least one stock
    OLED. The DMI serial matches the configset_<serial>.vdf name Steam uses for
    the built-in controller (Deck-verified 2026-10-21).
    """
    try:
        with open(STEAM_CONFIG, "r", encoding="utf-8", errors="replace") as f:
            match = re.search(r'"SteamDeckRegisteredSerialNumber"\s+"([^"]+)"', f.read())
        if match:
            return match.group(1)
    except OSError:
        pass
    # Deck only: other devices' DMI serials name no Steam controller
    from detect_hw import detect_device
    if detect_device() not in ("sd_lcd", "sd_oled"):
        return None
    try:
        with open("/sys/class/dmi/id/product_serial") as f:
            return f.read().strip() or None
    except OSError:
        _log.debug("DMI serial read failed", exc_info=True)
    return None


# --- Configset patching

def record_configset_edit(configset_path: str, key: str, template_name: str):
    """Record a configset VDF edit in the wrapper ledger.

    Lazy wrapper import keeps this module a leaf. Failures are logged
    and swallowed, so ledger problems never block a profile write.
    """
    try:
        from wrapper import _record_configset
        filename = os.path.basename(configset_path)
        _record_configset(filename, key, template_name)
    except Exception:
        _log.debug("configset ledger record failed", exc_info=True)


def shortcut_title_key(title: str) -> str:
    """Configset key Game Mode reads for a non-Steam shortcut: the title in
    lowercase without / \\ ? % * : | " < > . (Steam ignores the numeric
    shortcut appid key there)."""
    return re.sub(r'[/\\?%*:|"<>.]', "", title.lower())


def patch_configset(configset_path: str, key: str, template_name: str):
    """
    Patch a single key in a configset VDF to use our template.
    If the key exists, replace its contents. If not, insert it.
    Creates the file with a root controller_config block if missing.
    Every write is recorded in the wrapper ledger for uninstall reversal.
    """
    entry = f'\t"{key}"\n\t{{\n\t\t"template"\t\t"{template_name}"\n\t}}\n'

    if not os.path.exists(configset_path):
        os.makedirs(os.path.dirname(configset_path), exist_ok=True)
        with open(configset_path, "w", encoding="utf-8") as f:
            f.write('"controller_config"\n{\n' + entry + '}\n')
        record_configset_edit(configset_path, key, template_name)
        return

    with open(configset_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # This regex works because configset entries are shallow (one level of
    # braces). [^}]* matches everything inside the block without crossing
    # into nested blocks. Do NOT reuse this pattern for deeper VDF
    # structures like config.vdf or localconfig.vdf where blocks nest
    # multiple levels deep.
    pattern = rf'\t"{re.escape(key)}"\n\t\{{[^}}]*\}}\n?'
    if re.search(pattern, content, re.MULTILINE | re.DOTALL):
        content = re.sub(pattern, entry, content, flags=re.MULTILINE | re.DOTALL)
    else:
        content = content.rstrip()
        if content.endswith("}"):
            content = content[:-1].rstrip() + "\n" + entry + "}\n"

    with open(configset_path, "w", encoding="utf-8") as f:
        f.write(content)
    record_configset_edit(configset_path, key, template_name)


def prelaunch_prefix(key: str) -> str:
    """Launch option text that runs prelaunch.sh (silent mod client update)
    before the rest of the command. Goes right before %command% or the
    option that wraps it."""
    return f'bash "{PROJECT_ROOT}/prelaunch.sh" {key} '


# CoD1 and UO copy the GL extension string into a fixed buffer and crash at
# startup ("Buffer overrun detected!"). Proton applies this fix only to the
# Steam appids 2620/2640, so non-Steam shortcuts set it themselves. It has to
# come first in a launch option, because prelaunch.sh execs its arguments as a
# command.
GL_FIX = "MESA_EXTENSION_MAX_YEAR=2003 "
GL_FIX_KEYS = ("cod1sp", "cod1mp", "coduosp", "coduomp")


# --- Wine drive letters

def nvme_compatdata(appid) -> str:
    """Internal-drive compatdata path for appid."""
    return os.path.join(STEAM_ROOT, "steamapps", "compatdata", str(appid))


def linux_to_wine_path(linux_path: str) -> str:
    """Z: drive path (Wine maps the whole Linux filesystem under Z:)."""
    return "Z:" + linux_path.replace("/", "\\")


def wine_path_for_prefix(linux_path: str, compatdata_path: str) -> str:
    """
    Windows path for linux_path as seen inside the Proton prefix at
    compatdata_path. Uses the prefix drive letter that maps the path's
    Steam library (Proton/Wine give an SD card library its own letter,
    usually D:), creating one if missing, and falls back to Z:.

    Plutonium's own launcher passes SD card games as D:\\steamapps\\....
    The same folder as Z:\\run\\media\\<card>\\... made BO2 Zombies offline
    fail with "Black Ops II server is not available" (Deck, 2026-09-25).
    Internal drive paths keep Z:, which works.
    """
    z_path = "Z:" + os.path.normpath(linux_path).replace("/", "\\")
    path = os.path.realpath(linux_path)
    dosdevices = os.path.join(compatdata_path, "pfx", "dosdevices")
    if not os.path.isdir(dosdevices):
        return z_path
    # Internal paths stay on Z: even when a letter maps them: Proton and
    # Heroic remap letters like s: between runs (Heroic prefix s: was home
    # at install, the SD card at launch, so LCD MW3 offline broke, 2026-10-06).
    home = os.path.realpath(os.path.expanduser("~"))
    if path == home or path.startswith(home + "/"):
        return z_path

    drives = {}
    for name in os.listdir(dosdevices):
        if not re.fullmatch(r"[a-y]:", name) or name == "c:":
            continue
        target = os.path.realpath(os.path.join(dosdevices, name))
        drives[name] = target

    hits = [(len(t), n) for n, t in drives.items()
            if t != "/" and (path == t or path.startswith(t + "/"))]
    if hits:
        letter = sorted(hits, key=lambda h: (-h[0], h[1]))[0][1]
    else:
        # Only give a letter to a Steam library outside home (SD card or
        # other mount); internal paths stay on Z:.
        parts = path.split("/")
        if "steamapps" not in parts:
            return z_path
        root = "/".join(parts[:parts.index("steamapps")]) or "/"
        if root == "/":
            return z_path
        free = [f"{c}:" for c in "defghijklmnopqrstuvwxy" if f"{c}:" not in drives]
        if not free:
            return z_path
        letter = free[0]
        try:
            os.symlink(root, os.path.join(dosdevices, letter))
        except OSError:
            _log.debug("drive letter create failed", exc_info=True)
            return z_path
        drives[letter] = root

    rel = os.path.relpath(path, drives[letter])
    rel = "" if rel == "." else rel.replace("/", "\\")
    return f"{letter.upper()}\\{rel}"
