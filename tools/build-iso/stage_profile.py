#!/usr/bin/env python3
"""Stage the Archiso profile: copy distro/archiso, fill placeholders, assemble the package list.

Pure file operations, no Arch tools needed, so it runs (and is tested) anywhere.
Usage: stage_profile.py --version 0.1.0 --repo /abs/path/to/repo --out build/profile
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_LISTS = ("base.txt", "desktop.txt", "live-only.txt")
VERSION_RE = re.compile(r"^[0-9]+(\.[0-9]+){1,3}([._-][A-Za-z0-9]+)?$")
TEXT_FILES = ("profiledef.sh", "pacman.conf")


def read_package_list(path: Path) -> list[str]:
    pkgs = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            pkgs.append(line)
    return pkgs


def assemble_packages(lists_dir: Path) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for name in PACKAGE_LISTS:
        for pkg in read_package_list(lists_dir / name):
            if pkg not in seen:
                seen.add(pkg)
                ordered.append(pkg)
    return ordered


INSTALLED_LISTS = ("base.txt", "desktop.txt")  # what the installer pacstraps: never live-only tools


def stage(version: str, local_repo: Path, out: Path, source: Path = REPO_ROOT) -> Path:
    if not VERSION_RE.match(version):
        raise ValueError(f"invalid version {version!r}")
    if not local_repo.is_absolute():
        raise ValueError("local repo path must be absolute")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(source / "distro" / "archiso", out, symlinks=True)
    for name in TEXT_FILES:
        f = out / name
        text = f.read_text(encoding="utf-8")
        text = text.replace("@CHUDOS_VERSION@", version).replace("@CHUDOS_REPO@", str(local_repo))
        f.write_text(text, encoding="utf-8")
    # The installer needs the ChudOS packages offline: ship the built repo inside the image.
    if (local_repo / "chudos.db.tar.gz").is_file():
        bundled = out / "airootfs" / "opt" / "chudos-repo"
        shutil.copytree(local_repo, bundled, symlinks=False)
        # pacman reads "chudos.db"; repo-add makes it a symlink, which a plain copy would not preserve.
        for suffix in ("db", "files"):
            src = local_repo / f"chudos.{suffix}.tar.gz"
            if src.is_file():
                (bundled / f"chudos.{suffix}").write_bytes(src.read_bytes())
    seen: set[str] = set()
    installed = [p for n in INSTALLED_LISTS for p in read_package_list(source / "distro" / "packages" / n) if not (p in seen or seen.add(p))]
    target = out / "airootfs" / "usr" / "share" / "chudos" / "installer"
    target.mkdir(parents=True, exist_ok=True)
    (target / "install-packages.txt").write_text("\n".join(installed) + "\n", encoding="utf-8")
    packages = assemble_packages(source / "distro" / "packages")
    (out / "packages.x86_64").write_text("\n".join(packages) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--repo", required=True, type=Path, help="absolute path of the local [chudos] pacman repo")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    try:
        out = stage(a.version, a.repo, a.out)
    except (ValueError, OSError) as exc:
        print(f"stage_profile: {exc}", file=sys.stderr)
        return 1
    print(f"staged profile at {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
