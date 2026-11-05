"""The validator must actually fail on bad input, not just pass on good input."""
import shutil
from pathlib import Path

import validate

SRC = Path(validate.ROOT) / "distro" / "archiso"


def copy(tmp_path):
    dst = tmp_path / "archiso"
    shutil.copytree(SRC, dst, symlinks=True)
    return dst


def test_real_repo_passes():
    assert validate.run() == []


def test_unknown_profiledef_variable_fails(tmp_path):
    b = copy(tmp_path)
    (b / "profiledef.sh").open("a").write('\nmade_up_option="x"\n')
    assert any("made_up_option" in e for e in validate.run(b))


def test_missing_required_variable_fails(tmp_path):
    b = copy(tmp_path)
    t = (b / "profiledef.sh").read_text().replace('install_dir="chudos"\n', "")
    (b / "profiledef.sh").write_text(t)
    assert any("install_dir" in e for e in validate.run(b))


def test_bad_bootmode_fails(tmp_path):
    b = copy(tmp_path)
    t = (b / "profiledef.sh").read_text().replace("uefi.systemd-boot", "uefi.magic")
    (b / "profiledef.sh").write_text(t)
    assert any("uefi.magic" in e for e in validate.run(b))


def test_file_permissions_for_missing_file_fails(tmp_path):
    b = copy(tmp_path)
    (b / "airootfs/etc/skel/Desktop/install-chudos.desktop").unlink()
    assert any("install-chudos.desktop" in e for e in validate.run(b))


def test_siglevel_never_fails(tmp_path):
    b = copy(tmp_path)
    t = (b / "pacman.conf").read_text().replace("SigLevel    = Required DatabaseOptional", "SigLevel = Never")
    (b / "pacman.conf").write_text(t)
    assert any("Never" in e for e in validate.run(b))


def test_extra_remote_repo_fails(tmp_path):
    b = copy(tmp_path)
    (b / "pacman.conf").open("a").write("\n[evil]\nServer = https://evil.example/$repo\n")
    errs = validate.run(b)
    assert any("sections" in e for e in errs) and any("non-local" in e for e in errs)


def test_symlink_to_unexpected_target_fails(tmp_path):
    b = copy(tmp_path)
    (b / "airootfs/etc/systemd/system/bad.service").symlink_to("/etc/passwd")
    assert any("bad.service" in e for e in validate.run(b))


def test_package_name_validation(tmp_path, monkeypatch):
    lists = tmp_path / "distro" / "packages"
    shutil.copytree(Path(validate.ROOT) / "distro" / "packages", lists)
    (lists / "base.txt").open("a").write("Bad Name\nbase\n")
    monkeypatch.setattr(validate, "ROOT", tmp_path)
    errs = []
    validate.check_packages(errs)
    assert any("Bad Name" in e for e in errs) and any("duplicates" in e for e in errs)
