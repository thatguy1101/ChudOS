import json

from chudos_welcome import state


def test_state_path_uses_xdg_state_home(tmp_path):
    p = state.state_path({"XDG_STATE_HOME": str(tmp_path)})
    assert p == tmp_path / "chudos" / "welcome.json"


def test_state_path_falls_back_to_home(tmp_path):
    p = state.state_path({"HOME": str(tmp_path)})
    assert p == tmp_path / ".local" / "state" / "chudos" / "welcome.json"


def test_missing_file_means_show(tmp_path):
    assert state.should_show(tmp_path / "nope.json") is True


def test_roundtrip_dismissed(tmp_path):
    p = tmp_path / "s" / "welcome.json"
    state.save(p, True)
    assert state.load(p)["dismissed"] is True
    assert state.should_show(p) is False
    assert not p.with_suffix(".json.tmp").exists()


def test_force_and_live_override_dismissed(tmp_path):
    p = tmp_path / "w.json"
    state.save(p, True)
    assert state.should_show(p, force=True) is True
    assert state.should_show(p, live_session=True) is True


def test_corrupt_json_is_treated_as_default(tmp_path):
    p = tmp_path / "w.json"
    p.write_text("{not json", encoding="utf-8")
    assert state.load(p)["dismissed"] is False


def test_wrong_shape_or_version_is_default(tmp_path):
    p = tmp_path / "w.json"
    for bad in ([], {"version": 99, "dismissed": True}, {"version": 1, "dismissed": "yes"}):
        p.write_text(json.dumps(bad), encoding="utf-8")
        assert state.load(p) == {"version": 1, "dismissed": False}


def test_save_failure_raises_oserror(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    try:
        state.save(blocker / "sub" / "w.json", True)
    except OSError:
        return
    raise AssertionError("expected OSError")
