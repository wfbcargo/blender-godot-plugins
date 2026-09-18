"""The wardrobe spec: one custom property, `wardrobe`, on the garment object.

glTF carries object custom properties as node extras (the exporter must be told
`export_extras`), and Godot's importer stores them as `node.get_meta("extras")["wardrobe"]`.

    {
      "schema": "wardrobe/1",
      "garment": "Shirt", "kind": "shirt", "layer": 2,
      "body": {"name": "Figure", "vertex_count": 17112, "rig": "Figure_metarig"},
      "hide": {"space": "gltf_mesh", "count": 6000, "positions_f32": "<base64 xyz float32 LE>",
               "tolerance_m": 0.0005},
      "edge": {... the same, covered skin left drawn ...},
      "hem":  {"space": "gltf_armature", "fabric": "cotton_jersey", "share": 0.8,
               "bones": [{"name", "ring", "parent", "head", "tail", "inward_dir", "inward_m",
                          "max_offset_m", "frequency_hz", "damping_ratio", "response", "gravity_scale"}]},
      "fit":  {"ease": {...gap statistics...}, "cut": {...}}
    }

`layer` orders garments: 1 underwear, 2 shirts, 3 sweaters and vests, 4 jackets and coats.
"""

from __future__ import annotations

import json

from . import SCHEMA, cover, rigmap

PROP = "wardrobe"
LAYERS = {"underwear": 1, "shirt": 2, "sweater": 3, "vest": 3, "jacket": 4, "coat": 4}


def _plain(v):
    return v.to_dict() if hasattr(v, "to_dict") else dict(v)


def build(garment, body, cover_rep, hem_rep=None, ease_rep=None, kind="shirt", layer=None, layers=None):
    """`layers`: {inner garment object: cover.compute(this, inner)} - what this garment hides of
    the garments worn under it, carried as positions in each one's mesh space."""
    g = rigmap._obj(garment)
    b = rigmap._obj(body)
    s = {
        "schema": SCHEMA,
        "garment": g.name,
        "kind": kind,
        "layer": int(layer if layer is not None else LAYERS.get(kind, 2)),
        "body": {"name": b.name, "vertex_count": len(b.data.vertices), "rig": rigmap.rig_of(b).name},
        "hide": {"space": "gltf_mesh", "count": len(cover_rep["_hidden"]),
                 "positions_f32": cover.gltf_positions(b, cover_rep["_hidden"]), "tolerance_m": 0.0005},
        "edge": {"space": "gltf_mesh", "count": len(cover_rep["_edge"]),
                 "positions_f32": cover.gltf_positions(b, cover_rep["_edge"]), "tolerance_m": 0.0005},
        "cover": {k: v for k, v in cover_rep.items() if not k.startswith("_")},
        "fit": {"ease": ease_rep or {}, "cut": _plain(g.get("wardrobe_cut", {}))},
    }
    if hem_rep is not None:
        s["hem"] = hem_rep["block"]
    if layers:
        s["hide_layers"] = {}
        for inner, rep in layers.items():
            inner = rigmap._obj(inner)
            s["hide_layers"][inner.name] = {
                "space": "gltf_mesh", "count": len(rep["_hidden"]),
                "positions_f32": cover.gltf_positions(inner, rep["_hidden"]), "tolerance_m": 0.0005,
                "tris_hidden": rep["tris_hidden"]}
    return s


def write(garment, s):
    g = rigmap._obj(garment)
    # stored as JSON text round-tripped to plain types: IDProperty groups reject some floats
    g[PROP] = json.loads(json.dumps(s))
    return validate(s)


def read(garment):
    g = rigmap._obj(garment)
    v = g.get(PROP)
    return v.to_dict() if hasattr(v, "to_dict") else v


def validate(s):
    p = []
    for k in ("schema", "garment", "kind", "layer", "body", "hide"):
        if k not in s:
            p.append("missing " + k)
    if s.get("schema") != SCHEMA:
        p.append(f"schema is {s.get('schema')}, expected {SCHEMA}")
    for key in ("hide", "edge"):
        blk = s.get(key)
        if blk is None:
            continue
        if blk.get("space") != "gltf_mesh":
            p.append(f"{key}.space must be gltf_mesh")
        import base64
        n = len(base64.b64decode(blk.get("positions_f32", ""))) // 12
        if n != blk.get("count"):
            p.append(f"{key}: {n} positions for count {blk.get('count')}")
    for name, blk in s.get("hide_layers", {}).items():
        import base64 as _b
        if len(_b.b64decode(blk.get("positions_f32", ""))) // 12 != blk.get("count"):
            p.append(f"hide_layers.{name}: positions do not match count")
    cov = s.get("cover", {})
    # a skirt covers a thin band of hip above its hinge and every vertex of it is within the hem's edge
    # margin, so it hides nothing and that is right; covered skin that the margin does not explain is not
    if cov.get("covered", 0) > 0 and s.get("hide", {}).get("count", 0) == 0             and cov.get("edge", 0) < cov.get("covered", 0):
        p.append("the garment covers skin but hides none: its weights do not agree with the body's "
                 "(a non-bone vertex group taken for a weight?)")
    hem = s.get("hem")
    if hem is not None:
        if hem.get("space") != "gltf_armature":
            p.append("hem.space must be gltf_armature")
        for bone in hem.get("bones", []):
            for k in ("name", "parent", "head", "tail", "inward_dir", "inward_m", "max_offset_m",
                      "frequency_hz", "damping_ratio"):
                if k not in bone:
                    p.append(f"hem bone {bone.get('name', '?')} missing {k}")
    return p
