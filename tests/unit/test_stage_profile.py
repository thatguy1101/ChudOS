import pytest
import stage_profile as sp


def test_assemble_dedupes_and_strips_comments(tmp_path):
    (tmp_path / "base.txt").write_text("# c\nbase\nlinux  # kernel\n")
    (tmp_path / "desktop.txt").write_text("linux\nsddm\n")
    (tmp_path / "live-only.txt").write_text("\narchinstall\n")
    assert sp.assemble_packages(tmp_path) == ["base", "linux", "sddm", "archinstall"]


def test_stage_fills_placeholders(tmp_path):
    out = sp.stage("1.2.3", tmp_path / "repo", tmp_path / "profile")
    prof = (out / "profiledef.sh").read_text()
    assert 'iso_version="1.2.3"' in prof and "@CHUDOS" not in prof
    assert f"file://{tmp_path / 'repo'}" in (out / "pacman.conf").read_text()
    pk = (out / "packages.x86_64").read_text().split()
    assert {"chudos-welcome", "chudos-profiles", "archinstall"} <= set(pk)


def test_stage_preserves_symlinks(tmp_path):
    out = sp.stage("1.0", tmp_path / "r", tmp_path / "p")
    link = out / "airootfs/etc/systemd/system/display-manager.service"
    assert link.is_symlink()


@pytest.mark.parametrize("bad", ["", "1", "1.0; rm -rf /", "../x", "1.0 beta"])
def test_bad_versions_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        sp.stage(bad, tmp_path / "r", tmp_path / "p")


def test_relative_repo_path_rejected(tmp_path):
    with pytest.raises(ValueError):
        sp.stage("1.0", __import__("pathlib").Path("rel/repo"), tmp_path / "p")


def test_installed_defaults_have_no_live_only_files():
    import validate
    errs = []
    validate.check_separation(errs)
    assert errs == []


def _fake_repo(tmp_path):
    r = tmp_path / "repo"; r.mkdir()
    (r / "chudos.db.tar.gz").write_text("db"); (r / "chudos.files.tar.gz").write_text("files"); (r / "chudos-welcome-0.1.0-1-any.pkg.tar.zst").write_text("pkg")
    return r


def test_stage_bundles_repo_for_the_installer(tmp_path):
    out = sp.stage("1.0.0", _fake_repo(tmp_path), tmp_path / "p")
    b = out / "airootfs/opt/chudos-repo"
    assert (b / "chudos.db").read_text() == "db" and (b / "chudos.files").read_text() == "files" and (b / "chudos-welcome-0.1.0-1-any.pkg.tar.zst").is_file()


def test_installed_package_list_excludes_live_only_tools(tmp_path):
    out = sp.stage("1.0.0", _fake_repo(tmp_path), tmp_path / "p")
    pk = (out / "airootfs/usr/share/chudos/installer/install-packages.txt").read_text().split()
    assert {"base", "linux", "plasma-desktop", "sddm", "zram-generator", "chudos-welcome"} <= set(pk)
    assert not {"chudos-installer", "archinstall", "mkinitcpio-archiso", "arch-install-scripts"} & set(pk)
    assert len(pk) == len(set(pk))
    iso = (out / "packages.x86_64").read_text().split()
    assert "chudos-installer" in iso


def test_stage_without_built_repo_does_not_invent_one(tmp_path):
    out = sp.stage("1.0.0", tmp_path / "none", tmp_path / "p")
    assert not (out / "airootfs/opt/chudos-repo").exists()
