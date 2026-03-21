"""
controller_profiles.py - DeckOps controller template installer

Copies the bundled Neptune controller templates from assets/controllers/
into Steam's controller_base/templates/ directory so they are available
globally across all games without any per-game or per-account setup.

Also patches configset_controller_neptune.vdf to set our template as the
active default for each managed game, overriding any community config or
workshop ID that Steam would otherwise use.

Templates (2 variants × 3 schemes = 6 total):
    controller_neptune_deckops_hold.vdf
    controller_neptune_deckops_toggle.vdf
    controller_neptune_deckops_ads.vdf
    controller_neptune_deckops_other_hold.vdf
    controller_neptune_deckops_other_toggle.vdf
    controller_neptune_deckops_other_ads.vdf

Must be called while Steam is closed.
"""

import os
import re
import shutil
import binascii

# ── Paths ─────────────────────────────────────────────────────────────────────

_HERE         = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT  = os.path.dirname(_HERE)
ASSETS_DIR    = os.path.join(PROJECT_ROOT, "assets", "controllers")
TEMPLATES_DIR = os.path.expanduser("~/.steam/steam/controller_base/templates")
STEAM_DIR     = os.path.expanduser("~/.local/share/Steam")
STEAM_CONFIG  = os.path.join(STEAM_DIR, "config", "config.vdf")

TEMPLATES = [
    "controller_neptune_deckops_hold.vdf",
    "controller_neptune_deckops_toggle.vdf",
    "controller_neptune_deckops_ads.vdf",
    "controller_neptune_deckops_other_hold.vdf",
    "controller_neptune_deckops_other_toggle.vdf",
    "controller_neptune_deckops_other_ads.vdf",
]

# ── Per-game profile assignment map ───────────────────────────────────────────
#
# "standard" — the user's scheme choice (normal gamepad layout)
# "other"    — the user's scheme choice but KB+M variant (for SP campaigns
#              that need mouse-look via Steam Input)

APPID_PROFILE_MAP = {
    "7940":   "standard",  # CoD4 SP (IW3SP-MOD)
    "10090":  "standard",  # WaW — Plutonium SP/ZM/MP
    "10180":  "other",     # MW2 SP — via Steam, KB+M layout
    "10190":  "standard",  # MW2 MP — iw4x
    "42680":  "other",     # MW3 SP — via Steam, KB+M layout
    "42690":  "standard",  # MW3 MP — Plutonium
    "42700":  "standard",  # BO1 SP/ZM — Plutonium
    "42710":  "standard",  # BO1 MP — Plutonium
    "202970": "standard",  # BO2 SP — via Steam
    "202990": "standard",  # BO2 MP — Plutonium
    "212910": "standard",  # BO2 ZM — Plutonium
}

# ── Named game keys used in configset_controller_neptune.vdf ──────────────────
#
# Steam resolves controller profiles by both numeric appid AND a named key
# string in the configset files. We write both so the profile sticks.
#
# 10180 and 42680 are empty because they're SP titles that share a named key
# with their MP counterpart (10190 and 42690). If both wrote to the same
# named key, the MP entry would overwrite the SP entry every time since
# the loop processes them in order. Using appid-only for SP avoids that.
# See also: deckops_uninstall.sh mirrors this map for cleanup.

APPID_NAMED_KEYS = {
    "7940":   ["call of duty 4 modern warfare (2007)"],
    "10090":  ["call of duty world at war",
               "call of duty world at war - multiplayer"],
    "10180":  [],
    "10190":  ["call of duty modern warfare 2 (2009) - multiplayer"],
    "42680":  [],
    "42690":  ["call of duty modern warfare 3 - multiplayer"],
    "42700":  ["call of duty black ops",
               "call of duty black ops - zombies"],
    "42710":  ["call of duty black ops - multiplayer"],
    "202970": [],
    "202990": ["call of duty black ops ii - multiplayer"],
    "212910": ["call of duty black ops ii - zombies"],
}

# ── Non-Steam shortcut definitions ────────────────────────────────────────────
#
# DeckOps creates non-Steam shortcuts for CoD4 MP and WaW MP. These have
# dynamically calculated appids based on exe path + name. We need to find
# the install dirs and calculate the appids at runtime so we can assign
# controller profiles to them too. Without this, re-applying profiles from
# Settings would miss the shortcuts entirely.
#
# Must match shortcut.py SHORTCUTS.

SHORTCUT_DEFS = {
    "cod4mp": {
        "name":          "Call of Duty 4: Modern Warfare - Multiplayer",
        "exe_name":      "iw3mp.exe",
        "game_appid":    "7940",
        "profile_type":  "other",
    },
    "t4mp": {
        "name":          "Call of Duty: World at War - Multiplayer",
        "exe_name":      "CoDWaWmp.exe",
        "game_appid":    "10090",
        "profile_type":  "standard",
    },
}

MIN_UID = 10000


# ── Helpers ───────────────────────────────────────────────────────────────────

def _calc_shortcut_appid(exe_path: str, name: str) -> str:
    """
    Calculate the Steam shortcut appid from exe path and name.
    Must match shortcut.py _calc_shortcut_appid exactly.
    """
    key = (exe_path + name).encode("utf-8")
    crc = binascii.crc32(key) & 0xFFFFFFFF
    return str((crc | 0x80000000) & 0xFFFFFFFF)

def _find_all_steam_uids() -> list[str]:
    """Return all valid Steam user ID folders from userdata/."""
    userdata = os.path.join(STEAM_DIR, "userdata")
    if not os.path.isdir(userdata):
        return []
    seen, uids = set(), []
    for entry in os.listdir(userdata):
        if not entry.isdigit() or int(entry) < MIN_UID:
            continue
        real = os.path.realpath(os.path.join(userdata, entry))
        if real in seen:
            continue
        seen.add(real)
        uids.append(entry)
    return uids


def _get_deck_serial() -> str | None:
    """Read the Steam Deck serial number from Steam's config.vdf."""
    if not os.path.exists(STEAM_CONFIG):
        return None
    try:
        with open(STEAM_CONFIG, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        match = re.search(r'"SteamDeckRegisteredSerialNumber"\s+"([^"]+)"', content)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def _profile_filename(profile_type: str, gyro_mode: str) -> list[str]:
    """Return the list of VDF filenames for a given profile type and gyro mode."""
    if profile_type == "standard":
        return [f"controller_neptune_deckops_{gyro_mode}.vdf"]
    elif profile_type == "other":
        return [f"controller_neptune_deckops_other_{gyro_mode}.vdf"]
    return []


def _patch_configset(configset_path: str, key: str, template_name: str):
    """
    Patch a single key in configset_controller_neptune.vdf to use our template.
    If the key exists, replace its contents. If not, insert it.
    """
    entry = f'\t"{key}"\n\t{{\n\t\t"template"\t\t"{template_name}"\n\t}}\n'

    if not os.path.exists(configset_path):
        os.makedirs(os.path.dirname(configset_path), exist_ok=True)
        with open(configset_path, "w", encoding="utf-8") as f:
            f.write('"controller_config"\n{\n' + entry + '}')
        return

    with open(configset_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # This regex works because configset entries are shallow (one level of braces).
    # [^}}]* matches everything inside the block without crossing into nested blocks.
    # Do NOT reuse this pattern for deeper VDF structures like config.vdf or
    # localconfig.vdf where blocks nest multiple levels deep.
    pattern = rf'\t"{re.escape(key)}"\n\t\{{[^}}]*\}}\n?'
    if re.search(pattern, content, re.MULTILINE | re.DOTALL):
        content = re.sub(pattern, entry, content, flags=re.MULTILINE | re.DOTALL)
    else:
        content = content.rstrip()
        if content.endswith("}"):
            content = content[:-1].rstrip() + "\n" + entry + "}\n"

    with open(configset_path, "w", encoding="utf-8") as f:
        f.write(content)


# ── Public API ────────────────────────────────────────────────────────────────

def install_controller_templates(on_progress=None):
    """
    Copy all DeckOps Neptune templates into Steam's global templates directory.
    Safe to call multiple times — existing files are overwritten.
    Must be called while Steam is closed.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    os.makedirs(TEMPLATES_DIR, exist_ok=True)

    for filename in TEMPLATES:
        src  = os.path.join(ASSETS_DIR, filename)
        dest = os.path.join(TEMPLATES_DIR, filename)

        if not os.path.exists(src):
            prog(f"  ⚠ Template not found, skipping: {filename}")
            continue

        shutil.copy2(src, dest)
        prog(f"  ✓ {filename}")

    prog("Controller templates installed.")


def assign_controller_profiles(gyro_mode: str, on_progress=None):
    """
    Assign DeckOps controller profiles for all managed games.

    gyro_mode — "hold", "toggle", or "ads"
    Must be called while Steam is closed.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if gyro_mode not in ("hold", "toggle", "ads"):
        prog(f"  ⚠ Invalid gyro_mode '{gyro_mode}' — must be 'hold', 'toggle', or 'ads'.")
        return

    uids = _find_all_steam_uids()
    if not uids:
        prog("  ⚠ No Steam user accounts found — controller assignment skipped.")
        return

    serial = _get_deck_serial()
    if serial:
        prog(f"  Deck serial: {serial}")
    else:
        prog("  ⚠ Could not read Deck serial — serial configset write skipped.")

    # Pre-calculate non-Steam shortcut appids before entering the uid loop.
    # These depend on the exe path which is the same for all users.
    shortcut_appids = {}
    try:
        from detect_games import find_steam_root, parse_library_folders, find_installed_games
        steam_root = find_steam_root()
        if steam_root:
            installed = find_installed_games(parse_library_folders(steam_root))
            for key, sdef in SHORTCUT_DEFS.items():
                game = installed.get(key)
                if not game:
                    continue
                install_dir = game.get("install_dir", "")
                if not install_dir:
                    continue
                exe_path = os.path.join(install_dir, sdef["exe_name"])
                shortcut_appids[key] = _calc_shortcut_appid(exe_path, sdef["name"])
    except Exception as ex:
        prog(f"  ⚠ Could not detect shortcut appids: {ex}")

    for uid in uids:
        config_root    = os.path.join(
            STEAM_DIR, "userdata", uid, "241100", "remote", "controller_config"
        )
        steam_cfg_root = os.path.join(
            STEAM_DIR, "steamapps", "common", "Steam Controller Configs", uid, "config"
        )
        configset_neptune = os.path.join(steam_cfg_root, "configset_controller_neptune.vdf")
        configset_serial  = os.path.join(steam_cfg_root, f"configset_{serial}.vdf") if serial else None

        for appid, profile_type in APPID_PROFILE_MAP.items():
            filenames        = _profile_filename(profile_type, gyro_mode)
            primary_filename = filenames[0] if filenames else None
            if not primary_filename:
                continue

            src_primary = os.path.join(ASSETS_DIR, primary_filename)
            if not os.path.exists(src_primary):
                prog(f"  ⚠ Asset missing, skipping: {primary_filename}")
                continue

            # Path 1: userdata controller_config (Your Layouts)
            dest_dir = os.path.join(config_root, appid)
            os.makedirs(dest_dir, exist_ok=True)
            for filename in filenames:
                src  = os.path.join(ASSETS_DIR, filename)
                dest = os.path.join(dest_dir, filename)
                if os.path.exists(src):
                    shutil.copy2(src, dest)

            # Path 2: numbered appid folder — controller_neptune.vdf
            cfg_dir_num = os.path.join(steam_cfg_root, appid)
            os.makedirs(cfg_dir_num, exist_ok=True)
            shutil.copy2(src_primary, os.path.join(cfg_dir_num, "controller_neptune.vdf"))

            # Path 3: patch configset files — this sets the active default
            _patch_configset(configset_neptune, appid, primary_filename)
            if configset_serial:
                _patch_configset(configset_serial, appid, primary_filename)

            for named_key in APPID_NAMED_KEYS.get(appid, []):
                _patch_configset(configset_neptune, named_key, primary_filename)
                if configset_serial:
                    _patch_configset(configset_serial, named_key, primary_filename)

            prog(f"  ✓ [{appid}] → {primary_filename}")

        # ── Non-Steam shortcut controller profiles ────────────────────────────
        # These have dynamic appids calculated from exe path + name. We need
        # to find the actual install dirs to get the right appid. Without this,
        # re-applying profiles from Settings would miss MW1 MP and WaW MP.
        for key, sdef in SHORTCUT_DEFS.items():
            if key not in shortcut_appids:
                continue

            shortcut_appid   = shortcut_appids[key]
            filenames        = _profile_filename(sdef["profile_type"], gyro_mode)
            primary_filename = filenames[0] if filenames else None
            if not primary_filename:
                continue

            src_primary = os.path.join(ASSETS_DIR, primary_filename)
            if not os.path.exists(src_primary):
                continue

            # Write to all three paths, same as static appids above
            dest_dir = os.path.join(config_root, shortcut_appid)
            os.makedirs(dest_dir, exist_ok=True)
            for filename in filenames:
                src = os.path.join(ASSETS_DIR, filename)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(dest_dir, filename))

            cfg_dir_num = os.path.join(steam_cfg_root, shortcut_appid)
            os.makedirs(cfg_dir_num, exist_ok=True)
            shutil.copy2(src_primary, os.path.join(cfg_dir_num, "controller_neptune.vdf"))

            _patch_configset(configset_neptune, shortcut_appid, primary_filename)
            if configset_serial:
                _patch_configset(configset_serial, shortcut_appid, primary_filename)

            prog(f"  ✓ [shortcut {shortcut_appid}] → {primary_filename}")

    prog("Controller profiles assigned.")
