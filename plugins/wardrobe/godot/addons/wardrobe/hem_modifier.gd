extends SkeletonModifier3D
## Hems and cuffs that swing: one sprung bone per section of an opening, after the animation.
##
## Blender's hem.prepare hangs a ring of bones around each opening of a garment - parented to
## the torso for a hem, the upper arm for a cuff - and weights the fabric between hinge and edge
## to them. Each frame, each bone's tail is a point on a damped spring whose rest is where the
## animated parent puts it; the bone turns to aim at the sprung tail. A stride's jolt, a turn and
## a stop carry through and settle.
##
## Two limits keep the fabric where it belongs:
##   max_offset_m   the swing, from the bone's length and a maximum angle
##   inward_m       a backstop: how far the tail may move toward the skin it hung over at rest
##                  (the rest gap less a margin), along the direction to that skin, carried in
##                  the parent's frame so it turns with the body
##
## A skirt or dress (hem bones hung from the pelvis, hinged above the hip joints) also carries
## `colliders`: capsules round the thighs and shins, in those bones' frames, and after the spring
## _collide_ring places the whole ring:
##   fold      what the thighs under a bone do (at the front the lesser swing toward it, at the side
##             the nearer thigh's, in the pelvis's frame) turns its head and tail about the hip line:
##             in a crouch the front of the skirt lies on the thighs as their skin would carry it
##   swing     each bone with a test point (COLLIDE_AT along it) inside a capsule, less its
##             `collider_slack_m` (how far inside it was at rest), swings outward about its head by
##             the least angle that clears it; its neighbours follow to within SPREAD_DEG, and the
##             cloth between two neighbours is lifted clear too: a lifted thigh lifts the front of the
##             skirt over it, as dynamic bones with leg colliders do in Unity and Unreal
## Neither is a spring offset: not limited by max_offset_m, not fed back, so the cloth falls as soon
## as the thigh leaves. `colliders = false` (an equip option) turns both off: the control.
##
## Integration is the exact damped oscillator (as follow-through's jiggle modifier): stable at
## any frame rate and frequency, so a frequency means Hz.

var spec: Dictionary
var report: Dictionary = {}
var bones: Array[Dictionary] = []
var paused := false
var response_scale := 1.0
var garment: MeshInstance3D
var colliders: Array[Dictionary] = []   # {bone, head_local, tail_local, radii}
var collide := true
var _neighbours: Array = []
var thighs: Array[Dictionary] = []      # {bone, rest_dir, rest_head}: skeleton space, at rest
var hip_centre := Vector3.ZERO          # between the thighs' heads, skeleton space, at rest

# stats, since the last reset_stats()
var peak_offset_m := 0.0
var backstop_hits := 0
var collider_pushes := 0
var peak_push_m := 0.0
var usec_total := 0
var frames := 0

const COLLIDE_AT: Array[float] = [0.125, 0.25, 0.5, 0.75, 1.0]   # hem.py's COLLIDE_AT
const SWING_STEP_DEG := 10.0         # the search for the least swing steps this far, then halves
const MAX_SWING_DEG := 110.0         # from hanging, the fold included: at 120 a crouch stood the front up
const SPREAD_DEG := 30.0             # a neighbour swings at most this much less
const SHARED_FOLD := 1.0             # of the thighs' shared forward swing

const TELEPORT_M := 1.0
const MAX_ACCEL := 400.0


static func build(skel: Skeleton3D, garment_mesh: MeshInstance3D, s: Dictionary, options := {}):
	var mod = new()
	mod.spec = s
	mod.garment = garment_mesh
	mod.name = String(garment_mesh.name) + "_hem"
	mod.set_meta("wardrobe_hem_for", garment_mesh)
	skel.add_child(mod)
	mod._setup(skel, options)
	return mod


func _setup(skel: Skeleton3D, options: Dictionary) -> void:
	var overrides: Dictionary = options.get("overrides", {})
	var problems := PackedStringArray()
	var worst_head := 0.0
	for b in spec["hem"]["bones"]:
		var bone := skel.find_bone(String(b["name"]))
		var parent := skel.find_bone(String(b["parent"]))
		if bone < 0:
			problems.append("hem bone %s not in the skeleton" % b["name"])
			continue
		if parent < 0:
			parent = skel.get_bone_parent(bone)
		var p: Dictionary = b.duplicate()
		for k in overrides:
			p[k] = overrides[k]
		var rest_global := skel.get_bone_global_rest(bone)
		var head := _vec(b["head"])
		var tail := _vec(b["tail"])
		worst_head = maxf(worst_head, rest_global.origin.distance_to(head))
		var parent_rest := skel.get_bone_global_rest(parent) if parent >= 0 else Transform3D.IDENTITY
		var tail_local := rest_global.affine_inverse() * tail
		bones.append({
			"name": String(b["name"]), "ring": String(b.get("ring", "")),
			"bone": bone, "parent": parent, "rest": skel.get_bone_rest(bone),
			"tail_local": tail_local, "length": maxf(tail_local.length(), 0.005),
			"inward_local": (parent_rest.basis.inverse() * _vec(b["inward_dir"])).normalized(),
			"inward_m": float(p.get("inward_m", 0.02)),
			"max_offset": float(p.get("max_offset_m", 0.08)),
			"frequency_hz": float(p.get("frequency_hz", 1.8)),
			"damping_ratio": float(p.get("damping_ratio", 0.3)),
			"response": float(p.get("response", 1.0)),
			"gravity_scale": float(p.get("gravity_scale", 1.0)),
			"e": Vector3.ZERO, "u": Vector3.ZERO, "target": Vector3.ZERO, "target_v": Vector3.ZERO,
			"started": false, "g_rest_local": Vector3.ZERO, "offset": Vector3.ZERO,
			"slack": PackedFloat32Array(b.get("collider_slack_m", [])),
			"out_local": (parent_rest.basis.inverse() * _vec(b.get("outward_dir", b["inward_dir"]))).normalized() \
				* (1.0 if b.has("outward_dir") else -1.0),
		})
	if worst_head > 0.01:
		problems.append("hem bone heads are %.3f m from the spec: wrong skeleton or space" % worst_head)
	collide = bool(options.get("colliders", true))
	for c in spec["hem"].get("colliders", []):
		var cb := skel.find_bone(String(c["bone"]))
		if cb < 0:
			problems.append("hem collider bone %s not in the skeleton" % c["bone"])
			continue
		var inv := skel.get_bone_global_rest(cb).affine_inverse()
		colliders.append({"bone": cb, "head_local": inv * _vec(c["head"]), "tail_local": inv * _vec(c["tail"]),
			"radii": PackedFloat32Array(c["radii_m"])})
	# the thighs: collider bones whose parent is not a collider bone (a shin's is its thigh)
	var cbones := {}
	for c in colliders:
		cbones[c["bone"]] = true
	for cb in cbones:
		if not cbones.has(skel.get_bone_parent(cb)):
			thighs.append({"bone": cb, "rest_dir": skel.get_bone_global_rest(cb).basis.y.normalized(),
				"rest_head": skel.get_bone_global_rest(cb).origin})
			hip_centre += skel.get_bone_global_rest(cb).origin
	if not thighs.is_empty():
		hip_centre /= thighs.size()
	report = {"built": not bones.is_empty(), "bones": bones.size(), "head_error_m": snappedf(worst_head, 0.0001),
		"colliders": colliders.size(), "problems": problems}


static func _vec(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))


func _gravity() -> Vector3:
	var g: float = ProjectSettings.get_setting("physics/3d/default_gravity", 9.8)
	var gv: Vector3 = ProjectSettings.get_setting("physics/3d/default_gravity_vector", Vector3.DOWN)
	return gv * g


func reset_stats() -> void:
	peak_offset_m = 0.0
	backstop_hits = 0
	collider_pushes = 0
	peak_push_m = 0.0
	usec_total = 0
	frames = 0


func _process_modification_with_delta(delta: float) -> void:
	var skel := get_skeleton()
	if skel == null or delta <= 0.0:
		return
	var t0 := Time.get_ticks_usec()
	var skel_xf := skel.global_transform
	var g := _gravity()
	var caps := []                     # world [head, tail, radii]
	if collide:
		for c in colliders:
			var cx := skel_xf * skel.get_bone_global_pose(c["bone"])
			caps.append([cx * (c["head_local"] as Vector3), cx * (c["tail_local"] as Vector3), c["radii"]])
	for b in bones:
		var parent: int = b["parent"]
		var parent_pose := skel.get_bone_global_pose(parent) if parent >= 0 else Transform3D.IDENTITY
		var frame := skel_xf * (parent_pose * (b["rest"] as Transform3D))
		var target := frame * (b["tail_local"] as Vector3)
		var parent_basis := skel_xf.basis * parent_pose.basis
		if not b["started"] or target.distance_to(b["target"]) > TELEPORT_M:
			b["target"] = target
			b["target_v"] = Vector3.ZERO
			b["e"] = Vector3.ZERO
			b["u"] = Vector3.ZERO
			b["g_rest_local"] = parent_basis.inverse() * g
			b["started"] = true
		var vt: Vector3 = (target - b["target"]) / delta
		var at: Vector3 = (vt - b["target_v"]) / delta
		if at.length() > MAX_ACCEL:
			at = at.normalized() * MAX_ACCEL
		b["target"] = target
		b["target_v"] = vt
		var g_rest_world: Vector3 = parent_basis * (b["g_rest_local"] as Vector3)
		var push: Vector3 = (g - g_rest_world) * float(b["gravity_scale"]) - at * float(b["response"]) * response_scale
		var next := spring_step(b["e"], b["u"], TAU * float(b["frequency_hz"]), float(b["damping_ratio"]), delta, push)
		var e: Vector3 = next[0]
		var u: Vector3 = next[1]
		var limit := float(b["max_offset"])
		if e.length() > limit:
			var n := e.normalized()
			e = n * limit
			var out := u.dot(n)
			if out > 0.0:
				u -= n * out
		# backstop: not further toward the skin than the rest gap allows
		var inward: Vector3 = (parent_basis * (b["inward_local"] as Vector3)).normalized()
		var depth := e.dot(inward)
		if depth > float(b["inward_m"]):
			e -= inward * (depth - float(b["inward_m"]))
			var into := u.dot(inward)
			if into > 0.0:
				u -= inward * into
			backstop_hits += 1
		b["e"] = e
		b["u"] = u
		if paused:
			e = Vector3.ZERO
		b["offset"] = e
		peak_offset_m = maxf(peak_offset_m, e.length())
		if caps.is_empty():
			_aim(skel, b, frame, e)
		else:
			b["frame"] = frame
			b["out"] = (parent_basis * (b["out_local"] as Vector3)).normalized()
	if not caps.is_empty():
		_collide_ring(skel, caps)
	usec_total += Time.get_ticks_usec() - t0
	frames += 1


## Swing the bones out of the colliders, as a ring. Every swing is outward, about the bone's head toward its
## `out` (level, away from the body's axis): swung round a thigh instead - along the capsule's normal, or
## the way the thigh runs - two neighbours parted or crossed, and the thigh showed between them. Each bone
## with a test point inside a capsule swings by the least angle that clears it (to 1 degree, at most
## MAX_SWING_DEG); its neighbours on the ring are raised to within SPREAD_DEG of it, both ways round; and
## while the cloth between two neighbours (their mean at each test point) is inside a capsule both swing on
## by 3 degrees, as long as that takes it less far inside. Spreading and the cloth between are repeated until nothing more is raised (4 rounds).
func _collide_ring(skel: Skeleton3D, caps: Array) -> void:
	var n := bones.size()
	var heads: Array[Vector3] = []
	var vs: Array[Vector3] = []
	var axes: Array[Vector3] = []
	var tops := PackedFloat32Array()
	var phis := PackedFloat32Array()
	phis.resize(n)
	for i in n:
		var b: Dictionary = bones[i]
		var frame: Transform3D = b["frame"]
		var head := frame.origin
		var v := frame * (b["tail_local"] as Vector3) + (b["offset"] as Vector3) - head
		# what the thighs do together carries the cloth as skin weights would: a crouch or a sit lifts the front
		var folded := _shared_fold(skel, b, head, v)
		heads.append(folded[0])
		vs.append(folded[1])
		# the swing turns about the level line across the bone (its hanging direction x out), whatever v is:
		# turned toward `out` from v itself, a bone the fold had already brought level went over the top
		var hang := frame * (b["tail_local"] as Vector3) - frame.origin
		var axis := hang.cross(b["out"])
		axes.append(axis.normalized() if axis.length() > 1e-6 else Vector3.ZERO)
		tops.append(maxf(deg_to_rad(MAX_SWING_DEG - float(b["fold_deg"])), 0.0))
		if _first_inside(heads[i], heads[i] + vs[i], caps, b["slack"]) >= 0:
			phis[i] = _least_angle(heads[i], vs[i], axes[i], caps, b["slack"], tops[i])
	var nb: Array = _ring_neighbours()
	var spread := deg_to_rad(SPREAD_DEG)
	var step := deg_to_rad(3.0)
	for _round in 4:
		for _pass in 2:
			for sweep in 2:
				for k in n:
					var i := k if sweep == 0 else n - 1 - k
					for j: int in nb[i]:
						phis[i] = minf(maxf(phis[i], phis[j] - spread), tops[i])
		var raised := false
		for i in n:
			if nb[i].is_empty():
				continue
			var j: int = nb[i][0]
			var depth := _between(heads, vs, axes, caps, bones[i]["slack"], i, j, phis[i], phis[j])
			for _it in 12:
				if depth <= 0.0 or (phis[i] >= tops[i] and phis[j] >= tops[j]):
					break
				var pi2 := minf(phis[i] + step, tops[i])
				var pj2 := minf(phis[j] + step, tops[j])
				var d2 := _between(heads, vs, axes, caps, bones[i]["slack"], i, j, pi2, pj2)
				if d2 >= depth:
					break                  # swinging on does not get the cloth out (a crouch): leave it
				phis[i] = pi2
				phis[j] = pj2
				depth = d2
				raised = true
		if not raised:
			break
	for i in n:
		var b: Dictionary = bones[i]
		var frame: Transform3D = b["frame"]
		var sprung: Vector3 = frame * (b["tail_local"] as Vector3) + (b["offset"] as Vector3)
		var moved := Transform3D(frame.basis, heads[i])
		var tail := heads[i] + _swing(vs[i], axes[i], phis[i])
		if tail.distance_to(sprung) > 1e-5:
			collider_pushes += 1
			peak_push_m = maxf(peak_push_m, tail.distance_to(sprung))
		b["swing_deg"] = rad_to_deg(phis[i])
		# the head where the fold carried it, in the parent's frame, then the bone aimed at the tail
		var parent: int = b["parent"]
		var parent_world := skel.global_transform * (skel.get_bone_global_pose(parent) if parent >= 0 else Transform3D.IDENTITY)
		skel.set_bone_pose_position(b["bone"], parent_world.affine_inverse() * heads[i])
		_aim(skel, b, moved, tail - moved * (b["tail_local"] as Vector3))


## How far the cloth between two neighbouring bones (their mean at each test point, below a quarter of the
## way down - at the hinge it is on the hip) is inside the capsules.
static func _between(heads: Array[Vector3], vs: Array[Vector3], axes: Array[Vector3], caps: Array,
		slack: PackedFloat32Array, i: int, j: int, phi_i: float, phi_j: float) -> float:
	return _depth((heads[i] + heads[j]) * 0.5,
		(heads[i] + _swing(vs[i], axes[i], phi_i) + heads[j] + _swing(vs[j], axes[j], phi_j)) * 0.5,
		caps, slack, 0.25)


## The bone's head and sprung direction v, [head, v], carried by what the thighs do under it: each thigh's
## swing toward the bone's `out` from rest (in the plane of down and out, in the parent's rest frame) - at
## the front the lesser of the two, at the side the nearer thigh's, between the two by how far to the side
## the bone faces; never below 0 - turns head and tail about the level line across `out` through the hip
## joints (the nearer one at a side), as skin on the thighs turns. In a crouch both thighs come up in front
## and the front of the skirt comes with them and lies on them; spread in a wide squat, each carries its
## side. Hinged at the pelvis alone a thigh folded up above the hinge had no swing that cleared it. The
## back of a thigh never swings back toward a bone at the back in a crouch, so the back of the skirt hangs
## from the pelvis as it tips (turned forward with the front, it went into the buttocks). In a stride one
## thigh comes forward and one goes back, the front shares nothing, and the colliders alone keep the forward
## thigh under the cloth.
func _shared_fold(skel: Skeleton3D, b: Dictionary, head: Vector3, v: Vector3) -> Array:
	b["fold_deg"] = 0.0
	if thighs.is_empty():
		return [head, v]
	var parent: int = b["parent"]
	var pose := skel.get_bone_global_pose(parent) if parent >= 0 else Transform3D.IDENTITY
	var rest := skel.get_bone_global_rest(parent) if parent >= 0 else Transform3D.IDENTITY
	var out: Vector3 = (rest.basis * (b["out_local"] as Vector3)).normalized()
	var least := INF
	var near := 0.0
	var near_head := hip_centre
	var best_side := -INF
	for t in thighs:
		# the thigh now, carried back into the parent's rest frame
		var now: Vector3 = rest.basis * (pose.basis.inverse() * skel.get_bone_global_pose(t["bone"]).basis.y.normalized())
		var was: Vector3 = t["rest_dir"]
		# how far the thigh's tail has moved toward `out`, as the angle a turn about the level line across
		# `out` would need: stable when the thigh swings in another plane (an angle in the down-out plane
		# ran to 132 degrees for a bone at the side of a thigh swung forward)
		var swing := asin(clampf((now - was).dot(out), -1.0, 1.0))
		least = minf(least, swing)
		var side := ((t["rest_head"] as Vector3) - hip_centre).dot(out)
		if side > best_side:
			best_side = side
			near = swing
			near_head = t["rest_head"]
	var lateral := absf(out.x)
	var fold := maxf(lerpf(least, near, lateral), 0.0) * SHARED_FOLD
	if fold <= 0.0:
		return [head, v]
	b["fold_deg"] = rad_to_deg(fold)
	var pivot := hip_centre.lerp(near_head, lateral)
	var axis := Vector3.DOWN.cross(out)
	if axis.length() < 1e-6:
		return [head, v]
	var turn := Basis(axis.normalized(), fold)
	var to_world := skel.global_transform * pose * rest.affine_inverse()      # parent-rest skeleton space -> world
	var from_world := to_world.affine_inverse()
	var h := to_world * (pivot + turn * (from_world * head - pivot))
	var t2 := to_world * (pivot + turn * (from_world * (head + v) - pivot))
	return [h, t2 - h]


## For each bone, the next and the previous bone of the same ring, round it (none on a ring of two or less).
func _ring_neighbours() -> Array:
	if not _neighbours.is_empty():
		return _neighbours
	for i in bones.size():
		var same: Array[int] = []
		for j in bones.size():
			if String(bones[j]["ring"]) == String(bones[i]["ring"]):
				same.append(j)
		var k := same.find(i)
		_neighbours.append([same[(k + 1) % same.size()], same[(k - 1 + same.size()) % same.size()]] if same.size() > 2 else [])
	return _neighbours


static func _swing(v: Vector3, axis: Vector3, phi: float) -> Vector3:
	if phi <= 0.0 or axis == Vector3.ZERO:
		return v
	return v.rotated(axis, phi)


## The least swing of v (from head) toward dir that leaves every test point outside every capsule.
static func _least_angle(head: Vector3, v: Vector3, axis: Vector3, caps: Array, slack: PackedFloat32Array, top: float) -> float:
	var phi := _clearing_angle(head, v, axis, caps, slack, 0.0, top)
	if phi < 0.0:
		# nothing clears it all (a thigh folded up against the hips in a crouch): the least swing that clears
		# the lower half, so the cloth lies along the thigh instead of standing up off it
		phi = _clearing_angle(head, v, axis, caps, slack, 0.5, top)
	return phi if phi >= 0.0 else 0.0


## The least swing (to 1 degree, at most `top`) that leaves the test points from `from_f` down outside
## every capsule, or -1.
static func _clearing_angle(head: Vector3, v: Vector3, axis: Vector3, caps: Array, slack: PackedFloat32Array,
		from_f: float, top: float) -> float:
	var lo := 0.0
	var step := deg_to_rad(SWING_STEP_DEG)
	var phi := step
	while phi <= top + 1e-6:
		if _depth(head, head + _swing(v, axis, phi), caps, slack, from_f) <= 0.0:
			var hi := phi
			while hi - lo > deg_to_rad(1.0):
				var mid := (lo + hi) * 0.5
				if _depth(head, head + _swing(v, axis, mid), caps, slack, from_f) > 0.0:
					lo = mid
				else:
					hi = mid
			return hi
		lo = phi
		phi += step
	return -1.0



## How far the test points of the bone head -> tail (from `from_f` along it) are inside the capsules (less the
## bone's slack), summed.
static func _depth(head: Vector3, tail: Vector3, caps: Array, slack: PackedFloat32Array, from_f := 0.0) -> float:
	var total := 0.0
	for ci in caps.size():
		var c: Array = caps[ci]
		var a: Vector3 = c[0]
		var ab: Vector3 = (c[1] as Vector3) - a
		var l2 := maxf(ab.length_squared(), 1e-9)
		var sl := slack[ci] if ci < slack.size() else 0.0
		for f: float in COLLIDE_AT:
			if f < from_f:
				continue
			var p := head + (tail - head) * f
			var s := clampf((p - a).dot(ab) / l2, 0.0, 1.0)
			total += maxf(radius_at(c[2], s) - sl - p.distance_to(a + ab * s), 0.0)
	return total


## The first capsule with a test point of the bone head -> tail inside it (less the bone's slack), or -1.
static func _first_inside(head: Vector3, tail: Vector3, caps: Array, slack: PackedFloat32Array) -> int:
	for ci in caps.size():
		var c: Array = caps[ci]
		var a: Vector3 = c[0]
		var ab: Vector3 = (c[1] as Vector3) - a
		var l2 := maxf(ab.length_squared(), 1e-9)
		var sl := slack[ci] if ci < slack.size() else 0.0
		for f: float in COLLIDE_AT:
			var p := head + (tail - head) * f
			var s := clampf((p - a).dot(ab) / l2, 0.0, 1.0)
			if p.distance_to(a + ab * s) < radius_at(c[2], s) - sl:
				return ci
	return -1


## A collider's radius at s (0 head, 1 tail), linear between its knots (as hem.py's radius_at).
static func radius_at(radii: PackedFloat32Array, s: float) -> float:
	if radii.size() == 1:
		return radii[0]
	var x := clampf(s, 0.0, 1.0) * (radii.size() - 1)
	var k := mini(int(x), radii.size() - 2)
	return lerpf(radii[k], radii[k + 1], x - k)


func _aim(skel: Skeleton3D, b: Dictionary, frame: Transform3D, e: Vector3) -> void:
	var from: Vector3 = b["tail_local"]
	var to := frame.affine_inverse() * (frame * from + e)
	var q := Quaternion.IDENTITY
	if from.length() > 1e-6 and to.length() > 1e-6:
		q = Quaternion(from.normalized(), to.normalized())
	var rest: Transform3D = b["rest"]
	skel.set_bone_pose_rotation(b["bone"], rest.basis.get_rotation_quaternion() * q)


## One exact step of x'' = -w^2 x - 2 z w x' + push, over dt. Returns [x, x'].
## (The same closed form as follow-through's jiggle_modifier.gd.)
static func spring_step(x: Vector3, v: Vector3, w: float, z: float, dt: float, push: Vector3) -> Array:
	var eq := push / (w * w)
	var x0 := x - eq
	var xn: Vector3
	var vn: Vector3
	if z < 0.999:
		var wd := w * sqrt(1.0 - z * z)
		var ex := exp(-z * w * dt)
		var c := cos(wd * dt)
		var s := sin(wd * dt)
		xn = (x0 * c + (v + x0 * (z * w)) * (s / wd)) * ex
		vn = (v * c - (v * (z * w) + x0 * (w * w)) * (s / wd)) * ex
	elif z <= 1.001:
		var ex := exp(-w * dt)
		xn = (x0 + (v + x0 * w) * dt) * ex
		vn = (v - (v + x0 * w) * (w * dt)) * ex
	else:
		var r := w * sqrt(z * z - 1.0)
		var r1 := -z * w + r
		var r2 := -z * w - r
		var c2 := (x0 * r1 - v) / (r1 - r2)
		var c1 := x0 - c2
		xn = c1 * exp(r1 * dt) + c2 * exp(r2 * dt)
		vn = c1 * (r1 * exp(r1 * dt)) + c2 * (r2 * exp(r2 * dt))
	return [xn + eq, vn]


## Knock every bone: an instant velocity change, world m/s.
func kick(velocity: Vector3) -> void:
	for b in bones:
		b["u"] = (b["u"] as Vector3) - velocity


func stats() -> Dictionary:
	return {"bones": bones.size(), "peak_offset_m": snappedf(peak_offset_m, 0.0001), "backstop_hits": backstop_hits,
		"colliders": colliders.size() if collide else 0, "collider_pushes": collider_pushes,
		"peak_push_m": snappedf(peak_push_m, 0.0001),
		"usec_per_frame": snappedf(float(usec_total) / maxf(frames, 1), 0.1), "frames": frames}
