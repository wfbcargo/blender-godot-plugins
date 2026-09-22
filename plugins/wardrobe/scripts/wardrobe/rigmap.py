"""Which bones of a humanoid rig are the torso, the neck, the arms and the legs.

When rig-anything is importable its bone roles say so (`rig_analysis.bodymap.build(...)["roles"]`):
the spine runs from the `pelvis` role to the `head`, the torso ends at `chest` (where the arms
attach), and arms and legs are the `hand.*` and `foot.*` limbs. Without rig-anything, names do:
rig-anything's humanoid metarig names them spine .. spine.006, shoulder.L, upper_arm.L,
forearm.L, hand.L, thigh.L; Rigify's deform rig prefixes DEF-; the spine is walked from its root
through children called spine, neck or head, and the torso ends at the bone the arms hang from.

Every position here is in the body mesh's object space, which is where the garment is
built and fitted - the glTF exporter writes a skinned mesh in that space too.
"""

from __future__ import annotations

import bpy
from mathutils import Vector


def _obj(name):
    o = bpy.data.objects.get(name) if isinstance(name, str) else name
    if o is None:
        raise KeyError(f"no object {name!r}")
    return o


def rig_of(body):
    body = _obj(body)
    for m in body.modifiers:
        if m.type == "ARMATURE" and m.object is not None:
            return m.object
    if body.parent is not None and body.parent.type == "ARMATURE":
        return body.parent
    raise ValueError(f"{body.name} is not skinned to an armature")


def _find(bones, *candidates):
    for c in candidates:
        for prefix in ("", "DEF-", "ORG-"):
            if prefix + c in bones:
                return prefix + c
    return None


def humanoid(body):
    """Bone names and rest positions (body object space) of a humanoid rig.

    Returns {"rig", "spine": [..root to head..], "neck": [...], "arms": {"L": [upper, fore, hand],
    "R": ...}, "legs": {"L": [thigh, shin, foot], ...}, "heads": {bone: Vector}, "tails": {...}}.
    """
    body = _obj(body)
    rig = rig_of(body)
    bones = rig.data.bones
    to_body = body.matrix_world.inverted() @ rig.matrix_world
    names = set(bones.keys())
    heads = {n: to_body @ bones[n].head_local for n in names}
    tails = {n: to_body @ bones[n].tail_local for n in names}

    mapped = _from_roles(rig, body) or _from_names(rig)
    spine, torso, neck, arms, legs = mapped
    below = _below(rig, spine, arms, legs)
    if legs:
        hip_z = sum(heads[l["thigh"]].z for l in legs.values()) / len(legs)
    else:
        # no legs (a tail in their place, humanform.graft): the hips are where the pelvis begins
        hip_z = heads[spine[0]].z
    return {"rig": rig.name, "spine": spine, "torso": torso, "neck": neck, "arms": arms, "legs": legs,
            "below": below, "hip_z": hip_z,
            "heads": heads, "tails": tails, "up": Vector((0, 0, 1)), "forward": _forward(heads, arms)}


def _below(rig, spine, arms, legs):
    """The deform bones that hang from the pelvis and are neither spine, arm nor leg - a tail in the legs' place:
    a garment's lower cut takes them with the legs. [] on a person."""
    import re
    sided = re.compile(r"[._-]([LlRr])$")
    known = set(spine) | {b for a in arms.values() for b in a.values() if b} | \
        {b for l in legs.values() for b in l.values() if b}
    out = []
    bones = rig.data.bones
    stack = [c for c in bones[spine[0]].children if c.name not in known and not sided.search(c.name)]
    while stack:
        b = stack.pop()
        if b.use_deform:
            out.append(b.name)
        stack.extend(c for c in b.children if c.name not in known)
    return sorted(out)


def _from_roles(rig, body):
    """(spine, torso, neck, arms, legs) from rig-anything's bone roles, or None when rig-anything is
    not importable, knows no roles, or the roles do not describe a biped (a pelvis, a chest on the
    spine, and hand/foot limbs with no front/hind rank)."""
    try:
        from rig_analysis import bodymap
    except ImportError:
        return None
    bm = bodymap.build(rig.name, meshes=[body])
    roles = bm.get("roles") if isinstance(bm, dict) else None
    if not roles or not roles.get("pelvis") or not roles.get("head"):
        return None
    axial = bm["axial"]
    if roles["pelvis"] not in axial or roles["head"] not in axial:
        return None
    a, b = axial.index(roles["pelvis"]), axial.index(roles["head"])
    if a > b:
        return None
    tail = set(roles.get("tail") or ())
    spine = [n for n in axial[a:b + 1] if n not in tail]
    if roles.get("chest") not in spine:
        return None
    si = spine.index(roles["chest"])

    arms, legs = {}, {}
    for key, limb in (roles.get("limbs") or {}).items():
        end_word, _, side = key.rpartition(".")
        if limb["role"] == "arm" and end_word == "hand":
            arms[side] = {"shoulder": limb["girdle"], "upper": limb["upper"], "fore": limb["lower"],
                          "hand": limb["end"]}
        elif limb["role"] == "leg" and end_word == "foot":
            legs[side] = {"thigh": limb["upper"], "shin": limb["lower"], "foot": limb["end"]}
    if not arms or not legs:
        return None
    return spine, spine[:si + 1], spine[si + 1:], arms, legs


def _from_names(rig):
    """(spine, torso, neck, arms, legs) from bone names: the fallback without rig-anything."""
    bones = rig.data.bones
    names = set(bones.keys())

    spine = []
    root = _find(names, "spine", "hips", "pelvis", "Hips")
    b = bones.get(root) if root else None
    while b is not None:
        spine.append(b.name)
        nxt = [c for c in b.children if c.name.startswith(("spine", "DEF-spine", "neck", "head"))]
        b = nxt[0] if nxt else None
    if not spine:
        raise ValueError(f"{rig.name}: no spine chain found")

    arms, legs = {}, {}
    for side in ("L", "R"):
        upper = _find(names, f"upper_arm.{side}", f"UpperArm.{side}")
        fore = _find(names, f"forearm.{side}", f"LowerArm.{side}")
        hand = _find(names, f"hand.{side}", f"Hand.{side}")
        shoulder = _find(names, f"shoulder.{side}", f"Shoulder.{side}")
        thigh = _find(names, f"thigh.{side}", f"UpperLeg.{side}")
        shin = _find(names, f"shin.{side}", f"LowerLeg.{side}")
        foot = _find(names, f"foot.{side}", f"Foot.{side}")
        if upper:
            arms[side] = {"shoulder": shoulder, "upper": upper, "fore": fore, "hand": hand}
        if thigh:
            legs[side] = {"thigh": thigh, "shin": shin, "foot": foot}

    # the shoulder line: the spine bone the arms hang from; everything above it is neck/head
    shoulder_bone = None
    for side, a in arms.items():
        p = bones[a["shoulder"] or a["upper"]].parent
        while p is not None and p.name not in spine:
            p = p.parent
        if p is not None:
            shoulder_bone = p.name
    si = spine.index(shoulder_bone) if shoulder_bone in spine else int(len(spine) * 0.6)
    return spine, spine[:si + 1], spine[si + 1:], arms, legs


def _forward(heads, arms):
    """The way the body faces, from where its left arm is: measured, not assumed."""
    if "L" in arms and "R" in arms:
        left = heads[arms["L"]["upper"]] - heads[arms["R"]["upper"]]
        f = left.cross(Vector((0, 0, 1)))          # left x up = forward (left +X, up +Z -> -Y)
        if f.length > 1e-6:
            return f.normalized()
    return Vector((0, -1, 0))


def deform_names(obj):
    """Names of the vertex groups on `obj` that are deforming bones of its rig. Everything else -
    wd_ease, wd_hide_<garment>, a painted pin group - is data, never a skin weight."""
    obj = _obj(obj)
    rig = rig_of(obj)
    bones = {b.name for b in rig.data.bones if b.use_deform}
    return {vg.name for vg in obj.vertex_groups if vg.name in bones}


def chain_weights(body, bone_names):
    """Per-vertex summed weight of a set of bones (vertex index -> float)."""
    body = _obj(body)
    gi = {g.index for g in body.vertex_groups if g.name in bone_names}
    out = [0.0] * len(body.data.vertices)
    for v in body.data.vertices:
        s = 0.0
        for g in v.groups:
            if g.group in gi:
                s += g.weight
        out[v.index] = s
    return out
