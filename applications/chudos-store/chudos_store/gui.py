"""ChudOS Store window (PySide6). UI only: every package operation goes through pacman.Pacman.
Never runs as root; install/remove ask for confirmation first and then for polkit authorisation."""
from __future__ import annotations

import os
import sys

from .catalogue import entries
from .pacman import PROTECTED, Pacman, StoreError


def build_window(pm: Pacman | None = None, confirm=None, geteuid=os.geteuid):
    from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
    from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                                   QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

    pm = pm or Pacman()
    if confirm is None:
        confirm = lambda title, text: QMessageBox.question(win, title, text) == QMessageBox.Yes  # noqa: E731

    class Sig(QObject):
        line = Signal(str)
        done = Signal(object)

    class Job(QRunnable):
        def __init__(self, fn):
            super().__init__(); self.fn = fn; self.sig = Sig()
        def run(self):
            try:
                self.sig.done.emit(self.fn(self.sig.line.emit))
            except Exception as exc:  # noqa: BLE001 - shown to the user
                self.sig.done.emit(exc)

    win = QWidget(); win._jobs = []
    win.setWindowTitle("ChudOS Store"); win.resize(860, 520)
    root = QVBoxLayout(win)
    top = QHBoxLayout(); root.addLayout(top)
    box = QLineEdit(); box.setPlaceholderText("Search packages (letters, digits, . _ + @ -)"); box.setAccessibleName("Search")
    b_search, b_rec = QPushButton("Search"), QPushButton("Recommended")
    for w in (box, b_search, b_rec):
        top.addWidget(w)
    mid = QHBoxLayout(); root.addLayout(mid, 1)
    lst = QListWidget(); lst.setAccessibleName("Results"); mid.addWidget(lst, 1)
    info = QPlainTextEdit(); info.setReadOnly(True); info.setAccessibleName("Package information"); mid.addWidget(info, 1)
    acts = QHBoxLayout(); root.addLayout(acts)
    b_install, b_remove = QPushButton("Install…"), QPushButton("Remove…")
    acts.addWidget(b_install); acts.addWidget(b_remove); acts.addStretch(1)
    log = QPlainTextEdit(); log.setReadOnly(True); log.setMaximumHeight(130); log.setAccessibleName("Progress"); root.addWidget(log)
    status = QLabel(""); status.setWordWrap(True); status.setAccessibleName("Status"); root.addWidget(status)
    state = {"busy": False}

    def say(level, text):
        status.setText(text); status.setStyleSheet({"ok": "color:#2e8b57;", "warn": "color:#b8860b;", "error": "color:#d9534f;"}[level])

    def set_busy(b):
        state["busy"] = b
        for w in (b_search, b_rec, b_install, b_remove, box):
            w.setEnabled(not b and geteuid() != 0)
        if not b:
            update_buttons()

    def selected():
        it = lst.currentItem()
        return it.data(Qt.UserRole) if it else None

    def update_buttons():
        name = selected()
        b_install.setEnabled(bool(name) and not state["busy"] and geteuid() != 0)
        b_remove.setEnabled(bool(name) and name not in PROTECTED and not state["busy"] and geteuid() != 0)

    def run_bg(fn, on_done, on_line=None):
        job = Job(fn)
        if on_line:
            job.sig.line.connect(on_line)
        job.sig.done.connect(on_done); win._jobs.append(job)
        QThreadPool.globalInstance().start(job)

    def fill(rows):
        lst.clear()
        for name, text in rows:
            it = QListWidgetItem(text); it.setData(Qt.UserRole, name); lst.addItem(it)
        update_buttons()

    def search():
        q = box.text(); set_busy(True); say("ok", "Searching…")
        def done(res):
            set_busy(False)
            if isinstance(res, Exception):
                return say("error", res.message if isinstance(res, StoreError) else str(res))
            fill([(p.name, f"{'● ' if p.installed else '   '}{p.name} {p.version}  ({p.repo})") for p in res])
            say("ok" if res else "warn", f"{len(res)} result(s)." if res else "No packages found.")
        run_bg(lambda _l: pm.search(q), done)

    def recommended():
        set_busy(True); say("ok", "Loading recommended apps…")
        def work(_l):
            rows = []
            for e in entries():
                try:
                    inst = pm.is_installed(e["name"])
                except StoreError:
                    inst = False
                rows.append((e["name"], f"{'● ' if inst else '   '}{e['name']}  [{e['category']}]  {e['why']}"))
            return rows
        def done(res):
            set_busy(False)
            if isinstance(res, Exception):
                return say("error", str(res))
            fill(res); say("ok", "Recommended apps. ● = installed. Availability is checked when you select one.")
        run_bg(work, done)

    def show_info():
        name = selected(); update_buttons()
        if not name:
            return
        def done(res):
            if isinstance(res, Exception):
                info.setPlainText(res.message if isinstance(res, StoreError) else str(res)); return
            keys = ("Name", "Version", "Description", "Repository", "URL", "Licenses", "Download Size", "Installed Size", "Depends On", "Installed")
            info.setPlainText("\n".join(f"{k}: {res[k]}" for k in keys if k in res))
        run_bg(lambda _l: pm.info(name), done)

    def operate(verb):
        name = selected()
        if not name or state["busy"]:
            return
        if not confirm(f"{verb} {name}", f"{verb} '{name}'?\n\nYou will be asked for your password. Package signatures are always verified."
                       + ("\nOnly this package is removed; removal is refused if other packages need it." if verb == "Remove" else "\nDependencies are installed too.")):
            return say("warn", "Cancelled. Nothing was changed.")
        log.clear(); set_busy(True); say("ok", f"{verb[:-1] if verb.endswith('e') else verb}ing {name}…")
        def done(res):
            set_busy(False)
            if isinstance(res, Exception):
                return say("error", res.message if isinstance(res, StoreError) else str(res))
            say("ok" if res.ok else "error", res.message)
            show_info()
        fn = (lambda on: pm.install([name], on)) if verb == "Install" else (lambda on: pm.remove(name, on))
        run_bg(fn, done, on_line=log.appendPlainText)

    b_search.clicked.connect(search); box.returnPressed.connect(search); b_rec.clicked.connect(recommended)
    b_install.clicked.connect(lambda: operate("Install")); b_remove.clicked.connect(lambda: operate("Remove"))
    lst.currentItemChanged.connect(lambda *_: show_info())
    if geteuid() == 0:
        say("error", "The Store refuses to run as root. Start it as your normal user.")
        set_busy(False)
    else:
        say("ok", "Search for a package or open Recommended. If installs fail with 'not found', run a full system update first.")
    update_buttons()
    win._w = dict(box=box, search=b_search, rec=b_rec, list=lst, info=info, install=b_install, remove=b_remove, log=log, status=status)
    return win


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("chudos-store: PySide6 is not installed (package: pyside6).", file=sys.stderr)
        return 2
    app = QApplication(sys.argv[:1]); w = build_window(); w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
