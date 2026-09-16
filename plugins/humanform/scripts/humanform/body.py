"""A body as arrays: its rest-pose surface in world space, and its landmarks.

    b = body.load("Nora")            # evaluated in the rig's rest pose
    b.co, b.edges, b.loop_edge, b.loop_face, b.tris
    b.landmarks["shoulder.L"]        # Vector, world space
    b.landmark_source                # "rig:Nora_rig", "mpfb-joints" or "none"

Landmarks come from the rig by bone name (rig-anything / Rigify basic_human, MPFB
game_engine and default, Mixamo), or from MPFB's joint-* vertex groups when there is no rig.
"""

from __future__ import annotations

import re

import bpy
import numpy as np
from mathutils import Vector

# landmark -> the bone whose HEAD is that joint, by rig family (left side; right is mirrored)
BONE_HEADS = {
    "shoulder": ["upper_arm", "upperarm", "upperarm01", "arm"],
    "elbow": ["forearm", "lowerarm", "lowerarm01"],
    "wrist": ["hand", "wrist"],
    "hip": ["thigh", "upperleg01", "upleg"],
    "knee": ["shin", "calf", "lowerleg01", "leg"],
    "ankle": ["foot"],
}
MPFB_JOINTS = {
    "shoulder": "joint-{s}-shoulder", "elbow": "joint-{s}-elbow", "wrist": "joint-{s}-hand",
    "hip": "joint-{s}-upper-leg", "knee": "joint-{s}-knee", "ankle": "joint-{s}-ankle",
}
MPFB_POINTS = dict(MPFB_JOINTS, eye="joint-{s}-eye")
_PREFIX = re.compile(r"^(def[-_]|org[-_]|mch[-_]|mixamorig\d*:)", re.I)


def obj(o):
    return bpy.data.objects[o] if isinstance(o, str) else o


def rig_of(ob):
    for m in ob.modifiers:
        if m.type == "ARMATURE" and m.object is not None:
            return m.object
    p = ob.parent
    return p if p is not None and p.type == "ARMATURE" else None


def _side_of(name):
    """'L', 'R' or None from a bone name in any of the supported conventions."""
    n = _PREFIX.sub("", name)
    low = n.lower()
    if re.search(r"(\.|_|-)l$", low) or low.startswith("left"):
        return "L"
    if re.search(r"(\.|_|-)r$", low) or low.startswith("right"):
        return "R"
    return None


def _stem(name):
    """'DEF-upper_arm.L' -> 'upper_arm', 'mixamorig:LeftForeArm' -> 'forearm', 'calf_l' -> 'calf'."""
    n = _PREFIX.sub("", name).lower()
    n = re.sub(r"(\.|_|-)(l|r)$", "", n)
    return re.sub(r"^(left|right)", "", n)


def rig_landmarks(rig):
    """{'shoulder.L': Vector, ...} from bone heads in world space, rest pose.

    Deform bones win over ORG/MCH copies of the same name, so a generated Rigify rig reads the
    same joints as its metarig."""
    by_stem = {}
    for b in rig.data.bones:
        side = _side_of(b.name)
        if side is None:
            continue
        key = (_stem(b.name), side)
        if key not in by_stem or b.use_deform and not by_stem[key].use_deform:
            by_stem[key] = b
    mw = rig.matrix_world
    found = {}
    for mark, stems in BONE_HEADS.items():
        for side in ("L", "R"):
            for st in stems:
                b = by_stem.get((st, side))
                if b is not None:
                    found[f"{mark}.{side}"] = mw @ b.head_local
                    break
    return found


_GROUP_CACHE = {}


def mpfb_landmarks(ob, co, patterns=MPFB_JOINTS):
    found = {}
    if len(co) != len(ob.data.vertices):
        return found
    key = (ob.data.name, len(co), len(ob.vertex_groups), tuple(sorted(patterns)))
    if key in _GROUP_CACHE:       # membership is topology, not shape: read it once per mesh
        return {name: Vector(co[idx].mean(axis=0)) for name, idx in _GROUP_CACHE[key].items()}
    wanted = {}
    for mark, pattern in patterns.items():
        for side, s in (("L", "l"), ("R", "r")):
            g = ob.vertex_groups.get(pattern.format(s=s))
            if g is not None:
                wanted[g.index] = f"{mark}.{side}"
    if not wanted:
        return found
    members = {k: [] for k in wanted}
    for v in ob.data.vertices:
        for e in v.groups:
            if e.group in members:
                members[e.group].append(v.index)
    cached = {}
    for gi, idx in members.items():
        if idx:
            cached[wanted[gi]] = np.array(idx)
            found[wanted[gi]] = Vector(co[idx].mean(axis=0))
    _GROUP_CACHE[key] = cached
    return found


class Body:
    """Rest-pose surface arrays and landmarks for one mesh object."""

    def __init__(self, ob, rest=True):
        self.ob = obj(ob)
        self.rig = rig_of(self.ob)
        self._read(rest)
        self.landmarks = {}
        self.landmark_source = "none"
        if self.rig is not None:
            self.landmarks = rig_landmarks(self.rig)
            if self.landmarks:
                self.landmark_source = "rig:" + self.rig.name
        self.mpfb = mpfb_landmarks(self.ob, self.co_unmasked, MPFB_POINTS)
        if len(self.landmarks) < 12:
            mp = {k: v for k, v in self.mpfb.items() if not k.startswith("eye.")}
            if len(mp) > len(self.landmarks):
                self.landmarks, self.landmark_source = mp, "mpfb-joints"

    def _read(self, rest):
        rig = self.rig
        prev = None
        if rest and rig is not None:
            prev = rig.data.pose_position
            rig.data.pose_position = "REST"
        # MPFB masks its helper geometry with a Mask modifier; read joints from the unmasked mesh
        masks = [m for m in self.ob.modifiers if m.type == "MASK" and m.show_viewport]
        try:
            bpy.context.view_layer.update()
            dg = bpy.context.evaluated_depsgraph_get()
            self.co_unmasked = None
            if masks:
                for m in masks:
                    m.show_viewport = False
                bpy.context.view_layer.update()
                dg = bpy.context.evaluated_depsgraph_get()
                self.co_unmasked = self._coords(self.ob.evaluated_get(dg))
                for m in masks:
                    m.show_viewport = True
                bpy.context.view_layer.update()
                dg = bpy.context.evaluated_depsgraph_get()
            ev = self.ob.evaluated_get(dg)
            me = ev.to_mesh()
            try:
                self._arrays(me)
            finally:
                ev.to_mesh_clear()
            if self.co_unmasked is None:
                self.co_unmasked = self.co
        finally:
            for m in masks:
                m.show_viewport = True
            if prev is not None:
                rig.data.pose_position = prev
                bpy.context.view_layer.update()

    def _coords(self, ev):
        me = ev.to_mesh()
        try:
            n = len(me.vertices)
            co = np.empty(n * 3, np.float32)
            me.vertices.foreach_get("co", co)
        finally:
            ev.to_mesh_clear()
        return self._world(co.reshape(-1, 3))

    def _world(self, co):
        m = np.array(self.ob.matrix_world, dtype=np.float64)
        return co.astype(np.float64) @ m[:3, :3].T + m[:3, 3]

    def _arrays(self, me):
        nv, ne, nl, nf = len(me.vertices), len(me.edges), len(me.loops), len(me.polygons)
        co = np.empty(nv * 3, np.float32)
        me.vertices.foreach_get("co", co)
        self.co = self._world(co.reshape(-1, 3))
        e = np.empty(ne * 2, np.int64)
        me.edges.foreach_get("vertices", e)
        self.edges = e.reshape(-1, 2)
        le = np.empty(nl, np.int64)
        me.loops.foreach_get("edge_index", le)
        self.loop_edge = le
        ltot = np.empty(nf, np.int64)
        me.polygons.foreach_get("loop_total", ltot)
        self.face_sizes = ltot
        self.loop_face = np.repeat(np.arange(nf), ltot)
        me.calc_loop_triangles()
        t = np.empty(len(me.loop_triangles) * 3, np.int64)
        me.loop_triangles.foreach_get("vertices", t)
        self.tris = t.reshape(-1, 3)
        self.uv_layers = [u.name for u in me.uv_layers]

    # convenience -------------------------------------------------------------------------
    @property
    def floor(self):
        return float(self.co[:, 2].min())

    @property
    def top(self):
        return float(self.co[:, 2].max())

    def mark(self, name):
        v = self.landmarks.get(name)
        return None if v is None else Vector(v)


def load(ob, rest=True):
    return Body(ob, rest=rest)
