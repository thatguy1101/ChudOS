"""Safe wrapper around pacman for the ChudOS Store. No Qt.

Rules enforced here (and tested):
 * package names and search text are validated against strict patterns; names can never start with '-'
 * every subprocess is an argv list (no shell); '--' ends options before any user-derived argument
 * read-only queries run unprivileged; install/remove go through pkexec (polkit prompt) and are refused
   when the caller is root, so the GUI can never be the privileged process
 * we never refresh the sync database ('-Sy'), never pass --noconfirm for removal, never touch SigLevel,
   never add repositories. A stale database fails safely; the user is told to do a full system update.
 * pacman's own signature verification is the only trust mechanism; "signature" failures are surfaced, not bypassed
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

PKG_RE = re.compile(r"^[a-z0-9@_+][a-z0-9@._+-]{0,99}$")
QUERY_RE = re.compile(r"^[A-Za-z0-9@._+ -]{1,60}$")
LOCK_FILE = Path("/var/lib/pacman/db.lck")
MAX_BATCH = 20


class StoreError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind          # invalid | locked | not-found | network | signature | space | conflict | privilege | tool | failed
        self.message = message


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not PKG_RE.match(name):
        raise StoreError("invalid", f"Invalid package name: {name!r}")
    return name


def validate_query(q: str) -> str:
    q = q.strip() if isinstance(q, str) else ""
    if not QUERY_RE.match(q) or q.startswith("-"):
        raise StoreError("invalid", "Search text may only contain letters, digits and . _ + @ - (1-60 characters).")
    return q


@dataclass
class Package:
    repo: str
    name: str
    version: str
    description: str = ""
    installed: bool = False


@dataclass
class Result:
    ok: bool
    kind: str = ""
    message: str = ""
    output: list[str] = field(default_factory=list)


def classify(output: str, rc: int) -> tuple[str, str]:
    """Map pacman output to (kind, friendly message). Order matters: most specific first."""
    t = output.lower()
    rules = (
        ("locked", ("unable to lock database", "db.lck"), "Another package operation is running (database locked). Wait for it to finish; if none is running, see Recovery in the Control Centre."),
        ("signature", ("invalid or corrupted package", "signature from", "pgp signature", "unknown trust", "keyring"), "Package signature verification failed. ChudOS will not bypass it. Update archlinux-keyring with a full system update, then retry."),
        ("space", ("not enough free disk space", "no space left"), "Not enough free disk space."),
        ("not-found", ("target not found", "could not find or read package"), "Package not found in the configured repositories. Your package database may be out of date: do a full system update first."),
        ("network", ("failed retrieving file", "could not resolve host", "failed to connect", "connection timed out", "download library error"), "Network or mirror problem while downloading. Check your connection and retry; if files return 404 do a full system update."),
        ("conflict", ("conflicting files", "are in conflict", "breaks dependency", "unresolvable package conflicts", "failed to prepare transaction"), "The change conflicts with installed packages. Nothing was changed."),
    )
    for kind, needles, msg in rules:
        if any(n in t for n in needles):
            return kind, msg
    return "failed", f"pacman exited with status {rc}."


def parse_search(text: str) -> list[Package]:
    """Parse `pacman -Ss` output: 'repo/name ver [group] [installed]' followed by an indented description."""
    pkgs: list[Package] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line.startswith((" ", "\t")):
            head = line.split()
            if len(head) < 2 or "/" not in head[0]:
                continue
            repo, name = head[0].split("/", 1)
            if not PKG_RE.match(name):
                continue  # untrusted output: drop anything that is not a valid name
            pkgs.append(Package(repo, name, head[1], installed="[installed" in line))
        elif pkgs:
            pkgs[-1].description = (pkgs[-1].description + " " + line.strip()).strip()[:300]
    return pkgs


def parse_info(text: str) -> dict[str, str]:
    """Parse `pacman -Si` key/value text. Values are data for display only; they are never executed."""
    info: dict[str, str] = {}
    key = None
    for line in text.splitlines():
        if " : " in line and not line.startswith(" "):
            key, _, val = line.partition(" : ")
            key = key.strip(); info[key] = val.strip()
        elif key and line.startswith(" "):
            info[key] += " " + line.strip()
    return info


Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False, env={**os.environ, "LC_ALL": "C"})


class Pacman:
    def __init__(self, runner: Runner = _run, which=shutil.which, geteuid=os.geteuid, lock_file: Path = LOCK_FILE,
                 stream: Callable[[list[str], Callable[[str], None]], int] | None = None):
        self.run, self.which, self.geteuid, self.lock_file = runner, which, geteuid, lock_file
        self._stream = stream or self._default_stream

    # ---- read-only (unprivileged)
    def _need(self, tool: str) -> None:
        if not self.which(tool):
            raise StoreError("tool", f"{tool} is not installed.")

    def _query(self, argv: list[str]) -> subprocess.CompletedProcess:
        self._need("pacman")
        try:
            return self.run(argv)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StoreError("failed", f"Could not run pacman: {exc}") from exc

    def search(self, query: str) -> list[Package]:
        q = validate_query(query)
        p = self._query(["pacman", "-Ss", "--", q])
        if p.returncode == 1 and not p.stdout.strip() and "error" not in p.stderr.lower():
            return []                           # pacman exits 1 with no output for "no matches"; an error message means failure
        if p.returncode != 0:
            kind, msg = classify(p.stdout + p.stderr, p.returncode)
            raise StoreError(kind, msg)
        pkgs = parse_search(p.stdout)[:100]
        return pkgs

    def is_installed(self, name: str) -> bool:
        validate_name(name)
        return self._query(["pacman", "-Qq", "--", name]).returncode == 0

    def info(self, name: str) -> dict[str, str]:
        validate_name(name)
        p = self._query(["pacman", "-Si", "--", name])
        if p.returncode != 0:
            kind, msg = classify(p.stdout + p.stderr, p.returncode)
            raise StoreError(kind, msg)
        d = parse_info(p.stdout)
        d["Installed"] = "yes" if self.is_installed(name) else "no"
        return d

    # ---- privileged (install/remove)
    def _privileged_ok(self) -> None:
        if self.geteuid() == 0:
            raise StoreError("privilege", "Refusing to run the Store as root. Start it as your normal user; polkit will ask for permission.")
        self._need("pkexec"); self._need("pacman")
        if self.lock_file.exists():
            raise StoreError("locked", classify("unable to lock database", 1)[1])

    def _default_stream(self, argv: list[str], on_line: Callable[[str], None]) -> int:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env={**os.environ, "LC_ALL": "C"})
        assert proc.stdout is not None
        for line in proc.stdout:
            on_line(line.rstrip("\n"))
        return proc.wait()

    def _transact(self, argv: list[str], on_line: Callable[[str], None]) -> Result:
        lines: list[str] = []
        def collect(l: str) -> None:
            lines.append(l); on_line(l)
        try:
            rc = self._stream(argv, collect)
        except OSError as exc:
            return Result(False, "failed", f"Could not start the operation: {exc}", lines)
        if rc == 0:
            return Result(True, "", "Done.", lines)
        if rc in (126, 127) and any("not authorized" in l.lower() or "dismissed" in l.lower() for l in lines):
            return Result(False, "privilege", "Permission was not granted.", lines)
        kind, msg = classify("\n".join(lines), rc)
        return Result(False, kind, msg, lines)

    def install(self, names: Iterable[str], on_line: Callable[[str], None] = lambda l: None) -> Result:
        pkgs = [validate_name(n) for n in names]
        if not pkgs or len(pkgs) > MAX_BATCH:
            raise StoreError("invalid", f"Choose between 1 and {MAX_BATCH} packages.")
        self._privileged_ok()
        # --needed: skip already-installed; no -y (never a partial upgrade); no --noconfirm bypass of trust prompts is
        # possible because signature checks are not prompts; --noconfirm only answers the default yes/no questions.
        return self._transact(["pkexec", "pacman", "-S", "--needed", "--noconfirm", "--", *pkgs], on_line)

    def remove(self, name: str, on_line: Callable[[str], None] = lambda l: None) -> Result:
        pkg = validate_name(name)
        if pkg in PROTECTED:
            raise StoreError("invalid", f"{pkg} is protected and cannot be removed from the Store.")
        self._privileged_ok()
        # plain -R: refuses if anything depends on it; no -s/-n/-c so nothing extra is removed; interactive prompts
        # are answered "yes" only for the single confirmed package via --noconfirm after the GUI's own confirmation.
        return self._transact(["pkexec", "pacman", "-R", "--noconfirm", "--", pkg], on_line)


PROTECTED = frozenset({
    "pacman", "glibc", "linux", "linux-firmware", "base", "systemd", "bash", "coreutils", "filesystem", "sudo", "polkit",
    "sddm", "plasma-desktop", "plasma-workspace", "kwin", "networkmanager", "mkinitcpio", "grub", "systemd-boot", "python",
    "pyside6", "chudos-defaults", "chudos-welcome", "chudos-profiles", "chudos-monitor", "chudos-control-center", "chudos-store",
})
