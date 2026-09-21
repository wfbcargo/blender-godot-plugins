#!/usr/bin/env python3
"""Rebuild every fixture headless and compare it against its golden.

    python tools/regress.py                      # all fixtures, against tests/golden/
    python tools/regress.py --only rabbit        # one
    python tools/regress.py --plugins <checkout> # exercise another checkout of the plugins
    python tools/regress.py --update             # rewrite the goldens, then review the diff
    python tools/regress.py --twice              # build each fixture twice; the builds must agree
    python tools/regress.py --godot <project>    # then play the exports in Godot's verifiers
    python tools/regress.py --quick              # only the fixtures the changed plugins reach
    python tools/regress.py --quick --dry-run    # say what would run, and why, and stop

The longest fixtures start first (DURATIONS, measured), each result is printed as soon as it is in,
the full diff of every changed key goes to a file whose path is printed, and every run ends with
exactly one line `REGRESS DONE exit=N, K fixtures ok`, which is what a background wait should match.

`--quick` compares this branch with `main` (`git diff --name-only main...HEAD`, plus uncommitted and
untracked files) and runs the fixtures that reach a changed plugin - through `H.use` in the fixture
or through one plugin importing another - or whose own fixture, helper or golden changed. A change to
tools/ or the shared harness runs everything; documentation runs nothing. It prints what it selected
and what it skipped, and why. Run a full `--twice` before merging all the same.

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
every manifest through rig-anything's `verify_moves.gd`, each fixture in GODOT_WARDROBE dressed
and walked by wardrobe's `verify_wardrobe.gd`, each fixture in GODOT_FLESH's body driven round
follow-through's `verify_flesh.gd` courses, each fixture in GODOT_STRANDS's strands swung at
30/60/120/240 fps by `verify_strands.gd` (with controls that must fail), and each fixture in GODOT_LOOKDEV's body looked at by
lookdev's `close-shot` (beside its Blender close set, with a must-fail control) and lookdev's `selftest`. The folder is removed afterwards whatever happens.
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
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"
GOLDEN = REPO / "tests" / "golden"
SCRIPT_VARS = {"RA_SCRIPTS": "rig-anything", "HF_SCRIPTS": "humanform",
               "FT_SCRIPTS": "follow-through", "WD_SCRIPTS": "wardrobe", "CP_SCRIPTS": "character-pipeline",
               "LD_SCRIPTS": "lookdev"}
# The folder under a plugin that holds its importable packages. `scripts` for all but lookdev, whose
# Blender package lives in `blender/` - so `--plugins <checkout>` reached every plugin but that one, and
# a run said it was exercising another checkout while its hair material came from this one.
PACKAGE_DIR = {"lookdev": "blender"}

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

# Seconds one build of each fixture took, measured (see the notebook realism-step0/repo-regress-quick):
# the pool is fed longest first so the two slowest builds never start last and leave one Blender
# idle at the end. Only the order matters. A fixture not listed here is assumed long, so a new one
# starts early rather than at the tail.
DURATIONS = {  # 2026-09-18, `--jobs 2` on main at 5a218d3
    "rabbit": 193, "cricket": 182, "pipeline_muscle": 130, "dressed_presets": 69, "pipeline_woman": 67,
    "dressed_skirts": 55, "flesh_figure": 54, "traced_detail": 53, "rigify_human": 230, "quadruped": 49,
    "mpfb_woman_curvy": 49, "pipeline_ponytail": 40, "dressed_figure": 38, "hair_presets": 36,
    "strand_ponytail": 32, "muscle_definition": 31, "mixamo_names": 21, "skin_detail": 18,
    "review_sheet": 9, "starfish": 6, "pipeline_paths": 28, "asym_meter": 95,
}
UNKNOWN_DURATION = 10 ** 6

# Windows MAX_PATH. A --keep folder whose deepest output nears it breaks renders and glb writes in
# ways that do not say "path too long". DEEPEST_OUTPUT is the longest path under a fixture's output
# folder, relative to the --keep root, measured on a full run; the warning is also raised afterwards
# from what the run actually wrote.
MAX_PATH = 260
PATH_MARGIN = 20
DEEPEST_OUTPUT = 95   # pipeline_woman's review png, 93, plus `a/` under --twice


def _print(*args, **kw):
    """Every line flushed: a run is watched from a background log, and a buffered result is a lost one."""
    kw.setdefault("flush", True)
    print(*args, **kw)


def find_blender():
    if os.environ.get("BLENDER"):
        return os.environ["BLENDER"]
    found = sorted(glob.glob(r"C:/Program Files/Blender Foundation/Blender */blender.exe"))
    return found[-1] if found else (shutil.which("blender") or "blender")


def fixtures():
    return sorted(p.stem for p in FIXTURES.glob("*.py") if not p.name.startswith("_"))


def schedule(names):
    """Longest first by DURATIONS; unmeasured fixtures first of all, then by name."""
    return sorted(names, key=lambda n: (-DURATIONS.get(n, UNKNOWN_DURATION), n))


# --- --quick: which fixtures a change reaches ------------------------------------------------------

def _plugin_packages():
    """{plugin: {top-level importable name}} from each plugin's package folder."""
    out = {}
    for plugin in sorted(set(SCRIPT_VARS.values())):
        root = REPO / "plugins" / plugin / PACKAGE_DIR.get(plugin, "scripts")
        names = set()
        if root.is_dir():
            for p in root.iterdir():
                if p.is_dir() and (p / "__init__.py").is_file():
                    names.add(p.name)
                elif p.suffix == ".py":
                    names.add(p.stem)
        out[plugin] = names
    return out


def plugin_imports():
    """{plugin: {other plugins its sources import}}, scanned from the checkout. Lazy imports count:
    a function that imports wardrobe runs wardrobe's code whenever it is called."""
    packages = _plugin_packages()
    owner = {name: plugin for plugin, names in packages.items() for name in names}
    pattern = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
    graph = {}
    for plugin in packages:
        root = REPO / "plugins" / plugin / PACKAGE_DIR.get(plugin, "scripts")
        found = set()
        for src in (root.rglob("*.py") if root.is_dir() else []):
            try:
                text = src.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            found |= {owner[m] for m in pattern.findall(text) if m in owner}
        graph[plugin] = found - {plugin}
    return graph


def fixture_plugins(name, graph=None):
    """{plugin: how the fixture reaches it}: the plugins its source names (H.use and any *_SCRIPTS it
    reads), then every plugin those import, transitively."""
    graph = plugin_imports() if graph is None else graph
    text = (FIXTURES / (name + ".py")).read_text(encoding="utf-8", errors="replace")
    reach = {SCRIPT_VARS[v]: "uses it" for v in re.findall(r"\b([A-Z]{2}_SCRIPTS)\b", text) if v in SCRIPT_VARS}
    todo = list(reach)
    while todo:
        plugin = todo.pop()
        for other in sorted(graph.get(plugin, ())):
            if other not in reach:
                reach[other] = "%s imports %s" % (plugin, other) if reach[plugin] == "uses it" \
                    else "%s, which imports %s" % (reach[plugin], other)
                todo.append(other)
    return reach


def changed_files(base="main"):
    """Repo-relative paths that differ from `base`: committed on this branch since it left base,
    staged, unstaged and untracked. Renames count both names."""
    def git(*args):
        proc = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError("git %s: %s" % (" ".join(args), proc.stderr.strip()))
        return [l.strip() for l in proc.stdout.splitlines() if l.strip()]
    paths = set(git("diff", "--name-only", "--no-renames", "%s...HEAD" % base))
    paths |= set(git("diff", "--name-only", "--no-renames", "HEAD"))
    paths |= set(git("ls-files", "--others", "--exclude-standard"))
    return sorted(paths)


def select(changed, names=None):
    """What a set of changed paths reaches. Returns (selected {fixture: [reasons]},
    skipped {fixture: reason}, notes [(path, what it selected)])."""
    names = fixtures() if names is None else names
    graph = plugin_imports()
    reach = {n: fixture_plugins(n, graph) for n in names}
    sources = {n: (FIXTURES / (n + ".py")).read_text(encoding="utf-8", errors="replace") for n in names}
    selected, notes = {}, []

    def pick(fixture_names, why):
        for n in fixture_names:
            selected.setdefault(n, []).append(why)
        return fixture_names

    for path in changed:
        parts = path.replace("\\", "/").split("/")
        if "__pycache__" in parts or path.endswith(".pyc"):
            notes.append((path, "nothing (bytecode)"))
        elif parts[0] == "tools":
            pick(names, "shared code: %s" % path)
            notes.append((path, "every fixture (shared code)"))
        elif parts[0] == "plugins" and len(parts) > 2:
            plugin = parts[1]
            hit = [n for n in names if plugin in reach[n]]
            for n in hit:
                selected.setdefault(n, []).append("%s changed (%s)" % (
                    plugin, "the fixture uses it" if reach[n][plugin] == "uses it" else reach[n][plugin]))
            notes.append((path, ", ".join(hit) if hit else "nothing (no fixture reaches %s)" % plugin))
        elif parts[:2] == ["tests", "fixtures"] and len(parts) == 3 and path.endswith(".py"):
            stem = parts[2][:-3]
            if stem.startswith("_"):
                # a helper: every fixture that names it (all of them import _harness)
                hit = pick([n for n in names if re.search(r"\b%s\b" % re.escape(stem), sources[n])],
                           "shared test harness: %s" % path)
                notes.append((path, "every fixture (shared harness)" if len(hit) == len(names)
                              else ", ".join(hit) or "nothing (no fixture names %s)" % stem))
            else:
                hit = pick([stem] if stem in names else [], "its fixture changed")
                notes.append((path, ", ".join(hit) or "nothing (fixture gone)"))
        elif parts[:2] == ["tests", "golden"] and len(parts) == 3 and path.endswith(".json"):
            stem = parts[2][:-5]
            hit = pick([stem] if stem in names else [], "its golden changed")
            notes.append((path, ", ".join(hit) or "nothing (no such fixture)"))
        elif path.endswith(".md") or parts[0] in ("docs", ".claude-plugin") or path in (".gitignore",):
            notes.append((path, "nothing (documentation or marketplace metadata; no fixture reads it)"))
        else:
            pick(names, "unclassified change: %s" % path)
            notes.append((path, "every fixture (not classified, so run everything)"))

    skipped = {}
    for n in names:
        if n not in selected:
            skipped[n] = "reaches only %s, none of which changed" % ", ".join(sorted(reach[n])) \
                if reach[n] else "reaches no plugin"
    return selected, skipped, notes


def volatile(key):
    words = [w for w in re.split(r"[_\W]+", key.lower()) if w]
    if not words or words[-1] in UNITS:
        return False
    return any(w in VOLATILE for w in words)


def volatile_blocks(value, prefix=""):
    """[(dotted key, n)] where a volatile key holds a dict of n entries (a list of paths is fine).
    `flatten` drops the whole block, so a `build_timing` that also held a result is never compared."""
    out = []
    if isinstance(value, dict):
        for k, v in value.items():
            key = "%s.%s" % (prefix, k) if prefix else str(k)
            if volatile(str(k)) and isinstance(v, dict) and v:
                out.append((key, len(v)))
            elif not volatile(str(k)):
                out += volatile_blocks(v, key)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out += volatile_blocks(v, "%s[%d]" % (prefix, i))
    return out


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
        report = json.load(fh)
    # Read now: without --keep the folder is gone by the time the result is printed.
    report["_stage_times"] = stage_times(out)
    report["_deepest"] = deepest_path(out)
    return report, took


def stage_times(out):
    """[(manifest, quality, total_seconds, {stage: seconds})] from every character-pipeline manifest a
    fixture exported: its `build` block records how long each stage took. The pipeline fixtures silence
    the runner's log, so this is the only place a slow stage shows."""
    rows = []
    for p in sorted(out.rglob("*.moves.json")):
        if "_humanform_library" in p.parts:
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                build = json.load(fh).get("build") or {}
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(build, dict) and isinstance(build.get("stage_seconds"), dict):
            rows.append((p.relative_to(out).as_posix(), build.get("quality"), build.get("total_seconds"),
                         build["stage_seconds"]))
    return rows


def deepest_path(root):
    """(length, path) of the longest path under root, as an absolute path string."""
    best = (0, "")
    for dirpath, dirnames, filenames in os.walk(root):
        for f in filenames + dirnames:
            full = os.path.join(dirpath, f)
            if len(full) > best[0]:
                best = (len(full), full)
    return best


def path_warning(keep_root, deepest_rel):
    """A warning line when keep_root plus the deepest relative output nears MAX_PATH, else None."""
    total = len(str(keep_root)) + 1 + deepest_rel
    if deepest_rel and total >= MAX_PATH - PATH_MARGIN:
        return ("WARNING: --keep %s (%d characters) plus the deepest fixture output (%d) is %d characters, "
                "within %d of Windows' %d-character MAX_PATH: renders and glb writes fail there without "
                "saying why. Use a shorter --keep folder." % (keep_root, len(str(keep_root)), deepest_rel,
                                                             total, PATH_MARGIN, MAX_PATH))
    return None


# --godot: the engine side of each fixture. Every `.moves.json` a fixture exports goes through
# rig-anything's MovesController verifier. A fixture named here also has its garment worn by the
# body it was cut from, walked, and counted for holes and poke-through by wardrobe's verifier.
# `garment` may list several files, comma-separated: they are worn together. Each of `controls` is
# run with the same args plus its own and must fail: `cut=` removes a patch of the garment, so a
# check that stops seeing real holes fails the harness.
GODOT_WARDROBE = {
    "dressed_figure": {"body": "figure.glb", "garment": "shirt.glb",
                       "args": ["frames=240", "every=8", "hem=true", "jiggle=true"],
                       "controls": [["cut=0.04"]]},
    "dressed_presets": {"body": "figure.glb", "garment": "sports_top.glb,shorts_mid_thigh.glb",
                        "args": ["frames=240", "every=8", "hem=true", "jiggle=true"]},
    # every=4: a thigh goes through a skirt for a few frames of a stride, and every=8 can step over them.
    # The mini, not the knee skirt: this Figure's walk crosses its feet over the midline and a knee-length
    # hem between the legs is inside a thigh there whatever the colliders do (12 of 1152 vertices, 1.04%,
    # at frame 172 - 8 of them inside a jiggle bone's flesh). The crowd women's walks are 0. rigid=spine
    # skins the skirt to the pelvis alone and colliders=false takes the thigh capsules and the fold off it;
    # the thighs must come through in both.
    "dressed_skirts": {"body": "figure.glb", "garment": "skirtmini.glb",
                       "args": ["frames=240", "every=4", "hem=true", "jiggle=true"],
                       "controls": [["rigid=spine"], ["colliders=false"]]},
    "pipeline_woman": {"body": "fixwoman.glb", "garment": "fixwoman_sportstop.glb,fixwoman_shorts.glb",
                       "args": ["frames=240", "every=8", "hem=true", "jiggle=true"]},
    # the compression pair on the embossed body: cloth eased inside 12 mm of relief, and lifted back
    # over the skin that stood through it, must still leave no hole and no skin showing
    "traced_detail": {"body": "figure.glb", "garment": "top_compressed.glb,shorts_compressed.glb",
                      "args": ["frames=240", "every=8", "hem=true", "jiggle=true"]},
}
# A pipeline fixture whose body carries flesh has it sprung in Godot by follow-through's `verify_flesh.gd`:
# the full course with every check, then each motion alone on its own clip (walk, run; jump needs a Jump
# clip, which only a spec listing that role has) deciding on `within_body` - does any jiggle bone swing
# further than its mass stands out, carrying skin through the body. on_limit's 10% line is drawn on the
# full course and a one-motion course concentrates it, so there it is printed, not decisive. `control`
# raises every region's limit to 2 x its manifest `peak_m` (the flesh block export writes), the failure
# within_body exists for, and must fail - so a check that stops measuring fails the harness.
GODOT_FLESH = {
    "pipeline_woman": {"body": "fixwoman.glb", "manifest": "fixwoman.moves.json",
                       "runs": [("full", []),
                                ("walk", ["course=walk", "require=within_body"]),
                                ("run", ["course=run", "require=within_body"])],
                       "control": ["require=within_body"]},
}
# A fixture whose export carries a strand chain has it swung by follow-through's `verify_strands.gd` at
# 30/60/120/240 fps: rest drift, a kick that settles, a fling at the head and the run kept out of the
# head's skin, a stalled frame capped, and the run's swing within 1.25x across the rates, both as it
# gets going and once settled. The first control steps the strands as before follow-through 0.6.3
# (`legacy_integration=true`: the body's motion not low-passed), whose run swung 68/73/53/53 deg at
# the start and 65/69/53/53 settled here: it must fail, and fail on every FAIL line listed with it
# (a control that failed for something else - a strand in the head - would prove nothing), so a
# verifier that stops telling rates apart in either window fails the harness. The second control keeps
# every other 0.6.3 fix and turns only the low-pass off (`mod=smooth_hz:0`): its run swung 67/52/53/53
# deg at the start (1.28, a thin margin over 1.25) and passes settled (1.21), so it must fail on the
# starting swing only. Each control is (its arguments, the FAIL lines it must print).
GODOT_STRANDS = {
    "pipeline_ponytail": {"body": "ponywoman.glb", "strands": "ponywoman_hair.glb", "args": [],
                          "controls": [(["legacy_integration=true"],
                                        ["starting swing differs across frame rates",
                                         "settled swing differs across frame rates"]),
                                       (["mod=smooth_hz:0"],
                                        ["starting swing differs across frame rates"])]},
}
# A fixture named here has its gait jittered by rig-anything's `verify_jitter.gd`: the per-cycle phase
# and amplitude series' DFA exponent, whether stride timing and arm swing actually vary cycle to cycle
# (and are exactly periodic with jitter off), that the jittered playhead never drifts from the plain one,
# that planted feet travel no further, what it costs per frame, and that a manifest with no `variability`
# key - every character built before the seam - reads as all zeros and off. Two controls, each of which
# must fail and must fail on the lines named with it - a control that failed for some other reason would
# prove nothing. `spectrum=white` is one gaussian per cycle, what a naive randf() gives (it reads DFA 0.50
# against the shipped 0.82), so a DFA check that stops telling a persistent series from a white one fails
# the harness. `naive=1` reads the warp's slope off the clip's own playing phase instead of the
# unjittered one - the implementation a first attempt gives - whose per-cycle bias of about 1.2 x gain^2
# does not telescope (over 400 s study_man's worst gap is 0.494 cycles and the trend fitted through a
# sample a second of it -0.503, both past the 0.216 bound, against 0.134 and +0.042 for the shipped one),
# so a drift check that stops seeing accumulated phase error fails the harness too.
# `also` is a second run that must ALSO pass: `switch=7` changes gait every 7 s for the whole run,
# which is the only thing that drives `jitter_factor`'s clip-change branch more than once. Without
# it the verifier drove one clip from start to finish while a real character changes gait
# constantly, and the branch was wrong: re-anchoring the tracked playhead to the target threw away
# one tracking lag per change, so 17 changes reached a 0.449-cycle gap with a +0.42 trend, past the
# same 0.216 bound (rig-anything 0.35.0 fixes it; `reanchor=target` is that old shape, kept as the
# control). Every other control below covers a check that had none: `spectrum=flat` warps the
# playhead and scales the arm by the same amount every cycle, so the two "it varies" checks must
# fail; `absent_on=0.6` makes a manifest with NO `variability` block resolve to jitter, which is
# what off-by-default must never mean; `lod_m=0` turns the distance gate off; `ctl=legs` points
# `arm_pose` at the thighs so the amplitude modifier builds over the legs - the one thing the
# "arms only, so it cannot add foot skate" argument rules out; `rate=1` uses the bounded offset as
# a playback-RATE multiplier, the other plausible first attempt, which moves the mean stride time;
# `tick=0.25` advances the animation 4 times a second instead of 60, which is what a throttled
# distant character gets, and there the tracking term's one-tick lag is larger than the bound.
GODOT_JITTER = {
    "pipeline_woman": {"manifest": "fixwoman.moves.json",
                       "args": ["cycles=4096", "seconds=40", "long=160"],
                       "also": [["cycles=1024", "seconds=20", "long=400", "switch=7"],
                                ["cycles=1024", "seconds=20", "long=400", "tick=0.0667"]],
                       # (control args, the lines it EXISTS to fail, the lines it is also allowed
                       # to fail). The third list is not a courtesy: every failure a control
                       # produces has to be named, or the control has stopped being one thing.
                       "controls": [(["spectrum=white"], ["phase series DFA alpha",
                                                          "amplitude series DFA alpha"],
                                     # white noise steps the phase where the persistent series
                                     # glides, and the foot pays for it: this same control reads
                                     # 0.0345 m of skate against the shipped 0.0281
                                     ["planted-foot travel is no worse"]),
                                    (["naive=1", "long=400"], ["does not grow with the run"],
                                     ["stays inside the offset bound"]),
                                    (["cycles=1024", "seconds=20", "long=120", "switch=7",
                                      "reanchor=target"],
                                     ["stays inside the offset bound", "does not grow with the run"],
                                     []),
                                    # a tick coarse enough that the tracking term's one-tick lag
                                    # (0.227 cycles at 4 Hz, against 0.0167 at 60) is most of the
                                    # gap. This is where the shipped controller stops holding its
                                    # bound, and it is a control so that the day it holds - the
                                    # `jitter_track_lead` experiment does hold it, at 0.059 - the
                                    # row goes red and the change gets read rather than absorbed.
                                    (["cycles=1024", "seconds=20", "long=400", "tick=0.25"],
                                     ["stays inside the offset bound"], []),
                                    (["cycles=1024", "seconds=16", "long=16", "spectrum=flat"],
                                     ["stride interval varies", "arm swing varies cycle to cycle"],
                                     # a constant series has no fluctuation to detrend (DFA is NaN)
                                     # and sits at its own mean rather than zero
                                     ["phase series DFA alpha", "amplitude series DFA alpha",
                                      "phase series is bounded and centred"]),
                                    (["cycles=1024", "seconds=16", "long=16", "absent_on=0.6"],
                                     ["no `variability` in the shipped manifest",
                                      "the rate factor is exactly 1.0"], []),
                                    (["cycles=1024", "seconds=16", "long=16", "lod_m=0"],
                                     ["LOD: the amplitude modifier runs"], []),
                                    (["cycles=1024", "seconds=16", "long=16", "ctl=legs"],
                                     ["the modifier reaches no leg"],
                                     # the whole point of "arms only": a modifier over the thighs
                                     # reads 0.0465 m of skate against 0.0368 off
                                     ["planted-foot travel is no worse"]),
                                    (["cycles=1024", "seconds=16", "long=16", "rate=1"],
                                     ["mean stride time is unchanged by jitter"],
                                     ["stays inside the offset bound", "does not grow with the run"])]},
}
# A fixture named here has its exports measured LEFT AGAINST RIGHT in Godot by rig-anything's
# `verify_asymmetry.gd` (the meter is `asymmetry_meter.gd`), and the engine's numbers are held against the
# bake-time `variability.measure` numbers the fixture's own report carries for the same clips - read from
# this build's report, never the golden, so it is always one baked clip measured by two engines.
#
# Two imports of each export. `keys`: a copy imported at the clip's own frame rate with Godot's keyframe
# optimizer off, and sampled at exactly those key instants (tick = 1/fps) - the poses the engine plays are
# then Blender's frames to float32 (measured: every bone within 9e-7 m), so what is left between the two
# meters is the meters. That is the run check 1 is gated on, within ASYM_TOL. `game`: the export as the
# game imports it (resampled to 30 fps, keyframe-reduced) and sampled at 60 Hz, the numbers a character
# actually reads in play: its deviation from the bake is printed as free values, and it is gated on the
# verdicts only (stride even; is asymmetric where the golden says so), because resampling a 24 fps clip at
# 30 fps and reducing its keys moves a turnaround by up to a key - 5-23 mm of stride, 1 degree of swing.
#
# `must_fail` names the cases whose "is asymmetric" check MUST FAIL on every clip (and nothing else may
# fail): the asymmetry-0 build and the RA_ASYM_MIRROR=1 build, whose False verdicts are in the golden.
# Because that check is an AND, a control must also read under its floor on EVERY channel (arm swing,
# shoulder dip, lag), one at a time - the golden's `over_floor` - at the keys (at the game's import only
# with ASYM_GAME_CHANNELS, off by default: that import cannot tell the run's shoulder dip apart). Every
# row prints each gated value against its floor, and marks THIN the ones within ASYM_THIN of it.
# The engine's verdict must also equal the golden's for every case. Two more controls, both on `asym`:
# `swap=1` (the meter told +lat is -lat) must invert every ratio (lag: exchange its sides) and flip stance_offset, agree with the
# fixture's own Blender swap, and DISAGREE with asym's Blender numbers - so a comparison blind to sides
# fails the harness; and `poison=1` (the manifest's variability block, arm_pose values, gaits and stance
# spans rewritten before the meter sees them) must reproduce the plain run's numbers exactly, so a meter
# that reads the answer fails the harness. Step length joins "is asymmetric" here, on the Python side:
# its stance offset must MOVE against the zero build's by more than the fixture's STEP_M (asym) and must
# not (mirror).
GODOT_ASYM = {
    "asym_meter": {"cases": ("asym", "zero", "mirror"), "must_fail": ("zero", "mirror"),
                   "swap_of": "asym", "zero": "zero"},
}
# Engine against bake at the keys, per side. Blender rounds lengths and lag to 1e-5 and angles to 1e-3, and
# at the keys the poses agree to 1e-6 m, so lengths and lag get 5e-5 (rounding plus float32). Arm swing
# gets 0.1 degree: the palm point sits half a hand past the wrist and a leaf hand's length is not in the
# file - the meter takes half its forearm (0.100 m against the Figure's 0.106), and a centimetre of hand
# moves a walk's swing by about 0.07 degree (measured: -0.05 / -0.06 on the walk, +0.01 on the run).
ASYM_TOL = {"arm_swing_deg": 0.1, "step_length_m": 5e-5, "stride_m": 5e-5, "shoulder_dip_m": 5e-5,
            "lag_cycles": 5e-5, "stance_offset_m": 5e-5}
ASYM_KEYS = "_keys"
# A fixture named here has its body looked at in Godot by lookdev's `close-shot` (the head, eye and hand
# views and full, under one preset, beside the fixture's own Blender close set from the review stage when
# it wrote one), and must pass every tile check; each of `controls` is the same run with its own args and
# must fail - a camera moved off its subject - so a tile check that stops measuring fails the harness. The
# first fixture here also runs `lookdev.mjs selftest` on its body: lookdev's own controls.
# `edges` runs `lookdev.mjs edges` on the body's hands (with and without the skin's transmittance): it must
# draw no lines, and its control - humanform 0.12's transmittance (skin mode, 1 cm, full strength) put back
# with --material-set - must fail EDGE_LINES, so an edge check that stops seeing the lines fails the harness.
GODOT_LOOKDEV = {
    "pipeline_woman": {"body": "fixwoman.glb",
                       "views": "face,eyes,face_3q,head_side,head_back,hand_palm.L,hand_back.L,full",
                       "presets": "clear_midday",
                       "controls": [["--views", "face", "--aim-offset", "face=0,-0.12,0"]],
                       "edges": {"views": "hands", "presets": "clear_midday",
                                 "control": ["subsurf_scatter_transmittance_depth=0.01",
                                             "subsurf_scatter_transmittance_color=[0.92,0.42,0.30,1.0]"]},
                       "eyes": True},
}
LOOKDEV_MJS = REPO / "plugins" / "lookdev" / "bin" / "lookdev.mjs"


def _strip_eye_preset(src, dst):
    """A copy of `src` with the eye preset taken back off: no `lookdev` extras on the eye materials and the
    old 0.01 pupil. This is exactly what every character's eyes were before lookdev 0.12.0, so `lookdev eyes`
    must fail on it - a check that stops seeing a preset-less eye then fails the harness."""
    buf = src.read_bytes()
    jlen = struct.unpack_from("<I", buf, 12)[0]
    g = json.loads(buf[20:20 + jlen].decode("utf-8"))
    for m in g.get("materials", []):
        ld = (m.get("extras") or {}).get("lookdev") or {}
        if ld.get("preset") != "eye":
            continue
        m.pop("extras", None)
        if ld.get("part") == "pupil":
            pbr = m.setdefault("pbrMetallicRoughness", {})
            pbr["baseColorFactor"] = [0.01, 0.01, 0.01, 1.0]
    js = json.dumps(g, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    rest = buf[20 + jlen:]
    dst.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + len(rest))
                    + struct.pack("<II", len(js), 0x4E4F534A) + js + rest)


def _node(args, timeout=900):
    node = shutil.which("node") or "node"
    try:
        proc = subprocess.run([node, str(LOOKDEV_MJS), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 99, "cannot run node %s: %s" % (LOOKDEV_MJS.name, exc)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _run_lookdev(godot, project, where, src, out, name, selftest):
    """GODOT_LOOKDEV's close-shot runs on one fixture's body, and lookdev's selftest: [(check, passed, detail)]."""
    spec = GODOT_LOOKDEV[name]
    body = sorted(where.rglob(spec["body"]))
    if not body:
        return [("close-shot %s" % name, False, "the fixture did not export %s" % spec["body"])]
    glb = "res://" + body[0].relative_to(project).as_posix()
    # the fixture's own Blender close set (review/<id>/close/, not the stage test's close_control/)
    blender = sorted(p.parent for p in src.rglob("close.json") if p.parent.name == "close")
    base = ["close-shot", "--project", str(project), "--godot", str(godot), "--glb", glb,
            "--presets", spec["presets"]]
    rows = []
    runs = [("close-shot %s" % name, ["--views", spec["views"]] + (["--pair-blender", str(blender[0])] if blender else []), True)]
    runs += [("close-shot %s %s (must fail)" % (name, " ".join(c[2:] if c[0] == "--views" else c)), c, False)
             for c in spec.get("controls", [])]
    for k, (label, args, should_pass) in enumerate(runs):
        o = out / ("close_%d" % k)
        code, text = _node(base + args + ["--out", str(o)])
        try:
            with open(o / "close.json", encoding="utf-8") as fh:
                rep = json.load(fh)
        except (OSError, ValueError):
            rows.append((label, False, "no close.json, exit %s: %s" % (code, " | ".join(text.strip().splitlines()[-3:]))))
            continue
        passed = code == 0 and not rep.get("failures")
        pair = rep.get("pair_blender") or {}
        detail = "exit %s, %d tiles, %d failed%s; sheet %s" % (
            code, len(rep.get("tiles", [])), len(rep.get("failures", [])),
            (", Blender pair %d view(s), none for %s" % (len(pair.get("paired", [])),
                                                         ",".join(u["view"] for u in pair.get("unpaired", [])) or "-"))
            if pair else ", no Blender close set to pair", rep.get("sheet"))
        detail += "".join("\n            " + f for f in rep.get("failures", [])[:8])
        rows.append((label, passed == should_pass, detail))
    edges = spec.get("edges")
    if edges:
        for label, sets, should_pass in (("edges %s" % name, [], True),
                                         ("edges %s old transmittance (must fail)" % name, edges["control"], False)):
            o = out / ("edges_%d" % int(not should_pass))
            args = ["edges", "--project", str(project), "--godot", str(godot), "--glb", glb, "--views", edges["views"],
                    "--presets", edges["presets"], "--out", str(o)]
            for m in sets:
                args += ["--material-set", m]
            code, text = _node(args)
            try:
                with open(o / "edges.json", encoding="utf-8") as fh:
                    rep = json.load(fh)
            except (OSError, ValueError):
                rows.append((label, False, "no edges.json, exit %s: %s" % (code, " | ".join(text.strip().splitlines()[-3:]))))
                continue
            lined = [t for t in rep.get("tiles", []) if t.get("fails")]
            passed = code == 0 and not lined
            worst = max(rep.get("tiles", []), key=lambda t: t.get("lines_per_mille", 0), default={})
            detail = "exit %s, %d tiles, %d with lines; worst %s %s %.2f per mille (ratio %.2f)" % (
                code, len(rep.get("tiles", [])), len(lined), worst.get("preset"), worst.get("view"),
                worst.get("lines_per_mille", 0), worst.get("worst_ratio", 0))
            if should_pass:
                rows.append((label, passed, detail))
            else:
                rows.append((label, code == 1 and bool(lined), detail))
    if spec.get("eyes"):
        stripped = out / "eyes_control.glb"
        try:
            _strip_eye_preset(body[0], stripped)
        except (OSError, ValueError, KeyError, struct.error) as e:
            rows.append(("eyes %s (control)" % name, False, "could not make the control: %s" % e))
            stripped = None
        for label, target, should_pass in (("eyes %s" % name, body[0], True),
                                           ("eyes %s preset stripped (must fail)" % name, stripped, False)):
            if target is None:
                continue
            code, text = _node(["eyes", str(target), "--json"])
            try:
                rep = json.loads(text[text.index("{"):text.rindex("}") + 1])
            except ValueError:
                rows.append((label, False, "no json, exit %s: %s" % (code, " | ".join(text.strip().splitlines()[-3:]))))
                continue
            fails = rep.get("failures", [])
            detail = "exit %s, parts %s, iris/pupil %sx, limbal %sx%s" % (
                code, ",".join(rep.get("found", [])), rep.get("iris_pupil_ratio"), rep.get("limbal_share"),
                "".join(chr(10) + " " * 12 + f for f in fails[:4]))
            rows.append((label, (code == 0 and not fails) if should_pass else (code == 1 and bool(fails)), detail))
    if selftest:
        code, text = _node(["selftest", "--project", str(project), "--godot", str(godot), "--glb", glb,
                            "--out", str(out / "selftest")])
        verdict = [l for l in text.splitlines() if l.startswith("lookdev selftest")]
        bad = [l for l in text.splitlines() if l.startswith("FAIL ")]
        rows.append(("lookdev selftest", code == 0 and bool(verdict) and "PASSED" in verdict[-1],
                     (verdict[-1] if verdict else "no verdict, exit %s" % code)
                     + "".join("\n            " + b[:200] for b in bad[:8])))
    return rows


# The Godot addons the verifiers load from the project, and where this repo keeps each one.
GODOT_ADDONS = {"rig_anything": "rig-anything", "wardrobe": "wardrobe", "follow_through": "follow-through",
                "lookdev": "lookdev"}
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
    results, manifests, wardrobe, flesh, strands, lookdev, jitter = [], [], [], [], [], [], []
    asym = []
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
            if name in GODOT_FLESH:
                flesh.append(name)
            if name in GODOT_STRANDS:
                strands.append(name)
            if name in GODOT_JITTER:
                jitter.append(name)
            if name in GODOT_LOOKDEV:
                lookdev.append(name)
            if name in GODOT_ASYM:
                _stage_asym_keys(src, dst, name)
                asym.append(name)
        if not (manifests or wardrobe or flesh or strands or lookdev or jitter or asym):
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
            runs = [("verify_wardrobe %s" % name, spec["args"], True)]
            runs += [("verify_wardrobe %s %s (must fail)" % (name, " ".join(c)), spec["args"] + c, False)
                     for c in spec.get("controls", [])]
            for label, args, should_pass in runs:
                code, out = _godot(godot, project, "--fixed-fps", "60", "-s", "res://addons/wardrobe/verify_wardrobe.gd",
                                   "--", "body=" + res["body"], "garment=" + res["garment"], *args)
                line = [l for l in out.splitlines() if l.startswith("WD_RESULT ")]
                if not line:
                    results.append((label, False, "no WD_RESULT, exit %s" % code))
                    continue
                r = json.loads(line[-1][len("WD_RESULT "):])
                results.append((label, bool(r.get("passed")) == should_pass,
                                "holes %.3f%% (occluded %s, coincident %s) poke %.3f%% over %s frames%s" % (
                                    100 * r.get("holes_frac", 0), r.get("occluded_worst"), r.get("coincident_worst"),
                                    100 * r.get("poke_frac", 0), r.get("frames"),
                                    "".join("\n            " + p for p in r.get("problems", [])))))
        for name in flesh:
            results += _run_flesh(godot, project, stage / name, name)
        if flesh:
            results += _run_jiggle_selftest(godot, project)
        for name in strands:
            results += _run_strands(godot, project, stage / name, name)
        for name in jitter:
            results += _run_jitter(godot, project, stage / name, name)
        for name in asym:
            results += _run_asym(godot, project, stage / name, out_root / name, name)
        for k, name in enumerate(lookdev):
            results += _run_lookdev(godot, project, stage / name, out_root / name, out_root / "_lookdev" / name,
                                    name, selftest=k == 0)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return results


def _run_flesh(godot, project, where, name):
    """GODOT_FLESH's runs on one fixture's body: [(check, passed, detail)]."""
    spec = GODOT_FLESH[name]
    body = sorted(where.rglob(spec["body"]))
    manifest = sorted(where.rglob(spec["manifest"]))
    if not body or not manifest:
        return [("verify_flesh %s" % name, False, "the fixture did not export %s and %s" % (spec["body"], spec["manifest"]))]
    with open(manifest[0], encoding="utf-8") as fh:
        block = json.load(fh).get("flesh") or {}
    regions = block.get("regions") or []
    if not regions:
        return [("verify_flesh %s" % name, False, "its manifest has no flesh block with regions: %s" % block)]
    scene = "res://" + body[0].relative_to(project).as_posix()
    raised = ",".join("%s:%.4f" % (r["name"], 2.0 * float(r["peak_m"])) for r in regions)
    runs = [("verify_flesh %s %s" % (name, label), args, True) for label, args in spec["runs"]]
    runs.append(("verify_flesh %s limits=2x peak_m (must fail)" % name, spec["control"] + ["limits=" + raised], False))
    out_rows = []
    for label, args, should_pass in runs:
        code, out = _godot(godot, project, "--fixed-fps", "60", "-s", "res://addons/follow_through/verify_flesh.gd",
                           "--", "scene=" + scene, *args)
        reports = [json.loads(l[len("FT_FLESH_LIMITS "):]) for l in out.splitlines() if l.startswith("FT_FLESH_LIMITS ")]
        verdict = [l for l in out.splitlines() if l.startswith("FT_SUMMARY")]
        if not reports or not verdict:
            out_rows.append((label, False, "no FT_FLESH_LIMITS / FT_SUMMARY, exit %s: %s"
                             % (code, " | ".join(out.strip().splitlines()[-3:]))))
            continue
        passed = code == 0 and "PASSED" in verdict[-1]
        rows = []
        for rep in reports:
            for rname, g in sorted(rep["regions"].items()):
                rows.append("%s peak %.3f / limit %.3f / stands %.3f, on limit %.1f%%%s" % (
                    rname, g["peak_offset_m"], g["max_offset_m"], g["peak_m"], 100 * g["on_limit_share"],
                    "" if not g.get("advisory") else " (advisory: %s)" % ",".join(g["advisory"])))
            rows += ["FAILED " + f for f in rep.get("failures", [])] + ["PROBLEM " + p for p in rep.get("problems", [])]
        out_rows.append((label, passed == should_pass,
                         verdict[-1] + "".join("\n            " + r for r in rows[:12])))
    return out_rows


def _run_jiggle_selftest(godot, project):
    """follow-through's jiggle_selftest.gd: the spring's shape kicked and timed at three frame rates, and the linear
    spring (`down_ratio=1`) as the control, which must fail on `down_up`: [(check, passed, detail)]."""
    rows = []
    for label, args, should_pass in (("jiggle spring selftest", [], True),
                                     ("jiggle spring selftest down_ratio=1 (must fail)", ["down_ratio=1"], False)):
        code, out = _godot(godot, project, "-s", "res://addons/follow_through/jiggle_selftest.gd", "--", *args)
        verdict = [l for l in out.splitlines() if l.startswith("FT_SUMMARY")]
        line = [l for l in out.splitlines() if l.startswith("FT_JIGGLE_SELFTEST ")]
        if not verdict or not line:
            rows.append((label, False, "no FT_JIGGLE_SELFTEST / FT_SUMMARY, exit %s: %s"
                         % (code, " | ".join(out.strip().splitlines()[-3:]))))
            continue
        r = json.loads(line[-1][len("FT_JIGGLE_SELFTEST "):])
        passed = code == 0 and "PASSED" in verdict[-1]
        fails = r.get("failures", [])
        if not should_pass and not any(f.startswith("down_up") for f in fails):
            passed = True            # failed, but not on the spring's shape: that is not the control failing
        detail = verdict[-1] + "".join("\n            %s fps: below/above %s, ap/side %s" % (k, v.get("down_up"), v.get("ap_side"))
                                       for k, v in sorted(r.get("rates", {}).items())) + "".join("\n            " + f for f in fails[:4])
        rows.append((label, passed == should_pass, detail))
    return rows


def _run_jitter(godot, project, where, name):
    """GODOT_JITTER's run on one fixture's manifest and its must-fail control: [(check, passed, detail)]."""
    spec = GODOT_JITTER[name]
    found = sorted(where.rglob(spec["manifest"]))
    if not found:
        return [("verify_jitter %s" % name, False, "the fixture did not export %s" % spec["manifest"])]
    res = "manifests=res://" + found[0].relative_to(project).as_posix()
    rows = []
    runs = [("verify_jitter %s" % name, spec["args"], True, [], [])]
    runs += [("verify_jitter %s %s" % (name, " ".join(a)), spec["args"] + a, True, [], [])
             for a in spec.get("also", [])]
    runs += [("verify_jitter %s %s (must fail)" % (name, " ".join(ctl)), spec["args"] + ctl, False, must, allowed)
             for ctl, must, allowed in spec["controls"]]
    for label, args, should_pass, must, allowed in runs:
        code, out = _godot(godot, project, "--fixed-fps", "60", "-s",
                           "res://addons/rig_anything/verify_jitter.gd", "--", res, *args)
        verdict = [l for l in out.splitlines() if l.startswith("RA_JIT VERIFY")]
        line = [l for l in out.splitlines() if l.startswith("RA_JITTER ")]
        if not verdict or not line:
            rows.append((label, False, "no RA_JITTER / RA_JIT VERIFY, exit %s: %s"
                         % (code, " | ".join(out.strip().splitlines()[-3:]))))
            continue
        r = json.loads(line[-1][len("RA_JITTER "):])
        passed = code == 0 and "PASSED" in verdict[-1]
        fails = [l.split("FAIL", 1)[1].strip() for l in out.splitlines() if l.startswith("RA_JIT  FAIL")]
        if not should_pass:
            # A control has to fail on ITS OWN line, and on nothing the spec has not named. The
            # first half was here; the second was claimed in a report and not enforced, and two
            # controls did quietly fail extra lines (`spectrum=flat` failed five, `spectrum=white`
            # three). A consequence a control genuinely has is declared beside it in `allowed`, so
            # the log says which failures were expected; anything else makes the row red, because
            # a control that fails for a second, unnoticed reason has stopped proving what it is
            # here to prove.
            missing = [w for w in must if not any(w in f for f in fails)]
            extra = [f for f in fails if not any(w in f for w in must + allowed)]
            if missing or extra:
                why = []
                if missing:
                    why.append("it did not fail on " + " and ".join(missing))
                if extra:
                    why.append("it also failed on %d line(s) the control does not declare: %s"
                               % (len(extra), " | ".join(e[:90] for e in extra[:3])))
                rows.append((label, False, "; ".join(why) + " - that is not this control failing"))
                continue
        # A control may leave a measurement undefined - `spectrum=flat` has no DFA exponent,
        # because a constant series has no fluctuation to detrend - and Godot writes that as null.
        # Printing the row must not be what decides whether the control counted.
        def num(*keys):
            v = r
            for k in keys:
                v = v.get(k) if isinstance(v, dict) else None
            return float("nan") if v is None else float(v)

        # A run under `switch=` or a coarse `tick=` does not measure the one-clip cycle: the
        # verifier SKIPS those checks there, and the row must not print their numbers as though
        # they meant what they mean at 60 Hz on one clip (a green row read "stride cv 0.2244 on /
        # 0.217367 off", which is the gait ladder, not the jitter).
        coarse = any(a.startswith("switch=") for a in args) or any(
            a.startswith("tick=") and float(a[5:]) > 1.5 / 60.0 for a in args)
        cycle = ("[stride, swing and skate not measured under %s]"
                 % " ".join(a for a in args if a.startswith(("switch=", "tick="))) if coarse else
                 "stride cv %.4f on / %.6f off | swing cv %.4f on / %.5f off | skate mean %.4f on / %.4f off m"
                 % (num("stride", "cv_on"), num("stride", "cv_off"), num("amplitude", "cv_on"),
                    num("amplitude", "cv_off"), num("skate", "on", "mean_m"),
                    num("skate", "off", "mean_m")))
        detail = ("alpha phase %.3f amp %.3f | %s | drift %.4f of %.4f cycles over %.0f s"
                  " | %.2f + %.2f us per character per frame"
                  % (num("dfa", "phase"), num("dfa", "amp"), cycle,
                     num("drift", "cycles_at_long"), num("drift", "bound_cycles"),
                     num("drift", "seconds_long"), num("cost_us_per_frame", "phase"),
                     num("cost_us_per_frame", "amp"))
                  + "".join("\n            " + f for f in fails[:6]))
        rows.append((label, passed == should_pass, detail))
    return rows


def _asym_report(src, name):
    with open(src / (name + ".json"), encoding="utf-8") as fh:
        return json.load(fh).get("report") or {}


def _stage_asym_keys(src, dst, name):
    """A second copy of each case's export under `_keys/`, with a `.import` written first so Godot
    imports it at the clip's own frame rate and keeps every key (GODOT_ASYM)."""
    fps = _asym_report(src, name).get("fps") or 24
    for case in GODOT_ASYM[name]["cases"]:
        for moves in sorted((src / case).glob("*.moves.json")):
            with open(moves, encoding="utf-8") as fh:
                m = json.load(fh)
            glb = src / case / m["scene"].rsplit("/", 1)[-1]
            to = dst / ASYM_KEYS / case
            to.mkdir(parents=True, exist_ok=True)
            shutil.copy2(glb, to / glb.name)
            with open(to / (glb.name + ".import"), "w", encoding="utf-8") as fh:
                fh.write('[remap]\n\nimporter="scene"\n\n[params]\n\nanimation/fps=%s\n'
                         '_subresources={"nodes": {"PATH:AnimationPlayer": {"optimizer/enabled": false}}}\n'
                         % fps)
            m["scene"] = "res://%s/%s/%s/%s/%s" % (GODOT_STAGE, name, ASYM_KEYS, case, glb.name)
            with open(to / moves.name, "w", encoding="utf-8") as fh:
                json.dump(m, fh, indent=1)


def _asym_play(godot, project, manifest, args):
    """One verify_asymmetry.gd run: ({role: report line}, [FAIL lines], verdict line, exit code)."""
    res = "res://" + manifest.relative_to(project).as_posix()
    code, out = _godot(godot, project, "-s", "res://addons/rig_anything/verify_asymmetry.gd", "--",
                       "manifests=" + res, *args)
    reps = {}
    for l in out.splitlines():
        if l.startswith("RA_ASYM_REPORT "):
            r = json.loads(l[len("RA_ASYM_REPORT "):])
            reps[r["role"]] = r
    fails = [l.split("FAIL", 1)[1].strip() for l in out.splitlines() if l.startswith("RA_ASYM  FAIL")]
    verdict = ([l for l in out.splitlines() if l.startswith("RA_ASYM VERIFY")] or
               ["no verdict, exit %s: %s" % (code, " | ".join(out.strip().splitlines()[-3:]))])[-1]
    return reps, fails, verdict, code


ASYM_CHANNELS = ("arm_swing_deg", "step_length_m", "stride_m", "shoulder_dip_m", "lag_cycles")


def _asym_gaps(godot_rep, bake):
    """{channel: worst |engine - bake| over the two sides}, and stance_offset_m's."""
    gaps = {}
    for c in ASYM_CHANNELS:
        g, b = godot_rep.get(c) or {}, bake.get(c) or {}
        if not g or not b:
            gaps[c] = float("inf")
            continue
        gaps[c] = max(abs(g["plus_lat"] - b["plus_lat"]), abs(g["minus_lat"] - b["minus_lat"]))
    g, b = godot_rep.get("stance_offset_m"), bake.get("stance_offset_m")
    gaps["stance_offset_m"] = float("inf") if g is None or b is None else abs(g - b)
    return gaps


def _asym_over(godot_rep, floors):
    """{channel: over its floor?} for the three channels "is asymmetric" ANDs, from the engine's report."""
    lag = godot_rep.get("lag_cycles") or {}
    return {"arm_swing_deg": (godot_rep.get("arm_swing_deg") or {}).get("index", 0.0) > floors["INDEX"],
            "shoulder_dip_m": (godot_rep.get("shoulder_dip_m") or {}).get("index", 0.0) > floors["INDEX"],
            "lag_cycles": bool(lag) and abs(lag["plus_lat"] - lag["minus_lat"]) > floors["LAG"]}


def _asym_values(godot_rep):
    """The three gated free values of "is asymmetric", by channel."""
    lag = godot_rep.get("lag_cycles") or {}
    return {"arm_swing_deg": (godot_rep.get("arm_swing_deg") or {}).get("index", 0.0),
            "shoulder_dip_m": (godot_rep.get("shoulder_dip_m") or {}).get("index", 0.0),
            "lag_cycles": abs(lag["plus_lat"] - lag["minus_lat"]) if lag else 0.0}


# The per-channel over_floor gate at the GAME's default import. Off: that import (30 fps resample AND
# the keyframe optimizer, together) makes a SYMMETRIC build's run read a shoulder-dip index of
# 0.050 (zero) / 0.041 (mirror) against the asymmetric build's 0.043 - the channel cannot be told
# apart there at all, so its verdict is noise, not a meter defect (at the keys the same builds read
# 0.019 / 0.022 / 0.120). Measured ad hoc: either setting alone restores it (optimizer off at 30 fps:
# 0.033 / 0.032 / 0.070; 24 fps with the optimizer on: 0.029 / 0.033 / 0.130).
# RA_REGRESS_ASYM_GAME_CHANNELS=1 turns the gate on; it goes red on exactly that until the exports
# ship an import preset. The row "what the game's default import can tell apart" prints it either way.
ASYM_GAME_CHANNELS = os.environ.get("RA_REGRESS_ASYM_GAME_CHANNELS") == "1"
# A free value within this factor of its floor, on either side, is printed THIN: a verdict that small
# import or tick changes could flip. Printed, never gated - the floors are the fixture's.
ASYM_THIN = 1.25


def _asym_margins(godot_rep, floors):
    """Each gated free value against its floor, as value / floor, so a thin margin is visible."""
    lag = godot_rep.get("lag_cycles") or {}
    vals = (("arm index", (godot_rep.get("arm_swing_deg") or {}).get("index"), floors["INDEX"]),
            ("dip index", (godot_rep.get("shoulder_dip_m") or {}).get("index"), floors["INDEX"]),
            ("|lag diff|", abs(lag["plus_lat"] - lag["minus_lat"]) if lag else None, floors["LAG"]),
            ("stride index", (godot_rep.get("stride_m") or {}).get("index"), floors["STRIDE_INDEX"]))
    out = []
    for what, v, f in vals:
        if v is None:
            out.append("%s -" % what)
            continue
        r = v / f
        out.append("%s %.5f (x%.2f of %g)%s" % (what, v, r, f, " THIN" if 1.0 / ASYM_THIN < r < ASYM_THIN else ""))
    return ", ".join(out)


def _asym_rows(godot_rep):
    rows = ""
    for c in ASYM_CHANNELS:
        v = godot_rep.get(c) or {}
        if v:
            rows += "\n            %-15s +lat %.5f -lat %.5f ratio %s index %.5f" % (
                c, v["plus_lat"], v["minus_lat"], "-" if v.get("ratio") is None else "%.5f" % v["ratio"],
                v["index"])
    if "stance_offset_m" in godot_rep:
        rows += "\n            stance_offset   %+.5f m" % godot_rep["stance_offset_m"]
    return rows


def _asym_swap_why(role, sw, plain):
    """What a side-swapped report `sw` gets wrong against the unswapped `plain` of the same clip.

    Four channels must invert their ratio. lag_cycles is judged by EXCHANGE instead (the swapped
    +lat must be the unswapped -lat and back): its ratio is ill-conditioned near zero, so an
    inversion test would pass or fail on noise, while its per-side values are the same samples
    relabelled and must match to the digit. stance_offset must flip sign."""
    why = []
    for c in ("arm_swing_deg", "step_length_m", "stride_m", "shoulder_dip_m"):
        prod = sw[c]["ratio"] * plain[c]["ratio"]
        if abs(prod - 1.0) > 1e-6:
            why.append("%s %s: ratio did not invert (%.6f x %.6f)" % (role, c, sw[c]["ratio"], plain[c]["ratio"]))
    a, b = sw.get("lag_cycles") or {}, plain.get("lag_cycles") or {}
    if not a or not b:
        why.append("%s lag_cycles: missing from a report" % role)
    elif abs(a["plus_lat"] - b["minus_lat"]) > 1e-9 or abs(a["minus_lat"] - b["plus_lat"]) > 1e-9:
        why.append("%s lag_cycles: sides did not exchange (swapped +lat %.6f -lat %.6f, unswapped +lat %.6f -lat %.6f)"
                   % (role, a["plus_lat"], a["minus_lat"], b["plus_lat"], b["minus_lat"]))
    if (abs(sw["stance_offset_m"] + plain["stance_offset_m"]) > 1e-9
            or sw["stance_offset_m"] * plain["stance_offset_m"] >= 0.0):
        why.append("%s: stance_offset did not flip (%+.5f against %+.5f)"
                   % (role, sw["stance_offset_m"], plain["stance_offset_m"]))
    return why


def _run_asym(godot, project, where, src, name):
    """GODOT_ASYM's runs on one fixture: [(check, passed, detail)]."""
    spec = GODOT_ASYM[name]
    rep = _asym_report(src, name)
    cases, floors, fps = rep.get("cases") or {}, rep.get("floors") or {}, rep.get("fps") or 24
    if not cases or not floors:
        return [("verify_asymmetry %s" % name, False, "the fixture's report has no cases or floors")]
    judge = ["floor_index=%s" % floors["INDEX"], "floor_lag=%s" % floors["LAG"],
             "stride_index=%s" % floors["STRIDE_INDEX"]]
    at_keys = judge + ["tick=%r" % (1.0 / fps), "cycles=3"]
    in_game = judge + ["cycles=12"]
    rows, got = [], {}

    def manifest(case, keyed):
        found = sorted((where / ASYM_KEYS / case if keyed else where / case).glob("*.moves.json"))
        return found[0] if found else None

    for mode, args in (("keys", at_keys), ("game", in_game)):
        for case in spec["cases"]:
            label = "verify_asymmetry %s %s (%s)" % (name, case, "at its keys, against the bake" if mode == "keys"
                                                        else "as the game imports it, at 60 Hz")
            path = manifest(case, mode == "keys")
            if path is None:
                rows.append((label, False, "the fixture did not export %s" % case))
                continue
            reps, fails, verdict, code = _asym_play(godot, project, path, args)
            got[(mode, case)] = reps
            bake = cases.get(case, {}).get("measured", {})
            why, notes = [], []
            roles = sorted(bake)
            if sorted(reps) != roles:
                why.append("measured %s, the bake has %s" % (sorted(reps), roles))
            # every FAIL must be a declared one, and a must-fail case must fail it on every clip
            must = case in spec["must_fail"]
            extra = [f for f in fails if not (must and "is asymmetric" in f)]
            if extra:
                why.append("failed %d undeclared line(s): %s" % (len(extra), " | ".join(e[:110] for e in extra[:3])))
            for role in roles:
                said = not any(("%s: is asymmetric" % role) in f for f in fails)
                golden = bake[role]["verdicts"]["asymmetric"]
                if said != golden:
                    why.append("%s: the engine says asymmetric=%s, the bake (golden) %s" % (role, said, golden))
                if must and said:
                    why.append("%s: a control that must fail 'is asymmetric' passed it" % role)
                # one channel at a time: "is asymmetric" is an AND, so a control fails it on ONE channel
                # under its floor; it must be under on EVERY channel, and each channel must say what the
                # golden's over_floor says
                if role not in reps:
                    continue
                over = _asym_over(reps[role]["report"], floors)
                gold = bake[role]["verdicts"].get("over_floor")
                # at the keys the engine plays the bake, so this is gated; at the game's import it is
                # gated only with ASYM_GAME_CHANNELS (off: see there), and otherwise printed
                chan = []
                if gold is None:
                    chan.append("%s: the golden has no per-channel over_floor verdicts" % role)
                else:
                    for c, v in over.items():
                        if v != gold.get(c):
                            chan.append("%s %s: the engine says over its floor=%s, the golden %s" % (role, c, v, gold.get(c)))
                if must and any(over.values()):
                    chan.append("%s: a control reads over its floor on %s" % (
                        role, ", ".join(c for c, v in over.items() if v)))
                if mode == "keys" or ASYM_GAME_CHANNELS:
                    why += chan
                else:
                    notes += ["(ungated, ASYM_GAME_CHANNELS off) " + c for c in chan]
            detail = ""
            for role in roles:
                if role not in reps:
                    continue
                detail += "\n          %s against the floors: %s" % (role, _asym_margins(reps[role]["report"], floors))
                gaps = _asym_gaps(reps[role]["report"], bake[role])
                over = [c for c, g in gaps.items() if g > ASYM_TOL[c]]
                detail += "\n          %s against the bake, worst side: %s" % (role, ", ".join(
                    "%s %.5f%s" % (c, g, " (> %g)" % ASYM_TOL[c] if mode == "keys" and c in over else "")
                    for c, g in gaps.items()))
                if mode == "keys" and over:
                    why.append("%s disagrees with the bake beyond tolerance on %s" % (role, ", ".join(over)))
                if case == spec["cases"][0]:
                    detail += _asym_rows(reps[role]["report"])
            rows.append((label, not why, verdict + "".join("\n          " + w for w in why + notes) + detail))

    # what the game's import can still tell apart: per clip and channel, the asymmetric build's value
    # against the largest a symmetric control reads there. Printed, never gated (free values)
    base = spec["swap_of"]
    if ("game", base) in got:
        lines = []
        for role in sorted(got[("game", base)]):
            a = _asym_values(got[("game", base)][role]["report"])
            ctl = [_asym_values(got[("game", c)][role]["report"]) for c in spec["must_fail"]
                   if role in got.get(("game", c), {})]
            for c in a:
                worst = max((v[c] for v in ctl), default=None)
                if worst is None:
                    continue
                lines.append("%s %s: %s %.5f against the controls' worst %.5f (x%.2f)%s" % (
                    role, c, base, a[c], worst, a[c] / worst if worst else float("inf"),
                    "  CANNOT TELL APART" if a[c] <= worst else ""))
        rows.append(("verify_asymmetry %s what the game's default import can tell apart (printed, not gated)" % name,
                     True, "".join("\n          " + l for l in lines)))

    # step length: the stance offset MOVES against the zero build (asym), and does not (mirror)
    zero = got.get(("keys", spec["zero"]), {})
    for case in spec["cases"]:
        if case == spec["zero"] or ("keys", case) not in got:
            continue
        why, detail = [], ""
        for role, r in sorted(got[("keys", case)].items()):
            if role not in zero:
                why.append("%s: no zero build to measure against" % role)
                continue
            moved = r["report"]["stance_offset_m"] - zero[role]["report"]["stance_offset_m"]
            said = abs(moved) > floors["STEP_M"]
            golden = cases[case]["measured"][role]["verdicts"]["step_moved"]
            detail += "\n          %s stance offset moved %+.5f m against zero's (floor %.3f): %s, golden %s" % (
                role, moved, floors["STEP_M"], said, golden)
            if said != golden:
                why.append("%s: the engine says step moved=%s, the golden %s" % (role, said, golden))
        rows.append(("verify_asymmetry %s %s step length moved against zero" % (name, case), not why,
                     "; ".join(why) + detail))

    base = spec["swap_of"]
    path = manifest(base, True)
    if path is None or ("keys", base) not in got:
        return rows
    # the side-swap control: ratios invert, stance flips, and the bake's own swap agrees while
    # the unswapped bake must NOT - a comparison that cannot see sides fails here
    reps, fails, verdict, code = _asym_play(godot, project, path, at_keys + ["swap=1"])
    why, detail = [], ""
    if not reps:
        why.append("no RA_ASYM_REPORT: " + verdict)
    for role, r in sorted(reps.items()):
        plain = got[("keys", base)][role]["report"]
        sw = r["report"]
        why += _asym_swap_why(role, sw, plain)
        own = _asym_gaps(sw, cases["swap"]["measured"][role])
        wrong = _asym_gaps(sw, cases[base]["measured"][role])
        over_own = [c for c, g in own.items() if g > ASYM_TOL[c]]
        over_wrong = [c for c, g in wrong.items() if g > ASYM_TOL[c]]
        if over_own:
            why.append("%s: disagrees with the bake's own swap on %s" % (role, ", ".join(over_own)))
        if not over_wrong:
            why.append("%s: a swapped meter AGREED with the unswapped bake - the comparison cannot see sides" % role)
        detail += ("\n          %s ratios arm %.5f step %.5f dip %.5f (unswapped %.5f %.5f %.5f), stance %+.5f "
                   "(unswapped %+.5f); against the unswapped bake it is off on %s" % (
                       role, sw["arm_swing_deg"]["ratio"], sw["step_length_m"]["ratio"], sw["shoulder_dip_m"]["ratio"],
                       plain["arm_swing_deg"]["ratio"], plain["step_length_m"]["ratio"],
                       plain["shoulder_dip_m"]["ratio"], sw["stance_offset_m"], plain["stance_offset_m"],
                       ", ".join(over_wrong) or "nothing"))
    rows.append(("verify_asymmetry %s %s swap=1 (sides exchanged: ratios invert, stance flips)" % (name, base),
                 not why, "; ".join(why) + detail))

    # the poison control: nothing the meter must not read may move a digit
    reps_p, fails_p, verdict_p, code_p = _asym_play(godot, project, path, at_keys + ["poison=1"])
    why = []
    for role, r in sorted(got[("keys", base)].items()):
        if role not in reps_p:
            why.append("%s: not measured with the poisoned manifest" % role)
        elif reps_p[role]["hash"] != r["hash"]:
            why.append("%s: the numbers MOVED when the manifest's variability, arm_pose values, gaits and "
                       "stance spans were rewritten - the meter reads something it must not" % role)
    rows.append(("verify_asymmetry %s %s poison=1 (the answer rewritten: numbers must not move)" % (name, base),
                 not why, "; ".join(why) or "identical report hash on %s" % ", ".join(sorted(reps_p))))
    return rows


def _run_strands(godot, project, where, name):
    """GODOT_STRANDS' run on one fixture's exports and its must-fail controls: [(check, passed, detail)]."""
    spec = GODOT_STRANDS[name]
    body = sorted(where.rglob(spec["body"]))
    hair = sorted(where.rglob(spec["strands"]))
    if not body or not hair:
        return [("verify_strands %s" % name, False, "the fixture did not export %s and %s" % (spec["body"], spec["strands"]))]
    res = ["scene=res://" + body[0].relative_to(project).as_posix(), "strands=res://" + hair[0].relative_to(project).as_posix()]
    rows = []
    runs = [("verify_strands %s" % name, spec["args"], True, [])]
    runs += [("verify_strands %s %s (must fail)" % (name, " ".join(ctl)), spec["args"] + ctl, False, must)
             for ctl, must in spec["controls"]]
    for label, args, should_pass, must in runs:
        code, out = _godot(godot, project, "-s", "res://addons/follow_through/verify_strands.gd", "--", *res, *args)
        verdict = [l for l in out.splitlines() if l.startswith("FT_SUMMARY")]
        per_rate = [json.loads(l[len("FT_STRAND "):]) for l in out.splitlines() if l.startswith("FT_STRAND ")]
        if not verdict or not per_rate:
            rows.append((label, False, "no FT_STRAND / FT_SUMMARY, exit %s: %s" % (code, " | ".join(out.strip().splitlines()[-3:]))))
            continue
        passed = code == 0 and "PASSED" in verdict[-1]
        fails = [l.strip() for l in out.splitlines() if l.strip().startswith("FAIL ")]
        if not should_pass:
            missing = [w for w in must if not any(w in f for f in fails)]
            if missing:
                # failed, but not for the reason the control exists for: that is not the control failing
                passed = True
                fails.insert(0, "FAIL (control) did not fail on: " + "; ".join(missing))
        detail = verdict[-1] + "".join("\n            %s fps: swing %s deg settled (mean %s), %s starting, head %s m, rest drift %s deg" % (
            r.get("fps"), r.get("swing_deg"), r.get("swing_mean_deg"), r.get("start_swing_deg"), r.get("run_head_penetration_m"),
            r.get("rest_drift_deg")) for r in per_rate) + "".join("\n            " + f for f in fails[:8])
        rows.append((label, passed == should_pass, detail))
    return rows


def show(changes, was="was", now="now", limit=40):
    for key, before, after in changes[:limit]:
        _print("          %s\n            %s %r\n            %s %r" % (key, was, before, now, after))
    if len(changes) > limit:
        _print("          ... and %d more (all of them are in the diff file)" % (len(changes) - limit))


def diff_text(name, changes, was="was", now="now", heading=""):
    lines = ["== %s: %s%d key(s)" % (name, heading, len(changes))]
    for key, before, after in changes:
        lines.append("  %s\n    %s %r\n    %s %r" % (key, was, before, now, after))
    return "\n".join(lines) + "\n"


def done_line(code, ok):
    """The last line of every run, exactly: a background wait matches on it."""
    return "REGRESS DONE exit=%d, %d fixtures ok" % (code, ok)  # never singular: waits match this literal


def default_diff_path(keep):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    folder = Path(keep) if keep else Path(tempfile.gettempdir()) / "regress-diffs"
    return folder / ("regress-%s-%d.diff" % (stamp, os.getpid()))


def main(argv=None):
    state = {"ok": 0}
    try:
        code = _main(argv, state)
    except SystemExit as exc:                    # argparse errors and --help
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 2)
    except BaseException:
        import traceback
        traceback.print_exc()
        code = 3
    _print(done_line(code, state["ok"]))
    return code


def _main(argv, state):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", metavar="FIXTURE", help="run these fixtures, not all")
    ap.add_argument("--quick", action="store_true",
                    help="run only the fixtures that reach what changed since --base (see above)")
    ap.add_argument("--base", default="main", help="what --quick compares with (default main)")
    ap.add_argument("--changed", nargs="+", metavar="PATH",
                    help="with --quick: take these repo-relative paths as the change instead of asking git")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the fixtures that would run, in order, and why; build nothing")
    ap.add_argument("--plugins", metavar="CHECKOUT",
                    help="a repo checkout whose plugins/<name>/scripts the fixtures import")
    ap.add_argument("--update", action="store_true",
                    help="rewrite goldens from this run (a golden within tolerance is left alone)")
    ap.add_argument("--twice", action="store_true",
                    help="build every fixture twice and fail if the two builds disagree")
    ap.add_argument("--jobs", type=int, default=1, help="fixtures to run at once (default 1)")
    ap.add_argument("--keep", metavar="DIR", help="keep each fixture's output here, not in a temp dir")
    ap.add_argument("--diff", metavar="FILE",
                    help="write the full diff here (default: in --keep, else <temp>/regress-diffs/)")
    ap.add_argument("--blender", default=find_blender())
    ap.add_argument("--godot", metavar="PROJECT",
                    help="also run the Godot verifiers on the fixtures' exports inside this project")
    ap.add_argument("--godot-bin", default=find_godot(), help="the Godot console binary ($GODOT)")
    args = ap.parse_args(argv)

    if args.quick and args.only:
        ap.error("--quick chooses the fixtures itself; do not pass --only with it")
    if args.changed and not args.quick:
        ap.error("--changed only means something with --quick")
    names = args.only or fixtures()
    unknown = [n for n in names if not (FIXTURES / (n + ".py")).is_file()]
    if unknown:
        ap.error("no such fixture: %s (have: %s)" % (", ".join(unknown), ", ".join(fixtures())))

    if args.quick:
        try:
            changed = args.changed or changed_files(args.base)
        except RuntimeError as exc:
            ap.error("--quick could not list the change: %s" % exc)
        selected, skipped, notes = select(changed, names)
        _print("quick: %d path(s) changed against %s" % (len(changed), "--changed" if args.changed else args.base))
        for path, what in notes:
            _print("  %s -> %s" % (path, what))
        _print("quick: selected %d of %d fixture(s)" % (len(selected), len(names)))
        for n in schedule(selected):
            _print("  run   %s: %s" % (n, "; ".join(dict.fromkeys(selected[n]))))
        for n in sorted(skipped):
            _print("  skip  %s: %s" % (n, skipped[n]))
        names = list(selected)
    names = schedule(names)
    _print("order (longest first): %s" % " ".join(names))
    if args.keep:
        keep_root = Path(args.keep).resolve()
        warn = path_warning(keep_root, DEEPEST_OUTPUT if args.twice else DEEPEST_OUTPUT - 2)
        if warn:
            _print(warn)
    if args.dry_run or not names:
        if not names:
            _print("nothing to run")
        return 0

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
            _print("WARNING: the project's addons differ from this repo's, so the verifiers run the "
                   "project's copy:\n  " + "\n  ".join(drift))

    env = dict(os.environ)
    if args.plugins:
        root = Path(args.plugins).resolve()
        for var, plugin in SCRIPT_VARS.items():
            # A checkout from before a plugin moved in here does not have it; that plugin then
            # stays on this repo's copy rather than failing to import.
            scripts = root / "plugins" / plugin / PACKAGE_DIR.get(plugin, "scripts")
            if scripts.is_dir():
                env[var] = str(scripts)
        have = sorted(p for var, p in SCRIPT_VARS.items() if env.get(var, "").startswith(str(root)))
        _print("plugins: %s (%s; the rest from this checkout)" % (root, ", ".join(have)))
    else:
        _print("plugins: %s (this checkout)" % REPO)
    GOLDEN.mkdir(parents=True, exist_ok=True)

    diff_path = Path(args.diff) if args.diff else default_diff_path(args.keep)
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_chunks = []

    temp = None if args.keep else tempfile.TemporaryDirectory(prefix="regress-")
    out_root = Path(args.keep) if args.keep else Path(temp.name)
    failures, updated, built, deepest = [], [], [], (0, "")
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            # With --twice each build gets its own folder - and so its own humanform library, so
            # the second build cannot warm-start from the first and hide a difference. Submitted
            # longest first, both builds of a fixture together, so its result is in as early as it can be.
            builds = ("a", "b") if args.twice else ("",)
            runs = {}
            for name in names:
                for b in builds:
                    runs[pool.submit(run_fixture, name, args.blender, out_root / b, env)] = (name, b)
            results = {}
            for fut in concurrent.futures.as_completed(runs):
                name, b = runs[fut]
                results[(name, b)] = fut.result()
                if all((name, x) in results for x in builds):
                    for fresh, _ in (results[(name, x)] for x in builds):
                        if fresh.get("_deepest", (0,))[0] > deepest[0]:
                            deepest = tuple(fresh["_deepest"])
                    state["ok"] += judge(name, [results[(name, x)] for x in builds], args, failures,
                                         updated, built, diff_chunks)
        if project and built:
            # A fixture whose golden moved still exported something worth playing; one that
            # errored or did not reproduce did not.
            _print("\ngodot: %s" % project)
            for check, passed, detail in run_godot(args.godot_bin, project, out_root / builds[0], built):
                _print("  %s %s: %s" % ("ok     " if passed else "FAILED ", check, detail))
                if not passed:
                    failures.append(check)
                    diff_chunks.append("== godot %s: FAILED\n  %s\n" % (check, detail))
    finally:
        if temp:
            temp.cleanup()
        # Written whatever happened, even when the run died part-way: what it had seen is in it.
        with open(diff_path, "w", encoding="utf-8") as fh:
            fh.write("regress %s, %s\n\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(sys.argv[1:])))
            fh.write("".join(diff_chunks) if diff_chunks else "no key changed in any fixture\n")

    if args.keep and deepest[0]:
        # the free value: what this run wrote, not the DEEPEST_OUTPUT estimate
        rel = deepest[0] - len(str(out_root)) - 1
        _print("deepest output: %d characters (%s)" % (deepest[0], deepest[1]))
        warn = path_warning(Path(args.keep), rel)
        if warn:
            _print(warn)
    if updated:
        _print("\ngoldens written for %s - review the diff before committing" % ", ".join(updated))
    _print("\nfull diff: %s" % diff_path)
    if failures:
        _print("%d fixture(s) changed or failed: %s" % (len(failures), ", ".join(failures)))
        return 1
    _print("no change")
    return 0


def judge(name, results, args, failures, updated, built, diff_chunks):
    """Print one fixture's result the moment its builds are in. Returns 1 if it passed, else 0."""
    fresh, took = results[0]
    stages = fresh.pop("_stage_times", [])
    fresh.pop("_deepest", None)
    versions = " ".join("%s %s" % (k, v) for k, v in sorted(fresh.get("plugins", {}).items()))
    head = "%s [%.0fs] %s" % (name, took, versions)
    if "error" in fresh:
        _print("  ERROR   %s\n          %s" % (head, fresh["error"]))
        diff_chunks.append("== %s: ERROR\n%s\n" % (name, fresh["error"]))
        failures.append(name)
        return 0
    if args.twice:
        second, took_b = results[1]
        second.pop("_stage_times", None)
        second.pop("_deepest", None)
        head = "%s [%.0fs + %.0fs] %s" % (name, took, took_b, versions)
        if "error" in second:
            _print("  ERROR   %s (second build)\n          %s" % (head, second["error"]))
            diff_chunks.append("== %s: ERROR in the second build\n%s\n" % (name, second["error"]))
            failures.append(name)
            return 0
        differ = compare(fresh, second)
        if differ:
            # Checked before the golden: a build that does not reproduce is not a
            # result to compare, and never one to record.
            _print("  NONDETERMINISTIC %s: %d key(s) differ between two builds" % (head, len(differ)))
            show(differ, "a", "b")
            diff_chunks.append(diff_text(name, differ, "a", "b", "NONDETERMINISTIC, "))
            failures.append(name)
            return 0
    built.append(name)
    for key, n in volatile_blocks(fresh.get("report", {})):
        _print("  WARNING %s: `%s` is a volatile key holding a dict of %d entr%s, so none of it is "
               "compared; rename it if it holds results" % (name, key, n, "y" if n == 1 else "ies"))
    golden_path = GOLDEN / (name + ".json")
    old = None
    if golden_path.is_file():
        with open(golden_path, encoding="utf-8") as fh:
            old = json.load(fh)
    changes = compare(old, fresh) if old is not None else None
    passed = 1
    if old is None or (args.update and changes):
        with open(golden_path, "w", encoding="utf-8") as fh:
            json.dump(fresh, fh, indent=1, sort_keys=True)
        _print("  %s %s" % ("UPDATED" if old is not None else "RECORDED", head))
        if changes:
            diff_chunks.append(diff_text(name, changes, heading="UPDATED, "))
        updated.append(name)
    elif not changes:
        # With --update too: a golden within tolerance is not rewritten, so a re-record touches
        # only the goldens that moved (its version stamp stays as it was).
        _print("  ok      %s%s" % (head, " (golden within tolerance, kept)" if args.update else ""))
    else:
        failures.append(name)
        passed = 0
        _print("  CHANGED %s: %d key(s)" % (head, len(changes)))
        show(changes)
        diff_chunks.append(diff_text(name, changes, heading="CHANGED, "))
    for manifest, quality, total, secs in stages:
        _print("          stages %s (%s, %ss): %s" % (manifest, quality, total,
                                                     ", ".join("%s %s" % kv for kv in secs.items())))
    return passed


if __name__ == "__main__":
    sys.exit(main())
