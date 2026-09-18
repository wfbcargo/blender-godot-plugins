"""A ponytail that swings, from a character spec alone: character-pipeline's strand stage (05 5.2).

A woman with `[hair] preset = "ponytail"` goes through every stage. The hair stage joins its cap and
tie into the body but leaves the tail its own object, because the join drops the properties
follow-through builds a chain from; the strand stage then hands that object to
`follow_through.strand.prepare`, which hangs the chain on the head bone; and the export writes it
beside the body as `<id>_hair.glb`, named in the manifest's `strands` so a controller knows what to
hand `FollowThrough.attach`. No build script holds any of it: the spec's preset is what says there is
a strand at all.

The golden holds the stages this spec has (a `bun` spec has no strand stage, nor a `long_loose` one -
its curtain is a sheet, not a line, and stays joined into the body), what the hair stage
left loose and its follow-through contract, the chain (bones, length, per-bone frequency, colliders,
weights), both glbs read back - the body's skeleton carrying the chain bones, and the strand file's
own spec with its bone heads where the spec puts them - and the manifest.

Two refusals: export before the strand stage has run (the hair would ship weighted rigidly to the
head and never swing), and the strand stage before the moves are authored.

Not here: the swinging itself, which is Godot's. `verify_strands.gd` on this character's exports is
in follow-through's strands reference.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "HF_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS", "CP_SCRIPTS", "LD_SCRIPTS")
for _var in ("RA_SCRIPTS", "HF_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS", "CP_SCRIPTS", "LD_SCRIPTS"):
    os.environ[_var] = H.scripts(_var)

SPEC = '''
[character]
id = "ponywoman"
name = "PonyWoman"

[body]
sex = "female"
age = 30
stature = 1.68
build = "curvy"
seed = 11
style = "realistic"
skin = [0.62, 0.45, 0.36]

[moves]
roles = ["Idle", "Run"]
gaits = { Run = 2.0 }
style = "adult"

[hair]
preset = "ponytail"
colour = [0.35, 0.22, 0.12]

[review]
enabled = false

[export]
dir = "assets/ponywoman"
res_dir = "res://assets/ponywoman"
'''


def _glb_json(path):
    with open(path, "rb") as fh:
        data = fh.read()
    n = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20:20 + n])


def _statuses(report):
    return {k: v["status"] for k, v in report.items() if isinstance(v, dict) and "status" in v}


def _skeleton(path, prefix):
    """What the exported file's skeleton and meshes say about the chain."""
    j = _glb_json(path)
    names = [n.get("name", "") for n in j["nodes"]]
    chain = sorted(n for n in names if n.startswith(prefix))
    skins = [sorted(names[k] for k in s["joints"] if names[k].startswith(prefix)) for s in j.get("skins", [])]
    return {"meshes": sorted(n.get("name") for n in j["nodes"] if "mesh" in n),
            "chain_bones": chain, "chain_bones_in_skin": sorted({b for s in skins for b in s})}


def build():
    import bpy
    import tomllib
    H.clear_scene()
    from character_pipeline import runner, spec, stages

    root = os.path.join(H.out_dir(), "pipeline_ponytail")
    os.makedirs(os.path.join(root, "characters"), exist_ok=True)
    spec_path = os.path.join(root, "characters", "ponywoman.toml")
    with open(spec_path, "w", encoding="utf-8") as fh:
        fh.write(SPEC)
    ch = spec.load(spec_path)

    # the stages this spec has, against one whose preset grows no strand and one whose strand is a
    # sheet rather than a line (`long_loose`'s curtain: joined into the body, no chain - see
    # `stages.CHAINED_STRAND_KINDS`)
    base = tomllib.loads(SPEC)
    others = {p: spec.parse(dict(base, hair={"preset": p, "colour": [0.35, 0.22, 0.12]}), spec_path)
              for p in ("bun", "long_loose")}
    stage_names = {"ponytail": [s[0] for s in stages.STAGES if s[5](ch)]}
    stage_names.update({p: [s[0] for s in stages.STAGES if s[5](o)] for p, o in others.items()})
    strand_kinds = {"ponytail": stages.hair_strand_kind(ch)}
    strand_kinds.update({p: stages.hair_strand_kind(o) for p, o in others.items()})

    # after the hair stage the tail is loose, and the chain cannot be hung on a rig whose move set
    # is not authored yet; after the moves it still has no chain, so the export refuses
    part = runner.build(ch, to_stage="hair", save=False, log=lambda m: None)
    hair = part["hair"]["report"]
    loose = stages.strand_meshes(ch)
    refusals = {"strand_before_moves": stages.check_strand(ch)}
    runner.build(ch, to_stage="moves", save=False, log=lambda m: None)
    refusals["export_before_strand"] = stages.check_export(ch)
    refusals["strand_meshes"] = loose
    refusals["chained_before"] = stages.chained(ch)

    # the rest of it, then again: nothing to do
    full = runner.build(ch, save=False, log=lambda m: None)
    again = runner.build(ch, save=False, log=lambda m: None)

    strand = full["strand"]["report"]
    export = full["export"]["report"]
    body = bpy.data.objects[ch.mesh]
    tail = bpy.data.objects[loose[0]]
    manifest_path = export["moves"]
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    return {
        "stage_names": stage_names,
        "strand_kinds": strand_kinds,
        "chained_kinds": list(stages.CHAINED_STRAND_KINDS),
        "stages": _statuses(full),
        "rerun": _statuses(again),
        "hair": {"joined": hair["joined"], "strand_object": hair.get("strand_object"),
                 "strand_kind": hair.get("strand_kind"),
                 "parts": sorted(hair["parts"]), "contract": H.stable(hair["strand_contract"])},
        "refusals": H.stable(refusals),
        "strand": H.stable(strand),
        "strand_object": {"name": tail.name, "verts": len(tail.data.vertices),
                          "groups": sorted(g.name for g in tail.vertex_groups),
                          "materials": [m.name for m in tail.data.materials if m],
                          "face_order": H.face_order(tail),
                          "spec_keys": sorted(tail["follow_through"].keys())},
        "body": {"verts": len(body.data.vertices),
                 "materials": [m.name for m in body.data.materials if m],
                 "strand_group": "ft_strand" in [g.name for g in body.vertex_groups]},
        "export_strands": H.stable(dict(export["strands"], glb=os.path.basename(export["strands"]["glb"]))),
        "body_glb": _skeleton(export["glb"], "ft_strand_"),
        "hair_glb": _skeleton(export["strands"]["glb"], "ft_strand_"),
        "manifest": H.moves_manifest({"manifest": manifest, "problems": export.get("problems")}),
        "manifest_strands": manifest.get("strands"),
    }


H.run("pipeline_ponytail", build)
