"""
ui_manifest.py: optional manifest mods step before the game scan

Lists manifest .json files found in the Games folders, lets the user
tick mods, pick one option each, enter the shared CDN and a target
Games folder, then installs. The screen skips itself when no manifests exist.
"""

import html, os, threading

from qt import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QScrollArea, QCheckBox, QPushButton,
    QButtonGroup, QProgressBar, QLineEdit, QPlainTextEdit,
)
from qt import Qt

import inhibit
import manifest_mods as mm
from net import _fmt_size

from ui_constants import (
    C_CARD, C_IW, C_TREY, C_DIM, C_DARK_BTN,
    font, _btn, _lbl, _badge, _header_bar, _log_to_file, _log_html, _copy_log_to_clipboard, _Sigs, go_to,
)

_NEXT_TO_JSON = "@json"
_BOX_CSS = f"color:#CCC;background:#1A1A2A;border:1px solid {C_DIM};border-radius:8px;padding:10px 16px;"


def _pill(text):
    b = QPushButton(text); b.setCheckable(True); b.setFont(font(10, True)); b.setFixedHeight(34)
    b.setStyleSheet(
        f"QPushButton{{background:{C_DARK_BTN};color:#AAA;border:none;border-radius:6px;padding:0 12px;}}"
        f"QPushButton:checked{{background:{C_IW};color:#FFF;}}")
    return b


class ManifestModsScreen(QWidget):
    def __init__(self, stack):
        super().__init__(); self.stack = stack; self.screen_name = "ManifestModsScreen"
        self._found = []; self._rows = []; self._busy = False; self._roots = []

        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        lay.addWidget(_header_bar()[0])

        # --- pick view
        self._pick = QWidget(); clay = QVBoxLayout(self._pick); clay.setContentsMargins(60,20,60,30); clay.setSpacing(12)
        self.status = _lbl("Looking for mod manifests...", 13, C_DIM); clay.addWidget(self.status)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._lw = QWidget(); self._list = QVBoxLayout(self._lw)
        self._list.setContentsMargins(0,0,0,0); self._list.setSpacing(10); self._list.addStretch()
        scroll.setWidget(self._lw); clay.addWidget(scroll, stretch=1)

        crow = QHBoxLayout(); crow.setSpacing(12)
        crow.addWidget(_lbl("Mod CDN:", 13, "#FFF", bold=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, wrap=False))
        self.cdn = QLineEdit(); self.cdn.setPlaceholderText("cdn.example.com/mods"); self.cdn.setFixedHeight(44)
        self.cdn.setFont(font(13))
        self.cdn.setStyleSheet(f"QLineEdit{{background:{C_CARD};color:#FFF;border:2px solid #33333F;"
                               f"border-radius:8px;padding:0 14px;}}QLineEdit:focus{{border-color:{C_IW};}}")
        crow.addWidget(self.cdn, 1); clay.addLayout(crow)

        self._root_row = QHBoxLayout(); self._root_row.setSpacing(8)
        self._root_row.addWidget(_lbl("Install to:", 13, "#FFF", bold=True, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, wrap=False))
        self._root_row.addSpacing(4)
        self._root_grp = QButtonGroup(self); self._root_grp.buttonClicked.connect(lambda _b: self._refresh_rows())
        self._root_row.addStretch(); clay.addLayout(self._root_row)

        self.warning = _lbl("", 12, C_TREY, align=Qt.AlignmentFlag.AlignLeft); self.warning.setVisible(False); clay.addWidget(self.warning)

        brow = QHBoxLayout(); brow.setSpacing(16)
        self.back = _btn("<< Back", C_DARK_BTN, h=52); self.back.setFixedWidth(180)
        self.back.clicked.connect(lambda: go_to(self.stack, "SetupFlowScreen"))
        self.skip = _btn("Skip >>", C_DARK_BTN, h=52); self.skip.setFixedWidth(200)
        self.skip.clicked.connect(lambda: go_to(self.stack, "WelcomeScreen"))
        self.inst = _btn("Install Selected", C_IW, h=52); self.inst.clicked.connect(self._install)
        brow.addWidget(self.back); brow.addWidget(self.skip); brow.addWidget(self.inst, 1); clay.addLayout(brow)
        lay.addWidget(self._pick, stretch=1)

        # --- install view, same layout as the game install screen
        self._run = QWidget(); rlay = QVBoxLayout(self._run); rlay.setContentsMargins(80,20,80,60); rlay.setSpacing(20)
        self.cur = _lbl("Preparing...", 16, "#CCC"); rlay.addWidget(self.cur)
        self.bar = QProgressBar(); self.bar.setMaximum(100); self.bar.setTextVisible(False); self.bar.setFixedHeight(22)
        bw = QHBoxLayout(); bw.setContentsMargins(60,0,60,0); bw.addWidget(self.bar); rlay.addLayout(bw)

        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setFont(font(11))
        self.log.setStyleSheet("QPlainTextEdit{color:#666677;background:transparent;border:none;padding:10px;}")
        rlay.addWidget(self.log, stretch=1)
        self._log_status = _lbl("", 11, C_DIM, wrap=False)
        log_btn = _btn("Copy Log", C_DARK_BTN, size=11, h=40); log_btn.setFixedWidth(130)
        log_btn.clicked.connect(lambda: _copy_log_to_clipboard(self._log_status))
        lr = QHBoxLayout(); lr.addStretch(); lr.addWidget(log_btn); lr.addWidget(self._log_status); lr.addStretch()
        rlay.addLayout(lr)

        self.summary = _lbl("", 12, "#CCC", align=Qt.AlignmentFlag.AlignLeft); self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.summary.setStyleSheet(_BOX_CSS); self.summary.setVisible(False)
        sw = QHBoxLayout(); sw.addStretch(); sw.addWidget(self.summary, 3); sw.addStretch(); rlay.addLayout(sw)

        self.mods_btn = _btn("<< Back to Mods", C_DARK_BTN, size=13, h=52); self.mods_btn.setFixedWidth(280)
        self.mods_btn.clicked.connect(self._show_pick)
        self.cont = _btn("Continue  >>", C_IW, size=13, h=52); self.cont.setFixedWidth(320)
        self.cont.clicked.connect(lambda: go_to(self.stack, "WelcomeScreen"))
        cw = QHBoxLayout(); cw.addStretch(); cw.addWidget(self.mods_btn); cw.addSpacing(12); cw.addWidget(self.cont); cw.addStretch()
        rlay.addLayout(cw)
        self._run.setVisible(False); lay.addWidget(self._run, stretch=1)

    def showEvent(self, e):
        super().showEvent(e)
        if self._busy: return
        self._show_pick(); self._set_enabled(False)
        self.status.setText("Looking for mod manifests...")
        self._sigs = _Sigs(); self._sigs.done.connect(self._on_scanned)
        threading.Thread(target=self._scan, daemon=True).start()

    def _show_pick(self):
        self._run.setVisible(False); self._pick.setVisible(True); self.warning.setVisible(False)

    def _scan(self):
        try:
            self._found = mm.scan_manifests(); self._roots = mm.games_roots()
        except Exception as ex:
            _log_to_file(f"[ManifestModsScreen] scan failed: {ex}"); self._found = []
        self._sigs.done.emit(bool(self._found))

    def _on_scanned(self, any_found):
        # Nothing to offer: go straight on to the game scan.
        if not any_found:
            go_to(self.stack, "WelcomeScreen"); return
        ok = [f for f in self._found if "manifest" in f]; bad = len(self._found) - len(ok)
        self.status.setText(f"{len(ok)} mod(s) found in your Games folder. Tick the ones to install, "
                            "or skip to the game scan." + (f" {bad} could not be read." if bad else ""))
        if not self.cdn.text(): self.cdn.setText(mm.get_saved_cdn())
        self._build_roots(); self._build_rows(); self._set_enabled(True)

    def _build_roots(self):
        for b in self._root_grp.buttons():
            self._root_grp.removeButton(b); b.deleteLater()
        home = os.path.expanduser("~")
        # Default: each mod goes to the Games folder its manifest is in. Picking a drive sends every mod there.
        for r in [_NEXT_TO_JSON] + self._roots:
            b = _pill("Next to each manifest" if r == _NEXT_TO_JSON else
                      "Internal: ~/" + os.path.relpath(r, home) if r.startswith(home + os.sep) else f"SD / drive: {r}")
            b.setProperty("root", r); b.setChecked(r == _NEXT_TO_JSON)
            self._root_grp.addButton(b); self._root_row.insertWidget(self._root_row.count() - 1, b)

    def _root(self):
        b = self._root_grp.checkedButton()
        return b.property("root") if b else ""

    def _target(self, r):
        root = self._root()
        return r["dir"] if root == _NEXT_TO_JSON else root

    def _build_rows(self):
        while self._list.count() > 1:
            it = self._list.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        self._rows = []
        for f in self._found:
            card = QFrame(); card.setObjectName("mmcard")
            card.setStyleSheet(f"QFrame#mmcard{{background:{C_CARD};border-top:3px solid #333344;border-radius:8px;}}")
            v = QVBoxLayout(card); v.setContentsMargins(16,12,16,12); v.setSpacing(6)
            if "error" in f:
                v.addWidget(_lbl(f"{f['file']}: {f['error']}", 11, C_DIM, align=Qt.AlignmentFlag.AlignLeft))
                self._list.insertWidget(self._list.count() - 1, card); continue
            m = f["manifest"]
            head = QHBoxLayout(); head.setSpacing(10)
            cb = QCheckBox(m["name"]); cb.setFont(font(13, True)); cb.setStyleSheet("color:#FFF;background:transparent;")
            head.addWidget(cb)
            if m["version"]: head.addWidget(_lbl(f"v{m['version']}", 11, C_DIM, align=Qt.AlignmentFlag.AlignLeft, wrap=False))
            head.addStretch()
            state = _badge("", C_IW, 110, h=24, size=9, radius=4); state.setVisible(False); head.addWidget(state)
            v.addLayout(head)
            if m["description"]: v.addWidget(_lbl(m["description"], 10, "#777788", align=Qt.AlignmentFlag.AlignLeft))
            orow = QHBoxLayout(); orow.setContentsMargins(32,0,0,0); orow.setSpacing(8)
            if m["mode"] == "components":
                grp, boxes = None, []
                for c in m["components"]:
                    if not c["show"]: continue
                    ob = QCheckBox(f"{c['name']}  ({_fmt_size(sum(x['size'] for x in c['files']))})"); ob.setFont(font(11))
                    ob.setStyleSheet("color:#CCC;background:transparent;"); ob.setProperty("oid", c["id"])
                    ob.setProperty("req", c["required"]); ob.setProperty("def", c["default"])
                    ob.setChecked(c["required"] or c["default"]); ob.setEnabled(not c["required"])
                    if c["description"]: ob.setToolTip(c["description"])
                    # Ticking a part ticks the mod without re-running the mod's check-all.
                    ob.toggled.connect(lambda on, mc=cb: (on and not mc.isChecked() and (mc.blockSignals(True), mc.setChecked(True), mc.blockSignals(False)),
                                                          self._update_total()))
                    boxes.append(ob); orow.addWidget(ob); orow.addSpacing(10)
                cb.toggled.connect(lambda on, bs=boxes: ([b.setChecked(on) for b in bs if not b.property("req")], self._update_total()))
            else:
                grp, boxes = QButtonGroup(card), None
                for i, o in enumerate(m["options"]):
                    b = _pill(f"{o['name']}  ({_fmt_size(mm.total_size(o))})"); b.setProperty("oid", o["id"]); b.setChecked(i == 0)
                    if o["description"]: b.setToolTip(o["description"])
                    grp.addButton(b); orow.addWidget(b)
                cb.toggled.connect(lambda _on: self._update_total())
                grp.buttonClicked.connect(lambda _b, mc=cb: (mc.setChecked(True), self._update_total()))
            orow.addStretch(); v.addLayout(orow)
            self._rows.append({"m": m, "dir": os.path.dirname(f["path"]), "cb": cb, "grp": grp, "boxes": boxes, "state": state, "card": card})
            self._list.insertWidget(self._list.count() - 1, card)
        self._refresh_rows()

    def _set_state(self, r, text, color):
        r["card"].setStyleSheet(f"QFrame#mmcard{{background:{C_CARD};border-top:3px solid {color or '#333344'};border-radius:8px;}}")
        b = r["state"]; b.setVisible(bool(text)); b.setText(text)
        b.setStyleSheet(f"QPushButton{{background:{color};color:#FFF;border:none;border-radius:4px;}}"
                        f"QPushButton:disabled{{background:{color};color:#FFF;}}")

    def _refresh_rows(self):
        for r in self._rows:
            root = self._target(r); mid = r["m"]["id"]; iroot = mm.install_root(root, r["m"]) if root else ""
            rec = mm.get_receipt(iroot, mid) if iroot else {}
            if r["boxes"] is not None:
                # Tick what is installed in this Games folder, so installing more parts keeps the old ones.
                have = set((rec.get("option") or "").split("+")) if rec else None
                for b in r["boxes"]:
                    if b.property("req"): continue
                    b.blockSignals(True); b.setChecked(b.property("oid") in have if have is not None else bool(b.property("def"))); b.blockSignals(False)
            elif rec.get("option"):
                for b in r["grp"].buttons():
                    if b.property("oid") == rec["option"]: b.setChecked(True)
            if not rec:
                self._set_state(r, "", "")
            elif not rec.get("complete"):
                self._set_state(r, "INCOMPLETE", C_TREY); r["state"].setToolTip("Install again to finish")
            elif mm.needs_update(r["m"], iroot):
                self._set_state(r, "UPDATE", C_TREY); r["state"].setToolTip("")
            else:
                try: name = mm.get_option(r["m"], rec.get("option"))["name"]
                except mm.ManifestError: name = ""
                self._set_state(r, "INSTALLED", C_IW); r["state"].setToolTip(name)
        self._update_total()

    def _selected(self):
        out = []
        for r in self._rows:
            if not r["cb"].isChecked(): continue
            if r["boxes"] is not None:
                out.append((r["m"], "+".join(b.property("oid") for b in r["boxes"] if b.isChecked()), self._target(r)))
            elif r["grp"].checkedButton():
                out.append((r["m"], r["grp"].checkedButton().property("oid"), self._target(r)))
        return out

    def _update_total(self):
        sel = self._selected()
        size = sum(mm.total_size(mm.get_option(m, oid)) for m, oid, _r in sel)
        self.inst.setText(f"Install Selected ({_fmt_size(size)})" if sel else "Install Selected")
        self.inst.setEnabled(bool(sel) and not self._busy)

    def _set_enabled(self, on):
        self.back.setEnabled(on); self.skip.setEnabled(on); self.cdn.setEnabled(on); self._lw.setEnabled(on)
        for b in self._root_grp.buttons(): b.setEnabled(on)
        if on: self._update_total()
        else: self.inst.setEnabled(False)

    def _warn(self, text):
        self.warning.setText(text); self.warning.setVisible(True)

    def _install(self):
        sel = self._selected()
        if not sel: return
        if not self._root(): self._warn("Choose where to install the mods."); return
        try:
            cdn = mm.normalize_cdn(self.cdn.text())
        except mm.ManifestError as ex:
            self._warn(f"Mod CDN: {ex}"); return
        self._busy = True; self._set_enabled(False)
        self._pick.setVisible(False); self._run.setVisible(True)
        self.cur.setText("Preparing..."); self.cur.setStyleSheet("color:#CCC;background:transparent;")
        self.bar.setValue(0); self.log.clear(); self._log_status.setVisible(False)
        self.summary.setVisible(False); self.mods_btn.setVisible(False); self.cont.setVisible(False)
        self._isigs = _Sigs()
        self._isigs.progress.connect(lambda p, m: (self.bar.setValue(p), self.cur.setText(m)))
        self._isigs.log.connect(self._append_log)
        self._isigs.done.connect(self._on_installed)
        threading.Thread(target=self._do_install, args=(sel, cdn), daemon=True).start()

    def _do_install(self, sel, cdn):
        self._results = []; n = len(sel)
        log = self._isigs.log.emit
        inhibit.start("DeckOps is installing mods")
        try:
            for i, (m, oid, root) in enumerate(sel):
                opt = mm.get_option(m, oid)
                log(f"--- {m['name']} ({opt['name']}) ---")
                tag = f"[{i + 1}/{n}] {m['name']}: "
                cb = lambda p, msg, _i=i, _t=tag: self._isigs.progress.emit(int((_i * 100 + p) / n), _t + msg)
                try:
                    errs = mm.install_manifest(m, oid, cdn, root, cb, on_log=log)
                    if errs:
                        log(f"✗ {len(errs)} file(s) failed")
                    else:
                        log(f"✓ {opt['name']} installed")
                    self._results.append((m, oid, errs, ""))
                except mm.ManifestError as ex:
                    log(f"✗ {ex}")
                    self._results.append((m, oid, None, str(ex)))
                except Exception as ex:
                    _log_to_file(f"[ManifestModsScreen] {m['id']} install failed: {ex}")
                    log(f"✗ unexpected error: {ex}")
                    self._results.append((m, oid, None, "unexpected error, see log"))
        finally:
            inhibit.stop()
        self._isigs.done.emit(all(e == [] for _m, _o, e, _x in self._results))

    def _append_log(self, text):
        _log_to_file(text)
        sb = self.log.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        self.log.appendHtml(_log_html(text))
        if at_bottom: sb.setValue(sb.maximum())

    def _on_installed(self, all_ok):
        self._busy = False; self.bar.setValue(100)
        lines = []
        for m, oid, errs, msg in self._results:
            name = html.escape(f"{m['name']} ({mm.get_option(m, oid)['name']})")
            if errs == []:
                lines.append(f'<span style="color:{C_IW}">&#10003; {name} installed</span>')
            elif errs:
                lines.append(f'<span style="color:{C_TREY}">&#10007; {name}: {len(errs)} file(s) failed. '
                             f'Install again to retry only those.</span>')
            else:
                lines.append(f'<span style="color:{C_TREY}">&#10007; {name}: {html.escape(msg)}</span>')
        self.summary.setText("<br>".join(lines)); self.summary.setVisible(True)
        self.cur.setText("Mods installed!" if all_ok else "Finished with errors.")
        self.cur.setStyleSheet(f"color:{C_IW if all_ok else C_TREY};background:transparent;")
        self.mods_btn.setVisible(True); self.cont.setVisible(True)
        self._set_enabled(True); self._refresh_rows()
