import os
import json
import re
import shutil
import subprocess

from identity import LEDGER_PATH
from log import get_logger
from steam_common import backup_file as _backup_file, newest_proton_dir, write_json as _write_json

_log = get_logger(__name__)

# --- VDF edit ledger
# Records every VDF edit DeckOps makes, so the uninstaller can undo each one
# instead of regex-sweeping whole files.


def _read_ledger() -> dict:
    """Read the VDF edit ledger. Returns an empty dict if it is missing or corrupt."""
    if not os.path.exists(LEDGER_PATH):
        return {}
    try:
        with open(LEDGER_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        _log.debug("VDF ledger read failed, starting fresh", exc_info=True)
        return {}


def _write_ledger(data: dict):
    """Write the VDF edit ledger. A failure is logged and does not stop the caller."""
    try:
        os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
        _write_json(LEDGER_PATH, data)
    except OSError:
        _log.debug("VDF ledger write failed", exc_info=True)


def _record_localconfig(uid: str, appid: str, key: str, value: str):
    """Record a localconfig.vdf edit in the ledger."""
    ledger = _read_ledger()
    lc = ledger.setdefault("localconfig", {})
    uid_block = lc.setdefault(uid, {})
    app_block = uid_block.setdefault(appid, {})
    app_block[key] = value
    _write_ledger(ledger)


def _record_config_vdf(appid: str, key: str, value: str):
    """Record a config.vdf edit in the ledger."""
    ledger = _read_ledger()
    cv = ledger.setdefault("config_vdf", {})
    section = cv.setdefault(key, {})
    section[appid] = value
    _write_ledger(ledger)


def _remove_config_vdf(appid: str, key: str):
    """Remove a config.vdf entry from the ledger (used by the clear functions)."""
    ledger = _read_ledger()
    cv = ledger.get("config_vdf", {})
    section = cv.get(key, {})
    section.pop(appid, None)
    if not section:
        cv.pop(key, None)
    _write_ledger(ledger)


def _record_configset(configset_filename: str, key: str, template_name: str):
    """Record a configset VDF edit in the ledger."""
    ledger = _read_ledger()
    cs = ledger.setdefault("configsets", {})
    file_block = cs.setdefault(configset_filename, {})
    file_block[key] = template_name
    _write_ledger(ledger)



def _find_block_end(text, start):
    """
    Return the offset of the brace that closes the block opened at start,
    or -1. Braces inside quoted strings are skipped.

    WARNING: the quote check is required. VDF values such as bash
    substitutions (e.g. ${@/iw3sp.exe/iw3sp_mod.exe}) contain { and }
    that must NOT count as block delimiters, or localconfig.vdf gets
    corrupted.
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


def _validate_vdf(path: str) -> bool:
    """
    Read a VDF file back after writing and check that its braces balance.

    Walks the whole file with the same quote-aware rule as _find_block_end.
    Returns True if every { has a matching }, False if not.

    On failure it logs the error and restores the .bak copy if there is
    one, so Steam never reads a corrupt file.
    """
    try:
        with open(path, "r", errors="replace") as f:
            data = f.read()
    except OSError:
        _log.error("VDF validation: cannot read %s", path)
        return False

    depth = 0
    in_quote = False
    for i, c in enumerate(data):
        if c == '"' and (i == 0 or data[i - 1] != '\\'):
            in_quote = not in_quote
        elif not in_quote:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth < 0:
                    break

    if depth != 0:
        _log.error(
            "VDF validation FAILED for %s (brace depth %d) — restoring backup",
            path, depth,
        )
        bak = path + ".bak"
        if os.path.exists(bak):
            try:
                shutil.copy2(bak, path)
                _log.info("VDF restored from %s", bak)
            except OSError:
                _log.error("VDF restore failed for %s", path, exc_info=True)
        return False

    return True


def _write_and_validate_vdf(path: str, data: str, encoding: str = "utf-8",
                            errors: str | None = None) -> bool:
    """
    Back up path, write data to it, then check the brace balance.

    If the check fails, the backup is restored. Returns True if the write
    is clean.

    encoding, errors: passed to open(). Use errors="replace" for
    localconfig.vdf, which can contain non-UTF-8 bytes.
    """
    _backup_file(path)
    open_kwargs = {"encoding": encoding}
    if errors:
        open_kwargs = {"errors": errors}
    with open(path, "w", **open_kwargs) as f:
        f.write(data)
    if not _validate_vdf(path):
        _log.error("VDF corruption detected in %s after write", path)
        return False
    return True


# --- localconfig.vdf helpers

_INTERSTITIAL_RE = re.compile(
    r'"Deck_ConfiguratorInterstitialApps_AppLauncherInteractionIssues"\s*"[^"]*"\s*"apps"\s*\{',
    re.IGNORECASE
)


def _localconfigs(steam_root):
    """Yield (uid, vdf_path, content) for every user's localconfig.vdf."""
    userdata = os.path.join(steam_root, "userdata")
    if not os.path.exists(userdata):
        return
    for uid in os.listdir(userdata):
        vdf_path = os.path.join(userdata, uid, "config", "localconfig.vdf")
        if not os.path.exists(vdf_path):
            continue
        with open(vdf_path, "r", errors="replace") as f:
            content = f.read()
        yield uid, vdf_path, content


def _app_block(content, appid):
    """
    Return (open, close) brace offsets of the first "<appid>" { block, or None.

    WARNING: braces inside quoted strings must be skipped. VDF values such
    as bash substitutions (e.g. ${@/iw3sp.exe/iw3sp_mod.exe}) contain { and }
    that must NOT count as block delimiters. Counting them cuts blocks short
    and overwrites the keys next to them in localconfig.vdf.
    _find_block_end handles this.
    """
    m = re.search(r'"' + re.escape(appid) + r'"\s*\{', content, re.IGNORECASE)
    if not m:
        return None
    close = _find_block_end(content, m.end() - 1)
    return None if close == -1 else (m.end() - 1, close)


def _split_flat(inner):
    """
    Split an app block body at its first sub-block: (flat keys, sub-blocks).
    Only the flat part is edited. Keys with the same name inside cloud
    sub-blocks are never touched.
    """
    sub = re.search(r'"[^"]+"\s*\{', inner)
    return (inner[:sub.start()], inner[sub.start():]) if sub else (inner, "")


def _add_flat_key(flat, line):
    """Add a key line before the indent of the next line (the closing brace or a
    sub-block), so that line keeps its own indent."""
    body = flat.rstrip(" \t")
    return body + line + flat[len(body):]


def _value_pattern(key):
    """Match "key" "value" with groups (prefix, value, closing quote)."""
    return re.compile(r'("' + key + r'"\s*")((?:[^"\\]|\\.)*)(")', re.IGNORECASE)


def _dlo_entry(appid, hash_key, index):
    return (
        f'\t\t\t\t"{appid}"\n'
        f'\t\t\t\t{{\n'
        f'\t\t\t\t\t"DefaultLaunchOption"\n'
        f'\t\t\t\t\t{{\n'
        f'\t\t\t\t\t\t"{hash_key}"\t\t"{index}"\n'
        f'\t\t\t\t\t}}\n'
        f'\t\t\t\t}}\n'
    )


def get_proton_path(steam_root):
    """
    Find the best Proton binary for running Windows executables.

    Preference order:
      1. The pinned GE-Proton version (ge_proton_version in deckops.json)
      2. GE-Proton in ~/.local/share/Steam/compatibilitytools.d/
      3. GE-Proton in steam_root/compatibilitytools.d/
      4. Newest vanilla Proton in steam_root/steamapps/common/

    The pin keeps DeckOps on the GE-Proton version it installed, even when
    ProtonUp-Qt or another tool has put newer (maybe unstable) versions
    on disk.

    Versions sort by number, so GE-Proton9-28 > GE-Proton9-5 and
    Proton 10 > Proton 9.
    """
    ge_search_dirs = [
        os.path.expanduser("~/.local/share/Steam/compatibilitytools.d"),
    ]
    if steam_root:
        ge_search_dirs.append(os.path.join(steam_root, "compatibilitytools.d"))

    # Try the pinned version first
    try:
        import config as _cfg
        pinned = _cfg.get_ge_proton_version()
    except Exception:
        pinned = None

    if pinned:
        for ge_dir in ge_search_dirs:
            candidate = os.path.join(ge_dir, pinned, "proton")
            if os.path.exists(candidate):
                return candidate

    # Pinned version not found. Use the newest GE-Proton on disk.
    for ge_dir in ge_search_dirs:
        name = newest_proton_dir(ge_dir, "GE-Proton")
        if name:
            return os.path.join(ge_dir, name, "proton")

    # Fall back to vanilla Proton
    if not steam_root:
        return None
    common = os.path.join(steam_root, "steamapps", "common")
    name = newest_proton_dir(common, "Proton")
    return os.path.join(common, name, "proton") if name else None


def find_compatdata(steam_root, appid, game_install_dir=None):
    """
    Find the Wine prefix folder for a given Steam appid.

    Searches every Steam library folder (internal and SD card), so the
    right prefix is found wherever the game is installed.

    With game_install_dir, the prefix in the game's own library folder wins.
    When both the internal drive and the SD card have compatdata for the
    same appid, the internal one would otherwise always come back first,
    because _all_library_dirs lists it first.

    Returns the path, or None if there is none.
    """
    from detect_games import _all_library_dirs

    all_dirs = _all_library_dirs(steam_root)

    # If we know where the game is installed, prefer the prefix in the same
    # library folder, so SD card games use the SD card prefix.
    if game_install_dir:
        game_norm = os.path.normpath(game_install_dir)
        for steamapps_dir in all_dirs:
            sa_norm = os.path.normpath(steamapps_dir)
            # Check if the game's install_dir lives under this steamapps/
            # e.g. /run/media/deck/SD1/steamapps/common/Call of Duty 4
            #       starts with /run/media/deck/SD1/steamapps
            if game_norm.startswith(sa_norm + os.sep) or game_norm.startswith(sa_norm + "/"):
                candidate = os.path.join(steamapps_dir, "compatdata", str(appid))
                if os.path.isdir(candidate):
                    return candidate
                # The game is here but has no compatdata yet. Fall through
                # to the general scan.
                break

    for steamapps_dir in all_dirs:
        candidate = os.path.join(steamapps_dir, "compatdata", str(appid))
        if os.path.isdir(candidate):
            return candidate

    # Fallback to the default location (may not exist yet)
    default = os.path.join(steam_root, "steamapps", "compatdata", str(appid))
    if os.path.exists(default):
        return default
    return None


def set_launch_options(steam_root, appid, options):
    """
    Set or append launch options for a Steam game in localconfig.vdf.

    Updates the LaunchOptions entry for the appid in every Steam account
    under steam_root/userdata. Always writes to the flat app block, NOT
    inside a cloud sub-block. Steam's UI reads LaunchOptions from the flat
    block. A value in the cloud sub-block never shows up in Steam
    properties, even when it is written correctly.

    steam_root: path to the Steam root directory
    appid:      Steam appid, int or str
    options:    launch option string to set, e.g. "iw4x.exe %command%"
    """
    appid = str(appid)
    # Escape double quotes so the value is valid inside a VDF quoted string
    vdf_options = options.replace('"', '\\"')
    launch_pattern = _value_pattern("LaunchOptions")

    for uid, vdf_path, content in _localconfigs(steam_root):
        # Brace parsing must be quote-aware. See the WARNING in _app_block.
        block = _app_block(content, appid)
        if not block:
            continue
        app_open, app_close = block

        # Write LaunchOptions in the flat app block, where Steam reads it.
        # The cloud sub-block value is NOT shown in Steam properties, so
        # never write there.
        flat, rest = _split_flat(content[app_open + 1:app_close])
        launch_match = launch_pattern.search(flat)

        if launch_match:
            existing = launch_match.group(2)
            if vdf_options in existing:
                continue
            new_options = (existing.strip() + " " + vdf_options).strip()
            flat = launch_pattern.sub(
                lambda m: m.group(1) + new_options + m.group(3), flat, count=1
            )
        else:
            # Insert before the first sub-block, or at the end if there is none.
            # Take the indent from the existing flat keys, so the entry lines up
            # however deep this appid block is nested.
            # With no flat keys, use one tab (what the old key-line lookup gave).
            indent_match = re.search(r'\n(\t+)"', flat)
            indent = indent_match.group(1) if indent_match else '\t'
            flat = _add_flat_key(flat, f'{indent}"LaunchOptions"\t\t"{vdf_options}"\n')

        _write_and_validate_vdf(vdf_path, content[:app_open + 1] + flat + rest + content[app_close:],
                                errors="replace")
        _record_localconfig(uid, appid, "LaunchOptions", vdf_options)


def clear_launch_options(steam_root, appid):
    """
    Remove any LaunchOptions for a Steam game in localconfig.vdf.

    Installers call it before writing a new option, and Remove calls it.
    It also clears options left by older DeckOps versions that used launch
    commands instead of exe renames. Must be called while Steam is closed.
    """
    appid = str(appid)
    launch_pattern = _value_pattern("LaunchOptions")

    for uid, vdf_path, content in _localconfigs(steam_root):
        block = _app_block(content, appid)
        if not block:
            continue
        app_open, app_close = block

        # Only touch LaunchOptions in the flat block, not inside sub-blocks.
        flat, rest = _split_flat(content[app_open + 1:app_close])
        launch_match = launch_pattern.search(flat)
        if not launch_match or not launch_match.group(2).strip():
            continue

        # Set the value to an empty string
        flat = launch_pattern.sub(r'\g<1>\g<3>', flat, count=1)
        _write_and_validate_vdf(vdf_path, content[:app_open + 1] + flat + rest + content[app_close:],
                                errors="replace")
        _record_localconfig(uid, appid, "LaunchOptions", "")


def _reapply_launch_menus():
    # Steam refreshes appinfo.vdf from Valve's servers now and then, which
    # drops our launch menu entries. Put them back whenever Steam is closed.
    try:
        import config as _cfg
        c = _cfg.load()
        if c.get("launch_menus"):
            from steam_appinfo import reapply_all
            reapply_all(c.get("steam_root") or os.path.expanduser("~/.local/share/Steam"))
    except Exception:
        _log.debug("launch menu reapply failed", exc_info=True)


# The 32-bit client and the 64-bit one (steamrt64). Whole word, so steamwebhelper does not match.
_STEAM_PROC = r"(ubuntu12_32|steamrt64)/steam( |$)"


def kill_steam(on_progress=None):
    """
    Close the Steam desktop client cleanly without triggering the SteamOS
    session manager (which would switch back to Game Mode).

    Sends SIGTERM to the Steam client and waits for Steam to shut itself
    down. Never force-kills (SIGKILL), because that can corrupt
    localconfig.vdf and start the SteamOS first-run wizard.

    on_progress: optional callback(str) for status messages while
                 waiting for Steam to exit.

    Raises TimeoutError after 120 seconds if Steam refuses to close.
    """
    import time

    # Is Steam running at all?
    r = subprocess.run(
        ["pgrep", "-f", _STEAM_PROC],
        capture_output=True
    )
    if r.returncode != 0:
        _reapply_launch_menus()
        return  # Steam is not running

    # SIGTERM to the main Steam process makes it shut down and write its config
    subprocess.run(["pkill", "-TERM", "-f", _STEAM_PROC], capture_output=True)

    if on_progress:
        on_progress("Waiting for Steam to safely close itself...")

    # Wait for Steam to exit on its own. Never force-kill.
    deadline = time.time() + 120
    elapsed = 0
    while time.time() < deadline:
        r = subprocess.run(
            ["pgrep", "-f", _STEAM_PROC],
            capture_output=True
        )
        if r.returncode != 0:
            # Steam is gone. Steam writes config.vdf and localconfig.vdf
            # during shutdown, and the kernel may still buffer those writes
            # after the process exits. sync flushes them before we touch
            # any VDF file.
            time.sleep(3)
            subprocess.run(["sync"], capture_output=True)
            _reapply_launch_menus()
            return
        time.sleep(1)
        elapsed += 1
        if on_progress and elapsed % 10 == 0:
            on_progress("Still waiting for Steam to close safely...")

    raise TimeoutError(
        "Steam did not close within 120 seconds. "
        "Please close Steam manually and try again."
    )


def launch_steam(uri=None):
    """
    Open a steam:// URI (or just Steam itself) fully detached from DeckOps.

    Uses xdg-open for a URI and gtk-launch for a plain launch.
    start_new_session=True keeps Steam from being a child of DeckOps, so
    it keeps running if DeckOps exits.

    uri: a steam:// URI, e.g. "steam://open/console". If None, Steam
         opens from its .desktop file.
    """
    try:
        if uri:
            cmd = ["xdg-open", uri]
        else:
            cmd = ["gtk-launch", "steam.desktop"]
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _log.info("Launched Steam%s (detached)", f" with {uri}" if uri else "")
    except FileNotFoundError:
        _log.warning("Could not find %s", cmd[0])
    except Exception as ex:
        _log.warning("Failed to launch Steam: %s", ex)


def set_steam_input_enabled(steam_root, appids=None):
    """
    Enable Steam Input for the given appids by setting
    UseSteamControllerConfig to "1" in each user's localconfig.vdf.

    Must be called while Steam is closed.

    steam_root: path to the Steam root directory
    appids:     list of int or str appids. Defaults to every game DeckOps manages.
    """
    # Every regular Steam appid DeckOps manages. Non-Steam shortcuts get
    # AllowDesktopConfig in shortcuts.vdf instead.
    DEFAULT_APPIDS = [
        "7940",    # CoD4
        "10090",   # WaW
        "10180",   # MW2 SP
        "10190",   # MW2 MP
        "42680",   # MW3 SP
        "42690",   # MW3 MP
        "42750",   # MW3 Dedicated Server
        "42700",   # BO1
        "42710",   # BO1 MP
        "202970",  # BO2 SP
        "202990",  # BO2 MP
        "212910",  # BO2 ZM
        "311210",  # BO3
        "2620",    # CoD1 SP (IW-Pad)
        "2640",    # UO SP (IW-Pad)
        "2630",    # CoD2 SP (IW-Pad)
    ]

    if appids is None:
        appids = DEFAULT_APPIDS

    appids = [str(a) for a in appids]
    si_pattern = _value_pattern("UseSteamControllerConfig")

    for uid, vdf_path, content in _localconfigs(steam_root):
        modified_appids = []
        for appid in appids:
            block = _app_block(content, appid)
            if not block:
                continue
            app_open, app_close = block

            # Only patch the flat section, never a sub-block
            flat, rest = _split_flat(content[app_open + 1:app_close])
            si_match = si_pattern.search(flat)

            if si_match:
                if si_match.group(2) == "1":
                    continue  # already enabled
                flat = si_pattern.sub(lambda m: m.group(1) + "1" + m.group(3), flat, count=1)
            else:
                indent_match = re.search(r'\n(\t+)"', flat)
                indent = indent_match.group(1) if indent_match else '\t\t\t\t\t\t'
                flat = _add_flat_key(flat, f'{indent}"UseSteamControllerConfig"\t\t"1"\n')

            content = content[:app_open + 1] + flat + rest + content[app_close:]
            modified_appids.append(appid)

        if modified_appids:
            _write_and_validate_vdf(vdf_path, content, errors="replace")
            for appid in modified_appids:
                _record_localconfig(uid, appid, "UseSteamControllerConfig", "1")


STEAM_CONFIG = os.path.expanduser("~/.local/share/Steam/config/config.vdf")


def set_compat_tool(appids, version):
    """
    Write a CompatToolMapping entry in Steam's config.vdf for each appid.
    This is the one implementation. ge_proton.py and shortcut.py both call
    it, so the entries are written twice at different points in the
    install flow, which makes it harder for Steam to override them.

    Steps (first match wins):
      1. The appid block exists: replace it in place.
      2. The CompatToolMapping block exists: insert into it.
      3. Otherwise: create the whole CompatToolMapping block.

    appids:  list of int or str appids, e.g. ["10190", "42690"]
    version: GE-Proton version string, e.g. "GE-Proton10-32"
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
        # Create the CompatToolMapping block with all entries at once
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
        # CompatToolMapping exists. Replace or insert each appid entry.
        for appid in appids:
            appid_str = str(appid)
            entry = _entry(appid_str)
            # The entry block is 4 lines, so [^}]* needs re.DOTALL to span
            # them.
            pattern = rf'(\t+"{re.escape(appid_str)}"\n\t+\{{[^}}]*\}})'
            if re.search(pattern, data, re.MULTILINE | re.DOTALL):
                # Replace the existing block
                data = re.sub(pattern, entry.rstrip('\n'), data, flags=re.MULTILINE | re.DOTALL)
            else:
                # Insert after the CompatToolMapping opening brace
                data = re.sub(
                    r'("CompatToolMapping"\s*\{)',
                    r'\1\n' + entry,
                    data,
                    count=1,
                )

    _write_and_validate_vdf(STEAM_CONFIG, data)
    for appid in appids:
        _record_config_vdf(str(appid), "CompatToolMapping", version)


def clear_compat_tool(appids):
    """
    Remove the CompatToolMapping entries for these appids from Steam's
    config.vdf. The inverse of set_compat_tool, for games Steam must NOT
    wrap in a compat tool, e.g. LCD Plutonium games whose launch options
    run `flatpak run` to hand off to Heroic.

    Steam runs any launch that has a CompatToolMapping entry inside Steam
    Linux Runtime (sniper). The host's flatpak binary is not visible from
    that container, so the flatpak call fails and the game closes right
    after it opens. Heroic runs Proton itself, so a Steam-side compat tool
    breaks the launch.

    Does nothing if config.vdf or the entry is missing. Must be called
    while Steam is closed so the change sticks.

    appids: list of int or str appids
    """
    if not os.path.exists(STEAM_CONFIG):
        return

    with open(STEAM_CONFIG, "r", encoding="utf-8") as f:
        data = f.read()

    modified = False
    for appid in appids:
        appid_str = str(appid)
        # Matches the appid block with its trailing newline, so no blank
        # line is left behind.
        pattern = rf'\t+"{re.escape(appid_str)}"\n\t+\{{[^}}]*\}}\n?'
        if re.search(pattern, data, re.MULTILINE | re.DOTALL):
            data = re.sub(pattern, "", data, flags=re.MULTILINE | re.DOTALL)
            modified = True

    if modified:
        _write_and_validate_vdf(STEAM_CONFIG, data)
        for appid in appids:
            _remove_config_vdf(str(appid), "CompatToolMapping")


def set_default_launch_option(steam_root, appids_config):
    """
    Set the default launch option for games with several launch modes, so
    the Steam Deck skips the 'which mode?' dialog.

    On SteamOS the Deck configurator controls the picker, not the normal
    localconfig.vdf apps block. So this function:

      - writes DefaultLaunchOption into the "apps" block right after
        "Deck_ConfiguratorInterstitialApps_AppLauncherInteractionIssues"
      - sets "Deck_ConfiguratorInterstitialsCheckbox_AppLauncherInteractionIssues"
        to "1", so the configurator treats the choice as confirmed and
        stops showing the picker

    appids_config: dict of appid to (hash_key, index),
        e.g. {"7940": ("7a722f97", "1"), "10090": ("9aa5e05f", "0")}

    Must be called while Steam is closed.
    """
    for uid, vdf_path, content in _localconfigs(steam_root):
        modified = False

        # Step 1: set the checkbox to "1", so the Deck configurator treats
        # the launch choice as confirmed and stops showing the picker.
        checkbox_pattern = _value_pattern("Deck_ConfiguratorInterstitialsCheckbox_AppLauncherInteractionIssues")
        if checkbox_pattern.search(content):
            content  = checkbox_pattern.sub(r'\g<1>1\g<3>', content)
            modified = True

        # Step 2: write DefaultLaunchOption into the Deck configurator's own
        # "apps" block, which is what the picker reads on SteamOS. The block
        # comes right after the InterstitialApps key.
        interstitial_match = _INTERSTITIAL_RE.search(content)

        if interstitial_match:
            apps_open  = interstitial_match.end() - 1
            apps_close = _find_block_end(content, apps_open)
            if apps_close != -1:
                apps_block = content[apps_open + 1:apps_close]

                for appid, (hash_key, index) in appids_config.items():
                    entry = _dlo_entry(appid, hash_key, index)
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
            # No Deck configurator block yet. Build it and insert it before
            # "LaunchOptionTipsShown" if that key is there.
            deck_block  = '\t\t\t"Deck_ConfiguratorInterstitialsVersionSeen_AppLauncherInteractionIssues"\t\t"1"\n'
            deck_block += '\t\t\t"Deck_ConfiguratorInterstitialsCheckbox_AppLauncherInteractionIssues"\t\t"1"\n'
            deck_block += '\t\t\t"Deck_ConfiguratorInterstitialApps_AppLauncherInteractionIssues"\t\t"[' + ','.join(appids_config.keys()) + ']"\n'
            deck_block += '\t\t\t"apps"\n\t\t\t{\n'
            for appid, (hash_key, index) in appids_config.items():
                deck_block += _dlo_entry(appid, hash_key, index)
            deck_block += '\t\t\t}\n'

            tips_pattern = re.compile(r'"LaunchOptionTipsShown"', re.IGNORECASE)
            tips_match   = tips_pattern.search(content)
            if tips_match:
                content  = content[:tips_match.start()] + deck_block + content[tips_match.start():]
                modified = True
            else:
                # No LaunchOptionTipsShown (fresh account). Insert before the
                # closing brace of the "Steam" block instead, which holds the
                # localconfig keys under "Software" -> "Valve" -> "Steam".
                steam_block_pattern = re.compile(r'"Steam"\s*\{', re.IGNORECASE)
                steam_match = steam_block_pattern.search(content)
                if steam_match:
                    steam_open  = steam_match.end() - 1
                    steam_close = _find_block_end(content, steam_open)
                    if steam_close != -1:
                        # Insert deck_block just before the Steam block closes
                        content = (
                            content[:steam_close] +
                            deck_block +
                            content[steam_close:]
                        )
                        modified = True

        if modified:
            _write_and_validate_vdf(vdf_path, content, errors="replace")
            for appid, (hash_key, index) in appids_config.items():
                _record_localconfig(
                    uid, appid, "DefaultLaunchOption",
                    json.dumps({"hash_key": hash_key, "index": index})
                )


def clear_default_launch_option(steam_root, appids):
    """
    Remove DeckOps' DefaultLaunchOption for these appids from the Deck
    configurator "apps" block (see set_default_launch_option), so Steam
    shows the launch menu again. Must be called while Steam is closed.
    """
    for uid, vdf_path, content in _localconfigs(steam_root):
        m = _INTERSTITIAL_RE.search(content)
        if not m:
            continue
        apps_open = m.end() - 1
        apps_close = _find_block_end(content, apps_open)
        if apps_close == -1:
            continue
        block = content[apps_open + 1:apps_close]
        changed = False
        for appid in appids:
            am = re.search(r'\s*"' + re.escape(str(appid)) + r'"\s*\{', block)
            if not am:
                continue
            end = _find_block_end(block, am.end() - 1)
            if end == -1:
                continue
            block = block[:am.start()] + block[end + 1:]
            changed = True
        if changed:
            _write_and_validate_vdf(vdf_path, content[:apps_open + 1] + block + content[apps_close:],
                                    errors="replace")
