"""Test bodies with no front or back: a jellyfish, a starfish, a brittle star and
an anemone, built procedurally so `radial` has shapes whose answers are known.

They are deliberately built the two ways real assets arrive:

- the jellyfish's bell is one closed shell and its tentacles and oral arms are
  SEPARATE loose parts overlapping it - how a modelled jellyfish usually comes,
  and exactly what bone heat refuses;
- the starfish, brittle star and anemone are one connected skin, arms fused to
  the body, made from metaballs so the junctions are smooth and manifold.

Each is sized like the animal: an Aurelia-like bell 0.3 m across with fineness
0.38, a 0.25 m starfish, a brittle star with a 0.03 m disc and 0.14 m arms.
"""

from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Vector


def _replace(name):
    old = bpy.data.objects.get(name)
    if old is not None:
        data = old.data
        bpy.data.objects.remove(old, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.MetaBall):
                bpy.data.metaballs.remove(data)


def _link(obj, collection=None):
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def _tube(bm, points, radii, sides=8):
    """A capped tube along `points`, radius per point, into `bm`."""
    rings = []
    prev_n = None
    for i, p in enumerate(points):
        t = (points[min(i + 1, len(points) - 1)] - points[max(i - 1, 0)]).normalized()
        if prev_n is None:
            ref = Vector((1, 0, 0)) if abs(t.x) < 0.9 else Vector((0, 1, 0))
            prev_n = (ref - t * ref.dot(t)).normalized()
        else:
            prev_n = (prev_n - t * prev_n.dot(t)).normalized()
        b = t.cross(prev_n)
        rings.append([bm.verts.new(p + (prev_n * math.cos(2 * math.pi * k / sides)
                                        + b * math.sin(2 * math.pi * k / sides)) * radii[i])
                      for k in range(sides)])
    for a, c in zip(rings, rings[1:]):
        for k in range(sides):
            bm.faces.new((a[k], a[(k + 1) % sides], c[(k + 1) % sides], c[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def jellyfish(name="JellyTest", diameter=0.3, fineness=0.38, thickness=0.035,
              tentacles=8, oral_arms=4, tentacle_length=1.4, segments=64, collection=None):
    """An oblate, rowing jellyfish: a closed bell shell, `tentacles` marginal
    tentacles and `oral_arms` oral arms, every appendage its own loose part.
    Tentacles sit on multiples of 360/tentacles and oral arms between them, so
    with the defaults the body is tetraradial - 4-fold - like Aurelia."""
    _replace(name)
    R, H = 0.5 * diameter, fineness * diameter
    t = thickness * diameter
    bm = bmesh.new()
    outer_rings, inner_rings = 14, 11

    def ring(r, h):
        return [bm.verts.new((r * math.cos(2 * math.pi * k / segments),
                              r * math.sin(2 * math.pi * k / segments), h)) for k in range(segments)]
    top = bm.verts.new((0.0, 0.0, H))
    rings = []
    for i in range(1, outer_rings + 1):
        phi = 0.5 * math.pi * i / outer_rings
        rings.append(ring(R * math.sin(phi), H * math.cos(phi) ** 0.9))
    # the margin: a rounded lip
    rings.append(ring(R - 0.5 * t, -0.35 * t))
    for i in range(inner_rings, 0, -1):
        phi = 0.5 * math.pi * i / inner_rings
        rings.append(ring((R - t) * math.sin(phi), (H - t) * math.cos(phi) ** 0.9 - 0.05 * t))
    bottom = bm.verts.new((0.0, 0.0, H - t - 0.05 * t))
    for k in range(segments):
        bm.faces.new((top, rings[0][k], rings[0][(k + 1) % segments]))
    for a, c in zip(rings, rings[1:]):
        for k in range(segments):
            bm.faces.new((a[k], c[k], c[(k + 1) % segments], a[(k + 1) % segments]))
    for k in range(segments):
        bm.faces.new((bottom, rings[-1][(k + 1) % segments], rings[-1][k]))

    L = tentacle_length * diameter
    for j in range(tentacles):
        th = 2 * math.pi * j / tentacles
        d = Vector((math.cos(th), math.sin(th), 0.0))
        pts, radii = [], []
        for i in range(25):
            s = i / 24.0
            pts.append(d * (R - 0.5 * t + 0.08 * R * math.sin(math.pi * s) - 0.05 * R * s)
                       + Vector((0.0, 0.0, 0.2 * t - L * s)))
            radii.append(diameter * (0.012 - 0.009 * s))
        _tube(bm, pts, radii, sides=6)
    for j in range(oral_arms):
        th = 2 * math.pi * (j + 0.5) / oral_arms
        d = Vector((math.cos(th), math.sin(th), 0.0))
        pts, radii = [], []
        for i in range(17):
            s = i / 16.0
            pts.append(d * (0.06 * R + 0.35 * R * math.sin(0.5 * math.pi * s))
                       + Vector((0.0, 0.0, H - t - 0.01 * diameter - 0.75 * diameter * s)))
            radii.append(diameter * (0.035 - 0.022 * s))
        _tube(bm, pts, radii, sides=8)
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    obj = _link(bpy.data.objects.new(name, me), collection)
    # float it: the tentacle tips a little above the floor
    obj.location.z = L + 0.05
    _apply_location(obj)
    return obj


def _apply_location(obj):
    obj.data.transform(obj.matrix_basis)
    obj.matrix_basis.identity()


def _metaball_mesh(name, elements, resolution, collection=None):
    """Mesh a set of (co, radius) metaballs into one connected skin."""
    _replace(name)
    _replace(name + "_mb")
    mb = bpy.data.metaballs.new(name + "_mb")
    mb.resolution = resolution
    mb.render_resolution = resolution
    mb.threshold = 0.6
    for co, rad, stiff in elements:
        e = mb.elements.new()
        e.co = co
        e.radius = rad
        e.stiffness = stiff
    tmp = bpy.data.objects.new(name + "_mb", mb)
    bpy.context.scene.collection.objects.link(tmp)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.metaballs.remove(mb)
    me.name = name
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=resolution * 0.05)
    # A metaball chain thins out below threshold at its very tip and leaves a
    # few beads floating past it. Those are the generator's, not the animal's.
    bm.verts.ensure_lookup_table()
    seen, best = set(), []
    for v0 in bm.verts:
        if v0 in seen:
            continue
        stack, comp = [v0], []
        seen.add(v0)
        while stack:
            v = stack.pop()
            comp.append(v)
            for e in v.link_edges:
                o = e.other_vert(v)
                if o not in seen:
                    seen.add(o)
                    stack.append(o)
        if len(comp) > len(best):
            best = comp
    keep = set(best)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v not in keep], context="VERTS")
    bm.to_mesh(me)
    bm.free()
    obj = _link(bpy.data.objects.new(name, me), collection)
    # rest it on the floor
    low = min(v.co.z for v in me.vertices)
    obj.location.z = -low
    _apply_location(obj)
    return obj


def _arm_balls(n_arms, disc_r, arm_len, root_r, tip_r, count=None, lift=0.0, start=0.0, z=0.0,
               curl=0.0, stiff=2.0):
    """Balls along each arm. A metaball shows at about 0.57 of its radius at
    threshold 0.6, so balls further apart than their radius mesh as beads - the
    first starfish came out as 7 loose parts - and they are spaced at 0.4 tip
    radii."""
    if count is None:
        count = int(math.ceil(arm_len / (0.4 * tip_r)))
    out = []
    for j in range(n_arms):
        th = start + 2 * math.pi * j / n_arms
        d = Vector((math.cos(th), math.sin(th), 0.0))
        for i in range(count):
            s = (i + 1) / float(count)
            r = disc_r * 0.6 + arm_len * s
            out.append((d * r + Vector((0.0, 0.0, z + lift * s * s + curl * s ** 3)),
                        root_r + (tip_r - root_r) * s, stiff))
    return out


def starfish(name="StarTest", span=0.25, arms=5, collection=None):
    """A sea star: a broad disc and stout tapering arms, one connected skin."""
    disc = 0.16 * span
    elems = [(Vector((0.0, 0.0, 0.0)), disc * 1.25, 2.0)]
    elems += _arm_balls(arms, disc, 0.5 * span - disc * 0.6, 0.09 * span, 0.04 * span)
    obj = _metaball_mesh(name, elems, resolution=0.004, collection=collection)
    _flatten(obj, 0.55)
    return obj


def brittle_star(name="BrittleTest", disc=0.03, arm_length=0.14, arms=5, collection=None):
    """A brittle star: a small round disc and long slender arms that stay slender
    to the tip - the rowers of Astley 2012."""
    elems = [(Vector((0.0, 0.0, 0.0)), disc * 1.05, 2.0)]
    elems += _arm_balls(arms, disc, arm_length, 0.009, 0.005)
    obj = _metaball_mesh(name, elems, resolution=0.0015, collection=collection)
    _flatten(obj, 0.6)
    return obj


def anemone(name="AnemoneTest", height=0.22, column=0.05, tentacles=10, collection=None):
    """A sea anemone: a column on the floor and a crown of tentacles round the
    oral disc at the top, curving up and out - its appendages point oral, as a
    jellyfish's do, only its oral side is up."""
    elems = []
    for i in range(13):
        s = i / 12.0
        elems.append((Vector((0.0, 0.0, 0.6 * height * s)), column * (1.15 - 0.15 * s), 2.0))
    top = 0.62 * height
    elems += _arm_balls(tentacles, column * 1.1, 0.4 * height, 0.018, 0.009, lift=0.25 * height,
                        z=top, curl=0.05 * height)
    return _metaball_mesh(name, elems, resolution=0.003, collection=collection)


def _flatten(obj, share):
    """Squash along Z about the floor: a starfish is far flatter than a metaball
    arm is round."""
    for v in obj.data.vertices:
        v.co.z *= share
    obj.data.update()


def build_all(collection_name="RadialTests"):
    coll = bpy.data.collections.get(collection_name)
    if coll is None:
        coll = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(coll)
    made = [jellyfish(collection=coll), starfish(collection=coll),
            brittle_star(collection=coll), anemone(collection=coll)]
    # side by side, each at its own spot on the floor - world origin is where
    # the analysis expects a body to be rigged, so move them back before export
    return {o.name: {"vertices": len(o.data.vertices), "dimensions": [round(x, 4) for x in o.dimensions]}
            for o in made}
