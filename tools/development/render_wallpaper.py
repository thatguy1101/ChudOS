#!/usr/bin/env python3
"""Render the ChudOS default wallpaper (original artwork: a plain gradient).

Output: branding/wallpapers/ChudOSDefault/ as a Plasma wallpaper package
(metadata.json + contents/images/<W>x<H>.png). Requires PySide6.
Run:  QT_QPA_PLATFORM=offscreen python3 tools/development/render_wallpaper.py
"""
import json
import sys
from pathlib import Path

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QRadialGradient

SIZES = [(1920, 1080), (2560, 1440)]
ROOT = Path(__file__).resolve().parents[2] / "branding" / "wallpapers" / "ChudOSDefault"


def render(w: int, h: int) -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    base = QLinearGradient(0, 0, w, h)
    base.setColorAt(0.0, QColor("#0e1016"))
    base.setColorAt(1.0, QColor("#1b1d2b"))
    p.fillRect(0, 0, w, h, base)
    glow = QRadialGradient(QPointF(w * 0.78, h * 0.2), w * 0.5)
    glow.setColorAt(0.0, QColor(108, 140, 255, 70))
    glow.setColorAt(1.0, QColor(108, 140, 255, 0))
    p.fillRect(0, 0, w, h, glow)
    p.end()
    return img


def main() -> int:
    app = QGuiApplication(sys.argv[:1])  # noqa: F841 (needed for QImage painting)
    out = ROOT / "contents" / "images"
    out.mkdir(parents=True, exist_ok=True)
    for w, h in SIZES:
        if not render(w, h).save(str(out / f"{w}x{h}.png")):
            print(f"failed to write {w}x{h}", file=sys.stderr)
            return 1
    (ROOT / "metadata.json").write_text(json.dumps({
        "KPlugin": {
            "Id": "ChudOSDefault",
            "Name": "ChudOS Default",
            "Authors": [{"Name": "ChudOS Project"}],
            "License": "GPL-3.0-or-later",
        }
    }, indent=2) + "\n", encoding="utf-8")
    print(f"wrote wallpaper package to {ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
