extends RefCounted
## Helpers shared by the lookdev Godot scripts: finding the environment and
## lights a scene actually renders with, and setting properties from JSON.
##
## These scripts run from outside the project (`--script <absolute path>`), so
## nothing here may assume a `res://` location for itself.

const PHYSICAL_UNITS_SETTING := "rendering/lights_and_shadows/use_physical_light_units"


static func physical_units() -> bool:
	return bool(ProjectSettings.get_setting(PHYSICAL_UNITS_SETTING, false))


static func rendering_method() -> String:
	return str(ProjectSettings.get_setting("rendering/renderer/rendering_method", "forward_plus"))


## Emit one machine-readable line for bin/lookdev.mjs. Everything else Godot
## prints is treated as log noise, except engine errors, which the runner also
## scans for - Godot reports most failures without failing.
static func emit(kind: String, data: Dictionary = {}) -> void:
	var d := data.duplicate()
	d["type"] = kind
	print("LOOKDEV " + JSON.stringify(d))


static func fail(tree: SceneTree, message: String) -> void:
	emit("error", {"message": message})
	tree.quit(2)


## `-- --spec path` style user args into a dictionary. Flags without a value
## become true.
static func parse_user_args() -> Dictionary:
	var out := {}
	var args := OS.get_cmdline_user_args()
	var i := 0
	while i < args.size():
		var a: String = args[i]
		if a.begins_with("--"):
			var key := a.substr(2)
			if i + 1 < args.size() and not str(args[i + 1]).begins_with("--"):
				out[key] = args[i + 1]
				i += 2
				continue
			out[key] = true
		i += 1
	return out


static func load_json(path: String) -> Variant:
	var text := FileAccess.get_file_as_string(path)
	if text.is_empty():
		return null
	return JSON.parse_string(text)


static func find_all(root: Node, cls: String) -> Array[Node]:
	var found: Array[Node] = []
	_find_all(root, cls, found)
	return found


static func _find_all(node: Node, cls: String, found: Array[Node]) -> void:
	if node.is_class(cls):
		found.append(node)
	for child in node.get_children():
		_find_all(child, cls, found)


## The Environment that renders: a current camera's own environment wins over
## the WorldEnvironment's, as in the engine.
static func active_environment(root: Node, camera: Camera3D = null) -> Environment:
	if camera != null and camera.environment != null:
		return camera.environment
	for we in find_all(root, "WorldEnvironment"):
		if (we as WorldEnvironment).environment != null:
			return (we as WorldEnvironment).environment
	return null


static func first_sun(root: Node) -> DirectionalLight3D:
	var suns := find_all(root, "DirectionalLight3D")
	return null if suns.is_empty() else suns[0] as DirectionalLight3D


## Resolve a target spelled `@env`, `@sun`, `@camera`, `@world` or a node path
## relative to the scene root.
static func resolve_target(scene_root: Node, target: String, camera: Camera3D) -> Object:
	match target:
		"@env":
			return active_environment(scene_root, camera)
		"@sun":
			return first_sun(scene_root)
		"@camera":
			return camera
		"@world":
			var wes := find_all(scene_root, "WorldEnvironment")
			return null if wes.is_empty() else wes[0]
		".", "":
			return scene_root
	return scene_root.get_node_or_null(NodePath(target))


static func has_property(obj: Object, prop: String) -> bool:
	for p in obj.get_property_list():
		if p["name"] == prop:
			return true
	return false


## Set `target:property[:sub]` to a JSON value, converting it to the type the
## property already holds. Returns "" on success or a reason.
static func apply_set(scene_root: Node, camera: Camera3D, key: String, value: Variant) -> String:
	var colon := key.find(":")
	if colon < 0:
		return "expected target:property, got '%s'" % key
	var target := key.substr(0, colon)
	var prop := key.substr(colon + 1)
	var obj := resolve_target(scene_root, target, camera)
	if obj == null:
		return "target '%s' not found" % target
	var head := prop.split(":")[0]
	if not has_property(obj, head):
		return "%s has no property '%s'" % [obj.get_class(), head]
	var current: Variant = obj.get_indexed(NodePath(prop))
	var converted: Variant = convert_value(value, typeof(current))
	if converted == null and value != null:
		return "cannot convert %s to %s" % [JSON.stringify(value), type_string(typeof(current))]
	obj.set_indexed(NodePath(prop), converted)
	var after: Variant = obj.get_indexed(NodePath(prop))
	if typeof(converted) in [TYPE_FLOAT, TYPE_INT] and typeof(after) in [TYPE_FLOAT, TYPE_INT]:
		if not is_equal_approx(float(after), float(converted)):
			return "set but reads back %s (clamped, or hidden while physical light units are %s)" % [
				str(after), "on" if physical_units() else "off"]
	return ""


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
		TYPE_VECTOR2:
			if value is Array and value.size() == 2:
				return Vector2(value[0], value[1])
		TYPE_NIL, TYPE_OBJECT:
			if value is String and (value as String).begins_with("res://"):
				return load(value)
			return value
	return value


## Unit vector pointing from the scene toward the sun for a light whose -Z is
## its travel direction.
static func to_sun(light: Node3D) -> Vector3:
	return world_transform(light).basis.z.normalized()


## global_transform, but also for nodes in a scene that was instantiated and
## never added to the tree (lint, preset), where the engine returns identity.
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


static func elevation_azimuth(light: Node3D) -> Vector2:
	var d := to_sun(light)
	var elevation := rad_to_deg(asin(clampf(d.y, -1.0, 1.0)))
	var azimuth := rad_to_deg(atan2(d.x, -d.z))
	return Vector2(elevation, azimuth)


## Azimuth 0 puts the sun toward -Z (Godot's forward), 90 toward +X.
static func basis_from_elevation_azimuth(elevation_deg: float, azimuth_deg: float) -> Basis:
	var e := deg_to_rad(clampf(elevation_deg, -89.0, 89.0))
	var a := deg_to_rad(azimuth_deg)
	var toward_sun := Vector3(sin(a) * cos(e), sin(e), -cos(a) * cos(e))
	return Basis.looking_at(-toward_sun, Vector3.UP)


## Blackbody colour for a temperature in Kelvin (Tanner Helland's fit, ~1%
## error across 1000-40000 K). Needed because Light3D.light_temperature is
## ignored unless physical light units are on.
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


static func vec3_json(v: Vector3) -> Array:
	return [snappedf(v.x, 0.001), snappedf(v.y, 0.001), snappedf(v.z, 0.001)]
