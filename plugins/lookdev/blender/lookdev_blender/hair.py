"""The hair material preset: strands that survive glTF into Godot.

    from lookdev_blender import hair
    mat, rep = hair.material("Belle_hair", colour=(0.17, 0.10, 0.06))    # colour: a screen (sRGB) colour

A hair shell or card reads as hair, not as a painted helmet, from three things, and each is carried
the way glTF and Godot 4.7 can carry it:

- **Strands with a root-to-tip gradient.** A generated strand texture (`<name>_strands`, packed): fine
  strands in clumps across U, and along V a gradient from darker roots (V = 0) to lighter tips (V = 1).
  It is an image on Base Color, so glTF writes it as the base colour texture.
- **Thinned roots and tips.** The texture's alpha breaks into separate strands of uneven length below
  `root_zone[1]` and above `tip_zone[0]`, and is 0 at the very ends. Alpha goes through a Math Round
  node, which the exporter writes as alphaMode MASK (cutoff 0.5) and Godot imports as alpha scissor. A
  mesh maps its hairline to V near 0 and its tips to V near 1, so the edge is individual strands with
  skin between them rather than a cut.
- **Anisotropy, backlight, rim.** Blender renders anisotropy (Principled Anisotropic, turned to run
  along the strands); Godot's importer ignores KHR_materials_anisotropy and glTF has no backlight or rim.
  So the material carries a `lookdev` custom property - written as glTF material extras, which Godot
  keeps as the material's `extras` metadata - and `godot/addons/lookdev/lookdev_materials.gd` sets those
  StandardMaterial3D properties after import.

Mesh contract: the UV map the material reads has U across the strands in units of `tile_m` metres
(so strand width is the same on every part) and V along them, 0 at the root or hairline, 1 at the tip.
The texture repeats in U; V outside 0..1 must be clamped by the mesh (the ends are transparent).
"""

from __future__ import annotations

import json
import math
import os

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PRESETS = os.path.normpath(os.path.join(HERE, "..", "..", "presets", "materials.json"))


def presets():
    with open(PRESETS, encoding="utf-8") as fh:
        return json.load(fh)["materials"]


def preset(name="hair", **overrides):
    p = presets().get(name)
    if p is None:
        raise KeyError(f"no material preset {name!r} (have: {sorted(presets())})")
    p = json.loads(json.dumps(p))
    for k, v in overrides.items():
        if k not in p:
            raise KeyError(f"material preset {name!r} has no field {k!r}")
        p[k] = v
    return p


def _srgb_to_linear(c):
    c = min(max(float(c), 0.0), 1.0)
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(a):
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1 / 2.4) - 0.055)


def _smooth(e0, e1, x):
    t = np.clip((x - e0) / max(e1 - e0, 1e-9), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def strand_texture(colour_linear, p, seed=0):
    """(colour, normal): (H, W, 4) float arrays, rows bottom-up as Blender stores them (row 0 is V = 0). Colour
    is sRGB-encoded with straight alpha; normal is a tangent-space map (+X along U, +Y along V), encoded
    0..1. Deterministic for a seed."""
    W, H = p["texture_px"]
    rng = np.random.RandomState(seed)
    n = int(p["strands_per_tile"])
    nc = int(p["clumps_per_tile"])
    v = (np.arange(H) + 0.5) / H                                    # (H,)
    x = np.arange(W) + 0.5                                          # (W,)
    base = np.asarray(colour_linear[:3], np.float64)

    tone = (p["root_mult"] + (1 - p["root_mult"]) * _smooth(0.0, 0.35, v)) \
        * (1 + (p["tip_mult"] - 1) * _smooth(0.5, 1.0, v))          # root-to-tip gradient, (H,)
    clump = 1 + p["clump_jitter"] * rng.uniform(-1, 1, nc)
    # locks: a few broad bands per tile that wander along the strands, so hair reads in lengths, not as paint
    nl = int(p.get("locks_per_tile", 4))
    lock_phase = rng.uniform(0, 2 * math.pi, (nl, 2))
    uu = x / W
    lock = np.zeros((H, W))
    for k in range(nl):
        lock += np.sin(2 * math.pi * (k + 1) * (uu[None, :] + 0.03 * np.sin(2 * math.pi * v[:, None] * (k + 1)
                                                                          + lock_phase[k, 1])) + lock_phase[k, 0])
    lock = 1 + p.get("lock_jitter", 0.0) * lock / nl
    r0, r1 = p["root_zone"]
    t0, t1 = p["tip_zone"]
    # a feathered hairline (off at the defaults): where the opaque middle starts wanders across U by up to
    # `root_ragged` of V past root_zone[1], and each strand's root lies between root_zone[0] and that start,
    # skewed toward it by `root_power` (< 1: fewer strands reach the edge, so coverage thins out toward it). Its
    # own random stream, so a preset without it draws exactly the strands it always did.
    ragged = float(p.get("root_ragged", 0.0))
    rpow = float(p.get("root_power", 1.0))
    if ragged > 0:
        frng = np.random.RandomState(seed + 7919)
        uu0 = (np.arange(W) + 0.5) / W
        low = np.zeros(W)
        for k in range(1, 5):
            low += frng.normal() / k * np.sin(2 * math.pi * (k + 1) * uu0 + frng.uniform(0, 2 * math.pi))
        # and strand by strand: a value per strand's pitch, eased between strands and blurred over three,
        # so the edge is uneven at the scale of a few hairs, not a row of scallops
        cells = frng.uniform(0.0, 1.0, n)
        cells = (np.roll(cells, 1) + 2 * cells + np.roll(cells, -1)) / 4
        pos = uu0 * n - 0.5
        i0 = np.floor(pos).astype(int)
        fr = _smooth(0.0, 1.0, pos - i0)
        high = cells[i0 % n] * (1 - fr) + cells[(i0 + 1) % n] * fr
        norm = lambda a: (a - a.min()) / max(float(a.max() - a.min()), 1e-9)
        wob = 0.35 * norm(low) + 0.65 * norm(high)
        body_start = r1 + ragged * wob                               # (W,)
    else:
        frng = None
        body_start = np.full(W, float(r1))

    cover = np.zeros((H, W))                                        # strand coverage, 0..1
    shade = np.full((H, W), p["gap_mult"])                          # brightness of what shows there
    pitch = W / n
    for j in range(n):
        cx = (j + 0.5 + rng.uniform(-0.3, 0.3)) * pitch
        half = pitch * rng.uniform(0.45, 0.75)
        bright = (1 + p["strand_jitter"] * rng.normal()) * clump[int(j * nc / n) % nc]
        root = rng.uniform(r0, r1)
        tip = rng.uniform(t0, t1)
        freq, phase = rng.uniform(1.0, 3.0), rng.uniform(0, 2 * math.pi)
        if ragged > 0 or rpow != 1.0:
            start = float(body_start[int(cx) % W])
            root = r0 + (start - r0) * ((root - r0) / max(r1 - r0, 1e-9)) ** rpow
        centre = cx + p["wave_px"] * np.sin(2 * math.pi * (v * freq) + phase)     # (H,)
        # thinner near its own ends
        rw = p.get("root_width", 0.35)
        width = half * (rw + (1 - rw) * _smooth(root, root + 0.03, v) * (1 - _smooth(tip - 0.04, tip, v)))
        alive = (v > root) & (v < tip)
        lo = int(math.floor(cx - half - p["wave_px"] - 1))
        hi = int(math.ceil(cx + half + p["wave_px"] + 1))
        cols = np.arange(lo, hi)
        wrapped = cols % W
        dx = np.abs(x[wrapped][None, :] - centre[:, None])
        dx = np.minimum(dx, W - dx)
        c = np.clip(1 - dx / np.maximum(width[:, None], 1e-6), 0, 1) * alive[:, None]
        prof = np.sqrt(c)
        better = prof > cover[:, wrapped]
        cover[:, wrapped] = np.where(better, prof, cover[:, wrapped])
        shade[:, wrapped] = np.where(better, (p["gap_mult"] + (1 - p["gap_mult"]) * prof) * bright,
                                     shade[:, wrapped])

    # a shell has an opaque middle between the thinned roots and tips (it hides the scalp); a card has none -
    # its strands with gaps between them all the way along, so a card over skin shows skin between the hairs
    # fine hairs (`fine_per_tile`, off at the defaults): short, thin and lighter, rooted over the root zone
    # before the opaque middle starts - the vellus a real hairline fades out through
    for j in range(int(p.get("fine_per_tile", 0))):
        cx = frng.uniform(0, W) if frng is not None else rng.uniform(0, W)
        g = frng if frng is not None else rng
        start = float(body_start[int(cx) % W])
        root = g.uniform(r0, start)
        tip = min(root + g.uniform(0.015, 0.05), start + 0.02)
        half = pitch * g.uniform(0.2, 0.35)
        lean = g.normal(0.0, 1.5)
        centre = cx + lean * _smooth(root, tip, v)
        alive = (v > root) & (v < tip)
        width = half * (1 - 0.6 * _smooth(root, tip, v))
        lo, hi = int(math.floor(cx - 4)), int(math.ceil(cx + 4))
        cols = np.arange(lo, hi)
        wrapped = cols % W
        dx = np.abs(x[wrapped][None, :] - centre[:, None])
        dx = np.minimum(dx, W - dx)
        c = np.clip(1 - dx / np.maximum(width[:, None], 1e-6), 0, 1) * alive[:, None] * 0.75
        better = c > cover[:, wrapped]
        cover[:, wrapped] = np.where(better, c, cover[:, wrapped])
        shade[:, wrapped] = np.where(better, (p["gap_mult"] + (1 - p["gap_mult"]) * c) * 1.2, shade[:, wrapped])

    # edge hairs (`edge_hairs` per tile, off at the defaults): short, thin hairs scattered in front of the dense
    # start, more of them the nearer it is (`edge_power`), each leaning its own way off a slowly turning
    # direction (`edge_lean`, texels of lean over its length), so the hairline is a thinning scatter of hairs
    # rather than a comb of parallel spikes. Their own random stream, so nothing else moves.
    ne = int(p.get("edge_hairs", 0))
    if ne > 0 and p.get("mode", "shell") != "card":
        erng = np.random.RandomState(seed + 15485)
        depth = float(p.get("edge_depth", 0.05))
        epow = float(p.get("edge_power", 2.0))
        elean = float(p.get("edge_lean", 6.0))
        l0, l1 = p.get("edge_len", [0.01, 0.03])
        dir_ph = erng.uniform(0, 2 * math.pi, 3)
        deep_ph = erng.uniform(0, 2 * math.pi, 3)
        for j in range(ne):
            cx = erng.uniform(0, W)
            start = float(body_start[int(cx) % W])
            u = erng.uniform(0.0, 1.0) ** epow                      # 0 at the dense start, 1 at `edge_depth`
            # how deep the scatter reaches wanders too (0.4..1.6 x), so its front is not a second ruled line
            deep = 1 + 0.6 * sum(math.sin(2 * math.pi * (k + 2) * cx / W + deep_ph[k]) / (k + 1) for k in range(3)) / 1.83
            root = max(start - depth * deep * u, r0)
            tip = root + erng.uniform(l0, l1)
            field = sum(math.sin(2 * math.pi * (k + 1) * cx / W + dir_ph[k]) / (k + 1) for k in range(3))
            lean = elean * (0.6 * field + erng.normal(0.0, 0.6))
            half = pitch * erng.uniform(*p.get("edge_width", [0.3, 0.55]))
            shade_j = 1 + p.get("edge_tone", 0.0) * u               # lighter toward the front: finer hairs
            tt = _smooth(root, tip, v)
            centre = cx + lean * (1 - tt)                           # leans off at its root end, into the line
            alive = (v > root) & (v < tip)
            width = half * (0.4 + 0.6 * _smooth(root, root + 0.4 * (tip - root), v)) * (1 - 0.5 * tt)
            reach = int(abs(lean)) + 3
            cols = np.arange(int(cx) - reach, int(cx) + reach + 1)
            wrapped = cols % W
            dx = np.abs(x[wrapped][None, :] - centre[:, None])
            dx = np.minimum(dx, W - dx)
            c = np.sqrt(np.clip(1 - dx / np.maximum(width[:, None], 1e-6), 0, 1)) * alive[:, None]
            better = c > cover[:, wrapped]
            cover[:, wrapped] = np.where(better, c, cover[:, wrapped])
            shade[:, wrapped] = np.where(better, (p["gap_mult"] + (1 - p["gap_mult"]) * c) * shade_j,
                                         shade[:, wrapped])

    if p.get("mode", "shell") == "card":
        body = np.zeros((H, 1))
    elif ragged > 0:
        body = _smooth(0.0, 1.0, (v[:, None] - body_start[None, :] + 0.02) / 0.03)             * (1 - _smooth(t0 - 0.005, t0 + 0.01, v))[:, None]
    else:
        body = (_smooth(r1 - 0.01, r1 + 0.005, v) * (1 - _smooth(t0 - 0.005, t0 + 0.01, v)))[:, None]   # opaque middle
    alpha = np.maximum(body, cover)
    # toward the root, coverage fades rather than stopping: Blender and glTF's MASK cut it at 0.5, so strands
    # thin out toward the hairline; Godot's depth pre-pass blends the rest, so the hairline is a soft fade
    f0, f1 = p.get("root_fade", [r0, r0])
    alpha = alpha * np.power(_smooth(f0, f1, v), p.get("root_fade_power", 0.5))[:, None]
    alpha[(v < r0 * 0.5) | (v > 0.5 * (t1 + 1))] = 0.0
    lin = base[None, None, :] * (tone[:, None] * shade * lock)[:, :, None]
    out = np.empty((H, W, 4))
    out[:, :, :3] = _linear_to_srgb(lin)
    out[:, :, 3] = alpha
    # normals: each strand a rounded ridge across U, locks a broad wave
    height = cover + 0.5 * (lock - 1) / max(p.get("lock_jitter", 0.0), 1e-6) * 0.15
    slope = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5 * p.get("normal_strength", 1.0)
    nrm = np.stack([-slope, np.zeros_like(slope), np.ones_like(slope)], axis=2)
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    normal = np.empty((H, W, 4))
    normal[:, :, :3] = nrm * 0.5 + 0.5
    normal[:, :, 3] = 1.0
    return out, normal


def material(name, colour, preset_name="hair", seed=0, uv_map=None, pixels=None, **overrides):
    """A Principled hair material, reused and rebuilt by name. `colour` is the hair's mid-length screen
    (sRGB) colour; the texture darkens it toward the roots and lightens it toward the tips.

    `pixels` is (colour, normal) as `strand_texture` returns them - (H, W, 4) arrays, rows bottom-up, colour
    sRGB with straight alpha - for a caller that draws its own hairs (humanform's brow and lash cards, its
    sparse body hair). They become the material's images in place of the preset's strands, so a caller never
    has to overwrite the pixels of an image this function made (the report's `pixels` says whose they are).

    Returns (material, report). The report says what glTF will carry and what Godot must re-apply."""
    p = preset(preset_name, **overrides)
    lin = tuple(_srgb_to_linear(c) for c in colour[:3])
    W, H = p["texture_px"]
    img_name = f"{name}_strands"
    old = bpy.data.images.get(img_name)
    if old is not None:
        bpy.data.images.remove(old)
    if pixels is not None:
        colour_px, normal_px = (np.asarray(a, np.float64) for a in pixels)
        if colour_px.shape[2] != 4 or normal_px.shape != colour_px.shape:
            raise ValueError(f"pixels must be two (H, W, 4) arrays of one size, got {colour_px.shape} and {normal_px.shape}")
        H, W = colour_px.shape[:2]
    else:
        colour_px, normal_px = strand_texture(lin, p, seed=seed)
    img = bpy.data.images.new(img_name, W, H, alpha=True)
    img.colorspace_settings.name = "sRGB"
    img.alpha_mode = "STRAIGHT"
    img.pixels.foreach_set(colour_px.astype(np.float32).ravel())
    img.pack()
    nrm_name = f"{name}_strands_normal"
    old = bpy.data.images.get(nrm_name)
    if old is not None:
        bpy.data.images.remove(old)
    nimg = bpy.data.images.new(nrm_name, W, H, alpha=False)
    nimg.colorspace_settings.name = "Non-Color"
    nimg.pixels.foreach_set(normal_px.astype(np.float32).ravel())
    nimg.pack()

    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.extension = "REPEAT"
    tex.interpolation = "Linear"
    uv = nt.nodes.new("ShaderNodeUVMap")
    if uv_map:
        uv.uv_map = uv_map
    rnd = nt.nodes.new("ShaderNodeMath")
    rnd.operation = "ROUND"                         # the exporter's sign for alphaMode MASK
    tan = nt.nodes.new("ShaderNodeTangent")
    tan.direction_type = "UV_MAP"
    if uv_map:
        tan.uv_map = uv_map
    nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], rnd.inputs[0])
    nt.links.new(rnd.outputs[0], bsdf.inputs["Alpha"])
    nt.links.new(tan.outputs["Tangent"], bsdf.inputs["Tangent"])
    ntex = nt.nodes.new("ShaderNodeTexImage")
    ntex.image = nimg
    ntex.extension = "REPEAT"
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nmap.space = "TANGENT"
    if uv_map:
        nmap.uv_map = uv_map
    nmap.inputs["Strength"].default_value = 1.0
    nt.links.new(uv.outputs["UV"], ntex.inputs["Vector"])
    nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    ntex.location, nmap.location = (-650, -300), (-400, -300)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = p["roughness"]
    if "Specular IOR Level" in bsdf.inputs and "specular" in p:
        bsdf.inputs["Specular IOR Level"].default_value = p["specular"]
    for sock, key in (("Anisotropic", "anisotropic"), ("Anisotropic Rotation", "anisotropic_rotation")):
        if sock in bsdf.inputs:
            bsdf.inputs[sock].default_value = p[key]
    for i, node in enumerate((uv, tex, rnd, tan, bsdf, out)):
        node.location = (-900 + 250 * i, 0)
    mat.diffuse_color = (*lin, 1.0)
    mat.use_backface_culling = True
    for attr, value in (("surface_render_method", "DITHERED"), ("blend_method", "CLIP")):
        try:
            setattr(mat, attr, value)
        except (AttributeError, TypeError):
            pass

    g = dict(p["godot"])
    share = g.pop("backlight_share", None)
    if share is not None:
        g["backlight"] = [round(c * share, 4) for c in lin] + [1.0]
    mat["lookdev"] = {"preset": preset_name, "godot": g}
    if p.get("mesh"):
        mat["lookdev"]["mesh"] = dict(p["mesh"])
    if p.get("alpha"):
        mat["lookdev"]["alpha"] = dict(p["alpha"])
    report = {"material": mat.name, "image": img.name, "texture_px": [W, H], "tile_m": p["tile_m"],
              "colour_linear": [round(c, 4) for c in lin], "gltf": {"alphaMode": "MASK", "alphaCutoff": 0.5,
              "baseColorTexture": img.name,
              "normalTexture": nimg.name}, "godot_extras": g, "mesh_extras": p.get("mesh"),
              "alpha_extras": p.get("alpha"), "mode": p.get("mode", "shell"),
              "pixels": "caller" if pixels is not None else "preset"}
    return mat, report
