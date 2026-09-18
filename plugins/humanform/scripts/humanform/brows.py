"""L6 part: eyebrows, eyelashes and light body hair on a baked MPFB body, and where its ears are.

    rep = brows.add(body, lm, colour=(0.12, 0.08, 0.05), base="StudyMan", brows=True, lashes=True)
    rep["objects"]      # {"brows": "StudyMan_brows", "lashes": "StudyMan_lashes"}
    brows.add(..., body_hair=True, sex="male")    # + "StudyMan_body_hair": forearms, shins, pubic; chest,
                                                  #   belly and thighs on a man
    brows.ear_vertices(body)                      # {"L": [...], "R": [...]} body vertex indices, or None

`hair.add(..., brows=True, lashes=True, body_hair=False)` calls this; the pipeline's `[hair]` section passes
the three switches through.

**Where things go.** A baked humanform body keeps MPFB's body vertices 0..13379 in base-mesh order (the
bake deletes only the helpers after them). `data/face_regions.json`, written by
`scripts/derive_face_regions.py` from MPFB's `base.obj`, stores by base index:
- the ears (the vertices MPFB's ear flap, wing and lobe targets bend), which `hair` keeps its cap off;
- MPFB's eyelash helper cards (`helper-{l,r}-eyelashes-{1,2}`, upper and lower lid, 92 quads a side), which
  the bake deletes, as proxy fits: each card vertex is a triangle of body vertices, barycentric weights and
  an offset along the triangle's normal in units of the triangle's size, so the cards follow the lids
  through every target and the fit;
- a brow card on each brow ridge (16 x 4), laid on the neutral face from the eye and stored the same way.

**Materials.** lookdev's hair material (`lookdev_blender.hair.material`) with its own strand settings per
part, so glTF carries alphaMode MASK, the strand texture and the `lookdev` extras that
`LookdevMaterials.apply` re-applies in Godot. Brows take the `[hair]` colour darkened by `BROW_DARKEN`,
lashes by `LASH_DARKEN`; lashes are two-sided (glTF doubleSided). Brow strands lean along the brow: V runs
across it from the lower edge (roots) to the upper edge (tips), U is sheared so a strand runs up and
toward the temple, upright at the brow's head and nearly along it by its tail.

**Body hair** (off unless asked): a shell 0.3 mm off the skin over the regions, cut from the body's faces
by bone weight (and facing, for the torso), with a sparse strand texture - the hair texture with most of
its strands removed in bands and the rest staggered - repeating in V every `BODY_HAIR_STRAND_M` along the
limb (down the torso), so it reads as short hairs with skin between them.

Everything is skinned like the body under it (weights interpolated from the triangle each vertex rides,
the head for brows and lashes). A body that is not an MPFB body (fewer than 13380 vertices) gets none of
it, and the report says so.
"""

from __future__ import annotations

import json
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector

BROW_DARKEN = 0.6           # brow colour: the hair colour's sRGB channels times this
LASH_DARKEN = 0.35
BODY_HAIR_DARKEN = 0.8
BODY_HAIR_STRAND_M = 0.014  # one strand's length on the skin; V repeats every this far
BODY_HAIR_KEEP = 0.22       # share of the texture's strand bands kept
BODY_HAIR_LIFT_M = 0.0003
TILE_M = 0.04
GODOT_SCISSOR = 2           # BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR

# lookdev hair preset overrides per part (keys of lookdev's `hair` material preset)
LOOK = {
    "brows": {"texture_px": [256, 512], "strands_per_tile": 90, "root_zone": [0.02, 0.3], "tip_zone": [0.6, 0.98],
              "root_fade": [0.0, 0.25], "tip_mult": 1.1, "gap_mult": 0.35, "wave_px": 0.8, "lock_jitter": 0.15},
    "lashes": {"texture_px": [256, 512], "strands_per_tile": 60, "root_zone": [0.0, 0.1], "tip_zone": [0.45, 0.97],
               "root_fade": [0.0, 0.04], "tip_mult": 1.0, "root_mult": 1.0, "gap_mult": 0.3, "wave_px": 0.5},
    "body_hair": {"texture_px": [256, 512], "strands_per_tile": 48, "root_zone": [0.05, 0.4], "tip_zone": [0.6, 0.95],
                  "root_fade": [0.0, 0.2], "tip_mult": 1.15, "gap_mult": 0.5, "wave_px": 1.2},
}

_DATA = None


def regions():
    global _DATA
    if _DATA is None:
        import humanform as pkg
        with open(os.path.join(pkg.DATA, "face_regions.json"), encoding="utf-8") as fh:
            _DATA = json.load(fh)
    return _DATA


def is_mpfb(ob):
    return len(ob.data.vertices) >= regions()["n_body"]


def ear_vertices(ob):
    """{"L": [indices], "R": [indices]} of the body's ear vertices, or None for a body that is not MPFB's."""
    if not is_mpfb(ob):
        return None
    d = regions()["ears"]
    return {"L": list(d["L"]), "R": list(d["R"])}


def _rebuild(co, fits):
    f = np.asarray(fits, np.float64)
    ia, ib, ic = f[:, 0].astype(int), f[:, 1].astype(int), f[:, 2].astype(int)
    a, b, c = co[ia], co[ib], co[ic]
    n = np.cross(b - a, c - a)
    area2 = np.linalg.norm(n, axis=1)
    n = n / area2[:, None]
    return (f[:, 3:4] * a + f[:, 4:5] * b + f[:, 5:6] * c + (f[:, 6] * np.sqrt(area2 / 2))[:, None] * n,
            (ia, ib, ic), f[:, 3:6])


def _vertex_weights(ob, indices):
    """{vertex: {group name: weight}} for the given body vertices."""
    names = {g.index: g.name for g in ob.vertex_groups}
    out = {}
    for i in set(int(x) for x in indices):
        out[i] = {names[e.group]: e.weight for e in ob.data.vertices[i].groups if e.weight > 1e-4 and e.group in names}
    return out


def _darken(colour, k):
    return tuple(max(0.0, min(1.0, c * k)) for c in colour)


def _material(name, colour, uv_name, part, double_sided=False):
    try:
        from lookdev_blender import hair as ld_hair
    except ImportError:
        ld_hair = None
    if ld_hair is None:
        from . import look
        mat = look.material(name, srgb=colour, roughness=0.5)
        return mat, {"material": mat.name, "source": "flat (lookdev_blender not importable)"}, TILE_M
    over = dict(LOOK[part])
    # in Godot, scissor rather than the hair preset's depth pre-pass: a card this fine and this close to the
    # skin blends its many sub-cutoff strand fringes into a grey haze (eyeshadow round the lashes, a smudge under
    # the brow); cut at the same 0.5 the exporter writes, it is strands with skin between them
    over["godot"] = dict(ld_hair.preset("hair")["godot"], transparency=GODOT_SCISSOR)
    mat, rep = ld_hair.material(name, colour, uv_map=uv_name, **over)
    if double_sided:
        mat.use_backface_culling = False
    return mat, dict(rep, source="lookdev", double_sided=double_sided), rep["tile_m"]


def _card_object(name, body, rig, pts_world, faces, uvs, weights, uv_name, tile):
    """A mesh from world points, quads and per-vertex UVs (U in metres, divided by `tile`)."""
    from .hair import _object
    bm = bmesh.new()
    verts = [bm.verts.new(Vector(p)) for p in pts_world]
    bm.verts.index_update()                     # a new BMVert's index is not its place until this
    uv = bm.loops.layers.uv.new(uv_name)
    for q in faces:
        f = bm.faces.new([verts[i] for i in q])
        f.smooth = True
        for loop in f.loops:
            u, v = uvs[loop.vert.index]
            loop[uv].uv = (u / tile, v)
    ob = _object(name, bm, body, rig, weights)
    bm.free()
    return ob


def _interp_weights(ob, tris, bary, fallback):
    """Per-card-vertex weights interpolated from the triangle each vertex rides: {group: array}."""
    ia, ib, ic = tris
    table = _vertex_weights(ob, np.concatenate([ia, ib, ic]))
    groups = sorted({g for w in table.values() for g in w})
    out = {g: np.zeros(len(ia)) for g in groups}
    for k in range(len(ia)):
        for idx, w in ((ia[k], bary[k, 0]), (ib[k], bary[k, 1]), (ic[k], bary[k, 2])):
            for g, x in table[int(idx)].items():
                out[g][k] += w * x
    if not groups:
        return {fallback: np.ones(len(ia))}
    total = sum(out.values())
    total = np.where(total > 1e-6, total, 1.0)
    return {g: np.clip(w / total, 0.0, 1.0) for g, w in out.items() if w.max() > 1e-3}


def _cards(ob, co, part, base, rig, colour, uv_name, head):
    d = regions()[part]
    mat, mat_rep, tile = _material(f"{base}_{part}", colour, uv_name, part, double_sided=(part == "lashes"))
    pts, faces, uvs, tris, bary = [], [], [], ([], [], []), []
    for side in ("L", "R"):
        card = d[side]
        p, (ia, ib, ic), w = _rebuild(co, card["fit"])
        off = len(pts)
        pts.extend(p.tolist())
        faces.extend([[off + i for i in q] for q in card["faces"]])
        uvs.extend(card["uv"])
        tris[0].extend(ia.tolist())
        tris[1].extend(ib.tolist())
        tris[2].extend(ic.tolist())
        bary.extend(w.tolist())
    tris = tuple(np.array(t) for t in tris)
    weights = _interp_weights(ob, tris, np.array(bary), head)
    card = _card_object(f"{base}_{part}", ob, rig, pts, faces, uvs, weights, uv_name, tile)
    card.data.materials.append(mat)
    card["humanform_hair"] = {"part": part}
    # the lash roots and the brow must lie on the skin: the distance of each card's root row from the body
    return card, {"faces": len(faces), "verts": len(pts), "weights": sorted(weights),
                  "material": {k: mat_rep.get(k) for k in ("material", "source", "gltf", "double_sided")},
                  "colour": [round(c, 4) for c in colour]}


# ------------------------------------------------------------------------------------------ body hair

def _sparse(mat_rep, seed=3):
    """Thin the body hair texture: keep BODY_HAIR_KEEP of its strand bands, each rolled along V at random so
    the kept strands do not start on one row."""
    img = bpy.data.images[mat_rep["image"]]
    nimg = bpy.data.images.get(mat_rep["gltf"]["normalTexture"]) if mat_rep.get("gltf") else None
    W, H = img.size
    px = np.empty(W * H * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(H, W, 4)
    npx = None
    if nimg is not None:
        npx = np.empty(W * H * 4, np.float32)
        nimg.pixels.foreach_get(npx)
        npx = npx.reshape(H, W, 4)
    rng = np.random.RandomState(seed)
    band = max(2, W // LOOK["body_hair"]["strands_per_tile"])
    for x0 in range(0, W, band):
        cols = slice(x0, min(W, x0 + band))
        if rng.uniform() > BODY_HAIR_KEEP:
            px[:, cols, 3] = 0.0
            continue
        shift = int(rng.randint(0, H))
        px[:, cols] = np.roll(px[:, cols], shift, axis=0)
        if npx is not None:
            npx[:, cols] = np.roll(npx[:, cols], shift, axis=0)
    img.pixels.foreach_set(px.ravel())
    img.pack()
    if npx is not None:
        nimg.pixels.foreach_set(npx.ravel())
        nimg.pack()


def _weights_array(ob, name):
    g = ob.vertex_groups.get(name)
    w = np.zeros(len(ob.data.vertices))
    if g is None:
        return w
    for v in ob.data.vertices:
        for e in v.groups:
            if e.group == g.index:
                w[v.index] = e.weight
    return w


def body_hair_regions(ob, co, normals, sex):
    """{region: boolean vertex mask} over the body's first n_body vertices."""
    n = regions()["n_body"]
    co, normals = co[:n], normals[:n]
    W = {name: _weights_array(ob, name)[:n] for name in
         ("forearm.L", "forearm.R", "shin.L", "shin.R", "thigh.L", "thigh.R", "spine", "spine.001", "spine.002",
          "spine.003")}
    front = -normals[:, 1]
    out = {"forearms": (W["forearm.L"] + W["forearm.R"]) > 0.6,
           "shins": (W["shin.L"] + W["shin.R"]) > 0.6}
    # the crotch: the lowest point of the body's middle above the knees
    mid = co[(np.abs(co[:, 0]) < 0.01) & (co[:, 2] > 0.5)]
    crotch = float(mid[:, 2].min()) if len(mid) else 0.8
    out["pubic"] = ((co[:, 2] > crotch + 0.02) & (co[:, 2] < crotch + 0.1) & (np.abs(co[:, 0]) < 0.055 + 0.3 *
                    np.maximum(co[:, 2] - crotch - 0.02, 0.0)) & (front > 0.25))
    if sex == "male":
        out["thighs"] = ((W["thigh.L"] + W["thigh.R"]) > 0.6) & (co[:, 2] < crotch - 0.03)
        chest = W["spine.002"] + W["spine.003"]
        out["chest"] = (chest > 0.5) & (front > 0.55) & (np.abs(co[:, 0]) < 0.11)
        belly = W["spine.001"] + W["spine"]
        out["belly"] = (belly > 0.5) & (front > 0.5) & (np.abs(co[:, 0]) < 0.03 + 0.25 * np.maximum(
            crotch + 0.16 - co[:, 2], 0.0)) & (co[:, 2] > crotch + 0.08)
    return {k: v for k, v in out.items() if v.any()}


def _body_hair(ob, co, base, rig, colour, uv_name, sex):
    me = ob.data
    nrm = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("normal", nrm)
    m3 = np.array(ob.matrix_world.to_3x3(), np.float64)
    nrm = nrm.reshape(-1, 3).astype(np.float64) @ m3.T
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1), 1e-9)[:, None]
    masks = body_hair_regions(ob, co, nrm, sex)
    mat, mat_rep, tile = _material(f"{base}_body_hair", colour, uv_name, "body_hair")
    if mat_rep.get("source") == "lookdev":
        _sparse(mat_rep)
    region_of = np.full(len(co), -1)
    names = sorted(masks)
    for k, name in enumerate(names):
        region_of[np.nonzero(masks[name])[0]] = k
    bones = rig.data.bones if rig is not None else None
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    src_layer = bm.verts.layers.int.new("hf_src")
    for v in bm.verts:
        v[src_layer] = v.index
    keep = [f for f in bm.faces if all(region_of[v.index] >= 0 for v in f.verts)
            and len({region_of[v.index] for v in f.verts}) == 1]
    counts = {name: 0 for name in names}
    for f in keep:
        counts[names[region_of[f.verts[0].index]]] += 1
    region_face = {f: names[region_of[f.verts[0].index]] for f in keep}
    keep_set = set(keep)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f not in keep_set], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    for layer in list(bm.loops.layers.uv.values()):
        bm.loops.layers.uv.remove(layer)
    for layer in list(bm.loops.layers.color.values()):
        bm.loops.layers.color.remove(layer)
    dl = bm.verts.layers.deform.active
    src = [v[src_layer] for v in bm.verts]      # the body vertex each shell vertex was cut from
    mw = ob.matrix_world
    for v, i in zip(bm.verts, src):
        v.co = mw @ v.co + Vector(nrm[i]) * BODY_HAIR_LIFT_M
    bm.verts.layers.int.remove(src_layer)
    uv = bm.loops.layers.uv.new(uv_name)
    # V along the limb's bone (down the torso) every BODY_HAIR_STRAND_M, U around it in tiles
    axis_of = {"forearms": ("forearm.L", "forearm.R"), "shins": ("shin.L", "shin.R"), "thighs": ("thigh.L", "thigh.R")}
    for f, name in region_face.items():
        for loop in f.loops:
            p = loop.vert.co
            bone_names = axis_of.get(name)
            if bone_names and bones is not None and all(b in bones for b in bone_names):
                b = bones[bone_names[0] if p.x > 0 else bone_names[1]]
                h = rig.matrix_world @ b.head_local
                t = rig.matrix_world @ b.tail_local
                ax = (t - h).normalized()
                rel = p - h
                along = rel.dot(ax)
                radial = rel - ax * along
                ref = Vector((0.0, -1.0, 0.0))
                r0 = (ref - ax * ref.dot(ax)).normalized()
                ang = math.atan2(radial.dot(ax.cross(r0)), radial.dot(r0))
                loop[uv].uv = (ang * 0.04 / tile, along / BODY_HAIR_STRAND_M)
            else:
                loop[uv].uv = (p.x / tile, -p.z / BODY_HAIR_STRAND_M)
    for f in bm.faces:
        f.smooth = True
    weights = {}
    if dl is not None:
        names_g = {g.index: g.name for g in ob.vertex_groups}
        per = {}
        for k, v in enumerate(bm.verts):
            for gi, w in v[dl].items():
                if gi in names_g and w > 1e-4:
                    per.setdefault(names_g[gi], np.zeros(len(bm.verts)))[k] = w
            v[dl].clear()
        weights = per
    bm.verts.index_update()
    from .hair import _object
    hob = _object(f"{base}_body_hair", bm, ob, rig, weights)
    bm.free()
    hob.data.materials.append(mat)
    hob["humanform_hair"] = {"part": "body_hair"}
    return hob, {"faces": len(hob.data.polygons), "verts": len(hob.data.vertices), "regions": counts,
                 "sex": sex, "material": {k: mat_rep.get(k) for k in ("material", "source", "gltf")},
                 "source_vertices": len(src)}


# ------------------------------------------------------------------------------------------ entry

def add(body, lm, colour, base, rig=None, uv_name="UVMap", brows=True, lashes=True, body_hair=False, sex=None):
    """Brows, lashes and (optionally) body hair on a baked MPFB body. `lm` is `hair.landmarks(body)`;
    `colour` the scalp hair's screen (sRGB) colour. Returns {objects, parts, skipped}."""
    from . import body as _body
    ob = _body.obj(body)
    out = {"objects": {}, "parts": {}, "skipped": None}
    if not (brows or lashes or body_hair):
        return out
    if not is_mpfb(ob):
        out["skipped"] = f"{ob.name} has {len(ob.data.vertices)} vertices, fewer than an MPFB body's " \
                         f"{regions()['n_body']}: no brows, lashes or body hair"
        return out
    co = lm["_co"]
    head = lm["head_bone"]
    for part, on, k in (("brows", brows, BROW_DARKEN), ("lashes", lashes, LASH_DARKEN)):
        if not on:
            continue
        card, rep = _cards(ob, co, part, base, rig, _darken(colour, k), uv_name, head)
        out["objects"][part] = card.name
        out["parts"][part] = rep
    if body_hair:
        hob, rep = _body_hair(ob, co, base, rig, _darken(colour, BODY_HAIR_DARKEN), uv_name, sex)
        out["objects"]["body_hair"] = hob.name
        out["parts"]["body_hair"] = rep
    return out
