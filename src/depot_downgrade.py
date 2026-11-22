"""
depot_downgrade.py - Unified 32-bit depot downgrade helper

Activision pushed 64-bit updates for MW3, Ghosts, and Advanced
Warfare that break community client compatibility (Plutonium,
AlterWare). This module detects 64-bit installs, walks the user
through a QR-code login (DepotDownloader) or a manual Steam console
paste, and merges the 32-bit depot files into the game folder
(MW3: into downgrade/).

Steam installs only. Own installs are left alone because the user
supplies the files.
"""

import json
import os
import re
import shutil
import struct
import subprocess
import zipfile

from log import get_logger, redact_also
from net import download, github_asset
from steam_common import write_json

_log = get_logger(__name__)

# --- Game configurations

# The depots each game needs for a 32-bit downgrade.

GAME_CONFIGS = {
    "iw5": {
        "name": "Modern Warfare 3",
        "app_id": 42680,
        "depots": (
            {"depot": 42681, "manifest": "5651167211650965131"},
            {"depot": 42682, "manifest": "2661317971072643596", "app": 42690},
            {"depot": 42683, "manifest": "1595601894688570808", "app": 42690},
            {"depot": 42691, "manifest": "4104640605720756125", "app": 42690},
            # Dedicated Server only. App 42750 also lists 42682/42683, so a
            # DS-only install fetches its whole set under the DS license.
            {"depot": 42751, "manifest": "9089183337461621316", "app": 42750},
        ),
        "depot_ids": (42681, 42682, 42683, 42691, 42751),
        "depot_cmds": (
            "download_depot 42680 42681 5651167211650965131",
            "download_depot 42690 42682 2661317971072643596",
            "download_depot 42690 42683 1595601894688570808",
            "download_depot 42690 42691 4104640605720756125",
            "download_depot 42750 42751 9089183337461621316",
        ),
        "ds_app_id": 42750,
        "ds_depot_ids": (42682, 42751, 42683),
        "detection_exe": "iw5sp.exe",
        "marker_file": os.path.join("main", "iw_00.iwd"),
        "marker_threshold": 380 * 1024 * 1024,
        "sp_depot_id": 42681,
        "dlc": {
            "1": {
                "name": "Collection 1",
                "app": 42690, "depot": 42695,
                "manifest": "9005316271397236436",
                "marker": os.path.join("zone", "dlc", "mp_overwatch.ff"),
                "marker_size": 77324309,
            },
            "2": {
                "name": "Collection 2",
                "app": 42690, "depot": 42696,
                "manifest": "2478272765185873756",
                "marker": os.path.join("zone", "dlc", "mp_cement.ff"),
                "marker_size": 94543893,
            },
            "3": {
                "name": "Collection 3 (Chaos Pack)",
                "app": 42690, "depot": 42697,
                "manifest": "5810618727794750362",
                "marker": os.path.join("zone", "dlc", "mp_crosswalk_ss.ff"),
                "marker_size": 74227733,
            },
            "4": {
                "name": "Collection 4 (Final Assault)",
                "app": 42690, "depot": 42698,
                "manifest": "5997898371746217629",
                "marker": os.path.join("zone", "dlc", "mp_shipbreaker.ff"),
                "marker_size": 80756757,
            },
        },
    },
    "iw6": {
        "name": "Call of Duty: Ghosts",
        "app_id": 209160,
        "always_64bit": True,
        "depots": (
            {"depot": 209161, "manifest": "2184173331509504109"},
            {"depot": 209163, "manifest": "4970028369212033415"},
            {"depot": 209162, "manifest": "7362622108341025052", "app": 209170},
            {"depot": 209164, "manifest": "8983067619469855177", "app": 209170},
            {"depot": 209171, "manifest": "5223938320976514402", "app": 209170},
            {"depot": 209172, "manifest": "1215466573079763620", "app": 209170},
        ),
        "depot_ids": (209161, 209163, 209162, 209164, 209171, 209172),
        "depot_cmds": (
            "download_depot 209160 209161 2184173331509504109",
            "download_depot 209160 209163 4970028369212033415",
            "download_depot 209170 209162 7362622108341025052",
            "download_depot 209170 209164 8983067619469855177",
            "download_depot 209170 209171 5223938320976514402",
            "download_depot 209170 209172 1215466573079763620",
        ),
        "detection_exe": "iw6sp64_ship.exe",
        "detection_exe_alt": "iw6mp64_ship.exe",
        "marker_file": None,
        "marker_threshold": None,
        "dlc": {
            "onslaught": {
                "name": "Onslaught",
                "app": 209170, "depot": 259250,
                "manifest": "858753029120825623",
            },
            "devastation": {
                "name": "Devastation",
                "app": 209170, "depot": 259251,
                "manifest": "1150481678624215672",
            },
            "invasion": {
                "name": "Invasion",
                "app": 209170, "depot": 259252,
                "manifest": "3583786073939989181",
            },
            "nemesis": {
                "name": "Nemesis",
                "app": 209170, "depot": 259253,
                "manifest": "6264908471824415901",
            },
        },
    },
    "s1": {
        "name": "Call of Duty: Advanced Warfare",
        "app_id": 209650,
        "always_64bit": True,
        "depots": (
            {"depot": 209651, "manifest": "8904987612539955698"},
            {"depot": 209652, "manifest": "7997216963741037244"},
            {"depot": 310340, "manifest": "3027530553092813409", "app": 209660},
            {"depot": 310341, "manifest": "7286983045129950292", "app": 209660},
            {"depot": 310342, "manifest": "1115818459498978172", "app": 209660},
            {"depot": 310351, "manifest": "1373781635064905469", "app": 209660},
            {"depot": 310352, "manifest": "3190197747840803077", "app": 209660},
            {"depot": 310353, "manifest": "1786374612997832970", "app": 209660},
            {"depot": 310343, "manifest": "4656459945361775496", "app": 209660},
        ),
        "depot_ids": (209651, 209652, 310340, 310341, 310342,
                      310351, 310352, 310353, 310343),
        "depot_cmds": (
            "download_depot 209650 209651 8904987612539955698",
            "download_depot 209650 209652 7997216963741037244",
            "download_depot 209660 310340 3027530553092813409",
            "download_depot 209660 310341 7286983045129950292",
            "download_depot 209660 310342 1115818459498978172",
            "download_depot 209660 310351 1373781635064905469",
            "download_depot 209660 310352 3190197747840803077",
            "download_depot 209660 310353 1786374612997832970",
            "download_depot 209660 310343 4656459945361775496",
        ),
        "detection_exe": "s1_sp64_ship.exe",
        "marker_file": None,
        "marker_threshold": None,
        "dlc": {
            "atlas_gorge": {
                "name": "Atlas Gorge",
                "app": 209660, "depot": 318790,
                "manifest": "1858867507944457961",
            },
            "havoc": {
                "name": "Havoc",
                "app": 209660, "depot": 318791,
                "manifest": "1768298366781761218",
            },
            "ascendance": {
                "name": "Ascendance",
                "app": 209660, "depot": 318792,
                "manifest": "5542785062311499763",
            },
            "supremacy": {
                "name": "Supremacy",
                "app": 209660, "depot": 318793,
                "manifest": "2176153660918059816",
            },
            "reckoning": {
                "name": "Reckoning",
                "app": 209660, "depot": 318794,
                "manifest": "901586032961765427",
            },
        },
    },
}


# --- DepotDownloader paths

DEPOTDOWNLOADER_DIR = os.path.expanduser(
    "~/.local/share/deckops/depotdownloader"
)
DEPOTDOWNLOADER_BIN = os.path.join(DEPOTDOWNLOADER_DIR, "DepotDownloader")

REQUIRED_FREE_SPACE_GB = 15


# --- Detection

def is_pe_64bit(exe_path: str) -> bool | None:
    """
    Read a Windows exe's PE header to get its bitness.
    Returns True (64-bit), False (32-bit), or None (not a valid PE).
    """
    try:
        with open(exe_path, "rb") as f:
            if f.read(2) != b"MZ":
                return None
            f.seek(0x3C)
            pe_offset = struct.unpack("<I", f.read(4))[0]
            f.seek(pe_offset)
            if f.read(4) != b"PE\0\0":
                return None
            machine = struct.unpack("<H", f.read(2))[0]
            if machine == 0x8664:
                return True
            if machine == 0x014C:
                return False
            return None
    except (OSError, struct.error) as ex:
        _log.warning("PE header check failed for %s: %s", exe_path, ex)
        return None


# --- Downgrade receipt
#
# After a merge, deckops_depot.json in the game folder records every file the
# old depots put there and its size. It alone decides "already downgraded"
# for every game. It survives a DeckOps config reset, and a Steam
# update/verify shows up as missing or resized files.
# Only data files are compared: mod clients and the DeckOps wrapper overwrite
# exes/dlls (iw5mp.exe, iw5mp_server.exe, ...), which must not count as an upgrade.

RECEIPT_NAME = "deckops_depot.json"
_UNCHECKED_EXTS = (".exe", ".dll", ".asi", ".ini", ".cfg", ".txt", ".json", ".log")

# MW3 depot files live in a downgrade/ subfolder so the 64-bit
# Steam install stays intact and Steam Verify never re-corrupts it.
_IW5_SUBDIR = "downgrade"


def plut_game_dir(game_key: str, install_dir: str, source: str = "steam") -> str:
    """Game dir Plutonium should load. Steam MW3 plays from downgrade/."""
    if game_key in ("iw5mp", "iw5mp_ds") and source != "own" and install_dir:
        return os.path.join(install_dir, _IW5_SUBDIR)
    return install_dir


def _merge_dir(game_id: str, install_dir: str) -> str:
    if game_id == "iw5":
        return os.path.join(install_dir, _IW5_SUBDIR)
    return install_dir


def _receipt_path(game_id: str, install_dir: str) -> str:
    return os.path.join(_merge_dir(game_id, install_dir), RECEIPT_NAME)


def _write_receipt(game_id: str, install_dir: str, merged: dict):
    from datetime import datetime
    target = _merge_dir(game_id, install_dir)
    path = _receipt_path(game_id, install_dir)
    data = {}
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    if data.get("game_id") != game_id:
        data = {"game_id": game_id, "files": {}}
    data.setdefault("files", {}).update(merged)
    data["manifests"] = {str(d["depot"]): d["manifest"] for d in GAME_CONFIGS[game_id]["depots"]}
    data["updated_at"] = datetime.now().isoformat()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_json(path, data, indent=1)
        _log.info("Wrote downgrade receipt for %s (%d files)", game_id, len(data["files"]))
    except OSError as ex:
        _log.warning("Could not write downgrade receipt %s: %s", path, ex)


def clear_receipt(game_id: str, install_dir: str):
    try:
        os.remove(_receipt_path(game_id, install_dir))
    except FileNotFoundError:
        pass
    except OSError as ex:
        _log.warning("Could not remove downgrade receipt: %s", ex)


def _receipt_status(game_id: str, install_dir: str):
    """True = receipt matches the files on disk, False = files changed since
    (Steam update/verify), None = no usable receipt (install predates receipts)."""
    target = _merge_dir(game_id, install_dir)
    try:
        with open(_receipt_path(game_id, install_dir)) as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as ex:
        _log.warning("Unreadable downgrade receipt in %s: %s", target, ex)
        return None
    if data.get("game_id") != game_id or not data.get("files"):
        return None
    files = {rf: sz for rf, sz in data["files"].items() if not rf.lower().endswith(_UNCHECKED_EXTS)}
    if not files:
        files = data["files"]
    for rf, size in files.items():
        p = os.path.join(target, rf)
        try:
            if os.path.getsize(p) != size:
                _log.info("%s receipt mismatch: %s size changed", game_id, rf)
                return False
        except OSError:
            _log.info("%s receipt mismatch: %s missing", game_id, rf)
            return False
    return True


def is_downgrade_needed(game_id: str, install_dir: str) -> bool:
    """
    Check whether a game install needs older depot files. The receipt written
    by merge_depots decides for every game. Installs from before receipts
    fall back to the old per-game checks.
    """
    if game_id not in GAME_CONFIGS:
        return False
    status = _receipt_status(game_id, install_dir)
    if status is not None:
        _log.debug("%s receipt check -> %s", GAME_CONFIGS[game_id]["name"],
                   "downgraded" if status else "files changed, downgrade needed")
        return not status
    return _legacy_downgrade_needed(game_id, install_dir)


def _legacy_downgrade_needed(game_id: str, install_dir: str) -> bool:
    """Pre-receipt detection: config flag (Ghosts/AW), marker size (MW3), PE header (MW2)."""
    cfg = GAME_CONFIGS.get(game_id)
    if not cfg:
        return False

    if cfg.get("always_64bit"):
        from config import is_depot_patched
        needed = not is_depot_patched(game_id)
        _log.debug("%s always-64bit, depot_patched=%s -> needed=%s",
                   cfg["name"], not needed, needed)
        return needed

    # MW3 depot files live in downgrade/. No folder means no downgrade yet.
    if game_id == "iw5":
        dg_dir = _merge_dir("iw5", install_dir)
        if not os.path.isdir(dg_dir):
            _log.debug("MW3 downgrade/ folder missing -> needed")
            return True
        marker = os.path.join(dg_dir, cfg["marker_file"])
        if os.path.isfile(marker):
            try:
                size = os.path.getsize(marker)
                is_64 = size > cfg["marker_threshold"]
                _log.debug("MW3 downgrade/ marker size: %d -> %s",
                           size, "64-bit" if is_64 else "32-bit")
                return is_64
            except OSError as ex:
                _log.warning("Failed to stat marker %s: %s", marker, ex)
        return True

    # Marker file check (other games with markers)
    if cfg.get("marker_file") and cfg.get("marker_threshold"):
        marker = os.path.join(install_dir, cfg["marker_file"])
        if os.path.isfile(marker):
            try:
                size = os.path.getsize(marker)
                is_64 = size > cfg["marker_threshold"]
                _log.debug("%s marker size: %d -> %s",
                           cfg["name"], size, "64-bit" if is_64 else "32-bit")
                return is_64
            except OSError as ex:
                _log.warning("Failed to stat marker %s: %s", marker, ex)

    # PE header check on detection exe (try alt if primary missing)
    for exe_key in ("detection_exe", "detection_exe_alt"):
        exe_name = cfg.get(exe_key)
        if not exe_name:
            continue
        exe = os.path.join(install_dir, exe_name)
        if os.path.isfile(exe):
            result = is_pe_64bit(exe)
            _log.debug("%s PE check on %s: %s",
                       cfg["name"], exe_name,
                       {True: "64-bit", False: "32-bit", None: "unknown"}.get(result))
            return result is True

    return False


def detect_dlc_status(game_id: str, install_dir: str) -> dict:
    """
    Check DLC marker files for a game. Returns dict keyed by DLC key:
      "ok"      - marker present and correct size
      "missing" - not installed
      "wrong"   - installed but wrong size (needs downgrade)

    Only MW3 has DLC markers. Games without them get an empty dict.
    """
    cfg = GAME_CONFIGS.get(game_id)
    if not cfg:
        return {}
    status = {}
    for key, dlc in cfg.get("dlc", {}).items():
        marker = dlc.get("marker")
        if not marker:
            continue
        target = _merge_dir(game_id, install_dir)
        marker_path = os.path.join(target, marker)
        if not os.path.isfile(marker_path):
            status[key] = "missing"
        else:
            try:
                actual = os.path.getsize(marker_path)
                expected = dlc.get("marker_size")
                if expected and actual == expected:
                    status[key] = "ok"
                else:
                    status[key] = "wrong"
            except OSError:
                status[key] = "missing"
    return status


def detect_installed_dlc(game_id: str, steam_root: str) -> list[str]:
    """
    Read the game's appmanifests to find which DLC packs are installed.
    Steam lists installed DLC depots under InstalledDepots with a
    "dlcappid" field. Returns the GAME_CONFIGS DLC keys found there.
    """
    cfg = GAME_CONFIGS.get(game_id)
    if not cfg:
        return []

    dlc_map = cfg.get("dlc", {})
    if not dlc_map:
        return []

    # Reverse lookup: DLC app id or depot id -> DLC key.
    # Some games put the DLC depot ID in the manifest's dlcappid.
    appid_to_key = {}
    for key, dlc in dlc_map.items():
        dlc_app = dlc.get("app")
        dlc_depot = dlc.get("depot")
        if dlc_app:
            appid_to_key[str(dlc_app)] = key
        if dlc_depot:
            appid_to_key[str(dlc_depot)] = key

    # Base app manifest first. The MP app manifest is checked below.
    from detect_games import _all_library_dirs
    found_keys = set()

    for steamapps_dir in _all_library_dirs(steam_root):
        # DLC depots can sit under the base app or the MP app manifest
        for check_app in {cfg["app_id"]}:
            acf = os.path.join(steamapps_dir, f"appmanifest_{check_app}.acf")
            if not os.path.isfile(acf):
                continue
            try:
                with open(acf, "r", errors="replace") as f:
                    content = f.read()
                for m in re.finditer(r'"dlcappid"\s+"(\d+)"', content):
                    dlc_appid = m.group(1)
                    if dlc_appid in appid_to_key:
                        found_keys.add(appid_to_key[dlc_appid])
            except OSError as ex:
                _log.warning("Failed to read %s: %s", acf, ex)

    # Then the MP app manifest, if it differs from the base app
    mp_apps = {d.get("app") for d in cfg["depots"] if d.get("app")}
    for mp_app in mp_apps:
        if mp_app == cfg["app_id"]:
            continue
        for steamapps_dir in _all_library_dirs(steam_root):
            acf = os.path.join(steamapps_dir, f"appmanifest_{mp_app}.acf")
            if not os.path.isfile(acf):
                continue
            try:
                with open(acf, "r", errors="replace") as f:
                    content = f.read()
                for m in re.finditer(r'"dlcappid"\s+"(\d+)"', content):
                    dlc_appid = m.group(1)
                    if dlc_appid in appid_to_key:
                        found_keys.add(appid_to_key[dlc_appid])
            except OSError as ex:
                _log.warning("Failed to read %s: %s", acf, ex)

    result = sorted(found_keys)
    if result:
        _log.info("%s installed DLC: %s", cfg["name"],
                  ", ".join(dlc_map[k]["name"] for k in result))
    return result


# --- Disk space

def check_free_space_gb(path: str) -> float:
    try:
        st = os.statvfs(path)
        return (st.f_bavail * st.f_frsize) / (1024 ** 3)
    except OSError:
        return 0.0


def has_enough_space(path: str) -> bool:
    return check_free_space_gb(path) >= REQUIRED_FREE_SPACE_GB


# --- Depot staging

def find_depot_staging(steam_root: str, app_id: int) -> str | None:
    """
    Locate the depot staging directory after a download_depot command.
    Steam places downloaded depots under its internal steamapps/content/.
    """
    candidates = [
        os.path.join(steam_root, "ubuntu12_32", "steamapps", "content",
                     f"app_{app_id}"),
        os.path.join(steam_root, "steamapps", "content",
                     f"app_{app_id}"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            _log.debug("Found depot staging at %s", c)
            return c
    return None


# --- Steam console helpers

def open_steam_console():
    from wrapper import launch_steam
    launch_steam("steam://open/console")


def open_steam_install(appid: int):
    from wrapper import launch_steam
    launch_steam(f"steam://install/{appid}")


def copy_to_clipboard(text: str):
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"]):
        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            proc.communicate(input=text.encode("utf-8"), timeout=5)
            if proc.returncode == 0:
                _log.debug("Copied to clipboard via %s", cmd[0])
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    _log.warning("Could not copy to clipboard (no wl-copy or xclip)")


# --- DepotDownloader management

def ensure_depotdownloader(on_progress=None) -> str:
    def prog(msg):
        _log.info(msg)
        if on_progress:
            on_progress(msg)

    if os.path.isfile(DEPOTDOWNLOADER_BIN) and os.access(
        DEPOTDOWNLOADER_BIN, os.X_OK
    ):
        prog("DepotDownloader already present.")
        return DEPOTDOWNLOADER_BIN

    os.makedirs(DEPOTDOWNLOADER_DIR, exist_ok=True)
    zip_path = os.path.join(DEPOTDOWNLOADER_DIR, "dd.zip")

    prog("Fetching DepotDownloader release info...")
    try:
        from detect_hw import is_arm
        _dd_arch = "linux-arm64" if is_arm() else "linux-x64"
        # Its releases carry no GitHub digest yet. download() checks one if they ever do
        dl_url, digest = github_asset("SteamRE/DepotDownloader", f"{_dd_arch}.zip")
    except Exception as ex:
        raise RuntimeError(f"Failed to get DepotDownloader release: {ex}")

    prog("Downloading DepotDownloader...")
    download(dl_url, zip_path, label="DepotDownloader", digest=digest)

    prog("Extracting DepotDownloader...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(DEPOTDOWNLOADER_DIR)
    os.chmod(DEPOTDOWNLOADER_BIN, 0o755)

    if not os.path.isfile(DEPOTDOWNLOADER_BIN):
        raise RuntimeError(
            f"DepotDownloader binary not found after extraction at "
            f"{DEPOTDOWNLOADER_BIN}"
        )

    prog("DepotDownloader ready.")
    return DEPOTDOWNLOADER_BIN


def cleanup_depotdownloader():
    try:
        if os.path.isdir(DEPOTDOWNLOADER_DIR):
            shutil.rmtree(DEPOTDOWNLOADER_DIR, ignore_errors=True)
            _log.info("Removed DepotDownloader and credentials at %s",
                       DEPOTDOWNLOADER_DIR)
    except Exception as ex:
        _log.warning("Failed to clean up DepotDownloader: %s", ex)


# --- QR-based depot download

_USERNAME_RE = re.compile(
    r"Success!.*-username\s+(\S+)\s+-remember-password"
)
_QR_CHARS = frozenset("█▀▄▐▌░▒▓ ")
_DD_ERROR_KEYWORDS = (
    "401", "access denied", "aborting",
    "result: 0", "no manifest request code",
    "unable to download", "not completely downloaded",
    "not available", "could not get depot key",
)


def _is_qr_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    block_count = sum(1 for c in stripped if c in _QR_CHARS)
    return block_count > len(stripped) * 0.5


def qr_text_to_pixmap(qr_text: str, scale: int = 6):
    try:
        from qt import QImage, QPixmap, qRgb

        lines = qr_text.split("\n")
        if not lines:
            return None

        qr_lines = [l for l in lines if "█" in l]
        if not qr_lines:
            return None

        min_col = min(line.find("█") for line in qr_lines)
        max_col = max(
            max(i for i, c in enumerate(line) if c == "█")
            for line in qr_lines
        ) + 1

        height = len(qr_lines)
        char_width = max_col - min_col
        width = (char_width + 1) // 2

        quiet = 4
        img_w = (width + quiet * 2) * scale
        img_h = (height + quiet * 2) * scale

        white = qRgb(255, 255, 255)
        black = qRgb(0, 0, 0)

        img = QImage(img_w, img_h, QImage.Format.Format_RGB32)
        img.fill(white)

        for row_idx, line in enumerate(qr_lines):
            for mod_idx in range(width):
                src_col = min_col + mod_idx * 2
                if src_col < len(line) and line[src_col] == "█":
                    px = (mod_idx + quiet) * scale
                    py = (row_idx + quiet) * scale
                    for dy in range(scale):
                        for dx in range(scale):
                            img.setPixel(px + dx, py + dy, black)

        return QPixmap.fromImage(img)

    except Exception as ex:
        _log.warning("Failed to convert QR text to pixmap: %s", ex)
        return None


def run_depot_download_qr(
    staging_dir: str,
    depot_info: dict,
    on_qr,
    on_auth_success,
    on_progress,
    on_log,
    app_id: int | None = None,
    username: str | None = None,
    max_retries: int = 0,
) -> str | None:
    """
    Run DepotDownloader for a single depot with QR code authentication.

    Uses depot_info["app"] if set, else app_id. With neither, returns None.
    On success returns the Steam username, else None.
    """
    os.makedirs(staging_dir, exist_ok=True)

    effective_app = depot_info.get("app") or app_id
    if not effective_app:
        on_log("No app_id for depot download")
        return None

    attempt = 0
    while True:
        attempt += 1

        cmd = [
            DEPOTDOWNLOADER_BIN,
            "-app", str(effective_app),
            "-depot", str(depot_info["depot"]),
            "-manifest", depot_info["manifest"],
            "-dir", staging_dir,
            "-remember-password",
            "-max-downloads", "25",
        ]

        if username:
            cmd.extend(["-username", username])
        else:
            cmd.append("-qr")

        if attempt > 1:
            on_log(f"Retrying QR login (attempt {attempt})...")
        else:
            on_log(f"Running: DepotDownloader -depot {depot_info['depot']} ...")
        _log.info("DepotDownloader command: %s", " ".join(cmd))

        captured_username = None
        auth_succeeded = False
        error_lines = []

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=DEPOTDOWNLOADER_DIR,
            )

            qr_lines = []
            reading_qr = False

            for line in proc.stdout:
                line = line.rstrip("\n\r")
                _log.debug("DD: %s", line)

                if "QR code has changed" in line or (
                    "Use the Steam Mobile App" in line
                ):
                    reading_qr = True
                    qr_lines = []
                    continue

                if reading_qr:
                    if _is_qr_line(line):
                        qr_lines.append(line)
                        continue
                    elif qr_lines:
                        qr_text = "\n".join(qr_lines)
                        on_qr(qr_text)
                        qr_lines = []
                        reading_qr = False

                m = _USERNAME_RE.search(line)
                if m:
                    captured_username = m.group(1)
                    redact_also(captured_username)
                    auth_succeeded = True
                    on_auth_success(captured_username)
                    on_log("QR authentication successful.")
                    continue

                if "Got depot key" in line:
                    on_progress(f"Downloading depot {depot_info['depot']}...")
                    on_log(line)
                elif "%" in line and ("download" in line.lower() or
                                      "/" in line):
                    on_progress(line.strip())
                else:
                    stripped = line.strip()
                    if stripped and not _is_qr_line(line):
                        error_lines.append(stripped)
                        on_log(line)

            proc.wait()

            if proc.returncode == 0 and (auth_succeeded or username):
                on_log(f"Depot {depot_info['depot']} download complete.")
                return captured_username or username

            if username:
                on_log(f"DepotDownloader exited with code {proc.returncode}")
                for el in error_lines[-10:]:
                    on_log(f"  {el}")
                return None

            real_error = any(
                any(kw in el.lower() for kw in _DD_ERROR_KEYWORDS)
                for el in error_lines
            )

            if real_error or (auth_succeeded and proc.returncode != 0):
                on_log(f"DepotDownloader failed (exit code {proc.returncode}).")
                for el in error_lines[-10:]:
                    on_log(f"  {el}")
                if auth_succeeded:
                    on_log(
                        "Authentication succeeded but the download was "
                        "denied. Your Steam account may not own this game."
                    )
                return None

            if max_retries > 0 and attempt >= max_retries:
                on_log("Max QR login retries reached.")
                return None

            on_log("QR code expired. Generating a new one...")

        except Exception as ex:
            on_log(f"DepotDownloader error: {ex}")
            _log.exception("DepotDownloader failed")
            return None


# --- Merge helpers

def _is_dd_artifact(rel_path: str) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    if parts[0] == ".DepotDownloader":
        return True
    if rel_path.endswith(".manifest"):
        return True
    return False


def _cleanup_dd_artifacts(install_dir: str):
    dd_dir = os.path.join(install_dir, ".DepotDownloader")
    if os.path.isdir(dd_dir):
        try:
            shutil.rmtree(dd_dir, ignore_errors=True)
        except Exception:
            pass
    try:
        for fname in os.listdir(install_dir):
            if fname.endswith(".manifest"):
                os.remove(os.path.join(install_dir, fname))
    except Exception:
        pass


def _merge_tree(src: str, dst: str, prog):
    rel_files = []
    for dirpath, dirnames, filenames in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        for fname in filenames:
            rf = fname if rel == "." else os.path.join(rel, fname)
            if not _is_dd_artifact(rf):
                rel_files.append(rf)

    total = len(rel_files)
    if total == 0:
        return {}

    deleted = 0
    for i, rf in enumerate(rel_files, 1):
        dst_file = os.path.join(dst, rf)
        if os.path.isfile(dst_file):
            try:
                os.remove(dst_file)
                deleted += 1
            except OSError as ex:
                _log.warning("Could not delete %s: %s", dst_file, ex)
        if i % 25 == 0 or i == total:
            prog(f"Removing old files... {i}/{total}")
    _log.info("Deleted %d old files", deleted)

    for i, rf in enumerate(rel_files, 1):
        src_file = os.path.join(src, rf)
        dst_file = os.path.join(dst, rf)
        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
        shutil.move(src_file, dst_file)
        if i % 25 == 0 or i == total:
            prog(f"Moving files into place... {i}/{total}")

    merged = {}
    for rf in rel_files:
        try:
            merged[rf.replace(os.sep, "/")] = os.path.getsize(os.path.join(dst, rf))
        except OSError:
            pass
    return merged


def merge_depots(game_id: str, staging_dir: str, install_dir: str,
                 on_progress=None):
    """
    Merge 32-bit depot files into the game folder.

    MW3 (iw5) merges into a downgrade/ subfolder so the 64-bit Steam
    install stays intact. Other games merge straight into install_dir.

    Handles the manual path (depot_XXXXX subdirs) and the QR path
    (files directly in staging_dir).
    """
    cfg = GAME_CONFIGS.get(game_id)
    if not cfg:
        raise ValueError(f"Unknown game_id: {game_id}")

    def prog(msg):
        _log.info(msg)
        if on_progress:
            on_progress(msg)

    target = _merge_dir(game_id, install_dir)
    os.makedirs(target, exist_ok=True)

    depot_ids = cfg["depot_ids"]
    has_depot_subdirs = any(
        os.path.isdir(os.path.join(staging_dir, f"depot_{d}"))
        for d in depot_ids
    )

    merged = {}
    if has_depot_subdirs:
        for depot_id in depot_ids:
            depot_path = os.path.join(staging_dir, f"depot_{depot_id}")
            if not os.path.isdir(depot_path):
                continue
            prog(f"Merging depot {depot_id} into {cfg['name']} install...")
            merged.update(_merge_tree(depot_path, target, prog))
            prog(f"Depot {depot_id} merged.")
    else:
        prog(f"Merging 32-bit files into {cfg['name']} install...")
        merged.update(_merge_tree(staging_dir, target, prog))
        prog("Merge complete.")

    if merged:
        _write_receipt(game_id, install_dir, merged)

    _cleanup_dd_artifacts(target)

    prog("Cleaning up depot staging files...")
    try:
        shutil.rmtree(staging_dir, ignore_errors=True)
        prog("Staging files removed.")
    except Exception as ex:
        prog(f"Could not remove staging dir: {ex}")

    # Post-merge sanity: MW3 skips this since the game root stays 64-bit
    # by design. Other games check their marker files.
    if game_id != "iw5" and cfg.get("marker_file") and _legacy_downgrade_needed(game_id, install_dir):
        clear_receipt(game_id, install_dir)
        prog(
            f"WARNING: {cfg['name']} still appears to be 64-bit after merge. "
            f"Try verifying game files in Steam, then run DeckOps again."
        )
        return False

    return True


def trim_iw5_duplicates(install_dir: str, on_progress=None) -> int:
    """
    Delete files from the MW3 game root that also exist in downgrade/.
    Saves disk space: Plutonium no longer reads these 64-bit copies.
    Steam Verify restores them if the user wants vanilla SP back.
    Returns the number of files removed.

    Root .exe files are always kept: the Plutonium Steam wrapper replaces
    iw5mp.exe / iw5mp_server.exe in the root, and trim runs before the
    Plutonium install. Deleting them leaves nothing to wrap.
    """
    dg_dir = _merge_dir("iw5", install_dir)
    if not os.path.isdir(dg_dir):
        return 0

    def prog(msg):
        _log.info(msg)
        if on_progress:
            on_progress(msg)

    removed = 0
    for dirpath, _, filenames in os.walk(dg_dir):
        rel = os.path.relpath(dirpath, dg_dir)
        for fname in filenames:
            if fname == RECEIPT_NAME or fname.lower().endswith(".exe"):
                continue
            rf = fname if rel == "." else os.path.join(rel, fname)
            root_file = os.path.join(install_dir, rf)
            if os.path.isfile(root_file):
                try:
                    os.remove(root_file)
                    removed += 1
                except OSError:
                    pass
        if removed and removed % 25 == 0:
            prog(f"Trimming duplicate files... {removed} removed")

    # Clean empty dirs left behind in the game root
    for dirpath, dirnames, filenames in os.walk(install_dir, topdown=False):
        if dirpath == install_dir:
            continue
        if os.path.basename(dirpath) == _IW5_SUBDIR:
            continue
        if not filenames and not dirnames:
            try:
                os.rmdir(dirpath)
            except OSError:
                pass

    prog(f"Trimmed {removed} duplicate files from MW3 install")
    return removed


# Files the removed AlterWare SP mod (sp_mod.py) placed in the MW3 root
_IW5_SP_MOD_FILES = ("iw5-mod.exe", os.path.join("raw", "scripts", "sp", "_cp.gsc"))


def migrate_legacy_iw5(install_dir: str) -> bool:
    """
    Clean up an MW3 install downgraded in place by older DeckOps versions.
    Removes the stale root receipt and SP mod leftovers. Returns True if
    the root iw5sp.exe is still the CEG-less 32-bit depot exe, which only
    a Steam Verify of appid 42680 can fix.
    """
    receipt = os.path.join(install_dir, RECEIPT_NAME)
    try:
        with open(receipt) as f:
            if json.load(f).get("game_id") == "iw5":
                os.remove(receipt)
                _log.info("Removed legacy MW3 root receipt %s", receipt)
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as ex:
        _log.warning("Could not read legacy MW3 receipt %s: %s", receipt, ex)

    for rf in _IW5_SP_MOD_FILES:
        p = os.path.join(install_dir, rf)
        if os.path.isfile(p):
            try:
                os.remove(p)
                _log.info("Removed MW3 SP mod leftover %s", p)
            except OSError as ex:
                _log.warning("Could not remove %s: %s", p, ex)

    return iw5sp_needs_verify(install_dir)


def iw5sp_needs_verify(install_dir: str) -> bool:
    """True if the root iw5sp.exe is the CEG-less 32-bit depot exe left by
    an old in-place downgrade. Read-only. A Steam Verify of 42680 fixes it."""
    exe = os.path.join(install_dir, GAME_CONFIGS["iw5"]["detection_exe"])
    return os.path.isfile(exe) and is_pe_64bit(exe) is False
