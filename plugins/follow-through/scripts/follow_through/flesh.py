"""Flesh: find the soft parts of a skinned body, and give each a jiggle bone.

A breast, a belly, a buttock, a bloater's torso - each is a mass of soft tissue
standing proud of the body's lean core, carried by a bone it does not move rigidly
with. Games move these with jiggle bones: one extra bone per mass, sprung to its
parent, with the mass's vertices weighted to it. This module finds the masses,
adds the bones, paints the weights and writes the spec the Godot runtime springs.

Nothing about skinning says which vertices are soft: bone heat spread the test
figure's breasts over `shoulder.L` and `spine.004`, and basic_human's own `breast`
bones sat 14 cm below them. So the soft parts come from the surface and the
skeleton together.

  chains      core bones joined into polylines - pelvis to head, each arm, each leg -
              continuing through the most collinear child at a branch. Side bones
              (breast, pelvis, shoulder, heel, the jiggle bones added here) are not core.
  rings       every vertex belongs to its nearest chain at an arc length along it;
              one band of arc length is a ring round the chain, a cross-section.
  envelope    per angular sector, the lean radius along the chain is a local line
              refitted without the rings standing more than 8% above it. A ramp (a
              waist widening into hips) is a line and stays lean; a bump (a buttock on
              the back of the hips) is rejected, and is the excess. A chain's first ring,
              and its last ring built when it is searched to its end, take their radius
              from their wall only (normal across the chain): the spine's first ring is the crotch, and a line starting there read the
              figure's belly 12 cm proud and gave it love handles (05 5.9).
  profile     a mass where one chain ends and the next begins - a buttock, between the
              spine and the thighs - has no rings on both sides of it, so rings cannot
              see it. A type with `"lean": "profile"` is read from the side instead: per
              slice across the body, the silhouette behind the hip joints from the small
              of the back to the back of the thigh, with the same refitted line under it.
  zones       excess alone cannot tell hips from a pinched waist, so every flesh
              type in the registry names a zone of the body - which chain, a height
              between hip and shoulder, a facing, a side - and a region is excess
              inside a zone. A new kind of flesh is a new registry entry.

What was measured and dropped on the way, so nobody tries it again:

  - distance to the strongest-weighted bone, normalised per bone: the shoulder and
    neck bones' own spread swamped the breasts.
  - Taubin smoothing as a lean envelope: 200 passes on a 1.2 cm voxel mesh moved the
    surface under 1.4 mm at the 99th percentile; diffusion crosses about an edge per
    pass and a breast is ten edges across.
  - one ellipse per ring, fixed on the bone: the skull sits ahead of the head bone and
    the whole back of the head read as a bulge. With a free centre, the fit slid
    toward the bulges and erased the belly and buttocks.
  - taking each ring's 30th-percentile excess off every sector, so hips wider all round
    than the waist cancel: it did, and it also cost the figure its buttocks and grew
    every other region. Zones handle hips instead.
  - chains by nearest segment alone: a bloater's wide torso sides went to its A-posed
    upper arms, which pass closer to them than the spine. Chains come from skin weights.
  - buttocks from rings (improvements 05 5.9). The spine's first ring is the crotch
    (0.02 m from the chain at the figure's hip sides, against 0.15-0.17 m of hip), so the
    refitted line started there and the sides of the hips stood 0.10-0.12 m proud: 60% of
    the figure's buttock bone weight came from them (0.13 m off). Rings without the crotch
    (only vertices whose normal is across the chain) lost the buttock instead - 20 seeds,
    a bump at the end of a chain reads as a ramp - and moved every other region. On Belle
    the pelvis chain had four rings, the line hugged the upper buttock and only the fold
    under it stood out (bone head 0.794 m facing down, hips 0.873). Nor did moving the
    butt zone's heights. Read from the side, both samples' buttocks land 0.02-0.04 m from
    their centres and Belle's bone head 1 cm from her marked one read the same way.
"""

from __future__ import annotations

import math
import re

import bpy
import numpy as np

SIDE_BONES = ("breast", "pelvis", "heel", "shoulder", "clavicle", "jiggle", "ft_", "twist",
              "ear", "eye", "jaw", "tongue", "tooth", "teeth", "finger", "thumb", "palm")
COLLINEAR_DEG = 35.0      # a branch continues the chain through a child within this of straight on
SECTORS = 24
BANDS_PER_HEIGHT = 40     # ring thickness = body height / this
OUTLIER = 1.08            # rings this far above the local envelope line are dropped and it is refitted
END_RING_WALL = 0.5       # a chain's first and last ring take radius only from vertices with |normal . axis| under this
ENVELOPE_HALF_WIDTHS = (0.15, 0.30)   # of body height, each side of a ring. Two scales, the larger excess
                                     # kept: 0.18 alone read most of a bloater's 50 cm belly as lean, 0.30
                                     # alone lost a figure's breasts at the top of the spine chain

# a vertex is bulge when it stands this far outside its ring's lean ellipse ...
SEED_EXCESS = 0.012       # ... in metres per metre of body height
SEED_RELATIVE = 0.25      # ... and as a fraction of the lean radius there
GROW_RELATIVE = 0.10      # clusters grow into vertices down to this, so weights feather out
MIN_REGION_FRACTION = 0.003   # of the body's vertices; smaller clusters are noise

# check_placement: a region fails when more than this share of its weight is on head-skinned vertices
HEAD_SHARE_MAX = 0.02

# a type with "attachment": "upper" (breast, butt) hangs from above (_hang_from_above)
ATTACH_UP_M = (0.03, 0.06)      # the pivot's rise above the apex, clipped to this (a type's `attach_rise_m`)
ATTACH_ABOVE_M = 0.10           # check_placement reads the weight this far above the apex (a type's `attach_above_m`)
ATTACH_UNDER_LEAN_M = 0.02      # and its depth under the lean surface there
ATTACH_U0 = 0.3                 # weight is 0 up to this far along pivot -> apex
ATTACH_LEG_OFF = 0.5            # and 0 on a vertex with this share of its skin on a leg, rising to 1 at none
# check_placement on such a type (research-flesh-jiggle.md B and C)
ATTACH_APEX_MIN = 0.9           # mean weight within 2 cm of the tail, at least
ATTACH_ABOVE_MAX = 0.3          # weight 10 cm above the apex, at most
ATTACH_THIGH_MAX = 0.05         # weight on vertices half or more skinned to a leg, at most
# jiggle_block: a material's mass scaling of frequency is clipped to this range
MASS_SCALE = (0.75, 1.33)

# FT_FLESH_LEGACY_PLACEMENT=1 puts back how regions were placed before check_placement existed - the face
# seeding and growing regions, every patch in a zone merged - so check_placement has a control that must
# fail (the cast builds' breast bones on the chin).


def _legacy_placement():
    import os
    return os.environ.get("FT_FLESH_LEGACY_PLACEMENT") == "1"


def armature_of(obj):
    for m in obj.modifiers:
        if m.type == "ARMATURE" and m.object is not None:
            return m.object
    if obj.parent is not None and obj.parent.type == "ARMATURE":
        return obj.parent
    return None


def name_tokens(name):
    """`DEF-breast.L` -> [def, breast, l]; `mixamorig:LeftShoulder` -> [mixamorig, left, shoulder].
    Whole tokens, because substrings lie: `ear` is inside `forearm`."""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return [t for t in re.split(r"[^a-z]+", spaced.lower()) if t]


def _is_side(name, side):
    if name.lower().startswith("ft_"):
        return True
    toks = name_tokens(name)
    return any(t == s or t == s + "s" for t in toks for s in side)


def chains(rig, side=SIDE_BONES):
    """Core bones as polylines. Returns [{"bones": [...], "points": (k+1, 3) world}]."""
    core = {b.name: b for b in rig.data.bones if b.use_deform and not _is_side(b.name, side)}
    if not core:        # a rig whose bones are all "side" by name: use every deform bone
        core = {b.name: b for b in rig.data.bones if b.use_deform}

    def kids(b):
        out = []
        for c in b.children:
            if c.name in core:
                out.append(c)
            else:
                out.extend(kids(c))
        return out

    def par(b):
        p = b.parent
        while p is not None and p.name not in core:
            p = p.parent
        return p

    def straight_on(b):
        d = (b.tail_local - b.head_local).normalized()
        best, best_dot = None, math.cos(math.radians(COLLINEAR_DEG))
        for c in kids(b):
            dc = (c.tail_local - c.head_local).normalized()
            if d.dot(dc) > best_dot:
                best, best_dot = c, d.dot(dc)
        if best is None and len(kids(b)) == 1:
            best = kids(b)[0]
        return best

    continued = set()
    for b in core.values():
        nxt = straight_on(b)
        if nxt is not None:
            continued.add(nxt.name)
    mw = rig.matrix_world
    out = []
    for b in core.values():
        if b.name in continued:
            continue
        ch = [b]
        while True:
            nxt = straight_on(ch[-1])
            if nxt is None:
                break
            ch.append(nxt)
        pts = [tuple(mw @ ch[0].head_local)] + [tuple(mw @ x.tail_local) for x in ch]
        out.append({"bones": [x.name for x in ch], "points": np.array(pts, dtype=float)})
    return out


def _world_vertices(obj):
    me = obj.data
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    M = np.array(obj.matrix_world)
    return co.reshape(n, 3) @ M[:3, :3].T + M[:3, 3]


def _world_normals(obj):
    me = obj.data
    n = len(me.vertices)
    no = np.empty(n * 3)
    me.vertices.foreach_get("normal", no)
    R = np.array(obj.matrix_world.to_3x3().inverted().transposed())
    no = no.reshape(n, 3) @ R.T
    return no / np.maximum(np.linalg.norm(no, axis=1)[:, None], 1e-12)


def _edges(obj):
    me = obj.data
    e = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", e)
    return e.reshape(-1, 2)


def bone_roles(rig, obj=None):
    """rig-anything's bone roles for `rig` (`bodymap.build(...)["roles"]`), or None.

    Roles name bones by what they do - `pelvis` (where the legs attach), `chest` (where the arms
    attach), `head`, and each limb's girdle, upper, lower and end - so a flesh type's `anchor` and the
    body's hip and shoulder heights are read, not searched for. Used only when rig-anything's
    `rig_analysis` is importable and knows roles; everything here has a fallback without it."""
    try:
        from rig_analysis import bodymap
    except ImportError:
        return None
    bm = bodymap.build(rig.name, meshes=[obj] if obj is not None else None)
    roles = bm.get("roles") if isinstance(bm, dict) else None
    return roles or None


def _role_bone(rig, roles, role):
    """The bone a role names on `rig`, or None: an unknown role, a list role, or no roles at all."""
    name = (roles or {}).get(role)
    return name if isinstance(name, str) and rig is not None and name in rig.data.bones else None


def body_frame(rig, chs, P, roles=None):
    """Up, forward and lateral for the body, and landmark heights.

    Up is world Z (Blender). Forward is the side the feet point to when there are
    feet (toe bones ahead of the ankle), else -Y, rig-anything's convention.
    Lateral is up x forward. Heights are hip (where the legs join), shoulder
    (where the arms join) and the body's top and bottom: from `roles` (the legs' upper
    bones, the arms' girdles and upper bones) when given, else from bone names."""
    up = np.array([0.0, 0.0, 1.0])
    fwd = None
    names = {b.name.lower(): b for b in rig.data.bones}
    mw = rig.matrix_world
    feet = [b for n, b in names.items() if "toe" in n or "foot" in n]
    if feet:
        v = np.zeros(3)
        for b in feet:
            d = np.array(tuple(mw @ b.tail_local)) - np.array(tuple(mw @ b.head_local))
            d[2] = 0.0
            v += d
        if np.linalg.norm(v) > 1e-6:
            fwd = v / np.linalg.norm(v)
    if fwd is None:
        fwd = np.array([0.0, -1.0, 0.0])
    lat = np.cross(fwd, up)

    def join_height(words):
        zs = [(mw @ b.head_local).z for n, b in names.items() if any(w in n for w in words)]
        return float(max(zs)) if zs else None

    def limb_height(role, parts):
        zs = [(mw @ rig.data.bones[n].head_local).z
              for limb in ((roles or {}).get("limbs") or {}).values() if limb.get("role") == role
              for n in (limb.get(k) for k in parts) if n and n in rig.data.bones]
        return float(max(zs)) if zs else None

    lo, hi = float(P[:, 2].min()), float(P[:, 2].max())
    hip = limb_height("leg", ("upper",))
    if hip is None:
        hip = join_height(("thigh", "upper_leg", "upperleg", "hip"))
    shoulder = limb_height("arm", ("girdle", "upper"))
    if shoulder is None:
        shoulder = join_height(("upper_arm", "upperarm", "shoulder", "clavicle"))
    return {"up": up, "forward": fwd, "lateral": lat, "bottom": lo, "top": hi,
            "hip": hip if hip is not None else lo + 0.5 * (hi - lo),
            "shoulder": shoulder if shoulder is not None else lo + 0.8 * (hi - lo),
            "mid_lateral": float(np.median(P @ lat))}


def tissue(obj_name, rig_name=None, side=SIDE_BONES):
    """Per-vertex soft tissue measures for a skinned body. See the module docstring."""
    obj = bpy.data.objects[obj_name]
    rig = bpy.data.objects[rig_name] if rig_name else armature_of(obj)
    if rig is None:
        return {"error": f"{obj_name} has no armature - flesh is measured against a skeleton"}
    obj.users_scene[0].view_layers[0].update()
    P = _world_vertices(obj)
    n = len(P)
    chs = chains(rig, side)
    roles = bone_roles(rig, obj)
    frame = body_frame(rig, chs, P, roles)
    H = max(frame["top"] - frame["bottom"], 1e-6)

    # nearest point on every chain, for every vertex
    C = len(chs)
    dist_c = np.full((C, n), np.inf)
    arc_c = np.zeros((C, n))
    cap_c = np.zeros((C, n), dtype=bool)
    for ci, ch in enumerate(chs):
        pts = ch["points"]
        acc = 0.0
        for si in range(len(pts) - 1):
            h = pts[si]
            d = pts[si + 1] - h
            L = float(np.linalg.norm(d))
            if L < 1e-9:
                continue
            f_raw = ((P - h) @ d) / (L * L)
            f = np.clip(f_raw, 0.0, 1.0)
            dist = np.linalg.norm(P - (h + f[:, None] * d), axis=1)
            m = dist < dist_c[ci]
            dist_c[ci, m] = dist[m]
            arc_c[ci, m] = acc + f[m] * L
            end_cap = ((si == 0) & (f_raw < 0.0)) | ((si == len(pts) - 2) & (f_raw > 1.0))
            cap_c[ci, m] = end_cap[m]
            acc += L
        ch["length"] = acc
    # Which chain a vertex belongs to comes from its skin: the chain of its strongest bone,
    # or of that bone's nearest core ancestor (shoulder -> spine). Nearest-chain alone gave
    # a bloater's wide torso sides to its A-posed upper arms, which pass closer to them than
    # the spine does; bone heat diffuses through the body and knows better.
    chain_of = np.argmin(dist_c, axis=0)
    by_skin = _chain_from_skin(obj, rig, chs)
    has = by_skin >= 0
    chain_of[has] = by_skin[has]
    cols = np.arange(n)
    arc = arc_c[chain_of, cols]
    cap = cap_c[chain_of, cols]

    # Where flesh is looked for. The spine chain (the one reaching highest) stops at
    # the shoulders: a skull is itself a bump along the chain, and the envelope below
    # would call the whole head a bulge. Limbs keep their first two segments - upper
    # arm and forearm, thigh and shin; hands and feet have no jiggle to find.
    spine_ci = int(np.argmax([c["points"][:, 2].max() for c in chs]))
    searched = ~cap
    for ci, ch in enumerate(chs):
        on = chain_of == ci
        if ci == spine_ci:
            # well above the shoulder joints: a fitted rig can put them 12 cm under the top
            # of the shoulders, and a cut just above them excluded a bloater's chest
            cut = on & ~cap & (P[:, 2] > frame["shoulder"] + 0.10 * H)
            searched &= ~cut
            ch["role"] = "spine"
            # its end is searched only when the shoulder cut takes nothing of it (a spine
            # stopping below the shoulders); otherwise its top ring is a slice at the cut
            ch["to_end"] = not bool(cut.any())
        else:
            seg_len = np.linalg.norm(np.diff(ch["points"], axis=0), axis=1)
            limit = seg_len[:2].sum() if len(seg_len) > 2 else ch["length"]
            searched &= ~(on & (arc > limit))
            ch["role"] = "limb"
            # searched to its end only when the limit is its length (two segments or fewer). A
            # longer limb's last searched ring is the wrist or ankle, a slice through it - even
            # when no hand vertex happens to be skinned to the chain
            ch["to_end"] = len(seg_len) <= 2
    # The face is never flesh. The shoulder cut above sits 0.1 x height over the shoulder joints, which
    # on a slim fitted body is above the chin: the chin stands well out of the neck's lean envelope, and
    # the cast's Mei and Ruth got their breast bones on it (1.66-1.71 m, lips weighted 100 % to them)
    # while their breasts never moved. A vertex skinned mostly to the head or a bone under it neither
    # seeds nor grows a region (find_regions). It still shapes the envelope: taking the neck's rings out
    # of the fit lowered the upper-chest line and cut the sample Figure's breasts from 687 to 458
    # vertices, and its sports top then failed its cover check.
    head_skinned = _head_skinned(obj, rig, roles)

    band = H / BANDS_PER_HEIGHT
    halves = [max(2, int(round(hw * H / band))) for hw in ENVELOPE_HALF_WIDTHS]
    normals = _world_normals(obj)
    lean = np.zeros(n)
    excess = np.zeros(n)
    rings = 0
    for ci, ch in enumerate(chs):
        pts = ch["points"]
        idx = np.where((chain_of == ci) & searched)[0]
        if len(idx) < SECTORS:
            continue
        seg_len = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        seg_start = np.concatenate([[0.0], np.cumsum(seg_len)[:-1]])
        nb = int(math.ceil(ch["length"] / band)) + 1
        R = np.full((nb, SECTORS), np.nan)      # median radius per ring and sector
        r_of = np.zeros(len(idx))
        k_of = np.minimum((arc[idx] / band).astype(int), nb - 1)
        # the last ring built: arc stops at the chain's length (past it is cap), so the last ring
        # holding vertices is int(length / band) - ring nb - 1 only when the length is a whole
        # number of bands - or the one before it when that sliver is too thin to build
        counts = np.bincount(k_of, minlength=nb)
        built = np.where(counts >= SECTORS // 2)[0]
        last = int(built.max()) if ch["to_end"] and len(built) else -1
        s_of = np.zeros(len(idx), dtype=int)
        for k in range(nb):
            mk = k_of == k
            if mk.sum() < SECTORS // 2:
                continue
            sel = idx[mk]
            s0 = (k + 0.5) * band
            si = int(np.clip(np.searchsorted(seg_start, s0, side="right") - 1, 0, len(seg_len) - 1))
            ax = (pts[si + 1] - pts[si]) / max(seg_len[si], 1e-9)
            ref = frame["forward"] if abs(ax @ frame["forward"]) < 0.9 else frame["up"]
            e2 = ref - (ref @ ax) * ax
            e2 /= np.linalg.norm(e2)
            e1 = np.cross(e2, ax)
            # radius from each vertex's own foot point on the chain, so a bend in the
            # chain inside one band does not smear the ring
            foot = _foot_points(P[sel], pts, arc[sel], seg_start, seg_len)
            rel = P[sel] - foot
            th = np.arctan2(rel @ e2, rel @ e1)
            r = np.linalg.norm(rel, axis=1)
            sec = ((th + math.pi) / (2 * math.pi) * SECTORS).astype(int) % SECTORS
            r_of[mk] = r
            s_of[mk] = sec
            # A chain's end ring is a cap across it as well as a wall round it: the spine's first
            # ring is the crotch, 0.02 m from the chain where the hip sides are 0.15 m, and a
            # line starting there skews the whole torso (05 5.9). An end ring's radius comes
            # from its wall - vertices whose normal is across the chain - and every vertex in it
            # is still measured against that. The last ring counts only on a chain searched to
            # its end; a ring at a search cut is a slice through the body, not a cap.
            wall = np.ones(len(sel), dtype=bool)
            if k == 0 or k == last:
                wall = np.abs(normals[sel] @ ax) < END_RING_WALL
            for s in range(SECTORS):
                hit = r[(sec == s) & wall]
                if len(hit):
                    R[k, s] = np.median(hit)
            rings += 1
        env = _nanmin_quiet(np.stack([_lower_envelope(R, h) for h in halves]))
        lv = env[k_of, s_of]
        good = ~np.isnan(lv)
        lean[idx[good]] = lv[good]
        excess[idx[good]] = r_of[good] - lv[good]
    relative = np.where(lean > 0, excess / np.maximum(lean, 1e-9), 0.0)
    return {"object": obj.name, "rig": rig.name, "P": P, "height": H, "chains": chs,
            "chain_of": chain_of, "arc": arc, "searched": searched, "lean": lean,
            "excess": excess, "relative": relative, "frame": frame, "rings": rings,
            "roles": roles, "radius": dist_c[chain_of, cols], "head_skinned": head_skinned}


def _head_bones(rig, roles):
    """The head bone (its rig-anything role, else a bone named `head`) and every bone under it that is not
    one of follow-through's own: the jaw, lips, eyes and tongue move the face, not flesh."""
    name = _role_bone(rig, roles, "head")
    if name is None:
        name = next((b.name for b in rig.data.bones if b.name.lower() == "head"), None)
    if name is None:
        return set()
    out, stack = set(), [rig.data.bones[name]]
    while stack:
        b = stack.pop()
        if b.name.startswith("ft_"):
            continue
        out.add(b.name)
        stack.extend(b.children)
    return out


def _head_skinned(obj, rig, roles):
    """Per vertex, whether its strongest bone weight (follow-through's own bones left out) is a head bone."""
    head = _head_bones(rig, roles)
    out = np.zeros(len(obj.data.vertices), dtype=bool)
    if not head:
        return out
    group_name = {g.index: g.name for g in obj.vertex_groups}
    for v in obj.data.vertices:
        best, bw = None, 0.0
        for x in v.groups:
            gname = group_name.get(x.group, "")
            if x.weight > bw and not gname.startswith("ft_"):
                best, bw = gname, x.weight
        out[v.index] = best in head
    return out


def _chain_from_skin(obj, rig, chs):
    """Per vertex, the index of the chain holding its strongest-weighted bone (or that bone's
    nearest ancestor on a chain), or -1 where the vertex has no bone weight."""
    on_chain = {b: ci for ci, ch in enumerate(chs) for b in ch["bones"]}
    bones = rig.data.bones
    resolve = {}
    for b in bones:
        cur = b
        while cur is not None and cur.name not in on_chain:
            cur = cur.parent
        resolve[b.name] = on_chain[cur.name] if cur is not None else -1
    group_chain = {g.index: resolve.get(g.name, -1) for g in obj.vertex_groups}
    out = np.full(len(obj.data.vertices), -1, dtype=int)
    for v in obj.data.vertices:
        best_w = 0.0
        for x in v.groups:
            c = group_chain.get(x.group, -1)
            if c >= 0 and x.weight > best_w:
                best_w = x.weight
                out[v.index] = c
    return out


def _foot_points(Q, pts, arcs, seg_start, seg_len):
    si = np.clip(np.searchsorted(seg_start, arcs, side="right") - 1, 0, len(seg_len) - 1)
    d = pts[si + 1] - pts[si]
    t = np.clip((arcs - seg_start[si]) / np.maximum(seg_len[si], 1e-9), 0.0, 1.0)
    return pts[si] + d * t[:, None]


def _lower_envelope(R, half):
    """The lean radius map under a (rings x sectors) radius map.

    Per sector, a local straight line through the rings within `half` of each ring,
    refitted without the rings standing more than OUTLIER above it. A ramp - a
    waist narrowing into the hips - is a line and stays lean; a bump - a buttock
    on the back of the hips, a breast on the chest - is rejected and left as excess.
    Neighbouring sectors are then averaged, since a bulge's edge should not jump."""
    nb, ns = R.shape
    env = np.full_like(R, np.nan)
    ks = np.arange(nb, dtype=float)
    for s in range(ns):
        col = R[:, s]
        for k in range(nb):
            if np.isnan(col[k]):
                continue
            lo, hi = max(0, k - half), min(nb, k + half + 1)
            x = ks[lo:hi]
            y = col[lo:hi]
            use = ~np.isnan(y)
            val = None
            for _ in range(6):
                if use.sum() < 3:
                    break
                c1, c0 = np.polyfit(x[use], y[use], 1)
                fit = c1 * x + c0
                val = c1 * k + c0
                nxt = ~np.isnan(y) & (y <= fit * OUTLIER)
                if np.array_equal(nxt, use):
                    break
                use = nxt
            env[k, s] = col[k] if val is None else min(val, col[k])
    out = env.copy()
    for s in range(ns):
        stack = np.stack([env[:, (s - 1) % ns], env[:, s], env[:, (s + 1) % ns]])
        out[:, s] = _nanmean_quiet(stack)
    return np.where(np.isnan(env), np.nan, out)


# A ring with too few vertices to build (a sliver at a chain's end, a sector no vertex faces) is NaN
# all the way down its column, and numpy's nanmin / nanmean warn on every such column. The warnings
# read like failures in a build log and meant nothing: these give the same numbers without them.

def _nanmin_quiet(stack):
    """np.nanmin(stack, axis=0), NaN where a column is all NaN, without the RuntimeWarning."""
    return np.fmin.reduce(stack, axis=0)


def _nanmean_quiet(stack):
    """np.nanmean(stack, axis=0), NaN where a column is all NaN, without the RuntimeWarning."""
    ok = ~np.isnan(stack)
    n = ok.sum(axis=0)
    total = np.where(ok, stack, 0.0).sum(axis=0)
    return np.where(n > 0, total / np.maximum(n, 1), np.nan)


def _profile(t, facing_back=True):
    """How far each vertex stands out of the body seen from the side, across chains.

    Per slice across the body (a band wide) and per band of height, the silhouette is the
    furthest skin behind the hip joints (or ahead of them, `facing_back=False`) among vertices
    facing that way, arms left out. `_lower_envelope` runs down each slice as it runs along a
    chain, so the lean line goes from the small of the back to the back of the thigh and a
    buttock between them stands out of it. Excess is how far a vertex is behind that line; its
    lean is its distance from its chain less that excess, so `relative` means what it does
    for rings. Cached in `t`."""
    key = "_profile_back" if facing_back else "_profile_front"
    if key in t:
        return t[key]
    P = t["P"]
    n = len(P)
    f = t["frame"]
    H = t["height"]
    band = H / BANDS_PER_HEIGHT
    halves = [max(2, int(round(hw * H / band))) for hw in ENVELOPE_HALF_WIDTHS]
    out_dir = -f["forward"] if facing_back else f["forward"]
    normals = _world_normals(bpy.data.objects[t["object"]])
    mid_z = 0.5 * (f["hip"] + f["shoulder"])
    arm = np.zeros(n, dtype=bool)
    hips = []
    for ci, ch in enumerate(t["chains"]):
        if ch.get("role") == "spine":
            continue
        if ch["points"][0, 2] > mid_z:
            arm |= t["chain_of"] == ci
        elif abs(ch["points"][0, 2] - f["hip"]) < 0.02 * H:
            hips.append(ch["points"][0])
    ref = float(np.mean([h @ out_dir for h in hips])) if hips else float(np.median(P @ out_dir))
    depth = P @ out_dir - ref
    use = np.where(((normals @ out_dir) > 0.0) & ~arm & (depth > 0.0))[0]
    excess, lean, searched = np.zeros(n), np.zeros(n), np.zeros(n, dtype=bool)
    if len(use) >= SECTORS:
        # a slice of empty columns each side, so the envelope's neighbour averaging, which wraps
        # round like sectors do, never mixes the body's two sides
        col = np.floor((P[use] @ f["lateral"] - f["mid_lateral"]) / band).astype(int)
        col -= col.min() - 1
        row = np.floor((P[use, 2] - f["bottom"]) / band).astype(int)
        S = np.full((row.max() + 1, col.max() + 2), np.nan)
        np.fmax.at(S, (row, col), depth[use])
        env = _nanmin_quiet(np.stack([_lower_envelope(S, h) for h in halves]))
        lv = env[row, col]
        good = ~np.isnan(lv)
        v = use[good]
        excess[v] = depth[v] - lv[good]
        lean[v] = np.maximum(t["radius"][v] - np.maximum(excess[v], 0.0), 0.01 * H)
        searched[v] = True
    relative = np.where(lean > 0, excess / np.maximum(lean, 1e-9), 0.0)
    t[key] = {"excess": excess, "lean": lean, "relative": relative, "searched": searched}
    return t[key]


def measured(t, entry):
    """The tissue measure a flesh type is read with: `t` itself (rings), or with a type's
    `"lean": "profile"` its excess, lean, relative and searched from `_profile`, from behind when
    the type's zone faces back (a mean facing over 90 degrees)."""
    if (entry or {}).get("lean") != "profile":
        return t
    facing = (entry.get("zone") or {}).get("facing_deg", [0, 180])
    return dict(t, **_profile(t, facing_back=0.5 * (facing[0] + facing[1]) > 90.0))


def shown(t, c=None):
    """Excess and relative per vertex as a heat map should draw them: rings, except inside the
    (grown) zone of a type read by `"lean": "profile"`, where each vertex the profile searched
    shows the profile. A heat drawn from rings alone put a buttock's heat on the hip sides and
    the fold under it, where `find_regions` no longer looks (05 5.9)."""
    from . import registry
    c = c if c is not None else coordinates(t)
    excess, relative = t["excess"].copy(), t["relative"].copy()
    for entry in registry.types_for(cls="flesh").values():
        if entry.get("lean") != "profile":
            continue
        tt = measured(t, entry)
        m = tt["searched"] & _in_zone(_grown_zone(entry.get("zone") or {}), c)
        excess[m] = tt["excess"][m]
        relative[m] = tt["relative"][m]
    return excess, relative



def coordinates(t):
    """Where each vertex is on the body, in the terms zones are written in.

      height    0 at the hip joints, 1 at the shoulder joints; the legs are negative
      facing    degrees between the vertex's outward direction and the body's forward,
                in the horizontal plane: 0 front, 90 side, 180 back
      lateral   distance from the midline over half the shoulder width
      side      +1 on the body's left (Blender .L), -1 on its right
      role      spine, arm or leg, from the chain; segment is the bone index on it
    """
    P = t["P"]
    f = t["frame"]
    n = len(P)
    fwd, up = f["forward"], f["up"]
    left = np.cross(up, fwd)
    span = max(f["shoulder"] - f["hip"], 1e-6)
    height = (P[:, 2] - f["hip"]) / span
    outward = np.zeros((n, 3))
    segment = np.zeros(n, dtype=int)
    role = np.full(n, "spine", dtype=object)
    mid_z = 0.5 * (f["hip"] + f["shoulder"])
    for ci, ch in enumerate(t["chains"]):
        pts = ch["points"]
        if ch.get("role") == "spine":
            ch["kind"] = "spine"
        else:
            ch["kind"] = "arm" if pts[0, 2] > mid_z else "leg"
        on = t["chain_of"] == ci
        if not on.any():
            continue
        seg_len = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        seg_start = np.concatenate([[0.0], np.cumsum(seg_len)[:-1]])
        foot = _foot_points(P[on], pts, t["arc"][on], seg_start, seg_len)
        outward[on] = P[on] - foot
        segment[on] = np.clip(np.searchsorted(seg_start, t["arc"][on], side="right") - 1, 0, len(seg_len) - 1)
        role[on] = ch["kind"]
    horiz = outward - np.outer(outward @ up, up)
    hn = np.linalg.norm(horiz, axis=1)
    cosf = np.where(hn > 1e-9, (horiz @ fwd) / np.maximum(hn, 1e-9), 1.0)
    facing = np.degrees(np.arccos(np.clip(cosf, -1.0, 1.0)))
    signed = P @ left - float(np.median(P @ left))
    half_width = _half_shoulder_width(t, left)
    return {"height": height, "facing": facing, "lateral": np.abs(signed) / half_width,
            "side": np.sign(signed), "role": role, "segment": segment, "half_width": half_width}


def _half_shoulder_width(t, left):
    arms = [c for c in t["chains"] if c.get("kind") == "arm"]
    if len(arms) >= 2:
        xs = sorted(float(c["points"][0] @ left) for c in arms)
        return max(0.5 * (xs[-1] - xs[0]), 1e-3)
    return 0.12 * t["height"]


def _vertex_areas(obj):
    me = obj.data
    area = np.zeros(len(me.vertices))
    s = obj.matrix_world.to_scale()
    k = abs(s.x * s.y * s.z) ** (2.0 / 3.0)
    for poly in me.polygons:
        share = poly.area * k / len(poly.vertices)
        for v in poly.vertices:
            area[v] += share
    return area


def _adjacency(obj):
    E = _edges(obj)
    n = len(obj.data.vertices)
    nbr = [[] for _ in range(n)]
    for a, b in E:
        nbr[a].append(int(b))
        nbr[b].append(int(a))
    return nbr


def _in_zone(zone, c):
    m = np.ones(len(c["height"]), dtype=bool)
    chain = zone.get("chain", "any")
    if chain != "any":
        m &= c["role"] == chain
    if "height" in zone:
        m &= (c["height"] >= zone["height"][0]) & (c["height"] <= zone["height"][1])
    if "facing_deg" in zone:
        m &= (c["facing"] >= zone["facing_deg"][0]) & (c["facing"] <= zone["facing_deg"][1])
    if "lateral" in zone:
        m &= (c["lateral"] >= zone["lateral"][0]) & (c["lateral"] <= zone["lateral"][1])
    if "segment" in zone:
        m &= c["segment"] == int(zone["segment"])
    return m


# which flesh types are looked for first: a vertex belongs to the first region that claims it
ORDER = ("bloater_belly", "breast", "butt", "belly", "love_handle", "arm_flab", "thigh")


# ------------------------------------------------------------------ regions

def find_regions(obj_name, rig_name=None, types=None, t=None):
    """Soft masses on a skinned body, typed by the registry's flesh zones.

    Returns {"regions": [...], "declined": [...], "missed": [...], "tissue": t, "coords": c}.
    Each region has its vertices and weights, its size, where its jiggle bone goes, and why it
    got its type. `missed` has one entry per type looked for that came out with no region at
    all, saying why with the numbers (see `_miss`); `declined` keeps the one-line notes, which
    also cover a type that was found on one side only."""
    from . import registry
    obj = bpy.data.objects[obj_name]
    t = t or tissue(obj_name, rig_name)
    if "error" in t:
        return t
    c = coordinates(t)
    H = t["height"]
    n = len(t["P"])
    area = _vertex_areas(obj)
    nbr = _adjacency(obj)
    normals = _world_normals(obj)
    body_volume = _mesh_volume(obj)
    flesh_types = registry.types_for(cls="flesh")
    order = [x for x in ORDER if x in flesh_types] + sorted(x for x in flesh_types if x not in ORDER)
    if types is not None:
        order = [x for x in order if x in types]
    claimed = np.zeros(n, dtype=bool)
    claimed_by = np.full(n, "", dtype=object)      # which type took each vertex, for a miss's reason
    name_toks = set(registry.name_tokens(obj.name))
    min_size = max(8, int(MIN_REGION_FRACTION * n))
    regions, declined, missed = [], [], []
    legacy = _legacy_placement()
    not_face = np.ones(n, dtype=bool) if legacy else ~t.get("head_skinned", np.zeros(n, dtype=bool))
    for tname in order:
        entry = flesh_types[tname]
        zone = entry["zone"]
        tt = measured(t, entry)       # rings, or the side profile for a type that asks for it
        seed_all = (tt["excess"] > SEED_EXCESS * H) & (tt["relative"] > SEED_RELATIVE) & tt["searched"] & not_face
        grow_all = (tt["relative"] > GROW_RELATIVE) & tt["searched"] & not_face
        in_zone = _in_zone(zone, c)
        seeds = seed_all & in_zone & ~claimed
        if seeds.sum() < min_size:
            declined.append(f"{tname}: {int(seeds.sum())} bulging vertices in its zone")
            missed.append(_miss(tname, entry, tt, in_zone, claimed, claimed_by, seed_all, H, min_size))
            continue
        # grow from the seeds through vertices that still bulge a little, within a
        # slightly larger zone, so the weights can feather to nothing at the edge
        allowed = (grow_all & _in_zone(_grown_zone(zone), c) & ~claimed) | seeds
        comps = [cmp for cmp in _components(np.where(seeds)[0], allowed, nbr) if len(cmp) >= min_size]
        if not comps:
            declined.append(f"{tname}: bulges in its zone were each under {min_size} vertices")
            missed.append(_miss(tname, entry, tt, in_zone, claimed, claimed_by, seed_all, H, min_size, reason="too_small"))
            continue
        groups = []
        members = sorted(v for cmp in comps for v in cmp)
        nearest = entry.get("patches") == "nearest" and not legacy
        if entry.get("paired"):
            for side, suffix in ((1.0, ".L"), (-1.0, ".R")):
                on_side = lambda v: c["side"][v] == side or (c["side"][v] == 0 and side > 0)
                if nearest:
                    # one mass a side: the patch nearest the zone's centre, not every bulge in the zone
                    # merged, whose excess^2 centre can land on whichever patch stands out most
                    parts = [[v for v in cmp if on_side(v)] for cmp in comps]
                    parts = [p for p in parts if len(p) >= min_size]
                    verts = np.array(sorted(min(parts, key=lambda p: _zone_distance(zone, c, p))) if parts else [],
                                     dtype=int)
                else:
                    verts = np.array([v for v in members if on_side(v)], dtype=int)
                if len(verts) >= min_size:
                    groups.append((tname + suffix, verts))
        else:
            groups.append((tname, np.array(members, dtype=int)))
        kept = 0
        last_why = None
        for rname, verts in groups:
            reg = _region(obj, tt, c, rname, tname, entry, verts, area, normals, body_volume, nbr)
            when = entry.get("when", {})
            named = bool(name_toks & set(entry.get("names", [])))
            need = when.get("volume_fraction_min", 0.0)
            need_peak = when.get("peak_over_height_min", 0.0)
            if reg["volume_fraction"] < need or reg["peak_m"] / H < need_peak:
                why = (f"{tname}: needs {need:.0%} of the body's volume and to stand {need_peak:.0%} of its "
                       f"height out; has {reg['volume_fraction']:.1%} and {reg['peak_m'] / H:.1%}")
                if not named:
                    declined.append(why)
                    last_why = (reg, need, need_peak)
                    continue
                reg["evidence"].append(why + " - taken anyway, the name says so")
            if named:
                reg["evidence"].append(f"name agrees: {obj.name}")
            regions.append(reg)
            claimed[verts] = True
            claimed_by[verts] = tname
            kept += 1
        if not kept:
            m = _miss(tname, entry, tt, in_zone, claimed, claimed_by, seed_all, H, min_size,
                      reason="too_small" if last_why is None else "too_little")
            if last_why is not None:
                reg, need, need_peak = last_why
                m.update({"volume_fraction": reg["volume_fraction"], "volume_fraction_min": need,
                          "region_peak_m": reg["peak_m"], "peak_over_height": round(reg["peak_m"] / H, 4),
                          "peak_over_height_min": need_peak})
                m["message"] += (f"; its bulge holds {reg['volume_fraction']:.1%} of the body's volume (needs "
                                 f"{need:.0%}) and stands {reg['peak_m'] / H:.1%} of its height out "
                                 f"(needs {need_peak:.0%})")
            missed.append(m)
    return {"object": obj.name, "rig": t["rig"], "regions": regions, "declined": declined, "missed": missed,
            "tissue": t, "coords": c, "body_volume_m3": round(body_volume, 5)}


def _miss(tname, entry, tt, in_zone, claimed, claimed_by, seed_all, H, min_size, reason=None):
    """Why a flesh type looked for came out with no region, with the numbers a spec author needs.

    `reason` is one of
      zone_empty         no vertex the measure searched lies in the type's zone
      claimed            the zone's bulge was taken by a type looked for earlier (ORDER)
      below_threshold    the zone's skin never stands out far enough to seed a region: its peak
                         excess (m) and relative excess against SEED_EXCESS x height and SEED_RELATIVE
      too_small          it seeded, but fewer than `min_size` vertices, or in pieces each under it
      too_little         a region was built but falls short of the type's `when` volume / peak
    """
    zone_n = int(in_zone.sum())
    looked = in_zone & tt["searched"]
    free = looked & ~claimed
    need_m = SEED_EXCESS * H
    exc = tt["excess"][free]
    rel = tt["relative"][free]
    peak = float(exc.max()) if len(exc) else 0.0
    peak_rel = float(rel.max()) if len(rel) else 0.0
    seeds = int((seed_all & free).sum())
    seeds_claimed = int((seed_all & looked & claimed).sum())
    takers = {}
    for who in claimed_by[looked & claimed]:
        takers[who] = takers.get(who, 0) + 1
    if reason is None:
        if not looked.any():
            reason = "zone_empty"
        elif seeds_claimed >= min_size and seeds < min_size:
            reason = "claimed"
        elif seeds == 0:
            reason = "below_threshold"
        else:
            reason = "too_small"
    out = {"type": tname, "reason": reason, "zone_vertices": zone_n, "searched": int(looked.sum()),
           "claimed": int((looked & claimed).sum()), "peak_excess_m": round(peak, 4),
           "seed_excess_m": round(need_m, 4), "peak_relative": round(peak_rel, 3),
           "seed_relative": SEED_RELATIVE, "over_excess": int((free & (tt["excess"] > need_m)).sum()),
           "over_relative": int((free & (tt["relative"] > SEED_RELATIVE)).sum()),
           "seeds": seeds, "min_size": int(min_size),
           "claimed_by": dict(sorted(takers.items())),
           "measure": "profile" if (entry or {}).get("lean") == "profile" else "rings"}
    lead = {
        "zone_empty": f"no searched vertex in its zone ({zone_n} vertices in the zone, none on a searched ring)",
        "claimed": (f"its zone's bulge ({seeds_claimed} seed vertices) was already taken by "
                    + ", ".join(f"{k} ({v} vertices)" for k, v in sorted(takers.items()))
                    + ", looked for before it"),
        "below_threshold": "peak below threshold",
        "too_small": f"{seeds} seed vertices, fewer than {min_size} or in pieces each under it",
        "too_little": "a bulge too slight for the type",
    }[reason]
    out["message"] = (f"{tname}: {lead}: in its zone the skin stands at most {peak:.4f} m out (a seed needs "
                      f"{need_m:.4f} m = {SEED_EXCESS} x height {H:.2f} m) and {peak_rel:.0%} of its lean "
                      f"radius (needs {SEED_RELATIVE:.0%}); {out['over_excess']} vertices pass the first, "
                      f"{out['over_relative']} the second, {seeds} both (a region needs {min_size}); "
                      f"{out['searched']} of {zone_n} zone vertices searched, {out['claimed']} claimed")
    return out


def _zone_distance(zone, c, verts):
    """How far a patch's mean place is from the middle of `zone`, each coordinate over the zone's own range."""
    d2 = 0.0
    for k in ("height", "facing", "lateral"):
        key = "facing_deg" if k == "facing" else k
        if key not in zone:
            continue
        lo, hi = zone[key]
        mid, half = 0.5 * (lo + hi), max(0.5 * (hi - lo), 1e-6)
        d2 += ((float(np.mean(c[k][verts])) - mid) / half) ** 2
    return d2


def _grown_zone(zone):
    """A zone a little larger than `zone`, which a region grows into from its seeds."""
    loose = dict(zone)
    if "height" in loose:
        loose["height"] = [zone["height"][0] - 0.1, zone["height"][1] + 0.1]
    if "facing_deg" in loose:
        loose["facing_deg"] = [max(0, zone["facing_deg"][0] - 20), min(180, zone["facing_deg"][1] + 20)]
    return loose


def _components(seeds, allowed, nbr):
    seen = set()
    out = []
    for s in seeds:
        s = int(s)
        if s in seen:
            continue
        comp = []
        stack = [s]
        seen.add(s)
        while stack:
            v = stack.pop()
            comp.append(v)
            for w in nbr[v]:
                if w not in seen and allowed[w]:
                    seen.add(w)
                    stack.append(w)
        out.append(comp)
    return out


def _mesh_volume(obj):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    v = abs(bm.calc_volume(signed=True))
    bm.free()
    return v


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _region(obj, t, c, rname, tname, entry, verts, area, normals, body_volume, nbr, weights=None):
    P = t["P"]
    rel = t["relative"][verts]
    exc = np.maximum(t["excess"][verts], 0.0)
    peak_rel = float(np.percentile(rel, 90))
    if weights is None:
        w = _smoothstep((rel - GROW_RELATIVE) / max(0.6 * peak_rel - GROW_RELATIVE, 1e-6))
        # two passes of neighbour averaging, counting outside neighbours as zero: a weight
        # that steps from one vertex to the next shows as a crease when the bone moves
        idx = {int(v): k for k, v in enumerate(verts)}
        for _ in range(2):
            nw = w.copy()
            for k, v in enumerate(verts):
                ring = nbr[int(v)]
                inside = [idx[u] for u in ring if u in idx]
                nw[k] = (w[k] + sum(w[j] for j in inside)) / (1 + len(ring))
            w = nw
        w = w / max(float(w.max()), 1e-9)
    else:
        w = np.asarray(weights, dtype=float)
    wa = w * area[verts]
    n_mean = (normals[verts] * wa[:, None]).sum(axis=0)
    n_mean /= max(np.linalg.norm(n_mean), 1e-12)
    # the bone sits under the mass, not under the region: weighted by excess squared, so a
    # ribcage front that bulges a little below a breast does not drag the bone down to it
    # (plain area weighting put the test figure's breast bones 11 cm below the breasts)
    wm = wa * exc * exc
    if weights is not None:
        # a painted group or a 2D mark says where the mass is: place the bone by what was
        # marked, not by excess - a mark over a bloater's moobs that took in the top of its
        # belly put the moob bones on the belly, whose excess is larger
        wm = wa * w * w
    total = max(float(wm.sum()), 1e-18)
    surface = (P[verts] * wm[:, None]).sum(axis=0) / total
    depth = float((exc * wm).sum() / total)
    peak = max(float(np.percentile(exc, 90)), 0.01)
    tail = surface
    head = surface - n_mean * (depth + 0.5 * peak)
    w_out = w
    attach = None
    if entry.get("attachment") == "upper" and not _legacy_attachment():
        head, tail, w_out, attach = _hang_from_above(obj, t, verts, w, exc, n_mean, surface,
                                                      rise_m=tuple(entry.get("attach_rise_m", ATTACH_UP_M)))
    volume = float((exc * area[verts] * np.clip(w, 0, 1)).sum())
    coords = {k: float(np.average(c[k][verts], weights=w + 1e-9)) for k in ("height", "facing", "lateral")}
    roles = list(c["role"][verts])
    role = max(set(roles), key=roles.count)
    density = 950.0
    if entry.get("material"):
        from . import registry
        density = registry.material(entry["material"]).get("density_kg_m3", density)
    return {
        "name": rname, "type": tname, "material": entry.get("material"),
        "vertices": np.asarray(verts, dtype=int), "weights": w_out, "count": int(len(verts)),
        "attachment": attach,
        "volume_m3": round(volume, 6),
        "volume_fraction": round(volume / max(body_volume, 1e-9), 4),
        "peak_m": round(peak, 4), "peak_relative": round(peak_rel, 3),
        "mass_kg": round(volume * density, 3),
        "head": head, "tail": tail, "normal": n_mean,
        "anchor_bone": _anchor_from_role(t, entry.get("anchor")) or _anchor_bone(t, head),
        "place": {**{k: round(v, 3) for k, v in coords.items()}, "chain": role},
        "paired": rname.endswith((".L", ".R")),
        "features": _region_features(coords, role, peak_rel, volume / max(body_volume, 1e-9)),
        "evidence": [f"{len(verts)} vertices standing up to {peak:.3f} m ({peak_rel:.0%} of the lean radius) "
                     f"out of the body in the {tname} zone: height {coords['height']:.2f}, facing "
                     f"{coords['facing']:.0f} deg, on the {role}"],
    }


def _legacy_attachment():
    import os
    return os.environ.get("FT_FLESH_LEGACY_ATTACHMENT") == "1"


def _hang_from_above(obj, t, verts, w, exc, n_mean, surface, rise_m=ATTACH_UP_M):
    """A mass that hangs from its upper edge - a breast from the chest wall above it, a buttock from the
    iliac crest and sacrum - pivots there, not at its own height, and moves most at its apex (research-flesh-
    jiggle.md items B and C). Before this the bone's tail sat at the excess^2 centre, 5-8 cm inside the
    surface, its head at the same height 15 cm deep (study_woman's 3 cm *below* the tail), and the weight was a
    plateau: >= 0.9 from 14 cm above the nipple to 4 cm below, so a vertical bounce rocked the upper pole and
    the lower back with the mass as one lump; a buttock's weight ran 12-16 cm down the back of the thigh.

    Tail: the apex, the mean of the region's most outward vertices (along its mean normal) among those
    weighted >= 0.5. Head: under the lean surface at the apex by ATTACH_UNDER_LEAN_M, raised by 0.6 x the
    region's height above the apex, clipped to `rise_m` (ATTACH_UP_M, or the type's `attach_rise_m`). Weight: the measured feathering times
    smoothstep((u - ATTACH_U0) / (1 - ATTACH_U0)), u the vertex's place along head -> tail (0 at the pivot, 1
    at the apex), times (1 - its skin share on leg chains), normalised to 1 at the apex.

    Returns head, tail, weights and a report of where they went."""
    P = t["P"][verts]
    up = np.asarray(t["frame"]["up"], dtype=float)
    out = (P - surface) @ n_mean
    strong = np.where(w >= 0.5)[0]
    if len(strong) < 3:
        strong = np.arange(len(verts))
    k = max(3, int(round(0.05 * len(strong))))
    top = strong[np.argsort(out[strong])[-k:]]
    apex = P[top].mean(axis=0)
    lean_at_apex = apex - n_mean * float(exc[top].mean())
    zs = P[w > 0.2] @ up if (w > 0.2).any() else P @ up
    rise = float(np.clip(0.6 * (np.percentile(zs, 90) - apex @ up), rise_m[0], rise_m[1]))
    head = lean_at_apex - n_mean * ATTACH_UNDER_LEAN_M
    # exactly `rise` above the apex: stepping in along a normal that tilts down lowered it (study_woman 2.8 cm)
    head = head + up * (float(apex @ up) + rise - float(head @ up))
    axis = apex - head
    L2 = max(float(axis @ axis), 1e-9)
    u = ((P - head) @ axis) / L2
    g = _smoothstep((u - ATTACH_U0) / (1.0 - ATTACH_U0))
    leg = _leg_share(obj, t, verts)
    # nothing on a vertex the thigh mostly moves: 1 - leg alone left 0.51 on the sample Figure's, and a
    # buttock weighted onto the back of the thigh creases the fold as the leg swings
    graded = w * g * _smoothstep((ATTACH_LEG_OFF - leg) / ATTACH_LEG_OFF)
    # full weight at the apex: most of the 2 cm round it at 1. Normalising on the outermost vertices alone left
    # study_man's and Marco's seat at 0.80-0.85 there, the thigh's share taking the rest
    near = np.linalg.norm(P - apex, axis=1) < 0.02
    ref = graded[near] if near.sum() >= 3 else graded[top]
    at_apex = float(np.percentile(ref, 25))
    graded = np.clip(graded / max(at_apex, 1e-6), 0.0, 1.0)
    report = {"apex": [round(float(x), 4) for x in apex], "rise_m": round(rise, 4),
              "under_lean_m": ATTACH_UNDER_LEAN_M, "leg_share_max": round(float(leg.max()), 3),
              "weight_before_grading_at_apex": round(float(w[top].mean()), 3)}
    return head, apex, graded, report


def _leg_share(obj, t, verts):
    """Per region vertex, the share of its (non-ft_) skin weight on a leg: each leg's upper bone (rig-anything's
    limb roles, else a bone named like a thigh) and every bone under it. Not the chains' `kind`, which is set by
    height alone: on study_woman it called the root-to-spine chain and the fingers legs, and every bone under
    `root` then counted as leg."""
    rig = bpy.data.objects.get(t.get("rig") or "")
    legs = set()
    if rig is None:
        return np.zeros(len(verts))
    for limb in ((t.get("roles") or {}).get("limbs") or {}).values():
        if limb.get("role") == "leg" and limb.get("upper") in rig.data.bones:
            legs.add(limb["upper"])
    if not legs:
        legs = {b.name for b in rig.data.bones
                if {"thigh", "upperleg", "upleg"} & set(name_tokens(b.name)) or "upper_leg" in b.name.lower()}
    if legs:
        stack = [rig.data.bones[b] for b in list(legs)]
        while stack:
            b = stack.pop()
            for ch_b in b.children:
                if ch_b.name not in legs and not ch_b.name.startswith("ft_"):
                    legs.add(ch_b.name)
                    stack.append(ch_b)
    names = {g.index: g.name for g in obj.vertex_groups}
    out = np.zeros(len(verts))
    for i, v in enumerate(verts):
        tot = on = 0.0
        for x in obj.data.vertices[int(v)].groups:
            n = names.get(x.group, "")
            if n.startswith("ft_"):
                continue
            tot += x.weight
            if n in legs:
                on += x.weight
        out[i] = on / tot if tot > 0 else 0.0
    return out


def _attachment_measures(t, r, verts, w, above_m=ATTACH_ABOVE_M):
    """How a hanging mass's bone and weight sit (check_placement): the pivot's rise over the tail, the mean weight
    within 2 cm of the tail, the most weight on region vertices 9-11 cm above the tail within 4 cm of it
    horizontally, and the most on vertices with half or more of their skin on a leg. Free values, never clamped."""
    P = t["P"][verts]
    up = np.asarray(t["frame"]["up"], dtype=float)
    tail, head = np.asarray(r["tail"], dtype=float), np.asarray(r["head"], dtype=float)
    d = P - tail
    dz = d @ up
    horiz = np.linalg.norm(d - np.outer(dz, up), axis=1)
    near = np.linalg.norm(d, axis=1) < 0.02
    above = (dz > above_m - 0.01) & (dz < above_m + 0.01) & (horiz < 0.04)
    leg = _leg_share(bpy.data.objects[t["object"]], t, verts) >= 0.5
    return {"pivot_rise_m": round(float((head - tail) @ up), 4),
            "weight_at_apex": round(float(w[near].mean()), 3) if near.any() else 0.0,
            "weight_10cm_above": round(float(w[above].max()), 3) if above.any() else 0.0, "above_m": above_m,
            "weight_on_thigh": round(float(w[leg].max()), 3) if leg.any() else 0.0}


def check_placement(t, regions, c=None):
    """Whether each region sits where its type's flesh is on a body: its bone's tail and its weight centre
    below the chin (the lowest head-skinned vertex, `tissue`'s `head_skinned`) and inside the type's
    (grown) zone height, and at most HEAD_SHARE_MAX of its weight on head-skinned vertices. Nothing else
    tests where a jiggle bone lands anatomically: the cast's Mei and Ruth passed every check with their
    breast bones on the chin.

    Returns {"ok": bool, "chin_z": float or None, "regions": [{name, type, ok, tail_z, centre_z,
    tail_height, centre_height, zone_height, head_share, problems}]}. Heights are zone coordinates (0 at
    the hip joints, 1 at the shoulder joints), z in metres; a region whose type has no registry zone is
    checked against the chin and for head weight only."""
    from . import registry
    c = c if c is not None else coordinates(t)
    f = t["frame"]
    P = t["P"]
    span = max(f["shoulder"] - f["hip"], 1e-6)
    head = t.get("head_skinned")
    chin = float(P[head, 2].min()) if head is not None and head.any() else None
    types = registry.types_for(cls="flesh")
    out = []
    for r in regions:
        verts = np.asarray(r["vertices"], dtype=int)
        w = np.clip(np.asarray(r["weights"], dtype=float), 0.0, None)
        wsum = max(float(w.sum()), 1e-12)
        zone = (types.get(r["type"]) or {}).get("zone")
        tail_z = float(r["tail"][2])
        centre_z = float((P[verts, 2] * w).sum() / wsum)
        row = {"name": r["name"], "type": r["type"], "problems": [],
               "tail_z": round(tail_z, 3), "centre_z": round(centre_z, 3),
               "tail_height": round((tail_z - f["hip"]) / span, 3),
               "centre_height": round(float((c["height"][verts] * w).sum() / wsum), 3),
               "head_share": round(float(w[head[verts]].sum() / wsum), 3) if head is not None else 0.0}
        if chin is not None:
            for z, what in ((tail_z, "bone tail"), (centre_z, "weight centre")):
                if z >= chin:
                    row["problems"].append(f"{r['name']}: its {what} is at {z:.3f} m, at or above the chin "
                                           f"({chin:.3f} m, the lowest vertex skinned to the head)")
        if zone and "height" in zone:
            lo, hi = _grown_zone(zone)["height"]
            row["zone_height"] = [round(lo, 3), round(hi, 3)]
            for k, what in (("tail_height", "bone tail"), ("centre_height", "weight centre")):
                if not lo <= row[k] <= hi:
                    row["problems"].append(f"{r['name']}: its {what} is at height {row[k]:.2f}, outside the "
                                           f"{r['type']} zone's {lo:.2f}-{hi:.2f} (0 hip joints, 1 shoulder joints)")
        entry = types.get(r["type"]) or {}
        if entry.get("attachment") == "upper":
            rise_min = float(entry.get("attach_rise_m", ATTACH_UP_M)[0])
            row.update(_attachment_measures(t, r, verts, w, above_m=float(entry.get("attach_above_m", ATTACH_ABOVE_M))))
            if row["pivot_rise_m"] < rise_min - 0.001:
                row["problems"].append(f"{r['name']}: its pivot is {row['pivot_rise_m'] * 100:.1f} cm above its tail; a "
                                       f"mass hanging from above pivots at least {rise_min * 100:.0f} cm above its apex")
            if row["weight_at_apex"] < ATTACH_APEX_MIN:
                row["problems"].append(f"{r['name']}: weight {row['weight_at_apex']:.2f} at its apex (the tail), "
                                       f"under {ATTACH_APEX_MIN}")
            if row["weight_10cm_above"] > ATTACH_ABOVE_MAX:
                row["problems"].append(f"{r['name']}: weight {row['weight_10cm_above']:.2f} {row['above_m'] * 100:.0f} cm above its apex, over "
                                       f"{ATTACH_ABOVE_MAX}: the attachment moves with the mass")
            if row["weight_on_thigh"] > ATTACH_THIGH_MAX:
                row["problems"].append(f"{r['name']}: weight {row['weight_on_thigh']:.2f} on vertices the thigh "
                                       f"mostly moves, over {ATTACH_THIGH_MAX}")
        if row["head_share"] > HEAD_SHARE_MAX:
            row["problems"].append(f"{r['name']}: {row['head_share']:.0%} of its weight is on head-skinned "
                                   f"vertices (the face), over {HEAD_SHARE_MAX:.0%}")
        row["ok"] = not row["problems"]
        out.append(row)
    return {"ok": all(x["ok"] for x in out), "chin_z": None if chin is None else round(chin, 3), "regions": out}


def _region_features(coords, role, peak_rel, volume_fraction):
    return {"height": coords["height"], "facing_cos": math.cos(math.radians(coords["facing"])),
            "facing_sin": math.sin(math.radians(coords["facing"])), "lateral": min(coords["lateral"], 2.0) / 2.0,
            "peak": min(peak_rel, 2.0) / 2.0, "volume_fraction": min(volume_fraction * 10.0, 1.0),
            "chain_spine": float(role == "spine"), "chain_arm": float(role == "arm"),
            "chain_leg": float(role == "leg")}


def _anchor_from_role(t, role):
    """The bone a type's registry `anchor` names, or None to fall back on the nearest core bone.

    `anchor` is a rig-anything bone role (`pelvis`, `chest`, `head`, ...), read from `t["roles"]`.
    Without roles (rig-anything not importable) `pelvis` is still found by `_pelvis_bone`."""
    if not role:
        return None
    rig = bpy.data.objects.get(t.get("rig") or "")
    bone = _role_bone(rig, t.get("roles"), role)
    if bone is None and role == "pelvis":
        bone = _pelvis_bone(t)
    return bone


def _pelvis_bone(t):
    """The bone the legs hang from: the parent most leg chains start under, or None.

    The fallback for `"anchor": "pelvis"` (buttocks) when rig-anything's roles are not to hand. The nearest bone
    put an MPFB woman's buttocks on her thighs - her pelvis bone starts at the hip joints and the
    seat hangs below them - so every stride swung them with the leg, and a thigh lifted level in a
    crouch turned gravity on them: on their swing limit half the time."""
    rig = bpy.data.objects.get(t.get("rig") or "")
    if rig is None:
        return None
    H = t.get("height") or 1.0
    counts = {}
    for ch in t["chains"]:
        if ch.get("kind") != "leg" or ch.get("length", 0.0) < 0.25 * H:
            continue
        b = rig.data.bones.get(ch["bones"][0])
        if b is not None and b.parent is not None:
            counts[b.parent.name] = counts.get(b.parent.name, 0) + 1
    best = max(counts.items(), key=lambda kv: kv[1], default=(None, 0))
    return best[0] if best[1] >= 2 else None


def _anchor_bone(t, point):
    """The core bone whose segment passes nearest `point`."""
    best, best_d = None, math.inf
    for ch in t["chains"]:
        pts = ch["points"]
        for si, bone in enumerate(ch["bones"]):
            h, d = pts[si], pts[si + 1] - pts[si]
            L2 = float(d @ d)
            f = 0.0 if L2 < 1e-12 else float(np.clip((point - h) @ d / L2, 0.0, 1.0))
            dist = float(np.linalg.norm(point - (h + f * d)))
            if dist < best_d:
                best, best_d = bone, dist
    return best


def region_from_group(obj_name, group, rig_name=None):
    """A region from a painted vertex group - how a new kind of flesh is taught."""
    obj = bpy.data.objects[obj_name]
    g = obj.vertex_groups.get(group)
    if g is None:
        return {"error": f"{obj_name} has no vertex group {group!r}"}
    t = tissue(obj_name, rig_name)
    if "error" in t:
        return t
    c = coordinates(t)
    weights = {}
    for v in obj.data.vertices:
        for x in v.groups:
            if x.group == g.index and x.weight > 0.0:
                weights[v.index] = x.weight
    if not weights:
        return {"error": f"vertex group {group!r} on {obj_name} is empty"}
    verts = np.array(sorted(weights), dtype=int)
    reg = _region(obj, t, c, group, group, {}, verts, _vertex_areas(obj), _world_normals(obj),
                  _mesh_volume(obj), _adjacency(obj), weights=[weights[int(v)] for v in verts])
    reg["paired"] = group.endswith((".L", ".R", "_L", "_R"))
    reg["coords_range"] = {k: (float(c[k][verts].min()), float(c[k][verts].max()))
                           for k in ("height", "facing", "lateral")}
    return reg


def zone_around(region, pad=0.08):
    """A zone that holds a taught region, padded."""
    r = region["coords_range"]
    return {"chain": region["place"]["chain"],
            "height": [round(r["height"][0] - pad, 3), round(r["height"][1] + pad, 3)],
            "facing_deg": [round(max(0.0, r["facing"][0] - 15.0), 1), round(min(180.0, r["facing"][1] + 15.0), 1)],
            "lateral": [round(max(0.0, r["lateral"][0] - pad), 3), round(r["lateral"][1] + pad, 3)]}


# ------------------------------------------------------------------ rigging

JIGGLE_PREFIX = "ft_jiggle_"
JIGGLE_SHARE_MAX = 0.98   # of a vertex's weight a jiggle bone may take (add_jiggle_bones)
ROLE_PROP = "ft_role"     # on every bone follow-through adds; rig-anything's bodymap skips tagged bones


def add_jiggle_bones(obj_name, regions, rig_name=None, weight_scale=1.0):
    """One bone per region, parented to its anchor bone, its vertices weighted to it.

    The jiggle weight is taken out of the vertex's other weights in proportion, so each
    vertex keeps its total. Re-running replaces the jiggle bones made before, giving their weight
    back first (`remove_jiggle_weights`), so a second run weights the body as the first did."""
    obj = bpy.data.objects[obj_name]
    rig = bpy.data.objects[rig_name] if rig_name else armature_of(obj)
    restored = remove_jiggle_weights(obj, rig)
    inv = rig.matrix_world.inverted()
    win = bpy.context.window
    prev_scene = win.scene
    prev_active = bpy.context.view_layer.objects.active
    made = []
    win.scene = rig.users_scene[0]
    try:
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        bpy.context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        eb = rig.data.edit_bones
        for b in [b for b in eb if b.name.startswith(JIGGLE_PREFIX)]:
            eb.remove(b)
        for r in regions:
            bone = eb.new(JIGGLE_PREFIX + r["name"])
            bone.head = inv @ _vec(r["head"])
            bone.tail = inv @ _vec(r["tail"])
            parent = eb.get(r["anchor_bone"])
            if parent is not None:
                bone.parent = parent
            bone.use_deform = True
            bone.use_connect = False
            # tagged, so rig-anything's body map leaves it out: an unsided bone on the spine
            # otherwise reads as the end of the axial chain and costs the rig its pelvis role
            bone[ROLE_PROP] = "jiggle"
            made.append(bone.name)
        bpy.ops.object.mode_set(mode="OBJECT")
    finally:
        if bpy.context.view_layer.objects.active is not None and bpy.context.view_layer.objects.active.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        win.scene = prev_scene
        if prev_active is not None and prev_active.name in bpy.context.view_layer.objects:
            bpy.context.view_layer.objects.active = prev_active
    groups = {r["name"]: obj.vertex_groups.new(name=JIGGLE_PREFIX + r["name"]) for r in regions}
    jiggle_index = {g.index for g in groups.values()}
    for r in regions:
        g = groups[r["name"]]
        for v, w in zip(r["vertices"], r["weights"]):
            # never all of it: a vertex whose other weights were all taken can only give its jiggle weight back to
            # the anchor bone (remove_jiggle_weights), and a second prepare then measured the thigh share it lost -
            # Ruth's graded butt came back 0.57 at the apex and 0.50 10 cm above it, failing check_placement
            w = float(min(JIGGLE_SHARE_MAX, w * weight_scale))
            if w <= 1e-3:
                continue
            vert = obj.data.vertices[int(v)]
            others = [x for x in vert.groups if x.group not in jiggle_index]
            total = sum(x.weight for x in others) or 1.0
            for x in others:
                x.weight = x.weight * (1.0 - w)
            g.add([int(v)], w * total, "REPLACE")
    limited = limit_influences(obj, rig)
    return {"rig": rig.name, "bones": made, "vertices_limited_to_4": limited, "weights_restored": restored}


def remove_jiggle_weights(obj, rig=None):
    """Take the jiggle groups off `obj`, giving each vertex's jiggle weight back to the weights it came from.

    `add_jiggle_bones` takes a jiggle weight `w * T` out of a vertex's other weights in proportion (each
    scaled by `1 - w`, `T` their total), so scaling them back by `T / (T - jiggle)` restores them. Removing
    the groups alone lost that share: a second `prepare` on a fleshed body (a pipeline rebuild from its
    saved .blend after a `[flesh]` edit) left the vertices at a mass's heart with almost no weight - 5 of
    study_man's with none at all, which the glTF exporter hangs on a `neutral_bone` - and measured the
    masses on those thinned weights. A vertex whose other weights were all taken (w = 1) has no proportion
    left: its weight goes to the jiggle bone's parent. The bones themselves stay (`add_jiggle_bones`
    replaces them). Returns the number of vertices given weight back."""
    jig = {g.index: g.name for g in obj.vertex_groups if g.name.startswith(JIGGLE_PREFIX)}
    if not jig:
        return 0
    parent_of = {}
    if rig is not None:
        for idx, name in jig.items():
            b = rig.data.bones.get(name)
            if b is not None and b.parent is not None:
                parent_of[idx] = b.parent.name
    restored = 0
    for v in obj.data.vertices:
        mine = [(x.group, x.weight) for x in v.groups if x.group in jig]
        j = sum(w for _g, w in mine)
        if j <= 0.0:
            continue
        others = [x for x in v.groups if x.group not in jig]
        rest = sum(x.weight for x in others)
        if rest > 1e-6:
            scale = (rest + j) / rest
            for x in others:
                x.weight = x.weight * scale
        else:
            for gi, w in mine:
                parent = parent_of.get(gi)
                if parent is None:
                    continue
                g = obj.vertex_groups.get(parent) or obj.vertex_groups.new(name=parent)
                g.add([v.index], w, "ADD")
        restored += 1
    for name in sorted(jig.values()):
        obj.vertex_groups.remove(obj.vertex_groups[name])
    return restored


def limit_influences(obj, rig, most=4):
    """Keep each vertex's `most` strongest bone weights and renormalise them.

    glTF carries four joints per vertex; Blender's exporter drops the rest and renormalises
    on its own, with a warning. A jiggle weight added as a fifth influence could be the one
    it drops, and the mass would stop moving at its edge - so the choice is made here."""
    bones = {b.name for b in rig.data.bones}
    changed = 0
    for v in obj.data.vertices:
        deform = [x for x in v.groups if obj.vertex_groups[x.group].name in bones and x.weight > 0.0]
        if len(deform) <= most:
            continue
        # plain (group, weight) pairs: removing a group from the vertex compacts `v.groups`, and an element
        # read before that then writes its weight to the wrong group or nowhere - the kept weights were never
        # scaled back up, and a vertex lost the dropped share of its total (up to 22 % on the sample Figure)
        pairs = sorted(((x.group, x.weight) for x in deform), key=lambda gw: gw[1], reverse=True)
        keep = pairs[:most]
        total = sum(w for _g, w in pairs)
        kept = sum(w for _g, w in keep) or 1.0
        for g, _w in pairs[most:]:
            obj.vertex_groups[g].remove([v.index])
        for g, w in keep:
            obj.vertex_groups[g].add([v.index], w / kept * total, "REPLACE")
        changed += 1
    return changed


def _vec(a):
    from mathutils import Vector
    return Vector((float(a[0]), float(a[1]), float(a[2])))


def jiggle_block(obj, rig, regions, overrides=None):
    """The spec's `jiggle` block: one entry per region, positions in armature space, glTF axes."""
    from . import registry
    from .spec import to_gltf
    inv = rig.matrix_world.inverted()
    types = registry.load()["types"]
    out = []
    for r in regions:
        params = dict(registry.material(r["material"]).get("jiggle", {})) if r.get("material") else {}
        # the swing limit as a share of peak_m: the type's own, unless an override names a share or
        # the material fraction (`max_offset`) instead
        share = types.get(r["type"], {}).get("limit_share")
        for key in (r["type"], r["name"]):
            o = (overrides or {}).get(key, {})
            if "limit_share" in o:
                share = o["limit_share"]
            elif "max_offset" in o:
                share = None
            params.update(o)
        head = inv @ _vec(r["head"])
        tail = inv @ _vec(r["tail"])
        entry = {
            "name": r["name"], "type": r["type"], "material": r.get("material"),
            "bone": JIGGLE_PREFIX + r["name"], "parent": r["anchor_bone"],
            "head": [round(x, 5) for x in to_gltf(head)], "tail": [round(x, 5) for x in to_gltf(tail)],
            "mass_kg": r["mass_kg"], "volume_m3": r["volume_m3"], "peak_m": r["peak_m"], "vertices": r["count"],
            # the furthest the tail may leave its rest place: the type's `limit_share` of how far the
            # mass stands out (tuned per type - its `limit_note` says how), or else a fraction of the
            # bulge's own size from the material
            "max_offset_m": (round(float(share) * r["peak_m"], 4) if share is not None
                             else round(float(params.get("max_offset", 0.5)) * 2.0 * r["peak_m"], 4)),
        }
        for k in ("frequency_hz", "damping_ratio", "squash", "gravity_scale", "aim", "translate", "response",
                  "frequency_down_ratio", "frequency_ap_ratio"):
            if k in params:
                entry[k] = params[k]
        # a heavier mass on the same tissue swings slower (research-flesh-jiggle.md, E): frequency x
        # (mass_ref_kg / mass_kg) ^ mass_exponent, clipped to MASS_SCALE. soft_fat ships it off (exponent 0): on
        # every body measured the swing limit bounds the amplitude, and a lower frequency only held the heavy
        # mass on its limit longer (Belle's breast at 1.9 Hz: walking 4.0 -> 7.4 % on the limit, jumping 8 -> 15 %)
        exp_ = float(params.get("mass_exponent", 0.0))
        if exp_ and "frequency_hz" in entry and r.get("mass_kg"):
            scale = (float(params.get("mass_ref_kg", r["mass_kg"])) / float(r["mass_kg"])) ** exp_
            entry["frequency_hz"] = round(float(entry["frequency_hz"]) * min(max(scale, MASS_SCALE[0]), MASS_SCALE[1]), 4)
            entry["mass_scale"] = round(scale, 4)
        out.append(entry)
    return {"space": "gltf_armature", "armature": rig.name, "regions": out}


def prepare(obj_name, rig_name=None, types=None, overrides=None, weight_scale=1.0, regions=None):
    """Find the soft masses on a skinned body, give each a jiggle bone, and write the spec.

    `types` limits which flesh types are looked for; `overrides` is
    {region or type name: {"frequency_hz": ..., "damping_ratio": ..., "limit_share": ...}}. Each
    region's `max_offset_m` is its type's `limit_share` x peak_m when the type has one (breast,
    butt), else the material's `max_offset` x 2 x peak_m. `regions` skips the
    search and rigs these instead - from marks.regions() (zones marked on 2D renders) or a
    filtered find_regions()."""
    from . import classify, spec
    obj = bpy.data.objects[obj_name]
    rig = bpy.data.objects[rig_name] if rig_name else armature_of(obj)
    if rig is None:
        return {"error": f"{obj_name} is not skinned to an armature: flesh needs a skeleton "
                         "(rig it with rig-anything first)"}
    # a body fleshed before is measured, and weighted, as it was before its first jiggle bones
    remove_jiggle_weights(obj, rig)
    if regions is None:
        found = find_regions(obj_name, rig.name, types)
        if "error" in found:
            return found
        regions, declined, missed = found["regions"], found["declined"], found["missed"]
        placement = check_placement(found["tissue"], regions, found["coords"])
    else:
        declined, missed = [], []
        t = tissue(obj_name, rig.name)
        placement = check_placement(t, regions) if "error" not in t else {"ok": True, "regions": []}
    report = {"object": obj_name, "rig": rig.name, "regions": regions, "declined": declined,
              "missed": missed, "warnings": [], "placement": placement}
    if not regions:
        report["warnings"].append("no soft masses found - look at render_heat(); paint a vertex group "
                                  "and registry.teach(obj, type, group=...) if one was missed")
        return report
    report["bones"] = add_jiggle_bones(obj_name, regions, rig.name, weight_scale)["bones"]
    rec = classify.classify(obj_name, cls="flesh")
    s = spec.build(obj, rec)
    s["jiggle"] = jiggle_block(obj, rig, regions, overrides)
    s["type"] = ",".join(sorted({r["type"] for r in regions}))
    spec.write(obj, s)
    report["spec"] = s
    return report


def set_params(obj_name, region, **params):
    """Change one region's (or every region of a type's) jiggle values in the spec."""
    from . import spec
    obj = bpy.data.objects[obj_name]
    s = spec.read(obj)
    if s is None or "jiggle" not in s:
        raise ValueError(f"{obj_name} has no jiggle spec - run flesh.prepare first")
    allowed = {"frequency_hz", "damping_ratio", "squash", "gravity_scale", "aim", "translate", "response",
               "max_offset_m", "frequency_down_ratio", "frequency_ap_ratio"}
    bad = set(params) - allowed
    if bad:
        raise ValueError(f"not jiggle parameters: {sorted(bad)}")
    hit = 0
    for r in s["jiggle"]["regions"]:
        if region in (r["name"], r["type"]):
            r.update(params)
            hit += 1
    if not hit:
        raise ValueError(f"no region or type named {region!r}")
    return spec.write(obj, s)


def suggest_limits(report, band=None, target=None, caps=None):
    """A suggested `max_offset_m` (and `limit_share`) per region from Godot's measured time on the limit.

    `report` is what `verify_flesh.gd` (or a self-test calling `JiggleModifier.print_limit_report`)
    printed: the `FT_FLESH_LIMITS {json}` lines, the log holding them, the `out=` JSON file, or the
    parsed dicts. A region on its limit for less than `band[0]` or more than `band[1]` of the ticks
    (default `limits.BAND`) gets a limit read off the unlimited swing's demand curve that puts
    it at `target` (the middle). `caps` defaults to each registry type's `limit_max_share`, and a
    type with none is capped at `limits.DEFAULT_MAX_SHARE` x peak_m: no suggestion ever carries a
    mass further than it stands out of the body.

    A report that measured nothing fails: the result's `problems` say what, and `in_band` and
    `settled` are then false. See `limits.suggest` for the returned rows; `apply_limits` writes them
    into the spec."""
    from . import limits, registry
    if caps is None:
        caps = {name: t["limit_max_share"] for name, t in registry.load()["types"].items()
                if "limit_max_share" in t}
    return limits.suggest(report, band=band or limits.BAND, target=target, caps=caps)


def apply_limits(obj_name, suggestion, body=None):
    """Write a `suggest_limits` result's `suggested_max_offset_m` into `obj_name`'s jiggle spec.

    `body` names the body in the suggestion (default: `obj_name`, or the only one). Regions the
    suggestion does not name are left alone. A suggestion with `problems` - a report that measured
    nothing - is refused. Returns {region: [old, new]} for what changed."""
    from . import spec
    if not suggestion.get("measured", True):
        raise ValueError("this suggestion came from a report that measured nothing: "
                         + "; ".join(suggestion.get("problems", [])))
    bodies = suggestion["bodies"]
    key = body or (obj_name if obj_name in bodies else (next(iter(bodies)) if len(bodies) == 1 else None))
    if key not in bodies:
        raise ValueError(f"no body {body or obj_name!r} in the suggestion; it has {sorted(bodies)}")
    if not bodies[key]:
        raise ValueError(f"the suggestion measured no region of {key!r}: "
                         + "; ".join(suggestion.get("problems", [])))
    obj = bpy.data.objects[obj_name]
    s = spec.read(obj)
    if s is None or "jiggle" not in s:
        raise ValueError(f"{obj_name} has no jiggle spec - run flesh.prepare first")
    changed = {}
    for r in s["jiggle"]["regions"]:
        row = bodies[key].get(r["name"])
        if row is None:
            continue
        new = float(row["suggested_max_offset_m"])
        if abs(new - float(r["max_offset_m"])) >= 5e-5:
            changed[r["name"]] = [r["max_offset_m"], new]
            r["max_offset_m"] = new
    spec.write(obj, s)
    return changed


def summarize(report):
    if "error" in report:
        return "ERROR " + report["error"]
    lines = [f"{report['object']} on {report['rig']}: {len(report['regions'])} soft region(s)"]
    for r in report["regions"]:
        p = r["place"]
        lines.append(f"  {r['name']:16} {r['type']:14} {str(r['material']):11} {r['count']:5} verts, "
                     f"stands {r['peak_m']:.3f} m out, {r['volume_fraction']:.1%} of the body, "
                     f"on {r['anchor_bone']} (height {p['height']:.2f}, facing {p['facing']:.0f}, {p['chain']})")
    for d in report.get("declined", []):
        lines.append("  - " + d)
    for m in report.get("missed", []):
        lines.append("  MISSED " + m["message"])
    s = report.get("spec")
    if s:
        for j in s["jiggle"]["regions"]:
            lines.append(f"  bone {j['bone']}: {j.get('frequency_hz')} Hz, damping {j.get('damping_ratio')}, "
                         f"squash {j.get('squash')}, max offset {j['max_offset_m']} m")
    for w in report.get("warnings", []):
        lines.append("  WARNING " + w)
    return "\n".join(lines)


# ------------------------------------------------------------------ looking

def render_heat(obj_name, out_dir, regions=None, views=("front", "right", "iso"), size=560):
    """Render the body coloured by how far it stands proud of its lean envelope, with found
    regions in blue - the visual half of recognising flesh. A temporary colour attribute
    and a throwaway scene; the object's colours and the user's scene are left as they were."""
    import os
    from mathutils import Vector
    from . import views as V
    obj = bpy.data.objects[obj_name]
    t = tissue(obj_name)
    if "error" in t:
        return t
    H = t["height"]
    n = len(t["P"])
    excess, relative = shown(t)
    k = np.clip(excess / (0.04 * H), 0.0, 1.0) * (relative > GROW_RELATIVE)
    cols = np.ones((n, 4))
    cols[:, 1] = 1.0 - 0.8 * k
    cols[:, 2] = 1.0 - 0.8 * k
    cols[~t["searched"], :3] = (0.75, 0.82, 0.75)
    for r in (regions or []):
        for v, w in zip(r["vertices"], r["weights"]):
            cols[int(v), :3] = (1.0 - 0.8 * w, 1.0 - 0.6 * w, 1.0)
    me = obj.data
    name = "ft_heat"
    attr = me.color_attributes.get(name) or me.color_attributes.new(name, "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", cols.ravel())
    prev_active = me.color_attributes.active_color_name
    me.color_attributes.active_color = attr
    os.makedirs(out_dir, exist_ok=True)
    scene = bpy.data.scenes.new("ft_heat_tmp")
    cam_data = bpy.data.cameras.new("ft_heat_cam")
    cam = bpy.data.objects.new("ft_heat_cam", cam_data)
    files = []
    try:
        scene.collection.objects.link(obj)
        scene.collection.objects.link(cam)
        scene.camera = cam
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.render.resolution_x = scene.render.resolution_y = size
        scene.display.shading.light = "FLAT"
        scene.display.shading.color_type = "VERTEX"
        centre, dims = V._bounds([obj])
        radius = max(dims) * 0.5 or 1.0
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = radius * 2.3
        cam_data.clip_end = radius * 40
        for view in views:
            d = Vector(V.VIEWS[view]).normalized()
            cam.location = centre + d * radius * 6.0
            cam.rotation_euler = (centre - cam.location).normalized().to_track_quat("-Z", "Y").to_euler()
            path = os.path.join(out_dir, f"{obj_name.replace('.', '_')}_heat_{view}.png")
            scene.render.filepath = path
            bpy.ops.render.render(write_still=True, scene=scene.name)
            files.append(path)
    finally:
        scene.collection.objects.unlink(obj)
        bpy.data.scenes.remove(scene, do_unlink=True)
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.cameras.remove(cam_data, do_unlink=True)
        me.color_attributes.remove(me.color_attributes[name])
        if prev_active and prev_active in me.color_attributes:
            me.color_attributes.active_color_name = prev_active
    return {"object": obj_name, "files": files,
            "note": "white is lean, red stands proud of the lean envelope, blue is a found region, "
                    "green was not searched (head, hands, feet)"}
