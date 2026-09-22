extends SceneTree
## Measure what `gait_jitter.gd` actually does, on a real `.moves.json`, and fail when it is not
## what it claims.
##
##   godot --headless --fixed-fps 60 --path <project> -s res://addons/rig_anything/verify_jitter.gd -- \
##       manifests=res://a.moves.json[,res://b.moves.json] [jitter=0.6] [amp=0.6] [seed=7] \
##       [cycles=4096] [seconds=60] [long=300] [spectrum=white] [naive=1] [skate_ratio=1.25]
##
## `--fixed-fps 60` is not optional: the bodies are driven on real frames, because that is the only
## way the skeleton's modifier pass runs (`Skeleton3D.advance` does not run it from a script loop),
## and `_process`'s delta has to be the tick the animation is advanced by.
##
## Checks, each one printed as an `RA_JIT  PASS/FAIL` line with its free measurement beside it:
##
##  1. spectrum - the DFA exponent of the phase and of the amplitude series is near 0.8. The
##     CONTROL is `spectrum=white`: one gaussian per cycle, which is what a naive `randf()` gives.
##     It reads ~0.5 and must FAIL this same check.
##  2. absent   - a manifest with no `variability` key - every character built before the seam -
##     resolves to all zeros: jitter off, playback rate exactly 1x base, no modifier built.
##  3. varies   - driven at a gait's natural speed, stride intervals and arm swing differ from
##     cycle to cycle with jitter on and are exactly periodic with it off, and the MEAN stride
##     time is unchanged (which is what `implied_speed` time scaling rests on).
##  4. drift    - the two runs' real playheads, read off the AnimationPlayer, sampled once a
##     second for the whole run. The gap between them must never leave the offset bound, and the
##     TREND fitted through those samples, carried over the whole run, must not leave it either.
##     A gap that wanders inside a bound and one that grows are different shapes, and only a fit
##     over the run tells them apart: comparing the endpoint against one earlier endpoint compares
##     two samples of a wandering quantity, which reads as growth whenever the earlier one happened
##     to be small (it false-failed a clean 3600 s run at 0.0659 against 0.0600). Its CONTROL is
##     `naive=1`, which reads the warp's slope off the clip's own playing phase instead of the
##     unjittered one - the implementation a first attempt gives. Its per-cycle bias is about
##     1.2 x gain^2 and does not telescope, so it must FAIL both.
##  5. skate    - the planted foot's horizontal travel during stance, jitter on against off, the
##     same estimator both sides. On may be no more than `skate_ratio` x off.
##  6. cost     - microseconds per character per frame for the phase warp and for the amplitude
##     modifier, timed over 20000 calls against a do-nothing call. Reported free; the check is a
##     generous ceiling.
##  7. lod      - the amplitude modifier does nothing past `lod_distance_m`.
##
## Prints `RA_JITTER <json>` per manifest and `RA_JIT VERIFY PASSED/FAILED`; exits 1 on failure.

const TICK := 1.0 / 60.0
## The tick the ANIMATION is advanced by, which `tick=<seconds>` may make coarser than the engine
## frame. Both bodies advance by the same amount, so every gap between them stays the measurement
## it was; what changes is how finely the phase warp is integrated. It is the condition the
## tracking term exists for - see `_finish`'s lag check.
var _dt := TICK
## The band the shipped generator must land in, and white noise must not.
const ALPHA_MIN := 0.70
const ALPHA_MAX := 0.90
## Stride-interval and arm-swing coefficient of variation: jitter on must beat VARY_MIN, and off
## must stay under NO_VARY, because the clip is one baked cycle and is exactly periodic.
const VARY_MIN := 0.005
const NO_VARY := 0.0005
## The arm-swing estimator has a floor of its own: the first harmonic is summed over whatever 60 Hz
## samples fall inside the cycle, and a clip interpolated between keys is not band-limited, so a
## perfectly periodic swing still reads about 0.4% of variation. The off run must stay under this
## floor, and the on run must clear it by AMP_RATIO - which is the check that actually has teeth.
const AMP_FLOOR := 0.01
const AMP_RATIO := 5.0
## A foot counts as planted while it is within this of its own lowest point over the run.
const PLANT_M := 0.02
## Generous ceilings on the measured per-frame cost. The free numbers are what matter.
const COST_PHASE_US := 20.0
const COST_AMP_US := 60.0

var _fails := []
var _opt := {}
var _paths := []
var _state := "next"
var _out := {}
var _who := ""
var _m := {}
var _role := ""
var _speed := 0.0
var _on: MovesController
var _off: MovesController
var _s_on := {}
var _s_off := {}
var _tick := 0
## (cycles played by the unjittered body, gap in cycles), once a second over the whole run.
var _gap := []
var _short_ticks := 0
var _total_ticks := 0
var _short := {}
## `switch=<seconds>` alternates the commanded speed between two gaits, so the clip changes over
## and over: without it `_advance` drives ONE clip for the whole run and `jitter_factor`'s
## re-anchor branch (`clip != _jit_clip`) fires once at startup and never again, while a real
## character changes gait constantly. Both bodies switch on the same tick, so the gap between
## their playheads stays the measurement it was. The stride-interval, arm-swing and skate checks
## are about ONE clip's cycle and are skipped in this mode; the drift checks are the point of it.
var _speed2 := 0.0
var _speed_now := 0.0
var _switches := 0
## How many manifests this run has already drawn a series for; it steps the injected seed.
var _drawn := 0


## An independent observer of what the skeleton's modifier pass actually produces. It is added to
## the skeleton AFTER the jitter modifier, so when it runs, the poses it reads are the ones the
## renderer will skin with - which the poses read from outside the pass are not, because
## Skeleton3D restores them once the pass is over. Everything this verifier measures off a bone
## comes through here, so nothing is taken on the jitter modifier's own word.
class PoseProbe extends SkeletonModifier3D:
	var bones := PackedInt32Array()
	var world := Transform3D()
	var at := []
	var frames := 0

	func _process_modification_with_delta(_delta: float) -> void:
		var skel := get_skeleton()
		if skel == null:
			return
		for k in bones.size():
			at[k] = (world * skel.get_bone_global_pose(bones[k])).origin
		frames += 1


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("manifests="):
			_paths.append_array(a.substr(10).split(",", false))
		elif a.begins_with("dir="):
			_find(a.substr(4), _paths)
		elif "=" in a:
			_opt[a.get_slice("=", 0)] = a.substr(a.find("=") + 1)
	_dt = _f("tick", TICK)
	if _paths.is_empty():
		print("RA_JIT VERIFY: give manifests=<a,b> or dir=<res://...>")
		quit(2)


func _find(dir: String, out: Array) -> void:
	for f in DirAccess.get_files_at(dir):
		if f.ends_with(".moves.json"):
			out.append(dir.path_join(f))
	for d in DirAccess.get_directories_at(dir):
		_find(dir.path_join(d), out)


func _f(key: String, dflt: float) -> float:
	return float(_opt[key]) if _opt.has(key) else dflt


func _check(ok: bool, what: String) -> void:
	print("RA_JIT  %s  %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		_fails.append(what)


## A check this mode cannot measure. It prints its own line and counts as neither pass nor fail.
## A skipped check used to be written `_check(_switching() or ok, "... (cv %.6f < %.5f)")`, which
## passes the row AND prints its bound as though it had been met: `switch=7` logged "stride
## interval is exactly periodic (cv 0.217982 < 0.00050)" - 0.218 is not less than 0.0005. A reader
## of that log is being told something false by a green run, which is worse than either verdict.
func _skip(what: String) -> void:
	print("RA_JIT  SKIP  %s" % what)


func _process(delta: float) -> bool:
	match _state:
		"next":
			if _paths.is_empty():
				print("RA_JIT VERIFY %s" % ("PASSED" if _fails.is_empty() else "FAILED: %d checks" % _fails.size()))
				quit(0 if _fails.is_empty() else 1)
				return true
			_start(_paths.pop_front())
		"drive":
			_step(delta)
	return false


# ------------------------------------------------------------------ setup

## The manifest as the game has it, plus the `variability` block this run asks for. The block is
## injected here rather than demanded of the asset, so the verifier runs against characters built
## before the seam existed - which is every one of them.
## The seed is stepped once per manifest (`seed`, `seed+1`, `seed+2`, ...) so a run over several
## characters is several DRAWS, not one draw measured several times: with a fixed seed every
## character reported byte-identical DFA rows, and "the spectrum holds on three characters" then
## rested on one series. A one-manifest run (which is what regress drives) is index 0 and its
## numbers are unchanged. The resolved seed is in `RA_JITTER`'s `variability` block per character.
func _with_variability(path: String) -> Dictionary:
	var m: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	m["variability"] = {
		"seed": int(_f("seed", 7.0)) + _drawn,
		"asymmetry": 0.0,
		"jitter_phase": _f("jitter", 0.6),
		"jitter_amp": _f("amp", 0.6),
	}
	return m


## A MovesController on a manifest written to `user://`, driven by hand. The animation is stepped
## by this script; the skeleton's modifier pass is left to the engine, on real frames.
func _body(m: Dictionary, tag: String) -> MovesController:
	var path := "user://_jit_%s.moves.json" % tag
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(JSON.stringify(m))
	f.close()
	var body := MovesController.new()
	body.manifest_path = path
	root.add_child(body)
	body.set_physics_process(false)
	body._anim.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	return body


func _start(path: String) -> void:
	_m = _with_variability(path)
	_drawn += 1
	_who = "%s:" % str(_m.get("creature", path.get_file()))
	_out = {"who": str(_m.get("creature", "")), "manifest": path,
			"variability": _m["variability"], "spectrum": _opt.get("spectrum", "persistent")}
	_spectrum()
	_absent(path)
	var gait := _fastest_walk(_m)
	if gait.is_empty():
		_check(false, "%s the manifest has no gait to drive" % _who)
		print("RA_JITTER %s" % JSON.stringify(_out))
		return
	_role = gait["role"]
	_speed = gait["speed"]
	_speed_now = _speed
	_speed2 = _speed
	_switches = 0
	if _switching():
		# the fastest gait on the ladder, or Idle when there is only one
		var fastest := 0.0
		for r in _m.get("gaits", {}):
			if _m.get("clips", {}).has(r):
				fastest = maxf(fastest, float(_m["gaits"][r].get("natural_speed_mps", 0.0)))
		_speed2 = fastest if fastest > _speed * 1.05 else 0.0

	var off_m := _m.duplicate(true)
	off_m.erase("variability")
	_off = _body(off_m, "off")
	if _opt.get("ctl", "") == "legs":
		# the control: build the amplitude modifier over the LEGS, which is the one thing the
		# "arms only" argument rules out. It must fail `_legs`, and it should show up in the
		# skate number too.
		var probe := _body(_m, "legprobe")
		_m["arm_pose"] = _leg_roots(_m, probe._skeleton)
		probe.queue_free()
		_out["control_arm_pose"] = _m["arm_pose"]
	_on = _body(_m, "on")
	_on.jitter.spectrum = str(_opt.get("spectrum", "persistent"))
	_on.jitter.reset()
	_on.jitter_track = _f("track", 4.0)
	_on.jitter_track_lead = _opt.get("lead", "0") == "1"
	_on.jitter_naive = _opt.get("naive", "0") == "1"     # the control: it must drift
	_on.jitter_rate = _opt.get("rate", "0") == "1"       # the control: it must move the mean pace
	# the control for the gait-change path: with `switch=` it must drift
	_on.jitter_reanchor_target = _opt.get("reanchor", "") == "target"
	_out["jitter_track"] = _on.jitter_track
	_out["jitter_track_lead"] = _on.jitter_track_lead
	_out["tick"] = _dt
	_out["jitter_naive"] = _on.jitter_naive
	_out["jitter_rate"] = _on.jitter_rate
	_out["jitter_reanchor_target"] = _on.jitter_reanchor_target
	var mod: Node = _on.jitter_modifier()
	_out["modifier"] = mod.report if mod != null else {"built": false}
	_check(mod != null and bool(mod.report.get("built", false)),
			"%s the amplitude modifier is built over the arm chain (%s)"
			% [_who, mod.report if mod != null else "not built"])
	if mod != null:
		mod.lod_override = 0.0          # headless: there is no camera, so measure it up close
		# `lod_m=0` turns the gate off, which is the control for the LOD check: a gate that has
		# stopped gating must be seen.
		mod.lod_distance_m = _f("lod_m", 30.0)
	_legs(mod)
	_s_on = _sampler(_on)
	_s_off = _sampler(_off)
	_gap = []
	_tick = 0
	_short_ticks = int(round(_f("seconds", 60.0) / _dt))
	_total_ticks = maxi(int(round(_f("long", 300.0) / _dt)), _short_ticks)
	_short = {}
	_state = "drive"


func _fastest_walk(m: Dictionary) -> Dictionary:
	var gaits: Dictionary = m.get("gaits", {})
	for role in ["Walk", "Trot", "Run", "Amble", "Pace"]:
		if gaits.has(role) and m.get("clips", {}).has(role):
			return {"role": role, "speed": float(gaits[role].get("natural_speed_mps", 1.0))}
	return {}


# ------------------------------------------------------------------ 1. the spectrum

func _spectrum() -> void:
	var j := GaitJitter.from_moves(_m)
	j.spectrum = str(_opt.get("spectrum", "persistent"))
	j.reset()
	var n := int(_f("cycles", 4096.0))
	var a_phase: float = GaitJitter.dfa(j.series(n, "phase"))
	var a_amp: float = GaitJitter.dfa(j.series(n, "amp"))
	_out["dfa"] = {"phase": a_phase, "amp": a_amp, "cycles": n, "band": [ALPHA_MIN, ALPHA_MAX]}
	_check(a_phase >= ALPHA_MIN and a_phase <= ALPHA_MAX,
			"%s phase series DFA alpha %.3f in [%.2f, %.2f] over %d cycles (white noise reads 0.5)"
			% [_who, a_phase, ALPHA_MIN, ALPHA_MAX, n])
	_check(a_amp >= ALPHA_MIN and a_amp <= ALPHA_MAX,
			"%s amplitude series DFA alpha %.3f in [%.2f, %.2f] over %d cycles"
			% [_who, a_amp, ALPHA_MIN, ALPHA_MAX, n])
	# A random walk would also pass DFA at 1.0; this says the series stays bounded and near zero,
	# which is what stops the gait wandering away over a long run.
	var s := j.series(n, "phase")
	var mean := 0.0
	var worst := 0.0
	for v in s:
		mean += v
		worst = maxf(worst, absf(v))
	mean /= float(n)
	_out["series"] = {"mean": mean, "max_abs": worst}
	_check(absf(mean) < 0.6 and worst < 6.0,
			"%s phase series is bounded and centred (mean %.4f, max |x| %.2f)" % [_who, mean, worst])
	# What was just measured has to be the series the gait is driven by, not a lookalike: run the
	# live stream through advance_cycle() and compare knot for knot.
	var live := GaitJitter.from_moves(_m)
	live.spectrum = j.spectrum
	live.reset()
	live.advance_cycle()        # reset() has already drawn the pair either side of cycle 0
	var worst_gap := 0.0
	for i in 256:
		worst_gap = maxf(worst_gap, absf(live.last_knot("phase") - s[i]))
		live.advance_cycle()
	_out["series"]["live_gap"] = worst_gap
	_check(worst_gap < 1e-9,
			"%s the measured series is the one advance_cycle() drives the gait with (worst knot gap %s over 256 cycles)"
			% [_who, worst_gap])


# ------------------------------------------------------------------ 2. the key is absent

## `absent_on=<0..1>` is the control, and it is set only around this check so that the control
## fails THIS check and nothing else: with it, a manifest that carries no `variability` block
## resolves to that much jitter - which is what "off unless the manifest asks" must never mean.
func _absent(path: String) -> void:
	GaitJitter.absent_default = _f("absent_on", 0.0)
	_absent_body(path)
	GaitJitter.absent_default = 0.0


func _absent_body(path: String) -> void:
	var raw: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	var had: bool = raw.has("variability")
	var j := GaitJitter.from_moves(raw)
	var zeros: bool = not j.enabled() and j.phase_gain() == 0.0 and j.amp_gain() == 0.0 \
			and float(j.resolved["asymmetry"]) == 0.0
	_out["absent"] = {"manifest_had_variability": had, "enabled": j.enabled(),
			"resolved": j.resolved, "from_manifest": j.from_manifest}
	_check(had or (zeros and not j.from_manifest),
			"%s no `variability` in the shipped manifest -> all zeros, jitter off (the manifest had it: %s)"
			% [_who, had])
	var body := _body(raw, "absent")
	var role: String = body.play_gait_for(1.0, -1.0, TICK)
	var factor: float = body.jitter_factor(1.0, TICK)
	_out["absent"]["rate_factor"] = factor
	_out["absent"]["modifier"] = body.jitter_modifier() != null
	_check(body.jitter_modifier() == null and factor == 1.0,
			"%s with no `variability` the rate factor is exactly 1.0 and no modifier is built (playing %s)"
			% [_who, role])
	body.queue_free()


## The whole argument that amplitude jitter cannot add foot skate is that it scales ARMS: a leg
## whose rotation is scaled plants its foot somewhere else. Nothing checked it - `arm_pose`'s roots
## plus MAX_DEPTH were the only thing standing between the modifier and a thigh, and a manifest
## that named one would be caught, if at all, by the skate number rather than by name. So: walk up
## from every foot the manifest names, as far as the chain the arm roots hang from, and require
## that the modifier collected none of it. The CONTROL is `ctl=legs`, which rewrites `arm_pose` to
## name the leg roots before the modifier is built - the mistake this is watching for, made on
## purpose.
func _legs(mod: Node) -> void:
	var skel: Skeleton3D = _on._skeleton
	if mod == null or skel == null:
		_check(false, "%s no modifier or skeleton to check the arm chain on" % _who)
		return
	var feet := _foot_bones(_m, _role, skel)
	if feet.is_empty():
		_check(false, "%s the manifest names no foot to check the modifier against" % _who)
		return
	# Everything above the arm roots: where the leg chain stops being a leg and becomes the trunk.
	var trunk := {}
	for r in GaitJitterModifier.arm_roots(_m):
		var i := skel.find_bone(r)
		if i < 0:
			i = skel.find_bone(r.replace(".", "_"))
		while i >= 0:
			i = skel.get_bone_parent(i)
			if i >= 0:
				trunk[i] = true
	var leg := {}
	for f in feet:
		var i: int = f
		var guard := 0
		while i >= 0 and not trunk.has(i) and guard < 32:
			leg[i] = true
			i = skel.get_bone_parent(i)
			guard += 1
		_descend(skel, f, leg)
	var hit := PackedStringArray()
	for b in mod.bones:
		if leg.has(int(b)):
			hit.append(skel.get_bone_name(int(b)))
	_out["arm_only"] = {"leg_bones": leg.size(), "modifier_bones": mod.bones.size(),
			"in_a_leg": hit}
	_check(hit.is_empty(),
			"%s the modifier reaches no leg: 0 of its %d bones are in the %d-bone leg chain under %s (%s)"
			% [_who, mod.bones.size(), leg.size(), str(GaitJitterModifier.arm_roots(_m)),
			"none" if hit.is_empty() else str(hit)])


func _descend(skel: Skeleton3D, bone: int, into: Dictionary) -> void:
	into[bone] = true
	for c in skel.get_bone_children(bone):
		_descend(skel, c, into)


## The control for `_legs`: point `arm_pose` at the leg roots (two bones up from each foot, which
## is the thigh on every rig here), so the modifier builds over the legs.
func _leg_roots(m: Dictionary, skel: Skeleton3D) -> Dictionary:
	var per := {}
	for f in _foot_bones(m, _role, skel):
		var i: int = f
		for _d in 2:
			var up := skel.get_bone_parent(i)
			if up >= 0:
				i = up
		per[skel.get_bone_name(i)] = {}
	return {"Walk": per}


# ------------------------------------------------------------------ 3-5. driven on real frames

func _sampler(body: MovesController) -> Dictionary:
	var skel: Skeleton3D = body._skeleton
	var watched := PackedInt32Array([_deepest_arm_bone(body, skel)])
	var feet := _foot_bones(_m, _role, skel)
	for k in mini(feet.size(), 2):
		watched.append(feet[k])
	var probe := PoseProbe.new()
	probe.name = "pose_probe"
	probe.bones = watched
	probe.world = skel.global_transform if skel else Transform3D()
	probe.at.resize(watched.size())
	for i in watched.size():
		probe.at[i] = Vector3.ZERO
	if skel != null:
		skel.add_child(probe)        # after the jitter modifier: it sees the modified pose
	return {"body": body, "skel": skel, "probe": probe, "watched": watched,
			"last_u": -1.0, "t": 0.0, "travelled": 0.0, "wraps": [], "cycle_amp": [],
			"sa": 0.0, "sb": 0.0, "sn": 0, "foot_xz": [[], []]}


func _switching() -> bool:
	return _f("switch", 0.0) > 0.0


## Whether the one-clip, one-cycle checks can be measured at all this run. Two clips alternating
## under `switch=` are not one cycle; and a tick coarser than the frame is too few samples per
## cycle for the stride wrap and the first-harmonic arm-swing estimators (at `tick=0.0667` a
## perfectly periodic swing already reads cv 0.0167, past the 0.01 floor the check rests on). Both
## modes exist for the drift checks, which the tick and the gait change are what can break.
func _cycle_checks() -> bool:
	return not _switching() and _dt <= TICK * 1.5


func _step(_delta: float) -> void:
	var delta := _dt
	if _switching():
		var half := _f("switch", 0.0)
		var phase := int(floor((float(_tick) * _dt) / half))
		var want: float = _speed if phase % 2 == 0 else _speed2
		if want != _speed_now:
			_switches += 1
		_speed_now = want
	_sample(_s_on)
	_sample(_s_off)
	_advance(_s_on, delta)
	_advance(_s_off, delta)
	_tick += 1
	if _tick % 60 == 0 or _tick >= _total_ticks:
		var c_off := _played(_s_off)
		_gap.append(Vector2(c_off, _played(_s_on) - c_off))
	if _tick == _short_ticks:
		_short = {"on": _snapshot(_s_on), "off": _snapshot(_s_off)}
	if _tick >= _total_ticks:
		_finish()


## Read the pose the engine settled on at the end of the previous frame - after the skeleton's
## modifier pass, which is the whole reason this runs on frames at all.
func _sample(s: Dictionary) -> void:
	var probe: PoseProbe = s["probe"]
	var watched: PackedInt32Array = s["watched"]
	var u: float = s["last_u"]
	if probe == null or probe.frames == 0 or u < 0.0:
		return
	if watched[0] >= 0:
		# Arm swing per cycle as the first Fourier harmonic of the hand's fore-aft travel, not its
		# min/max: a per-tick extreme is quantised by where the 60 Hz samples fall in the cycle,
		# which on its own reads as 0.7% of "variation" on a clip that has none.
		var p: Vector3 = probe.at[0]
		s["sa"] = float(s["sa"]) + p.z * cos(TAU * u)
		s["sb"] = float(s["sb"]) + p.z * sin(TAU * u)
		s["sn"] = int(s["sn"]) + 1
	if _tick >= _short_ticks:
		return                                  # feet are only measured over the first window
	for k in range(1, watched.size()):
		var fp: Vector3 = probe.at[k]
		s["foot_xz"][k - 1].append(Vector3(fp.x, fp.y, fp.z + float(s["travelled"])))


func _advance(s: Dictionary, delta: float) -> void:
	var body: MovesController = s["body"]
	var anim: AnimationPlayer = body._anim
	body.play_gait_for(_speed_now, -1.0, delta)
	anim.advance(delta)
	s["t"] = float(s["t"]) + delta
	s["travelled"] = float(s["travelled"]) + _speed_now * delta
	var len_s: float = anim.current_animation_length
	var u: float = fposmod(anim.current_animation_position / len_s, 1.0) if len_s > 0.0 else 0.0
	var last_u: float = s["last_u"]
	if last_u >= 0.0 and u < last_u:
		var wraps: Array = s["wraps"]
		# The run starts mid-cycle, so the first window is a partial one: skip it rather than let
		# it read as variation the clip does not have.
		if int(s["sn"]) > 8 and not wraps.is_empty():
			s["cycle_amp"].append(2.0 * Vector2(float(s["sa"]) / float(s["sn"]),
					float(s["sb"]) / float(s["sn"])).length())
		s["sa"] = 0.0
		s["sb"] = 0.0
		s["sn"] = 0
		# Where inside this frame the playhead crossed the loop, so a stride interval is not
		# quantised to 1/60 s - which is 1.7% of a stride and would swamp the jitter.
		var span: float = (1.0 - last_u) + u
		var frac: float = (1.0 - last_u) / span if span > 0.0 else 0.0
		wraps.append(float(s["t"]) - delta + frac * delta)
	s["last_u"] = u


## The playhead as the AnimationPlayer itself reports it, in cycles.
func _played(s: Dictionary) -> float:
	return float((s["wraps"] as Array).size()) + float(s["last_u"])


## The playhead as the AnimationPlayer itself reports it, in cycles, plus the per-cycle series.
func _snapshot(s: Dictionary) -> Dictionary:
	var wraps: Array = s["wraps"]
	var iv := []
	for i in range(1, wraps.size()):
		iv.append(wraps[i] - wraps[i - 1])
	return {"played": float(wraps.size()) + float(s["last_u"]), "intervals": iv,
			"cycle_amp": (s["cycle_amp"] as Array).duplicate(), "seconds": float(s["t"])}


func _deepest_arm_bone(body: MovesController, skel: Skeleton3D) -> int:
	if skel == null:
		return -1
	for r in GaitJitterModifier.arm_roots(body._m):
		var i: int = skel.find_bone(r)
		if i < 0:
			i = skel.find_bone(r.replace(".", "_"))
		if i < 0:
			continue
		for _d in 2:
			var kids := skel.get_bone_children(i)
			if kids.is_empty():
				break
			i = kids[0]
		return i
	return -1


func _foot_bones(m: Dictionary, role: String, skel: Skeleton3D) -> Array:
	var out := []
	if skel == null:
		return out
	for f in m.get("contacts", {}).get(role, {}).get("feet", []):
		var n := str(f.get("bone", ""))
		var i := skel.find_bone(n)
		if i < 0:
			i = skel.find_bone(n.replace(".", "_"))
		if i >= 0:
			out.append(i)
	return out


## Horizontal travel of a foot while it is planted: mean and worst over the stance runs. The
## absolute number includes the ankle rolling heel to toe, which is not skate; what matters is
## that the same estimator reads no worse with jitter than without.
func _skate(samples: Array) -> Dictionary:
	var low := INF
	for p in samples:
		low = minf(low, p.y)
	var runs := []
	var cur := []
	for p in samples:
		if p.y <= low + PLANT_M:
			cur.append(p)
		elif not cur.is_empty():
			runs.append(cur)
			cur = []
	if not cur.is_empty():
		runs.append(cur)
	var worst := 0.0
	var total := 0.0
	var n := 0
	for r in runs:
		if r.size() < 4:
			continue
		var x0 := INF
		var x1 := -INF
		var z0 := INF
		var z1 := -INF
		for p in r:
			x0 = minf(x0, p.x)
			x1 = maxf(x1, p.x)
			z0 = minf(z0, p.z)
			z1 = maxf(z1, p.z)
		var d := Vector2(x1 - x0, z1 - z0).length()
		worst = maxf(worst, d)
		total += d
		n += 1
	return {"worst_m": worst, "mean_m": total / float(maxi(n, 1)), "stances": n}


func _cv(a: Array) -> float:
	if a.size() < 2:
		return 0.0
	var mean := 0.0
	for v in a:
		mean += v
	mean /= float(a.size())
	if mean == 0.0:
		return 0.0
	var var_ := 0.0
	for v in a:
		var_ += (v - mean) * (v - mean)
	return sqrt(var_ / float(a.size())) / mean


func _mean(a: Array) -> float:
	if a.is_empty():
		return 0.0
	var s := 0.0
	for v in a:
		s += v
	return s / float(a.size())


# ------------------------------------------------------------------ the verdict

func _finish() -> void:
	var on: Dictionary = _short["on"]
	var off: Dictionary = _short["off"]
	var long_on := _snapshot(_s_on)
	var long_off := _snapshot(_s_off)
	var mod: Node = _on.jitter_modifier()

	# ---- 3. it varies, and the mean pace does not
	var cv_on := _cv(on["intervals"])
	var cv_off := _cv(off["intervals"])
	var amp_on := _cv(on["cycle_amp"])
	var amp_off := _cv(off["cycle_amp"])
	_out["stride"] = {"cv_on": cv_on, "cv_off": cv_off, "strides": (on["intervals"] as Array).size(),
			"mean_interval_on": _mean(on["intervals"]), "mean_interval_off": _mean(off["intervals"]),
			"seconds": on["seconds"]}
	_out["amplitude"] = {"cv_on": amp_on, "cv_off": amp_off, "cycles": (on["cycle_amp"] as Array).size(),
			"swing_on_m": _mean(on["cycle_amp"]), "swing_off_m": _mean(off["cycle_amp"]),
			"modifier_frames": mod.counters() if mod != null else {},
			"probe_frames": (_s_on["probe"] as PoseProbe).frames}
	var pace := absf(_mean(on["intervals"]) / maxf(_mean(off["intervals"]), 1e-9) - 1.0)
	_out["stride"]["mean_pace_error"] = pace
	if not _cycle_checks():
		# Two clips of different lengths, alternating: "the stride interval" is not one quantity
		# here and a cv over it would measure the ladder, not the jitter. This mode exists for the
		# drift checks below, which are the ones the gait-change path can break. The five cycle
		# checks and the skate check are SKIPPED, by name and with their raw measurements beside
		# them, rather than passed with a bound they did not meet.
		if _switching():
			_out["switched_gaits"] = _switches
			_check(_switches >= 2, "%s the gait changed %d times during the run (%.1f m/s <-> %.1f m/s)"
					% [_who, _switches, _speed, _speed2])
		_skip("%s at tick %.4f s under `switch=%.1f` the one-clip checks do not apply and are not run: stride interval off (cv %.6f) and on (cv %.4f), arm swing off (cv %.5f) and on (cv %.4f), mean pace (%.4f%% off), planted-foot travel. Each of these measures the gait ladder or the sampling, not the jitter; the drift checks below are what these modes are for."
				% [_who, _dt, _f("switch", 0.0), cv_off, cv_on, amp_off, amp_on, 100.0 * pace])
	else:
		_check(cv_off < NO_VARY, "%s jitter off: stride interval is exactly periodic (cv %.6f < %.5f over %d strides)"
				% [_who, cv_off, NO_VARY, (off["intervals"] as Array).size()])
		_check(cv_on > VARY_MIN, "%s jitter on: stride interval varies (cv %.4f > %.4f over %d strides, mean %.4f s)"
				% [_who, cv_on, VARY_MIN, (on["intervals"] as Array).size(), _mean(on["intervals"])])
		_check(amp_off < AMP_FLOOR, "%s jitter off: arm swing is periodic to the estimator's floor (cv %.5f < %.3f, swing %.4f m)"
				% [_who, amp_off, AMP_FLOOR, _mean(off["cycle_amp"])])
		_check(amp_on > VARY_MIN and amp_on > amp_off * AMP_RATIO,
				"%s jitter on: arm swing varies cycle to cycle (cv %.4f, %.1fx the off run's %.5f floor, swing %.4f m over %d cycles)"
				% [_who, amp_on, amp_on / maxf(amp_off, 1e-9), amp_off, _mean(on["cycle_amp"]), (on["cycle_amp"] as Array).size()])
		_check(pace < 0.01, "%s mean stride time is unchanged by jitter (%.4f%% off the unjittered mean)"
				% [_who, 100.0 * pace])

	# ---- 4. no drift, measured on the two runs' real playheads
	# One constant, not a literal that happens to match it: the bound IS the clamp the generator
	# draws under. Which also means `worst_gap <= bound` cannot fail on the shipped path because a
	# knot came out too big - it is bounded by construction there. What it still has teeth against
	# is a change of MECHANISM, which is what `naive=1` supplies and what it must catch.
	var bound: float = _on.jitter.phase_gain() * GaitJitter.KNOT_MAX
	var d_short: float = absf(float(on["played"]) - float(off["played"]))
	var d_long: float = absf(float(long_on["played"]) - float(long_off["played"]))
	var hz := maxf(float(_m.get("gaits", {}).get(_role, {}).get("stride_frequency_hz", 1.0)), 0.01)
	# The whole run, not two endpoints: the largest gap it ever reached, and the trend fitted
	# through every sample, carried over the run. Both are free numbers in the report.
	var worst_gap := 0.0
	for g in _gap:
		worst_gap = maxf(worst_gap, absf((g as Vector2).y))
	var fitted := _fitted_drift()
	_out["drift"] = {"cycles_at_short": d_short, "seconds_short": float(on["seconds"]),
			"cycles_at_long": d_long, "seconds_long": float(long_on["seconds"]),
			"played_on": long_on["played"], "played_off": long_off["played"],
			"bound_cycles": bound, "metres_at_long": d_long * _speed / hz,
			"worst_gap_cycles": worst_gap, "fitted_drift_cycles": fitted,
			"samples": _gap.size(), "controller_drift": float(_on.jitter_state()["drift"]),
			"worst_offset_cycles": float(_on.jitter_state()["worst_offset"]),
			"worst_lag_cycles": float(_on.jitter_state()["worst_lag"])}
	# Both halves of the gap, free: how large an offset the generator actually COMMANDED (the
	# bound is what it is allowed to command) and how far the playhead ever lagged that command.
	# A worst gap near the bound with a small lag is a long run that drew a large knot, which is
	# the mechanism working; the same number with a large lag would be the controller slipping.
	_check(worst_gap <= bound,
			"%s the jittered playhead stays inside the offset bound over %d cycles (worst gap %.4f <= %.4f cycles, %.3f m of ground; it ends at %.4f; of that gap the commanded offset reached %.4f and the tracking lag %.4f)"
			% [_who, int(float(long_off["played"])), worst_gap, bound,
			worst_gap * _speed / hz, d_long,
			float(_on.jitter_state()["worst_offset"]), float(_on.jitter_state()["worst_lag"])])
	_check(absf(fitted) <= bound,
			"%s the gap does not grow with the run (the trend through %d samples carries %+.4f cycles over %.0f s, bound %.4f; the gap reads %.4f at %.0f s and %.4f at the end)"
			% [_who, _gap.size(), fitted, float(long_on["seconds"]), bound, d_short,
			float(on["seconds"]), d_long])

	# ---- 5. no more foot skate
	var sk_on := {"worst_m": 0.0, "mean_m": 0.0, "stances": 0}
	var sk_off := sk_on.duplicate()
	for k in 2:
		var a := _skate(_s_on["foot_xz"][k])
		var b := _skate(_s_off["foot_xz"][k])
		if float(a["worst_m"]) > float(sk_on["worst_m"]):
			sk_on = a
		if float(b["worst_m"]) > float(sk_off["worst_m"]):
			sk_off = b
	var ratio := _f("skate_ratio", 1.25)
	_out["skate"] = {"on": sk_on, "off": sk_off, "ratio": ratio}
	if not _cycle_checks():
		pass                                  # named in the SKIP line above, with the others
	elif int(sk_off["stances"]) > 0:
		var ok: bool = float(sk_on["worst_m"]) <= float(sk_off["worst_m"]) * ratio + 0.0001 \
				and float(sk_on["mean_m"]) <= float(sk_off["mean_m"]) * ratio + 0.0001
		_check(ok, "%s planted-foot travel is no worse with jitter (mean %.4f m on / %.4f off, worst %.4f / %.4f, over %d/%d stances)"
				% [_who, sk_on["mean_m"], sk_off["mean_m"], sk_on["worst_m"], sk_off["worst_m"],
				sk_on["stances"], sk_off["stances"]])
	else:
		_check(false, "%s no stance run found to measure foot skate on" % _who)

	# ---- 6. what it costs
	var cost := _cost(_on, mod)
	_out["cost_us_per_frame"] = cost
	_check(float(cost["phase"]) < COST_PHASE_US,
			"%s phase warp costs %.3f us per character per frame (%.3f net of the call; ceiling %.0f)"
			% [_who, cost["phase"], cost["phase_net"], COST_PHASE_US])
	_check(float(cost["amp"]) < COST_AMP_US,
			"%s amplitude modifier costs %.3f us per character per frame over %d bones (%.3f net; ceiling %.0f)"
			% [_who, cost["amp"], cost["bones"], cost["amp_net"], COST_AMP_US])

	# ---- 7. LOD
	if mod != null:
		mod.lod_override = mod.lod_distance_m * 3.0 + 100.0
		var before: int = int(mod.counters()["applied"])
		for i in 60:
			mod._process_modification_with_delta(TICK)
		var far_applied: int = int(mod.counters()["applied"]) - before
		mod.lod_override = 1.0
		before = int(mod.counters()["applied"])
		for i in 60:
			mod._process_modification_with_delta(TICK)
		var near_applied: int = int(mod.counters()["applied"]) - before
		_out["lod"] = {"applied_far": far_applied, "applied_near": near_applied,
				"distance_m": mod.lod_distance_m}
		_check(far_applied == 0 and near_applied == 60,
				"%s LOD: the amplitude modifier runs %d/60 frames at 1 m and %d/60 past %.0f m"
				% [_who, near_applied, far_applied, mod.lod_distance_m])

	print("RA_JITTER %s" % JSON.stringify(_out))
	_on.queue_free()
	_off.queue_free()
	_on = null
	_off = null
	_state = "next"


## Least squares through the (cycles, gap) samples, times the cycles the run covered: how far the
## gap would have moved if the trend in it were real. A bounded wander fits a slope near zero
## whatever its endpoints happen to be; an accumulating error fits its own rate.
func _fitted_drift() -> float:
	var n := _gap.size()
	if n < 3:
		return 0.0
	var mx := 0.0
	var my := 0.0
	for g in _gap:
		mx += (g as Vector2).x
		my += (g as Vector2).y
	mx /= float(n)
	my /= float(n)
	var num := 0.0
	var den := 0.0
	for g in _gap:
		var dx: float = (g as Vector2).x - mx
		num += dx * ((g as Vector2).y - my)
		den += dx * dx
	if den <= 0.0:
		return 0.0
	var span: float = (_gap[n - 1] as Vector2).x - (_gap[0] as Vector2).x
	return num / den * span


## Time the two pieces of per-frame work on their own, over enough calls that the clock is not the
## measurement, and against the same loop around a do-nothing call.
func _cost(body: MovesController, mod: Node) -> Dictionary:
	# The best of three passes, not the mean: a timing is a minimum plus whatever the machine was
	# doing, and the mean measures the machine.
	var n := 20000
	var phase_us := INF
	var amp_us := INF if mod != null else 0.0
	var base_us := INF
	if mod != null:
		mod.lod_override = 0.0
	for _pass in 3:
		var t0 := Time.get_ticks_usec()
		for i in n:
			body.jitter_factor(1.0, TICK)
		phase_us = minf(phase_us, float(Time.get_ticks_usec() - t0) / float(n))
		if mod != null:
			var t1 := Time.get_ticks_usec()
			for i in n:
				mod._process_modification_with_delta(TICK)
			amp_us = minf(amp_us, float(Time.get_ticks_usec() - t1) / float(n))
		var t2 := Time.get_ticks_usec()
		for i in n:
			_noop()
		base_us = minf(base_us, float(Time.get_ticks_usec() - t2) / float(n))
	return {"phase": phase_us, "amp": amp_us, "total": phase_us + amp_us,
			"phase_net": maxf(phase_us - base_us, 0.0), "amp_net": maxf(amp_us - base_us, 0.0),
			"call_overhead": base_us, "calls": n,
			"bones": mod.bones.size() if mod != null else 0}


func _noop() -> void:
	pass
