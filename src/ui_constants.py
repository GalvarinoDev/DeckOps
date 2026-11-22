"""
ui_constants.py — Shared constants, helpers, and game definitions for DeckOps UI

Extracted from ui_qt.py so that ui_setup.py, ui_install.py, ui_manage.py,
and ui_qt.py can all import from a single source without circular deps.
"""

import html
import os

from qt import (
    QLabel, QPushButton, QFrame, QHBoxLayout, QMessageBox, QWidget,
)
from qt import Qt, pyqtSignal, QObject, QUrl, QT6
from qt import QFont, QFontDatabase

import config as cfg
from identity import BUILD_BADGE, BRANCH
from log import get_logger

_log = get_logger(__name__)


# ── Paths ─────────────────────────────────────────────────────────────────────

from steam_common import PROJECT_ROOT
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


def _copy_log_to_clipboard(status_widget=None):
    """Read the last 200 lines of install.log and copy to clipboard."""
    from depot_downgrade import copy_to_clipboard
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        # An early failure in a long install scrolls out of the tail
        errs = [l for l in lines[:-200] if "  ERROR  " in l or "✗" in l][-50:]
        tail = "".join(lines[-200:])
        if errs:
            tail = "--- earlier errors ---\n" + "".join(errs) + "--- last 200 lines ---\n" + tail
        copy_to_clipboard(tail)
        if status_widget:
            status_widget.setText("Log copied to clipboard (last 200 lines)")
    except FileNotFoundError:
        if status_widget:
            status_widget.setText("No log file found")
    except Exception as ex:
        if status_widget:
            status_widget.setText(f"Failed to copy log: {ex}")


# ── Colors ────────────────────────────────────────────────────────────────────

C_BG       = "#141416"
C_CARD     = "#1E1E26"
C_IW       = "#6DC62B"
C_TREY     = "#F47B20"
C_DIM      = "#888899"
C_DARK_BTN = "#33333F"
C_RED_BTN  = "#7A1515"
C_BLUE_BTN = "#1A5FAA"

# Accent: orange on every branch. Only the branch badges change: green for stable.
C_ACCENT    = C_TREY
C_ACCENT_BG = "#2A1A08"
C_BADGE     = C_IW if BRANCH == "stable" else C_TREY
C_BADGE_BG  = "#0A2A08" if BRANCH == "stable" else "#2A1A08"


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
# Each entry is one card in the UI. What each card shows
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
    # --- Release order. The games page shows a row per dev with the "classic" games
    # left of a divider. The install screen splits the list into its two columns by dev.
    {"base":"Call of Duty","classic":True,"keys":["cod1mp","cod1sp"],"appid":2620,"dev":"iw","client":"iw-pad + cod1x",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: United Offensive","classic":True,"keys":["coduomp","coduosp"],"appid":2640,"dev":"iw","client":"iw-pad + coduox",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    # Finest Hour has no Steam app. 99000005 is its placeholder
    {"base":"Call of Duty: Finest Hour","classic":True,"keys":["codfh"],"appid":99000005,"dev":"trey","client":"fh remastered",
     "launch_note":"Put your PAL (Europe) Xbox disc image in Games/finesthour. DeckOps installs Finest Hour Remastered from it."},
    {"base":"Call of Duty 2","classic":True,"keys":["cod2mp","cod2sp"],"appid":2630,"dev":"iw","client":"iw-pad + cod2x",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    # Big Red One has no Steam app either. 99000004 is its placeholder
    {"base":"Call of Duty 2: Big Red One","classic":True,"keys":["bro"],"appid":99000004,"dev":"trey","client":"bro",
     "launch_note":"Put your Xbox disc image in Games/bro. DeckOps installs the BRO engine next to it."},
    # CoD3 has no Steam app. 99000003 is a placeholder, used only for the card image
    {"base":"Call of Duty 3","classic":True,"keys":["cod3"],"appid":99000003,"dev":"trey","client":"cod3recomp",
     "launch_note":"Put your Xbox 360 disc image in Games/cod3. DeckOps installs CoD3Recomp next to it."},
    {"base":"Call of Duty 4: Modern Warfare","keys":["cod4mp","cod4sp"],"appid":7940,"dev":"iw","client":"cod4r + iw3sp",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: World at War","keys":["t4mp","t4sp"],"appid":10090,"dev":"trey","client":"plutonium",
     "lcd_keys":["t4mp","t4sp"],"lcd_client":"plutonium",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: Modern Warfare 2","keys":["iw4mp","iw4sp"],"appid":10190,"dev":"iw","client":"iw4x",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: Black Ops","keys":["t5mp","t5sp"],"appid":42700,"dev":"trey","client":"plutonium",
     "lcd_keys":["t5mp","t5sp"],"lcd_client":"plutonium",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: Modern Warfare 3","keys":["iw5mp","iw5sp","iw5mp_ds"],"appid":42690,"dev":"iw","client":"plutonium",
     "lcd_keys":["iw5mp","iw5sp","iw5mp_ds"],"lcd_client":"plutonium","lcd_appid":42680,
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: Black Ops II","keys":["t6mp","t6sp","t6zm"],"appid":202990,"dev":"trey","client":"plutonium + t6sp-mod",
     "lcd_keys":["t6mp","t6sp","t6zm"],"lcd_client":"plutonium + t6sp-mod","lcd_appid":202970,
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: Ghosts","keys":["iw6mp","iw6sp"],"appid":209160,"dev":"iw","client":"alterware",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: Advanced Warfare","keys":["s1mp","s1sp"],"appid":209650,"dev":"iw","client":"alterware",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"Call of Duty: Black Ops III","keys":["t7"],"appid":311210,"dev":"trey","client":"cleanops",
     "launch_note":"DeckOps creates Proton prefixes automatically."},
    {"base":"DeckOps: Plutonium Offline","keys":[],"appid":None,"dev":"trey","client":"lan",
     "launch_note":"Offline Mode: offline launcher, Plutonium Offline launch menu entries and bot matches."},
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
    "cod1sp": "steam", "cod1mp": "cod1x",
    "coduosp": "steam", "coduomp": "coduox",
    "cod2sp": "steam", "cod2mp": "cod2x",
    "cod3":   "cod3recomp",
    "bro":    "bro",
    "codfh":  "finesthour",
    "cod4mp": "cod4r",
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
    # "t7x":    "t7x",  # DISABLED 2026-09: AlterWare discontinuing Dec 2026
    "iw6mp": "alterware",
    "iw6sp": "alterware",
    "s1mp":  "alterware",
    "s1sp":  "alterware",
}

KEY_EXES = {
    "cod1sp":"CoDSP.exe","cod1mp":"CoDMP.exe",
    "coduosp":"CoDUOSP.exe","coduomp":"CoDUOMP.exe",
    "cod2sp":"CoD2SP_s.exe","cod2mp":"CoD2MP_s.exe",
    "cod3":"CoD3SP_s.exe",
    "bro":"cod_bro",
    "codfh":"CODFH.exe",
    "cod4mp":"iw3mp.exe","cod4sp":"iw3sp.exe",
    "iw4mp":"iw4mp.exe","iw4sp":"iw4sp.exe",
    "iw5mp":"iw5mp.exe","iw5mp_ds":"iw5mp_server.exe","iw5sp":"iw5sp.exe",
    "t4sp":"CoDWaW.exe","t4mp":"CoDWaWmp.exe",
    "t5sp":"BlackOps.exe","t5mp":"BlackOpsMP.exe",
    "t6zm":"t6zm.exe","t6mp":"t6mp.exe","t6sp":"t6sp.exe",
    "t7":"BlackOps3.exe",
    # "t7x":"t7x.exe",  # DISABLED 2026-09: AlterWare discontinuing Dec 2026
    "iw6mp":"iw6mp64_ship.exe","iw6sp":"iw6sp64_ship.exe",
    "s1mp":"s1_mp64_ship.exe","s1sp":"s1_sp64_ship.exe",
}

# Label shown beneath each per-key checkbox in SetupScreen.
KEY_MODE_LABEL = {
    "cod1mp": "MP",    "cod1sp": "SP",
    "coduomp": "MP",   "coduosp": "SP",
    "cod2mp": "MP",    "cod2sp": "SP",
    "cod3":   "SP",
    "bro":    "SP",
    "codfh":  "SP",
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
    2620:   "https://shared.steamstatic.com/store_item_assets/steam/apps/2620/library_600x900_2x.jpg",
    2640:   "https://cdn2.steamgriddb.com/grid/3ead4e722d6df4d4d7e1c61fbdd66968.png",
    2630:   "https://shared.steamstatic.com/store_item_assets/steam/apps/2630/library_600x900_2x.jpg",
    99000003: "https://cdn2.steamgriddb.com/grid/ebb4cd828b62543f83b337e48b333eb8.jpg",  # CoD3 placeholder appid
    99000005: "https://cdn2.steamgriddb.com/grid/f0dda1e19cb7596fcb7430e4b3f4f0b5.png",  # Finest Hour placeholder appid
    99000004: "https://cdn2.steamgriddb.com/grid/3e5589b2df55552e7716818b29ba2a2d.png",  # Big Red One placeholder appid
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
# The games page picks the card width that fits every card on screen, up to this
CARD_MAX_W = 300

MUSIC_URL = "https://archive.org/download/adrenaline-klickaud/Adrenaline_KLICKAUD.mp3"


# ── Audio ─────────────────────────────────────────────────────────────────────

_music_volume  = cfg.get_music_volume()
_music_enabled = cfg.get_music_enabled()

_player = None

# Qt's media player; PyQt6 wheels bundle FFmpeg for mp3. PyQt5 would need
# system GStreamer plugins, so the PyQt5 fallback plays no music.
def _kill_audio():
    if _player:
        _player.stop()

def _start_audio():
    global _player
    if not _music_enabled or not QT6 or not os.path.exists(MUSIC_PATH):
        return
    try:
        from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
        if _player is None:
            _player = QMediaPlayer(); _player.setAudioOutput(QAudioOutput(_player))
            _player.setSource(QUrl.fromLocalFile(MUSIC_PATH)); _player.setLoops(QMediaPlayer.Loops.Infinite)
        _player.audioOutput().setVolume(_music_volume)
        if _player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            _player.play()
    except Exception:
        _log.debug("audio start failed", exc_info=True)

def _set_audio_volume(vol: float):
    global _music_volume
    _music_volume = vol
    cfg.set_music_volume(vol)
    if _player:
        _player.audioOutput().setVolume(vol)

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

def _lbl(text, size=14, color="#FFF", bold=False, align=Qt.AlignmentFlag.AlignCenter, wrap=True):
    w = QLabel(text); w.setFont(font(size,bold)); w.setAlignment(align)
    w.setWordWrap(wrap); w.setStyleSheet(f"color:{color};background:transparent;")
    return w

def _header_bar():
    """Compact top bar used by list screens. Returns (bar, row layout) so callers can append buttons."""
    hdr = QWidget(); hdr.setFixedHeight(60); hdr.setStyleSheet(f"background:{C_CARD};")
    hl = QHBoxLayout(hdr); hl.setContentsMargins(20,0,20,0)
    t = QLabel("DECKOPS"); t.setFont(font(22, display=True))
    t.setStyleSheet("color:#FFF;background:transparent;"); hl.addWidget(t)
    b = QLabel(BRANCH.upper()); b.setFont(font(10, bold=True))
    b.setStyleSheet(
        f"color:{C_BADGE};background:{C_BADGE_BG};border:1px solid {C_BADGE};"
        "border-radius:4px;padding:1px 6px;")
    hl.addWidget(b); hl.addStretch()
    return hdr, hl

def _badge(text, color, w, h=30, size=10, radius=6):
    b = QPushButton(text); b.setFont(font(size, True)); b.setFixedSize(w, h); b.setEnabled(False)
    b.setStyleSheet(
        f"QPushButton{{background:{color};color:#FFF;border:none;border-radius:{radius}px;}}"
        f"QPushButton:disabled{{background:{color};color:#FFF;}}")
    return b

def _back_row(lay, slot):
    b = _btn("<< Back", C_DARK_BTN, size=12, h=44); b.setFixedWidth(140)
    b.clicked.connect(slot)
    row = QHBoxLayout(); row.addWidget(b); row.addStretch(); lay.addLayout(row)
    return b

def _log_html(text: str) -> str:
    """Colorize a log line by its leading marker. Everything else stays dim."""
    color = {"✓": C_IW, "✗": C_TREY, "⚠": C_TREY}.get(text.lstrip()[:1], "#666677")
    body = html.escape(text).replace("\n", "<br>").replace("  ", "&nbsp;&nbsp;")
    return f'<span style="color:{color};white-space:pre-wrap">{body}</span>'


def _hdiv():
    d = QFrame(); d.setFrameShape(QFrame.Shape.HLine); d.setFixedHeight(1)
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

def _ask_iw4x_dlc(parent, selected) -> str:
    """
    Ask about free IW4x DLC maps during install.

    Returns:
      "install" - download DLC (user said yes)
      "keep"    - DLC already present, skip silently
      ""        - no IW4x selected, or user declined
    """
    iw4x_games = [(k, gd, g) for k, gd, g in selected if KEY_CLIENT.get(k) == "iw4x"]
    if not iw4x_games:
        return ""
    from iw4x import is_iw4x_dlc_installed
    dlc_present = all(is_iw4x_dlc_installed(g["install_dir"])
                      for _, _, g in iw4x_games if g.get("install_dir"))

    if dlc_present:
        return "keep"

    reply = QMessageBox.question(
        parent,
        "Free DLC Maps",
        "Install free DLC maps for Modern Warfare 2?\n\n"
        "Includes CoD4, MW3, Black Ops, and CoD Online maps.\n"
        "Recommended for joining most servers.\n\n"
        "Download size: ~3 GB",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    return "install" if reply == QMessageBox.StandardButton.Yes else ""

def _ask_bo3_client(parent, selected) -> str:
    """
    Return the BO3 client to install.

    T7X was disabled in September 2026 (AlterWare discontinuing Dec 2026).
    The original three-way dialog (CleanOps / T7X / Both) is preserved
    below in comments for easy re-enable.  For now, always return
    "cleanops" so the install flow skips T7X without any UI prompt.
    """
    return "cleanops"
    # ── DISABLED 2026-09: AlterWare discontinuing Dec 2026 ──────────────
    # has_bo3 = any(KEY_CLIENT.get(k) == "cleanops" for k, _, _ in selected)
    # if not has_bo3:
    #     return "cleanops"
    #
    # msg = QMessageBox(parent)
    # msg.setWindowTitle("Black Ops III - Client Selection")
    # msg.setText(
    #     "Choose which BO3 client to install.\n\n"
    #     "CleanOps\n"
    #     "Patches BO3 to protect against exploits. Adds dedicated servers "
    #     "alongside Activision's official servers. Recommended for official "
    #     "Steam copies. You can skip this for non-Steam installs.\n\n"
    #     "T7X\n"
    #     "Separate client with its own dedicated server list. "
    #     "Download size: ~105 MB.\n\n"
    #     "Both\n"
    #     "Installs CleanOps and T7X side by side. Do the first launch in "
    #     "Desktop Mode:\n"
    #     "  1. Launch Black Ops III first (CleanOps patches).\n"
    #     "  2. Launch T7X after CleanOps is working.\n"
    #     "  3. After this, both work fine in Game Mode."
    # )
    # btn_cleanops = msg.addButton("CleanOps", QMessageBox.ButtonRole.AcceptRole)
    # btn_t7x      = msg.addButton("T7X", QMessageBox.ButtonRole.AcceptRole)
    # btn_both     = msg.addButton("Both", QMessageBox.ButtonRole.AcceptRole)
    # msg.setDefaultButton(btn_cleanops)
    # msg.exec()
    #
    # clicked = msg.clickedButton()
    # if clicked == btn_t7x:
    #     return "t7x"
    # if clicked == btn_both:
    #     return "both"
    # return "cleanops"

# ── Title block ───────────────────────────────────────────────────────────────

def _show_preflight(parent, checks) -> bool:
    """
    Show the pre-install checks. Returns True to go ahead.

    Nothing here is a hard stop: the space figures are estimates, so a
    wrong one must not wall off a valid install. The recommendation is
    plain and the choice stays with the user.
    """
    import preflight as _pf
    if not checks:
        return True
    level = _pf.worst(checks)
    if level == _pf.OK:
        return True

    icons = {_pf.OK: "\u2713", _pf.WARN: "\u26a0", _pf.BLOCK: "\u2717"}
    colors = {_pf.OK: C_IW, _pf.WARN: C_TREY, _pf.BLOCK: C_TREY}
    rows = []
    for c in checks:
        rows.append(
            f'<div style="color:{colors[c.level]}"><b>{icons[c.level]}&nbsp;&nbsp;'
            f'{html.escape(c.title)}</b></div>'
            f'<div style="color:#999999;margin-bottom:6px">'
            f'&nbsp;&nbsp;&nbsp;&nbsp;{html.escape(c.detail)}</div>')

    msg = QMessageBox(parent)
    msg.setWindowTitle("Before installing")
    msg.setTextFormat(Qt.TextFormat.RichText)
    msg.setText(
        ("<b>Some checks did not pass.</b><br><br>" if level == _pf.BLOCK
         else "<b>Worth knowing before you start.</b><br><br>")
        + "".join(rows))
    go = msg.addButton("Install Anyway", QMessageBox.ButtonRole.AcceptRole)
    back = msg.addButton("Go Back", QMessageBox.ButtonRole.RejectRole)
    msg.setDefaultButton(back if level == _pf.BLOCK else go)
    msg.exec()
    return msg.clickedButton() is go


def _title_block(lay, main_size=56):
    t = QLabel("DECKOPS")
    t.setFont(font(main_size, display=True))
    t.setAlignment(Qt.AlignmentFlag.AlignCenter)
    t.setStyleSheet("color:#FFFFFF; background:transparent;")
    lay.addWidget(t)
    sub = QLabel()
    sub.setTextFormat(Qt.TextFormat.RichText)
    sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sub.setStyleSheet(f"color:{C_ACCENT}; background:transparent;")
    sub.setText(
        f'<span style="font-family:\'{_FONT_FAMILY_DISP}\'; font-size:28pt; color:{C_ACCENT};">'
        f'COMBAT'
        f'<span style="font-size:16pt;">on</span>'
        f'DECK'
        f'</span>'
    )
    lay.addWidget(sub)
    # Build badge — always shown, text and color come from the branch
    badge = QLabel(BUILD_BADGE)
    badge.setFont(font(10, bold=True))
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        f"color:{C_BADGE};background:{C_BADGE_BG};border:1px solid {C_BADGE};"
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
    # Download retry dialog: (label, error_msg)
    retry_dl    = pyqtSignal(str, str)
    # Manual download fallback: (url, dest_folder, filename, label)
    manual_dl   = pyqtSignal(str, str, str, str)
    # IW5 (MW3) 32-bit depot downgrade
    iw5_dg_wait   = pyqtSignal(str, str)   # manual gate: (command, step_label)
    iw5_dg_go     = pyqtSignal()           # manual gate: dismiss
    iw5_qr_show   = pyqtSignal(str)        # QR path: display/refresh QR text
    iw5_qr_hide   = pyqtSignal()           # QR path: dismiss QR display
    iw5_dg_choose = pyqtSignal()           # show method chooser dialog
    iw5_trim_ask  = pyqtSignal()           # offer to trim duplicate 64-bit files
    # Zombies Declassified opt-in prompt
    zd_ask        = pyqtSignal()           # show install/skip buttons
    zd_go         = pyqtSignal()           # dismiss buttons
    # Recompile installed: offer to delete its disc image (game title, disc path)
    disc_ask      = pyqtSignal(str, str)


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
QProgressBar::chunk {{ background:{C_ACCENT}; border-radius:7px; }}
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
