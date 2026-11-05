#!/usr/bin/env bash
# Build the ChudOS ISO inside an Arch Linux container. Works on any Linux host with Docker (or Podman: DOCKER=podman).
# Usage:  ./tools/build-iso/docker-build.sh        ->  out/chudos-*.iso
# Needs --privileged: mkarchiso mounts and loop devices. The container only touches ./build and ./out.
# UNTESTED: written without access to Docker or Arch. Send me the first error.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKER="${DOCKER:-docker}"
command -v "${DOCKER}" >/dev/null || { echo "need ${DOCKER} installed" >&2; exit 1; }
mkdir -p "${ROOT}/build" "${ROOT}/out"
# shellcheck disable=SC2016  # the single-quoted script is meant to expand inside the container
"${DOCKER}" run --rm --privileged -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" -v "${ROOT}":/work archlinux:latest bash -euo pipefail -c '
  pacman -Syu --noconfirm --needed archiso base-devel git python sudo shellcheck
  id builder >/dev/null 2>&1 || useradd -m builder
  chown -R builder /work/build
  su builder -c "cd /work && git config --global --add safe.directory /work && ./tools/build-iso/build.sh packages"
  cd /work && ./tools/build-iso/build.sh iso
  chown -R "${HOST_UID}:${HOST_GID}" /work/build /work/out
'
echo "Done. ISO is in ${ROOT}/out/"
ls -lh "${ROOT}/out/"
