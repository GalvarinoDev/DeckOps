"""
ui_qt.py — DeckOps PyQt5 UI
"""

import sys, os, subprocess, threading
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QPushButton, QCheckBox, QProgressBar,
    QFrame, QSizePolicy, QMessageBox, QPlainTextEdit,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QFontDatabase, QPixmap
from PyQt5.QtWidgets import QGraphicsOpacityEffect

import bootstrap as _bootstrap
from detect_games import find_steam_root, parse_library_folders, find_installed_games
import config as cfg

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR    = os.path.join(PROJECT_ROOT, "assets", "fonts")
HEADERS_DIR  = os.path.join(PROJECT_ROOT, "assets", "images", "headers")
MUSIC_PATH   = os.path.join(PROJECT_ROOT, "assets", "music", "background.mp3")

os.makedirs(HEADERS_DIR, exist_ok=True)

C_BG       = "#141416"
C_CARD     = "#1E1E26"
C_IW       = "#6DC62B"
C_TREY     = "#F47B20"
C_DIM      = "#888899"
C_DARK_BTN = "#33333F"
C_RED_BTN  = "#7A1515"
C_BLUE_BTN = "#1A5FAA"

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
# depends on the Deck model. OLED users get the full key list. LCD users get
# a reduced set via the lcd_* overrides:
#
#   lcd_keys   — which game keys this card includes on LCD (empty = card hidden)
#   lcd_client — client badge label on LCD (e.g. "steam" instead of "plutonium")
#   lcd_appid  — appid used for the header image and Steam store link on LCD
#
# If an lcd_* field is missing, the card uses the default (OLED) value.
# The _active_keys(), _active_client(), _active_appid() helpers below
# resolve the correct value based on the user's saved deck_model config.

ALL_GAMES = [
    {"base":"Call of Duty 4: Modern Warfare","keys":["cod4mp","cod4sp"],"appid":7940,"dev":"iw","client":"cod4x + iw3sp",
     "launch_note":"Launch Multiplayer and Singleplayer at least once through Steam before continuing."},
    {"base":"Call of Duty: Modern Warfare 2","keys":["iw4mp","iw4sp"],"appid":10190,"dev":"iw","client":"iw4x",
     "launch_note":"Launch Multiplayer through Steam at least once before continuing."},
    {"base":"Call of Duty: Modern Warfare 3","keys":["iw5mp","iw5sp"],"appid":42690,"dev":"iw","client":"plutonium",
     "lcd_keys":["iw5sp"],"lcd_client":"steam","lcd_appid":42680,
     "launch_note":"Launch Multiplayer through Steam at least once before continuing."},
    {"base":"Call of Duty: World at War","keys":["t4sp","t4mp"],"appid":10090,"dev":"trey","client":"plutonium",
     "lcd_keys":["t4sp"],"lcd_client":"plutonium",
     "launch_note":"Launch Campaign through Steam at least once before continuing."},
    {"base":"Call of Duty: Black Ops","keys":["t5sp","t5mp"],"appid":42700,"dev":"trey","client":"plutonium",
     "lcd_keys":["t5sp"],"lcd_client":"plutonium",
     "launch_note":"Launch Campaign through Steam at least once before continuing."},
    {"base":"Call of Duty: Black Ops II","keys":["t6mp","t6zm","t6sp"],"appid":202990,"dev":"trey","client":"plutonium",
     "lcd_keys":["t6sp","t6zm"],"lcd_client":"plutonium + steam","lcd_appid":202970,
     "launch_note":"Launch Multiplayer and Zombies through Steam before continuing."},
]

def _active_keys(gd):
    """Return the keys to show for this card based on the user's Deck model."""
    if cfg.is_oled():
        return gd["keys"]
    return gd.get("lcd_keys", gd["keys"])

def _active_client(gd):
    """Return the client label for this card based on the user's Deck model."""
    if cfg.is_oled():
        return gd["client"]
    return gd.get("lcd_client", gd["client"])

def _active_appid(gd):
    """Return the display appid for this card based on the user's Deck model."""
    if cfg.is_oled():
        return gd["appid"]
    return gd.get("lcd_appid", gd["appid"])

KEY_CLIENT = {
    "cod4mp": "cod4x",
    "cod4sp": "iw3sp",
    "iw4mp":  "iw4x",
    "iw4sp":  "steam",
    "iw5mp":  "plutonium",
    "iw5sp":  "steam",
    "t4sp":   "plutonium",
    "t4mp":   "plutonium",
    "t5sp":   "plutonium",
    "t5mp":   "plutonium",
    "t6zm":   "plutonium",
    "t6mp":   "plutonium",
    "t6sp":   "steam",
}

KEY_EXES = {
    "cod4mp":"iw3mp.exe","cod4sp":"iw3sp.exe",
    "iw4mp":"iw4mp.exe","iw4sp":"iw4sp.exe",
    "iw5mp":"iw5mp.exe","iw5sp":"iw5sp.exe",
    "t4sp":"CoDWaW.exe","t4mp":"CoDWaWmp.exe",
    "t5sp":"BlackOps.exe","t5mp":"BlackOpsMP.exe",
    "t6zm":"t6zm.exe","t6mp":"t6mp.exe","t6sp":"t6sp.exe",
}

# Label shown beneath each per-key checkbox in SetupScreen.
KEY_MODE_LABEL = {
    "cod4mp": "MP",    "cod4sp": "SP",
    "iw4mp":  "MP",    "iw4sp":  "SP",
    "iw5mp":  "MP",    "iw5sp":  "SP",
    "t4sp":   "SP+ZM", "t4mp":   "MP",
    "t5sp":   "SP+ZM", "t5mp":   "MP",
    "t6sp":   "SP",    "t6zm":   "ZM",    "t6mp":   "MP",
}

def _is_prefix_ready(steam_root: str, appid: int) -> bool:
    """
    Check if a game has been launched through Steam at least once.
    Returns True if the Proton prefix exists and is initialized.
    """
    prefix = os.path.join(
        steam_root, "steamapps", "compatdata", str(appid), "pfx"
    )
    return os.path.isdir(prefix)


def _all_prefixes_ready(steam_root: str, gd: dict) -> bool:
    """
    Check that ALL required Proton prefixes exist for a game card.
    Some games (BO1) have keys that map to different appids (42700 SP, 42710 MP)
    and both prefixes must exist before setup is safe to proceed.
    Only checks keys active for the current Deck model.
    """
    from detect_games import GAMES
    keys = _active_keys(gd)
    appids_needed = {GAMES[k]["appid"] for k in keys if k in GAMES}
    return any(_is_prefix_ready(steam_root, aid) for aid in appids_needed)

SP_IMAGE_URLS = {
    7940:   "https://shared.steamstatic.com/store_item_assets/steam/apps/7940/header.jpg",
    10180:  "https://shared.steamstatic.com/store_item_assets/steam/apps/10180/header.jpg",
    10190:  "https://shared.steamstatic.com/store_item_assets/steam/apps/10180/header.jpg",
    42680:  "https://shared.steamstatic.com/store_item_assets/steam/apps/42680/header.jpg",
    42690:  "https://shared.steamstatic.com/store_item_assets/steam/apps/42680/header.jpg",
    10090:  "https://shared.steamstatic.com/store_item_assets/steam/apps/10090/header.jpg",
    42700:  "https://shared.steamstatic.com/store_item_assets/steam/apps/42700/header.jpg",
    202970: "https://shared.steamstatic.com/store_item_assets/steam/apps/202970/header.jpg",
    202990: "https://shared.steamstatic.com/store_item_assets/steam/apps/202970/header.jpg",
}

IMG_RATIO = 215 / 460
BTN_RATIO = 0.20
CARD_COLS = 3

MUSIC_URL = "https://archive.org/download/adrenaline-klickaud/Adrenaline_KLICKAUD.mp3"

_music_volume  = 0.4
_music_enabled = True

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
        pass

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
        pass

def _set_audio_volume(vol: float):
    global _music_volume
    _music_volume = vol
    if not _pygame_available():
        return
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.music.set_volume(vol)
    except Exception:
        pass

def _header_path(appid: int) -> str:
    return os.path.join(HEADERS_DIR, f"{appid}.jpg")

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

class _Sigs(QObject):
    progress    = pyqtSignal(int, str)
    log         = pyqtSignal(str)
    done        = pyqtSignal(bool)
    plut_wait   = pyqtSignal()
    plut_go     = pyqtSignal()
    pulse_start = pyqtSignal(str)
    pulse_stop  = pyqtSignal()

# ── BootstrapScreen ────────────────────────────────────────────────────────────
class BootstrapScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack = stack
        lay = QVBoxLayout(self); lay.setContentsMargins(80,80,80,80); lay.setSpacing(14)
        lay.addStretch()
        _title_block(lay)
        lay.addStretch()
        self.status = _lbl("Preparing...", 13, C_DIM)
        lay.addWidget(self.status)
        self.bar = QProgressBar(); self.bar.setMaximum(100); self.bar.setTextVisible(False)
        self.bar.setFixedHeight(14)
        bw = QHBoxLayout(); bw.addStretch(); bw.addWidget(self.bar,6); bw.addStretch()
        lay.addLayout(bw); lay.addSpacing(50)

    def showEvent(self, e):
        super().showEvent(e)
        _start_audio()
        if _bootstrap.all_ready():
            QTimer.singleShot(300, self._proceed); return
        self._s = _Sigs()
        self._s.progress.connect(lambda p,m: (self.bar.setValue(p), self.status.setText(m)))
        self._s.done.connect(lambda _: QTimer.singleShot(300, self._proceed))
        threading.Thread(target=lambda: _bootstrap.run(
            on_progress=lambda p,m: self._s.progress.emit(p,m),
            on_complete=lambda ok: self._s.done.emit(ok),
        ), daemon=True).start()

    def _proceed(self):
        # Re-load font and re-apply stylesheet now that bootstrap has completed.
        # This is a no-op if the font was already loaded at startup, but ensures
        # the correct font is applied even on a fresh install where bootstrap
        # runs for the first time.
        try:
            _load_font()
            QApplication.instance().setStyleSheet(_app_style())
        except FileNotFoundError:
            pass  # Font missing — fall back gracefully, app still works

        if cfg.is_first_run():
            self.stack.setCurrentIndex(1)
        else:
            root = find_steam_root()
            self.stack.widget(5).set_installed(find_installed_games(parse_library_folders(root)))
            self.stack.setCurrentIndex(5)

# ── IntroScreen ────────────────────────────────────────────────────────────────
class IntroScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack = stack
        self._selected_model = ""

        main_lay = QVBoxLayout(self); main_lay.setContentsMargins(0,0,0,0)

        # ── Model section (first screen) ──────────────────────────────────────
        self._model_section = QWidget()
        lay = QVBoxLayout(self._model_section); lay.setContentsMargins(80,60,80,60); lay.setSpacing(16)
        _title_block(lay)
        lay.addSpacing(8)
        lay.addWidget(_lbl(
            "DeckOps sets up community multiplayer clients for your Call of Duty games "
            "on Steam Deck, so you can play online with the best possible performance "
            "and shader cache benefits.", 14, "#CCCCCC"))
        lay.addSpacing(6)
        for warn in [
            "⚠   Before continuing, launch each game through Steam at least once — "
            "exactly these modes: CoD4 (Multiplayer AND Singleplayer), MW2 (Multiplayer), MW3 (Multiplayer), "
            "WaW (Campaign AND Multiplayer), BO1 (Campaign AND Multiplayer), "
            "BO2 (Zombies AND Multiplayer). "
            "This creates the Proton prefix and starts shader cache downloads. "
            "Skipping this is the #1 cause of install failures.",
            "⚠   If you plan to play Plutonium titles (WaW, BO1, BO2, MW3), "
            "create a free Plutonium account at plutonium.pw before continuing.",
        ]:
            lay.addWidget(_lbl(warn, 13, C_TREY, align=Qt.AlignLeft))
        lay.addSpacing(16)

        lay.addWidget(_lbl("Which Steam Deck do you have?", 15, "#CCC"))
        brow = QHBoxLayout(); brow.setSpacing(20)
        lcd  = _btn("Steam Deck LCD", C_DARK_BTN, h=56)
        oled = _btn("Steam Deck OLED", C_IW, h=56)
        lcd.clicked.connect(lambda: self._pick_model("lcd"))
        oled.clicked.connect(lambda: self._pick_model("oled"))
        brow.addWidget(lcd); brow.addWidget(oled)
        lay.addLayout(brow)
        main_lay.addWidget(self._model_section)

        # ── Gyro section (second screen, replaces model section) ──────────────
        self._gyro_section = QWidget(); self._gyro_section.setVisible(False)
        gl = QVBoxLayout(self._gyro_section); gl.setContentsMargins(80,60,80,60); gl.setSpacing(16)

        # Back button top-left showing which model was picked
        self._back_btn = _btn("← Steam Deck OLED", C_DARK_BTN, size=11, h=36)
        self._back_btn.setFixedWidth(220)
        self._back_btn.clicked.connect(self._back_to_model)
        back_row = QHBoxLayout()
        back_row.addWidget(self._back_btn); back_row.addStretch()
        gl.addLayout(back_row)

        gl.addStretch()
        _title_block(gl)
        gl.addSpacing(16)
        gl.addWidget(_lbl("How do you want to activate gyro aiming?", 15, "#CCC"))
        gl.addSpacing(4)
        gl.addWidget(_lbl(
            "Hold  —  gyro is active while R5 (right grip) is held down.\n"
            "ADS  —  gyro activates when you aim down sights.\n"
            "Toggle  —  press R5 once to turn gyro on, press again to turn it off.",
            13, C_DIM, align=Qt.AlignLeft))
        gl.addSpacing(12)
        grow = QHBoxLayout(); grow.setSpacing(20)
        hold_btn   = _btn("Hold",   C_DARK_BTN, h=56)
        ads_btn    = _btn("ADS",    C_DARK_BTN, h=56)
        toggle_btn = _btn("Toggle", C_DARK_BTN, h=56)
        hold_btn.clicked.connect(lambda: self._pick_gyro("hold"))
        ads_btn.clicked.connect(lambda: self._pick_gyro("ads"))
        toggle_btn.clicked.connect(lambda: self._pick_gyro("toggle"))
        grow.addWidget(hold_btn); grow.addWidget(ads_btn); grow.addWidget(toggle_btn)
        gl.addLayout(grow)
        gl.addStretch()
        main_lay.addWidget(self._gyro_section)

    def _back_to_model(self):
        self._gyro_section.setVisible(False)
        self._model_section.setVisible(True)

    def _pick_model(self, model):
        cfg.set_deck_model(model)
        label = "Steam Deck OLED" if model == "oled" else "Steam Deck LCD"
        self._back_btn.setText(f"← {label}")
        self._model_section.setVisible(False)
        self._gyro_section.setVisible(True)

    def _pick_gyro(self, mode):
        cfg.set_gyro_mode(mode)
        self.stack.setCurrentIndex(2)

# ── WelcomeScreen ──────────────────────────────────────────────────────────────
class WelcomeScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.installed={}; self.steam_root=""
        lay = QVBoxLayout(self); lay.setContentsMargins(80,60,80,60); lay.setSpacing(14)
        _title_block(lay)
        lay.addSpacing(12)
        self.status = _lbl("Scanning for Steam...", 14, C_DIM)
        lay.addWidget(self.status)
        self.bar = QProgressBar(); self.bar.setMaximum(100); self.bar.setTextVisible(False)
        self.bar.setFixedHeight(14)
        bw = QHBoxLayout(); bw.addStretch(); bw.addWidget(self.bar,6); bw.addStretch()
        lay.addLayout(bw)
        lay.addSpacing(10)
        self.results = _lbl("", 13, C_IW)
        lay.addWidget(self.results)
        lay.addStretch()
        self.cont = _btn("Continue >>", C_IW, h=52)
        self.cont.setFixedWidth(260); self.cont.setVisible(False)
        self.cont.clicked.connect(self._go_next)
        cw = QHBoxLayout(); cw.addStretch(); cw.addWidget(self.cont); cw.addStretch()
        lay.addLayout(cw)

    def showEvent(self, e):
        super().showEvent(e)
        self.bar.setValue(0); self.results.setText(""); self.cont.setVisible(False)
        QTimer.singleShot(200, self._scan_steam)

    def _scan_steam(self):
        self.status.setText("Scanning for Steam..."); self.bar.setValue(20)
        self.steam_root = find_steam_root()
        if not self.steam_root:
            self.status.setText("Steam not found. Is it installed?")
            self.status.setStyleSheet(f"color:{C_TREY};background:transparent;")
            self.bar.setValue(100); return
        self.status.setText(f"Found Steam at {self.steam_root}"); self.bar.setValue(40)
        QTimer.singleShot(200, self._scan_games)

    def _scan_games(self):
        self.status.setText("Scanning for games..."); self.bar.setValue(70)
        libs = parse_library_folders(self.steam_root)
        self.installed = find_installed_games(libs)
        if not cfg.is_oled():
            # LCD: only keep keys that appear in at least one card's lcd_keys
            lcd_allowed = set()
            for g in ALL_GAMES:
                lcd_allowed.update(g.get("lcd_keys", g["keys"]))
            self.installed = {k:v for k,v in self.installed.items() if k in lcd_allowed}
        QTimer.singleShot(200, self._show_results)

    def _show_results(self):
        self.bar.setValue(100)
        if not self.installed:
            self.status.setText("No supported games found.")
            self.status.setStyleSheet(f"color:{C_TREY};background:transparent;"); return
        unique = len({g["name"].split(" - ")[0].split(" (")[0] for g in self.installed.values()})
        self.status.setText(f"Found {unique} supported game(s)!")
        self.status.setStyleSheet(f"color:{C_IW};background:transparent;")
        seen,lines = set(),[]
        for g in sorted(self.installed.values(), key=lambda x: x.get("order",99)):
            base = g["name"].split(" - ")[0].split(" (")[0]
            if base not in seen: seen.add(base); lines.append(base)
        self.results.setText("\n".join(lines)); self.cont.setVisible(True)

    def _go_next(self):
        if cfg.is_first_run():
            s = self.stack.widget(3); s.installed=self.installed; s.steam_root=self.steam_root
            self.stack.setCurrentIndex(3)
        else:
            self.stack.widget(5).set_installed(self.installed); self.stack.setCurrentIndex(5)

# ── SetupScreen ────────────────────────────────────────────────────────────────
class SetupScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.installed={}; self.steam_root=""; self._checks={}
        lay = QVBoxLayout(self); lay.setContentsMargins(60,40,60,40); lay.setSpacing(14)
        t = QLabel("SETUP"); t.setFont(font(36,True)); t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("color:#FFF;background:transparent;"); lay.addWidget(t)
        lay.addWidget(_lbl(
            "Choose which games to set up. "
            "Games marked with ⚠ must be launched through Steam first.", 13, C_DIM))
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._lw = QWidget(); self._ll = QVBoxLayout(self._lw)
        self._ll.setSpacing(0); self._ll.addStretch()
        scroll.setWidget(self._lw); lay.addWidget(scroll, stretch=1)

        self.warning = _lbl("", 12, C_TREY, align=Qt.AlignLeft)
        self.warning.setVisible(False); lay.addWidget(self.warning)
        brow = QHBoxLayout(); brow.setSpacing(16)
        back = _btn("<< Back", C_DARK_BTN, h=52); back.setFixedWidth(180)
        back.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        self.inst_btn = _btn("Install Selected >>", C_IW, h=52)
        self.inst_btn.clicked.connect(self._go_install)
        brow.addWidget(back); brow.addWidget(self.inst_btn, stretch=1); lay.addLayout(brow)

    def showEvent(self, e):
        super().showEvent(e)
        self.warning.setVisible(False)
        self._build()

    def _build(self):
        while self._ll.count() > 1:
            item = self._ll.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._checks.clear()

        from detect_games import GAMES
        _LCD_OFFLINE_KEYS = {"t4sp", "t5sp", "t6zm"}
        # Each card gets up to 3 checkbox slots. Empty slots are transparent
        # placeholders that take space but draw nothing, keeping all rows aligned.
        MAX_SLOTS  = 3
        SLOT_W     = 28
        SLOT_GAP   = 8
        CHECKS_W   = MAX_SLOTS * SLOT_W + (MAX_SLOTS - 1) * SLOT_GAP

        for gd in ALL_GAMES:
            keys = _active_keys(gd)
            if not keys: continue
            ik = [k for k in keys if k in self.installed]
            if not ik: continue

            color  = C_IW if gd["dev"] == "iw" else C_TREY
            client = _active_client(gd)
            is_lcd_offline = not cfg.is_oled() and any(k in _LCD_OFFLINE_KEYS for k in keys)

            row = QHBoxLayout()
            row.setSpacing(12)
            row.setContentsMargins(8, 8, 8, 8)

            # ── Per-key checkbox column ────────────────────────────────────────
            checks_widget = QWidget()
            checks_widget.setFixedWidth(CHECKS_W)
            checks_layout = QHBoxLayout(checks_widget)
            checks_layout.setContentsMargins(0, 0, 0, 0)
            checks_layout.setSpacing(SLOT_GAP)

            for key in keys:
                appid       = GAMES[key]["appid"] if key in GAMES else None
                installed   = key in self.installed
                pre_ready   = _is_prefix_ready(self.steam_root, appid) if appid else False
                already_done = cfg.is_game_setup(key)

                slot = QWidget()
                slot.setFixedWidth(SLOT_W)
                slot_lay = QVBoxLayout(slot)
                slot_lay.setContentsMargins(0, 0, 0, 0)
                slot_lay.setSpacing(2)
                slot_lay.setAlignment(Qt.AlignHCenter)

                cb = QCheckBox()
                if not installed or not pre_ready:
                    cb.setChecked(False)
                    cb.setEnabled(False)
                elif already_done:
                    cb.setChecked(False)
                else:
                    cb.setChecked(True)

                mode_color = C_TREY if (not installed or not pre_ready) else "#666677"
                mode_lbl = _lbl(KEY_MODE_LABEL.get(key, key), 9, mode_color,
                                 align=Qt.AlignHCenter, wrap=False)

                slot_lay.addWidget(cb, alignment=Qt.AlignHCenter)
                slot_lay.addWidget(mode_lbl)
                checks_layout.addWidget(slot)

                self._checks[key] = (cb, gd)

            # Fill remaining slots with transparent spacers for alignment
            for _ in range(MAX_SLOTS - len(keys)):
                spacer = QWidget()
                spacer.setFixedSize(SLOT_W, 38)
                spacer.setStyleSheet("background: transparent;")
                checks_layout.addWidget(spacer)

            row.addWidget(checks_widget)

            # ── Game name + optional offline note ──────────────────────────────
            name_wrap = QWidget()
            name_wrap_lay = QVBoxLayout(name_wrap)
            name_wrap_lay.setContentsMargins(0, 0, 0, 0)
            name_wrap_lay.setSpacing(2)

            any_ready = any(
                _is_prefix_ready(self.steam_root, GAMES[k]["appid"])
                for k in ik if k in GAMES
            )
            name_color = "#FFF" if any_ready else "#555566"
            name_lbl = _lbl(gd["base"], 14, name_color, align=Qt.AlignLeft, wrap=False)
            name_wrap_lay.addWidget(name_lbl)

            if is_lcd_offline:
                offline_lbl = _lbl("⚠ offline only on LCD", 10, C_TREY,
                                    align=Qt.AlignLeft, wrap=False)
                name_wrap_lay.addWidget(offline_lbl)

            row.addWidget(name_wrap, stretch=1)

            # ── Client badge ───────────────────────────────────────────────────
            badge = QPushButton(client.upper())
            badge.setFont(font(10, True))
            badge.setFixedSize(160, 30)
            badge.setEnabled(False)
            badge.setStyleSheet(
                f"QPushButton{{background:{color};color:#FFF;border:none;border-radius:6px;}}"
                f"QPushButton:disabled{{background:{color};color:#FFF;}}"
            )
            row.addWidget(badge)

            cw = QWidget()
            cw.setLayout(row)
            self._ll.insertWidget(self._ll.count() - 1, cw)

    def _go_install(self):
        selected = []
        from detect_games import GAMES
        for key, (cb, gd) in self._checks.items():
            if not cb.isChecked(): continue
            if key not in self.installed: continue
            # Only install keys whose prefix is actually ready.
            appid = GAMES[key]["appid"] if key in GAMES else None
            if appid and not _is_prefix_ready(self.steam_root, appid): continue
            selected.append((key, gd, self.installed[key]))
        if not selected:
            self.warning.setText("Select at least one game to continue.")
            self.warning.setVisible(True); return
        s = self.stack.widget(4); s.selected=selected; s.steam_root=self.steam_root
        self.stack.setCurrentIndex(4)

# ── InstallScreen ──────────────────────────────────────────────────────────────
class InstallScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.selected=[]; self.steam_root=""
        self._plut_event = threading.Event()

        lay = QVBoxLayout(self); lay.setContentsMargins(80,60,80,60); lay.setSpacing(20)
        t = QLabel("INSTALLING"); t.setFont(font(36,True)); t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("color:#FFF;background:transparent;"); lay.addWidget(t)
        self.cur = _lbl("Preparing...", 16, "#CCC"); lay.addWidget(self.cur)
        self.bar = QProgressBar(); self.bar.setMaximum(100); self.bar.setTextVisible(False)
        self.bar.setFixedHeight(22)
        bw = QHBoxLayout(); bw.setContentsMargins(60,0,60,0); bw.addWidget(self.bar)
        lay.addLayout(bw)
        self.stat = _lbl("", 13, C_IW); lay.addWidget(self.stat)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(font(11))
        self.log.setStyleSheet("QPlainTextEdit{color:#666677;background:transparent;border:none;padding:10px;}")
        lay.addWidget(self.log, stretch=1)

        self.plut_btn = _btn("I've closed Plutonium  ✓", C_TREY, size=13, h=52)
        self.plut_btn.setFixedWidth(460); self.plut_btn.setVisible(False)
        self.plut_btn.clicked.connect(self._confirm_plut)
        pw = QHBoxLayout(); pw.addStretch(); pw.addWidget(self.plut_btn); pw.addStretch()
        lay.addLayout(pw)

        self.cont_btn = _btn("Continue  >>", C_IW, size=13, h=52)
        self.cont_btn.setFixedWidth(320); self.cont_btn.setVisible(False)
        self.cont_btn.clicked.connect(lambda: self.stack.setCurrentIndex(7))
        cw = QHBoxLayout(); cw.addStretch(); cw.addWidget(self.cont_btn); cw.addStretch()
        lay.addLayout(cw)

        self._s = _Sigs()
        self._s.progress.connect(lambda p,m: (self.bar.setValue(p), self.cur.setText(m)))
        self._s.log.connect(self._append_log)
        self._s.done.connect(self._on_done)
        self._s.plut_wait.connect(lambda: self.plut_btn.setVisible(True))
        self._s.plut_go.connect(lambda: self.plut_btn.setVisible(False))
        self._s.pulse_start.connect(self._start_pulse)
        self._s.pulse_stop.connect(self._stop_pulse)

        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._do_pulse)
        self._pulse_msg   = ""
        self._pulse_count = 0

    def _start_pulse(self, base_msg):
        self._pulse_msg   = base_msg
        self._pulse_count = 0
        self._pulse_timer.start(500)

    def _do_pulse(self):
        dots = "." * (self._pulse_count % 4)
        self.cur.setText(f"{self._pulse_msg}{dots}")
        self._pulse_count += 1

    def _stop_pulse(self):
        self._pulse_timer.stop()

    def _append_log(self, text):
        self.log.appendPlainText(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def showEvent(self, e):
        super().showEvent(e)
        self.bar.setValue(0); self.log.clear()
        self.plut_btn.setVisible(False)
        self._stop_pulse()
        self._plut_event.clear()
        QTimer.singleShot(400, lambda: threading.Thread(target=self._run, daemon=True).start())

    def _confirm_plut(self):
        self._plut_event.set()

    def _on_done(self, _):
        self._stop_pulse()
        self.cur.setText("Installation complete!")
        self.cont_btn.setVisible(True)

    def _go_management(self):
        root = find_steam_root()
        self.stack.widget(5).set_installed(find_installed_games(parse_library_folders(root)))
        self.stack.setCurrentIndex(5)

    def _run(self):
        from wrapper import get_proton_path, find_compatdata, kill_steam
        from plutonium import launch_bootstrapper, is_plutonium_ready, install_plutonium
        from cod4x import install_cod4x
        from iw4x import install_iw4x
        from iw3sp import install_iw3sp
        from ge_proton import install_ge_proton, set_compat_tool, MANAGED_APPIDS

        selected_keys   = [key for key, _, _ in self.selected]
        has_plut        = any(KEY_CLIENT.get(k) == "plutonium" for k in selected_keys)
        has_cod4        = any(KEY_CLIENT.get(k) in ("cod4x", "iw3sp") for k in selected_keys)
        has_iw4x        = any(KEY_CLIENT.get(k) == "iw4x" for k in selected_keys)
        logged_bases    = set()
        ge_version      = None
        _compat_applied = False
        _steam_killed   = False

        def _kill_steam_once():
            nonlocal _steam_killed
            if not _steam_killed:
                self._s.progress.emit(28, "Closing Steam...")
                self._s.log.emit("Closing Steam...")
                try:
                    kill_steam()
                    self._s.log.emit("  ✓ Steam closed.")
                except Exception as ex:
                    self._s.log.emit(f"  Could not close Steam: {ex}")
                _steam_killed = True

        def _apply_compat():
            nonlocal _compat_applied
            if ge_version and not _compat_applied:
                try:
                    set_compat_tool(MANAGED_APPIDS, ge_version)
                    self._s.log.emit(f"✓  GE-Proton {ge_version} set for all games")
                    cfg.set_ge_proton_version(ge_version)
                    _compat_applied = True
                except Exception as ex:
                    self._s.log.emit(f"  CompatToolMapping skipped: {ex}")
        _launch_defaults_set = False
        def _set_launch_defaults():
            nonlocal _launch_defaults_set
            if _launch_defaults_set:
                return
            defaults = {}
            if has_cod4:
                defaults["7940"] = ("7a722f97", "1")   # CoD4 → Singleplayer
            if any(k in ("t4sp", "t4mp") for k in selected_keys):
                defaults["10090"] = ("9aa5e05f", "0") # WaW → Campaign
            if not defaults:
                return
            try:
                from wrapper import set_default_launch_option
                set_default_launch_option(self.steam_root, defaults)
                self._s.log.emit("✓  Default launch options set (SP mode)")
                _launch_defaults_set = True
            except Exception as ex:
                self._s.log.emit(f"  Launch options skipped: {ex}")

        # ── GE-Proton download + extract (Steam still running) ────────────────
        try:
            self._s.pulse_start.emit("Installing GE-Proton")
            self._s.log.emit("Installing GE-Proton...")
            ge_version = install_ge_proton(
                on_progress=lambda pct, msg: self._s.progress.emit(2 + int(pct * 0.08), msg)
            )
            self._s.pulse_stop.emit()
            self._s.log.emit(f"✓  {ge_version} downloaded")
        except Exception as ex:
            self._s.pulse_stop.emit()
            self._s.log.emit(f"  GE-Proton setup skipped: {ex}")

        proton = get_proton_path(self.steam_root)

        # ── Plutonium bootstrapper (Steam still running) ──────────────────────
        if has_plut:
            if not is_plutonium_ready():
                self._s.progress.emit(12, "Launching Plutonium — please log in...")
                self._s.log.emit(
                    "Plutonium is launching now.\n"
                    "  1. Wait for it to finish downloading\n"
                    "  2. Log in with your Plutonium account\n"
                    "  3. Close the Plutonium window\n"
                    "  4. Click the button below to continue"
                )
                try:
                    launch_bootstrapper(proton, on_progress=lambda p, m: self._s.progress.emit(p, m))
                except Exception as ex:
                    self._s.log.emit(f"✗  Plutonium launch failed: {ex}")
                    self._s.progress.emit(100, "Setup failed."); self._s.done.emit(True); return

                self._s.plut_wait.emit()
                self._plut_event.wait()
                self._s.plut_go.emit()

                if not is_plutonium_ready():
                    self._s.log.emit(
                        "✗  Plutonium does not appear to be fully set up.\n"
                        "   Make sure you logged in and let it finish downloading."
                    )
                    self._s.progress.emit(100, "Setup incomplete."); self._s.done.emit(True); return

                self._s.log.emit("✓  Plutonium ready.")
            else:
                self._s.progress.emit(12, "Close Plutonium if open, then confirm...")
                self._s.log.emit(
                    "Almost there!\n"
                    "  Close Plutonium if it's still open.\n"
                    "  Click the button below to continue."
                )
                self._s.plut_wait.emit()
                self._plut_event.wait()
                self._s.plut_go.emit()

        # ── Kill Steam once — everything from here runs with Steam closed ─────
        _kill_steam_once()
        _apply_compat()
        _set_launch_defaults()

        # ── Clean up stale launch options from older DeckOps versions ─────────
        # Old versions used launch commands instead of the exe rename strategy.
        # If those are still in localconfig.vdf they'll conflict with the rename.
        try:
            from wrapper import clear_launch_options
            for stale_appid in ["7940", "10190"]:
                clear_launch_options(self.steam_root, stale_appid)
            self._s.log.emit("✓  Stale launch options cleared")
        except Exception as ex:
            self._s.log.emit(f"  Launch option cleanup skipped: {ex}")

        # ── Plutonium games ───────────────────────────────────────────────────
        if has_plut:
            from plutonium import install_xact_once, XACT_GAME_KEYS
            has_xact = any(k in XACT_GAME_KEYS for k in selected_keys)
            xact_ready = False
            if has_xact:
                self._s.progress.emit(29, "Installing XACT audio (once for all games)...")
                self._s.log.emit("Installing XACT audio components (shared across WaW and Black Ops)...")
                self._s.pulse_start.emit("Installing XACT audio")
                xact_ready = install_xact_once(
                    [k for k in selected_keys if k in XACT_GAME_KEYS],
                    steam_root=self.steam_root,
                    proton_path=proton,
                    on_progress=lambda msg: self._s.log.emit(f"  {msg}"),
                )
                self._s.pulse_stop.emit()

            plut_selected = [(k, gd, g) for k, gd, g in self.selected if KEY_CLIENT.get(k) == "plutonium"]
            total_plut = len(plut_selected)
            for idx, (key, gd, game) in enumerate(plut_selected):
                bp = 30 + int(idx / max(total_plut, 1) * 30)
                base_name = gd["base"]
                if base_name not in logged_bases:
                    self._s.progress.emit(bp, f"Setting up {base_name}...")
                def op_plut(pct, msg, _b=bp): self._s.progress.emit(_b + int(pct / 100 * 8), msg)
                try:
                    from plutonium import GAME_META as _PLUT_META
                    _plut_appid = _PLUT_META[key][0] if key in _PLUT_META else gd["appid"]
                    compat = find_compatdata(self.steam_root, _plut_appid)
                    install_plutonium(game, key, self.steam_root, proton, compat, op_plut,
                                      protontricks_ready=xact_ready)
                    cfg.mark_game_setup(key, "plutonium")
                    if base_name not in logged_bases:
                        self._s.log.emit(f"✓  {base_name} done")
                        logged_bases.add(base_name)
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        # ── iw4x (Steam closed) ───────────────────────────────────────────────
        if has_iw4x:
            for key, gd, game in [(k, gd, g) for k, gd, g in self.selected if KEY_CLIENT.get(k) == "iw4x"]:
                base_name = gd["base"]
                self._s.progress.emit(62, f"Setting up {base_name}...")
                def op_iw4x(pct, msg): self._s.progress.emit(62 + int(pct / 100 * 8), msg)
                try:
                    compat = find_compatdata(self.steam_root, gd["appid"])
                    install_iw4x(game, self.steam_root, proton, compat, op_iw4x)
                    cfg.mark_game_setup(key, "iw4x")
                    self._s.log.emit(f"✓  {base_name} done")
                    logged_bases.add(base_name)
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        # ── CoD4 (iw3sp + cod4x) — Steam closed ──────────────────────────────
        if has_cod4:
            cod4_selected = [(k, gd, g) for k, gd, g in self.selected if KEY_CLIENT.get(k) in ("cod4x", "iw3sp")]
            for key, gd, game in cod4_selected:
                base_name = gd["base"]
                self._s.progress.emit(75, f"Setting up {base_name}...")
                def op_cod4(pct, msg): self._s.progress.emit(75 + int(pct / 100 * 10), msg)
                try:
                    compat = find_compatdata(self.steam_root, gd["appid"])
                    c = KEY_CLIENT.get(key, gd["client"])
                    if c == "cod4x":
                        install_cod4x(game, self.steam_root, proton, compat, op_cod4,
                                      appid=gd["appid"])
                    elif c == "iw3sp":
                        install_iw3sp(game, self.steam_root, proton, compat, op_cod4)
                    cfg.mark_game_setup(key, c)
                    if base_name not in logged_bases:
                        self._s.log.emit(f"✓  {base_name} done")
                        logged_bases.add(base_name)
                        self._s.log.emit(
                            "⚠  CoD4 setup note:\n"
                            "   • CoD4 Multiplayer requires TWO launches to finish setup.\n"
                            "     Launch it once through Steam, let it close, then launch again."
                        )
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        # ── Vanilla Steam games (no mod client, just configs + controllers) ──
        # Games like MW2 SP, MW3 SP, and BO2 SP run through Steam as-is.
        # No download or exe replacement needed. We just mark them as set up
        # so they show as installed on the My Games screen and get their
        # display configs and controller profiles applied below.
        for key, gd, game in self.selected:
            c = KEY_CLIENT.get(key, "")
            if c == "steam" and not cfg.is_game_setup(key):
                cfg.mark_game_setup(key, "steam")
                self._s.log.emit(f"✓  {gd['base']} ({key}) ready")

        # ── game display configs ──────────────────────────────────────────────
        try:
            from game_config import apply_game_configs
            applied, skipped, failed = apply_game_configs(
                selected_keys=selected_keys,
                installed_games={k: g for k, gd, g in self.selected if g},
                steam_root=self.steam_root,
                deck_model=cfg.get_deck_model() or "oled",
                on_progress=lambda msg: self._s.log.emit(msg),
            )
            if applied > 0:
                self._s.log.emit(f"✓  Game display configs: {applied} written"
                                 + (f", {skipped} skipped" if skipped else "")
                                 + (f", {failed} failed" if failed else ""))
            elif skipped > 0:
                self._s.log.emit(f"⚠  Game display configs: none applied ({skipped} skipped)")
            else:
                self._s.log.emit("⚠  Game display configs: no eligible configs found")
        except Exception as ex:
            self._s.log.emit(f"  Game configs skipped: {ex}")

        # ── Controller templates + profiles (after all games) ─────────────────
        self._s.progress.emit(90, "Installing controller templates...")
        self._s.log.emit("Installing controller templates...")
        try:
            from controller_profiles import install_controller_templates, assign_controller_profiles
            install_controller_templates(
                on_progress=lambda msg: self._s.log.emit(f"  {msg}")
            )
            gyro_mode = cfg.get_gyro_mode() or "hold"
            assign_controller_profiles(
                gyro_mode,
                on_progress=lambda msg: self._s.log.emit(f"  {msg}")
            )
            self._s.log.emit(f"✓  Controller profiles assigned ({gyro_mode} mode)")
        except Exception as ex:
            self._s.log.emit(f"  Templates skipped: {ex}")

        try:
            from wrapper import set_steam_input_enabled
            set_steam_input_enabled(self.steam_root)
            self._s.log.emit("✓  Steam Input enabled for all games")
        except Exception as ex:
            self._s.log.emit(f"  Steam Input setup skipped: {ex}")

        # ── Non-Steam shortcuts ───────────────────────────────────────────────
        try:
            from shortcut import create_shortcuts
            self._s.log.emit("Creating non-Steam shortcuts...")
            installed_for_shortcuts = {k: g for k, gd, g in self.selected if g}
            create_shortcuts(
                installed_games=installed_for_shortcuts,
                selected_keys=selected_keys,
                gyro_mode=cfg.get_gyro_mode() or "hold",
                on_progress=lambda msg: self._s.log.emit(msg)
            )
        except Exception as ex:
            self._s.log.emit(f"  Shortcuts skipped: {ex}")

        cfg.complete_first_run(self.steam_root)
        self._s.progress.emit(100, "All done!")
        self._s.done.emit(True)


# ── ManagementCard ─────────────────────────────────────────────────────────────
class ManagementCard(QFrame):
    def __init__(self, gd, installed, on_setup, on_update, on_reinstall, parent=None):
        super().__init__(parent)
        color = C_IW if gd["dev"] == "iw" else C_TREY
        self._color  = color
        self._appid  = _active_appid(gd)
        self.setObjectName("MC")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        keys       = _active_keys(gd)
        client     = _active_client(gd)
        ik         = [k for k in keys if k in installed]
        is_setup   = any(cfg.is_game_setup(k) for k in keys)
        is_present = len(ik) > 0

        border_color = color if is_setup else ("#445544" if is_present else "#333344")
        self.setStyleSheet(
            f"QFrame#MC{{background:{C_CARD};border-top:3px solid {border_color};border-radius:8px;}}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._img = QLabel()
        self._img.setAlignment(Qt.AlignCenter)
        self._img.setStyleSheet("background:#0A0A10;border:none;")
        if not is_setup:
            effect = QGraphicsOpacityEffect()
            effect.setOpacity(0.45 if is_present else 0.25)
            self._img.setGraphicsEffect(effect)
        lay.addWidget(self._img)
        self._raw_pixmap = None

        cached = _header_path(self._appid)
        if os.path.exists(cached):
            self._raw_pixmap = QPixmap(cached)
        else:
            threading.Thread(target=self._fetch, args=(self._appid,), daemon=True).start()

        badge_row = QWidget()
        badge_row.setStyleSheet(f"background:{C_CARD};border:none;")
        bl = QHBoxLayout(badge_row)
        bl.setContentsMargins(8, 4, 8, 4); bl.setSpacing(6)

        client_lbl = QPushButton(client.upper())
        client_lbl.setFont(font(9, True)); client_lbl.setFixedHeight(22)
        client_lbl.setEnabled(False)
        client_lbl.setStyleSheet(
            f"QPushButton{{background:{color};color:#FFF;border:none;border-radius:4px;padding:0 8px;}}"
            f"QPushButton:disabled{{background:{color};color:#FFF;}}"
        )
        bl.addWidget(client_lbl)
        bl.addStretch()

        if is_setup:
            status_lbl = _lbl("✓ installed", 10, C_IW, align=Qt.AlignRight, wrap=False)
        elif is_present:
            status_lbl = _lbl("not set up", 10, C_DIM, align=Qt.AlignRight, wrap=False)
        else:
            status_lbl = _lbl("not installed", 10, "#554444", align=Qt.AlignRight, wrap=False)
        bl.addWidget(status_lbl)
        lay.addWidget(badge_row)

        title = _lbl(gd["base"], 12, "#FFF" if is_present else "#444455",
                     align=Qt.AlignLeft, wrap=False)
        title.setContentsMargins(8, 4, 8, 0)
        lay.addWidget(title)

        btn_row = QWidget(); btn_row.setStyleSheet(f"background:{C_CARD};border:none;")
        br = QHBoxLayout(btn_row); br.setContentsMargins(8, 6, 8, 8); br.setSpacing(6)

        if not is_present:
            inst_btn = _btn("Install on Steam", C_DARK_BTN, size=10, h=32)
            inst_btn.clicked.connect(lambda _=None, aid=self._appid: subprocess.Popen(
                ["xdg-open", f"steam://install/{aid}"]))
            br.addWidget(inst_btn); br.addStretch()
        elif not is_setup:
            setup_btn = _btn("Set Up", C_IW, size=10, h=32)
            setup_btn.clicked.connect(lambda: on_setup(gd))
            br.addWidget(setup_btn); br.addStretch()
        else:
            # Only show Update/Reinstall for games with a mod client
            has_mod = any(KEY_CLIENT.get(k, "") not in ("steam", "") for k in ik)
            if has_mod:
                upd_btn = _btn("Update", C_DARK_BTN, size=10, h=32)
                rei_btn = _btn("Reinstall", C_DARK_BTN, size=10, h=32)
                upd_btn.clicked.connect(lambda: on_update(gd, ik))
                rei_btn.clicked.connect(lambda: on_reinstall(gd, ik))
                br.addWidget(upd_btn); br.addWidget(rei_btn)
            fld_btn = _btn("Open Folder", C_DARK_BTN, size=10, h=32)
            _idir = installed.get(ik[0], {}).get("install_dir", "") if ik else ""
            fld_btn.clicked.connect(lambda _=None, d=_idir: subprocess.Popen(
                ["xdg-open", d]) if d else None)
            br.addWidget(fld_btn); br.addStretch()

        lay.addWidget(btn_row)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._scale_image()

    def _scale_image(self):
        if self._raw_pixmap:
            w = self.width()
            h = int(w * IMG_RATIO)
            self._img.setFixedSize(w, h)
            self._img.setPixmap(
                self._raw_pixmap.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            )
        else:
            w = self.width()
            self._img.setFixedSize(w, int(w * IMG_RATIO))

    def _fetch(self, appid):
        url = SP_IMAGE_URLS.get(appid)
        if not url:
            return
        try:
            import urllib.request
            dest = _header_path(appid)
            urllib.request.urlretrieve(url, dest)
            pix = QPixmap(dest)
            if not pix.isNull():
                self._raw_pixmap = pix
                QTimer.singleShot(0, self._scale_image)
        except Exception:
            pass

# ── ManagementScreen ───────────────────────────────────────────────────────────
class ManagementScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.installed={}
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        hdr = QWidget(); hdr.setFixedHeight(60)
        hdr.setStyleSheet(f"background:{C_CARD};")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(20,0,20,0)
        title = QLabel("DECKOPS"); title.setFont(font(22, display=True))
        title.setStyleSheet("color:#FFF;background:transparent;")
        hl.addWidget(title); hl.addStretch()
        guide_btn = _btn("📋  Guide", C_BLUE_BTN, size=11, h=36); guide_btn.setFixedWidth(100)
        guide_btn.clicked.connect(lambda: self.stack.setCurrentIndex(7))
        hl.addWidget(guide_btn)
        hl.addSpacing(8)
        cfg_btn = _btn("⚙  Settings", C_DARK_BTN, size=11, h=36); cfg_btn.setFixedWidth(120)
        cfg_btn.clicked.connect(lambda: self.stack.setCurrentIndex(6))
        hl.addWidget(cfg_btn)
        lay.addWidget(hdr)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget(); self._grid = QGridLayout(inner)
        self._grid.setContentsMargins(16,16,16,16); self._grid.setSpacing(12)
        for c in range(CARD_COLS):
            self._grid.setColumnStretch(c, 1)
        scroll.setWidget(inner); lay.addWidget(scroll, stretch=1)

        self._status = _lbl("", 12, C_DIM)
        self._status.setContentsMargins(16,4,16,4)
        lay.addWidget(self._status)

    def set_installed(self, installed):
        self.installed = installed
        self._rebuild()

    def showEvent(self, e):
        super().showEvent(e)
        root = find_steam_root()
        self.installed = find_installed_games(parse_library_folders(root))
        self._rebuild()

    def _rebuild(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        games = [g for g in ALL_GAMES if _active_keys(g)]

        for idx, gd in enumerate(games):
            row = idx // CARD_COLS
            col = idx  % CARD_COLS
            card = ManagementCard(
                gd, self.installed,
                on_setup     = self._setup,
                on_update    = self._update,
                on_reinstall = self._reinstall,
            )
            self._grid.addWidget(card, row, col)

        total = len(games)
        remainder = total % CARD_COLS
        if remainder:
            for col in range(remainder, CARD_COLS):
                self._grid.addWidget(QWidget(), total // CARD_COLS, col)

    def _setup(self, gd):
        root = find_steam_root()
        inst = find_installed_games(parse_library_folders(root))
        s = self.stack.widget(3)
        s.installed  = inst
        s.steam_root = root
        self.stack.setCurrentIndex(3)

    def _update(self, gd, keys):
        root = find_steam_root()
        inst = find_installed_games(parse_library_folders(root))
        selected = [(k, gd, inst.get(k, {})) for k in keys if inst.get(k)]
        if not selected:
            self._status.setText("Game not found in Steam library."); return
        s = self.stack.widget(8)
        s.mode       = "update"
        s.selected   = selected
        s.steam_root = root
        self.stack.setCurrentIndex(8)

    def _reinstall(self, gd, keys):
        root = find_steam_root()
        inst = find_installed_games(parse_library_folders(root))
        selected = [(k, gd, inst.get(k, {})) for k in keys if inst.get(k)]
        if not selected:
            self._status.setText("Game not found in Steam library."); return
        s = self.stack.widget(8)
        s.mode       = "reinstall"
        s.selected   = selected
        s.steam_root = root
        self.stack.setCurrentIndex(8)


# ── ControllerInfoScreen ───────────────────────────────────────────────────────
class ControllerInfoScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack = stack
        lay = QVBoxLayout(self); lay.setContentsMargins(60,30,60,30); lay.setSpacing(8)

        t = QLabel("SETUP COMPLETE"); t.setFont(font(32, True)); t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("color:#FFF;background:transparent;"); lay.addWidget(t)
        lay.addWidget(_lbl(
            "DeckOps has configured your games with controller profiles, GE-Proton, "
            "and display settings. You're ready to play.",
            13, C_DIM))
        lay.addWidget(_hdiv())

        # ── Warning box ────────────────────────────────────────────────────────
        lay.addWidget(_lbl("⚠  Do This Before Anything Else", 13, C_TREY, bold=True, align=Qt.AlignLeft))
        lay.addWidget(_lbl(
            "You will be switched to Game Mode automatically. "
            "Launch every modded game at least once before using Steam in Desktop Mode, "
            "especially MW1 (Singleplayer) and MW2 (Multiplayer). "
            "Steam Cloud will overwrite your setup if you don't.",
            11, C_DIM, align=Qt.AlignLeft))
        lay.addWidget(_lbl(
            "If Steam asks about cloud saves, choose Keep Local. "
            "If a game asks for Safe Mode, choose No.",
            11, C_DIM, align=Qt.AlignLeft))
        lay.addWidget(_hdiv())

        # ── MW1 / WaW launch mode instruction ─────────────────────────────────
        lay.addWidget(_lbl("🎮  First Launch - Modern Warfare 1 & World at War", 13, C_IW, bold=True, align=Qt.AlignLeft))
        lay.addWidget(_lbl(
            "When launching either game for the first time, Steam will ask which mode you want to launch. "
            "Select Singleplayer or Campaign and set it as your default. "
            "Multiplayer for these games launches via the DeckOps shortcuts in your library instead.",
            11, C_DIM, align=Qt.AlignLeft))
        lay.addWidget(_lbl(
            "MW1 Singleplayer (IW3SP-MOD): On your first launch, "
            "the game will ask you to select a profile. Choose \"Player\" — "
            "this is the profile DeckOps created with your display settings. "
            "Creating a new profile will use default settings instead.",
            11, C_DIM, align=Qt.AlignLeft))

        lay.addWidget(_hdiv())

        # ── LCD-only Plutonium online warning ──────────────────────────────────
        # Only shown to LCD users. WaW and BO1 Campaign/Zombies run through
        # Plutonium on LCD but online play requires an OLED Deck. Playing
        # online on LCD will result in errors.
        self._lcd_plut_warn_div  = _hdiv()
        self._lcd_plut_warn_hdr  = _lbl("⚠  WaW & Black Ops — Offline Only on LCD", 13, C_TREY, bold=True, align=Qt.AlignLeft)
        self._lcd_plut_warn_body = _lbl(
            "Campaign and Zombies for World at War and Black Ops run through Plutonium on LCD. "
            "Do not attempt to play these online — Plutonium online servers require an OLED Steam Deck "
            "and you will run into errors if you try. Stick to offline Campaign and Zombies.",
            11, C_DIM, align=Qt.AlignLeft)
        lay.addWidget(self._lcd_plut_warn_div)
        lay.addWidget(self._lcd_plut_warn_hdr)
        lay.addWidget(self._lcd_plut_warn_body)

        lay.addWidget(_hdiv())

        # ── BO2 encrypted config note ──────────────────────────────────────────
        lay.addWidget(_lbl("⚠  Black Ops II - Manual Setup Required", 13, C_TREY, bold=True, align=Qt.AlignLeft))
        lay.addWidget(_lbl(
            "BO2 Multiplayer and Zombies config files are handled automatically by DeckOps. "
            "Singleplayer config files are encrypted and cannot be written by DeckOps. "
            "Set your resolution and display settings manually in-game after launching for the first time.",
            11, C_DIM, align=Qt.AlignLeft))

        lay.addWidget(_hdiv())

        # ── Controller Profiles & GE-Proton ───────────────────────────────────
        lay.addWidget(_lbl("🎮  Controller Profiles & GE-Proton", 13, C_IW, bold=True, align=Qt.AlignLeft))
        # gyro_desc is set dynamically in showEvent so it always reflects the
        # user's actual choice, not whatever was in config at construction time.
        self._gyro_lbl = _lbl("", 11, C_DIM, align=Qt.AlignLeft)
        lay.addWidget(self._gyro_lbl)
        lay.addWidget(_lbl(
            "Newest GE-Proton installed and set for all games. "
            "Change Hold, ADS, or Toggle anytime in Settings — Re-apply Controller Profiles.",
            11, "#666", align=Qt.AlignLeft))

        lay.addStretch()

        lay.addWidget(_lbl(
            "Launch each modded game at least once before going online — Steam Cloud may overwrite your setup if you launch Desktop Mode first.",
            11, C_TREY, align=Qt.AlignCenter))
        lay.addSpacing(4)

        cont = _btn("Continue  >>", C_IW, h=52)
        cont.clicked.connect(self._reopen_steam)
        cw = QHBoxLayout(); cw.addStretch(); cw.addWidget(cont, stretch=1); cw.addStretch()
        lay.addLayout(cw)

    def showEvent(self, e):
        super().showEvent(e)
        gyro_mode = cfg.get_gyro_mode() or "hold"
        if gyro_mode == "hold":
            gyro_desc = "R5 held"
        elif gyro_mode == "ads":
            gyro_desc = "aim down sights"
        else:
            gyro_desc = "R5 toggles"
        self._gyro_lbl.setText(
            f"Standard gamepad layout with gyro aiming ({gyro_desc}) assigned to all games. "
        )
        # Only show the online warning if the user is on LCD
        is_lcd = not cfg.is_oled()
        self._lcd_plut_warn_div.setVisible(is_lcd)
        self._lcd_plut_warn_hdr.setVisible(is_lcd)
        self._lcd_plut_warn_body.setVisible(is_lcd)

    def _go_management(self):
        root = find_steam_root()
        self.stack.widget(5).set_installed(find_installed_games(parse_library_folders(root)))
        self.stack.setCurrentIndex(5)

    def _reopen_steam(self):
        try:
            steam_root = cfg.load().get("steam_root", "") or find_steam_root()
            steam_sh = os.path.join(steam_root, "steam.sh") if steam_root else None
            if steam_sh and os.path.exists(steam_sh):
                subprocess.Popen([steam_sh], start_new_session=True)
            else:
                subprocess.Popen(["steam"], start_new_session=True)
        except Exception:
            try:
                subprocess.Popen(["steam"], start_new_session=True)
            except Exception:
                pass
        root = find_steam_root()
        self.stack.widget(5).set_installed(find_installed_games(parse_library_folders(root)))
        self.stack.setCurrentIndex(5)


def _reopen_steam_bg(steam_root=None):
    """Reopen Steam in the background after a settings operation."""
    try:
        if not steam_root:
            steam_root = find_steam_root()
        steam_sh = os.path.join(steam_root, "steam.sh") if steam_root else None
        if steam_sh and os.path.exists(steam_sh):
            subprocess.Popen([steam_sh], start_new_session=True)
        else:
            subprocess.Popen(["steam"], start_new_session=True)
    except Exception:
        pass

# ── ConfigureScreen ────────────────────────────────────────────────────────────
class ConfigureScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack
        lay = QVBoxLayout(self); lay.setContentsMargins(60,40,60,40); lay.setSpacing(18)
        t = QLabel("SETTINGS"); t.setFont(font(36,True)); t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("color:#FFF;background:transparent;"); lay.addWidget(t)
        lay.addWidget(_hdiv())

        lay.addWidget(_lbl("Background Music", 14, "#CCC", align=Qt.AlignLeft))
        mr = QHBoxLayout(); mr.setSpacing(12)
        self._music_on = True
        self._music_toggle = _btn("Music: ON", C_IW, size=12, h=40); self._music_toggle.setFixedWidth(160)
        self._music_toggle.clicked.connect(self._toggle_music)
        from PyQt5.QtWidgets import QSlider
        self._vol_slider = QSlider(Qt.Horizontal); self._vol_slider.setRange(0,100)
        self._vol_slider.setValue(int(_music_volume*100))
        self._vol_label = _lbl(f"{int(_music_volume*100)}%", 12, C_DIM, wrap=False)
        self._vol_label.setFixedWidth(40)
        self._vol_slider.valueChanged.connect(self._set_volume)
        mr.addWidget(self._music_toggle); mr.addWidget(self._vol_slider,stretch=1); mr.addWidget(self._vol_label)
        lay.addLayout(mr)
        lay.addWidget(_hdiv())

        lay.addWidget(_lbl("Plutonium Account", 14, "#CCC", align=Qt.AlignLeft))
        pr = QHBoxLayout(); pr.setSpacing(12)
        reset_btn = _btn("Reset Credentials", C_RED_BTN, size=12, h=40)
        sync_btn  = _btn("Sync to All Prefixes", C_DARK_BTN, size=12, h=40)
        reset_btn.clicked.connect(self._reset)
        sync_btn.clicked.connect(self._sync)
        pr.addWidget(reset_btn); pr.addWidget(sync_btn); pr.addStretch()
        lay.addLayout(pr)
        lay.addWidget(_hdiv())

        lay.addWidget(_lbl("Controller Profiles", 14, "#CCC", align=Qt.AlignLeft))
        cr = QHBoxLayout(); cr.setSpacing(12)
        ctrl_btn  = _btn("Re-apply Templates", C_DARK_BTN, size=12, h=40)
        guide_btn = _btn("Guide", C_BLUE_BTN, size=12, h=40)
        ctrl_btn.clicked.connect(self._apply_controller_profiles)
        guide_btn.clicked.connect(lambda: self.stack.setCurrentIndex(7))
        cr.addWidget(ctrl_btn); cr.addWidget(guide_btn); cr.addStretch()
        lay.addLayout(cr)
        lay.addWidget(_hdiv())

        lay.addWidget(_lbl("Shortcuts & Proton", 14, "#CCC", align=Qt.AlignLeft))
        sr = QHBoxLayout(); sr.setSpacing(12)
        shortcut_btn  = _btn("Repair Shortcuts",     C_DARK_BTN, size=12, h=40)
        gamecfg_btn   = _btn("Re-apply Game Configs", C_DARK_BTN, size=12, h=40)
        shortcut_btn.clicked.connect(self._repair_shortcuts)
        gamecfg_btn.clicked.connect(self._reapply_game_configs)
        sr.addWidget(shortcut_btn); sr.addWidget(gamecfg_btn); sr.addStretch()
        lay.addLayout(sr)
        lay.addWidget(_hdiv())

        lay.addWidget(_lbl("Danger Zone", 14, C_TREY, align=Qt.AlignLeft))
        dr = QHBoxLayout(); dr.setSpacing(12)
        uninstall_btn = _btn("Full Uninstall", C_RED_BTN, size=12, h=40)
        reset_cfg_btn = _btn("Reset DeckOps Config", C_RED_BTN, size=12, h=40)
        uninstall_btn.clicked.connect(self._run_uninstaller)
        reset_cfg_btn.clicked.connect(self._reset_deckops)
        dr.addWidget(uninstall_btn); dr.addWidget(reset_cfg_btn); dr.addStretch()
        lay.addLayout(dr)

        lay.addStretch()
        self.status = _lbl("", 12, C_DIM)
        lay.addWidget(self.status)
        back = _btn("<< Back", C_DARK_BTN, h=48); back.setFixedWidth(160)
        back.clicked.connect(lambda: self.stack.setCurrentIndex(5))
        bw = QHBoxLayout(); bw.addWidget(back); bw.addStretch()
        lay.addLayout(bw)

    def _toggle_music(self):
        self._music_on = not self._music_on
        if self._music_on:
            _start_audio()
            self._music_toggle.setText("Music: ON")
            self._music_toggle.setStyleSheet(
                self._music_toggle.styleSheet().replace(C_DARK_BTN, C_IW))
        else:
            _kill_audio()
            self._music_toggle.setText("Music: OFF")
            self._music_toggle.setStyleSheet(
                self._music_toggle.styleSheet().replace(C_IW, C_DARK_BTN))

    def _set_volume(self, val):
        self._vol_label.setText(f"{val}%")
        _set_audio_volume(val / 100.0)

    def _pdirs(self):
        sr = cfg.load().get("steam_root","")
        return [d for g in ALL_GAMES if g["plutonium"]
                for d in [os.path.join(sr,"steamapps","compatdata",str(g["appid"]),"pfx","drive_c","users","steamuser","AppData","Local","Plutonium")]
                if os.path.isdir(d)]

    def _reset(self):
        dirs = self._pdirs()
        if not dirs: self.status.setText("No Plutonium prefixes found."); return
        removed = [f for f in ["config.json","info.json"]
                   if os.path.exists(os.path.join(dirs[0],f)) and not os.remove(os.path.join(dirs[0],f))]
        self.status.setText(
            f"Removed {', '.join(removed)}. Launch a Plutonium game to log in, then Sync."
            if removed else "No credential files found — already clean.")

    def _sync(self):
        import shutil as _sh; dirs = self._pdirs()
        if not dirs: self.status.setText("No Plutonium prefixes found."); return
        synced = 0
        for fname in ["config.json","info.json"]:
            src = os.path.join(dirs[0], fname)
            if not os.path.exists(src): continue
            for d in dirs[1:]:
                try: _sh.copy2(src, os.path.join(d,fname)); synced += 1
                except Exception: pass
        self.status.setText(f"Synced to {synced} prefix(es) successfully.")

    def _run_uninstaller(self):
        uninstall_script = os.path.join(PROJECT_ROOT, "deckops_uninstall.sh")
        if not os.path.exists(uninstall_script):
            self.status.setText("Uninstall script not found."); return
        try:
            subprocess.Popen(["konsole", "--noclose", "-e", "bash", uninstall_script])
        except FileNotFoundError:
            try:
                subprocess.Popen(["xterm", "-hold", "-e", "bash", uninstall_script])
            except FileNotFoundError:
                self.status.setText("Could not open terminal. Run deckops_uninstall.sh manually.")

    def _apply_controller_profiles(self):
        self.status.setText("Re-applying controller profiles...")
        s = _Sigs()
        s.log.connect(lambda msg: self.status.setText(msg))
        s.done.connect(lambda ok: self.status.setText(
            "✓  Controller profiles applied." if ok else "✗  Failed — check that Steam is closed."
        ))
        def _run():
            try:
                from controller_profiles import install_controller_templates, assign_controller_profiles
                from wrapper import kill_steam, set_steam_input_enabled
                s.log.emit("Closing Steam...")
                kill_steam()
                install_controller_templates(
                    on_progress=lambda msg: s.log.emit(msg)
                )
                gyro_mode = cfg.get_gyro_mode() or "hold"
                assign_controller_profiles(
                    gyro_mode,
                    on_progress=lambda msg: s.log.emit(msg)
                )
                sr = cfg.load().get("steam_root", "")
                if sr:
                    set_steam_input_enabled(sr)
                s.done.emit(True)
                _reopen_steam_bg(sr)
            except Exception as ex:
                s.log.emit(f"✗  Failed: {ex}")
                s.done.emit(False)
        threading.Thread(target=_run, daemon=True).start()

    def _reset_deckops(self):
        cfg.reset()
        self.status.setText("Config wiped. Restart DeckOps to run setup again.")
        QTimer.singleShot(1500, lambda: self.stack.setCurrentIndex(0))

    def _repair_shortcuts(self):
        self.status.setText("Repairing shortcuts...")
        s = _Sigs()
        s.log.connect(lambda msg: self.status.setText(msg))
        s.done.connect(lambda ok: self.status.setText(
            "✓  Shortcuts repaired." if ok else "✗  Failed — check that Steam is closed."
        ))
        def _run():
            try:
                from shortcut import create_shortcuts, SHORTCUTS
                from wrapper import kill_steam, set_steam_input_enabled
                
                steam_root = cfg.load().get("steam_root", "") or find_steam_root()
                if not steam_root:
                    s.log.emit("✗  Steam not found.")
                    s.done.emit(False)
                    return
                
                s.log.emit("Closing Steam...")
                kill_steam()
                
                libs = parse_library_folders(steam_root)
                installed = find_installed_games(libs)
                
                shortcut_keys = [k for k in SHORTCUTS.keys() if k in installed]
                if not shortcut_keys:
                    s.log.emit("No shortcut-eligible games found.")
                    s.done.emit(True)
                    _reopen_steam_bg(steam_root)
                    return
                
                gyro_mode = cfg.get_gyro_mode() or "hold"
                create_shortcuts(
                    installed_games=installed,
                    selected_keys=shortcut_keys,
                    gyro_mode=gyro_mode,
                    on_progress=lambda msg: s.log.emit(msg)
                )
                set_steam_input_enabled(steam_root)
                s.done.emit(True)
                _reopen_steam_bg(steam_root)
            except Exception as ex:
                s.log.emit(f"✗  Failed: {ex}")
                s.done.emit(False)
        threading.Thread(target=_run, daemon=True).start()

    def _reapply_game_configs(self):
        self.status.setText("Re-applying game configs...")
        s = _Sigs()
        s.log.connect(lambda msg: self.status.setText(msg))
        s.done.connect(lambda ok: self.status.setText(
            "✓  Game configs applied." if ok else "✗  Failed — check that Steam is closed."
        ))
        def _run():
            try:
                from game_config import apply_game_configs
                from detect_games import find_installed_games, parse_library_folders
                from wrapper import kill_steam
                steam_root = cfg.load().get("steam_root", "") or find_steam_root()
                if not steam_root:
                    s.log.emit("✗  Steam not found.")
                    s.done.emit(False)
                    return
                s.log.emit("Closing Steam...")
                kill_steam()
                installed = find_installed_games(parse_library_folders(steam_root))
                setup_keys = list(cfg.get_setup_games().keys())
                applied, skipped, failed = apply_game_configs(
                    selected_keys=setup_keys,
                    installed_games=installed,
                    steam_root=steam_root,
                    deck_model=cfg.get_deck_model() or "oled",
                    on_progress=lambda msg: s.log.emit(msg),
                )
                s.log.emit(
                    f"✓  {applied} config(s) applied"
                    + (f", {skipped} skipped" if skipped else "")
                    + (f", {failed} failed" if failed else "")
                )
                s.done.emit(failed == 0)
                _reopen_steam_bg(steam_root)
            except Exception as ex:
                s.log.emit(f"✗  Failed: {ex}")
                s.done.emit(False)
        threading.Thread(target=_run, daemon=True).start()



# ── UpdateScreen ───────────────────────────────────────────────────────────────
class UpdateScreen(QWidget):
    """Handles both Update and Reinstall from ManagementScreen."""

    def __init__(self, stack):
        super().__init__(); self.stack = stack
        self.selected   = []
        self.steam_root = ""
        self.mode       = "update"
        self._steam_closed = threading.Event()

        lay = QVBoxLayout(self); lay.setContentsMargins(80,60,80,60); lay.setSpacing(20)
        self.title = QLabel("UPDATE"); self.title.setFont(font(36, True))
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("color:#FFF;background:transparent;")
        lay.addWidget(self.title)

        self.cur = _lbl("Preparing...", 16, "#CCC"); lay.addWidget(self.cur)
        self.bar = QProgressBar(); self.bar.setMaximum(100); self.bar.setTextVisible(False)
        self.bar.setFixedHeight(22)
        bw = QHBoxLayout(); bw.setContentsMargins(60,0,60,0); bw.addWidget(self.bar)
        lay.addLayout(bw)

        self.log = QPlainTextEdit(); self.log.setReadOnly(True)
        self.log.setFont(font(11))
        self.log.setStyleSheet("QPlainTextEdit{color:#666677;background:transparent;border:none;padding:10px;}")
        lay.addWidget(self.log, stretch=1)

        self.steam_btn = _btn("Steam is closed  ✓", C_TREY, size=13, h=52)
        self.steam_btn.setFixedWidth(360); self.steam_btn.setVisible(False)
        self.steam_btn.clicked.connect(lambda: self._steam_closed.set())
        sw = QHBoxLayout(); sw.addStretch(); sw.addWidget(self.steam_btn); sw.addStretch()
        lay.addLayout(sw)

        self.back_btn = _btn("<< Back to My Games", C_DARK_BTN, h=48)
        self.back_btn.setFixedWidth(220); self.back_btn.setVisible(False)
        self.back_btn.clicked.connect(self._go_back)
        bk = QHBoxLayout(); bk.addStretch(); bk.addWidget(self.back_btn); bk.addStretch()
        lay.addLayout(bk)

        self._s = _Sigs()
        self._s.progress.connect(lambda p,m: (self.bar.setValue(p), self.cur.setText(m)))
        self._s.log.connect(self._append_log)
        self._s.done.connect(self._on_done)
        self._s.plut_wait.connect(lambda: self.steam_btn.setVisible(True))
        self._s.plut_go.connect(lambda: self.steam_btn.setVisible(False))

    def _append_log(self, text):
        self.log.appendPlainText(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def showEvent(self, e):
        super().showEvent(e)
        self.title.setText("REINSTALL" if self.mode == "reinstall" else "UPDATE")
        self.bar.setValue(0); self.log.clear()
        self.steam_btn.setVisible(False); self.back_btn.setVisible(False)
        self._steam_closed.clear()
        QTimer.singleShot(400, lambda: threading.Thread(target=self._run, daemon=True).start())

    def _on_done(self, _):
        self.cur.setText("Done!")
        self.back_btn.setVisible(True)
        _reopen_steam_bg(cfg.load().get("steam_root", "") or find_steam_root())

    def _go_back(self):
        root = find_steam_root()
        self.stack.widget(5).set_installed(find_installed_games(parse_library_folders(root)))
        self.stack.setCurrentIndex(5)

    def _run(self):
        from wrapper import get_proton_path, find_compatdata, kill_steam
        from iw4x import install_iw4x
        from cod4x import install_cod4x
        from iw3sp import install_iw3sp
        from plutonium import install_plutonium

        has_cod4  = any(KEY_CLIENT.get(k) in ("cod4x", "iw3sp") for k, _, _ in self.selected)
        has_iw4x  = any(KEY_CLIENT.get(k) == "iw4x" for k, _, _ in self.selected)
        has_plut  = any(KEY_CLIENT.get(k) == "plutonium" for k, _, _ in self.selected)
        proton    = get_proton_path(self.steam_root)
        total     = len(self.selected)

        if not has_plut:
            self._s.progress.emit(5, "Closing Steam...")
            self._s.log.emit("Closing Steam...")
            try:
                kill_steam()
                self._s.log.emit("  ✓ Steam closed.")
            except Exception as ex:
                self._s.log.emit(f"  Could not close Steam: {ex}")

        # Clean up stale launch options from older DeckOps versions
        if has_cod4 or has_iw4x:
            try:
                from wrapper import clear_launch_options
                for stale_appid in ["7940", "10190"]:
                    clear_launch_options(self.steam_root, stale_appid)
            except Exception:
                pass

        for idx, (key, gd, game) in enumerate(self.selected):
            if not game:
                continue
            base_name = gd["base"]
            bp = int(idx / total * 90)
            self._s.progress.emit(bp, f"{'Reinstalling' if self.mode == 'reinstall' else 'Updating'} {base_name}...")
            def op(pct, msg, _b=bp): self._s.progress.emit(_b + int(pct / 100 * (90 // total)), msg)
            c = KEY_CLIENT.get(key, gd.get("client", ""))
            try:
                from plutonium import GAME_META as _PLUT_META
                _appid = _PLUT_META[key][0] if (c == "plutonium" and key in _PLUT_META) else gd["appid"]
                compat = find_compatdata(self.steam_root, _appid)
                if c == "cod4x":
                    install_cod4x(game, self.steam_root, proton, compat, op,
                                  appid=gd["appid"])
                elif c == "iw3sp":
                    install_iw3sp(game, self.steam_root, proton, compat, op)
                elif c == "iw4x":
                    install_iw4x(game, self.steam_root, proton, compat, op)
                elif c == "plutonium":
                    install_plutonium(game, key, self.steam_root, proton, compat, op)
                self._s.log.emit(f"✓  {base_name} ({key}) done")
            except Exception as ex:
                self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        self._s.progress.emit(100, "All done!")
        self._s.done.emit(True)


# ── App ────────────────────────────────────────────────────────────────────────
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

class DeckOpsWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("DeckOps"); self.resize(1280,800); self.setMinimumSize(800,500)
        self.stack = QStackedWidget(); self.setCentralWidget(self.stack)
        for cls in [BootstrapScreen,IntroScreen,WelcomeScreen,SetupScreen,InstallScreen,ManagementScreen,ConfigureScreen,ControllerInfoScreen,UpdateScreen]:
            self.stack.addWidget(cls(self.stack))
        self.stack.setCurrentIndex(0)

    def closeEvent(self, e):
        _kill_audio()
        super().closeEvent(e)

def run():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    _load_font()
    app.setStyleSheet(_app_style())
    win = DeckOpsWindow()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    run()
