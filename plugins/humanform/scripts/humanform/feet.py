"""A foot plan: how many toes carry the ground, what pads them, and what grows on their ends (08 fantasy
species, layer 5, beside the leg plan).

    feet.validate({"plan": "paw", "toes": 4})       # standard library only: species_design calls it
    rep = feet.apply(human, "paw")                  # after legs.apply, before tail.apply

`legs.py` says where a leg's segments point - it is what turns a plantigrade leg digitigrade. It does not
change what is on the end of it, and that was the flaw the first gnoll showed in Godot: a raised hock over a
human foot with five long toes lying flat reads as a person on tiptoe, not as a paw. This is the other half,
and it is parameters rather than names: a paw and a hoof are two settings of one plan, with a human foot as
the setting that changes nothing.

- **`toes`** is how many toes the foot ends in. The five hm08 toes are never deleted (the vertex order is what
  the skin regions and the brow fits index): they are **fused**, moved onto the axes of the `toes` groups they
  are split into, fully at the tips and not at all at the ball, so a four-toed paw has four toes and a cloven
  hoof two. `width` fattens what a fused group becomes, `splay` spreads the groups across the foot.
- **The pads** are three dome displacements on the sole, in toe lengths, so they scale with the body:
  **`pad`** under the standing ball (the metacarpal pad a digitigrade foot walks on), **`toe_pad`** under each
  toe's own tip, and **`heel_pad`** at the back of the foot. The body is re-stood on the floor afterwards, so
  a pad adds its own thickness under the foot the way an animal's does.
- **The nail** is `nail` (hm08's own toenails, a human foot), `claw` or `hoof`. A claw and a hoof are the SAME
  mechanism the head's horns and tusks use (`features._part`: a tapered, curved tube with `length`,
  `base_radius`, `tip_radius`, `curve`, `curl` and `sink`) - a claw is data, not a mesh. A hoof is that
  mechanism at its blunt extreme: short, nearly as wide at the tip as the base, sunk far enough to swallow the
  toe it caps. Each part is skinned 100% to the toe bone, in `<human>_footparts`.
- **The check** (`contact`): what the plan says carries the ground must be the lowest thing on the foot. A claw
  whose tip reaches below the pads would walk the creature on its nails; a hoof that does not reach below the
  flesh is not carrying anything. Both are refused with the millimetres measured.

Presets: `human` (5 toes, no pads, hm08's nails - the plan that changes nothing), `paw`, `hoof`.
"""

from __future__ import annotations

import math

try:                     # validate() is standard library only: species_design and the spec check call it
    import numpy as np
except ImportError:      # pragma: no cover
    np = None

PROP = "hf_feet"
PARTS_SUFFIX = "_footparts"
PLANS = ("human", "paw", "hoof")
KEYS = {"plan", "toes", "splay", "width", "pad", "toe_pad", "heel_pad", "nail", "claw"}
NAILS = ("nail", "claw", "hoof")
HORN = (0.22, 0.19, 0.17)
# pads and parts are fractions of the TOE's own length, so a gnome's paw and a troll's are the same paw
PRESETS = {
    "human": {"toes": 5, "splay": 1.0, "width": 1.0, "pad": 0.0, "toe_pad": 0.0, "heel_pad": 0.0, "nail": "nail"},
    "paw":   {"toes": 4, "splay": 1.15, "width": 1.35, "pad": 0.14, "toe_pad": 0.11, "heel_pad": 0.08,
              "nail": "claw"},
    "hoof":  {"toes": 2, "splay": 0.45, "width": 2.2, "pad": 0.06, "toe_pad": 0.04, "heel_pad": 0.10,
              "nail": "hoof"},
}
# Which LEG ratios go with each foot: a paw belongs on a dog's leg and a hoof on a goat's (humanform.legs
# RATIOS). The pipeline takes these as the leg plan's default when the species names a foot and leaves the
# leg's ratios unsaid, because a paw on a human-proportioned leg is exactly the thing that read wrong.
LEG_RATIOS = {"human": None, "paw": "canine", "hoof": "caprine"}
LIMITS = {"toes": (1, 5), "splay": (0.3, 2.0), "width": (0.5, 3.0),
          "pad": (0.0, 0.6), "toe_pad": (0.0, 0.5), "heel_pad": (0.0, 0.5)}
# the attached part each nail kind is, in toe lengths ([out, forward, up] for vectors, as features does)
NAIL_PARTS = {
    # `direction` is "normal", which for these anchors is the toe's OWN axis: a claw follows the toe it grows
    # on however the splay has turned it, and `curve` bends the tip down from there
    "claw": {"kind": "horn", "length": 0.45, "base_radius": 0.13, "tip_radius": 0.05, "sink": 0.6,
             "direction": "normal", "curve": [0.0, 0.06, -0.55], "rings": 9, "segments": 10,
             "color": list(HORN), "roughness": 0.35},
    # a hoof is the same tube gone blunt: short, almost as wide at the tip, and sunk deep enough to cap the toe
    "hoof": {"kind": "horn", "length": 0.45, "base_radius": 0.24, "tip_radius": 0.85, "sink": 0.8,
             "direction": "normal", "curve": [0.0, -0.10, -1.30], "rings": 6, "segments": 14,
             "color": list(HORN), "roughness": 0.30},
}
PAD_RADIUS = {"pad": 0.85, "toe_pad": 0.40, "heel_pad": 0.70}   # each dome's reach, in toe lengths
# WHERE THE FOOT WILL STAND, as fractions of the digit length forward of the ball: the pad under the standing
# ball at 0, the toe pads at 0.75 of each toe. `humanform.legs` solves the stance against this, so the body is
# balanced over the patch it will really have rather than over the plantigrade foot the warp balanced it on.
# MEASURED on built bodies (`balance` reports `patch_digits`, which is this), not assumed: a paw stands on the
# pads under its ball and its toes and reads 0.0-0.75; a hoof's horn curves down hard and its lowest point sits
# at 0.49, not out at the toe's end where the horn is anchored.
PATCH = {"human": None, "paw": (0.0, 0.75), "hoof": (0.40, 0.60)}
BALANCE_MARGIN = 0.10     # of the patch's own length: how far inside its edges the body's centre must sit
BALANCE_ABS = 0.010       # ... but never more than this, because an unguligrade foot stands on a POINT: the
                          # satyr's two hooves make a patch 0 mm long, and a share of nothing is nothing
WIDTH_DEPTH = 0.35        # the share of `width` a fused group takes THROUGH the foot as well as across
SOLE_BAND = 0.55          # of the foot's height: how far up the foot a pad's displacement reaches
NAIL_DOWN = 0.15          # the steepest an attached nail may start off horizontal (sine of the angle)
HOOF_STAND = 0.006        # metres a solved hoof stands below the flesh: the horn carries, not the pads
CLAW_CLEAR = 0.004        # ... and metres a solved claw's tip keeps ABOVE them: the pads carry
NAIL_LENGTH = (0.15, 1.6)  # toe lengths a solved nail may come out at: past it, it is a stilt, not a nail
CONTACT_BAND = 0.004      # metres above the lowest point that still counts as touching the ground
CONTACT_TOL = 0.002       # metres: how far the wrong part of the foot may be the lowest before it is refused


def normalise(spec):
    """A foot plan as a dict with every key filled in. A preset name is a shorthand."""
    if spec is None:
        spec = "human"
    if isinstance(spec, str):
        spec = {"plan": spec}
    plan = (spec or {}).get("plan", "human")
    out = dict(PRESETS.get(plan, PRESETS["human"]))
    out["plan"] = plan
    for k, v in (spec or {}).items():
        out[k] = v
    return out


def validate(spec):
    """[] or the problems with a `feet` block, each naming its range. Standard library only."""
    if spec is None or spec == "human":
        return []
    if not isinstance(spec, (str, dict)):
        return [f"foot must be one of {', '.join(PLANS)}, or a table of them, not {type(spec).__name__}"]
    if isinstance(spec, str):
        return [] if spec in PLANS else [f"foot = {spec!r}: one of {', '.join(PLANS)}"]
    out = []
    plan = spec.get("plan", "human")
    if plan not in PLANS:
        out.append(f"foot.plan = {plan!r}: one of {', '.join(PLANS)} (each is a starting point; every knob "
                   f"below can be given beside it)")
    out += [f"foot: unknown key {k!r} - it takes {', '.join(sorted(KEYS))}" for k in sorted(set(spec) - KEYS)]
    for k in ("toes", "splay", "width", "pad", "toe_pad", "heel_pad"):
        if k in spec:
            lo, hi = LIMITS[k]
            v = spec[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                what = ("toes the foot ends in; the five are fused onto that many, never deleted" if k == "toes"
                        else "how far the toe groups spread across the foot" if k == "splay"
                        else "how much fatter a fused toe group is" if k == "width"
                        else "the pad's depth, in toe lengths")
                out.append(f"foot.{k} = {v!r}: a number in {lo}..{hi} ({what})")
    if "toes" in spec and isinstance(spec["toes"], (int, float)) and not isinstance(spec["toes"], bool) \
            and spec["toes"] != int(spec["toes"]):
        out.append(f"foot.toes = {spec['toes']!r}: a whole number of toes")
    if "nail" in spec and spec["nail"] not in NAILS:
        out.append(f"foot.nail = {spec['nail']!r}: one of {', '.join(NAILS)} ('nail' leaves hm08's own toenails; "
                   f"'claw' and 'hoof' are attached parts on the toe bone)")
    claw = spec.get("claw")
    if claw is not None:
        if not isinstance(claw, dict):
            out.append("foot.claw must be a table of the attached part's own keys (length, base_radius, "
                       "tip_radius, curve, curl, direction, sink, color, roughness)")
        else:
            allowed = {"length", "base_radius", "tip_radius", "curve", "curl", "curl_axis", "direction",
                       "sink", "color", "roughness", "rings", "segments", "kind"}
            out += [f"foot.claw: unknown key {k!r} - it takes {', '.join(sorted(allowed))}"
                    for k in sorted(set(claw) - allowed)]
            for k in ("length", "base_radius"):
                if k in claw and (isinstance(claw[k], bool) or not isinstance(claw[k], (int, float))
                                  or not 0.02 <= claw[k] <= 3.0):
                    out.append(f"foot.claw.{k} = {claw[k]!r}: a number in 0.02..3.0 (toe lengths)")
            if spec.get("nail", PRESETS.get(plan, PRESETS['human'])["nail"]) == "nail":
                out.append("foot.claw is given but foot.nail is 'nail': a claw's shape needs nail = 'claw' "
                           "or 'hoof'")
    return out


# ---------------------------------------------------------------------------- reading the foot


def _smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _group_verts(human, name):
    g = human.vertex_groups.get(name)
    if g is None:
        return np.array([], int)
    return np.array([v.index for v in human.data.vertices
                     if any(e.group == g.index and e.weight > 0.5 for e in v.groups)], int)


def _spread(co, idx):
    """The size of a set of vertices, as the inventory measures a part (the diagonal of its bounding box)."""
    if not len(idx):
        return 0.0
    P = co[idx]
    return float(np.linalg.norm(P.max(axis=0) - P.min(axis=0)))


def _toe_lines(human, side, n_all):
    """The five toes of one foot as polylines, from MPFB's own joint helpers (`joint-l-toe-<n>-<k>`): the
    anatomy of the foot, read off the body rather than guessed from where vertices happen to lie."""
    letter = "l" if side == "L" else "r"
    me = human.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    by_group = {}
    for g in human.vertex_groups:
        if g.name.startswith(f"joint-{letter}-toe-"):
            by_group[g.name] = g.index
    if not by_group:
        return None
    members = {name: [] for name in by_group}
    want = {idx: name for name, idx in by_group.items()}
    for v in me.vertices:
        for e in v.groups:
            if e.group in want and e.weight > 0.5:
                members[want[e.group]].append(v.index)
    lines = []
    for toe in range(1, 6):
        pts = []
        for j in range(1, 6):
            idx = members.get(f"joint-{letter}-toe-{toe}-{j}")
            if idx:
                pts.append(co[np.array(idx)].mean(axis=0))
        if len(pts) >= 2:
            lines.append(np.array(pts))
    return lines if len(lines) == 5 else None


def _nearest_line(P, line):
    """Distance from each point of P to a polyline, and how far along it (0..1) the nearest point is."""
    best = np.full(len(P), 1e30)
    at = np.zeros(len(P))
    seg = line[1:] - line[:-1]
    ln = np.linalg.norm(seg, axis=1)
    cum = np.concatenate([[0.0], np.cumsum(ln)])
    total = max(float(cum[-1]), 1e-9)
    for i in range(len(seg)):
        d = seg[i]
        dd = max(float(np.dot(d, d)), 1e-12)
        t = np.clip(((P - line[i]) @ d) / dd, 0.0, 1.0)
        q = line[i][None, :] + t[:, None] * d[None, :]
        dist = np.linalg.norm(P - q, axis=1)
        hit = dist < best
        best[hit] = dist[hit]
        at[hit] = (cum[i] + t[hit] * ln[i]) / total
    return best, at


def _groups(n_src, n_dst):
    """Which of `n_src` toes each of `n_dst` groups takes: contiguous and as even as the count allows, counted
    from the big toe, so 5 -> 4 fuses the two small toes and 5 -> 2 makes two even halves."""
    if n_dst >= n_src:
        return [[i] for i in range(n_src)]
    if n_dst == 1:
        return [list(range(n_src))]
    out, start = [], 0
    left = n_src
    for g in range(n_dst):
        take = int(round(left / (n_dst - g)))
        take = max(1, min(take, left - (n_dst - g - 1)))
        out.append(list(range(start, start + take)))
        start += take
        left -= take
    return out


def apply(human, spec, report=None, verbose=False):
    """Reshape a rigged body's feet to a foot plan, in place: the toes fused onto `toes` groups, the pads, and
    the claws or hooves as attached parts. Returns the report. Raises ValueError, with the measurement in the
    message, when the plan cannot be built or the wrong part of the foot would carry the ground."""
    import bpy
    from mathutils import Vector
    from . import body as _body, delta, graft, look
    from . import features as feat
    from .species import _Rig

    problems = validate(spec)
    if problems:
        raise ValueError("; ".join(problems))
    p = normalise(spec)
    rep = {} if report is None else report
    rep.update({"plan": p["plan"], "parameters": {k: p[k] for k in sorted(KEYS) if k in p}})
    if p["plan"] == "human" and p == normalise("human"):
        rep["changed"] = False
        return rep

    human = _body.obj(human)
    rig = _body.rig_of(human)
    if rig is None:
        raise ValueError(f"{human.name} has no rig: feet.apply runs after scaffold.finish")
    rigd = _Rig(rig)
    if not rigd.legs:
        raise ValueError(f"{rig.name}: no legs, so no feet to plan")
    rep["flattened_keys"] = graft._flatten_keys(human)

    me = human.data
    n_all = len(me.vertices)
    body_n = delta.BODY_VERTS
    co = np.empty(n_all * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).copy()
    gi = {g.index: g.name for g in human.vertex_groups}
    nails = _group_verts(human, "toenails")
    nail_before = _spread(co, nails)
    host_idx = None            # the foot the inventory measures the nails against (its own +x half)

    def dominated(bone):
        out = []
        for v in me.vertices:
            best, bw = None, 0.0
            for e in v.groups:
                nm = gi.get(e.group)
                if nm in rig.data.bones and e.weight > bw:
                    best, bw = nm, e.weight
            if best == bone:
                out.append(v.index)
        return np.array(out, int)

    n_dst = int(p["toes"])
    sides = {}
    lowest_before = float(co[:body_n, 2].min())
    for side, chain in sorted(rigd.legs.items()):
        if len(chain) < 4 or not all(chain[:4]):
            raise ValueError(f"leg {side} has no toe segment: a foot plan needs the four leg bones")
        foot_b, toe_b = chain[2], chain[3]
        lines = _toe_lines(human, side, n_all)
        if lines is None:
            raise ValueError(f"foot {side}: MPFB's toe joint helpers (joint-{'l' if side == 'L' else 'r'}-toe-N-K) "
                             "are not on this body, so its toes cannot be told apart")
        toe_idx = dominated(toe_b)
        foot_idx = dominated(foot_b)
        if not len(toe_idx):
            raise ValueError(f"foot {side}: no skin on {toe_b}")
        ball = np.array(rig.data.bones[toe_b].head_local)
        tipb = np.array(rig.data.bones[toe_b].tail_local)
        toe_len = float(np.linalg.norm(tipb - ball))
        lat = np.array([1.0 if side == "L" else -1.0, 0.0, 0.0])      # outward from the midline

        # 1. which toe each vertex belongs to, and how far down it, from the joint helpers
        P = co[toe_idx]
        near = [_nearest_line(P, l) for l in lines]
        dists = np.stack([d for d, _ in near])
        along = np.stack([a for _, a in near])
        own = np.argmin(dists, axis=0)
        u = along[own, np.arange(len(P))]

        # 2. each toe's own axis, and the target axis of the group it joins
        def axis_point(line, t):
            seg = line[1:] - line[:-1]
            ln = np.linalg.norm(seg, axis=1)
            cum = np.concatenate([[0.0], np.cumsum(ln)])
            s = float(np.clip(t, 0, 1)) * float(cum[-1])
            k = int(np.clip(np.searchsorted(cum, s) - 1, 0, len(seg) - 1))
            f = (s - cum[k]) / max(ln[k], 1e-9)
            return line[k] + seg[k] * f

        groups = _groups(5, n_dst)
        of_group = {t: g for g, members in enumerate(groups) for t in members}
        centre_x = float(np.mean([axis_point(l, 0.0)[0] for l in lines]))
        moved = P.copy()
        w = _smooth(u / 0.55)[:, None]                 # nothing at the ball, all of it by mid-toe
        for i in range(len(P)):
            t = int(own[i])
            src = axis_point(lines[t], float(u[i]))
            g = groups[of_group[t]]
            dst = np.mean([axis_point(lines[m], float(u[i])) for m in g], axis=0)
            dst = dst.copy()
            dst[0] = centre_x + (dst[0] - centre_x) * float(p["splay"])
            # `width` fattens the group ACROSS the foot, where the toes it swallowed used to be; a fused toe
            # is wider, not proportionally taller, so the part of the offset out of that direction takes only
            # a share of it (WIDTH_DEPTH). Scaling the whole offset doubled the toes' depth and pushed the
            # sole 3 cm through the floor.
            off = P[i] - src                            # its own place round its own toe
            side_off = float(np.dot(off, lat)) * lat
            moved[i] = (src + side_off * float(p["width"])
                        + (off - side_off) * (1.0 + (float(p["width"]) - 1.0) * WIDTH_DEPTH)
                        + (dst - src) * float(w[i, 0]))
        co[toe_idx] = moved

        # 3. the pads: domes pressed down into the sole, in toe lengths
        sole = np.concatenate([toe_idx, foot_idx])
        S = co[sole]
        foot_lo, foot_hi = float(S[:, 2].min()), float(S[:, 2].max())
        band = max(SOLE_BAND * (foot_hi - foot_lo), 1e-4)
        anchors = []
        if float(p["pad"]) > 0:
            anchors.append((ball[:2], float(p["pad"]), PAD_RADIUS["pad"]))
        if float(p["heel_pad"]) > 0:
            rear = S[np.argmax(S[:, 1])]                # forward is -Y: the rearmost point of the foot
            anchors.append((rear[:2], float(p["heel_pad"]), PAD_RADIUS["heel_pad"]))
        if float(p["toe_pad"]) > 0:
            for g in groups:
                q = np.mean([axis_point(lines[m], 0.75) for m in g], axis=0)
                q = q.copy()
                q[0] = centre_x + (q[0] - centre_x) * float(p["splay"])
                anchors.append((q[:2], float(p["toe_pad"]), PAD_RADIUS["toe_pad"]))
        for centre, depth, radius in anchors:
            r = radius * toe_len
            d = np.linalg.norm(S[:, :2] - centre[None, :], axis=1)
            near = 1.0 - _smooth(d / max(r, 1e-9))
            low = 1.0 - _smooth((S[:, 2] - foot_lo) / band)
            S[:, 2] -= depth * toe_len * near * low
        co[sole] = S

        if side == "L":
            host_idx = np.concatenate([toe_idx, foot_idx])
            host_before = _spread(co, host_idx)
        sides[side] = {"toe_bone": toe_b, "toe_len": round(toe_len, 4), "lines": lines, "groups": groups,
                       "centre_x": centre_x, "axis_point": axis_point, "toe_idx": toe_idx, "lat": lat,
                       "ball": ball, "own": own, "u": u}

    me.vertices.foreach_set("co", co.ravel())
    me.update()

    # 4. re-stand: a pad adds its own thickness under the foot, as an animal's does
    dz = max(0.0, lowest_before - float(co[:body_n, 2].min()))
    if dz > 1e-6:
        _lift(human, rig, dz)
        co[:, 2] += dz
        for s in sides.values():
            s["ball"] = s["ball"] + np.array([0.0, 0.0, dz])
            s["lines"] = [l + np.array([0.0, 0.0, dz]) for l in s["lines"]]
    rep["pad_lift_mm"] = round(dz * 1000, 2)

    # where each toe group now ENDS, on the finished skin: the centroid of its distal flesh, and the direction
    # from the group's mid-toe to it. A claw or a hoof grows from there.
    me.vertices.foreach_get("co", co.reshape(-1))
    co = co.reshape(-1, 3)
    for side, s in sides.items():
        tips = []
        for members in s["groups"]:
            sel = np.isin(s["own"], members)
            far = sel & (s["u"] >= 0.88)
            if not far.any():
                far = sel & (s["u"] >= float(np.percentile(s["u"][sel], 85)))
            mid = sel & (s["u"] >= 0.45) & (s["u"] < 0.75)
            P = co[s["toe_idx"][far]]
            # a nail grows out of the TOP of the toe's end, not its middle: the upper half of the distal
            # flesh. Centred, a claw's base ring dipped below the pads whatever its length was.
            up_half = P[P[:, 2] >= float(np.median(P[:, 2]))]
            q = (up_half if len(up_half) else P).mean(axis=0)
            root = co[s["toe_idx"][mid]].mean(axis=0) if mid.any() else s["ball"]
            n = q - root
            n = n / max(float(np.linalg.norm(n)), 1e-9)
            # a toe measured tip-minus-middle points steeply down on a padded foot, and a claw grown along it
            # dives straight through the floor: the anchor's direction is held to NAIL_DOWN of down at most,
            # and the part's own `curve` does the bending from there
            if n[2] < -NAIL_DOWN:
                n = np.array([n[0], n[1], -NAIL_DOWN])
                n = n / max(float(np.linalg.norm(n)), 1e-9)
            tips.append((q, n))
        s["tip"] = tips

    # 5. the nails: hm08's own, or an attached part per toe group (the head's horn mechanism)
    parts_rep = None
    if p["nail"] != "nail":
        # A hoof stands the creature on horn and a claw must not. Which LENGTH does either depends on the leg
        # plan's toe, the fuse and the pads - the same fraction that put a paw's claws 13 mm through the floor
        # left the satyr's hoof 11 mm in the air - so it is solved against the contact check itself: build,
        # measure what carries, correct, build again. An explicit `claw.length` is taken as given and held to
        # the same check.
        want = (-HOOF_STAND) if p["nail"] == "hoof" else CLAW_CLEAR
        fixed = "length" in (p.get("claw") or {})
        L = None
        tries = []
        for _ in range(1 if fixed else 6):
            parts_rep = _build_claws(human, rig, sides, p, feat, look, bpy, Vector, length=L)
            L = parts_rep["length_toe_lengths"]
            gap = (contact(human, p, rig)["gap_mm"] or 0.0) / 1000.0
            tries.append([round(L, 4), round(gap * 1000, 2)])
            if abs(gap - want) <= 0.0012:
                break
            # the nail's reach below the flesh is very nearly linear in its length: step by the shortfall over
            # the length that produced it, with the base ring's own dip as the offset
            if len(tries) >= 2 and abs(tries[-1][1] - tries[-2][1]) > 1e-6:
                slope = (tries[-1][0] - tries[-2][0]) / ((tries[-1][1] - tries[-2][1]) / 1000.0)
                L = float(np.clip(L + slope * (want - gap), 0.12, 2.8))
            else:
                L = float(np.clip(L + (gap - want) * 8.0, 0.12, 2.8))
        parts_rep["length_solved"] = not fixed
        parts_rep["length_tries"] = tries
        if not fixed and not NAIL_LENGTH[0] <= L <= NAIL_LENGTH[1]:
            raise ValueError(
                f"foot: a {p['nail']} that {'carries' if p['nail'] == 'hoof' else 'clears'} the pads on this "
                f"foot comes out {L:.2f} toe lengths long (outside {NAIL_LENGTH[0]}..{NAIL_LENGTH[1]}) - it is "
                f"reaching for the ground sideways. Curve it down harder (`claw.curve` z), sink it less "
                f"(`claw.sink`), or lighten `pad`/`toe_pad`")
    rep["parts"] = parts_rep

    rep["sides"] = {side: {k: s[k] for k in ("toe_bone", "toe_len") } | {"groups": s["groups"]}
                    for side, s in sides.items()}
    # What the plan did to hm08's own toenails, so the anatomy inventory grades them against the plan rather
    # than against a human foot: fusing five toes onto two draws the nails together, and that is the point.
    me.vertices.foreach_get("co", co.reshape(-1))
    co = co.reshape(-1, 3)
    # ... measured the way the inventory does: the nails' size over their HOST foot's, before and after
    if nail_before and host_idx is not None and host_before:
        rep["nail_ratio"] = round((_spread(co, nails) / _spread(co, host_idx))
                                  / (nail_before / host_before), 3)
    else:
        rep["nail_ratio"] = 1.0
    rep["changed"] = True
    rep["contact"] = contact(human, p, rig)
    bad = rep["contact"].get("problem")
    if bad:
        raise ValueError(bad)
    rep["balance"] = balance(human, rig)
    rig[PROP] = {"plan": p["plan"], "toes": int(p["toes"]), "nail": p["nail"]}
    human[PROP] = rig[PROP]
    if verbose:
        print("feet", p["plan"], rep["contact"])
    return rep


def _lift(human, rig, dz):
    """Everything up by dz: the rest bones and every mesh skinned to them. The floor is where the pads now are."""
    import bpy
    from mathutils import Vector
    from . import species
    for ob in species._skinned(rig):
        me = ob.data
        n = len(me.vertices)
        c = np.empty(n * 3)
        me.vertices.foreach_get("co", c)
        c = c.reshape(-1, 3)
        c[:, 2] += dz
        me.vertices.foreach_set("co", c.ravel())
        if me.shape_keys is not None:
            for kb in me.shape_keys.key_blocks:
                k = np.empty(n * 3)
                kb.data.foreach_get("co", k)
                k = k.reshape(-1, 3)
                k[:, 2] += dz
                kb.data.foreach_set("co", k.ravel())
        me.update()
    vl = bpy.context.view_layer
    prev, hidden = vl.objects.active, rig.hide_get()
    rig.hide_set(False)
    vl.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for eb in rig.data.edit_bones:
            eb.head = eb.head + Vector((0.0, 0.0, dz))
            eb.tail = eb.tail + Vector((0.0, 0.0, dz))
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        rig.hide_set(hidden)
        if prev is not None:
            vl.objects.active = prev


def _frames(sides):
    """The attached-part frame of each foot. `features._part` reads `scale` and the landmarks, and nothing a
    claw or a hoof sets reaches for the rest of a head's frame."""
    from types import SimpleNamespace
    out = {}
    for side, s in sorted(sides.items()):
        lm = {}
        for g in range(len(s["groups"])):
            # A claw grows out of the END OF THE TOE, so its anchor is the distal flesh of the group, measured
            # on the reshaped, padded mesh - not the joint line, whose last point sits inside the toe.
            q, n = s["tip"][g]
            lm[f"claw{g}.{side}"] = (q, n)
        out[side] = SimpleNamespace(co=None, nrm=None, faces=None, tree=None, lm=lm, scale=1.0)
    return out


def _lay(bm, feat, frames, sides, base, length, uv=None, on_face=None):
    """Build every nail into `bm` at `length` (in toe lengths). Returns (lowest z it reaches, the part rows)."""
    rows, lo = [], 1e30
    for side, s in sorted(sides.items()):
        L = s["toe_len"]
        for g in range(len(s["groups"])):
            at = dict(base)
            at["anchor"] = f"claw{g}.{side}"
            at["mirror"] = False
            at["length"] = float(length) * L
            at["base_radius"] = float(base["base_radius"]) * L
            at["bone"] = s["toe_bone"]
            faces, full = feat._part(bm, frames[side], at, 1.0, rows)
            for f in faces:
                for lp in f.loops:
                    lo = min(lo, float(lp.vert.co.z))
                if on_face is not None:
                    on_face(f, full, s)
    return lo, rows


def _build_claws(human, rig, sides, p, feat, look, bpy, Vector, length=None):
    """A claw or a hoof per toe group, built by the head's own attached-part mechanism (`features._part`) and
    skinned 100% to that foot's toe bone, in `<human>_footparts`."""
    import bmesh
    name = human.name + PARTS_SUFFIX
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    base = dict(NAIL_PARTS[p["nail"]])
    base.update(p.get("claw") or {})
    frames = _frames(sides)
    length = float(base["length"]) if length is None else float(length)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    mats, groups = [], {}

    def on_face(f, full, s):
        mat = look.material(f"{human.name}_{p['nail']}_part", srgb=tuple(full["color"]),
                            roughness=float(full["roughness"]))
        if mat not in mats:
            mats.append(mat)
        f.material_index = mats.index(mat)
        f.smooth = True
        for lp in f.loops:
            c = lp.vert.co
            lp[uv].uv = (0.5 + math.atan2(c.y, c.x) / (2 * math.pi), c.z)
            groups.setdefault(s["toe_bone"], set()).add(lp.vert)

    _, rows = _lay(bm, feat, frames, sides, base, length, uv=uv, on_face=on_face)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.verts.index_update()
    by_bone = {b: [v.index for v in vs] for b, vs in groups.items()}
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    for c in human.users_collection:
        c.objects.link(ob)
    ob.matrix_world = human.matrix_world.copy()
    for b, idx in by_bone.items():
        ob.vertex_groups.new(name=b).add(idx, 1.0, "REPLACE")
    ob.parent = rig
    ob.matrix_parent_inverse = rig.matrix_world.inverted()
    ob.modifiers.new("Armature", "ARMATURE").object = rig
    return {"object": name, "verts": len(me.vertices), "faces": len(me.polygons),
            "bones": sorted(by_bone), "parts": rows,
            "length_toe_lengths": round(length, 3)}


def nail_over_foot(human):
    """hm08's toenails, sized against the foot they sit on, exactly as the anatomy inventory measures a part
    against its host. Taken before and after the body plan, the ratio of the two IS the change the plan meant
    to make - a leg plan that shortens the toes and a foot plan that fuses five of them onto two both draw the
    nails together - so the inventory can be told that and go on grading the rest."""
    from . import body as _body
    from .species import _Rig
    human = _body.obj(human)
    rig = _body.rig_of(human)
    if rig is None:
        return None
    nails = _group_verts(human, "toenails")
    if not len(nails):
        return None
    rigd = _Rig(rig)
    # the shape as the body is DRAWN (basis plus every key at its value), which is what the anatomy inventory
    # measures; read off the raw base instead, this disagreed with it by 40% once the keys were flattened
    from .species import _Mesh
    mm = _Mesh(human, rig, rigd)
    co = mm.mixed(mm.keys) if mm.keys else mm.base
    me = human.data
    want = {b for ch in rigd.legs.values() for b in ch[2:4] if b}
    gi = {g.index: g.name for g in human.vertex_groups}
    host = []
    for v in me.vertices:
        best, bw = None, 0.0
        for e in v.groups:
            nm = gi.get(e.group)
            if nm in rig.data.bones and e.weight > bw:
                best, bw = nm, e.weight
        if best in want and co[v.index, 0] > 0:
            host.append(v.index)
    hs = _spread(co, np.array(host, int))
    return (_spread(co, nails) / hs) if hs > 1e-9 else None


def patch_of(spec):
    """The contact patch a foot plan will leave (`PATCH`), as fractions of the digit length forward of the
    ball, or None for a plantigrade human foot, which stands on its whole sole and is not solved against one.

    A paw stands on the pads under its ball and its toes, so its patch runs 0 to 0.75 of the digits; a hoof
    stands on the horn that caps the toe's END, which is why theirs sits past the digits' own length."""
    p = normalise(spec)
    return PATCH.get(p["plan"]) if p["nail"] != "hoof" else PATCH["hoof"]


def balance(human, rig=None):
    """Where the body's centre stands over the patch it ACTUALLY has, measured after the plan has run.

    `humanform.species._balance` balances a body over its plantigrade foot during the warp; a leg plan then
    moves the contact out from under it and a foot plan moves it again. Nothing re-checked that until the
    first gnoll stood with its centre 50 mm outside its paws and had two clips refused at export. This is the
    re-check: the sole's own lowest band, fore and aft, against the centre of every skinned vertex.
    """
    from . import body as _body
    from .species import _Rig, _skinned
    human = _body.obj(human)
    rig = rig or _body.rig_of(human)
    if rig is None:
        return None
    rigd = _Rig(rig)
    if not rigd.legs:
        return None
    me = human.data
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    want = {b for ch in rigd.legs.values() for b in ch[2:4] if b}
    gi = {g.index: g.name for g in human.vertex_groups}
    sole = []
    for v in me.vertices:
        best, bw = None, 0.0
        for e in v.groups:
            nm = gi.get(e.group)
            if nm in rig.data.bones and e.weight > bw:
                best, bw = nm, e.weight
        if best in want:
            sole.append(v.index)
    parts = _parts_object(human)
    pts = [co[np.array(sole, int)]] if sole else []
    if parts is not None and len(parts.data.vertices):
        pc = np.empty(len(parts.data.vertices) * 3)
        parts.data.vertices.foreach_get("co", pc)
        pts.append(pc.reshape(-1, 3))
    if not pts:
        return None
    P = np.concatenate(pts)
    lo = float(P[:, 2].min())
    band = P[P[:, 2] <= lo + CONTACT_BAND]
    # forward is -Y, as everywhere in this package
    back, front = -float(band[:, 1].max()), -float(band[:, 1].min())
    com = -float(np.concatenate([_verts(o) for o in _skinned(rig)])[:, 1].mean())
    sole = [round(back, 4), round(front, 4)]
    # THE CHECK'S OWN NUMBERS. The sole's lowest band is this module's measure; what refuses a clip at export
    # is rig-anything's - `keyposes.support` (the contact points its poser finds) against `motion.Body.com`
    # (the skinned body). Predicting the export means using the export's measure, so where rig-anything can be
    # imported it is, and the sole band stays in the report as the second opinion.
    source = "the sole's lowest band"
    try:
        from rig_analysis import bodymap as _bm, motion as _mo, keyposes as _kp
        b = _bm.build(rig.name)
        if "error" not in b:
            bod = _mo.Body(rig, b)
            lo, hi = _kp.support(_kp.Poser(bod))
            back, front = float(lo), float(hi)
            com = float(bod.com(bod.fk()).dot(b["fwd"]))
            source = "rig-anything's own support and centre of mass"
    except ImportError:
        pass
    span = max(front - back, 0.0)
    margin = min(com - back, front - com)
    limit = min(BALANCE_MARGIN * span, BALANCE_ABS)
    # the same patch in the units the prediction is written in: digit lengths forward of the ball, so a build
    # says what `PATCH` should be for its own foot plan rather than leaving it to be guessed
    toe_b = sorted(rigd.legs)[0]
    tb = rig.data.bones[rigd.legs[toe_b][3]]
    ball_f, dlen = -float(tb.head_local.y), max(float(tb.length), 1e-9)
    return {"com_fwd": round(com, 4), "patch_fwd": [round(back, 4), round(front, 4)],
            "measured_by": source, "sole_band_fwd": sole,
            "patch_digits": [round((back - ball_f) / dlen, 3), round((front - ball_f) / dlen, 3)],
            "digit_m": round(dlen, 4),
            "margin_m": round(margin, 4),
            "margin_share": round(margin / span, 3) if span > 1e-6 else None,
            "limit_m": round(limit, 4), "band_m": CONTACT_BAND,
            "failed": margin < limit}


def settle(human, legs_spec, rig=None, passes=4, report=None):
    """Move the feet under the body until it balances over the patch it ACTUALLY stands on.

    `humanform.species._balance` balances a body over its PLANTIGRADE foot during the warp. A leg plan then
    moves the contact out from under it and a foot plan moves it again - the pads and the horn - and where
    that patch ends up cannot be predicted from the plan's numbers: the same hoof measured 0.50 of a digit
    length forward of the ball on one build and 0.25 on the next, because the pads move with the leg. The
    first gnoll stood with its centre 50 mm outside its paws and had Crouch and MouthOpen refused at export,
    and its spec had to carry a hand-tuned stance.

    So it is measured and corrected rather than solved blind: measure the patch and the body's centre, move
    the ball by the difference (the leg plan's `stance`, whose targets are absolute, so re-applying it lands
    exactly where one pass with the final stance would), measure again. Two or three passes settle it.
    """
    from . import body as _body
    from . import legs as legs_mod
    from .species import _Rig
    human = _body.obj(human)
    rig = rig or _body.rig_of(human)
    rows = []
    b = balance(human, rig)
    for _ in range(passes):
        if not b or not b["failed"]:
            break
        rigd = _Rig(rig)
        side = sorted(rigd.legs)[0]
        chain = rigd.legs[side]
        hip = rig.data.bones[chain[0]].head_local
        ball = rig.data.bones[chain[3]].head_local
        hip_h = float(hip.z)
        cur = (-float(ball.y) + float(hip.y)) / max(hip_h, 1e-9)
        centre = 0.5 * (b["patch_fwd"][0] + b["patch_fwd"][1])
        want = cur + (b["com_fwd"] - centre) / max(hip_h, 1e-9)
        rows.append({"stance": round(cur, 4), "margin_mm": round(b["margin_m"] * 1000, 1),
                     "to": round(want, 4)})
        if abs(want - cur) * hip_h < 0.0005:
            break
        legs_mod.apply(human, dict(_as_dict(legs_spec), stance=want))
        b = balance(human, rig)
    if report is not None:
        report["settle"] = rows
        report["balance"] = b
    return b, rows


def _as_dict(spec):
    return {"plan": spec} if isinstance(spec, str) else dict(spec or {})


def _verts(ob):
    n = len(ob.data.vertices)
    c = np.empty(n * 3)
    ob.data.vertices.foreach_get("co", c)
    return c.reshape(-1, 3)


def _parts_object(human):
    import bpy
    return bpy.data.objects.get(human.name + PARTS_SUFFIX)


def contact(human, spec=None, rig=None):
    """What the foot actually stands on: the lowest of the pads (the body's own skin) and the lowest of the
    attached parts, and whether the right one carries.

    A claw is a claw because the pads take the weight and the claw does not; a hoof is a hoof because it does.
    Getting that wrong is invisible in a bone check and obvious in Godot - a creature walking on its nails.
    """
    from . import body as _body, delta
    human = _body.obj(human)
    p = normalise(spec)
    me = human.data
    n = len(me.vertices)
    c = np.empty(n * 3)
    me.vertices.foreach_get("co", c)
    c = c.reshape(-1, 3)
    pad = float(c[:delta.BODY_VERTS, 2].min())
    import bpy
    parts = bpy.data.objects.get(human.name + PARTS_SUFFIX)
    out = {"nail": p["nail"], "pad_z": round(pad, 5), "part_z": None, "gap_mm": None}
    if parts is None or not len(parts.data.vertices):
        out["problem"] = (f"foot: nail = {p['nail']!r} but no {human.name}{PARTS_SUFFIX} was built"
                          if p["nail"] != "nail" else None)
        return out
    pc = np.empty(len(parts.data.vertices) * 3)
    parts.data.vertices.foreach_get("co", pc)
    part_z = float(pc.reshape(-1, 3)[:, 2].min())
    out["part_z"] = round(part_z, 5)
    out["gap_mm"] = round((part_z - pad) * 1000, 2)
    if p["nail"] == "claw" and part_z < pad - CONTACT_TOL:
        out["problem"] = (f"foot: the claws reach {abs(out['gap_mm']):.1f} mm below the pads - the creature "
                          f"would walk on its nails. Shorten `claw.length`, or curve it further up "
                          f"(`claw.curve` up), or deepen `pad`/`toe_pad`")
    elif p["nail"] == "hoof" and part_z > pad - CONTACT_TOL:
        out["problem"] = (f"foot: the hoof stops {out['gap_mm']:.1f} mm above the flesh - the foot would stand "
                          f"on its pads with the hoof in the air. Lengthen `claw.length`, sink it less "
                          f"(`claw.sink`), or lighten `pad`/`toe_pad`")
    return out


def read(obj):
    """The plan `apply` left on a rig or a body, or None."""
    v = obj.get(PROP) if obj is not None else None
    return dict(v) if v else None
