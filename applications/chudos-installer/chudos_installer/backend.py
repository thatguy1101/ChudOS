"""chudos-install-backend: the ONLY root part of the installer. Start it with sudo from the (non-root) window.

Input (one JSON object on stdin):  {"settings": {...incl. password...}, "confirm_erase": "/dev/sdX"}
Output: one JSON event per line on stdout (see engine.py).  It never accepts commands: it builds the plan itself from validated data.
--dry-run validates and prints the plan (no root needed, nothing is executed).
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sys
from pathlib import Path

from . import engine as engine_mod
from .plan import build_plan, describe, read_package_list
from .settings import SettingsError, validate

DEFAULT_PACKAGES = Path("/usr/share/chudos/installer/install-packages.txt")
LOCK = Path("/run/chudos-install.lock")


def main(argv=None, stdin=sys.stdin, out=sys.stdout, preflight=engine_mod.preflight, engine_cls=engine_mod.Engine,
         zoneinfo=Path("/usr/share/zoneinfo"), lock_path: Path = LOCK) -> int:
    ap = argparse.ArgumentParser(prog="chudos-install-backend")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--packages", type=Path, default=DEFAULT_PACKAGES)
    a = ap.parse_args(argv)

    def emit(ev: dict) -> None:
        print(json.dumps(ev), file=out, flush=True)

    try:
        req = json.loads(stdin.read(65536))
        s = validate(req["settings"], zoneinfo)
        if req.get("confirm_erase") != s.disk:
            raise SettingsError("confirm_erase", "The erase confirmation does not match the selected disk.")
        packages = read_package_list(a.packages)
    except SettingsError as exc:
        emit({"type": "error", "step": "validation", "message": f"{exc.field}: {exc.message}", "disk_modified": False}); return 2
    except (ValueError, KeyError, TypeError, OSError) as exc:
        emit({"type": "error", "step": "validation", "message": f"Invalid request: {exc}", "disk_modified": False}); return 2

    steps = build_plan(s, packages)
    if a.dry_run:
        for line in describe(steps):
            print(line, file=out)
        for e in preflight(s):
            print(f"preflight: {e}", file=out)
        return 0

    problems = preflight(s)
    if problems:
        emit({"type": "error", "step": "preflight", "message": " ".join(problems), "disk_modified": False}); return 3
    lock = open(lock_path, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        emit({"type": "error", "step": "preflight", "message": "Another installation is already running.", "disk_modified": False}); return 3
    ok = engine_cls(s, packages, emit, steps=steps).run()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
