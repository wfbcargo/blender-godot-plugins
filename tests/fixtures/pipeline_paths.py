"""Specs safe to copy (06 rank 2): a relative `[export] blend` builds and saves under whichever project the spec
sits in, and the runner refuses to save outside the project and $BLEND_DIR unless told to.

One body (draft, `to_stage="body"`) is built from a spec in project `a`; the same file, copied byte for byte
into project `b`, is built there in the same session (body is then unchanged, so it only saves). Then:

- **where it saved:** every .blend under the fixture's folder after each build, relative to it - `a`'s build
  saves `a/fixpath.blend`, `b`'s `b/fixpath.blend`, and `a`'s file is not written again by `b`'s build;
- **BLEND_DIR:** with $BLEND_DIR set, the relative blend resolves and saves under it instead;
- **hash-identical copies:** `runner.plan` of the copied spec equals the original's stage for stage (the string
  is hashed as written); the control, the copy with an absolute blend, moves export (and review after it);
- **refusals, each before any stage runs** (the build log must hold no stage line): an absolute blend outside
  the project, a relative `../` one leaving it, and a sibling folder whose name only starts with the project's
  (`c2` beside `c`: a prefix test would let it through). The scene is emptied first, so a build that got past
  the guard would run body (and log it) before saving. Each refusal's control is the same build with
  `save_outside=True`, which must save exactly there - so the refusal is the guard, not something else failing.

`PIPELINE_PATHS_NO_GUARD=1` replaces `runner.check_save_path` with one that passes everything: the refusal keys
must then change (the harness's control, run by hand).
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "HF_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS", "CP_SCRIPTS")

SPEC = '''
[character]
id = "fixpath"
name = "FixPath"

[body]
sex = "male"
age = 35
stature = 1.78
build = "average"
seed = 3
style = "realistic"
skin = [0.62, 0.45, 0.36]

[moves]
gaits = { Walk = 0.2 }
style = "adult"

[build]
quality = "draft"

[export]
dir = "assets/fixpath"
res_dir = "res://assets/fixpath"
blend = "fixpath.blend"
'''


def _write(project, text):
    os.makedirs(os.path.join(project, "characters"), exist_ok=True)
    path = os.path.join(project, "characters", "fixpath.toml")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def _blends(root):
    found = []
    for dirpath, _dirs, files in os.walk(root):
        found += [os.path.relpath(os.path.join(dirpath, f), root).replace("\\", "/") for f in files
                  if f.endswith(".blend")]
    return sorted(found)


def _rel(path, root):
    return os.path.relpath(path, root).replace("\\", "/") if path else None


def build():
    from character_pipeline import runner, spec

    if os.environ.get("PIPELINE_PATHS_NO_GUARD") == "1":
        runner.check_save_path = lambda ch, path, save_outside=False: path

    H.clear_scene()
    root = os.path.join(H.out_dir(), "pipeline_paths")
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    os.environ.pop("BLEND_DIR", None)
    out = {}

    def run(spec_path, **kw):
        lines = []
        try:
            r = runner.build(spec_path, to_stage="body", log=lines.append, **kw)
            return {"saved": _rel(r.get("saved"), root), "body": r["body"]["status"]}, lines
        except runner.BuildRefused as exc:
            return {"refused": True, "names_save_outside": "save_outside=True" in str(exc),
                    "stage_lines": sum(1 for m in lines if "..." in m)}, lines

    a = _write(os.path.join(root, "a"), SPEC)
    out["a"], _ = run(a)
    out["after_a"] = _blends(root)
    stamp = os.path.getmtime(os.path.join(root, "a", "fixpath.blend"))

    b_project = os.path.join(root, "b")
    os.makedirs(os.path.join(b_project, "characters"))
    shutil.copyfile(a, os.path.join(b_project, "characters", "fixpath.toml"))    # byte for byte, no sed
    b = os.path.join(b_project, "characters", "fixpath.toml")
    out["b"], _ = run(b)
    out["after_b"] = _blends(root)
    out["a_untouched_by_b"] = os.path.getmtime(os.path.join(root, "a", "fixpath.blend")) == stamp

    os.environ["BLEND_DIR"] = os.path.join(root, "blends")
    try:
        out["with_env"], _ = run(b)
        out["env_resolves_to"] = _rel(spec.load(b).blend_path(), root)
    finally:
        os.environ.pop("BLEND_DIR", None)
    out["after_env_build"] = _blends(root)

    # a copy hashes as the original; an edited blend string moves export (the control)
    pa, pb = runner.plan(a), runner.plan(b)
    out["plan_copy_equal"] = pa == pb
    moved = _write(os.path.join(root, "b_abs"), SPEC.replace('blend = "fixpath.blend"',
                                                              'blend = "%s"' % os.path.join(root, "b_abs", "x.blend")
                                                              .replace("\\", "/")))
    pm = runner.plan(moved)
    out["plan_control_moved"] = sorted(k for k in pa if pa[k] != pm.get(k))

    # refusals, each with its save_outside control
    cases = {
        "absolute_outside": os.path.join(root, "outside", "fixpath.blend").replace("\\", "/"),
        "relative_up": "../outside_up/fixpath.blend",
        "prefix_sibling": os.path.join(root, "c2", "fixpath.blend").replace("\\", "/"),
    }
    for name, blend in cases.items():
        c = _write(os.path.join(root, "c"), SPEC.replace('blend = "fixpath.blend"', 'blend = "%s"' % blend))
        H.clear_scene()                         # no body in the session: a build would have to run one first
        refused, _ = run(c)
        allowed, _ = run(c, save_outside=True)
        out[name] = {"refused": refused, "save_outside": allowed}
    out["after_all"] = _blends(root)
    return out


H.run("pipeline_paths", build)
