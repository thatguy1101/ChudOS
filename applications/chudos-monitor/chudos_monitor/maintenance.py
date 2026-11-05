"""Read-only maintenance and update diagnostics. Nothing in this module changes or deletes anything.

Changes (upgrade, cache cleanup) are delegated to an interactive terminal command that the user confirms and
watches: see terminal_command(). Every reader returns a Metric (available value or an explicit reason).
"""
from __future__ import annotations

import heapq
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from .sysinfo import Metric, storage

CACHE_DIR = Path("/var/cache/pacman/pkg")
LOCK_FILE = Path("/var/lib/pacman/db.lck")
MIN_FREE_BYTES = 2 * 1024**3
Run = Callable[[list[str]], subprocess.CompletedProcess]


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)


def _need(tool: str, which) -> Metric | None:
    return None if which(tool) else Metric.na(f"{tool} is not installed")


# ---------------- update pre-flight ----------------
def preflight(lock_file: Path = LOCK_FILE, usage=shutil.disk_usage) -> dict[str, list[str]]:
    """Checks before a full upgrade. Returns {'blockers': [...], 'warnings': [...]}. Never raises."""
    blockers, warnings = [], []
    if lock_file.exists():
        blockers.append("The package database is locked (another pacman may be running).")
    root = storage("/", usage)
    if not root.available:
        warnings.append(f"Could not check free space ({root.reason}).")
    elif root.value["free"] < MIN_FREE_BYTES:
        blockers.append(f"Less than {MIN_FREE_BYTES // 1024**3} GiB free on / (free space matters during an upgrade).")
    warnings.append("Read the Arch Linux news (archlinux.org/news) if you have not updated for a while.")
    return {"blockers": blockers, "warnings": warnings}


def _norm_kernel(v: str) -> str:
    # pacman: 6.12.1.arch1-1  ->  uname: 6.12.1-arch1-1
    return re.sub(r"\.(arch\d+)", r"-\1", v.strip().split()[-1] if " " in v.strip() else v.strip())


def restart_needed(running: str | None = None, run: Run = _run, which=shutil.which, package: str = "linux") -> Metric:
    """Heuristic (an estimate): the running kernel differs from the installed kernel package version.
    Value True/False. Only covers the stock 'linux' kernel; says so when it cannot tell."""
    if (na := _need("pacman", which)):
        return na
    running = running if running is not None else os.uname().release
    try:
        p = run(["pacman", "-Q", package])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Metric.na(f"pacman failed: {exc}")
    if p.returncode != 0:
        return Metric.na(f"package {package!r} not installed (different kernel package?)")
    installed = _norm_kernel(p.stdout.split()[-1]) if p.stdout.split() else ""
    if not installed:
        return Metric.na("could not parse installed kernel version")
    if "-arch" not in running:
        return Metric.na("running kernel is not the Arch 'linux' kernel; cannot compare")
    return Metric(installed != running, estimate=True)


def terminal_command(kind: str) -> list[str]:
    """Fixed interactive commands the user runs in a terminal. Nothing user-derived is ever interpolated."""
    cmds = {
        "update": ["sudo", "pacman", "-Syu"],            # sync + full upgrade together: never a partial upgrade
        "clean-cache": ["sudo", "paccache", "-r"],       # keeps 3 most recent cached versions per package
    }
    if kind not in cmds:
        raise ValueError(f"unknown command {kind!r}")
    return ["konsole", "-e", *cmds[kind]]


# ---------------- package status ----------------
def orphans(run: Run = _run, which=shutil.which) -> Metric:
    """Packages installed as dependencies that nothing needs. A LIST ONLY: ChudOS never removes them for you."""
    if (na := _need("pacman", which)):
        return na
    try:
        p = run(["pacman", "-Qdtq"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Metric.na(f"pacman failed: {exc}")
    if p.returncode == 1 and not p.stdout.strip():
        return Metric([])                      # pacman exits 1 when the list is empty
    if p.returncode != 0:
        return Metric.na(f"pacman exited {p.returncode}")
    return Metric([l for l in p.stdout.split() if re.fullmatch(r"[a-z0-9@._+-]+", l)])


def cache_size(cache: Path = CACHE_DIR) -> Metric:
    try:
        total = n = 0
        with os.scandir(cache) as it:
            for e in it:
                if e.is_file(follow_symlinks=False):
                    total += e.stat(follow_symlinks=False).st_size; n += 1
        return Metric({"bytes": total, "files": n})
    except OSError as exc:
        return Metric.na(f"cannot read {cache}: {exc.strerror or exc}")


def cleanup_preview(run: Run = _run, which=shutil.which) -> Metric:
    """What `paccache -r` WOULD remove (paccache -d is a dry run). Nothing is deleted."""
    if (na := _need("paccache", which)):
        return Metric.na("paccache not installed (package: pacman-contrib)")
    try:
        p = run(["paccache", "-d"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Metric.na(f"paccache failed: {exc}")
    if p.returncode != 0:
        return Metric.na(f"paccache exited {p.returncode}")
    return Metric([l for l in (p.stdout + p.stderr).splitlines() if l.strip()][-5:])


# ---------------- logs ----------------
def recent_errors(lines: int = 50, run: Run = _run, which=shutil.which) -> Metric:
    if (na := _need("journalctl", which)):
        return na
    lines = max(1, min(int(lines), 500))
    try:
        p = run(["journalctl", "-p", "err", "-b", "--no-pager", "-n", str(lines)])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Metric.na(f"journalctl failed: {exc}")
    text = (p.stdout or "").strip()
    if p.returncode != 0 and not text:
        return Metric.na("could not read the journal (you may need to be in the systemd-journal group)")
    if "No journal files were opened" in text or "not seeing messages" in text.lower() and len(text.splitlines()) <= 2:
        return Metric.na("journal not readable by your user (join the systemd-journal group to see system logs)")
    return Metric(text.splitlines())


# ---------------- large files (bounded, read-only) ----------------
def largest_files(root: Path, count: int = 15, max_entries: int = 200_000, max_seconds: float = 10.0,
                  clock=time.monotonic) -> Metric:
    """Top-N largest regular files under root. Does not follow symlinks, stays on one filesystem, and stops at the
    entry/time budget (reporting that the scan was partial). Never opens, modifies or deletes anything."""
    root = Path(root)
    try:
        dev = root.stat().st_dev
    except OSError as exc:
        return Metric.na(f"cannot read {root}: {exc.strerror or exc}")
    heap: list[tuple[int, str]] = []
    seen, partial, start, stack = 0, False, clock(), [str(root)]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    seen += 1
                    if seen > max_entries or clock() - start > max_seconds:
                        partial = True; stack.clear(); break
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            if e.stat(follow_symlinks=False).st_dev == dev:
                                stack.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            item = (e.stat(follow_symlinks=False).st_size, e.path)
                            if len(heap) < count:
                                heapq.heappush(heap, item)
                            else:
                                heapq.heappushpop(heap, item)
                    except OSError:
                        continue
        except OSError:
            continue
    return Metric({"files": sorted(heap, reverse=True), "partial": partial, "scanned": seen})
