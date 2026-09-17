"""Delta parts: a sculpted displacement of the shared MPFB mesh, stored per vertex, applied to any body.

A target part (`parts`) is a set of MPFB target weights. A **delta** part is a shape MPFB has no
target for - muscle definition, a knuckle, a scar - stored as how far each vertex moves along its own
normal, in named groups that are scaled separately when the part is applied:

    card = delta.store("muscle", "definition-v1", {"abdominals": h_abs, "deltoids": h_delt},
                       reference={"stature_m": 1.668}, tags=["muscle"])
    delta.apply(human, card, weights={"abdominals": 0.3, "deltoids": 0.9})      # a shape key
    delta.apply(baked_mesh, card, weights=w, mode="mesh")                         # into the vertices
    library.apply(human, card)                                                     # the same, all groups at 1

Why along the normal: every MPFB body shares one mesh, so vertex i is the same place on the body
(the navel, the top of the deltoid) on a short woman and a tall heavy man; its normal there is the
body's own. A height measured on the reference body is scaled by the wearer's stature over the
reference's and pushed along the wearer's normal, so the bulge sits on the wearer's surface rather
than where the reference's surface was. Heights are stored in micrometres, as integers, so a card is
exact JSON and a stored part reproduces bit for bit.

Indices are into MPFB's hm08 body: vertices 0..BODY_VERTS-1 of a humanform body, before or after
rig-anything's `bake_for_game` (the helper geometry it removes comes after the body, and the eyes
humanform joins come after that), so one card applies at every stage.

`mode="key"` writes (or rewrites) a shape key `hfd:<region>` on an unbaked body - relative to the
basis, displaced along the normals of the body as its current targets shape it - so `bake_for_game`
folds it in at its value, and `library.capture` (which reads `hf:` keys) never stores it as a target.
Set its value to 0 to keep the definition out of the geometry and bake it into a normal map instead
(`high_copy` and lookdev's `detail.bake_normal_from_high`).
"""

from __future__ import annotations

import datetime

import bpy
import numpy as np

from . import library

BODY_VERTS = 13380          # hm08's body vertices (MPFB puts helpers after them)
KEY_PREFIX = "hfd:"
UNIT = 1e-6                 # stored heights are micrometres


def _obj(o):
    return bpy.data.objects[o] if isinstance(o, str) else o


def check_topology(ob):
    """None when `ob` carries hm08's body at the front of its vertices, else the problem."""
    me = _obj(ob).data
    n = len(me.vertices)
    if n < BODY_VERTS:
        return f"{ob.name if hasattr(ob, 'name') else ob} has {n} vertices; an MPFB hm08 body has {BODY_VERTS}"
    # hm08's first face and vertex 0's valence: a cheap fingerprint that tells another mesh apart
    if tuple(me.polygons[0].vertices) != HM08_FACE0:
        return f"{_obj(ob).name}'s first face is {tuple(me.polygons[0].vertices)}, not hm08's {HM08_FACE0}"
    return None


HM08_FACE0 = (4848, 0, 1, 4847)   # hm08's first quad, as MPFB 2 loads it


def mixed_coords(ob):
    """Object-space vertex positions of the body as its shape keys currently mix (relative keys,
    muted keys and `hfd:` keys skipped), or the mesh's own positions when it has no keys."""
    me = _obj(ob).data
    n = len(me.vertices)
    co = np.empty(n * 3, np.float64)
    keys = me.shape_keys
    if keys is None or not keys.use_relative:
        me.vertices.foreach_get("co", co)
        return co.reshape(n, 3)
    basis = keys.key_blocks[0]
    basis.data.foreach_get("co", co)
    base = co.reshape(n, 3).copy()
    out = base.copy()
    tmp = np.empty(n * 3, np.float64)
    for kb in keys.key_blocks[1:]:
        if kb.mute or abs(kb.value) < 1e-9 or kb.name.startswith(KEY_PREFIX):
            continue
        rel = kb.relative_key
        kb.data.foreach_get("co", tmp)
        d = tmp.reshape(n, 3) - (base if rel == basis else _key_co(rel, n))
        if kb.vertex_group:
            vg = _obj(ob).vertex_groups.get(kb.vertex_group)
            if vg is not None:
                w = np.zeros(n)
                for v in me.vertices:
                    for g in v.groups:
                        if g.group == vg.index:
                            w[v.index] = g.weight
                d = d * w[:, None]
        out += d * kb.value
    return out


def _key_co(kb, n):
    a = np.empty(n * 3, np.float64)
    kb.data.foreach_get("co", a)
    return a.reshape(n, 3)


def body_faces(ob):
    """hm08 body faces as a (F, 4) index array (every body face is a quad)."""
    me = _obj(ob).data
    loops = np.empty(len(me.polygons), np.int64)
    starts = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_total", loops)
    me.polygons.foreach_get("loop_start", starts)
    lv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    quads = loops == 4
    idx = starts[quads][:, None] + np.arange(4)[None, :]
    f = lv[idx]
    return f[np.all(f < BODY_VERTS, axis=1)]


def vertex_normals(co, faces):
    """Area-weighted vertex normals of quads (split into two triangles), for the first BODY_VERTS."""
    co = co[:BODY_VERTS]
    nrm = np.zeros_like(co)
    for a, b, c in ((0, 1, 2), (0, 2, 3)):
        fn = np.cross(co[faces[:, b]] - co[faces[:, a]], co[faces[:, c]] - co[faces[:, a]])
        for j in (a, b, c):
            np.add.at(nrm, faces[:, j], fn)
    ln = np.linalg.norm(nrm, axis=1)
    return nrm / np.maximum(ln, 1e-12)[:, None]


def neighbours(faces, n=BODY_VERTS):
    """Vertex adjacency along quad edges, as (rows, cols) for a sparse average."""
    e = np.concatenate([faces[:, [i, (i + 1) % 4]] for i in range(4)])
    e = np.concatenate([e, e[:, ::-1]])
    e = np.unique(e, axis=0)
    return e[:, 0], e[:, 1]


def smooth(values, faces, iterations=2, share=0.5):
    """Laplacian smoothing of a per-vertex scalar over the mesh."""
    r, c = neighbours(faces)
    deg = np.bincount(r, minlength=BODY_VERTS).astype(np.float64)
    v = np.asarray(values, np.float64).copy()
    for _ in range(iterations):
        avg = np.bincount(r, weights=v[c], minlength=BODY_VERTS) / np.maximum(deg, 1)
        v = (1 - share) * v + share * avg
    return v


# ------------------------------------------------------------------ cards

def pack(heights, eps_um=1):
    """A per-vertex height array (metres) as sparse integer micrometres: {"index": [...], "value": [...]}."""
    h = np.rint(np.asarray(heights, np.float64) / UNIT).astype(np.int64)
    idx = np.nonzero(np.abs(h) >= eps_um)[0]
    return {"index": idx.tolist(), "value": h[idx].tolist()}


def unpack(group):
    h = np.zeros(BODY_VERTS, np.float64)
    h[np.asarray(group["index"], np.int64)] = np.asarray(group["value"], np.float64) * UNIT
    return h


def store(region, name, groups, reference, tags=(), critic=None, sex=None, style=None, thumb=None, notes=None):
    """Keep a delta part in the library. `groups`: {name: per-vertex heights in metres (BODY_VERTS,)};
    `reference`: at least `stature_m` of the body the heights were measured on."""
    payload = {"type": "delta", "frame": "normal", "unit": "um", "reference": dict(reference),
               "groups": {g: pack(h) for g, h in sorted(groups.items())}}
    card = {"schema": library.SCHEMA, "kind": "part", "region": region, "name": name, "tags": list(tags),
            "sex": sex, "style": style, "topology": library.TOPOLOGY, "payload": payload,
            "quality": {"critic": critic}, "source": "sculpted", "notes": notes,
            "created": datetime.datetime.now().isoformat(timespec="seconds")}
    card["id"] = library._card_id(f"{region}-{name}", payload)
    return library._store(card, thumb)


def heights(card, weights=None, stature_m=None):
    """The combined per-vertex heights (metres) of a delta card: each group times its weight (1 when
    `weights` is None; a group missing from `weights` is 0), scaled by `stature_m` over the reference's."""
    card = library.load(card["id"]) if "payload" not in card else card
    p = card["payload"]
    if p.get("type") != "delta":
        raise ValueError(f"{card.get('id')} is not a delta part")
    out = np.zeros(BODY_VERTS, np.float64)
    for g, data in p["groups"].items():
        w = 1.0 if weights is None else float(weights.get(g, 0.0))
        if w:
            out += w * unpack(data)
    if stature_m:
        out *= float(stature_m) / float(p["reference"]["stature_m"])
    return out


def stature_of(co):
    b = co[:BODY_VERTS, 2]
    return float(b.max() - b.min())


def apply(ob, card, weights=None, mode="key", value=1.0, key_name=None, scale_to_body=True, refine=None):
    """Put a delta part on a body. Returns a report: the key or mode used, the stature it was scaled to,
    and per group the vertices moved and the largest height (mm) after scaling and weighting.

    `refine(heights, faces, scale) -> heights` (optional) is handed the combined heights of every group,
    after weighting and scaling to this body, and returns what is written. The groups are what was sculpted;
    the combined heights are what the surface carries, and only the second can be held to what the mesh can
    show - see `muscle.facet_guard`. The per-group rows stay as weighted and scaled, so `refined_max_mm`
    beside `max_mm` is what refining took off."""
    ob = _obj(ob)
    problem = check_topology(ob)
    if problem:
        raise ValueError(problem)
    card = library.load(card["id"]) if "payload" not in card else card
    co = mixed_coords(ob)
    faces = body_faces(ob)
    nrm = vertex_normals(co, faces)
    st = stature_of(co) if scale_to_body else None
    h = heights(card, weights, st)
    me = ob.data
    n = len(me.vertices)
    report = {"card": card.get("id"), "mode": mode, "stature_m": round(st, 4) if st else None,
              "scale": round(st / card["payload"]["reference"]["stature_m"], 4) if st else 1.0, "groups": {}}
    report["max_mm"] = round(float(np.abs(h).max()) * 1000, 2)
    if refine is not None:
        h = np.asarray(refine(h, faces, report["scale"]), np.float64)
        report["refined_max_mm"] = round(float(np.abs(h).max()) * 1000, 2)
    disp = np.zeros((n, 3))
    disp[:BODY_VERTS] = nrm * h[:, None]
    for g, data in card["payload"]["groups"].items():
        w = 1.0 if weights is None else float(weights.get(g, 0.0))
        gh = unpack(data) * w * (report["scale"])
        report["groups"][g] = {"weight": round(w, 3), "vertices": int(np.count_nonzero(np.abs(gh) > 1e-5)),
                               "max_mm": round(float(np.abs(gh).max()) * 1000, 2)}
    if mode == "key":
        if me.shape_keys is None:
            ob.shape_key_add(name="Basis", from_mix=False)
        name = key_name or f"{KEY_PREFIX}{card['region']}"
        kb = me.shape_keys.key_blocks.get(name) or ob.shape_key_add(name=name, from_mix=False)
        basis = me.shape_keys.key_blocks[0]
        b = np.empty(n * 3, np.float64)
        basis.data.foreach_get("co", b)
        kb.data.foreach_set("co", (b.reshape(n, 3) + disp).ravel())
        kb.relative_key = basis
        kb.slider_min = 0.0
        kb.value = value
        report["key"] = name
    elif mode == "mesh":
        if me.shape_keys is not None and len(me.shape_keys.key_blocks) > 1:
            raise ValueError(f"{ob.name} has shape keys; use mode='key' (bake_for_game folds it in)")
        cur = np.empty(n * 3, np.float64)
        me.vertices.foreach_get("co", cur)
        me.vertices.foreach_set("co", (cur.reshape(n, 3) + disp * value).ravel())
    else:
        raise ValueError("mode must be 'key' or 'mesh'")
    me.update()
    return report


def key_heights(ob, key_name=None, value=None):
    """What `ob`'s `hfd:` keys actually put on its surface: per-vertex heights (metres, (BODY_VERTS,))
    along the body's own normals, read back from the shape keys rather than recomputed from a card.

    `key_name` picks one key (None: every `hfd:` key on the mesh, summed - they share one surface, so what
    a vertex stands off its neighbours is their sum). `value` overrides the key's slider; None uses it,
    which is how the mesh is drawn. A missing key is zero."""
    ob = _obj(ob)
    me = ob.data
    n = len(me.vertices)
    out = np.zeros(BODY_VERTS, np.float64)
    keys = me.shape_keys
    if keys is None:
        return out
    names = [key_name] if key_name else [k.name for k in keys.key_blocks if k.name.startswith(KEY_PREFIX)]
    nrm = vertex_normals(mixed_coords(ob), body_faces(ob))
    basis = keys.key_blocks[0]
    b = np.empty(n * 3, np.float64)
    basis.data.foreach_get("co", b)
    b = b.reshape(n, 3)[:BODY_VERTS]
    tmp = np.empty(n * 3, np.float64)
    for name in names:
        kb = keys.key_blocks.get(name)
        if kb is None:
            continue
        kb.data.foreach_get("co", tmp)
        d = tmp.reshape(n, 3)[:BODY_VERTS] - b
        out += np.einsum("ij,ij->i", d, nrm) * (kb.value if value is None else float(value))
    return out


def static_copy(ob, key_name, value=1.0, name=None):
    """A static copy of a body with its delta key at `value` and every other key and modifier (the helper
    mask) as they are, the rig's pose ignored (rest), UVs and materials kept."""
    ob = _obj(ob)
    kb = ob.data.shape_keys.key_blocks[key_name]
    was = kb.value
    arm = {m.name: m.show_viewport for m in ob.modifiers if m.type == "ARMATURE"}
    try:
        kb.value = value
        for m in ob.modifiers:
            if m.type == "ARMATURE":
                m.show_viewport = False
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
    finally:
        kb.value = was
        for m in ob.modifiers:
            if m.name in arm:
                m.show_viewport = arm[m.name]
        bpy.context.view_layer.update()
    copy = bpy.data.objects.new(name or f"{ob.name}_static", me)
    for c in ob.users_collection:
        c.objects.link(copy)
    copy.matrix_world = ob.matrix_world.copy()
    return copy


def high_copy(ob, key_name, name=None):
    """The high source a normal map is baked from onto the body with the key at 0 (or onto its
    `bake_for_game` mesh): `static_copy` with the key at 1."""
    return static_copy(ob, key_name, 1.0, name=name or f"{_obj(ob).name}_high")
