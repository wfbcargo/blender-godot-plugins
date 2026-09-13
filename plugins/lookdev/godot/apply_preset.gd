extends SceneTree
## lookdev preset: apply a named lighting recipe (presets/presets.json) to a
## scene's sun, sky, environment and exposure, and save the result.
##
##   godot --headless --path <project> --script <this> -- --scene res://x.tscn \
##         --out <path.tscn> --preset golden_hour --presets <presets.json> \
##         [--elevation deg] [--azimuth deg] [--energy-scale k]
##
## Recipes carry values for both light-unit modes, and the project setting
## decides which apply: with physical units off, temperatures become light
## colours (light_temperature is ignored then) and lux/nits become relative
## energies calibrated against an 18% grey probe.

const Common := preload("common.gd")

var scene_root: Node
var physical := false


func _initialize() -> void:
	var args := Common.parse_user_args()
	var presets: Variant = Common.load_json(str(args.get("presets", "")))
	if not presets is Dictionary:
		Common.fail(self, "cannot read presets file")
		return
	var name := str(args.get("preset", ""))
	if not presets["presets"].has(name):
		Common.fail(self, "unknown preset '%s' (known: %s)" % [name, ", ".join(presets["presets"].keys())])
		return
	var preset: Dictionary = presets["presets"][name]
	var scene_path := str(args.get("scene", ""))
	var out_path := str(args.get("out", ""))
	var packed := load(scene_path) as PackedScene
	if packed == null:
		Common.fail(self, "cannot load scene '%s'" % scene_path)
		return
	# GEN_EDIT_STATE_MAIN keeps instanced sub-scenes (imported .glb and so on)
	# as instances when repacked, rather than baking their contents in.
	scene_root = packed.instantiate(PackedScene.GEN_EDIT_STATE_MAIN)
	physical = Common.physical_units()

	var we := _world_environment()
	var env := we.environment
	_apply_environment(env, preset)
	_apply_sky(env, preset.get("sky", {}))
	_apply_sun(preset.get("sun", {}), args)
	_apply_exposure(we, preset)

	var out := PackedScene.new()
	var err := out.pack(scene_root)
	if err != OK:
		Common.fail(self, "pack failed: %s" % error_string(err))
		return
	err = ResourceSaver.save(out, out_path)
	if err != OK:
		Common.fail(self, "save to '%s' failed: %s" % [out_path, error_string(err)])
		return
	Common.emit("done", {"out": out_path, "kind": preset.get("kind", "day"), "physical_light_units": physical})
	scene_root.free()
	quit(0)


func change(what: String) -> void:
	Common.emit("change", {"what": what})


func own(node: Node, parent: Node) -> void:
	parent.add_child(node)
	node.owner = scene_root


func _world_environment() -> WorldEnvironment:
	var wes := Common.find_all(scene_root, "WorldEnvironment")
	var we: WorldEnvironment
	if wes.is_empty():
		we = WorldEnvironment.new()
		we.name = "WorldEnvironment"
		own(we, scene_root)
		change("added WorldEnvironment")
	else:
		we = wes[0]
	if we.environment == null:
		we.environment = Environment.new()
		change("added Environment")
	elif not we.environment.resource_path.is_empty() and not we.environment.resource_path.contains("::"):
		# An external .tres would be referenced, not saved, and the edits lost -
		# and editing it in place would change every scene sharing it.
		change("copied shared %s into the scene (the original file is untouched)" % we.environment.resource_path)
		we.environment = we.environment.duplicate(true)
	return we


func _set_all(obj: Object, props: Dictionary, label: String) -> void:
	for key in props:
		if str(key).begins_with("_"):
			continue
		if not Common.has_property(obj, key):
			Common.emit("warning", {"message": "%s has no property '%s' (skipped)" % [obj.get_class(), key]})
			continue
		var value: Variant = Common.convert_value(props[key], typeof(obj.get(key)))
		obj.set(key, value)
	if not props.is_empty():
		change("%s: %s" % [label, ", ".join(props.keys().filter(func(k): return not str(k).begins_with("_")))])


func _apply_environment(env: Environment, preset: Dictionary) -> void:
	_set_all(env, preset.get("environment", {}), "environment")
	var mode_key := "environment_physical" if physical else "environment_relative"
	_set_all(env, preset.get(mode_key, {}), mode_key)


func _apply_sky(env: Environment, sky_def: Dictionary) -> void:
	if sky_def.is_empty():
		return
	var type := str(sky_def.get("type", "physical"))
	var cls: String = {"physical": "PhysicalSkyMaterial", "procedural": "ProceduralSkyMaterial"}.get(type, "")
	if cls.is_empty():
		Common.emit("warning", {"message": "sky type '%s' unsupported; use physical or procedural" % type})
		return
	env.background_mode = Environment.BG_SKY
	if env.sky == null:
		env.sky = Sky.new()
	if env.sky.sky_material == null or env.sky.sky_material.get_class() != cls:
		# A PanoramaSkyMaterial (HDRI) is a deliberate choice; keep it, the preset
		# still sets sun, exposure and effects around it.
		if env.sky.sky_material is PanoramaSkyMaterial and not sky_def.get("replace_hdri", false):
			change("kept existing HDRI sky")
			return
		env.sky.sky_material = ClassDB.instantiate(cls)
		change("sky material -> %s" % cls)
	_set_all(env.sky.sky_material, sky_def.get("material", {}), cls)
	var mode_key := "material_physical" if physical else "material_relative"
	_set_all(env.sky.sky_material, sky_def.get(mode_key, {}), cls + " (" + mode_key + ")")


func _apply_sun(sun_def: Dictionary, args: Dictionary) -> void:
	if sun_def.is_empty():
		return
	var sun := Common.first_sun(scene_root)
	var azimuth := 150.0
	if sun == null:
		sun = DirectionalLight3D.new()
		sun.name = "Sun"
		own(sun, scene_root)
		change("added DirectionalLight3D 'Sun'")
	else:
		# Keep the scene's composition: the sun stays on the side it was on.
		var ea := Common.elevation_azimuth(sun)
		if ea.x > 0.5:
			azimuth = ea.y
	if sun_def.has("azimuth"):
		azimuth = float(sun_def["azimuth"])
	if args.has("azimuth"):
		azimuth = float(args["azimuth"])
	var elevation := float(args.get("elevation", sun_def.get("elevation", 50.0)))
	var parent_basis := Basis.IDENTITY
	if sun.get_parent() is Node3D:
		parent_basis = Common.world_transform(sun.get_parent() as Node3D).basis.orthonormalized()
	sun.basis = parent_basis.inverse() * Common.basis_from_elevation_azimuth(elevation, azimuth)
	change("sun elevation %.1f°, azimuth %.1f°" % [elevation, azimuth])

	var scale := float(args.get("energy-scale", 1.0))
	var kelvin := float(sun_def.get("kelvin", 6500.0))
	if physical:
		sun.light_color = Color.WHITE
		sun.light_temperature = kelvin
		sun.light_intensity_lux = float(sun_def.get("lux", 100000.0)) * scale
		change("sun %d K, %s lux" % [int(kelvin), str(sun.light_intensity_lux)])
	else:
		sun.light_color = Common.kelvin_to_color(kelvin)
		sun.light_energy = float(sun_def.get("energy", 1.0)) * scale
		change("sun %d K -> colour %s, energy %.3f" % [int(kelvin), sun.light_color.to_html(false), sun.light_energy])
	_set_all(sun, sun_def.get("light", {}), "sun")


func _apply_exposure(we: WorldEnvironment, preset: Dictionary) -> void:
	if physical:
		var def: Dictionary = preset.get("camera_physical", {})
		if def.is_empty():
			return
		var attrs := we.camera_attributes as CameraAttributesPhysical
		if attrs == null:
			attrs = CameraAttributesPhysical.new()
			we.camera_attributes = attrs
			change("added CameraAttributesPhysical")
		_set_all(attrs, def, "camera attributes")
		for cam in Common.find_all(scene_root, "Camera3D"):
			if (cam as Camera3D).attributes != null:
				Common.emit("warning", {"message": "%s has its own CameraAttributes, which override the WorldEnvironment's exposure" % scene_root.get_path_to(cam)})
	else:
		for cam in Common.find_all(scene_root, "Camera3D"):
			if (cam as Camera3D).attributes != null:
				Common.emit("warning", {"message": "%s has its own CameraAttributes; tonemap_exposure still applies on top" % scene_root.get_path_to(cam)})
