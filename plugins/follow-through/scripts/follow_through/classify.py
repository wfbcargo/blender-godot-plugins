"""Decide what kind of secondary motion a mesh has, and which library handles it.

Two levels, as in the field:

  family   the dimension of the thing that moves
             strand   1D - a rope, a tail, hair, a scarf thin enough to be a line
             shell    2D - a surface: cloth, a flag, a sail
             volume   3D - a body with an inside: jello, flesh, a belly
  class    within a family, how it hangs and what holds it

and a **route**: the runtime that will move it in Godot.

  soft_body      SoftBody3D - a real mass-spring surface (cloth today)
  spring_bones   SpringBoneSimulator3D on a bone chain (strands; not built yet)
  none           nothing should move

Geometry constrains, renders decide. `classify` states what the measures
support, how strongly, and which parts were guessed - a flag from nothing but
its name and a vertical face is `hanging_sheet` with its pins marked guessed. A
caller who has looked at the renders passes `cls=` to override, and the pins are
then recomputed for that class.
"""

from __future__ import annotations

import bpy

from . import measure

CLOTH_CLASSES = ("hanging_sheet", "draped_sheet", "draped_tube", "loose_sheet", "strap", "tensioned")
ROUTES = {
    "hanging_sheet": "soft_body",
    "draped_sheet": "soft_body",
    "draped_tube": "soft_body",
    "loose_sheet": "soft_body",
    "tensioned": "soft_body",
    "strap": "spring_bones",
    "solid_sheet": "none",
    "volume": "none",
    "not_cloth": "none",
}

# Thresholds, each argued from the sample bodies' measures (see SKILL.md).
THIN_SHELL = 0.05        # thickness / longest extent: a solidified blanket 0.007, a pole 0.02, a body 0.2+
ROD = 0.1                # mid extent / longest: a pole 0.02 - a rod is not a sheet however thin
STRIP = 5.0              # long / mid extent of an open sheet: a scarf 9.3, a pennant 2.25
HORIZONTAL = 0.35        # verticality below this: the sheet lies flat (tablecloth 0.0, a cape 0.8)
TOP_BAND = 0.75          # contact mean height fraction above this: held from above
EDGE_BAND = 0.02         # fraction of the height span counted as "the top edge"


def _loop_verts(m, which):
    loops = m["boundary_loops"]
    if not loops:
        return []
    loop = max(loops, key=lambda l: l["height"]) if which == "top" else loops[0]
    return list(loop["vertices"])


def _top_edge(obj, fraction=EDGE_BAND, boundary_only=True):
    """Vertices within `fraction` of the height span of the highest point (world z)."""
    mw = obj.matrix_world
    zs = {v.index: (mw @ v.co).z for v in obj.data.vertices}
    hi = max(zs.values())
    lo = min(zs.values())
    band = max((hi - lo) * fraction, 1e-4)
    picked = {i for i, z in zs.items() if z >= hi - band}
    if boundary_only:
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        boundary = {v.index for v in bm.verts if v.is_boundary}
        bm.free()
        picked &= boundary or picked
    return sorted(picked)


def _pins_for(obj, m, cls):
    """Which vertices hold the cloth up, and why. Returns (vertices, source, guessed)."""
    touching = {name: c for name, c in m["contacts"]["by_object"].items()}
    group = obj.vertex_groups.get("ft_pin")
    if group is not None:
        idx = sorted(v.index for v in obj.data.vertices
                     if any(g.group == group.index and g.weight >= 0.5 for g in v.groups))
        if idx:
            return idx, "vertex group ft_pin (painted)", False
    for mod in obj.modifiers:
        if mod.type == "CLOTH" and mod.settings.vertex_group_mass:
            g = obj.vertex_groups.get(mod.settings.vertex_group_mass)
            if g is not None:
                idx = sorted(v.index for v in obj.data.vertices
                             if any(x.group == g.index and x.weight >= 0.5 for x in v.groups))
                if idx:
                    return idx, f"existing cloth pin group {g.name}", False

    if cls == "loose_sheet":
        return [], "a loose sheet rests; nothing holds it", False

    if cls == "draped_tube":
        top = _loop_verts(m, "top")
        held = [n for n, c in touching.items() if set(c["vertices"]) & set(top)]
        src = f"upper boundary loop, touching {', '.join(held)}" if held else "upper boundary loop"
        return sorted(top), src, not held

    # Worn: a cape hangs from its whole top edge, not from the few vertices that
    # happen to touch a narrow back - on the test body those were 9 of an 11-vertex
    # shoulder line plus a second row, and the corners were left to fall.
    if cls == "draped_sheet":
        held = [n for n, c in touching.items() if c["mean_height_fraction"] >= 0.5]
        if held or m["skin"].get("armature"):
            on = ", ".join(held) if held else m["skin"]["armature"]
            return _top_edge(obj), f"top edge, worn on {on}", False

    # Held by something it touches: those vertices are the pins.
    above = [(n, c) for n, c in touching.items() if c["mean_height_fraction"] >= 0.25]
    if above and cls in ("hanging_sheet", "draped_sheet", "tensioned", "strap"):
        name, c = max(above, key=lambda nc: (nc[1]["mean_height_fraction"], nc[1]["count"]))
        verts = c["vertices"]
        # a body touching a cape's whole back is not all pin: keep the upper band of the contact
        if c["fraction_of_vertices"] > 0.3:
            mw = obj.matrix_world
            zs = {i: (mw @ obj.data.vertices[i].co).z for i in verts}
            hi = max(zs.values())
            span = m["bounds"]["max"][2] - m["bounds"]["min"][2]
            verts = [i for i, z in zs.items() if z >= hi - max(span * EDGE_BAND, 1e-4)]
        return sorted(verts), f"touching {name}", False

    return _top_edge(obj), "top edge (nothing touches it - guessed from gravity)", True


def classify(obj_name, cls=None, measures=None):
    """Recognise one object. `cls` overrides the class after looking at renders."""
    obj = bpy.data.objects.get(obj_name)
    m = measures or measure.analyze(obj_name)
    if "error" in m:
        return m
    evidence = []
    guessed = []
    hints = m["name_hints"]
    extents = m["extents_m"]
    longest = max(extents[0], 1e-9)
    mid_ratio = extents[1] / longest

    family = None
    auto = None
    confidence = 0.5

    if m["closed"]:
        tos = m["thickness_over_size"] or 1.0
        if mid_ratio < ROD:
            family, auto = "strand", "not_cloth"
            evidence.append(f"closed and rod-like (mid/long extent {mid_ratio:.3f} < {ROD}): a rigid "
                            "or strand body, not a sheet")
            confidence = 0.8
        elif tos < THIN_SHELL:
            family, auto = "shell", "solid_sheet"
            evidence.append(f"closed but thin: thickness {m['thickness_m']} m is "
                            f"{tos:.4f} of its size (< {THIN_SHELL}) - a sheet modelled with thickness")
            confidence = 0.85
        else:
            family, auto = "volume", "volume"
            evidence.append(f"closed with depth: thickness/size {tos:.3f}, compactness "
                            f"{m['compactness']} (sphere 0.094)")
            confidence = 0.85
    else:
        family = "shell"
        loops = m["boundary_loops"]
        evidence.append(f"open surface: {len(loops)} boundary loop(s), Euler characteristic "
                        f"{m['euler_characteristic']}")
        skinned = m["skin"].get("armature") is not None
        touching = m["contacts"]["by_object"]
        held_above = {n: c for n, c in touching.items() if c["mean_height_fraction"] >= TOP_BAND}
        resting = {n: c for n, c in touching.items() if c["mean_height_fraction"] < TOP_BAND}

        if len(loops) >= 2 and m["euler_characteristic"] <= 0:
            auto = "draped_tube"
            evidence.append("two or more boundary loops round one surface: a tube")
            confidence = 0.8
        elif m["aspect_long_over_mid"] >= STRIP:
            auto = "strap"
            evidence.append(f"a strip: long/mid extent {m['aspect_long_over_mid']} >= {STRIP}")
            confidence = 0.75
        elif skinned:
            auto = "draped_sheet"
            evidence.append(f"skinned to {m['skin']['armature']}: worn on a body")
            confidence = 0.8
        elif m["verticality"] < HORIZONTAL:
            auto = "loose_sheet"
            evidence.append(f"lies flat (verticality {m['verticality']} < {HORIZONTAL})"
                            + (f", resting on {', '.join(resting)}" if resting else ""))
            confidence = 0.7 if resting else 0.55
        else:
            auto = "hanging_sheet"
            if held_above:
                evidence.append(f"hangs: vertical (verticality {m['verticality']}) and held near the "
                                f"top by {', '.join(held_above)}")
                confidence = 0.8
            elif touching:
                evidence.append(f"vertical (verticality {m['verticality']}), touching "
                                f"{', '.join(touching)} part-way down")
                confidence = 0.65
            else:
                evidence.append(f"vertical (verticality {m['verticality']}) and touching nothing")
                confidence = 0.5
                guessed.append("class")

    if hints:
        if auto in hints:
            evidence.append(f"name agrees: {m['object']} -> {hints[0]}")
            confidence = min(0.95, confidence + 0.1)
        elif family == "shell" and auto in CLOTH_CLASSES:
            evidence.append(f"name suggests {hints[0]} but the geometry reads {auto} - look at the renders")
            confidence = max(0.3, confidence - 0.2)
            guessed.append("class")

    chosen = cls or auto
    if cls and cls != auto:
        evidence.append(f"class set by caller: {cls} (geometry read {auto})")
        guessed = [g for g in guessed if g != "class"]
        if cls in CLOTH_CLASSES:
            family = "shell"

    result = {
        "object": m["object"],
        "family": family,
        "class": chosen,
        "auto_class": auto,
        "route": ROUTES.get(chosen, "none"),
        "confidence": round(confidence, 2),
        "evidence": evidence,
        "guessed": guessed,
        "touching": sorted(m["contacts"]["by_object"]),
        "warnings": [],
    }

    if chosen in CLOTH_CLASSES:
        verts, source, pin_guess = _pins_for(obj, m, chosen)
        result["pins"] = {"vertices": verts, "count": len(verts), "source": source}
        if pin_guess:
            result["guessed"].append("pins")
        if not verts and chosen != "loose_sheet":
            result["warnings"].append("no pins found: the cloth will fall. Paint vertex group "
                                      "ft_pin or pass pins explicitly")
    if chosen == "solid_sheet":
        result["warnings"].append("a sheet with modelled thickness cannot be simulated as one "
                                  "surface: simulate the single-layer sheet (remove or disable "
                                  "the Solidify) and thicken it in the material or at render")
    if m["blocking_modifiers"]:
        result["warnings"].append("modifiers that change the vertex set: "
                                  + ", ".join(m["blocking_modifiers"])
                                  + " - apply them before recognising pins, or the pins will "
                                  "name vertices the exported file does not have")
    if m["shape_keys"]:
        result["warnings"].append(f"{m['shape_keys']} shape keys: Godot's SoftBody3D refuses a mesh "
                                  "with blend shapes, the runtime strips them")
    if m["components"] > 1:
        result["warnings"].append(f"{m['components']} separate pieces: each simulates alone and "
                                  "pieces never stop each other passing through")
    return result


def scene(scene_name=None, only=None):
    """Classify every mesh in a scene. Returns {name: result}."""
    sc = bpy.data.scenes[scene_name] if scene_name else bpy.context.scene
    out = {}
    for o in sc.objects:
        if o.type != "MESH" or (only and o.name not in only):
            continue
        out[o.name] = classify(o.name)
    return out


def summarize(res):
    if "error" in res:
        return "ERROR " + res["error"]
    lines = [f"{res['object']}: {res['family']} / {res['class']} -> {res['route']} "
             f"(confidence {res['confidence']})"]
    for e in res["evidence"]:
        lines.append("  - " + e)
    if "pins" in res:
        lines.append(f"  pins: {res['pins']['count']} from {res['pins']['source']}")
    if res["guessed"]:
        lines.append("  GUESSED: " + ", ".join(res["guessed"]))
    for w in res["warnings"]:
        lines.append("  WARNING " + w)
    return "\n".join(lines)
