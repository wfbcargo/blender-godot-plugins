"""Whole-body actions built on the body map: crouch first.

Each action is described in BODY-RELATIVE terms - fractions of leg length,
pitches of the axial chain, hand targets relative to the shoulder - so one
description fits a humanoid, a quadruped and a hexapod. The map supplies the
parts, `motion` turns targets into keys, and every clip is played back through
Blender and checked before it is reported as done.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Vector

from . import bodymap, gait, motion, verify


def _support(body, legs):
    """Forward extent of what the planted legs stand on, rest space."""
    fwd = body.bm["fwd"]
    rig = body.rig
    coords = []
    for l in legs:
        for n in [l["end"]] + l["digits"] if l["end"] else [l["lower"]]:
            b = rig.data.bones[n]
            coords += [b.head_local.dot(fwd), b.tail_local.dot(fwd)]
    return min(coords), max(coords)


def lean_angles(bm, lean, head_level):
    """Total pitch per axial bone for a torso leaning `lean` degrees.

    The pelvis takes half, the torso ramps to the full lean by its top, and the
    neck and head hand `head_level` of it back so the creature keeps looking
    where it was looking. Positive leans forward, negative back. Bones behind
    the pelvis ride with it.
    """
    n = len(bm["axial"])
    a = [0.0] * n
    if lean == 0.0 or n == 0:
        return a
    p = bm["pelvis_index"]
    torso_idx = [bm["axial"].index(x) for x in bm["torso"]]
    neck_idx = [bm["axial"].index(x) for x in bm["neck"]]
    head_idx = bm["axial"].index(bm["head"]) if bm["head"] else None
    pelvis = 0.5 * lean
    for i in range(n):
        a[i] = pelvis
    if torso_idx:
        last = max(torso_idx)
        for i in torso_idx:
            f = (i - p) / max(last - p, 1)
            a[i] = pelvis + (lean - pelvis) * f
        for i in range(last + 1, n):
            a[i] = lean
    tail_end = sorted(neck_idx + ([head_idx] if head_idx is not None else []))
    for k, i in enumerate(tail_end):
        f = (k + 1) / float(len(tail_end))
        a[i] = lean * (1.0 - head_level * f)
    return a


def _leg_drop_room(bm, leg, fold_limit):
    """How far the hip can drop straight down before this leg folds past
    `fold_limit` of its full length. Splayed legs lose less length per unit of
    drop than vertical ones, so it is solved, not assumed."""
    up = bm["up_vec"]
    span = leg["rest_root"] - leg["rest_eff"]
    vert = span.dot(up)
    horiz2 = max(span.length_squared - vert * vert, 0.0)
    shortest = max(abs(leg["a"] - leg["b"]), fold_limit * (leg["a"] + leg["b"]))
    return vert - math.sqrt(max(shortest * shortest - horiz2, 0.0))


def crouch(rig_name, depth=0.6, frames=12, forward="-Y", up="Z", floor=0.0,
           action_name="Crouch", lean_degrees=None, head_level=0.8,
           arms_forward=True, fold_limit=0.45, fps=None):
    """Author a one-shot crouch that ends held low, feet planted throughout.

    depth         0 stands, 1 folds the most-constrained leg to `fold_limit` of
                  its length (or puts the belly near the floor, if sooner)
    lean_degrees  total forward pitch of the torso at full depth. Defaults to
                  45 for an upright body, 0 for a horizontal one
    head_level    how much of that lean the neck and head take back out, so
                  the creature keeps looking where it was looking

    The hips are then moved fore/aft until the skinned centre of mass sits over
    the feet. On a biped that is what pushes the hips back as the knees come
    forward; on a quadruped the mass is already inside a wide support and
    nothing moves. The same rule, not a special case.

    Stand back up in the engine by playing the clip backwards.
    """
    bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return bm
    rig = bpy.data.objects[rig_name]
    legs = [l for l in bm["limbs"] if l["role"] == "leg" and l["axial_index"] is not None]
    if not legs:
        return {"error": "%s has no legs to crouch on - nothing holds it off the "
                         "ground, so there is nothing to fold" % rig_name,
                "bodymap": bodymap.summary(bm)}
    if len(bm["axial"]) == 0:
        return {"error": "no axial chain", "bodymap": bodymap.summary(bm)}

    body = motion.Body(rig, bm)
    upv, fwd = bm["up_vec"], bm["fwd"]
    upright = bm["upright"]
    lean = (45.0 if upright else 0.0) if lean_degrees is None else lean_degrees
    n_axial = len(bm["axial"])
    # ---- how low can it go
    room = min(_leg_drop_room(bm, l, fold_limit) for l in legs)
    axial_pts = [pt for n in bm["axial"]
                 for pt in (rig.data.bones[n].head_local, rig.data.bones[n].tail_local)]
    lowest_axial = min((rig.matrix_world @ pt).dot(bodymap.axis_vector(up)) - floor
                       for pt in axial_pts)
    belly = lowest_axial - 0.08 * bm["height"]
    max_drop = max(0.0, min(room, belly))
    drop = depth * max_drop

    def angles(s):
        return lean_angles(bm, lean * s, head_level)

    free =[l for l in bm["limbs"] if l["role"] == "arm" and l["axial_index"] is not None]

    def pose(s, shift):
        infos = {}
        axial = body.bend_axial(-upv * (drop * s) + fwd * (shift * s), angles(s))
        posed = body.fk(axial)
        overrides = dict(axial)
        for l in legs:
            ov, info = body.solve_limb(posed, l, l["rest_eff"].copy(),
                                       end_rotation=Matrix.Identity(3))
            overrides.update(ov)
            infos[l["name"]] = info
        if upright and arms_forward:
            for l in free:
                shoulder = posed[l["upper"]].translation
                reach = l["a"] + l["b"]
                rest_eff = body.carried(posed, l["attach"], l["rest_eff"])
                lateral = (rest_eff - shoulder).dot(bm["lat"])
                goal = (shoulder + fwd * (0.6 * reach) - upv * (0.55 * reach)
                        + bm["lat"] * lateral)
                target = rest_eff.lerp(goal, s)
                ov, info = body.solve_limb(posed, l, target)
                overrides.update(ov)
                infos[l["name"]] = info
        return body.fk(overrides), infos

    # ---- balance: slide the hips until the centre of mass is over the feet
    lo, hi = _support(body, legs)
    centre, half = (lo + hi) * 0.5, (hi - lo) * 0.5
    band = (centre - 0.3 * half, centre + 0.3 * half)

    def com_fwd(shift):
        return body.com(pose(1.0, shift)[0]).dot(fwd)

    shift = 0.0
    c0 = com_fwd(0.0)
    if not band[0] <= c0 <= band[1]:
        goal = band[0] if c0 < band[0] else band[1]
        x0, f0 = 0.0, c0 - goal
        x1 = -f0
        f1 = com_fwd(x1) - goal
        for _ in range(6):
            if abs(f1) < 1e-5 or abs(f1 - f0) < 1e-12:
                break
            x0, x1, f0 = x1, x1 - f1 * (x1 - x0) / (f1 - f0), f1
            f1 = com_fwd(x1) - goal
        shift = x1

    # ---- author
    scene = bpy.context.scene
    if fps:
        scene.render.fps = fps
    snap = verify._snapshot(rig)
    ad = rig.animation_data or rig.animation_data_create()
    prev_action = ad.action
    prev_frame = scene.frame_current

    frames = max(2, int(frames))
    keyed, infos_by_frame = [], {}
    for f in range(1, frames + 1):
        smooth = motion.smoothstep((f - 1) / float(frames - 1))
        posed, infos = pose(smooth, shift)
        keyed.append((f, posed))
        infos_by_frame[f] = infos

    action = gait._fresh_action(rig, action_name)
    try:
        motion.bake(body, action, keyed)
        ev = motion.evaluate(body, action, keyed)
        if "error" in ev:
            return {"error": ev["error"], "action": action.name}
        report = _check_common(body, bm, keyed, ev, infos_by_frame,
                               planted=legs, posed_limbs=legs + free,
                               support=(lo, hi), rest_floor=floor)
    finally:
        scene.frame_set(prev_frame)
        if prev_action is not None:
            verify.bind_action(rig, prev_action)
        else:
            ad.action = None
        verify._restore(rig, snap)

    report.update({
        "rig": rig_name,
        "action": action.name,
        "frames": [1, frames],
        "fps": scene.render.fps,
        "depth": depth,
        "hip_drop_m": round(drop, 4),
        "max_drop_m": round(max_drop, 4),
        "drop_limited_by": "legs" if room <= belly else "belly clearance",
        "lean_degrees": lean,
        "hip_shift_m": round(shift, 4),
        "upright": upright,
        "com_source": body.com_source,
        "crouched_height_m": report["end_height_m"],
    })
    return report


def slide(rig_name, frames=10, forward="-Y", up="Z", floor=0.0, action_name="Slide",
          lead="L", hip_height=0.36, lean_degrees=-35.0, head_level=0.85, fps=None):
    """Author a one-shot baseball slide that ends held low.

    From standing, over `frames`, into: hips dropped to `hip_height` of leg
    length, lead leg straight out along the ground toes up, trail leg tucked
    with its knee turned OUT (turned down, a knee that tight would go through
    the floor), torso leaning back, head still looking ahead, the trail-side
    hand reaching back to the ground and the other forward.

    Nothing is planted - a slide travels - so the checks are reach, fold, bend
    direction, bones and SKIN against the floor. Travel is the engine's job;
    the clip is authored in place, like every other clip here.

    Upright bipeds only. A slide is a biped move, and inventing one for a
    quadruped would be a different action wearing this one's name.
    """
    bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return bm
    rig = bpy.data.objects[rig_name]
    legs = [l for l in bm["limbs"] if l["role"] == "leg" and l["axial_index"] is not None]
    arms = [l for l in bm["limbs"] if l["role"] == "arm" and l["axial_index"] is not None]
    if not bm["upright"] or len(legs) != 2:
        return {"error": "slide is authored for upright bipeds; %s is %s with %d legs"
                         % (rig_name, "upright" if bm["upright"] else "horizontal",
                            len(legs)), "bodymap": bodymap.summary(bm)}
    lead_leg = next((l for l in legs if l["side"] == lead), None)
    if lead_leg is None:
        return {"error": "no leg on side %r" % lead}
    trail_leg = next(l for l in legs if l is not lead_leg)

    body = motion.Body(rig, bm)
    upv, fwd, lat = bm["up_vec"], bm["fwd"], bm["lat"]
    mw = rig.matrix_world
    upw = bodymap.axis_vector(up)

    def height(p_arm):
        return (mw @ p_arm).dot(upw) - floor

    leg_len = sum(l["a"] + l["b"] for l in legs) / 2.0
    centre = sum((l["rest_root"] for l in legs), Vector()) / 2.0

    def outward(l, rest_point):
        return lat if (rest_point - centre).dot(lat) > 0.0 else -lat

    hip_rest = sum(height(l["rest_root"]) for l in legs) / 2.0
    ankle_rest = sum(height(l["rest_eff"]) for l in legs) / 2.0
    drop = hip_rest - hip_height * leg_len
    dz = ankle_rest - hip_height * leg_len          # ankle relative to hip, at the end
    lead_reach = 0.96 * leg_len
    lead_fwd = math.sqrt(max(lead_reach ** 2 - dz ** 2, 0.0))

    arm_side = {l["side"]: l for l in arms}
    back_arm = arm_side.get(trail_leg["side"])
    front_arm = arm_side.get(lead_leg["side"])

    poles_last = {}

    def pose(s):
        infos = {}
        axial = body.bend_axial(-upv * (drop * s), lean_angles(bm, lean_degrees * s,
                                                               head_level))
        posed = body.fk(axial)
        overrides = dict(axial)

        # The feet get going before the hips come down. Moving both on the same
        # curve left the lead foot behind a half-dropped pelvis and the middle
        # of the clip read as sitting on a chair.
        s_feet = math.sqrt(s)

        def leg(l, offset, pole):
            hip = posed[l["upper"]].translation
            lateral = (l["rest_eff"] - l["rest_root"]).dot(lat)
            goal = hip + offset + lat * lateral
            target = l["rest_eff"].lerp(goal, s_feet)
            ov, info = body.solve_limb(posed, l, target, pole=pole, pole_weight=s_feet)
            overrides.update(ov)
            infos[l["name"]] = info
            poles_last[l["name"]] = pole

        # Both feet aim along the FLOOR from wherever the hips are now, so the
        # lead leg reaches out as the pelvis drops rather than kicking up.
        hip_now = sum(height(posed[l["upper"]].translation) for l in legs) / 2.0
        dz_now = ankle_rest - hip_now
        fwd_now = math.sqrt(max(lead_reach ** 2 - dz_now ** 2, 0.0))
        leg(lead_leg, fwd * fwd_now + upv * dz_now, (upv + fwd * 0.2).normalized())
        out_t = outward(trail_leg, trail_leg["rest_root"])
        leg(trail_leg, fwd * (0.32 * leg_len * s) + upv * dz_now,
            (out_t + fwd * 0.35 - upv * 0.15).normalized())

        for l, offset in ((back_arm, (-0.35, -0.75, 0.3)),
                          (front_arm, (0.55, 0.15, 0.3))):
            if l is None:
                continue
            shoulder = posed[l["upper"]].translation
            reach = l["a"] + l["b"]
            rest_eff = body.carried(posed, l["attach"], l["rest_eff"])
            goal = shoulder + (fwd * offset[0] + upv * offset[1]
                               + outward(l, l["rest_root"]) * offset[2]) * reach
            ov, info = body.solve_limb(posed, l, rest_eff.lerp(goal, s))
            overrides.update(ov)
            infos[l["name"]] = info
        return body.fk(overrides), infos

    keyed, infos_by_frame, action, report = _author(
        body, rig, action_name, frames, pose, fps,
        lambda keyed, ev, infos: _check_common(
            body, bm, keyed, ev, infos, planted=[], posed_limbs=legs,
            pole_overrides=poles_last, rest_floor=floor))
    if "error" in report:
        return report
    report.update({
        "rig": rig_name, "action": action.name, "frames": [1, len(keyed)],
        "fps": bpy.context.scene.render.fps, "lead": lead,
        "hip_height_m": round(hip_height * leg_len, 4),
        "lean_degrees": lean_degrees,
        "slide_height_m": report["end_height_m"],
    })
    return report


def _evaluated_frame(rig, action_name, frame):
    """Blender's pose at one frame of an existing clip (None = its last), or None."""
    action = bpy.data.actions.get(action_name) if action_name else None
    if action is None:
        return None
    scene = bpy.context.scene
    ad = rig.animation_data or rig.animation_data_create()
    prev, prev_frame = ad.action, scene.frame_current
    snap = verify._snapshot(rig)
    try:
        if not verify.bind_action(rig, action)["bound"]:
            return None
        if frame is None:
            frame = int(action.frame_range[1])
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        return {pb.name: pb.matrix.copy() for pb in rig.pose.bones}
    finally:
        scene.frame_set(prev_frame)
        if prev is not None:
            verify.bind_action(rig, prev)
        else:
            ad.action = None
        verify._restore(rig, snap)


def _pose_gap(rig, a, b):
    """Largest distance between the same bone's head or tail in two poses."""
    worst, at = 0.0, None
    for bone in rig.data.bones:
        tip = Vector((0.0, bone.length, 0.0))
        e = max((a[bone.name].translation - b[bone.name].translation).length,
                ((a[bone.name] @ tip) - (b[bone.name] @ tip)).length)
        if e > worst:
            worst, at = e, bone.name
    return worst, at


def crouch_walk(rig_name, depth=0.6, stride=0.40, lift=0.10, frames=24,
                forward="-Y", up="Z", floor=0.0, action_name="CrouchWalk",
                bob=0.012, sway=0.015, arm_swing=0.10, attempts=5, fps=None):
    """Author a looping walk at crouch height.

    The base is `keyposes.crouch_key(depth)` - exactly the pose the Crouch clip
    ends on - with a gait laid over the feet. `stride` and `lift` are fractions
    of leg length.

    A foot in stance moves backward in a straight line at constant speed, on
    the floor, flat. That straight line IS the no-skate condition: the body
    moves forward at stride / stance-time, and in the engine the clip is
    time-scaled by that speed. Stance is exactly half the cycle so the
    exporter's stride-based speed (2 steps of one stride per cycle) is the true
    figure, not an approximation.

    If any leg cannot reach its target the stride and lift shrink and the cycle
    is re-authored, as `gait.generate` does for floor clearance.
    """
    from . import keyposes as kp

    bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return bm
    rig = bpy.data.objects[rig_name]
    body = motion.Body(rig, bm)
    P = kp.Poser(body)
    if len(P.legs) < 2:
        return {"error": "%s has %d legs - nothing to walk on" % (rig_name, len(P.legs))}

    base, cinfo = kp.crouch_key(P, depth=depth)
    offsets = gait.phase_offsets(
        [{"name": l["name"], "side": l["side"], "forward": l["forward_pos"]}
         for l in P.legs], gait=gait._default_gait(len(P.legs)))
    L = P.leg_len
    frames = max(8, int(frames) // 2 * 2)
    first_leg = min(P.legs, key=lambda l: offsets[l["name"]])

    def foot(p, S, H):
        """(fore/aft offset, lift, in stance) at cycle phase p."""
        if p < 0.5:
            return S * (0.5 - p / 0.5), 0.0, True
        u = (p - 0.5) / 0.5
        return -0.5 * S + S * motion.smoothstep(u), H * math.sin(math.pi * u), False

    def key_at(p0, S, H):
        limbs = dict(base.limbs)
        x_by_side = {}
        for l in P.legs:
            x, y, stance = foot((p0 + offsets[l["name"]]) % 1.0, S, H)
            x_by_side.setdefault(l["side"], x)
            limbs[l["name"]] = {
                "target": (lambda p, limb, posed, x=x, y=y:
                           limb["rest_eff"] + p.fwd * x + p.up * y),
                "planted": True,
            }
        for a in P.arms:
            spec = base.limbs.get(a["name"])
            if spec is None:
                continue
            swing = -x_by_side.get(a["side"], 0.0) / max(0.5 * S, 1e-9)
            limbs[a["name"]] = {
                "target": (lambda p, limb, posed, fn=spec["target"], k=swing:
                           fn(p, limb, posed)
                           + p.fwd * (k * arm_swing * (limb["a"] + limb["b"]))),
                "planted": False,
            }
        # lowest as the legs spread, twice a cycle; sway over the stance leg
        dip = bob * L * 0.5 * (1.0 + math.cos(4.0 * math.pi * p0))
        lean_over = sway * L * math.sin(2.0 * math.pi * p0) * \
            (1.0 if (first_leg["rest_root"] - P.centre).dot(P.lat) > 0 else -1.0)
        return base.copy(drop=base.drop + dip, sway=lean_over, limbs=limbs)

    S, H = stride * L, lift * L
    for attempt in range(max(1, attempts)):
        samples = [P.pose(key_at((f - 1) / float(frames), S, H))
                   for f in range(1, frames + 2)]        # last repeats the first
        clamped = [(f + 1, n) for f, (_, infos) in enumerate(samples)
                   for n, i in infos.items() if i["clamped"]]
        if not clamped:
            break
        S *= 0.85
        H *= 0.9

    def check(keyed, ev, infos_by_frame):
        r = _check_common(body, bm, keyed, ev, infos_by_frame, planted=[],
                          posed_limbs=P.legs, rest_floor=floor, starts_at_rest=False)
        evaluated = ev["evaluated"]
        seam, seam_bone = _pose_gap(rig, evaluated[1], evaluated[frames + 1])
        if seam > 1e-4:
            r["failures"].append("loop seam %.5f on %s" % (seam, seam_bone))
        # stance feet follow their straight line: this is the skate test
        slip = {}
        tol = 0.004 * bm["size"]
        for l in P.legs:
            rest_f = l["rest_eff"].dot(P.fwd)
            rest_h = P.height(l["rest_eff"])
            worst = 0.0
            for f in range(1, frames + 2):
                p = ((f - 1) / float(frames) + offsets[l["name"]]) % 1.0
                x, _, stance = foot(p, S, H)
                if not stance:
                    continue
                ankle = evaluated[f][l["end"] or l["lower"]].translation
                worst = max(worst, abs(ankle.dot(P.fwd) - (rest_f + x)),
                            abs(P.height(ankle) - rest_h))
            slip[l["name"]] = round(worst, 5)
            if worst > tol:
                r["failures"].append("%s leaves its stance line by %.4f - the foot "
                                     "would skate" % (l["name"], worst))
        r["stance_slip"] = slip
        r["loop_seam"] = round(seam, 6)
        return r

    keyed, infos, action, report = _author_samples(body, rig, action_name, samples,
                                                   fps, check)
    if "error" in report:
        return report
    fps_now = bpy.context.scene.render.fps
    stance_s = (frames / 2.0) / fps_now
    report.update({
        "rig": rig_name, "action": action.name, "frames": [1, frames + 1],
        "fps": fps_now, "depth": depth,
        "stride_m": round(S, 4), "lift_m": round(H, 4), "attempts": attempt + 1,
        "reach_shrunk": bool(attempt),
        "implied_speed_cycle_mps": round(S / stance_s, 4),
        # the engine imports all frames+1 keys and loops over them
        "implied_speed_playback_mps": round(S / (((frames + 1) / 2.0) / fps_now), 4),
        "base": base.name,
    })
    return report


def slide_recover(rig_name, to="stand", frames=None, forward="-Y", up="Z", floor=0.0,
                  action_name=None, lead="L", mid_depth=0.9, crouch_depth=0.6,
                  slide_clip="Slide", crouch_clip="Crouch", fps=None):
    """Author the way out of a slide.

    to="stand"   slide pose -> deep crouch (feet drawn under, torso forward)
                 -> standing. Named SlideRecover.
    to="crouch"  slide pose -> the Crouch clip's held pose. Named SlideToCrouch,
                 for when crouch is still held as the slide runs out.

    Both start on `keyposes.slide_key` and end on rest or `crouch_key`, the
    same keys the Slide and Crouch clips are built from. The seams are then
    MEASURED against Blender's playback of those clips when they exist, because
    "built from the same maths" is a claim and a gap in the engine is a pop.
    """
    from . import keyposes as kp

    bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return bm
    rig = bpy.data.objects[rig_name]
    body = motion.Body(rig, bm)
    P = kp.Poser(body)
    if not bm["upright"] or len(P.legs) != 2:
        return {"error": "slide recovery is authored for upright bipeds"}

    slide = kp.slide_key(P, lead=lead)
    if to == "crouch":
        end, _ = kp.crouch_key(P, depth=crouch_depth)
        frames = frames or 12
        action_name = action_name or "SlideToCrouch"
        split = None

        def pose(t):
            w = motion.smoothstep(t)
            # feet come under the body a little ahead of the hips rising, and
            # the chest comes forward ahead of both
            return P.blend(slide, end, w, w_legs=motion.smoothstep(min(1.0, t / 0.8)),
                           w_lean=motion.smoothstep(min(1.0, t / 0.6)))
    else:
        mid, _ = kp.crouch_key(P, depth=mid_depth)
        end = kp.rest_key()
        frames = frames or 18
        action_name = action_name or "SlideRecover"
        split = 0.5

        def pose(t):
            if t <= split:
                u = t / split
                # Chest first. With the lean on the hips' curve the torso passed
                # upright while the hips were still low, and the middle of the
                # clip read as sitting on an invisible chair.
                return P.blend(slide, mid, motion.smoothstep(u),
                               w_legs=motion.smoothstep(min(1.0, u / 0.8)),
                               w_lean=motion.smoothstep(min(1.0, u / 0.55)))
            return P.blend(mid, end, motion.smoothstep((t - split) / (1.0 - split)))

    samples = [pose((f - 1) / float(frames - 1)) for f in range(1, frames + 1)]
    split_frame = 1 + int(round(split * (frames - 1))) if split is not None else None
    before_slide = _evaluated_frame(rig, slide_clip, None)
    before_crouch = _evaluated_frame(rig, crouch_clip, None) if to == "crouch" else None

    def check(keyed, ev, infos_by_frame):
        evaluated = ev["evaluated"]
        r = _check_common(body, bm, keyed, ev, infos_by_frame, planted=[],
                          posed_limbs=P.legs, rest_floor=floor, starts_at_rest=False)
        tol = 0.002 * bm["size"]
        seams = {}
        if before_slide is not None:
            gap, bone = _pose_gap(rig, evaluated[1], before_slide)
            seams["from " + slide_clip] = round(gap, 5)
            if gap > tol:
                r["failures"].append("first frame is %.4f from the end of %s (%s)"
                                     % (gap, slide_clip, bone))
        else:
            r["failures"].append("no %s clip to measure the start seam against"
                                 % slide_clip)
        if to == "crouch":
            if before_crouch is not None:
                gap, bone = _pose_gap(rig, evaluated[frames], before_crouch)
                seams["to " + crouch_clip] = round(gap, 5)
                if gap > tol:
                    r["failures"].append("last frame is %.4f from the end of %s (%s)"
                                         % (gap, crouch_clip, bone))
            else:
                r["failures"].append("no %s clip to measure the end seam against"
                                     % crouch_clip)
        else:
            rest = {b.name: b.matrix_local for b in rig.data.bones}
            gap, bone = _pose_gap(rig, evaluated[frames], rest)
            seams["to rest"] = round(gap, 5)
            if gap > tol:
                r["failures"].append("last frame is %.4f from rest (%s)" % (gap, bone))
            # from the deep crouch up, both feet are planted
            drift = {}
            for l in P.legs:
                n = l["end"] or l["lower"]
                h0 = evaluated[split_frame][n].translation
                worst = max((evaluated[f][n].translation - h0).length
                            for f in range(split_frame, frames + 1))
                drift[l["name"]] = round(worst, 5)
                if worst > 0.005 * bm["size"]:
                    r["failures"].append("%s slides %.4f while standing up"
                                         % (l["name"], worst))
            r["planted_drift"] = drift
            lo, hi = kp.support(P)
            c = body.com(evaluated[split_frame]).dot(P.fwd)
            r["balance_at_deep_crouch"] = {"support_fwd": [round(lo, 4), round(hi, 4)],
                                           "com_fwd": round(c, 4),
                                           "margin_m": round(min(c - lo, hi - c), 4)}
            if c < lo or c > hi:
                r["failures"].append("centre of mass outside the feet at the deep "
                                     "crouch - it would fall")
        r["seams"] = seams
        return r

    keyed, infos, action, report = _author_samples(body, rig, action_name, samples,
                                                   fps, check)
    if "error" in report:
        return report
    report.update({"rig": rig_name, "action": action.name, "frames": [1, frames],
                   "fps": bpy.context.scene.render.fps, "to": to,
                   "split_frame": split_frame})
    return report


def _author(body, rig, action_name, frames, pose, fps, check):
    """Sample `pose(s)` over eased progress, bake, play back, check, restore."""
    frames = max(2, int(frames))
    samples = [pose(motion.smoothstep((f - 1) / float(frames - 1)))
               for f in range(1, frames + 1)]
    return _author_samples(body, rig, action_name, samples, fps, check)


def _author_samples(body, rig, action_name, samples, fps, check):
    """Bake already-posed frames (1, 2, ...), play back, check, restore."""
    scene = bpy.context.scene
    if fps:
        scene.render.fps = fps
    snap = verify._snapshot(rig)
    ad = rig.animation_data or rig.animation_data_create()
    prev_action = ad.action
    prev_frame = scene.frame_current

    keyed, infos_by_frame = [], {}
    for f, (posed, infos) in enumerate(samples, start=1):
        keyed.append((f, posed))
        infos_by_frame[f] = infos

    action = gait._fresh_action(rig, action_name)
    try:
        motion.bake(body, action, keyed)
        ev = motion.evaluate(body, action, keyed)
        if "error" in ev:
            return keyed, infos_by_frame, action, {"error": ev["error"]}
        report = check(keyed, ev, infos_by_frame)
    finally:
        scene.frame_set(prev_frame)
        if prev_action is not None:
            verify.bind_action(rig, prev_action)
        else:
            ad.action = None
        verify._restore(rig, snap)
    return keyed, infos_by_frame, action, report


def _check_common(body, bm, keyed, ev, infos_by_frame, planted, posed_limbs,
                  support=None, pole_overrides=None, rest_floor=0.0,
                  starts_at_rest=True):
    """Checks every action shares, all measured on Blender's evaluated pose.

    `planted` limbs must not move their ends. `pole_overrides` maps a limb name
    to the direction its mid-joint was asked to point on the LAST frame, for
    limbs posed against their natural bend (a slide's knee turned out).
    `support` enables the balance check, which only a static pose can pass.
    """
    pole_overrides = pole_overrides or {}
    rig = body.rig
    size = bm["size"]
    tol = 0.005 * size
    mw = rig.matrix_world
    upw = bodymap.axis_vector(bm["up"])
    fwd = bm["fwd"]
    failures, notes = [], []
    evaluated = ev["evaluated"]
    first, last = keyed[0][0], keyed[-1][0]

    # 1. Blender plays what the maths predicted
    if ev["prediction_error"] > 1e-4 * max(size, 1.0) + 1e-5:
        f, b = ev["prediction_worst"]
        failures.append("Blender's pose differs from the prediction by %.5f at "
                        "frame %d on %s" % (ev["prediction_error"], f, b))

    # 2. frame one is the rest pose
    rest_err = 0.0
    for b in body.bones:
        m = evaluated[first][b.name]
        rest_err = max(rest_err, (m.translation - b.head_local).length)
    if starts_at_rest and rest_err > tol:
        failures.append("first frame is not the rest pose (off by %.4f)" % rest_err)

    # 3. planted feet stay planted
    drift = {}
    for l in planted:
        pts = [l["end"]] + l["digits"] if l["end"] else [l["lower"]]
        worst = 0.0
        for n in pts:
            h0 = evaluated[first][n].translation
            t0 = motion.tail_of(body, evaluated[first], n)
            for f, _ in keyed:
                worst = max(worst, (evaluated[f][n].translation - h0).length,
                            (motion.tail_of(body, evaluated[f], n) - t0).length)
        drift[l["name"]] = round(worst, 5)
        if worst > tol:
            failures.append("%s slides %.4f while planted (tolerance %.4f)"
                            % (l["name"], worst, tol))

    # 4. reach and fold
    tightest = {}
    for f, infos in infos_by_frame.items():
        for name, info in infos.items():
            if info["clamped"]:
                failures.append("%s cannot reach its target at frame %d (needs %.0f%% "
                                "of its length)" % (name, f, 100 * info["reach"]))
            tightest[name] = min(tightest.get(name, 180.0), info["knee_angle"])
    for name, ang in tightest.items():
        if ang < 25.0:
            failures.append("%s folds to %.0f degrees - past what a joint does"
                            % (name, ang))

    # 5. mid-joints bend the intended way, measured on Blender's pose
    wrong = []
    for l in posed_limbs:
        mats = evaluated[last]
        root = mats[l["upper"]].translation
        mid = mats[l["lower"]].translation
        eff = (mats[l["end"]].translation if l["end"]
               else motion.tail_of(body, mats, l["lower"]))
        span = eff - root
        t = (mid - root).dot(span) / max(span.dot(span), 1e-12)
        dev = mid - (root + span * t)
        if dev.length < 0.02 * span.length:
            continue
        # the measured rest bend, or the role default, carried by the attach
        rot = mats[l["attach"]].to_3x3() @ body.rest[l["attach"]].to_3x3().inverted()
        intended = pole_overrides.get(l["name"]) or rot @ (
            l["rest_dev"] if l["pole_source"] == "rest shape" else l["default_pole"])
        if dev.dot(intended) < 0.0:
            wrong.append(l["name"])
    if wrong:
        failures.append("mid-joint bends the wrong way on " + ", ".join(wrong))

    # 6. nothing through the floor
    lowest, lowest_at = float("inf"), None
    for f, _ in keyed:
        for b in body.bones:
            for pt in (evaluated[f][b.name].translation,
                       motion.tail_of(body, evaluated[f], b.name)):
                h = (mw @ pt).dot(upw) - rest_floor
                if h < lowest:
                    lowest, lowest_at = h, (f, b.name)
    rest_lowest = min((mw @ p).dot(upw) - rest_floor
                      for b in body.bones for p in (b.head_local, b.tail_local))
    if lowest < min(0.0, rest_lowest) - tol:
        failures.append("%s reaches %.4f, below the floor, at frame %d"
                        % (lowest_at[1], lowest, lowest_at[0]))

    # 7. the SKIN stays above the floor. Bones are not enough once a pose puts
    # the body near the ground: the hips joint of a slide sits 0.3 m up while
    # the backside around it does not.
    skin_tol = 0.015 * bm["height"]
    skin = ev.get("skin_lowest") or {}
    skin_low = min(skin.values()) if skin else None
    if skin_low is not None:
        skin_rest = skin[first]
        if skin_low < min(0.0, skin_rest) - rest_floor - skin_tol:
            at = min(skin, key=skin.get)
            failures.append("skin reaches %.4f, through the floor, at frame %d"
                            % (skin_low - rest_floor, at))

    # 8. balance on the final pose, from Blender's evaluated skin. Only
    # meaningful for a pose meant to be held still.
    balance = None
    if support is not None:
        lo, hi = support
        com_last = body.com(evaluated[last]).dot(fwd)
        com_first = body.com(evaluated[first]).dot(fwd)
        margin = min(com_last - lo, hi - com_last)
        if margin < 0.0:
            failures.append("centre of mass is %.4f outside the feet at the end - it "
                            "would fall" % -margin)
        balance = {"support_fwd": [round(lo, 4), round(hi, 4)],
                   "com_fwd_start": round(com_first, 4),
                   "com_fwd_end": round(com_last, 4),
                   "margin_m": round(margin, 4)}

    # height at the end: for sizing the engine's collision shape
    top = max((mw @ pt).dot(upw) - rest_floor
              for b in body.bones
              for pt in (evaluated[last][b.name].translation,
                         motion.tail_of(body, evaluated[last], b.name)))
    rest_top = max((mw @ p).dot(upw) - rest_floor
                   for b in body.bones for p in (b.head_local, b.tail_local))

    return {
        "prediction_error": round(ev["prediction_error"], 7),
        "rest_error": round(rest_err, 6),
        "planted_drift": drift,
        "tightest_joint_degrees": {k: round(v, 1) for k, v in tightest.items()},
        "lowest_point": round(lowest, 4),
        "skin_lowest": round(skin_low - rest_floor, 4) if skin_low is not None else None,
        "balance": balance,
        "standing_height_m": round(rest_top, 4),
        "end_height_m": round(top, 4),
        "tolerance": round(tol, 5),
        "failures": failures,
        "passed": not failures,
    }


def summarize(r):
    if "error" in r:
        return "ERROR: " + r["error"]
    lines = ["%s  %s  %s  frames %d-%d" % (r["rig"], r["action"],
                                           "PASSED" if r["passed"] else "FAILED",
                                           r["frames"][0], r["frames"][1])]
    if "hip_drop_m" in r:
        lines.append("  drop %.3f of max %.3f (limited by %s), hips shifted %+.3f, "
                     "lean %.0f deg" % (r["hip_drop_m"], r["max_drop_m"],
                                        r["drop_limited_by"], r["hip_shift_m"],
                                        r["lean_degrees"]))
    for k in ("hip_height_m", "lead", "lean_degrees"):
        if k in r and "hip_drop_m" not in r:
            lines.append("  %s %s" % (k, r[k]))
    lines += [
        "  height %.3f -> %.3f   lowest bone point %.4f   lowest skin %s"
        % (r["standing_height_m"], r["end_height_m"], r["lowest_point"], r["skin_lowest"]),
        "  prediction error %.2e, rest error %.2e" % (r["prediction_error"], r["rest_error"]),
        "  drift %s" % r["planted_drift"],
        "  tightest joints %s" % r["tightest_joint_degrees"],
    ]
    if r.get("balance"):
        lines.append("  balance %s  (com: %s)" % (r["balance"], r.get("com_source")))
    for k in ("stride_m", "lift_m", "attempts", "implied_speed_playback_mps",
              "loop_seam", "stance_slip", "seams", "balance_at_deep_crouch",
              "split_frame"):
        if r.get(k) is not None:
            lines.append("  %s %s" % (k, r[k]))
    lines += ["  FAIL " + f for f in r["failures"]]
    return "\n".join(lines)
