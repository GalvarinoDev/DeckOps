import os
import re

# Paths where Steam is commonly installed on Linux
STEAM_PATHS = [
    os.path.expanduser("~/.local/share/Steam"),
    os.path.expanduser("~/.steam/steam"),
]

# Each entry represents a supported game mode
# xact flag indicates whether the Windows audio component needs installing
GAMES = {
    "t4sp":  {
        "name": "Call of Duty: World at War",
        "order": 2,
        "appid": "10090",
        "exe": "CoDWaW.exe",
        "protocol": "plutonium://play/t4sp",
        "xact": True   # WAW needs xact for audio to work correctly
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
        "xact": True   # BO1 also needs xact
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
    "iw5mp": {
        "name": "Call of Duty: Modern Warfare 3 (2011) - Multiplayer",
        "order": 5,
        "appid": "42690",
        "exe": "iw5mp.exe",
        "protocol": "plutonium://play/iw5mp",
        "xact": False
    },
    "iw4mp": {
        "name": "Call of Duty: Modern Warfare 2 (2009) - Multiplayer",
        "order": 3,
        "appid": "10190",
        "exe": "iw4mp.exe",
        "protocol": "iw4x",   # MW2 uses iw4x instead of Plutonium
        "xact": False
    },
    "cod4mp": {
        "name": "Call of Duty 4: Modern Warfare (2007) - Multiplayer",
        "order": 1,
        "appid": "7940",
        "exe": "iw3mp.exe",
        "protocol": "cod4x",  # COD4 uses cod4x
        "xact": False
    },
}

def get_exe_size(exe_path):
    # Grab the real size from the user's actual installation
    # This is better than hardcoding since versions can vary
    if os.path.exists(exe_path):
        return os.path.getsize(exe_path)
    return None

def find_steam_root():
    # Check each known Steam path until we find one that exists
    for path in STEAM_PATHS:
        if os.path.exists(path):
            return path
    return None

def parse_library_folders(steam_root):
    # Steam keeps track of all library locations in this file
    vdf_path = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    libraries = []
    if not os.path.exists(vdf_path):
        return libraries
    with open(vdf_path, "r") as f:
        content = f.read()
    # Pull out all the path entries
    paths = re.findall(r'"path"\s+"([^"]+)"', content)
    for path in paths:
        libraries.append(path)
    return libraries

def find_installed_games(libraries):
    installed = {}
    for lib in libraries:
        steamapps = os.path.join(lib, "steamapps")
        if not os.path.exists(steamapps):
            continue
        for key, game in GAMES.items():
            # Each installed Steam game has a manifest file we can check
            manifest = os.path.join(steamapps, f"appmanifest_{game['appid']}.acf")
            if os.path.exists(manifest):
                with open(manifest, "r") as f:
                    content = f.read()
                # The manifest tells us the actual folder name Steam used
                match = re.search(r'"installdir"\s+"([^"]+)"', content)
                if match:
                    install_dir = os.path.join(steamapps, "common", match.group(1))
                    exe_path = os.path.join(install_dir, game["exe"])
                    exe_size = get_exe_size(exe_path)
                    installed[key] = {
                        **game,
                        "library": lib,
                        "steamapps": steamapps,
                        "install_dir": install_dir,
                        "exe_path": exe_path,
                        "exe_size": exe_size,
                    }
    return installed

if __name__ == "__main__":
    steam_root = find_steam_root()
    if not steam_root:
        print("Steam not found!")
    else:
        print(f"Steam found at: {steam_root}")
        libraries = parse_library_folders(steam_root)
        print(f"Libraries found: {libraries}")
        installed = find_installed_games(libraries)
        for key, game in installed.items():
            print(f"{game['name']}: {game['exe_path']} ({game['exe_size']} bytes)")
