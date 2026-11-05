"""Control Centre logic with no Qt: tool detection, launch actions, validated Git identity.

Everything launched is a fixed argv (never a shell string). Nothing here installs packages:
install hints are text for the user to run themselves (the Store arrives in a later milestone).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ESSENTIAL, RECOMMENDED, OPTIONAL = "essential", "recommended", "optional"


@dataclass(frozen=True)
class Tool:
    name: str
    binary: str
    tier: str
    package: str          # Arch package that provides it (hint only)
    note: str = ""


DEV_TOOLS = (
    Tool("Git", "git", ESSENTIAL, "git"),
    Tool("SSH client", "ssh", ESSENTIAL, "openssh"),
    Tool("Python", "python3", ESSENTIAL, "python"),
    Tool("Terminal (Konsole)", "konsole", ESSENTIAL, "konsole"),
    Tool("Kate editor", "kate", RECOMMENDED, "kate"),
    Tool("GCC (C/C++)", "gcc", RECOMMENDED, "gcc"),
    Tool("Make", "make", RECOMMENDED, "make"),
    Tool("Node.js", "node", RECOMMENDED, "nodejs"),
    Tool("npm", "npm", RECOMMENDED, "npm"),
    Tool("Java (JDK)", "javac", RECOMMENDED, "jdk-openjdk", "also needed for Minecraft servers/mods"),
    Tool("Rust (rustup)", "rustup", OPTIONAL, "rustup"),
    Tool("Podman", "podman", OPTIONAL, "podman", "rootless containers"),
)

GAME_TOOLS = (
    Tool("Steam", "steam", RECOMMENDED, "steam", "needs the multilib repo enabled; proprietary"),
    Tool("Java runtime", "java", RECOMMENDED, "jre17-openjdk", "Minecraft needs a specific Java version per game version (e.g. 17); see docs"),
    Tool("Prism Launcher", "prismlauncher", OPTIONAL, "prismlauncher", "Minecraft launcher (extra repo)"),
    Tool("GameMode", "gamemoderun", OPTIONAL, "gamemode", "benefit not measured by ChudOS"),
    Tool("MangoHud", "mangohud", OPTIONAL, "mangohud", "in-game performance overlay"),
    Tool("Vulkan info", "vulkaninfo", OPTIONAL, "vulkan-tools", "shows which GPU/driver Vulkan sees"),
)


def tool_status(tools, which=shutil.which) -> list[tuple[Tool, bool]]:
    return [(t, which(t.binary) is not None) for t in tools]


def install_hint(missing: list[Tool]) -> str:
    return "sudo pacman -S " + " ".join(sorted({t.package for t in missing})) if missing else ""


# ---------- KDE settings shortcuts (KDE already does these well) ----------
KDE_PAGES = {
    "Colours": "kcm_colors", "Fonts": "kcm_fonts", "Icons": "kcm_icons",
    "Global theme": "kcm_lookandfeel", "Desktop effects": "kcm_kwin_effects",
    "Notifications": "kcm_notifications",
}


def kde_settings_argv(page: str | None) -> list[str]:
    if page is not None and page not in KDE_PAGES.values():
        raise ValueError(f"unknown settings page {page!r}")
    return ["systemsettings"] + ([page] if page else [])


def launch(argv: list[str], which=shutil.which, popen=subprocess.Popen) -> tuple[bool, str]:
    if not argv or which(argv[0]) is None:
        return False, f"{argv[0] if argv else 'program'} is not installed."
    try:
        popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as exc:
        return False, f"Could not start {argv[0]}: {exc}"
    return True, f"Started {argv[0]}."


def projects_dir(home: Path | None = None) -> Path:
    return (home or Path.home()) / "Projects"


def terminal_argv(directory: Path) -> list[str]:
    return ["konsole", "--workdir", str(directory)]


# ---------- Git identity (no credentials, ever) ----------
_EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


def validate_git_identity(name: str, email: str) -> str | None:
    """Return an error message, or None if valid."""
    if not name.strip() or len(name) > 100 or any(ord(c) < 32 for c in name):
        return "Name must be 1-100 printable characters."
    if len(email) > 254 or not _EMAIL_RE.match(email):
        return "Enter a valid email address."
    return None


def git_get(key: str, run=subprocess.run) -> str | None:
    try:
        p = run(["git", "config", "--global", "--get", key], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() or None if p.returncode == 0 else None


def git_set_identity(name: str, email: str, run=subprocess.run) -> tuple[bool, str]:
    err = validate_git_identity(name, email)
    if err:
        return False, err
    for key, val in (("user.name", name.strip()), ("user.email", email.strip())):
        try:
            p = run(["git", "config", "--global", key, val], capture_output=True, text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"git failed: {exc}"
        if p.returncode != 0:
            return False, f"git config {key} failed: {p.stderr.strip() or p.returncode}"
    return True, "Git identity saved to ~/.gitconfig."


UPDATE_GUIDANCE = (
    "Arch is a rolling release: always upgrade everything together (sudo pacman -Syu). "
    "Never run 'pacman -Sy' on its own or install packages after only refreshing the database (partial upgrade). "
    "Read the Arch news first if the last update was long ago. If an update is interrupted, run the same "
    "command again; if pacman reports a lock and no pacman is running, only then remove /var/lib/pacman/db.lck."
)

RECOVERY_GUIDANCE = (
    "Broken desktop settings: log in on a text console (Ctrl+Alt+F3) and rename ~/.config/plasma-org.kde.plasma.desktop-appletsrc. "
    "Profile problems: 'chudos-profile reset <id>' restores a built-in profile; delete ~/.config/chudos to start over. "
    "Failed boot after an update: boot the ChudOS live medium, mount your system, arch-chroot into it and re-run the upgrade. "
    "Disk full: free space before updating (pacman -Scc removes cached packages and is irreversible: read what it prints)."
)
