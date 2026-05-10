"""
ui_install.py — Install pipeline screens for DeckOps

Screens: WelcomeScreen, SetupScreen, InstallScreen, OwnInstallScreen, OwnScanScreen
Extracted from ui_qt.py — all hardcoded stack indices replaced with named lookups.
"""

import os, subprocess, threading

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QCheckBox, QProgressBar,
    QPlainTextEdit, QFileDialog, QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer

from detect_games import find_steam_root, parse_library_folders, find_installed_games
import config as cfg
from net import DownloadError

from ui_constants import (
    C_BG, C_CARD, C_IW, C_TREY, C_DIM, C_DARK_BTN,
    font, _btn, _lbl, _title_block, _log_to_file, _Sigs,
    ALL_GAMES, KEY_CLIENT, KEY_EXES, KEY_MODE_LABEL,
    _active_keys, _active_client, _active_appid,
    _ask_iw4x_dlc, _ask_t7x_install,
    go_to, get_screen,
)


# ── WelcomeScreen ─────────────────────────────────────────────────────────────
class WelcomeScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.installed={}; self.screen_name = "WelcomeScreen"
        self.steam_installed={}; self.own_installed={}; self.steam_root=""
        self._steam_only = False  # set by OwnScanScreen skip or advanced flow
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
        self.results.setTextFormat(Qt.RichText)
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
        source = cfg.get_game_source() or "steam"
        libs = parse_library_folders(self.steam_root)
        steam_found = find_installed_games(libs)
        self.steam_installed = steam_found
        if source == "own" and not self._steam_only:
            from detect_games import find_own_installed
            own_found = find_own_installed()
            self.own_installed = own_found
            self.installed = {**own_found, **steam_found}
        else:
            self.own_installed = {}
            self.installed = steam_found
        if cfg.is_lcd():
            lcd_allowed = set()
            for g in ALL_GAMES:
                lcd_allowed.update(g.get("lcd_keys", g["keys"]))
            self.installed = {k:v for k,v in self.installed.items() if k in lcd_allowed}
            self.steam_installed = {k:v for k,v in self.steam_installed.items() if k in lcd_allowed}
            self.own_installed = {k:v for k,v in self.own_installed.items() if k in lcd_allowed}
        QTimer.singleShot(200, self._show_results)

    def _show_results(self):
        self.bar.setValue(100)
        if not self.installed:
            # Advanced flow with own games already parked: no Steam games is OK,
            # skip straight to SetupScreen which will route to OwnInstallScreen.
            if self._steam_only and cfg.get_game_source() == "own":
                own_screen = get_screen(self.stack, "OwnInstallScreen")
                if own_screen.own_selected:
                    self.status.setText("No Steam games found — continuing with your non-Steam games.")
                    self.status.setStyleSheet(f"color:{C_IW};background:transparent;")
                    self.cont.setVisible(True)
                    return
            self.status.setText("No supported games found.")
            self.status.setStyleSheet(f"color:{C_TREY};background:transparent;"); return
        unique = len({g["name"].split(" - ")[0].split(" (")[0] for g in self.installed.values()})
        self.status.setText(f"Found {unique} supported game(s)!")
        self.status.setStyleSheet(f"color:{C_IW};background:transparent;")
        lines = []
        # Steam games
        seen_steam = set()
        for g in sorted(self.steam_installed.values(), key=lambda x: x.get("order",99)):
            base = g["name"].split(" - ")[0].split(" (")[0]
            if base not in seen_steam:
                seen_steam.add(base)
                lines.append(f'<span style="color:{C_IW}">{base} (Steam)</span>')
        # Own games
        seen_own = set()
        for g in sorted(self.own_installed.values(), key=lambda x: x.get("order",99)):
            base = g["name"].split(" - ")[0].split(" (")[0]
            if base not in seen_own:
                seen_own.add(base)
                lines.append(f'<span style="color:{C_TREY}">{base} (Non-Steam)</span>')
        self.results.setText("<br>".join(lines)); self.cont.setVisible(True)

    def _go_next(self):
        if cfg.is_first_run():
            # Advanced flow with no Steam games: skip the blank SetupScreen
            # and route straight to OwnInstallScreen (mirrors SetupScreen._go_install
            # zero-selection logic).
            if self._steam_only and cfg.get_game_source() == "own" \
                    and not self.steam_installed:
                own_screen = get_screen(self.stack, "OwnInstallScreen")
                own_screen.steam_selected = []
                own_screen.steam_root = self.steam_root
                _own_sel = own_screen.own_selected or {}
                _own_tmp = []
                for _k, _g in _own_sel.items():
                    for _gd in ALL_GAMES:
                        if _k in _active_keys(_gd):
                            _own_tmp.append((_k, _gd, _g)); break
                own_screen.install_iw4x_dlc = _ask_iw4x_dlc(self, _own_tmp)
                own_screen.install_t7x_opt = _ask_t7x_install(self, _own_tmp)
                go_to(self.stack, "OwnInstallScreen")
                return
            s = get_screen(self.stack, "SetupScreen")
            s.steam_installed = self.steam_installed
            s.own_installed   = self.own_installed
            s.steam_root      = self.steam_root
            go_to(self.stack, "SetupScreen")
        else:
            get_screen(self.stack, "ManagementScreen").set_installed(self.installed)
            go_to(self.stack, "ManagementScreen")


# ── SetupScreen ───────────────────────────────────────────────────────────────
class SetupScreen(QWidget):
    """
    Steam game selection. Shows detected Steam games with checkboxes.
    In the advanced flow, routes to OwnInstallScreen instead of InstallScreen
    so both Steam and own games are handled in one pass.
    """
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.screen_name = "SetupScreen"
        self.steam_installed={}; self.own_installed={}; self.steam_root=""
        self._checks={}

        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        # ── Compact header bar ─────────────────────────────────────────
        hdr = QWidget(); hdr.setFixedHeight(60)
        hdr.setStyleSheet(f"background:{C_CARD};")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(20,0,20,0)
        title = QLabel("DECKOPS"); title.setFont(font(22, display=True))
        title.setStyleSheet("color:#FFF;background:transparent;")
        hl.addWidget(title)
        nightly_lbl = QLabel("NIGHTLY"); nightly_lbl.setFont(font(9, bold=True))
        nightly_lbl.setStyleSheet(
            "color:#F47B20;background:#2A1A08;border:1px solid #F47B20;"
            "border-radius:4px;padding:1px 6px;"
        )
        hl.addWidget(nightly_lbl)
        hl.addStretch()
        lay.addWidget(hdr)

        # ── Content area ───────────────────────────────────────────────
        content = QWidget()
        clay = QVBoxLayout(content); clay.setContentsMargins(60,20,60,40); clay.setSpacing(14)
        clay.addWidget(_lbl(
            "Choose which games to set up. "
            "DeckOps will create Proton prefixes automatically.", 13, C_DIM))
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._lw = QWidget(); self._ll = QVBoxLayout(self._lw)
        self._ll.setSpacing(0); self._ll.addStretch()
        scroll.setWidget(self._lw); clay.addWidget(scroll, stretch=1)

        self.warning = _lbl("", 12, C_TREY, align=Qt.AlignLeft)
        self.warning.setVisible(False); clay.addWidget(self.warning)
        brow = QHBoxLayout(); brow.setSpacing(16)
        back = _btn("<< Back", C_DARK_BTN, h=52); back.setFixedWidth(180)
        back.clicked.connect(lambda: go_to(self.stack, "WelcomeScreen"))
        self.inst_btn = _btn("Install Selected >>", C_IW, h=52)
        self.inst_btn.clicked.connect(self._go_install)
        brow.addWidget(back); brow.addWidget(self.inst_btn, stretch=1); clay.addLayout(brow)
        lay.addWidget(content, stretch=1)

    def showEvent(self, e):
        super().showEvent(e)
        self.warning.setVisible(False)
        self._build()

    def _build(self):
        while self._ll.count() > 1:
            item = self._ll.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._checks.clear()

        MAX_SLOTS  = 3
        SLOT_W     = 28
        SLOT_GAP   = 8
        CHECKS_W   = MAX_SLOTS * SLOT_W + (MAX_SLOTS - 1) * SLOT_GAP

        for gd in ALL_GAMES:
            keys = _active_keys(gd)
            if not keys: continue
            ik = [k for k in keys if k in self.steam_installed]
            # Priority: hide iw5mp_ds (free DS) when iw5mp (full game) is present
            if "iw5mp" in ik and "iw5mp_ds" in ik:
                ik = [k for k in ik if k != "iw5mp_ds"]
                keys = [k for k in keys if k != "iw5mp_ds"]
            if not ik: continue

            color  = C_IW if gd["dev"] == "iw" else C_TREY
            client = _active_client(gd)

            row = QHBoxLayout()
            row.setSpacing(12)
            row.setContentsMargins(8, 8, 8, 8)

            # ── Per-key checkbox column ────────────────────────────────────
            checks_widget = QWidget()
            checks_widget.setFixedWidth(CHECKS_W)
            checks_layout = QHBoxLayout(checks_widget)
            checks_layout.setContentsMargins(0, 0, 0, 0)
            checks_layout.setSpacing(SLOT_GAP)

            for key in keys:
                installed   = key in self.steam_installed
                already_done = cfg.is_game_setup_for_source(key, "steam")

                slot = QWidget()
                slot.setFixedWidth(SLOT_W)
                slot_lay = QVBoxLayout(slot)
                slot_lay.setContentsMargins(0, 0, 0, 0)
                slot_lay.setSpacing(2)
                slot_lay.setAlignment(Qt.AlignHCenter)

                cb = QCheckBox()
                if not installed:
                    cb.setChecked(False)
                    cb.setEnabled(False)
                elif already_done:
                    cb.setChecked(False)
                else:
                    cb.setChecked(True)

                mode_color = C_TREY if not installed else "#666677"
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

            # ── Game name + optional offline note ──────────────────────────
            name_wrap = QWidget()
            name_wrap_lay = QVBoxLayout(name_wrap)
            name_wrap_lay.setContentsMargins(0, 0, 0, 0)
            name_wrap_lay.setSpacing(2)

            any_installed = len(ik) > 0
            name_color = "#FFF" if any_installed else "#555566"
            name_lbl = _lbl(gd["base"], 14, name_color, align=Qt.AlignLeft, wrap=False)
            name_wrap_lay.addWidget(name_lbl)

            row.addWidget(name_wrap, stretch=1)

            # ── Client badge ───────────────────────────────────────────────
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
        for key, (cb, gd) in self._checks.items():
            if not cb.isChecked(): continue
            if key not in self.steam_installed: continue
            selected.append((key, gd, self.steam_installed[key]))
        if not selected:
            # Advanced flow: own games are already queued on OwnInstallScreen,
            # so zero Steam games is valid. Route straight through.
            if cfg.get_game_source() == "own":
                own_screen = get_screen(self.stack, "OwnInstallScreen")
                own_screen.steam_selected = []
                own_screen.steam_root = self.steam_root
                # Build a temporary list to check for iw4x in own games
                _own_sel = own_screen.own_selected or {}
                _own_tmp = []
                for _k, _g in _own_sel.items():
                    for _gd in ALL_GAMES:
                        if _k in _active_keys(_gd):
                            _own_tmp.append((_k, _gd, _g)); break
                own_screen.install_iw4x_dlc = _ask_iw4x_dlc(self, _own_tmp)
                go_to(self.stack, "OwnInstallScreen")
                return
            self.warning.setText("Select at least one game to continue.")
            self.warning.setVisible(True); return

        # Advanced flow -- OwnInstallScreen handles both Steam + own games
        if cfg.get_game_source() == "own":
            own_screen = get_screen(self.stack, "OwnInstallScreen")
            own_screen.steam_selected = selected
            own_screen.steam_root = self.steam_root
            # Merge steam + own selections for DLC prompt check
            _own_sel = own_screen.own_selected or {}
            _own_tmp = []
            for _k, _g in _own_sel.items():
                for _gd in ALL_GAMES:
                    if _k in _active_keys(_gd):
                        _own_tmp.append((_k, _gd, _g)); break
            own_screen.install_iw4x_dlc = _ask_iw4x_dlc(self, selected + _own_tmp)
            own_screen.install_t7x_opt = _ask_t7x_install(self, selected + _own_tmp)
            go_to(self.stack, "OwnInstallScreen")
            return

        # Standard flow -- InstallScreen handles Steam games only
        s = get_screen(self.stack, "InstallScreen")
        s.selected   = selected
        s.steam_root = self.steam_root
        s.install_iw4x_dlc = _ask_iw4x_dlc(self, selected)
        s.install_t7x_opt = _ask_t7x_install(self, selected)
        go_to(self.stack, "InstallScreen")

# ── InstallScreen ─────────────────────────────────────────────────────────────
class InstallScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.selected=[]; self.steam_root=""; self.screen_name = "InstallScreen"
        self._plut_event = threading.Event()
        self._manual_dl_event = threading.Event()
        self._manual_dl_ok = False
        self._return_to_management = False
        self.install_t7x_opt = False

        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        hdr = QWidget(); hdr.setFixedHeight(60)
        hdr.setStyleSheet(f"background:{C_CARD};")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(20,0,20,0)
        _ht = QLabel("DECKOPS"); _ht.setFont(font(22, display=True))
        _ht.setStyleSheet("color:#FFF;background:transparent;"); hl.addWidget(_ht)
        _nb = QLabel("NIGHTLY"); _nb.setFont(font(9, bold=True))
        _nb.setStyleSheet(
            "color:#F47B20;background:#2A1A08;border:1px solid #F47B20;"
            "border-radius:4px;padding:1px 6px;"
        )
        hl.addWidget(_nb); hl.addStretch()
        lay.addWidget(hdr)

        content = QWidget()
        clay = QVBoxLayout(content); clay.setContentsMargins(80,20,80,60); clay.setSpacing(20)
        self.cur = _lbl("Preparing...", 16, "#CCC"); clay.addWidget(self.cur)
        self.bar = QProgressBar(); self.bar.setMaximum(100); self.bar.setTextVisible(False)
        self.bar.setFixedHeight(22)
        bw = QHBoxLayout(); bw.setContentsMargins(60,0,60,0); bw.addWidget(self.bar)
        clay.addLayout(bw)
        self.stat = _lbl("", 13, C_IW); clay.addWidget(self.stat)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(font(11))
        self.log.setStyleSheet("QPlainTextEdit{color:#666677;background:transparent;border:none;padding:10px;}")
        clay.addWidget(self.log, stretch=1)

        self.plut_warn = _lbl(
            "⚠  LCD: Plutonium takes time to download and launch.\n"
            "     Please be patient — do NOT click the button below until\n"
            "     Plutonium has fully loaded, you have logged in, and closed the window.",
            12, C_TREY, align=Qt.AlignCenter,
        )
        self.plut_warn.setStyleSheet(
            f"color:{C_TREY};background:#2A1A08;border:1px solid {C_TREY};"
            "border-radius:8px;padding:10px 16px;"
        )
        self.plut_warn.setVisible(False)
        clay.addWidget(self.plut_warn)

        self.plut_btn = _btn("I've closed Plutonium  ✓", C_TREY, size=13, h=52)
        self.plut_btn.setFixedWidth(460); self.plut_btn.setVisible(False)
        self.plut_btn.clicked.connect(self._confirm_plut)
        pw = QHBoxLayout(); pw.addStretch(); pw.addWidget(self.plut_btn); pw.addStretch()
        clay.addLayout(pw)

        self.cont_btn = _btn("Continue  >>", C_IW, size=13, h=52)
        self.cont_btn.setFixedWidth(320); self.cont_btn.setVisible(False)
        self.cont_btn.clicked.connect(lambda: go_to(self.stack, "SetupCompleteScreen"))
        cw = QHBoxLayout(); cw.addStretch(); cw.addWidget(self.cont_btn); cw.addStretch()
        clay.addLayout(cw)
        lay.addWidget(content, stretch=1)

        self._s = _Sigs()
        self._s.progress.connect(lambda p,m: (self.bar.setValue(p), self.cur.setText(m)))
        self._s.log.connect(self._append_log)
        self._s.done.connect(self._on_done)
        self._s.plut_wait.connect(self._show_plut_wait)
        self._s.plut_go.connect(self._hide_plut_wait)
        self._s.pulse_start.connect(self._start_pulse)
        self._s.pulse_stop.connect(self._stop_pulse)
        self._s.manual_dl.connect(self._show_manual_dl_dialog)

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

    def _show_plut_wait(self):
        is_lcd = cfg.is_lcd()
        self.plut_warn.setVisible(is_lcd)
        self.plut_btn.setVisible(True)

    def _hide_plut_wait(self):
        self.plut_warn.setVisible(False)
        self.plut_btn.setVisible(False)

    def _append_log(self, text):
        self.log.appendPlainText(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
        _log_to_file(text)

    def showEvent(self, e):
        super().showEvent(e)
        self.bar.setValue(0); self.log.clear()
        self.plut_btn.setVisible(False)
        self.plut_warn.setVisible(False)
        self._stop_pulse()
        self._plut_event.clear()
        self._manual_dl_event.clear()
        self._manual_dl_ok = False
        # Route the continue button based on whether this was triggered
        # from ManagementScreen (return to My Games) or the first-run
        # wizard (go to SetupCompleteScreen).
        try:
            self.cont_btn.clicked.disconnect()
        except Exception:
            pass
        if self._return_to_management:
            self.cont_btn.setText("Back to My Games  >>")
            self.cont_btn.clicked.connect(self._go_management)
            self._return_to_management = False
        else:
            self.cont_btn.setText("Continue  >>")
            self.cont_btn.clicked.connect(lambda: go_to(self.stack, "SetupCompleteScreen"))
        _log_to_file("── Install started ──")
        QTimer.singleShot(400, lambda: threading.Thread(target=self._run, daemon=True).start())

    def _confirm_plut(self):
        self._plut_event.set()

    def _show_manual_dl_dialog(self, url, dest_folder, filename, label):
        """
        Show a dialog telling the user to manually download a file.
        Runs on the main thread (called via signal from worker).
        """
        os.makedirs(dest_folder, exist_ok=True)
        dest_path = os.path.join(dest_folder, filename)

        msg = QMessageBox(self)
        msg.setWindowTitle(f"{label} — Download Failed")
        msg.setTextFormat(Qt.RichText)
        msg.setText(
            f"<b>{label}</b> could not be downloaded automatically.<br><br>"
            f'Download it manually here:<br>'
            f'<a href="{url}">{url}</a><br><br>'
            f'Then place <b>{filename}</b> in:<br>'
            f'<code>{dest_folder}</code><br><br>'
            f'Click <b>Open Folder</b> to open the destination, then '
            f'<b>I\'ve Placed It</b> when the file is in place.'
        )
        open_btn = msg.addButton("Open Folder", QMessageBox.ActionRole)
        done_btn = msg.addButton("I've Placed It", QMessageBox.AcceptRole)
        skip_btn = msg.addButton("Skip", QMessageBox.RejectRole)

        # Keep dialog open until user clicks Done or Skip
        while True:
            msg.exec_()
            clicked = msg.clickedButton()
            if clicked == open_btn:
                subprocess.Popen(["xdg-open", dest_folder])
                # Re-show the dialog
                continue
            elif clicked == done_btn:
                if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                    self._manual_dl_ok = True
                    self._manual_dl_event.set()
                    return
                # File not there yet — tell user and loop
                QMessageBox.warning(
                    self, "File Not Found",
                    f"{filename} was not found in:\n{dest_folder}\n\n"
                    "Make sure the file is downloaded and placed in the correct folder.",
                )
                continue
            else:
                # Skip
                self._manual_dl_ok = False
                self._manual_dl_event.set()
                return

    def _on_done(self, _):
        self._stop_pulse()
        self.cur.setText("Installation complete!")
        self.cont_btn.setVisible(True)

    def _go_management(self):
        # Restart Steam so shortcuts and compat tool changes take effect.
        os.system("gtk-launch steam.desktop &")
        root = find_steam_root()
        get_screen(self.stack, "ManagementScreen").set_installed(find_installed_games(parse_library_folders(root)))
        go_to(self.stack, "ManagementScreen")

    def _run(self):
        from wrapper import get_proton_path, find_compatdata, kill_steam
        from plutonium_oled import launch_bootstrapper, is_plutonium_ready, install_plutonium
        from cod4x import install_cod4x
        from iw4x import install_iw4x
        from iw3sp import install_iw3sp
        from t6sp_mod import install_t6sp_mod
        from cleanops import install_cleanops
        from t7x import install_t7x
        from ge_proton import install_ge_proton, set_compat_tool, MANAGED_APPIDS

        selected_keys   = [key for key, _, _ in self.selected]
        has_plut        = any(KEY_CLIENT.get(k) == "plutonium" for k in selected_keys)
        has_cod4        = any(KEY_CLIENT.get(k) in ("cod4x", "iw3sp") for k in selected_keys)
        has_iw4x        = any(KEY_CLIENT.get(k) == "iw4x" for k in selected_keys)
        has_cleanops    = any(KEY_CLIENT.get(k) == "cleanops" for k in selected_keys)
        has_t6sp_mod    = any(KEY_CLIENT.get(k) == "t6sp_mod" for k in selected_keys)

        # ── T7X opt-in: inject t7x into selected if user chose to install it ──
        has_t7x = getattr(self, "install_t7x_opt", False) and has_cleanops
        if has_t7x:
            # Find the t7 (CleanOps) entry and clone it for t7x
            for k, gd, g in self.selected:
                if k == "t7":
                    self.selected.append(("t7x", gd, dict(g)))
                    selected_keys.append("t7x")
                    break
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
                    kill_steam(on_progress=lambda msg: self._s.log.emit(f"  {msg}"))
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

        # ── Copy deps from GE-Proton default_pfx into all game prefixes ──────
        # Every selected game gets its prefix preloaded — no exceptions.
        # ensure_all_prefix_deps handles deduplication and skips prefixes
        # that are already initialized.
        proton = get_proton_path(self.steam_root)

        if ge_version:
            from ge_proton import ensure_all_prefix_deps
            from detect_games import GAMES as _GAMES_MAP
            self._s.log.emit("Installing prefix dependencies...")
            self._s.pulse_start.emit("Installing prefix dependencies")
            dep_targets = []
            for key, gd, game in self.selected:
                # Use per-key appid from GAMES, not card-level gd["appid"].
                # Card-level appid is wrong for keys that have their own appid
                # (e.g. t6zm=212910, t6sp=202970 vs card appid 202990).
                appid = _GAMES_MAP[key]["appid"] if key in _GAMES_MAP else gd["appid"]
                _install_dir = game["install_dir"] if game else None
                compat = find_compatdata(self.steam_root, appid,
                                         game_install_dir=_install_dir)
                if not compat and game and game.get("install_dir"):
                    # Prefix doesn't exist yet — build the path from the game's
                    # steamapps dir so ensure_prefix_deps can create it
                    steamapps = os.path.dirname(os.path.dirname(game["install_dir"]))
                    compat = os.path.join(steamapps, "compatdata", str(appid))
                if compat:
                    dep_targets.append((key, compat))
            if dep_targets:
                done = ensure_all_prefix_deps(
                    ge_version, dep_targets,
                    on_progress=lambda msg: self._s.log.emit(msg),
                    proton_path=proton,
                    steam_root=self.steam_root,
                )
                self._s.log.emit(f"✓  Prefix dependencies: {done}/{len(dep_targets)} ready")
            self._s.pulse_stop.emit()

        # ── Plutonium bootstrapper (Steam still running) ──────────────────────
        if has_plut:
            is_lcd = cfg.is_lcd()

            # LCD and OLED / Other both require the user to log in, just in different
            # prefixes. LCD logs in inside HGL's shared default prefix so
            # the auth state is bound to the exact Wine prefix that will
            # later launch the games. OLED / Other logs in inside the dedicated
            # DeckOps prefix at ~/.local/share/deckops/plutonium_prefix/.
            if is_lcd:
                from plutonium_lcd import (launch_bootstrapper_lcd,
                                    is_plutonium_ready_lcd)
                plut_ready = is_plutonium_ready_lcd()
            else:
                plut_ready = is_plutonium_ready()

            if not plut_ready:
                if is_lcd:
                    self._s.progress.emit(12, "Setting up Plutonium through HGL...")
                    self._s.log.emit(
                        "Setting up Plutonium through HGL...\n"
                        "  1. HGL will download and launch Plutonium (this may take a few minutes)\n"
                        "  2. Log in with your Plutonium account\n"
                        "  3. Close the Plutonium window\n"
                        "  4. Click the button below to continue"
                    )
                else:
                    self._s.progress.emit(12, "Launching Plutonium — please log in...")
                    self._s.log.emit(
                        "Plutonium is launching now.\n"
                        "  1. Wait for it to finish downloading\n"
                        "  2. Log in with your Plutonium account\n"
                        "  3. Close the Plutonium window\n"
                        "  4. Click the button below to continue"
                    )
                try:
                    if is_lcd:
                        launch_bootstrapper_lcd(
                            on_progress=lambda p, m: self._s.progress.emit(p, m)
                        )
                    else:
                        launch_bootstrapper(
                            proton,
                            on_progress=lambda p, m: self._s.progress.emit(p, m),
                            steam_root=self.steam_root,
                        )
                except DownloadError as dl_ex:
                    self._s.log.emit(f"⚠  {dl_ex.label} download failed — manual download needed")
                    self._manual_dl_event.clear()
                    self._manual_dl_ok = False
                    self._s.manual_dl.emit(
                        dl_ex.url,
                        os.path.dirname(dl_ex.dest),
                        os.path.basename(dl_ex.dest),
                        dl_ex.label,
                    )
                    self._manual_dl_event.wait()
                    if not self._manual_dl_ok:
                        self._s.log.emit("  ✗  Skipped by user.")
                        self._s.progress.emit(100, "Setup incomplete."); self._s.done.emit(True); return
                    self._s.log.emit(f"  ✓  {dl_ex.label} placed manually")
                except Exception as ex:
                    self._s.log.emit(f"✗  Plutonium launch failed: {ex}")
                    self._s.progress.emit(100, "Setup failed."); self._s.done.emit(True); return

                if is_lcd:
                    self._s.log.emit(
                        "⏳  HGL is launching Plutonium. This may take a minute on first run\n"
                        "   while HGL sets up the Wine prefix."
                    )
                    self._s.pulse_start.emit("Waiting for Plutonium login")

                self._s.plut_wait.emit()
                self._plut_event.wait()
                self._s.plut_go.emit()

                if is_lcd:
                    self._s.pulse_stop.emit()

                # Verify Plutonium is ready after the user closed the window
                ready_check = is_plutonium_ready_lcd() if is_lcd else is_plutonium_ready()
                if not ready_check:
                    self._s.log.emit(
                        "✗  Plutonium does not appear to be fully set up.\n"
                        "   Make sure you logged in and let it finish downloading."
                    )
                    self._s.progress.emit(100, "Setup incomplete."); self._s.done.emit(True); return

                self._s.log.emit("✓  Plutonium ready.")
            else:
                self._s.progress.emit(12, "Waiting for Plutonium...")
                self._s.log.emit(
                    "Wait for Plutonium to finish updating, sign in, then close Plutonium."
                )
                self._s.plut_wait.emit()
                self._plut_event.wait()
                self._s.plut_go.emit()

        # ── Kill Steam once — everything from here runs with Steam closed ─────
        _kill_steam_once()

        # ── Clean slate: clear ALL launch options and compat tools ─────────
        # Previous installs (LCD→OLED switch, older DeckOps versions) can
        # leave stale launch options and compat tool entries that conflict
        # with the current install. Wipe everything for MANAGED_APPIDS
        # first, then re-apply what's needed via _apply_compat below.
        try:
            from wrapper import clear_launch_options, clear_compat_tool
            for appid in MANAGED_APPIDS:
                clear_launch_options(self.steam_root, appid)
            clear_compat_tool(MANAGED_APPIDS)
            self._s.log.emit("✓  Cleared all launch options and compat tools")
        except Exception as ex:
            self._s.log.emit(f"  Launch option / compat tool cleanup skipped: {ex}")

        _apply_compat()
        _set_launch_defaults()

        # ── Plutonium games ───────────────────────────────────────────────────
        if has_plut:
            # Create the launcher shortcut FIRST so the appid/prefix exist
            # before per-game installs mirror configs into it.
            try:
                from shortcut import create_launcher_shortcut
                create_launcher_shortcut(
                    on_progress=lambda m: self._s.log.emit(m)
                )
            except Exception as ex:
                self._s.log.emit(f"  Launcher shortcut failed: {ex}")

            # Preheat the offline launcher prefix with GE-Proton's full
            # dependency set (d3dx9, d3dcompiler, vcrun, xact, etc.).
            # The launcher prefix is a non-Steam shortcut — Steam/Proton
            # never initializes it automatically, so it misses the DLLs
            # that per-game prefixes get on first launch.
            try:
                from shortcut import get_launcher_appid
                from ge_proton import ensure_prefix_deps
                launcher_appid = get_launcher_appid()
                launcher_compat = os.path.join(
                    os.path.expanduser("~/.local/share/Steam"),
                    "steamapps", "compatdata", str(launcher_appid),
                )
                ensure_prefix_deps(
                    ge_version, launcher_compat,
                    on_progress=lambda msg: self._s.log.emit(msg),
                    proton_path=proton,
                    steam_root=self.steam_root,
                )
                self._s.log.emit("✓  Offline launcher prefix ready")
            except Exception as ex:
                self._s.log.emit(f"  Launcher prefix deps skipped: {ex}")

            # LCD: also prepare Heroic's shared prefix. Heroic initializes
            # it during Plutonium login, but may not include the full d3dx9
            # set needed for all games. ensure_prefix_deps only copies
            # missing DLLs so it won't overwrite Heroic's own files.
            if cfg.is_lcd():
                try:
                    from ge_proton import ensure_prefix_deps as _epd
                    from plutonium_lcd import HEROIC_DEFAULT_WINE_PREFIX
                    if os.path.isdir(HEROIC_DEFAULT_WINE_PREFIX):
                        _epd(
                            ge_version, HEROIC_DEFAULT_WINE_PREFIX,
                            on_progress=lambda msg: self._s.log.emit(msg),
                            proton_path=proton,
                            steam_root=self.steam_root,
                        )
                        self._s.log.emit("✓  Heroic shared prefix ready")
                except Exception as ex:
                    self._s.log.emit(f"  Heroic prefix deps skipped: {ex}")

            plut_selected = [(k, gd, g) for k, gd, g in self.selected if KEY_CLIENT.get(k) == "plutonium"]
            total_plut = len(plut_selected)
            for idx, (key, gd, game) in enumerate(plut_selected):
                bp = 30 + int(idx / max(total_plut, 1) * 30)
                base_name = gd["base"]
                if base_name not in logged_bases:
                    self._s.progress.emit(bp, f"Setting up {base_name}...")
                def op_plut(pct, msg, _b=bp): self._s.progress.emit(_b + int(pct / 100 * 8), msg)
                try:
                    from plutonium_oled import GAME_META as _PLUT_META
                    _plut_appid = _PLUT_META[key][0] if key in _PLUT_META else gd["appid"]
                    compat = find_compatdata(self.steam_root, _plut_appid,
                                              game_install_dir=game["install_dir"] if game else None)
                    install_plutonium(game, key, self.steam_root, proton, compat, op_plut)
                    # plutonium installer (plutonium_oled.py / plutonium_lcd.py)
                    # owns its own mark_game_setup call so lan_wrapper_path
                    # and other install-side metadata are preserved.
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
                    compat = find_compatdata(self.steam_root, gd["appid"],
                                              game_install_dir=game["install_dir"] if game else None)
                    install_iw4x(game, self.steam_root, proton, compat, op_iw4x,
                                 install_dlc=getattr(self, 'install_iw4x_dlc', False))
                    cfg.mark_game_setup(key, "iw4x", source="steam")
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
                    _install_dir = game["install_dir"] if game else None
                    compat = find_compatdata(self.steam_root, gd["appid"],
                                             game_install_dir=_install_dir)
                    c = KEY_CLIENT.get(key, gd["client"])
                    if c == "cod4x":
                        install_cod4x(game, self.steam_root, proton, compat, op_cod4,
                                      appid=gd["appid"])
                    elif c == "iw3sp":
                        install_iw3sp(game, self.steam_root, proton, compat, op_cod4)
                    cfg.mark_game_setup(key, c, source="steam")
                    if base_name not in logged_bases:
                        self._s.log.emit(f"✓  {base_name} done")
                        logged_bases.add(base_name)
                except DownloadError as dl_ex:
                    self._s.log.emit(f"⚠  {dl_ex.label} download failed — manual download needed")
                    self._manual_dl_event.clear()
                    self._manual_dl_ok = False
                    self._s.manual_dl.emit(
                        dl_ex.url,
                        os.path.dirname(dl_ex.dest),
                        os.path.basename(dl_ex.dest),
                        dl_ex.label,
                    )
                    self._manual_dl_event.wait()
                    if not self._manual_dl_ok:
                        self._s.log.emit(f"  ✗  {base_name} skipped by user.")
                    else:
                        self._s.log.emit(f"  ✓  {dl_ex.label} placed manually — re-run install to finish setup")
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        # ── T7X (BO3 AlterWare client) — Steam closed ─────────────────────────
        # Must run BEFORE CleanOps — CleanOps drops d3d11.dll into the
        # stock BO3 dir, and the symlink farm would pick it up if it
        # already exists. Running T7x first builds symlinks from a clean
        # stock dir, then CleanOps only touches the stock dir afterward.
        if has_t7x:
            for key, gd, game in [(k, gd, g) for k, gd, g in self.selected if KEY_CLIENT.get(k) == "t7x"]:
                base_name = gd["base"]
                self._s.progress.emit(86, f"Setting up T7x...")
                def op_t7x(pct, msg): self._s.progress.emit(86 + int(pct / 100 * 2), msg)
                try:
                    t7x_dir = install_t7x(game, on_progress=op_t7x)
                    game["install_dir"] = t7x_dir
                    cfg.mark_game_setup(key, "t7x", source="steam")
                    self._s.log.emit(f"✓  {base_name} (T7x) done")
                    logged_bases.add(base_name)
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} (T7x) failed: {ex}")

        # ── CleanOps (BO3) — Steam closed ─────────────────────────────────────
        if has_cleanops:
            for key, gd, game in [(k, gd, g) for k, gd, g in self.selected if KEY_CLIENT.get(k) == "cleanops"]:
                base_name = gd["base"]
                self._s.progress.emit(88, f"Setting up {base_name}...")
                def op_cleanops(pct, msg): self._s.progress.emit(88 + int(pct / 100 * 4), msg)
                try:
                    compat = find_compatdata(self.steam_root, gd["appid"],
                                              game_install_dir=game["install_dir"] if game else None)
                    install_cleanops(game, self.steam_root, proton, compat, op_cleanops)
                    cfg.mark_game_setup(key, "cleanops", source="steam")
                    self._s.log.emit(f"✓  {base_name} done")
                    logged_bases.add(base_name)
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        # ── AlterWare (Ghosts / Advanced Warfare) — Steam closed ──────────────
        has_alterware = any(KEY_CLIENT.get(k) == "alterware" for k in selected_keys)
        if has_alterware:
            from alterware import install_alterware
            for key, gd, game in [(k, gd, g) for k, gd, g in self.selected if KEY_CLIENT.get(k) == "alterware"]:
                base_name = gd["base"]
                self._s.progress.emit(91, f"Setting up {base_name}...")
                def op_alterware(pct, msg): self._s.progress.emit(91 + int(pct / 100 * 4), msg)
                try:
                    from detect_games import GAMES as _GAMES_MAP
                    _appid = _GAMES_MAP[key]["appid"] if key in _GAMES_MAP else gd["appid"]
                    _install_dir = game["install_dir"] if game else None
                    compat = find_compatdata(self.steam_root, _appid,
                                              game_install_dir=_install_dir)
                    if not compat and _install_dir:
                        steamapps = os.path.dirname(os.path.dirname(_install_dir))
                        compat = os.path.join(steamapps, "compatdata", str(_appid))
                    install_alterware(game, key, self.steam_root, proton, compat, op_alterware,
                                     source="steam")
                    cfg.mark_game_setup(key, "alterware", source="steam")
                    self._s.log.emit(f"✓  {base_name} done")
                    logged_bases.add(base_name)
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        # ── T6SP-MOD (BO2 Singleplayer) — Steam closed ───────────────────
        if has_t6sp_mod:
            for key, gd, game in [(k, gd, g) for k, gd, g in self.selected if KEY_CLIENT.get(k) == "t6sp_mod"]:
                base_name = gd["base"]
                self._s.progress.emit(95, f"Installing Rattpak's T6SP-MOD (Beta)...")
                def op_t6sp(pct, msg): self._s.progress.emit(95 + int(pct / 100 * 2), msg)
                try:
                    _install_dir = game["install_dir"] if game else None
                    compat = find_compatdata(self.steam_root, gd["appid"],
                                              game_install_dir=_install_dir)
                    install_t6sp_mod(game, self.steam_root, proton, compat, op_t6sp)
                    cfg.mark_game_setup(key, "t6sp_mod", source="steam")
                    self._s.log.emit(f"✓  {base_name} (T6SP-MOD) done")
                    logged_bases.add(base_name)
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        # ── Vanilla Steam games (no mod client, just configs + controllers) ──
        # Games like MW2 SP and MW3 SP run through Steam as-is.
        # No download or exe replacement needed. We just mark them as set up
        # so they show as installed on the My Games screen and get their
        # display configs and controller profiles applied below.
        for key, gd, game in self.selected:
            c = KEY_CLIENT.get(key, "")
            if c == "steam" and not cfg.is_game_setup_for_source(key, "steam"):
                cfg.mark_game_setup(key, "steam", source="steam")
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
            from controller_profiles import install_controller_templates, assign_controller_profiles, assign_external_controller_profiles
            install_controller_templates(
                on_progress=lambda msg: self._s.log.emit(f"  {msg}")
            )
            gyro_mode = cfg.get_gyro_mode() or "on"
            # Neptune profiles always assigned - user may play handheld too
            assign_controller_profiles(
                gyro_mode,
                on_progress=lambda msg: self._s.log.emit(f"  {msg}")
            )
            self._s.log.emit(f"✓  Neptune controller profiles assigned ({gyro_mode} mode)")
            # Docked users also get external controller profiles
            if cfg.is_docked():
                controller_type = cfg.get_external_controller() or "playstation"
                assign_external_controller_profiles(
                    controller_type,
                    gyro_mode,
                    on_progress=lambda msg: self._s.log.emit(f"  {msg}")
                )
                self._s.log.emit(f"✓  External controller profiles assigned ({controller_type})")
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
                gyro_mode=cfg.get_gyro_mode() or "on",
                on_progress=lambda msg: self._s.log.emit(msg),
                steam_root=self.steam_root,
            )
        except Exception as ex:
            self._s.log.emit(f"  Shortcuts skipped: {ex}")

        # ── Custom artwork for Steam MP/ZM games ─────────────────────────────
        try:
            from shortcut import apply_steam_artwork
            self._s.log.emit("Applying custom artwork for multiplayer games...")
            apply_steam_artwork(
                selected_keys=selected_keys,
                on_progress=lambda msg: self._s.log.emit(msg)
            )
        except Exception as ex:
            self._s.log.emit(f"  Steam artwork skipped: {ex}")

        # Standard flow always finishes here. Advanced flow uses
        # OwnInstallScreen instead and never reaches this screen.
        cfg.complete_first_run(self.steam_root)
        self._s.progress.emit(100, "All done!")
        self._s.done.emit(True)


# ── OwnInstallScreen ─────────────────────────────────────────────────────────
class OwnInstallScreen(QWidget):
    """
    Install flow for the advanced ("Steam or Other") path.

    Handles both Steam-selected games (passed from SetupScreen as
    steam_selected) and own-detected games (parked by OwnScanScreen as
    own_selected) in a single pass.

    Creates non-Steam shortcuts for own games, copies GE-Proton's
    default_pfx to build each own game's compatdata prefix automatically,
    sets GE-Proton compat for MANAGED_APPIDS and own shortcut appids,
    then installs mod clients. No manual game launch step required.
    """

    def __init__(self, stack):
        super().__init__(); self.stack = stack; self.screen_name = "OwnInstallScreen"
        self.own_selected    = {}   # dict of key -> game, set by OwnScanScreen
        self.steam_selected  = []   # list of (key, gd, game), set by SetupScreen
        self.steam_root = ""
        self._plut_event = threading.Event()
        self._manual_dl_event = threading.Event()
        self._manual_dl_ok = False
        self._return_to_management = False
        self.install_t7x_opt = False

        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        hdr = QWidget(); hdr.setFixedHeight(60)
        hdr.setStyleSheet(f"background:{C_CARD};")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(20,0,20,0)
        _ht = QLabel("DECKOPS"); _ht.setFont(font(22, display=True))
        _ht.setStyleSheet("color:#FFF;background:transparent;"); hl.addWidget(_ht)
        _nb = QLabel("NIGHTLY"); _nb.setFont(font(9, bold=True))
        _nb.setStyleSheet(
            "color:#F47B20;background:#2A1A08;border:1px solid #F47B20;"
            "border-radius:4px;padding:1px 6px;"
        )
        hl.addWidget(_nb); hl.addStretch()
        lay.addWidget(hdr)

        content = QWidget()
        clay = QVBoxLayout(content); clay.setContentsMargins(80,20,80,60); clay.setSpacing(20)
        self.cur = _lbl("Preparing...", 16, "#CCC"); clay.addWidget(self.cur)
        self.bar = QProgressBar(); self.bar.setMaximum(100); self.bar.setTextVisible(False)
        self.bar.setFixedHeight(22)
        bw = QHBoxLayout(); bw.setContentsMargins(60,0,60,0); bw.addWidget(self.bar)
        clay.addLayout(bw)
        self.stat = _lbl("", 13, C_IW); clay.addWidget(self.stat)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setFont(font(11))
        self.log.setStyleSheet("QPlainTextEdit{color:#666677;background:transparent;border:none;padding:10px;}")
        clay.addWidget(self.log, stretch=1)

        self.plut_warn = _lbl(
            "⚠  LCD: Plutonium takes time to download and launch.\n"
            "     Please be patient — do NOT click the button below until\n"
            "     Plutonium has fully loaded, you have logged in, and closed the window.",
            12, C_TREY, align=Qt.AlignCenter,
        )
        self.plut_warn.setStyleSheet(
            f"color:{C_TREY};background:#2A1A08;border:1px solid {C_TREY};"
            "border-radius:8px;padding:10px 16px;"
        )
        self.plut_warn.setVisible(False)
        clay.addWidget(self.plut_warn)

        self.plut_btn = _btn("I've closed Plutonium  ✓", C_TREY, size=13, h=52)
        self.plut_btn.setFixedWidth(460); self.plut_btn.setVisible(False)
        self.plut_btn.clicked.connect(self._confirm_plut)
        pw = QHBoxLayout(); pw.addStretch(); pw.addWidget(self.plut_btn); pw.addStretch()
        clay.addLayout(pw)

        self.cont_btn = _btn("Continue  >>", C_IW, size=13, h=52)
        self.cont_btn.setFixedWidth(320); self.cont_btn.setVisible(False)
        self.cont_btn.clicked.connect(lambda: go_to(self.stack, "SetupCompleteScreen"))
        cw = QHBoxLayout(); cw.addStretch(); cw.addWidget(self.cont_btn); cw.addStretch()
        clay.addLayout(cw)
        lay.addWidget(content, stretch=1)

        self._s = _Sigs()
        self._s.progress.connect(lambda p, m: (self.bar.setValue(p), self.cur.setText(m)))
        self._s.log.connect(self._append_log)
        self._s.done.connect(self._on_done)
        self._s.plut_wait.connect(self._show_plut_wait)
        self._s.plut_go.connect(self._hide_plut_wait)
        self._s.pulse_start.connect(self._start_pulse)
        self._s.pulse_stop.connect(self._stop_pulse)
        self._s.manual_dl.connect(self._show_manual_dl_dialog)

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

    def _show_plut_wait(self):
        is_lcd = cfg.is_lcd()
        self.plut_warn.setVisible(is_lcd)
        self.plut_btn.setVisible(True)

    def _hide_plut_wait(self):
        self.plut_warn.setVisible(False)
        self.plut_btn.setVisible(False)

    def _append_log(self, text):
        _log_to_file(text)
        self.log.appendPlainText(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def showEvent(self, e):
        super().showEvent(e)
        self.bar.setValue(0); self.log.clear()
        self.plut_btn.setVisible(False)
        self.plut_warn.setVisible(False)
        self.cont_btn.setVisible(False)
        self._plut_event.clear()
        self._manual_dl_event.clear()
        self._manual_dl_ok = False
        self._stop_pulse()
        # Route the continue button based on whether this was triggered
        # from ManagementScreen (return to My Games) or the first-run
        # wizard (go to SetupCompleteScreen).
        try:
            self.cont_btn.clicked.disconnect()
        except Exception:
            pass
        if self._return_to_management:
            self.cont_btn.setText("Back to My Games  >>")
            self.cont_btn.clicked.connect(lambda: (
                os.system("gtk-launch steam.desktop &"),
                get_screen(self.stack, "ManagementScreen").set_installed(
                    find_installed_games(parse_library_folders(find_steam_root()))
                ),
                go_to(self.stack, "ManagementScreen"),
            ))
            self._return_to_management = False
        else:
            self.cont_btn.setText("Continue  >>")
            self.cont_btn.clicked.connect(lambda: go_to(self.stack, "SetupCompleteScreen"))
        _log_to_file("── Own Install started ──")
        QTimer.singleShot(400, lambda: threading.Thread(target=self._run, daemon=True).start())

    def _confirm_plut(self):
        self._plut_event.set()

    def _show_manual_dl_dialog(self, url, dest_folder, filename, label):
        """
        Show a dialog telling the user to manually download a file.
        Runs on the main thread (called via signal from worker).
        """
        os.makedirs(dest_folder, exist_ok=True)
        dest_path = os.path.join(dest_folder, filename)

        msg = QMessageBox(self)
        msg.setWindowTitle(f"{label} — Download Failed")
        msg.setTextFormat(Qt.RichText)
        msg.setText(
            f"<b>{label}</b> could not be downloaded automatically.<br><br>"
            f'Download it manually here:<br>'
            f'<a href="{url}">{url}</a><br><br>'
            f'Then place <b>{filename}</b> in:<br>'
            f'<code>{dest_folder}</code><br><br>'
            f'Click <b>Open Folder</b> to open the destination, then '
            f'<b>I\'ve Placed It</b> when the file is in place.'
        )
        open_btn = msg.addButton("Open Folder", QMessageBox.ActionRole)
        done_btn = msg.addButton("I've Placed It", QMessageBox.AcceptRole)
        skip_btn = msg.addButton("Skip", QMessageBox.RejectRole)

        while True:
            msg.exec_()
            clicked = msg.clickedButton()
            if clicked == open_btn:
                subprocess.Popen(["xdg-open", dest_folder])
                continue
            elif clicked == done_btn:
                if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                    self._manual_dl_ok = True
                    self._manual_dl_event.set()
                    return
                QMessageBox.warning(
                    self, "File Not Found",
                    f"{filename} was not found in:\n{dest_folder}\n\n"
                    "Make sure the file is downloaded and placed in the correct folder.",
                )
                continue
            else:
                self._manual_dl_ok = False
                self._manual_dl_event.set()
                return

    def _on_done(self, _):
        self._stop_pulse()
        self.cur.setText("Installation complete!\n\nIf you enjoy these mods, please consider starring the original creators' GitHub repositories!")
        self.cont_btn.setVisible(True)

    def _run(self):
        import traceback as _tb
        try:
            self._run_inner()
        except Exception:
            err = _tb.format_exc()
            _log_to_file(f"[FATAL] OwnInstallScreen._run crashed:\n{err}")
            try:
                self._s.log.emit(f"✗ Install failed with error:\n{err}")
                self._s.progress.emit(100, "Install failed — see log.")
                self._s.done.emit(True)
            except Exception:
                pass

    def _run_inner(self):
        from wrapper import get_proton_path, find_compatdata, kill_steam, set_compat_tool
        from shortcut import enrich_own_games, write_own_shortcuts
        from cod4x import install_cod4x
        from iw4x import install_iw4x
        from iw3sp import install_iw3sp
        from t6sp_mod import install_t6sp_mod
        from cleanops import install_cleanops
        from t7x import install_t7x
        from ge_proton import install_ge_proton, MANAGED_APPIDS

        # Build the combined selected list from both Steam and own sources.
        # own_selected is a dict {key: game_dict} from OwnScanScreen.
        # steam_selected is a list [(key, gd, game)] from SetupScreen.
        # We need to merge them into self.selected as [(key, gd, game)].
        own_as_tuples = []
        for k, g in self.own_selected.items():
            for gd in ALL_GAMES:
                if k in _active_keys(gd):
                    own_as_tuples.append((k, gd, g)); break
        self.selected = list(self.steam_selected) + own_as_tuples

        selected_keys = [key for key, _, _ in self.selected]
        logged_bases  = set()
        has_plut      = any(KEY_CLIENT.get(k) == "plutonium" for k in selected_keys)
        has_cod4      = any(KEY_CLIENT.get(k) in ("cod4x", "iw3sp") for k in selected_keys)
        has_t6sp_mod  = any(KEY_CLIENT.get(k) == "t6sp_mod" for k in selected_keys)

        # ── GE-Proton download (Steam still running) ─────────────────────
        ge_version = None
        try:
            self._s.pulse_start.emit("Installing GE-Proton")
            self._s.log.emit("Installing GE-Proton...")
            ge_version = install_ge_proton(
                on_progress=lambda pct, msg: self._s.progress.emit(2 + int(pct * 0.06), msg)
            )
            self._s.pulse_stop.emit()
            self._s.log.emit(f"✓  {ge_version} downloaded")
            cfg.set_ge_proton_version(ge_version)
        except Exception as ex:
            self._s.pulse_stop.emit()
            self._s.log.emit(f"  GE-Proton setup skipped: {ex}")

        proton = get_proton_path(self.steam_root)

        # ── Plutonium bootstrapper (Steam still running) ─────────────────
        # Downloads Plutonium and launches it so the user can log in. LCD
        # routes through HGL (shared default prefix); OLED uses the
        # dedicated DeckOps prefix via Proton directly.
        if has_plut:
            from plutonium_oled import (launch_bootstrapper, is_plutonium_ready,
                                   install_plutonium)
            from plutonium_oled import GAME_META as _PLUT_META
            is_lcd = cfg.is_lcd()

            if is_lcd:
                from plutonium_lcd import (launch_bootstrapper_lcd,
                                    is_plutonium_ready_lcd)
                plut_ready = is_plutonium_ready_lcd()
            else:
                plut_ready = is_plutonium_ready()

            if not plut_ready:
                if is_lcd:
                    self._s.progress.emit(10, "Setting up Plutonium through HGL...")
                    self._s.log.emit(
                        "Setting up Plutonium through HGL...\n"
                        "  1. HGL will download and launch Plutonium (this may take a few minutes)\n"
                        "  2. Log in with your Plutonium account\n"
                        "  3. Close the Plutonium window\n"
                        "  4. Click the button below to continue"
                    )
                else:
                    self._s.progress.emit(10, "Launching Plutonium — please log in...")
                    self._s.log.emit(
                        "Plutonium is launching now.\n"
                        "  1. Wait for it to finish downloading\n"
                        "  2. Log in with your Plutonium account\n"
                        "  3. Close the Plutonium window\n"
                        "  4. Click the button below to continue"
                    )
                try:
                    if is_lcd:
                        launch_bootstrapper_lcd(
                            on_progress=lambda p, m: self._s.progress.emit(p, m)
                        )
                    else:
                        launch_bootstrapper(
                            proton,
                            on_progress=lambda p, m: self._s.progress.emit(p, m),
                            steam_root=self.steam_root,
                        )
                except DownloadError as dl_ex:
                    self._s.log.emit(f"⚠  {dl_ex.label} download failed — manual download needed")
                    self._manual_dl_event.clear()
                    self._manual_dl_ok = False
                    self._s.manual_dl.emit(
                        dl_ex.url,
                        os.path.dirname(dl_ex.dest),
                        os.path.basename(dl_ex.dest),
                        dl_ex.label,
                    )
                    self._manual_dl_event.wait()
                    if not self._manual_dl_ok:
                        self._s.log.emit("  ✗  Skipped by user.")
                        self._s.progress.emit(100, "Setup incomplete."); self._s.done.emit(True); return
                    self._s.log.emit(f"  ✓  {dl_ex.label} placed manually")
                except Exception as ex:
                    self._s.log.emit(f"✗  Plutonium launch failed: {ex}")
                    self._s.progress.emit(100, "Setup failed."); self._s.done.emit(True); return

                if is_lcd:
                    self._s.log.emit(
                        "⏳  HGL is launching Plutonium. This may take a minute on first run\n"
                        "   while HGL sets up the Wine prefix."
                    )
                    self._s.pulse_start.emit("Waiting for Plutonium login")

                self._s.plut_wait.emit()
                self._plut_event.wait()
                self._s.plut_go.emit()

                if is_lcd:
                    self._s.pulse_stop.emit()

                ready_check = is_plutonium_ready_lcd() if is_lcd else is_plutonium_ready()
                if not ready_check:
                    self._s.log.emit(
                        "✗  Plutonium does not appear to be fully set up.\n"
                        "   Make sure you logged in and let it finish downloading."
                    )
                    self._s.progress.emit(100, "Setup incomplete."); self._s.done.emit(True); return

                self._s.log.emit("✓  Plutonium ready.")
            else:
                self._s.log.emit("✓  Plutonium already set up.")

        # ── Kill Steam ────────────────────────────────────────────────────
        self._s.progress.emit(18, "Closing Steam...")
        self._s.log.emit("Closing Steam...")
        try:
            kill_steam(on_progress=lambda msg: self._s.log.emit(f"  {msg}"))
            self._s.log.emit("  ✓ Steam closed.")
        except Exception as ex:
            self._s.log.emit(f"  Could not close Steam: {ex}")

        # ── Clean slate: clear ALL launch options and compat tools ─────
        # Previous installs (LCD→OLED switch, older DeckOps versions) can
        # leave stale launch options and compat tool entries that conflict
        # with the current install. Wipe everything for MANAGED_APPIDS
        # first, then re-apply what's needed below.
        try:
            from wrapper import clear_launch_options, clear_compat_tool
            for appid in MANAGED_APPIDS:
                clear_launch_options(self.steam_root, appid)
            clear_compat_tool(MANAGED_APPIDS)
            self._s.log.emit("✓  Cleared all launch options and compat tools")
        except Exception as ex:
            self._s.log.emit(f"  Launch option / compat tool cleanup skipped: {ex}")

        # ── Set GE-Proton compat for MANAGED_APPIDS ──────────────────────
        # Must run AFTER kill_steam - Steam overwrites config.vdf on exit.
        # Only write for Steam appids if the user actually has Steam games
        # selected - otherwise this may trigger Steam to re-download games.
        if ge_version and self.steam_selected:
            try:
                set_compat_tool(MANAGED_APPIDS, ge_version)
                self._s.log.emit(f"✓  {ge_version} set for Steam game appids")
            except Exception as ex:
                self._s.log.emit(f"  CompatToolMapping for Steam appids skipped: {ex}")

        # ── T7X opt-in: inject t7x into selected if user chose it ─────
        # Injection must happen early so t7x is included in prefix init,
        # shortcuts, and selected_keys. Actual install runs later (after
        # CleanOps) to match the original phase order.
        has_cleanops = any(KEY_CLIENT.get(k) == "cleanops" for k in selected_keys)
        has_t7x = getattr(self, "install_t7x_opt", False) and has_cleanops
        if has_t7x:
            for k, gd, g in list(self.selected):
                if k == "t7":
                    t7x_tuple = ("t7x", gd, dict(g))
                    self.selected.append(t7x_tuple)
                    self.steam_selected.append(t7x_tuple)
                    selected_keys.append("t7x")
                    break

        # ── Enrich own game dicts (shortcut_appid, compatdata_path) ───────
        # enrich_own_games computes CRC-based appids, prefix paths, and
        # resolved exe/launch options WITHOUT writing any VDF entries.
        # Must run before ensure_all_prefix_deps. Actual shortcut writing
        # is deferred to write_own_shortcuts() after all mod clients are
        # installed so every target exe exists on disk.
        self._s.progress.emit(20, "Computing own game shortcuts...")
        self._s.log.emit("Enriching own game data...")
        gyro_mode = cfg.get_gyro_mode() or "on"
        own_games_dict = {k: g for k, g in self.own_selected.items()}
        own_games_dict = enrich_own_games(
            own_games=own_games_dict,
            selected_keys=[k for k in self.own_selected],
            on_progress=lambda msg: self._s.log.emit(msg),
        )
        _log_to_file("[BREADCRUMB] enrich_own_games returned")

        # Update self.selected with enriched own game dicts (shortcut_appid etc)
        self.selected = [
            (k, gd, own_games_dict.get(k, g)) for k, gd, g in self.selected
        ]
        # Rebuild own_games with enriched dicts for compat tool mapping later.
        # Only include own-selected keys - Steam games don't have shortcut_appid.
        own_games = {k: g for k, gd, g in self.selected if g and k in self.own_selected}
        _log_to_file("[BREADCRUMB] own_games rebuilt, starting prefix init")

        # ── Create prefixes + install deps from GE-Proton default_pfx ─────
        # Every selected game gets its prefix preloaded — no exceptions.
        # Own games use their CRC-based prefix (set by create_own_shortcuts).
        # Steam games use their Steam appid prefix.
        # LCD Plutonium games still get a prefix for offline mode; HGL
        # manages its own prefix separately for online mode.
        # ensure_all_prefix_deps handles deduplication and skips prefixes
        # that are already initialized, so passing everything in is safe.
        self._s.progress.emit(30, "Creating Proton prefixes...")
        self._s.log.emit("Creating Proton prefixes and installing dependencies...")
        self._s.pulse_start.emit("Installing prefix dependencies")
        from ge_proton import ensure_all_prefix_deps
        from detect_games import GAMES as _GAMES_MAP
        from wrapper import find_compatdata
        dep_targets = []
        for key, gd, game in self.selected:
            if not game:
                continue
            if key in self.own_selected:
                # Own games always use their CRC-based prefix
                compat = game.get("compatdata_path", "")
            else:
                # Steam games use the per-key appid, not card-level gd["appid"].
                # Card-level appid is wrong for keys like t6zm (212910 vs 202990).
                appid = _GAMES_MAP[key]["appid"] if key in _GAMES_MAP else gd["appid"]
                compat = find_compatdata(self.steam_root, appid,
                                         game_install_dir=game.get("install_dir"))
                if not compat and game.get("install_dir"):
                    steamapps = os.path.dirname(os.path.dirname(game["install_dir"]))
                    compat = os.path.join(steamapps, "compatdata", str(appid))
            if compat:
                dep_targets.append((key, compat))
        if dep_targets:
            _log_to_file(f"[BREADCRUMB] calling ensure_all_prefix_deps with {len(dep_targets)} targets: {[k for k,_ in dep_targets]}")
            done = ensure_all_prefix_deps(
                ge_version, dep_targets,
                on_progress=lambda msg: self._s.log.emit(msg),
                proton_path=proton,
                steam_root=self.steam_root,
            )
            self._s.log.emit(f"✓  Prefix dependencies: {done}/{len(dep_targets)} ready")
        self._s.pulse_stop.emit()
        _log_to_file("[BREADCRUMB] prefix deps done")

        # ── Plutonium games ───────────────────────────────────────────────
        if has_plut:
            # Create the launcher shortcut FIRST so the appid/prefix exist
            # before per-game installs mirror configs into it.
            try:
                from shortcut import create_launcher_shortcut
                create_launcher_shortcut(
                    on_progress=lambda m: self._s.log.emit(m)
                )
            except Exception as ex:
                self._s.log.emit(f"  Launcher shortcut failed: {ex}")

            # Preheat the offline launcher prefix with GE-Proton's full
            # dependency set (d3dx9, d3dcompiler, vcrun, xact, etc.).
            # The launcher prefix is a non-Steam shortcut — Steam/Proton
            # never initializes it automatically, so it misses the DLLs
            # that per-game prefixes get on first launch.
            try:
                from shortcut import get_launcher_appid
                from ge_proton import ensure_prefix_deps
                launcher_appid = get_launcher_appid()
                launcher_compat = os.path.join(
                    os.path.expanduser("~/.local/share/Steam"),
                    "steamapps", "compatdata", str(launcher_appid),
                )
                ensure_prefix_deps(
                    ge_version, launcher_compat,
                    on_progress=lambda msg: self._s.log.emit(msg),
                    proton_path=proton,
                    steam_root=self.steam_root,
                )
                self._s.log.emit("✓  Offline launcher prefix ready")
            except Exception as ex:
                self._s.log.emit(f"  Launcher prefix deps skipped: {ex}")

            # LCD: also prepare Heroic's shared prefix. Heroic initializes
            # it during Plutonium login, but may not include the full d3dx9
            # set needed for all games. ensure_prefix_deps only copies
            # missing DLLs so it won't overwrite Heroic's own files.
            if cfg.is_lcd():
                try:
                    from ge_proton import ensure_prefix_deps as _epd
                    from plutonium_lcd import HEROIC_DEFAULT_WINE_PREFIX
                    if os.path.isdir(HEROIC_DEFAULT_WINE_PREFIX):
                        _epd(
                            ge_version, HEROIC_DEFAULT_WINE_PREFIX,
                            on_progress=lambda msg: self._s.log.emit(msg),
                            proton_path=proton,
                            steam_root=self.steam_root,
                        )
                        self._s.log.emit("✓  Heroic shared prefix ready")
                except Exception as ex:
                    self._s.log.emit(f"  Heroic prefix deps skipped: {ex}")

            # Per-game Plutonium install: copy Plutonium into each prefix,
            # write config.json with game paths. Own games skip the wrapper
            # (shortcuts point at Plutonium directly). Steam games in the
            # mixed flow get the full wrapper treatment.
            plut_selected = [(k, gd, g) for k, gd, g in self.selected
                             if KEY_CLIENT.get(k) == "plutonium"]
            installed_for_plut = {k: g for k, gd, g in self.selected if g}
            total_plut = len(plut_selected)
            for idx, (key, gd, game) in enumerate(plut_selected):
                bp = 40 + int(idx / max(total_plut, 1) * 12)
                base_name = gd["base"]
                if base_name not in logged_bases:
                    self._s.progress.emit(bp, f"Setting up {base_name}...")
                def op_plut(pct, msg, _b=bp): self._s.progress.emit(_b + int(pct / 100 * 6), msg)
                try:
                    source = "own" if key in self.own_selected else "steam"
                    if source == "own":
                        compat = game.get("compatdata_path", "")
                    else:
                        _plut_appid = _PLUT_META[key][0] if key in _PLUT_META else gd["appid"]
                        compat = find_compatdata(self.steam_root, _plut_appid,
                                                  game_install_dir=game.get("install_dir"))
                    wp = install_plutonium(game, key, self.steam_root, proton, compat,
                                     on_progress=op_plut,
                                     installed_games=installed_for_plut,
                                     source=source)
                    # plutonium installer (plutonium_oled.py / plutonium_lcd.py)
                    # owns its own mark_game_setup call so lan_wrapper_path
                    # and other install-side metadata are preserved. wp is
                    # discarded here -- the installer already persisted it.
                    if base_name not in logged_bases:
                        self._s.log.emit(f"✓  {base_name} done")
                        logged_bases.add(base_name)
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        # ── T6SP-MOD (BO2 Singleplayer) ──────────────────────────────────
        _log_to_file("[BREADCRUMB] starting t6sp_mod install phase")
        if has_t6sp_mod:
            for key, gd, game in [(k, gd, g) for k, gd, g in self.selected if KEY_CLIENT.get(k) == "t6sp_mod"]:
                base_name = gd["base"]
                self._s.progress.emit(52, f"Installing Rattpak's T6SP-MOD (Beta)...")
                def op_t6sp(pct, msg): self._s.progress.emit(52 + int(pct / 100 * 4), msg)
                try:
                    source = "own" if key in self.own_selected else "steam"
                    if source == "own":
                        compat = game.get("compatdata_path", "")
                    else:
                        compat = find_compatdata(self.steam_root, gd["appid"],
                                                  game_install_dir=game.get("install_dir"))
                    install_t6sp_mod(game, self.steam_root, proton, compat, op_t6sp, source=source)
                    cfg.mark_game_setup(key, "t6sp_mod", source=source)
                    self._s.log.emit(f"✓  {base_name} (T6SP-MOD) done")
                    logged_bases.add(base_name)
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        # ── Install iw4x ─────────────────────────────────────────────────
        _log_to_file("[BREADCRUMB] starting iw4x install phase")
        has_iw4x = any(KEY_CLIENT.get(k) == "iw4x" for k in selected_keys)
        if has_iw4x:
            for key, gd, game in [(k, gd, g) for k, gd, g in self.selected if KEY_CLIENT.get(k) == "iw4x"]:
                base_name = gd["base"]
                self._s.progress.emit(56, f"Setting up {base_name}...")
                def op_iw4x(pct, msg): self._s.progress.emit(56 + int(pct / 100 * 7), msg)
                try:
                    source = "own" if key in self.own_selected else "steam"
                    if source == "own":
                        compat = game.get("compatdata_path", "")
                    else:
                        compat = find_compatdata(self.steam_root, gd["appid"],
                                                  game_install_dir=game.get("install_dir"))
                    install_iw4x(game, self.steam_root, proton, compat, op_iw4x, source=source,
                                 install_dlc=getattr(self, 'install_iw4x_dlc', False))
                    cfg.mark_game_setup(key, "iw4x", source=source)
                    self._s.log.emit(f"✓  {base_name} done")
                    logged_bases.add(base_name)
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        # ── Install CoD4 (iw3sp + cod4x) ─────────────────────────────────
        _log_to_file("[BREADCRUMB] starting cod4 install phase")
        if has_cod4:
            cod4_selected = [(k, gd, g) for k, gd, g in self.selected if KEY_CLIENT.get(k) in ("cod4x", "iw3sp")]
            for key, gd, game in cod4_selected:
                base_name = gd["base"]
                self._s.progress.emit(63, f"Setting up {base_name}...")
                def op_cod4(pct, msg): self._s.progress.emit(63 + int(pct / 100 * 7), msg)
                try:
                    source = "own" if key in self.own_selected else "steam"
                    c = KEY_CLIENT.get(key, gd["client"])
                    if source == "own":
                        compat = game.get("compatdata_path", "")
                        cod4x_appid = game.get("shortcut_appid", 7940)
                    else:
                        compat = find_compatdata(self.steam_root, gd["appid"],
                                                  game_install_dir=game.get("install_dir"))
                        cod4x_appid = gd["appid"]
                    if c == "cod4x":
                        install_cod4x(game, self.steam_root, proton, compat, op_cod4,
                                      appid=cod4x_appid)
                    elif c == "iw3sp":
                        install_iw3sp(game, self.steam_root, proton, compat, op_cod4, source=source)
                    cfg.mark_game_setup(key, c, source=source)
                    if base_name not in logged_bases:
                        self._s.log.emit(f"✓  {base_name} done")
                        logged_bases.add(base_name)
                except DownloadError as dl_ex:
                    self._s.log.emit(f"⚠  {dl_ex.label} download failed — manual download needed")
                    self._manual_dl_event.clear()
                    self._manual_dl_ok = False
                    self._s.manual_dl.emit(
                        dl_ex.url,
                        os.path.dirname(dl_ex.dest),
                        os.path.basename(dl_ex.dest),
                        dl_ex.label,
                    )
                    self._manual_dl_event.wait()
                    if not self._manual_dl_ok:
                        self._s.log.emit(f"  ✗  {base_name} skipped by user.")
                    else:
                        self._s.log.emit(f"  ✓  {dl_ex.label} placed manually — re-run install to finish setup")
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        # ── Install T7X (BO3 AlterWare client) ─────────────────────────
        # Must run BEFORE CleanOps — CleanOps drops d3d11.dll into the
        # stock BO3 dir, and the symlink farm would pick it up if it
        # already exists. Running T7x first builds symlinks from a clean
        # stock dir, then CleanOps only touches the stock dir afterward.
        _log_to_file("[BREADCRUMB] starting t7x install phase")
        if has_t7x:
            for key, gd, game in [(k, gd, g) for k, gd, g in self.selected if KEY_CLIENT.get(k) == "t7x"]:
                base_name = gd["base"]
                self._s.progress.emit(70, f"Setting up T7x...")
                def op_t7x(pct, msg): self._s.progress.emit(70 + int(pct / 100 * 2), msg)
                try:
                    source = "own" if key in self.own_selected else "steam"
                    t7x_dir = install_t7x(game, on_progress=op_t7x)
                    game["install_dir"] = t7x_dir
                    cfg.mark_game_setup(key, "t7x", source=source)
                    self._s.log.emit(f"✓  {base_name} (T7x) done")
                    logged_bases.add(base_name)
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} (T7x) failed: {ex}")

        # ── Install CleanOps (BO3) ────────────────────────────────────────
        _log_to_file("[BREADCRUMB] starting cleanops install phase")
        if has_cleanops:
            for key, gd, game in [(k, gd, g) for k, gd, g in self.selected if KEY_CLIENT.get(k) == "cleanops"]:
                base_name = gd["base"]
                self._s.progress.emit(72, f"Setting up {base_name}...")
                def op_cleanops(pct, msg): self._s.progress.emit(72 + int(pct / 100 * 4), msg)
                try:
                    source = "own" if key in self.own_selected else "steam"
                    if source == "own":
                        compat = game.get("compatdata_path", "")
                    else:
                        compat = find_compatdata(self.steam_root, gd["appid"],
                                                  game_install_dir=game.get("install_dir"))
                    install_cleanops(game, self.steam_root, proton, compat, op_cleanops, source=source)
                    cfg.mark_game_setup(key, "cleanops", source=source)
                    self._s.log.emit(f"✓  {base_name} done")
                    logged_bases.add(base_name)
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        # ── Install AlterWare (Ghosts / Advanced Warfare) ─────────────────
        _log_to_file("[BREADCRUMB] starting alterware install phase")
        has_alterware = any(KEY_CLIENT.get(k) == "alterware" for k in selected_keys)
        if has_alterware:
            from alterware import install_alterware
            for key, gd, game in [(k, gd, g) for k, gd, g in self.selected if KEY_CLIENT.get(k) == "alterware"]:
                base_name = gd["base"]
                self._s.progress.emit(76, f"Setting up {base_name}...")
                def op_alterware(pct, msg): self._s.progress.emit(76 + int(pct / 100 * 4), msg)
                try:
                    source = "own" if key in self.own_selected else "steam"
                    _appid = _GAMES_MAP[key]["appid"] if key in _GAMES_MAP else gd["appid"]
                    _install_dir = game.get("install_dir")
                    if source == "own":
                        compat = game.get("compatdata_path", "")
                        if not compat:
                            compat = find_compatdata(self.steam_root, _appid,
                                                      game_install_dir=_install_dir)
                    else:
                        compat = find_compatdata(self.steam_root, _appid,
                                                  game_install_dir=_install_dir)
                    if not compat and _install_dir:
                        steamapps = os.path.dirname(os.path.dirname(_install_dir))
                        compat = os.path.join(steamapps, "compatdata", str(_appid))
                    install_alterware(game, key, self.steam_root, proton, compat, op_alterware,
                                     source=source)
                    cfg.mark_game_setup(key, "alterware", source=source)
                    self._s.log.emit(f"✓  {base_name} done")
                    logged_bases.add(base_name)
                except Exception as ex:
                    self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        # ── Mark vanilla games ────────────────────────────────────────────
        for key, gd, game in self.selected:
            c = KEY_CLIENT.get(key, "")
            source = "own" if key in self.own_selected else "steam"
            if c == "steam" and not cfg.is_game_setup_for_source(key, source):
                cfg.mark_game_setup(key, "steam", source=source)
                self._s.log.emit(f"✓  {gd['base']} ({key}) ready")

        # ── Game display configs ──────────────────────────────────────────
        self._s.progress.emit(78, "Applying game configs...")
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
        except Exception as ex:
            self._s.log.emit(f"  Game configs skipped: {ex}")

        # ── Controller templates ──────────────────────────────────────────
        self._s.progress.emit(88, "Installing controller templates...")
        try:
            from controller_profiles import install_controller_templates, assign_controller_profiles, assign_external_controller_profiles
            install_controller_templates(
                on_progress=lambda msg: self._s.log.emit(f"  {msg}")
            )
            gyro_mode = cfg.get_gyro_mode() or "on"
            # Neptune profiles always assigned - user may play handheld too
            assign_controller_profiles(
                gyro_mode,
                on_progress=lambda msg: self._s.log.emit(f"  {msg}")
            )
            self._s.log.emit(f"✓  Neptune controller profiles assigned ({gyro_mode} mode)")
            # Docked users also get external controller profiles
            if cfg.is_docked():
                controller_type = cfg.get_external_controller() or "playstation"
                assign_external_controller_profiles(
                    controller_type,
                    gyro_mode,
                    on_progress=lambda msg: self._s.log.emit(f"  {msg}")
                )
                self._s.log.emit(f"✓  External controller profiles assigned ({controller_type})")
        except Exception as ex:
            self._s.log.emit(f"  Templates skipped: {ex}")

        try:
            from wrapper import set_steam_input_enabled
            set_steam_input_enabled(self.steam_root)
            self._s.log.emit("✓  Steam Input enabled for all games")
        except Exception as ex:
            self._s.log.emit(f"  Steam Input setup skipped: {ex}")

        # ── Write own game shortcuts (VDF, artwork, controllers, compat) ──
        # All mod client exes now exist on disk. write_own_shortcuts reads
        # the enrichment data set by enrich_own_games() earlier and writes
        # the actual VDF entries, downloads artwork, assigns controller
        # configs, and sets GE-Proton compat tool per shortcut.
        if self.own_selected:
            self._s.progress.emit(88, "Writing own game shortcuts...")
            try:
                write_own_shortcuts(
                    own_games=own_games,
                    selected_keys=[k for k in self.own_selected],
                    gyro_mode=gyro_mode,
                    on_progress=lambda msg: self._s.log.emit(msg),
                )
            except Exception as ex:
                self._s.log.emit(f"  Own shortcuts failed: {ex}")

        # ── Non-Steam shortcuts for Steam games (mixed flow) ─────────────
        # Steam games also need their non-Steam shortcuts (e.g. WaW MP,
        # CoD4 MP) created via create_shortcuts(). Without this, Steam games
        # in the mixed flow don't get their mod client shortcuts.
        if self.steam_selected:
            try:
                from shortcut import create_shortcuts
                steam_installed = {k: g for k, gd, g in self.steam_selected if g}
                steam_keys = [k for k, _, _ in self.steam_selected]
                create_shortcuts(
                    installed_games=steam_installed,
                    selected_keys=steam_keys,
                    gyro_mode=gyro_mode,
                    on_progress=lambda msg: self._s.log.emit(msg),
                    steam_root=self.steam_root,
                )
            except Exception as ex:
                self._s.log.emit(f"  Steam shortcuts skipped: {ex}")

            # Set default launch option so Steam Deck skips the mode picker
            has_cod4_steam = any(KEY_CLIENT.get(k) in ("cod4x", "iw3sp")
                                for k, _, _ in self.steam_selected)
            has_waw_steam = any(k in ("t4sp", "t4mp")
                               for k, _, _ in self.steam_selected)
            defaults = {}
            if has_cod4_steam:
                defaults["7940"] = ("7a722f97", "1")   # CoD4 -> Singleplayer
            if has_waw_steam:
                defaults["10090"] = ("9aa5e05f", "0")   # WaW -> Campaign
            if defaults:
                try:
                    from wrapper import set_default_launch_option
                    set_default_launch_option(self.steam_root, defaults)
                    self._s.log.emit("✓  Default launch options set (SP mode)")
                except Exception as ex:
                    self._s.log.emit(f"  Launch options skipped: {ex}")

        # ── Steam artwork for Steam-sourced games ─────────────────────────
        if self.steam_selected:
            self._s.progress.emit(95, "Applying Steam artwork...")
            try:
                from shortcut import apply_steam_artwork
                steam_keys = [k for k, _, _ in self.steam_selected]
                apply_steam_artwork(
                    selected_keys=steam_keys,
                    on_progress=lambda msg: self._s.log.emit(msg)
                )
            except Exception as ex:
                self._s.log.emit(f"  Steam artwork skipped: {ex}")

        # ── Done ──────────────────────────────────────────────────────────
        _log_to_file("[BREADCRUMB] all phases complete, finishing up")
        cfg.complete_first_run(self.steam_root)
        self._s.progress.emit(100, "All done!")
        self._s.done.emit(True)


# ── OwnScanScreen ────────────────────────────────────────────────────────────
class OwnScanScreen(QWidget):
    """
    Shown in the advanced flow before WelcomeScreen. Scans for non-Steam
    games (CD, GOG, MS Store, etc.) in default and user-chosen folders.
    """
    def __init__(self, stack):
        super().__init__(); self.stack = stack; self.screen_name = "OwnScanScreen"
        self._own_found = {}
        self._checks = {}
        self._extra_paths = []

        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        hdr = QWidget(); hdr.setFixedHeight(60)
        hdr.setStyleSheet(f"background:{C_CARD};")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(20,0,20,0)
        _ht = QLabel("DECKOPS"); _ht.setFont(font(22, display=True))
        _ht.setStyleSheet("color:#FFF;background:transparent;"); hl.addWidget(_ht)
        _nb = QLabel("NIGHTLY"); _nb.setFont(font(9, bold=True))
        _nb.setStyleSheet(
            "color:#F47B20;background:#2A1A08;border:1px solid #F47B20;"
            "border-radius:4px;padding:1px 6px;"
        )
        hl.addWidget(_nb); hl.addStretch()
        lay.addWidget(hdr)

        content = QWidget()
        clay = QVBoxLayout(content); clay.setContentsMargins(60,20,60,40); clay.setSpacing(14)
        clay.addWidget(_lbl("NON-STEAM GAMES", 14, C_TREY, align=Qt.AlignCenter))
        clay.addWidget(_lbl(
            "Scanning for games installed outside Steam. "
            "You can also choose a custom folder below.",
            13, C_DIM))

        self.status = _lbl("Scanning...", 14, C_DIM)
        clay.addWidget(self.status)
        self.bar = QProgressBar(); self.bar.setMaximum(100); self.bar.setTextVisible(False)
        self.bar.setFixedHeight(14)
        bw = QHBoxLayout(); bw.addStretch(); bw.addWidget(self.bar, 6); bw.addStretch()
        clay.addLayout(bw)

        # Scrollable list of found games
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_widget)
        clay.addWidget(scroll, stretch=1)

        self._no_games_msg = _lbl(
            "No supported games found in the default locations.\n"
            "Use \"Choose Folder\" to pick where your games are installed.",
            13, C_TREY, align=Qt.AlignCenter)
        self._no_games_msg.setVisible(False)
        clay.addWidget(self._no_games_msg)

        # Button row — matches SetupScreen pattern
        self.warning = _lbl("", 12, C_TREY, align=Qt.AlignLeft)
        self.warning.setVisible(False); clay.addWidget(self.warning)
        btn_row = QHBoxLayout(); btn_row.setSpacing(16)

        back = _btn("<< Back", C_DARK_BTN, h=52); back.setFixedWidth(180)
        back.clicked.connect(lambda: go_to(self.stack, "SetupFlowScreen"))

        self._folder_btn = _btn("Choose Folder", C_DARK_BTN, h=52)
        self._folder_btn.setFixedWidth(200)
        self._folder_btn.clicked.connect(self._pick_folder)

        self._skip_btn = _btn("Skip >>", C_DARK_BTN, h=52)
        self._skip_btn.setFixedWidth(140)
        self._skip_btn.setVisible(False)
        self._skip_btn.clicked.connect(self._skip)

        self._cont_btn = _btn("Continue >>", C_IW, h=52)
        self._cont_btn.setVisible(False)
        self._cont_btn.clicked.connect(self._continue)

        btn_row.addWidget(back)
        btn_row.addWidget(self._folder_btn)
        btn_row.addWidget(self._skip_btn)
        btn_row.addWidget(self._cont_btn, stretch=1)
        clay.addLayout(btn_row)
        lay.addWidget(content, stretch=1)

    def showEvent(self, e):
        super().showEvent(e)
        self._own_found.clear()
        self._checks.clear()
        self._extra_paths.clear()
        self._no_games_msg.setVisible(False)
        self._skip_btn.setVisible(False)
        self._cont_btn.setVisible(False)
        self.bar.setValue(0)
        self.status.setText("Scanning for non-Steam games...")
        # Clear previous game rows
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        QTimer.singleShot(200, self._scan)

    def _scan(self):
        self.bar.setValue(30)
        self.status.setText("Scanning game folders...")
        self._s = _Sigs()
        self._s.progress.connect(lambda p, m: (self.bar.setValue(p), self.status.setText(m)))
        self._s.done.connect(lambda _: self._show_results())
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        from detect_games import find_own_installed
        results = find_own_installed(
            extra_paths=self._extra_paths if self._extra_paths else None,
            on_progress=lambda msg: self._s.progress.emit(60, msg),
        )
        self._own_found = results
        self._s.progress.emit(100, "Scan complete.")
        self._s.done.emit(True)

    def _show_results(self):
        self.bar.setValue(100)
        self._checks.clear()

        # Clear previous game rows (keep the trailing stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._own_found:
            self.status.setText("No supported games found.")
            self.status.setStyleSheet(f"color:{C_TREY};background:transparent;")
            self._no_games_msg.setVisible(True)
            self._skip_btn.setVisible(True)
            self._cont_btn.setVisible(False)
            return

        self._no_games_msg.setVisible(False)
        self._skip_btn.setVisible(False)
        count = len(self._own_found)
        self.status.setText(f"Found {count} game(s)!")
        self.status.setStyleSheet(f"color:{C_IW};background:transparent;")

        # Build game rows sorted by order — matches SetupScreen row style
        for key in sorted(self._own_found, key=lambda k: self._own_found[k].get("order", 99)):
            game = self._own_found[key]
            row = QHBoxLayout(); row.setSpacing(12); row.setContentsMargins(8, 8, 8, 8)

            cb = QCheckBox()
            cb.setChecked(True)
            cb.toggled.connect(self._update_continue)
            self._checks[key] = cb
            row.addWidget(cb)

            name_lbl = _lbl(game["name"], 14, "#FFF", align=Qt.AlignLeft, wrap=False)
            row.addWidget(name_lbl, stretch=1)

            path_lbl = _lbl(game["install_dir"], 10, C_DIM, align=Qt.AlignRight, wrap=False)
            row.addWidget(path_lbl)

            cw = QWidget(); cw.setLayout(row)
            self._list_layout.insertWidget(self._list_layout.count() - 1, cw)

        self._cont_btn.setVisible(True)

    def _update_continue(self):
        """Show Continue only if at least one game is checked."""
        any_checked = any(cb.isChecked() for cb in self._checks.values())
        self._cont_btn.setVisible(any_checked)
        if not any_checked:
            self._skip_btn.setVisible(True)
        else:
            self._skip_btn.setVisible(False)

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select your games folder", os.path.expanduser("~"),
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)
        if folder:
            if folder not in self._extra_paths:
                self._extra_paths.append(folder)
            # Re-scan with the new path included
            self.status.setText(f"Scanning {folder}...")
            self.bar.setValue(0)
            self._no_games_msg.setVisible(False)
            self._skip_btn.setVisible(False)
            self._cont_btn.setVisible(False)
            QTimer.singleShot(200, self._scan)

    def _skip(self):
        """Skip own games, go straight to Steam detection."""
        # Set a flag so WelcomeScreen knows to skip own scanning
        ws = get_screen(self.stack, "WelcomeScreen")
        ws._steam_only = True
        go_to(self.stack, "WelcomeScreen")

    def _continue(self):
        """Store selected own games on OwnInstallScreen and advance to WelcomeScreen."""
        selected = {}
        for key, cb in self._checks.items():
            if cb.isChecked() and key in self._own_found:
                selected[key] = self._own_found[key]
        # Park own games on OwnInstallScreen - SetupScreen will route there
        # after the user picks their Steam games
        own_screen = get_screen(self.stack, "OwnInstallScreen")
        own_screen.own_selected = selected
        # Advance to WelcomeScreen for Steam game detection
        ws = get_screen(self.stack, "WelcomeScreen")
        ws._steam_only = True
        go_to(self.stack, "WelcomeScreen")
