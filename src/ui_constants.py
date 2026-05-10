"""
ui_constants.py — Shared constants, helpers, and game definitions for DeckOps UI

Extracted from ui_qt.py so that ui_setup.py, ui_install.py, ui_manage.py,
and ui_qt.py can all import from a single source without circular deps.
"""

import os

from PyQt5.QtWidgets import (
    QLabel, QPushButton, QFrame, QHBoxLayout, QVBoxLayout, QMessageBox,
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QFontDatabase

import config as cfg
from identity import BUILD_BADGE
from log import get_logger

_log = get_logger(__name__)


# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR    = os.path.join(PROJECT_ROOT, "assets", "fonts")
HEADERS_DIR  = os.path.join(PROJECT_ROOT, "assets", "images", "headers")
HEROES_DIR   = os.path.join(PROJECT_ROOT, "assets", "images", "heroes")
MUSIC_PATH   = os.path.join(PROJECT_ROOT, "assets", "music", "background.mp3")
LOG_DIR      = os.path.join(PROJECT_ROOT, "logs")
LOG_PATH     = os.path.join(LOG_DIR, "install.log")

os.makedirs(HEADERS_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


# ── Logging ───────────────────────────────────────────────────────────────────

def _log_to_file(text: str):
    """Append a line to the install log via the logging framework.

    Kept as a thin bridge so existing callers in ui_install.py and
    ui_manage.py continue to work without changes.
    """
    _log.info(text)


# ── Colors ────────────────────────────────────────────────────────────────────

C_BG       = "#141416"
C_CARD     = "#1E1E26"
C_IW       = "#6DC62B"
C_TREY     = "#F47B20"
C_DIM      = "#888899"
C_DARK_BTN = "#33333F"
C_RED_BTN  = "#7A1515"
C_BLUE_BTN = "#1A5FAA"


# ── Fonts ─────────────────────────────────────────────────────────────────────

_FONT_FAMILY      = "Sans Serif"
_FONT_FAMILY_DISP = "Sans Serif"
_FONT_LOADED      = False

def _load_font():
    global _FONT_FAMILY, _FONT_FAMILY_DISP, _FONT_LOADED
    if _FONT_LOADED:
        return
    russo = os.path.join(FONTS_DIR, "RussoOne-Regular.ttf")
    if not os.path.exists(russo):
        raise FileNotFoundError(
            f"Required font not found: {russo}\n"
            f"Ensure assets/fonts/RussoOne-Regular.ttf is present in the repo."
        )
    fid = QFontDatabase.addApplicationFont(russo)
    fams = QFontDatabase.applicationFontFamilies(fid)
    if fams:
        _FONT_FAMILY      = fams[0]
        _FONT_FAMILY_DISP = fams[0]
    _FONT_LOADED = True

def font(size=13, bold=False, weight=None, display=False):
    family = _FONT_FAMILY_DISP if display else _FONT_FAMILY
    f = QFont(family, size)
    if weight is not None:
        f.setWeight(weight)
    else:
        f.setBold(bold)
    return f


# ── Game card definitions ─────────────────────────────────────────────────────
#
# Each entry is one card in the UI. Always 6 cards, but what each card shows
# depends on the Deck model. OLED and Other users get the full key list. LCD
# users get a reduced set via the lcd_* overrides:
#
#   lcd_keys   — which game keys this card includes on LCD (empty = card hidden)
#   lcd_client — client badge label on LCD (e.g. "steam" instead of "plutonium")
#   lcd_appid  — appid used for the header image and Steam store link on LCD
#
# If an lcd_* field is missing, the card uses the default (OLED) value.
# The _active_keys(), _active_client(), _active_appid() helpers below
# resolve the correct value based on the user's saved deck_model config.

ALL_GAMES = [
    # ── Row 1: Infinity Ward (green) ─────────────────────────────────────
    {"base":"Call of Duty 4: Modern Warfare","keys":["cod4mp","cod4sp"],"appid":7940,"dev":"iw","client":"cod4x + iw3sp",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: Modern Warfare 2","keys":["iw4mp","iw4sp"],"appid":10190,"dev":"iw","client":"iw4x",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: Modern Warfare 3","keys":["iw5mp","iw5sp","iw5mp_ds"],"appid":42690,"dev":"iw","client":"plutonium",
     "lcd_keys":["iw5mp","iw5sp","iw5mp_ds"],"lcd_client":"plutonium + steam","lcd_appid":42680,
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: Ghosts","keys":["iw6mp","iw6sp"],"appid":209160,"dev":"iw","client":"alterware",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: Advanced Warfare","keys":["s1mp","s1sp"],"appid":209650,"dev":"iw","client":"alterware",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    # ── Row 2: Treyarch (orange) ─────────────────────────────────────────
    {"base":"Call of Duty: World at War","keys":["t4mp","t4sp"],"appid":10090,"dev":"trey","client":"plutonium",
     "lcd_keys":["t4mp","t4sp"],"lcd_client":"plutonium",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: Black Ops","keys":["t5mp","t5sp"],"appid":42700,"dev":"trey","client":"plutonium",
     "lcd_keys":["t5mp","t5sp"],"lcd_client":"plutonium",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: Black Ops II","keys":["t6mp","t6sp","t6zm"],"appid":202990,"dev":"trey","client":"plutonium + t6sp-mod",
     "lcd_keys":["t6mp","t6sp","t6zm"],"lcd_client":"plutonium + t6sp-mod","lcd_appid":202970,
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: Black Ops III","keys":["t7"],"appid":311210,"dev":"trey","client":"cleanops + t7x",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"DeckOps: Plutonium Offline","keys":[],"appid":None,"dev":"trey","client":"lan",
     "launch_note":"Re-adds the Plutonium offline launcher shortcut."},
]

def _active_keys(gd):
    """Return the keys to show for this card based on the user's Deck model."""
    if not cfg.is_lcd():
        return gd["keys"]
    return gd.get("lcd_keys", gd["keys"])

def _active_client(gd):
    """Return the client label for this card based on the user's Deck model."""
    if not cfg.is_lcd():
        return gd["client"]
    return gd.get("lcd_client", gd["client"])

def _active_appid(gd):
    """Return the display appid for this card based on the user's Deck model."""
    if not cfg.is_lcd():
        return gd["appid"]
    return gd.get("lcd_appid", gd["appid"])

KEY_CLIENT = {
    "cod4mp": "cod4x",
    "cod4sp": "iw3sp",
    "iw4mp":  "iw4x",
    "iw4sp":  "steam",
    "iw5mp":    "plutonium",
    "iw5mp_ds": "plutonium",
    "iw5sp":  "steam",
    "t4sp":   "plutonium",
    "t4mp":   "plutonium",
    "t5sp":   "plutonium",
    "t5mp":   "plutonium",
    "t6zm":   "plutonium",
    "t6mp":   "plutonium",
    "t6sp":   "t6sp_mod",
    "t7":     "cleanops",
    "t7x":    "t7x",
    "iw6mp": "alterware",
    "iw6sp": "alterware",
    "s1mp":  "alterware",
    "s1sp":  "alterware",
}

KEY_EXES = {
    "cod4mp":"iw3mp.exe","cod4sp":"iw3sp.exe",
    "iw4mp":"iw4mp.exe","iw4sp":"iw4sp.exe",
    "iw5mp":"iw5mp.exe","iw5mp_ds":"iw5mp_server.exe","iw5sp":"iw5sp.exe",
    "t4sp":"CoDWaW.exe","t4mp":"CoDWaWmp.exe",
    "t5sp":"BlackOps.exe","t5mp":"BlackOpsMP.exe",
    "t6zm":"t6zm.exe","t6mp":"t6mp.exe","t6sp":"t6sp.exe",
    "t7":"BlackOps3.exe",
    "t7x":"t7x.exe",
    "iw6mp":"iw6mp64_ship.exe","iw6sp":"iw6sp64_ship.exe",
    "s1mp":"s1_mp64_ship.exe","s1sp":"s1_sp64_ship.exe",
}

# Label shown beneath each per-key checkbox in SetupScreen.
KEY_MODE_LABEL = {
    "cod4mp": "MP",    "cod4sp": "SP",
    "iw4mp":  "MP",    "iw4sp":  "SP",
    "iw5mp":  "MP",    "iw5mp_ds": "DS",    "iw5sp":  "SP",
    "t4sp":   "S/Z",   "t4mp":   "MP",
    "t5sp":   "S/Z",   "t5mp":   "MP",
    "t6sp":   "SP",    "t6zm":   "ZM",    "t6mp":   "MP",
    "t7":     "All",
    "iw6mp":  "MP",    "iw6sp":  "SP",
    "s1mp":   "MP",    "s1sp":   "SP",
}


SP_IMAGE_URLS = {
    7940:   "https://shared.steamstatic.com/store_item_assets/steam/apps/7940/library_600x900_2x.jpg",
    10180:  "https://shared.steamstatic.com/store_item_assets/steam/apps/10180/library_600x900_2x.jpg",
    10190:  "https://shared.steamstatic.com/store_item_assets/steam/apps/10180/library_600x900_2x.jpg",
    42680:  "https://shared.steamstatic.com/store_item_assets/steam/apps/42680/library_600x900_2x.jpg",
    42690:  "https://shared.steamstatic.com/store_item_assets/steam/apps/42680/library_600x900_2x.jpg",
    10090:  "https://shared.steamstatic.com/store_item_assets/steam/apps/10090/library_600x900_2x.jpg",
    42700:  "https://shared.steamstatic.com/store_item_assets/steam/apps/42700/library_600x900_2x.jpg",
    202970: "https://shared.steamstatic.com/store_item_assets/steam/apps/202970/library_600x900_2x.jpg",
    202990: "https://shared.steamstatic.com/store_item_assets/steam/apps/202970/library_600x900_2x.jpg",
    311210: "https://shared.steamstatic.com/store_item_assets/steam/apps/311210/library_600x900_2x.jpg",
    209160: "https://shared.steamstatic.com/store_item_assets/steam/apps/209160/library_600x900_2x.jpg",
    209650: "https://shared.steamstatic.com/store_item_assets/steam/apps/209650/library_600x900_2x.jpg",
}

IMG_RATIO = 1.5
BTN_RATIO = 0.20
CARD_COLS  = 5
CARD_MAX_W = 187

MUSIC_URL = "https://archive.org/download/adrenaline-klickaud/Adrenaline_KLICKAUD.mp3"


# ── Audio ─────────────────────────────────────────────────────────────────────

_music_volume  = cfg.get_music_volume()
_music_enabled = cfg.get_music_enabled()

def _pygame_available():
    try:
        import pygame
        return True
    except ImportError:
        return False

def _kill_audio():
    if not _pygame_available():
        return
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            pygame.mixer.quit()
    except Exception:
        _log.debug("audio shutdown failed", exc_info=True)

def _start_audio():
    if not _music_enabled or not _pygame_available():
        return
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        if not pygame.mixer.music.get_busy():
            if os.path.exists(MUSIC_PATH):
                pygame.mixer.music.load(MUSIC_PATH)
            else:
                return
            pygame.mixer.music.set_volume(_music_volume)
            pygame.mixer.music.play(-1)
    except Exception:
        _log.debug("audio start failed", exc_info=True)

def _set_audio_volume(vol: float):
    global _music_volume
    _music_volume = vol
    cfg.set_music_volume(vol)
    if not _pygame_available():
        return
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.music.set_volume(vol)
    except Exception:
        _log.debug("audio volume change failed", exc_info=True)

def _set_audio_enabled(enabled: bool):
    global _music_enabled
    _music_enabled = enabled
    cfg.set_music_enabled(enabled)


# ── UI helpers ────────────────────────────────────────────────────────────────

def _header_path(appid: int) -> str:
    return os.path.join(HEADERS_DIR, f"{appid}_grid.jpg")

def _btn(text, color, size=13, h=44):
    b = QPushButton(text); b.setFont(font(size, True)); b.setFixedHeight(h)
    b.setStyleSheet(
        f"QPushButton{{background:{color};color:#FFF;border:none;border-radius:8px;padding:0 18px;}}"
        f"QPushButton:hover{{background:{color}CC;}}"
        f"QPushButton:pressed{{background:{color}99;}}"
        f"QPushButton:disabled{{background:#333344;color:#666677;}}"
    )
    return b

def _lbl(text, size=14, color="#FFF", bold=False, align=Qt.AlignCenter, wrap=True):
    w = QLabel(text); w.setFont(font(size,bold)); w.setAlignment(align)
    w.setWordWrap(wrap); w.setStyleSheet(f"color:{color};background:transparent;")
    return w

def _hdiv():
    d = QFrame(); d.setFrameShape(QFrame.HLine); d.setFixedHeight(1)
    d.setStyleSheet("background:#252530;border:none;"); return d

def _detached_open(args):
    """
    Launch an external command fully detached from DeckOps.

    Double-forks so the resulting process is adopted by PID 1 (init/systemd)
    and has no parent relationship to DeckOps. It will not appear as a child
    or subprocess of DeckOps in any task manager.
    """
    try:
        pid = os.fork()
        if pid == 0:
            # First child — new session, then fork again and exit
            os.setsid()
            pid2 = os.fork()
            if pid2 == 0:
                # Grandchild — close inherited fds and exec
                devnull = os.open(os.devnull, os.O_RDWR)
                os.dup2(devnull, 0)
                os.dup2(devnull, 1)
                os.dup2(devnull, 2)
                os.close(devnull)
                os.execlp(args[0], *args)
            else:
                os._exit(0)
        else:
            # Parent — reap the first child immediately
            os.waitpid(pid, 0)
    except OSError:
        _log.warning("detached_open failed for %s", args, exc_info=True)


# ── Install dialogs ───────────────────────────────────────────────────────────

def _ask_iw4x_dlc(parent, selected) -> bool:
    """
    Show a dialog asking whether to install free IW4x DLC maps.
    Returns True if the user wants DLC, False otherwise.
    Only shows the dialog if iw4x is in the selected games.
    """
    has_iw4x = any(KEY_CLIENT.get(k) == "iw4x" for k, _, _ in selected)
    if not has_iw4x:
        return False
    reply = QMessageBox.question(
        parent,
        "Free DLC Maps",
        "Install free DLC maps for Modern Warfare 2?\n\n"
        "Includes CoD4, MW3, Black Ops, and CoD Online maps.\n"
        "Recommended for joining most servers.\n\n"
        "Download size: ~3 GB",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.Yes,
    )
    return reply == QMessageBox.Yes

def _ask_t7x_install(parent, selected):
    """
    Show a dialog asking whether to install T7X alongside CleanOps.
    Returns True if the user wants T7X, False otherwise.
    Only shows the dialog if BO3 (t7/cleanops) is in the selected games.
    """
    has_bo3 = any(KEY_CLIENT.get(k) == "cleanops" for k, _, _ in selected)
    if not has_bo3:
        return False
    reply = QMessageBox.question(
        parent,
        "T7X — Additional BO3 Client",
        "CleanOps is already included — it patches BO3 to protect against "
        "exploits and adds dedicated servers alongside Activision's official servers.\n\n"
        "T7X is an optional additional client with its own dedicated server list. "
        "Using both is supported but not required.\n\n"
        "If you install both, do the first launch in Desktop Mode:\n"
        "  1. Launch T7X first. Once it loads, close it.\n"
        "  2. Launch BO3 (CleanOps patches). It won't launch after patching — "
        "hit Stop in Steam and relaunch.\n"
        "  3. After this, both work fine in Game Mode.\n\n"
        "If you're unsure, just pick one and skip the other.\n\n"
        "Download size: ~105 MB\n\n"
        "Install T7X?",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.Yes,
    )
    return reply == QMessageBox.Yes


# ── Title block ───────────────────────────────────────────────────────────────

def _title_block(lay, main_size=56):
    t = QLabel("DECKOPS")
    t.setFont(font(main_size, display=True))
    t.setAlignment(Qt.AlignCenter)
    t.setStyleSheet("color:#FFFFFF; background:transparent;")
    lay.addWidget(t)
    sub = QLabel()
    sub.setTextFormat(Qt.RichText)
    sub.setAlignment(Qt.AlignCenter)
    sub.setStyleSheet(f"color:{C_TREY}; background:transparent;")
    sub.setText(
        f'<span style="font-family:\'{_FONT_FAMILY_DISP}\'; font-size:28pt; color:{C_TREY};">'
        f'COMBAT'
        f'<span style="font-size:16pt;">on</span>'
        f'DECK'
        f'</span>'
    )
    lay.addWidget(sub)
    # Build badge — only shown for Nightly builds (None for Stable)
    if BUILD_BADGE:
        badge = QLabel(BUILD_BADGE)
        badge.setFont(font(10, bold=True))
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            "color:#F47B20;background:#2A1A08;border:1px solid #F47B20;"
            "border-radius:4px;padding:2px 10px;"
        )
        bw = QHBoxLayout(); bw.addStretch(); bw.addWidget(badge); bw.addStretch()
        lay.addLayout(bw)


# ── Shared signals ────────────────────────────────────────────────────────────

class _Sigs(QObject):
    progress    = pyqtSignal(int, str)
    log         = pyqtSignal(str)
    done        = pyqtSignal(bool)
    plut_wait   = pyqtSignal()
    plut_go     = pyqtSignal()
    pulse_start = pyqtSignal(str)
    pulse_stop  = pyqtSignal()
    # Manual download fallback: (url, dest_folder, filename, label)
    manual_dl   = pyqtSignal(str, str, str, str)


# ── App stylesheet ────────────────────────────────────────────────────────────

def _app_style():
    return f"""
* {{ font-family: "{_FONT_FAMILY}"; }}
QWidget {{ background-color:{C_BG}; color:#FFF; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background:{C_BG}; border:none; }}
QScrollBar:vertical {{ background:#1E1E28; width:8px; border-radius:4px; }}
QScrollBar::handle:vertical {{ background:#44445A; border-radius:4px; min-height:30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QProgressBar {{ background:#252535; border-radius:7px; border:none; }}
QProgressBar::chunk {{ background:{C_TREY}; border-radius:7px; }}
QCheckBox::indicator {{ width:22px; height:22px; border:2px solid #555568; border-radius:4px; background:#252535; }}
QCheckBox::indicator:checked {{ background:{C_IW}; border-color:{C_IW}; }}
"""


# ── Named screen navigation ──────────────────────────────────────────────────
#
# Replace all hardcoded setCurrentIndex(N) / widget(N) calls with these.
# Each screen sets self.screen_name in __init__; these helpers look it up.

def go_to(stack, name):
    """Navigate to a screen by name. Returns the screen widget."""
    for i in range(stack.count()):
        w = stack.widget(i)
        if getattr(w, "screen_name", w.__class__.__name__) == name:
            stack.setCurrentIndex(i)
            return w
    return None

def get_screen(stack, name):
    """Get a screen widget by name without navigating to it."""
    for i in range(stack.count()):
        w = stack.widget(i)
        if getattr(w, "screen_name", w.__class__.__name__) == name:
            return w
    return None
