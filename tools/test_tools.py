#!/usr/bin/env python3
"""Checks for tools/regress.py, tools/bump.py and tools/scratch_project.py that need no Blender. Each check has a control that
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


# --- scratch_project.py and specs safe to copy ------------------------------------------------------

def _tree(root):
    """Every file under root by content: what 'untouched' is measured against."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


def _fake_godot(tmp, text, code=0):
    n = len(list(Path(tmp).glob("godot_*")))
    if os.name == "nt":
        fake = Path(tmp) / ("godot_%d.cmd" % n)
        fake.write_text("@echo %s\r\n@exit /b %d\r\n" % (text, code))
    else:
        fake = Path(tmp) / ("godot_%d" % n)
        fake.write_text("#!/bin/sh\necho '%s'\nexit %d\n" % (text, code))
        fake.chmod(0o755)
    return str(fake)


def _fake_spec(cid, blend):
    return ('[character]\nid = "%s"\nname = "%s"\n\n[body]\nsex = "male"\n\n[moves]\ngaits = { Walk = 0.2 }\n\n'
            '[export]\ndir = "assets/%s"\nres_dir = "res://assets/%s"\nblend = "%s"\n' % (cid, cid.title(), cid, cid, blend))


def _fake_game(tmp):
    game, blends = Path(tmp) / "game", Path(tmp) / "realblends"
    files = {
        "project.godot": 'config_version=5\n\n[application]\n\nrun/main_scene="res://main.tscn"\n',
        "main.tscn": '[ext_resource type="PackedScene" path="res://assets/not_copied.glb" id="1"]\n',
        "figure.tscn": '[ext_resource type="Script" path="res://figure.gd" id="1"]\n',
        "figure.gd": 'const F = "res://assets/fig/%s.glb"\nconst A = preload("res://addons/mine/y.gd")\n',
        "characters/fig.toml": _fake_spec("fig", "fig.blend"),
        "characters/abs.toml": _fake_spec("abs", "%s/abs.blend" % blends.as_posix()),
        "characters/other.toml": _fake_spec("other", "%s/other.blend" % blends.as_posix()),
        "assets/save_guard.py": "# guard\n", "assets/humans/build_human.py": "# human\n",
        "assets/belle/build_belle.py": "# belle\n", "assets/fig/fig.glb": "glb", "assets/fig/review/sheet.png": "png",
        "assets/other/other.glb": "glb", "addons/lookdev/x.gd": "# the game's copy\n", "addons/mine/y.gd": "# y\n",
    }
    for rel, text in files.items():
        (game / rel).parent.mkdir(parents=True, exist_ok=True)
        (game / rel).write_text(text, encoding="utf-8", newline="\n")
    blends.mkdir()
    for n in ("fig", "abs", "other"):
        (blends / (n + ".blend")).write_bytes(b"BLENDER-" + n.encode())
    lib = Path(tmp) / "library"
    (lib / "items").mkdir(parents=True)
    (lib / "index.json").write_text("{}")
    return game, blends, lib


def test_scratch_project():
    import scratch_project as sp
    spec = sp._spec_module(REPO)
    tmp = tempfile.mkdtemp(prefix="tsp_")
    saved_env = os.environ.pop("BLEND_DIR", None)
    try:
        # spec.resolve_blend / inside, without Blender
        proj = os.path.join(tmp, "p")
        absolute = "C:/x/y.blend" if os.name == "nt" else "/x/y.blend"
        check("absolute blend kept", spec.resolve_blend(absolute, proj) == os.path.normpath(absolute))
        check("relative blend under the project", spec.resolve_blend("y.blend", proj) == os.path.join(proj, "y.blend"))
        os.environ["BLEND_DIR"] = os.path.join(tmp, "bd")
        check("relative blend under BLEND_DIR when set", spec.resolve_blend("y.blend", proj) ==
              os.path.join(tmp, "bd", "y.blend"))
        check("save roots: project and BLEND_DIR", spec.save_roots(proj) == [os.path.normpath(proj),
                                                                             os.path.join(tmp, "bd")])
        os.environ.pop("BLEND_DIR")
        check("inside the project", spec.inside(os.path.join(proj, "sub", "y.blend"), [proj]))
        sibling = os.path.join(tmp, "p2", "y.blend")
        check("a sibling whose name starts with the project's is outside", not spec.inside(sibling, [proj]))
        check("control: a prefix test would call that sibling inside", sibling.startswith(proj))
        check("../ out of the project is outside", not spec.inside(spec.resolve_blend("../q/y.blend", proj), [proj]))
        text, old = sp.rewrite_blend('[export]\ndir = "a"\nblend = "C:/B/x.blend"  # c\n')
        check("absolute blend rewritten to its file name",
              old == "C:/B/x.blend" and 'blend = "x.blend"  # c' in text, text)
        check("control: a relative blend is left alone",
              sp.rewrite_blend('blend = "x.blend"\n') == ('blend = "x.blend"\n', None))

        game, blends, lib = _fake_game(tmp)
        before, before_blends = _tree(game), _tree(blends)
        out = Path(tmp) / "scratch"
        clean = _fake_godot(tmp, "Godot Engine v4.7 import ok")
        done = sp.make(out, who=["fig", "abs"], game=game, game_blend_dir=str(blends), library=str(lib),
                       godot=clean, blender="blender", log=lambda m: None)
        check("layout: characters, build scripts, the chosen export, addons, scenes",
              all((out / r).is_file() for r in ("characters/fig.toml", "characters/other.toml", "assets/save_guard.py",
                                                "assets/humans/build_human.py", "assets/belle/build_belle.py",
                                                "assets/fig/fig.glb", "addons/mine/y.gd", "figure.tscn", "figure.gd")))
        check("review/ folders are not copied", not (out / "assets/fig/review").exists())
        check("a character not chosen: its export is not copied", not (out / "assets/other").exists())
        check("the chosen blends copied into blends/, the other not",
              sorted(p.name for p in (out / "blends").glob("*.blend")) == ["abs.blend", "fig.blend"])
        check("blends/ and the library carry .gdignore",
              (out / "blends/.gdignore").is_file() and (out / "humanform_library/.gdignore").is_file())
        check("a relative spec is copied byte for byte",
              (out / "characters/fig.toml").read_bytes() == (game / "characters/fig.toml").read_bytes())
        check("absolute specs rewritten, chosen or not", sorted(done["rewritten"]) == ["abs", "other"],
              str(done["rewritten"]))
        bd = str(out / "blends")
        where = {t.stem: spec.resolve_blend(spec.load(str(t)).export.blend, str(out), blend_dir_override=bd)
                 for t in (out / "characters").glob("*.toml")}
        check("every copied spec's blend resolves under the copy",
              all(spec.inside(p, [str(out)]) for p in where.values()), str(where))
        real = {t.stem: spec.resolve_blend(spec.load(str(t)).export.blend, str(out), blend_dir_override=bd)
                for t in (game / "characters").glob("*.toml")}
        check("control: the game's own specs, resolved the same way, reach outside the copy",
              not all(spec.inside(p, [str(out)]) for p in real.values()), str(real))
        check("the game is untouched", _tree(game) == before)
        check("the game's blends are untouched", _tree(blends) == before_blends)
        (game / "characters/fig.toml").write_text("changed")
        check("control: the untouched check sees an edit", _tree(game) != before)
        (game / "characters/fig.toml").write_bytes(before["characters/fig.toml"])
        env = dict(re.findall(r"^export (\w+)='([^']*)'$", (out / "env.sh").read_text(), re.M))
        check("env.sh: PROJECT and BLEND_DIR are the copy",
              env.get("PROJECT") == sp.fwd(out) and env.get("BLEND_DIR") == sp.fwd(out / "blends"), str(env))
        scripts = {k: v for k, v in env.items() if k.endswith("_SCRIPTS")}
        check("env.sh: RA/HF/FT/WD/CP/LD_SCRIPTS at the checkout, each a folder",
              sorted(scripts) == ["CP_SCRIPTS", "FT_SCRIPTS", "HF_SCRIPTS", "LD_SCRIPTS", "RA_SCRIPTS", "WD_SCRIPTS"]
              and all(v.startswith(sp.fwd(REPO) + "/") and os.path.isdir(v) for v in scripts.values()), str(scripts))
        check("env.sh: HUMANFORM_LIBRARY is a copy of the library",
              env.get("HUMANFORM_LIBRARY") == sp.fwd(out / "humanform_library")
              and (out / "humanform_library/index.json").is_file())
        ps1 = (out / "env.ps1").read_text()
        check("env.ps1 sets the same variables", all("$env:%s = '%s'" % kv in ps1 for kv in env.items()))
        check("addons this repo keeps come from the checkout",
              not (out / "addons/lookdev/x.gd").exists() and (out / "addons/lookdev").is_dir()
              and "lookdev" in done["addons_from_checkout"])
        check("a scene naming a file the copy lacks is left out, with the main scene line",
              not (out / "main.tscn").exists() and "main_scene" not in (out / "project.godot").read_text()
              and done["main_scene"] is None)
        check("control: a scene whose files are all there is kept (a % format path is not a reference)",
              (out / "figure.tscn").exists() and (out / "figure.gd").exists())
        build_sh = (out / "build.sh").read_text()
        check("build.sh sources env.sh and picks the build script",
              '. "$HERE/env.sh"' in build_sh and "build_human.py" in build_sh and "build_belle.py" in build_sh)
        check("the printed command is build.sh with the first figure",
              done["build"] == "bash %s/build.sh fig" % sp.fwd(out), done["build"])

        def refused(**kw):
            args = dict(out=Path(tmp) / "s2", who=["fig"], game=game, game_blend_dir=str(blends), library=str(lib),
                        godot=clean, blender="blender", log=lambda m: None)
            args.update(kw)
            try:
                sp.make(**args)
                return None
            except sp.Refused as exc:
                return str(exc)
        check("refuses a folder that is not empty", "not empty" in (refused(out=out) or ""))
        check("refuses a folder inside the game", "inside the game" in (refused(out=game / "scratch") or ""))
        check("refuses an unknown character", "no characters/" in (refused(who=["nobody"]) or ""))
        bad = _fake_godot(tmp, "ERROR: Failed loading resource: res://x.glb")
        why = refused(out=Path(tmp) / "s3", godot=bad)
        check("an import that prints ERROR is refused, naming the line", "Failed loading resource" in (why or ""),
              str(why))
        check("control: the same copy with a clean import passes", refused(out=Path(tmp) / "s4") is None)
        crash = _fake_godot(tmp, "nothing said", code=3)
        check("an import that exits non-zero is refused", "exit 3" in (refused(out=Path(tmp) / "s5", godot=crash) or ""))
        check("--force copies over a folder that is not empty", refused(out=out, force=True) is None)
    finally:
        if saved_env is not None:
            os.environ["BLEND_DIR"] = saved_env
        else:
            os.environ.pop("BLEND_DIR", None)
        shutil.rmtree(tmp, ignore_errors=True)


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
    for t in (test_quick, test_pieces, test_bump, test_scratch_project, test_end_to_end):
        print(t.__name__, flush=True)
        t()
    print("\n%s" % ("%d FAILED: %s" % (len(FAILED), ", ".join(FAILED)) if FAILED else "all passed"))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
