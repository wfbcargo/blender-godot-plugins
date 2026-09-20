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

    def skin_lowest(self, posed, up_world):
        """Lowest point of the linear-blend-skinned mesh for a predicted pose,
        as a world height. Lets a pose be solved against the floor before it is
        baked, rather than found through it afterwards."""
        if not hasattr(self, "_skin"):
            self._skin = []
            to_arm = self.rig.matrix_world.inverted()
            for o in bpy.data.objects:
                if o.type != "MESH" or not any(m.type == "ARMATURE" and m.object == self.rig
                                               for m in o.modifiers):
                    continue
                groups = {g.index: g.name for g in o.vertex_groups
                          if g.name in self.rest}
                m = to_arm @ o.matrix_world
                for v in o.data.vertices:
                    ws = [(groups[g.group], g.weight) for g in v.groups
                          if g.group in groups and g.weight > 0.0]
                    tot = sum(w for _, w in ws)
                    if tot > 0:
                        self._skin.append((m @ v.co, [(n, w / tot) for n, w in ws]))
        if not self._skin:
            return None
        mw = self.rig.matrix_world
        deform = {n: posed[n] @ self.rest[n].inverted() for n in self.rest}
        low = float("inf")
        for co, ws in self._skin:
            p = Vector((0.0, 0.0, 0.0))
            for n, w in ws:
                p += (deform[n] @ co) * w
            low = min(low, (mw @ p).dot(up_world))
        return low

    def skinned_bones(self):
        """Names of the bones that move any skin, or None when no mesh is bound.

        A bone nothing is weighted to is a control, not body: MPFB's `root` sits
        at the pelvis and dips 3-7 cm under the floor as the hips drop, while the
        skin it would have to drag through the floor does not exist."""
        self.skin_lowest(self.fk(), self._world_up())      # builds the vertex cache
        if not self._skin:
            return None
        return {n for _, ws in self._skin for n, _ in ws}

    def body_bones(self):
        """The bones that stand for the body in a floor test: every bone but the
        body map's `roles["controls"]`, in FK order.

        With no skin to read there are no controls and every bone stands in.
        A body map without roles (`radial.body_map` builds its own) falls back
        to `skinned_bones`. The two differ on an unskinned bone that is on a
        limb or the axial chain but not the root - the Rigify sample Figure's
        hands carry no skin and are still hands - and the role is the intent:
        a control is what is excluded, not whatever lacks weight.

        Bones the body map leaves to their own module - maw, fin, radial and
        tentacle bones, and bones other plugins added - have no roles, so they
        keep the skin rule: an unskinned one (a maw's mouth socket) is not body."""
        roles = self.bm.get("roles")
        skinned = self.skinned_bones()
        if roles is None:
            return [b for b in self.bones if skinned is None or b.name in skinned] or self.bones
        controls = set(roles["controls"])
        if skinned is not None:
            own = set()
            for key in ("maw_bones", "fin_bones", "radial_bones", "tentacle_bones", "added_bones"):
                own.update(self.bm.get(key) or ())
            controls.update(n for n in own if n not in skinned)
        return [b for b in self.bones if b.name not in controls] or self.bones

    def com(self, posed):
        total, acc = 0.0, Vector((0.0, 0.0, 0.0))
        for name, (s, w) in self.com_terms.items():
            m = posed[name] @ self.rest[name].inverted()
            acc += m.to_3x3() @ s + m.translation * w
            total += w
        return acc / total if total > 0 else acc

    # ------------------------------------------------------- floor contact
    def _world_up(self):
        from . import bodymap
        return bodymap.axis_vector(self.bm["up"])

    def chain_skin(self, entries):
        """Skin measurements for a chain of bones that can meet the floor.

        `entries` are (bone, base_rest, tip_rest). Returns a dict per bone:
        `underside` - how far the skin it dominates hangs below its bone line -
        and `rest_bottom`, the lowest that skin sits at rest (world height).
        A tail or a toe meets the floor by its skin, not its bone.
        """
        key = tuple(e[0] for e in entries)
        cache = self.__dict__.setdefault("_chain_skin", {})
        if key in cache:
            return cache[key]
        upw = self._world_up()
        mw = self.rig.matrix_world
        out = {e[0]: {"underside": 0.0, "rest_bottom": None} for e in entries}
        spans = {e[0]: (e[1], e[2]) for e in entries}
        self.skin_lowest(self.fk(), upw)                   # builds the vertex cache
        for co, ws in self._skin:
            top = max(ws, key=lambda nw: nw[1])[0]
            if top not in spans:
                continue
            b, t = spans[top]
            seg = t - b
            u = max(0.0, min(1.0, (co - b).dot(seg) / max(seg.dot(seg), 1e-12)))
            h = (mw @ co).dot(upw)
            o = out[top]
            o["underside"] = max(o["underside"], (mw @ (b + seg * u)).dot(upw) - h)
            o["rest_bottom"] = h if o["rest_bottom"] is None else min(o["rest_bottom"], h)
        cache[key] = out
        return out

    def drape_chain(self, entries, base, rotations, floor=0.0, clearance=0.0):
        """Lay a chain along the floor wherever it would pass through it.

        `entries` are (bone, base_rest, tip_rest) base to tip, `base` where the
        chain starts now, `rotations[i]` the rotation each bone would take
        before any floor contact. Any bone whose skin would go below the floor
        swings up about its base until it lies on it - a rope, not a rod - and
        the next bone starts from where that one ended.

        A bone may still lie as low as it rested, or a body authored touching
        the ground would be lifted off it on frame one.
        """
        skin = self.chain_skin(entries)
        upw = self._world_up()
        up_a = self.bm["up_vec"]
        mw = self.rig.matrix_world
        out = {}

        def height(p):
            return (mw @ p).dot(upw) - floor

        for (name, b_rest, t_rest), rot in zip(entries, rotations):
            sk = skin[name]
            allowed = clearance if sk["rest_bottom"] is None else                 min(clearance, sk["rest_bottom"] - floor)
            need = allowed + sk["underside"]
            d = rot @ (t_rest - b_rest)
            if height(base + d) < need:
                length = d.length
                vert = max(-length, min(length, need - height(base)))
                horiz = d - up_a * d.dot(up_a)
                if horiz.length < 1e-9:
                    horiz = -self.bm["fwd"]
                d_new = horiz.normalized() * math.sqrt(max(length * length - vert * vert, 0.0))                     + up_a * vert
                rot = d.rotation_difference(d_new).to_matrix() @ rot
                d = d_new
            out[name] = (Matrix.Translation(base) @ rot.to_4x4()
                         @ Matrix.Translation(-b_rest) @ self.rest[name])
            base = base + d
        return out

    def tail_chain(self):
        """[(bone, base_rest, tip_rest)] for the body map's tail, base to tip."""
        names, joints = self.bm["axial"], self.bm["axial_joints"]
        chain = []
        for n in self.bm.get("tail", []):
            k = names.index(n)
            chain.append((n, joints[k + 1] if k + 1 < len(joints) else joints[k], joints[k]))
        return chain

    def pose_tail(self, posed, lift_deg=0.0, sway_deg=0.0, floor=0.0, clearance=0.0):
        """Overrides for the tail: ride the pelvis, curl, sway, then drape.

        The tail starts wherever the axial bend left its base. Each bone adds an
        equal share of `lift_deg` (tip up) and `sway_deg` (tip to the side), so
        a tail curls rather than pivoting as a stick, and then lies along the
        floor wherever it would otherwise pass into it.
        """
        chain = self.tail_chain()
        if not chain:
            return {}
        first = chain[0][0]
        carried = posed[first].to_3x3() @ self.rest[first].to_3x3().inverted()
        n = len(chain)
        rots = [Matrix.Rotation(math.radians(sway_deg * (i + 1) / n), 3, self.bm["up_vec"])
                @ Matrix.Rotation(math.radians(lift_deg * (i + 1) / n), 3, self.bm["lat"])
                @ carried for i in range(n)]
        return self.drape_chain(chain, self.carried(posed, first, chain[0][1]), rots,
                                floor=floor, clearance=clearance)

    def turn_bone(self, posed, name, lat_deg=0.0, fwd_deg=0.0, up_deg=0.0):
        """Override turning ONE bone about its own posed head, by totals about
        the body map's axes - never about the bone's own.

        For a bone that hangs off the axial chain rather than sitting on it, so
        `bend_axial` cannot reach it: a shoulder girdle, which carries the whole
        arm. What the bone carries follows on the next `fk`, because `fk` walks
        the hierarchy and derives a child from its posed parent.

        Totals, like `bend_axial`'s, and in its order - pitch about `lat`, then
        roll about `fwd`, then yaw about `up_vec` - so a caller that knows one
        knows the other. Which side a positive value lifts or brings forward is
        `axis_turns`, not a convention to be remembered here.
        """
        if name not in posed or not (lat_deg or fwd_deg or up_deg):
            return {}
        bm = self.bm
        r = Matrix.Identity(3)
        if lat_deg:
            r = Matrix.Rotation(math.radians(lat_deg), 3, bm["lat"]) @ r
        if fwd_deg:
            r = Matrix.Rotation(math.radians(fwd_deg), 3, bm["fwd"]) @ r
        if up_deg:
            r = Matrix.Rotation(math.radians(up_deg), 3, bm["up_vec"]) @ r
        head = posed[name].translation.copy()
        turn = (Matrix.Translation(head) @ r.to_4x4()
                @ Matrix.Translation(-head))
        return {name: turn @ posed[name]}

    def drape_digits(self, posed, limb, floor=0.0, clearance=0.0):
        """Toes lie on the floor rather than pointing into it."""
        if not limb["digits"] or not limb["end"]:
            return {}
        bones = self.rig.data.bones
        chain = [(d, bones[d].head_local.copy(), bones[d].tail_local.copy())
                 for d in limb["digits"]]
        rots = [posed[d].to_3x3() @ self.rest[d].to_3x3().inverted() for d in limb["digits"]]
        base = posed[limb["end"]] @ Vector((0.0, bones[limb["end"]].length, 0.0))
        return self.drape_chain(chain, base, rots, floor=floor, clearance=clearance)

    def lay_on_floor(self, posed, bone_name, floor=0.0, clearance=0.0):
        """Overrides turning one bone about its head - the least angle, either way
        - until the skin it dominates lies on the floor rather than through it.
        {} when that skin is already clear. What the bone carries turns with it.

        For a foot in the air. `drape_chain` models a bone's skin as a rod hanging
        a fixed `underside` below the bone line, measured at rest, which suits a
        tail or a toe lying along the floor. A foot bone slopes from the ankle down
        to the ball with the heel pad under its top end: its rest underside is the
        heel's 4.4 cm on a Rigify biped, and a rod that deep lifted the ball 4.5 cm
        clear the moment a slide's foot left the floor - its toe tip jumped 12 cm
        in one frame. Here the skin is the skin: each vertex is skinned exactly
        with the turned bone, as the ball comes up the heel goes down, and the turn
        stops where the lowest of them rests. A bone no skin is weighted to lays
        its own head and tail instead. The allowance is the rest pose's own lowest
        skin, as everywhere, so a foot authored on the ground is not lifted off it.
        """
        import numpy as np
        rig_bones = self.rig.data.bones
        cache = self.__dict__.setdefault("_lay_skin", {})
        if bone_name not in cache:
            self.skin_lowest(self.fk(), self._world_up())      # builds the vertex cache
            carried, stack = set(), [rig_bones[bone_name]]
            while stack:
                b = stack.pop()
                carried.add(b.name)
                stack.extend(b.children)
            verts = [(co, ws) for co, ws in (self._skin or [])
                     if max(ws, key=lambda nw: nw[1])[0] == bone_name]
            if not verts:
                b = rig_bones[bone_name]
                verts = [(b.head_local.copy(), [(bone_name, 1.0)]),
                         (b.tail_local.copy(), [(bone_name, 1.0)])]
            cache[bone_name] = (carried, verts)
        carried, verts = cache[bone_name]
        mw = self.rig.matrix_world
        upw = self._world_up()
        g = mw.to_3x3().transposed() @ upw          # height = p . g + h0, armature space
        h0 = mw.translation.dot(upw) - floor
        rest_low = min(co.dot(g) for co, _ in verts) + h0
        allowed = min(clearance, rest_low)

        names = {n for _, ws in verts for n, _ in ws}
        deform = {n: posed[n] @ self.rest[n].inverted() for n in names}
        head = posed[bone_name].translation.copy()
        tip = posed[bone_name] @ Vector((0.0, rig_bones[bone_name].length, 0.0))
        axis = (tip - head).cross(self.bm["up_vec"])
        if axis.length < 1e-9:
            axis = self.bm["lat"].copy()
        axis.normalize()
        # A vertex's height as the bone turns by t about `axis` through its head:
        # a cos t + b sin t + c (Rodrigues, the turned share of its weight only).
        kg = axis.dot(g)
        a, b, c = [], [], []
        for co, ws in verts:
            moved, fixed, share = Vector(), Vector(), 0.0
            for n, w in ws:
                p = (deform[n] @ co) * w
                if n in carried:
                    moved += p
                    share += w
                else:
                    fixed += p
            u = moved - head * share
            ku = axis.dot(u)
            a.append(u.dot(g) - ku * kg)
            b.append(axis.cross(u).dot(g))
            c.append((fixed + head * share).dot(g) + h0 + ku * kg)
        a, b, c = np.array(a), np.array(b), np.array(c)

        def low(t):
            return float(np.min(a * math.cos(t) + b * math.sin(t) + c))

        if low(0.0) >= allowed - 1e-7:
            return {}
        step = math.radians(1.0)
        found, best = None, (low(0.0), 0.0)
        for i in range(1, 91):
            for t in (i * step, -i * step):
                h = low(t)
                if h >= allowed:
                    found = t
                    break
                if h > best[0]:
                    best = (h, t)
            if found is not None:
                break
        if found is None:
            t = best[1]                                   # as near as turning gets it
        else:
            lo, hi = found - math.copysign(step, found), found      # lo through, hi clear
            for _ in range(20):
                mid = 0.5 * (lo + hi)
                if low(mid) >= allowed:
                    hi = mid
                else:
                    lo = mid
            t = hi
        if t == 0.0:
            return {}
        turn = (Matrix.Translation(head) @ Matrix.Rotation(t, 4, axis)
                @ Matrix.Translation(-head))
        return {bone_name: turn @ posed[bone_name]}

    def limb_skin_lowest(self, posed, bone_names):
        """(lowest posed height, lowest rest height) of the skin a set of bones
        dominates - to hold a planted limb's own skin above the floor."""
        upw = self._world_up()
        self.skin_lowest(self.fk(), upw)
        names = set(bone_names)
        mw = self.rig.matrix_world
        deform = {n: posed[n] @ self.rest[n].inverted() for n in self.rest}
        low = rest_low = None
        for co, ws in self._skin:
            if max(ws, key=lambda nw: nw[1])[0] not in names:
                continue
            p = Vector((0.0, 0.0, 0.0))
            for n, w in ws:
                p += (deform[n] @ co) * w
            h, r = (mw @ p).dot(upw), (mw @ co).dot(upw)
            low = h if low is None else min(low, h)
            rest_low = r if rest_low is None else min(rest_low, r)
        return low, rest_low

    # ------------------------------------------------------------ axial
    def bend_axial(self, translation, angles_deg, yaw_deg=None, roll_deg=None):
        """Overrides for the axial chain: moved by `translation`, each segment
        pitched by its own world angle about the lateral axis, then rolled about
        the forward axis and turned about the up axis.

        `angles_deg[i]` is the TOTAL pitch of axial bone i, not an increment -
        which is what makes "keep the head level" a one-number request.
        Positive pitches the head end forward (upright) or down (horizontal).
        `yaw_deg[i]` and `roll_deg[i]` are totals too, so a head that holds its
        orientation while the chest turns under it is a zero. Both are
        right-handed about the body map's `up_vec` and `fwd`, never a bone's
        axis; a caller that needs to know which side a positive value brings
        forward (or up) asks `axis_turns` rather than assuming it.
        """
        bm = self.bm
        names = bm["axial"]
        joints = bm["axial_joints"]
        n = len(names)
        if n == 0:
            return {}
        p = bm["pelvis_index"]
        rots = []
        for i, a in enumerate(angles_deg):
            r = Matrix.Rotation(math.radians(a), 3, bm["lat"])
            if roll_deg is not None and roll_deg[i]:
                r = Matrix.Rotation(math.radians(roll_deg[i]), 3, bm["fwd"]) @ r
            if yaw_deg is not None and yaw_deg[i]:
                r = Matrix.Rotation(math.radians(yaw_deg[i]), 3, bm["up_vec"]) @ r
            rots.append(r)
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

    def axis_turns(self, axis, point, toward):
        """+1 when a small positive rotation about `axis` (the body map's
        `up_vec`, `fwd` or `lat`) moves `point` - relative to the axis through
        the origin - toward `toward`, -1 when away. How a caller gets a sense
        for a yaw or roll without reading any sign convention."""
        return 1.0 if axis.cross(point).dot(toward) >= 0.0 else -1.0

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
