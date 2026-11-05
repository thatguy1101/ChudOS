from chudos_welcome import actions


def test_unknown_action_rejected():
    ok, msg = actions.run("rm -rf /", popen=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not spawn")))
    assert not ok and "Unknown" in msg


def test_missing_program_reported(monkeypatch):
    monkeypatch.setattr(actions.shutil, "which", lambda _: None)
    ok, msg = actions.run("settings", popen=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not spawn")))
    assert not ok and "not installed" in msg


def test_spawn_uses_argv_list_no_shell(monkeypatch):
    monkeypatch.setattr(actions.shutil, "which", lambda _: "/usr/bin/x")
    calls = []
    ok, _ = actions.run("terminal", popen=lambda argv, **kw: calls.append((argv, kw)))
    assert ok
    argv, kw = calls[0]
    assert isinstance(argv, list) and argv == ["konsole"]
    assert "shell" not in kw and kw["start_new_session"] is True


def test_spawn_oserror_is_reported(monkeypatch):
    monkeypatch.setattr(actions.shutil, "which", lambda _: "/usr/bin/x")

    def boom(*a, **k):
        raise PermissionError("denied")

    ok, msg = actions.run("files", popen=boom)
    assert not ok and "denied" in msg


def test_all_action_keys_unique_and_argv_nonempty():
    keys = [a.key for a in actions.ACTIONS]
    assert len(keys) == len(set(keys))
    assert all(a.argv for a in actions.ACTIONS)


def test_welcome_offers_profiles_and_control_centre_with_fixed_binaries():
    assert actions.get("controlcenter").argv == ("chudos-control-center",)
    assert actions.get("profiles").argv == ("chudos-profiles-gui",)
    assert actions.get("updates").argv == ("konsole",)
