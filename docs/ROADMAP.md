# Roadmap

## Done (code exists, statically checked + unit tested)
Archiso profile, package lists, branding v0, `chudos-defaults`, `chudos-welcome`, build driver, validator, tests, Dopamine Profiles engine + CLI + manager window, Control Centre v0 (7 sections), system-info library (unit tested only; not run on real Plasma).

## Next (blocked on an Arch build host)
1. Build the ISO and boot it in QEMU/OVMF; fix whatever breaks (expect package-name and SDDM/Plasma-session issues).
2. VM install test of `chudos-installer` (QEMU + OVMF); then a public signed repo so installed systems can update ChudOS packages.
3. Boot/login branding (SDDM theme, boot menu look).

## Next (no Arch host needed)
- Welcome app profile picker; GUI polish (live preview not implemented).
- More verified profile settings (only when read/write/rollback exist).

## Planned later (not started)
GPU monitoring, process list, in-app update installer (today: confirmed terminal), a real polkit policy, + safe cleanup, developer/gaming package work beyond detection, developer + gaming packages, Monitor, Store, update/maintenance tools, release engineering.

## Known limitations
See README and INSTALLATION.
