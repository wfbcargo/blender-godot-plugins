#!/usr/bin/env python3
"""Rebuild every fixture headless and compare it against its golden.

    python tools/regress.py                      # all fixtures, against tests/golden/
    python tools/regress.py --only rabbit        # one
    python tools/regress.py --plugins <checkout> # exercise another checkout of the plugins
    python tools/regress.py --update             # rewrite the goldens, then review the diff
    python tools/regress.py --twice              # build each fixture twice; the builds must agree
    python tools/regress.py --godot <project>    # then play the exports in Godot's verifiers

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

`--godot <project>` then copies each fixture's `.glb` and `.moves.json` into
`<project>/_regress/`, imports them, and runs the engine-side verifiers the project's addons carry:
every manifest through rig-anything's `verify_moves.gd`, and each fixture in GODOT_WARDROBE dressed
and walked by wardrobe's `verify_wardrobe.gd`. The folder is removed afterwards whatever happens.
It warns first when the project's addons differ from this repo's, since those are what run.

Blender is found at $BLENDER, or the newest under Program Files, or `blender` on PATH; Godot at
$GODOT, or the newest `Godot_v*_console.exe` under ~/Downloads, or `godot` on PATH.
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
               "FT_SCRIPTS": "follow-through", "WD_SCRIPTS": "wardrobe", "CP_SCRIPTS": "character-pipeline"}

# Keys whose value is a path, a duration or a date: real output, never the same twice. Matched as
# whole words of the key (split on `_`), never as substrings: `*file*` once skipped `profile`, `*dir*`
# a radial arm's `direction_model` and `*path*` a distance, `path_m`. A key ending in a unit is a
# measurement whatever else it says.
VOLATILE = {"path", "paths", "filepath", "file", "files", "filename", "dir", "directory", "timing",
            "timings", "elapsed", "when", "date", "timestamp", "secs", "seconds"}
UNITS = {"m", "m2", "m3", "mm", "cm", "deg", "rad", "mps", "hz", "kg", "pct"}
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
    words = [w for w in re.split(r"[_\W]+", key.lower()) if w]
    if not words or words[-1] in UNITS:
        return False
    return any(w in VOLATILE for w in words)


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


# --godot: the engine side of each fixture. Every `.moves.json` a fixture exports goes through
# rig-anything's MovesController verifier. A fixture named here also has its garment worn by the
# body it was cut from, walked, and counted for holes and poke-through by wardrobe's verifier.
# `garment` may list several files, comma-separated: they are worn together.
GODOT_WARDROBE = {
    "dressed_figure": {"body": "figure.glb", "garment": "shirt.glb",
                       "args": ["frames=240", "every=8", "hem=true", "jiggle=true"]},
    "dressed_presets": {"body": "figure.glb", "garment": "sports_top.glb,shorts_mid_thigh.glb",
                        "args": ["frames=240", "every=8", "hem=true", "jiggle=true"]},
    "pipeline_woman": {"body": "fixwoman.glb", "garment": "fixwoman_sportstop.glb,fixwoman_shorts.glb",
                       "args": ["frames=240", "every=8", "hem=true", "jiggle=true"]},
}
# The Godot addons the verifiers load from the project, and where this repo keeps each one.
GODOT_ADDONS = {"rig_anything": "rig-anything", "wardrobe": "wardrobe", "follow_through": "follow-through"}
GODOT_STAGE = "_regress"                         # res://_regress/<fixture>/, removed afterwards


def find_godot():
    if os.environ.get("GODOT"):
        return os.environ["GODOT"]
    found = sorted(glob.glob(os.path.expanduser(r"~/Downloads/Godot_v*/Godot_v*_console.exe")))
    return found[-1] if found else (shutil.which("godot") or "godot")


def _text(path):
    with open(path, "rb") as fh:
        return fh.read().replace(b"\r\n", b"\n")


def addon_drift(project):
    """Files where the project's copy of an addon differs from this repo's, ignoring line endings.
    The verifiers run the project's copy, so a drifted one is testing something else."""
    drift = []
    for addon, plugin in GODOT_ADDONS.items():
        mine = REPO / "plugins" / plugin / "godot" / "addons" / addon
        theirs = project / "addons" / addon
        if not mine.is_dir():
            continue
        if not theirs.is_dir():
            drift.append("addons/%s missing from the project" % addon)
            continue
        names = {p.relative_to(mine) for p in mine.rglob("*") if p.is_file() and p.suffix != ".uid"}
        names |= {p.relative_to(theirs) for p in theirs.rglob("*") if p.is_file() and p.suffix != ".uid"}
        for rel in sorted(names):
            a, b = mine / rel, theirs / rel
            if not a.is_file() or not b.is_file() or _text(a) != _text(b):
                drift.append("addons/%s/%s" % (addon, rel.as_posix()))
    return drift


def _godot(godot, project, *args, timeout=900):
    proc = subprocess.run([godot, "--headless", "--path", str(project), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)
    return proc.returncode, proc.stdout or ""


def run_godot(godot, project, out_root, names):
    """Stage the fixtures' exports in the project, import them, run the verifiers.
    Returns [(fixture or check, passed, one-line detail)]."""
    stage = project / GODOT_STAGE
    shutil.rmtree(stage, ignore_errors=True)
    results, manifests, wardrobe = [], [], []
    try:
        for name in names:
            src = out_root / name
            dst = stage / name
            files = [p for p in src.rglob("*") if p.is_file() and "_humanform_library" not in p.parts
                     and (p.suffix == ".glb" or p.name.endswith(".moves.json"))]
            for p in files:
                # Keep the fixture's own layout: `rabbit` writes a second rabbit.moves.json under
                # fresh_session/, and a flat copy would verify one file twice.
                rel = p.relative_to(src)
                target = dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target)
                if p.name.endswith(".moves.json"):
                    res_dir = "res://%s/%s" % (GODOT_STAGE, (Path(name) / rel.parent).as_posix())
                    # A manifest names its glb by the res:// path it was exported for; here it is
                    # beside the manifest, wherever that was meant to be.
                    with open(target, encoding="utf-8") as fh:
                        m = json.load(fh)
                    if m.get("scene"):
                        m["scene"] = "%s/%s" % (res_dir, m["scene"].rsplit("/", 1)[-1])
                    with open(target, "w", encoding="utf-8") as fh:
                        json.dump(m, fh, indent=1)
                    label = (Path(name) / rel).as_posix()
                    if m.get("gaits"):
                        manifests.append("%s/%s" % (res_dir, p.name))
                    else:
                        # verify_moves drives a gait ladder. A radial body's crawl has no `gaits`
                        # entry, and no engine verifier of its own yet.
                        results.append(("verify_moves %s" % label, True,
                                        "skipped - its manifest has no gaits for MovesController to drive"))
            if name in GODOT_WARDROBE:
                wardrobe.append(name)
        if not manifests and not wardrobe:
            return results or [("godot", True, "no fixture in this run exports anything Godot checks")]

        code, out = _godot(godot, project, "--import")
        if code != 0:
            return results + [("godot import", False, "exit %s: %s" % (code, out.strip().splitlines()[-1:] or ""))]

        if manifests:
            code, out = _godot(godot, project, "-s", "res://addons/rig_anything/verify_moves.gd", "--",
                               "manifests=" + ",".join(manifests))
            verdict = [l for l in out.splitlines() if l.startswith("MOVES VERIFY")]
            failed = [l.split("FAIL", 1)[1].strip() for l in out.splitlines() if l.startswith("MOVES  FAIL")]
            results.append(("verify_moves (%d manifest%s)" % (len(manifests), "" if len(manifests) == 1 else "s"),
                            code == 0 and bool(verdict) and "PASSED" in verdict[-1],
                            (verdict[-1] if verdict else "no verdict, exit %s" % code)
                            + ("".join("\n            " + f for f in failed[:12]))))

        for name in wardrobe:
            spec = GODOT_WARDROBE[name]
            wanted = [spec["body"]] + spec["garment"].split(",")
            found = {f: sorted((stage / name).rglob(f)) for f in wanted}
            if not all(found.values()):
                results.append(("verify_wardrobe %s" % name, False,
                                "the fixture did not export %s" % " and ".join(wanted)))
                continue
            at = {f: "res://" + v[0].relative_to(project).as_posix() for f, v in found.items()}
            res = {"body": at[spec["body"]], "garment": ",".join(at[f] for f in wanted[1:])}
            code, out = _godot(godot, project, "--fixed-fps", "60", "-s", "res://addons/wardrobe/verify_wardrobe.gd",
                               "--", "body=" + res["body"], "garment=" + res["garment"], *spec["args"])
            line = [l for l in out.splitlines() if l.startswith("WD_RESULT ")]
            if not line:
                results.append(("verify_wardrobe %s" % name, False, "no WD_RESULT, exit %s" % code))
                continue
            r = json.loads(line[-1][len("WD_RESULT "):])
            results.append(("verify_wardrobe %s" % name, bool(r.get("passed")),
                            "holes %.3f%% poke %.3f%% over %s frames%s" % (
                                100 * r.get("holes_frac", 0), 100 * r.get("poke_frac", 0), r.get("frames"),
                                "".join("\n            " + p for p in r.get("problems", [])))))
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return results


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
    ap.add_argument("--godot", metavar="PROJECT",
                    help="also run the Godot verifiers on the fixtures' exports inside this project")
    ap.add_argument("--godot-bin", default=find_godot(), help="the Godot console binary ($GODOT)")
    args = ap.parse_args(argv)

    names = args.only or fixtures()
    unknown = [n for n in names if not (FIXTURES / (n + ".py")).is_file()]
    if unknown:
        ap.error("no such fixture: %s (have: %s)" % (", ".join(unknown), ", ".join(fixtures())))
    if not Path(args.blender).is_file() and not shutil.which(args.blender):
        ap.error("no Blender at %s - set $BLENDER or pass --blender" % args.blender)
    project = Path(args.godot).resolve() if args.godot else None
    if project:
        if not (project / "project.godot").is_file():
            ap.error("--godot %s: no project.godot there" % project)
        if not Path(args.godot_bin).is_file() and not shutil.which(args.godot_bin):
            ap.error("no Godot at %s - set $GODOT or pass --godot-bin" % args.godot_bin)
        drift = addon_drift(project)
        if drift:
            print("WARNING: the project's addons differ from this repo's, so the verifiers run the "
                  "project's copy:\n  " + "\n  ".join(drift))

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
    failures, updated, built = [], [], []
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
                built.append(name)
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
        if project and built:
            # A fixture whose golden moved still exported something worth playing; one that
            # errored or did not reproduce did not.
            print("\ngodot: %s" % project)
            for check, passed, detail in run_godot(args.godot_bin, project, out_root / builds[0], built):
                print("  %s %s: %s" % ("ok     " if passed else "FAILED ", check, detail))
                if not passed:
                    failures.append(check)
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
