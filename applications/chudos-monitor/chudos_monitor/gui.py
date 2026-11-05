"""ChudOS Monitor window (PySide6). Samples only while the window is visible AND active; interval is configurable."""
from __future__ import annotations

import sys

from . import sysinfo as si

MIN_INTERVAL, MAX_INTERVAL, DEFAULT_INTERVAL = 1, 60, 2


def fmt(m, render=str):
    return render(m.value) if m.available else f"unavailable ({m.reason})"


def build_window(proc=si.PROC, storage_path="/"):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import (QCheckBox, QFormLayout, QHBoxLayout, QLabel, QProgressBar, QSpinBox, QVBoxLayout, QWidget)

    win = QWidget(); win.setWindowTitle("ChudOS Monitor"); win.resize(520, 360)
    lay = QVBoxLayout(win)
    form = QFormLayout(); lay.addLayout(form)
    L = {k: QLabel() for k in ("cpu", "mem", "disk", "net", "uptime", "gpu", "model")}
    bars = {k: QProgressBar() for k in ("cpu", "mem", "disk")}
    for b in bars.values():
        b.setRange(0, 1000); b.setTextVisible(False); b.setMaximumHeight(10)
    form.addRow("Processor", L["model"])
    form.addRow("CPU", L["cpu"]); form.addRow("", bars["cpu"])
    form.addRow("Memory", L["mem"]); form.addRow("", bars["mem"])
    form.addRow(f"Storage ({storage_path})", L["disk"]); form.addRow("", bars["disk"])
    form.addRow("Network", L["net"]); form.addRow("Uptime", L["uptime"])
    form.addRow("GPU", L["gpu"])
    L["gpu"].setText("unavailable (GPU monitoring is not implemented yet)")
    row = QHBoxLayout(); lay.addLayout(row)
    spin = QSpinBox(); spin.setRange(MIN_INTERVAL, MAX_INTERVAL); spin.setValue(DEFAULT_INTERVAL); spin.setSuffix(" s"); spin.setAccessibleName("Refresh interval")
    pause = QCheckBox("Pause"); pause.setAccessibleName("Pause updates")
    row.addWidget(QLabel("Refresh every")); row.addWidget(spin); row.addWidget(pause); row.addStretch(1)
    note = QLabel("Memory 'used' = total minus the kernel's MemAvailable. Values marked unavailable could not be read; they are not zero.")
    note.setWordWrap(True); lay.addWidget(note); lay.addStretch(1)

    cpu, net = si.CpuSampler(proc), si.NetSampler(proc)
    L["model"].setText(fmt(si.cpu_model(proc)))

    def bar(name, frac):
        bars[name].setValue(0 if frac is None else int(1000 * max(0.0, min(1.0, frac))))

    def refresh():
        c = cpu.sample(); L["cpu"].setText(fmt(c, lambda v: f"{v}%")); bar("cpu", c.value / 100 if c.available else None)
        m = si.memory(proc)
        if m.available:
            v = m.value; L["mem"].setText(f"{si.human_bytes(v['used'])} of {si.human_bytes(v['total'])}"); bar("mem", v["used"] / v["total"])
        else:
            L["mem"].setText(fmt(m)); bar("mem", None)
        d = si.storage(storage_path)
        if d.available:
            v = d.value; L["disk"].setText(f"{si.human_bytes(v['free'])} free of {si.human_bytes(v['total'])}"); bar("disk", v["used"] / v["total"])
        else:
            L["disk"].setText(fmt(d)); bar("disk", None)
        L["net"].setText(fmt(net.sample(), lambda v: f"↓ {si.human_bytes(v['rx_per_s'])}/s  ↑ {si.human_bytes(v['tx_per_s'])}/s"))
        L["uptime"].setText(fmt(si.uptime_seconds(proc), si.human_duration))

    timer = QTimer(win); timer.setInterval(DEFAULT_INTERVAL * 1000)
    timer.timeout.connect(lambda: refresh() if win.isActiveWindow() and not pause.isChecked() else None)
    spin.valueChanged.connect(lambda v: timer.setInterval(v * 1000))
    pause.toggled.connect(lambda on: None if on else refresh())
    orig_show, orig_hide = win.showEvent, win.hideEvent
    win.showEvent = lambda e: (orig_show(e), refresh(), timer.start())[0]
    win.hideEvent = lambda e: (orig_hide(e), timer.stop())[0]
    win._m = dict(labels=L, bars=bars, spin=spin, pause=pause, timer=timer, refresh=refresh)
    return win


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("chudos-monitor: PySide6 is not installed (package: pyside6).", file=sys.stderr)
        return 2
    app = QApplication(sys.argv[:1]); w = build_window(); w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
