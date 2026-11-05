# Installation

**Status: written but untested.** No ISO has been built or booted, and the installer has only run against fakes.

## Requirements
- UEFI computer (in a VM, enable EFI / OVMF). BIOS is not supported.
- Internet connection (Arch packages are downloaded during install).
- A whole disk of at least 20 GiB that you are happy to ERASE. Dual-boot and keeping data are not supported yet.

## Steps
1. Write the ISO to a USB stick or attach it to a VM, and boot it. The live session logs in automatically as `chud`.
2. Connect to the network with the panel's network icon (wait a minute after boot for the package keyring).
3. Double-click **Install ChudOS** on the desktop (or run `chudos-installer`).
4. Pick the disk (nothing is preselected), your name, password, time zone, language and keyboard.
5. On the last page, type the disk name exactly (for example `/dev/sda`) to enable **Erase and install**.
6. When it finishes, remove the USB/ISO and restart.

## Terminal access
Like the Arch ISO: press **Ctrl+Alt+F3** (F3 to F6) for a text console already logged in as `chud` (passwordless sudo, live only).
Ctrl+Alt+F1 or F2 returns to the desktop. Which of F1/F2 is the desktop is untested. `sudo archinstall` is available as a text-mode fallback.

## What the installer does
GPT disk with a 1 GiB EFI partition (`/boot`) and an ext4 root, systemd-boot, zram swap, a locked root account and your user in `wheel` with sudo,
NetworkManager and SDDM enabled. Your password goes to the backend over stdin only. Preview the exact steps without changing anything:
`chudos-install-backend --dry-run < request.json`.

## Known limitations
- The installed system's pacman.conf does not include `[chudos]`: ChudOS packages are not updated until a public signed repo exists.
- Secure Boot, disk encryption, snapshots, BIOS boot: not supported.
- NVIDIA drivers are not in the image (Intel/AMD Vulkan only).
