"""
steam_appinfo.py: add launch menu entries to Steam's appinfo.vdf

Steam shows its "choose a launch option" dialog when an app's cached
appinfo has more than one launch entry for the current OS. DeckOps uses
that to offer mod client entries (e.g. Plutonium Online / Offline) under
the stock game entries.

Append-only by design: stock entries are never renumbered, our entries
go after the last existing key and are matched by `executable`. The one
edit to a stock entry is a "tag" argument (VANILLA_TAG): Steam drops it
together with our entries, so a launch option can tell a stock pick from
a lost menu.

Steam rewrites appinfo.vdf from Valve's servers now and then, so every
menu we add is recorded in deckops.json (`launch_menus`) and
reapply_all() puts them back. Only call with Steam closed.

Leaf module: stdlib + log, with a lazy config import.
"""

import copy
import hashlib
import os
import shutil
import struct
import tempfile

from log import get_logger

_log = get_logger(__name__)

APPINFO_V28 = 0x07564428
APPINFO_V29 = 0x07564429

# Binary KV value types
_T_DICT, _T_STR, _T_INT32, _T_FLOAT, _T_PTR = 0x00, 0x01, 0x02, 0x03, 0x04
_T_WSTR, _T_COLOR, _T_UINT64, _T_END, _T_INT64 = 0x05, 0x06, 0x07, 0x08, 0x0A
_FIXED = {_T_INT32: 4, _T_FLOAT: 4, _T_PTR: 4, _T_COLOR: 4, _T_UINT64: 8, _T_INT64: 8}

# Per-app header after appid + size: state, last_updated, pics token,
# text sha1, change number, binary sha1
_HDR = struct.Struct("<IIQ20sI20s")

VANILLA_TAG = "-deckops_vanilla"


def appinfo_path(steam_root: str) -> str:
    return os.path.join(steam_root, "appcache", "appinfo.vdf")


# --- file model

class _AppInfo:
    def __init__(self, data: bytes):
        self.data = bytearray(data)
        self.magic = struct.unpack_from("<I", data, 0)[0]
        if self.magic not in (APPINFO_V28, APPINFO_V29):
            raise ValueError(f"unsupported appinfo.vdf version {self.magic:#x}")
        self.v29 = self.magic == APPINFO_V29
        self.strings, self.str_off = [], None
        if self.v29:
            self.str_off = struct.unpack_from("<q", data, 8)[0]
            count = struct.unpack_from("<I", data, self.str_off)[0]
            pos = self.str_off + 4
            for _ in range(count):
                end = data.index(b"\x00", pos)
                self.strings.append(data[pos:end].decode("utf-8", "surrogateescape"))
                pos = end + 1
        self._index = {s: i for i, s in enumerate(self.strings)}
        self._added = []

    def find_app(self, appid: int):
        """(start, end) of the app's block including appid + size, or None."""
        pos = 16 if self.v29 else 8
        while pos + 8 <= len(self.data):
            aid, size = struct.unpack_from("<II", self.data, pos)
            if aid == 0:
                return None
            if aid == appid:
                return pos, pos + 8 + size
            pos += 8 + size
        return None

    # --- binary KV

    def parse_kv(self, buf: bytes, pos: int = 0):
        """Parse a KV dict body into [[type, key, value], ...]; returns (node, pos)."""
        node = []
        while True:
            t = buf[pos]; pos += 1
            if t == _T_END:
                return node, pos
            if self.v29:
                key = self.strings[struct.unpack_from("<I", buf, pos)[0]]; pos += 4
            else:
                end = buf.index(b"\x00", pos)
                key = buf[pos:end].decode("utf-8", "surrogateescape"); pos = end + 1
            if t == _T_DICT:
                val, pos = self.parse_kv(buf, pos)
            elif t == _T_STR:
                end = buf.index(b"\x00", pos)
                val = bytes(buf[pos:end]); pos = end + 1
            elif t == _T_WSTR:
                end = pos
                while buf[end:end + 2] != b"\x00\x00":
                    end += 2
                val = bytes(buf[pos:end]); pos = end + 2
            elif t in _FIXED:
                val = bytes(buf[pos:pos + _FIXED[t]]); pos += _FIXED[t]
            else:
                raise ValueError(f"unknown KV type {t:#x}")
            node.append([t, key, val])

    def _key(self, key: str) -> bytes:
        if not self.v29:
            return key.encode("utf-8", "surrogateescape") + b"\x00"
        if key not in self._index:
            self._index[key] = len(self.strings)
            self.strings.append(key); self._added.append(key)
        return struct.pack("<I", self._index[key])

    def encode_kv(self, node) -> bytes:
        out = bytearray()
        for t, key, val in node:
            out.append(t); out += self._key(key)
            if t == _T_DICT:
                out += self.encode_kv(val)
            elif t == _T_STR:
                out += val + b"\x00"
            elif t == _T_WSTR:
                out += val + b"\x00\x00"
            else:
                out += val
        out.append(_T_END)
        return bytes(out)

    def replace_app(self, start: int, end: int, header: tuple, node):
        kv = self.encode_kv(node)
        text_sha = hashlib.sha1(_text_vdf(node)).digest()
        bin_sha = hashlib.sha1(kv).digest()
        state, last, token, _, change, _ = header
        body = _HDR.pack(state, last, token, text_sha, change, bin_sha) + kv
        appid = struct.unpack_from("<I", self.data, start)[0]
        blob = struct.pack("<II", appid, len(body)) + body
        delta = len(blob) - (end - start)
        self.data[start:end] = blob
        if self.v29:
            self.str_off += delta
            struct.pack_into("<q", self.data, 8, self.str_off)
            if self._added:
                self.data += b"".join(s.encode("utf-8", "surrogateescape") + b"\x00" for s in self._added)
                struct.pack_into("<I", self.data, self.str_off, len(self.strings))
                self._added = []


def _text_vdf(node, depth: int = 0) -> bytes:
    # Valve's text checksum can't be reproduced exactly by any known tool.
    # Steam accepts a recomputed one, so use the conventional text layout.
    tabs, out = b"\t" * depth, b""
    esc = lambda s: s.replace(b"\\", b"\\\\")
    for t, key, val in node:
        k = esc(key.encode("utf-8", "surrogateescape"))
        if t == _T_DICT:
            out += tabs + b'"' + k + b'"\n' + tabs + b"{\n" + _text_vdf(val, depth + 1) + tabs + b"}\n"
            continue
        if t == _T_STR:
            v = esc(val)
        elif t == _T_INT32:
            v = str(struct.unpack("<I", val)[0]).encode()
        elif t in (_T_UINT64, _T_INT64):
            v = str(struct.unpack("<Q" if t == _T_UINT64 else "<q", val)[0]).encode()
        elif t == _T_FLOAT:
            v = repr(struct.unpack("<f", val)[0]).encode()
        else:
            v = val
        out += tabs + b'"' + k + b'"\t\t"' + v + b'"\n'
    return out


def _get(node, key):
    for item in node:
        if item[1] == key:
            return item
    return None


def _dict(node, key):
    item = _get(node, key)
    return item[2] if item and item[0] == _T_DICT else None


def _entry_node(entry: dict):
    node = [[_T_STR, "executable", entry["executable"].encode()]]
    if entry.get("arguments"):
        node.append([_T_STR, "arguments", entry["arguments"].encode()])
    if entry.get("description"):
        node.append([_T_STR, "description", entry["description"].encode()])
    node.append([_T_DICT, "config", [[_T_STR, "oslist", entry.get("oslist", "windows").encode()]]])
    return node


# --- edit helpers

def _tag(launch, exe: bytes, tag: bytes) -> bool:
    changed = False
    for item in launch:
        if item[0] != _T_DICT or (_get(item[2], "executable") or [0, 0, b""])[2] != exe:
            continue
        args = _get(item[2], "arguments")
        if args is None:
            item[2].insert(1, [_T_STR, "arguments", tag]); changed = True
        elif tag not in args[2].split():
            args[2] = (args[2] + b" " + tag).strip(); changed = True
    return changed


def _edit_launch(steam_root: str, appid: int, edit) -> bool:
    """Load appinfo.vdf, run edit(launch_node) on one app, write back if it changed."""
    path = appinfo_path(steam_root)
    try:
        with open(path, "rb") as f:
            raw = f.read()
        ai = _AppInfo(raw)
    except (OSError, ValueError) as ex:
        _log.warning(f"appinfo.vdf unreadable: {ex}")
        return False

    span = ai.find_app(int(appid))
    if not span:
        _log.info(f"appinfo: app {appid} not cached yet, launch menu skipped")
        return False
    start, end = span
    header = _HDR.unpack_from(ai.data, start + 8)
    kv = bytes(ai.data[start + 8 + _HDR.size:end])
    node, used = ai.parse_kv(kv)

    # Refuse to write anything we can't reproduce byte for byte.
    if used != len(kv) or ai.encode_kv(node) != kv:
        _log.warning(f"appinfo: app {appid} did not round-trip, launch menu skipped")
        return False

    launch = _dict(_dict(_dict(node, "appinfo") or [], "config") or [], "launch")
    if launch is None:
        _log.info(f"appinfo: app {appid} has no launch config, skipped")
        return False
    if not edit(launch):
        return True

    ai.replace_app(start, end, header, node)
    try:
        shutil.copy2(path, path + ".bak")
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(ai.data)
        os.replace(tmp, path)
    except OSError as ex:
        _log.warning(f"appinfo.vdf write failed: {ex}")
        return False
    return True


def _record(appid, entries=None, remove=None):
    import config as cfg
    c = cfg.load()
    menus = copy.deepcopy(c.get("launch_menus", {}))
    cur = [e for e in menus.get(str(appid), []) if e["executable"] not in (remove or ())]
    for e in entries or []:
        cur = [x for x in cur if x["executable"] != e["executable"]] + [dict(e)]
    if cur:
        menus[str(appid)] = cur
    else:
        menus.pop(str(appid), None)
    c["launch_menus"] = menus
    cfg.save(c)


# --- public API

def add_launch_entries(steam_root: str, appid: int, entries: list, record: bool = True) -> bool:
    """
    Append launch entries after the stock ones. Each entry is a dict with
    executable (relative to the install dir), description, optional
    arguments and oslist (default windows). An existing entry with the
    same executable is updated in place. An entry with "tag" instead adds
    that argument to the stock entries running its executable.
    """
    def edit(launch):
        changed = False
        for e in entries:
            if e.get("tag"):
                changed |= _tag(launch, e["executable"].encode(), e["tag"].encode())
                continue
            new = _entry_node(e)
            hit = next((item for item in launch if item[0] == _T_DICT and
                        (_get(item[2], "executable") or [0, 0, b""])[2] == e["executable"].encode()), None)
            if hit:
                if hit[2] != new:
                    hit[2] = new; changed = True
                continue
            nxt = max((int(k) for _, k, _ in launch if k.isdigit()), default=-1) + 1
            launch.append([_T_DICT, str(nxt), new]); changed = True
        return changed

    ok = _edit_launch(steam_root, appid, edit)
    if record:
        _record(appid, entries=entries)
    return ok


def remove_launch_entries(steam_root: str, appid: int, executables: list) -> bool:
    """Remove our entries (matched by executable) and forget them."""
    wanted = {x.encode() for x in executables}
    def edit(launch):
        before = len(launch)
        launch[:] = [item for item in launch if not (item[0] == _T_DICT and
                     (_get(item[2], "executable") or [0, 0, b""])[2] in wanted)]
        return len(launch) != before

    ok = _edit_launch(steam_root, appid, edit)
    _record(appid, remove=executables)
    return ok


def reapply_all(steam_root: str):
    """Re-add every recorded menu. Steam may have refreshed appinfo since."""
    import config as cfg
    for appid, entries in cfg.load().get("launch_menus", {}).items():
        add_launch_entries(steam_root, int(appid), entries, record=False)
