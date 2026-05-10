#!/usr/bin/env python3
"""
launcher_plut_win.py - Offline LAN launcher for Plutonium on Steam Deck
(Windows .exe version — runs inside Proton)

A lightweight PyQt5 app that shows installed Plutonium games and lets
the user pick a mode (MP, S/Z, ZM) to launch in offline LAN mode.
Designed to run as a non-Steam shortcut with Proton in Game Mode.

This is a Windows executable built with PyInstaller. It runs inside
the same Wine/Proton prefix as the Plutonium bootstrapper, so launching
a game is a simple Windows-to-Windows subprocess call. No second Proton
instance, no environment conflicts, no cgroup issues.

Flow:
  1. Read DeckOps deckops.json (via Wine Z: drive) to find Plutonium games.
  2. Read Plutonium config.json from the prefix for game install paths.
  3. Show compact game rows with hero background art and mode buttons.
  4. User taps a mode → call bootstrapper directly with -lan → game starts.

Gamepad input: Steam Deck Game Mode maps D-pad to arrow keys and A/B to
Return/Escape. Qt sees these as keyPressEvents. evdev is not available
inside Wine, but the keyboard mapping works identically.
"""

import os
import sys
import subprocess
import threading
import urllib.request
import json

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy,
)
from PyQt5.QtGui import QFont, QFontDatabase, QPixmap, QPainter, QColor
from PyQt5.QtCore import (
    Qt, QTimer, QRect, QObject, QThread, pyqtSignal, pyqtSlot,
)

# ── paths ────────────────────────────────────────────────────────────────────
# Inside Wine/Proton, Z: maps to the Linux root filesystem.
# The Plutonium directory depends on deck model:
#   LCD  → Heroic shared prefix (~/Games/Heroic/Prefixes/default)
#   OLED → per-game Steam compatdata prefix
# Both are resolved via deckops.json at startup.
#
# All paths are derived from the exe location so they work on any Linux
# username, not just "deck".  The exe lives at:
#   ~/<INSTALL_DIR_NAME>/assets/LAN/DeckOps_Offline.exe
# so walking four parents up gives us the Linux home directory via Z:.

# ── Branch identity (mirrors identity.py — keep in sync) ─────────────────────
_BRANCH = "stable"  # "nightly" or "stable"
_INSTALL_DIR_NAME = "DeckOps-Nightly" if _BRANCH == "nightly" else "DeckOps"
_GITHUB_USER = "GalvarinoDev"
_GITHUB_REPO = "DeckOps-Nightly" if _BRANCH == "nightly" else "DeckOps"
_GITHUB_RAW = f"https://raw.githubusercontent.com/{_GITHUB_USER}/{_GITHUB_REPO}/refs/heads/main"


def _detect_linux_home() -> str:
    """Derive the Linux home directory (as a Wine Z: path) from the exe location.

    PyInstaller sets sys.executable to the .exe path, which sits at:
        Z:\\home\\<user>\\<INSTALL_DIR_NAME>\\assets\\LAN\\DeckOps_Offline.exe

    Walking four parents up (LAN → assets → <INSTALL_DIR_NAME> → home dir)
    gives us Z:\\home\\<user>.

    Falls back to Z:\\home\\deck if detection fails.
    """
    try:
        exe = os.path.abspath(sys.executable)
        # exe  = .../<INSTALL_DIR_NAME>/assets/LAN/DeckOps_Offline.exe
        # We want four levels up: exe → LAN → assets → <INSTALL_DIR_NAME> → home
        home = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(exe)
        )))
        # Sanity check: the install dir should exist one level down
        deckops_dir = os.path.join(home, _INSTALL_DIR_NAME)
        if os.path.isdir(deckops_dir):
            return home
    except Exception:
        pass
    return r"Z:\home\deck"


_LINUX_HOME = _detect_linux_home()

# DeckOps config lives on the Linux filesystem
_LINUX_PROJECT_ROOT = os.path.join(_LINUX_HOME, _INSTALL_DIR_NAME)
_DECKOPS_JSON = os.path.join(_LINUX_PROJECT_ROOT, "deckops.json")

# Assets
FONTS_DIR  = os.path.join(_LINUX_PROJECT_ROOT, "assets", "fonts")
HEROES_DIR = os.path.join(_LINUX_PROJECT_ROOT, "assets", "images", "heroes")
MUSIC_PATH = os.path.join(_LINUX_PROJECT_ROOT, "assets", "music",
                           "background.mp3")

# LCD Heroic prefix Plutonium path (Wine path via Z: drive)
_LCD_PLUT_DIR = os.path.join(
    _LINUX_HOME, "Games", "Heroic", "Prefixes", "default", "pfx",
    "drive_c", "users", "steamuser", "AppData", "Local", "Plutonium",
)

# OLED uses per-game compatdata — each game has its own prefix with its
# own config.json containing only that game's path. We need to merge
# config.json from ALL prefixes to get the complete picture.
_OLED_COMPATDATA_BASE = os.path.join(
    _LINUX_HOME, ".local", "share", "Steam", "steamapps", "compatdata",
)
_OLED_PLUT_SUFFIX = os.path.join(
    "pfx", "drive_c", "users", "steamuser",
    "AppData", "Local", "Plutonium",
)
# Check Steam appids first (most common), then scan remaining dirs
_OLED_APPID_PRIORITY = ["10090", "42700", "42710", "202990", "42690"]


def _find_all_plut_dirs() -> list:
    """Find all compatdata directories that contain Plutonium config.json."""
    results = []

    # Priority appids first
    for appid in _OLED_APPID_PRIORITY:
        candidate = os.path.join(_OLED_COMPATDATA_BASE, appid, _OLED_PLUT_SUFFIX)
        if os.path.exists(os.path.join(candidate, "config.json")):
            results.append(candidate)

    # Scan remaining dirs
    try:
        if os.path.isdir(_OLED_COMPATDATA_BASE):
            for entry in os.listdir(_OLED_COMPATDATA_BASE):
                if entry in _OLED_APPID_PRIORITY:
                    continue
                candidate = os.path.join(
                    _OLED_COMPATDATA_BASE, entry, _OLED_PLUT_SUFFIX,
                )
                if os.path.exists(os.path.join(candidate, "config.json")):
                    results.append(candidate)
    except OSError:
        pass

    return results


def _resolve_plut_dir() -> str:
    """Determine the primary Plutonium directory (where the bootstrapper lives).

    LCD: Heroic shared prefix.
    OLED / Other: first prefix found with a bootstrapper exe. Falls back to
    first prefix with config.json, then LOCALAPPDATA.
    """
    try:
        with open(_DECKOPS_JSON, "r") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

    model = cfg.get("deck_model", "oled")

    if model == "lcd":
        return _LCD_PLUT_DIR

    # OLED / Other: find a prefix that has the bootstrapper
    all_dirs = _find_all_plut_dirs()
    for d in all_dirs:
        if os.path.exists(os.path.join(d, "bin",
                                        "plutonium-bootstrapper-win32.exe")):
            return d

    # No bootstrapper found — use first with config.json
    if all_dirs:
        return all_dirs[0]

    # Fallback to LOCALAPPDATA (whatever prefix this exe is running in)
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Plutonium")


# Resolved at import time
_PLUT_DIR = _resolve_plut_dir()
_BOOTSTRAPPER = os.path.join(_PLUT_DIR, "bin",
                              "plutonium-bootstrapper-win32.exe")

# Plutonium game key → protocol key (for bootstrapper argument)
_PLUT_KEY_MAP = {
    "iw5mp_ds": "iw5mp",
}

def _plut_key(game_key: str) -> str:
    return _PLUT_KEY_MAP.get(game_key, game_key)


# ── per-game prefix resolution (OLED only) ───────────────────────────────────
# Maps game keys to the Steam appid whose compatdata prefix should be used
# for launching that game. Each game runs from its own prefix, ensuring
# the correct DLLs, registry, and Proton state are available.
# LCD is unaffected — it uses the Heroic shared prefix for everything.

_GAME_KEY_APPIDS = {
    "t4sp":     "10090",
    "t4mp":     "10090",
    "t5sp":     "42700",
    "t5mp":     "42710",
    "t6mp":     "202990",
    "t6zm":     "212910",
    "iw5mp":    "42690",
    "iw5mp_ds": "42690",
}


def _resolve_game_plut_dir(game_key: str) -> tuple:
    """
    Resolve the Plutonium directory and bootstrapper path for a specific
    game key. On OLED / Other, uses the game's own compatdata prefix.
    On LCD, returns the global _PLUT_DIR.

    Returns (plut_dir, bootstrapper_path).
    Falls back to the global _PLUT_DIR if the per-game prefix doesn't
    have a bootstrapper.
    """
    # LCD: always use global (Heroic shared prefix)
    try:
        with open(_DECKOPS_JSON, "r") as f:
            cfg = json.load(f)
        if cfg.get("deck_model") == "lcd":
            return _PLUT_DIR, _BOOTSTRAPPER
    except Exception:
        pass

    # OLED / Other: try the game's own prefix first
    appid = _GAME_KEY_APPIDS.get(game_key)
    if appid:
        candidate = os.path.join(_OLED_COMPATDATA_BASE, appid, _OLED_PLUT_SUFFIX)
        bootstrapper = os.path.join(candidate, "bin",
                                     "plutonium-bootstrapper-win32.exe")
        if os.path.exists(bootstrapper):
            return candidate, bootstrapper

    # Fall back to global (original behavior)
    return _PLUT_DIR, _BOOTSTRAPPER


# ── colors (match DeckOps ui_qt.py) ──────────────────────────────────────────

C_BG       = "#141416"
C_CARD     = "#1E1E26"
C_IW       = "#6DC62B"
C_TREY     = "#F47B20"
C_DIM      = "#888899"
C_DARK_BTN = "#33333F"

# ── layout constants for 1280x800 ───────────────────────────────────────────

HEADER_H = 52
ROW_H    = 160
ROW_GAP  = 10
PAD_X    = 16
PAD_Y    = 12

# ── font ─────────────────────────────────────────────────────────────────────

_FONT_FAMILY = "Sans Serif"
_FONT_LOADED = False

def _load_font():
    global _FONT_FAMILY, _FONT_LOADED
    if _FONT_LOADED:
        return
    russo = os.path.join(FONTS_DIR, "RussoOne-Regular.ttf")
    if os.path.exists(russo):
        fid = QFontDatabase.addApplicationFont(russo)
        fams = QFontDatabase.applicationFontFamilies(fid)
        if fams:
            _FONT_FAMILY = fams[0]
    _FONT_LOADED = True

def _font(size=13, bold=False):
    f = QFont(_FONT_FAMILY, size)
    f.setBold(bold)
    return f

# ── Plutonium game data ──────────────────────────────────────────────────────

PLUT_GAMES = [
    {
        "base": "Call of Duty: World at War",
        "dev": "trey",
        "modes": [("t4mp", "MP"), ("t4sp", "S/Z")],
        "hero_url": f"{_GITHUB_RAW}/assets/images/heroes/waw-banner.png",
        "hero_file": "waw-banner.png",
    },
    {
        "base": "Call of Duty: Black Ops",
        "dev": "trey",
        "modes": [("t5mp", "MP"), ("t5sp", "S/Z")],
        "hero_url": f"{_GITHUB_RAW}/assets/images/heroes/bo1-banner.png",
        "hero_file": "bo1-banner.png",
    },
    {
        "base": "Call of Duty: Black Ops II",
        "dev": "trey",
        "modes": [("t6mp", "MP"), ("t6zm", "ZM")],
        "hero_url": f"{_GITHUB_RAW}/assets/images/heroes/bo2-banner.png",
        "hero_file": "bo2-banner.png",
    },
    {
        "base": "Call of Duty: Modern Warfare 3",
        "dev": "iw",
        "modes": [("iw5mp", "MP"), ("iw5mp_ds", "DS")],
        "hero_url": f"{_GITHUB_RAW}/assets/images/heroes/mw3-banner.png",
        "hero_file": "mw3-banner.png",
    },
]


# ── XInput gamepad polling ────────────────────────────────────────────────────
# Uses XInput-Python to read the Steam Deck's gamepad inside Wine/Proton.
# Steam Deck presents as an XInput controller in Game Mode.
# Polls on a QTimer — no threading needed.

_XINPUT_AVAILABLE = False
try:
    import XInput
    _XINPUT_AVAILABLE = True
except ImportError:
    pass

_GAMEPAD_POLL_MS = 50  # 20 Hz polling
_GAMEPAD_REPEAT_DELAY_MS = 400  # initial delay before repeat
_GAMEPAD_REPEAT_RATE_MS = 150   # repeat interval after initial delay


class GamepadPoller:
    """Polls XInput state and emits navigation actions."""

    # XInput button constants
    DPAD_UP    = 0x0001
    DPAD_DOWN  = 0x0002
    DPAD_LEFT  = 0x0004
    DPAD_RIGHT = 0x0008
    BTN_A      = 0x1000
    BTN_B      = 0x2000

    NAV_BUTTONS = (DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT, BTN_A, BTN_B)

    def __init__(self, on_up, on_down, on_left, on_right, on_activate, on_back):
        self._callbacks = {
            self.DPAD_UP:    on_up,
            self.DPAD_DOWN:  on_down,
            self.DPAD_LEFT:  on_left,
            self.DPAD_RIGHT: on_right,
            self.BTN_A:      on_activate,
            self.BTN_B:      on_back,
        }
        self._prev_buttons = 0
        self._held_button = None
        self._held_time_ms = 0

        self._timer = QTimer()
        self._timer.setInterval(_GAMEPAD_POLL_MS)
        self._timer.timeout.connect(self._poll)

    def start(self):
        if not _XINPUT_AVAILABLE:
            return
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _poll(self):
        try:
            # Find first connected controller
            connected = XInput.get_connected()
            ctrl_idx = None
            for i in range(4):
                if connected[i]:
                    ctrl_idx = i
                    break
            if ctrl_idx is None:
                return

            state = XInput.get_state(ctrl_idx)
            buttons = state.Gamepad.wButtons

            for btn in self.NAV_BUTTONS:
                is_pressed = bool(buttons & btn)
                was_pressed = bool(self._prev_buttons & btn)

                if is_pressed and not was_pressed:
                    # Fresh press — fire immediately
                    self._fire(btn)
                    self._held_button = btn
                    self._held_time_ms = 0
                elif is_pressed and was_pressed and self._held_button == btn:
                    # Held — handle repeat
                    self._held_time_ms += _GAMEPAD_POLL_MS
                    if self._held_time_ms >= _GAMEPAD_REPEAT_DELAY_MS:
                        if (self._held_time_ms - _GAMEPAD_REPEAT_DELAY_MS) % _GAMEPAD_REPEAT_RATE_MS < _GAMEPAD_POLL_MS:
                            self._fire(btn)
                elif not is_pressed and was_pressed and self._held_button == btn:
                    # Released
                    self._held_button = None
                    self._held_time_ms = 0

            self._prev_buttons = buttons

        except Exception:
            pass

    def _fire(self, btn):
        cb = self._callbacks.get(btn)
        if cb:
            cb()


# ── audio (background music) ─────────────────────────────────────────────

LAUNCHER_VOLUME_MULT = 0.5
FADEOUT_MS           = 1000


def _pygame_available():
    try:
        import pygame  # noqa: F401
        return True
    except ImportError:
        return False


def _audio_volume() -> float:
    try:
        data = _load_deckops_config()
        return data.get("music_volume", 0.4) * LAUNCHER_VOLUME_MULT
    except Exception:
        return 0.2


def _audio_enabled() -> bool:
    try:
        data = _load_deckops_config()
        return data.get("music_enabled", True)
    except Exception:
        return True


def _start_audio():
    if not _audio_enabled() or not _pygame_available():
        return
    if not os.path.exists(MUSIC_PATH):
        return
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        if not pygame.mixer.music.get_busy():
            pygame.mixer.music.load(MUSIC_PATH)
            pygame.mixer.music.set_volume(_audio_volume())
            pygame.mixer.music.play(-1)
    except Exception:
        pass


def _fadeout_audio(ms: int = FADEOUT_MS):
    if not _pygame_available():
        return
    try:
        import pygame
        if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
            pygame.mixer.music.fadeout(ms)
    except Exception:
        pass


# ── config helpers ────────────────────────────────────────────────────────

def _load_deckops_config() -> dict:
    """Load deckops.json from the Linux filesystem via Z: drive."""
    if not os.path.exists(_DECKOPS_JSON):
        return {}
    try:
        with open(_DECKOPS_JSON, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _load_plut_config() -> dict:
    """Load Plutonium config.json — merges across all prefixes on OLED / Other.

    LCD: single config.json from the Heroic shared prefix.
    OLED / Other: each per-game prefix has its own config.json with only that
    game's path populated. This function merges all of them so every
    installed game's path is available.
    """
    try:
        with open(_DECKOPS_JSON, "r") as f:
            deckops_cfg = json.load(f)
    except Exception:
        deckops_cfg = {}

    model = deckops_cfg.get("deck_model", "oled")

    if model == "lcd":
        # LCD: single config from Heroic shared prefix
        config_path = os.path.join(_PLUT_DIR, "config.json")
        if not os.path.exists(config_path):
            return {}
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    # OLED / Other: merge config.json from all prefixes
    merged = {}
    path_keys = ("t4Path", "t5Path", "t6Path", "iw5Path")

    for plut_dir in _find_all_plut_dirs():
        config_path = os.path.join(plut_dir, "config.json")
        try:
            with open(config_path, "r") as f:
                cfg = json.load(f)
            for key in path_keys:
                val = cfg.get(key, "")
                if val and not merged.get(key):
                    merged[key] = val
        except (json.JSONDecodeError, IOError):
            continue

    return merged


# ── launch helper ────────────────────────────────────────────────────────

_LAUNCH_FIRED = False
_LAUNCH_DEBOUNCE_MS = 3000


def _launch_lan(game_key: str, game_dir_wine: str, player_name: str):
    """Launch the Plutonium bootstrapper in LAN mode.

    This is a direct Windows-to-Windows process call inside the same
    Proton prefix. No bash, no second Proton instance, no environment
    stripping needed.

    On OLED, resolves the correct per-game prefix so the bootstrapper
    runs from the same prefix that Steam/Proton initialized for that
    game, with matching DLLs and Proton state.
    """
    global _LAUNCH_FIRED
    if _LAUNCH_FIRED:
        return
    _LAUNCH_FIRED = True

    _fadeout_audio()

    plut_dir, bootstrapper = _resolve_game_plut_dir(game_key)

    try:
        subprocess.Popen(
            [
                bootstrapper,
                _plut_key(game_key),
                game_dir_wine,
                "+name", player_name,
                "-lan",
            ],
            cwd=plut_dir,
        )
    except Exception:
        pass

    # Quit the launcher after a short delay to let the game take over
    def _clear():
        global _LAUNCH_FIRED
        _LAUNCH_FIRED = False
    QTimer.singleShot(_LAUNCH_DEBOUNCE_MS, _clear)

    QTimer.singleShot(1500, lambda: QApplication.instance().quit())


# ── helpers ──────────────────────────────────────────────────────────────────

def _hero_path(hero_file: str) -> str:
    return os.path.join(HEROES_DIR, hero_file)


def _get_setup_plut_keys() -> dict:
    """
    Return Plutonium game keys that have been set up, with their
    game directory paths for direct bootstrapper launching.

    Reads deckops.json for which games are installed, and Plutonium's
    config.json for the Wine game directory paths.

    Returns dict — {game_key: {"game_dir": str, "player_name": str}}
    """
    try:
        deckops = _load_deckops_config()
        plut_cfg = _load_plut_config()

        setup_games = deckops.get("setup_games", {})
        player_name = deckops.get("player_name") or "Player"

        # Map game key prefixes to Plutonium config.json path keys
        _cfg_keys = {
            "t4": "t4Path",
            "t5": "t5Path",
            "t6": "t6Path",
            "iw5": "iw5Path",
        }

        result = {}
        for k, v in setup_games.items():
            if v.get("client") != "plutonium":
                continue

            # Derive the config key from the game key prefix
            # t4sp -> t4, t5mp -> t5, t6zm -> t6, iw5mp -> iw5
            prefix = k[:3] if k.startswith("iw") else k[:2]
            cfg_key = _cfg_keys.get(prefix, "")
            game_dir = plut_cfg.get(cfg_key, "")

            if game_dir:
                result[k] = {
                    "game_dir": game_dir,
                    "player_name": player_name,
                }

        return result
    except Exception:
        return {}


# ── widgets ──────────────────────────────────────────────────────────────────

class GameRow(QWidget):
    """
    A fixed-height row with a hero background image, dark overlay,
    game title, and mode launch buttons.
    """

    def __init__(self, game_def: dict, setup_info: dict, parent=None):
        super().__init__(parent)
        self._game_def = game_def
        self._bg_pixmap = None
        self._color = C_IW if game_def["dev"] == "iw" else C_TREY

        self._available = [
            (key, label) for key, label in game_def["modes"]
            if key in setup_info
        ]
        self._has_modes = len(self._available) > 0

        self._row_focused = False
        self._mode_buttons = []
        self._focused_btn_idx = None

        self.setFixedHeight(ROW_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        cached = _hero_path(game_def["hero_file"])
        if os.path.exists(cached):
            self._bg_pixmap = QPixmap(cached)
        else:
            threading.Thread(target=self._fetch_hero, daemon=True).start()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(4)

        title = QLabel(game_def["base"])
        title.setFont(_font(16, bold=True))
        title.setStyleSheet("color:#FFF;background:transparent;")
        left.addWidget(title)

        badge = QLabel("LAN MODE")
        badge.setFont(_font(9, bold=True))
        badge.setFixedHeight(20)
        badge.setFixedWidth(90)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"background:{self._color};color:#FFF;border:none;"
            f"border-radius:4px;"
        )
        left.addWidget(badge)

        lay.addLayout(left)
        lay.addStretch()

        if self._has_modes:
            for key, label in self._available:
                info = setup_info[key]
                game_dir = info.get("game_dir", "")
                player_name = info.get("player_name", "Player")
                has_game = bool(game_dir)

                btn = QPushButton(label)
                btn.setFont(_font(14, bold=True))
                btn.setFixedSize(120, 52)
                btn.setFocusPolicy(Qt.NoFocus)

                if has_game:
                    self._apply_btn_style(btn, focused=False)
                    btn.clicked.connect(
                        lambda checked=False, k=key, d=game_dir,
                               n=player_name: _launch_lan(k, d, n)
                    )
                    self._mode_buttons.append((btn, key))
                else:
                    btn.setStyleSheet(
                        f"QPushButton{{background:{C_DARK_BTN};color:{C_DIM};"
                        f"border:none;border-radius:8px;}}"
                    )
                    btn.setEnabled(False)
                    btn.setToolTip("Game path not found in config")

                lay.addWidget(btn, alignment=Qt.AlignVCenter)
        else:
            no_lbl = QLabel("Not installed")
            no_lbl.setFont(_font(13))
            no_lbl.setStyleSheet(f"color:{C_DIM};background:transparent;")
            lay.addWidget(no_lbl, alignment=Qt.AlignVCenter)

    def _apply_btn_style(self, btn: QPushButton, focused: bool):
        if focused:
            btn.setStyleSheet(
                f"QPushButton{{background:{self._color};color:#FFF;"
                f"border:3px solid #FFFFFF;border-radius:8px;}}"
                f"QPushButton:pressed{{background:{self._color}99;}}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton{{background:{self._color};color:#FFF;"
                f"border:none;border-radius:8px;}}"
                f"QPushButton:hover{{background:{self._color}CC;}}"
                f"QPushButton:pressed{{background:{self._color}99;}}"
            )

    def launchable_count(self) -> int:
        return len(self._mode_buttons)

    def trigger_focused_button(self):
        if self._focused_btn_idx is None:
            return
        if 0 <= self._focused_btn_idx < len(self._mode_buttons):
            btn, _ = self._mode_buttons[self._focused_btn_idx]
            btn.click()

    def set_row_focused(self, focused: bool):
        if self._row_focused == focused:
            return
        self._row_focused = focused
        if not focused:
            self.set_focused_button(None)
        self.update()

    def set_focused_button(self, idx):
        if self._focused_btn_idx == idx:
            return
        if self._focused_btn_idx is not None and \
                0 <= self._focused_btn_idx < len(self._mode_buttons):
            old_btn, _ = self._mode_buttons[self._focused_btn_idx]
            self._apply_btn_style(old_btn, focused=False)
        self._focused_btn_idx = idx
        if idx is not None and 0 <= idx < len(self._mode_buttons):
            new_btn, _ = self._mode_buttons[idx]
            self._apply_btn_style(new_btn, focused=True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()

        painter.fillRect(rect, QColor(C_CARD))

        if self._bg_pixmap and not self._bg_pixmap.isNull():
            pw = self._bg_pixmap.width()
            ph = self._bg_pixmap.height()
            rw = rect.width()
            rh = rect.height()

            scale = rw / pw
            src_h_needed = int(rh / scale)
            src_y = max(0, (ph - src_h_needed) // 2)
            src_rect = QRect(0, src_y, pw, min(src_h_needed, ph))

            painter.drawPixmap(rect, self._bg_pixmap, src_rect)

        if not self._has_modes:
            painter.fillRect(rect, QColor(0, 0, 0, int(255 * 0.85)))

        painter.fillRect(QRect(0, 0, 3, rect.height()), QColor(self._color))

        if self._row_focused:
            border = 4
            c = QColor(self._color)
            painter.fillRect(QRect(0, 0, rect.width(), border), c)
            painter.fillRect(QRect(0, rect.height() - border,
                                    rect.width(), border), c)
            painter.fillRect(QRect(0, 0, border, rect.height()), c)
            painter.fillRect(QRect(rect.width() - border, 0,
                                    border, rect.height()), c)

        painter.end()
        super().paintEvent(event)

    def _fetch_hero(self):
        url = self._game_def.get("hero_url")
        if not url:
            return
        try:
            dest = _hero_path(self._game_def["hero_file"])
            urllib.request.urlretrieve(url, dest)
            pix = QPixmap(dest)
            if not pix.isNull():
                self._bg_pixmap = pix
                QTimer.singleShot(0, self.update)
        except Exception:
            pass


class LauncherWindow(QWidget):
    """Main fullscreen launcher window — fits 1280x800 with no scrolling."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DeckOps Offline")
        self.setStyleSheet(f"background:{C_BG};")

        setup_info = _get_setup_plut_keys()

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # ── header bar ──
        hdr = QWidget()
        hdr.setFixedHeight(HEADER_H)
        hdr.setStyleSheet(f"background:{C_CARD};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)

        title = QLabel("DECKOPS")
        title.setFont(_font(20, bold=True))
        title.setStyleSheet(f"color:{C_TREY};background:transparent;")
        hl.addWidget(title)

        subtitle = QLabel("OFFLINE")
        subtitle.setFont(_font(12))
        subtitle.setStyleSheet(f"color:{C_DIM};background:transparent;")
        subtitle.setContentsMargins(8, 4, 0, 0)
        hl.addWidget(subtitle)
        hl.addStretch()

        quit_btn = QPushButton("\u2715")
        quit_btn.setFont(_font(16, bold=True))
        quit_btn.setFixedSize(44, 44)
        quit_btn.setFocusPolicy(Qt.NoFocus)
        quit_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C_DIM};border:none;"
            f"border-radius:8px;}}"
            f"QPushButton:hover{{background:{C_DARK_BTN};color:#FFF;}}"
        )
        quit_btn.clicked.connect(self._quit_with_fade)
        hl.addWidget(quit_btn)
        root_lay.addWidget(hdr)

        # ── game rows ──
        rows_container = QWidget()
        rows_container.setStyleSheet(f"background:{C_BG};")
        rows_lay = QVBoxLayout(rows_container)
        rows_lay.setContentsMargins(PAD_X, PAD_Y, PAD_X, PAD_Y)
        rows_lay.setSpacing(ROW_GAP)

        installed = []
        uninstalled = []
        for game_def in PLUT_GAMES:
            has_any = any(k in setup_info for k, _ in game_def["modes"])
            row = GameRow(game_def, setup_info)
            if has_any:
                installed.append(row)
            else:
                uninstalled.append(row)

        for row in installed:
            rows_lay.addWidget(row)
        for row in uninstalled:
            rows_lay.addWidget(row)

        rows_lay.addStretch()
        root_lay.addWidget(rows_container)

        if not setup_info:
            empty = QLabel(
                "No Plutonium games installed.\n"
                "Run the DeckOps installer first."
            )
            empty.setFont(_font(14))
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color:{C_DIM};background:transparent;")
            rows_lay.insertWidget(0, empty)

        # ── keyboard focus tracking ──
        self._focus_rows = [r for r in installed if r.launchable_count() > 0]
        self._row_idx = 0
        if self._focus_rows:
            self._focus_rows[0].set_row_focused(True)
            self._focus_rows[0].set_focused_button(0)

        self.setFocusPolicy(Qt.StrongFocus)

        # ── XInput gamepad ──
        self._gamepad = GamepadPoller(
            on_up=lambda: self.on_move_row(-1),
            on_down=lambda: self.on_move_row(+1),
            on_left=lambda: self.on_move_btn(-1),
            on_right=lambda: self.on_move_btn(+1),
            on_activate=self._activate_focused,
            on_back=self._quit_with_fade,
        )
        self._gamepad.start()

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key_Escape:
            self._quit_with_fade()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._activate_focused()
            return
        if key == Qt.Key_Up:
            self.on_move_row(-1)
            return
        if key == Qt.Key_Down:
            self.on_move_row(+1)
            return
        if key == Qt.Key_Left:
            self.on_move_btn(-1)
            return
        if key == Qt.Key_Right:
            self.on_move_btn(+1)
            return

        super().keyPressEvent(event)

    @pyqtSlot(int)
    def on_move_row(self, delta: int):
        if not self._focus_rows:
            return
        new_idx = max(0, min(len(self._focus_rows) - 1, self._row_idx + delta))
        if new_idx == self._row_idx:
            return
        self._focus_rows[self._row_idx].set_row_focused(False)
        self._row_idx = new_idx
        self._focus_rows[self._row_idx].set_row_focused(True)
        self._focus_rows[self._row_idx].set_focused_button(0)

    @pyqtSlot(int)
    def on_move_btn(self, delta: int):
        if not self._focus_rows:
            return
        row = self._focus_rows[self._row_idx]
        n = row.launchable_count()
        if n == 0:
            return
        cur = row._focused_btn_idx if row._focused_btn_idx is not None else 0
        new_idx = max(0, min(n - 1, cur + delta))
        row.set_focused_button(new_idx)

    @pyqtSlot()
    def _activate_focused(self):
        if not self._focus_rows:
            return
        self._focus_rows[self._row_idx].trigger_focused_button()

    @pyqtSlot()
    def _quit_with_fade(self):
        _fadeout_audio()
        QTimer.singleShot(FADEOUT_MS, QApplication.instance().quit)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    _load_font()

    win = LauncherWindow()
    win.showFullScreen()
    win.activateWindow()
    win.raise_()
    win.setFocus()
    _start_audio()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
