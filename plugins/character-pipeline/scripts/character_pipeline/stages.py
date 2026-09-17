"""The stages a character is built in, what each needs, and how it knows.

    body      humanform body and rig from the brief (or an object already in the file)
    bake      one skinned mesh: shape keys and helpers baked, skin material, eyes joined
    hair      a hair mesh skinned to the head role (optional)
    flesh     follow-through jiggle bones (optional)
    moves     rig-anything's move set - after flesh, before garments
    garments  wardrobe presets, cut from the fleshed skin (optional)
    export    the glb, .moves.json and garment glbs, and the .blend
    review    the review sheet: every clip as 8-frame strips of the dressed character (on unless the spec
              says `[review] enabled = false`)

Each stage names the stages it needs and checks the file itself before it runs, so a stage run out of
order refuses with the order rather than producing a wrong result. The orders below were each found
by breaking them on a real character:

- moves before garments: rig-anything measures how far the arms hang out from what is bound to the
  rig, and 8 mm of sports top at the armpits sent Belle's run arms up over her head;
- flesh before garments: a garment is cut from the skin and takes its weights, and cut first it
  carries no jiggle bones;
- bake before moves.
"""

from __future__ import annotations

import os

import bpy


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


def _rest(ch):
    rig = _obj(ch.rig)
    if rig.animation_data:
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.view_layer.update()


def run_hair(ch, ctx):
    from . import hair
    if ch.hair.kind != "shell_bun":
        raise RuntimeError(f"hair: no builder for kind {ch.hair.kind!r} (have: shell_bun)")
    return hair.shell_bun(ch, **ch.hair.params)


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
    return {k: e.get(k) for k in ("glb", "moves", "verified", "clips", "bones", "problems")}


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
    out = review.summary(r)
    out["meshes"] = meshes
    return out


# (name, needs, spec sections its hash covers, precondition check, run, applies to this spec)
STAGES = [
    ("body", (), ("character", "body"), lambda ch: None, run_body, lambda ch: True),
    ("bake", ("body",), ("character", "body"), check_bake, run_bake, lambda ch: True),
    ("hair", ("bake",), ("hair",), check_not_dressed("hair"), run_hair, lambda ch: ch.hair is not None),
    ("flesh", ("bake", "hair"), ("flesh",), check_not_dressed("flesh"), run_flesh, lambda ch: ch.flesh is not None),
    ("moves", ("bake", "hair", "flesh"), ("moves",), check_not_dressed("moves"), run_moves, lambda ch: True),
    ("garments", ("moves", "flesh"), ("outfit",), check_garments, run_garments, lambda ch: bool(ch.outfit)),
    ("export", ("moves", "garments"), ("export", "moves"), check_export, run_export, lambda ch: True),
    ("review", ("export",), ("review",), check_review, run_review, lambda ch: ch.review.enabled),
]
ORDER = [s[0] for s in STAGES]
