extends SceneTree
## Drive a fleshed body round a fixed course and measure each region's time on its swing limit.
##
##   godot --headless --fixed-fps 60 --path <project> -s res://addons/follow_through/verify_flesh.gd -- \
##       scene=res://assets/figure.glb [response=1.5] [limits=breast.L:0.08,butt.R:0.06] [out=C:/x/limits.json]
##
## The course is the same every run, so two runs can be compared: settle, walk, stop, walk
## through a turn, run, stop, two standing jumps landing hard, stand. The body walks in place on
## its walk clip while the scene root carries it, speeding up and slowing down at ACCEL m/s^2;
## takeoff and landing are one tick, as a CharacterBody3D's are. Belle's self-test (belle_demo.gd) mixes the same kinds of
## motion with rolls and a crouch.
##
## Prints one `FT_FLESH_LIMITS {json}` line per body (JiggleModifier.limit_report: per region the
## share of ticks on the limit, peak offset, the unlimited swing's demand curve) that
## `follow_through.flesh.suggest_limits` reads, then `FT_SUMMARY ... PASSED|FAILED`.
##
## Checks, per region:
##   finite            no NaN or inf offset
##   within_limit      peak offset <= max_offset_m (+0.1 mm)
##   moved             peak offset > 2 mm: the load reached the bone
##   on_limit          on_limit_share < max_share (default 0.10, belle_demo's line): pinned on
##                     its limit the clamp stops the swing dead - allowed for moments, not as the look
##
## Arguments:
##   response=<x>      JiggleModifier.response_scale (default 1; Belle's demo plays at 1.5)
##   set=k:v,...       jiggle overrides for every region (as verify_volume.gd)
##   limits=r:m,...    max_offset_m per region name, for trying a suggestion without re-exporting
##   walk=, idle=      clip names (default: the first clip with "walk" / "idle" in its name)
##   walk_mps=1.2 run_mps=2.6 jump_mps=3.28 (a 0.55 m jump, belle_controller.gd's JUMP_HEIGHT)
##   max_share=0.10    the on_limit check's line
##   out=<path>        also write the reports, as a JSON list, to that file

const FollowThrough = preload("res://addons/follow_through/follow_through.gd")

const ACCEL := 7.0                  # m/s^2, belle_controller.gd's ACCEL
const GRAVITY := 9.8
## [seconds, label, speed m/s (or "walk"/"run"), turn deg over the segment's first 0.5 s, jump]
const COURSE := [
	[1.0, "settle", 0.0, 0.0, false],
	[3.0, "walk", "walk", 0.0, false],
	[1.5, "stop", 0.0, 0.0, false],
	[2.0, "turn", "walk", 90.0, false],
	[2.5, "run", "run", 0.0, false],
	[1.2, "stop", 0.0, 0.0, false],
	[1.2, "jump", 0.0, 0.0, true],
	[1.2, "jump", 0.0, 0.0, true],
	[1.0, "stand", 0.0, 0.0, false],
]

var args := {}
var instance: Node3D
var player: AnimationPlayer
var walk_clip := ""
var idle_clip := ""
var mods: Array = []                # {name, mod, finite}
var started := false
var t := 0.0
var seg := -1
var seg_t := 0.0
var speed := 0.0
var yaw := 0.0
var height := 0.0
var vy := 0.0
var jumped := false
var max_share := 0.10


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.split("=", true, 1)
		if kv.size() == 2:
			args[kv[0]] = kv[1]
	max_share = float(args.get("max_share", "0.10"))
	if args.get("scene", "") == "":
		printerr("verify_flesh: pass scene=res://...")
		quit(2)


func _start() -> bool:
	var packed: PackedScene = load(args["scene"])
	if packed == null:
		printerr("verify_flesh: cannot load " + args["scene"])
		return false
	instance = packed.instantiate()
	root.add_child(instance)
	var over := {}
	if args.has("set"):
		for pair in String(args["set"]).split(","):
			var kv: PackedStringArray = pair.split(":")
			over[kv[0]] = float(kv[1])
	var limits := {}
	if args.has("limits"):
		for pair in String(args["limits"]).split(","):
			var i := pair.rfind(":")
			limits[pair.substr(0, i)] = float(pair.substr(i + 1))
	for rep in FollowThrough.apply(instance, {"overrides": over, "routes": ["jiggle_bones"]}):
		if not rep.get("built", false):
			printerr("verify_flesh: %s not built: %s" % [rep["node"], rep.get("problems", [])])
			continue
		var mod = rep["body"]
		mod.response_scale = float(args.get("response", "1.0"))
		for reg in mod.regions:
			if limits.has(reg["name"]):
				reg["max_offset"] = float(limits[reg["name"]])
		mods.append({"name": String(rep["node"]), "mod": mod, "finite": true})
	if mods.is_empty():
		printerr("verify_flesh: no jiggle_bones spec in " + args["scene"])
		return false
	var players := instance.find_children("*", "AnimationPlayer", true, false)
	if not players.is_empty():
		player = players[0]
		for c in player.get_animation_list():
			if walk_clip == "" and "walk" in c.to_lower():
				walk_clip = c
			if idle_clip == "" and "idle" in c.to_lower():
				idle_clip = c
		walk_clip = args.get("walk", walk_clip)
		idle_clip = args.get("idle", idle_clip)
		for c in [walk_clip, idle_clip]:
			if c != "" and player.has_animation(c):
				player.get_animation(c).loop_mode = Animation.LOOP_LINEAR
	return true


func _play(clip: String, rate: float) -> void:
	if player == null or clip == "" or not player.has_animation(clip):
		return
	if player.current_animation != clip:
		player.play(clip, 0.2)
	player.speed_scale = rate


func _process(delta: float) -> bool:
	if not started:
		started = true
		if not _start():
			quit(2)
		return false
	_advance(delta)
	return false


func _advance(delta: float) -> void:
	if seg < 0 or seg_t >= float(COURSE[seg][0]):
		seg += 1
		seg_t = 0.0
		jumped = false
		if seg >= COURSE.size():
			_finish()
			return
		if seg == 1:
			for m in mods:
				m["mod"].measure_limits()
	var s: Array = COURSE[seg]
	var label: String = s[1]
	for m in mods:
		m["mod"].measure_label = label
	var walk_mps := float(args.get("walk_mps", "1.2"))
	var run_mps := float(args.get("run_mps", "2.6"))
	var want := 0.0
	if s[2] is String:
		want = walk_mps if s[2] == "walk" else run_mps
	else:
		want = float(s[2])
	speed = move_toward(speed, want, ACCEL * delta)
	if want > 0.0:
		_play(walk_clip, speed / walk_mps)
	else:
		_play(idle_clip if idle_clip != "" else walk_clip, 1.0 if idle_clip != "" else 0.0)
	if float(s[3]) != 0.0 and seg_t < 0.5:
		yaw += deg_to_rad(float(s[3])) * delta / 0.5
	if s[4] and not jumped:
		jumped = true
		vy = float(args.get("jump_mps", "3.28"))
	if height > 0.0 or vy > 0.0:
		vy -= GRAVITY * delta
		height += vy * delta
		if height <= 0.0:
			height = 0.0            # a hard landing: stopped in one tick
			vy = 0.0
	instance.rotation.y = yaw
	instance.position += Basis(Vector3.UP, yaw) * Vector3(0, 0, -speed * delta)
	instance.position.y = height
	seg_t += delta
	t += delta
	for m in mods:
		for reg in m["mod"].regions:
			if not (reg["offset"] as Vector3).is_finite():
				m["finite"] = false


func _finish() -> void:
	var ok := true
	var all := []
	for m in mods:
		var r: Dictionary = m["mod"].limit_report()
		r["body"] = m["name"]
		r["course"] = "verify_flesh/1"
		r["response_scale"] = m["mod"].response_scale
		r["max_share"] = max_share
		var body_ok: bool = m["finite"]
		for rname in r["regions"]:
			var g: Dictionary = r["regions"][rname]
			var checks := {
				"finite": m["finite"],
				"within_limit": float(g["peak_offset_m"]) <= float(g["max_offset_m"]) + 1e-4,
				"moved": float(g["peak_offset_m"]) > 0.002,
				"on_limit": float(g["on_limit_share"]) < max_share,
			}
			g["checks"] = checks
			g["passed"] = not checks.values().has(false)
			body_ok = body_ok and g["passed"]
		r["passed"] = body_ok
		ok = ok and body_ok
		all.append(r)
		print("FT_FLESH_LIMITS " + JSON.stringify(r))
		for rname in r["regions"]:
			var g: Dictionary = r["regions"][rname]
			print("  %-16s %s  limit %.3f  peak %.3f  free peak %.3f  on the limit %4.1f%% in %d contacts (longest %d ticks)  %s" % [
				rname, "OK " if g["passed"] else "BAD", g["max_offset_m"], g["peak_offset_m"], g["free_peak_m"],
				100.0 * float(g["on_limit_share"]), g["contacts"], g["longest_contact_ticks"], g["on_limit_by_label"]])
	if args.has("out"):
		var f := FileAccess.open(args["out"], FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify(all, " "))
			f.close()
	print("FT_SUMMARY %d fleshed bodies, %s" % [mods.size(), "PASSED" if ok else "FAILED"])
	quit(0 if ok else 1)
