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
## glint lines. Per face, each corner keeps its own tangent. Done once per mesh resource.


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
				mat.set_meta("lookdev_applied", spec.get("preset", ""))
				done.append(mat.resource_name)
		if not rebuild.is_empty() and mi.mesh is ArrayMesh and not mi.mesh.has_meta("lookdev_tangents"):
			tangents_per_face(mi.mesh, rebuild)
			retangented.append(mi.mesh.resource_name if mi.mesh.resource_name != "" else String(mi.name))
	return {"materials": done, "skipped": skipped, "tangents_per_face": retangented}


## Per-corner tangents of a de-indexed triangle list: each triangle's direction of increasing U in its
## plane (the strand texture's across-strand axis, which is all its normal map and the anisotropy use),
## made perpendicular to each corner's normal, with a +1 sign. V takes no part: a hair shell's V runs
## away from the hairline, and where it turns (round an ear, over the crown) Mikktspace's tangents
## follow it into patches.
static func strand_tangents(arrays: Array) -> PackedFloat32Array:
	var pos: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var nrm: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	var out := PackedFloat32Array()
	out.resize(pos.size() * 4)
	for i in range(0, pos.size() - 2, 3):
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
		for c in 3:
			var n := nrm[i + c]
			var tv := grad - n * grad.dot(n)
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
## instance sharing the mesh gets it.
static func tangents_per_face(mesh: ArrayMesh, surfaces: Array) -> void:
	var count := mesh.get_surface_count()
	var saved := []
	for i in count:
		var arrays := mesh.surface_get_arrays(i)
		var format := mesh.surface_get_format(i)
		if i in surfaces and mesh.get_blend_shape_count() == 0 				and mesh.surface_get_primitive_type(i) == Mesh.PRIMITIVE_TRIANGLES:
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
