extends SceneTree
## Load `.moves.json` manifests into a plain MovesController and check its gait choice and playback:
## speeds 0 -> walk -> run -> walk, each role and rate against the manifest, hysteresis either side of
## every change, and the stride phase carried across a change.
##
##   godot --headless --path <project> -s res://addons/rig_anything/verify_moves.gd -- \
##       manifests=res://a.moves.json,res://b.moves.json   (or dir=res://assets/humans, searched recursively)
##
## Prints one MOVES line per check and MOVES VERIFY PASSED / FAILED; exits 1 on failure.

const TICK := 1.0 / 60.0

var _fails := []


func _initialize() -> void:
	var paths := []
	for a in OS.get_cmdline_user_args():
		if a.begins_with("manifests="):
			paths.append_array(a.substr(10).split(",", false))
		elif a.begins_with("dir="):
			_find(a.substr(4), paths)
	if paths.is_empty():
		print("MOVES VERIFY: give manifests=<a,b> or dir=<res://...>")
		quit(2)
		return
	_run.call_deferred(paths)


func _find(dir: String, out: Array) -> void:
	for f in DirAccess.get_files_at(dir):
		if f.ends_with(".moves.json"):
			out.append(dir.path_join(f))
	for d in DirAccess.get_directories_at(dir):
		_find(dir.path_join(d), out)


func _check(ok: bool, what: String) -> void:
	print("MOVES  %s  %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		_fails.append(what)


func _run(paths: Array) -> void:
	for p in paths:
		_verify(p)
	print("MOVES VERIFY %s" % ("PASSED" if _fails.is_empty() else "FAILED: %d checks" % _fails.size()))
	quit(0 if _fails.is_empty() else 1)


func _verify(path: String) -> void:
	var body := MovesController.new()
	body.manifest_path = path
	root.add_child(body)
	body.set_physics_process(false)      # driven by hand below, not by input
	var anim: AnimationPlayer = body._anim
	anim.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var who := "%s:" % body.display_name
	var ladder: Array = body._ladder
	print("MOVES %s ladder %s  collider r %.3f h %.2f" % [who, ladder.map(func(g): return "%s %.2f" % [g["role"], g["speed"]]),
			body.collider_radius, body.height])
	if ladder.is_empty():
		_check(false, "%s no gait in the manifest" % who)
		body.free()
		return

	var drive := func(speed: float, seconds: float) -> String:
		var role := ""
		for i in int(round(seconds / TICK)):
			role = body.play_gait_for(speed)
			anim.advance(TICK)
		return role
	var expect := func(role: String, speed: float, label: String) -> void:
		var got: String = body.current_role()
		var rate := anim.speed_scale
		var want_rate: float = 1.0 if role == "Idle" else speed / body.implied_speed(role)
		_check(got == role and absf(rate - want_rate) < 1e-4,
				"%s %s at %.2f m/s plays %s x%.3f (want %s x%.3f)" % [who, label, speed, got, rate, role, want_rate])

	var walk: Dictionary = ladder[0]
	var top: Dictionary = ladder[-1]
	drive.call(0.0, 0.5)
	expect.call("Idle", 0.0, "standing")
	drive.call(walk["speed"], 0.7)
	expect.call(walk["role"], walk["speed"], "walking")
	# Walk is never the only ladder rung for a runner, so each change-up line is checked on the way
	for i in ladder.size() - 1:
		var line := sqrt(ladder[i]["speed"] * ladder[i + 1]["speed"])
		var hold := line * (1.0 + body.gait_hysteresis * 0.5)
		drive.call(hold, 0.2)
		expect.call(ladder[i]["role"], hold, "just over the %s/%s line" % [ladder[i]["role"], ladder[i + 1]["role"]])
		var phase := fmod(anim.current_animation_position / anim.current_animation_length, 1.0)
		var over := line * (1.0 + body.gait_hysteresis * 1.5)
		drive.call(over, TICK)
		expect.call(ladder[i + 1]["role"], over, "past the change-up")
		# one tick of the new clip has played at the new rate since the seek
		var after := fmod((anim.current_animation_position - TICK * anim.speed_scale) / anim.current_animation_length + 1.0, 1.0)
		_check(absf(after - phase) < 0.02 or absf(absf(after - phase) - 1.0) < 0.02,
				"%s %s -> %s keeps the stride phase (%.3f -> %.3f)" % [who, ladder[i]["role"], ladder[i + 1]["role"], phase, after])
	if ladder.size() > 1:
		drive.call(top["speed"], 0.7)
		expect.call(top["role"], top["speed"], "running")
		for i in range(ladder.size() - 1, 0, -1):
			var line := sqrt(ladder[i]["speed"] * ladder[i - 1]["speed"])
			var hold := line / (1.0 + body.gait_hysteresis * 0.5)
			drive.call(hold, 0.2)
			expect.call(ladder[i]["role"], hold, "just under the %s/%s line" % [ladder[i - 1]["role"], ladder[i]["role"]])
	else:
		drive.call(walk["speed"] * 3.0, 0.3)
		expect.call(walk["role"], walk["speed"] * 3.0, "pushed to 3x walk (no faster gait)")
	drive.call(walk["speed"], 0.7)
	expect.call(walk["role"], walk["speed"], "back to walking")
	drive.call(0.0, 0.5)
	expect.call("Idle", 0.0, "stopped")
	body.free()
