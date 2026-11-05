# Troubleshooting

- **`build.sh check` says host is not Arch:** build in an Arch VM/container.
- **`error: target not found: <pkg>` during mkarchiso:** a package was renamed/removed; check archlinux.org/packages and edit `distro/packages/*.txt`, then run `validate.py`.
- **`makepkg` refuses to run as root:** run `build.sh packages` as a normal user.
- **`local repo missing`:** run `build.sh packages` before `iso`.
- **Welcome says PySide6 missing:** install `pyside6`.
- **Wallpaper not applied:** run `/usr/lib/chudos/apply-defaults` inside a Plasma session; delete `~/.local/state/chudos/defaults-applied-v1` to retry.
- **Welcome keeps appearing / never appears:** state file is `~/.local/state/chudos/welcome.json`; `chudos-welcome --force` always shows. It always shows on the live medium.
