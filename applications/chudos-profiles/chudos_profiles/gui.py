"""ChudOS profile manager (PySide6). UI only; all logic lives in store/apply/viewmodel."""
from __future__ import annotations

import sys
from pathlib import Path

from .apply import ApplyError, Backend, apply_profile
from .cli import make_store
from .schema import SETTINGS, ValidationError
from .store import BUILTIN_IDS, StoreError
from .viewmodel import availability, summarize


LABELS = {
    "appearance.accent_color": "Accent colour",
    "effects.animation_speed": "Animation speed",
    "effects.blur": "Window blur",
    "sound.enabled": "ChudOS sounds",
    "sound.volume": "Sound volume",
}


def build_window(store, backend_factory=Backend):
    from PySide6.QtCore import Qt, QThreadPool, QRunnable, QObject, Signal
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (QCheckBox, QColorDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
                                   QInputDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                                   QSpinBox, QVBoxLayout, QWidget)

    class Done(QObject):
        finished = Signal(object, object)   # (result, exception)

    class Job(QRunnable):
        def __init__(self, fn):
            super().__init__(); self.fn = fn; self.signals = Done()
        def run(self):
            try:
                self.signals.finished.emit(self.fn(), None)
            except Exception as exc:  # noqa: BLE001 - reported to the user, not swallowed
                self.signals.finished.emit(None, exc)

    win = QWidget()
    win.setWindowTitle("ChudOS Profiles")
    win.resize(760, 460)
    root = QHBoxLayout(win)
    lst = QListWidget(); lst.setAccessibleName("Profiles"); lst.setMaximumWidth(220)
    root.addWidget(lst)
    right = QVBoxLayout(); root.addLayout(right, 1)
    title = QLabel(); title.setStyleSheet("font-size: 18px; font-weight: 600;")
    desc = QLabel(); desc.setWordWrap(True)
    right.addWidget(title); right.addWidget(desc)
    form = QFormLayout(); right.addLayout(form)
    status = QLabel(""); status.setWordWrap(True); status.setAccessibleName("Status")
    right.addStretch(1); right.addWidget(status)
    btn_row = QHBoxLayout(); right.addLayout(btn_row)

    state = {"id": None, "widgets": {}, "avail": {}, "color": {}}

    def say(level, text):
        status.setText(text)
        status.setStyleSheet({"ok": "color:#2e8b57;", "warn": "color:#b8860b;", "error": "color:#d9534f;"}[level])

    def refresh(select=None):
        profs, warns = store.list()
        active = store.active()
        lst.blockSignals(True); lst.clear()
        for p in profs:
            tag = "" if p["builtin"] else " (custom)"
            tag += " (edited)" if p["modified"] else ""
            it = QListWidgetItem(("● " if p["id"] == active else "   ") + p["name"] + tag)
            it.setData(Qt.UserRole, p["id"]); lst.addItem(it)
            if p["id"] == (select or state["id"]):
                lst.setCurrentItem(it)
        lst.blockSignals(False)
        if lst.currentItem() is None and lst.count():
            lst.setCurrentRow(0)
        show(lst.currentItem().data(Qt.UserRole) if lst.currentItem() else None)
        if warns:
            say("warn", "Skipped unreadable profile(s): " + "; ".join(warns))

    def show(pid):
        while form.rowCount():
            form.removeRow(0)
        state.update(id=pid, widgets={}, color={})
        if pid is None:
            return
        prof = store.get(pid)
        state["avail"] = availability(backend_factory())
        title.setText(prof["name"] + ("   [active]" if store.active() == pid else ""))
        desc.setText(prof["description"])
        for sid, s in SETTINGS.items():
            cur = prof["settings"].get(sid, s.default)
            if s.kind == "bool":
                w = QCheckBox(); w.setChecked(cur)
            elif s.kind == "int":
                w = QSpinBox(); w.setRange(int(s.minimum), int(s.maximum)); w.setValue(cur)
            elif s.kind == "float":
                w = QDoubleSpinBox(); w.setRange(0, s.maximum); w.setSingleStep(0.25); w.setDecimals(2); w.setValue(cur)
            else:
                w = QPushButton(cur); state["color"][sid] = cur
                w.setStyleSheet(f"background:{cur};")
                def pick(_=False, sid=sid, w=w):
                    c = QColorDialog.getColor(QColor(state["color"][sid]), win)
                    if c.isValid():
                        state["color"][sid] = c.name(); w.setText(c.name()); w.setStyleSheet(f"background:{c.name()};")
                w.clicked.connect(pick)
            w.setAccessibleName(sid); w.setToolTip(s.description + "\nVia: " + s.mechanism)
            reason = state["avail"][sid]
            label = QLabel(LABELS[sid]); label.setBuddy(w)
            if reason:
                w.setEnabled(False)
                row = QWidget(); h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0)
                h.addWidget(w); n = QLabel(f"unavailable: {reason}"); n.setStyleSheet("color:#888;"); h.addWidget(n)
                form.addRow(label, row)
            else:
                form.addRow(label, w)
            state["widgets"][sid] = w
        sel_builtin = pid in BUILTIN_IDS
        buttons["delete"].setEnabled(not sel_builtin)
        buttons["reset"].setEnabled(sel_builtin)

    def collect():
        out = {}
        for sid, w in state["widgets"].items():
            k = SETTINGS[sid].kind
            out[sid] = (w.isChecked() if k == "bool" else state["color"][sid] if k == "color" else w.value())
        return out

    def guarded(fn):
        def run(*_):
            try:
                fn()
            except (StoreError, ValidationError, ApplyError, OSError) as exc:
                say("error", str(exc))
        return run

    def save():
        prof = dict(store.get(state["id"])); prof["settings"] = collect()
        store.save(prof); refresh(state["id"]); say("ok", "Saved.")

    def apply_():
        save()
        pid = state["id"]; say("ok", "Applying…"); buttons["apply"].setEnabled(False)
        job = Job(lambda: apply_profile(store, pid, backend_factory()))
        def done(res, exc):
            buttons["apply"].setEnabled(True)
            if exc is not None:
                say("error", str(exc))
            else:
                say(*summarize(res))
            refresh(pid)
        job.signals.finished.connect(done)
        win._job = job  # keep alive
        QThreadPool.globalInstance().start(job)

    def duplicate():
        name, ok = QInputDialog.getText(win, "Duplicate profile", "Name for the copy:")
        if ok and name.strip():
            nid = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")[:40]
            store.duplicate(state["id"], nid, name.strip()); refresh(nid); say("ok", "Copy created.")

    def delete():
        if QMessageBox.question(win, "Delete", f"Delete profile '{state['id']}'? This cannot be undone.") == QMessageBox.Yes:
            store.delete(state["id"]); state["id"] = None; refresh(); say("ok", "Deleted.")

    def reset():
        if QMessageBox.question(win, "Reset", "Discard your edits and restore the original built-in settings?") == QMessageBox.Yes:
            store.reset(state["id"]); refresh(state["id"]); say("ok", "Restored original settings.")

    def export():
        path, _ = QFileDialog.getSaveFileName(win, "Export profile", f"{state['id']}.json", "Profile (*.json)")
        if path:
            store.export_to(state["id"], Path(path)); say("ok", f"Exported to {path}")

    def import_():
        path, _ = QFileDialog.getOpenFileName(win, "Import profile", "", "Profile (*.json)")
        if path:
            p = store.import_from(Path(path)); refresh(p["id"]); say("ok", f"Imported '{p['id']}'. Nothing was applied.")

    buttons = {}
    for key, text, fn in (("apply", "Save and Apply", apply_), ("save", "Save", save), ("duplicate", "Duplicate", duplicate),
                          ("delete", "Delete", delete), ("reset", "Reset to original", reset),
                          ("import", "Import…", import_), ("export", "Export…", export)):
        b = QPushButton(text); b.clicked.connect(guarded(fn)); btn_row.addWidget(b); buttons[key] = b
    lst.currentItemChanged.connect(lambda cur, _prev: show(cur.data(Qt.UserRole) if cur else None))
    win._buttons, win._state, win._refresh, win._status, win._list = buttons, state, refresh, status, lst
    refresh()
    return win


def main(argv=None) -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("chudos-profiles-gui: PySide6 is not installed (package: pyside6).", file=sys.stderr)
        return 2
    app = QApplication(sys.argv[:1])
    win = build_window(make_store())
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
