"""The stages a character is built in, what each needs, and how it knows.

    body      humanform body and rig from the brief (or an object already in the file)
    muscle    humanform's muscle definition on the unbaked body: delta-part shape keys weighted by the brief,
              as geometry, or (output = "normal") a high copy the bake stage bakes into the skin's normal
              map (optional: `[muscle]`)
    bake      one skinned mesh: shape keys and helpers baked, skin material, eyes joined
    hair      humanform's hair layer from a preset, joined into the body - except a strand part the
              strand stage will chain, which stays its own object (optional)
    flesh     follow-through jiggle bones (optional)
    moves     rig-anything's move set - after flesh, before garments
    strand    a follow-through spring-bone chain on the hair the hair stage left loose: a ponytail's
              tail (only where the preset grows one that is a line - `CHAINED_STRAND_KINDS`)
    garments  wardrobe presets, cut from the fleshed skin (optional)
    export    the glb, .moves.json, the hair strand's own glb and the garment glbs, and the .blend
    review    the review sheet: every clip as 8-frame strips of the dressed character (on unless the spec
              says `[review] enabled = false`), and the close-up look set: lit EEVEE close-ups of the face,
              eyes, head, hands, bust, crotch and feet in `review/<id>/close/` (`[review] close = false`
              leaves it out; the quality picks the views)

Each stage names the stages it needs and checks the file itself before it runs, so a stage run out of
order refuses with the order rather than producing a wrong result. The orders below were each found
by breaking them on a real character:

- moves before garments: rig-anything measures how far the arms hang out from what is bound to the
  rig, and 8 mm of sports top at the armpits sent Belle's run arms up over her head;
- flesh before garments: a garment is cut from the skin and takes its weights, and cut first it
  carries no jiggle bones;
- bake before moves;
- muscle before bake: `humanform.muscle.define` reads the fitted MPFB macros and writes shape keys, which
  `bake_for_game` then bakes; on a baked mesh there are neither. Like hair it cannot be taken off again, so a
  changed `[muscle]` rebuilds from body (the runner restarts there by itself, `RESTARTS_FROM_BODY`);
- hair once: the stage joins the hair into the body and cannot take it off again, so a body that already
  has hair refuses (`check_hair`) and changing `[hair]` means rebuilding from `body`;
- moves before strand: the chain hangs 3-8 new bones off the head bone, and rig-anything reads a rig's
  *structure* to find its limbs, neck and tail. The move set is authored (and stored) while the rig is
  still the body's own; `export_character` after the chain is the path follow-through's `strand_ponytail`
  fixture already exercises;
- strand before garments: the chain's colliders are measured from every other mesh skinned to the rig,
  and a top's cloth round the neck would widen the neck capsule the hair is held off.
"""

from __future__ import annotations

import os

import bpy

from . import quality as quality_mod
from . import spec as spec_mod


class StageRefused(RuntimeError):
    """A stage whose preconditions do not hold. The message names what to run first."""


# ------------------------------------------------------------------ what the file says

def _obj(name):
    return bpy.data.objects.get(name)


def garments_bound(ch):
    """Meshes wardrobe cut, bound to this character's rig."""
    rig = _obj(ch.rig)
    if rig is None:
        return []
    out = []
    for o in bpy.data.objects:
        if o.type != "MESH" or o.name == ch.mesh:
            continue
        if not any(m.type == "ARMATURE" and m.object == rig for m in o.modifiers):
            continue
        if o.get("wardrobe_cut") is not None or o.get("wardrobe") is not None:     # set by tailor / spec.write
            out.append(o.name)
    return sorted(out)


def baked(ch):
    ob = _obj(ch.mesh)
    return ob is not None and ob.type == "MESH" and not (ob.data.shape_keys and len(ob.data.shape_keys.key_blocks) > 1)


def fleshed(ch):
    ob = _obj(ch.mesh)
    if ob is None or "follow_through" not in ob:
        return False
    return any(g.name.startswith("ft_jiggle_") for g in ob.vertex_groups)


def haired(ch):
    """Meshes in the file that are already this character's hair - joined into the body, or a loose hair
    object left from a run that did not finish.

    humanform's `views.hair_objects` is the detector: a hair material on a mesh's slots (lookdev's `hair`
    preset, or `hair` as a whole part of the material's name, which is what the deprecated shell_bun path
    makes) or the `humanform_hair` property. The hair stage *joins* hair into the body, so it can only add a
    second layer over the first; this is what stops it.

    Only *this* character's meshes: the body, meshes named `<name>_*`, and meshes bound to its rig. A file
    can hold a whole crowd (`_clear_for` clears one character out of it by name), and another character's
    hair is not this one's."""
    ob = _obj(ch.mesh)
    if ob is None or ob.type != "MESH":
        return []
    from humanform import views
    rig = _obj(ch.rig)
    mine = [o for o in bpy.data.objects
            if o.type == "MESH" and o.name != ch.mesh
            and (o.name.startswith(ch.name + "_")
                 or (rig is not None and any(m.type == "ARMATURE" and m.object == rig for m in o.modifiers)))]
    return sorted(o.name for o in views.hair_objects(ob, mine))


def strand_meshes(ch):
    """This character's follow-through strand meshes: hair the hair stage left as its own object
    (`ft_type = "strand"` - humanform's ponytail tail).

    The hair stage joins its cap and its rigid volumes into the body, because rig-anything exports one
    mesh, but a strand cannot go in: the join drops the object properties the chain is built from
    (`ft_centreline`, `ft_root_bone`), and a body mesh can carry one follow-through spec, which on a
    fleshed body is its jiggle. So the strand stays a mesh of its own, gets its chain here, and is
    exported beside the body for `FollowThrough.attach`.

    Only this character's: named `<name>_*`, or skinned to its rig (as `haired` does, since a file can
    hold a whole crowd)."""
    rig = _obj(ch.rig)
    out = []
    for o in bpy.data.objects:
        if o.type != "MESH" or o.name == ch.mesh:
            continue
        if str(o.get("ft_type", "")).lower() != "strand":
            continue
        if o.name.startswith(ch.name + "_") or (
                rig is not None and any(m.type == "ARMATURE" and m.object == rig for m in o.modifiers)):
            out.append(o.name)
    return sorted(out)


def chained(ch):
    """The strand meshes that already carry a chain: a follow-through spec with `strands.chains`."""
    out = []
    for name in strand_meshes(ch):
        s = _obj(name).get("follow_through")
        if s is not None and (s.get("strands") or {}).get("chains"):
            out.append(name)
    return out


# The shapes of humanform strand follow-through hangs a chain on. A chain is a line, and
# `long_loose`'s curtain is a 16 cm-wide sheet: one chain down its middle turns it, running, into a
# twisted wedge standing out of the shoulder, and `verify_strands.gd` measures 2.9 cm of it inside the
# head (against 1.2 mm for the ponytail). Until follow-through builds a sheet of chains - or types the
# curtain as the shell it is - a curtain is joined into the body and rides the head rigidly, as all
# hair did before this stage existed.
CHAINED_STRAND_KINDS = ("tube",)


def hair_strand_kind(ch):
    """The shape of the strand part this spec's hair preset grows (`tube`, `curtain`), or None -
    humanform's own answer, not a list kept here, so a preset that grows one later needs no edit."""
    if ch.hair is None or ch.hair.kind != "preset" or not ch.hair.preset:
        return None
    from humanform import hair as hf_hair
    try:
        p = hf_hair.params(ch.hair.preset)
    except (KeyError, ValueError):
        return None
    return p["strand"]["kind"] if "strand" in p["parts"] else None


def hair_has_chain(ch):
    """Whether this spec's hair grows a strand the strand stage can chain."""
    return hair_strand_kind(ch) in CHAINED_STRAND_KINDS


def moves_stored(ch):
    """Roles of the spec with a report stored on their action (rig-anything `stored`)."""
    if _obj(ch.rig) is None:
        return []
    from rig_analysis import stored
    have = stored.load(ch.rig, roles=ch.moves.roles)
    return [r for r in ch.moves.roles if r in have and "error" not in have[r]]


# ------------------------------------------------------------------ stages

def _clear_for(ch):
    """Factory startup's cube, light and camera, and any earlier build of this character."""
    for o in list(bpy.data.objects):
        if o.name in ("Cube", "Light", "Camera") or o.name == ch.name or o.name.startswith(ch.name + "_"):
            bpy.data.objects.remove(o, do_unlink=True)
    # the skin material is reused by name (humanform `look.material`), so a normal map an earlier build wired into
    # it would ride along onto a body whose spec no longer asks for one
    mat = bpy.data.materials.get(f"{ch.name}_skin")
    if mat is not None:
        bpy.data.materials.remove(mat)
    img = bpy.data.images.get(f"{ch.name}_muscle_normal")
    if img is not None:
        bpy.data.images.remove(img)


def run_body(ch, ctx):
    if ch.body.source == "blend":
        if _obj(ch.body.object) is None:
            raise StageRefused(f"body: {ch.body.object!r} is not in the open file - open the .blend that holds it")
        return {"source": "blend", "object": ch.body.object}
    _clear_for(ch)
    from humanform import pipeline, sheet
    parts = ch.body.parts
    res = pipeline.make(sheet.new(**ch.body.brief), use_library=True, face_part=parts.get("face"),
                        hand_part=parts.get("hands"), foot_part=parts.get("feet"),
                        **quality_mod.settings(ctx["quality"], "body"))
    out = {k: res.get(k) for k in ("ansur", "check", "notes", "macros")}
    out["stature"] = _stature(res)
    out["library"] = res.get("path")                # reuse | warm | fresh: where the body's seconds went
    out["timing"] = res.get("timing")
    likeness = (res.get("fit") or {}).get("likeness")
    if likeness:                                    # a [body.face]: each measure as fitted against its target
        out["likeness"] = likeness
    return out


def _stature(res):
    """The body's stature in metres, from where `humanform.pipeline.make` puts it for each kind of body:

    - fitted to ANSUR (fresh or warm): the `stature` row of the fit's residuals, as the last pass measured it;
    - aged: `fit.aged.stature.stature_m`, the height macro bisected back to the brief after ageing;
    - child: `fit.stature.stature_m`, likewise;
    - reused from the library: the fit is one measurement with no residual rows, so the body is measured
      here with humanform's own `scaffold.stature`."""
    fit = res.get("fit") or {}
    for bisected in ((fit.get("aged") or {}).get("stature"), fit.get("stature")):
        if isinstance(bisected, dict) and bisected.get("stature_m") is not None:
            return bisected["stature_m"]
    for row in fit.get("residuals") or []:
        if row.get("measure") == "stature":
            return row.get("value")
    human = _obj(res.get("human") or "")
    if human is None:
        return None
    from humanform import scaffold
    return round(scaffold.stature(human), 4)


def muscled(ch):
    """Whether this character's body already carries muscle definition: humanform's `hfd:muscle` key on the
    unbaked body, or the mark the bake stage leaves on the baked mesh (`cp_muscle`)."""
    human = _obj(ch.name)
    if human is not None and human.type == "MESH" and human.data.shape_keys is not None:
        if any(k.name.startswith("hfd:muscle") for k in human.data.shape_keys.key_blocks):
            return True
    ob = _obj(ch.mesh)
    return ob is not None and ob.get("cp_muscle") is not None


def check_muscle(ch):
    if _obj(ch.rig) is None or _obj(ch.name) is None:
        if baked(ch):
            return ("muscle needs the unbaked body: %s is already baked - rebuild from body (definition is shape "
                    "keys on the humanform body, which bake bakes)" % ch.mesh)
        return "muscle needs body: no %s with its %s in the file - run body first" % (ch.name, ch.rig)
    if muscled(ch):
        return "muscle is already on %s - rebuild from body to change [muscle]" % ch.name
    return None


def run_muscle(ch, ctx):
    """`humanform.muscle.define` on the unbaked body for the brief: the definition groups on `hfd:muscle`
    (at 1 for geometry, at 0 for a normal map) and the limbs' missing bulk on `hfd:muscle-bulk` (always at 1,
    it is silhouette). Groups the spec leaves out are weighted 0. For a normal map the high copy is made
    here and kept (hidden) for the bake stage, which bakes it onto the game mesh and removes it."""
    from humanform import delta, muscle, sheet
    human = _obj(ch.name)
    brief = sheet.new(**ch.body.brief)
    off = {g: 0.0 for g in spec_mod.MUSCLE_GROUPS if g not in ch.muscle.groups}
    geometry = ch.muscle.output == "geometry"
    rep = muscle.define(human, brief, geometry=geometry, strength=ch.muscle.strength, weights_override=off or None)
    out = {"output": ch.muscle.output, "strength": ch.muscle.strength, "groups": list(ch.muscle.groups),
           "weights": rep["weights"], "body_fat_pct": rep["body_fat_pct"], "muscle_term": rep["muscle_term"],
           "definition_total": rep["definition_total"], "fitted_muscle": rep["fitted_muscle"],
           "spike_um": rep["spike_um"], "spike_limit_um": rep["spike_limit_um"], "card": rep["card"],
           "max_mm": (rep.get("applied") or {}).get("max_mm")}
    if not geometry:
        high = delta.high_copy(human, muscle.KEY, name=f"{ch.name}_muscle_high")
        high.hide_render = True
        out["high"] = high.name
    return out


def _bake_muscle_normal(ch, ctx):
    """The bake stage's half of `[muscle] output = "normal"`: the high copy baked into the skin's normal map
    on the game mesh (lookdev's matched bake), the image packed into the .blend, the high copy removed."""
    high = _obj(f"{ch.name}_muscle_high")
    if high is None:
        raise RuntimeError(f"bake: [muscle] output = \"normal\" but there is no {ch.name}_muscle_high - rebuild "
                           "from body")
    from . import plugins
    plugins.use("lookdev_blender")
    from lookdev_blender import detail
    size = ch.muscle.normal_size or quality_mod.settings(ctx["quality"], "muscle")["normal_size"]
    tex_dir = os.path.join(ctx["scratch"], "muscle_normal")
    nm = detail.bake_normal_from_high(_obj(ch.mesh), high, tex_dir, size=size, material=f"{ch.name}_skin",
                                      name=f"{ch.name}_muscle_normal")
    bpy.data.objects.remove(high, do_unlink=True)
    if "error" in nm:
        raise RuntimeError(f"bake: muscle normal map: {nm['error']}")
    img = nm.get("image")
    img = bpy.data.images.get(img) if isinstance(img, str) else img
    if img is not None and not img.packed_file:
        img.pack()
    return {"size": size, "method": nm["method"], "materials": nm["materials"], "warnings": nm["warnings"],
            "over_5deg": round(nm["stats"]["over_5deg"], 3)}


def _separate_joined(ch):
    """Before a rebake of an already baked mesh: take off the faces an earlier bake joined in (the eyes: every
    face whose material is not the skin's) as the `ch.eyes` object again, so `look.skin` - which gives every face
    the skin material - skins the body alone, and the join below puts them back with their own materials, as a
    first bake does. Without it a from=bake rerun gave the eyes the skin material and baked their UVs into the
    skin maps (study_woman's unmarked skin tone moved 0.858 -> 0.772). Returns the face count taken off."""
    ob = _obj(ch.mesh)
    if ob is None or _obj(ch.eyes) is not None:
        return 0
    skin = f"{ch.name}_skin"
    other = {i for i, m in enumerate(ob.data.materials) if m is None or m.name != skin}
    me = ob.data
    faces = [p.material_index in other for p in me.polygons]
    if not any(faces) or all(faces):
        return 0
    # a copy keeps the joined faces, the body keeps the rest: bmesh deletes carry vertex groups and attributes
    import bmesh
    part = ob.copy()
    part.data = me.copy()
    for c in ob.users_collection:
        c.objects.link(part)
    for target, drop in ((me, [i for i, f in enumerate(faces) if f]), (part.data, [i for i, f in enumerate(faces) if not f])):
        bm = bmesh.new()
        bm.from_mesh(target)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.faces[i] for i in drop], context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        bm.to_mesh(target)
        bm.free()
        target.update()
    part.name = ch.eyes
    return sum(faces)


def check_bake(ch):
    if _obj(ch.rig) is None or (_obj(ch.name) is None and not baked(ch)):
        return "bake needs body: no %s with its %s in the file - run body first" % (ch.name, ch.rig)
    already = haired(ch)
    if already:
        # measured on study_woman: a from=bake on her haired body baked a near-black albedo (tone error 0.79, every
        # region grey) - look.skin gives the hair and eye faces the skin material and the bake reads their UVs
        return ("bake on a body that already has hair joined (%s) would re-skin the hair and eyes and bake a broken "
                "albedo - rebuild from body (a whole build does this by itself)" % ", ".join(already))
    return None


def run_bake(ch, ctx):
    from humanform import look
    from rig_analysis import export as ra_export
    if _obj(ch.name) is not None:                    # the unbaked humanform mesh is still there
        b = ra_export.bake_for_game(ch.name, ch.rig, name=ch.mesh)
        if "error" in b:
            raise RuntimeError(f"bake: {b['error']}")
    else:
        b = {"note": "already baked"}
        split = _separate_joined(ch)
        if split:
            b["separated_for_rebake"] = split
    ob = _obj(ch.mesh)
    _obj(ch.rig).data.pose_position = "POSE"
    skin = ch.body.brief.get("skin") if ch.body.source == "brief" else ch.body.skin
    if skin is not None:
        # the maps' size is the build quality's (2048 px final, 1024 preview and draft): humanform's own
        # default is 1024, which every final build shipped until this was passed (06 rank 12)
        look.skin(ob, skin, name=f"{ch.name}_skin", size=quality_mod.settings(ctx["quality"], "skin")["size"])
    # the eyes, and a species head's parts and teeth (humanform.features: `<name>_headparts`, `<name>_teeth`,
    # skinned to their bones) keep their own materials; `_separate_joined` takes them off again as the eyes
    # object on a rebake
    parts = [o for o in (_obj(ch.eyes), _obj(ch.name + "_headparts"), _obj(ch.name + "_teeth")) if o is not None]
    if parts:
        with bpy.context.temp_override(active_object=ob, selected_editable_objects=[ob] + parts, object=ob,
                                       selected_objects=[ob] + parts):
            bpy.ops.object.join()
    unweighted = sum(1 for v in ob.data.vertices if not any(g.weight > 1e-4 for g in v.groups))
    out = {"verts": len(ob.data.vertices), "groups": len(ob.vertex_groups), "unweighted": unweighted,
           "materials": [m.name for m in ob.data.materials if m], "baked": b}
    sk = skin_manifest(ch)
    if sk is not None:
        out["skin"] = sk
    if ch.muscle is not None:
        if ch.muscle.output == "normal":
            out["muscle_normal"] = _bake_muscle_normal(ch, ctx)
        ob["cp_muscle"] = ch.muscle.output          # `muscled`: the baked body carries it now
    return out


def check_not_dressed(stage):
    def check(ch):
        if not baked(ch):
            return f"{stage} needs bake: {ch.mesh} is not a baked mesh - run bake first"
        worn = garments_bound(ch)
        if worn:
            return (f"garments are bound to the rig ({', '.join(worn)}) - run {stage} before garments, or build "
                    "from body (a whole build restarts there by itself; fresh=1 builds from nothing)"
                    + (": rig-anything measures arm hang against every mesh on the rig" if stage == "moves"
                       else ": a garment cut first carries no jiggle weights" if stage == "flesh" else ""))
        return None
    return check


def check_hair(ch):
    """`check_not_dressed`, and then: no hair in the file already.

    `run_hair` joins the hair into the body, so it can only ever add. On a rebuild where only `[hair]`
    changed, bake's hash is unchanged and bake is skipped, so without this the new layer went on top of the
    old one: the bun stayed in the mesh, and `humanform.hair`'s landmarks read the previous cap (weighted
    1.0 to the head bone) as scalp, so the crown rose and the head unit `h` grew - every measurement the
    hairline is placed from moved. Changing `[hair]` means rebuilding from `body`, which is the one stage
    that clears the character out of the file."""
    problem = check_not_dressed("hair")(ch)
    if problem:
        return problem
    already = haired(ch)
    if already:
        return ("hair is already in this file (%s) and the hair stage joins a layer on rather than "
                "replacing it - rebuild from body (from_stage=\"body\") to change [hair]" % ", ".join(already))
    return None


def _rest(ch):
    rig = _obj(ch.rig)
    if rig.animation_data:
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.view_layer.update()


def run_hair(ch, ctx):
    """humanform's hair layer from the spec's preset and colour, joined into the body - rig-anything exports
    one mesh.

    A strand part the strand stage will chain (`CHAINED_STRAND_KINDS`) is *not* joined: the join drops the
    object properties follow-through builds a chain from, and the strand stage needs them. It is left
    skinned to the rig with humanform's rigid fallback weights, so a build stopped before the strand stage
    still shows hair that moves with the head. Any other strand part is joined like the rest of the hair.
    Either way its follow-through contract is checked and reported here."""
    if ch.hair.kind == "shell_bun":
        from . import hair
        out = hair.shell_bun(ch, **ch.hair.params)
        out["deprecated"] = spec_mod.DEPRECATED["hair.kind"]
        return out
    from humanform import hair as hf_hair
    _rest(ch)
    face = ch.hair.face()
    if face.get("body_hair"):
        face["sex"] = ch.body.brief.get("sex") if ch.body.source == "brief" else None
    rep = hf_hair.add(ch.mesh, preset=ch.hair.preset, colour=ch.hair.colour, name=ch.name,
                      **face, **quality_mod.settings(ctx["quality"], "hair"))
    ob = _obj(ch.mesh)
    made = dict(rep["objects"])
    strand = made.pop("strand") if "strand" in made and hair_has_chain(ch) else None
    parts = [_obj(n) for n in made.values()]
    selected = [ob] + parts
    with bpy.context.temp_override(active_object=ob, selected_editable_objects=selected, object=ob,
                                   selected_objects=selected):
        bpy.ops.object.join()
    out = {"preset": rep["preset"], "colour": rep["colour"], "joined": sorted(made.values()),
           "head": rep["landmarks"]["head_bone"], "cap": rep["cap"], "hair": rep["hair"],
           "parts": rep["parts"], "material": {k: rep["material"].get(k) for k in ("material", "source", "gltf")}}
    if "face" in rep:
        out["face"] = rep["face"]
    out["strand_object"] = strand                   # None: there is none, or it was joined like the rest
    out["strand_kind"] = hair_strand_kind(ch)
    if "contract" in rep:
        out["strand_contract"] = rep["contract"]
        if not rep["contract"]["passed"]:
            raise RuntimeError(f"hair: the strand does not meet its follow-through contract: "
                               f"{rep['contract']['problems']}")
    return out


def judge_flesh(ch, r, asked=None):
    """What the flesh stage says it did: {"found": {type: [region names]}, "missed": [miss]}, printed to
    the build log, raising RuntimeError when a type the spec asks for found no mass and is not in
    `[flesh] may_miss`. `r` is follow-through's `flesh.prepare` (or `find_regions`) report; each miss is
    its `missed` entry - why, with the numbers - or `not_looked_for` for a type the registry lacks.

    A type named in the spec that finds no mass used to be dropped with no line in the log, the report
    or the manifest (study_woman's belly)."""
    asked = list(ch.flesh.types) if asked is None else asked
    found = {}
    for g in r.get("regions", []):
        found.setdefault(str(g["type"]), []).append(str(g["name"]))
    missed = [dict(m) for m in r.get("missed", []) if m["type"] in asked]
    for t in asked:
        if t not in found and not any(m["type"] == t for m in missed):
            missed.append({"type": t, "reason": "not_looked_for",
                           "message": f"{t}: not a flesh type follow-through's registry has, so never looked for"})
    out = {"found": {t: sorted(v) for t, v in sorted(found.items())}, "missed": missed}
    for t, names in out["found"].items():
        print(f"[{ch.id}] flesh: found {t}: {', '.join(names)}")
    # where each region's bone and weight landed on the body (follow-through's check_placement): a breast
    # bone on the chin passed every other check in the cast builds
    placement = r.get("placement") or {}
    misplaced = [p for row in placement.get("regions", []) for p in row["problems"]]
    if placement.get("regions"):
        out["placement"] = [{k: row[k] for k in ("name", "tail_height", "centre_height", "head_share", "ok")}
                            for row in placement["regions"]]
    if misplaced:
        for p in misplaced:
            print(f"[{ch.id}] flesh: MISPLACED {p}")
        raise RuntimeError("flesh: regions outside their anatomical zone: %s" % "; ".join(misplaced))
    for m in missed:
        allowed = m["type"] in ch.flesh.may_miss
        print(f"[{ch.id}] flesh: MISSED {m['message']}" + (" (allowed: [flesh] may_miss)" if allowed else ""))
    fatal = [m for m in missed if m["type"] not in ch.flesh.may_miss]
    if fatal:
        raise RuntimeError("flesh: the spec asks for %s and the body has none: %s. Add the type to [flesh] may_miss "
                           "to build without it" % ([m["type"] for m in fatal],
                                                     "; ".join(m["message"] for m in fatal)))
    return out


def undress(ch):
    """Take this character's garments off, so flesh can run again on a dressed body instead of the build restarting
    from body: every garment bound to the rig (`garments_bound`) with its mesh and the materials only it used, the
    hem bones wardrobe hung on the rig (`wd_role`), and the groups wardrobe's cover wrote on the body
    (`wd_hide_*`, `wd_edge_*`). The garments stage cuts them again from the new flesh. Returns what went, and
    `left`: anything of wardrobe's still in the file (then the caller restarts from body instead)."""
    rig = _obj(ch.rig)
    body = _obj(ch.mesh)
    worn = garments_bound(ch)
    meshes, mats = [], set()
    for name in worn:
        o = _obj(name)
        meshes.append(o.data)
        mats |= {m for m in o.data.materials if m is not None}
        bpy.data.objects.remove(o, do_unlink=True)
    for me in meshes:
        if me.users == 0:
            bpy.data.meshes.remove(me)
    for m in mats:
        if m.users == 0:
            bpy.data.materials.remove(m)
    hem = [b.name for b in rig.data.bones if b.get("wd_role") is not None]
    if hem:
        prev = bpy.context.view_layer.objects.active
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            for n in hem:
                eb = rig.data.edit_bones.get(n)
                if eb is not None:
                    rig.data.edit_bones.remove(eb)
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")
            if prev is not None and prev.name in bpy.context.view_layer.objects:
                bpy.context.view_layer.objects.active = prev
    groups = [g.name for g in body.vertex_groups if g.name.startswith(("wd_hide_", "wd_edge_"))]
    for n in groups:
        body.vertex_groups.remove(body.vertex_groups[n])
    left = garments_bound(ch) + [b.name for b in rig.data.bones if b.get("wd_role") is not None] + \
        [g.name for g in body.vertex_groups if g.name.startswith("wd_")]
    return {"garments": worn, "hem_bones": len(hem), "body_groups": groups, "left": left}


def preflesh_name(ch):
    """The mesh datablock that keeps the body as it was before its first jiggle bones (`_preflesh`)."""
    return f"{ch.mesh}:preflesh"


def _geometry_digest(me):
    import hashlib
    import numpy as np
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    loops = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", loops)
    return hashlib.sha1(np.round(co, 6).tobytes() + loops.tobytes()).hexdigest()[:16]


def _preflesh(ch):
    """Put the body back exactly as it was before the flesh stage first ran on it, or keep a copy of it as it is.

    follow-through takes each jiggle weight out of a vertex's other weights and then keeps the four strongest
    influences (`limit_influences`), so a second `flesh.prepare` can give back only what was not dropped: a rerun
    weighted study_man within 0.020 of a fresh build, and the moves stage, which reads the weights, had to rerun
    after every [flesh] edit. So the first flesh run keeps the unfleshed mesh (a copy of its data with a fake
    user, linked to no object, so no exporter sees it), and a rerun swaps it back in - geometry, materials and
    every weight exactly as bake and hair left them - before `prepare`. Only when it still fits: the same
    vertices and faces, and the object's vertex groups starting with the ones the copy was taken with (jiggle
    groups come after them); otherwise follow-through's own give-back is used, as before.
    Returns "kept", "restored" or why neither."""
    ob = _obj(ch.mesh)
    name = preflesh_name(ch)
    snap = bpy.data.meshes.get(name)
    jiggle = [g.name for g in ob.vertex_groups if g.name.startswith("ft_jiggle_")]
    if not jiggle:
        if snap is not None:
            bpy.data.meshes.remove(snap)
        snap = ob.data.copy()
        snap.name = name
        snap.use_fake_user = True
        snap["cp_groups"] = [g.name for g in ob.vertex_groups]
        snap["cp_geometry"] = _geometry_digest(ob.data)
        return "kept"
    if snap is None:
        return "no copy of the unfleshed body in this file (built before character-pipeline 0.10.0)"
    groups = list(snap.get("cp_groups") or [])
    names = [g.name for g in ob.vertex_groups]
    if names[:len(groups)] != groups or any(not n.startswith("ft_jiggle_") for n in names[len(groups):]):
        return "the body's vertex groups are not the copy's plus jiggle groups"
    if len(snap.vertices) != len(ob.data.vertices) or snap.get("cp_geometry") != _geometry_digest(ob.data):
        return "the body's geometry is not the copy's"
    old = ob.data
    keep = old.name
    fresh = snap.copy()
    fresh.use_fake_user = False
    for k in ("cp_groups", "cp_geometry"):
        if k in fresh:
            del fresh[k]
    ob.data = fresh
    bpy.data.meshes.remove(old)
    fresh.name = keep
    for g in [g for g in ob.vertex_groups if g.name.startswith("ft_jiggle_")]:
        ob.vertex_groups.remove(g)
    return "restored"


def run_flesh(ch, ctx):
    from follow_through import flesh as ft_flesh
    from follow_through import marks
    _rest(ch)
    regions = None
    out = {"unfleshed": _preflesh(ch)}
    if ctx.get("undressed"):
        out["undressed"] = ctx.pop("undressed")
    if ch.flesh.zones:
        sheet_dir = os.path.join(ctx["scratch"], "flesh_sheet")
        sheet = marks.render(ch.mesh, sheet_dir, views=("front", "right", "back"), focus="torso")
        found = marks.regions(ch.mesh, ch.flesh.zones, sheet)
        regions = found["regions"]
        out["zones"] = len(ch.flesh.zones)
    r = ft_flesh.prepare(ch.mesh, rig_name=ch.rig, regions=regions,
                         types=ch.flesh.types or None if regions is None else None,
                         overrides=ch.flesh.overrides or None)
    if "error" in r:
        raise RuntimeError(f"flesh: {r['error']}")
    out.update(judge_flesh(ch, r, asked=list(ch.flesh.types) if regions is None else []))
    # copied out first: set_params replaces the object's `follow_through` property, and iterating the
    # old one while that happens reads freed memory (it crashed Blender)
    spec_regions = [(str(g["name"]), str(g["type"]), float(g["peak_m"]))
                    for g in _obj(ch.mesh)["follow_through"]["jiggle"]["regions"] if "peak_m" in g]
    limits = {}
    for name, kind, peak in spec_regions:
        if kind in ch.flesh.limit_share:
            limits[name] = round(ch.flesh.limit_share[kind] * peak, 4)
            ft_flesh.set_params(ch.mesh, name, max_offset_m=limits[name])
    out.update({"summary": ft_flesh.summarize(r), "limits_m": limits})
    return out


def run_moves(ch, ctx):
    from rig_analysis import actions, verify
    for a in list(bpy.data.actions):
        if a.name.startswith(ch.name + "_"):
            bpy.data.actions.remove(a)
    held = {"style": ch.moves.style}
    if ch.moves.stance_width is not None:
        held["stance_width"] = ch.moves.stance_width
    if ch.moves.posture is not None:
        held["posture"] = ch.moves.posture
    options = {"Idle": dict(held)}
    for role, froude in ch.moves.gaits.items():
        options[role] = dict(held, froude=froude)
    for role, extra in ch.moves.per_gait.items():
        options[role] = dict(options.get(role, {}), **extra)
    # This character's own fixed left/right asymmetry, drawn from its identity. None or
    # `asymmetry = 0` (the default) is the identity and every clip is the one it always was.
    # A species' build implies a style (rig-anything's morphology.derive_style: a long trunk's roll, a stocky
    # body's ground time), laid under the spec's own, which wins key by key. Off for a human unless asked, and
    # a human-proportioned body derives nothing anyway, so a human's clips are the ones it always had.
    derive = ch.derive_moves
    res = actions.move_set(ch.rig, prefix=ch.name, roles=tuple(ch.moves.roles), options=options,
                           variability=variability_block(ch), derive=derive)
    if "error" in res:
        raise RuntimeError(f"moves: {res['error']}")
    out = {}
    for role in ch.moves.roles:
        r = res[role]
        if "error" in r:
            raise RuntimeError(f"moves {role}: {r['error']}")
        up = r.get("upper") or {}
        out[role] = {"action": r["action"], "passed": r.get("passed"), "failures": r.get("failures", [])[:4],
                     "stance_width": r.get("stance_width"), "drop_m": r.get("drop_m"),
                     "arm_out": up.get("arm_out"), "arm_clearance_m": r.get("arm_clearance_m")}
        if r.get("variability"):
            # what the asymmetry did, measured off the baked clip - only present when a spec
            # opted in, so a character at the default reports exactly what it always reported
            out[role]["variability"] = r["variability"]
    for role in ch.moves.clearance_check:
        c = verify.limb_clearance(ch.rig, res[role]["action"], mesh_name=ch.mesh, every=2)
        out[role]["limb_clearance"] = {k: c.get(k) for k in ("closest_m", "at_frame", "samples_inside", "error")
                                       if k in c}
    # Warned, never refused (each with its fix), and printed before a failing clip refuses the stage: a walk
    # outside Froude 0.18-0.35, hands that cannot reach the hips or the top of the head (a dwarf's short arms).
    # Only in the report when there is something to say.
    from rig_analysis import bodymap, morphology
    bm = bodymap.build(ch.rig, forward="-Y")
    warnings = morphology.checks(res, morphology.measure(bm, with_mass=False)) if "error" not in bm else []
    for w in warnings:
        print(f"[{ch.id}] moves WARNING {w}")
    if warnings:
        out["warnings"] = warnings
    if derive:
        got = next((res[r]["morphology"] for r in ch.moves.roles if res[r].get("morphology")), None)
        if got:
            out["derived_style"] = got["derived"]
            out["morphology"] = got["measured"]
    failing = sorted(role for role in ch.moves.roles if out[role]["failures"] and role not in ch.moves.may_fail)
    if failing:
        # each failing clip with what failed and by how much, so the fix (a [moves.per_gait.<role>] option, or
        # may_fail) can be chosen from the message alone instead of by rebuilding to read the stored report
        why = "; ".join(f"{role}: {' | '.join(res[role].get('failures') or out[role]['failures'])}" for role in failing)
        raise RuntimeError(f"moves: clips failing their checks: {failing} - {why} (tune the role in "
                           "[moves.per_gait.<role>], or list it in moves.may_fail to export it forced)")
    ctx["moves"] = res
    return out


def check_strand(ch):
    """A strand mesh to chain, the move set already authored, and nothing dressed yet."""
    problem = check_not_dressed("strand")(ch)
    if problem:
        return problem
    if not strand_meshes(ch):
        return ("strand needs hair: no mesh with ft_type = \"strand\" for %s in the file - run hair first "
                "(the %s preset grows one)" % (ch.name, (ch.hair.preset if ch.hair else None) or "ponytail"))
    missing = [r for r in ch.moves.roles if r not in moves_stored(ch)]
    if missing:
        return (f"strand needs moves: no stored clips for {missing} - run moves before strand (rig-anything "
                "reads the rig's structure to find its limbs and neck, so the move set is authored before "
                "3-8 chain bones hang off the head)")
    return None


def run_strand(ch, ctx):
    """follow-through's spring-bone chain on each strand mesh the hair stage left loose.

    `strand.prepare` hangs the bones off the strand's `ft_root_bone` (the head), weights the mesh along
    them, measures head and neck colliders from the body's own skin and writes the `strands` spec the
    Godot modifier springs. The spec travels in the strand's own glb (`run_export`), which
    `FollowThrough.attach` puts on the body's skeleton."""
    from follow_through import strand as ft_strand
    _rest(ch)
    out = {}
    for name in strand_meshes(ch):
        r = ft_strand.prepare(name, rig_name=ch.rig)
        if "error" in r:
            raise RuntimeError(f"strand: {r['error']}")
        if not r["colliders"]:
            raise RuntimeError(f"strand: {name} has no head or neck collider - nothing would keep the "
                               "hair out of the head in Godot")
        blk = r["spec"]["strands"]
        out[name] = {
            "type": r["type"], "type_source": r["type_source"], "material": r["material"],
            "root_bone": r["root_bone"], "warnings": r["warnings"],
            "chains": [dict(c, frequency_hz=[b["frequency_hz"] for b in s["bones"]],
                            bone_names=[b["bone"] for b in s["bones"]])
                       for c, s in zip(r["chains"], blk["chains"])],
            "colliders": r["colliders"], "collider_source": r["collider_source"],
            "weights": r["weights"],
            "damping_ratio": blk["chains"][0]["bones"][0]["damping_ratio"],
            "collision_friction": blk["collision_friction"],
        }
    return out


def check_garments(ch):
    if not baked(ch):
        return "garments needs bake - run bake first"
    missing = [r for r in ch.moves.roles if r not in moves_stored(ch)]
    if missing:
        return (f"garments needs moves: no stored clips for {missing} - run moves before garments "
                "(rig-anything measures arm hang against every mesh on the rig)")
    if ch.flesh is not None and not fleshed(ch):
        return "garments needs flesh: the body has no jiggle bones yet - run flesh before garments"
    return None


def run_garments(ch, ctx):
    from wardrobe import presets
    _rest(ch)
    out, made, res = {}, {}, []                     # made: preset -> garment object name
    for g in ch.outfit:
        preset = presets.get(g.preset)
        name = g.name or preset.get("name") or g.preset
        path = os.path.join(ch.out_dir(), f"{ch.id}_{name.lower()}.glb")
        # worn over whichever of the presets it names are in this outfit, innermost first
        over = [made[p] for p in preset.get("worn_over", []) if p in made]
        r = presets.dress(ch.mesh, g.preset, name=name, colour=g.colour, out_path=path, over=over)
        if not r.get("passed"):
            raise RuntimeError(f"garments: {name} did not pass: {r.get('problems')}")
        made[g.preset] = name
        out[name] = {k: r.get(k) for k in ("verts", "cut", "cover", "jiggle_groups", "export", "passed")}
        res.append(f"{ch.export.res_dir}/{ch.id}_{name.lower()}.glb")
    ctx["garment_res"] = res
    return {"garments": out, "res": res}


def check_export(ch):
    missing = [r for r in ch.moves.roles if r not in moves_stored(ch)]
    if missing:
        return f"export needs moves: no stored clips for {missing} - run moves first"
    if ch.outfit and not garments_bound(ch):
        return "export needs garments: the spec has an outfit and none is bound - run garments first"
    loose = [n for n in strand_meshes(ch) if n not in chained(ch)]
    if loose:
        return (f"export needs strand: {', '.join(loose)} has no spring-bone chain yet - run strand first, "
                "or the hair would ship weighted rigidly to the head and never swing")
    return None


def variability_block(ch):
    """The seam's `variability` block for this character: the RESOLVED values a build used, or
    None when the spec has no `[variability]`.

    {"seed": int, "asymmetry": float, "jitter_phase": float, "jitter_amp": float}. An unstated
    seed is derived from `character.id`, so it is the same in every build of this spec and
    different for every other character. rig-anything bakes `asymmetry`; the two jitter dials
    are the runtime half and are carried through untouched for the engine to read."""
    if ch.variability is None or not ch.variability.asked():
        # An empty `[variability]` table asks for nothing, so it is nothing: it is left out of
        # the moves hash (`spec.Character.section`) and it writes no manifest key either, or the
        # two would disagree - a spec that added the empty table would hash the same, skip
        # export, and never grow the key it had just asked for.
        return None
    from rig_analysis import variability as ra_var
    try:
        return ra_var.resolve(ch.variability.table(), ch.id)
    except ra_var.VariabilityError as e:
        raise RuntimeError(f"[variability]: {e}") from e


def run_export(ch, ctx):
    from rig_analysis import export as ra_export, stored
    from wardrobe import presets
    os.makedirs(ch.out_dir(), exist_ok=True)
    glb = os.path.join(ch.out_dir(), f"{ch.id}.glb")
    reports = stored.load(ch.rig, roles=ch.moves.roles)
    stand = (reports.get("Idle") or {}).get("standing_height_m")
    if stand is None:
        # Not reachable through the stages (a spec must list Idle, and export refuses without its stored
        # report), so this is a stored Idle report that never measured it. Falling back to the mesh top
        # would quietly bring back the second convention the field was removed to end.
        raise RuntimeError("export: the stored Idle report has no standing_height_m, which height_m.stand is "
                           "taken from - rerun moves (from_stage=\"moves\") so rig-anything measures it")
    garment_names = [g.name or presets.get(g.preset).get("name") or g.preset for g in ch.outfit]
    extra = {
        "style": ch.moves.style,
        "posture": ch.moves.posture,
        "stance_width": ch.moves.stance_width,
        "note": ch.export.note or f"{ch.name}: built by character-pipeline from {os.path.basename(ch.path or '')}",
    }
    if garment_names:
        # the garments a controller equips, innermost first
        extra["garments"] = [f"{ch.export.res_dir}/{ch.id}_{n.lower()}.glb" for n in garment_names]
    strands = chained(ch)
    strand_glb = os.path.join(ch.out_dir(), f"{ch.id}_hair.glb")
    if strands:
        # the strand file a controller hands FollowThrough.attach, then apply - one glb for every chain
        extra["strands"] = [f"{ch.export.res_dir}/{ch.id}_hair.glb"]
    if ch.body.source == "brief":
        extra["brief"] = dict(ch.body.brief, name=ch.name)
    # The seam: ONE top-level key, holding the resolved values this build actually used. Written
    # only for a spec with a [variability] table, so every manifest built before this key existed
    # stays byte-for-byte what it was.
    var = variability_block(ch)
    if var is not None:
        extra["variability"] = var
    e = ra_export.export_character(ch.mesh, ch.rig, glb, name=ch.name, creature=ch.id, reports=reports,
                                   res_path=f"{ch.export.res_dir}/{ch.id}.glb", roles=list(ch.moves.roles),
                                   loops=list(ch.moves.loops), gaits=list(ch.moves.export_gaits),
                                   force=bool(ch.moves.may_fail), extra=extra, review=False)
    if "error" in e:
        raise RuntimeError(f"export refused: {e['error']}")
    forced = sorted(set(e["manifest"].get("forced_clips") or [])
                    - {f"{ch.name}_{r}" for r in ch.moves.may_fail} - set(ch.moves.may_fail))
    if forced:
        raise RuntimeError(f"export: clips shipped only by force that the spec does not allow: {forced}")
    # One convention for standing height: the Idle clip's (the rig standing at rest, which a hair bun does
    # not raise). rig-anything writes the collider's height there; replaced here, in the file and the result.
    import json
    with open(e["moves"], encoding="utf-8") as fh:
        manifest = json.load(fh)
    manifest["height_m"]["stand"] = stand
    with open(e["moves"], "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    e["manifest"]["height_m"]["stand"] = stand
    fl = flesh_manifest(ch)
    sk = skin_manifest(ch)
    for key, block in (("flesh", fl), ("skin", sk)):
        if block is not None:
            manifest[key] = block
            e["manifest"][key] = block
    if fl is not None or sk is not None:
        with open(e["moves"], "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
    out = {k: e.get(k) for k in ("glb", "moves", "verified", "clips", "bones", "problems")}
    if fl is not None:
        out["flesh"] = fl
    if sk is not None:
        out["skin"] = sk
    if strands:
        from follow_through import strand as ft_strand
        s = ft_strand.export(strand_glb, strands, ch.rig)
        if not s.get("passed"):
            raise RuntimeError(f"export: the hair strand glb did not read back: "
                               f"{s.get('error') or [c['problems'] for c in s.get('specs', [])]}")
        out["strands"] = {"glb": s["path"], "res": extra["strands"], "meshes": s["meshes"],
                          "specs": [{k: c.get(k) for k in ("node", "route", "strand_chains", "strand_bones",
                                                           "strand_head_error_m", "problems")}
                                    for c in s.get("specs", [])]}
    return out


def flesh_manifest(ch):
    """The manifest's `flesh` block: what the glb's jiggle bones are and how they are sprung, and what
    the spec asked for that the flesh stage did not find. None for a spec with no [flesh].

    {"regions": [{name, type, bone, parent, peak_m, max_offset_m, material, frequency_hz,
    damping_ratio}], "missed": [{type, reason}]}. A game reads it without opening the glb; the Godot
    verifier (verify_flesh.gd) checks each bone's swing against its peak_m."""
    if ch.flesh is None:
        return None
    spec = _obj(ch.mesh).get("follow_through")
    regions = []
    if spec is not None and "jiggle" in spec:
        for g in spec["jiggle"]["regions"]:
            g = {k: g[k] for k in g.keys()}
            row = {"name": str(g["name"]), "type": str(g["type"]), "bone": str(g["bone"]),
                   "parent": str(g.get("parent", "")), "peak_m": round(float(g["peak_m"]), 4),
                   "max_offset_m": round(float(g["max_offset_m"]), 4),
                   "material": str(g["material"]) if g.get("material") is not None else None}
            for k in ("frequency_hz", "damping_ratio"):
                if g.get(k) is not None:
                    row[k] = round(float(g[k]), 4)
            regions.append(row)
    # the reasons are in the flesh stage's stored report when it fitted there; which types are
    # missing is read from the bones themselves, so it holds whatever the record kept
    from . import runner
    rec = (runner.records(ch).get("flesh") or {}).get("report") or {}
    why = {m.get("type"): m.get("reason") for m in rec.get("missed") or [] if isinstance(m, dict)}
    have = {r["type"] for r in regions}
    missed = [{"type": t, "reason": why.get(t), "allowed": t in ch.flesh.may_miss}
              for t in ch.flesh.types if t not in have]
    return {"types": list(ch.flesh.types), "regions": regions, "missed": missed}


def skin_manifest(ch):
    """The manifest's `skin` block: how the skin shipped, read from the skin material in the file (humanform's
    `humanform_skin` record), not from a stage report - `{stage, map_px, tone_ok, tone_error, regions, contrast,
    contrast_ok, roughness}`.
    `stage` is "baked" (maps of `map_px` square), "flat" (no maps: the bake failed or lookdev was absent, with
    its `error`) or "marked" (an unbaked MPFB body). None when the body has no skin material of humanform's."""
    mat = bpy.data.materials.get(f"{ch.name}_skin")
    rec = mat.get("humanform_skin") if mat is not None else None
    if rec is None:
        return None
    rec = rec.to_dict() if hasattr(rec, "to_dict") else dict(rec)
    stage = str(rec.get("stage", ""))
    out = {"stage": "marked" if stage == "flat" and rec.get("marked") and "size" not in rec else stage,
           "map_px": int(rec["size"]) if stage == "baked" and rec.get("size") is not None else None}
    if rec.get("tone_ok") is not None:
        out["tone_ok"] = bool(rec["tone_ok"])
        out["tone_error"] = round(float(rec.get("tone_error", 0.0)), 4)
    if rec.get("regions"):
        # each marked region's tone in the baked albedo (sRGB): a bake that lost the marks has them all equal
        out["regions"] = {str(k): [round(float(x), 3) for x in v] for k, v in dict(rec["regions"]).items()}
    if rec.get("contrast"):
        # each region against plain skin in the baked albedo: CIELAB dE, lightness and red/green (humanform 0.14.0),
        # and whether every floored region reached humanform's CONTRAST_FLOOR (the failures listed when not)
        out["contrast"] = {str(k): {str(a): float(b) for a, b in dict(v).items()} for k, v in dict(rec["contrast"]).items()}
        out["contrast_ok"] = bool(rec.get("contrast_ok"))
        if rec.get("contrast_fail"):
            out["contrast_fail"] = [str(x) for x in rec["contrast_fail"]]
    if rec.get("roughness"):
        # the baked roughness over each region's texels, the T-zone's and plain skin's
        out["roughness"] = {str(k): round(float(v), 3) for k, v in dict(rec["roughness"]).items()}
    if rec.get("error"):
        out["error"] = str(rec["error"])
    return out


def review_dir(ch):
    """Where the review sheet goes: `<export dir>/review/<id>/` (the `review/` folder carries a .gdignore)."""
    return os.path.join(ch.out_dir(), "review", ch.id)


def check_review(ch):
    glb = os.path.join(ch.out_dir(), f"{ch.id}.glb")
    if not os.path.isfile(glb):
        return f"review needs export: no {glb} - run export first"
    missing = [r for r in ch.moves.roles if r not in moves_stored(ch)]
    if missing:
        return f"review needs moves: no stored clips for {missing} - run moves first"
    return None


def close_dir(ch):
    """Where the close-up look set goes: `<export dir>/review/<id>/close/`."""
    return os.path.join(review_dir(ch), "close")


def wears_top(ch):
    """Whether the outfit has a garment over the bust: a wardrobe preset cut as a shirt or a dress."""
    if not ch.outfit:
        return False
    from wardrobe import presets
    return any(presets.get(g.preset).get("cut") in ("shirt", "dress")
               for g in ch.outfit)


def close_pose(ch):
    """The clip and frame the close-up set is posed on: the Idle's first frame, else the first role's."""
    roles = list(ch.moves.roles)
    role = "Idle" if "Idle" in roles else (roles[0] if roles else None)
    return f"{ch.name}_{role}" if role else None


def run_close(ch, ctx, meshes, aim_override=None):
    """rig-anything's close-up look set of the dressed character (`closeups.look_set`), at this quality's views;
    raises when a tile shows no body or its camera is not on the part it names. `aim_override` is the stage
    test's control only (a camera aimed from the wrong bone must fail)."""
    from rig_analysis import closeups
    q = quality_mod.settings(ctx["quality"], "close")
    r = closeups.look_set(meshes, ch.rig, close_dir(ch), views=q["views"], action=close_pose(ch),
                          under_bust=bool(q["under_bust"]) and wears_top(ch), title=ch.name,
                          aim_override=aim_override)
    if "error" in r:
        raise RuntimeError(f"review: close-up set: {r['error']}")
    if r["failed"]:
        raise RuntimeError(f"review: close-up tiles that do not show their part: {r['failed']}")
    return closeups.summary(r)


def run_review(ch, ctx):
    """rig-anything's review sheet of the character as the game shows it: the body with its hair and every
    garment bound to the rig, each clip the export shipped, at the shared scale (2.1 m for a person) - then
    the close-up look set (`run_close`), unless `[review] close = false`."""
    import json
    import time
    from rig_analysis import review
    with open(os.path.join(ch.out_dir(), f"{ch.id}.moves.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    clips = [manifest["clips"][r] for r in ch.moves.roles if r in manifest["clips"]]
    meshes = review.bound_meshes(ch.rig, first=ch.mesh)
    r = review.sheet(meshes, ch.rig, clips, review_dir(ch), loops=manifest.get("loops", []),
                     frame_height_m=ch.review.frame_height_m, title=ch.name,
                     **quality_mod.settings(ctx["quality"], "review"))
    if "error" in r:
        raise RuntimeError(f"review: {r['error']}")
    empty = sorted(f"{c} {v}" for c, vs in r["strips"].items() for v, s in vs.items()
                   if s["cells_with_body"] < len(r["frames"][c]))
    if empty:
        raise RuntimeError(f"review: strips with cells showing no body: {empty}")
    # nothing may reach an edge: sideways it would land in the next frame's cell, and at the bottom or the
    # top the frame has cut the pose off - which is what the sheet exists to show
    cut = sorted(f"{c} {v}" for c, vs in r["strips"].items() for v, s in vs.items() if s["edge_cells"])
    if cut:
        raise RuntimeError(f"review: strips whose body reaches the edge of the picture: {cut}")
    out = review.summary(r)
    out["meshes"] = meshes
    if ch.review.close:
        t0 = time.time()
        out["close"] = run_close(ch, ctx, meshes)
        out["close"]["stage_seconds"] = round(time.time() - t0, 2)
    else:
        removed = clear_close(ch)
        if removed:
            out["close_removed"] = removed
    return out


def clear_close(ch):
    """`[review] close = false`: take away a close-up set an earlier build wrote, so nothing reads a stale
    one as this build's. Only what `closeups.look_set` writes (pngs, close.json, .gdignore) is removed, then the
    folder if that left it empty. Returns the folder removed, or None when there was none."""
    d = close_dir(ch)
    if not os.path.isdir(d):
        return None
    for f in os.listdir(d):
        if f.endswith(".png") or f in ("close.json", ".gdignore"):
            os.remove(os.path.join(d, f))
    if not os.listdir(d):
        os.rmdir(d)
    return d


# (name, needs, spec sections its hash covers, precondition check, run, applies to this spec)
STAGES = [
    ("body", (), ("character", "body"), lambda ch: None, run_body, lambda ch: True),
    ("muscle", ("body",), ("muscle",), check_muscle, run_muscle, lambda ch: ch.muscle is not None),
    ("bake", ("body", "muscle"), ("character", "body"), check_bake, run_bake, lambda ch: True),
    ("hair", ("bake",), ("hair",), check_hair, run_hair, lambda ch: ch.hair is not None),
    ("flesh", ("bake", "hair"), ("flesh",), check_not_dressed("flesh"), run_flesh, lambda ch: ch.flesh is not None),
    ("moves", ("bake", "hair", "flesh"), ("moves",), check_not_dressed("moves"), run_moves, lambda ch: True),
    ("strand", ("hair", "moves"), ("hair",), check_strand, run_strand, hair_has_chain),
    ("garments", ("moves", "flesh", "strand"), ("outfit",), check_garments, run_garments, lambda ch: bool(ch.outfit)),
    ("export", ("moves", "garments", "strand"), ("export", "moves"), check_export, run_export, lambda ch: True),
    ("review", ("export",), ("review",), check_review, run_review, lambda ch: ch.review.enabled),
]
ORDER = [s[0] for s in STAGES]

# Stages that put something on the body that nothing takes off again (hair joins into the mesh, muscle is baked
# into it): {stage: does the body carry it?}. A whole build restarts from body (forced) instead of stacking a
# second layer, refusing, or shipping a layer the spec dropped, when one of them
# - has to run (its section is new or changed) and the body carries it already, or cannot take it any more
#   (`RESTARTS_FROM_BODY`: muscle on a body already baked), or
# - is no longer in the spec and the body still carries it.
CARRIED = {"hair": lambda ch: bool(haired(ch)), "muscle": muscled}
RESTARTS_FROM_BODY = {"hair": CARRIED["hair"],
                      "muscle": lambda ch: muscled(ch) or (_obj(ch.name) is None and baked(ch)),
                      # a bake that has to run again on a body that already has hair joined: humanform's look.skin
                      # gives every face the skin material (the hair's and eyes' too), and hair must follow it anyway
                      # and cannot go on twice - so start from body rather than bake, re-skin, then restart at hair
                      "bake": CARRIED["hair"],
                      # flesh and moves on a dressed body: the garments were cut from (and weighted by) the body
                      # before, and flesh/moves refuse while they are bound - a resumed build of a dressed spec
                      # whose [moves] changed starts over from body, as the build did before builds resumed from
                      # the saved blend; flesh's garments are taken off first (runner.UNDRESS_FOR_FLESH,
                      # `undress`), so flesh restarts from body only when that is turned off or leaves something
                      "flesh": lambda ch: bool(garments_bound(ch)),
                      "moves": lambda ch: bool(garments_bound(ch))}
