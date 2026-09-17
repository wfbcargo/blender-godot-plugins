"""rig-anything's review sheet measures what it claims to (improvements 04 b).

A box on a one-bone rig, four clips, built from nothing:

- `Static`: every key the same pose. Eight identical cells, so `distinct_cells` must be 1 in every
  view. Before the render was undithered and cells compared with a tolerance it was 8: dither noise
  alone made every cell's bytes differ.
- `Tilt`: the bone leans up to 17 degrees forwards and 20 sideways. Every sampled frame is a visibly
  different pose, so `distinct_cells` is 8, and the lean reaches out of the rest body's cell, so its
  strips are centred and the cells widen: no cell is crossed.
- `Travel`: the pose never changes but the body moves 3 m sideways, several cell widths, like a
  jump that travels. Drawn where it stands (`centre_poses=False`) the boxes cross into the neighbouring
  cells, which `edge_cells` counts, and distinct_cells is 8 because each cell shows a different part of
  the box; centred (the default) no cell is crossed and it is one pose. Seen from the right it travels
  toward the camera, and must stay behind the floor line.
- `Dip`: the box sinks 0.35 m through the floor and then rises 0.9 m above where it stands, so the
  poses leave the rest body's frame downwards and upwards - a rabbit's JumpAir legs through the floor,
  a launch above the standing head. It is rendered as its own sheet (`spill`), because the bands are one
  height for the whole sheet: `bands_px` is [label, above, below] and must grow past the resting
  [45, 0, 13] at both ends, while `edge_cells` stays 0. Before the bands were grown from the evaluated
  poses the legs were simply cut off at row 0 and `edge_cells`, which looked only at the side columns,
  said 0.

The sheet is otherwise the export's: fixtures that export (cricket, rabbit, ...) record theirs.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS")


def _box_rig():
    import bpy
    H.clear_scene()
    arm = bpy.data.armatures.new("ReviewBox_arm")
    rig = bpy.data.objects.new("ReviewBox_rig", arm)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    b = arm.edit_bones.new("root")
    b.head, b.tail = (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    me = bpy.data.meshes.new("ReviewBox")
    # a tall box with a nose on its front (-Y), so a lean reads in every view
    verts = [(x, y, z) for z in (0.0, 1.6) for y in (-0.12, 0.12) for x in (-0.2, 0.2)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    nose = [(x, y, z) for z in (1.2, 1.4) for y in (-0.12, -0.3) for x in (-0.06, 0.06)]
    verts += nose
    faces += [tuple(8 + i for i in f) for f in faces[:6]]
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new("ReviewBox", me)
    bpy.context.scene.collection.objects.link(ob)
    vg = ob.vertex_groups.new(name="root")
    vg.add(list(range(len(me.vertices))), 1.0, "REPLACE")
    ob.modifiers.new("Armature", "ARMATURE").object = rig
    pb = rig.pose.bones["root"]
    pb.rotation_mode = "XYZ"
    rig.animation_data_create()
    for name in ("Static", "Tilt", "Travel", "Dip"):
        act = bpy.data.actions.new(name)
        act.use_fake_user = True
        rig.animation_data.action = act
        # Dip is keyed at the middle too: down through the floor, then up past the standing head
        for f in (1, 15, 29) if name == "Dip" else (1, 29):
            end = f == 29
            pb.rotation_euler = (0.3 if name == "Tilt" and end else 0.0, 0.0,
                                 0.35 if name == "Tilt" and end else 0.0)
            z = 0.0
            if name == "Dip":
                z = {1: 0.0, 15: -0.35, 29: 0.9}[f]
            # the bone points up, so its local Y is world up and its local X is world sideways
            pb.location = (3.0 if name == "Travel" and end else 0.0, z, 0.0)
            pb.keyframe_insert("rotation_euler", frame=f)
            pb.keyframe_insert("location", frame=f)
    rig.animation_data.action = None
    return rig.name, ob.name


def build():
    from rig_analysis import review
    rig, body = _box_rig()
    out = os.path.join(H.out_dir(), "review_sheet")
    centred = review.sheet([body], rig, ["Static", "Tilt", "Travel"], os.path.join(out, "centred"), loops=[])
    in_place = review.sheet([body], rig, ["Travel"], os.path.join(out, "in_place"), loops=[], centre_poses=False)
    # its own sheet: the bands are one height for the whole sheet, so `centred` keeps the resting bands
    spill = review.sheet([body], rig, ["Dip"], os.path.join(out, "spill"), loops=[])
    return {"centred": H.review_sheet(review.summary(centred)),
            "in_place": H.review_sheet(review.summary(in_place)),
            "spill": H.review_sheet(review.summary(spill))}


H.run("review_sheet", build)
