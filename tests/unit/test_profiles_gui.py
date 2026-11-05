import os
import time
from pathlib import Path

import pytest

from chudos_profiles import apply as ap
from chudos_profiles.apply import ApplyResult
from chudos_profiles.store import ProfileStore
from chudos_profiles.viewmodel import availability, summarize
from test_profiles import FakeKDE, backend  # reuse the fake KDE

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_summarize_levels():
    assert summarize(ApplyResult("x"))[0] == "ok"
    assert summarize(ApplyResult("x", applied=["a"]))[0] == "ok"
    assert summarize(ApplyResult("x", unavailable={"a": "no tool"}))[0] == "warn"
    assert summarize(ApplyResult("x", warnings=["w"]))[0] == "warn"
    lvl, txt = summarize(ApplyResult("x", failed={"s": "boom"}, rolled_back=["a"], not_restored=["b"]))
    assert lvl == "error" and "boom" in txt and "undone" in txt and "b" in txt


def test_availability_reports_reasons(tmp_path):
    b = backend(tmp_path, FakeKDE(), missing=("kwriteconfig6",))
    av = availability(b)
    assert av["effects.blur"] and av["sound.volume"] is None


@pytest.fixture
def window(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from chudos_profiles.gui import build_window
    QApplication.instance() or QApplication([])
    store = ProfileStore(ROOT / "profiles", tmp_path / "cfg", tmp_path / "state")
    kde = FakeKDE()
    win = build_window(store, backend_factory=lambda: backend(tmp_path, kde))
    return win, store, kde


def test_gui_lists_profiles_and_protects_builtins(window):
    win, store, _ = window
    assert win._list.count() == 5
    assert win._buttons["delete"].isEnabled() is False and win._buttons["reset"].isEnabled() is True


def test_gui_edit_and_save_persists(window):
    win, store, _ = window
    win._state["widgets"]["sound.volume"].setValue(7)
    win._buttons["save"].click()
    assert store.get(win._state["id"])["settings"]["sound.volume"] == 7
    assert "Saved" in win._status.text()


def test_gui_apply_changes_fake_desktop_and_marks_active(window):
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication
    win, store, kde = window
    win._list.setCurrentRow(2)  # lock-in
    win._buttons["apply"].click()
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(50):
        QApplication.processEvents()
        if store.active():
            break
        time.sleep(0.02)
    assert store.active() == "lock-in"
    assert kde.db[("kwinrc", "Plugins", "blurEnabled")] == "false"


def test_gui_unavailable_settings_are_disabled(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from chudos_profiles.gui import build_window
    QApplication.instance() or QApplication([])
    store = ProfileStore(ROOT / "profiles", tmp_path / "cfg", tmp_path / "state")
    win = build_window(store, backend_factory=lambda: backend(tmp_path, FakeKDE(), missing=("kwriteconfig6", "kreadconfig6")))
    assert win._state["widgets"]["effects.blur"].isEnabled() is False
    assert win._state["widgets"]["sound.volume"].isEnabled() is True
