"""GUI-independent helpers for the profile manager (no Qt imports, unit-tested)."""
from __future__ import annotations

from .apply import ApplyResult, Backend
from .schema import SETTINGS


def summarize(res: ApplyResult) -> tuple[str, str]:
    """Return (level, text); level is 'ok' | 'warn' | 'error'."""
    if res.failed:
        sid, why = next(iter(res.failed.items()))
        extra = ""
        if res.rolled_back:
            extra = f" Earlier changes were undone ({len(res.rolled_back)})."
        if res.not_restored:
            extra += f" Could not restore: {', '.join(res.not_restored)}."
        return "error", f"Failed on {sid}: {why}.{extra}"
    if res.unavailable:
        names = ", ".join(res.unavailable)
        return "warn", f"Applied what this system supports. Unavailable: {names}."
    if res.warnings:
        return "warn", "Applied. " + " ".join(res.warnings)
    if not res.applied:
        return "ok", "Already up to date. Nothing changed."
    return "ok", f"Applied {len(res.applied)} setting(s)."


def availability(backend: Backend | None = None) -> dict[str, str | None]:
    """Map each setting id to None (usable) or the reason it is unavailable here."""
    b = backend or Backend()
    return {sid: b.available(sid) for sid in SETTINGS}
