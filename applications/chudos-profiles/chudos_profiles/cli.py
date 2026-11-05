"""chudos-profile command line (also the integration point the GUI will use)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import sound
from .apply import ApplyError, apply_profile
from .schema import SETTINGS, ValidationError
from .store import ProfileStore, StoreError

BUILTIN_DIRS = (Path("/usr/share/chudos/profiles"),)


def make_store(env=None) -> ProfileStore:
    env = os.environ if env is None else env
    home = Path(env.get("HOME", "~")).expanduser()
    cfg = Path(env.get("XDG_CONFIG_HOME") or home / ".config") / "chudos"
    state = Path(env.get("XDG_STATE_HOME") or home / ".local" / "state") / "chudos"
    builtin = Path(env["CHUDOS_PROFILE_DIR"]) if env.get("CHUDOS_PROFILE_DIR") else BUILTIN_DIRS[0]
    return ProfileStore(builtin, cfg, state)


def main(argv=None, store: ProfileStore | None = None, out=sys.stdout, err=sys.stderr) -> int:
    ap = argparse.ArgumentParser(prog="chudos-profile")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("active")
    sub.add_parser("settings")
    for name in ("show", "apply", "delete", "reset"):
        sub.add_parser(name).add_argument("id")
    p = sub.add_parser("create"); p.add_argument("id"); p.add_argument("name"); p.add_argument("--description", default="")
    p = sub.add_parser("duplicate"); p.add_argument("src"); p.add_argument("id"); p.add_argument("name")
    p = sub.add_parser("set"); p.add_argument("id"); p.add_argument("setting"); p.add_argument("value", help="JSON value")
    p = sub.add_parser("export"); p.add_argument("id"); p.add_argument("file", type=Path)
    p = sub.add_parser("import"); p.add_argument("file", type=Path); p.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(argv)
    store = store or make_store()
    try:
        if a.cmd == "list":
            profs, warns = store.list()
            act = store.active()
            for pr in profs:
                tag = "builtin" if pr["builtin"] else "custom"
                tag += ", modified" if pr["modified"] else ""
                print(f"{'*' if pr['id'] == act else ' '} {pr['id']:<16} {pr['name']} [{tag}]", file=out)
            for w in warns:
                print(f"warning: {w}", file=err)
        elif a.cmd == "active":
            print(store.active() or "(none)", file=out)
        elif a.cmd == "settings":
            for s in SETTINGS.values():
                print(f"{s.id}  ({s.kind}, default {s.default!r})\n    {s.description}\n    via: {s.mechanism}", file=out)
        elif a.cmd == "show":
            print(json.dumps(store.get(a.id), indent=2), file=out)
        elif a.cmd == "apply":
            res = apply_profile(store, a.id)
            for k in ("applied", "unchanged", "rolled_back", "not_restored"):
                if getattr(res, k):
                    print(f"{k}: {', '.join(getattr(res, k))}", file=out)
            for sid, why in res.unavailable.items():
                print(f"unavailable: {sid}: {why}", file=out)
            for sid, why in res.failed.items():
                print(f"FAILED: {sid}: {why}", file=err)
            for w in res.warnings:
                print(f"warning: {w}", file=err)
            if res.ok:
                st = sound.play("profile-applied", sound.load(sound.config_path()))
                if res.unavailable:
                    print(f"profile '{a.id}' PARTLY applied: {len(res.unavailable)} setting(s) unavailable on this system "
                          f"(sound: {st})", file=out)
                else:
                    print(f"profile '{a.id}' applied and active (sound: {st})", file=out)
            return 0 if res.ok else 1
        elif a.cmd == "create":
            store.create(a.id, a.name, a.description)
        elif a.cmd == "duplicate":
            store.duplicate(a.src, a.id, a.name)
        elif a.cmd == "set":
            prof = dict(store.get(a.id))
            try:
                value = json.loads(a.value)
            except ValueError:
                raise ValidationError("value must be JSON (true, 0.5, \"#aabbcc\")")
            prof["settings"] = dict(prof["settings"], **{a.setting: value})
            store.save(prof)
        elif a.cmd == "delete":
            store.delete(a.id)
        elif a.cmd == "reset":
            store.reset(a.id)
        elif a.cmd == "export":
            store.export_to(a.id, a.file)
        elif a.cmd == "import":
            pr = store.import_from(a.file, overwrite=a.overwrite)
            print(f"imported '{pr['id']}'", file=out)
    except (StoreError, ValidationError, ApplyError) as exc:
        print(f"error: {exc}", file=err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
