"""
controller_profiles.py - DeckOps controller template installer

Copies the bundled controller templates from assets/controllers/
into Steam's controller_base/templates/ directory so they are available
globally across all games without any per-game or per-account setup.

Also patches the appropriate configset VDFs to set our template as the
active default for each managed game, overriding any community config or
workshop ID that Steam would otherwise use.

Universal templates (always installed — 28 total):
    PS5:       controller_ps5_deckops{,_ads,_other,_other_ads}.vdf
    PS5 Edge:  controller_ps5_edge_deckops{,_ads,_other,_other_ads}.vdf
    PS4:       controller_ps4_deckops{,_ads,_other,_other_ads}.vdf
    Xbox360:   controller_xbox360_deckops{,_other}.vdf
    XboxOne:   controller_xboxone_deckops{,_other}.vdf
    XboxElite: controller_xboxelite_deckops{,_other}.vdf
    Generic:   controller_generic_deckops{,_other}.vdf
    Triton:    controller_triton_deckops_{ads,off,hold,toggle}.vdf
               controller_triton_deckops_other_{ads,off,hold,toggle}.vdf

Per-device Neptune templates (only the matching variant is installed):
    Standard (SD LCD/OLED, Legion Go S, generic):
        controller_neptune_deckops_{ads,off,hold,toggle}.vdf
        controller_neptune_deckops_other_{ads,off,hold,toggle}.vdf
    Legion (Go 1 — 4 paddles, no left touchpad):
        controller_neptune_deckops_legion_{ads,off}.vdf
        controller_neptune_deckops_legion_other_{ads,off}.vdf
    2btn (ROG Ally, MSI Claw — 2 paddles, no touchpad):
        controller_neptune_deckops_2btn_{ads,off}.vdf
        controller_neptune_deckops_2btn_other_{ads,off}.vdf

Per-device SteamOS Handheld templates (Legion Go 2 only):
    controller_steamos_handheld_deckops_legion_{ads,off}.vdf
    controller_steamos_handheld_deckops_legion_other_{ads,off}.vdf

Steam Machine uses triton templates as its PRIMARY controller (not external).
    assign_controller_profiles() returns triton VDFs via _profile_filename()
    instead of Neptune. Full hold/toggle support like standard Neptune.
    No Neptune templates are installed for Steam Machine.

Must be called while Steam is closed.
"""

import os
import re
import shutil
import binascii

from log import get_logger

_log = get_logger(__name__)


def _record_configset_edit(configset_path: str, key: str, template_name: str):
    """Record a configset VDF edit in the wrapper ledger."""
    try:
        from wrapper import _record_configset
        filename = os.path.basename(configset_path)
        _record_configset(filename, key, template_name)
    except Exception:
        _log.debug("configset ledger record failed", exc_info=True)


# ── Paths ─────────────────────────────────────────────────────────────────────

_HERE         = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT  = os.path.dirname(_HERE)
ASSETS_DIR    = os.path.join(PROJECT_ROOT, "assets", "controllers")
TEMPLATES_DIR = os.path.expanduser("~/.steam/steam/controller_base/templates")
STEAM_DIR     = os.path.expanduser("~/.local/share/Steam")
STEAM_CONFIG  = os.path.join(STEAM_DIR, "config", "config.vdf")

TEMPLATES = [
    # ── Universal templates (always installed) ────────────────────────────
    # These cover any controller a user might plug in, regardless of device.
    # PS5
    "controller_ps5_deckops.vdf",
    "controller_ps5_deckops_ads.vdf",
    "controller_ps5_deckops_other.vdf",
    "controller_ps5_deckops_other_ads.vdf",
    # PS5 DualSense Edge (4 paddles, gyro)
    "controller_ps5_edge_deckops.vdf",
    "controller_ps5_edge_deckops_ads.vdf",
    "controller_ps5_edge_deckops_other.vdf",
    "controller_ps5_edge_deckops_other_ads.vdf",
    # PS4
    "controller_ps4_deckops.vdf",
    "controller_ps4_deckops_ads.vdf",
    "controller_ps4_deckops_other.vdf",
    "controller_ps4_deckops_other_ads.vdf",
    # Xbox 360
    "controller_xbox360_deckops.vdf",
    "controller_xbox360_deckops_other.vdf",
    # Xbox One
    "controller_xboxone_deckops.vdf",
    "controller_xboxone_deckops_other.vdf",
    # Xbox Elite 2 (4 paddles, no gyro)
    "controller_xboxelite_deckops.vdf",
    "controller_xboxelite_deckops_other.vdf",
    # Generic (covers 8BitDo and anything else Steam maps as generic)
    "controller_generic_deckops.vdf",
    "controller_generic_deckops_other.vdf",
    # Steam Controller 2 (Triton — dual trackpads, gyro, 4 back buttons)
    "controller_triton_deckops_ads.vdf",
    "controller_triton_deckops_off.vdf",
    "controller_triton_deckops_hold.vdf",
    "controller_triton_deckops_toggle.vdf",
    "controller_triton_deckops_other_ads.vdf",
    "controller_triton_deckops_other_off.vdf",
    "controller_triton_deckops_other_hold.vdf",
    "controller_triton_deckops_other_toggle.vdf",
]

# ── Per-device Neptune templates ──────────────────────────────────────────────
# Only the variant matching the user's device is installed.
# Steam Machine uses triton (already in TEMPLATES above) so needs no Neptune.

NEPTUNE_STANDARD = [
    # Standard (SD LCD/OLED, Legion Go S, generic fallback)
    "controller_neptune_deckops_ads.vdf",
    "controller_neptune_deckops_off.vdf",
    "controller_neptune_deckops_hold.vdf",
    "controller_neptune_deckops_toggle.vdf",
    "controller_neptune_deckops_other_ads.vdf",
    "controller_neptune_deckops_other_off.vdf",
    "controller_neptune_deckops_other_hold.vdf",
    "controller_neptune_deckops_other_toggle.vdf",
]

NEPTUNE_LEGION = [
    # Legion (Go 1 — 4 paddles, no left touchpad)
    "controller_neptune_deckops_legion_ads.vdf",
    "controller_neptune_deckops_legion_off.vdf",
    "controller_neptune_deckops_legion_other_ads.vdf",
    "controller_neptune_deckops_legion_other_off.vdf",
]

STEAMOS_HANDHELD_LEGION = [
    # SteamOS Handheld (Legion Go 2 — controller_steamos_handheld type)
    "controller_steamos_handheld_deckops_legion_ads.vdf",
    "controller_steamos_handheld_deckops_legion_off.vdf",
    "controller_steamos_handheld_deckops_legion_other_ads.vdf",
    "controller_steamos_handheld_deckops_legion_other_off.vdf",
]

NEPTUNE_2BTN = [
    # 2btn (ROG Ally, MSI Claw — 2 paddles, no touchpad)
    "controller_neptune_deckops_2btn_ads.vdf",
    "controller_neptune_deckops_2btn_off.vdf",
    "controller_neptune_deckops_2btn_other_ads.vdf",
    "controller_neptune_deckops_2btn_other_off.vdf",
]

# ── Per-game profile assignment map ───────────────────────────────────────────
#
# "standard" -- the user's scheme choice (normal gamepad layout)
# "other"    -- KB+M variant for SP campaigns that need mouse-look
#               via Steam Input (CoD4 MP, MW2 SP, MW3 SP)

APPID_PROFILE_MAP = {
    "7940":   "standard",  # CoD4 SP (IW3SP-MOD)
    "10090":  "standard",  # WaW -- Plutonium SP/ZM/MP
    "10180":  "other",     # MW2 SP -- via Steam, KB+M layout
    "10190":  "standard",  # MW2 MP -- iw4x
    "42680":  "other",     # MW3 SP -- via Steam, KB+M layout
    "42690":  "standard",  # MW3 MP -- Plutonium
    "42750":  "standard",  # MW3 DS -- Plutonium (free dedicated server)
    "42700":  "standard",  # BO1 SP/ZM -- Plutonium
    "42710":  "standard",  # BO1 MP -- Plutonium
    "202970": "standard",  # BO2 SP -- via Steam
    "202990": "standard",  # BO2 MP -- Plutonium
    "212910": "standard",  # BO2 ZM -- Plutonium
    "311210": "standard",  # BO3 -- CleanOps (native controller support)
    "209160": "standard",  # Ghosts SP -- AlterWare (native controller + aim assist)
    "209170": "standard",  # Ghosts MP -- AlterWare (native controller + aim assist)
    "209650": "standard",  # AW SP -- AlterWare (native controller + aim assist)
    "209660": "standard",  # AW MP -- AlterWare (native controller + aim assist)
}

# ── Named game keys used in configset VDFs ────────────────────────────────────
#
# Steam resolves controller profiles by both numeric appid AND a named key
# string in the configset files. We write both so the profile sticks.
#
# 10180 and 42680 are empty because they share a named key with their MP
# counterpart (10190 and 42690). Writing both would cause the MP entry to
# overwrite the SP entry since the loop processes them in order.
# See also: deckops_uninstall.sh mirrors this map for cleanup.

APPID_NAMED_KEYS = {
    "7940":   ["call of duty 4 modern warfare (2007)"],
    "10090":  ["call of duty world at war",
               "call of duty world at war - multiplayer"],
    "10180":  [],
    "10190":  ["call of duty modern warfare 2 (2009) - multiplayer"],
    "42680":  [],
    "42690":  ["call of duty modern warfare 3 - multiplayer"],
    "42750":  ["call of duty modern warfare 3 - dedicated server"],
    "42700":  ["call of duty black ops",
               "call of duty black ops - zombies"],
    "42710":  ["call of duty black ops - multiplayer"],
    "202970": [],
    "202990": ["call of duty black ops ii - multiplayer"],
    "212910": ["call of duty black ops ii - zombies"],
    "311210": ["call of duty black ops iii"],
    "209160": ["call of duty ghosts"],
    "209170": ["call of duty ghosts - multiplayer"],
    "209650": ["call of duty advanced warfare"],
    "209660": ["call of duty advanced warfare - multiplayer"],
}

# ── External controller configset filenames ───────────────────────────────────
#
# Maps the user's controller_type config value to the list of configset VDF
# filenames that need to be patched. PlayStation covers both PS4 and PS5 since
# we install both template variants and let Steam match the connected hardware.

EXTERNAL_CONFIGSET_NAMES = {
    "playstation": [
        "configset_controller_ps5.vdf",
        "configset_controller_ps4.vdf",
        "configset_controller_ps5_edge.vdf",
    ],
    "xbox": [
        "configset_controller_xbox360.vdf",
        "configset_controller_xboxone.vdf",
        "configset_controller_xboxelite.vdf",
    ],
    "other": [
        "configset_controller_generic.vdf",
    ],
    "steamcontroller": [
        "configset_controller_triton.vdf",
    ],
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
    "t7x": {
        "name":          "Call of Duty: Black Ops 3 T7x",
        "exe_name":      "t7x.exe",
        "game_appid":    "311210",
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
        _log.debug("serial number read failed", exc_info=True)
    return None


def _primary_configset_name() -> tuple[str, str]:
    """Return (canonical_vdf_basename, configset_filename) for the primary controller.

    Legion Go 2 uses controller_steamos_handheld; everything else uses
    controller_neptune.  The canonical VDF basename is what gets written
    into the numbered appid folder (e.g. controller_neptune.vdf).
    The configset filename is the configset file that gets patched.
    """
    import config as cfg
    if cfg.is_other() and cfg.get_other_device_type() == "legion_go_2":
        return ("controller_steamos_handheld.vdf",
                "configset_controller_steamos_handheld.vdf")
    return ("controller_neptune.vdf",
            "configset_controller_neptune.vdf")


def _profile_filename(profile_type: str, gyro_mode: str) -> list[str]:
    """Return the list of primary controller VDF filenames for a profile type and gyro mode.

    Steam Machine uses triton templates as its primary controller:
        Supports full hold/toggle (same suffix mapping as standard Neptune).

    Checks other_device_type when the device is "other" (non-Steam Deck):
        legion_go    -> Neptune Legion templates (no left touchpad)
        legion_go_2  -> SteamOS Handheld Legion templates
        2btn         -> Neptune 2btn templates (2 paddles, no touchpad)
        legion_go_s / generic -> standard Neptune (fallback)

    Gyro mode mapping for standard Neptune and triton:
        "on"     -> ads   (gyro activates on ADS / left trigger pull)
        "hold"   -> hold  (gyro active while holding a button)
        "toggle" -> toggle (gyro toggled on/off with a button press)
        "off"    -> off   (no gyro)

    Hold and toggle VDFs only exist for standard Neptune, and triton.
    Legion, legion_go_2, and 2btn devices only have ads/off variants —
    hold/toggle falls back to ads for those devices.
    """
    # Map gyro_mode to VDF filename suffix
    _SUFFIX_MAP = {"on": "ads", "hold": "hold", "toggle": "toggle"}
    suffix = _SUFFIX_MAP.get(gyro_mode, "off")

    import config as cfg

    # Steam Machine: triton is the primary controller (full hold/toggle support)
    if cfg.is_steam_machine():
        if profile_type == "other":
            return [f"controller_triton_deckops_other_{suffix}.vdf"]
        return [f"controller_triton_deckops_{suffix}.vdf"]

    # Check if this is a non-Deck device with a specific controller variant
    if cfg.is_other():
        device_type = cfg.get_other_device_type()
        # Legion, legion_go_2, and 2btn only have ads/off — no hold/toggle VDFs
        other_suffix = "ads" if gyro_mode in ("on", "hold", "toggle") else "off"
        if device_type == "legion_go":
            if profile_type == "other":
                return [f"controller_neptune_deckops_legion_other_{other_suffix}.vdf"]
            return [f"controller_neptune_deckops_legion_{other_suffix}.vdf"]
        elif device_type == "legion_go_2":
            if profile_type == "other":
                return [f"controller_steamos_handheld_deckops_legion_other_{other_suffix}.vdf"]
            return [f"controller_steamos_handheld_deckops_legion_{other_suffix}.vdf"]
        elif device_type == "2btn":
            if profile_type == "other":
                return [f"controller_neptune_deckops_2btn_other_{other_suffix}.vdf"]
            return [f"controller_neptune_deckops_2btn_{other_suffix}.vdf"]
        # legion_go_s and generic fall through to standard Neptune

    # Standard Neptune (Steam Deck LCD/OLED, Legion Go S, generic)
    if profile_type == "standard":
        return [f"controller_neptune_deckops_{suffix}.vdf"]
    elif profile_type == "other":
        return [f"controller_neptune_deckops_other_{suffix}.vdf"]
    return []


def _external_profile_filenames(controller_type: str, profile_type: str, gyro_mode: str) -> list[str]:
    """
    Return the list of external controller VDF filenames for a given
    controller type, profile type, and gyro mode.

    PS5/PS4/Edge gyro logic:
        on/hold/toggle -> _ads variant (gyro on left trigger pull)
        off            -> standard variant (no gyro)

    External controllers don't have separate hold/toggle VDFs —
    hold and toggle map to the ads variant (closest equivalent).
    Xbox/Elite/Generic: gyro_mode is ignored - no gyro hardware on these controllers.
    """
    use_ads = gyro_mode in ("on", "hold", "toggle")

    if controller_type == "playstation":
        if profile_type == "other":
            suffix = "_other_ads" if use_ads else "_other"
        else:
            suffix = "_ads" if use_ads else ""
        return [
            f"controller_ps5_deckops{suffix}.vdf",
            f"controller_ps4_deckops{suffix}.vdf",
            f"controller_ps5_edge_deckops{suffix}.vdf",
        ]

    elif controller_type == "xbox":
        if profile_type == "other":
            return [
                "controller_xbox360_deckops_other.vdf",
                "controller_xboxone_deckops_other.vdf",
                "controller_xboxelite_deckops_other.vdf",
            ]
        return [
            "controller_xbox360_deckops.vdf",
            "controller_xboxone_deckops.vdf",
            "controller_xboxelite_deckops.vdf",
        ]

    elif controller_type == "other":
        if profile_type == "other":
            return ["controller_generic_deckops_other.vdf"]
        return ["controller_generic_deckops.vdf"]

    elif controller_type == "steamcontroller":
        # Triton has gyro and its own hold/toggle VDFs (like Neptune)
        if gyro_mode == "hold":
            suffix = "_other_hold" if profile_type == "other" else "_hold"
        elif gyro_mode == "toggle":
            suffix = "_other_toggle" if profile_type == "other" else "_toggle"
        elif gyro_mode == "off":
            suffix = "_other_off" if profile_type == "other" else "_off"
        else:
            # "on" → ads variant
            suffix = "_other_ads" if profile_type == "other" else "_ads"
        return [f"controller_triton_deckops{suffix}.vdf"]

    return []


def _patch_configset(configset_path: str, key: str, template_name: str):
    """
    Patch a single key in a configset VDF to use our template.
    If the key exists, replace its contents. If not, insert it.
    """
    entry = f'\t"{key}"\n\t{{\n\t\t"template"\t\t"{template_name}"\n\t}}\n'

    if not os.path.exists(configset_path):
        os.makedirs(os.path.dirname(configset_path), exist_ok=True)
        with open(configset_path, "w", encoding="utf-8") as f:
            f.write('"controller_config"\n{\n' + entry + '}')
        _record_configset_edit(configset_path, key, template_name)
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
    _record_configset_edit(configset_path, key, template_name)


# ── Public API ────────────────────────────────────────────────────────────────

def install_controller_templates(on_progress=None):
    """
    Copy DeckOps controller templates into Steam's global templates directory.

    Always installs universal templates (PS5, PS4, Xbox, Generic, Triton).
    Only installs the Neptune/SteamOS Handheld variant matching the user's device:
        Steam Deck LCD/OLED, Legion Go S, generic -> Neptune standard
        Legion Go 1                               -> Neptune Legion
        Legion Go 2                               -> SteamOS Handheld Legion
        ROG Ally, MSI Claw                        -> Neptune 2btn
        Steam Machine                             -> none (uses triton)

    Safe to call multiple times -- existing files are overwritten.
    Must be called while Steam is closed.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    import config as cfg

    # Build the full list: universal + device-specific
    to_install = list(TEMPLATES)

    model = cfg.get_deck_model() or "oled"
    if model == "steam_machine":
        # Triton is already in TEMPLATES, no Neptune needed
        pass
    elif model == "other":
        device_type = cfg.get_other_device_type()
        if device_type == "legion_go":
            to_install += NEPTUNE_LEGION
        elif device_type == "legion_go_2":
            to_install += STEAMOS_HANDHELD_LEGION
        elif device_type == "2btn":
            to_install += NEPTUNE_2BTN
        else:
            # legion_go_s, generic -> standard Neptune
            to_install += NEPTUNE_STANDARD
    else:
        # LCD, OLED -> standard Neptune
        to_install += NEPTUNE_STANDARD

    os.makedirs(TEMPLATES_DIR, exist_ok=True)

    for filename in to_install:
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
    Assign DeckOps Neptune controller profiles for all managed games.

    gyro_mode -- "on", "off", "hold", or "toggle"
    Must be called while Steam is closed.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if gyro_mode not in ("on", "off", "hold", "toggle"):
        prog(f"  ⚠ Invalid gyro_mode '{gyro_mode}' -- must be 'on', 'off', 'hold', or 'toggle'.")
        return

    uids = _find_all_steam_uids()
    if not uids:
        prog("  ⚠ No Steam user accounts found -- controller assignment skipped.")
        return

    serial = _get_deck_serial()
    if serial:
        prog(f"  Deck serial: {serial}")
    else:
        prog("  ⚠ Could not read Deck serial -- serial configset write skipped.")

    # Pre-calculate non-Steam shortcut appids before entering the uid loop.
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

    # Resolve the primary controller type (neptune vs steamos_handheld)
    canonical_vdf, configset_filename = _primary_configset_name()

    for uid in uids:
        config_root    = os.path.join(
            STEAM_DIR, "userdata", uid, "241100", "remote", "controller_config"
        )
        steam_cfg_root = os.path.join(
            STEAM_DIR, "steamapps", "common", "Steam Controller Configs", uid, "config"
        )
        configset_primary = os.path.join(steam_cfg_root, configset_filename)
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

            # Path 2: numbered appid folder under Steam Controller Configs
            # Writes the canonical VDF (controller_neptune.vdf or
            # controller_steamos_handheld.vdf) so Steam can find the
            # profile even if the configset patching has not taken effect yet.
            cfg_dir_num = os.path.join(steam_cfg_root, appid)
            os.makedirs(cfg_dir_num, exist_ok=True)
            shutil.copy2(src_primary, os.path.join(cfg_dir_num, canonical_vdf))

            # Path 3: patch configset files -- this sets the active default
            _patch_configset(configset_primary, appid, primary_filename)
            if configset_serial:
                _patch_configset(configset_serial, appid, primary_filename)

            for named_key in APPID_NAMED_KEYS.get(appid, []):
                _patch_configset(configset_primary, named_key, primary_filename)
                if configset_serial:
                    _patch_configset(configset_serial, named_key, primary_filename)

            prog(f"  ✓ [{appid}] → {primary_filename}")

        # ── Non-Steam shortcut controller profiles ────────────────────────────
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

            dest_dir = os.path.join(config_root, shortcut_appid)
            os.makedirs(dest_dir, exist_ok=True)
            for filename in filenames:
                src = os.path.join(ASSETS_DIR, filename)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(dest_dir, filename))

            cfg_dir_num = os.path.join(steam_cfg_root, shortcut_appid)
            os.makedirs(cfg_dir_num, exist_ok=True)
            shutil.copy2(src_primary, os.path.join(cfg_dir_num, canonical_vdf))

            _patch_configset(configset_primary, shortcut_appid, primary_filename)
            if configset_serial:
                _patch_configset(configset_serial, shortcut_appid, primary_filename)

            prog(f"  ✓ [shortcut {shortcut_appid}] → {primary_filename}")

    # ── "My Own" game controller profiles ────────────────────────────────────
    # For users who installed via CD/GOG/etc, DeckOps created the shortcuts
    # with canonical names. We recalculate the appid the same way
    # create_own_shortcuts() does and assign profiles to it.
    #
    # Some mod clients replace the exe in the shortcut (e.g. iw6-mod.exe
    # instead of iw6mp64_ship.exe). The CRC must use the same exe path
    # that was written into the shortcut's Exe field.
    try:
        import config as cfg
        if cfg.get_game_source() == "own":
            from detect_games import find_own_installed
            from shortcut import OWN_SHORTCUTS
            own_games = find_own_installed()
            for key, game in own_games.items():
                if key not in OWN_SHORTCUTS:
                    continue
                own_def = OWN_SHORTCUTS[key]
                canonical_name = own_def["name"]
                exe_path = game.get("exe_path", "")
                if not exe_path:
                    continue
                install_dir = game.get("install_dir", "")

                # Resolve the actual exe that was used in the shortcut.
                # Must match create_own_game_shortcuts per-key logic.
                if key == "iw4mp" and install_dir:
                    actual_exe = os.path.join(install_dir, "iw4x.exe")
                elif key == "cod4sp" and install_dir:
                    actual_exe = os.path.join(install_dir, "iw3sp_mod.exe")
                elif key in ("iw6mp", "iw6sp") and install_dir:
                    actual_exe = os.path.join(install_dir, "iw6-mod.exe")
                elif key in ("s1mp", "s1sp") and install_dir:
                    actual_exe = os.path.join(install_dir, "s1-mod.exe")
                elif key == "t7x" and install_dir:
                    actual_exe = os.path.join(install_dir, "t7x.exe")
                else:
                    actual_exe = exe_path

                # Must match create_own_shortcuts: quoted exe + canonical name
                quoted_exe = f'"{actual_exe}"'
                shortcut_appid = _calc_shortcut_appid(quoted_exe, canonical_name)

                steam_appid = game.get("appid", "")
                profile_type = APPID_PROFILE_MAP.get(steam_appid, "standard")
                filenames = _profile_filename(profile_type, gyro_mode)
                primary_filename = filenames[0] if filenames else None
                if not primary_filename:
                    continue
                src_primary = os.path.join(ASSETS_DIR, primary_filename)
                if not os.path.exists(src_primary):
                    continue
                for uid in uids:
                    config_root = os.path.join(
                        STEAM_DIR, "userdata", uid, "241100", "remote", "controller_config"
                    )
                    steam_cfg_root = os.path.join(
                        STEAM_DIR, "steamapps", "common", "Steam Controller Configs", uid, "config"
                    )
                    configset_own = os.path.join(steam_cfg_root, configset_filename)
                    configset_serial_path = os.path.join(steam_cfg_root, f"configset_{serial}.vdf") if serial else None

                    dest_dir = os.path.join(config_root, shortcut_appid)
                    os.makedirs(dest_dir, exist_ok=True)
                    for filename in filenames:
                        src = os.path.join(ASSETS_DIR, filename)
                        if os.path.exists(src):
                            shutil.copy2(src, os.path.join(dest_dir, filename))

                    _patch_configset(configset_own, shortcut_appid, primary_filename)
                    if configset_serial_path:
                        _patch_configset(configset_serial_path, shortcut_appid, primary_filename)

                prog(f"  ✓ [own {shortcut_appid}] {key} → {primary_filename}")
    except Exception as ex:
        prog(f"  ⚠ Could not assign profiles for own games: {ex}")

    prog("Controller profiles assigned.")


def assign_external_controller_profiles(controller_type: str, gyro_mode: str, on_progress=None):
    """
    Assign DeckOps external controller profiles for all managed games.

    controller_type -- "playstation", "xbox", or "other"
    gyro_mode       -- "on" or "off" (only affects PS5/PS4 templates)

    Patches configset VDFs for the relevant external controller types so
    Steam picks up our templates when the user plugs in their controller.
    Must be called while Steam is closed.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if controller_type not in ("playstation", "xbox", "other", "steamcontroller"):
        prog(f"  ⚠ Invalid controller_type '{controller_type}'.")
        return

    if gyro_mode not in ("on", "off", "hold", "toggle"):
        prog(f"  ⚠ Invalid gyro_mode '{gyro_mode}' -- must be 'on', 'off', 'hold', or 'toggle'.")
        return

    uids = _find_all_steam_uids()
    if not uids:
        prog("  ⚠ No Steam user accounts found -- external controller assignment skipped.")
        return

    configset_filenames = EXTERNAL_CONFIGSET_NAMES.get(controller_type, [])

    # Pre-calculate non-Steam shortcut appids
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

        for appid, profile_type in APPID_PROFILE_MAP.items():
            filenames        = _external_profile_filenames(controller_type, profile_type, gyro_mode)
            primary_filename = filenames[0] if filenames else None
            if not primary_filename:
                continue

            src_primary = os.path.join(ASSETS_DIR, primary_filename)
            if not os.path.exists(src_primary):
                prog(f"  ⚠ Asset missing, skipping: {primary_filename}")
                continue

            # Copy all matching templates into the userdata controller_config dir
            dest_dir = os.path.join(config_root, appid)
            os.makedirs(dest_dir, exist_ok=True)
            for filename in filenames:
                src = os.path.join(ASSETS_DIR, filename)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(dest_dir, filename))

            # Path 2: numbered appid folder -- derive canonical name from
            # template filename by stripping _deckops suffix.
            # e.g. controller_ps5_deckops.vdf -> controller_ps5.vdf
            canonical_vdf = primary_filename.replace("_deckops", "")
            cfg_dir_num = os.path.join(steam_cfg_root, appid)
            os.makedirs(cfg_dir_num, exist_ok=True)
            shutil.copy2(src_primary, os.path.join(cfg_dir_num, canonical_vdf))

            # Patch all relevant external configset files
            for cs_filename in configset_filenames:
                configset_path = os.path.join(steam_cfg_root, cs_filename)
                _patch_configset(configset_path, appid, primary_filename)

                for named_key in APPID_NAMED_KEYS.get(appid, []):
                    _patch_configset(configset_path, named_key, primary_filename)

            prog(f"  ✓ [{appid}] → {primary_filename}")

        # ── Non-Steam shortcut controller profiles ────────────────────────────
        for key, sdef in SHORTCUT_DEFS.items():
            if key not in shortcut_appids:
                continue

            shortcut_appid   = shortcut_appids[key]
            filenames        = _external_profile_filenames(controller_type, sdef["profile_type"], gyro_mode)
            primary_filename = filenames[0] if filenames else None
            if not primary_filename:
                continue

            src_primary = os.path.join(ASSETS_DIR, primary_filename)
            if not os.path.exists(src_primary):
                continue

            dest_dir = os.path.join(config_root, shortcut_appid)
            os.makedirs(dest_dir, exist_ok=True)
            for filename in filenames:
                src = os.path.join(ASSETS_DIR, filename)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(dest_dir, filename))

            canonical_vdf = primary_filename.replace("_deckops", "")
            cfg_dir_num = os.path.join(steam_cfg_root, shortcut_appid)
            os.makedirs(cfg_dir_num, exist_ok=True)
            shutil.copy2(src_primary, os.path.join(cfg_dir_num, canonical_vdf))

            for cs_filename in configset_filenames:
                configset_path = os.path.join(steam_cfg_root, cs_filename)
                _patch_configset(configset_path, shortcut_appid, primary_filename)

            prog(f"  ✓ [shortcut {shortcut_appid}] → {primary_filename}")

    # ── "My Own" game external controller profiles ────────────────────────────
    try:
        import config as cfg
        if cfg.get_game_source() == "own":
            from detect_games import find_own_installed
            from shortcut import OWN_SHORTCUTS
            own_games = find_own_installed()
            for key, game in own_games.items():
                if key not in OWN_SHORTCUTS:
                    continue
                own_def = OWN_SHORTCUTS[key]
                canonical_name = own_def["name"]
                exe_path = game.get("exe_path", "")
                if not exe_path:
                    continue
                install_dir = game.get("install_dir", "")

                # Resolve the actual exe that was used in the shortcut.
                # Must match create_own_game_shortcuts per-key logic.
                if key == "iw4mp" and install_dir:
                    actual_exe = os.path.join(install_dir, "iw4x.exe")
                elif key == "cod4sp" and install_dir:
                    actual_exe = os.path.join(install_dir, "iw3sp_mod.exe")
                elif key in ("iw6mp", "iw6sp") and install_dir:
                    actual_exe = os.path.join(install_dir, "iw6-mod.exe")
                elif key in ("s1mp", "s1sp") and install_dir:
                    actual_exe = os.path.join(install_dir, "s1-mod.exe")
                elif key == "t7x" and install_dir:
                    actual_exe = os.path.join(install_dir, "t7x.exe")
                else:
                    actual_exe = exe_path

                quoted_exe = f'"{actual_exe}"'
                shortcut_appid = _calc_shortcut_appid(quoted_exe, canonical_name)

                steam_appid  = game.get("appid", "")
                profile_type = APPID_PROFILE_MAP.get(steam_appid, "standard")
                filenames    = _external_profile_filenames(controller_type, profile_type, gyro_mode)
                primary_filename = filenames[0] if filenames else None
                if not primary_filename:
                    continue
                src_primary = os.path.join(ASSETS_DIR, primary_filename)
                if not os.path.exists(src_primary):
                    continue

                for uid in uids:
                    config_root    = os.path.join(
                        STEAM_DIR, "userdata", uid, "241100", "remote", "controller_config"
                    )
                    steam_cfg_root = os.path.join(
                        STEAM_DIR, "steamapps", "common", "Steam Controller Configs", uid, "config"
                    )
                    dest_dir = os.path.join(config_root, shortcut_appid)
                    os.makedirs(dest_dir, exist_ok=True)
                    for filename in filenames:
                        src = os.path.join(ASSETS_DIR, filename)
                        if os.path.exists(src):
                            shutil.copy2(src, os.path.join(dest_dir, filename))

                    for cs_filename in configset_filenames:
                        configset_path = os.path.join(steam_cfg_root, cs_filename)
                        _patch_configset(configset_path, shortcut_appid, primary_filename)

                prog(f"  ✓ [own {shortcut_appid}] {key} → {primary_filename}")
    except Exception as ex:
        prog(f"  ⚠ Could not assign external profiles for own games: {ex}")

    prog("External controller profiles assigned.")
