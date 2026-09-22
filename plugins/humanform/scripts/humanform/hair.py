"""L6 part: hair from a preset - a scalp cap with a feathered hairline, preset volumes, and strands.

    rep = hair.add("Belle_body", preset="bun", colour=(0.17, 0.10, 0.06))
    rep["objects"]      # {"hair": "Belle_hair"}                       rigid: cap, bun / tie / fall
                        # {"hair": ..., "strand": "Belle_hair_strand"}  ponytail and long_loose
    hair.add(body, sheet=s)             # the brief's `hair = {"preset": ..., "colour": ...}`
    hair.contract("Belle_hair_strand")  # the follow-through strand contract, read back and checked

Presets (`data/hair_presets.json`): `short_crop`, `bob`, `bun`, `ponytail`, `long_loose`.

**Needs a baked body** (no Mask modifier): the cap is cut from the surface the game draws. It works on
the rest shape of the mesh data, in world space, with the body's rig found from its Armature modifier.

**Landmarks.** Everything is placed from the head, measured on the mesh: the head bone (the rig's body
profile's head, as `eyes.head_bone`), the head's vertices (weighted >= 0.5 to it), the crown top, the
eye centre (the eyeballs, by their `HF_` materials when joined or the `<name>_eyes` object), the head's
front-to-back centre above the brows, and each ear (the most lateral head vertices around eye height).
Heights are in head units h = crown top - eye centre.

**Hairline.** A closed curve around the head - `hairline.keys`, height against azimuth, warped so the
measured ear sits at 90 degrees - with an ellipse cut around each ear. A body vertex's signed distance
`d` (metres, + inside the hair) is its height over the curve (turned into distance across it where the curve
is steep, as down a sideburn), or its distance out of the ear ellipse.
The cap is the body's faces whose mean `d` is over `-feather_m`, smooth-subdivided (kept out of the skin),
then offset along the normal by a thickness that rises from `edge_offset_m` (0.6 mm) at the edge
to the preset's full thickness `feather_in_m` inside the line, the full-thickness part relaxed so a crease in
the skin does not become a ridge. There is no wall at the edge: it is
tapered geometry. Over that, the lookdev hair material's alpha breaks the edge into strands: V is
`cap_v_hairline` at d = 0, so the geometric boundary sits in the texture's transparent root zone and the
visible hairline is strand tips with skin between them.

**Strand direction.** U runs around an axis from the head centre (toward the bun, the tie, or the crown)
and V away from the hairline - across the curve near it, along the axis's meridians further in - so a
pulled-back cap's strands run into its bun and V never goes flat or turns back on itself over the crown. U is scaled to a whole
number of texture tiles per turn, so there is no seam.

**Volumes** (rigid, in `<base>_hair`, skinned 100% to the head bone):
- `bun`: a coiled spindle torus on the head surface at the preset's azimuth and elevation, strands
  spiralling round it.
- `tie`: a small hair-wrapped ring where a ponytail is gathered.
- `fall`: bob and long_loose, a shell over the ears and nape from the crown to `bottom_h`, lying on the cap
  with no thickness at its top, hanging straight from the widest part of the head above each point (so it
  clears the ears) and flaring by `flare_m` below it, in locks (`lock_m`) with ragged ends (`ragged_m`),
  open at the face by `face_open_deg` either side of the front.

**Strands** (`<base>_hair_strand`: ponytail's tube, long_loose's curtain down the back). The follow-through
contract, on the object:
- `ft_type = "strand"`
- `ft_root_bone` = the rig's head bone name (the bone role `head`, resolved)
- `ft_centreline` = a flat [x, y, z, ...] list of `points` points in the object's local space, root first,
  evenly spaced along the strand
- `ft_length_m`, `ft_radius_m` (per centreline point: the tube's half width, the curtain's half thickness)
- `ft_strand_type` = the follow-through type the preset is (`ponytail`, `long_hair`), so the registry
  types it from the preset rather than from the object's name
- a vertex group `ft_strand` whose weight is each vertex's share of the length (0 at the root, 1 at the
  tip), so the order survives a join into another mesh
- `humanform_hair = {"preset", "part": "strand", "kind": "tube" | "curtain"}`

Until follow-through builds the chain, the strand is skinned rigidly as a fallback: to the head bone at
the root, blending into its parent (the neck) and grandparent (the chest) toward the tip, so a turn of the
head does not swing the tail through the back.
"""

from __future__ import annotations

import json
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from . import body as _body
from . import brows as _brows
from . import eyes as _eyes
from . import look
from .sheet import HAIR_PRESETS as PRESETS

EYE_MATERIALS = ("sclera", "iris", "pupil")
TILE_M = 0.04          # the lookdev hair texture's tile width, used when lookdev is not importable
# Hair scales with the head it is on. Every length here and in the presets (a key ending `_m`) was tuned on
# human heads, whose crown stands HEAD_H_REF above the eyes, give or take a tenth (HEAD_BAND). A head outside
# that band scales them all by how far outside it is (`head_scale`): a 3.1 m cyclops's head (h 0.19 m) had its
# cap cut at a fixed 16 cm from the head's axis, and the back of his skull came out bald in whole faces.
HEAD_H_REF = 0.12
HEAD_BAND = (0.9, 1.1)


def head_scale(lm):
    """1 for a head within HEAD_BAND of HEAD_H_REF (every human's hair is as it was tuned), else the head's
    height over the nearer end of the band: lengths scale with the head beyond it."""
    h = float(lm["h"])
    lo, hi = HEAD_H_REF * HEAD_BAND[0], HEAD_H_REF * HEAD_BAND[1]
    return h / hi if h > hi else (h / lo if h < lo else 1.0)


def scale_lengths(d, k):
    """`d` with every number (or list of numbers) under a key ending `_m` multiplied by `k`, recursively."""
    if isinstance(d, dict):
        out = {}
        for key, v in d.items():
            if isinstance(key, str) and key.endswith("_m") and not isinstance(v, (dict, str, bool)):
                out[key] = [x * k for x in v] if isinstance(v, (list, tuple)) else v * k
            else:
                out[key] = scale_lengths(v, k)
        return out
    if isinstance(d, list):
        return [scale_lengths(v, k) for v in d]
    return d


def presets():
    import humanform as pkg
    with open(os.path.join(pkg.DATA, "hair_presets.json"), encoding="utf-8") as fh:
        return json.load(fh)


def params(preset, **overrides):
    doc = presets()
    if preset not in doc["presets"]:
        raise ValueError(f"hair preset {preset!r} is not one of {sorted(doc['presets'])}")
    p = json.loads(json.dumps(doc["defaults"]))
    p.update(json.loads(json.dumps(doc["presets"][preset])))
    p.update(overrides)
    p["preset"] = preset
    p["hairline"] = doc["hairline"]
    return p


def _smooth(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / max(e1 - e0, 1e-9), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ------------------------------------------------------------------------------------------ landmarks

def _weights(ob, group):
    g = ob.vertex_groups.get(group)
    w = np.zeros(len(ob.data.vertices))
    if g is None:
        return w
    for v in ob.data.vertices:
        for e in v.groups:
            if e.group == g.index:
                w[v.index] = e.weight
    return w


def _world_co(ob):
    n = len(ob.data.vertices)
    co = np.empty(n * 3, np.float32)
    ob.data.vertices.foreach_get("co", co)
    m = np.array(ob.matrix_world, np.float64)
    return co.reshape(-1, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3]


def _eye_vertices(ob):
    idx = [i for i, m in enumerate(ob.data.materials) if m and any(k in m.name.lower() for k in EYE_MATERIALS)]
    if not idx:
        return np.zeros(0, np.int64)
    mi = np.empty(len(ob.data.polygons), np.int64)
    ob.data.polygons.foreach_get("material_index", mi)
    verts = set()
    for p in ob.data.polygons:
        if mi[p.index] in idx:
            verts.update(p.vertices)
    return np.array(sorted(verts), np.int64)


def landmarks(ob):
    """The head, measured on a baked body: {head_bone, top, eye, h, cy, ear_L, ear_R, chin, centre, ...}
    in world space (lists of 3 floats), plus arrays under `_` keys for the builder."""
    ob = _body.obj(ob)
    if any(m.type == "MASK" and m.show_viewport for m in ob.modifiers):
        raise ValueError(f"hair: {ob.name} still has a Mask modifier - bake it first (hair is cut from the "
                         "surface the game draws)")
    rig = _body.rig_of(ob)
    head = _eyes.head_bone(rig)
    if rig is not None and head not in rig.data.bones:
        raise ValueError(f"hair: {rig.name} has no head bone {head!r}")
    co = _world_co(ob)
    w = _weights(ob, head)
    eyes_idx = _eye_vertices(ob)
    is_eye = np.zeros(len(co), bool)
    is_eye[eyes_idx] = True
    head_mask = (w >= 0.5) & ~is_eye
    if head_mask.sum() < 50:
        raise ValueError(f"hair: fewer than 50 vertices of {ob.name} are weighted to the head bone {head!r}")
    hp = co[head_mask]
    top = float(hp[:, 2].max())
    if len(eyes_idx):
        eye = co[eyes_idx].mean(axis=0)
        eye_source = "eyeballs"
    else:
        other = next((o for o in bpy.data.objects if o.type == "MESH" and o is not ob and "eye" in o.name.lower()
                      and rig is not None and _body.rig_of(o) is rig), None)
        if other is not None:
            eye = _world_co(other).mean(axis=0)
            eye_source = other.name
        else:
            zmin = float(hp[:, 2].min())
            eye = np.array([0.0, float(hp[:, 1].min()) + 0.03, top - 0.47 * (top - zmin)])
            eye_source = "estimated"
    ez = float(eye[2])
    h = top - ez
    above = hp[hp[:, 2] > ez + 0.25 * h]
    cy = float((above[:, 1].min() + above[:, 1].max()) / 2)
    band = hp[(hp[:, 2] > ez - 0.55 * h) & (hp[:, 2] < ez + 0.15 * h)]
    ears, ear_boxes = {}, {}
    for side, sign in (("L", 1.0), ("R", -1.0)):
        s = band[band[:, 0] * sign > 0]
        # the ear: what stands out sideways past the skull near the most lateral point
        reach = float((s[:, 0] * sign).max())
        ear = s[(s[:, 0] * sign) > reach - 0.012]
        lo, hi = ear.min(axis=0), ear.max(axis=0)
        ears[side] = np.array([float(np.median(ear[:, 0])), float((lo[1] + hi[1]) / 2), float((lo[2] + hi[2]) / 2)])
        ear_boxes[side] = [round(float(hi[1] - lo[1]) / 2, 4), round(float(hi[2] - lo[2]) / 2, 4)]
    front = hp[hp[:, 1] < cy - 0.4 * h]
    chin = float(front[:, 2].min()) if len(front) else ez - 1.0 * h
    centre = np.array([0.0, cy, ez + 0.1 * h])
    # the ears themselves, on an MPFB body: every vertex MPFB's ear targets bend (humanform.brows)
    ear_idx = _brows.ear_vertices(ob)
    ear_all = np.array(sorted(ear_idx["L"] + ear_idx["R"]), np.int64) if ear_idx else np.zeros(0, np.int64)
    ear_kd = None
    if len(ear_all):
        from mathutils.kdtree import KDTree
        ear_kd = KDTree(len(ear_all))
        for k, i in enumerate(ear_all):
            ear_kd.insert(Vector(co[i]), k)
        ear_kd.balance()
    return {"head_bone": head, "rig": rig.name if rig else None, "top": top, "eye": [0.0, float(eye[1]), ez],
            "eye_source": eye_source, "h": h, "cy": cy, "ear_L": ears["L"].tolist(), "ear_R": ears["R"].tolist(),
            "ear_half_m": ear_boxes, "ear_vertices": int(len(ear_all)),
            "chin": chin, "centre": centre.tolist(), "back_y": float(hp[:, 1].max()),
            "_co": co, "_eye_vertices": eyes_idx, "_ear_vertices": ear_all, "_ear_kd": ear_kd}


# ------------------------------------------------------------------------------------------ hairline

def _azimuth(p, cy):
    """Degrees around the head's vertical axis: 0 at the front (-Y), +90 at the body's left (+X)."""
    return np.degrees(np.arctan2(p[..., 0], -(p[..., 1] - cy)))


def _warp(az_abs, ear_az):
    """Warp |azimuth| so the measured ear lands at 90: [0, ear] -> [0, 90], [ear, 180] -> [90, 180]."""
    return np.where(az_abs <= ear_az, az_abs * 90.0 / ear_az, 90.0 + (az_abs - ear_az) * 90.0 / (180.0 - ear_az))


def signed_distance(p, lm, hp):
    """Metres inside (+) or outside (-) the hairline for points (N, 3)."""
    p = np.atleast_2d(p)
    cy, ez, h = lm["cy"], lm["eye"][2], lm["h"]
    keys = np.array(hp["keys"], np.float64)
    az = _azimuth(p, cy)
    d = np.empty(len(p))
    for side, sign in (("L", 1.0), ("R", -1.0)):
        ear = np.array(lm[f"ear_{side}"])
        ear_az = float(abs(_azimuth(ear, cy)))
        sel = (az * sign) >= 0
        a = _warp(np.abs(az[sel]), ear_az)
        line = ez + h * np.interp(a, keys[:, 0], keys[:, 1])
        # height over the line, turned into distance across it where the line is steep (a sideburn's front
        # edge runs nearly vertical, and a vertical offset there would squeeze the feather to nothing)
        eps = 0.5
        slope_deg = h * (np.interp(a + eps, keys[:, 0], keys[:, 1]) - np.interp(a - eps, keys[:, 0], keys[:, 1])) / (2 * eps)
        warp_rate = np.where(np.abs(az[sel]) <= ear_az, 90.0 / ear_az, 90.0 / (180.0 - ear_az))
        # the head's radius where a hairline runs; not the point's own, which goes to 0 on top of the head
        radius = np.maximum(np.hypot(p[sel, 0], p[sel, 1] - cy), 0.06 * lm.get("scale", 1.0))
        slope = slope_deg * warp_rate / (radius * math.pi / 180.0)
        dz = (p[sel, 2] - line) / np.sqrt(1.0 + slope * slope)
        if "ear_half_m" in lm:
            # the measured box holds skin around the ear too; `ear_scale` shrinks it to the ear itself
            ry, rz = np.array(lm["ear_half_m"][side]) * np.array(hp.get("ear_scale", [1.0, 1.0])) + hp["ear_margin_m"]
        else:
            ry, rz = hp["ear_ellipse_m"]
        q = np.sqrt(((p[sel, 1] - ear[1]) / ry) ** 2 + ((p[sel, 2] - ear[2]) / rz) ** 2)
        lateral = (p[sel, 0] * sign) > (abs(ear[0]) - 0.035 * lm.get("scale", 1.0))
        ear_d = (q - 1.0) * min(ry, rz)
        d[sel] = np.where(lateral, np.minimum(dz, ear_d), dz)
    kd = lm.get("_ear_kd")
    if kd is not None:
        # the ear itself: no hair within `ear_clear_m` of any ear vertex, the feather running out from there
        clear = hp.get("ear_clear_m", 0.004)
        near = np.array([kd.find(Vector(q))[2] for q in p])
        d = np.minimum(d, near - clear)
    return d


# ------------------------------------------------------------------------------------------ helpers

def _bvh(co, ob, skip_vertices):
    skip = set(int(i) for i in skip_vertices)
    polys = [tuple(p.vertices) for p in ob.data.polygons if not any(v in skip for v in p.vertices)]
    return BVHTree.FromPolygons([Vector(c) for c in co], polys)


def _axis_frame(axis):
    a = Vector(axis).normalized()
    ref = Vector((0.0, -1.0, 0.0))
    r0 = (ref - a * ref.dot(a))
    if r0.length < 1e-6:
        r0 = Vector((0.0, 0.0, 1.0)) - a * a.z
    r0.normalize()
    return a, r0, a.cross(r0)


def _surface_point(bvh, centre, direction):
    """Where a ray from outside the head toward `centre` along -direction first meets the skin."""
    d = Vector(direction).normalized()
    origin = Vector(centre) + d * 0.5
    loc, normal, _i, _dist = bvh.ray_cast(origin, -d, 1.0)
    if loc is None:
        raise ValueError("hair: a ray toward the head centre missed the body")
    return loc, normal


def _dir(azimuth, elevation):
    a, e = math.radians(azimuth), math.radians(elevation)
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


def _set_uvs(bm, uv_layer, uv_of_loop):
    for f in bm.faces:
        for loop in f.loops:
            loop[uv_layer].uv = uv_of_loop(f, loop)


def _grid_faces(bm, grid, closed_u=False, flip=False):
    """Quads over a rows x columns list of BMVerts. Returns the faces with their (row, col) corners."""
    out = []
    rows, cols = len(grid), len(grid[0])
    for i in range(rows - 1):
        for j in range(cols - (0 if closed_u else 1)):
            jn = (j + 1) % cols
            quad = [grid[i][j], grid[i][jn], grid[i + 1][jn], grid[i + 1][j]]
            corners = [(i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j)]
            if flip:
                quad.reverse()
                corners.reverse()
            f = bm.faces.new(quad)
            out.append((f, corners))
    return out


# ------------------------------------------------------------------------------------------ parts

def _cap(ob, lm, p, bvh, uv_name, tile):
    co = lm["_co"]
    hp = p["hairline"]
    ez, h = lm["eye"][2], lm["h"]
    d_all = np.full(len(co), -1.0)
    k_ = lm.get("scale", 1.0)
    near = (co[:, 2] > ez - 1.1 * h) & (np.hypot(co[:, 0], co[:, 1] - lm["cy"]) < 0.16 * k_)
    near[lm["_eye_vertices"]] = False
    d_all[near] = signed_distance(co[near], lm, hp)

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    feather = p["feather_m"]
    ear = np.zeros(len(co), bool)
    if p.get("ear_cut", True):
        ear[lm.get("_ear_vertices", np.zeros(0, np.int64))] = True
    keep = []
    for f in bm.faces:
        idx = [v.index for v in f.verts]
        if all(near[i] for i in idx) and not any(ear[i] for i in idx) and float(np.mean(d_all[idx])) > -feather:
            keep.append(f)
    faces_from_body = len(keep)
    keep_set = set(keep)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f not in keep_set], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    dl = bm.verts.layers.deform.active
    if dl is not None:
        for v in bm.verts:
            v[dl].clear()
    for layer in list(bm.loops.layers.uv.values()):
        bm.loops.layers.uv.remove(layer)
    for layer in list(bm.loops.layers.color.values()):
        bm.loops.layers.color.remove(layer)
    mw = ob.matrix_world
    for v in bm.verts:
        v.co = mw @ v.co
    for _ in range(int(p.get("subdivide", 1))):
        # smooth subdivision, so the cap's outline is round where the body's quads are coarse (the back of
        # the skull); a new vertex that falls inside the skin (a concave spot) is put back on it
        bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=1, use_grid_fill=True, smooth=1.0)
        for v in bm.verts:
            hit = bvh.find_nearest(v.co)
            if hit[0] is not None and (v.co - hit[0]).dot(hit[1]) < 0:
                v.co = hit[0]
    bm.verts.index_update()
    bm.faces.index_update()
    bm.normal_update()
    pts = np.array([tuple(v.co) for v in bm.verts])
    d = signed_distance(pts, lm, hp)
    normals = [v.normal.copy() for v in bm.verts]
    # two passes of neighbour-averaged normals, so the offset surface does not ripple over the quads
    for _ in range(2):
        normals = [sum((normals[e.other_vert(v).index] for e in v.link_edges), normals[v.index]).normalized()
                   for v in bm.verts]
    top = lm["top"]
    full = p["cap_thick_m"] + p["crown_extra_m"] * _smooth(ez + 0.3 * h, top, pts[:, 2])
    rise = _smooth(-feather, p["feather_in_m"], d)
    thick = p["edge_offset_m"] + (full - p["edge_offset_m"]) * rise
    # the geometric edge always lies on the skin and sits in the texture's transparent root zone, and the ring
    # inside it only part way up, wherever the hairline curve itself runs
    boundary = np.array([v.is_boundary for v in bm.verts])
    ring = np.array([not b and any(e.other_vert(v).is_boundary for e in v.link_edges)
                     for v, b in zip(bm.verts, boundary)])
    edge = p["edge_offset_m"]
    thick = np.where(boundary, edge, np.where(ring, np.minimum(thick, edge + 0.4 * (thick - edge)), thick))
    for v, n, t in zip(bm.verts, normals, thick):
        v.co = v.co + n * float(t)
    # an offset surface sharpens a concave crease of the skin (the skull's base over the nape) into a ridge
    # that catches a rim light: relax the full-thickness part, then keep it clear of the skin by half its
    # thickness
    free = [v for v, b, r in zip(bm.verts, boundary, ring) if not b and not r]
    for _ in range(int(p.get("cap_relax", 4))):
        target = {v.index: sum((e.other_vert(v).co for e in v.link_edges), Vector()) / max(len(v.link_edges), 1)
                  for v in free}
        for v in free:
            v.co = v.co.lerp(target[v.index], 0.5)
    for v in free:
        t = float(thick[v.index])
        hit = bvh.find_nearest(v.co)
        if hit[0] is None:
            continue
        off = v.co - hit[0]
        if off.dot(hit[1]) < 0.5 * t:
            v.co = hit[0] + hit[1] * (0.5 * t)

    # UVs: U around the strand axis, V away from the hairline
    axis_to = p.get("axis", {})
    centre = Vector(lm["centre"])
    if "to" in axis_to:
        axis = p["_targets"][axis_to["to"]] - centre
    else:
        axis = _dir(axis_to.get("azimuth", 180), axis_to.get("elevation", 70))
    a, r0, r1 = _axis_frame(axis)
    turns = max(1, round(2 * math.pi * 0.09 * k_ / tile))
    # V: distance from the hairline. Near the line it is `d`, across the hairline curve (the only measure that
    # knows an ear). A few centimetres in it becomes the distance along the strand axis's meridian from where
    # that meridian crosses the hairline. `d` alone is a height, and over the top of the head
    # its gradient lies along U: the UV handedness flips in patches there and Godot's generated tangents swing
    # the anisotropic highlight into glints. The meridian distance always runs toward the pole.
    q = pts - np.array(tuple(centre))
    qn = np.maximum(np.linalg.norm(q, axis=1), 1e-6)
    theta = np.arccos(np.clip(q @ np.array(tuple(a)) / qn, -1.0, 1.0))
    phi = np.arctan2(q @ np.array(tuple(r1)), q @ np.array(tuple(r0)))
    # where each meridian first crosses the hairline going out from the pole: rays cast at the skin along it
    nbins = 72
    bins = ((phi + math.pi) / (2 * math.pi) * nbins).astype(int) % nbins
    thetas = np.radians(np.arange(2.0, 178.0, 1.0))
    line_theta = np.full(nbins, np.nan)
    ca, c0, c1 = np.array(tuple(a)), np.array(tuple(r0)), np.array(tuple(r1))
    for k in range(nbins):
        ph = (k + 0.5) / nbins * 2 * math.pi - math.pi
        dirs = (np.cos(thetas)[:, None] * ca + np.sin(thetas)[:, None] * (math.cos(ph) * c0 + math.sin(ph) * c1))
        hits = []
        for dv in dirs:
            loc, _n, _i, _dist = bvh.ray_cast(centre + Vector(dv) * 0.3 * k_, Vector(-dv), 0.3 * k_)
            hits.append(tuple(loc) if loc is not None else (np.nan,) * 3)
        hits = np.array(hits)
        ok = ~np.isnan(hits[:, 0])
        if ok.sum() < 2:
            continue
        dd = np.full(len(hits), np.nan)
        dd[ok] = signed_distance(hits[ok], lm, hp)
        out = np.nonzero(ok & (dd < 0))[0]
        if len(out):
            j = out[0]
            if j > 0 and ok[j - 1]:
                f = dd[j - 1] / max(dd[j - 1] - dd[j], 1e-9)
                line_theta[k] = thetas[j - 1] + f * (thetas[j] - thetas[j - 1])
            else:
                line_theta[k] = thetas[j]
    have = ~np.isnan(line_theta)
    if have.any():
        centres = np.arange(nbins)
        line_theta = np.interp(centres, np.concatenate([centres[have] - nbins, centres[have], centres[have] + nbins]),
                               np.tile(line_theta[have], 3))
        for _ in range(4):       # the crossing jumps where the line turns down a sideburn; V must not
            line_theta = (np.roll(line_theta, 1) + 2 * line_theta + np.roll(line_theta, -1)) / 4
        # continuous in phi between bin centres
        fb = (phi + math.pi) / (2 * math.pi) * nbins - 0.5
        i0 = np.floor(fb).astype(int)
        fr = fb - i0
        lt = line_theta[i0 % nbins] * (1 - fr) + line_theta[(i0 + 1) % nbins] * fr
        meridian = (lt - theta) * qn
        w = _smooth(0.008 * k_, 0.03 * k_, d)
        # far from the line `d` counts for a quarter, so it wins only where the meridian has no hairline to
        # measure from (under an ear); a smooth maximum, so V has no crease where they trade places
        d_far = np.where(d < 0.04 * k_, d, 0.04 * k_ + 0.25 * (d - 0.04 * k_))
        k = 0.015 * k_
        far_g = 0.5 * (meridian + d_far + np.sqrt((meridian - d_far) ** 2 + k * k))
        g = (1 - w) * d + w * far_g
    else:
        g = d
    # V rises at 1 / cap_v_span_m per metre for `cap_v_near_m`, then at whatever rate brings the farthest point
    # to cap_v_max. It is never clamped above: a run of faces at one V has no tangent either.
    v_h, v_max, span = p["cap_v_hairline"], p["cap_v_max"], p["cap_v_span_m"]
    d1 = p.get("cap_v_near_m", 0.03)
    v1 = v_h + d1 / span
    far = max(float(g.max()), d1 + 1e-3)
    slope2 = max((v_max - v1) / (far - d1), 0.0)
    v_of = np.where(g <= d1, v_h + g / span, v1 + (g - d1) * slope2)
    wobble = p.get("edge_wobble_m", 0.0)
    if wobble:
        # the hairline wanders: V near the line moves by up to `edge_wobble_m` (as distance) with a sum of sines
        # round the head whose shortest wavelength is about a texture tile, so the texture's own ragged edge,
        # which repeats every tile, does not show as a repeat
        wrng = np.random.RandomState(p.get("edge_seed", 3))
        az = np.radians(_azimuth(pts, lm["cy"]))
        wav = np.zeros(len(pts))
        for k in range(3, 15):
            wav += wrng.normal() / k * np.sin(k * az + wrng.uniform(0, 2 * math.pi))
        wav /= max(float(np.abs(wav).max()), 1e-9)
        v_of = v_of + wobble * wav * (1 - _smooth(0.01 * k_, 0.035 * k_, d)) / span
    v_of = np.maximum(v_of, 0.001)
    v_of = np.where(boundary, np.minimum(v_of, 0.003), v_of)
    uv = bm.loops.layers.uv.new(uv_name)

    def ang(pt):
        q = Vector(pt) - centre
        return math.atan2(q.dot(r1), q.dot(r0))

    angles = np.array([ang(q) for q in pts])
    line_u = p.get("line_u_m", 0.0)
    line_rep = None
    if line_u:
        # U carried straight off the hairline (off at the defaults): within `line_u_m` of the line, U is the
        # strand axis's angle at the point of the line the vertex lies across from (a Newton step down the
        # gradient of `d` over the skin), so U runs along the line and V straight across it. Around the axis alone,
        # U and V meet at a slant where the line runs steeply (the temples, a sideburn) and the texture's
        # thinning root zone shears into long diagonal spikes. Past `line_u_m` it eases back to the axis's U.
        sel = np.nonzero(d < line_u)[0]
        bm.verts.ensure_lookup_table()
        bm.normal_update()
        if len(sel):
            nrm = np.array([tuple(bm.verts[i].normal) for i in sel])
            eps = 0.001
            grad = np.zeros((len(sel), 3))
            for k in range(3):
                e = np.zeros(3)
                e[k] = eps
                grad[:, k] = (signed_distance(pts[sel] + e, lm, hp) - signed_distance(pts[sel] - e, lm, hp)) / (2 * eps)
            grad -= nrm * np.sum(grad * nrm, axis=1)[:, None]          # along the skin
            g2 = np.maximum(np.sum(grad * grad, axis=1), 0.25)          # |grad d| is ~1; never a long jump
            foot = pts[sel] - (d[sel] / g2)[:, None] * grad
            a_foot = np.array([ang(q) for q in foot])
            diff = (angles[sel] - a_foot + math.pi) % (2 * math.pi) - math.pi
            w = _smooth(0.3 * line_u, line_u, d[sel])
            # the turn, relaxed over the mesh: `d`'s gradient jumps where the ear's distance takes over, and a
            # foot that jumps between neighbours folds the UVs into facets
            turn = np.zeros(len(pts))
            turn[sel] = -(1 - w) * diff
            inside = np.zeros(len(pts), bool)
            inside[sel] = True
            nbrs = [[e.other_vert(bm.verts[i]).index for e in bm.verts[i].link_edges] for i in sel]
            # held at the line itself (where U must run along it), free from 0.3 `line_u_m` in
            hold = 0.5 * _smooth(0.0, 0.3 * line_u, d[sel])
            for _ in range(int(p.get("line_u_relax", 16))):
                avg = np.array([turn[nb].mean() if nb else turn[i] for i, nb in zip(sel, nbrs)])
                turn[sel] = (1 - hold) * turn[sel] + hold * avg
            angles[sel] = angles[sel] + turn[sel]
            line_rep = {"verts": int(len(sel)), "line_u_m": line_u,
                        "turned_deg_max": round(float(np.degrees(np.abs(turn[sel])).max()), 2)}

    for f in bm.faces:
        base = None
        for loop in f.loops:
            t = float(angles[loop.vert.index])
            if base is None:
                base = t
            while t - base > math.pi:
                t -= 2 * math.pi
            while t - base < -math.pi:
                t += 2 * math.pi
            loop[uv].uv = (t / (2 * math.pi) * turns, float(v_of[loop.vert.index]))
    rep = {"faces_from_body": faces_from_body, "verts": len(bm.verts), "faces": len(bm.faces),
           "boundary_verts": int(boundary.sum()),
           "boundary_offset_mm_max": round(float(thick[boundary].max()) * 1000, 3) if boundary.any() else None,
           "boundary_d_mm": [round(float(d[boundary].min()) * 1000, 1), round(float(d[boundary].max()) * 1000, 1)]
           if boundary.any() else None,
           "boundary_v_max": round(float(v_of[boundary].max()), 4) if boundary.any() else None,
           "thick_mm": [round(float(thick.min()) * 1000, 2), round(float(thick.max()) * 1000, 2)],
           "strand_turns": turns, "uv_handedness": _handedness(bm, uv, d, 0.03), "line_u": line_rep,
           "ear_covered_verts": ear_coverage(bm, lm, ob)}
    return bm, rep, (pts, d, v_of, boundary)


def ear_coverage(bm, lm, ob, within=0.02):
    """How many of the body's ear vertices the cap lies over: an ear vertex facing out of the head (its normal
    within 78 degrees of the direction from the head's centre) whose normal, followed out for `within` metres,
    meets the cap. The back of the ear faces the scalp, which is hair, so it is not counted. 0 is the goal;
    None on a body with no known ears."""
    idx = lm.get("_ear_vertices")
    if idx is None or not len(idx):
        return None
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    centre = Vector(lm["centre"])
    rot = ob.matrix_world.to_3x3()
    covered = 0
    for i in idx:
        p = Vector(lm["_co"][i])
        n = (rot @ ob.data.vertices[int(i)].normal).normalized()
        if n.dot((p - centre).normalized()) < 0.2:
            continue
        hit = tree.ray_cast(p + n * 0.0003, n, within)
        if hit[0] is not None:
            covered += 1
    return covered


def _handedness(bm, uv, d, beyond):
    """Faces whose every vertex is more than `beyond` metres inside the hairline, by the sign of their UV frame
    against their normal: {"same", "flipped", "flat"} (flat: no V change). Away from the line and the ears V
    must run one way round U everywhere, or the tangents Godot and Blender derive from it flip in patches."""
    out = {"same": 0, "flipped": 0, "flat": 0}
    counts = {}
    for f in bm.faces:
        if not all(d[v.index] > beyond for v in f.verts):
            continue
        ls = f.loops
        p0, p1, p2 = ls[0].vert.co, ls[1].vert.co, ls[2].vert.co
        u0, u1, u2 = ls[0][uv].uv, ls[1][uv].uv, ls[2][uv].uv
        e1, e2 = p1 - p0, p2 - p0
        a1, a2 = u1 - u0, u2 - u0
        det = a1.x * a2.y - a1.y * a2.x
        if abs(det) < 1e-9:
            out["flat"] += 1
            continue
        tan = (e1 * a2.y - e2 * a1.y) / det
        bit = (e2 * a1.x - e1 * a2.x) / det
        counts["same" if tan.cross(bit).dot(f.normal) > 0 else "flipped"] = counts.get(
            "same" if tan.cross(bit).dot(f.normal) > 0 else "flipped", 0) + 1
    out.update(counts)
    return out


def _torus(bm, uv, centre, axis, major, minor, segs, tile, v_range, flatten=1.0, spiral=True):
    a, r0, r1 = _axis_frame(axis)
    nu, nv = segs
    grid = []
    for i in range(nu + 1):
        th = 2 * math.pi * i / nu
        radial = r0 * math.cos(th) + r1 * math.sin(th)
        row = []
        for j in range(nv + 1):
            ph = 2 * math.pi * j / nv
            if i == nu or j == nv:
                row.append(None)
                continue
            pos = centre + radial * (major + minor * math.cos(ph)) + a * (minor * math.sin(ph) * flatten)
            row.append(bm.verts.new(pos))
        grid.append(row)
    k_minor = max(1, round(2 * math.pi * minor / tile))
    faces = 0
    for i in range(nu):
        for j in range(nv):
            idx = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            verts = [grid[ii % nu][jj % nv] for ii, jj in idx]
            f = bm.faces.new(verts)
            for loop, (ii, jj) in zip(f.loops, idx):
                su, sv = ii / nu, jj / nv
                u = (sv + (su if spiral else 0.0)) * k_minor
                vv = v_range[0] + (v_range[1] - v_range[0]) * 0.5 * (1 + math.cos(2 * math.pi * su))
                loop[uv].uv = (u, vv)
            f.smooth = True
            faces += 1
    return faces


def _coil(bm, uv, base, axis, spec, tile):
    """A bun: a tube wound in a flat spiral from its centre out, domed, its outer end tucked to the head."""
    a, r0, r1 = _axis_frame(axis)
    n, m = spec["segments"]
    tube = spec["tube_m"]
    outer = spec["radius_m"] - tube
    inner = 0.15 * tube          # the first turn starts almost on the axis
    turns = spec["turns"]
    line, radii = [], []
    for k in range(n):
        s = k / (n - 1)
        ang = 2 * math.pi * turns * s
        rad = inner + (outer - inner) * s
        # the inner end tapers to a point and sinks below the first turn, so the middle shows no end
        height = tube * 0.95 * (1 - s * s) - tube * 0.7 * (1 - float(_smooth(0.0, 0.2, s)))
        line.append(base + (r0 * math.cos(ang) + r1 * math.sin(ang)) * rad + a * (tube * 0.7 + height))
        radii.append(tube * (0.25 + 0.75 * float(_smooth(0.0, 0.25, s))) * (1 - 0.35 * float(_smooth(0.8, 1.0, s))))
    pts = np.array([tuple(x) for x in line])
    tang = np.gradient(pts, axis=0)
    tang /= np.linalg.norm(tang, axis=1)[:, None]
    grid = []
    for k in range(n):
        tk = Vector(tang[k])
        b0 = (a - tk * a.dot(tk)).normalized()
        c0 = tk.cross(b0)
        grid.append([bm.verts.new(line[k] + b0 * (radii[k] * math.cos(2 * math.pi * j / m))
                                  + c0 * (radii[k] * math.sin(2 * math.pi * j / m))) for j in range(m)])
    k_ring = max(1, round(2 * math.pi * tube / tile))
    length = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())
    v0, v1 = spec["v"]
    faces = 0
    for f, corners in _grid_faces(bm, grid, closed_u=True):
        for loop, (i, j) in zip(f.loops, corners):
            loop[uv].uv = (j / m * k_ring, v0 + (v1 - v0) * i / (n - 1))
        f.smooth = True
        faces += 1
    for row, k, flip in ((grid[0], 0, True), (grid[-1], n - 1, False)):
        if k:
            cap = bm.verts.new(Vector(pts[k]) + Vector(tang[k]) * (radii[k] * 0.6))
        else:       # the inner end dives into the coil, so its tip is hidden rather than a dimple
            cap = bm.verts.new(Vector(pts[k]) - Vector(tang[k]) * (radii[k] * 0.3) - a * (radii[k] * 0.9))
        for j in range(m):
            tri = [row[j], row[(j + 1) % m], cap]
            if flip:
                tri.reverse()
            f = bm.faces.new(tri)
            for loop in f.loops:
                jj = j if loop.vert is row[j] else j + 1
                end_v = (v0 - 0.01) if k == 0 else (v1 + 0.01)       # the tip a little past the ring: no flat V
                loop[uv].uv = (((jj if loop.vert is not cap else j + 0.5) / m * k_ring),
                               end_v if loop.vert is cap else (v0 if k == 0 else v1))
            f.smooth = True
            faces += 1
    return faces, length


def _fall(bm, uv, lm, p, bvh, tile):
    fp = p["fall"]
    ez, h, cy = lm["eye"][2], lm["h"], lm["cy"]
    ncol, nrow = fp["columns"], fp["rows"]
    s = np.linspace(0, 1, nrow)
    zs = np.linspace(ez + fp["top_h"] * h, ez + fp["bottom_h"] * h, nrow)
    # open at the face: narrow at the crown (the fall starts from the parting), `face_open_deg` from `open_at`
    top_open = fp.get("crown_open_deg", fp["face_open_deg"])
    opening = top_open + (fp["face_open_deg"] - top_open) * _smooth(0.0, fp.get("open_at", 0.35), s)
    azs = np.stack([np.linspace(o, 360.0 - o, ncol) for o in opening])
    r = np.zeros((nrow, ncol))
    for j in range(ncol):
        for i, z in enumerate(zs):
            a = math.radians(azs[i, j])
            dvec = Vector((math.sin(a), -math.cos(a), 0.0))
            origin = Vector((0.0, cy, z)) + dvec * 0.4 * lm.get("scale", 1.0)
            loc, _n, _k, _dist = bvh.ray_cast(origin, -dvec, 0.4 * lm.get("scale", 1.0))
            r[i, j] = (Vector((loc.x, loc.y - cy, 0.0)).length if loc is not None else (r[i - 1, j] if i else 0.02))
    r_skin = r.copy()
    r = np.maximum.accumulate(r, axis=0)            # hang straight down from the widest point above
    for _ in range(3):
        r[:, 1:-1] = 0.25 * r[:, :-2] + 0.5 * r[:, 1:-1] + 0.25 * r[:, 2:]
    cap = p["cap_thick_m"]
    # the fall is the outer surface from the crown down: its top row lies on the cap with no thickness, so it
    # has no edge to see, then it thickens and, below the widest part of the head, hangs out to the flare
    emerge = fp.get("emerge_at", 0.3)
    under = cap + p["crown_extra_m"] + 0.0005
    off = (under + 0.0015 * _smooth(0.0, 0.15, s) + (fp["flare_m"] - under - 0.0015) * _smooth(emerge, 0.9, s)
           - fp["tuck_m"] * _smooth(0.8, 1.0, s))
    # locks: a slow wave round the head, deeper toward the ends, so the sides are not one slab; and ends of
    # uneven length
    rng = np.random.RandomState(fp.get("seed", 7))
    n_locks = fp.get("locks", 9)
    lock_amp = fp.get("lock_m", 0.004)
    phase = rng.uniform(0, 2 * math.pi, 3)
    lock = np.zeros((nrow, ncol))
    for k, ph in enumerate(phase):
        lock += np.sin(np.radians(azs) * n_locks * (k + 1) / 2 + ph) / (k + 1)
    lock = lock_amp * lock * _smooth(emerge, 1.0, s)[:, None]
    ragged = fp.get("ragged_m", 0.01) * rng.uniform(0.0, 1.0, ncol)
    ragged = np.convolve(np.concatenate([ragged[-2:], ragged, ragged[:2]]), np.ones(5) / 5, mode="valid")
    thick = np.minimum(fp["thick_m"] * _smooth(-0.05, 0.25, s) + 0.0008, off)
    edges = _smooth(0.0, fp.get("edge_taper_deg", 14.0), np.minimum(azs - azs[:, :1], azs[:, -1:] - azs))
    # whether the cap is under a point of the fall: the hairline's signed distance there, eased over the feather
    probe = np.stack([np.sin(np.radians(azs)) * r_skin, cy - np.cos(np.radians(azs)) * r_skin,
                      np.repeat(zs[:, None], ncol, axis=1)], axis=2).reshape(-1, 3)
    e_cap = _smooth(-p["feather_m"], p["feather_in_m"], signed_distance(probe, lm, p["hairline"])).reshape(nrow, ncol)
    outer, inner = [], []
    for i, z in enumerate(zs):
        orow, irow = [], []
        for j in range(ncol):
            a = azs[i, j]
            dvec = Vector((math.sin(math.radians(a)), -math.cos(math.radians(a)), 0.0))
            base = Vector((0.0, cy, z))
            # at its edges the fall lies back down under the cap (or on the skin) and thins to nothing
            e = edges[i, j]
            # at its edges the fall thins to nothing lying on the cap (on the skin, below the cap's edge)
            o = under * e_cap[i, j] + (off[i] + lock[i, j] - under * e_cap[i, j]) * e
            t = 0.001 + (thick[i] - 0.001) * e
            rr = r_skin[i, j] + (r[i, j] - r_skin[i, j]) * e
            base = base - Vector((0.0, 0.0, ragged[j] * float(_smooth(0.7, 1.0, s[i]))))
            orow.append(bm.verts.new(base + dvec * (rr + o)))
            irow.append(bm.verts.new(base + dvec * (rr + max(o - t, 0.0005))))
        outer.append(orow)
        inner.append(irow)
    r_nom = 0.1 * lm.get("scale", 1.0)
    v0, v1 = fp["v"]

    def u_of(j, i=None):
        return math.radians(azs[i if i is not None else nrow - 1, j]) * r_nom / tile

    def v_of(i):
        return v0 + (v1 - v0) * s[i]

    faces = 0
    for grid, flip in ((outer, True), (inner, False)):
        for f, corners in _grid_faces(bm, grid, flip=flip):
            for loop, (i, j) in zip(f.loops, corners):
                loop[uv].uv = (u_of(j, i), v_of(i))
            f.smooth = True
            faces += 1
    # bottom rim: strand tips; front edges: along the strands
    last = nrow - 1
    for j in range(ncol - 1):
        f = bm.faces.new([inner[last][j], inner[last][j + 1], outer[last][j + 1], outer[last][j]])
        for loop, (jj, vv) in zip(f.loops, ((j, v1), (j + 1, v1), (j + 1, 0.99), (j, 0.99))):
            loop[uv].uv = (u_of(jj), vv)
        f.smooth = True
        faces += 1
    for j, flip in ((0, True), (ncol - 1, False)):
        for i in range(nrow - 1):
            quad = [outer[i][j], outer[i + 1][j], inner[i + 1][j], inner[i][j]]
            if flip:
                quad.reverse()
            f = bm.faces.new(quad)
            for loop in f.loops:
                ii = i if loop.vert in (outer[i][j], inner[i][j]) else i + 1
                loop[uv].uv = (u_of(j, ii) + (0.02 if loop.vert in (inner[i][j], inner[i + 1][j]) else 0.0), v_of(ii))
            f.smooth = True
            faces += 1
    return {"faces": faces, "bottom_z": round(float(zs[-1]), 4), "radius_m": [round(float(r.min()), 4),
            round(float(r.max()), 4)], "flare_mm": round(float(off.max()) * 1000, 1)}


# A fringe (bangs, `add(fringe=...)`): a sheet across the front of the head from the cap down over the forehead,
# in head units h like the presets (0 at the eyes; the hairline is at 0.55 h at the front). Any preset can wear
# one, and these numbers are merged in only when a build asks, so no preset's resolved parameters (and no build's
# hash) move without it. `width_deg` either side of the front; `top_h` where it leaves the cap (near the crown:
# at 0.8 h the step onto the cap showed as a line across the head), `bottom_h` where
# it ends (0.2 h: at the brows); it lies `off_m` off the forehead at its ends, thickens to `thick_m`, and its ends
# are `ragged_m` uneven.
FRINGE = {"width_deg": 62.0, "top_h": 0.95, "bottom_h": 0.2, "off_m": 0.003, "thick_m": 0.005, "ragged_m": 0.008,
          "edge_taper_deg": 16.0, "columns": 30, "rows": 12, "v": [0.55, 0.985], "seed": 11}


def _fringe(bm, uv, lm, p, bvh, tile, fp):
    """The fringe's outer and inner sheets and its rim, hung straight down from the widest point above (over the
    brow ridge, not into the hollow under it) and thinning to nothing at its sides, where the fall takes over."""
    ez, h, cy = lm["eye"][2], lm["h"], lm["cy"]
    ncol, nrow = int(fp["columns"]), int(fp["rows"])
    s = np.linspace(0, 1, nrow)
    zs = np.linspace(ez + fp["top_h"] * h, ez + fp["bottom_h"] * h, nrow)
    azs = np.linspace(-fp["width_deg"], fp["width_deg"], ncol)
    r = np.zeros((nrow, ncol))
    for j, a_deg in enumerate(azs):
        a = math.radians(a_deg)
        dvec = Vector((math.sin(a), -math.cos(a), 0.0))
        for i, z in enumerate(zs):
            loc, _n, _k, _d = bvh.ray_cast(Vector((0.0, cy, z)) + dvec * 0.4 * lm.get("scale", 1.0), -dvec,
                                           0.4 * lm.get("scale", 1.0))
            r[i, j] = Vector((loc.x, loc.y - cy, 0.0)).length if loc is not None else (r[i - 1, j] if i else 0.08)
    r = np.maximum.accumulate(r, axis=0)
    under = p["cap_thick_m"] + p["crown_extra_m"] + 0.0005
    # on the cap at the top, easing down onto the forehead by half way, then lying `off_m` off it
    off = under + (fp["off_m"] - under) * _smooth(0.0, 0.5, s)
    thick = 0.0008 + (fp["thick_m"] - 0.0008) * _smooth(0.0, 0.4, s)
    edge_deg = np.minimum(azs + fp["width_deg"], fp["width_deg"] - azs)
    edges = _smooth(0.0, fp["edge_taper_deg"], edge_deg)
    rng = np.random.RandomState(int(fp.get("seed", 11)))
    ragged = fp["ragged_m"] * rng.uniform(0.0, 1.0, ncol)
    ragged = np.convolve(np.concatenate([ragged[:1], ragged, ragged[-1:]]), np.ones(3) / 3, mode="valid")
    outer, inner = [], []
    for i, z in enumerate(zs):
        orow, irow = [], []
        for j, a_deg in enumerate(azs):
            a = math.radians(a_deg)
            dvec = Vector((math.sin(a), -math.cos(a), 0.0))
            e = edges[j]
            o = under + (off[i] - under) * e            # at its sides it stays on the cap, under the fall
            t = 0.0005 + (thick[i] - 0.0005) * e
            base = Vector((0.0, cy, z - ragged[j] * float(_smooth(0.6, 1.0, s[i]))))
            orow.append(bm.verts.new(base + dvec * (r[i, j] + o)))
            irow.append(bm.verts.new(base + dvec * (r[i, j] + max(o - t, 0.0005))))
        outer.append(orow)
        inner.append(irow)
    r_nom = 0.1 * lm.get("scale", 1.0)
    v0, v1 = fp["v"]

    def u_of(j):
        return math.radians(azs[j]) * r_nom / tile

    def v_of(i):
        return v0 + (v1 - v0) * s[i]

    faces = 0
    for grid, flip in ((outer, True), (inner, False)):
        for f, corners in _grid_faces(bm, grid, flip=flip):
            for loop, (i, j) in zip(f.loops, corners):
                loop[uv].uv = (u_of(j), v_of(i))
            f.smooth = True
            faces += 1
    last = nrow - 1
    for j in range(ncol - 1):                           # the ends: strand tips
        f = bm.faces.new([inner[last][j], inner[last][j + 1], outer[last][j + 1], outer[last][j]])
        for loop, (jj, vv) in zip(f.loops, ((j, v1), (j + 1, v1), (j + 1, 0.99), (j, 0.99))):
            loop[uv].uv = (u_of(jj), vv)
        f.smooth = True
        faces += 1
    return {"faces": faces, "top_z": round(float(zs[0]), 4), "bottom_z": round(float(zs[-1]), 4),
            "width_deg": fp["width_deg"], "off_mm": round(float(off[-1]) * 1000, 1)}


def _resample(points, n):
    pts = np.asarray(points, np.float64)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    t = np.linspace(0.0, s[-1], n)
    return np.stack([np.interp(t, s, pts[:, k]) for k in range(3)], axis=1), float(s[-1])


def _push_out(bvh, pos, clearance):
    hit = bvh.find_nearest(pos)
    if hit[0] is None:
        return pos
    loc, normal = hit[0], hit[1]
    off = pos - loc
    dist = off.length
    outward = off.normalized() if dist > 1e-6 and off.dot(normal) > 0 else normal
    if off.dot(normal) < 0 or dist < clearance:
        return loc + outward * clearance
    return pos


def _tube(bm, uv, root, root_normal, sp, bvh, tile):
    n = sp["points"]
    L = sp["length_m"]
    down = Vector((0.0, 0.0, -1.0))
    fine = 4 * n
    ds = L / (fine - 1)
    r_root, r_peak, r_tip = sp["radius_m"]
    peak = sp["peak_at"]

    def radius(t):
        return (r_root + (r_peak - r_root) * float(_smooth(0.0, peak, t))
                - (r_peak - r_tip) * float(_smooth(peak + 0.05, 1.0, t)))

    pts = [root.copy()]
    direction = (root_normal * 0.8 + down * 0.6).normalized()
    for k in range(1, fine):
        t = k / (fine - 1)
        direction = (direction * (1 - sp["droop"]) + down * sp["droop"]).normalized()
        cand = pts[-1] + direction * ds
        cand = _push_out(bvh, cand, radius(t) + sp["clearance_m"])
        cand = pts[-1] + (cand - pts[-1]).normalized() * ds
        direction = (cand - pts[-1]).normalized()
        pts.append(cand)
    centre, length = _resample([tuple(p) for p in pts], n)
    # rings along a finer resample, parallel-transported frames
    ringc, _ = _resample(centre, 3 * n)
    m = sp["ring"]
    tangents = np.gradient(ringc, axis=0)
    tangents /= np.linalg.norm(tangents, axis=1)[:, None]
    ref = Vector((1.0, 0.0, 0.0))
    grid, frames = [], []
    t0 = Vector(tangents[0])
    b0 = (ref - t0 * ref.dot(t0)).normalized()
    for k in range(len(ringc)):
        tk = Vector(tangents[k])
        b0 = (b0 - tk * b0.dot(tk)).normalized()
        c0 = tk.cross(b0)
        t = k / (len(ringc) - 1)
        rad = radius(t)
        row = []
        for j in range(m):
            ph = 2 * math.pi * j / m
            pos = Vector(ringc[k]) + b0 * (rad * math.cos(ph)) + c0 * (rad * sp["depth"] * math.sin(ph))
            row.append(bm.verts.new(pos))
        grid.append(row)
        frames.append(t)
    v0, v1 = sp["v"]
    k_ring = max(1, round(2 * math.pi * r_peak / tile))
    faces = 0
    for f, corners in _grid_faces(bm, grid, closed_u=True):
        for loop, (i, j) in zip(f.loops, corners):
            loop[uv].uv = (j / m * k_ring, v0 + (v1 - v0) * frames[i])
        f.smooth = True
        faces += 1
    for row, t_end, vv, flip in ((grid[0], ringc[0] - tangents[0] * 0.002, v0 - 0.01, True),
                                 (grid[-1], ringc[-1] + tangents[-1] * r_tip, 0.995, False)):
        tip = bm.verts.new(Vector(t_end))
        for j in range(m):
            tri = [row[j], row[(j + 1) % m], tip]
            if flip:
                tri.reverse()
            f = bm.faces.new(tri)
            ring_v = v0 if flip else v1
            for loop in f.loops:
                jj = j if loop.vert is row[j] else j + 1
                loop[uv].uv = ((jj if loop.vert is not tip else j + 0.5) / m * k_ring,
                               vv if loop.vert is tip else ring_v)
            f.smooth = True
            faces += 1
    radii = [round(radius(i / (n - 1)), 4) for i in range(n)]
    return centre, length, radii, faces


def _curtain(bm, uv, lm, sp, bvh, tile):
    """Long hair down the back: a thick sheet `width_m` across, hanging from inside the fall, lying on the
    head, neck and back from behind (each point as far back as the body above it, plus clearance)."""
    ez, h, cy = lm["eye"][2], lm["h"], lm["cy"]
    ncol, nrow = sp["columns"], sp["rows"]
    z0 = ez + sp["root_h"] * h
    L = sp["length_m"]
    s = np.linspace(0.0, 1.0, nrow)
    back = Vector((0.0, 1.0, 0.0))
    xs = np.zeros((nrow, ncol))
    ys = np.zeros((nrow, ncol))
    floor_y = np.full((nrow, ncol), -1.0)          # the least y each point may take: skin + clearance + thickness
    for i, t in enumerate(s):
        half = sp["width_m"] / 2 * (1 - sp["tip_narrow"] * t)
        xs[i] = np.linspace(-half, half, ncol) * (1 + 0.0 * t)
    zs = z0 - L * s
    # the body's back surface under each point; where a ray passes beside the neck it takes the nearest column's
    # that hit, so the curtain's corners do not fold forward into the gap beside the neck
    surf = np.full((nrow, ncol), np.nan)
    for j in range(ncol):
        for i in range(nrow):
            loc, _n, _k, _dist = bvh.ray_cast(Vector((xs[i, j], cy + 0.5, zs[i])), -back, 0.6)
            if loc is not None:
                surf[i, j] = loc.y
                floor_y[i, j] = loc.y + sp["clearance_m"] + sp["thick_m"]
    for i in range(nrow):
        hit = np.nonzero(~np.isnan(surf[i]))[0]
        if len(hit):
            for j in np.nonzero(np.isnan(surf[i]))[0]:
                surf[i, j] = surf[i, hit[np.argmin(np.abs(hit - j))]]
        else:
            surf[i] = surf[i - 1] if i else cy
    for j in range(ncol):
        prev = -1.0
        for i in range(nrow):
            prev = max(prev, surf[i, j] + sp["clearance_m"] + sp["thick_m"])
            ys[i, j] = prev
    for _ in range(2):
        ys[:, 1:-1] = 0.25 * ys[:, :-2] + 0.5 * ys[:, 1:-1] + 0.25 * ys[:, 2:]
    ys = np.maximum.accumulate(ys, axis=0)
    # curl the edges forward a little, round the head and back
    curl = sp.get("edge_curl_m", 0.012) * (xs / (sp["width_m"] / 2)) ** 2
    curl = np.minimum(curl, np.maximum(ys - floor_y, 0.0))     # never curled into the body
    outer, inner = [], []
    for i in range(nrow):
        orow, irow = [], []
        for j in range(ncol):
            orow.append(bm.verts.new(Vector((xs[i, j], ys[i, j] - curl[i, j], zs[i]))))
            irow.append(bm.verts.new(Vector((xs[i, j], ys[i, j] - curl[i, j] - sp["thick_m"], zs[i]))))
        outer.append(orow)
        inner.append(irow)
    v0, v1 = sp["v"]

    def u_of(i, j):
        return xs[i, j] / tile

    faces = 0
    # columns run toward -X, which seen from behind is left to right: the outer sheet faces +Y as built
    for grid, flip in ((outer, False), (inner, True)):
        for f, corners in _grid_faces(bm, grid, flip=flip):
            for loop, (i, j) in zip(f.loops, corners):
                loop[uv].uv = (u_of(i, j), v0 + (v1 - v0) * s[i])
            f.smooth = True
            faces += 1
    for (i, flip) in ((nrow - 1, False), (0, True)):
        for j in range(ncol - 1):
            quad = [outer[i][j], outer[i][j + 1], inner[i][j + 1], inner[i][j]]
            if flip:
                quad.reverse()
            f = bm.faces.new(quad)
            for loop in f.loops:
                jj = j if loop.vert in (outer[i][j], inner[i][j]) else j + 1
                # across the rim V steps from the sheet's end to just past it, so the rim has a tangent
                end = (v1, 0.992) if i else (v0, v0 - 0.01)
                loop[uv].uv = (u_of(i, jj), end[0] if loop.vert in (outer[i][j], outer[i][j + 1]) else end[1])
            f.smooth = True
            faces += 1
    for j, flip in ((0, False), (ncol - 1, True)):
        for i in range(nrow - 1):
            quad = [outer[i][j], outer[i + 1][j], inner[i + 1][j], inner[i][j]]
            if flip:
                quad.reverse()
            f = bm.faces.new(quad)
            for loop in f.loops:
                ii = i if loop.vert in (outer[i][j], inner[i][j]) else i + 1
                loop[uv].uv = (u_of(ii, j), v0 + (v1 - v0) * s[ii])
            f.smooth = True
            faces += 1
    mid = ncol // 2
    line = [tuple((Vector(outer[i][mid].co) + Vector(inner[i][mid].co)) / 2) for i in range(nrow)]
    centre, length = _resample(line, sp["points"])
    radii = [round(sp["thick_m"] / 2, 4)] * sp["points"]
    return centre, length, radii, faces


# ------------------------------------------------------------------------------------------ objects

def _object(name, bm, body, rig, weights):
    """weights: {group: per-vertex numpy array} (bm vertex order)."""
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    me = bpy.data.meshes.new(name)
    inv = body.matrix_world.inverted()
    for v in bm.verts:
        v.co = inv @ v.co
    bm.normal_update()
    bm.to_mesh(me)
    ob = bpy.data.objects.new(name, me)
    for coll in body.users_collection:
        coll.objects.link(ob)
    ob.matrix_world = body.matrix_world.copy()
    for group, w in weights.items():
        vg = ob.vertex_groups.new(name=group)
        for i, x in enumerate(w):
            if x > 1e-4:
                vg.add([i], float(x), "REPLACE")
    if rig is not None:
        ob.parent = rig
        ob.matrix_parent_inverse = rig.matrix_world.inverted()
        mod = ob.modifiers.new("Armature", "ARMATURE")
        mod.object = rig
    return ob


def _material(name, colour, uv_name, look=None):
    """lookdev's hair material; `look` is the preset's overrides of lookdev's `hair` strand settings (short_crop's
    feathered hairline)."""
    try:
        from lookdev_blender import hair as ld_hair
    except ImportError:
        ld_hair = None
    if ld_hair is not None:
        mat, rep = ld_hair.material(name, colour, uv_map=uv_name, **(look or {}))
        return mat, dict(rep, source="lookdev"), rep["tile_m"]
    mat = look.material(name, srgb=colour, roughness=0.45)
    return mat, {"material": mat.name, "source": "flat (lookdev_blender not importable)"}, TILE_M


def _clearance(bvh, verts, samples=400):
    """Smallest signed distance (m) of vertices from the body surface: negative is inside the skin."""
    if not verts:
        return None
    step = max(1, len(verts) // samples)
    worst = 1.0
    for v in verts[::step]:
        hit = bvh.find_nearest(v)
        if hit[0] is None:
            continue
        off = v - hit[0]
        worst = min(worst, off.length if off.dot(hit[1]) >= 0 else -off.length)
    return round(worst, 5)


def add(body, preset=None, colour=None, sheet=None, name=None, brows=False, lashes=False, body_hair=False, sex=None,
        brow_shape=None, beard=None, beard_colour=None, beard_length=None, beard_volume=None, beard_braids=None,
        fringe=None, **overrides):
    """Hair on a baked body. `preset` and `colour` (a screen sRGB colour) default to `sheet["hair"]`, then
    `bun`-less `short_crop` and the preset's colour. Returns a report with the objects made.

    `brows`, `lashes` and `body_hair` add `humanform.brows`' layers in the hair colour darkened (off by default,
    so a build that does not ask is unchanged); `sex` ("male" / "female", else the sheet's) picks the body hair
    regions. `brow_shape` (else the brief's `hair.brow_shape`, else "natural": the brow card as MPFB fits it) is
    one of `brows.BROW_SHAPES`. `beard` (else the brief's `hair.beard`; None: none) is one of
    `brows.BEARD_STYLES`, in `beard_colour` (a screen colour; None: the hair colour a little darker), with the
    style's length at the chin and volume unless `beard_length` (m) or `beard_volume` (0..1) say, and
    `beard_braids` ropes wound out of a hanging beard. A beard that hangs leaves `objects["beard_strand"]`,
    which carries follow-through's strand contract and must not be joined into the body. `fringe`
    (else the brief's `hair.fringe`) hangs a fringe across the forehead: True for FRINGE, or a dict over it."""
    ob = _body.obj(body)
    brief = (sheet or {}).get("hair") or {}
    brow_shape = brow_shape or brief.get("brow_shape")
    beard = beard or brief.get("beard")
    beard_braids = beard_braids if beard_braids is not None else brief.get("beard_braids")
    fringe = fringe if fringe is not None else brief.get("fringe")
    preset = preset or brief.get("preset") or "short_crop"
    p = params(preset, **overrides)
    colour = tuple(colour if colour is not None else brief.get("colour") or p["colour"])
    base = name or (ob.name[:-5] if ob.name.endswith("_body") else ob.name)
    lm = landmarks(ob)
    lm["scale"] = head_scale(lm)
    if lm["scale"] != 1.0:
        p = scale_lengths(p, lm["scale"])
    if not p.get("ear_cut", True):
        # measured but not cut round (a control: what the cap did before it knew where the ears were)
        lm["_ear_kd"] = None
    rig = _body.rig_of(ob)
    bvh = _bvh(lm["_co"], ob, lm["_eye_vertices"])
    uv_name = ob.data.uv_layers.active.name if ob.data.uv_layers.active else "UVMap"
    mat, mat_rep, tile = _material(f"{base}_hair", colour, uv_name, p.get("look"))

    centre = Vector(lm["centre"])
    targets = {}
    surface = {}
    for part in ("bun", "tie"):
        if part in p["parts"]:
            spec = p[part]
            direction = _dir(spec["azimuth"], spec["elevation"])
            loc, normal = _surface_point(bvh, centre, direction)
            surface[part] = (loc, normal)
            targets[part] = loc
    p["_targets"] = targets

    bm, cap_rep, _cap_data = _cap(ob, lm, p, bvh, uv_name, tile)
    uv = bm.loops.layers.uv[uv_name]
    for f in bm.faces:
        f.smooth = True
    cap_verts = [v.co.copy() for v in bm.verts]
    report = {"preset": preset, "colour": list(colour), "landmarks": {k: v for k, v in lm.items()
              if not k.startswith("_")}, "cap": cap_rep, "material": mat_rep, "parts": {}}
    cap_thick = p["cap_thick_m"]
    if "bun" in p["parts"]:
        spec = p["bun"]
        loc, normal = surface["bun"]
        faces, length = _coil(bm, uv, loc + normal * (cap_thick * 0.5), normal, spec, tile)
        report["parts"]["bun"] = {"faces": faces, "centre": [round(x, 4) for x in loc], "coil_length_m": round(length, 4),
                                  "outer_radius_m": spec["radius_m"]}
    if "tie" in p["parts"]:
        spec = p["tie"]
        loc, normal = surface["tie"]
        c = loc + normal * (cap_thick + spec["minor_m"] * 0.6)
        tie_axis = (normal * 0.8 + Vector((0, 0, -0.6))).normalized()
        faces = _torus(bm, uv, c, tie_axis, spec["major_m"], spec["minor_m"], spec["segments"], tile, (0.48, 0.52),
                       spiral=False)
        report["parts"]["tie"] = {"faces": faces, "centre": [round(x, 4) for x in c]}
    if "fall" in p["parts"]:
        report["parts"]["fall"] = _fall(bm, uv, lm, p, bvh, tile)
    if fringe:
        fp = scale_lengths(dict(FRINGE, **(fringe if isinstance(fringe, dict) else {})), lm["scale"])
        report["parts"]["fringe"] = _fringe(bm, uv, lm, p, bvh, tile, fp)
    for f in bm.faces:
        f.material_index = 0
    head = lm["head_bone"]
    hair_ob = _object(f"{base}_hair", bm, ob, rig, {head: np.ones(len(bm.verts))})
    bm.free()
    hair_ob.data.materials.append(mat)
    hair_ob["humanform_hair"] = {"preset": preset, "part": "rigid"}
    objects = {"hair": hair_ob.name}
    if brows or lashes or body_hair or beard:
        face = _brows.add(ob, lm, colour, base, rig=rig, uv_name=uv_name, brows=brows, lashes=lashes,
                          body_hair=body_hair, sex=sex or (sheet or {}).get("sex"), brow_shape=brow_shape,
                          beard=beard, beard_colour=beard_colour, beard_length=beard_length,
                          beard_volume=beard_volume, beard_braids=beard_braids)
        objects.update(face["objects"])
        report["face"] = {"parts": face["parts"], "skipped": face["skipped"]}
    # the cap's clearance: a fall's inner sheet and the underside of a bun or tie are tucked under the cap and
    # into the scalp on purpose, so only the cap is measured here
    report["hair"] = {"verts": len(hair_ob.data.vertices), "faces": len(hair_ob.data.polygons),
                      "cap_min_clearance_m": _clearance(bvh, cap_verts)}

    if "strand" in p["parts"]:
        sp = p["strand"]
        sbm = bmesh.new()
        suv = sbm.loops.layers.uv.new(uv_name)
        if sp["kind"] == "tube":
            loc, normal = surface["tie"]
            root = loc + normal * (cap_thick + p["tie"]["minor_m"] * 0.4)
            centre_line, length, radii, faces = _tube(sbm, suv, root, normal, sp, bvh, tile)
        else:
            centre_line, length, radii, faces = _curtain(sbm, suv, lm, sp, bvh, tile)
        sbm.verts.index_update()
        # share of the length for each vertex: its projection onto the centreline
        cl = np.asarray(centre_line)
        seg = np.linalg.norm(np.diff(cl, axis=0), axis=1)
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        share = np.zeros(len(sbm.verts))
        for v in sbm.verts:
            pt = np.array(tuple(v.co))
            best, best_s = 1e9, 0.0
            for k in range(len(cl) - 1):
                a_, b_ = cl[k], cl[k + 1]
                ab = b_ - a_
                tt = float(np.clip(np.dot(pt - a_, ab) / max(np.dot(ab, ab), 1e-12), 0, 1))
                dist = float(np.linalg.norm(pt - (a_ + tt * ab)))
                if dist < best:
                    best, best_s = dist, (cum[k] + tt * seg[k]) / cum[-1]
            share[v.index] = best_s
        # below its root, which is gathered into the tie or tucked under the fall
        strand_verts = [v.co.copy() for v in sbm.verts if share[v.index] > 0.15]
        weights = {"ft_strand": np.maximum(share, 1e-3)}
        bones = rig.data.bones if rig is not None else None
        neck = bones[head].parent if bones is not None and head in bones else None
        chest = neck.parent if neck is not None else None
        a_ = _smooth(0.1, 0.6, share)
        b_ = _smooth(0.5, 1.0, share)
        if neck is not None and chest is not None:
            weights[head] = 1 - a_
            weights[neck.name] = a_ * (1 - b_)
            weights[chest.name] = a_ * b_
        elif neck is not None:
            weights[head] = 1 - a_
            weights[neck.name] = a_
        else:
            weights[head] = np.ones(len(share))
        inv = ob.matrix_world.inverted()
        strand_ob = _object(f"{base}_hair_strand", sbm, ob, rig, weights)
        sbm.free()
        strand_ob.data.materials.append(mat)
        local = [tuple(inv @ Vector(c)) for c in centre_line]
        strand_ob["ft_type"] = "strand"
        strand_ob["ft_root_bone"] = head
        strand_ob["ft_centreline"] = [round(float(x), 5) for pt in local for x in pt]
        strand_ob["ft_length_m"] = round(length, 4)
        strand_ob["ft_strand_type"] = sp["type"]
        strand_ob["ft_radius_m"] = radii
        strand_ob["humanform_hair"] = {"preset": preset, "part": "strand", "kind": sp["kind"]}
        objects["strand"] = strand_ob.name
        report["parts"]["strand"] = {"kind": sp["kind"], "faces": faces, "verts": len(strand_ob.data.vertices),
                                     "length_m": round(length, 4), "root": [round(x, 4) for x in centre_line[0]],
                                     "tip": [round(x, 4) for x in centre_line[-1]],
                                     "min_clearance_m": _clearance(bvh, strand_verts),     # below 15% of its length
                                     "weights": sorted(weights)}
        report["contract"] = contract(strand_ob)
    # the hair carries only its own UV map: a body UV layer that reached a part (the skin's `hf_detail`)
    # would otherwise become its active map and the strand texture would sample the body's UVs
    for _n in objects.values():
        _me = bpy.data.objects[_n].data
        for _layer in [u.name for u in _me.uv_layers if u.name != uv_name]:
            _me.uv_layers.remove(_me.uv_layers[_layer])
        if uv_name in _me.uv_layers:
            _me.uv_layers.active = _me.uv_layers[uv_name]
            _me.uv_layers[uv_name].active_render = True
    report["objects"] = objects
    return report


def contract(strand):
    """The follow-through strand contract as `strand` carries it, checked. {passed, problems, ...}."""
    ob = _body.obj(strand)
    problems = []
    if ob.get("ft_type") != "strand":
        problems.append(f"ft_type is {ob.get('ft_type')!r}, not 'strand'")
    rig = _body.rig_of(ob)
    root = ob.get("ft_root_bone")
    if not root:
        problems.append("no ft_root_bone")
    elif rig is not None and root not in rig.data.bones:
        problems.append(f"ft_root_bone {root!r} is not a bone of {rig.name}")
    flat = list(ob.get("ft_centreline") or [])
    if len(flat) < 6 or len(flat) % 3:
        problems.append("ft_centreline must be a flat [x, y, z, ...] list of at least two points")
    pts = np.array(flat, np.float64).reshape(-1, 3) if flat and len(flat) % 3 == 0 else np.zeros((0, 3))
    g = ob.vertex_groups.get("ft_strand")
    order = None
    if g is None:
        problems.append("no ft_strand vertex group")
    elif len(pts) >= 2:
        w = _weights(ob, "ft_strand")
        co = np.empty(len(ob.data.vertices) * 3, np.float32)
        ob.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        near_root = w < 0.1
        near_tip = w > 0.9
        if near_root.any() and near_tip.any():
            d_root = float(np.linalg.norm(co[near_root].mean(axis=0) - pts[0]))
            d_tip = float(np.linalg.norm(co[near_tip].mean(axis=0) - pts[-1]))
            order = {"root_group_to_first_point_m": round(d_root, 4), "tip_group_to_last_point_m": round(d_tip, 4)}
            if d_root > d_tip + 0.05 or d_tip > 0.1:
                problems.append("ft_strand weights do not run from the first centreline point to the last")
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1) if len(pts) >= 2 else np.zeros(0)
    return {"passed": not problems, "problems": problems, "ft_type": ob.get("ft_type"), "ft_root_bone": root,
            "points": len(pts), "length_m": round(float(seg.sum()), 4),
            "spacing_m": [round(float(seg.min()), 4), round(float(seg.max()), 4)] if len(seg) else None,
            "order": order}
