import io
import subprocess
from pathlib import Path

import pytest

from chudos_store import cli
from chudos_store.catalogue import CATALOGUE, entries
from chudos_store.pacman import (PROTECTED, Pacman, StoreError, classify, parse_info, parse_search, validate_name,
                                 validate_query)

SEARCH = """extra/firefox 130.0-1 [installed]
    Fast, Private & Safe Web Browser
extra/firefox-i18n-de 130.0-1
    German language pack for Firefox
core/--evil 1.0-1
    should be dropped
"""


def cp(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


def pm(tmp_path, runner=None, stream=None, euid=1000, tools=("pacman", "pkexec")):
    return Pacman(runner=runner or (lambda a: cp()), which=lambda t: "/x" if t in tools else None, geteuid=lambda: euid,
                  lock_file=tmp_path / "db.lck", stream=stream)


@pytest.mark.parametrize("bad", ["", "-S", "--root=/x", "a b", "a;b", "a$(x)", "A", "a/b", "a\nb", "x" * 101, "../x", None, 5])
def test_invalid_names_rejected(bad):
    with pytest.raises(StoreError) as e:
        validate_name(bad)
    assert e.value.kind == "invalid"


@pytest.mark.parametrize("ok", ["firefox", "lib32-mesa", "python-pyside6", "a", "gtk+", "libc++", "qt6-base", "foo.bar_baz@1"])
def test_valid_names_accepted(ok):
    assert validate_name(ok) == ok


@pytest.mark.parametrize("bad", ["", "   ", "-Syu", "a;b", "a|b", "$(id)", "`id`", "x" * 61, "a\nb", "a&b", "a'b"])
def test_bad_queries_rejected(bad):
    with pytest.raises(StoreError):
        validate_query(bad)


def test_parse_search_filters_untrusted_names_and_marks_installed():
    pk = parse_search(SEARCH)
    assert [p.name for p in pk] == ["firefox", "firefox-i18n-de"]
    assert pk[0].installed and not pk[1].installed and pk[0].description.startswith("Fast")


def test_parse_info_multiline():
    d = parse_info("Name            : foo\nDescription     : a b\n                  c d\nVersion         : 1\n")
    assert d == {"Name": "foo", "Description": "a b c d", "Version": "1"}


def test_search_uses_argv_with_double_dash(tmp_path):
    seen = []
    p = pm(tmp_path, runner=lambda a: (seen.append(a) or cp(0, SEARCH)))
    assert len(p.search("fire fox")) == 2
    assert seen == [["pacman", "-Ss", "--", "fire fox"]]


def test_search_no_matches_is_empty_not_error(tmp_path):
    assert pm(tmp_path, runner=lambda a: cp(1, "")).search("zzzz") == []


def test_search_failure_with_error_text_is_not_reported_as_no_results(tmp_path):
    with pytest.raises(StoreError) as e:
        pm(tmp_path, runner=lambda a: cp(1, "", "error: failed to synchronize all databases (unable to lock database)")).search("x")
    assert e.value.kind == "locked"


def test_search_pacman_missing_and_failure(tmp_path):
    with pytest.raises(StoreError) as e:
        pm(tmp_path, tools=()).search("x")
    assert e.value.kind == "tool"
    with pytest.raises(StoreError) as e:
        pm(tmp_path, runner=lambda a: cp(1, "", "error: failed retrieving file 'x' from mirror")).search("x")
    assert e.value.kind == "network"
    def boom(a): raise subprocess.TimeoutExpired(a, 60)
    with pytest.raises(StoreError) as e:
        pm(tmp_path, runner=boom).search("x")
    assert e.value.kind == "failed"


def test_info_includes_installed_flag_and_not_found(tmp_path):
    def runner(a):
        if a[1] == "-Si": return cp(0, "Name : foo\nVersion : 1\n")
        return cp(0)
    assert pm(tmp_path, runner=runner).info("foo")["Installed"] == "yes"
    with pytest.raises(StoreError) as e:
        pm(tmp_path, runner=lambda a: cp(1, "", "error: package 'foo' was not found")).info("foo")
    assert e.value.kind == "failed"
    with pytest.raises(StoreError) as e:
        pm(tmp_path, runner=lambda a: cp(1, "", "error: target not found: foo")).info("foo")
    assert e.value.kind == "not-found"


def test_install_builds_safe_argv_and_streams_progress(tmp_path):
    seen, lines = [], []
    def stream(argv, on_line):
        seen.append(argv); on_line("downloading foo..."); on_line("installing foo..."); return 0
    r = pm(tmp_path, stream=stream).install(["foo", "bar"], lines.append)
    assert r.ok and lines == ["downloading foo...", "installing foo..."] and r.output == lines
    assert seen[0] == ["pkexec", "pacman", "-S", "--needed", "--noconfirm", "--", "foo", "bar"]
    assert "-y" not in seen[0] and "-Sy" not in seen[0] and "-u" not in seen[0]


def test_install_never_runs_as_root(tmp_path):
    called = []
    with pytest.raises(StoreError) as e:
        pm(tmp_path, euid=0, stream=lambda a, f: called.append(a) or 0).install(["foo"])
    assert e.value.kind == "privilege" and called == []


def test_install_refuses_when_locked_or_no_pkexec(tmp_path):
    (tmp_path / "db.lck").write_text("")
    called = []
    with pytest.raises(StoreError) as e:
        pm(tmp_path, stream=lambda a, f: called.append(a) or 0).install(["foo"])
    assert e.value.kind == "locked" and called == []
    (tmp_path / "db.lck").unlink()
    with pytest.raises(StoreError) as e:
        pm(tmp_path, tools=("pacman",)).install(["foo"])
    assert e.value.kind == "tool"


def test_install_validates_every_name_before_privilege(tmp_path):
    called = []
    for names in (["ok", "--noconfirm"], [], ["a"] * 21, ["a b"]):
        with pytest.raises(StoreError):
            pm(tmp_path, stream=lambda a, f: called.append(a) or 0).install(names)
    assert called == []


@pytest.mark.parametrize("out,kind", [
    ("error: failed to init transaction (unable to lock database)", "locked"),
    ("error: foo: signature from \"X\" is unknown trust", "signature"),
    ("error: failed retrieving file 'foo' from mirror: Could not resolve host", "network"),
    ("error: Partition / too full: not enough free disk space", "space"),
    ("error: target not found: foo", "not-found"),
    ("error: failed to prepare transaction (could not satisfy dependencies)", "conflict"),
    ("something odd", "failed"),
])
def test_failures_are_classified(tmp_path, out, kind):
    r = pm(tmp_path, stream=lambda a, f: (f(out), 1)[1]).install(["foo"])
    assert not r.ok and r.kind == kind and r.message


def test_signature_failure_message_says_not_bypassed():
    assert "will not bypass" in classify("invalid or corrupted package (PGP signature)", 1)[1]


def test_polkit_denied_is_a_privilege_error(tmp_path):
    r = pm(tmp_path, stream=lambda a, f: (f("Error executing command as another user: Not authorized"), 127)[1]).install(["foo"])
    assert r.kind == "privilege"


def test_stream_oserror_reported(tmp_path):
    def boom(a, f): raise OSError("exec failed")
    r = pm(tmp_path, stream=boom).install(["foo"])
    assert not r.ok and "exec failed" in r.message


def test_remove_protected_and_normal(tmp_path):
    seen = []
    p = pm(tmp_path, stream=lambda a, f: (seen.append(a), 0)[1])
    for name in ("pacman", "linux", "chudos-control-center", "sddm"):
        with pytest.raises(StoreError):
            p.remove(name)
    assert p.remove("vlc").ok and seen == [["pkexec", "pacman", "-R", "--noconfirm", "--", "vlc"]]
    assert not any(flag in seen[0] for flag in ("-Rs", "-Rns", "-Rdd", "-dd", "--nodeps"))


def test_catalogue_is_valid_unique_and_not_protected():
    names = [e["name"] for e in entries()]
    assert len(names) == len(set(names)) == len(CATALOGUE)
    assert not set(names) & PROTECTED


def run_cli(*args, pm_, answer="n"):
    o, e = io.StringIO(), io.StringIO()
    rc = cli.main(list(args), pm=pm_, out=o, err=e, confirm=lambda prompt: answer)
    return rc, o.getvalue(), e.getvalue()


def test_cli_install_requires_confirmation(tmp_path):
    called = []
    p = pm(tmp_path, stream=lambda a, f: called.append(a) or 0)
    rc, out, _ = run_cli("install", "foo", pm_=p, answer="n")
    assert rc == 0 and "Nothing was changed" in out and called == []
    rc, _, _ = run_cli("install", "foo", pm_=p, answer="y")
    assert rc == 0 and len(called) == 1
    rc, _, _ = run_cli("install", "foo", "--yes", pm_=p)
    assert len(called) == 2


def test_cli_reports_errors_with_nonzero_status(tmp_path):
    rc, _, err = run_cli("search", "--", "-Syu", pm_=pm(tmp_path))
    assert rc == 1 and "invalid" in err
    rc, _, err = run_cli("install", "--yes", "foo", pm_=pm(tmp_path, euid=0))
    assert rc == 1 and "root" in err
