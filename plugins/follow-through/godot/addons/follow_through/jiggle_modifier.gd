extends SkeletonModifier3D
## Flesh that follows through: breasts, bellies, buttocks, a bloater's torso.
##
## Blender's flesh.prepare adds one bone per soft mass and weights the mass to it; this
## modifier springs those bones every frame, after the animation has posed the skeleton.
## Each bone's tail is a point on a damped spring whose rest is where the animated
## skeleton puts it, so a footfall's jolt, a turn and a stop all carry through.
##
## Why not SpringBoneSimulator3D: it simulates rotation only (a chain's tails keep their
## length), and its stiffness is multiplied by the frame time without being squared, so
## a spring's frequency changes with the frame rate. Flesh needs translation and squash
## too, and a frequency that means Hz.
##
## Integration is the exact solution of a damped oscillator over the frame, not an Euler
## step: semi-implicit Euler at 60 Hz is unstable above ~8 Hz when critically damped, and
## firm flesh lives at 5-10 Hz. The load over the frame is the anchor's acceleration and
## the change of gravity relative to the rest pose - flesh modelled standing already sags
## as it should, and only sags further when the body leans or lies down.
##
## Every assumption is checked at build time and written to `report`: the bone exists, its
## rest head is where Blender said, and its tail lies along its local Y (so squash can be a
## pose scale).

var spec: Dictionary
var report: Dictionary = {}
var regions: Array[Dictionary] = []
var paused := false                 # hold every bone at rest (for side-by-side comparisons)
var response_scale := 1.0           # multiplies every region's response, live (a slider in a demo)

const TELEPORT_M := 1.0             # the anchor moved further than this in a frame: reset, do not fling
const MAX_ACCEL := 400.0            # m/s^2; animation keys that snap would otherwise launch the flesh


static func build(mesh: MeshInstance3D, s: Dictionary, options := {}):
	var skel := mesh.get_node_or_null(mesh.skeleton) as Skeleton3D
	var mod = new()
	mod.spec = s
	mod.name = String(mesh.name) + "_jiggle"
	if skel == null:
		mod.report = {"built": false, "problems": PackedStringArray(["%s has no skeleton" % mesh.name])}
		return mod
	skel.add_child(mod)
	mod._setup(skel, options)
	return mod


func _setup(skel: Skeleton3D, options: Dictionary) -> void:
	var overrides: Dictionary = options.get("overrides", {})
	var problems := PackedStringArray()
	var worst_head := 0.0
	var worst_axis := 0.0
	for r in spec["jiggle"]["regions"]:
		var bone := _find(skel, String(r["bone"]))
		var parent := _find(skel, String(r["parent"]))
		if bone < 0:
			problems.append("bone %s not in the skeleton" % r["bone"])
			continue
		if parent < 0:
			parent = skel.get_bone_parent(bone)
		var rest_global := skel.get_bone_global_rest(bone)
		var head := _vec(r["head"])
		var tail := _vec(r["tail"])
		var tail_local := rest_global.affine_inverse() * tail
		var length := tail_local.length()
		var head_error := rest_global.origin.distance_to(head)
		worst_head = maxf(worst_head, head_error)
		var along_y := absf(tail_local.normalized().dot(Vector3.UP)) if length > 1e-6 else 1.0
		worst_axis = maxf(worst_axis, 1.0 - along_y)
		var p: Dictionary = r.duplicate()
		for k in overrides:
			p[k] = overrides[k]
		regions.append({
			"name": String(r["name"]), "type": String(r.get("type", "")),
			"bone": bone, "parent": parent,
			"rest": skel.get_bone_rest(bone),
			"tail_local": tail_local, "length": maxf(length, 0.005),
			"squash_ok": along_y > 0.98,
			"frequency_hz": float(p.get("frequency_hz", 2.5)),
			"damping_ratio": float(p.get("damping_ratio", 0.25)),
			"squash": float(p.get("squash", 0.5)),
			"gravity_scale": float(p.get("gravity_scale", 1.0)),
			"aim": float(p.get("aim", 1.0)),
			"translate": float(p.get("translate", 0.3)),
			"response": float(p.get("response", 1.0)),
			"max_offset": float(p.get("max_offset_m", 0.1)),
			"e": Vector3.ZERO, "u": Vector3.ZERO,
			"target": Vector3.ZERO, "target_v": Vector3.ZERO, "started": false,
			"g_rest_local": Vector3.ZERO, "offset": Vector3.ZERO, "stretch": 1.0,
		})
	report = {"built": problems.is_empty() or not regions.is_empty(), "problems": problems,
		"regions": regions.size(), "head_error_m": snappedf(worst_head, 0.0001),
		"axis_off_y": snappedf(worst_axis, 0.0001)}
	if worst_head > 0.01:
		problems.append("jiggle bone heads are %.3f m from where Blender put them: wrong skeleton or space" % worst_head)
	for reg in regions:
		if not reg["squash_ok"]:
			problems.append("%s: tail is not along the bone's local Y - squash disabled" % reg["name"])
	report["problems"] = problems


static func _find(skel: Skeleton3D, bone_name: String) -> int:
	var i := skel.find_bone(bone_name)
	if i < 0:
		i = skel.find_bone(bone_name.replace(".", "_"))
	return i


static func _vec(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))


func _gravity() -> Vector3:
	var g: float = ProjectSettings.get_setting("physics/3d/default_gravity", 9.8)
	var gv: Vector3 = ProjectSettings.get_setting("physics/3d/default_gravity_vector", Vector3.DOWN)
	return gv * g


func _process_modification_with_delta(delta: float) -> void:
	var skel := get_skeleton()
	if skel == null or delta <= 0.0:
		return
	var skel_xf := skel.global_transform
	var g := _gravity()
	for reg in regions:
		var parent: int = reg["parent"]
		var parent_pose := skel.get_bone_global_pose(parent) if parent >= 0 else Transform3D.IDENTITY
		var bone_rest_now := parent_pose * (reg["rest"] as Transform3D)
		var frame := skel_xf * bone_rest_now                   # the bone at rest on the animated parent, world
		var target := frame * (reg["tail_local"] as Vector3)
		if not reg["started"] or target.distance_to(reg["target"]) > TELEPORT_M:
			reg["target"] = target
			reg["target_v"] = Vector3.ZERO
			reg["e"] = Vector3.ZERO
			reg["u"] = Vector3.ZERO
			# gravity as the rest pose felt it, in the parent's frame
			reg["g_rest_local"] = (skel_xf.basis * parent_pose.basis).inverse() * g
			reg["started"] = true
		var vt: Vector3 = (target - reg["target"]) / delta
		var at: Vector3 = (vt - reg["target_v"]) / delta
		if at.length() > MAX_ACCEL:
			at = at.normalized() * MAX_ACCEL
		reg["target"] = target
		reg["target_v"] = vt
		var g_rest_world: Vector3 = (skel_xf.basis * parent_pose.basis) * (reg["g_rest_local"] as Vector3)
		# response scales only the body's own motion: 1 is physical, games usually want 2-4
		var push: Vector3 = (g - g_rest_world) * float(reg["gravity_scale"]) - at * float(reg["response"]) * response_scale
		var w := TAU * float(reg["frequency_hz"])
		var next := spring_step(reg["e"], reg["u"], w, float(reg["damping_ratio"]), delta, push)
		var e: Vector3 = next[0]
		var u: Vector3 = next[1]
		var limit := float(reg["max_offset"])
		if e.length() > limit:
			var n := e.normalized()
			e = n * limit
			var out := u.dot(n)
			if out > 0.0:
				u -= n * out
		reg["e"] = e
		reg["u"] = u
		if paused:
			e = Vector3.ZERO
		_pose(skel, reg, frame, e)


## One exact step of x'' = -w^2 x - 2 z w x' + push, over dt. Returns [x, x'].
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


## Pose the bone: its head moves a share of the offset, it turns to aim at the sprung
## tail, and it stretches toward it with the cross-section scaled by 1/sqrt so the mass
## keeps its volume.
func _pose(skel: Skeleton3D, reg: Dictionary, frame: Transform3D, e: Vector3) -> void:
	var bone: int = reg["bone"]
	var rest: Transform3D = reg["rest"]
	var tail_local: Vector3 = reg["tail_local"]
	var shift := e * float(reg["translate"])
	var inv := frame.affine_inverse()
	var shift_local := inv.basis * shift
	var tip := inv * (frame * tail_local + e)
	var from := tail_local
	var to := tip - shift_local
	var q := Quaternion.IDENTITY
	if from.length() > 1e-6 and to.length() > 1e-6:
		q = Quaternion(from.normalized(), to.normalized())
		q = Quaternion.IDENTITY.slerp(q, clampf(float(reg["aim"]), 0.0, 1.0))
	var pose_scale := Vector3.ONE
	var stretch := 1.0
	if reg["squash_ok"] and float(reg["squash"]) > 0.0:
		stretch = 1.0 + (to.length() / float(reg["length"]) - 1.0) * float(reg["squash"])
		stretch = clampf(stretch, 0.5, 2.0)
		var side := 1.0 / sqrt(stretch)
		pose_scale = Vector3(side, stretch, side)
	reg["offset"] = e
	reg["stretch"] = stretch
	skel.set_bone_pose_position(bone, rest.origin + rest.basis * shift_local)
	skel.set_bone_pose_rotation(bone, rest.basis.get_rotation_quaternion() * q)
	skel.set_bone_pose_scale(bone, pose_scale * rest.basis.get_scale())


## Knock every region: an instant velocity change, world m/s - a punch, a landing.
func kick(velocity: Vector3, only_type := "") -> void:
	for reg in regions:
		if only_type == "" or reg["type"] == only_type:
			reg["u"] = (reg["u"] as Vector3) - velocity


func region_offsets() -> Dictionary:
	var out := {}
	for reg in regions:
		out[reg["name"]] = {"offset": reg["offset"], "stretch": reg["stretch"]}
	return out
