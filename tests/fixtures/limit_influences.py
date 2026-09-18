"""follow-through's `flesh.limit_influences` keeps each vertex's total deform weight (the 0.6.1 fix).

glTF carries four joints per vertex, so after the jiggle weights go on, `limit_influences` keeps each
vertex's four strongest bone weights and scales them back up to the vertex's old total. Before 0.6.1 it
removed the weakest groups and then wrote the kept weights through `VertexGroupElement`s read before the
removal; removing a group compacts `v.groups`, so those elements pointed at the wrong slot or none, the kept
weights were never scaled back up, and a vertex lost the dropped share of its total (up to 22 % on the sample
Figure; notebook realism-step0/cp-resume-hashes). Nothing checked it directly: `flesh_figure`'s
`prepare_again` only saw it through a second `flesh.prepare`.

The body here is 64 loose vertices on an eight-bone armature, weighted by a fixed formula: one to eight
bone influences per vertex, each vertex's groups added in its own order (so the dropped groups sit first,
in the middle and last in `v.groups`), bone groups created interleaved with two non-bone groups (a mask and a
note, which must be left alone), a zero-weight bone entry on some vertices, and every vertex's bone weights
scaled to a total between 0.6 and 1.0 (not normalised, like the sample Figure; below 1, so no kept weight
scaled up can reach Blender's clamp at 1.0 and hide a loss). What is measured, against the weights before:

- `max_total_lost`: the largest drop in a vertex's total bone weight - the free value, signed, never clamped;
- `max_total_gained`: the largest rise (a write to the wrong group can add as well as lose);
- `over_four`: vertices left with more than four bone influences;
- `not_strongest`: vertices whose kept groups are not their four strongest before;
- `ratio_spread`: the largest spread, within a vertex, of kept weight after / before (a renormalisation
  scales every kept weight by the same factor);
- `other_groups_moved`: vertices whose non-bone group weights changed;
- `untouched_moved`: vertices with four or fewer influences whose weights changed at all;
- `changed` against `expected_changed`: the count the function returns and the count with more than four.

The **control** runs the pre-0.6.1 write (`_stale_write`, bd22728's loop verbatim) on a fresh copy of the same
body and must fail the same check: the fixture raises if the fix fails or if the control passes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("FT_SCRIPTS")

BONES = 8
VERTS = 64
MOST = 4
EPS = 1e-5          # float32 weights of order 1: rounding stays near 1e-7


def _stale_write(obj, rig, most=4):
    """`limit_influences` as it was before follow-through 0.6.1 (bd22728): the control, never used to build."""
    bones = {b.name for b in rig.data.bones}
    changed = 0
    for v in obj.data.vertices:
        deform = [x for x in v.groups if obj.vertex_groups[x.group].name in bones and x.weight > 0.0]
        if len(deform) <= most:
            continue
        deform.sort(key=lambda x: x.weight, reverse=True)
        keep = deform[:most]
        total = sum(x.weight for x in deform)
        kept = sum(x.weight for x in keep) or 1.0
        for x in deform[most:]:
            obj.vertex_groups[x.group].remove([v.index])
        for x in keep:
            x.weight = x.weight / kept * total
        changed += 1
    return changed


def _body(name):
    """The weighted vertices and their armature (see the module docstring)."""
    import bpy
    arm = bpy.data.armatures.new(name + "_arm")
    rig = bpy.data.objects.new(name + "_rig", arm)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for i in range(BONES):
        b = arm.edit_bones.new(f"bone{i}")
        b.head = (i * 0.1, 0.0, 0.0)
        b.tail = (i * 0.1, 0.0, 0.1)
    bpy.ops.object.mode_set(mode="OBJECT")

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(i * 0.01, 0.0, 0.0) for i in range(VERTS)], [], [])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    # bone groups interleaved with two groups no bone has: group index order is not bone order
    order = ["bone0", "mask", "bone1", "bone2", "note", "bone3", "bone4", "bone5", "bone6", "bone7"]
    for g in order:
        obj.vertex_groups.new(name=g)
    for v in range(VERTS):
        k = 1 + v % BONES                                   # 1..8 bone influences
        start = (v * 3) % BONES
        picked = [(start + j * 3) % BONES for j in range(k)]  # 3 is prime to 8: k distinct bones
        raw = [0.05 + ((v * 7 + j * 13) % 17) / 20.0 + j * 1e-3 for j in range(k)]   # distinct weights
        scale = (0.6 + 0.4 * ((v * 5) % 9) / 8.0) / sum(raw)                          # total 0.6..1.0
        # the order the groups go on this vertex: rotated per vertex, so the weakest land anywhere in v.groups
        rot = v % k
        for j in list(range(rot, k)) + list(range(rot)):
            obj.vertex_groups[f"bone{picked[j]}"].add([v], raw[j] * scale, "REPLACE")
        if v % 5 == 0:
            obj.vertex_groups["mask"].add([v], 0.25 + (v % 4) * 0.1, "REPLACE")
        if v % 7 == 0:
            obj.vertex_groups["note"].add([v], 0.9, "REPLACE")
        if v % 6 == 0 and k < BONES:                      # a bone entry at zero weight: not an influence
            spare = next(b for b in range(BONES) if b not in picked)
            obj.vertex_groups[f"bone{spare}"].add([v], 0.0, "REPLACE")
    return obj, rig


def _weights(obj):
    names = {g.index: g.name for g in obj.vertex_groups}
    return [{names[x.group]: x.weight for x in v.groups} for v in obj.data.vertices]


def _judge(before, after, changed):
    """The measurements of the module docstring, and whether they pass."""
    def bone(d):
        return {k: w for k, w in d.items() if k.startswith("bone") and w > 0.0}

    lost = gained = spread = 0.0
    over = not_strongest = others = untouched = expected = 0
    for b, a in zip(before, after):
        bb, ab = bone(b), bone(a)
        tb, ta = sum(bb.values()), sum(ab.values())
        lost, gained = max(lost, tb - ta), max(gained, ta - tb)
        over += len(ab) > MOST
        if {k: w for k, w in b.items() if not k.startswith("bone")} != {k: w for k, w in a.items()
                                                                          if not k.startswith("bone")}:
            others += 1
        if len(bb) <= MOST:
            untouched += b != a
            continue
        expected += 1
        strongest = set(sorted(bb, key=bb.get, reverse=True)[:MOST])
        not_strongest += set(ab) != strongest
        ratios = [ab[k] / bb[k] for k in ab if k in bb]
        if ratios:
            spread = max(spread, max(ratios) - min(ratios))
    out = {"max_total_lost": round(lost, 6), "max_total_gained": round(gained, 6), "over_four": over,
           "not_strongest": not_strongest, "ratio_spread": round(spread, 6), "other_groups_moved": others,
           "untouched_moved": untouched, "changed": changed, "expected_changed": expected}
    out["ok"] = (lost <= EPS and gained <= EPS and over == 0 and not_strongest == 0 and spread <= EPS
                 and others == 0 and untouched == 0 and changed == expected)
    return out


def _limited(obj, rig, fn):
    """(weights after `fn` limits the body, the count `fn` returns)."""
    changed = fn(obj, rig, MOST)
    return _weights(obj), changed


def build():
    from follow_through import flesh

    obj, rig = _body("Fixed")
    before = _weights(obj)
    fixed = _judge(before, *_limited(obj, rig, flesh.limit_influences))

    cobj, crig = _body("Stale")
    if _weights(cobj) != before:
        raise AssertionError("limit_influences: the control's body is not weighted like the checked one")
    control = _judge(before, *_limited(cobj, crig, _stale_write))

    influences = {}
    for d in before:
        n = sum(1 for k, w in d.items() if k.startswith("bone") and w > 0.0)
        influences[n] = influences.get(n, 0) + 1
    report = {"fixed": fixed, "control": control, "vertices": VERTS,
              "influences_before": {str(k): influences[k] for k in sorted(influences)}}
    if not fixed["ok"]:
        raise AssertionError(f"limit_influences does not keep the weights: {fixed}")
    if control["ok"]:
        raise AssertionError(f"limit_influences control (the pre-0.6.1 write) passed the check: {control}")
    return report


H.run("limit_influences", build)
