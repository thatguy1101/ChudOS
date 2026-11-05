# Release-candidate readiness (honest status, 2026-11-03)

**Verdict: NOT a release candidate. It is a statically checked, unit-tested foundation that has never been built into an ISO,
booted, installed, or run on a real Plasma desktop.** Passing tests here means "the logic behaves against fakes", not "ChudOS works".

## Verification levels
| Level | Result |
|---|---|
| Static validation (profile, pacman.conf, package lists, live/installed separation, desktop files) | pass |
| shellcheck / bash -n on scripts and PKGBUILDs | pass |
| Unit + offscreen GUI tests | pass (see TESTING.md for the count) |
| PKGBUILD `package()` run into scratch dirs; launcher paths; every module imports from the installed layout | pass |
| `makepkg` real build of the 6 packages | **not done** |
| ISO build (`mkarchiso`) | **not done** |
| ISO boot (QEMU/OVMF), live desktop, autologin | **not done** |
| VM installation, installed system boots to ChudOS desktop | **not done** |
| Profiles actually change a real Plasma session (accent, animation speed, blur) | **not done** |
| Real pacman / pkexec / checkupdates / paccache behaviour | **not done** |
| Physical hardware, Secure Boot, NVIDIA, Steam/Proton, Minecraft | **not done** |

## Review findings
Fixed (found by tests or review): `pacman -Ss` errors shown as "no results"; profile apply reporting "active" when settings were unavailable; stale Welcome text;
double CPU sampling at Control Centre start; unused imports; live-only installer launcher shipped in the installed-defaults package; `/etc/issue` file
conflicting with Arch's `filesystem` package (removed).
Open (not fixed, by design or lack of environment):
- Duplicated helper code: the background-job/Signal helper is copied in 3 windows and "launch fixed argv" exists in Welcome and Control Centre. Small; a shared package was judged worse than the copy for now.
- Placeholder project URL in all PKGBUILDs; no LICENSE file (licence choice is the owner's); SECURITY contact is a placeholder.
- The graphical installer installs the ChudOS packages from the bundled repo, but it is **untested on real hardware or a VM**, and installed systems cannot update them (no public repo).
- Local build repo is unsigned (`SigLevel = Optional TrustAll`, build-time only). Release packages should be signed.
- `pkexec` shows a generic polkit prompt; no custom polkit action text.
- Store uses `--noconfirm` for install/remove after the GUI confirmation. It auto-answers pacman's default prompts (e.g. picks the default package provider).
  Signature checking is separate and is never bypassed, but this should be reviewed on real pacman.
- `os-release` / boot / login branding not done; SDDM theme not done; boot menu is stock apart from names.
- Unverified Plasma assumptions: `plasma-apply-colorscheme --accent-color`, `AnimationDurationFactor` live reload, `systemsettings kcm_*` page ids,
  SDDM `Session=plasma` on Plasma 6.8 with the X11 greeter (Plasma also ships its own `plasma-login-manager`).
- Not implemented (not claimed): search in Control Centre, per-category sounds and sound packs, other-event sounds, notification controls, GPU/process monitoring,
  in-app update install and cleanup, service status, snapshots, Secure Boot, encryption guidance, custom installer.

## Release blockers (in order)
1. Build the 6 packages and the ISO on an Arch host; fix what breaks.
2. Boot it in QEMU+OVMF: live desktop, autologin, Welcome, Control Centre, Store launch, no crashes.
3. Verify profile settings on the live Plasma (screenshots/readbacks), fix or remove any that do not work.
4. Test a VM install end to end; then decide on a public signed repo for updates.
5. Test Store and update flow against real pacman (locks, interruptions, offline, bad signature).
6. Licence, contact, project URL, signed packages, checksums published with the ISO.

## Next priorities
Items 1-3 above (they need only an Arch VM), then installation path, then branding (SDDM, boot), then GPU/Proton/Minecraft testing on real hardware.
