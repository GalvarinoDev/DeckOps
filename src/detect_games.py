import os
import re
import glob

# Paths where Steam is commonly installed on Linux
STEAM_PATHS = [
    os.path.expanduser("~/.local/share/Steam"),
    os.path.expanduser("~/.steam/steam"),
]

# Known SD card mount point patterns on Steam Deck
SD_CARD_PATTERNS = [
    "/run/media/deck/*/SteamLibrary",
    "/run/media/deck/*",
    "/run/media/mmcblk0p1/SteamLibrary",
    "/run/media/mmcblk0p1",
]

GAMES = {
    "t4sp":  {
        "name": "Call of Duty: World at War",
        "order": 2,
        "appid": "10090",
        "exe": "CoDWaW.exe",
        "protocol": "plutonium://play/t4sp",
        "xact": True
    },
    "t4mp":  {
        "name": "Call of Duty: World at War - Multiplayer",
        "order": 2,
        "appid": "10090",
        "exe": "CoDWaWmp.exe",
        "protocol": "plutonium://play/t4mp",
        "xact": True
    },
    "t5sp":  {
        "name": "Call of Duty: Black Ops",
        "order": 4,
        "appid": "42700",
        "exe": "BlackOps.exe",
        "protocol": "plutonium://play/t5sp",
        "xact": True
    },
    "t5mp":  {
        "name": "Call of Duty: Black Ops - Multiplayer",
        "order": 4,
        "appid": "42710",
        "exe": "BlackOpsMP.exe",
        "protocol": "plutonium://play/t5mp",
        "xact": True
    },
    "t6mp":  {
        "name": "Call of Duty: Black Ops II - Multiplayer",
        "order": 6,
        "appid": "202990",
        "exe": "t6mp.exe",
        "protocol": "plutonium://play/t6mp",
        "xact": False
    },
    "t6zm":  {
        "name": "Call of Duty: Black Ops II - Zombies",
        "order": 6,
        "appid": "212910",
        "exe": "t6zm.exe",
        "protocol": "plutonium://play/t6zm",
        "xact": False
    },
    "t6sp":  {
        "name": "Call of Duty: Black Ops II - Singleplayer",
        "order": 6,
        "appid": "202970",
        "exe": "t6sp.exe",
        "protocol": "steam",
        "xact": False
    },
    "iw5mp": {
        "name": "Call of Duty: Modern Warfare 3 (2011) - Multiplayer",
        "order": 5,
        "appid": "42690",
        "exe": "iw5mp.exe",
        "protocol": "plutonium://play/iw5mp",
        "xact": False
    },
    "iw5sp": {
        "name": "Call of Duty: Modern Warfare 3 (2011) - Singleplayer",
        "order": 5,
        "appid": "42680",
        "exe": "iw5sp.exe",
        "protocol": "steam",
        "xact": False
    },
    "iw4mp": {
        "name": "Call of Duty: Modern Warfare 2 (2009) - Multiplayer",
        "order": 3,
        "appid": "10190",
        "exe": "iw4mp.exe",
        "protocol": "iw4x",
        "xact": False
    },
    "iw4sp": {
        "name": "Call of Duty: Modern Warfare 2 (2009) - Singleplayer",
        "order": 3,
        "appid": "10180",
        "exe": "iw4sp.exe",
        "protocol": "steam",
        "xact": False
    },
    "cod4mp": {
        "name": "Call of Duty 4: Modern Warfare (2007) - Multiplayer",
        "order": 1,
        "appid": "7940",
        "exe": "iw3mp.exe",
        "protocol": "cod4x",
        "xact": False
    },
    "cod4sp": {
        "name": "Call of Duty 4: Modern Warfare (2007) - Singleplayer",
        "order": 1,
        "appid": "7940",
        "exe": "iw3sp.exe",
        "protocol": "iw3sp",
        "xact": False
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
    Kept for backwards compatibility — callers pass this to find_installed_games.
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

            # Parse install dir name from acf
            install_name = None
            with open(acf, "r", errors="replace") as f:
                for line in f:
                    m = re.search(r'"installdir"\s+"([^"]+)"', line)
                    if m:
                        install_name = m.group(1)
                        break

            if not install_name:
                continue

            install_dir = os.path.join(steamapps_dir, "common", install_name)
            exe_path    = os.path.join(install_dir, exe)

            if os.path.exists(install_dir):
                installed[key] = {
                    **meta,
                    "install_dir": install_dir,
                    "exe_path":    exe_path,
                    "exe_size":    get_exe_size(exe_path),
                }
                break

    return installed


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
            print(f"        {game['exe_path']} ({game['exe_size']} bytes)")
