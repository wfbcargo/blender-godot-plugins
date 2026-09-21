extends SceneTree
## Play each gait clip of a `.moves.json` and measure the body's own left against its right off the
## PLAYING skeleton with `AsymmetryMeter` (asymmetry_meter.gd) - arm swing, step length, stride,
## shoulder dip (over the hips, and in a frame riding the chest) and arm lag, per side.
##
##   godot --headless --path <project> -s res://addons/rig_anything/verify_asymmetry.gd -- \
##       manifests=res://a.moves.json[,res://b.moves.json]  [clips=Walk,Run] [cycles=12]
##       [swap=1] [poison=1] [floor_index=0.04] [floor_lag=0.012] [stride_index=0.02]
##
## Per clip it prints one `RA_ASYM` row per channel (+lat, -lat, ratio, index), a
## `RA_ASYM_REPORT {json}` line with the whole report (regress reads that one), and two checks:
##
##   stride     each foot travels the same distance off the hips on both sides: stride_m's index
##              under `stride_index`. The no-skate invariant - a planted foot that swept further
##              than the other in the same time would slide.
##   asymmetric the body reads a non-zero index on every channel the draw moves: arm_swing_deg and
##              shoulder_dip_m over `floor_index`, and |lag_cycles diff| over `floor_lag`. A
##              symmetric body (asymmetry 0, or the RA_ASYM_MIRROR=1 bake) MUST fail this one.
##              Step length is not in it: a body's own feet can already plant apart (the fixture
##              Figure's do, by 10 mm), so its index is not zero at asymmetry 0. regress judges
##              it on how far `stance_offset_m` MOVED against the asymmetry-0 build instead.
##
## The floors are the fixture's (tests/fixtures/asym_meter.py), passed in by regress so the bake
## and the engine judge on one number; the defaults here are the same values. Whether the engine
## agrees with the bake-time `variability.measure` on the same clip is judged by regress on the
## Python side, from RA_ASYM_REPORT - never by reading bake numbers in here.
##
## Controls:
##   swap=1    the meter is told +lat is -lat. Every ratio must invert and stance_offset flip.
##   poison=1  the meter gets a copy of the manifest whose `variability` block, `arm_pose` values,
##             `gaits` and stance spans are rewritten; the numbers must not move by one digit (the
##             row prints a hash of the report so regress can compare the two runs exactly).
##
## Prints RA_ASYM VERIFY PASSED / FAILED; exits 1 on a failed check.

const TICK := 1.0 / 60.0
const FLOOR_INDEX := 0.04
const FLOOR_LAG := 0.012
const STRIDE_INDEX := 0.02

var _fails := []


func _initialize() -> void:
	var o := {"manifests": [], "clips": ["Walk", "Run"], "cycles": 12, "swap": false, "poison": false,
		"floor_index": FLOOR_INDEX, "floor_lag": FLOOR_LAG, "stride_index": STRIDE_INDEX, "tick": TICK}
	for a in OS.get_cmdline_user_args():
		var kv := String(a).split("=", true, 1)
		if kv.size() < 2:
			continue
		match kv[0]:
			"manifests": o["manifests"] = Array(kv[1].split(",", false))
			"clips": o["clips"] = Array(kv[1].split(",", false))
			"cycles": o["cycles"] = int(kv[1])
			"swap": o["swap"] = kv[1] == "1" or kv[1] == "true"
			"poison": o["poison"] = kv[1] == "1" or kv[1] == "true"
			"floor_index": o["floor_index"] = float(kv[1])
			"floor_lag": o["floor_lag"] = float(kv[1])
			"stride_index": o["stride_index"] = float(kv[1])
			"tick": o["tick"] = float(kv[1])
	if o["manifests"].is_empty():
		print("RA_ASYM VERIFY: give manifests=<res://a.moves.json,...>")
		quit(2)
		return
	_run.call_deferred(o)


func _check(ok: bool, what: String) -> void:
	print("RA_ASYM  %s  %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		_fails.append(what)


func _run(o: Dictionary) -> void:
	for p in o["manifests"]:
		_verify(String(p), o)
	print("RA_ASYM VERIFY %s" % ("PASSED" if _fails.is_empty() else "FAILED: %d checks" % _fails.size()))
	quit(0 if _fails.is_empty() else 1)


## What the meter may not read, rewritten: if any of it reached a number, that number moves.
func _poisoned(m: Dictionary) -> Dictionary:
	var p: Dictionary = m.duplicate(true)
	p["variability"] = {"seed": 1, "asymmetry": 1.0, "jitter_phase": 1.0, "jitter_amp": 1.0}
	for clip in p.get("arm_pose", {}):
		for b in p["arm_pose"][clip]:
			p["arm_pose"][clip][b] = {"arm_swing_deg": 999.0, "arm_carry_deg": [-99.0, 99.0]}
	for g in p.get("gaits", {}):
		p["gaits"][g] = {"natural_speed_mps": 99.0, "stride_m": 99.0, "stride_frequency_hz": 99.0}
	for g in p.get("contacts", {}):
		for f in p["contacts"][g].get("feet", []):
			f["stance"] = [[0.25, 0.3]]
			f["duty_factor"] = 0.01
			f["length"] = 9.0
	p["implied_speed_mps"] = {}
	p["arm_gait"] = {}
	return p


func _verify(path: String, o: Dictionary) -> void:
	var body := MovesController.new()
	body.manifest_path = path
	root.add_child(body)
	body.set_physics_process(false)
	var anim: AnimationPlayer = body._anim
	var skel: Skeleton3D = body._skeleton
	var who := String(body.display_name)
	if anim == null or skel == null:
		_check(false, "%s: no AnimationPlayer or Skeleton3D in %s" % [who, path])
		body.free()
		return
	anim.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var manifest: Dictionary = body._m
	var given: Dictionary = _poisoned(manifest) if o["poison"] else manifest
	for role in o["clips"]:
		var clip := String(manifest.get("clips", {}).get(role, ""))
		if clip == "" or not anim.has_animation(clip):
			print("RA_ASYM %s: no %s clip, skipped" % [who, role])
			continue
		anim.play(clip, 0.0)
		anim.speed_scale = 1.0
		anim.seek(0.0, true)
		var meter := AsymmetryMeter.new(skel, given)
		meter.swap_sides = o["swap"]
		var length := anim.get_animation(clip).length
		# whole cycles plus one tick, so the last one completes
		var ticks := int(ceil((float(o["cycles"]) * length) / float(o["tick"]))) + 2
		for t in ticks:
			meter.sample(fposmod(anim.current_animation_position / length, 1.0))
			anim.advance(float(o["tick"]))
		var r := meter.report()
		_print_rows(who, role, clip, r)
		print("RA_ASYM_REPORT %s" % JSON.stringify({"who": who, "manifest": path, "role": role, "clip": clip,
			"swap": o["swap"], "poison": o["poison"], "hash": JSON.stringify(_numbers(r)).hash(),
			"report": _plain(r)}))
		for p in r["problems"]:
			_check(false, "%s %s: %s" % [who, role, p])
		var st: Dictionary = r.get("stride_m", {})
		_check(not st.is_empty() and float(st["index"]) < float(o["stride_index"]),
			"%s %s: stride is even on both sides (index %.5f < %.3f; +lat %.5f m, -lat %.5f m)" % [
				who, role, float(st.get("index", -1.0)), o["stride_index"],
				float(st.get("plus_lat", 0.0)), float(st.get("minus_lat", 0.0))])
		var arm: Dictionary = r.get("arm_swing_deg", {})
		var dip: Dictionary = r.get("shoulder_dip_m", {})
		var lag: Dictionary = r.get("lag_cycles", {})
		var asym := (not arm.is_empty() and float(arm["index"]) > float(o["floor_index"])
			and not dip.is_empty() and float(dip["index"]) > float(o["floor_index"])
			and not lag.is_empty() and absf(float(lag["diff"])) > float(o["floor_lag"]))
		_check(asym, "%s %s: is asymmetric (arm swing index %.5f, shoulder dip index %.5f > %.3f; |lag diff| %.5f > %.4f cycles)" % [
			who, role, float(arm.get("index", 0.0)), float(dip.get("index", 0.0)), o["floor_index"],
			absf(float(lag.get("diff", 0.0))), o["floor_lag"]])
	body.free()


func _print_rows(who: String, role: String, clip: String, r: Dictionary) -> void:
	print("RA_ASYM %s %s (%s): %d whole cycles, %d samples%s" % [who, role, clip, r["cycles"], r["samples"],
		"  [sides swapped]" if r.get("swap_sides", false) else ""])
	print("RA_ASYM   %-21s %11s %11s %9s %9s" % ["channel", "+lat", "-lat", "ratio", "index"])
	for c in AsymmetryMeter.CHANNELS:
		var v: Dictionary = r.get(c, {})
		if v.is_empty():
			print("RA_ASYM   %-21s  (not measured)" % c)
			continue
		print("RA_ASYM   %-21s %11.5f %11.5f %9s %9.5f" % [c, v["plus_lat"], v["minus_lat"],
			"-" if v["ratio"] == null else "%.5f" % v["ratio"], v["index"]])
	if r.has("stance_offset_m"):
		print("RA_ASYM   %-21s %+11.5f m" % ["stance_offset", r["stance_offset_m"]])
	for c in r.get("fourier", {}):
		var f: Dictionary = r["fourier"][c]
		print("RA_ASYM   %-21s first harmonic +lat %.5f -lat %.5f (peak-to-peak above)" % [
			c, f["plus_lat_amp"], f["minus_lat_amp"]])


## Only the numbers a channel reports, for the poison control's exact comparison.
func _numbers(r: Dictionary) -> Dictionary:
	var out := {"stance_offset_m": r.get("stance_offset_m", null), "fourier": r.get("fourier", {})}
	for c in AsymmetryMeter.CHANNELS:
		out[c] = r.get(c, {})
	return out


## Vectors as arrays, so the report is JSON.
func _plain(v: Variant) -> Variant:
	if v is Dictionary:
		var d := {}
		for k in v:
			d[str(k)] = _plain(v[k])
		return d
	if v is Array or v is PackedStringArray:
		return Array(v).map(func(x): return _plain(x))
	if v is Vector3:
		return [v.x, v.y, v.z]
	return v
