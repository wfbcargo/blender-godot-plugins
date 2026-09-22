extends RefCounted
## humanform fur: shell fur on a skinned, animated body, from the coverage map humanform painted on it.
##
##     const Fur := preload("res://addons/humanform_fur/fur.gd")
##     for rep in Fur.attach(model):            # after Wardrobe.equip, so garments hide fur too
##         if not rep["problems"].is_empty(): push_warning(str(rep["problems"]))
##     Fur.lod(model, camera.global_position)   # once a frame, or leave it to the camera distance
##
## What it builds. The body mesh carries `humanform_fur` in its glTF node extras (humanform's
## `fur.py`), naming three textures beside the glb and the shells' heights. `attach` adds one
## MeshInstance3D per shell as a child of the body's own Skeleton3D, each sharing the body's `mesh`
## and `skin` and pointing at the same skeleton, with one ShaderMaterial between them. The GPU
## therefore skins a shell exactly as it skins the skin: the fur cannot swim over the body, because it
## *is* the body, displaced along its own skinned normal. Nothing is simulated and nothing is stored
## between frames, so a walk and a run cost what a rest pose costs.
##
## Why the shells are ordered the way they are. `heights` comes from the file in van der Corput order -
## the outermost first, then the middle, then between - so the first M of them always span the whole
## height. A level of detail draws fewer shells at a distance without shortening the fur or moving its
## outline, and it fades the last one out over `FADE_M` rather than switching it off, so nothing pops.
##
## The skin under dense fur. `hide` lists the body vertices the fur covers, as positions in the glTF
## mesh space, exactly as wardrobe lists the skin a garment covers - because Godot's importer reorders
## vertices and splits them at UV seams, so an index means nothing across that boundary. Those
## triangles are dropped from the body's index buffer (the base coat, shell 0, is opaque and stands in
## for them), and `detach` puts the mesh back.

const SCHEMA := "humanform-fur/1"
const PROP := "humanform_fur"
const SHADER_PATH := "res://addons/humanform_fur/fur.gdshader"

const META_SPEC := "humanform_fur_spec"       ## on the body mesh: the spec it was built from
const META_SOURCE := "humanform_fur_source"   ## on the body mesh: its mesh before fur hid anything
const META_SHELLS := "humanform_fur_shells"   ## on the body mesh: the shell MeshInstance3Ds
const META_SHELL := "humanform_fur_shell"     ## on a shell: its height

const FADE_M := 1.5          ## metres over which a shell that a level of detail drops fades out
const NEAR_M := 1.2          ## every shell up to here
const FAR_M := 12.0          ## the base coat and the outline shell beyond here
const MIN_SHELLS := 2


## The fur spec on a node, or {} - the same three lines wardrobe and follow-through read extras with.
static func spec_of(node: Node) -> Dictionary:
	if node == null or not node.has_meta("extras"):
		return {}
	var extras = node.get_meta("extras")
	if typeof(extras) != TYPE_DICTIONARY or not extras.has(PROP):
		return {}
	var s = extras[PROP]
	if typeof(s) == TYPE_STRING:
		s = JSON.parse_string(s)
	return s if typeof(s) == TYPE_DICTIONARY else {}


static func validate(spec: Dictionary) -> PackedStringArray:
	var p := PackedStringArray()
	for k in ["schema", "regions", "shells", "heights", "textures", "length_max_m", "uv_scale"]:
		if not spec.has(k):
			p.append("missing " + k)
	if spec.get("schema", "") != SCHEMA:
		p.append("schema is %s, this runtime reads %s" % [spec.get("schema", "?"), SCHEMA])
	var hide: Dictionary = spec.get("hide", {})
	if not hide.is_empty():
		if hide.get("space", "") != "gltf_mesh":
			p.append("hide.space must be gltf_mesh")
		if Marshalls.base64_to_raw(hide.get("positions_f32", "")).size() != 12 * int(hide.get("count", 0)):
			p.append("hide: positions do not match count")
	return p


## Every furred mesh under `root`, with its spec.
static func find_furred(root: Node) -> Array:
	var out := []
	for n in root.find_children("*", "MeshInstance3D", true, false):
		var s := spec_of(n)
		if not s.is_empty():
			out.append({"mesh": n, "spec": s})
	return out


## Build the shells for every furred mesh under `root`. `options`:
##   dir: String        where the textures live; "" takes the directory of `root.scene_file_path`
##   hide: bool         drop the skin the fur covers (default true, and only when the spec asks)
##   shells: int        cap the shell count (0: the spec's)
## Returns one report per furred mesh: {mesh, built, shells, hidden, problems}.
static func attach(root: Node, options := {}) -> Array:
	var out := []
	for e in find_furred(root):
		out.append(_attach_one(e["mesh"], e["spec"], root, options))
	return out


static func _attach_one(mi: MeshInstance3D, spec: Dictionary, root: Node, options: Dictionary) -> Dictionary:
	var rep := {"mesh": String(mi.name), "built": false, "shells": 0, "hidden": 0,
		"problems": PackedStringArray()}
	for p in validate(spec):
		rep["problems"].append(p)
	if not rep["problems"].is_empty():
		return rep
	if mi.has_meta(META_SHELLS):
		detach(mi)
	var skel := mi.get_node_or_null(mi.skeleton) as Skeleton3D
	if skel == null:
		rep["problems"].append("%s has no skeleton: fur must be skinned with the body" % mi.name)
		return rep
	var dir: String = options.get("dir", "")
	if dir == "":
		dir = _dir_of(root, mi)
	var mat := _material(spec, dir, rep["problems"])
	if mat == null:
		return rep
	var heights: Array = spec.get("heights", [])
	var cap: int = int(options.get("shells", 0))
	if cap > 0:
		heights = heights.slice(0, cap)
	var shells: Array[MeshInstance3D] = []
	var shell_mesh := _furred_mesh(mi.mesh, float(spec.get("min_density", 0.02)))
	rep["shell_tris"] = shell_mesh[1]
	rep["body_tris"] = shell_mesh[2]
	if shell_mesh[1] <= 0:
		rep["problems"].append("no triangle on the body carries fur: the coverage map is empty or COLOR_0 "
			+ "did not survive the export (rig_analysis.export.VERTEX_COLOUR_MAPS)")
		return rep
	# the base coat first: opaque, and what stands in for the skin the fur hides
	for t in ([0.0] as Array) + heights:
		var s := MeshInstance3D.new()
		s.name = "%s_fur_%02d" % [mi.name, shells.size()]
		s.mesh = shell_mesh[0]
		s.skin = mi.skin
		var sm: ShaderMaterial = mat.duplicate()
		sm.set_shader_parameter("shell_t", float(t))
		sm.set_shader_parameter("shell_fade", 1.0)
		s.material_override = sm
		s.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF if shells.size() > 0 \
			else GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		skel.add_child(s)
		s.skeleton = s.get_path_to(skel)
		s.transform = mi.transform
		s.set_meta(META_SHELL, float(t))
		shells.append(s)
	rep["vertex_colour_off"] = _no_vertex_albedo(mi)
	mi.set_meta(META_SHELLS, shells)
	mi.set_meta(META_SPEC, spec)
	rep["shells"] = shells.size()
	var hide: Dictionary = spec.get("hide", {})
	if options.get("hide", true) and bool(spec.get("cover", true)) and not hide.is_empty():
		var r := _hide(mi, hide)
		rep["hidden"] = r["tris_hidden"]
		rep["unmatched"] = r["unmatched"]
		if r["unmatched"] > int(hide.get("count", 0)) * 0.05:
			rep["problems"].append("%d of %d covered positions did not match a vertex of the imported mesh"
				% [r["unmatched"], int(hide.get("count", 0))])
	rep["built"] = true
	return rep


## The mesh the shells are drawn from: the body's, keeping only the triangles that carry fur.
##
## A finished body is one mesh with several surfaces - skin, and the hair cap, brows and lashes Blender
## joined into it - and a shell is a copy of the whole thing. Copied whole, seventeen of them draw over the
## hair and the lashes as well, which is what turned a clean hair cap into black speckle; and they pay for
## every triangle of a bare hand, a bare foot and a bare scalp. The density is already in COLOR_0, so the
## test needs nothing the file does not carry: a triangle is kept when any corner has fur.
## Returns [mesh, kept triangles, total triangles].
static func _furred_mesh(src: Mesh, min_density: float) -> Array:
	var out := ArrayMesh.new()
	out.blend_shape_mode = src.blend_shape_mode if src is ArrayMesh else Mesh.BLEND_SHAPE_MODE_NORMALIZED
	if src is ArrayMesh:
		for i in (src as ArrayMesh).get_blend_shape_count():
			out.add_blend_shape((src as ArrayMesh).get_blend_shape_name(i))
	var kept_total := 0
	var total := 0
	for si in src.get_surface_count():
		var arrays: Array = src.surface_get_arrays(si)
		var cols: PackedColorArray = arrays[Mesh.ARRAY_COLOR] if arrays[Mesh.ARRAY_COLOR] != null 			else PackedColorArray()
		var n: int = (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
		var index: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null 			else PackedInt32Array(range(n))
		total += index.size() / 3
		# A surface with no coverage map is not skin: the hair cap, the brows and the lashes are surfaces of
		# this same mesh, and kept, they were drawn seventeen times over as fur - a black skull cap over the
		# hair. Only what carries the map can carry fur.
		if cols.size() != n:
			continue
		var kept := PackedInt32Array()
		kept.resize(index.size())
		var w := 0
		for t in range(0, index.size(), 3):
			var d := maxf(maxf(cols[index[t]].r, cols[index[t + 1]].r), cols[index[t + 2]].r)
			if d < min_density:
				continue
			kept[w] = index[t]
			kept[w + 1] = index[t + 1]
			kept[w + 2] = index[t + 2]
			w += 3
		kept.resize(w)
		kept_total += w / 3
		if w == 0:
			continue
		arrays[Mesh.ARRAY_INDEX] = kept
		var flags := 0
		if src.surface_get_format(si) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS:
			flags |= Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS
		var shapes := src.surface_get_blend_shape_arrays(si) if src is ArrayMesh else []
		out.add_surface_from_arrays(src.surface_get_primitive_type(si), arrays, shapes, {}, flags)
	return [out, kept_total, total]


## The coverage map travels as COLOR_0, and Godot's glTF importer turns on "albedo from vertex colour"
## for every material on a mesh that has one. The body's other materials - skin, hair, brows, lashes, all
## on the one mesh once Blender joined them - would then be multiplied by the fur's density and length: the
## hands and the scalp went black and the hair cap dissolved. Turn it off wherever it was turned on; the
## fur's own shader reads COLOR directly and does not care.
static func _no_vertex_albedo(mi: MeshInstance3D) -> int:
	var n := 0
	var mats := []
	if mi.mesh != null:
		for i in mi.mesh.get_surface_count():
			mats.append(mi.mesh.surface_get_material(i))
	for i in mi.get_surface_override_material_count():
		mats.append(mi.get_surface_override_material(i))
	mats.append(mi.material_override)
	for m in mats:
		var bm := m as BaseMaterial3D
		if bm != null and bm.get_flag(BaseMaterial3D.FLAG_ALBEDO_FROM_VERTEX_COLOR):
			bm.set_flag(BaseMaterial3D.FLAG_ALBEDO_FROM_VERTEX_COLOR, false)
			n += 1
	return n


## Take the fur off: the shells go, and the body's own mesh comes back.
static func detach(mi: MeshInstance3D) -> void:
	if mi.has_meta(META_SHELLS):
		for s in mi.get_meta(META_SHELLS):
			if is_instance_valid(s):
				s.queue_free()
		mi.remove_meta(META_SHELLS)
	if mi.has_meta(META_SOURCE):
		var src: Mesh = mi.get_meta(META_SOURCE)
		var mats := []
		for i in mi.get_surface_override_material_count():
			mats.append(mi.get_surface_override_material(i))
		mi.mesh = src
		for i in min(mats.size(), mi.get_surface_override_material_count()):
			mi.set_surface_override_material(i, mats[i])
		mi.remove_meta(META_SOURCE)


## Distance level of detail. Call it with the camera's position once a frame (or not at all: every
## shell is drawn). It never hides a shell outright - a dropped shell fades over FADE_M - and the
## outermost shell is first in the file's order, so the fur's length and outline never change.
static func lod(root: Node, camera_pos: Vector3) -> void:
	for e in find_furred(root):
		var mi: MeshInstance3D = e["mesh"]
		if not mi.has_meta(META_SHELLS):
			continue
		var shells: Array = mi.get_meta(META_SHELLS)
		var d := mi.global_position.distance_to(camera_pos)
		var want := _want(shells.size(), d)
		for i in range(1, shells.size()):
			var s: MeshInstance3D = shells[i]
			if not is_instance_valid(s):
				continue
			# shell i is whole while `want` is past it, and fades out over the next FADE_M of distance
			var f := clampf(want - float(i), 0.0, 1.0)
			(s.material_override as ShaderMaterial).set_shader_parameter("shell_fade", f)
			s.visible = f > 0.002


## How many strand shells a body at `d` metres deserves, as a continuous number so the last one fades.
static func _want(n: int, d: float) -> float:
	if n <= MIN_SHELLS:
		return float(n)
	var far := float(MIN_SHELLS)
	var t := clampf((d - NEAR_M) / maxf(FAR_M - NEAR_M, 0.001), 0.0, 1.0)
	# shells fall with the angle the fur covers, which falls as 1/d: half the distance, twice the layers
	return maxf(far, lerpf(float(n), far, t * t))


# ------------------------------------------------------------------ materials and textures

static var _shader: Shader = null


static func shader() -> Shader:
	if _shader != null:
		return _shader
	if ResourceLoader.exists(SHADER_PATH):
		_shader = load(SHADER_PATH)
	if _shader == null and FileAccess.file_exists(SHADER_PATH):
		_shader = Shader.new()
		_shader.code = FileAccess.get_file_as_string(SHADER_PATH)
	return _shader


static func _dir_of(root: Node, mi: Node) -> String:
	for n in [mi, root]:
		var p: Node = n
		while p != null:
			if p.scene_file_path != "":
				return p.scene_file_path.get_base_dir()
			p = p.get_parent()
	return ""


static func _tex(dir: String, name: String, problems: PackedStringArray) -> Texture2D:
	var path := dir.path_join(name)
	if not ResourceLoader.exists(path):
		problems.append("fur texture %s is not in the project - was it exported beside the glb?" % path)
		return null
	return load(path)


static func _material(spec: Dictionary, dir: String, problems: PackedStringArray) -> ShaderMaterial:
	var sh := shader()
	if sh == null:
		problems.append("fur shader %s is missing" % SHADER_PATH)
		return null
	var tex: Dictionary = spec.get("textures", {})
	var m := ShaderMaterial.new()
	m.shader = sh
	for key in [["colour", "fur_colour"], ["strands", "strands"]]:
		var t := _tex(dir, String(tex.get(key[0], "")), problems)
		if t == null:
			return null
		m.set_shader_parameter(key[1], t)
	m.set_shader_parameter("length_max_m", float(spec.get("length_max_m", 0.02)))
	m.set_shader_parameter("uv_scale", float(spec.get("uv_scale", 1.0)))
	m.set_shader_parameter("lay", float(spec.get("lay", 0.55)))
	m.set_shader_parameter("min_density", float(spec.get("min_density", 0.02)))
	m.set_shader_parameter("cover_density", float(spec.get("cover_density", 0.75)))
	return m


# ------------------------------------------------------------------ hiding the skin under the fur

## Body vertices the fur covers, matched by position (Godot's importer reorders and splits vertices,
## so the spec lists positions, as wardrobe's does), then their triangles dropped from the index
## buffer. The mesh as imported is kept on the node so `detach` restores it.
static func _hide(mi: MeshInstance3D, blk: Dictionary) -> Dictionary:
	var src: Mesh = mi.get_meta(META_SOURCE, mi.mesh)
	mi.set_meta(META_SOURCE, src)
	var m := _match_positions(src, blk)
	var hidden: Dictionary = m[0]
	var mats := []
	for i in mi.get_surface_override_material_count():
		mats.append(mi.get_surface_override_material(i))
	var r := _rebuild(mi, src, hidden)
	for i in min(mats.size(), mi.get_surface_override_material_count()):
		if mats[i] != null:
			mi.set_surface_override_material(i, mats[i])
	r["unmatched"] = m[1]
	return r


static func _match_positions(mesh: Mesh, blk: Dictionary) -> Array:
	var raw := Marshalls.base64_to_raw(String(blk.get("positions_f32", "")))
	var want := raw.to_float32_array()
	var tol := float(blk.get("tolerance_m", 0.0005))
	var cell := maxf(tol, 1e-5) * 2.0
	var grid := {}
	var base := 0
	for s in mesh.get_surface_count():
		var arrays := mesh.surface_get_arrays(s)
		var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		for i in verts.size():
			var v := verts[i]
			var key := Vector3i(int(floor(v.x / cell)), int(floor(v.y / cell)), int(floor(v.z / cell)))
			if not grid.has(key):
				grid[key] = PackedInt32Array()
			grid[key].append(base + i)
		base += verts.size()
	var positions := PackedVector3Array()
	positions.resize(base)
	base = 0
	for s in mesh.get_surface_count():
		var verts: PackedVector3Array = mesh.surface_get_arrays(s)[Mesh.ARRAY_VERTEX]
		for i in verts.size():
			positions[base + i] = verts[i]
		base += verts.size()
	var hidden := {}
	var unmatched := 0
	var n := want.size() / 3
	for k in n:
		var p := Vector3(want[k * 3], want[k * 3 + 1], want[k * 3 + 2])
		var c := Vector3i(int(floor(p.x / cell)), int(floor(p.y / cell)), int(floor(p.z / cell)))
		var got := false
		for dx in [-1, 0, 1]:
			for dy in [-1, 0, 1]:
				for dz in [-1, 0, 1]:
					var key := c + Vector3i(dx, dy, dz)
					if not grid.has(key):
						continue
					for idx in grid[key]:
						if positions[idx].distance_to(p) <= tol:
							hidden[idx] = true
							got = true
		if not got:
			unmatched += 1
	return [hidden, unmatched]


## `mi` gets `src` without the triangles whose three corners are all hidden, and without the coverage map
## it carried as a vertex colour. Only ARRAY_INDEX and ARRAY_COLOR change, so the skin, the weights and the
## blend shapes are the mesh's own. It runs even with nothing to hide, for the colour alone.
static func _rebuild(mi: MeshInstance3D, src: Mesh, hidden: Dictionary) -> Dictionary:
	var out := ArrayMesh.new()
	out.blend_shape_mode = src.blend_shape_mode if src is ArrayMesh else Mesh.BLEND_SHAPE_MODE_NORMALIZED
	if src is ArrayMesh:
		for i in (src as ArrayMesh).get_blend_shape_count():
			out.add_blend_shape((src as ArrayMesh).get_blend_shape_name(i))
	var base := 0
	var dropped := 0
	var total := 0
	for s in src.get_surface_count():
		var arrays := src.surface_get_arrays(s)
		var n: int = arrays[Mesh.ARRAY_VERTEX].size()
		var shapes := src.surface_get_blend_shape_arrays(s) if src is ArrayMesh else []
		var flags := 0
		if src.surface_get_format(s) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS:
			flags |= Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS
		var index: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null \
			else PackedInt32Array(range(n))
		# The coverage map rode in on COLOR_0, and the body's own materials must not see it: Godot's glTF
		# importer turns "albedo from vertex colour" on for every material on a mesh that has one, and the
		# hair cap, whose vertices carry no fur and so a colour of zero, went black. The shells have taken
		# their copy of the mesh by now; the body itself has no use for it.
		arrays[Mesh.ARRAY_COLOR] = null
		var kept := PackedInt32Array()
		kept.resize(index.size())
		var w := 0
		for t in range(0, index.size(), 3):
			total += 1
			var a := index[t]
			var b := index[t + 1]
			var c := index[t + 2]
			if hidden.has(a + base) and hidden.has(b + base) and hidden.has(c + base):
				dropped += 1
				continue
			kept[w] = a
			kept[w + 1] = b
			kept[w + 2] = c
			w += 3
		kept.resize(w)
		arrays[Mesh.ARRAY_INDEX] = kept
		if w > 0:
			out.add_surface_from_arrays(src.surface_get_primitive_type(s), arrays, shapes, {}, flags)
			out.surface_set_material(out.get_surface_count() - 1, src.surface_get_material(s))
		base += n
	mi.mesh = out
	return {"tris_hidden": dropped, "tris_total": total}
