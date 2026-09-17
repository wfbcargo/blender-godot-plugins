"""L3-L4 muscle definition: sculpted delta parts, scaled by how muscular and how lean the brief is.

MPFB's mesh is smooth, so its muscle macro makes a body bigger, not defined: a muscular man reads as
average. Definition here is a `delta` part - per-vertex heights along the normal, in groups - authored
once with signed distance sculpting on MPFB's default male and put on any MPFB body:

    rep = muscle.define(human, brief)                     # after pipeline.make, before bake_for_game
    rep["weights"]        # per group, 0..1: muscle term x leanness for that group; `bulk` below
    rep["body_fat_pct"]   # the estimate the leanness came from
    rep["applied"]        # delta.apply's report (key hfd:muscle, max heights in mm per group)
    rep["applied_bulk"]   # the same for key hfd:muscle-bulk

    rep = muscle.define(human, brief, geometry=False)     # hfd:muscle at 0: definition only in a normal map
    high = delta.high_copy(human, "hfd:muscle")           # ...baked by lookdev's detail.bake_normal_from_high

The sculpted groups: deltoids, upper arms (biceps, triceps), pectorals, abdominals, obliques (with serratus
and the inguinal line), quadriceps, calves, forearms. Each is a set of pads (ellipsoids whose outer surface
stands `height` proud of the skin at an anchor found by casting a ray from inside a limb or the torso,
trimmed to a plateau) smoothly unioned, minus grooves - polylines of skin points sunk with a smooth
cross-section, tapered at both ends (the sternum, the linea alba ending above the navel, the tendinous
intersections, the rectus femoris and sartorius lines, between the calf heads). A vertex's height is how
deep it lies inside the group's field, masked to skin that faces the way its pad does - so a pad on the chest
does not raise the inside of the arm beside it. Pads are mirrored with |x| rounded near the midline, so the
two sides meet in a soft valley rather than a crease.

hm08 has about 15 mm between vertices, so a form narrower than that cannot be carried: it comes out as a
single vertex standing off its neighbours, which renders as a bright facet stuck through the skin (two of
them sat on Dante's outer thigh). Two limits keep every form resolvable - a groove is never sunk deeper
than `GROOVE_SLOPE` of its own radius, and `despike` pulls back any vertex left standing more than
`SPIKE_LIMIT` off the mean of its neighbours. Forms are many vertices wide, so this takes off facets and
not muscles.

Two groups are derived, not sculpted, from MPFB's own muscle shape (muscle 1.0 against 0.5 along the normal):
`relief` is it high-passed (the back, arms and neck the sculpted groups do not reach; off the front midline,
where MPFB's crease read as a knife cut), `bulk` is it low-passed on the limbs and shoulders (off the trunk
whose girths the fit reached). The fit trades the muscle macro for weight to reach girths - Dante's brief
says muscle 0.9, the fit lands on 0.66, and his arms come out thinner than the forced-macro body's - so
`bulk` is weighted by that shortfall, (brief muscle - fitted macro) / 0.5, on its own key: it is mass, which
fat does not hide and a normal map cannot carry.

**How much shows** (`weights`): definition = muscle term x leanness, per group.

- muscle term: `smoothstep(0.3, 1.0, muscle)`, where muscle is the brief's own `muscle` or its build's
  (scaffold.BUILD_MUSCLE), never the fitted macro: the fit moves the macro to reach girths, and the
  brief is what says the person trains.
- body fat: Deurenberg (1991), 1.2 BMI + 0.23 age - 10.8 (male) - 5.4, with BMI less the share of it
  that is muscle (10 BMI per unit of muscle above 0.5) and firm skin (firmness above 0.5) reading leaner.
- leanness per group: 1 at or under the fat % where that group is fully visible, 0 at or over the %
  where fat hides it, smoothstep between. Abdominals and obliques need the leanest body; forearms,
  calves and deltoids show through more. Women's thresholds are 8 points higher (essential fat).
"""

from __future__ import annotations

import numpy as np

from . import delta, library, sdf

REGION = "muscle"
NAME = "definition-v2"
SCULPTED = ("deltoids", "upper_arms", "pectorals", "abdominals", "obliques", "quadriceps", "calves", "forearms")
DEFINITION = SCULPTED + ("relief",)
GROUPS = DEFINITION + ("bulk",)

# body fat % (male) at which a group is fully visible, and at which it is gone
VISIBLE = {"abdominals": (12.0, 22.0), "obliques": (12.0, 22.0), "pectorals": (13.0, 25.0),
           "quadriceps": (13.0, 25.0), "deltoids": (14.0, 28.0), "upper_arms": (14.0, 28.0), "calves": (15.0, 30.0), "forearms": (15.0, 30.0),
           "relief": (13.0, 27.0)}
FEMALE_OFFSET = 8.0
# a woman's pectorals lie under the breast: only their upper edge reads
FEMALE_GROUP = {"pectorals": 0.35}
MUSCLE_RANGE = (0.3, 1.0)
MUSCLE_BMI = 10.0          # BMI points per unit of muscle above 0.5 that are not fat
FIRMNESS_PCT = 6.0         # body fat points per unit of firmness away from 0.5


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return float(t * t * (3 - 2 * t))


def body_fat(sex, bmi, age, muscle=0.5, firmness=0.5):
    """Estimated body fat %: Deurenberg's adult formula on BMI less its muscle share, firmer reading leaner."""
    lean_bmi = float(bmi) - MUSCLE_BMI * max(float(muscle) - 0.5, 0.0)
    pct = 1.2 * lean_bmi + 0.23 * float(age) - 10.8 * (1.0 if sex == "male" else 0.0) - 5.4
    return pct - FIRMNESS_PCT * (float(firmness) - 0.5)


def brief_inputs(brief):
    """sex, BMI, age, muscle and firmness from a brief (resolved or not)."""
    from . import scaffold, sheet
    s = brief.get("sheet", brief)
    if s.get("bmi") is None or s.get("age") is None:
        s = sheet.resolve(s)["sheet"]
    build = s.get("build") if isinstance(s.get("build"), str) else "average"
    muscle = s.get("muscle") if s.get("muscle") is not None else scaffold.BUILD_MUSCLE.get(build, 0.5)
    firmness = s.get("firmness") if s.get("firmness") is not None else 0.5
    return {"sex": s["sex"], "bmi": float(s["bmi"]), "age": float(s["age"]), "muscle": float(muscle),
            "firmness": float(firmness)}


def weights(brief=None, sex=None, bmi=None, age=None, muscle=None, firmness=None, strength=1.0, fitted_muscle=None):
    """Per-group weights for a brief (or the numbers directly). Returns {"weights", "muscle_term",
    "body_fat_pct", "leanness", "inputs", "definition_total"}. The definition groups: muscle term x leanness.
    `bulk`: how far `fitted_muscle` (the body's MPFB macro after the fit) sits under the brief's muscle, as a
    share of MPFB's 0.5 -> 1.0 muscle sculpt (0 when not given, or when the fit is at or over the brief)."""
    x = brief_inputs(brief) if brief is not None else {}
    for k, v in (("sex", sex), ("bmi", bmi), ("age", age), ("muscle", muscle), ("firmness", firmness)):
        if v is not None:
            x[k] = v
    x.setdefault("firmness", 0.5)
    x.setdefault("muscle", 0.5)
    fat = body_fat(x["sex"], x["bmi"], x["age"], x["muscle"], x["firmness"])
    m = _smoothstep(*MUSCLE_RANGE, x["muscle"])
    off = FEMALE_OFFSET if x["sex"] == "female" else 0.0
    lean, w = {}, {}
    for g in DEFINITION:
        full, gone = VISIBLE[g]
        lean[g] = 1.0 - _smoothstep(full + off, gone + off, fat)
        share = FEMALE_GROUP.get(g, 1.0) if x["sex"] == "female" else 1.0
        w[g] = round(float(strength) * m * lean[g] * share, 4)
    total = round(sum(w.values()), 4)
    w["bulk"] = 0.0 if fitted_muscle is None else \
        round(float(np.clip((x["muscle"] - float(fitted_muscle)) / (1.0 - 0.5), 0.0, 1.0)), 4)
    return {"weights": w, "muscle_term": round(m, 4), "body_fat_pct": round(fat, 2),
            "leanness": {g: round(v, 4) for g, v in lean.items()}, "inputs": x, "definition_total": total}


# ------------------------------------------------------------------ authoring

def reference_body(name="HF_MuscleRef"):
    """MPFB's default male (every macro at its default, gender 1): the body the set is authored on."""
    import bpy
    from . import scaffold
    HumanService, TargetService, _, _ = scaffold.services()
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    macro = TargetService.get_default_macro_info_dict()
    macro["gender"] = 1.0
    human = HumanService.create_human(macro_detail_dict=macro)
    human.name = name
    return human


def _joints(ob, co):
    """Centroids of MPFB's joint-* vertex groups (left side and midline), in the mixed shape."""
    me = ob.data
    n = len(me.vertices)
    idx = {g.index: g.name for g in ob.vertex_groups if g.name.startswith("joint-")}
    acc = {}
    for v in me.vertices:
        for g in v.groups:
            if g.group in idx:
                acc.setdefault(idx[g.group], []).append(v.index)
    out = {name: co[np.asarray(ix)].mean(axis=0) for name, ix in acc.items() if max(ix) < n}
    return out


def _unit(v):
    v = np.asarray(v, np.float64)
    return v / max(np.linalg.norm(v), 1e-12)


class _Skin:
    """Ray casts against the body's surface and limb/torso frames from its joints."""

    def __init__(self, co, faces, joints):
        from mathutils import Vector
        from mathutils.bvhtree import BVHTree
        self.co = co[:delta.BODY_VERTS]
        self.tree = BVHTree.FromPolygons([Vector(p) for p in self.co], [tuple(int(i) for i in f) for f in faces])
        self.j = joints
        self.Vector = Vector

    def cast(self, origin, direction):
        loc, nrm, _, _ = self.tree.ray_cast(self.Vector(origin), self.Vector(_unit(direction)), 1.0)
        if loc is None:
            raise RuntimeError(f"no skin from {np.round(origin, 3)} toward {np.round(direction, 3)}")
        return np.array(loc[:]), _unit(nrm[:])

    def limb(self, a, b, t, theta, lift=0.0):
        """Skin on the limb from joint a to b at `t` along it, `theta` degrees around it (0 front, 90
        lateral, 180 back, -90 medial). Returns (point, normal, limb axis)."""
        ja, jb = self.j[a], self.j[b]
        ax = _unit(jb - ja)
        f = _unit(np.array([0.0, -1.0, 0.0]) - ax * ax[1] * -1.0)
        lat = _unit(np.cross(f, ax))
        if lat[0] < 0:
            lat = -lat
        th = np.radians(theta)
        d = np.cos(th) * f + np.sin(th) * lat
        p, n = self.cast(ja + t * (jb - ja) + lift * d, d)
        return p, n, ax

    def torso(self, x, z, theta=0.0, y=0.0):
        """Skin of the trunk hit from (x, y, z) toward `theta` degrees from the front (-Y) to the left (+X).
        x and z are given on MPFB's default male as MPFB loads its basis (REF) and mapped onto this body
        by its pelvis, neck and shoulder joints."""
        th = np.radians(theta)
        pz, nz = self.j["joint-pelvis"][2], self.j["joint-neck"][2]
        zz = pz + (z - REF["pelvis_z"]) / (REF["neck_z"] - REF["pelvis_z"]) * (nz - pz)
        xx = x / REF["shoulder_x"] * self.j["joint-l-shoulder"][0]
        p, n = self.cast(np.array([xx, y, zz]), np.array([np.sin(th), -np.cos(th), 0.0]))
        return p, n

    def scale(self):
        """This body's size over the default male's, from pelvis to neck."""
        return float((self.j["joint-neck"][2] - self.j["joint-pelvis"][2]) / (REF["neck_z"] - REF["pelvis_z"]))


# MPFB's default male as its basis loads (the numbers `_author_group` places the trunk's pads by)
REF = {"pelvis_z": 0.891, "neck_z": 1.408, "shoulder_x": 0.168}


SINK = 0.3                 # a belly's untrimmed crown stands this share of its depth radius proud of the skin


def _pad(p, n, u, a, b, h):
    """A muscle belly: an ellipsoid with footprint radii a (along u) and b (across), and a depth radius
    the larger of them, whose crown would stand SINK x depth proud of the skin at p - trimmed (in
    `author`) to h. Deep and round, it follows a curved limb instead of standing off it like a plate;
    trimmed, its top is a plateau with a bevelled edge, which is what reads as a defined muscle."""
    n = _unit(n)
    u = _unit(np.asarray(u) - n * (np.asarray(u) @ n))
    v = np.cross(n, u)
    c = max(a, b)
    rot = np.stack([u, v, n], axis=1)
    return sdf.ellipsoid(p - n * (c * (1.0 - SINK)), (a, b, c), rot=rot), n, h


def _author_group(sk, g):
    """(pads [(prim, normal, height)], grooves [(points, radius, depth, taper)]) for group g, left side.
    A groove is a polyline of skin points: vertices within `radius` of it sink up to `depth`, fading over
    the first and last `taper` of its length so it starts and ends without a notch."""
    L = sk.limb
    pads, grooves = [], []

    def pad(anchor, u, a, b, h):
        p, n = anchor[0], anchor[1]
        pads.append(_pad(p, n, u, a, b, h * HEIGHT_GAIN * GROUP_GAIN.get(g, 1.0)))

    def groove(points, r, depth, taper=0.25):
        depth = min(depth * HEIGHT_GAIN * GROUP_GAIN.get(g, 1.0), GROOVE_SLOPE * r)
        grooves.append((np.array([q[0] if isinstance(q, tuple) else q for q in points]), r, depth, taper))

    Z = np.array([0.0, 0.0, 1.0])
    X = np.array([1.0, 0.0, 0.0])
    sh, el, wr = "joint-l-shoulder", "joint-l-elbow", "joint-l-hand"
    hip, kn, an = "joint-l-upper-leg", "joint-l-knee", "joint-l-ankle"
    s = sk.scale()
    T = sk.torso
    if g == "deltoids":
        for t, th, a, b, h in ((0.22, 90, 0.075, 0.045, 0.011), (0.12, 30, 0.06, 0.035, 0.010),
                               (0.15, 150, 0.06, 0.035, 0.009), (-0.02, 80, 0.045, 0.045, 0.007)):
            p, n, ax = L(sh, el, t, th)
            pad((p, n), ax, a * s, b * s, h * s)
        # the deltoid's insertion: its front and back borders meeting on the outside of the arm
        groove([L(sh, el, 0.08, 5), L(sh, el, 0.25, 35), L(sh, el, 0.42, 80)], 0.016 * s, 0.005 * s)
        groove([L(sh, el, 0.08, 175), L(sh, el, 0.25, 145), L(sh, el, 0.42, 100)], 0.016 * s, 0.005 * s)
    elif g == "upper_arms":
        for t, th, a, b, h in ((0.58, 0, 0.10, 0.035, 0.013), (0.45, 180, 0.12, 0.04, 0.012),
                               (0.35, -150, 0.07, 0.03, 0.008)):
            p, n, ax = L(sh, el, t, th)
            pad((p, n), ax, a * s, b * s, h * s)
        # biceps from triceps on the outside and the inside of the arm
        groove([L(sh, el, 0.45, 80), L(sh, el, 0.95, 95)], 0.016 * s, 0.006 * s)
        groove([L(sh, el, 0.35, -80), L(sh, el, 0.9, -95)], 0.016 * s, 0.005 * s)
    elif g == "pectorals":
        tilt = _unit([np.cos(np.radians(18)), 0.0, np.sin(np.radians(18))])
        pad(T(0.07, 1.22), tilt, 0.075 * s, 0.055 * s, 0.008 * s)
        pad(T(0.06, 1.30), X, 0.05 * s, 0.028 * s, 0.004 * s)
        pad(T(0.125, 1.245), tilt, 0.04 * s, 0.04 * s, 0.006 * s)
        # the sternum between them: a soft valley, fading out at both ends
        groove([T(0.0, 1.335), T(0.0, 1.25), T(0.0, 1.165)], 0.018 * s, 0.003 * s, taper=0.3)
        # the lower border: a crease under the slab; the groove between it and the deltoid
        groove([T(0.02, 1.162), T(0.08, 1.172), T(0.14, 1.20)], 0.012 * s, 0.003 * s)
        groove([T(0.115, 1.335), T(0.155, 1.255)], 0.01 * s, 0.002 * s)
    elif g == "abdominals":
        for z, b, h in ((1.140, 0.026, 0.009), (1.080, 0.026, 0.009), (1.022, 0.025, 0.008), (0.945, 0.045, 0.006)):
            pad(T(0.037, z), X, 0.034 * s, b * s, h * s)
        # the linea alba: a soft valley from the sternum, ending above the navel
        groove([T(0.0, 1.175), T(0.0, 1.08), T(0.0, 1.005)], 0.016 * s, 0.003 * s, taper=0.3)
        for z in (1.111, 1.051):                                  # tendinous intersections
            groove([T(0.005, z), T(0.04, z + 0.002), T(0.075, z + 0.004)], 0.008 * s, 0.003 * s, taper=0.2)
    elif g == "obliques":
        pad(T(0.0, 0.985, theta=62), Z, 0.06 * s, 0.035 * s, 0.005 * s)
        for i, z in enumerate((1.205, 1.170, 1.135)):
            pad(T(0.0, z, theta=68 - 4 * i), _unit([0.0, -0.5, -1.0]), 0.03 * s, 0.012 * s, 0.003 * s)
        groove([T(0.0, 0.955, theta=48), T(0.045, 0.875)], 0.012 * s, 0.003 * s)
    elif g == "quadriceps":
        for t, th, a, b, h in ((0.60, 65, 0.14, 0.045, 0.012),    # vastus lateralis
                               (0.42, 5, 0.16, 0.032, 0.011),     # rectus femoris
                               (0.80, -40, 0.065, 0.045, 0.018)): # vastus medialis: the teardrop
            p, n, ax = L(hip, kn, t, th)
            pad((p, n), ax, a * s, b * s, h * s)
        # rectus femoris from vastus lateralis; the sartorius line down the inside to the knee;
        # the teardrop's upper edge; the iliotibial band on the outside
        groove([L(hip, kn, 0.25, 38), L(hip, kn, 0.55, 40), L(hip, kn, 0.85, 30)], 0.02 * s, 0.007 * s)
        groove([L(hip, kn, 0.12, -10), L(hip, kn, 0.45, -45), L(hip, kn, 0.72, -75), L(hip, kn, 0.95, -100)],
               0.02 * s, 0.007 * s)
        groove([L(hip, kn, 0.30, 115), L(hip, kn, 0.65, 115), L(hip, kn, 0.92, 105)], 0.018 * s, 0.005 * s)
        groove([L(hip, kn, 0.92, -20), L(hip, kn, 0.95, 20)], 0.016 * s, 0.005 * s, taper=0.3)  # above the patella
    elif g == "calves":
        for t, th, a, b, h in ((0.28, -150, 0.10, 0.045, 0.018),   # gastrocnemius, medial head (lower)
                               (0.24, 150, 0.085, 0.038, 0.015),   # lateral head
                               (0.55, 115, 0.09, 0.025, 0.006),    # soleus showing on the outside
                               (0.35, 40, 0.11, 0.022, 0.007)):    # tibialis anterior
            p, n, ax = L(kn, an, t, th)
            pad((p, n), ax, a * s, b * s, h * s)
        # between the heads, and where they end on the Achilles tendon (the lower border of the diamond)
        groove([L(kn, an, 0.08, 180), L(kn, an, 0.25, 180), L(kn, an, 0.42, 180)], 0.016 * s, 0.006 * s)
        groove([L(kn, an, 0.36, 110), L(kn, an, 0.47, 150), L(kn, an, 0.53, 180), L(kn, an, 0.47, -150),
                L(kn, an, 0.40, -105)], 0.02 * s, 0.007 * s, taper=0.15)
        groove([L(kn, an, 0.15, 20), L(kn, an, 0.55, 15)], 0.014 * s, 0.004 * s)   # shin bone beside the tibialis
    elif g == "forearms":
        for t, th, a, b, h in ((0.22, 60, 0.09, 0.032, 0.012),    # brachioradialis and wrist extensors
                               (0.28, 130, 0.09, 0.03, 0.009),
                               (0.26, -60, 0.09, 0.034, 0.011)):  # wrist flexors
            p, n, ax = L(el, wr, t, th)
            pad((p, n), ax, a * s, b * s, h * s)
        groove([L(el, wr, 0.1, 0), L(el, wr, 0.45, 5), L(el, wr, 0.75, 10)], 0.016 * s, 0.006 * s)
        groove([L(el, wr, 0.15, 180), L(el, wr, 0.55, 175)], 0.014 * s, 0.004 * s)
    else:
        raise ValueError(f"unknown group {g!r}")
    return pads, grooves


HEIGHT_GAIN = 1.6          # every sculpted pad's and groove's height, as judged on Dante's renders
# the limbs are seen from further off and their muscles lie under a rounder surface: judged on renders at
# full-body scale, their forms need more height than the trunk's to read
GROUP_GAIN = {"quadriceps": 1.5, "calves": 1.4, "forearms": 1.4, "upper_arms": 1.2}
RELIEF_GAIN = 1.5
RELIEF_MIDLINE = (0.02, 0.05)   # |x| (m, reference scale): relief gone on the front midline inside, whole outside
RELIEF_SMOOTH = 6          # Laplacian iterations taken off MPFB's muscle shape: what is left is its relief
RELIEF_EXCLUDE = ("genitals", "nipple", "nippleTip", "fingernails", "toenails", "ears", "lips", "scalp")
ALIGN = (0.25, 0.6)        # skin normal . pad normal: no height below the first, full above the second
ALIGN_OFFSET = 0.03        # metres added to a pad's distance where the skin faces away from it
GROOVE_SLOPE = 0.3         # a groove sinks at most this share of its own radius: hm08's ~15 mm edges
                           # cannot carry a narrower, deeper cut without one vertex dropping alone
SPIKE_LIMIT = 0.004        # m a vertex may stand off its neighbours' mean before `despike` pulls it back
PAD_BLEND = 0.008          # smooth union radius between a group's pads (m)
MIDLINE_SOFT = 0.015       # a pad reaching the midline meets its mirror in a valley this wide, not a crease
BULK_FEATHER = 0.35        # bulk fades in over this share of the shoulder joint's half-width off the trunk


def _muscle_shape(ob, faces):
    """How far each body vertex of `ob` moves along its normal from MPFB muscle 0.5 to 1.0, and the body's
    positions and joints at 0.5."""
    from . import scaffold
    _, TS, HOP, _ = scaffold.services()
    was = HOP.get_value("muscle", entity_reference=ob)
    try:
        HOP.set_value("muscle", 0.5, entity_reference=ob)
        TS.reapply_macro_details(ob)
        co0 = delta.mixed_coords(ob)
        HOP.set_value("muscle", 1.0, entity_reference=ob)
        TS.reapply_macro_details(ob)
        co1 = delta.mixed_coords(ob)
    finally:
        HOP.set_value("muscle", was, entity_reference=ob)
        TS.reapply_macro_details(ob)
    n0 = delta.vertex_normals(co0, faces)
    return np.einsum("ij,ij->i", (co1 - co0)[:delta.BODY_VERTS], n0), co0, _joints(ob, co0)


def _keep(ob, faces, p, j, s):
    """1 on the body, 0 on the head above the neck joint, the hands, the feet and MPFB's excluded groups."""
    keep = 1.0 - np.clip((p[:, 2] - j["joint-neck"][2]) / (0.06 * s), 0.0, 1.0)
    keep *= np.clip((p[:, 2] - j["joint-l-ankle"][2]) / (0.04 * s), 0.0, 1.0)
    for side in (1.0, -1.0):
        el, wr = j["joint-l-elbow"].copy(), j["joint-l-hand"].copy()
        el[0] *= side
        wr[0] *= side
        ax = _unit(wr - el)
        past = (p - wr) @ ax
        keep *= np.where(np.sign(p[:, 0]) == side, 1.0 - np.clip((past + 0.02 * s) / (0.03 * s), 0.0, 1.0), 1.0)
    idx = {g.index for g in ob.vertex_groups if g.name in RELIEF_EXCLUDE}
    if idx:
        out = np.zeros(delta.BODY_VERTS, bool)
        for v in ob.data.vertices[:delta.BODY_VERTS]:
            if any(g.group in idx and g.weight > 0.1 for g in v.groups):
                out[v.index] = True
        keep = np.minimum(keep, delta.smooth((~out).astype(np.float64), faces, iterations=2))
    return keep


def _scale(j):
    return float((j["joint-neck"][2] - j["joint-pelvis"][2]) / (REF["neck_z"] - REF["pelvis_z"]))


def relief(ob, faces=None, shape=None):
    """The relief of MPFB's own muscle sculpt, as heights on `ob` (an MPFB human, normally the reference):
    how far each vertex moves along its normal from muscle 0.5 to 1.0, less that movement smoothed over
    RELIEF_SMOOTH iterations - the growth of the whole body taken out, the separations between muscles
    (the back, the arms, the serratus, the neck) left. Zero on the head above the neck joint, the hands
    past the wrists, the feet below the ankles and MPFB's genital, nipple, nail, ear, lip and scalp groups."""
    faces = delta.body_faces(ob) if faces is None else faces
    d, co0, j = shape or _muscle_shape(ob, faces)
    hp = d - delta.smooth(d, faces, iterations=RELIEF_SMOOTH, share=0.5)
    p = co0[:delta.BODY_VERTS]
    s = _scale(j)
    # MPFB's sculpt has a midline crease down the sternum and the linea alba into the navel; high-passed and
    # amplified it reads as a knife cut, so it is taken out on the front of the trunk (the pectorals' and
    # abdominals' own soft grooves stand in for it)
    n0 = delta.vertex_normals(co0, faces)
    mid = 1.0 - np.clip((np.abs(p[:, 0]) - RELIEF_MIDLINE[0] * s) / ((RELIEF_MIDLINE[1] - RELIEF_MIDLINE[0]) * s), 0, 1)
    mid *= np.clip((-n0[:, 1] - 0.2) / 0.3, 0.0, 1.0)
    mid *= np.clip((p[:, 2] - (j["joint-pelvis"][2] - 0.08 * s)) / (0.04 * s), 0.0, 1.0)
    return hp * _keep(ob, faces, p, j, s) * (1.0 - mid) * RELIEF_GAIN


def bulk(ob, faces=None, shape=None):
    """The mass of MPFB's muscle sculpt on the limbs and shoulders: the same movement from muscle 0.5 to 1.0,
    smoothed (the part `relief` leaves out), zero on the trunk inside the shoulders and above the hips -
    whose girths the fit reached - feathered over BULK_FEATHER of the shoulder joint's half-width. Weighted
    by how far the fit left the macro under the brief's muscle (`weights`), it gives back the arms,
    shoulders and legs the fit traded for the trunk's girths. Not definition: fat does not hide it."""
    faces = delta.body_faces(ob) if faces is None else faces
    d, co0, j = shape or _muscle_shape(ob, faces)
    lo = delta.smooth(d, faces, iterations=RELIEF_SMOOTH, share=0.5)
    p = co0[:delta.BODY_VERTS]
    s = _scale(j)
    sx = j["joint-l-shoulder"][0]
    inside_x = 1.0 - np.clip((np.abs(p[:, 0]) - (1.0 - BULK_FEATHER) * sx) / (BULK_FEATHER * sx), 0.0, 1.0)
    pz, nz = j["joint-pelvis"][2], j["joint-neck"][2]
    trunk_z = np.clip((p[:, 2] - (pz - 0.10 * s)) / (0.10 * s), 0.0, 1.0)
    trunk_z *= 1.0 - np.clip((p[:, 2] - (nz - 0.14 * s)) / (0.08 * s), 0.0, 1.0)
    return lo * _keep(ob, faces, p, j, s) * (1.0 - inside_x * trunk_z)


def _groove_depth(pts, line, r, depth, taper):
    """How far a groove along polyline `line` (mirrored to the right side) sinks each point: `depth` on the
    line, smoothly 0 at `r` from it, and along its length smoothly 0 at both ends over `taper` of it."""
    out = np.zeros(len(pts))
    lo, hi = line.min(axis=0) - r, line.max(axis=0) + r
    q = pts.copy()
    q[:, 0] = np.abs(q[:, 0])
    idx = np.nonzero(np.all((q >= lo) & (q <= hi), axis=1))[0]
    if not len(idx):
        return out
    q = q[idx]
    seg = np.diff(line, axis=0)
    seg_len = np.linalg.norm(seg, axis=1)
    start = np.concatenate([[0.0], np.cumsum(seg_len)])
    total = max(start[-1], 1e-9)
    best = np.full(len(q), np.inf)
    along = np.zeros(len(q))
    for i, (a0, v, ln) in enumerate(zip(line[:-1], seg, seg_len)):
        t = np.clip((q - a0) @ v / max(ln * ln, 1e-12), 0.0, 1.0)
        dist = np.linalg.norm(q - (a0 + t[:, None] * v), axis=1)
        closer = dist < best
        best[closer] = dist[closer]
        along[closer] = (start[i] + t[closer] * ln) / total
    inside = np.clip(1.0 - best / r, 0.0, 1.0)
    w = inside * inside * (3 - 2 * inside)
    if taper > 0:
        e = np.clip(np.minimum(along, 1.0 - along) / taper, 0.0, 1.0)
        w *= e * e * (3 - 2 * e)
    out[idx] = depth * w
    return out


def author(ob, groups=GROUPS, smooth_iterations=1):
    """Per-group heights (metres, (BODY_VERTS,)) sculpted on body `ob` (normally `reference_body()`).
    Deterministic: the same body gives the same heights."""
    co = delta.mixed_coords(ob)
    faces = delta.body_faces(ob)
    nrm = delta.vertex_normals(co, faces)
    joints = _joints(ob, co)
    sk = _Skin(co, faces, joints)
    pts = co[:delta.BODY_VERTS]
    out = {}
    shape = _muscle_shape(ob, faces) if {"relief", "bulk"} & set(groups) else None
    for g in groups:
        if g in ("relief", "bulk"):
            out[g] = despike((relief if g == "relief" else bulk)(ob, faces, shape), faces)
            continue
        pads, grooves = _author_group(sk, g)
        d = np.full(len(pts), sdf.FAR)
        for prim, pn, ph in pads:
            fn, (lo, hi) = sdf.mirrored_x(prim, soft=MIDLINE_SOFT)
            m = np.all((pts >= lo - sdf.MARGIN) & (pts <= hi + sdf.MARGIN), axis=1)
            idx = np.nonzero(m)[0]
            if not len(idx):
                continue
            pn_m = np.tile(pn, (len(idx), 1))
            pn_m[:, 0] *= np.sign(pts[idx, 0] + 1e-9)          # the mirrored pad's normal on the right
            align = np.clip((np.einsum("ij,ij->i", nrm[idx], pn_m) - ALIGN[0]) / (ALIGN[1] - ALIGN[0]), 0, 1)
            # trimmed to the belly's height with a rounded shoulder
            dp = sdf.smax(fn(pts[idx]), np.full(len(idx), -ph), 0.6 * ph) + (1.0 - align) * ALIGN_OFFSET
            d[idx] = sdf.smin(d[idx], dp, PAD_BLEND)
        h = np.maximum(-d, 0.0)
        for line, r, depth, taper in grooves:
            h -= _groove_depth(pts, line, r, depth, taper)
        if smooth_iterations:
            h = delta.smooth(h, faces, iterations=smooth_iterations)
        out[g] = despike(h, faces)
    return out


def spikes(h, faces, adjacency=None):
    """How far each height stands off the mean of its neighbours: a form reads as a form, a single
    vertex standing off its neighbours reads as a bright facet stuck through the skin."""
    r, c = adjacency or delta.neighbours(faces)
    deg = np.maximum(np.bincount(r, minlength=delta.BODY_VERTS).astype(np.float64), 1)
    return np.asarray(h, np.float64) - np.bincount(r, weights=np.asarray(h, np.float64)[c],
                                                   minlength=delta.BODY_VERTS) / deg


def despike(h, faces, limit=None, passes=6):
    """Pull back any vertex standing more than `limit` (SPIKE_LIMIT) off its neighbours' mean, leaving
    the rest as sculpted. Forms are many vertices wide, so this takes off facets and not muscles. Each
    pass moves the neighbours' means too, so it converges rather than lands: six passes leave about
    1% over the limit."""
    limit = SPIKE_LIMIT if limit is None else limit
    h = np.asarray(h, np.float64).copy()
    adjacency = delta.neighbours(faces)
    for _ in range(passes):
        d = spikes(h, faces, adjacency)
        over = np.abs(d) > limit
        if not over.any():
            break
        h[over] -= np.sign(d[over]) * (np.abs(d[over]) - limit)
    return h


def seed(store=True, name=NAME):
    """Author the set on MPFB's default male and (by default) store it in the library as a delta part.
    Returns the card. The reference body is removed afterwards."""
    import bpy
    ref = reference_body()
    try:
        co = delta.mixed_coords(ref)
        groups = author(ref)
        reference = {"body": "mpfb2 default male", "stature_m": round(delta.stature_of(co), 4)}
    finally:
        bpy.data.objects.remove(ref, do_unlink=True)
    notes = "authored by humanform.muscle.author on MPFB's default male with SDF pads and grooves"
    if not store:
        return {"kind": "part", "region": REGION, "name": name, "id": None,
                "payload": {"type": "delta", "frame": "normal", "unit": "um", "reference": reference,
                            "groups": {g: delta.pack(h) for g, h in sorted(groups.items())}}}
    return delta.store(REGION, name, groups, reference, tags=["muscle definition"] + list(GROUPS), notes=notes)


def find(name=NAME):
    """The stored set called `name`, or None."""
    for c in library.find_parts(REGION):
        if c.get("name") == name:
            return library.load(c["id"])
    return None


def define(human, brief, card=None, geometry=True, strength=1.0, weights_override=None):
    """Put muscle definition on an unbaked humanform body for its brief: the stored set (authored and
    stored on first use), weighted per group by `weights`. Two shape keys:

    - `hfd:muscle` - the definition groups - at 1 with `geometry`, at 0 without (bake it into a normal map
      from `delta.high_copy(human, "hfd:muscle")`);
    - `hfd:muscle-bulk` - the limbs' and shoulders' mass the fit left under the brief's muscle - always at 1:
      it is silhouette, which a normal map cannot carry.
    """
    from . import scaffold
    _, _, HOP, _ = scaffold.services()
    card = card or find() or seed(store=True)
    fitted = float(HOP.get_value("muscle", entity_reference=human))
    w = weights(brief, strength=strength, fitted_muscle=fitted)
    if weights_override:
        w["weights"].update(weights_override)
    groups = card["payload"]["groups"]
    wd = {g: v for g, v in w["weights"].items() if g != "bulk"}
    applied = delta.apply(human, card, weights=wd, mode="key", value=1.0 if geometry else 0.0)
    applied_bulk = None
    if "bulk" in groups:
        applied_bulk = delta.apply(human, card, weights={"bulk": w["weights"]["bulk"]}, mode="key", value=1.0,
                                   key_name=delta.KEY_PREFIX + REGION + "-bulk")
    return dict(w, fitted_muscle=round(fitted, 4), applied=applied, applied_bulk=applied_bulk,
                geometry=bool(geometry), card=card.get("id"))
