"""The stages a character is built in, what each needs, and how it knows.

    body      humanform body and rig from the brief (or an object already in the file)
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
              says `[review] enabled = false`)

Each stage names the stages it needs and checks the file itself before it runs, so a stage run out of
order refuses with the order rather than producing a wrong result. The orders below were each found
by breaking them on a real character:

- moves before garments: rig-anything measures how far the arms hang out from what is bound to the
  rig, and 8 mm of sports top at the armpits sent Belle's run arms up over her head;
- flesh before garments: a garment is cut from the skin and takes its weights, and cut first it
  carries no jiggle bones;
- bake before moves;
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


def run_body(ch, ctx):
    if ch.body.source == "blend":
        if _obj(ch.body.object) is None:
            raise StageRefused(f"body: {ch.body.object!r} is not in the open file - open the .blend that holds it")
        return {"source": "blend", "object": ch.body.object}
    _clear_for(ch)
    from humanform import pipeline, sheet
    parts = ch.body.parts
    res = pipeline.make(sheet.new(**ch.body.brief), use_library=True, face_part=parts.get("face"),
                        hand_part=parts.get("hands"), foot_part=parts.get("feet"))
    out = {k: res.get(k) for k in ("ansur", "check", "notes", "macros")}
    out["stature"] = _stature(res)
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


def check_bake(ch):
    if _obj(ch.rig) is not None and (_obj(ch.name) is not None or baked(ch)):
        return None
    return "bake needs body: no %s with its %s in the file - run body first" % (ch.name, ch.rig)


def run_bake(ch, ctx):
    from humanform import look
    from rig_analysis import export as ra_export
    if _obj(ch.name) is not None:                    # the unbaked humanform mesh is still there
        b = ra_export.bake_for_game(ch.name, ch.rig, name=ch.mesh)
        if "error" in b:
            raise RuntimeError(f"bake: {b['error']}")
    else:
        b = {"note": "already baked"}
    ob = _obj(ch.mesh)
    _obj(ch.rig).data.pose_position = "POSE"
    skin = ch.body.brief.get("skin") if ch.body.source == "brief" else ch.body.skin
    if skin is not None:
        look.skin(ob, skin, name=f"{ch.name}_skin")
    eyes = _obj(ch.eyes)
    if eyes is not None:
        with bpy.context.temp_override(active_object=ob, selected_editable_objects=[ob, eyes], object=ob,
                                       selected_objects=[ob, eyes]):
            bpy.ops.object.join()
    unweighted = sum(1 for v in ob.data.vertices if not any(g.weight > 1e-4 for g in v.groups))
    return {"verts": len(ob.data.vertices), "groups": len(ob.vertex_groups), "unweighted": unweighted,
            "materials": [m.name for m in ob.data.materials if m], "baked": b}


def check_not_dressed(stage):
    def check(ch):
        if not baked(ch):
            return f"{stage} needs bake: {ch.mesh} is not a baked mesh - run bake first"
        worn = garments_bound(ch)
        if worn:
            return (f"garments are bound to the rig ({', '.join(worn)}) - run {stage} before garments"
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
    rep = hf_hair.add(ch.mesh, preset=ch.hair.preset, colour=ch.hair.colour, name=ch.name)
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
    out["strand_object"] = strand                   # None: there is none, or it was joined like the rest
    out["strand_kind"] = hair_strand_kind(ch)
    if "contract" in rep:
        out["strand_contract"] = rep["contract"]
        if not rep["contract"]["passed"]:
            raise RuntimeError(f"hair: the strand does not meet its follow-through contract: "
                               f"{rep['contract']['problems']}")
    return out


def run_flesh(ch, ctx):
    from follow_through import flesh as ft_flesh
    from follow_through import marks
    _rest(ch)
    regions = None
    out = {}
    if ch.flesh.zones:
        sheet_dir = os.path.join(ctx["scratch"], "flesh_sheet")
        sheet = marks.render(ch.mesh, sheet_dir, views=("front", "right", "back"), focus="torso")
        found = marks.regions(ch.mesh, ch.flesh.zones, sheet)
        regions = found["regions"]
        out["zones"] = len(ch.flesh.zones)
    r = ft_flesh.prepare(ch.mesh, rig_name=ch.rig, regions=regions,
                         types=ch.flesh.types or None if regions is None else None)
    if "error" in r:
        raise RuntimeError(f"flesh: {r['error']}")
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
    res = actions.move_set(ch.rig, prefix=ch.name, roles=tuple(ch.moves.roles), options=options)
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
    for role in ch.moves.clearance_check:
        c = verify.limb_clearance(ch.rig, res[role]["action"], mesh_name=ch.mesh, every=2)
        out[role]["limb_clearance"] = {k: c.get(k) for k in ("closest_m", "at_frame", "samples_inside", "error")
                                       if k in c}
    failing = sorted(role for role in ch.moves.roles if out[role]["failures"] and role not in ch.moves.may_fail)
    if failing:
        raise RuntimeError(f"moves: clips failing their checks: {failing} (list a role in moves.may_fail "
                           "to export it forced)")
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
    out = {k: e.get(k) for k in ("glb", "moves", "verified", "clips", "bones", "problems")}
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


def run_review(ch, ctx):
    """rig-anything's review sheet of the character as the game shows it: the body with its hair and every
    garment bound to the rig, each clip the export shipped, at the shared scale (2.1 m for a person)."""
    import json
    from rig_analysis import review
    with open(os.path.join(ch.out_dir(), f"{ch.id}.moves.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    clips = [manifest["clips"][r] for r in ch.moves.roles if r in manifest["clips"]]
    meshes = review.bound_meshes(ch.rig, first=ch.mesh)
    r = review.sheet(meshes, ch.rig, clips, review_dir(ch), loops=manifest.get("loops", []),
                     frame_height_m=ch.review.frame_height_m, title=ch.name)
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
    return out


# (name, needs, spec sections its hash covers, precondition check, run, applies to this spec)
STAGES = [
    ("body", (), ("character", "body"), lambda ch: None, run_body, lambda ch: True),
    ("bake", ("body",), ("character", "body"), check_bake, run_bake, lambda ch: True),
    ("hair", ("bake",), ("hair",), check_hair, run_hair, lambda ch: ch.hair is not None),
    ("flesh", ("bake", "hair"), ("flesh",), check_not_dressed("flesh"), run_flesh, lambda ch: ch.flesh is not None),
    ("moves", ("bake", "hair", "flesh"), ("moves",), check_not_dressed("moves"), run_moves, lambda ch: True),
    ("strand", ("hair", "moves"), ("hair",), check_strand, run_strand, hair_has_chain),
    ("garments", ("moves", "flesh", "strand"), ("outfit",), check_garments, run_garments, lambda ch: bool(ch.outfit)),
    ("export", ("moves", "garments", "strand"), ("export", "moves"), check_export, run_export, lambda ch: True),
    ("review", ("export",), ("review",), check_review, run_review, lambda ch: ch.review.enabled),
]
ORDER = [s[0] for s in STAGES]
