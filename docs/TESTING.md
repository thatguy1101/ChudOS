# Testing

Environment used: Ubuntu 24.04 container, Python 3.13, PySide6 6.12.0 (pip), shellcheck 0.11.0,
2 vCPU, no KVM, no pacman/archiso/QEMU. Date: 2026-11-02.

## Levels of verification
| Level | Status |
|---|---|
| Static checks | done |
| Unit tests | done (220 passing, incl. offscreen profile-manager and Control Centre GUI) |
| Profile engine against a fake KDE backend | done (dict-backed stand-in for kreadconfig6/kwriteconfig6) |
| Profile engine against real Plasma (settings actually change, KWin reloads live) | **not done** |
| Sound playback through real PipeWire | **not done** |
| GUI smoke (offscreen Qt) | done |
| Packaging layout (PKGBUILD package() into scratch dirs, all modules import from installed layout) | done (tests/packaging) |
| Package names against archlinux.org | partial (below) |
| `makepkg` of local packages | **not done** (no Arch) |
| ISO build | **not done** |
| ISO boot in QEMU | **not done** |
| VM installation | **not done** |
| Installed system boots to ChudOS desktop | **not done** |
| Real Plasma: wallpaper apply, Welcome autostart | **not done** |
| Physical hardware | **not done** |

## Commands and results (2026-11-02)
- `python3 -I tools/validation/validate.py` → `validation OK`
- `python3 -m pytest -q tests` → 220 passed (maintenance, monitor window, store, sysinfo, Control Centre tools/GUI, welcome state/actions, validator-negative cases, staging, offscreen GUI, profile schema/store/apply/sound/CLI)
- `shellcheck` on `build.sh`, `apply-defaults`, `live-install` → clean; `bash -n` on both PKGBUILDs → OK
  (syntax only; PKGBUILDs were never run through makepkg)
- Welcome app launched offscreen for 4 s with no crash (one Qt platform-plugin message, harmless offscreen)
- `apply-defaults` run against a stub `plasma-apply-wallpaperimage`: tool missing → skips, no marker;
  wallpaper dir missing → skips; success → one call, marker written, second run no-op.
  The stub is not real Plasma, so real behaviour is unproven.
- The validator was shown to fail on bad input (unknown profiledef var, bad bootmode, SigLevel Never,
  extra remote repo, bad symlink target, bad package name, duplicate package).

## Package names
Confirmed to exist on archlinux.org (2026-11-02): pyside6, sddm, plasma-desktop, plasma-login-manager,
archinstall, vulkan-radeon, vulkan-intel, xorg-server, xorg-xwayland, noto-fonts-emoji, mkinitcpio-archiso,
kde-gtk-config, breeze-gtk, xdg-desktop-portal-kde, qt6-wayland. Also in upstream releng's list: base, linux,
linux-firmware, amd-ucode, intel-ucode, mkinitcpio, sudo, nano, openssh, btrfs-progs, dosfstools,
e2fsprogs, efibootmgr, less, man-db, arch-install-scripts, parted, gptfdisk, cryptsetup, squashfs-tools.
plasma-desktop's dependency page lists powerdevil (required) and plasma-nm, plasma-pa, kscreen (optional).
**Not individually verified:** breeze, konsole, dolphin, kate, ark, firefox, pipewire, pipewire-pulse,
wireplumber, mesa, vulkan-icd-loader, noto-fonts, networkmanager, git. All are long-standing Arch names.
The package-list validator checks name syntax only, not existence.

## Untestable here
Docker is installed in the authoring environment, but neither Docker Hub nor the Arch mirrors were reachable (connection refused by the sandbox proxy), so an Arch container could not be pulled and packages could not be downloaded. Not worked around.

Everything needing Arch, KVM, or a real Plasma session (see table). Untested assumptions: SDDM autologin
`Session=plasma` resolves in Plasma 6.8; tmpfiles `C /home/chud ... /etc/skel` works on archiso's rootfs;
sysusers creates `chud` early enough for tmpfiles; systemd symlinks enable sddm/NetworkManager.

## Dopamine Profiles engine (what the tests prove, and what they do not)
Proven by tests: strict validation (types, limits, unknown keys, NaN, duplicate JSON keys, size cap, path-traversal ids);
built-ins cannot be deleted, can be customised and reset; import cannot use built-in ids or overwrite silently;
corrupt files become warnings; unchanged settings are not rewritten; unrelated settings are not touched; a failed apply
restores earlier changes (and reports any it cannot restore); overlapping applies are refused by a lock; missing tools are
reported "unavailable" instead of pretended; the CLI says "PARTLY applied" when settings were unavailable.
NOT proven: that the KDE keys below actually change a running desktop. The fake backend only shows we issue the intended
commands. Needs a real Plasma 6.x session:
- accent colour: `plasma-apply-colorscheme --accent-color #rrggbb` (flag existence seen in KDE forum/MR titles only)
- animation speed: `kdeglobals [KDE] AnimationDurationFactor` = 1/speed (0 = off), then `qdbus6 org.kde.KWin /KWin reconfigure`
- blur: `kwinrc [Plugins] blurEnabled`, then KWin reconfigure
- sounds: ChudOS-played only (profile-applied cue via pw-play/paplay); not attached to KDE events

Profile manager GUI: tested offscreen (list, built-ins protected, edit+save persists, apply via fake KDE marks active, unavailable settings disabled) and screenshotted once. Not tested: real Plasma look and feel, keyboard navigation by hand, screen readers, colour picker dialog, file dialogs.

## Control Centre
Tested: sysinfo readers against fake /proc trees (first CPU sample = unavailable, idle = real 0%, missing fields = unavailable, no guessing MemAvailable),
updates states (none / list / failure / missing tool), tool detection, launch argv handling (no shell), Git identity validation,
background update check, scroll pages, Overview timer only on Overview, Ctrl+1..7 wiring, screenshots on this Ubuntu host (real values shown).
NOT tested: real keystroke dispatch (offscreen Qt does not deliver it), screen readers, systemsettings page ids (`kcm_colors`, `kcm_fonts`, `kcm_icons`,
`kcm_lookandfeel`, `kcm_kwin_effects`, `kcm_notifications` are from memory of Plasma 6 and must be checked on a real Plasma),
launching real programs, `checkupdates` on Arch, Wayland rendering/theme, high-DPI, any layout on a real KDE theme.
Not implemented (so not claimed): search box, per-category sound volumes, sound packs, update installation, cleanup, service status.

## Store
Tested with a fake pacman runner / fake streamer: name and query validation (option injection, shell characters, traversal), exact argv for
search/info/install/remove (always `--` before user-derived args; no -y/-u/-Sy; removal never -s/-n/-dd), root refusal, lock refusal,
pkexec/pacman missing, error classification (locked, signature, space, not-found, network, conflict), polkit denial, protected-package list,
catalogue validity, CLI confirmation, GUI offscreen (search, errors, confirm/cancel, progress log, failed remove, protected removal disabled, root disabled).
A real bug was found by these tests and fixed: `pacman -Ss` exiting 1 with an error on stderr was shown as "no results".
NOT tested: real pacman output formats beyond the parser's assumptions (`repo/name version [installed]` + indented description,
`-Si` "Key : value"), real pkexec/polkit prompts, real downloads, signature failures, interrupted transactions, locks held by a live pacman,
catalogue package names (checked only at runtime against pacman), localisation (we force LC_ALL=C for parsing).

## Updates / maintenance / Monitor
Tested with fakes: pre-flight (lock, low space, unreadable space), kernel restart heuristic (marked an ESTIMATE; says when it cannot tell),
fixed terminal commands (`sudo pacman -Syu`, `sudo paccache -r`; never `-Sy`, never --noconfirm), orphan list (filtered, "none" is a real answer),
cache size, `paccache -d` dry-run preview, journal errors (clamped), bounded largest-files scan (no symlinks, one filesystem, entry/time budget,
partial reported), a source check that the module contains no delete/write calls, GUI: update/cleanup need confirmation, blocked by pre-flight,
launch exactly the fixed command; Monitor: first CPU/network sample shown unavailable not 0, second computes, interval bounded 1-60 s, timer idle while hidden.
NOT tested: a real `pacman -Syu` (interrupted, locked, failed), real `checkupdates`/`paccache`/`journalctl` output formats, real network counters,
GPU (not implemented), process list (not implemented), konsole actually opening, restart heuristic against real Arch kernel naming variants (linux-lts, zen).

## Installer (`chudos-installer`)
**Verified here (sandbox, no Arch):** settings validation matrix, lsblk disk filtering, exact plan order and argv, password never in argv/plan/files,
engine behaviour against a fake executor (failure handling, always unmounts, path-traversal refusal), backend refusals (bad confirmation,
failed preflight, concurrent run), offscreen GUI flow including the typed-disk-name gate, staging bundles the repo and excludes live-only
packages from the install list.
**NOT verified (needs an Arch host + QEMU/OVMF):** real sgdisk/mkfs/pacstrap/arch-chroot, `bootctl install` inside the chroot, that the
installed system boots, that `bootctl` ships in the `systemd` package, SDDM autologin, the keyring service, Ctrl+Alt+F3..F6 consoles
(and which of F1/F2 is the desktop), the `chudos` repo `file://` bundle being readable by pacstrap.
