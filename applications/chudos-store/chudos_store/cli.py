"""chudos-store command line: search, info, install, remove, recommended. Confirmation is required for changes."""
from __future__ import annotations

import argparse
import sys

from .catalogue import entries
from .pacman import Pacman, StoreError


def main(argv=None, pm: Pacman | None = None, out=sys.stdout, err=sys.stderr, confirm=input) -> int:
    ap = argparse.ArgumentParser(prog="chudos-store")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("recommended")
    sub.add_parser("search").add_argument("query")
    sub.add_parser("info").add_argument("name")
    p = sub.add_parser("install"); p.add_argument("names", nargs="+"); p.add_argument("-y", "--yes", action="store_true", help="skip the confirmation question")
    p = sub.add_parser("remove"); p.add_argument("name"); p.add_argument("-y", "--yes", action="store_true")
    a = ap.parse_args(argv)
    pm = pm or Pacman()
    try:
        if a.cmd == "recommended":
            for e in entries():
                print(f"{'*' if pm.is_installed(e['name']) else ' '} {e['name']:<20} {e['category']:<12} {e['why']}", file=out)
        elif a.cmd == "search":
            for pk in pm.search(a.query):
                print(f"{'*' if pk.installed else ' '} {pk.repo}/{pk.name} {pk.version}  {pk.description}", file=out)
        elif a.cmd == "info":
            for k, v in pm.info(a.name).items():
                print(f"{k}: {v}", file=out)
        else:
            names = a.names if a.cmd == "install" else [a.name]
            verb = "Install" if a.cmd == "install" else "Remove"
            if not a.yes and confirm(f"{verb} {', '.join(names)}? Your password will be requested. [y/N] ").strip().lower() != "y":
                print("Cancelled. Nothing was changed.", file=out); return 0
            res = pm.install(names, lambda l: print(l, file=out)) if a.cmd == "install" else pm.remove(names[0], lambda l: print(l, file=out))
            if not res.ok:
                print(f"error ({res.kind}): {res.message}", file=err); return 1
            print(res.message, file=out)
    except StoreError as exc:
        print(f"error ({exc.kind}): {exc.message}", file=err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
