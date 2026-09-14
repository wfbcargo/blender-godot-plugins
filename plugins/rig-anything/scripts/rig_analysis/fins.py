"""Fins: find them on the skin, give them ray bones, and pose them.

A fish arrives as a mesh. Its fins are the parts of the skin that are a SHEET
- millimetres thick on a body centimetres deep - and where each one attaches
and which way its sheet faces says what it is. `wings` recognises a sheet by
the principal spreads of the skin a limb's bones hold; a fin has no bones yet,
so thickness is measured per vertex instead: a ray cast inward along the
vertex normal crosses the whole body where the skin is body, and a few
millimetres where it is fin.

RECOGNITION
-----------

- thickness per vertex, inward along the normal
- the threshold between fin and body is found, not assumed: Otsu's split of
  log thickness, the two populations being that far apart
- connected fin vertices are one fin; it is classified by its base (where it
  meets body skin) and its sheet normal:

      caudal    median, at the rear end of the body core
      dorsal    median, base above the body axis
      anal      median, base below the axis, behind mid-body
      keel      median, below the axis, in front of mid-body
      pectoral  paired, the frontmost pair
      pelvic    paired, behind the pectorals and below the axis
      flukes    a caudal fin whose sheet is horizontal - a whale's

RIGGING
-------

`build_fish` makes an armature from the mesh when there is none: a head, a
spine through the centres of the body's cross-sections, and for every fin a fan
of ray bones from its base to its edge - the lepidotrichia a real fin folds and
spreads on. `build_rays` adds the fans to an armature that already has a body.
Every ray is tagged (`fin_role`) and left out of the body map's spine.

POSING
------

Per fin, like a wing's state: `fold` (0 as modelled, 1 laid back along the
body), `fan` (spread of the rays about their mean), `stroke` (out of the sheet
plane - a pectoral's abduction, a caudal fin's lag), `cup` (extra stroke toward
the fin's edges, the caudal cupping) and `twist`.
"""

from __future__ import annotations

import json
import math
import re

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

PROP = "rig_anything_fins"
ROLE = "fin_role"
NAME = re.compile(r"(^|[._\-])fin|fluke|lepidotrich|ray_", re.I)
WEIGHTS = "rig_anything_fin_weights:"

# Rays per fin: the base divided by this share of the fin's length, clamped.
RAYS = {"caudal": (3, 5), "flukes": (3, 5), "dorsal": (2, 5), "anal": (2, 4), "keel": (2, 3),
        "pectoral": (2, 4), "pelvic": (2, 3)}


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _v(x):
    return [round(float(c), 6) for c in x]


def _axes(forward, up):
    from .bodymap import axis_vector
    fwd = axis_vector(forward)
    upv = axis_vector(up)
    lat = upv.cross(fwd).normalized()
    return fwd, upv, lat


def _pca(points):
    import numpy as np
    a = np.array([tuple(p) for p in points])
    c = a.mean(axis=0)
    w, v = np.linalg.eigh(np.cov((a - c).T))
    return Vector(c), [max(float(x), 0.0) for x in w], [Vector(tuple(v[:, i])) for i in range(3)]


def _otsu(values, bins=64):
    """Threshold between two populations of `values`."""
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return hi
    hist = [0] * bins
    for x in values:
        hist[min(bins - 1, int((x - lo) / (hi - lo) * bins))] += 1
    total = len(values)
    sum_all = sum(i * h for i, h in enumerate(hist))
    best, best_t, w0, sum0 = -1.0, 0, 0, 0.0
    for i in range(bins):
        w0 += hist[i]
        if w0 == 0 or w0 == total:
            continue
        sum0 += i * hist[i]
        m0 = sum0 / w0
        m1 = (sum_all - sum0) / (total - w0)
        var = w0 * (total - w0) * (m0 - m1) ** 2
        if var > best:
            best, best_t = var, i
    return lo + (best_t + 1) * (hi - lo) / bins


# --------------------------------------------------------------------------
# detection
# --------------------------------------------------------------------------

def _mesh_space(mesh_obj, rig):
    """Vertex positions and normals in the space the rig will live in."""
    m = (rig.matrix_world.inverted() @ mesh_obj.matrix_world) if rig else mesh_obj.matrix_world
    n3 = m.to_3x3().inverted().transposed()
    me = mesh_obj.data
    cos = [m @ v.co for v in me.vertices]
    nors = [(n3 @ v.normal).normalized() for v in me.vertices]
    return cos, nors


def detect(mesh_name, forward="-Y", up="Z", rig_name=None, min_share=0.004):
    """Find the fins on a mesh. Works bound or not; coordinates are the rig's
    space when `rig_name` is given, else world."""
    obj = bpy.data.objects.get(mesh_name)
    if obj is None or obj.type != "MESH":
        return {"error": "no mesh named %r" % mesh_name}
    rig = bpy.data.objects.get(rig_name) if rig_name else None
    me = obj.data
    cos, nors = _mesh_space(obj, rig)
    n = len(cos)
    fwd, upv, lat = _axes(forward, up)
    polys = [tuple(p.vertices) for p in me.polygons]
    tree = BVHTree.FromPolygons(cos, polys, epsilon=0.0)
    us = [c.dot(fwd) for c in cos]
    L = max(us) - min(us)
    eps = 1e-5 * L

    # 1. thickness: inward along the normal to the next surface
    thick = []
    for co, nv in zip(cos, nors):
        hit = tree.ray_cast(co - nv * eps * 4.0, -nv, L)
        thick.append((hit[0] - co).length if hit[0] is not None else L)
    logs = [math.log(max(t, 1e-6 * L)) for t in thick]
    thr = math.exp(_otsu(logs))
    thr = max(0.003 * L, min(0.04 * L, thr))
    fin = [t < thr for t in thick]

    nbr = [[] for _ in range(n)]
    for e in me.edges:
        a, b = e.vertices
        nbr[a].append(b)
        nbr[b].append(a)
    # one smoothing pass: a vertex goes with most of its neighbours
    fin = [(sum(fin[j] for j in nbr[i]) * 2 > len(nbr[i])) if nbr[i] else fin[i] for i in range(n)]

    def core_of(fin_now):
        """Cross-sections of the body's non-fin skin: centre and half extents
        per station, from percentiles so a few stray rim vertices do not
        widen them, and ends where stations still hold skin."""
        ids = [i for i in range(n) if not fin_now[i]]
        if len(ids) < 0.2 * n:
            return None
        # The body is the largest connected run of non-fin skin. A rim vertex
        # left along a fin's edge is cut off from it by fin, whatever its own
        # ray read; counted, they carried the core's end into the tail fin.
        seen_b = [False] * n
        best = []
        for i0 in ids:
            if seen_b[i0]:
                continue
            stack, comp_b = [i0], []
            seen_b[i0] = True
            while stack:
                v = stack.pop()
                comp_b.append(v)
                for j in nbr[v]:
                    if not fin_now[j] and not seen_b[j]:
                        seen_b[j] = True
                        stack.append(j)
            if len(comp_b) > len(best):
                best = comp_b
        ids = best
        lo_all, hi_all = min(us[i] for i in ids), max(us[i] for i in ids)
        counts = [0] * 60
        for i in ids:
            counts[min(59, int((us[i] - lo_all) / max(hi_all - lo_all, 1e-12) * 60))] += 1
        enough = 0.1 * sorted(counts)[len(counts) // 2]
        k0 = next(k for k in range(60) if counts[k] >= enough)
        k1 = next(k for k in range(59, -1, -1) if counts[k] >= enough)
        a0 = lo_all + (hi_all - lo_all) * k0 / 60.0
        a1 = lo_all + (hi_all - lo_all) * (k1 + 1) / 60.0
        ids = [i for i in ids if a0 <= us[i] <= a1]
        out = []
        for k in range(40):
            a = a0 + (a1 - a0) * k / 40.0
            b = a0 + (a1 - a0) * (k + 1) / 40.0
            sl = [i for i in ids if a <= us[i] <= b]
            if len(sl) < 4:
                continue
            hs = sorted(cos[i].dot(upv) for i in sl)
            ls = sorted(cos[i].dot(lat) for i in sl)
            q = lambda arr, t: arr[int(t * (len(arr) - 1))]
            out.append({"u": 0.5 * (a + b),
                        "h": 0.5 * (q(hs, 0.05) + q(hs, 0.95)), "l": 0.5 * (q(ls, 0.05) + q(ls, 0.95)),
                        "half_h": 0.5 * (q(hs, 0.95) - q(hs, 0.05)),
                        "half_w": 0.5 * (q(ls, 0.95) - q(ls, 0.05))})
        return a0, a1, ids, out

    def inside(rows_, a0, a1, i, grow=1.0):
        u = us[i]
        if u < a0 - 0.02 * L or u > a1 + 0.02 * L:
            return False
        r = min(rows_, key=lambda r: abs(r["u"] - u))
        dh = (cos[i].dot(upv) - r["h"]) / max(r["half_h"], 1e-9)
        dl = (cos[i].dot(lat) - r["l"]) / max(r["half_w"], 1e-9)
        return dh * dh + dl * dl <= grow * grow

    # The rim. A vertex on a fin's edge has a normal lying IN the sheet, so its
    # inward ray runs the length of the fin and reads as body; the test fish's
    # spine ran into its tail fin on those, and its fin edges stayed on the
    # spine and folded. So grow each fin across its rim: a neighbour belongs if,
    # along the sheet's own normal, the skin either side is within the
    # threshold - or there is none, because it is the edge. Never into the body's
    # own cross-section: unguarded, the growth crept across the belly and joined
    # both pelvic fins to the anal fin.
    provisional = core_of(fin)
    if provisional is None:
        return {"error": "most of %s measured as sheet (threshold %.4f) - is it a flat object?"
                         % (mesh_name, thr)}
    for _ in range(10):
        grown = []
        for i in range(n):
            if fin[i] or inside(provisional[3], provisional[0], provisional[1], i, 1.05):
                continue
            fn = [j for j in nbr[i] if fin[j]]
            if not fn:
                continue
            ref = nors[fn[0]]
            sheet_n = Vector((0.0, 0.0, 0.0))
            for j in fn:
                sheet_n += nors[j] if nors[j].dot(ref) >= 0.0 else -nors[j]
            if sheet_n.length < 1e-9:
                continue
            sheet_n.normalize()
            span = 0.0
            for sgn in (1.0, -1.0):
                hit = tree.ray_cast(cos[i] + sheet_n * sgn * eps, sheet_n * sgn, 3.0 * thr)
                span += (hit[0] - cos[i]).length if hit[0] is not None else 0.0
            if span < thr:
                grown.append(i)
        if not grown:
            break
        for i in grown:
            fin[i] = True

    body_set = set(core_of(fin)[2]) if core_of(fin) else set()
    for i in range(n):
        if not fin[i] and i not in body_set and any(fin[j] for j in nbr[i]):
            fin[i] = True

    # 2. the body core
    core = core_of(fin)
    if core is None:
        return {"error": "most of %s measured as sheet (threshold %.4f) - is it a flat object?"
                         % (mesh_name, thr)}
    u0, u1, body_ids, rows = core
    midline = sum(r["l"] for r in rows) / len(rows)

    def core_at(u):
        best = min(rows, key=lambda r: abs(r["u"] - u))
        return best

    def in_core(i):
        return inside(rows, u0, u1, i, 1.3)

    # 3. fins: connected fin vertices
    seen = [False] * n
    comps = []
    for i in range(n):
        if not fin[i] or seen[i]:
            continue
        stack, comp = [i], []
        seen[i] = True
        while stack:
            v = stack.pop()
            comp.append(v)
            for j in nbr[v]:
                if fin[j] and not seen[j]:
                    seen[j] = True
                    stack.append(j)
        if len(comp) >= max(12, min_share * n):
            comps.append(comp)

    fins, warnings = [], []
    # loose parts are not fins: a tongue or baleen plate is thin and has no body
    from .maw import _components
    mcomp, msizes = _components(me)
    largest = max(msizes, key=msizes.get)
    # skin a wing or a maw already owns is not fin
    owned = set()
    if rig is not None:
        from . import bodymap
        bm = bodymap.build(rig.name, forward=forward, up=up)
        if "error" not in bm:
            claim = set(bm.get("maw_bones", []))
            for w in bm.get("wings", []):
                claim.update(bodymap._descendants_names(rig.data.bones[w["upper"]], w["side"]))
            if claim:
                groups = {g.index: g.name for g in obj.vertex_groups}
                for v in me.vertices:
                    ws = [(groups.get(g.group), g.weight) for g in v.groups]
                    tot = sum(w for _, w in ws) or 1.0
                    if sum(w for nme, w in ws if nme in claim) / tot >= 0.5:
                        owned.add(v.index)
    for comp in comps:
        if mcomp[comp[0]] != largest and msizes[mcomp[comp[0]]] < 0.2 * msizes[largest]:
            continue
        if sum(1 for i in comp if i in owned) * 2 > len(comp):
            continue
        pts = [cos[i] for i in comp]
        centre, lam, vecs = _pca(pts)
        normal = vecs[0].normalized()
        # The base is where the fin meets BODY: skin inside the core's cross-
        # section. Any non-fin neighbour counted, a rim vertex left over on a
        # lobe made the tail fin's "base" run round its outline and its rays
        # stood along the edge.
        base = [i for i in comp if any(not fin[j] and in_core(j) for j in nbr[i])]
        if not base:
            base = [i for i in comp if any(not fin[j] for j in nbr[i])]
        if not base:
            warnings.append("a sheet of %d vertices touches no body - a loose flap, skipped" % len(comp))
            continue
        base_c = sum((cos[i] for i in base), Vector()) / len(base)
        side_l = centre.dot(lat) - midline
        core = core_at(base_c.dot(fwd))
        vertical = abs(normal.dot(lat)) > 0.7
        horizontal = abs(normal.dot(upv)) > 0.7
        crosses = (min(cos[i].dot(lat) for i in comp) - midline < -0.25 * core["half_w"]
                   and max(cos[i].dot(lat) for i in comp) - midline > 0.25 * core["half_w"])
        median = crosses or abs(side_l) < 0.35 * max(core["half_w"], 1e-6)
        bu = base_c.dot(fwd)
        bh = base_c.dot(upv) - core["h"]
        # where along the body: 0 at the rear of the core, 1 at its front
        along = (bu - u0) / max(u1 - u0, 1e-9)
        rear = min(along, 1.0 - along) == along       # nearer the u0 end
        tip_u = max(us[i] for i in comp)
        low_u = min(us[i] for i in comp)
        info = {"vertices": comp, "base": base, "centre": centre, "normal": normal,
                "base_centre": base_c, "spread": lam, "median": median,
                "side": None if median else ("L" if side_l > 0 else "R"),
                "vertical": vertical, "horizontal": horizontal,
                "base_u": bu, "base_h": bh, "u_range": (low_u, tip_u)}
        ext = max(pts, key=lambda p: (p - base_c).length)
        info["length"] = (ext - base_c).length
        along_head = (bu - u0) / max(u1 - u0, 1e-9)     # 0 tail end .. 1 head end
        info["along"] = along_head
        if info["length"] < 0.05 * L:
            warnings.append("a %d-vertex sheet %.3f long at %.0f%% of the body is too small "
                            "to be a fin - skipped" % (len(comp), info["length"], 100 * along_head))
            continue
        if median and along_head > 0.8:
            warnings.append("a median sheet in the front fifth of the body (lips, a crest?) - "
                            "not a fin, skipped")
            continue
        fins.append(info)

    # classify
    paired = sorted([f for f in fins if not f["median"]], key=lambda f: -f["along"])
    for f in fins:
        if f["median"]:
            if f["along"] < 0.15 or f["u_range"][0] < u0 + 0.02 * L:
                f["kind"] = "flukes" if f["horizontal"] else "caudal"
            elif f["base_h"] > 0.0:
                f["kind"] = "dorsal"
            else:
                f["kind"] = "anal" if f["along"] < 0.5 else "keel"
    if paired:
        front = max(f["along"] for f in paired)
        for f in paired:
            core = core_at(f["base_u"])
            if f["along"] >= front - 0.05:
                f["kind"] = "pectoral"
            elif f["base_h"] < -0.3 * core["half_h"]:
                f["kind"] = "pelvic"
            else:
                f["kind"] = "pectoral"
    counts = {}
    for f in sorted(fins, key=lambda f: -f["along"]):
        key = (f["kind"], f["side"])
        counts[key] = counts.get(key, 0) + 1
        f["index"] = counts[key]
        f["name"] = "fin_%s%s%s" % (f["kind"], "" if counts[key] == 1 else "_%d" % counts[key],
                                    ("." + f["side"]) if f["side"] else "")
    pairs = {}
    for f in fins:
        if f["side"]:
            pairs.setdefault((f["kind"], f["index"]), {})[f["side"]] = f
    for key, pr in pairs.items():
        if len(pr) != 2:
            warnings.append("%s has no mirror partner" % "/".join(x["name"] for x in pr.values()))
        elif abs(pr["L"]["length"] - pr["R"]["length"]) > 0.15 * max(pr["L"]["length"], pr["R"]["length"]):
            warnings.append("%s and %s differ in length by more than 15%%" % (pr["L"]["name"], pr["R"]["name"]))

    return {"mesh": mesh_name, "rig": rig_name, "forward": forward, "up": up,
            "swims": "dorsoventral" if any(f["kind"] == "flukes" for f in fins) else "lateral",
            "fwd": fwd, "up_vec": upv, "lat": lat, "midline": midline,
            "length": L, "thickness_threshold": thr, "core": rows, "core_u": (u0, u1),
            "fins": fins, "fin_vertices": sum(len(f["vertices"]) for f in fins),
            "warnings": warnings}


def summary(d):
    if "error" in d:
        return "ERROR: " + d["error"]
    lines = ["%s: %.3f long, sheet under %.4f thick, %d fins, body waves %s"
             % (d["mesh"], d["length"], d["thickness_threshold"], len(d["fins"]), d["swims"])]
    for f in sorted(d["fins"], key=lambda f: -f["along"]):
        lines.append("  %-18s %4d verts  %.3f long  base at %3.0f%% of the body%s"
                     % (f["name"], len(f["vertices"]), f["length"], 100 * f["along"],
                        "  (horizontal)" if f["horizontal"] else ""))
    lines += ["  WARN " + w for w in d["warnings"]]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# building
# --------------------------------------------------------------------------

def _point(d, row):
    return d["fwd"] * row["u"] + d["up_vec"] * row["h"] + d["lat"] * row["l"]


def _resample(points, count):
    """`count`+1 points at equal arc length along a polyline."""
    cum = [0.0]
    for a, b in zip(points, points[1:]):
        cum.append(cum[-1] + (b - a).length)
    total = cum[-1]
    out = []
    for k in range(count + 1):
        s = total * k / count
        i = 0
        while i < len(cum) - 2 and cum[i + 1] < s:
            i += 1
        t = (s - cum[i]) / max(cum[i + 1] - cum[i], 1e-12)
        out.append(points[i].lerp(points[i + 1], max(0.0, min(1.0, t))))
    return out


def _fin_frame(d, f):
    """In-plane backward direction e1, e2 = n x e1, for a fin's sheet."""
    n = f["normal"]
    back = -d["fwd"] - n * (-d["fwd"]).dot(n)
    if back.length < 1e-6:
        back = d["up_vec"] - n * d["up_vec"].dot(n)
    e1 = back.normalized()
    return e1, n.cross(e1).normalized()


def _rays(d, f, cos):
    """[(base point, tip point)] fanned over a fin."""
    lo, hi = RAYS.get(f["kind"], (2, 4))
    n = f["normal"]
    e1, e2 = _fin_frame(d, f)
    base_pts = [cos[i] for i in f["base"]]
    bc = f["base_centre"]
    if len(base_pts) >= 4:
        _, _, vecs = _pca(base_pts)
        axis = vecs[2] - n * vecs[2].dot(n)
        axis = axis.normalized() if axis.length > 1e-9 else e1
    else:
        axis = e1
    ts = [(p - bc).dot(axis) for p in base_pts]
    base_len = (max(ts) - min(ts)) if ts else 0.0
    verts = [cos[i] for i in f["vertices"]]
    rays = []
    if base_len >= 0.5 * f["length"]:
        # a long base (a dorsal fin): rays stand along it
        k = max(lo, min(hi, int(round(base_len / (0.35 * f["length"]))) + 1))
        t0, t1 = min(ts), max(ts)
        half = 0.5 * (t1 - t0) / k
        for r in range(k):
            t = t0 + (t1 - t0) * (0.12 + 0.76 * r / max(k - 1, 1))
            bp = min(base_pts, key=lambda p: abs((p - bc).dot(axis) - t))
            strip = [p for p in verts if abs((p - bc).dot(axis) - t) <= half] or verts
            tip = max(strip, key=lambda p: (p - bp).length)
            rays.append((bp.copy(), tip.copy()))
    else:
        # a short base (a caudal or pectoral fin): rays fan out by angle
        ang = [math.atan2((p - bc).dot(e2), (p - bc).dot(e1)) for p in verts]
        a0, a1 = min(ang), max(ang)
        span = math.degrees(a1 - a0)
        k = max(lo, min(hi, int(round(span / 35.0)) + 1))
        width = 0.5 * (a1 - a0) / k
        for r in range(k):
            a = a0 + (a1 - a0) * (0.08 + 0.84 * r / max(k - 1, 1))
            strip = [p for p, g in zip(verts, ang) if abs(g - a) <= width] or verts
            tip = max(strip, key=lambda p: (p - bc).length)
            rays.append((bc.copy(), tip.copy()))
    return rays


def _edit(rig):
    from .maw import _edit as edit
    edit(rig)


def _store(rig, d, fins_out):
    rig.data[PROP] = json.dumps({
        "version": 1, "mesh": d["mesh"], "forward": d["forward"], "up": d["up"],
        "swims": d["swims"], "length": d["length"], "thickness_threshold": d["thickness_threshold"],
        "fins": fins_out})
    txt = bpy.data.texts.get(WEIGHTS + d["mesh"]) or bpy.data.texts.new(WEIGHTS + d["mesh"])
    txt.clear()
    txt.write(json.dumps({"n": len(bpy.data.objects[d["mesh"]].data.vertices),
                          "fins": {f["name"]: {"vertices": f["vertices"], "base": f["base"]}
                                   for f in d["fins"]}}))


def _add_rays(rig, d, cos, parent_of):
    """Create ray bones, in edit mode; returns the stored fin descriptions."""
    eb = rig.data.edit_bones
    out = []
    for f in d["fins"]:
        parent = parent_of(f)
        names = []
        base, _, side = f["name"].partition(".")
        for k, (bp, tip) in enumerate(_rays(d, f, cos)):
            name = "%s_ray%d%s" % (base, k + 1, ("." + side) if side else "")
            if name in eb:
                eb.remove(eb[name])
            b = eb.new(name)
            b.head = bp
            b.tail = bp + (tip - bp) * 0.97
            if (b.tail - b.head).length < 1e-6:
                b.tail = b.head + f["normal"].cross(d["fwd"]) * 0.01
            b.parent = eb[parent]
            b.use_connect = False
            b.use_deform = True
            b.align_roll(f["normal"])
            names.append(name)
        out.append({"name": f["name"], "kind": f["kind"], "side": f["side"], "parent": parent,
                    "rays": names, "normal": _v(f["normal"]), "horizontal": f["horizontal"],
                    "length": f["length"], "base_centre": _v(f["base_centre"]),
                    "along": f["along"]})
    return out


def build_fish(mesh_name, detection=None, rig_name=None, forward="-Y", up="Z",
               segments=8, head_share=0.24):
    """An armature for a fish-shaped mesh with no rig: head, spine through the
    body's cross-sections, and a fan of rays on every fin. Not bound - call
    `bind` next."""
    d = detection or detect(mesh_name, forward=forward, up=up)
    if "error" in d:
        return d
    obj = bpy.data.objects[mesh_name]
    rig_name = rig_name or mesh_name + "_rig"
    rows = sorted(d["core"], key=lambda r: -r["u"])            # head end first
    centre = [_point(d, r) for r in rows]
    u1, u0 = rows[0]["u"], rows[-1]["u"]
    snout = centre[0] + d["fwd"] * max(d["core_u"][1] - u1, 0.0)
    neck_u = u1 - head_share * (u1 - u0)
    body_pts = [p for p, r in zip(centre, rows) if r["u"] <= neck_u]
    neck = body_pts[0]
    tail_end = body_pts[-1] - d["fwd"] * max(u0 - d["core_u"][0], 0.0)
    joints = _resample(body_pts[:-1] + [tail_end], segments)
    old = bpy.data.objects.get(rig_name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    arm = bpy.data.armatures.new(rig_name)
    rig = bpy.data.objects.new(rig_name, arm)
    coll = obj.users_collection[0] if obj.users_collection else bpy.context.scene.collection
    coll.objects.link(rig)
    rig.matrix_world = Matrix.Identity(4)
    cos, _ = _mesh_space(obj, None)
    _edit(rig)
    eb = arm.edit_bones
    spine = []
    for k in range(segments):
        name = "spine" if k == 0 else "spine.%03d" % k
        b = eb.new(name)
        b.head, b.tail = joints[k], joints[k + 1]
        if spine:
            b.parent = eb[spine[-1]]
            b.use_connect = True
        b.align_roll(d["up_vec"])
        spine.append(name)
    h = eb.new("head")
    h.head, h.tail = neck, snout
    h.parent = eb["spine"]
    h.align_roll(d["up_vec"])
    axial = ["head"] + spine

    def parent_of(f):
        p = f["base_centre"]

        def dist(nm):
            a, b = eb[nm].head, eb[nm].tail
            ab = b - a
            t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.dot(ab), 1e-12)))
            return (p - (a + ab * t)).length
        return min(axial, key=dist)

    stored = _add_rays(rig, d, cos, parent_of)
    bpy.ops.object.mode_set(mode="OBJECT")
    for f in stored:
        for r in f["rays"]:
            rig.data.bones[r][ROLE] = f["kind"]
    _store(rig, d, stored)
    return {"rig": rig_name, "spine": axial, "fins": {f["name"]: f["rays"] for f in stored}}


def build_rays(rig_name, mesh_name, detection=None, forward="-Y", up="Z"):
    """Fans of rays on the fins of a mesh already bound to an armature (a whale's
    flukes and flippers), each parented to the bone that holds its base."""
    rig = bpy.data.objects[rig_name]
    unbuild(rig_name)
    d = detection or detect(mesh_name, forward=forward, up=up, rig_name=rig_name)
    if "error" in d:
        return d
    obj = bpy.data.objects[mesh_name]
    cos, _ = _mesh_space(obj, rig)
    groups = {g.index: g.name for g in obj.vertex_groups if g.name in rig.data.bones}

    def parent_of(f):
        votes = {}
        for i in f["base"]:
            ws = [(groups[g.group], g.weight) for g in obj.data.vertices[i].groups if g.group in groups]
            if ws:
                top = max(ws, key=lambda x: x[1])[0]
                votes[top] = votes.get(top, 0) + 1
        return max(votes, key=votes.get)

    _edit(rig)
    stored = _add_rays(rig, d, cos, parent_of)
    bpy.ops.object.mode_set(mode="OBJECT")
    for f in stored:
        for r in f["rays"]:
            rig.data.bones[r][ROLE] = f["kind"]
    _store(rig, d, stored)
    return {"rig": rig_name, "fins": {f["name"]: (f["parent"], f["rays"]) for f in stored}}


def _bound(rig):
    return [o for o in bpy.data.objects if o.type == "MESH" and any(
        m.type == "ARMATURE" and m.object == rig for m in o.modifiers)]


def unbuild(rig_name):
    """Remove fin rays this module added: their weights go back to each fin's
    parent bone, then the bones go."""
    rig = bpy.data.objects[rig_name]
    raw = rig.data.get(PROP)
    names = {b.name for b in rig.data.bones if b.get(ROLE)}
    if not names:
        return {"removed": []}
    parents = {}
    if raw:
        for f in json.loads(raw)["fins"]:
            for r in f["rays"]:
                parents[r] = f["parent"]
    for o in _bound(rig):
        groups = {g.name: g for g in o.vertex_groups}
        for nm in names:
            g = groups.get(nm)
            if g is None:
                continue
            p = groups.get(parents.get(nm, ""))
            if p is not None:
                for v in o.data.vertices:
                    w = next((x.weight for x in v.groups if x.group == g.index), 0.0)
                    if w > 0.0:
                        cur = next((x.weight for x in v.groups if x.group == p.index), 0.0)
                        p.add([v.index], cur + w, "REPLACE")
            o.vertex_groups.remove(g)
    _edit(rig)
    for nm in names:
        if nm in rig.data.edit_bones:
            rig.data.edit_bones.remove(rig.data.edit_bones[nm])
    bpy.ops.object.mode_set(mode="OBJECT")
    if PROP in rig.data:
        del rig.data[PROP]
    return {"removed": sorted(names)}


def bind(mesh_name, rig_name):
    """Bone heat for the body with the rays held out of it - a sheet a few
    millimetres thick is where bone heat is least reliable - then `skin`."""
    from . import skin as skin_mod
    rig = bpy.data.objects[rig_name]
    rays = [b for b in rig.data.bones if b.get(ROLE)]
    for b in rays:
        b.use_deform = False
    try:
        r = skin_mod.bind(mesh_name, rig_name)
    finally:
        for b in rays:
            b.use_deform = True
    if "error" in r:
        return r
    r["fins"] = skin(rig_name)
    return r


def skin(rig_name, root=0.3):
    """Weight each fin to its rays: shared between the two rays either side of a
    vertex (by angle for a fanned fin, by position along the base for a long
    one), fading in from the base over `root` of the fin's length so the fin
    stays joined to the body it grows from. Idempotent: ray weights are cleared
    back into the parent first."""
    rig = bpy.data.objects[rig_name]
    raw = rig.data.get(PROP)
    if not raw:
        return {"error": "%s has no fins - run fins.build_fish or build_rays" % rig_name}
    st = json.loads(raw)
    obj = bpy.data.objects[st["mesh"]]
    txt = bpy.data.texts.get(WEIGHTS + st["mesh"])
    if txt is None:
        return {"error": "fin vertex lists for %s are missing - rebuild" % st["mesh"]}
    ids = json.loads(txt.as_string())
    if ids["n"] != len(obj.data.vertices):
        return {"error": "%s has changed since its fins were found - rebuild" % st["mesh"]}
    cos, _ = _mesh_space(obj, rig)
    bones = rig.data.bones
    groups = {g.name: g for g in obj.vertex_groups}
    for f in st["fins"]:
        for r in f["rays"]:
            if r not in groups:
                groups[r] = obj.vertex_groups.new(name=r)
    ray_idx = {groups[r].index for f in st["fins"] for r in f["rays"]}
    name_of = {g.index: g.name for g in obj.vertex_groups}
    report = {}
    for f in st["fins"]:
        vid = ids["fins"][f["name"]]
        verts, base = vid["vertices"], vid["base"]
        base_set = set(base)
        rays = f["rays"]
        heads = [bones[r].head_local for r in rays]
        tips = [bones[r].tail_local for r in rays]
        n = Vector(f["normal"])
        base_pts = [cos[i] for i in base]
        changed = 0
        spread = max((h - heads[0]).length for h in heads)
        if spread > 0.3 * f["length"]:
            # rays stand along a long base: order them along it
            axis = (heads[-1] - heads[0]).normalized()
            keyf = lambda q, a=axis, o=heads[0]: (q - o).dot(a)
            keys = sorted((keyf(h), r) for h, r in zip(heads, rays))
        else:
            # a fan: order by angle about its centre, in the sheet
            o = sum(heads, Vector()) / len(heads)
            e1 = (tips[len(tips) // 2] - o)
            e1 = (e1 - n * e1.dot(n)).normalized()
            e2 = n.cross(e1)
            keyf = lambda q, o=o, e1=e1, e2=e2: math.atan2((q - o).dot(e2), (q - o).dot(e1))
            keys = sorted((keyf(t), r) for t, r in zip(tips, rays))
        for i in verts:
            p = cos[i]
            v = obj.data.vertices[i]
            old = {name_of[g.group]: g.weight for g in v.groups if g.group not in ray_idx}
            tot = sum(old.values()) or 1.0
            old = {k: w / tot for k, w in old.items()}
            # distance from the fin's base
            dist = min((p - b).length for b in base_pts) if base_pts else 0.0
            s = _smooth(dist / max(root * f["length"], 1e-9)) if i not in base_set else 0.0
            # the two rays either side of the vertex - by angle about the fan's
            # centre, or by position along a long base. The two NEAREST rays
            # flipped between neighbours (ray 3 with 4, then 3 with 2) and the
            # pectoral membrane stretched 10x as its rays folded apart.
            key = keyf(p)
            share = {}
            if key <= keys[0][0]:
                share[keys[0][1]] = 1.0
            elif key >= keys[-1][0]:
                share[keys[-1][1]] = 1.0
            else:
                for (ka, ra), (kb, rb) in zip(keys, keys[1:]):
                    if ka <= key <= kb:
                        t = (key - ka) / max(kb - ka, 1e-12)
                        share[ra] = 1.0 - t
                        share[rb] = share.get(rb, 0.0) + t
                        break
            new = {k: w * (1.0 - s) for k, w in old.items()}
            for r, w in share.items():
                new[r] = new.get(r, 0.0) + s * w
            for g in list(v.groups):
                if g.group in ray_idx:
                    obj.vertex_groups[g.group].remove([i])
            for k, w in new.items():
                if w > 1e-5:
                    groups[k].add([i], w, "REPLACE")
                elif k in groups and k not in rays:
                    groups[k].remove([i])
            changed += 1
        report[f["name"]] = {"vertices": changed, "rays": len(rays)}
    return report


def summarize_build(st):
    return "\n".join("  %-18s on %-10s %d rays" % (f, p, len(r)) for f, (p, r) in st.items())


# --------------------------------------------------------------------------
# posing
# --------------------------------------------------------------------------

REST_STATE = {"fold": 0.0, "fan": 1.0, "stroke": 0.0, "cup": 0.0, "twist": 0.0}


def state(**kw):
    s = dict(REST_STATE)
    s.update(kw)
    return s


def _wrap(a):
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def read(rig):
    raw = rig.data.get(PROP) if rig is not None else None
    if not raw:
        return None
    st = json.loads(raw)
    names = {b.name for b in rig.data.bones}
    for f in st["fins"]:
        if f["parent"] not in names or any(r not in names for r in f["rays"]):
            return None
    return st


class FinRig:
    """Rest measurements for every fin on a rig, and the pose maths.

    Each fin gets a frame from its rest sheet: n its normal - pointing away
    from the body for a paired fin, to +lat for a median one - e1 backward in
    the sheet, e2 = n x e1. A ray's in-plane angle is measured from e1, so
    `fold` 1 lays every ray back along the body whichever way it stood.
    """

    def __init__(self, body, stored=None):
        self.body = body
        rig = body.rig
        st = stored or read(rig)
        self.fins = []
        if not st:
            return
        bm = body.bm
        fwd, up, lat = bm["fwd"], bm["up_vec"], bm["lat"]
        bones = rig.data.bones
        for f in st["fins"]:
            n = Vector(f["normal"]).normalized()
            if f["side"]:
                out = lat if f["side"] == "L" else -lat
                ref = out if abs(n.dot(lat)) > 0.25 else up
            else:
                ref = lat if abs(n.dot(lat)) > 0.25 else up
            if n.dot(ref) < 0.0:
                n = -n
            back = -fwd - n * (-fwd).dot(n)
            if back.length < 1e-6:
                back = up - n * up.dot(n)
            e1 = back.normalized()
            e2 = n.cross(e1).normalized()
            rays = []
            for r in f["rays"]:
                b = bones[r]
                v = b.tail_local - b.head_local
                rays.append({"name": r, "head": b.head_local.copy(),
                             "theta": math.atan2(v.dot(e2), v.dot(e1)), "dir": v.normalized()})
            thetas = [x["theta"] for x in rays]
            mean = math.atan2(sum(math.sin(t) for t in thetas), sum(math.cos(t) for t in thetas))
            half = max(abs(_wrap(t - mean)) for t in thetas) or 1.0
            mdir = (e1 * math.cos(mean) + e2 * math.sin(mean)).normalized()
            self.fins.append(dict(f, n=n, e1=e1, e2=e2, rays_rest=rays, mean=mean, half=half,
                                  mdir=mdir, stroke_axis=mdir.cross(n).normalized()))   # +stroke toward +n

    def bones(self):
        return {r["name"] for f in self.fins for r in f["rays_rest"]}

    def by_kind(self, kind):
        return [f for f in self.fins if f["kind"] == kind]

    def pose(self, posed, states):
        """Overrides for every ray. `states` maps a fin name, or a kind, or "*",
        to a state; the most specific wins."""
        body = self.body
        out = {}
        for f in self.fins:
            s = dict(REST_STATE)
            for key in ("*", f["kind"], f["name"]):
                if key in states and states[key] is not None:
                    s.update(states[key])
            parent = f["parent"]
            C = posed[parent].to_3x3() @ body.rest[parent].to_3x3().inverted()
            n, sa, md = C @ f["n"], C @ f["stroke_axis"], C @ f["mdir"]
            for r in f["rays_rest"]:
                off = _wrap(r["theta"] - f["mean"])
                # fold 1 is as far as this fin's skin folds cleanly (`limits`)
                fold = s["fold"] * (f.get("fold_clean", 1.0) if s["fold"] > 0.0 else 1.0)
                inplane = fold * _wrap(0.0 - r["theta"]) + (s["fan"] - 1.0) * off
                outer = abs(off) / f["half"]
                stroke = math.radians(s["stroke"]) * (1.0 + s["cup"] * outer)
                R = (Matrix.Rotation(math.radians(s["twist"]), 3, md)
                     @ Matrix.Rotation(stroke, 3, sa)
                     @ Matrix.Rotation(inplane, 3, n) @ C)
                head = body.carried(posed, parent, r["head"])
                out[r["name"]] = (Matrix.Translation(head) @ R.to_4x4()
                                  @ Matrix.Translation(-r["head"]) @ body.rest[r["name"]])
        return out

    def tips(self, mats, kind=None):
        from .motion import tail_of
        return [(f["name"], tail_of(self.body, mats, r["name"]))
                for f in self.fins if kind in (None, f["kind"]) for r in f["rays_rest"]]
