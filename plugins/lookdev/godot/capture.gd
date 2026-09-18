extends SceneTree
## lookdev capture: render a scene from chosen cameras in one or more debug
## views, and write PNGs plus stats.json. Driven by bin/lookdev.mjs.
##
##   godot --path <project> --script <this> --resolution 1280x720 \
##         --fixed-fps 60 --position -20000,-20000 -- --spec <spec.json>
##
## It must run WITH a window. `--headless` only offers the dummy renderer, so
## every viewport texture comes back empty. The runner parks the window
## off-screen instead - and never minimized, because on Windows a minimized
## window skips drawing entirely and the capture would be a stale frame.
##
## The scene is never saved: `set` overrides exist so candidate lighting can be
## tried and compared without touching the user's files.

const Common := preload("common.gd")
const Stats := preload("stats.gd")

const VIEWS := {
	"lit": Viewport.DEBUG_DRAW_DISABLED,
	"unshaded": Viewport.DEBUG_DRAW_UNSHADED,
	"lighting": Viewport.DEBUG_DRAW_LIGHTING,
	"normal": Viewport.DEBUG_DRAW_NORMAL_BUFFER,
	"overdraw": Viewport.DEBUG_DRAW_OVERDRAW,
	"ssao": Viewport.DEBUG_DRAW_SSAO,
	"ssil": Viewport.DEBUG_DRAW_SSIL,
	"pssm": Viewport.DEBUG_DRAW_PSSM_SPLITS,
	"sdfgi": Viewport.DEBUG_DRAW_SDFGI,
	"sdfgi_probes": Viewport.DEBUG_DRAW_SDFGI_PROBES,
	"gi_buffer": Viewport.DEBUG_DRAW_GI_BUFFER,
	"voxel_gi_lighting": Viewport.DEBUG_DRAW_VOXEL_GI_LIGHTING,
	"luminance": Viewport.DEBUG_DRAW_SCENE_LUMINANCE,
}

const PROBE_RADIUS := 0.25

var spec: Dictionary
var out_dir: String
var scene_root: Node
var probe_gray: MeshInstance3D
var probe_chrome: MeshInstance3D
var current_shot := ""


func _initialize() -> void:
	_run()


func _run() -> void:
	var args := Common.parse_user_args()
	if not args.has("spec"):
		Common.fail(self, "no --spec given")
		return
	var parsed: Variant = Common.load_json(str(args["spec"]))
	if not parsed is Dictionary:
		Common.fail(self, "spec is not a JSON object: " + str(args["spec"]))
		return
	spec = parsed
	out_dir = str(spec.get("out_dir", ""))
	if out_dir.is_empty() or DirAccess.make_dir_recursive_absolute(out_dir) != OK:
		Common.fail(self, "cannot create out_dir '%s'" % out_dir)
		return
	# make_dir_recursive_absolute says OK for a folder that exists but cannot be written, and every
	# save_png after it then fails quietly: try a file first.
	var probe_file := out_dir.path_join(".lookdev_write_test")
	var pf := FileAccess.open(probe_file, FileAccess.WRITE)
	if pf == null:
		Common.fail(self, "cannot write into out_dir '%s': %s" % [out_dir, error_string(FileAccess.get_open_error())])
		return
	pf.close()
	DirAccess.remove_absolute(probe_file)

	var scene_path := str(spec.get("scene", ""))
	var packed := load(scene_path) as PackedScene
	if packed == null:
		Common.fail(self, "cannot load scene '%s'" % scene_path)
		return
	scene_root = packed.instantiate()
	root.add_child(scene_root)
	current_scene = scene_root

	var views: Array = spec.get("views", ["lit", "unshaded", "lighting"])
	for v in views:
		if not VIEWS.has(v):
			Common.fail(self, "unknown view '%s' (known: %s)" % [v, ", ".join(VIEWS.keys())])
			return

	# One frame so _ready has run and scene-created cameras exist.
	await process_frame
	var mats := _count_materials(scene_root)
	if mats == 0:
		Common.fail(self, "the scene has 0 materials after it ran (nothing to light or measure); capture refuses to report numbers for an empty frame")
		return

	var set_results := []
	var sets: Dictionary = spec.get("set", {})
	for key in sets:
		var err := Common.apply_set(scene_root, root.get_camera_3d(), key, sets[key])
		set_results.append({"key": key, "ok": err.is_empty(), "error": err})
		if not err.is_empty():
			Common.emit("warning", {"message": "set %s: %s" % [key, err]})

	if spec.get("probes", false):
		_make_probes()

	var warmup := int(spec.get("warmup_frames", 90))
	for i in warmup:
		await process_frame
	if spec.get("freeze", true):
		# Pausing stops scripts and animation so every view of a shot sees the
		# same geometry; rendering, TAA and GI keep converging regardless.
		paused = true

	var shots: Array = spec.get("shots", [{"name": "view"}])
	var shot_results := []
	for shot in shots:
		var res: Variant = await _capture_shot(shot, views)
		if res == null:
			return
		shot_results.append(res)

	var sheet := _contact_sheet(shot_results, views)

	var result := {
		"scene": scene_path,
		"sheet": sheet,
		"views": views,
		"resolution": [root.size.x, root.size.y],
		"physical_light_units": Common.physical_units(),
		"rendering_method": Common.rendering_method(),
		"environment": _environment_summary(),
		"set": set_results,
		"shots": shot_results,
	}
	var f := FileAccess.open(out_dir.path_join("stats.json"), FileAccess.WRITE)
	if f == null:
		Common.fail(self, "cannot write stats.json in '%s': %s" % [out_dir, error_string(FileAccess.get_open_error())])
		return
	f.store_string(JSON.stringify(result, "  ", false))
	f.close()
	Common.emit("done", {"stats": out_dir.path_join("stats.json")})
	quit(0)


func _capture_shot(shot: Dictionary, views: Array) -> Variant:
	var shot_name := str(shot.get("name", "view"))
	current_shot = shot_name
	var cam := _setup_camera(shot)
	if cam == null:
		Common.fail(self, "shot '%s': no camera. The scene has no current Camera3D - give the shot a 'camera' node path or an 'eye' and 'target'." % shot_name)
		return null
	if probe_gray != null:
		_place_probes(cam, shot)

	var settle := int(spec.get("view_frames", 20))
	var files := {}
	var stats := {}
	var images := {}
	for v in views:
		root.debug_draw = VIEWS[v]
		# The unshaded view still goes through exposure and the tonemapper, so
		# with tonemap_exposure 16 every albedo would read as white. Neutralise
		# them there, so the view shows the base colour actually authored.
		var saved := _push_env({"tonemap_mode": Environment.TONE_MAPPER_LINEAR, "tonemap_exposure": 1.0,
				"glow_enabled": false, "fog_enabled": false, "volumetric_fog_enabled": false,
				"adjustment_enabled": false}) if v == "unshaded" else {}
		for i in settle:
			await process_frame
		await RenderingServer.frame_post_draw
		_pop_env(saved)
		var img := root.get_texture().get_image()
		var path := out_dir.path_join("%s_%s.png" % [shot_name, v])
		var serr := img.save_png(path)
		if serr != OK:
			Common.fail(self, "cannot save '%s': %s" % [path, error_string(serr)])
			return null
		files[v] = path
		images[v] = img
	root.debug_draw = Viewport.DEBUG_DRAW_DISABLED

	var mask := PackedByteArray()
	if spec.get("mask_background", true):
		mask = await _background_mask(settle)

	for v in images:
		var small := Stats.reduce(images[v])
		match v:
			"lit":
				stats[v] = Stats.lit(small, mask)
			"unshaded":
				stats[v] = Stats.albedo(small, mask)
			"lighting":
				stats[v] = Stats.lighting(small, mask)

	var probe := {}
	if probe_gray != null:
		probe = _read_probes(cam, images)
		probe["key_fill"] = await _probe_key_fill(cam, settle)

	var eye := cam.global_position
	return {
		"name": shot_name,
		"camera": {
			"node": str(scene_root.get_path_to(cam)) if scene_root.is_ancestor_of(cam) else "(lookdev)",
			"eye": Common.vec3_json(eye),
			"forward": Common.vec3_json(-cam.global_basis.z),
			"fov": cam.fov,
		},
		"files": files,
		"stats": stats,
		"probes": probe,
	}


## Surface and override materials under `node` (the probes are added later and are not counted).
func _count_materials(node: Node) -> int:
	var n := 0
	if node is GeometryInstance3D and (node as GeometryInstance3D).material_override != null:
		n += 1
	if node is MeshInstance3D and (node as MeshInstance3D).mesh != null:
		var mi := node as MeshInstance3D
		for i in mi.mesh.get_surface_count():
			if mi.mesh.surface_get_material(i) != null or mi.get_surface_override_material(i) != null:
				n += 1
	elif node is CSGShape3D and node.get("material") != null:
		n += 1
	for c in node.get_children():
		n += _count_materials(c)
	return n


func _setup_camera(shot: Dictionary) -> Camera3D:
	if shot.has("camera"):
		var node := scene_root.get_node_or_null(NodePath(str(shot["camera"]))) as Camera3D
		if node == null:
			return null
		node.make_current()
		return node
	if shot.has("eye") and shot.has("target"):
		var cam := root.get_node_or_null("LookdevCamera") as Camera3D
		if cam == null:
			cam = Camera3D.new()
			cam.name = "LookdevCamera"
			cam.process_mode = Node.PROCESS_MODE_ALWAYS
			root.add_child(cam)
		var eye := _vec3(shot["eye"])
		var target := _vec3(shot["target"])
		var up := Vector3.UP
		if absf((target - eye).normalized().dot(up)) > 0.99:
			up = Vector3.FORWARD
		cam.look_at_from_position(eye, target, up)
		cam.fov = float(shot.get("fov", 50.0))
		cam.make_current()
		return cam
	return root.get_camera_3d()


func _vec3(a: Variant) -> Vector3:
	return Vector3(a[0], a[1], a[2])


## Reference spheres: an 18% grey diffuse ball and a chrome ball, the
## lighting-artist standard. The grey ball reads exposure and key/fill balance;
## the chrome ball shows what the scene reflects.
func _make_probes() -> void:
	var sphere := SphereMesh.new()
	sphere.radius = PROBE_RADIUS
	sphere.height = PROBE_RADIUS * 2.0
	var gray := StandardMaterial3D.new()
	# albedo_color is sRGB-encoded; 118/255 is 18% linear.
	gray.albedo_color = Color8(118, 118, 118)
	gray.roughness = 1.0
	gray.metallic_specular = 0.5
	var chrome := StandardMaterial3D.new()
	chrome.albedo_color = Color(0.95, 0.95, 0.95)
	chrome.metallic = 1.0
	chrome.roughness = 0.05
	probe_gray = MeshInstance3D.new()
	probe_gray.name = "LookdevGrayProbe"
	probe_gray.mesh = sphere
	probe_gray.material_override = gray
	probe_chrome = MeshInstance3D.new()
	probe_chrome.name = "LookdevChromeProbe"
	probe_chrome.mesh = sphere
	probe_chrome.material_override = chrome
	root.add_child(probe_gray)
	root.add_child(probe_chrome)


func _place_probes(cam: Camera3D, shot: Dictionary) -> void:
	var at: Vector3
	var right := cam.global_basis.x
	var p: Variant = spec.get("probes")
	if shot.has("probe_at"):
		at = _vec3(shot["probe_at"])
	elif p is Dictionary and p.has("at"):
		at = _vec3(p["at"])
	else:
		# Lower third, right of centre, close enough to read clearly.
		var fwd := -cam.global_basis.z
		var dist := float(p.get("distance", 3.0)) if p is Dictionary else 3.0
		at = cam.global_position + fwd * dist + right * dist * 0.28 - cam.global_basis.y * dist * 0.14
	probe_gray.global_position = at
	probe_chrome.global_position = at + right * PROBE_RADIUS * 2.6


func _read_probes(cam: Camera3D, images: Dictionary) -> Dictionary:
	var out := {}
	for pair in [["gray", probe_gray]]:
		var node: MeshInstance3D = pair[1]
		if cam.is_position_behind(node.global_position):
			out[pair[0]] = {"visible": false}
			continue
		var c := cam.unproject_position(node.global_position)
		var edge := cam.unproject_position(node.global_position + cam.global_basis.x * PROBE_RADIUS)
		var radius := c.distance_to(edge) * 0.45
		var entry := {"screen": [int(c.x), int(c.y)], "radius_px": snappedf(radius, 0.1)}
		if images.has("lit"):
			entry["lit"] = Stats.disk_mean(images["lit"], c, radius)
		if images.has("lighting"):
			entry["lighting"] = Stats.disk_mean(images["lighting"], c, radius)
		out[pair[0]] = entry
	return out


## Key-to-fill ratio, read off the grey probe.
##
## Frame statistics can't give this: a frame that is mostly one sunlit floor has
## no shade in it however flat the lighting is. So a second camera looks at the
## probe and reads two patches of it, chosen by surface normal:
##   key  - normals facing the sun
##   fill - normals 120 degrees from the sun, rotated over the top: facing away
##          from it and as far up as possible while no part of the sampled
##          patch can still catch grazing sun. What open shade sees: sky and
##          bounce only.
## A percentile over the whole ball would instead find its underside, which only
## ever sees the ground. The camera sits on the bisector of the two normals so
## both patches face it. The lighting-only view renders with linear tonemapping
## at 1/8 exposure - AgX would compress the very ratio being measured - so the
## values come back as linear light on an 18% grey surface, at exposure 1.
func _probe_key_fill(shot_cam: Camera3D, settle: int) -> Dictionary:
	const EXPOSURE_SCALE := 0.125
	const MATCH := 0.93
	var sun := Common.first_sun(scene_root)
	if sun == null or not sun.visible:
		return {"measured": false, "reason": "no visible DirectionalLight3D, so there is no key direction to measure against"}
	var at := probe_gray.global_position
	var key_n := Common.to_sun(sun)
	var horizontal := Vector3(key_n.x, 0.0, key_n.z)
	if horizontal.length() < 0.05:
		horizontal = shot_cam.global_basis.x
	# Rotate key_n 120 degrees in the vertical plane through the zenith.
	var axis := horizontal.normalized().cross(Vector3.UP).normalized()
	var fill_n := key_n.rotated(axis, deg_to_rad(120.0)).normalized()
	if fill_n.dot(Vector3.UP) < key_n.rotated(axis, deg_to_rad(-120.0)).dot(Vector3.UP):
		fill_n = key_n.rotated(axis, deg_to_rad(-120.0)).normalized()
	var view := (key_n + fill_n).normalized()

	var cam := Camera3D.new()
	cam.name = "LookdevProbeCamera"
	root.add_child(cam)
	var up := Vector3.UP if absf(view.dot(Vector3.UP)) < 0.98 else Vector3.FORWARD
	probe_chrome.visible = false
	cam.make_current()
	# In enclosed spaces the camera can land behind a wall. Flash the probe
	# magenta and unshaded, and step closer until the camera actually sees it.
	var seen := false
	for dist in [1.6, 1.0, 0.7, 0.5]:
		cam.look_at_from_position(at + view * dist, at, up)
		cam.fov = rad_to_deg(2.0 * atan(PROBE_RADIUS * 1.6 / dist))
		if await _probe_visible(cam, at):
			seen = true
			break
	if not seen:
		probe_chrome.visible = true
		cam.queue_free()
		shot_cam.make_current()
		return {"measured": false, "reason": "no clear line of sight to the probe from the key/fill angle (geometry in the way). Move it with 'probe_at' in a spec."}

	var env := Common.active_environment(scene_root, cam)
	var saved := _push_env({"tonemap_mode": Environment.TONE_MAPPER_LINEAR,
			"tonemap_exposure": (env.tonemap_exposure if env != null else 1.0) * EXPOSURE_SCALE,
			"glow_enabled": false, "fog_enabled": false, "volumetric_fog_enabled": false})
	root.debug_draw = Viewport.DEBUG_DRAW_LIGHTING
	for i in settle:
		await process_frame
	await RenderingServer.frame_post_draw
	var img := root.get_texture().get_image()
	img.convert(Image.FORMAT_RGBA8)
	root.debug_draw = Viewport.DEBUG_DRAW_DISABLED
	_pop_env(saved)
	probe_chrome.visible = true
	var path := out_dir.path_join("%s_probe_keyfill.png" % current_shot)
	img.save_png(path)

	var c := cam.unproject_position(at)
	var edge := cam.unproject_position(at + cam.global_basis.x * PROBE_RADIUS)
	var radius := c.distance_to(edge)
	var cam_basis := cam.global_basis
	cam.queue_free()
	shot_cam.make_current()

	var lut := Stats.lin_lut()
	var sums := [0.0, 0.0]
	var counts := [0, 0]
	var clipped := 0
	for yv in range(int(c.y - radius), int(c.y + radius) + 1):
		for xv in range(int(c.x - radius), int(c.x + radius) + 1):
			if xv < 0 or yv < 0 or xv >= img.get_width() or yv >= img.get_height():
				continue
			var nx := (xv - c.x) / radius
			var ny := -(yv - c.y) / radius
			var r2 := nx * nx + ny * ny
			if r2 > 0.9:
				continue
			# Orthographic approximation of the sphere normal; at 25 degrees FOV
			# and 1.6 m the perspective error is a few degrees.
			var n := (cam_basis * Vector3(nx, ny, sqrt(1.0 - r2))).normalized()
			var which := -1
			if n.dot(key_n) > MATCH:
				which = 0
			elif n.dot(fill_n) > MATCH:
				which = 1
			if which < 0:
				continue
			var px := img.get_pixel(xv, yv)
			if maxi(px.r8, maxi(px.g8, px.b8)) >= 254:
				clipped += 1
			sums[which] += (0.2126 * lut[px.r8] + 0.7152 * lut[px.g8] + 0.0722 * lut[px.b8]) / EXPOSURE_SCALE
			counts[which] += 1
	if counts[0] < 20 or counts[1] < 20:
		return {"measured": false, "reason": "probe patches not visible (%d key, %d fill pixels) - is the probe inside geometry?" % counts, "image": path}
	var key: float = sums[0] / counts[0]
	var fill: float = sums[1] / counts[1]
	return {
		"measured": true,
		"key_linear": snappedf(key, 0.001),
		"fill_linear": snappedf(fill, 0.001),
		"key_fill_ratio": snappedf(key / maxf(fill, 0.0005), 0.01),
		"key_fill_stops": snappedf(log(key / maxf(fill, 0.0005)) / log(2.0), 0.01),
		"clipped_pct": snappedf(100.0 * clipped / (counts[0] + counts[1]), 0.1),
		"image": path,
	}


## Whether `cam` sees the grey probe unobstructed: render it unshaded in two
## flat colours and check that the pixels over it change. A colour test alone
## fails, because exposure and AgX shift the colour.
func _probe_visible(cam: Camera3D, at: Vector3) -> bool:
	var saved := probe_gray.material_override
	root.debug_draw = Viewport.DEBUG_DRAW_UNSHADED
	var imgs := []
	for col in [Color(1, 0, 1), Color(0, 1, 0)]:
		var flag := StandardMaterial3D.new()
		flag.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		flag.albedo_color = col
		probe_gray.material_override = flag
		for i in 3:
			await process_frame
		await RenderingServer.frame_post_draw
		var img := root.get_texture().get_image()
		img.convert(Image.FORMAT_RGBA8)
		imgs.append(img)
	root.debug_draw = Viewport.DEBUG_DRAW_DISABLED
	probe_gray.material_override = saved
	if cam.is_position_behind(at):
		return false
	var c := cam.unproject_position(at)
	var r := c.distance_to(cam.unproject_position(at + cam.global_basis.x * PROBE_RADIUS)) * 0.8
	var hit := 0
	var total := 0
	for k in 64:
		var p := Vector2i(c + Vector2.from_angle(k * TAU / 64.0) * r * sqrt(float(k % 8 + 1) / 8.0))
		if p.x < 0 or p.y < 0 or p.x >= imgs[0].get_width() or p.y >= imgs[0].get_height():
			continue
		total += 1
		var a: Color = imgs[0].get_pixelv(p)
		var b: Color = imgs[1].get_pixelv(p)
		if absi(a.r8 - b.r8) + absi(a.g8 - b.g8) + absi(a.b8 - b.b8) > 60:
			hit += 1
	return total > 32 and hit >= total * 0.9


## Temporarily override properties on the active Environment; returns what to
## restore with _pop_env. No-op without an environment.
func _push_env(props: Dictionary) -> Dictionary:
	var env := Common.active_environment(scene_root, root.get_camera_3d())
	if env == null or props.is_empty():
		return {}
	var saved := {"_env": env}
	for key in props:
		saved[key] = env.get(key)
		env.set(key, props[key])
	return saved


func _pop_env(saved: Dictionary) -> void:
	if saved.is_empty():
		return
	var env: Environment = saved["_env"]
	for key in saved:
		if key != "_env":
			env.set(key, saved[key])


## Render unshaded twice with two flat backgrounds; changed pixels are sky.
func _background_mask(settle: int) -> PackedByteArray:
	var env := Common.active_environment(scene_root, root.get_camera_3d())
	var made_env := false
	if env == null:
		# No environment: the default clear colour is the background.
		env = Environment.new()
		var we := WorldEnvironment.new()
		we.name = "LookdevMaskEnv"
		we.environment = env
		root.add_child(we)
		made_env = true
	var saved := {}
	for prop in ["background_mode", "background_color", "background_energy_multiplier",
			"fog_enabled", "volumetric_fog_enabled", "glow_enabled", "tonemap_mode"]:
		saved[prop] = env.get(prop)
	env.background_mode = Environment.BG_COLOR
	env.background_energy_multiplier = 1.0
	env.fog_enabled = false
	env.volumetric_fog_enabled = false
	env.glow_enabled = false
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	root.debug_draw = Viewport.DEBUG_DRAW_UNSHADED
	var imgs := []
	for col in [Color(1, 0, 1), Color(0, 1, 0)]:
		env.background_color = col
		for i in maxi(4, settle >> 1):
			await process_frame
		await RenderingServer.frame_post_draw
		imgs.append(Stats.reduce(root.get_texture().get_image()))
	root.debug_draw = Viewport.DEBUG_DRAW_DISABLED
	for prop in saved:
		env.set(prop, saved[prop])
	if made_env:
		root.get_node("LookdevMaskEnv").queue_free()
	# Let the restored environment settle before the next shot renders.
	for i in 2:
		await process_frame
	return Stats.background_mask(imgs[0], imgs[1])


## One image with a row per shot and a column per view, in the order given, so
## a whole capture can be looked at in a single read.
func _contact_sheet(shot_results: Array, views: Array) -> String:
	const TILE_W := 640
	const GAP := 4
	if shot_results.is_empty() or views.is_empty():
		return ""
	var first := Image.load_from_file(shot_results[0]["files"][views[0]])
	var tile_h := int(round(first.get_height() * float(TILE_W) / first.get_width()))
	var sheet := Image.create(views.size() * (TILE_W + GAP) - GAP,
			shot_results.size() * (tile_h + GAP) - GAP, false, Image.FORMAT_RGBA8)
	sheet.fill(Color(0.08, 0.08, 0.08))
	for row in shot_results.size():
		for col in views.size():
			var img := Image.load_from_file(shot_results[row]["files"][views[col]])
			img.convert(Image.FORMAT_RGBA8)
			img.resize(TILE_W, tile_h, Image.INTERPOLATE_BILINEAR)
			sheet.blit_rect(img, Rect2i(0, 0, TILE_W, tile_h),
					Vector2i(col * (TILE_W + GAP), row * (tile_h + GAP)))
	var path := out_dir.path_join("sheet.png")
	sheet.save_png(path)
	return path


func _environment_summary() -> Dictionary:
	var env := Common.active_environment(scene_root, root.get_camera_3d())
	if env == null:
		return {"present": false}
	return {
		"present": true,
		"tonemap_mode": env.tonemap_mode,
		"tonemap_exposure": env.tonemap_exposure,
		"ambient_light_source": env.ambient_light_source,
		"sdfgi": env.sdfgi_enabled,
		"ssao": env.ssao_enabled,
		"ssil": env.ssil_enabled,
		"ssr": env.ssr_enabled,
		"glow": env.glow_enabled,
		"fog": env.fog_enabled,
		"volumetric_fog": env.volumetric_fog_enabled,
	}
