"""
controller_profiles.py - DeckOps controller template installer

Copies the four bundled Neptune controller templates from assets/controllers/
into Steam's controller_base/templates/ directory so they are available
globally across all games without any per-game or per-account setup.

Also patches configset_controller_neptune.vdf to set our template as the
active default for each managed game, overriding any community config or
workshop ID that Steam would otherwise use.

Templates:
    controller_neptune_deckops_hold.vdf         — gyro active while R5 held
    controller_neptune_deckops_toggle.vdf        — R5 toggles gyro on/off
    controller_neptune_deckops_other_hold.vdf    — KB+M with R5 hold gyro
    controller_neptune_deckops_other_toggle.vdf  — KB+M with R5 toggle gyro

Must be called while Steam is closed.
"""

import os
import re
import shutil

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
    "controller_neptune_deckops_other_hold.vdf",
    "controller_neptune_deckops_other_toggle.vdf",
]

# ── Per-game profile assignment map ───────────────────────────────────────────
#
# "standard" — the user's hold/toggle choice (normal gamepad layout)
# "other"    — the user's hold/toggle choice but KB+M variant (for SP campaigns
#              that need mouse-look via Steam Input)
# "both"     — writes both standard AND other so the user can switch in Steam
#              Input per session (CoD4, which shares one appid for SP and MP)

APPID_PROFILE_MAP = {
    "7940":   "standard",  # CoD4 — SP only (IW3SP-MOD); MP (CoD4x) handled by non-Steam shortcut
    "10090":  "standard",  # WaW  — Plutonium SP/ZM/MP
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
# Each appid may also appear under named keys in the configset file.
# We patch both the numeric appid key AND any named keys.

APPID_NAMED_KEYS = {
    "7940":   ["call of duty 4 modern warfare (2007)"],
    "10090":  ["call of duty world at war",
               "call of duty world at war - multiplayer"],
    "10180":  ["call of duty modern warfare 2 (2009) - multiplayer"],
    "10190":  ["call of duty modern warfare 2 (2009) - multiplayer"],
    "42680":  ["call of duty modern warfare 3 - multiplayer"],
    "42690":  ["call of duty modern warfare 3 - multiplayer"],
    "42700":  ["call of duty black ops",
               "call of duty black ops - zombies"],
    "42710":  ["call of duty black ops - multiplayer"],
    "202970": [],
    "202990": ["call of duty black ops ii - multiplayer"],
    "212910": ["call of duty black ops ii - zombies"],
}

MIN_UID = 10000


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    suffix = gyro_mode
    if profile_type == "standard":
        return [f"controller_neptune_deckops_{suffix}.vdf"]
    elif profile_type == "other":
        return [f"controller_neptune_deckops_other_{suffix}.vdf"]
    elif profile_type == "both":
        return [
            f"controller_neptune_deckops_{suffix}.vdf",
            f"controller_neptune_deckops_other_{suffix}.vdf",
        ]
    return []


def _patch_configset(configset_path: str, key: str, template_name: str):
    """
    Patch a single key in configset_controller_neptune.vdf to use our template.
    If the key exists, replace its contents. If not, insert it.
    """
    entry = f'\t"{key}"\n\t{{\n\t\t"template"\t\t"{template_name}"\n\t}}\n'

    if not os.path.exists(configset_path):
        # Create minimal file — note the leading quote on "controller_config"
        with open(configset_path, "w", encoding="utf-8") as f:
            f.write('"controller_config"\n{\n' + entry + '}')
        return

    with open(configset_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # Replace existing key block if present.
    # Use re.DOTALL so the block interior matches across lines.
    # \{{ and \}} are literal braces in the regex (escaped for f-string then regex).
    pattern = rf'\t"{re.escape(key)}"\n\t\{{[^}}]*\}}\n?'
    if re.search(pattern, content, re.MULTILINE | re.DOTALL):
        content = re.sub(pattern, entry, content, flags=re.MULTILINE | re.DOTALL)
    else:
        # Insert before closing brace of root block
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

    Writes to three places:
      1. userdata/.../controller_config/<appid>/ — shows in Your Layouts
      2. Steam Controller Configs/.../config/<appid>/controller_neptune.vdf
      3. Patches configset_controller_neptune.vdf and configset_<serial>.vdf
         to set our template as the active default — this is what Steam reads.

    gyro_mode — "hold" or "toggle"
    Must be called while Steam is closed.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    if gyro_mode not in ("hold", "toggle"):
        prog(f"  ⚠ Invalid gyro_mode '{gyro_mode}' — must be 'hold' or 'toggle'.")
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

            # ── Path 1: userdata controller_config (Your Layouts) ─────────────
            dest_dir = os.path.join(config_root, appid)
            os.makedirs(dest_dir, exist_ok=True)
            for filename in filenames:
                src  = os.path.join(ASSETS_DIR, filename)
                dest = os.path.join(dest_dir, filename)
                if os.path.exists(src):
                    shutil.copy2(src, dest)

            # ── Path 2: numbered appid folder — controller_neptune.vdf ────────
            cfg_dir_num = os.path.join(steam_cfg_root, appid)
            os.makedirs(cfg_dir_num, exist_ok=True)
            shutil.copy2(src_primary, os.path.join(cfg_dir_num, "controller_neptune.vdf"))

            # ── Path 3: patch configset files — this sets the active default ──
            # Patch numeric appid key
            _patch_configset(configset_neptune, appid, primary_filename)
            if configset_serial:
                _patch_configset(configset_serial, appid, primary_filename)

            # Patch named game keys
            for named_key in APPID_NAMED_KEYS.get(appid, []):
                _patch_configset(configset_neptune, named_key, primary_filename)
                if configset_serial:
                    _patch_configset(configset_serial, named_key, primary_filename)

            prog(f"  ✓ [{appid}] → {primary_filename}")

    prog("Controller profiles assigned.")
