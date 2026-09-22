"""Replace a limb pair with something else - for any creature (08 fantasy species, layer 5: the body plan).

    graft.validate({"legs": {"to": "tail", "length": 1.0, "fluke": {"span": 0.24}}}, absent=["knees", ...])
    rep = graft.apply(human, {"legs": {"to": "tail"}})        # on the unbaked, rigged, warped MPFB body

A human has no graft. A creature whose description replaces its legs with a tail (a merfolk, a naga, a lamia) is
the body above a seam and a lofted tail below it:

- **the seam** is a horizontal cut round the body at the hip joints (`seam`: metres above them). Every face below it
  that the legs or the pelvis carry goes (the hands hanging beside the thighs stay). The vertices are kept, loose,
  inside the tail and skinned to it, so hm08's vertex order - which brows, the skin regions and the lash fits read -
  is untouched; the exporter drops loose vertices.
- **the tail** is lofted from the seam's own vertex ring down to the floor (`length` 1: the tail reaches the floor
  as the legs did, standing). Each ring morphs from the seam's cross-section into an ellipse whose half width and
  depth follow `width` and `depth` (profiles over the tail's length, fractions of the seam's), narrowing to a
  peduncle, then flattens into a blade - the fluke - of `fluke.span` (body lengths: cetaceans 0.2-0.27
  [measured]), `fluke.chord` (of the span), its tips swept back by `fluke.sweep` and its trailing edge notched by
  `fluke.notch`. `fluke.plane` "horizontal" is a cetacean's (and a mermaid's in most art): the blade spans left
  to right; "vertical" is a fish's.
- **the rig**: the leg chains are removed and a chain of `bones` tail bones hangs off the pelvis down the tail
  (`tail.000` ...), each tail vertex weighted to the two nearest along it; skin the legs carried above the seam
  goes to the first tail bone. The rig's body profile is told (`rig["hf_graft"]`) so rig-anything reads a swimmer.
- **the surface**: the tail's UVs are laid in the largest rectangle of the skin atlas the removed legs freed, the
  vertex group `GROUP` marks the tail (humanform.skin's pattern region `graft` reads it, fading up over the seam by
  its own `fade`), and `PROP` on the body records the seam, the UV rectangle and what the graft removed.

What a replacement takes away must be declared absent by the description (`REPLACES[pair]["parts"]`, with its
reason): `validate` refuses a graft whose absences are not stated, so the anatomy inventory never has to guess.
"""

from __future__ import annotations

import json
import math

import numpy as np

GROUP = "hf_graft"
PROP = "hf_graft"
REPLACES = {
    # the parts a pair's replacement takes with it: the description must say so (species anatomy.absent)
    "legs": {"parts": ("knees", "soles", "nails.toes", "genitals"), "kinds": ("tail",),
             "why": "the legs, their feet and the crotch are below the seam"},
}
TAIL_KEYS = {"to", "seam", "length", "width", "depth", "fluke", "bones", "rings", "fade"}
FLUKE_KEYS = {"span", "chord", "sweep", "notch", "thickness", "plane"}
# the default body of a tail, over its length t (0 the seam, 1 the fluke's root): fractions of the seam's half width
# and half depth. Two legs pressed together and drawn out: hips, thighs, knees, calves, the peduncle [folklore, art]
WIDTH = [(0.0, 1.0), (0.15, 0.97), (0.4, 0.78), (0.65, 0.52), (0.85, 0.24), (1.0, 0.13)]
DEPTH = [(0.0, 1.0), (0.15, 1.0), (0.4, 0.84), (0.65, 0.6), (0.85, 0.34), (1.0, 0.24)]
FLUKE = {"span": 0.24, "chord": 0.45, "sweep": 0.35, "notch": 0.18, "thickness": 0.012, "plane": "horizontal"}
DEFAULTS = {"seam": 0.0, "length": 1.0, "bones": 8, "rings": 28, "fade": 0.08}
LIMITS = {"seam": (-0.15, 0.25), "length": (0.6, 1.0), "bones": (3, 16), "rings": (10, 60), "fade": (0.0, 0.3),
          "span": (0.08, 0.5), "chord": (0.15, 1.0), "sweep": (0.0, 1.0), "notch": (0.0, 0.6),
          "thickness": (0.003, 0.05)}


def validate(spec, absent=()):
    """[] or the problems with a graft block ({pair: {...}}), each naming the fix. `absent`: the parts the species
    declares absent (names); every part a replacement takes must be among them."""
    if not spec:
        return []
    if not isinstance(spec, dict):
        return [f"graft must be a table of pair = {{ to = ... }}, not {type(spec).__name__}"]
    out = []
    absent = set(absent)
    for pair, g in spec.items():
        if pair not in REPLACES:
            out.append(f"graft.{pair}: only {', '.join(REPLACES)} can be replaced so far")
            continue
        if not isinstance(g, dict):
            out.append(f"graft.{pair} must be a table ({', '.join(sorted(TAIL_KEYS))})")
            continue
        if g.get("to") not in REPLACES[pair]["kinds"]:
            out.append(f"graft.{pair}.to = {g.get('to')!r}: one of {', '.join(REPLACES[pair]['kinds'])}")
        out += [f"graft.{pair}: unknown key {k!r} - it takes {', '.join(sorted(TAIL_KEYS))}" for k in sorted(set(g) - TAIL_KEYS)]
        for k in ("seam", "length", "bones", "rings", "fade"):
            if k in g:
                lo, hi = LIMITS[k]
                if isinstance(g[k], bool) or not isinstance(g[k], (int, float)) or not lo <= g[k] <= hi:
                    out.append(f"graft.{pair}.{k} = {g[k]!r}: a number in {lo}..{hi}"
                               + (" (a tail longer than the legs would pass through the floor standing: "
                                  "curled tails are not made yet)" if k == "length" and isinstance(g[k], (int, float))
                                  and g[k] > hi else ""))
        for k in ("width", "depth"):
            prof = g.get(k)
            if prof is not None and (not isinstance(prof, (list, tuple)) or len(prof) < 2
                                     or not all(isinstance(p, (list, tuple)) and len(p) == 2 for p in prof)):
                out.append(f"graft.{pair}.{k}: a profile [[t, fraction], ...] with t from 0 (seam) to 1 (fluke)")
        fl = g.get("fluke") or {}
        if not isinstance(fl, dict):
            out.append(f"graft.{pair}.fluke must be a table ({', '.join(sorted(FLUKE_KEYS))})")
        else:
            out += [f"graft.{pair}.fluke: unknown key {k!r} - it takes {', '.join(sorted(FLUKE_KEYS))}"
                    for k in sorted(set(fl) - FLUKE_KEYS)]
            for k in ("span", "chord", "sweep", "notch", "thickness"):
                if k in fl:
                    lo, hi = LIMITS[k]
                    if not isinstance(fl[k], (int, float)) or not lo <= fl[k] <= hi:
                        out.append(f"graft.{pair}.fluke.{k} = {fl[k]!r}: a number in {lo}..{hi}")
            if fl.get("plane", "horizontal") not in ("horizontal", "vertical"):
                out.append(f"graft.{pair}.fluke.plane = {fl.get('plane')!r}: horizontal (flukes) or vertical (a fish)")
        missing = [p for p in REPLACES[pair]["parts"] if p not in absent and p.split(".")[0] not in absent]
        if missing:
            out.append(f"graft.{pair} -> {g.get('to')}: {REPLACES[pair]['why']}, so the description must declare "
                       f"{', '.join(missing)} absent (anatomy.absent, each with its reason)")
    return out


def _profile(prof, t):
    ts = np.array([p[0] for p in prof], float)
    vs = np.array([p[1] for p in prof], float)
    return np.interp(t, ts, vs)


def _smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------------------------------------------ the surface

def _free_rect(uv_faces, grid=256, margin=2):
    """The largest axis-aligned rectangle of the unit UV square no face in `uv_faces` (lists of (u, v)) touches,
    as (u0, v0, u1, v1), from a raster of the faces' UV triangles."""
    occ = np.zeros((grid, grid), bool)
    for f in uv_faces:
        f = np.asarray(f, float)
        lo = np.clip(np.floor(f.min(axis=0) * grid).astype(int) - margin, 0, grid - 1)
        hi = np.clip(np.ceil(f.max(axis=0) * grid).astype(int) + margin, 0, grid - 1)
        occ[lo[1]:hi[1] + 1, lo[0]:hi[0] + 1] = True
    # maximal rectangle in a binary matrix (histogram method), rows are v
    best, rect = 0, None
    h = np.zeros(grid, int)
    for y in range(grid):
        h = np.where(occ[y], 0, h + 1)
        stack = []
        for x in range(grid + 1):
            cur = h[x] if x < grid else 0
            start = x
            while stack and stack[-1][1] >= cur:
                s0, hh = stack.pop()
                area = hh * (x - s0)
                if area > best:
                    best, rect = area, (s0, y - hh + 1, x, y + 1)
                start = s0
            stack.append((start, cur))
    if rect is None:
        return None
    x0, y0, x1, y1 = rect
    return (x0 / grid, y0 / grid, x1 / grid, y1 / grid)


def _loops(edges):
    """Boundary edges -> ordered vertex loops (lists of vertex indices)."""
    from collections import defaultdict
    adj = defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    seen, loops = set(), []
    for start in adj:
        if start in seen or len(adj[start]) != 2:
            continue
        loop, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = [n for n in adj[cur] if n != prev]
            if not nxt:
                break
            n = nxt[0] if nxt[0] not in seen or nxt[0] == start else (nxt[1] if len(nxt) > 1 else None)
            if n is None or n == start:
                break
            if n in seen:
                break
            loop.append(n)
            seen.add(n)
            prev, cur = cur, n
        loops.append(loop)
    return loops


def apply(human, spec, verbose=False):
    """Graft the pairs in `spec` onto `human` (see the module docstring). Returns a report."""
    import bmesh
    import bpy
    from mathutils import Vector
    from . import body as _body, delta
    human = bpy.data.objects[human] if isinstance(human, str) else human
    rig = _body.rig_of(human)
    if rig is None:
        raise ValueError(f"graft: {human.name} has no rig - graft after the rig (and the warp)")
    report = {}
    for pair, g in spec.items():
        if pair != "legs" or g.get("to") != "tail":
            raise ValueError(f"graft.{pair} -> {g.get('to')}: not made (see validate)")
        report[pair] = _legs_to_tail(human, rig, dict(DEFAULTS, **g), delta, bmesh, bpy, Vector, verbose)
    return report


def _flatten_keys(human):
    """The body as drawn, as its only shape: every key applied into the basis and removed (the bake would have
    flattened them anyway; a graft adds vertices no key has)."""
    from .eye_layout import _full
    me = human.data
    if me.shape_keys is None:
        return 0
    co = _full(human)
    n = len(me.vertices)
    keys = [kb.name for kb in me.shape_keys.key_blocks]
    human.shape_key_clear()
    me.vertices.foreach_set("co", co.ravel())
    me.update()
    return len(keys)


def _legs_to_tail(human, rig, g, delta, bmesh, bpy, Vector, verbose):
    from .species import _Rig
    rep = {"flattened_keys": _flatten_keys(human)}
    rigd = _Rig(rig)
    legs = rigd.legs
    if not legs:
        raise ValueError("graft legs -> tail: the rig has no legs off its pelvis")
    leg_bones = {n for ch in legs.values() for n in ch if n}
    pelvis = rigd.spine[0]
    hip_z = float(np.mean([rig.data.bones[ch[0]].head_local.z for ch in legs.values()]))
    mw = human.matrix_world
    seam_z = hip_z + float(g["seam"])
    me = human.data
    n_all = len(me.vertices)
    co = np.empty(n_all * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    names = {vg.index: vg.name for vg in human.vertex_groups}
    top = np.full(n_all, "", object)
    for v in me.vertices:
        best, bw = "", 0.0
        for e in v.groups:
            nm = names.get(e.group)
            if nm in rig.data.bones and e.weight > bw:
                best, bw = nm, e.weight
        top[v.index] = best
    body_n = delta.BODY_VERTS
    carried = np.array([t in leg_bones or t == pelvis for t in top])
    arm_like = np.array([rigd.kind.get(t) in ("clavicle", "upper", "fore", "hand", "digit") for t in top])
    below = (co[:, 2] < seam_z) & carried & ~arm_like
    below[body_n:] = False                                       # helpers are the mask's, not ours
    # 1. faces: drop every body face with a vertex below the seam
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    drop = [f for f in bm.faces if any(below[v.index] for v in f.verts) and all(v.index < body_n for v in f.verts)]
    # the seam: boundary edges left by the dropped faces, as loops
    dropped = set(drop)
    edges = []
    for f in drop:
        for e in f.edges:
            if any(ff not in dropped for ff in e.link_faces):
                edges.append((e.verts[0].index, e.verts[1].index))
    loops = _loops(edges)
    if not loops:
        bm.free()
        raise ValueError("graft legs -> tail: the seam left no boundary loop")
    loops.sort(key=len, reverse=True)
    seam = loops[0]
    rep["seam_loops"] = [len(l) for l in loops]
    if len(loops) > 1 and len(loops[1]) > 0.25 * len(seam):
        bm.free()
        raise ValueError(f"graft legs -> tail: the seam at z {seam_z:.3f} cut {len(loops)} loops {rep['seam_loops']} "
                         "- it must be one ring round the body (raise the seam above the crotch)")
    bmesh.ops.delete(bm, geom=drop, context="FACES_ONLY")
    # loose edges left by the faces would be exported as lines: remove the edges no face uses (verts stay)
    loose = [e for e in bm.edges if not e.link_faces and all(v.index < body_n for v in e.verts)]
    bmesh.ops.delete(bm, geom=loose, context="EDGES_FACES")
    bm.verts.ensure_lookup_table()
    rep["faces_removed"] = len(drop)

    # 2. the seam ring, levelled onto the seam's height and ordered round the body
    sv = [bm.verts[i] for i in seam]
    P0 = np.array([tuple(v.co) for v in sv])
    centre = P0.mean(axis=0)
    ang = np.arctan2(P0[:, 1] - centre[1], P0[:, 0] - centre[0])
    order = np.argsort(ang)
    sv = [sv[i] for i in order]
    P0 = P0[order]
    for v in sv:
        v.co.z = seam_z
    P0[:, 2] = seam_z
    rel = P0[:, :2] - centre[:2]
    W0, D0 = float(np.abs(rel[:, 0]).max()), float(np.abs(rel[:, 1]).max())
    theta = np.arctan2(rel[:, 1] / max(D0, 1e-6), rel[:, 0] / max(W0, 1e-6))
    M = len(sv)
    # the section the rings start from: the seam's, smoothed round the ring so the groin's dents do not run down
    # the tail as creases (they did, on the first merman), at the seam's own width and depth
    soft = rel.copy()
    for _ in range(max(6, M // 3)):
        soft = 0.5 * soft + 0.25 * (np.roll(soft, 1, axis=0) + np.roll(soft, -1, axis=0))
    soft[:, 0] *= W0 / max(float(np.abs(soft[:, 0]).max()), 1e-6)
    soft[:, 1] *= D0 / max(float(np.abs(soft[:, 1]).max()), 1e-6)
    # 3. the tail: rings down to the fluke's root, then the fluke
    H = float(co[:body_n, 2].max() - co[:body_n, 2].min())
    fl = dict(FLUKE, **(g.get("fluke") or {}))
    span = fl["span"] * H
    chord = fl["chord"] * span
    reach = seam_z * float(g["length"])                          # seam to the lowest fluke tip
    body_len = max(reach - chord * (1 + fl["sweep"]), 0.3 * reach)
    K = int(g["rings"])
    F = max(4, K // 4)
    wprof, dprof = g.get("width") or WIDTH, g.get("depth") or DEPTH
    horizontal = fl["plane"] == "horizontal"
    rings = [sv]
    ring_t = [0.0]
    for k in range(1, K + 1):
        t = k / K
        z = seam_z - body_len * t
        e = _smooth(t / 0.35)                                    # the seam's own section, then an ellipse
        r = _smooth(t / 0.08)                                    # the seam's dents gone within a ring or two
        w, d = _profile(wprof, t) * W0, _profile(dprof, t) * D0
        sx = (1 - r) * rel[:, 0] + r * soft[:, 0]
        sy = (1 - r) * rel[:, 1] + r * soft[:, 1]
        x = (1 - e) * sx * (w / W0) + e * w * np.cos(theta)
        y = (1 - e) * sy * (d / D0) + e * d * np.sin(theta)
        rings.append([bm.verts.new((centre[0] + xi, centre[1] + yi, z)) for xi, yi in zip(x, y)])
        ring_t.append(t)
    ped_w, ped_d = _profile(wprof, 1.0) * W0, _profile(dprof, 1.0) * D0
    z_ped = seam_z - body_len
    lat = np.cos(theta)
    a = np.abs(lat)
    for f in range(1, F + 1):
        u = f / F
        half = ped_w + (span / 2 - ped_w) * (1 - (1 - u) ** 2) if horizontal else ped_w * (1 - u) + 0.004
        edge = fl["thickness"] / 2 * (1 - u ** 4) + 0.0005        # thinning to a sharp trailing edge
        thick = ped_d * (1 - u) ** 1.5 + edge if horizontal else \
            ped_d + (span / 2 - ped_d) * (1 - (1 - u) ** 2)
        if horizontal:
            x, y, s = half * lat, thick * np.sin(theta), a
        else:
            x, y, s = half * lat, thick * np.sin(theta), np.abs(np.sin(theta))
        z = z_ped - chord * u * (1 + fl["sweep"] * s ** 2) + fl["notch"] * chord * (1 - s) ** 2 * u ** 2
        rings.append([bm.verts.new((centre[0] + xi, centre[1] + yi, zi)) for xi, yi, zi in zip(x, y, z)])
        ring_t.append(1.0 + u)
    # the trailing edge closed by a strip of faces across the blade's thin section (top half onto bottom half)
    faces_new = []
    for r0, r1 in zip(rings[:-1], rings[1:]):
        for j in range(M):
            jj = (j + 1) % M
            faces_new.append(bm.faces.new((r0[j], r0[jj], r1[jj], r1[j])))
    last = rings[-1]
    # the trailing edge: the last ring zipped shut, top onto bottom, from one tip to the other (an n-gon across a
    # swept, notched blade folded and shaded black)
    ll = np.array([tuple(v.co) for v in last])
    key = 0 if horizontal else 1
    j_r, j_l = int(np.argmax(ll[:, key])), int(np.argmin(ll[:, key]))

    def walk(step):
        out, j = [j_r], j_r
        while j != j_l:
            j = (j + step) % M
            out.append(j)
        return out
    T, Bt = walk(1), walk(-1)
    i = k = 0
    cap_faces = []
    while i < len(T) - 1 or k < len(Bt) - 1:
        adv_t = k == len(Bt) - 1 or (i < len(T) - 1 and ll[T[i + 1], key] >= ll[Bt[k + 1], key])
        if adv_t:
            tri = (last[T[i]], last[Bt[k]], last[T[i + 1]])
            i += 1
        else:
            tri = (last[T[i]], last[Bt[k]], last[Bt[k + 1]])
            k += 1
        if len(set(tri)) == 3:
            try:
                cap_faces.append(bm.faces.new(tri))
            except ValueError:
                pass
    faces_new.extend(cap_faces)
    for f in faces_new:
        f.smooth = True
    bm.normal_update()
    # outward normals: flip the tail's faces if they face the axis
    probe = faces_new[M * (K // 2)]
    c = probe.calc_center_median()
    if probe.normal.dot(Vector((c.x - centre[0], c.y - centre[1], 0.0))) < 0:
        for f in faces_new:
            f.normal_flip()
    bm.verts.index_update()
    tail_idx = [v.index for r in rings[1:] for v in r]
    seam_idx = [v.index for v in sv]
    rep.update(seam_z=round(seam_z, 4), seam_verts=M, rings=K + F, tail_verts=len(tail_idx), span_m=round(span, 3),
               chord_m=round(chord, 3), body_len_m=round(body_len, 3))

    # 4. UVs: the tail in the largest rectangle of the atlas no remaining body face uses
    uvl = bm.loops.layers.uv.active
    rect = None
    if uvl is not None:
        new_faces = set(faces_new)
        uv_faces = [[tuple(l[uvl].uv) for l in f.loops] for f in bm.faces
                    if f not in new_faces and all(v.index < body_n for v in f.verts)]
        rect = _free_rect(uv_faces)
        if rect is None:
            rect = (0.0, 0.0, 0.05, 0.05)
        u0, v0, u1, v1 = rect
        nr = len(rings) - 1
        for ri in range(nr):
            for j in range(M):
                f = faces_new[ri * M + j]
                for l in f.loops:
                    vi = l.vert
                    # which ring and column this corner is
                    col = j if vi in (rings[ri][j], rings[ri + 1][j]) else j + 1
                    row = ri if vi in (rings[ri][j], rings[ri][(j + 1) % M]) else ri + 1
                    l[uvl].uv = (u0 + (u1 - u0) * col / M, v1 - (v1 - v0) * row / nr)
        for cf in cap_faces:
            for l in cf.loops:
                l[uvl].uv = (u0 + (u1 - u0) * 0.5, v0)
    rep["uv_rect"] = [round(x, 4) for x in rect] if rect else None
    # shape keys none (flattened); write back
    bm.to_mesh(me)
    bm.free()
    me.update()
    n_new = len(me.vertices)

    # 5. the rig: leg chains out, a tail chain in
    bpy.context.view_layer.objects.active = rig
    prev_mode = rig.mode
    for o in bpy.context.selected_objects:
        o.select_set(False)
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = rig.data.edit_bones
    removed = []
    for nm in list(leg_bones):
        b = eb.get(nm)
        if b is not None:
            for ch in [c for c in eb if c.parent == b]:
                if ch.name not in leg_bones:
                    removed.append(ch.name)
                    eb.remove(ch)
            removed.append(nm)
            eb.remove(b)
    B = int(g["bones"])
    mwi = rig.matrix_world.inverted()
    tip_z = seam_z - reach
    # the chain runs down the tail's centre, its last bone through the fluke
    joints = [Vector((centre[0], centre[1], seam_z - (seam_z - tip_z) * (i / B) ** 1.0)) for i in range(B + 1)]
    names = []
    parent = eb[pelvis]
    for i in range(B):
        b = eb.new(f"tail.{i:03d}")
        b.head = mwi @ (mw @ joints[i])
        b.tail = mwi @ (mw @ joints[i + 1])
        b.roll = 0.0
        b.parent = parent
        b.use_connect = i > 0
        b.use_deform = True
        parent = b
        names.append(b.name)
    bpy.ops.object.mode_set(mode="OBJECT")
    rep["bones_removed"] = sorted(set(removed))
    rep["bones"] = names

    # 6. weights: the tail by its height along the chain; the legs' weights above the seam onto the first tail bone
    zs = np.array([j.z for j in joints])
    co2 = np.empty(n_new * 3)
    me.vertices.foreach_get("co", co2)
    co2 = co2.reshape(-1, 3)
    for nm in names:
        if nm not in human.vertex_groups:
            human.vertex_groups.new(name=nm)
    vg = {nm: human.vertex_groups[nm] for nm in names}
    gr = human.vertex_groups.get(GROUP) or human.vertex_groups.new(name=GROUP)

    def along(z):
        s = np.clip((seam_z - z) / max(seam_z - tip_z, 1e-6), 0, 1) * B      # 0 at the seam, B at the tip
        mid = np.clip(s - 0.5, 0, B - 1)
        i0 = np.floor(mid).astype(int)
        f = mid - i0
        return i0, np.clip(i0 + 1, 0, B - 1), f

    leg_groups = [human.vertex_groups[nm] for nm in leg_bones if nm in human.vertex_groups]
    loose_idx = np.flatnonzero(below[:n_all])
    # loose leg vertices: into the tail's axis at their own height, carried by it
    for i in loose_idx:
        z = seam_z - (seam_z - co2[i, 2]) / max(seam_z, 1e-6) * body_len
        me.vertices[i].co = Vector((centre[0], centre[1], z))
    me.update()
    for grp in leg_groups:
        idx = [v.index for v in me.vertices if any(e.group == grp.index for e in v.groups)]
        keep = [i for i in idx if not below[i] and i < n_all]
        # what the thigh carried above the seam goes to the first tail bone, at its weight
        for i in keep:
            w = next(e.weight for e in me.vertices[i].groups if e.group == grp.index)
            vg[names[0]].add([int(i)], w, "ADD")
        human.vertex_groups.remove(grp)
    everyone = list(loose_idx) + list(range(n_all, n_new))
    for i in everyone:
        v = me.vertices[i]
        for e in list(v.groups):
            gname = human.vertex_groups[e.group].name
            if gname != GROUP:
                human.vertex_groups[e.group].remove([int(i)])
        i0, i1, f = along(np.array([co2[i, 2] if i >= n_all else me.vertices[i].co.z]))
        vg[names[int(i0[0])]].add([int(i)], float(1 - f[0]), "REPLACE")
        if int(i1[0]) != int(i0[0]):
            vg[names[int(i1[0])]].add([int(i)], float(f[0]), "REPLACE")
    gr.add(list(range(n_all, n_new)), 1.0, "REPLACE")
    # a Mask modifier that keeps a group (MPFB's "Hide helpers" keeps its body group) must keep the tail too
    for m in human.modifiers:
        if m.type == "MASK" and m.vertex_group and not m.invert_vertex_group:
            keepg = human.vertex_groups.get(m.vertex_group)
            if keepg is not None:
                keepg.add(list(range(n_all, n_new)), 1.0, "REPLACE")
    # the seam ring carries the pelvis and the tail half and half
    pel = human.vertex_groups.get(pelvis)
    for i in seam_idx:
        vg[names[0]].add([int(i)], 0.5, "ADD")
    human.vertex_groups.active_index = gr.index
    info = {"pair": "legs", "to": "tail", "seam_z": round(seam_z, 4), "uv_rect": rep["uv_rect"],
            "fade": float(g["fade"]), "bones": names, "tip_z": round(tip_z, 4), "centre": [round(float(c), 4) for c in centre],
            "removed_parts": list(REPLACES["legs"]["parts"]), "fluke": {k: fl[k] for k in FLUKE}, "span_m": rep["span_m"],
            "first_new_vertex": n_all}
    human[PROP] = json.dumps(info)
    rig[PROP] = json.dumps({"tail": names, "pelvis": pelvis, "fluke_plane": fl["plane"], "removed": rep["bones_removed"]})
    rep["loose_verts"] = int(len(loose_idx))
    return rep
