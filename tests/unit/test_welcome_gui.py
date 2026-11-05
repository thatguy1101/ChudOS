import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_window_builds_and_dismiss_persists(tmp_path):
    from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton
    from chudos_welcome import app, state

    qt = QApplication.instance() or QApplication([])
    path = tmp_path / "welcome.json"
    win = app._build_window(path)
    win.show()
    check = win.findChild(QCheckBox)
    check.setChecked(True)
    close = [b for b in win.findChildren(QPushButton) if b.text() == "Close"][0]
    close.click()
    assert state.load(path)["dismissed"] is True
    assert qt is not None
