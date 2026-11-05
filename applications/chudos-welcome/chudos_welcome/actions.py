"""Launchable actions for the Welcome app. No Qt imports.

Every action is a fixed argv from this table: nothing user- or file-supplied
is ever passed to a shell. An action whose program is missing reports that
instead of failing silently.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    key: str
    label: str
    argv: tuple[str, ...]
    live_only: bool = False  # shown only on the live medium


ACTIONS: tuple[Action, ...] = (
    Action("install", "Install ChudOS", ("chudos-installer",), live_only=True),
    Action("controlcenter", "Open ChudOS Control Centre", ("chudos-control-center",)),
    Action("profiles", "Choose a Dopamine Profile", ("chudos-profiles-gui",)),
    Action("store", "Open the ChudOS Store", ("chudos-store-gui",)),
    Action("monitor", "Open the ChudOS Monitor", ("chudos-monitor",)),
    Action("settings", "Open KDE System Settings", ("systemsettings",)),
    Action("terminal", "Open a terminal", ("konsole",)),
    Action("files", "Open file manager", ("dolphin",)),
    Action("updates", "Open a terminal to update (sudo pacman -Syu)", ("konsole",)),
    Action("docs", "Read the Arch Wiki", ("xdg-open", "https://wiki.archlinux.org/")),
)

_BY_KEY = {a.key: a for a in ACTIONS}


def get(key: str) -> Action | None:
    return _BY_KEY.get(key)


def available(action: Action) -> bool:
    return shutil.which(action.argv[0]) is not None


def run(key: str, popen=subprocess.Popen) -> tuple[bool, str]:
    """Start an action detached. Returns (ok, message)."""
    action = get(key)
    if action is None:
        return False, f"Unknown action: {key!r}"
    if not available(action):
        return False, f"{action.argv[0]} is not installed on this system."
    try:
        popen(list(action.argv), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as exc:
        return False, f"Could not start {action.argv[0]}: {exc}"
    return True, f"Started {action.argv[0]}."
