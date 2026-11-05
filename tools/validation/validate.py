#!/usr/bin/env python3
"""Static validation of the ChudOS repository. Runs on any host (no Arch tools needed).

Checks (each failure is reported; exit status 1 if any fail):
  - profiledef.sh defines the variables mkarchiso requires, and only known ones
  - pacman.conf has the expected repos and a safe SigLevel for upstream repos
  - package lists parse, have no duplicates across lists, and contain no obviously bad names
  - every package the Archiso profile installs from the [chudos] repo has a PKGBUILD
  - live-only files are not shipped in the installed-system defaults
  - systemd enable symlinks in airootfs are relative-safe (point under /usr/lib/systemd/system)
  - desktop files have the keys the freedesktop spec requires
  - wallpaper package metadata is valid JSON and referenced images exist
This validates structure only. It does not prove that a package exists in Arch.
"""
from __future__ import annotations

import configparser
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_PROFILEDEF = {
    "iso_name", "iso_label", "iso_publisher", "iso_application", "iso_version",
    "install_dir", "bootmodes", "pacman_conf", "airootfs_image_type", "file_permissions",
}
KNOWN_PROFILEDEF = REQUIRED_PROFILEDEF | {
    "buildmodes", "arch", "airootfs_image_tool_options", "bootstrap_tarball_compression",
    "bootstrap_tarball_compression", "kernel_params_aarch64",
}
VALID_BOOTMODES = {
    "bios.syslinux", "uefi.systemd-boot", "uefi.grub", "bios.grub", "uefi-ia32.systemd-boot",
    "uefi-x64.systemd-boot", "bios.syslinux.mbr", "bios.syslinux.eltorito",
    "uefi-ia32.grub.esp", "uefi-x64.grub.esp", "uefi-ia32.grub.eltorito", "uefi-x64.grub.eltorito",
}
PKG_NAME_RE = re.compile(r"^[a-z0-9@._+-]+$")
LOCAL_PACKAGES = {"chudos-defaults", "chudos-welcome", "chudos-profiles",
                  "chudos-monitor", "chudos-control-center", "chudos-store"}
LIVE_ONLY_PACKAGES = {"chudos-installer"}  # on the live medium only, never installed
# Files that must exist only in the live overlay, never in installed-system defaults.
LIVE_ONLY_MARKERS = ("sudoers.d", "sddm.conf.d", "install-chudos.desktop", "getty@", "live-autologin")


def err(errors: list[str], msg: str) -> None:
    errors.append(msg)


def check_profiledef(errors: list[str], base: Path) -> None:
    f = base / "profiledef.sh"
    if not f.is_file():
        return err(errors, "profiledef.sh missing")
    text = f.read_text(encoding="utf-8")
    assigned = set(re.findall(r"^([a-z_]+)=", text, flags=re.M))
    for var in sorted(REQUIRED_PROFILEDEF - assigned):
        err(errors, f"profiledef.sh: required variable {var} not set")
    for var in sorted(assigned - KNOWN_PROFILEDEF):
        err(errors, f"profiledef.sh: unknown variable {var} (not a documented Archiso option)")
    m = re.search(r"^bootmodes=\(([^)]*)\)", text, flags=re.M)
    if m:
        for mode in re.findall(r"'([^']+)'", m.group(1)):
            if mode not in VALID_BOOTMODES:
                err(errors, f"profiledef.sh: unknown bootmode {mode!r}")
    # every file_permissions path that is meant to be in the overlay must exist there
    for path in re.findall(r'\["(/[^"]+)"\]=', text):
        if not (base / "airootfs" / path.lstrip("/")).exists():
            err(errors, f"profiledef.sh: file_permissions entry {path} has no file in airootfs")


def check_pacman_conf(errors: list[str], base: Path) -> None:
    f = base / "pacman.conf"
    if not f.is_file():
        return err(errors, "pacman.conf missing")
    text = f.read_text(encoding="utf-8")
    sections = re.findall(r"^\[([^\]]+)\]", text, flags=re.M)
    if sections != ["options", "core", "extra", "chudos"]:
        err(errors, f"pacman.conf: unexpected sections {sections}")
    # The only SigLevel loosening allowed is the local [chudos] repo.
    in_chudos = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            in_chudos = s == "[chudos]"
        if s.startswith("SigLevel") and "Never" in s:
            err(errors, "pacman.conf: SigLevel Never is not allowed")
        if s.startswith("SigLevel") and "TrustAll" in s and not in_chudos:
            err(errors, "pacman.conf: TrustAll only allowed in [chudos]")
    if re.search(r"^Server\s*=\s*https?://", text, flags=re.M):
        err(errors, "pacman.conf: non-local Server= entry found; extra repositories are not allowed")


def read_list(path: Path) -> list[str]:
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def check_packages(errors: list[str]) -> None:
    seen: dict[str, str] = {}
    for name in ("base.txt", "desktop.txt", "live-only.txt"):
        f = ROOT / "distro" / "packages" / name
        if not f.is_file():
            err(errors, f"package list {name} missing")
            continue
        for pkg in read_list(f):
            if not PKG_NAME_RE.match(pkg):
                err(errors, f"{name}: invalid package name {pkg!r}")
            if pkg in seen:
                err(errors, f"{name}: {pkg} duplicates entry in {seen[pkg]}")
            seen[pkg] = name
    for name in ("optional-developer.txt", "optional-gaming.txt"):
        f = ROOT / "distro" / "packages" / name
        if not f.is_file():
            err(errors, f"optional package list {name} missing")
            continue
        opt = read_list(f)
        for pkg in opt:
            if not PKG_NAME_RE.match(pkg):
                err(errors, f"{name}: invalid package name {pkg!r}")
            if pkg in seen:
                err(errors, f"{name}: {pkg} is already in the ISO list {seen[pkg]} (optional lists must not overlap)")
        if len(opt) != len(set(opt)):
            err(errors, f"{name}: duplicate entries")
    for pkg in LOCAL_PACKAGES:
        if pkg not in seen:
            err(errors, f"local package {pkg} is not in any package list")
        if not (ROOT / "packaging" / pkg / "PKGBUILD").is_file():
            err(errors, f"local package {pkg} has no PKGBUILD")
    for pkg in LIVE_ONLY_PACKAGES:
        if pkg in seen and seen[pkg] != "live-only.txt":
            err(errors, f"{pkg} must be only in live-only.txt, found in {seen[pkg]}")
        if pkg not in seen:
            err(errors, f"live-only package {pkg} is not in live-only.txt")
        if not (ROOT / "packaging" / pkg / "PKGBUILD").is_file():
            err(errors, f"live-only package {pkg} has no PKGBUILD")
    for pkg in ("zram-generator", "linux", "base", "sddm", "plasma-desktop", "mkinitcpio-archiso"):
        if pkg not in seen:
            err(errors, f"essential package {pkg} missing from package lists")


def check_separation(errors: list[str]) -> None:
    defaults = ROOT / "system" / "defaults"
    for p in defaults.rglob("*"):
        rel = str(p.relative_to(defaults))
        if any(marker in rel for marker in LIVE_ONLY_MARKERS):
            err(errors, f"live-only file in installed defaults: {rel}")
    if not (ROOT / "distro/archiso/airootfs/etc/sudoers.d/10-chudos-live").is_file():
        err(errors, "live sudoers file missing from live overlay")
    mirrors = ROOT / "distro/archiso/airootfs/etc/pacman.d/mirrorlist"
    if not mirrors.is_file() or not re.search(r"^Server\s*=\s*https://", mirrors.read_text(encoding="utf-8"), flags=re.M):
        err(errors, "live overlay needs etc/pacman.d/mirrorlist with an https Server (the installer downloads through it)")
    for n in (3, 4, 5, 6):
        if not (ROOT / f"distro/archiso/airootfs/etc/systemd/system/getty@tty{n}.service.d/live-autologin.conf").is_file():
            err(errors, f"live terminal autologin drop-in for tty{n} missing")
    sysd = ROOT / "distro/archiso/airootfs/etc/systemd/system"
    for rel in ("default.target", "display-manager.service", "multi-user.target.wants/NetworkManager.service",
                "multi-user.target.wants/chudos-pacman-init.service", "sysinit.target.wants/systemd-timesyncd.service"):
        if not (sysd / rel).is_symlink():
            err(errors, f"airootfs/etc/systemd/system/{rel} must be a symlink (an archive tool may have turned it into a copy; use tar or zip -y)")
    desk = ROOT / "distro/archiso/airootfs/etc/skel/Desktop/install-chudos.desktop"
    if not desk.is_file() or not desk.stat().st_mode & 0o100:
        err(errors, "live desktop installer shortcut missing or not executable")


def check_symlinks(errors: list[str], base: Path) -> None:
    for p in (base / "airootfs").rglob("*"):
        if p.is_symlink():
            target = str(p.readlink())
            if not target.startswith("/usr/lib/systemd/system/"):
                err(errors, f"airootfs symlink {p.relative_to(base)} -> {target} (unexpected target)")


def check_desktop_files(errors: list[str]) -> None:
    for p in ROOT.rglob("*.desktop"):
        if ".git" in p.parts:
            continue
        cp = configparser.ConfigParser(interpolation=None, strict=True)
        cp.optionxform = str
        try:
            cp.read(p, encoding="utf-8")
            entry = cp["Desktop Entry"]
        except (configparser.Error, KeyError) as exc:
            err(errors, f"{p.relative_to(ROOT)}: unparseable ({exc})")
            continue
        for key in ("Type", "Name", "Exec"):
            if key not in entry:
                err(errors, f"{p.relative_to(ROOT)}: missing {key}")


def check_wallpaper(errors: list[str]) -> None:
    pkg = ROOT / "branding" / "wallpapers" / "ChudOSDefault"
    try:
        meta = json.loads((pkg / "metadata.json").read_text(encoding="utf-8"))
        if meta["KPlugin"]["Id"] != "ChudOSDefault":
            err(errors, "wallpaper metadata Id mismatch")
    except (OSError, ValueError, KeyError) as exc:
        err(errors, f"wallpaper metadata invalid: {exc}")
    if not list((pkg / "contents" / "images").glob("*.png")):
        err(errors, "wallpaper has no images")


def run(base: Path | None = None) -> list[str]:
    base = base or ROOT / "distro" / "archiso"
    errors: list[str] = []
    check_profiledef(errors, base)
    check_pacman_conf(errors, base)
    check_packages(errors)
    check_separation(errors)
    check_symlinks(errors, base)
    check_desktop_files(errors)
    check_wallpaper(errors)
    return errors


def main() -> int:
    errors = run()
    for e in errors:
        print(f"FAIL: {e}", file=sys.stderr)
    if errors:
        print(f"{len(errors)} validation error(s)", file=sys.stderr)
        return 1
    print("validation OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
