"""Curated recommended-apps catalogue. Data only; every name is re-validated before use.
Availability and installed state always come from pacman at runtime, never from this file."""
from __future__ import annotations

from .pacman import validate_name

CATALOGUE = (
    # (package, category, why)
    ("firefox", "Internet", "Web browser"),
    ("thunderbird", "Internet", "Email client"),
    ("vlc", "Media", "Plays almost any audio/video file"),
    ("obs-studio", "Media", "Recording and streaming"),
    ("gimp", "Graphics", "Image editor"),
    ("krita", "Graphics", "Digital painting"),
    ("inkscape", "Graphics", "Vector graphics"),
    ("libreoffice-fresh", "Office", "Office suite (large)"),
    ("keepassxc", "Security", "Offline password manager"),
    ("neovim", "Development", "Terminal editor"),
    ("nodejs", "Development", "JavaScript runtime"),
    ("rustup", "Development", "Rust toolchain manager"),
    ("jdk-openjdk", "Development", "Java development kit (Minecraft servers/mods)"),
    ("podman", "Development", "Rootless containers"),
    ("htop", "System", "Process viewer"),
    ("steam", "Games", "Needs the multilib repository enabled; proprietary"),
    ("prismlauncher", "Games", "Minecraft launcher (check it is in your repos)"),
)


def entries() -> list[dict]:
    out = []
    for name, cat, why in CATALOGUE:
        validate_name(name)
        out.append({"name": name, "category": cat, "why": why})
    return out
