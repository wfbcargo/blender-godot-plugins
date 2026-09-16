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
## Integration is the exact damped oscillator (as follow-through's jiggle modifier): stable at
## any frame rate and frequency, so a frequency means Hz.

var spec: Dictionary
var report: Dictionary = {}
var bones: Array[Dictionary] = []
var paused := false
var response_scale := 1.0
var garment: MeshInstance3D

# stats, since the last reset_stats()
var peak_offset_m := 0.0
var backstop_hits := 0
var usec_total := 0
var frames := 0

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
		})
	if worst_head > 0.01:
		problems.append("hem bone heads are %.3f m from the spec: wrong skeleton or space" % worst_head)
	report = {"built": not bones.is_empty(), "bones": bones.size(), "head_error_m": snappedf(worst_head, 0.0001),
		"problems": problems}


static func _vec(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))


func _gravity() -> Vector3:
	var g: float = ProjectSettings.get_setting("physics/3d/default_gravity", 9.8)
	var gv: Vector3 = ProjectSettings.get_setting("physics/3d/default_gravity_vector", Vector3.DOWN)
	return gv * g


func reset_stats() -> void:
	peak_offset_m = 0.0
	backstop_hits = 0
	usec_total = 0
	frames = 0


func _process_modification_with_delta(delta: float) -> void:
	var skel := get_skeleton()
	if skel == null or delta <= 0.0:
		return
	var t0 := Time.get_ticks_usec()
	var skel_xf := skel.global_transform
	var g := _gravity()
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
		_aim(skel, b, frame, e)
	usec_total += Time.get_ticks_usec() - t0
	frames += 1


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
		"usec_per_frame": snappedf(float(usec_total) / maxf(frames, 1), 0.1), "frames": frames}
