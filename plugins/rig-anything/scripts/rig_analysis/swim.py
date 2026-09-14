"""Swimming for any body with a spine, and fins to swim with.

A walk comes from a Froude number and a flight from wing loading; a swim comes
from body length. Fish change speed almost entirely through tail-beat
frequency: the distance covered per beat - the stride - stays near 0.7 body
lengths (Videler; Wardle), and so does the tail's amplitude (Bainbridge 1958).
So one travelling wave, scaled by length, covers a cruise and a sprint:

    y(z, t) = A(z) L sin(2 pi (z / lambda - f t))

z runs 0 at the snout to 1 at the tail fin's tip. The envelope A(z) and the
wavelength lambda are the swimming MODE:

    anguilliform   A = 0.1 e^(z-1),              lambda 0.64 L  (eel; Tytell & Lauder 2004)
    subcarangiform between eel and carangiform,  lambda 0.80 L  (trout - interpolated)
    carangiform    A = 0.02 - 0.08 z + 0.16 z^2, lambda 0.95 L  (Videler & Hess 1984, via
                                                                  Borazjani & Sotiropoulos 2010)
    thunniform     motion in the peduncle,       lambda 1.25 L  (tuna; Donley & Dickson 2000)
    cetacean       the same wave, UP AND DOWN,   lambda 1.00 L  (flukes; envelope a design)

The body is posed as rigid segments laid along that curve, anchored a third of
the way back, with the side-to-side recoil of the whole body removed - a fish
does not drift sideways every beat. The caudal fin's rays are turned so its tip
lands on the envelope too, which is what the amplitude check then measures on
Blender's playback.

Fins follow the research on what they do at each speed: median fins stand up
slow and fold at speed, pectorals lie against the body at cruise and swing out
to brake or scull, the tail fin cups and folds to 70% of its spread in a glide.

CLIPS
-----

    Swim      loop, one tail beat at cruise speed
    Sprint    loop, one beat at burst speed (never under 12 frames; played faster)
    Glide     loop, coasting: body straight, fins folded, a slow drift
    Hover     loop, one pectoral stroke - sculling on the spot, body still
    TurnL/R   one-shot: a beat with the body bent into the turn and out
    Escape    one-shot: a C-start - bend, counter-bend, a burst beat
    Brake     one-shot: pectorals out against the flow, tail flared

A cetacean (flukes) gets Swim, Sprint, Glide and the turns: no fish-fin moves.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Vector

from . import bodymap, fins as fin_mod, motion

STRIDE = 0.7            # body lengths per tail beat (0.6-0.8: Videler; Wardle)
CAUDAL_MAX = 45.0       # tail fin against its peduncle, degrees - a design bound
WATER = 1025.0          # kg/m3 - a fish is near neutrally buoyant

MODES = {
    "anguilliform": dict(plane="lateral", wavelength=0.64, turn_radius=0.06,
                         envelope=lambda z: 0.1 * math.exp(z - 1.0)),
    "subcarangiform": dict(plane="lateral", wavelength=0.80, turn_radius=0.1,
                           envelope=lambda z: 0.5 * (0.1 * math.exp(z - 1.0)
                                                     + 0.02 - 0.08 * z + 0.16 * z * z)),
    "carangiform": dict(plane="lateral", wavelength=0.95, turn_radius=0.1,
                        envelope=lambda z: 0.02 - 0.08 * z + 0.16 * z * z),
    # A design shape: tuna and lamnid sharks move almost only at the peduncle.
    "thunniform": dict(plane="lateral", wavelength=1.25, turn_radius=0.47,
                       envelope=lambda z: 0.012 + 0.088 * z ** 5),
    # Design as well: dolphin and whale bodies bend mostly in the tail stock;
    # peak-to-peak fluke amplitude 0.15-0.25 L (Rohr & Fish 2004), L/5 humpback.
    "cetacean": dict(plane="dorsoventral", wavelength=1.0, turn_radius=0.3,
                     envelope=lambda z: 0.015 + 0.085 * z ** 3),
}


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


# --------------------------------------------------------------------------
# the body as a chain along its length
# --------------------------------------------------------------------------

class Swimmer:
    """A body map, its fins, and the chain the wave is laid along."""

    def __init__(self, rig_name, mode=None, forward="-Y", up="Z"):
        rig = bpy.data.objects[rig_name]
        bm = bodymap.build(rig_name, forward=forward, up=up)
        if "error" in bm:
            raise ValueError(bm["error"])
        self.rig, self.bm = rig, bm
        self.body = motion.Body(rig, bm)
        self.fins = fin_mod.FinRig(self.body)
        self.maw = None
        if bm.get("maw"):
            from .maw import MawRig
            self.maw = MawRig(self.body)
        st = fin_mod.read(rig) or {}
        fwd = bm["fwd"]
        self.scale = sum(rig.matrix_world.to_scale()) / 3.0
        meshes = fin_mod._bound(rig)
        if not meshes:
            raise ValueError("%s has no bound mesh to measure" % rig_name)
        to_arm = rig.matrix_world.inverted()
        us = []
        for o in meshes:
            m = to_arm @ o.matrix_world
            us.extend((m @ v.co).dot(fwd) for v in o.data.vertices)
        self.snout_u, self.tip_u = max(us), min(us)
        self.length = self.snout_u - self.tip_u                  # armature units

        # axial chain, head end first, as points: pts[i] .. pts[i+1] is bone i
        axial = list(reversed(bm["axial"]))
        joints = list(reversed(bm["axial_joints"]))
        bones = rig.data.bones
        head = bones[axial[0]]
        front = head.head_local if (head.head_local - joints[0]).length > \
            (head.tail_local - joints[0]).length else head.tail_local
        rear_bone = bones[axial[-1]]
        rear_end = rear_bone.head_local if (rear_bone.head_local - joints[-1]).length > \
            (rear_bone.tail_local - joints[-1]).length else rear_bone.tail_local
        # joints[i] is the rear end of axial bone i (head first): the chain of
        # points runs snout, the head's rear joint, ..., the last bone's rear end
        self.pts = [front.copy()] + [j.copy() for j in joints] + [rear_end.copy()]
        self.pts = self._dedupe(self.pts)
        self.axial = axial
        self.z = [max(0.0, min(1.0, (self.snout_u - p.dot(fwd)) / self.length)) for p in self.pts]

        if st.get("swims") == "dorsoventral":
            auto = "cetacean"
        else:
            depth = max(self._depths(), default=0.0)
            auto = "anguilliform" if self.length / max(depth, 1e-9) > 12.0 else "carangiform"
        self.mode = mode or auto
        self.mode_guessed = mode is None
        self.spec = MODES[self.mode]
        self.disp = bm["up_vec"] if self.spec["plane"] == "dorsoventral" else bm["lat"]
        self.radius = self._radii()
        cz = [f for f in self.fins.fins if f["kind"] in ("caudal", "flukes")]
        self.caudal = cz[0] if cz else None
        self._caudal_sign = self._probe_caudal() if self.caudal else 1.0
        # clean limits measured on this skin by `measure_fin_limits`
        self.limits = {k: st[k] for k in ("bend_clean_deg", "brake_clean") if k in st}

    def _dedupe(self, pts):
        """One point per joint: bones in the chain share their joints, so the
        list from the body map may repeat. Keep n_bones + 1 points."""
        out = [pts[0]]
        for p in pts[1:]:
            if (p - out[-1]).length > 1e-7:
                out.append(p)
        need = len(self.bm["axial"]) + 1
        return out[:need] if len(out) >= need else out

    def _depths(self):
        bm = self.bm
        rows = {}
        rays = self.fins.bones()
        for o in fin_mod._bound(self.rig):
            m = self.rig.matrix_world.inverted() @ o.matrix_world
            names = {g.index: g.name for g in o.vertex_groups}
            for v in o.data.vertices:
                if any(names.get(g.group) in rays and g.weight > 0.5 for g in v.groups):
                    continue
                p = m @ v.co
                k = int(20 * (self.snout_u - p.dot(bm["fwd"])) / self.length)
                lo, hi = rows.get(k, (1e9, -1e9))
                h = p.dot(bm["up_vec"])
                rows[k] = (min(lo, h), max(hi, h))
        return [hi - lo for lo, hi in rows.values()]

    def _radii(self):
        from .flight import _seg_dist
        rig = self.rig
        dists = {n: [] for n in self.axial}
        for o in fin_mod._bound(rig):
            m = rig.matrix_world.inverted() @ o.matrix_world
            names = {g.index: g.name for g in o.vertex_groups}
            for v in o.data.vertices:
                ws = [(names.get(g.group), g.weight) for g in v.groups]
                ws = [x for x in ws if x[0] in dists]
                if not ws:
                    continue
                top = max(ws, key=lambda x: x[1])[0]
                b = rig.data.bones[top]
                dists[top].append(_seg_dist(m @ v.co, b.head_local, b.tail_local))
        out = {}
        for n, ds in dists.items():
            ds.sort()
            out[n] = ds[int(0.8 * (len(ds) - 1))] if ds else 0.0
        return out

    def _probe_caudal(self):
        """Which stroke sign moves the tail fin's tip toward +disp."""
        from .motion import tail_of
        posed = self.body.fk()
        base = self.fins.pose(posed, {})
        test = self.fins.pose(posed, {self.caudal["name"]: fin_mod.state(stroke=10.0)})
        r = self.caudal["rays_rest"][len(self.caudal["rays_rest"]) // 2]["name"]
        d = (tail_of(self.body, test, r) - tail_of(self.body, base, r)).dot(self.disp)
        return 1.0 if d > 0.0 else -1.0

    # ---------------------------------------------------------------- pose
    def offsets(self, phase, amp=1.0):
        lam, env = self.spec["wavelength"], self.spec["envelope"]
        return [amp * env(z) * self.length * math.sin(2.0 * math.pi * (z / lam - phase)) for z in self.z]

    def chain(self, offsets, bend_deg=0.0, anchor_z=0.33):
        """Rigid segments laid along the wave's offsets (in the wave's plane),
        plus `bend_deg` of sideways C-bend spread over the rear of the body for
        a turn, with the recoil of both removed. Returns posed points and
        per-segment rotations.

        The beat and the bend are ONE rotation per segment. Built as two whole
        poses and multiplied - a whale beats up and down but turns sideways - the
        joints came apart and Blender's playback missed the prediction by 9.5 cm
        on the flukes."""
        pts, fwd, lat = self.pts, self.bm["fwd"], self.bm["lat"]
        disp = self.disp
        n = len(pts)
        weights = [_smooth((self.z[i] - 0.25) / 0.6) for i in range(n - 1)]
        wsum = sum(weights) or 1.0

        def rot(seg, ang, direction):
            axis = seg.normalized().cross(direction)
            if axis.length < 1e-9:
                axis = fwd.cross(direction)
            axis.normalize()
            R = Matrix.Rotation(ang, 3, axis)
            # a positive angle moves the segment's rear end toward +direction
            if ang and (R @ seg - seg).dot(direction) * ang < 0.0:
                R = Matrix.Rotation(-ang, 3, axis)
            return R

        rots = []
        for i in range(n - 1):
            seg = pts[i + 1] - pts[i]
            ds = max(abs(seg.dot(fwd)), 1e-9)
            wave = math.atan2(offsets[i + 1] - offsets[i], ds)
            # a turn's C-bend grows toward the tail; its angles sum to bend_deg
            bend = math.radians(bend_deg) * weights[i] / wsum
            R = rot(seg, wave, disp)
            if bend:
                R = rot(R @ seg, bend, lat) @ R
            rots.append(R)
        k = min(range(n), key=lambda i: abs(self.z[i] - anchor_z))
        new = [None] * n
        new[k] = pts[k] + disp * offsets[k]
        for i in range(k, n - 1):
            new[i + 1] = new[i] + rots[i] @ (pts[i + 1] - pts[i])
        for i in range(k - 1, -1, -1):
            new[i] = new[i + 1] - rots[i] @ (pts[i + 1] - pts[i])
        # recoil: the body's mass-weighted offset stays zero, in both planes
        w = 0.0
        acc = Vector((0.0, 0.0, 0.0))
        for i in range(n - 1):
            r = self.radius.get(self.axial[i], 0.0) if i < len(self.axial) else 0.0
            seg_w = r * r * (pts[i + 1] - pts[i]).length
            mid = 0.5 * ((new[i] - pts[i]) + (new[i + 1] - pts[i + 1]))
            w += seg_w
            acc += (disp * mid.dot(disp) + (lat * mid.dot(lat) if bend_deg else Vector())) * seg_w
        shift = acc / w if w > 0 else Vector((0.0, 0.0, 0.0))
        return [p - shift for p in new], rots

    def axial_overrides(self, new, rots):
        body = self.body
        out = {}
        for i, name in enumerate(self.axial):
            b = body.rig.data.bones[name]
            a, c = self.pts[i], self.pts[i + 1]
            use_a = (b.head_local - a).length <= (b.head_local - c).length
            head_rest, head_new = (a, new[i]) if use_a else (c, new[i + 1])
            out[name] = (Matrix.Translation(head_new) @ rots[i].to_4x4()
                         @ Matrix.Translation(-head_rest) @ body.rest[name])
        return out

    def pose(self, phase=0.0, amp=1.0, bend_deg=0.0, fins=None, caudal=True, maw=None):
        """Armature matrices for one instant of the wave. `fins` maps fin name,
        kind or "*" to fin states; the tail fin's stroke is solved so its tip
        follows the envelope, unless `caudal` is False."""
        body = self.body
        offs = self.offsets(phase, amp)
        new, rots = self.chain(offs, bend_deg)
        overrides = self.axial_overrides(new, rots)
        posed = body.fk(overrides)
        if self.maw is not None and maw:
            from .maw import blend_states
            overrides.update(self.maw.pose(posed, blend_states(maw, maw, 1.0)))
            posed = body.fk(overrides)
        states = dict(fins or {})
        if caudal and self.caudal is not None:
            lam, env = self.spec["wavelength"], self.spec["envelope"]
            tip_off = amp * env(1.0) * self.length * math.sin(2.0 * math.pi * (1.0 / lam - phase))
            fin_len = max(self.length * (1.0 - self.z[-1]), 1e-9)
            # solved on the wave alone: against a turn's bend the fin was aimed at
            # the straight body and counter-rotated 80 degrees through the peduncle
            wave_pts = new if not bend_deg else self.chain(offs, 0.0)[0]
            ped = (wave_pts[-1] - self.pts[-1]).dot(self.disp)
            want = math.atan2(tip_off - ped, fin_len)
            seg = wave_pts[-1] - wave_pts[-2]
            have = math.atan2(seg.dot(self.disp), max(seg.dot(-self.bm["fwd"]), 1e-9))
            kind = self.caudal["kind"]
            extra = dict(states.get(kind) or {})
            rel = max(-CAUDAL_MAX, min(CAUDAL_MAX, math.degrees(want - have)))
            extra["stroke"] = rel * self._caudal_sign + extra.get("stroke", 0.0)
            states[kind] = extra
        if self.fins.fins:
            overrides.update(self.fins.pose(posed, states))
            posed = body.fk(overrides)
        return posed, {}


def measure_fin_limits(rig_name, forward="-Y", up="Z", stretch_limit=3.0, steps=8,
                       adduct=-8.0):
    """How far each fin folds - with the adduction a folded fin carries - before
    a face turns inside out or an edge passes `stretch_limit`, by bisection on
    predicted poses; stored so fold 1 means it. The test fish's pectorals are
    modelled half folded, and folded further they dragged their base through
    the flank: 152 faces inside out."""
    import json
    rig = bpy.data.objects[rig_name]
    raw = json.loads(rig.data[fin_mod.PROP])
    for f in raw["fins"]:
        f.pop("fold_clean", None)
    rig.data[fin_mod.PROP] = json.dumps(raw)
    sw = Swimmer(rig_name, forward=forward, up=up)
    checks = SwimChecks(sw)
    body = sw.body
    _, rest_flips = checks.skin(body.fk())
    out = {}
    for f in raw["fins"]:
        if f["kind"] in ("caudal", "flukes"):
            continue

        def clean(x, f=f):
            st = {f["name"]: fin_mod.state(fold=x, stroke=adduct if f["side"] else 0.0)}
            posed = body.fk(sw.fins.pose(body.fk(), st))
            s, fl = checks.skin(posed)
            return s <= stretch_limit and fl <= rest_flips
        if clean(1.0):
            best = 1.0
        else:
            lo, hi = 0.0, 1.0
            if not clean(0.0):
                best = 0.0
            else:
                for _ in range(steps):
                    mid = 0.5 * (lo + hi)
                    if clean(mid):
                        lo = mid
                    else:
                        hi = mid
                best = lo
        f["fold_clean"] = round(best, 3)
        out[f["name"]] = f["fold_clean"]

    def bisect(ok, hi, steps_=steps):
        if ok(hi):
            return hi
        lo = 0.0
        for _ in range(steps_):
            mid = 0.5 * (lo + hi)
            if ok(mid):
                lo = mid
            else:
                hi = mid
        return lo

    # the widest C-bend the body takes, either way - a turn and a C-start ask
    # for it, and a decimated mesh is not quite symmetric
    def bend_ok(deg):
        for sgn in (1.0, -1.0):
            posed = sw.pose(0.0, amp=0.0, bend_deg=sgn * deg, caudal=False)[0]
            st, fl = checks.skin(posed)
            if st > stretch_limit or fl > rest_flips:
                return False
        return True
    raw["bend_clean_deg"] = round(bisect(bend_ok, 150.0), 1)
    out["bend_clean_deg"] = raw["bend_clean_deg"]
    # how far the whole braking pose goes - pectorals, pelvics and tail flare
    # together; measured one at a time they each passed and together folded
    if sw.fins.by_kind("pectoral"):
        def brake_ok(k):
            posed = body.fk(sw.fins.pose(body.fk(), brake_states(k)))
            st, fl = checks.skin(posed)
            return st <= stretch_limit and fl <= rest_flips
        raw["brake_clean"] = round(bisect(brake_ok, 1.0), 3)
        out["brake_clean"] = raw["brake_clean"]
    rig.data[fin_mod.PROP] = json.dumps(raw)
    return out


# --------------------------------------------------------------------------
# numbers
# --------------------------------------------------------------------------

def plan(sw, mass_kg=None):
    """Speeds, tail beats and manoeuvre numbers from length and mode."""
    from .flight import mesh_volume
    L = sw.length * sw.scale
    vol, closed = mesh_volume(sw.rig)
    mass = float(mass_kg) if mass_kg else vol * WATER
    spec = sw.spec
    notes = []
    if sw.mode == "cetacean":
        # Baleen whales cruise near 2 m/s at every size (Gough et al. 2019).
        cruise = 2.0
        ucrit, burst = cruise * 1.5, cruise * 3.0
        notes.append("cetacean cruise 2 m/s (baleen whales, any size); critical 1.5x and burst 3x "
                     "cruise are design numbers")
    else:
        # Critical (sustainable) speed: 3.22 L/s at 15 cm, 2.05 L/s at 37 cm in bull
        # trout - a power law through those, ~L^-0.5. Cruise is half of it (design).
        ucrit = 3.22 * (L / 0.15) ** -0.5 * L
        cruise = 0.5 * ucrit
        # Sprint: 25 L/s at 0.1 m, ~4 L/s at 1 m (Wardle 1975) - L^-0.8 between.
        burst = 25.0 * (L / 0.1) ** -0.796 * L
        if not (0.04 <= L <= 2.0):
            notes.append("fish speed fits are from 0.1-1 m fish; %.2f m is extrapolated" % L)
    stride = STRIDE * L
    a_tail = spec["envelope"](1.0) * L
    f_cruise, f_burst = cruise / stride, burst / stride
    # Pectoral sculling: 2.79 Hz in a bluegill (~0.1 kg, assumed), scaling with
    # mass^-0.12 (Drucker & Jensen 1996).
    f_pect = 2.79 * (max(mass, 1e-3) / 0.1) ** -0.12
    return {
        "mode": sw.mode, "mode_guessed": sw.mode_guessed, "plane": spec["plane"],
        "length_m": L, "mass_kg": mass, "mass_source": "given" if mass_kg else
        "skin volume x %.0f kg/m3%s" % (WATER, "" if closed else " (mesh not closed)"),
        "wavelength_body_lengths": spec["wavelength"], "tail_amplitude_m": a_tail,
        "stride_m": stride, "ucrit_mps": ucrit, "cruise_speed_mps": cruise, "burst_speed_mps": burst,
        "tailbeat_cruise_hz": f_cruise, "tailbeat_burst_hz": f_burst,
        "strouhal": f_cruise * 2.0 * a_tail / cruise,
        "slip_ratio": cruise / (spec["wavelength"] * L * f_cruise),
        "pectoral_hz": f_pect, "turn_radius_m": spec["turn_radius"] * L,
        # C-start stage 1: 15-40 ms in adult fish, turning 30-100 degrees (Domenici & Blake)
        "cstart_stage1_s": 0.03, "cstart_turn_deg": 70.0,
        # kick 0.11 s, glide 0.16 s in bluegill (JEB 2009): the coast is ~60% of a cycle
        "coast_share": 0.16 / 0.27,
        "notes": notes,
    }


def summarize_plan(p):
    return "\n".join([
        "%s swimmer (%s%s), %.2f m, %.2f kg (%s)" % (p["mode"], p["plane"], ", guessed" if p["mode_guessed"] else "",
                                                     p["length_m"], p["mass_kg"], p["mass_source"]),
        "stride %.2f m, tail amplitude %.3f m, wave %.2f L" % (p["stride_m"], p["tail_amplitude_m"],
                                                              p["wavelength_body_lengths"]),
        "cruise %.2f m/s at %.2f Hz, critical %.2f, burst %.2f m/s at %.2f Hz; St %.2f, slip %.2f"
        % (p["cruise_speed_mps"], p["tailbeat_cruise_hz"], p["ucrit_mps"], p["burst_speed_mps"],
           p["tailbeat_burst_hz"], p["strouhal"], p["slip_ratio"]),
        "pectoral sculling %.2f Hz, turn radius %.2f m" % (p["pectoral_hz"], p["turn_radius_m"]),
    ] + ["NOTE " + n for n in p["notes"]])


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

class SwimChecks:
    def __init__(self, sw):
        self.sw = sw
        rig = sw.body.rig
        self.meshes = []
        for o in fin_mod._bound(rig):
            m = rig.matrix_world.inverted() @ o.matrix_world
            names = {g.index: g.name for g in o.vertex_groups if g.name in rig.data.bones}
            cos = [m @ v.co for v in o.data.vertices]
            ws = []
            for v in o.data.vertices:
                w = {names[g.group]: g.weight for g in v.groups if g.group in names and g.weight > 0}
                t = sum(w.values())
                ws.append({k: x / t for k, x in w.items()} if t else {})
            faces = [tuple(p.vertices) for p in o.data.polygons]
            edges = {(min(a, b), max(a, b)) for f in faces for a, b in zip(f, f[1:] + f[:1])}
            rest_len = {e: (cos[e[0]] - cos[e[1]]).length for e in edges}
            sliver = []
            for f in faces:
                nv = Vector((0.0, 0.0, 0.0))
                for k in range(len(f)):
                    nv += cos[f[k]].cross(cos[f[(k + 1) % len(f)]])
                longest = max((cos[f[k]] - cos[f[(k + 1) % len(f)]]).length for k in range(len(f)))
                sliver.append(0.5 * nv.length < 0.1 * longest * longest)
            self.meshes.append({"cos": cos, "ws": ws, "faces": faces, "sliver": sliver,
                                "edges": [e for e in edges if rest_len[e] > 1e-9], "rest_len": rest_len})

    def skin(self, mats):
        body = self.sw.body
        deform = {n: mats[n] @ body.rest[n].inverted() for n in body.rest}
        stretch, flipped = 1.0, 0
        for m in self.meshes:
            pos = []
            for co, ws in zip(m["cos"], m["ws"]):
                p = Vector((0.0, 0.0, 0.0))
                for n, w in ws.items():
                    p += (deform[n] @ co) * w
                pos.append(p if ws else co)
            for e in m["edges"]:
                stretch = max(stretch, (pos[e[0]] - pos[e[1]]).length / m["rest_len"][e])
            for fi, f in enumerate(m["faces"]):
                w = m["ws"][f[0]]
                if m["sliver"][fi] or not w:
                    continue
                n0, n1 = Vector((0.0, 0.0, 0.0)), Vector((0.0, 0.0, 0.0))
                for k in range(len(f)):
                    n0 += m["cos"][f[k]].cross(m["cos"][f[(k + 1) % len(f)]])
                    n1 += pos[f[k]].cross(pos[f[(k + 1) % len(f)]])
                top = max(w, key=w.get)
                if n1.length > 1e-12 and n1.dot(deform[top].to_3x3() @ n0) < 0.0:
                    flipped += 1
        return stretch, flipped

    def lateral(self, mats, bone):
        """A bone's tail across the body's travel line, in its wave plane."""
        from .motion import tail_of
        return tail_of(self.sw.body, mats, bone).dot(self.sw.disp)

    def fin_clearance(self, mats):
        """Smallest distance of a paired fin's ray tip from the axial chain, over
        that bone's body radius."""
        from .flight import _seg_dist
        from .motion import tail_of
        body, sw = self.sw.body, self.sw
        worst = float("inf")
        for f in sw.fins.fins:
            if not f["side"]:
                continue
            for r in f["rays_rest"]:
                p = tail_of(body, mats, r["name"])
                for n in sw.axial:
                    rad = sw.radius.get(n, 0.0)
                    if rad > 0:
                        worst = min(worst, _seg_dist(p, mats[n].translation, tail_of(body, mats, n)) / rad)
        return worst


def _check_swim(sw, checks, keyed, ev, infos, loop=False, amp_plan=None, stretch_limit=3.0,
                wave=False):
    from .actions import _check_common, _pose_gap
    body, bm = sw.body, sw.bm
    r = _check_common(body, bm, keyed, ev, infos, planted=[], posed_limbs=[],
                      rest_floor=bm["floor"], starts_at_rest=False)
    # a swimmer has no floor
    r["failures"] = [f for f in r["failures"] if "the floor" not in f]
    evaluated = ev["evaluated"]
    frames = [f for f, _ in keyed]
    use = frames[:-1] if loop else frames
    if loop:
        seam, bone = _pose_gap(body.rig, evaluated[frames[0]], evaluated[frames[-1]])
        r["loop_seam"] = round(seam, 6)
        if seam > 1e-4 * bm["size"]:
            r["failures"].append("loop seam %.5f on %s" % (seam, bone))
    worst_s, worst_f, at = 1.0, 0, None
    _, rest_f = checks.skin(body.fk())
    for f in use[::max(1, len(use) // 12)]:
        s, fl = checks.skin(evaluated[f])
        worst_s = max(worst_s, s)
        if fl - rest_f > worst_f:
            worst_f, at = fl - rest_f, f
    r["stretch_max"] = round(worst_s, 3)
    r["flipped_faces"] = worst_f
    if worst_s > stretch_limit:
        r["failures"].append("skin stretches to %.1fx" % worst_s)
    if worst_f:
        r["failures"].append("%d faces turn inside out at frame %d" % (worst_f, at))
    if any(f["side"] for f in sw.fins.fins):
        rest_c = checks.fin_clearance(body.fk())
        c = min(checks.fin_clearance(evaluated[f]) for f in use)
        r["fin_clearance"] = round(c, 3)
        if c < min(0.8, 0.8 * rest_c):
            r["failures"].append("a paired fin passes into the body (%.2f of its radius)" % c)
    sc = sw.scale
    if sw.caudal is not None:
        # the ray reaching furthest back, and the envelope where its tip is -
        # the middle ray of a forked tail ends in the notch
        from .motion import tail_of
        rest = body.fk()
        tip = max((r["name"] for r in sw.caudal["rays_rest"]),
                  key=lambda nm: -tail_of(body, rest, nm).dot(bm["fwd"]))
        z_tip = max(0.0, min(1.0, (sw.snout_u - tail_of(body, rest, tip).dot(bm["fwd"])) / sw.length))
        ys = [checks.lateral(evaluated[f], tip) for f in use]
        hs = [checks.lateral(evaluated[f], sw.axial[0]) for f in use]
        r["tail_pp_m"] = round((max(ys) - min(ys)) * sc, 4)
        r["head_pp_m"] = round((max(hs) - min(hs)) * sc, 4)
        if amp_plan is not None:
            want = 2.0 * amp_plan * sw.spec["envelope"](z_tip) / sw.spec["envelope"](1.0) * sc
            r["tail_pp_plan_m"] = round(want, 4)
            if abs(r["tail_pp_m"] - want) > 0.2 * want:
                r["failures"].append("tail fin sweeps %.3f m peak to peak, planned %.3f"
                                     % (r["tail_pp_m"], want))
    if wave and loop and len(use) >= 8:
        # The wave must travel tailward. A standing wave animates beautifully and
        # swims nowhere; a headward one swims backward.
        phases = []
        n = len(use)
        for i, name in enumerate(sw.axial):
            if sw.z[i + 1] < 0.35:
                continue
            ys = [checks.lateral(evaluated[f], name) for f in use]
            re = sum(y * math.cos(2 * math.pi * k / n) for k, y in enumerate(ys))
            im = sum(y * math.sin(2 * math.pi * k / n) for k, y in enumerate(ys))
            phases.append((sw.z[i + 1], math.atan2(im, re)))
        if len(phases) >= 3:
            unwrapped = [phases[0][1]]
            for _, ph in phases[1:]:
                d = (ph - unwrapped[-1] + math.pi) % (2 * math.pi) - math.pi
                unwrapped.append(unwrapped[-1] + d)
            dz = phases[-1][0] - phases[0][0]
            dphi = unwrapped[-1] - unwrapped[0]
            r["wave_travels"] = "tailward" if dphi > 0 else "headward"
            r["measured_wavelength_L"] = round(abs(dz * 2 * math.pi / dphi), 3) if abs(dphi) > 1e-6 else None
            if dphi <= 0:
                r["failures"].append("the body wave travels toward the head - it would swim backward")
    return r


# --------------------------------------------------------------------------
# clips
# --------------------------------------------------------------------------

def _fin_states(p, speed, glide=False):
    """What fins do at a speed: median fins erect below ~1-1.5 L/s and folding
    faster (bluegill; tuna), pectorals against the body at cruise, the tail fin
    cupped - its outer rays lead - and folded to 70% in a glide (JEB 2009)."""
    ls = speed / max(p["length_m"], 1e-9)
    median_fold = 0.8 * _smooth((ls - 1.0) / 1.5)
    return {
        "dorsal": fin_mod.state(fold=median_fold), "anal": fin_mod.state(fold=median_fold),
        "keel": fin_mod.state(fold=median_fold),
        "pectoral": fin_mod.state(fold=0.55 + 0.3 * _smooth(ls / 2.0), stroke=-12.0),
        "pelvic": fin_mod.state(fold=0.4, stroke=-8.0),
        "caudal": fin_mod.state(cup=0.3, fan=0.7 if glide else 1.0),
        "flukes": fin_mod.state(),
    }


def _author(sw, action_name, samples, fps, check):
    from .actions import _author_samples
    return _author_samples(sw.body, sw.rig, action_name, samples, fps, check)


def _finish(r, sw, action, frames, extra):
    if "error" in r:
        return r
    r.update({"rig": sw.rig.name, "action": action.name, "frames": [1, frames],
              "fps": bpy.context.scene.render.fps, "mode": sw.mode})
    r.update(extra)
    return r


def beat(rig_name, role="Swim", speed=None, frames=None, action_name=None, mode=None, fps=None,
         forward="-Y", up="Z", mass_kg=None, min_frames=12):
    """One looping tail beat at `speed` (default cruise for Swim, burst for Sprint)."""
    sw = Swimmer(rig_name, mode=mode, forward=forward, up=up)
    p = plan(sw, mass_kg)
    fps_now = fps or bpy.context.scene.render.fps
    speed = speed or (p["burst_speed_mps"] if role == "Sprint" else p["cruise_speed_mps"])
    f_beat = speed / p["stride_m"]
    natural = fps_now / f_beat
    n = int(frames or max(min_frames, round(natural)))
    fin_states = _fin_states(p, speed)
    samples = [sw.pose((k - 1) / float(n), fins=fin_states) for k in range(1, n + 2)]
    checks = SwimChecks(sw)
    amp = sw.spec["envelope"](1.0) * sw.length
    _, _, action, r = _author(sw, action_name or role, samples, fps,
                              lambda keyed, ev, infos: _check_swim(sw, checks, keyed, ev, infos, loop=True,
                                                                    amp_plan=amp, wave=True))
    duration = (n + 1) / float(fps_now)
    return _finish(r, sw, action, n + 1, {
        "role": role, "plan": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in p.items()},
        "speed_mps": round(speed, 4), "tailbeat_hz": round(f_beat, 4),
        "frames_per_beat_natural": round(natural, 2),
        "playback_speed_scale": round(f_beat * duration, 4)})


def glide(rig_name, frames=48, action_name="Glide", mode=None, fps=None, forward="-Y", up="Z"):
    """Coasting between kicks: body nearly straight, fins folded, a slow drift."""
    sw = Swimmer(rig_name, mode=mode, forward=forward, up=up)
    p = plan(sw)
    fin_states = _fin_states(p, p["burst_speed_mps"], glide=True)
    samples = [sw.pose((k - 1) / float(frames), amp=0.08, fins=fin_states) for k in range(1, frames + 2)]
    checks = SwimChecks(sw)
    _, _, action, r = _author(sw, action_name, samples, fps,
                              lambda keyed, ev, infos: _check_swim(sw, checks, keyed, ev, infos, loop=True))
    return _finish(r, sw, action, frames + 1, {"role": "Glide", "coast_share": round(p["coast_share"], 3)})


def hover(rig_name, frames=None, action_name="Hover", mode=None, fps=None, forward="-Y", up="Z",
          mass_kg=None):
    """Station holding: one pectoral stroke - abduction 60% of it, the faster
    adduction the rest (Walker & Westneat 1997; Hove 2001) - body barely moving,
    median fins up."""
    sw = Swimmer(rig_name, mode=mode, forward=forward, up=up)
    if not sw.fins.by_kind("pectoral"):
        return {"error": "%s has no pectoral fins to hover with" % rig_name}
    p = plan(sw, mass_kg)
    fps_now = fps or bpy.context.scene.render.fps
    natural = fps_now / p["pectoral_hz"]
    n = int(frames or max(12, round(natural)))
    samples = []
    for k in range(1, n + 2):
        t = (k - 1) / float(n)
        u = t / 0.6 if t < 0.6 else 1.0 - (t - 0.6) / 0.4
        stroke = -10.0 + 55.0 * (0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, u))))
        fs = {"dorsal": fin_mod.state(), "anal": fin_mod.state(),
              "pectoral": fin_mod.state(fold=0.1, stroke=stroke, twist=15.0 * math.sin(2 * math.pi * t), fan=1.1),
              "pelvic": fin_mod.state(stroke=6.0 * math.sin(2 * math.pi * t)),
              "caudal": fin_mod.state(cup=0.2)}
        samples.append(sw.pose(t, amp=0.06, fins=fs))
    checks = SwimChecks(sw)
    _, _, action, r = _author(sw, action_name, samples, fps,
                              lambda keyed, ev, infos: _check_swim(sw, checks, keyed, ev, infos, loop=True))
    duration = (n + 1) / float(fps_now)
    return _finish(r, sw, action, n + 1, {"role": "Hover", "pectoral_hz": round(p["pectoral_hz"], 3),
                                          "playback_speed_scale": round(p["pectoral_hz"] * duration, 4)})


def turn(rig_name, side="L", frames=None, action_name=None, mode=None, fps=None, forward="-Y", up="Z",
         bend_deg=60.0):
    """A cruise beat with the body bent into the turn and back out. The engine
    turns the body by `turn_deg` over the clip - the arc swum at cruise on the
    mode's turning radius (0.05-0.1 L flexible fish, ~0.5 L a tuna)."""
    sw = Swimmer(rig_name, mode=mode, forward=forward, up=up)
    p = plan(sw)
    fps_now = fps or bpy.context.scene.render.fps
    n = int(frames or max(16, round(fps_now / p["tailbeat_cruise_hz"])))
    sign = 1.0 if side == "L" else -1.0
    bend_deg = min(bend_deg, 0.8 * sw.limits.get("bend_clean_deg", bend_deg))
    fin_states = _fin_states(p, p["cruise_speed_mps"])
    fin_states["dorsal"] = fin_mod.state()          # erect for the turn
    fin_states["anal"] = fin_mod.state()
    samples = []
    for k in range(1, n + 1):
        t = (k - 1) / float(n - 1)
        samples.append(sw.pose(t, bend_deg=sign * bend_deg * math.sin(math.pi * t), fins=fin_states))
    checks = SwimChecks(sw)
    _, _, action, r = _author(sw, action_name or "Turn" + side, samples, fps,
                              lambda keyed, ev, infos: _check_swim(sw, checks, keyed, ev, infos))
    dur = (n - 1) / float(fps_now)
    # heading change: the arc swum on the turning radius, but no more than 90
    # degrees a beat - a design cap; the radius alone gave a 1 m fish 380
    turn_deg = min(90.0, math.degrees(p["cruise_speed_mps"] * dur / max(p["turn_radius_m"], 1e-9)))
    return _finish(r, sw, action, n, {"role": "Turn" + side, "turn_deg": round(turn_deg, 1),
                                      "bend_deg": round(bend_deg, 1), "length_s": round(dur, 4), "side": side})


def escape(rig_name, action_name="Escape", mode=None, fps=None, forward="-Y", up="Z", side="L"):
    """A C-start: stage 1 bends the body into a C, stage 2 flips the tail back,
    stage 3 is a burst beat. Stage 1 takes 15-40 ms in adult fish - under a
    frame at 24 fps - so the clip is authored slow and the engine plays it at
    `playback_speed_scale`."""
    sw = Swimmer(rig_name, mode=mode, forward=forward, up=up)
    if sw.spec["plane"] != "lateral":
        return {"error": "a C-start is a fish escape; %s swims %s" % (rig_name, sw.spec["plane"])}
    p = plan(sw)
    fps_now = fps or bpy.context.scene.render.fps
    s1, s2, burst_frames = 4, 5, 12
    n = 1 + s1 + s2 + burst_frames
    # stage 1 turns the head 30-100 degrees; the C is as deep as the skin allows
    c_bend = (1.0 if side == "L" else -1.0) * min(150.0, sw.limits.get("bend_clean_deg", 150.0))
    fins_fast = _fin_states(p, p["burst_speed_mps"])
    fins_flare = dict(fins_fast, dorsal=fin_mod.state(), anal=fin_mod.state(),
                      pectoral=fin_mod.state(fold=0.2, stroke=10.0))
    samples = []
    for k in range(1, n + 1):
        if k <= 1 + s1:
            u = _smooth((k - 1) / float(s1))
            samples.append(sw.pose(0.0, amp=1.0 - u, bend_deg=c_bend * u, fins=fins_flare))
        elif k <= 1 + s1 + s2:
            u = _smooth((k - 1 - s1) / float(s2))
            samples.append(sw.pose(0.25 * u, amp=u, bend_deg=c_bend * (1.0 - u) - 0.3 * c_bend * math.sin(math.pi * u),
                                   fins=fins_flare))
        else:
            u = (k - 1 - s1 - s2) / float(burst_frames)
            samples.append(sw.pose(0.25 + u, fins=fins_fast))
    checks = SwimChecks(sw)
    _, _, action, r = _author(sw, action_name, samples, fps,
                              lambda keyed, ev, infos: _check_swim(sw, checks, keyed, ev, infos))
    real = p["cstart_stage1_s"] * (1.0 + s2 / float(s1)) + 1.0 / p["tailbeat_burst_hz"]
    authored = (n - 1) / float(fps_now)
    return _finish(r, sw, action, n, {"role": "Escape", "turn_deg": p["cstart_turn_deg"],
                                      "real_duration_s": round(real, 4),
                                      "playback_speed_scale": round(authored / real, 4)})


def brake_states(k=1.0):
    """The braking fin pose at share k: pectorals out against the flow, pelvics
    with them, tail flared, median fins up."""
    return {"dorsal": fin_mod.state(), "anal": fin_mod.state(),
            "pectoral": fin_mod.state(fold=-0.1 * k, stroke=65.0 * k, fan=1.0 + 0.2 * k, twist=-20.0 * k),
            "pelvic": fin_mod.state(stroke=35.0 * k, fan=1.0 + 0.1 * k),
            "caudal": fin_mod.state(fan=1.0 + 0.15 * k)}


def brake(rig_name, frames=12, action_name="Brake", mode=None, fps=None, forward="-Y", up="Z"):
    """Pectorals swung out and held against the flow, pelvics out with them (as
    in ~60% of trout braking), tail flared, median fins up. Held at the end."""
    sw = Swimmer(rig_name, mode=mode, forward=forward, up=up)
    if not sw.fins.by_kind("pectoral"):
        return {"error": "%s has no pectoral fins to brake with" % rig_name}
    p = plan(sw)
    cruise = _fin_states(p, p["cruise_speed_mps"])
    share = sw.limits.get("brake_clean", 1.0)
    out = brake_states(share)
    samples = []
    for k in range(1, frames + 1):
        u = _smooth((k - 1) / float(frames - 1))
        mixed = {}
        for key in set(cruise) | set(out):
            a = cruise.get(key) or fin_mod.state()
            b = out.get(key) or fin_mod.state()
            mixed[key] = {q: a[q] + (b[q] - a[q]) * u for q in fin_mod.REST_STATE}
        samples.append(sw.pose(0.0, amp=1.0 - u, fins=mixed, caudal=u < 1.0))
    checks = SwimChecks(sw)
    _, _, action, r = _author(sw, action_name, samples, fps,
                              lambda keyed, ev, infos: _check_swim(sw, checks, keyed, ev, infos))
    return _finish(r, sw, action, frames, {"role": "Brake", "brake_share": share})


def swim_set(rig_name, prefix=None, mode=None, fps=None, forward="-Y", up="Z", mass_kg=None,
             roles=None):
    """Author every swimming clip. Returns {role: report}."""
    prefix = prefix or rig_name
    name = lambda role: "%s_%s" % (prefix, role)
    sw = Swimmer(rig_name, mode=mode, forward=forward, up=up)
    fishy = sw.spec["plane"] == "lateral"
    roles = roles or (("Swim", "Sprint", "Glide", "Hover", "TurnL", "TurnR", "Escape", "Brake") if fishy
                      else ("Swim", "Sprint", "Glide", "TurnL", "TurnR"))
    common = dict(mode=sw.mode, fps=fps, forward=forward, up=up)
    makers = {
        "Swim": lambda: beat(rig_name, "Swim", action_name=name("Swim"), mass_kg=mass_kg, **common),
        "Sprint": lambda: beat(rig_name, "Sprint", action_name=name("Sprint"), mass_kg=mass_kg, **common),
        "Glide": lambda: glide(rig_name, action_name=name("Glide"), **common),
        "Hover": lambda: hover(rig_name, action_name=name("Hover"), mass_kg=mass_kg, **common),
        "TurnL": lambda: turn(rig_name, "L", action_name=name("TurnL"), **common),
        "TurnR": lambda: turn(rig_name, "R", action_name=name("TurnR"), **common),
        "Escape": lambda: escape(rig_name, action_name=name("Escape"), **common),
        "Brake": lambda: brake(rig_name, action_name=name("Brake"), **common),
    }
    return {role: makers[role]() for role in roles}


PLAN_KEYS = ("mode", "plane", "length_m", "mass_kg", "stride_m", "tail_amplitude_m",
             "wavelength_body_lengths", "ucrit_mps", "cruise_speed_mps", "burst_speed_mps",
             "tailbeat_cruise_hz", "tailbeat_burst_hz", "strouhal", "slip_ratio", "pectoral_hz",
             "turn_radius_m", "coast_share", "notes")


def engine_manifest(reports):
    """The `swim` entry of `.moves.json`."""
    ok = {k: r for k, r in reports.items() if isinstance(r, dict) and "error" not in r}
    pl = ok.get("Swim", {}).get("plan", {})
    out = {k: pl.get(k) for k in PLAN_KEYS}
    out["clips"] = {role: r["action"] for role, r in ok.items()}
    out["loops"] = [r["action"] for role, r in ok.items() if role in ("Swim", "Sprint", "Glide", "Hover")]
    # the engine plays a beat clip at speed / (stride_m * clip_beat_hz)
    out["clip_beat_hz"] = {role: round(r["tailbeat_hz"] / r["playback_speed_scale"], 4)
                           for role, r in ok.items() if role in ("Swim", "Sprint")}
    # what Blender measured the tail fin sweeping, peak to peak, per beat clip
    out["tail_pp_m"] = {role: r.get("tail_pp_m") for role, r in ok.items() if role in ("Swim", "Sprint")}
    if "Hover" in ok:
        out["hover"] = {"pectoral_hz": ok["Hover"]["pectoral_hz"],
                        "playback_speed_scale": ok["Hover"]["playback_speed_scale"]}
    for role in ("TurnL", "TurnR"):
        if role in ok:
            out.setdefault("turn", {})[role] = {"turn_deg": ok[role]["turn_deg"], "length_s": ok[role]["length_s"]}
    if "Escape" in ok:
        out["escape"] = {k: ok["Escape"][k] for k in ("turn_deg", "real_duration_s", "playback_speed_scale")}
    out["problems"] = (["%s did not pass: %s" % (k, "; ".join(r.get("failures", [])))
                        for k, r in ok.items() if not r.get("passed")]
                       + ["%s: %s" % (k, r["error"]) for k, r in reports.items()
                          if isinstance(r, dict) and "error" in r])
    return out


def summarize(r):
    from .actions import summarize as base
    if "error" in r:
        return "ERROR: " + r["error"]
    try:
        lines = [base(r)]
    except KeyError:
        lines = ["%s %s" % (r.get("action"), "PASSED" if r.get("passed") else "FAILED")]
        lines += ["  FAIL " + f for f in r.get("failures", [])]
    for k in ("tailbeat_hz", "playback_speed_scale", "tail_pp_m", "tail_pp_plan_m", "head_pp_m",
              "wave_travels", "measured_wavelength_L", "stretch_max", "flipped_faces", "fin_clearance",
              "turn_deg", "real_duration_s"):
        if r.get(k) is not None:
            lines.append("  %s %s" % (k, r[k]))
    return "\n".join(lines)
