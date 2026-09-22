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

A skirt or a dress hangs from a ring hinged just above the hip joints, and from the hip joints down
the cloth is the bones' outright (see `prepare`). It also carries **colliders**: capsules fitted to
the thighs and the shins (`_leg_colliders`, each carried up to the hip), which Godot's hem modifier
swings the bones out of.

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


def _level_out(v, down):
    """`v` without its component along `down`, normalised."""
    x = v - down * v.dot(down)
    return x.normalized() if x.length > 1e-6 else Vector((0, -1, 0))


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
            under=(), hinge_lift=0.05, skin_band=0.04, collider_margin=0.006):
    """`under`: garments that may be worn under this one; the backstop is measured to the nearest of
    them or the body, so a hem does not swing into a waistband.

    A skirt or a dress (tailor.skirt / tailor.dress) is hung differently. Its hem bones hang from the
    pelvis alone, hinged `hinge_lift` above the hip joints instead of `hem_hinge` above the edge, and
    from the hip joints down (over `skin_band` metres) the cloth is theirs outright: it turns as one panel
    and nothing of it follows a single thigh by weight. Weights that do split the tube round each leg, and
    a stride read as shorts or culottes (the hem between the legs, the legs out through slits - fig224).
    Above the hip joints the cloth keeps the skin's weights, so the hips carry it. It also raises the cut's
    `cover_floor_z` to the hinge, so cover (which runs after this) hides no skin under cloth the bones move.

    The block then carries `colliders`: capsules fitted to each thigh and shin (`_leg_colliders`,
    `collider_margin` added for the cloth and for the chord between two bones), and each bone's slack
    against them. In Godot the hem modifier folds the ring with the thighs and swings each bone out of
    the capsules, so a lifted thigh carries the front of the skirt over it and the cloth between the
    legs stays one panel."""
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
        hinge_z = None
        ring_hip_z = None
        if kind in ("skirt", "dress"):
            # a skirt's hem hangs from the pelvis, hinged at the hip joints, and the thighs push it (colliders);
            # offset half a bone, so none sits on the midline between the legs
            parents = [hm["spine"][0]]
            phase = 0.5
            cut = g.get("wardrobe_cut")
            hip_z = float(cut["hip_z"]) if cut is not None and "hip_z" in cut else \
                hm["hip_z"]
            hinge_z = hip_z + hinge_lift
            ring_hip_z = hip_z
            if cut is not None:
                # cover runs after this and hides no skin below `cover_floor_z`. The cut put it at the hip
                # joints, but the cloth is the hem bones' from the hinge down and they move it: on Rosa's
                # mini, 4 of the 30 vertices hidden in that band opened in a run (13% of them, a fail).
                # Nothing under moving cloth is hidden.
                rec = dict(cut)
                rec["cover_floor_z"] = round(hinge_z, 5)
                g["wardrobe_cut"] = rec
        rings.append({"ring": "hem", "loop": tags["hem"], "dir": -up, "centre": Vector((root.x, root.y, 0)),
                      "count": hem_bones, "hinge": hem_hinge, "ref": fwd,
                      "parents": parents, "phase": phase, "hinge_z": hinge_z, "hip_z": ring_hip_z})
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
            if r.get("hinge_z") is not None:
                head = gbvh.find_nearest(Vector((tail.x, tail.y, r["hinge_z"])))[0]
            else:
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
        rigid = r.get("hinge_z") is not None
        reach = max((rb["tail"] - rb["head"]).length for rb in ring_bones) if rigid else r["hinge"]
        band = fit.geodesic(bm, r["loop"], reach * 1.6)
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
            if rigid:
                # the bones take the cloth from the hip joints down, over `skin_band` metres; above that it
                # keeps the skin's weights, and cover hides that band (its weights agree with the skin's).
                # By the gap to the skin instead - the cloth that hangs free is the bones' - the front of a
                # knee skirt, close to the belly and the thighs at rest, went half with the skin and was left
                # inside the thighs in a crouch (14 vertices); by the greater of the two, 10 there and 12
                # inside a run's forward thigh. The hip crease, half one and half the other either way, is
                # where a run pinches the cloth and the hip comes through it; ease answers that (0.022).
                # From the *hinge* down instead - so that the thigh capsules could push the band of cloth
                # over the hip, which skin weights never let them - a run's raised thigh showed much less
                # through the front (Nadia's knee skirt, poke 21 -> 10), but a deep crouch then left the
                # cloth over the hip inside an abducted thigh and failed: 7 of 1088 against 1. The band
                # stays the skin's, and the collider carried up to the hip is what answers the run.
                s = (r["hip_z"] - v.co.z) / skin_band
            s = min(max(s, 0.0), 1.0)
            total = (1.0 if rigid else share) * s * s * (3 - 2 * s)
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
                # a skirt's: away from the body's axis, level - the way its colliders swing it
                **({"outward_dir": to_gltf(to_rig.to_3x3() @ _level_out(rb["tail"] - c, d))}
                   if r.get("hinge_z") is not None else {}),
                "inward_m": round(max(0.0, rb["gap"] - backstop_margin), 4),
                "max_offset_m": round(L * math.sin(math.radians(max_angle_deg)), 4),
                "frequency_hz": round(_frequency(L, fab), 3), "damping_ratio": fab["damping_ratio"],
                "response": fab["response"], "gravity_scale": 1.0,
            })
        r["summary"] = {"ring": r["ring"], "bones": n, "hinge_m": round(length, 3), "frequency_hz": round(freq, 2),
                        "weighted_verts": sum(1 for vi in band if extra[vi]),
                        "gap_min_m": round(min(rb["gap"] for rb in ring_bones), 4),
                        "parents": sorted({rb["parent"] for rb in ring_bones})}
    colliders = []
    if any(r.get("hinge_z") is not None for r in rings):
        hem_ring = next(r for r in rings if r.get("hinge_z") is not None)
        colliders, slack = _leg_colliders(b, hm, rig, [rb for rb in new_bones if rb["name"].startswith(prefix + "hem_")],
                                          collider_margin)
        for bo in bones_out:
            if bo["name"] in slack:
                bo["collider_slack_m"] = slack[bo["name"]]
        hem_ring["summary"]["colliders"] = [{"bone": c["bone"], "radii_m": c["radii_m"]} for c in colliders]
        hem_ring["summary"]["collider_slack_max_m"] = max((x for row in slack.values() for x in row), default=0.0)
        for c in colliders:
            c["head"] = to_gltf(to_rig @ c.pop("_head"))
            c["tail"] = to_gltf(to_rig @ c.pop("_tail"))
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
                      "share": share, "bones": bones_out, **({"colliders": colliders} if colliders else {})}}


COLLIDE_AT = (0.125, 0.25, 0.5, 0.75, 1.0)      # hem_modifier.gd's COLLIDE_AT: where along a hem bone it is tested


def _leg_colliders(body, hm, rig, hem_bones, margin, thigh_knots=(0.35, 0.55, 0.75, 1.0),
                   shin_knots=(0.0, 0.5, 1.0), band=0.1, pct=0.75, clear=0.004, thigh_top=0.12):
    """Capsules round the thighs and shins (body object space), fitted to the leg's skin: at each knot along a
    bone (fractions of its length) the cross-section of the skin within `band` of it - the vertices skinned
    mostly to that bone and to bones under it that are not the next bone of the leg (jiggle bones) - gives a
    centre (the middle of its extent across the bone) and a radius (the `pct` percentile of the distance to
    that centre, plus `margin`); a capsule joins each pair of neighbouring knots. The thigh is only *measured*
    from a third of the way down: above that its skin is the buttock and the groin, round the bone's line 14 cm
    out, and a collider fitted that big pushed the skirt off the hips in a stride.

    But it must not *stop* there. Measured from 0.35 down, the top 13 cm of the thigh - from the hip joint to
    the first knot - had no collider at all, and in a run the raised thigh went straight through the front
    panel above it (Nadia's knee skirt: 21 poking vertices, a wedge of thigh from the hem to the waistband in
    a front view, the critic's fig224 finding again). So the first capsule is carried up to `thigh_top` with
    the radius it was measured at and its centre slid along the bone: conservative where the thigh is widest,
    and the cloth resting on it at rest is not pushed, because that is what each bone's slack takes off.

    And for each hem bone, each capsule's `slack`: how far inside that capsule (plus `clear`) the bone already
    is at rest, at the worst of its test points. The runtime takes it off the radius for that bone alone, so
    cloth resting against a thigh is not pushed standing still. Returns (colliders, {hem bone: [slack]})."""
    names = {vg.index: vg.name for vg in body.vertex_groups}
    out = []
    for leg in hm["legs"].values():
        chain = [leg.get("thigh"), leg.get("shin")]
        for i, bone in enumerate(chain):
            if not bone or rig.data.bones.get(bone) is None:
                continue
            nxt = chain[i + 1] if i + 1 < len(chain) else leg.get("foot")
            own = {bone}
            for c in rig.data.bones[bone].children_recursive:
                if nxt and (c.name == nxt or nxt in {q.name for q in c.parent_recursive}):
                    continue
                own.add(c.name)
            a, t = hm["heads"][bone], hm["tails"][bone]
            ab = t - a
            L2 = max(ab.length_squared, 1e-9)
            axis = ab.normalized()
            ex = _ortho(axis, hm["forward"])
            ey = axis.cross(ex)
            pts = []
            for v in body.data.vertices:
                if sum(x.weight for x in v.groups if names.get(x.group) in own) >= 0.5:
                    pts.append(((v.co - a).dot(ab) / L2, v.co.copy()))
            knots = []
            for k in (thigh_knots if i == 0 else shin_knots):
                sec = [co for sv, co in pts if abs(sv - k) <= band]
                if len(sec) < 6:
                    continue
                on = a + ab * k
                xs = [(co - on).dot(ex) for co in sec]
                ys = [(co - on).dot(ey) for co in sec]
                centre = on + ex * ((min(xs) + max(xs)) * 0.5) + ey * ((min(ys) + max(ys)) * 0.5)
                d = sorted(((co - centre) - axis * (co - centre).dot(axis)).length for co in sec)
                knots.append((k, centre, d[int(pct * (len(d) - 1))] + margin))
            if i == 0 and knots and thigh_top < knots[0][0]:
                # carry the top of the thigh up to the hip, at the radius it was measured at
                k0, c0, r0 = knots[0]
                knots.insert(0, (thigh_top, c0 - ab * (k0 - thigh_top), r0))
            knots = [(c, r) for _, c, r in knots]
            for (c0, r0), (c1, r1) in zip(knots, knots[1:]):
                out.append({"bone": bone, "_head": c0, "_tail": c1, "radii_m": [round(r0, 4), round(r1, 4)]})
    slack = {}
    for hb in hem_bones:
        row = []
        for c in out:
            a, ab = c["_head"], c["_tail"] - c["_head"]
            L2 = max(ab.length_squared, 1e-9)
            worst = 0.0
            for f in COLLIDE_AT:
                p = hb["head"] + (hb["tail"] - hb["head"]) * f
                s = min(max((p - a).dot(ab) / L2, 0.0), 1.0)
                worst = max(worst, radius_at(c["radii_m"], s) + clear - (p - (a + ab * s)).length)
            row.append(round(worst, 4))
        slack[hb["name"]] = row
    return out, slack


def radius_at(radii, s):
    """A collider's radius at `s` (0 head, 1 tail): linear between its knots (as hem_modifier.gd)."""
    x = min(max(s, 0.0), 1.0) * (len(radii) - 1)
    k = min(int(x), len(radii) - 2)
    return radii[k] + (radii[k + 1] - radii[k]) * (x - k)


def summarize(rep):
    lines = [f"{rep['garment']}: {len(rep['block']['bones'])} hem bones on {rep['rig']} ({rep['fabric']}), "
             f"{rep['reweighted_verts']} verts reweighted"]
    for r in rep["rings"]:
        lines.append(f"  {r['ring']:7s} {r['bones']} bones, hinge {r['hinge_m']} m, {r['frequency_hz']} Hz, "
                     f"{r['weighted_verts']} verts, closest skin {r['gap_min_m']} m, on {', '.join(r['parents'])}")
    return "\n".join(lines)
