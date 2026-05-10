"""
DeckOps Decky Plugin — Python Backend

Toggles game display configs between handheld and docked modes.
Patches r_mode, r_aspectRatio, r_aspectRatioWindow, and r_displayRefresh
in all deployed game config files.

Handheld resolution is derived from the user's device:
  - Steam Deck LCD/OLED → 1280x800
  - Legion Go / Go S / Go 2, MSI Claw 8 → 1920x1200
  - ROG Ally / Ally X / Xbox Ally X → 1920x1080
  - Steam Machine / General PC → user-configured resolution
Docked resolution is auto-detected via xrandr/DRM or user-configured.

If DeckOps is not installed, the plugin exposes a download_deckops()
method to fetch and run install.sh. Display features are only available
after DeckOps is installed at ~/DeckOps-Nightly/.
"""

import os
import sys
import re
import subprocess
import asyncio
import glob

import decky

# ── Deferred DeckOps module imports ──────────────────────────────────────────
# The plugin runs from ~/homebrew/plugins/DeckOps/ but DeckOps source lives
# at ~/DeckOps-Nightly/src/. We add it to sys.path at load time (harmless if
# the directory doesn't exist yet), but defer the actual imports until first
# use so the plugin can load even when DeckOps is not installed.

DECKOPS_SRC = os.path.expanduser("~/DeckOps-Nightly/src")
if DECKOPS_SRC not in sys.path:
    sys.path.insert(0, DECKOPS_SRC)

DECKOPS_INSTALL_DIR = os.path.expanduser("~/DeckOps-Nightly")
DECKOPS_ENTRY_POINT = os.path.join(DECKOPS_INSTALL_DIR, "src", "main.py")

INSTALL_SH_URL = (
    "https://raw.githubusercontent.com/GalvarinoDev/"
    "DeckOps-Nightly/main/install.sh"
)

cfg = None
game_config = None
detect_games = None


def _ensure_deckops_imports():
    """
    Lazily import DeckOps modules on first use. Returns True if imports
    succeeded, False if DeckOps is not installed.
    """
    global cfg, game_config, detect_games

    if cfg is not None:
        return True

    try:
        import config as _cfg
        import game_config as _game_config
        import detect_games as _detect_games

        cfg = _cfg
        game_config = _game_config
        detect_games = _detect_games
        return True
    except ImportError as e:
        decky.logger.warning(f"DeckOps modules not available: {e}")
        return False


# ── Constants ────────────────────────────────────────────────────────────────

# Supported docked resolutions grouped by aspect ratio
SUPPORTED_RESOLUTIONS = {
    "16:9":  ["1920x1080", "1280x720"],
    "16:10": ["1920x1200", "1280x800"],
    "21:9":  ["2560x1080"],
}

# All supported resolutions as a flat set for validation
ALL_SUPPORTED = {r for group in SUPPORTED_RESOLUTIONS.values() for r in group}

# Aspect ratio dvar values per ratio
# Most games use "wide 16:9" or "wide 16:10"
# BO2 uses "auto" with a separate r_aspectRatioWindow float
ASPECT_RATIO_DVAR = {
    "16:9":  "wide 16:9",
    "16:10": "wide 16:10",
    "21:9":  "auto",
}

# BO2 r_aspectRatioWindow float values
ASPECT_RATIO_WINDOW = {
    "16:9":  "1.77778",
    "16:10": "1.6",
    "21:9":  "2.37037",
}

# Docked refresh = empty string (auto-detect from monitor)
DOCKED_REFRESH = ""

# Config filenames we patch
CONFIG_FILENAMES = {
    "config.cfg",
    "config_mp.cfg",
    "iw3sp_mod_config.cfg",
    "iw4x_config.cfg",
    "plutonium_mp.cfg",
    "plutonium_zm.cfg",
}


# ── Device-aware handheld resolution + refresh ───────────────────────────────

def _get_handheld_info():
    """
    Determine handheld resolution and refresh rate from the user's device
    config. Reads deck_model and other_device from deckops.json.

    Returns (resolution, refresh_rate, aspect_ratio_category).

    Device mapping:
      lcd                       → 1280x800   @ 60 Hz  (16:10)
      oled                      → 1280x800   @ 90 Hz  (16:10)
      other + 1920x1080         → 1920x1080  @ 60 Hz  (16:9)   ROG Ally, Ally X, Xbox Ally X
      other + 1920x1200         → 1920x1200  @ 60 Hz  (16:10)  Legion Go, Go S, MSI Claw 8
      other + 1920x1200_144hz   → 1920x1200  @ 144 Hz (16:10)  Legion Go 2
      other + None (general_pc) → fallback to docked_resolution or 1920x1080
      steam_machine + res       → user-configured resolution
      steam_machine + None      → fallback to 1280x720
    """
    deckops_cfg = cfg.load()
    deck_model = deckops_cfg.get("deck_model", "lcd")
    other_device = deckops_cfg.get("other_device")

    # ── Steam Deck LCD / OLED ────────────────────────────────────────────
    if deck_model == "lcd":
        return "1280x800", "60 Hz", "16:10"

    if deck_model == "oled":
        return "1280x800", "90 Hz", "16:10"

    # ── Other devices (Legion Go, ROG Ally, MSI Claw 8, General PC) ──────
    if deck_model == "other":
        if other_device:
            # Handle resolution keys with refresh suffix (e.g. "1920x1200_144hz")
            if "_" in other_device:
                res_part, refresh_part = other_device.rsplit("_", 1)
                # Extract numeric Hz value (e.g. "144hz" → "144 Hz")
                hz_match = re.match(r"(\d+)hz", refresh_part, re.IGNORECASE)
                refresh = f"{hz_match.group(1)} Hz" if hz_match else "60 Hz"
                resolution = res_part
            else:
                resolution = other_device
                refresh = "60 Hz"

            ratio = _classify_aspect_ratio(
                *map(int, resolution.split("x"))
            )
            return resolution, refresh, ratio or "16:9"

        # General PC with no preset resolution — use docked_resolution
        # as a best guess, or fall back to 1920x1080
        fallback = deckops_cfg.get("docked_resolution") or "1920x1080"
        ratio = _classify_aspect_ratio(*map(int, fallback.split("x")))
        decky.logger.info(
            f"General PC: no handheld resolution set, using {fallback}"
        )
        return fallback, "60 Hz", ratio or "16:9"

    # ── Steam Machine ────────────────────────────────────────────────────
    if deck_model == "steam_machine":
        if other_device and "_" not in other_device:
            ratio = _classify_aspect_ratio(
                *map(int, other_device.split("x"))
            )
            return other_device, "60 Hz", ratio or "16:9"

        # No resolution configured — safe default
        return "1280x720", "60 Hz", "16:9"

    # ── Unknown device — safe fallback ───────────────────────────────────
    decky.logger.warning(
        f"Unknown deck_model '{deck_model}', falling back to 1280x800"
    )
    return "1280x800", "60 Hz", "16:10"


# ── DRM-based external display detection ────────────────────────────────────

def _check_drm_external():
    """
    Check /sys/class/drm/ for connected external displays.

    Returns the connector name (e.g. 'DP-1', 'HDMI-A-1') if an external
    display is connected, or None if only eDP (internal) is connected.
    """
    drm_path = "/sys/class/drm"
    try:
        for entry in os.listdir(drm_path):
            # Skip internal display and non-connector entries
            if "eDP" in entry or "Writeback" in entry:
                continue
            if not entry.startswith("card"):
                continue

            status_file = os.path.join(drm_path, entry, "status")
            if os.path.exists(status_file):
                try:
                    with open(status_file, "r") as f:
                        status = f.read().strip()
                    if status == "connected":
                        # Extract connector name (e.g. 'card0-DP-1' -> 'DP-1')
                        parts = entry.split("-", 1)
                        connector = parts[1] if len(parts) > 1 else entry
                        decky.logger.info(f"DRM: External display on {connector}")
                        return connector
                except (IOError, OSError):
                    continue
    except (IOError, OSError):
        pass

    return None


# ── xrandr display detection ────────────────────────────────────────────────

def _run_xrandr(display=None):
    """
    Run xrandr and return output. Optionally set DISPLAY env var.
    """
    env = os.environ.copy()
    if display:
        env["DISPLAY"] = display

    try:
        out = subprocess.check_output(
            ["xrandr", "--current"], text=True, timeout=5, env=env
        )
        return out
    except Exception as e:
        decky.logger.error(f"xrandr failed (DISPLAY={display}): {e}")
        return None


def _parse_xrandr_resolution(xrandr_output):
    """
    Parse the current resolution from xrandr output.

    In Game Mode, outputs are named 'gamescope' rather than
    'eDP-1' or 'HDMI-A-1'. We look for the connected output
    and its current resolution.

    Returns (width, height) or None.
    """
    if not xrandr_output:
        return None

    for line in xrandr_output.splitlines():
        match = re.match(
            r'^(\S+)\s+connected\s+(?:primary\s+)?(\d+)x(\d+)',
            line
        )
        if match:
            return int(match.group(2)), int(match.group(3))

    return None


def _classify_aspect_ratio(width, height):
    """
    Determine aspect ratio string from dimensions.
    Returns "16:9", "16:10", "21:9", or None for unknown ratios.
    """
    ratio = width / height
    if abs(ratio - 16/9) < 0.05:
        return "16:9"
    elif abs(ratio - 16/10) < 0.05:
        return "16:10"
    elif abs(ratio - 21/9) < 0.1:
        return "21:9"
    return None


def _detect_external_display():
    """
    Detect external display resolution. Works in both Game Mode
    (Gamescope) and Desktop Mode.

    Game Mode strategy:
      - DISPLAY=:0 is Gamescope's external output (if connected)
      - DISPLAY=:1 is the internal screen
      - If :0 reports a resolution different from the device's native, it's external
      - Also checks DRM connectors to confirm external is connected

    Desktop Mode strategy:
      - Standard xrandr, look for non-eDP connected outputs

    Returns a dict with:
        connected: bool
        resolution: "WIDTHxHEIGHT" or None (native monitor resolution)
        aspect_ratio: "16:9" / "16:10" / "21:9" / None
        matched_res: closest supported resolution or None
        needs_testing: bool (true for 21:9 — untested, may need user verification)
    """
    result = {
        "connected": False,
        "resolution": None,
        "aspect_ratio": None,
        "matched_res": None,
        "needs_testing": False,
    }

    # Check DRM first — reliable way to know if external is plugged in
    drm_connector = _check_drm_external()

    # ── Game Mode detection (Gamescope) ──────────────────────────────────
    xrandr_d0 = _run_xrandr(":0")
    xrandr_d1 = _run_xrandr(":1")

    if xrandr_d0 and "gamescope" in xrandr_d0:
        # We're in Game Mode
        res_d0 = _parse_xrandr_resolution(xrandr_d0)
        res_d1 = _parse_xrandr_resolution(xrandr_d1)

        decky.logger.info(
            f"Game Mode: :0={res_d0}, :1={res_d1}, DRM={drm_connector}"
        )

        if res_d0 and drm_connector:
            width, height = res_d0
            # Get the device's native handheld resolution for comparison
            handheld_res, _, _ = _get_handheld_info()
            handheld_w, handheld_h = map(int, handheld_res.split("x"))

            if (width, height) != (handheld_w, handheld_h) or drm_connector:
                result["connected"] = True
                result["resolution"] = f"{width}x{height}"
                result["aspect_ratio"] = _classify_aspect_ratio(width, height)

                result["matched_res"] = _match_resolution(
                    width, height, result["aspect_ratio"]
                )

                # Flag 21:9 as needing testing
                if result["aspect_ratio"] == "21:9":
                    result["needs_testing"] = True
                    decky.logger.info(
                        f"21:9 ultrawide detected ({width}x{height}), "
                        f"using {result['matched_res']} — untested, may need verification"
                    )

                decky.logger.info(
                    f"External display detected: {width}x{height} "
                    f"(ratio={result['aspect_ratio']}, "
                    f"match={result['matched_res']})"
                )
                return result

        return result

    # ── Desktop Mode detection ───────────────────────────────────────────
    xrandr_out = xrandr_d0 or _run_xrandr()
    if not xrandr_out:
        return result

    for line in xrandr_out.splitlines():
        if line.startswith("eDP"):
            continue

        match = re.match(
            r'^(\S+)\s+connected\s+(?:primary\s+)?(\d+)x(\d+)',
            line
        )
        if match:
            output_name = match.group(1)
            width = int(match.group(2))
            height = int(match.group(3))

            result["connected"] = True
            result["resolution"] = f"{width}x{height}"
            result["aspect_ratio"] = _classify_aspect_ratio(width, height)

            result["matched_res"] = _match_resolution(
                width, height, result["aspect_ratio"]
            )

            if result["aspect_ratio"] == "21:9":
                result["needs_testing"] = True

            decky.logger.info(
                f"Desktop external: {output_name} at {width}x{height} "
                f"(ratio={result['aspect_ratio']}, "
                f"match={result['matched_res']})"
            )
            break

    return result


def _match_resolution(width, height, aspect_ratio):
    """
    Find the closest supported resolution for a detected display.

    Strategy:
    1. If the native res is directly supported, use it
    2. If we know the aspect ratio, pick the highest supported res
       in that ratio that doesn't exceed the native res
    3. Fall back to 1920x1080 (safe default for most monitors)
    """
    native = f"{width}x{height}"
    if native in ALL_SUPPORTED:
        return native

    # Try matching by aspect ratio
    if aspect_ratio and aspect_ratio in SUPPORTED_RESOLUTIONS:
        candidates = SUPPORTED_RESOLUTIONS[aspect_ratio]
        for res in candidates:  # sorted highest-first
            rw, rh = map(int, res.split("x"))
            if rw <= width and rh <= height:
                return res

    # Fallback: 1920x1080 if monitor is big enough, else 1280x720
    if width >= 1920 and height >= 1080:
        return "1920x1080"
    return "1280x720"


def _get_ratio_for_resolution(resolution):
    """
    Determine the aspect ratio category for a given resolution string.
    Returns "16:9", "16:10", or "21:9".
    """
    try:
        w, h = map(int, resolution.split("x"))
        ratio = _classify_aspect_ratio(w, h)
        return ratio or "16:9"  # default to 16:9 if unknown
    except (ValueError, AttributeError):
        return "16:9"


# ── Config patching ──────────────────────────────────────────────────────────

def _find_deployed_configs():
    """
    Find all game config files that DeckOps has deployed.

    Uses game_config's config map and dest resolvers to locate the
    actual config file paths on disk. Only returns files that exist.
    """
    deckops_cfg = cfg.load()
    steam_root = deckops_cfg.get("steam_root")
    setup_games = deckops_cfg.get("setup_games", {})

    if not steam_root or not setup_games:
        decky.logger.warning("No steam_root or setup_games in deckops.json")
        return []

    # Get installed games for path resolution
    try:
        library_folders = detect_games.parse_library_folders(steam_root)
        installed = detect_games.find_installed_games(library_folders, steam_root)
    except Exception as e:
        decky.logger.error(f"Failed to detect installed games: {e}")
        return []

    config_map = game_config._build_config_map(steam_root, installed)
    found_configs = []

    for game_key in setup_games:
        if game_key not in config_map:
            continue

        game = installed.get(game_key, {})
        install_dir = game.get("install_dir", "")

        for asset_subpath, fixed_dest in config_map[game_key]:
            # Resolve destination directory
            if fixed_dest:
                if game.get("source") == "own" and game.get("compatdata_path"):
                    pfx_parts = fixed_dest.split("/pfx/", 1)
                    if len(pfx_parts) == 2:
                        fixed_dest = os.path.join(
                            game["compatdata_path"], "pfx", pfx_parts[1]
                        )
                dest_dir = fixed_dest
            else:
                if not install_dir:
                    continue
                dest_dir = game_config._dest_from_install(game_key, install_dir)
                if not dest_dir:
                    continue

            config_file = os.path.join(
                dest_dir, os.path.basename(asset_subpath)
            )
            if os.path.exists(config_file):
                found_configs.append({
                    "path": config_file,
                    "game_key": game_key,
                    "filename": os.path.basename(config_file),
                })

    decky.logger.info(f"Found {len(found_configs)} deployed config files")
    return found_configs


def _patch_config(filepath, resolution, refresh_rate, aspect_ratio_str,
                  aspect_ratio_category):
    """
    Patch display dvars in a single config file:
      - r_mode          → resolution (e.g. "1920x1080")
      - r_displayRefresh → refresh_rate (e.g. "90 Hz" or "")
      - r_aspectRatio   → aspect string (e.g. "wide 16:9", "wide 16:10", "auto")
      - r_aspectRatioWindow → float string for BO2 (e.g. "1.77778")

    Does find-and-replace on the specific dvar lines. Leaves all
    other settings untouched.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except (IOError, OSError) as e:
        decky.logger.error(f"Failed to read {filepath}: {e}")
        return False

    original = content

    # Patch r_mode
    content = re.sub(
        r'(seta r_mode\s+")[^"]*(")',
        rf'\g<1>{resolution}\2',
        content
    )

    # Patch r_displayRefresh
    content = re.sub(
        r'(seta r_displayRefresh\s+")[^"]*(")',
        rf'\g<1>{refresh_rate}\2',
        content
    )

    # Patch r_aspectRatio
    # BO2 configs use "auto", all others use "wide 16:9" / "wide 16:10"
    is_bo2 = "plutonium_" in os.path.basename(filepath)
    if is_bo2:
        # BO2 always uses "auto" — patch the window value instead
        ar_window = ASPECT_RATIO_WINDOW.get(aspect_ratio_category, "1.77778")
        content = re.sub(
            r'(seta r_aspectRatioWindow\s+")[^"]*(")',
            rf'\g<1>{ar_window}\2',
            content
        )
    else:
        content = re.sub(
            r'(seta r_aspectRatio\s+")[^"]*(")',
            rf'\g<1>{aspect_ratio_str}\2',
            content
        )

    if content == original:
        decky.logger.info(f"No changes needed for {filepath}")
        # Lock read-only even if nothing changed -- may have been
        # left writable by enable_file_editing or a previous run
        try:
            os.chmod(filepath, 0o444)
        except OSError:
            pass
        return True

    try:
        # Unlock before writing -- file may be read-only from a previous patch
        try:
            os.chmod(filepath, 0o644)
        except OSError:
            pass
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        # Lock read-only so the game engine can't overwrite our settings
        os.chmod(filepath, 0o444)
        decky.logger.info(
            f"Patched {filepath}: r_mode={resolution}, "
            f"refresh={refresh_rate}, aspect={aspect_ratio_str}"
        )
        return True
    except (IOError, OSError) as e:
        decky.logger.error(f"Failed to write {filepath}: {e}")
        return False


def _apply_mode(mode, resolution=None):
    """
    Apply handheld or docked display settings to all deployed configs.

    mode: "handheld" or "docked"
    resolution: for docked, the target resolution (auto-detected if None)

    Returns dict with results.
    """
    if mode == "handheld":
        target_res, target_refresh, target_ratio_cat = _get_handheld_info()
    else:
        # Docked mode
        if resolution:
            target_res = resolution
        else:
            display_info = _detect_external_display()
            target_res = display_info.get("matched_res", "1920x1080")
        target_refresh = DOCKED_REFRESH
        target_ratio_cat = _get_ratio_for_resolution(target_res)

    # Get the aspect ratio dvar string
    target_aspect_str = ASPECT_RATIO_DVAR.get(target_ratio_cat, "wide 16:9")

    configs = _find_deployed_configs()
    patched = 0
    failed = 0

    for config_entry in configs:
        if _patch_config(
            config_entry["path"], target_res, target_refresh,
            target_aspect_str, target_ratio_cat
        ):
            patched += 1
        else:
            failed += 1

    # Save the mode to deckops.json
    cfg.set_play_mode(mode)
    if mode == "docked":
        cfg.set_docked_resolution(target_res)

    decky.logger.info(
        f"Mode set to {mode}: {target_res} @ "
        f"{'auto' if not target_refresh else target_refresh} "
        f"(aspect={target_aspect_str}, "
        f"{patched} patched, {failed} failed)"
    )

    return {
        "mode": mode,
        "resolution": target_res,
        "refresh_rate": target_refresh or "auto",
        "patched": patched,
        "failed": failed,
        "total": len(configs),
    }


# ── Plugin class ─────────────────────────────────────────────────────────────

class Plugin:

    async def is_installed(self):
        """
        Check whether DeckOps is installed on the device.
        Returns {"installed": bool}.
        """
        installed = os.path.isfile(DECKOPS_ENTRY_POINT)
        decky.logger.info(f"DeckOps installed: {installed}")
        return {"installed": installed}

    async def download_deckops(self):
        """
        Download and run install.sh to install DeckOps.

        Downloads install.sh from GitHub, executes it in a subprocess,
        and returns success/failure with output.
        """
        import tempfile

        decky.logger.info("Starting DeckOps download...")

        # ── Download install.sh ──────────────────────────────────────────
        try:
            tmp_script = tempfile.mktemp(suffix=".sh", prefix="deckops_install_")
            result = subprocess.run(
                ["curl", "-sSL", INSTALL_SH_URL, "-o", tmp_script],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                decky.logger.error(f"curl failed: {result.stderr}")
                return {
                    "success": False,
                    "message": "Failed to download installer. Check your internet connection.",
                }
        except subprocess.TimeoutExpired:
            decky.logger.error("curl timed out downloading install.sh")
            return {
                "success": False,
                "message": "Download timed out. Check your internet connection.",
            }
        except Exception as e:
            decky.logger.error(f"Download error: {e}")
            return {
                "success": False,
                "message": f"Download failed: {e}",
            }

        # ── Run install.sh ───────────────────────────────────────────────
        try:
            os.chmod(tmp_script, 0o755)
            result = subprocess.run(
                ["bash", tmp_script],
                capture_output=True, text=True, timeout=300,
                env={**os.environ, "TERM": "dumb"},
            )

            # Clean up temp script
            try:
                os.remove(tmp_script)
            except OSError:
                pass

            if result.returncode != 0:
                decky.logger.error(
                    f"install.sh failed (rc={result.returncode}): "
                    f"{result.stderr[-500:]}"
                )
                return {
                    "success": False,
                    "message": "Installation failed. Check the Decky log for details.",
                }

            # Verify install succeeded
            if os.path.isfile(DECKOPS_ENTRY_POINT):
                decky.logger.info("DeckOps installed successfully")
                return {
                    "success": True,
                    "message": (
                        "DeckOps downloaded! Switch to Desktop Mode "
                        "and open DeckOps to set up your games."
                    ),
                }
            else:
                decky.logger.error(
                    "install.sh completed but entry point not found"
                )
                return {
                    "success": False,
                    "message": "Installation completed but DeckOps files not found.",
                }

        except subprocess.TimeoutExpired:
            decky.logger.error("install.sh timed out after 300s")
            try:
                os.remove(tmp_script)
            except OSError:
                pass
            return {
                "success": False,
                "message": "Installation timed out.",
            }
        except Exception as e:
            decky.logger.error(f"install.sh error: {e}")
            try:
                os.remove(tmp_script)
            except OSError:
                pass
            return {
                "success": False,
                "message": f"Installation failed: {e}",
            }

    async def get_status(self):
        """
        Return current display mode status for the frontend.
        """
        if not _ensure_deckops_imports():
            return {"error": "DeckOps is not installed"}

        deckops_cfg = cfg.load()
        play_mode = deckops_cfg.get("play_mode", "handheld") or "handheld"
        deck_model = deckops_cfg.get("deck_model", "lcd")
        docked_res = deckops_cfg.get("docked_resolution")

        # Check for external display
        display_info = _detect_external_display()

        # Get device-aware handheld info for status display
        handheld_res, handheld_refresh, _ = _get_handheld_info()

        return {
            "mode": play_mode,
            "deck_model": deck_model,
            "docked_resolution": docked_res,
            "external_connected": display_info["connected"],
            "external_resolution": display_info["resolution"],
            "external_aspect_ratio": display_info["aspect_ratio"],
            "matched_resolution": display_info["matched_res"],
            "needs_testing": display_info["needs_testing"],
            "handheld_refresh": handheld_refresh,
            "handheld_resolution": handheld_res,
        }

    async def set_handheld(self):
        """Switch all game configs to handheld mode."""
        if not _ensure_deckops_imports():
            return {"error": "DeckOps is not installed"}
        return _apply_mode("handheld")

    async def set_docked(self, resolution=None):
        """
        Switch all game configs to docked mode.
        If resolution is None, auto-detects from xrandr.
        """
        if not _ensure_deckops_imports():
            return {"error": "DeckOps is not installed"}
        return _apply_mode("docked", resolution)


    async def enable_file_editing(self):
        """
        Temporarily unlock all deployed game configs so the game engine
        can write to them (e.g. to save in-game settings changes).

        Configs are re-locked read-only automatically on the next mode
        switch (set_handheld / set_docked). This state is not persisted —
        a plugin reload will not re-unlock files.

        Intended to be surfaced in the UI as "Allow Game Config Editing",
        sitting beneath the handheld/docked resolution toggle.
        """
        if not _ensure_deckops_imports():
            return {"error": "DeckOps is not installed"}

        configs = _find_deployed_configs()
        unlocked = 0
        failed = 0

        for config_entry in configs:
            try:
                os.chmod(config_entry["path"], 0o644)
                unlocked += 1
                decky.logger.info(f"Unlocked for editing: {config_entry['path']}")
            except (IOError, OSError) as e:
                decky.logger.warning(
                    f"Could not unlock {config_entry['path']}: {e}"
                )
                failed += 1

        decky.logger.info(
            f"File editing enabled: {unlocked} unlocked, {failed} failed. "
            "Configs will be re-locked on next mode switch."
        )
        return {
            "unlocked": unlocked,
            "failed": failed,
            "total": len(configs),
        }

    async def detect_display(self):
        """Run xrandr detection and return display info."""
        return _detect_external_display()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def _main(self):
        self.loop = asyncio.get_event_loop()
        decky.logger.info("DeckOps display plugin loaded")

    async def _unload(self):
        decky.logger.info("DeckOps display plugin unloaded")

    async def _uninstall(self):
        decky.logger.info("DeckOps display plugin uninstalled")

    async def _migration(self):
        pass
