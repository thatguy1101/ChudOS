import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from chudos_monitor import maintenance as mt


def cp(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


GIB = 1024**3


def test_preflight_blocks_on_lock_and_low_space(tmp_path):
    lock = tmp_path / "db.lck"
    ok = mt.preflight(lock, usage=lambda p: SimpleNamespace(total=100 * GIB, used=50 * GIB, free=50 * GIB))
    assert ok["blockers"] == [] and any("news" in w for w in ok["warnings"])
    lock.write_text("")
    low = mt.preflight(lock, usage=lambda p: SimpleNamespace(total=100 * GIB, used=99 * GIB, free=1 * GIB))
    assert len(low["blockers"]) == 2


def test_preflight_unreadable_space_is_warning_not_pass_or_crash(tmp_path):
    def boom(p): raise OSError(5, "I/O error")
    r = mt.preflight(tmp_path / "none", usage=boom)
    assert r["blockers"] == [] and any("Could not check free space" in w for w in r["warnings"])


@pytest.mark.parametrize("running,installed,expect", [
    ("6.12.1-arch1-1", "linux 6.12.1.arch1-1", False),
    ("6.12.1-arch1-1", "linux 6.12.4.arch1-1", True),
])
def test_restart_needed_compares_kernel(running, installed, expect):
    m = mt.restart_needed(running, run=lambda a: cp(0, installed + "\n"), which=lambda t: "/x")
    assert m.available and m.value is expect and m.estimate is True


def test_restart_needed_says_when_it_cannot_tell():
    assert "cannot compare" in mt.restart_needed("6.1.0-generic", run=lambda a: cp(0, "linux 6.12.1.arch1-1"), which=lambda t: "/x").reason
    assert "not installed" in mt.restart_needed("6.12.1-arch1-1", run=lambda a: cp(1), which=lambda t: "/x").reason
    assert "pacman is not installed" in mt.restart_needed("x", which=lambda t: None).reason
    def to(a): raise subprocess.TimeoutExpired(a, 1)
    assert "failed" in mt.restart_needed("6.12.1-arch1-1", run=to, which=lambda t: "/x").reason
    assert "parse" in mt.restart_needed("6.12.1-arch1-1", run=lambda a: cp(0, "\n"), which=lambda t: "/x").reason


def test_terminal_commands_are_fixed_and_full_upgrade_only():
    assert mt.terminal_command("update") == ["konsole", "-e", "sudo", "pacman", "-Syu"]
    assert mt.terminal_command("clean-cache") == ["konsole", "-e", "sudo", "paccache", "-r"]
    with pytest.raises(ValueError):
        mt.terminal_command("update; rm -rf /")
    for kind in ("update", "clean-cache"):
        assert "-Sy" not in mt.terminal_command(kind) and "--noconfirm" not in mt.terminal_command(kind)


def test_orphans_states():
    w = lambda t: "/x"
    assert mt.orphans(lambda a: cp(0, "a\nb-c\n"), w).value == ["a", "b-c"]
    empty = mt.orphans(lambda a: cp(1, ""), w)
    assert empty.available and empty.value == []                     # none is a real answer
    assert not mt.orphans(lambda a: cp(2, "", "err"), w).available
    assert mt.orphans(lambda a: cp(0, "ok\n../bad\nx;y\n"), w).value == ["ok"]   # untrusted output filtered
    assert not mt.orphans(which=lambda t: None).available


def test_cache_size_counts_files_not_dirs(tmp_path):
    (tmp_path / "a.pkg").write_bytes(b"x" * 100); (tmp_path / "b.pkg").write_bytes(b"y" * 50); (tmp_path / "d").mkdir()
    assert mt.cache_size(tmp_path).value == {"bytes": 150, "files": 2}
    assert not mt.cache_size(tmp_path / "missing").available


def test_cleanup_preview_is_dry_run_only():
    seen = []
    m = mt.cleanup_preview(lambda a: (seen.append(a) or cp(0, "==> finished dry run: 3 candidates (12 MiB)\n")), lambda t: "/x")
    assert seen == [["paccache", "-d"]] and m.available
    assert "pacman-contrib" in mt.cleanup_preview(which=lambda t: None).reason
    assert not mt.cleanup_preview(lambda a: cp(1), lambda t: "/x").available


def test_recent_errors_and_clamping():
    seen = []
    m = mt.recent_errors(10_000, lambda a: (seen.append(a) or cp(0, "line1\nline2\n")), lambda t: "/x")
    assert m.value == ["line1", "line2"] and seen[0][-1] == "500"
    assert mt.recent_errors(0, lambda a: (seen.append(a) or cp(0, "")), lambda t: "/x").value == []
    assert seen[-1][-1] == "1"
    assert "systemd-journal" in mt.recent_errors(run=lambda a: cp(1, "", "denied"), which=lambda t: "/x").reason
    assert not mt.recent_errors(which=lambda t: None).available


def test_largest_files_top_n_and_symlinks_ignored(tmp_path):
    for i, size in enumerate((10, 500, 30, 4000, 7)):
        (tmp_path / f"f{i}").write_bytes(b"x" * size)
    sub = tmp_path / "sub"; sub.mkdir(); (sub / "big").write_bytes(b"x" * 9000)
    (tmp_path / "link").symlink_to(sub / "big")
    m = mt.largest_files(tmp_path, count=3)
    assert [s for s, _ in m.value["files"]] == [9000, 4000, 500] and m.value["partial"] is False
    assert not any(p.endswith("link") for _, p in m.value["files"])


def test_largest_files_budget_reports_partial(tmp_path):
    for i in range(50):
        (tmp_path / f"f{i}").write_bytes(b"x")
    m = mt.largest_files(tmp_path, max_entries=10)
    assert m.value["partial"] is True and m.value["scanned"] > 10
    t = iter(range(0, 1000, 5))
    assert mt.largest_files(tmp_path, max_seconds=1, clock=lambda: next(t)).value["partial"] is True


def test_largest_files_missing_root_and_unreadable_subdir(tmp_path):
    assert not mt.largest_files(tmp_path / "nope").available
    d = tmp_path / "locked"; d.mkdir(); (d / "f").write_bytes(b"x"); (tmp_path / "ok").write_bytes(b"yy")
    d.chmod(0)
    try:
        m = mt.largest_files(tmp_path)
        assert m.available and any(p.endswith("ok") for _, p in m.value["files"])
    finally:
        d.chmod(0o755)


def test_nothing_in_module_deletes_anything():
    src = Path(mt.__file__).read_text()
    for banned in ("unlink", "rmtree", "os.remove", "rmdir", "os.rename", "shutil.move", "write_text", "write_bytes"):
        assert banned not in src
