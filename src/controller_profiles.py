"""
controller_profiles.py - DeckOps controller template installer

Copies the bundled controller templates from assets/controllers/
into Steam's controller_base/templates/ directory so they are available
globally across all games without any per-game or per-account setup.

Also patches the appropriate configset VDFs to set our template as the
active default for each managed game, overriding any community config or
workshop ID that Steam would otherwise use.

Universal templates (always installed — 26 total):
    PS5:       controller_ps5_deckops{,_ads,_other,_other_ads}.vdf
    PS5 Edge:  controller_ps5_edge_deckops{,_ads,_other,_other_ads}.vdf
    PS4:       controller_ps4_deckops{,_ads,_other,_other_ads}.vdf
    Xbox360:   controller_xbox360_deckops{,_other}.vdf
    XboxOne:   controller_xboxone_deckops{,_other}.vdf
    XboxElite: controller_xboxelite_deckops{,_other}.vdf
    Generic:   controller_generic_deckops{,_other}.vdf
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

Per-device Triton templates (Steam Machine only):
    controller_triton_deckops_{ads,off,hold,toggle}.vdf
    controller_triton_deckops_other_{ads,off,hold,toggle}.vdf

Must be called while Steam is closed.
"""

import os
import re
import shutil

from log import get_logger

_log = get_logger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────

from steam_common import (
    PROJECT_ROOT, STEAM_ROOT,
    calc_shortcut_appid as _calc_appid_int,
    find_all_steam_uids as _find_all_steam_uids,
    get_deck_serial as _get_deck_serial,
    patch_configset as _patch_configset,
    shortcut_title_key as _shortcut_title_key,
)
ASSETS_DIR    = os.path.join(PROJECT_ROOT, "assets", "controllers")
TEMPLATES_DIR = os.path.expanduser("~/.steam/steam/controller_base/templates")



def _calc_shortcut_appid(exe_path: str, name: str) -> str:
    """Str-returning wrapper over steam_common.calc_shortcut_appid.

    This module uses appids as configset keys and path segments, so the
    documented contract here is str. The CRC logic itself lives in
    steam_common — do not reimplement it.
    """
    return str(_calc_appid_int(exe_path, name))

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
    # BO3 (CleanOps) -- per-game PS controller variants
    "controller_ps5_deckops_bo3.vdf",
    "controller_ps5_deckops_bo3_ads.vdf",
    "controller_ps5_edge_deckops_bo3.vdf",
    "controller_ps5_edge_deckops_bo3_ads.vdf",
    "controller_ps4_deckops_bo3.vdf",
    "controller_ps4_deckops_bo3_ads.vdf",
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
]

# ── Per-device Neptune templates ──────────────────────────────────────────────
# Only the variant matching the user's device is installed.

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

TRITON_STANDARD = [
    # Triton (Steam Machine — Steam Controller 2)
    "controller_triton_deckops_ads.vdf",
    "controller_triton_deckops_off.vdf",
    "controller_triton_deckops_hold.vdf",
    "controller_triton_deckops_toggle.vdf",
    "controller_triton_deckops_other_ads.vdf",
    "controller_triton_deckops_other_off.vdf",
    "controller_triton_deckops_other_hold.vdf",
    "controller_triton_deckops_other_toggle.vdf",
]

# ── Per-game profile assignment map ───────────────────────────────────────────
#
# "standard" -- the user's scheme choice (normal gamepad layout)
# "other"    -- KB+M variant for SP campaigns that need mouse-look
#               via Steam Input (CoD4x MP)

APPID_PROFILE_MAP = {
    "7940":   "standard",  # CoD4 SP (IW3SP-MOD)
    "10090":  "standard",  # WaW -- Plutonium SP/ZM/MP
    "10180":  "standard",  # MW2 SP -- IW-Pad (stick input + aim assist)
    "10190":  "standard",  # MW2 MP -- iw4x
    "42680":  "standard",  # MW3 SP -- IW-Pad (stick input + aim assist)
    "42690":  "standard",  # MW3 MP -- Plutonium
    "42750":  "standard",  # MW3 DS -- Plutonium (free dedicated server)
    "42700":  "standard",  # BO1 SP/ZM -- Plutonium
    "42710":  "standard",  # BO1 MP -- Plutonium
    "202970": "standard",  # BO2 SP -- via Steam
    "202990": "standard",  # BO2 MP -- Plutonium
    "212910": "standard",  # BO2 ZM -- Plutonium
    "311210": "bo3",       # BO3 -- CleanOps (native controller support, per-game PS templates)
    "209160": "standard",  # Ghosts SP -- AlterWare (native controller + aim assist)
    "209170": "standard",  # Ghosts MP -- AlterWare (native controller + aim assist)
    "209650": "standard",  # AW SP -- AlterWare (native controller + aim assist)
    "209660": "standard",  # AW MP -- AlterWare (native controller + aim assist)
}

# Steam CoD1 / UO / CoD2 apps: SP with IW-Pad (MP runs through DeckOps shortcuts).
# Kept out of APPID_PROFILE_MAP because own shortcuts look their template up
# there by the game's appid, and the own MP shortcuts need "other".
STEAM_SP_APPS = {"2620": "standard", "2640": "standard", "2630": "standard"}

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
        "configset_controller_neptune.vdf",
        "configset_controller_triton.vdf",
    ],
}

# ── Non-Steam shortcut definitions ────────────────────────────────────────────
#
# DeckOps creates non-Steam shortcuts for the Steam copies of CoD1, UO, CoD2,
# CoD4 and WaW MP (and T7x, which is disabled). Their appids come from the exe
# path and name, so the install dirs are found and the appids worked out at
# runtime to assign controller profiles to them too. Without this,
# re-applying profiles from Settings would miss the shortcuts.
#
# Must match shortcut.py SHORTCUTS.

SHORTCUT_DEFS = {
    "cod1mp": {
        "name":          "Call of Duty - Multiplayer",
        "exe_name":      "CoDMP.exe",
        "game_appid":    "2620",
        "profile_type":  "other",
    },
    "coduomp": {
        "name":          "Call of Duty: United Offensive - Multiplayer",
        "exe_name":      "CoDUOMP.exe",
        "game_appid":    "2640",
        "profile_type":  "other",
    },
    "cod2mp": {
        "name":          "Call of Duty 2 - Multiplayer",
        "exe_name":      "CoD2MP_s.exe",
        "game_appid":    "2630",
        "profile_type":  "other",
    },
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
        "profile_type":  "bo3",
    },
}



# ── Helpers ───────────────────────────────────────────────────────────────────

def _primary_configset_name() -> tuple[str, str]:
    """Return (canonical_vdf_basename, configset_filename) for the primary controller.

    Steam Machine uses controller_triton; Legion Go 2 uses
    controller_steamos_handheld; everything else uses controller_neptune.
    """
    import config as cfg
    if cfg.is_steam_machine():
        return ("controller_triton.vdf",
                "configset_controller_triton.vdf")
    if cfg.is_other() and cfg.get_other_device_type() == "legion_go_2":
        return ("controller_steamos_handheld.vdf",
                "configset_controller_steamos_handheld.vdf")
    return ("controller_neptune.vdf",
            "configset_controller_neptune.vdf")


def _profile_filename(profile_type: str, gyro_mode: str) -> list[str]:
    """Return the list of primary controller VDF filenames for a profile type and gyro mode.

    Steam Machine uses Triton Standard (Steam Controller 2).

    Checks other_device_type when the device is "other" (non-Steam Deck):
        legion_go    -> Neptune Legion templates (no left touchpad)
        legion_go_2  -> SteamOS Handheld Legion templates
        2btn         -> Neptune 2btn templates (2 paddles, no touchpad)
        legion_go_s / generic -> standard Neptune (fallback)

    Gyro mode mapping:
        "on"     -> ads   (gyro activates on ADS / left trigger pull)
        "hold"   -> hold  (gyro active while holding a button)
        "toggle" -> toggle (gyro toggled on/off with a button press)
        "off"    -> off   (no gyro)

    Hold and toggle VDFs only exist for standard Neptune.
    Legion, legion_go_2, and 2btn devices only have ads/off variants.
    """
    # BO3 has per-game PS templates but uses standard Neptune for primary controller
    if profile_type == "bo3":
        profile_type = "standard"

    # Map gyro_mode to VDF filename suffix
    _SUFFIX_MAP = {"on": "ads", "hold": "hold", "toggle": "toggle"}
    suffix = _SUFFIX_MAP.get(gyro_mode, "off")

    import config as cfg

    # Steam Machine: Triton (Steam Controller 2)
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
        if profile_type == "bo3":
            suffix = "_bo3_ads" if use_ads else "_bo3"
        elif profile_type == "other":
            suffix = "_other_ads" if use_ads else "_other"
        else:
            suffix = "_ads" if use_ads else ""
        return [
            f"controller_ps5_deckops{suffix}.vdf",
            f"controller_ps4_deckops{suffix}.vdf",
            f"controller_ps5_edge_deckops{suffix}.vdf",
        ]

    # Non-PlayStation controllers have no per-game variants
    if profile_type == "bo3":
        profile_type = "standard"

    if controller_type == "xbox":
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
        if gyro_mode == "hold":
            suffix = "_other_hold" if profile_type == "other" else "_hold"
        elif gyro_mode == "toggle":
            suffix = "_other_toggle" if profile_type == "other" else "_toggle"
        elif gyro_mode == "off":
            suffix = "_other_off" if profile_type == "other" else "_off"
        else:
            suffix = "_other_ads" if profile_type == "other" else "_ads"
        import config as cfg
        prefix = "controller_triton" if cfg.is_steam_machine() else "controller_neptune"
        return [f"{prefix}_deckops{suffix}.vdf"]

    return []

def _cod4mp_profile(key: str, profile_type: str) -> str:
    # CoD4R has native controller support -- use standard gamepad layout
    if key != "cod4mp":
        return profile_type
    import config as cfg
    return cfg.get_cod4mp_profile_type(profile_type)


def _steam_shortcut_appids(prog) -> dict:
    """Non-Steam shortcut appids for SHORTCUT_DEFS games installed through Steam."""
    appids = {}
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
                appids[key] = _calc_shortcut_appid(exe_path, sdef["name"])
    except Exception as ex:
        prog(f"  ⚠ Could not detect shortcut appids: {ex}")
    return appids


def _launcher_appid(prog):
    # The launcher is not in SHORTCUT_DEFS because its exe is a shell script
    # under INSTALL_DIR, not a game exe in a Steam library. Read the appid
    # from shortcuts.vdf rather than recalculating the CRC so it matches
    # whatever Steam is actually using.
    try:
        from shortcut import get_shortcut_appid, LAUNCHER_TITLE
        found = get_shortcut_appid(LAUNCHER_TITLE)
        if found is not None:
            return str(found)
    except Exception as ex:
        prog(f"  ⚠ Could not detect launcher shortcut appid: {ex}")
    return None


def _assign(uids, pick, canonical, configsets, prog, launcher=False, label=""):
    """
    Shared body of assign_controller_profiles / assign_external_controller_profiles.

    pick(profile_type) -> template filenames, primary first
    canonical(primary) -> VDF name for the numbered appid folder
    configsets         -> configset filenames to patch under each uid
    launcher           -- also re-apply the offline launcher shortcut profile
    """
    shortcut_appids = _steam_shortcut_appids(prog)
    launcher_appid  = _launcher_appid(prog) if launcher else None

    def files(profile_type, missing_msg=None):
        filenames = pick(profile_type)
        if not filenames:
            return None
        if not os.path.exists(os.path.join(ASSETS_DIR, filenames[0])):
            if missing_msg:
                prog(missing_msg.format(filenames[0]))
            return None
        return filenames

    def write(uid, appid, filenames, num_dir=True, named_keys=()):
        primary = filenames[0]
        config_root    = os.path.join(STEAM_ROOT, "userdata", uid, "241100", "remote", "controller_config")
        steam_cfg_root = os.path.join(STEAM_ROOT, "steamapps", "common", "Steam Controller Configs", uid, "config")

        # Path 1: userdata controller_config (Your Layouts)
        dest_dir = os.path.join(config_root, appid)
        os.makedirs(dest_dir, exist_ok=True)
        for filename in filenames:
            src = os.path.join(ASSETS_DIR, filename)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(dest_dir, filename))

        # Path 2: numbered appid folder under Steam Controller Configs.
        # Writes the canonical VDF (e.g. controller_neptune.vdf or
        # controller_ps5.vdf) so Steam can find the profile even if the
        # configset patching has not taken effect yet.
        if num_dir:
            cfg_dir_num = os.path.join(steam_cfg_root, appid)
            os.makedirs(cfg_dir_num, exist_ok=True)
            shutil.copy2(os.path.join(ASSETS_DIR, primary), os.path.join(cfg_dir_num, canonical(primary)))

        # Path 3: patch configset files -- this sets the active default
        for cs_filename in configsets:
            configset_path = os.path.join(steam_cfg_root, cs_filename)
            _patch_configset(configset_path, appid, primary)
            for named_key in named_keys:
                _patch_configset(configset_path, named_key, primary)

    for uid in uids:
        for appid, profile_type in {**APPID_PROFILE_MAP, **STEAM_SP_APPS}.items():
            filenames = files(profile_type, "  ⚠ Asset missing, skipping: {}")
            if filenames:
                write(uid, appid, filenames, named_keys=APPID_NAMED_KEYS.get(appid, []))
                prog(f"  ✓ [{appid}] → {filenames[0]}")

        # ── Non-Steam shortcut controller profiles ────────────────────────────
        for key, sdef in SHORTCUT_DEFS.items():
            if key not in shortcut_appids:
                continue
            filenames = files(_cod4mp_profile(key, sdef["profile_type"]))
            if filenames:
                write(uid, shortcut_appids[key], filenames, named_keys=[_shortcut_title_key(sdef["name"])])
                prog(f"  ✓ [shortcut {shortcut_appids[key]}] → {filenames[0]}")

        # ── DeckOps offline launcher controller profile ───────────────────────
        # The launcher shortcut gets its initial profile from shortcut.py's
        # _assign_controller_config at creation time, but that write is lost
        # if Steam was running (Steam flushes in-memory configset state on
        # exit). Re-applying here means every install's final profile pass
        # and the Settings "Re-apply Templates" button self-heal the
        # launcher instead of skipping it.
        if launcher_appid:
            filenames = files("standard", "  ⚠ Asset missing, launcher skipped: {}")
            if filenames:
                from shortcut import LAUNCHER_TITLE
                write(uid, launcher_appid, filenames, named_keys=[_shortcut_title_key(LAUNCHER_TITLE)])
                prog(f"  ✓ [launcher {launcher_appid}] → {filenames[0]}")

    # ── "My Own" game controller profiles ────────────────────────────────────
    # For users who installed via CD/GOG/etc, DeckOps created the shortcuts
    # with canonical names. We recalculate the appid the same way
    # create_own_shortcuts() does and assign profiles to it.
    #
    # Some mod clients replace the exe in the shortcut (e.g. iw6-mod.exe
    # instead of iw6mp64_ship.exe). The CRC must use the same exe path
    # that was written into the shortcut's Exe field.
    try:
        from detect_games import find_own_installed
        from shortcut import OWN_SHORTCUTS, own_shortcut_exe
        for key, game in (find_own_installed() or {}).items():
            if key not in OWN_SHORTCUTS or not game.get("exe_path", ""):
                continue
            # Must match create_own_shortcuts: quoted exe + canonical name
            shortcut_appid = _calc_shortcut_appid(f'"{own_shortcut_exe(key, game)}"', OWN_SHORTCUTS[key]["name"])

            profile_type = APPID_PROFILE_MAP.get(game.get("appid", ""), OWN_SHORTCUTS[key].get("template_type", "standard"))
            filenames = files(_cod4mp_profile(key, profile_type))
            if not filenames:
                continue
            for uid in uids:
                write(uid, shortcut_appid, filenames, num_dir=False,
                      named_keys=[_shortcut_title_key(OWN_SHORTCUTS[key]["name"])])
            prog(f"  ✓ [own {shortcut_appid}] {key} → {filenames[0]}")
    except Exception as ex:
        prog(f"  ⚠ Could not assign {label}profiles for own games: {ex}")


# ── Public API ────────────────────────────────────────────────────────────────

def install_controller_templates(on_progress=None):
    """
    Copy DeckOps controller templates into Steam's global templates directory.

    Always installs universal templates (PS5, PS4, Xbox, Generic).
    Only installs the Neptune/Triton/SteamOS Handheld variant matching the user's device:
        Steam Deck LCD/OLED, Legion Go S, generic -> Neptune standard
        Steam Machine                             -> Triton standard
        Legion Go 1                               -> Neptune Legion
        Legion Go 2                               -> SteamOS Handheld Legion
        ROG Ally, MSI Claw                        -> Neptune 2btn

    Safe to call multiple times -- existing files are overwritten.
    Must be called while Steam is closed.
    """
    prog = on_progress or (lambda *a: None)

    import config as cfg

    # Build the full list: universal + device-specific
    to_install = list(TEMPLATES)

    model = cfg.get_deck_model() or "oled"
    if model == "steam_machine":
        to_install += TRITON_STANDARD
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
    Assign DeckOps controller profiles for all managed games.

    gyro_mode -- "on", "off", "hold", or "toggle"
    Must be called while Steam is closed.
    """
    prog = on_progress or (lambda *a: None)

    if gyro_mode not in ("on", "off", "hold", "toggle"):
        prog(f"  ⚠ Invalid gyro_mode '{gyro_mode}' -- must be 'on', 'off', 'hold', or 'toggle'.")
        return

    uids = _find_all_steam_uids()
    if not uids:
        prog("  ⚠ No Steam user accounts found -- controller assignment skipped.")
        return

    serial = _get_deck_serial()
    if serial:
        prog("  Deck serial found")
    else:
        prog("  ⚠ Could not read Deck serial -- serial configset write skipped.")

    # Resolve the primary controller type (neptune vs steamos_handheld)
    canonical_vdf, configset_filename = _primary_configset_name()
    configsets = [configset_filename] + ([f"configset_{serial}.vdf"] if serial else [])

    _assign(uids, lambda pt: _profile_filename(pt, gyro_mode), lambda primary: canonical_vdf,
            configsets, prog, launcher=True)

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
    prog = on_progress or (lambda *a: None)

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

    # Numbered appid folder name is the template name minus _deckops,
    # e.g. controller_ps5_deckops.vdf -> controller_ps5.vdf
    _assign(uids, lambda pt: _external_profile_filenames(controller_type, pt, gyro_mode),
            lambda primary: primary.replace("_deckops", ""),
            EXTERNAL_CONFIGSET_NAMES.get(controller_type, []), prog, label="external ")

    prog("External controller profiles assigned.")
