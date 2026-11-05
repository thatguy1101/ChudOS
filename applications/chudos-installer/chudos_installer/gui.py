"""ChudOS Installer window (PySide6). Runs as the normal user; the only privileged step is
`sudo -n chudos-install-backend`, fed one JSON request on stdin (the password never touches argv or disk)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from . import __version__
from .disks import human_size, list_disks
from .form import Form
from .settings import KEYBOARDS, LOCALES

BACKEND_ARGV = ["sudo", "-n", "chudos-install-backend"]
TERMINAL_HINT = ("Need a terminal? Press Ctrl+Alt+F3 (or F4-F6) for a text console, "
                 "and Ctrl+Alt+F1 or F2 to come back to this window.")


def timezones(root: Path = Path("/usr/share/zoneinfo")) -> list[str]:
    out = []
    for p in sorted(root.glob("*/*")):
        if p.is_file() and p.parent.name[:1].isupper() and p.parent.name not in {"Etc", "SystemV", "US", "Brazil", "Canada", "Chile", "Mexico"}:
            out.append(f"{p.parent.name}/{p.name}")
    return out or ["UTC"]


def build_window(disks_fn=list_disks, tz_fn=timezones, start_backend=None):
    from PySide6.QtCore import QProcess, Qt
    from PySide6.QtWidgets import (QComboBox, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QProgressBar,
                                   QPushButton, QStackedWidget, QVBoxLayout, QHBoxLayout, QWidget, QFormLayout)

    form = Form()
    win = QWidget(); win.setWindowTitle("Install ChudOS"); win.resize(720, 520)
    outer = QVBoxLayout(win)
    stack = QStackedWidget(); outer.addWidget(stack, 1)
    err = QLabel(""); err.setStyleSheet("color: #d9534f;"); err.setWordWrap(True); outer.addWidget(err)
    nav = QHBoxLayout(); back = QPushButton("Back"); nxt = QPushButton("Continue"); nav.addStretch(1); nav.addWidget(back); nav.addWidget(nxt); outer.addLayout(nav)
    hint = QLabel(TERMINAL_HINT); hint.setWordWrap(True); hint.setStyleSheet("color: gray;"); outer.addWidget(hint)

    def page(title, body=None):
        w = QWidget(); l = QVBoxLayout(w); h = QLabel(title); h.setStyleSheet("font-size: 20px; font-weight: 600;"); l.addWidget(h)
        if body:
            b = QLabel(body); b.setWordWrap(True); l.addWidget(b)
        return w, l

    # 0 welcome
    p0, l0 = page("Install ChudOS", f"ChudOS {__version__} (early prototype). This installer will ERASE ONE WHOLE DISK and install ChudOS on it.\n\n"
                  "Requirements: a UEFI computer (in a VM, enable EFI), an internet connection, and a disk of at least 20 GiB whose contents you do not need.\n"
                  "Dual-boot and keeping existing data are not supported yet.")
    l0.addStretch(1); stack.addWidget(p0)
    # 1 disk
    p1, l1 = page("Choose the disk to erase", "Nothing is selected for you. Greyed-out disks cannot be used."); lst = QListWidget(); l1.addWidget(lst)
    refresh = QPushButton("Rescan disks"); l1.addWidget(refresh); stack.addWidget(p1)
    def fill_disks():
        lst.clear(); form.disk = ""; form.usable_disks = set()
        for d in disks_fn():
            text = f"{d.path}   {human_size(d.size_bytes)}   {d.model or 'unknown model'}"
            if d.contents: text += "\n    now contains: " + "; ".join(d.contents[:4])
            if not d.usable: text += f"\n    unavailable: {d.reason}"
            it = QListWidgetItem(text); it.setData(Qt.UserRole, d.path)
            if not d.usable: it.setFlags(it.flags() & ~Qt.ItemIsSelectable & ~Qt.ItemIsEnabled)
            else: form.usable_disks.add(d.path)
            lst.addItem(it)
    refresh.clicked.connect(fill_disks)
    lst.currentItemChanged.connect(lambda cur, _p: setattr(form, "disk", cur.data(Qt.UserRole) if cur else ""))
    # 2 user
    p2, l2 = page("Who are you?"); fl = QFormLayout(); l2.addLayout(fl); l2.addStretch(1); stack.addWidget(p2)
    f_name, f_host, f_user, f_pw, f_pw2 = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
    f_pw.setEchoMode(QLineEdit.Password); f_pw2.setEchoMode(QLineEdit.Password)
    f_tz = QComboBox(); f_tz.addItems(tz_fn())
    for lab, w in (("Your name", f_name), ("Computer name", f_host), ("Username", f_user), ("Password", f_pw), ("Repeat password", f_pw2), ("Time zone", f_tz)):
        fl.addRow(lab, w)
    # 3 language
    p3, l3 = page("Language and keyboard"); fl3 = QFormLayout(); l3.addLayout(fl3); l3.addStretch(1); stack.addWidget(p3)
    f_loc, f_key = QComboBox(), QComboBox()
    for lab, v in LOCALES: f_loc.addItem(lab, v)
    for k in KEYBOARDS: f_key.addItem(k[0], k[1])
    fl3.addRow("Language", f_loc); fl3.addRow("Keyboard", f_key)
    # 4 summary + confirm
    p4, l4 = page("Ready to erase and install"); summ = QLabel(); summ.setWordWrap(True); l4.addWidget(summ)
    warn = QLabel(); warn.setWordWrap(True); warn.setStyleSheet("color: #d9534f; font-weight: 600;"); l4.addWidget(warn)
    f_conf = QLineEdit(); l4.addWidget(f_conf); l4.addStretch(1); stack.addWidget(p4)
    # 5 progress
    p5, l5 = page("Installing..."); bar = QProgressBar(); l5.addWidget(bar); stepl = QLabel(""); l5.addWidget(stepl)
    log = QPlainTextEdit(); log.setReadOnly(True); l5.addWidget(log); stack.addWidget(p5)
    # 6 done
    p6, l6 = page("Done"); res = QLabel(); res.setWordWrap(True); l6.addWidget(res); l6.addStretch(1); stack.addWidget(p6)

    def collect():
        form.fullname, form.hostname, form.username = f_name.text(), f_host.text().strip(), f_user.text().strip()
        form.password, form.password2, form.timezone = f_pw.text(), f_pw2.text(), f_tz.currentText()
        form.locale, form.keymap = f_loc.currentData(), f_key.currentData()
        form.confirm = f_conf.text().strip()

    def update_summary():
        collect()
        summ.setText(f"Disk: {form.disk}\nUser: {form.username} ({form.fullname})\nComputer name: {form.hostname}\nTime zone: {form.timezone}\n"
                     f"Language: {f_loc.currentText()}   Keyboard: {f_key.currentText()}")
        warn.setText(f"EVERYTHING on {form.disk} will be permanently erased. To continue, type the disk name exactly: {form.disk}")

    state = {"proc": None, "running": False, "lines": []}

    def refresh_nav():
        i = stack.currentIndex(); collect()
        back.setEnabled(0 < i < 5 and not state["running"]); back.setVisible(i < 5)
        nxt.setVisible(i < 6 or True)
        nxt.setText({0: "Continue", 4: "Erase and install", 5: "Installing...", 6: "Restart now"}.get(i, "Continue"))
        ok = {0: True, 1: not form.disk_error(), 2: not form.user_errors(), 3: True, 4: form.confirm_ok(), 5: False, 6: True}[i]
        nxt.setEnabled(ok); err.setText("")
        if i == 1 and form.disk_error() and form.disk: err.setText(form.disk_error())

    def on_event(ev):
        t = ev.get("type")
        if t == "step":
            bar.setMaximum(ev["n"]); bar.setValue(ev["i"]); stepl.setText(ev["title"])
        elif t == "log":
            log.appendPlainText(ev["line"])
        elif t == "error":
            state["running"] = False; stack.setCurrentIndex(6)
            extra = "Your disk was NOT changed." if not ev.get("disk_modified") else "The disk was partly modified; the installation did not finish."
            res.setText(f"Installation failed at: {ev.get('step')}\n{ev.get('message')}\n\n{extra}\nYou can use Ctrl+Alt+F3 for a terminal, or close this window and try again.")
            nxt.setText("Close"); nxt.setEnabled(True); state["failed"] = True
        elif t == "done":
            state["running"] = False; stack.setCurrentIndex(6)
            res.setText("ChudOS is installed. Remove the installation USB/ISO, then restart."); nxt.setText("Restart now"); nxt.setEnabled(True)

    def feed(chunk):
        state["buf"] = state.get("buf", "") + chunk
        while "\n" in state["buf"]:
            line, state["buf"] = state["buf"].split("\n", 1)
            if not line.strip(): continue
            try: on_event(json.loads(line))
            except ValueError: log.appendPlainText(line)

    def start():
        req = json.dumps(form.request())
        stack.setCurrentIndex(5); state["running"] = True; refresh_nav()
        if start_backend:                                  # test hook
            start_backend(req, feed); return
        p = QProcess(win); state["proc"] = p
        p.readyReadStandardOutput.connect(lambda: feed(bytes(p.readAllStandardOutput()).decode("utf-8", "replace")))
        p.readyReadStandardError.connect(lambda: log.appendPlainText(bytes(p.readAllStandardError()).decode("utf-8", "replace").rstrip()))
        p.finished.connect(lambda code, _s: (None if not state["running"] else on_event({"type": "error", "step": "backend", "message": f"The installer backend stopped unexpectedly (exit {code}).", "disk_modified": True})))
        p.start(BACKEND_ARGV[0], BACKEND_ARGV[1:]); p.write(req.encode()); p.closeWriteChannel()

    def go_next():
        i = stack.currentIndex(); collect()
        if i == 6:
            if state.get("failed"): win.close()
            else: QProcess.startDetached("systemctl", ["reboot"]); 
            return
        if i == 4:
            if form.confirm_ok(): start()
            return
        if i == 1 and not form.disk_error() or i in (0, 2, 3) and (i != 2 or not form.user_errors()):
            stack.setCurrentIndex(i + 1)
            if i + 1 == 4: update_summary()
        refresh_nav()

    def go_back():
        if stack.currentIndex() > 0 and not state["running"]: stack.setCurrentIndex(stack.currentIndex() - 1); refresh_nav()

    nxt.clicked.connect(go_next); back.clicked.connect(go_back)
    for w in (f_name, f_host, f_user, f_pw, f_pw2, f_conf): w.textChanged.connect(lambda *_: (update_summary() if stack.currentIndex() == 4 else collect(), refresh_nav()))
    lst.currentItemChanged.connect(lambda *_: refresh_nav()); f_tz.currentIndexChanged.connect(lambda *_: refresh_nav())
    def closer(ev):
        if state["running"]: ev.ignore()                   # no cancel once the disk is being modified
        else: ev.accept()
    win.closeEvent = closer
    fill_disks(); refresh_nav()
    win._ctl = dict(form=form, stack=stack, nxt=nxt, back=back, lst=lst, f_name=f_name, f_host=f_host, f_user=f_user, f_pw=f_pw, f_pw2=f_pw2,
                    f_tz=f_tz, f_conf=f_conf, go_next=go_next, state=state, res=res, bar=bar, log=log, err=err, feed=feed)
    return win


def main(argv=None) -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("chudos-installer: PySide6 is not installed.", file=sys.stderr); return 2
    app = QApplication(sys.argv[:1]); app.setApplicationName("chudos-installer")
    w = build_window(); w.show(); return app.exec()
