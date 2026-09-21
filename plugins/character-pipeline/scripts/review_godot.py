#!/usr/bin/env python3
"""Review built characters in Godot's look: lookdev's `close-shot` of each one, dressed, beside its Blender
close set, judged by close-shot's own checks.

    python review_godot.py characters/cast_*.toml [--presets clear_midday] [--views face,bust,full] [--no-import]

Why: the review stage's close-ups are Blender's, and what ships is Godot's. The likeness round's dress showed
its bust points and its beard square patches only in Godot - seven rebuilds between them, each found by eye
after the build. This renders the same views through the game's own import, lighting and materials, with the
Blender tile of each view first in its row, into `<export dir>/review/<id>/godot/` (sheet.png, close.json).

It runs AFTER the builds, never inside one: `build_many` builds in parallel, and a Godot `--import` per build
would race on the one project's import cache. So the project is imported once, then each character is shot
in turn. `build_many` calls this when its builds are done (`--no-godot-review` skips it).

A character fails when close-shot reports a failure (a view that misses its subject, a full figure lit past
white, shadow acne on the floor...) or does not run. Exit 0 when every character passes, 1 otherwise, 2 when
nothing could run (no Godot, no node, no lookdev). Godot is $GODOT, else the newest `Godot_v*_console.exe`
under ~/Downloads, else `godot` on PATH; lookdev is $LD_SCRIPTS's plugin, else the installed copy.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from character_pipeline import spec as spec_mod  # noqa: E402

# one preset keeps it near a build's own review in time; add overcast for a lighting check
DEFAULT_PRESETS = "clear_midday"


def find_godot():
    if os.environ.get("GODOT") and os.path.isfile(os.environ["GODOT"]):
        return os.environ["GODOT"]
    found = sorted(glob.glob(os.path.expanduser(r"~/Downloads/Godot_v*/Godot_v*_console.exe")))
    return found[-1] if found else shutil.which("godot")


def find_lookdev():
    ld = os.environ.get("LD_SCRIPTS")
    root = os.path.dirname(ld) if ld else os.path.join(os.path.expanduser("~"), ".claude", "skills", "lookdev")
    mjs = os.path.join(root, "bin", "lookdev.mjs")
    return mjs if os.path.isfile(mjs) else None


def target(ch):
    """(project, res:// glb, export dir, garments, Blender close dir or None, out dir) for a built character."""
    project = ch.project
    export_dir = os.path.join(project, ch.export.dir)
    glb = f"{ch.export.res_dir.rstrip('/')}/{ch.id}.glb"
    garments = []
    manifest = os.path.join(export_dir, f"{ch.id}.moves.json")
    if os.path.isfile(manifest):
        with open(manifest, encoding="utf-8") as fh:
            garments = json.load(fh).get("garments") or []
    close = os.path.join(export_dir, "review", ch.id, "close")
    out = os.path.join(export_dir, "review", ch.id, "godot")
    return project, glb, export_dir, garments, (close if os.path.isfile(os.path.join(close, "close.json")) else None), out


def review_one(ch, godot, lookdev, presets, views):
    project, glb, export_dir, garments, close, out = target(ch)
    if not os.path.isfile(os.path.join(export_dir, f"{ch.id}.glb")):
        return {"id": ch.id, "ok": False, "error": f"not built: no {ch.id}.glb in {ch.export.dir}"}
    cmd = ["node", lookdev, "close-shot", "--project", project, "--godot", godot, "--glb", glb,
           "--presets", presets, "--out", out]
    if views:
        cmd += ["--views", views]
    if garments:
        cmd += ["--garments", ",".join(garments)]
    if close:
        cmd += ["--pair-blender", close]
    # a close.json from the last run must not stand in for this one if it does not finish (a timed-out shot
    # read its predecessor's 5.06% as its own)
    stale = os.path.join(out, "close.json")
    if os.path.isfile(stale):
        os.remove(stale)
    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    secs = round(time.time() - t0, 1)
    try:
        with open(os.path.join(out, "close.json"), encoding="utf-8") as fh:
            rep = json.load(fh)
    except (OSError, ValueError):
        tail = " | ".join((res.stdout + res.stderr).strip().splitlines()[-3:])
        return {"id": ch.id, "ok": False, "seconds": secs, "error": f"close-shot did not finish (exit {res.returncode}): {tail}"}
    pair = rep.get("pair_blender") or {}
    return {"id": ch.id, "ok": res.returncode == 0 and not rep.get("failures"), "seconds": secs,
            "tiles": len(rep.get("tiles", [])), "failures": rep.get("failures", []),
            "paired": len(pair.get("paired", [])), "blender": bool(close), "garments": len(garments),
            "sheet": rep.get("sheet")}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--presets", default=DEFAULT_PRESETS)
    ap.add_argument("--views", default=None, help="close-shot views (default: lookdev's full close set)")
    ap.add_argument("--no-import", action="store_true", help="the project is already imported")
    a = ap.parse_args(argv)
    specs = [s for s in a.specs if os.path.basename(s) != "pipeline.toml"]
    godot, lookdev = find_godot(), find_lookdev()
    missing = [n for n, v in (("Godot", godot), ("node", shutil.which("node")), ("lookdev", lookdev)) if not v]
    if missing:
        print(f"REVIEW_GODOT cannot run: no {', '.join(missing)}", file=sys.stderr)
        return 2
    chars = [spec_mod.load(s) for s in specs]
    if not a.no_import:
        for project in sorted({c.project for c in chars}):
            t0 = time.time()
            r = subprocess.run([godot, "--headless", "--path", project, "--import"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            print(f"imported {project} in {time.time() - t0:.1f} s (exit {r.returncode})", flush=True)
    results = []
    for ch in chars:
        r = review_one(ch, godot, lookdev, a.presets, a.views)
        results.append(r)
        if r.get("error"):
            print(f"  FAIL  {r['id']:<22} {r['error']}", flush=True)
        else:
            print(f"  {'ok  ' if r['ok'] else 'FAIL'}  {r['id']:<22} {r['seconds']:>5.1f} s  {r['tiles']} tiles, "
                  f"{r['paired']} beside Blender, {r['garments']} garment(s)  sheet {r['sheet']}", flush=True)
            for f in r["failures"][:8]:
                print(f"          {f}", flush=True)
    bad = sum(1 for r in results if not r["ok"])
    print(f"REVIEW_GODOT DONE {len(results) - bad} ok, {bad} failed")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
