"""Runs an install plan. Separate from the plan (data) and the GUI (user-level process).

Safety: preflight() is the gate. It refuses unless we are root, on the live medium, booted in UEFI, the target is a currently
usable whole disk, the tools and the bundled repository exist and the network is up. Nothing else in this module decides what is safe.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from string import Template
from typing import Callable

from . import disks as disks_mod
from .plan import REPO_DIR, TARGET, Step, build_plan, pacman_conf
from .settings import InstallSettings

REQUIRED_TOOLS = ("wipefs", "sgdisk", "partprobe", "udevadm", "mkfs.fat", "mkfs.ext4", "mount", "umount", "blkid", "pacstrap", "genfstab", "arch-chroot")


class InstallError(Exception):
    pass


def preflight(s: InstallSettings, *, live_marker: Path = Path("/run/archiso"), efi: Path = Path("/sys/firmware/efi"),
              geteuid: Callable = os.geteuid, which: Callable = shutil.which, repo: Path = Path(REPO_DIR), keyring: Path = Path("/etc/pacman.d/gnupg/trustdb.gpg"),
              list_disks: Callable = disks_mod.list_disks, run: Callable = None) -> list[str]:
    run = run or (lambda argv: subprocess.run(argv, capture_output=True, text=True, timeout=15, check=False))
    errors: list[str] = []
    if geteuid() != 0:
        errors.append("The installer backend must run as root (the window starts it with sudo).")
    if not live_marker.is_dir():
        errors.append("Refusing to run: this is not the ChudOS live medium. The installer never runs on an installed system.")
    if not efi.is_dir():
        errors.append("This computer did not boot in UEFI mode. ChudOS can only be installed on UEFI systems (in a VM, enable EFI).")
    match = [d for d in list_disks() if d.path == s.disk]
    if not match:
        errors.append(f"{s.disk} was not found.")
    elif not match[0].usable:
        errors.append(f"{s.disk} cannot be used: {match[0].reason}.")
    missing = [t for t in REQUIRED_TOOLS if not which(t)]
    if missing:
        errors.append("Missing tools on the live system: " + ", ".join(missing))
    if not (repo / "chudos.db").exists():
        errors.append(f"The bundled ChudOS package repository is missing ({repo}).")
    if not keyring.exists():
        errors.append("The package keyring is still being set up. Wait a minute after boot, then try again.")
    if which("nm-online"):
        try:
            if run(["nm-online", "-q", "-t", "5"]).returncode != 0:
                errors.append("No internet connection. Connect with the network icon in the panel, then try again.")
        except (OSError, subprocess.TimeoutExpired):
            errors.append("Could not check the network connection.")
    return errors


class SubprocessExecutor:
    def run(self, argv: list[str], stdin_text: str | None, on_line: Callable[[str], None]) -> int:
        p = subprocess.Popen(argv, stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env={**os.environ, "LC_ALL": "C"})
        if stdin_text is not None:
            assert p.stdin is not None
            try:
                p.stdin.write(stdin_text); p.stdin.close()
            except BrokenPipeError:
                pass
        assert p.stdout is not None
        for line in p.stdout:
            on_line(line.rstrip("\n"))
        return p.wait()

    def capture(self, argv: list[str]) -> tuple[int, str]:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False, env={**os.environ, "LC_ALL": "C"})
        return p.returncode, p.stdout.strip()


class Engine:
    def __init__(self, settings: InstallSettings, packages: list[str], emit: Callable[[dict], None], executor=None,
                 target: str = TARGET, steps: list[Step] | None = None):
        self.s, self.emit, self.x, self.target = settings, emit, executor or SubprocessExecutor(), target
        self.steps = steps if steps is not None else build_plan(settings, packages)
        self.vars: dict[str, str] = {}
        self.tail: list[str] = []
        self.destructive_started = False

    def _log(self, line: str) -> None:
        self.tail = (self.tail + [line])[-40:]
        self.emit({"type": "log", "line": line})

    def _write(self, st: Step) -> None:
        rel = Path(st.path)
        if not rel.is_absolute() or ".." in rel.parts:
            raise InstallError(f"refusing to write outside the target: {st.path}")
        dest = Path(self.target) / str(rel).lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".chudos-tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, st.mode)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(Template(st.content).safe_substitute(self.vars))
        os.chmod(tmp, st.mode)
        os.replace(tmp, dest)

    def _argv(self, st: Step, conf: str) -> list[str]:
        argv = [conf if a == "@PACMAN_CONF@" else a for a in st.argv]
        return ["arch-chroot", self.target, *argv] if st.chroot else argv

    def run(self) -> bool:
        conf_dir = Path(tempfile.mkdtemp(prefix="chudos-install-"))
        conf = conf_dir / "pacman.conf"
        conf.write_text(pacman_conf(), encoding="utf-8")
        total = len(self.steps)
        try:
            for i, st in enumerate(self.steps, 1):
                self.emit({"type": "step", "i": i, "n": total, "title": st.title})
                if st.destructive:
                    self.destructive_started = True
                try:
                    if st.kind == "write":
                        self._write(st)
                    elif st.kind == "capture":
                        rc, out = self.x.capture(self._argv(st, str(conf)))
                        if rc != 0 or not out:
                            raise InstallError(f"{st.argv[0]} failed (exit {rc})")
                        self.vars[st.var] = out
                    else:
                        stdin = st.stdin_fmt.format(username=self.s.username, password=self.s.password) if st.stdin_fmt else None
                        rc = self.x.run(self._argv(st, str(conf)), stdin, self._log)
                        if rc != 0 and not st.tolerate_failure:
                            raise InstallError(f"{st.argv[0]} failed (exit {rc})")
                        if rc != 0:
                            self._log(f"warning: {st.argv[0]} failed (exit {rc}) but this step is optional")
                except (InstallError, OSError) as exc:
                    self.emit({"type": "error", "step": st.title, "message": str(exc), "tail": self.tail[-15:],
                               "disk_modified": self.destructive_started})
                    return False
            self.emit({"type": "done"})
            return True
        finally:
            shutil.rmtree(conf_dir, ignore_errors=True)
            try:
                self.x.run(["umount", "-R", self.target], None, lambda l: None)
            except OSError:
                pass
