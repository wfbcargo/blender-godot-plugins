class_name LookdevMaterials
extends RefCounted
## Puts back what glTF dropped from a lookdev material preset (presets/materials.json).
##
## Blender writes a material's `lookdev` custom property as glTF material extras; Godot's importer keeps
## them as the material's `extras` metadata. For the hair preset that is anisotropy, backlight, rim,
## alpha-to-coverage and the specular level - StandardMaterial3D properties the glTF importer never sets.
##
##     var scene = load("res://assets/belle/belle.glb").instantiate()
##     LookdevMaterials.apply(scene)     # before or after add_child; returns what it changed
##
## Materials are shared resources of the imported scene, so applying once changes every instance; a
## material already applied is skipped.
##
## A preset can also ask for its surfaces' tangents to be rebuilt (`lookdev.mesh.tangents = "per_face"`).
## The hair preset does: a glb written without tangents gets Godot's, generated per shared vertex, and
## where a hair shell's UV handedness changes (round an ear, where V runs away from the hairline on both
## sides) the corners disagree, their sum collapses, and the anisotropic highlight turns into bright
## glint lines. Here each corner starts from its own triangle's tangent and averages the triangles meeting
## at its position mod 180 degrees, which keeps that turn and still leaves the field smooth. Done once per
## mesh resource.
##
## A preset can also carry a tiling detail normal (`lookdev.detail`): humanform's skin asks for pores this way,
## because pores (0.05-0.2 mm) are finer than any texel a body-sized map can spend. The texture is made here from
## a seeded cellular noise (so every run draws the same pores) and tiles on UV2, which humanform writes as a copy
## of the body's UV map (`hf_detail`); a mesh without UV2 gets it triplanar instead.


## Every StandardMaterial3D under `root` (surface and override materials) whose extras carry
## `lookdev.godot` gets those properties, and surfaces whose preset asks for it get per-face tangents.
## Returns {"materials": [names], "skipped": n, "tangents_per_face": [mesh names]}.
static func apply(root: Node) -> Dictionary:
	var done := []
	var retangented := []
	var skipped := 0
	var stack: Array[Node] = [root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		for c in n.get_children():
			stack.append(c)
		if not n is MeshInstance3D:
			continue
		var mi := n as MeshInstance3D
		if mi.mesh == null:
			continue
		var rebuild := []
		for i in mi.mesh.get_surface_count():
			for mat in [mi.mesh.surface_get_material(i), mi.get_surface_override_material(i)]:
				if mat == null or not mat is StandardMaterial3D:
					continue
				var spec := preset_of(mat)
				if spec.is_empty():
					continue
				var mesh_spec = spec.get("mesh", {})
				if typeof(mesh_spec) == TYPE_DICTIONARY and mesh_spec.get("tangents", "") == "per_face" 						and not i in rebuild:
					rebuild.append(i)
				if mat.has_meta("lookdev_applied"):
					skipped += 1
					continue
				set_properties(mat, spec.get("godot", {}))
				var detail = spec.get("detail", {})
				if typeof(detail) == TYPE_DICTIONARY and not detail.is_empty():
					var has_uv2: bool = mi.mesh.surface_get_format(i) & Mesh.ARRAY_FORMAT_TEX_UV2 != 0
					set_detail(mat, detail, has_uv2)
				mat.set_meta("lookdev_applied", spec.get("preset", ""))
				done.append(mat.resource_name)
		if not rebuild.is_empty() and mi.mesh is ArrayMesh and not mi.mesh.has_meta("lookdev_tangents"):
			if tangents_per_face(mi.mesh, rebuild):
				retangented.append(mi.mesh.resource_name if mi.mesh.resource_name != "" else String(mi.name))
	return {"materials": done, "skipped": skipped, "tangents_per_face": retangented}


## Per-corner tangents of a de-indexed triangle list: each triangle's direction of increasing U in its
## plane (the strand texture's across-strand axis, which is all its normal map and the anisotropy use),
## made perpendicular to each corner's normal, with a +1 sign. V takes no part: a hair shell's V runs
## away from the hairline, and where it turns (round an ear, over the crown) Mikktspace's tangents
## follow it into patches.
##
## A triangle's own tangent alone is faceted where the U field turns fast - round the axis the strands
## run to (the bun), a face turns 60-80 degrees from the next, and each flat facet catches a different
## part of the anisotropic highlight, which draws dark polygons in the sheen. So each corner averages
## the tangents of every face meeting at its position, each flipped (mod 180 degrees) onto this face's
## own first: a turn of the frame round a hole no longer cancels, while over the cap the field is
## smooth again. Where that sum collapses (the axis itself, where every direction meets) the face's own
## tangent stands.
static func strand_tangents(arrays: Array) -> PackedFloat32Array:
	var pos: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var nrm: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	var tris := pos.size() / 3
	var face_t := PackedVector3Array()
	face_t.resize(tris)
	var at_pos := {}                                     # position (0.1 mm) -> faces meeting there
	for f in tris:
		var i := f * 3
		var p0 := pos[i]
		var e1 := pos[i + 1] - p0
		var e2 := pos[i + 2] - p0
		var fn := e1.cross(e2)
		var area2 := fn.length()
		var grad := Vector3.ZERO
		if area2 > 1e-12:
			fn /= area2
			# gradient of U over the triangle: sum of U differences times the edge normals in its plane
			grad = ((uv[i + 1].x - uv[i].x) * fn.cross(-e2) + (uv[i + 2].x - uv[i].x) * fn.cross(e1)) / area2
		if grad.length_squared() < 1e-20:
			var n0 := nrm[i]
			grad = n0.cross(Vector3.UP if absf(n0.y) < 0.9 else Vector3.RIGHT)
		face_t[f] = grad.normalized()
		for c in 3:
			var key := Vector3i((pos[i + c] * 10000.0).round())
			if not at_pos.has(key):
				at_pos[key] = []
			at_pos[key].append(f)
	var out := PackedFloat32Array()
	out.resize(pos.size() * 4)
	for f in tris:
		var i := f * 3
		var mine := face_t[f]
		for c in 3:
			var acc := Vector3.ZERO
			var share: Array = at_pos[Vector3i((pos[i + c] * 10000.0).round())]
			for g in share:
				var tg := face_t[g]
				acc += tg if tg.dot(mine) >= 0.0 else -tg
			if acc.length_squared() < 0.25 * share.size() * share.size():
				acc = mine                               # the faces meeting here point every way
			var n := nrm[i + c]
			var tv := acc - n * acc.dot(n)
			if tv.length_squared() < 1e-20:
				tv = n.cross(Vector3.UP if absf(n.y) < 0.9 else Vector3.RIGHT)
			tv = tv.normalized()
			out[(i + c) * 4] = tv.x
			out[(i + c) * 4 + 1] = tv.y
			out[(i + c) * 4 + 2] = tv.z
			out[(i + c) * 4 + 3] = 1.0
	return out


## Rebuilds the listed surfaces of `mesh` with one vertex per triangle corner and `strand_tangents` on
## that, keeping every other surface, the blend shapes, skin weights and materials. In place, so every
## instance sharing the mesh gets it. Returns whether it rebuilt anything.
##
## A mesh it cannot retangent it does not touch at all. Blend shapes are the case: the rebuild is a
## de-index, and a blend shape's arrays are indexed against the surface it belongs to, so a surface with
## shapes is left as it is. Before, the teardown ran anyway - every surface was round-tripped through
## `surface_get_arrays` (which loses the LOD and shadow-mesh data the format flags do not carry), no
## tangents were built, and the mesh was still stamped `lookdev_tangents`, so a later correct pass was
## skipped. character-pipeline bakes shape keys away before export, but this is lookdev's public entry
## point and any mesh can arrive at it.
static func tangents_per_face(mesh: ArrayMesh, surfaces: Array) -> bool:
	var count := mesh.get_surface_count()
	var rebuild := []
	if mesh.get_blend_shape_count() == 0:
		for i in surfaces:
			if i is int and i >= 0 and i < count and mesh.surface_get_primitive_type(i) == Mesh.PRIMITIVE_TRIANGLES:
				rebuild.append(i)
	if rebuild.is_empty():
		return false
	var saved := []
	for i in count:
		var arrays := mesh.surface_get_arrays(i)
		var format := mesh.surface_get_format(i)
		if i in rebuild:
			var st := SurfaceTool.new()
			st.create_from_arrays(arrays, Mesh.PRIMITIVE_TRIANGLES)
			st.deindex()
			arrays = st.commit_to_arrays()
			arrays[Mesh.ARRAY_TANGENT] = strand_tangents(arrays)
			format |= Mesh.ARRAY_FORMAT_TANGENT
			format &= ~Mesh.ARRAY_FORMAT_INDEX
		saved.append({"arrays": arrays, "format": format, "primitive": mesh.surface_get_primitive_type(i),
			"blend": mesh.surface_get_blend_shape_arrays(i), "material": mesh.surface_get_material(i),
			"name": mesh.surface_get_name(i)})
	mesh.clear_surfaces()
	for s in saved:
		# only the compression and skinning flags carry over; the array flags follow the arrays given
		var flags: int = s["format"] & ~(Mesh.ARRAY_FORMAT_VERTEX | Mesh.ARRAY_FORMAT_NORMAL
			| Mesh.ARRAY_FORMAT_TANGENT | Mesh.ARRAY_FORMAT_COLOR | Mesh.ARRAY_FORMAT_TEX_UV
			| Mesh.ARRAY_FORMAT_TEX_UV2 | Mesh.ARRAY_FORMAT_BONES | Mesh.ARRAY_FORMAT_WEIGHTS
			| Mesh.ARRAY_FORMAT_INDEX)
		mesh.add_surface_from_arrays(s["primitive"], s["arrays"], s["blend"], {}, flags)
		var k := mesh.get_surface_count() - 1
		mesh.surface_set_material(k, s["material"])
		mesh.surface_set_name(k, s["name"])
	mesh.set_meta("lookdev_tangents", "per_face")
	return true


static func preset_of(mat: Material) -> Dictionary:
	if not mat.has_meta("extras"):
		return {}
	var extras = mat.get_meta("extras")
	if typeof(extras) != TYPE_DICTIONARY or not extras.has("lookdev"):
		return {}
	var spec = extras["lookdev"]
	return spec if typeof(spec) == TYPE_DICTIONARY else {}


## JSON values onto a material: arrays of 3 or 4 numbers become Colors, numbers go to int properties
## as ints. Unknown properties are reported, not silently ignored.
static func set_properties(mat: Material, props: Dictionary) -> void:
	var known := {}
	for p in mat.get_property_list():
		known[p["name"]] = p["type"]
	for key in props:
		if not known.has(key):
			push_warning("lookdev: %s has no property %s" % [mat.resource_name, key])
			continue
		var value = props[key]
		match known[key]:
			TYPE_COLOR:
				var a: Array = value
				value = Color(a[0], a[1], a[2], a[3] if a.size() > 3 else 1.0)
			TYPE_INT:
				value = int(value)
			TYPE_FLOAT:
				value = float(value)
			TYPE_BOOL:
				value = bool(value)
		mat.set(key, value)


static var _detail_cache := {}


## A seamless pore normal map: cellular noise (distance to the nearest cell centre, so every cell centre is a
## pit) turned into a tangent-space normal map. Cached per spec, so every skin material with the same detail
## shares one texture.
static func detail_normal(d: Dictionary) -> Texture2D:
	var key := JSON.stringify(d)
	if _detail_cache.has(key):
		return _detail_cache[key]
	var px := int(d.get("tile_px", 256))
	var noise := FastNoiseLite.new()
	noise.noise_type = FastNoiseLite.TYPE_CELLULAR
	noise.seed = int(d.get("seed", 0))
	noise.frequency = float(d.get("cells", 48)) / float(px)
	noise.fractal_type = FastNoiseLite.FRACTAL_NONE
	noise.cellular_return_type = FastNoiseLite.RETURN_DISTANCE
	var img := noise.get_seamless_image(px, px, false, false, 0.1, true)
	img.convert(Image.FORMAT_RGBA8)
	img.bump_map_to_normal_map(float(d.get("bump", 3.0)))
	img.generate_mipmaps()
	var tex := ImageTexture.create_from_image(img)
	_detail_cache[key] = tex
	return tex


## The detail layer on `mat`: the pore normal, mixed into the material's own normal map at `strength` (Godot
## mixes detail normals by the detail albedo's alpha, so a white detail albedo with that alpha, multiplied in,
## leaves the colour alone), tiled `uv2_scale` times across UV2.
static func set_detail(mat: BaseMaterial3D, d: Dictionary, has_uv2 := true) -> void:
	if str(d.get("normal", "")) != "pores":
		push_warning("lookdev: %s asks for detail '%s', which this addon does not make" % [mat.resource_name, d.get("normal")])
		return
	var a := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	a.fill(Color(1, 1, 1, clampf(float(d.get("strength", 0.35)), 0.0, 1.0)))
	mat.detail_enabled = true
	mat.detail_blend_mode = BaseMaterial3D.BLEND_MODE_MUL
	mat.detail_uv_layer = BaseMaterial3D.DETAIL_UV_2
	mat.detail_albedo = ImageTexture.create_from_image(a)
	mat.detail_normal = detail_normal(d)
	mat.normal_enabled = true
	var s := float(d.get("uv2_scale", 80.0))
	if has_uv2:
		mat.uv2_scale = Vector3(s, s, 1.0)
	else:
		# about the same pore size on a body: UV1 spans roughly 1.5 m, so s tiles per 1.5 m of surface
		mat.uv2_triplanar = true
		mat.uv2_scale = Vector3.ONE * (s / 1.5)
