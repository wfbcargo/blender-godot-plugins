"""Volume library: jello, pudding, slime, clay, water balloons - bodies with an inside.

    r = volume.prepare("Jello")                  # classify, type, material, pins, spec
    r = volume.prepare("Blob", type="slime")     # or say what it is
    print(volume.summarize(r))

A volume is simulated in Godot by shape matching on a lattice (shape_match_body.gd): the
mesh is embedded in a few cells a side, every lattice node pulls toward where its
neighbourhood's best rigid fit says it should be, and the render mesh follows. So the
spec is small - what the material is and how big the lattice - and everything else is
measured at runtime.

What a material sets, and what it means in the world:

  frequency_hz      how fast it wobbles when held at its base and pushed: a jello cube a
                    few Hz (gelatin G' 2-10 kPa), clay near 10
  damping_ratio     of that wobble: 0.1 rings for seconds, 1 settles without overshoot
  squash            0 keeps its shape rigidly, 1 lets it squash and bulge while keeping
                    its volume
  global_stiffness  share of shape memory held by the whole body at once; low values let
                    parts sag independently (slime), high values keep a form (rubber)
  friction          0-1 at contacts; static below 5 cm/s
  plastic           yield (strain before it stays deformed), creep (1/s toward the held
                    shape), max (fraction of its size the rest shape may drift): clay
  resolution        lattice cells along the longest side; 3-4 for a demo prop, cost grows
                    roughly with its cube

Mass is the mesh's volume times the material's density. Mass changes how hard a volume
pushes on nothing - volumes are pushed by physics bodies and do not push back - but it
sets the size of a poke's effect.
"""

from __future__ import annotations

import bmesh
import bpy

from . import classify, registry, spec

VOLUME_ROUTES = ("shape_matching",)


def _mesh_volume(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    v = abs(bm.calc_volume(signed=True))
    bm.free()
    return v


def prepare(obj_name, type=None, material=None, cls=None, resolution=4, overrides=None, pins=None):
    """Recognise a volume, choose its material, write the spec (and `ft_pin` for a mounted one).

    `type` names what it is (a registry type); `material` overrides the type's material;
    `cls` overrides the class (loose_volume or mounted_volume); `pins` overrides the pinned
    vertices of a mounted volume; `overrides` changes shape_matching values."""
    obj = bpy.data.objects[obj_name]
    rec = classify.classify(obj_name, cls=cls)
    if "error" in rec:
        return rec
    report = {"object": obj_name, "recognition": rec, "warnings": list(rec["warnings"])}
    if rec["family"] != "volume":
        report["declined"] = f"{obj_name} is a {rec['family']} ({rec['class']}), not a volume"
        return report
    if rec["class"] == "flesh":
        report["declined"] = "a skinned body: its soft parts are flesh - use flesh.prepare"
        return report
    types = registry.types_for("volume")
    guessed_type = type is None
    kind = type or rec.get("type")
    if kind not in types:
        raise ValueError(f"unknown volume type {kind!r}; one of {sorted(types)} - or registry.define it")
    entry = types[kind]
    material = material or entry.get("material")
    mat = registry.material(material)
    if mat.get("route") == "none":
        report["declined"] = f"{kind} is {material}: recognised, and nothing moves"
        return report
    if rec["class"] not in entry["classes"] and cls is None:
        report["warnings"].append(f"{kind} is usually {'/'.join(entry['classes'])}, geometry read {rec['class']}")
    rec["type"] = kind
    rec["route"] = "shape_matching"
    if pins is not None:
        rec["pins"] = {"vertices": sorted(pins), "count": len(pins), "source": "caller"}
        rec["class"] = "mounted_volume" if pins else "loose_volume"
    if rec["class"] == "mounted_volume":
        spec.set_pin_group(obj, rec.get("pins", {}).get("vertices", []))
    vol = _mesh_volume(obj)
    params = dict(mat.get("shape_matching", {}))
    params.update(overrides or {})
    params["resolution"] = int(resolution)
    params["total_mass"] = round(max(vol * mat.get("density_kg_m3", 1000.0), 0.001), 4)
    s = spec.build(obj, rec, anchor="node" if rec["class"] == "mounted_volume" else None)
    s["type"] = kind
    s["material"] = {"preset": material, "density_kg_m3": mat.get("density_kg_m3")}
    s["shape_matching"] = params
    if guessed_type and rec.get("guessed") and "type" in rec["guessed"]:
        s["guessed"] = sorted(set(s["guessed"]) | {"type"})
    spec.write(obj, s)
    report.update({"spec": s, "type": kind, "material": material, "volume_m3": round(vol, 6),
                   "material_source": mat.get("source", "")})
    return report


def set_params(obj_name, **params):
    """Change shape_matching values in an object's spec - e.g. what verify_volume.gd's tune
    recommended: set_params("Jello", stiffness_gain=1.3)."""
    obj = bpy.data.objects[obj_name]
    s = spec.read(obj)
    if s is None or "shape_matching" not in s:
        raise ValueError(f"{obj_name} has no shape_matching spec - run volume.prepare first")
    allowed = {"frequency_hz", "damping_ratio", "squash", "global_stiffness", "friction", "resolution",
               "total_mass", "gravity_scale", "stiffness_gain", "cluster_radius", "substeps", "plastic"}
    bad = set(params) - allowed
    if bad:
        raise ValueError(f"not shape_matching parameters: {sorted(bad)}")
    s["shape_matching"].update(params)
    return spec.write(obj, s)


def summarize(r):
    if "error" in r:
        return "ERROR " + r["error"]
    lines = [classify.summarize(r["recognition"])]
    if "declined" in r:
        lines.append("DECLINED " + r["declined"])
        return "\n".join(lines)
    s = r["spec"]
    sm = s["shape_matching"]
    plastic = sm.get("plastic")
    lines.append(f"  {r['type']} of {r['material']}: {r['volume_m3']} m3, {sm['total_mass']} kg")
    lines.append(f"  godot: {sm['frequency_hz']} Hz, damping {sm['damping_ratio']}, squash {sm.get('squash')}, "
                 f"global {sm.get('global_stiffness')}, friction {sm.get('friction')}, lattice {sm['resolution']}"
                 + (f", plastic past {plastic['yield']} at {plastic['creep']}/s up to {plastic['max']}" if plastic else ""))
    if "pins" in s:
        lines.append(f"  pins: {s['pins']['count']} anchored to {s['pins']['anchor']}")
    if s.get("guessed"):
        lines.append("  GUESSED: " + ", ".join(s["guessed"]))
    for w in r["warnings"]:
        if w not in r["recognition"]["warnings"]:
            lines.append("  WARNING " + w)
    return "\n".join(lines)
