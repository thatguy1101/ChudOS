#!/usr/bin/env bash
# shellcheck disable=SC2034
#
# ChudOS Archiso profile definition.
# Derived from the upstream Archiso "releng" profile (same variable names and
# formats); only variables that upstream releng uses are set here.
#
# @CHUDOS_VERSION@ is replaced by tools/build-iso/stage_profile.py at build time.

iso_name="chudos"
iso_label="CHUDOS_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="ChudOS Project"
iso_application="ChudOS Live/Install Medium"
iso_version="@CHUDOS_VERSION@"
install_dir="chudos"
bootmodes=('uefi.systemd-boot')
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86,arm64' '-b' '1M' '-Xdict-size' '1M')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical' '--long' '-19')
file_permissions=(
  ["/etc/sudoers.d/10-chudos-live"]="0:0:440"
  ["/etc/skel/Desktop/install-chudos.desktop"]="0:0:755"
)
