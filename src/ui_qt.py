"""
ui_qt.py — DeckOps PyQt5 UI
Replaces ui.py (Kivy). All backend logic unchanged.
PyQt5 ships with KDE on every Steam Deck — zero install needed.
"""

import sys, os, subprocess, threading
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QPushButton, QCheckBox, QProgressBar,
    QFrame, QSizePolicy,
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
MUSIC_PATH   = os.path.join(PROJECT_ROOT, "assets", "music", "background.ogg")

os.makedirs(HEADERS_DIR, exist_ok=True)

C_BG       = "#141416"
C_CARD     = "#1E1E26"
C_IW       = "#6DC62B"
C_TREY     = "#F47B20"
C_DIM      = "#888899"
C_DARK_BTN = "#33333F"
C_RED_BTN  = "#7A1515"
C_BLUE_BTN = "#1A5FAA"

_FONT_FAMILY      = "Sans Serif"  # body/UI — variable font
_FONT_FAMILY_DISP = "Sans Serif"  # display titles — CndBlk static instance
_FONT_LOADED      = False

def _load_font():
    """
    Load Science Gothic fonts. Must be called after QApplication is created.

    Two fonts are used:
      ScienceGothic-CndBlk.ttf — Condensed Black static instance.
                                  Used for DECKOPS / COMBATonDECK titles.
                                  PyQt5 renders variable font weight axes
                                  unreliably; a static instance is required
                                  to guarantee the Black + Condensed look.
      ScienceGothic-VF.ttf     — Variable font for body/UI text.
                                  Falls back to CndBlk if not yet downloaded.
    """
    global _FONT_FAMILY, _FONT_FAMILY_DISP, _FONT_LOADED

    cnd_blk = os.path.join(FONTS_DIR, "ScienceGothic-CndBlk.ttf")
    if os.path.exists(cnd_blk):
        fid = QFontDatabase.addApplicationFont(cnd_blk)
        fams = QFontDatabase.applicationFontFamilies(fid)
        if fams:
            _FONT_FAMILY_DISP = fams[0]

    vf = os.path.join(FONTS_DIR, "ScienceGothic-VF.ttf")
    if os.path.exists(vf):
        fid = QFontDatabase.addApplicationFont(vf)
        fams = QFontDatabase.applicationFontFamilies(fid)
        if fams:
            _FONT_FAMILY = fams[0]
    else:
        _FONT_FAMILY = _FONT_FAMILY_DISP  # VF not yet downloaded — use CndBlk

    if _FONT_FAMILY_DISP == "Sans Serif" and _FONT_FAMILY != "Sans Serif":
        _FONT_FAMILY_DISP = _FONT_FAMILY   # CndBlk missing — best effort

    _FONT_LOADED = True

def font(size=14, bold=False, weight=None, display=False):
    """
    Return a QFont.
    display=True  → Condensed Black static instance (titles/headings)
    display=False → variable font (body/buttons)
    weight overrides bold when provided.
    """
    family = _FONT_FAMILY_DISP if display else _FONT_FAMILY
    f = QFont(family, size)
    if weight is not None:
        f.setWeight(weight)
    else:
        f.setBold(bold)
    return f

ALL_GAMES = [
    {"base":"Call of Duty 4: Modern Warfare","keys":["cod4mp"],"appid":7940,"dev":"iw","client":"cod4x","plutonium":False,
     "launch_note":"Launch Multiplayer at least once through Steam before continuing."},
    {"base":"Call of Duty: Modern Warfare 2","keys":["iw4mp"],"appid":10190,"dev":"iw","client":"iw4x","plutonium":False,
     "launch_note":"Launch Multiplayer at least once through Steam before continuing."},
    {"base":"Call of Duty: Modern Warfare 3","keys":["iw5mp"],"appid":42690,"dev":"iw","client":"plutonium","plutonium":True,
     "launch_note":"Launch Multiplayer at least once through Steam before continuing."},
    {"base":"Call of Duty: World at War","keys":["t4sp","t4mp"],"appid":10090,"dev":"trey","client":"plutonium","plutonium":True,
     "launch_note":"Launch both Campaign and Multiplayer through Steam before continuing."},
    {"base":"Call of Duty: Black Ops","keys":["t5sp","t5mp"],"appid":42700,"dev":"trey","client":"plutonium","plutonium":True,
     "launch_note":"Launch both Campaign and Multiplayer through Steam before continuing."},
    {"base":"Call of Duty: Black Ops II","keys":["t6mp","t6zm"],"appid":202990,"dev":"trey","client":"plutonium","plutonium":True,
     "launch_note":"Launch both Multiplayer and Zombies through Steam before continuing."},
]

KEY_EXES = {
    "cod4mp":"iw3mp.exe","iw4mp":"iw4mp.exe","iw5mp":"iw5mp.exe",
    "t4sp":"CoDWaW.exe","t4mp":"CoDWaWmp.exe",
    "t5sp":"BlackOps.exe","t5mp":"BlackOpsMP.exe",
    "t6zm":"t6zm.exe","t6mp":"t6mp.exe",
}

# Hardcoded button labels per game key — avoids relying on name string parsing
KEY_LABELS = {
    "cod4mp": "MULTIPLAYER",
    "iw4mp":  "MULTIPLAYER",
    "iw5mp":  "MULTIPLAYER",
    "t4sp":   "CAMPAIGN / ZOMBIES",
    "t4mp":   "MULTIPLAYER",
    "t5sp":   "CAMPAIGN / ZOMBIES",
    "t5mp":   "MULTIPLAYER",
    "t6zm":   "ZOMBIES",
    "t6mp":   "MULTIPLAYER",
}

# Single-player header images (different Steam appids for SP vs MP versions)
SP_IMAGE_URLS = {
    7940:   "https://shared.steamstatic.com/store_item_assets/steam/apps/7940/header.jpg",
    10190:  "https://shared.steamstatic.com/store_item_assets/steam/apps/10180/header.jpg",
    42690:  "https://shared.steamstatic.com/store_item_assets/steam/apps/42680/header.jpg",
    10090:  "https://shared.steamstatic.com/store_item_assets/steam/apps/10090/header.jpg",
    42700:  "https://shared.steamstatic.com/store_item_assets/steam/apps/42700/header.jpg",
    202990: "https://shared.steamstatic.com/store_item_assets/steam/apps/202970/header.jpg",
}

# ── Card proportions (mirrors Kivy version) ────────────────────────────────
# Card height is derived from card width so layout scales at any resolution.
IMG_RATIO = 215 / 460   # image height / card width
BTN_RATIO = 0.20        # button height / image height
BTN_SLOTS = 2           # always reserve 2 button rows so all cards match height
BTN_GAP   = 4           # px gap between buttons on multi-mode (Treyarch) cards
CARD_COLS = 3           # always lay out 3 columns; pad with spacers if fewer games

def _wrapper_installed(key, install_dir):
    exe = KEY_EXES.get(key)
    if not exe or not install_dir: return False
    path = os.path.join(install_dir, exe)
    if not os.path.exists(path): return False
    if os.path.exists(path + ".bak"): return True
    try:
        with open(path,"rb") as f: return f.read(11) == b"#!/bin/bash"
    except OSError: return False

def _header_path(appid):
    return os.path.join(HEADERS_DIR, f"{appid}.jpg")

def _btn(text, bg, fg="#FFF", size=14, bold=True, h=52):
    b = QPushButton(text); b.setFont(font(size,bold)); b.setFixedHeight(h)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet(f"""
        QPushButton{{background:{bg};color:{fg};border:none;border-radius:7px;padding:0 18px;}}
        QPushButton:hover{{background:{bg}CC;}}
        QPushButton:pressed{{background:{bg}88;}}
        QPushButton:disabled{{background:#2A2A36;color:#555566;}}
    """)
    return b

def _lbl(text, size=15, color="#FFF", bold=False, align=Qt.AlignCenter, wrap=True):
    w = QLabel(text); w.setFont(font(size,bold)); w.setAlignment(align)
    w.setWordWrap(wrap); w.setStyleSheet(f"color:{color};background:transparent;")
    return w

def _hdiv():
    d = QFrame(); d.setFrameShape(QFrame.HLine); d.setFixedHeight(1)
    d.setStyleSheet("background:#252530;border:none;"); return d

def _sp(h):
    w = QWidget(); w.setFixedHeight(h); w.setStyleSheet("background:transparent;"); return w

def _title_block(lay, main_size=64):
    """
    Recreates the original Kivy title exactly:
      DECKOPS          - main_size pt, Condensed Black, white
      COMBATonDECK     - 32pt Condensed Black, orange; 'on' is 18pt
    Uses _FONT_FAMILY_DISP (CndBlk static instance) so PyQt5 actually
    renders the heavy condensed weight instead of the VF default.
    """
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
        f'<span style="font-family:\'{_FONT_FAMILY_DISP}\'; font-size:32pt; color:{C_TREY};">'
        f'COMBAT'
        f'<span style="font-size:18pt;">on</span>'
        f'DECK'
        f'</span>'
    )
    lay.addWidget(sub)

MUSIC_URL = "https://archive.org/download/adrenaline-klickaud/Adrenaline_KLICKAUD.mp3"

_audio_proc = None   # global handle so _kill_audio can reach it anywhere

def _kill_audio():
    global _audio_proc
    if _audio_proc and _audio_proc.poll() is None:
        try:
            import signal as _sig
            os.killpg(os.getpgid(_audio_proc.pid), _sig.SIGTERM)
        except (ProcessLookupError, OSError):
            try: _audio_proc.terminate()
            except Exception: pass
    _audio_proc = None

def _start_audio():
    global _audio_proc
    # Download and cache music on first run
    if not os.path.exists(MUSIC_PATH):
        def _fetch():
            try:
                import urllib.request
                os.makedirs(os.path.dirname(MUSIC_PATH), exist_ok=True)
                urllib.request.urlretrieve(MUSIC_URL, MUSIC_PATH)
            except Exception:
                pass
        threading.Thread(target=_fetch, daemon=True).start()
        source = MUSIC_URL
    else:
        source = MUSIC_PATH
    try:
        _audio_proc = subprocess.Popen(
            ["mpv", "--no-video", "--loop", "--volume=75", source],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        return _audio_proc
    except FileNotFoundError:
        return None

class _Sigs(QObject):
    progress  = pyqtSignal(int, str)
    log       = pyqtSignal(str)
    done      = pyqtSignal(bool)
    plut_wait = pyqtSignal()
    plut_go   = pyqtSignal()

# ── BootstrapScreen ────────────────────────────────────────────────────────
class BootstrapScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack = stack
        lay = QVBoxLayout(self); lay.setContentsMargins(80,80,80,80); lay.setSpacing(14)
        lay.addStretch()
        _title_block(lay)
        lay.addStretch()
        self.status = _lbl("Preparing...", 14, C_DIM)
        lay.addWidget(self.status)
        self.bar = QProgressBar(); self.bar.setMaximum(100); self.bar.setTextVisible(False)
        self.bar.setFixedHeight(14)
        bw = QHBoxLayout(); bw.addStretch(); bw.addWidget(self.bar,6); bw.addStretch()
        lay.addLayout(bw); lay.addSpacing(50)

    def showEvent(self, e):
        super().showEvent(e)
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
        _load_font()
        if cfg.is_first_run():
            self.stack.setCurrentIndex(1)
        else:
            root = find_steam_root()
            self.stack.widget(5).set_installed(find_installed_games(parse_library_folders(root)))
            self.stack.setCurrentIndex(5)

# ── IntroScreen ────────────────────────────────────────────────────────────
class IntroScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack = stack
        lay = QVBoxLayout(self); lay.setContentsMargins(80,60,80,60); lay.setSpacing(16)
        _title_block(lay)
        lay.addSpacing(8)
        lay.addWidget(_lbl(
            "DeckOps sets up community multiplayer clients for your Call of Duty games "
            "on Steam Deck, so you can play online with the best possible performance "
            "and shader cache benefits.", 15, "#CCCCCC"))
        lay.addSpacing(6)
        for warn in [
            "⚠   Before continuing, launch each game through Steam at least once — "
            "exactly these modes: CoD4 (Multiplayer), MW2 (Multiplayer), MW3 (Multiplayer), "
            "WaW (Campaign AND Multiplayer), BO1 (Campaign AND Multiplayer), "
            "BO2 (Zombies AND Multiplayer). "
            "This creates the Proton prefix and starts shader cache downloads. "
            "Skipping this is the #1 cause of install failures.",
            "⚠   If you plan to play Plutonium titles (WaW, BO1, BO2, MW3), "
            "create a free Plutonium account at plutonium.pw before continuing.",
        ]:
            lay.addWidget(_lbl(warn, 14, C_TREY, align=Qt.AlignLeft))
        lay.addSpacing(16)
        lay.addWidget(_lbl("Which Steam Deck do you have?", 19, "#FFF", bold=True))
        row = QHBoxLayout(); row.setSpacing(20)
        oled = _btn("Steam Deck OLED", C_IW, size=16, h=64)
        lcd  = _btn("Steam Deck LCD",  C_DARK_BTN, size=16, h=64)
        oled.clicked.connect(lambda: (cfg.set_deck_model("oled"), self.stack.setCurrentIndex(2)))
        lcd.clicked.connect( lambda: (cfg.set_deck_model("lcd"),  self.stack.setCurrentIndex(2)))
        row.addWidget(oled); row.addWidget(lcd); lay.addLayout(row); lay.addStretch()

# ── WelcomeScreen ──────────────────────────────────────────────────────────
class WelcomeScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.installed={}; self.steam_root=""
        lay = QVBoxLayout(self); lay.setContentsMargins(80,50,80,50); lay.setSpacing(14)
        top = QHBoxLayout()
        back = _btn("<< Back", C_DARK_BTN, size=12, h=36); back.setFixedWidth(110)
        back.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        top.addWidget(back); top.addStretch(); lay.addLayout(top)
        _title_block(lay)
        lay.addWidget(_lbl("Bringing the Golden Age of FPS to your Deck", 18, C_DIM))
        lay.addStretch()
        self.status  = _lbl("Looking for Steam...", 16, C_IW)
        self.bar     = QProgressBar(); self.bar.setMaximum(100)
        self.bar.setTextVisible(False); self.bar.setFixedHeight(18)
        self.results = _lbl("", 15, C_IW)
        lay.addWidget(self.status)
        bw = QHBoxLayout(); bw.addStretch(); bw.addWidget(self.bar,7); bw.addStretch()
        lay.addLayout(bw); lay.addWidget(self.results); lay.addStretch()
        self.cont = _btn("Continue >>", C_IW, size=16, h=60); self.cont.setFixedWidth(340)
        self.cont.setVisible(False); self.cont.clicked.connect(self._go_next)
        cw = QHBoxLayout(); cw.addStretch(); cw.addWidget(self.cont); cw.addStretch()
        lay.addLayout(cw)

    def showEvent(self, e):
        super().showEvent(e)
        self.bar.setValue(0); self.results.setText(""); self.cont.setVisible(False)
        self.status.setText("Looking for Steam...")
        self.status.setStyleSheet(f"color:{C_IW};background:transparent;")
        QTimer.singleShot(300, self._scan)

    def _scan(self):
        self.bar.setValue(10); self.steam_root = find_steam_root()
        if not self.steam_root:
            self.status.setText("Steam not found! Is it installed?")
            self.status.setStyleSheet(f"color:{C_TREY};background:transparent;")
            self.bar.setValue(100); return
        self.status.setText(f"Found Steam at {self.steam_root}"); self.bar.setValue(40)
        QTimer.singleShot(200, self._scan_games)

    def _scan_games(self):
        self.status.setText("Scanning for games..."); self.bar.setValue(70)
        libs = parse_library_folders(self.steam_root)
        self.installed = find_installed_games(libs)
        if not cfg.is_oled():
            pk = {k for g in ALL_GAMES if g["plutonium"] for k in g["keys"]}
            self.installed = {k:v for k,v in self.installed.items() if k not in pk}
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

# ── SetupScreen ────────────────────────────────────────────────────────────
class SetupScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.installed={}; self.steam_root=""; self._checks={}
        lay = QVBoxLayout(self); lay.setContentsMargins(60,40,60,40); lay.setSpacing(14)
        t = QLabel("SETUP"); t.setFont(font(40,True)); t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("color:#FFF;background:transparent;"); lay.addWidget(t)
        lay.addWidget(_lbl(
            "Choose which games to set up. DeckOps will download and install "
            "the community client for each selected game.", 14, C_DIM))
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._lw = QWidget(); self._ll = QVBoxLayout(self._lw)
        self._ll.setSpacing(0); self._ll.addStretch()
        scroll.setWidget(self._lw); lay.addWidget(scroll, stretch=1)
        self.warning = _lbl("", 13, C_TREY, align=Qt.AlignLeft)
        self.warning.setVisible(False); lay.addWidget(self.warning)
        brow = QHBoxLayout(); brow.setSpacing(16)
        back = _btn("<< Back", C_DARK_BTN, h=56); back.setFixedWidth(180)
        back.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        self.inst_btn = _btn("Install Selected >>", C_IW, h=56)
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
        for gd in ALL_GAMES:
            if gd["plutonium"] and not cfg.is_oled(): continue
            ik = [k for k in gd["keys"] if k in self.installed]
            if not ik: continue
            base = gd["base"]; done = any(cfg.is_game_setup(k) for k in ik)
            color = C_IW if gd["dev"]=="iw" else C_TREY
            row = QHBoxLayout(); row.setSpacing(16); row.setContentsMargins(8,8,8,8)
            cb = QCheckBox(); cb.setChecked(not done); self._checks[base] = (cb, gd)
            name = _lbl(base, 16, "#666677" if done else "#FFF", align=Qt.AlignLeft, wrap=False)
            badge = QPushButton(gd["client"].upper()); badge.setFont(font(11,True))
            badge.setFixedSize(108,30); badge.setEnabled(False)
            badge.setStyleSheet(f"QPushButton{{background:{color};color:#FFF;border:none;border-radius:6px;}}QPushButton:disabled{{background:{color};color:#FFF;}}")
            row.addWidget(cb); row.addWidget(name, stretch=1); row.addWidget(badge)
            if done:
                tick = _lbl("✓ set up", 13, C_IW, align=Qt.AlignRight, wrap=False)
                tick.setFixedWidth(80); row.addWidget(tick)
            cw = QWidget(); cw.setLayout(row); cw.setFixedHeight(52)
            self._ll.insertWidget(self._ll.count()-1, cw)
            self._ll.insertWidget(self._ll.count()-1, _hdiv())

    def _has_prefix(self, appid):
        return os.path.isdir(os.path.join(self.steam_root,"steamapps","compatdata",str(appid)))

    def _go_install(self):
        self.warning.setVisible(False)
        selected, no_prefix = [], []
        for base, (cb, gd) in self._checks.items():
            if not cb.isChecked(): continue
            ik = [k for k in gd["keys"] if k in self.installed]
            if not ik: continue
            if not self._has_prefix(gd["appid"]):
                no_prefix.append((gd["base"], gd.get("launch_note",""))); continue
            for k in ik: selected.append((k, gd, self.installed[k]))
        if no_prefix:
            lines = []
            for name, note in no_prefix:
                lines.append(f"• {name}")
                if note: lines.append(f"   {note}")
            self.warning.setText(
                "⚠  These games have never been launched through Steam:\n\n" +
                "\n".join(lines) +
                "\n\nLaunch each through Steam first, then return here.")
            self.warning.setVisible(True); return
        if not selected: return
        # install_plutonium() handles the full bootstrapper + login flow automatically.
        # It downloads plutonium.exe, runs it through Proton, waits for the user to
        # log in and close the launcher, then copies the install to all other prefixes.
        s = self.stack.widget(4); s.selected=selected; s.steam_root=self.steam_root
        self.stack.setCurrentIndex(4)

# ── InstallScreen ──────────────────────────────────────────────────────────
class InstallScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.selected=[]; self.steam_root=""
        self._plut_event = threading.Event()

        lay = QVBoxLayout(self); lay.setContentsMargins(80,60,80,60); lay.setSpacing(20)
        t = QLabel("INSTALLING"); t.setFont(font(40,True)); t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("color:#FFF;background:transparent;"); lay.addWidget(t)
        self.cur = _lbl("Preparing...", 18, "#CCC"); lay.addWidget(self.cur)
        self.bar = QProgressBar(); self.bar.setMaximum(100); self.bar.setTextVisible(False)
        self.bar.setFixedHeight(22)
        bw = QHBoxLayout(); bw.setContentsMargins(60,0,60,0); bw.addWidget(self.bar)
        lay.addLayout(bw)
        self.stat = _lbl("", 14, C_IW); lay.addWidget(self.stat)
        ls = QScrollArea(); ls.setWidgetResizable(True)
        self.log = QLabel(""); self.log.setFont(font(12)); self.log.setAlignment(Qt.AlignTop|Qt.AlignLeft)
        self.log.setWordWrap(True); self.log.setStyleSheet("color:#666677;background:transparent;padding:10px;")
        ls.setWidget(self.log); lay.addWidget(ls, stretch=1)

        # Plutonium login confirmation button
        self.plut_btn = _btn("I've logged in and closed Plutonium  ✓", C_TREY, size=14, h=56)
        self.plut_btn.setFixedWidth(460); self.plut_btn.setVisible(False)
        self.plut_btn.clicked.connect(self._confirm_plut)
        pw = QHBoxLayout(); pw.addStretch(); pw.addWidget(self.plut_btn); pw.addStretch()
        lay.addLayout(pw)

        # Add to Steam prompt (shown after install completes)
        self._steam_row = QWidget(); sr = QHBoxLayout(self._steam_row); sr.setSpacing(16)
        self._steam_row.setVisible(False)
        add_btn  = _btn("Add DeckOps to Steam", C_BLUE_BTN, size=14, h=52); add_btn.setFixedWidth(280)
        skip_btn = _btn("Skip", C_DARK_BTN, size=14, h=52); skip_btn.setFixedWidth(120)
        add_btn.clicked.connect(self._add_to_steam)
        skip_btn.clicked.connect(self._go_games)
        sr.addStretch(); sr.addWidget(add_btn); sr.addWidget(skip_btn); sr.addStretch()
        lay.addWidget(self._steam_row)

        self.done_btn = _btn("Let's Play >>", C_IW, size=16, h=60); self.done_btn.setFixedWidth(320)
        self.done_btn.setVisible(False); self.done_btn.clicked.connect(self._go_games)
        dw = QHBoxLayout(); dw.addStretch(); dw.addWidget(self.done_btn); dw.addStretch()
        lay.addLayout(dw)

        self._s = _Sigs()
        self._s.progress.connect(lambda p,m: (self.bar.setValue(p), self.cur.setText(m)))
        self._s.log.connect(lambda l: self.log.setText(self.log.text()+l+"\n"))
        self._s.done.connect(self._on_done)
        self._s.plut_wait.connect(lambda: self.plut_btn.setVisible(True))
        self._s.plut_go.connect(lambda: self.plut_btn.setVisible(False))

    def showEvent(self, e):
        super().showEvent(e)
        self.bar.setValue(0); self.log.setText("")
        self.done_btn.setVisible(False); self.plut_btn.setVisible(False)
        self._steam_row.setVisible(False)
        self._plut_event.clear()
        QTimer.singleShot(400, lambda: threading.Thread(target=self._run, daemon=True).start())

    def _confirm_plut(self):
        self._plut_event.set()

    def _on_done(self, _):
        # Show Add to Steam prompt before Let's Play
        self._steam_row.setVisible(True)
        self.cur.setText("Add DeckOps to Steam for easy access from Game Mode?")

    def _add_to_steam(self):
        try:
            _write_steam_shortcut()
            self._steam_row.setVisible(False)
            self.cur.setText("Added! Restart Steam to see DeckOps in your library.")
        except Exception as ex:
            self.cur.setText(f"Could not add to Steam: {ex}")
        QTimer.singleShot(2000, self._show_lets_play)

    def _show_lets_play(self):
        self._steam_row.setVisible(False)
        self.done_btn.setVisible(True)

    def _run(self):
        from wrapper import get_proton_path, find_compatdata
        from plutonium import launch_bootstrapper, is_plutonium_ready, install_plutonium
        from cod4x import install_cod4x
        from iw4x import install_iw4x

        proton = get_proton_path(self.steam_root)

        has_plut = any(gd["client"] == "plutonium" for _, gd, _ in self.selected)
        if has_plut and not is_plutonium_ready():
            self._s.progress.emit(2, "Launching Plutonium — please log in...")
            self._s.log.emit(
                "Plutonium is launching now.\n"
                "  1. Log in with your Plutonium account\n"
                "  2. Wait for it to finish downloading\n"
                "  3. Close the Plutonium window\n"
                "  4. Click the button below to continue"
            )
            try:
                launch_bootstrapper(proton, on_progress=lambda p,m: self._s.progress.emit(p,m))
            except Exception as ex:
                self._s.log.emit(f"✗  Plutonium launch failed: {ex}")
                self._s.progress.emit(100,"Setup failed."); self._s.done.emit(True); return

            self._s.plut_wait.emit()
            self._plut_event.wait()
            self._s.plut_go.emit()

            if not is_plutonium_ready():
                self._s.log.emit(
                    "✗  Plutonium does not appear to be fully set up.\n"
                    "   Make sure you logged in and let it finish downloading."
                )
                self._s.progress.emit(100,"Setup incomplete."); self._s.done.emit(True); return

            self._s.log.emit("✓  Plutonium ready — continuing with game installs...")

        total = len(self.selected)
        for idx,(key,gd,game) in enumerate(self.selected):
            bp = int(idx/total*100); sp = int(1/total*100)
            self._s.progress.emit(bp, f"Setting up {gd['base']}  ({idx+1}/{total})")
            def op(pct,msg,_b=bp,_s=sp): self._s.progress.emit(_b+int(pct/100*_s), msg)
            try:
                compat = find_compatdata(self.steam_root, gd["appid"])
                c = gd["client"]
                if c=="cod4x":   install_cod4x(game,self.steam_root,proton,compat,op)
                elif c=="iw4x":  install_iw4x(game,self.steam_root,proton,compat,op)
                elif c=="plutonium": install_plutonium(game,key,self.steam_root,proton,compat,op)
                cfg.mark_game_setup(key, c); self._s.log.emit(f"✓  {gd['base']} done")
            except Exception as ex:
                self._s.log.emit(f"✗  {gd['base']} failed: {ex}")

        cfg.complete_first_run(self.steam_root)
        self._s.progress.emit(100,"All done!"); self._s.done.emit(True)

    def _go_games(self):
        self._steam_row.setVisible(False)
        root = find_steam_root()
        self.stack.widget(5).set_installed(find_installed_games(parse_library_folders(root)))
        self.stack.setCurrentIndex(5)

# ── GameCard ───────────────────────────────────────────────────────────────
class GameCard(QFrame):
    """
    Card height is derived from card width using the same ratios as the
    original Kivy version:
        img_h  = width * IMG_RATIO   (215/460 ≈ 0.467)
        btn_h  = img_h * BTN_RATIO   (0.20)
        total  = img_h + BTN_SLOTS * btn_h

    resizeEvent() calls _recalc() whenever the card is resized by the grid,
    so the layout stays correct at every window size and resolution.
    """
    def __init__(self, gd, installed, on_select, on_configure, parent=None):
        super().__init__(parent)
        color = C_IW if gd["dev"]=="iw" else C_TREY
        self._color = color; self._appid = gd["appid"]
        self.setObjectName("GC")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        ik = [k for k in gd["keys"] if k in installed]
        if "Black Ops II" in gd["base"]:
            ik = sorted(ik, key=lambda k: 0 if "zm" in k else 1)
        ready = [k for k in ik if _wrapper_installed(k, installed[k].get("install_dir", ""))]
        is_installed = len(ready) > 0

        # Dim border for uninstalled cards
        border_color = color if is_installed else "#333344"
        self.setStyleSheet(
            f"QFrame#GC{{background:{C_CARD};border-top:3px solid {border_color};border-radius:8px;}}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header image — dimmed if not installed. Store raw pixmap and rescale
        # in _recalc() using KeepAspectRatioByExpanding so images fill correctly.
        self._img = QLabel()
        self._img.setAlignment(Qt.AlignCenter)
        self._img.setStyleSheet("background:#0A0A10;border:none;border-radius:0px;")
        if not is_installed:
            effect = QGraphicsOpacityEffect(); effect.setOpacity(0.35)
            self._img.setGraphicsEffect(effect)
        lay.addWidget(self._img)
        self._raw_pixmap = None

        cached = _header_path(gd["appid"])
        if os.path.exists(cached):
            self._raw_pixmap = QPixmap(cached)
        else:
            threading.Thread(target=self._fetch, args=(gd["appid"],), daemon=True).start()

        self._play_btns = []
        self._btn_gaps  = []   # small spacers between multi-mode buttons

        if is_installed:
            for i, key in enumerate(ready):
                # Small gap between buttons on Treyarch (multi-mode) cards
                if i > 0:
                    gap = QWidget(); gap.setStyleSheet(f"background:{C_BG};border:none;")
                    lay.addWidget(gap); self._btn_gaps.append(gap)
                mode = KEY_LABELS.get(key, key.upper())
                b = QPushButton(mode); b.setFont(font(12, True))
                b.setCursor(Qt.PointingHandCursor)
                b.setStyleSheet(
                    f"QPushButton{{background:{color};color:#FFF;border:none;border-radius:0px;}}"
                    f"QPushButton:hover{{background:{color}CC;}}"
                    f"QPushButton:pressed{{background:{color}88;}}"
                )
                b.clicked.connect(lambda _, k=key, g=installed[key]: on_select(k, g))
                lay.addWidget(b)
                self._play_btns.append(b)
        else:
            # Not installed — CONFIGURE button spanning full button area
            b = QPushButton("CONFIGURE"); b.setFont(font(12, True))
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton{{background:{C_BLUE_BTN};color:#FFF;border:none;border-radius:0px;}}"
                f"QPushButton:hover{{background:{C_BLUE_BTN}CC;}}"
                f"QPushButton:pressed{{background:{C_BLUE_BTN}88;}}"
            )
            b.clicked.connect(lambda _: on_configure(gd))
            lay.addWidget(b)
            self._play_btns.append(b)

        # Seed an initial size — will be corrected by resizeEvent once placed
        self._recalc(460)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._recalc(self.width())

    def _recalc(self, w):
        """Recompute all heights from current card width."""
        if w <= 0:
            return
        img_h = int(w * IMG_RATIO)
        btn_h = int(img_h * BTN_RATIO)
        self._img.setFixedSize(w, img_h)
        # Scale pixmap to fill width, cropping vertically to maintain aspect ratio
        if self._raw_pixmap:
            scaled = self._raw_pixmap.scaled(
                w, img_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = (scaled.width()  - w)    // 2
            y = (scaled.height() - img_h) // 2
            self._img.setPixmap(scaled.copy(x, y, w, img_h))
        n = len(self._play_btns)
        if n == 1:
            # Single button (IW games or uninstalled) — spans full button area
            total_btn_h = BTN_SLOTS * btn_h
            self._play_btns[0].setFixedHeight(total_btn_h)
        else:
            # Multi-mode (Treyarch) — two buttons with a small gap between them
            total_btn_h = n * btn_h + BTN_GAP
            for b in self._play_btns:
                b.setFixedHeight(btn_h)
            for g in self._btn_gaps:
                g.setFixedHeight(BTN_GAP)
        self.setFixedHeight(img_h + total_btn_h)

    def _fetch(self, appid):
        import urllib.request
        dest = _header_path(appid)
        url  = SP_IMAGE_URLS.get(appid,
               f"https://shared.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DeckOps"})
            with urllib.request.urlopen(req, timeout=15) as r:
                with open(dest, "wb") as f: f.write(r.read())
            def _apply():
                self._raw_pixmap = QPixmap(dest)
                self._recalc(self.width())
            QTimer.singleShot(0, _apply)
        except Exception: pass

# ── GameScreen ─────────────────────────────────────────────────────────────
class GameScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.installed={}
        lay = QVBoxLayout(self); lay.setContentsMargins(14,10,14,10); lay.setSpacing(8)

        # Header: centered title + fixed-width settings button
        hdr = QWidget(); hdr.setFixedHeight(40)
        title = QLabel("SELECT A GAME"); title.setParent(hdr)
        title.setFont(font(20, display=True))
        title.setStyleSheet("color:#FFF;background:transparent;")
        title.setAlignment(Qt.AlignCenter)
        title.setGeometry(0, 2, 1280, 36)
        cb = _btn("SETTINGS", C_BLUE_BTN, size=12, h=36); cb.setFixedWidth(150)
        cb.setParent(hdr)
        cb.clicked.connect(lambda: self.stack.setCurrentIndex(6))
        self._hdr_title = title; self._hdr_cb = cb
        lay.addWidget(hdr)

        lay.addSpacing(28)   # breathing room between header and game cards

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._gw = QWidget()
        self._grid = QGridLayout(self._gw)
        self._grid.setSpacing(10)
        self._grid.setContentsMargins(0, 0, 0, 4)
        self._grid.setAlignment(Qt.AlignTop)
        # Equal column stretch — CARD_COLS columns always share the full width
        for col in range(CARD_COLS):
            self._grid.setColumnStretch(col, 1)
        scroll.setWidget(self._gw); lay.addWidget(scroll, stretch=1)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Re-position header widgets on resize
        w = self.width() - 28   # account for layout margins
        self._hdr_title.setGeometry(0, 2, w, 36)
        self._hdr_cb.move(w - 150, 2)

    def set_installed(self, inst): self.installed=inst; self._pop()
    def showEvent(self, e): super().showEvent(e); self._pop()

    def _pop(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        is_oled = cfg.is_oled()
        ig = [g for g in ALL_GAMES if g["dev"]=="iw"   and (not g["plutonium"] or is_oled)]
        tg = [g for g in ALL_GAMES if g["dev"]=="trey" and (not g["plutonium"] or is_oled)]

        for col, gd in enumerate(ig):
            self._grid.addWidget(GameCard(gd, self.installed, self._sel, self._configure), 0, col)
        for col in range(len(ig), CARD_COLS):
            self._grid.addWidget(QWidget(), 0, col)

        if tg:
            for col, gd in enumerate(tg):
                self._grid.addWidget(GameCard(gd, self.installed, self._sel, self._configure), 1, col)
            for col in range(len(tg), CARD_COLS):
                self._grid.addWidget(QWidget(), 1, col)

    def _configure(self, gd):
        """CONFIGURE button on an uninstalled card — jump straight to SetupScreen."""
        self.stack.setCurrentIndex(2)

    def _sel(self, key, game):
        _kill_audio()
        exe = KEY_EXES.get(key); idir = game.get("install_dir","")
        if exe and idir:
            wp = os.path.join(idir, exe)
            if os.path.exists(wp): subprocess.Popen([wp]); QApplication.instance().quit(); return
        gd = next((g for g in ALL_GAMES if key in g["keys"]), {})
        if gd.get("appid"): subprocess.Popen(["steam", f"steam://rungameid/{gd['appid']}"])
        QApplication.instance().quit()

# ── Steam shortcut helper ──────────────────────────────────────────────────
def _write_steam_shortcut():
    """Write DeckOps to shortcuts.vdf. Steam must be restarted to pick it up."""
    import struct, time

    def _find_vdf():
        for steam in [
            os.path.expanduser("~/.local/share/Steam"),
            os.path.expanduser("~/.steam/steam"),
            os.path.expanduser("~/.steam/debian-installation"),
        ]:
            ud = os.path.join(steam, "userdata")
            if not os.path.exists(ud): continue
            for uid in os.listdir(ud):
                cfg_dir = os.path.join(ud, uid, "config")
                vdf = os.path.join(cfg_dir, "shortcuts.vdf")
                if os.path.exists(vdf) or os.path.exists(cfg_dir):
                    return vdf
        return None

    def _sf(k, v): return b'\x01' + k.encode() + b'\x00' + v.encode() + b'\x00'
    def _if(k, v): return b'\x02' + k.encode() + b'\x00' + struct.pack('<I', v)

    def _entry(idx, name, exe, icon, start_dir):
        e  = b'\x00' + str(idx).encode() + b'\x00'
        e += _sf('appname', name); e += _sf('exe', exe)
        e += _sf('StartDir', start_dir); e += _sf('icon', icon)
        e += _sf('ShortcutPath', ''); e += _sf('LaunchOptions', '')
        e += _if('IsHidden', 0); e += _if('AllowDesktopConfig', 1)
        e += _if('AllowOverlay', 1); e += _if('OpenVR', 0)
        e += _if('Devkit', 0); e += _sf('DevkitGameID', '')
        e += _if('LastPlayTime', int(time.time()))
        e += b'\x00tags\x00\x08\x08'
        return e

    vdf = _find_vdf()
    if not vdf: raise RuntimeError("shortcuts.vdf not found")

    home    = os.path.expanduser("~")
    name    = "DeckOps"
    exe     = f"python3 {home}/DeckOps/src/main.py"
    icon    = f"{home}/DeckOps/assets/images/icon.png"
    sdir    = f"{home}/DeckOps"

    if os.path.exists(vdf):
        data = open(vdf, 'rb').read()
        if b'DeckOps' in data: return   # already added
        existing = data[:-2] if data.endswith(b'\x08\x08') else data
        idx = existing.count(b'\x00appname\x00')
    else:
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        existing = b'\x00shortcuts\x00'
        idx = 0

    updated = existing + _entry(idx, name, exe, icon, sdir) + b'\x08\x08'
    open(vdf, 'wb').write(updated)


# ── ConfigureScreen ────────────────────────────────────────────────────────
class ConfigureScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack
        lay = QVBoxLayout(self); lay.setContentsMargins(40,20,40,20); lay.setSpacing(10)
        hdr = QHBoxLayout()
        back = _btn("<< Back", C_DARK_BTN, size=12, h=36); back.setFixedWidth(110)
        back.clicked.connect(lambda: self.stack.setCurrentIndex(5))
        t = QLabel("SETTINGS"); t.setFont(font(28,True)); t.setStyleSheet("color:#FFF;background:transparent;")
        hdr.addWidget(back); hdr.addWidget(t); hdr.addStretch(); lay.addLayout(hdr)

        sw = QWidget(); sl = QVBoxLayout(sw); sl.setSpacing(10); sl.setContentsMargins(0,6,0,6)

        # ── Updates ───────────────────────────────────────────────────────
        sl.addWidget(_lbl("UPDATES", 13, C_DIM, bold=True, align=Qt.AlignLeft))

        self._plut_upd_btn = _btn(
            "Update Plutonium  (World at War, Black Ops, Black Ops II, MW3)",
            C_TREY, size=12, h=36)
        self._plut_upd_btn.clicked.connect(self._update_plutonium)
        sl.addWidget(self._plut_upd_btn)

        self._cod4x_upd_btn = _btn(
            "Update CoD4x  (Call of Duty 4: Modern Warfare)",
            C_IW, size=12, h=36)
        self._cod4x_upd_btn.clicked.connect(self._update_cod4x)
        sl.addWidget(self._cod4x_upd_btn)

        self._iw4x_upd_btn = _btn(
            "Update iw4x  (Modern Warfare 2)",
            C_IW, size=12, h=36)
        self._iw4x_upd_btn.clicked.connect(self._update_iw4x)
        sl.addWidget(self._iw4x_upd_btn)

        sl.addWidget(_hdiv())

        # ── Plutonium credentials ─────────────────────────────────────────
        self._plut_cred_w = QWidget(); pcl = QVBoxLayout(self._plut_cred_w)
        pcl.setContentsMargins(0,0,0,0); pcl.setSpacing(6)
        pcl.addWidget(_lbl("PLUTONIUM ACCOUNT", 13, C_TREY, bold=True, align=Qt.AlignLeft))
        pcl.addWidget(_lbl(
            "Reset credentials to log in with a different account. "
            "After logging in, sync to all games.",
            12, C_DIM, align=Qt.AlignLeft))
        pr = QHBoxLayout(); pr.setSpacing(12)
        rb = _btn("RESET CREDENTIALS", C_TREY, size=12, h=36)
        sb = _btn("SYNC TO ALL GAMES", C_TREY, size=12, h=36)
        rb.clicked.connect(self._reset); sb.clicked.connect(self._sync)
        pr.addWidget(rb); pr.addWidget(sb); pcl.addLayout(pr)
        sl.addWidget(self._plut_cred_w)
        sl.addWidget(_hdiv())

        # ── Music ─────────────────────────────────────────────────────────
        sl.addWidget(_lbl("MUSIC", 13, C_DIM, bold=True, align=Qt.AlignLeft))
        music_row = QHBoxLayout(); music_row.setSpacing(16)
        self._music_toggle = _btn("Music: ON", C_IW, size=12, h=36); self._music_toggle.setFixedWidth(140)
        self._music_toggle.clicked.connect(self._toggle_music)
        from PyQt5.QtWidgets import QSlider
        self._vol_slider = QSlider(Qt.Horizontal); self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(75); self._vol_slider.setFixedHeight(30)
        self._vol_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background:#252535; height:6px; border-radius:3px;
            }}
            QSlider::handle:horizontal {{
                background:{C_TREY}; width:16px; height:16px;
                margin:-5px 0; border-radius:8px;
            }}
            QSlider::sub-page:horizontal {{
                background:{C_TREY}; height:6px; border-radius:3px;
            }}
        """)
        self._vol_slider.valueChanged.connect(self._set_volume)
        self._vol_label = _lbl("75%", 13, C_DIM, wrap=False); self._vol_label.setFixedWidth(40)
        music_row.addWidget(self._music_toggle)
        music_row.addWidget(_lbl("Volume:", 13, C_DIM, wrap=False))
        music_row.addWidget(self._vol_slider, stretch=1)
        music_row.addWidget(self._vol_label)
        sl.addLayout(music_row)
        sl.addWidget(_hdiv())

        # ── Steam ─────────────────────────────────────────────────────────
        sl.addWidget(_lbl("STEAM", 13, C_DIM, bold=True, align=Qt.AlignLeft))
        steam_btn = _btn("Add DeckOps to Steam Library", C_IW, size=12, h=36)
        steam_btn.clicked.connect(self._add_to_steam)
        sl.addWidget(steam_btn)
        sl.addWidget(_hdiv())

        # ── Deck model ────────────────────────────────────────────────────
        sl.addWidget(_lbl("DECK MODEL", 13, C_DIM, bold=True, align=Qt.AlignLeft))
        self._deck_toggle = _btn("", C_IW, size=12, h=36)
        self._deck_toggle.clicked.connect(self._toggle_deck_model)
        sl.addWidget(self._deck_toggle)
        sl.addWidget(_hdiv())

        # ── Danger zone ───────────────────────────────────────────────────
        sl.addWidget(_lbl("DANGER ZONE", 13, "#AA3333", bold=True, align=Qt.AlignLeft))
        reset_btn = _btn("Reset DeckOps  (wipe config and start over)", C_RED_BTN, size=12, h=36)
        reset_btn.clicked.connect(self._reset_deckops)
        sl.addWidget(reset_btn)

        lay.addWidget(sw, stretch=1)

        self.status = _lbl("", 13, C_IW); lay.addWidget(self.status)

        # Update thread signals
        self._s = _Sigs()
        self._s.progress.connect(lambda p,m: self.status.setText(m))
        self._s.log.connect(lambda l: self.status.setText(l))
        self._s.done.connect(lambda _: None)

        self._music_on = True

    def showEvent(self, e):
        super().showEvent(e)
        self.status.setText("")
        self._plut_cred_w.setVisible(cfg.is_oled())
        self._plut_upd_btn.setVisible(
            any(cfg.is_game_setup(k) for g in ALL_GAMES if g["plutonium"] for k in g["keys"]))
        self._cod4x_upd_btn.setVisible(
            any(cfg.is_game_setup(k) for g in ALL_GAMES if g["client"]=="cod4x" for k in g["keys"]))
        self._iw4x_upd_btn.setVisible(
            any(cfg.is_game_setup(k) for g in ALL_GAMES if g["client"]=="iw4x" for k in g["keys"]))
        model = cfg.get_deck_model() or "oled"
        self._deck_toggle.setText(
            f"Current model: Steam Deck {'OLED' if model == 'oled' else 'LCD'}  (click to switch)")

    def _toggle_deck_model(self):
        current = cfg.get_deck_model() or "oled"
        new_model = "lcd" if current == "oled" else "oled"
        cfg.set_deck_model(new_model)
        self._deck_toggle.setText(
            f"Current model: Steam Deck {'OLED' if new_model == 'oled' else 'LCD'}  (click to switch)")
        self.status.setText(f"Deck model set to {new_model.upper()}.")

    # ── update handlers ───────────────────────────────────────────────────

    def _update_plutonium(self):
        self.status.setText("Launching Plutonium updater...")
        def _run():
            try:
                from wrapper import get_proton_path
                from plutonium import launch_bootstrapper, is_plutonium_ready, install_plutonium
                root   = find_steam_root()
                proton = get_proton_path(root)
                launch_bootstrapper(proton, on_progress=lambda p,m: self._s.log.emit(m))
                if not is_plutonium_ready():
                    self._s.log.emit("Plutonium update incomplete."); return
                inst = find_installed_games(parse_library_folders(root))
                for gd in ALL_GAMES:
                    if not gd["plutonium"]: continue
                    for key in gd["keys"]:
                        if not cfg.is_game_setup(key): continue
                        game  = inst.get(key, {})
                        if not game: continue
                        from wrapper import find_compatdata
                        compat = find_compatdata(root, gd["appid"])
                        from wrapper import get_proton_path
                        install_plutonium(game, key, root, proton, compat)
                self._s.log.emit("Plutonium updated successfully.")
            except Exception as ex:
                self._s.log.emit(f"Update failed: {ex}")
        threading.Thread(target=_run, daemon=True).start()

    def _update_cod4x(self):
        self.status.setText("Updating CoD4x...")
        def _run():
            try:
                from wrapper import get_proton_path, find_compatdata
                from cod4x import install_cod4x
                root   = find_steam_root()
                proton = get_proton_path(root)
                inst   = find_installed_games(parse_library_folders(root))
                for gd in ALL_GAMES:
                    if gd["client"] != "cod4x": continue
                    for key in gd["keys"]:
                        if not cfg.is_game_setup(key): continue
                        game = inst.get(key, {})
                        if not game: continue
                        compat = find_compatdata(root, gd["appid"])
                        install_cod4x(game, root, proton, compat)
                self._s.log.emit("CoD4x updated successfully.")
            except Exception as ex:
                self._s.log.emit(f"Update failed: {ex}")
        threading.Thread(target=_run, daemon=True).start()

    def _update_iw4x(self):
        self.status.setText("Updating iw4x...")
        def _run():
            try:
                from wrapper import get_proton_path, find_compatdata
                from iw4x import install_iw4x
                root   = find_steam_root()
                proton = get_proton_path(root)
                inst   = find_installed_games(parse_library_folders(root))
                for gd in ALL_GAMES:
                    if gd["client"] != "iw4x": continue
                    for key in gd["keys"]:
                        if not cfg.is_game_setup(key): continue
                        game = inst.get(key, {})
                        if not game: continue
                        compat = find_compatdata(root, gd["appid"])
                        install_iw4x(game, root, proton, compat)
                self._s.log.emit("iw4x updated successfully.")
            except Exception as ex:
                self._s.log.emit(f"Update failed: {ex}")
        threading.Thread(target=_run, daemon=True).start()

    # ── music ─────────────────────────────────────────────────────────────

    def _toggle_music(self):
        global _audio_proc
        self._music_on = not self._music_on
        if self._music_on:
            _start_audio()
            self._music_toggle.setText("Music: ON")
            self._music_toggle.setStyleSheet(self._music_toggle.styleSheet().replace(C_DARK_BTN, C_IW))
        else:
            _kill_audio()
            self._music_toggle.setText("Music: OFF")

    def _set_volume(self, val):
        global _audio_proc
        self._vol_label.setText(f"{val}%")
        if _audio_proc and _audio_proc.poll() is None:
            try: subprocess.Popen(["kill", "-USR1", str(_audio_proc.pid)])
            except Exception: pass
        _kill_audio()
        if self._music_on:
            source = MUSIC_PATH if os.path.exists(MUSIC_PATH) else MUSIC_URL
            try:
                _audio_proc = subprocess.Popen(
                    ["mpv","--no-video","--loop",f"--volume={val}", source],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
            except FileNotFoundError: pass

    # ── steam ─────────────────────────────────────────────────────────────

    def _add_to_steam(self):
        try:
            _write_steam_shortcut()
            self.status.setText("Added! Restart Steam to see DeckOps in your library.")
        except Exception as ex:
            self.status.setText(f"Could not add to Steam: {ex}")

    # ── plutonium credentials ─────────────────────────────────────────────

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

    # ── reinstall / uninstall ─────────────────────────────────────────────

    def _reinstall(self, key, gd):
        root = find_steam_root(); inst = find_installed_games(parse_library_folders(root))
        s = self.stack.widget(4); s.selected=[(key,gd,inst.get(key,{}))]; s.steam_root=root
        self.stack.setCurrentIndex(4)

    def _confirm_uninstall(self, key, gd):
        self.status.setText(f"Press UNINSTALL again to confirm removal of {gd['base']}.")
        self.status.mousePressEvent = lambda _: self._do_uninstall(key, gd)

    def _do_uninstall(self, key, gd):
        self.status.mousePressEvent = None
        try:
            root = find_steam_root(); inst = find_installed_games(parse_library_folders(root))
            game = inst.get(key, {}); c = gd.get("client")
            if c=="cod4x": from cod4x import uninstall_cod4x; uninstall_cod4x(game)
            elif c=="iw4x": from iw4x import uninstall_iw4x; uninstall_iw4x(game)
            elif c=="plutonium": from plutonium import uninstall_plutonium; uninstall_plutonium(game,key)
            for k in gd.get("keys",[]): cc=cfg.load(); cc["setup_games"].pop(k,None); cfg.save(cc)
            self.status.setText(f"{gd['base']} uninstalled.")
        except Exception as ex: self.status.setText(f"Uninstall error: {ex}")

    # ── deck model / reset ────────────────────────────────────────────────

    def _reset_deckops(self):
        cfg.reset()
        self.status.setText("Config wiped. Restart DeckOps to run setup again.")
        QTimer.singleShot(1500, lambda: self.stack.setCurrentIndex(0))

# ── App ────────────────────────────────────────────────────────────────────
def _app_style():
    """Build the global stylesheet after _load_font() has set _FONT_FAMILY."""
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
        for cls in [BootstrapScreen,IntroScreen,WelcomeScreen,SetupScreen,InstallScreen,GameScreen,ConfigureScreen]:
            self.stack.addWidget(cls(self.stack))
        self.stack.setCurrentIndex(0); _start_audio()

    def closeEvent(self, e):
        _kill_audio()
        super().closeEvent(e)

def run():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # Load fonts FIRST — _app_style() and _title_block() both read _FONT_FAMILY/_FONT_FAMILY_DISP
    _load_font()
    app.setStyleSheet(_app_style())
    win = DeckOpsWindow()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    run()
