"""Runs each PKGBUILD's package() into a scratch pkgdir (no makepkg needed) and checks the result.
Proves the install layout and launcher paths are self-consistent; does NOT prove makepkg/pacman accept the packages."""
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PKGS = sorted(p.name for p in (ROOT / "packaging").iterdir() if (p / "PKGBUILD").is_file())


def package_into(name, tmp_path):
    pkgdir = tmp_path / name
    pkgdir.mkdir()
    script = f'set -e; source PKGBUILD; startdir="{ROOT}/packaging/{name}"; pkgdir="{pkgdir}"; package; echo "$pkgver"'
    r = subprocess.run(["bash", "-c", script], cwd=ROOT / "packaging" / name, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return pkgdir


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pkgs")
    return {n: package_into(n, tmp) for n in PKGS}


def test_all_expected_packages_found():
    assert PKGS == ["chudos-control-center", "chudos-defaults", "chudos-installer", "chudos-monitor", "chudos-profiles", "chudos-store", "chudos-welcome"]


def test_no_package_installs_outside_usr_etc(built):
    for name, d in built.items():
        top = {p.name for p in d.iterdir()}
        assert top <= {"usr", "etc"}, (name, top)


def test_no_bytecode_or_tests_or_repo_files_leak(built):
    for name, d in built.items():
        for p in d.rglob("*"):
            assert "__pycache__" not in p.parts and not p.name.endswith(".pyc"), (name, p)
            assert ".git" not in p.parts and "tests" not in p.parts, (name, p)


def test_launchers_are_executable_and_use_fixed_python(built):
    for name, d in built.items():
        for f in (d / "usr/bin").glob("*") if (d / "usr/bin").exists() else []:
            assert f.stat().st_mode & stat.S_IXUSR, f
            text = f.read_text()
            assert text.startswith("#!/bin/sh") and "/usr/bin/python3 -m " in text and '"$@"' in text, f


def test_launcher_pythonpaths_exist_in_the_packages_that_provide_them(built):
    provided = set()
    for d in built.values():
        for p in (d / "usr/lib/chudos").glob("*") if (d / "usr/lib/chudos").exists() else []:
            provided.add("/usr/lib/chudos/" + p.name)
    for name, d in built.items():
        for f in (d / "usr/bin").glob("*") if (d / "usr/bin").exists() else []:
            m = re.search(r"PYTHONPATH=([^$\s]+)", f.read_text())
            for path in m.group(1).split(":"):
                assert path in provided, (f.name, path, provided)


def _import_all_script(paths, top):
    return (f"import sys, pkgutil, importlib; sys.path[:0]={paths!r}; pkg = importlib.import_module({top!r}); "
            "mods = [m.name for m in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + '.') if not m.name.endswith('__main__')]; "
            "[importlib.import_module(m) for m in mods]; print(len(mods))")


def test_every_module_imports_from_the_installed_tree(built):
    """Imports EVERY module of each launcher's package using only the paths its launcher sets (remapped to scratch pkgdirs)."""
    mapping = {}
    for d in built.values():
        for p in (d / "usr/lib/chudos").glob("*") if (d / "usr/lib/chudos").exists() else []:
            mapping["/usr/lib/chudos/" + p.name] = str(p)
    for name, d in built.items():
        for f in (d / "usr/bin").glob("*") if (d / "usr/bin").exists() else []:
            text = f.read_text()
            paths = [mapping[p] for p in re.search(r"PYTHONPATH=([^$\s]+)", text).group(1).split(":")]
            top = re.search(r"-m ([\w.]+)", text).group(1).split(".")[0]
            r = subprocess.run(["python3", "-I", "-c", _import_all_script(paths, top)], capture_output=True, text=True,
                               env={**os.environ, "HOME": str(d), "QT_QPA_PLATFORM": "offscreen"})
            assert r.returncode == 0, (f.name, top, r.stderr[-500:])


def test_the_import_check_really_fails_when_a_path_is_missing(built):
    d = built["chudos-control-center"]
    mapping = {"/usr/lib/chudos/" + p.name: str(p) for dd in built.values() if (dd / "usr/lib/chudos").exists() for p in (dd / "usr/lib/chudos").glob("*")}
    only_cc = [mapping["/usr/lib/chudos/control-center"]]          # drop monitor + profiles-engine
    r = subprocess.run(["python3", "-I", "-c", _import_all_script(only_cc, "chudos_control_center")], capture_output=True, text=True,
                       env={**os.environ, "HOME": str(d), "QT_QPA_PLATFORM": "offscreen"})
    assert r.returncode != 0 and "No module named" in r.stderr


def test_desktop_files_reference_installed_launchers(built):
    bins = {f.name for d in built.values() if (d / "usr/bin").exists() for f in (d / "usr/bin").glob("*")}
    for d in built.values():
        for df in list((d / "usr/share/applications").glob("*.desktop")) + list((d / "etc/xdg/autostart").glob("*.desktop")) if d.exists() else []:
            exe = re.search(r"^Exec=(\S+)", df.read_text(), flags=re.M).group(1)
            assert exe in bins or exe.startswith("/usr/lib/chudos/"), (df.name, exe)


def test_defaults_package_contents(built):
    d = built["chudos-defaults"]
    assert "0.1.0" in (d / "etc/chudos-release").read_text() and "@CHUDOS" not in (d / "etc/chudos-release").read_text()
    assert (d / "usr/share/wallpapers/ChudOSDefault/metadata.json").is_file()
    assert (d / "usr/share/icons/hicolor/scalable/apps/chudos.svg").is_file()
    assert os.access(d / "usr/lib/chudos/apply-defaults", os.X_OK)
    assert not any("sudoers" in str(p) or "sddm.conf.d" in str(p) or "install-chudos" in str(p) for p in d.rglob("*"))


def test_profiles_package_ships_builtins_and_sound(built):
    d = built["chudos-profiles"]
    assert sorted(p.stem for p in (d / "usr/share/chudos/profiles").glob("*.json")) == ["default", "gaming", "hyper", "lock-in", "zen"]
    assert (d / "usr/share/chudos/sounds/profile-applied.wav").is_file()


def test_installer_package_ships_window_backend_and_no_secrets(built):
    d = built["chudos-installer"]
    for b in ("chudos-installer", "chudos-install-backend"):
        assert (d / "usr/bin" / b).stat().st_mode & 0o111
    assert "chudos_installer.backend" in (d / "usr/bin/chudos-install-backend").read_text()
    assert (d / "usr/lib/chudos/installer/chudos_installer/engine.py").is_file()
    assert not list(d.rglob("install-packages.txt"))   # generated at ISO staging, from base+desktop only
