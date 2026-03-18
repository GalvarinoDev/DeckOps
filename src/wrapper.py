import os
import re
import stat
import shutil
import subprocess


def _find_block_end(text, start):
    """
    Brace-depth parser that skips braces inside quoted strings.

    WARNING: Must skip braces inside quoted strings - VDF values like
    bash substitutions (e.g. ${@/iw3sp.exe/iw3sp_mod.exe}) contain
    { and } characters that must NOT be counted as block delimiters.
    Failure to do this will corrupt localconfig.vdf.
    """
    depth = 0
    i = start
    in_quote = False
    while i < len(text):
        c = text[i]
        if c == '"' and (i == 0 or text[i - 1] != '\\'):
            in_quote = not in_quote
        elif not in_quote:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


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
    the LaunchOptions entry for the given appid in each one. Always writes
    to the flat app block — NOT inside any cloud sub-block. Steam's UI reads
    LaunchOptions from the flat block; writing to the cloud sub-block causes
    the option to be invisible in Steam properties even if correctly written.

    steam_root  — path to the Steam root directory
    appid       — int or str Steam appid
    options     — launch option string to set, e.g. "iw4x.exe %command%"
    """
    appid = str(appid)
    # Escape double quotes so the value is valid inside a VDF quoted string
    vdf_options = options.replace('"', '\\"')
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

        # Find the appid block using regex, then brace-depth parse to get its
        # true boundaries.
        #
        # WARNING: Must skip braces inside quoted strings — VDF values like
        # bash substitutions (e.g. ${@/iw3sp.exe/iw3sp_mod.exe}) contain
        # { and } characters that must NOT be counted as block delimiters.
        # Failure to do this will corrupt localconfig.vdf by cutting blocks
        # short and trampling adjacent keys.
        key_pattern = re.compile(
            r'"' + re.escape(appid) + r'"\s*\{',
            re.IGNORECASE
        )
        key_match = key_pattern.search(content)
        if not key_match:
            continue

        app_open  = key_match.end() - 1
        app_close = _find_block_end(content, app_open)
        if app_close == -1:
            continue

        app_inner = content[app_open + 1:app_close]

        # Always write LaunchOptions directly in the flat app block.
        # Steam reads LaunchOptions from here — the cloud sub-block value
        # is NOT shown in Steam properties and should never be written to.
        launch_pattern = re.compile(
            r'("LaunchOptions"\s*")([^"]*?)(")',
            re.IGNORECASE
        )

        # Only match LaunchOptions in the flat block, not inside sub-blocks.
        # Find the first sub-block start so we only search before it.
        subblock_match = re.search(r'"[^"]+"\s*\{', app_inner)
        flat_section = app_inner[:subblock_match.start()] if subblock_match else app_inner

        launch_match = launch_pattern.search(flat_section)

        if launch_match:
            existing = launch_match.group(2)
            if vdf_options in existing:
                continue
            new_options  = (existing.strip() + " " + vdf_options).strip()
            new_app_inner = launch_pattern.sub(
                lambda m: m.group(1) + new_options + m.group(3),
                app_inner,
                count=1
            )
        else:
            # Insert before the first sub-block, or at end if no sub-blocks
            indent_match = re.search(r'\n(\t+)"', flat_section)
            indent = indent_match.group(1) if indent_match else '\t\t\t\t\t\t'
            insert_pos = subblock_match.start() if subblock_match else len(app_inner)
            insert_str = f'{indent}"LaunchOptions"\t\t"{vdf_options}"\n'
            new_app_inner = app_inner[:insert_pos] + insert_str + app_inner[insert_pos:]

        new_content = (
            content[:app_open + 1] +
            new_app_inner +
            content[app_close:]
        )

        with open(vdf_path, "w", errors="replace") as f:
            f.write(new_content)


def kill_steam():
    """
    Terminate the Steam desktop client without triggering the SteamOS
    session manager (which would switch back to Game Mode).

    Targets ubuntu12_32/steam directly — this is the actual main Steam
    process on SteamOS. Killing it triggers a graceful shutdown that writes
    localconfig.vdf cleanly, matching what happens when the user closes
    Steam manually. All child processes (steamwebhelper, srt-logger etc.)
    die automatically when the parent is terminated.
    """
    import time

    # SIGTERM to the main Steam process triggers graceful shutdown + config write
    subprocess.run(["pkill", "-TERM", "-f", "ubuntu12_32/steam"], capture_output=True)

    # Wait for all Steam processes to fully exit
    deadline = time.time() + 20
    while time.time() < deadline:
        r = subprocess.run(
            ["pgrep", "-f", "ubuntu12_32/steam"],
            capture_output=True
        )
        if r.returncode != 0:
            time.sleep(1)  # Brief extra wait for localconfig.vdf write to complete
            return
        time.sleep(1)

    # Force kill if graceful shutdown timed out
    subprocess.run(["pkill", "-9", "-f", "ubuntu12_32/steam"],  capture_output=True)
    subprocess.run(["pkill", "-9", "-f", "steamwebhelper"],      capture_output=True)
    subprocess.run(["pkill", "-9", "-f", "steam.sh"],            capture_output=True)
    time.sleep(3)


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
            key_pattern = re.compile(
                r'"' + re.escape(appid) + r'"\s*\{',
                re.IGNORECASE
            )
            key_match = key_pattern.search(content)
            if not key_match:
                continue

            app_open  = key_match.end() - 1
            app_close = _find_block_end(content, app_open)
            if app_close == -1:
                continue

            app_block = content[app_open + 1:app_close]

            si_pattern = re.compile(
                r'("UseSteamControllerConfig"\s*")([^"]*?)(")',
                re.IGNORECASE
            )

            # Only patch the flat section, not inside any sub-blocks
            subblock_match = re.search(r'"[^"]+"\s*\{', app_block)
            flat_section = app_block[:subblock_match.start()] if subblock_match else app_block
            si_match = si_pattern.search(flat_section)

            if si_match:
                if si_match.group(2) == "1":
                    continue  # already enabled
                new_block = si_pattern.sub(
                    lambda m: m.group(1) + "1" + m.group(3),
                    app_block,
                    count=1,
                )
            else:
                indent_match = re.search(r'\n(\t+)"', flat_section)
                indent = indent_match.group(1) if indent_match else '\t\t\t\t\t\t'
                insert_pos = subblock_match.start() if subblock_match else len(app_block)
                insert_str = f'{indent}"UseSteamControllerConfig"\t\t"1"\n'
                new_block = app_block[:insert_pos] + insert_str + app_block[insert_pos:]

            content = (
                content[:app_open + 1] +
                new_block +
                content[app_close:]
            )
            modified = True

        if modified:
            with open(vdf_path, "w", errors="replace") as f:
                f.write(content)


STEAM_CONFIG = os.path.expanduser("~/.local/share/Steam/config/config.vdf")


def set_compat_tool(appids, version):
    """
    Write CompatToolMapping entries in Steam's config.vdf for each appid.
    Single source of truth — called from both ge_proton.py and shortcut.py
    so the entries are written twice at different points in the install flow,
    making it harder for Steam to override them.

    Logic (in order, no overlap):
      1. If the appid block already exists → replace it in place
      2. Else if CompatToolMapping block exists → insert into it
      3. Else → create the entire CompatToolMapping block from scratch

    appids  — list of int or str appids, e.g. ["10190", "42690"]
    version — GE-Proton version string, e.g. "GE-Proton10-32"
    """
    if not os.path.exists(STEAM_CONFIG):
        raise FileNotFoundError(f"Steam config not found: {STEAM_CONFIG}")

    with open(STEAM_CONFIG, "r", encoding="utf-8") as f:
        data = f.read()

    def _entry(appid_str):
        return (
            f'\t\t\t\t"{appid_str}"\n'
            f'\t\t\t\t{{\n'
            f'\t\t\t\t\t"name"\t\t"{version}"\n'
            f'\t\t\t\t\t"config"\t\t""\n'
            f'\t\t\t\t\t"Priority"\t\t"250"\n'
            f'\t\t\t\t}}\n'
        )

    has_mapping = '"CompatToolMapping"' in data

    if not has_mapping:
        # Create the entire CompatToolMapping block and all entries at once
        block = '\t\t\t"CompatToolMapping"\n\t\t\t{\n'
        for appid in appids:
            block += _entry(str(appid))
        block += '\t\t\t}\n'
        data = re.sub(
            r'("Steam"\s*\{)',
            r'\1\n' + block,
            data,
            count=1,
        )
    else:
        # CompatToolMapping exists — replace or insert each appid entry
        for appid in appids:
            appid_str = str(appid)
            entry = _entry(appid_str)
            # Use re.DOTALL so [^}] correctly spans multiple lines inside the block.
            # The entry block is 4 lines, so [^}]* with DOTALL is required.
            pattern = rf'(\t+"{re.escape(appid_str)}"\n\t+\{{[^}}]*\}})'
            if re.search(pattern, data, re.MULTILINE | re.DOTALL):
                # Replace existing block
                data = re.sub(pattern, entry.rstrip('\n'), data, flags=re.MULTILINE | re.DOTALL)
            else:
                # Insert after CompatToolMapping opening brace
                data = re.sub(
                    r'("CompatToolMapping"\s*\{)',
                    r'\1\n' + entry,
                    data,
                    count=1,
                )

    with open(STEAM_CONFIG, "w", encoding="utf-8") as f:
        f.write(data)


def set_default_launch_option(steam_root, appids_config):
    """
    Set the default launch option for games with multiple launch modes so
    Steam Deck skips the 'which mode?' dialog.

    On SteamOS the picker is controlled by the Deck configurator system, not
    the standard localconfig.vdf apps block. This function targets the correct
    Deck-specific location:

      - Writes DefaultLaunchOption into the "apps" block that sits directly
        after "Deck_ConfiguratorInterstitialApps_AppLauncherInteractionIssues"
      - Sets "Deck_ConfiguratorInterstitialsCheckbox_AppLauncherInteractionIssues"
        to "1" so the Deck configurator treats the choice as confirmed and
        stops showing the picker

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

        # ── Step 1: set the checkbox to "1" so the Deck configurator treats
        # the launch choice as confirmed and stops showing the picker ──────────
        checkbox_pattern = re.compile(
            r'("Deck_ConfiguratorInterstitialsCheckbox_AppLauncherInteractionIssues"\s*")([^"]*?)(")',
            re.IGNORECASE
        )
        if checkbox_pattern.search(content):
            content  = checkbox_pattern.sub(r'\g<1>1\g<3>', content)
            modified = True

        # ── Step 2: write DefaultLaunchOption into the Deck configurator's
        # own "apps" block — this is what the picker actually reads on SteamOS.
        # The block sits immediately after the InterstitialApps key. ──────────
        interstitial_pattern = re.compile(
            r'"Deck_ConfiguratorInterstitialApps_AppLauncherInteractionIssues"\s*"[^"]*"\s*"apps"\s*\{',
            re.IGNORECASE
        )
        interstitial_match = interstitial_pattern.search(content)

        if interstitial_match:
            apps_open  = interstitial_match.end() - 1
            apps_close = _find_block_end(content, apps_open)
            if apps_close != -1:
                apps_block = content[apps_open + 1:apps_close]

                for appid, (hash_key, index) in appids_config.items():
                    entry = (
                        f'\t\t\t\t"{appid}"\n'
                        f'\t\t\t\t{{\n'
                        f'\t\t\t\t\t"DefaultLaunchOption"\n'
                        f'\t\t\t\t\t{{\n'
                        f'\t\t\t\t\t\t"{hash_key}"\t\t"{index}"\n'
                        f'\t\t\t\t\t}}\n'
                        f'\t\t\t\t}}\n'
                    )
                    appid_pattern = re.compile(
                        r'"' + re.escape(appid) + r'"\s*\{',
                        re.IGNORECASE
                    )
                    appid_match = appid_pattern.search(apps_block)
                    if appid_match:
                        appid_open  = appid_match.end() - 1
                        appid_close = _find_block_end(apps_block, appid_open)
                        if appid_close != -1:
                            apps_block = (
                                apps_block[:appid_match.start()] +
                                entry.strip() +
                                apps_block[appid_close + 1:]
                            )
                    else:
                        apps_block = apps_block.rstrip() + '\n' + entry

                content = (
                    content[:apps_open + 1] +
                    apps_block +
                    content[apps_close:]
                )
                modified = True
        else:
            # Deck configurator block doesn't exist yet — build it from scratch
            # and insert before "LaunchOptionTipsShown" if present
            deck_block  = '\t\t\t"Deck_ConfiguratorInterstitialsVersionSeen_AppLauncherInteractionIssues"\t\t"1"\n'
            deck_block += '\t\t\t"Deck_ConfiguratorInterstitialsCheckbox_AppLauncherInteractionIssues"\t\t"1"\n'
            deck_block += '\t\t\t"Deck_ConfiguratorInterstitialApps_AppLauncherInteractionIssues"\t\t"[' + ','.join(appids_config.keys()) + ']"\n'
            deck_block += '\t\t\t"apps"\n\t\t\t{\n'
            for appid, (hash_key, index) in appids_config.items():
                deck_block += (
                    f'\t\t\t\t"{appid}"\n'
                    f'\t\t\t\t{{\n'
                    f'\t\t\t\t\t"DefaultLaunchOption"\n'
                    f'\t\t\t\t\t{{\n'
                    f'\t\t\t\t\t\t"{hash_key}"\t\t"{index}"\n'
                    f'\t\t\t\t\t}}\n'
                    f'\t\t\t\t}}\n'
                )
            deck_block += '\t\t\t}\n'

            tips_pattern = re.compile(r'"LaunchOptionTipsShown"', re.IGNORECASE)
            tips_match   = tips_pattern.search(content)
            if tips_match:
                content  = content[:tips_match.start()] + deck_block + content[tips_match.start():]
                modified = True

        if modified:
            with open(vdf_path, "w", errors="replace") as f:
                f.write(content)
