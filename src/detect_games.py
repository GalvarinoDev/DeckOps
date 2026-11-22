import os
import re
import glob
import hashlib
import zipfile
import shutil
import subprocess

# Paths where Steam is commonly installed on Linux
STEAM_PATHS = [
    os.path.expanduser("~/.local/share/Steam"),
    os.path.expanduser("~/.steam/steam"),
]

# SD card and external drive mounts. /run/media/<user>/<label>: the user is
# deck on SteamOS and the login name on Bazzite/CachyOS. /run/media/<label>
# is where older SteamOS mounted the card (mmcblk0p1).
SD_CARD_PATTERNS = [
    "/run/media/*/*/SteamLibrary",
    "/run/media/*/*",
    "/run/media/*/SteamLibrary",
    "/run/media/*",
]

# Maps game key to metadata for each supported title.
#
# Most games use a mod client (cod4x, iw4x, plutonium) and have a protocol
# URL that the wrapper script launches. Games with protocol "steam" are
# vanilla Steam titles with no mod client. They're tracked here so DeckOps
# can detect them, apply display configs, assign controller profiles, and
# show them on the right cards in the UI. They don't get a wrapper script
# or any exe replacement.

GAMES = {
    "cod1sp": {
        "name": "Call of Duty - Singleplayer",
        "order": 0,
        "appid": "2620",
        "exe": "CoDSP.exe",
        "protocol": "steam",
    },
    "cod1mp": {
        "name": "Call of Duty - Multiplayer",
        "order": 0,
        "appid": "2620",
        "exe": "CoDMP.exe",
        "protocol": "steam",
    },
    "coduosp": {
        "name": "Call of Duty: United Offensive - Singleplayer",
        "order": 0,
        "appid": "2640",
        "exe": "CoDUOSP.exe",
        "protocol": "steam",
    },
    "coduomp": {
        "name": "Call of Duty: United Offensive - Multiplayer",
        "order": 0,
        "appid": "2640",
        "exe": "CoDUOMP.exe",
        "protocol": "steam",
    },
    "cod2sp": {
        "name": "Call of Duty 2 - Singleplayer",
        "order": 0,
        "appid": "2630",
        "exe": "CoD2SP_s.exe",
        "protocol": "steam",
    },
    "cod2mp": {
        "name": "Call of Duty 2 - Multiplayer",
        "order": 0,
        "appid": "2630",
        "exe": "CoD2MP_s.exe",
        "protocol": "steam",
    },
    # CoD3 has no PC release or Steam app. CoD3Recomp runs the user's Xbox 360
    # disc. The appid is a placeholder used only for the game card (find_cod3).
    "cod3": {
        "name": "Call of Duty 3",
        "order": 0,
        "appid": "99000003",
        "exe": "CoD3SP_s.exe",
        "protocol": "cod3recomp",
    },
    # Big Red One is console only too. The BRO engine runs the user's Xbox disc
    # natively. Placeholder appid like CoD3 (find_bro).
    "bro": {
        "name": "Call of Duty 2: Big Red One",
        "order": 0,
        "appid": "99000004",
        "exe": "cod_bro",
        "protocol": "bro",
    },
    # Finest Hour too. Finest Hour Remastered runs the user's PAL Xbox disc
    # under Proton (find_fh).
    "codfh": {
        "name": "Call of Duty: Finest Hour",
        "order": 0,
        "appid": "99000005",
        "exe": "CODFH.exe",
        "protocol": "finesthour",
    },
    "t4sp":  {
        "name": "Call of Duty: World at War",
        "order": 2,
        "appid": "10090",
        "exe": "CoDWaW.exe",
        "protocol": "plutonium://play/t4sp",
    },
    "t4mp":  {
        "name": "Call of Duty: World at War - Multiplayer",
        "order": 2,
        "appid": "10090",
        "exe": "CoDWaWmp.exe",
        "protocol": "plutonium://play/t4mp",
    },
    "t5sp":  {
        "name": "Call of Duty: Black Ops",
        "order": 4,
        "appid": "42700",
        "exe": "BlackOps.exe",
        "protocol": "plutonium://play/t5sp",
    },
    "t5mp":  {
        "name": "Call of Duty: Black Ops - Multiplayer",
        "order": 4,
        "appid": "42710",
        "exe": "BlackOpsMP.exe",
        "protocol": "plutonium://play/t5mp",
    },
    "t6mp":  {
        "name": "Call of Duty: Black Ops II - Multiplayer",
        "order": 6,
        "appid": "202990",
        "exe": "t6mp.exe",
        "protocol": "plutonium://play/t6mp",
    },
    "t6zm":  {
        "name": "Call of Duty: Black Ops II - Zombies",
        "order": 6,
        "appid": "212910",
        "exe": "t6zm.exe",
        "protocol": "plutonium://play/t6zm",
    },
    "t6sp":  {
        "name": "Call of Duty: Black Ops II - Singleplayer",
        "order": 6,
        "appid": "202970",
        "exe": "t6sp.exe",
        "protocol": "t6sp_mod",
    },
    "t7": {
        "name": "Call of Duty: Black Ops III",
        "order": 7,
        "appid": "311210",
        "exe": "BlackOps3.exe",
        "protocol": "cleanops",
    },
    # ── DISABLED 2026-09: AlterWare discontinuing Dec 2026 ──
    # "t7x": {
    #     "name": "Call of Duty: Black Ops III - T7x",
    #     "order": 7,
    #     "appid": "311210",
    #     "exe": "BlackOps3.exe",
    #     "protocol": "t7x",
    # },
    "iw6mp": {
        "name": "Call of Duty: Ghosts - Multiplayer",
        "order": 8,
        "appid": "209170",
        "exe": "iw6mp64_ship.exe",
        "protocol": "alterware",
    },
    "iw6sp": {
        "name": "Call of Duty: Ghosts - Singleplayer",
        "order": 8,
        "appid": "209160",
        "exe": "iw6sp64_ship.exe",
        "exe_alt": "iw6mp64_ship.exe",
        "protocol": "alterware",
    },
    "s1mp": {
        "name": "Call of Duty: Advanced Warfare - Multiplayer",
        "order": 9,
        "appid": "209660",
        "exe": "s1_mp64_ship.exe",
        "protocol": "alterware",
    },
    "s1sp": {
        "name": "Call of Duty: Advanced Warfare - Singleplayer",
        "order": 9,
        "appid": "209650",
        "exe": "s1_sp64_ship.exe",
        "protocol": "alterware",
    },
    "iw5mp": {
        "name": "Call of Duty: Modern Warfare 3 (2011) - Multiplayer",
        "order": 5,
        "appid": "42690",
        "exe": "iw5mp.exe",
        "protocol": "plutonium://play/iw5mp",
    },
    "iw5sp": {
        "name": "Call of Duty: Modern Warfare 3 (2011) - Singleplayer",
        "order": 5,
        "appid": "42680",
        "exe": "iw5sp.exe",
        "protocol": "steam",
    },
    "iw5mp_ds": {
        "name": "Call of Duty: Modern Warfare 3 - Dedicated Server",
        "order": 5,
        "appid": "42750",
        "exe": "iw5mp_server.exe",
        "protocol": "plutonium://play/iw5mp",
    },
    "iw4mp": {
        "name": "Call of Duty: Modern Warfare 2 (2009) - Multiplayer",
        "order": 3,
        "appid": "10190",
        "exe": "iw4mp.exe",
        "protocol": "iw4x",
    },
    "iw4sp": {
        "name": "Call of Duty: Modern Warfare 2 (2009) - Singleplayer",
        "order": 3,
        "appid": "10180",
        "exe": "iw4sp.exe",
        "protocol": "steam",
    },
    "cod4mp": {
        "name": "Call of Duty 4: Modern Warfare (2007) - Multiplayer",
        "order": 1,
        "appid": "7940",
        "exe": "iw3mp.exe",
        "protocol": "cod4r",
    },
    "cod4sp": {
        "name": "Call of Duty 4: Modern Warfare (2007) - Singleplayer",
        "order": 1,
        "appid": "7940",
        "exe": "iw3sp.exe",
        "protocol": "iw3sp",
    },
}


def get_exe_size(exe_path):
    if os.path.exists(exe_path):
        return os.path.getsize(exe_path)
    return None


def find_steam_root():
    for path in STEAM_PATHS:
        if os.path.exists(path):
            return path
    return None


def _all_library_dirs(steam_root):
    """
    Returns a deduplicated list of all steamapps directories to search.
    Covers:
      - The main Steam install
      - Every path listed in libraryfolders.vdf
      - SD card mount points via glob (handles any card name/label)
    """
    seen = set()
    dirs = []

    def add(path):
        path = os.path.normpath(path)
        if path not in seen:
            seen.add(path)
            dirs.append(path)

    # 1. Main Steam steamapps
    if steam_root:
        add(os.path.join(steam_root, "steamapps"))

    # 2. libraryfolders.vdf entries
    if steam_root:
        vdf_path = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf_path):
            with open(vdf_path, "r", errors="replace") as f:
                content = f.read()
            for path in re.findall(r'"path"\s+"([^"]+)"', content):
                add(os.path.join(path, "steamapps"))
                # Some SD card libraries use a SteamLibrary subfolder
                add(os.path.join(path, "SteamLibrary", "steamapps"))

    # 3. Brute-force SD card mount points — catches any card regardless of label
    for pattern in SD_CARD_PATTERNS:
        for match in glob.glob(pattern):
            if os.path.isdir(match):
                add(os.path.join(match, "steamapps"))
                add(os.path.join(match, "SteamLibrary", "steamapps"))

    return dirs


def parse_library_folders(steam_root):
    """
    Returns all library root dirs (not steamapps subdirs).
    Kept for backwards compatibility -- callers pass this to find_installed_games.
    """
    dirs = []
    if steam_root:
        dirs.append(steam_root)
    vdf_path = os.path.join(steam_root or "", "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf_path):
        with open(vdf_path, "r", errors="replace") as f:
            content = f.read()
        for path in re.findall(r'"path"\s+"([^"]+)"', content):
            if path not in dirs:
                dirs.append(path)
    return dirs


def find_installed_games(library_folders, steam_root=None):
    """
    Scans all Steam library folders and returns a dict of installed DeckOps-supported games.
    Keys are game keys (e.g. 'iw4mp'), values are game info dicts.
    """
    if steam_root is None and library_folders:
        steam_root = library_folders[0]

    all_steamapps_dirs = _all_library_dirs(steam_root)
    installed = {}

    for key, meta in GAMES.items():
        appid = meta["appid"]
        exe   = meta["exe"]

        for steamapps_dir in all_steamapps_dirs:
            acf = os.path.join(steamapps_dir, f"appmanifest_{appid}.acf")
            if not os.path.exists(acf):
                continue

            # Parse install dir name and state flags from acf
            install_name = None
            state_flags  = None
            with open(acf, "r", errors="replace") as f:
                for line in f:
                    m = re.search(r'"installdir"\s+"([^"]+)"', line)
                    if m:
                        install_name = m.group(1)
                    m = re.search(r'"StateFlags"\s+"(\d+)"', line)
                    if m:
                        state_flags = m.group(1)
                    if install_name and state_flags:
                        break

            if not install_name:
                continue

            # Bit 4 = fully installed. 6 is installed with an update waiting;
            # a first download that hasn't finished doesn't have the bit.
            if not state_flags or not int(state_flags) & 4:
                continue

            install_dir = os.path.join(steamapps_dir, "common", install_name)
            exe_path    = os.path.join(install_dir, exe)

            if not os.path.exists(exe_path) and meta.get("exe_alt"):
                exe_path = os.path.join(install_dir, meta["exe_alt"])

            if os.path.exists(install_dir) and os.path.exists(exe_path):
                installed[key] = {
                    **meta,
                    "install_dir": install_dir,
                    "exe_path":    exe_path,
                    "exe_size":    get_exe_size(exe_path),
                }
                break

    return installed


# --- Own installs
# A game is found by its stock exe, in a folder of any name. Fastfiles aren't
# checked because a copy can lack a mode: a BO2 copy with only Campaign and
# Zombies has no t6mp.exe or mp_*.ff.

# Default scan locations -- case-sensitive on Linux.
OWN_SCAN_PATHS = [
    os.path.expanduser("~/Games"),
    os.path.expanduser("~/games"),
    # /run/media/<user>/<label> (SteamOS user is deck; Bazzite/CachyOS use the
    # login name), plus /run/media/<label> as older SteamOS mounted mmcblk0p1
    "/run/media/*/*/Games",
    "/run/media/*/*/games",
    "/run/media/*/Games",
    "/run/media/*/games",
]

# Lowercase stock exe -> game keys. The MW3 dedicated server has its own Steam
# app and is not an own-install game.
_OWN_EXES = {}
for _k, _m in GAMES.items():
    if _k == "iw5mp_ds":
        continue
    for _e in (_m["exe"], _m.get("exe_alt")):
        if _e:
            _OWN_EXES.setdefault(_e.lower(), []).append(_k)


def _walk_games(root):
    """Walk every folder under root. os.walk skips symlinked folders, so a link loop can't trap it."""
    skip = {"__pycache__", "DeckOps-T7X"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in skip]
        yield dirpath, dirnames, filenames


def find_own_installed(extra_paths=None, on_progress=None):
    """
    Scan ~/Games, SD card Games folders and extra_paths (the Choose Folder
    picks) for stock game exes. Exe names match in any case. The folder that
    holds the exe becomes install_dir.

    Returns the same dict as find_installed_games() plus "source": "own".
    """
    prog = on_progress or (lambda *a: None)

    scan_dirs = []
    seen = set()
    for pattern in OWN_SCAN_PATHS:
        for path in glob.glob(pattern):
            path = os.path.normpath(path)
            # realpath: SteamOS also links /run/media/<label> to /run/media/deck/<label>
            real = os.path.realpath(path)
            if real not in seen and os.path.isdir(path):
                seen.add(real)
                scan_dirs.append(path)
    if extra_paths:
        for path in extra_paths:
            path = os.path.normpath(path)
            real = os.path.realpath(path)
            if real not in seen and os.path.isdir(path):
                seen.add(real)
                scan_dirs.append(path)

    if not scan_dirs:
        prog("No game folders found to scan.")
        return {}

    found = {}
    uo_cod1 = {}
    for scan_dir in scan_dirs:
        prog(f"Scanning {scan_dir}...")
        for dirpath, dirnames, filenames in _walk_games(scan_dir):
            exes = {f.lower(): f for f in filenames if f.lower() in _OWN_EXES}
            if not exes:
                continue
            # Game root found; skip its subfolders
            dirnames.clear()
            # A UO folder also ships CoD1's CoDSP/CoDMP. A separate CoD1 folder wins,
            # else CoD1 runs from the UO folder (Deluxe Edition is one folder)
            is_uo = "coduosp.exe" in exes or "coduomp.exe" in exes
            for low, fname in exes.items():
                for key in _OWN_EXES[low]:
                    if key in found:
                        continue
                    meta = GAMES[key]
                    # Ghosts SP falls back to the MP exe; use its own when present
                    exe_path = os.path.join(dirpath, exes.get(meta["exe"].lower(), fname))
                    hit = {
                        **meta,
                        "install_dir": dirpath,
                        "exe_path":    exe_path,
                        "exe_size":    get_exe_size(exe_path),
                        "source":      "own",
                    }
                    if is_uo and key in ("cod1sp", "cod1mp"):
                        uo_cod1.setdefault(key, hit)
                        continue
                    found[key] = hit
                    prog(f"  found {key}: {meta['name']} at {dirpath}")

    for key, hit in uo_cod1.items():
        if key not in found:
            found[key] = hit
            prog(f"  found {key}: {hit['name']} at {hit['install_dir']} (UO folder)")

    cod3 = find_cod3(scan_dirs)
    if cod3:
        found["cod3"] = {**found.get("cod3", {}), **cod3}
        prog(f"  found cod3: Call of Duty 3 at {cod3['install_dir']}")
    bro = find_bro(scan_dirs)
    if bro:
        found["bro"] = {**found.get("bro", {}), **bro}
        prog(f"  found bro: Call of Duty 2: Big Red One at {bro['install_dir']}")
    fh = find_fh(scan_dirs)
    if fh:
        found["codfh"] = {**found.get("codfh", {}), **fh}
        prog(f"  found codfh: Call of Duty: Finest Hour at {fh['install_dir']}")

    if not found:
        prog("No supported games found.")
    else:
        prog(f"Found {len(found)} game(s).")

    return found


def find_cod3(scan_dirs):
    """Find Call of Duty 3 in a "cod3" folder (any case), either a scan dir
    itself or a folder in one. It needs the disc image (.iso, or a .zip, .7z or .rar with
    one inside), an installed game/ folder, or the disc's files copied in as
    they are. CoD3Recomp installs next to them."""
    for scan_dir in scan_dirs:
        dirs = [scan_dir] if os.path.basename(scan_dir).lower() == "cod3" else [
            os.path.join(scan_dir, d) for d in sorted(os.listdir(scan_dir))
            if d.lower() == "cod3" and os.path.isdir(os.path.join(scan_dir, d))]
        for d in dirs:
            files = sorted(os.listdir(d))
            disc = next((os.path.join(d, f) for f in files if f.lower().endswith(".iso")), None) \
                or next((os.path.join(d, f) for f in files if f.lower().endswith(DISC_ARCHIVES)), None)
            installed = any(os.path.isfile(os.path.join(d, sub, "default.xex"))
                            and os.path.isdir(os.path.join(d, sub, "sp")) for sub in ("game", ""))
            if disc or installed:
                exe = next((f for f in files if f.lower() == "cod3sp_s.exe"), "CoD3SP_s.exe")
                return {**GAMES["cod3"], "install_dir": d, "exe_path": os.path.join(d, exe),
                        "exe_size": get_exe_size(os.path.join(d, exe)), "disc": disc, "source": "own"}
    loose = find_loose_disc(scan_dirs, "cod3")
    if loose:
        d, disc = loose
        exe = os.path.join(d, "CoD3SP_s.exe")
        return {**GAMES["cod3"], "install_dir": d, "exe_path": exe, "exe_size": get_exe_size(exe),
                "disc": disc, "loose": True, "source": "own"}
    return None


def _disc_game_dir(scan_dirs, key, exe_rel, installed):
    """Game folder for a console game DeckOps installs from the user's disc: a
    folder named DISC_FOLDERS[key] (any case), either a scan dir itself or a
    folder in one. It needs a disc image (.iso, or a .zip, .7z or .rar with one inside) or
    installed(folder). Otherwise a loose disc in a scan dir."""
    name = DISC_FOLDERS[key]
    for scan_dir in scan_dirs:
        try:
            dirs = [scan_dir] if os.path.basename(scan_dir).lower() == name else [
                os.path.join(scan_dir, d) for d in sorted(os.listdir(scan_dir))
                if d.lower() == name and os.path.isdir(os.path.join(scan_dir, d))]
        except OSError:
            continue
        for d in dirs:
            files = sorted(os.listdir(d))
            disc = next((os.path.join(d, f) for f in files if f.lower().endswith(".iso")), None) \
                or next((os.path.join(d, f) for f in files if f.lower().endswith(DISC_ARCHIVES)), None)
            if disc or installed(d):
                exe = os.path.join(d, exe_rel)
                return {**GAMES[key], "install_dir": d, "exe_path": exe,
                        "exe_size": get_exe_size(exe), "disc": disc, "source": "own"}
    loose = find_loose_disc(scan_dirs, key)
    if loose:
        d, disc = loose
        exe = os.path.join(d, exe_rel)
        return {**GAMES[key], "install_dir": d, "exe_path": exe, "exe_size": get_exe_size(exe),
                "disc": disc, "loose": True, "source": "own"}
    return None


def find_bro(scan_dirs):
    """Big Red One: the Xbox disc, or the extracted files in assets/. The engine installs next to them."""
    return _disc_game_dir(scan_dirs, "bro", GAMES["bro"]["exe"],
                          lambda d: os.path.isfile(os.path.join(d, "assets", "default.xbe")))


def find_fh(scan_dirs):
    """Finest Hour: the PAL Xbox disc, its files copied in as they are (default.xbe),
    or the installed port in game/."""
    exe = os.path.join("game", GAMES["codfh"]["exe"])
    return _disc_game_dir(scan_dirs, "codfh", exe,
                          lambda d: os.path.isfile(os.path.join(d, "default.xbe"))
                          or os.path.isfile(os.path.join(d, exe)))


# Disc images left loose in a scan dir. The scan only reads them. The install
# moves them into the game's folder (move_disc_in).
COD3_XEX_SIZE = 7254016  # the default.xex CoD3Recomp was recompiled from
BRO_XBE_SHA1 = {"bb33fd9d2fd2d667df9e669dcb6b47a347bdccbb",  # Standard (World)
                "5a84a08720483e93add552cfdbf7fbf924658553"}  # Collector's Edition
FH_XBE_SHA1 = "938a7b1e17928de49cb3c5834d61abcd3d9081c8"  # PAL, version 3, the only one the port runs
DISC_FOLDERS = {"cod3": "cod3", "bro": "bro", "codfh": "finesthour"}


DISC_ARCHIVES = (".zip", ".7z", ".rar")


def _archive_list(path):
    """Every name inside a .zip, .7z or .rar. A .7z or .rar is listed with 7z
    (SteamOS ships it), else bsdtar, else unrar (some 7z builds have no RAR codec).
    Empty if none can read it."""
    if path.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(path) as zf:
                return zf.namelist()
        except (OSError, zipfile.BadZipFile):
            return []
    for cmd in (["7z", "l", "-ba", "-slt", path], ["bsdtar", "-tf", path], ["unrar", "lb", path]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0:
            if cmd[0] == "7z":
                return [l[7:] for l in r.stdout.splitlines() if l.startswith("Path = ")]
            return r.stdout.splitlines()
    return []


def archive_isos(path):
    """Names of the .iso files inside an archive, without unpacking it. With no
    .iso, the .zip files inside instead: archive.org often wraps a zipped disc in a .rar."""
    names = _archive_list(path)
    return [n for n in names if n.lower().endswith(".iso")] or \
        [n for n in names if n.lower().endswith(".zip")]


def _extract(archive, member, dest):
    if archive.lower().endswith(".zip"):
        with zipfile.ZipFile(archive) as zf, zf.open(member) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out, 8 << 20)
        return
    for cmd in (["7z", "e", "-so", archive, member], ["bsdtar", "-xOf", archive, member],
                ["unrar", "p", "-inul", archive, member]):
        try:
            with open(dest, "wb") as out:
                r = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE, timeout=3600)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0:
            return
    if os.path.exists(dest):
        os.remove(dest)
    raise RuntimeError(f"Could not unpack {os.path.basename(archive)}. Unpack the .iso yourself.")


def unpack_iso(archive, dest, log):
    """Unpack the first .iso in an archive to dest and return dest. A .zip inside
    the archive is unpacked first, then its .iso, and the inner .zip is deleted."""
    names = archive_isos(archive)
    if not names:
        raise RuntimeError(f"No .iso inside {os.path.basename(archive)}")
    log(f"Unpacking {os.path.basename(names[0])} (several GB, this takes a few minutes)...")
    if not names[0].lower().endswith(".zip"):
        _extract(archive, names[0], dest)
        return dest
    inner = dest + ".zip"
    try:
        _extract(archive, names[0], inner)
        if not any(n.lower().endswith(".iso") for n in archive_isos(inner)):
            raise RuntimeError(f"No .iso inside {os.path.basename(names[0])}")
        return unpack_iso(inner, dest, log)
    finally:
        if os.path.exists(inner):
            os.remove(inner)


def disc_game(path):
    """"cod3", "bro", "codfh" or None. An .iso is judged by its main file, an archive
    by the name of the .iso (or .zip) inside (unpacking it to look would take minutes)."""
    low = path.lower()
    if low.endswith(DISC_ARCHIVES):
        names = [re.sub(r"[^a-z0-9]", "", os.path.basename(n).lower()) for n in archive_isos(path)]
        for n in names:
            if "bigredone" in n:
                return "bro"
            if "finesthour" in n:
                return "codfh"
            if "callofduty3" in n or "cod3" in n:
                return "cod3"
        return None
    if not low.endswith(".iso"):
        return None
    from xdvdfs import root_files
    files = root_files(path)
    if files.get("default.xex", (0, 0))[1] == COD3_XEX_SIZE:
        return "cod3"
    xbe = files.get("default.xbe")
    if xbe and xbe[1] < 64 << 20:
        try:
            with open(path, "rb") as f:
                f.seek(xbe[0])
                sha = hashlib.sha1(f.read(xbe[1])).hexdigest()
            if sha in BRO_XBE_SHA1:
                return "bro"
            if sha == FH_XBE_SHA1:
                return "codfh"
        except OSError:
            pass
    return None


def find_loose_disc(scan_dirs, key):
    """(game folder, loose .iso or archive) for key, from the top level of a scan dir.
    The game folder may not exist yet."""
    name = DISC_FOLDERS[key]
    for scan_dir in scan_dirs:
        if os.path.basename(scan_dir).lower() == name:
            continue
        try:
            entries = sorted(os.listdir(scan_dir))
        except OSError:
            continue
        folder = next((os.path.join(scan_dir, e) for e in entries
                       if e.lower() == name and os.path.isdir(os.path.join(scan_dir, e))),
                      os.path.join(scan_dir, name))
        # An .iso before an archive: it installs faster and needs no unpacking
        for e in sorted(entries, key=lambda e: not e.lower().endswith(".iso")):
            p = os.path.join(scan_dir, e)
            if e.lower().endswith((".iso",) + DISC_ARCHIVES) and os.path.isfile(p) and disc_game(p) == key:
                return folder, p
    return None


def move_disc_in(disc, folder, log):
    """Move a loose disc image into its game folder and return the new path.
    It is a rename on the same drive: instant, and nothing is copied or deleted."""
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, os.path.basename(disc))
    # os.rename would replace an existing file without asking
    if os.path.exists(dest):
        raise RuntimeError(f"{dest} already exists. Move {os.path.basename(disc)} yourself.")
    os.rename(disc, dest)
    log(f"Moved {os.path.basename(disc)} into {folder}")
    return dest


def find_all_games(steam_root=None):
    """Detect all installed games from both Steam and non-Steam sources.

    Steam games take priority when a key exists in both.
    Each entry is tagged with source="steam" or source="own".
    """
    if steam_root is None:
        steam_root = find_steam_root()
    libs = parse_library_folders(steam_root)
    steam = find_installed_games(libs, steam_root)
    own = find_own_installed()
    merged = {}
    for k, v in own.items():
        merged[k] = v
    for k, v in steam.items():
        merged[k] = {**v, "source": "steam"}
    return merged


if __name__ == "__main__":
    steam_root = find_steam_root()
    if not steam_root:
        print("Steam not found.")
    else:
        print(f"Steam found at: {steam_root}")
        libraries = parse_library_folders(steam_root)
        print(f"Libraries found:")
        for lib in libraries:
            print(f"  {lib}")
        installed = find_installed_games(libraries)
        print(f"\nInstalled games ({len(installed)}):")
        for key, game in installed.items():
            print(f"  [{key}] {game['name']}")
            print(f"        {game['install_dir']}")

    print(f"\nOwn games scan:")
    own = find_own_installed(on_progress=print)
    for key, game in own.items():
        print(f"  [{key}] {game['name']}")
        print(f"        {game['install_dir']}")
