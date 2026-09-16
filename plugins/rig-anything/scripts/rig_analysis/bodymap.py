"""One body description for any rig: spine, neck, head, tail and limbs.

Four naming schemes already live in this project - a hand-built humanoid
(`Thigh.L`, `UpperArm.L`, `Hips/Spine/Chest/Neck/Head`), the Rigify human and
quadruped fitters (`thigh.L`, `front_thigh.L`, `spine.00N`) and the generic
builder (`leg1_upper.L`, `arm1_lower.R`). An action written against any one of
them is useless on the other three. So nothing downstream reads bone names;
it reads this map.

The map is built from STRUCTURE, with names only as tie-breakers:

- A limb is a chain of sided bones (`.L`/`.R`) hanging off an unsided one. Its
  first bone is a girdle when it is called a shoulder, clavicle or pelvis;
  the next two are the upper and lower segments, the one after is the end
  (foot or hand), and anything further is digits.
- Grounded is a leg, free is an arm - the same rule `decompose` uses. Names
  do not decide it, so a quadruped's front legs are legs here even though a
  Rigify quadruped calls them `front_thigh`.
- The axial chain is the unsided path from one end of the body to the other.
  Which end is the head is settled by a bone called head, else by height on an
  upright body and by the forward axis on a horizontal one. The HIERARCHY
  direction is not trusted: the generic builder roots a biped's spine at the
  top of the neck, and a map that assumed the root was the pelvis would bend
  that creature inside out.
- The neck is whatever axial bone lies between the head and the nearest limb
  attachment. The generic builder joins the head straight onto the torso, so
  on those rigs the neck is empty - reported as such rather than invented.
"""

from __future__ import annotations

import re

import bpy
from mathutils import Vector

AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}

_SUFFIX = re.compile(r"^(?P<base>.+)[._\-](?P<side>L|R|l|r|Left|Right|left|right)$")
_PREFIX = re.compile(r"^(?P<side>Left|Right)(?P<base>[A-Z_].*)$")
_GIRDLE = re.compile(r"shoulder|clavicle|collar|scapula|pelvis", re.I)
_OFFSHOOT = re.compile(r"heel|palm|breast|twist|pole|ik", re.I)
_HEAD = re.compile(r"head|skull", re.I)
_NECK = re.compile(r"neck", re.I)
_TAIL = re.compile(r"tail", re.I)


def side_of(name):
    """("L" | "R" | None, base name)."""
    short = name.split(":")[-1]
    m = _SUFFIX.match(short)
    if m:
        return m.group("side")[0].upper(), m.group("base")
    m = _PREFIX.match(short)
    if m:
        return m.group("side")[0].upper(), m.group("base")
    return None, short


def axis_vector(spec):
    """"-Y" -> Vector((0, -1, 0))."""
    v = Vector((0.0, 0.0, 0.0))
    v[AXIS_INDEX[spec[-1].upper()]] = -1.0 if spec.startswith("-") else 1.0
    return v


def _depth(bone):
    d = 0
    while bone.parent is not None:
        bone = bone.parent
        d += 1
    return d


def _subtree_len(bone, side):
    kids = [c for c in bone.children if side_of(c.name)[0] == side]
    return 1 + max((_subtree_len(c, side) for c in kids), default=0)


def _descendants_names(bone, side):
    out = [bone.name]
    for c in bone.children:
        if side_of(c.name)[0] == side:
            out.extend(_descendants_names(c, side))
    return out


def bound_meshes(rig):
    """The mesh objects an Armature modifier binds to `rig`."""
    return [o for o in bpy.data.objects if o.type == "MESH"
            and any(m.type == "ARMATURE" and m.object == rig for m in o.modifiers)]


def skinned_bone_names(rig, meshes=None):
    """Names of `rig`'s bones that carry any skin weight on `meshes` (default: the meshes bound
    to it), or None when there is no mesh to read."""
    if meshes is None:
        meshes = bound_meshes(rig)
    else:
        meshes = [bpy.data.objects[m] if isinstance(m, str) else m for m in meshes]
        meshes = [m for m in meshes if m is not None and m.type == "MESH"]
    if not meshes:
        return None
    bone_names = set(rig.data.bones.keys())
    out = set()
    for m in meshes:
        groups = {g.index: g.name for g in m.vertex_groups if g.name in bone_names}
        if not groups:
            continue
        for v in m.data.vertices:
            for g in v.groups:
                if g.weight > 1e-4 and g.group in groups:
                    out.add(groups[g.group])
    return out


def _roles(rig, limbs, axial_names, pelvis_idx, legs, neck, head_idx, head_guessed, tail_axial,
           height, meshes, excluded):
    """Bones named by what they do, so no consumer re-derives them. See `build`'s `roles`."""
    warnings = []
    skinned = skinned_bone_names(rig, meshes)
    bones = [b for b in rig.data.bones if b.name not in excluded]

    # limbs by role and rank: a quadruped's front feet are `front_foot.L`, a biped's `foot.L`
    out_limbs = {}
    for role, end_word in (("leg", "foot"), ("arm", "hand")):
        group = [l for l in limbs if l["role"] == role]
        attach = sorted({l["axial_index"] for l in group if l["axial_index"] is not None},
                        reverse=True)                                     # head end first
        ranks = {1: [""], 2: ["front_", "hind_"], 3: ["front_", "mid_", "hind_"]}.get(len(attach))
        for l in group:
            if ranks is None or l["axial_index"] is None:
                rank = "rank%d_" % (attach.index(l["axial_index"]) if l["axial_index"] in attach else 0)
            else:
                rank = ranks[attach.index(l["axial_index"])]
            key = "%s%s.%s" % (rank, end_word, l["side"])
            if key in out_limbs:
                warnings.append("two %s limbs claim %s: %s and %s"
                                % (role, key, out_limbs[key]["upper"], l["upper"]))
                continue
            out_limbs[key] = {"role": role, "girdle": l["girdle"], "upper": l["upper"],
                              "lower": l["lower"], "end": l["end"], "digits": list(l["digits"])}

    pelvis = axial_names[pelvis_idx] if legs and 0 <= pelvis_idx < len(axial_names) else None
    arm_attach = [l["axial_index"] for l in limbs if l["role"] == "arm" and l["axial_index"] is not None]
    leg_attach = sorted({l["axial_index"] for l in legs})
    if arm_attach:
        chest = axial_names[max(arm_attach)]
    elif len(leg_attach) > 1:                     # a quadruped's shoulders carry its front legs
        chest = axial_names[leg_attach[-1]]
    else:
        chest = None
    head = axial_names[head_idx] if head_idx is not None else None

    # The root: a motion bone at the rear end of the chain (or parentless and off it), not the
    # pelvis, that moves no skin - or, with no skin to read, lies wholly below the ankles.
    # MPFB's and most game rigs' root lies on the floor under the whole skeleton.
    ankles = min((height(l["rest_eff"]) for l in legs), default=None)
    candidates = []
    if axial_names and (pelvis is None or pelvis_idx > 0):
        candidates.append(axial_names[0])
    candidates += [b.name for b in bones if b.parent is None and not side_of(b.name)[0]
                   and b.name not in axial_names]
    root = None
    for name in candidates:
        b = rig.data.bones[name]
        low = ankles is not None and max(height(b.head_local), height(b.tail_local)) <= ankles
        if name in (pelvis, chest, head):
            continue
        if (skinned is not None and name not in skinned) or (skinned is None and low):
            root = name
            if skinned is None:
                warnings.append("root %s found by height alone (no mesh bound to read skin)" % name)
            break

    limb_bones = set()
    for l in limbs:
        limb_bones.update(n for n in (l["girdle"], l["upper"], l["lower"], l["end"]) if n)
        limb_bones.update(l["digits"])
    unskinned = sorted(b.name for b in bones if skinned is not None and b.name not in skinned)
    axial_set = set(axial_names)
    controls = [n for n in unskinned if n not in limb_bones and (n not in axial_set or n == root)]

    if legs and pelvis is None:
        warnings.append("no pelvis: the legs attach to no axial bone")
    if head is None:
        warnings.append("no head bone")
    elif head_guessed:
        warnings.append("head %s guessed from position (no bone called head)" % head)
    if skinned is not None:
        dead = [n for n in limb_bones if n not in skinned and not side_of(n)[1].lower().startswith(("heel", "palm"))]
        if dead:
            warnings.append("limb bones with no skin: " + ", ".join(sorted(dead)[:6]))

    return {
        "profile": None,
        "root": root,
        "pelvis": pelvis,
        "chest": chest,
        "neck": list(neck),
        "head": head,
        "tail": list(tail_axial),
        "breast_anchor": chest,
        "butt_anchor": pelvis,
        "limbs": out_limbs,
        "skinned": skinned is not None,
        "unskinned": unskinned,
        "controls": controls,
        "warnings": warnings,
    }


def build(rig_name, forward="-Y", up="Z", floor=0.0, meshes=None):
    """Describe a rig's body. Everything positional is in ARMATURE space.

    `forward`/`up` are world axes, as everywhere else in this package. `floor`
    is the world height of the ground. `meshes` are the skin read for `roles`
    (default: every mesh an Armature modifier binds to the rig).

    `roles` names bones by what they do, so nothing downstream re-derives them:
    `root` (a motion bone that moves no skin, or lies under the ankles), `pelvis`
    (where the legs attach), `chest` (where the arms attach; the front legs on a
    quadruped), `neck`, `head`, `tail`, `breast_anchor` and `butt_anchor`,
    `limbs` keyed `foot.L` / `hand.R` / `front_foot.L` with girdle, upper, lower,
    end and digits, `unskinned` bones and `controls` (unskinned and on no limb
    chain), and whether skin was read at all. Roles are derived here once; a
    disagreement is a warning in `roles["warnings"]`, never a silent guess.
    """
    rig = bpy.data.objects.get(rig_name)
    if rig is None or rig.type != "ARMATURE":
        return {"error": "no armature named " + repr(rig_name)}

    mw = rig.matrix_world
    to_arm = mw.to_3x3().inverted()
    fwd = (to_arm @ axis_vector(forward)).normalized()
    upv = (to_arm @ axis_vector(up)).normalized()
    lat = upv.cross(fwd).normalized()
    uidx = AXIS_INDEX[up[-1].upper()]
    usign = -1.0 if up.startswith("-") else 1.0

    def height(p):
        return (mw @ p)[uidx] * usign - floor

    bones = list(rig.data.bones)
    warnings = []

    # A maw's bones - jaw, throat, tongue, mouth socket - hang off the head.
    # Left in, the jaw is the far end of the axial chain and reads as the head,
    # and a sided lip or tongue chain reads as a limb. `maw` poses them.
    from . import maw as maw_mod
    maw_names, fin_names = set(), set()
    for b in bones:
        if b.get(maw_mod.ROLE) or maw_mod.NAME.search(b.name):
            maw_names.add(b.name)
            maw_names.update(c.name for c in b.children_recursive)
        # Fin rays likewise, found by their tag: a name test for fin would take
        # a dragon's finger bones. `fins` poses them.
        if b.get('fin_role'):
            fin_names.add(b.name)
    # A radial body's hub, ribs and arms have no side and no front, and read
    # as one long spine with nothing on it; `radial` poses them. Tentacle chains
    # tagged by `tentacles` likewise belong to that module, not to a limb.
    radial_names = {b.name for b in bones if b.get('radial_role')}
    tentacle_names = {b.name for b in bones if b.get('tentacle')}
    bones = [b for b in bones if b.name not in maw_names and b.name not in fin_names
             and b.name not in radial_names and b.name not in tentacle_names]
    if not bones:
        if radial_names:
            return {"error": "%s is a radial rig - no spine or limbs to map; use "
                             "radial.RadialRig or radial.body_map" % rig_name}
        return {"error": "%s has no bones this map describes" % rig_name}

    # Blender's pose maths only matches the plain FK used by `motion` when
    # bones inherit rotation and scale normally. Say so rather than bake a clip
    # that drifts from its own prediction.
    odd = [b.name for b in bones
           if not b.use_inherit_rotation or b.inherit_scale != "FULL"]
    if odd:
        warnings.append("bones with non-default inheritance, poses may not "
                        "match prediction: " + ", ".join(odd[:5]))

    pts = [p for b in bones for p in (b.head_local, b.tail_local)]
    body_height = max(height(p) for p in pts)
    size = max((max(p[i] for p in pts) - min(p[i] for p in pts)) for i in range(3))

    # ------------------------------------------------------------------ limbs
    limbs, ignored = [], []
    starts = [b for b in bones
              if side_of(b.name)[0] and (b.parent is None or not side_of(b.parent.name)[0])]
    for start in starts:
        side = side_of(start.name)[0]
        chain, cur = [start], start
        while True:
            kids = [c for c in cur.children if side_of(c.name)[0] == side]
            if not kids:
                break
            kids.sort(key=lambda c: (bool(_OFFSHOOT.search(c.name)),
                                     -_subtree_len(c, side)))
            cur = kids[0]
            chain.append(cur)
        girdle = None
        if len(chain) >= 3 and _GIRDLE.search(chain[0].name):
            girdle = chain.pop(0)
        if len(chain) < 2:
            ignored.append(start.name)
            continue
        upper, lower = chain[0], chain[1]
        end = chain[2] if len(chain) > 2 else None
        digits = chain[3:]
        attach = (girdle or upper).parent

        root = upper.head_local.copy()
        mid = lower.head_local.copy()
        eff = end.head_local.copy() if end else lower.tail_local.copy()
        every = [upper, lower] + ([end] if end else []) + digits + ([girdle] if girdle else [])
        lowest = min(min(height(b.head_local), height(b.tail_local)) for b in every)

        limbs.append({
            "name": re.sub(r"_upper$", "", side_of(upper.name)[1]) + "." + side,
            "side": side,
            "girdle": girdle.name if girdle else None,
            "upper": upper.name, "lower": lower.name,
            "end": end.name if end else None,
            "digits": [d.name for d in digits],
            "attach": attach.name if attach else None,
            "a": (mid - root).length,
            "b": (eff - mid).length,
            "rest_root": root, "rest_mid": mid, "rest_eff": eff,
            "lowest": lowest,
            "forward_pos": root.dot(fwd),
        })

    lowest_any = min((l["lowest"] for l in limbs), default=0.0)
    ground_band = max(0.12 * body_height, lowest_any + 0.05 * body_height)
    for l in limbs:
        l["role"] = "leg" if l["lowest"] <= ground_band else "arm"

    # Which way each mid-joint points. Measured from the rest shape when the
    # limb is clearly bent; otherwise a role default, because a dead-straight
    # limb (the hand-built humanoid's knees sit exactly on the hip-ankle line)
    # has no bend to measure and its reading would be decided by noise.
    for l in limbs:
        span = l["rest_eff"] - l["rest_root"]
        t = max(0.0, min(1.0, (l["rest_mid"] - l["rest_root"]).dot(span)
                         / max(span.dot(span), 1e-12)))
        dev = l["rest_mid"] - (l["rest_root"] + span * t)
        rel = dev.length / max(span.length, 1e-9)
        fwd_rel = abs(dev.dot(fwd)) / max(span.length, 1e-9)
        default = fwd.copy() if l["role"] == "leg" else -fwd
        if fwd_rel >= 0.02 or rel >= 0.05:
            l["pole_source"] = "rest shape"
        else:
            l["pole_source"] = "role default (limb near-straight at rest)"
        l["rest_dev"] = dev
        l["rest_pole"] = dev.normalized() if rel > 1e-6 else default
        l["default_pole"] = default
        l["rest_bend_rel"] = rel

    # mirrored pairs should agree - flag, do not silently fix
    by_base = {}
    for l in limbs:
        by_base.setdefault(l["name"].rsplit(".", 1)[0], []).append(l)
    for base, pair in by_base.items():
        if len(pair) == 2 and all(p["pole_source"] == "rest shape" for p in pair):
            a, b = pair[0]["rest_pole"], pair[1]["rest_pole"]
            mirrored = a - lat * (2.0 * a.dot(lat))
            if mirrored.dot(b) < 0.0:
                warnings.append("mirrored limbs %s disagree on bend direction"
                                % base)

    # ------------------------------------------------------------------ wings
    # A free limb whose skin is a sheet - or whose bones are called wing,
    # feather, primary - is a wing: role "wing", so nothing that swings or
    # reaches with arms touches it, and `wings.WingRig` poses it instead.
    unsided = [p for b in bones if not side_of(b.name)[0]
               for p in (b.head_local, b.tail_local)]
    midline = (sum(p.dot(lat) for p in unsided) / len(unsided)) if unsided else 0.0
    wings = []
    if limbs:
        from . import wings as wing_mod
        wings, wing_warnings = wing_mod.detect(
            rig, limbs, fwd, upv, lat, midline, lambda l: l["role"] == "leg")
        warnings.extend(wing_warnings)
    if wings:
        # A creature's size and height are its body's. A dragon's span is 3 m
        # on a 2.3 m body, and every tolerance scaled by size loosened with it.
        wing_bones = set()
        for w in wings:
            wing_bones.update(_descendants_names(rig.data.bones[w["upper"]], w["side"]))
        pts_body = [p for b in bones if b.name not in wing_bones
                    for p in (b.head_local, b.tail_local)]
        if pts_body:
            size = max((max(p[i] for p in pts_body) - min(p[i] for p in pts_body))
                       for i in range(3))
            body_height = max(height(p) for p in pts_body)

    # ------------------------------------------------------------ axial chain
    limb_bones = set()
    for l in limbs:
        limb_bones.update(n for n in (l["girdle"], l["upper"], l["lower"], l["end"]) if n)
        limb_bones.update(l["digits"])
    axial_all = [b for b in bones if not side_of(b.name)[0]]
    names = {b.name for b in axial_all}

    def unsided_neighbours(b):
        out = [c for c in b.children if c.name in names]
        if b.parent is not None and b.parent.name in names:
            out.append(b.parent)
        return out

    ends = [b for b in axial_all if len(unsided_neighbours(b)) <= 1]

    def path_between(a, b):
        # hierarchy is a tree: meet at the lowest common ancestor
        up_a = []
        cur = a
        while cur is not None and cur.name in names:
            up_a.append(cur)
            cur = cur.parent
        idx = {x.name: i for i, x in enumerate(up_a)}
        up_b = []
        cur = b
        while cur is not None and cur.name in names and cur.name not in idx:
            up_b.append(cur)
            cur = cur.parent
        if cur is None or cur.name not in idx:
            return None
        return up_a[:idx[cur.name] + 1] + list(reversed(up_b))

    head_named = [b for b in ends if _HEAD.search(b.name)]
    tail_named = [b for b in ends if _TAIL.search(b.name)]

    axial, head_guessed = [], False
    if len(axial_all) == 1:
        axial = axial_all
    elif ends:
        # longest end-to-end path, preferring one that ends in a named head
        best = None
        for i, a in enumerate(ends):
            for b in ends[i + 1:]:
                p = path_between(a, b)
                if not p:
                    continue
                touches_tail = any(e in tail_named for e in (a, b)) and \
                    not any(e in head_named for e in (a, b)) and len(ends) > 2
                score = (any(e in head_named for e in (a, b)), not touches_tail,
                         sum(x.length for x in p))
                if best is None or score > best[0]:
                    best = (score, p)
        axial = best[1] if best else axial_all[:1]

    def far_point(b, other):
        # the endpoint of b away from its neighbour in the chain
        o = (other.head_local + other.tail_local) * 0.5
        return b.head_local if (b.head_local - o).length > (b.tail_local - o).length \
            else b.tail_local

    upright = False
    if len(axial) >= 2:
        p0 = far_point(axial[0], axial[1])
        p1 = far_point(axial[-1], axial[-2])
        span = p1 - p0
        upright = abs(span.normalized().dot(upv)) > 0.6 if span.length > 1e-9 else False

        if axial[-1] in head_named:
            pass
        elif axial[0] in head_named:
            axial.reverse()
        else:
            head_guessed = True
            score0 = p0.dot(upv) if upright else p0.dot(fwd)
            score1 = p1.dot(upv) if upright else p1.dot(fwd)
            if score0 > score1:
                axial.reverse()
    # axial now runs rear/lower end -> head end

    axial_names = [b.name for b in axial]
    pos = {n: i for i, n in enumerate(axial_names)}

    def axial_index_of(bone_name):
        # walk up from a limb's attach bone to the first axial bone
        b = rig.data.bones.get(bone_name) if bone_name else None
        while b is not None and b.name not in pos:
            b = b.parent
        return pos[b.name] if b is not None else None

    for l in limbs:
        l["axial_index"] = axial_index_of(l["attach"])

    attach_idx = [l["axial_index"] for l in limbs if l["axial_index"] is not None]
    front_attach = max(attach_idx) if attach_idx else -1
    legs = [l for l in limbs if l["role"] == "leg" and l["axial_index"] is not None]
    pelvis_idx = (min(l["axial_index"] for l in legs) if legs
                  else (min(attach_idx) if attach_idx else 0))

    # ------------------------------------------------------------------ tail
    # A tail is not more spine. It carries no limb, it trails rather than
    # supports, and it may rest on the ground - the downloaded rat's does, 1.2
    # cm into it - which is a contact the spine never has. So it is told apart
    # and posed by its own rules (`motion.Body.pose_tail`).
    #
    # Tail when named so, or when the bone's pelvis-side end already lies
    # behind the rearmost hip joint. Neither test alone is enough: Rigify names
    # its tail spine.000-003, and the generic builder's quadruped spine doubles
    # back so its tail starts mid-body, 0.3 m ahead of its hips. Everything past
    # the first tail bone, away from the pelvis, is tail too.
    tail_axial = []
    hips = [l["rest_root"].dot(fwd) for l in legs]
    margin = 0.03 * size
    candidates = list(range(pelvis_idx - 1, -1, -1))        # pelvis side first
    if not legs:
        # a legless body has no hips; only names can say where its tail starts
        candidates = [i for i in range(len(axial)) if _TAIL.search(axial_names[i])]
        candidates.sort(reverse=True)
    started = False
    for i in candidates:
        b = axial[i]
        pelvis_side = None
        if i + 1 < len(axial):
            # the end of this bone nearer the next bone toward the pelvis
            nxt = axial[i + 1]

            def gap(p):
                return min((p - nxt.head_local).length, (p - nxt.tail_local).length)
            pelvis_side = b.head_local if gap(b.head_local) <= gap(b.tail_local) \
                else b.tail_local
        behind = (hips and pelvis_side is not None
                  and pelvis_side.dot(fwd) < min(hips) - margin)
        if started or _TAIL.search(b.name) or behind:
            started = True
            tail_axial.append(b.name)

    head_idx = None
    named = [i for i, n in enumerate(axial_names) if _HEAD.search(n)]
    if named:
        head_idx = named[0]
    elif axial_names and len(axial_names) - 1 > front_attach:
        head_idx = len(axial_names) - 1
    neck = []
    # no limbs means nothing marks where the torso ends, so no neck either
    if head_idx is not None and attach_idx:
        neck = axial_names[front_attach + 1:head_idx]
    neck += [n for n in axial_names if _NECK.search(n) and n not in neck]
    neck_start = min((pos[n] for n in neck), default=head_idx if head_idx is not None
                     else len(axial_names))

    # proximal point of each axial bone: the end facing the rear of the chain
    joints = []
    for i, b in enumerate(axial):
        if len(axial) == 1:
            joints.append(b.head_local.copy())
        elif i == 0:
            joints.append(far_point(b, axial[1]).copy())
        else:
            # the end nearer the previous bone; works whichever way the
            # hierarchy runs and tolerates unconnected gaps
            joints.append(far_point(b, axial[i + 1]).copy() if i + 1 < len(axial)
                          else (b.head_local.copy()
                                if (b.head_local - joints[i - 1]).length
                                < (b.tail_local - joints[i - 1]).length
                                else b.tail_local.copy()))

    tails = []
    for e in ends:
        if e.name in pos:
            continue
        p = None
        for a in axial:
            q = path_between(e, a)
            if q and (p is None or len(q) < len(p)):
                p = q
        if p:
            tails.append([x.name for x in p if x.name not in pos])

    roles = _roles(rig, limbs, axial_names, pelvis_idx, legs, neck, head_idx, head_guessed,
                   tail_axial, height, meshes,
                   maw_names | fin_names | radial_names | tentacle_names)

    return {
        "rig": rig.name,
        "roles": roles,
        "forward": forward, "up": up, "floor": floor,
        "fwd": fwd, "up_vec": upv, "lat": lat,
        "height": body_height, "size": size,
        "upright": upright,
        "axial": axial_names,
        "axial_joints": joints,
        "pelvis_index": pelvis_idx,
        "torso": [n for n in axial_names[pelvis_idx:neck_start] if n not in tail_axial],
        "rear": [n for n in axial_names[:pelvis_idx] if n not in tail_axial],
        # base (at the pelvis) to tip; axial indices are kept in `axial`
        "tail": tail_axial,
        "neck": neck,
        "head": axial_names[head_idx] if head_idx is not None else None,
        "head_guessed": head_guessed,
        "tails": tails,
        "limbs": sorted(limbs, key=lambda l: (-l["forward_pos"], l["side"])),
        # free sheet-skinned limbs, with planform and fold frame; see `wings`
        "wings": wings,
        # jaw, throat, tongue and mouth socket as `maw.build` stored them, or None
        "maw": maw_mod.read(rig),
        "maw_bones": sorted(maw_names),
        "fin_bones": sorted(fin_names),
        "radial_bones": sorted(radial_names),
        "tentacle_bones": sorted(tentacle_names),
        "midline": midline,
        "ignored_chains": ignored,
        "warnings": warnings,
    }


def summary(bm):
    if "error" in bm:
        return bm["error"]
    lines = ["%s: %s body, height %.3f" % (bm["rig"], "upright" if bm["upright"]
                                            else "horizontal", bm["height"])]
    lines.append("  axial  " + " > ".join(bm["axial"]))
    if bm["rear"]:
        lines.append("  rear   %s  (behind the pelvis, not tail)" % ", ".join(bm["rear"]))
    if bm["tail"]:
        lines.append("  TAIL   %s  (base > tip)" % " > ".join(bm["tail"]))
    lines.append("  torso  %s" % ", ".join(bm["torso"]))
    lines.append("  neck   %s" % (", ".join(bm["neck"]) or "(none - head joins torso)"))
    lines.append("  head   %s%s" % (bm["head"], "  (guessed)" if bm["head_guessed"] else ""))
    for t in bm["tails"]:
        lines.append("  tail   " + " > ".join(t))
    for l in bm["limbs"]:
        lines.append("  %-4s %-10s %s%s > %s > %s   on %s  a=%.3f b=%.3f  pole: %s"
                     % (l["role"], l["name"],
                        (l["girdle"] + " > ") if l["girdle"] else "",
                        l["upper"], l["lower"], l["end"] or "-",
                        l["attach"], l["a"], l["b"], l["pole_source"]))
    scale = 1.0
    rig = bpy.data.objects.get(bm["rig"])
    if rig is not None:
        scale = sum(rig.matrix_world.to_scale()) / 3.0
    for w in bm.get("wings", []):
        extra = []
        if w["fingers"]:
            extra.append("%d fingers" % len(w["fingers"]))
        if w["feathers"]:
            extra.append("%d feather bones" % len(w["feathers"]))
        lines.append("  WING %-9s %s, by %s: reach %.3f m%s, sheet %s%s%s"
                     % (w["name"], w["kind"], w["evidence"], w["reach"] * scale,
                        (", area %.3f m2" % (w["area"] * scale * scale)) if w["area"] else "",
                        w["thickness_ratio"],
                        (", " + ", ".join(extra)) if extra else "",
                        ", RESTS FOLDED" if w["rests_folded"] else ""))
    mw = bm.get("maw")
    if mw:
        lines.append("  MAW  %s: %s hinge, mouth %.3f m, gape %.0f deg, throat %s, tongue %s"
                     % (mw["kind"], mw["jaw"], mw["mouth_length"] * scale, mw["spec"]["gape"],
                        mw["throat"], " > ".join(mw["tongue"]) or "-"))
    elif bm.get("maw_bones"):
        lines.append("  maw bones %s - not measured by maw.build, so not posable"
                     % ", ".join(bm["maw_bones"]))
    if bm.get("fin_bones"):
        lines.append("  FINS %d ray bones - posed by fins.FinRig" % len(bm["fin_bones"]))
    if bm.get("radial_bones"):
        lines.append("  RADIAL %d hub, rib and arm bones - posed by radial.RadialRig" % len(bm["radial_bones"]))
    if bm.get("tentacle_bones"):
        lines.append("  TENTACLES %d bones - posed by the tentacles module" % len(bm["tentacle_bones"]))
    r = bm.get("roles") or {}
    if r:
        lines.append("  ROLES root %s, pelvis %s, chest %s, head %s%s"
                     % (r["root"], r["pelvis"], r["chest"], r["head"],
                        "" if r["skinned"] else "  (no skin read)"))
        if r["controls"]:
            lines.append("  controls %s" % ", ".join(r["controls"]))
    for w in bm["warnings"] + r.get("warnings", []):
        lines.append("  WARN " + w)
    return "\n".join(lines)
