"""First-run state for ChudOS Welcome. No Qt imports: fully unit-testable.

State is a small JSON file under XDG_STATE_HOME. Corrupt or unreadable state is
treated as "not yet shown" rather than crashing the app.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

STATE_VERSION = 1


def state_path(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    base = env.get("XDG_STATE_HOME") or str(Path(env.get("HOME", "~")).expanduser() / ".local" / "state")
    return Path(base) / "chudos" / "welcome.json"


def load(path: Path) -> dict:
    """Return stored state, or defaults if missing/corrupt/wrong shape."""
    default = {"version": STATE_VERSION, "dismissed": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
        return default
    if not isinstance(data.get("dismissed"), bool):
        return default
    return {"version": STATE_VERSION, "dismissed": data["dismissed"]}


def save(path: Path, dismissed: bool) -> None:
    """Atomically write state (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"version": STATE_VERSION, "dismissed": bool(dismissed)}), encoding="utf-8")
    os.replace(tmp, path)


def should_show(path: Path, force: bool = False, live_session: bool = False) -> bool:
    if force:
        return True
    if live_session:
        return True  # live media has a throwaway home; always greet
    return not load(path)["dismissed"]
