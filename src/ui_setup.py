"""
ui_setup.py — First-run setup flow for DeckOps

Replaces IntroScreen + SourceScreen from ui_qt.py with a unified flow:
    OS → Device → Gyro → Name → Source → [Controller] → [Play Mode] → Done

Supports SteamOS, Bazzite, CachyOS, and General PC with per-OS controller
template strategy.
"""

import os, threading

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QPlainTextEdit, QFrame,
)
from PyQt5.QtCore import Qt, QTimer

import config as cfg
from identity import GITHUB_USER, GITHUB_REPO

from ui_constants import (
    C_BG, C_CARD, C_IW, C_TREY, C_DIM, C_DARK_BTN, C_BLUE_BTN,
    font, _btn, _lbl, _hdiv, _title_block, _Sigs,
    go_to, get_screen,
    PROJECT_ROOT,
)


# ── Device definitions ────────────────────────────────────────────────────────
#
# Each device maps to: deck_model, other_device (resolution key),
# other_device_type (controller template group), has_gyro.

DEVICES = {
    "sd_lcd":       {"label": "Steam Deck LCD",       "deck_model": "lcd",   "other_device": None,              "other_device_type": None,         "has_gyro": True},
    "sd_oled":      {"label": "Steam Deck OLED",      "deck_model": "oled",  "other_device": None,              "other_device_type": None,         "has_gyro": True},
    "legion_go":    {"label": "Lenovo Legion Go",     "deck_model": "other", "other_device": "1920x1200",       "other_device_type": "legion_go",  "has_gyro": True},
    "legion_go_s":  {"label": "Lenovo Legion Go S",   "deck_model": "other", "other_device": "1920x1200",       "other_device_type": "legion_go_s","has_gyro": True},
    "legion_go_2":  {"label": "Lenovo Legion Go 2",   "deck_model": "other", "other_device": "1920x1200_144hz", "other_device_type": "legion_go",  "has_gyro": True},
    "rog_ally":     {"label": "ROG Ally",              "deck_model": "other", "other_device": "1920x1080",       "other_device_type": "2btn",       "has_gyro": True},
    "rog_ally_x":   {"label": "ROG Ally X",            "deck_model": "other", "other_device": "1920x1080",       "other_device_type": "2btn",       "has_gyro": True},
    "xbox_ally_x":  {"label": "ROG Xbox Ally X",       "deck_model": "other", "other_device": "1920x1080",       "other_device_type": "2btn",       "has_gyro": True},
    "msi_claw_8":   {"label": "MSI Claw 8",           "deck_model": "other", "other_device": "1920x1200",       "other_device_type": "2btn",       "has_gyro": True},
    "general_pc":   {"label": "PC",                    "deck_model": "other", "other_device": None,              "other_device_type": "generic",    "has_gyro": True},
    "steam_machine":{"label": "Steam Machine",         "deck_model": "steam_machine", "other_device": None,  "other_device_type": "steam_machine", "has_gyro": True},
}


class SetupFlowScreen(QWidget):
    """
    Unified first-run setup. One QWidget with show/hide sections
    for progressive disclosure. screen_name = "SetupFlowScreen".
    """

    def __init__(self, stack):
        super().__init__()
        self.stack = stack
        self.screen_name = "SetupFlowScreen"
        self._selected_os = None      # "steamos", "bazzite", "cachyos", "other_linux"
        self._selected_device = None  # key from DEVICES
        self._is_general_pc = False
        self._is_steam_machine = False

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)

        # ── 1. OS section ─────────────────────────────────────────────────
        self._os_section = QWidget()
        lay = QVBoxLayout(self._os_section)
        lay.setContentsMargins(80, 60, 80, 60); lay.setSpacing(16)
        _title_block(lay)
        lay.addSpacing(8)
        lay.addWidget(_lbl(
            "DeckOps sets up community multiplayer clients for your Call of Duty games, "
            "so you can play online with the best possible performance.",
            14, "#CCCCCC"))
        lay.addSpacing(6)
        for warn in [
            "⚠   DeckOps will automatically create Proton prefixes for your games. "
            "You do NOT need to launch each game through Steam first.",
            "⚠   If you plan to play Plutonium titles online (WaW, BO1, BO2, MW3), "
            "create a free Plutonium account at plutonium.pw before continuing.",
            "⚠   Make sure you have a stable internet connection before installing. "
            "If the install fails, don't re-run it repeatedly, join the Discord for help instead.",
        ]:
            lay.addWidget(_lbl(warn, 13, C_TREY, align=Qt.AlignLeft))
        lay.addSpacing(16)
        lay.addWidget(_lbl("What operating system are you running?", 15, "#CCC"))
        lay.addSpacing(12)

        os_row = QHBoxLayout(); os_row.setSpacing(20)
        for os_key, label in [
            ("steamos", "SteamOS"),
            ("bazzite", "Bazzite"),
            ("cachyos", "CachyOS"),
        ]:
            b = _btn(label, C_IW, h=56)
            b.clicked.connect(lambda checked, k=os_key: self._pick_os(k))
            os_row.addWidget(b)
        lay.addLayout(os_row)
        main_lay.addWidget(self._os_section)

        # ── 2. Device model section ───────────────────────────────────────
        self._model_section = QWidget(); self._model_section.setVisible(False)
        ml = QVBoxLayout(self._model_section)
        ml.setContentsMargins(80, 60, 80, 60); ml.setSpacing(16)
        self._back_os_btn = _btn("← Back", C_DARK_BTN, size=10, h=30)
        self._back_os_btn.setFixedWidth(80)
        self._back_os_btn.clicked.connect(self._back_to_os)
        brow = QHBoxLayout(); brow.addWidget(self._back_os_btn); brow.addStretch()
        ml.addLayout(brow)
        ml.addSpacing(40)
        _title_block(ml)
        ml.addStretch()
        ml.addWidget(_lbl("Which device do you have?", 15, "#CCC"))
        ml.addSpacing(12)
        mrow = QHBoxLayout(); mrow.setSpacing(20)
        lcd_btn  = _btn("Steam Deck LCD",  C_IW, h=56)
        oled_btn = _btn("Steam Deck OLED", C_IW, h=56)
        sm_btn   = _btn("Steam Machine",   C_IW, h=56)
        other_btn = _btn("Other Device",   C_TREY, h=56)
        lcd_btn.clicked.connect(lambda: self._pick_device("sd_lcd"))
        oled_btn.clicked.connect(lambda: self._pick_device("sd_oled"))
        sm_btn.clicked.connect(lambda: self._pick_device("steam_machine"))
        other_btn.clicked.connect(self._show_device_picker)
        mrow.addWidget(lcd_btn); mrow.addWidget(oled_btn); mrow.addWidget(sm_btn); mrow.addWidget(other_btn)
        ml.addLayout(mrow)
        ml.addSpacing(40)
        main_lay.addWidget(self._model_section)

        # ── 3. Specific device picker (Other) ────────────────────────────
        self._device_section = QWidget(); self._device_section.setVisible(False)
        dvl = QVBoxLayout(self._device_section)
        dvl.setContentsMargins(80, 60, 80, 60); dvl.setSpacing(16)
        self._back_model_btn = _btn("← Back", C_DARK_BTN, size=10, h=30)
        self._back_model_btn.setFixedWidth(80)
        self._back_model_btn.clicked.connect(self._back_to_model)
        brow2 = QHBoxLayout(); brow2.addWidget(self._back_model_btn); brow2.addStretch()
        dvl.addLayout(brow2)
        dvl.addSpacing(40)
        _title_block(dvl)
        dvl.addStretch()
        dvl.addWidget(_lbl("Select your device", 15, "#CCC"))
        dvl.addSpacing(4)
        dvl.addWidget(_lbl(
            "Pick the device closest to yours. This sets the display resolution, "
            "refresh rate, and controller profile group.",
            13, C_DIM, align=Qt.AlignLeft))
        dvl.addSpacing(12)

        dev_cols = QHBoxLayout(); dev_cols.setSpacing(20)

        # Left column: Lenovo
        col_lenovo = QVBoxLayout(); col_lenovo.setSpacing(10)
        col_lenovo.addWidget(_lbl("Lenovo", 12, C_TREY, bold=True))
        for dev_key in ("legion_go", "legion_go_s", "legion_go_2"):
            b = _btn(DEVICES[dev_key]["label"], C_DARK_BTN, h=48)
            b.clicked.connect(lambda checked, k=dev_key: self._pick_device(k))
            col_lenovo.addWidget(b)
        dev_cols.addLayout(col_lenovo)

        # Middle column: ASUS
        col_asus = QVBoxLayout(); col_asus.setSpacing(10)
        col_asus.addWidget(_lbl("ASUS", 12, C_TREY, bold=True))
        for dev_key in ("rog_ally", "rog_ally_x", "xbox_ally_x"):
            b = _btn(DEVICES[dev_key]["label"], C_DARK_BTN, h=48)
            b.clicked.connect(lambda checked, k=dev_key: self._pick_device(k))
            col_asus.addWidget(b)
        dev_cols.addLayout(col_asus)

        # Right column: MSI + PC
        col_right = QVBoxLayout(); col_right.setSpacing(10)
        col_right.addWidget(_lbl("MSI", 12, C_TREY, bold=True))
        msi_btn = _btn(DEVICES["msi_claw_8"]["label"], C_DARK_BTN, h=48)
        msi_btn.clicked.connect(lambda: self._pick_device("msi_claw_8"))
        col_right.addWidget(msi_btn)
        col_right.addSpacing(10)
        col_right.addWidget(_lbl("Other", 12, C_TREY, bold=True))
        pc_btn = _btn("PC", C_DARK_BTN, h=48)
        pc_btn.clicked.connect(lambda: self._pick_device("general_pc"))
        col_right.addWidget(pc_btn)
        dev_cols.addLayout(col_right)

        dvl.addLayout(dev_cols)
        dvl.addSpacing(40)
        main_lay.addWidget(self._device_section)

        # ── 4. Gyro section ───────────────────────────────────────────────
        self._gyro_section = QWidget(); self._gyro_section.setVisible(False)
        gl = QVBoxLayout(self._gyro_section)
        gl.setContentsMargins(80, 60, 80, 60); gl.setSpacing(16)
        self._back_device_gyro_btn = _btn("← Back", C_DARK_BTN, size=10, h=30)
        self._back_device_gyro_btn.setFixedWidth(80)
        self._back_device_gyro_btn.clicked.connect(self._back_to_device_from_gyro)
        brow3 = QHBoxLayout(); brow3.addWidget(self._back_device_gyro_btn); brow3.addStretch()
        gl.addLayout(brow3)
        gl.addSpacing(40)
        _title_block(gl)
        gl.addStretch()
        gl.addWidget(_lbl("Do you want gyro aiming?", 15, "#CCC"))
        gl.addSpacing(12)
        grow = QHBoxLayout(); grow.setSpacing(20)
        gyro_yes = _btn("Yes", C_IW, h=56)
        gyro_no  = _btn("No",  C_DARK_BTN, h=56)
        gyro_yes.clicked.connect(self._gyro_yes)
        gyro_no.clicked.connect(lambda: self._pick_gyro("off"))
        grow.addWidget(gyro_yes); grow.addWidget(gyro_no)
        gl.addLayout(grow)
        gl.addSpacing(40)
        main_lay.addWidget(self._gyro_section)

        # ── 4b. Gyro mode section (shown after Yes) ───────────────────────
        self._gyro_mode_section = QWidget(); self._gyro_mode_section.setVisible(False)
        gml = QVBoxLayout(self._gyro_mode_section)
        gml.setContentsMargins(80, 60, 80, 60); gml.setSpacing(16)
        self._back_gyro_mode_btn = _btn("← Back", C_DARK_BTN, size=10, h=30)
        self._back_gyro_mode_btn.setFixedWidth(80)
        self._back_gyro_mode_btn.clicked.connect(self._back_to_gyro_from_mode)
        brow3b = QHBoxLayout(); brow3b.addWidget(self._back_gyro_mode_btn); brow3b.addStretch()
        gml.addLayout(brow3b)
        gml.addSpacing(40)
        _title_block(gml)
        gml.addStretch()
        gml.addWidget(_lbl("How should gyro activate?", 15, "#CCC"))
        gml.addSpacing(4)
        self._gyro_mode_desc_lbl = _lbl("", 13, C_DIM, align=Qt.AlignLeft)
        gml.addWidget(self._gyro_mode_desc_lbl)
        gml.addSpacing(12)
        gmrow = QHBoxLayout(); gmrow.setSpacing(20)
        gyro_ads    = _btn("ADS",    C_IW, h=56)
        gyro_hold   = _btn("Hold",   C_IW, h=56)
        gyro_toggle = _btn("Toggle", C_IW, h=56)
        gyro_ads.clicked.connect(lambda: self._pick_gyro("on"))
        gyro_hold.clicked.connect(lambda: self._pick_gyro("hold"))
        gyro_toggle.clicked.connect(lambda: self._pick_gyro("toggle"))
        gmrow.addWidget(gyro_ads); gmrow.addWidget(gyro_hold); gmrow.addWidget(gyro_toggle)
        self._gyro_hold_btn   = gyro_hold
        self._gyro_toggle_btn = gyro_toggle
        gml.addLayout(gmrow)
        gml.addSpacing(40)
        main_lay.addWidget(self._gyro_mode_section)

        # ── 5. Player name section ────────────────────────────────────────
        self._name_section = QWidget(); self._name_section.setVisible(False)
        nl = QVBoxLayout(self._name_section)
        nl.setContentsMargins(80, 60, 80, 60); nl.setSpacing(16)
        self._back_gyro_name_btn = _btn("← Back", C_DARK_BTN, size=10, h=30)
        self._back_gyro_name_btn.setFixedWidth(80)
        self._back_gyro_name_btn.clicked.connect(self._back_to_gyro_from_name)
        brow4 = QHBoxLayout(); brow4.addWidget(self._back_gyro_name_btn); brow4.addStretch()
        nl.addLayout(brow4)
        nl.addSpacing(40)
        _title_block(nl)
        nl.addStretch()
        nl.addWidget(_lbl("What's your player name?", 15, "#CCC"))
        nl.addSpacing(4)
        nl.addWidget(_lbl(
            "This is your in-game name for most mod clients: CoD4x, IW4x, "
            "AlterWare (Ghosts, AW), T7X, and Plutonium (LCD offline mode). "
            "Your Steam display name is filled in by default. Change it to whatever you want.",
            13, C_DIM, align=Qt.AlignLeft))
        nl.addSpacing(12)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Player")
        self._name_input.setMaxLength(32)
        self._name_input.setFixedHeight(48)
        self._name_input.setFont(font(14))
        self._name_input.setStyleSheet(
            f"QLineEdit{{background:{C_CARD};color:#FFF;border:2px solid #33333F;"
            f"border-radius:8px;padding:0 16px;}}"
            f"QLineEdit:focus{{border-color:{C_IW};}}"
        )
        nl.addWidget(self._name_input)
        nl.addSpacing(16)
        name_cont = _btn("Continue >>", C_IW, h=52)
        name_cont.setFixedWidth(260)
        name_cont.clicked.connect(self._save_player_name)
        nc_row = QHBoxLayout(); nc_row.addStretch(); nc_row.addWidget(name_cont); nc_row.addStretch()
        nl.addLayout(nc_row)
        nl.addSpacing(40)
        main_lay.addWidget(self._name_section)

        # ── 6. Game source section (merged from SourceScreen) ─────────────
        self._source_section = QWidget(); self._source_section.setVisible(False)
        sl = QVBoxLayout(self._source_section)
        sl.setContentsMargins(80, 60, 80, 60); sl.setSpacing(16)
        self._back_name_source_btn = _btn("← Back", C_DARK_BTN, size=10, h=30)
        self._back_name_source_btn.setFixedWidth(80)
        self._back_name_source_btn.clicked.connect(self._back_to_name_from_source)
        brow5 = QHBoxLayout(); brow5.addWidget(self._back_name_source_btn); brow5.addStretch()
        sl.addLayout(brow5)
        sl.addSpacing(40)
        _title_block(sl)
        sl.addStretch()
        sl.addWidget(_lbl("How did you install your games?", 15, "#CCC"))
        sl.addSpacing(8)

        cards = QHBoxLayout(); cards.setSpacing(20)

        steam_card = QFrame()
        steam_card.setStyleSheet(
            f"QFrame{{background:{C_CARD};border:2px solid #33333F;border-radius:10px;}}"
            f"QLabel{{background:transparent;}}")
        sc = QVBoxLayout(steam_card); sc.setContentsMargins(24, 24, 24, 24); sc.setSpacing(10)
        rec = QPushButton("RECOMMENDED"); rec.setFont(font(9, True)); rec.setFixedHeight(24)
        rec.setEnabled(False)
        rec.setStyleSheet(
            f"QPushButton{{background:{C_IW};color:#FFF;border:none;border-radius:5px;padding:0 10px;}}"
            f"QPushButton:disabled{{background:{C_IW};color:#FFF;}}")
        sc.addWidget(rec, alignment=Qt.AlignLeft)
        sc.addWidget(_lbl("Steam", 18, "#FFF", bold=True, align=Qt.AlignLeft, wrap=False))
        sc.addWidget(_lbl(
            "Your games were purchased and installed through Steam. "
            "DeckOps will detect them automatically.",
            12, C_DIM, align=Qt.AlignLeft))
        sc.addWidget(_lbl("Works with games on internal storage or SD card.",
                          11, "#555568", align=Qt.AlignLeft))
        sc.addStretch()
        steam_btn = _btn("Select Steam >>", C_IW, h=44)
        steam_btn.clicked.connect(lambda: self._pick_source("steam"))
        sc.addWidget(steam_btn)
        cards.addWidget(steam_card)

        own_card = QFrame()
        own_card.setStyleSheet(
            f"QFrame{{background:{C_CARD};border:2px solid #33333F;border-radius:10px;}}"
            f"QLabel{{background:transparent;}}")
        oc = QVBoxLayout(own_card); oc.setContentsMargins(24, 24, 24, 24); oc.setSpacing(10)
        adv = QPushButton("ADVANCED"); adv.setFont(font(9, True)); adv.setFixedHeight(24)
        adv.setEnabled(False)
        adv.setStyleSheet(
            f"QPushButton{{background:{C_TREY};color:#FFF;border:none;border-radius:5px;padding:0 10px;}}"
            f"QPushButton:disabled{{background:{C_TREY};color:#FFF;}}")
        oc.addWidget(adv, alignment=Qt.AlignLeft)
        oc.addWidget(_lbl("Steam & Non-Steam", 18, "#FFF", bold=True, align=Qt.AlignLeft, wrap=False))
        oc.addWidget(_lbl(
            "You have games from the Microsoft Store, CD, GOG, or other storefronts. "
            "Steam games are also detected automatically.",
            12, C_DIM, align=Qt.AlignLeft))
        oc.addWidget(_lbl("Make sure your non-Steam games are in /home/deck/games before continuing.",
                          11, "#555568", align=Qt.AlignLeft))
        oc.addStretch()
        own_btn = _btn("Select Steam & Non-Steam >>", C_TREY, h=44)
        own_btn.clicked.connect(lambda: self._pick_source("own"))
        oc.addWidget(own_btn)
        cards.addWidget(own_card)

        sl.addLayout(cards)
        sl.addSpacing(40)
        main_lay.addWidget(self._source_section)

        # ── 7. Primary controller section (Bazzite + General PC) ──────────
        # Bazzite doesn't have InputPlumber wired up yet, so Neptune templates
        # won't work. User must pick their controller type for all modes.
        # General PC users also need to pick their controller.
        self._primary_controller_section = QWidget()
        self._primary_controller_section.setVisible(False)
        pcl = QVBoxLayout(self._primary_controller_section)
        pcl.setContentsMargins(80, 60, 80, 60); pcl.setSpacing(16)
        self._back_source_ctrl_btn = _btn("← Back", C_DARK_BTN, size=10, h=30)
        self._back_source_ctrl_btn.setFixedWidth(80)
        self._back_source_ctrl_btn.clicked.connect(self._back_to_source_from_ctrl)
        brow6 = QHBoxLayout(); brow6.addWidget(self._back_source_ctrl_btn); brow6.addStretch()
        pcl.addLayout(brow6)
        pcl.addSpacing(40)
        _title_block(pcl)
        pcl.addStretch()
        self._ctrl_title_lbl = _lbl("What controller do you use?", 15, "#CCC")
        pcl.addWidget(self._ctrl_title_lbl)
        pcl.addSpacing(4)
        self._ctrl_desc_lbl = _lbl(
            "PlayStation:  PS5 or PS4 DualShock/DualSense. Includes gyro aiming.\n"
            "Xbox:  Xbox 360, Xbox One, or Xbox Elite. Standard layout, no gyro.\n"
            "Steam Controller:  Steam Controller 2 (Triton). Dual trackpads, gyro, 4 back buttons.\n"
            "Other:  Generic or 8BitDo controller. Standard layout, no gyro.",
            13, C_DIM, align=Qt.AlignLeft)
        pcl.addWidget(self._ctrl_desc_lbl)
        pcl.addSpacing(12)
        pcrow = QHBoxLayout(); pcrow.setSpacing(20)
        for ctrl_key, label in [("playstation", "PlayStation"), ("xbox", "Xbox"), ("steamcontroller", "Steam Controller"), ("other", "Other")]:
            b = _btn(label, C_DARK_BTN, h=56)
            b.clicked.connect(lambda checked, k=ctrl_key: self._pick_primary_controller(k))
            pcrow.addWidget(b)
        pcl.addLayout(pcrow)
        pcl.addSpacing(40)
        main_lay.addWidget(self._primary_controller_section)

        # ── 8. Resolution section (General PC, or docked) ─────────────────
        self._resolution_section = QWidget(); self._resolution_section.setVisible(False)
        rl = QVBoxLayout(self._resolution_section)
        rl.setContentsMargins(80, 60, 80, 60); rl.setSpacing(16)
        self._back_res_btn = _btn("← Back", C_DARK_BTN, size=10, h=30)
        self._back_res_btn.setFixedWidth(80)
        self._back_res_btn.clicked.connect(self._back_to_prev_from_res)
        brow_res = QHBoxLayout(); brow_res.addWidget(self._back_res_btn); brow_res.addStretch()
        rl.addLayout(brow_res)
        rl.addSpacing(40)
        _title_block(rl)
        rl.addStretch()
        self._res_title_lbl = _lbl("What resolution is your display?", 15, "#CCC")
        rl.addWidget(self._res_title_lbl)
        rl.addSpacing(4)
        rl.addWidget(_lbl(
            "Pick the resolution that matches your monitor or TV, "
            "or choose My Own to set it yourself in-game.",
            13, C_DIM, align=Qt.AlignLeft))
        rl.addSpacing(12)

        res_cols = QHBoxLayout(); res_cols.setSpacing(20)
        col_1610 = QVBoxLayout(); col_1610.setSpacing(10)
        col_1610.addWidget(_lbl("16:10", 13, C_IW, bold=True))
        for res_key, label in [("1280x800", "1280 x 800"), ("1920x1200", "1920 x 1200")]:
            b = _btn(label, C_DARK_BTN, h=52)
            b.clicked.connect(lambda checked, k=res_key: self._pick_resolution(k))
            col_1610.addWidget(b)
        res_cols.addLayout(col_1610)

        col_169 = QVBoxLayout(); col_169.setSpacing(10)
        col_169.addWidget(_lbl("16:9", 13, C_IW, bold=True))
        for res_key, label in [("1280x720", "1280 x 720"), ("1920x1080", "1920 x 1080")]:
            b = _btn(label, C_DARK_BTN, h=52)
            b.clicked.connect(lambda checked, k=res_key: self._pick_resolution(k))
            col_169.addWidget(b)
        res_cols.addLayout(col_169)

        rl.addLayout(res_cols)
        rl.addSpacing(8)
        own_res = _btn("My Own", C_DARK_BTN, h=44)
        own_res.setFixedWidth(200)
        own_res.clicked.connect(lambda: self._pick_resolution("own"))
        own_row = QHBoxLayout(); own_row.addStretch(); own_row.addWidget(own_res); own_row.addStretch()
        rl.addLayout(own_row)
        rl.addSpacing(40)
        main_lay.addWidget(self._resolution_section)

        # ── 9. Play mode section (handhelds only, not General PC) ─────────
        self._play_section = QWidget(); self._play_section.setVisible(False)
        pl = QVBoxLayout(self._play_section)
        pl.setContentsMargins(80, 60, 80, 60); pl.setSpacing(16)
        self._back_play_btn = _btn("← Back", C_DARK_BTN, size=10, h=30)
        self._back_play_btn.setFixedWidth(80)
        self._back_play_btn.clicked.connect(self._back_to_prev_from_play)
        brow_play = QHBoxLayout(); brow_play.addWidget(self._back_play_btn); brow_play.addStretch()
        pl.addLayout(brow_play)
        pl.addSpacing(40)
        _title_block(pl)
        pl.addStretch()
        pl.addWidget(_lbl("How do you play?", 15, "#CCC"))
        pl.addSpacing(4)
        pl.addWidget(_lbl(
            "Handheld Only:  you play exclusively on the device screen.\n"
            "Also Docked:  you also connect to a TV or monitor with an external controller.\n"
            "Choosing Docked will install the DeckOps Decky plugin. "
            "Decky Loader is required, you can install it after setup from decky.xyz.",
            13, C_DIM, align=Qt.AlignLeft))
        pl.addSpacing(12)
        prow = QHBoxLayout(); prow.setSpacing(20)
        hh_btn = _btn("Handheld Only", C_DARK_BTN, h=56)
        dk_btn = _btn("Also Docked",   C_DARK_BTN, h=56)
        hh_btn.clicked.connect(lambda: self._pick_play_mode("handheld"))
        dk_btn.clicked.connect(lambda: self._pick_play_mode("docked"))
        prow.addWidget(hh_btn); prow.addWidget(dk_btn)
        pl.addLayout(prow)
        pl.addSpacing(40)
        main_lay.addWidget(self._play_section)

        # ── 10. Decky install section (docked only) ───────────────────────
        self._decky_section = QWidget(); self._decky_section.setVisible(False)
        dl = QVBoxLayout(self._decky_section)
        dl.setContentsMargins(80, 60, 80, 60); dl.setSpacing(16)
        self._back_decky_btn = _btn("← Back", C_DARK_BTN, size=10, h=30)
        self._back_decky_btn.setFixedWidth(80)
        self._back_decky_btn.clicked.connect(self._back_to_play_from_decky)
        brow_dk = QHBoxLayout(); brow_dk.addWidget(self._back_decky_btn); brow_dk.addStretch()
        dl.addLayout(brow_dk)
        dl.addSpacing(40)
        _title_block(dl)
        dl.addStretch()
        self._decky_status_lbl = _lbl("Installing DeckOps Decky plugin...", 15, "#CCC")
        dl.addWidget(self._decky_status_lbl)
        dl.addSpacing(4)
        self._decky_log = QPlainTextEdit()
        self._decky_log.setReadOnly(True)
        self._decky_log.setFont(font(11))
        self._decky_log.setStyleSheet(
            "QPlainTextEdit{color:#666677;background:transparent;border:none;padding:10px;}")
        self._decky_log.setFixedHeight(180)
        dl.addWidget(self._decky_log)

        self._decky_cont_btn = _btn("Continue  >>", C_IW, size=13, h=52)
        self._decky_cont_btn.setFixedWidth(320); self._decky_cont_btn.setVisible(False)
        self._decky_cont_btn.clicked.connect(self._decky_continue)
        dcw = QHBoxLayout(); dcw.addStretch(); dcw.addWidget(self._decky_cont_btn); dcw.addStretch()
        dl.addLayout(dcw)

        self._decky_retry_btn = _btn("Retry", C_TREY, size=13, h=52)
        self._decky_retry_btn.setFixedWidth(320); self._decky_retry_btn.setVisible(False)
        self._decky_retry_btn.clicked.connect(self._start_decky_install)
        drw = QHBoxLayout(); drw.addStretch(); drw.addWidget(self._decky_retry_btn); drw.addStretch()
        dl.addLayout(drw)

        dl.addSpacing(40)
        main_lay.addWidget(self._decky_section)

        self._decky_sigs = _Sigs()
        self._decky_sigs.log.connect(self._decky_append_log)
        self._decky_sigs.done.connect(self._decky_on_done)

        # ── 11. Docked external controller section ────────────────────────
        # Only shown for docked users on SteamOS/CachyOS who haven't already
        # picked a controller (Bazzite/PC users already picked in step 7).
        self._docked_controller_section = QWidget()
        self._docked_controller_section.setVisible(False)
        dcl = QVBoxLayout(self._docked_controller_section)
        dcl.setContentsMargins(80, 60, 80, 60); dcl.setSpacing(16)
        self._back_docked_ctrl_btn = _btn("← Back", C_DARK_BTN, size=10, h=30)
        self._back_docked_ctrl_btn.setFixedWidth(80)
        self._back_docked_ctrl_btn.clicked.connect(self._back_to_resolution_from_docked_ctrl)
        brow_dc = QHBoxLayout(); brow_dc.addWidget(self._back_docked_ctrl_btn); brow_dc.addStretch()
        dcl.addLayout(brow_dc)
        dcl.addSpacing(40)
        _title_block(dcl)
        dcl.addStretch()
        dcl.addWidget(_lbl("What external controller do you use?", 15, "#CCC"))
        dcl.addSpacing(4)
        dcl.addWidget(_lbl(
            "PlayStation:  PS5 or PS4 DualShock/DualSense. Includes gyro aiming.\n"
            "Xbox:  Xbox 360, Xbox One, or Xbox Elite. Standard layout, no gyro.\n"
            "Steam Controller:  Steam Controller 2 (Triton). Dual trackpads, gyro, 4 back buttons.\n"
            "Other:  Generic or 8BitDo controller. Standard layout, no gyro.",
            13, C_DIM, align=Qt.AlignLeft))
        dcl.addSpacing(12)
        dcrow = QHBoxLayout(); dcrow.setSpacing(20)
        for ctrl_key, label in [("playstation", "PlayStation"), ("xbox", "Xbox"), ("steamcontroller", "Steam Controller"), ("other", "Other")]:
            b = _btn(label, C_DARK_BTN, h=56)
            b.clicked.connect(lambda checked, k=ctrl_key: self._pick_docked_controller(k))
            dcrow.addWidget(b)
        dcl.addLayout(dcrow)
        dcl.addSpacing(40)
        main_lay.addWidget(self._docked_controller_section)

    # ── Section visibility helpers ────────────────────────────────────────

    def _hide_all(self):
        for attr in dir(self):
            if attr.endswith("_section") and hasattr(getattr(self, attr), "setVisible"):
                getattr(self, attr).setVisible(False)

    def _show(self, section_name):
        self._hide_all()
        getattr(self, section_name).setVisible(True)

    # ── Navigation logic ─────────────────────────────────────────────────

    def _pick_os(self, os_key):
        self._selected_os = os_key
        cfg.set_os_type(os_key)
        if os_key in ("bazzite", "cachyos"):
            # Non-SteamOS users are always on Other devices — skip model screen
            self._show("_device_section")
        else:
            self._show("_model_section")

    def _back_to_os(self):
        self._show("_os_section")

    def _pick_device(self, dev_key):
        self._selected_device = dev_key
        dev = DEVICES[dev_key]
        self._is_general_pc = (dev_key == "general_pc")
        self._is_steam_machine = (dev_key == "steam_machine")

        # Save device config
        cfg.set_deck_model(dev["deck_model"])
        if dev["other_device"]:
            cfg.set_other_device(dev["other_device"])
        if dev["other_device_type"]:
            cfg.set_other_device_type(dev["other_device_type"])

        # Next: gyro (if device has it) or name
        if dev["has_gyro"]:
            self._show_gyro_section(dev_key)
        else:
            cfg.set_gyro_mode("off")
            self._show_name_section()

    def _show_device_picker(self):
        self._show("_device_section")

    def _back_to_model(self):
        if self._selected_os in ("bazzite", "cachyos"):
            # Non-SteamOS users skipped the model screen — go back to OS
            self._show("_os_section")
        else:
            self._show("_model_section")

    def _show_gyro_section(self, dev_key):
        """Show the Yes/No gyro question."""
        self._show("_gyro_section")

    def _back_to_device_from_gyro(self):
        dev = DEVICES.get(self._selected_device, {})
        if self._selected_os in ("bazzite", "cachyos"):
            # Non-SteamOS users always came from the device picker
            self._show("_device_section")
        elif dev.get("deck_model") in ("lcd", "oled", "steam_machine"):
            self._show("_model_section")
        else:
            self._show("_device_section")

    def _gyro_yes(self):
        """User wants gyro — show the mode picker.

        Steam Deck LCD/OLED and Steam Machine: 3 options (ADS, Hold, Toggle)
        All other devices:   skip mode picker, apply 'on' (ADS) directly
        """
        has_full_modes = self._selected_device in ("sd_lcd", "sd_oled", "steam_machine")
        if not has_full_modes:
            # Non-SD/SM devices only support ADS mode
            self._pick_gyro("on")
            return
        # SD/SM: show mode picker with Hold/Toggle visible
        self._gyro_hold_btn.setVisible(True)
        self._gyro_toggle_btn.setVisible(True)
        self._gyro_mode_desc_lbl.setText(
            "ADS:  gyro activates when you aim down sights (left trigger).\n"
            "Hold:  gyro active while holding L5.\n"
            "Toggle:  press L5 to toggle gyro on and off."
        )
        self._show("_gyro_mode_section")

    def _back_to_gyro_from_mode(self):
        self._show("_gyro_section")

    def _pick_gyro(self, mode):
        cfg.set_gyro_mode(mode)
        self._show_name_section()

    def _back_to_gyro_from_name(self):
        dev = DEVICES.get(self._selected_device, {})
        if not dev.get("has_gyro"):
            # No gyro section to go back to, go to device
            self._back_to_device_from_gyro()
            return
        # If the user picked a mode (ADS/Hold/Toggle) they came through
        # the mode picker — go back there. If they picked "off" (No) they
        # skipped it — go back to the Yes/No screen.
        gyro = cfg.get_gyro_mode()
        has_full_modes = self._selected_device in ("sd_lcd", "sd_oled", "steam_machine")
        if gyro != "off" and has_full_modes:
            self._show("_gyro_mode_section")
        else:
            self._show("_gyro_section")

    def _show_name_section(self):
        """Show the player name input, pre-filled with Steam display name."""
        if not self._name_input.text():
            saved = cfg.get_player_name()
            if saved:
                self._name_input.setText(saved)
            else:
                steam_name = cfg.get_steam_display_name()
                if steam_name:
                    self._name_input.setText(steam_name)
        self._show("_name_section")

    def _save_player_name(self):
        name = self._name_input.text().strip()
        cfg.set_player_name(name if name else "Player")
        if self._allows_source_choice():
            self._show("_source_section")
        else:
            # Forced advanced — auto-set source and continue
            cfg.set_game_source("own")
            self._pick_source("own")

    def _allows_source_choice(self):
        """Only SteamOS users on LCD, OLED, or Steam Machine get the source picker."""
        return (self._selected_os == "steamos"
                and self._selected_device in ("sd_lcd", "sd_oled", "steam_machine"))

    def _back_to_name_from_source(self):
        self._show("_name_section")

    def _pick_source(self, source):
        cfg.set_game_source(source)
        # Routing depends on OS and device
        if self._needs_primary_controller():
            self._show("_primary_controller_section")
        elif self._is_steam_machine:
            # Steam Machine: need resolution, no controller or play mode
            self._res_title_lbl.setText("What resolution is your display?")
            self._show("_resolution_section")
        elif self._is_general_pc:
            # PC: go to resolution, then controller
            self._res_title_lbl.setText("What resolution is your display?")
            self._show("_resolution_section")
        else:
            # SteamOS/CachyOS handheld: play mode
            self._show("_play_section")

    def _needs_primary_controller(self):
        """Bazzite and General PC users need to pick their controller type."""
        return self._selected_os == "bazzite" or self._is_general_pc

    def _back_to_source_from_ctrl(self):
        if self._allows_source_choice():
            self._show("_source_section")
        else:
            # Forced advanced skipped the source screen — back to name
            self._show("_name_section")

    def _pick_primary_controller(self, ctrl_type):
        cfg.set_external_controller(ctrl_type)
        if self._is_general_pc:
            # PC: need resolution
            self._res_title_lbl.setText("What resolution is your display?")
            self._show("_resolution_section")
        else:
            # Bazzite handheld: play mode
            self._show("_play_section")

    def _back_to_prev_from_play(self):
        """Back from play mode goes to controller (Bazzite), source (SteamOS with source choice), or name (forced advanced)."""
        if self._needs_primary_controller():
            self._show("_primary_controller_section")
        elif self._allows_source_choice():
            self._show("_source_section")
        else:
            self._show("_name_section")

    def _pick_play_mode(self, mode):
        cfg.set_play_mode(mode)
        if mode == "docked":
            self._show("_decky_section")
            self._decky_log.clear()
            self._decky_cont_btn.setVisible(False)
            self._decky_retry_btn.setVisible(False)
            self._decky_status_lbl.setText("Installing DeckOps Decky plugin...")
            self._back_decky_btn.setEnabled(False)
            self._start_decky_install()
        else:
            self._finish()

    # ── Decky install ─────────────────────────────────────────────────────

    def _back_to_play_from_decky(self):
        self._show("_play_section")

    def _decky_append_log(self, text):
        self._decky_log.appendPlainText(text)
        self._decky_log.verticalScrollBar().setValue(
            self._decky_log.verticalScrollBar().maximum())

    def _decky_on_done(self, ok):
        self._back_decky_btn.setEnabled(True)
        if ok:
            self._decky_status_lbl.setText("✓  Decky plugin installed.")
            self._decky_cont_btn.setVisible(True)
        else:
            self._decky_status_lbl.setText("✗  Install failed. Check your connection and retry.")
            self._decky_retry_btn.setVisible(True)

    def _decky_continue(self):
        # Docked: need resolution
        self._res_title_lbl.setText("What resolution is your external display?")
        self._show("_resolution_section")

    def _start_decky_install(self):
        self._decky_cont_btn.setVisible(False)
        self._decky_retry_btn.setVisible(False)
        self._back_decky_btn.setEnabled(False)
        self._decky_status_lbl.setText("Installing DeckOps Decky plugin...")
        s = self._decky_sigs

        def _run():
            import urllib.request
            ZIP_URL  = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/raw/main/DeckOps.zip"
            dl_dir   = os.path.expanduser("~/Downloads")
            zip_path = os.path.join(dl_dir, "DeckOps.zip")
            try:
                os.makedirs(dl_dir, exist_ok=True)
                s.log.emit("→  Downloading DeckOps.zip...")
                urllib.request.urlretrieve(ZIP_URL, zip_path)
                s.log.emit(f"   ✓  Saved to {zip_path}")
                s.log.emit("   Install via Decky → Install from zip.")
                s.done.emit(True)
            except Exception as ex:
                s.log.emit(f"✗  {ex}")
                s.done.emit(False)

        threading.Thread(target=_run, daemon=True).start()

    # ── Resolution ────────────────────────────────────────────────────────

    def _back_to_prev_from_res(self):
        if self._is_steam_machine:
            if self._allows_source_choice():
                self._show("_source_section")
            else:
                self._show("_name_section")
        elif self._is_general_pc:
            # PC: back to controller
            self._show("_primary_controller_section")
        else:
            # Docked: back to decky/play
            self._show("_decky_section")

    def _pick_resolution(self, resolution):
        if self._is_steam_machine:
            # Steam Machine: store resolution in other_device for config dir resolution
            cfg.set_other_device(resolution)
            self._finish()
            return
        cfg.set_docked_resolution(resolution)
        if self._is_general_pc:
            # PC already picked controller — done
            self._finish()
        elif not cfg.get_external_controller():
            # Docked SteamOS/CachyOS: need external controller
            self._show("_docked_controller_section")
        else:
            # Bazzite docked: already picked controller
            self._finish()

    # ── Docked external controller (SteamOS/CachyOS only) ────────────────

    def _back_to_resolution_from_docked_ctrl(self):
        self._show("_resolution_section")

    def _pick_docked_controller(self, ctrl_type):
        cfg.set_external_controller(ctrl_type)
        self._finish()

    # ── Finish ────────────────────────────────────────────────────────────

    def _finish(self):
        """Route to the correct next screen based on game_source."""
        source = cfg.get_game_source() or "steam"
        if source == "own":
            go_to(self.stack, "OwnScanScreen")
        else:
            go_to(self.stack, "WelcomeScreen")
