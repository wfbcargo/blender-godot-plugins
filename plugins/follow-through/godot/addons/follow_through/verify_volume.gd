extends SceneTree
## Run an imported asset's follow-through volumes and flesh in Godot, and measure them.
##
##   godot --headless --path <project> -s res://addons/follow_through/verify_volume.gd -- \
##       scene=res://assets/volumes/volume_samples.glb frames=360 tune=true
##   godot --headless --path <project> -s res://addons/follow_through/verify_volume.gd -- \
##       scene=res://assets/flesh/bloater.glb
##
## Shape-matching volumes (jello, clay, slime, balloons), each against a limit:
##   finite            no NaN or inf in the lattice
##   volume_ratio      render-mesh volume at the end over at the start      0.85 - 1.15
##                     (plastic materials 0.75 - 1.25: they flow, and keep their volume only roughly)
##   inside_fraction   render vertices inside a collider at the end          <= 0.05
##   settle_mps        fastest render vertex's travel over half a second, in the last half second <= 0.1
##   pin_error_m       pinned lattice nodes against their anchors            <= 0.005
##   frequency         with tune=true: the body held at its base and sheared, zero gravity,
##                     no colliders; measured wobble against frequency_hz    within 35%
##                     reports recommended_stiffness_gain (write it back with volume.set_params)
##   ms_per_tick       reported, not limited
##
## Flesh (jiggle bones), per region:
##   head_error_m      bone rest head against the spec                       <= 0.01
##   axis_off_y        tail off the bone's local Y (squash needs it on Y)     <= 0.02
##   frequency         after a kick, zero crossings of the offset             within 20% of frequency_hz
##                     (regions that ring: damping_ratio < 0.5)
##   settles           offset under 10% of its peak within 5 time constants (1 / (zeta w))
##   within_limit      offset never past max_offset_m while the clip plays
##   finite
##
## colliders=auto gives every unskinned mesh without a spec a convex collider (AnimatableBody3D,
## so a moved prop carries what rests on it); colliders=none tests the bodies alone.
## Prints one `FT_RESULT {json}` line per body, then `FT_SUMMARY ... PASSED|FAILED`.

const FollowThrough = preload("res://addons/follow_through/follow_through.gd")

var args := {}
var scene_path := ""
var frames := 360
var tune := false
var colliders := "auto"
var set_all := {}

var phase := "run"                  # run -> tune -> kick -> done
var instance: Node3D
var frame := 0
var volumes: Array = []             # {body, rest_volume, prev, speeds, pin_error, ms, ...}
var flesh: Array = []               # {mod, rep, series, peak...}
var results := {}
var tune_queue: Array = []
var tune_state := {}
var started := false


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.split("=", true, 1)
		if kv.size() == 2:
			args[kv[0]] = kv[1]
	scene_path = args.get("scene", "")
	frames = int(args.get("frames", "360"))
	tune = args.get("tune", "false") == "true"
	colliders = args.get("colliders", "auto")
	if args.has("set"):
		for pair in args["set"].split(","):
			var kv2: PackedStringArray = pair.split(":")
			set_all[kv2[0]] = float(kv2[1])
	if scene_path == "":
		printerr("verify_volume: pass scene=res://...")
		quit(2)


func _start() -> void:
	var packed: PackedScene = load(scene_path)
	if packed == null:
		printerr("verify_volume: cannot load " + scene_path)
		quit(2)
		return
	instance = packed.instantiate()
	root.add_child(instance)
	if colliders == "auto":
		_add_colliders(instance)
	for rep in FollowThrough.apply(instance, {"overrides": set_all, "routes": ["shape_matching", "jiggle_bones"]}):
		var name := String(rep["node"])
		if not rep.get("built", false):
			results[name] = {"node": name, "route": rep.get("route"), "built": false,
				"problems": rep.get("problems", []), "passed": false}
			continue
		if rep["route"] == "shape_matching":
			var body = rep["body"]
			volumes.append({"name": name, "body": body, "rep": rep, "rest_volume": body.mesh_volume(),
				"prev": body.surface_positions(), "speeds": [], "pin_error": 0.0, "ms": 0.0,
				"finite": true, "plastic": body.plastic_yield > 0.0})
		else:
			var mod = rep["body"]
			flesh.append({"name": name, "mod": mod, "rep": rep, "worst_offset": {}, "finite": true})
	var players := instance.find_children("*", "AnimationPlayer", true, false)
	if not players.is_empty():
		var ap: AnimationPlayer = players[0]
		var clips := ap.get_animation_list()
		if not clips.is_empty():
			ap.get_animation(clips[0]).loop_mode = Animation.LOOP_LINEAR
			ap.play(clips[0])


func _add_colliders(node: Node) -> void:
	for n in node.find_children("*", "MeshInstance3D", true, false):
		var mi: MeshInstance3D = n
		if not FollowThrough.spec_of(mi).is_empty() or mi.skin != null or mi.mesh == null:
			continue
		# Convex, not a trimesh: a trimesh has no inside, so a vertex that crossed a floor
		# slab's top face within one tick was never in contact again - every loose sample
		# volume fell through the floor at 59 m/s. Props here are convex; concave scenery
		# needs its own convex pieces.
		var hull := mi.mesh.create_convex_shape(true, false)
		if hull == null:
			continue
		var body := AnimatableBody3D.new()
		var shape := CollisionShape3D.new()
		shape.shape = hull
		body.add_child(shape)
		mi.add_child(body)


func _physics_process(delta: float) -> bool:
	if not started:
		started = true
		_start()
		return false
	match phase:
		"run":
			_run_tick(delta)
		"tune":
			_tune_tick(delta)
		"kick":
			_kick_tick(delta)
	return false


# ------------------------------------------------------------------ the plain run

func _run_tick(delta: float) -> void:
	frame += 1
	for v in volumes:
		var body = v["body"]
		var now: PackedVector3Array = body.surface_positions()
		for i in now.size():
			if not now[i].is_finite():
				v["finite"] = false
		# settling is judged on half a second of travel, not one tick: contacts buzz a few
		# millimetres tick to tick (a resting water balloon's bottom read 0.3 m/s per tick and
		# went nowhere), while drift, rocking and ringing all show over 30 ticks
		var history: Array = v.get("history", [])
		history.append(now)
		if history.size() > 31:
			history.pop_front()
		v["history"] = history
		if history.size() == 31:
			var old: PackedVector3Array = history[0]
			var fastest := 0.0
			for i in now.size():
				fastest = maxf(fastest, now[i].distance_to(old[i]) / (30.0 * delta))
			v["speeds"].append(fastest)
		v["prev"] = now
		if frame > frames - 30:
			var pins: PackedInt32Array = body.pinned_nodes()
			for k in pins.size():
				v["pin_error"] = maxf(v["pin_error"], body.x[pins[k]].distance_to(body.pin_target(k)))
	for f in flesh:
		var offs: Dictionary = f["mod"].region_offsets()
		for rname in offs:
			var d: float = (offs[rname]["offset"] as Vector3).length()
			if is_nan(d) or is_inf(d):
				f["finite"] = false
			f["worst_offset"][rname] = maxf(f["worst_offset"].get(rname, 0.0), d)
	if frame == 30:
		# time a few ticks directly, outside the engine's own dispatch
		for v in volumes:
			var t0 := Time.get_ticks_usec()
			for i in 5:
				v["body"]._physics_process(1.0 / 60.0)
			v["ms"] = (Time.get_ticks_usec() - t0) / 5000.0
	if frame >= frames:
		for v in volumes:
			results[v["name"]] = _measure_volume(v)
		if tune and not volumes.is_empty():
			tune_queue = volumes.duplicate()
			phase = "tune"
			_next_tune()
		elif not flesh.is_empty():
			_begin_kick()
		else:
			_finish()


func _measure_volume(v: Dictionary) -> Dictionary:
	var body = v["body"]
	var ratio: float = body.mesh_volume() / maxf(v["rest_volume"], 1e-12)
	var speeds: Array = v["speeds"]
	var settle := 0.0
	for s in speeds.slice(maxi(0, speeds.size() - 30)):
		settle = maxf(settle, s)
	var space: PhysicsDirectSpaceState3D = body.get_world_3d().direct_space_state
	var q := PhysicsPointQueryParameters3D.new()
	var inside := 0
	var pos: PackedVector3Array = body.surface_positions()
	var stride := maxi(1, int(pos.size() / 200.0))
	var sampled := 0
	var centre := Vector3.ZERO
	for p in pos:
		centre += p
	centre /= float(maxi(pos.size(), 1))
	for i in range(0, pos.size(), stride):
		# a mounted volume's base sits on its plate: those vertices touch it by design
		if body.near_pinned(i):
			continue
		sampled += 1
		# resting contact is a sample radius deep by design: only deeper than that is inside
		q.position = pos[i] + (centre - pos[i]).normalized() * body._sample_radius * 1.5
		if not space.intersect_point(q, 1).is_empty():
			inside += 1
	var lo := 0.75 if v["plastic"] else 0.85
	var hi := 1.25 if v["plastic"] else 1.15
	var r := {
		"node": v["name"], "route": "shape_matching", "type": v["rep"].get("type", ""), "built": true,
		"nodes": body.report.get("nodes"), "cells": body.report.get("cells"),
		"frequency_hz": body.frequency_hz, "substeps": body.substeps_used,
		"stiffness_limited": body.stiffness_limited,
		"ms_per_tick": snappedf(v["ms"], 0.01),
		"volume_ratio": snappedf(ratio, 0.001), "inside_fraction": snappedf(inside / float(maxi(sampled, 1)), 0.001),
		"settle_mps": snappedf(settle, 0.001), "pin_error_m": snappedf(v["pin_error"], 0.0001),
		"finite": v["finite"],
	}
	r["checks"] = {
		"finite": v["finite"],
		"volume": ratio >= lo and ratio <= hi,
		"not_inside": r["inside_fraction"] <= 0.05,
		"settled": settle <= 0.1,
		"pins": v["pin_error"] <= 0.005,
	}
	r["passed"] = not r["checks"].values().has(false)
	return r


# ------------------------------------------------------------------ frequency tuning

func _next_tune() -> void:
	if tune_state.has("body"):
		tune_state["body"].queue_free()
		tune_state["body"].source.visible = true
	if tune_queue.is_empty():
		if not flesh.is_empty():
			_begin_kick()
		else:
			_finish()
		return
	var v: Dictionary = tune_queue.pop_front()
	var src: MeshInstance3D = v["body"].source
	v["body"].set_physics_process(false)
	var over := set_all.duplicate()
	over["gravity_scale"] = 0.0
	# a body on its own, far from every collider, held at its base
	var test = FollowThrough.ShapeMatchBody.build(src, v["body"].spec, {"overrides": over, "hide_source": false})
	test.set_physics_process(false)
	var lo := INF
	for p in test.x:
		lo = minf(lo, p.y)
	var top := PackedInt32Array()
	var bottom := PackedInt32Array()
	var hi := -INF
	for p in test.x:
		hi = maxf(hi, p.y)
	for i in test.x.size():
		if test.x[i].y < lo + test.spacing * 0.5:
			bottom.append(i)
		elif test.x[i].y > hi - test.spacing * 0.5:
			top.append(i)
	test._pinned.fill(0)
	test._pin_ids.clear()
	test._pin_bone.clear()
	test._pin_offset.clear()
	for i in bottom:
		test._pinned[i] = 1
		test._pin_ids.append(i)
		test._pin_bone.append(-1)
		test._pin_offset.append(src.global_transform.affine_inverse() * test.x[i])
	for i in top:
		test._v[i] = Vector3(0.2, 0, 0)
	tune_state = {"v": v, "body": test, "top": top, "bottom": bottom, "series": PackedFloat32Array(), "tick": 0}


func _tune_tick(delta: float) -> void:
	var st := tune_state
	var test = st["body"]
	# far from everything: step it directly, without collision queries
	test.collide_enabled = false
	test._physics_process(delta)
	var t := Vector3.ZERO
	var b := Vector3.ZERO
	for i in st["top"]:
		t += test.x[i]
	for i in st["bottom"]:
		b += test.x[i]
	st["series"].append((t / float(st["top"].size()) - b / float(st["bottom"].size())).x)
	st["tick"] += 1
	if st["tick"] >= 240:
		var series: PackedFloat32Array = st["series"]
		var mean := 0.0
		for s in series:
			mean += s
		mean /= float(series.size())
		var crossings: Array[int] = []
		for k in range(1, series.size()):
			if (series[k - 1] < mean) != (series[k] < mean):
				crossings.append(k)
		var measured := 0.0
		if crossings.size() >= 3:
			measured = (crossings.size() - 1) / 2.0 / ((crossings[-1] - crossings[0]) * delta)
		var r: Dictionary = results[st["v"]["name"]]
		var target: float = test.frequency_hz
		r["measured_hz"] = snappedf(measured, 0.01)
		if measured > 0.0:
			r["recommended_stiffness_gain"] = snappedf(test.stiffness_gain * pow(target / measured, 2.0), 0.01)
		# 35%: the base-held calibration is a cube's, and a tapered mould held by its whole
		# base rings about 30% high; the recommended gain is what to write back
		r["checks"]["frequency"] = measured > 0.0 and absf(measured - target) <= 0.35 * target
		if st["v"]["plastic"] or float(test.damping_ratio) >= 0.7:
			# a heavily damped or plastic body does not ring: nothing to count
			r["checks"]["frequency"] = true
			r["frequency_note"] = "not measured: damping %.2f%s" % [test.damping_ratio, ", plastic" if st["v"]["plastic"] else ""]
		r["passed"] = not r["checks"].values().has(false)
		_next_tune()


# ------------------------------------------------------------------ flesh kick

func _begin_kick() -> void:
	phase = "kick"
	frame = 0
	for f in flesh:
		f["series"] = {}
		for players in instance.find_children("*", "AnimationPlayer", true, false):
			(players as AnimationPlayer).pause()
	for f in flesh:
		for reg in f["mod"].regions:
			reg["e"] = Vector3.ZERO
			reg["u"] = Vector3.ZERO
		f["mod"].kick(Vector3(0, 1.0, 0))


func _kick_tick(delta: float) -> void:
	frame += 1
	for f in flesh:
		for reg in f["mod"].regions:
			var s: Array = f["series"].get(reg["name"], [])
			s.append((reg["e"] as Vector3).y)
			f["series"][reg["name"]] = s
	if frame >= 240:
		for f in flesh:
			results[f["name"]] = _measure_flesh(f, delta)
		_finish()


func _measure_flesh(f: Dictionary, delta: float) -> Dictionary:
	var mod = f["mod"]
	var rep: Dictionary = mod.report
	var regions := {}
	var all_ok: bool = rep.get("head_error_m", 1.0) <= 0.01 and rep.get("axis_off_y", 1.0) <= 0.02 and f["finite"]
	for reg in mod.regions:
		var s: Array = f["series"].get(reg["name"], [])
		var peak := 0.0
		var peak_at := 0
		for k in s.size():
			if absf(s[k]) > peak:
				peak = absf(s[k])
				peak_at = k
		var crossings: Array[int] = []
		for k in range(1, s.size()):
			if (s[k - 1] < 0.0) != (s[k] < 0.0):
				crossings.append(k)
		var measured := 0.0
		if crossings.size() >= 3:
			measured = (crossings.size() - 1) / 2.0 / ((crossings[-1] - crossings[0]) * delta)
		var w: float = TAU * float(reg["frequency_hz"])
		var z: float = float(reg["damping_ratio"])
		var tau_frames := int(5.0 / maxf(z * w, 0.01) / delta)
		var settled := true
		for k in range(mini(peak_at + tau_frames, s.size()), s.size()):
			if absf(s[k]) > 0.1 * peak:
				settled = false
				break
		var target: float = reg["frequency_hz"]
		var damped: float = target * sqrt(maxf(1.0 - z * z, 0.0))
		# counted only where it rings: at damping 0.6 a kicked region crosses zero once or
		# twice and there is no frequency to read
		var freq_ok := z >= 0.5 or (measured > 0.0 and absf(measured - damped) <= 0.2 * damped)
		var within: bool = f["worst_offset"].get(reg["name"], 0.0) <= float(reg["max_offset"]) + 1e-4
		regions[reg["name"]] = {"frequency_hz": target, "expected_damped_hz": snappedf(damped, 0.01),
			"measured_hz": snappedf(measured, 0.01), "peak_m": snappedf(peak, 0.0001),
			"settled": settled, "worst_offset_while_playing_m": snappedf(f["worst_offset"].get(reg["name"], 0.0), 0.0001),
			"max_offset_m": reg["max_offset"], "frequency_ok": freq_ok, "within_limit": within}
		all_ok = all_ok and freq_ok and settled and within and peak > 0.0
	return {"node": f["name"], "route": "jiggle_bones", "built": true,
		"head_error_m": rep.get("head_error_m"), "axis_off_y": rep.get("axis_off_y"),
		"problems": rep.get("problems", []), "regions": regions, "finite": f["finite"], "passed": all_ok}


func _finish() -> void:
	var ok := not results.is_empty()
	for name in results:
		print("FT_RESULT " + JSON.stringify(results[name]))
		ok = ok and results[name].get("passed", false)
	print("FT_SUMMARY %d volume/flesh bodies, %s" % [results.size(), "PASSED" if ok else "FAILED"])
	quit(0 if ok else 1)
