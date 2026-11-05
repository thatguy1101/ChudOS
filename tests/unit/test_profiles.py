import json
import shutil
from pathlib import Path

import pytest

from chudos_profiles import apply as ap
from chudos_profiles import cli, schema, sound
from chudos_profiles.schema import ValidationError, validate_profile
from chudos_profiles.store import BUILTIN_IDS, ProfileStore, StoreError, parse_json_bytes

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path):
    return ProfileStore(ROOT / "profiles", tmp_path / "cfg", tmp_path / "state")


class FakeKDE:
    """Stands in for kreadconfig6/kwriteconfig6/plasma-apply-colorscheme/qdbus6 with a dict."""
    def __init__(self):
        self.db = {}
        self.calls = []
        self.fail_on = None       # substring of argv that makes a call fail
        self.reloads = 0

    def __call__(self, argv):
        self.calls.append(argv)
        if self.fail_on and self.fail_on in " ".join(argv):
            return 1, "boom"
        tool = argv[0]
        if tool == "kreadconfig6":
            key = (argv[2], argv[4], argv[6])
            return (0, self.db[key]) if key in self.db else (0, "")
        if tool == "kwriteconfig6":
            self.db[(argv[2], argv[4], argv[6])] = argv[7]
            return 0, ""
        if tool == "plasma-apply-colorscheme":
            h = argv[2]
            self.db[("kdeglobals", "General", "AccentColor")] = ",".join(str(int(h[i:i+2], 16)) for i in (1, 3, 5))
            return 0, ""
        if tool in ("qdbus6", "qdbus"):
            self.reloads += 1
            return 0, ""
        return 127, "unknown"


def backend(tmp_path, kde, missing=()):
    which = lambda t: None if t in missing else f"/usr/bin/{t}"
    return ap.Backend(runner=kde, which=which, sound_cfg=tmp_path / "sound.json")


# ---------- schema ----------
def good(**over):
    d = {"format_version": 1, "id": "mine", "name": "Mine", "description": "", "settings": {}}
    d.update(over)
    return d


@pytest.mark.parametrize("bad", [
    good(format_version=2), good(id="Bad Id"), good(id="-x"), good(id="a" * 41), good(name=""),
    good(name="x" * 41), good(name="a\nb"), good(settings=[]), good(extra=1),
    good(settings={"nope": 1}),
    good(settings={"effects.blur": "yes"}),
    good(settings={"effects.animation_speed": 0.1}),
    good(settings={"effects.animation_speed": 9}),
    good(settings={"effects.animation_speed": float("nan")}),
    good(settings={"effects.animation_speed": True}),
    good(settings={"sound.volume": 101}), good(settings={"sound.volume": 5.5}),
    good(settings={"appearance.accent_color": "red"}),
    [], "str", None,
])
def test_invalid_profiles_rejected(bad):
    with pytest.raises(ValidationError):
        validate_profile(bad)


def test_valid_edge_values():
    p = validate_profile(good(settings={"effects.animation_speed": 0, "sound.volume": 0, "sound.enabled": False,
                                        "appearance.accent_color": "#ABCDEF"}))
    assert p["settings"]["appearance.accent_color"] == "#abcdef"


def test_builtin_files_are_valid_and_complete():
    for pid in BUILTIN_IDS:
        prof = parse_json_bytes((ROOT / "profiles" / f"{pid}.json").read_bytes())
        assert prof["id"] == pid
        assert set(prof["settings"]) == set(schema.SETTINGS)


def test_parse_rejects_big_dupes_and_garbage():
    with pytest.raises(ValidationError):
        parse_json_bytes(b" " * 70000)
    with pytest.raises(ValidationError):
        parse_json_bytes(b'{"id":"a","id":"b"}')
    with pytest.raises(ValidationError):
        parse_json_bytes(b"\xff\xfe")
    with pytest.raises(ValidationError):
        parse_json_bytes(b"[" * 100000)


# ---------- store ----------
def test_list_has_builtins_first_and_active_none(store):
    profs, warns = store.list()
    assert [p["id"] for p in profs] == list(BUILTIN_IDS) and warns == []
    assert store.active() is None


def test_create_duplicate_edit_delete_custom(store):
    store.create("work", "Work", "desc", {"effects.blur": False})
    store.duplicate("work", "work2", "Work 2")
    assert store.get("work2")["settings"] == {"effects.blur": False}
    store.save(dict(store.get("work"), settings={"effects.blur": True}))
    assert store.get("work")["settings"]["effects.blur"] is True
    store.delete("work")
    with pytest.raises(StoreError):
        store.get("work")


def test_cannot_create_over_builtin_or_delete_builtin(store):
    with pytest.raises(StoreError):
        store.create("zen", "x")
    for pid in BUILTIN_IDS:
        with pytest.raises(StoreError):
            store.delete(pid)


def test_builtin_customise_and_reset(store):
    custom = dict(store.get("zen"), settings={"sound.volume": 5})
    store.save(custom)
    assert store.get("zen")["settings"] == {"sound.volume": 5}
    assert [p for p in store.list()[0] if p["id"] == "zen"][0]["modified"] is True
    store.reset("zen")
    assert store.get("zen")["settings"]["sound.volume"] == 20
    with pytest.raises(StoreError):
        store.reset("nonbuiltin")


def test_corrupt_user_file_is_warning_not_crash(store):
    store.create("ok", "Ok")
    (store.user_dir / "broken.json").write_text("{nope")
    profs, warns = store.list()
    assert "ok" in [p["id"] for p in profs] and any("broken" in w for w in warns)


def test_id_filename_mismatch_rejected(store):
    store.create("a", "A")
    shutil.copy(store.user_dir / "a.json", store.user_dir / "b.json")
    with pytest.raises(StoreError):
        store.get("b")


def test_path_traversal_ids_rejected(store):
    for bad in ("../etc/passwd", "a/b", ""):
        with pytest.raises(StoreError):
            store.get(bad)


def test_export_import_roundtrip(store, tmp_path):
    store.create("trip", "Trip", settings={"sound.volume": 10})
    out = tmp_path / "trip.json"
    store.export_to("trip", out)
    store.delete("trip")
    assert store.import_from(out)["id"] == "trip"
    with pytest.raises(StoreError):
        store.import_from(out)                      # exists, no overwrite
    store.import_from(out, overwrite=True)


def test_import_refuses_builtin_ids_and_bad_files(store, tmp_path):
    f = tmp_path / "x.json"
    f.write_text(json.dumps(good(id="hyper")))
    with pytest.raises(StoreError):
        store.import_from(f)
    f.write_text(json.dumps(good(settings={"run": "rm -rf /"})))
    with pytest.raises(ValidationError):
        store.import_from(f)
    with pytest.raises(StoreError):
        store.import_from(tmp_path / "missing.json")
    assert not store.user_dir.exists() or list(store.user_dir.glob("*.json")) == []


def test_deleting_active_profile_clears_active(store):
    store.create("tmp", "Tmp")
    store.set_active("tmp")
    store.delete("tmp")
    assert store.active() is None


def test_corrupt_active_state_ignored(store):
    store.state_file.parent.mkdir(parents=True)
    store.state_file.write_text("garbage")
    assert store.active() is None


# ---------- apply ----------
def test_apply_writes_real_keys_and_records_active(store, tmp_path):
    kde = FakeKDE()
    res = ap.apply_profile(store, "lock-in", backend(tmp_path, kde))
    assert res.ok and store.active() == "lock-in"
    assert kde.db[("kdeglobals", "KDE", "AnimationDurationFactor")] == "0"
    assert kde.db[("kwinrc", "Plugins", "blurEnabled")] == "false"
    assert kde.db[("kdeglobals", "General", "AccentColor")] == "108,140,255"
    assert sound.load(tmp_path / "sound.json") == {"enabled": False, "volume": 0}
    assert kde.reloads == 1


def test_animation_speed_maps_to_duration_factor(store, tmp_path):
    kde = FakeKDE()
    ap.apply_profile(store, "hyper", backend(tmp_path, kde))
    assert float(kde.db[("kdeglobals", "KDE", "AnimationDurationFactor")]) == pytest.approx(0.6667, abs=1e-3)


def test_second_apply_skips_unchanged_and_does_not_write(store, tmp_path):
    kde = FakeKDE()
    ap.apply_profile(store, "zen", backend(tmp_path, kde))
    kde.calls.clear()
    res = ap.apply_profile(store, "zen", backend(tmp_path, kde))
    assert res.applied == [] and len(res.unchanged) == 5
    assert not any(c[0] in ("kwriteconfig6", "plasma-apply-colorscheme", "qdbus6") for c in kde.calls)
    assert kde.reloads == 1  # none added


def test_partial_profile_leaves_other_settings_alone(store, tmp_path):
    kde = FakeKDE()
    kde.db[("kwinrc", "Plugins", "blurEnabled")] = "true"
    store.create("only-sound", "S", settings={"sound.volume": 10})
    ap.apply_profile(store, "only-sound", backend(tmp_path, kde))
    assert kde.db[("kwinrc", "Plugins", "blurEnabled")] == "true"
    assert not any(c[0] == "kwriteconfig6" for c in kde.calls)


def test_failure_rolls_back_earlier_changes(store, tmp_path):
    kde = FakeKDE()
    kde.db[("kdeglobals", "General", "AccentColor")] = "1,2,3"
    kde.db[("kdeglobals", "KDE", "AnimationDurationFactor")] = "1"
    kde.db[("kwinrc", "Plugins", "blurEnabled")] = "true"
    kde.fail_on = "kwriteconfig6 --file kwinrc"          # blur WRITE fails (reads still work)
    store.save(dict(store.get("lock-in"), settings={          # applied in sorted order: accent, speed, blur
        "appearance.accent_color": "#112233", "effects.animation_speed": 0, "effects.blur": False}))
    res = ap.apply_profile(store, "lock-in", backend(tmp_path, kde))
    assert not res.ok and list(res.failed) == ["effects.blur"]
    assert store.active() is None
    assert kde.db[("kdeglobals", "General", "AccentColor")] == "1,2,3"       # restored
    assert kde.db[("kdeglobals", "KDE", "AnimationDurationFactor")] == "1.0"  # restored (1/1.0)
    assert kde.db[("kwinrc", "Plugins", "blurEnabled")] == "true"
    assert set(res.rolled_back) == {"appearance.accent_color", "effects.animation_speed"}
    assert res.not_restored == [] and res.applied == []


def test_rollback_reports_settings_with_unknown_previous_value(store, tmp_path):
    kde = FakeKDE()                     # blur unset -> previous unknown
    store.save(dict(store.get("zen"), settings={"effects.blur": False, "sound.volume": 10}))
    real_write = ap.Backend.write

    def flaky(self, sid, value):
        if sid == "sound.volume":
            raise ap.ApplyError("disk full")
        return real_write(self, sid, value)
    ap.Backend.write = flaky
    try:
        res = ap.apply_profile(store, "zen", backend(tmp_path, kde))
    finally:
        ap.Backend.write = real_write
    assert not res.ok and res.not_restored == ["effects.blur"] and res.applied == ["effects.blur"]


def test_missing_tools_reported_unavailable_not_fabricated(store, tmp_path):
    kde = FakeKDE()
    res = ap.apply_profile(store, "hyper", backend(tmp_path, kde, missing=("kwriteconfig6", "kreadconfig6", "plasma-apply-colorscheme")))
    assert res.ok
    assert set(res.unavailable) == {"appearance.accent_color", "effects.animation_speed", "effects.blur"}
    assert res.applied == ["sound.volume"] and res.unchanged == ["sound.enabled"]
    assert kde.calls == []


def test_missing_qdbus_is_warning_not_failure(store, tmp_path):
    kde = FakeKDE()
    res = ap.apply_profile(store, "zen", backend(tmp_path, kde, missing=("qdbus6", "qdbus")))
    assert res.ok and any("next login" in w for w in res.warnings)


def test_kwin_reload_failure_is_warning(store, tmp_path):
    kde = FakeKDE()
    kde.fail_on = "reconfigure"
    res = ap.apply_profile(store, "zen", backend(tmp_path, kde))
    assert res.ok and any("KWin reload failed" in w for w in res.warnings)


def test_overlapping_apply_is_refused(store, tmp_path):
    kde = FakeKDE()
    with ap.apply_lock(store.lock_file):
        with pytest.raises(ap.ApplyError, match="in progress"):
            ap.apply_profile(store, "zen", backend(tmp_path, kde))
    assert ap.apply_profile(store, "zen", backend(tmp_path, kde)).ok   # lock released


def test_unknown_profile_errors(store, tmp_path):
    with pytest.raises(StoreError):
        ap.apply_profile(store, "nope", backend(tmp_path, FakeKDE()))


def test_runner_handles_missing_binary_and_timeout():
    assert ap.default_runner(["definitely-not-a-real-binary-xyz"])[0] == 127


# ---------- sound ----------
def test_sound_disabled_or_zero_volume_never_spawns(tmp_path):
    spawn = lambda *a, **k: (_ for _ in ()).throw(AssertionError("spawned"))
    assert sound.play("profile-applied", {"enabled": False, "volume": 50}, popen=spawn) == "disabled"
    assert sound.play("profile-applied", {"enabled": True, "volume": 0}, popen=spawn) == "disabled"


def test_sound_player_selection_and_volume(tmp_path):
    (tmp_path / "profile-applied.wav").write_bytes(b"RIFF")
    calls = []
    st = sound.play("profile-applied", {"enabled": True, "volume": 40}, dirs=(tmp_path,),
                    which=lambda t: "/x" if t == "pw-play" else None, popen=lambda a, **k: calls.append(a))
    assert st == "played" and calls[0][:3] == ["pw-play", "--volume", "0.40"]
    calls.clear()
    sound.play("profile-applied", {"enabled": True, "volume": 50}, dirs=(tmp_path,),
               which=lambda t: "/x" if t == "paplay" else None, popen=lambda a, **k: calls.append(a))
    assert calls[0][:3] == ["paplay", "--volume", "32768"]


def test_sound_degrades_without_asset_or_player(tmp_path):
    cfg = {"enabled": True, "volume": 50}
    assert sound.play("profile-applied", cfg, dirs=(tmp_path,)) == "no-asset"
    (tmp_path / "profile-applied.wav").write_bytes(b"x")
    assert sound.play("profile-applied", cfg, dirs=(tmp_path,), which=lambda t: None) == "no-player"
    assert sound.play("../../etc/passwd", cfg, dirs=(tmp_path,)) == "no-asset"


def test_sound_config_corrupt_falls_back_to_defaults(tmp_path):
    p = tmp_path / "s.json"
    p.write_text('{"enabled": "yes", "volume": 999}')
    assert sound.load(p) == {"enabled": True, "volume": 50}


# ---------- cli ----------
def run_cli(store, *args):
    import io
    o, e = io.StringIO(), io.StringIO()
    rc = cli.main(list(args), store=store, out=o, err=e)
    return rc, o.getvalue(), e.getvalue()


def test_cli_list_create_set_delete(store):
    rc, out, _ = run_cli(store, "list")
    assert rc == 0 and "hyper" in out
    assert run_cli(store, "create", "mine", "Mine")[0] == 0
    assert run_cli(store, "set", "mine", "sound.volume", "12")[0] == 0
    assert store.get("mine")["settings"]["sound.volume"] == 12
    rc, _, err = run_cli(store, "set", "mine", "sound.volume", "500")
    assert rc == 1 and "between" in err
    rc, _, err = run_cli(store, "set", "mine", "sound.volume", "{bad")
    assert rc == 1 and "JSON" in err
    assert run_cli(store, "delete", "mine")[0] == 0
    rc, _, err = run_cli(store, "delete", "zen")
    assert rc == 1 and "built-in" in err


def test_cli_apply_reports_partial_when_settings_unavailable(store, tmp_path, monkeypatch):
    kde = FakeKDE()
    inst = backend(tmp_path, kde, missing=("kwriteconfig6", "kreadconfig6", "plasma-apply-colorscheme"))
    monkeypatch.setattr(ap, "Backend", lambda: inst)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "c"))
    rc, out, _ = run_cli(store, "apply", "hyper")
    assert rc == 0 and "PARTLY applied" in out and "3 setting(s) unavailable" in out
