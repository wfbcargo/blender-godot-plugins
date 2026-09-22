"""The fixed contact sheet a critic judges a body from.

    res = views.contact_sheet("Nora", out_dir, preset="realistic", report=rep)
    res["sheets"]   # [body.png, closeups.png]

body.png - rows: clay (form), normals (surface flow and lumps), silhouette (proportion and
gesture); columns: front, front_left, left, back. Orthographic, the same scale in every tile, so
heights compare across views and across versions. Overlays on the clay and silhouette rows:
  orange dashes - the preset's target heights (chin, shoulder joint, hip joint, crotch, knee)
  cyan ticks    - the same landmarks as measured (left edge of each tile)
closeups.png - clay: face front, face left, left hand from its back, left foot from above and in front
(hand and foot clipped to themselves).
hair.png - when the body has hair (joined, or a hair object): the head lit and in colour, front, three-quarter
and back at 1 m, then close three-quarter, side and back (`hair_sheet`).

View names say which side of the body the camera sees: `left` is the body's left, +X.
Rendered with Workbench in a private scene in the rig's rest pose; the user's scene is untouched.
"""

from __future__ import annotations

import json
import os
import re

import bpy
import numpy as np
from mathutils import Vector

from . import body as _body

AUTO_INCLUDE = ("hair", "eye", "brow", "lash", "teeth", "tongue", "headparts")
TARGET_KEYS = (("chin", "chin_z"), ("shoulder_joint", "shoulder_z"), ("hip_joint", "hip_z"),
               ("crotch", "crotch_z"), ("knee_joint", "knee_z"))
ORANGE = (1.0, 0.55, 0.1, 1.0)
CYAN = (0.1, 0.85, 1.0, 1.0)
FRAME_HEIGHT_M = 2.0
FRAME_WIDTH_M = 1.4


def _dirs(fwd):
    left = Vector((1, 0, 0))
    return {"front": fwd, "back": -fwd, "left": left, "right": -left,
            "front_left": (fwd + left).normalized(), "front_right": (fwd - left).normalized()}


def _matcap(name_hint):
    caps = [l.name for l in bpy.context.preferences.studio_lights if l.type == "MATCAP"]
    for c in caps:
        if name_hint in c:
            return c
    return caps[0] if caps else None


def _render_tile(sc, cam, centre, direction, scale, w, h, path, clip=None):
    """`clip`: render only what lies within this distance of `centre` along the view - a hand in front
    of the thigh, a foot under the belly."""
    cam.data.ortho_scale = scale
    cam.data.clip_start, cam.data.clip_end = (10.0 - clip, 10.0 + clip) if clip else (0.1, 40.0)
    cam.data.sensor_fit = "VERTICAL" if h >= w else "HORIZONTAL"
    pos = centre + direction * 10.0
    cam.location = pos
    cam.rotation_euler = (centre - pos).to_track_quat("-Z", "Y").to_euler()
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.filepath = path
    with bpy.context.temp_override(scene=sc):
        bpy.ops.render.render(write_still=True, scene=sc.name)
    img = bpy.data.images.load(path, check_existing=False)
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)


def _hline(tile, row, colour, x0=0.0, x1=1.0, dash=0, thick=2):
    h, w = tile.shape[:2]
    r = int(round(row))
    if r < 0 or r >= h:
        return
    a, b = int(x0 * w), int(x1 * w)
    for rr in range(max(0, r - thick // 2), min(h, r + (thick + 1) // 2)):
        if dash:
            for x in range(a, b, dash * 2):
                tile[rr, x:min(b, x + dash)] = colour
        else:
            tile[rr, a:b] = colour


def _stitch(rows, gap=4, bg=(0.12, 0.12, 0.13, 1.0)):
    th, tw = rows[0][0].shape[:2]
    nr, nc = len(rows), max(len(r) for r in rows)
    H, W = nr * th + (nr - 1) * gap, nc * tw + (nc - 1) * gap
    out = np.empty((H, W, 4), np.float32)
    out[:] = bg
    for i, row in enumerate(rows):
        y = H - (i + 1) * th - i * gap          # images are stored bottom-up: row 0 on top
        for j, t in enumerate(row):
            x = j * (tw + gap)
            out[y:y + th, x:x + tw] = t
    return out


def _save(arr, path):
    h, w = arr.shape[:2]
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
    img.pixels.foreach_set(arr.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def contact_sheet(ob, out_dir, preset="realistic", sex=None, include=(), report=None, tile=(400, 800),
                  views=("front", "front_left", "left", "back")):
    import humanform as pkg  # noqa: WPS433

    b = _body.load(ob)
    rig = b.rig
    os.makedirs(os.path.join(out_dir, "tiles"), exist_ok=True)
    m = report["measurements"] if report else None
    floor, top = b.floor, b.top
    H = top - floor
    fwd = Vector(m["forward"]) if m else Vector((0, -1, 0))
    dirs = _dirs(fwd)

    extra = [_body.obj(o) for o in include]
    if not include and rig is not None:
        extra = [o for o in bpy.data.objects if o.type == "MESH" and o is not b.ob and _body.rig_of(o) is rig
                 and any(k in o.name.lower() for k in AUTO_INCLUDE)]

    sc = bpy.data.scenes.new("HumanformViews")
    prev_pose = rig.data.pose_position if rig else None
    world = bpy.data.worlds.new("HumanformWorld")
    cam = bpy.data.objects.new("HumanformCam", bpy.data.cameras.new("HumanformCam"))
    files = []
    try:
        for o in [b.ob] + extra + ([rig] if rig else []):
            sc.collection.objects.link(o)
        sc.collection.objects.link(cam)
        sc.camera = cam
        cam.data.type = "ORTHO"
        cam.data.clip_end = 40.0
        sc.world = world
        sc.render.engine = "BLENDER_WORKBENCH"
        sc.render.film_transparent = False
        sc.render.resolution_percentage = 100
        try:
            sc.view_settings.view_transform = "Standard"
        except TypeError:
            pass
        sh = sc.display.shading
        if rig:
            rig.data.pose_position = "REST"

        def mode(name):
            sh.show_cavity = False
            sh.show_object_outline = False
            if name == "clay":
                sh.light = "MATCAP"
                sh.studio_light = _matcap("basic_1")
                sh.color_type = "SINGLE"
                sh.single_color = (0.8, 0.8, 0.8)
                sh.show_cavity = True
                sh.cavity_type = "BOTH"
                world.color = (0.28, 0.29, 0.31)
            elif name == "normals":
                sh.light = "MATCAP"
                sh.studio_light = _matcap("check_normal")
                sh.color_type = "SINGLE"
                sh.single_color = (1.0, 1.0, 1.0)
                world.color = (0.2, 0.2, 0.2)
            else:
                sh.light = "FLAT"
                sh.color_type = "SINGLE"
                sh.single_color = (0.0, 0.0, 0.0)
                world.color = (1.0, 1.0, 1.0)

        # A fixed frame - 2.0 m tall, 1.4 m wide - so sheets of different versions and different
        # bodies compare tile for tile. Grown (and recorded in views.json) only when a body
        # does not fit, since then the two sheets differ in scale.
        th = tile[1]
        span = max(float(np.ptp(b.co[:, 0])), float(np.ptp(b.co[:, 1])))
        scale = max(FRAME_HEIGHT_M, H * 1.08)
        width_m = max(FRAME_WIDTH_M, span * 1.06)
        tw = int(np.ceil(th * width_m / scale / 2)) * 2
        centre = Vector((0.0, 0.0, scale / 2 - 0.02))
        targets = pkg.presets()["presets"][preset]["ratios"]

        def overlay(t):
            def row(z):
                return (z - (centre.z - scale / 2)) / scale * th
            for key, mkey in TARGET_KEYS:
                entry = targets.get(key, {})
                tgt = entry.get("any") or (entry.get(sex) if sex else None)
                if tgt:
                    _hline(t, row(floor + tgt[0] * H), ORANGE, dash=6)
                if m and m.get(mkey) is not None:
                    _hline(t, row(floor + m[mkey]), CYAN, 0.0, 0.14, thick=3)

        rows = []
        for mname in ("clay", "normals", "silhouette"):
            mode(mname)
            row_tiles = []
            for v in views:
                path = os.path.join(out_dir, "tiles", f"{mname}_{v}.png")
                t = _render_tile(sc, cam, centre, dirs[v], scale, tw, th, path)
                if mname != "normals":
                    overlay(t)
                row_tiles.append(t)
            rows.append(row_tiles)
        sheet = os.path.join(out_dir, "body.png")
        _save(_stitch(rows), sheet)
        files.append(sheet)

        # close-ups: material colour, so eyes (sclera, iris, pupil) read against the clay skin
        mode("clay")
        sh.color_type = "MATERIAL"
        cs = 600
        close = []
        chin = floor + (m["chin_z"] if m and m.get("chin_z") else 0.87 * H)
        head_c = Vector((0.0, 0.0, (chin + top) / 2))
        face_y = b.co[b.co[:, 2] > chin][:, 1]
        head_c.y = float((face_y.min() + face_y.max()) / 2) if len(face_y) else 0.0
        hs = (top - chin) * 1.5
        close.append(_render_tile(sc, cam, head_c, dirs["front"], hs, cs, cs, os.path.join(out_dir, "tiles", "face_front.png")))
        close.append(_render_tile(sc, cam, head_c, dirs["left"], hs, cs, cs, os.path.join(out_dir, "tiles", "face_left.png")))
        # hand from its back and foot from above-front, clipped to themselves (the thigh used to hide
        # the hand's palm side and the shin the instep)
        for region, label, fname in (("hands", "back", "hand_back.png"), ("feet", "above", "foot_above.png")):
            try:
                fr = next(f for f in region_frames(b, region, m) if f[0] == label)
            except (ValueError, StopIteration):
                continue
            _, c, d, s_, clip = fr
            close.append(_render_tile(sc, cam, c, d, s_ * 1.2, cs, cs, os.path.join(out_dir, "tiles", fname),
                                      clip=clip))
        grid = [close[:2], close[2:4]] if len(close) > 2 else [close]
        if len(grid) > 1 and len(grid[1]) < 2:
            grid[1].append(np.zeros_like(close[0]))
        sheet = os.path.join(out_dir, "closeups.png")
        _save(_stitch(grid), sheet)
        files.append(sheet)
        frame = {"frame_height_m": scale, "frame_width_m": width_m, "floor_z": floor, "tile_px": [tw, th],
                 "standard_frame": scale == FRAME_HEIGHT_M and width_m == FRAME_WIDTH_M,
                 "views": list(views), "rows": ["clay", "normals", "silhouette"], "preset": preset}
        with open(os.path.join(out_dir, "views.json"), "w", encoding="utf-8") as fh:
            json.dump(frame, fh, indent=1)
    finally:
        if rig:
            rig.data.pose_position = prev_pose
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.scenes.remove(sc)
        bpy.data.worlds.remove(world)
    hair = hair_objects(b.ob, extra)
    if hair:
        files.append(hair_sheet(b.ob, out_dir, include=[o for o in extra if o not in hair] + hair)["sheet"])
    return {"sheets": files, "extra": [o.name for o in extra]}


# ------------------------------------------------------------------------------------------ hair

HAIR_SHOTS = (("front", 0.0, 1.0, 0.0), ("three_quarter", 45.0, 1.0, 0.0), ("back", 180.0, 1.0, 0.0),
              ("close", 35.0, 0.42, 0.02), ("close_side", 95.0, 0.32, 0.0), ("close_back", 150.0, 0.42, 0.04))


def _hair_material(mat):
    """A material that is hair: lookdev's `hair` preset, or `hair` as a whole part of its name.

    A part, not a substring. A character called HairWoman has a `HairWoman_skin` material, and
    `"hair" in name.lower()` called her skin hair - which made character-pipeline's new "is there hair
    already" check refuse her first hair stage. The name test is only there for the deprecated shell_bun
    material (`<name>_hair`), which carries no `lookdev` property."""
    if mat is None:
        return False
    lookdev = mat.get("lookdev")
    if bool(lookdev) and lookdev.get("preset") == "hair":
        return True
    return "hair" in re.split(r"[^a-z0-9]+", mat.name.lower())


def hair_objects(body, extra=()):
    """Meshes that are hair: humanform's hair objects, or `body` itself when hair was joined into it (a hair
    material on one of its slots)."""
    out = [o for o in extra if o.get("humanform_hair") is not None or any(_hair_material(m) for m in o.data.materials)]
    if any(_hair_material(m) for m in body.data.materials):
        out.append(body)
    return out


def hair_sheet(ob, out_dir, include=(), size=520, engine=None):
    """hair.png: the head lit, in colour, at the distances hair is judged from - front, three-quarter and back
    at 1 m, and close three-quarter, side and back - with a 50 mm lens, a warm key from the front left and a
    cool rim from behind. Material colour, not clay: a hairline reads as hair or as a cap edge only with its
    strand texture and alpha. Rendered in a private scene in the rig's rest pose, with EEVEE unless `engine`."""
    import math
    b = _body.load(ob)
    rig = b.rig
    top = b.top
    head_pts = b.co[b.co[:, 2] > top - 0.25]
    cy = float((head_pts[:, 1].min() + head_pts[:, 1].max()) / 2) if len(head_pts) else 0.0
    target0 = Vector((0.0, cy, top - 0.1))
    tiles_dir = os.path.join(out_dir, "tiles")
    os.makedirs(tiles_dir, exist_ok=True)
    sc = bpy.data.scenes.new("HumanformHair")
    world = bpy.data.worlds.new("HumanformHairWorld")
    cam = bpy.data.objects.new("HumanformHairCam", bpy.data.cameras.new("HumanformHairCam"))
    lights = []
    prev_pose = rig.data.pose_position if rig else None
    tiles = []
    try:
        for o in {id(x): x for x in [b.ob, *[_body.obj(i) for i in include]] + ([rig] if rig else [])}.values():
            sc.collection.objects.link(o)
        sc.collection.objects.link(cam)
        sc.camera = cam
        cam.data.lens = 50
        for name, energy, rot, colour in (("Key", 3.5, (55, 0, -35), (1.0, 0.96, 0.9)),
                                          ("Rim", 2.5, (-60, 0, 20), (0.9, 0.95, 1.0))):
            data = bpy.data.lights.new(f"HumanformHair{name}", "SUN")
            data.energy, data.color = energy, colour
            lo = bpy.data.objects.new(data.name, data)
            lo.rotation_euler = [math.radians(a) for a in rot]
            sc.collection.objects.link(lo)
            lights.append(lo)
        world.use_nodes = True
        bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
        bg.inputs["Color"].default_value = (0.32, 0.34, 0.37, 1.0)
        bg.inputs["Strength"].default_value = 0.6
        sc.world = world
        for candidate in ([engine] if engine else ["BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"]):
            try:
                sc.render.engine = candidate
                break
            except TypeError:
                continue
        sc.render.resolution_x = sc.render.resolution_y = size
        sc.render.resolution_percentage = 100
        try:
            sc.view_settings.view_transform = "AgX"
        except TypeError:
            pass
        if rig:
            rig.data.pose_position = "REST"
        for label, az, dist, dz in HAIR_SHOTS:
            a = math.radians(az)
            target = target0 + Vector((0.0, 0.0, dz))
            cam.location = target + Vector((math.sin(a), -math.cos(a), 0.12)).normalized() * dist
            cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
            path = os.path.join(tiles_dir, f"hair_{label}.png")
            sc.render.filepath = path
            with bpy.context.temp_override(scene=sc):
                bpy.ops.render.render(write_still=True, scene=sc.name)
            img = bpy.data.images.load(path, check_existing=False)
            px = np.empty(size * size * 4, np.float32)
            img.pixels.foreach_get(px)
            bpy.data.images.remove(img)
            tiles.append(px.reshape(size, size, 4))
        sheet = os.path.join(out_dir, "hair.png")
        _save(_stitch([tiles[:3], tiles[3:]]), sheet)
    finally:
        if rig:
            rig.data.pose_position = prev_pose
        for lo in lights:
            data = lo.data
            bpy.data.objects.remove(lo, do_unlink=True)
            bpy.data.lights.remove(data)
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.scenes.remove(sc)
        bpy.data.worlds.remove(world)
    return {"sheet": sheet, "shots": [s[0] for s in HAIR_SHOTS]}


def region_frames(b, region, m=None):
    """[(label, centre, view direction, ortho scale, clip)] framing one region of a body: the face from
    the front and left; the left hand from its back and from the front (thumb profile); the left foot
    from above, its outer side and the front. Hands and feet are clipped to themselves."""
    from . import measure

    m = m or measure.measurements(b, fast=True)
    floor, top = b.floor, b.top
    dirs = _dirs(Vector(m["forward"]))
    if region == "face":
        chin = floor + (m.get("chin_z") or 0.87 * (top - floor))
        centre = Vector((0.0, 0.0, (chin + top) / 2 - 0.01))
        ys = b.co[b.co[:, 2] > chin][:, 1]
        centre.y = float((ys.min() + ys.max()) / 2) if len(ys) else 0.0
        scale = (top - chin) * 1.35
        return [(v, centre, dirs[v], scale, None) for v in ("front", "left")]
    if region == "hands":
        fr = measure.hand_frame(b, "L")
        if fr is None:
            raise ValueError("no left hand to frame (no wrist and elbow landmarks)")
        w, a, across, back, length = fr
        centre = w + a * (0.55 * length)
        side = (dirs["front"] - a * dirs["front"].dot(a)).normalized()
        return [("back", centre, back, 1.4 * length, 0.6 * length),
                ("front", centre, side, 1.4 * length, 0.6 * length)]
    if region == "feet":
        ank = b.mark("ankle.L")
        if ank is None:
            raise ValueError("no left ankle to frame")
        H = top - floor
        sel = (b.co[:, 2] < ank.z) & (np.abs(b.co[:, 0] - ank.x) < 0.07 * H)
        pts = b.co[sel]
        az = ank.z - floor
        centre = Vector(((pts[:, 0].min() + pts[:, 0].max()) / 2, (pts[:, 1].min() + pts[:, 1].max()) / 2,
                         floor + 0.4 * az))
        length = float(max(np.ptp(pts[:, 1]), np.ptp(pts[:, 0])))
        # from above and in front (straight down, the shin hides the foot, and clipping the shin away
        # leaves a cut face over the instep); from the front, framed tighter and lower, since a foot is a
        # third as wide as it is long. The clips keep the other leg and the belly out.
        low = centre.copy()
        low.z = floor + 0.8 * az
        above = (dirs["front"] * 0.6 + Vector((0.0, 0.0, 1.0))).normalized()
        return [("above", centre, above, 1.1 * length, 0.2),
                ("outer", low, dirs["left"], 1.1 * length, 0.12),
                ("front", low, dirs["front"], 0.6 * length, 0.2)]
    raise ValueError(f"variant_grid frames face, hands and feet, not {region!r}")


def variant_grid(ob, out_png, variants, apply, region="face", tile=300, views=None, per_row=3):
    """One image of many designs on the same body, for a single critic call. Each design is a panel of
    views of the region in clay (see `region_frames`; `views` picks some by label); panels run left to
    right, top to bottom, `per_row` to a row, in the order of `variants`, with a wide gap between
    panels. `apply(variant)` puts a design on the body. The frame is fixed from the body as it is when
    called, so designs compare at one scale."""
    b = _body.load(ob)
    rig = b.rig
    frames = [f for f in region_frames(b, region) if views is None or f[0] in views]
    extra = [o for o in bpy.data.objects if o.type == "MESH" and o is not b.ob and rig is not None
             and _body.rig_of(o) is rig and any(k in o.name.lower() for k in AUTO_INCLUDE)]
    sc = bpy.data.scenes.new("HumanformVariants")
    world = bpy.data.worlds.new("HumanformVariantsWorld")
    cam = bpy.data.objects.new("HumanformVariantsCam", bpy.data.cameras.new("HumanformVariantsCam"))
    prev_pose = rig.data.pose_position if rig else None
    rows = []
    tmp = os.path.join(os.path.dirname(out_png), "tiles_variants")
    os.makedirs(tmp, exist_ok=True)
    try:
        for o in [b.ob] + extra + ([rig] if rig else []):
            sc.collection.objects.link(o)
        sc.collection.objects.link(cam)
        sc.camera = cam
        cam.data.type = "ORTHO"
        cam.data.clip_end = 40.0
        sc.world = world
        world.color = (0.28, 0.29, 0.31)
        sc.render.engine = "BLENDER_WORKBENCH"
        sc.render.resolution_percentage = 100
        try:
            sc.view_settings.view_transform = "Standard"
        except TypeError:
            pass
        sh = sc.display.shading
        sh.light, sh.studio_light = "MATCAP", _matcap("basic_1")
        sh.color_type, sh.single_color = "MATERIAL", (0.8, 0.8, 0.8)     # eyes keep their colours
        sh.show_cavity, sh.cavity_type = True, "BOTH"
        if rig:
            rig.data.pose_position = "REST"
        for i, variant in enumerate(variants):
            apply(variant)
            bpy.context.view_layer.update()
            rows.append(_stitch([[_render_tile(sc, cam, centre, d, scale, tile, tile,
                                               os.path.join(tmp, f"{i:02d}_{label}.png"), clip=clip)
                                  for label, centre, d, scale, clip in frames]], gap=2))
        blank = np.zeros_like(rows[0])
        blank[:] = (0.12, 0.12, 0.13, 1.0)
        grid = [rows[i:i + per_row] for i in range(0, len(rows), per_row)]
        grid[-1] += [blank] * (per_row - len(grid[-1]))
        _save(_stitch(grid, gap=24), out_png)
    finally:
        if rig:
            rig.data.pose_position = prev_pose
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.scenes.remove(sc)
        bpy.data.worlds.remove(world)
    return out_png
