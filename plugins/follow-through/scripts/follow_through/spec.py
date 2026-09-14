"""The follow-through spec: what is written onto a Blender object for Godot to read.

One custom property, `follow_through`, a dict matching
`schema/follow-through.schema.json`. The glTF exporter writes object custom
properties as node extras when `export_extras=True`, and Godot 4.7 imports them
as `node.get_meta("extras")`. Verified end to end: nested dicts survive, integers
arrive as floats.

Two Blender things are the editable source, and the spec is regenerated from them:

  vertex group `ft_pin`    which vertices are held (weight >= 0.5). Paint it to
                           change the pins, then `sync(obj)`.
  `follow_through`         everything else; edit through `cloth.prepare(...)` or
                           by hand, then `validate`.

Why pins are positions, not indices: Godot's editor importer reorders vertices
(5 of 182 kept their index on a test banner) and UV seams split one Blender
vertex into two. A position names the same point in both programs.
"""

from __future__ import annotations

import bmesh
import bpy

from . import SCHEMA, VERSION

PROP = "follow_through"
PIN_GROUP = "ft_pin"

FAMILIES = ("strand", "shell", "volume")
CLASSES = ("hanging_sheet", "draped_sheet", "draped_tube", "loose_sheet", "strap", "tensioned",
           "solid_sheet", "volume", "not_cloth")
ROUTES = ("soft_body", "spring_bones", "none")
ANCHORS = ("node", "bone", "none")
PRESETS = ("silk", "cotton", "wool", "denim", "canvas", "leather", "rubber", "custom")


def to_gltf(co):
    """Blender mesh-local (x, y, z), Z up, to glTF mesh-local (x, z, -y), Y up."""
    return (co[0], co[2], -co[1])


def pin_vertices(obj, threshold=0.5):
    g = obj.vertex_groups.get(PIN_GROUP)
    if g is None:
        return []
    return sorted(v.index for v in obj.data.vertices
                  if any(x.group == g.index and x.weight >= threshold for x in v.groups))


def set_pin_group(obj, vertices):
    """Replace `ft_pin` with exactly `vertices` at weight 1."""
    g = obj.vertex_groups.get(PIN_GROUP)
    if g is not None:
        obj.vertex_groups.remove(g)
    g = obj.vertex_groups.new(name=PIN_GROUP)
    if vertices:
        g.add(list(vertices), 1.0, "REPLACE")
    return g


def _strongest_bone(obj, vid, bone_names):
    best = None
    for x in obj.data.vertices[vid].groups:
        name = obj.vertex_groups[x.group].name
        if name in bone_names and x.weight > 0 and (best is None or x.weight > best[1]):
            best = (name, x.weight)
    return best[0] if best else None


def _armature(obj):
    for m in obj.modifiers:
        if m.type == "ARMATURE" and m.object is not None:
            return m.object
    return None


def pins_block(obj, vertices, anchor):
    """The `pins` dict for these vertices."""
    me = obj.data
    # A skinned mesh is written with its world transform baked into the vertices
    # (glTF ignores a skinned node's own transform, so the exporter moves the data
    # instead): a cape on a rig at x=11 was written at x=10.75, not -0.25, and
    # every mesh-local pin missed. An unskinned mesh is written mesh-local.
    basis = obj.matrix_world if _armature(obj) is not None else None
    positions = []
    for i in vertices:
        co = me.vertices[i].co if basis is None else basis @ me.vertices[i].co
        positions.extend(round(c, 6) for c in to_gltf(co))
    # half the shortest edge touching a pin, capped at 0.1 mm: never reaches a neighbour
    tol = 1e-4
    if vertices:
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        shortest = min((e.calc_length() for i in vertices for e in bm.verts[i].link_edges),
                       default=1.0)
        bm.free()
        tol = min(1e-4, shortest * 0.5)
    block = {"count": len(vertices), "space": "gltf_mesh", "positions": positions,
             "tolerance": tol, "anchor": anchor if vertices else "none"}
    if block["anchor"] == "bone":
        arm = _armature(obj)
        names = {b.name for b in arm.data.bones} if arm else set()
        bones = [_strongest_bone(obj, i, names) for i in vertices]
        if None in bones:
            missing = sum(1 for b in bones if b is None)
            raise ValueError(f"{missing} pinned vertices carry no bone weight - anchor=bone needs "
                             "every pin skinned; use anchor=node or weight them")
        block["bones"] = bones
    return block


def build(obj, recognition, fabric=None, soft_body=None, anchor=None):
    """Assemble a spec dict from a classify() result and a library's parameters."""
    pins = recognition.get("pins", {}).get("vertices", [])
    if anchor is None:
        if not pins:
            anchor = "none"
        elif recognition["class"] in ("draped_sheet", "draped_tube") and _armature(obj):
            anchor = "bone"
        else:
            anchor = "node"
    spec = {
        "schema": SCHEMA,
        "family": recognition["family"],
        "class": recognition["class"],
        "route": recognition["route"],
        "confidence": recognition.get("confidence", 0.5),
        "guessed": list(recognition.get("guessed", [])),
        "source": {"tool": "follow-through", "version": VERSION, "object": obj.name,
                   "vertices": len(obj.data.vertices), "pin_group": PIN_GROUP},
    }
    if fabric is not None:
        spec["fabric"] = fabric
    if soft_body is not None:
        spec["soft_body"] = soft_body
    if recognition["class"] in CLASSES[:6]:
        spec["pins"] = pins_block(obj, pins, anchor)
        spec["collision"] = {"layer": 1, "mask": 1,
                             "touching": sorted(recognition.get("touching", []))}
    return spec


def validate(spec):
    """Check a spec against the schema's rules. Returns a list of problems (empty = valid).

    Blender ships no jsonschema, so this restates the schema's constraints; the
    JSON file stays the contract and the Godot reader checks the same things."""
    p = []

    def need(d, keys, where):
        for k in keys:
            if k not in d:
                p.append(f"{where}: missing {k}")

    if not isinstance(spec, dict):
        return ["spec is not a dict"]
    need(spec, ("schema", "family", "class", "route", "source"), "spec")
    if spec.get("schema") != SCHEMA:
        p.append(f"schema is {spec.get('schema')!r}, expected {SCHEMA!r}")
    if spec.get("family") not in FAMILIES:
        p.append(f"family {spec.get('family')!r} not in {FAMILIES}")
    if spec.get("class") not in CLASSES:
        p.append(f"class {spec.get('class')!r} not in {CLASSES}")
    if spec.get("route") not in ROUTES:
        p.append(f"route {spec.get('route')!r} not in {ROUTES}")
    if spec.get("route") == "soft_body":
        need(spec, ("fabric", "soft_body", "pins"), "soft_body route")
        sb = spec.get("soft_body", {})
        need(sb, ("total_mass", "linear_stiffness", "simulation_precision", "damping_coefficient"),
             "soft_body")
        if sb.get("total_mass", 1) <= 0:
            p.append("soft_body.total_mass must be > 0")
        if not 0 <= sb.get("linear_stiffness", 0.5) <= 1:
            p.append("soft_body.linear_stiffness must be in [0, 1]")
        if sb.get("simulation_precision", 5) < 1 or float(sb.get("simulation_precision", 5)) % 1:
            p.append("soft_body.simulation_precision must be a whole number >= 1")
        fab = spec.get("fabric", {})
        if fab.get("preset") not in PRESETS:
            p.append(f"fabric.preset {fab.get('preset')!r} not in {PRESETS}")
        if fab.get("areal_density_gsm", 1) <= 0:
            p.append("fabric.areal_density_gsm must be > 0")
    pins = spec.get("pins")
    if pins is not None:
        need(pins, ("count", "space", "positions", "tolerance", "anchor"), "pins")
        if pins.get("space") != "gltf_mesh":
            p.append("pins.space must be gltf_mesh")
        if len(pins.get("positions", [])) != 3 * pins.get("count", 0):
            p.append(f"pins.positions has {len(pins.get('positions', []))} numbers for "
                     f"{pins.get('count')} pins")
        if pins.get("anchor") not in ANCHORS:
            p.append(f"pins.anchor {pins.get('anchor')!r} not in {ANCHORS}")
        if pins.get("anchor") == "bone" and len(pins.get("bones", [])) != pins.get("count"):
            p.append("pins.anchor=bone needs one bone name per pin")
        if spec.get("class") not in ("loose_sheet",) and spec.get("route") == "soft_body" \
                and pins.get("count", 0) == 0:
            p.append(f"a {spec.get('class')} with no pins falls to the ground")
    return p


def _plain(v):
    """IDProperty values back to plain Python."""
    if hasattr(v, "to_dict"):
        return {k: _plain(x) for k, x in v.to_dict().items()}
    if hasattr(v, "to_list"):
        return [_plain(x) for x in v.to_list()]
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


def write(obj, spec):
    problems = validate(spec)
    if problems:
        raise ValueError("invalid follow-through spec:\n  " + "\n  ".join(problems))
    obj[PROP] = spec
    return spec


def read(obj):
    v = obj.get(PROP)
    return None if v is None else _plain(v)


def sync(obj):
    """Regenerate pin positions (and bones) from the `ft_pin` group. Call after painting
    the group, after editing the mesh, and always before export - `export` does."""
    spec = read(obj)
    if spec is None:
        raise ValueError(f"{obj.name} has no {PROP} spec")
    if "pins" not in spec:
        return spec
    verts = pin_vertices(obj)
    anchor = spec["pins"].get("anchor", "node")
    if anchor == "none" and verts:
        anchor = "bone" if _armature(obj) and spec["class"] in ("draped_sheet", "draped_tube") else "node"
    spec["pins"] = pins_block(obj, verts, anchor)
    spec["source"]["vertices"] = len(obj.data.vertices)
    spec["source"]["object"] = obj.name
    return write(obj, spec)
