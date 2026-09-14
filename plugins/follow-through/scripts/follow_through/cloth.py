"""Cloth library: fabrics, the Blender preview, and the Godot SoftBody3D parameters.

    r = cloth.prepare("Banner", fabric="cotton")        # classify, pin, write the spec
    print(cloth.summarize(r))
    sim = cloth.preview("Banner", frames=90)            # Blender's own cloth sim, measured
    print(cloth.summarize_preview(sim))

Two solvers, two parameter sets, one fabric name
------------------------------------------------
Blender simulates cloth with an implicit mass-spring solver (Baraff and Witkin):
separate tension, compression, shear and bending springs, mass per vertex. Godot
4.7 under Jolt simulates it with substepped XPBD, and exposes one 0-1
`linear_stiffness` for stretch and shear, one total mass, and **no bending
stiffness at all** - its Jolt module builds the body with `EBendType::None`.
Neither parameter set converts into the other, so a fabric carries both:

  blender   the shipped Blender preset where one exists (silk, cotton, denim,
            leather, rubber - verbatim from scripts/presets/cloth), for the preview
  godot     SoftBody3D values, chosen for how the fabric *stretches* and *settles*,
            which is all Godot can express. Denim and cotton differ in Blender by
            their bending; in Godot they differ by mass, damping and little else.

Mass comes from areal density - the grams per square metre fabric is sold by -
times the sheet's area. Under Jolt mass does not change how far a pinned sheet
sags (measured: identical sag at 1 and 10 kg); it changes how hard wind and
collisions push it.
"""

from __future__ import annotations

import math
from collections import deque

import bmesh
import bpy

from . import classify, measure, spec

# areal_density_gsm: textile references (see references/cloth.md); leather and rubber
# are sheet-goods estimates.
#
# godot values were measured on the sample bodies in Godot 4.7.2 / Jolt, 8 s runs:
#   linear_stiffness  0.7-0.8 is the stable band. At 0.9 a pennant hanging from its
#                     top edge fluttered at 3.2 m/s after 8 s, at 1.0 at 7.6 m/s after
#                     5 s and rose above its pins; a curtain at 0.95, precision 30, hit 17. Below
#                     0.5 stretch grows (banner max edge 1.42 at 0.3). With no bend
#                     constraints a near-rigid sheet has nowhere to put its energy.
#   damping           a decay rate per second, not a 0-1 fraction: a free sheet given
#                     2 m/s kept 35% of it per second at 1.0 and stopped within 2 s
#                     at 3.0; values above 1 are accepted and work. It is the air:
#                     it bleeds every velocity, so falling cloth tops out at g / c
#                     (9.8 m/s at 1.0, 4.9 at 2.0). Godot's default 0.01 never settles
#                     a swing - a cape's hem still moved 0.54 m/s after 8 s - and 0.3
#                     left a scarf at 3 m/s six seconds after its anchor stopped.
#                     Real fabric loses most of a swing in about a second: 0.6 for
#                     silk that floats, up to 2 for leather that drops dead.
#                     (drag_coefficient is passed through; its effect under Jolt was
#                     not measured.)
#   precision         ceil(hops / 2) held stretch p95 at or under 1.03 on every sample;
#                     verify_cloth.gd doubles it until stretch passes.
FABRICS = {
    "silk": {
        "areal_density_gsm": 70,
        "blender": {"quality": 5, "mass": 0.15, "tension_stiffness": 5, "compression_stiffness": 5,
                    "shear_stiffness": 5, "bending_stiffness": 0.05, "tension_damping": 0,
                    "compression_damping": 0, "shear_damping": 0, "air_damping": 1},
        "godot": {"linear_stiffness": 0.7, "damping_coefficient": 0.6, "drag_coefficient": 0.02},
        "source": "Blender preset Silk",
    },
    "cotton": {
        "areal_density_gsm": 140,
        "blender": {"quality": 5, "mass": 0.3, "tension_stiffness": 15, "compression_stiffness": 15,
                    "shear_stiffness": 15, "bending_stiffness": 0.5, "tension_damping": 5,
                    "compression_damping": 5, "shear_damping": 5, "air_damping": 1},
        "godot": {"linear_stiffness": 0.75, "damping_coefficient": 1.0, "drag_coefficient": 0.01},
        "source": "Blender preset Cotton",
    },
    "wool": {
        "areal_density_gsm": 300,
        "blender": {"quality": 8, "mass": 0.6, "tension_stiffness": 25, "compression_stiffness": 25,
                    "shear_stiffness": 25, "bending_stiffness": 3, "tension_damping": 15,
                    "compression_damping": 15, "shear_damping": 15, "air_damping": 1},
        "godot": {"linear_stiffness": 0.75, "damping_coefficient": 1.2, "drag_coefficient": 0.01},
        "source": "interpolated between Blender Cotton and Denim - no shipped preset",
    },
    "denim": {
        "areal_density_gsm": 450,
        "blender": {"quality": 12, "mass": 1.0, "tension_stiffness": 40, "compression_stiffness": 40,
                    "shear_stiffness": 40, "bending_stiffness": 10, "tension_damping": 25,
                    "compression_damping": 25, "shear_damping": 25, "air_damping": 1},
        "godot": {"linear_stiffness": 0.8, "damping_coefficient": 1.5, "drag_coefficient": 0.005},
        "source": "Blender preset Denim",
    },
    "canvas": {
        "areal_density_gsm": 300,
        "blender": {"quality": 12, "mass": 0.8, "tension_stiffness": 60, "compression_stiffness": 60,
                    "shear_stiffness": 60, "bending_stiffness": 20, "tension_damping": 25,
                    "compression_damping": 25, "shear_damping": 25, "air_damping": 1},
        "godot": {"linear_stiffness": 0.8, "damping_coefficient": 1.5, "drag_coefficient": 0.005},
        "source": "interpolated between Blender Denim and Leather - no shipped preset",
    },
    "leather": {
        "areal_density_gsm": 900,
        "blender": {"quality": 15, "mass": 0.4, "tension_stiffness": 80, "compression_stiffness": 80,
                    "shear_stiffness": 80, "bending_stiffness": 150, "tension_damping": 25,
                    "compression_damping": 25, "shear_damping": 25, "air_damping": 1},
        "godot": {"linear_stiffness": 0.8, "damping_coefficient": 2.0, "drag_coefficient": 0.0},
        "source": "Blender preset Leather",
    },
    "rubber": {
        "areal_density_gsm": 1000,
        "blender": {"quality": 7, "mass": 3.0, "tension_stiffness": 15, "compression_stiffness": 15,
                    "shear_stiffness": 15, "bending_stiffness": 25, "tension_damping": 25,
                    "compression_damping": 25, "shear_damping": 25, "air_damping": 1},
        "godot": {"linear_stiffness": 0.35, "damping_coefficient": 1.0, "drag_coefficient": 0.0},
        "source": "Blender preset Rubber",
    },
}

# which fabric a class gets when the caller names none
DEFAULT_FABRIC = {"hanging_sheet": "cotton", "draped_sheet": "wool", "draped_tube": "cotton",
                  "loose_sheet": "cotton", "strap": "silk", "tensioned": "canvas"}

MODIFIER = "FollowThrough Cloth"


def hops_from_pins(obj, pins):
    """Largest number of edges between any vertex and its nearest pin.

    Tension travels about one edge per constraint pass, so a hem 24 edges below
    its pins needs more passes per tick than a pennant 9 edges long - or it
    stretches under its own weight. With no pins, the sheet's edge diameter / 2."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    try:
        seeds = list(pins) if pins else [0]
        dist = {i: 0 for i in seeds}
        q = deque(seeds)
        while q:
            i = q.popleft()
            for e in bm.verts[i].link_edges:
                j = e.other_vert(bm.verts[i]).index
                if j not in dist:
                    dist[j] = dist[i] + 1
                    q.append(j)
        far = max(dist.values()) if dist else 0
        return far if pins else max(1, far // 2)
    finally:
        bm.free()


def godot_params(obj, recognition, fabric):
    fab = FABRICS[fabric]
    area = sum(p.area for p in obj.data.polygons) * _area_scale(obj)
    pins = recognition.get("pins", {}).get("vertices", [])
    hops = hops_from_pins(obj, pins)
    params = dict(fab["godot"])
    params["total_mass"] = round(max(fab["areal_density_gsm"] / 1000.0 * area, 0.001), 4)
    # starting point only: verify_cloth.gd measures stretch and raises it if needed
    params["simulation_precision"] = int(min(40, max(5, math.ceil(hops / 2))))
    params["shrinking_factor"] = 0.0
    params["pressure_coefficient"] = 0.0
    return params, {"area_m2": round(area, 4), "hops_from_pins": hops}


def _area_scale(obj):
    s = obj.matrix_world.to_scale()
    return abs(s.x * s.y * s.z) ** (2.0 / 3.0)


def prepare(obj_name, fabric=None, cls=None, pins=None, anchor=None):
    """Recognise, choose a fabric, write `ft_pin` and the spec. Returns a report.

    `cls` overrides the class (after looking at renders), `pins` overrides the
    pinned vertex indices, `anchor` overrides what pins follow."""
    obj = bpy.data.objects[obj_name]
    rec = classify.classify(obj_name, cls=cls)
    if "error" in rec:
        return rec
    report = {"object": obj_name, "recognition": rec, "warnings": list(rec["warnings"])}
    if rec["class"] not in classify.CLOTH_CLASSES:
        report["declined"] = (f"{rec['class']} is not cloth this library simulates "
                              f"(family {rec['family']}, route {rec['route']})")
        return report
    if rec["route"] != "soft_body":
        report["warnings"].append(f"{rec['class']} routes to {rec['route']}, which follow-through "
                                  "does not build yet - writing a soft_body spec instead")
        rec["route"] = "soft_body"
    if pins is not None:
        rec["pins"] = {"vertices": sorted(pins), "count": len(pins), "source": "caller"}
        rec["guessed"] = [g for g in rec["guessed"] if g != "pins"]
    guessed_fabric = fabric is None
    fabric = fabric or DEFAULT_FABRIC[rec["class"]]
    if fabric not in FABRICS:
        raise ValueError(f"unknown fabric {fabric!r}; one of {sorted(FABRICS)}")
    params, info = godot_params(obj, rec, fabric)
    spec.set_pin_group(obj, rec["pins"]["vertices"])
    s = spec.build(obj, rec,
                   fabric={"preset": fabric, "areal_density_gsm": FABRICS[fabric]["areal_density_gsm"]},
                   soft_body=params, anchor=anchor)
    if guessed_fabric:
        s["guessed"].append("fabric")
    spec.write(obj, s)
    report.update({"spec": s, "fabric": fabric, "fabric_source": FABRICS[fabric]["source"], **info})
    return report


def set_params(obj_name, **soft_body):
    """Change Godot SoftBody3D values in an object's spec, e.g. what verify_cloth.gd's
    tune=true recommended: set_params("Curtain", simulation_precision=24)."""
    obj = bpy.data.objects[obj_name]
    s = spec.read(obj)
    if s is None or "soft_body" not in s:
        raise ValueError(f"{obj_name} has no soft_body spec - run cloth.prepare first")
    unknown = set(soft_body) - {"total_mass", "linear_stiffness", "simulation_precision",
                                "damping_coefficient", "drag_coefficient", "shrinking_factor",
                                "pressure_coefficient"}
    if unknown:
        raise ValueError(f"not SoftBody3D properties: {sorted(unknown)}")
    s["soft_body"].update(soft_body)
    if "simulation_precision" in soft_body:
        s["soft_body"]["simulation_precision"] = int(soft_body["simulation_precision"])
    return spec.write(obj, s)


def apply_blender(obj_name):
    """Add or refresh a Cloth modifier from the spec, for previewing in Blender.

    Pins use the same `ft_pin` group the spec was written from. The modifier is
    only a preview: `export` turns it off while writing the file, because the
    glTF exporter evaluates modifiers and would bake the current frame's drape
    into the mesh."""
    obj = bpy.data.objects[obj_name]
    s = spec.read(obj)
    if s is None or s.get("route") != "soft_body":
        raise ValueError(f"{obj_name} has no soft_body spec - run cloth.prepare first")
    mod = obj.modifiers.get(MODIFIER) or obj.modifiers.new(MODIFIER, "CLOTH")
    fab = FABRICS[s["fabric"]["preset"]] if s["fabric"]["preset"] in FABRICS else FABRICS["cotton"]
    cs = mod.settings
    for k, v in fab["blender"].items():
        setattr(cs, k, v)
    cs.vertex_group_mass = spec.PIN_GROUP if s["pins"]["count"] else ""
    mod.collision_settings.use_collision = True
    return mod


def preview(obj_name, frames=90, start=1):
    """Run Blender's cloth sim on the object and measure it.

    Steps the object's own scene frame by frame from `start`, reads the evaluated
    mesh, and restores the frame. Reports how much the sheet stretched (Blender's
    springs can stretch too), how far pins drifted, where it hung and whether it
    settled. These are the reference numbers a Godot run is compared with."""
    obj = bpy.data.objects[obj_name]
    s = spec.read(obj)
    mod = apply_blender(obj_name)
    scene = obj.users_scene[0]
    prev = scene.frame_current
    mod.point_cache.frame_start = start
    mod.point_cache.frame_end = start + frames
    pins = spec.pin_vertices(obj)
    me = obj.data
    rest_edges = [(e.vertices[0], e.vertices[1]) for e in me.edges]
    rest_len = [(me.vertices[a].co - me.vertices[b].co).length for a, b in rest_edges]
    mw = obj.matrix_world
    rest_pins = {i: mw @ me.vertices[i].co for i in pins}
    history = []
    try:
        for f in range(start, start + frames + 1):
            scene.frame_set(f)
            dg = scene.view_layers[0].depsgraph
            ev = obj.evaluated_get(dg)
            m2 = ev.to_mesh()
            pts = [mw @ v.co for v in m2.vertices]
            ev.to_mesh_clear()
            history.append(pts)
    finally:
        scene.frame_set(prev)
    last = history[-1]
    stretch = sorted((last[a] - last[b]).length / max(r, 1e-9) for (a, b), r in zip(rest_edges, rest_len))
    drift = max(((last[i] - p).length for i, p in rest_pins.items()), default=0.0)
    speeds = []
    for a, b in zip(history[-11:], history[-10:]):
        speeds.append(max((pb - pa).length for pa, pb in zip(a, b)) * scene.render.fps)
    return {
        "object": obj_name,
        "fabric": s["fabric"]["preset"],
        "frames": frames,
        "stretch_max": round(stretch[-1], 4),
        "stretch_p95": round(stretch[int(len(stretch) * 0.95)], 4),
        "pin_drift_m": round(drift, 5),
        "lowest_z": round(min(p.z for p in last), 4),
        "rest_lowest_z": round(min((mw @ v.co).z for v in me.vertices), 4),
        "max_point_speed_last_10_frames_mps": round(max(speeds), 4),
    }


def summarize(r):
    if "error" in r:
        return "ERROR " + r["error"]
    lines = [classify.summarize(r["recognition"])]
    if "declined" in r:
        lines.append("DECLINED " + r["declined"])
        return "\n".join(lines)
    s = r["spec"]
    sb = s["soft_body"]
    lines.append(f"  fabric {r['fabric']} ({r['fabric_source']}), area {r['area_m2']} m2, "
                 f"{r['hops_from_pins']} edges from pins to the farthest point")
    lines.append(f"  godot: mass {sb['total_mass']} kg, stiffness {sb['linear_stiffness']}, "
                 f"precision {sb['simulation_precision']}, damping {sb['damping_coefficient']}")
    lines.append(f"  pins: {s['pins']['count']} anchored to {s['pins']['anchor']}"
                 + (f" ({', '.join(sorted(set(s['pins']['bones'])))})" if s['pins'].get('bones') else ""))
    if s["guessed"]:
        lines.append("  GUESSED: " + ", ".join(s["guessed"]))
    for w in r["warnings"]:
        if w not in r["recognition"]["warnings"]:
            lines.append("  WARNING " + w)
    return "\n".join(lines)


def summarize_preview(p):
    return (f"{p['object']} ({p['fabric']}), {p['frames']} frames in Blender: stretch max "
            f"{p['stretch_max']} p95 {p['stretch_p95']}, pin drift {p['pin_drift_m']} m, lowest "
            f"z {p['lowest_z']} (rest {p['rest_lowest_z']}), still moving at "
            f"{p['max_point_speed_last_10_frames_mps']} m/s")
