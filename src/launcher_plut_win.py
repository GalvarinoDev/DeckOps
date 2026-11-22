#!/usr/bin/env python3
"""
launcher_plut_win.py - Offline LAN launcher for Plutonium on Steam Deck
(Windows .exe version, runs inside Proton)

A small PyQt5 app that lists the installed Plutonium games and lets the
user pick a mode (MP, S/Z, ZM, DS) to launch in offline LAN mode. It is
a Windows executable built with PyInstaller and runs under GE-Proton as
a non-Steam shortcut in Game Mode.

Picking a mode writes an intent file (.lan_intent.json) and exits. The
wrapper script (launcher_offline.sh) reads it and execs the game's -lan
wrapper, which runs the game in its own Proton prefix. Every device uses
this flow.

Every launch attempt is logged to .lan_launch.log on the Linux filesystem.

Flow:
  1. Read deckops.json (through the Wine Z: drive) for the installed
     Plutonium games and each game's stored lan_wrapper_path.
  2. Show compact game rows with hero background art and mode buttons.
  3. When the user taps a mode, the exe writes the intent file and the
     wrapper script takes over.

Gamepad input: Steam Deck Game Mode maps the D-pad to arrow keys and A/B
to Return/Escape, so Qt gets them as keyPressEvents. evdev is not
available inside Wine, but the keyboard mapping works the same.
"""

import os
import sys
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

# --- Paths
# Inside Wine/Proton, Z: maps to the Linux root filesystem.
# Every path comes from the exe location, so any Linux username works,
# not only "deck". The exe lives at:
#   ~/<INSTALL_DIR_NAME>/assets/LAN/DeckOps_Offline.exe
# so four parents up is the Linux home directory on Z:.

# --- Branch identity (copy of identity.py, keep in sync)
_BRANCH = "stable"  # "nightly" or "stable"; only used when the exe is not in an install dir


def _exe_install_dir_name() -> str:
    """Name of the install dir the exe sits in (<dir>/assets/LAN/DeckOps_Offline.exe).

    One exe then serves Stable and Nightly, so a branch port needs no rebuild.
    """
    try:
        name = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(sys.executable)))))
        if name in ("DeckOps", "DeckOps-Nightly"):
            return name
    except Exception:
        pass
    return "DeckOps-Nightly" if _BRANCH == "nightly" else "DeckOps"


_INSTALL_DIR_NAME = _exe_install_dir_name()
_GITHUB_USER = "GalvarinoDev"
_GITHUB_REPO = _INSTALL_DIR_NAME  # repo and install dir share a name on both branches
_GITHUB_RAW = f"https://raw.githubusercontent.com/{_GITHUB_USER}/{_GITHUB_REPO}/refs/heads/main"


def _detect_linux_home() -> str:
    """Find the Linux home directory (as a Wine Z: path) from the exe location.

    PyInstaller sets sys.executable to the .exe path:
        Z:\\home\\<user>\\<INSTALL_DIR_NAME>\\assets\\LAN\\DeckOps_Offline.exe

    Four parents up (LAN -> assets -> <INSTALL_DIR_NAME> -> home dir) is
    Z:\\home\\<user>.

    Falls back to Z:\\home\\deck if that fails.
    """
    try:
        exe = os.path.abspath(sys.executable)
        # exe  = .../<INSTALL_DIR_NAME>/assets/LAN/DeckOps_Offline.exe
        # Four levels up: exe -> LAN -> assets -> <INSTALL_DIR_NAME> -> home
        home = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(exe)
        )))
        # The install dir must exist one level down, or the guess is wrong
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

# The exe writes the intent file when the user picks a game.
# launcher_offline.sh reads it after the exe exits and execs the
# per-game LAN wrapper script. All Deck models use it.
_INTENT_FILE = os.path.join(_LINUX_PROJECT_ROOT, ".lan_intent.json")
# The launcher's own settings (music mute). deckops.json is only read here.
_SETTINGS_FILE = os.path.join(_LINUX_PROJECT_ROOT, ".lan_launcher.json")

# Launch log (Linux filesystem, through Z:). Written before and after
# every launch attempt, so a failed launch leaves a trace.
_LAN_LOG = os.path.join(_LINUX_PROJECT_ROOT, ".lan_launch.log")


def _lan_log(msg: str):
    """Append a line to the launch diagnostics log. Never raises."""
    try:
        import datetime
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(_LAN_LOG, "a") as f:
            f.write(f"[{stamp}] {msg}\n")
    except Exception:
        pass

# Assets
FONTS_DIR  = os.path.join(_LINUX_PROJECT_ROOT, "assets", "fonts")
HEROES_DIR = os.path.join(_LINUX_PROJECT_ROOT, "assets", "images", "heroes")
MUSIC_PATH = os.path.join(_LINUX_PROJECT_ROOT, "assets", "music",
                           "background.mp3")


# --- Colors (same as DeckOps ui_qt.py)

C_BG       = "#141416"
C_CARD     = "#1E1E26"
C_IW       = "#6DC62B"
C_TREY     = "#F47B20"
C_DIM      = "#888899"
C_DARK_BTN = "#33333F"

# --- Layout for 1280x800

HEADER_H = 52
ROW_H    = 160
ROW_GAP  = 10
PAD_X    = 16
PAD_Y    = 12

# --- Font

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

# --- Plutonium games

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


# --- XInput gamepad polling
# XInput-Python reads the Steam Deck's gamepad inside Wine/Proton.
# In Game Mode the Deck shows up as an XInput controller.
# A QTimer does the polling, so no thread is needed.

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
    BTN_Y      = 0x8000

    NAV_BUTTONS = (DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT, BTN_A, BTN_B)

    def __init__(self, on_up, on_down, on_left, on_right, on_activate, on_back, on_mute=None):
        self._callbacks = {
            self.DPAD_UP:    on_up,
            self.DPAD_DOWN:  on_down,
            self.DPAD_LEFT:  on_left,
            self.DPAD_RIGHT: on_right,
            self.BTN_A:      on_activate,
            self.BTN_B:      on_back,
            self.BTN_Y:      on_mute,
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
                    # New press, fire at once
                    self._fire(btn)
                    self._held_button = btn
                    self._held_time_ms = 0
                elif is_pressed and was_pressed and self._held_button == btn:
                    # Held, repeat after the delay
                    self._held_time_ms += _GAMEPAD_POLL_MS
                    if self._held_time_ms >= _GAMEPAD_REPEAT_DELAY_MS:
                        if (self._held_time_ms - _GAMEPAD_REPEAT_DELAY_MS) % _GAMEPAD_REPEAT_RATE_MS < _GAMEPAD_POLL_MS:
                            self._fire(btn)
                elif not is_pressed and was_pressed and self._held_button == btn:
                    # Released
                    self._held_button = None
                    self._held_time_ms = 0

            # Y toggles, so it never repeats while held
            if buttons & self.BTN_Y and not self._prev_buttons & self.BTN_Y:
                self._fire(self.BTN_Y)

            self._prev_buttons = buttons

        except Exception:
            pass

    def _fire(self, btn):
        cb = self._callbacks.get(btn)
        if cb:
            cb()


# --- Background music

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


def _music_muted() -> bool:
    """The launcher's saved choice; until there is one, start muted if DeckOps' music is off."""
    try:
        with open(_SETTINGS_FILE) as f:
            return bool(json.load(f)["music_muted"])
    except Exception:
        pass
    try:
        return not _load_deckops_config().get("music_enabled", True)
    except Exception:
        return False


def _set_music_muted(muted: bool):
    try:
        with open(_SETTINGS_FILE, "w") as f:
            json.dump({"music_muted": muted}, f)
    except Exception:
        pass


def _start_audio():
    if _music_muted() or not _pygame_available():
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


# --- Config

def _load_deckops_config() -> dict:
    """Load deckops.json from the Linux filesystem through the Z: drive."""
    if not os.path.exists(_DECKOPS_JSON):
        return {}
    try:
        with open(_DECKOPS_JSON, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}



# --- Launch

_LAUNCH_FIRED = False

# LauncherWindow sets this. It swaps the game list for the "Starting ..." message
_ON_LAUNCH = None
_LAUNCH_MESSAGE_MS = 3000


def _launch_lan_lcd(lan_wrapper_path: str, title: str = ""):
    """Write a launch intent file and exit.

    launcher_offline.sh reads the intent after this exe exits and execs
    the per-game LAN wrapper script. The LAN wrapper runs the Plutonium
    bootstrapper with -lan inside the game's own Proton prefix, so each
    game gets a fully set up Wine environment with the right DLLs and
    DXVK state.

    All Deck models use it (OLED, LCD, Other). The name keeps "lcd" for
    backward compatibility with any external callers.
    """
    global _LAUNCH_FIRED
    if _LAUNCH_FIRED:
        return
    _LAUNCH_FIRED = True

    _fadeout_audio()
    _lan_log(f"Intent write: {lan_wrapper_path}")

    try:
        intent = {"lan_wrapper_path": lan_wrapper_path}
        with open(_INTENT_FILE, "w") as f:
            json.dump(intent, f)
    except Exception as ex:
        _lan_log(f"Intent write FAILED: {ex}")

    if _ON_LAUNCH:
        _ON_LAUNCH(title)
    QTimer.singleShot(_LAUNCH_MESSAGE_MS if _ON_LAUNCH else 500, lambda: QApplication.instance().quit())


def _dispatch_launch(info: dict, title: str = ""):
    """Write a launch intent and exit. launcher_offline.sh reads the
    intent after this exe exits and execs the per-game LAN wrapper
    script, which starts the game in its own Proton prefix.

    All Deck models (OLED, LCD, Other) use this flow. The per-game LAN
    wrapper picks the prefix, so the launcher exe never runs game code
    inside its own Wine environment.
    """
    lan_path = info.get("lan_wrapper_path", "")
    if lan_path:
        _launch_lan_lcd(lan_path, title)
    else:
        _lan_log(f"Launch skipped: no lan_wrapper_path in {info!r}")


# --- Helpers

def _hero_path(hero_file: str) -> str:
    return os.path.join(HEROES_DIR, hero_file)


def _get_setup_plut_keys() -> dict:
    """
    Return the Plutonium game keys that are set up, with the data each
    launch path needs.

    All models use the intent-file bridge: the exe writes
    .lan_intent.json with the lan_wrapper_path and exits.
    launcher_offline.sh reads the intent and execs the per-game LAN
    wrapper script, which runs the bootstrapper in that game's Proton
    prefix.

    Returns {game_key: {...}}. A game is included only if its
    lan_wrapper_path exists on disk.
    """
    try:
        deckops     = _load_deckops_config()
        setup_games = deckops.get("setup_games", {})

        result = {}
        for k, v in setup_games.items():
            if v.get("client") != "plutonium":
                continue
            lan_path = v.get("lan_wrapper_path")
            if lan_path and os.path.exists(lan_path):
                result[k] = {"lan_wrapper_path": lan_path}
        return result
    except Exception:
        return {}


# --- Widgets

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
                # A game is launchable if its info dict has what its
                # model's launch path needs. _get_setup_plut_keys only
                # returns games that pass that check, so being in
                # setup_info is enough.
                launchable = bool(info)

                btn = QPushButton(label)
                btn.setFont(_font(14, bold=True))
                btn.setFixedSize(120, 52)
                btn.setFocusPolicy(Qt.NoFocus)

                if launchable:
                    self._apply_btn_style(btn, focused=False)
                    btn.clicked.connect(
                        lambda checked=False, i=info, t=f"{game_def['base']} ({label})": _dispatch_launch(i, t)
                    )
                    self._mode_buttons.append((btn, key))
                else:
                    btn.setStyleSheet(
                        f"QPushButton{{background:{C_DARK_BTN};color:{C_DIM};"
                        f"border:none;border-radius:8px;}}"
                    )
                    btn.setEnabled(False)
                    btn.setToolTip("Not available")

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
    """Fullscreen launcher window. Fits 1280x800 with no scrolling."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DeckOps Offline")
        self.setStyleSheet(f"background:{C_BG};")

        setup_info = _get_setup_plut_keys()

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # --- Header bar
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

        self._music_btn = QPushButton()
        self._music_btn.setFont(_font(11, bold=True))
        self._music_btn.setFixedHeight(36)
        self._music_btn.setFocusPolicy(Qt.NoFocus)
        self._music_btn.setStyleSheet(
            f"QPushButton{{background:{C_DARK_BTN};color:#FFF;border:none;"
            f"border-radius:8px;padding:0 12px;}}"
            f"QPushButton:hover{{background:{C_DIM};}}"
        )
        self._music_btn.clicked.connect(self._toggle_music)
        self._update_music_btn()
        hl.addWidget(self._music_btn)

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

        # --- Game rows
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
        self._rows_container = rows_container

        self._starting = QLabel()
        self._starting.setAlignment(Qt.AlignCenter)
        self._starting.setWordWrap(True)
        self._starting.setStyleSheet(f"color:#FFF;background:{C_BG};")
        self._starting.hide()
        root_lay.addWidget(self._starting, 1)
        global _ON_LAUNCH
        _ON_LAUNCH = self._show_starting

        if not setup_info:
            empty = QLabel(
                "No Plutonium games installed.\n"
                "Run the DeckOps installer first."
            )
            empty.setFont(_font(14))
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color:{C_DIM};background:transparent;")
            rows_lay.insertWidget(0, empty)

        # --- Keyboard focus
        self._focus_rows = [r for r in installed if r.launchable_count() > 0]
        self._row_idx = 0
        if self._focus_rows:
            self._focus_rows[0].set_row_focused(True)
            self._focus_rows[0].set_focused_button(0)

        self.setFocusPolicy(Qt.StrongFocus)

        # --- XInput gamepad
        self._gamepad = GamepadPoller(
            on_up=lambda: self.on_move_row(-1),
            on_down=lambda: self.on_move_row(+1),
            on_left=lambda: self.on_move_btn(-1),
            on_right=lambda: self.on_move_btn(+1),
            on_activate=self._activate_focused,
            on_back=self._quit_with_fade,
            on_mute=self._toggle_music,
        )
        self._gamepad.start()

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key_Escape:
            self._quit_with_fade()
            return
        if key == Qt.Key_M:
            self._toggle_music()
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

    def _update_music_btn(self):
        self._music_btn.setText("Y  MUSIC OFF" if _music_muted() else "Y  MUSIC ON")

    @pyqtSlot()
    def _toggle_music(self):
        muted = not _music_muted()
        _set_music_muted(muted)
        if muted:
            _fadeout_audio(300)
        else:
            _start_audio()
        self._update_music_btn()

    def _show_starting(self, title: str):
        self._gamepad.stop()
        self._rows_container.hide()
        self._starting.setText(
            f"<div style='font-size:22pt;font-weight:bold'>Starting {title}...</div>"
            f"<div style='font-size:13pt;color:{C_DIM};margin-top:14px'>"
            f"The screen may stay black for up to a minute while the game starts. This is normal.</div>")
        self._starting.show()

    @pyqtSlot()
    def _quit_with_fade(self):
        _fadeout_audio()
        QTimer.singleShot(FADEOUT_MS, QApplication.instance().quit)


# --- Main

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
