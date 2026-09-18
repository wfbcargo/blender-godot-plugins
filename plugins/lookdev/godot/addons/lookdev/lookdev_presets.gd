extends RefCounted
## lookdev lighting presets at runtime: apply a named recipe from presets.json (shipped beside this
## file) to a WorldEnvironment and a sun - environment, sky, sun direction, colour and energy, and
## exposure - the same way the offline `lookdev.mjs preset` (godot/apply_preset.gd) writes it into a
## scene, because that script calls this one.
##
##     const LookdevPresets := preload("res://addons/lookdev/lookdev_presets.gd")
##     var rep := LookdevPresets.apply("overcast", $WorldEnvironment, $Sun, {"stage": "open"})
##     if not rep["ok"]: push_error(rep["problems"])
##
## Deliberately no class_name: lookdev's tools run from the plugin folder against a project that has
## its own copy of this addon, and a second script declaring the same class_name fails to parse
## ("hides a global script class"). Preload it by path.
##
## Recipes carry values for both light-unit modes; the project setting
## rendering/lights_and_shadows/use_physical_light_units decides which apply. With physical units off,
## Kelvin becomes a light colour (light_temperature is ignored then) and lux becomes a relative energy
## calibrated against an 18% grey probe.
##
## A recipe may say what it needs: `"needs": "interior"` (interior_daylight) opens exposure ~4.5 stops for
## light coming in through windows, and on an open stage it clips everything to white. `apply` refuses such
## a recipe when options.stage is "open" (unless options.force), and warns when the stage is not given.
## `sky_openness` measures a stage when the caller does not know it.

const PRESETS := preload("presets.json")
const PHYSICAL_UNITS_SETTING := "rendering/lights_and_shadows/use_physical_light_units"
## Where a sun that is not above the horizon yet is put (degrees; 0 is toward -Z, 90 toward +X).
const DEFAULT_AZIMUTH := 150.0


## Every recipe by name, from presets.json (or options.presets when a caller passes its own file's data).
static func all(source: Variant = null) -> Dictionary:
	var data: Variant = source if source is Dictionary else PRESETS.data
	if not data is Dictionary:
		return {}
	return (data as Dictionary).get("presets", {})


static func names(source: Variant = null) -> PackedStringArray:
	return PackedStringArray(all(source).keys())


## "" when the recipe works anywhere, else what it needs ("interior").
static func needs(preset_name: String, source: Variant = null) -> String:
	return str(all(source).get(preset_name, {}).get("needs", ""))


static func physical_units() -> bool:
	return bool(ProjectSettings.get_setting(PHYSICAL_UNITS_SETTING, false))


## Apply recipe `preset_name` to `we` (its Environment and, in physical mode, its camera attributes) and
## to `sun`. Returns {"ok", "preset", "kind", "needs", "stage", "physical", "changes", "warnings",
## "problems"}; nothing is changed when ok is false.
##
## options:
##   fresh         true (default): a new Environment, so nothing from the previous recipe survives
##                 (night's volumetric fog, golden hour's glow). false edits the Environment in place.
##   stage         "open" | "interior" | "" - where this is applied; see `needs`.
##   force         apply a recipe whose needs the stage does not meet (it is still reported as a warning).
##   elevation, azimuth, energy_scale   override the recipe's sun.
##   keep_sun_side true (default): a sun already above the horizon keeps its azimuth.
##   presets       the parsed presets file to read instead of the one beside this script.
static func apply(preset_name: String, we: WorldEnvironment, sun: DirectionalLight3D, options := {}) -> Dictionary:
	var src: Variant = options.get("presets", null)
	var recipes := all(src)
	var rep := {"ok": false, "preset": preset_name, "kind": "", "needs": "", "stage": str(options.get("stage", "")),
		"physical": physical_units(), "changes": PackedStringArray(), "warnings": PackedStringArray(),
		"problems": PackedStringArray()}
	if not recipes.has(preset_name):
		rep["problems"].append("unknown preset '%s' (known: %s)" % [preset_name, ", ".join(PackedStringArray(recipes.keys()))])
		return rep
	var p: Dictionary = recipes[preset_name]
	rep["kind"] = str(p.get("kind", "day"))
	rep["needs"] = str(p.get("needs", ""))
	if rep["needs"] != "":
		var stage: String = rep["stage"]
		if stage == "":
			rep["warnings"].append("%s needs an %s stage (%s); the stage was not given, so it is applied as asked" % [
				preset_name, rep["needs"], str(p.get("_needs", "it is calibrated for one"))])
		elif stage != rep["needs"]:
			var msg := "%s needs an %s stage and this is an %s one: %s" % [preset_name, rep["needs"], stage,
				str(p.get("_needs", "it is calibrated for one"))]
			if not options.get("force", false):
				rep["problems"].append(msg + " Refused (pass force to apply it anyway).")
				return rep
			rep["warnings"].append(msg + " Applied because forced.")
	if we == null:
		rep["problems"].append("no WorldEnvironment to apply to")
		return rep
	var physical: bool = rep["physical"]
	if options.get("fresh", true) or we.environment == null:
		we.environment = Environment.new()
		rep["changes"].append("new Environment")
	var env := we.environment
	_set_all(env, p.get("environment", {}), "environment", rep)
	_set_all(env, p.get("environment_physical" if physical else "environment_relative", {}),
		"environment_physical" if physical else "environment_relative", rep)
	_apply_sky(env, p.get("sky", {}), physical, options, rep)
	_apply_sun(sun, p.get("sun", {}), physical, options, rep)
	_apply_exposure(we, p, physical, rep)
	rep["ok"] = rep["problems"].is_empty()
	return rep


static func _set_all(obj: Object, props: Dictionary, label: String, rep: Dictionary) -> void:
	var done := PackedStringArray()
	for key in props:
		if str(key).begins_with("_"):
			continue
		if not has_property(obj, key):
			rep["warnings"].append("%s has no property '%s' (skipped)" % [obj.get_class(), key])
			continue
		obj.set(key, convert_value(props[key], typeof(obj.get(key))))
		done.append(str(key))
	if not done.is_empty():
		rep["changes"].append("%s: %s" % [label, ", ".join(done)])


static func _apply_sky(env: Environment, sky_def: Dictionary, physical: bool, options: Dictionary, rep: Dictionary) -> void:
	if sky_def.is_empty():
		return
	var type := str(sky_def.get("type", "physical"))
	var cls: String = {"physical": "PhysicalSkyMaterial", "procedural": "ProceduralSkyMaterial"}.get(type, "")
	if cls.is_empty():
		rep["warnings"].append("sky type '%s' unsupported; use physical or procedural" % type)
		return
	env.background_mode = Environment.BG_SKY
	if env.sky == null:
		env.sky = Sky.new()
	if env.sky.sky_material == null or env.sky.sky_material.get_class() != cls:
		# A PanoramaSkyMaterial (HDRI) is a deliberate choice; keep it, the recipe still sets the sun,
		# exposure and effects around it.
		if env.sky.sky_material is PanoramaSkyMaterial and not sky_def.get("replace_hdri", false):
			rep["changes"].append("kept existing HDRI sky")
			return
		env.sky.sky_material = ClassDB.instantiate(cls)
		rep["changes"].append("sky material -> %s" % cls)
	_set_all(env.sky.sky_material, sky_def.get("material", {}), cls, rep)
	var mode_key := "material_physical" if physical else "material_relative"
	_set_all(env.sky.sky_material, sky_def.get(mode_key, {}), "%s (%s)" % [cls, mode_key], rep)


static func _apply_sun(sun: DirectionalLight3D, sun_def: Dictionary, physical: bool, options: Dictionary, rep: Dictionary) -> void:
	if sun == null:
		if not sun_def.is_empty():
			rep["warnings"].append("the recipe has a sun but no DirectionalLight3D was given")
		return
	sun.visible = not sun_def.is_empty()
	if sun_def.is_empty():
		rep["changes"].append("sun hidden (the recipe has none)")
		return
	var azimuth := DEFAULT_AZIMUTH
	if options.get("keep_sun_side", true):
		# Keep the scene's composition: a sun that is up stays on the side it was on.
		var ea := elevation_azimuth(sun)
		if ea.x > 0.5:
			azimuth = ea.y
	if sun_def.has("azimuth"):
		azimuth = float(sun_def["azimuth"])
	if options.has("azimuth"):
		azimuth = float(options["azimuth"])
	var elevation := float(options.get("elevation", sun_def.get("elevation", 50.0)))
	var parent_basis := Basis.IDENTITY
	if sun.get_parent() is Node3D:
		parent_basis = world_transform(sun.get_parent() as Node3D).basis.orthonormalized()
	sun.basis = parent_basis.inverse() * basis_from_elevation_azimuth(elevation, azimuth)
	rep["changes"].append("sun elevation %.1f°, azimuth %.1f°" % [elevation, azimuth])
	var scale := float(options.get("energy_scale", 1.0))
	var kelvin := float(sun_def.get("kelvin", 6500.0))
	if physical:
		sun.light_color = Color.WHITE
		sun.light_temperature = kelvin
		sun.light_intensity_lux = float(sun_def.get("lux", 100000.0)) * scale
		rep["changes"].append("sun %d K, %s lux" % [int(kelvin), str(sun.light_intensity_lux)])
	else:
		sun.light_color = kelvin_to_color(kelvin)
		sun.light_energy = float(sun_def.get("energy", 1.0)) * scale
		rep["changes"].append("sun %d K -> colour %s, energy %.3f" % [int(kelvin), sun.light_color.to_html(false), sun.light_energy])
	_set_all(sun, sun_def.get("light", {}), "sun", rep)


static func _apply_exposure(we: WorldEnvironment, p: Dictionary, physical: bool, rep: Dictionary) -> void:
	if not physical:
		return
	var def: Dictionary = p.get("camera_physical", {})
	if def.is_empty():
		return
	var attrs := we.camera_attributes as CameraAttributesPhysical
	if attrs == null:
		attrs = CameraAttributesPhysical.new()
		we.camera_attributes = attrs
		rep["changes"].append("added CameraAttributesPhysical")
	_set_all(attrs, def, "camera attributes", rep)


# ------------------------------------------------------------------ stage

## Share of rays from `at` toward the sky (the zenith and a ring at 45 degrees) that leave every mesh
## under `root` without hitting a triangle: 1.0 on an open stage, near 0 in a closed room. Meshes are
## read as they are (no skinning), which is enough for walls and ceilings. Works on a scene that was
## instantiated and never added to the tree.
static func sky_openness(root: Node, at: Vector3, rays := 9) -> float:
	var dirs: Array[Vector3] = [Vector3.UP]
	for k in maxi(rays - 1, 0):
		var a := TAU * k / float(maxi(rays - 1, 1))
		dirs.append(Vector3(cos(a), 1.0, sin(a)).normalized())
	var meshes: Array = []
	var stack: Array[Node] = [root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		for c in n.get_children():
			stack.append(c)
		if n is MeshInstance3D and (n as MeshInstance3D).mesh != null and (n as MeshInstance3D).visible:
			var tm := (n as MeshInstance3D).mesh.generate_triangle_mesh()
			if tm != null:
				meshes.append([tm, world_transform(n as Node3D).affine_inverse()])
	var open := 0
	for d in dirs:
		var hit := false
		for pair in meshes:
			var inv: Transform3D = pair[1]
			var r: Dictionary = (pair[0] as TriangleMesh).intersect_ray(inv * at, (inv.basis * d).normalized())
			if not r.is_empty():
				hit = true
				break
		if not hit:
			open += 1
	return open / float(dirs.size())


# ------------------------------------------------------------------ helpers (as godot/common.gd)

static func has_property(obj: Object, prop: String) -> bool:
	for p in obj.get_property_list():
		if p["name"] == prop:
			return true
	return false


static func convert_value(value: Variant, type: int) -> Variant:
	if value is String and (value as String).contains("("):
		var parsed: Variant = str_to_var(value)
		if parsed != null:
			return parsed
	match type:
		TYPE_BOOL:
			return bool(value)
		TYPE_INT:
			return int(value)
		TYPE_FLOAT:
			return float(value)
		TYPE_STRING, TYPE_STRING_NAME:
			return str(value)
		TYPE_COLOR:
			if value is String:
				return Color.from_string(value, Color.MAGENTA)
			if value is Array and value.size() >= 3:
				return Color(value[0], value[1], value[2], value[3] if value.size() > 3 else 1.0)
		TYPE_VECTOR3:
			if value is Array and value.size() == 3:
				return Vector3(value[0], value[1], value[2])
	return value


## global_transform, also for a node in a scene that was instantiated and never added to the tree.
static func world_transform(node: Node3D) -> Transform3D:
	if node.is_inside_tree():
		return node.global_transform
	var xf := node.transform
	var p := node.get_parent()
	while p != null:
		if p is Node3D:
			xf = (p as Node3D).transform * xf
		p = p.get_parent()
	return xf


## (elevation, azimuth) in degrees of the direction toward the light (its -Z travels away from it).
static func elevation_azimuth(light: Node3D) -> Vector2:
	var d := world_transform(light).basis.z.normalized()
	return Vector2(rad_to_deg(asin(clampf(d.y, -1.0, 1.0))), rad_to_deg(atan2(d.x, -d.z)))


## Azimuth 0 puts the sun toward -Z (Godot's forward), 90 toward +X.
static func basis_from_elevation_azimuth(elevation_deg: float, azimuth_deg: float) -> Basis:
	var e := deg_to_rad(clampf(elevation_deg, -89.0, 89.0))
	var a := deg_to_rad(azimuth_deg)
	var toward_sun := Vector3(sin(a) * cos(e), sin(e), -cos(a) * cos(e))
	return Basis.looking_at(-toward_sun, Vector3.UP)


## Blackbody colour for a temperature in Kelvin (Tanner Helland's fit, ~1% error across 1000-40000 K).
## Needed because Light3D.light_temperature is ignored unless physical light units are on.
static func kelvin_to_color(kelvin: float) -> Color:
	var t := clampf(kelvin, 1000.0, 40000.0) / 100.0
	var r: float
	var g: float
	var b: float
	if t <= 66.0:
		r = 255.0
		g = 99.4708025861 * log(t) - 161.1195681661
	else:
		r = 329.698727446 * pow(t - 60.0, -0.1332047592)
		g = 288.1221695283 * pow(t - 60.0, -0.0755148492)
	if t >= 66.0:
		b = 255.0
	elif t <= 19.0:
		b = 0.0
	else:
		b = 138.5177312231 * log(t - 10.0) - 305.0447927307
	return Color(clampf(r, 0, 255) / 255.0, clampf(g, 0, 255) / 255.0, clampf(b, 0, 255) / 255.0)
