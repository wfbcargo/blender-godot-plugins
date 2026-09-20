"""Per-bone mass, centre of mass and inertia, measured from the skin.

Nothing in the package knew what a body weighs. `motion._com_terms` comes
closest and gets it wrong in a way that does not show until you ask for more
than a centroid: it weights each bone by the SUM OF ITS VERTEX WEIGHTS, so mass
follows mesh density rather than volume. On Belle that put 50% of her mass in
the head bone and 4% in each big toe, because a face is modelled finely and a
toe is modelled finely and a thigh is not. For a COM that only ever moved a few
centimetres that was tolerable. For angular momentum it is not: momentum is
mass times a lever arm, and both come from here.

TWO MEASUREMENTS, WHICH CHECK EACH OTHER

**The whole body** is a closed surface, so its volume integrals are surface
integrals: each triangle spans a signed tetrahedron with the origin, and
summing them gives volume, centre and inertia exactly, concavities and cavities
cancelling on their own. Exact, fast, and origin-independent - for the WHOLE.

**Per bone it does not work at all**, which cost an afternoon to see. Weight a
tetrahedron by its triangle's skin weights and you have not partitioned the
body: you have integrated the weight extended inward ALONG RAYS FROM THE
ORIGIN, so a ray reaching the left thigh drags the pelvis it passed through
into the thigh's share. The answer then changes when the origin moves, which is
the tell - `integral(w dV)` over a closed surface is origin-independent only
when `w` is constant. Belle's thighs came out 10.8 kg and 6.4 kg, and no amount
of hole-filling touched it.

So the partition is VOLUMETRIC. The body is voxelised, each interior voxel
takes the skin weights of its nearest surface vertex, and mass, centre and
inertia accumulate per bone from the voxels. That is origin-independent by
construction, it is what "the mass that moves with this bone" actually means,
and it degrades gracefully on a mesh with holes rather than exploding.

The two methods are independent, so they are run together and compared:
`volume_agreement` is the voxel total against the surface total. The VOXEL
number is the one reported, because the surface integral is exact only on a
closed surface and real bodies are not closed - Belle keeps 637 boundary edges
in her head that no filler will take, and that is the whole of her 4% gap. So
read the pair together with `watertight`: agreement on a watertight mesh means
both methods and the resolution are sound, and a gap on a mesh that is NOT
watertight is the surface's error, not the partition's. A gap on a watertight
mesh is the one to worry about.

Two things about real assets that this had to learn the hard way, both of them
silent until measured: a body is many OVERLAPPING shells, because hands and
feet are transplanted parts, so inside/outside is a winding number and never a
parity; and those shells do not agree which way is out - Marco's cast glb is
wound inward where Belle's is not, and a mesh with only SOME shells flipped
reads 16% light with no sign change to give it away.

WHAT IS STORED, AND WHY IN THAT FRAME

Per bone: mass, and the centre of mass and inertia tensor written in the BONE'S
OWN REST-LOCAL FRAME. That is the only frame in which they are constants. Posed,
a bone's world inertia is `R I R^T` for that bone's rotation and its COM rides
its matrix, so a consumer needs no remeasuring per frame - which is what makes a
per-frame angular-momentum term affordable.

Density is uniform by default, which is a real approximation: bone, fat and
lung differ by a factor of several, and the error lands mostly in the trunk.
Pass `total_mass` to rescale a body to a known weight - that fixes the total,
not the distribution. Improving the distribution wants per-region densities,
which the follow-through flesh registry already carries for some tissues.

Sources: Dempster's segment data and Winter, "Biomechanics and Motor Control of
Human Movement", for whole-body density ~1010 kg/m^3; the tetrahedron
decomposition is the standard divergence-theorem construction (cf. Mirtich,
"Fast and Accurate Computation of Polyhedral Mass Properties", 1996).
"""

from __future__ import annotations

import json
import math

# Whole-body density of an adult human, kg/m^3. Close enough for any flesh
# creature; a body that is mostly gas or stone wants its own.
DEFAULT_DENSITY = 1010.0

STAMP_KEY = "rig_anything_mass"

# Interior voxels to aim for. 300k over a human is ~6 mm, which resolves a
# finger and costs a few seconds; inertia converges long before the eye does.
TARGET_VOXELS = 300000
MIN_VOXEL_M = 0.0015
# Mirror symmetry is only checked on bones holding at least this share of
# the body; below it, one voxel is a large fraction of the bone.
MIRROR_MIN_SHARE = 0.005

# Canonical second moment of the tetrahedron (0, e1, e2, e3):
#   integral of x_i x_j dV = (1 + delta_ij) / 120
# so the covariance of a general tet (0, a, b, c) is
#   det(J)/120 * (a a^T + b b^T + c c^T + s s^T),  s = a + b + c
_COV_SCALE = 1.0 / 120.0

# For axis a, the in-plane axes are the other two in increasing order (u, v).
# (u, v, a) is (1,2,0) for x and (0,1,2) for z - even permutations - but
# (0,2,1) for y, which is odd, so the projected cross product points the other
# way there. Getting this wrong flips every crossing on one axis in three.
_PARITY = (1.0, -1.0, 1.0)


# --------------------------------------------------------------------------
# the integrals - plain arithmetic, no bpy, so they can be self-tested
# --------------------------------------------------------------------------

def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _outer_into(m, v, k):
    """m += k * v v^T, m a flat 9-list."""
    for i in range(3):
        vi = v[i] * k
        m[i * 3 + 0] += vi * v[0]
        m[i * 3 + 1] += vi * v[1]
        m[i * 3 + 2] += vi * v[2]


class Accum:
    """Running volume, first moment and second moment about the origin.

    Fed either whole tetrahedra (the surface integral) or voxels (the
    partition); the reductions afterwards are the same either way.
    """

    __slots__ = ("vol", "mom", "cov")

    def __init__(self):
        self.vol = 0.0
        self.mom = [0.0, 0.0, 0.0]
        self.cov = [0.0] * 9

    def add_tet(self, a, b, c, share=1.0):
        """The tetrahedron (origin, a, b, c), scaled by `share`."""
        det = _dot(a, _cross(b, c))
        vol = det / 6.0 * share
        self.vol += vol
        q = vol * 0.25
        s = (a[0] + b[0] + c[0], a[1] + b[1] + c[1], a[2] + b[2] + c[2])
        self.mom[0] += s[0] * q
        self.mom[1] += s[1] * q
        self.mom[2] += s[2] * q
        k = det * _COV_SCALE * share
        _outer_into(self.cov, a, k)
        _outer_into(self.cov, b, k)
        _outer_into(self.cov, c, k)
        _outer_into(self.cov, s, k)

    def add_voxel(self, c, vol, self_moment):
        """A cube of volume `vol` centred at `c`.

        `self_moment` is the cube's own second moment about its centre,
        vol * h^2 / 12 per axis - small, but free, and it keeps a one-voxel
        bone from reporting zero inertia.
        """
        self.vol += vol
        self.mom[0] += c[0] * vol
        self.mom[1] += c[1] * vol
        self.mom[2] += c[2] * vol
        _outer_into(self.cov, c, vol)
        self.cov[0] += self_moment
        self.cov[4] += self_moment
        self.cov[8] += self_moment

    def centre(self):
        if abs(self.vol) < 1e-18:
            return (0.0, 0.0, 0.0)
        return (self.mom[0] / self.vol, self.mom[1] / self.vol, self.mom[2] / self.vol)

    def inertia_about_centre(self, density):
        """Inertia tensor about this accumulation's own centre of mass.

        The covariance shifts by the parallel-axis term first; the inertia
        tensor is then trace(C) I - C, which is the standard identity between
        the second moment of mass and the moment of inertia."""
        c = self.centre()
        cov = list(self.cov)
        shift = [0.0] * 9
        _outer_into(shift, c, self.vol)
        for i in range(9):
            cov[i] = (cov[i] - shift[i]) * density
        tr = cov[0] + cov[4] + cov[8]
        out = [-x for x in cov]
        out[0] += tr
        out[4] += tr
        out[8] += tr
        return out


def _to_local(point, basis_inv, origin):
    """A point in armature space, written in a bone's rest-local frame."""
    d = (point[0] - origin[0], point[1] - origin[1], point[2] - origin[2])
    return tuple(_dot(basis_inv[i], d) for i in range(3))


def _rotate_tensor(t, basis_inv):
    """R^T T R, with R the bone's rest basis (rows of basis_inv are R's columns)."""
    m = [0.0] * 9
    for i in range(3):
        for j in range(3):
            m[i * 3 + j] = sum(basis_inv[i][k] * t[k * 3 + j] for k in range(3))
    out = [0.0] * 9
    for i in range(3):
        for j in range(3):
            out[i * 3 + j] = sum(m[i * 3 + k] * basis_inv[j][k] for k in range(3))
    return out


_SIDE_SUFFIX = ((".L", ".R"), (".l", ".r"), ("_L", "_R"), ("_l", "_r"))


def _mirror_name(name):
    """The name of this bone's opposite number, or None if it has no side."""
    for a, b in _SIDE_SUFFIX:
        for x, y in ((a, b), (b, a)):
            if name.endswith(x):
                return name[:-len(x)] + y
            i = name.find(x + ".")
            if i >= 0:
                return name[:i] + y + name[i + len(x):]
    return None


# --------------------------------------------------------------------------
# geometry gathering
# --------------------------------------------------------------------------

def _meshes_for(rig):
    import bpy
    return [o for o in bpy.data.objects if o.type == "MESH" and any(
        m.type == "ARMATURE" and m.object == rig for m in o.modifiers)]


def _boundary_loops(edges):
    """Split boundary edges into closed vertex loops."""
    adj = {}
    for e in edges:
        for a, b in ((e.verts[0], e.verts[1]), (e.verts[1], e.verts[0])):
            adj.setdefault(a, []).append((b, e))
    loops, seen = [], set()
    for start in adj:
        if start in seen or len(adj[start]) != 2:
            continue
        loop, loop_edges, cur, prev = [start], [], start, None
        seen.add(start)
        while True:
            nxt = nxt_e = None
            for v, e in adj[cur]:
                if v is not prev and (v is start or v not in seen):
                    nxt, nxt_e = v, e
                    break
            if nxt is None:
                break
            loop_edges.append(nxt_e)
            if nxt is start:
                loops.append((loop, loop_edges))
                break
            if len(adj.get(nxt, ())) != 2:
                break                       # a junction: not a simple loop
            seen.add(nxt)
            loop.append(nxt)
            prev, cur = cur, nxt
    return loops


def _fill_holes(bm, warnings, obj_name):
    """Close the surface, and say how much of it could not be closed.

    Bodies from humanform arrive as several shells - hands and feet are
    transplanted parts - open where they meet, and open again at the eye
    sockets and the mouth bag. An open surface has no volume: the integral
    depends on where the origin sits. Leaving Belle's unfilled overstated her
    by 14%.

    `holes_fill` first, because it handles the easy loops well; then
    `triangle_fill` ONE LOOP AT A TIME, because a filler handed every remaining
    boundary edge at once will bridge two separate openings and the face
    spanning them adds a slab of volume that is not in the body.
    """
    import bmesh
    boundary = [e for e in bm.edges if len(e.link_faces) == 1]
    found = len(boundary)
    if not boundary:
        return found, 0
    try:
        res = bmesh.ops.holes_fill(bm, edges=boundary, sides=0)
        new = [f for f in res.get("faces", []) if f.is_valid]
        if new:
            bmesh.ops.triangulate(bm, faces=new)
    except RuntimeError as e:                               # pragma: no cover
        warnings.append("%s: holes_fill failed (%s)" % (obj_name, e))

    left = [e for e in bm.edges if len(e.link_faces) == 1]
    for _verts, loop_edges in _boundary_loops(left):
        if len(loop_edges) < 3:
            continue
        try:
            res = bmesh.ops.triangle_fill(bm, edges=loop_edges, use_beauty=True)
        except RuntimeError:                                # pragma: no cover
            continue
        made = [f for f in res.get("geom", [])
                if isinstance(f, bmesh.types.BMFace) and f.is_valid]
        if made:
            bmesh.ops.triangulate(bm, faces=made)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    still = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    if still:
        warnings.append("%s: %d boundary edges could not be closed; the surface "
                        "total is approximate there" % (obj_name, still))
    return found, found - still


def _gather(rig, warnings):
    """Every skinned triangle in armature space, with per-vertex bone weights.

    Returns (verts, tris, weights, meshes, holes). `weights[i]` is a list of
    (bone, share) summing to one, or empty where nothing is weighted.
    """
    import bmesh

    to_arm = rig.matrix_world.inverted()
    verts, tris, weights = [], [], []
    holes = [0, 0]
    meshes = _meshes_for(rig)
    for o in meshes:
        groups = {g.index: g.name for g in o.vertex_groups
                  if g.name in rig.data.bones and rig.data.bones[g.name].use_deform}
        m = to_arm @ o.matrix_world
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.transform(m)
        if m.determinant() < 0.0:
            # a mirrored object scale turns the surface inside out
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        # Every shell outward, before anything is measured. A body arrives as
        # many shells (hands and feet are transplanted parts) and they do not
        # agree about which way is out: Marco's cast glb imports wound inward
        # where Belle's does not, and a mesh with SOME shells flipped is worse
        # than one wound wholly inward, because the flipped ones subtract and
        # the surface total quietly comes out 16% off with no sign change to
        # notice. The winding-number test downstream needs this too.
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        found, filled = _fill_holes(bm, warnings, o.name)
        holes[0] += found
        holes[1] += filled
        bm.verts.ensure_lookup_table()

        base = len(verts)
        dl = bm.verts.layers.deform.active
        for v in bm.verts:
            verts.append(tuple(v.co))
            ws = []
            if dl is not None:
                ws = [(groups[gi], w) for gi, w in v[dl].items()
                      if gi in groups and w > 0.0]
            tot = sum(w for _, w in ws)
            weights.append([(n, w / tot) for n, w in ws] if tot > 0.0 else [])
        for f in bm.faces:
            if len(f.verts) == 3:
                tris.append(tuple(base + v.index for v in f.verts))
        bm.free()
    return verts, tris, weights, meshes, holes


# --------------------------------------------------------------------------
# the volumetric partition
# --------------------------------------------------------------------------

def _axis_spans(verts, tris, lo, h, dims, axis, mark):
    """Mark every cell whose centre is inside, by WINDING NUMBER along one axis.

    Not parity. A body from humanform is not one closed manifold - hands and
    feet are transplanted parts, so it arrives as a couple of dozen shells that
    OVERLAP at the wrists and ankles. A ray through an overlap crosses four
    surfaces where there are two solids, parity says "outside", and the arm
    hollows out. Counting signed crossings gives the union instead, which is
    what a body made of overlapping parts means: enter a shell and the winding
    goes up, leave it and it comes down, and inside is wherever it is above
    zero. Nested shells - an eyeball inside a head - fall out correctly too.

    The crossings are found by RASTERISING each triangle into the columns it
    covers, not by casting rays. Ray casting a mesh with coincident surfaces
    means stepping off each hit by an epsilon to avoid hitting it again, and on
    Belle's overlapping seams that crawl ran into its own iteration cap
    mid-body, left the winding stuck positive, and filled the air beside her
    arm with 345% too much solid. Rasterising has no epsilon and no cap: each
    triangle contributes exactly one crossing to each column it covers.
    """
    nx, ny, nz = dims
    stride = (ny * nz, nz, 1)
    u, v = [k for k in range(3) if k != axis]
    nu, nv = dims[u], dims[v]
    cols = [None] * (nu * nv)
    # Nudge the sample point off the lattice so a column centre landing exactly
    # on a shared edge does not count twice or fall through the crack.
    jit = h * 1.37e-4
    lu, lv, la = lo[u], lo[v], lo[axis]

    for i0, i1, i2 in tris:
        p0, p1, p2 = verts[i0], verts[i1], verts[i2]
        a0u, a0v, a0a = p0[u], p0[v], p0[axis]
        a1u, a1v, a1a = p1[u], p1[v], p1[axis]
        a2u, a2v, a2a = p2[u], p2[v], p2[axis]
        # Twice the signed projected area normalises the barycentrics; its
        # sign alone will NOT do for entering-vs-leaving, because which way
        # round (u, v) sits relative to the axis flips with the axis (for y,
        # x cross z is -y). Take the normal's own component instead.
        area = (a1u - a0u) * (a2v - a0v) - (a2u - a0u) * (a1v - a0v)
        if area == 0.0:
            continue                    # edge-on to this axis: no crossing
        inv = 1.0 / area
        e1 = (a1u - a0u, a1v - a0v, a1a - a0a)
        e2 = (a2u - a0u, a2v - a0v, a2a - a0a)
        # the (u, v, axis) frame is right-handed iff (u, v, axis) is an even
        # permutation of (0, 1, 2); `_PARITY` carries that so the cross
        # product's axis component comes out in world orientation
        na = (e1[0] * e2[1] - e1[1] * e2[0]) * _PARITY[axis]
        if na == 0.0:
            continue
        sign = 1 if na < 0.0 else -1        # normal against the ray: entering

        iu0 = int(math.ceil((min(a0u, a1u, a2u) - lu) / h - 0.5))
        iu1 = int(math.floor((max(a0u, a1u, a2u) - lu) / h - 0.5))
        iv0 = int(math.ceil((min(a0v, a1v, a2v) - lv) / h - 0.5))
        iv1 = int(math.floor((max(a0v, a1v, a2v) - lv) / h - 0.5))
        if iu0 < 0:
            iu0 = 0
        if iv0 < 0:
            iv0 = 0
        if iu1 > nu - 1:
            iu1 = nu - 1
        if iv1 > nv - 1:
            iv1 = nv - 1

        for iu in range(iu0, iu1 + 1):
            cu = lu + (iu + 0.5) * h + jit
            row = iu * nv
            for iv in range(iv0, iv1 + 1):
                cv = lv + (iv + 0.5) * h + jit
                w0 = ((a1u - cu) * (a2v - cv) - (a2u - cu) * (a1v - cv)) * inv
                if w0 < 0.0:
                    continue
                w1 = ((a2u - cu) * (a0v - cv) - (a0u - cu) * (a2v - cv)) * inv
                if w1 < 0.0:
                    continue
                w2 = 1.0 - w0 - w1
                if w2 < 0.0:
                    continue
                t = w0 * a0a + w1 * a1a + w2 * a2a
                c = cols[row + iv]
                if c is None:
                    cols[row + iv] = [(t, sign)]
                else:
                    c.append((t, sign))

    na = dims[axis]
    top = la + (na + 1) * h
    su, sv, sa = stride[u], stride[v], stride[axis]
    for idx, cr in enumerate(cols):
        if not cr:
            continue
        cr.sort()
        iu, iv = divmod(idx, nv)
        base = iu * su + iv * sv
        winding = 0
        n = len(cr)
        for i in range(n):
            t, sg = cr[i]
            winding += sg
            if winding <= 0:
                continue
            nxt = cr[i + 1][0] if i + 1 < n else top
            k0 = int(math.ceil((t - la) / h - 0.5))
            k1 = int(math.floor((nxt - la) / h - 0.5))
            if k0 < 0:
                k0 = 0
            if k1 > na - 1:
                k1 = na - 1
            for c in range(k0, k1 + 1):
                mark[base + c * sa] += 1


def _voxelise(verts, tris, weights, volume, target=TARGET_VOXELS):
    """Per-bone Accums from voxels inside the surface.

    Inside/outside is the winding number along ALL THREE axes, majority vote.
    One axis is not enough on a real body: a column running along a limb grazes
    it tangentially, and a column through an unclosed eye socket has no honest
    answer at all. Two axes out of three agreeing rides over both, and where
    the surface is sound all three agree anyway.

    Each interior voxel takes the bone weights of its nearest surface vertex.
    """
    from mathutils import Vector
    from mathutils.kdtree import KDTree

    lo = [min(v[i] for v in verts) for i in range(3)]
    hi = [max(v[i] for v in verts) for i in range(3)]
    # `target` counts INTERIOR voxels, so size the cell from the body's own
    # volume, which the surface integral already measured exactly. Guessing a
    # fill fraction from the bounding box instead is what made the first run
    # land on 69k voxels when it asked for 300k: a figure with its arms out
    # fills far less of its box than a solid would.
    h = max(MIN_VOXEL_M, (max(volume, 1e-12) / max(target, 1.0)) ** (1.0 / 3.0))
    dims = [max(1, int(math.ceil((hi[i] - lo[i]) / h)) + 1) for i in range(3)]
    nx, ny, nz = dims

    kd = KDTree(len(verts))
    for i, v in enumerate(verts):
        kd.insert(Vector(v), i)
    kd.balance()

    votes = bytearray(nx * ny * nz)
    for axis in (0, 1, 2):
        _axis_spans(verts, tris, lo, h, dims, axis, votes)

    vol = h * h * h
    self_moment = vol * h * h / 12.0
    per_bone, unassigned = {}, Accum()
    voxels = 0
    for ix in range(nx):
        x = lo[0] + (ix + 0.5) * h
        for iy in range(ny):
            y = lo[1] + (iy + 0.5) * h
            base = (ix * ny + iy) * nz
            for iz in range(nz):
                if votes[base + iz] < 2:
                    continue
                p = (x, y, lo[2] + (iz + 0.5) * h)
                _co, idx, _d = kd.find(Vector(p))
                voxels += 1
                ws = weights[idx] if idx is not None else ()
                if not ws:
                    unassigned.add_voxel(p, vol, self_moment)
                    continue
                for n, sh in ws:
                    acc = per_bone.get(n)
                    if acc is None:
                        acc = per_bone[n] = Accum()
                    acc.add_voxel(p, vol * sh, self_moment * sh)
    return per_bone, unassigned, {"voxel_m": h, "voxels": voxels, "grid": dims}


# --------------------------------------------------------------------------
# measuring a rig
# --------------------------------------------------------------------------

def measure(rig_name, density=DEFAULT_DENSITY, total_mass=None,
            target_voxels=TARGET_VOXELS):
    """Mass, COM and inertia for the body and for every deforming bone.

    Measured on the REST mesh (`o.data`, as `motion._com_terms` uses), in
    armature space, with each bone's result also written in its own rest-local
    frame where it is constant.

    `total_mass` rescales the density so the body weighs that; the density
    actually used is reported.
    """
    import bpy
    from mathutils import Vector

    rig = bpy.data.objects.get(rig_name)
    if rig is None or rig.type != "ARMATURE":
        return {"error": "no armature named " + repr(rig_name)}
    meshes = _meshes_for(rig)
    if not meshes:
        return {"error": "no mesh is skinned to " + repr(rig_name)}

    warnings = []
    verts, tris, weights, meshes, holes = _gather(rig, warnings)
    if not tris:
        return {"error": "no triangles on the meshes skinned to " + repr(rig_name)}

    # the whole body, exactly, from the surface
    whole = Accum()
    for a, b, c in tris:
        whole.add_tet(verts[a], verts[b], verts[c])
    if whole.vol < 0.0:
        # The surface is wound inward as a whole - Marco and the rest of the
        # cast import that way where Belle does not. That is not an error to
        # refuse, it is a convention to flip: a signed volume tells you which
        # way round a closed surface is, so turn it over and carry on. The
        # winding-number test downstream would otherwise find nothing inside.
        tris = [(a, c, b) for a, b, c in tris]
        whole = Accum()
        for a, b, c in tris:
            whole.add_tet(verts[a], verts[b], verts[c])
        warnings.append("the surface was wound inward; flipped")
    if whole.vol <= 0.0:
        return {"error": "measured volume is %.6g m^3 - the surface encloses "
                         "nothing" % whole.vol}

    # the partition, volumetrically
    per_bone, unassigned, grid = _voxelise(verts, tris, weights, whole.vol,
                                           target_voxels)
    if not per_bone:
        return {"error": "no voxel landed inside the surface - the mesh may be "
                         "open everywhere, or smaller than one voxel"}


    # The VOXELS are authoritative, and the surface total is the cross-check.
    # It was the other way round at first, rescaling the partition onto the
    # surface's number - which quietly pushed that number's error into every
    # bone. The surface integral is exact only on a CLOSED surface, and the 637
    # boundary edges left in Belle's head are why the two sit ~4% apart. A
    # discretisation error shrinks with the voxel; this one does not, at three
    # resolutions, so it belongs to the surface.
    voxel_vol = sum(a.vol for a in per_bone.values()) + unassigned.vol
    used_density = density
    if total_mass is not None:
        if total_mass <= 0.0:
            return {"error": "total_mass must be positive"}
        used_density = total_mass / max(voxel_vol, 1e-12)

    bones = {}
    for name, acc in per_bone.items():
        b = rig.data.bones[name]
        basis = b.matrix_local.to_3x3()
        basis_inv = [tuple(basis.col[i]) for i in range(3)]      # rows of R^T
        centre = acc.centre()
        inertia = acc.inertia_about_centre(used_density)
        bones[name] = {
            "mass": acc.vol * used_density,
            "volume": acc.vol,
            "com": list(centre),
            "com_local": list(_to_local(centre, basis_inv, tuple(b.head_local))),
            "inertia_local": _rotate_tensor(inertia, basis_inv),
        }

    return {
        "rig": rig_name,
        "meshes": [o.name for o in meshes],
        "density": used_density,
        "density_given": density,
        "total_mass": voxel_vol * used_density,
        "total_volume": voxel_vol,
        "surface_volume": whole.vol,
        "com": list(whole.centre()),
        "inertia": whole.inertia_about_centre(used_density),
        "grid": grid,
        "bones": bones,
        "holes": {"found": holes[0], "filled": holes[1]},
        "warnings": warnings,
        "checks": _checks(whole, per_bone, unassigned, voxel_vol, grid, holes),
    }


def _checks(whole, per_bone, unassigned, voxel_vol, grid, holes):
    """Everything that must hold if the measurement means anything."""
    agreement = voxel_vol / whole.vol if whole.vol else 0.0
    negative = sorted(n for n, a in per_bone.items() if a.vol <= 0.0)
    # A mirrored body's paired bones must weigh the same, and nothing else
    # here notices a partition leaking across the midline. But a distal phalanx
    # is a centimetre long and holds a fraction of a gram, so at any usable
    # resolution its two sides differ by a quarter and say nothing - the pair
    # that trips the check wanders between runs, which is how you tell noise
    # from a defect. The gate looks only at bones carrying real mass; the small
    # ones are reported separately rather than thrown away.
    worst, worst_pair = 0.0, None
    small_worst = 0.0
    for name, acc in per_bone.items():
        other = _mirror_name(name)
        twin = per_bone.get(other) if other else None
        if twin is None or other < name:
            continue
        m = max(abs(acc.vol), abs(twin.vol))
        if m <= 0.0:
            continue
        d = abs(acc.vol - twin.vol) / m
        if m < MIRROR_MIN_SHARE * voxel_vol:
            small_worst = max(small_worst, d)
        elif d > worst:
            worst, worst_pair = d, (name, other)
    return {
        # the two independent measurements of the same body
        "volume_agreement": agreement,
        "methods_agree": 0.95 <= agreement <= 1.05,
        "watertight": holes[0] == holes[1],
        "holes_found": holes[0],
        "holes_filled": holes[1],
        "voxels": grid["voxels"],
        "voxel_m": grid["voxel_m"],
        "unassigned_volume_share": abs(unassigned.vol) / max(voxel_vol, 1e-18),
        "all_masses_positive": not negative,
        "negative_mass_bones": negative,
        "mirror_mismatch": worst,
        "mirror_worst_pair": list(worst_pair) if worst_pair else None,
        "mirror_mismatch_small_bones": small_worst,
        "bones": len(per_bone),
    }


# --------------------------------------------------------------------------
# what the mass model is for: how fast a hanging part wants to swing
# --------------------------------------------------------------------------

G = 9.80665


def pendulum(data, rig, bones, pivot, axis):
    """Natural frequency, in Hz, of `bones` swinging about `axis` through
    `pivot` under gravity - the compound pendulum, w^2 = m g d / I.

    `m` is the summed mass, `d` the lever arm from the axis to the combined
    centre of mass, and `I` the moment about that same axis, each bone's own
    tensor rotated into armature space and carried out to the axis by the
    parallel-axis theorem. All three come from the measurement, so nothing here
    is fitted: the number is a property of the body that was modelled.

    This is what a limb hung on a walking body actually wants to do, and it is
    the quantity `upper.response` needs to say how far behind its drive the
    limb runs. A human arm lands near 0.7-0.9 Hz and a hand near 1.5 Hz, which
    is the check that the tensors and the frames are right way round.

    None when the bones carry no measured mass.
    """
    from mathutils import Matrix, Vector
    a = Vector(axis).normalized()
    pivot = Vector(pivot)
    total, moment, inertia = 0.0, Vector((0.0, 0.0, 0.0)), 0.0
    for name in bones:
        b = data["bones"].get(name)
        if not b:
            continue
        m = b["mass"]
        if m <= 0.0:
            continue
        com = Vector(b["com"])
        total += m
        moment += com * m
        # the bone's own tensor is written in its rest-local frame, where it is
        # a constant; bring it back to armature space before reading an axis off
        basis = rig.data.bones[name].matrix_local.to_3x3()
        t = b["inertia_local"]
        il = Matrix(((t[0], t[1], t[2]), (t[3], t[4], t[5]), (t[6], t[7], t[8])))
        iw = basis @ il @ basis.transposed()
        own = a.dot(iw @ a)
        # parallel axis, out to the line through `pivot` along `a`
        r = com - pivot
        perp = (r - a * r.dot(a)).length
        inertia += own + m * perp * perp
    if total <= 0.0 or inertia <= 0.0:
        return None
    com = moment / total
    r = com - pivot
    d = (r - a * r.dot(a)).length
    if d <= 1e-9:
        return None
    return math.sqrt(total * G * d / inertia) / (2.0 * math.pi)


def body_mass(body):
    """The mass model for a `motion.Body`, measured once and kept on it.

    A character builds several clips off one body and the measurement is a
    property of the body, not of the clip, so it is taken from the rig's stamp
    when there is one and otherwise measured and cached. None when the body
    carries no skinned mass.
    """
    got = body.__dict__.get("_mass_data")
    if got is not None:
        return got or None
    try:
        got = load(body.rig.name) or measure(body.rig.name)
    except Exception:                                           # pragma: no cover
        got = None
    if got is not None and "error" in got:
        got = None
    body.__dict__["_mass_data"] = got or {}
    return got


def angular_momentum(data, body, evaluated, frames, fps, speed):
    """Whole-body angular momentum about the centre of mass, per frame, read
    off a BAKED clip and normalised the way the gait literature normalises it
    (L / M H V - mass, standing height, travel speed).

    Why this is here rather than in a gait module: it is the one measurement
    that can ARBITRATE between two ways of moving. Whole-body angular momentum
    is held in a narrow band about zero through a stride, by the arms
    cancelling the legs; walking with the arms reversed needs almost no
    shoulder torque yet costs 26% more energy, because the cancellation is what
    the arms are for (Collins, Adamczyk & Kuo 2009). So a change that lowers
    the residual is doing what a body does, and one that raises it is not -
    without anyone having to have an opinion about how it looks.

    Each bone contributes its own spin and the orbit of its centre of mass:
    `sum m (p - pc) x (v - vc) + R I R^T w`, velocities by central difference
    around the loop, and the whole thing is frame-invariant because it is taken
    about the COM - which is why an in-place clip measures the same as one that
    travels.

    Returns the up-axis component's range and mean magnitude, or None when the
    body has no measured mass.
    """
    from mathutils import Matrix, Vector

    rest = body.rest
    parts = []
    for name, b in data["bones"].items():
        if b["mass"] <= 0.0 or name not in rest:
            continue
        t = b["inertia_local"]
        parts.append((name, b["mass"], Vector(b["com"]),
                      Matrix(((t[0], t[1], t[2]), (t[3], t[4], t[5]), (t[6], t[7], t[8])))))
    if not parts:
        return None
    # frame `frames + 1` repeats frame 1 to close the loop; leave it out
    seq = [evaluated.get(f) for f in range(1, frames + 1)]
    if any(fr is None for fr in seq) or len(seq) < 3:
        return None

    pos, rot = [], []
    for fr in seq:
        p, r = {}, {}
        for name, m, com, il in parts:
            if name not in fr:
                return None
            p[name] = (fr[name] @ rest[name].inverted()) @ com
            r[name] = fr[name].to_3x3()
        pos.append(p)
        rot.append(r)

    n = len(seq)
    dt = 1.0 / float(fps or 30)
    up = body.bm["up_vec"]
    total = sum(m for _, m, _, _ in parts)
    ups = []
    for i in range(n):
        j, k = (i + 1) % n, (i - 1) % n
        pc, vc = Vector(), Vector()
        for name, m, _c, _i in parts:
            pc += pos[i][name] * m
            vc += ((pos[j][name] - pos[k][name]) / (2.0 * dt)) * m
        pc /= total
        vc /= total
        L = Vector()
        for name, m, _c, il in parts:
            v = (pos[j][name] - pos[k][name]) / (2.0 * dt)
            L += (pos[i][name] - pc).cross((v - vc) * m)
            q = (rot[j][name] @ rot[i][name].inverted()).to_quaternion()
            ang = q.angle
            if ang > math.pi:
                ang -= 2.0 * math.pi
            if abs(ang) > 1e-12:
                L += (rot[i][name] @ il @ rot[i][name].transposed()) @ (q.axis * (ang / dt))
        ups.append(L.dot(up))
    norm = total * max(body.bm["height"], 1e-6) * max(speed, 1e-6)
    ups = [u / norm for u in ups]
    return {"up_range": round(max(ups) - min(ups), 5),
            "up_mean_abs": round(sum(abs(u) for u in ups) / len(ups), 5)}


# --------------------------------------------------------------------------
# stamping, so a later session need not remeasure
# --------------------------------------------------------------------------

def stamp(rig_name, **kwargs):
    """Measure and write the result onto the armature as a custom property."""
    import bpy
    r = measure(rig_name, **kwargs)
    if "error" in r:
        return r
    bpy.data.objects[rig_name][STAMP_KEY] = json.dumps(r)
    return r


def load(rig_name):
    """The stamped measurement, or None."""
    import bpy
    rig = bpy.data.objects.get(rig_name)
    if rig is None:
        return None
    raw = rig.get(STAMP_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def com_terms(data):
    """`motion.Body.com_terms` built from a real mass model.

    Same shape as `motion._com_terms` - {bone: (first moment, mass)} - and the
    same affine-in-each-bone-matrix property, so it drops straight in, but the
    weights are volume rather than vertex count.
    """
    from mathutils import Vector
    return {name: (Vector(b["com"]) * b["mass"], b["mass"])
            for name, b in data["bones"].items()}


def summarize(data, top=12):
    """A short text report: the heaviest bones and the checks."""
    if "error" in data:
        return "ERROR: " + data["error"]
    c = data["checks"]
    lines = ["MASS  %s   %.2f kg over %.5f m^3 at %.0f kg/m^3"
             % (data["rig"], data["total_mass"], data["total_volume"], data["density"]),
             "  com         %.3f %.3f %.3f" % tuple(data["com"]),
             "  bones       %d" % c["bones"],
             "  voxels      %d at %.1f mm" % (c["voxels"], 1000.0 * c["voxel_m"]),
             "  watertight  %s (%d holes found, %d closed)"
             % ("yes" if c["watertight"] else "NO", c["holes_found"], c["holes_filled"]),
             "  methods     %s (voxel/surface volume %.4f)"
             % ("agree" if c["methods_agree"] else "DISAGREE", c["volume_agreement"]),
             "  mirror      %.2f%% worst on a bone that matters%s"
             % (100.0 * c["mirror_mismatch"],
                "" if not c["mirror_worst_pair"] else
                "  (%s vs %s)" % tuple(c["mirror_worst_pair"])),
             "              %.2f%% worst on bones under %.1f%% of the body"
             % (100.0 * c["mirror_mismatch_small_bones"], 100.0 * MIRROR_MIN_SHARE),
             "  unassigned  %.4f%%" % (100.0 * c["unassigned_volume_share"])]
    ranked = sorted(data["bones"].items(), key=lambda kv: -kv[1]["mass"])
    lines.append("")
    lines.append("  heaviest")
    for name, b in ranked[:top]:
        lines.append("    %-28s %7.3f kg  %5.1f%%"
                     % (name, b["mass"], 100.0 * b["mass"] / data["total_mass"]))
    for w in data["warnings"]:
        lines.append("  warn  " + w)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# self-test: shapes whose mass properties are known in closed form
# --------------------------------------------------------------------------

def _box_tris(sx, sy, sz, origin=(0.0, 0.0, 0.0)):
    """A closed, outward-wound box from `origin` to origin + (sx, sy, sz)."""
    x0, y0, z0 = origin
    x1, y1, z1 = x0 + sx, y0 + sy, z0 + sz
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    tris = []
    for a, b, c, d in quads:
        tris.append((v[a], v[b], v[c]))
        tris.append((v[a], v[c], v[d]))
    return tris


def _sphere_tris(r, rings=64, segments=128):
    """A closed UV sphere, outward wound."""
    tris = []

    def p(i, j):
        phi = math.pi * i / rings
        th = 2.0 * math.pi * j / segments
        return (r * math.sin(phi) * math.cos(th),
                r * math.sin(phi) * math.sin(th),
                r * math.cos(phi))
    for i in range(rings):
        for j in range(segments):
            a, b, c, d = p(i, j), p(i, j + 1), p(i + 1, j + 1), p(i + 1, j)
            if i:
                tris.append((a, c, b))
            if i + 1 < rings:
                tris.append((a, d, c))
    return tris


def selftest(verbose=True):
    """Check the integrals against shapes with analytic mass properties.

    Runs without Blender. A box and a sphere pin down volume, centre and all
    three principal moments; an off-centre box pins the parallel-axis term;
    voxels of a box pin `add_voxel` against the same closed form; and a box
    split between two bones pins what the partition must do.
    """
    results = []

    def close(got, want, tol, what):
        results.append((abs(got - want) <= tol * max(abs(want), 1e-12),
                        what, got, want))

    # --- box, analytic: V = sxsysz, I_xx = m(sy^2 + sz^2)/12 -----------------
    sx, sy, sz, rho = 0.4, 0.7, 1.9, DEFAULT_DENSITY
    acc = Accum()
    for a, b, c in _box_tris(sx, sy, sz, origin=(3.0, -2.0, 5.0)):
        acc.add_tet(a, b, c)
    m = acc.vol * rho
    close(acc.vol, sx * sy * sz, 1e-12, "box volume")
    ctr = acc.centre()
    close(ctr[0], 3.0 + sx / 2.0, 1e-12, "box com x (off origin)")
    close(ctr[2], 5.0 + sz / 2.0, 1e-12, "box com z (off origin)")
    I = acc.inertia_about_centre(rho)
    close(I[0], m * (sy * sy + sz * sz) / 12.0, 1e-9, "box I_xx")
    close(I[4], m * (sx * sx + sz * sz) / 12.0, 1e-9, "box I_yy")
    close(I[8], m * (sx * sx + sy * sy) / 12.0, 1e-9, "box I_zz")
    results.append((abs(I[1]) < 1e-9 * I[0], "box I_xy (zero by symmetry)", I[1], 0.0))

    # --- sphere, analytic: I = 2/5 m r^2 -------------------------------------
    r = 0.83
    acc = Accum()
    for a, b, c in _sphere_tris(r):
        acc.add_tet(a, b, c)
    m = acc.vol * rho
    close(acc.vol, 4.0 / 3.0 * math.pi * r ** 3, 2e-3, "sphere volume (tessellated)")
    I = acc.inertia_about_centre(rho)
    close(I[0], 0.4 * m * r * r, 3e-3, "sphere I_xx")
    close(I[8], 0.4 * m * r * r, 3e-3, "sphere I_zz")

    # --- voxels reproduce the same box ---------------------------------------
    n, s = 40, 1.0
    h = s / n
    vol, sm = h ** 3, h ** 5 / 12.0
    vac = Accum()
    for i in range(n):
        for j in range(n):
            for k in range(n):
                vac.add_voxel(((i + 0.5) * h, (j + 0.5) * h, (k + 0.5) * h), vol, sm)
    close(vac.vol, s ** 3, 1e-12, "voxel box volume")
    close(vac.centre()[0], s / 2.0, 1e-12, "voxel box com")
    Iv = vac.inertia_about_centre(rho)
    close(Iv[0], (vac.vol * rho) * (s * s + s * s) / 12.0, 1e-9,
          "voxel box I_xx (self-moment included)")

    # --- winding: a reversed surface reports negative volume, not garbage ----
    rev = Accum()
    for a, b, c in _box_tris(1.0, 1.0, 1.0):
        rev.add_tet(a, c, b)
    close(rev.vol, -1.0, 1e-12, "reversed winding gives negative volume")

    # --- the partition a voxel split must produce ---------------------------
    left, right = Accum(), Accum()
    for i in range(n):
        for j in range(n):
            for k in range(n):
                c = ((i + 0.5) * h, (j + 0.5) * h, (k + 0.5) * h)
                (left if c[0] < 0.5 else right).add_voxel(c, vol, sm)
    close(left.vol + right.vol, s ** 3, 1e-12, "split halves sum to the whole")
    close(left.vol, 0.5 * s ** 3, 1e-12, "split is even")
    close(left.centre()[0], 0.25, 1e-9, "split half sits at its own centre")

    passed = sum(1 for ok, *_ in results if ok)
    if verbose:
        for ok, what, got, want in results:
            print("  %s  %-42s got %-14.8g want %.8g"
                  % ("ok  " if ok else "FAIL", what, got, want))
        print("  %d/%d passed" % (passed, len(results)))
    return {"passed": passed, "total": len(results),
            "ok": passed == len(results),
            "failures": [w for ok, w, _, _ in results if not ok]}


if __name__ == "__main__":
    selftest()
