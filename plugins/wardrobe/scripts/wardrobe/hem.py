"""Sprung bones for the parts of a garment that hang free: the hem and the cuffs.

    rep = hem.prepare(shirt, "Figure", fabric="cotton_jersey")
    print(hem.summarize(rep))

A skinned garment moves exactly with the body - which is right at the shoulders and wrong at
a hem, which should swing after a stride and settle. Games do this with a ring of bones
around each opening: each bone hangs from a hinge line above the edge, parented to the torso
(or the upper arm for a cuff), and the fabric between hinge and edge is weighted to it,
feathered in from the hinge and across to its neighbours. In Godot a SkeletonModifier3D
springs each bone's tail after the animation (`hem_modifier.gd`).

Two things keep a hem out of the body, and both are measured here:

- the bones are parented to the torso, not the thighs, and take up to `share` of the edge's
  weight - so a lifting thigh no longer drags the hem up with it;
- each bone records how far its tail may swing *inward* before it reaches skin (the rest gap
  to the body, less a few millimetres): the runtime clamps the spring there. That is a
  per-bone **backstop**, the thing Unreal, Unity and Jolt use to keep cloth off the body.

Bones are named `wd_<garment>_<ring>_<nn>`. Re-running replaces them.
"""

from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import fit, rigmap

# Frequencies: a hanging flap is a pendulum, f = sqrt(g/L)/2pi, stiffened by the fabric's
# bending: f = sqrt(f_pendulum^2 + stiff_hz^2). Damping is air drag plus the fabric's own loss.
FABRICS = {
    "silk": {"stiff_hz": 0.4, "damping_ratio": 0.12, "response": 1.4, "note": "light, swings long"},
    "cotton_jersey": {"stiff_hz": 1.1, "damping_ratio": 0.28, "response": 1.0, "note": "T-shirt knit"},
    "cotton_poplin": {"stiff_hz": 1.6, "damping_ratio": 0.32, "response": 0.9, "note": "a dress shirt"},
    "wool": {"stiff_hz": 1.8, "damping_ratio": 0.4, "response": 0.8, "note": "a sweater"},
    "denim": {"stiff_hz": 3.0, "damping_ratio": 0.5, "response": 0.6, "note": "barely swings"},
    "leather": {"stiff_hz": 4.0, "damping_ratio": 0.55, "response": 0.5, "note": "a jacket hem"},
}

SPACE = "gltf_armature"


def to_gltf(v):
    return [round(v.x, 6), round(v.z, 6), round(-v.y, 6)]


def _frequency(length, fabric):
    fp = math.sqrt(9.81 / max(length, 0.01)) / (2 * math.pi)
    return math.sqrt(fp * fp + fabric["stiff_hz"] ** 2)


def _ortho(axis, hint):
    x = hint - axis * hint.dot(axis)
    if x.length < 1e-6:
        x = Vector((1, 0, 0)) - axis * axis.x
    return x.normalized()


def _remove_bones(rig, prefix):
    names = [b.name for b in rig.data.bones if b.name.startswith(prefix)]
    if not names:
        return 0
    with _edit(rig):
        for n in names:
            eb = rig.data.edit_bones.get(n)
            if eb is not None:
                rig.data.edit_bones.remove(eb)
    return len(names)


class _edit:
    """Edit mode on an armature, from the MCP session or `blender -b`."""

    def __init__(self, rig):
        self.rig = rig

    def __enter__(self):
        vl = bpy.context.view_layer
        if bpy.context.scene.objects.get(self.rig.name) is None:
            bpy.context.scene.collection.objects.link(self.rig)
        vl.update()
        self.prev = vl.objects.active
        vl.objects.active = self.rig
        bpy.ops.object.mode_set(mode="EDIT")
        return self.rig.data.edit_bones

    def __exit__(self, *exc):
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.objects.active = self.prev
        return False


def prepare(garment, body, fabric="cotton_jersey", hem_bones=8, cuff_bones=4, hem_hinge=0.14,
            cuff_hinge=0.06, share=0.8, backstop_margin=0.004, max_angle_deg=35.0, leg_bones=6, leg_hinge=0.08,
            under=()):
    """`under`: garments that may be worn under this one; the backstop is measured to the nearest of
    them or the body, so a hem does not swing into a waistband."""
    g = rigmap._obj(garment)
    b = rigmap._obj(body)
    hm = rigmap.humanoid(b)
    rig = bpy.data.objects[hm["rig"]]
    fab = dict(FABRICS[fabric]) if isinstance(fabric, str) else dict(fabric)
    prefix = f"wd_{g.name}_"
    removed = _remove_bones(rig, prefix)
    for vg in [vg for vg in g.vertex_groups if vg.name.startswith(prefix)]:
        g.vertex_groups.remove(vg)

    # garment and body surfaces (body object space == garment object space: tailor keeps them equal)
    bm = bmesh.new()
    bm.from_mesh(g.data)
    bm.verts.ensure_lookup_table()
    kind = fit.kind_of(g)
    tags = fit.tag_loops(fit.boundary_loops(bm), kind)
    me = g.data
    gbvh = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], fit.canonical_tris(me),
                                all_triangles=True)
    bbvh, _, _ = fit.body_bvh(b)
    stops = [bbvh] + [fit.body_bvh(o)[0] for o in under]
    up = Vector((0, 0, 1))
    fwd = hm["forward"]
    to_rig = rig.matrix_world.inverted() @ b.matrix_world

    rings = []
    if hem_bones and "hem" in tags:
        root = hm["heads"][hm["spine"][0]]
        parents = list(hm["torso"])
        phase = 0.0
        if kind in ("skirt", "dress"):
            # a skirt's hem is held by the thighs as much as the hips: each bone hangs from whichever of
            # the torso and the thighs holds the fabric at its hinge, so a lifted thigh carries the front
            # of the hem instead of passing through it; offset half a bone, so none sits on the midline
            # between the legs, split evenly between them
            parents += [l["thigh"] for l in hm["legs"].values()]
            phase = 0.5
        rings.append({"ring": "hem", "loop": tags["hem"], "dir": -up, "centre": Vector((root.x, root.y, 0)),
                      "count": hem_bones, "hinge": hem_hinge, "ref": fwd,
                      "parents": parents, "phase": phase})
    if kind == "pants":
        cut = g.get("wardrobe_cut")
        on_shin = float(cut.get("leg", 2.0)) > 1.0
        for side in ("L", "R"):
            key = "leg." + side
            if leg_bones and key in tags and side in hm["legs"]:
                bone = hm["legs"][side]["shin" if on_shin else "thigh"]
                d = (hm["tails"][bone] - hm["heads"][bone]).normalized()
                c = sum((v.co for v in tags[key]), Vector()) / len(tags[key])
                rings.append({"ring": key, "loop": tags[key], "dir": d, "centre": c, "count": leg_bones,
                              "hinge": leg_hinge, "ref": fwd, "parents": [bone]})
    for side in ("L", "R") if kind != "pants" else ():
        key = "cuff." + side
        if cuff_bones and key in tags and side in hm["arms"]:
            cut = g.get("wardrobe_cut")
            long_sleeve = cut is not None and float(cut.get("sleeve", 0.0)) > 1.0
            upper = hm["arms"][side]["fore" if long_sleeve else "upper"]
            d = (hm["tails"][upper] - hm["heads"][upper]).normalized()
            c = sum((v.co for v in tags[key]), Vector()) / len(tags[key])
            rings.append({"ring": key, "loop": tags[key], "dir": d, "centre": c, "count": cuff_bones,
                          "hinge": cuff_hinge, "ref": fwd, "parents": [upper]})

    group_names = {vg.index: vg.name for vg in g.vertex_groups}
    bones = {bn.name for bn in rig.data.bones if bn.use_deform}
    weights = [{group_names[x.group]: x.weight for x in v.groups if group_names[x.group] in bones}
               for v in me.vertices]
    extra = [dict() for _ in me.vertices]
    bones_out = []
    new_bones = []

    for r in rings:
        d, c = r["dir"], r["centre"]
        ex = _ortho(d, r["ref"])
        ey = d.cross(ex)

        def angle(p):
            q = p - c
            q = q - d * q.dot(d)
            return math.atan2(q.dot(ey), q.dot(ex)) % (2 * math.pi)

        loop = [(angle(v.co), v) for v in r["loop"]]
        n = r["count"]
        ring_bones = []
        for k in range(n):
            th = 2 * math.pi * (k + r.get("phase", 0.0)) / n
            tail_v = min(loop, key=lambda t: min(abs(t[0] - th), 2 * math.pi - abs(t[0] - th)))[1]
            tail = tail_v.co.copy()
            head = gbvh.find_nearest(tail - d * r["hinge"])[0]
            # parent: the listed bone that holds the fabric at the hinge most
            near = [v for v in bm.verts if (v.co - head).length < 0.05]
            best, best_w = r["parents"][0], -1.0
            for pn in r["parents"]:
                s = sum(weights[v.index].get(pn, 0.0) for v in near)
                if s > best_w:
                    best, best_w = pn, s
            # backstop: how far the tail may move toward the skin
            hits = [t.find_nearest(tail) for t in stops]
            hit = min((h for h in hits if h[0] is not None), key=lambda h: h[3])
            inward = (hit[0] - tail)
            gap = inward.length
            ring_bones.append({"name": f"{prefix}{r['ring'].replace('.', '_')}_{k:02d}", "parent": best,
                               "head": head, "tail": tail, "theta": th, "gap": gap,
                               "inward_dir": inward.normalized() if gap > 1e-6 else -d})

        # weights: feather from the hinge to the edge, and across to the two nearest bones
        band = fit.geodesic(bm, r["loop"], r["hinge"] * 1.6)
        for vi in band:
            v = bm.verts[vi]
            a = angle(v.co)
            f = a / (2 * math.pi) * n - r.get("phase", 0.0)
            k0 = int(math.floor(f)) % n
            k1 = (k0 + 1) % n
            t = f - math.floor(f)
            b0, b1 = ring_bones[k0], ring_bones[k1]
            hp = (b0["head"] - c).dot(d) * (1 - t) + (b1["head"] - c).dot(d) * t
            tp = (b0["tail"] - c).dot(d) * (1 - t) + (b1["tail"] - c).dot(d) * t
            s = ((v.co - c).dot(d) - hp) / (tp - hp) if abs(tp - hp) > 1e-6 else 0.0
            s = min(max(s, 0.0), 1.0)
            total = share * s * s * (3 - 2 * s)
            if total <= 1e-4:
                continue
            extra[vi][b0["name"]] = extra[vi].get(b0["name"], 0.0) + total * (1 - t)
            extra[vi][b1["name"]] = extra[vi].get(b1["name"], 0.0) + total * t

        length = sum((rb["tail"] - rb["head"]).length for rb in ring_bones) / n
        freq = _frequency(length, fab)
        for rb in ring_bones:
            new_bones.append(rb)
            L = (rb["tail"] - rb["head"]).length
            bones_out.append({
                "name": rb["name"], "ring": r["ring"], "parent": rb["parent"],
                "head": to_gltf(to_rig @ rb["head"]), "tail": to_gltf(to_rig @ rb["tail"]),
                "inward_dir": to_gltf(to_rig.to_3x3() @ rb["inward_dir"]),
                "inward_m": round(max(0.0, rb["gap"] - backstop_margin), 4),
                "max_offset_m": round(L * math.sin(math.radians(max_angle_deg)), 4),
                "frequency_hz": round(_frequency(L, fab), 3), "damping_ratio": fab["damping_ratio"],
                "response": fab["response"], "gravity_scale": 1.0,
            })
        r["summary"] = {"ring": r["ring"], "bones": n, "hinge_m": round(length, 3), "frequency_hz": round(freq, 2),
                        "weighted_verts": sum(1 for vi in band if extra[vi]),
                        "gap_min_m": round(min(rb["gap"] for rb in ring_bones), 4),
                        "parents": sorted({rb["parent"] for rb in ring_bones})}
    bm.free()

    # the bones, in the rig, pointing from hinge to edge
    with _edit(rig) as ebs:
        for rb in new_bones:
            eb = ebs.new(rb["name"])
            eb.head = to_rig @ rb["head"]
            eb.tail = to_rig @ rb["tail"]
            eb.parent = ebs[rb["parent"]]
            eb.use_connect = False
            eb.use_deform = True
            eb.align_roll(to_rig.to_3x3() @ -rb["inward_dir"])
            eb["wd_role"] = "hem"      # rig-anything's bodymap leaves tagged bones out of the body

    # merge weights: the bones take `total`, the old influences keep the rest; four a vertex
    for rb in new_bones:
        if rb["name"] not in g.vertex_groups:
            g.vertex_groups.new(name=rb["name"])
    changed = 0
    dropped_worst = 0.0
    for i, ex in enumerate(extra):
        if not ex:
            continue
        total = sum(ex.values())
        merged = {k: w * (1 - total) for k, w in weights[i].items()}
        for k, w in ex.items():
            merged[k] = merged.get(k, 0.0) + w
        top = sorted(merged.items(), key=lambda kv: -kv[1])
        kept = top[:4]
        s = sum(w for _, w in kept)
        dropped_worst = max(dropped_worst, 1 - s / (sum(w for _, w in top) or 1))
        for k in weights[i]:
            g.vertex_groups[k].remove([i])
        for k, w in kept:
            g.vertex_groups[k].add([i], w / s, "REPLACE")
        changed += 1

    return {"garment": g.name, "rig": rig.name, "fabric": fabric if isinstance(fabric, str) else "custom",
            "removed_bones": removed, "rings": [r["summary"] for r in rings], "reweighted_verts": changed,
            "worst_dropped_share": round(dropped_worst, 3),
            "block": {"space": SPACE, "fabric": fabric if isinstance(fabric, str) else "custom",
                      "share": share, "bones": bones_out}}


def summarize(rep):
    lines = [f"{rep['garment']}: {len(rep['block']['bones'])} hem bones on {rep['rig']} ({rep['fabric']}), "
             f"{rep['reweighted_verts']} verts reweighted"]
    for r in rep["rings"]:
        lines.append(f"  {r['ring']:7s} {r['bones']} bones, hinge {r['hinge_m']} m, {r['frequency_hz']} Hz, "
                     f"{r['weighted_verts']} verts, closest skin {r['gap_min_m']} m, on {', '.join(r['parents'])}")
    return "\n".join(lines)
