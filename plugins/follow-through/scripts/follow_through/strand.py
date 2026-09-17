"""Strands: ponytails and long hair as sprung bone chains.

A strand is a line that hangs from one bone and swings: a ponytail, a braid, a lock of long
hair. It is built the way games build it - a chain of bones along the strand's centreline,
parented to the bone it grows from, with the mesh weighted along the chain - because bones and
weights are core glTF and the chain costs a spring per bone. In Godot `strand_modifier.gd`
springs each chain after the animation, root to tip, with the exact damped integration flesh
uses, an angular limit per bone and collision with capsules round the head and neck.

The input contract (what humanform's hair layer writes on a hair mesh):

    obj["ft_type"] = "strand"            routes it here (classify reads it)
    obj["ft_root_bone"] = "head"         the bone the strand grows from
    obj["ft_centreline"] = [[x, y, z], ...]         optional, root to tip, object-local
    obj["ft_centreline_world"] = [[x, y, z], ...]   or the same in world space
    obj["ft_centrelines"] = [[[x, y, z], ...], ...] optional, several chains (object-local)
    obj["ft_strand_type"] = "ponytail"   optional; else the name, else the class default

Without a centreline each loose part of the mesh is a chain, and its centreline is derived from
the mesh: surface distance from the vertices nearest the root bone, and the centroid of each band
of that distance - the principal line of the part followed from its root, which a straight axis
would cut across where a ponytail curls out of the scalp before it falls.

    r = strand.prepare("Ponytail")                 # chain, weights, spec
    print(strand.summarize(r))
    m = strand.export(r"C:/proj/assets/figure_hair.glb", ["Ponytail"], "Figure_metarig")

The body goes out through rig-anything's `export_character` as usual (its rig now carries the
strand bones); the hair goes out beside it, and `FollowThrough.attach` puts it on the body's
skeleton in Godot.
"""

from __future__ import annotations

import heapq
import math
import re

import bpy
from mathutils import Vector

from . import spec as ft_spec

STRAND_PREFIX = "ft_strand_"
ROLE_PROP = "ft_role"
TYPE_PROP = "ft_type"
ROOT_PROP = "ft_root_bone"
LINE_PROP = "ft_centreline"
LINE_WORLD_PROP = "ft_centreline_world"
LINES_PROP = "ft_centrelines"
KIND_PROP = "ft_strand_type"
G = 9.81

DEFAULTS = {"damping_ratio": 0.5, "gravity_scale": 1.0, "response": 1.0, "max_angle_deg": 40.0,
            "root_max_angle_deg": 60.0, "segment_m": 0.07, "min_bones": 3, "max_bones": 8,
            "pendulum_scale": 1.0, "min_frequency_hz": 0.6, "max_frequency_hz": 6.0,
            "collision_margin_m": 0.004, "collision_friction": 0.1, "band_m": 0.015}


# ------------------------------------------------------------------ what is a strand

def is_strand(obj):
    return obj is not None and str(obj.get(TYPE_PROP, "")).lower() == "strand"


def _rig_for(obj, root_bone=None):
    for m in obj.modifiers:
        if m.type == "ARMATURE" and m.object is not None:
            return m.object
    if obj.parent is not None and obj.parent.type == "ARMATURE":
        return obj.parent
    scenes = obj.users_scene or bpy.data.scenes
    for sc in scenes:
        for o in sc.objects:
            if o.type == "ARMATURE" and (root_bone is None or root_bone in o.data.bones):
                return o
    return None


def _plain_points(v):
    pts = ft_spec._plain(v)
    if pts and not isinstance(pts[0], (list, tuple)):
        pts = [pts[i:i + 3] for i in range(0, len(pts), 3)]
    return [Vector((float(p[0]), float(p[1]), float(p[2]))) for p in pts]


# ------------------------------------------------------------------ centrelines

def _components(me):
    parent = list(range(len(me.vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for e in me.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[max(a, b)] = min(a, b)
    groups = {}
    for i in range(len(me.vertices)):
        groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=lambda g: g[0])


def _segment_distance(p, a, b):
    ab = b - a
    t = 0.0 if ab.length_squared < 1e-12 else max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (p - (a + ab * t)).length


def derive_centreline(obj, verts, root_head, root_tail, band_m=DEFAULTS["band_m"]):
    """Root-to-tip centreline of one connected part, world space.

    Seeds are the part's vertices within 1.5 cm of the nearest one to the root bone; every vertex
    gets its surface distance from them (Dijkstra over edges), and the centreline is the centroid
    of each band `band_m` wide. Returns (points, report)."""
    mw = obj.matrix_world
    me = obj.data
    P = {i: mw @ me.vertices[i].co for i in verts}
    d_root = {i: _segment_distance(P[i], root_head, root_tail) for i in verts}
    nearest = min(d_root.values())
    seeds = [i for i in verts if d_root[i] <= nearest + 0.015]
    member = set(verts)
    nbr = {i: [] for i in verts}
    for e in me.edges:
        a, b = e.vertices
        if a in member and b in member:
            w = (P[a] - P[b]).length
            nbr[a].append((b, w))
            nbr[b].append((a, w))
    dist = {i: math.inf for i in verts}
    heap = []
    for s in seeds:
        dist[s] = 0.0
        heap.append((0.0, s))
    heapq.heapify(heap)
    while heap:
        d, i = heapq.heappop(heap)
        if d > dist[i]:
            continue
        for j, w in nbr[i]:
            if d + w < dist[j]:
                dist[j] = d + w
                heapq.heappush(heap, (d + w, j))
    far = max(d for d in dist.values() if d < math.inf)
    bands = max(3, int(round(far / band_m)))
    sums = [Vector((0, 0, 0)) for _ in range(bands)]
    counts = [0] * bands
    for i in verts:
        if dist[i] == math.inf:
            continue
        k = min(bands - 1, int(dist[i] / far * bands))
        sums[k] += P[i]
        counts[k] += 1
    pts = [sums[k] / counts[k] for k in range(bands) if counts[k]]
    # the first band's centroid sits half a band in; start the line where the part meets the root
    seed_c = sum((P[i] for i in seeds), Vector((0, 0, 0))) / len(seeds)
    if pts and (pts[0] - seed_c).length > 1e-4:
        pts.insert(0, seed_c.lerp(pts[0], 0.5))
    return pts, {"method": "surface distance from the root", "seeds": len(seeds), "bands": bands,
                 "surface_length_m": round(far, 4)}


def _arc(points):
    s = [0.0]
    for a, b in zip(points, points[1:]):
        s.append(s[-1] + (b - a).length)
    return s


def resample(points, n):
    """`n` + 1 points at equal arc length along a polyline."""
    s = _arc(points)
    total = s[-1]
    out = []
    k = 0
    for i in range(n + 1):
        want = total * i / n
        while k < len(points) - 2 and s[k + 1] < want:
            k += 1
        seg = s[k + 1] - s[k]
        t = 0.0 if seg < 1e-12 else (want - s[k]) / seg
        out.append(points[k].lerp(points[k + 1], max(0.0, min(1.0, t))))
    return out


def _project(p, joints):
    """Arc length along a polyline of the nearest point to p, and the distance to it."""
    best = (math.inf, 0.0)
    s0 = 0.0
    for a, b in zip(joints, joints[1:]):
        ab = b - a
        L = ab.length
        t = 0.0 if L < 1e-12 else max(0.0, min(1.0, (p - a).dot(ab) / (L * L)))
        d = (p - (a + ab * t)).length
        if d < best[0]:
            best = (d, s0 + t * L)
        s0 += L
    return best[1], best[0]


def centrelines(obj, rig, root_bone):
    """[(world points, vertex indices or None, report)] - one per chain."""
    mw = obj.matrix_world
    if obj.get(LINES_PROP) is not None:
        lines = [[mw @ p for p in _plain_points(line)] for line in ft_spec._plain(obj[LINES_PROP])]
        return [(ln, None, {"method": f"custom property {LINES_PROP}"}) for ln in lines]
    if obj.get(LINE_WORLD_PROP) is not None:
        return [(_plain_points(obj[LINE_WORLD_PROP]), None, {"method": f"custom property {LINE_WORLD_PROP}"})]
    if obj.get(LINE_PROP) is not None:
        return [([mw @ p for p in _plain_points(obj[LINE_PROP])], None, {"method": f"custom property {LINE_PROP}"})]
    rb = rig.data.bones[root_bone]
    head, tail = rig.matrix_world @ rb.head_local, rig.matrix_world @ rb.tail_local
    out = []
    for comp in _components(obj.data):
        if len(comp) < 8:
            continue
        pts, rep = derive_centreline(obj, comp, head, tail)
        out.append((pts, comp, rep))
    return out


# ------------------------------------------------------------------ colliders

def _strongest(obj, bones):
    """{bone name: [world positions of vertices whose strongest deform weight is that bone]}"""
    names = {g.index: g.name for g in obj.vertex_groups}
    mw = obj.matrix_world
    out = {}
    for v in obj.data.vertices:
        best = None
        for x in v.groups:
            n = names.get(x.group)
            if n is not None and x.weight > 0 and (best is None or x.weight > best[1]):
                best = (n, x.weight)
        if best and best[0] in bones:
            out.setdefault(best[0], []).append(mw @ v.co)
    return out


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0.0


def collider_bones(rig):
    """The head and neck bones: rig-anything's body map when it is importable, else by name."""
    try:
        from rig_analysis import bodymap
        roles = bodymap.build(rig.name)["roles"]
        head = roles.get("head")
        neck = list(roles.get("neck") or [])
        if head:
            return head, neck, "rig-anything body map"
    except Exception:                                   # rig-anything missing or the map failed
        pass
    names = [b.name for b in rig.data.bones]
    head = next((n for n in names if re.search(r"(^|[^a-z])head($|[^a-z])", n.lower())), None)
    neck = [n for n in names if "neck" in n.lower()]
    return head, neck, "bone names"


COLLIDER_PERCENTILE = 0.95  # of the skin's distances from a collider's axis: its radius


def _percentile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0.0


def colliders(rig, bodies, exclude=()):
    """What keeps a strand out of the head and neck, from the skin that rides those bones, world space.

    The head is an ellipsoid on its bone's axes: centred on the middle of its skin's bounds in that
    frame, half those bounds its radii. A head is deeper than it is wide, and a capsule round it
    either stood proud of its sides or left the back of the skull - where a ponytail hangs - uncovered:
    on the MPFB woman a capsule of the 95th percentile radius (9.7 cm) let a ponytail thrown forward
    go 7 mm into the back of her head (11 cm from the middle), one round the skin's centroid 6.7 cm
    (her dense face pulled the centroid 5 cm forward). Each neck bone is a capsule along the bone
    through the middle of its skin's bounds, with the 95th percentile of that skin's distance from
    the axis (over the middle half of its length) for its radius, its ends pulled in by the radius."""
    head, neck, source = collider_bones(rig)
    wanted = ([head] if head else []) + list(neck)
    pos = {}
    for body in bodies:
        if body.name in exclude:
            continue
        for k, v in _strongest(body, set(wanted)).items():
            pos.setdefault(k, []).extend(v)
    out = []
    for bname in wanted:
        pts = pos.get(bname, [])
        if len(pts) < 8:
            continue
        b = rig.data.bones[bname]
        R = (rig.matrix_world.to_3x3() @ b.matrix_local.to_3x3()).normalized()
        axes = [R.col[i].normalized() for i in range(3)]
        coords = [[p.dot(ax) for ax in axes] for p in pts]
        lo = [min(c[i] for c in coords) for i in range(3)]
        hi = [max(c[i] for c in coords) for i in range(3)]
        mid = [(lo[i] + hi[i]) / 2 for i in range(3)]
        c = axes[0] * mid[0] + axes[1] * mid[1] + axes[2] * mid[2]
        if bname == head:
            radii = [(hi[i] - lo[i]) / 2 for i in range(3)]
            out.append({"name": "head", "bone": bname, "shape": "ellipsoid", "a": c, "b": c, "axes": axes,
                        "radii_m": radii, "radius_m": max(radii)})
            continue
        axis = axes[1]
        along = [(p - c).dot(axis) for p in pts]
        a0, a1 = min(along), max(along)
        band = [p for p, t in zip(pts, along) if a0 + 0.25 * (a1 - a0) <= t <= a1 - 0.25 * (a1 - a0)] or pts
        r = _percentile([((p - c) - axis * (p - c).dot(axis)).length for p in band], COLLIDER_PERCENTILE)
        ta, tb = a0 + r, a1 - r
        if ta > tb:
            ta = tb = (a0 + a1) / 2
        out.append({"name": "neck_" + re.sub(r"[^A-Za-z0-9]+", "_", bname), "bone": bname, "shape": "capsule",
                    "a": c + axis * ta, "b": c + axis * tb, "radius_m": r})
    return out, source


# ------------------------------------------------------------------ building

def _safe(name):
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


def _material(kind):
    from . import registry
    reg = registry.load()
    entry = reg["types"].get(kind, {})
    mat = entry.get("material", "hair")
    params = dict(DEFAULTS)
    params.update(reg["materials"].get(mat, {}).get("strand", {}))
    return mat, params


def recognise_type(obj):
    from . import registry
    if obj.get(KIND_PROP):
        return str(obj[KIND_PROP]), "custom property " + KIND_PROP
    rec = registry.recognise(features={}, name=obj.name, family="strand", cls="strand")
    return rec["type"], "; ".join(rec["evidence"]) or "default"


def frequency(hanging_m, params):
    """A strand below a joint swings as a hanging compound pendulum of that length:
    f = (1 / 2 pi) sqrt(3 g / 2 h), scaled and clamped by the material."""
    h = max(hanging_m, 1e-3)
    f = params["pendulum_scale"] * math.sqrt(1.5 * G / h) / (2 * math.pi)
    return max(params["min_frequency_hz"], min(params["max_frequency_hz"], f))


def prepare(obj_name, rig_name=None, root_bone=None, kind=None, overrides=None, bodies=None):
    """Hang a bone chain along each of a strand mesh's centrelines, weight the mesh to it and write
    the spec. Re-running replaces the chains this object had.

    root_bone   the bone it grows from (default the object's `ft_root_bone`)
    kind        a strand type (`ponytail`, `long_hair`); default `ft_strand_type`, the name, the default
    overrides   material values: damping_ratio, max_angle_deg, segment_m, frequency_hz (all bones)...
    bodies      meshes the head and neck colliders are measured from (default every other mesh
                skinned to the rig)"""
    from . import classify
    obj = bpy.data.objects[obj_name]
    root_bone = root_bone or obj.get(ROOT_PROP)
    rig = bpy.data.objects[rig_name] if rig_name else _rig_for(obj, root_bone)
    if rig is None:
        return {"error": f"{obj_name}: no armature found - pass rig_name"}
    if not root_bone or root_bone not in rig.data.bones:
        return {"error": f"{obj_name}: root bone {root_bone!r} is not in {rig.name} - set {ROOT_PROP}"}
    if kind is None:
        kind, kind_source = recognise_type(obj)
    else:
        kind_source = "caller"
    mat, params = _material(kind)
    params.update(overrides or {})
    report = {"object": obj_name, "rig": rig.name, "root_bone": root_bone, "type": kind,
              "type_source": kind_source, "material": mat, "warnings": []}

    lines = centrelines(obj, rig, root_bone)
    if not lines:
        return dict(report, error=f"{obj_name}: no centreline given and no part big enough to derive one")
    base = STRAND_PREFIX + _safe(obj_name)
    chains = []
    for ci, (pts, comp, line_rep) in enumerate(lines):
        if len(pts) < 2:
            report["warnings"].append(f"chain {ci}: a centreline needs two points")
            continue
        length = _arc(pts)[-1]
        n = int(max(params["min_bones"], min(params["max_bones"], round(length / params["segment_m"]))))
        joints = resample(pts, n)
        chains.append({"name": f"{base}_{ci}" if len(lines) > 1 else base, "points": pts,
                       "joints": joints, "length_m": length, "vertices": comp, "centreline": line_rep})

    _add_bones(rig, root_bone, chains, base)
    weights = _weight(obj, rig, root_bone, chains)
    bodies = bodies if bodies is not None else [
        o for o in bpy.data.objects if o.type == "MESH" and o is not obj and not is_strand(o)
        and any(m.type == "ARMATURE" and m.object is rig for m in o.modifiers)]
    caps, cap_source = colliders(rig, [bpy.data.objects[b] if isinstance(b, str) else b for b in bodies])
    if not caps:
        report["warnings"].append("no head or neck collider: nothing keeps the strand out of the head")

    rec = classify.classify(obj_name)
    s = ft_spec.build(obj, rec)
    s["type"] = kind
    s["strands"] = strand_block(rig, root_bone, chains, weights["radius"], caps, params, mat)
    ft_spec.write(obj, s)
    report.update(chains=[{"name": c["name"], "bones": len(c["joints"]) - 1, "length_m": round(c["length_m"], 4),
                           "centreline": c["centreline"]} for c in chains],
                  weights={k: v for k, v in weights.items() if k != "radius"},
                  colliders=[{"name": c["name"], "bone": c["bone"], "shape": c["shape"],
                              "radius_m": round(c["radius_m"], 4)} for c in caps],
                  collider_source=cap_source, spec=s)
    return report


def _add_bones(rig, root_bone, chains, base):
    inv = rig.matrix_world.inverted()
    win = bpy.context.window
    prev_scene = win.scene
    prev_active = bpy.context.view_layer.objects.active
    win.scene = rig.users_scene[0]
    try:
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        bpy.context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        eb = rig.data.edit_bones
        for b in [b for b in eb if b.name.startswith(base + "_")]:
            eb.remove(b)
        for c in chains:
            parent = eb[root_bone]
            names = []
            for i, (a, b) in enumerate(zip(c["joints"], c["joints"][1:])):
                bone = eb.new(f"{c['name']}_{i:02d}")
                bone.head = inv @ a
                bone.tail = inv @ b
                bone.align_roll(Vector((1, 0, 0)) if abs((b - a).normalized().x) < 0.9 else Vector((0, 1, 0)))
                bone.parent = parent
                bone.use_connect = i > 0
                bone.use_deform = True
                # tagged, so rig-anything's body map leaves it out of the head and spine
                bone[ROLE_PROP] = "strand"
                parent = bone
                names.append(bone.name)
            c["bones"] = names
        bpy.ops.object.mode_set(mode="OBJECT")
    finally:
        if bpy.context.view_layer.objects.active is not None and bpy.context.view_layer.objects.active.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        win.scene = prev_scene
        if prev_active is not None and prev_active.name in bpy.context.view_layer.objects:
            bpy.context.view_layer.objects.active = prev_active


def _weight(obj, rig, root_bone, chains):
    """Weights along each chain: the root bone at the strand's root, then each bone full at its
    middle and shared linearly with its neighbours between middles. Replaces every bone weight the
    mesh had (a hair shell rigidly on the head, say); other groups stay."""
    bone_names = {b.name for b in rig.data.bones}
    for g in [g for g in obj.vertex_groups if g.name in bone_names]:
        obj.vertex_groups.remove(g)
    groups = {root_bone: obj.vertex_groups.new(name=root_bone)}
    for c in chains:
        for n in c["bones"]:
            groups[n] = obj.vertex_groups.new(name=n)
    if not any(m.type == "ARMATURE" and m.object is rig for m in obj.modifiers):
        for m in [m for m in obj.modifiers if m.type == "ARMATURE"]:
            obj.modifiers.remove(m)
        mod = obj.modifiers.new("Armature", "ARMATURE")
        mod.object = rig
    if obj.parent is not rig or obj.parent_type != "OBJECT":
        # skinned now: a bone parent as well would move it twice
        mw = obj.matrix_world.copy()
        obj.parent = rig
        obj.parent_type = "OBJECT"
        obj.matrix_parent_inverse = rig.matrix_world.inverted()
        obj.matrix_world = mw
    mw = obj.matrix_world
    member = {}
    for ci, c in enumerate(chains):
        for i in c["vertices"] or ():
            member[i] = ci
    radius = {n: [] for c in chains for n in c["bones"]}
    far = 0.0
    for v in obj.data.vertices:
        p = mw @ v.co
        if v.index in member:
            ci = member[v.index]
            s, d = _project(p, chains[ci]["joints"])
        else:
            ci, s, d = min(((k, *_project(p, c["joints"])) for k, c in enumerate(chains)), key=lambda x: x[2])
        c = chains[ci]
        n = len(c["bones"])
        seg = c["length_m"] / n
        u = s / seg
        far = max(far, d)
        k = min(n - 1, int(u))
        radius[c["bones"][k]].append(d)
        if u <= 0.5:
            pairs = [(root_bone, 1.0 - u / 0.5), (c["bones"][0], u / 0.5)]
        elif u >= n - 0.5:
            pairs = [(c["bones"][-1], 1.0)]
        else:
            j = int(u - 0.5)
            t = (u - 0.5) - j
            pairs = [(c["bones"][j], 1.0 - t), (c["bones"][j + 1], t)]
        for name, w in pairs:
            if w > 1e-4:
                groups[name].add([v.index], w, "REPLACE")
    return {"vertices": len(obj.data.vertices), "furthest_from_centreline_m": round(far, 4),
            "radius": {k: _median(v) for k, v in radius.items()}}


def _gltf(rig, p):
    inv = rig.matrix_world.inverted()
    return [round(x, 5) for x in ft_spec.to_gltf(inv @ p)]


def strand_block(rig, root_bone, chains, radius, caps, params, mat):
    """The spec's `strands` block: bones per chain in armature space, glTF axes, and colliders."""
    out = []
    for c in chains:
        n = len(c["bones"])
        seg = c["length_m"] / n
        bones = []
        for i, name in enumerate(c["bones"]):
            hanging = c["length_m"] - i * seg
            bones.append({
                "bone": name, "parent": root_bone if i == 0 else c["bones"][i - 1],
                "head": _gltf(rig, c["joints"][i]), "tail": _gltf(rig, c["joints"][i + 1]),
                "length_m": round((c["joints"][i + 1] - c["joints"][i]).length, 5),
                "hanging_m": round(hanging, 4),
                "radius_m": round(radius.get(name, 0.0), 4),
                "frequency_hz": round(params["frequency_hz"] if "frequency_hz" in params
                                      else frequency(hanging, params), 4),
                "damping_ratio": params["damping_ratio"],
                "max_angle_deg": params["root_max_angle_deg"] if i == 0 else params["max_angle_deg"],
            })
        out.append({"name": c["name"], "root_bone": root_bone, "length_m": round(c["length_m"], 4),
                    "bones": bones})
    return {
        "space": "gltf_armature", "armature": rig.name, "material": mat,
        "gravity_scale": params["gravity_scale"], "response": params["response"],
        "collision_margin_m": params["collision_margin_m"],
        "collision_friction": params["collision_friction"],
        "chains": out,
        "colliders": [_collider_entry(rig, c) for c in caps],
    }


def _collider_entry(rig, c):
    e = {"name": c["name"], "bone": c["bone"], "shape": c["shape"], "a": _gltf(rig, c["a"]), "b": _gltf(rig, c["b"]),
         "radius_m": round(c["radius_m"], 4)}
    if c["shape"] == "ellipsoid":
        rot = rig.matrix_world.inverted().to_3x3()
        e["axes"] = [[round(x, 5) for x in ft_spec.to_gltf((rot @ ax).normalized())] for ax in c["axes"]]
        e["radii_m"] = [round(r, 4) for r in c["radii_m"]]
    return e


def set_params(obj_name, **params):
    """Change values on every bone of every chain (frequency_hz, damping_ratio, max_angle_deg) or on
    the block (gravity_scale, response, collision_margin_m, collision_friction), without rebuilding."""
    obj = bpy.data.objects[obj_name]
    s = ft_spec.read(obj)
    blk = s["strands"]
    for k, v in params.items():
        if k in ("gravity_scale", "response", "collision_margin_m", "collision_friction"):
            blk[k] = v
        else:
            for c in blk["chains"]:
                for b in c["bones"]:
                    b[k] = v
    return ft_spec.write(obj, s)


# ------------------------------------------------------------------ export

def export(path, objects, rig_name):
    """Write the strand meshes with the rig and no clips, through rig-anything's `export_glb`, and
    read the file back: every strand bone in the skin where the spec puts it. The body goes out
    through rig-anything's `export_character` from the same rig."""
    from rig_analysis import export as rx
    from . import export as ft_export
    written = rx.export_glb(path, list(objects) + [rig_name], actions=[], rig_name=rig_name)
    if "error" in written:
        return {"path": path, "passed": False, "error": written["error"]}
    m = ft_export.verify(path, expect_meshes=list(objects))
    m["written"] = {k: written.get(k) for k in ("exported", "morph_targets", "options_dropped_by_this_blender")}
    return m


def summarize(r):
    if "error" in r:
        return "ERROR " + r["error"]
    lines = [f"{r['object']}: {r['type']} ({r['material']}) on {r['rig']}:{r['root_bone']}"]
    for c in r["chains"]:
        lines.append(f"  {c['name']}: {c['bones']} bones over {c['length_m']} m, centreline by "
                     f"{c['centreline']['method']}")
    for b in r["spec"]["strands"]["chains"][0]["bones"]:
        lines.append(f"    {b['bone']}: {b['frequency_hz']} Hz, zeta {b['damping_ratio']}, "
                     f"limit {b['max_angle_deg']} deg, radius {b['radius_m']} m")
    for c in r["colliders"]:
        lines.append(f"  collider {c['name']} ({c['shape']}) on {c['bone']}: radius {c['radius_m']} m")
    for w in r["warnings"]:
        lines.append("  WARNING " + w)
    return "\n".join(lines)
