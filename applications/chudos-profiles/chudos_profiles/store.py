"""Profile storage. Profiles are data: JSON only, size-limited, never executed.

Built-ins ship read-only (system dir). A user "override" with the same id customises a built-in;
deleting the override restores the original. User profiles live in the user's config dir.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .schema import ID_RE, ValidationError, validate_profile

MAX_BYTES = 64 * 1024
BUILTIN_IDS = ("default", "hyper", "lock-in", "gaming", "zen")
DEFAULT_PROFILE = "default"


class StoreError(Exception):
    pass


def parse_json_bytes(raw: bytes) -> dict:
    if len(raw) > MAX_BYTES:
        raise ValidationError(f"file too large (> {MAX_BYTES} bytes)")
    def no_dupes(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise ValidationError(f"duplicate key {k!r}")
            d[k] = v
        return d
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=no_dupes)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValidationError(f"not valid JSON: {exc}") from exc
    return validate_profile(data)


class ProfileStore:
    def __init__(self, builtin_dir: Path, config_dir: Path, state_dir: Path):
        self.builtin_dir = Path(builtin_dir)
        self.user_dir = Path(config_dir) / "profiles"
        self.state_file = Path(state_dir) / "active-profile.json"
        self.lock_file = Path(state_dir) / "apply.lock"

    # ---- reading
    def _read(self, path: Path) -> dict:
        try:
            return parse_json_bytes(path.read_bytes())
        except OSError as exc:
            raise StoreError(f"cannot read {path.name}: {exc}") from exc

    def builtin(self, pid: str) -> dict | None:
        p = self.builtin_dir / f"{pid}.json"
        return self._read(p) if p.is_file() else None

    def get(self, pid: str) -> dict:
        if not ID_RE.match(pid):
            raise StoreError(f"invalid profile id {pid!r}")
        up = self.user_dir / f"{pid}.json"
        if up.is_file():
            prof = self._read(up)
            if prof["id"] != pid:
                raise StoreError(f"{up.name}: id does not match file name")
            return prof
        prof = self.builtin(pid)
        if prof is None:
            raise StoreError(f"no such profile: {pid}")
        return prof

    def list(self) -> tuple[list[dict], list[str]]:
        """Return (profiles, warnings). Corrupt files become warnings, not crashes."""
        ids, warnings, out = set(), [], []
        for d in (self.builtin_dir, self.user_dir):
            if d.is_dir():
                ids.update(p.stem for p in d.glob("*.json"))
        for pid in sorted(ids, key=lambda i: (i not in BUILTIN_IDS, BUILTIN_IDS.index(i) if i in BUILTIN_IDS else 0, i)):
            try:
                prof = self.get(pid)
            except (StoreError, ValidationError) as exc:
                warnings.append(f"{pid}: {exc}")
                continue
            prof = dict(prof, builtin=pid in BUILTIN_IDS, modified=(self.user_dir / f"{pid}.json").is_file() and pid in BUILTIN_IDS)
            out.append(prof)
        return out, warnings

    # ---- writing
    def save(self, profile: dict) -> dict:
        prof = validate_profile(profile)
        self.user_dir.mkdir(parents=True, exist_ok=True)
        path = self.user_dir / f"{prof['id']}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(prof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        return prof

    def create(self, pid: str, name: str, description: str = "", settings: dict | None = None) -> dict:
        if pid in BUILTIN_IDS or (self.user_dir / f"{pid}.json").exists():
            raise StoreError(f"profile {pid!r} already exists")
        return self.save({"format_version": 1, "id": pid, "name": name, "description": description,
                          "settings": settings or {}})

    def duplicate(self, src: str, new_id: str, new_name: str) -> dict:
        base = self.get(src)
        return self.create(new_id, new_name, base["description"], dict(base["settings"]))

    def delete(self, pid: str) -> None:
        if pid in BUILTIN_IDS:
            raise StoreError("built-in profiles cannot be deleted (use reset to restore defaults)")
        path = self.user_dir / f"{pid}.json"
        if not path.is_file():
            raise StoreError(f"no such custom profile: {pid}")
        path.unlink()
        if self.active() == pid:
            self.state_file.unlink(missing_ok=True)

    def reset(self, pid: str) -> None:
        if pid not in BUILTIN_IDS:
            raise StoreError("only built-in profiles can be reset")
        (self.user_dir / f"{pid}.json").unlink(missing_ok=True)

    # ---- import / export
    def export_to(self, pid: str, dest: Path) -> None:
        prof = self.get(pid)
        Path(dest).write_text(json.dumps(prof, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def import_from(self, src: Path, overwrite: bool = False) -> dict:
        try:
            raw = Path(src).read_bytes()
        except OSError as exc:
            raise StoreError(f"cannot read import file: {exc}") from exc
        prof = parse_json_bytes(raw)
        if prof["id"] in BUILTIN_IDS:
            raise StoreError(f"import id {prof['id']!r} is reserved for a built-in profile; change the id")
        if (self.user_dir / f"{prof['id']}.json").exists() and not overwrite:
            raise StoreError(f"profile {prof['id']!r} already exists (overwrite not confirmed)")
        return self.save(prof)

    # ---- active profile record
    def active(self) -> str | None:
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            pid = data.get("active")
            return pid if isinstance(pid, str) and ID_RE.match(pid) else None
        except (OSError, ValueError, AttributeError):
            return None

    def set_active(self, pid: str) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"active": pid}), encoding="utf-8")
        os.replace(tmp, self.state_file)
