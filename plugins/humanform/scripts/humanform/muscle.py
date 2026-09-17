"""L3-L4 muscle definition: sculpted delta parts, scaled by how muscular and how lean the brief is.

MPFB's mesh is smooth, so its muscle macro makes a body bigger, not defined: a muscular man reads as
average. Definition here is a `delta` part - per-vertex heights along the normal, in groups - authored
once with signed distance sculpting on MPFB's default male and put on any MPFB body:

    rep = muscle.define(human, brief)                     # after pipeline.make, before bake_for_game
    rep["weights"]        # per group, 0..1: muscle term x leanness for that group
    rep["body_fat_pct"]   # the estimate the leanness came from
    rep["applied"]        # delta.apply's report (key hfd:muscle, max heights in mm per group)

    rep = muscle.define(human, brief, geometry=False)     # key at 0: definition only in a normal map
    high = delta.high_copy(human, "hfd:muscle")           # ...baked by lookdev's detail.bake_normal_from_high

The sculpted groups: deltoids, pectorals, abdominals, obliques (with serratus and the inguinal line),
quadriceps, calves, forearms. A last group, `relief`, is not sculpted: it is MPFB's own muscle shape
(muscle 1.0 against 0.5) high-passed, which gives the back, arms and neck the definition the seven do not
reach (see `relief`). Each is a set of pads (ellipsoids whose outer surface stands `height` proud of the
skin at an anchor found by casting a ray from inside a limb or the torso) smoothly unioned, minus cuts
(the linea alba, the sternum) and grooves (the inguinal line, between the calf heads). A vertex's height
is how deep it lies inside the group's field, masked to skin that faces the way its pad does - so a pad
on the chest does not raise the inside of the arm beside it.

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
NAME = "definition-v1"
SCULPTED = ("deltoids", "pectorals", "abdominals", "obliques", "quadriceps", "calves", "forearms")
GROUPS = SCULPTED + ("relief",)

# body fat % (male) at which a group is fully visible, and at which it is gone
VISIBLE = {"abdominals": (12.0, 22.0), "obliques": (12.0, 22.0), "pectorals": (13.0, 25.0),
           "quadriceps": (13.0, 25.0), "deltoids": (14.0, 28.0), "calves": (15.0, 30.0), "forearms": (15.0, 30.0),
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


def weights(brief=None, sex=None, bmi=None, age=None, muscle=None, firmness=None, strength=1.0):
    """Per-group definition weights for a brief (or the numbers directly). Returns
    {"weights", "muscle_term", "body_fat_pct", "leanness", "inputs"}."""
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
    for g in GROUPS:
        full, gone = VISIBLE[g]
        lean[g] = 1.0 - _smoothstep(full + off, gone + off, fat)
        share = FEMALE_GROUP.get(g, 1.0) if x["sex"] == "female" else 1.0
        w[g] = round(float(strength) * m * lean[g] * share, 4)
    return {"weights": w, "muscle_term": round(m, 4), "body_fat_pct": round(fat, 2),
            "leanness": {g: round(v, 4) for g, v in lean.items()}, "inputs": x}


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
    """(pads [(prim, normal)], cuts [prim], grooves [(prim, radius, depth)]) for group g, left side."""
    L = sk.limb
    pads, cuts, grooves = [], [], []

    def pad(anchor, u, a, b, h):
        p, n = anchor[0], anchor[1]
        pads.append(_pad(p, n, u, a, b, h * HEIGHT_GAIN))

    def groove(pa, pb, r, depth):
        grooves.append((sdf.capsule(pa, pb, r), r, depth * HEIGHT_GAIN))

    Z = np.array([0.0, 0.0, 1.0])
    X = np.array([1.0, 0.0, 0.0])
    sh, el, wr = "joint-l-shoulder", "joint-l-elbow", "joint-l-hand"
    hip, kn, an = "joint-l-upper-leg", "joint-l-knee", "joint-l-ankle"
    s = sk.scale()
    zc = lambda z: z  # noqa: E731  (torso heights are mapped inside _Skin.torso)
    if g == "deltoids":
        for t, th, a, b, h in ((0.22, 90, 0.075, 0.045, 0.008), (0.12, 30, 0.06, 0.035, 0.007),
                               (0.15, 150, 0.06, 0.035, 0.006), (-0.02, 80, 0.045, 0.045, 0.005)):
            p, n, ax = L(sh, el, t, th)
            pad((p, n), ax, a * s, b * s, h * s)
    elif g == "pectorals":
        tilt = _unit([np.cos(np.radians(18)), 0.0, np.sin(np.radians(18))])
        pad(sk.torso(0.07, zc(1.22)), tilt, 0.075 * s, 0.055 * s, 0.008 * s)
        pad(sk.torso(0.06, zc(1.30)), X, 0.05 * s, 0.028 * s, 0.004 * s)
        pad(sk.torso(0.125, zc(1.245)), tilt, 0.04 * s, 0.04 * s, 0.006 * s)
        a, b = sk.torso(0.0, zc(1.16))[0], sk.torso(0.0, zc(1.34))[0]
        cuts.append(sdf.capsule(a, b, 0.007 * s))
        # the lower border: a crease under the slab; the groove between it and the deltoid
        groove(sk.torso(0.02, zc(1.162))[0], sk.torso(0.14, zc(1.20))[0], 0.012 * s, 0.003 * s)
        groove(sk.torso(0.115, zc(1.335))[0], sk.torso(0.155, zc(1.255))[0], 0.01 * s, 0.002 * s)
    elif g == "abdominals":
        for z, b, h in ((1.140, 0.026, 0.009), (1.080, 0.026, 0.009), (1.022, 0.025, 0.008), (0.945, 0.045, 0.006)):
            pad(sk.torso(0.037, zc(z)), X, 0.034 * s, b * s, h * s)
        a, b = sk.torso(0.0, zc(1.17))[0], sk.torso(0.0, zc(0.90))[0]
        cuts.append(sdf.capsule(a, b, 0.006 * s))
        groove(a, b, 0.008 * s, 0.002 * s)                       # the linea alba
        for z in (1.111, 1.051):                                  # tendinous intersections
            groove(sk.torso(0.0, zc(z))[0], sk.torso(0.075, zc(z + 0.004))[0], 0.008 * s, 0.003 * s)
    elif g == "obliques":
        pad(sk.torso(0.0, zc(0.985), theta=62), Z, 0.06 * s, 0.035 * s, 0.005 * s)
        for i, z in enumerate((1.205, 1.170, 1.135)):
            pad(sk.torso(0.0, zc(z), theta=68 - 4 * i), _unit([0.0, -0.5, -1.0]), 0.03 * s, 0.012 * s, 0.003 * s)
        groove(sk.torso(0.0, zc(0.955), theta=48)[0], sk.torso(0.045, zc(0.875))[0], 0.012 * s, 0.003 * s)
    elif g == "quadriceps":
        for t, th, a, b, h in ((0.55, 75, 0.13, 0.045, 0.006), (0.45, 5, 0.15, 0.035, 0.005),
                               (0.82, -45, 0.055, 0.038, 0.007)):
            p, n, ax = L(hip, kn, t, th)
            pad((p, n), ax, a * s, b * s, h * s)
        groove(L(hip, kn, 0.2, -20)[0], L(hip, kn, 0.85, -95)[0], 0.01 * s, 0.002 * s)
    elif g == "calves":
        for t, th, a, b, h in ((0.30, -150, 0.11, 0.04, 0.008), (0.27, 145, 0.09, 0.032, 0.006),
                               (0.52, 110, 0.09, 0.025, 0.003), (0.35, 35, 0.11, 0.02, 0.003)):
            p, n, ax = L(kn, an, t, th)
            pad((p, n), ax, a * s, b * s, h * s)
        groove(L(kn, an, 0.12, 180)[0], L(kn, an, 0.45, 180)[0], 0.008 * s, 0.002 * s)
    elif g == "forearms":
        for t, th, a, b, h in ((0.25, 60, 0.09, 0.028, 0.005), (0.30, 130, 0.09, 0.028, 0.004),
                               (0.30, -60, 0.09, 0.03, 0.004)):
            p, n, ax = L(el, wr, t, th)
            pad((p, n), ax, a * s, b * s, h * s)
    else:
        raise ValueError(f"unknown group {g!r}")
    return pads, cuts, grooves


HEIGHT_GAIN = 1.6          # every sculpted pad's and groove's height, as judged on Dante's renders
RELIEF_GAIN = 1.5
RELIEF_SMOOTH = 6          # Laplacian iterations taken off MPFB's muscle shape: what is left is its relief
RELIEF_EXCLUDE = ("genitals", "nipple", "nippleTip", "fingernails", "toenails", "ears", "lips", "scalp")
ALIGN = (0.25, 0.6)        # skin normal . pad normal: no height below the first, full above the second
PAD_BLEND = 0.008          # smooth union radius between a group's pads (m)
CUT_BLEND = 0.006


def relief(ob, faces=None):
    """The relief of MPFB's own muscle sculpt, as heights on `ob` (an MPFB human, normally the reference):
    how far each vertex moves along its normal from muscle 0.5 to 1.0, less that movement smoothed over
    RELIEF_SMOOTH iterations - the growth of the whole body taken out, the separations between muscles
    (the back, the arms, the serratus, the neck) left. Zero on the head above the neck joint, the hands
    past the wrists, the feet below the ankles and MPFB's genital, nipple, nail, ear, lip and scalp groups."""
    from . import scaffold
    _, TS, HOP, _ = scaffold.services()
    faces = delta.body_faces(ob) if faces is None else faces
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
    d = np.einsum("ij,ij->i", (co1 - co0)[:delta.BODY_VERTS], n0)
    hp = d - delta.smooth(d, faces, iterations=RELIEF_SMOOTH, share=0.5)
    p = co0[:delta.BODY_VERTS]
    j = _joints(ob, co0)
    s = float((j["joint-neck"][2] - j["joint-pelvis"][2]) / (REF["neck_z"] - REF["pelvis_z"]))
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
    return hp * keep * RELIEF_GAIN


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
    for g in groups:
        if g == "relief":
            out[g] = relief(ob, faces)
            continue
        pads, cuts, grooves = _author_group(sk, g)
        d = np.full(len(pts), sdf.FAR)
        for prim, pn, ph in pads:
            fn, (lo, hi) = sdf.mirrored_x(prim)
            m = np.all((pts >= lo - sdf.MARGIN) & (pts <= hi + sdf.MARGIN), axis=1)
            idx = np.nonzero(m)[0]
            if not len(idx):
                continue
            pn_m = np.tile(pn, (len(idx), 1))
            pn_m[:, 0] *= np.sign(pts[idx, 0] + 1e-9)          # the mirrored pad's normal on the right
            align = np.clip((np.einsum("ij,ij->i", nrm[idx], pn_m) - ALIGN[0]) / (ALIGN[1] - ALIGN[0]), 0, 1)
            # trimmed to the belly's height with a rounded shoulder
            dp = sdf.smax(fn(pts[idx]), np.full(len(idx), -ph), 0.6 * ph) + (1.0 - align) * 0.03
            d[idx] = sdf.smin(d[idx], dp, PAD_BLEND)
        for prim in cuts:
            fn, (lo, hi) = sdf.mirrored_x(prim)
            m = np.all((pts >= lo - sdf.MARGIN) & (pts <= hi + sdf.MARGIN), axis=1)
            idx = np.nonzero(m)[0]
            if len(idx):
                d[idx] = sdf.smax(d[idx], -fn(pts[idx]), CUT_BLEND)
        h = np.maximum(-d, 0.0)
        for prim, r, depth in grooves:
            fn, (lo, hi) = sdf.mirrored_x(prim)
            m = np.all((pts >= lo - sdf.MARGIN) & (pts <= hi + sdf.MARGIN), axis=1)
            idx = np.nonzero(m)[0]
            if len(idx):
                inside = np.clip(-fn(pts[idx]) / r, 0.0, 1.0)
                h[idx] -= depth * inside * inside * (3 - 2 * inside)
        if smooth_iterations:
            h = delta.smooth(h, faces, iterations=smooth_iterations)
        out[g] = h
    return out


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
    notes = "authored by humanform.muscle.author on MPFB's default male with SDF pads, cuts and grooves"
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
    stored on first use), weighted per group by `weights`, as shape key `hfd:muscle` - at 1 with
    `geometry`, at 0 without (bake it into a normal map from `delta.high_copy`)."""
    card = card or find() or seed(store=True)
    w = weights(brief, strength=strength)
    if weights_override:
        w["weights"].update(weights_override)
    applied = delta.apply(human, card, weights=w["weights"], mode="key", value=1.0 if geometry else 0.0)
    return dict(w, applied=applied, geometry=bool(geometry), card=card.get("id"))
