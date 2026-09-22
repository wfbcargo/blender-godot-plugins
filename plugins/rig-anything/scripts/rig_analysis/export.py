"""Export a rigged, animated asset - and the numbers an engine needs to play it.

Phase 5. Building the skeleton and the walk is not the end of the job. A clip
that verifies perfectly inside Blender can still slide its feet in the engine,
because the engine is not playing the clip Blender authored:

  - Blender's cycle is `hi - lo` frames, since the duplicated final frame exists
    only to close the loop. glTF exports every keyed frame, so the engine
    imports `hi - lo + 1` and loops over all of them.
  - The two periods differ by one frame-interval. Time-scale against the wrong
    one and the feet skate, by 4% on a 25-frame run cycle.

That bug shipped. It was found by hand, in a game project, weeks after the clip
was exported and pronounced good. So this module does not hand back a single
"speed" and leave the caller to guess which period it belongs to: it exports,
then reads the written file back and reports the duration the engine will
actually see, measured rather than predicted.

The house rule applies to export as much as to rigging - a generated asset
fails quietly. A rig off its origin still animates and merely orbits. An
optimised-away keyframe still plays, at the wrong length. Assert on both.
"""

import fnmatch
import json
import math
import os
import struct

import bpy

from . import verify

# glTF chunk type for the embedded JSON, little-endian 'JSON'.
_GLB_JSON_CHUNK = 0x4E4F534A
_GLB_MAGIC = 0x46546C67

# Godot rewrites these out of node names, silently breaking any get_node() path
# or animation track that assumed the Blender spelling.
_GODOT_ILLEGAL = set(".:@/\"%")


def _fps():
    return bpy.context.scene.render.fps or 24


def _obj(name):
    return bpy.data.objects.get(name)


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------

def _shape_keys_live(mesh):
    """Names of shape keys that change the mesh: unmuted, non-basis, value != 0."""
    keys = mesh.data.shape_keys
    if keys is None:
        return []
    blocks = keys.key_blocks
    return [k.name for k in blocks[1:]
            if not k.mute and abs(k.value) > 1e-6 and k.relative_key != k]


def _bake_block(rig):
    """(profile name or None, the `bake` block of the rig's body profile or {}). See
    `bodymap.load_profile`; a missing key means today's default."""
    from . import bodymap
    profile = bodymap.load_profile(rig)
    return (profile["name"], profile.get("bake") or {}) if profile else (None, {})


def _over_influenced(mesh, rig, most=4):
    """How many vertices more than `most` deform bones pull on."""
    deform = {b.name for b in rig.data.bones if b.use_deform}
    names = {g.index: g.name for g in mesh.vertex_groups}
    return sum(1 for v in mesh.data.vertices
               if sum(1 for g in v.groups if g.weight > 0.0 and names.get(g.group) in deform) > most)


def preflight(mesh_name, rig_name, tolerance=0.01, actions=None):
    """Everything that makes an export silently wrong, checked before writing.

    None of these raise in Blender and none of them raise in the engine. They
    just produce an asset that is subtly, permanently incorrect - which is why
    they are worth a pass of their own rather than a comment in the procedure.

    Problems (block `export` unless forced):
      - rig off origin, unapplied scale, no Armature modifier, node names Godot
        rewrites
      - `actions` keying a bone on a rotation its mode ignores - the clip would
        export as the rest pose
      - shape keys with a non-zero value. They are the body's shape in Blender
        and ship as glTF morph targets, so what the engine shows depends on it
        applying their default weights. Bake them (`bake_for_game`), or zero
        them if they really are morph targets.
    Warnings:
      - a Mask modifier: the hidden geometry is only removed because modifiers
        are applied on export; `bake_for_game` makes that permanent
      - vertices pulled by more than 4 bones: the exporter keeps the 4
        heaviest and renormalises, so they deform differently in the engine

    The rig's body profile (`bodymap.load_profile`) names what its source
    carries: a `bake` block with `shape_keys: false` makes live shape keys a
    warning (they are meant to ship as morph targets), a mask in its
    `mask_modifiers` is named as the source's own, and `max_influences`
    replaces 4.
    """
    mesh, rig = _obj(mesh_name), _obj(rig_name)
    problems, warnings = [], []

    if rig is None or rig.type != "ARMATURE":
        return {"error": "no armature named " + repr(rig_name)}
    if mesh is None or mesh.type != "MESH":
        return {"error": "no mesh named " + repr(mesh_name)}

    # 1. Origin. An exported root carrying a translation orbits instead of
    #    turning in place. A compensating parent empty hides this in Blender's
    #    viewport and does not survive the trip.
    origin = verify.check_export_origin(rig_name, mesh_name, tolerance=tolerance)
    if not origin.get("passed"):
        problems.append("rig off origin: " + origin.get("note", ""))

    # 2. Unapplied transforms. Scale on the object rather than the data is
    #    exported as a node transform, so the character arrives the right size
    #    but its animation amplitudes no longer match the metres the gait was
    #    measured in.
    for o in (rig, mesh):
        s = tuple(round(v, 5) for v in o.scale)
        if s != (1.0, 1.0, 1.0):
            problems.append("%s has unapplied scale %s - apply it, the gait was "
                            "measured in world metres" % (o.name, list(s)))
        rot = tuple(round(math.degrees(v), 3) for v in o.rotation_euler)
        if rot != (0.0, 0.0, 0.0) and o is rig:
            warnings.append("%s has unapplied rotation %s deg" % (o.name, list(rot)))

    # 3. The armature must actually deform the mesh, or it exports as a static
    #    mesh that happens to sit next to a skeleton.
    if not any(m.type == "ARMATURE" and m.object is rig for m in mesh.modifiers):
        problems.append("%s has no Armature modifier bound to %s - it would "
                        "export as static geometry" % (mesh_name, rig_name))

    # 4. Names Godot rewrites. Bone names live inside the skeleton and survive;
    #    object names become node names and do not.
    bad_objects = [o.name for o in (mesh, rig)
                   if any(c in _GODOT_ILLEGAL for c in o.name)]
    if bad_objects:
        problems.append("object names contain characters Godot strips from node "
                        "names: " + ", ".join(bad_objects))
    bad_bones = [b.name for b in rig.data.bones
                 if any(c in _GODOT_ILLEGAL for c in b.name)]
    if bad_bones:
        warnings.append(
            "%d bone names use '.' (e.g. %s). Bone names are not node names so "
            "this normally survives, but it is not the spelling Godot's humanoid "
            "retargeting profile expects - prefer _L/_R if you retarget."
            % (len(bad_bones), ", ".join(bad_bones[:3])))

    # 5. Keys the bones would ignore. A quaternion key on an Euler bone exports
    #    a clip of the rest pose, and every clip check on it passes.
    for name in actions or []:
        if bpy.data.actions.get(name) is None:
            continue
        m = verify.rotation_mode_mismatches(rig_name, name)
        if m.get("mismatches"):
            problems.append("%s: %s" % (name, m["note"]))

    # 6. What the mesh is made of in Blender and not in the file.
    profile, bake = _bake_block(rig)
    live = _shape_keys_live(mesh)
    if live and bake.get("shape_keys") is False:
        warnings.append("%s has %d shape keys with a value (%s) - profile %s ships them as morph "
                        "targets, so the engine must apply their weights"
                        % (mesh_name, len(live), ", ".join(live[:3]) + ("..." if len(live) > 3 else ""),
                           profile))
    elif live:
        problems.append("%s has %d shape keys with a value (%s) - they would ship as morph "
                        "targets rather than as the body's shape; bake them with "
                        "export.bake_for_game" % (mesh_name, len(live), ", ".join(live[:3])
                                                  + ("..." if len(live) > 3 else "")))
    masks = [m.name for m in mesh.modifiers if m.type == "MASK"]
    if masks:
        warnings.append("%s has Mask modifiers (%s) - the hidden geometry is dropped only "
                        "because modifiers are applied on export; bake_for_game makes it "
                        "permanent%s" % (mesh_name, ", ".join(masks),
                                         "" if not set(masks) & set(bake.get("mask_modifiers") or ())
                                         else " (the %s source's own helper mask)" % profile))
    most = int(bake.get("max_influences", 4))
    over = _over_influenced(mesh, rig, most=most)
    if over:
        warnings.append("%d vertices of %s are pulled by more than %d bones - the exporter "
                        "keeps the %d heaviest, so they deform differently in the engine "
                        "(bake_for_game limits and normalises)" % (over, mesh_name, most, most))

    return {
        "mesh": mesh_name,
        "rig": rig_name,
        "origin": origin,
        "bones": len(rig.data.bones),
        "problems": problems,
        "warnings": warnings,
        "passed": not problems,
    }


def bake_for_game(mesh_name, rig_name, name=None, influences=None):
    """One skinned mesh as the engine will draw it, replacing `mesh_name`.

    Shape keys at their current values and every modifier except Armature
    (a Mask hiding helper geometry, a mirror, a subdivision) are baked into the
    mesh at the rig's rest pose. Then the skin is made what a game skeleton
    reads: vertex groups that are not deform bones are removed (MPFB's joint-
    and helper- groups, a rig's control bones), each vertex keeps its
    `influences` heaviest bones, and the weights are normalised - the exporter
    would otherwise do the last two itself, silently and differently.

    The new object takes `name` (default: the original's name), the original's
    world transform, parent, materials and custom properties, is parented to
    the rig and bound with an Armature modifier. The original is deleted.

    The rig's body profile `bake` block, when it has one, says the rest:
    `max_influences` is the default for `influences` (else 4), `strip_groups`
    patterns are removed even where a deform bone has that name, and
    `shape_keys: false` refuses a mesh whose live keys would be flattened.
    """
    src, rig = _obj(mesh_name), _obj(rig_name)
    if rig is None or rig.type != "ARMATURE":
        return {"error": "no armature named " + repr(rig_name)}
    if src is None or src.type != "MESH":
        return {"error": "no mesh named " + repr(mesh_name)}
    name = name or mesh_name
    profile, bake = _bake_block(rig)
    if influences is None:
        influences = int(bake.get("max_influences", 4))
    strip = list(bake.get("strip_groups") or ())

    keys = _shape_keys_live(src)
    if keys and bake.get("shape_keys") is False:
        return {"error": "%s has %d live shape keys and profile %s ships them as morph targets; "
                         "baking would flatten them" % (mesh_name, len(keys), profile)}
    applied = [m.name for m in src.modifiers if m.type != "ARMATURE" and m.show_viewport]
    prev_pos = rig.data.pose_position
    arm_state = {m.name: m.show_viewport for m in src.modifiers if m.type == "ARMATURE"}
    try:
        rig.data.pose_position = "REST"
        for m in src.modifiers:
            if m.type == "ARMATURE":
                m.show_viewport = False
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(src.evaluated_get(dg), preserve_all_data_layers=True,
                                             depsgraph=dg)
    finally:
        rig.data.pose_position = prev_pos
        for m in src.modifiers:
            if m.name in arm_state:
                m.show_viewport = arm_state[m.name]
        bpy.context.view_layer.update()

    world = src.matrix_world.copy()
    groups = [g.name for g in src.vertex_groups]
    props = {k: src[k] for k in src.keys() if k not in ("_RNA_UI",)}
    collections = list(src.users_collection) or [bpy.context.scene.collection]
    verts_before = len(src.data.vertices)
    if name == mesh_name:
        src.name = mesh_name + "_prebake"
    ob = bpy.data.objects.new(name, me)
    for c in collections:
        c.objects.link(ob)
    me.name = name
    # new_from_object keeps each vertex's group weights but not the object's
    # group names, which index them
    if len(ob.vertex_groups) == 0:
        for g in groups:
            ob.vertex_groups.new(name=g)
    for k, v in props.items():
        try:
            ob[k] = v
        except (TypeError, ValueError):
            pass
    bpy.data.objects.remove(src, do_unlink=True)
    if me.shape_keys is not None:
        ob.shape_key_clear()
    ob.parent = rig
    ob.matrix_world = world
    ob.modifiers.new("Armature", "ARMATURE").object = rig

    deform = {b.name for b in rig.data.bones if b.use_deform}

    def stripped(g):
        return g.name not in deform or any(fnmatch.fnmatchcase(g.name, p) for p in strip)
    removed = [g.name for g in ob.vertex_groups if stripped(g)]
    for g in list(ob.vertex_groups):
        if stripped(g):
            ob.vertex_groups.remove(g)

    # limit and normalise, one group at a time for the removals
    drop = {}
    limited = unweighted = 0
    for v in ob.data.vertices:
        ws = sorted(((g.weight, g.group) for g in v.groups if g.weight > 0.0), reverse=True)
        zero = [g.group for g in v.groups if g.weight <= 0.0]
        keep, cut = ws[:influences], ws[influences:]
        if cut:
            limited += 1
        for _, gi in cut:
            drop.setdefault(gi, []).append(v.index)
        for gi in zero:
            drop.setdefault(gi, []).append(v.index)
        tot = sum(w for w, _ in keep)
        if tot <= 0.0:
            unweighted += 1
            continue
        kept = {gi: w / tot for w, gi in keep}
        for g in v.groups:
            if g.group in kept:
                g.weight = kept[g.group]
    for gi, idx in drop.items():
        ob.vertex_groups[gi].remove(idx)

    return {
        "mesh": ob.name,
        "vertices": {"before": verts_before, "after": len(me.vertices)},
        "shape_keys_baked": keys,
        "modifiers_applied": applied,
        "groups_removed": len(removed),
        "groups_kept": len(ob.vertex_groups),
        "vertices_limited": limited,
        "influences": influences,
        "unweighted_vertices": unweighted,
    }


# ---------------------------------------------------------------------------
# clip measurement
# ---------------------------------------------------------------------------

def clip_report(rig_name, foot_bones, actions=None, loop_clips=None, floor=0.0,
                up="Z", forward="-Y", tolerance=None, size=None,
                still_ratio=0.05, gaits=None, recheck=True, clearance=False):
    """Measure every clip, and say which period each speed belongs to.

    `gaits` names the clips that are locomotion. A declared gait whose stride
    measures under `still_ratio` of the creature is a failure, not a note: the
    legs are not moving, and the likeliest reason is keys the bones ignore. A
    clip not declared is judged by its stride as before.

    `recheck` plays every clip back through `verify.recheck` - floor, skin,
    seam, stance slide, balance, rotation modes - and its failures are the
    clip's failures. It is what catches a layer keyed over a clip after it was
    authored. `clearance` adds `verify.limb_clearance` to it.

    `implied_speed_playback_mps` is the one an engine wants. It is reported
    first and named in full for that reason: the alternative differs by one
    frame in the denominator, which is small enough to look right and large
    enough to slide the feet.

    `loop_clips` names the clips that are cycles. It matters twice. A one-shot
    is not required to close its seam - failing a jump for landing somewhere
    other than where it took off is nonsense. And only a cycle carries a speed:
    a jump travels 0.163 m, comfortably over any stride threshold, but dividing
    that by its length yields a number that means nothing, and a number that
    means nothing is exactly what gets pasted into a game and time-scaled
    against. So locomotion requires both a loop and a real stride. Pass None to
    treat every clip as looping.
    """
    rig = _obj(rig_name)
    if rig is None or rig.type != "ARMATURE":
        return {"error": "no armature named " + repr(rig_name)}

    if actions is None:
        actions = [a.name for a in bpy.data.actions]
    if size is None:
        # The body's size, not the tail's. A rat's largest dimension is mostly
        # tail, which made every one of its strides read as under 5% of the
        # creature - a walk reported as standing still, with no speed at all.
        dims = rig.dimensions
        size = max(dims) if max(dims) > 0 else 1.0
        try:
            from . import bodymap
            bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
            tail = set(bm.get("tail", []))
            # nor its wings: a dragon's span is 3.1 m on a 2.3 m body
            for w in bm.get("wings", []):
                tail.update(bodymap._descendants_names(rig.data.bones[w["upper"]], w["side"]))
            pts = [p for b in rig.data.bones if b.name not in tail
                   for p in (b.head_local, b.tail_local)]
            if tail and pts:
                size = max(max(p[i] for p in pts) - min(p[i] for p in pts)
                           for i in range(3)) or size
        except Exception:
            pass
    if tolerance is None:
        # Same rule as the gait generator: scale the floor tolerance to the
        # creature. A rat's toes rest at +0.00003 and a pendulum swing must dip.
        tolerance = 0.005 * size

    clips, problems, failed = {}, [], {}
    gaits = set(gaits or [])
    for name in sorted(gaits - set(actions)):
        problems.append("%s is declared a gait but not among the clips" % name)
        failed[name] = "declared a gait but not among the clips"
    for name in actions:
        if bpy.data.actions.get(name) is None:
            problems.append("no action named " + repr(name))
            failed[name] = "no such action"
            continue
        loops = True if loop_clips is None else (name in loop_clips)
        # A clip may carry the floor it was authored against: an airborne clip (a hopper's
        # JumpAir) is authored in place with the ground it left below the body, and holding
        # it to the origin's floor fails every hanging foot and refuses the whole export.
        clip = bpy.data.actions.get(name)
        clip_floor = clip.get("rig_anything_floor", floor) if clip else floor
        c = verify.check_clip(rig_name, name, foot_bones, floor=clip_floor, up=up,
                              forward=forward, tolerance=tolerance, loop=loops)
        if "error" in c:
            problems.append(name + ": " + c["error"])
            failed[name] = c["error"]
            continue

        stride = c["stride_m"]
        locomotion = loops and stride >= still_ratio * size
        failures = list(c["failures"])
        if name in gaits:
            if not loops:
                failures.append("declared a gait but not a loop")
            if stride < still_ratio * size:
                failures.append("declared a gait but its feet travel %.4f m, under %.0f%% of the "
                                "%.3f m creature - the legs are not moving"
                                % (stride, still_ratio * 100, size))
        entry = {
            "locomotion": locomotion,
            "gait": name in gaits,
            "loops": loops,
            "frames": c["frames"],
            "fps": c["fps"],
            # What the engine sees: every keyed frame, looped over all of them.
            "engine_duration_s": c["playback_duration_s"],
            # What Blender authored against: the true cycle, one frame shorter.
            "blender_cycle_s": c["duration_s"],
            "loop_seam": c["loop_seam"],
            "lowest_foot": c["lowest_foot"],
        }
        if recheck:
            r = verify.recheck(rig_name, name, forward=forward, up=up, floor=clip_floor,
                               loop=loops, clearance=clearance)
            if "error" in r:
                # a body the map cannot read (a rock with a clip) has nothing
                # to re-check against; say so rather than fail it
                entry["recheck"] = {"skipped": r["error"]}
            else:
                entry["recheck"] = {k: r.get(k) for k in (
                    "lowest_bone", "skin_lowest", "loop_seam", "stance_speed_mps",
                    "contacts", "balance", "clearance", "failures")}
                failures += [f for f in r["failures"]
                             # the seam and rotation modes are already reported above
                             if not f.startswith(("loop seam", "rotation mode"))]
        if clip_floor != floor:
            # This clip declared a floor of its own, so its body is one the engine flies:
            # the ground it left is below it and the clip only shapes what the body does in
            # the air. Its authoring check already drops floor failures for that reason
            # ("in the air: the floor is the engine's business"); the re-check measures
            # against the declared floor and reports what it finds, but a foot or skin hanging
            # under a notional ground does not refuse the export.
            entry["declared_floor_m"] = round(clip_floor, 5)
            entry["floor_notes"] = [f for f in failures if "floor" in f]
            failures = [f for f in failures if "floor" not in f]
        entry["passed"] = not failures
        entry["failures"] = failures
        if locomotion:
            entry["stride_m"] = stride
            entry["implied_speed_playback_mps"] = c["implied_speed_playback_mps"]
            entry["implied_speed_cycle_mps"] = c["implied_speed_mps"]
            entry["speed_source"] = c["speed_source"]
            entry["duty_factor"] = c["duty_factor"]
            entry["use"] = ("implied_speed_playback_mps - the engine loops over "
                            "all %d keyed frames"
                            % (c["frames"][1] - c["frames"][0] + 1))
        elif not loops:
            entry["note"] = ("one-shot, not a cycle - no speed reported "
                             "(it travels %.4f m, but not per stride)" % stride)
        else:
            entry["note"] = ("stride %.4f m is under %.0f%% of the %.3f m creature "
                             "- not locomotion, no speed reported"
                             % (stride, still_ratio * 100, size))
        clips[name] = entry

    bad = sorted(n for n, c in clips.items() if not c["passed"])

    return {
        "rig": rig_name,
        "size_m": round(size, 4),
        "floor_tolerance_m": round(tolerance, 5),
        "clips": clips,
        "problems": problems,
        "failed": failed,
        # measured, but failing their checks
        "failing": {n: clips[n]["failures"] for n in bad},
        "passed": not problems and not bad,
    }


# ---------------------------------------------------------------------------
# reading the written file back
# ---------------------------------------------------------------------------

def inspect_glb(filepath):
    """Read durations and node names out of a written .glb, without importing it.

    This exists because predicting the exported length is exactly the mistake
    that shipped. The exporter can drop keyframes it considers redundant, and a
    clip one frame shorter than expected implies a different speed. A GLB
    carries its JSON in the first chunk, and the spec requires min/max on every
    animation sampler input accessor, so the real duration is readable with no
    dependencies and no round trip through the importer.
    """
    if not os.path.exists(filepath):
        return {"error": "no file at " + filepath}

    with open(filepath, "rb") as fh:
        magic, version, _total = struct.unpack("<III", fh.read(12))
        if magic != _GLB_MAGIC:
            return {"error": "not a GLB (bad magic) - a .gltf is JSON, read it directly"}
        doc = None
        while True:
            head = fh.read(8)
            if len(head) < 8:
                break
            length, ctype = struct.unpack("<II", head)
            data = fh.read(length)
            if ctype == _GLB_JSON_CHUNK:
                doc = json.loads(data.decode("utf-8"))
                break
        if doc is None:
            return {"error": "no JSON chunk in " + filepath}

    accessors = doc.get("accessors", [])

    def _input_max(sampler):
        idx = sampler.get("input")
        acc = accessors[idx] if idx is not None and idx < len(accessors) else None
        if acc and acc.get("max"):
            return float(acc["max"][0])
        return 0.0

    animations = {}
    for anim in doc.get("animations", []):
        samplers = anim.get("samplers", [])
        duration = max((_input_max(s) for s in samplers), default=0.0)
        animations[anim.get("name", "<unnamed>")] = round(duration, 6)

    skins = doc.get("skins", [])
    return {
        "file": filepath,
        "size_bytes": os.path.getsize(filepath),
        "gltf_version": version,
        "generator": doc.get("asset", {}).get("generator"),
        "animations": animations,
        "nodes": [n.get("name") for n in doc.get("nodes", [])],
        "meshes": [m.get("name") for m in doc.get("meshes", [])],
        "skins": len(skins),
        "joints": len(skins[0].get("joints", [])) if skins else 0,
    }


# ---------------------------------------------------------------------------
# the export itself
# ---------------------------------------------------------------------------

def export_glb(filepath, objects, actions=None, rig_name=None,
               apply_modifiers=True):
    """Write a GLB containing exactly the given objects and exactly `actions`.

    "Exactly" is the point. The exporter's ACTIONS mode means *every action in
    the blend file that has a fake user*, not the ones belonging to the thing
    being exported - and every generated rig leaves its clips behind with a fake
    user on. Exporting a humanoid from a file that had also been used to rig a
    rat and a hexapod put `RatWalk`, `Trot` and `Tripod` into the humanoid's
    glb, as clips that animate nothing.

    So the wanted actions are staged onto temporary NLA tracks and exported with
    NLA_TRACKS, which takes the tracks and nothing else. The tracks are removed
    afterwards; the scene ends as it started.

    Options are filtered against the operator's own RNA before being passed, so
    this runs on 4.x and 5.x rather than failing on whichever keyword a given
    build renamed.
    """
    missing = [n for n in objects if _obj(n) is None]
    if missing:
        return {"error": "no such objects: " + ", ".join(missing)}

    filepath = os.path.abspath(filepath)
    parent = os.path.dirname(filepath)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)

    view = bpy.context.view_layer
    prev_selected = [o for o in bpy.data.objects if o.select_get()]
    prev_active = view.objects.active

    wanted = {
        "filepath": filepath,
        "export_format": "GLB",
        "use_selection": True,
        # Selection is per scene, and without this the exporter takes selected objects from
        # every scene: a body exported after a follow-through volume export in another
        # scene carried eleven jello, clay and floor meshes it had never seen.
        "use_active_scene": True,
        "export_yup": True,
        "export_apply": apply_modifiers,
        # An empty list is not "no preference", it is "this thing has no gait" -
        # a chair, a rock, a worm. The skill declines to invent locomotion for
        # those, so the export must not bake a scene animation onto them either.
        "export_animations": True if actions is None else bool(actions),
        # One glTF animation per staged NLA track, named after the track.
        "export_animation_mode": "NLA_TRACKS" if actions else "SCENE",
        # Each clip keeps its own frame range rather than being cropped to the
        # scene's, which is what preserves the duplicated closing frame the loop
        # depends on.
        "export_frame_range": False,
        # Do not let the exporter decide a keyframe is redundant. It can change
        # the clip length, and the clip length is the number all of this is for.
        "export_optimize_animation_size": False,
        "export_cameras": False,
        "export_lights": False,
        # Object custom properties become node extras. follow-through writes its
        # secondary-motion spec (jiggle bones on flesh, cloth pins) there, and a rig
        # exported without extras arrives in Godot with nothing to make it move.
        "export_extras": True,
    }

    # Morph targets only when there is something to morph, and said outright
    # rather than left to the exporter's default: shape keys that were baked into
    # the mesh must not come back as blend shapes, and ones that were kept (a
    # face's expressions) must not be dropped.
    wanted["export_morph"] = any(
        _obj(n).type == "MESH" and _obj(n).data.shape_keys is not None
        and len(_obj(n).data.shape_keys.key_blocks) > 1 for n in objects)

    props = {p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}
    kwargs = {k: v for k, v in wanted.items() if k in props}
    dropped = sorted(set(wanted) - set(kwargs))

    rig = _obj(rig_name) if rig_name else None
    staged, ad, prev_action, prev_slot = [], None, None, None
    staged_names, skipped = [], []

    try:
        if actions:
            if rig is None or rig.type != "ARMATURE":
                return {"error": "staging actions needs rig_name to be an armature"}
            ad = rig.animation_data or rig.animation_data_create()
            prev_action, prev_slot = ad.action, getattr(ad, "action_slot", None)
            ad.action = None
            for name in actions:
                a = bpy.data.actions.get(name)
                if a is None:
                    skipped.append(name + ": no such action")
                    continue
                track = ad.nla_tracks.new()
                track.name = name
                strip = track.strips.new(name, int(a.frame_range[0]), a)
                strip.name = name
                # A strip carries its own slot binding on 4.4+; without it the
                # track exports as an empty clip of the right length.
                slots = list(getattr(a, "slots", []) or [])
                if hasattr(strip, "action_slot") and slots:
                    pick = next((s for s in slots
                                 if s.identifier == "OB" + rig.name), None)
                    if pick is None and len(slots) == 1:
                        pick = slots[0]
                    if pick is not None:
                        try:
                            strip.action_slot = pick
                        except (AttributeError, TypeError):
                            pass
                staged.append(track)
                staged_names.append(name)

        bpy.ops.object.select_all(action="DESELECT")
        for n in objects:
            o = _obj(n)
            o.select_set(True)
            view.objects.active = o
        bpy.ops.export_scene.gltf(**kwargs)
    finally:
        if ad is not None:
            for track in staged:
                try:
                    ad.nla_tracks.remove(track)
                except RuntimeError:
                    pass
            ad.action = prev_action
            if prev_slot is not None:
                try:
                    ad.action_slot = prev_slot
                except (AttributeError, TypeError):
                    pass
        bpy.ops.object.select_all(action="DESELECT")
        for o in prev_selected:
            try:
                o.select_set(True)
            except RuntimeError:
                pass
        view.objects.active = prev_active

    return {
        "file": filepath,
        "exported": list(objects),
        "morph_targets": wanted["export_morph"],
        "staged_clips": staged_names or None,
        "skipped": skipped,
        "options_dropped_by_this_blender": dropped,
        "written": os.path.exists(filepath),
    }


# ---------------------------------------------------------------------------
# engine collision
# ---------------------------------------------------------------------------

def collider(mesh_name, rig_name, forward="-Y", up="Z", floor=0.0, share=0.98):
    """The `collider: {radius, height}` block `MovesController` reads, from the
    skinned mesh at rest.

    radius  how far the TRUNK's skin - the torso, anything hung off it that is
            not a limb (jiggle bones included), and the upper legs - reaches
            out horizontally from the vertical line through the rig's origin,
            its `share` percentile so one stray vertex does not size it. Arms
            are left out: a capsule wide enough for a swinging hand wedges in
            doorways. Hips and belly are what bump into things.
    height  the top of the whole mesh above the floor.
    Metres, world space."""
    from . import bodymap, verify
    ob, rig = bpy.data.objects.get(mesh_name), bpy.data.objects.get(rig_name)
    if ob is None or rig is None:
        return {"error": "missing mesh or rig"}
    bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return {"error": bm["error"]}
    _, trunk = verify.clearance_bones(rig, bm, [])
    upw = bodymap.axis_vector(up)
    origin = rig.matrix_world.translation
    names = {g.index: g.name for g in ob.vertex_groups}
    dists, top = [], -float("inf")
    for v in ob.data.vertices:
        p = ob.matrix_world @ v.co
        top = max(top, p.dot(upw) - floor)
        best = max(v.groups, key=lambda g: g.weight, default=None)
        if best is None or names.get(best.group) not in trunk:
            continue
        d = p - origin
        dists.append((d - upw * d.dot(upw)).length)
    if not dists:
        return {"error": "no skin weighted to the trunk of " + rig_name}
    dists.sort()
    return {"radius": round(dists[min(len(dists) - 1, int(share * len(dists)))], 4),
            "height": round(top, 4)}


# ---------------------------------------------------------------------------
# GDScript output
# ---------------------------------------------------------------------------

def godot_constants(report, suffix="_CLIP_IMPLIED_SPEED"):
    """Emit the locomotion speeds as constants, ready to paste.

    Transcribing these by hand is how the wrong period got into a game in the
    first place, so the generated line carries its derivation in the comment -
    the same shape the hand-written ones use, and now checkable against the clip
    rather than against memory.
    """
    lines = []
    for name, c in sorted(report.get("clips", {}).items()):
        if not c.get("locomotion"):
            continue
        if c.get("speed_source", "").startswith("stance"):
            why = "stance feet sweep back at this, duty %s, over %s s" % (
                c.get("duty_factor"), format(c["engine_duration_s"], ".4g"))
        else:
            why = "%s m per step, 2 steps / %s s" % (
                format(c["stride_m"], ".3f"), format(c["engine_duration_s"], ".4g"))
        lines.append("const %s%s := %s   # %s"
                     % (name.upper(), suffix,
                        format(c["implied_speed_playback_mps"], ".4g"), why))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# front door
# ---------------------------------------------------------------------------

def export(mesh_name, rig_name, filepath, foot_bones, actions=None,
           loop_clips=None, floor=0.0, up="Z", forward="-Y", force=False,
           skip_bad_clips=False, sidecar=True, gaits=None, recheck=True,
           clearance=False, review=True, review_options=None):
    """Preflight, export, then read the file back and check it against the plan.

    Returns a manifest the engine side can be driven from. `verified` is the
    part that matters: it compares the duration predicted from Blender's frame
    ranges against the duration actually written into the glTF. If those
    disagree the speeds are wrong and the feet will slide - which is precisely
    the failure this phase exists to make unshippable.

    `gaits` names the clips that are locomotion (see `clip_report`). Every clip
    is re-checked on playback (`recheck=True`), and a clip failing any check
    blocks the export: `skip_bad_clips=True` drops it and says so, `force=True`
    ships it anyway with its failures in the manifest.

    `review` (on by default) then writes the review sheet beside the glb, in
    `<glb folder>/review/<glb name>/`: every exported clip as 8-frame strips
    from the front, right and three-quarter views at one shared scale, and a
    `contact.png` (see `review.py`). `review_options` go to `review.sheet`
    (`frame_height_m`, `views`, `frames`, `cell_px`, `title`). The manifest's
    `review` says what was written, or its `error`: a sheet that could not be
    rendered does not undo a verified export, but it is never silent.
    """
    pre = preflight(mesh_name, rig_name, actions=actions)
    if "error" in pre:
        return pre
    if not pre["passed"] and not force:
        return {"stage": "preflight", "preflight": pre, "exported": False,
                "note": "refusing to export - fix the problems, or pass force=True"}

    clips = clip_report(rig_name, foot_bones, actions=actions,
                        loop_clips=loop_clips, floor=floor, up=up,
                        forward=forward, gaits=gaits, recheck=recheck,
                        clearance=clearance)
    if "error" in clips:
        return {"stage": "clips", "preflight": pre, "clips": clips, "exported": False}
    if clips["failing"] and not (skip_bad_clips or force):
        return {"stage": "clips", "preflight": pre, "clips": clips, "exported": False,
                "note": "refusing to export - " + "; ".join(
                    "%s: %s" % (n, "; ".join(f)) for n, f in sorted(clips["failing"].items()))
                + " (skip_bad_clips=True drops these clips, force=True ships them)"}
    dropped = {}
    if clips["failing"] and skip_bad_clips and not force:
        for n in clips["failing"]:
            dropped[n] = clips["clips"].pop(n)["failures"]
    if dropped and not clips["clips"]:
        return {"stage": "clips", "preflight": pre, "clips": clips, "exported": False,
                "dropped": dropped, "note": "refusing to export - no clip passed its checks"}
    if clips["failed"] and not skip_bad_clips:
        # A clip that cannot be measured has no knowable speed, and a clip that
        # animates nothing is a clip the engine will happily play. `force` does
        # not cover this: it waives geometry the caller can see and judge, while
        # this is the deliverable itself going missing. Dropping these quietly
        # would hand back a file short of the clips that were asked for, with
        # nothing to say so - pass skip_bad_clips to mean it on purpose.
        return {"stage": "clips", "preflight": pre, "clips": clips,
                "exported": False,
                "note": "refusing to export - " + "; ".join(clips["problems"])}

    written = export_glb(filepath, [mesh_name, rig_name],
                         actions=sorted(clips["clips"]), rig_name=rig_name)
    if "error" in written:
        return {"stage": "export", "preflight": pre, "clips": clips,
                "export": written, "exported": False}

    actual = inspect_glb(written["file"])

    # The check the whole module is built around.
    mismatches = []
    if "animations" in actual:
        for name, c in clips["clips"].items():
            got = actual["animations"].get(name)
            if got is None:
                mismatches.append("%s: not present in the exported file" % name)
                continue
            expected = c["engine_duration_s"]
            # Half a frame-interval of slack. Anything larger is a different clip.
            if abs(got - expected) > 0.5 / (c["fps"] or 24):
                mismatches.append(
                    "%s: exported %.4f s but the frame range implies %.4f s - "
                    "the speed derived from it is wrong" % (name, got, expected))
        # Clips nobody asked for. They arrive from other rigs in the same file
        # and animate nothing, but they show up in the engine's clip list and
        # get played.
        for extra in sorted(set(actual["animations"]) - set(clips["clips"])):
            mismatches.append("%s: in the file but not requested - a stray clip "
                              "from another rig" % extra)

    manifest = {
        "stage": "done",
        "preflight": pre,
        "clips": clips,
        "export": written,
        "file": actual,
        "verified": {
            "durations_match": not mismatches,
            "mismatches": mismatches,
        },
        "godot": godot_constants(clips),
        "exported": True,
        # dropped by skip_bad_clips, and shipped failing under force
        "dropped_clips": dropped,
        "forced_clips": clips["failing"] if force else {},
    }

    if sidecar:
        side = os.path.splitext(written["file"])[0] + ".rig.json"
        with open(side, "w", encoding="utf-8") as fh:
            json.dump({k: manifest[k] for k in ("clips", "file", "verified", "godot",
                                                "dropped_clips", "forced_clips")},
                      fh, indent=2)
        manifest["sidecar"] = side

    if review:
        manifest["review"] = review_sheet(mesh_name, rig_name, written["file"], clips["clips"],
                                          forward=forward, floor=floor, options=review_options)
    return manifest


def review_sheet(mesh_name, rig_name, glb_path, clips, forward="-Y", floor=0.0, options=None):
    """`review.for_glb` for an export's clips ({name: clip check}, whose `loops` it reads), reduced to
    `review.summary`; an exception becomes {error}."""
    from . import review as rv
    try:
        r = rv.for_glb([mesh_name], rig_name, glb_path, sorted(clips),
                       loops=[n for n, c in clips.items() if c.get("loops")], forward=forward,
                       floor=floor, **dict(options or {}))
    except Exception as exc:                        # reported, not raised: the glb is already verified
        import traceback
        traceback.print_exc()
        return {"error": "review sheet failed: %s: %s" % (type(exc).__name__, exc)}
    return rv.summary(r)


def _res_path(glb_path):
    """`res://` path of `glb_path` inside the Godot project holding it (the nearest folder above
    with a project.godot), else `res://<file name>`."""
    full = os.path.abspath(glb_path)
    d = os.path.dirname(full)
    while True:
        if os.path.isfile(os.path.join(d, "project.godot")):
            return "res://" + os.path.relpath(full, d).replace(os.sep, "/")
        parent = os.path.dirname(d)
        if parent == d:
            return "res://" + os.path.basename(full)
        d = parent


def export_character(mesh_name, rig_name, glb_path, name=None, reports=None, res_path=None,
                     roles=None, loops=None, gaits=None, foot_bones=None, forward="-Y", up="Z",
                     floor=0.0, force=False, skip_bad_clips=False, sidecar=True, creature=None,
                     extra=None, review=True, review_options=None):
    """Export a biped or quadruped through `export` and write `<glb base>.moves.json` beside it:
    the manifest `MovesController` reads, as `hop.export_creature` and
    `radial_moves.export_creature` write for their bodies.

    reports     {role: report} from `actions.move_set` (or `locomotion.cycle`); None loads what
                the set functions stored on the rig's actions (`stored.resolve`).
    roles       the roles to export, in order (default: every report). One must be Idle:
                MovesController starts on it.
    loops       roles whose clip loops (default: those whose report measured a `loop_seam`).
    gaits       roles that are locomotion (default: those with a `natural_speed_mps`, i.e. the
                `cycle` reports). They get `gaits` and `contacts` entries and the export's gait
                checks.
    foot_bones  default: the end bone of every leg in `bodymap.build(rig)["roles"]["limbs"]`.
    name        the display name; `creature` the id, default the glb's base name.
    res_path    the glb's `res://` path (`scene`). Default: its path inside the Godot project that
                holds it (the folder with project.godot), else `res://<file name>`.
    force, skip_bad_clips, sidecar, review, review_options   as `export`. A dropped clip leaves the
                manifest too. The review sheet's title is the display name; a sheet that failed is
                listed in `problems`.
    extra       fields merged into the manifest last - a project's own (`style`, `note`, ...),
                replacing any written here.

    Writes creature, name, rig, scene, clips, loops, implied_speed_mps (by role), height_m (stand
    is the mesh top at rest; crouch and crouch_walk when those roles were exported), gaits,
    contacts, verified, clip_checks, forced_clips, known_failures (authoring failures by role),
    collider (`collider`), and dropped_clips when any were. Returns {glb, moves, manifest,
    verified, clips, bones, problems, export}, or {error, ...} with nothing written after the
    refusal."""
    from . import bodymap, locomotion, stored
    reports = stored.resolve(reports, rig_name, roles)
    roles = list(roles) if roles is not None else list(reports)
    missing = [r for r in roles if not isinstance(reports.get(r), dict)]
    errored = ["%s: %s" % (r, reports[r]["error"]) for r in roles
               if r not in missing and "error" in reports[r]]
    if missing or errored:
        return {"error": "not exporting roles that were not authored: "
                + "; ".join(missing + errored)}
    if "Idle" not in roles:
        return {"error": "no Idle role - MovesController starts every character on its Idle clip"}
    if loops is None:
        loops = [r for r in roles if reports[r].get("loop_seam") is not None]
    if gaits is None:
        gaits = [r for r in roles if "natural_speed_mps" in reports[r]]
    if foot_bones is None:
        bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
        if "error" in bm:
            return {"error": bm["error"]}
        foot_bones = [l["end"] for l in bm["roles"]["limbs"].values() if l["role"] == "leg" and l["end"]]
        if not foot_bones:
            return {"error": "no legs on %s to take foot bones from - pass foot_bones" % rig_name}

    clip = {r: reports[r]["action"] for r in roles}
    e = export(mesh_name, rig_name, glb_path, foot_bones=foot_bones, actions=list(clip.values()),
               loop_clips=[clip[r] for r in roles if r in loops], floor=floor, up=up, forward=forward,
               force=force, skip_bad_clips=skip_bad_clips, sidecar=sidecar,
               gaits=[clip[r] for r in roles if r in gaits], review=review,
               review_options=dict({"title": name or creature or os.path.basename(os.path.splitext(glb_path)[0])},
                                   **(review_options or {})))
    if not e.get("exported"):
        return {"error": "export refused at %s: %s" % (e.get("stage"), e.get("note") or e.get("error")),
                "export": e}
    checks = e["clips"]["clips"]
    kept = [r for r in roles if clip[r] in checks]
    if "Idle" not in kept:
        return {"error": "the Idle clip was dropped from the export: %s"
                % "; ".join(e["dropped_clips"].get(clip["Idle"], [])), "export": e}
    role_of = {clip[r]: r for r in kept}
    loco = locomotion.engine_manifest(rig_name, {r: reports[r] for r in kept if r in gaits},
                                      forward=forward, up=up, floor=floor, mesh_name=mesh_name)
    if "collider" not in loco:
        return {"error": "no collider: %s" % (loco.get("error") or "; ".join(loco["problems"])),
                "export": e, "engine": loco}

    heights = {"stand": loco["collider"]["height"]}
    for role, key, field in (("Crouch", "crouch", "crouched_height_m"),
                             ("CrouchWalk", "crouch_walk", "end_height_m")):
        if role in kept and reports[role].get(field) is not None:
            heights[key] = reports[role][field]
    base = os.path.splitext(glb_path)[0]
    creature = creature or os.path.basename(base)
    moves = {
        "creature": creature, "name": name or creature, "rig": rig_name,
        "scene": res_path or _res_path(glb_path),
        "clips": {r: clip[r] for r in kept},
        "loops": [clip[r] for r in kept if r in loops],
        "implied_speed_mps": {role_of[k]: c["implied_speed_playback_mps"] for k, c in checks.items()
                              if c.get("implied_speed_playback_mps")},
        "height_m": heights,
        "gaits": loco.get("gaits", {}),
        "contacts": loco.get("contacts", {}),
        "verified": e["verified"],
        "clip_checks": {k: {"passed": c.get("passed"), "lowest_foot": c.get("lowest_foot"),
                            "loop_seam": c.get("loop_seam"), "failures": c.get("failures", [])}
                        for k, c in checks.items()},
        # how each arm was carried, per clip that has arms (`verify.arm_pose`, keyed like
        # clip_checks). Written because the motion critic's keep-or-revert rule compares this
        # round's ranges against the previous version's, and the build report dies with the run.
        "arm_pose": {clip[r]: reports[r]["arm_pose"] for r in kept if reports[r].get("arm_pose")},
        # which gait each clip's arms were judged as - a run keeps both arms in front and is
        # exempt from the swing-through-hanging a walk must show. Recorded because the flag was
        # silently False for every clip until rig-anything 0.27.0 and nothing showed it.
        "arm_gait": {clip[r]: ("run" if reports[r]["arm_running"] else "walk")
                     for r in kept if "arm_running" in reports[r]},
        # clips that failed their playback checks and were shipped only because force was passed
        "forced_clips": e.get("forced_clips", {}),
        # what each role's authoring reported failing
        "known_failures": {r: reports[r]["failures"] for r in kept if reports[r].get("failures")},
        # the capsule MovesController builds: trunk and hips, arms left out
        "collider": loco["collider"],
    }
    # a turn on the spot ends turned: the yaw and where the rig's origin went, which the engine
    # applies to the character when the clip ends (`actions.turn`)
    turns = {r: reports[r]["turn"] for r in kept if reports[r].get("turn")}
    if turns:
        moves["turns"] = turns
    if e.get("dropped_clips"):
        moves["dropped_clips"] = e["dropped_clips"]
    moves.update(extra or {})
    path = base + ".moves.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(moves, fh, indent=2)
    return {"glb": glb_path, "moves": path, "manifest": moves, "verified": e["verified"],
            "clips": [clip[r] for r in kept], "bones": e["preflight"]["bones"],
            "problems": loco["problems"] + (["review: " + e["review"]["error"]]
                                            if "error" in (e.get("review") or {}) else []),
            "review": e.get("review"), "export": e}


def summarize(manifest):
    """One screen of the things worth reading."""
    if "error" in manifest:
        return "ERROR: " + manifest["error"]
    out = []
    pre = manifest.get("preflight", {})
    out.append("preflight: " + ("ok" if pre.get("passed") else "FAILED"))
    for p in pre.get("problems", []):
        out.append("  ! " + p)
    for w in pre.get("warnings", []):
        out.append("  ~ " + w)

    if not manifest.get("exported"):
        out.append("not exported (" + manifest.get("stage", "?") + ")")
        return "\n".join(out)

    f = manifest.get("file", {})
    out.append("wrote %s (%.1f KB, %d joints)"
               % (os.path.basename(f.get("file", "?")),
                  f.get("size_bytes", 0) / 1024.0, f.get("joints", 0)))

    out.append("")
    out.append("%-10s %5s %9s %9s %10s  %s"
               % ("clip", "loop", "engine_s", "in_file", "speed", ""))
    for name, c in sorted(manifest["clips"]["clips"].items()):
        infile = f.get("animations", {}).get(name)
        speed = (format(c["implied_speed_playback_mps"], ".4g")
                 if c.get("locomotion") else "-")
        out.append("%-10s %5s %9.4f %9s %10s  %s"
                   % (name, "yes" if c.get("loops") else "no",
                      c["engine_duration_s"],
                      format(infile, ".4f") if infile is not None else "MISSING",
                      speed,
                      "" if c["passed"] else "FAILED: " + "; ".join(c["failures"])))

    for name, fails in sorted((manifest.get("dropped_clips") or {}).items()):
        out.append("dropped %s: %s" % (name, "; ".join(fails)))
    for name in sorted(manifest.get("forced_clips") or {}):
        out.append("FORCED %s out despite its failures" % name)

    v = manifest.get("verified", {})
    out.append("")
    out.append("durations match: " + ("yes" if v.get("durations_match") else "NO"))
    for m in v.get("mismatches", []):
        out.append("  ! " + m)
    if manifest.get("godot"):
        out.append("")
        out.append(manifest["godot"])
    return "\n".join(out)
