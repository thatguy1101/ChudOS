import json
import io
from pathlib import Path

import pytest

from chudos_installer import backend, disks, engine, plan, settings
from chudos_installer.settings import SettingsError, validate

GIB = 1024**3


@pytest.fixture
def zoneinfo(tmp_path):
    z = tmp_path / "zoneinfo"; (z / "Australia").mkdir(parents=True)
    (z / "Australia/Perth").write_text("x"); (z / "UTC").write_text("x")
    return z


def raw(**over):
    d = dict(disk="/dev/sda", hostname="chudbox", username="max", fullname="Max Q", password="hunter2", timezone="Australia/Perth",
             locale="en_AU.UTF-8", keymap="us")
    d.update(over)
    return d


# ---------------- settings validation ----------------
def test_valid_settings(zoneinfo):
    s = validate(raw(), zoneinfo)
    assert s.disk == "/dev/sda" and "password" not in s.public() and s.hostname == "chudbox"


@pytest.mark.parametrize("field,value", [
    ("disk", "/dev/sda1"), ("disk", "/dev/loop0"), ("disk", "/dev/sda; rm -rf /"), ("disk", "sda"), ("disk", "/dev/zram0"), ("disk", "/dev/nvme0n1p2"),
    ("hostname", "-bad"), ("hostname", "has space"), ("hostname", "a" * 33), ("hostname", ""),
    ("username", "Root"), ("username", "root"), ("username", "1abc"), ("username", "a b"), ("username", "chud"), ("username", "x" * 32),
    ("fullname", ""), ("fullname", "a:b"), ("fullname", "a,b"), ("fullname", "a\nb"), ("fullname", "x" * 65),
    ("password", ""), ("password", "a\nb"), ("password", "x" * 129), ("password", "a\x00b"),
    ("timezone", "../etc/passwd"), ("timezone", "Nowhere/Land"), ("timezone", "Australia/../UTC"), ("timezone", "a b"),
    ("locale", "xx_XX.UTF-8"), ("locale", "en_US.UTF-8; reboot"), ("keymap", "evil"), ("keymap", "../us"),
])
def test_invalid_values_rejected(zoneinfo, field, value):
    with pytest.raises(SettingsError) as e:
        validate(raw(**{field: value}), zoneinfo)
    assert e.value.field == field


def test_missing_and_nonstring_fields_rejected(zoneinfo):
    for key in raw():
        r = raw(); del r[key]
        with pytest.raises(SettingsError):
            validate(r, zoneinfo)
    with pytest.raises(SettingsError):
        validate(raw(password=123), zoneinfo)


def test_curated_lists_are_consistent():
    assert all(k[1] in settings.KEYMAPS for k in settings.KEYBOARDS) and len(settings.LOCALE_VALUES) == len(settings.LOCALES)


# ---------------- disks ----------------
def lsblk(*nodes):
    return json.dumps({"blockdevices": list(nodes)})


def node(name, size=100 * GIB, typ="disk", mounts=(None,), children=None, ro=False, rm=False, model="Disk", **kw):
    d = {"name": name, "path": f"/dev/{name}", "size": size, "type": typ, "ro": ro, "rm": rm, "model": model, "mountpoints": list(mounts)}
    d.update(kw)
    if children is not None:
        d["children"] = children
    return d


def test_disk_filtering_and_reasons():
    text = lsblk(
        node("sda"),
        node("sdb", children=[node("sdb1", typ="part", mounts=["/run/archiso/bootmnt"], fstype="iso9660", label="CHUDOS")]),
        node("sdc", size=8 * GIB), node("sdd", ro=True), node("loop0", typ="loop", mounts=["/x"]),
        node("zram0", mounts=["[SWAP]"]), node("sr0", typ="rom"), node("nvme0n1", model="Fast SSD", rm=False, children=[node("nvme0n1p1", typ="part", fstype="ntfs", label="Windows")]),
    )
    ds = {d.path: d for d in disks.parse_lsblk(text)}
    assert set(ds) == {"/dev/sda", "/dev/sdb", "/dev/sdc", "/dev/sdd", "/dev/nvme0n1"}
    assert ds["/dev/sda"].usable and ds["/dev/nvme0n1"].usable
    assert not ds["/dev/sdb"].usable and "live USB" in ds["/dev/sdb"].reason
    assert "too small" in ds["/dev/sdc"].reason and ds["/dev/sdd"].reason == "read-only"
    assert any("ntfs" in c and "Windows" in c for c in ds["/dev/nvme0n1"].contents)


def test_old_lsblk_single_mountpoint_key_and_string_flags():
    d = disks.parse_lsblk(json.dumps({"blockdevices": [{"name": "sda", "path": "/dev/sda", "size": str(50 * GIB), "type": "disk", "ro": "0", "rm": "1",
                                                          "children": [{"name": "sda1", "mountpoint": "/", "type": "part"}]}]}))
    assert d[0].removable and not d[0].usable


def test_garbage_lsblk_is_empty_not_crash():
    assert disks.parse_lsblk("not json") == [] and disks.parse_lsblk("{}") == [] and disks.parse_lsblk(json.dumps({"blockdevices": [1, None]})) == []


def test_part_path_naming():
    assert disks.part_path("/dev/sda", 1) == "/dev/sda1" and disks.part_path("/dev/nvme0n1", 2) == "/dev/nvme0n1p2" and disks.part_path("/dev/mmcblk0", 1) == "/dev/mmcblk0p1"


# ---------------- plan ----------------
def settings_obj(zoneinfo, **over):
    return validate(raw(**over), zoneinfo)


def test_plan_follows_install_guide_order(zoneinfo):
    steps = plan.build_plan(settings_obj(zoneinfo), ["base", "linux"])
    cmds = [" ".join(s.argv) for s in steps if s.kind == "cmd"]
    idx = lambda prefix: next(i for i, c in enumerate(cmds) if c.startswith(prefix))
    assert idx("wipefs") < idx("sgdisk --zap-all") < idx("sgdisk --clear") < idx("mkfs.fat") < idx("mount /dev/sda2") < idx("pacstrap") < idx("bootctl")
    assert "sgdisk --clear --new=1:0:+1G --typecode=1:ef00 --change-name=1:ESP --new=2:0:0 --typecode=2:8300 --change-name=2:ChudOS /dev/sda" in cmds
    assert "mount -o umask=0077 /dev/sda1 /mnt/boot" in cmds
    assert "pacstrap -C @PACMAN_CONF@ -K /mnt base linux" in cmds


def test_only_destructive_steps_touch_the_disk_and_only_the_chosen_disk(zoneinfo):
    steps = plan.build_plan(settings_obj(zoneinfo, disk="/dev/nvme0n1"), ["base"])
    for st in steps:
        if st.destructive:
            assert any(a.startswith("/dev/nvme0n1") for a in st.argv)
    assert not any("/dev/sda" in " ".join(s.argv) for s in steps)
    assert [s for s in steps if s.destructive] and all(a.startswith("/dev/nvme0n1") for s in steps if s.destructive for a in s.argv if a.startswith("/dev/"))
    assert "mkfs.fat -F 32 -n ESP /dev/nvme0n1p1" in [" ".join(s.argv) for s in steps]


def test_password_never_in_plan(zoneinfo):
    s = settings_obj(zoneinfo, password="S3cr3t!pw")
    blob = json.dumps([st.__dict__ for st in plan.build_plan(s, ["base"])]) + "\n".join(plan.describe(plan.build_plan(s, ["base"])))
    assert "S3cr3t" not in blob
    chp = next(st for st in plan.build_plan(s, ["base"]) if st.argv == ("chpasswd",))
    assert chp.stdin_fmt == "{username}:{password}\n" and chp.chroot


def test_files_written_and_services(zoneinfo):
    st = {(s.path or " ".join(s.argv)): s for s in plan.build_plan(settings_obj(zoneinfo, keymap="dvorak", locale="de_DE.UTF-8", hostname="box"), ["base"])}
    assert st["/etc/locale.gen"].content == "de_DE.UTF-8 UTF-8\nen_US.UTF-8 UTF-8\n" and st["/etc/locale.conf"].content == "LANG=de_DE.UTF-8\n"
    assert st["/etc/vconsole.conf"].content == "KEYMAP=dvorak\n" and 'XkbVariant" "dvorak"' in st["/etc/X11/xorg.conf.d/00-keyboard.conf"].content
    assert st["/etc/sudoers.d/10-wheel"].mode == 0o440 and "127.0.1.1 box.localdomain box" in st["/etc/hosts"].content
    assert "root=UUID=$root_uuid rw" in st["/boot/loader/entries/chudos.conf"].content and "default chudos.conf" in st["/boot/loader/loader.conf"].content
    assert "systemctl enable NetworkManager.service sddm.service systemd-timesyncd.service" in st
    assert st["systemctl enable systemd-boot-update.service"].tolerate_failure


def test_bootloader_entry_loads_microcode_before_initramfs():
    e = plan.loader_entry().splitlines()
    assert e.index("initrd  /amd-ucode.img") < e.index("initrd  /initramfs-linux.img") and e.index("initrd  /intel-ucode.img") < e.index("initrd  /initramfs-linux.img")


def test_installer_pacman_conf_is_strict():
    c = plan.pacman_conf()
    assert "SigLevel = Never" not in c and c.count("TrustAll") == 1 and "[chudos]\nSigLevel = Optional TrustAll\nServer = file:///opt/chudos-repo" in c
    assert "http" not in c and "[multilib]" not in c and "[testing]" not in c


def test_describe_marks_erasing(zoneinfo):
    text = "\n".join(plan.describe(plan.build_plan(settings_obj(zoneinfo), ["base"])))
    assert "ERASES DATA" in text and "sgdisk --zap-all /dev/sda" in text


def test_read_package_list(tmp_path):
    f = tmp_path / "p.txt"; f.write_text("# c\nbase\nlinux # k\n")
    assert plan.read_package_list(f) == ["base", "linux"]
    f.write_text("base\n--noconfirm\n")
    with pytest.raises(ValueError):
        plan.read_package_list(f)
    f.write_text("# nothing\n")
    with pytest.raises(ValueError):
        plan.read_package_list(f)


# ---------------- engine ----------------
class FakeExec:
    def __init__(self, fail_on=None, uuid="1234-ABCD"):
        self.calls, self.stdins, self.fail_on, self.uuid = [], [], fail_on, uuid
    def run(self, argv, stdin_text, on_line):
        self.calls.append(argv); self.stdins.append(stdin_text); on_line("out: " + argv[0])
        return 1 if self.fail_on and self.fail_on in " ".join(argv) else 0
    def capture(self, argv):
        self.calls.append(argv)
        if argv[0] == "blkid": return 0, self.uuid
        if argv[0] == "genfstab": return 0, "UUID=1234 / ext4 rw 0 1"
        return 0, ""


def run_engine(zoneinfo, tmp_path, fail_on=None, **over):
    ev = []
    ex = FakeExec(fail_on)
    s = settings_obj(zoneinfo, **over)
    e = engine.Engine(s, ["base", "linux"], ev.append, executor=ex, target=str(tmp_path / "mnt"))
    return e.run(), ev, ex, tmp_path / "mnt"


def test_engine_success_writes_files_with_captured_values(zoneinfo, tmp_path):
    ok, ev, ex, tgt = run_engine(zoneinfo, tmp_path)
    assert ok and ev[-1] == {"type": "done"}
    assert "root=UUID=1234-ABCD rw" in (tgt / "boot/loader/entries/chudos.conf").read_text()
    assert (tgt / "etc/fstab").read_text().startswith("UUID=1234")
    assert oct((tgt / "etc/sudoers.d/10-wheel").stat().st_mode & 0o777) == "0o440"
    assert (tgt / "etc/hostname").read_text() == "chudbox\n"
    assert ex.calls[-1] == ["umount", "-R", str(tgt)]                     # always unmounts at the end
    assert not list(tgt.rglob("*.chudos-tmp"))


def test_engine_password_goes_only_to_stdin(zoneinfo, tmp_path):
    ok, ev, ex, tgt = run_engine(zoneinfo, tmp_path, password="Pa$$w0rd{x}")
    assert ok and "max:Pa$$w0rd{x}\n" in ex.stdins
    assert not any("Pa$$w0rd" in " ".join(c) for c in ex.calls) and "Pa$$w0rd" not in json.dumps(ev)
    assert not any("Pa$$w0rd" in p.read_text() for p in tgt.rglob("*") if p.is_file())


def test_engine_chroot_commands_use_arch_chroot_and_conf_is_substituted(zoneinfo, tmp_path):
    ok, ev, ex, tgt = run_engine(zoneinfo, tmp_path)
    assert ["arch-chroot", str(tgt), "locale-gen"] in ex.calls
    pac = next(c for c in ex.calls if c[0] == "pacstrap")
    assert "@PACMAN_CONF@" not in pac and pac[1] == "-C" and pac[2].endswith("pacman.conf")


def test_engine_failure_stops_reports_and_unmounts(zoneinfo, tmp_path):
    ok, ev, ex, tgt = run_engine(zoneinfo, tmp_path, fail_on="mkfs.ext4")
    err = ev[-1]
    assert not ok and err["type"] == "error" and "mkfs.ext4" in err["message"] and err["disk_modified"] is True
    assert not any(c[0] == "pacstrap" for c in ex.calls) and ex.calls[-1][0] == "umount"


def test_failure_before_destructive_steps_says_disk_unchanged(zoneinfo, tmp_path):
    ev = []
    ex = FakeExec(fail_on="true")
    steps = [plan.Step("first", argv=("true",))]
    e = engine.Engine(settings_obj(zoneinfo), [], ev.append, executor=ex, target=str(tmp_path), steps=steps)
    assert not e.run() and ev[-1]["disk_modified"] is False


def test_tolerated_failure_warns_and_continues(zoneinfo, tmp_path):
    ok, ev, ex, tgt = run_engine(zoneinfo, tmp_path, fail_on="hwclock")
    assert ok and any(e.get("type") == "log" and "optional" in e["line"] for e in ev)


def test_capture_failure_is_an_error(zoneinfo, tmp_path):
    ev = []
    class NoUuid(FakeExec):
        def capture(self, argv): return 1, ""
    e = engine.Engine(settings_obj(zoneinfo), ["base"], ev.append, executor=NoUuid(), target=str(tmp_path))
    assert not e.run() and "blkid failed" in ev[-1]["message"]


def test_write_refuses_paths_escaping_target(zoneinfo, tmp_path):
    ev = []
    steps = [plan.Step("evil", kind="write", path="/../etc/evil", content="x")]
    e = engine.Engine(settings_obj(zoneinfo), [], ev.append, executor=FakeExec(), target=str(tmp_path / "mnt"), steps=steps)
    assert not e.run() and "outside the target" in ev[-1]["message"] and not (tmp_path / "etc").exists()


def test_progress_events_cover_every_step(zoneinfo, tmp_path):
    ok, ev, ex, tgt = run_engine(zoneinfo, tmp_path)
    steps = [e for e in ev if e["type"] == "step"]
    assert [s["i"] for s in steps] == list(range(1, steps[0]["n"] + 1))


# ---------------- preflight ----------------
def good_pre(zoneinfo, tmp_path, **over):
    live = tmp_path / "archiso"; live.mkdir(exist_ok=True)
    efi = tmp_path / "efi"; efi.mkdir(exist_ok=True)
    repo = tmp_path / "repo"; repo.mkdir(exist_ok=True); (repo / "chudos.db").write_text("x")
    keyr = tmp_path / "trustdb.gpg"; keyr.write_text("x")
    kw = dict(keyring=keyr, live_marker=live, efi=efi, geteuid=lambda: 0, which=lambda t: "/x", repo=repo,
              list_disks=lambda: [disks.Disk("/dev/sda", 100 * GIB)], run=lambda a: type("R", (), {"returncode": 0})())
    kw.update(over)
    return engine.preflight(settings_obj(zoneinfo), **kw)


def test_preflight_ok(zoneinfo, tmp_path):
    assert good_pre(zoneinfo, tmp_path) == []


@pytest.mark.parametrize("over,needle", [
    (dict(geteuid=lambda: 1000), "must run as root"),
    (dict(live_marker=Path("/nonexistent-live")), "not the ChudOS live medium"),
    (dict(efi=Path("/nonexistent-efi")), "UEFI"),
    (dict(list_disks=lambda: []), "was not found"),
    (dict(list_disks=lambda: [disks.Disk("/dev/sda", 100 * GIB, usable=False, reason="in use")]), "cannot be used: in use"),
    (dict(which=lambda t: None if t == "pacstrap" else "/x"), "Missing tools"),
    (dict(run=lambda a: type("R", (), {"returncode": 1})()), "No internet"),
])
def test_preflight_refusals(zoneinfo, tmp_path, over, needle):
    assert any(needle in e for e in good_pre(zoneinfo, tmp_path, **over))


def test_preflight_keyring_not_ready(zoneinfo, tmp_path):
    assert any("keyring" in e for e in good_pre(zoneinfo, tmp_path, keyring=tmp_path / "missing"))


def test_preflight_missing_repo(zoneinfo, tmp_path):
    assert any("bundled ChudOS package repository" in e for e in good_pre(zoneinfo, tmp_path, repo=tmp_path / "norepo"))


# ---------------- backend ----------------
def call_backend(tmp_path, zoneinfo, req, *args, pre=lambda s: [], engine_cls=None):
    pk = tmp_path / "pk.txt"; pk.write_text("base\nlinux\n")
    out = io.StringIO()
    rc = backend.main(["--packages", str(pk), *args], stdin=io.StringIO(json.dumps(req) if not isinstance(req, str) else req), out=out,
                      preflight=pre, engine_cls=engine_cls or engine.Engine, zoneinfo=zoneinfo, lock_path=tmp_path / "lock")
    return rc, out.getvalue()


def test_backend_requires_exact_disk_confirmation(tmp_path, zoneinfo):
    rc, out = call_backend(tmp_path, zoneinfo, {"settings": raw(), "confirm_erase": "/dev/sdb"})
    assert rc == 2 and "confirmation does not match" in out
    rc, out = call_backend(tmp_path, zoneinfo, {"settings": raw()})
    assert rc == 2
    assert "ERASES" not in out


def test_backend_rejects_bad_json_and_bad_settings(tmp_path, zoneinfo):
    assert call_backend(tmp_path, zoneinfo, "not json")[0] == 2
    rc, out = call_backend(tmp_path, zoneinfo, {"settings": raw(disk="/dev/sda1"), "confirm_erase": "/dev/sda1"})
    assert rc == 2 and "disk" in out


def test_backend_dry_run_prints_plan_without_running_or_password(tmp_path, zoneinfo):
    class Boom:
        def __init__(self, *a, **k): raise AssertionError("engine must not run in dry-run")
    rc, out = call_backend(tmp_path, zoneinfo, {"settings": raw(password="topsecret"), "confirm_erase": "/dev/sda"}, "--dry-run",
                           pre=lambda s: ["not live"], engine_cls=Boom)
    assert rc == 0 and "sgdisk --zap-all /dev/sda" in out and "topsecret" not in out and "preflight: not live" in out


def test_backend_stops_on_preflight_failure_and_does_not_start_engine(tmp_path, zoneinfo):
    class Boom:
        def __init__(self, *a, **k): raise AssertionError("engine must not run")
    rc, out = call_backend(tmp_path, zoneinfo, {"settings": raw(), "confirm_erase": "/dev/sda"}, pre=lambda s: ["No internet connection."], engine_cls=Boom)
    ev = json.loads(out.strip().splitlines()[-1])
    assert rc == 3 and ev["step"] == "preflight" and ev["disk_modified"] is False


def test_backend_runs_engine_with_events_as_json_lines(tmp_path, zoneinfo):
    class Fake:
        def __init__(self, s, packages, emit, steps=None): self.emit = emit; assert packages == ["base", "linux"]
        def run(self): self.emit({"type": "done"}); return True
    rc, out = call_backend(tmp_path, zoneinfo, {"settings": raw(), "confirm_erase": "/dev/sda"}, engine_cls=Fake)
    assert rc == 0 and json.loads(out.strip().splitlines()[-1]) == {"type": "done"}


def test_backend_refuses_second_concurrent_install(tmp_path, zoneinfo):
    import fcntl
    held = open(tmp_path / "lock", "w"); fcntl.flock(held, fcntl.LOCK_EX)
    rc, out = call_backend(tmp_path, zoneinfo, {"settings": raw(), "confirm_erase": "/dev/sda"})
    assert rc == 3 and "already running" in out
