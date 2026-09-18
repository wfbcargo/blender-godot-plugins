"""Close-ups: a lit EEVEE look set of a posed person - face, eyes, head, hands, bust, crotch, feet - aimed from bones.

    from rig_analysis import closeups
    r = closeups.look_set(["Walter_body", "Walter_shirt"], "Walter_rig", "C:/.../review/walter/close",
                          action="Walter_Idle")

The review sheet (`review.sheet`) shows how a body moves, workbench-lit at 2.1 m a cell: it cannot say
whether a face, a hand or a hairline looks right. Every agent of the figure study round wrote its own
`lit.py` to find out, framing the hands failed three times and a far camera hid the bust shelf twice
(improvements 06 rank 1). This is that picture, written by the build.

**Posed frame.** Everything is taken on ONE frame of one clip - `action` (the pipeline passes the character's
Idle) at `frame` (default: the clip's first frame) - and the label of every tile says which. The meshes are
frozen at that frame, so the tiles and the numbers below agree.

**Aimed from bones, never height fractions.** Each view's camera target, direction and frame size come from
the posed bones (and for the eyes, the sclera faces of the frozen mesh): the face from the head bone's
facing, the palm from the knuckle line and the hand's length, the bust from the shoulders, the crotch from
the hip joints, the feet from the foot and toe bones. The view math follows lookdev's Godot `close_shot.gd`,
so a Blender tile and a Godot one of the same view show the same thing. Distance sets the perspective, the
lens the framing: each tile's field of view is chosen so the subject fills it at the stated distance.

    view            distance  what
    face            0.6 m     front, from the head's facing, eyes to chin and both ears
    face_3q         0.6 m     three-quarter from the front-left: the hairline, the nose and the cheek in relief
    eyes            0.4 m     the eyes, lids, lashes and brows
    head_side       1.0 m     the whole head from its left: the ear, the hairline round it, the nape
    head_back       1.0 m     the whole head from behind: the nape hairline, a bun or tail and how it attaches
    hand_palm.L/.R  0.5 m     the palm; whatever is nearer the camera than the hand (the thigh) is clipped
    hand_back.L/.R  0.5 m     the back of the hand, knuckles and nails: from the front and the hand's outer side,
                              a little below the knuckles; nothing further than the hand (the thigh) is drawn
    bust            0.8 m     the chest from the front, collarbones to under the breasts
    under_bust      0.42 m    from below the bust, looking up: the fold under a breast and a top's lower edge
                              (only when asked, `under_bust=True`: the pipeline asks for any spec wearing a top)
    crotch          0.8 m     the pelvis from the front, hips to upper thighs
    knees           0.8 m     both knees from the front: the kneecaps
    feet            1.0 m     both feet from the front and above
    foot_inner.L/.R 0.6 m     a foot's inner side: the arch and the inner ankle bone
    foot_outer.L/.R 0.6 m     a foot's outer side: the outer ankle bone and the heel

**Checked, and it fails.** Every tile is measured from its own pixels and the posed bones, with the free
values reported (`tiles[view]`):
- `coverage` - the share of the tile the figure covers (the render's alpha); under `MIN_COVERAGE` the tile
  shows no body and fails (`empty`);
- `subject_uv` / `subject_off` - where the view's own points (`subject`: the hand's wrist, each knuckle and
  each fingertip; both eyes; each foot's ankle, heel and toe tip; the head, shoulders, hips or knees) project
  in the tile, and how far their centroid is from the centre (0 centre, 0.5 the edge); past `CENTRAL` the
  camera is not on the part it names (`off_centre`), and a subject behind the camera fails the same way;
- `subject_margin` - how far the worst of those points is inside the tile's nearest edge (negative outside);
  under `MARGIN` the tile cuts off part of what it is for (`cut`, naming the points) - a palm camera 3 cm up
  the arm keeps the centroid central and puts the fingertips on the edge;
- `on_body` - whether the figure covers the tile at that projected centroid, for views whose subject is
  on the body (not the gap between the feet or the thighs) (`off_body`).
A failed tile is still written and labelled; `failed` lists `view: reason` and the caller decides (the
pipeline's review stage raises). `aim_override` moves a view's target onto another bone or by a world
offset while the checks keep the view's own subject: the control that a wrongly aimed camera fails.

**Lit** with a sun key from the front-left above, a softer fill from the right and a grey world, AgX view
transform, EEVEE, on a flat grey backdrop composited from the alpha. The picture shows the file's Blender
materials: a lookdev material in Godot can differ (judge those with lookdev's `close-shot`).

Writes `<out_dir>/<view>.png` (each with its label band: view, distance, width of the tile in metres, the
clip and frame), `sheet.png` (every tile at half size), `close.json`, and a `.gdignore`. Every png and
close.json already in `out_dir` is replaced.
"""

from __future__ import annotations

import json
import math
import os
import time

import bpy
from mathutils import Matrix, Vector

# default distance of each view, metres (the lens is chosen from it)
DISTANCES = {"face": 0.6, "face_3q": 0.6, "eyes": 0.4, "head_side": 1.0, "head_back": 1.0,
             "hand_palm.L": 0.5, "hand_back.L": 0.5, "hand_palm.R": 0.5, "hand_back.R": 0.5,
             "bust": 0.8, "under_bust": 0.42, "crotch": 0.8, "knees": 0.8, "feet": 1.0,
             "foot_inner.L": 0.6, "foot_outer.L": 0.6, "foot_inner.R": 0.6, "foot_outer.R": 0.6}
VIEWS = ("face", "face_3q", "eyes", "head_side", "head_back", "hand_palm.L", "hand_back.L", "hand_palm.R",
         "hand_back.R", "bust", "crotch", "knees", "feet", "foot_inner.L", "foot_outer.L", "foot_inner.R",
         "foot_outer.R")
# the subject of a view is on the body at its projected centroid; not so for the gap between feet or thighs
OFF_BODY_OK = ("feet", "crotch", "knees")

MIN_COVERAGE = 0.05       # a tile the figure covers less of shows no body
CENTRAL = 0.3             # the subject's centroid within this of the centre (0.5 = the tile's edge), each axis
MARGIN = 0.04             # every subject point at least this far inside the tile's edges (0.5 = the centre)
# hand_back's camera direction, as weights of (the back of the hand's normal, the body's front, world up): from
# the outside front, a little below the knuckles - from above, the curled fingertips hide the nails
HAND_BACK = (1.0, 0.8, -0.4)
HAND_BACK_BEHIND = 0.02   # m: hand_back draws nothing further than the hand's deepest point and this (the thigh)
SIZE_PX = 512
LABEL_PX = 34
SAMPLES = 16
BACKDROP = (0.36, 0.37, 0.39)     # display-referred, what the tile shows behind the figure
LABEL_BG = (0.10, 0.11, 0.12)

# Candidate bone names per role, first found wins: rig-anything/Rigify first, then Mixamo (as lookdev's
# close_shot.gd).
ALIASES = {
    "head": ["head", "Head", "spine.006", "spine.005", "mixamorig:Head"],
    "neck": ["neck", "Neck", "spine.004", "mixamorig:Neck"],
    "chest": ["chest", "spine.003", "mixamorig:Spine2"],
    "hips": ["hips", "pelvis", "spine", "mixamorig:Hips"],
}
FINGERS = (("f_index", "Index"), ("f_middle", "Middle"), ("f_ring", "Ring"), ("f_pinky", "Pinky"))
for _s, _m in (("L", "Left"), ("R", "Right")):
    for _f, _mf in FINGERS:
        for _i in ("01", "03"):
            ALIASES[f"{_f}.{_i}.{_s}"] = [f"{_f}.{_i}.{_s}", f"mixamorig:{_m}Hand{_mf}{int(_i)}"]
    ALIASES.update({
        f"upper_arm.{_s}": [f"upper_arm.{_s}", f"mixamorig:{_m}Arm"],
        f"hand.{_s}": [f"hand.{_s}", f"mixamorig:{_m}Hand"],
        f"thumb.02.{_s}": [f"thumb.02.{_s}", f"mixamorig:{_m}HandThumb2"],
        f"thumb.03.{_s}": [f"thumb.03.{_s}", f"mixamorig:{_m}HandThumb3"],
        f"thigh.{_s}": [f"thigh.{_s}", f"mixamorig:{_m}UpLeg"],
        f"shin.{_s}": [f"shin.{_s}", f"mixamorig:{_m}Leg"],
        f"foot.{_s}": [f"foot.{_s}", f"mixamorig:{_m}Foot"],
        f"toe.{_s}": [f"toe.{_s}", f"mixamorig:{_m}ToeBase"],
    })


class _Pose:
    """The rig on the frozen frame: posed and rest positions of roles, and the body's frame at rest."""

    def __init__(self, rig):
        self.rig = rig
        self.mw = rig.matrix_world.copy()

    def name(self, role):
        for n in ALIASES.get(role, [role]):
            if n in self.rig.pose.bones:
                return n
        return None

    def missing(self, roles):
        miss = [f"{r} (tried {', '.join(ALIASES.get(r, [r]))})" for r in roles if self.name(r) is None]
        if not miss:
            return None
        have = [b.name for b in self.rig.data.bones][:60]
        return "no bone for %s; the rig has: %s" % ("; ".join(miss), ", ".join(have))

    def p(self, role, tail=False):
        pb = self.rig.pose.bones[self.name(role)]
        return self.mw @ (pb.tail if tail else pb.head)

    def rest(self, role):
        return self.mw @ self.rig.data.bones[self.name(role)].head_local

    def carry(self, role, v):
        """A rest-space world direction carried through the bone's pose into world space."""
        n = self.name(role)
        posed = (self.mw @ self.rig.pose.bones[n].matrix).to_3x3()
        rest = (self.mw @ self.rig.data.bones[n].matrix_local).to_3x3()
        return ((posed @ rest.inverted()) @ Vector(v)).normalized()


def _eyes(frozen, left):
    """Posed eyeball centres [left, right] from the sclera (else "eye", not lash or brow) faces of the
    frozen meshes, or []."""
    for ob in frozen:
        me = ob.data
        slots = [(m.name.lower() if m else "") for m in me.materials]
        pick = [i for i, n in enumerate(slots) if "sclera" in n]
        if not pick:
            pick = [i for i, n in enumerate(slots) if "eye" in n and "lash" not in n and "brow" not in n]
        if not pick:
            continue
        vids = set()
        for poly in me.polygons:
            if poly.material_index in pick:
                vids.update(poly.vertices)
        if not vids:
            continue
        pts = [ob.matrix_world @ me.vertices[i].co for i in vids]
        mid = sum(pts, Vector()) / len(pts)
        sides = ([p for p in pts if (p - mid).dot(left) > 0], [p for p in pts if (p - mid).dot(left) <= 0])
        if not sides[0] or not sides[1]:
            continue
        out = []
        for s in sides:
            lo = Vector((min(p.x for p in s), min(p.y for p in s), min(p.z for p in s)))
            hi = Vector((max(p.x for p in s), max(p.y for p in s), max(p.z for p in s)))
            out.append((lo + hi) / 2.0)
        return out
    return []


def _heel(frozen, ankle, toe_end, stature):
    """The back of the heel: of the body's (the first frozen mesh's) vertices below the ankle and within a
    foot's length of it, the one furthest back along the foot. A rig has no heel bone. Without such vertices,
    a point behind and below the ankle at a typical heel's offset."""
    import numpy as np
    flat = Vector((toe_end.x - ankle.x, toe_end.y - ankle.y, 0.0))
    back = -flat.normalized() if flat.length > 1e-4 else Vector((0.0, 1.0, 0.0))
    reach = max(flat.length, 0.1 * stature / 1.7)
    if frozen:
        ob = frozen[0]
        n = len(ob.data.vertices)
        if n:
            co = np.empty(n * 3, dtype=np.float64)
            ob.data.vertices.foreach_get("co", co)
            co = co.reshape(n, 3)
            mw = np.array(ob.matrix_world, dtype=np.float64)
            w = co @ mw[:3, :3].T + mw[:3, 3]
            d = w - np.array(ankle, dtype=np.float64)
            b = np.array(back, dtype=np.float64)
            along = d @ b                                       # how far behind the ankle
            side = np.linalg.norm(d[:, :2] - np.outer(along, b[:2]), axis=1)
            near = (d[:, 2] < 0.0) & (side < reach * 0.3) & (along > -reach) & (along < reach)
            if near.any():
                i = int(np.flatnonzero(near)[np.argmax(along[near])])
                return Vector(w[i])
    return ankle + back * 0.05 * stature / 1.7 - Vector((0.0, 0.0, max(0.0, ankle.z) * 0.6))


def _aim(view, dist, P, frozen, fwd_rest, up_rest, left_rest, stature):
    """{target, dir (toward the camera), up, frame (m across), near, subject {name: point}, body} or {error}."""
    fwd = P.carry("chest" if P.name("chest") else "hips", fwd_rest)
    flat = Vector((fwd.x, fwd.y, 0.0))
    fwd = flat.normalized() if flat.length > 1e-3 else Vector((0.0, -1.0, 0.0))
    zup = Vector((0.0, 0.0, 1.0))
    left = zup.cross(fwd).normalized() * -1.0          # the body's left on the ground: fwd x up = -left
    if left.dot(left_rest) < 0:
        left = -left
    a = {"near": 0.02, "up": zup, "body": view not in OFF_BODY_OK}
    if view in ("face", "face_3q", "eyes", "head_side", "head_back"):
        m = P.missing(["head", "neck"])
        if m:
            return {"error": m}
        hf, hu = P.carry("head", fwd_rest), P.carry("head", up_rest)
        hl = hu.cross(hf).normalized()                  # the head's left
        eyes = _eyes(frozen, left_rest)
        head_mid = (P.p("head") + P.p("head", tail=True)) / 2.0
        if eyes:
            centre, ipd = (eyes[0] + eyes[1]) / 2.0, (eyes[0] - eyes[1]).length
        else:
            nl = (P.p("head") - P.p("neck")).length
            centre, ipd = P.p("head") + hu * nl * 0.9 + hf * nl * 0.7, 0.063 * stature / 1.7
        a["up"] = hu
        a["subject"] = {"head": head_mid}
        # both eyes must be in the face views' picture, not only their centroid
        both = {"eye.L": eyes[0], "eye.R": eyes[1]} if eyes else {}
        if view == "face":
            a.update(target=centre - hu * ipd * 0.35 + hf * ipd * 0.2, dir=hf, frame=ipd * 4.4)
            a["subject"].update(both)
        elif view == "face_3q":
            a.update(target=centre - hu * ipd * 0.2, dir=(hf + hl).normalized(), frame=ipd * 4.8)
            a["subject"].update(both)
        elif view == "eyes":
            a.update(target=centre + hf * ipd * 0.2, dir=hf, frame=ipd * 2.4)
            if eyes:
                a["subject"] = dict(both)
        else:
            # the whole head and whatever hangs off it: from the neck's base to a head height above the eyes
            top = centre + hu * ipd * 2.3
            bottom = P.p("neck") - hu * ipd * 0.8
            a.update(target=(top + bottom) / 2.0 - hf * ipd * 0.6, frame=(top - bottom).length * 1.25,
                     dir=hl if view == "head_side" else -hf)
        return a
    if view.startswith("hand_"):
        s = view[-1]
        roles = [f"hand.{s}", f"thumb.02.{s}", f"thumb.03.{s}"] + [f"{f}.{i}.{s}" for f, _ in FINGERS
                                                                     for i in ("01", "03")]
        m = P.missing(roles)
        if m:
            return {"error": m}
        wrist, knuckle = P.p(f"hand.{s}"), P.p(f"f_middle.01.{s}")
        # every point the tile must show: the wrist, each knuckle and each fingertip (the end bone's tail)
        subject = {"wrist": wrist, "thumb.knuckle": P.p(f"thumb.02.{s}"),
                   "thumb.tip": P.p(f"thumb.03.{s}", tail=True)}
        for f, _ in FINGERS:
            subject[f"{f[2:]}.knuckle"] = P.p(f"{f}.01.{s}")
            subject[f"{f[2:]}.tip"] = P.p(f"{f}.03.{s}", tail=True)
        tip = subject["middle.tip"]
        along = (knuckle - wrist).normalized()
        across = (P.p(f"f_index.01.{s}") - P.p(f"f_pinky.01.{s}")).normalized()
        palm = along.cross(across).normalized() * (1.0 if s == "L" else -1.0)
        length = (tip - wrist).length
        if view.startswith("hand_palm"):
            # the palm faces the thigh: from the palm's side and the front, the thigh clipped (below)
            a.update(target=(wrist + tip) / 2.0, dir=(palm + fwd * 0.6).normalized(), frame=length * 1.3,
                     up=-along)
            # the hand hangs by the thigh: clip whatever is nearer the camera than the hand itself
            a["near"] = max(0.02, dist - length * 0.35)
        else:
            # the back of the hand and the nails: from the hand's outer side and the front, a little below the
            # knuckles, so the curled fingertips show their nails; the thigh behind the hand is not drawn (far
            # clip). From the outer side alone the thigh filled half the tile and the fingertips were hidden;
            # from above the knuckles the thigh filled the tile and the nails were hidden
            a.update(target=(wrist + tip) / 2.0, dir=(-palm * HAND_BACK[0] + fwd * HAND_BACK[1]
                                                      + zup * HAND_BACK[2]).normalized(),
                     frame=length * 1.3, up=-along)
            a["far_behind"] = HAND_BACK_BEHIND
        a["subject"] = subject
        a["key_side"] = 0.0
        return a
    if view in ("bust", "under_bust"):
        m = P.missing(["upper_arm.L", "upper_arm.R"])
        if m:
            return {"error": m}
        l, r = P.p("upper_arm.L"), P.p("upper_arm.R")
        w = (l - r).length
        cu = P.carry("chest" if P.name("chest") else "hips", up_rest)
        chest = (l + r) / 2.0 - cu * w * 0.35 + fwd * w * 0.3
        if view == "bust":
            a.update(target=chest, frame=w * 1.5, dir=fwd, subject={"upper_arm.L": l, "upper_arm.R": r,
                                                                   "chest": chest})
        else:
            fold = chest - cu * w * 0.3
            a.update(target=fold, frame=w * 1.25, dir=(fwd - zup * 0.9).normalized(),
                     subject={"under_bust": fold})
        return a
    if view == "crotch":
        m = P.missing(["thigh.L", "thigh.R"])
        if m:
            return {"error": m}
        l, r = P.p("thigh.L"), P.p("thigh.R")
        w = (l - r).length
        a.update(target=(l + r) / 2.0 - zup * w * 0.4, frame=w * 2.8, dir=(fwd - zup * 0.1).normalized(),
                 subject={"thigh.L": l, "thigh.R": r})
        return a
    if view == "knees":
        m = P.missing(["thigh.L", "thigh.R", "shin.L", "shin.R"])
        if m:
            return {"error": m}
        l, r = P.p("shin.L"), P.p("shin.R")
        w = (P.p("thigh.L") - P.p("thigh.R")).length
        a.update(target=(l + r) / 2.0, frame=w * 2.8, dir=(fwd + zup * 0.1).normalized(),
                 subject={"shin.L": l, "shin.R": r})
        return a
    if view == "feet" or view.startswith("foot_"):
        m = P.missing(["foot.L", "foot.R", "toe.L", "toe.R"])
        if m:
            return {"error": m}
        # each foot's ankle (the foot bone's head), heel (the rearmost skin under the ankle) and toe (the toe
        # bone's tail): every one must be in the picture
        feet = {}
        for s in ("L", "R"):
            ankle, toe_end = P.p(f"foot.{s}"), P.p(f"toe.{s}", tail=True)
            feet[s] = {"ankle": ankle, "heel": _heel(frozen, ankle, toe_end, stature), "toe": toe_end}
        if view == "feet":
            pts = [P.p("foot.L"), P.p("foot.R"), P.p("toe.L"), P.p("toe.R")]
            lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
            hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
            foot_len = (P.p("foot.L") - P.p("toe.L")).length * 1.6
            c = (lo + hi) / 2.0
            c.z = max(0.0, lo.z) * 0.5 + 0.03
            a.update(target=c, frame=max(hi.x - lo.x, hi.y - lo.y) + foot_len,
                     dir=(fwd + zup * 0.7).normalized(),
                     subject={f"{k}.{s}": p for s, f in feet.items() for k, p in f.items()})
        else:
            s = view[-1]
            ankle, toe_end = feet[s]["ankle"], feet[s]["toe"]
            c = (ankle + toe_end) / 2.0
            c.z = (ankle.z + max(0.0, toe_end.z)) / 2.0 - 0.01
            outer = left if s == "L" else -left              # away from the other foot
            inner = view.startswith("foot_inner")
            a.update(target=c, frame=(toe_end - ankle).length * 1.9,
                     dir=((-outer if inner else outer) + zup * 0.15).normalized(),
                     subject={f"{k}.{s}": p for k, p in feet[s].items()})
            if inner:
                # the other foot stands between the camera and this foot's inner side: clip what is
                # nearer than the foot's own half width
                a["near"] = max(0.02, dist - 0.09 * stature / 1.7)
                # ...and it still shades the big toe from the key though it is out of the picture: no key shadow
                a["key_shadow"] = False
        return a
    return {"error": "unknown view %r (views: %s, under_bust)" % (view, ", ".join(VIEWS))}


def _look_matrix(eye, direction, up):
    """A camera at `eye` looking along -`direction`, `up` up the picture."""
    z = Vector(direction).normalized()
    x = Vector(up).cross(z)
    if x.length < 1e-6:
        x = Vector((0.0, 0.0, 1.0)).cross(z) if abs(z.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    x.normalize()
    y = z.cross(x).normalized()
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = eye
    return m


def _project(cam_matrix, fov, p):
    """(u, v) in the square tile, 0..1 from the bottom left, and whether `p` is in front of the camera."""
    local = cam_matrix.inverted() @ Vector(p)
    if local.z >= -1e-6:
        return None, False
    half = math.tan(fov / 2.0)
    return (0.5 + local.x / (-local.z) / (2.0 * half), 0.5 + local.y / (-local.z) / (2.0 * half)), True


def _png_rgba(path):
    import numpy as np
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = img.size
        px = np.empty(w * h * img.channels, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(h, w, img.channels)
        if img.channels == 3:
            px = np.concatenate([px, np.ones((h, w, 1), dtype=np.float32)], axis=2)
        return px.copy()
    finally:
        bpy.data.images.remove(img)


def _save_png(path, rgb):
    import numpy as np
    h, w = rgb.shape[:2]
    img = bpy.data.images.new("close_out", w, h, alpha=False)
    try:
        rgba = np.ones((h, w, 4), dtype=np.float32)
        rgba[:, :, :3] = rgb
        img.pixels.foreach_set(rgba.ravel())
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)


def _labels(texts, width, band, tmp_path):
    """Each text rendered white on dark into a band `band` px tall and `width` wide, (h, w, 3) arrays, row 0
    the bottom, from one workbench render."""
    import numpy as np
    scene = bpy.data.scenes.new("close_labels_tmp")
    cam_data = bpy.data.cameras.new("close_labels_cam")
    cam = bpy.data.objects.new("close_labels_cam", cam_data)
    world = bpy.data.worlds.new("close_labels_world")
    made = []
    try:
        n = len(texts)
        scene.collection.objects.link(cam)
        scene.camera = cam
        world.color = LABEL_BG
        scene.world = world
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.render.resolution_x, scene.render.resolution_y = width, band * n
        scene.render.resolution_percentage = 100
        scene.render.dither_intensity = 0.0
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        try:
            scene.view_settings.view_transform = "Standard"
        except TypeError:
            pass
        scene.display.shading.light = "FLAT"
        scene.display.shading.color_type = "OBJECT"
        # one metre per band: the picture is `n` metres tall, `width / band` wide, looking down -Z
        cam_data.type = "ORTHO"
        cam_data.sensor_fit = "VERTICAL"
        cam_data.ortho_scale = float(n)
        aspect = width / float(band)
        cam.location = (aspect / 2.0, -n / 2.0, 10.0)
        for i, t in enumerate(texts):
            cu = bpy.data.curves.new("close_label", type="FONT")
            cu.body = t
            cu.size = 0.44
            ob = bpy.data.objects.new("close_label", cu)
            ob.color = (0.95, 0.95, 0.95, 1.0)
            ob.location = (0.25, -i - 0.72, 0.0)
            scene.collection.objects.link(ob)
            made.append(ob)
        scene.render.filepath = tmp_path
        bpy.ops.render.render(write_still=True, scene=scene.name)
        px = _png_rgba(tmp_path)[:, :, :3]
        os.remove(tmp_path)
        # row 0 is the bottom: the last text's band is at the bottom of the picture
        return [px[(n - 1 - i) * band:(n - i) * band] for i in range(n)]
    finally:
        for ob in made:
            cu = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            bpy.data.curves.remove(cu)
        bpy.data.scenes.remove(scene, do_unlink=True)
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.cameras.remove(cam_data, do_unlink=True)
        bpy.data.worlds.remove(world)


def _light(scene):
    """The key and the fill: two suns, aimed per view by `_aim_lights`; only the key casts shadows."""
    made = []
    for name, energy, angle, shadow in (("close_key", 3.2, 3.0, True), ("close_fill", 1.1, 12.0, False)):
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy = energy
        ld.angle = math.radians(angle)
        # the fill casts no shadow: a palm hangs facing the thigh, and the thigh clipped out of the picture
        # would still shade it black
        ld.use_shadow = shadow
        ob = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(ob)
        made.append(ob)
    return made


def _aim_lights(lights, cam_matrix, key_side=0.8, key_shadow=True):
    """Light each tile as a photographer would its subject: the key from the camera's upper left (turned
    toward world up), the fill from its right. A light fixed on the body would leave the back of the head and
    the back of a hand turned from it in shadow, which is not what those tiles are for. A hand's key sits over
    the camera (`key_side` 0): a palm hangs facing the thigh, and a key from the side goes behind it."""
    m = cam_matrix.to_3x3()
    right, toward = m.col[0].normalized(), m.col[2].normalized()
    zup = Vector((0.0, 0.0, 1.0))
    lights[0].data.use_shadow = key_shadow
    for ob, frm in zip(lights, (toward * 1.0 - right * key_side + zup * 0.7, toward * 1.0 + right * 1.0 + zup * 0.2)):
        # a sun shines along its -Z: point -Z from `frm` toward the body
        ob.rotation_euler = frm.normalized().to_track_quat("Z", "Y").to_euler()


def look_set(meshes, rig_name, out_dir, views=None, action=None, frame=None, under_bust=False,
             distances=None, size_px=SIZE_PX, samples=SAMPLES, aim_override=None, title=None, gdignore=True):
    """Render the close-up look set of `meshes` (names, the body first) posed by `rig_name` into `out_dir`.

    views        default `VIEWS`, plus `under_bust` when `under_bust` is True
    action       the clip the pose is taken from (None: the rig's current pose); `frame` default its first
    distances    {view: metres} overriding `DISTANCES`
    aim_override {view: bone name | (dx, dy, dz)}: that view's camera target moves onto the bone's posed head,
                 or by the offset, keeping its direction, lens and checks - the control that a camera aimed
                 from the wrong bone, or at nothing, fails
    Returns {dir, pose {action, frame}, tiles {view: {...}}, failed [..], files, sheet, seconds} or {error}."""
    import numpy as np
    from . import verify

    t0 = time.time()
    rig = bpy.data.objects.get(rig_name)
    mesh_objs = [bpy.data.objects.get(m) for m in meshes]
    if rig is None or rig.type != "ARMATURE" or not mesh_objs or None in mesh_objs:
        return {"error": "missing rig or mesh: %s / %s" % (rig_name, list(meshes))}
    act = None
    if action is not None:
        act = bpy.data.actions.get(action)
        if act is None:
            return {"error": "no action %r" % action}
    views = list(views if views is not None else VIEWS)
    if under_bust and "under_bust" not in views:
        views.append("under_bust")
    unknown = [v for v in views if v not in DISTANCES]
    if unknown:
        return {"error": "unknown view(s) %s (have %s)" % (unknown, sorted(DISTANCES))}
    dist_of = dict(DISTANCES, **(distances or {}))
    aim_override = dict(aim_override or {})

    P = _Pose(rig)
    m = P.missing(["head", "hips", "upper_arm.L", "upper_arm.R"])
    if m:
        return {"error": m}

    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith(".png") or f == "close.json":
            os.remove(os.path.join(out_dir, f))
    if gdignore:
        p = os.path.join(out_dir, ".gdignore")
        if not os.path.exists(p):
            open(p, "w").close()

    main = bpy.context.scene
    prev_frame = main.frame_current
    ad = rig.animation_data or rig.animation_data_create()
    prev_action, prev_slot = ad.action, getattr(ad, "action_slot", None)
    prev_nla = getattr(ad, "use_nla", None)
    snap = verify._snapshot(rig)
    scene = bpy.data.scenes.new("rig_anything_close_tmp")
    world = bpy.data.worlds.new("rig_anything_close_world")
    cam_data = bpy.data.cameras.new("rig_anything_close_cam")
    cam = bpy.data.objects.new("rig_anything_close_cam", cam_data)
    frozen, lights, tiles, failed, files = [], [], {}, [], []
    pose = {"action": action, "frame": None}
    try:
        if prev_nla is not None:
            ad.use_nla = False
        if act is not None:
            binding = verify.bind_action(rig, act)
            if not binding["bound"]:
                return {"error": "%s: %s" % (action, binding["note"])}
            f = int(round(act.frame_range[0])) if frame is None else int(frame)
            main.frame_set(f)
            pose["frame"] = f
        else:
            pose["frame"] = main.frame_current
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        for ob in mesh_objs:
            shape = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True,
                                                    depsgraph=dg)
            fr = bpy.data.objects.new("close_frozen", shape)
            fr.matrix_world = ob.matrix_world.copy()
            frozen.append(fr)
            scene.collection.objects.link(fr)

        # the body's frame at rest (world): up from hips to head, left between the shoulders
        up_rest = (P.rest("head") - P.rest("hips")).normalized()
        left_rest = (P.rest("upper_arm.L") - P.rest("upper_arm.R")).normalized()
        fwd_rest = left_rest.cross(up_rest).normalized()
        up_rest = fwd_rest.cross(left_rest).normalized()
        # the body's height from the rig, not the mesh: a frame size must not collapse with what is drawn
        # (the empty-tile control draws a speck)
        lowest = min((P.mw @ b.head_local).z for b in rig.data.bones)
        stature = max(0.3, (P.mw @ rig.data.bones[P.name("head")].tail_local).z - lowest)

        scene.collection.objects.link(cam)
        scene.camera = cam
        world.color = (0.20, 0.20, 0.21)
        scene.world = world
        try:
            scene.render.engine = "BLENDER_EEVEE"
        except TypeError:
            scene.render.engine = "BLENDER_EEVEE_NEXT"
        if hasattr(scene, "eevee"):
            scene.eevee.taa_render_samples = int(samples)
        scene.render.resolution_x = scene.render.resolution_y = int(size_px)
        scene.render.resolution_percentage = 100
        scene.render.film_transparent = True
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"
        try:
            scene.view_settings.view_transform = "AgX"
            scene.view_settings.look = "None"
        except TypeError:
            pass
        lights = _light(scene)
        cam_data.type = "PERSP"
        cam_data.sensor_fit = "VERTICAL"

        aims = {}
        for view in views:
            dist = float(dist_of[view])
            a = _aim(view, dist, P, frozen, fwd_rest, up_rest, left_rest, stature)
            if "error" in a:
                return {"error": "%s: %s" % (view, a["error"])}
            ov = aim_override.get(view)
            if ov is not None:
                if isinstance(ov, str):
                    if P.name(ov) is None:
                        return {"error": "%s: aim_override bone %r not in the rig" % (view, ov)}
                    a["target"] = P.p(ov)
                else:
                    a["target"] = a["target"] + Vector(tuple(ov))
                a["overridden"] = ov if isinstance(ov, str) else list(ov)
            a["distance"] = dist
            a["fov"] = 2.0 * math.atan(a["frame"] * 0.5 / dist)
            aims[view] = a

        name = title or rig_name
        clip = ("%s f%d" % (action, pose["frame"])) if action else "rest/current f%d" % pose["frame"]
        texts = ["%s  %.2f m  (%.2f m wide)  %s  %s" % (v, aims[v]["distance"], aims[v]["frame"], clip, name)
                 for v in views]
        bands = _labels(texts, int(size_px), LABEL_PX, os.path.join(out_dir, "_labels_tmp.png"))
        bg = np.array(BACKDROP, dtype=np.float32)

        for view, band in zip(views, bands):
            a = aims[view]
            eye = a["target"] + a["dir"] * a["distance"]
            mat = _look_matrix(eye, a["dir"], a["up"])
            cam.matrix_world = mat
            _aim_lights(lights, mat, a.get("key_side", 0.8), a.get("key_shadow", True))
            cam_data.angle_y = a["fov"]
            cam_data.clip_start = a["near"]
            cam_data.clip_end = a["distance"] + 4.0
            if a.get("far_behind") is not None:
                # nothing further than the subject's deepest point (and a margin) is drawn: the thigh
                # behind a hand
                deepest = max((a["target"] - Vector(p_)).dot(a["dir"]) for p_ in a["subject"].values())
                cam_data.clip_end = a["distance"] + max(0.0, deepest) + a["far_behind"]
            raw = os.path.join(out_dir, "_render_tmp.png")
            scene.render.filepath = raw
            bpy.ops.render.render(write_still=True, scene=scene.name)
            rgba = _png_rgba(raw)
            os.remove(raw)
            alpha = rgba[:, :, 3:4]
            rgb = rgba[:, :, :3] * alpha + bg * (1.0 - alpha)          # straight alpha over the backdrop
            mask = rgba[:, :, 3] > 0.5
            coverage = float(mask.mean())
            # the view's own bones in the picture
            uvs, behind = {}, []
            for k, pnt in a["subject"].items():
                uv, front = _project(mat, a["fov"], pnt)
                if not front:
                    behind.append(k)
                else:
                    uvs[k] = [round(uv[0], 3), round(uv[1], 3)]
            reasons = []
            if coverage < MIN_COVERAGE:
                reasons.append("empty (coverage %.3f < %.2f)" % (coverage, MIN_COVERAGE))
            off, on_body, margin = None, None, None
            if behind:
                reasons.append("off_centre (%s behind the camera)" % ", ".join(behind))
            elif uvs:
                # every point, not only the centroid: a palm camera 6 cm up keeps the centroid in the middle
                # and cuts the fingertips off. The free value: how far the worst point is inside the edge
                # (negative outside the tile)
                inside = {k: min(u, 1.0 - u, v, 1.0 - v) for k, (u, v) in uvs.items()}
                worst = min(inside, key=inside.get)
                margin = round(inside[worst], 3)
                if margin < MARGIN:
                    cut = sorted(k for k, m_ in inside.items() if m_ < MARGIN)
                    reasons.append("cut (%s: %.3f inside the edge < %.2f)" % (", ".join(cut), margin, MARGIN))
                cu = sum(u for u, _ in uvs.values()) / len(uvs)
                cv = sum(v for _, v in uvs.values()) / len(uvs)
                off = round(max(abs(cu - 0.5), abs(cv - 0.5)), 3)
                if off > CENTRAL:
                    reasons.append("off_centre (subject centroid %.3f from the centre > %.2f)" % (off, CENTRAL))
                h, w = mask.shape
                x, y = int(cu * (w - 1)), int(cv * (h - 1))
                if 0 <= x < w and 0 <= y < h:
                    on_body = bool(mask[max(0, y - 2):y + 3, max(0, x - 2):x + 3].any())
                else:
                    on_body = False
                if a["body"] and not on_body:
                    reasons.append("off_body (no figure at the subject's centroid)")
            path = os.path.join(out_dir, "%s.png" % view)
            _save_png(path, np.concatenate([rgb, band], axis=0))      # row 0 is the bottom: label on top
            files.append(path)
            tiles[view] = {"file": path, "distance_m": round(a["distance"], 3), "frame_m": round(a["frame"], 4),
                           "fov_deg": round(math.degrees(a["fov"]), 2), "near_m": round(a["near"], 3),
                           "coverage": round(coverage, 4), "subject_uv": uvs, "subject_off": off,
                           "subject_margin": margin,
                           "on_body": on_body, "body_view": a["body"], "ok": not reasons, "fail": reasons,
                           "target": [round(x, 4) for x in a["target"]], "eye": [round(x, 4) for x in eye]}
            if "overridden" in a:
                tiles[view]["aim_override"] = a["overridden"]
            if reasons:
                failed.append("%s: %s" % (view, "; ".join(reasons)))
    finally:
        for fr in frozen:
            me = fr.data
            bpy.data.objects.remove(fr, do_unlink=True)
            bpy.data.meshes.remove(me)
        for ob in lights:
            ld = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            bpy.data.lights.remove(ld)
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

    out = {"dir": out_dir, "pose": pose, "views": views, "size_px": int(size_px), "samples": int(samples),
           "tiles": tiles, "failed": failed, "files": files}
    if files:
        out["sheet"] = _sheet(files, os.path.join(out_dir, "sheet.png"))
        files.append(out["sheet"]["file"])
    out["count"] = len(files)
    out["seconds"] = round(time.time() - t0, 2)
    with open(os.path.join(out_dir, "close.json"), "w", encoding="utf-8") as fh:
        json.dump({k: v for k, v in out.items() if k != "files"}, fh, indent=1)
    return out


def _sheet(files, path, per_row=4, gap=4):
    """Every tile at half size, `per_row` to a row, first tile top left."""
    import numpy as np
    halves = []
    for f in files:
        rgb = _png_rgba(f)[:, :, :3]
        h2, w2 = rgb.shape[0] // 2, rgb.shape[1] // 2
        halves.append(rgb[: h2 * 2, : w2 * 2].reshape(h2, 2, w2, 2, 3).mean(axis=(1, 3)))
    h2, w2 = halves[0].shape[:2]
    rows = (len(halves) + per_row - 1) // per_row
    cols = min(per_row, len(halves))
    canvas = np.empty((rows * h2 + (rows + 1) * gap, cols * w2 + (cols + 1) * gap, 3), dtype=np.float32)
    canvas[:] = LABEL_BG
    for i, t in enumerate(halves):
        r, c = divmod(i, per_row)
        y = canvas.shape[0] - gap - (r + 1) * h2 - r * gap       # row 0 is the bottom: first row on top
        x = gap + c * (w2 + gap)
        canvas[y:y + h2, x:x + w2] = t
    _save_png(path, canvas)
    return {"file": path, "size_px": [int(canvas.shape[1]), int(canvas.shape[0])]}


def summary(r):
    """What a manifest keeps of a look set (paths go to close.json)."""
    if "error" in r:
        return {"error": r["error"]}
    return {"count": r["count"], "pose": r["pose"], "views": r["views"], "size_px": r["size_px"],
            "tiles": {v: {k: t[k] for k in ("distance_m", "frame_m", "coverage", "subject_off", "subject_margin",
                                                   "on_body", "ok")}
                      for v, t in r["tiles"].items()},
            "failed": r["failed"], "seconds": r["seconds"]}
