extends SceneTree
## Dress a body, walk it, and measure whether any skin shows through or any hole opens.
##
##   godot --headless --fixed-fps 60 --path <project> -s res://addons/wardrobe/verify_wardrobe.gd -- \
##       body=res://assets/wardrobe/nora.glb garment=res://assets/wardrobe/nora_tshirt.glb \
##       frames=480 every=8 circle=1.2 speed=0.83 hem=true jiggle=true response=2.5
##
## Everything is measured on the skinned geometry the renderer would draw: every sampled frame,
## body and garment vertices are skinned here from the skeleton's final pose (after the hem and
## flesh modifiers), and lines are cast from each body vertex, starting at the skin, against the
## garment and the drawn body.
##
##   holes        hidden skin a viewer can see into. A hidden vertex is covered when the line along
##                its normal crosses the garment within 12 cm in front or 6 cm behind (skin that is
##                not drawn and lies outside the cloth shows only the cloth). Otherwise it is looked
##                at from 48 directions within 80 degrees of its normal, 50 cm out: it is a hole
##                only if some view reaches it past drawn skin and outward-facing cloth and, past
##                it, meets the inside of the body or nothing - not cloth or the outside of skin.
##   occluded     hidden skin with no cloth on its normal that no view reaches or sees into: an
##                armpit folded shut, a belly under a waistband behind raised thighs in a crouch.
##   coincident   hidden skin with the cloth within 3 mm of it, either side: pressed on, covered.
##   poke         drawn skin that was under a garment at rest and has come out through it: cloth
##                within 3 cm behind it and none in front. A thigh through a hem, a breast's edge
##                through a shirt. Skin that was never under cloth - a hand swinging against a
##                shirt - is not counted: touching the outside of cloth is not coming through it.
##   match        every hidden position in the spec found a body vertex
##   hem          peak swing, backstop hits, finite, microseconds per frame
##
## Limits: holes and poke each at most 0.5% of the vertices they are counted over, in the worst
## sampled frame; every hidden position matched; hem offsets finite and within their limits.
## occluded and coincident are reported, not limited. A run that measured nothing fails: a body,
## garment or clip= that does not exist, setup that did not finish (a script error in it leaves no
## pose hooked up), or no frame sampled.
##
## Controls and evidence: cut=<m> removes a patch of the garment and must fail; shot=<frame>, run
## with a window, renders that frame's holes (see _plan_shots). trace=true prints every sample,
## trace=holes every hole candidate with how many of its views see in.
##
## Prints `WD_RESULT ` followed by JSON.

const Wardrobe = preload("res://addons/wardrobe/wardrobe.gd")

const LIMITS := {"holes_frac": 0.005, "poke_frac": 0.005}
const UP_REACH := 0.12
const BEHIND := 0.03
const BEHIND_HIDDEN := 0.06
const CELL := 0.04
const EDGE_TOL := 0.001            # m past a triangle's edge a line still counts as crossing it
const COINCIDENT_MAX := 0.003      # cloth this close to hidden skin, either side, is pressed onto it
const VIEW_REACH := 0.5            # a line of sight this long past skin and cloth is open air
const VIEW_CONE_DEG := 80.0
const VIEW_DIRS := 48
const SHOT_VIEWS := ["open", "normal", "tilt_up", "tilt_down", "tilt_left", "tilt_right", "eye"]

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
var shots: Array = []               # {vertex, view, point, line, viewport, camera}
var shot_wait := 0
var shot_results: Array = []
var open_dir := {}                  # hole vertex -> the first view that sees into it, this sample
var view_dirs: Array[Vector3] = []  # around +Z, the normal first
var setup_problems := PackedStringArray()
var setup_done := false             # set last in _setup: a script error part-way leaves it false
var still := false                  # nothing plays, so the skeleton never updates: sample from _process
var sampled_frame := -1


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.split("=", true, 1)
		if kv.size() == 2:
			args[kv[0]] = kv[1]
	frames = int(args.get("frames", "480"))
	# a spiral over the cap within VIEW_CONE_DEG of the pole, evenly spread by area
	var cap := 1.0 - cos(deg_to_rad(VIEW_CONE_DEG))
	for k in VIEW_DIRS:
		var z := 1.0 - cap * k / float(VIEW_DIRS - 1)
		var r := sqrt(maxf(1.0 - z * z, 0.0))
		var phi := k * PI * (3.0 - sqrt(5.0))
		view_dirs.append(Vector3(r * cos(phi), r * sin(phi), z))
	every = int(args.get("every", "8"))
	circle = float(args.get("circle", "1.2"))
	speed = float(args.get("speed", "0.83"))


func _process(_delta: float) -> bool:
	if not started:
		started = true
		_setup()
		return false
	if not setup_done:
		_finish()
		return true
	if shot_wait > 0:
		shot_wait -= 1
		if shot_wait == 0:
			_capture()
			_finish()
			return true
		return false
	frame += 1
	if still:
		_on_pose()
	if circle > 0.0:
		angle += speed / circle * (1.0 / 60.0)
		body_root.position = Vector3(cos(angle), 0, -sin(angle)) * circle
		body_root.rotation = Vector3(0, angle, 0)
	if frame >= frames:
		_finish()
		return true
	return false


func _setup() -> void:
	var body_path: String = args.get("body", "res://assets/wardrobe/nora.glb")
	var packed: PackedScene = load(body_path) if ResourceLoader.exists(body_path) else null
	if packed == null:
		setup_problems.append("body not found: %s" % body_path)
		return
	for path in args.get("garment", "res://assets/wardrobe/nora_tshirt.glb").split(","):
		if not ResourceLoader.exists(path):
			setup_problems.append("garment not found: %s" % path)
	if not setup_problems.is_empty():
		return
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
	if args.has("cut"):
		_cut(float(args["cut"]))
	var players := body_root.find_children("*", "AnimationPlayer", true, false)
	if players.is_empty():
		setup_problems.append("the body has no AnimationPlayer")
		return
	var player: AnimationPlayer = players[0]
	var clips := player.get_animation_list()
	var clip: String = args.get("clip", clips[0] if not clips.is_empty() else "")
	if not player.has_animation(clip):
		setup_problems.append("no clip %s; the body has %s" % [clip, ", ".join(clips)])
		return
	player.get_animation(clip).loop_mode = Animation.LOOP_LINEAR
	if args.get("still", "false") != "true":
		player.play(clip)
	else:
		circle = 0.0
		still = true
	_rest_under()
	skel.skeleton_updated.connect(_on_pose)
	setup_done = true


## cut=<radius m>: a control that must fail. Removes every garment triangle with a corner within the
## radius of a point on the cloth - by default the garment vertex nearest the middle of the hidden
## skin, or cut_at=x,y,z in the body's rest space - from what is measured and from what is drawn.
func _cut(radius: float) -> void:
	var at := Vector3.ZERO
	if args.has("cut_at"):
		var xyz: PackedStringArray = args["cut_at"].split(",")
		at = Vector3(float(xyz[0]), float(xyz[1]), float(xyz[2]))
	else:
		var verts: PackedVector3Array = body_arrays[Mesh.ARRAY_VERTEX]
		var mid := Vector3.ZERO
		for i in hidden_idx:
			mid += body.transform * verts[i]
		mid /= maxf(hidden_idx.size(), 1)
		var best := INF
		for g in garments:
			for v in (g["arrays"][Mesh.ARRAY_VERTEX] as PackedVector3Array):
				var w: Vector3 = g["mesh"].transform * v
				if w.distance_to(mid) < best:
					best = w.distance_to(mid)
					at = w
	var removed := 0
	for g in garments:
		var arrays: Array = g["arrays"]
		var pts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var idx: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		var xf: Transform3D = g["mesh"].transform
		var kept := PackedInt32Array()
		for t in range(0, idx.size(), 3):
			if (xf * pts[idx[t]]).distance_to(at) <= radius or (xf * pts[idx[t + 1]]).distance_to(at) <= radius \
					or (xf * pts[idx[t + 2]]).distance_to(at) <= radius:
				removed += 1
				continue
			kept.append_array([idx[t], idx[t + 1], idx[t + 2]])
		arrays[Mesh.ARRAY_INDEX] = kept
		var mi: MeshInstance3D = g["mesh"]
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		mesh.surface_set_material(0, mi.mesh.surface_get_material(0))
		mi.mesh = mesh
	print("WD_CUT %d garment triangles within %.3f m of %s" % [removed, radius, at])


## Body vertices under a garment at rest: the line along the normal meets it from just behind the
## skin (COINCIDENT_MAX) to UP_REACH in front.
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
		if not is_nan(_cross(grid, tris, p, n, -COINCIDENT_MAX, UP_REACH)):
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
	if frame % every != 0 or frame == 0 or shot_wait > 0 or frame == sampled_frame:
		return
	sampled_frame = frame
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
			var n: Vector3 = gp[1][idx[t]] + gp[1][idx[t + 1]] + gp[1][idx[t + 2]]
			tris.append([pts[idx[t]], pts[idx[t + 1]], pts[idx[t + 2]], n.normalized()])
	var grid := _grid(tris)
	var pos: PackedVector3Array = bpos[0]
	var nor: PackedVector3Array = bpos[1]
	var holes := 0
	var pokes := 0
	var candidates := 0
	var coincident := 0
	var occluded := 0
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
		if is_hidden:
			# the line along the normal starts at the skin itself: rays started 0.5 mm off it, both
			# ways, stepped over cloth pressed within 0.5 mm and called it a hole (Belle's shorts)
			var c := _cross(grid, tris, p, n, -BEHIND_HIDDEN, UP_REACH)
			if is_nan(c):
				hole_candidates.append(i)
			elif absf(c) <= COINCIDENT_MAX:
				coincident += 1
			continue
		if not under_rest.has(i):
			continue
		candidates += 1
		if is_nan(_cross(grid, tris, p, n, 0.0, UP_REACH)) and not is_nan(_cross(grid, tris, p, n, -BEHIND, 0.0)):
			pokes += 1
			var bn := _dominant_bone(i)
			where[bn] = where.get(bn, 0) + 1
	# a hole is skin a viewer can see into. Hidden skin with no cloth on its normal can still be shut in:
	# an armpit folded with the arm down (60 vertices a frame), or a belly under a waistband with the
	# thighs raised in front of it in a crouch (8 on Belle, the thigh 13-25 cm off). Or it has come
	# out in front of cloth that its normal only grazes, and a viewer sees the cloth behind it (3 on
	# Belle's breast under the sports top's hem in a jump). Only a view that sees into the body counts.
	var hole_list: Array[int] = []
	open_dir.clear()
	if not hole_candidates.is_empty():
		var lo := pos[hole_candidates[0]]
		var hi := lo
		for i in hole_candidates:
			lo = lo.min(pos[i])
			hi = hi.max(pos[i])
		var reach_box := AABB(lo - Vector3.ONE * VIEW_REACH, hi - lo + Vector3.ONE * VIEW_REACH * 2.0)
		var btris := []
		var bidx: PackedInt32Array = body_arrays[Mesh.ARRAY_INDEX]
		for t in range(0, bidx.size(), 3):
			var a := bidx[t]
			var b := bidx[t + 1]
			var c := bidx[t + 2]
			if hidden_set.has(a) and hidden_set.has(b) and hidden_set.has(c):
				continue                   # not drawn: blocks nothing
			if not reach_box.has_point(pos[a]):
				continue
			btris.append([pos[a], pos[b], pos[c], (nor[a] + nor[b] + nor[c]).normalized()])
		var bgrid := _grid(btris)
		var tracing: bool = args.get("trace", "") == "holes"
		for i in hole_candidates:
			var n := nor[i].normalized()
			var open := _open_views(grid, tris, bgrid, btris, pos[i], n, tracing, i)
			if tracing:
				print("WD_HOLE v%d %s open %d/%d" % [i, body_arrays[Mesh.ARRAY_VERTEX][i], open, view_dirs.size()])
			if open == 0:
				occluded += 1
				continue
			holes += 1
			hole_list.append(i)
			var hb := _dominant_bone(i)
			hole_at[hb] = hole_at.get(hb, 0) + 1
	samples += 1
	if args.has("shot") and frame == int(args["shot"]) and shots.is_empty():
		_plan_shots(hole_list, pos, nor)
	if args.get("trace", "false") == "true":
		print("WD_TRACE frame %d holes %d occluded %d coincident %d poke %d %s" % [frame, holes, occluded, coincident, pokes, hole_at])
	if holes > worst["holes"]:
		worst["holes"] = holes
		worst["holes_frame"] = frame
		holes_where = hole_at
	if pokes > worst["poke"]:
		worst["poke"] = pokes
		worst["poke_frame"] = frame
		poke_where = where
	worst["candidates"] = maxi(worst.get("candidates", 0), candidates)
	worst["coincident"] = maxi(worst.get("coincident", 0), coincident)
	worst["occluded"] = maxi(worst.get("occluded", 0), occluded)
	sample_ms += Time.get_ticks_msec() - t0


## How many views of p, from within VIEW_CONE_DEG of its normal and VIEW_REACH away, see into the
## body. A view along d is blocked by any drawn skin (the body is closed, so a line through it always
## leaves through a face turned to the viewer) or by cloth turned to the viewer. Past p the viewer
## sees the first surface turned to them: cloth or skin covers p, the inside of the body (a back face)
## or nothing at all is a hole. Back faces of cloth are culled and seen through. Stops at the first
## view that sees in unless `all`.
func _open_views(grid: Dictionary, tris: Array, bgrid: Dictionary, btris: Array, p: Vector3, n: Vector3, all: bool, vertex: int) -> int:
	var to_n := Basis.IDENTITY
	if n.dot(Vector3.BACK) < -0.9999:
		to_n = Basis(Vector3.UP, PI)
	else:
		to_n = Basis(Quaternion(Vector3.BACK, n))
	var open := 0
	for local in view_dirs:
		var d: Vector3 = to_n * local
		# 2 mm off the skin: the drawn triangles around a vertex at the edge of the hidden skin touch it
		if not _hits(bgrid, btris, p + d * 0.002, d, VIEW_REACH, Vector3.ZERO).is_empty():
			continue
		if not _hits(grid, tris, p, d, VIEW_REACH, d).is_empty():
			continue
		var behind := _hits(bgrid, btris, p - d * 0.002, -d, VIEW_REACH, Vector3.ZERO)
		var cloth_behind := _hits(grid, tris, p, -d, VIEW_REACH, d)
		var cloth_at: float = cloth_behind[0][0] if not cloth_behind.is_empty() else INF
		if not behind.is_empty() and behind[0][0] + 0.002 < cloth_at:
			if (behind[0][1] as Vector3).dot(d) > 0.0:
				continue                   # the outside of other skin
		elif cloth_at < INF:
			continue                       # cloth turned to the viewer
		open += 1
		if open == 1:
			open_dir[vertex] = d
		if not all:
			break
	return open


## Crossings along o + t*d for 0 <= t <= reach, nearest first, as [t, face normal]. A non-zero `viewer`
## keeps only faces turned towards a viewer off in that direction (normal . viewer > 0).
func _hits(grid: Dictionary, tris: Array, o: Vector3, d: Vector3, reach: float, viewer: Vector3) -> Array:
	var out := []
	for ti in _cells_along(grid, o + d * (reach * 0.5), d, reach * 0.5):
		var t: Array = tris[ti]
		var hit := _tri(o, d, t[0], t[1], t[2])
		if hit >= 0.0 and hit <= reach and (viewer == Vector3.ZERO or (t[3] as Vector3).dot(viewer) > 0.0):
			out.append([hit, t[3]])
	out.sort_custom(func(x, y): return x[0] < y[0])
	return out


## shot=<frame>: render every hole vertex of that sampled frame from outside, then stop. Needs a
## window (not --headless). Each view is its own SubViewport rendered once in the very frame that was
## measured - pausing instead lets the jiggle and hem springs move on, or drop their offsets. The
## body is drawn tan on its front faces and magenta on its back faces, the garment blue as the game
## culls it: magenta near the vertex means you can see into the body. Each view also names what the
## line from the vertex to the camera meets. shot_verts=a,b limits the vertices, shot_dist= sets the
## camera distance (0.3 m), shot_dir= saves the PNGs.
func _plan_shots(hole_list: Array[int], pos: PackedVector3Array, nor: PackedVector3Array) -> void:
	if DisplayServer.get_name() == "headless":
		print("WD_SHOT skipped: shot= needs a window (run without --headless)")
		return
	var body_mat := ShaderMaterial.new()
	body_mat.shader = Shader.new()
	body_mat.shader.code = "shader_type spatial;\nrender_mode unshaded, cull_disabled;\nvoid fragment() { ALBEDO = FRONT_FACING ? vec3(0.8, 0.65, 0.5) : vec3(1.0, 0.0, 1.0); }"
	body.material_override = body_mat
	var cloth_mat := StandardMaterial3D.new()
	cloth_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	cloth_mat.albedo_color = Color(0.15, 0.3, 0.9)
	for g in garments:
		g["mesh"].material_override = cloth_mat
	var only: Array = Array(args.get("shot_verts", "").split(",", false)).map(func(x): return int(x))
	var dist := float(args.get("shot_dist", "0.3"))
	var sxf := skel.global_transform
	var fwd := (body_root.global_transform.basis.z * Vector3(1, 0, 1)).normalized()
	for i in hole_list:
		if not only.is_empty() and not only.has(i):
			continue
		var p: Vector3 = sxf * pos[i]
		var n: Vector3 = (sxf.basis * nor[i]).normalized()
		var side := n.cross(Vector3.UP).normalized()
		var up := side.cross(n).normalized()
		var dirs := {
			"normal": n, "tilt_up": n.rotated(side, deg_to_rad(-35)), "tilt_down": n.rotated(side, deg_to_rad(35)),
			"tilt_left": n.rotated(up, deg_to_rad(35)), "tilt_right": n.rotated(up, deg_to_rad(-35)),
			"eye": (fwd + Vector3.UP * 0.6).normalized(), "open": (sxf.basis * open_dir[i]).normalized() if open_dir.has(i) else n,
		}
		for view in SHOT_VIEWS:
			var dir: Vector3 = dirs[view]
			var vp := SubViewport.new()
			vp.size = Vector2i(640, 480)
			vp.render_target_update_mode = SubViewport.UPDATE_ONCE
			root.add_child(vp)
			var cam := Camera3D.new()
			cam.fov = 50.0
			cam.near = 0.002
			vp.add_child(cam)
			cam.look_at_from_position(p + dir * dist, p, Vector3.UP if absf(dir.dot(Vector3.UP)) < 0.95 else Vector3.FORWARD)
			cam.current = true
			shots.append({"vertex": i, "view": view, "point": p, "viewport": vp, "camera": cam,
				"line": _line_to_camera(pos, sxf, p, dir, dist)})
	print("WD_SHOT frame %d: %d hole verts, %d views" % [frame, hole_list.size(), shots.size()])
	if not shots.is_empty():
		shot_wait = 3


## What the line from the vertex to the camera meets first: "open", "body at N mm" or "cloth at N mm".
func _line_to_camera(bp: PackedVector3Array, sxf: Transform3D, p: Vector3, dir: Vector3, dist: float) -> String:
	var tris := []
	var bidx: PackedInt32Array = body_arrays[Mesh.ARRAY_INDEX]
	for t in range(0, bidx.size(), 3):
		if hidden_set.has(bidx[t]) and hidden_set.has(bidx[t + 1]) and hidden_set.has(bidx[t + 2]):
			continue
		tris.append([sxf * bp[bidx[t]], sxf * bp[bidx[t + 1]], sxf * bp[bidx[t + 2]], "body"])
	for g in garments:
		var gp := _skin(g["mesh"], g["arrays"], g["bind"])
		var idx: PackedInt32Array = g["arrays"][Mesh.ARRAY_INDEX]
		for t in range(0, idx.size(), 3):
			tris.append([sxf * gp[0][idx[t]], sxf * gp[0][idx[t + 1]], sxf * gp[0][idx[t + 2]], "cloth"])
	var best := -1.0
	var what := "open"
	var o := p + dir * 0.002
	for t in tris:
		var h := _tri(o, dir, t[0], t[1], t[2])
		if h >= 0.0 and h <= dist and (best < 0.0 or h < best):
			best = h
			what = "%s at %.1f mm" % [t[3], (h + 0.002) * 1000]
	return what


func _capture() -> void:
	for s in shots:
		var img: Image = s["viewport"].get_texture().get_image()
		var c: Vector2 = s["camera"].unproject_position(s["point"])
		var counts := {"magenta": 0, "skin": 0, "cloth": 0}
		var r := 12
		for y in range(int(c.y) - r, int(c.y) + r + 1):
			for x in range(int(c.x) - r, int(c.x) + r + 1):
				if x < 0 or y < 0 or x >= img.get_width() or y >= img.get_height() or Vector2(x, y).distance_to(c) > r:
					continue
				var px := img.get_pixel(x, y)
				if px.r > 0.7 and px.g < 0.3 and px.b > 0.7:
					counts["magenta"] += 1
				elif px.b > px.r + 0.3:
					counts["cloth"] += 1
				elif px.r > px.b + 0.1 and px.g > 0.4:
					counts["skin"] += 1
		print("WD_SHOT v%d %s magenta %d skin %d cloth %d line_to_camera %s" % [s["vertex"], s["view"], counts["magenta"], counts["skin"], counts["cloth"], s["line"]])
		shot_results.append({"vertex": s["vertex"], "view": s["view"], "magenta_px": counts["magenta"],
			"skin_px": counts["skin"], "cloth_px": counts["cloth"], "line": s["line"]})
		if args.has("shot_dir"):
			img.save_png("%s/f%d_v%d_%s.png" % [args["shot_dir"], frame, s["vertex"], s["view"]])


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


## Signed distance along d from p to the triangle crossing nearest p with lo <= t <= hi, or NAN.
func _cross(grid: Dictionary, tris: Array, p: Vector3, d: Vector3, lo: float, hi: float) -> float:
	var best := NAN
	for ti in _cells_along(grid, p + d * ((lo + hi) * 0.5), d, (hi - lo) * 0.5):
		var t: Array = tris[ti]
		var hit := _tri(p, d, t[0], t[1], t[2])
		if hit >= lo and hit <= hi and (is_nan(best) or absf(hit) < absf(best)):
			best = hit
	return best


## Triangles in the cells around a segment `mid ± d * half`.
func _cells_along(grid: Dictionary, mid: Vector3, d: Vector3, half: float) -> Dictionary:
	var cells := {}
	var steps := int(ceil(half * 2.0 / (CELL * 0.5))) + 1
	for s in steps:
		var q := mid + d * (-half + half * 2.0 * s / float(maxi(steps - 1, 1)))
		var c := Vector3i(floori(q.x / CELL), floori(q.y / CELL), floori(q.z / CELL))
		for dx in [-1, 0, 1]:
			for dy in [-1, 0, 1]:
				for dz in [-1, 0, 1]:
					cells[c + Vector3i(dx, dy, dz)] = true
	var out := {}
	for k in cells:
		if grid.has(k):
			for ti in grid[k]:
				out[ti] = true
	return out


## Where the line o + t*d crosses triangle abc, as t (negative behind o), or NAN.
static func _tri(o: Vector3, d: Vector3, a: Vector3, b: Vector3, c: Vector3) -> float:
	var e1 := b - a
	var e2 := c - a
	var p := d.cross(e2)
	var det := e1.dot(p)
	if absf(det) < 1e-12:
		return NAN
	var inv := 1.0 / det
	var s := o - a
	# a tolerance on the edges, in metres: a garment cut from the body puts each cloth vertex exactly
	# on its skin vertex's normal, so these lines pass through vertices, where exact tests miss every
	# triangle around it (72 "holes" at rest without it); and at a fold the line slips between two
	# faces, missing each by 0.1-0.4 mm - 1e-3 of a 3 cm face was 0.03 mm (2 holes a frame on Belle)
	var area2 := e1.cross(e2).length()
	var u := s.dot(p) * inv
	if u < -EDGE_TOL * e2.length() / area2:
		return NAN
	var q := s.cross(e1)
	var v := d.dot(q) * inv
	if v < -EDGE_TOL * e1.length() / area2 or u + v > 1.0 + EDGE_TOL * (c - b).length() / area2:
		return NAN
	return e2.dot(q) * inv


func _finish() -> void:
	var problems := PackedStringArray(setup_problems)
	if setup_problems.is_empty() and not setup_done:
		problems.append("setup did not finish (a script error above); nothing was measured")
	elif setup_done and samples == 0:
		problems.append("no frame was sampled in %d frames (every=%d); nothing was measured" % [frame, every])
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
	var body_verts: int = body_arrays[Mesh.ARRAY_VERTEX].size() if not body_arrays.is_empty() else 0
	var poke_frac := float(worst["poke"]) / maxf(float(body_verts - hidden_idx.size()), 1.0)
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
		"poke_by_bone": poke_where, "holes_by_bone": holes_where, "holes_frame": worst["holes_frame"],
		"occluded_worst": worst.get("occluded", 0), "coincident_worst": worst.get("coincident", 0), "hem_stats": hem_stats, "equip": equip,
		"passed": problems.is_empty(), "problems": problems,
	}
	if not shot_results.is_empty():
		result["shots"] = shot_results
	print("WD_RESULT " + JSON.stringify(result))
