import subprocess

import pytest

from chudos_control_center import tools


def test_tool_status_uses_which():
    st = dict((t.binary, ok) for t, ok in tools.tool_status(tools.DEV_TOOLS, which=lambda b: "/x" if b == "git" else None))
    assert st["git"] is True and st["node"] is False


def test_install_hint_dedupes_and_sorts():
    miss = [t for t in tools.DEV_TOOLS if t.binary in ("node", "npm", "git")]
    assert tools.install_hint(miss) == "sudo pacman -S git nodejs npm"
    assert tools.install_hint([]) == ""


def test_every_tool_has_tier_and_package():
    for t in tools.DEV_TOOLS + tools.GAME_TOOLS:
        assert t.tier in (tools.ESSENTIAL, tools.RECOMMENDED, tools.OPTIONAL) and t.package and t.binary


def test_kde_settings_argv_whitelist():
    assert tools.kde_settings_argv("kcm_colors") == ["systemsettings", "kcm_colors"]
    assert tools.kde_settings_argv(None) == ["systemsettings"]
    with pytest.raises(ValueError):
        tools.kde_settings_argv("kcm_colors; rm -rf /")


def test_launch_missing_and_oserror_and_ok():
    assert tools.launch(["nonexistent-xyz"], which=lambda b: None)[0] is False
    assert tools.launch([], which=lambda b: "x")[0] is False
    def boom(*a, **k): raise PermissionError("denied")
    ok, msg = tools.launch(["x"], which=lambda b: "/x", popen=boom)
    assert not ok and "denied" in msg
    calls = []
    assert tools.launch(["x", "a b"], which=lambda b: "/x", popen=lambda a, **k: calls.append((a, k)))[0]
    assert calls[0][0] == ["x", "a b"] and "shell" not in calls[0][1]


def test_terminal_argv_keeps_path_as_single_argument(tmp_path):
    weird = tmp_path / "a b; rm -rf"
    assert tools.terminal_argv(weird) == ["konsole", "--workdir", str(weird)]


@pytest.mark.parametrize("name,email", [("", "a@b.co"), ("x" * 101, "a@b.co"), ("a\nb", "a@b.co"),
                                        ("Ok", "nope"), ("Ok", "a@b"), ("Ok", "a b@c.de"), ("Ok", "<a@b.co>"), ("Ok", "a@b.co" + "x" * 260)])
def test_git_identity_validation_rejects(name, email):
    assert tools.validate_git_identity(name, email)


def test_git_identity_valid_and_set_uses_argv():
    assert tools.validate_git_identity("Max Q", "max@example.com") is None
    calls = []
    def run(argv, **k):
        calls.append(argv); return subprocess.CompletedProcess(argv, 0, "", "")
    ok, _ = tools.git_set_identity(" Max ", "max@example.com", run=run)
    assert ok and calls == [["git", "config", "--global", "user.name", "Max"], ["git", "config", "--global", "user.email", "max@example.com"]]


def test_git_set_failure_paths():
    bad = lambda argv, **k: subprocess.CompletedProcess(argv, 1, "", "locked")
    assert tools.git_set_identity("A", "a@b.co", run=bad) == (False, "git config user.name failed: locked")
    assert not tools.git_set_identity("", "a@b.co")[0]
    def to(argv, **k): raise subprocess.TimeoutExpired(argv, 5)
    assert not tools.git_set_identity("A", "a@b.co", run=to)[0]
    assert tools.git_get("user.name", run=to) is None
    assert tools.git_get("user.name", run=bad) is None


def test_guidance_mentions_no_partial_upgrades():
    assert "-Sy" in tools.UPDATE_GUIDANCE and "partial" in tools.UPDATE_GUIDANCE.lower()
