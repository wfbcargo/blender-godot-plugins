class_name GaitJitterModifier
extends SkeletonModifier3D
## Per-cycle amplitude jitter on the arm swing, applied after the animation has posed the rig.
##
## Why the arms and nothing else. Amplitude variation has to come off the pose, and scaling a
## leg's rotation changes where the foot lands - which is exactly the foot skate this branch
## promised not to add. The arm chain carries no ground contact, it is the most visible swing
## on a walk, and its stride-to-stride variability is real. So the scaled set is the arm roots
## the manifest's `arm_pose` names (`upper_arm.L`, `upper_arm.R`) and their descendants down to
## `MAX_DEPTH`, and nothing below the pelvis is ever touched.
##
## The scale is a slerp from the bone's REST rotation toward its animated rotation by
## `1 + jitter`, so jitter 0 is the animation untouched, bit for bit, and the rest pose is the
## fixed point. Cost is one slerp per bone per frame over ~6 bones.
##
## LOD: `lod_distance_m` turns it off past that distance from the active camera;
## SkeletonModifier3D's own `active = false` turns it off outright. Phase jitter (in
## MovesController) is a single multiply and stays on; this is the part with a per-bone cost, so
## this is the part gated.

## How far below an arm root to follow the chain: upper_arm -> forearm -> hand. Fingers add
## cost and show nothing at the distance an arm swing reads from.
const MAX_DEPTH := 2
## Slerp weight is clamped here: a manifest asking for a wild amplitude cannot fold an elbow
## backwards.
const SCALE_MIN := 0.7
const SCALE_MAX := 1.3

var jitter: GaitJitter
## Set every frame by MovesController: where in the cycle the clip is, 0..1.
var cycle_u := 0.0
## Past this distance from the active camera the modifier does nothing. 0 disables the gate.
var lod_distance_m := 30.0
## Set from outside to bypass the camera lookup (a headless verifier has no camera).
var lod_override := -1.0

var bones := PackedInt32Array()
var report := {}

var _rest := []                # per bone: the rest rotation quaternion
var _skipped_lod := 0
var _applied := 0


## Build over a skeleton, taking the arm roots from a `.moves.json`'s `arm_pose` (any clip's
## entry: the keys are the same for all of them). Returns the modifier, added under `skel`.
static func build(skel: Skeleton3D, m: Dictionary, j: GaitJitter):
	var mod = new()
	mod.name = "gait_jitter"
	mod.jitter = j
	var roots := arm_roots(m)
	var problems := PackedStringArray()
	if roots.is_empty():
		problems.append("the manifest names no arm root in arm_pose")
	for r in roots:
		var i := _find(skel, r)
		if i < 0:
			problems.append("no bone %s on the skeleton" % r)
			continue
		mod._collect(skel, i, 0)
	mod.report = {"built": not mod.bones.is_empty(), "roots": roots,
			"bones": mod.bones.size(), "problems": problems}
	skel.add_child(mod)
	return mod


## The arm roots a manifest names, in a stable order.
static func arm_roots(m: Dictionary) -> PackedStringArray:
	var out := PackedStringArray()
	var ap: Variant = m.get("arm_pose", null)
	if not (ap is Dictionary):
		return out
	for clip in (ap as Dictionary):
		var per: Variant = (ap as Dictionary)[clip]
		if not (per is Dictionary):
			continue
		for bone in (per as Dictionary):
			if not bone in out:
				out.append(bone)
	out.sort()
	return out


static func _find(skel: Skeleton3D, bone_name: String) -> int:
	var i := skel.find_bone(bone_name)
	if i < 0:
		# glTF import replaces "." in a bone name; strand_modifier does the same lookup.
		i = skel.find_bone(bone_name.replace(".", "_"))
	return i


func _collect(skel: Skeleton3D, bone: int, depth: int) -> void:
	if bone in bones:
		return
	bones.append(bone)
	_rest.append(skel.get_bone_rest(bone).basis.get_rotation_quaternion().normalized())
	if depth >= MAX_DEPTH:
		return
	for child in skel.get_bone_children(bone):
		_collect(skel, child, depth + 1)


## Times the modifier skipped its work because the camera was far away, and times it ran.
func counters() -> Dictionary:
	return {"applied": _applied, "skipped_lod": _skipped_lod}


func _lod_far() -> bool:
	if lod_distance_m <= 0.0:
		return false
	if lod_override >= 0.0:
		return lod_override > lod_distance_m
	var skel := get_skeleton()
	if skel == null:
		return false
	var cam := skel.get_viewport().get_camera_3d() if skel.is_inside_tree() else null
	if cam == null:
		return false
	return skel.global_position.distance_to(cam.global_position) > lod_distance_m


func _process_modification_with_delta(_delta: float) -> void:
	if jitter == null or jitter.amp_gain() <= 0.0 or bones.is_empty():
		return
	if _lod_far():
		_skipped_lod += 1
		return
	var skel := get_skeleton()
	if skel == null:
		return
	var s := clampf(jitter.amp_scale(cycle_u), SCALE_MIN, SCALE_MAX)
	for k in bones.size():
		var b: int = bones[k]
		var rest: Quaternion = _rest[k]
		var posed := skel.get_bone_pose_rotation(b)
		skel.set_bone_pose_rotation(b, rest.slerp(posed, s).normalized())
	_applied += 1
