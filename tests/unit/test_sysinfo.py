import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from chudos_monitor import sysinfo as si


def proc(tmp_path, stat=None, meminfo=None, cpuinfo=None, uptime=None):
    if stat is not None: (tmp_path / "stat").write_text(stat)
    if meminfo is not None: (tmp_path / "meminfo").write_text(meminfo)
    if cpuinfo is not None: (tmp_path / "cpuinfo").write_text(cpuinfo)
    if uptime is not None: (tmp_path / "uptime").write_text(uptime)
    return tmp_path


def test_cpu_first_sample_is_unavailable_not_zero(tmp_path):
    p = proc(tmp_path, stat="cpu  100 0 100 800 0 0 0 0 0 0\n")
    s = si.CpuSampler(p)
    first = s.sample()
    assert not first.available and first.value is None and "second" in first.reason


def test_cpu_percent_from_two_samples(tmp_path):
    p = proc(tmp_path, stat="cpu  100 0 100 800 0 0 0 0 0 0\n")
    s = si.CpuSampler(p); s.sample()
    proc(tmp_path, stat="cpu  200 0 200 900 0 0 0 0 0 0\n")   # +200 busy, +100 idle
    assert s.sample().value == pytest.approx(66.7, abs=0.1)


def test_cpu_zero_is_real_zero_when_fully_idle(tmp_path):
    p = proc(tmp_path, stat="cpu  10 0 10 100 0 0 0 0 0 0\n")
    s = si.CpuSampler(p); s.sample()
    proc(tmp_path, stat="cpu  10 0 10 200 0 0 0 0 0 0\n")
    m = s.sample()
    assert m.available and m.value == 0.0


def test_cpu_no_time_elapsed_and_unreadable(tmp_path):
    p = proc(tmp_path, stat="cpu  1 0 1 1 0 0 0 0 0 0\n")
    s = si.CpuSampler(p); s.sample()
    assert "no CPU time" in s.sample().reason
    assert not si.CpuSampler(tmp_path / "missing").sample().available
    proc(tmp_path, stat="cpu  a b c\n")
    assert si.read_cpu_times(tmp_path) is None
    proc(tmp_path, stat="intr 1 2 3\n")
    assert si.read_cpu_times(tmp_path) is None


def test_memory_values_and_missing_fields(tmp_path):
    p = proc(tmp_path, meminfo="MemTotal: 1000 kB\nMemAvailable: 400 kB\nMemFree: 1 kB\n")
    v = si.memory(p).value
    assert v == {"total": 1024000, "available": 409600, "used": 614400}
    proc(tmp_path, meminfo="MemTotal: 1000 kB\n")
    assert "not guessing" in si.memory(p).reason
    proc(tmp_path, meminfo="garbage")
    assert not si.memory(p).available
    assert not si.memory(tmp_path / "nope").available


def test_memory_available_never_exceeds_total(tmp_path):
    p = proc(tmp_path, meminfo="MemTotal: 100 kB\nMemAvailable: 900 kB\n")
    assert si.memory(p).value["used"] == 0


def test_storage_ok_error_and_zero_size():
    ok = si.storage("/x", usage=lambda p: SimpleNamespace(total=100, used=40, free=60))
    assert ok.value == {"path": "/x", "total": 100, "used": 40, "free": 60}
    def boom(p): raise FileNotFoundError(2, "No such file or directory")
    assert "cannot stat" in si.storage("/nope", usage=boom).reason
    assert "zero size" in si.storage("/proc", usage=lambda p: SimpleNamespace(total=0, used=0, free=0)).reason


def test_os_and_chudos_release(tmp_path):
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/os-release").write_text('NAME="Arch Linux"\nPRETTY_NAME="Arch Linux"\n')
    (tmp_path / "etc/chudos-release").write_text('NAME="ChudOS"\nVERSION="0.1.0"\n')
    assert si.os_name(tmp_path).value == "Arch Linux" and si.chudos_version(tmp_path).value == "0.1.0"
    assert not si.os_name(tmp_path / "x").available and not si.chudos_version(tmp_path / "x").available


def test_cpu_model_and_uptime(tmp_path):
    p = proc(tmp_path, cpuinfo="processor : 0\nmodel name\t: Test CPU 9000\n", uptime="3661.5 100.0\n")
    assert si.cpu_model(p).value == "Test CPU 9000" and si.uptime_seconds(p).value == 3661.5
    proc(tmp_path, cpuinfo="processor : 0\n", uptime="x")
    assert not si.cpu_model(p).available and not si.uptime_seconds(p).available


def run_result(rc, out=""):
    return lambda argv: subprocess.CompletedProcess(argv, rc, stdout=out, stderr="")


def test_updates_states():
    which = lambda t: "/usr/bin/checkupdates"
    assert si.pending_updates(run_result(0, "a 1 -> 2\nb 3 -> 4\n"), which).value == ["a 1 -> 2", "b 3 -> 4"]
    none = si.pending_updates(run_result(2), which)
    assert none.available and none.value == []            # up to date is a real, available answer
    assert "exited 1" in si.pending_updates(run_result(1), which).reason
    assert "pacman-contrib" in si.pending_updates(run_result(0), lambda t: None).reason


def test_updates_timeout_and_oserror():
    def to(argv): raise subprocess.TimeoutExpired(argv, 1)
    def oe(argv): raise OSError("nope")
    assert "failed" in si.pending_updates(to, lambda t: "x").reason
    assert "failed" in si.pending_updates(oe, lambda t: "x").reason


def test_formatters():
    assert si.human_bytes(512) == "512 B" and si.human_bytes(1536) == "1.5 KiB" and si.human_bytes(3 * 1024**3) == "3.0 GiB"
    assert si.human_duration(90061) == "1d 1h 1m" and si.human_duration(125) == "2m"


def test_real_proc_on_this_host_does_not_crash():
    assert si.kernel().available
    si.memory(); si.cpu_model(); si.storage("/"); si.uptime_seconds(); si.os_name()


NETDEV = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 9999 1 0 0 0 0 0 0 9999 1 0 0 0 0 0 0
  eth0: {rx} 10 0 0 0 0 0 0 {tx} 10 0 0 0 0 0 0
"""


def test_net_sampler_rates_ignore_loopback_and_first_is_unavailable(tmp_path):
    (tmp_path / "net").mkdir()
    (tmp_path / "net/dev").write_text(NETDEV.format(rx=1000, tx=500))
    t = iter([100.0, 102.0])
    s = si.NetSampler(tmp_path, clock=lambda: next(t))
    assert not s.sample().available
    (tmp_path / "net/dev").write_text(NETDEV.format(rx=3000, tx=900))
    assert s.sample().value == {"rx_per_s": 1000.0, "tx_per_s": 200.0}


def test_net_sampler_failure_modes(tmp_path):
    assert "no network interfaces" in si.NetSampler(tmp_path).sample().reason
    (tmp_path / "net").mkdir()
    (tmp_path / "net/dev").write_text(NETDEV.format(rx=1000, tx=500))
    t = iter([1.0, 1.0, 2.0])
    s = si.NetSampler(tmp_path, clock=lambda: next(t)); s.sample()
    assert "no time elapsed" in s.sample().reason
    (tmp_path / "net/dev").write_text(NETDEV.format(rx=10, tx=5))
    assert "reset" in s.sample().reason
