import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def fake_proc(tmp_path, busy=100, idle=900):
    (tmp_path / "net").mkdir(exist_ok=True)
    (tmp_path / "stat").write_text(f"cpu  {busy} 0 0 {idle} 0 0 0 0 0 0\n")
    (tmp_path / "meminfo").write_text("MemTotal: 2048 kB\nMemAvailable: 512 kB\n")
    (tmp_path / "cpuinfo").write_text("model name : Fake CPU\n")
    (tmp_path / "uptime").write_text("120.0 1.0\n")
    return tmp_path


def make(tmp_path):
    from PySide6.QtWidgets import QApplication
    from chudos_monitor.gui import build_window
    QApplication.instance() or QApplication([])
    return build_window(fake_proc(tmp_path))


def test_first_refresh_shows_unavailable_cpu_net_not_zero(tmp_path):
    win = make(tmp_path); m = win._m
    m["refresh"]()
    assert "unavailable (needs a second sample)" in m["labels"]["cpu"].text()
    assert "unavailable" in m["labels"]["net"].text() and m["bars"]["cpu"].value() == 0
    assert m["labels"]["mem"].text() == "1.5 MiB of 2.0 MiB" and m["labels"]["model"].text() == "Fake CPU"
    assert m["labels"]["uptime"].text() == "2m"


def test_second_refresh_computes_cpu(tmp_path):
    win = make(tmp_path); m = win._m
    m["refresh"]()
    fake_proc(tmp_path, busy=300, idle=1000)    # +200 busy, +100 idle -> 66.7%
    m["refresh"]()
    assert m["labels"]["cpu"].text() == "66.7%" and abs(m["bars"]["cpu"].value() - 667) <= 1


def test_gpu_is_declared_unavailable_not_faked(tmp_path):
    assert "not implemented" in make(tmp_path)._m["labels"]["gpu"].text()


def test_interval_is_configurable_and_bounded_and_timer_idle_until_shown(tmp_path):
    win = make(tmp_path); m = win._m
    assert not m["timer"].isActive()
    m["spin"].setValue(5)
    assert m["timer"].interval() == 5000
    m["spin"].setValue(10_000)
    assert m["spin"].value() == 60
    win.show(); assert m["timer"].isActive()
    win.hide(); assert not m["timer"].isActive()


def test_missing_proc_files_show_unavailable(tmp_path):
    from PySide6.QtWidgets import QApplication
    from chudos_monitor.gui import build_window
    QApplication.instance() or QApplication([])
    m = build_window(tmp_path / "empty")._m
    m["refresh"]()
    for k in ("cpu", "mem", "net", "uptime", "model"):
        assert "unavailable" in m["labels"][k].text()
