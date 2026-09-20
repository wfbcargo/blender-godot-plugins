class_name MovesController
extends CharacterBody3D
## A body that walks (trots, runs...) on any rig-anything `.moves.json`.
##
## Reads the manifest directly: `scene` is instanced as the child "Model", `clips` maps roles to clip
## names, `loops` sets loop modes. Nothing else is required. The gait ladder is every travelling role
## the manifest has a speed for - Walk, Trot, Run and the like, plus anything with a `gaits` entry -
## slowest first. Each moves at `gaits.<role>.natural_speed_mps` (the real speed for this body's size,
## from its Froude number), or `implied_speed_mps` x `implied_pace` for a manifest without gait data.
##
## Clips are in place; the body moves, and a gait plays at (ground speed / the clip's implied speed),
## so planted feet move backward exactly as fast as the body goes forward and do not skate. Gaits
## change where neighbouring speeds meet as a ratio - the geometric mean - with `gait_hysteresis`
## either side, and carry the stride phase across (every cycle starts on the same footfall).
##
## Collision is a capsule from the manifest's optional `collider` {radius, height}, else the standing
## height (`height_m.stand`) and `_fallback_collider_radius()`.
##
## Per-cycle variability (`gait_jitter.gd`) comes off the manifest's optional `variability` block and
## is OFF unless it asks for it - which every character built before that block existed does not. It
## warps the playhead within the stride and scales the arm swing, so a looping clip stops reading as
## a loop. The warp is bounded and tracked against the unjittered phase, so it never accumulates:
## `implied_speed` time scaling and planted feet are unchanged over any run length.
##
## The default `_physics_process` is plain locomotion from `input_source` -> {dir: Vector3 (length
## 0..1), run or sprint: bool}. Subclasses with more moves override `_physics_process` and use the
## pieces: `play_gait_for`, `play_role`, `add_hold`, `_set_height`. Hooks: `_setup()` after the model,
## ladder and collider exist; `_build_collider()`, `_set_height()` and `_fallback_collider_radius()`
## for another collision shape.

const MOVING := 0.05
## Roles taken as gaits when present, whatever order they are listed in; the ladder sorts by speed.
const GAIT_ROLES := ["Walk", "Amble", "Pace", "Trot", "Canter", "Lope", "Run", "Gallop", "Sprint"]

## Set before adding to the tree.
@export var manifest_path := ""
## Callable(self) -> Dictionary, called each physics tick by the default locomotion.
var input_source: Callable

## Below this planar speed the body idles; lowered to a quarter of the walk for small, slow bodies.
var moving_threshold := MOVING
## Change-up at (geometric mean x (1 + this)), change-down at (geometric mean / (1 + this)).
var gait_hysteresis := 0.08
## Natural speed as a multiple of implied speed, for manifests without `gaits`.
var implied_pace := 1.0
var accel := 6.0
var turn_speed := 8.0
var gait_blend := 0.25
var idle_blend := 0.3
## Collider radius; 0 takes the manifest's `collider.radius` or the fallback.
var collider_radius := 0.0

var display_name := ""
var height := 1.0
var walk_speed := 0.0           # the slowest gait
var run_speed := 0.0            # the fastest gait; 0 with only one

var _m: Dictionary
var _clip := {}                 # role -> clip name
var _implied := {}
var _heights := {}
var _gaits := {}
## Travelling gaits slowest first: [{role, speed, up, down}], `up`/`down` the speeds at which to change
## to the next faster / previous slower gait.
var _ladder := []
var _model: Node3D
var _anim: AnimationPlayer
var _skeleton: Skeleton3D
var _shape: Shape3D
var _shape_node: CollisionShape3D
var _gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity", 9.8)
var _yaw := 0.0

# ---- per-cycle variability (gait_jitter.gd); all inert while `jitter.enabled()` is false
## The manifest's resolved `variability`, or an all-zero (disabled) one when it had none.
var jitter: GaitJitter
## Past this distance from the active camera the amplitude modifier stops working (the phase
## warp is one multiply and stays on). 0 turns the gate off.
var jitter_lod_distance_m := 30.0
## How hard the playhead is pulled back onto (base phase + bounded offset), per cycle. This is
## what makes the warp drift-free: the error decays with a time constant of 1/this cycles. Setting
## it to 0 leaves the offset applied open loop, which still telescopes because the slope is read at
## the UNJITTERED phase. `jitter_naive` is the one that drifts, and is the control.
var jitter_track := 4.0
## The control `verify_jitter.gd` ships for the drift check, and the implementation a first attempt
## gives: read the warp's slope off the clip's OWN playing phase and multiply the rate by it. The
## slope is then evaluated at the already-warped playhead, so the per-cycle advance is
## `integral du / (1 + w')` instead of `integral (1 - w') du`, and the difference - about
## 1.2 x gain^2 per cycle - does not telescope. It accumulates, which is the whole failure this
## design exists to avoid, so it must fail the bound.
var jitter_naive := false
var _jit_theta := 0.0           # base phase in cycles, advancing at exactly the unjittered rate
var _jit_phi := 0.0             # the commanded (jittered) playhead, in the same cycles
var _jit_clip := ""
var _jit_last_u := 0.0
var _jit_mod: Node = null


func _ready() -> void:
	load_moves()
	_build_ladder()
	_build_collider()
	build_jitter()
	_setup()
	if _clip.has("Idle"):
		_anim.play(_clip["Idle"])


## Hook: runs once the model, clips, ladder and collider are in place.
func _setup() -> void:
	pass


func load_moves() -> void:
	_m = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	for role in _m["clips"]:
		_clip[role] = _m["clips"][role]
	_implied = _m.get("implied_speed_mps", {})
	_heights = _m.get("height_m", {})
	_gaits = _m.get("gaits", {})
	display_name = _m.get("name", _m.get("creature", manifest_path.get_file().get_basename()))
	var col: Dictionary = _m.get("collider", {})
	height = float(col.get("height", _heights.get("stand", 1.0)))
	jitter = GaitJitter.from_moves(_m, str(_m.get("creature", "")))
	_model = (load(_m["scene"]) as PackedScene).instantiate()
	_model.name = "Model"
	add_child(_model)
	_anim = _model.find_children("*", "AnimationPlayer", true, false)[0]
	var skels := _model.find_children("*", "Skeleton3D", true, false)
	_skeleton = skels[0] if not skels.is_empty() else null
	# pose on physics ticks, in step with the body
	_anim.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_PHYSICS
	var loops: Array = _m.get("loops", [])
	for n in _anim.get_animation_list():
		_anim.get_animation(n).loop_mode = Animation.LOOP_LINEAR if n in loops else Animation.LOOP_NONE


# ------------------------------------------------------------------ gaits

## The natural speed of a gait role, 0 if the manifest gives none.
func gait_speed(role: String) -> float:
	if _gaits.has(role) and _gaits[role].has("natural_speed_mps"):
		return float(_gaits[role]["natural_speed_mps"])
	return implied_speed(role) * implied_pace


## The ground speed a role's clip was authored for at rate 1 (`implied_speed_mps`, keyed by role or,
## in some exporters' manifests, by clip name), 0 if unknown.
func implied_speed(role: String) -> float:
	return float(_implied.get(role, _implied.get(_clip.get(role, ""), 0.0)))


func _build_ladder() -> void:
	_ladder = []
	var roles := GAIT_ROLES.duplicate()
	for role in _gaits:
		if not role in roles:
			roles.append(role)
	for role in roles:
		if _clip.has(role) and gait_speed(role) > 0.0:
			_ladder.append({"role": role, "speed": gait_speed(role)})
	_ladder.sort_custom(func(a, b): return a["speed"] < b["speed"])
	walk_speed = _ladder[0]["speed"] if not _ladder.is_empty() else 0.0
	run_speed = _ladder[-1]["speed"] if _ladder.size() > 1 else 0.0
	if walk_speed > 0.0:
		# a cricket walks at 4 cm/s: a fixed threshold would never let it leave Idle
		moving_threshold = minf(moving_threshold, walk_speed * 0.25)
	var k := 1.0 + gait_hysteresis
	for i in _ladder.size():
		var g: Dictionary = _ladder[i]
		g["up"] = sqrt(g["speed"] * _ladder[i + 1]["speed"]) * k if i + 1 < _ladder.size() else INF
		g["down"] = sqrt(g["speed"] * _ladder[i - 1]["speed"]) / k if i > 0 else moving_threshold


func gait_roles() -> Array:
	return _ladder.map(func(g): return g["role"])


func can_run() -> bool:
	return run_speed > 0.0


func has_role(role: String) -> bool:
	return _clip.has(role)


## The gait for this speed, staying in the current one until the speed crosses that gait's own
## change-up or change-down line. From outside a gait, the nearest by geometric mean.
func pick_gait(speed: float) -> String:
	if _ladder.is_empty():
		return ""
	var playing := str(_anim.current_animation)
	var current := -1
	for i in _ladder.size():
		if _clip[_ladder[i]["role"]] == playing:
			current = i
	if current < 0:
		current = 0
		for i in _ladder.size():
			if speed >= sqrt(_ladder[i]["speed"] * _ladder[maxi(i - 1, 0)]["speed"]):
				current = i
	while current + 1 < _ladder.size() and speed > _ladder[current]["up"]:
		current += 1
	while current > 0 and speed < _ladder[current]["down"]:
		current -= 1
	return _ladder[current]["role"]


## Playback rate that keeps planted feet still at `speed`.
func rate_for(role: String, speed: float) -> float:
	var implied := implied_speed(role)
	if implied <= 0.0:
		implied = gait_speed(role)
	return speed / implied if implied > 0.0 else 1.0


## Idle below `moving_threshold`, else the gait for `speed` at its matching rate. `blend` is for a
## gait change (default `gait_blend`); settling into Idle always takes `idle_blend`. Returns the role.
## `delta` is the tick the jitter integrates over; -1 takes the physics tick.
func play_gait_for(speed: float, blend := -1.0, delta := -1.0) -> String:
	var role := pick_gait(speed) if speed > moving_threshold else ""
	if role == "":
		if _clip.has("Idle"):
			play_role("Idle", idle_blend, 1.0)
			_anim.speed_scale = jitter_factor(1.0, delta)
		return "Idle"
	play_gait(role, gait_blend if blend < 0.0 else blend)
	var base := rate_for(role, speed)
	_anim.speed_scale = base * jitter_factor(base, delta)
	return role


# ------------------------------------------------------------------ variability

## Build the arm-swing amplitude modifier, if the manifest asked for amplitude jitter and the
## model has a skeleton. Called from `_ready`; safe to call again.
func build_jitter() -> void:
	if _jit_mod != null or jitter == null or _skeleton == null or jitter.amp_gain() <= 0.0:
		return
	_jit_mod = GaitJitterModifier.build(_skeleton, _m, jitter)
	_jit_mod.lod_distance_m = jitter_lod_distance_m


## The amplitude modifier, or null when there is none (jitter off, no skeleton, no arm bones).
func jitter_modifier() -> Node:
	return _jit_mod


## The playback-rate multiplier for this tick: 1.0 exactly whenever jitter is off.
##
## `_jit_theta` is the phase the clip WOULD be at with no jitter, advancing at exactly
## `base_rate / clip_length` cycles per second. The playhead `_jit_phi` is steered toward
## `_jit_theta + offset(_jit_theta)`, where `offset` is bounded by `jitter.phase_gain()`. A
## bounded target cannot drift, and the proportional term absorbs the integration error that an
## open-loop `1 + offset'` would otherwise let build up: that error is about 1.2 x gain^2 per
## cycle, which is 8 cycles of drift over an hour of walking - exactly the failure this must not
## ship.
func jitter_factor(base_rate: float, delta := -1.0) -> float:
	if jitter == null or not jitter.enabled() or _anim == null:
		return 1.0
	var length := _anim.current_animation_length
	if length <= 0.0 or base_rate <= 0.0:
		return 1.0
	var dt := delta if delta >= 0.0 else get_physics_process_delta_time()
	var clip := str(_anim.current_animation)
	if clip != _jit_clip:
		# A gait change seeks the playhead to the carried phase; re-anchor rather than fight it.
		_jit_clip = clip
		_jit_phi = _jit_theta + jitter.phase_offset(fposmod(_jit_theta, 1.0))
	var r := base_rate / length
	var u := 0.0
	var f := 1.0
	if jitter_naive:
		u = fposmod(_anim.current_animation_position / length, 1.0)
		if u < _jit_last_u:
			jitter.advance_cycle()
		_jit_last_u = u
		f = 1.0 + jitter.phase_slope(u)
		_jit_theta += r * dt
	else:
		var was := floori(_jit_theta)
		_jit_theta += r * dt
		while floori(_jit_theta) > was:
			jitter.advance_cycle()
			was += 1
		u = fposmod(_jit_theta, 1.0)
		var target := _jit_theta + jitter.phase_offset(u)
		f = 1.0 + jitter.phase_slope(u) + jitter_track * (target - _jit_phi)
	f = clampf(f, GaitJitter.RATE_MIN, GaitJitter.RATE_MAX)
	_jit_phi += r * f * dt
	if _jit_mod != null:
		_jit_mod.cycle_u = u
	return f


## What the jitter has done so far: the base phase, the played phase, and their difference in
## cycles. `drift` is the number a long run must not let grow - it is bounded by the offset.
func jitter_state() -> Dictionary:
	return {"theta": _jit_theta, "phi": _jit_phi, "drift": _jit_phi - _jit_theta,
			"cycles": jitter.cycles() if jitter != null else 0}


## Switch to a gait without restarting the stride: coming from another gait, the normalised phase is
## carried across so the feet stay where they were in the step.
func play_gait(role: String, blend := 0.2) -> void:
	var clip: String = _clip[role]
	if _anim.current_animation == clip:
		return
	var phase := 0.0
	var from := str(_anim.current_animation)
	if _anim.current_animation_length > 0.0:
		for g in _ladder:
			if _clip[g["role"]] == from:
				phase = fmod(_anim.current_animation_position / _anim.current_animation_length, 1.0)
	_anim.play(clip, blend)
	if phase > 0.0:
		_anim.seek(phase * _anim.get_animation(clip).length, true)


func play_role(role: String, blend := 0.2, rate := 1.0) -> void:
	var clip: String = _clip[role]
	if _anim.current_animation != clip:
		_anim.play(clip, blend)
	_anim.speed_scale = rate


## The role playing now ("Idle", "Walk"...), or "".
func current_role() -> String:
	var playing := str(_anim.current_animation) if _anim else ""
	for role in _clip:
		if _clip[role] == playing:
			return role
	return ""


var current_clip: String:
	get:
		return str(_anim.current_animation) if _anim else ""


## A looping one-key clip holding `role`'s clip at time `t` - crouched, tucked - added to the player
## and to the clips as role `hold_name`.
func add_hold(hold_name: String, role: String, t: float) -> void:
	var src := _anim.get_animation(_clip[role])
	var hold := Animation.new()
	hold.length = 0.5
	hold.loop_mode = Animation.LOOP_LINEAR
	for i in src.get_track_count():
		var type := src.track_get_type(i)
		var v: Variant
		match type:
			Animation.TYPE_POSITION_3D:
				v = src.position_track_interpolate(i, t)
			Animation.TYPE_ROTATION_3D:
				v = src.rotation_track_interpolate(i, t)
			Animation.TYPE_SCALE_3D:
				v = src.scale_track_interpolate(i, t)
			_:
				continue
		var j := hold.add_track(type)
		hold.track_set_path(j, src.track_get_path(i))
		hold.track_insert_key(j, 0.0, v)
	_anim.get_animation_library("").add_animation(hold_name, hold)
	_clip[hold_name] = hold_name


# ------------------------------------------------------------------ body

func _fallback_collider_radius(h: float) -> float:
	return 0.12 * h


func _build_collider() -> void:
	var col: Dictionary = _m.get("collider", {})
	var shape := CapsuleShape3D.new()
	if collider_radius <= 0.0:
		collider_radius = float(col.get("radius", _fallback_collider_radius(height)))
	shape.radius = minf(collider_radius, height * 0.5)
	_shape = shape
	_shape_node = CollisionShape3D.new()
	_shape_node.shape = _shape
	add_child(_shape_node)
	_set_height(height)


## Resize the collider for a stance (standing, crouched...), feet on the body's origin.
func _set_height(h: float) -> void:
	var capsule := _shape as CapsuleShape3D
	capsule.height = maxf(h, capsule.radius * 2.0)
	_shape_node.position.y = h * 0.5


func planar_speed() -> float:
	return Vector2(velocity.x, velocity.z).length()


## Face a world yaw (0 faces +Z, the way rig-anything's glbs face).
func face(yaw: float) -> void:
	_yaw = yaw
	rotation.y = yaw


func _physics_process(delta: float) -> void:
	var cmd: Dictionary = input_source.call(self) if input_source.is_valid() else {}
	var dir: Vector3 = cmd.get("dir", Vector3.ZERO)
	dir.y = 0.0
	var amount := minf(dir.length(), 1.0)
	var top := run_speed if (cmd.get("run", false) or cmd.get("sprint", false)) and can_run() else walk_speed
	var want := dir.normalized() * top * amount if amount > 0.0 else Vector3.ZERO
	var planar := Vector3(velocity.x, 0.0, velocity.z).lerp(want, clampf(accel * delta, 0.0, 1.0))
	velocity.x = planar.x
	velocity.z = planar.z
	if not is_on_floor():
		velocity.y -= _gravity * delta
	else:
		velocity.y = -0.1
	move_and_slide()

	if amount > 0.0:
		face(lerp_angle(_yaw, atan2(dir.x, dir.z), clampf(turn_speed * delta, 0.0, 1.0)))
	play_gait_for(planar_speed(), -1.0, delta)
