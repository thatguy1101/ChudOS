"""Apply a profile to the desktop.

Safety properties:
 * only settings listed in the profile are touched (no overwriting of unrelated settings)
 * unchanged settings are skipped
 * a file lock prevents overlapping applications
 * on failure, settings already changed are restored to their previous values (when known)
 * active profile is recorded only after a fully successful apply
Subprocesses use argv lists (no shell) with a timeout.
"""
from __future__ import annotations

import fcntl
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from . import sound
from .schema import SETTINGS
from .store import ProfileStore

TIMEOUT = 10


class ApplyError(Exception):
    pass


def default_runner(argv: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return p.returncode, p.stdout.strip() or p.stderr.strip()


@dataclass
class ApplyResult:
    profile: str
    applied: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    unavailable: dict[str, str] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    rolled_back: list[str] = field(default_factory=list)
    not_restored: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


@contextmanager
def apply_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ApplyError("another profile change is already in progress") from exc
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _hex_to_rgb(h: str) -> str:
    return ",".join(str(int(h[i:i + 2], 16)) for i in (1, 3, 5))


def _rgb_to_hex(s: str) -> str | None:
    try:
        parts = [int(x) for x in s.split(",")]
        if len(parts) != 3 or not all(0 <= x <= 255 for x in parts):
            return None
        return "#%02x%02x%02x" % tuple(parts)
    except ValueError:
        return None


class Backend:
    """Reads/writes the real settings. Injected runner/which/sound path make it testable."""

    def __init__(self, runner=default_runner, which=shutil.which, sound_cfg: Path | None = None):
        self.run, self.which = runner, which
        self.sound_cfg = sound_cfg or sound.config_path()
        self.kwin_dirty = False

    def available(self, sid: str) -> str | None:
        req = SETTINGS[sid].requires
        if req and not self.which(req):
            return f"{req} is not installed"
        if sid == "effects.animation_speed" or sid == "effects.blur":
            if not self.which("kreadconfig6"):
                return "kreadconfig6 is not installed"
        return None

    def _kread(self, f: str, g: str, k: str) -> str | None:
        rc, out = self.run(["kreadconfig6", "--file", f, "--group", g, "--key", k])
        return out if rc == 0 and out != "" else None

    def _kwrite(self, f: str, g: str, k: str, v: str) -> None:
        rc, out = self.run(["kwriteconfig6", "--file", f, "--group", g, "--key", k, v])
        if rc != 0:
            raise ApplyError(f"kwriteconfig6 failed: {out}")

    def read(self, sid: str):
        """Current value, or None if unknown/unset."""
        if sid == "appearance.accent_color":
            v = self._kread("kdeglobals", "General", "AccentColor")
            return _rgb_to_hex(v) if v else None
        if sid == "effects.animation_speed":
            v = self._kread("kdeglobals", "KDE", "AnimationDurationFactor")
            if v is None:
                return 1.0  # KDE's documented default when unset
            try:
                f = float(v)
            except ValueError:
                return None
            return 0.0 if f == 0 else round(1 / f, 4)
        if sid == "effects.blur":
            v = self._kread("kwinrc", "Plugins", "blurEnabled")
            return None if v is None else v.lower() == "true"
        if sid in ("sound.enabled", "sound.volume"):
            return sound.load(self.sound_cfg)[sid.split(".")[1]]
        raise KeyError(sid)

    def write(self, sid: str, value) -> None:
        if sid == "appearance.accent_color":
            rc, out = self.run(["plasma-apply-colorscheme", "--accent-color", value])
            if rc != 0:
                raise ApplyError(f"plasma-apply-colorscheme failed: {out}")
        elif sid == "effects.animation_speed":
            factor = 0 if value == 0 else round(1 / value, 4)
            self._kwrite("kdeglobals", "KDE", "AnimationDurationFactor", str(factor))
            self.kwin_dirty = True
        elif sid == "effects.blur":
            self._kwrite("kwinrc", "Plugins", "blurEnabled", "true" if value else "false")
            self.kwin_dirty = True
        elif sid in ("sound.enabled", "sound.volume"):
            cfg = sound.load(self.sound_cfg)
            cfg[sid.split(".")[1]] = value
            sound.save(self.sound_cfg, cfg["enabled"], cfg["volume"])
        else:
            raise KeyError(sid)

    def reload_kwin(self) -> str | None:
        """Ask KWin to re-read config (no desktop restart). Returns a warning on failure."""
        if not self.kwin_dirty:
            return None
        for tool in ("qdbus6", "qdbus"):
            if self.which(tool):
                rc, out = self.run([tool, "org.kde.KWin", "/KWin", "reconfigure"])
                self.kwin_dirty = False
                return None if rc == 0 else f"KWin reload failed ({out}); changes apply at next login"
        return "no qdbus tool found; KWin changes apply at next login"


def _same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) < 1e-3
        except (TypeError, ValueError):
            return False
    return a == b


def apply_profile(store: ProfileStore, pid: str, backend: Backend | None = None) -> ApplyResult:
    backend = backend or Backend()
    profile = store.get(pid)
    result = ApplyResult(profile=pid)
    with apply_lock(store.lock_file):
        done: list[tuple[str, object]] = []  # (setting id, previous value or None)
        for sid, target in profile["settings"].items():
            reason = backend.available(sid)
            if reason:
                result.unavailable[sid] = reason
                continue
            try:
                before = backend.read(sid)
                if before is not None and _same(before, target):
                    result.unchanged.append(sid)
                    continue
                backend.write(sid, target)
            except (ApplyError, OSError) as exc:
                result.failed[sid] = str(exc)
                break
            done.append((sid, before))
            result.applied.append(sid)
        if result.failed:
            for sid, before in reversed(done):
                if before is None:
                    result.not_restored.append(sid)  # previous value unknown (was unset)
                    continue
                try:
                    backend.write(sid, before)
                    result.rolled_back.append(sid)
                except (ApplyError, OSError):
                    result.not_restored.append(sid)
            result.applied = [s for s in result.applied if s in result.not_restored]
        warn = backend.reload_kwin()
        if warn:
            result.warnings.append(warn)
        if result.ok:
            store.set_active(pid)
    return result
