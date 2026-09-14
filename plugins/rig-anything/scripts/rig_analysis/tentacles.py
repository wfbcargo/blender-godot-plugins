"""Tentacles: arms with no skeleton in them, found on the skin and rigged as chains.

An octopus arm has no joints. It bends anywhere, twists, and changes length -
arms elongate 66% on average when reaching and up to 80% (arm L2), and can be
stretched passively past twice their rest length (JEMBE 2013). So an arm is
rigged as a chain of short bones that are NOT connected: each bone's head may
move away from its parent's tail, which is how a chain of rigid bones carries
an arm that gets longer. Nothing here uses constraints - glTF cannot carry
them - so every pose is solved as positions and baked.

    detect(mesh)     arms found on the skin: an azimuth histogram of the far
                     skin, a centreline through shells of distance from the
                     hub, a radius profile; the head and mantle are what is left
    build(mesh)      body, head, mantle (scaled to breathe and jet), a funnel
                     socket and N bones per arm
    skin(rig)        weights from geometry, not bone heat: a 3.5 mm arm tip is
                     where bone heat is least reliable, and the web between two
                     arms must be shared by both or it tears when they part

Arms are named for the octopus: pairs I-IV counted from the dorsal midline,
L1 the front left arm and R4 the back right (cephalopodpage). Any other count
gets arm01.. in azimuth order.

A posed arm is given as JOINT POSITIONS and turned into bone matrices by
parallel transport from the body, so a curve never needs a roll or a sign: see
`Tentacles.chain`. `curve` integrates a centreline from curvature along the
arm, `hermite` spans two points - a base on the body and a sucker on the floor.
"""

from __future__ import annotations

import json
import math

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

PROP = "rig_anything_tentacles"
BONES_PER_ARM = 12


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def min_jerk(t):
    """0..1 with a bell-shaped derivative - the speed profile of the bend that
    travels down a reaching arm (Gutfreund 1996; Yekutieli 2005)."""
    t = max(0.0, min(1.0, t))
    return t * t * t * (10.0 - 15.0 * t + 6.0 * t * t)


# --------------------------------------------------------------------------
# a test body
# --------------------------------------------------------------------------

def make_test_octopus(name="OctoTest", mantle=0.16, arm=0.70, web_share=0.4, voxel=0.0035,
                      faces=28000):
    """An O. vulgaris-proportioned test mesh, one closed manifold skin.

    Arms 4.4x the mantle (4.4-4.6x measured on 19 animals, JEMBE 2013; 4-5x
    from 15-25 cm mantles and 76-100 cm arms), tapering ~8:1 base to tip, a web
    reaching `web_share` of the arm (40% in benthic O. vulgaris - search
    snippet, primary source not read), eyes high on the head, the mantle
    sweeping back and up. Faces -Y, arms spread on the floor at Z = 0.
    """
    scene = bpy.context.scene
    for n in (name, name + "_rig"):
        o = bpy.data.objects.get(n)
        if o:
            bpy.data.objects.remove(o, do_unlink=True)
    parts = []

    def link(nm, me):
        o = bpy.data.objects.new(nm, me)
        scene.collection.objects.link(o)
        parts.append(o)
        return o

    H = 0.05
    ring_z = H + 0.03
    # arms: a skin modifier on a star
    import bmesh
    me = bpy.data.meshes.new("_octo_arms")
    bm = bmesh.new()
    radii = []

    def vert(p, r):
        radii.append(r)
        return bm.verts.new(Vector(p))
    hub = vert((0, 0, ring_z), 0.04)
    N = 22
    base_r = arm / 26.0
    for sgn in (1.0, -1.0):
        for i in range(4):
            ang = math.radians(22.5 + 45.0 * i)
            d = Vector((sgn * math.sin(ang), -math.cos(ang), 0.0))
            prev = hub
            for k in range(1, N + 1):
                s = k / N * arm
                drop = min(1.0, s / (0.22 * arm))
                r = base_r * (1 - s / arm) ** 1.3 + 0.0035
                z = (ring_z - base_r) * (1 - drop * (2 - drop)) + r
                v = vert(d * (0.03 + s) + Vector((0, 0, z)), r)
                bm.edges.new((prev, v))
                prev = v
    bm.to_mesh(me)
    bm.free()
    arms_o = link("_octo_arms", me)
    bm = bmesh.new()
    bm.from_mesh(me)
    lay = bm.verts.layers.skin.verify()
    bm.verts.ensure_lookup_table()
    for v, r in zip(bm.verts, radii):
        v[lay].radius = (r, r)
    bm.verts[0][lay].use_root = True
    bm.to_mesh(me)
    bm.free()
    arms_o.modifiers.new("skin", "SKIN")
    arms_o.modifiers.new("sub", "SUBSURF").levels = 2

    # head and mantle: a surface of revolution along a bent axis
    head_len, head_r = 0.085, 0.04
    tilt = math.radians(40.0)

    def axis(t):
        if t < 0.3:
            return Vector((0, 0, H + 0.02 + head_len * t / 0.3))
        u = (t - 0.3) / 0.7
        return Vector((0, 0, H + 0.02 + head_len)) + Vector((0, math.sin(tilt), math.cos(tilt))) * mantle * u

    def radius(t):
        if t < 0.3:
            return head_r + 0.25 * head_r * math.sin(math.pi * t / 0.3)
        u = (t - 0.3) / 0.7
        return 0.45 * head_r + 0.3 * mantle * math.sin(math.pi * (0.12 + 0.88 * u)) ** 0.8 * (1 - u) ** 0.15
    me = bpy.data.meshes.new("_octo_body")
    bm = bmesh.new()
    SEG, RING = 32, 40
    rings = []
    for j in range(RING + 1):
        t = j / RING
        c = axis(t)
        tan = (axis(min(1, t + 0.01)) - axis(max(0, t - 0.01))).normalized()
        x = Vector((1, 0, 0))
        y = tan.cross(x).normalized()
        r = radius(t) if 0 < j < RING else 0.0
        rings.append([bm.verts.new(c + (x * math.cos(2 * math.pi * k / SEG) * 1.1
                                         + y * math.sin(2 * math.pi * k / SEG)) * r) for k in range(SEG)])
    for j in range(RING):
        for k in range(SEG):
            try:
                bm.faces.new((rings[j][k], rings[j][(k + 1) % SEG], rings[j + 1][(k + 1) % SEG], rings[j + 1][k]))
            except ValueError:
                pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.to_mesh(me)
    bm.free()
    link("_octo_body", me)
    for sgn in (1, -1):
        me = bpy.data.meshes.new("_octo_eye")
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=0.45 * head_r)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(sgn * 1.1 * head_r, -0.3 * head_r, H + 0.02 + 0.7 * head_len))
        bm.to_mesh(me)
        bm.free()
        link("_octo_eye", me)
    # web: a thin skirt with a scalloped edge that runs further up each arm
    me = bpy.data.meshes.new("_octo_web")
    bm = bmesh.new()
    WR = web_share * arm
    rows = []
    for j in range(9):
        s = j / 8 * WR
        drop = min(1.0, s / (0.22 * arm))
        z = (ring_z - base_r) * (1 - drop * (2 - drop)) + 0.018
        row = []
        for k in range(64):
            a = 2 * math.pi * k / 64
            scallop = math.cos(8 * (a - math.radians(22.5)))
            reach = (0.03 + s) * (0.7 + 0.3 * scallop) if j else 0.03
            row.append(bm.verts.new((math.sin(a) * reach, -math.cos(a) * reach, z)))
        rows.append(row)
    for j in range(8):
        for k in range(64):
            bm.faces.new((rows[j][k], rows[j][(k + 1) % 64], rows[j + 1][(k + 1) % 64], rows[j + 1][k]))
    bm.to_mesh(me)
    bm.free()
    web = link("_octo_web", me)
    sol = web.modifiers.new("sol", "SOLIDIFY")
    sol.thickness = 0.01
    sol.offset = 0

    dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    for o in parts:
        ev = o.evaluated_get(dg)
        m = ev.to_mesh()
        tm = bpy.data.meshes.new("_tmp")
        tm.from_pydata([o.matrix_world @ v.co for v in m.vertices], [], [tuple(p.vertices) for p in m.polygons])
        ev.to_mesh_clear()
        bm.from_mesh(tm)
        bpy.data.meshes.remove(tm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    scene.collection.objects.link(obj)
    for o in parts:
        mesh = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    rm = obj.modifiers.new("remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = voxel
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    n = len(ev.to_mesh().polygons)
    ev.to_mesh_clear()
    obj.modifiers.new("dec", "DECIMATE").ratio = min(1.0, faces / max(n, 1))
    sm = obj.modifiers.new("smooth", "SMOOTH")
    sm.factor, sm.iterations = 0.5, 3
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    final = bpy.data.meshes.new_from_object(ev)
    old = obj.data
    obj.modifiers.clear()
    obj.data = final
    bpy.data.meshes.remove(old)
    final.name = name
    for p in final.polygons:
        p.use_smooth = True
    # settle on the floor
    low = min(v.co.z for v in final.vertices)
    for v in final.vertices:
        v.co.z -= low
    return {"mesh": name, "vertices": len(final.vertices), "faces": len(final.polygons),
            "mantle_m": mantle, "arm_m": arm, "web_share": web_share}


# --------------------------------------------------------------------------
# recognition
# --------------------------------------------------------------------------

def _polyline_param(P, pts):
    """For points P (n,3), the arc length of the nearest point on polyline
    `pts` (m,3) and the distance to it."""
    A, B = pts[:-1], pts[1:]
    AB = B - A
    L = np.linalg.norm(AB, axis=1)
    cum = np.concatenate([[0.0], np.cumsum(L)])
    best_d = np.full(len(P), np.inf)
    best_s = np.zeros(len(P))
    for i in range(len(A)):
        ab = AB[i]
        denom = max(float(ab @ ab), 1e-12)
        t = np.clip(((P - A[i]) @ ab) / denom, 0.0, 1.0)
        q = A[i] + t[:, None] * ab
        d = np.linalg.norm(P - q, axis=1)
        m = d < best_d
        best_d[m] = d[m]
        best_s[m] = cum[i] + t[m] * L[i]
    return best_s, best_d, cum[-1]


def _circ(a):
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def detect(mesh_name, n_arms=None, up="Z", forward="-Y"):
    """Find the arms, the hub they radiate from, and the head and mantle.

    Works on a body resting with its arms spread - as a fish's fins are found
    spread. Arms are the far skin clustered by azimuth about the hub; each
    one's centreline is the centroid of its skin in shells of distance from
    the hub, walked from the tip inward so a shell's skin is taken near the
    one outside it and the web and head do not pull it up."""
    if up != "Z" or forward != "-Y":
        raise ValueError("tentacles.detect expects Z up and -Y forward")
    obj = bpy.data.objects[mesh_name]
    mw = obj.matrix_world
    V = np.array([tuple(mw @ v.co) for v in obj.data.vertices])
    floor = float(V[:, 2].min())
    c = 0.5 * (V[:, :2].min(axis=0) + V[:, :2].max(axis=0))
    peaks = []
    for _ in range(3):
        rel = V[:, :2] - c
        rho = np.hypot(rel[:, 0], rel[:, 1])
        R = float(rho.max())
        az = np.arctan2(rel[:, 0], -rel[:, 1])          # 0 forward (-Y), + toward +X (left)
        far = rho > 0.5 * R
        bins = 90
        h, _ = np.histogram(az[far], bins=bins, range=(-math.pi, math.pi))
        k = np.array([1, 2, 3, 2, 1], dtype=float)
        hs = np.array([sum(k[j] * h[(i + j - 2) % bins] for j in range(5)) for i in range(bins)])
        cand = [i for i in range(bins)
                if hs[i] > 0.15 * hs.max() and all(hs[i] >= hs[(i + d) % bins] for d in (-3, -2, -1, 1, 2, 3))]
        # plateaus give adjacent maxima: keep one per run
        cand = [i for i in cand if (i - 1) % bins not in cand]
        cand.sort(key=lambda i: -hs[i])
        if n_arms:
            cand = cand[:n_arms]
        centres = [-math.pi + (i + 0.5) * 2 * math.pi / bins for i in cand]
        fa = az[far]
        diff = np.array([[abs(_circ(float(a) - cz)) for cz in centres] for a in fa])
        lab = diff.argmin(axis=1)
        idx_far = np.nonzero(far)[0]
        peaks = []
        mids = []
        for j, cz in enumerate(centres):
            sel = idx_far[lab == j]
            if len(sel) < 10:
                continue
            a = az[sel]
            mean = math.atan2(float(np.sin(a).mean()), float(np.cos(a).mean()))
            tip = sel[np.argmax(rho[sel])]
            band = sel[(rho[sel] > 0.5 * R) & (rho[sel] < 0.62 * R)]
            mids.append(V[band, :2].mean(axis=0) if len(band) else V[tip, :2])
            peaks.append({"azimuth": mean, "tip_index": int(tip)})
        c = np.mean(mids, axis=0)
    rel = V[:, :2] - c
    rho = np.hypot(rel[:, 0], rel[:, 1])
    R = float(rho.max())
    az = np.arctan2(rel[:, 0], -rel[:, 1])
    peaks.sort(key=lambda p: p["azimuth"])
    n = len(peaks)
    if n < 3:
        return {"error": "found %d arms - is the body resting with its arms spread?" % n}
    centre_mask = rho < 0.04 * R
    hub_z = float(V[centre_mask, 2].min()) if centre_mask.any() else floor
    hub = np.array([c[0], c[1], hub_z])

    arms = []
    for j, p in enumerate(peaks):
        prev_az, next_az = peaks[j - 1]["azimuth"], peaks[(j + 1) % n]["azimuth"]
        half = 0.5 * min(abs(_circ(p["azimuth"] - prev_az)), abs(_circ(next_az - p["azimuth"])))
        sector = np.abs(np.array([_circ(float(a) - p["azimuth"]) for a in az])) < half
        tip = V[p["tip_index"]]
        tip_rho = float(rho[p["tip_index"]])
        edges = np.linspace(0.07 * R, tip_rho, 26)
        pts, rads = [], []
        zc, rc = float(tip[2]), None
        for e0, e1 in reversed(list(zip(edges[:-1], edges[1:]))):
            m = sector & (rho >= e0) & (rho < e1)
            if rc is not None:
                m &= V[:, 2] < zc + 3.0 * rc + 0.01 * R
            if m.sum() < 4:
                continue
            cen = V[m].mean(axis=0)
            rr = float(np.median(np.linalg.norm(V[m] - cen, axis=1)))
            pts.append(cen)
            rads.append(rr)
            zc, rc = float(cen[2]), rr
        pts.reverse()
        rads.reverse()
        d = np.array([math.sin(p["azimuth"]), -math.cos(p["azimuth"]), 0.0])
        base = hub + d * 0.05 * R + np.array([0.0, 0.0, rads[0] if rads else 0.0])
        line = np.array([base] + pts + [tip])
        rline = [rads[0] if rads else 0.0] + rads + [rads[-1] * 0.5 if rads else 0.0]
        for _ in range(2):
            line[1:-1] = 0.25 * line[:-2] + 0.5 * line[1:-1] + 0.25 * line[2:]
        seg = np.linalg.norm(np.diff(line, axis=0), axis=1)
        arms.append({"azimuth": p["azimuth"], "dir": d.tolist(), "centreline": line.tolist(),
                     "radii": rline, "length": float(seg.sum())})

    # names: pairs I-IV from the front on each side, when there are eight
    left = [a for a in arms if a["azimuth"] > 0]
    right = [a for a in arms if a["azimuth"] <= 0]
    if n == 8 and len(left) == 4:
        for side, group in (("L", left), ("R", right)):
            for i, a in enumerate(sorted(group, key=lambda a: abs(a["azimuth"]))):
                a["label"], a["side"], a["pair"] = "%s%d" % (side, i + 1), side, i + 1
    else:
        for i, a in enumerate(arms):
            a["label"], a["side"], a["pair"] = "arm%02d" % (i + 1), "", i + 1

    # head and mantle: skin above the hub that no arm claims
    near_arm = np.zeros(len(V), dtype=bool)
    for a in arms:
        s, dist, L = _polyline_param(V, np.array(a["centreline"]))
        r = np.interp(s, np.linspace(0, L, len(a["radii"])), a["radii"])
        near_arm |= dist < 2.0 * np.maximum(r, 0.005)
    body = (~near_arm) & (V[:, 2] > hub_z + 0.01 * R) & (rho < 0.35 * R)
    B = V[body]
    if len(B) < 20:
        return {"error": "no head or mantle found above the arms"}
    cen = B.mean(axis=0)
    _, _, vt = np.linalg.svd(B - cen, full_matrices=False)
    ax = vt[0] if vt[0][2] > 0 else -vt[0]
    proj = (B - hub) @ ax
    lo, hi = float(proj.min()), float(proj.max())
    nb = 20
    prof = []
    for i in range(nb):
        m = (proj >= lo + (hi - lo) * i / nb) & (proj < lo + (hi - lo) * (i + 1) / nb + 1e-9)
        if m.sum() < 5:
            prof.append((None, None))
            continue
        cc = B[m].mean(axis=0)
        prof.append((cc, float(np.percentile(np.linalg.norm(B[m] - cc, axis=1), 80))))
    valid = [i for i in range(nb) if prof[i][0] is not None]
    inner = [i for i in valid if 0.25 * nb <= i <= 0.65 * nb]
    neck_i = None
    for i in inner:
        nbrs = [prof[j][1] for j in (i - 1, i + 1) if 0 <= j < nb and prof[j][1] is not None]
        if nbrs and prof[i][1] <= min(nbrs) and prof[i][1] < 0.92 * max(prof[j][1] for j in valid if j < i):
            neck_i = i
            break
    neck_i = neck_i if neck_i is not None else int(0.35 * nb)
    neck = prof[neck_i][0]
    far = B[np.argmax(np.linalg.norm(B - neck, axis=1))]
    head_r = max((prof[i][1] for i in valid if i <= neck_i), default=0.0)
    mantle_r = max((prof[i][1] for i in valid if i > neck_i), default=0.0)
    # Dorsal mantle length (DML), the measure cephalopod speeds are quoted in,
    # runs from between the eyes to the apex. The eyes are not found: a smooth
    # skin shows no bulge a slice can tell from the mantle's own widening, and
    # the widest slice below the neck WAS the neck. They are put a head radius
    # below the neck, toward the mouth - on the test body 1 cm from where they
    # were modelled. Pass dml_m to `octopus.Octopus` to override.
    eye = neck + (hub - neck) / max(np.linalg.norm(hub - neck), 1e-9) * head_r
    return {
        "mesh": mesh_name, "floor": floor, "reach": R, "hub": hub.tolist(), "arms": arms,
        "neck": neck.tolist(), "apex": far.tolist(), "head_radius": head_r, "mantle_radius": mantle_r,
        "eye": eye.tolist(), "dorsal_mantle_length": float(np.linalg.norm(far - eye)),
        "mantle_length": float(np.linalg.norm(far - neck)),
        "arm_length": float(np.mean([a["length"] for a in arms])),
        "arm_count": n,
    }


def summary(d):
    if "error" in d:
        return "ERROR " + d["error"]
    lines = ["%d arms from a hub %.3f m up; reach %.3f m; mantle %.3f m (radius %.3f), DML %.3f m, head radius %.3f"
             % (d["arm_count"], d["hub"][2], d["reach"], d["mantle_length"], d["mantle_radius"],
                d["dorsal_mantle_length"], d["head_radius"])]
    for a in d["arms"]:
        lines.append("  %-5s azimuth %6.1f deg  length %.3f m  base radius %.4f  tip %.4f"
                     % (a["label"], math.degrees(a["azimuth"]), a["length"], a["radii"][1], a["radii"][-2]))
    lines.append("  arms / DML %.2f (O. vulgaris 4.4-4.6)" % (d["arm_length"] / max(d["dorsal_mantle_length"], 1e-9)))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# building
# --------------------------------------------------------------------------

def _resample(line, n):
    line = [Vector(p) for p in line]
    cum = [0.0]
    for a, b in zip(line, line[1:]):
        cum.append(cum[-1] + (b - a).length)
    total = cum[-1]
    out = []
    j = 0
    for i in range(n + 1):
        s = total * i / n
        while j < len(line) - 2 and cum[j + 1] < s:
            j += 1
        seg = max(cum[j + 1] - cum[j], 1e-12)
        out.append(line[j].lerp(line[j + 1], (s - cum[j]) / seg))
    return out, total


def build(mesh_name, detection=None, rig_name=None, bones_per_arm=BONES_PER_ARM):
    """An armature for a tentacled body: `body` at the hub (the mouth), `head`
    up to the neck, `mantle` to the apex (a leaf, so it may scale), a `funnel`
    socket, and `bones_per_arm` unconnected bones along each arm."""
    d = detection or detect(mesh_name)
    if "error" in d:
        return d
    mesh = bpy.data.objects[mesh_name]
    rig_name = rig_name or mesh_name + "_rig"
    old = bpy.data.objects.get(rig_name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    arm_data = bpy.data.armatures.new(rig_name)
    rig = bpy.data.objects.new(rig_name, arm_data)
    bpy.context.scene.collection.objects.link(rig)
    view = bpy.context.view_layer
    for o in view.objects:
        o.select_set(False)
    view.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    hub, neck, apex = Vector(d["hub"]), Vector(d["neck"]), Vector(d["apex"])
    up = Vector((0, 0, 1))
    fwd = Vector((0, -1, 0))

    body = eb.new("body")
    body.head = hub
    body.tail = hub + up * max(0.5 * (neck - hub).length, 0.01)
    body.align_roll(fwd)
    head = eb.new("head")
    head.head = hub + up * 1e-4
    head.tail = neck
    head.parent = body
    head.align_roll(fwd)
    mantle = eb.new("mantle")
    mantle.head = neck
    mantle.tail = apex
    mantle.parent = head
    mantle.align_roll(fwd)
    funnel = eb.new("funnel")
    # ventral, where the mantle opens behind the head; points at the arms
    back = Vector((apex.x - neck.x, apex.y - neck.y, 0.0))
    back = back.normalized() if back.length > 1e-6 else Vector((0, 1, 0))
    funnel.head = neck + back * d["head_radius"] * 0.9 - up * d["head_radius"] * 0.4
    funnel.tail = funnel.head + (hub - funnel.head).normalized() * d["head_radius"]
    funnel.parent = head
    funnel.use_deform = False
    funnel.align_roll(fwd)

    arms_out = []
    for a in d["arms"]:
        joints, total = _resample(a["centreline"], bones_per_arm)
        names = []
        prev = body
        for k in range(bones_per_arm):
            nm = "arm%d_%02d.%s" % (a["pair"], k, a["side"]) if a["side"] else "%s_%02d" % (a["label"], k)
            b = eb.new(nm)
            b.head, b.tail = joints[k], joints[k + 1]
            b.parent = prev
            b.use_connect = False
            b.align_roll(up)
            prev = b
            names.append(nm)
        arms_out.append({"label": a["label"], "side": a["side"], "pair": a["pair"], "azimuth": a["azimuth"],
                         "dir": a["dir"], "bones": names, "length": total,
                         "radii": [float(x) for x in np.interp(np.linspace(0, 1, bones_per_arm + 1),
                                                                np.linspace(0, 1, len(a["radii"])), a["radii"])]})
    bpy.ops.object.mode_set(mode="OBJECT")
    for b in arm_data.bones:
        if b.name.startswith("arm"):
            b["tentacle"] = b.name.split("_")[0]
    rig.data[PROP] = json.dumps({
        "version": 1, "mesh": mesh_name, "floor": d["floor"], "hub": d["hub"], "neck": d["neck"],
        "apex": d["apex"], "head_radius": d["head_radius"], "mantle_radius": d["mantle_radius"],
        "mantle_length": d["mantle_length"], "arm_length": d["arm_length"], "reach": d["reach"],
        "eye": d["eye"], "dorsal_mantle_length": d["dorsal_mantle_length"],
        "arms": arms_out})
    mesh.parent = rig
    for m in [m for m in mesh.modifiers if m.type == "ARMATURE"]:
        mesh.modifiers.remove(m)
    mod = mesh.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    return {"rig": rig_name, "bones": len(arm_data.bones), "arms": len(arms_out),
            "arm_bones": bones_per_arm}


def read(rig):
    rig = bpy.data.objects[rig] if isinstance(rig, str) else rig
    raw = rig.data.get(PROP)
    return json.loads(raw) if raw else None


# --------------------------------------------------------------------------
# weights
# --------------------------------------------------------------------------

def skin(rig_name, mesh_name=None, sharpness=5.0, max_influences=4, smooth_iterations=6):
    """Weights from the centrelines.

    Every vertex scores each arm and the body by its distance over the local
    radius; a soft minimum over the scores shares it. Skin on an arm goes to
    that arm; web between two arms goes to both in proportion, so the web
    stretches between them instead of tearing off one. Along an arm the share
    is split between the two bones either side of it (a tent over bone
    midpoints), and near the hub it fades into `body`. Head and mantle share
    a blend around the neck."""
    rig = bpy.data.objects[rig_name]
    st = read(rig)
    mesh = bpy.data.objects[mesh_name or st["mesh"]]
    mw = mesh.matrix_world
    V = np.array([tuple(mw @ v.co) for v in mesh.data.vertices])
    n = len(V)
    bones = rig.data.bones
    hub, neck, apex = np.array(st["hub"]), np.array(st["neck"]), np.array(st["apex"])

    # body: distance to hub -> neck -> apex, over a radius profile
    axis = np.array([hub, neck, apex])
    s_b, d_b, L_b = _polyline_param(V, axis)
    neck_s = float(np.linalg.norm(neck - hub))
    # The body's radius narrows to the mouth: the crown under the head belongs
    # to the arms. Held at the head's full radius, the oral disc was body skin,
    # stayed flat while the arm bases turned back to jet, and folded 680 faces.
    head_prof = st["head_radius"] * (0.35 + 0.65 * np.clip(s_b / max(0.6 * neck_s, 1e-9), 0.0, 1.0) ** 2)
    r_b = np.where(s_b < neck_s, head_prof,
                   st["mantle_radius"] * np.sqrt(np.clip(1.0 - ((s_b - neck_s) / max(L_b - neck_s, 1e-9)) ** 2 * 0.85, 0.05, 1.0)))
    score = [d_b / np.maximum(r_b, 1e-3)]
    arm_s = []
    for a in st["arms"]:
        pts = []
        for nm in a["bones"]:
            pts.append(np.array(bones[nm].head_local))
        pts.append(np.array(bones[a["bones"][-1]].tail_local))
        s, dist, L = _polyline_param(V, np.array(pts))
        r = np.interp(s, np.linspace(0, L, len(a["radii"])), a["radii"])
        score.append(dist / np.maximum(r, 0.004))
        arm_s.append((s, L))
    S = np.array(score)                         # (regions, n)
    W = np.exp(-sharpness * (S - S.min(axis=0)))
    W[W < 0.01] = 0.0
    W /= W.sum(axis=0)

    weights = {}

    def add(name, w):
        if name in weights:
            weights[name] += w
        else:
            weights[name] = w.copy()

    # body region -> body / head / mantle along the axis
    wb = W[0]
    t_oral = np.clip(s_b / max(0.35 * neck_s, 1e-9), 0, 1)
    oral = 1.0 - np.vectorize(smooth)(t_oral)
    blend = np.vectorize(smooth)((s_b - (neck_s - 0.3 * st["head_radius"])) / max(0.6 * st["head_radius"] + 0.15 * (L_b - neck_s), 1e-9))
    add("body", wb * oral)
    add("head", wb * (1 - oral) * (1 - blend))
    add("mantle", wb * (1 - oral) * blend)
    # arms
    for j, a in enumerate(st["arms"]):
        w = W[j + 1]
        s, L = arm_s[j]
        nb = len(a["bones"])
        l = L / nb
        root = 1.0 - np.vectorize(smooth)(s / max(0.5 * l, 1e-9))
        add("body", w * root)
        centres = (np.arange(nb) + 0.5) * l
        for k, nm in enumerate(a["bones"]):
            if k == 0:
                tent = np.where(s <= centres[0], 1.0, np.clip(1 - (s - centres[0]) / l, 0, 1))
            elif k == nb - 1:
                tent = np.where(s >= centres[-1], 1.0, np.clip(1 - (centres[-1] - s) / l, 0, 1))
            else:
                tent = np.clip(1 - np.abs(s - centres[k]) / l, 0, 1)
            add(nm, w * (1 - root) * tent)

    names = list(weights)
    M = np.array([weights[k] for k in names])     # (bones, n)
    # Smooth over the surface. The web is a centimetre thick, and its two
    # faces scored a little differently against the arms: at rest nothing
    # shows, but an arm lengthening beside one shortening moved the faces
    # apart and turned the underside inside out at every arm base.
    if smooth_iterations:
        e = np.array([tuple(ed.vertices) for ed in mesh.data.edges])
        deg = np.bincount(e.ravel(), minlength=n).astype(float)
        for _ in range(smooth_iterations):
            acc = np.zeros_like(M)
            np.add.at(acc.T, e[:, 0], M.T[e[:, 1]])
            np.add.at(acc.T, e[:, 1], M.T[e[:, 0]])
            M = 0.5 * M + 0.5 * acc / np.maximum(deg, 1.0)
    # keep the strongest influences
    if max_influences:
        order = np.argsort(-M, axis=0)
        keep = np.zeros_like(M, dtype=bool)
        for i in range(max_influences):
            keep[order[i], np.arange(n)] = True
        M = np.where(keep, M, 0.0)
    tot = M.sum(axis=0)
    M = M / np.where(tot > 0, tot, 1.0)
    mesh.vertex_groups.clear()
    for k, nm in enumerate(names):
        g = mesh.vertex_groups.new(name=nm)
        col = M[k]
        idx = np.nonzero(col > 1e-4)[0]
        # group add by weight buckets keeps this fast
        for w_val in np.unique(np.round(col[idx], 3)):
            sel = idx[np.round(col[idx], 3) == w_val]
            g.add([int(i) for i in sel], float(w_val), "REPLACE")
    covered = float((tot > 0).mean())
    return {"mesh": mesh.name, "rig": rig_name, "groups": len(names), "coverage": round(covered, 4),
            "max_influences": max_influences}


# --------------------------------------------------------------------------
# posing
# --------------------------------------------------------------------------

def _min_rotation(a, b):
    a, b = a.normalized(), b.normalized()
    return a.rotation_difference(b).to_matrix()


class Tentacles:
    """A tentacled rig as values the clips need: rest data, arms as joint
    chains, and `chain` - joint positions to bone matrices."""

    def __init__(self, rig_name):
        from . import motion
        self.rig = bpy.data.objects[rig_name]
        self.st = read(self.rig)
        if not self.st:
            raise ValueError("%s has no tentacle data - run tentacles.build first" % rig_name)
        self.body = motion.Body(self.rig, {"limbs": [], "up": "Z"})
        bones = self.rig.data.bones
        self.arms = []
        for a in self.st["arms"]:
            joints = [bones[nm].head_local.copy() for nm in a["bones"]] + [bones[a["bones"][-1]].tail_local.copy()]
            lengths = [(joints[i + 1] - joints[i]).length for i in range(len(a["bones"]))]
            arm = dict(a)
            arm.update(joints=joints, lengths=lengths, dirv=Vector(a["dir"]))
            self.arms.append(arm)
        self.by_label = {a["label"]: a for a in self.arms}
        self.hub = Vector(self.st["hub"])
        self.floor = self.st["floor"]
        self.rest = self.body.rest

    def chain(self, arm, pts, parent_mat, twist=None):
        """Bone matrices for an arm whose joints are `pts` (n+1 points,
        armature space). The first bone's frame starts as its rest frame
        carried by the posed parent (`body`), and each bone takes its parent's
        frame turned by the smallest rotation onto its own direction - parallel
        transport - so the arm never needs a roll and never flips."""
        rest = self.rest
        pr = rest["body"].to_3x3()
        carried = parent_mat.to_3x3() @ pr.inverted()      # rest -> posed, for the body
        out = {}
        prev_frame = None
        prev_rest = None
        for k, nm in enumerate(arm["bones"]):
            R_rest = rest[nm].to_3x3()
            if prev_frame is None:
                F = carried @ R_rest
            else:
                F = prev_frame @ prev_rest.inverted() @ R_rest
            y = F.col[1]
            want = pts[k + 1] - pts[k]
            if want.length > 1e-9:
                F = _min_rotation(y, want) @ F
            if twist:
                F = Matrix.Rotation(twist[k], 3, want.normalized()) @ F
            M = F.to_4x4()
            M.translation = pts[k]
            out[nm] = M
            prev_frame, prev_rest = F, R_rest
        return out

    def body_mats(self, body_mat, head_rot=None, mantle_scale=(1.0, 1.0, 1.0), mantle_rot=None):
        """body, head, mantle and funnel from a posed body matrix; the mantle
        may squeeze across (X, Z of its bone) and lengthen (Y)."""
        rest = self.rest
        out = {"body": body_mat}
        head = body_mat @ rest["body"].inverted() @ rest["head"]
        if head_rot is not None:
            head = self._turn(head, head_rot)
        out["head"] = head
        mantle = head @ rest["head"].inverted() @ rest["mantle"]
        if mantle_rot is not None:
            mantle = self._turn(mantle, mantle_rot)
        sx, sy, sz = mantle_scale
        out["mantle"] = mantle @ Matrix.Diagonal((sx, sy, sz, 1.0))
        out["funnel"] = head @ rest["head"].inverted() @ rest["funnel"]
        return out

    @staticmethod
    def _turn(M, R3):
        t = M.translation.copy()
        N = (R3 @ M.to_3x3()).to_4x4()
        N.translation = t
        return N

    def arm_base(self, arm, body_mat):
        """Where an arm's first joint and its rest direction ride with the body."""
        carry = body_mat @ self.rest["body"].inverted()
        p0 = carry @ arm["joints"][0]
        d = (carry.to_3x3() @ (arm["joints"][1] - arm["joints"][0])).normalized()
        return p0, d

    def radius_at(self, arm, k):
        return arm["radii"][min(k, len(arm["radii"]) - 1)]


def curve(base, tangent, normal, lengths, kappa_n, kappa_b=None, floor_z=None, radii=None,
          stretch=1.0):
    """Integrate a centreline from curvature. `kappa_n(i)` bends toward
    `normal`, `kappa_b(i)` toward tangent x normal, in radians per metre at
    segment i. With `floor_z`, a segment that would pass under the floor (less
    its radius) is laid along it instead - arc length is kept, so an arm that
    curls into the ground lies on it rather than shortening."""
    t = tangent.normalized()
    nrm = (normal - t * normal.dot(t)).normalized()
    pts = [base.copy()]
    p = base.copy()
    for i, l in enumerate(lengths):
        l = l * (stretch(i) if callable(stretch) else stretch)
        b = t.cross(nrm)
        kn = kappa_n(i) if callable(kappa_n) else kappa_n
        kb = (kappa_b(i) if callable(kappa_b) else kappa_b) if kappa_b is not None else 0.0
        ang = math.hypot(kn, kb) * l
        if ang > 1e-9:
            axis = (b * kn - nrm * kb).normalized()
            R = Matrix.Rotation(ang, 3, axis)
            t, nrm = (R @ t).normalized(), (R @ nrm).normalized()
        q = p + t * l
        if floor_z is not None:
            rad = radii[i + 1] if radii else 0.0
            if q.z < floor_z + rad:
                flat = Vector((t.x, t.y, 0.0))
                if flat.length < 1e-6:
                    flat = Vector((pts[-1].x - base.x, pts[-1].y - base.y, 0.0))
                    flat = flat.normalized() if flat.length > 1e-6 else Vector((0, -1, 0))
                flat.normalize()
                dz = floor_z + rad - p.z
                horiz = math.sqrt(max(l * l - dz * dz, 0.0)) if abs(dz) < l else 0.0
                q = p + flat * horiz + Vector((0, 0, max(min(dz, l), -l)))
                t_new = (q - p).normalized() if (q - p).length > 1e-9 else flat
                nrm = (nrm - t_new * nrm.dot(t_new))
                nrm = nrm.normalized() if nrm.length > 1e-6 else Vector((0, 0, 1))
                t = t_new
        pts.append(q)
        p = q
    return pts


def blend_shapes(a, b, w, base=None):
    """Between two poses of one arm, by segment direction and length rather
    than by joint position. Joints lerped straight across moved through the
    arm's own middle - a curled arm and a straight one met in a pose with a
    segment at a tenth of its length. `w(k)` is the share of shape b for
    segment k, so a blend can travel down the arm; `base` moves the first
    joint (it rides the body)."""
    pts = [base.copy() if base is not None else a[0].lerp(b[0], w(0))]
    for k in range(len(a) - 1):
        da, db = a[k + 1] - a[k], b[k + 1] - b[k]
        la, lb = da.length, db.length
        wk = max(0.0, min(1.0, w(k)))
        if la < 1e-9 or lb < 1e-9:
            d = da.lerp(db, wk)
        else:
            q = da.normalized().rotation_difference(db.normalized())
            d = (Quaternion().slerp(q, wk) @ da.normalized()) * (la + (lb - la) * wk)
        pts.append(pts[-1] + d)
    return pts


def hermite(p0, m0, p1, m1, k, samples=64):
    """k+1 points evenly spaced by arc length along the cubic Hermite curve
    from p0 (tangent m0) to p1 (tangent m1)."""
    dense = []
    for i in range(samples + 1):
        t = i / samples
        h00, h10 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t
        h01, h11 = -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
        dense.append(p0 * h00 + m0 * h10 + p1 * h01 + m1 * h11)
    pts, total = _resample(dense, k)
    return pts, total
