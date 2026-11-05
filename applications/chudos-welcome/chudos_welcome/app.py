"""ChudOS Welcome: minimal first-run window (PySide6).

Scope for this milestone: orientation + shortcuts into existing tools +
"don't show again". Profile selection arrives with the Dopamine Profiles
milestone; nothing here pretends otherwise.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, actions, state


def _build_window(path: Path):
    from PySide6.QtWidgets import (QCheckBox, QLabel, QPushButton, QVBoxLayout, QWidget)

    win = QWidget()
    win.setWindowTitle("Welcome to ChudOS")
    win.setMinimumWidth(460)
    layout = QVBoxLayout(win)
    layout.setSpacing(12)

    title = QLabel("Welcome to ChudOS")
    title.setStyleSheet("font-size: 22px; font-weight: 600;")
    title.setAccessibleName("Welcome heading")
    layout.addWidget(title)

    body = QLabel(
        f"ChudOS {__version__} is an early prototype built on Arch Linux and KDE Plasma.\n"
        "Pick a Dopamine Profile or open the Control Centre below. The Store and Monitor are installed as separate apps."
    )
    body.setWordWrap(True)
    layout.addWidget(body)

    status = QLabel("")
    status.setWordWrap(True)
    status.setAccessibleName("Status")

    def make_handler(key: str):
        def handler():
            ok, msg = actions.run(key)
            status.setText(msg)
            status.setStyleSheet("" if ok else "color: #d9534f;")
        return handler

    live = Path("/run/archiso").is_dir()
    for act in actions.ACTIONS:
        if act.live_only and not live:
            continue
        btn = QPushButton(act.label)
        btn.setEnabled(actions.available(act))
        if not btn.isEnabled():
            btn.setToolTip(f"{act.argv[0]} is not installed")
        btn.clicked.connect(make_handler(act.key))
        layout.addWidget(btn)

    layout.addWidget(status)

    check = QCheckBox("Don't show this again")
    check.setChecked(state.load(path)["dismissed"])
    layout.addWidget(check)

    close = QPushButton("Close")

    def on_close():
        try:
            state.save(path, check.isChecked())
        except OSError as exc:
            status.setText(f"Could not save your preference: {exc}")
            return
        win.close()

    close.clicked.connect(on_close)
    layout.addWidget(close)
    return win


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chudos-welcome")
    parser.add_argument("--force", action="store_true", help="show even if dismissed")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    path = state.state_path()
    live = Path("/run/archiso").is_dir()
    if not state.should_show(path, force=args.force, live_session=live):
        return 0

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("chudos-welcome: PySide6 is not installed (package: pyside6).", file=sys.stderr)
        return 2

    app = QApplication(sys.argv[:1])
    app.setApplicationName("chudos-welcome")
    win = _build_window(path)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
