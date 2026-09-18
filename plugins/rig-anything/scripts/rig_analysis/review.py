"""Review sheets: every clip as strips of evenly spaced frames, at one scale for every body.

    from rig_analysis import review
    r = review.sheet(["Walter_body"], "Walter_rig", ["Walter_Walk", "Walter_Run"], "C:/.../review/walter",
                     loops=["Walter_Walk", "Walter_Run"])

A clip can pass every numeric check and still look wrong: Walter's arms reached forward with near-straight
elbows, Tomas' run hand sat at his neck, and floor, slide, balance and clearance all passed until someone
looked at eight frames side by side (improvements 04 b). So `export.export` writes this sheet itself - with
no extra call - and the character pipeline's `review` stage writes it for the dressed character.

For each clip and view there is one strip, `<out_dir>/<clip>_<view>.png`: `frames` (8) evenly spaced frames
side by side, workbench-lit, with the clip, view and frame numbers written above and the floor drawn as a
line. Garments and hair bound to the rig are drawn in their own colours. A flat body (a sea star) is seen
three-quarter from above rather than level. `contact.png` is every strip at half size, a row per clip and a column per view, and `review.json`
says what is where. The folder above `out_dir` gets a `.gdignore`, so Godot does not import the images.

**One scale.** Every cell is `frame_height_m` tall from just under the floor up (grown only if a body needs
more), so a child renders smaller than a man and characters line up. `frame_height_m=None` picks it: an
upright body (taller than twice its depth along `forward`) gets `HUMAN_FRAME_M`, 2.1 m, like every person;
anything else gets the smallest rung of `CREATURE_FRAMES_M` holding its size, so a dog and a wolf share a
scale while a cricket does not render as a speck.

**Fast.** A strip is one render, not eight: the eight frozen frames stand side by side along the camera's
right axis, which an orthographic camera shows without any of them overlapping. A clip costs three renders
and eight evaluations of the rig.

**What is measured** (from the pixels, per strip): `cells_with_body` - cells where anything but background,
floor line or label was drawn, so a strip that lost its body says so - and `distinct_cells`, how many of the
cells show different poses, so a clip rendering one frozen pose eight times (the stale-pose bug
`views.render_clip` documents) reports 1 - and `edge_cells`, cells whose body touches any edge of the strip,
left, right, bottom or top, so a pose spilling into its neighbour's cell or cut off by the frame says so.
Cells are compared with a tolerance (`PIXEL_DIFF`, `SAME_PIXELS`) on an undithered render: Blender's default
dither alone made every cell of a frozen pose differ.

**Travel.** Every clip is evaluated before anything renders. The cell width holds the widest pose drawn,
and a strip whose poses would leave their cells - a cricket's launch stretches and rises out of its
cell into the next - is drawn centred: each frame moved along the view's right axis so its own extent is
centred in its cell, the cell widened to the widest pose, and `(each frame centred)` in the heading. Where
a body stands relative to its neighbours is then not in the picture; each pose is, on its own.

**Spill up and down.** The frame is the rest body's, and a pose leaves it in every direction, not only
sideways: a rabbit's JumpAir legs go through the floor, a launch rises above the standing head. The bands
above and below the cell are grown from the evaluated poses too (`bands_px` [label, above, below]), in whole
pixels at the same metres-per-pixel, so the shared scale, the cell and the floor line do not move - the
picture is simply taller, with the rest ground band left over as the margin. Before that, a fixed 4% ground
band cut the rabbit's and the cricket's JumpAir legs off at row 0 while `edge_cells`, which looked only at
the side columns, reported 0: the sheet cropped the evidence and called itself clean.
"""

from __future__ import annotations

import json
import math
import os
import time

import bpy
from mathutils import Matrix, Vector

REVIEW_VIEWS = ("front", "right", "three_quarter")
# camera direction FROM, for a body facing -Y (Blender's front); rotated to the body's `forward`
VIEW_DIRS = {"front": (0.0, -1.0, 0.0), "right": (1.0, 0.0, 0.0), "three_quarter": (1.0, -1.0, 0.0),
             "back": (0.0, 1.0, 0.0), "left": (-1.0, 0.0, 0.0),
             "three_quarter_above": (1.0, -1.0, 1.2)}
# A body lower than this share of its length is flat - a sea star from level is a line - and its
# three-quarter view is taken from 40 degrees above instead (`three_quarter_above`).
FLAT = 0.35
HUMAN_FRAME_M = 2.1
CREATURE_FRAMES_M = (0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.1, 3.0, 4.5, 6.0, 9.0, 12.0)
CELL_PX = 320                 # a cell's height in pixels
CELL_ASPECT = 0.6             # a cell's width over its height, unless the body needs more
LABEL_BAND = 0.14             # of the frame height, above it: the title line and the frame numbers
GROUND_BAND = 0.04            # of the frame height, below it: the margin, grown by what the poses need
# a band grows to at most this many cell heights. A clip whose root runs away would otherwise render a
# picture thousands of pixels tall; past the cap the pose really is out of the picture and `edge_cells`
# says so, which is the honest answer and not one any fixture reaches (the largest grown band is 0.25).
GROW_MAX = 2.0
BACKGROUND = (0.20, 0.22, 0.25)
BODY = (0.80, 0.80, 0.82)
# every further mesh on the rig (garments, hair), in turn: told apart from skin, and none with the floor
# line's orange cast the body measure leaves out
GARMENTS = ((0.30, 0.48, 0.80), (0.42, 0.66, 0.45), (0.58, 0.46, 0.78))
FLOOR = (0.95, 0.45, 0.08)
TEXT = (0.95, 0.95, 0.95)
# two cells show the same pose unless at least SAME_PIXELS pixels differ by more than PIXEL_DIFF (of 1.0)
PIXEL_DIFF = 0.04
SAME_PIXELS = 12


def _forward_vec(forward):
    if isinstance(forward, str):
        from .bodymap import axis_vector
        v = axis_vector(forward)
    else:
        v = Vector(tuple(forward)[:3])
    v = Vector((v.x, v.y, 0.0))
    return v.normalized() if v.length > 1e-6 else Vector((0.0, -1.0, 0.0))


def _view_dir(name, forward):
    """The direction the camera looks from, turned so `front` faces the body's forward."""
    d = Vector(VIEW_DIRS[name]).normalized()
    turn = Vector((0.0, -1.0, 0.0)).rotation_difference(_forward_vec(forward))
    return (turn @ d).normalized()


def _rest_points(meshes):
    pts = []
    for ob in meshes:
        mw = ob.matrix_world
        pts.extend(mw @ v.co for v in ob.data.vertices)
    return pts


def _np_points(mesh, matrix_world):
    """A mesh's vertices in world space, as an (n, 3) array, through `matrix_world`."""
    import numpy as np
    co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    m = np.array([tuple(row) for row in matrix_world], dtype=np.float64)
    return co.reshape(-1, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3]


def frame_height(meshes, forward="-Y"):
    """The shared frame height for these bodies: `HUMAN_FRAME_M` if upright, else a `CREATURE_FRAMES_M` rung."""
    pts = _rest_points([bpy.data.objects[m] if isinstance(m, str) else m for m in meshes])
    if not pts:
        return HUMAN_FRAME_M
    fwd = _forward_vec(forward)
    lo_z = min(min(p.z for p in pts), 0.0)
    height = max(p.z for p in pts) - lo_z
    depth = max(p.dot(fwd) for p in pts) - min(p.dot(fwd) for p in pts)
    if height > 2.0 * depth and height <= HUMAN_FRAME_M:
        return HUMAN_FRAME_M
    size = max(height, max(p.x for p in pts) - min(p.x for p in pts),
               max(p.y for p in pts) - min(p.y for p in pts)) * 1.15
    return next((r for r in CREATURE_FRAMES_M if r >= size), round(size, 2))


def clip_frames(action, count=8, loops=False):
    """`count` evenly spaced whole frames of `action`: a loop leaves out its last frame (the first again)."""
    start, end = (float(f) for f in action.frame_range)
    if loops:
        step = (end - start) / count
        return [int(round(start + i * step)) for i in range(count)]
    if count == 1:
        return [int(round(start))]
    step = (end - start) / (count - 1)
    return [int(round(start + i * step)) for i in range(count)]


def _text(scene, body, size, rotation, location):
    cu = bpy.data.curves.new("review_label", type="FONT")
    cu.body = body
    cu.size = size
    cu.align_x = "LEFT"
    ob = bpy.data.objects.new("review_label", cu)
    ob.color = TEXT + (1.0,)
    ob.rotation_euler = rotation
    ob.location = location
    scene.collection.objects.link(ob)
    return ob


def _floor_line(scene, length, thickness, centre, right):
    me = bpy.data.meshes.new("review_floor")
    half_l, half_t = length / 2.0, thickness / 2.0
    up = Vector((0.0, 0.0, 1.0))
    corners = [centre + right * sx * half_l + up * sz * half_t
               for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    # a flat strip facing the camera, in front of the bodies: a foot below the floor shows under it
    me.from_pydata(corners, [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("review_floor", me)
    ob.color = FLOOR + (1.0,)
    scene.collection.objects.link(ob)
    return ob


def _png_pixels(path):
    import numpy as np
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = img.size
        px = np.empty(w * h * img.channels, dtype=np.float32)
        img.pixels.foreach_get(px)
        return px.reshape(h, w, img.channels)[:, :, :3].copy()
    finally:
        bpy.data.images.remove(img)


def _save_png(path, rgb):
    import numpy as np
    h, w = rgb.shape[:2]
    img = bpy.data.images.new("review_contact", w, h, alpha=False)
    try:
        rgba = np.ones((h, w, 4), dtype=np.float32)
        rgba[:, :, :3] = rgb
        img.pixels.foreach_set(rgba.ravel())
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)


def _measure_strip(rgb, cells, cell_w, band_px):
    """(cells_with_body, distinct_cells, edge_cells) from a strip's pixels (row 0 is the bottom).

    Two cells are the same pose when fewer than `SAME_PIXELS` of their pixels differ by more than
    `PIXEL_DIFF` - not when their bytes hash alike: the render is not dithered (`sheet` turns dither off),
    but antialiasing can still move a value by a step or two. `distinct_cells` counts the cells unlike every
    cell counted before them, so one pose drawn 8 times is 1.

    `edge_cells` counts cells whose body reaches ANY edge of the strip - the left or right column, the
    bottom row or the top row under the label band. A pose crossing sideways lands in its neighbour's cell
    and neither frame reads on its own; a pose leaving through the bottom is cut off, and that was the
    silent one: the frame's height came from the rest pose alone, so a rabbit's JumpAir legs going through
    the floor were cropped at row 0 while the strip reported `edge_cells` 0 - in the very clip whose job is
    to show a foot through the floor. `sheet` now grows the bands from the evaluated poses so nothing
    reaches an edge; this counts what is left, the same way in every direction."""
    import numpy as np
    h = rgb.shape[0]
    body = rgb[: h - band_px]                                   # the label band is on top
    # the background as the PNG holds it (view transform applied): the bottom-left pixel, under the floor line
    bg = body[0, 0]
    differs = np.abs(body - bg).max(axis=2) > 0.04
    orange = (body[:, :, 0] - body[:, :, 2]) > 0.25
    mask = differs & ~orange
    # the floor line's rows and their antialiased edges: whatever is there is not evidence of a body
    rows = np.flatnonzero(orange.mean(axis=1) > 0.3)
    for r in rows:
        mask[max(0, r - 2):r + 3] = False
    with_body, edges, kept = 0, 0, []
    for i in range(cells):
        cell = mask[:, i * cell_w:(i + 1) * cell_w]
        if cell.sum() > 0:
            with_body += 1
        if cell[:, 0].any() or cell[:, -1].any() or cell[0, :].any() or cell[-1, :].any():
            edges += 1
        px = body[:, i * cell_w:(i + 1) * cell_w]
        if all(int((np.abs(px - k).max(axis=2) > PIXEL_DIFF).sum()) >= SAME_PIXELS for k in kept):
            kept.append(px)
    return with_body, len(kept), edges


def sheet(meshes, rig_name, actions, out_dir, views=None, frames=8, frame_height_m=None,
          forward="-Y", loops=None, cell_px=CELL_PX, contact=True, gdignore=True, title=None, floor=0.0,
          centre_poses=True):
    """Render the review sheet of `actions` on `meshes` (names) posed by `rig_name` into `out_dir`.

    views           default `REVIEW_VIEWS`, with `three_quarter_above` for a flat body (`FLAT`)
    loops           actions that loop (their last frame, a repeat of the first, is not drawn)
    frame_height_m  the shared scale, metres per cell height; None picks it (`frame_height`)
    cell_px         a cell's height in pixels; its width follows the cell's metres
    gdignore        write `.gdignore` in `out_dir`'s parent (the `review/` folder) and in `out_dir`
    title           the name written on each strip before the clip (default the rig's)
    floor           the floor height, drawn as an orange line
    centre_poses    a strip whose poses would reach out of their cells (a jump, a lunge, a travelling clip) is
                    drawn with each frame's extent centred in its cell and `(each frame centred)` in its
                    heading; False draws every pose where it stands, in cells as wide as the rest body needs

    Every png and review.json already in `out_dir` is replaced. Returns {dir, files, count, frame_height_m,
    cell_m, cell_px, bands_px [label, above, below], views, frames {clip: [..]}, strips {clip: {view: {file,
    size_px, cells_with_body, distinct_cells, edge_cells, centred}}}, contact {file, size_px}, seconds}, or
    {error}."""
    import numpy as np
    from . import verify

    t0 = time.time()
    rig = bpy.data.objects.get(rig_name)
    mesh_objs = [bpy.data.objects.get(m) for m in meshes]
    acts = [bpy.data.actions.get(a) for a in actions]
    if rig is None or not mesh_objs or None in mesh_objs:
        return {"error": "missing rig or mesh: %s / %s" % (rig_name, list(meshes))}
    missing = [a for a, o in zip(actions, acts) if o is None]
    if missing:
        return {"error": "no action(s) %s" % missing}
    loops = set(loops or [])

    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith(".png") or f == "review.json":
            os.remove(os.path.join(out_dir, f))
    if gdignore:
        for d in (os.path.dirname(os.path.abspath(out_dir)), out_dir):
            p = os.path.join(d, ".gdignore")
            if not os.path.exists(p):
                open(p, "w").close()

    if frame_height_m is None:
        frame_height_m = frame_height(mesh_objs, forward)
    frame_height_m = float(frame_height_m)

    # the frame, on the REST shape (see views.render_clip: bound_box is the last evaluated pose)
    rest = _rest_points(mesh_objs)
    lo = Vector((min(p.x for p in rest), min(p.y for p in rest), min(p.z for p in rest)))
    hi = Vector((max(p.x for p in rest), max(p.y for p in rest), max(p.z for p in rest)))
    from .views import _frame
    centre, scale, radius = _frame(lo, hi, 2.6, frame_height_m)
    if views is None:
        flat = (hi.z - lo.z) < FLAT * max(hi.x - lo.x, hi.y - lo.y)
        views = tuple("three_quarter_above" if flat and v == "three_quarter" else v for v in REVIEW_VIEWS)
    bad_views = [v for v in views if v not in VIEW_DIRS]
    if bad_views:
        return {"error": "unknown view(s) %s (have %s)" % (bad_views, sorted(VIEW_DIRS))}
    dirs = {v: _view_dir(v, forward) for v in views}
    rights = {v: dirs[v].cross(Vector((0.0, 0.0, 1.0))).normalized() * -1.0 for v in views}
    # screen up: perpendicular to the view direction and to `right`, so a view from above measures height
    # up the picture rather than up the world. For a level view it is world Z.
    ups = {v: dirs[v].cross(rights[v]).normalized() for v in views}
    # the widest the rest body is across any view, with room for a stride or a reach
    across = max(max(p.dot(rights[v]) for p in rest) - min(p.dot(rights[v]) for p in rest) for v in views)
    rest_cell_m = max(scale * CELL_ASPECT, across * 1.3)
    px_m = scale / cell_px
    band_px = int(round(cell_px * LABEL_BAND))
    ground_base_px = int(round(cell_px * GROUND_BAND))
    # What a cell covers is `scale` metres about the view's anchor, along that view's `up`: a level camera
    # frames from the floor up (the rest frame's centre), one from above looks at the body's middle. The
    # anchor does not move when the bands grow, so a pose's reach past the cell is measured against it.
    box_centre = Vector(((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, (lo.z + hi.z) / 2.0))
    anchors = {v: (centre if abs(dirs[v].z) < 1e-6 else box_centre) for v in views}
    # the bands, the picture's height and the camera targets follow the poses: they are set below, once
    # every clip has been evaluated

    main = bpy.context.scene
    prev_frame = main.frame_current
    ad = rig.animation_data or rig.animation_data_create()
    prev_action, prev_slot = ad.action, getattr(ad, "action_slot", None)
    prev_nla = getattr(ad, "use_nla", None)
    snap = verify._snapshot(rig)

    scene = bpy.data.scenes.new("rig_anything_review_tmp")
    world = bpy.data.worlds.new("rig_anything_review_world")
    cam_data = bpy.data.cameras.new("rig_anything_review_cam")
    cam = bpy.data.objects.new("rig_anything_review_cam", cam_data)
    made = []                                                   # objects to remove, with their data
    files, strips, frame_lists = [], {}, {}
    try:
        if prev_nla is not None:
            ad.use_nla = False
        # Every clip's frames first, frozen as meshes (not yet in the render scene), with where each frame's
        # body lies across each view: the cell width then holds every pose, and a strip that would spill is centred.
        shapes_of, shifts, centred = {}, {}, {}
        need_m = 0.0                                            # the widest half-pose drawn, about its cell's centre
        near_m = 0.0                                            # the nearest any pose comes to a camera
        # how far any pose reaches below and above its cell, up the picture: a jump rises out of the top,
        # a foot through the floor sinks out of the bottom, and both are what the sheet exists to show
        under_m, over_m = 0.0, 0.0
        for action, act in zip(actions, acts):
            binding = verify.bind_action(rig, act)
            if not binding["bound"]:
                return {"error": "%s: %s" % (action, binding["note"])}
            fl = clip_frames(act, frames, action in loops)
            frame_lists[action] = fl
            shapes, spans = [], []          # per cell: [(mesh object, frozen)] and {view: (lo, hi)} about its centre
            for f in fl:
                main.frame_set(f)
                dg = bpy.context.evaluated_depsgraph_get()
                dg.update()
                cell, pts = [], []
                for k, ob in enumerate(mesh_objs):
                    shape = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
                    fr = bpy.data.objects.new("review_frozen", shape)
                    fr.color = (GARMENTS[(k - 1) % len(GARMENTS)] if k else BODY) + (1.0,)
                    made.append(fr)
                    cell.append((ob, fr))
                    pts.append(_np_points(shape, ob.matrix_world))
                pts = np.concatenate(pts)
                span = {}
                for view in views:
                    r = np.array(tuple(rights[view]))
                    along = pts @ r - float(anchors[view].dot(rights[view]))
                    span[view] = (float(along.min()), float(along.max()))
                    toward_cam = pts @ np.array(tuple(dirs[view])) - float(anchors[view].dot(dirs[view]))
                    near_m = max(near_m, float(toward_cam.max()))
                    # the cell is `scale` metres about the anchor along `up`, whatever the bands do
                    rise = pts @ np.array(tuple(ups[view])) - float(anchors[view].dot(ups[view]))
                    under_m = max(under_m, -scale / 2.0 - float(rise.min()))
                    over_m = max(over_m, float(rise.max()) - scale / 2.0)
                shapes.append(cell)
                spans.append(span)
            shapes_of[action] = shapes
            shifts[action], centred[action] = {}, {}
            for view in views:
                # A pose reaching past its cell crosses into the next one and neither reads: then every frame
                # of the strip is centred on its own extent. Only those strips can widen the cells (a strip
                # drawn where it stands, `centre_poses=False`, keeps the rest body's width and may spill).
                spill = any(max(-s[view][0], s[view][1]) > rest_cell_m / 2.0 - px_m for s in spans)
                centres = bool(centre_poses and spill)
                sh = [-(s[view][0] + s[view][1]) / 2.0 if centres else 0.0 for s in spans]
                centred[action][view] = centres
                shifts[action][view] = sh
                if centres:
                    need_m = max(need_m, max(max(-(s[view][0] + d), s[view][1] + d) for s, d in zip(spans, sh)))
        # whole pixels per cell: the rest body's cell, grown if a pose that is drawn in its cell needs more
        cell_w_px = max(8, int(round(rest_cell_m / px_m)))
        if 2.0 * need_m > (cell_w_px - 1) * px_m:
            cell_w_px = int(math.ceil(2.0 * need_m / px_m)) + 4
        cell_w_m = cell_w_px * px_m
        width_px = cell_w_px * frames
        # The bands, in whole pixels, from the poses rather than from the rest shape. The frame is the rest
        # body's (`_frame`), and a pose is free to leave it: a rabbit's JumpAir legs go through the floor,
        # a launch rises above the head. Growing the band adds pixels at the same `px_m`, so the shared
        # scale, the cell and where the floor line sits are untouched - only the picture is taller. The
        # rest ground band is kept as the margin, so nothing drawn ends within it of an edge.
        grow_max_px = int(round(GROW_MAX * cell_px))
        ground_px = min(grow_max_px, ground_base_px + int(math.ceil(under_m / px_m)))
        top_px = min(grow_max_px, ground_base_px + int(math.ceil(over_m / px_m))) if over_m > 1e-9 else 0
        height_px = cell_px + band_px + top_px + ground_px
        height_m = height_px * px_m
        # the camera's target: the cell's centre, moved up the picture by half the bands above it and down
        # by half the band below, so the cell itself stays put whatever they grow to
        rise_m = px_m * (band_px + top_px - ground_px) / 2.0
        looks = {v: anchors[v] + ups[v] * rise_m for v in views}
        target = centre + Vector((0.0, 0.0, rise_m))

        scene.collection.objects.link(cam)
        scene.camera = cam
        world.color = BACKGROUND
        scene.world = world
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.render.resolution_x, scene.render.resolution_y = width_px, height_px
        scene.render.resolution_percentage = 100
        scene.render.film_transparent = False
        # no dither: its noise changes every cell's pixels a little, and one pose must render as one image
        scene.render.dither_intensity = 0.0
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        try:
            scene.view_settings.view_transform = "Standard"
        except TypeError:
            pass
        scene.display.render_aa = "8"
        shading = scene.display.shading
        shading.light = "STUDIO"
        shading.color_type = "OBJECT"
        shading.show_cavity = False
        shading.show_shadows = False
        cam_data.type = "ORTHO"
        cam_data.sensor_fit = "VERTICAL"
        cam_data.ortho_scale = height_m
        cam_data.clip_start = 0.001
        # labels and floor stand in front of every pose (a clip can travel toward the camera), the camera further
        front_m = max(radius * 3.0, near_m + radius * 0.5)
        cam_m = front_m + radius * 3.0
        cam_data.clip_end = cam_m * 2.0 + radius * 40.0 + cell_w_m * frames

        band_m = LABEL_BAND * scale
        name = title or rig_name
        for action in actions:
            fl, shapes = frame_lists[action], shapes_of[action]
            for cell in shapes:
                for _ob, fr in cell:
                    scene.collection.objects.link(fr)
            strips[action] = {}
            for view in views:
                d, right, look_at = dirs[view], rights[view], looks[view]
                level = abs(d.z) < 1e-6
                cam.location = look_at + d * cam_m
                rot = (-d).to_track_quat("-Z", "Y").to_euler()
                cam.rotation_euler = rot
                up = rot.to_matrix() @ Vector((0.0, 1.0, 0.0))
                for i, cell in enumerate(shapes):
                    along = (i - (frames - 1) / 2.0) * cell_w_m + shifts[action][view][i]
                    offset = Matrix.Translation(right * along)
                    for ob, fr in cell:
                        fr.matrix_world = offset @ ob.matrix_world
                extras = []
                toward = d * front_m                             # labels and floor in front of every body
                top_left = look_at - right * cell_w_m * frames / 2.0 + up * height_m / 2.0 + toward
                heading = "%s   %s   %s" % (name, action, view)
                if centred[action][view]:
                    heading += "   (each frame centred)"
                extras.append(_text(scene, heading, band_m * 0.34, rot,
                                    top_left - up * band_m * 0.42 + right * cell_w_m * 0.04))
                for i, f in enumerate(fl):
                    extras.append(_text(scene, "f%d" % f, band_m * 0.28, rot,
                                        top_left - up * band_m * 0.9 + right * cell_w_m * (i + 0.04)))
                if level:
                    extras.append(_floor_line(scene, cell_w_m * frames, scale / cell_px * 2.0,
                                              Vector((target.x, target.y, floor)) + toward, right))
                path = os.path.join(out_dir, "%s_%s.png" % (bpy.path.clean_name(action), view))
                scene.render.filepath = path
                try:
                    bpy.ops.render.render(write_still=True, scene=scene.name)
                finally:
                    for ob in extras:
                        data = ob.data
                        bpy.data.objects.remove(ob, do_unlink=True)
                        if isinstance(data, bpy.types.Curve):
                            bpy.data.curves.remove(data)
                        else:
                            bpy.data.meshes.remove(data)
                rgb = _png_pixels(path)
                with_body, distinct, edges = _measure_strip(rgb, frames, cell_w_px, band_px)
                strips[action][view] = {"file": path, "size_px": [int(rgb.shape[1]), int(rgb.shape[0])],
                                        "cells_with_body": with_body, "distinct_cells": distinct,
                                        "edge_cells": edges, "centred": centred[action][view]}
                files.append(path)
            for cell in shapes:
                for _ob, fr in cell:
                    shape = fr.data
                    bpy.data.objects.remove(fr, do_unlink=True)
                    bpy.data.meshes.remove(shape)
                    made.remove(fr)
    finally:
        for fr in made:
            shape = fr.data
            bpy.data.objects.remove(fr, do_unlink=True)
            bpy.data.meshes.remove(shape)
        main.frame_set(prev_frame)
        bpy.data.scenes.remove(scene, do_unlink=True)
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.cameras.remove(cam_data, do_unlink=True)
        bpy.data.worlds.remove(world)
        if prev_action is not None:
            verify.bind_action(rig, prev_action)
            if prev_slot is not None:
                try:
                    ad.action_slot = prev_slot
                except (AttributeError, TypeError):
                    pass
        else:
            ad.action = None
        if prev_nla is not None:
            ad.use_nla = prev_nla
        verify._restore(rig, snap)

    out = {"dir": out_dir, "files": files, "count": len(files), "frame_height_m": round(frame_height_m, 4),
           "ortho_scale_m": round(scale, 4), "cell_m": [round(cell_w_m, 4), round(scale, 4)],
           "cell_px": [cell_w_px, cell_px], "bands_px": [band_px, top_px, ground_px],
           "views": list(views), "frames": frame_lists, "strips": strips}
    if contact and files:
        # half size: rows are clips, columns are views, 4 px of background between them
        gap = 4
        half = [[None for _ in views] for _ in actions]
        for r, action in enumerate(actions):
            for c, view in enumerate(views):
                rgb = _png_pixels(strips[action][view]["file"])
                h2, w2 = rgb.shape[0] // 2, rgb.shape[1] // 2
                half[r][c] = rgb[: h2 * 2, : w2 * 2].reshape(h2, 2, w2, 2, 3).mean(axis=(1, 3))
        h2, w2 = half[0][0].shape[:2]
        rows, cols = len(actions), len(views)
        canvas = np.empty((rows * h2 + (rows + 1) * gap, cols * w2 + (cols + 1) * gap, 3), dtype=np.float32)
        canvas[:] = half[0][0][-1, -1]                          # the background as the strips hold it
        for r in range(rows):
            y = canvas.shape[0] - gap - (r + 1) * h2 - r * gap  # first clip on top (row 0 is the bottom)
            for c in range(cols):
                x = gap + c * (w2 + gap)
                canvas[y:y + h2, x:x + w2] = half[r][c]
        path = os.path.join(out_dir, "contact.png")
        _save_png(path, canvas)
        out["contact"] = {"file": path, "size_px": [int(canvas.shape[1]), int(canvas.shape[0])]}
        files.append(path)
        out["count"] = len(files)
    out["seconds"] = round(time.time() - t0, 2)
    with open(os.path.join(out_dir, "review.json"), "w", encoding="utf-8") as fh:
        json.dump({k: v for k, v in out.items() if k != "files"}, fh, indent=1)
    return out


def bound_meshes(rig_name, first=None):
    """Meshes deformed by `rig_name` (an Armature modifier on it) and visible in renders, `first` leading."""
    rig = bpy.data.objects.get(rig_name)
    out = []
    for ob in bpy.data.objects:
        if ob.type != "MESH" or ob.hide_render:
            continue
        if any(m.type == "ARMATURE" and m.object == rig for m in ob.modifiers) or ob.parent == rig and \
                ob.parent_type == "ARMATURE":
            out.append(ob.name)
    out.sort()
    if first in out:
        out.remove(first)
        out.insert(0, first)
    return out


def for_glb(meshes, rig_name, glb_path, actions, loops=None, forward="-Y", frame_height_m=None, **options):
    """The sheet an export writes: `<glb folder>/review/<glb name>/`. One folder per glb, because several
    bodies are often exported into one folder, and a shared `contact.png` would be the last one's."""
    base = os.path.splitext(os.path.basename(glb_path))[0]
    out_dir = os.path.join(os.path.dirname(os.path.abspath(glb_path)), "review", base)
    return sheet(meshes, rig_name, actions, out_dir, loops=loops, forward=forward,
                 frame_height_m=frame_height_m, title=options.pop("title", base), **options)


def summary(r):
    """What a manifest keeps of a sheet (paths go to review.json, not the manifest)."""
    if "error" in r:
        return {"error": r["error"]}
    return {"dir": r["dir"], "count": r["count"], "frame_height_m": r["frame_height_m"],
            "cell_px": r["cell_px"], "bands_px": r["bands_px"], "views": r["views"], "frames": r["frames"],
            "strips": {c: {v: {k: s[k] for k in ("size_px", "cells_with_body", "distinct_cells", "edge_cells",
                                                                "centred")}
                           for v, s in vs.items()} for c, vs in r["strips"].items()},
            "contact_px": (r.get("contact") or {}).get("size_px"), "seconds": r["seconds"]}
