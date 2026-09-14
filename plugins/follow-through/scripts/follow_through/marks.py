"""Mark zones in 2D, map them onto the 3D mesh.

Deciding *what* a bulge is - a breast, a belly, hips that are just wide - is easy to see
and hard to measure; deciding *exactly which vertices* and *how far out* is the other way
round. So the two are split. Claude looks at labelled renders and says where each zone is
in 2D; this module finds the vertices under those marks that the camera could see, merges
the views, and hands regions to `flesh`, which places the bones and paints the weights.

    sheet = marks.render("Bloater", r"C:/scratch/marks")          # views with a grid and numbered candidates
    # read the PNGs, then say what is where:
    zones = [
        {"type": "bloater_belly", "view": "front", "cells": "D7:H11"},
        {"type": "bloater_belly", "view": "right", "ellipse": ["F8", 3, 4]},
        {"type": "breast", "view": "front", "candidate": 2},
        {"type": "breast", "view": "front", "cells": ["E5", "F5", "E6"], "side": "R"},
    ]
    found = marks.regions("Bloater", zones, sheet)
    report = flesh.prepare("Bloater", regions=found["regions"])

A mark is one of:

  cells       "D7:H11" (a block), or a list of cells ["E5", "F5"]. Columns are letters
              from the left, rows are numbers from the top, as printed on the render.
  ellipse     [centre cell, half-width in cells, half-height in cells]; weights fall off
              from the centre, so an ellipse makes a softer edge than a block.
  candidate   the number printed on a geometric candidate - "that one is a breast".

Each mark belongs to one view. Marking the same zone in two views (front and side)
adds the vertices each view saw; a paired type with no `side` is split down the body's
midline into .L and .R. Only vertices facing the camera and unoccluded count, so a
front-view mark never selects the back.
"""

from __future__ import annotations

import json
import math
import os
import re

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

VIEWS = {
    "front": Vector((0.0, -1.0, 0.0)),
    "back": Vector((0.0, 1.0, 0.0)),
    "left": Vector((1.0, 0.0, 0.0)),        # the body's left side (+X), seen from outside
    "right": Vector((-1.0, 0.0, 0.0)),
    "front_left": Vector((0.7071, -0.7071, 0.0)),
    "front_right": Vector((-0.7071, -0.7071, 0.0)),
}
GRID = 16
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# ------------------------------------------------------------------ rendering

def _camera_frame(direction):
    """The view direction (from the body toward the camera). The screen axes are read back
    from the camera object after it is placed, so projection matches the render exactly."""
    return direction.normalized(), None, None


def render(obj_name, out_dir, views=("front", "right", "back", "left"), size=768, grid=GRID,
           candidates=True, heat=True, focus=None):
    """Render labelled views of `obj_name` for marking. Returns a sheet: the files, and the
    camera of every view (needed to map marks back), also saved as <object>_marks.json.

    With `heat`, the body is coloured by how far it stands out of its lean envelope
    (flesh.tissue); with `candidates`, each geometric region flesh.find_regions proposes is
    drawn as a number at its peak.

    `focus` frames part of the body so cells are finer: "torso" (hips to shoulders), or
    ([x, y, z], size_m). On a whole 1.8 m body a cell is 12 cm; a moob is 6.5 cm across,
    and a 2x2-cell mark over one put its bone 12.6 cm off where a 0.9-cell ellipse put it
    7.6 cm off."""
    from . import flesh
    obj = bpy.data.objects[obj_name]
    os.makedirs(out_dir, exist_ok=True)
    found = None
    if candidates or heat:
        try:
            found = flesh.find_regions(obj_name)
        except Exception as exc:      # a mesh with no rig can still be marked
            found = {"error": str(exc)}
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    centre = (lo + hi) / 2.0
    extent = max((hi - lo).x, (hi - lo).y, (hi - lo).z) * 1.1
    if focus == "torso" and found and "error" not in found:
        f = found["tissue"]["frame"]
        span = f["shoulder"] - f["hip"]
        centre = Vector((centre.x, centre.y, 0.5 * (f["hip"] + f["shoulder"])))
        extent = max(span * 2.2, max((hi - lo).y, 0.1) * 1.3)
    elif isinstance(focus, (list, tuple)) and len(focus) == 2:
        centre, extent = Vector(focus[0]), float(focus[1])

    colours_attr = None
    me = obj.data
    prev_active = me.color_attributes.active_color_name
    if heat and found and "error" not in found:
        t = found["tissue"]
        H = t["height"]
        k = np.clip(t["excess"] / (0.04 * H), 0.0, 1.0) * (t["relative"] > flesh.GROW_RELATIVE)
        cols = np.ones((len(me.vertices), 4))
        cols[:, :3] = 0.82
        cols[:, 1] -= 0.55 * k
        cols[:, 2] -= 0.55 * k
        colours_attr = me.color_attributes.new("ft_marks", "FLOAT_COLOR", "POINT")
        colours_attr.data.foreach_set("color", cols.ravel())
        me.color_attributes.active_color = colours_attr

    # Marks are mapped onto rest-pose vertices, so the renders must show the rest pose: a rig
    # left on frame 12 of a walk drew the bloater mid-stride while its vertices stood still.
    rig = flesh.armature_of(obj)
    prev_pose = rig.data.pose_position if rig is not None else None
    if rig is not None:
        rig.data.pose_position = "REST"
    scene = bpy.data.scenes.new("ft_marks_tmp")
    cam_data = bpy.data.cameras.new("ft_marks_cam")
    cam = bpy.data.objects.new("ft_marks_cam", cam_data)
    made = [cam]
    sheet = {"object": obj.name, "size": size, "grid": grid, "extent": extent,
             "centre": list(centre), "views": {}, "files": [], "candidates": []}
    if found and "error" not in found:
        for i, r in enumerate(found["regions"], start=1):
            sheet["candidates"].append({"number": i, "name": r["name"], "type": r["type"],
                                        "tail": [float(x) for x in r["tail"]]})
    try:
        scene.collection.objects.link(obj)
        scene.collection.objects.link(cam)
        scene.camera = cam
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.render.resolution_x = scene.render.resolution_y = size
        scene.render.film_transparent = False
        sh = scene.display.shading
        sh.light = "STUDIO"
        sh.color_type = "VERTEX" if colours_attr is not None else "OBJECT"
        sh.show_cavity = True
        sh.background_type = "VIEWPORT"
        sh.background_color = (1.0, 1.0, 1.0)
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = extent
        cam_data.clip_end = extent * 50
        for view in views:
            d, right, up = _camera_frame(VIEWS[view])
            cam.location = centre + d * extent * 5.0
            cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
            scene.view_layers[0].update()
            # the camera's own axes, so projection matches what was rendered exactly
            mw = cam.matrix_world
            right = (mw.to_3x3() @ Vector((1, 0, 0))).normalized()
            up = (mw.to_3x3() @ Vector((0, 1, 0))).normalized()
            overlay = _overlay(scene, centre, d, right, up, extent, grid, sheet["candidates"], view)
            made.extend(overlay)
            path = os.path.join(out_dir, f"{obj.name.replace('.', '_')}_marks_{view}.png")
            scene.render.filepath = path
            bpy.ops.render.render(write_still=True, scene=scene.name)
            for o in overlay:
                scene.collection.objects.unlink(o)
            sheet["views"][view] = {"direction": list(d), "right": list(right), "up": list(up)}
            sheet["files"].append(path)
    finally:
        if obj.name in scene.collection.objects:
            scene.collection.objects.unlink(obj)
        bpy.data.scenes.remove(scene, do_unlink=True)
        for o in made:
            data = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if data is not None and data.users == 0:
                if isinstance(data, bpy.types.Camera):
                    bpy.data.cameras.remove(data)
                elif isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)
        if rig is not None:
            rig.data.pose_position = prev_pose
        if colours_attr is not None:
            me.color_attributes.remove(me.color_attributes["ft_marks"])
            if prev_active and prev_active in me.color_attributes:
                me.color_attributes.active_color_name = prev_active
    sheet_path = os.path.join(out_dir, f"{obj.name.replace('.', '_')}_marks.json")
    with open(sheet_path, "w", encoding="utf-8") as f:
        json.dump(sheet, f, indent=1)
    sheet["sheet"] = sheet_path
    sheet["how"] = ("columns are letters from the left, rows numbers from the top; mark zones with "
                    "cells ('D7:H11' or ['E5','F5']), an ellipse ['F8', half_w, half_h], or a candidate number")
    return sheet


def _overlay(scene, centre, d, right, up, extent, grid, candidates, view):
    """Grid lines, cell labels and candidate numbers, as geometry between the camera and the body."""
    objs = []
    near = centre + d * extent * 2.0          # in front of everything, behind the camera
    cell = extent / grid
    line = extent * 0.0016

    def quad(name, a, b, width, colour):
        me = bpy.data.meshes.new(name)
        dirv = (b - a).normalized()
        side = dirv.cross(d).normalized() * width
        me.from_pydata([a - side, a + side, b + side, b - side], [], [(0, 1, 2, 3)])
        ob = bpy.data.objects.new(name, me)
        ob.color = colour
        scene.collection.objects.link(ob)
        objs.append(ob)

    def text(name, body, at, height, colour):
        cu = bpy.data.curves.new(name, "FONT")
        cu.body = body
        cu.size = height
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        ob = bpy.data.objects.new(name, cu)
        ob.location = at
        ob.rotation_euler = d.to_track_quat("Z", "Y").to_euler()     # text faces +Z: toward the camera
        ob.color = colour
        scene.collection.objects.link(ob)
        objs.append(ob)

    ink = (0.1, 0.35, 0.9, 1.0)
    for i in range(grid + 1):
        s = -extent / 2 + i * cell
        quad(f"gx{i}", near + right * s + up * (-extent / 2), near + right * s + up * (extent / 2), line, ink)
        quad(f"gy{i}", near + up * s + right * (-extent / 2), near + up * s + right * (extent / 2), line, ink)
    for i in range(grid):
        s = -extent / 2 + (i + 0.5) * cell
        text(f"col{i}", LETTERS[i], near + right * s + up * (extent / 2 - cell * 0.25), cell * 0.32, ink)
        text(f"row{i}", str(i + 1), near + up * (extent / 2 - (i + 0.5) * cell) + right * (-extent / 2 + cell * 0.22),
             cell * 0.32, ink)
    for c in candidates:
        tail = Vector(c["tail"])
        # only candidates on the camera's side of the body are labelled in this view
        if (tail - centre).dot(d) < -extent * 0.02:
            continue
        rel = tail - centre
        at = near + right * rel.dot(right) + up * rel.dot(up)
        text(f"cand{c['number']}", str(c["number"]), at, cell * 0.55, (1.0, 0.85, 0.0, 1.0))
    return objs


# ------------------------------------------------------------------ marks back to 3D

def _cell(label):
    m = re.fullmatch(r"([A-Za-z])(\d+)", label.strip())
    if not m:
        raise ValueError(f"not a cell: {label!r} (a column letter then a row number, e.g. F7)")
    return LETTERS.index(m.group(1).upper()), int(m.group(2)) - 1


def _project(P, centre, view, extent):
    """World points to (u, v) in [0, 1] image space: u right, v down."""
    right = np.array(view["right"])
    up = np.array(view["up"])
    rel = P - np.array(centre)
    u = rel @ right / extent + 0.5
    v = 0.5 - rel @ up / extent
    return u, v


def _visible(obj, P, normals, direction):
    """Vertices facing the camera and not hidden behind another part of the body."""
    d = np.array(direction)
    facing = normals @ d > 0.05
    me = obj.data
    mw = obj.matrix_world
    verts = [mw @ v.co for v in me.vertices]
    polys = [tuple(p.vertices) for p in me.polygons]
    tree = BVHTree.FromPolygons(verts, polys)
    dv = Vector(direction)
    vis = np.zeros(len(P), dtype=bool)
    for i in np.where(facing)[0]:
        origin = Vector(P[i]) + dv * 1e-3
        hit = tree.ray_cast(origin, dv)
        vis[i] = hit[0] is None
    return vis


def _mark_weights(mark, u, v, grid, candidates, centre, view, extent):
    """Per vertex weight in [0, 1] for one mark in its view's image space."""
    cell = 1.0 / grid
    if "cells" in mark:
        cells = mark["cells"]
        boxes = []
        if isinstance(cells, str) and ":" in cells:
            a, b = cells.split(":")
            (c0, r0), (c1, r1) = _cell(a), _cell(b)
            boxes.append((min(c0, c1), min(r0, r1), max(c0, c1), max(r0, r1)))
        else:
            for c in ([cells] if isinstance(cells, str) else cells):
                ci, ri = _cell(c)
                boxes.append((ci, ri, ci, ri))
        w = np.zeros(len(u))
        for c0, r0, c1, r1 in boxes:
            inside = (u >= c0 * cell) & (u <= (c1 + 1) * cell) & (v >= r0 * cell) & (v <= (r1 + 1) * cell)
            w[inside] = 1.0
        return w
    if "ellipse" in mark:
        label, hw, hh = mark["ellipse"]
        ci, ri = _cell(label)
        cu, cv = (ci + 0.5) * cell, (ri + 0.5) * cell
        dist = np.sqrt(((u - cu) / (hw * cell)) ** 2 + ((v - cv) / (hh * cell)) ** 2)
        x = np.clip(1.0 - dist, 0.0, 1.0) * 1.6
        return np.clip(x, 0.0, 1.0)
    if "candidate" in mark:
        cand = next((c for c in candidates if c["number"] == int(mark["candidate"])), None)
        if cand is None:
            raise ValueError(f"no candidate numbered {mark['candidate']}")
        return None
    raise ValueError("a mark needs cells, ellipse or candidate")


def regions(obj_name, zones, sheet):
    """Regions for flesh.prepare from 2D marks. `sheet` is what render() returned, or the
    path of the _marks.json it saved."""
    from . import flesh, registry
    if isinstance(sheet, str):
        with open(sheet, encoding="utf-8") as f:
            sheet = json.load(f)
    obj = bpy.data.objects[obj_name]
    t = flesh.tissue(obj_name)
    if "error" in t:
        return t
    c = flesh.coordinates(t)
    P = t["P"]
    normals = flesh._world_normals(obj)
    area = flesh._vertex_areas(obj)
    nbr = flesh._adjacency(obj)
    body_volume = flesh._mesh_volume(obj)
    geo = None
    grouped = {}
    seen_views = {}
    notes = []
    for z in zones:
        view = sheet["views"][z["view"]]
        if z["view"] not in seen_views:
            seen_views[z["view"]] = _visible(obj, P, normals, view["direction"])
        vis = seen_views[z["view"]]
        u, v = _project(P, sheet["centre"], view, sheet["extent"])
        w = _mark_weights(z, u, v, sheet["grid"], sheet["candidates"], sheet["centre"], view, sheet["extent"])
        if w is None:     # a candidate: take that geometric region whole
            if geo is None:
                geo = {r["name"]: r for r in flesh.find_regions(obj_name, t=t)["regions"]}
            cand = next(x for x in sheet["candidates"] if x["number"] == int(z["candidate"]))
            r = geo[cand["name"]]
            w = np.zeros(len(P))
            w[r["vertices"]] = r["weights"]
            notes.append(f"candidate {z['candidate']} ({cand['name']}) marked as {z['type']}")
            if cand["name"].endswith((".L", ".R")) and "side" not in z:
                z = dict(z, side=cand["name"][-1])
        else:
            w = w * vis
        key = (z["type"], z.get("side"))
        grouped[key] = np.maximum(grouped.get(key, np.zeros(len(P))), w)
    out = []
    types = registry.types_for(cls="flesh")
    for (tname, side), w in grouped.items():
        entry = types.get(tname, {})
        pieces = []
        if side in ("L", "R"):
            sign = 1.0 if side == "L" else -1.0
            pieces.append((f"{tname}.{side}", w * (c["side"] == sign)))
        elif entry.get("paired"):
            pieces.append((f"{tname}.L", w * (c["side"] >= 0)))
            pieces.append((f"{tname}.R", w * (c["side"] < 0)))
        else:
            pieces.append((tname, w))
        for rname, wv in pieces:
            verts = np.where(wv > 0.02)[0]
            if len(verts) < 8:
                notes.append(f"{rname}: the marks cover {len(verts)} visible vertices - nothing to rig")
                continue
            # soften the mark's edge with the tissue measure: a vertex inside the mark that
            # stands out of the lean body counts fully, a lean one at half
            geo_w = flesh._smoothstep((t["relative"][verts] - flesh.GROW_RELATIVE) / 0.2)
            weights = wv[verts] * (0.5 + 0.5 * geo_w)
            weights = _feather(verts, weights, nbr)
            reg = flesh._region(obj, t, c, rname, tname, entry, verts, area, normals, body_volume, nbr,
                                weights=weights / max(weights.max(), 1e-9))
            reg["evidence"] = [f"marked in 2D ({', '.join(sorted({z['view'] for z in zones if z['type'] == tname}))})"]
            reg["coords_range"] = {k: (float(c[k][verts].min()), float(c[k][verts].max()))
                                   for k in ("height", "facing", "lateral")}
            out.append(reg)
    return {"object": obj.name, "rig": t["rig"], "regions": out, "declined": notes, "tissue": t, "coords": c}


def _feather(verts, weights, nbr, passes=2):
    idx = {int(v): k for k, v in enumerate(verts)}
    w = weights.astype(float)
    for _ in range(passes):
        nw = w.copy()
        for k, v in enumerate(verts):
            ring = nbr[int(v)]
            nw[k] = (w[k] + sum(w[idx[x]] for x in ring if x in idx)) / (1 + len(ring))
        w = nw
    return w
