"""Installer settings and strict validation. Every value that reaches a command line or a config file is validated here.
No Qt. The password is held in memory only and is never part of a plan, a log line or an argv."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MIN_DISK_BYTES = 20 * 1024**3
DISK_RE = re.compile(r"^/dev/(sd[a-z]{1,2}|vd[a-z]{1,2}|xvd[a-z]{1,2}|nvme[0-9]{1,2}n[0-9]{1,2}|mmcblk[0-9]{1,2})$")
HOSTNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$")
USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")
TZ_RE = re.compile(r"^[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+){0,2}$")
RESERVED_USERNAMES = frozenset({
    "root", "daemon", "bin", "sys", "sync", "games", "man", "lp", "mail", "news", "uucp", "proxy", "nobody", "http", "ftp",
    "git", "systemd-network", "systemd-resolve", "dbus", "polkit", "sddm", "chud", "wheel", "adm", "admin", "sudo",
})

# (label, value) - curated on purpose: every value is known to exist in glibc's locale.gen.
LOCALES = (
    ("English (United States)", "en_US.UTF-8"), ("English (United Kingdom)", "en_GB.UTF-8"), ("English (Australia)", "en_AU.UTF-8"),
    ("English (Canada)", "en_CA.UTF-8"), ("Deutsch", "de_DE.UTF-8"), ("Français", "fr_FR.UTF-8"), ("Español", "es_ES.UTF-8"),
    ("Italiano", "it_IT.UTF-8"), ("Português (Brasil)", "pt_BR.UTF-8"), ("Nederlands", "nl_NL.UTF-8"), ("Polski", "pl_PL.UTF-8"),
)
# (label, console keymap, xkb layout, xkb variant)
KEYBOARDS = (
    ("US", "us", "us", ""), ("UK", "uk", "gb", ""), ("German", "de-latin1", "de", ""), ("French", "fr", "fr", ""),
    ("Spanish", "es", "es", ""), ("Italian", "it", "it", ""), ("Portuguese", "pt-latin1", "pt", ""),
    ("Brazilian", "br-abnt2", "br", ""), ("Russian", "ru", "ru", ""), ("Japanese", "jp106", "jp", ""), ("US Dvorak", "dvorak", "us", "dvorak"),
)
LOCALE_VALUES = frozenset(v for _, v in LOCALES)
KEYMAPS = {k[1]: k for k in KEYBOARDS}


class SettingsError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field, self.message = field, message


@dataclass(frozen=True)
class InstallSettings:
    disk: str
    hostname: str
    username: str
    fullname: str
    password: str
    timezone: str
    locale: str
    keymap: str

    def public(self) -> dict:
        """Everything except the password: safe to log or print."""
        return {k: v for k, v in self.__dict__.items() if k != "password"}


def _ctl(s: str) -> bool:
    return any(ord(c) < 32 or ord(c) == 127 for c in s)


def validate(raw: dict, zoneinfo_dir: Path = Path("/usr/share/zoneinfo")) -> InstallSettings:
    """Validate a plain dict (from the GUI/JSON) into InstallSettings. Raises SettingsError(field, message)."""
    def get(name: str) -> str:
        v = raw.get(name)
        if not isinstance(v, str):
            raise SettingsError(name, f"{name} is required")
        return v
    disk = get("disk")
    if not DISK_RE.match(disk):
        raise SettingsError("disk", "Choose a whole disk such as /dev/sda or /dev/nvme0n1 (not a partition).")
    hostname = get("hostname").strip().lower()
    if not HOSTNAME_RE.match(hostname):
        raise SettingsError("hostname", "Computer name: letters, digits and '-', 1-32 characters, not starting or ending with '-'.")
    username = get("username").strip()
    if not USERNAME_RE.match(username) or username in RESERVED_USERNAMES:
        raise SettingsError("username", "Username: lowercase letters, digits, '_' or '-', starting with a letter; reserved names are not allowed.")
    fullname = get("fullname").strip()
    if not fullname or len(fullname) > 64 or _ctl(fullname) or ":" in fullname or "," in fullname:
        raise SettingsError("fullname", "Name: 1-64 characters, without ':' or ','.")
    password = get("password")
    if not 1 <= len(password) <= 128 or _ctl(password):
        raise SettingsError("password", "Password: 1-128 characters, no control characters.")
    tz = get("timezone")
    if not TZ_RE.match(tz) or ".." in tz or not (Path(zoneinfo_dir) / tz).is_file():
        raise SettingsError("timezone", "Unknown time zone.")
    locale = get("locale")
    if locale not in LOCALE_VALUES:
        raise SettingsError("locale", "Unsupported language.")
    keymap = get("keymap")
    if keymap not in KEYMAPS:
        raise SettingsError("keymap", "Unsupported keyboard layout.")
    return InstallSettings(disk, hostname, username, fullname, password, tz, locale, keymap)


def validate_package_name(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9@_+][a-z0-9@._+-]{0,99}", name))
