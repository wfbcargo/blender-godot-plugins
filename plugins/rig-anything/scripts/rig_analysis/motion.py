"""Pose a body by targets, bake it to keyframes, and prove Blender agrees.

`gait` animates by rotating bones through probed axes, which is enough when a
foot is allowed to slide. Crouching, sliding and climbing are not like that: a
foot stays planted while the hips drop, a hand stays on a wall while the body
rises. Those are positions, so this module poses by position.

Nothing here reads a rotation sign or a bone roll. Every pose is built as
armature-space matrices by rigidly moving each bone's REST matrix:

- the axial chain bends as a sequence of rigid segments pivoting on its own
  joints, walked from the pelvis outward - so it does not matter which way the
  hierarchy runs (the generic builder roots a biped at its neck);
- a limb is solved as a two-bone triangle and each segment is carried from its
  rest frame to the solved one by the rotation that maps (segment direction,
  bend-plane normal) onto the new pair, which fixes twist as well as aim;
- everything else follows its parent by plain forward kinematics.

Local keyframe values are then derived from those matrices. Because this
duplicates Blender's own pose evaluation, `evaluate` plays the baked clip back
through Blender and compares every bone against the prediction. That is the
guard against every quiet failure this package has met - an unbound slot, a
stale armature, a bone with unusual inheritance - all of which would otherwise
yield a clip that looks right in the numbers and wrong on screen.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Vector

from . import verify


def _depth(bone):
    d = 0
    while bone.parent is not None:
        bone = bone.parent
        d += 1
    return d


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


class Body:
    """A rig plus its body map, with the rest data the maths needs."""

    def __init__(self, rig, bm):
        self.rig = rig
        self.bm = bm
        self.bones = sorted(rig.data.bones, key=_depth)
        self.rest = {b.name: b.matrix_local.copy() for b in self.bones}
        self.rest_local = {
            b.name: (b.parent.matrix_local.inverted() @ b.matrix_local
                     if b.parent else b.matrix_local.copy())
            for b in self.bones
        }
        self.limbs = {l["name"]: l for l in bm["limbs"]}
        self.com_terms, self.com_source = _com_terms(rig)

    # ---------------------------------------------------------------- FK
    def fk(self, overrides=None):
        overrides = overrides or {}
        posed = {}
        for b in self.bones:
            if b.name in overrides:
                posed[b.name] = overrides[b.name]
            elif b.parent is None:
                posed[b.name] = self.rest[b.name].copy()
            else:
                posed[b.name] = posed[b.parent.name] @ self.rest_local[b.name]
        return posed

    def basis(self, posed):
        out = {}
        for b in self.bones:
            parent = posed[b.parent.name] if b.parent else Matrix.Identity(4)
            out[b.name] = (self.rest_local[b.name].inverted()
                           @ parent.inverted() @ posed[b.name])
        return out

    def carried(self, posed, bone_name, rest_point):
        """Where a rest-space point rides to when `bone_name` is posed."""
        return posed[bone_name] @ self.rest[bone_name].inverted() @ rest_point

    def com(self, posed):
        total, acc = 0.0, Vector((0.0, 0.0, 0.0))
        for name, (s, w) in self.com_terms.items():
            m = posed[name] @ self.rest[name].inverted()
            acc += m.to_3x3() @ s + m.translation * w
            total += w
        return acc / total if total > 0 else acc

    # ------------------------------------------------------------ axial
    def bend_axial(self, translation, angles_deg):
        """Overrides for the axial chain: moved by `translation`, each segment
        pitched by its own world angle about the lateral axis.

        `angles_deg[i]` is the TOTAL pitch of axial bone i, not an increment -
        which is what makes "keep the head level" a one-number request.
        Positive pitches the head end forward (upright) or down (horizontal).
        """
        bm = self.bm
        names = bm["axial"]
        joints = bm["axial_joints"]
        n = len(names)
        if n == 0:
            return {}
        p = bm["pelvis_index"]
        rots = [Matrix.Rotation(math.radians(a), 3, bm["lat"]) for a in angles_deg]
        new = [None] * n
        new[p] = joints[p] + translation
        for k in range(p, n - 1):
            new[k + 1] = new[k] + rots[k] @ (joints[k + 1] - joints[k])
        for k in range(p, 0, -1):
            new[k - 1] = new[k] - rots[k - 1] @ (joints[k] - joints[k - 1])
        out = {}
        for k, name in enumerate(names):
            out[name] = (Matrix.Translation(new[k]) @ rots[k].to_4x4()
                         @ Matrix.Translation(-joints[k]) @ self.rest[name])
        return out

    # -------------------------------------------------------------- IK
    def pole(self, posed, limb, d=None, override=None):
        """The direction this limb's mid-joint should point, this frame."""
        if override is not None:
            return override
        attach = limb["attach"]
        if attach:
            rot = posed[attach].to_3x3() @ self.rest[attach].to_3x3().inverted()
        else:
            rot = Matrix.Identity(3)
        dev = rot @ limb["rest_dev"]
        default = rot @ limb["default_pole"]
        if limb["pole_source"] == "rest shape":
            return dev
        # A near-straight limb: start exactly on the rest shape so frame one
        # reproduces rest, and hand over to the role default as it folds.
        d_rest = (limb["rest_eff"] - limb["rest_root"]).length
        w = 1.0 if d is None else max(0.0, min(1.0, 3.0 * (1.0 - d / max(d_rest, 1e-9))))
        v = dev + default * (d_rest * w)
        return v if v.length > 1e-9 else default

    def solve_limb(self, posed, limb, target, end_rotation=None, pole=None,
                   pole_weight=1.0, end_weight=1.0):
        """Overrides putting `limb`'s effector (ankle / wrist) on `target`.

        `end_rotation` is the end bone's armature-space rotation relative to
        rest - identity keeps a planted foot exactly as it rests. None lets the
        end follow the lower segment.

        `pole` asks the mid-joint to point somewhere other than its natural
        bend; `pole_weight` blends from the automatic pole (0) to it (1). Blend
        rather than switching, or frame one stops being rest - the automatic
        pole depends on how folded the limb is, which only this call knows.
        """
        up_n, lo_n, end_n = limb["upper"], limb["lower"], limb["end"]
        a, b = limb["a"], limb["b"]
        root = posed[up_n].translation.copy()
        span = target - root
        d_want = span.length
        u = span.normalized() if d_want > 1e-9 else -self.bm["up_vec"]
        # The clamp margin sets how far a dead-straight limb is bent when aimed
        # at its own rest effector: the triangle height grows as sqrt(margin),
        # so 1e-6 bent a straight hexapod arm by 0.4 degrees at rest.
        d_min, d_max = abs(a - b) + 1e-9, (a + b) * (1.0 - 1e-10)
        d = max(d_min, min(d_max, d_want))
        clamped = d_want > d_max * (1.0 + 1e-4) or d_want < d_min * (1.0 - 1e-4)

        pv = self.pole(posed, limb, d=d)
        if pole is not None:
            w = max(0.0, min(1.0, pole_weight))
            auto = pv.normalized() if pv.length > 1e-12 else pole.normalized()
            pv = auto.lerp(pole.normalized(), w)
            if pv.length < 1e-9:
                pv = pole.normalized()
        perp = pv - u * pv.dot(u)
        if perp.length < 1e-9:
            alt = self.bm["fwd"] if abs(u.dot(self.bm["fwd"])) < 0.9 else self.bm["up_vec"]
            perp = alt - u * alt.dot(u)
        perp.normalize()

        x = (a * a - b * b + d * d) / (2.0 * d)
        h = math.sqrt(max(a * a - x * x, 0.0))
        mid = root + u * x + perp * h
        eff = root + u * d

        # rest frame of the same triangle, built with the same pole rule
        r_root, r_mid, r_eff = limb["rest_root"], limb["rest_mid"], limb["rest_eff"]
        r_span = r_eff - r_root
        r_u = r_span.normalized()
        r_pv = limb["rest_dev"] if limb["rest_dev"].length > 1e-9 else limb["default_pole"]
        r_perp = r_pv - r_u * r_pv.dot(r_u)
        if r_perp.length < 1e-9:
            alt = self.bm["fwd"] if abs(r_u.dot(self.bm["fwd"])) < 0.9 else self.bm["up_vec"]
            r_perp = alt - r_u * alt.dot(r_u)
        r_n = r_u.cross(r_perp).normalized()
        n = u.cross(perp).normalized()

        def carry(rest_dir, new_dir):
            # the rotation taking the rest (aim, normal) frame onto the new one
            return _frame(new_dir, n) @ _frame(rest_dir, r_n).transposed()

        out = {}
        r_up = carry(r_mid - r_root, mid - root)
        out[up_n] = (Matrix.Translation(root) @ r_up.to_4x4()
                     @ Matrix.Translation(-r_root) @ self.rest[up_n])
        r_lo = carry(r_eff - r_mid, eff - mid)
        out[lo_n] = (Matrix.Translation(mid) @ r_lo.to_4x4()
                     @ Matrix.Translation(-r_mid) @ self.rest[lo_n])
        if end_n and end_rotation is not None:
            rot = end_rotation
            if end_weight < 1.0:
                # Part way between following the shin and holding a planted
                # orientation: a foot coming down onto the floor, or lifting off
                # it. Switching outright would snap the foot in one frame.
                follow = (out[lo_n] @ self.rest_local[end_n]).to_3x3() \
                    @ self.rest[end_n].to_3x3().inverted()
                rot = follow.to_quaternion().slerp(
                    end_rotation.to_quaternion(), max(0.0, end_weight)).to_matrix()
            out[end_n] = (Matrix.Translation(eff) @ rot.to_4x4()
                          @ Matrix.Translation(-r_eff) @ self.rest[end_n])

        fold = math.degrees((mid - root).angle(eff - mid)) if h > 0 else 0.0
        info = {
            "reach": d_want / (a + b),
            "clamped": clamped,
            "knee_angle": 180.0 - fold,      # included angle; 180 = straight
            "pole": perp.copy(),
        }
        return out, info


def _frame(direction, normal):
    """Orthonormal basis (columns) from an aim direction and a plane normal."""
    y = direction.normalized()
    z = normal - y * normal.dot(y)
    z.normalize()
    x = y.cross(z)
    m = Matrix.Identity(3)
    for i in range(3):
        m[i][0], m[i][1], m[i][2] = x[i], y[i], z[i]
    return m


def _com_terms(rig):
    """Per-bone mass terms from the skin, so COM follows linear blend skinning
    exactly: sum_b w_b (P_b R_b^-1) v is affine in each bone's matrix."""
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and any(
        m.type == "ARMATURE" and m.object == rig for m in o.modifiers)]
    terms = {}
    to_arm = rig.matrix_world.inverted()
    for o in meshes:
        groups = {g.index: g.name for g in o.vertex_groups
                  if g.name in rig.data.bones and rig.data.bones[g.name].use_deform}
        m = to_arm @ o.matrix_world
        for v in o.data.vertices:
            ws = [(groups[g.group], g.weight) for g in v.groups
                  if g.group in groups and g.weight > 0.0]
            tot = sum(w for _, w in ws)
            if tot <= 0.0:
                continue
            co = m @ v.co
            for name, w in ws:
                s, wt = terms.get(name, (Vector((0.0, 0.0, 0.0)), 0.0))
                terms[name] = (s + co * (w / tot), wt + w / tot)
    if terms:
        return terms, "skin (%d meshes)" % len(meshes)
    # no skin: bone midpoints weighted by length
    for b in rig.data.bones:
        mid = (b.head_local + b.tail_local) * 0.5
        terms[b.name] = (mid * b.length, b.length)
    return terms, "bone lengths (no skinned mesh found)"


# --------------------------------------------------------------------------
# baking and playback
# --------------------------------------------------------------------------

def bake(body, action, frames_posed, interpolation="LINEAR"):
    """Write one key per bone per frame from predicted armature matrices."""
    rig = body.rig
    rig.animation_data.action = action
    last_q = {}
    for frame, posed in frames_posed:
        basis = body.basis(posed)
        for b in body.bones:
            pb = rig.pose.bones[b.name]
            loc, q, _ = basis[b.name].decompose()
            prev = last_q.get(b.name)
            if prev is not None and prev.dot(q) < 0.0:
                q.negate()           # stay on one hemisphere or LINEAR flips
            last_q[b.name] = q
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = q
            pb.keyframe_insert("rotation_quaternion", frame=frame)
            if not b.use_connect:
                pb.location = loc
                pb.keyframe_insert("location", frame=frame)
    for fc in _fcurves(action):
        for kp in fc.keyframe_points:
            kp.interpolation = interpolation


def _fcurves(action):
    out = []
    for layer in getattr(action, "layers", []) or []:
        for strip in layer.strips:
            for cb in getattr(strip, "channelbags", []):
                out.extend(cb.fcurves)
    return out or list(getattr(action, "fcurves", []))


def evaluate(body, action, frames_posed):
    """Play the baked clip through Blender; return what it actually did.

    The result carries each frame's evaluated armature-space matrices so the
    action-specific checks measure Blender's pose, not this module's opinion
    of it.
    """
    rig = body.rig
    scene = bpy.context.scene
    verify.repair_evaluation(rig)
    binding = verify.bind_action(rig, action)
    if not binding["bound"]:
        return {"error": binding["note"], "binding": binding}

    worst, worst_at = 0.0, None
    evaluated = {}
    skin_lowest = {}
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and any(
        m.type == "ARMATURE" and m.object == rig for m in o.modifiers)]
    up = body.bm["up"]
    uidx = {"X": 0, "Y": 1, "Z": 2}[up[-1].upper()]
    usign = -1.0 if up.startswith("-") else 1.0
    for frame, posed in frames_posed:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        if meshes:
            dg = bpy.context.evaluated_depsgraph_get()
            low = float("inf")
            for o in meshes:
                ev_obj = o.evaluated_get(dg)
                me = ev_obj.to_mesh()
                mw = o.matrix_world
                low = min(low, min((mw @ v.co)[uidx] * usign for v in me.vertices))
                ev_obj.to_mesh_clear()
            skin_lowest[frame] = low
        mats = {}
        for b in body.bones:
            pb = rig.pose.bones[b.name]
            mats[b.name] = pb.matrix.copy()
            pred = posed[b.name]
            err = max((pb.head - pred.translation).length,
                      (pb.tail - pred @ Vector((0.0, b.length, 0.0))).length)
            if err > worst:
                worst, worst_at = err, (frame, b.name)
        evaluated[frame] = mats
    return {"binding": binding, "prediction_error": worst,
            "prediction_worst": worst_at, "evaluated": evaluated,
            "skin_lowest": skin_lowest}


def tail_of(body, mats, bone):
    return mats[bone] @ Vector((0.0, body.rig.data.bones[bone].length, 0.0))
