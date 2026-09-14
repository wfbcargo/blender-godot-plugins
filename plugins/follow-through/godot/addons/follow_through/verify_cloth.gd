extends SceneTree
## Run an imported asset's follow-through cloth in Godot and measure it.
##
##   godot --headless --path <project> -s res://addons/follow_through/verify_cloth.gd -- \
##       scene=res://assets/cloth/banner.glb frames=480 colliders=auto \
##       move=1.5,0,0 move_frames=40 bend=chest,x,40 tune=true
##
## move= carries the whole asset; bend=bone,axis,degrees swings one bone over the
## same window - the test for a cape pinned to a chest that turns.
##
## Headless works for everything measured here because pins are driven with
## soft_body_move_point (attachment-path pins never move headless) and Jolt
## collides headless (GodotPhysics soft bodies fall through obstacles headless -
## run this on a Jolt project).
##
## Measured per cloth, each with a pass limit:
##   pins_found          every spec pin landed on a vertex in the imported mesh
##   pin_error_m         pinned points against their targets, once still        <= 0.005
##   pin_lag_m           the same while the anchor moves: one tick behind is expected
##   stretch_p95 / max   final edge length / rest length                           <= 1.10 / 1.35
##   seam_gap_m          largest separation between vertices that started welded  <= 0.001
##   settle_mps          fastest point over the last 30 ticks                      <= 0.25
##                       or, after move=, at most a quarter of the peak just after the stop
##                       (after 8 s by default). This catches instability - a near-
##                       rigid sheet fluttering at 3-17 m/s - not a slow swing, which
##                       damping decides and which is a matter of taste.
##   finite              no NaN or inf anywhere
##
## tune=true rebuilds a cloth whose stretch fails with simulation_precision
## doubled, up to 64, and reports the lowest precision that passes. Stretch under
## Jolt comes from too few substeps, not from stiffness: at precision 1 a test
## sheet hung to 1.465 m against 0.527 m at 5, with the same stiffness.
##
## Prints one line per cloth starting `FT_RESULT ` followed by JSON.

const FollowThrough = preload("res://addons/follow_through/follow_through.gd")

const LIMITS := {"pin_error_m": 0.005, "stretch_p95": 1.10, "stretch_max": 1.35,
	"seam_gap_m": 0.001, "settle_mps": 0.25}

var args := {}
var scene_path := ""
var frames := 480
var move := Vector3.ZERO
var move_frames := 0
var move_start := 60
var tune := false
var colliders := "auto"
var bend_bone := ""              # bend=chest,x,40 - rotate a bone over the move window
var bend_axis := Vector3.RIGHT
var bend_deg := 0.0
var set_all := {}                # set=key:value,key:value - soft_body overrides for every cloth

var instance: Node3D
var cloths: Array = []           # {body, rest, edges, rest_len, seams, pins, lag, ...}
var frame := 0
var overrides := {}              # node name -> {simulation_precision: n}
var results := {}                # node name -> final result
var pending_tune := {}           # node name -> next precision to try
var started := false
var skipped_skinned: Array[String] = []


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.split("=", true, 1)
		if kv.size() == 2:
			args[kv[0]] = kv[1]
	scene_path = args.get("scene", "")
	frames = int(args.get("frames", "480"))
	move_frames = int(args.get("move_frames", "0"))
	move_start = int(args.get("move_start", "60"))
	tune = args.get("tune", "false") == "true"
	colliders = args.get("colliders", "auto")
	if args.has("set"):
		for pair in args["set"].split(","):
			var kv2: PackedStringArray = pair.split(":")
			set_all[kv2[0]] = float(kv2[1])
	if args.has("bend"):
		var b: PackedStringArray = args["bend"].split(",")
		bend_bone = b[0]
		bend_axis = {"x": Vector3.RIGHT, "y": Vector3.UP, "z": Vector3.BACK}[b[1]]
		bend_deg = float(b[2])
		if move_frames == 0:
			move_frames = 40
	if args.has("move"):
		var p: PackedStringArray = args["move"].split(",")
		move = Vector3(float(p[0]), float(p[1]), float(p[2]))
		if move_frames == 0:
			move_frames = 40
	if scene_path == "":
		printerr("verify_cloth: pass scene=res://...")
		quit(2)
		return
	# Not _start_run() here: during _initialize the root is not inside the tree yet,
	# so every global_transform reads identity and every pin anchors to the origin.
	started = false


func _start_run() -> void:
	if instance != null:
		instance.queue_free()
	var packed: PackedScene = load(scene_path)
	if packed == null:
		printerr("verify_cloth: cannot load " + scene_path)
		quit(2)
		return
	instance = packed.instantiate()
	root.add_child(instance)
	if colliders == "auto":
		skipped_skinned.clear()
		_add_colliders(instance)
	frame = 0
	cloths.clear()
	var reports := FollowThrough.apply(instance, {"overrides": set_all})
	for rep in reports:
		var name := String(rep["node"])
		if not rep.get("built", false):
			results[name] = {"node": name, "built": false, "problems": rep.get("problems", []), "passed": false}
			continue
		if results.has(name) and not pending_tune.has(name):
			# already final from an earlier run: take it out of this run's physics
			rep["body"].queue_free()
			rep["body"].source.visible = true
			continue
		var body = rep["body"]
		if pending_tune.has(name):
			body.queue_free()
			body.source.visible = true
			body = FollowThrough.ClothBody.build(body.source, body.spec,
				{"overrides": _merged({"simulation_precision": pending_tune[name]})})
			rep.merge(body.report, true)
		cloths.append(_rest_data(name, body, rep))


func _merged(extra: Dictionary) -> Dictionary:
	var d := set_all.duplicate()
	d.merge(extra, true)
	return d


## Trimesh colliders for every unskinned mesh that is not cloth, so a tablecloth has
## a table to land on. Skinned meshes are skipped and listed: a trimesh of a skinned
## body is frozen in one pose, and with bend=chest,x,40 the test cape's pins followed
## the chest into the rest-pose body it no longer matched - worst edge 7.8x its length.
## A body a cape should drape over needs capsules on its bones, added in the scene.
func _add_colliders(node: Node) -> void:
	for n in _all(node):
		if not n is MeshInstance3D or not FollowThrough.spec_of(n).is_empty() or n.mesh == null:
			continue
		var mi: MeshInstance3D = n
		if mi.skin != null:
			skipped_skinned.append(String(mi.name))
			continue
		var faces := mi.mesh.get_faces()
		if faces.is_empty():
			continue
		# Animatable, not Static: move= carries the whole asset, and a StaticBody3D that is
		# moved teleports - the test tablecloth fell straight through its travelling table.
		var body := AnimatableBody3D.new()
		var shape := CollisionShape3D.new()
		var tri := ConcavePolygonShape3D.new()
		tri.set_faces(faces)
		shape.shape = tri
		body.add_child(shape)
		mi.add_child(body)


func _all(node: Node) -> Array[Node]:
	var out: Array[Node] = [node]
	for c in node.get_children():
		out.append_array(_all(c))
	return out


func _rest_data(name: String, body, rep: Dictionary) -> Dictionary:
	var arrays: Array = body.mesh.surface_get_arrays(0)
	var rest: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var idx: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var seen := {}
	var edges := []
	for t in range(0, idx.size(), 3):
		for e in [[idx[t], idx[t + 1]], [idx[t + 1], idx[t + 2]], [idx[t + 2], idx[t]]]:
			var a: int = mini(e[0], e[1])
			var b: int = maxi(e[0], e[1])
			var key := a * 1000003 + b
			if not seen.has(key):
				seen[key] = true
				edges.append([a, b, rest[a].distance_to(rest[b])])
	var by_pos := {}
	for i in rest.size():
		var k := Vector3i((rest[i] * 100000.0).round())
		if not by_pos.has(k):
			by_pos[k] = []
		by_pos[k].append(i)
	var seams := []
	for k in by_pos:
		if by_pos[k].size() > 1:
			seams.append(by_pos[k])
	var lowest := INF
	for p in rest:
		lowest = minf(lowest, p.y)
	return {"name": name, "body": body, "rep": rep, "rest": rest, "edges": edges, "seams": seams,
		"rest_lowest": lowest, "pin_error": 0.0, "pin_lag": 0.0, "seam_gap": 0.0,
		"speeds": [], "prev": PackedVector3Array(), "finite": true,
		"precision": body.simulation_precision}


func _physics_process(delta: float) -> bool:
	if not started:
		started = true
		_start_run()
		return false
	if cloths.is_empty() and frame == 0:
		_finish_run()
		return false
	frame += 1
	var moving := move_frames > 0 and frame >= move_start and frame < move_start + move_frames
	if moving:
		instance.position += move / float(move_frames)
		if bend_bone != "":
			for sk in _all(instance):
				if sk is Skeleton3D and sk.find_bone(bend_bone) >= 0:
					var bi: int = sk.find_bone(bend_bone)
					var t := float(frame - move_start + 1) / float(move_frames)
					sk.set_bone_pose_rotation(bi, sk.get_bone_rest(bi).basis.get_rotation_quaternion()
						* Quaternion(bend_axis, deg_to_rad(bend_deg) * t))
	for c in cloths:
		_sample(c, delta, moving)
	if frame >= frames:
		_finish_run()
	return false


func _sample(c: Dictionary, delta: float, moving: bool) -> void:
	var body = c["body"]
	var rid: RID = body.get_physics_rid()
	var n: int = c["rest"].size()
	var now := PackedVector3Array()
	now.resize(n)
	for i in n:
		var p := PhysicsServer3D.soft_body_get_point_global_position(rid, i)
		if not p.is_finite():
			c["finite"] = false
		now[i] = p
	if frame > 2:
		var pins: PackedInt32Array = body.pinned_indices()
		var err := 0.0
		for k in pins.size():
			err = maxf(err, now[pins[k]].distance_to(body.pin_target(k)))
		var after_move := move_frames > 0 and frame >= move_start and frame < move_start + move_frames + 5
		if moving or after_move:
			c["pin_lag"] = maxf(c["pin_lag"], err)
		elif frame > frames - 30:
			c["pin_error"] = maxf(c["pin_error"], err)
	if c["prev"].size() == n:
		var fastest := 0.0
		var who := -1
		for i in n:
			var sp := now[i].distance_to(c["prev"][i]) / delta
			if sp > fastest:
				fastest = sp
				who = i
		c["speeds"].append(fastest)
		var stop := move_start + move_frames
		if move_frames > 0 and frame >= stop and frame < stop + 30:
			c["peak_after_stop"] = maxf(c.get("peak_after_stop", 0.0), fastest)
		c["fastest_vertex"] = who
	c["prev"] = now
	for group in c["seams"]:
		for j in range(1, group.size()):
			c["seam_gap"] = maxf(c["seam_gap"], now[group[0]].distance_to(now[group[j]]))


func _finish_run() -> void:
	var retry := false
	var next_tune := {}
	for c in cloths:
		var r := _measure(c)
		var name: String = c["name"]
		if tune and not r["checks"]["stretch"] and r["simulation_precision"] < 64:
			next_tune[name] = mini(r["simulation_precision"] * 2, 64)
			r["tuning"] = "stretch failed at precision %d, retrying at %d" % [r["simulation_precision"], next_tune[name]]
			retry = true
		var history: Array = results.get(name, {}).get("tried", [])
		history.append({"simulation_precision": r["simulation_precision"],
			"stretch_p95": r["stretch_p95"], "stretch_max": r["stretch_max"]})
		r["tried"] = history
		results[name] = r
	pending_tune = next_tune
	if retry:
		_start_run()
		return
	for name in results:
		var r: Dictionary = results[name]
		if r.get("tried", []).size() > 1:
			r["recommended_simulation_precision"] = r["simulation_precision"]
		print("FT_RESULT " + JSON.stringify(r))
	var all_ok := true
	for name in results:
		all_ok = all_ok and results[name].get("passed", false)
	if not skipped_skinned.is_empty():
		print("FT_NOTE colliders=auto skipped skinned meshes (add bone capsules for these): " + ", ".join(skipped_skinned))
	print("FT_SUMMARY %d cloth, %s" % [results.size(), "PASSED" if all_ok else "FAILED"])
	quit(0 if all_ok else 1)


func _measure(c: Dictionary) -> Dictionary:
	var body = c["body"]
	var now: PackedVector3Array = c["prev"]
	var ratios := PackedFloat32Array()
	for e in c["edges"]:
		if e[2] > 0.000001:
			ratios.append(now[e[0]].distance_to(now[e[1]]) / e[2])
	ratios.sort()
	var lowest := INF
	for p in now:
		lowest = minf(lowest, p.y)
	var speeds: Array = c["speeds"]
	var settle := 0.0
	for s in speeds.slice(maxi(0, speeds.size() - 30)):
		settle = maxf(settle, s)
	var rep: Dictionary = c["rep"]
	var r := {
		"node": c["name"], "class": rep.get("class"), "built": true,
		"vertices": c["rest"].size(), "surfaces": rep.get("surfaces"),
		"pins_total": rep.get("pins_total"), "pins_found": rep.get("pins_found"),
		"pinned_vertices": rep.get("pinned_vertices"),
		"simulation_precision": body.simulation_precision,
		"linear_stiffness": body.linear_stiffness, "total_mass": body.total_mass,
		"frames": frame,
		"pin_error_m": snappedf(c["pin_error"], 0.00001),
		"pin_lag_m": snappedf(c["pin_lag"], 0.00001),
		"stretch_p95": snappedf(ratios[int(ratios.size() * 0.95)], 0.0001) if ratios.size() else 1.0,
		"stretch_max": snappedf(ratios[ratios.size() - 1], 0.0001) if ratios.size() else 1.0,
		"seam_gap_m": snappedf(c["seam_gap"], 0.00001),
		"seam_groups": c["seams"].size(),
		"drop_m": snappedf(c["rest_lowest"] - lowest, 0.0001),
		"settle_mps": snappedf(settle, 0.0001),
		"finite": c["finite"],
	}
	var fv: int = c.get("fastest_vertex", -1)
	if fv >= 0:
		r["fastest_vertex"] = {"index": fv, "pinned": body.pinned_indices().has(fv),
			"rest": [snappedf(c["rest"][fv].x, 0.001), snappedf(c["rest"][fv].y, 0.001), snappedf(c["rest"][fv].z, 0.001)]}
	if rep.has("missing_bones"):
		r["missing_bones"] = rep["missing_bones"]
	var quiet_end := move_frames == 0 or move_start + move_frames < frame - 60
	var peak: float = c.get("peak_after_stop", 0.0)
	if move_frames > 0:
		r["peak_after_stop_mps"] = snappedf(peak, 0.0001)
	var checks := {
		"pins": rep.get("pins_found") == rep.get("pins_total") and not rep.has("missing_bones"),
		"pin_error": r["pin_error_m"] <= LIMITS["pin_error_m"],
		"stretch": r["stretch_p95"] <= LIMITS["stretch_p95"] and r["stretch_max"] <= LIMITS["stretch_max"],
		"seams": r["seam_gap_m"] <= LIMITS["seam_gap_m"],
		# still: below the limit. After a move: below the limit, or at most a quarter of
		# the swing it had just after stopping - a swing dying away, not a flutter feeding itself
		"settled": not quiet_end or r["settle_mps"] <= LIMITS["settle_mps"] 			or (move_frames > 0 and r["settle_mps"] <= 0.25 * peak),
		"finite": r["finite"],
		"one_surface": rep.get("surfaces", 1) == 1,
	}
	r["checks"] = checks
	var ok := true
	for k in checks:
		ok = ok and checks[k]
	r["passed"] = ok
	return r
