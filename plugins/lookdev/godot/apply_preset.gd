extends SceneTree
## lookdev preset: apply a named lighting recipe (addons/lookdev/presets.json) to a scene's sun, sky,
## environment and exposure, and save the result.
##
##   godot --headless --path <project> --script <this> -- --scene res://x.tscn \
##         --out <path.tscn> --preset golden_hour [--presets <presets.json>] \
##         [--elevation deg] [--azimuth deg] [--energy-scale k] [--stage open|interior] [--force]
##
## The recipe itself is applied by addons/lookdev/lookdev_presets.gd, the runtime applier a game uses
## (figure_study.gd does), so a scene written here and a scene lit at runtime get the same values. This
## script only finds or adds the WorldEnvironment and the sun, owns them in the saved scene, and decides
## the stage: a recipe that needs an interior (interior_daylight) is refused on an open stage - one where
## most rays up from the camera (or the middle of the scene) reach the sky - unless --force.

const Common := preload("common.gd")
const Presets := preload("addons/lookdev/lookdev_presets.gd")

var scene_root: Node


func _initialize() -> void:
	var args := Common.parse_user_args()
	var source: Variant = null
	if args.has("presets"):
		source = Common.load_json(str(args["presets"]))
		if not source is Dictionary:
			Common.fail(self, "cannot read presets file '%s'" % str(args["presets"]))
			return
	var name := str(args.get("preset", ""))
	if not Presets.all(source).has(name):
		Common.fail(self, "unknown preset '%s' (known: %s)" % [name, ", ".join(Presets.names(source))])
		return
	var scene_path := str(args.get("scene", ""))
	var out_path := str(args.get("out", ""))
	var packed := load(scene_path) as PackedScene
	if packed == null:
		Common.fail(self, "cannot load scene '%s'" % scene_path)
		return
	# GEN_EDIT_STATE_MAIN keeps instanced sub-scenes (imported .glb and so on)
	# as instances when repacked, rather than baking their contents in.
	scene_root = packed.instantiate(PackedScene.GEN_EDIT_STATE_MAIN)

	var stage := str(args.get("stage", ""))
	var openness := -1.0
	if stage == "" and Presets.needs(name, source) != "":
		openness = Presets.sky_openness(scene_root, _stage_point())
		stage = "open" if openness > 0.5 else "interior"
		Common.emit("change", {"what": "stage measured: %s (%.0f%% of rays up reach the sky)" % [stage, 100.0 * openness]})

	var we := _world_environment()
	var sun := Common.first_sun(scene_root)
	var had_sun := sun != null
	if sun == null:
		sun = DirectionalLight3D.new()
		sun.name = "Sun"
		own(sun, scene_root)       # before applying, so the sun's direction accounts for its parent
	var options := {"fresh": false, "stage": stage, "force": args.has("force")}
	if source != null:
		options["presets"] = source
	for k in ["elevation", "azimuth"]:
		if args.has(k):
			options[k] = float(args[k])
	if args.has("energy-scale"):
		options["energy_scale"] = float(args["energy-scale"])
	var rep := Presets.apply(name, we, sun, options)
	for w in rep["warnings"]:
		Common.emit("warning", {"message": w})
	if not rep["ok"]:
		Common.fail(self, "; ".join(rep["problems"]))
		scene_root.free()
		return
	if not had_sun:
		change("added DirectionalLight3D 'Sun'")
	for c in rep["changes"]:
		change(c)
	var want_q: int = int(Presets.all().get(name, {}).get("sun", {}).get("soft_shadow_filter_quality", -1))
	var have_q: int = int(ProjectSettings.get_setting("rendering/lights_and_shadows/directional_shadow/soft_shadow_filter_quality", 2))
	if want_q >= 0 and have_q < want_q:
		Common.emit("warning", {"message": "a scene cannot carry the soft shadow filter quality: set project setting rendering/lights_and_shadows/directional_shadow/soft_shadow_filter_quality to %d (it is %d), or call LookdevPresets.apply at runtime - below it a 0.5 deg sun stipples shadowed skin" % [want_q, have_q]})
	if rep["physical"]:
		for cam in Common.find_all(scene_root, "Camera3D"):
			if (cam as Camera3D).attributes != null:
				Common.emit("warning", {"message": "%s has its own CameraAttributes, which override the WorldEnvironment's exposure" % scene_root.get_path_to(cam)})
	else:
		for cam in Common.find_all(scene_root, "Camera3D"):
			if (cam as Camera3D).attributes != null:
				Common.emit("warning", {"message": "%s has its own CameraAttributes; tonemap_exposure still applies on top" % scene_root.get_path_to(cam)})

	var out := PackedScene.new()
	var err := out.pack(scene_root)
	if err != OK:
		Common.fail(self, "pack failed: %s" % error_string(err))
		return
	err = ResourceSaver.save(out, out_path)
	if err != OK:
		Common.fail(self, "save to '%s' failed: %s" % [out_path, error_string(err)])
		return
	Common.emit("done", {"out": out_path, "kind": rep["kind"], "needs": rep["needs"], "stage": stage,
		"sky_openness": openness, "physical_light_units": rep["physical"]})
	scene_root.free()
	quit(0)


func change(what: String) -> void:
	Common.emit("change", {"what": what})


func own(node: Node, parent: Node) -> void:
	parent.add_child(node)
	node.owner = scene_root


## Where the stage is judged from: the first camera, else 1.6 m above the bottom of the middle of the
## scene's meshes.
func _stage_point() -> Vector3:
	var cams := Common.find_all(scene_root, "Camera3D")
	if not cams.is_empty():
		return Common.world_transform(cams[0] as Node3D).origin
	var box := AABB()
	var first := true
	for mi in Common.find_all(scene_root, "MeshInstance3D"):
		if (mi as MeshInstance3D).mesh == null:
			continue
		var b := Common.world_transform(mi as Node3D) * (mi as MeshInstance3D).get_aabb()
		box = b if first else box.merge(b)
		first = false
	if first:
		return Vector3(0.0, 1.6, 0.0)
	return Vector3(box.get_center().x, box.position.y + minf(1.6, box.size.y * 0.5), box.get_center().z)


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
