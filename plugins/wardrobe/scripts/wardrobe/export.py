"""Export a garment - its mesh, the rig it is skinned to, its spec - and prove the file carries it.

    m = export.garment("Shirt", r"C:/proj/assets/wardrobe/shirt.glb", colour=(0.2, 0.42, 0.75))
    print(export.summarize(m))

The garment ships with its own copy of the body's rig, hem bones included, and no animation:
in Godot `Wardrobe.equip` adds the bones the body lacks and moves the mesh onto the body's
skeleton. Godot binds a skin to bones by name, so the copy only has to agree on names.

Read back from the written file:
  - the garment node's extras hold the spec, unchanged and valid
  - every hem bone is a joint of the garment's skin, and its head is where the spec says
  - hidden positions count what the spec says (the Godot runtime matches them to the body)
  - no stray meshes (selection is per scene; `use_active_scene` keeps other scenes out)
"""

from __future__ import annotations

import base64
import json
import os
import struct

import bpy

from . import rigmap, spec

COMPONENT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != 0x46546C67:
        raise ValueError(f"{path} is not a GLB")
    off, doc, binary = 12, None, b""
    while off < len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            binary = chunk
        off += 8 + clen
    return doc, binary


def _material(garment, colour):
    g = rigmap._obj(garment)
    name = f"wd_{g.name}"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_backface_culling = False            # glTF doubleSided: the inside shows at the openings
    mat.diffuse_color = (*colour, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*colour, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.9
    g.data.materials.clear()
    g.data.materials.append(mat)
    return mat


def garment(name, filepath, colour=(0.2, 0.42, 0.75)):
    g = rigmap._obj(name)
    rig = rigmap.rig_of(g)
    s = spec.read(g)
    if s is None:
        return {"exported": False, "problems": [f"{g.name} has no wardrobe spec"]}
    problems = spec.validate(s)
    if problems:
        return {"exported": False, "problems": problems}
    _material(g, colour)
    filepath = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    vl = bpy.context.view_layer
    for o in (g, rig):
        if bpy.context.scene.objects.get(o.name) is None:
            bpy.context.scene.collection.objects.link(o)
    vl.update()
    prev_sel = [o for o in vl.objects if o.select_get()]
    prev_active = vl.objects.active
    for o in vl.objects:
        o.select_set(False)
    g.select_set(True)
    rig.select_set(True)
    vl.objects.active = rig
    ad = rig.animation_data
    prev_action = ad.action if ad else None
    if ad:
        ad.action = None
    # the rest pose is what gets bound; a posed rig would bake a pose into the binds
    prev_pose = rig.data.pose_position
    rig.data.pose_position = "REST"
    wanted = {"filepath": filepath, "export_format": "GLB", "use_selection": True, "use_active_scene": True,
              "export_yup": True, "export_apply": True, "export_animations": False, "export_extras": True,
              "export_cameras": False, "export_lights": False, "export_skins": True}
    props = {p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}
    try:
        bpy.ops.export_scene.gltf(**{k: v for k, v in wanted.items() if k in props})
    finally:
        rig.data.pose_position = prev_pose
        if ad:
            ad.action = prev_action
        for o in vl.objects:
            o.select_set(o in prev_sel)
        vl.objects.active = prev_active
    m = verify(filepath, g.name, s)
    m["exported"] = True
    return m


def _accessor(doc, binary, index):
    acc = doc["accessors"][index]
    view = doc["bufferViews"][acc["bufferView"]]
    fmt, size = COMPONENT[acc["componentType"]]
    width = WIDTH[acc["type"]]
    stride = view.get("byteStride", size * width)
    base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    scale = {5121: 255.0, 5123: 65535.0}.get(acc["componentType"], 1.0) if acc.get("normalized") else 1.0
    return [tuple(x / scale for x in struct.unpack_from("<" + fmt * width, binary, base + i * stride))
            for i in range(acc["count"])]


def verify(path, garment_name, expected=None):
    doc, binary = read_glb(path)
    problems = []
    nodes = doc.get("nodes", [])
    node = next((n for n in nodes if n.get("name") == garment_name and "mesh" in n), None)
    meshes = [n["name"] for n in nodes if "mesh" in n]
    if node is None:
        return {"file": path, "passed": False, "problems": [f"no mesh node {garment_name}"]}
    if meshes != [garment_name]:
        problems.append(f"meshes in file {meshes}, expected only {garment_name}")
    s = node.get("extras", {}).get(spec.PROP)
    if s is None:
        problems.append("the garment node carries no wardrobe extras - exported without export_extras?")
        return {"file": path, "passed": False, "problems": problems}
    problems += spec.validate(s)
    if expected is not None and json.dumps(s, sort_keys=True) != json.dumps(expected, sort_keys=True):
        problems.append("the spec in the file differs from the object's")
    skin = doc["skins"][node["skin"]] if "skin" in node else None
    joints = [nodes[j]["name"] for j in skin["joints"]] if skin else []
    if skin is None:
        problems.append("the garment is not skinned")
    # every vertex skinned, its weights summing to one (the exporter renormalises what it keeps,
    # so this catches unskinned vertices, not weights diluted before export)
    weight_sum_min = None
    for prim in doc["meshes"][node["mesh"]]["primitives"]:
        if "WEIGHTS_0" in prim["attributes"]:
            sums = [sum(w) for w in _accessor(doc, binary, prim["attributes"]["WEIGHTS_0"])]
            lo = min(sums) if sums else 0.0
            weight_sum_min = lo if weight_sum_min is None else min(weight_sum_min, lo)
    if weight_sum_min is None:
        problems.append("the garment mesh has no WEIGHTS_0")
    elif weight_sum_min < 0.98:
        problems.append(f"a vertex's skin weights sum to {weight_sum_min:.3f}, not 1")
    hem = s.get("hem", {})
    worst = 0.0
    for b in hem.get("bones", []):
        if b["name"] not in joints:
            problems.append(f"hem bone {b['name']} is not a joint of the skin")
    # heads: accumulate node transforms down to each hem bone (translations and rotations)
    if skin is not None and hem.get("bones"):
        parent = {}
        for i, n in enumerate(nodes):
            for c in n.get("children", []):
                parent[c] = i
        from mathutils import Matrix, Quaternion, Vector

        def world(i):
            n = nodes[i]
            t = Vector(n.get("translation", [0, 0, 0]))
            q = n.get("rotation", [0, 0, 0, 1])
            r = Quaternion((q[3], q[0], q[1], q[2]))
            sc = n.get("scale", [1, 1, 1])
            m = Matrix.LocRotScale(t, r, Vector(sc))
            return world(parent[i]) @ m if i in parent else m

        index = {nodes[j]["name"]: j for j in skin["joints"]}
        # the spec is in armature space: undo the armature node's own transform
        arm = _armature_node(nodes, parent, skin)
        root_inv = world(arm).inverted() if arm is not None else Matrix.Identity(4)
        for b in hem["bones"]:
            if b["name"] in index:
                head = root_inv @ world(index[b["name"]]).translation
                worst = max(worst, (head - Vector(b["head"])).length)
        if worst > 1e-3:
            problems.append(f"hem bone heads are {worst:.4f} m from the spec")
    return {"file": path, "size_bytes": os.path.getsize(path), "garment": garment_name, "joints": len(joints),
            "hem_bones": len(hem.get("bones", [])), "hem_head_error_m": round(worst, 6),
            "weight_sum_min": round(weight_sum_min or 0.0, 4), "hidden": s.get("hide", {}).get("count"), "edge": s.get("edge", {}).get("count"),
            "passed": not problems, "problems": problems}


def _armature_node(nodes, parent, skin):
    """The node holding the skeleton: the parent of the root joint, or None at the scene root."""
    j = skin["joints"][0]
    while j in parent and parent[j] in skin["joints"]:
        j = parent[j]
    return parent.get(j)


def summarize(m):
    if not m.get("exported", True) and "problems" in m and "file" not in m:
        return "not exported: " + "; ".join(m["problems"])
    head = f"{os.path.basename(m['file'])}: {'PASSED' if m['passed'] else 'FAILED'}"
    body = (f"  {m.get('garment')}: {m.get('joints')} joints, {m.get('hem_bones')} hem bones "
            f"(heads within {m.get('hem_head_error_m')} m), {m.get('hidden')} body verts hidden, "
            f"{m.get('edge')} edge, {m.get('size_bytes', 0) // 1024} KB")
    return "\n".join([head, body] + [f"  - {p}" for p in m.get("problems", [])])
