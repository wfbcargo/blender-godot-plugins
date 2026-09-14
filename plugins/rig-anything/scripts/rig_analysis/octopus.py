"""An octopus that crawls and swims: clips from the research, checked on playback.

A fish swims from its length and a quadruped walks from a Froude number. An
octopus has no stride and no tail beat to scale; what the literature gives is
speeds in body and mantle lengths and a description of HOW each arm moves.
So every clip here is built from that description and every speed from the
body's dorsal mantle length (DML, eyes to mantle apex).

CRAWL - push by elongation (Levy, Flash & Hochner 2015, Curr Biol). An arm
opposite the direction of travel shortens its base, sticks the suckers at the
end of the shortened part to the ground, and lengthens: the body is pushed
away from a planted point while the rest of the arm stays down. Each arm
pushes in the direction set by where it sits on the body, the crawl is their
vector sum, and body orientation is controlled apart from the direction of
travel. So a crawl here is a direction, not a heading: `CrawlF`, `CrawlB`,
`CrawlL` and `CrawlR` share one arm schedule and one length and an engine
blends them to crawl any way without turning. Real arm choice is NOT rhythmic
(same paper); a loop has to be, and the schedule - four pairs of opposite-side
arms, six planted at any time - is a design. Leading arms stay planted and
shorten; Levy describes pushing, not pulling.

    crawl speed   1.54 DML/s (mean), 1.94 BL/s max - Abdopus aculeatus, Huffard 2006 JEB
    elongation    66% mean, 80% max active (arm L2), >2x passive - JEMBE 2013

SWIM - arm-web sculling. The eight arms open slowly and close fast, together:
a recovery-to-power time ratio of 2:1 swam a robot fastest and is reported to
match the animal (Sfakiotakis, Kazakidi et al.). Water is pushed toward the arm
tips, so the body goes mantle first.

    swim speed    1.27 BL/s mean, 3.06 max - Huffard 2006

JET - "the body is fully stretched out with arms straight and held tightly
together" (Huffard 2006). The mantle squeezes and refills. Jetting stops the
systemic heart, so octopuses jet only a few metres (Wells 1987) - an engine
should run out of jet.

    jet speed     1.73 BL/s mean, 3.29 max - Huffard 2006
    BL / DML      2.48: Huffard gives the mean crawl as both 0.62 BL/s and 1.54 DML/s

REACH - a bend forms at the base and travels to the tip, with a bell-shaped
speed profile of a constant shape (Gutfreund 1996; Yekutieli 2005): the arm is
straight behind the bend and still curled beyond it.

UNVERIFIED, marked in the numbers and the manifest as design: jet frequency
(1.4 Hz - cuttlefish escape jetting, 1.39 Hz; no octopus figure found), the
contraction's share of a jet cycle, how far the mantle squeezes, ventilation at
rest, the arm-stroke frequency and the jet range in metres.

CLIPS

    Idle             loop: ventilation, arm tips sway and lift on the floor
    CrawlF/B/L/R     loop: push by elongation toward each direction, one schedule
    TurnL/R          loop: the same schedule, grips sweeping round the hub
    Swim             loop: one arm-web stroke, mantle first
    Jet              loop: one mantle squeeze, arms straight and together
    Glide            loop: coasting in the jet shape
    Launch           one-shot: floor to jet shape (play backwards to land)
    Reach            one-shot: arm L1 reaches by bend propagation, held extended
"""

from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import gait, motion, verify
from . import tentacles as tn

# ---- numbers, with where they come from
BL_PER_DML = 1.54 / 0.62            # Huffard 2006: the same crawl, 1.54 DML/s and 0.62 BL/s
CRAWL_DML_S = 1.54                   # mean crawl, A. aculeatus (Huffard 2006)
SWIM_BL_S = 1.27                     # mean swim (Huffard 2006)
JET_BL_S = 1.73                      # mean jet (Huffard 2006)
JET_MAX_BL_S = 3.29
ELONGATION_MAX = 1.80                # 80% active, arm L2 (JEMBE 2013)
SHORTENING_MIN = 0.45                # design
RECOVERY_SHARE = 2.0 / 3.0           # open slow : close fast = 2 : 1 (Sfakiotakis / Kazakidi)
JET_HZ = 1.4                         # UNVERIFIED for octopus: cuttlefish escape jets 1.39 Hz
JET_CONTRACT_SHARE = 1.0 / 3.0       # UNVERIFIED design
MANTLE_SQUEEZE = 0.25                # UNVERIFIED design: mantle radius -25% at full contraction
VENT_HZ = 0.4                        # UNVERIFIED design: ventilation at rest
SWIM_STROKE_HZ = 1.0                 # UNVERIFIED design
JET_RANGE_M = 3.0                    # UNVERIFIED design: "only a few metres" (Wells 1987)
TISSUE = 1040.0                      # UNVERIFIED design, kg/m3
CRAWL_DUTY = 0.75                    # design: six of eight arms down
CRAWL_GROUPS = (("L1", "R3"), ("R2", "L4"), ("R1", "L3"), ("L2", "R4"))   # design
ANCHOR_SHARE = 0.55                  # design: suckers grip past the web; at 0.4 the web
                                     # between two arms gripping out of phase folded

# Godot's glTF import maps Blender (x, y, z) to (x, z, -y): -Y forward is +Z.
DIRECTIONS = {"CrawlF": Vector((0, -1, 0)), "CrawlB": Vector((0, 1, 0)),
              "CrawlL": Vector((1, 0, 0)), "CrawlR": Vector((-1, 0, 0))}


def _godot(v):
    return [round(v.x, 4), round(v.z, 4), round(-v.y, 4)]


def smooth(t):
    return tn.smooth(t)


# --------------------------------------------------------------------------
# the body
# --------------------------------------------------------------------------

class Octopus:
    def __init__(self, rig_name, dml_m=None):
        self.t = tn.Tentacles(rig_name)
        self.rig, self.body, self.st = self.t.rig, self.t.body, self.t.st
        if len(self.t.arms) != 8 or "L1" not in self.t.by_label:
            raise ValueError("%s is not an eight-armed body with named arms" % rig_name)
        self.rest = self.body.rest
        self.fps = bpy.context.scene.render.fps
        self.hub = Vector(self.st["hub"])
        self.floor = self.st["floor"]
        self.dml = float(dml_m) if dml_m else self.st["dorsal_mantle_length"]
        self.arm_len = self.st["arm_length"]
        self.size = self.st["reach"]
        neck, apex = Vector(self.st["neck"]), Vector(self.st["apex"])
        self.head_axis = (neck - self.hub).normalized()
        self.mantle_axis = (apex - neck).normalized()
        # the swimming frame: mantle forward (-Y), arms trailing (+Y), and the
        # side the eyes and arms I face (-Y at rest, dorsal) turned up
        self.swim_R = Matrix(((-1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, -1.0, 0.0)))
        self.swim_lift = 1.5 * self.st["mantle_radius"] + max(a["radii"][0] for a in self.t.arms) + 0.02 * self.size

    # ---- matrices
    def body_matrix(self, R3=None, offset=None):
        M = self.rest["body"].copy()
        if R3 is not None:
            pivot = self.hub
            T = Matrix.Translation(pivot) @ R3.to_4x4() @ Matrix.Translation(-pivot)
            M = T @ M
        if offset is not None:
            M = Matrix.Translation(offset) @ M
        return M

    def pose(self, body_mat, arms, mantle_scale=(1.0, 1.0, 1.0), straighten=0.0):
        """All bones: body, head, mantle (squeezed across by `mantle_scale`, and
        swung into line with the head by `straighten` 0..1), arms from joints."""
        R_body = body_mat.to_3x3() @ self.rest["body"].to_3x3().inverted()
        mantle_rot = None
        if straighten:
            corr = Matrix.Rotation(self.mantle_axis.angle(self.head_axis) * straighten, 3,
                                   self.mantle_axis.cross(self.head_axis).normalized())
            mantle_rot = R_body @ corr @ R_body.inverted()
        mats = self.t.body_mats(body_mat, mantle_scale=mantle_scale, mantle_rot=mantle_rot)
        for label, pts in arms.items():
            mats.update(self.t.chain(self.t.by_label[label], pts, body_mat))
        return self.body.fk(mats)

    def carried(self, body_mat, arm):
        carry = body_mat @ self.rest["body"].inverted()
        return [carry @ j for j in arm["joints"]]

    def on_floor(self, arm, pts):
        out = []
        for k, p in enumerate(pts):
            r = arm["radii"][k]
            out.append(Vector((p.x, p.y, max(p.z, self.floor + r))) if p.z < self.floor + r else p)
        return out

    # ---- speeds from size
    def plan(self, mass_kg=None):
        from .flight import mesh_volume
        vol, closed = mesh_volume(self.rig)
        mass = float(mass_kg) if mass_kg else vol * TISSUE
        bl = BL_PER_DML * self.dml
        return {
            "dml_m": self.dml, "body_length_m": bl, "arm_length_m": self.arm_len,
            "arms_per_dml": self.arm_len / self.dml, "mass_kg": mass,
            "mass_source": "given" if mass_kg else "skin volume x %.0f kg/m3 (design)%s"
            % (TISSUE, "" if closed else ", mesh not closed"),
            "crawl_speed_mps": CRAWL_DML_S * self.dml, "swim_speed_mps": SWIM_BL_S * bl,
            "jet_speed_mps": JET_BL_S * bl, "jet_max_speed_mps": JET_MAX_BL_S * bl,
            "jet_hz": JET_HZ, "jet_contract_share": JET_CONTRACT_SHARE, "mantle_squeeze": MANTLE_SQUEEZE,
            "swim_stroke_hz": SWIM_STROKE_HZ, "recovery_share": RECOVERY_SHARE, "vent_hz": VENT_HZ,
            "jet_range_m": JET_RANGE_M, "elongation_max": ELONGATION_MAX,
            "notes": ["speeds are Abdopus aculeatus means (Huffard 2006) scaled by DML - a %.2f m DML is "
                      "extrapolated from a small octopus" % self.dml,
                      "UNVERIFIED design: jet_hz, jet_contract_share, mantle_squeeze, vent_hz, "
                      "swim_stroke_hz, jet_range_m, tissue density"],
        }


def summarize_plan(p):
    return "\n".join([
        "octopus: DML %.3f m, BL %.3f m, arms %.3f m (%.1f DML), %.2f kg (%s)"
        % (p["dml_m"], p["body_length_m"], p["arm_length_m"], p["arms_per_dml"], p["mass_kg"], p["mass_source"]),
        "crawl %.3f m/s, swim %.3f m/s at %.1f Hz strokes, jet %.3f m/s (max %.3f) at %.1f Hz for %.0f m"
        % (p["crawl_speed_mps"], p["swim_speed_mps"], p["swim_stroke_hz"], p["jet_speed_mps"],
           p["jet_max_speed_mps"], p["jet_hz"], p["jet_range_m"]),
    ] + ["NOTE " + n for n in p["notes"]])


# --------------------------------------------------------------------------
# checks on Blender's playback
# --------------------------------------------------------------------------

class Skin:
    """Linear blend skinning of the bound mesh in numpy, for stretch, folded
    faces and the lowest point of any pose."""

    def __init__(self, o, influences=4):
        rig = o.rig
        self.o = o
        self.names = [b.name for b in rig.data.bones]
        index = {n: i for i, n in enumerate(self.names)}
        meshes = [m for m in bpy.data.objects if m.type == "MESH" and any(
            md.type == "ARMATURE" and md.object == rig for md in m.modifiers)]
        self.parts = []
        to_arm = rig.matrix_world.inverted()
        for ob in meshes:
            me = ob.data
            M = to_arm @ ob.matrix_world
            V = np.array([tuple(M @ v.co) for v in me.vertices])
            groups = {g.index: index[g.name] for g in ob.vertex_groups if g.name in index}
            idx = np.zeros((len(V), influences), dtype=int)
            w = np.zeros((len(V), influences))
            for i, v in enumerate(me.vertices):
                gs = sorted(((groups[g.group], g.weight) for g in v.groups if g.group in groups and g.weight > 0),
                            key=lambda x: -x[1])[:influences]
                tot = sum(x[1] for x in gs) or 1.0
                for k, (bi, wt) in enumerate(gs):
                    idx[i, k], w[i, k] = bi, wt / tot
            me.calc_loop_triangles()
            tris = np.array([tuple(t.vertices) for t in me.loop_triangles])
            e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
            e = np.unique(np.sort(e, axis=1), axis=0)
            rest_len = np.linalg.norm(V[e[:, 0]] - V[e[:, 1]], axis=1)
            keep = rest_len > 1e-9
            n0 = np.cross(V[tris[:, 1]] - V[tris[:, 0]], V[tris[:, 2]] - V[tris[:, 0]])
            area2 = np.linalg.norm(n0, axis=1)
            longest = np.max(np.stack([np.linalg.norm(V[tris[:, a]] - V[tris[:, b]], axis=1)
                                       for a, b in ((0, 1), (1, 2), (2, 0))]), axis=0)
            sliver = area2 < 0.2 * longest * longest
            web = self._web(o, V)
            self.parts.append({"V": V, "Vh": np.hstack([V, np.ones((len(V), 1))]), "idx": idx, "w": w,
                               "tris": tris, "edges": e[keep], "rest_len": rest_len[keep], "n0": n0,
                               "sliver": sliver, "top": idx[tris[:, 0], 0],
                               "web": web[tris].sum(axis=1) >= 2})
        rest = o.rest
        self.rest_inv = np.array([np.array(rest[n].inverted()) for n in self.names])
        m = self.measure(o.body.fk())
        self.rest_flips, self.rest_pleats = m["flipped"], m["pleats"]

    @staticmethod
    def _web(o, V):
        """Skin that is neither arm nor body: the web between the arms, and the
        membrane round the mouth. A closing umbrella must pleat - a disc of arms
        turned into a cone has less circumference to cover - so a face turned
        over there is reported as a pleat, not failed as a fold."""
        near = np.zeros(len(V), dtype=bool)
        for arm in o.t.arms:
            pts = np.array([tuple(p) for p in arm["joints"]])
            s, dist, L = tn._polyline_param(V, pts)
            r = np.interp(s, np.linspace(0, L, len(arm["radii"])), arm["radii"])
            near |= dist < 1.35 * np.maximum(r, 0.004)
        # the head and mantle - but not the oral disc under them, which is web
        # running in to the mouth between the arm bases
        axis = np.array([tuple(o.hub), o.st["neck"], o.st["apex"]])
        sb, db, _ = tn._polyline_param(V, axis)
        neck_s = (Vector(o.st["neck"]) - o.hub).length
        near |= (db < 1.25 * max(o.st["head_radius"], o.st["mantle_radius"])) & \
                ((sb > 0.3 * neck_s) | (V[:, 2] > o.hub.z + 0.5 * o.st["head_radius"]))
        return ~near

    def positions(self, mats, part):
        D = np.array([np.array(mats[n]) for n in self.names]) @ self.rest_inv
        P = np.zeros((len(part["V"]), 3))
        for k in range(part["idx"].shape[1]):
            Dk = D[part["idx"][:, k]]
            P += part["w"][:, k:k + 1] * np.einsum("nij,nj->ni", Dk, part["Vh"])[:, :3]
        return P, D

    def measure(self, mats):
        stretch, flipped, pleats, low = 1.0, 0, 0, float("inf")
        for part in self.parts:
            P, D = self.positions(mats, part)
            e = part["edges"]
            ratio = np.linalg.norm(P[e[:, 0]] - P[e[:, 1]], axis=1) / part["rest_len"]
            stretch = max(stretch, float(np.percentile(ratio, 99.9)))
            t = part["tris"]
            n1 = np.cross(P[t[:, 1]] - P[t[:, 0]], P[t[:, 2]] - P[t[:, 0]])
            R = D[part["top"], :3, :3]
            n0r = np.einsum("nij,nj->ni", R, part["n0"])
            bad = (np.einsum("ni,ni->n", n1, n0r) < 0.0) & ~part["sliver"]
            flipped += int((bad & ~part["web"]).sum())
            pleats += int((bad & part["web"]).sum())
            low = min(low, float(P[:, 2].min()))
        return {"stretch": stretch, "flipped": flipped, "pleats": pleats, "lowest": low}


def _joints(o, mats, arm):
    names = arm["bones"]
    pts = [mats[n].translation.copy() for n in names]
    last = o.rig.data.bones[names[-1]]
    pts.append(mats[names[-1]] @ Vector((0.0, last.length, 0.0)))
    return pts


def _check(o, skin, keyed, ev, loop, floor=True, stretch_limit=2.6, samples=16):
    failures, r = [], {}
    size = o.size
    r["prediction_error_m"] = round(ev["prediction_error"], 6)
    if ev["prediction_error"] > 1e-3 * size:
        failures.append("Blender's playback misses the prediction by %.4f m at %s"
                        % (ev["prediction_error"], ev["prediction_worst"]))
    evaluated = ev["evaluated"]
    frames = [f for f, _ in keyed]
    use = frames[:-1] if loop else frames
    if loop:
        a, b = evaluated[frames[0]], evaluated[frames[-1]]
        seam = max(max((a[n].translation - b[n].translation).length,
                       ((a[n].to_3x3() - b[n].to_3x3()) @ Vector((0, 1, 0))).length * 0.05)
                   for n in a)
        r["loop_seam"] = round(seam, 6)
        if seam > 1e-4 * size:
            failures.append("loop seam %.5f" % seam)
    worst = {"stretch": 1.0, "flipped": 0, "pleats": 0, "lowest": float("inf")}
    at = None
    for f in use[::max(1, len(use) // samples)] + [use[-1]]:
        m = skin.measure(evaluated[f])
        worst["stretch"] = max(worst["stretch"], m["stretch"])
        if m["flipped"] - skin.rest_flips > worst["flipped"]:
            worst["flipped"], at = m["flipped"] - skin.rest_flips, f
        worst["pleats"] = max(worst["pleats"], m["pleats"] - skin.rest_pleats)
        worst["lowest"] = min(worst["lowest"], m["lowest"])
    r["web_pleats"] = worst["pleats"]
    r["stretch_max"] = round(worst["stretch"], 3)
    r["flipped_faces"] = worst["flipped"]
    r["skin_lowest_m"] = round(worst["lowest"], 4)
    if worst["stretch"] > stretch_limit:
        failures.append("skin stretches to %.2fx (99.9th percentile edge)" % worst["stretch"])
    if worst["flipped"]:
        failures.append("%d faces turn inside out at frame %d" % (worst["flipped"], at))
    tol = 0.004 * size
    if floor and worst["lowest"] < o.floor - tol:
        failures.append("skin reaches %.4f m, under the floor by more than %.4f" % (worst["lowest"], tol))
    # arm length, bone by bone, against rest
    lo, hi = float("inf"), 0.0
    for arm in o.t.arms:
        for f in use:
            pts = _joints(o, evaluated[f], arm)
            for k, l in enumerate(arm["lengths"]):
                q = (pts[k + 1] - pts[k]).length / l
                lo, hi = min(lo, q), max(hi, q)
    r["segment_length_range"] = [round(lo, 3), round(hi, 3)]
    if hi > ELONGATION_MAX + 1e-3:
        failures.append("an arm segment stretches to %.2fx - octopus arms elongate up to %.2fx"
                        % (hi, ELONGATION_MAX))
    if lo < SHORTENING_MIN:
        failures.append("an arm segment shortens to %.2fx" % lo)
    r["failures"] = failures
    return r


def bake(o, action, keyed):
    """motion.bake, plus scale - the mantle squeezes."""
    motion.bake(o.body, action, keyed)
    rig = o.rig
    for frame, posed in keyed:
        basis = o.body.basis(posed)
        for name in ("mantle",):
            pb = rig.pose.bones[name]
            pb.scale = basis[name].to_scale()
            pb.keyframe_insert("scale", frame=frame)
    for fc in motion._fcurves(action):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


def _author(o, action_name, poses, check):
    scene = bpy.context.scene
    rig = o.rig
    snap = verify._snapshot(rig)
    scales = {pb.name: tuple(pb.scale) for pb in rig.pose.bones}
    ad = rig.animation_data or rig.animation_data_create()
    prev_action, prev_frame = ad.action, scene.frame_current
    keyed = list(enumerate(poses, start=1))
    action = gait._fresh_action(rig, action_name)
    try:
        bake(o, action, keyed)
        ev = motion.evaluate(o.body, action, keyed)
        if "error" in ev:
            return action, {"error": ev["error"]}
        report = check(keyed, ev)
        report["passed"] = not report["failures"]
    finally:
        scene.frame_set(prev_frame)
        try:
            if prev_action is not None:
                verify.bind_action(rig, prev_action)
            else:
                ad.action = None
        except ReferenceError:
            ad.action = None
        verify._restore(rig, snap)
        for pb in rig.pose.bones:
            pb.scale = scales[pb.name]
    report.update({"action": action.name, "frames": [1, len(poses)], "fps": o.fps})
    return action, report


def _rotate_tail(pts, k, R3):
    """Turn joints after k about joint k."""
    pivot = pts[k]
    return pts[:k + 1] + [pivot + R3 @ (p - pivot) for p in pts[k + 1:]]


def _lift_axis(pts, k):
    seg = pts[min(k + 1, len(pts) - 1)] - pts[max(k - 1, 0)]
    ax = seg.cross(Vector((0, 0, 1)))
    return ax.normalized() if ax.length > 1e-9 else Vector((1, 0, 0))


def _raise(pts, k, ang):
    """Turn the joints after k about joint k so they rise by angle `ang`."""
    ax = _lift_axis(pts, k)
    R = Matrix.Rotation(ang, 3, ax)
    seg = pts[-1] - pts[k]
    if (R @ seg).z < seg.z:
        R = Matrix.Rotation(-ang, 3, ax)
    return _rotate_tail(pts, k, R)


# --------------------------------------------------------------------------
# ground
# --------------------------------------------------------------------------

def idle_arms(o, t, body_mat):
    """Arms on the floor, the outer half swaying and the tips lifting a little.
    `t` 0..1 is one ventilation."""
    out = {}
    for i, arm in enumerate(o.t.arms):
        pts = o.carried(body_mat, arm)
        n = len(arm["bones"])
        ph = 2 * math.pi * (t + i / 8.0)
        for k in range(n):
            w = smooth((k / n - 0.35) / 0.5)
            if w <= 0:
                continue
            ang = math.radians(3.0) * w * math.sin(ph - 1.6 * math.pi * k / n)
            pts = _rotate_tail(pts, k, Matrix.Rotation(ang, 3, Vector((0, 0, 1))))
        lift = math.radians(10.0) * (0.5 + 0.5 * math.sin(ph))
        for k in range(n - 3, n):
            pts = _raise(pts, k, lift)
        out[arm["label"]] = o.on_floor(arm, pts)
    return out


def idle(rig_name, action_name=None):
    o = Octopus(rig_name)
    n = max(24, round(o.fps / VENT_HZ))
    poses = []
    for f in range(n + 1):
        t = f / n
        s = 1.0 + 0.06 * math.sin(2 * math.pi * t)
        bm = o.body_matrix(offset=Vector((0, 0, 0.002 * math.sin(2 * math.pi * t))))
        poses.append(o.pose(bm, idle_arms(o, t, bm), mantle_scale=(s, 1.0, s)))
    skin = Skin(o)
    _, r = _author(o, action_name or rig_name + "_Idle", poses,
                   lambda keyed, ev: _check(o, skin, keyed, ev, loop=True))
    r.update({"role": "Idle", "vent_hz": VENT_HZ, "playback_speed_scale": round(VENT_HZ * (n + 1) / o.fps, 4)})
    return r


class CrawlSchedule:
    """Which arm is down when, where its suckers grip, and how the grip moves
    under the body while down: along `direction` at `speed` for a crawl, or
    round the hub at `omega` rad/s for a turn on the spot."""

    def __init__(self, o, direction, speed, cycle_s, anchor_share=None, falloff=2.0, omega=0.0):
        self.o = o
        self.falloff = falloff
        self.v = direction.normalized() if direction.length > 0 else Vector((0, 0, 0))
        self.speed = speed
        self.omega = omega
        self.T = cycle_s
        self.duty = CRAWL_DUTY
        self.D = speed * self.duty * cycle_s                # grip travel per stance
        self.A = omega * self.duty * cycle_s                # grip turn per stance
        self.phase = {}
        for g, labels in enumerate(CRAWL_GROUPS):
            for lab in labels:
                self.phase[lab] = g / float(len(CRAWL_GROUPS))
        self.k = max(2, round((anchor_share or ANCHOR_SHARE) * len(o.t.arms[0]["bones"])))
        self.hub = Vector((o.hub.x, o.hub.y, 0.0))

    def _move(self, x):
        """The grip's rigid move at stance share x: +0.5 touch-down, -0.5 lift-off."""
        M = Matrix.Translation(self.v * self.D * x)
        if self.A:
            M = Matrix.Translation(self.hub) @ Matrix.Rotation(self.A * x, 4, "Z") @ Matrix.Translation(-self.hub) @ M
        return M

    def grip(self, arm, t):
        """(move, lift, in stance, swing share) at clip time t 0..1."""
        ph = (t + self.phase[arm["label"]]) % 1.0
        if ph < self.duty:
            return self._move(0.5 - ph / self.duty), Vector((0, 0, 0)), True, 0.0
        u = (ph - self.duty) / (1.0 - self.duty)
        travel = max(self.D, abs(self.A) * self.grip_radius(arm))
        lift = (0.25 * travel + 0.2 * arm["radii"][self.k]) * math.sin(math.pi * u)
        return self._move(-0.5 + smooth(u)), Vector((0, 0, lift)), False, u

    def grip_radius(self, arm):
        J = arm["joints"][self.k]
        return (Vector((J.x, J.y, 0.0)) - self.hub).length

    def planted_velocity(self, p):
        """How a planted point moves under the body."""
        return -self.v * self.speed + Vector((0, 0, -self.omega)).cross(Vector((p.x, p.y, 0.0)) - self.hub)


def crawl_arms(o, sched, t, body_mat):
    """The part of the arm between body and grip is its rest shape displaced
    toward where the grip is now, more toward the grip and hardly at the base
    - so an arm with its grip at rest IS the rest arm, and the web between two
    arm bases barely moves. A Hermite span from base to grip re-spaced the
    base joints of every arm and folded the web at all of them."""
    out, planted = {}, {}
    k = sched.k
    for arm in o.t.arms:
        rest = o.carried(body_mat, arm)
        M, lift, down, u = sched.grip(arm, t)
        J = arm["joints"][k]
        grip_rest = Vector((J.x, J.y, o.floor + arm["radii"][k]))
        A = M @ grip_rest + lift
        shift = A - grip_rest
        base_shift = rest[0] - arm["joints"][0]
        prox = [rest[j] + (shift - base_shift) * (j / k) ** sched.falloff for j in range(k)]
        distal = [M @ p + lift for p in arm["joints"][k:]]
        pts = prox + distal
        if not down:
            pts = _raise(pts, k, math.radians(20.0) * math.sin(math.pi * u))
        out[arm["label"]] = o.on_floor(arm, pts)
        planted[arm["label"]] = down
    return out, planted


def _grip_cycle(o, rig_name, role, sched, n, action_name):
    poses, plants = [], []
    for f in range(n + 1):
        t = f / n
        bm = o.body_matrix(offset=Vector((0, 0, 0.003 * math.sin(2 * math.pi * 4 * t))))
        arms, planted = crawl_arms(o, sched, t, bm)
        s = 1.0 + 0.05 * math.sin(2 * math.pi * t)
        poses.append(o.pose(bm, arms, mantle_scale=(s, 1.0, s)))
        plants.append(planted)
    skin = Skin(o)
    scale = max(sched.speed, abs(sched.omega) * max(sched.grip_radius(a) for a in o.t.arms))

    def check(keyed, ev):
        r = _check(o, skin, keyed, ev, loop=True)
        # suckers: planted joints move under the body exactly as the grip does
        slips, speeds, turns = [], [], []
        evaluated = ev["evaluated"]
        up = Vector((0, 0, 1))
        for i in range(n):
            a, b = evaluated[keyed[i][0]], evaluated[keyed[i + 1][0]]
            for arm in o.t.arms:
                lab = arm["label"]
                if not (plants[i][lab] and plants[i + 1][lab]):
                    continue
                pa, pb_ = _joints(o, a, arm), _joints(o, b, arm)
                for j in range(sched.k, len(pa)):
                    vel = (pb_[j] - pa[j]) * o.fps
                    slips.append((vel - sched.planted_velocity(pa[j])).length)
                    if sched.speed:
                        speeds.append(-vel.dot(sched.v))
                    rel = Vector((pa[j].x, pa[j].y, 0.0)) - sched.hub
                    if sched.omega and rel.length > 1e-6:
                        # a planted point turns under the body at minus the body's rate
                        turns.append(-up.cross(rel).dot(vel) / rel.length_squared)
        slips.sort()
        r["sucker_slip_max_mps"] = round(slips[-1], 5) if slips else None
        if speeds:
            speeds.sort()
            r["measured_speed_mps"] = round(speeds[len(speeds) // 2], 4)
        if turns:
            turns.sort()
            r["measured_turn_rate"] = round(turns[len(turns) // 2], 4)
        if slips and slips[-1] > 0.05 * scale:
            r["failures"].append("planted suckers slip %.4f m/s (%.0f%% of the grip speed)"
                                 % (slips[-1], 100 * slips[-1] / scale))
        return r
    _, r = _author(o, action_name or "%s_%s" % (rig_name, role), poses, check)
    r.update({"role": role, "cycle_s": round(n / float(o.fps), 4), "duty": CRAWL_DUTY,
              "anchor_joint": sched.k,
              # the engine loops over n+1 frames
              "playback_speed_scale": round((n + 1) / float(n), 4)})
    return r


def crawl(rig_name, role="CrawlF", speed=None, cycle_s=1.0, action_name=None, anchor_share=None, falloff=2.0):
    """One crawl cycle toward `role`'s direction. Arms grip where they lie and
    the grip travels back under the body at the crawl speed; an arm on the far
    side of the direction therefore lengthens while down - it pushes."""
    o = Octopus(rig_name)
    p = o.plan()
    speed = speed or p["crawl_speed_mps"]
    n = max(16, round(cycle_s * o.fps))
    sched = CrawlSchedule(o, DIRECTIONS[role], speed, n / float(o.fps), anchor_share, falloff)
    r = _grip_cycle(o, rig_name, role, sched, n, action_name)
    r.update({"speed_mps": round(speed, 4), "grip_travel_m": round(sched.D, 4),
              "direction_godot": _godot(sched.v)})
    return r


def turn(rig_name, side="L", cycle_s=1.0, action_name=None, anchor_share=None, falloff=2.0):
    """Turning on the spot. Body orientation is controlled apart from travel
    (Levy 2015); turned by the engine alone, the planted suckers were dragged
    round at the grip radius. Here they grip and sweep round the hub instead,
    at the rate that moves a grip as fast as a crawl does - a design, no
    turning rate was found. Blender's +Z turn is Godot's +Y, which turns a
    +Z-facing body toward +X: left."""
    o = Octopus(rig_name)
    p = o.plan()
    n = max(16, round(cycle_s * o.fps))
    probe = CrawlSchedule(o, Vector((0, 0, 0)), 0.0, 1.0, anchor_share, falloff)
    r_grip = sum(probe.grip_radius(a) for a in o.t.arms) / len(o.t.arms)
    omega = (1.0 if side == "L" else -1.0) * p["crawl_speed_mps"] / r_grip
    sched = CrawlSchedule(o, Vector((0, 0, 0)), 0.0, n / float(o.fps), anchor_share, falloff, omega=omega)
    r = _grip_cycle(o, rig_name, "Turn" + side, sched, n, action_name)
    r.update({"turn_rate_rad_s": round(omega, 4), "grip_radius_m": round(r_grip, 4), "side": side})
    return r


# --------------------------------------------------------------------------
# water
# --------------------------------------------------------------------------

def water_arms(o, body_mat, spread_deg, base_extra_deg=30.0, tip_deg=None, lag=0.0, spread_fn=None,
               sway=0.0, t=0.0, crown=0.1):
    """Arms trailing behind a mantle-first body, each in the plane through the
    travel axis and its own base: the angle off the axis runs from
    spread + base_extra near the base to `tip_deg` at the tip. `spread_fn(s)`
    overrides the spread by share along the arm - how a stroke lags down it.

    Each arm leaves the body at its REST angle and turns onto that profile
    over the first `crown` of its length. Turned at its first joint instead,
    every arm bent 70 degrees across a base thicker than the bend and folded
    ~800 faces of sucker skin at the crown."""
    R = body_mat.to_3x3() @ o.rest["body"].to_3x3().inverted()
    back = R @ Vector((0, 0, -1))
    out = {}
    for i, arm in enumerate(o.t.arms):
        p0 = o.carried(body_mat, arm)[0]
        radial = R @ Vector(arm["dir"])
        radial = (radial - back * radial.dot(back)).normalized()
        first = arm["joints"][1] - arm["joints"][0]
        theta0 = math.degrees(first.angle(Vector((0, 0, -1))))
        L = sum(arm["lengths"])
        pts = [p0]
        s = 0.0
        for k, l in enumerate(arm["lengths"]):
            share = (s + 0.5 * l) / L
            spread = spread_fn(share) if spread_fn else spread_deg
            tip = spread if tip_deg is None else tip_deg
            target = tip + (spread + base_extra_deg - tip) * (1.0 - share) ** 2
            ang = math.radians(target + (theta0 - target) * math.exp(-(s / L) / crown))
            if sway:
                ang += math.radians(sway) * share * math.sin(2 * math.pi * (t + i / 8.0) - 3.0 * share)
            d = back * math.cos(ang) + radial * math.sin(ang)
            pts.append(pts[-1] + d * l)
            s += l
        out[arm["label"]] = pts
    return out


def _water_body(o):
    return o.body_matrix(R3=o.swim_R, offset=Vector((0, 0, o.swim_lift)))


def jet_pose(o, u_squeeze=0.0):
    bm = _water_body(o)
    s = 1.0 - MANTLE_SQUEEZE * u_squeeze
    arms = water_arms(o, bm, spread_deg=2.0 + 2.0 * (1 - u_squeeze), base_extra_deg=18.0, tip_deg=-1.5)
    return o.pose(bm, arms, mantle_scale=(s, 1.0 + 0.08 * u_squeeze, s), straighten=1.0)


def _squeeze(t):
    """Mantle contraction over one jet cycle: fast squeeze, slow refill."""
    c = JET_CONTRACT_SHARE
    if t < c:
        return smooth(t / c)
    return 1.0 - smooth((t - c) / (1.0 - c))


def jet(rig_name, action_name=None):
    o = Octopus(rig_name)
    p = o.plan()
    n = max(12, round(o.fps / JET_HZ))
    poses = [jet_pose(o, _squeeze(f / n)) for f in range(n + 1)]
    skin = Skin(o)
    _, r = _author(o, action_name or rig_name + "_Jet", poses,
                   lambda keyed, ev: _check(o, skin, keyed, ev, loop=True, floor=False))
    r.update({"role": "Jet", "jet_hz": JET_HZ, "speed_mps": round(p["jet_speed_mps"], 4),
              "clip_hz": round(o.fps / (n + 1), 4), "playback_speed_scale": round(JET_HZ * (n + 1) / o.fps, 4),
              "mantle_squeeze": MANTLE_SQUEEZE})
    return r


def glide(rig_name, action_name=None, seconds=2.0):
    o = Octopus(rig_name)
    n = round(seconds * o.fps)
    bm = _water_body(o)
    poses = []
    for f in range(n + 1):
        t = f / n
        arms = water_arms(o, bm, spread_deg=5.0 + 2.0 * math.sin(2 * math.pi * t), base_extra_deg=20.0,
                          tip_deg=0.0, sway=6.0, t=t)
        s = 1.0 + 0.03 * math.sin(2 * math.pi * t)
        poses.append(o.pose(bm, arms, mantle_scale=(s, 1.0, s), straighten=1.0))
    skin = Skin(o)
    _, r = _author(o, action_name or rig_name + "_Glide", poses,
                   lambda keyed, ev: _check(o, skin, keyed, ev, loop=True, floor=False))
    r.update({"role": "Glide"})
    return r


def _stroke(t):
    """Arm spread 0 (closed) .. 1 (open): open over the recovery, snap shut."""
    rs = RECOVERY_SHARE
    if t < rs:
        return smooth(t / rs)
    return 1.0 - smooth((t - rs) / (1.0 - rs))


def swim(rig_name, action_name=None, open_deg=55.0, closed_deg=6.0, lag=0.15):
    """One arm-web stroke: all eight arms open slowly and close fast, the
    stroke lagging down each arm so the tips follow through."""
    o = Octopus(rig_name)
    p = o.plan()
    n = max(16, round(o.fps / SWIM_STROKE_HZ))
    bm = _water_body(o)
    poses = []
    for f in range(n + 1):
        t = f / n

        def spread(share, t=t):
            return closed_deg + (open_deg - closed_deg) * _stroke((t - lag * share) % 1.0)
        arms = water_arms(o, bm, spread_deg=0.0, base_extra_deg=25.0, spread_fn=spread)
        s = 1.0 + 0.04 * math.sin(2 * math.pi * t)
        poses.append(o.pose(bm, arms, mantle_scale=(s, 1.0, s), straighten=1.0))
    skin = Skin(o)
    _, r = _author(o, action_name or rig_name + "_Swim", poses,
                   lambda keyed, ev: _check(o, skin, keyed, ev, loop=True, floor=False, stretch_limit=3.2))
    r.update({"role": "Swim", "stroke_hz": SWIM_STROKE_HZ, "speed_mps": round(p["swim_speed_mps"], 4),
              "recovery_share": RECOVERY_SHARE, "open_deg": open_deg, "closed_deg": closed_deg,
              "playback_speed_scale": round(SWIM_STROKE_HZ * (n + 1) / o.fps, 4)})
    return r


def launch(rig_name, action_name=None, seconds=0.75, hop_share=0.9):
    """From resting on the floor to the jet shape: the body pushes off, turns
    mantle first and rises while the arms sweep back, tips last. Played
    backwards it lands."""
    o = Octopus(rig_name)
    n = round(seconds * o.fps)
    start_bm = o.body_matrix()
    start_arms = idle_arms(o, 0.0, start_bm)
    end_bm = _water_body(o)
    end_arms = water_arms(o, end_bm, spread_deg=4.0, base_extra_deg=18.0, tip_deg=-1.5)
    q_end = o.swim_R.to_quaternion()
    to_local = (end_bm @ o.rest["body"].inverted()).inverted()
    start_local = start_arms
    end_local = {lab: [to_local @ p for p in pts] for lab, pts in end_arms.items()}
    poses = []
    for f in range(n + 1):
        u = f / n
        w = smooth(u)
        R3 = Matrix.Identity(3).to_quaternion().slerp(q_end, w).to_matrix()
        # a push-off: the body hops clear while it turns over, or the arms,
        # which follow the body, sweep through the floor it is leaving
        hop = hop_share * o.arm_len * math.sin(math.pi * smooth(u))
        bm = o.body_matrix(R3=R3, offset=Vector((0, 0, o.swim_lift * w + hop)))
        arms = {}
        for arm in o.t.arms:
            lab = arm["label"]
            nb = len(arm["bones"])
            # blend in the body's own frame and carry the result: blended in
            # the world, arm directions stayed put while the body turned over
            # under them, and the crown tore (5.9x stretch, 1600 folds)
            local = tn.blend_shapes(start_local[lab], end_local[lab],
                                    lambda k, u=u, nb=nb: smooth((u - 0.35 * k / nb) / 0.65))
            carry = bm @ o.rest["body"].inverted()
            pts = [carry @ p for p in local]
            arms[lab] = pts
        # Idle starts and Jet ends with the mantle at rest size
        poses.append(o.pose(bm, arms, straighten=w))
    skin = Skin(o)
    _, r = _author(o, action_name or rig_name + "_Launch", poses,
                   lambda keyed, ev: _check(o, skin, keyed, ev, loop=False, floor=True))
    r.update({"role": "Launch", "length_s": round(n / float(o.fps), 4), "lift_m": round(o.swim_lift, 4),
              "hop_m": round(hop_share * o.arm_len, 4)})
    return r


def reach(rig_name, label="L1", action_name=None, elevation_deg=35.0, toward_front_deg=12.0,
          prep_s=0.25, reach_s=1.0, stretch=1.3):
    """Bend propagation. The arm curls, then a bend travels from base to tip
    on a minimum-jerk schedule (bell-shaped speed): straight and aimed behind
    the bend, still curled beyond it. Ends held extended; play backwards to
    withdraw."""
    o = Octopus(rig_name)
    arm = o.t.by_label[label]
    bm = o.body_matrix()
    rest_arms = idle_arms(o, 0.0, bm)
    nb = len(arm["bones"])
    d = Vector(arm["dir"])
    fwd = Vector((0, -1, 0))
    side = 1.0 if d.cross(fwd).z > 0 else -1.0
    aim_h = Matrix.Rotation(side * math.radians(toward_front_deg), 3, Vector((0, 0, 1))) @ d
    aim = (aim_h * math.cos(math.radians(elevation_deg)) + Vector((0, 0, 1)) * math.sin(math.radians(elevation_deg)))
    aim.normalize()
    normal = Vector((0, 0, 1)) - aim * aim.z
    # A curl tightens toward the tip - an inward spiral, which does not run
    # through itself the way a coil of one radius does after a turn.
    # Twelve bones cannot carry a tight curl: at 80 degrees a joint the tip's
    # skin folded on the inside, so no segment turns more than ~40 degrees.
    tip_curl_r = max(4.0 * arm["radii"][-1] + 0.01, max(arm["lengths"]) / 0.7)
    n_prep, n_reach = round(prep_s * o.fps), round(reach_s * o.fps)
    base = o.carried(bm, arm)[0]
    L = arm["length"]

    def coiled(sb_share, st):
        lengths = arm["lengths"]
        cum = [0.0]
        for l in lengths:
            cum.append(cum[-1] + l)

        def kap(i):
            mid = (cum[i] + 0.5 * lengths[i]) / L
            return (1.0 / tip_curl_r) * mid ** 1.2 * smooth((mid - sb_share) / 0.08)
        return tn.curve(base, aim, normal, lengths, kap, stretch=st)

    poses, bends = [], []
    others = {k: v for k, v in rest_arms.items() if k != label}
    for f in range(n_prep + n_reach + 1):
        if f <= n_prep:
            u = f / max(n_prep, 1)
            c = coiled(0.0, 1.0)
            pts = tn.blend_shapes(rest_arms[label], c, lambda k, u=u: smooth(u), base=base)
            sb = 0.0
        else:
            u = (f - n_prep) / n_reach
            sb = tn.min_jerk(u)
            pts = coiled(sb * 1.08, 1.0 + (stretch - 1.0) * smooth(u))
        # the base keeps near its rest direction and turns onto the aim over
        # three segments; aimed from the first joint it folded the crown
        pts = tn.blend_shapes(rest_arms[label], pts, lambda k: 0.3 + 0.7 * smooth(k / 3.0), base=base)
        bends.append(sb)
        arms = dict(others)
        arms[label] = o.on_floor(arm, pts)
        poses.append(o.pose(bm, arms))
    skin = Skin(o)

    def check(keyed, ev):
        r = _check(o, skin, keyed, ev, loop=False)
        evaluated = ev["evaluated"]
        tips = [_joints(o, evaluated[fr], arm)[-1] for fr, _ in keyed]
        speeds = [(tips[i + 1] - tips[i]).length * o.fps for i in range(n_prep, len(tips) - 1)]
        peak = max(range(len(speeds)), key=lambda i: speeds[i]) / max(len(speeds) - 1, 1)
        r["tip_speed_peak_share"] = round(peak, 3)
        r["tip_speed_peak_mps"] = round(max(speeds), 4)
        # where the arm is bent: the first joint past which it turns >20 deg
        # per segment, read on Blender's pose - it must travel outward
        front = []
        for fr, _ in keyed[n_prep:]:
            pts = _joints(o, evaluated[fr], arm)
            k_b = nb
            for k in range(1, nb):
                a_, b_ = pts[k] - pts[k - 1], pts[k + 1] - pts[k]
                if a_.angle(b_, 0.0) > math.radians(20.0):
                    k_b = k
                    break
            front.append(k_b)
        r["bend_joint_track"] = front
        if any(b < a - 1 for a, b in zip(front, front[1:])):
            r["failures"].append("the bend moves back toward the base")
        if not (0.25 <= peak <= 0.75):
            r["failures"].append("tip speed peaks at %.0f%% of the reach - not bell-shaped" % (100 * peak))
        mouth = o.hub
        r["tip_reach_m"] = round((tips[-1] - mouth).length, 4)
        return r
    _, r = _author(o, action_name or "%s_Reach" % rig_name, poses, check)
    r.update({"role": "Reach", "arm": label, "length_s": round((n_prep + n_reach) / float(o.fps), 4),
              "prep_s": prep_s, "elongation": stretch, "tip_bone": arm["bones"][-1]})
    return r


# --------------------------------------------------------------------------
# the set, and the engine's manifest
# --------------------------------------------------------------------------

ROLES = ("Idle", "CrawlF", "CrawlB", "CrawlL", "CrawlR", "TurnL", "TurnR", "Swim", "Jet", "Glide", "Launch",
         "Reach")
LOOPS = ("Idle", "CrawlF", "CrawlB", "CrawlL", "CrawlR", "TurnL", "TurnR", "Swim", "Jet", "Glide")


def octopus_set(rig_name, roles=None, prefix=None):
    prefix = prefix or rig_name
    name = lambda role: "%s_%s" % (prefix, role)
    makers = {
        "Idle": lambda: idle(rig_name, name("Idle")),
        "Swim": lambda: swim(rig_name, name("Swim")),
        "Jet": lambda: jet(rig_name, name("Jet")),
        "Glide": lambda: glide(rig_name, name("Glide")),
        "Launch": lambda: launch(rig_name, name("Launch")),
        "Reach": lambda: reach(rig_name, "L1", name("Reach")),
    }
    for role in DIRECTIONS:
        makers[role] = (lambda role=role: crawl(rig_name, role, action_name=name(role)))
    for side in ("L", "R"):
        makers["Turn" + side] = (lambda side=side: turn(rig_name, side, action_name=name("Turn" + side)))
    return {role: makers[role]() for role in (roles or ROLES)}


def engine_manifest(rig_name, reports):
    o = Octopus(rig_name)
    p = o.plan()
    ok = {k: r for k, r in reports.items() if "error" not in r}
    out = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in p.items()}
    out["clips"] = {role: r["action"] for role, r in ok.items()}
    out["loops"] = [r["action"] for role, r in ok.items() if role in LOOPS]
    crawl_roles = [k for k in ok if k in DIRECTIONS]
    if crawl_roles:
        c = ok[crawl_roles[0]]
        out["crawl"] = {"cycle_s": c["cycle_s"], "duty": c["duty"], "grip_travel_m": c["grip_travel_m"],
                        # the grip is the head of this bone on every arm
                        "anchor_joint": c["anchor_joint"],
                        "sucker_slip_max_mps": {k: ok[k].get("sucker_slip_max_mps") for k in crawl_roles},
                        "speed_mps": c["speed_mps"],
                        "measured_speed_mps": {k: ok[k].get("measured_speed_mps") for k in crawl_roles},
                        "directions": {k: ok[k]["direction_godot"] for k in crawl_roles},
                        "playback_speed_scale": c["playback_speed_scale"],
                        "groups": [list(g) for g in CRAWL_GROUPS]}
    turns = [k for k in ("TurnL", "TurnR") if k in ok]
    if turns:
        out["turn"] = {"rate_rad_s": {k: ok[k]["turn_rate_rad_s"] for k in turns},
                       "measured_rate_rad_s": {k: ok[k].get("measured_turn_rate") for k in turns},
                       "grip_radius_m": ok[turns[0]]["grip_radius_m"],
                       "playback_speed_scale": ok[turns[0]]["playback_speed_scale"],
                       "sucker_slip_max_mps": {k: ok[k].get("sucker_slip_max_mps") for k in turns}}
    for role in ("Swim", "Jet"):
        if role in ok:
            out[role.lower()] = {k: ok[role][k] for k in ("speed_mps", "playback_speed_scale") if k in ok[role]}
    if "Jet" in ok:
        out["jet"].update({"hz": JET_HZ, "contract_share": JET_CONTRACT_SHARE, "range_m": JET_RANGE_M})
    if "Swim" in ok:
        out["swim"].update({"stroke_hz": SWIM_STROKE_HZ, "recovery_share": RECOVERY_SHARE})
    if "Idle" in ok:
        out["idle"] = {"playback_speed_scale": ok["Idle"]["playback_speed_scale"], "vent_hz": VENT_HZ}
    if "Launch" in ok:
        out["launch"] = {"length_s": ok["Launch"]["length_s"], "lift_m": ok["Launch"]["lift_m"]}
    if "Reach" in ok:
        out["reach"] = {k: ok["Reach"][k] for k in ("arm", "length_s", "tip_reach_m", "tip_bone",
                                                     "tip_speed_peak_mps") if k in ok["Reach"]}
    out["arms"] = [{"label": a["label"], "bones": a["bones"], "length_m": round(a["length"], 4),
                    "tip_bone": a["bones"][-1]} for a in o.t.arms]
    out["sockets"] = {"mouth": "body", "funnel": "funnel", "mantle": "mantle"}
    out["problems"] = (["%s did not pass: %s" % (k, "; ".join(r.get("failures", [])))
                        for k, r in ok.items() if not r.get("passed")]
                       + ["%s: %s" % (k, r["error"]) for k, r in reports.items() if "error" in r])
    return out


def summarize(r):
    if "error" in r:
        return "ERROR " + r["error"]
    lines = ["%s %s" % (r.get("action"), "PASSED" if r.get("passed") else "FAILED")]
    lines += ["  FAIL " + f for f in r.get("failures", [])]
    for k in ("prediction_error_m", "loop_seam", "stretch_max", "flipped_faces", "web_pleats", "skin_lowest_m",
              "segment_length_range", "sucker_slip_max_mps", "measured_speed_mps", "speed_mps",
              "turn_rate_rad_s", "measured_turn_rate",
              "grip_travel_m", "tip_speed_peak_share", "tip_speed_peak_mps", "tip_reach_m"):
        if r.get(k) is not None:
            lines.append("  %s %s" % (k, r[k]))
    return "\n".join(lines)
