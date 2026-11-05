<div align="center">

# ChudOS

### Your system. Your workflow. Your experience.

**A custom Arch Linux distribution built for developers, designed for customisation, and ready for play.**

[![Based on Arch Linux](https://img.shields.io/badge/Based%20on-Arch%20Linux-1793D1?style=for-the-badge&logo=archlinux&logoColor=white)](https://archlinux.org/)
[![Desktop Environment](https://img.shields.io/badge/Desktop-KDE%20Plasma-1D99F3?style=for-the-badge&logo=kde&logoColor=white)](https://kde.org/plasma-desktop/)
[![Status](https://img.shields.io/badge/Status-Early%20Development-orange?style=for-the-badge)](#project-status)

---

</div>

## About

**ChudOS** is an Arch Linux-based distribution designed to deliver a polished, developer-focused desktop without sacrificing customisation, performance, or everyday usability.

Built on the flexibility of Arch Linux and the power of KDE Plasma, ChudOS combines a premium desktop experience with practical development tools, gaming support, and a collection of purpose-built system applications.

Its defining feature is **Dopamine Profiles**: configurable desktop experiences that change the look, feel, sounds, animations, and behaviour of the system to suit your workflow.

## Project Status

**ChudOS is in early development. The code for a bootable, installable image is written, but no ISO has been boot-tested yet.**

| Area | State |
|---|---|
| Live ISO profile (Archiso, UEFI, KDE Plasma, auto-login) | Written. Package builds verified on Arch. **ISO build and boot not yet verified.** |
| Graphical installer | Written and unit-tested against fakes. **Never run on a real disk or VM.** |
| ChudOS apps (Welcome, Profiles, Control Centre, Monitor, Store) | Written and unit-tested. Effects on a real Plasma session and a real pacman are **unverified**. |
| Licence, public package repository, Secure Boot, encryption | Not done |

Nothing in this README should be treated as working until it has been tested on real hardware or a VM. See [docs/TESTING.md](docs/TESTING.md) for exactly what is and is not verified.

## Features

### Installer

A simple graphical installer on the live image (double-click **Install ChudOS**), in place of Arch's text installer:

- Step-by-step wizard: disk, name and password, time zone, language and keyboard.
- Whole-disk erase only (UEFI, GPT, 1 GiB EFI partition + ext4, systemd-boot, zram swap). No dual-boot yet.
- Nothing is preselected, and you must type the disk name to confirm the erase.
- The window runs as a normal user. A separate root-only backend re-checks everything and refuses to run outside the live medium.
- Like the Arch ISO, **Ctrl+Alt+F3 to F6** open a terminal; Ctrl+Alt+F1/F2 returns to the desktop.
- ChudOS packages are bundled in the ISO and installed offline. Arch packages are downloaded, so an internet connection is required.

### Dopamine Profiles

Profiles change real KDE settings, not just themes. Built-in profiles:

| Profile | Description |
|---|---|
| **Default** | A polished, balanced desktop for everyday use. |
| **Hyper** | More expressive animations, vibrant colours, and sound cues. |
| **Lock In** | A distraction-minimised environment for focused development. |
| **Gaming** | Convenient access to gaming tools and settings. |
| **Zen** | A calmer desktop with restrained visuals and minimal sounds. |

You can also create custom profiles, import and export them, and a failed apply is rolled back.

### Custom System Applications

| Application | Purpose |
|---|---|
| **ChudOS Welcome** | First-run shortcuts. Also offers "Install ChudOS" on the live image. |
| **ChudOS Control Centre** | Overview, appearance, profiles, sound, developer, gaming and system pages, with real CPU/RAM/disk/update data. |
| **ChudOS Profiles** | Create, manage and switch profiles (GUI and `chudos-profile` CLI). |
| **ChudOS Monitor** | CPU, memory, storage and network. GPU is shown as unavailable rather than faked. |
| **ChudOS Store** | Search, install and remove packages through pacman, with `pkexec` for privileged steps. Never runs as root. |

### Developer and Gaming Support

Optional package sets (installed on request, not forced on everyone):

- **Developer:** gcc, make, cmake, gdb, Node.js, Python, Rust (rustup), Java, Podman, Neovim.
- **Gaming:** Steam, GameMode, MangoHud, Prism Launcher (Minecraft), Java runtimes, Vulkan tools, NVIDIA drivers.

ChudOS is not a maximum-performance AAA gaming distribution; gaming complements its focus on development and desktop usability.

## Building and Trying It

You need an Arch Linux machine (or the Docker script below).

```
sudo pacman -S --needed archiso base-devel git python
./tools/build-iso/build.sh check
./tools/build-iso/build.sh packages        # normal user, not root
sudo ./tools/build-iso/build.sh iso        # output: out/chudos-<date>.iso
```

On any Linux host with Docker: `./tools/build-iso/docker-build.sh` (untested).

Try it in a VM first (EFI enabled, 4 GB RAM, 30 GB disk). Only flash a USB stick for a real PC after a VM install works, because the installer **erases the whole disk you pick**. Details: [docs/BUILDING.md](docs/BUILDING.md) and [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Technology Stack

| Component | Technology |
|---|---|
| Base distribution | Arch Linux |
| Desktop environment | KDE Plasma (Wayland session, XWayland compatibility) |
| Installation image | Archiso (UEFI, systemd-boot) |
| Installer | Python + PySide6, following the Arch installation guide |
| Package management | pacman |
| GUI development | Python and PySide6 |
| System integration | KDE interfaces, systemd, standard Linux tools |

ChudOS builds on existing Linux technologies rather than reinventing them: no custom kernel, no custom package manager.

## Known Limitations

- Installed systems do not receive updates to the ChudOS packages until a public, signed repository exists.
- UEFI only. No BIOS boot, dual-boot, disk encryption, Secure Boot or snapshots.
- No NVIDIA drivers in the live image (Intel/AMD graphics only).
- Boot splash and SDDM theming are not done.

## Development

Checks that run on any machine:

```
python3 tools/validation/validate.py
python3 -m pytest -q tests
shellcheck tools/build-iso/build.sh tools/build-iso/docker-build.sh system/defaults/usr/lib/chudos/apply-defaults
```

Docs: [Architecture](docs/ARCHITECTURE.md) · [Decisions](docs/DECISIONS.md) · [Testing](docs/TESTING.md) · [Roadmap](docs/ROADMAP.md) · [Troubleshooting](docs/TROUBLESHOOTING.md) · [Developer & gaming](docs/DEVELOPER-GAMING.md) · [Release status](docs/RELEASE-CANDIDATE.md)

## Development Philosophy

- **Functionality first:** real, working features over superficial demonstrations.
- **Honest status:** a feature is not "working" until it has been tested.
- **Safe by default:** graphical apps never run as root; destructive actions need explicit confirmation.
- **Built on Linux:** reuse reliable existing technologies.
- **Personal by design:** let users shape their desktop around their preferences.

## Contributing

Bug reports and feedback are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## Disclaimer

ChudOS is an independent project based on Arch Linux. It is not an official Arch Linux or KDE project. Arch Linux, KDE Plasma, and other referenced technologies remain the property of their respective owners.

## License

Not chosen yet. Package metadata currently says GPL-3.0-or-later as a placeholder.

---

<div align="center">

**ChudOS: Linux, built around you.**

*Made for developers. Designed for you.*

</div>
