import os
import subprocess
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chudos_monitor.sysinfo import Metric
from chudos_profiles.store import ProfileStore

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def cc(tmp_path):
    from PySide6.QtWidgets import QApplication
    from chudos_control_center.gui import build_window
    QApplication.instance() or QApplication([])
    launched = []
    gitcalls = []
    def git_run(argv, **k):
        gitcalls.append(argv)
        return subprocess.CompletedProcess(argv, 0 if argv[3:4] != ["--get"] else 1, "", "")
    store = ProfileStore(ROOT / "profiles", tmp_path / "cfg", tmp_path / "state")
    win = build_window(store, launcher=lambda argv: (launched.append(argv) or (True, "Started.")),
                       sound_path=tmp_path / "sound.json", updates_fn=lambda: Metric(["a 1 -> 2"]),
                       git_run=git_run, home=tmp_path)
    return win, launched, gitcalls, tmp_path


def wait(cond, secs=5):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QThreadPool
    QThreadPool.globalInstance().waitForDone(secs * 1000)
    for _ in range(100):
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def test_has_seven_sections_and_overview_shows_real_values(cc):
    win, *_ = cc
    assert win._nav.count() == 7 and win._pages.count() == 7
    assert win._ov["kernel"].text() and "unavailable" not in win._ov["kernel"].text()
    assert win._ov["profile"].text() == "none applied yet"
    assert "unavailable (needs a second sample)" in win._ov["cpu"].text()   # first CPU sample is never shown as 0%


def test_ctrl_number_shortcuts_are_wired_to_sections(cc):
    """Wiring only: offscreen Qt does not dispatch real keystrokes to window shortcuts, so we fire the QShortcuts."""
    from PySide6.QtGui import QShortcut
    win, *_ = cc
    keys = {sc.key().toString(): sc for sc in win.findChildren(QShortcut)}
    assert sorted(keys) == [f"Ctrl+{i}" for i in range(1, 8)]
    keys["Ctrl+4"].activated.emit()
    assert win._nav.currentRow() == 3
    keys["Ctrl+1"].activated.emit()
    assert win._nav.currentRow() == 0


def test_overview_timer_only_runs_on_overview(cc):
    win, *_ = cc
    assert win._timer.isActive()
    win._nav.setCurrentRow(3)
    assert not win._timer.isActive()
    win._nav.setCurrentRow(0)
    assert win._timer.isActive()


def test_sound_save_persists_and_validates(cc):
    from chudos_profiles import sound
    win, _, _, tmp = cc
    enabled, vol, status, save = win._so
    enabled.setChecked(False); vol.setValue(15); save.click()
    assert sound.load(tmp / "sound.json") == {"enabled": False, "volume": 15}
    assert status.text() == "Saved."


def test_updates_check_runs_in_background_and_updates_overview(cc):
    win, *_ = cc
    win._check_updates.click()
    assert wait(lambda: "1 update(s) available" in win._sy_updates.text())
    assert "1 update(s)" in win._ov["updates"].text() and win._check_updates.isEnabled()


def test_updates_unavailable_is_reported_not_hidden(tmp_path):
    from PySide6.QtWidgets import QApplication
    from chudos_control_center.gui import build_window
    QApplication.instance() or QApplication([])
    store = ProfileStore(ROOT / "profiles", tmp_path / "cfg", tmp_path / "state")
    win = build_window(store, launcher=lambda a: (True, ""), sound_path=tmp_path / "s.json",
                       updates_fn=lambda: Metric.na("checkupdates not installed"), home=tmp_path)
    win._check_updates.click()
    assert wait(lambda: "Could not check" in win._sy_updates.text())
    assert "unavailable" in win._ov["updates"].text()


def test_git_identity_validation_blocks_bad_input_and_saves_good(cc):
    win, _, gitcalls, _ = cc
    name, email, save, status = win._dv
    gitcalls.clear()
    name.setText("Max"); email.setText("not-an-email"); save.click()
    assert "valid email" in status.text() and gitcalls == []
    email.setText("max@example.com"); save.click()
    assert "saved" in status.text().lower() and len(gitcalls) == 2


def test_profiles_page_is_the_existing_manager(cc):
    win, *_ = cc
    page = win._pages.widget(2)
    assert page.windowTitle() == "ChudOS Profiles"
    from PySide6.QtWidgets import QScrollArea
    assert isinstance(win._pages.widget(4), QScrollArea)   # long pages scroll instead of clipping


def _sys_window(tmp_path, answer, fake_maint, launched):
    from PySide6.QtWidgets import QApplication
    from chudos_control_center.gui import build_window
    QApplication.instance() or QApplication([])
    store = ProfileStore(ROOT / "profiles", tmp_path / "cfg", tmp_path / "state")
    return build_window(store, launcher=lambda argv: (launched.append(argv) or (True, "Started.")), sound_path=tmp_path / "s.json",
                        home=tmp_path, confirm=lambda t, x: answer, maint_mod=fake_maint)


class FakeMaint:
    from chudos_monitor import maintenance as real
    terminal_command = staticmethod(real.terminal_command)
    def __init__(self, blockers=()):
        self.blockers = list(blockers)
    def preflight(self):
        return {"blockers": self.blockers, "warnings": ["Read the news."]}
    def restart_needed(self):
        return Metric(True, estimate=True)
    def orphans(self):
        return Metric(["old-dep", "other"])
    def cache_size(self):
        return Metric.na("cannot read /var/cache/pacman/pkg: Permission denied")
    def cleanup_preview(self):
        return Metric(["3 candidates"])
    def recent_errors(self):
        return Metric([])
    def largest_files(self, root):
        return Metric({"files": [(2048, "/h/big.iso")], "partial": True, "scanned": 9})


def test_update_needs_confirmation_and_launches_fixed_terminal_command(tmp_path):
    launched = []
    win = _sys_window(tmp_path, False, FakeMaint(), launched)
    win._sy["start_update"]()
    assert launched == [] and "Nothing was changed" in win._sy["status"].text()
    win = _sys_window(tmp_path, True, FakeMaint(), launched)
    win._sy["start_update"]()
    assert launched == [["konsole", "-e", "sudo", "pacman", "-Syu"]]


def test_update_blocked_by_preflight_does_not_launch(tmp_path):
    launched = []
    win = _sys_window(tmp_path, True, FakeMaint(blockers=["The package database is locked."]), launched)
    win._sy["start_update"]()
    assert launched == [] and "locked" in win._sy["status"].text()


def test_cache_clean_is_confirmed_and_explains_what_it_removes(tmp_path):
    seen = []
    from PySide6.QtWidgets import QApplication
    from chudos_control_center.gui import build_window
    QApplication.instance() or QApplication([])
    launched = []
    store = ProfileStore(ROOT / "profiles", tmp_path / "cfg", tmp_path / "state")
    win = build_window(store, launcher=lambda a: (launched.append(a) or (True, "ok")), sound_path=tmp_path / "s.json", home=tmp_path,
                       confirm=lambda t, x: (seen.append(x) or True), maint_mod=FakeMaint())
    win._sy["clean_cache"]()
    assert launched == [["konsole", "-e", "sudo", "paccache", "-r"]] and "3 most recent" in seen[0] and "OLD" in seen[0]


def test_restart_check_and_details_show_unavailable_honestly(tmp_path):
    from PySide6.QtWidgets import QPushButton
    win = _sys_window(tmp_path, True, FakeMaint(), [])
    win._sy["restart"]()
    assert "Restart needed" in win._sy["status"].text()
    btn = {b.text(): b for b in win.findChildren(QPushButton)}
    btn["Show package cache size"].click()
    assert wait(lambda: "unavailable" in win._sy["details"].toPlainText() and "Permission denied" in win._sy["details"].toPlainText())
    btn["Show orphaned packages (list only)"].click()
    assert wait(lambda: "old-dep" in win._sy["details"].toPlainText())
    btn["Find large files in your home folder"].click()
    assert wait(lambda: "big.iso" in win._sy["details"].toPlainText() and "partial" in win._sy["details"].toPlainText())
    btn["Show recent system errors"].click()
    assert wait(lambda: "No errors logged" in win._sy["details"].toPlainText())
