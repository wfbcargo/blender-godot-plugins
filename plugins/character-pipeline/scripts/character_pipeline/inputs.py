"""What a stage reads besides the spec, for its input hash: the data files and code its result depends on.

A stage's hash always covered the spec sections it reads, the hashes of the stages it needs and the plugin
versions. That missed everything a plugin reads that a version bump does not follow (06 rank 3):

- a garment preset edited in `wardrobe/presets/garments.json` left `garments` "unchanged", and the old cut
  shipped until someone ran `force=1` (belle-top, about 10 min);
- the ear cut in humanform's `hair.py` left Belle's old cap "unchanged";
- flesh read follow-through's type registry (limit shares, zones, materials), and the user registry
  (`~/.claude/follow-through/types.json`) has no version at all; and a fix to how `flesh.py` weights the
  jiggle bones (0.6.1's `limit_influences`) left every saved study figure's flesh "unchanged".

So each stage names what it reads here, as `{label: digest}`, and the runner puts that into its hash and
into the stage's record in the .blend (so a rerun can say which input moved - `changed()`):

    stage     reads (label: what)
    bake      code:humanform.skin, code:humanform.look       the skin material, marks and bake
              code:lookdev_blender.bake                       the map bake (and .detail for a muscle normal map)
    hair      preset:<name>                                   humanform's resolved hair preset (hair_presets.json)
              code:humanform.hair, code:humanform.brows       the hair geometry (cap, ear cut, parts, cards)
              data:humanform.face_regions                     brow and lash placement (only with a face switch on)
              data:humanform.face_features                    beard placement: mouth, nose, lips (only with a beard)
              code:lookdev_blender.hair, data:lookdev.hair    the hair material and its preset (materials.json)
              code:character_pipeline.hair                    instead of all that for a deprecated shell_bun
    flesh     data:follow_through.registry                    the merged type registry: built-in and user
              code:follow_through.flesh                       finding the masses and weighting the jiggle bones
    garments  preset:<name>                                   each worn wardrobe preset's contents (garments.json)
    review    code:rig_analysis.closeups                      the close-up look set: views, aim, lights, checks
                                                              (only with `[review] close` on)

Data is hashed as parsed JSON (so a CRLF checkout and an LF one agree, and key order does not matter); code
as its source with line endings normalised. Presets are hashed one by one, so editing a preset the spec
does not wear, or a hair preset it does not use, reruns nothing. The version of each plugin a stage builds
with was in the hash already (`plugins.stage_versions`).

Stages not listed read only the spec and the stages before them (body's library and fit are humanform's
version; moves, strand and export read rig-anything's and follow-through's code, covered by their versions, as
is the review sheet's). A stage that starts reading a new file must add it here, and `tests/fixtures/pipeline_hashes.py`
must flip it.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os

from . import plugins


def _sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:16]


def data(value) -> str:
    """A digest of plain data: canonical JSON, so formatting, key order and line endings do not count."""
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))


def code(module: str) -> str:
    """A digest of a module's source as it is imported now (line endings normalised)."""
    mod = importlib.import_module(module)
    path = getattr(mod, "__file__", None)
    if not path or not os.path.isfile(path):
        return "absent"
    with open(path, "rb") as fh:
        return _sha(fh.read().replace(b"\r\n", b"\n"))


def json_file(path: str) -> str:
    if not os.path.isfile(path):
        return "absent"
    with open(path, encoding="utf-8") as fh:
        return data(json.load(fh))


def _lookdev():
    return plugins.available("lookdev_blender")


def _bake(ch):
    out = {"code:humanform.skin": code("humanform.skin"), "code:humanform.look": code("humanform.look")}
    if _lookdev():
        out["code:lookdev_blender.bake"] = code("lookdev_blender.bake")
        if ch.muscle is not None and ch.muscle.output == "normal":
            out["code:lookdev_blender.detail"] = code("lookdev_blender.detail")
    return out


def _hair(ch):
    if ch.hair.kind == "shell_bun":
        return {"code:character_pipeline.hair": code("character_pipeline.hair")}
    from humanform import hair as hf_hair
    import humanform
    out = {f"preset:{ch.hair.preset}": data(hf_hair.params(ch.hair.preset)),
           "code:humanform.hair": code("humanform.hair"), "code:humanform.brows": code("humanform.brows")}
    if ch.hair.face():
        out["data:humanform.face_regions"] = json_file(os.path.join(humanform.DATA, "face_regions.json"))
    if ch.hair.beard:                           # the beard is placed from the mouth, nose and chin
        out["data:humanform.face_features"] = json_file(os.path.join(humanform.DATA, "face_features.json"))
    if _lookdev():
        from lookdev_blender import hair as ld_hair
        out["code:lookdev_blender.hair"] = code("lookdev_blender.hair")
        out["data:lookdev.hair"] = data(ld_hair.presets().get("hair"))
    return out


def _flesh(ch):
    from follow_through import registry
    return {"data:follow_through.registry": data(registry.load()), "code:follow_through.flesh": code("follow_through.flesh")}


def _garments(ch):
    from wardrobe import presets
    return {f"preset:{g.preset}": data(presets.get(g.preset)) for g in ch.outfit}


def _review(ch):
    if not ch.review.close:
        return {}
    return {"code:rig_analysis.closeups": code("rig_analysis.closeups")}


READS = {"bake": _bake, "hair": _hair, "flesh": _flesh, "garments": _garments, "review": _review}


def stage_inputs(ch, stage, drop=()):
    """{label: digest} of what `stage` reads besides the spec, as the plugins on sys.path have it now.
    `drop` leaves labels out - only for the hash test's control, never for a build."""
    fn = READS.get(stage)
    out = fn(ch) if fn is not None else {}
    for label in drop:
        out.pop(label, None)
    return out


def changed(before, now):
    """The labels whose digest differs between a stored record's inputs and now (added, removed or edited)."""
    before = before or {}
    return sorted(k for k in set(before) | set(now) if before.get(k) != now.get(k))


# ------------------------------------------------------------------ what a stage leaves for the next

# A stage's input hash covers the hashes of the stages it needs, so any rerun upstream reran it too: a `[flesh]`
# limit_share edit reran moves (8 s of the 18 s) though moves never reads a swing limit. Where a stage reads an
# earlier stage only through what that stage left in the file, the earlier stage's *output* is digested when it
# runs (`outputs`), and the later stage's record also keeps a "view" hash in which that digest stands for the
# earlier stage's input hash. A stage whose input hash moved but whose view did not is skipped: what it reads is
# what it read when it last ran (runner._build).
#
#     stage    reads of an earlier stage's output          (READS_OUTPUT)
#     moves    flesh: the rig's bones and pose setup, every mesh bound to the rig - geometry, vertex groups and
#              weights, modifiers, and what rig-anything tells skin from cloth by (a follow-through route, a
#              wardrobe mark)
#
# Only moves, and only of flesh: everything else still follows the input hashes. What the flesh stage writes
# that moves does not read is the jiggle block of the body's `follow_through` spec (each mass's swing limit,
# frequency and damping, read by export into the glb and the manifest - export still reruns). When in doubt a
# part is in the digest: a wrong skip ships moves authored on a different body, a needless rerun costs 8 s.
READS_OUTPUT = {"moves": ("flesh",)}

OUTPUT_LABELS = ("rig:object", "rig:bones", "rig:pose", "meshes:bound", "mesh:geometry", "mesh:groups",
                 "mesh:weights", "mesh:modifiers", "mesh:marks", "mesh:shape_keys", "mesh:materials")


def _r(values, nd=6):
    return [round(float(x), nd) for x in values]


def _idprops(holder):
    """A datablock's or bone's custom properties as plain data (the pipeline's own records are Texts, not these)."""
    out = {}
    for k in holder.keys():
        v = holder[k]
        out[k] = v.to_dict() if hasattr(v, "to_dict") else (v.to_list() if hasattr(v, "to_list") else v)
    return out


def _mesh_parts(ob):
    import numpy as np
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    loops = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", loops)
    starts = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("loop_start", starts)
    names = [g.name for g in ob.vertex_groups]
    weights = []
    for v in me.vertices:
        weights.append(sorted((names[x.group], round(float(x.weight), 6)) for x in v.groups if x.weight > 0.0))
    ft = ob.get("follow_through")
    marks = {"follow_through.route": (ft.get("route") if ft is not None else None),
             "wardrobe_cut": ob.get("wardrobe_cut") is not None, "wardrobe": ob.get("wardrobe") is not None,
             "ft_type": ob.get("ft_type")}
    keys = [k.name for k in me.shape_keys.key_blocks] if me.shape_keys else []
    return {
        "mesh:geometry": _sha(np.round(co, 6).tobytes() + loops.tobytes() + starts.tobytes()
                              + json.dumps(_r(sum(map(list, ob.matrix_world), []))).encode()),
        "mesh:groups": data(names),
        "mesh:weights": data(weights),
        "mesh:modifiers": data([[m.type, getattr(getattr(m, "object", None), "name", None),
                                 getattr(m, "vertex_group", None), m.show_viewport, m.show_render]
                                for m in ob.modifiers]),
        "mesh:marks": data(marks),
        "mesh:shape_keys": data(keys),
        "mesh:materials": data([m.name if m else None for m in me.materials]),
    }


def _moves_view(ch):
    """What the moves stage reads of the file, as {label: digest}: the rig and every mesh bound to it."""
    import bpy
    rig = bpy.data.objects.get(ch.rig)
    if rig is None or rig.type != "ARMATURE":
        return {"rig:object": "absent"}
    out = {"rig:object": data({"matrix": _r(sum(map(list, rig.matrix_world), [])), "props": _idprops(rig),
                               "pose_position": rig.data.pose_position})}
    out["rig:bones"] = data([[b.name, b.parent.name if b.parent else None, _r(sum(map(list, b.matrix_local), [])),
                              _r(b.head_local), _r(b.tail_local), b.use_deform, b.use_connect, b.inherit_scale,
                              b.use_inherit_rotation, b.use_local_location, b.bbone_segments, _idprops(b)]
                             for b in rig.data.bones])
    # a bone's rotation mode only where flesh made the bone: moves itself puts every bone it keys into the mode its
    # keys use (rig-anything `verify.adopt_rotation_modes`), so after moves has run once the body's bones are no
    # longer in the mode moves found them in (MPFB's Euler), and a rerun of moves would see a different rig than a
    # fresh build's did - the flesh stage never sets the mode of a bone it did not add
    out["rig:pose"] = data([[pb.name, pb.rotation_mode if pb.bone.get("ft_role") else None,
                             list(pb.lock_location), list(pb.lock_rotation),
                             [[c.type, getattr(getattr(c, "target", None), "name", None), getattr(c, "subtarget", None),
                               c.mute, round(float(c.influence), 6)] for c in pb.constraints], _idprops(pb)]
                            for pb in rig.pose.bones])
    bound = sorted(o.name for o in bpy.data.objects
                   if o.type == "MESH" and any(m.type == "ARMATURE" and m.object == rig for m in o.modifiers))
    out["meshes:bound"] = data(bound)
    per = {name: _mesh_parts(bpy.data.objects[name]) for name in bound}
    for label in OUTPUT_LABELS:
        if label.startswith("mesh:"):
            out[label] = data({name: parts[label] for name, parts in per.items()})
    return out


OUTPUTS = {"flesh": _moves_view}


def outputs(ch, stage, drop=()):
    """{label: digest} of what the stages that read `stage`'s output (`READS_OUTPUT`) read of the file now, or
    None for a stage no later stage reads that way. Taken right after `stage` runs. `drop` leaves labels out -
    only for the hash test's control, never for a build."""
    fn = OUTPUTS.get(stage)
    if fn is None:
        return None
    out = fn(ch)
    for label in drop:
        out.pop(label, None)
    return out


def output_changed(before, now):
    """The labels whose digest differs between two `outputs` (the log line of a stage that reruns because of one)."""
    return changed(before, now)
