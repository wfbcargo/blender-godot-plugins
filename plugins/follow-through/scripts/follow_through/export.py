"""Export objects with their follow-through specs to glTF, and prove the file carries them.

    m = export.export(r"C:/proj/assets/cloth/banner.glb", ["Banner", "FlagPole"])
    print(export.summarize(m))

The exporter is given `export_extras=True` so each object's `follow_through`
property becomes node extras - the only channel verified to reach Godot intact
(vertex groups are never written, and Godot's importer drops custom `_`
attributes). Then the written file is read back and every spec is checked:

  - the node's extras hold the spec, unchanged
  - every pin position lands on at least one vertex of that node's mesh, within
    the spec's tolerance - so the Godot side will find it
  - how many vertices each pin landed on (2 = a UV seam split it; both halves are
    pinned in Godot, and Jolt welds exact duplicates anyway)

A spec whose pins name no vertex in the file blocks the export's verdict. That
is the failure a wrong coordinate convention, an applied modifier or a stale
spec produces, and in Godot it would look like cloth that simply falls.
"""

from __future__ import annotations

import json
import os
import struct

import bpy

from . import cloth, spec

COMPONENT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    magic, _version, _length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        raise ValueError(f"{path} is not a GLB")
    off = 12
    doc, binary = None, b""
    while off < len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            binary = chunk
        off += 8 + clen
    return doc, binary


def accessor(doc, binary, index):
    acc = doc["accessors"][index]
    view = doc["bufferViews"][acc["bufferView"]]
    fmt, size = COMPONENT[acc["componentType"]]
    width = WIDTH[acc["type"]]
    stride = view.get("byteStride", size * width)
    base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    out = []
    for i in range(acc["count"]):
        out.append(struct.unpack_from("<" + fmt * width, binary, base + i * stride))
    return out


def _check_node(doc, binary, node):
    s = node.get("extras", {}).get(spec.PROP)
    if s is None:
        return None
    res = {"node": node.get("name"), "class": s.get("class"), "route": s.get("route"),
           "problems": spec.validate(s), "_binary": (doc, binary)}
    pins = s.get("pins")
    if "mesh" not in node:
        res["problems"].append("node carries a spec but no mesh")
        res.pop("_binary", None)
        return res
    positions = []
    for prim in doc["meshes"][node["mesh"]]["primitives"]:
        positions.extend(accessor(doc, binary, prim["attributes"]["POSITION"]))
    res["gltf_vertices"] = len(positions)
    res["primitives"] = len(doc["meshes"][node["mesh"]]["primitives"])
    if res["primitives"] > 1 and s.get("route") in ("soft_body", "shape_matching"):
        res["problems"].append(f"{res['primitives']} primitives (one per material): the runtime "
                               "rebuilds a single surface - give the object one material")
    if s.get("route") == "jiggle_bones":
        _check_jiggle(doc, node, s, res)
    if pins and pins["count"]:
        tol = pins["tolerance"]
        flat = pins["positions"]
        # bucket vertices on a grid of tolerance-sized cells
        cell = max(tol * 4, 1e-6)
        grid = {}
        for i, p in enumerate(positions):
            grid.setdefault(tuple(int(c // cell) for c in p), []).append(i)
        hits = []
        for k in range(pins["count"]):
            q = flat[3 * k: 3 * k + 3]
            key = tuple(int(c // cell) for c in q)
            found = 0
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for i in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                            p = positions[i]
                            if sum((p[j] - q[j]) ** 2 for j in range(3)) <= tol * tol:
                                found += 1
            hits.append(found)
        missing = sum(1 for h in hits if h == 0)
        res["pins"] = pins["count"]
        res["pins_found"] = pins["count"] - missing
        res["pinned_vertices"] = sum(hits)
        res["seam_split_pins"] = sum(1 for h in hits if h > 1)
        if missing:
            res["problems"].append(f"{missing} of {pins['count']} pins land on no vertex in the file")
    res.pop("_binary", None)
    return res


def _node_matrices(doc):
    """World matrix of every glTF node, as 4x4 nested lists (column vectors)."""
    import numpy as np

    def local(n):
        if "matrix" in n:
            return np.array(n["matrix"], dtype=float).reshape(4, 4).T
        t = n.get("translation", [0, 0, 0])
        x, y, z, w = n.get("rotation", [0, 0, 0, 1])
        sx, sy, sz = n.get("scale", [1, 1, 1])
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        M = np.eye(4)
        M[:3, :3] = R * np.array([sx, sy, sz])
        M[:3, 3] = t
        return M

    nodes = doc.get("nodes", [])
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    world = {}

    def get(i):
        if i not in world:
            world[i] = local(nodes[i]) if i not in parent else get(parent[i]) @ local(nodes[i])
        return world[i]

    return {i: get(i) for i in range(len(nodes))}


def _check_jiggle(doc, node, s, res):
    """Every jiggle bone is a joint of this mesh's skin, and sits where the spec says.

    A joint's rest transform is the inverse of its inverse bind matrix (in the skinned
    mesh's bind space, which Blender's exporter makes world space); the spec's head is in
    armature space, so the armature node's world matrix carries it across."""
    import numpy as np
    regions = s["jiggle"]["regions"]
    res["jiggle_regions"] = len(regions)
    if "skin" not in node:
        res["problems"].append("a jiggle_bones spec on a mesh with no skin")
        return
    skin = doc["skins"][node["skin"]]
    names = {doc["nodes"][j].get("name"): k for k, j in enumerate(skin["joints"])}
    missing = [r["bone"] for r in regions if r["bone"] not in names]
    if missing:
        res["problems"].append(f"jiggle bones not in the skin: {missing} - export the rig with its new bones")
        return
    world = _node_matrices(doc)
    arm = next((i for i, n in enumerate(doc["nodes"]) if n.get("name") == s["jiggle"].get("armature")), None)
    A = world[arm] if arm is not None else np.eye(4)
    ibm = None
    if "inverseBindMatrices" in skin:
        _doc, binary = res.pop("_binary")
        ibm = accessor(doc, binary, skin["inverseBindMatrices"])
    worst = 0.0
    for r in regions:
        if ibm is None:
            break
        M = np.array(ibm[names[r["bone"]]], dtype=float).reshape(4, 4).T
        joint = np.linalg.inv(M)[:3, 3]
        head = (A @ np.array(list(r["head"]) + [1.0]))[:3]
        worst = max(worst, float(np.linalg.norm(joint - head)))
    res["jiggle_head_error_m"] = round(worst, 5)
    if worst > 0.01:
        res["problems"].append(f"jiggle bone heads are {worst:.3f} m from where the spec puts them")


def verify(path, expect_meshes=None):
    """Read an exported .glb back and check every follow-through spec in it - for files
    written by another exporter, such as rig-anything's export of a rigged, animated body."""
    doc, binary = read_glb(path)
    checks = []
    for n in doc.get("nodes", []):
        c = _check_node(doc, binary, n)
        if c:
            checks.append(c)
    meshes = sorted(n.get("name") for n in doc.get("nodes", []) if "mesh" in n)
    result = {"path": path, "specs": checks, "missing_specs": [], "meshes": meshes,
              "passed": bool(checks) and all(not c["problems"] for c in checks)}
    if expect_meshes is not None:
        extra = sorted(set(meshes) - set(expect_meshes))
        result["unexpected_meshes"] = extra
        if extra:
            result["passed"] = False
    return result


def export(path, objects, include_children=False, verify=True):
    """Export `objects` (names) to a .glb with extras, cloth previews disabled, and verify.

    Every cloth object's spec is re-synced from its `ft_pin` group first, so a
    pin group painted after `prepare` is what ships."""
    objs = [bpy.data.objects[n] for n in objects]
    scene = objs[0].users_scene[0]
    for o in objs:
        if spec.read(o) is not None:
            spec.sync(o)
    win = bpy.context.window
    prev_scene = win.scene
    prev_sel = [o.name for o in bpy.context.selected_objects]
    prev_active = bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None
    disabled = []
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    try:
        win.scene = scene
        for o in scene.objects:
            o.select_set(False)
        for o in objs:
            o.select_set(True)
            if include_children:
                for c in o.children_recursive:
                    c.select_set(True)
            for m in o.modifiers:
                if m.type == "CLOTH" and m.show_viewport:
                    m.show_viewport = False
                    disabled.append((o.name, m.name))
        bpy.ops.export_scene.gltf(
            filepath=path, export_format="GLB", use_selection=True, use_active_scene=True,
            export_extras=True, export_apply=False, export_animations=False,
            export_yup=True, export_skins=True, export_morph=False,
            export_lights=False, export_cameras=False)
    finally:
        for oname, mname in disabled:
            bpy.data.objects[oname].modifiers[mname].show_viewport = True
        # leave nothing selected in the export scene: selection is per scene, and an exporter
        # run later from another scene without use_active_scene picks these up
        for o in scene.objects:
            o.select_set(False)
        win.scene = prev_scene
        for o in prev_scene.objects:
            o.select_set(o.name in prev_sel)
        if prev_active and prev_active in prev_scene.objects:
            bpy.context.view_layer.objects.active = prev_scene.objects[prev_active]

    manifest = {"path": path, "objects": objects, "cloth_previews_disabled": [m for _o, m in disabled]}
    if verify:
        doc, binary = read_glb(path)
        checks = [c for c in (_check_node(doc, binary, n) for n in doc.get("nodes", [])) if c]
        manifest["specs"] = checks
        manifest["expected_specs"] = sorted(o.name for o in objs if spec.read(o) is not None)
        written = sorted(c["node"] for c in checks)
        manifest["missing_specs"] = [n for n in manifest["expected_specs"] if n not in written]
        manifest["passed"] = not manifest["missing_specs"] and all(not c["problems"] for c in checks)
    return manifest


def summarize(m):
    lines = [f"{m['path']}: {'PASSED' if m.get('passed') else 'FAILED'}"]
    for c in m.get("specs", []):
        pin = (f", pins {c['pins_found']}/{c['pins']} found on {c['pinned_vertices']} vertices "
               f"({c['seam_split_pins']} split by seams)") if "pins" in c else ""
        jig = (f", {c['jiggle_regions']} jiggle bones in the skin, heads within {c['jiggle_head_error_m']} m"
               if "jiggle_head_error_m" in c else "")
        lines.append(f"  {c['node']}: {c['class']}, {c.get('gltf_vertices')} vertices in file{pin}{jig}")
        for p in c["problems"]:
            lines.append("    PROBLEM " + p)
    for n in m.get("missing_specs", []):
        lines.append(f"  PROBLEM {n} has a spec in Blender but none in the file")
    if m.get("unexpected_meshes"):
        lines.append(f"  PROBLEM meshes in the file nobody exported: {', '.join(m['unexpected_meshes'])}")
    return "\n".join(lines)
