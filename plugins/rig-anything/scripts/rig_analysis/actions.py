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
           arms_forward=True, fold_limit=0.45, fps=None, tail_lift=0.0):
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

    Built on `keyposes.crouch_key`, which reproduces this clip's original
    hand-written path exactly (0.000000 m) - and, unlike it, poses a tail, so a
    body whose tail rests on the floor drapes it instead of pushing it through.

    Stand back up in the engine by playing the clip backwards.
    """
    from . import keyposes as kp
    bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return bm
    legs = [l for l in bm["limbs"] if l["role"] == "leg" and l["axial_index"] is not None]
    if not legs:
        return {"error": "%s has no legs to crouch on - nothing holds it off the "
                         "ground, so there is nothing to fold" % rig_name,
                "bodymap": bodymap.summary(bm)}
    if len(bm["axial"]) == 0:
        return {"error": "no axial chain", "bodymap": bodymap.summary(bm)}
    rig = bpy.data.objects[rig_name]
    body = motion.Body(rig, bm)
    P = kp.Poser(body)
    key, info = kp.crouch_key(P, depth=depth, lean_degrees=lean_degrees,
                              head_level=head_level, arms_forward=arms_forward,
                              fold_limit=fold_limit)
    key.tail_lift = tail_lift
    rest = kp.rest_key()
    free = [l for l in bm["limbs"] if l["role"] == "arm" and l["axial_index"] is not None]

    keyed, infos, action, report = _author(
        body, rig, action_name, frames, lambda s: P.blend(rest, key, s), fps,
        lambda keyed, ev, infos_by_frame: _check_common(
            body, bm, keyed, ev, infos_by_frame, planted=legs, posed_limbs=legs + free,
            support=info["support"], rest_floor=floor))
    if "error" in report:
        return report
    report.update({
        "rig": rig_name,
        "action": action.name,
        "frames": [1, len(keyed)],
        "fps": bpy.context.scene.render.fps,
        "depth": depth,
        "hip_drop_m": round(info["drop"], 4),
        "max_drop_m": round(info["max_drop"], 4),
        "drop_limited_by": info["limited_by"],
        "lean_degrees": info["lean"],
        "hip_shift_m": round(info["shift"], 4),
        "upright": bm["upright"],
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
    if not bm["upright"]:
        return skid(rig_name, frames=frames, forward=forward, up=up, floor=floor,
                    action_name=action_name, fps=fps)
    if len(legs) != 2:
        return {"error": "an upright body with %d legs has no slide authored"
                         % len(legs), "bodymap": bodymap.summary(bm)}
    lead_leg = next((l for l in legs if l["side"] == lead), None)
    if lead_leg is None:
        return {"error": "no leg on side %r" % lead}
    trail_leg = next(l for l in legs if l is not lead_leg)

    body = motion.Body(rig, bm)
    upv, fwd, lat = bm["up_vec"], bm["fwd"], bm["lat"]
    mw = rig.matrix_world
    upw = bodymap.axis_vector(up)
    # Written by hand rather than through a Poser, so wings are folded here.
    wing_poser = None
    if bm.get("wings"):
        from . import keyposes as kp, wings as wing_mod
        wing_poser = kp.Poser(body)

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
        if wing_poser is not None:
            overrides.update(wing_poser.wing_rig.pose(posed, wing_mod.blend_states(
                wing_poser.wing_default, wing_poser.wing_default, 1.0)))
            posed = body.fk(overrides)

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
    """Author a looping walk at crouch height. See `gait_cycle`."""
    return gait_cycle(rig_name, depth=depth, stride=stride, lift=lift, frames=frames,
                      forward=forward, up=up, floor=floor, action_name=action_name,
                      bob=bob, sway=sway, arm_swing=arm_swing, attempts=attempts,
                      fps=fps)


def gait_cycle(rig_name, depth=0.6, stride=0.40, lift=0.10, frames=24,
               forward="-Y", up="Z", floor=0.0, action_name="CrouchWalk",
               bob=0.012, sway=0.015, arm_swing=0.10, attempts=5, fps=None,
               gait_name=None, lean_degrees=None, tail_lift=0.0, tail_swing=0.0):
    """Author a looping IK gait for any number of legs, at any crouch depth.

    depth 0 is a walk at standing height, 0.6 the crouch walk; a run is a
    shallow depth with a long stride, a high lift, few frames and a trot or
    tripod `gait_name`. Phase offsets come from `gait.phase_offsets`, so a
    biped alternates, a quadruped walks in lateral sequence or trots, and a
    hexapod runs alternating tripods.

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

    base, cinfo = kp.crouch_key(P, depth=depth, lean_degrees=lean_degrees)
    start_depth = depth
    gait_name = gait_name or gait._default_gait(len(P.legs))
    offsets = gait.phase_offsets(
        [{"name": l["name"], "side": l["side"], "forward": l["forward_pos"]}
         for l in P.legs], gait=gait_name)
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
                # keep the crouch's heel/wrist lift through the stride
                "tilt": base.limbs.get(l["name"], {}).get("tilt", 0.0),
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
        # the tail is carried at `tail_lift` and swings once a cycle, opposite
        # the body's sway so the mass stays centred
        return base.copy(drop=base.drop + dip, sway=lean_over, limbs=limbs,
                         tail_lift=tail_lift,
                         tail_sway=-tail_swing * math.sin(2.0 * math.pi * p0))

    S, H = stride * L, lift * L
    skin_rest = body.skin_lowest(body.fk(), P._upw)
    skin_allowed = (min(0.0, skin_rest - floor) - 0.012 * bm["height"]
                    if skin_rest is not None else 0.0)
    for attempt in range(max(1, attempts) + 4):
        samples = [P.pose(key_at((f - 1) / float(frames), S, H))
                   for f in range(1, frames + 2)]        # last repeats the first
        clamped = [(f + 1, n) for f, (_, infos) in enumerate(samples)
                   for n, i in infos.items() if i["clamped"]]
        if not clamped:
            # Reach is not the only limit. A leg folding hard near the ground
            # bulges its skin into it mid-stride - the rat's run sat 1 cm under
            # the floor on its first frame - so the predicted skin is checked
            # too, on every other frame, and the stride shortened if it dips.
            low = min(body.skin_lowest(posed, P._upw) for posed, _ in samples[::2])                 if skin_rest is not None else None
            if low is None or low - floor >= skin_allowed:
                break
            S *= 0.85
            H *= 0.9
            continue
        # Out of reach. Flex the legs before shortening the stride: a body that
        # stands on nearly straight legs - this project's quadruped stands at
        # 97-99% of full length - has no reach left to step with at any stride,
        # and shrinking alone walks it in place. Real quadrupeds walk flexed.
        if depth < start_depth + 0.4:
            depth = min(start_depth + 0.4, depth + 0.1)
            base, cinfo = kp.crouch_key(P, depth=depth, lean_degrees=lean_degrees)
        else:
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
            # a lifted heel moves the ankle off the rest line by a fixed offset
            _, lift_off = P.tilt_rotation(l, base.limbs.get(l["name"], {}).get("tilt", 0.0))
            rest_f = (l["rest_eff"] + lift_off).dot(P.fwd)
            rest_h = P.height(l["rest_eff"] + lift_off)
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
        "fps": fps_now, "depth": round(depth, 3), "depth_requested": start_depth,
        "stride_m": round(S, 4), "lift_m": round(H, 4), "attempts": attempt + 1,
        "reach_shrunk": bool(attempt),
        "implied_speed_cycle_mps": round(S / stance_s, 4),
        # the engine imports all frames+1 keys and loops over them
        "implied_speed_playback_mps": round(S / (((frames + 1) / 2.0) / fps_now), 4),
        "base": base.name, "gait": gait_name,
        "phase_offsets": {k: round(v, 3) for k, v in offsets.items()},
    })
    return report


def slide_recover(rig_name, to="stand", frames=None, forward="-Y", up="Z", floor=0.0,
                  action_name=None, lead="L", mid_depth=None, crouch_depth=0.6,
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
    if bm["upright"] and len(P.legs) != 2:
        return {"error": "an upright body with %d legs has no slide authored"
                         % len(P.legs)}
    # a biped slides on its back; anything horizontal skids on its belly
    slide = kp.slide_key(P, lead=lead) if bm["upright"] else kp.skid_key(P)[0]
    # A biped comes up through a deep squat. A horizontal body passing its
    # stretched legs back under it through that depth folded a front leg to 21
    # degrees, so it comes up through the ordinary crouch.
    if mid_depth is None:
        mid_depth = 0.9 if bm["upright"] else crouch_depth
    # A biped draws its feet in ahead of rising. A horizontal body doing that
    # pulls its front feet under a belly still on the floor and folds those legs
    # to ~25 degrees, so its feet and body move together.
    feet_lead = 0.8 if bm["upright"] else 1.0
    if to == "crouch":
        end, _ = kp.crouch_key(P, depth=crouch_depth)
        frames = frames or 12
        action_name = action_name or "SlideToCrouch"
        split = None

        def pose(t):
            w = motion.smoothstep(t)
            # feet come under the body a little ahead of the hips rising, and
            # the chest comes forward ahead of both
            return P.blend(slide, end, w, w_legs=motion.smoothstep(min(1.0, t / feet_lead)),
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
                               w_legs=motion.smoothstep(min(1.0, u / feet_lead)),
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
            rest = getattr(body, "ground_rest", None) or {
                b.name: b.matrix_local for b in rig.data.bones}
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


def _setup(rig_name, forward, up, floor):
    from . import keyposes as kp
    bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return None, bm
    rig = bpy.data.objects[rig_name]
    body = motion.Body(rig, bm)
    P = kp.Poser(body)
    if not P.legs:
        return None, {"error": "%s has no legs" % rig_name}
    return (bm, rig, body, P), None


def skid(rig_name, frames=10, forward="-Y", up="Z", floor=0.0, action_name="Slide",
         fps=None):
    """A horizontal body's slide: rest -> `keyposes.skid_key`, held at the end.

    Belly dropped to just above the floor, legs stretched out along it - front
    forward, rear back, middle out. Feet reach before the belly comes down, as
    in the biped slide, so no leg is dragged under a falling body.
    """
    from . import keyposes as kp
    ctx, err = _setup(rig_name, forward, up, floor)
    if err:
        return err
    bm, rig, body, P = ctx
    key, info = kp.skid_key(P)
    rest = kp.rest_key()

    def pose(s):
        return P.blend(rest, key, s, w_legs=math.sqrt(s))

    keyed, infos, action, report = _author(
        body, rig, action_name, frames, pose, fps,
        lambda keyed, ev, infos: _check_common(body, bm, keyed, ev, infos, planted=[],
                                               posed_limbs=P.legs, rest_floor=floor))
    if "error" in report:
        return report
    report.update({"rig": rig_name, "action": action.name, "frames": [1, len(keyed)],
                   "fps": bpy.context.scene.render.fps,
                   "hip_drop_m": round(info["drop"], 4),
                   "slide_height_m": report["end_height_m"]})
    return report


def idle(rig_name, frames=48, forward="-Y", up="Z", floor=0.0, action_name="Idle",
         breath=0.006, sway_degrees=1.5, fps=None):
    """A breathing loop: the body settles and rises on planted feet, the torso
    and head drift a degree or two. Small on purpose - an idle that visibly
    moves reads as fidgeting."""
    from . import keyposes as kp
    ctx, err = _setup(rig_name, forward, up, floor)
    if err:
        return err
    bm, rig, body, P = ctx
    L = P.leg_len
    frames = max(8, int(frames))
    # Pitching a horizontal body lifts its front hips, and legs that stand
    # nearly straight cannot follow: the rat's front legs clamped at 100%.
    lean_amp = sway_degrees if bm["upright"] else 0.0
    samples = []
    for f in range(1, frames + 2):
        t = (f - 1) / float(frames)
        samples.append(P.pose(kp.Key(
            drop=breath * L * 0.5 * (1.0 - math.cos(2.0 * math.pi * t)),
            lean=lean_amp * math.sin(2.0 * math.pi * t), head_level=0.5,
            tail_sway=4.0 * math.sin(2.0 * math.pi * t))))

    def check(keyed, ev, infos_by_frame):
        r = _check_common(body, bm, keyed, ev, infos_by_frame, planted=P.legs,
                          posed_limbs=P.legs, rest_floor=floor)
        seam, bone = _pose_gap(rig, ev["evaluated"][1], ev["evaluated"][frames + 1])
        r["loop_seam"] = round(seam, 6)
        if seam > 1e-4:
            r["failures"].append("loop seam %.5f on %s" % (seam, bone))
        return r

    keyed, infos, action, report = _author_samples(body, rig, action_name, samples,
                                                   fps, check)
    if "error" in report:
        return report
    report.update({"rig": rig_name, "action": action.name, "frames": [1, frames + 1],
                   "fps": bpy.context.scene.render.fps})
    return report


def jump(rig_name, forward="-Y", up="Z", floor=0.0, action_name="Jump",
         timing=(6, 9, 14, 22), fps=None):
    """A one-shot jump for any number of legs, ending held on the landing reach.

    rest -> load (frame timing[0]) -> launch -> tuck -> reach (timing[3]). In
    place: the engine flies the body, the clip shapes it. Like the humanoid's
    authored Jump it ends on the reach so an AnimationPlayer holds that pose for
    the rest of the hang time.
    """
    from . import keyposes as kp
    ctx, err = _setup(rig_name, forward, up, floor)
    if err:
        return err
    bm, rig, body, P = ctx
    load, launch, tuck, reach = kp.jump_keys(P)
    keys = [kp.rest_key(), load, launch, tuck, reach]
    marks = [1] + list(timing)
    samples = []
    for f in range(1, marks[-1] + 1):
        seg = max(i for i in range(len(marks) - 1) if marks[i] <= f)
        seg = min(seg, len(keys) - 2)
        u = (f - marks[seg]) / float(marks[seg + 1] - marks[seg])
        w = motion.smoothstep(min(1.0, u))
        # legs lead out of the launch: feet leave the ground as the body peaks
        samples.append(P.blend(keys[seg], keys[seg + 1], w,
                               w_legs=math.sqrt(w) if seg >= 2 else w))

    def check(keyed, ev, infos_by_frame):
        r = _check_common(body, bm, keyed, ev, infos_by_frame, planted=[],
                          posed_limbs=P.legs, rest_floor=floor)
        # feet stay down from rest through the load
        drift = {}
        for l in P.legs:
            n = l["end"] or l["lower"]
            h0 = ev["evaluated"][1][n].translation
            worst = max((ev["evaluated"][f][n].translation - h0).length
                        for f in range(1, marks[1] + 1))
            drift[l["name"]] = round(worst, 5)
            if worst > 0.005 * bm["size"]:
                r["failures"].append("%s slides %.4f before take-off" % (l["name"], worst))
        r["planted_drift"] = drift
        return r

    keyed, infos, action, report = _author_samples(body, rig, action_name, samples,
                                                   fps, check)
    if "error" in report:
        return report
    report.update({"rig": rig_name, "action": action.name, "frames": [1, marks[-1]],
                   "fps": bpy.context.scene.render.fps,
                   "launch_rise_m": round(-launch.drop, 4),
                   "load_drop_m": round(load.drop, 4)})
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
        # Checks add their own failures after `_check_common` has already
        # written `passed`. Decided there, a loop seam, a skating foot or a
        # wing through the body printed PASSED with the failure listed beneath.
        if "failures" in report:
            report["passed"] = not report["failures"]
    finally:
        scene.frame_set(prev_frame)
        try:
            if prev_action is not None:
                verify.bind_action(rig, prev_action)
            else:
                ad.action = None
        except ReferenceError:
            # the rig was holding the very clip `_fresh_action` just replaced
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

    # 2. frame one is the rest pose - with wings, the GROUND rest, wings folded
    ground = getattr(body, "ground_rest", None)
    rest_err = 0.0
    for b in body.bones:
        m = evaluated[first][b.name]
        want = ground[b.name].translation if ground else b.head_local
        rest_err = max(rest_err, (m.translation - want).length)
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
        # Measured against REST, not the clip's first frame. A gait's first
        # frame is mid-stride; taking it as the baseline let a run whose skin
        # sat 3.6 cm under the floor from frame one pass.
        skin_rest = body.skin_lowest(body.fk(), upw)
        if skin_rest is None:
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

    # Height at the end, for sizing the engine's collision shape - of the body,
    # not its tail. A tail needs no collider, and counting it made the rat's
    # slide, which lifts its tail clear of its legs, 0.46 m tall against 0.34 m
    # standing.
    tail = set(bm.get("tail", []))
    body_bones = [b for b in body.bones if b.name not in tail] or body.bones
    top = max((mw @ pt).dot(upw) - rest_floor
              for b in body_bones
              for pt in (evaluated[last][b.name].translation,
                         motion.tail_of(body, evaluated[last], b.name)))
    rest_top = max((mw @ p).dot(upw) - rest_floor
                   for b in body_bones for p in (b.head_local, b.tail_local))

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


RUN_GAIT = {2: "walk", 4: "trot", 6: "tripod"}


def move_set(rig_name, prefix=None, forward="-Y", up="Z", floor=0.0, fps=None,
             roles=("Idle", "Walk", "Trot", "Run", "Crouch", "CrouchWalk", "Jump",
                    "Slide", "SlideRecover", "SlideToCrouch"),
             walk_froude="walk", trot_froude="trot", run_froude="sprint",
             legacy_gaits=False):
    """Author a playable move set for one creature. Returns {role: report}.

    Clips are named `<prefix>_<Role>` (prefix defaults to the rig name) so one
    .blend can hold several creatures' sets without any clip taking another's
    name. Order matters: the recoveries measure their seams against this set's
    own Slide and Crouch, so those are authored first.

    Walk, Trot and Run come from `locomotion.cycle` at `walk_froude`,
    `trot_froude` and `run_froude` (numbers, or names from `locomotion.GAITS`):
    stride, ground time, footfalls and reach all follow from the body's contacts
    and that one speed, so a run is a run and not a walk played fast. The trot
    is the middle gait an engine changes through, so a speed change never plays
    the walk at several times its rate. `legacy_gaits=True` restores the old
    `gait_cycle` walk and run and drops the trot. CrouchWalk stays on
    `gait_cycle`, which is built on the crouch pose.

    For the engine side, `locomotion.engine_manifest` turns these reports into
    the gait and contact-schedule entries a controller reads.
    """
    bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return {"error": bm["error"]}
    n_legs = len([l for l in bm["limbs"] if l["role"] == "leg"])
    prefix = prefix or rig_name
    name = lambda role: "%s_%s" % (prefix, role)
    common = dict(forward=forward, up=up, floor=floor, fps=fps)
    makers = {
        "Idle": lambda: idle(rig_name, action_name=name("Idle"), **common),
        "Walk": lambda: gait_cycle(rig_name, depth=0.0, stride=0.45, lift=0.10,
                                   frames=32, bob=0.01, sway=0.01, lean_degrees=0.0,
                                   tail_lift=8.0, tail_swing=8.0,
                                   action_name=name("Walk"), **common),
        # Start a run nearly straight-legged and let reach add flex only where a
        # body needs it: a flexed run folded the rat's wrists into the floor,
        # which shrank its stride to 3 cm. Straight, it ran at 3x its walk.
        "Run": lambda: gait_cycle(rig_name, depth=0.05, stride=0.45, lift=0.10,
                                  frames=12, bob=0.02, sway=0.0, lean_degrees=0.0,
                                  gait_name=RUN_GAIT.get(n_legs, "tripod"),
                                  tail_lift=20.0, tail_swing=5.0,
                                  action_name=name("Run"), **common),
        "Crouch": lambda: crouch(rig_name, depth=0.6, action_name=name("Crouch"),
                                 **common),
        "CrouchWalk": lambda: gait_cycle(rig_name, depth=0.6, tail_swing=6.0,
                                         action_name=name("CrouchWalk"), **common),
        "Jump": lambda: jump(rig_name, action_name=name("Jump"), **common),
        "Slide": lambda: slide(rig_name, action_name=name("Slide"), **common),
        "SlideRecover": lambda: slide_recover(
            rig_name, to="stand", action_name=name("SlideRecover"),
            slide_clip=name("Slide"), crouch_clip=name("Crouch"), **common),
        "SlideToCrouch": lambda: slide_recover(
            rig_name, to="crouch", action_name=name("SlideToCrouch"),
            slide_clip=name("Slide"), crouch_clip=name("Crouch"), **common),
    }
    if not legacy_gaits:
        from . import locomotion
        makers["Walk"] = lambda: locomotion.cycle(rig_name, froude=walk_froude,
                                                  action_name=name("Walk"), **common)
        makers["Run"] = lambda: locomotion.cycle(rig_name, froude=run_froude,
                                                 action_name=name("Run"), **common)
        makers["Trot"] = lambda: locomotion.cycle(rig_name, froude=trot_froude,
                                                  action_name=name("Trot"), **common)
    else:
        roles = [r for r in roles if r != "Trot"]
    return {role: makers[role]() for role in roles}
