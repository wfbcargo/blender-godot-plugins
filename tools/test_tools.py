#!/usr/bin/env python3
"""Checks for tools/regress.py and tools/bump.py that need no Blender. Each check has a control that
must fail, so a check that stops measuring is caught.

    python tools/test_tools.py

The end-to-end part runs regress.py against a fake Blender (a .cmd on Windows, a shell script
elsewhere, both calling `_fake_blender` in this file) that writes each fixture's golden back as its
report after a set delay, or a changed one when told to: the run order, results printed as they
finish, the diff file and the `REGRESS DONE` line are checked on a passing and a failing run.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import regress  # noqa: E402
import bump  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %s %s%s" % ("ok     " if ok else "FAILED ", name, (": " + detail) if detail and not ok else ""),
          flush=True)
    if not ok:
        FAILED.append(name)


# --- --quick selection ---------------------------------------------------------------------------

def test_quick():
    names = regress.fixtures()
    sel, skip, _ = regress.select(["plugins/wardrobe/scripts/wardrobe/fit.py"], names)
    for n in ("dressed_figure", "dressed_presets", "dressed_skirts", "traced_detail", "pipeline_woman"):
        check("wardrobe change selects %s" % n, n in sel, str(sorted(sel)))
    for n in ("rabbit", "cricket", "starfish", "quadruped", "review_sheet"):
        check("wardrobe change skips %s" % n, n in skip and n not in sel, str(sorted(sel)))
    # control: the same selector on a rig-anything change must pick rabbit and cricket up
    sel, _, _ = regress.select(["plugins/rig-anything/scripts/rig_analysis/hop.py"], names)
    check("control: rig-anything change selects rabbit and cricket", {"rabbit", "cricket"} <= set(sel))
    check("control: rig-anything change selects everything (every fixture uses it)", set(sel) == set(names),
          str(sorted(set(names) - set(sel))))
    for path in ("tools/regress.py", "tests/fixtures/_harness.py"):
        sel, skip, _ = regress.select([path], names)
        check("%s selects every fixture" % path, set(sel) == set(names) and not skip, str(sorted(skip)))
    sel, _, _ = regress.select(["tests/fixtures/_export_only.py"], names)
    check("_export_only.py selects rabbit alone", sorted(sel) == ["rabbit"], str(sorted(sel)))
    sel, skip, _ = regress.select(["docs/improvements/NEXT.md", "tests/README.md", ".claude-plugin/marketplace.json"],
                                  names)
    check("documentation selects nothing", not sel, str(sorted(sel)))
    sel, _, _ = regress.select(["tests/golden/starfish.json", "tests/fixtures/quadruped.py"], names)
    check("a fixture or golden selects itself", sorted(sel) == ["quadruped", "starfish"], str(sorted(sel)))
    sel, _, _ = regress.select(["plugins/godot-lsp/bridge.py"], names)
    check("godot-lsp selects nothing", not sel, str(sorted(sel)))
    sel, _, _ = regress.select(["some/new/thing.txt"], names)
    check("an unclassified path selects everything", set(sel) == set(names))
    # the import closure: humanform imports wardrobe, so a humanform-only fixture is reached
    reach = regress.fixture_plugins("mpfb_woman_curvy")
    check("mpfb_woman_curvy reaches wardrobe through humanform", "wardrobe" in reach, str(reach))
    check("control: rabbit reaches rig-anything alone", set(regress.fixture_plugins("rabbit")) == {"rig-anything"},
          str(regress.fixture_plugins("rabbit")))


# --- small pieces ----------------------------------------------------------------------------------

def test_pieces():
    saved = dict(regress.DURATIONS)
    try:
        regress.DURATIONS.clear()
        regress.DURATIONS.update({"a": 10, "b": 300, "c": 50})
        check("schedule is longest first, unmeasured before all", regress.schedule(["a", "b", "c", "new"]) ==
              ["new", "b", "c", "a"], str(regress.schedule(["a", "b", "c", "new"])))
    finally:
        regress.DURATIONS.clear()
        regress.DURATIONS.update(saved)
    check("done line", regress.done_line(1, 18) == "REGRESS DONE exit=1, 18 fixtures ok")
    check("done line, one", regress.done_line(0, 1) == "REGRESS DONE exit=0, 1 fixtures ok")
    warn = regress.volatile_blocks({"build_timing": {"stage": 1, "result": 2}, "a": [{"when": {"x": 1}}]})
    check("VOLATILE dict warned", [k for k, _ in warn] == ["build_timing", "a[0].when"], str(warn))
    quiet = regress.volatile_blocks({"record": {"stages_timed": ["a"]}, "paths": ["C:/x"], "build": {"stage_count": {"x": 1}},
                                     "total_seconds": 3.0})
    check("control: no warning for a list of paths, a dict under a plain key or a scalar", quiet == [], str(quiet))
    check("path warning near MAX_PATH", regress.path_warning(Path("C:/" + "k" * 150), 100) is not None)
    check("control: no path warning on a short --keep", regress.path_warning(Path("C:/k"), 100) is None)


# --- bump.py ---------------------------------------------------------------------------------------

def _bump_repo(root):
    shutil.copytree(REPO / ".claude-plugin", root / ".claude-plugin")
    for p in (REPO / "plugins").iterdir():
        if (p / ".claude-plugin" / "plugin.json").is_file():
            (root / "plugins" / p.name / ".claude-plugin").mkdir(parents=True)
            shutil.copy2(p / ".claude-plugin" / "plugin.json", root / "plugins" / p.name / ".claude-plugin")


def _snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*.json")}


def test_bump():
    with tempfile.TemporaryDirectory(prefix="bump-") as tmp:
        root = Path(tmp)
        _bump_repo(root)
        before = _snapshot(root)
        cur = json.loads((root / "plugins/wardrobe/.claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
        major, minor, patch = (int(x) for x in cur.split("."))
        new = "%d.%d.0" % (major, minor + 1)
        bump.bump(root, "wardrobe", new, "a test sentence")
        after = _snapshot(root)
        changed = sorted(k for k in after if after[k] != before[k])
        check("bump touches exactly plugin.json and marketplace.json",
              changed == [".claude-plugin/marketplace.json", "plugins/wardrobe/.claude-plugin/plugin.json"], str(changed))
        # line by line: exactly the version lines and the description line
        diff = []
        for k in changed:
            a = before[k].decode("utf-8").splitlines(True)
            b = after[k].decode("utf-8").splitlines(True)
            check("%s keeps its line count and line endings" % k, len(a) == len(b) and
                  all(x.endswith("\r\n") == y.endswith("\r\n") for x, y in zip(a, b)))
            diff += [(k, x.strip()[:40], y.strip()[-60:]) for x, y in zip(a, b) if x != y]
        kinds = sorted((k, x.split(":")[0]) for k, x, _ in diff)
        check("only version and description lines moved", kinds == [
            (".claude-plugin/marketplace.json", '"description"'),
            (".claude-plugin/marketplace.json", '"version"'),
            ("plugins/wardrobe/.claude-plugin/plugin.json", '"version"')], str(kinds))
        mk = json.loads((root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        entry = next(p for p in mk["plugins"] if p["name"] == "wardrobe")
        check("description ends with the Since sentence",
              entry["description"].endswith(" Since %s a test sentence." % new) and entry["version"] == new)
        # controls: each refusal writes nothing
        for bad in ("0.6", "v%s" % new, "01.0.0", cur, "%d.%d.%d" % (major, minor, patch)):
            snap = _snapshot(root)
            try:
                bump.bump(root, "wardrobe", bad, "x")
                refused = False
            except bump.Refused:
                refused = True
            check("control: bump refuses version %r and writes nothing" % bad, refused and _snapshot(root) == snap)
        try:
            bump.bump(root, "no-such-plugin", "9.9.9", "x")
            refused = False
        except bump.Refused:
            refused = True
        check("control: bump refuses an unknown plugin", refused)
        code = subprocess.run([sys.executable, str(HERE / "bump.py"), "wardrobe", "nope", "x", "--repo", str(root)],
                              capture_output=True, text=True).returncode
        check("control: bump.py exits non-zero on a bad version", code == 1, "exit %s" % code)


# --- end to end with a fake Blender ---------------------------------------------------------------

def _fake_blender():
    """Called as `blender -b --factory-startup --python <fixture> -- out=<dir>`."""
    argv = sys.argv
    fixture = Path(argv[argv.index("--python") + 1]).stem
    out = Path([a for a in argv if a.startswith("out=")][0][4:])
    delays = json.loads(os.environ.get("FAKE_DELAYS", "{}"))
    time.sleep(delays.get(fixture, 0.1))
    with open(REPO / "tests" / "golden" / (fixture + ".json"), encoding="utf-8") as fh:
        report = json.load(fh)
    if fixture in os.environ.get("FAKE_BREAK", "").split(","):
        report["report"]["_fake_moved"] = 1
        report["report"]["fake_moved"] = 1
    out.mkdir(parents=True, exist_ok=True)
    with open(out / (fixture + ".json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh)
    return 0


def _run_fake(tmp, names, env_extra, extra_args=()):
    if os.name == "nt":
        fake = Path(tmp) / "blender.cmd"
        fake.write_text('@"%s" "%s" --fake-blender %%*\r\n' % (sys.executable, Path(__file__).resolve()))
    else:
        fake = Path(tmp) / "blender"
        fake.write_text('#!/bin/sh\nexec "%s" "%s" --fake-blender "$@"\n' % (sys.executable, Path(__file__).resolve()))
        fake.chmod(0o755)
    env = dict(os.environ, **env_extra)
    diff = Path(tmp) / "out.diff"
    proc = subprocess.run([sys.executable, str(HERE / "regress.py"), "--blender", str(fake), "--jobs", "2",
                           "--diff", str(diff), "--only", *names, *extra_args],
                          capture_output=True, text=True, env=env)
    return proc, diff


def test_end_to_end():
    names = ["starfish", "rabbit", "review_sheet"]
    # rabbit is slowest; with --jobs 2 the other two finish first and must be printed first
    delays = {"rabbit": 4.0, "starfish": 0.5, "review_sheet": 0.5}
    saved = dict(regress.DURATIONS)
    with tempfile.TemporaryDirectory(prefix="rgt-") as tmp:
        proc, diff = _run_fake(tmp, names, {"FAKE_DELAYS": json.dumps(delays)})
        lines = proc.stdout.strip().splitlines()
        check("passing run: last line is REGRESS DONE exit=0, 3 fixtures ok",
              lines[-1] == "REGRESS DONE exit=0, 3 fixtures ok" and proc.returncode == 0,
              "exit %s, last %r\n%s" % (proc.returncode, lines[-1:], proc.stderr[-2000:]))
        order = [l.split()[1] for l in lines if l.startswith("  ok ")]
        check("results printed as they finish (rabbit last)", order[-1:] == ["rabbit"], str(order))
        sched = [l for l in lines if l.startswith("order (longest first):")]
        expect = regress.schedule(names)
        check("run order is the schedule", sched and sched[0].split(":", 1)[1].split() == expect, str(sched))
        check("the diff file is written and its path printed",
              diff.is_file() and any(str(diff) in l for l in lines))
        # control: a deliberately failing run
        proc, diff = _run_fake(tmp, names, {"FAKE_DELAYS": json.dumps(delays), "FAKE_BREAK": "starfish"})
        lines = proc.stdout.strip().splitlines()
        check("control: failing run ends REGRESS DONE exit=1, 2 fixtures ok",
              lines[-1] == "REGRESS DONE exit=1, 2 fixtures ok" and proc.returncode == 1,
              "exit %s, last %r" % (proc.returncode, lines[-1:]))
        text = diff.read_text(encoding="utf-8") if diff.is_file() else ""
        check("control: the diff file holds the moved key", "starfish" in text and "fake_moved" in text, text[:300])
        # --keep: the deepest path this run wrote is measured afterwards and warned on near MAX_PATH
        for label, width, want in (("long", 0, True), ("control: short", 10, False)):
            keep = Path(tmp) / "k"
            if not width:
                width = 232 - len(str(keep))          # + "\starfish\starfish.json" = 255 characters
            keep = Path(str(keep) + "x" * max(1, width))
            proc, _ = _run_fake(tmp, ["starfish"], {"FAKE_DELAYS": "{}"}, ["--keep", str(keep)])
            lines = proc.stdout.splitlines()
            at = [i for i, l in enumerate(lines) if l.startswith("deepest output:")]
            warned = bool(at) and at[0] + 1 < len(lines) and lines[at[0] + 1].startswith("WARNING: --keep")
            check("%s --keep: deepest output measured, warned=%s" % (label, want), bool(at) and warned == want,
                  proc.stdout[-600:])
            shutil.rmtree("\\\\?\\" + str(keep) if os.name == "nt" else keep, ignore_errors=True)
        # an argparse error still ends with the line
        proc = subprocess.run([sys.executable, str(HERE / "regress.py"), "--only", "no_such_fixture"],
                              capture_output=True, text=True)
        check("an argument error ends REGRESS DONE exit=2", proc.stdout.strip().splitlines()[-1:] ==
              ["REGRESS DONE exit=2, 0 fixtures ok"], proc.stdout[-300:])
    regress.DURATIONS.update(saved)


def main():
    if "--fake-blender" in sys.argv:
        return _fake_blender()
    for t in (test_quick, test_pieces, test_bump, test_end_to_end):
        print(t.__name__, flush=True)
        t()
    print("\n%s" % ("%d FAILED: %s" % (len(FAILED), ", ".join(FAILED)) if FAILED else "all passed"))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
