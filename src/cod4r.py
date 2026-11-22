"""
cod4r.py - DeckOps installer for CoD4R (Call of Duty 4: Revived)

CoD4R is a community client by k/divity that adds controller support,
a server browser, QoL improvements, and bot support to CoD4 multiplayer.

Unlike CoD4x (which uses a chain-loader DLL mechanism), CoD4R drops files
directly into the game directory:
  - main/*.iwd          (mod packages: jcod4r_00, xcommon_glyphs,
                          xcommon_cod4qol, xcommon_cod4r_weapons)
  - zone/english/*.ff   (fastfiles: cod4r_patchv2, cod4r_controls,
                          cod4r_ambfix, qol)
  - iw3mp.exe, mss32.dll (CoD4R builds, replace the stock files)
  - miles32.dll          (patched Miles Sound System library)
  - Cod4R-DedRun.exe     (dedicated server runner)
  - userraw/cod4r_id.key  (player identity key)
  - Mods/mp_bots/         (bot support mod)
plus launcher.dll and cod4r_<ver>/cod4r_<ver>.dll in the prefix's
AppData/Local/CallofDuty4MW/bin/.

Install flow:
  1. Write registry keys so Steam skips first-launch installers
  2. Fetch CoD4R's signed manifest and check its signature
  3. Download every file whose sha256 doesn't match the manifest
  4. Verify CoD4R files landed
  5. Delete servercache.dat
  6. Write metadata

DeckOps does what CoD4R-Launcher.exe does itself, without running it:
the launcher needs a GUI the user has to close, and newer builds show a
black window under Proton. Re-running the install only downloads files
that changed, so it doubles as the update.
"""

import base64
import hashlib
import json
import os
import subprocess
import tempfile

from net import download as _download
from steam_common import nvme_compatdata as _nvme_compatdata, write_json
from cod4x import _write_registry_keys  # same appid 7940 keys

from log import get_logger

_log = get_logger(__name__)


# --- constants

# CoD4R's update server, the one CoD4R-Launcher.exe uses. Plain HTTP, so
# the manifest is checked against the launcher's signing key below.
_CDN = "http://74.208.200.240"

# Public key embedded in CoD4R-Launcher.exe. manifest.json.sig is a
# base64 RSA SHA-256 signature over manifest.json.
_MANIFEST_KEY = """-----BEGIN PUBLIC KEY-----
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEA2r/t4vsfcLA6PuC6aZod
nMB58WzKrgnO64IN5zAeAbDxqWk+sjtu9L08id6UPvBPuTcqo7DwmKZQ01axFxHl
UKfHFeXGHgaM7ua4RTdcDbIxza7o6lGUhtca3Ntbi3LilF0MkzTcbwOjUdIEoUlV
kUHPZpUgY0jFmjma8TurqnOAbxzys3XnQ4gHkY0eL90p3Q2oPrwUAs1vuSe3MI8R
0/s/LIfjyKIvuyhTmLqnQ2ma5zUnCi9NUYUEvZWtCmUpIqCjgF/1ypywF3kphIsb
q90gdFSQ3O07sQwPq7zwlATmw/k/OoT4shjnoi7Md08tlbWHzokdifOcmk212uLI
Hw5da5sFDZW8omLa1DuOiWLqK810Z7rVbxdHzrtYJ6wZsWFXuTjz0JhPODMIcDGc
ETrWCgWAB+TNx1eNk4ITA4HjsTBBn4KnBAa5JuBTagC7/ZnOldJMN9erzE8ldoFE
9wBKiWkXCPtQhjQ6oEDdgsUgU+L1OBODhGPxv4U73o6De0j85ANR4tcCnqPoqzd0
nk24kQKH8EQJTDH9qo5p4/TNMrAd9wAK+U42xh8Eho7vY7JihIhzI1ShEdkqNA/Z
quSjERQjJq5Eys+oN4JPzOV31ZY9t2Ai5LofPn8r5sC1sMnrjORg9nd22LwgZZgg
kGVOa+i6OT99LMDzING0zlECAwEAAQ==
-----END PUBLIC KEY-----
"""

METADATA_FILE = "deckops_cod4r.json"

# The AppData subfolder name where the game stores runtime data
# (servercache, player configs, etc.), same as CoD4x.
_GAME_APPDATA_FOLDER = "CallofDuty4MW"

# --- helpers

def _get_game_appdata_dir(compatdata_path: str) -> str:
    """
    Return the AppData/Local/CallofDuty4MW path inside a Wine prefix.

    This is where the game stores runtime data like servercache.dat
    and player configs.
    """
    return os.path.join(
        compatdata_path,
        "pfx", "drive_c", "users", "steamuser",
        "AppData", "Local", _GAME_APPDATA_FOLDER,
    )


def _check_signature(tmp: str, log):
    key = os.path.join(tmp, "key.pem"); sig = os.path.join(tmp, "sig.bin")
    with open(key, "w") as f: f.write(_MANIFEST_KEY)
    with open(os.path.join(tmp, "manifest.json.sig"), "rb") as f: raw = base64.b64decode(f.read())
    with open(sig, "wb") as f: f.write(raw)
    try:
        r = subprocess.run(["openssl", "dgst", "-sha256", "-verify", key, "-signature", sig,
                            os.path.join(tmp, "manifest.json")], capture_output=True, text=True)
    except FileNotFoundError:
        # Same policy as net.download digests: missing tooling skips the
        # check rather than blocking the install.
        log("  openssl not found, CoD4R manifest signature not checked")
        return
    if r.returncode != 0:
        raise RuntimeError(f"CoD4R manifest signature check failed: {(r.stdout + r.stderr).strip()}")
    log("  CoD4R manifest signature verified")


def _manifest_files(m: dict, install_dir: str, compatdata_path: str) -> list:
    """(local path, manifest entry) for every CoD4R file, placed where
    CoD4R-Launcher.exe puts them (verified by hash on a launcher run)."""
    bin_dir = os.path.join(_get_game_appdata_dir(compatdata_path), "bin")
    dests = {"root": install_dir, "main": os.path.join(install_dir, "main"),
             "zone": os.path.join(install_dir, "zone", "english"), "bin": bin_dir}
    out = []
    for a in m["assets"]:
        if a["dest"] not in dests:
            raise RuntimeError(f"Unknown CoD4R manifest dest '{a['dest']}' for {a['name']}")
        out.append((os.path.join(dests[a["dest"]], os.path.basename(a["name"])), a))
    c = os.path.basename(m["client"]["path"])
    out.append((os.path.join(bin_dir, os.path.splitext(c)[0], c), m["client"]))
    out.append((os.path.join(install_dir, os.path.basename(m["dedi"]["path"])), m["dedi"]))
    return out


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()


def _verify_cod4r_files(install_dir: str, on_progress=None) -> bool:
    """
    Check that the critical CoD4R files are present in the game directory.

    Returns True if the critical files are found.
    """
    def log(msg):
        if on_progress:
            on_progress(msg)

    # Critical files that must be present for CoD4R to work
    critical = [
        os.path.join("main", "jcod4r_00.iwd"),
        os.path.join("zone", "english", "cod4r_patchv2.ff"),
        os.path.join("zone", "english", "cod4r_controls.ff"),
        "miles32.dll",
    ]

    missing = []
    for rel in critical:
        full = os.path.join(install_dir, rel)
        if not os.path.exists(full):
            missing.append(rel)

    if missing:
        log(f"  Missing CoD4R files: {', '.join(missing)}")
        return False

    log("  All critical CoD4R files verified")
    return True


# --- public API

def sync_files(install_dir: str, compatdata_path: str, log=None, prog=None,
               fetch_timeout: int = 30, tries: int = 3) -> int:
    """
    Bring the CoD4R files in line with the signed manifest and return how
    many were replaced. Used by the install and by prelaunch.py.

    Changed files download to <file>.new and are only renamed into place
    once every download succeeded, so an interrupted update (a launch
    timeout, the network dropping) leaves the previous set intact. The
    .new sits next to its target because the game folder and the prefix
    bin/ can be on different drives.
    """
    log = log or (lambda *a: None)
    prog = prog or (lambda *a: None)
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("manifest.json", "manifest.json.sig"):
            _download(f"{_CDN}/{name}", os.path.join(tmp, name),
                      label=f"CoD4R {name}", timeout=fetch_timeout, tries=tries)
        _check_signature(tmp, log)
        with open(os.path.join(tmp, "manifest.json")) as f:
            m = json.load(f)

    base = m.get("base_url", _CDN).rstrip("/")
    files = _manifest_files(m, install_dir, compatdata_path)
    todo = [(p, e) for p, e in files
            if not (os.path.isfile(p) and _sha256(p) == e["sha256"].lower())]
    log(f"  CoD4R client v{m['client']['version']}: "
        f"{len(files) - len(todo)} of {len(files)} files up to date")
    total = sum(e["size"] for _, e in todo) or 1
    done = 0
    for p, e in todo:
        new = p + ".new"
        # Left by an earlier interrupted update and already complete.
        if not (os.path.isfile(new) and _sha256(new) == e["sha256"].lower()):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            _download(
                f"{base}/{e['path']}", new,
                on_progress=lambda pct, lbl, _d=done, _s=e["size"]:
                    prog(int((_d + _s * pct / 100) / total * 100), lbl),
                label=os.path.basename(p), timeout=120,
                digest=f"sha256:{e['sha256']}",
            )
        done += e["size"]
    for p, _ in todo:
        os.replace(p + ".new", p)
    if todo:
        log(f"  Updated {len(todo)} CoD4R file(s): {', '.join(os.path.basename(p) for p, _ in todo)}")
    return len(todo)



def install_cod4r(game: dict, steam_root: str, proton_path: str,
                  compatdata_path: str, on_progress=None, appid: int = 7940,
                  source: str = "steam"):
    """
    Install or update CoD4R from its signed manifest. No Proton run and
    no user interaction; files already matching the manifest are skipped.

    Parameters:
      game            : dict from detect_games with install_dir, exe_path, etc.
      steam_root      : path to the Steam root directory (unused, common signature)
      proton_path     : path to the Proton executable (unused, common signature)
      compatdata_path : path to the game's compatdata prefix (can be None/empty)
      on_progress     : optional callback(percent: int, status: str)
      appid           : Steam appid (default 7940)
      source          : 'steam' or 'own'
    """
    install_dir = game["install_dir"]

    prog = on_progress or (lambda *a: None)

    def log(msg):
        _log.info(msg.strip())
        if on_progress:
            on_progress(0, msg)

    compatdata_path = _nvme_compatdata(str(appid))
    log(f"  Prefix path: {compatdata_path}")

    # --- Step 1: Write registry keys
    prog(5, "Writing registry keys...")
    _write_registry_keys(compatdata_path, on_progress=log)

    # --- Steps 2-3: Fetch the manifest, download changed files
    prog(10, "Fetching CoD4R manifest...")
    sync_files(install_dir, compatdata_path, log,
               lambda pct, lbl: prog(15 + int(pct * 0.6), lbl))

    # --- Step 4: Verify CoD4R files
    prog(80, "Verifying installation...")
    verified = _verify_cod4r_files(install_dir, on_progress=log)
    if not verified:
        log("  CoD4R files not fully present")
        log("  Try running DeckOps install again")

    # --- Step 5: Delete servercache.dat
    # Force a fresh server list on first launch.
    appdata_dir = _get_game_appdata_dir(compatdata_path)
    for cache_path in [
        os.path.join(install_dir, "servercache.dat"),
        os.path.join(appdata_dir, "servercache.dat"),
    ]:
        if os.path.exists(cache_path):
            os.remove(cache_path)

    prog(90, "Cleared server cache.")

    # --- Step 6: Write metadata
    prog(95, "Saving metadata...")
    write_json(os.path.join(install_dir, METADATA_FILE), {
        "client": "cod4r",
        "source": source,
        "appdata_dir": appdata_dir,
        "compatdata_path": compatdata_path,
    })

    prog(100, "CoD4R installation complete!")
