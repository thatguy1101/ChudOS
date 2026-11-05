"""Qt-free wizard logic: validation of each page and the typed-erase gate."""
from __future__ import annotations

from dataclasses import dataclass, field

from .settings import HOSTNAME_RE, KEYBOARDS, LOCALES, RESERVED_USERNAMES, USERNAME_RE


@dataclass
class Form:
    disk: str = ""
    fullname: str = ""
    hostname: str = ""
    username: str = ""
    password: str = ""
    password2: str = ""
    timezone: str = ""
    locale: str = LOCALES[0][1] if LOCALES else ""
    keymap: str = KEYBOARDS[0][1] if KEYBOARDS else "us"
    confirm: str = ""
    usable_disks: set = field(default_factory=set)

    def disk_error(self) -> str:
        if not self.disk:
            return "Choose the disk to install ChudOS on."
        return "" if self.disk in self.usable_disks else "That disk cannot be used."

    def user_errors(self) -> dict[str, str]:
        e: dict[str, str] = {}
        if not self.fullname.strip() or any(c in self.fullname for c in ":,\n"):
            e["fullname"] = "Enter your name (no colons or commas)."
        if not HOSTNAME_RE.match(self.hostname):
            e["hostname"] = "Computer name: letters, digits and hyphens, starting with a letter or digit."
        if not USERNAME_RE.match(self.username) or self.username in RESERVED_USERNAMES:
            e["username"] = "Username: lowercase letters, digits, - or _, starting with a letter. Not a reserved name."
        if len(self.password) < 1:
            e["password"] = "Choose a password."
        elif self.password != self.password2:
            e["password2"] = "The passwords do not match."
        if not self.timezone:
            e["timezone"] = "Choose your time zone."
        return e

    def confirm_ok(self) -> bool:
        return bool(self.disk) and self.confirm == self.disk and not self.disk_error() and not self.user_errors()

    def request(self) -> dict:
        if not self.confirm_ok():
            raise ValueError("form is not complete or not confirmed")
        return {"settings": {"disk": self.disk, "hostname": self.hostname, "username": self.username, "fullname": self.fullname.strip(),
                              "password": self.password, "timezone": self.timezone, "locale": self.locale, "keymap": self.keymap},
                "confirm_erase": self.confirm}
