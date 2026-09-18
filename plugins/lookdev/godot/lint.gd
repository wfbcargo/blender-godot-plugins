extends SceneTree
## lookdev lint: static checks on a scene's environment, lights and materials.
## Runs headless - nothing is rendered, and the scene is instantiated but never
## added to the tree, so none of its scripts run.
##
##   godot --headless --path <project> --script <this> -- --scene res://x.tscn --out lint.json
##
## Each finding says what is wrong, why it matters for realism, and the property
## to change. Severity: error = renders wrong or not at all; warn = a common
## cause of the "CG look"; info = worth a deliberate decision.

const Common := preload("common.gd")

var findings: Array = []
var scene_root: Node
var physical := false
var material_count := 0
var light_count := 0
var _seen_materials := {}


func _initialize() -> void:
	var args := Common.parse_user_args()
	var scene_path := str(args.get("scene", ""))
	var out := str(args.get("out", ""))
	var packed := load(scene_path) as PackedScene
	if packed == null:
		Common.fail(self, "cannot load scene '%s'" % scene_path)
		return
	scene_root = packed.instantiate()
	physical = Common.physical_units()

	# Materials first: the lights check asks whether anything is emissive.
	_walk_materials(scene_root)
	if material_count == 0:
		# A lint that looked at nothing must not read as a clean bill of health. The usual cause is a
		# scene whose script builds the stage and loads the characters in _ready (figure_study.tscn):
		# lint instantiates without running scripts, so it sees none of that.
		add("error", "NO_MATERIALS", "scene",
			"the scene has 0 materials to check: it is empty, or its geometry is made at runtime by a script (lint instantiates the scene without running scripts). Nothing was measured.",
			"lint a scene that holds the geometry (an imported glb, a saved stage), or use `capture`/`close-shot`, which run the scene")
	_check_project()
	_check_environment()
	_check_lights()
	_check_gi_nodes()

	var report := {
		"scene": scene_path,
		"physical_light_units": physical,
		"rendering_method": Common.rendering_method(),
		"checked": {"materials": material_count, "lights": light_count},
		"findings": findings,
	}
	var text := JSON.stringify(report, "  ", false)
	if out.is_empty():
		print(text)
	else:
		var f := FileAccess.open(out, FileAccess.WRITE)
		if f == null:
			Common.fail(self, "cannot write '%s': %s" % [out, error_string(FileAccess.get_open_error())])
			scene_root.free()
			return
		f.store_string(text)
		f.close()
	Common.emit("done", {"findings": findings.size()})
	scene_root.free()
	quit(0)


func add(severity: String, code: String, where: String, message: String, fix := "") -> void:
	findings.append({"severity": severity, "code": code, "where": where, "message": message, "fix": fix})


func path_of(node: Node) -> String:
	return "." if node == scene_root else str(scene_root.get_path_to(node))


# ----------------------------------------------------------------- project

func _check_project() -> void:
	var method := Common.rendering_method()
	if method != "forward_plus":
		add("info", "RENDERER", "project.godot",
			"rendering method is '%s': SDFGI, VoxelGI, SSIL, SSR, volumetric fog and auto-exposure are Forward+ only." % method)
	var msaa := int(ProjectSettings.get_setting("rendering/anti_aliasing/quality/msaa_3d", 0))
	var taa := bool(ProjectSettings.get_setting("rendering/anti_aliasing/quality/use_taa", false))
	var fxaa := int(ProjectSettings.get_setting("rendering/anti_aliasing/quality/screen_space_aa", 0))
	if msaa == 0 and not taa and fxaa == 0:
		add("info", "NO_ANTIALIASING", "project.godot",
			"no MSAA, TAA or screen-space AA: aliased edges and shimmering speculars read as CG, and soft-shadow dithering stays visible.",
			"rendering/anti_aliasing/quality/use_taa = true (or msaa_3d = 2)")
	var shadow_size := int(ProjectSettings.get_setting("rendering/lights_and_shadows/directional_shadow/size", 4096))
	if shadow_size < 4096:
		add("info", "SHADOW_RES", "project.godot", "directional shadow map is %d px; sun shadows will be soft and blocky." % shadow_size,
			"rendering/lights_and_shadows/directional_shadow/size = 4096")


# ------------------------------------------------------------- environment

func _check_environment() -> void:
	var wes := Common.find_all(scene_root, "WorldEnvironment")
	if wes.size() > 1:
		add("warn", "ENV_MULTIPLE", "scene", "%d WorldEnvironment nodes; only one applies and which one is order-dependent." % wes.size())
	var env: Environment = null
	var where := "scene"
	for we in wes:
		if (we as WorldEnvironment).environment != null:
			env = (we as WorldEnvironment).environment
			where = path_of(we)
			break
	if env == null:
		add("error", "ENV_MISSING", "scene",
			"no WorldEnvironment with an Environment. The scene falls back to a flat clear colour, no sky ambient, no reflections and linear tonemapping.",
			"add a WorldEnvironment with background_mode = Sky, a PhysicalSkyMaterial, ambient_light_source = Sky and tonemap_mode = AgX (or run `lookdev.mjs preset`)")
		return
	var forward_plus := Common.rendering_method() == "forward_plus"

	# Background / sky
	if env.background_mode == Environment.BG_SKY:
		if env.sky == null or env.sky.sky_material == null:
			add("error", "SKY_MISSING", where, "background_mode is Sky but there is no Sky or sky material; the background renders black and ambient comes out black.",
				"assign environment.sky with a PhysicalSkyMaterial or PanoramaSkyMaterial")
		elif env.sky.sky_material is PanoramaSkyMaterial and (env.sky.sky_material as PanoramaSkyMaterial).panorama == null:
			add("error", "HDRI_MISSING", where, "PanoramaSkyMaterial has no panorama texture.", "set panorama to an .hdr/.exr equirectangular image")

	# Tonemapping
	match env.tonemap_mode:
		Environment.TONE_MAPPER_LINEAR, Environment.TONE_MAPPER_REINHARDT:
			add("warn", "TONEMAP", where,
				"tonemap_mode is %s: highlights clip hard and saturated lights skew hue. Real cameras and film roll highlights off." % ["Linear", "Reinhard"][env.tonemap_mode],
				"environment.tonemap_mode = 4 (AgX). Its defaults (white 16.29, contrast 1.25) match Blender's AgX, so Blender reference renders are comparable. Re-check exposure after switching.")
		Environment.TONE_MAPPER_FILMIC, Environment.TONE_MAPPER_ACES:
			if env.tonemap_white < 4.0:
				add("info", "TONEMAP_WHITE", where, "tonemap_white %.1f with Filmic/ACES compresses highlights early; photoreal setups use 6-8." % env.tonemap_white,
					"environment.tonemap_white = 6.0, or switch to AgX (4)")

	# Ambient
	var ambient_from_sky := env.ambient_light_source == Environment.AMBIENT_SOURCE_SKY or \
			(env.ambient_light_source == Environment.AMBIENT_SOURCE_BG and env.background_mode == Environment.BG_SKY)
	if env.ambient_light_source == Environment.AMBIENT_SOURCE_COLOR or \
			(env.ambient_light_source == Environment.AMBIENT_SOURCE_BG and env.background_mode in [Environment.BG_COLOR, Environment.BG_CLEAR_COLOR]):
		add("warn", "AMBIENT_FLAT", where,
			"ambient light is a constant colour: it arrives equally from every direction and erases form - the single most common flat-CG tell.",
			"environment.ambient_light_source = 3 (Sky) with a sky background, plus GI")
	elif ambient_from_sky and env.ambient_light_sky_contribution >= 0.999 and not is_equal_approx(env.ambient_light_energy, 1.0):
		# Verified in 4.7 with lookdev capture: 0.0 and 0.9 render identically.
		add("warn", "AMBIENT_ENERGY_IGNORED", where,
			"ambient_light_energy is %.2f, but with sky ambient and ambient_light_sky_contribution = 1 it has no effect - it only scales the colour share of ambient." % env.ambient_light_energy,
			"to change sky fill, scale the sky itself (sky material energy_multiplier, or background_energy_multiplier), or blend toward ambient_light_color with ambient_light_sky_contribution < 1")
	if env.ambient_light_source == Environment.AMBIENT_SOURCE_DISABLED:
		add("info", "AMBIENT_OFF", where, "ambient light disabled: shadows get only GI. Fine with baked lightmaps, black otherwise.")

	# Global illumination
	var voxel := Common.find_all(scene_root, "VoxelGI")
	var lightmap := Common.find_all(scene_root, "LightmapGI")
	if not env.sdfgi_enabled and voxel.is_empty() and lightmap.is_empty():
		add("warn", "NO_GI", where,
			"no global illumination (SDFGI, VoxelGI or LightmapGI): no bounce light or colour bleed, so shadowed areas are lit only by the sky and read flat or dirty.",
			"exteriors / large or dynamic scenes: environment.sdfgi_enabled = true (sdfgi_use_occlusion = true against leaks). Bounded interiors: VoxelGI. Static and best quality: LightmapGI (editor bake only).")
	if env.sdfgi_enabled and not forward_plus:
		add("error", "SDFGI_RENDERER", where, "SDFGI is enabled but the renderer is not Forward+; it does nothing.")
	if not env.ssao_enabled:
		add("info", "NO_SSAO", where, "SSAO off: objects don't sit on surfaces; contact darkening is missing.",
			"environment.ssao_enabled = true (radius ~1, intensity ~2; keep ssao_light_affect near 0 so AO only darkens ambient)")
	elif env.ssao_light_affect > 0.3:
		add("info", "SSAO_LIGHT_AFFECT", where, "ssao_light_affect %.2f darkens direct light too; real occlusion affects ambient only." % env.ssao_light_affect,
			"environment.ssao_light_affect = 0.0")
	if not env.ssil_enabled and forward_plus and voxel.is_empty() and lightmap.is_empty() and not env.sdfgi_enabled:
		add("info", "NO_SSIL", where, "SSIL off as well: no short-range bounce at all.", "environment.ssil_enabled = true")

	# Post
	if env.glow_enabled and (env.glow_intensity > 1.5 or env.glow_hdr_threshold < 0.8):
		add("warn", "GLOW_HEAVY", where,
			"glow intensity %.2f / HDR threshold %.2f blooms midtones, not just light sources - a strong CG tell." % [env.glow_intensity, env.glow_hdr_threshold],
			"glow_hdr_threshold >= 1.0 and glow_intensity <= 1.0")
	if env.adjustment_enabled and env.adjustment_saturation > 1.3:
		add("info", "SATURATION_BOOST", where, "adjustment_saturation %.2f; oversaturation reads as CG." % env.adjustment_saturation)
	if not env.fog_enabled and not env.volumetric_fog_enabled:
		add("info", "NO_FOG", where,
			"no fog or aerial perspective. Distant objects keep full contrast, which flattens depth in exteriors (fine for small interiors).",
			"fog_enabled = true, fog_mode = 0, fog_density ~0.0005-0.002, fog_aerial_perspective ~0.5, fog_sky_affect ~0.3")
	if env.volumetric_fog_enabled and not forward_plus:
		add("error", "VOLFOG_RENDERER", where, "volumetric fog needs Forward+.")

	_check_exposure(env, where)


func _check_exposure(env: Environment, where: String) -> void:
	var attrs: CameraAttributes = null
	for we in Common.find_all(scene_root, "WorldEnvironment"):
		if (we as WorldEnvironment).camera_attributes != null:
			attrs = (we as WorldEnvironment).camera_attributes
	for cam in Common.find_all(scene_root, "Camera3D"):
		if (cam as Camera3D).attributes != null:
			attrs = (cam as Camera3D).attributes
	if physical:
		if attrs == null:
			add("warn", "PHYSICAL_NO_CAMERA_ATTRIBUTES", where,
				"physical light units are on but no CameraAttributes are set, so exposure uses defaults tuned for nothing in particular.",
				"WorldEnvironment.camera_attributes = CameraAttributesPhysical (daylight: aperture 16, shutter 100-250, sensitivity 100; interiors: aperture 2.8-4, shutter 50-60)")
	if env.tonemap_exposure > 4.0 or env.tonemap_exposure < 0.25:
		add("info", "EXPOSURE_EXTREME", where,
			"tonemap_exposure %.2f is far from 1: usually a sign the light levels themselves are inconsistent." % env.tonemap_exposure)


# ------------------------------------------------------------------ lights

func _check_lights() -> void:
	var lights := Common.find_all(scene_root, "Light3D")
	light_count = lights.size()
	var suns: Array[Node] = []
	var shadowed_local := 0
	for l in lights:
		var light := l as Light3D
		var where := path_of(light)
		if light is DirectionalLight3D:
			suns.append(light)
			_check_sun(light as DirectionalLight3D, where)
		elif light is OmniLight3D or light is SpotLight3D:
			if light.shadow_enabled:
				shadowed_local += 1
			_check_local(light, where)
		if not physical and not is_equal_approx(light.light_temperature, 6500.0):
			add("warn", "TEMPERATURE_IGNORED", where,
				"light_temperature is %d K but physical light units are off, so it has no effect." % int(light.light_temperature),
				"set light_color to the blackbody colour instead (lookdev presets do this), or enable rendering/lights_and_shadows/use_physical_light_units")
		if light.shadow_enabled and light.shadow_bias > 0.3:
			add("warn", "SHADOW_BIAS_HIGH", where, "shadow_bias %.2f detaches shadows from their casters (peter-panning); objects look like they float." % light.shadow_bias,
				"shadow_bias ~0.03-0.1; fix acne with shadow_normal_bias instead")
		if light.shadow_enabled and light.shadow_normal_bias > 5.0:
			add("info", "SHADOW_NORMAL_BIAS_HIGH", where, "shadow_normal_bias %.1f can shrink shadows and open light leaks at contacts." % light.shadow_normal_bias)

	if lights.is_empty():
		var emissive := false
		for m in _seen_materials.values():
			if m is BaseMaterial3D and (m as BaseMaterial3D).emission_enabled:
				emissive = true
		if Common.find_all(scene_root, "LightmapGI").is_empty() and not emissive:
			add("warn", "NO_LIGHTS", "scene", "no lights: everything is lit by ambient alone, with no key direction and no shadows.",
				"add a DirectionalLight3D (exteriors) or practical Omni/Spot lights (interiors)")
	if suns.size() > 1:
		var shadowed := suns.filter(func(s): return (s as Light3D).shadow_enabled).size()
		add("warn" if shadowed > 1 else "info", "MULTIPLE_SUNS", "scene",
			"%d DirectionalLight3Ds (%d with shadows). One sun means one shadow direction; extra suns give double shadows and cost a shadow pass each." % [suns.size(), shadowed],
			"keep one shadowed sun; fake fill with sky ambient/GI, or an unshadowed sun at low energy")
	if shadowed_local > 8:
		add("info", "MANY_SHADOWED_LIGHTS", "scene", "%d shadowed omni/spot lights share the positional shadow atlas; expect blurry shadows or dropped ones." % shadowed_local)


func _check_sun(sun: DirectionalLight3D, where: String) -> void:
	var ea := Common.elevation_azimuth(sun)
	if ea.x < 0.0:
		add("error", "SUN_BELOW_HORIZON", where,
			"the sun points upward (elevation %.0f°): light comes from below the ground." % ea.x,
			"rotate so the light's -Z points down; `lookdev.mjs preset --elevation` sets it from angles")
	elif ea.x < 3.0 and sun.visible:
		add("info", "SUN_GRAZING", where, "sun elevation %.1f°: grazing light and very long shadows. Intended for sunset?" % ea.x)
	if not sun.shadow_enabled:
		add("warn", "SUN_NO_SHADOW", where, "the sun casts no shadows: nothing is grounded, and the main depth cue in an exterior is gone.",
			"shadow_enabled = true")
	elif sun.directional_shadow_max_distance > 500.0:
		add("info", "SHADOW_DISTANCE", where,
			"directional_shadow_max_distance %.0f spreads the shadow map thin; near shadows go soft and blocky." % sun.directional_shadow_max_distance,
			"directional_shadow_max_distance 100-200 for ground-level cameras")
	if physical:
		var lux := sun.light_intensity_lux
		if lux < 0.01 or lux > 150000.0:
			add("warn", "SUN_LUX", where, "sun intensity %s lux is outside the natural range (moonlight ~0.1, overcast ~10k-20k, clear noon ~100k)." % str(lux))
	else:
		if sun.light_energy > 8.0:
			add("warn", "SUN_ENERGY_HIGH", where,
				"light_energy %.1f without physical units usually means exposure is being fixed with the light. Brightness belongs to exposure; the sun:sky ratio is what reads as real." % sun.light_energy)
	if sun.light_angular_distance == 0.0 and sun.shadow_enabled:
		add("info", "SUN_HARD_EDGES", where,
			"light_angular_distance 0: razor-sharp shadow edges everywhere. The real sun subtends ~0.5°, which softens shadows with distance from the caster.",
			"light_angular_distance = 0.5 (costs some performance)")


func _check_local(light: Light3D, where: String) -> void:
	var attenuation := 1.0
	var reach := 0.0
	if light is OmniLight3D:
		attenuation = (light as OmniLight3D).omni_attenuation
		reach = (light as OmniLight3D).omni_range
	else:
		attenuation = (light as SpotLight3D).spot_attenuation
		reach = (light as SpotLight3D).spot_range
	if attenuation < 0.5:
		add("info", "FALLOFF_LINEAR", where,
			"attenuation %.2f gives near-linear falloff; real lights fall off with the inverse square, which is what makes a light pool read as a light." % attenuation,
			"attenuation ~1.0-2.0 with a range long enough that the cutoff isn't visible")
	if reach < 1.0:
		add("info", "RANGE_SHORT", where, "range %.2f m: the light ends in a visible hard edge." % reach)
	if physical:
		var lm := light.light_intensity_lumens
		if lm < 1.0 or lm > 100000.0:
			add("warn", "LUMENS", where, "%s lumens is outside practical range (candle ~13, 60W bulb ~800, streetlight 5k-20k)." % str(lm))


func _check_gi_nodes() -> void:
	for n in Common.find_all(scene_root, "LightmapGI"):
		var lm := n as LightmapGI
		if lm.light_data == null:
			add("warn", "LIGHTMAP_UNBAKED", path_of(lm), "LightmapGI has no baked data, so it contributes nothing.",
				"bake in the editor (Bake Lightmaps); it cannot be baked from a script in 4.7. Mesh import needs meshes/light_baking = Static Lightmaps.")
	for n in Common.find_all(scene_root, "VoxelGI"):
		var v := n as VoxelGI
		if v.data == null:
			add("warn", "VOXELGI_UNBAKED", path_of(v), "VoxelGI has no baked data, so it contributes nothing.",
				"bake in the editor, or at runtime: $VoxelGI.bake() (works outside the editor)")


# --------------------------------------------------------------- materials

func _walk_materials(node: Node) -> void:
	if node is GeometryInstance3D:
		var gi := node as GeometryInstance3D
		if gi.material_override != null:
			_check_material(gi.material_override, path_of(node) + " (material_override)", node)
		elif node is MeshInstance3D:
			var mi := node as MeshInstance3D
			if mi.mesh != null:
				for s in mi.mesh.get_surface_count():
					var mat := mi.get_surface_override_material(s)
					if mat == null:
						mat = mi.mesh.surface_get_material(s)
					if mat == null:
						if not (node is Label3D):
							add("info", "NO_MATERIAL", path_of(node) + " surface %d" % s,
								"no material: renders with Godot's default white-grey, which has no plausible albedo or roughness.")
					else:
						_check_material(mat, path_of(node) + " surface %d" % s, node)
	for child in node.get_children():
		_walk_materials(child)


func _check_material(mat: Material, where: String, node: Node) -> void:
	var id := mat.get_instance_id()
	if _seen_materials.has(id):
		return
	_seen_materials[id] = mat
	material_count += 1
	if mat is ShaderMaterial:
		return
	if not mat is BaseMaterial3D:
		return
	var m := mat as BaseMaterial3D
	var label := where
	if not m.resource_name.is_empty():
		label += " [%s]" % m.resource_name

	if m.shading_mode == BaseMaterial3D.SHADING_MODE_UNSHADED and not (node is Label3D) and not (node is Sprite3D):
		add("info", "UNSHADED", label, "unshaded material: ignores all lighting, so it will never sit in the scene's light.")
		return

	var c := m.albedo_color
	var r8 := c.r8
	var g8 := c.g8
	var b8 := c.b8
	var mx := maxi(r8, maxi(g8, b8))
	var mn := mini(r8, mini(g8, b8))
	var textured := m.albedo_texture != null
	var metal := m.metallic >= 0.5
	# With a texture, albedo_color is a tint multiplier and only extremes matter.
	if not metal and not m.emission_enabled:
		if not textured and mx < 30:
			add("warn", "ALBEDO_TOO_DARK", label,
				"albedo %s is darker than almost any real dielectric (charcoal is ~0.02-0.04 linear, ~40-56 sRGB). It will look like a hole and kill bounce light." % _col(c),
				"keep base colour >= 30-50 sRGB (fresh asphalt ~56, soil ~115)")
		if not textured and mx > 240:
			add("warn", "ALBEDO_TOO_BRIGHT", label,
				"albedo %s is brighter than real surfaces (fresh snow ~0.85 linear / 240 sRGB; white paint 0.7-0.8). Overbright albedo also over-feeds GI." % _col(c),
				"cap base colour around 240 sRGB; white paint ~215-230")
		if textured and mx < 150 and not c.is_equal_approx(Color.WHITE):
			add("info", "ALBEDO_TINT_DARK", label, "albedo_color %s multiplies the albedo texture; dark tints often push textures below physical range." % _col(c))
		if mx > 60 and float(mx - mn) / mx > 0.85 and not textured:
			add("info", "ALBEDO_SATURATED", label, "albedo %s is nearly fully saturated; natural materials rarely exceed ~0.6 saturation." % _col(c))
	if m.metallic > 0.1 and m.metallic < 0.9 and m.metallic_texture == null:
		add("warn", "METALLIC_PARTIAL", label,
			"metallic %.2f: a surface is either metal or not. In-between values are only for transitions (dirt, worn edges) painted in a mask." % m.metallic,
			"metallic 0.0 or 1.0; drive transitions with metallic_texture")
	if metal and mx < 170 and not textured:
		add("warn", "METAL_TOO_DARK", label,
			"metal base colour %s is below 170 sRGB. For metals base colour is the specular reflectance: iron ~196, aluminium ~232, gold (255,220,145)." % _col(c),
			"raise base colour; darken a metal with roughness or dirt, not albedo")
	if not metal and m.roughness < 0.05 and m.roughness_texture == null:
		add("info", "ROUGHNESS_MIRROR", label,
			"roughness %.2f: a perfect mirror finish. Even polished dielectrics (glass, lacquer) sit around 0.05-0.2." % m.roughness)
	if m.roughness_texture == null and not m.detail_enabled and node is MeshInstance3D and (node as MeshInstance3D).mesh != null:
		var size := (node as MeshInstance3D).mesh.get_aabb().size * (node as Node3D).scale
		if maxf(size.x, maxf(size.y, size.z)) > 6.0 and m.normal_texture == null:
			add("info", "UNIFORM_SURFACE", label,
				"a %.0f m surface with constant roughness and no normal map. Real surfaces vary (±0.05-0.15 roughness from wear and dust); uniform ones read as plastic." % maxf(size.x, maxf(size.y, size.z)),
				"add roughness_texture / normal_texture, or detail_enabled with a tiling detail map; uv1_triplanar for untextured terrain")
	_check_skin(m, label)
	if not is_equal_approx(m.metallic_specular, 0.5):
		if m.metallic_specular > 0.8 or m.metallic_specular < 0.2:
			add("info", "SPECULAR_UNUSUAL", label,
				"metallic_specular %.2f. Nearly every dielectric is 0.5 (F0 4%%); water ~0.35, skin ~0.42, gemstones higher." % m.metallic_specular)
	if m.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED and is_equal_approx(c.a, 1.0) and m.albedo_texture == null:
		add("info", "TRANSPARENT_OPAQUE", label,
			"transparency is enabled on a fully opaque colour: breaks sorting, SSAO/SSR and shadow receiving for nothing.",
			"transparency = Disabled")
	if m.emission_enabled and m.emission_energy_multiplier > 16.0 and not physical:
		add("info", "EMISSION_HOT", label, "emission energy %.1f will clip and bloom regardless of exposure." % m.emission_energy_multiplier)


## Skin that reads as clay or plastic: a material named `*skin*` or carrying lookdev's `skin` preset with a flat
## albedo (lips, areolae, palms and knees all one colour), one roughness everywhere, no normal or pore detail, or
## no subsurface scattering. A preset material counts what `LookdevMaterials.apply` will set from its extras
## (glTF cannot carry subsurface), since lint never runs the scene's scripts.
func _check_skin(m: BaseMaterial3D, label: String) -> void:
	var spec := {}
	if m.has_meta("extras") and typeof(m.get_meta("extras")) == TYPE_DICTIONARY:
		var e: Dictionary = m.get_meta("extras")
		if typeof(e.get("lookdev")) == TYPE_DICTIONARY:
			spec = e["lookdev"]
	var preset := str(spec.get("preset", ""))
	if preset != "skin" and not m.resource_name.to_lower().contains("skin"):
		return
	var g = spec.get("godot", {})
	var asks_sss: bool = typeof(g) == TYPE_DICTIONARY and bool(g.get("subsurf_scatter_enabled", false))
	var problems := []
	if m.albedo_texture == null:
		problems.append("a flat albedo (lips, areolae, palms, soles and knees all one colour)")
	if m.roughness_texture == null:
		problems.append("one roughness everywhere")
	if m.normal_texture == null and not m.detail_enabled and not spec.has("detail"):
		problems.append("no normal map or pore detail")
	if not m.subsurf_scatter_enabled and not asks_sss:
		problems.append("no subsurface scattering")
	if not problems.is_empty():
		add("warn", "SKIN_PLASTIC", label,
			"skin with %s: it reads as clay or plastic under any light." % ", ".join(problems),
			"humanform look.skin (realistic, the default) bakes regional tone, roughness and normal maps; LookdevMaterials.apply sets subsurf_scatter and pores from the material's extras")


func _col(c: Color) -> String:
	return "(%d,%d,%d)" % [c.r8, c.g8, c.b8]
