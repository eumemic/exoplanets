"""Command line: run from pipeline/ as `../.venv/bin/python -m dag COMMAND`.

  status            every rule's state (ok, new, stale, edited, missing, waiting, failed) and why
  explain RULE      a rule's inputs, parameters, code and the distributions it uses, with what changed
  run [RULE ...]    build what is not up to date (all rules, or the named ones and what they need)
      --dry-run         list what would run
      --discard-edits   overwrite outputs that were changed outside the build
  check             exit 1 unless every rule is up to date and every check passed
      --ci              on another machine (CI): compare the lock with the committed files and code only, not with the
                        installed packages, and list inputs that are not present (private data) instead of failing;
                        private rules are left out
  graph             the rules in build order, with their inputs and outputs
"""
import argparse
import sys
from pathlib import Path

from .graph import BuildError, Project

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m dag", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["status", "explain", "run", "check", "graph"])
    ap.add_argument("rules", nargs="*")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--discard-edits", action="store_true")
    ap.add_argument("--ci", action="store_true")
    a = ap.parse_args(argv)
    try:
        p = Project(a.root)
        if a.command == "status":
            for n in p.order:
                s = p.status(n)
                print(f"{n + (' (private)' if p.rules[n].private else ''):28s} {s.state}" + ("" if s.ok else ": " + "; ".join(s.reasons[:6]) + (" …" if len(s.reasons) > 6 else "")))
            p.hasher.save()
        elif a.command == "explain":
            for n in a.rules or p.order:
                r = p.rules[n]
                st, info = p.stamp(r)
                s = p.status(n)
                print(f"{n}: {s.state}")
                for x in s.reasons:
                    print(f"  - {x}")
                print("  inputs:", *(f"    {k}" for k in info["inputs"]), sep="\n")
                print("  outputs:", *(f"    {k}" for k in r.outputs), sep="\n")
                print("  parameters:", *(f"    {k} = {v!r}" for k, v in info["params"].items()), sep="\n")
                print("  code:", *(f"    {k}" for k in sorted(info["code"]["parts"])), sep="\n")
                print("  packages:", *(f"    {k} {v['version']}" + (" (files changed after install)" if v.get("modified") else "")
                                       for k, v in info["code"]["env"]["dists"].items()), sep="\n")
            p.hasher.save()
        elif a.command == "run":
            ran, failed = p.run(a.rules, discard_edits=a.discard_edits, dry_run=a.dry_run)
            if not a.dry_run:
                print(f"ran {len(ran)} rule(s)" + (f"; failed checks: {', '.join(failed)}" if failed else ""))
            return 1 if failed else 0
        elif a.command == "check" and a.ci:
            n_bad = 0
            for n in p.order:
                if p.rules[n].private:
                    continue
                problems, unchecked = p.check_lock(n)
                n_bad += bool(problems)
                for x in problems:
                    print(f"{n}: {x}")
                if unchecked:
                    print(f"{n}: not present here, not checked: {', '.join(unchecked)}")
            print("the lock matches the committed files and code" if not n_bad else f"{n_bad} rule(s) do not match the lock")
            return 1 if n_bad else 0
        elif a.command == "check":
            bad = [(n, p.status(n)) for n in p.order]
            bad = [(n, s) for n, s in bad if not s.ok]
            p.hasher.save()
            for n, s in bad:
                print(f"{n}: {s.state}: " + "; ".join(s.reasons))
            print("all rules up to date and all checks passed" if not bad else f"{len(bad)} rule(s) not up to date")
            return 1 if bad else 0
        elif a.command == "graph":
            for n in p.order:
                r = p.rules[n]
                print(f"{n}" + (" (check)" if r.is_check else "") + (" (private)" if r.private else ""))
                for i in r.inputs:
                    print(f"    < {i}")
                for o in r.outputs:
                    print(f"    > {o}")
    except BuildError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
