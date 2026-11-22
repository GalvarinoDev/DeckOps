"""
manifest_mods.py: manifest-driven mod installer for DeckOps

Finds known manifest files in the Games folders (home and SD card)
and installs the files for one chosen option into a Games folder
(~/Games or <SD>/Games), from a CDN base URL the user types in. Games
do not need to be installed yet; mod files overwrite whatever is
already there.

Manifests never carry links. DeckOps rejects any manifest containing
one. The manifest says what to install and the user says where it
comes from. Files are installed as-is (no archives, nothing is
executed) and every file is size checked, plus hash checked when the
manifest gives one (md5, sha1, sha256, sha512 or blake2b hex, told apart
by length; anything else means size only). A receipt in
<games>/.deckops_manifests/ lists what was installed so updates and
option switches only touch those files.

One CDN URL is shared by all mods. It is remembered in deckops.json and
mirrored into the save backup folder, which survives uninstall.

Any .json in a Games folder that looks like a manifest is listed; its
name, options and id all come from the file. Other JSON files are ignored.

Manifest format (paths are relative to the Games folder):
    {"schema": 1, "id": "some_mod", "name": "Shown mod name",
     "version": "1.0", "description": "optional",
     "options": [
        {"id": "any_slug", "name": "Shown option name", "description": "optional",
         "files": [{"path": "Some Game/mods/x.ff", "sha256": "<64 hex>", "size": 123}]}
     ]}

Component format (no schema; components can be combined, required ones always
install, id/name default to the filename minus a manifest_ prefix):
    {"ManifestHash": "...",
     "components": {"base": {"displayName": "Shown name", "show": true,
                             "required": true, "defaultEnabled": true}},
     "files": [["Some Game/mods/x.ff", 123, "<64 hex>", "base"]]}
"""

import glob
import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from log import get_logger
from net import download as _download, DownloadError

_log = get_logger(__name__)

SCHEMA = 1
MAX_OPTIONS = 3
RECEIPT_DIR = ".deckops_manifests"
# Mod CDN gets a curl UA rather than the fake browser one other downloads use.
MOD_HEADERS = {"User-Agent": "curl/8.9.1", "Accept": "*/*"}


_LINK_RE = re.compile(r"://|^//|^www\.", re.I)
_HEX = re.compile(r"^(?:[0-9a-f]{16}|[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64}|[0-9a-f]{128})$")
# The "sha256" field name is kept for receipts. Any of these is accepted by length.
try:
    import xxhash as _xxhash
except ImportError:
    _xxhash = None
_HASH_ALGOS = {32: ("md5",), 40: ("sha1",), 64: ("sha256",), 128: ("sha512", "blake2b")}
if _xxhash:
    _HASH_ALGOS[16] = ("xxh3_64",)
_SLUG = re.compile(r"^[a-z0-9_-]{1,32}$")


class ManifestError(ValueError):
    pass


# --- Locations

def _games_in(base: str) -> str:
    # Reuse a lowercase games/ if that is what the user already has.
    lower = os.path.join(base, "games")
    return lower if os.path.isdir(lower) and not os.path.isdir(os.path.join(base, "Games")) \
        else os.path.join(base, "Games")


def games_roots() -> list:
    """Candidate install targets: ~/Games first, then Games on each writable mounted card/drive."""
    user = os.environ.get("USER", "deck")
    out, seen = [], set()
    mounts = sorted(set(glob.glob(f"/run/media/{user}/*") + glob.glob("/run/media/deck/*")
                        + glob.glob("/run/media/mmcblk0p1")))
    for base in [os.path.expanduser("~")] + mounts:
        if not os.path.isdir(base) or not os.access(base, os.W_OK):
            continue
        g = _games_in(base)
        real = os.path.realpath(g)
        if real not in seen:
            seen.add(real); out.append(g)
    return out


# --- Scan

def manifest_dirs() -> list:
    """Games on home, then Games on each card/drive. Only ones that exist."""
    return [d for d in games_roots() if os.path.isdir(d)]


def _looks_like_manifest(p: str) -> bool:
    # Cheap sniff so unrelated JSON files in Games are skipped silently.
    try:
        if os.path.getsize(p) > 4 << 20:
            return False
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return isinstance(d, dict) and (("schema" in d and "options" in d)
                                        or ("components" in d and "files" in d))
    except (OSError, ValueError):
        return False


def scan_manifests(folders: list = None) -> list:
    """Return [{"file", "path", "manifest"} | {"file", "path", "error"}] for manifest
    .json files at the top level of each folder. First copy of a mod id wins."""
    found, taken = [], set()
    for folder in folders or manifest_dirs():
        try:
            names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".json"))
        except OSError:
            continue
        for name in names:
            p = os.path.join(folder, name)
            if not os.path.isfile(p) or not _looks_like_manifest(p):
                continue
            try:
                m = load_manifest(p)
            except ManifestError as e:
                _log.warning("manifest %s rejected: %s", p, e)
                found.append({"file": name, "path": p, "error": str(e)})
                continue
            if m["id"] in taken:
                _log.info("manifest %s: duplicate id %s, ignoring", p, m["id"])
                continue
            taken.add(m["id"])
            found.append({"file": name, "path": p, "manifest": m})
    return found


# --- Validation

def _walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k; yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


def _check_relpath(p: str):
    if not isinstance(p, str) or not p or len(p) > 240:
        raise ManifestError(f"bad path: {p!r}")
    if "\\" in p or ":" in p or p.startswith("/") or any(ord(c) < 32 for c in p):
        raise ManifestError(f"bad path: {p!r}")
    parts = p.split("/")
    if any(x in ("", ".", "..") for x in parts):
        raise ManifestError(f"bad path: {p!r}")
    if parts[0] == RECEIPT_DIR:
        raise ManifestError(f"reserved path: {p!r}")


def _text(v, field: str, maxlen: int, required: bool = True) -> str:
    if v is None and not required:
        return ""
    if not isinstance(v, str) or not v.strip() or len(v) > maxlen \
            or any(ord(c) < 32 and c != "\n" for c in v):
        raise ManifestError(f"bad {field}")
    return v.strip()


def _check_files(files, where: str):
    if not isinstance(files, list) or not files:
        raise ManifestError(f"{where}: no files listed")
    seen, unhashed = set(), []
    for f in files:
        if not isinstance(f, dict):
            raise ManifestError(f"{where}: bad file entry")
        _check_relpath(f.get("path"))
        if f["path"].lower() in seen:
            raise ManifestError(f"{where}: duplicate path {f['path']}")
        seen.add(f["path"].lower())
        # Hash is optional: anything that is not a known hex hash means size check only.
        h = f.get("sha256"); h = h.strip().lower() if isinstance(h, str) else ""
        f["sha256"] = h if _HEX.match(h) else ""
        if not f["sha256"]:
            unhashed.append(f["path"])
        if not isinstance(f.get("size"), int) or isinstance(f["size"], bool) or f["size"] <= 0:
            raise ManifestError(f"{where}: bad size for {f['path']}")
    if unhashed:
        _log.info("manifest %s: %d file(s) without a usable hash, size check only (first: %s)",
                  where, len(unhashed), unhashed[0])


def load_manifest(path: str) -> dict:
    try:
        if os.path.getsize(path) > 4 << 20:
            raise ManifestError("manifest too large")
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError) as e:
        raise ManifestError(f"unreadable: {e}")
    if not isinstance(m, dict):
        raise ManifestError("not a JSON object")
    for s in _walk_strings(m):
        if _LINK_RE.search(s):
            raise ManifestError("manifests must not contain links")
    if "schema" not in m and "components" in m:
        return _load_components(m, path)
    if m.get("schema") != SCHEMA:
        raise ManifestError(f"unsupported schema {m.get('schema')!r}")
    # id names the receipt file, so keep it a plain slug.
    if not isinstance(m.get("id"), str) or not _SLUG.match(m["id"]):
        raise ManifestError(f"bad id {m.get('id')!r}")
    opts = m.get("options")
    if not isinstance(opts, list) or not 1 <= len(opts) <= MAX_OPTIONS:
        raise ManifestError(f"need 1 to {MAX_OPTIONS} options")
    ids = set()
    for o in opts:
        oid = o.get("id") if isinstance(o, dict) else None
        if not isinstance(oid, str) or not _SLUG.match(oid):
            raise ManifestError(f"bad option id {oid!r}")
        if oid in ids:
            raise ManifestError(f"duplicate option {oid!r}")
        ids.add(oid)
        o["name"] = _text(o.get("name"), f"{oid} name", 80)
        o["description"] = _text(o.get("description"), f"{oid} description", 500, False)
        _check_files(o.get("files"), oid)
    m["name"] = _text(m.get("name"), "name", 80)
    m["description"] = _text(m.get("description"), "description", 1000, False)
    m["version"] = _text(m.get("version"), "version", 32, False)
    m["mode"] = "options"
    return m


def _load_components(raw: dict, path: str) -> dict:
    # Component format: components can be combined. Files are [path, size, sha256, component] rows.
    stem = re.sub(r"^manifest[_-]?", "", os.path.splitext(os.path.basename(path))[0], flags=re.I)
    mid = raw.get("id", re.sub(r"[^a-z0-9_-]", "", stem.lower())[:32])
    if not isinstance(mid, str) or not _SLUG.match(mid):
        raise ManifestError(f"bad id {mid!r}")
    comps = raw.get("components")
    if not isinstance(comps, dict) or not comps:
        raise ManifestError("no components")
    out = {}
    for cid, c in comps.items():
        if not _SLUG.match(cid) or not isinstance(c, dict):
            raise ManifestError(f"bad component {cid!r}")
        out[cid] = {"id": cid, "name": _text(c.get("displayName"), f"{cid} displayName", 80),
                    "description": _text(c.get("description"), f"{cid} description", 500, False),
                    "show": c.get("show", True) is not False, "required": c.get("required") is True,
                    "default": c.get("defaultEnabled") is True, "files": []}
    rows = raw.get("files")
    if not isinstance(rows, list) or not rows:
        raise ManifestError("no files listed")
    for r in rows:
        if not isinstance(r, list) or len(r) != 4:
            raise ManifestError(f"bad file row {r!r}"[:120])
        if r[3] not in out:
            raise ManifestError(f"{r[0]!r} names unknown component {r[3]!r}")
        out[r[3]]["files"].append({"path": r[0], "size": r[1], "sha256": r[2]})
    _check_files([f for c in out.values() for f in c["files"]], "files")
    # Empty components have nothing to install. Hidden optional ones could never be picked.
    keep = [c for c in out.values() if c["files"] and (c["show"] or c["required"])]
    if not keep:
        raise ManifestError("no installable components")
    mh = raw.get("ManifestHash")
    ver = raw.get("version", mh[:12] if isinstance(mh, str) else None)
    cdn_path = raw.get("cdn_path") or f"{stem.lower()}_game_files"
    if not isinstance(cdn_path, str) or "/" in cdn_path or "\\" in cdn_path \
            or cdn_path.startswith(".") or len(cdn_path) > 64:
        raise ManifestError(f"bad cdn_path {cdn_path!r}")
    install_dir = raw.get("install_dir") or stem.lower()
    if not isinstance(install_dir, str) or "/" in install_dir or "\\" in install_dir \
            or install_dir.startswith(".") or len(install_dir) > 64:
        raise ManifestError(f"bad install_dir {install_dir!r}")
    return {"mode": "components", "id": mid, "components": keep, "options": [],
            "name": _text(raw.get("name", stem), "name", 80),
            "description": _text(raw.get("description"), "description", 1000, False),
            "version": _text(ver, "version", 32, False),
            "cdn_path": cdn_path, "install_dir": install_dir}


def build_selection(m: dict, ids) -> dict:
    """Chosen components plus required ones, merged into one option-shaped dict."""
    known = {c["id"] for c in m["components"]}
    want = {i for i in ids if i} | {c["id"] for c in m["components"] if c["required"]}
    if want - known:
        raise ManifestError(f"{m['id']} has no component {sorted(want - known)[0]!r}")
    sel = [c for c in m["components"] if c["id"] in want]
    return {"id": "+".join(c["id"] for c in sel),
            "name": ", ".join(c["name"] for c in sel if c["show"]) or m["name"],
            "files": [f for c in sel for f in c["files"]]}


def get_option(m: dict, option_id: str) -> dict:
    if m.get("mode") == "components":
        return build_selection(m, (option_id or "").split("+"))
    for o in m["options"]:
        if o["id"] == option_id:
            return o
    raise ManifestError(f"{m['id']} has no option {option_id!r}")


def option_hash(opt: dict) -> str:
    rows = sorted(f"{f['path']}|{f['sha256'].lower()}|{f['size']}" for f in opt["files"])
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()[:16]


def total_size(opt: dict) -> int:
    return sum(f["size"] for f in opt["files"])


# --- CDN

def normalize_cdn(text: str) -> str:
    """User-typed CDN base -> https://host/path/ or ManifestError."""
    s = (text or "").strip()
    if "://" not in s:
        s = "https://" + s
    u = urlsplit(s)
    if u.scheme.lower() != "https":
        raise ManifestError("CDN must use https://")
    if not u.hostname or u.username or u.password:
        raise ManifestError("CDN URL has no valid host")
    path = u.path if u.path.endswith("/") else u.path + "/"
    return urlunsplit(("https", u.netloc.lower(), path, "", ""))


def _file_url(cdn: str, relpath: str) -> str:
    url = urljoin(cdn, quote(relpath))
    b, u = urlsplit(cdn), urlsplit(url)
    if u.netloc != b.netloc or not u.path.startswith(b.path):
        raise ManifestError(f"path escapes CDN base: {relpath}")
    return url


# --- Remembered CDN (deckops.json + backup mirror)

def _cdn_backup_path() -> str:
    from save_backup import BACKUP_ROOT
    return os.path.join(BACKUP_ROOT, "manifest_cdn.json")


def get_saved_cdn() -> str:
    import config as cfg
    cdn = cfg.load().get("manifest_cdn") or ""
    if not cdn:
        try:
            with open(_cdn_backup_path()) as f:
                cdn = (json.load(f) or {}).get("cdn", "")
        except (OSError, ValueError, AttributeError):
            cdn = ""
    return cdn if isinstance(cdn, str) else ""


def save_cdn(cdn: str):
    import config as cfg
    c = cfg.load(); c["manifest_cdn"] = cdn; cfg.save(c)
    bp = _cdn_backup_path()
    try:
        os.makedirs(os.path.dirname(bp), exist_ok=True)
        tmp = bp + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"cdn": cdn}, f, indent=2)
        os.replace(tmp, bp)
    except OSError:
        _log.warning("could not mirror manifest CDN to backup", exc_info=True)


def _remember(mod_id: str, **fields):
    import config as cfg
    c = cfg.load()
    mods = dict(c.get("manifest_mods") or {})
    mods[mod_id] = {**(mods.get(mod_id) or {}), **fields}
    c["manifest_mods"] = mods
    cfg.save(c)


def _safe_dest(root: str, relpath: str) -> str:
    root = os.path.realpath(root)
    dest = os.path.realpath(os.path.join(root, *relpath.split("/")))
    if os.path.commonpath([root, dest]) != root or dest == root:
        raise ManifestError(f"path escapes target: {relpath}")
    return dest


# --- Receipts

def install_root(games_root: str, m: dict) -> str:
    d = m.get("install_dir")
    return os.path.join(games_root, d) if d else games_root


def _receipt_path(root: str, mod_id: str) -> str:
    return os.path.join(root, RECEIPT_DIR, f"{mod_id}.json")


def get_receipt(root: str, mod_id: str) -> dict:
    try:
        with open(_receipt_path(root, mod_id)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def is_installed(root: str, mod_id: str) -> bool:
    return bool(get_receipt(root, mod_id).get("complete"))


def _write_receipt(root: str, m: dict, opt: dict, cdn: str, overwritten: list, failed: list):
    rp = _receipt_path(root, m["id"])
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    tmp = rp + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"id": m["id"], "name": m["name"], "version": m["version"],
                   "option": opt["id"], "option_hash": option_hash(opt),
                   "cdn_host": urlsplit(cdn).netloc,
                   "installed_at": datetime.now().isoformat(),
                   "files": {x["path"]: x["sha256"] or f"size:{x['size']}" for x in opt["files"]},
                   "overwritten": sorted(overwritten),
                   "complete": not failed, "failed": sorted(failed)}, f, indent=2)
    os.replace(tmp, rp)


# --- Install / update

def _hash_ok(path: str, want: str) -> bool:
    # Algorithm is picked by hash length. 128 hex could be sha512 or blake2b, so try both in one read.
    want = want.lower()
    algos = _HASH_ALGOS.get(len(want), ())
    if not algos:
        return False
    if "xxh3_64" in algos:
        if not _xxhash:
            return False
        h = _xxhash.xxh3_64()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest() == want
    hs = [hashlib.new(a) for a in algos]
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            for h in hs:
                h.update(chunk)
    return any(h.hexdigest() == want for h in hs)


def _receipt_ok(path: str, tag: str) -> bool:
    # Receipt entries are a hash, or "size:<n>" for files the manifest gave no hash.
    if tag.startswith("size:"):
        return tag[5:].isdigit() and os.path.getsize(path) == int(tag[5:])
    if not _can_verify(tag):
        return os.path.isfile(path)
    return _hash_ok(path, tag)


def _can_verify(h: str) -> bool:
    return bool(h) and bool(_HASH_ALGOS.get(len(h)))


def _matches(path: str, entry: dict) -> bool:
    try:
        if os.path.getsize(path) != entry["size"]:
            return False
        h = entry["sha256"]
        if not h or not _can_verify(h):
            return True
        return _hash_ok(path, h)
    except OSError:
        return False


def _remove(path: str, root: str):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    root = os.path.realpath(root)
    d = os.path.dirname(path)
    while os.path.realpath(d) != root and os.path.commonpath([root, os.path.realpath(d)]) == root:
        try:
            os.rmdir(d)
        except OSError:
            break
        d = os.path.dirname(d)


def _remove_ours(root: str, receipt: dict, keep: set = frozenset()):
    """Remove receipt files not in keep, only if they are still the file we installed.
    Files that were there before us, or changed since, are left alone."""
    skip = set(receipt.get("overwritten", [])) | set(keep)
    for p, sha in (receipt.get("files") or {}).items():
        if p in skip:
            continue
        try:
            _check_relpath(p); dest = _safe_dest(root, p)
        except ManifestError:
            _log.warning("manifest %s: skipped bad receipt entry %r", receipt.get("id"), p)
            continue
        try:
            if os.path.isfile(dest) and _receipt_ok(dest, sha):
                _remove(dest, root)
        except OSError:
            pass


def install_manifest(m: dict, option_id: str, cdn_text: str, games_root: str,
                     on_progress=None, on_log=None) -> list:
    """Install or switch to one option of a validated manifest. Returns failed paths."""
    prog = on_progress or (lambda *a: None)
    def log(msg):
        if on_log:
            on_log(msg)

    opt = get_option(m, option_id)
    base = normalize_cdn(cdn_text); cdn = base
    if m.get("cdn_path"):
        cdn = base + quote(m["cdn_path"]) + "/"
    if not games_root:
        raise ManifestError("no Games folder chosen")
    dest_root = install_root(games_root, m)
    os.makedirs(dest_root, exist_ok=True)
    plan = [(f, _safe_dest(dest_root, f["path"]), _file_url(cdn, f["path"])) for f in opt["files"]]

    free = shutil.disk_usage(dest_root).free
    if total_size(opt) > free:
        raise ManifestError(f"not enough space: need {total_size(opt) >> 20} MB, have {free >> 20} MB")

    log(f"CDN: {cdn}")
    log(f"Target: {dest_root}")
    log(f"{len(plan)} files, {total_size(opt) >> 20} MB total")
    # Remember the base only. cdn_path differs per manifest.
    save_cdn(base)
    old = get_receipt(dest_root, m["id"])
    ours = old.get("files") or {}
    overwritten = [p for p in old.get("overwritten", []) if p in {f["path"] for f in opt["files"]}]
    total, errors = len(plan), []
    # Bar is weighted by bytes so one big file does not crawl at the end.
    size_all = max(total_size(opt), 1)
    done_b = 0
    pct = lambda b: 2 + int(b * 96 / size_all)
    prog(2, f"Installing {opt['name']} ({total} files)...")

    for i, (f, dest, url) in enumerate(plan):
        base_b = done_b; done_b += f["size"]
        if os.path.isfile(dest):
            prog(pct(base_b), f"Verifying {i + 1}/{total}: {f['path']}")
            if _matches(dest, f):
                log(f"  skip {f['path']} (up to date)")
                continue
            if f["path"] not in ours and f["path"] not in overwritten:
                overwritten.append(f["path"])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        log(f"  get  {f['path']}")
        try:
            _download(url, dest, timeout=300, headers=MOD_HEADERS, label=f"{i + 1}/{total}: {f['path']}",
                      on_progress=lambda p, msg, _b=base_b, _s=f["size"]: prog(pct(_b + _s * p // 100), msg))
        except DownloadError as ex:
            log(f"✗ download failed: {f['path']} ({ex})")
            errors.append(f["path"]); continue
        except Exception as ex:
            _log.warning("manifest %s: download failed for %s", m["id"], f["path"], exc_info=True)
            log(f"✗ download failed: {f['path']} ({ex})")
            errors.append(f["path"]); continue
        if not _matches(dest, f):
            _log.warning("manifest %s: checksum mismatch for %s", m["id"], f["path"])
            log(f"✗ checksum mismatch: {f['path']}")
            _remove(dest, dest_root)
            errors.append(f["path"])

    # Switching option or version: drop our files the new option does not list.
    _remove_ours(dest_root, old, keep={f["path"] for f in opt["files"]})

    _write_receipt(dest_root, m, opt, cdn, overwritten, errors)
    _remember(m["id"], option=opt["id"], games_root=games_root, complete=not errors,
              option_hash=option_hash(opt), installed_at=datetime.now().isoformat())

    if errors:
        prog(100, f"Installed with {len(errors)} error(s)")
        _log.warning("manifest %s install errors: %s", m["id"], errors)
    else:
        prog(100, f"{opt['name']} installed!")
    return errors


def needs_update(m: dict, games_root: str) -> bool:
    r = get_receipt(games_root, m["id"])
    if not r.get("complete"):
        return True
    try:
        return r.get("option_hash") != option_hash(get_option(m, r.get("option")))
    except ManifestError:
        return True

