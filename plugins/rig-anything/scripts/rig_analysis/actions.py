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

from . import bodymap, gait, motion, stored, verify


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
            support=info["support"], rest_floor=floor,
            # arms posed by `upper.arm_spec` bend where their pole says, not
            # where the rest pose's elbow pointed
            pole_overrides={n: s["pole"] for n, s in key.limbs.items()
                            if s.get("pole") is not None and n in {a["name"] for a in free}}))
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
    if not bm["upright"]:
        return skid(rig_name, frames=frames, forward=forward, up=up, floor=floor,
                    action_name=action_name, fps=fps)
    if len(legs) != 2:
        return {"error": "an upright body with %d legs has no slide authored"
                         % len(legs), "bodymap": bodymap.summary(bm)}
    if not any(l["side"] == lead for l in legs):
        return {"error": "no leg on side %r" % lead}

    # Built from `keyposes.slide_key` through the Poser, the same key and the same
    # blend the recoveries start from. Hand-written here, the slide solved its feet
    # without the Poser's floor handling: the tucked trail foot followed its shin
    # into the ground (toe.R 0.16 m and skin 0.11 m under the floor at frame 8 on a
    # Rigify biped), and SlideRecover, which drapes that toe, started 0.18 m from
    # where Slide ended. One path, and the seam is zero by construction.
    from . import keyposes as kp
    body = motion.Body(rig, bm)
    P = kp.Poser(body)
    key = kp.slide_key(P, lead=lead, hip_height=hip_height, lean_degrees=lean_degrees,
                       head_level=head_level)
    # rest looks where the slide's head looks, so only the lean moves the head
    start = kp.rest_key().copy(head_level=head_level)
    leg_len = P.leg_len
    # the knees are posed against their natural bend: the trail knee turned out
    poles_last = {l["name"]: key.limbs[l["name"]]["pole"] for l in legs}

    def pose(s):
        # The feet get going before the hips come down. Moving both on the same
        # curve left the lead foot behind a half-dropped pelvis and the middle
        # of the clip read as sitting on a chair.
        return P.blend(start, key, s, w_legs=math.sqrt(s))

    # Held to the floor-skid check like any clip. It used to opt out because "a
    # slide drives its lead leg along the floor" - and it did: the lead heel
    # dragged 0.32 m forward and the trail foot 0.18 m. Nothing
    # in a slide needs that; both feet leave the floor for their new spots
    # (`Poser._step`), and on a Rigify biped the worst skid is now 2 mm.
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
            if spec.get("arm"):
                # an arm posed by angle swings by angle, so it never outreaches
                # itself; `arm_swing` is the hand's travel as a share of reach
                from . import upper as upper_mod
                f, o, e, hi = spec["arm"]
                limbs[a["name"]] = upper_mod.arm_spec(
                    P, a, f + swing * math.degrees(math.atan(arm_swing / 0.8)), o, e, hi)
                continue
            limbs[a["name"]] = {
                "target": (lambda p, limb, posed, fn=spec["target"], k=swing:
                           fn(p, limb, posed)
                           + p.fwd * (k * arm_swing * (limb["a"] + limb["b"]))),
                "pole": spec.get("pole"),
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
        def in_stance(name, f):
            if name not in offsets:
                return False
            return foot(((f - 1) / float(frames) + offsets[name]) % 1.0, S, H)[2]
        r = _check_common(body, bm, keyed, ev, infos_by_frame, planted=[],
                          posed_limbs=P.legs, rest_floor=floor, starts_at_rest=False,
                          skid=in_stance)  # stance is held to the skate test below
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

    # Held to the floor-skid check, like the biped slide: it opted out because "a
    # skid drags the body along the floor", but the check is on the legs, and a
    # Rigify dog's feet stretched out along the floor dragged 11 mm (front) and
    # 9 mm (rear) before they stepped (`Poser._step`); now 0.
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


# degrees an upright idle's chest tips back at the top of each breath (`idle`)
BREATH_CHEST_DEG = 1.5


def idle(rig_name, frames=48, forward="-Y", up="Z", floor=0.0, action_name="Idle",
         breath=0.006, sway_degrees=1.5, fps=None, stance_width=None, posture=None,
         upper=None, style=None):
    """A breathing loop: the body settles and rises on planted feet, the torso
    and head drift a degree or two. Small on purpose - an idle that visibly
    moves reads as fidgeting.

    `stance_width` and `posture` are the same as `locomotion.cycle`'s, so an
    idle stands the way its character walks. With either, frame one is that
    stance rather than the rest pose.

    `upper` as in `cycle`, over `upper.idle_defaults`: an upright biped's arms
    come down from the rig's rest pose to hang relaxed - out from the hips by
    as much as clears them, a little forward, elbows soft - and drift with the
    breath. False leaves them at rest.

    `style` is `locomotion.cycle`'s: its stance, posture and "idle" section,
    so a character stands the way its style walks."""
    from . import keyposes as kp, upper as upper_mod
    from .locomotion import style_args
    given = {k: v for k, v in dict(stance_width=stance_width, posture=posture,
                                   upper=upper).items() if v is not None}
    try:
        st = style_args(style, "idle", given)
    except ValueError as e:
        return {"error": str(e)}
    stance_width, posture, upper = st.get("stance_width"), st.get("posture"), st.get("upper")
    ctx, err = _setup(rig_name, forward, up, floor)
    if err:
        return err
    bm, rig, body, P = ctx
    L = P.leg_len
    frames = max(8, int(frames))
    # Pitching a horizontal body lifts its front hips, and legs that stand
    # nearly straight cannot follow: the rat's front legs clamped at 100%.
    lean_amp = sway_degrees if bm["upright"] else 0.0
    limbs = {}
    if stance_width is not None:
        for l in P.legs:
            limbs[l["name"]] = {"target": (lambda p, limb, posed, s=kp.stance_shift(P, l, stance_width):
                                           limb["rest_eff"] + s)}
    params = upper_mod.resolve(P, upper, upper_mod.idle_defaults())
    U = upper_mod.Upper(P, params, posture=posture, stance=limbs) if params and P.arms else None

    def key_at(t, shift=None):
        key_limbs = dict(limbs)
        if U is not None:
            key_limbs.update(U.idle_key(t))
        # an upright chest lifts with the breath, the head held level over it
        chest = (upper_mod.trunk(P, 0.0, 0.0, 0.0, 0.0,
                                 -BREATH_CHEST_DEG * 0.5 * (1.0 - math.cos(2.0 * math.pi * t)), 1.0)
                 if bm["upright"] and bm["axial"] else None)
        return kp.Key(trunk=chest, 
            drop=balance["drop"] + breath * L * 0.5 * (1.0 - math.cos(2.0 * math.pi * t)),
            shift=balance["shift"] if shift is None else shift,
            lean=lean_amp * math.sin(2.0 * math.pi * t), head_level=0.5,
            tail_sway=4.0 * math.sin(2.0 * math.pi * t), limbs=key_limbs, posture=posture)

    # Standing still, the centre of mass has to be over the feet. A hunch or
    # arms hanging in front carry it forward - Walter's by 5.5 cm, off his
    # toes - and a person standing like that puts their hips back. Only as far
    # as the foot's inner 70%: centring the mass (the crouch's +-30% band) put
    # Walter's hips 16 cm back, his seat behind his heels. Only when
    # something was asked of the stance, so a plain idle still starts at rest.
    balance = {"shift": 0.0, "drop": 0.0}
    if bm["upright"] and (posture or U is not None):
        lo, hi = _support(body, P.legs)
        centre, half = 0.5 * (lo + hi), 0.5 * (hi - lo)
        band = (centre - 0.7 * half, centre + 0.7 * half)

        def com_fwd(s):
            return body.com(P.pose(key_at(0.0, shift=s))[0]).dot(bm["fwd"])
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
            balance["shift"] = x1
            # hips back on straight legs cannot reach the feet: soften the knees
            # by as much as the legs are short
            for _ in range(6):
                infos = P.pose(key_at(0.0))[1]
                over = max(infos[l["name"]]["reach"] * (l["a"] + l["b"])
                           - 0.99 * (l["a"] + l["b"]) for l in P.legs)
                if over <= 0.0:
                    break
                balance["drop"] += over * 1.2
    shift = balance["shift"]

    def check(keyed, ev, infos_by_frame):
        r = _check_common(body, bm, keyed, ev, infos_by_frame, planted=P.legs,
                          posed_limbs=P.legs, rest_floor=floor,
                          starts_at_rest=stance_width is None and not posture and U is None)
        seam, bone = _pose_gap(rig, ev["evaluated"][1], ev["evaluated"][frames + 1])
        r["loop_seam"] = round(seam, 6)
        if seam > 1e-4:
            r["failures"].append("loop seam %.5f on %s" % (seam, bone))
        return r

    keyed, infos, action, report = upper_mod.author_clear(
        U, rig_name, bm, lambda s: _author_samples(body, rig, action_name, s, fps, check),
        lambda: [P.pose(key_at((f - 1) / float(frames))) for f in range(1, frames + 2)])
    if "error" in report:
        return report
    report.update({"rig": rig_name, "action": action.name, "frames": [1, frames + 1],
                   "fps": bpy.context.scene.render.fps, "stance_width": stance_width,
                   "hip_shift_m": round(shift, 4),
                   "posture": dict(posture) if posture else None,
                   "upper": U.report() if U is not None else None})
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
        # The snapshot's modes are the rig's, not the clip's: on an Euler rig
        # they would leave every quaternion key just baked silently unplayed.
        verify.adopt_rotation_modes(rig, action)
    return keyed, infos_by_frame, action, report


def _check_common(body, bm, keyed, ev, infos_by_frame, planted, posed_limbs,
                  support=None, pole_overrides=None, rest_floor=0.0,
                  starts_at_rest=True, skid=True):
    """Checks every action shares, all measured on Blender's evaluated pose.

    `planted` limbs must not move their ends. `pole_overrides` maps a limb name
    to the direction its mid-joint was asked to point on the LAST frame, for
    limbs posed against their natural bend (a slide's knee turned out).
    `support` enables the balance check, which only a static pose can pass.
    `skid` is False for a clip whose floor is not the ground its legs stand on
    (a hop's air phase), or a callable `(limb name, frame) -> in stance` for a gait played in
    place: its stance feet travel back along the floor by design and are held to
    the gait's own skate test, and only its swing is checked here.
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

    # 6. nothing through the floor - of every bone but the controls
    # (`roles["controls"]`, see `motion.Body.body_bones`). A control is not body
    # (MPFB's root dips under the floor as the hips drop) and step 7 already
    # holds the skin itself; with no mesh bound there are no controls and every
    # bone stands in for the body.
    floor_bones = body.body_bones()
    lowest, lowest_at = float("inf"), None
    for f, _ in keyed:
        for b in floor_bones:
            for pt in (evaluated[f][b.name].translation,
                       motion.tail_of(body, evaluated[f], b.name)):
                h = (mw @ pt).dot(upw) - rest_floor
                if h < lowest:
                    lowest, lowest_at = h, (f, b.name)
    rest_lowest = min((mw @ p).dot(upw) - rest_floor
                      for b in floor_bones for p in (b.head_local, b.tail_local))
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

    # 9. a foot on the floor does not move along it. Each clip measured its
    # own drift from a touchdown frame it guessed, and a cricket's forefeet
    # reached the floor a frame before their spot and skidded 0.5 mm into it.
    # Here: every run of frames in which a limb's contact pivot is on the floor
    # (no higher than at rest, within tolerance), measured from the run's first
    # frame, across the floor. Only limbs that stand on the floor at rest: a
    # hand hanging lower than it rests is not on the floor. A gait's planned
    # stance frames are left out: a cricket's hind toe dragged through the end of
    # every swing, and the gait's own test, which looks only at stance, passed it.
    skids = {}
    in_stance = skid if callable(skid) else None
    if skid:
        frames = sorted(f for f, _ in keyed)
        for l in posed_limbs:
            n = l["end"] or l["lower"]
            pivot = rig.data.bones[n].tail_local.copy()
            rest_h = (mw @ pivot).dot(upw)
            if rest_h - rest_floor > 0.1 * bm["height"]:
                continue
            on_floor = rest_h + tol
            start, worst = None, 0.0
            for f in frames:
                w = mw @ body.carried(evaluated[f], n, pivot)
                if w.dot(upw) > on_floor or (in_stance and in_stance(l["name"], f)):
                    start = None
                    continue
                if start is None:
                    start = w
                    continue
                d = w - start
                worst = max(worst, (d - upw * d.dot(upw)).length)
            skids[l["name"]] = round(worst, 5)
            if worst > tol:
                failures.append("%s skids %.4f along the floor (tolerance %.4f)" % (l["name"], worst, tol))

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
        "floor_skid": skids,
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


def turn(rig_name, direction="L", degrees=90.0, frames=24, forward="-Y", up="Z", floor=0.0,
         action_name="Turn", fps=None, stance_width=None, posture=None, upper=None, style=None,
         lift=0.08, shift=0.5):
    """Turn on the spot: pivot on the inside foot's ball and step the other foot round.

    A two-legged body standing as its idle stands (`stance_width`, `posture`,
    `style` as `idle`) turns `degrees` towards `direction` ("L" or "R", the
    body's own sides). The whole body turns about the inside foot's contact
    pivot (the toe end of its end bone), so that point never moves while the
    heel sweeps round it. The outside foot lifts first, is carried round in the
    air - the turn happens only while it is off the floor - and comes down
    where the idle stance puts it after the turn. The hips lean `shift` of the
    hip gap over the pivot foot while the other is up. The arms hang as the
    idle's.

    The clip is not a loop and does not end where it began: it ends turned.
    Its report carries `turn` = {yaw_deg, pivot_leg, pivot_m, end_offset_m,
    floor_skid_m, skid_tolerance_m}:
    the yaw (positive to the body's left) and where the rig's origin went, in
    the rig's space. That is what an engine applies to the character when the
    clip ends, before it plays Idle. Checked like every clip (floor, skin,
    reach, joint fold); the floor-skid check follows both contacts through
    every frame they are on the floor, so the pivot may not move and the
    stepping foot must lift before it travels."""
    from . import keyposes as kp, upper as upper_mod
    from .locomotion import style_args
    given = {k: v for k, v in dict(stance_width=stance_width, posture=posture,
                                   upper=upper).items() if v is not None}
    try:
        st = style_args(style, "idle", given)
    except ValueError as e:
        return {"error": str(e)}
    stance_width, posture, upper = st.get("stance_width"), st.get("posture"), st.get("upper")
    ctx, err = _setup(rig_name, forward, up, floor)
    if err:
        return err
    bm, rig, body, P = ctx
    if len(P.legs) != 2:
        return {"error": "%s has %d legs - a turn steps one foot round the other"
                % (rig_name, len(P.legs))}
    direction = str(direction).upper()[:1]
    if direction not in ("L", "R"):
        return {"error": "direction is L or R, not %r" % direction}
    frames = max(12, int(frames))
    up_v, fwd = P.up, P.fwd
    side_of = {l["name"]: (l["rest_root"] - P.centre).dot(P.lat) for l in P.legs}
    named = [l for l in P.legs if l.get("side") == direction]
    inside = named[0] if named else max(
        P.legs, key=lambda l: side_of[l["name"]] * (1.0 if direction == "L" else -1.0))
    outside = [l for l in P.legs if l is not inside][0]
    toward = inside["rest_root"] - P.centre
    toward = (toward - up_v * toward.dot(up_v)).normalized()
    # turning towards the inside leg's side: forward swings onto `toward`
    axis = up_v if up_v.cross(fwd).dot(toward) > 0.0 else -up_v
    yaw_sign = 1.0 if direction == "L" else -1.0

    shifts = {l["name"]: (kp.stance_shift(P, l, stance_width) if stance_width is not None
                          else Vector((0.0, 0.0, 0.0))) for l in P.legs}
    pivot = rig.data.bones[inside["end"] or inside["lower"]].tail_local + shifts[inside["name"]]
    total = math.radians(degrees)

    def about_pivot(theta):
        return (Matrix.Translation(pivot) @ Matrix.Rotation(theta, 4, axis)
                @ Matrix.Translation(-pivot))

    # the stepping foot is in the air over [A, B] of the clip; the turn runs inside that
    A, B = 0.12, 0.88

    def step_u(t):
        return max(0.0, min(1.0, (t - A) / (B - A)))

    def travel(u):
        return motion.smoothstep(max(0.0, min(1.0, (u - 0.12) / 0.76)))

    L_leg = P.leg_len
    start = outside["rest_eff"] + shifts[outside["name"]]
    end = about_pivot(total) @ start
    hip_half = 0.5 * abs(side_of[inside["name"]] - side_of[outside["name"]])
    lean_side = 1.0 if side_of[inside["name"]] > 0.0 else -1.0

    params = upper_mod.resolve(P, upper, upper_mod.idle_defaults())
    stance = {l["name"]: {"target": (lambda p, limb, posed, s=shifts[l["name"]]: limb["rest_eff"] + s)}
              for l in P.legs}
    U = upper_mod.Upper(P, params, posture=posture, stance=stance) if params and P.arms else None

    def key_at(t):
        u = step_u(t)
        theta = total * travel(u)
        inv = about_pivot(theta).inverted()
        # the foot's path over the floor, carried into the turning body's frame
        world = start.lerp(end, travel(u)) + up_v * (lift * L_leg * math.sin(math.pi * u))
        limbs = dict(stance)
        limbs[outside["name"]] = {"target": (lambda p, limb, posed, g=inv @ world: g),
                                  "planted": 1.0}
        if U is not None:
            limbs.update(U.idle_key(0.0))
        lean = math.sin(math.pi * min(1.0, max(0.0, (t - 0.02) / 0.96)))
        return kp.Key(limbs=limbs, sway=shift * 2.0 * hip_half * lean * lean_side,
                      drop=0.01 * L_leg * lean, posture=posture, head_level=0.5), theta

    def sample(t):
        key, theta = key_at(t)
        posed, infos = P.pose(key)
        M = about_pivot(theta)
        return {n: M @ m for n, m in posed.items()}, infos

    def check(keyed, ev, infos_by_frame):
        return _check_common(body, bm, keyed, ev, infos_by_frame, planted=[],
                             posed_limbs=P.legs, rest_floor=floor, starts_at_rest=False,
                             skid=True)

    keyed, infos, action, report = upper_mod.author_clear(
        U, rig_name, bm, lambda smp: _author_samples(body, rig, action_name, smp, fps, check),
        lambda: [sample((f - 1) / float(frames)) for f in range(1, frames + 2)])
    if "error" in report:
        return report
    origin_end = about_pivot(total) @ Vector((0.0, 0.0, 0.0))
    scale = sum(rig.matrix_world.to_scale()) / 3.0
    report.update({"rig": rig_name, "action": action.name, "frames": [1, frames + 1],
                   "fps": bpy.context.scene.render.fps, "stance_width": stance_width,
                   "posture": dict(posture) if posture else None,
                   "upper": U.report() if U is not None else None,
                   "turn": {"yaw_deg": round(yaw_sign * degrees, 3),
                            "pivot_leg": inside["name"],
                            "pivot_m": [round(x * scale, 4) for x in pivot],
                            "end_offset_m": [round(x * scale, 4) for x in origin_end],
                            # how far each foot slid along the floor while on it, the pivot
                            # included, against the check's tolerance - the planted-pivot proof
                            # the manifest carries once the build report is gone
                            "floor_skid_m": report.get("floor_skid"),
                            "skid_tolerance_m": report.get("tolerance")}})
    return report


RUN_GAIT = {2: "walk", 4: "trot", 6: "tripod"}


def move_set(rig_name, prefix=None, forward="-Y", up="Z", floor=0.0, fps=None,
             roles=("Idle", "Walk", "Trot", "Run", "Crouch", "CrouchWalk", "Jump",
                    "Slide", "SlideRecover", "SlideToCrouch"),
             # also known, not made unless asked: "TurnL", "TurnR" (`turn`)
             walk_froude="walk", trot_froude="trot", run_froude="sprint",
             legacy_gaits=False, options=None, variability=None, derive=False, mass=None):
    """Author a playable move set for one creature. Returns {role: report}.

    `options` is {role: {keyword: value}}, handed to that role's maker over its
    defaults - so each gait can have its own speed, hip drop and stance, and the
    idle the same stance and posture:

        options={"Idle": {"stance_width": 1.0, "posture": hunch},
                 "Walk": {"froude": 0.06, "max_drop": 0.06, "stance_width": 1.0,
                          "posture": hunch}}

    Walk, Trot and Run take `locomotion.cycle`'s keywords (froude there
    overrides walk_froude and friends), Idle takes `idle`'s.

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

    `derive=True` measures the build (`morphology.derive_style`: trunk-to-leg ratio, stockiness,
    mass - `mass` as `morphology.measure`) and lays the style it implies UNDER each role's own style,
    key by key, for the roles that take a style (Idle, the gaits, the turns). A body inside the
    human range derives {} and its clips are exactly the ones `derive=False` gives. Each of those
    roles' reports then carries `morphology`: what was measured and the style derived.

    `variability` is this character's `[variability]` (`variability.py`): a fixed
    left/right asymmetry drawn once from its seed and baked into the gait clips -
    arm swing, step length, shoulder dip and arm lag. It reaches the roles
    `locomotion.cycle` authors (Walk, Trot, Run) and nothing else, because only a
    cycle has two sides taking turns; an idle, a crouch or a jump is unchanged. The
    default is None, and `asymmetry = 0` is the identity, so a character that asks
    for nothing gets the clips it always got. An explicit `variability` in `options`
    for one role beats this.

    For the engine side, `locomotion.engine_manifest` turns these reports into
    the gait and contact-schedule entries a controller reads. Each report is also
    stored on its action (`stored.store`), so that works in a later session too.
    """
    bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return {"error": bm["error"]}
    n_legs = len([l for l in bm["limbs"] if l["role"] == "leg"])
    prefix = prefix or rig_name
    name = lambda role: "%s_%s" % (prefix, role)
    common = dict(forward=forward, up=up, floor=floor, fps=fps)
    # role -> (maker, its default keywords); `options` are laid over the defaults
    makers = {
        "Idle": (idle, dict(action_name=name("Idle"))),
        "Walk": (gait_cycle, dict(depth=0.0, stride=0.45, lift=0.10, frames=32, bob=0.01,
                                  sway=0.01, lean_degrees=0.0, tail_lift=8.0,
                                  tail_swing=8.0, action_name=name("Walk"))),
        # Start a run nearly straight-legged and let reach add flex only where a
        # body needs it: a flexed run folded the rat's wrists into the floor,
        # which shrank its stride to 3 cm. Straight, it ran at 3x its walk.
        "Run": (gait_cycle, dict(depth=0.05, stride=0.45, lift=0.10, frames=12, bob=0.02,
                                 sway=0.0, lean_degrees=0.0,
                                 gait_name=RUN_GAIT.get(n_legs, "tripod"),
                                 tail_lift=20.0, tail_swing=5.0, action_name=name("Run"))),
        "Crouch": (crouch, dict(depth=0.6, action_name=name("Crouch"))),
        "CrouchWalk": (gait_cycle, dict(depth=0.6, tail_swing=6.0,
                                        action_name=name("CrouchWalk"))),
        "Jump": (jump, dict(action_name=name("Jump"))),
        "TurnL": (turn, dict(direction="L", action_name=name("TurnL"))),
        "TurnR": (turn, dict(direction="R", action_name=name("TurnR"))),
        "Slide": (slide, dict(action_name=name("Slide"))),
        "SlideRecover": (slide_recover, dict(to="stand", action_name=name("SlideRecover"),
                                             slide_clip=name("Slide"),
                                             crouch_clip=name("Crouch"))),
        "SlideToCrouch": (slide_recover, dict(to="crouch", action_name=name("SlideToCrouch"),
                                              slide_clip=name("Slide"),
                                              crouch_clip=name("Crouch"))),
    }
    if not legacy_gaits:
        from . import locomotion
        makers["Walk"] = (locomotion.cycle, dict(froude=walk_froude, action_name=name("Walk")))
        makers["Run"] = (locomotion.cycle, dict(froude=run_froude, action_name=name("Run")))
        makers["Trot"] = (locomotion.cycle, dict(froude=trot_froude, action_name=name("Trot")))
    else:
        roles = [r for r in roles if r != "Trot"]
    options = dict(options or {})
    # A turn starts and ends standing as the idle stands, so it takes the
    # idle's stance, posture and style unless given its own.
    for t in ("TurnL", "TurnR"):
        held = {k: v for k, v in options.get("Idle", {}).items()
                if k in ("stance_width", "posture", "style")}
        if held:
            options[t] = dict(held, **options.get(t, {}))
    unknown = set(options) - set(makers)
    if unknown:
        return {"error": "options for unknown roles: " + ", ".join(sorted(unknown))}
    if variability:
        from . import locomotion as loco_mod
        for role, (fn, _kw) in makers.items():
            if fn is loco_mod.cycle:
                options[role] = dict({"variability": variability}, **options.get(role, {}))
    styled = ()
    if derive:
        from . import locomotion as loco_mod, morphology
        measured = morphology.measure(bm, mass=mass)
        derived = morphology.derive_style(bm, measured=measured)
        styled = [role for role, (fn, _kw) in makers.items() if fn in (idle, turn, loco_mod.cycle)]
        if derived:
            for role in styled:
                opts = dict(options.get(role, {}))
                opts["style"] = morphology.merge_styles(derived, opts.get("style"))
                options[role] = opts
    out = {}
    for role in roles:
        fn, kw = makers[role]
        out[role] = fn(rig_name, **dict(common, **dict(kw, **options.get(role, {}))))
        if role in styled and isinstance(out[role], dict) and "error" not in out[role]:
            out[role]["morphology"] = {"measured": measured, "derived": derived}
    stored.store(out, rig_name)
    return out
