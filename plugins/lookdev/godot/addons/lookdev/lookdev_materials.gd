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


## Every StandardMaterial3D under `root` (surface and override materials) whose extras carry
## `lookdev.godot` gets those properties. Returns {"materials": [names], "skipped": n}.
static func apply(root: Node) -> Dictionary:
	var done := []
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
		for i in mi.mesh.get_surface_count():
			for mat in [mi.mesh.surface_get_material(i), mi.get_surface_override_material(i)]:
				if mat == null or not mat is StandardMaterial3D:
					continue
				if mat.has_meta("lookdev_applied"):
					skipped += 1
					continue
				var spec := preset_of(mat)
				if spec.is_empty():
					continue
				set_properties(mat, spec.get("godot", {}))
				mat.set_meta("lookdev_applied", spec.get("preset", ""))
				done.append(mat.resource_name)
	return {"materials": done, "skipped": skipped}


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
