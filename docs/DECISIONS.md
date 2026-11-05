# Decisions

1. **Archiso `releng` as the base.** Reference files were fetched from upstream master on 2026-11-01. Variables in `profiledef.sh` are limited to ones releng uses.
2. **UEFI only (`uefi.systemd-boot`)** for this milestone. BIOS/syslinux, grub and speech boot entries from releng were dropped on purpose; they are untested here. Easy to re-add.
3. **SDDM + Plasma (Wayland session).** Arch also ships `plasma-login-manager` (6.8.2). Not adopted: SDDM is the established default and the Plasma login manager is untested by us. Revisit. `xorg-server` is kept so SDDM's default X11 greeter works; this is untested.
4. **Not `plasma-meta` / `kde-applications`.** Keep the image lean; add apps deliberately.
5. **Installer = own small graphical wizard (`chudos-installer`), following the Arch installation guide.** Not archinstall (text UI, not the Mint-style feel wanted) and not Calamares (large, heavy configuration, untested by us). The window runs as the normal user; a separate root-only backend rebuilds the plan from validated data, so the window can never send commands. archinstall stays on the live image as a text-mode fallback. Installed systems get the `chudos-*` packages from a repo bundled in the ISO (`/opt/chudos-repo`, unsigned, `Optional TrustAll` for that repo only). The installed system's own pacman.conf does not list `[chudos]`, so ChudOS packages do not receive updates until a public signed repo exists.
6. **Local unsigned `[chudos]` repo for the build only.** It is used by mkarchiso at build time and not copied into the installed system's pacman.conf.
7. **Welcome app installs to `/usr/lib/chudos/welcome` + launcher script**, avoiding Python-version-specific site-packages paths.
8. **`/etc/os-release` and `/etc/issue` are not changed:** they belong to Arch's `filesystem` package. Branding them needs a pacman hook or a ChudOS-owned `filesystem` replacement; deferred.
9. **Licence not chosen.** GPL-3.0-or-later appears in package metadata as a placeholder; choose before publishing.
11. **Profiles are data; settings registry is the only source of what a profile may contain.** Unknown keys are errors, not ignored. Sound is limited to cues ChudOS plays itself; attaching sounds to arbitrary KDE events is not attempted.
12. **Applying a profile with unavailable tools is a partial success, reported as such,** never silently "active".
13. **Control Centre reuses, not duplicates:** KDE System Settings pages for appearance, the existing profile manager window for profiles, `chudos_monitor.sysinfo` for metrics. Overview refreshes every 2 s only while visible and the window is active; updates are checked on demand (network).
14. **Installing packages is not done by the Control Centre yet:** it shows the exact `pacman -S` line to run. A GUI install needs the privilege design in the Store milestone.
15. **Store never refreshes the database (`-Sy`) and never passes `-u`:** a stale database fails safely ("not found"/404) and the user is told to do a full system update. Removal uses plain `-R` (fails if anything depends on the package) and a protected list blocks removing system/ChudOS packages. `pkexec` is used for privilege (generic polkit prompt; a custom polkit policy is a later improvement).
10. **PySide6 from the Arch repo (`pyside6`), not pip.**
