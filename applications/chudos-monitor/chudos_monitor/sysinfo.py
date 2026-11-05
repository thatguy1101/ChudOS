"""Real system information from Linux interfaces (/proc, statvfs, pacman tools).

Every reader returns a Metric. A metric is either available (value set) or unavailable (reason set):
"unavailable" is never reported as 0. Paths and runners are injectable so this is testable anywhere.
No polling happens here; callers decide when to sample.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

PROC = Path("/proc")


@dataclass(frozen=True)
class Metric:
    value: Any = None
    reason: str = ""            # set when unavailable
    estimate: bool = False      # True when the value is derived, not measured

    @property
    def available(self) -> bool:
        return self.value is not None

    @staticmethod
    def na(reason: str) -> "Metric":
        return Metric(None, reason)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


# ---------------- CPU ----------------
def read_cpu_times(proc: Path = PROC) -> tuple[int, int] | None:
    """(idle_including_iowait, total) jiffies from the aggregate 'cpu' line, or None."""
    text = _read(proc / "stat")
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("cpu "):
            try:
                f = [int(x) for x in line.split()[1:]]
            except ValueError:
                return None
            if len(f) < 5:
                return None
            idle = f[3] + f[4]
            # guest time is already counted inside user/nice: exclude it from the total
            total = sum(f[:8]) if len(f) >= 8 else sum(f)
            return idle, total
    return None


class CpuSampler:
    """CPU usage needs two samples. The first call is 'unavailable', not 0%."""

    def __init__(self, proc: Path = PROC):
        self.proc, self._prev = proc, None

    def sample(self) -> Metric:
        cur = read_cpu_times(self.proc)
        if cur is None:
            return Metric.na("could not read /proc/stat")
        prev, self._prev = self._prev, cur
        if prev is None:
            return Metric.na("needs a second sample")
        d_total, d_idle = cur[1] - prev[1], cur[0] - prev[0]
        if d_total <= 0:
            return Metric.na("no CPU time elapsed between samples")
        return Metric(round(max(0.0, min(100.0, 100.0 * (d_total - d_idle) / d_total)), 1))


def cpu_model(proc: Path = PROC) -> Metric:
    text = _read(proc / "cpuinfo")
    if text:
        for line in text.splitlines():
            if line.lower().startswith(("model name", "hardware", "cpu model")) and ":" in line:
                return Metric(line.split(":", 1)[1].strip())
    return Metric.na("model not exposed by this kernel/architecture")


def cpu_count() -> Metric:
    n = os.cpu_count()
    return Metric(n) if n else Metric.na("unknown")


# ---------------- network ----------------
class NetSampler:
    """Total receive/transmit rate (bytes/s) over all non-loopback interfaces. Needs two samples."""

    def __init__(self, proc: Path = PROC, clock=None):
        import time
        self.proc, self.clock, self._prev = proc, clock or time.monotonic, None

    def _read(self):
        text = _read(self.proc / "net" / "dev")
        if not text:
            return None
        rx = tx = n = 0
        for line in text.splitlines()[2:]:
            if ":" not in line:
                continue
            name, data = line.split(":", 1)
            f = data.split()
            if name.strip() == "lo" or len(f) < 9 or not (f[0].isdigit() and f[8].isdigit()):
                continue
            rx += int(f[0]); tx += int(f[8]); n += 1
        return (rx, tx, n) if n else None

    def sample(self) -> Metric:
        cur, now = self._read(), self.clock()
        if cur is None:
            return Metric.na("no network interfaces found in /proc/net/dev")
        prev, self._prev = self._prev, (cur, now)
        if prev is None:
            return Metric.na("needs a second sample")
        (prx, ptx, _), pt = prev
        dt = now - pt
        if dt <= 0:
            return Metric.na("no time elapsed between samples")
        if cur[0] < prx or cur[1] < ptx:
            return Metric.na("interface counters reset between samples")
        return Metric({"rx_per_s": (cur[0] - prx) / dt, "tx_per_s": (cur[1] - ptx) / dt})


# ---------------- memory ----------------
def memory(proc: Path = PROC) -> Metric:
    """Value: dict(total, available, used) in bytes. 'available' is the kernel's own MemAvailable."""
    text = _read(proc / "meminfo")
    if not text:
        return Metric.na("could not read /proc/meminfo")
    kb = {}
    for line in text.splitlines():
        parts = line.replace(":", "").split()
        if len(parts) >= 2 and parts[1].isdigit():
            kb[parts[0]] = int(parts[1]) * 1024
    if "MemTotal" not in kb or kb["MemTotal"] <= 0:
        return Metric.na("MemTotal missing")
    if "MemAvailable" not in kb:
        return Metric.na("MemAvailable not provided by this kernel; not guessing")
    total, avail = kb["MemTotal"], min(kb["MemAvailable"], kb["MemTotal"])
    return Metric({"total": total, "available": avail, "used": total - avail})


# ---------------- storage ----------------
def storage(path: str = "/", usage: Callable = shutil.disk_usage) -> Metric:
    try:
        u = usage(path)
    except OSError as exc:
        return Metric.na(f"cannot stat {path}: {exc.strerror or exc}")
    if u.total <= 0:
        return Metric.na(f"{path} reports zero size (virtual filesystem?)")
    return Metric({"path": path, "total": u.total, "used": u.used, "free": u.free})


# ---------------- general ----------------
def os_name(root: Path = Path("/")) -> Metric:
    for rel in ("etc/os-release", "usr/lib/os-release"):
        text = _read(root / rel)
        if text:
            for line in text.splitlines():
                if line.startswith("PRETTY_NAME="):
                    return Metric(line.split("=", 1)[1].strip().strip('"'))
    return Metric.na("os-release not found")


def chudos_version(root: Path = Path("/")) -> Metric:
    text = _read(root / "etc" / "chudos-release")
    if text:
        for line in text.splitlines():
            if line.startswith("VERSION="):
                return Metric(line.split("=", 1)[1].strip().strip('"'))
    return Metric.na("ChudOS release file not installed (not running a ChudOS install?)")


def kernel() -> Metric:
    try:
        return Metric(os.uname().release)
    except AttributeError:
        return Metric.na("unknown")


def uptime_seconds(proc: Path = PROC) -> Metric:
    text = _read(proc / "uptime")
    try:
        return Metric(float(text.split()[0])) if text else Metric.na("could not read /proc/uptime")
    except (ValueError, IndexError):
        return Metric.na("could not parse /proc/uptime")


# ---------------- updates ----------------
def pending_updates(runner: Callable | None = None, which: Callable = shutil.which, timeout: int = 60) -> Metric:
    """Uses `checkupdates` (pacman-contrib): it syncs a private DB copy and never touches the system DB.
    exit 0 = updates listed, exit 2 = none, anything else = failed. Run on demand only (uses the network)."""
    if not which("checkupdates"):
        return Metric.na("checkupdates not installed (package: pacman-contrib)")
    run = runner or (lambda argv: subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False))
    try:
        p = run(["checkupdates"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Metric.na(f"checkupdates failed: {exc}")
    if p.returncode == 2:
        return Metric([])
    if p.returncode == 0:
        return Metric([ln for ln in p.stdout.splitlines() if ln.strip()])
    return Metric.na(f"checkupdates exited {p.returncode} (offline or database locked?)")


def human_bytes(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or unit == "TiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def human_duration(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400); h, s = divmod(s, 3600); m, _ = divmod(s, 60)
    return " ".join(x for x in (f"{d}d" if d else "", f"{h}h" if h or d else "", f"{m}m") if x)
