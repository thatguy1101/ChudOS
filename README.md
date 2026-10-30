<div align="center">

# ChudOS

### Your system. Your workflow. Your experience.

**A custom Arch Linux distribution built for developers, designed for customisation, and ready for play.**

[![Based on Arch Linux](https://img.shields.io/badge/Based%20on-Arch%20Linux-1793D1?style=for-the-badge&logo=archlinux&logoColor=white)](https://archlinux.org/)
[![Desktop Environment](https://img.shields.io/badge/Desktop-KDE%20Plasma-1D99F3?style=for-the-badge&logo=kde&logoColor=white)](https://kde.org/plasma-desktop/)
[![Status](https://img.shields.io/badge/Status-Early%20Development-orange?style=for-the-badge)](#-project-status)

---

</div>

## About

**ChudOS** is an Arch Linux-based distribution designed to deliver a polished, developer-focused desktop without sacrificing customisation, performance, or everyday usability.

Built on the flexibility of Arch Linux and the power of KDE Plasma, ChudOS aims to combine a premium desktop experience with practical development tools, gaming support, and a collection of purpose-built system applications.

Its defining feature is **Dopamine Profiles**: configurable desktop experiences that let users change the look, feel, sounds, animations, and behaviour of their system to suit their workflow.

From a clean, distraction-free development environment to a more expressive and animated desktop, ChudOS is designed to make Linux feel personal.

## Features

### Custom Desktop Experience

- A cohesive ChudOS visual identity.
- Custom branding, themes, icons, and wallpapers.
- Smooth animations and carefully designed visual effects.
- Extensive desktop customisation through KDE Plasma.
- A clean, premium default appearance.

### Dopamine Profiles

Customisable desktop profiles designed around different workflows and experiences.

| Profile | Description |
|---|---|
| **Default** | A polished, balanced desktop for everyday use. |
| **Hyper** | More expressive animations, vibrant colours, and configurable sound effects. |
| **Lock In** | A distraction-minimised environment for focused development. |
| **Gaming** | Convenient access to games, performance information, and gaming-related settings. |
| **Zen** | A calmer desktop with restrained visuals and minimal decorative sounds. |
| **Custom** | Build, configure, and save your own desktop experience. |

Profiles are intended to control real desktop settings, not just themes. The planned profile system includes configurable animations, sound effects, individual volume controls, visual effects, and other supported preferences.

### Developer-Focused

ChudOS aims to provide a convenient development environment with support for:

- Git and GitHub workflows.
- Python, Java, JavaScript, and TypeScript.
- C, C++, and Rust.
- Terminal-based development.
- Build tools and development utilities.
- Containers and project workflows.

The goal is to make common development tasks accessible without requiring users to configure everything manually.

### Gaming Support

ChudOS is designed for everyday gaming and moderate gaming workloads.

Planned support includes:

- Steam and Proton.
- Minecraft Java Edition.
- Modded Minecraft and Java runtime management.
- Gaming-related performance monitoring.
- Convenient access to gaming tools and applications.

ChudOS is not intended to be a specialised, maximum-performance AAA gaming distribution. Gaming features will complement its primary focus on development and desktop usability.

### Custom System Applications

ChudOS aims to develop its own collection of integrated desktop utilities.

| Application | Purpose |
|---|---|
| **ChudOS Welcome** | First-run setup, onboarding, and useful shortcuts. |
| **ChudOS Control Centre** | A central interface for ChudOS-specific settings. |
| **ChudOS Profiles** | Create, manage, and switch desktop profiles. |
| **ChudOS Monitor** | View system resources and performance information. |
| **ChudOS Store** | Discover and manage applications through supported package-management interfaces. |

These applications will be developed incrementally as the underlying distribution takes shape.

## Technology Stack

| Component | Technology |
|---|---|
| Base distribution | Arch Linux |
| Desktop environment | KDE Plasma |
| Display protocol | Wayland, with XWayland compatibility |
| Installation image | Archiso |
| Package management | pacman |
| GUI development | Python and PySide6, where appropriate |
| System integration | Linux utilities, KDE interfaces, and systemd where needed |
| Version control | Git |

ChudOS builds on existing Linux technologies rather than reinventing them unnecessarily. The objective is to create a cohesive distribution through thoughtful integration, custom software, and carefully selected defaults.

## Project Goals

- Deliver a bootable, installable ChudOS distribution.
- Establish a consistent visual identity.
- Develop a genuinely functional Dopamine Profiles system.
- Build useful, integrated desktop applications.
- Provide a convenient developer environment.
- Support everyday gaming and modded Minecraft.
- Keep the system responsive and reasonably lightweight.
- Make customisation accessible without requiring constant manual configuration.
- Maintain clear documentation, safe system operations, and a reliable build process.

## Project Status

**ChudOS is in early development.**

The project is being developed incrementally, beginning with the distribution foundation and progressing towards custom desktop functionality, system utilities, and a complete installation experience.

Features described in this README represent the project's goals and planned functionality. Individual features should not be considered implemented or stable until they are available in the codebase and have been tested.

Installation instructions and release information will be published as the project matures.

## Development Philosophy

ChudOS follows a few core principles:

- **Functionality first:** Real, working features over superficial demonstrations.
- **Customisation without compromise:** Extensive configuration while preserving reliability.
- **Performance matters:** Avoid unnecessary background services and excessive resource usage.
- **Built for developers:** Make development workflows convenient and practical.
- **Personal by design:** Let users shape their desktop around their preferences.
- **Built on Linux:** Reuse reliable existing technologies wherever they make sense.

## Contributing

ChudOS is under active development, and its architecture and feature set may evolve as the project progresses.

Bug reports, technical feedback, and suggestions are welcome as the project becomes more established.

Please review the project's contribution guidelines before submitting changes.

## Disclaimer

ChudOS is an independent project based on Arch Linux. It is not an official Arch Linux or KDE project.

Arch Linux, KDE Plasma, and other referenced technologies remain the property of their respective owners.

## License

The project's licensing terms will be documented here once established.

---

<div align="center">

**ChudOS — Linux, built around you.**

*Made for developers. Designed for you.*

</div>
