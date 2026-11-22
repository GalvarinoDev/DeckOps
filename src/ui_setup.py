"""
ui_setup.py: first-run setup flow for DeckOps

Flow: [Autodetect Confirm] → OS → Device → Gyro → Name → [Controller] → [Play Mode / Resolution] → Done

When DMI and os-release give both the OS and the device, a confirm screen
lets the user accept with one click or go through the manual flow. Every
OS goes through the model screen, so a Deck on Bazzite or CachyOS can
still pick LCD or OLED.
"""

from qt import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit
from qt import Qt

import config as cfg
from detect_hw import detect_os, detect_device

from ui_constants import (
    C_CARD, C_IW, C_TREY, C_DIM, C_DARK_BTN,
    font, _btn, _lbl, _title_block, _back_row,
    go_to,
)


# --- Device definitions
#
# Each device maps to: deck_model, other_device (resolution key),
# other_device_type (controller template group), has_gyro.

DEVICES = {
    "sd_lcd":       {"label": "Steam Deck LCD",       "deck_model": "lcd",   "other_device": None,              "other_device_type": None,         "has_gyro": True},
    "sd_oled":      {"label": "Steam Deck OLED",      "deck_model": "oled",  "other_device": None,              "other_device_type": None,         "has_gyro": True},
    "legion_go":    {"label": "Lenovo Legion Go",     "deck_model": "other", "other_device": "1920x1200",       "other_device_type": "legion_go",  "has_gyro": True},
    "legion_go_s":  {"label": "Lenovo Legion Go S",   "deck_model": "other", "other_device": "1920x1200",       "other_device_type": "legion_go_s","has_gyro": True},
    "legion_go_2":  {"label": "Lenovo Legion Go 2",   "deck_model": "other", "other_device": "1920x1200_144hz", "other_device_type": "legion_go_2","has_gyro": True},
    "rog_ally":     {"label": "ROG Ally",              "deck_model": "other", "other_device": "1920x1080",       "other_device_type": "2btn",       "has_gyro": True},
    "rog_ally_x":   {"label": "ROG Ally X",            "deck_model": "other", "other_device": "1920x1080",       "other_device_type": "2btn",       "has_gyro": True},
    "xbox_ally_x":  {"label": "ROG Xbox Ally X",       "deck_model": "other", "other_device": "1920x1080",       "other_device_type": "2btn",       "has_gyro": True},
    "msi_claw_8":   {"label": "MSI Claw 8",           "deck_model": "other", "other_device": "1920x1200",       "other_device_type": "2btn",       "has_gyro": True},
    "rp6":          {"label": "Retroid Pocket 6",     "deck_model": "other", "other_device": "1920x1080",       "other_device_type": "generic",    "has_gyro": False},
    "general_pc":   {"label": "PC",                    "deck_model": "other", "other_device": None,              "other_device_type": "generic",    "has_gyro": True},
    "steam_machine":{"label": "Steam Machine",         "deck_model": "steam_machine", "other_device": None,  "other_device_type": "steam_machine", "has_gyro": True},
}


class SetupFlowScreen(QWidget):
    """
    The whole first-run setup in one QWidget. Each step is a section that
    is shown or hidden in turn. screen_name = "SetupFlowScreen".
    """

    def __init__(self, stack):
        super().__init__()
        self.stack = stack
        self.screen_name = "SetupFlowScreen"
        self._selected_os = None      # "steamos", "bazzite", "cachyos", "other_linux"
        self._selected_device = None  # key from DEVICES
        self._is_general_pc = False
        self._is_steam_machine = False

        self._autodetected = False

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)

        # --- 0. Autodetect confirm section
        self._detected_os = detect_os()
        self._detected_device = detect_device() or ("general_pc" if self._detected_os else None)

        self._confirm_section = QWidget(); self._confirm_section.setVisible(False)
        cl = QVBoxLayout(self._confirm_section)
        cl.setContentsMargins(80, 60, 80, 60); cl.setSpacing(16)
        _title_block(cl)
        cl.addSpacing(8)
        cl.addWidget(_lbl(
            "DeckOps sets up community multiplayer clients for your Call of Duty games, "
            "so you can play online with the best possible performance.",
            14, "#CCCCCC"))
        cl.addSpacing(6)
        for warn in [
            "⚠   DeckOps will automatically create Proton prefixes for your games. "
            "You do NOT need to launch each game through Steam first.",
            "⚠   If you plan to play Plutonium titles online (WaW, BO1, BO2, MW3), "
            "create a free Plutonium account at plutonium.pw before continuing.",
            "⚠   Make sure you have a stable internet connection before installing. "
            "If the install fails, don't re-run it repeatedly, join the Discord for help instead.",
        ]:
            cl.addWidget(_lbl(warn, 13, C_TREY, align=Qt.AlignmentFlag.AlignLeft))
        cl.addSpacing(16)
        os_label = {"steamos": "SteamOS", "bazzite": "Bazzite", "cachyos": "CachyOS", "armada": "Armada"}.get(
            self._detected_os, self._detected_os or "Unknown")
        dev_label = DEVICES.get(self._detected_device, {}).get("label", self._detected_device or "Unknown")
        self._confirm_lbl = _lbl(f"Detected {os_label} on {dev_label}. Is this correct?", 15, "#CCC")
        cl.addWidget(self._confirm_lbl)
        cl.addSpacing(12)
        crow = QHBoxLayout(); crow.setSpacing(20)
        yes_btn = _btn("Yes", C_IW, h=56)
        change_btn = _btn("Change", C_DARK_BTN, h=56)
        yes_btn.clicked.connect(self._accept_autodetect)
        change_btn.clicked.connect(self._reject_autodetect)
        crow.addWidget(yes_btn); crow.addWidget(change_btn)
        cl.addLayout(crow)
        cl.addSpacing(40)
        main_lay.addWidget(self._confirm_section)

        # --- 1. OS section
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
            lay.addWidget(_lbl(warn, 13, C_TREY, align=Qt.AlignmentFlag.AlignLeft))
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

        # --- 2. Device model section
        self._model_section = QWidget(); self._model_section.setVisible(False)
        ml = QVBoxLayout(self._model_section)
        ml.setContentsMargins(80, 60, 80, 60); ml.setSpacing(16)
        self._back_os_btn = _back_row(ml, self._back_to_os)
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

        # --- 3. Specific device picker (Other)
        self._device_section = QWidget(); self._device_section.setVisible(False)
        dvl = QVBoxLayout(self._device_section)
        dvl.setContentsMargins(80, 60, 80, 60); dvl.setSpacing(16)
        self._back_model_btn = _back_row(dvl, self._back_to_model)
        dvl.addSpacing(40)
        _title_block(dvl)
        dvl.addStretch()
        dvl.addWidget(_lbl("Select your device", 15, "#CCC"))
        dvl.addSpacing(4)
        dvl.addWidget(_lbl(
            "Pick the device closest to yours. This sets the display resolution, "
            "refresh rate, and controller profile group.",
            13, C_DIM, align=Qt.AlignmentFlag.AlignLeft))
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
        col_right.addWidget(_lbl("Retroid", 12, C_TREY, bold=True))
        rp6_btn = _btn(DEVICES["rp6"]["label"], C_DARK_BTN, h=48)
        rp6_btn.clicked.connect(lambda: self._pick_device("rp6"))
        col_right.addWidget(rp6_btn)
        col_right.addSpacing(10)
        col_right.addWidget(_lbl("Other", 12, C_TREY, bold=True))
        pc_btn = _btn("PC", C_DARK_BTN, h=48)
        pc_btn.clicked.connect(lambda: self._pick_device("general_pc"))
        col_right.addWidget(pc_btn)
        dev_cols.addLayout(col_right)

        dvl.addLayout(dev_cols)
        dvl.addSpacing(40)
        main_lay.addWidget(self._device_section)

        # --- 4. Gyro section
        self._gyro_section = QWidget(); self._gyro_section.setVisible(False)
        gl = QVBoxLayout(self._gyro_section)
        gl.setContentsMargins(80, 60, 80, 60); gl.setSpacing(16)
        self._back_device_gyro_btn = _back_row(gl, self._back_to_device_from_gyro)
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

        # --- 4b. Gyro mode section (shown after Yes)
        self._gyro_mode_section = QWidget(); self._gyro_mode_section.setVisible(False)
        gml = QVBoxLayout(self._gyro_mode_section)
        gml.setContentsMargins(80, 60, 80, 60); gml.setSpacing(16)
        self._back_gyro_mode_btn = _back_row(gml, self._back_to_gyro_from_mode)
        gml.addSpacing(40)
        _title_block(gml)
        gml.addStretch()
        gml.addWidget(_lbl("How should gyro activate?", 15, "#CCC"))
        gml.addSpacing(4)
        self._gyro_mode_desc_lbl = _lbl("", 13, C_DIM, align=Qt.AlignmentFlag.AlignLeft)
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

        # --- 5. Player name section
        self._name_section = QWidget(); self._name_section.setVisible(False)
        nl = QVBoxLayout(self._name_section)
        nl.setContentsMargins(80, 60, 80, 60); nl.setSpacing(16)
        self._back_gyro_name_btn = _back_row(nl, self._back_to_gyro_from_name)
        nl.addSpacing(40)
        _title_block(nl)
        nl.addStretch()
        nl.addWidget(_lbl("What's your player name?", 15, "#CCC"))
        nl.addSpacing(4)
        nl.addWidget(_lbl(
            "This is your in-game name for most mod clients: CoD4x, IW4x, "
            "and Plutonium (LCD offline mode). "
            "Your Steam display name is filled in by default. Change it to whatever you want.",
            13, C_DIM, align=Qt.AlignmentFlag.AlignLeft))
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

        # --- 6. Primary controller section (Bazzite + General PC)
        # Bazzite doesn't have InputPlumber wired up yet, so Neptune templates
        # don't work there and the user picks a controller type for every
        # play mode. General PC users pick one too.
        self._primary_controller_section = QWidget()
        self._primary_controller_section.setVisible(False)
        pcl = QVBoxLayout(self._primary_controller_section)
        pcl.setContentsMargins(80, 60, 80, 60); pcl.setSpacing(16)
        self._back_name_ctrl_btn = _back_row(pcl, self._back_to_name_from_ctrl)
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
            13, C_DIM, align=Qt.AlignmentFlag.AlignLeft)
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

        # --- 7. Resolution section (General PC, or docked)
        self._resolution_section = QWidget(); self._resolution_section.setVisible(False)
        rl = QVBoxLayout(self._resolution_section)
        rl.setContentsMargins(80, 60, 80, 60); rl.setSpacing(16)
        self._back_res_btn = _back_row(rl, self._back_to_prev_from_res)
        rl.addSpacing(40)
        _title_block(rl)
        rl.addStretch()
        self._res_title_lbl = _lbl("What resolution is your display?", 15, "#CCC")
        rl.addWidget(self._res_title_lbl)
        rl.addSpacing(4)
        rl.addWidget(_lbl(
            "Pick the resolution that matches your monitor or TV, "
            "or choose My Own to set it yourself in-game.",
            13, C_DIM, align=Qt.AlignmentFlag.AlignLeft))
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

        # --- 8. Play mode section (handhelds only, not General PC)
        self._play_section = QWidget(); self._play_section.setVisible(False)
        pl = QVBoxLayout(self._play_section)
        pl.setContentsMargins(80, 60, 80, 60); pl.setSpacing(16)
        self._back_play_btn = _back_row(pl, self._back_to_prev_from_play)
        pl.addSpacing(40)
        _title_block(pl)
        pl.addStretch()
        pl.addWidget(_lbl("How do you play?", 15, "#CCC"))
        pl.addSpacing(4)
        pl.addWidget(_lbl(
            "Handheld Only:  you play exclusively on the device screen.\n"
            "Also Docked:  you also connect to a TV or monitor with an external controller.",
            13, C_DIM, align=Qt.AlignmentFlag.AlignLeft))
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

        # --- 9. Docked external controller section
        # Only for docked users on SteamOS or CachyOS. Bazzite and PC users
        # already picked a controller in step 6.
        self._docked_controller_section = QWidget()
        self._docked_controller_section.setVisible(False)
        dcl = QVBoxLayout(self._docked_controller_section)
        dcl.setContentsMargins(80, 60, 80, 60); dcl.setSpacing(16)
        self._back_docked_ctrl_btn = _back_row(dcl, self._back_to_resolution_from_docked_ctrl)
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
            13, C_DIM, align=Qt.AlignmentFlag.AlignLeft))
        dcl.addSpacing(12)
        dcrow = QHBoxLayout(); dcrow.setSpacing(20)
        for ctrl_key, label in [("playstation", "PlayStation"), ("xbox", "Xbox"), ("steamcontroller", "Steam Controller"), ("other", "Other")]:
            b = _btn(label, C_DARK_BTN, h=56)
            b.clicked.connect(lambda checked, k=ctrl_key: self._pick_docked_controller(k))
            dcrow.addWidget(b)
        dcl.addLayout(dcrow)
        dcl.addSpacing(40)
        main_lay.addWidget(self._docked_controller_section)

        # Start on the confirm screen if both were detected, else on OS
        if self._detected_os and self._detected_device:
            self._os_section.setVisible(False)
            self._confirm_section.setVisible(True)

    # --- Section visibility helpers

    def _hide_all(self):
        for attr in dir(self):
            if attr.endswith("_section") and hasattr(getattr(self, attr), "setVisible"):
                getattr(self, attr).setVisible(False)

    def _show(self, section_name):
        self._hide_all()
        getattr(self, section_name).setVisible(True)

    # --- Navigation logic

    def _accept_autodetect(self):
        self._autodetected = True
        self._pick_os(self._detected_os)
        self._pick_device(self._detected_device)

    def _reject_autodetect(self):
        self._autodetected = False
        self._show("_os_section")

    def _pick_os(self, os_key):
        self._selected_os = os_key
        cfg.set_os_type(os_key)
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

        # Next is gyro if the device has it, else name
        if dev["has_gyro"]:
            self._show_gyro_section(dev_key)
        else:
            cfg.set_gyro_mode("off")
            self._show_name_section()

    def _show_device_picker(self):
        self._show("_device_section")

    def _back_to_model(self):
        self._show("_model_section")

    def _show_gyro_section(self, dev_key):
        """Show the Yes/No gyro question."""
        self._show("_gyro_section")

    def _back_to_device_from_gyro(self):
        if self._autodetected:
            self._show("_confirm_section")
            return
        dev = DEVICES.get(self._selected_device, {})
        if dev.get("deck_model") in ("lcd", "oled", "steam_machine"):
            self._show("_model_section")
        else:
            self._show("_device_section")

    def _gyro_yes(self):
        """User wants gyro.

        Steam Deck LCD/OLED and Steam Machine get the mode picker (ADS, Hold,
        Toggle). Other devices skip it and get 'on' (ADS) directly.
        """
        has_full_modes = self._selected_device in ("sd_lcd", "sd_oled", "steam_machine")
        if not has_full_modes:
            # Non-SD/SM devices only support ADS mode
            self._pick_gyro("on")
            return
        # Deck and Steam Machine: mode picker with Hold and Toggle shown
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
            # No gyro step to return to, so go back to the device step
            self._back_to_device_from_gyro()
            return
        # A picked mode (ADS/Hold/Toggle) means the user came through the
        # mode picker, so go back there. "off" (No) skipped it, so go back
        # to the Yes/No screen.
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
        cfg.set_game_source("both")
        if self._needs_primary_controller():
            self._show("_primary_controller_section")
        elif self._is_steam_machine:
            self._res_title_lbl.setText("What resolution is your display?")
            self._show("_resolution_section")
        elif self._is_general_pc:
            self._res_title_lbl.setText("What resolution is your display?")
            self._show("_resolution_section")
        else:
            self._show("_play_section")

    def _needs_primary_controller(self):
        """Bazzite and General PC users need to pick their controller type."""
        return self._selected_os == "bazzite" or self._is_general_pc

    def _back_to_name_from_ctrl(self):
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
        """Back from play mode goes to controller (Bazzite) or name."""
        if self._needs_primary_controller():
            self._show("_primary_controller_section")
        else:
            self._show("_name_section")

    def _pick_play_mode(self, mode):
        cfg.set_play_mode(mode)
        if mode == "docked":
            self._res_title_lbl.setText("What resolution is your external display?")
            self._show("_resolution_section")
        else:
            self._finish()

    # --- Resolution

    def _back_to_prev_from_res(self):
        if self._is_steam_machine:
            self._show("_name_section")
        elif self._is_general_pc:
            # PC: back to controller
            self._show("_primary_controller_section")
        else:
            # Docked: back to play mode
            self._show("_play_section")

    def _pick_resolution(self, resolution):
        if self._is_steam_machine:
            # Steam Machine keeps its resolution in other_device, which picks its config folder
            cfg.set_other_device(resolution)
            self._finish()
            return
        cfg.set_docked_resolution(resolution)
        if self._is_general_pc:
            # PC already picked a controller, so we're done
            self._finish()
        elif not self._needs_primary_controller():
            # Docked SteamOS/CachyOS: ask for the external controller
            self._show("_docked_controller_section")
        else:
            # Docked Bazzite already picked a controller
            self._finish()

    # --- Docked external controller (SteamOS/CachyOS only)

    def _back_to_resolution_from_docked_ctrl(self):
        self._show("_resolution_section")

    def _pick_docked_controller(self, ctrl_type):
        cfg.set_external_controller(ctrl_type)
        self._finish()

    # --- Finish

    def _finish(self):
        # The manifest mods step skips itself and goes to the game scan when there are none
        go_to(self.stack, "ManifestModsScreen")
