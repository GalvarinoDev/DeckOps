import os
import re
import stat
import shutil
import subprocess


def get_proton_path(steam_root):
    """
    Find the best available Proton binary for running Windows executables.

    Preference order:
      1. GE-Proton in ~/.local/share/Steam/compatibilitytools.d/
      2. GE-Proton in steam_root/compatibilitytools.d/
      3. Newest vanilla Proton in steam_root/steamapps/common/

    Uses numeric version sorting so GE-Proton9-28 > GE-Proton9-5,
    and Proton 10 > Proton 9.
    """
    def _version_key(name):
        parts = re.findall(r'\d+', name)
        return tuple(int(p) for p in parts)

    # Check GE-Proton in both possible locations
    ge_search_dirs = [
        os.path.expanduser("~/.local/share/Steam/compatibilitytools.d"),
        os.path.join(steam_root, "compatibilitytools.d"),
    ]
    for ge_dir in ge_search_dirs:
        if not os.path.isdir(ge_dir):
            continue
        ge_dirs = [
            d for d in os.listdir(ge_dir)
            if d.startswith("GE-Proton") and
            os.path.exists(os.path.join(ge_dir, d, "proton"))
        ]
        if ge_dirs:
            ge_dirs.sort(key=_version_key, reverse=True)
            return os.path.join(ge_dir, ge_dirs[0], "proton")

    # Fall back to vanilla Proton
    common = os.path.join(steam_root, "steamapps", "common")
    if not os.path.exists(common):
        return None

    proton_dirs = [
        d for d in os.listdir(common)
        if d.startswith("Proton") and
        os.path.exists(os.path.join(common, d, "proton"))
    ]
    if not proton_dirs:
        return None

    proton_dirs.sort(key=_version_key, reverse=True)
    return os.path.join(common, proton_dirs[0], "proton")


def find_compatdata(steam_root, appid):
    """
    Find the Wine prefix folder for a given Steam appid.
    Returns the path or None if not found.
    """
    compatdata = os.path.join(
        steam_root, "steamapps", "compatdata", str(appid)
    )
    if os.path.exists(compatdata):
        return compatdata
    return None


def get_plutonium_launcher(compatdata_path):
    """
    Return the path to plutonium-launcher-win32.exe inside the given prefix,
    or None if not found.
    """
    launcher = os.path.join(
        compatdata_path,
        "pfx", "drive_c", "users", "steamuser",
        "AppData", "Local", "Plutonium", "bin",
        "plutonium-launcher-win32.exe"
    )
    if os.path.exists(launcher):
        return launcher
    return None


def write_wrapper_script(exe_path, script_content, original_size=None):
    """
    Write a bash wrapper script to replace the original exe.
    Backs up the original first, then writes and chmod's the script.
    Pads to original_size with null bytes so Steam's file validation passes.
    """
    backup_path = exe_path + ".bak"
    if not os.path.exists(backup_path) and os.path.exists(exe_path):
        shutil.copy2(exe_path, backup_path)

    script_bytes = script_content.encode("utf-8")

    if original_size and original_size > len(script_bytes):
        script_bytes += b"\x00" * (original_size - len(script_bytes))

    with open(exe_path, "wb") as f:
        f.write(script_bytes)

    os.chmod(exe_path, os.stat(exe_path).st_mode |
             stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def set_launch_options(steam_root, appid, options):
    """
    Set or append launch options for a Steam game in localconfig.vdf.

    Finds all Steam user accounts under steam_root/userdata and updates
    the LaunchOptions entry for the given appid in each one. If the option
    string is already present it is not duplicated.

    steam_root  — path to the Steam root directory
    appid       — int or str Steam appid
    options     — launch option string to set, e.g. "PROTON_USE_NTSYNC=1 %command%"
    """
    appid = str(appid)
    userdata = os.path.join(steam_root, "userdata")
    if not os.path.exists(userdata):
        return

    for uid in os.listdir(userdata):
        vdf_path = os.path.join(
            userdata, uid, "config", "localconfig.vdf"
        )
        if not os.path.exists(vdf_path):
            continue

        with open(vdf_path, "r", errors="replace") as f:
            content = f.read()

        # Find the apps section for this appid (case-insensitive key match)
        # localconfig.vdf structure: "apps" { "APPID" { "LaunchOptions" "..." } }
        app_pattern = re.compile(
            r'("' + re.escape(appid) + r'"\s*\{)(.*?)(\})',
            re.IGNORECASE | re.DOTALL
        )
        match = app_pattern.search(content)

        if match:
            app_block = match.group(2)
            launch_pattern = re.compile(
                r'("LaunchOptions"\s*")([^"]*?)(")',
                re.IGNORECASE
            )
            launch_match = launch_pattern.search(app_block)

            if launch_match:
                existing = launch_match.group(2)
                # Don't duplicate if already present
                if options in existing:
                    continue
                # Append to existing options
                new_options = (existing.strip() + " " + options).strip()
                new_app_block = launch_pattern.sub(
                    lambda m: m.group(1) + new_options + m.group(3),
                    app_block
                )
            else:
                # No LaunchOptions key yet — insert one
                new_app_block = app_block.rstrip() + \
                    f'\n\t\t\t"LaunchOptions"\t\t"{options}"\n\t\t'

            new_content = (
                content[:match.start(2)] +
                new_app_block +
                content[match.end(2):]
            )
        else:
            # appid block doesn't exist at all — skip rather than corrupt the vdf
            continue

        with open(vdf_path, "w", errors="replace") as f:
            f.write(new_content)


def set_ntsync_launch_options(steam_root, appids):
    """
    Apply PROTON_USE_NTSYNC=1 %command% to all given appids.

    appids — list of int or str appids
    """
    for appid in appids:
        set_launch_options(steam_root, appid, "PROTON_USE_NTSYNC=1 %command%")


def kill_steam():
    """
    Terminate the Steam desktop client without triggering the SteamOS
    session manager (which would switch back to Game Mode).

    Sends SIGTERM directly to the steam and steam.sh processes rather
    than using `steam -shutdown` which goes through the session wrapper.
    """
    import time

    subprocess.run(["pkill", "-TERM", "-f", "steam.sh"], capture_output=True)
    subprocess.run(["pkill", "-TERM", "-x", "steam"],    capture_output=True)

    deadline = time.time() + 15
    while time.time() < deadline:
        r1 = subprocess.run(["pgrep", "-x", "steam"],    capture_output=True)
        r2 = subprocess.run(["pgrep", "-f", "steam.sh"], capture_output=True)
        if r1.returncode != 0 and r2.returncode != 0:
            return
        time.sleep(1)

    # Force kill if still running
    subprocess.run(["pkill", "-9", "-f", "steam.sh"], capture_output=True)
    subprocess.run(["pkill", "-9", "-x", "steam"],    capture_output=True)
    time.sleep(2)


def set_steam_input_enabled(steam_root, appids=None):
    """
    Enable Steam Input for the given appids by setting
    UseSteamControllerConfig to "1" in each user's localconfig.vdf.

    Must be called while Steam is closed.

    steam_root — path to the Steam root directory
    appids     — list of int or str appids; defaults to all DeckOps-managed games
    """
    # All regular Steam appids DeckOps manages
    # (non-Steam shortcuts are handled separately via AllowDesktopConfig in shortcuts.vdf)
    DEFAULT_APPIDS = [
        "7940",    # CoD4
        "10090",   # WaW
        "10180",   # MW2 SP
        "10190",   # MW2 MP
        "42680",   # MW3 SP
        "42690",   # MW3 MP
        "42700",   # BO1
        "42710",   # BO1 MP
        "202970",  # BO2 SP
        "202990",  # BO2 MP
        "212910",  # BO2 ZM
    ]

    if appids is None:
        appids = DEFAULT_APPIDS

    appids = [str(a) for a in appids]
    userdata = os.path.join(steam_root, "userdata")
    if not os.path.exists(userdata):
        return

    for uid in os.listdir(userdata):
        vdf_path = os.path.join(userdata, uid, "config", "localconfig.vdf")
        if not os.path.exists(vdf_path):
            continue

        with open(vdf_path, "r", errors="replace") as f:
            content = f.read()

        modified = False
        for appid in appids:
            app_pattern = re.compile(
                r'("' + re.escape(appid) + r'"\s*\{)(.*?)(\})',
                re.IGNORECASE | re.DOTALL
            )
            match = app_pattern.search(content)
            if not match:
                continue

            app_block = match.group(2)
            si_pattern = re.compile(
                r'("UseSteamControllerConfig"\s*")([^"]*?)(")',
                re.IGNORECASE
            )
            si_match = si_pattern.search(app_block)

            if si_match:
                if si_match.group(2) == "1":
                    continue  # already enabled
                new_block = si_pattern.sub(
                    lambda m: m.group(1) + "1" + m.group(3),
                    app_block
                )
            else:
                new_block = app_block.rstrip() + \
                    '\n\t\t\t"UseSteamControllerConfig"\t\t"1"\n\t\t'

            content = (
                content[:match.start(2)] +
                new_block +
                content[match.end(2):]
            )
            modified = True

        if modified:
            with open(vdf_path, "w", errors="replace") as f:
                f.write(content)


def set_default_launch_option(steam_root, appids_config):
    """
    Set the default launch option for games with multiple launch modes,
    so Steam skips the 'which mode?' dialog.

    appids_config — dict mapping appid to (hash_key, index)
        e.g. {"7940": ("7a722f97", "1"), "10090": ("9aa5e05f", "0")}

    Must be called while Steam is closed.
    """
    userdata = os.path.join(steam_root, "userdata")
    if not os.path.exists(userdata):
        return

    for uid in os.listdir(userdata):
        vdf_path = os.path.join(userdata, uid, "config", "localconfig.vdf")
        if not os.path.exists(vdf_path):
            continue

        with open(vdf_path, "r", errors="replace") as f:
            content = f.read()

        modified = False

        for appid, (hash_key, index) in appids_config.items():
            # Build the DefaultLaunchOption block
            entry = (
                f'\t\t\t\t\t"DefaultLaunchOption"\n'
                f'\t\t\t\t\t{{\n'
                f'\t\t\t\t\t\t"{hash_key}"\t\t"{index}"\n'
                f'\t\t\t\t\t}}\n'
            )

            # Check if appid block exists
            app_pattern = re.compile(
                r'("' + re.escape(appid) + r'"\s*\{)(.*?)(\})',
                re.IGNORECASE | re.DOTALL
            )
            match = app_pattern.search(content)

            if match:
                app_block = match.group(2)
                dlo_pattern = re.compile(
                    r'"DefaultLaunchOption"\s*\{[^}]*\}',
                    re.IGNORECASE | re.DOTALL
                )

                if dlo_pattern.search(app_block):
                    # Replace existing DefaultLaunchOption
                    new_block = dlo_pattern.sub(entry.strip(), app_block)
                else:
                    # Insert DefaultLaunchOption into existing app block
                    new_block = app_block.rstrip() + '\n' + entry + '\t\t\t\t'

                content = (
                    content[:match.start(2)] +
                    new_block +
                    content[match.end(2):]
                )
                modified = True

        if modified:
            with open(vdf_path, "w", errors="replace") as f:
                f.write(content)
