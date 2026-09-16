"""Shared by every fixture. A fixture is a script Blender runs:

    blender -b --factory-startup --python tests/fixtures/<name>.py -- out=<dir>

It builds something from nothing - no .blend, no stored asset - and writes
`<out>/<name>.json`, a report of numbers a later build must reproduce. `tools/regress.py`
runs them and compares against `tests/golden/`.

Which plugin checkout is exercised comes from the environment (RA_SCRIPTS, HF_SCRIPTS,
FT_SCRIPTS, WD_SCRIPTS - the names `grungist-creek`'s build scripts already use), so the
same fixture can be run against a worktree without editing it. Unset, they point at this
repo's own plugins/.

A fixture must be deterministic: seed every generator, never read the user's humanform
library (the harness points HUMANFORM_LIBRARY at a scratch folder), and report no
timings, paths or dates - the runner strips them, but a fixture that reports them is
reporting noise.
"""
import json
import os
import sys
import traceback

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PLUGINS = {"RA_SCRIPTS": "rig-anything", "HF_SCRIPTS": "humanform",
           "FT_SCRIPTS": "follow-through", "WD_SCRIPTS": "wardrobe"}


def scripts(var):
    """The scripts folder for one plugin: the environment's, or this repo's."""
    return os.environ.get(var) or os.path.join(REPO, "plugins", PLUGINS[var], "scripts")


USED = {}


def use(*vars):
    """Put those plugins on sys.path and return their folders, noting which versions ran."""
    out = []
    for var in vars:
        p = scripts(var)
        if p not in sys.path:
            sys.path.insert(0, p)
        USED[PLUGINS[var]] = _version(p)
        out.append(p)
    return out


def _version(scripts_dir):
    """The version of the plugin whose scripts folder that is - context for a run, never compared."""
    manifest = os.path.join(os.path.dirname(scripts_dir), ".claude-plugin", "plugin.json")
    try:
        with open(manifest, encoding="utf-8") as fh:
            return json.load(fh)["version"]
    except (OSError, ValueError, KeyError):
        return "?"


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return dict(a.split("=", 1) for a in argv if "=" in a)


def out_dir():
    d = args().get("out") or os.path.join(REPO, "tests", "_out")
    os.makedirs(d, exist_ok=True)
    return d


def enable_addons(*modules):
    """Turn on add-ons a fixture needs. `--factory-startup` starts with Rigify off, and
    rig-anything's `fit_basic_human` then fails with `'Armature' object has no attribute
    'rigify_colors'` - a real trap, filed under improvements category 1."""
    import addon_utils
    for module in modules:
        addon_utils.enable(module, default_set=False, persistent=True)


def clear_scene():
    """Factory startup's cube, camera and light: gone, so a fixture starts from nothing."""
    import bpy
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def round_floats(value, places=6):
    if isinstance(value, float):
        return round(value, places)
    if isinstance(value, dict):
        return {k: round_floats(v, places) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [round_floats(v, places) for v in value]
    return value


def stable(value, max_list=16, places=6):
    """A plugin report reduced to what a golden can hold: numbers, strings and bools.

    Blender objects and vectors become lists, private keys (`_foo`) go, and a list longer
    than `max_list` - per-frame traces, mostly - keeps its length and its ends, so a golden
    stays readable and still moves when the trace does."""
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, places)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return {k: stable(v, max_list, places) for k, v in value.items() if not str(k).startswith("_")}
    if hasattr(value, "__len__") or isinstance(value, (list, tuple)):
        try:
            items = list(value)
        except TypeError:
            return str(value)
        if len(items) > max_list:
            return {"len": len(items), "first": stable(items[0], max_list, places),
                    "last": stable(items[-1], max_list, places)}
        return [stable(v, max_list, places) for v in items]
    return str(value)


def run(name, build):
    """Run one fixture's `build()` and write its report. Any failure is the report."""
    out = out_dir()
    os.environ.setdefault("HUMANFORM_LIBRARY", os.path.join(out, "_humanform_library"))
    path = os.path.join(out, name + ".json")
    try:
        report = {"fixture": name, "plugins": dict(USED), "report": round_floats(build())}
    except Exception as exc:                                  # a broken fixture is a failed run
        traceback.print_exc()
        report = {"fixture": name, "plugins": dict(USED),
                  "error": f"{type(exc).__name__}: {exc}"}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, sort_keys=True, default=str)
    print("FIXTURE_WROTE", path)
    if "error" in report:
        sys.exit(1)
