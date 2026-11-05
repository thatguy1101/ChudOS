"""Setting registry: the single source of truth for what a profile may contain.

Only settings with a real implementation (see apply.py) are listed. Each has an id,
type, default, limits, description and mechanism. Unknown ids are rejected, never ignored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

FORMAT_VERSION = 1
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_NAME = 40
MAX_DESC = 200


@dataclass(frozen=True)
class SettingDef:
    id: str
    kind: str                      # "bool" | "float" | "int" | "color"
    default: Any
    description: str
    mechanism: str                 # how it is applied; shown in the UI
    minimum: float | None = None
    maximum: float | None = None
    requires: str | None = None    # external program needed at apply time
    zero_ok: bool = False          # 0 allowed even though below minimum (meaning: off)


SETTINGS: dict[str, SettingDef] = {s.id: s for s in (
    SettingDef("appearance.accent_color", "color", "#3daee9",
               "Plasma accent colour.", "plasma-apply-colorscheme --accent-color (Plasma 6.1+)",
               requires="plasma-apply-colorscheme"),
    SettingDef("effects.animation_speed", "float", 1.0,
               "Animation speed: 1 = normal, 2 = twice as fast, 0.5 = half speed, 0 = animations off. "
               "Applied as AnimationDurationFactor = 1/speed (0 -> 0).",
               "kdeglobals [KDE] AnimationDurationFactor + KWin reconfigure",
               minimum=0.25, maximum=4.0, requires="kwriteconfig6", zero_ok=True),
    SettingDef("effects.blur", "bool", True,
               "Desktop blur effect.", "kwinrc [Plugins] blurEnabled + KWin reconfigure",
               requires="kwriteconfig6"),
    SettingDef("sound.enabled", "bool", True,
               "Play ChudOS decorative sounds (never touches app audio or system notifications).",
               "ChudOS sound player (chudos-profiles sound config)"),
    SettingDef("sound.volume", "int", 50,
               "Decorative effects volume, 0-100.", "ChudOS sound player (chudos-profiles sound config)",
               minimum=0, maximum=100),
)}


class ValidationError(ValueError):
    pass


def validate_value(setting: SettingDef, value: Any) -> Any:
    k = setting.kind
    if k == "bool":
        if not isinstance(value, bool):
            raise ValidationError(f"{setting.id}: expected true/false")
        return value
    if k in ("int", "float"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(f"{setting.id}: expected a number")
        if k == "int" and (isinstance(value, float) and not value.is_integer()):
            raise ValidationError(f"{setting.id}: expected a whole number")
        v = int(value) if k == "int" else float(value)
        if v != v or v in (float("inf"), float("-inf")):
            raise ValidationError(f"{setting.id}: not a finite number")
        if v == 0 and setting.zero_ok:
            return v
        if setting.minimum is not None and v < setting.minimum or setting.maximum is not None and v > setting.maximum:
            raise ValidationError(f"{setting.id}: must be between {setting.minimum} and {setting.maximum}"
                                  + (" (or 0 for off)" if setting.zero_ok else ""))
        return v
    if k == "color":
        if not isinstance(value, str) or not HEX_RE.match(value):
            raise ValidationError(f"{setting.id}: expected colour like #3daee9")
        return value.lower()
    raise ValidationError(f"{setting.id}: unsupported kind {k}")


def validate_profile(data: Any) -> dict:
    """Strictly validate and normalise a profile dict. Raises ValidationError."""
    if not isinstance(data, dict):
        raise ValidationError("profile must be a JSON object")
    allowed = {"format_version", "id", "name", "description", "settings"}
    extra = set(data) - allowed
    if extra:
        raise ValidationError(f"unknown field(s): {', '.join(sorted(map(str, extra)))}")
    if data.get("format_version") != FORMAT_VERSION:
        raise ValidationError(f"unsupported format_version {data.get('format_version')!r} (expected {FORMAT_VERSION})")
    pid = data.get("id")
    if not isinstance(pid, str) or not ID_RE.match(pid):
        raise ValidationError("id must be 1-40 chars of a-z, 0-9 and '-', not starting with '-'")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME or any(ord(c) < 32 for c in name):
        raise ValidationError(f"name must be 1-{MAX_NAME} printable characters")
    desc = data.get("description", "")
    if not isinstance(desc, str) or len(desc) > MAX_DESC or any(ord(c) < 32 for c in desc):
        raise ValidationError(f"description must be at most {MAX_DESC} printable characters")
    settings = data.get("settings")
    if not isinstance(settings, dict):
        raise ValidationError("settings must be an object")
    clean = {}
    for key, value in settings.items():
        if key not in SETTINGS:
            raise ValidationError(f"unknown setting {key!r}")
        clean[key] = validate_value(SETTINGS[key], value)
    return {"format_version": FORMAT_VERSION, "id": pid, "name": name.strip(),
            "description": desc, "settings": clean}
