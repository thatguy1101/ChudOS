#!/usr/bin/env bash
# ChudOS build driver.  Usage: build.sh {check|packages|stage|iso} [--version X.Y.Z]
#
# Real ISO builds need an Arch Linux host (or Arch container) with archiso,
# and root for mkarchiso. Nothing here touches disks other than build/ and out/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="${ROOT}/build"
OUT="${ROOT}/out"
VERSION="$(date +%Y.%m.%d)"

die() { echo "build.sh: $*" >&2; exit 1; }

cmd="${1:-}"; shift || true
while [ $# -gt 0 ]; do
    case "$1" in
        --version) VERSION="${2:?--version needs a value}"; shift 2 ;;
        *) die "unknown option: $1" ;;
    esac
done

check_prereqs() {
    local missing=0
    [ -f /etc/arch-release ] || { echo "FAIL: host is not Arch Linux (/etc/arch-release missing)"; missing=1; }
    for t in mkarchiso makepkg repo-add sha256sum python3; do
        command -v "$t" >/dev/null 2>&1 || { echo "FAIL: missing tool: $t"; missing=1; }
    done
    [ "$missing" -eq 0 ] && echo "OK: build prerequisites present"
    return "$missing"
}

build_packages() {
    command -v makepkg >/dev/null 2>&1 || die "makepkg not found (Arch host required)"
    [ "$(id -u)" -ne 0 ] || die "makepkg refuses to run as root; run build.sh packages as a normal user"
    mkdir -p "${BUILD}/repo"
    for pkg in chudos-defaults chudos-welcome chudos-profiles chudos-monitor chudos-control-center chudos-store chudos-installer; do
        ( cd "${ROOT}/packaging/${pkg}" && PKGDEST="${BUILD}/repo" makepkg --force --nodeps --noconfirm )
    done
    # --nodeps: pyside6/plasma-* are resolved later, from Arch repos, by mkarchiso.
    repo-add "${BUILD}/repo/chudos.db.tar.gz" "${BUILD}"/repo/*.pkg.tar.* >/dev/null
    echo "local repo ready: ${BUILD}/repo"
}

stage() {
    python3 "${ROOT}/tools/validation/validate.py" || die "validation failed; not staging"
    python3 "${ROOT}/tools/build-iso/stage_profile.py" --version "${VERSION}" \
        --repo "${BUILD}/repo" --out "${BUILD}/profile"
}

build_iso() {
    check_prereqs || die "prerequisites not met"
    [ "$(id -u)" -eq 0 ] || die "mkarchiso needs root: run 'sudo $0 iso' (packages must be built first, as a normal user)"
    [ -f "${BUILD}/repo/chudos.db.tar.gz" ] || die "local repo missing: run '$0 packages' first"
    stage
    mkdir -p "${OUT}"
    mkarchiso -v -w "${BUILD}/work" -o "${OUT}" "${BUILD}/profile"
    local iso
    iso="$(find "${OUT}" -maxdepth 1 -name 'chudos-*.iso' -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)"
    [ -n "${iso}" ] || die "mkarchiso finished but no ISO found in ${OUT}"
    ( cd "${OUT}" && sha256sum "$(basename "${iso}")" > "$(basename "${iso}").sha256" )
    {
        echo "iso=$(basename "${iso}")"
        echo "version=${VERSION}"
        echo "built_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "host=$(uname -srm)"
        echo "archiso=$(pacman -Q archiso 2>/dev/null || echo unknown)"
        echo "git_commit=$(git -C "${ROOT}" rev-parse --short HEAD 2>/dev/null || echo none)"
    } > "${OUT}/BUILDINFO"
    echo "ISO: ${iso}"; cat "${iso}.sha256"
    echo "NOTE: built is not boot-tested. See docs/TESTING.md."
}

case "${cmd}" in
    check)    check_prereqs ;;
    packages) build_packages ;;
    stage)    stage ;;
    iso)      build_iso ;;
    *)        die "usage: build.sh {check|packages|stage|iso} [--version X.Y.Z]" ;;
esac
