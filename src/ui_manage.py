"""
ui_manage.py: post-install management screens for DeckOps

Screens: ManagementCard, ManagementScreen, SetupCompleteScreen,
         ConfigureScreen, UpdateScreen
Screens are looked up by name (go_to/get_screen), never by stack index.
"""

import os, subprocess, sys, shutil, stat, threading, json, urllib.request, urllib.error, urllib.parse, compileall

from qt import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QPushButton, QCheckBox, QProgressBar, QPlainTextEdit,
    QFrame, QSizePolicy, QMessageBox, QLineEdit, QSlider, QDialog,
)
from qt import Qt, QTimer, QObject, QEvent, pyqtSignal
from qt import QPixmap
from qt import QGraphicsOpacityEffect

from detect_games import find_steam_root, find_all_games
import config as cfg
import inhibit

from ui_constants import (
    C_CARD, C_IW, C_TREY, C_DIM, C_DARK_BTN, C_RED_BTN, C_BLUE_BTN,
    font, _btn, _lbl, _hdiv, _log_to_file, _log_html, _copy_log_to_clipboard,
    _Sigs, _detached_open, _header_bar, _header_path, _ask_iw4x_dlc,
    _show_preflight,
    ALL_GAMES, KEY_CLIENT,
    _active_keys, _active_client, _active_appid,
    SP_IMAGE_URLS, IMG_RATIO, CARD_MAX_W,
    HEROES_DIR, PROJECT_ROOT,
    _music_volume, _music_enabled,
    _set_audio_volume, _set_audio_enabled, _start_audio, _kill_audio,
    go_to, get_screen,
)

from identity import GITHUB_USER, GITHUB_REPO
from log import get_logger

_log = get_logger(__name__)


# VERSION is per install. The repo still tracks an old copy from 2026-05
_PROTECTED = ("deckops.json", "VERSION", "assets/music/background.mp3")
_HDR = {"User-Agent": "DeckOps"}


def _protected(path: str) -> bool:
    return path.startswith("logs/") or path in _PROTECTED


def _tree(api: str, sha: str) -> dict:
    """{path: (blob sha, mode, size)} for every file in the commit."""
    req = urllib.request.Request(f"{api}/git/trees/{sha}?recursive=1", headers=_HDR)
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read())
    if d.get("truncated"):
        raise RuntimeError("GitHub's file list came back incomplete")
    return {e["path"]: (e["sha"], e["mode"], e.get("size", 0)) for e in d.get("tree", []) if e.get("type") == "blob"}


def _remote_changes(removed: bool = False):
    """
    (local_sha, remote_sha, stale, gone) for this install vs GitHub main.
    stale is {path: (blob sha, mode, size)} for every file on disk that differs
    from main or is missing, so a download that was cut off or served stale
    gets fixed on the next update even when VERSION already matches.
    gone lists files of the installed version that main no longer has
    (looked up only with removed=True). Raises if GitHub can't be reached.
    """
    from steam_common import git_blob_sha
    local_sha = "0"
    try:
        with open(os.path.join(PROJECT_ROOT, "VERSION")) as f:
            local_sha = f.read().strip() or "0"
    except OSError:
        pass
    api = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}"
    with urllib.request.urlopen(urllib.request.Request(f"{api}/commits/main", headers=_HDR), timeout=10) as r:
        remote_sha = json.loads(r.read()).get("sha", "")
    if not remote_sha:
        raise RuntimeError("GitHub returned no commit")
    want = _tree(api, remote_sha)
    stale = {}
    for path, (sha, mode, size) in want.items():
        if _protected(path):
            continue
        f = os.path.join(PROJECT_ROOT, path)
        try:
            ok = os.path.isfile(f) and git_blob_sha(f) == sha and (mode != "100755" or os.access(f, os.X_OK))
        except OSError:
            ok = False
        if not ok:
            stale[path] = (sha, mode, size)
    gone = []
    if removed and local_sha not in ("0", remote_sha):
        try:
            gone = [p for p in _tree(api, local_sha) if p not in want and not _protected(p)]
        except Exception:
            # e.g. the installed commit is gone after a force push. Leftovers stay
            _log.warning("could not list files of installed version %s", local_sha, exc_info=True)
    return local_sha, remote_sha, stale, gone


def _reset_hint(names) -> bool:
    # Mirrors launcher.sh RESET_HINT: config.py or more than 3 src/ files changed
    return "src/config.py" in names or sum(n.startswith("src/") for n in names) > 3


def _check_update_status():
    """Compare this install to GitHub main. Returns 'OK|..', 'UPDATE|..' or 'FAIL|..'."""
    try:
        local_sha, remote_sha, stale, _ = _remote_changes()
        if local_sha == remote_sha:
            if not stale:
                return "OK|You're up to date!"
            return f"UPDATE|{len(stale)} DeckOps file(s) need repair."
        hint = "\nReset Config recommended after updating." if _reset_hint(stale) else ""
        return f"UPDATE|Update available — {len(stale)} file(s) to download.{hint}"
    except Exception as ex:
        _log.warning("Update check failed: %s", ex)
        return "FAIL|Update check failed."


def card_rows(games):
    """The games page rows as (classics, the rest). The rest is a row per dev
    (Infinity Ward / Sledgehammer, then Treyarch and the LAN launcher). The classics
    go left of a divider, filled left to right, top to bottom, in release order, as
    many rows as the rest has. Both keep ALL_GAMES' release order."""
    classics = [g for g in games if g.get("classic")]
    rest = [r for r in ([g for g in games if not g.get("classic") and g["dev"] == "iw"],
                        [g for g in games if not g.get("classic") and g["dev"] != "iw"]) if r]
    n = max(len(rest), 1)
    per = -(-len(classics) // n)
    left = [classics[i * per:(i + 1) * per] for i in range(n)]
    return list(zip(left, rest or [[]]))


def card_width(cols, rows, w, h, gap=10):
    """Width of the largest cards that fit cols x rows in a w x h area, so the page never scrolls."""
    # 3 px for the coloured strip on top of each card
    cw = min((w - gap * (cols - 1)) // cols, int(((h - gap * (rows - 1)) / rows - 3) / IMG_RATIO))
    return max(1, min(cw, CARD_MAX_W))


# --- ManagementCard
class ManagementCard(QFrame):
    def __init__(self, gd, installed, on_setup, on_configure,
                 on_readd=None, on_add_ds=None, on_offline=None, parent=None):
        super().__init__(parent)
        color = C_IW if gd["dev"] == "iw" else C_TREY
        self._color  = color
        self._appid  = _active_appid(gd)
        self._is_lan = gd.get("client") == "lan"
        self.setObjectName("MC")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        keys       = _active_keys(gd)
        client     = _active_client(gd)

        if self._is_lan:
            # Offline Mode card: dimmed until added, like a game that isn't set up
            ik         = []
            is_setup   = cfg.get_offline_mode()
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

        # --- Image container with overlaid badge and buttons
        img_container = QWidget()
        img_container.setStyleSheet("background:#0A0A10;border:none;")
        img_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._img = QLabel(img_container)
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setStyleSheet("background:transparent;border:none;")
        if not is_setup:
            effect = QGraphicsOpacityEffect()
            effect.setOpacity(0.45 if is_present else 0.25)
            self._img.setGraphicsEffect(effect)

        # Client badge, overlaid top-left on the image. Only the main client
        # ("cod4r + iw3sp" shows COD4R) so it stays readable on small cards.
        self._client_badge = QPushButton(client.split(" + ")[0].upper(), img_container)
        self._client_badge.setFont(font(9, True)); self._client_badge.setEnabled(False)
        self._client_badge.setStyleSheet(
            f"QPushButton{{background:{color};color:#FFF;border:none;border-radius:3px;padding:2px 6px;}}"
            f"QPushButton:disabled{{background:{color};color:#FFF;}}"
        )
        self._client_badge.adjustSize()
        self._client_badge.raise_()

        # Buttons, overlaid bottom-center on the image
        self._btn_bar = QWidget(img_container)
        self._btn_bar.setStyleSheet("background:transparent;border:none;")
        bb = QHBoxLayout(self._btn_bar)
        bb.setContentsMargins(4, 0, 4, 0); bb.setSpacing(4)

        def _card_btn(text, bg, fg="#FFF"):
            # Small padding: cards are narrow on small screens
            b = QPushButton(text); b.setFont(font(10, True)); b.setFixedHeight(40)
            b.setStyleSheet(
                f"QPushButton{{background:{bg};color:{fg};border:none;border-radius:4px;padding:0 6px;}}"
                f"QPushButton:disabled{{background:{bg};color:{fg};}}")
            return b

        if self._is_lan and not is_setup:
            b = _card_btn("Add", C_IW)
            if on_offline: b.clicked.connect(lambda: on_offline(True))
        elif self._is_lan:
            b = _card_btn("Repair", C_TREY)
            if on_readd: b.clicked.connect(lambda: on_readd(gd))
            rm = _card_btn("Remove", C_RED_BTN)
            if on_offline: rm.clicked.connect(lambda: on_offline(False))
            bb.addStretch(); bb.addWidget(b); bb.addWidget(rm); b = None
        elif not is_setup and is_present:
            b = _card_btn("Set Up", C_IW)
            b.clicked.connect(lambda: on_setup(gd))
        elif is_setup:
            b = _card_btn("Options", "rgba(51,51,63,200)", "#CCC")
            b.clicked.connect(lambda: on_configure(gd, ik))
        elif "iw5mp_ds" in keys and on_add_ds:
            b = _card_btn("Get Free Game", C_IW)
            b.clicked.connect(lambda: on_add_ds(gd))
        else:
            b = _card_btn("Set Up", "rgba(37,37,53,200)", "#555568")
            b.setEnabled(False)
        if b: bb.addStretch(); bb.addWidget(b)
        bb.addStretch()

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
                self._img_sigs = _Sigs()
                self._img_sigs.log.connect(self._on_image_fetched)
                threading.Thread(target=self._fetch, args=(self._appid,), daemon=True).start()

    def _on_image_fetched(self, path):
        try:
            pix = QPixmap(path)
            if not pix.isNull():
                self._raw_pixmap = pix
                self._scale_image()
        except RuntimeError:
            pass  # card was rebuilt while the download ran

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
                self._raw_pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            )
        # Client badge sits top-left with a 4px margin
        self._client_badge.move(4, 4)
        # Button bar runs along the bottom, full width
        self._btn_bar.setFixedWidth(w)
        bh = self._btn_bar.sizeHint().height()
        self._btn_bar.move(0, h - bh - 4)

    def _fetch(self, appid):
        url = SP_IMAGE_URLS.get(appid)
        if not url:
            return
        try:
            from net import download
            dest = _header_path(appid)
            download(url, dest, timeout=10)
            self._img_sigs.log.emit(dest)
        except Exception:
            _log.debug("image load failed", exc_info=True)


# --- ManagementScreen
class ManagementScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.installed={}; self.screen_name = "ManagementScreen"
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        hdr, hl = _header_bar()
        self._deckops_update_btn = _btn("Update DeckOps", C_DARK_BTN, size=11, h=40)
        self._deckops_update_btn.setFixedWidth(170)
        self._deckops_update_btn.clicked.connect(self._check_deckops_update)
        hl.addWidget(self._deckops_update_btn)
        hl.addSpacing(8)
        self._game_update_btn = _btn("Update Games", C_DARK_BTN, size=11, h=40)
        self._game_update_btn.setFixedWidth(160)
        self._game_update_btn.clicked.connect(self._update_all_games)
        hl.addWidget(self._game_update_btn)
        hl.addSpacing(8)
        guide_btn = _btn("📋  Guide", C_DARK_BTN, size=11, h=40); guide_btn.setFixedWidth(120)
        guide_btn.clicked.connect(self._open_guide)
        hl.addWidget(guide_btn)
        hl.addSpacing(8)
        cfg_btn = _btn("⚙  Settings", C_DARK_BTN, size=11, h=40); cfg_btn.setFixedWidth(140)
        cfg_btn.clicked.connect(lambda: go_to(self.stack, "ConfigureScreen"))
        hl.addWidget(cfg_btn)
        lay.addWidget(hdr)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); self._scroll = scroll
        # The cards shrink to fit instead (card_width)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._cards = []
        scroll.setWidget(QWidget()); lay.addWidget(scroll, stretch=1)

        self._deckops_update_status = _lbl("", 10, C_DIM, wrap=False)
        self._deckops_update_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._deckops_update_status.setContentsMargins(16,0,16,4)
        lay.addWidget(self._deckops_update_status)

        self._status = _lbl("", 12, C_DIM)
        self._status.setContentsMargins(16,4,16,4)
        lay.addWidget(self._status)

        # Empty status lines are hidden so the cards get their height
        for l in (self._deckops_update_status, self._status):
            l.hide()
            l.setText = lambda t, l=l, f=l.setText: (f(t), l.setVisible(bool(t)))
        # Refit the cards whenever the visible area changes size
        scroll.viewport().installEventFilter(self)

    def _open_guide(self):
        get_screen(self.stack, "SetupCompleteScreen")._from_guide = True
        go_to(self.stack, "SetupCompleteScreen")

    def set_installed(self, installed):
        self.installed = installed
        self._rebuild()

    def showEvent(self, e):
        super().showEvent(e)
        self._refresh()

    def _refresh(self):
        if getattr(self, "_scanning", False): return
        self._scanning = True
        self._game_update_btn.setEnabled(False)
        if not self.installed: self._status.setText("Loading games...")
        self._scan_sigs = _Sigs()
        self._scan_sigs.done.connect(self._on_scanned)
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        try:
            self._scanned = find_all_games()
        except Exception:
            _log.warning("game scan failed", exc_info=True)
            self._scanned = None
        self._scan_sigs.done.emit(self._scanned is not None)

    def _on_scanned(self, ok):
        self._scanning = False
        self._game_update_btn.setEnabled(True)
        if self._status.text() == "Loading games...": self._status.setText("")
        if ok:
            self.installed = self._scanned
            self._rebuild()

    def _rebuild(self):
        games = [g for g in ALL_GAMES
                 if _active_keys(g) or g.get("client") == "lan"]
        rows = card_rows(games)

        # Classics block | divider line | the rest, centered, the leftover space split around it
        inner = QWidget(); v = QVBoxLayout(inner)
        v.setContentsMargins(10,10,10,10); v.addStretch()
        h = QHBoxLayout(); h.setSpacing(10); h.addStretch()
        self._cards = []
        left_any = any(row[0] for row in rows)
        for side in (0, 1):
            grid = QGridLayout(); grid.setSpacing(10)
            grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            for r, row in enumerate(rows):
                for c, gd in enumerate(row[side]):
                    card = ManagementCard(
                        gd, self.installed,
                        on_setup     = self._setup,
                        on_configure = self._configure,
                        on_readd     = self._readd,
                        on_add_ds    = self._add_mw3_ds,
                        on_offline   = self._offline,
                    )
                    self._cards.append(card); grid.addWidget(card, r, c)
            # CLASSICS over the left block. The right one has no heading, an empty label keeps both level
            col = QVBoxLayout(); col.setSpacing(6)
            if left_any:
                col.addWidget(_lbl("CLASSICS" if side == 0 else "", 11, C_DIM, bold=True))
            col.addLayout(grid); h.addLayout(col)
            if side == 0 and left_any:
                # The line runs beside the cards only: an empty heading-height label sits above it
                lc = QVBoxLayout(); lc.setSpacing(6); lc.addWidget(_lbl("", 11, bold=True))
                line = QFrame(); line.setFixedWidth(2); line.setStyleSheet(f"background:{C_DIM};border:none;")
                lc.addWidget(line, stretch=1); h.addLayout(lc)
        h.addStretch(); v.addLayout(h); v.addStretch()
        # setWidget deletes the old page and its cards
        self._scroll.setWidget(inner)
        left = max((len(r[0]) for r in rows), default=0)
        self._shape = (max(left + max((len(r[1]) for r in rows), default=0), 1), max(len(rows), 1))
        self._divider = 22 if left else 0  # the 2 px line and the spacing on each side
        self._heading = _lbl("X", 11, bold=True).sizeHint().height() + 6 if left else 0
        self._fitted = None
        self._place_cards()

    def _place_cards(self):
        if not self._cards:
            return
        vp = self._scroll.viewport()
        w = card_width(*self._shape, vp.width() - 20 - self._divider, vp.height() - 20 - self._heading)
        if w == self._fitted:
            return
        self._fitted = w
        for c in self._cards:
            c.setFixedWidth(w)

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Type.Resize and obj is self._scroll.viewport():
            self._place_cards()
        return super().eventFilter(obj, e)

    # --- Update DeckOps (from ManagementScreen)
    _GITHUB_USER = GITHUB_USER
    _GITHUB_REPO = GITHUB_REPO

    def _check_deckops_update(self):
        self._deckops_update_btn.setEnabled(False)
        self._deckops_update_status.setText("Checking...")
        self._deckops_update_status.setStyleSheet(f"color:{C_DIM};")
        self._du_sig = _Sigs()
        self._du_sig.log.connect(self._on_deckops_update_signal)
        threading.Thread(target=self._deckops_update_worker, daemon=True).start()

    def _deckops_update_worker(self):
        self._du_sig.log.emit(_check_update_status())

    def _on_deckops_update_signal(self, msg):
        kind, text = msg.split("|", 1)
        self._deckops_update_btn.setEnabled(True)
        self._deckops_update_status.setText(text)
        if kind == "UPDATE":
            self._deckops_update_status.setStyleSheet(f"color:{C_IW};")
            self._deckops_update_btn.setText("Update && Restart")
            try:
                self._deckops_update_btn.clicked.disconnect()
            except TypeError:
                pass
            self._deckops_update_btn.clicked.connect(self._apply_deckops_update)
        else:
            self._deckops_update_status.setStyleSheet(f"color:{C_DIM};")

    def _apply_deckops_update(self):
        # Apply runs on Settings. Show it so download progress is visible
        s = get_screen(self.stack, "ConfigureScreen")
        go_to(self.stack, "ConfigureScreen")
        QTimer.singleShot(0, s._apply_update)

    # --- Update all games (batch)
    def _update_all_games(self):
        root = find_steam_root()
        all_installed = self.installed

        # Build selected list: all set-up games with a mod client
        _gd_by_key = {}
        for gd_entry in ALL_GAMES:
            for k in _active_keys(gd_entry):
                _gd_by_key[k] = gd_entry

        selected = []
        for key, game in all_installed.items():
            c = KEY_CLIENT.get(key, "")
            if c in ("steam", "", None):
                continue
            if not cfg.is_game_setup(key):
                continue
            gd_entry = _gd_by_key.get(key)
            if gd_entry:
                selected.append((key, gd_entry, game))

        if not selected:
            self._status.setText("No installed mod-client games to update.")
            return

        names = ", ".join(s[1]["base"] for s in selected)
        msg = QMessageBox(self)
        msg.setWindowTitle("Update All Games")
        msg.setText(f"This will update {len(selected)} game(s):\n\n{names}\n\nContinue?")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        zd_cb = None
        if cfg.is_zd_installed() and any(k == "t6zm" for k, _, _ in selected):
            zd_cb = QCheckBox("Also check Zombies Declassified for updates (up to ~9 GB)")
            msg.setCheckBox(zd_cb)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        us = get_screen(self.stack, "UpdateScreen")
        us.update_zd = bool(zd_cb and zd_cb.isChecked())
        us.selected = selected
        us.steam_root = root
        go_to(self.stack, "UpdateScreen")

    def _offline(self, on):
        """Add or remove Offline Mode (offline launcher, Steam menu Offline entries, bot matches)."""
        text = ("Add Offline Mode? Adds the offline launcher, Plutonium Offline in each game's Steam "
                "launch menu, and bot matches in WaW / BO1 / BO2 / MW3 MP. Steam closes while it is set up."
                if on else
                "Remove Offline Mode? Removes the offline launcher, the Plutonium Offline launch menu "
                "entries and the bot match files. Steam closes while it is removed.")
        if QMessageBox.question(self, "Offline Mode", text) != QMessageBox.StandardButton.Yes:
            return
        def task(sigs):
            from wrapper import kill_steam
            from plutonium import apply_offline_mode
            sigs.progress.emit(2, "Closing Steam...")
            kill_steam(on_progress=sigs.log.emit)
            sr = cfg.load().get("steam_root", "") or find_steam_root()
            apply_offline_mode(on, sr, lambda p, m: (sigs.progress.emit(p, m.strip()), sigs.log.emit(m.strip())))
            sigs.log.emit("✓  Offline Mode added." if on else "✓  Offline Mode removed.")
        us = get_screen(self.stack, "UpdateScreen")
        us.task = ("OFFLINE MODE", task)
        go_to(self.stack, "UpdateScreen")

    def _readd(self, gd):
        """Repair the offline launcher: its files, its prefix and its shortcut."""
        if QMessageBox.question(self, "Offline Mode", "Repair the offline launcher? Checks its files, "
                                "rebuilds its prefix and re-adds the shortcut. Steam closes while it runs.") \
                != QMessageBox.StandardButton.Yes:
            return
        def task(sigs):
            import plutonium
            from shortcut import create_launcher_shortcut, repair_launcher_files
            from wrapper import kill_steam
            log = lambda m: sigs.log.emit(m.strip())
            # Steam must be closed first. Steam holds shortcuts.vdf and the
            # controller configsets in memory and flushes them on exit, which
            # clobbers any edits made while it is running. That is why the
            # launcher's controller template sometimes reverted.
            sigs.progress.emit(2, "Closing Steam...")
            kill_steam(on_progress=sigs.log.emit)
            sigs.progress.emit(10, "Checking launcher files...")
            repair_launcher_files(log)
            # Also the offline server's prefix. _lan_prefixes sets it up again
            sigs.progress.emit(40, "Rebuilding launcher prefix...")
            shutil.rmtree(plutonium.LAN_SERVER_PREFIX, ignore_errors=True)
            plutonium._lan_prefixes(log)
            try: os.remove(os.path.join(PROJECT_ROOT, ".lan_intent.json"))
            except FileNotFoundError: pass
            sigs.progress.emit(90, "Re-adding shortcut...")
            create_launcher_shortcut(on_progress=log)
            sigs.log.emit("✓  Offline launcher repaired. Safe to reopen Steam.")
        us = get_screen(self.stack, "UpdateScreen")
        us.task = ("REPAIR OFFLINE LAUNCHER", task)
        go_to(self.stack, "UpdateScreen")

    def _setup(self, gd, force_downgrade_ids=None):
        """Route a single card's keys through the install flow."""
        root = find_steam_root()
        keys = _active_keys(gd)
        # Find which keys are present in the merged installed dict
        present_keys = [k for k in keys if k in self.installed]
        if not present_keys:
            self._status.setText("Game files not found.")
            return

        selected = [(k, gd, self.installed[k]) for k in present_keys]

        # Asked first so the DLC choice is part of the space check.
        dlc = _ask_iw4x_dlc(self, selected)

        import preflight
        rows = [(k, KEY_CLIENT.get(k, ""), g.get("install_dir", ""))
                for k, _gd, g in selected]
        try:
            checks = preflight.check(rows, iw4x_dlc=(dlc == "install"),
                                     downgrade_keys=[k for k, _, _ in rows])
        except Exception as ex:
            _log_to_file(f"[ManagementScreen] preflight failed: {ex}")
            checks = []
        if not _show_preflight(self, checks):
            return

        s = get_screen(self.stack, "InstallScreen")
        own_selected = {}
        steam_selected = []
        for k, g_gd, game in selected:
            if game.get("source") == "own":
                own_selected[k] = game
            else:
                steam_selected.append((k, g_gd, game))
        s.own_selected = own_selected
        s.steam_selected = steam_selected
        s.steam_root = root
        s._return_to_management = True
        s.install_iw4x_dlc = dlc
        s.force_downgrade_ids = set(force_downgrade_ids or ())
        go_to(self.stack, "InstallScreen")

    def _add_mw3_ds(self, gd):
        """Request Steam install the free MW3 Dedicated Server (42750).

        Used when MW3 isn't installed at all. Once the user installs it
        via Steam and returns to DeckOps, showEvent rescans and the card
        picks up the normal Set Up flow.
        """
        from depot_downgrade import open_steam_install
        open_steam_install(42750)
        QMessageBox.information(
            self, gd["base"],
            "DeckOps is adding the free MW3 Dedicated Server tools to "
            "your Steam account.\n\n"
            "Please let it finish installing in Steam. Once it's done, "
            "close DeckOps and reopen it, then click Set Up on the "
            "MW3 card."
        )

    def _configure(self, gd, installed_keys):
        """Show configure dialog with Mods, Update, and Reinstall options."""
        _MOD_CLIENTS = ("cod4r", "cod4x", "iw4x", "plutonium", "alterware", "t7x")
        has_mods_support = any(KEY_CLIENT.get(k, "") in _MOD_CLIENTS for k in installed_keys)
        has_mod_client = any(KEY_CLIENT.get(k, "") not in ("steam", "") for k in installed_keys) \
            or any(cfg.get_setup_games().get(k, {}).get("client") == "iw-pad" for k in installed_keys)

        # Depot downgrade option: shown for any Steam-sourced game that
        # can be downgraded (MW3, Ghosts, AW). Whether the downgrade
        # is actually needed is checked on click.
        _DG_KEY_MAP = {
            "iw5": ("iw5mp", "iw5mp_ds", "iw5sp"),
            "iw6": ("iw6mp", "iw6sp"),
            "s1":  ("s1mp", "s1sp"),
        }
        _DG_LABELS = {"iw5": "Downgrade MW3",
                       "iw6": "Downgrade Ghosts", "s1": "Downgrade AW"}
        has_depot_dg = None
        for _dg_id, _dg_keys in _DG_KEY_MAP.items():
            _matched = [k for k in installed_keys if k in _dg_keys]
            if _matched:
                setup_games = cfg.get_setup_games()
                for k in _matched:
                    entry = setup_games.get(k, {})
                    if entry.get("source", "steam") == "steam":
                        has_depot_dg = _dg_id
                        break
            if has_depot_dg:
                break

        # Zombies Declassified: offered when t6zm is set up with Plutonium
        # and the user owns all BO2 Zombies DLC
        has_zd = False
        if ("t6zm" in installed_keys
                and KEY_CLIENT.get("t6zm") == "plutonium"
                and cfg.is_game_setup("t6zm")):
            _bo2 = self.installed.get("t6zm", {}).get("install_dir", "")
            if _bo2:
                from zombies_declassified import has_bo2_zm_dlc
                has_zd = has_bo2_zm_dlc(_bo2)

        # MW3 SP: old in-place downgrades left a 32-bit iw5sp.exe that
        # won't launch through Steam until a Verify restores it
        sp_verify = False
        _sp = self.installed.get("iw5sp", {}) if "iw5sp" in installed_keys else {}
        if _sp.get("install_dir") and _sp.get("source", "steam") != "own":
            from depot_downgrade import iw5sp_needs_verify
            sp_verify = iw5sp_needs_verify(_sp["install_dir"])

        msg = QMessageBox(self)
        msg.setWindowTitle(gd["base"])
        msg.setText("What would you like to do?")

        mods_btn = None
        if has_mods_support:
            mods_btn = msg.addButton("Mods", QMessageBox.ButtonRole.AcceptRole)
        zd_btn = None
        if has_zd:
            zd_btn = msg.addButton("Zombies Declassified", QMessageBox.ButtonRole.AcceptRole)
        upd_btn = None
        if has_mod_client:
            upd_btn = msg.addButton("Update", QMessageBox.ButtonRole.AcceptRole)
        dg_btn = None
        if has_depot_dg:
            dg_btn = msg.addButton(_DG_LABELS[has_depot_dg], QMessageBox.ButtonRole.AcceptRole)
        sp_btn = None
        if sp_verify:
            sp_btn = msg.addButton("Verify SP Files", QMessageBox.ButtonRole.AcceptRole)
        rei_btn = msg.addButton("Reinstall", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == mods_btn:
            self._mods(gd, installed_keys)
        elif clicked == zd_btn:
            self._zombies_declassified(gd, installed_keys)
        elif clicked == upd_btn:
            self._update(gd, installed_keys)
        elif clicked == dg_btn:
            self._depot_downgrade(has_depot_dg, gd, installed_keys)
        elif clicked == sp_btn:
            from wrapper import launch_steam
            launch_steam("steam://validate/42680")
            self._status.setText("Steam is verifying MW3 Single Player files...")
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

    def _zombies_declassified(self, gd, installed_keys):
        """Install, update, or uninstall Zombies Declassified DLC5 for BO2 ZM."""

        from zombies_declassified import resolve_zd_storage
        plut_storage_t6 = resolve_zd_storage(self.installed.get("t6zm"))

        if not plut_storage_t6 or not os.path.isdir(plut_storage_t6):
            self._status.setText("Could not find Plutonium storage/t6 directory.")
            return

        from zombies_declassified import is_zd_installed as _zd_present

        is_installed = _zd_present(plut_storage_t6)

        msg = QMessageBox(self)
        msg.setWindowTitle("Zombies Declassified")
        if is_installed:
            info = cfg.get_zd_info()
            tag = info.get("release_tag", "unknown")
            msg.setText(f"Zombies Declassified {tag} is installed.\nWhat would you like to do?")
            upd_btn = msg.addButton("Check for Updates", QMessageBox.ButtonRole.AcceptRole)
            rm_btn  = msg.addButton("Uninstall", QMessageBox.ButtonRole.DestructiveRole)
        else:
            msg.setText(
                "Zombies Declassified adds 10 classic Zombies maps to BO2.\n"
                "Download size: ~9 GB\n\n"
                "Install now?"
            )
            upd_btn = msg.addButton("Install", QMessageBox.ButtonRole.AcceptRole)
            rm_btn  = None
        msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == upd_btn:
            action = "update" if is_installed else "install"
        elif clicked == rm_btn:
            action = "uninstall"
        else:
            return

        # Run on background thread with a simple progress dialog
        from qt import QProgressDialog
        pd = QProgressDialog("Starting...", None, 0, 100, self)
        pd.setWindowTitle("Zombies Declassified")
        pd.setMinimumDuration(0); pd.setAutoClose(False); pd.setAutoReset(False)
        pd.setCancelButton(None); pd.show()

        _st6 = plut_storage_t6

        class _ZDSigs(QObject):
            progress = pyqtSignal(int, str)
            done     = pyqtSignal(str)
        sigs = _ZDSigs()
        sigs.progress.connect(lambda p, m: (pd.setValue(p), pd.setLabelText(m)))

        def _on_done(result_msg):
            pd.setValue(100); pd.setLabelText(result_msg)
            pd.setCancelButtonText("OK")
            pd.canceled.connect(pd.close)
            if action == "install":
                from zombies_declassified import get_zd_info as _get_info
                info = _get_info(_st6)
                if info.get("manifest_hash"):
                    cfg.mark_zd_installed(info["manifest_hash"])
            elif action == "uninstall":
                cfg.unmark_zd_installed()
        sigs.done.connect(_on_done)

        def _worker():
            try:
                from zombies_declassified import install_zd, update_zd, uninstall_zd
                if action == "install":
                    errors = install_zd(_st6, lambda p, m: sigs.progress.emit(p, m))
                    if errors:
                        sigs.done.emit(f"Installed with {len(errors)} error(s). Check log.")
                    else:
                        sigs.done.emit("Zombies Declassified installed!")
                elif action == "update":
                    updated = update_zd(_st6, lambda p, m: sigs.progress.emit(p, m))
                    if updated:
                        from zombies_declassified import get_zd_info as _get_info
                        info = _get_info(_st6)
                        if info.get("manifest_hash"):
                            cfg.mark_zd_installed(info["manifest_hash"])
                        sigs.done.emit("Updated!")
                    else:
                        sigs.done.emit("Already up to date.")
                elif action == "uninstall":
                    uninstall_zd(_st6, lambda p, m: sigs.progress.emit(p, m))
                    sigs.done.emit("Zombies Declassified removed.")
            except Exception as ex:
                sigs.done.emit(f"Error: {ex}")
        threading.Thread(target=_worker, daemon=True).start()

    def _reinstall(self, gd):
        """Unmark game keys as set up, then route through the install flow."""
        keys = _active_keys(gd)
        cfg.unmark_game_setup(keys)
        self._status.setText(f"Cleared setup state for {gd['base']}. Running clean install...")
        # Route through the same path as "Set Up"
        self._setup(gd)

    def _depot_downgrade(self, game_id, gd, installed_keys):
        """Downgrade a game from 64-bit to 32-bit and reinstall it.

        Checks first whether the downgrade is needed. If the depot files
        are already right, it asks before forcing one. Then it clears the
        receipt, unmarks the game's keys and reruns the install flow with
        the downgrade forced.
        """
        _DG_KEY_MAP = {
            "iw5": ("iw5mp", "iw5mp_ds", "iw5sp"),
            "iw6": ("iw6mp", "iw6sp"),
            "s1":  ("s1mp", "s1sp"),
        }
        _dg_keys = [k for k in installed_keys if k in _DG_KEY_MAP.get(game_id, ())]
        if not _dg_keys:
            return

        from depot_downgrade import is_downgrade_needed, GAME_CONFIGS
        gcfg = GAME_CONFIGS.get(game_id, {})
        game_name = gcfg.get("name", gd["base"])

        idir = ""
        for k in _dg_keys:
            game = self.installed.get(k, {})
            if game.get("install_dir"):
                idir = game["install_dir"]
                break

        if idir and not is_downgrade_needed(game_id, idir):
            msg = QMessageBox(self)
            msg.setWindowTitle(gd["base"])
            msg.setText(f"{game_name} already has the correct depot files.")
            msg.addButton(QMessageBox.StandardButton.Ok)
            force_btn = msg.addButton("Force Downgrade", QMessageBox.ButtonRole.AcceptRole)
            msg.exec()
            if msg.clickedButton() != force_btn:
                return

        # Force a fresh downgrade: drop both the receipt and the legacy flag
        from depot_downgrade import clear_receipt
        if idir: clear_receipt(game_id, idir)
        if gcfg.get("always_64bit"):
            cfg.clear_depot_patched(game_id)
        cfg.unmark_game_setup(_dg_keys)
        self._status.setText(
            f"{game_name} downgrade selected. Running depot download and reinstall..."
        )
        self._setup(gd, force_downgrade_ids={game_id})

    def _mods(self, gd, installed_keys):
        """Open the mod folder for a game. Shows a chooser for games with
        both mods/ and usermaps/ folders (CoD4R, CoD4x, IW4x, T7X), for
        AlterWare games with data/scripts/mp and data/scripts/sp, or for
        OLED Plutonium games whose SP/MP modes live in separate prefixes."""

        # --- Plutonium storage name mapping
        _PLUT_STORAGE = {
            "t4sp": "t4", "t4mp": "t4",
            "t5sp": "t5", "t5mp": "t5",
            "t6mp": "t6", "t6zm": "t6",
            "iw5mp": "iw5", "iw5mp_ds": "iw5",
        }

        # Appid per key. On OLED, keys on the same card with different
        # appids have separate Wine prefixes, so separate mods/ folders.
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
            if c in ("cod4r", "cod4x", "iw4x"):
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

        if client in ("cod4r", "cod4x", "iw4x"):
            mod_key = installed_keys[0]
            game = self.installed.get(mod_key, {})
            install_dir = game.get("install_dir", "")
            if not install_dir:
                self._status.setText("Game install directory not found.")
                return
            # Two folders, so ask which one
            msg = QMessageBox(self)
            msg.setWindowTitle("Open Mod Folder")
            msg.setText(f"Which folder would you like to open for {gd['base']}?")
            mods_btn = msg.addButton("Mods", QMessageBox.ButtonRole.AcceptRole)
            usermaps_btn = msg.addButton("User Maps", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
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
            # Two folders, so ask which one
            msg = QMessageBox(self)
            msg.setWindowTitle("Open Mod Folder")
            msg.setText(f"Which folder would you like to open for {gd['base']} (T7x)?")
            mods_btn = msg.addButton("Mods", QMessageBox.ButtonRole.AcceptRole)
            usermaps_btn = msg.addButton("User Maps", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
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
                mp_btn = msg.addButton("MP Scripts", QMessageBox.ButtonRole.AcceptRole)
                sp_btn = msg.addButton("SP Scripts", QMessageBox.ButtonRole.AcceptRole)
                msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                msg.exec()
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
                    btn = msg.addButton(label, QMessageBox.ButtonRole.AcceptRole)
                    key_buttons.append((btn, k))
                msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                msg.exec()
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
                # Single prefix or LCD: open directly
                mods_path = _resolve_plut_mods_dir(plut_keys[0])
                if mods_path:
                    _open_folder(mods_path)
                else:
                    self._status.setText("Could not resolve Plutonium mods folder.")


# --- SetupCompleteScreen
class SetupCompleteScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack = stack; self.screen_name = "SetupCompleteScreen"
        self._from_guide = False
        lay = QVBoxLayout(self); lay.setContentsMargins(60,20,60,20); lay.setSpacing(0)

        t = QLabel("SETUP COMPLETE"); t.setFont(font(28, True)); t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet("color:#FFF;background:transparent;"); lay.addWidget(t)
        lay.addWidget(_lbl(
            "Your games are configured with controller profiles, GE-Proton, "
            "and display settings. Open Steam (or return to Game Mode) to start playing.",
            12, C_DIM))

        # --- Scrollable content area
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget()
        sl = QVBoxLayout(inner); sl.setContentsMargins(0,8,0,8); sl.setSpacing(6)

        # --- Cloud saves
        sl.addWidget(_hdiv())
        sl.addWidget(_lbl("⚠  Steam Cloud Saves", 12, C_TREY, bold=True, align=Qt.AlignmentFlag.AlignLeft))
        sl.addWidget(_lbl(
            "If Steam asks about cloud saves, choose Keep Local. "
            "If a game asks for Safe Mode, choose No.",
            11, C_DIM, align=Qt.AlignmentFlag.AlignLeft))

        # --- MW1 / WaW shortcuts
        self._mw1waw_div = _hdiv()
        self._mw1waw_hdr = _lbl("🎮  MW1 & WaW Multiplayer", 12, C_IW, bold=True, align=Qt.AlignmentFlag.AlignLeft)
        # Text set in showEvent, for the games that are set up
        self._mw1waw_body = _lbl("", 11, C_DIM, align=Qt.AlignmentFlag.AlignLeft)
        sl.addWidget(self._mw1waw_div)
        sl.addWidget(self._mw1waw_hdr)
        sl.addWidget(self._mw1waw_body)

        # --- First launch
        sl.addWidget(_hdiv())
        sl.addWidget(_lbl("⏳  First Launch", 12, "#5B9BD5", bold=True, align=Qt.AlignmentFlag.AlignLeft))
        sl.addWidget(_lbl(
            "All games take longer to start the first time. Later starts are faster.",
            11, C_DIM, align=Qt.AlignmentFlag.AlignLeft))
        self._offline_body = _lbl(
            "Start each Plutonium game one time before you use Plutonium Offline.",
            11, C_DIM, align=Qt.AlignmentFlag.AlignLeft)
        sl.addWidget(self._offline_body)

        # --- MW2 MP own-game first launch
        self._mw2own_div = _hdiv()
        self._mw2own_hdr = _lbl("🎮  MW2 Multiplayer (Non-Steam)", 12, C_IW, bold=True, align=Qt.AlignmentFlag.AlignLeft)
        self._mw2own_body = _lbl(
            "Start MW2 Multiplayer (IW4x) two times after the first install. "
            "The first launch fails. The second launch works.",
            11, C_DIM, align=Qt.AlignmentFlag.AlignLeft)
        sl.addWidget(self._mw2own_div)
        sl.addWidget(self._mw2own_hdr)
        sl.addWidget(self._mw2own_body)

        # --- BO3 first launch
        self._bo3_div = _hdiv()
        self._bo3_hdr = _lbl("🎮  Black Ops III: First Launch", 12, C_TREY, bold=True, align=Qt.AlignmentFlag.AlignLeft)
        self._bo3_body = _lbl(
            "CleanOps finishes its install on the first launch. Do the "
            "first launch in Desktop Mode:\n\n"
            "1. Start Black Ops III (CleanOps). It patches the game. The Deck "
            "can be slow for a short time.\n"
            "2. If the game does not start, press the blue Stop button in "
            "Steam. Then start it again.",
            11, C_DIM, align=Qt.AlignmentFlag.AlignLeft)
        sl.addWidget(self._bo3_div)
        sl.addWidget(self._bo3_hdr)
        sl.addWidget(self._bo3_body)

        # --- LCD notes (LCD only)
        self._lcd_div = _hdiv()
        self._lcd_hdr = _lbl("⚠  LCD Steam Deck Notes", 12, C_TREY, bold=True, align=Qt.AlignmentFlag.AlignLeft)
        self._lcd_body = _lbl(
            "Plutonium games on LCD can take a moment to start while a "
            "shader cache cleanup runs. If a game does not start, wait or "
            "start it again.\n\n"
            "If Steam asks to compile Vulkan shaders, skip it. LCD Plutonium "
            "games do not use them.\n\n"
            "To exit faster, quit from the in-game menu, not the Steam overlay.",
            11, C_DIM, align=Qt.AlignmentFlag.AlignLeft)
        sl.addWidget(self._lcd_div)
        sl.addWidget(self._lcd_hdr)
        sl.addWidget(self._lcd_body)

        # --- Restore player saves (visible only when backups exist)
        self._restore_div = _hdiv()
        self._restore_hdr = _lbl("💾  Restore Player Saves", 12, C_IW, bold=True, align=Qt.AlignmentFlag.AlignLeft)
        self._restore_body = _lbl(
            "Backups from a previous install were found. "
            "Restore your configs, stats, and custom classes?",
            11, C_DIM, align=Qt.AlignmentFlag.AlignLeft)
        self._restore_status = _lbl("", 11, C_IW, align=Qt.AlignmentFlag.AlignLeft)
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

        # --- Continue button (pinned outside scroll)
        cont = _btn("Continue  >>", C_IW, size=13, h=42)
        cont.setFixedWidth(240)
        cont.clicked.connect(self._go_management)
        cw = QHBoxLayout(); cw.setContentsMargins(0,4,0,12); cw.addStretch(); cw.addWidget(cont); cw.addStretch()
        lay.addLayout(cw)

    def showEvent(self, e):
        super().showEvent(e)
        plut = any(cfg.is_game_setup(k) for k in ("t4sp", "t4mp", "t5sp", "t5mp", "t6mp", "t6zm", "iw5mp"))
        show_lcd = cfg.is_lcd() and plut
        for w in (self._lcd_div, self._lcd_hdr, self._lcd_body):
            w.setVisible(show_lcd)
        self._offline_body.setVisible(plut and cfg.get_offline_mode())
        mp = [n for k, n in (("cod4mp", "MW1"), ("t4mp", "WaW")) if cfg.is_game_setup(k)]
        text = ""
        if mp:
            text = (f"{' and '.join(mp)} {'have' if len(mp) > 1 else 'has a'} DeckOps "
                    f"multiplayer shortcut{'s' if len(mp) > 1 else ''} in your Steam library. "
                    "Use the main game entry for singleplayer and the DeckOps shortcut for multiplayer.")
        if cfg.is_game_setup("cod4sp"):
            from game_config import _cod4_profile_name
            name = _cod4_profile_name(cfg.get_player_name())
            text += ("\n\n" if text else "") + (
                f"MW1 Singleplayer: on the first launch, select the \"{name}\" profile. "
                "DeckOps made this profile with your display settings.")
        self._mw1waw_hdr.setText("🎮  " + (" & ".join(mp) + " Multiplayer" if mp else "MW1 Singleplayer"))
        self._mw1waw_body.setText(text)
        for w in (self._mw1waw_div, self._mw1waw_hdr, self._mw1waw_body):
            w.setVisible(bool(text))
        show_bo3 = cfg.is_game_setup("t7")
        for w in (self._bo3_div, self._bo3_hdr, self._bo3_body):
            w.setVisible(show_bo3)
        show_mw2own = cfg.is_game_setup_for_source("iw4mp", "own")
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
                    self._s.log.emit(f"✓  Restored saves for {count} group(s): {groups}")
                else:
                    self._s.log.emit("No matching save data found to restore.")
            except Exception as ex:
                self._s.log.emit(f"⚠  Restore failed: {ex}")

        self._s = _Sigs()
        self._s.log.connect(self._restore_finished)
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
        self._from_guide = False
        go_to(self.stack, "ManagementScreen")


# --- ConfigureScreen
class ConfigureScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack=stack; self.screen_name = "ConfigureScreen"
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        hdr, hl = _header_bar()
        t = _lbl("SETTINGS", 16, "#CCC", bold=True, wrap=False)
        hl.insertSpacing(2, 20); hl.insertWidget(3, t)
        back = _btn("<< Back", C_DARK_BTN, size=12, h=40); back.setFixedWidth(140)
        back.clicked.connect(lambda: go_to(self.stack, "ManagementScreen"))
        hl.addWidget(back)
        lay.addWidget(hdr)

        # Scroll only kicks in on windows smaller than the Deck screen
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget()
        cols = QHBoxLayout(inner); cols.setContentsMargins(40,16,40,16); cols.setSpacing(40)
        left = QVBoxLayout(); left.setSpacing(10)
        right = QVBoxLayout(); right.setSpacing(10)
        cols.addLayout(left, 1); cols.addLayout(right, 1)

        def _head(col, text, color="#CCC", first=False):
            if not first: col.addSpacing(12)
            col.addWidget(_lbl(text, 13, color, bold=True, align=Qt.AlignmentFlag.AlignLeft))

        # --- Left: Background Music
        _head(left, "Background Music", first=True)
        mr = QHBoxLayout(); mr.setSpacing(12)
        self._music_on = _music_enabled
        self._music_toggle = _btn(
            "Music: ON" if self._music_on else "Music: OFF",
            C_IW if self._music_on else C_DARK_BTN,
            size=12, h=40,
        )
        self._music_toggle.setFixedWidth(160)
        self._music_toggle.clicked.connect(self._toggle_music)
        self._vol_slider = QSlider(Qt.Orientation.Horizontal); self._vol_slider.setRange(0,100)
        self._vol_slider.setValue(int(_music_volume*100))
        self._vol_label = _lbl(f"{int(_music_volume*100)}%", 12, C_DIM, wrap=False)
        self._vol_label.setFixedWidth(44)
        self._vol_slider.valueChanged.connect(self._set_volume)
        mr.addWidget(self._music_toggle); mr.addWidget(self._vol_slider,stretch=1); mr.addWidget(self._vol_label)
        left.addLayout(mr)

        # --- Left: Controller Profiles
        _head(left, "Controller Profiles")
        gr = QHBoxLayout(); gr.setSpacing(8)
        gr.addWidget(_lbl("Gyro:", 12, "#AAA", wrap=False))
        self._gyro_btns = {}
        # Steam Deck LCD/OLED and Steam Machine get 4 modes, other devices 2.
        # showEvent hides Hold and Toggle.
        for mode in ("on", "hold", "toggle", "off"):
            labels = {"on": "ADS", "hold": "Hold", "toggle": "Toggle", "off": "Off"}
            b = _btn(labels[mode], C_DARK_BTN, size=11, h=40)
            b.setFixedWidth(96)
            b.clicked.connect(lambda checked, m=mode: self._set_gyro(m))
            gr.addWidget(b)
            self._gyro_btns[mode] = b
        gr.addStretch()
        left.addLayout(gr)
        ctrl_btn = _btn("Re-apply Templates", C_DARK_BTN, size=12, h=40)
        ctrl_btn.setFixedWidth(220)
        ctrl_btn.clicked.connect(self._apply_controller_profiles)
        left.addWidget(ctrl_btn)

        # --- Left: Shortcuts
        _head(left, "Shortcuts")
        left.addWidget(_lbl("Closes Steam, then re-adds any missing DeckOps shortcuts.",
                            11, C_DIM, align=Qt.AlignmentFlag.AlignLeft))
        sc_fix_btn = _btn("Repair Shortcuts", C_DARK_BTN, size=12, h=40)
        sc_fix_btn.setFixedWidth(220); sc_fix_btn.clicked.connect(self._repair_shortcuts)
        left.addWidget(sc_fix_btn)

        # --- Left: Game Configs
        _head(left, "Game Configs")
        left.addWidget(_lbl("Copies the DeckOps game settings for your device again. This overwrites changes you made to those files.",
                            11, C_DIM, align=Qt.AlignmentFlag.AlignLeft))
        gc_btn = _btn("Re-apply Game Configs", C_DARK_BTN, size=12, h=40)
        gc_btn.setFixedWidth(220); gc_btn.clicked.connect(self._confirm_game_configs)
        left.addWidget(gc_btn)

        # --- Left: Player Name
        _head(left, "Player Name")
        nr = QHBoxLayout(); nr.setSpacing(12)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Enter player name...")
        self._name_input.setFixedHeight(40)
        self._name_input.setMaxLength(32)
        self._name_input.setStyleSheet(
            "QLineEdit{background:#2A2A3A;color:#FFF;border:1px solid #444;"
            "border-radius:6px;padding:0 10px;font-size:13px;}"
            "QLineEdit:focus{border:1px solid #888;}"
        )
        save_btn = _btn("Save", C_IW, size=12, h=40)
        save_btn.setFixedWidth(90)
        save_btn.clicked.connect(self._save_name)
        nr.addWidget(self._name_input, stretch=1); nr.addWidget(save_btn)
        left.addLayout(nr)
        self._name_note = _lbl("Sets your offline name for CoD4x, IW4x, AlterWare, T7X, and Plutonium. Does not affect CleanOps.", 10, C_DIM, align=Qt.AlignmentFlag.AlignLeft)
        left.addWidget(self._name_note)

        # --- Left: Shader Cache (LCD only)
        self._shader_row = QWidget()
        sr_lay = QVBoxLayout(self._shader_row); sr_lay.setContentsMargins(0,0,0,0); sr_lay.setSpacing(10)
        sr_lay.addSpacing(12)
        sr_lay.addWidget(_lbl("Shader Cache", 13, "#CCC", bold=True, align=Qt.AlignmentFlag.AlignLeft))
        sc_btn = _btn("Clear Shader Cache", C_DARK_BTN, size=12, h=40)
        sc_btn.setFixedWidth(220)
        sc_btn.clicked.connect(self._clear_shader_cache)
        sr_lay.addWidget(sc_btn)
        left.addWidget(self._shader_row)
        # Kept for showEvent's LCD toggle. The two-column layout has no dividers
        self._shader_hdiv = QWidget(); self._shader_hdiv.setFixedHeight(0)
        left.addWidget(self._shader_hdiv)
        left.addStretch()

        # --- Right: Links
        _head(right, "Links", first=True)
        lr = QHBoxLayout(); lr.setSpacing(12)
        discord_btn = _btn("Discord", "#5865F2", size=12, h=40)
        discord_btn.setFixedWidth(120)
        discord_btn.clicked.connect(lambda: self._open_url("https://discord.gg/bkSQeq5Azk"))
        stable_btn = _btn("Stable", C_DARK_BTN, size=12, h=40)
        stable_btn.setFixedWidth(120)
        stable_btn.clicked.connect(lambda: self._open_url(f"https://github.com/{GITHUB_USER}/DeckOps"))
        nightly_btn = _btn("Nightly", C_DARK_BTN, size=12, h=40)
        nightly_btn.setFixedWidth(120)
        nightly_btn.clicked.connect(lambda: self._open_url(f"https://github.com/{GITHUB_USER}/DeckOps-Nightly"))
        lr.addWidget(discord_btn); lr.addWidget(stable_btn); lr.addWidget(nightly_btn); lr.addStretch()
        right.addLayout(lr)

        # --- Right: Updates & Logs
        _head(right, "Updates & Logs")
        self._update_btn = _btn("Check for Updates", C_BLUE_BTN, size=12, h=40)
        self._update_btn.setFixedWidth(220)
        self._update_btn.clicked.connect(self._check_for_updates)
        right.addWidget(self._update_btn)
        self._update_status = _lbl("", 11, C_DIM, align=Qt.AlignmentFlag.AlignLeft)
        right.addWidget(self._update_status)
        udr = QHBoxLayout(); udr.setSpacing(12)
        log_btn = _btn("Copy Log", C_DARK_BTN, size=12, h=40)
        log_btn.setFixedWidth(130)
        view_log_btn = _btn("View Log", C_DARK_BTN, size=12, h=40)
        view_log_btn.setFixedWidth(130)
        view_log_btn.clicked.connect(self._view_log)
        udr.addWidget(log_btn); udr.addWidget(view_log_btn); udr.addStretch()
        right.addLayout(udr)
        self._log_status = _lbl("", 11, C_DIM, align=Qt.AlignmentFlag.AlignLeft)
        right.addWidget(self._log_status)
        log_btn.clicked.connect(lambda: _copy_log_to_clipboard(self._log_status))

        # --- Right: Danger Zone
        _head(right, "Danger Zone", "#E05050")
        right.addWidget(_lbl("These remove DeckOps changes. Each asks for confirmation first.",
                             11, C_DIM, align=Qt.AlignmentFlag.AlignLeft))
        dzr = QHBoxLayout(); dzr.setSpacing(12)
        uninstall_btn = _btn("Full Uninstall", C_RED_BTN, size=12, h=40)
        reset_cfg_btn = _btn("Reset DeckOps Config", C_RED_BTN, size=12, h=40)
        uninstall_btn.clicked.connect(self._confirm_uninstall)
        reset_cfg_btn.clicked.connect(self._confirm_reset)
        dzr.addWidget(uninstall_btn); dzr.addWidget(reset_cfg_btn); dzr.addStretch()
        right.addLayout(dzr)

        # --- Right: About + status
        right.addSpacing(12)
        self._about_label = _lbl("", 11, C_DIM, align=Qt.AlignmentFlag.AlignLeft)
        right.addWidget(self._about_label)
        self.status = _lbl("", 12, C_DIM, align=Qt.AlignmentFlag.AlignLeft)
        right.addWidget(self.status)
        right.addStretch()

        scroll.setWidget(inner)
        lay.addWidget(scroll, stretch=1)

    def showEvent(self, event):
        super().showEvent(event)
        # Sync music toggle with current state (may have changed via mute button)
        self._music_on = cfg.get_music_enabled()
        self._music_toggle.setText("Music: ON" if self._music_on else "Music: OFF")
        self._music_toggle.setStyleSheet(
            self._music_toggle.styleSheet()
            .replace(C_IW if not self._music_on else C_DARK_BTN,
                     C_IW if self._music_on else C_DARK_BTN))
        # Refresh dynamic state
        model = cfg.get_deck_model() or "unknown"
        source_label = "Steam & Non-Steam"
        player = cfg.get_player_name() or "Player"
        self._name_input.setText(player if player != "Player" else "")

        # Show hold/toggle only for Steam Deck LCD/OLED and Steam Machine
        has_full_modes = model in ("lcd", "oled", "steam_machine")
        self._gyro_btns["hold"].setVisible(has_full_modes)
        self._gyro_btns["toggle"].setVisible(has_full_modes)
        # Other devices show "Gyro On" instead of ADS
        self._gyro_btns["on"].setText("ADS" if has_full_modes else "Gyro On")

        # Gyro highlight
        gyro = cfg.get_gyro_mode() or "on"
        # Other devices with hold or toggle saved highlight "on"
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

    def _repair_shortcuts(self):
        self.status.setText("Checking shortcuts...")
        s = _Sigs()
        s.log.connect(lambda msg: self.status.setText(msg))
        def _run():
            try:
                from shortcut import repair_shortcuts
                from wrapper import kill_steam
                s.log.emit("Closing Steam...")
                kill_steam(on_progress=lambda msg: s.log.emit(f"  {msg}"))
                sr = cfg.load().get("steam_root", "") or None
                readded = repair_shortcuts(sr, on_progress=s.log.emit)
                if readded:
                    s.log.emit(f"✓  Re-added: {', '.join(readded)}. It is now safe to reopen Steam.")
                else:
                    s.log.emit("✓  All shortcuts present. It is now safe to reopen Steam.")
            except Exception as ex:
                s.log.emit(f"✗  Repair failed: {ex}")
        threading.Thread(target=_run, daemon=True).start()

    def _confirm_game_configs(self):
        reply = QMessageBox.warning(
            self, "Re-apply Game Configs",
            "This copies the DeckOps settings for your device over the config "
            "files of every game DeckOps set up. Settings you changed in game "
            "will be lost.\n\nClose all games first. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._reapply_game_configs()

    def _reapply_game_configs(self):
        self.status.setText("Applying game configs...")
        s = _Sigs()
        s.log.connect(lambda msg: self.status.setText(msg))
        def _run():
            try:
                from game_config import apply_game_configs
                from detect_games import find_all_games as _find_all
                steam_root = cfg.load().get("steam_root", "") or find_steam_root()
                installed = _find_all(steam_root) if steam_root else {}
                keys = [k for k in cfg.get_setup_games() if k in installed]
                applied, skipped, failed = apply_game_configs(
                    selected_keys=keys, installed_games=installed,
                    steam_root=steam_root, deck_model=cfg.get_deck_model() or "oled",
                    on_progress=lambda msg: s.log.emit(msg),
                )
                s.log.emit(f"✓  Game configs: {applied} written"
                           + (f", {skipped} skipped" if skipped else "")
                           + (f", {failed} failed" if failed else "") + ".")
            except Exception as ex:
                s.log.emit(f"✗  Failed: {ex}")
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
                from detect_games import find_all_games as _find_all
                steam_root = cfg.load().get("steam_root", "") or find_steam_root()
                installed = _find_all(steam_root) if steam_root else {}
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

    def _view_log(self):
        from ui_constants import LOG_PATH
        lines = []
        try:
            with open(LOG_PATH, "r", errors="replace") as f:
                lines = f.readlines()
        except FileNotFoundError:
            pass
        tail = "".join(lines[-500:]) if lines else "(No log file found)"

        dlg = QDialog(self)
        dlg.setWindowTitle("Install Log")
        dlg.resize(700, 480)
        vl = QVBoxLayout(dlg); vl.setContentsMargins(12,12,12,12); vl.setSpacing(8)
        txt = QPlainTextEdit(); txt.setReadOnly(True); txt.setFont(font(10))
        txt.setStyleSheet("QPlainTextEdit{color:#AAB;background:#1A1A24;border:1px solid #333;border-radius:4px;padding:6px;}")
        txt.setPlainText(tail)
        vl.addWidget(txt, stretch=1)
        br = QHBoxLayout()
        copy_btn = _btn("Copy to Clipboard", C_DARK_BTN, size=11, h=40)
        copy_btn.clicked.connect(lambda: (
            QApplication.clipboard().setText(tail),
            self.status.setText("Log copied to clipboard."),
        ))
        br.addStretch(); br.addWidget(copy_btn); br.addStretch()
        vl.addLayout(br)
        txt.verticalScrollBar().setValue(txt.verticalScrollBar().maximum())
        dlg.exec()

    def _open_url(self, url):
        _detached_open(["xdg-open", url])

    def _confirm_uninstall(self):
        reply = QMessageBox.warning(
            self, "Full Uninstall",
            "This will remove all DeckOps files, shortcuts, controller profiles, "
            "and mod client installations. Your Steam games will NOT be deleted.\n\n"
            "DeckOps will close and the uninstaller will run in a terminal window.\n\n"
            "Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
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
            # Close DeckOps, since the uninstaller removes its files
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

    # --- Update check
    _GITHUB_USER = GITHUB_USER
    _GITHUB_REPO = GITHUB_REPO

    def _init_update_signals(self):
        """Connect the update result signal (fresh for each check)."""
        self._update_sig = _Sigs()
        self._update_sig.log.connect(self._on_update_signal)

    def _check_for_updates(self):
        """Compare this install to GitHub main in a background thread."""
        self._init_update_signals()
        self._update_btn.setEnabled(False)
        self._update_status.setText("Checking...")
        self._update_status.setStyleSheet(f"color:{C_DIM};")
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_worker(self):
        self._update_sig.log.emit(_check_update_status())

    def _on_update_signal(self, msg):
        """Runs on the main thread, called through the signal."""
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
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._update_btn.setEnabled(False)
        self._update_btn.setText("Updating...")
        self._update_status.setText("Downloading update...")
        self._update_status.setStyleSheet(f"color:{C_DIM};")

        # Same popup as the Zombies Declassified download
        from qt import QProgressDialog
        pd = self._update_pd = QProgressDialog("Checking files...", None, 0, 100, self)
        pd.setWindowTitle("Update DeckOps")
        pd.setMinimumDuration(0); pd.setAutoClose(False); pd.setAutoReset(False)
        pd.setCancelButton(None); pd.show()

        self._apply_sig = _Sigs()
        self._apply_sig.progress.connect(lambda p, m: (pd.setValue(p), pd.setLabelText(m)))
        self._apply_sig.log.connect(self._on_apply_signal)
        threading.Thread(target=self._apply_worker, daemon=True).start()

    def _apply_worker(self):
        """Download every file that differs from GitHub main, stage, check, apply, then signal relaunch."""
        from net import download
        from steam_common import git_blob_sha
        install_dir = PROJECT_ROOT
        update_dir = os.path.join(install_dir, ".update")
        try:
            local_sha, remote_sha, stale, gone = _remote_changes(removed=True)
            if not stale and not gone and local_sha == remote_sha:
                self._apply_sig.log.emit("FAIL|Already up to date.")
                return
            # Files come from the commit itself: main on raw.githubusercontent is cached
            # for minutes after a push and served the previous version (Deck, 2026-10-22)
            raw = f"https://raw.githubusercontent.com/{self._GITHUB_USER}/{self._GITHUB_REPO}/{remote_sha}"
            if os.path.isdir(update_dir):
                shutil.rmtree(update_dir)
            os.makedirs(update_dir, exist_ok=True)

            total = len(stale)
            nbytes = sum(size for _, _, size in stale.values()) or 1
            got = 0
            for idx, (path, (sha, _, size)) in enumerate(sorted(stale.items())):
                head = f"Downloading ({idx+1}/{total})"
                self._apply_sig.log.emit(f"PROG|{head}: {os.path.basename(path)}")
                dest = os.path.join(update_dir, path)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                # Bar fills by bytes across all files. The label shows this file's size and speed
                prog = lambda p, m, g=got, sz=size, h=head: self._apply_sig.progress.emit(
                    min(99, int((g + sz * p / 100) * 100 / nbytes)), f"{h}\n{m}")
                # net.download retries and rejects truncated streams. The hash check catches the rest
                download(f"{raw}/{urllib.parse.quote(path)}", dest, on_progress=prog,
                         label=os.path.basename(path), timeout=30, headers=_HDR)
                if git_blob_sha(dest) != sha:
                    raise RuntimeError(f"{path} does not match GitHub")
                got += size
            self._apply_sig.progress.emit(99, "Installing update...")

            # A syntax error pushed to main would otherwise brick every install on relaunch
            if not compileall.compile_dir(update_dir, quiet=1):
                raise RuntimeError("update has Python errors, nothing applied")

            # Copied over the old file, not renamed: offline copies hard-link some of these
            for path, (_, mode, _) in stale.items():
                target = os.path.join(install_dir, path)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(os.path.join(update_dir, path), target)
                if mode == "100755":
                    os.chmod(target, 0o755)

            # Delete files removed or renamed away upstream, so stale modules can never shadow current ones
            for path in gone:
                target = os.path.join(install_dir, path)
                if os.path.isfile(target):
                    os.remove(target)
                    _log.info("Removed stale file: %s", path)

            shutil.rmtree(update_dir, ignore_errors=True)

            # chmod +x shell scripts
            for script in ("launcher.sh", "deckops_uninstall.sh", "install.sh"):
                spath = os.path.join(install_dir, script)
                if os.path.isfile(spath):
                    os.chmod(spath, os.stat(spath).st_mode | stat.S_IEXEC)

            # Last, so an update that failed part way is retried in full
            with open(os.path.join(install_dir, "VERSION"), "w") as f:
                f.write(remote_sha)

            # Clean up stale flag file if present
            flag = os.path.expanduser("~/.deckops_update_requested")
            if os.path.isfile(flag):
                os.remove(flag)

            _log.info("Update applied successfully — SHA %s (%d file(s), %d removed)", remote_sha, total, len(gone))
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
            self._update_pd.setValue(100); self._update_pd.setLabelText(text)
            self._update_status.setText(text)
            self._update_status.setStyleSheet(f"color:{C_IW};")
            _kill_audio()
            QTimer.singleShot(1000, self._relaunch)
        else:
            # FAIL
            self._update_pd.close()
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
        """Relaunch DeckOps: exec the same Python with main.py."""
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
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._reset_deckops()

    def _reset_deckops(self):
        cfg.reset()
        self.status.setText("Config wiped. Restarting setup...")
        QTimer.singleShot(1500, lambda: go_to(self.stack, "BootstrapScreen"))



# --- UpdateScreen
class UpdateScreen(QWidget):
    """Runs game updates and one-off tasks (such as Offline Mode) started from ManagementScreen."""

    def __init__(self, stack):
        super().__init__(); self.stack = stack; self.screen_name = "UpdateScreen"
        self.update_zd = False
        self.selected   = []
        self.steam_root = ""
        # (title, fn(sigs)) run in place of the game updates, e.g. adding Offline Mode
        self.task = None
        self._steam_closed = threading.Event()

        lay = QVBoxLayout(self); lay.setContentsMargins(80,60,80,60); lay.setSpacing(20)
        self.title = QLabel("UPDATE"); self.title.setFont(font(36, True))
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

        self._log_status = _lbl("", 10, C_DIM, wrap=False)
        log_btn = _btn("Copy Log", C_DARK_BTN, size=11, h=40); log_btn.setFixedWidth(130)
        log_btn.clicked.connect(lambda: _copy_log_to_clipboard(self._log_status))
        lr = QHBoxLayout(); lr.addStretch(); lr.addWidget(log_btn); lr.addWidget(self._log_status); lr.addStretch()
        lay.addLayout(lr)

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
        self.log.appendHtml(_log_html(text))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
        _log_to_file(text)

    def showEvent(self, e):
        super().showEvent(e)
        self.bar.setValue(0); self.log.clear()
        self.title.setText(self.task[0] if self.task else "UPDATE")
        self.steam_btn.setVisible(False); self.back_btn.setVisible(False)
        self._steam_closed.clear()
        inhibit.start("DeckOps is updating")
        _log_to_file("── Update started ──")
        QTimer.singleShot(400, lambda: threading.Thread(target=self._run, daemon=True).start())

    def _on_done(self, _):
        inhibit.stop()
        self.cur.setText("Done! It is now safe to open Steam.")
        self.back_btn.setVisible(True)

    def _go_back(self):
        go_to(self.stack, "ManagementScreen")

    def _run(self):
        task, self.task = self.task, None
        if task:
            try:
                task[1](self._s)
            except Exception as ex:
                self._s.log.emit(f"✗  {task[0].title()} failed: {ex}")
            self._s.progress.emit(100, "All done!")
            self._s.done.emit(True)
            return
        from wrapper import get_proton_path, find_compatdata, kill_steam, set_compat_tool
        from ge_proton import install_ge_proton, MANAGED_APPIDS
        from iw4x import install_iw4x
        from cod4x import install_cod4x
        from cod4r import install_cod4r
        from iw3sp import install_iw3sp
        from t6sp_mod import install_t6sp_mod
        from cleanops import install_cleanops
        from t7x import install_t7x
        from net import DownloadError

        is_lcd = cfg.is_lcd()

        if is_lcd:
            from plutonium_lcd import (install_plutonium_lcd,
                                       launch_bootstrapper_lcd,
                                       is_plutonium_ready_lcd)
        else:
            from plutonium import (install_plutonium,
                                        launch_bootstrapper,
                                        is_plutonium_ready)

        has_cod4  = any(KEY_CLIENT.get(k) in ("cod4r", "cod4x", "iw3sp") for k, _, _ in self.selected)
        has_iw4x  = any(KEY_CLIENT.get(k) == "iw4x" for k, _, _ in self.selected)
        has_plut  = any(KEY_CLIENT.get(k) == "plutonium" for k, _, _ in self.selected)
        proton    = get_proton_path(self.steam_root)

        # Auto-expand: if any Plutonium key is selected, pull in all other
        # installed Plutonium games so the shared cache rebuild covers every
        # prefix (OLED) or every sideload entry (LCD).
        if has_plut:
            _PLUT_KEYS = {"t4sp","t4mp","t5sp","t5mp","t6mp","t6zm","iw5mp","iw5mp_ds"}
            already = {k for k, _, _ in self.selected}
            _all_installed = find_all_games(self.steam_root)
            # Find the right gd entry for each sibling key
            _gd_by_key = {}
            for gd_entry in ALL_GAMES:
                for k in _active_keys(gd_entry):
                    _gd_by_key[k] = gd_entry
            extras = []
            for pk in _PLUT_KEYS - already:
                if pk in _all_installed and cfg.is_game_setup(pk):
                    gd_entry = _gd_by_key.get(pk)
                    if gd_entry:
                        extras.append((pk, gd_entry, _all_installed[pk]))
            if extras:
                names = ", ".join(e[2].get("name", e[0]) for e in extras)
                self._s.log.emit(f"Also updating {len(extras)} sibling Plutonium game(s): {names}")
                self.selected.extend(extras)

        total = len(self.selected)

        # Read setup_games to determine source for each key
        setup_games = cfg.get_setup_games()

        # --- Plutonium update: re-run bootstrapper
        if has_plut:
            if is_lcd:
                self._s.progress.emit(5, "Setting up Plutonium through HGL...")
                self._s.log.emit(
                    "Setting up Plutonium through HGL...\n"
                    "  1. HGL will download and launch Plutonium (this may take a few minutes)\n"
                    "  2. Log in if prompted\n"
                    "  3. Close the Plutonium window\n"
                    "  4. Click the button below to continue"
                )
            else:
                self._s.progress.emit(5, "Launching Plutonium to check for updates...")
                self._s.log.emit(
                    "Plutonium is launching now.\n"
                    "  1. Wait for it to finish updating\n"
                    "  2. Log in if prompted\n"
                    "  3. Close the Plutonium window\n"
                    "  4. Click the button below to continue"
                )
            try:
                if is_lcd:
                    launch_bootstrapper_lcd(
                        on_progress=lambda p, m: self._s.progress.emit(p, m),
                    )
                else:
                    launch_bootstrapper(
                        proton,
                        on_progress=lambda p, m: self._s.progress.emit(p, m),
                        steam_root=self.steam_root,
                    )
            except DownloadError as dl_ex:
                self._s.log.emit(f"✗  {dl_ex.label} download failed: {dl_ex}")
                self._s.progress.emit(100, "Update failed.")
                self._s.done.emit(True)
                return
            except Exception as ex:
                self._s.log.emit(f"✗  Plutonium launch failed: {ex}")
                self._s.progress.emit(100, "Update failed.")
                self._s.done.emit(True)
                return

            self._s.plut_wait.emit()
            self._steam_closed.wait()
            self._steam_closed.clear()
            self._s.plut_go.emit()

            _ready = is_plutonium_ready_lcd() if is_lcd else is_plutonium_ready()
            if not _ready:
                self._s.log.emit(
                    "✗  Plutonium does not appear to be fully set up.\n"
                    "   Make sure you let it finish updating."
                )
                self._s.progress.emit(100, "Update incomplete.")
                self._s.done.emit(True)
                return

            self._s.log.emit("✓  Plutonium updated.")

            # Remove the old shared copy prefixes used to link to. OLED games
            # are reinstalled below and link to the master in the dedicated
            # prefix instead. LCD reads everything from the Heroic prefix.
            from plutonium import SHARED_PLUT_DIR
            if os.path.isdir(SHARED_PLUT_DIR):
                shutil.rmtree(SHARED_PLUT_DIR, ignore_errors=True)
                self._s.log.emit("  Removed the old shared Plutonium copy")

        # --- GE-Proton download (Steam may still be running)
        ge_version = None
        try:
            self._s.log.emit("Checking GE-Proton...")
            ge_version = install_ge_proton(
                on_progress=lambda pct, msg: self._s.progress.emit(2 + int(pct * 0.03), msg)
            )
            cfg.set_ge_proton_version(ge_version)
            self._s.log.emit(f"✓  {ge_version} ready")
        except Exception as ex:
            self._s.log.emit(f"  GE-Proton update skipped: {ex}")

        if not has_plut:
            self._s.progress.emit(5, "Closing Steam...")
            self._s.log.emit("Closing Steam...")
            try:
                kill_steam(on_progress=lambda msg: self._s.log.emit(f"  {msg}"))
                self._s.log.emit("  ✓ Steam closed.")
            except Exception as ex:
                self._s.log.emit(f"  Could not close Steam: {ex}")

        # --- Clean slate: clear launch options and compat tools
        # Same as InstallScreen, so stale entries from earlier installs
        # (LCD to OLED, older DeckOps versions) can't interfere with the update.
        # Launch options are cleared only for the Steam games in this update,
        # so a per-game update doesn't wipe other games' options.
        try:
            from wrapper import clear_launch_options, clear_compat_tool
            from detect_games import GAMES
            run_appids = {GAMES[k]["appid"] for k, _, g in self.selected
                          if k in GAMES and (g or {}).get("source") != "own"}
            for appid in MANAGED_APPIDS:
                if appid in run_appids:
                    clear_launch_options(self.steam_root, appid)
            clear_compat_tool(MANAGED_APPIDS)
            self._s.log.emit("✓  Cleared launch options and compat tools")
            if "7940" in run_appids:
                from iw3sp import apply_cod4_launch_option
                apply_cod4_launch_option(self.steam_root)
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
            # Prefer the client from the original install if available
            if key in ("cod4mp", "iw4sp", "iw5sp", "cod1sp", "coduosp", "cod2sp", "coduomp") and entry.get("client"):
                c = entry["client"]
            try:
                from plutonium import GAME_META as _PLUT_META
                from detect_games import GAMES as _GAMES_MAP
                if c == "plutonium" and key in _PLUT_META:
                    _appid = _PLUT_META[key][0]
                elif c == "alterware" and key in _GAMES_MAP:
                    _appid = _GAMES_MAP[key]["appid"]
                else:
                    _appid = gd["appid"]

                # Resolve compatdata. Own games may have a CRC-based prefix
                if source == "own":
                    compat = game.get("compatdata_path", "")
                    # Scanned games are not enriched here. Use the same
                    # prefix the install flow gave this own-copy game
                    # Despite its name, own_plut_prefix is the plain own-shortcut prefix
                    # for every key except t4mp, so CoD3 and Finest Hour use it too
                    if not compat and (c == "plutonium" and not cfg.is_lcd() or c in ("cod3recomp", "finesthour")):
                        from shortcut import own_plut_prefix
                        compat = own_plut_prefix(key, game)
                    if not compat:
                        compat = find_compatdata(self.steam_root, _appid,
                                                  game_install_dir=game.get("install_dir"))
                else:
                    compat = find_compatdata(self.steam_root, _appid,
                                              game_install_dir=game.get("install_dir"))
                if not compat and game.get("install_dir"):
                    steamapps = os.path.dirname(os.path.dirname(game["install_dir"]))
                    compat = os.path.join(steamapps, "compatdata", str(_appid))

                if c == "cod4r":
                    install_cod4r(game, self.steam_root, proton, compat, op,
                                  appid=gd["appid"], source=source)
                elif c == "cod4x":
                    install_cod4x(game, self.steam_root, proton, compat, op,
                                  appid=gd["appid"])
                elif c == "iw3sp":
                    install_iw3sp(game, self.steam_root, proton, compat, op,
                                  source=source)
                elif c == "iw4x":
                    install_iw4x(game, self.steam_root, proton, compat, op,
                                 source=source, install_dlc=False, force=True)
                elif c == "plutonium":
                    if is_lcd:
                        install_plutonium_lcd(game, key,
                                             installed_games=installed_for_plut,
                                             on_progress=op,
                                             steam_root=self.steam_root,
                                             proton_path=proton,
                                             compatdata_path=compat,
                                             source=source)
                    else:
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
                    if source == "own":
                        from shortcut import migrate_own_t6sp
                        migrate_own_t6sp(game, self._s.log.emit)
                elif c == "cod1x":
                    from cod1x import install_cod1x
                    install_cod1x(game, self.steam_root, op, source=game.get("source", "steam"))
                elif c == "coduox":
                    from coduox import install_coduox
                    install_coduox(game, op, source=game.get("source", "steam"))
                elif c == "cod2x":
                    from cod2x import install_cod2x
                    install_cod2x(game, self.steam_root, op, source=game.get("source", "steam"))
                elif c == "cod3recomp":
                    from cod3recomp import install_cod3
                    install_cod3(game, self.steam_root, proton, compat, op)
                elif c == "finesthour":
                    from finesthour import install_fh
                    install_fh(game, self.steam_root, proton, compat, op)
                elif c == "bro":
                    from bro import install_bro
                    install_bro(game, on_progress=op)
                elif c == "iw-pad":
                    from sp_mod import install_sp_mod
                    install_sp_mod(key, game["install_dir"], op,
                                   source=source, steam_root=self.steam_root)
                self._s.log.emit(f"✓  {base_name} ({key}) done")
                # Installs that mark themselves (Plutonium) just saved fresh paths
                entry = cfg.get_setup_games().get(key, entry)
                cfg.mark_game_setup(key, c, source=source,
                                    wrapper_path=entry.get("wrapper_path"),
                                    lan_wrapper_path=entry.get("lan_wrapper_path"))
            except Exception as ex:
                self._s.log.emit(f"✗  {base_name} ({key}) failed: {ex}")

        # --- Re-apply GE-Proton compat + Steam Input
        if ge_version:
            try:
                set_compat_tool(MANAGED_APPIDS, ge_version)
                self._s.log.emit(f"✓  {ge_version} set for Steam game appids")
            except Exception as ex:
                self._s.log.emit(f"  CompatToolMapping skipped: {ex}")

        try:
            from wrapper import set_steam_input_enabled
            set_steam_input_enabled(self.steam_root)
            self._s.log.emit("✓  Steam Input enabled for all games")
        except Exception as ex:
            self._s.log.emit(f"  Steam Input setup skipped: {ex}")

        # Steam WaW has Plutonium entries in its launch menu. A Deck default
        # from older installs would auto-pick Campaign and hide it.
        _setup = cfg.get_setup_games()
        if any(k in ("t4sp", "t4mp") and _setup.get(k, {}).get("source", "steam") == "steam"
                              for k, _, _ in self.selected):
            try:
                from wrapper import clear_default_launch_option
                clear_default_launch_option(self.steam_root, ["10090"])
            except Exception as ex:
                self._s.log.emit(f"  WaW launch picker reset skipped: {ex}")

        # Zombies Declassified: only when the user opted in on the Update Games prompt
        _do_zd = self.update_zd; self.update_zd = False
        if _do_zd and cfg.is_zd_installed() and any(k == "t6zm" for k, _, _ in self.selected):
            try:
                self._s.log.emit("Checking Zombies Declassified for updates...")
                from zombies_declassified import resolve_zd_storage
                _zd_storage = resolve_zd_storage({k: g for k, _, g in self.selected}.get("t6zm"))

                from zombies_declassified import is_zd_installed as _zd_at
                if not _zd_storage or not _zd_at(_zd_storage):
                    self._s.log.emit(f"⚠  Zombies Declassified not found in {_zd_storage}, skipped (nothing downloaded).")
                else:
                    from zombies_declassified import update_zd
                    updated = update_zd(_zd_storage,
                                        lambda p, m: self._s.log.emit(f"  ZD: {m}"))
                    if updated:
                        from zombies_declassified import get_zd_info as _zdi
                        info = _zdi(_zd_storage)
                        if info.get("manifest_hash"):
                            cfg.mark_zd_installed(info["manifest_hash"])
                        self._s.log.emit("✓  Zombies Declassified updated")
                    else:
                        self._s.log.emit("✓  Zombies Declassified is up to date")
            except Exception as ex:
                self._s.log.emit(f"⚠  Zombies Declassified update skipped: {ex}")

        # Clean up ZD files leaked into non-t6zm prefixes by older versions
        if has_plut and not is_lcd:
            try:
                from plutonium import cleanup_zd_from_other_prefixes
                n = cleanup_zd_from_other_prefixes(
                    {k: g for k, _, g in self.selected if g},
                    self.steam_root,
                    on_progress=lambda msg: self._s.log.emit(msg),
                )
                if n:
                    self._s.log.emit(f"✓  Cleaned ZD files from {n} prefix(es)")
            except Exception as ex:
                self._s.log.emit(f"  ZD cleanup skipped: {ex}")

        # Clean up Plutonium dirs leaked into non-Plutonium prefixes by older versions
        if has_plut and not is_lcd:
            try:
                from plutonium import cleanup_plut_from_non_plut_prefixes
                n = cleanup_plut_from_non_plut_prefixes(
                    self.steam_root,
                    on_progress=lambda msg: self._s.log.emit(msg),
                )
                if n:
                    self._s.log.emit(f"✓  Cleaned Plutonium from {n} non-Plutonium prefix(es)")
            except Exception as ex:
                self._s.log.emit(f"  Plutonium cleanup skipped: {ex}")

        self._s.progress.emit(100, "All done!")
        self._s.done.emit(True)
