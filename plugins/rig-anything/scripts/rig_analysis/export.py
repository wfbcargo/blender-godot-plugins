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

def preflight(mesh_name, rig_name, tolerance=0.01):
    """Everything that makes an export silently wrong, checked before writing.

    None of these raise in Blender and none of them raise in the engine. They
    just produce an asset that is subtly, permanently incorrect - which is why
    they are worth a pass of their own rather than a comment in the procedure.
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

    return {
        "mesh": mesh_name,
        "rig": rig_name,
        "origin": origin,
        "bones": len(rig.data.bones),
        "problems": problems,
        "warnings": warnings,
        "passed": not problems,
    }


# ---------------------------------------------------------------------------
# clip measurement
# ---------------------------------------------------------------------------

def clip_report(rig_name, foot_bones, actions=None, loop_clips=None, floor=0.0,
                up="Z", forward="-Y", tolerance=None, size=None,
                still_ratio=0.05):
    """Measure every clip, and say which period each speed belongs to.

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
    for name in actions:
        if bpy.data.actions.get(name) is None:
            problems.append("no action named " + repr(name))
            failed[name] = "no such action"
            continue
        loops = True if loop_clips is None else (name in loop_clips)
        c = verify.check_clip(rig_name, name, foot_bones, floor=floor, up=up,
                              forward=forward, tolerance=tolerance, loop=loops)
        if "error" in c:
            problems.append(name + ": " + c["error"])
            failed[name] = c["error"]
            continue

        stride = c["stride_m"]
        locomotion = loops and stride >= still_ratio * size
        entry = {
            "locomotion": locomotion,
            "loops": loops,
            "frames": c["frames"],
            "fps": c["fps"],
            # What the engine sees: every keyed frame, looped over all of them.
            "engine_duration_s": c["playback_duration_s"],
            # What Blender authored against: the true cycle, one frame shorter.
            "blender_cycle_s": c["duration_s"],
            "loop_seam": c["loop_seam"],
            "lowest_foot": c["lowest_foot"],
            "passed": c["passed"],
            "failures": c["failures"],
        }
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

    return {
        "rig": rig_name,
        "size_m": round(size, 4),
        "floor_tolerance_m": round(tolerance, 5),
        "clips": clips,
        "problems": problems,
        "failed": failed,
        "passed": not problems and all(c["passed"] for c in clips.values()),
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
        "staged_clips": staged_names or None,
        "skipped": skipped,
        "options_dropped_by_this_blender": dropped,
        "written": os.path.exists(filepath),
    }


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
           skip_bad_clips=False, sidecar=True):
    """Preflight, export, then read the file back and check it against the plan.

    Returns a manifest the engine side can be driven from. `verified` is the
    part that matters: it compares the duration predicted from Blender's frame
    ranges against the duration actually written into the glTF. If those
    disagree the speeds are wrong and the feet will slide - which is precisely
    the failure this phase exists to make unshippable.
    """
    pre = preflight(mesh_name, rig_name)
    if "error" in pre:
        return pre
    if not pre["passed"] and not force:
        return {"stage": "preflight", "preflight": pre, "exported": False,
                "note": "refusing to export - fix the problems, or pass force=True"}

    clips = clip_report(rig_name, foot_bones, actions=actions,
                        loop_clips=loop_clips, floor=floor, up=up,
                        forward=forward)
    if "error" in clips:
        return {"stage": "clips", "preflight": pre, "clips": clips, "exported": False}
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
    }

    if sidecar:
        side = os.path.splitext(written["file"])[0] + ".rig.json"
        with open(side, "w", encoding="utf-8") as fh:
            json.dump({k: manifest[k] for k in ("clips", "file", "verified", "godot")},
                      fh, indent=2)
        manifest["sidecar"] = side

    return manifest


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

    v = manifest.get("verified", {})
    out.append("")
    out.append("durations match: " + ("yes" if v.get("durations_match") else "NO"))
    for m in v.get("mismatches", []):
        out.append("  ! " + m)
    if manifest.get("godot"):
        out.append("")
        out.append(manifest["godot"])
    return "\n".join(out)
