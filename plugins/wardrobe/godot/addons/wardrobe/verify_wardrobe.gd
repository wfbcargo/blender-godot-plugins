extends SceneTree
## Dress a body, walk it, and measure whether any skin shows through or any hole opens.
##
##   godot --headless --fixed-fps 60 --path <project> -s res://addons/wardrobe/verify_wardrobe.gd -- \
##       body=res://assets/wardrobe/nora.glb garment=res://assets/wardrobe/nora_tshirt.glb \
##       frames=480 every=8 circle=1.2 speed=0.83 hem=true jiggle=true response=2.5
##
## Everything is measured on the skinned geometry the renderer would draw: every sampled frame,
## body and garment vertices are skinned here from the skeleton's final pose (after the hem and
## flesh modifiers), and rays are cast along each body vertex normal against the garment.
##
##   holes        hidden skin the garment no longer covers - you would see into the body.
##                A hidden vertex is covered when its outward ray meets the garment within
##                12 cm, or it has passed outside it (cloth within 6 cm behind): skin that is not
##                drawn and lies outside the cloth shows only the cloth.
##   poke         drawn skin that was under a garment at rest and has come out through it: cloth
##                within 3 cm behind it and none in front. A thigh through a hem, a breast's edge
##                through a shirt. Skin that was never under cloth - a hand swinging against a
##                shirt - is not counted: touching the outside of cloth is not coming through it.
##   match        every hidden position in the spec found a body vertex
##   hem          peak swing, backstop hits, finite, microseconds per frame
##
## Limits: holes and poke each at most 0.5% of the vertices they are counted over, in the worst
## sampled frame; every hidden position matched; hem offsets finite and within their limits.
##
## Prints `WD_RESULT ` followed by JSON.

const Wardrobe = preload("res://addons/wardrobe/wardrobe.gd")

const LIMITS := {"holes_frac": 0.005, "poke_frac": 0.005}
const UP_REACH := 0.12
const BEHIND := 0.03
const BEHIND_HIDDEN := 0.06
const CELL := 0.04
const EDGE_EPS := 1e-3

var args := {}
var body_root: Node3D
var skel: Skeleton3D
var body: MeshInstance3D
var garments: Array = []           # {mesh, spec, arrays, bind_bone}
var hems: Array = []
var body_arrays: Array
var body_bind: PackedInt32Array
var hidden_idx := PackedInt32Array()
var hidden_set := {}
var frame := 0
var frames := 480
var every := 8
var circle := 1.2
var speed := 0.83
var angle := 0.0
var worst := {"holes": 0, "poke": 0, "holes_frame": -1, "poke_frame": -1}
var samples := 0
var sample_ms := 0.0
var equip_reports: Array = []
var finite := true
var started := false
var peak_by_bone := {}
var poke_where := {}
var under_rest := {}
var holes_where := {}


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.split("=", true, 1)
		if kv.size() == 2:
			args[kv[0]] = kv[1]
	frames = int(args.get("frames", "480"))
	every = int(args.get("every", "8"))
	circle = float(args.get("circle", "1.2"))
	speed = float(args.get("speed", "0.83"))


func _process(_delta: float) -> bool:
	if not started:
		started = true
		_setup()
		return false
	frame += 1
	if circle > 0.0:
		angle += speed / circle * (1.0 / 60.0)
		body_root.position = Vector3(cos(angle), 0, -sin(angle)) * circle
		body_root.rotation = Vector3(0, angle, 0)
	if frame >= frames:
		_finish()
		return true
	return false


func _setup() -> void:
	var packed: PackedScene = load(args.get("body", "res://assets/wardrobe/nora.glb"))
	body_root = packed.instantiate()
	root.add_child(body_root)
	if args.get("jiggle", "true") == "true" and ResourceLoader.exists("res://addons/follow_through/follow_through.gd"):
		var ft = load("res://addons/follow_through/follow_through.gd")
		for rep in ft.apply(body_root, {"routes": ["jiggle_bones"]}):
			if rep.get("built", false):
				rep["body"].response_scale = float(args.get("response", "2.5"))
	var opts := {"hem": args.get("hem", "true") == "true"}
	for path in args.get("garment", "res://assets/wardrobe/nora_tshirt.glb").split(","):
		for rep in Wardrobe.equip(body_root, load(path), opts):
			equip_reports.append(rep)
			if rep.get("built", false):
				if rep.has("hem"):
					hems.append(rep["hem"])
	body = Wardrobe.body_mesh(body_root)
	skel = body.get_node(body.skeleton)
	var src: Mesh = body.get_meta(Wardrobe.META_SOURCE, body.mesh)
	body_arrays = src.surface_get_arrays(0)
	body_bind = _binds(body)
	for gm in Wardrobe.worn(body):
		garments.append({"mesh": gm, "arrays": gm.mesh.surface_get_arrays(0), "bind": _binds(gm)})
		for i in gm.get_meta(Wardrobe.META_HIDE, PackedInt32Array()):
			hidden_set[i] = true
	hidden_idx = PackedInt32Array(hidden_set.keys())
	var player: AnimationPlayer = body_root.find_children("*", "AnimationPlayer", true, false)[0]
	var clip: String = args.get("clip", player.get_animation_list()[0])
	player.get_animation(clip).loop_mode = Animation.LOOP_LINEAR
	if args.get("still", "false") != "true":
		player.play(clip)
	else:
		circle = 0.0
	_rest_under()
	skel.skeleton_updated.connect(_on_pose)


## Body vertices under a garment at rest: an outward ray meets it within UP_REACH.
func _rest_under() -> void:
	var tris := []
	for g in garments:
		var pts: PackedVector3Array = g["arrays"][Mesh.ARRAY_VERTEX]
		var nor: PackedVector3Array = g["arrays"][Mesh.ARRAY_NORMAL]
		var idx: PackedInt32Array = g["arrays"][Mesh.ARRAY_INDEX]
		var xf: Transform3D = g["mesh"].transform
		for t in range(0, idx.size(), 3):
			tris.append([xf * pts[idx[t]], xf * pts[idx[t + 1]], xf * pts[idx[t + 2]],
				(xf.basis * (nor[idx[t]] + nor[idx[t + 1]] + nor[idx[t + 2]])).normalized()])
	var grid := _grid(tris)
	var verts: PackedVector3Array = body_arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = body_arrays[Mesh.ARRAY_NORMAL]
	var bxf := body.transform
	for i in verts.size():
		var p := bxf * verts[i]
		var n := (bxf.basis * normals[i]).normalized()
		if _ray(grid, tris, p + n * 0.0005, n, UP_REACH) >= 0.0:
			under_rest[i] = true


func _grid(tris: Array) -> Dictionary:
	var grid := {}
	for ti in tris.size():
		var t: Array = tris[ti]
		var lo: Vector3 = (t[0] as Vector3).min(t[1]).min(t[2])
		var hi: Vector3 = (t[0] as Vector3).max(t[1]).max(t[2])
		for x in range(floori(lo.x / CELL), floori(hi.x / CELL) + 1):
			for y in range(floori(lo.y / CELL), floori(hi.y / CELL) + 1):
				for z in range(floori(lo.z / CELL), floori(hi.z / CELL) + 1):
					var k := Vector3i(x, y, z)
					if grid.has(k):
						grid[k].append(ti)
					else:
						grid[k] = [ti]
	return grid


func _binds(mi: MeshInstance3D) -> PackedInt32Array:
	var out := PackedInt32Array()
	for b in mi.skin.get_bind_count():
		out.append(skel.find_bone(mi.skin.get_bind_name(b)) if skel != null else -1)
	return out


func _on_pose() -> void:
	if frame % every != 0 or frame == 0:
		return
	var t0 := Time.get_ticks_msec()
	for h in hems:
		for b in h.bones:
			var e: Vector3 = b["offset"]
			if not e.is_finite():
				finite = false
			peak_by_bone[b["name"]] = maxf(peak_by_bone.get(b["name"], 0.0), e.length())
	var bpos := _skin(body, body_arrays, body_bind)
	var tris := []                     # [a, b, c, n]
	for g in garments:
		var gp := _skin(g["mesh"], g["arrays"], g["bind"])
		var idx: PackedInt32Array = g["arrays"][Mesh.ARRAY_INDEX]
		var pts: PackedVector3Array = gp[0]
		for t in range(0, idx.size(), 3):
			var a := pts[idx[t]]
			var b := pts[idx[t + 1]]
			var c := pts[idx[t + 2]]
			var n: Vector3 = gp[1][idx[t]] + gp[1][idx[t + 1]] + gp[1][idx[t + 2]]
			tris.append([a, b, c, n.normalized()])
	var grid := {}
	for ti in tris.size():
		var t: Array = tris[ti]
		var lo: Vector3 = (t[0] as Vector3).min(t[1]).min(t[2])
		var hi: Vector3 = (t[0] as Vector3).max(t[1]).max(t[2])
		for x in range(floori(lo.x / CELL), floori(hi.x / CELL) + 1):
			for y in range(floori(lo.y / CELL), floori(hi.y / CELL) + 1):
				for z in range(floori(lo.z / CELL), floori(hi.z / CELL) + 1):
					var k := Vector3i(x, y, z)
					if grid.has(k):
						grid[k].append(ti)
					else:
						grid[k] = [ti]
	var pos: PackedVector3Array = bpos[0]
	var nor: PackedVector3Array = bpos[1]
	var holes := 0
	var pokes := 0
	var candidates := 0
	var where := {}
	var hole_at := {}
	var hole_candidates: Array[int] = []
	for i in pos.size():
		var p := pos[i]
		var cell := Vector3i(floori(p.x / CELL), floori(p.y / CELL), floori(p.z / CELL))
		var near := false
		for dx in [-1, 0, 1]:
			for dy in [-1, 0, 1]:
				for dz in [-1, 0, 1]:
					if grid.has(cell + Vector3i(dx, dy, dz)):
						near = true
		var is_hidden := hidden_set.has(i)
		# skin with no cloth in the cells around it is only skipped when drawn: hidden skin under a
		# hem hanging 5-8 cm off the back had none within a cell and was counted a hole at rest (47)
		if not near and not is_hidden:
			continue
		var n := nor[i].normalized()
		var up := _ray(grid, tris, p + n * 0.0005, n, UP_REACH)
		if is_hidden:
			if up < 0.0 and _ray(grid, tris, p - n * 0.0005, -n, BEHIND_HIDDEN) < 0.0:
				hole_candidates.append(i)
			continue
		if not under_rest.has(i):
			continue
		candidates += 1
		if up < 0.0 and _ray(grid, tris, p - n * 0.0005, -n, BEHIND) >= 0.0:
			pokes += 1
			var bn := _dominant_bone(i)
			where[bn] = where.get(bn, 0) + 1
	# skin folded shut - an armpit with the arm down - meets its own body along its normal before any
	# cloth: no one can see into it, and 60 such vertices a frame were counted holes
	if not hole_candidates.is_empty():
		var btris := []
		var bidx: PackedInt32Array = body_arrays[Mesh.ARRAY_INDEX]
		var near_cells := {}
		for i in hole_candidates:
			var c := Vector3i(floori(pos[i].x / CELL), floori(pos[i].y / CELL), floori(pos[i].z / CELL))
			for dx in range(-3, 4):
				for dy in range(-3, 4):
					for dz in range(-3, 4):
						near_cells[c + Vector3i(dx, dy, dz)] = true
		for t in range(0, bidx.size(), 3):
			var a := pos[bidx[t]]
			if not near_cells.has(Vector3i(floori(a.x / CELL), floori(a.y / CELL), floori(a.z / CELL))):
				continue
			btris.append([a, pos[bidx[t + 1]], pos[bidx[t + 2]], Vector3.ZERO])
		var bgrid := _grid(btris)
		for i in hole_candidates:
			var n := nor[i].normalized()
			if _ray(bgrid, btris, pos[i] + n * 0.002, n, UP_REACH) >= 0.0:
				continue
			holes += 1
			if args.get("trace", "") == "holes":
				print("WD_HOLE ", body_arrays[Mesh.ARRAY_VERTEX][i])
			var hb := _dominant_bone(i)
			hole_at[hb] = hole_at.get(hb, 0) + 1
	samples += 1
	if args.get("trace", "false") == "true":
		print("WD_TRACE frame %d holes %d poke %d %s" % [frame, holes, pokes, hole_at])
	if holes > worst["holes"]:
		worst["holes"] = holes
		worst["holes_frame"] = frame
		holes_where = hole_at
	if pokes > worst["poke"]:
		worst["poke"] = pokes
		worst["poke_frame"] = frame
		poke_where = where
	worst["candidates"] = maxi(worst.get("candidates", 0), candidates)
	sample_ms += Time.get_ticks_msec() - t0


func _dominant_bone(i: int) -> String:
	var bones: PackedInt32Array = body_arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = body_arrays[Mesh.ARRAY_WEIGHTS]
	var per: int = bones.size() / (body_arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
	var best := 0
	for k in per:
		if weights[i * per + k] > weights[i * per + best]:
			best = k
	return body.skin.get_bind_name(bones[i * per + best])


## Skinned positions and normals in skeleton space.
func _skin(mi: MeshInstance3D, arrays: Array, bind_bone: PackedInt32Array) -> Array:
	var xf: Array[Transform3D] = []
	for b in mi.skin.get_bind_count():
		var bone := bind_bone[b]
		xf.append((skel.get_bone_global_pose(bone) if bone >= 0 else Transform3D.IDENTITY) * mi.skin.get_bind_pose(b))
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var per := bones.size() / verts.size()
	var mesh_xf := mi.transform
	var out_p := PackedVector3Array()
	var out_n := PackedVector3Array()
	out_p.resize(verts.size())
	out_n.resize(verts.size())
	for i in verts.size():
		var p := Vector3.ZERO
		var n := Vector3.ZERO
		var v := mesh_xf * verts[i]
		var nv := mesh_xf.basis * normals[i]
		for k in per:
			var w := weights[i * per + k]
			if w <= 0.0:
				continue
			var t: Transform3D = xf[bones[i * per + k]]
			p += (t * v) * w
			n += (t.basis * nv) * w
		out_p[i] = p
		out_n[i] = n
	return [out_p, out_n]


## Distance to the first garment triangle along a ray, or -1. Cells are gathered around every
## sample along the ray, so a ray crossing a cell corner cannot skip the cell it crosses.
func _ray(grid: Dictionary, tris: Array, o: Vector3, d: Vector3, reach: float) -> float:
	var seen := {}
	var cells := {}
	var best := -1.0
	var steps := int(ceil(reach / (CELL * 0.5))) + 1
	for s in steps:
		var q := o + d * (reach * s / float(steps - 1))
		var c := Vector3i(floori(q.x / CELL), floori(q.y / CELL), floori(q.z / CELL))
		for dx in [-1, 0, 1]:
			for dy in [-1, 0, 1]:
				for dz in [-1, 0, 1]:
					cells[c + Vector3i(dx, dy, dz)] = true
	for k in cells:
		if not grid.has(k):
			continue
		for ti in grid[k]:
			if seen.has(ti):
				continue
			seen[ti] = true
			var t: Array = tris[ti]
			var hit := _tri(o, d, t[0], t[1], t[2])
			if hit >= 0.0 and hit <= reach and (best < 0.0 or hit < best):
				best = hit
	return best


static func _tri(o: Vector3, d: Vector3, a: Vector3, b: Vector3, c: Vector3) -> float:
	var e1 := b - a
	var e2 := c - a
	var p := d.cross(e2)
	var det := e1.dot(p)
	if absf(det) < 1e-12:
		return -1.0
	var inv := 1.0 / det
	var s := o - a
	# a tolerance on the edges: a garment cut from the body puts each cloth vertex exactly on its
	# skin vertex's normal, so these rays pass through vertices, where exact tests miss every
	# triangle around it (72 "holes" at rest without it)
	var u := s.dot(p) * inv
	if u < -EDGE_EPS or u > 1.0 + EDGE_EPS:
		return -1.0
	var q := s.cross(e1)
	var v := d.dot(q) * inv
	if v < -EDGE_EPS or u + v > 1.0 + EDGE_EPS:
		return -1.0
	return e2.dot(q) * inv


func _finish() -> void:
	var problems := PackedStringArray()
	var equip := []
	for rep in equip_reports:
		var r := {}
		for k in rep:
			if k != "mesh" and k != "hem":
				r[k] = rep[k]
		equip.append(r)
		if not rep.get("built", false):
			problems.append("not built: %s" % [rep.get("problems")])
		for p in rep.get("problems", []):
			problems.append(p)
		var hide: Dictionary = rep.get("hide", {})
		if int(hide.get("hide_unmatched", 0)) > 0:
			problems.append("%d hidden positions matched no body vertex" % hide["hide_unmatched"])
	var hem_stats := []
	var over := 0
	for h in hems:
		var st: Dictionary = h.stats()
		hem_stats.append(st)
		for b in h.bones:
			if peak_by_bone.get(b["name"], 0.0) > float(b["max_offset"]) + 1e-4:
				over += 1
	var holes_frac := float(worst["holes"]) / maxf(hidden_idx.size(), 1)
	var poke_frac := float(worst["poke"]) / maxf(float(body_arrays[Mesh.ARRAY_VERTEX].size() - hidden_idx.size()), 1.0)
	if holes_frac > LIMITS["holes_frac"]:
		problems.append("holes: %d hidden verts uncovered (%.2f%%) at frame %d" % [worst["holes"], holes_frac * 100, worst["holes_frame"]])
	if poke_frac > LIMITS["poke_frac"]:
		problems.append("poke: %d drawn verts through the garment (%.2f%%) at frame %d" % [worst["poke"], poke_frac * 100, worst["poke_frame"]])
	if not finite:
		problems.append("a hem offset went non-finite")
	if over > 0:
		problems.append("%d hem bones swung past max_offset_m" % over)
	var result := {
		"body": args.get("body", ""), "garment": args.get("garment", ""), "hem": args.get("hem", "true"),
		"frames": frame, "samples": samples, "sample_ms": snappedf(sample_ms / maxf(samples, 1), 0.1),
		"hidden_verts": hidden_idx.size(), "holes_worst": worst["holes"], "holes_frac": snappedf(holes_frac, 0.00001),
		"poke_worst": worst["poke"], "poke_frac": snappedf(poke_frac, 0.00001), "poke_candidates": worst.get("candidates", 0),
		"poke_by_bone": poke_where, "holes_by_bone": holes_where, "hem_stats": hem_stats, "equip": equip,
		"passed": problems.is_empty(), "problems": problems,
	}
	print("WD_RESULT " + JSON.stringify(result))
