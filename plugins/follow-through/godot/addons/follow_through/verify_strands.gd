extends SceneTree
## Put a body's strands on it in Godot, run them at several frame rates, and measure them.
##
##   godot --headless --path <project> -s res://addons/follow_through/verify_strands.gd -- \
##       scene=res://assets/figure.glb strands=res://assets/figure_ponytail.glb clip=Figure_Run
##
## `strands` is the glb strand.export wrote (omit it when the strands are in `scene`). `clip` is the
## run (default: the first clip with "Run" in its name, else the longest). `rates` the frame rates
## (default 30,60,120,240). Time is stepped by hand - the AnimationPlayer and the Skeleton3D's
## modifiers are both advanced manually - so each rate is exactly that rate, however fast the
## machine is. For each rate the body is loaded afresh and goes through:
##
##   rest     the rest pose, nothing moving, 1 s          rest_drift_deg      <= 0.5
##   kick     knocked sideways at 1.5 m/s, 4 s            settled: the last 0.5 s under 10% of the
##                                                        peak and under 2 deg; peak_deg reported
##   fling    knocked back at 3 m/s so the strands are    head_penetration_m <= 0.005
##            thrown forward at the head, 2 s
##   run      the clip, looped, 4 s                       swing_deg >= 3 (tip deflection in the
##                                                        root bone's frame, after the first 0.5 s)
##                                                        head_penetration_m <= 0.005
##   hitch    one 0.75 s frame mid-run, then 0.5 s        the frame simulates at most
##            at the rate again                           StrandModifier.MAX_STEPS steps and drops the
##                                                        rest; head_penetration_m <= 0.005
##   always   finite bone poses, no non-finite spring state
##
## Head penetration is measured against the body's skin, not the colliders: every strand vertex is
## skinned on the CPU and compared with the head's own surface (the body's vertices skinned mostly to
## the collider bone named `head`, as a radius per direction round their centroid, in that bone's
## frame, read between cells). A strand vertex counts by how much deeper it is than it was at rest,
## so a root grown into the scalp is not a penetration.
##
## Across rates: the run's swing_deg within 25% of each other (max / min <= 1.25).
##
## legacy_integration=true steps the strands as before follow-through 0.6.3 (StrandModifier's
## legacy_integration): the run swings differently at each rate. It is regress's control and must fail
## the spread, on pipeline_ponytail (1.39) as on study_woman (1.26).
## set=key:value,... overrides spring values on every bone (damping_ratio, frequency_hz, max_angle_deg,
## gravity_scale, response, collision_margin_m) for tuning without re-exporting.
## dump=<file.json> writes, for the first rate, every chain's joints (skeleton space, glTF axes) each
## frame of the fling and the run, with the clip time - for rendering what the numbers describe.
## Prints one `FT_STRAND {json}` line per rate, then `FT_SUMMARY ... PASSED|FAILED`.

const FollowThrough = preload("res://addons/follow_through/follow_through.gd")
const StrandModifier = preload("res://addons/follow_through/strand_modifier.gd")

const LAT := 24
const LON := 48
const HITCH_S := 0.75               # the stalled frame the hitch phase feeds the modifier

var args := {}
var results: Array = []
var failures := PackedStringArray()


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.split("=", true, 1)
		if kv.size() == 2:
			args[kv[0]] = kv[1]
	if args.get("scene", "") == "":
		printerr("verify_strands: pass scene=res://...")
		quit(2)
		return
	_main.call_deferred()


func _main() -> void:
	var rates: Array = []
	for r in String(args.get("rates", "30,60,120,240")).split(","):
		rates.append(int(r))
	var swings := []
	for rate in rates:
		var res = await _run_rate(rate)
		if typeof(res) != TYPE_DICTIONARY or not res.has("swing_deg"):
			# a script error or an early return: nothing was measured, which is never a pass
			failures.append("%d fps: the run was not measured (%s)" % [rate, str(res.get("failures", "script error") if typeof(res) == TYPE_DICTIONARY else "script error")])
			res = res if typeof(res) == TYPE_DICTIONARY else {}
		results.append(res)
		print("FT_STRAND " + JSON.stringify(res))
		if res.has("swing_deg"):
			swings.append(float(res["swing_deg"]))
		for f in res.get("failures", []):
			failures.append("%d fps: %s" % [rate, f])
	var spread := 0.0
	if swings.size() > 1:
		spread = swings.max() / maxf(swings.min(), 1e-6)
		if spread > 1.25:
			failures.append("the run's swing differs across frame rates: %s deg (max/min %.2f > 1.25)" % [str(swings), spread])
	var passed := failures.is_empty() and not results.is_empty()
	print("FT_SUMMARY %s rates=%s swing_spread=%.3f %s" % [args["scene"], str(rates), spread, "PASSED" if passed else "FAILED"])
	for f in failures:
		print("  FAIL " + f)
	quit(0 if passed else 1)


func _run_rate(rate: int) -> Dictionary:
	var out := {"fps": rate, "failures": PackedStringArray()}
	var dt := 1.0 / float(rate)
	var packed: PackedScene = load(args["scene"])
	if packed == null:
		out["failures"].append("cannot load " + args["scene"])
		return out
	var body: Node3D = packed.instantiate()
	root.add_child(body)
	if args.has("strands"):
		var sp: PackedScene = load(args["strands"])
		if sp == null:
			out["failures"].append("cannot load " + args["strands"])
			body.queue_free()
			return out
		var att := FollowThrough.attach(body, sp)
		for a in att:
			for p in a.get("problems", []):
				out["failures"].append("attach: " + p)
	var overrides := {}
	if args.has("set"):
		for pair in String(args["set"]).split(","):
			var kv: PackedStringArray = pair.split(":")
			overrides[kv[0]] = float(kv[1])
	var reps := FollowThrough.apply(body, {"routes": ["spring_bones"], "overrides": overrides})
	var mods: Array = []
	var meshes: Array = []
	for rep in reps:
		for p in rep.get("problems", []):
			out["failures"].append(String(rep["node"]) + ": " + p)
		if rep.get("body") != null:
			mods.append(rep["body"])
			meshes.append(_mesh_named(body, String(rep["node"])))
	if mods.is_empty():
		out["failures"].append("no strands built")
		body.queue_free()
		return out
	var mod = mods[0]
	for m in mods:
		m.legacy_integration = args.get("legacy_integration", "false") == "true"
	var skel: Skeleton3D = mod.get_skeleton()
	out["build"] = mod.report.duplicate()
	out["build"].erase("problems")
	skel.modifier_callback_mode_process = Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL
	var player := body.find_children("*", "AnimationPlayer", true, false)
	var ap: AnimationPlayer = player[0] if not player.is_empty() else null
	if ap != null:
		ap.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		ap.stop()
	skel.reset_bone_poses()

	var head := _head_table(skel, mod, meshes)
	if head.is_empty():
		out["failures"].append("no head collider or no head skin to measure penetration against")
	var hair := []
	for gm in meshes:
		hair.append(_skin_data(gm, skel))
	var state := {"skel": skel, "mods": mods, "head": head, "hair": hair, "rest_depth": [], "pen": 0.0,
		"pen_at": [], "tip": 0.0, "ap": ap, "phase": "", "frames": []}
	var dumping: bool = args.has("dump") and results.is_empty()
	if not head.is_empty():
		for h in hair:
			state["rest_depth"].append(_depths(h, skel, head, true))
	var measured := {"n": 0}
	var on_processed := func():
		_measure(state, measured)
	mods[-1].modification_processed.connect(on_processed)

	# rest
	await _steps(ap, skel, dt, 1.0, state)
	out["rest_drift_deg"] = snappedf(_max_angle(mods), 0.001)
	if out["rest_drift_deg"] > 0.5:
		out["failures"].append("drifts at rest: %.3f deg" % out["rest_drift_deg"])

	# kick sideways, settle
	for m in mods:
		m.kick(Vector3(1.5, 0, 0))
		m.reset_stats()
	var series: Array = await _steps(ap, skel, dt, 4.0, state)
	var peak: float = series.max()
	var tail_n := int(0.5 / dt)
	var last: float = series.slice(series.size() - tail_n).max()
	out["kick_peak_deg"] = snappedf(peak, 0.01)
	out["kick_last_deg"] = snappedf(last, 0.01)
	out["kick_settle_s"] = snappedf(_settle_time(series, peak * 0.1, dt), 0.01)
	if peak < 1.0:
		out["failures"].append("a 1.5 m/s kick moved the strands %.2f deg" % peak)
	if last > maxf(0.1 * peak, 0.1) or last > 2.0:
		out["failures"].append("not settled 4 s after a kick: %.2f deg of a %.2f deg peak" % [last, peak])

	# fling at the head
	state["pen"] = 0.0
	var toward := _toward_head(skel, mod)
	for m in mods:
		m.kick(-toward * 3.0)
		m.reset_stats()
	state["phase"] = "fling" if dumping else ""
	await _steps(ap, skel, dt, 2.0, state)
	state["phase"] = ""
	out["fling_head_penetration_m"] = snappedf(state["pen"], 0.0001)
	out["fling_penetration_at"] = state["pen_at"]
	out["fling_collision_hits"] = mod.collision_hits
	if state["pen"] > 0.005:
		out["failures"].append("thrown at the head, a strand went %.4f m into it" % state["pen"])

	# run
	skel.reset_bone_poses()
	var clip := _clip(ap)
	if clip == "":
		out["failures"].append("no clip to run")
	else:
		out["clip"] = clip
		ap.get_animation(clip).loop_mode = Animation.LOOP_LINEAR
		ap.play(clip)
		await _steps(ap, skel, dt, float(args.get("warmup", "0.5")), state)
		state["pen"] = 0.0
		state["pen_at"] = []
		for m in mods:
			m.reset_stats()
		state["phase"] = "run" if dumping else ""
		var swing: Array = await _steps(ap, skel, dt, float(args.get("run_s", "4.0")), state, true)
		state["phase"] = ""
		out["swing_deg"] = snappedf(swing.max(), 0.01)
		out["swing_mean_deg"] = snappedf(_mean(swing), 0.01)
		out["run_peak_bone_angle_deg"] = mod.peak_angle_deg
		out["run_limit_hits"] = mod.limit_hits
		out["run_collision_hits"] = mod.collision_hits
		out["run_head_penetration_m"] = snappedf(state["pen"], 0.0001)
		out["run_penetration_at"] = state["pen_at"]
		out["run_usec_per_frame"] = mod.stats()["usec_per_frame"]
		out["run_accel_clamps"] = mod.accel_clamps
		if swing.max() < 3.0:
			out["failures"].append("the run swings the strands only %.2f deg" % swing.max())
		if state["pen"] > 0.005:
			out["failures"].append("running, a strand went %.4f m into the head" % state["pen"])

	# hitch: one frame of HITCH_S in the middle of the run - a level load, a breakpoint, a window
	# dragged. The frame may simulate at most StrandModifier.MAX_STEPS steps (so a stall costs a
	# bounded amount and cannot make the next frame worse), and the strand must come out of it finite,
	# out of the head, and still swinging within its limits over the half second after.
	state["pen"] = 0.0
	state["pen_at"] = []
	for m in mods:
		m.reset_stats()
	if ap != null and ap.is_playing():
		ap.advance(HITCH_S)
	skel.advance(HITCH_S)
	await process_frame
	var after: Array = await _steps(ap, skel, dt, 0.5, state)
	var hitch: Dictionary = mod.stats()
	out["hitch_s"] = HITCH_S
	out["hitch_steps"] = hitch["peak_steps"]
	out["hitch_dropped_steps"] = hitch["dropped_steps"]
	out["hitch_head_penetration_m"] = snappedf(state["pen"], 0.0001)
	out["hitch_peak_deg"] = snappedf(after.max() if not after.is_empty() else 0.0, 0.01)
	if int(hitch["peak_steps"]) > StrandModifier.MAX_STEPS:
		out["failures"].append("a %.2f s frame simulated %d steps (at most %d)"
			% [HITCH_S, int(hitch["peak_steps"]), StrandModifier.MAX_STEPS])
	if int(hitch["dropped_steps"]) <= 0:
		out["failures"].append("a %.2f s frame dropped no steps: the cap did not engage" % HITCH_S)
	if state["pen"] > 0.005:
		out["failures"].append("after a %.2f s frame, a strand went %.4f m into the head" % [HITCH_S, state["pen"]])
	var nonfinite := 0
	for m in mods:
		nonfinite += m.nonfinite
	for b in skel.get_bone_count():
		var xf := skel.get_bone_global_pose(b)
		if not (xf.origin.is_finite() and xf.basis.x.is_finite() and xf.basis.y.is_finite() and xf.basis.z.is_finite()):
			nonfinite += 1
	out["nonfinite"] = nonfinite
	if nonfinite > 0:
		out["failures"].append("%d non-finite states or poses" % nonfinite)
	out["measured_frames"] = measured["n"]
	if dumping:
		var f := FileAccess.open(args["dump"], FileAccess.WRITE)
		f.store_string(JSON.stringify({"fps": rate, "clip": out.get("clip", ""), "frames": state["frames"]}))
		f.close()
	body.queue_free()
	return out


func _mesh_named(n: Node, name: String) -> MeshInstance3D:
	for m in n.find_children("*", "MeshInstance3D", true, false):
		if String(m.name) == name:
			return m
	return null


func _clip(ap: AnimationPlayer) -> String:
	if ap == null:
		return ""
	if args.has("clip"):
		return args["clip"] if ap.has_animation(args["clip"]) else ""
	var best := ""
	for n in ap.get_animation_list():
		if "Run" in String(n):
			return n
		if best == "" or ap.get_animation(n).length > ap.get_animation(best).length:
			best = n
	return best


## Advance `seconds` at `dt`, one engine frame a step (the skeleton applies its modifiers in its
## deferred update, not inside `advance`). Returns the per-step series: the largest bone angle of any modifier,
## or with `tips`, the largest tip deflection of any chain in its root bone's frame.
func _steps(ap: AnimationPlayer, skel: Skeleton3D, dt: float, seconds: float, state: Dictionary, tips := false) -> Array:
	var series := []
	var n := int(round(seconds / dt))
	for i in n:
		if ap != null and ap.is_playing():
			ap.advance(dt)
		skel.advance(dt)
		await process_frame
		series.append(float(state["tip"]) if tips else _max_angle(state["mods"]))
	return series


func _max_angle(mods: Array) -> float:
	var worst := 0.0
	for m in mods:
		for ch in m.chains:
			for b in ch["bones"]:
				worst = maxf(worst, rad_to_deg(float(b["angle"])))
	return worst


## How far each chain's tip has swung, as an angle at its first bone's head, in the root bone's frame.
func _tip_deflection(skel: Skeleton3D, mods: Array) -> float:
	var worst := 0.0
	for m in mods:
		for ch in m.chains:
			var bones: Array = ch["bones"]
			if bones.is_empty() or ch["root_bone"] < 0:
				continue
			var first: int = bones[0]["bone"]
			var last: Dictionary = bones[-1]
			var root_pose := skel.get_bone_global_pose(ch["root_bone"])
			var root_rest := skel.get_bone_global_rest(ch["root_bone"])
			var h_now := root_pose.affine_inverse() * skel.get_bone_global_pose(first).origin
			var t_now := root_pose.affine_inverse() * (skel.get_bone_global_pose(last["bone"]) * (last["tail_local"] as Vector3))
			var h_rest := root_rest.affine_inverse() * skel.get_bone_global_rest(first).origin
			var t_rest := root_rest.affine_inverse() * (skel.get_bone_global_rest(last["bone"]) * (last["tail_local"] as Vector3))
			var a := (t_now - h_now).normalized()
			var b := (t_rest - h_rest).normalized()
			worst = maxf(worst, rad_to_deg(acos(clampf(a.dot(b), -1.0, 1.0))))
	return worst


func _settle_time(series: Array, below: float, dt: float) -> float:
	for i in range(series.size() - 1, -1, -1):
		if series[i] > below:
			return (i + 1) * dt
	return 0.0


func _mean(xs: Array) -> float:
	var s := 0.0
	for x in xs:
		s += x
	return s / maxf(xs.size(), 1)


## World direction from the strands' middle toward the head collider's centre.
func _toward_head(skel: Skeleton3D, mod) -> Vector3:
	var c := Vector3.ZERO
	var head_c := Vector3.ZERO
	for col in mod.colliders:
		if col["name"] == "head":
			head_c = skel.global_transform * (skel.get_bone_global_pose(col["bone"]) * (col["a_local"] as Vector3))
	var n := 0
	for ch in mod.chains:
		for b in ch["bones"]:
			c += skel.global_transform * skel.get_bone_global_pose(b["bone"]).origin
			n += 1
	c /= maxf(n, 1)
	var d := head_c - c
	d.y = 0.0
	return d.normalized() if d.length() > 1e-6 else Vector3.FORWARD


## Skinning data for a mesh: positions, and per vertex [(skeleton bone, bind pose, weight)].
func _skin_data(gm: MeshInstance3D, skel: Skeleton3D) -> Dictionary:
	var verts := PackedVector3Array()
	var infl: Array = []
	var skin := gm.skin
	var bind_bone := []
	for bi in skin.get_bind_count():
		var bn := skin.get_bind_name(bi)
		bind_bone.append(skel.find_bone(bn) if bn != "" else skin.get_bind_bone(bi))
	for s in gm.mesh.get_surface_count():
		var arr := gm.mesh.surface_get_arrays(s)
		var pos: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
		var bones = arr[Mesh.ARRAY_BONES]
		var weights = arr[Mesh.ARRAY_WEIGHTS]
		if bones == null or weights == null:
			continue
		var per: int = bones.size() / pos.size()
		for i in pos.size():
			var list := []
			for k in per:
				var w: float = weights[i * per + k]
				if w > 1e-4:
					var bi: int = bones[i * per + k]
					list.append([bind_bone[bi], skin.get_bind_pose(bi), w])
			verts.append(pos[i])
			infl.append(list)
	return {"verts": verts, "infl": infl}


func _skinned(h: Dictionary, i: int, skel: Skeleton3D, rest: bool) -> Vector3:
	var p := Vector3.ZERO
	var v: Vector3 = h["verts"][i]
	for x in h["infl"][i]:
		var pose := skel.get_bone_global_rest(x[0]) if rest else skel.get_bone_global_pose(x[0])
		p += (pose * ((x[1] as Transform3D) * v)) * float(x[2])
	return p


## The head's surface as a radius per direction round its skin's centroid, in the head bone's frame.
func _head_table(skel: Skeleton3D, mod, strand_meshes: Array) -> Dictionary:
	var head_bone := -1
	for col in mod.colliders:
		if col["name"] == "head":
			head_bone = col["bone"]
	if head_bone < 0:
		return {}
	var local := PackedVector3Array()
	for gm in skel.find_children("*", "MeshInstance3D", true, false):
		if gm in strand_meshes or gm.skin == null:
			continue
		var h := _skin_data(gm, skel)
		var inv := skel.get_bone_global_rest(head_bone).affine_inverse()
		for i in h["verts"].size():
			var best := -1.0
			var bb := -1
			for x in h["infl"][i]:
				if float(x[2]) > best:
					best = float(x[2])
					bb = x[0]
			if bb == head_bone:
				local.append(inv * _skinned(h, i, skel, true))
	if local.size() < 16:
		return {}
	var c := Vector3.ZERO
	for p in local:
		c += p
	c /= local.size()
	var radius := PackedFloat32Array()
	radius.resize(LAT * LON)
	radius.fill(-1.0)
	for p in local:
		var k := _cell(p - c)
		radius[k] = maxf(radius[k], (p - c).length())
	return {"bone": head_bone, "centre": c, "radius": radius, "vertices": local.size()}


func _cell(d: Vector3) -> int:
	var r := d.length()
	if r < 1e-9:
		return 0
	var lat := clampi(int((acos(clampf(d.y / r, -1.0, 1.0)) / PI) * LAT), 0, LAT - 1)
	var lon := clampi(int(((atan2(d.z, d.x) + PI) / TAU) * LON), 0, LON - 1)
	return lat * LON + lon


## Per strand vertex, how deep inside the head's surface it is (negative outside). A cell the head's
## skin does not reach (the neck opening) reads as outside.
func _depths(h: Dictionary, skel: Skeleton3D, head: Dictionary, rest: bool) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(h["verts"].size())
	var hb: int = head["bone"]
	var inv := (skel.get_bone_global_rest(hb) if rest else skel.get_bone_global_pose(hb)).affine_inverse()
	var c: Vector3 = head["centre"]
	for i in h["verts"].size():
		var d := inv * _skinned(h, i, skel, rest) - c
		var r := _radius_at(head, d)
		out[i] = (r - d.length()) if r > 0.0 else -1.0
	return out


## The head's surface along `d`, read between the four cell centres round it. A nearest-cell read
## steps by however much the surface changes from one cell to the next - 2 cm on an MPFB woman, where
## the hair tie a ponytail is gathered in stands off the skull - and a strand vertex resting on such a
## step went from 12 mm outside the head to 9 mm inside it on a 3 mm move, which is not a penetration
## but the step. Cells the surface never reached are left out; all four means no surface here.
func _radius_at(head: Dictionary, d: Vector3) -> float:
	var r := d.length()
	if r < 1e-9:
		return -1.0
	var radius: PackedFloat32Array = head["radius"]
	var fi := acos(clampf(d.y / r, -1.0, 1.0)) / PI * LAT - 0.5
	var fj := (atan2(d.z, d.x) + PI) / TAU * LON - 0.5
	var i0 := floori(fi)
	var j0 := floori(fj)
	var ti := fi - i0
	var tj := fj - j0
	var total := 0.0
	var weight := 0.0
	for a in 2:
		var i := clampi(i0 + a, 0, LAT - 1)
		var wi := ti if a == 1 else 1.0 - ti
		for b in 2:
			var j := posmod(j0 + b, LON)
			var v: float = radius[i * LON + j]
			if v <= 0.0:
				continue
			var w := wi * (tj if b == 1 else 1.0 - tj)
			total += v * w
			weight += w
	return total / weight if weight > 1e-6 else -1.0


## Called when the skeleton has applied its modifiers (the only moment the sprung poses can be read:
## they are gone again after skinning).
func _measure(state: Dictionary, measured: Dictionary) -> void:
	measured["n"] += 1
	state["tip"] = _tip_deflection(state["skel"], state["mods"])
	if state["phase"] != "":
		var sk: Skeleton3D = state["skel"]
		var chains_out := []
		for m in state["mods"]:
			for ch in m.chains:
				var js := []
				for b in ch["bones"]:
					var xf := sk.get_bone_global_pose(b["bone"])
					if js.is_empty():
						js.append([xf.origin.x, xf.origin.y, xf.origin.z])
					var t := xf * (b["tail_local"] as Vector3)
					js.append([t.x, t.y, t.z])
				chains_out.append(js)
		var ap: AnimationPlayer = state["ap"]
		state["frames"].append({"phase": state["phase"], "clip_s": ap.current_animation_position if ap != null and ap.is_playing() else 0.0,
			"tip_deg": state["tip"], "chains": chains_out})
	if state["head"].is_empty():
		return
	for k in state["hair"].size():
		var h: Dictionary = state["hair"][k]
		var now := _depths(h, state["skel"], state["head"], false)
		var rest: PackedFloat32Array = state["rest_depth"][k]
		for i in now.size():
			var excess := now[i] - maxf(rest[i], 0.0)
			if excess > state["pen"]:
				state["pen"] = excess
				# where on the strand: the vertex's rest position, and its strongest bone
				var best := [-1, 0.0]
				for x in h["infl"][i]:
					if float(x[2]) > best[1]:
						best = [x[0], float(x[2])]
				var at := _skinned(h, i, state["skel"], true)
				state["pen_at"] = [snappedf(at.x, 0.001), snappedf(at.y, 0.001), snappedf(at.z, 0.001),
					state["skel"].get_bone_name(best[0]), snappedf(rest[i], 0.001)]
