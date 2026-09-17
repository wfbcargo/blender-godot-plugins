extends SkeletonModifier3D
## Strands that follow through: ponytails and locks of long hair as sprung bone chains.
##
## Blender's strand.prepare hangs a chain of bones along a strand's centreline, parented to the
## bone it grows from, and weights the mesh along it. This modifier springs every chain after the
## animation, root to tip: each bone's tail is a point on a damped spring whose rest is where its
## parent - animated for the first bone, already sprung for the rest - puts it, so a swing at the
## root travels down the chain.
##
## The simulation runs in fixed steps of 1/120 s, as many as fit in each frame (at most MAX_STEPS, so
## a stalled frame drops time rather than spiralling), with the animated parent and the colliders
## interpolated to each step's moment, so 30 fps and 240 fps swing the same. Per bone, per substep, in order:
##   spring      the exact damped oscillator over the frame (as jiggle_modifier.gd and wardrobe's
##               hem), loaded by the target's acceleration and the change of gravity in the parent's
##               frame. Stable at any frame rate and frequency, so a frequency means Hz.
##   length      the tail is put back on the bone's length: a strand swings, it does not stretch
##   angle       no further than max_angle_deg from where the parent points it
##   collision   four points along the bone kept out of an ellipsoid round the head and capsules round
##               the neck bones (grown by the strand's own radius and a margin). Where the strand sits closer than
##               that at rest - its root grows out of the scalp - the rest gap is the limit, so
##               nothing is pushed out at rest and nothing goes deeper than it started.
## Velocity into a limit or a collider is removed, velocity along the bone always is.
##
## Every assumption is checked at build time and written to `report`: each bone exists and its
## rest head is where Blender put it.

var spec: Dictionary
var report: Dictionary = {}
var chains: Array[Dictionary] = []
var colliders: Array[Dictionary] = []
var paused := false                 # hold every bone at rest
var response_scale := 1.0           # multiplies every bone's response to the body's motion, live

# stats, since the last reset_stats()
var peak_angle_deg := 0.0
var limit_hits := 0
var collision_hits := 0
var nonfinite := 0
var usec_total := 0
var frames := 0
var peak_steps := 0
var dropped_steps := 0
var _caps_prev: Array = []
var _left := 0.0                    # time since the last step, carried between frames

const TELEPORT_M := 1.0
const MAX_ACCEL := 400.0
const PASSES := 2                   # collision passes over every collider per bone
const STEP := 1.0 / 120.0           # the simulation's fixed step; a frame takes as many as fit in it
const MAX_STEPS := 16               # the most one frame may simulate: a stall drops time, never spirals
const SAMPLES := [0.25, 0.5, 0.75, 1.0]   # points along each bone kept out of the colliders


static func build(mesh: MeshInstance3D, s: Dictionary, options := {}):
	var skel := mesh.get_node_or_null(mesh.skeleton) as Skeleton3D
	var mod = new()
	mod.spec = s
	mod.name = String(mesh.name) + "_strands"
	if skel == null:
		mod.report = {"built": false, "problems": PackedStringArray(["%s has no skeleton" % mesh.name])}
		return mod
	skel.add_child(mod)
	mod._setup(skel, options)
	return mod


func _setup(skel: Skeleton3D, options: Dictionary) -> void:
	var overrides: Dictionary = options.get("overrides", {})
	var blk: Dictionary = spec["strands"]
	var problems := PackedStringArray()
	var margin := float(overrides.get("collision_margin_m", blk.get("collision_margin_m", 0.004)))
	for c in blk.get("colliders", []):
		var cb := _find(skel, String(c["bone"]))
		if cb < 0:
			problems.append("collider bone %s not in the skeleton" % c["bone"])
			continue
		var inv := skel.get_bone_global_rest(cb).affine_inverse()
		var col := {"name": String(c["name"]), "bone": cb, "a_local": inv * _vec(c["a"]),
			"b_local": inv * _vec(c["b"]), "radius": float(c.get("radius_m", 0.0)),
			"a_rest": _vec(c["a"]), "b_rest": _vec(c["b"]), "ellipsoid": String(c.get("shape", "capsule")) == "ellipsoid"}
		if col["ellipsoid"]:
			var axes: Array = c["axes"]
			col["basis_rest"] = Basis(_vec(axes[0]), _vec(axes[1]), _vec(axes[2]))
			col["basis_local"] = inv.basis * col["basis_rest"]
			col["radii"] = _vec(c["radii_m"])
		col["bound"] = maxf(col["radius"], (col["radii"] as Vector3)[(col["radii"] as Vector3).max_axis_index()]) if col["ellipsoid"] else col["radius"]
		colliders.append(col)
	var worst_head := 0.0
	var count := 0
	for ch in blk["chains"]:
		var bones: Array[Dictionary] = []
		for b in ch["bones"]:
			var bone := _find(skel, String(b["bone"]))
			if bone < 0:
				problems.append("strand bone %s not in the skeleton" % b["bone"])
				continue
			var parent := _find(skel, String(b["parent"]))
			if parent < 0:
				parent = skel.get_bone_parent(bone)
			var p: Dictionary = b.duplicate()
			for k in overrides:
				p[k] = overrides[k]
			var rest_global := skel.get_bone_global_rest(bone)
			var head := _vec(b["head"])
			var tail := _vec(b["tail"])
			worst_head = maxf(worst_head, rest_global.origin.distance_to(head))
			var tail_local := rest_global.affine_inverse() * tail
			var reach := float(b.get("radius_m", 0.0)) + margin
			# the gap each collider allows this bone's middle and tail: its radius plus the strand's,
			# or what the strand had at rest if that is less
			var gaps: Array = []
			for col in colliders:
				var row := []
				for t in SAMPLES:
					var at_rest := head.lerp(tail, t)
					if col["ellipsoid"]:
						# a scale of the ellipsoid grown by the strand's reach: 1 on its surface
						var k := _ellipsoid_scale(at_rest, col["a_rest"], col["basis_rest"], col["radii"] + Vector3.ONE * reach)
						row.append(minf(1.0, k - 0.001 / maxf(col["radii"].x, 0.01)))
					else:
						row.append(minf(col["radius"] + reach, _dist_segment(at_rest, col["a_rest"], col["b_rest"]) - 0.001))
				gaps.append(row)
			bones.append({
				"name": String(b["bone"]), "bone": bone, "parent": parent,
				"rest": skel.get_bone_rest(bone), "tail_local": tail_local,
				"length": maxf(tail_local.length(), 0.002),
				"frequency_hz": float(p.get("frequency_hz", 1.5)),
				"damping_ratio": float(p.get("damping_ratio", 0.3)),
				"max_angle": deg_to_rad(float(p.get("max_angle_deg", 40.0))),
				"gravity_scale": float(p.get("gravity_scale", blk.get("gravity_scale", 1.0))),
				"response": float(p.get("response", blk.get("response", 1.0))),
				"gaps": gaps, "reach": reach,
				"friction": clampf(float(p.get("collision_friction", blk.get("collision_friction", 0.0))), 0.0, 1.0),
				"e": Vector3.ZERO, "u": Vector3.ZERO, "target": Vector3.ZERO, "target_v": Vector3.ZERO,
				"started": false, "g_rest_local": Vector3.ZERO, "angle": 0.0, "tip": Vector3.ZERO,
				"q": Quaternion.IDENTITY,
			})
			count += 1
		chains.append({"name": String(ch["name"]), "root_bone": _find(skel, String(ch.get("root_bone", ""))),
			"bones": bones})
	if worst_head > 0.01:
		problems.append("strand bone heads are %.3f m from where Blender put them: wrong skeleton or space" % worst_head)
	report = {"built": count > 0, "problems": problems, "chains": chains.size(), "bones": count,
		"colliders": colliders.size(), "head_error_m": snappedf(worst_head, 0.0001)}


static func _find(skel: Skeleton3D, bone_name: String) -> int:
	var i := skel.find_bone(bone_name)
	if i < 0:
		i = skel.find_bone(bone_name.replace(".", "_"))
	return i


static func _vec(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))


static func _closest(p: Vector3, a: Vector3, b: Vector3) -> Vector3:
	var ab := b - a
	var l2 := ab.length_squared()
	if l2 < 1e-12:
		return a
	return a + ab * clampf((p - a).dot(ab) / l2, 0.0, 1.0)


## How far out `p` is on an ellipsoid (centre, orthonormal axes, radii): 1 on its surface.
static func _ellipsoid_scale(p: Vector3, c: Vector3, axes: Basis, radii: Vector3) -> float:
	var d := p - c
	var q := Vector3(d.dot(axes.x) / radii.x, d.dot(axes.y) / radii.y, d.dot(axes.z) / radii.z)
	return q.length()


static func _dist_segment(p: Vector3, a: Vector3, b: Vector3) -> float:
	return p.distance_to(_closest(p, a, b))


func _gravity() -> Vector3:
	var g: float = ProjectSettings.get_setting("physics/3d/default_gravity", 9.8)
	var gv: Vector3 = ProjectSettings.get_setting("physics/3d/default_gravity_vector", Vector3.DOWN)
	return gv * g


func reset_stats() -> void:
	peak_angle_deg = 0.0
	limit_hits = 0
	collision_hits = 0
	nonfinite = 0
	usec_total = 0
	frames = 0
	peak_steps = 0
	dropped_steps = 0


func _process_modification_with_delta(delta: float) -> void:
	var skel := get_skeleton()
	if skel == null or delta <= 0.0:
		return
	var t0 := Time.get_ticks_usec()
	var skel_xf := skel.global_transform
	var g := _gravity()
	var caps_now: Array = []
	for col in colliders:
		var xf := skel_xf * skel.get_bone_global_pose(col["bone"])
		caps_now.append([xf * (col["a_local"] as Vector3), xf * (col["b_local"] as Vector3),
			xf.basis * (col["basis_local"] as Basis) if col["ellipsoid"] else null])
	var caps_prev: Array = _caps_prev if _caps_prev.size() == caps_now.size() else caps_now
	# Fixed steps of STEP, the time left over carried to the next frame, with the animated parent and
	# the colliders interpolated to each step's moment in the frame. The length, limit and collision
	# projections take energy out per step, so the step must not follow the frame rate: one step a
	# frame swung a ponytail a third as far at 30 fps as at 240 and let it pass a neck in one step,
	# and substeps of at most 1/120 s still swung it 24% further at 240 fps (1/240 s steps) than at 60.
	# A frame longer than MAX_STEPS * STEP (a load, a breakpoint, a window dragged) simulates only its
	# last MAX_STEPS: the strand lands on the frame's own pose from 0.13 s of motion instead of the
	# whole stall, so the cost of a hitch is bounded and a slow frame cannot make the next one slower.
	# The time in front of that window is skipped, not replayed, so each bone's target is moved to the
	# window's start first (`_seed`): without that the first step reads a whole stall's worth of the
	# body's motion as one step of it and the spring gets an impulse that is not there - a 0.75 s frame
	# threw the MPFB ponytail onto its 60 deg limit and 6 mm into the head.
	var steps: Array = []
	var clock := STEP - _left
	while clock <= delta + 1e-9:
		steps.append(clampf(clock / delta, 0.0, 1.0))
		clock += STEP
	_left = delta - (clock - STEP)
	var seed_f := -1.0
	if steps.size() > MAX_STEPS:
		dropped_steps += steps.size() - MAX_STEPS
		steps = steps.slice(steps.size() - MAX_STEPS)
		_left = 0.0
		seed_f = maxf(float(steps[0]) - STEP / delta, 0.0)
	peak_steps = maxi(peak_steps, steps.size())
	for ch in chains:
		var bones: Array = ch["bones"]
		if bones.is_empty():
			continue
		var parent: int = bones[0]["parent"]
		var now := skel_xf * (skel.get_bone_global_pose(parent) if parent >= 0 else Transform3D.IDENTITY)
		var prev: Transform3D = ch.get("parent_prev", now)
		if prev.origin.distance_to(now.origin) > TELEPORT_M:
			prev = now
		if seed_f >= 0.0:
			var seed_xf := _blend(prev, now, seed_f)
			for bd in bones:
				seed_xf = _seed(seed_xf, bd)
		for f in steps:
			var parent_xf := _blend(prev, now, f)
			var caps: Array = []
			for c in caps_now.size():
				caps.append([(caps_prev[c][0] as Vector3).lerp(caps_now[c][0], f), (caps_prev[c][1] as Vector3).lerp(caps_now[c][1], f), caps_now[c][2]])
			for bd in bones:
				parent_xf = _step(parent_xf, g, caps, bd, STEP)
		ch["parent_prev"] = now
		for bd in bones:
			var rest: Transform3D = bd["rest"]
			skel.set_bone_pose_position(bd["bone"], rest.origin)
			skel.set_bone_pose_rotation(bd["bone"], rest.basis.get_rotation_quaternion() * (bd["q"] as Quaternion))
	_caps_prev = caps_now
	usec_total += Time.get_ticks_usec() - t0
	frames += 1


## Move a bone's target to where the parent puts it at the start of a shortened frame's window,
## without integrating: the skipped time becomes a jump of the body the strand is not pushed by,
## while its own offset and velocity (its swing) carry through. Returns this bone's world transform,
## which is where it already points, so the next bone seeds from the same chain it will step on.
func _seed(parent_xf: Transform3D, b: Dictionary) -> Transform3D:
	var frame := parent_xf * (b["rest"] as Transform3D)
	if b["started"]:
		b["target"] = frame * (b["tail_local"] as Vector3)
		b["target_v"] = Vector3.ZERO
	return frame * Transform3D(Basis(b["q"] as Quaternion), Vector3.ZERO)


static func _blend(a: Transform3D, b: Transform3D, f: float) -> Transform3D:
	if f >= 1.0:
		return b
	var qa := a.basis.get_rotation_quaternion()
	var qb := b.basis.get_rotation_quaternion()
	var scale := b.basis.get_scale()
	return Transform3D(Basis(qa.slerp(qb, f)).scaled(scale), a.origin.lerp(b.origin, f))


## One bone, one substep. `parent_xf` is the parent bone's world transform (animated for the first
## bone, sprung for the rest); returns this bone's.
func _step(parent_xf: Transform3D, g: Vector3, caps: Array, b: Dictionary, dt: float) -> Transform3D:
	var frame := parent_xf * (b["rest"] as Transform3D)
	var head := frame.origin
	var target := frame * (b["tail_local"] as Vector3)
	var parent_basis := parent_xf.basis
	if not b["started"] or target.distance_to(b["target"]) > TELEPORT_M:
		b["target"] = target
		b["target_v"] = Vector3.ZERO
		b["e"] = Vector3.ZERO
		b["u"] = Vector3.ZERO
		b["g_rest_local"] = parent_basis.inverse() * g
		b["started"] = true
	var vt: Vector3 = (target - b["target"]) / dt
	var at: Vector3 = (vt - b["target_v"]) / dt
	if at.length() > MAX_ACCEL:
		at = at.normalized() * MAX_ACCEL
	b["target"] = target
	b["target_v"] = vt
	var g_rest_world: Vector3 = parent_basis * (b["g_rest_local"] as Vector3)
	var push: Vector3 = (g - g_rest_world) * float(b["gravity_scale"]) - at * float(b["response"]) * response_scale
	var next := spring_step(b["e"], b["u"], TAU * float(b["frequency_hz"]), float(b["damping_ratio"]), dt, push)
	var e: Vector3 = next[0]
	var u: Vector3 = next[1]
	var length: float = b["length"]
	var rest_dir := (target - head).normalized()

	# on the bone's length
	var dir := target + e - head
	dir = dir.normalized() if dir.length() > 1e-6 else rest_dir
	# within the angle limit
	var angle := acos(clampf(dir.dot(rest_dir), -1.0, 1.0))
	var limit: float = b["max_angle"]
	var limited := false
	if angle > limit:
		var axis := rest_dir.cross(dir)
		if axis.length() > 1e-6:
			dir = rest_dir.rotated(axis.normalized(), limit)
			limited = true
			limit_hits += 1
	var tail := head + dir * length
	# out of the colliders
	var pushed := Vector3.ZERO
	var near: Array = []
	for k in caps.size():
		# only colliders the bone can reach: its head within its length and the collider's bound
		var bound: float = colliders[k]["bound"] + float(b["reach"]) + length
		if _dist_segment(head, caps[k][0], caps[k][1]) <= bound:
			near.append(k)
	for _pass in PASSES:
		if near.is_empty():
			break
		for k in near:
			var gaps: Array = b["gaps"][k]
			for j in SAMPLES.size():
				var t: float = SAMPLES[j]
				var r: float = gaps[j]
				if r <= 0.0:
					continue
				var p := head.lerp(tail, t)
				var move: Vector3
				if caps[k][2] != null:
					# out along the ellipsoid's own scaling, to the scale allowed
					var radii: Vector3 = colliders[k]["radii"] + Vector3.ONE * float(b["reach"])
					var basis: Basis = caps[k][2]
					var sc := _ellipsoid_scale(p, caps[k][0], basis, radii)
					if sc >= r or sc < 1e-6:
						continue
					move = (p - caps[k][0]) * (r / sc - 1.0)
				else:
					var q := _closest(p, caps[k][0], caps[k][1])
					var d := p.distance_to(q)
					if d >= r:
						continue
					move = (p - q) / d * (r - d) if d > 1e-6 else (tail - head).normalized() * r
				var n := move.normalized()
				tail += move / t
				tail = head + (tail - head).normalized() * length
				pushed += n
				collision_hits += 1
	dir = (tail - head).normalized()
	angle = acos(clampf(dir.dot(rest_dir), -1.0, 1.0))
	e = tail - target
	# velocity: never along the bone, never further into a limit or a collider
	u -= dir * u.dot(dir)
	if limited:
		var away := (dir - rest_dir * dir.dot(rest_dir))
		if away.length() > 1e-6:
			away = away.normalized()
			var out := u.dot(away)
			if out > 0.0:
				u -= away * out
	if pushed.length() > 1e-6:
		var n2 := pushed.normalized()
		var into := u.dot(n2)
		if into < 0.0:
			u -= n2 * into
		# contact friction: sliding along the collider loses `collision_friction` of its speed per
		# step (1/120 s) in contact.
		# Without it a ponytail resting on the neck gained swing on every stride of a run (tip
		# 22, 30, 41, 49, 66, 74, 95 deg on successive strides) - the push out of the collider feeds
		# the chain below; 0.1 holds it at 10-21 deg.
		var slide := u - n2 * u.dot(n2)
		u -= slide * (1.0 - float(b["friction"]))
	if not (is_finite(e.x) and is_finite(e.y) and is_finite(e.z) and is_finite(u.x) and is_finite(u.y) and is_finite(u.z)):
		nonfinite += 1
		e = Vector3.ZERO
		u = Vector3.ZERO
		tail = target
		angle = 0.0
	b["e"] = e
	b["u"] = u
	if paused:
		tail = target
		angle = 0.0
	b["angle"] = angle
	b["tip"] = tail
	peak_angle_deg = maxf(peak_angle_deg, rad_to_deg(angle))
	# the rotation that aims the bone at its tail, in its rest frame; the bone's world transform with it
	var from: Vector3 = b["tail_local"]
	var to := frame.affine_inverse() * tail
	var rot := Quaternion.IDENTITY
	if from.length() > 1e-6 and to.length() > 1e-6:
		rot = Quaternion(from.normalized(), to.normalized())
	b["q"] = rot
	return frame * Transform3D(Basis(rot), Vector3.ZERO)


## One exact step of x'' = -w^2 x - 2 z w x' + push, over dt. Returns [x, x'].
## (The same closed form as jiggle_modifier.gd.)
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


## Knock every bone: an instant change of the body's velocity, world m/s - the strands lag it.
func kick(velocity: Vector3, only_chain := "") -> void:
	for ch in chains:
		if only_chain == "" or ch["name"] == only_chain:
			for b in ch["bones"]:
				b["u"] = (b["u"] as Vector3) - velocity


func stats() -> Dictionary:
	return {"chains": chains.size(), "peak_angle_deg": snappedf(peak_angle_deg, 0.01), "limit_hits": limit_hits,
		"collision_hits": collision_hits, "nonfinite": nonfinite,
		"usec_per_frame": snappedf(float(usec_total) / maxf(frames, 1), 0.1), "frames": frames,
		"peak_steps": peak_steps, "dropped_steps": dropped_steps}
