"""ChudOS decorative sound config + player.

Scope: sounds ChudOS itself plays (e.g. when a profile is applied). This does NOT attach sounds to
arbitrary KDE events and never alters application audio or system notification sounds.
Playback uses PipeWire's pw-play (fallback: paplay) as a detached, short-lived process.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .schema import SETTINGS, ValidationError, validate_value

SOUND_DIRS = (Path("/usr/share/chudos/sounds"),)
EVENTS = ("profile-applied",)


def config_path(env=None) -> Path:
    env = os.environ if env is None else env
    base = env.get("XDG_CONFIG_HOME") or str(Path(env.get("HOME", "~")).expanduser() / ".config")
    return Path(base) / "chudos" / "sound.json"


def load(path: Path) -> dict:
    cfg = {"enabled": SETTINGS["sound.enabled"].default, "volume": SETTINGS["sound.volume"].default}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cfg["enabled"] = validate_value(SETTINGS["sound.enabled"], data["enabled"])
        cfg["volume"] = validate_value(SETTINGS["sound.volume"], data["volume"])
    except (OSError, ValueError, KeyError, TypeError, ValidationError):
        pass  # missing or corrupt -> defaults
    return cfg


def save(path: Path, enabled: bool, volume: int) -> None:
    cfg = {"enabled": validate_value(SETTINGS["sound.enabled"], enabled),
           "volume": validate_value(SETTINGS["sound.volume"], volume)}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg), encoding="utf-8")
    os.replace(tmp, path)


def find_asset(event: str, dirs=SOUND_DIRS) -> Path | None:
    if event not in EVENTS:
        return None
    for d in dirs:
        p = Path(d) / f"{event}.wav"
        if p.is_file():
            return p
    return None


def play(event: str, cfg: dict, dirs=SOUND_DIRS, which=shutil.which, popen=subprocess.Popen) -> str:
    """Play an event sound if allowed. Returns a short status string (never raises)."""
    if not cfg.get("enabled") or cfg.get("volume", 0) <= 0:
        return "disabled"
    asset = find_asset(event, dirs)
    if asset is None:
        return "no-asset"
    vol = max(0, min(100, int(cfg["volume"]))) / 100
    if which("pw-play"):
        argv = ["pw-play", "--volume", f"{vol:.2f}", str(asset)]
    elif which("paplay"):
        argv = ["paplay", "--volume", str(int(vol * 65536)), str(asset)]
    else:
        return "no-player"
    try:
        popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              start_new_session=True)
    except OSError:
        return "failed"
    return "played"
