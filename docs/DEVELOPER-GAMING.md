# Developer and gaming support

Nothing here was tested on real hardware or a real Arch install. Package existence was checked on archlinux.org
(2026-11-03): gcc/make are standard base-devel tools; verified pages: jdk-openjdk (Java 27 at the time), jre17-openjdk,
rustup, podman, steam (**multilib**), prismlauncher, gamemode, mangohud, nvidia-open, nvidia-utils, vulkan-radeon, vulkan-intel.

## Tiers (developer)
| Tier | Tools | Where |
|---|---|---|
| Essential (in the ISO) | git, openssh, python, konsole, kate, nano | `distro/packages/*.txt` |
| Recommended | gcc, make, cmake, gdb, nodejs, npm, jdk-openjdk, python-pip | `optional-developer.txt`, Control Centre shows what is missing + the `pacman -S` line |
| Optional | rustup, podman, neovim | same |
Large toolchains are not in the ISO on purpose. TypeScript is installed per project with npm. Podman is preferred over Docker
(rootless, no daemon); Docker is not offered.

## Control Centre integrations
Developer page: tool status, install line (text only), `~/Projects` folder and a terminal opened there, Git name/email
(validated; **no passwords or tokens**), Arch Wiki link. Welcome and Control Centre launch fixed programs only.

## Gaming
- **GPU drivers:** the ISO ships Mesa with Vulkan for AMD (`vulkan-radeon`) and Intel (`vulkan-intel`). NVIDIA is **not** included:
  install `nvidia-open` + `nvidia-utils` yourself (pairs with the stock `linux` kernel; a different kernel needs a matching or DKMS package).
  Always check the Arch Wiki for your GPU generation first.
- **Steam / Proton:** `steam` is in the `multilib` repository. ChudOS does not enable multilib or any repository silently:
  you enable it yourself in `/etc/pacman.conf`, then do a full update (`sudo pacman -Syu`), then install. Proton is installed from inside Steam.
  Steam is proprietary software.
- **Minecraft Java:** no game assets or launcher accounts are bundled. `prismlauncher` is an option (verified in `extra` on 2026-11-03).
  **Java version matters:** each Minecraft version needs a specific Java version. The newest `jdk-openjdk` is not always the right one.
  Install the needed `jreNN-openjdk` and switch with `archlinux-java`. Modpack compatibility on Linux is not guaranteed.
- **GameMode / MangoHud:** optional, detected by the Control Centre. ChudOS has **not measured** whether they or the Gaming profile improve
  performance, and makes no such claim.
- **Gaming profile:** turns off animations and blur and lowers decorative sound volume (the settings that exist today). Notification
  behaviour is not controlled yet.

## Not done
No in-app GPU/driver detection, no automatic driver installation, no launcher integration beyond starting Steam/Prism if installed,
no performance measurements, no controller support work.
