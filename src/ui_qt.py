"""
ui_qt.py — DeckOps main UI entry point

Slim shell: BootstrapScreen, DeckOpsWindow, and run().
All screen classes are imported from split modules:
    ui_constants  — shared constants, helpers, navigation
    ui_setup      — first-run setup flow (OS → Device → Gyro → ...)
    ui_install    — install pipeline (Welcome, Setup, Install, OwnInstall, OwnScan)
    ui_manage     — post-install (Management, Configure, ControllerInfo, Update)
"""

import sys, os, threading

from PyQt5.QtWidgets import QApplication, QMainWindow, QStackedWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QWidget
from PyQt5.QtCore import Qt, QTimer

import bootstrap as _bootstrap
from detect_games import find_steam_root, parse_library_folders, find_installed_games
import config as cfg
from identity import APP_TITLE

from ui_constants import (
    C_DIM, font, _btn, _lbl, _title_block, _Sigs,
    _load_font, _app_style, _start_audio, _kill_audio,
    go_to, get_screen,
)

from ui_setup import SetupFlowScreen
from ui_install import WelcomeScreen, SetupScreen, InstallScreen, OwnInstallScreen, OwnScanScreen
from ui_manage import ManagementScreen, ConfigureScreen, SetupCompleteScreen, UpdateScreen


# ── BootstrapScreen ───────────────────────────────────────────────────────────
class BootstrapScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack = stack; self.screen_name = "BootstrapScreen"
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
            go_to(self.stack, "SetupFlowScreen")
        else:
            root = find_steam_root()
            get_screen(self.stack, "ManagementScreen").set_installed(
                find_installed_games(parse_library_folders(root))
            )
            go_to(self.stack, "ManagementScreen")


# ── DeckOpsWindow ─────────────────────────────────────────────────────────────
class DeckOpsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 800)
        self.setMinimumSize(800, 500)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # Register all screens — order doesn't matter, navigation is by name
        for cls in [
            BootstrapScreen,
            SetupFlowScreen,
            WelcomeScreen,
            SetupScreen,
            InstallScreen,
            OwnInstallScreen,
            OwnScanScreen,
            ManagementScreen,
            ConfigureScreen,
            SetupCompleteScreen,
            UpdateScreen,
        ]:
            self.stack.addWidget(cls(self.stack))

        self.stack.setCurrentIndex(0)

        # Debug label — shows current screen name and index in bottom-left
        self._dbg_label = QLabel(self)
        self._dbg_label.setStyleSheet(
            "color:#444455;background:transparent;padding:4px 8px;"
        )
        self._dbg_label.setFont(font(9))
        self._dbg_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._dbg_label.raise_()
        self.stack.currentChanged.connect(self._update_dbg_label)
        self._update_dbg_label(0)

    def _update_dbg_label(self, idx):
        w = self.stack.widget(idx)
        name = getattr(w, "screen_name", w.__class__.__name__)
        self._dbg_label.setText(f"[{idx}] {name}")
        self._dbg_label.adjustSize()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._dbg_label.move(8, self.height() - self._dbg_label.height() - 8)
        self._dbg_label.raise_()

    def closeEvent(self, e):
        _kill_audio()
        super().closeEvent(e)


# ── Entry point ───────────────────────────────────────────────────────────────
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
