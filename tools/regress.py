#!/usr/bin/env python3
"""Rebuild every fixture headless and compare it against its golden.

    python tools/regress.py                      # all fixtures, against tests/golden/
    python tools/regress.py --only rabbit        # one
    python tools/regress.py --plugins <checkout> # exercise another checkout of the plugins
    python tools/regress.py --update             # rewrite the goldens, then review the diff
    python tools/regress.py --twice              # build each fixture twice; the builds must agree

Each fixture (tests/fixtures/<name>.py) is a script Blender runs in its own process, building
something from nothing and writing a JSON report of what it got. This compares that report to
tests/golden/<name>.json key by key, with a numeric tolerance, and exits non-zero on any change.

A change is not by itself a failure - a fix moves numbers. The point is that it is *seen*, on
every fixture rather than on whichever character was being built at the time, and that accepting
it is a reviewed commit to tests/golden.

A golden only catches what differs from the one build it was recorded from. A step that gives a
different answer on every run - wardrobe's garments moved 9.9 mm between two builds of Belle - is
invisible to it, because the golden is one of the draws. `--twice` builds every fixture a second
time in the same run and compares the two builds with each other; a disagreement is
NONDETERMINISTIC and fails the run, and no golden is written from a build that did not reproduce.

Blender is found at $BLENDER, or the newest under Program Files, or `blender` on PATH.
"""
import argparse
import concurrent.futures
import fnmatch
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"
GOLDEN = REPO / "tests" / "golden"
SCRIPT_VARS = {"RA_SCRIPTS": "rig-anything", "HF_SCRIPTS": "humanform",
               "FT_SCRIPTS": "follow-through", "WD_SCRIPTS": "wardrobe"}

# Keys whose value is a path, a duration or a date: real output, never the same twice.
VOLATILE = ["*path*", "*file*", "*dir*", "*timing*", "*elapsed*", "*when*", "*date*",
            "*timestamp*", "*secs*", "*seconds"]
# A value that is an absolute path is volatile whatever its key is called - `sidecar` was one.
PATHLIKE = re.compile(r"^([A-Za-z]:[\\/]|\\\\|/[^/])")
# Relative tolerance by dotted key pattern; the first match wins, else DEFAULT_TOLERANCE.
TOLERANCES = {}
DEFAULT_TOLERANCE = 1e-3


def find_blender():
    if os.environ.get("BLENDER"):
        return os.environ["BLENDER"]
    found = sorted(glob.glob(r"C:/Program Files/Blender Foundation/Blender */blender.exe"))
    return found[-1] if found else (shutil.which("blender") or "blender")


def fixtures():
    return sorted(p.stem for p in FIXTURES.glob("*.py") if not p.name.startswith("_"))


def volatile(key):
    k = key.lower()
    return any(fnmatch.fnmatch(k, pat) for pat in VOLATILE)


def flatten(value, prefix=""):
    """{dotted key: scalar}, dropping volatile keys wherever they appear."""
    out = {}
    if isinstance(value, dict):
        for k, v in value.items():
            if not volatile(str(k)):
                out.update(flatten(v, "%s.%s" % (prefix, k) if prefix else str(k)))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.update(flatten(v, "%s[%d]" % (prefix, i)))
    elif isinstance(value, str) and PATHLIKE.match(value):
        pass                                    # an absolute path: this run's, not a result
    else:
        out[prefix] = value
    return out


def tolerance(key):
    for pat, tol in TOLERANCES.items():
        if fnmatch.fnmatch(key, pat):
            return tol
    return DEFAULT_TOLERANCE


def same(key, a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        scale = max(abs(a), abs(b))
        return abs(a - b) <= max(tolerance(key) * scale, 1e-9)
    return a == b


def compare(golden, fresh):
    """Every key that appeared, vanished or moved, as (key, was, now)."""
    was, now = flatten(golden.get("report", {})), flatten(fresh.get("report", {}))
    changes = []
    for key in sorted(set(was) | set(now)):
        if key not in now:
            changes.append((key, was[key], "<gone>"))
        elif key not in was:
            changes.append((key, "<new>", now[key]))
        elif not same(key, was[key], now[key]):
            changes.append((key, was[key], now[key]))
    return changes


def run_fixture(name, blender, out_root, env):
    path = FIXTURES / (name + ".py")
    out = out_root / name
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    proc = subprocess.run([blender, "-b", "--factory-startup", "--python", str(path),
                           "--", "out=%s" % out], capture_output=True, text=True, env=env)
    took = time.time() - started
    result_path = out / (name + ".json")
    if not result_path.is_file():
        tail = "\n".join((proc.stdout or "").splitlines()[-12:])
        return {"fixture": name, "error": "no report written (exit %s)\n%s" % (proc.returncode, tail)}, took
    with open(result_path, encoding="utf-8") as fh:
        return json.load(fh), took


def show(changes, was="was", now="now", limit=40):
    for key, before, after in changes[:limit]:
        print("          %s\n            %s %r\n            %s %r" % (key, was, before, now, after))
    if len(changes) > limit:
        print("          ... and %d more" % (len(changes) - limit))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", metavar="FIXTURE", help="run these fixtures, not all")
    ap.add_argument("--plugins", metavar="CHECKOUT",
                    help="a repo checkout whose plugins/<name>/scripts the fixtures import")
    ap.add_argument("--update", action="store_true", help="rewrite goldens from this run")
    ap.add_argument("--twice", action="store_true",
                    help="build every fixture twice and fail if the two builds disagree")
    ap.add_argument("--jobs", type=int, default=1, help="fixtures to run at once (default 1)")
    ap.add_argument("--keep", metavar="DIR", help="keep each fixture's output here, not in a temp dir")
    ap.add_argument("--blender", default=find_blender())
    args = ap.parse_args(argv)

    names = args.only or fixtures()
    unknown = [n for n in names if not (FIXTURES / (n + ".py")).is_file()]
    if unknown:
        ap.error("no such fixture: %s (have: %s)" % (", ".join(unknown), ", ".join(fixtures())))
    if not Path(args.blender).is_file() and not shutil.which(args.blender):
        ap.error("no Blender at %s - set $BLENDER or pass --blender" % args.blender)

    env = dict(os.environ)
    if args.plugins:
        root = Path(args.plugins).resolve()
        for var, plugin in SCRIPT_VARS.items():
            # A checkout from before a plugin moved in here does not have it; that plugin then
            # stays on this repo's copy rather than failing to import.
            scripts = root / "plugins" / plugin / "scripts"
            if scripts.is_dir():
                env[var] = str(scripts)
        have = sorted(p for var, p in SCRIPT_VARS.items() if env.get(var, "").startswith(str(root)))
        print("plugins: %s (%s; the rest from this checkout)" % (root, ", ".join(have)))
    else:
        print("plugins: %s (this checkout)" % REPO)
    GOLDEN.mkdir(parents=True, exist_ok=True)

    temp = None if args.keep else tempfile.TemporaryDirectory(prefix="regress-")
    out_root = Path(args.keep) if args.keep else Path(temp.name)
    failures, updated = [], []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            # With --twice each build gets its own folder - and so its own humanform library, so
            # the second build cannot warm-start from the first and hide a difference.
            builds = ("a", "b") if args.twice else ("",)
            runs = {(name, b): pool.submit(run_fixture, name, args.blender, out_root / b, env)
                    for name in names for b in builds}
            for name in names:
                fresh, took = runs[(name, builds[0])].result()
                versions = " ".join("%s %s" % (k, v) for k, v in sorted(fresh.get("plugins", {}).items()))
                head = "%s [%.0fs] %s" % (name, took, versions)
                if "error" in fresh:
                    print("  ERROR   %s\n          %s" % (head, fresh["error"]))
                    failures.append(name)
                    continue
                if args.twice:
                    second, took_b = runs[(name, "b")].result()
                    head = "%s [%.0fs + %.0fs] %s" % (name, took, took_b, versions)
                    if "error" in second:
                        print("  ERROR   %s (second build)\n          %s" % (head, second["error"]))
                        failures.append(name)
                        continue
                    differ = compare(fresh, second)
                    if differ:
                        # Checked before the golden: a build that does not reproduce is not a
                        # result to compare, and never one to record.
                        print("  NONDETERMINISTIC %s: %d key(s) differ between two builds"
                              % (head, len(differ)))
                        show(differ, "a", "b")
                        failures.append(name)
                        continue
                golden_path = GOLDEN / (name + ".json")
                if args.update or not golden_path.is_file():
                    with open(golden_path, "w", encoding="utf-8") as fh:
                        json.dump(fresh, fh, indent=1, sort_keys=True)
                    print("  %s %s" % ("UPDATED" if args.update else "RECORDED", head))
                    updated.append(name)
                    continue
                with open(golden_path, encoding="utf-8") as fh:
                    changes = compare(json.load(fh), fresh)
                if not changes:
                    print("  ok      %s" % head)
                    continue
                failures.append(name)
                print("  CHANGED %s: %d key(s)" % (head, len(changes)))
                show(changes)
    finally:
        if temp:
            temp.cleanup()

    if updated:
        print("\ngoldens written for %s - review the diff before committing" % ", ".join(updated))
    if failures:
        print("\n%d fixture(s) changed or failed: %s" % (len(failures), ", ".join(failures)))
        return 1
    print("\nno change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
