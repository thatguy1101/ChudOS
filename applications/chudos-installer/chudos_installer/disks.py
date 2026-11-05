"""Disk discovery and safety rules. A disk is offered ONLY if it is a whole disk, writable, big enough and has nothing
mounted anywhere on it (this also excludes the live USB). Nothing is ever preselected."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Callable

from .settings import DISK_RE, MIN_DISK_BYTES

LSBLK = ["lsblk", "--json", "--bytes", "--output", "NAME,PATH,SIZE,TYPE,RO,RM,MODEL,MOUNTPOINTS,FSTYPE,LABEL"]


@dataclass
class Disk:
    path: str
    size_bytes: int
    model: str = ""
    removable: bool = False
    contents: list[str] = field(default_factory=list)   # what is on it now, so the user recognises it
    usable: bool = True
    reason: str = ""                                    # why it is not usable


def _truthy(v) -> bool:
    return v in (True, 1, "1", "true")


def _mounts(node: dict) -> list[str]:
    found = []
    mp = node.get("mountpoints", node.get("mountpoint"))
    for m in (mp if isinstance(mp, list) else [mp]):
        if m:
            found.append(str(m))
    for child in node.get("children", []) or []:
        found += _mounts(child)
    return found


def _contents(node: dict) -> list[str]:
    out = []
    for child in node.get("children", []) or []:
        bits = [child.get("name", "?")]
        if child.get("fstype"):
            bits.append(child["fstype"])
        if child.get("label"):
            bits.append(f"“{child['label']}”")
        out.append(" ".join(bits))
    return out


def parse_lsblk(text: str) -> list[Disk]:
    try:
        data = json.loads(text)
        nodes = data["blockdevices"]
    except (ValueError, KeyError, TypeError):
        return []
    disks = []
    for n in nodes:
        if not isinstance(n, dict) or n.get("type") != "disk":
            continue
        path = str(n.get("path") or "")
        if not DISK_RE.match(path):
            continue                                   # zram, loop, ram, sr, md... are never offered
        try:
            size = int(n.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        d = Disk(path, size, str(n.get("model") or "").strip(), _truthy(n.get("rm")), _contents(n))
        mounts = _mounts(n)
        if _truthy(n.get("ro")):
            d.usable, d.reason = False, "read-only"
        elif mounts:
            d.usable, d.reason = False, "in use (mounted: " + ", ".join(sorted(set(mounts))[:3]) + "); this may be the live USB"
        elif size < MIN_DISK_BYTES:
            d.usable, d.reason = False, f"too small (need at least {MIN_DISK_BYTES // 1024**3} GiB)"
        disks.append(d)
    return sorted(disks, key=lambda d: d.path)


def list_disks(run: Callable = None) -> list[Disk]:
    run = run or (lambda argv: subprocess.run(argv, capture_output=True, text=True, timeout=20, check=False))
    try:
        p = run(LSBLK)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_lsblk(p.stdout) if p.returncode == 0 else []


def part_path(disk: str, n: int) -> str:
    """/dev/sda -> /dev/sda1 ; /dev/nvme0n1 and /dev/mmcblk0 -> ...p1"""
    return f"{disk}p{n}" if disk[-1].isdigit() else f"{disk}{n}"


def human_size(n: int) -> str:
    g = n / 1000**3
    return f"{g / 1000:.1f} TB" if g >= 1000 else f"{g:.0f} GB"
