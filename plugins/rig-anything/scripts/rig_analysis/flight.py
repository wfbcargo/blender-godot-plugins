"""Flight for any winged body: numbers from its size, and the clips to fly with.

`locomotion` gets a gait from one Froude number. A flying animal has its own
dimensionless rules, and they need only what the body map and the skin already
know - wing area, span and mass:

1. Wingbeat frequency follows size (Pennycuick 1990):
       f = 1.08 m^(1/3) g^(1/2) b^-1 S^(-1/4) rho^(-1/3)
   A second form (Pennycuick 1996, exponents reconstructed and dimension-
   checked) is reported beside it; they agree within ~10% on a pigeon.

2. Stroke amplitude shrinks with span (Nudds, Taylor & Thomas 2004), peak to
   peak in degrees:  theta = 67 b^-0.24
   and the tip travels A = b sin(theta / 2) peak to peak.

3. Cruising flyers of every kind sit at a Strouhal number St = f A / U of
   0.2-0.4 (Taylor, Nudds & Thomas 2003); birds flapping continuously at 0.21
   (Nudds et al. 2004). So cruise speed is U = f A / St.

4. Gliding is lift against weight: V = sqrt(2 m g / (rho S C_L)), with C_L 0.7
   at best glide (a jackdaw's 8.3 m/s, Rosen & Hedenstrom 2001) and 1.6 at the
   slowest (Tucker & Heine 1990). The sink rate is V / (L/D), and L/D rises
   with aspect ratio: 12.6 for a jackdaw, ~12 for condors, ~18 for an albatross.
   `ld_max = 4.6 sqrt(AR)` passes through those - a fit, labelled as one.

5. The downstroke takes 53-60% of the beat (Tobalske et al. 2007; Crandell &
   Tobalske 2015), and the upstroke flexes the wing to 65-93% of its span -
   less area moving up than down is what makes a flap lift at all.

What this does NOT know is the creature's mass beyond its skin. A mesh
volume times a density (850 kg/m3 default; birds are lighter than water from
air sacs, but no sourced figure was found) is a guess a designer should
override with `mass_kg`. The numbers then say plainly when a body could not
fly - a 100 kg dragon with 1.6 m2 of wing is loaded three times harder than
any bird that does - and the clips are authored anyway, because a game may want
the dragon regardless.

CLIPS
-----

    WingSpread  one-shot: ground rest (wings folded) -> spread and raised, feet
                planted. Played backwards it folds them.
    TakeOff     one-shot: load -> leap with the first, larger downstroke -> the
                Flap clip's first frame (measured seam)
    Flap        loop: one wingbeat, phase 0 at the top of the stroke
    Glide       loop: spread, a little dihedral, a slow balancing drift
    Dive        loop: wings half folded and swept back
    Land        one-shot: Glide's first frame (measured seam) -> flare, wings
                forward, legs reaching -> touchdown -> folded ground rest

Every clip is baked, played back through Blender and checked like every other
action here, plus: wings never pass into the body, never across the midline,
the downstroke sweeps more area than the upstroke, and the stroke amplitude
Blender plays is the one that was asked for.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from . import bodymap, keyposes as kp, motion, stored, wings as wing_mod

G = 9.81
RHO = 1.225
DENSITY = 850.0
# Mass of modelled wing skin as a share of the same volume of body: a design
# assumption, since a modelled wing is far thicker than the tissue it stands for.
WING_SKIN_SHARE = 0.25
ST_CRUISE = 0.21
CL_GLIDE = 0.7
CL_MAX = 1.6
DOWNSTROKE = 0.55
UPSTROKE_SPAN = 0.75
# Heaviest wing loading among birds that fly, N/m2 (large swans and bustards,
# ~20-25 kg/m2). Not from the sourced research - a sanity line, not physics.
MAX_BIRD_WING_LOADING = 250.0


# --------------------------------------------------------------------------
# numbers
# --------------------------------------------------------------------------

def mesh_volume(rig):
    """Skinned volume at rest, m3, and whether every mesh was closed."""
    import bmesh
    total, closed = 0.0, True
    for o in wing_mod._bound_meshes(rig):
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.transform(o.matrix_world)
        if any(not e.is_manifold for e in bm.edges):
            closed = False
        total += abs(bm.calc_volume(signed=True))
        bm.free()
    return total, closed


def wing_volume(rig, bm, w):
    """Volume enclosed by the skin a wing's bones dominate, armature units.

    That surface is open where the wing meets the body. The divergence theorem
    is taken about the shoulder joint, which lies on that cut, so the missing
    cap contributes almost nothing."""
    names = set(bodymap._descendants_names(rig.data.bones[w["upper"]], w["side"]))
    origin = w["root"]
    total = 0.0
    for cos, dom, polys in wing_mod.skin_table(rig):
        for poly in polys:
            if sum(1 for i in poly if dom[i] in names) * 2 < len(poly):
                continue
            a = cos[poly[0]] - origin
            for j in range(1, len(poly) - 1):
                b, c = cos[poly[j]] - origin, cos[poly[j + 1]] - origin
                total += a.dot(b.cross(c)) / 6.0
    return abs(total)


def pennycuick_1990(m, b, S, rho=RHO):
    return 1.08 * m ** (1 / 3) * G ** 0.5 / b * S ** -0.25 * rho ** (-1 / 3)


def pennycuick_1996(m, b, S, rho=RHO):
    return m ** (3 / 8) * G ** 0.5 * b ** (-23 / 24) * S ** (-1 / 3) * rho ** (-3 / 8)


def stroke_amplitude(b):
    """Peak-to-peak stroke angle, degrees (Nudds et al. 2004)."""
    return max(50.0, min(150.0, 67.0 * b ** -0.24))


def plan(poser, mass_kg=None, density=DENSITY, rho=RHO, strouhal=ST_CRUISE):
    """Everything a flight set needs from the body's size. See the module notes."""
    bm, rig = poser.bm, poser.rig
    wings = bm.get("wings", [])
    if not wings:
        return {"error": "%s has no wings" % rig.name}
    scale = sum(rig.matrix_world.to_scale()) / 3.0
    problems, notes = [], []
    areas = [w["area"] for w in wings if w["area"]]
    if len(areas) < len(wings):
        return {"error": "wing area needs a skinned mesh - found wings by name only"}
    roots = {w["side"]: w["root"] for w in wings}
    sep = (roots["L"] - roots["R"]).length if len(roots) == 2 else 0.0
    reach = sum(w["reach"] for w in wings) / len(wings)
    chord = sum(w["area"] / w["reach"] for w in wings) / len(wings)
    b = (sep + 2.0 * reach) * scale
    S = (sum(areas) + sep * chord) * scale * scale          # wings + body between
    vol, closed = mesh_volume(rig)
    wing_vol = sum(wing_volume(rig, bm, w) for w in wings) * scale ** 3
    if mass_kg is None:
        # A modelled wing is a slab centimetres thick; a real membrane or vane
        # is not. Counting it as body made a 1.9 m test bird weigh 22 kg.
        mass = (vol - wing_vol) * density + wing_vol * density * WING_SKIN_SHARE
        mass_source = ("body %.4f m3 x %.0f kg/m3 + wing skin %.4f m3 at %.0f%% of that%s"
                       % (vol - wing_vol, density, wing_vol, 100 * WING_SKIN_SHARE,
                          "" if closed else " (mesh not closed - volume approximate)"))
    else:
        mass, mass_source = float(mass_kg), "given"
    AR = b * b / S
    loading = mass * G / S
    f = pennycuick_1990(mass, b, S, rho)
    theta = stroke_amplitude(b)
    A = b * math.sin(math.radians(theta / 2.0))
    cruise = f * A / strouhal
    v_glide = math.sqrt(2.0 * mass * G / (rho * S * CL_GLIDE))
    v_min = math.sqrt(2.0 * mass * G / (rho * S * CL_MAX))
    ld = max(4.0, min(20.0, 4.6 * math.sqrt(AR)))
    if loading > MAX_BIRD_WING_LOADING:
        notes.append("wing loading %.0f N/m2 is past the heaviest flying birds (~%.0f): "
                     "a real animal this size could not fly; pass mass_kg to change it"
                     % (loading, MAX_BIRD_WING_LOADING))
    # Legs launch small birds (80-95% of take-off speed: Earls 2000, Provini
    # 2012) and much less of a pigeon (~25%: Berg & Biewener 2010). Between
    # them, log-interpolated on mass - an interpolation, not a measurement.
    lm = math.log10(max(mass, 1e-3))
    leg_share = max(0.25, min(0.93, 0.93 + (0.25 - 0.93) * (lm - math.log10(0.03))
                              / (math.log10(0.4) - math.log10(0.03))))
    return {
        "mass_kg": mass, "mass_source": mass_source,
        "span_m": b, "area_m2": S, "aspect_ratio": AR,
        "wing_loading_npm2": loading, "mean_chord_m": chord * scale,
        "wingbeat_hz": f, "wingbeat_hz_pennycuick_1996": pennycuick_1996(mass, b, S, rho),
        "stroke_deg": theta, "tip_excursion_m": A, "strouhal": strouhal,
        "cruise_speed_mps": cruise,
        "glide_speed_mps": v_glide, "min_speed_mps": v_min,
        "glide_ratio": ld, "sink_rate_mps": v_glide / ld,
        "glide_angle_deg": math.degrees(math.atan(1.0 / ld)),
        "takeoff_leg_share": leg_share,
        "downstroke_fraction": DOWNSTROKE,
        "notes": notes, "problems": problems, "scale": scale,
    }


# --------------------------------------------------------------------------
# keys
# --------------------------------------------------------------------------

def tucked_legs(poser, amount=1.0):
    """Legs drawn up in flight: front ranks forward, rear ranks (and a biped's
    only rank) trailing back."""
    out = {}
    for l in poser.legs:
        z = kp.leg_zone(poser, l) if len(poser.legs) > 2 else -1.0
        if z > 0.33:
            fold, f, u = 0.55, 0.12, 0.15
        elif z < -0.33:
            fold, f, u = 0.6, -0.35, 0.12
        else:
            fold, f, u = 0.6, -0.1, 0.15
        fold = 1.0 + (fold - 1.0) * amount
        out[l["name"]] = {"target": kp.hip_relative(fold, f * amount, u * amount, 0.0),
                          "planted": False}
    return out


def flight_lean(poser):
    """Upright bodies fly horizontal; horizontal bodies already are."""
    return 70.0 if poser.bm["upright"] else 0.0


def span_at(wr, poser, fold):
    """Tip distance from the shoulder at `fold`, over rest - measured on the
    posed bones, not assumed from the angles."""
    body = poser.body
    posed = body.fk()
    out = []
    for side in ("L", "R"):
        w = next((x for x in wr.wings if x["side"] == side), None)
        if w is None:
            continue
        states = wing_mod.blend_states(wing_mod.state(fold=fold), None, 0.0)
        ov = wr.pose(posed, states)
        tip_bone = (w["fingers"][0][-1] if w["fingers"] else
                    (w["digits"][-1] if w["digits"] else (w["end"] or w["lower"])))
        L = body.rig.data.bones[tip_bone].length
        tip = ov[tip_bone] @ Vector((0.0, L, 0.0))
        rest_tip = body.rest[tip_bone] @ Vector((0.0, L, 0.0))
        out.append((tip - ov[w["upper"]].translation).dot(w["outward"])
                   / max((rest_tip - w["root"]).dot(w["outward"]), 1e-9))
    return sum(out) / len(out)


def upstroke_fold(wr, poser, span_ratio=None):
    span_ratio = UPSTROKE_SPAN if span_ratio is None else span_ratio
    lo, hi = 0.0, 1.0
    for _ in range(14):
        mid = 0.5 * (lo + hi)
        if span_at(wr, poser, mid) > span_ratio:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def flap_state(p, theta, fold_up, downstroke=DOWNSTROKE, mean=None, twist=12.0,
               sweep=8.0, tilt=10.0, gain=1.0):
    """Wing state at phase p of a wingbeat; p = 0 is the top of the stroke.

    Elevation follows a cosine warped so the downstroke takes `downstroke` of
    the beat; it and its slope are continuous at both reversals. The wing is
    fully extended going down and flexes going up. It pronates (leading edge
    down) through the downstroke and supinates through the upstroke, and the
    stroke plane tilts so the downstroke also travels forward.
    """
    p %= 1.0
    theta = theta * gain
    mean = 0.2 * theta if mean is None else mean
    if p < downstroke:
        u = p / downstroke
        elev = mean + 0.5 * theta * math.cos(math.pi * u)
        return wing_mod.state(stroke=elev, fold=0.0, twist=twist * math.sin(math.pi * u),
                              sweep=sweep * math.sin(math.pi * u), tilt=tilt)
    u = (p - downstroke) / (1.0 - downstroke)
    elev = mean + 0.5 * theta * math.cos(math.pi * (1.0 + u))
    s = math.sin(math.pi * u)
    return wing_mod.state(stroke=elev, fold=fold_up * s, twist=-0.6 * twist * s,
                          sweep=-0.75 * sweep * s, tilt=tilt)


# --------------------------------------------------------------------------
# checks, on Blender's evaluated pose
# --------------------------------------------------------------------------

class WingChecks:
    """Clearance against the body, midline, and swept area, from the skin."""

    def __init__(self, poser):
        self.P = poser
        body, bm = poser.body, poser.bm
        self.body, self.bm = body, bm
        self.wr = poser.wing_rig
        rig = body.rig
        self.table = wing_mod.skin_table(rig)
        wing_bones = self.wr.bones()
        # body radius per axial bone from the skin it dominates (80th percentile)
        tail = set(bm.get("tail", []))
        self.axial = [n for n in bm["axial"] if n not in tail]
        dists = {n: [] for n in self.axial}
        for cos, dom, _ in self.table:
            for co, d in zip(cos, dom):
                if d in dists:
                    b = rig.data.bones[d]
                    dists[d].append(_seg_dist(co, b.head_local, b.tail_local))
        self.radius = {}
        for n, ds in dists.items():
            ds.sort()
            self.radius[n] = ds[int(0.8 * (len(ds) - 1))] if ds else 0.0
        # wing skin for area: weights per vertex on wing faces
        self.skin = []
        for o in wing_mod._bound_meshes(rig):
            names = {g.index: g.name for g in o.vertex_groups if g.name in rig.data.bones}
            m = rig.matrix_world.inverted() @ o.matrix_world
            me = o.data
            dom = [None] * len(me.vertices)
            ws_all = [None] * len(me.vertices)
            for v in me.vertices:
                ws = [(names[g.group], g.weight) for g in v.groups
                      if g.group in names and g.weight > 0.0]
                tot = sum(w for _, w in ws)
                if tot > 0:
                    ws_all[v.index] = [(n, w / tot) for n, w in ws]
                    dom[v.index] = max(ws, key=lambda x: x[1])[0]
            faces = [tuple(p.vertices) for p in me.polygons
                     if sum(1 for i in p.vertices if dom[i] in wing_bones) * 2 >= len(p.vertices)]
            used = sorted({i for f in faces for i in f})
            index = {i: k for k, i in enumerate(used)}
            self.skin.append(([(m @ me.vertices[i].co, ws_all[i] or []) for i in used],
                              [tuple(index[i] for i in f) for f in faces]))

    def points(self, mats, w):
        """Test points along a wing, past the shoulder."""
        body = self.body
        out = []
        names = [n for n in self.wr.seg[w["name"]]["order"] if n != w["upper"]]
        for n in names:
            head = mats[n].translation
            tip = motion.tail_of(body, mats, n)
            out += [head, (head + tip) * 0.5, tip]
        up_tip = motion.tail_of(body, mats, w["upper"])
        out.append((mats[w["upper"]].translation + up_tip) * 0.5)
        return out

    def clearance(self, mats):
        """Smallest (distance to the body's axis / body radius) of any wing point,
        and where. 1.0 is on the skin."""
        worst, at = float("inf"), None
        segs = [(n, mats[n].translation, motion.tail_of(self.body, mats, n))
                for n in self.axial if self.radius[n] > 0.0]
        for w in self.bm["wings"]:
            for p in self.points(mats, w):
                for n, a, b in segs:
                    r = _seg_dist(p, a, b) / self.radius[n]
                    if r < worst:
                        worst, at = r, (w["name"], n)
        return worst, at

    def midline(self, mats):
        """Most negative outward offset of a wing point from the body's centre
        plane, carried by the chest. Negative means across to the other side."""
        bm = self.bm
        ref = next((w["attach"] for w in bm["wings"] if w["attach"]), None)
        if ref is None:
            return 0.0
        C = mats[ref].to_3x3() @ self.body.rest[ref].to_3x3().inverted()
        lat = (C @ bm["lat"]).normalized()
        origin = mats[ref].translation - lat * (self.body.rest[ref].translation.dot(bm["lat"])
                                                - bm["midline"])
        worst = float("inf")
        for w in bm["wings"]:
            sign = 1.0 if w["outward"].dot(bm["lat"]) > 0 else -1.0
            for p in self.points(mats, w):
                worst = min(worst, (p - origin).dot(lat) * sign)
        return worst

    def area(self, mats, normal):
        """Wing skin area projected on the plane with `normal`, armature units."""
        body = self.body
        deform = {n: mats[n] @ body.rest[n].inverted() for n in body.rest}
        total = 0.0
        for verts, faces in self.skin:
            pos = []
            for co, ws in verts:
                p = Vector((0.0, 0.0, 0.0))
                for n, wt in ws:
                    p += (deform[n] @ co) * wt
                pos.append(p)
            for f in faces:
                nv = Vector((0.0, 0.0, 0.0))
                for j in range(len(f)):
                    nv += pos[f[j]].cross(pos[f[(j + 1) % len(f)]])
                total += abs(nv.dot(normal)) * 0.5
        return total * 0.5

    def elevation(self, mats, w):
        """Degrees above the body's horizontal of the wing's shoulder-to-tip line."""
        wr = self.wr
        order = wr.seg[w["name"]]["order"]
        tip_bone = (w["fingers"][0][-1] if w["fingers"] else
                    (w["digits"][-1] if w["digits"] else (w["end"] or w["lower"])))
        tip = motion.tail_of(self.body, mats, tip_bone)
        v = tip - mats[w["upper"]].translation
        return math.degrees(math.asin(max(-1.0, min(1.0, v.normalized().dot(self.bm["up_vec"])))))


def _seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.dot(ab), 1e-12)))
    return (p - (a + ab * t)).length


def _check_flight(poser, checks, keyed, ev, infos_by_frame, planted=(), loop=False,
                  starts_at_rest=False, clearance_min=0.8):
    from .actions import _check_common, _pose_gap
    body, bm = poser.body, poser.bm
    r = _check_common(body, bm, keyed, ev, infos_by_frame, planted=list(planted),
                      posed_limbs=poser.legs, rest_floor=bm["floor"],
                      starts_at_rest=starts_at_rest)
    evaluated = ev["evaluated"]
    frames = [f for f, _ in keyed]
    # The BIND pose sets what "clear of the body" can mean for this rig - a wing
    # modelled folded already lies on its skin. Not the ground rest: that is
    # posed by the same fold under test, and measured against itself a fold
    # driven into the chest passed.
    rest_clear, _ = checks.clearance(body.fk())
    allowed = min(clearance_min, 0.9 * rest_clear)
    worst, at, at_f = float("inf"), None, None
    mid = float("inf")
    for f in frames:
        c, where = checks.clearance(evaluated[f])
        if c < worst:
            worst, at, at_f = c, where, f
        mid = min(mid, checks.midline(evaluated[f]))
    r["wing_clearance"] = round(worst, 3)
    r["wing_clearance_allowed"] = round(allowed, 3)
    if worst < allowed:
        r["failures"].append("%s passes into the body at %s (%.2f of its radius) at frame %d"
                             % (at[0], at[1], worst, at_f))
    r["wing_midline_m"] = round(mid * poser.bm.get("scale", 1.0), 4)
    if mid < -0.01 * bm["size"]:
        r["failures"].append("a wing crosses the body's midline by %.4f" % -mid)
    if loop:
        seam, bone = _pose_gap(body.rig, evaluated[frames[0]], evaluated[frames[-1]])
        r["loop_seam"] = round(seam, 6)
        if seam > 1e-4:
            r["failures"].append("loop seam %.5f on %s" % (seam, bone))
    return r


# --------------------------------------------------------------------------
# clips
# --------------------------------------------------------------------------

def _setup(rig_name, forward, up, floor):
    bm = bodymap.build(rig_name, forward=forward, up=up, floor=floor)
    if "error" in bm:
        return None, bm
    if not bm.get("wings"):
        return None, {"error": "%s has no wings: %s" % (rig_name, bodymap.summary(bm))}
    rig = bpy.data.objects[rig_name]
    body = motion.Body(rig, bm)
    P = kp.Poser(body)
    return (bm, rig, body, P, WingChecks(P)), None


def _finish(report, rig, action, frames, extra):
    if "error" in report:
        return report
    report.update({"rig": rig.name, "action": action.name, "frames": [1, frames],
                   "fps": bpy.context.scene.render.fps})
    report.update(extra)
    return report


def spread(rig_name, frames=14, forward="-Y", up="Z", floor=0.0, action_name="WingSpread",
           stroke=20.0, fps=None):
    """Ground rest -> wings open and raised, feet planted. Play backwards to fold."""
    from .actions import _author
    ctx, err = _setup(rig_name, forward, up, floor)
    if err:
        return err
    bm, rig, body, P, checks = ctx
    rest = kp.Key(name="ground rest")
    key = kp.Key(name="spread", wings=wing_mod.state(stroke=stroke, fan=1.05),
                 head_level=0.8)

    def pose(s):
        # the fold opens first, the lift follows
        return P.blend(rest, key, s, w_wings=s)

    keyed, infos, action, report = _author(
        body, rig, action_name, frames, pose, fps,
        lambda keyed, ev, infos: _check_flight(P, checks, keyed, ev, infos,
                                               planted=P.legs, starts_at_rest=True))
    return _finish(report, rig, action, frames, {"role": "WingSpread"})


def flap(rig_name, frames=None, forward="-Y", up="Z", floor=0.0, action_name="Flap",
         mass_kg=None, density=DENSITY, fps=None, gain=1.0):
    """One wingbeat, looping, phase 0 at the top of the stroke.

    Frames default to one beat at the planned frequency, but never fewer than
    12: a large bird beats at ~4 Hz, which is 6 frames at 24 fps and nothing a
    blend can survive. The engine plays it at `playback_speed_scale`.
    """
    from .actions import _author_samples
    ctx, err = _setup(rig_name, forward, up, floor)
    if err:
        return err
    bm, rig, body, P, checks = ctx
    pl = plan(P, mass_kg=mass_kg, density=density)
    if "error" in pl:
        return pl
    fps_now = fps or bpy.context.scene.render.fps
    natural = fps_now / pl["wingbeat_hz"]
    frames = int(frames or max(12, round(natural)))
    fold_up = upstroke_fold(P.wing_rig, P)
    theta = pl["stroke_deg"]
    height = bm["height"]
    # Body bob: the lift swings about the weight once a beat; the body moves
    # ~ g / (2 pi f)^2, capped. A derivation, not a measurement.
    bob = min(G / (2.0 * math.pi * pl["wingbeat_hz"]) ** 2 / pl["scale"], 0.04 * height)
    legs = tucked_legs(P)
    lean = flight_lean(P)

    def key_at(p):
        return kp.Key(drop=bob * 0.5 * math.cos(2.0 * math.pi * p), lean=lean,
                      head_level=1.0, limbs=legs, tail_lift=6.0 + 3.0 * math.sin(2 * math.pi * p),
                      wings=flap_state(p, theta, fold_up, gain=gain), name="flap")

    samples = [P.pose(key_at((f - 1) / float(frames))) for f in range(1, frames + 2)]
    down_frames = [f for f in range(1, frames + 1) if (f - 1) / float(frames) < DOWNSTROKE]
    up_frames = [f for f in range(1, frames + 1) if (f - 1) / float(frames) >= DOWNSTROKE]

    def check(keyed, ev, infos):
        r = _check_flight(P, checks, keyed, ev, infos, loop=True)
        evaluated = ev["evaluated"]
        upv = bm["up_vec"]
        a_down = sum(checks.area(evaluated[f], upv) for f in down_frames) / len(down_frames)
        a_up = sum(checks.area(evaluated[f], upv) for f in up_frames) / len(up_frames)
        r["area_down_over_up"] = round(a_down / max(a_up, 1e-12), 3)
        if a_down < 1.1 * a_up:
            r["failures"].append("the upstroke sweeps %.0f%% of the downstroke's area - "
                                 "a flap that lifts needs less" % (100 * a_up / a_down))
        amp = {}
        for w in bm["wings"]:
            el = [checks.elevation(evaluated[f], w) for f in range(1, frames + 1)]
            amp[w["name"]] = round(max(el) - min(el), 1)
        r["stroke_measured_deg"] = amp
        # fold, twist and sweep bend the tip line, so allow a margin
        for n, a in amp.items():
            if abs(a - theta * gain) > 0.25 * theta * gain:
                r["failures"].append("%s strokes %.0f degrees, asked for %.0f"
                                     % (n, a, theta * gain))
        return r

    keyed, infos, action, report = _author_samples(body, rig, action_name, samples, fps, check)
    duration = (frames + 1) / float(fps_now)
    return _finish(report, rig, action, frames + 1, {
        "role": "Flap", "plan": _round(pl), "upstroke_fold": round(fold_up, 3),
        "upstroke_span_ratio": UPSTROKE_SPAN,
        "wingbeat_hz": round(pl["wingbeat_hz"], 3),
        "frames_per_beat_natural": round(natural, 2),
        "playback_speed_scale": round(pl["wingbeat_hz"] * duration, 4),
        "phase_top_of_stroke": 0.0, "phase_bottom_of_stroke": DOWNSTROKE,
        "bob_m": round(bob * pl["scale"], 4)})


def glide(rig_name, frames=48, forward="-Y", up="Z", floor=0.0, action_name="Glide",
          dihedral=6.0, fps=None):
    """Wings spread with a little dihedral, holding the air; a slow drift so a
    held glide is not a statue."""
    from .actions import _author_samples
    ctx, err = _setup(rig_name, forward, up, floor)
    if err:
        return err
    bm, rig, body, P, checks = ctx
    legs = tucked_legs(P)
    lean = flight_lean(P)

    def key_at(t):
        s = math.sin(2.0 * math.pi * t)
        c = math.cos(2.0 * math.pi * t)
        # a roll correction: one wing up as the other goes down
        return kp.Key(lean=lean, head_level=1.0, limbs=legs, tail_lift=4.0 + 2.0 * c,
                      tail_sway=3.0 * s, name="glide", wings={
                          "L": wing_mod.state(stroke=dihedral + 2.5 * s, fold=0.05, sweep=-4.0,
                                              twist=1.5 * c),
                          "R": wing_mod.state(stroke=dihedral - 2.5 * s, fold=0.05, sweep=-4.0,
                                              twist=-1.5 * c)})

    samples = [P.pose(key_at((f - 1) / float(frames))) for f in range(1, frames + 2)]

    def check(keyed, ev, infos):
        r = _check_flight(P, checks, keyed, ev, infos, loop=True)
        rest_area = checks.area(body.fk(), bm["up_vec"])
        a = min(checks.area(ev["evaluated"][f], bm["up_vec"]) for f in range(1, frames + 1))
        r["area_over_spread"] = round(a / max(rest_area, 1e-12), 3)
        if a < 0.85 * rest_area:
            r["failures"].append("gliding on %.0f%% of the wing - it would not hold the air"
                                 % (100 * a / rest_area))
        return r

    keyed, infos, action, report = _author_samples(body, rig, action_name, samples, fps, check)
    return _finish(report, rig, action, frames + 1, {"role": "Glide", "dihedral_deg": dihedral})


def dive(rig_name, frames=24, forward="-Y", up="Z", floor=0.0, action_name="Dive",
         fold=0.6, fps=None):
    """Wings half folded and swept back, legs tight, nose down."""
    from .actions import _author_samples
    ctx, err = _setup(rig_name, forward, up, floor)
    if err:
        return err
    bm, rig, body, P, checks = ctx
    legs = tucked_legs(P, amount=1.2)
    lean = flight_lean(P) + 12.0

    def key_at(t):
        s = math.sin(2.0 * math.pi * t)
        return kp.Key(lean=lean, head_level=0.6, limbs=legs, tail_lift=-4.0, name="dive",
                      wings=wing_mod.state(fold=fold + 0.03 * s, stroke=-4.0, sweep=-10.0,
                                           twist=2.0 * s))

    samples = [P.pose(key_at((f - 1) / float(frames))) for f in range(1, frames + 2)]

    def check(keyed, ev, infos):
        r = _check_flight(P, checks, keyed, ev, infos, loop=True)
        rest_area = checks.area(body.fk(), bm["up_vec"])
        a = sum(checks.area(ev["evaluated"][f], bm["up_vec"]) for f in range(1, frames + 1)) / frames
        r["area_over_spread"] = round(a / max(rest_area, 1e-12), 3)
        return r

    keyed, infos, action, report = _author_samples(body, rig, action_name, samples, fps, check)
    return _finish(report, rig, action, frames + 1, {"role": "Dive", "fold": fold})


def takeoff(rig_name, forward="-Y", up="Z", floor=0.0, action_name="TakeOff",
            flap_clip="Flap", mass_kg=None, density=DENSITY, timing=(8, 12, 18, 24), fps=None):
    """Ground rest -> load -> leap into a first, larger downstroke -> Flap's
    first frame.

    load    crouched, wings opening and rising
    launch  legs stretched, wings at the top of an enlarged stroke
    beat    the bottom of the first downstroke, legs trailing into the tuck
    ready   the Flap clip's phase 0 - top of stroke, legs tucked

    First wingbeats are larger than cruising ones (Berg & Biewener 2010), so
    the first stroke is 1.25x the planned amplitude.
    """
    from .actions import _author_samples, _evaluated_frame, _pose_gap
    ctx, err = _setup(rig_name, forward, up, floor)
    if err:
        return err
    bm, rig, body, P, checks = ctx
    pl = plan(P, mass_kg=mass_kg, density=density)
    if "error" in pl:
        return pl
    theta = pl["stroke_deg"]
    fold_up = upstroke_fold(P.wing_rig, P)
    load, _ = kp.crouch_key(P, depth=0.6)
    load.wings = wing_mod.state(fold=0.35, stroke=0.2 * theta + 0.5 * theta, tuck=0.0)
    launch_keys = kp.jump_keys(P)

    def above_floor(fn):
        # A push-off drives the feet back from hips that are still low; aimed
        # from there, the dragon's hind feet went 1.6 cm into the floor.
        def target(p, l, posed):
            t = fn(p, l, posed)
            dh = p.height(l["rest_eff"]) - p.height(t)
            return t + p.up * dh if dh > 0.0 else t
        return target
    launch = launch_keys[1].copy(
        name="launch", wings=flap_state(0.0, theta, fold_up, gain=1.25), head_level=1.0,
        # and the foot rolls over its toe, heel up, rather than following the
        # shin - which swung the toes down through the floor
        limbs={n: dict(s, target=above_floor(s["target"]), planted=1.0, tilt=25.0)
               for n, s in launch_keys[1].limbs.items()})
    beat = kp.Key(name="beat", limbs=tucked_legs(P, 0.6), lean=flight_lean(P), head_level=1.0,
                  drop=-0.5 * (-launch.drop), wings=flap_state(DOWNSTROKE, theta, fold_up, gain=1.25),
                  tail_lift=15.0)
    bob = min(G / (2.0 * math.pi * pl["wingbeat_hz"]) ** 2 / pl["scale"], 0.04 * bm["height"])
    ready = kp.Key(name="ready", drop=bob * 0.5, lean=flight_lean(P), head_level=1.0,
                   limbs=tucked_legs(P), tail_lift=6.0, wings=flap_state(0.0, theta, fold_up))
    keys = [kp.Key(name="ground rest"), load, launch, beat, ready]
    marks = [1] + list(timing)
    samples = []
    for f in range(1, marks[-1] + 1):
        seg = min(max(i for i in range(len(marks) - 1) if marks[i] <= f), len(keys) - 2)
        u = min(1.0, (f - marks[seg]) / float(marks[seg + 1] - marks[seg]))
        w = motion.smoothstep(u)
        # The downstroke is a stroke, not an ease: in the beat it runs on the
        # flap's own cosine. The unfold leads the crouch into the load.
        ww = u if seg == 2 else (math.sqrt(w) if seg == 0 else w)
        samples.append(P.blend(keys[seg], keys[seg + 1], w, w_wings=ww,
                               w_legs=math.sqrt(w) if seg >= 2 else w))
    before = _evaluated_frame(rig, flap_clip, 1)

    def check(keyed, ev, infos):
        r = _check_flight(P, checks, keyed, ev, infos, planted=[], starts_at_rest=True)
        evaluated = ev["evaluated"]
        drift = {}
        for l in P.legs:
            n = l["end"] or l["lower"]
            h0 = evaluated[1][n].translation
            worst = max((evaluated[f][n].translation - h0).length for f in range(1, marks[1] + 1))
            drift[l["name"]] = round(worst, 5)
            if worst > 0.005 * bm["size"]:
                r["failures"].append("%s slides %.4f before the leap" % (l["name"], worst))
        r["planted_drift"] = drift
        if before is not None:
            gap, bone = _pose_gap(rig, evaluated[marks[-1]], before)
            r["seams"] = {"to " + flap_clip: round(gap, 5)}
            if gap > 0.002 * bm["size"]:
                r["failures"].append("last frame is %.4f from %s's first (%s)"
                                     % (gap, flap_clip, bone))
        else:
            r["failures"].append("no %s clip to measure the end seam against" % flap_clip)
        return r

    keyed, infos, action, report = _author_samples(body, rig, action_name, samples, fps, check)
    return _finish(report, rig, action, marks[-1], {
        "role": "TakeOff", "leap_frame": marks[1], "first_stroke_deg": round(1.25 * theta, 1),
        "takeoff_leg_share": round(pl["takeoff_leg_share"], 3)})


def land(rig_name, forward="-Y", up="Z", floor=0.0, action_name="Land", glide_clip="Glide",
         timing=(9, 14, 26), fps=None):
    """Glide's first frame -> flare -> touchdown -> folded ground rest.

    flare      body pitched up, wings raised and swept forward, supinated to
               brake, legs reaching down and forward (Berg & Biewener 2010:
               body and wings rotate toward vertical, the stroke tilts up)
    touchdown  feet on their rest spots and planted from here, knees giving
    rest       ground rest: wings folded against the flank
    """
    from .actions import _author_samples, _evaluated_frame, _pose_gap
    ctx, err = _setup(rig_name, forward, up, floor)
    if err:
        return err
    bm, rig, body, P, checks = ctx
    lean = flight_lean(P)
    glide_start = kp.Key(lean=lean, head_level=1.0, limbs=tucked_legs(P), tail_lift=6.0,
                         tail_sway=0.0, name="glide", wings={
                             "L": wing_mod.state(stroke=6.0, fold=0.05, sweep=-4.0, twist=1.5),
                             "R": wing_mod.state(stroke=6.0, fold=0.05, sweep=-4.0, twist=-1.5)})

    def reach_down(p, l, posed):
        hip = posed[l["upper"]].translation
        want = l["rest_eff"] + p.fwd * (0.25 * (l["a"] + l["b"])) + p.up * (0.12 * (l["a"] + l["b"]))
        span = want - hip
        top = 0.9 * (l["a"] + l["b"])
        return hip + span * min(1.0, top / max(span.length, 1e-9))

    # Pitching up lifts a horizontal body's front hips away from the ground its
    # front feet are reaching for - at 22 degrees the dragon's needed 102%.
    flare = kp.Key(name="flare", lean=lean - (22.0 if bm["upright"] else 10.0),
                   head_level=1.0, tail_lift=-10.0,
                   limbs={l["name"]: {"target": reach_down, "planted": False} for l in P.legs},
                   wings=wing_mod.state(stroke=35.0, sweep=18.0, twist=-28.0, fold=0.0))
    touch, _ = kp.crouch_key(P, depth=0.35)
    touch.wings = wing_mod.state(stroke=40.0, sweep=5.0, twist=-10.0, fold=0.15)
    touch.name = "touchdown"
    rest = kp.Key(name="ground rest")
    keys = [glide_start, flare, touch, rest]
    marks = [1] + list(timing)
    samples = []
    for f in range(1, marks[-1] + 1):
        seg = min(max(i for i in range(len(marks) - 1) if marks[i] <= f), len(keys) - 2)
        u = min(1.0, (f - marks[seg]) / float(marks[seg + 1] - marks[seg]))
        w = motion.smoothstep(u)
        # folding runs behind the body settling
        samples.append(P.blend(keys[seg], keys[seg + 1], w,
                               w_wings=motion.smoothstep(max(0.0, (u - 0.25) / 0.75))
                               if seg == 2 else w))
    before = _evaluated_frame(rig, glide_clip, 1)

    def check(keyed, ev, infos):
        r = _check_flight(P, checks, keyed, ev, infos, planted=[])
        evaluated = ev["evaluated"]
        drift = {}
        for l in P.legs:
            n = l["end"] or l["lower"]
            h0 = evaluated[marks[2]][n].translation
            worst = max((evaluated[f][n].translation - h0).length
                        for f in range(marks[2], marks[3] + 1))
            drift[l["name"]] = round(worst, 5)
            if worst > 0.005 * bm["size"]:
                r["failures"].append("%s slides %.4f after touchdown" % (l["name"], worst))
        r["planted_drift"] = drift
        seams = {}
        if before is not None:
            gap, bone = _pose_gap(rig, evaluated[1], before)
            seams["from " + glide_clip] = round(gap, 5)
            if gap > 0.002 * bm["size"]:
                r["failures"].append("first frame is %.4f from %s's first (%s)"
                                     % (gap, glide_clip, bone))
        else:
            r["failures"].append("no %s clip to measure the start seam against" % glide_clip)
        gap, bone = _pose_gap(rig, evaluated[marks[-1]], body.ground_rest)
        seams["to ground rest"] = round(gap, 5)
        if gap > 0.002 * bm["size"]:
            r["failures"].append("last frame is %.4f from the ground rest (%s)" % (gap, bone))
        r["seams"] = seams
        return r

    keyed, infos, action, report = _author_samples(body, rig, action_name, samples, fps, check)
    return _finish(report, rig, action, marks[-1], {"role": "Land", "touchdown_frame": marks[2]})


def flight_set(rig_name, prefix=None, forward="-Y", up="Z", floor=0.0, fps=None,
               mass_kg=None, density=DENSITY,
               roles=("Glide", "Flap", "WingSpread", "TakeOff", "Dive", "Land")):
    """Author every flight clip for one creature. Returns {role: report}.

    Order matters: TakeOff measures its end against this set's Flap, and Land
    its start against this set's Glide.
    """
    prefix = prefix or rig_name
    name = lambda role: "%s_%s" % (prefix, role)
    common = dict(forward=forward, up=up, floor=floor, fps=fps)
    makers = {
        "Glide": lambda: glide(rig_name, action_name=name("Glide"), **common),
        "Flap": lambda: flap(rig_name, action_name=name("Flap"), mass_kg=mass_kg,
                             density=density, **common),
        "WingSpread": lambda: spread(rig_name, action_name=name("WingSpread"), **common),
        "TakeOff": lambda: takeoff(rig_name, action_name=name("TakeOff"), flap_clip=name("Flap"),
                                   mass_kg=mass_kg, density=density, **common),
        "Dive": lambda: dive(rig_name, action_name=name("Dive"), **common),
        "Land": lambda: land(rig_name, action_name=name("Land"), glide_clip=name("Glide"), **common),
    }
    out = {role: makers[role]() for role in roles}
    stored.store(out, rig_name)             # on the actions, so export works in a later session
    return out


ROLES = ("Glide", "Flap", "WingSpread", "TakeOff", "Dive", "Land")


FLIGHT_KEYS = ("mass_kg", "mass_source", "span_m", "area_m2", "aspect_ratio",
               "wing_loading_npm2", "wingbeat_hz", "stroke_deg", "cruise_speed_mps",
               "glide_speed_mps", "min_speed_mps", "glide_ratio", "sink_rate_mps",
               "glide_angle_deg", "takeoff_leg_share", "downstroke_fraction", "notes")


def engine_manifest(reports=None, rig_name=None):
    """The `flight` entry an engine controller reads, from `flight_set` reports -
    or, with `reports=None`, from those `flight_set` stored on `rig_name`'s actions."""
    reports = stored.resolve(reports, rig_name, ROLES)
    flap_r = reports.get("Flap", {})
    pl = flap_r.get("plan", {})
    problems = ["%s did not pass: %s" % (role, "; ".join(r.get("failures", [])))
                for role, r in reports.items() if isinstance(r, dict) and not r.get("passed")]
    problems += ["%s: %s" % (role, r["error"]) for role, r in reports.items()
                 if isinstance(r, dict) and "error" in r]
    return {
        **{k: pl.get(k) for k in FLIGHT_KEYS},
        "flap": {"playback_speed_scale": flap_r.get("playback_speed_scale"),
                 "phase_top_of_stroke": 0.0,
                 "phase_bottom_of_stroke": flap_r.get("phase_bottom_of_stroke")},
        "takeoff_leap_s": (reports.get("TakeOff", {}).get("leap_frame", 1) - 1)
        / float(bpy.context.scene.render.fps),
        "land_touchdown_s": (reports.get("Land", {}).get("touchdown_frame", 1) - 1)
        / float(bpy.context.scene.render.fps),
        "problems": problems,
    }


def summarize(r):
    from .actions import summarize as base
    if "error" in r:
        return "ERROR: " + r["error"]
    lines = [base(r)]
    for k in ("wing_clearance", "wing_clearance_allowed", "wing_midline_m", "area_down_over_up",
              "stroke_measured_deg", "area_over_spread", "wingbeat_hz",
              "playback_speed_scale", "upstroke_fold", "seams"):
        if r.get(k) is not None:
            lines.append("  %s %s" % (k, r[k]))
    return "\n".join(lines)


def summarize_plan(pl):
    if "error" in pl:
        return "ERROR: " + pl["error"]
    lines = [
        "mass %.2f kg (%s)" % (pl["mass_kg"], pl["mass_source"]),
        "span %.2f m, area %.3f m2, aspect ratio %.1f, wing loading %.0f N/m2"
        % (pl["span_m"], pl["area_m2"], pl["aspect_ratio"], pl["wing_loading_npm2"]),
        "wingbeat %.2f Hz (Pennycuick 1996 form: %.2f), stroke %.0f deg, tip travels %.2f m"
        % (pl["wingbeat_hz"], pl["wingbeat_hz_pennycuick_1996"], pl["stroke_deg"],
           pl["tip_excursion_m"]),
        "cruise %.1f m/s at St %.2f; glide %.1f m/s, stall %.1f m/s, L/D %.1f, sink %.2f m/s"
        % (pl["cruise_speed_mps"], pl["strouhal"], pl["glide_speed_mps"], pl["min_speed_mps"],
           pl["glide_ratio"], pl["sink_rate_mps"]),
        "legs give ~%.0f%% of take-off speed" % (100 * pl["takeoff_leg_share"]),
    ]
    lines += ["NOTE " + n for n in pl["notes"]]
    return "\n".join(lines)


def _round(pl):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in pl.items()
            if k not in ("problems",)}
