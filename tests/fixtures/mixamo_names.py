"""The same body under Mixamo's bone names must get the same roles (improvements 02).

Bone roles are derived from structure - which chains hang off the spine, which reach the ground,
where the chain ends - with names only as tie-breakers. This proves it on the one naming scheme a
downloaded character is most likely to carry: follow-through's `Figure`, fitted with Rigify
`basic_human` and bound, has its roles read; then every bone and its vertex group is renamed to
`mixamorig:Hips` ... `mixamorig:LeftToeBase`, the roles are read again, and each named role is mapped
back through the rename and compared. `same` is the check; `differences` names any role that moved,
and the Mixamo roles and warnings are kept so a change in either shows.

No moves and no export: a rename changes nothing a move reads except names.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "FT_SCRIPTS")

BODY = "Figure"
# Rigify basic_human -> Mixamo. Mixamo has one neck bone and no heel; the Figure's second neck bone
# and its heel helpers get names in the same style.
MIXAMO = {
    "spine": "Hips", "spine.001": "Spine", "spine.002": "Spine1", "spine.003": "Spine2",
    "spine.004": "Neck", "spine.005": "Neck1", "spine.006": "Head",
    "shoulder.L": "LeftShoulder", "upper_arm.L": "LeftArm", "forearm.L": "LeftForeArm", "hand.L": "LeftHand",
    "shoulder.R": "RightShoulder", "upper_arm.R": "RightArm", "forearm.R": "RightForeArm", "hand.R": "RightHand",
    "thigh.L": "LeftUpLeg", "shin.L": "LeftLeg", "foot.L": "LeftFoot", "toe.L": "LeftToeBase",
    "thigh.R": "RightUpLeg", "shin.R": "RightLeg", "foot.R": "RightFoot", "toe.R": "RightToeBase",
    "heel.02.L": "LeftHeel", "heel.02.R": "RightHeel",
}
PREFIX = "mixamorig:"


def _mapped(value, table):
    if isinstance(value, str):
        return table.get(value, value)
    if isinstance(value, list):
        return [_mapped(v, table) for v in value]
    if isinstance(value, dict):
        return {k: _mapped(v, table) for k, v in value.items()}
    return value


def build():
    import bpy
    H.clear_scene()
    from follow_through import samples
    from rig_analysis import bodymap

    made = samples.build_bodies(rig=True, walk=False, rig_anything=H.scripts("RA_SCRIPTS"))
    rig_name = made["bodies"][BODY]["rig"]
    rig = bpy.data.objects[rig_name]
    before = bodymap.build(rig_name)["roles"]

    unknown = sorted(b.name for b in rig.data.bones if b.name not in MIXAMO)
    table = {old: PREFIX + new for old, new in MIXAMO.items()}
    body = bpy.data.objects[BODY]
    for old, new in table.items():
        b = rig.data.bones.get(old)
        if b is not None:
            b.name = new                           # Blender renames the vertex groups with it
        g = body.vertex_groups.get(old)
        if g is not None:
            g.name = new
    after = bodymap.build(rig_name)["roles"]

    compared = ("root", "pelvis", "chest", "neck", "head", "tail", "breast_anchor", "butt_anchor",
                "limbs", "controls", "unskinned", "skinned")
    expected = {k: _mapped(before[k], table) for k in compared}
    unordered = ("controls", "unskinned")          # sorted by name, and a rename reorders them
    differences = sorted(k for k in compared
                         if (sorted(expected[k]) != sorted(after[k]) if k in unordered
                             else expected[k] != after[k]))
    return {
        "renamed": len(table),
        "not_in_table": unknown,
        "same": not differences,
        "differences": {k: {"rigify_mapped": H.stable(expected[k]), "mixamo": H.stable(after[k])}
                        for k in differences},
        "roles": H.stable(after),
    }


H.run("mixamo_names", build)
