import os
import subprocess
import time

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chudos_store.pacman import Package, Pacman, Result, StoreError


class FakePM:
    def __init__(self):
        self.calls = []
    def search(self, q):
        self.calls.append(("search", q))
        if q == "boom":
            raise StoreError("network", "Network problem.")
        return [Package("extra", "vlc", "3.0", "player", True), Package("extra", "mpv", "0.3")]
    def is_installed(self, n): return n == "firefox"
    def info(self, n): return {"Name": n, "Version": "1", "Description": "d", "Installed": "no"}
    def install(self, names, on_line):
        self.calls.append(("install", names)); on_line("installing..."); return Result(True, "", "Done.", ["installing..."])
    def remove(self, n, on_line):
        self.calls.append(("remove", n)); return Result(False, "conflict", "The change conflicts with installed packages. Nothing was changed.")


def make(answer=True, euid=1000):
    from PySide6.QtWidgets import QApplication
    from chudos_store.gui import build_window
    QApplication.instance() or QApplication([])
    fake = FakePM()
    return build_window(fake, confirm=lambda t, x: answer, geteuid=lambda: euid), fake


def wait(cond, secs=5):
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication
    QThreadPool.globalInstance().waitForDone(secs * 1000)
    for _ in range(100):
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def test_search_lists_results_and_validates_via_backend():
    win, fake = make(); w = win._w
    w["box"].setText("player"); w["search"].click()
    assert wait(lambda: w["list"].count() == 2) and fake.calls[0] == ("search", "player")
    assert w["list"].item(0).text().startswith("● vlc")


def test_search_error_is_shown_not_swallowed():
    win, _ = make(); w = win._w
    w["box"].setText("boom"); w["search"].click()
    assert wait(lambda: "Network problem" in w["status"].text()) and w["search"].isEnabled()


def test_install_requires_confirmation_and_streams_progress():
    win, fake = make(answer=False); w = win._w
    w["box"].setText("x"); w["search"].click(); assert wait(lambda: w["list"].count() == 2)
    w["list"].setCurrentRow(1); w["install"].click()
    assert "Nothing was changed" in w["status"].text() and not [c for c in fake.calls if c[0] == "install"]
    win2, fake2 = make(answer=True); w2 = win2._w
    w2["box"].setText("x"); w2["search"].click(); assert wait(lambda: w2["list"].count() == 2)
    w2["list"].setCurrentRow(1); w2["install"].click()
    assert wait(lambda: ("install", ["mpv"]) in fake2.calls and "Done." in w2["status"].text())
    assert "installing..." in w2["log"].toPlainText()


def test_failed_remove_shows_error_message():
    win, fake = make(); w = win._w
    w["box"].setText("x"); w["search"].click(); assert wait(lambda: w["list"].count() == 2)
    w["list"].setCurrentRow(0); w["remove"].click()
    assert wait(lambda: "conflicts" in w["status"].text())


def test_protected_package_cannot_be_removed_from_gui():
    win, fake = make(); w = win._w
    fake.search = lambda q: [Package("core", "pacman", "6")]
    w["box"].setText("pac"); w["search"].click(); assert wait(lambda: w["list"].count() == 1)
    w["list"].setCurrentRow(0)
    assert w["install"].isEnabled() and not w["remove"].isEnabled()


def test_gui_refuses_to_operate_as_root():
    win, _ = make(euid=0); w = win._w
    assert "refuses to run as root" in w["status"].text()
    assert not w["install"].isEnabled() and not w["search"].isEnabled()


def test_recommended_shows_installed_marker():
    win, _ = make(); w = win._w
    w["rec"].click()
    assert wait(lambda: w["list"].count() > 5)
    texts = [w["list"].item(i).text() for i in range(w["list"].count())]
    assert any(t.startswith("● firefox") for t in texts) and any(t.startswith("   vlc") for t in texts)
