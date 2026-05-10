"""
ui_manage.py — Post-install management screens for DeckOps

Screens: ManagementCard, ManagementScreen, SetupCompleteScreen,
         ConfigureScreen, UpdateScreen
Extracted from ui_qt.py — all hardcoded stack indices replaced with named lookups.
"""

import os, subprocess, sys, shutil, stat, threading, json, urllib.request, urllib.error

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QPushButton, QCheckBox, QProgressBar, QPlainTextEdit,
    QFrame, QSizePolicy, QMessageBox, QLineEdit, QSlider,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QGraphicsOpacityEffect

from detect_games import find_steam_root, parse_library_folders, find_installed_games
import config as cfg

from ui_constants import (
    C_BG, C_CARD, C_IW, C_TREY, C_DIM, C_DARK_BTN, C_RED_BTN, C_BLUE_BTN,
    font, _btn, _lbl, _hdiv, _title_block, _log_to_file, _Sigs,
    _detached_open, _header_path, _ask_iw4x_dlc,
    ALL_GAMES, KEY_CLIENT, KEY_MODE_LABEL,
    _active_keys, _active_client, _active_appid,
    SP_IMAGE_URLS, IMG_RATIO, CARD_COLS, CARD_MAX_W,
    HEROES_DIR, PROJECT_ROOT,
    _music_volume, _music_enabled,
    _set_audio_volume, _set_audio_enabled, _start_audio, _kill_audio,
    go_to, get_screen,
)

from identity import GITHUB_USER, GITHUB_REPO
from log import get_logger

_log = get_logger(__name__)


# ── ManagementCard ────────────────────────────────────────────────────────────
class ManagementCard(QFrame):
    def __init__(self, gd, installed, on_setup, on_configure,
                 on_readd=None, parent=None):
        super().__init__(parent)
        color = C_IW if gd["dev"] == "iw" else C_TREY
        self._color  = color
        self._appid  = _active_appid(gd)
        self._is_lan = gd.get("client") == "lan"
        self.setObjectName("MC")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setMaximumWidth(CARD_MAX_W)

        keys       = _active_keys(gd)
        client     = _active_client(gd)

        if self._is_lan:
            # DeckOps LAN card — always shown, no key-based detection
            ik         = []
            is_setup   = False
            is_present = True
        else:
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

        # ── Image container with overlaid badge and buttons ───────────────
        img_container = QWidget()
        img_container.setStyleSheet("background:#0A0A10;border:none;")
        img_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._img = QLabel(img_container)
        self._img.setAlignment(Qt.AlignCenter)
        self._img.setStyleSheet("background:transparent;border:none;")
        if not is_setup and not self._is_lan:
            effect = QGraphicsOpacityEffect()
            effect.setOpacity(0.45 if is_present else 0.25)
            self._img.setGraphicsEffect(effect)

        # Client badge — overlaid top-left on the image
        self._client_badge = QPushButton(client.upper(), img_container)
        self._client_badge.setFont(font(8, True)); self._client_badge.setEnabled(False)
        self._client_badge.setStyleSheet(
            f"QPushButton{{background:{color};color:#FFF;border:none;border-radius:3px;padding:2px 6px;}}"
            f"QPushButton:disabled{{background:{color};color:#FFF;}}"
        )
        self._client_badge.adjustSize()
        self._client_badge.raise_()

        # Buttons — overlaid bottom-center on the image
        self._btn_bar = QWidget(img_container)
        self._btn_bar.setStyleSheet("background:transparent;border:none;")
        bb = QHBoxLayout(self._btn_bar)
        bb.setContentsMargins(6, 0, 6, 0); bb.setSpacing(4)

        if self._is_lan:
            readd_btn = _btn("Re-Add", C_TREY, size=9, h=26)
            if on_readd:
                readd_btn.clicked.connect(lambda: on_readd(gd))
            readd_btn.setStyleSheet(
                f"QPushButton{{background:{C_TREY};color:#FFF;border:none;"
                f"border-radius:4px;font-weight:bold;padding:0 10px;}}"
            )
            bb.addStretch(); bb.addWidget(readd_btn); bb.addStretch()
        elif not is_setup and is_present:
            setup_btn = _btn("Set Up", C_IW, size=9, h=26)
            setup_btn.clicked.connect(lambda: on_setup(gd))
            setup_btn.setStyleSheet(
                f"QPushButton{{background:{C_IW};color:#FFF;border:none;"
                f"border-radius:4px;font-weight:bold;padding:0 10px;}}"
            )
            bb.addStretch(); bb.addWidget(setup_btn); bb.addStretch()
        elif is_setup:
            cfg_btn = _btn("Configure", C_DARK_BTN, size=9, h=26)
            cfg_btn.clicked.connect(lambda: on_configure(gd, ik))
            cfg_btn.setStyleSheet(
                f"QPushButton{{background:rgba(51,51,63,200);color:#CCC;border:none;"
                f"border-radius:4px;font-weight:bold;padding:0 10px;}}"
            )
            bb.addStretch(); bb.addWidget(cfg_btn); bb.addStretch()
        else:
            setup_btn = _btn("Set Up", C_DARK_BTN, size=9, h=26)
            setup_btn.setEnabled(False)
            setup_btn.setStyleSheet(
                f"QPushButton{{background:rgba(37,37,53,200);color:#555568;border:none;"
                f"border-radius:4px;font-weight:bold;padding:0 10px;}}"
                f"QPushButton:disabled{{background:rgba(37,37,53,200);color:#555568;}}"
            )
            bb.addStretch(); bb.addWidget(setup_btn); bb.addStretch()

        self._btn_bar.adjustSize()
        self._btn_bar.raise_()

        self._img_container = img_container
        lay.addWidget(img_container)
        self._raw_pixmap = None

        if self._is_lan:
            local_img = os.path.join(HEROES_DIR, "deckops_grid.png")
            if os.path.exists(local_img):
                self._raw_pixmap = QPixmap(local_img)
        else:
            cached = _header_path(self._appid)
            if os.path.exists(cached):
                self._raw_pixmap = QPixmap(cached)
            else:
                threading.Thread(target=self._fetch, args=(self._appid,), daemon=True).start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._scale_image()

    def _scale_image(self):
        w = self.width()
        h = int(w * IMG_RATIO)
        self._img_container.setFixedSize(w, h)
        self._img.setFixedSize(w, h)
        if self._raw_pixmap:
            self._img.setPixmap(
                self._raw_pixmap.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            )
        # Position client badge — top-left with 4px margin
        self._client_badge.move(4, 4)
        # Position button bar — bottom, full width
        self._btn_bar.setFixedWidth(w)
        bh = self._btn_bar.sizeHint().height()
        self._btn_bar.move(0, h - bh - 4)

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
            _log.debug("image load failed", exc_info=True)


# ── ManagementScreen ──────────────────────────────────────────────────────────
class ManagementScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.installed={}; self.screen_name = "ManagementScreen"
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

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
        guide_btn = _btn("📋  Guide", C_BLUE_BTN, size=10, h=36); guide_btn.setFixedWidth(90)
        guide_btn.clicked.connect(lambda: go_to(self.stack, "SetupCompleteScreen"))
        hl.addWidget(guide_btn)
        hl.addSpacing(8)
        cfg_btn = _btn("⚙  Settings", C_DARK_BTN, size=11, h=36); cfg_btn.setFixedWidth(120)
        cfg_btn.clicked.connect(lambda: go_to(self.stack, "ConfigureScreen"))
        hl.addWidget(cfg_btn)
        lay.addWidget(hdr)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget(); self._grid = QGridLayout(inner)
        self._grid.setContentsMargins(16,16,16,16); self._grid.setSpacing(12)
        self._grid.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
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
        merged = find_installed_games(parse_library_folders(root))
        # Merge own games so cards show regardless of install source
        if cfg.get_game_source() == "own":
            from detect_games import find_own_installed
            own = find_own_installed()
            # Own games take priority only for keys not already in Steam
            for k, v in own.items():
                if k not in merged:
                    merged[k] = v
        self.installed = merged
        self._rebuild()

    def _rebuild(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        games = [g for g in ALL_GAMES
                 if _active_keys(g) or g.get("client") == "lan"]

        for idx, gd in enumerate(games):
            row = idx // CARD_COLS
            col = idx  % CARD_COLS
            card = ManagementCard(
                gd, self.installed,
                on_setup     = self._setup,
                on_configure = self._configure,
                on_readd     = self._readd,
            )
            self._grid.addWidget(card, row, col)

        total = len(games)
        remainder = total % CARD_COLS
        if remainder:
            for col in range(remainder, CARD_COLS):
                self._grid.addWidget(QWidget(), total // CARD_COLS, col)

    def _readd(self, gd):
        """Re-add the Plutonium offline launcher shortcut."""
        from shortcut import create_launcher_shortcut
        self._status.setText("Re-adding Plutonium offline launcher...")

        def _on_progress(msg):
            self._status.setText(msg)

        def _run():
            create_launcher_shortcut(on_progress=_on_progress)
            QTimer.singleShot(0, lambda: self._status.setText(
                "Plutonium offline launcher shortcut re-added."
            ))

        threading.Thread(target=_run, daemon=True).start()

    def _setup(self, gd):
        """Route a single card's keys through the install flow."""
        root = find_steam_root()
        keys = _active_keys(gd)
        # Find which keys are present in the merged installed dict
        present_keys = [k for k in keys if k in self.installed]
        if not present_keys:
            self._status.setText("Game files not found.")
            return

        source = cfg.get_game_source() or "steam"

        # Build selected tuples for the install screen
        selected = [(k, gd, self.installed[k]) for k in present_keys]

        if source == "own":
            # Determine which are own vs Steam
            own_selected = {}
            steam_selected = []
            for k, g_gd, game in selected:
                if game.get("source") == "own":
                    own_selected[k] = game
                else:
                    steam_selected.append((k, g_gd, game))

            s = get_screen(self.stack, "OwnInstallScreen")
            s.own_selected = own_selected
            s.steam_selected = steam_selected
            s.steam_root = root
            s._return_to_management = True
            s.install_iw4x_dlc = _ask_iw4x_dlc(self, selected)
            go_to(self.stack, "OwnInstallScreen")
        else:
            # Standard Steam flow
            s = get_screen(self.stack, "InstallScreen")
            s.selected = selected
            s.steam_root = root
            s._return_to_management = True
            s.install_iw4x_dlc = _ask_iw4x_dlc(self, selected)
            go_to(self.stack, "InstallScreen")

    def _configure(self, gd, installed_keys):
        """Show configure dialog with Mods, Update, and Reinstall options."""
        _MOD_CLIENTS = ("cod4x", "iw4x", "plutonium", "alterware", "t7x")
        has_mods_support = any(KEY_CLIENT.get(k, "") in _MOD_CLIENTS for k in installed_keys)
        has_mod_client = any(KEY_CLIENT.get(k, "") not in ("steam", "") for k in installed_keys)

        msg = QMessageBox(self)
        msg.setWindowTitle(gd["base"])
        msg.setText("What would you like to do?")

        mods_btn = None
        if has_mods_support:
            mods_btn = msg.addButton("Mods", QMessageBox.AcceptRole)
        upd_btn = None
        if has_mod_client:
            upd_btn = msg.addButton("Update", QMessageBox.AcceptRole)
        rei_btn = msg.addButton("Reinstall", QMessageBox.AcceptRole)
        msg.addButton("Cancel", QMessageBox.RejectRole)
        msg.exec_()

        clicked = msg.clickedButton()
        if clicked == mods_btn:
            self._mods(gd, installed_keys)
        elif clicked == upd_btn:
            self._update(gd, installed_keys)
        elif clicked == rei_btn:
            self._reinstall(gd)

    def _update(self, gd, keys):
        """Route a single card's installed keys through the update flow."""
        root = find_steam_root()
        # Use the merged installed dict (already built in showEvent)
        selected = [(k, gd, self.installed.get(k, {})) for k in keys
                     if self.installed.get(k)]
        if not selected:
            self._status.setText("Game not found.")
            return
        s = get_screen(self.stack, "UpdateScreen")
        s.selected   = selected
        s.steam_root = root
        go_to(self.stack, "UpdateScreen")

    def _reinstall(self, gd):
        """Unmark game keys as set up, then route through the install flow."""
        keys = _active_keys(gd)
        cfg.unmark_game_setup(keys)
        self._status.setText(f"Cleared setup state for {gd['base']}. Running clean install...")
        # Route through the same path as "Set Up"
        self._setup(gd)

    def _mods(self, gd, installed_keys):
        """Open the mod folder for a game. Shows a chooser for games with
        both mods/ and usermaps/ directories (CoD4x, IW4x, T7X), for
        AlterWare games with data/scripts/mp and data/scripts/sp, or for
        OLED Plutonium games whose SP/MP modes live in separate prefixes."""

        # ── Plutonium storage name mapping ────────────────────────────────
        _PLUT_STORAGE = {
            "t4sp": "t4", "t4mp": "t4",
            "t5sp": "t5", "t5mp": "t5",
            "t6mp": "t6", "t6zm": "t6",
            "iw5mp": "iw5", "iw5mp_ds": "iw5",
        }

        # Appid per key — used to detect when keys on the same card
        # have separate Wine prefixes (different appids = different
        # mods/ folders on OLED).
        _PLUT_APPID = {
            "t4sp": 10090, "t4mp": 10090,
            "t5sp": 42700, "t5mp": 42710,
            "t6mp": 202990, "t6zm": 212910,
            "iw5mp": 42690, "iw5mp_ds": 42750,
        }

        # Friendly labels for the dialog buttons
        _PLUT_MODE_LABEL = {
            "t4sp": "Campaign / Zombies", "t4mp": "Multiplayer",
            "t5sp": "Campaign / Zombies", "t5mp": "Multiplayer",
            "t6zm": "Zombies",            "t6mp": "Multiplayer",
            "iw5mp": "Multiplayer",       "iw5mp_ds": "Dedicated Server",
        }

        def _open_folder(path):
            os.makedirs(path, exist_ok=True)
            _detached_open(["xdg-open", path])
            self._status.setText(f"Opened: {path}")

        def _resolve_plut_mods_dir(game_key):
            """Resolve the Plutonium mods/ folder for a game key."""
            storage_name = _PLUT_STORAGE.get(game_key)
            if not storage_name:
                return None

            if cfg.is_lcd():
                # LCD: single Heroic shared prefix for all games
                from plutonium_lcd import get_shared_plut_dir
                plut_dir = get_shared_plut_dir()
            else:
                # OLED: read plut_dir from per-game metadata
                game = self.installed.get(game_key, {})
                install_dir = game.get("install_dir", "")
                if install_dir:
                    meta_path = os.path.join(install_dir, "deckops_plutonium.json")
                    if os.path.exists(meta_path):
                        try:
                            import json
                            with open(meta_path) as f:
                                meta = json.load(f)
                            plut_dir = meta.get("plut_dir", "")
                        except Exception:
                            plut_dir = ""
                    else:
                        plut_dir = ""
                else:
                    plut_dir = ""

            if not plut_dir:
                return None
            return os.path.join(plut_dir, "storage", storage_name, "mods")

        # Determine which client we're dealing with from the installed keys
        client = None
        plut_keys = []
        alterware_keys = []
        for k in installed_keys:
            c = KEY_CLIENT.get(k, "")
            if c in ("cod4x", "iw4x"):
                client = c
                break
            elif c == "t7x":
                client = "t7x"
                break
            elif c == "alterware":
                client = "alterware"
                alterware_keys.append(k)
            elif c == "plutonium" and k in _PLUT_STORAGE:
                client = "plutonium"
                plut_keys.append(k)

        if not client:
            self._status.setText("No mod support for this game.")
            return

        if client in ("cod4x", "iw4x"):
            mod_key = installed_keys[0]
            game = self.installed.get(mod_key, {})
            install_dir = game.get("install_dir", "")
            if not install_dir:
                self._status.setText("Game install directory not found.")
                return
            # Two folders — ask user which one
            msg = QMessageBox(self)
            msg.setWindowTitle("Open Mod Folder")
            msg.setText(f"Which folder would you like to open for {gd['base']}?")
            mods_btn = msg.addButton("Mods", QMessageBox.AcceptRole)
            usermaps_btn = msg.addButton("User Maps", QMessageBox.AcceptRole)
            msg.addButton("Cancel", QMessageBox.RejectRole)
            msg.exec_()
            clicked = msg.clickedButton()
            if clicked == mods_btn:
                _open_folder(os.path.join(install_dir, "mods"))
            elif clicked == usermaps_btn:
                _open_folder(os.path.join(install_dir, "usermaps"))

        elif client == "t7x":
            from t7x import _get_sibling_dir
            mod_key = [k for k in installed_keys if KEY_CLIENT.get(k) == "t7x"]
            mod_key = mod_key[0] if mod_key else installed_keys[0]
            game = self.installed.get(mod_key, {})
            stock_dir = game.get("install_dir", "")
            if not stock_dir:
                self._status.setText("Game install directory not found.")
                return
            # T7X writes mods/usermaps into the DeckOps-T7X sibling dir,
            # not the stock BO3 install directory that detect_games returns.
            install_dir = _get_sibling_dir(stock_dir)
            if not os.path.isdir(install_dir):
                self._status.setText("T7X directory not found. Has T7X been installed?")
                return
            # Two folders — ask user which one
            msg = QMessageBox(self)
            msg.setWindowTitle("Open Mod Folder")
            msg.setText(f"Which folder would you like to open for {gd['base']} (T7x)?")
            mods_btn = msg.addButton("Mods", QMessageBox.AcceptRole)
            usermaps_btn = msg.addButton("User Maps", QMessageBox.AcceptRole)
            msg.addButton("Cancel", QMessageBox.RejectRole)
            msg.exec_()
            clicked = msg.clickedButton()
            if clicked == mods_btn:
                _open_folder(os.path.join(install_dir, "mods"))
            elif clicked == usermaps_btn:
                _open_folder(os.path.join(install_dir, "usermaps"))

        elif client == "alterware":
            if not alterware_keys:
                self._status.setText("No AlterWare mod keys found.")
                return
            mod_key = alterware_keys[0]
            game = self.installed.get(mod_key, {})
            install_dir = game.get("install_dir", "")
            if not install_dir:
                self._status.setText("Game install directory not found.")
                return

            # Determine which mode buttons to show based on installed keys
            has_mp = any(k.endswith("mp") for k in alterware_keys)
            has_sp = any(k.endswith("sp") for k in alterware_keys)

            if has_mp and has_sp:
                msg = QMessageBox(self)
                msg.setWindowTitle("Open Scripts Folder")
                msg.setText(f"Which scripts folder for {gd['base']}?")
                mp_btn = msg.addButton("MP Scripts", QMessageBox.AcceptRole)
                sp_btn = msg.addButton("SP Scripts", QMessageBox.AcceptRole)
                msg.addButton("Cancel", QMessageBox.RejectRole)
                msg.exec_()
                clicked = msg.clickedButton()
                if clicked == mp_btn:
                    _open_folder(os.path.join(install_dir, "data", "scripts", "mp"))
                elif clicked == sp_btn:
                    _open_folder(os.path.join(install_dir, "data", "scripts", "sp"))
            elif has_mp:
                _open_folder(os.path.join(install_dir, "data", "scripts", "mp"))
            elif has_sp:
                _open_folder(os.path.join(install_dir, "data", "scripts", "sp"))

        elif client == "plutonium":
            if not plut_keys:
                self._status.setText("No Plutonium mod keys found.")
                return

            # Check if multiple keys have different appids (OLED only).
            # If so, they have separate prefixes with separate mods/ folders.
            unique_appids = set(_PLUT_APPID.get(k) for k in plut_keys)
            need_chooser = not cfg.is_lcd() and len(unique_appids) > 1

            if need_chooser:
                msg = QMessageBox(self)
                msg.setWindowTitle("Open Mod Folder")
                msg.setText(f"Which mode's mods folder for {gd['base']}?")
                key_buttons = []
                for k in plut_keys:
                    label = _PLUT_MODE_LABEL.get(k, k)
                    btn = msg.addButton(label, QMessageBox.AcceptRole)
                    key_buttons.append((btn, k))
                msg.addButton("Cancel", QMessageBox.RejectRole)
                msg.exec_()
                clicked = msg.clickedButton()
                for btn, k in key_buttons:
                    if clicked == btn:
                        mods_path = _resolve_plut_mods_dir(k)
                        if mods_path:
                            _open_folder(mods_path)
                        else:
                            self._status.setText(f"Could not resolve mods folder for {k}.")
                        break
            else:
                # Single prefix or LCD — open directly
                mods_path = _resolve_plut_mods_dir(plut_keys[0])
                if mods_path:
                    _open_folder(mods_path)
                else:
                    self._status.setText("Could not resolve Plutonium mods folder.")


# ── SetupCompleteScreen ──────────────────────────────────────────────────────
class SetupCompleteScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack = stack; self.screen_name = "SetupCompleteScreen"
        lay = QVBoxLayout(self); lay.setContentsMargins(60,20,60,20); lay.setSpacing(0)

        t = QLabel("SETUP COMPLETE"); t.setFont(font(28, True)); t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("color:#FFF;background:transparent;"); lay.addWidget(t)
        lay.addWidget(_lbl(
            "Your games are configured with controller profiles, GE-Proton, "
            "and display settings. You're ready to play.",
            12, C_DIM))

        # ── Scrollable content area ───────────────────────────────────────────
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget()
        sl = QVBoxLayout(inner); sl.setContentsMargins(0,8,0,8); sl.setSpacing(6)

        # ── Cloud saves ───────────────────────────────────────────────────────
        sl.addWidget(_hdiv())
        sl.addWidget(_lbl("⚠  Steam Cloud Saves", 12, C_TREY, bold=True, align=Qt.AlignLeft))
        sl.addWidget(_lbl(
            "If Steam asks about cloud saves, choose Keep Local. "
            "If a game asks for Safe Mode, choose No.",
            11, C_DIM, align=Qt.AlignLeft))

        # ── MW1 / WaW shortcuts ───────────────────────────────────────────────
        sl.addWidget(_hdiv())
        sl.addWidget(_lbl("🎮  MW1 & WaW Multiplayer", 12, C_IW, bold=True, align=Qt.AlignLeft))
        sl.addWidget(_lbl(
            "MW1 and WaW have separate DeckOps multiplayer shortcuts in your "
            "Steam library. Use the main game entry for singleplayer and the "
            "DeckOps shortcut for multiplayer.\n\n"
            "MW1 Singleplayer: on first launch, select the \"Player\" profile. "
            "This is the profile DeckOps created with your display settings.",
            11, C_DIM, align=Qt.AlignLeft))

        # ── First launch ─────────────────────────────────────────────────────
        sl.addWidget(_hdiv())
        sl.addWidget(_lbl("⏳  First Launch", 12, "#5B9BD5", bold=True, align=Qt.AlignLeft))
        sl.addWidget(_lbl(
            "All games take longer to launch the first time. This is normal "
            "and they will be faster on subsequent launches.\n\n"
            "Plutonium games must be launched once before they can be used "
            "with the offline LAN launcher.",
            11, C_DIM, align=Qt.AlignLeft))

        # ── MW2 MP own-game first launch ──────────────────────────────────────
        self._mw2own_div = _hdiv()
        self._mw2own_hdr = _lbl("🎮  MW2 Multiplayer (Non-Steam)", 12, C_IW, bold=True, align=Qt.AlignLeft)
        self._mw2own_body = _lbl(
            "MW2 Multiplayer (IW4x) needs to be launched twice on initial "
            "installation. The first launch will fail, this is normal. "
            "Launch it again and it will work.",
            11, C_DIM, align=Qt.AlignLeft)
        sl.addWidget(self._mw2own_div)
        sl.addWidget(self._mw2own_hdr)
        sl.addWidget(self._mw2own_body)

        # ── BO3 first launch ─────────────────────────────────────────────────
        sl.addWidget(_hdiv())
        sl.addWidget(_lbl("🎮  Black Ops III: First Launch", 12, C_TREY, bold=True, align=Qt.AlignLeft))
        sl.addWidget(_lbl(
            "CleanOps and T7X finish installing on their first run. Do the "
            "first launch in Desktop Mode:\n\n"
            "1. If you installed T7X, launch it first, then close it.\n"
            "2. Launch Black Ops III (CleanOps). It will patch the game and "
            "may slow the Deck temporarily. It will not launch after "
            "patching. This is normal.\n"
            "3. Press the blue Stop button in Steam, then relaunch to "
            "verify it works.\n\n"
            "Skip step 1 if you only installed CleanOps.",
            11, C_DIM, align=Qt.AlignLeft))

        # ── LCD notes (LCD users only) ────────────────────────────────────────
        self._lcd_div = _hdiv()
        self._lcd_hdr = _lbl("⚠  LCD Steam Deck Notes", 12, C_TREY, bold=True, align=Qt.AlignLeft)
        self._lcd_body = _lbl(
            "Plutonium games on LCD may take a moment to launch while a "
            "shader cache cleanup runs. If a game does not start right "
            "away, be patient or try again.\n\n"
            "If Steam tries to compile Vulkan shaders before launching, "
            "skip it. These are not used by LCD Plutonium games.\n\n"
            "Quit games from the in-game menu rather than the Steam "
            "overlay for a faster exit.",
            11, C_DIM, align=Qt.AlignLeft)
        sl.addWidget(self._lcd_div)
        sl.addWidget(self._lcd_hdr)
        sl.addWidget(self._lcd_body)

        # ── Decky Loader (docked users only) ──────────────────────────────────
        self._decky_div  = _hdiv()
        self._decky_hdr  = _lbl("🖥  Docked Display Switching", 12, C_IW, bold=True, align=Qt.AlignLeft)
        self._decky_body = _lbl(
            "The DeckOps Decky plugin auto-switches display settings when "
            "you connect or disconnect a monitor. Decky Loader is required.",
            11, C_DIM, align=Qt.AlignLeft)
        self._decky_btn  = _btn("Get Decky Loader  →  decky.xyz", C_BLUE_BTN, size=12, h=40)
        self._decky_btn.setFixedWidth(320)
        self._decky_btn.clicked.connect(lambda: _detached_open(
            ["xdg-open", "https://decky.xyz/"]
        ))
        dbw = QHBoxLayout(); dbw.addWidget(self._decky_btn); dbw.addStretch()
        sl.addWidget(self._decky_div)
        sl.addWidget(self._decky_hdr)
        sl.addWidget(self._decky_body)
        sl.addLayout(dbw)

        # ── Restore player saves (visible only when backups exist) ────────────
        self._restore_div = _hdiv()
        self._restore_hdr = _lbl("💾  Restore Player Saves", 12, C_IW, bold=True, align=Qt.AlignLeft)
        self._restore_body = _lbl(
            "Backups from a previous install were found. "
            "Restore your configs, stats, and custom classes?",
            11, C_DIM, align=Qt.AlignLeft)
        self._restore_status = _lbl("", 11, C_IW, align=Qt.AlignLeft)
        self._restore_status.setVisible(False)

        self._restore_btn = _btn("Restore Saves", C_IW, size=12, h=40)
        self._restore_btn.setFixedWidth(200)
        self._restore_btn.clicked.connect(self._do_restore)
        self._restore_skip = _btn("Skip", C_DARK_BTN, size=12, h=40)
        self._restore_skip.setFixedWidth(120)
        self._restore_skip.clicked.connect(self._skip_restore)

        rbw = QHBoxLayout(); rbw.setSpacing(12)
        rbw.addWidget(self._restore_btn)
        rbw.addWidget(self._restore_skip)
        rbw.addStretch()

        sl.addWidget(self._restore_div)
        sl.addWidget(self._restore_hdr)
        sl.addWidget(self._restore_body)
        sl.addLayout(rbw)
        sl.addWidget(self._restore_status)

        self._restore_widgets = [
            self._restore_div, self._restore_hdr, self._restore_body,
            self._restore_btn, self._restore_skip,
        ]

        sl.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll, stretch=1)

        # ── Continue button (pinned outside scroll) ───────────────────────────
        lay.addSpacing(8)
        cont = _btn("Continue  >>", C_IW, h=52)
        cont.clicked.connect(self._go_management)
        cw = QHBoxLayout(); cw.addStretch(); cw.addWidget(cont, stretch=1); cw.addStretch()
        lay.addLayout(cw)

    def showEvent(self, e):
        super().showEvent(e)
        is_docked = cfg.is_docked()
        self._decky_div.setVisible(is_docked)
        self._decky_hdr.setVisible(is_docked)
        self._decky_body.setVisible(is_docked)
        self._decky_btn.setVisible(is_docked)
        is_lcd = cfg.is_lcd()
        self._lcd_div.setVisible(is_lcd)
        self._lcd_hdr.setVisible(is_lcd)
        self._lcd_body.setVisible(is_lcd)
        show_mw2own = (cfg.get_game_source() == "own"
                       and cfg.is_game_setup_for_source("iw4mp", "own"))
        self._mw2own_div.setVisible(show_mw2own)
        self._mw2own_hdr.setVisible(show_mw2own)
        self._mw2own_body.setVisible(show_mw2own)
        try:
            from save_backup import has_backups
            show_restore = has_backups()
        except Exception:
            show_restore = False
        for w in self._restore_widgets:
            w.setVisible(show_restore)
        self._restore_status.setVisible(False)

    def _do_restore(self):
        """Run save restore in a background thread."""
        self._restore_btn.setEnabled(False)
        self._restore_skip.setEnabled(False)
        self._restore_status.setText("Restoring saves...")
        self._restore_status.setVisible(True)

        def _run():
            try:
                from save_backup import restore_saves
                steam_root = find_steam_root()
                restored = restore_saves(
                    steam_root=steam_root,
                    on_progress=lambda msg: None,
                )
                count = len(restored) if restored else 0
                if count > 0:
                    groups = ", ".join(restored.keys())
                    self._s.done.emit(True)
                    QTimer.singleShot(0, lambda: self._restore_finished(
                        f"✓  Restored saves for {count} group(s): {groups}"))
                else:
                    QTimer.singleShot(0, lambda: self._restore_finished(
                        "No matching save data found to restore."))
            except Exception as ex:
                QTimer.singleShot(0, lambda: self._restore_finished(
                    f"⚠  Restore failed: {ex}"))

        self._s = _Sigs()
        threading.Thread(target=_run, daemon=True).start()

    def _restore_finished(self, message):
        self._restore_status.setText(message)
        self._restore_status.setVisible(True)
        self._restore_btn.setVisible(False)
        self._restore_skip.setVisible(False)
        self._restore_body.setVisible(False)

    def _skip_restore(self):
        """Hide the restore section without restoring."""
        for w in self._restore_widgets:
            w.setVisible(False)
        self._restore_status.setVisible(False)

    def _go_management(self):
        # Restart Steam so shortcuts and compat tool changes take effect.
        os.system("gtk-launch steam.desktop &")
        root = find_steam_root()
        get_screen(self.stack, "ManagementScreen").set_installed(find_installed_games(parse_library_folders(root)))
        go_to(self.stack, "ManagementScreen")


# ── ConfigureScreen ───────────────────────────────────────────────────────────
class ConfigureScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.screen_name = "ConfigureScreen"
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        t = QLabel("SETTINGS"); t.setFont(font(28,True)); t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("color:#FFF;background:transparent;padding:20px 0 10px 0;"); lay.addWidget(t)

        # Scroll area for all settings content
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget()
        sl = QVBoxLayout(inner); sl.setContentsMargins(60,10,60,30); sl.setSpacing(18)

        # ── Background Music ──────────────────────────────────────────────
        sl.addWidget(_lbl("Background Music", 13, "#CCC", align=Qt.AlignLeft))
        mr = QHBoxLayout(); mr.setSpacing(12)
        self._music_on = _music_enabled
        self._music_toggle = _btn(
            "Music: ON" if self._music_on else "Music: OFF",
            C_IW if self._music_on else C_DARK_BTN,
            size=12, h=40,
        )
        self._music_toggle.setFixedWidth(160)
        self._music_toggle.clicked.connect(self._toggle_music)
        self._vol_slider = QSlider(Qt.Horizontal); self._vol_slider.setRange(0,100)
        self._vol_slider.setValue(int(_music_volume*100))
        self._vol_label = _lbl(f"{int(_music_volume*100)}%", 12, C_DIM, wrap=False)
        self._vol_label.setFixedWidth(40)
        self._vol_slider.valueChanged.connect(self._set_volume)
        mr.addWidget(self._music_toggle); mr.addWidget(self._vol_slider,stretch=1); mr.addWidget(self._vol_label)
        sl.addLayout(mr)
        sl.addWidget(_hdiv())

        # ── Controller Profiles ───────────────────────────────────────────
        sl.addWidget(_lbl("Controller Profiles", 13, "#CCC", align=Qt.AlignLeft))
        gr = QHBoxLayout(); gr.setSpacing(8)
        gr.addWidget(_lbl("Gyro:", 12, "#AAA", wrap=False))
        self._gyro_btns = {}
        # SD LCD/OLED and Steam Machine get 4 modes; others get 2.
        # Hold/toggle hidden dynamically in showEvent.
        for mode in ("on", "hold", "toggle", "off"):
            labels = {"on": "ADS", "hold": "Hold", "toggle": "Toggle", "off": "Off"}
            b = _btn(labels[mode], C_DARK_BTN, size=11, h=36)
            b.setFixedWidth(90)
            b.clicked.connect(lambda checked, m=mode: self._set_gyro(m))
            gr.addWidget(b)
            self._gyro_btns[mode] = b
        gr.addSpacing(16)
        ctrl_btn = _btn("Re-apply Templates", C_DARK_BTN, size=12, h=36)
        ctrl_btn.clicked.connect(self._apply_controller_profiles)
        gr.addWidget(ctrl_btn)
        gr.addStretch()
        sl.addLayout(gr)
        sl.addWidget(_hdiv())

        # ── Player Name & Links ───────────────────────────────────────────
        sl.addWidget(_lbl("Player Name & Links", 13, "#CCC", align=Qt.AlignLeft))
        nr = QHBoxLayout(); nr.setSpacing(12)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Enter player name...")
        self._name_input.setFixedHeight(36)
        self._name_input.setMaxLength(32)
        self._name_input.setStyleSheet(
            "QLineEdit{background:#2A2A3A;color:#FFF;border:1px solid #444;"
            "border-radius:6px;padding:0 10px;font-size:13px;}"
            "QLineEdit:focus{border:1px solid #888;}"
        )
        save_btn = _btn("Save", C_IW, size=12, h=36)
        save_btn.setFixedWidth(80)
        save_btn.clicked.connect(self._save_name)
        nr.addWidget(self._name_input, stretch=1); nr.addWidget(save_btn)
        discord_btn = _btn("Discord", "#5865F2", size=12, h=36)
        discord_btn.setFixedWidth(100)
        discord_btn.clicked.connect(lambda: self._open_url("https://discord.gg/bkSQeq5Azk"))
        stable_btn = _btn("Stable", C_DARK_BTN, size=12, h=36)
        stable_btn.setFixedWidth(100)
        stable_btn.clicked.connect(lambda: self._open_url(f"https://github.com/{GITHUB_USER}/DeckOps"))
        nightly_btn = _btn("Nightly", C_DARK_BTN, size=12, h=36)
        nightly_btn.setFixedWidth(100)
        nightly_btn.clicked.connect(lambda: self._open_url(f"https://github.com/{GITHUB_USER}/DeckOps-Nightly"))
        nr.addWidget(discord_btn); nr.addWidget(stable_btn); nr.addWidget(nightly_btn)
        sl.addLayout(nr)
        self._name_note = _lbl("Sets your offline name for CoD4x, IW4x, AlterWare, T7X, and Plutonium. Does not affect CleanOps.", 10, C_DIM, align=Qt.AlignLeft)
        sl.addWidget(self._name_note)
        sl.addWidget(_hdiv())

        # ── Shader Cache (LCD only) ───────────────────────────────────────
        self._shader_row = QWidget()
        sr_lay = QVBoxLayout(self._shader_row); sr_lay.setContentsMargins(0,0,0,0); sr_lay.setSpacing(8)
        sr_lay.addWidget(_lbl("Shader Cache", 13, "#CCC", align=Qt.AlignLeft))
        sc_btn = _btn("Clear Shader Cache", C_DARK_BTN, size=12, h=36)
        sc_btn.setFixedWidth(220)
        sc_btn.clicked.connect(self._clear_shader_cache)
        sr_h = QHBoxLayout(); sr_h.addWidget(sc_btn); sr_h.addStretch()
        sr_lay.addLayout(sr_h)
        sl.addWidget(self._shader_row)
        self._shader_hdiv = _hdiv()
        sl.addWidget(self._shader_hdiv)

        # ── Updates & Danger Zone (single row) ────────────────────────────
        sl.addWidget(_lbl("Updates & Danger Zone", 13, "#CCC", align=Qt.AlignLeft))
        udr = QHBoxLayout(); udr.setSpacing(12)
        self._update_btn = _btn("Check for Updates", C_BLUE_BTN, size=12, h=40)
        self._update_btn.setFixedWidth(220)
        self._update_btn.clicked.connect(self._check_for_updates)
        udr.addWidget(self._update_btn)
        self._update_status = _lbl("", 11, C_DIM, wrap=False)
        udr.addWidget(self._update_status, stretch=1)
        uninstall_btn = _btn("Full Uninstall", C_RED_BTN, size=12, h=40)
        reset_cfg_btn = _btn("Reset DeckOps Config", C_RED_BTN, size=12, h=40)
        uninstall_btn.clicked.connect(self._confirm_uninstall)
        reset_cfg_btn.clicked.connect(self._confirm_reset)
        udr.addWidget(uninstall_btn); udr.addWidget(reset_cfg_btn)
        sl.addLayout(udr)
        sl.addWidget(_hdiv())

        # ── About ─────────────────────────────────────────────────────────
        self._about_label = _lbl("", 11, C_DIM, align=Qt.AlignLeft)
        sl.addWidget(self._about_label)

        sl.addStretch()
        self.status = _lbl("", 12, C_DIM)
        sl.addWidget(self.status)

        scroll.setWidget(inner)
        lay.addWidget(scroll, stretch=1)

        # Back button stays outside the scroll area
        back = _btn("<< Back", C_DARK_BTN, h=48); back.setFixedWidth(160)
        back.clicked.connect(lambda: go_to(self.stack, "ManagementScreen"))
        bw = QHBoxLayout(); bw.setContentsMargins(60,8,60,16)
        bw.addWidget(back); bw.addStretch()
        lay.addLayout(bw)

    def showEvent(self, event):
        super().showEvent(event)
        # Refresh dynamic state
        model = cfg.get_deck_model() or "unknown"
        source = cfg.get_game_source() or "steam"
        source_label = "Steam" if source == "steam" else "Steam & Non-Steam"
        player = cfg.get_player_name() or "Player"
        self._name_input.setText(player if player != "Player" else "")

        # Show hold/toggle only for Steam Deck LCD/OLED and Steam Machine
        has_full_modes = model in ("lcd", "oled", "steam_machine")
        self._gyro_btns["hold"].setVisible(has_full_modes)
        self._gyro_btns["toggle"].setVisible(has_full_modes)
        # Relabel ADS button for non-SD/SM devices
        self._gyro_btns["on"].setText("ADS" if has_full_modes else "Gyro On")

        # Gyro highlight
        gyro = cfg.get_gyro_mode() or "on"
        # If non-SD/SM device has hold/toggle saved, treat as "on" for highlight
        if not has_full_modes and gyro in ("hold", "toggle"):
            gyro = "on"
        for mode, btn in self._gyro_btns.items():
            if mode == gyro:
                btn.setStyleSheet(btn.styleSheet().replace(C_DARK_BTN, C_IW))
            else:
                btn.setStyleSheet(btn.styleSheet().replace(C_IW, C_DARK_BTN))

        # LCD-only shader cache section
        is_lcd = (model == "lcd")
        self._shader_row.setVisible(is_lcd)
        self._shader_hdiv.setVisible(is_lcd)

        # Build info
        build = "dev"
        build_path = os.path.join(PROJECT_ROOT, "BUILD")
        if os.path.exists(build_path):
            try:
                with open(build_path, "r") as f:
                    build = f.read().strip() or "dev"
            except Exception:
                _log.debug("BUILD file read failed", exc_info=True)

        # Device display name for about label
        if model == "steam_machine":
            device_display = "Steam Machine"
        elif model == "other":
            other_dev = cfg.get_other_device() or "unknown"
            _DEVICE_NAMES = {
                "1920x1200": "Other (1920×1200)",
                "1920x1200_144hz": "Other (1920×1200 144Hz)",
                "1920x1080": "Other (1920×1080)",
                "1280x720": "Other (1280×720)",
            }
            device_display = _DEVICE_NAMES.get(other_dev, f"Other ({other_dev})")
        elif model == "oled":
            device_display = "Steam Deck OLED"
        elif model == "lcd":
            device_display = "Steam Deck LCD"
        else:
            device_display = f"Steam Deck {model.upper()}"

        self._about_label.setText(
            f"Device: {device_display}  |  Source: {source_label}  |  "
            f"Player: {player}\n"
            f"Build: {build}"
        )

    def _toggle_music(self):
        self._music_on = not self._music_on
        _set_audio_enabled(self._music_on)
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

    def _set_gyro(self, mode):
        cfg.set_gyro_mode(mode)
        # Update button highlights
        for m, btn in self._gyro_btns.items():
            if m == mode:
                btn.setStyleSheet(btn.styleSheet().replace(C_DARK_BTN, C_IW))
            else:
                btn.setStyleSheet(btn.styleSheet().replace(C_IW, C_DARK_BTN))
        self.status.setText(f"Gyro mode set to {mode.upper()}. Hit Re-apply Templates to update controller profiles.")

    def _apply_controller_profiles(self):
        self.status.setText("Re-applying controller profiles...")
        s = _Sigs()
        s.log.connect(lambda msg: self.status.setText(msg))
        s.done.connect(lambda ok: self.status.setText(
            "✓  Controller profiles applied." if ok else "✗  Failed — check that Steam is closed."
        ))
        def _run():
            try:
                from controller_profiles import install_controller_templates, assign_controller_profiles, assign_external_controller_profiles
                from wrapper import kill_steam, set_steam_input_enabled
                s.log.emit("Closing Steam...")
                kill_steam(on_progress=lambda msg: s.log.emit(f"  {msg}"))
                install_controller_templates(
                    on_progress=lambda msg: s.log.emit(msg)
                )
                gyro_mode = cfg.get_gyro_mode() or "on"
                assign_controller_profiles(
                    gyro_mode,
                    on_progress=lambda msg: s.log.emit(msg)
                )
                if cfg.is_docked():
                    controller_type = cfg.get_external_controller() or "playstation"
                    assign_external_controller_profiles(
                        controller_type,
                        gyro_mode,
                        on_progress=lambda msg: s.log.emit(msg)
                    )
                sr = cfg.load().get("steam_root", "")
                if sr:
                    set_steam_input_enabled(sr)
                s.done.emit(True)
                s.log.emit("✓  Controller profiles applied. It is now safe to reopen Steam.")
            except Exception as ex:
                s.log.emit(f"✗  Failed: {ex}")
                s.done.emit(False)
        threading.Thread(target=_run, daemon=True).start()

    def _save_name(self):
        name = self._name_input.text().strip()
        if not name:
            self.status.setText("Please enter a name.")
            return
        cfg.set_player_name(name)
        self.status.setText(f"Updating player name to \"{name}\"...")
        s = _Sigs()
        s.log.connect(lambda msg: self.status.setText(msg))
        def _run():
            try:
                from game_config import rename_player
                from detect_games import find_installed_games, parse_library_folders
                steam_root = cfg.load().get("steam_root", "") or find_steam_root()
                installed = {}
                if steam_root:
                    installed = find_installed_games(parse_library_folders(steam_root))
                count = rename_player(
                    name, steam_root, installed_games=installed,
                    on_progress=lambda msg: s.log.emit(msg),
                )
                s.log.emit(f"✓  Player name set to \"{name}\" ({count} config(s) updated).")
            except Exception as ex:
                s.log.emit(f"✗  Failed: {ex}")
        threading.Thread(target=_run, daemon=True).start()

    def _clear_shader_cache(self):
        self.status.setText("Clearing shader cache...")
        s = _Sigs()
        s.log.connect(lambda msg: self.status.setText(msg))
        def _run():
            try:
                from cache_cleanup import cleanup_shader_cache, STEAM_APPIDS
                setup = cfg.get_setup_games()
                cleared = 0
                for key in STEAM_APPIDS:
                    if key in setup:
                        source = setup[key].get("source", "steam")
                        cleanup_shader_cache(key, source)
                        cleared += 1
                s.log.emit(f"✓  Shader cache cleared for {cleared} game(s).")
            except Exception as ex:
                s.log.emit(f"✗  Failed: {ex}")
        threading.Thread(target=_run, daemon=True).start()

    def _open_url(self, url):
        _detached_open(["xdg-open", url])

    def _confirm_uninstall(self):
        reply = QMessageBox.warning(
            self, "Full Uninstall",
            "This will remove all DeckOps files, shortcuts, controller profiles, "
            "and mod client installations. Your Steam games will NOT be deleted.\n\n"
            "DeckOps will close and the uninstaller will run in a terminal window.\n\n"
            "Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._run_uninstaller()

    def _run_uninstaller(self):
        uninstall_script = os.path.join(PROJECT_ROOT, "deckops_uninstall.sh")
        if not os.path.exists(uninstall_script):
            self.status.setText("✗  Uninstall script not found.")
            return
        self.status.setText("Launching uninstaller...")
        try:
            # Launch in Konsole so the user can see progress
            subprocess.Popen(
                ["konsole", "-e", "bash", uninstall_script],
                start_new_session=True,
            )
            # Close DeckOps — the uninstaller will remove our files
            _kill_audio()
            QApplication.instance().quit()
        except Exception:
            # Konsole not available (shouldn't happen on SteamOS)
            try:
                subprocess.Popen(
                    ["xterm", "-e", "bash", uninstall_script],
                    start_new_session=True,
                )
                _kill_audio()
                QApplication.instance().quit()
            except Exception as ex:
                self.status.setText(f"✗  Could not launch uninstaller: {ex}")

    # ── Update check ────────────────────────────────────────────────────────
    _GITHUB_USER = GITHUB_USER
    _GITHUB_REPO = GITHUB_REPO

    def _init_update_signals(self):
        """Connect the update result signal (call once during __init__)."""
        self._update_sig = _Sigs()
        self._update_sig.log.connect(self._on_update_signal)

    def _check_for_updates(self):
        """Hit GitHub API to compare local SHA against remote HEAD."""
        self._init_update_signals()
        self._update_btn.setEnabled(False)
        self._update_status.setText("Checking...")
        self._update_status.setStyleSheet(f"color:{C_DIM};")
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_worker(self):
        try:
            version_file = os.path.join(PROJECT_ROOT, "VERSION")
            local_sha = "0"
            if os.path.isfile(version_file):
                with open(version_file) as f:
                    local_sha = f.read().strip() or "0"

            req = urllib.request.Request(
                f"https://api.github.com/repos/{self._GITHUB_USER}/{self._GITHUB_REPO}/commits/main",
                headers={"User-Agent": "DeckOps"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            remote_sha = data.get("sha", "")

            if not remote_sha:
                self._update_sig.log.emit("FAIL|Could not reach GitHub.")
                return

            if local_sha == remote_sha:
                self._update_sig.log.emit("OK|You're up to date!")
                return

            # Get changed file count
            file_count = "unknown"
            if local_sha != "0":
                try:
                    creq = urllib.request.Request(
                        f"https://api.github.com/repos/{self._GITHUB_USER}/{self._GITHUB_REPO}/compare/{local_sha}...{remote_sha}",
                        headers={"User-Agent": "DeckOps"},
                    )
                    with urllib.request.urlopen(creq, timeout=15) as r2:
                        cdata = json.loads(r2.read())
                    files = cdata.get("files", [])
                    file_count = str(len(files))
                except Exception:
                    pass

            self._update_sig.log.emit(f"UPDATE|Update available — {file_count} file(s) changed.")

        except Exception as ex:
            _log.warning("Update check failed: %s", ex)
            self._update_sig.log.emit("FAIL|Update check failed.")

    def _on_update_signal(self, msg):
        """Slot that runs on the main thread via pyqtSignal."""
        kind, text = msg.split("|", 1)
        self._update_result(text, kind == "UPDATE")

    def _update_result(self, msg, update_available):
        self._update_btn.setEnabled(True)
        self._update_status.setText(msg)
        if update_available:
            self._update_status.setStyleSheet(f"color:{C_IW};")
            self._update_btn.setText("Update && Restart")
            try:
                self._update_btn.clicked.disconnect()
            except TypeError:
                pass
            self._update_btn.clicked.connect(self._apply_update)
        else:
            self._update_status.setStyleSheet(f"color:{C_DIM};")

    def _apply_update(self):
        reply = QMessageBox.question(
            self, "Update DeckOps",
            "DeckOps will download the update and relaunch.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        self._update_btn.setEnabled(False)
        self._update_btn.setText("Updating...")
        self._update_status.setText("Downloading update...")
        self._update_status.setStyleSheet(f"color:{C_DIM};")

        self._apply_sig = _Sigs()
        self._apply_sig.log.connect(self._on_apply_signal)
        threading.Thread(target=self._apply_worker, daemon=True).start()

    def _apply_worker(self):
        """Download changed files, stage, apply, then signal relaunch."""
        github_user = self._GITHUB_USER
        github_repo = self._GITHUB_REPO
        github_raw = f"https://raw.githubusercontent.com/{github_user}/{github_repo}/main"
        install_dir = PROJECT_ROOT
        update_dir = os.path.join(install_dir, ".update")
        version_file = os.path.join(install_dir, "VERSION")

        # Protected paths — never overwritten
        protected = {"logs", "deckops.json", "assets/music/background.mp3"}

        def is_protected(filepath):
            if filepath.startswith("logs/"):
                return True
            return filepath in protected

        try:
            # Read local SHA
            local_sha = "0"
            if os.path.isfile(version_file):
                with open(version_file) as f:
                    local_sha = f.read().strip() or "0"

            # Get remote SHA
            req = urllib.request.Request(
                f"https://api.github.com/repos/{github_user}/{github_repo}/commits/main",
                headers={"User-Agent": "DeckOps"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            remote_sha = data.get("sha", "")

            if not remote_sha or local_sha == remote_sha:
                self._apply_sig.log.emit("FAIL|Already up to date.")
                return

            # Get changed files list
            changed_files = []
            if local_sha != "0":
                try:
                    creq = urllib.request.Request(
                        f"https://api.github.com/repos/{github_user}/{github_repo}/compare/{local_sha}...{remote_sha}",
                        headers={"User-Agent": "DeckOps"},
                    )
                    with urllib.request.urlopen(creq, timeout=15) as r2:
                        cdata = json.loads(r2.read())
                    changed_files = [f["filename"] for f in cdata.get("files", [])]
                except Exception:
                    pass

            # Clean staging dir
            if os.path.isdir(update_dir):
                shutil.rmtree(update_dir)
            os.makedirs(update_dir, exist_ok=True)

            if not changed_files:
                # No compare available — full zip download
                self._apply_sig.log.emit("PROG|Downloading full update...")
                import tempfile, zipfile
                tmp_zip = tempfile.mktemp(suffix=".zip", prefix="deckops_update_")
                req = urllib.request.Request(
                    f"https://github.com/{github_user}/{github_repo}/archive/refs/heads/main.zip",
                    headers={"User-Agent": "DeckOps"},
                )
                with urllib.request.urlopen(req, timeout=120) as r, open(tmp_zip, "wb") as f:
                    f.write(r.read())

                tmp_extract = tempfile.mkdtemp(prefix="deckops_extract_")
                with zipfile.ZipFile(tmp_zip, "r") as zf:
                    zf.extractall(tmp_extract)
                os.remove(tmp_zip)

                # Find the extracted folder (GitHub zips have a top-level dir)
                entries = [e for e in os.listdir(tmp_extract)
                           if os.path.isdir(os.path.join(tmp_extract, e))]
                extracted = os.path.join(tmp_extract, entries[0]) if entries else tmp_extract

                # Copy to staging
                shutil.copytree(extracted, update_dir, dirs_exist_ok=True)
                shutil.rmtree(tmp_extract, ignore_errors=True)

                # Apply: copy everything, then restore protected files
                saved_config = None
                config_path = os.path.join(install_dir, "deckops.json")
                if os.path.isfile(config_path):
                    with open(config_path) as f:
                        saved_config = f.read()

                saved_music = None
                music_path = os.path.join(install_dir, "assets", "music", "background.mp3")
                if os.path.isfile(music_path):
                    saved_music = music_path + ".bak"
                    shutil.copy2(music_path, saved_music)

                # Copy staged files into install dir
                shutil.copytree(update_dir, install_dir, dirs_exist_ok=True)

                # Restore protected
                if saved_config is not None:
                    with open(config_path, "w") as f:
                        f.write(saved_config)
                if saved_music and os.path.isfile(saved_music):
                    shutil.move(saved_music, music_path)
            else:
                # Partial update — download only changed files
                total = len(changed_files)
                for idx, filepath in enumerate(changed_files):
                    if is_protected(filepath):
                        continue
                    self._apply_sig.log.emit(
                        f"PROG|Downloading ({idx+1}/{total}): {os.path.basename(filepath)}")

                    dest = os.path.join(update_dir, filepath)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)

                    try:
                        req = urllib.request.Request(
                            f"{github_raw}/{filepath}",
                            headers={"User-Agent": "DeckOps"},
                        )
                        with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
                            f.write(r.read())
                    except urllib.error.HTTPError as ex:
                        if ex.code == 404:
                            # File was deleted or renamed — skip it
                            _log.info("Skipping deleted/renamed file: %s", filepath)
                            continue
                        _log.warning("Failed to download %s: %s", filepath, ex)
                        shutil.rmtree(update_dir, ignore_errors=True)
                        self._apply_sig.log.emit(f"FAIL|Download failed: {filepath}")
                        return
                    except Exception as ex:
                        _log.warning("Failed to download %s: %s", filepath, ex)
                        shutil.rmtree(update_dir, ignore_errors=True)
                        self._apply_sig.log.emit(f"FAIL|Download failed: {filepath}")
                        return

                # Apply staged files
                for filepath in changed_files:
                    if is_protected(filepath):
                        continue
                    staged = os.path.join(update_dir, filepath)
                    if os.path.isfile(staged):
                        target = os.path.join(install_dir, filepath)
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        shutil.copy2(staged, target)

            # Cleanup staging
            shutil.rmtree(update_dir, ignore_errors=True)

            # Write new version SHA
            with open(version_file, "w") as f:
                f.write(remote_sha)

            # chmod +x shell scripts
            for script in ("launcher.sh", "deckops_uninstall.sh", "install.sh"):
                spath = os.path.join(install_dir, script)
                if os.path.isfile(spath):
                    os.chmod(spath, os.stat(spath).st_mode | stat.S_IEXEC)

            # Clean up stale flag file if present
            flag = os.path.expanduser("~/.deckops_update_requested")
            if os.path.isfile(flag):
                os.remove(flag)

            _log.info("Update applied successfully — SHA %s", remote_sha)
            self._apply_sig.log.emit("RELAUNCH|Update complete! Relaunching...")

        except Exception as ex:
            _log.error("Update failed: %s", ex)
            shutil.rmtree(update_dir, ignore_errors=True)
            self._apply_sig.log.emit(f"FAIL|Update failed: {ex}")

    def _on_apply_signal(self, msg):
        kind, text = msg.split("|", 1)
        if kind == "PROG":
            self._update_status.setText(text)
        elif kind == "RELAUNCH":
            self._update_status.setText(text)
            self._update_status.setStyleSheet(f"color:{C_IW};")
            _kill_audio()
            QTimer.singleShot(1000, self._relaunch)
        else:
            # FAIL
            self._update_btn.setEnabled(True)
            self._update_btn.setText("Check for Updates")
            try:
                self._update_btn.clicked.disconnect()
            except TypeError:
                pass
            self._update_btn.clicked.connect(self._check_for_updates)
            self._update_status.setText(text)
            self._update_status.setStyleSheet(f"color:{C_TREY};")

    def _relaunch(self):
        """Relaunch DeckOps by exec-ing the same Python + main.py."""
        # Clear bytecode cache so updated .py files are re-imported
        pycache = os.path.join(PROJECT_ROOT, "src", "__pycache__")
        if os.path.isdir(pycache):
            shutil.rmtree(pycache, ignore_errors=True)
        python = sys.executable
        entry = os.path.join(PROJECT_ROOT, "src", "main.py")
        _log.info("Relaunching: %s %s", python, entry)
        os.execv(python, [python, entry])

    def _confirm_reset(self):
        reply = QMessageBox.warning(
            self, "Reset Config",
            "This will wipe the DeckOps configuration file (deckops.json). "
            "DeckOps will restart and run the setup flow again.\n\n"
            "Your game files and Steam games are not affected.\n\n"
            "Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._reset_deckops()

    def _reset_deckops(self):
        cfg.reset()
        self.status.setText("Config wiped. Restarting setup...")
        QTimer.singleShot(1500, lambda: go_to(self.stack, "BootstrapScreen"))



# ── UpdateScreen ──────────────────────────────────────────────────────────────
class UpdateScreen(QWidget):
    """Handles Update from ManagementScreen."""

    def __init__(self, stack):
        super().__init__(); self.stack = stack; self.screen_name = "UpdateScreen"
        self.selected   = []
        self.steam_root = ""
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
        _log_to_file(text)

    def showEvent(self, e):
        super().showEvent(e)
        self.bar.setValue(0); self.log.clear()
        self.steam_btn.setVisible(False); self.back_btn.setVisible(False)
        self._steam_closed.clear()
        _log_to_file("── Update started ──")
        QTimer.singleShot(400, lambda: threading.Thread(target=self._run, daemon=True).start())

    def _on_done(self, _):
        self.cur.setText("Done! It is now safe to open Steam.")
        self.back_btn.setVisible(True)

    def _go_back(self):
        root = find_steam_root()
        get_screen(self.stack, "ManagementScreen").set_installed(find_installed_games(parse_library_folders(root)))
        go_to(self.stack, "ManagementScreen")

    def _run(self):
        from wrapper import get_proton_path, find_compatdata, kill_steam
        from iw4x import install_iw4x
        from cod4x import install_cod4x
        from iw3sp import install_iw3sp
        from t6sp_mod import install_t6sp_mod
        from cleanops import install_cleanops
        from t7x import install_t7x
        from plutonium_oled import install_plutonium

        has_cod4  = any(KEY_CLIENT.get(k) in ("cod4x", "iw3sp") for k, _, _ in self.selected)
        has_iw4x  = any(KEY_CLIENT.get(k) == "iw4x" for k, _, _ in self.selected)
        has_plut  = any(KEY_CLIENT.get(k) == "plutonium" for k, _, _ in self.selected)
        proton    = get_proton_path(self.steam_root)
        total     = len(self.selected)

        # Read setup_games to determine source for each key
        setup_games = cfg.get_setup_games()

        if not has_plut:
            self._s.progress.emit(5, "Closing Steam...")
            self._s.log.emit("Closing Steam...")
            try:
                kill_steam(on_progress=lambda msg: self._s.log.emit(f"  {msg}"))
                self._s.log.emit("  ✓ Steam closed.")
            except Exception as ex:
                self._s.log.emit(f"  Could not close Steam: {ex}")

        # ── Clean slate: clear launch options and compat tools ─────────
        # Same clean-slate approach as InstallScreen / OwnInstallScreen.
        # Prevents stale entries from previous installs (LCD→OLED, older
        # DeckOps versions) interfering with the update.
        try:
            from wrapper import clear_launch_options, clear_compat_tool
            from ge_proton import MANAGED_APPIDS
            for appid in MANAGED_APPIDS:
                clear_launch_options(self.steam_root, appid)
            clear_compat_tool(MANAGED_APPIDS)
            self._s.log.emit("✓  Cleared all launch options and compat tools")
        except Exception as ex:
            self._s.log.emit(f"  Launch option / compat tool cleanup skipped: {ex}")

        # Build installed_games dict for Plutonium sibling key resolution
        installed_for_plut = {k: g for k, _, g in self.selected if g}

        for idx, (key, gd, game) in enumerate(self.selected):
            if not game:
                continue
            base_name = gd["base"]
            bp = int(idx / total * 90)
            self._s.progress.emit(bp, f"Updating {base_name}...")
            def op(pct, msg, _b=bp): self._s.progress.emit(_b + int(pct / 100 * (90 // total)), msg)
            c = KEY_CLIENT.get(key, gd.get("client", ""))

            # Determine source from setup_games config entry
            entry = setup_games.get(key, {})
            source = entry.get("source", "steam")

            try:
                from plutonium_oled import GAME_META as _PLUT_META
                from detect_games import GAMES as _GAMES_MAP
                if c == "plutonium" and key in _PLUT_META:
                    _appid = _PLUT_META[key][0]
                elif c == "alterware" and key in _GAMES_MAP:
                    _appid = _GAMES_MAP[key]["appid"]
                else:
                    _appid = gd["appid"]

                # Resolve compatdata - own games may have CRC-based prefix
                if source == "own":
                    compat = game.get("compatdata_path", "")
                    if not compat:
                        compat = find_compatdata(self.steam_root, _appid,
                                                  game_install_dir=game.get("install_dir"))
                else:
                    compat = find_compatdata(self.steam_root, _appid,
                                              game_install_dir=game.get("install_dir"))
                if not compat and game.get("install_dir"):
                    steamapps = os.path.dirname(os.path.dirname(game["install_dir"]))
                    compat = os.path.join(steamapps, "compatdata", str(_appid))

                if c == "cod4x":
                    install_cod4x(game, self.steam_root, proton, compat, op,
                                  appid=gd["appid"])
                elif c == "iw3sp":
                    install_iw3sp(game, self.steam_root, proton, compat, op,
                                  source=source)
                elif c == "iw4x":
                    install_iw4x(game, self.steam_root, proton, compat, op,
                                 source=source, install_dlc=False)
                elif c == "plutonium":
                    install_plutonium(game, key, self.steam_root, proton, compat,
                                     on_progress=op,
                                     installed_games=installed_for_plut,
                                     source=source)
                elif c == "cleanops":
                    install_cleanops(game, self.steam_root, proton, compat, op,
                                    source=source)
                elif c == "t7x":
                    t7x_dir = install_t7x(game, on_progress=op)
                    game["install_dir"] = t7x_dir
                elif c == "alterware":
                    from alterware import install_alterware
                    install_alterware(game, key, self.steam_root, proton, compat, op,
                                     source=source)
                elif c == "t6sp_mod":
                    install_t6sp_mod(game, self.steam_root, proton, compat, op,
                                    source=source)
                self._s.log.emit(f"✓  {base_name} ({key}) done")
            except Exception as ex:
                self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        self._s.progress.emit(100, "All done!")
        self._s.done.emit(True)
