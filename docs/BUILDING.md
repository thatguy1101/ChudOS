# Building the ISO

**Status: this procedure has NOT been executed.** The authoring environment was Ubuntu 24.04 with no
pacman, archiso, QEMU or KVM. Treat the steps as untested until TESTING.md says otherwise.

## Requirements
Arch Linux host or container (privileged; mkarchiso mounts loop devices), ~15 GB free disk, network
to Arch mirrors. `sudo pacman -S archiso base-devel git python`.
(`pyside6` is only needed to regenerate the wallpaper or run the GUI test.)

## Steps
```
git clone <repo> chudos && cd chudos
tools/build-iso/build.sh check            # prerequisites
tools/build-iso/build.sh packages         # as a NORMAL user: builds chudos-* into build/repo
sudo tools/build-iso/build.sh iso --version 0.1.0
```
`iso` validates, stages `build/profile`, runs `mkarchiso`, writes `out/*.sha256` and `out/BUILDINFO`.
`makepkg --nodeps` is used for the two local packages because their dependencies come from the Arch
repos at ISO build time; building them still needs `base-devel`.

## Verify the output
```
cd out && sha256sum -c chudos-*.iso.sha256
```
## Boot test (QEMU, UEFI)
```
cp /usr/share/edk2/x64/OVMF_VARS.4m.fd /tmp/vars.fd     # path may differ by edk2 version
qemu-system-x86_64 -enable-kvm -m 4G -smp 2 -cdrom out/chudos-*.iso \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd \
  -drive if=pflash,format=raw,file=/tmp/vars.fd -vga virtio
```
Use a throwaway disk image for install tests (`qemu-img create -f qcow2 test.qcow2 30G`); never point
QEMU at a real disk.

## Likely failure points (unverified)
Package name not found (a package was renamed), `[chudos]` repo path wrong, mkarchiso rejecting a
profile option. See TROUBLESHOOTING.md.

## One-command build with Docker (any Linux host)
`./tools/build-iso/docker-build.sh` (or `DOCKER=podman ...`) builds the packages and the ISO inside an `archlinux` container. Output: `out/chudos-*.iso` + `.sha256`.
Untested. Use a native Arch host if the container build fails on mounts/loop devices.

## Trying the ISO
- **VM (recommended first):** VirtualBox/VMware with **EFI enabled**, 4 GB RAM, 30 GB disk. Or QEMU: `qemu-img create -f qcow2 test.qcow2 30G`, then
  `qemu-system-x86_64 -enable-kvm -m 4G -bios /usr/share/edk2/x64/OVMF.4m.fd -cdrom out/chudos-*.iso -drive file=test.qcow2,if=virtio`.
- **Real PC:** write the ISO to a USB stick with Ventoy, Rufus (DD mode) or balenaEtcher, boot it in UEFI mode, install to an empty disk. The installer ERASES the disk you pick.
