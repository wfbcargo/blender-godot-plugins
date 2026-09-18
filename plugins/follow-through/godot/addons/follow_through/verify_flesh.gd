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
##   within_body       peak offset <= body_share x peak_m (default 1.0): the bone's tip moves by the
##                     whole offset, so a mass that travels further than it stands out carries its
##                     skin through the surface it sits on. A limit is what lets that happen, so a
##                     suggestion raised past it is the bug this check catches, not a pass
##
## A run that measured nothing fails: no body built, or a `limit_report()` problem - no region
## measured (measure_limits() not called), or a region with 0 ticks. The report keeps those apart
## from what it did measure: `problems` is what was never measured, and only that makes a suggestion
## built on the report untrustworthy; `failures` is a check that measured and did not pass.
##
## Arguments:
##   response=<x>      JiggleModifier.response_scale (default 1; Belle's demo plays at 1.5)
##   set=k:v,...       jiggle overrides for every region (as verify_volume.gd)
##   limits=r:m,...    max_offset_m per region name, for trying a suggestion without re-exporting
##   walk=, idle=      clip names (default: the first clip with "walk" / "idle" in its name)
##   course=full       which course: full (the one above, walk clip for everything), or one of
##                     walk | run | jump - that motion alone, played with the body's own clip for it:
##                       walk  settle, walk, stop, walk through a turn, stop, stand
##                       run   settle, run, stop, run through a turn, stop, stand - on the run clip
##                       jump  settle, three standing jumps, stand - each plays the jump clip from its
##                             start, leaves the ground at the clip's highest hips (the take-off), holds
##                             that pose in the air and plays the rest (the landing) on touching down
##                     so a within_body failure names the motion that caused it
##   run=, jump=       clip names for course=run / jump (default: the first clip with "run" / "jump"
##                     in its name; a body without one fails the run rather than pass on the walk)
##   walk_mps=1.2 run_mps=2.6 jump_mps=3.28 (a 0.55 m jump, belle_controller.gd's JUMP_HEIGHT)
##   max_share=0.10    the on_limit check's line
##   body_share=1.0    the within_body check's line, as a share of peak_m
##   require=a,b       only these checks decide the verdict (default: all five). The others are still
##                     measured, printed and in the report, marked `advisory`. A run that measured
##                     nothing (a problem, an offset gone NaN) fails whatever this says. For the
##                     one-motion courses: on_limit's 10% line is a share of the whole course, drawn
##                     on the mixed one, and a course of nothing but jumps concentrates the ticks on the
##                     limit (study_woman: 10.6% on jumps alone, 0.9% on the full course)
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

## course=walk | run | jump: one motion alone (see Arguments). A jump is 2 s: the clip's take-off, 0.67 s
## of flight at jump_mps, then its landing.
const COURSES := {
	"walk": [
		[1.0, "settle", 0.0, 0.0, false],
		[3.0, "walk", "walk", 0.0, false],
		[1.5, "stop", 0.0, 0.0, false],
		[2.0, "turn", "walk", 90.0, false],
		[1.2, "stop", 0.0, 0.0, false],
		[1.0, "stand", 0.0, 0.0, false],
	],
	"run": [
		[1.0, "settle", 0.0, 0.0, false],
		[3.0, "run", "run", 0.0, false],
		[1.2, "stop", 0.0, 0.0, false],
		[2.5, "turn", "run", 90.0, false],
		[1.2, "stop", 0.0, 0.0, false],
		[1.0, "stand", 0.0, 0.0, false],
	],
	"jump": [
		[1.0, "settle", 0.0, 0.0, false],
		[2.0, "jump", 0.0, 0.0, true],
		[2.0, "jump", 0.0, 0.0, true],
		[2.0, "jump", 0.0, 0.0, true],
		[1.0, "stand", 0.0, 0.0, false],
	],
}

var args := {}
var course: Array = COURSE
var course_name := "full"
var run_clip := ""
var jump_clip := ""
var takeoff_t := -1.0               # the jump clip's time of highest hips, found by sampling it
var sampled := false
var airborne := false
var landed := false
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
var body_share := 1.0
var required: Array = []            # empty: every check decides


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.split("=", true, 1)
		if kv.size() == 2:
			args[kv[0]] = kv[1]
	max_share = float(args.get("max_share", "0.10"))
	body_share = float(args.get("body_share", "1.0"))
	if args.has("require"):
		for k in String(args["require"]).split(","):
			if not k in ["finite", "within_limit", "moved", "on_limit", "within_body"]:
				printerr("verify_flesh: require=%s: no check %s" % [args["require"], k])
				quit(2)
			required.append(k)
	if args.get("scene", "") == "":
		printerr("verify_flesh: pass scene=res://...")
		quit(2)
	course_name = String(args.get("course", "full"))
	if course_name != "full":
		if not COURSES.has(course_name):
			printerr("verify_flesh: course=%s is not one of full, %s" % [course_name, ", ".join(COURSES.keys())])
			quit(2)
		course = COURSES[course_name]


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
			if run_clip == "" and "run" in c.to_lower():
				run_clip = c
			if jump_clip == "" and "jump" in c.to_lower():
				jump_clip = c
		walk_clip = args.get("walk", walk_clip)
		idle_clip = args.get("idle", idle_clip)
		run_clip = args.get("run", run_clip)
		jump_clip = args.get("jump", jump_clip)
		for c in [walk_clip, idle_clip, run_clip]:
			if c != "" and player.has_animation(c):
				player.get_animation(c).loop_mode = Animation.LOOP_LINEAR
		if jump_clip != "" and player.has_animation(jump_clip):
			player.get_animation(jump_clip).loop_mode = Animation.LOOP_NONE
	# a course that names a motion must play that motion's clip: passing a run course on the walk
	# clip would be a run that measured something else
	var need := {"run": run_clip, "jump": jump_clip}
	if need.has(course_name) and (player == null or not player.has_animation(need[course_name])):
		printerr("verify_flesh: course=%s needs a %s clip, and %s has none (clips: %s)" % [
			course_name, course_name, args["scene"], player.get_animation_list() if player else []])
		return false
	return true


## The jump clip's take-off: the time its hips stand highest, sampled over 40 steps before the course
## starts. The skeleton only poses inside the tree, so this runs from _process.
func _sample_takeoff() -> void:
	var skels := instance.find_children("*", "Skeleton3D", true, false)
	var a := player.get_animation(jump_clip)
	var sk: Skeleton3D = skels[0]
	var hips := -1
	for b in sk.get_bone_count():
		if sk.get_bone_parent(b) == -1:
			hips = b
			break
	# the root bone may be a fixed root, so the height read is the highest of its children (on a
	# rig-anything biped, whose root is the hips, the spine and thighs: all rise with them)
	var best := -1e9
	player.play(jump_clip)
	for i in 41:
		var t_i := a.length * i / 40.0
		player.seek(t_i, true)
		var y := 0.0
		for b in sk.get_bone_count():
			y = max(y, sk.get_bone_global_pose(b).origin.y) if sk.get_bone_parent(b) == hips else y
		if y > best + 1e-5:
			best = y
			takeoff_t = t_i
	player.stop()


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
	if course_name == "jump" and not sampled:
		sampled = true
		_sample_takeoff()
		return false
	_advance(delta)
	return false


func _advance(delta: float) -> void:
	if seg < 0 or seg_t >= float(course[seg][0]):
		seg += 1
		seg_t = 0.0
		jumped = false
		airborne = false
		landed = false
		if seg >= course.size():
			_finish()
			return
		if seg == 1:
			for m in mods:
				m["mod"].measure_limits()
	var s: Array = course[seg]
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
	var jump_on_clip: bool = course_name == "jump" and s[4]
	if jump_on_clip:
		# the clip's take-off, then flight holding the take-off pose, then the clip's landing
		if not jumped:
			jumped = true
			player.play(jump_clip, 0.1)
			player.seek(0.0, true)
			player.speed_scale = 1.0
		elif not airborne and not landed and player.current_animation_position >= takeoff_t:
			airborne = true
			player.speed_scale = 0.0
			vy = float(args.get("jump_mps", "3.28"))
	elif course_name == "run" and want > 0.0:
		_play(run_clip, speed / float(args.get("run_mps", "2.6")))
	elif want > 0.0:
		_play(walk_clip, speed / walk_mps)
	elif not (course_name == "jump" and landed):
		_play(idle_clip if idle_clip != "" else walk_clip, 1.0 if idle_clip != "" else 0.0)
	if float(s[3]) != 0.0 and seg_t < 0.5:
		yaw += deg_to_rad(float(s[3])) * delta / 0.5
	if s[4] and not jumped and not jump_on_clip:
		jumped = true
		vy = float(args.get("jump_mps", "3.28"))
	if height > 0.0 or vy > 0.0:
		vy -= GRAVITY * delta
		height += vy * delta
		if height <= 0.0:
			height = 0.0            # a hard landing: stopped in one tick
			vy = 0.0
			if airborne:
				airborne = false
				landed = true
				player.speed_scale = 1.0
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
		r["course"] = "verify_flesh/1" if course_name == "full" else "verify_flesh/1:" + course_name
		r["clips"] = {"walk": walk_clip, "idle": idle_clip, "run": run_clip if course_name == "run" else "",
			"jump": jump_clip if course_name == "jump" else ""}
		r["response_scale"] = m["mod"].response_scale
		r["max_share"] = max_share
		r["body_share"] = body_share
		r["required"] = required
		# `problems` is what was never measured; `failures` is what was measured and is wrong.
		# Only the first makes a suggestion built on this report untrustworthy.
		var problems: PackedStringArray = r["problems"]
		if not m["finite"]:
			problems.append("an offset went NaN or inf")
		var failures := PackedStringArray()
		# a run that measured nothing is not a run that passed
		var body_ok: bool = m["finite"] and problems.is_empty()
		for rname in r["regions"]:
			var g: Dictionary = r["regions"][rname]
			var peak_m := float(g["peak_m"])
			var checks := {
				"finite": m["finite"],
				"within_limit": float(g["peak_offset_m"]) <= float(g["max_offset_m"]) + 1e-4,
				"moved": float(g["peak_offset_m"]) > 0.002,
				"on_limit": float(g["on_limit_share"]) < max_share,
				"within_body": peak_m <= 0.0 or float(g["peak_offset_m"]) <= body_share * peak_m + 1e-4,
			}
			g["checks"] = checks
			var deciding := {}
			for k in checks:
				if required.is_empty() or required.has(k) or k == "finite":
					deciding[k] = checks[k]
			g["passed"] = not deciding.values().has(false)
			var advisory := []
			for k in checks:
				if not checks[k] and not deciding.has(k):
					advisory.append(k)
			g["advisory"] = advisory
			if deciding.has("within_body") and not checks["within_body"]:
				failures.append("%s swung %.3f m, past %.2f x its %.3f m stand-out: its limit (%.3f m) lets its skin into the body" % [
					rname, float(g["peak_offset_m"]), body_share, peak_m, float(g["max_offset_m"])])
			var bad := []
			for k in deciding:
				if not deciding[k] and k != "within_body":
					bad.append(k)
			if not bad.is_empty():
				failures.append("%s: %s" % [rname, ", ".join(bad)])
			for k in advisory:
				print("  NOTE    %s: %s (advisory in this run)" % [rname, k])
			body_ok = body_ok and g["passed"]
		r["problems"] = problems          # a PackedStringArray is a value: put the appends back
		r["failures"] = failures
		r["passed"] = body_ok
		ok = ok and body_ok
		all.append(r)
		print("FT_FLESH_LIMITS " + JSON.stringify(r))
		for p in problems:
			print("  PROBLEM " + p)
		for f in failures:
			print("  FAILED  " + f)
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
	print("FT_SUMMARY %d fleshed bodies, course %s, %s" % [mods.size(), course_name, "PASSED" if ok else "FAILED"])
	quit(0 if ok else 1)
