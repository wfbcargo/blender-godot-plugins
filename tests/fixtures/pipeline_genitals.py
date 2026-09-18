"""Adult genital anatomy through character-pipeline, as neutral figure-study reference (`[body] genitals`).

A man and a woman are built from seeded briefs in TOML specs with `genitals = true`:

- the man (`genital_shape = { length = 0.4 }`, `[flesh] types = ["genital"]`, a draft Walk) through every stage:
  humanform's `genitals.keep` in the body stage (MPFB's `helper-genital` shell kept past the helper mask, the
  `hfg:penis-length-decr` target at 0.2), `genitals.fuse` in the bake stage (the shell subdivided, its footprint
  cut out of the body, the rim zipped to the shell's loop, the thighs' sweep cleared, pelvis-dominant weights),
  follow-through's `genital` flesh type (a jiggle bone on the pelvis at firm_flesh's 6 Hz, limit 0.3 x peak),
  and the glb read back for the geometry and `ft_jiggle_genital`;
- the body's surface after the fuse: open edges and connected pieces of the baked body (eyes and hair apart),
  and how far the shell goes into the thighs over the Walk (skinning only; the jiggle bone is Godot's);
- the woman through body and bake only: the `hfd:genital` relief key (mons, labia, cleft) folded in;
- a spec without `genitals` hashes its body section as before the field existed (no existing body rebuilds);
- the spec's refusals for the new fields.
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

MAN = '''
[character]
id = "fixstudyman"
name = "FixStudyMan"

[body]
sex = "male"
age = 32
stature = 1.79
build = "athletic"
seed = 11
firmness = 0.65
skin = [0.62, 0.44, 0.33]
genitals = true
genital_shape = { length = 0.4 }

[flesh]
types = ["genital"]

[moves]
gaits = { Walk = 0.2 }
style = "adult"
stance_width = 1.12

[build]
quality = "draft"

[review]
enabled = false

[export]
dir = "assets/fixstudyman"
res_dir = "res://assets/fixstudyman"
'''

WOMAN = '''
[character]
id = "fixstudywoman"
name = "FixStudyWoman"

[body]
sex = "female"
age = 30
stature = 1.67
build = "average"
seed = 12
skin = [0.86, 0.68, 0.57]
genitals = true

[moves]
gaits = { Walk = 0.2 }

[build]
quality = "draft"

[review]
enabled = false

[export]
dir = "assets/fixstudywoman"
res_dir = "res://assets/fixstudywoman"
'''


def _statuses(report):
    return {k: v["status"] for k, v in report.items() if isinstance(v, dict) and "status" in v}


def _surface(ob, skip_materials=()):
    """Open edges and connected pieces of `ob`'s faces, leaving out faces whose material is one of
    `skip_materials` (the eyes and hair joined into the body)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    names = [m.name if m else "" for m in ob.data.materials]
    keep = {f for f in bm.faces if not any(s in names[f.material_index].lower() for s in skip_materials)}
    open_edges = sum(1 for e in bm.edges if sum(1 for f in e.link_faces if f in keep) == 1)
    verts = {v for f in keep for v in f.verts}
    seen, pieces = set(), []
    for v in sorted(verts, key=lambda x: x.index):
        if v in seen:
            continue
        stack, n = [v], 0
        seen.add(v)
        while stack:
            x = stack.pop()
            n += 1
            for f in x.link_faces:
                if f not in keep:
                    continue
                for y in f.verts:
                    if y not in seen:
                        seen.add(y)
                        stack.append(y)
        pieces.append(n)
    bm.free()
    return {"open_edges": open_edges, "pieces": len(pieces), "largest": max(pieces) if pieces else 0}


def _shell_in_thighs(ob, rig, action, frames=6):
    """Per sampled frame of `action`: shell vertices (more than 2.5 cm from the join) standing more than 2 mm
    inside the rest of the body, and the deepest (mm)."""
    import bpy
    import numpy as np
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    at = ob.data.attributes["hf_genital"]
    m = np.zeros(len(ob.data.vertices), np.float32)
    at.data.foreach_get("value", m)
    shell = m > 0.5
    edges = np.array([e.vertices[:] for e in ob.data.edges])
    join = sorted({int(a) for a, b in edges if shell[a] and not shell[b]} |
                  {int(b) for a, b in edges if shell[b] and not shell[a]})
    rig.animation_data_create()
    act = bpy.data.actions[action]
    rig.animation_data.action = act
    if getattr(act, "slots", None):
        rig.animation_data.action_slot = act.slots[0]
    f0, f1 = (int(x) for x in act.frame_range)
    out = []
    for f in np.linspace(f0, f1, frames).astype(int):
        bpy.context.scene.frame_set(int(f))
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        faces = [p.vertices[:] for p in me.polygons if not any(shell[i] for i in p.vertices)]
        ev.to_mesh_clear()
        bvh = BVHTree.FromPolygons([Vector(c) for c in co], faces)
        jl = co[join]
        n_in, deep = 0, 0.0
        for i in np.nonzero(shell)[0]:
            if np.min(np.linalg.norm(jl - co[i], axis=1)) < 0.025:
                continue
            loc, nrm, _, _ = bvh.find_nearest(Vector(co[i]))
            s = (Vector(co[i]) - loc).dot(nrm)
            if s < -0.002:
                n_in += 1
                deep = max(deep, -s)
        out.append({"frame": int(f), "inside": n_in, "deepest_mm": round(deep * 1000, 1)})
    return out


def _glb(path):
    with open(path, "rb") as fh:
        b = fh.read()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    return {"jiggle_nodes": sorted(x["name"] for x in j["nodes"] if "jiggle" in x.get("name", "")),
            "meshes": sorted(m["name"] for m in j["meshes"]),
            "skins": len(j.get("skins", []))}


def build():
    import bpy
    import tomllib
    H.clear_scene()
    from character_pipeline import runner, spec

    root = os.path.join(H.out_dir(), "pipeline_genitals")
    os.makedirs(os.path.join(root, "characters"), exist_ok=True)
    quiet = dict(save=False, log=lambda m: None)

    def spec_file(name, text):
        path = os.path.join(root, "characters", name + ".toml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    man = spec.load(spec_file("fixstudyman", MAN))
    r = runner.build(man, **quiet)
    body_rep = r["body"]["report"]["genitals"]
    bake_rep = r["bake"]["report"]["genitals"]
    ob = bpy.data.objects[man.mesh]
    rig = bpy.data.objects[man.rig]
    regions = {g["name"]: {k: g.get(k) for k in ("type", "peak_m", "max_offset_m", "material")}
               for g in ob["follow_through"]["jiggle"]["regions"]} if "follow_through" in ob else {}
    for name, reg in regions.items():
        bone = rig.data.bones.get("ft_jiggle_" + name)
        reg["bone_parent"] = bone.parent.name if bone is not None and bone.parent else None
    shell_shares = bake_rep["weights"]["shares"]
    man_out = {
        "stages": _statuses(r),
        "body": H.stable(body_rep),
        "bake": H.stable({k: v for k, v in bake_rep.items() if k != "weights"}),
        "shares": H.stable(shell_shares, places=3),
        "pelvis_dominant": bool(shell_shares[bake_rep["weights"]["bone"]] > 0.8),
        "clearance": H.stable(bake_rep["weights"]["clearance"], places=4),
        "surface": _surface(ob, skip_materials=("sclera", "iris", "pupil", "hair")),
        "flesh_regions": H.stable(regions, places=4),
        "walk_in_thighs": _shell_in_thighs(ob, rig, f"{man.name}_Walk"),
        "glb": _glb(os.path.join(man.out_dir(), "fixstudyman.glb")),
        "unweighted": r["bake"]["report"]["unweighted"],
    }

    H.clear_scene()
    for t in list(bpy.data.texts):
        bpy.data.texts.remove(t)
    woman = spec.load(spec_file("fixstudywoman", WOMAN))
    r = runner.build(woman, to_stage="bake", **quiet)
    wrep = r["body"]["report"]["genitals"]
    wob = bpy.data.objects[woman.mesh]
    woman_out = {"stages": _statuses(r), "body": H.stable(wrep, places=4),
                 "bake_has_genitals": "genitals" in r["bake"]["report"],
                 "surface": _surface(wob, skip_materials=("sclera", "iris", "pupil", "hair"))}

    base = tomllib.loads(MAN)
    plain = dict(base, body={k: v for k, v in base["body"].items() if not k.startswith("genital")})
    plain_ch = spec.parse(plain)
    off = dict(base, body=dict(plain["body"], genitals=False))
    hashing = {"body_section_keys": sorted(plain_ch.section("body")),
               "explicit_false_same_digest": spec.parse(off).digest("body") == plain_ch.digest("body"),
               "on_differs": man.digest("body") != plain_ch.digest("body")}

    refusals = {}
    wbase = tomllib.loads(WOMAN)
    for label, data in (
            ("shape_on_woman", dict(wbase, body=dict(wbase["body"], genital_shape={"length": 0.4}))),
            ("shape_without_genitals", dict(base, body=dict(base["body"], genitals=False))),
            ("bad_shape_key", dict(base, body=dict(base["body"], genital_shape={"girth": 0.4}))),
            ("shape_range", dict(base, body=dict(base["body"], genital_shape={"length": 1.4}))),
            ("not_bool", dict(base, body=dict(base["body"], genitals="yes"))),
            ("blend_source", dict(base, body={"source": "blend", "object": "X", "genitals": True}))):
        try:
            spec.parse(data)
            refusals[label] = None
        except spec.SpecError as exc:
            refusals[label] = str(exc)

    return {"man": man_out, "woman": woman_out, "hashing": hashing, "refusals": refusals}


H.run("pipeline_genitals", build)
