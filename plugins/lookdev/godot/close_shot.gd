extends SceneTree
## lookdev close-shot: a labelled sheet of close-ups of one character, rendered in Godot under named
## lighting presets. Driven by `bin/lookdev.mjs close-shot`.
##
##   godot --path <project> --script <this> --resolution 640x640 --position -20000,-20000 \
##         --fixed-fps 60 -- --spec <spec.json>
##
## Loads a glb (an imported res:// path, or any file through GLTFDocument), applies LookdevMaterials,
## attaches the strands its .moves.json lists and equips any garments given, poses one clip at one time,
## then for every preset x view aims a camera from the posed frame's bones - never height fractions -
## and renders one tile. The field of view is chosen so the subject fills the tile at the stated
## distance: distance sets the perspective, the lens sets the framing, as a photographer would.
##
## Each tile is the render with a label band *above* it (view, distance, preset, fov, clip), as
## rig-anything's Blender look set does, so the label never covers the figure; `"label": "inside"` puts it
## back over the top of the render (the old layout, kept as the control for the head-under-band check).
##
## Like capture.gd it needs a window (`--headless` has no renderer); the runner parks it off-screen.
##
## Views (spec "views": [{"view": name, "distance": m, "aim_offset": [x,y,z]?, "pair": {...}?}]). The head
## and hand views follow rig-anything `closeups._aim`, so a Blender tile and a Godot tile of a view line up:
##   face, eyes                from the eyeballs (the sclera surface carried by the head bone's skin bind),
##                             falling back to the head bone when the mesh has no eye surface
##   face_3q                   three-quarter from the head's front-left: hairline, nose and cheek in relief
##   head_side, head_back      the whole head from its left and from behind: ear, hairline, nape, a tail
##   hand_palm.L/.R, hand_back.L/.R   palm centre from the hand and finger bones; the palm normal from
##                             the knuckle line and the hand's length, so it follows the pose
##   feet, bust, crotch, full  from foot/toe, upper arm, thigh bones and the whole posed skeleton
##   bone:<name>               any bone, from the figure's front (size from the view's "size", default 0.3 m)
## `aim_offset` moves a view's camera (target and eye) by a world offset while its checks keep the view's
## own subject: the control that a wrongly aimed camera fails.
##
## Fails loudly (exit 2, before rendering anything) on: a glb that does not load, no Skeleton3D, a view
## whose bone is missing, an unknown clip, a preset the open stage cannot take (interior_daylight) unless
## "force", an out_dir it cannot write. After rendering it exits 1 when any tile fails a check, each
## measured from the tile's own pixels and the posed bones, with the free value reported in close.json:
##   EMPTY_TILE      the figure covers less than "min_coverage" of the tile
##   SUBJECT_SMALL   the subject (what lies within `slab` of the target's depth) covers less than
##                   "min_subject" (body views)
##   OFF_TARGET      the view's subject points (its own bones: the head, both eyes, wrist/knuckle/tip...)
##                   project with their centroid more than CENTRAL from the tile's centre, lie behind the
##                   camera, or (body views) the figure does not cover their centroid
##   SUBJECT_CUT     full: the top of the head or a foot falls outside the picture
##   LABEL_OVER_HEAD full: the head's projected box meets the label band

const Common := preload("common.gd")

const HERE_ADDON := "addons/lookdev"
const STAGE_FLOOR := Color(0.46, 0.46, 0.46)       # sRGB 0.46 = linear 0.18, as figure_study's stage
const BACKDROP := Color(0.52, 0.53, 0.55)

## Candidate bone names per role, first found wins: rig-anything/Rigify first, then Mixamo.
const ALIASES := {
	"head": ["head", "Head", "spine.006", "spine.005", "mixamorig:Head"],
	"neck": ["neck", "Neck", "spine.004", "mixamorig:Neck"],
	"chest": ["chest", "spine.003", "mixamorig:Spine2"],
	"hips": ["hips", "pelvis", "spine", "mixamorig:Hips"],
	"upper_arm.L": ["upper_arm.L", "mixamorig:LeftArm"],
	"upper_arm.R": ["upper_arm.R", "mixamorig:RightArm"],
	"hand.L": ["hand.L", "mixamorig:LeftHand"],
	"hand.R": ["hand.R", "mixamorig:RightHand"],
	"f_index.01.L": ["f_index.01.L", "mixamorig:LeftHandIndex1"],
	"f_index.01.R": ["f_index.01.R", "mixamorig:RightHandIndex1"],
	"f_middle.01.L": ["f_middle.01.L", "mixamorig:LeftHandMiddle1"],
	"f_middle.01.R": ["f_middle.01.R", "mixamorig:RightHandMiddle1"],
	"f_middle.03.L": ["f_middle.03.L", "mixamorig:LeftHandMiddle3"],
	"f_middle.03.R": ["f_middle.03.R", "mixamorig:RightHandMiddle3"],
	"f_pinky.01.L": ["f_pinky.01.L", "mixamorig:LeftHandPinky1"],
	"f_pinky.01.R": ["f_pinky.01.R", "mixamorig:RightHandPinky1"],
	"thigh.L": ["thigh.L", "mixamorig:LeftUpLeg"],
	"thigh.R": ["thigh.R", "mixamorig:RightUpLeg"],
	"foot.L": ["foot.L", "mixamorig:LeftFoot"],
	"foot.R": ["foot.R", "mixamorig:RightFoot"],
	"toe.L": ["toe.L", "mixamorig:LeftToeBase"],
	"toe.R": ["toe.R", "mixamorig:RightToeBase"],
}
const VIEW_NAMES := ["face", "face_3q", "eyes", "head_side", "head_back", "hand_palm.L", "hand_back.L",
	"hand_palm.R", "hand_back.R", "feet", "bust", "crotch", "full"]
const CENTRAL := 0.3          # the subject's centroid within this of the centre (0.5 = the edge), each axis,
							  # as rig-anything's closeups.CENTRAL
const CUT_MARGIN := 0.01      # full: every subject point this far inside the picture

var spec: Dictionary
var out_dir: String
var model: Node3D
var skel: Skeleton3D
var anim: AnimationPlayer
var we: WorldEnvironment
var sun: DirectionalLight3D
var cam: Camera3D
var label: Label
var label_layer: CanvasLayer
var band_vp: SubViewport
var band_label: Label
var band_px := 0
var stage_nodes: Array[Node3D] = []
var presets_mod: Script
var preset_src: Variant = null     # spec "presets_file" parsed, or null for the addon's presets.json
var materials_mod: Script
var manifest: Dictionary = {}
var notes: PackedStringArray = []

# the figure's frame, from the rest skeleton
var fwd_rest := Vector3.BACK
var up_rest := Vector3.UP
var eyes_rest: Array = []          # [left centre, right centre] in skin bind space of the head, or []
var eyes_bone := -1
var _target := Vector3.ZERO


func _initialize() -> void:
	_run()


func _run() -> void:
	var args := Common.parse_user_args()
	var parsed: Variant = Common.load_json(str(args.get("spec", "")))
	if not parsed is Dictionary:
		Common.fail(self, "spec is not a JSON object: " + str(args.get("spec", "")))
		return
	spec = parsed
	out_dir = str(spec.get("out_dir", ""))
	var werr := _writable(out_dir)
	if werr != "":
		Common.fail(self, werr)
		return
	presets_mod = _addon_script("lookdev_presets.gd")
	materials_mod = _addon_script("lookdev_materials.gd")
	if presets_mod == null or materials_mod == null:
		Common.fail(self, "cannot load the lookdev addon scripts (project res://addons/lookdev or the plugin's copy)")
		return

	# ---- presets first: a refusal costs nothing. "presets_file" reads the recipes from another
	# presets.json (a control renders an old recipe with today's code) instead of the addon's.
	var preset_names: Array = spec.get("presets", ["clear_midday"])
	if str(spec.get("presets_file", "")) != "":
		preset_src = Common.load_json(str(spec["presets_file"]))
		if not preset_src is Dictionary or not (preset_src as Dictionary).has("presets"):
			Common.fail(self, "presets_file %s is not a presets.json (no 'presets')" % spec["presets_file"])
			return
	for pn in preset_names:
		if not presets_mod.all(preset_src).has(pn):
			Common.fail(self, "unknown preset '%s' (known: %s)" % [pn, ", ".join(presets_mod.names(preset_src))])
			return
		var need: String = presets_mod.needs(pn, preset_src)
		if need != "" and need != "open" and not spec.get("force", false):
			Common.fail(self, "preset %s needs an %s stage; close-shot renders on an open stage (a floor and a backdrop under the sky), where it clips everything to white. Pass --force to render it anyway." % [pn, need])
			return

	# ---- the character
	var glb := str(spec.get("glb", ""))
	model = _load_model(glb)
	if model == null:
		Common.fail(self, "cannot load '%s' (an imported res:// scene or a .glb/.gltf file)" % glb)
		return
	_build_stage()
	root.add_child(model)
	current_scene = model
	var skels := model.find_children("*", "Skeleton3D", true, false)
	if skels.is_empty():
		Common.fail(self, "'%s' has no Skeleton3D: close-shot aims its cameras at bones, and there are none" % glb)
		return
	skel = skels[0]
	manifest = _manifest_for(glb)

	var look: Dictionary = materials_mod.apply(model)
	var surfaces := 0
	for mi in model.find_children("*", "MeshInstance3D", true, false):
		if (mi as MeshInstance3D).mesh != null:
			surfaces += (mi as MeshInstance3D).mesh.get_surface_count()
	if surfaces == 0:
		Common.fail(self, "'%s' has no mesh surfaces to look at" % glb)
		return
	if look.get("materials", []).is_empty() and int(look.get("skipped", 0)) == 0:
		notes.append("no lookdev material extras in this glb: rendered with the imported materials as they are")

	var err := _attach_extras(glb)
	if err != "":
		Common.fail(self, err)
		return
	err = _pose()
	if err != "":
		Common.fail(self, err)
		return
	for i in 3:
		await process_frame
	skel.force_update_all_bone_transforms()

	# ---- resolve every view before rendering anything
	err = _rest_frame()
	if err != "":
		Common.fail(self, err)
		return
	var views: Array = spec.get("views", [])
	if views.is_empty():
		Common.fail(self, "no views given")
		return
	var aims := []
	for v in views:
		var a: Dictionary = _aim(v)
		if a.has("error"):
			Common.fail(self, "view %s: %s" % [str(v.get("view", "?")), a["error"]])
			return
		aims.append(a)

	# ---- render
	var tiles := []
	var failures := PackedStringArray()
	for pn in preset_names:
		var rep: Dictionary = presets_mod.apply(pn, we, sun, {"stage": "open", "force": spec.get("force", false), "presets": preset_src})
		if not rep["ok"]:
			Common.fail(self, "preset %s: %s" % [pn, "; ".join(rep["problems"])])
			return
		for w in rep["warnings"]:
			Common.emit("warning", {"message": "preset %s: %s" % [pn, w]})
		for ai in aims.size():
			var a: Dictionary = aims[ai]
			var t: Dictionary = await _render_tile(a, pn, int(spec.get("warmup_frames", 45)) if ai == 0 else 0)
			t["row"] = ai
			t["column"] = preset_names.find(pn)
			tiles.append(t)
			for f in t["failures"]:
				failures.append("%s %s: %s" % [pn, a["view"], f])
	var sheet := await _sheet(tiles, aims, preset_names)
	var result := {
		"glb": glb, "clip": spec.get("clip_resolved", ""), "time": spec.get("time", 0.0),
		"presets": preset_names, "sheet": sheet["path"], "sheet_px": sheet["size"],
		"layout": "one row per view, one column per preset" + (", the Blender tile of the view first" if sheet["blender"] else ""),
		"tile_px": [root.size.x, root.size.y], "band_px": band_px, "label": str(spec.get("label", "above")),
		"pair_blender": spec.get("pair_blender", {}),
		"materials": look, "notes": notes, "tiles": tiles, "failures": failures,
		"physical_light_units": Common.physical_units(),
	}
	var f := FileAccess.open(out_dir.path_join("close.json"), FileAccess.WRITE)
	if f == null:
		Common.fail(self, "cannot write %s: %s" % [out_dir.path_join("close.json"), error_string(FileAccess.get_open_error())])
		return
	f.store_string(JSON.stringify(result, "  ", false))
	f.close()
	Common.emit("done", {"sheet": sheet["path"], "stats": out_dir.path_join("close.json"), "failures": failures})
	quit(0 if failures.is_empty() else 1)


# ------------------------------------------------------------------ setup

func _writable(dir: String) -> String:
	if dir.is_empty():
		return "no out_dir given"
	if DirAccess.make_dir_recursive_absolute(dir) != OK and not DirAccess.dir_exists_absolute(dir):
		return "cannot create out_dir '%s'" % dir
	var probe := dir.path_join(".lookdev_write_test")
	var f := FileAccess.open(probe, FileAccess.WRITE)
	if f == null:
		return "cannot write into out_dir '%s': %s" % [dir, error_string(FileAccess.get_open_error())]
	f.close()
	DirAccess.remove_absolute(probe)
	return ""


## The project's copy of an addon script when it has one (a class_name script loaded from a second path
## fails to parse), else the plugin's own.
func _addon_script(file: String) -> Script:
	var res := "res://addons/lookdev/" + file
	if ResourceLoader.exists(res):
		return load(res)
	var here: String = (get_script() as Script).resource_path.get_base_dir()
	return load(here.path_join(HERE_ADDON).path_join(file))


func _load_model(path: String) -> Node3D:
	if path.is_empty():
		return null
	if path.begins_with("res://") and ResourceLoader.exists(path):
		var ps := load(path) as PackedScene
		if ps != null:
			return ps.instantiate() as Node3D
	var file := ProjectSettings.globalize_path(path) if path.begins_with("res://") else path
	if not FileAccess.file_exists(file):
		return null
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	if doc.append_from_file(file, state) != OK:
		return null
	notes.append("loaded through GLTFDocument (not the project's import): textures are uncompressed")
	return doc.generate_scene(state) as Node3D


func _manifest_for(glb: String) -> Dictionary:
	var p := glb.get_basename() + ".moves.json"
	var file: String = ProjectSettings.globalize_path(p) if p.begins_with("res://") else p
	if FileAccess.file_exists(file):
		var d: Variant = JSON.parse_string(FileAccess.get_file_as_string(file))
		if d is Dictionary:
			return d
	return {}


func _attach_extras(glb: String) -> String:
	if spec.get("strands", true):
		var paths: Array = manifest.get("strands", [])
		if not paths.is_empty():
			if not ResourceLoader.exists("res://addons/follow_through/follow_through.gd"):
				notes.append("strands listed in the manifest were not attached: the project has no follow_through addon")
			else:
				var ft: Script = load("res://addons/follow_through/follow_through.gd")
				for p in paths:
					if not ResourceLoader.exists(p):
						notes.append("strand file %s not found" % p)
						continue
					for r in ft.attach(model, load(p)):
						if not r.get("problems", []).is_empty():
							notes.append("strand %s: %s" % [p, r["problems"]])
				materials_mod.apply(model)
	var garments: Array = spec.get("garments", [])
	if not garments.is_empty():
		if not ResourceLoader.exists("res://addons/wardrobe/wardrobe.gd"):
			return "garments given but the project has no res://addons/wardrobe"
		var wd: Script = load("res://addons/wardrobe/wardrobe.gd")
		for g in garments:
			var gs: Variant = load(g) if str(g).begins_with("res://") else _load_model(str(g))
			if gs == null:
				return "cannot load garment '%s'" % g
			for r in wd.equip(model, gs, {"hem": false}):
				if not r.get("problems", PackedStringArray()).is_empty():
					return "garment %s: %s" % [g, r["problems"]]
		materials_mod.apply(model)
	return ""


func _pose() -> String:
	var players := model.find_children("*", "AnimationPlayer", true, false)
	var want := str(spec.get("clip", ""))
	if players.is_empty():
		if want != "":
			return "clip '%s' asked for, but the glb has no AnimationPlayer" % want
		notes.append("no AnimationPlayer: rest pose")
		return ""
	anim = players[0]
	if want == "":
		want = str(manifest.get("clips", {}).get("Idle", ""))
		if want == "":
			notes.append("no clip given and no Idle in a manifest: rest pose")
			return ""
	var clip := ""
	if anim.has_animation(want):
		clip = want
	elif manifest.get("clips", {}).has(want) and anim.has_animation(str(manifest["clips"][want])):
		clip = str(manifest["clips"][want])
	else:
		for n in anim.get_animation_list():
			if String(n).ends_with("_" + want):
				clip = n
				break
	if clip == "":
		return "no clip '%s' (clips: %s)" % [want, ", ".join(anim.get_animation_list())]
	var length := anim.get_animation(clip).length
	var t := clampf(float(spec.get("time", 0.0)), 0.0, length)
	anim.play(clip)
	anim.seek(t, true)
	anim.pause()
	spec["clip_resolved"] = "%s @ %.2f s of %.2f" % [clip, t, length]
	return ""


func _build_stage() -> void:
	we = WorldEnvironment.new()
	we.environment = Environment.new()
	root.add_child(we)
	sun = DirectionalLight3D.new()
	sun.name = "Sun"
	sun.shadow_enabled = true
	root.add_child(sun)
	var floor_mi := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(30.0, 30.0)
	floor_mi.mesh = pm
	floor_mi.material_override = _flat(STAGE_FLOOR, 0.85)
	root.add_child(floor_mi)
	var back := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 9.0
	cyl.bottom_radius = 9.0
	cyl.height = 7.0
	cyl.radial_segments = 64
	cyl.cap_top = false
	cyl.cap_bottom = false
	back.mesh = cyl
	back.position = Vector3(0.0, 3.5, 3.0)
	var bm := _flat(BACKDROP, 0.95)
	bm.cull_mode = BaseMaterial3D.CULL_FRONT
	back.material_override = bm
	# A background, not a wall: left in SDFGI, a 7 m cylinder 6-12 m away hides the sky below ~38 deg, and
	# a preset lit by its sky (overcast) rendered the figure as if in a courtyard - study_man's skin 0.33
	# display value against 0.50 with it out of GI (lookdev-overcast notebook, lookdev 0.9.0). The camera still sees it.
	back.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	root.add_child(back)
	stage_nodes = [floor_mi, back]
	cam = Camera3D.new()
	cam.name = "LookdevCloseCamera"
	root.add_child(cam)
	cam.make_current()
	label_layer = CanvasLayer.new()
	label = Label.new()
	label.position = Vector2(0, 0)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0, 0, 0, 0.55)
	sb.set_content_margin_all(6.0)
	label.add_theme_stylebox_override("normal", sb)
	label.add_theme_color_override("font_color", Color(1, 1, 1))
	label.add_theme_color_override("font_outline_color", Color.BLACK)
	label.add_theme_constant_override("outline_size", 5)
	label_layer.add_child(label)
	root.add_child(label_layer)


func _flat(c: Color, rough: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = rough
	return m


# ------------------------------------------------------------------ bones

func _bone(role: String) -> int:
	for n in ALIASES.get(role, [role]):
		var i := skel.find_bone(n)
		if i >= 0:
			return i
	return -1


func _missing(roles: Array) -> String:
	var miss := []
	for r in roles:
		if _bone(r) < 0:
			miss.append("%s (tried %s)" % [r, ", ".join(ALIASES.get(r, [r]))])
	if miss.is_empty():
		return ""
	var have := []
	for i in mini(skel.get_bone_count(), 60):
		have.append(skel.get_bone_name(i))
	return "no bone for %s; the skeleton has: %s" % ["; ".join(miss), ", ".join(have)]


## Posed world position of a bone's head.
func _p(role: String) -> Vector3:
	return skel.global_transform * skel.get_bone_global_pose(_bone(role)).origin


func _rest(role: String) -> Vector3:
	return skel.get_bone_global_rest(_bone(role)).origin


## Carries a rest-space direction through a bone's pose into world space.
func _carry(role: String, v: Vector3) -> Vector3:
	var i := _bone(role)
	var m := skel.global_transform.basis * skel.get_bone_global_pose(i).basis * skel.get_bone_global_rest(i).basis.inverse()
	return (m * v).normalized()


## The figure's forward and up at rest (left x up: glTF figures face +Z), and the eyeballs.
func _rest_frame() -> String:
	var m := _missing(["head", "hips", "upper_arm.L", "upper_arm.R"])
	if m != "":
		return m
	up_rest = (_rest("head") - _rest("hips")).normalized()
	var left := (_rest("upper_arm.L") - _rest("upper_arm.R")).normalized()
	fwd_rest = left.cross(up_rest).normalized()
	up_rest = fwd_rest.cross(left).normalized()
	_find_eyes()
	return ""


## Eyeball centres from the mesh: the vertices of a surface whose material is sclera (or "eye", not
## lashes or brows), split left and right, in the skin's bind space of the head bone.
func _find_eyes() -> void:
	var hb := _bone("head")
	for mi in model.find_children("*", "MeshInstance3D", true, false):
		var mesh := (mi as MeshInstance3D).mesh
		if mesh == null:
			continue
		var pick := -1
		for s in mesh.get_surface_count():
			var mat := mesh.surface_get_material(s)
			var nm := (mat.resource_name if mat != null else "").to_lower()
			if nm.contains("sclera"):
				pick = s
				break
			if pick < 0 and nm.contains("eye") and not nm.contains("lash") and not nm.contains("brow"):
				pick = s
		if pick < 0:
			continue
		var verts: PackedVector3Array = mesh.surface_get_arrays(pick)[Mesh.ARRAY_VERTEX]
		if verts.is_empty():
			continue
		# into skeleton rest space: the skin's bind pose for the head maps rest space to bone space,
		# so bone rest * bind = mesh -> skeleton rest
		var to_rest := Transform3D.IDENTITY
		var skin := (mi as MeshInstance3D).skin
		if skin != null:
			for b in skin.get_bind_count():
				var bn := skin.get_bind_name(b)
				var bi := skel.find_bone(bn) if bn != "" else skin.get_bind_bone(b)
				if bi == hb:
					to_rest = skel.get_bone_global_rest(hb) * skin.get_bind_pose(b)
					break
		var left := (_rest("upper_arm.L") - _rest("upper_arm.R")).normalized()
		var mid := Vector3.ZERO
		for v in verts:
			mid += to_rest * v
		mid /= verts.size()
		var sides := [[], []]
		for v in verts:
			var p: Vector3 = to_rest * v
			sides[0 if (p - mid).dot(left) > 0.0 else 1].append(p)
		if sides[0].is_empty() or sides[1].is_empty():
			continue
		var centres := []
		for s in sides:
			var box := AABB(s[0], Vector3.ZERO)
			for p in s:
				box = box.expand(p)
			centres.append(box.get_center())
		eyes_rest = centres
		eyes_bone = hb
		return


## Posed eyeball centres [left, right], or [] when the mesh has none.
func _eyes() -> Array:
	if eyes_rest.is_empty():
		return []
	var carry := skel.global_transform * skel.get_bone_global_pose(eyes_bone) * skel.get_bone_global_rest(eyes_bone).affine_inverse()
	return [carry * (eyes_rest[0] as Vector3), carry * (eyes_rest[1] as Vector3)]


# ------------------------------------------------------------------ aiming

## {view, distance, target, dir, frame (m across the tile), near, body (target must be on the figure),
##  anchors: {name: world pos}} or {error}.
func _aim(v: Dictionary) -> Dictionary:
	var view := str(v.get("view", ""))
	var dist := float(v.get("distance", 1.0))
	if dist <= 0.05:
		return {"error": "distance %.2f m is too close" % dist}
	# The body's facing on the ground: a crouch or a run leans the chest forward, and a camera that
	# followed that lean for the feet or the full body would end up under the floor.
	var fwd := _carry("chest" if _bone("chest") >= 0 else "hips", fwd_rest)
	var flat := Vector3(fwd.x, 0.0, fwd.z)
	if flat.length() < 0.2:
		flat = _carry("hips", fwd_rest)
		flat.y = 0.0
	fwd = flat.normalized() if flat.length() > 1e-3 else Vector3.BACK
	var up := Vector3.UP
	var a := {"view": view, "distance": dist, "near": 0.05, "body": true, "anchors": {},
		"aim_offset": v.get("aim_offset", []), "pair": v.get("pair", {})}
	if view.begins_with("bone:"):
		var bn := view.substr(5)
		if skel.find_bone(bn) < 0:
			return {"error": "no bone '%s' in the skeleton (%d bones; e.g. %s)" % [bn, skel.get_bone_count(),
				", ".join(_some_bones(12))]}
		a["target"] = skel.global_transform * skel.get_bone_global_pose(skel.find_bone(bn)).origin
		a["dir"] = fwd
		a["frame"] = float(v.get("size", 0.3))
		a["body"] = false
		a["anchors"][bn] = a["target"]
		return _finish(a)
	match view:
		"face", "eyes", "face_3q", "head_side", "head_back":
			var m := _missing(["head", "neck"])
			if m != "":
				return {"error": m}
			var h := _head(view)
			var hf: Vector3 = h["hf"]
			var hu: Vector3 = h["hu"]
			var hl: Vector3 = h["hl"]
			var centre: Vector3 = h["centre"]
			var ipd: float = h["ipd"]
			var e: Array = h["eyes"]
			if not e.is_empty():
				a["anchors"]["eye.L"] = e[0]
				a["anchors"]["eye.R"] = e[1]
			a["anchors"]["head"] = _p("head")
			a["anchors"]["head_mid"] = h["mid"]
			a["subject"] = {"head": h["mid"]}
			a["dir"] = hf
			up = hu
			match view:
				"face":
					a["target"] = centre - hu * ipd * 0.35 + hf * ipd * 0.2
					a["frame"] = ipd * 4.4
				"face_3q":
					a["target"] = centre - hu * ipd * 0.2
					a["dir"] = (hf + hl).normalized()
					a["frame"] = ipd * 4.8
				"eyes":
					a["target"] = centre + hf * ipd * 0.2
					a["frame"] = ipd * 2.4
					if not e.is_empty():
						a["subject"] = {"eye.L": e[0], "eye.R": e[1]}
				_:
					# the whole head and whatever hangs off it: from the neck's base to a head height above
					# the eyes (a bun or a tail behind is inside the frame)
					var top: Vector3 = h["top"]
					var bottom := _p("neck") - hu * ipd * 0.8
					a["target"] = (top + bottom) * 0.5 - hf * ipd * 0.6
					a["frame"] = (top - bottom).length() * 1.25
					a["dir"] = hl if view == "head_side" else -hf
		"hand_palm.L", "hand_palm.R", "hand_back.L", "hand_back.R":
			var s := view.substr(view.length() - 1)
			var roles := ["hand." + s, "f_index.01." + s, "f_middle.01." + s, "f_middle.03." + s, "f_pinky.01." + s]
			var m := _missing(roles)
			if m != "":
				return {"error": m}
			var wrist := _p("hand." + s)
			var knuckle := _p("f_middle.01." + s)
			var mid3 := _p("f_middle.03." + s)
			var tip := mid3 + (mid3 - _p("f_middle.01." + s)).normalized() * wrist.distance_to(knuckle) * 0.3
			var along := (knuckle - wrist).normalized()
			var across := (_p("f_index.01." + s) - _p("f_pinky.01." + s)).normalized()
			# left hand: palm = along x across; the right hand is its mirror image
			var palm := along.cross(across).normalized() * (1.0 if s == "L" else -1.0)
			var toward := palm if view.begins_with("hand_palm") else -palm
			a["dir"] = (toward + fwd * (0.6 if view.begins_with("hand_palm") else 0.25)).normalized()
			a["target"] = (wrist + tip) * 0.5
			a["frame"] = wrist.distance_to(tip) * 1.3
			# the hand hangs by the thigh: clip whatever is nearer the camera than the hand itself
			a["near"] = maxf(0.05, dist - wrist.distance_to(tip) * 0.35)
			a["anchors"] = {"wrist": wrist, "knuckle": knuckle, "tip": tip}
			a["subject"] = a["anchors"]
			a["slab"] = wrist.distance_to(tip) * 0.4
			up = along * -1.0
		"feet":
			var m := _missing(["foot.L", "foot.R", "toe.L", "toe.R"])
			if m != "":
				return {"error": m}
			var pts := [_p("foot.L"), _p("foot.R"), _p("toe.L"), _p("toe.R")]
			var box := AABB(pts[0], Vector3.ZERO)
			for p in pts:
				box = box.expand(p)
			var foot_len := (_p("foot.L") as Vector3).distance_to(_p("toe.L")) * 1.6
			var c := box.get_center()
			c.y = maxf(0.0, box.position.y) * 0.5 + 0.03
			a["target"] = c
			a["frame"] = maxf(box.size.x, box.size.z) + foot_len
			a["dir"] = (fwd + Vector3.UP * 0.7).normalized()
			a["body"] = false
			a["anchors"] = {"foot.L": pts[0], "foot.R": pts[1], "toe.L": pts[2], "toe.R": pts[3]}
		"bust":
			var m := _missing(["upper_arm.L", "upper_arm.R"])
			if m != "":
				return {"error": m}
			var l := _p("upper_arm.L")
			var r := _p("upper_arm.R")
			var w := l.distance_to(r)
			a["target"] = (l + r) * 0.5 - _carry("chest" if _bone("chest") >= 0 else "hips", up_rest) * w * 0.35 + fwd * w * 0.3
			a["frame"] = w * 1.5
			a["dir"] = fwd
			a["anchors"] = {"upper_arm.L": l, "upper_arm.R": r}
		"crotch":
			var m := _missing(["thigh.L", "thigh.R"])
			if m != "":
				return {"error": m}
			var l := _p("thigh.L")
			var r := _p("thigh.R")
			a["target"] = (l + r) * 0.5 - Vector3.UP * l.distance_to(r) * 0.4
			a["frame"] = l.distance_to(r) * 2.8
			a["dir"] = (fwd - Vector3.UP * 0.1).normalized()
			a["body"] = false
			a["anchors"] = {"thigh.L": l, "thigh.R": r}
		"full":
			var box := AABB(_p("hips"), Vector3.ZERO)
			for i in skel.get_bone_count():
				var bn := skel.get_bone_name(i)
				if bn.begins_with("ft_") or bn == "root":
					continue            # follow-through's jiggle and strand bones hang off the body; a
										# root bone can sit under the floor in a crouch
				box = box.expand(skel.global_transform * skel.get_bone_global_pose(i).origin)
			var top := box.end.y
			var e := _eyes()
			if not e.is_empty():
				top = maxf(top, ((e[0] as Vector3).y + (e[1] as Vector3).y) * 0.5 + (e[0] as Vector3).distance_to(e[1]) * 2.1)
			var bottom := minf(box.position.y, 0.0)
			a["target"] = Vector3(box.get_center().x, (top + bottom) * 0.5, box.get_center().z)
			a["frame"] = (top - bottom) * 1.1
			a["dir"] = (fwd + Vector3.UP * 0.05).normalized()
			a["body"] = false
			a["anchors"] = {"top": Vector3(box.get_center().x, top, box.get_center().z),
				"bottom": Vector3(box.get_center().x, bottom, box.get_center().z)}
			# the subject is the whole figure: the top of the head and both feet must be in the picture,
			# and the head's box (checked against the label band) is its eyes, crown, chin and ears
			a["subject"] = {}
			if _missing(["neck"]) == "":
				var h := _head(view)
				var c: Vector3 = h["centre"]
				var ipd: float = h["ipd"]
				var hu: Vector3 = h["hu"]
				var hl: Vector3 = h["hl"]
				a["subject"]["head_top"] = h["top"]
				a["head_box"] = [h["top"], c - hu * ipd * 1.9, c + hl * ipd * 1.3, c - hl * ipd * 1.3]
			for role in ["toe.L", "toe.R", "foot.L", "foot.R"]:
				if _bone(role) >= 0:
					a["subject"][role] = _p(role)
			a["cut"] = true
		_:
			return {"error": "unknown view '%s' (views: %s, or bone:<name>)" % [view, ", ".join(VIEW_NAMES)]}
	a["up"] = up
	return _finish(a)


func _finish(a: Dictionary) -> Dictionary:
	var dist: float = a["distance"]
	if not a.has("slab"):
		a["slab"] = float(a["frame"]) * 0.5
	if not a.has("subject"):
		a["subject"] = a["anchors"]
	# the control: the camera moves, the subject the checks look for does not
	var off: Array = a.get("aim_offset", [])
	if off.size() == 3:
		a["target"] = (a["target"] as Vector3) + Vector3(float(off[0]), float(off[1]), float(off[2]))
	a["fov"] = rad_to_deg(2.0 * atan(float(a["frame"]) * 0.5 / dist))
	a["eye"] = (a["target"] as Vector3) + (a["dir"] as Vector3) * dist
	if not a.has("up"):
		a["up"] = Vector3.UP
	return a


## The head's frame and size: forward, up and left (hu x hf, +X for a glTF figure facing +Z, as
## closeups._aim's `hl`), the eyes' centre and spacing (from the eyeballs, else placed from the head bone),
## the crown (a head height above the eyes) and the head's middle, a little above the eye line: where
## closeups._aim's head-bone midpoint lands on MPFB bodies (Blender face tile subject_off 0.169). The
## head bone's tail is not in a glb, so it cannot be taken from the bone.
func _head(view: String) -> Dictionary:
	var hf := _carry("head", fwd_rest)
	var hu := _carry("head", up_rest)
	var e := _eyes()
	var centre: Vector3
	var ipd: float
	if e.is_empty():
		# no eye surface: the eyes sit about one neck length above the head bone's head
		var nl := _p("head").distance_to(_p("neck"))
		centre = _p("head") + hu * nl * 0.9 + hf * nl * 0.7
		ipd = 0.063 * _scale()
		notes.append("%s: no sclera/eye surface in the mesh, eyes placed from the head bone" % view)
	else:
		centre = ((e[0] as Vector3) + (e[1] as Vector3)) * 0.5
		ipd = (e[0] as Vector3).distance_to(e[1])
	var top := centre + hu * ipd * 2.3
	return {"hf": hf, "hu": hu, "hl": hu.cross(hf).normalized(), "eyes": e, "centre": centre, "ipd": ipd,
		"top": top, "mid": centre + hu * ipd * 0.4}


func _scale() -> float:
	var h := float(manifest.get("height_m", {}).get("stand", 1.7))
	return h / 1.7


func _some_bones(n: int) -> PackedStringArray:
	var out := PackedStringArray()
	for i in mini(n, skel.get_bone_count()):
		out.append(skel.get_bone_name(i))
	return out


# ------------------------------------------------------------------ rendering

func _render_tile(a: Dictionary, preset: String, warmup: int) -> Dictionary:
	var up: Vector3 = a["up"]
	var dir: Vector3 = a["dir"]
	if absf(dir.dot(up.normalized())) > 0.95:
		up = Vector3.FORWARD
	cam.near = float(a["near"])
	cam.far = 200.0
	cam.fov = clampf(float(a["fov"]), 1.0, 120.0)
	cam.look_at_from_position(a["eye"], a["target"], up)
	_target = a["target"]
	var inside := str(spec.get("label", "above")) == "inside"
	var text := "Godot  %s   %.2f m   %s   fov %.1f°\n%s" % [a["view"], a["distance"], preset, cam.fov, spec.get("clip_resolved", "rest pose")]
	if inside:
		label.text = text
		# sized against the visible rect: a project's stretch mode scales the canvas to the window
		label.add_theme_font_size_override("font_size", maxi(12, int(root.get_visible_rect().size.y * 0.03)))
		label_layer.visible = true
	else:
		label_layer.visible = false
		_band(text, maxi(12, int(root.size.y * 0.03)))
	for i in warmup + int(spec.get("view_frames", 24)):
		await process_frame
	await RenderingServer.frame_post_draw
	var img := root.get_texture().get_image()
	img.convert(Image.FORMAT_RGBA8)
	var pic := Vector2(img.get_width(), img.get_height())
	var vis := root.get_visible_rect().size
	var to_px := Vector2(pic.x / vis.x, pic.y / vis.y)       # visible-rect coordinates -> picture pixels
	# the label band in picture pixels: above the picture (y < 0), or over its top-left corner
	var band := Rect2(0, -band_px, pic.x, band_px)
	if inside:
		var r := label.get_global_rect()
		band = Rect2(r.position * to_px, r.size * to_px)
	var tile_img := img
	if not inside:
		var bimg := band_vp.get_texture().get_image()
		bimg.convert(Image.FORMAT_RGBA8)
		tile_img = Image.create(img.get_width(), img.get_height() + band_px, false, Image.FORMAT_RGBA8)
		tile_img.blit_rect(bimg, Rect2i(0, 0, mini(bimg.get_width(), img.get_width()), mini(bimg.get_height(), band_px)), Vector2i.ZERO)
		tile_img.blit_rect(img, Rect2i(Vector2i.ZERO, img.get_size()), Vector2i(0, band_px))
	var name := "%s_%s" % [preset, str(a["view"]).replace(":", "-")]
	var path := out_dir.path_join(name + ".png")
	var failures := PackedStringArray()
	if tile_img.save_png(path) != OK:
		failures.append("cannot save %s" % path)
	var mask := await _figure_mask()
	_save_mask(mask, out_dir.path_join(name + "_mask.png"))
	var cov := _share(mask)
	var min_cov := float(spec.get("min_coverage", 0.03))
	if cov < min_cov:
		failures.append("EMPTY_TILE: the figure covers %.1f%% of the tile (min %.1f%%)" % [100.0 * cov, 100.0 * min_cov])
	# The subject alone: only what lies within `slab` of the target's depth (near and far planes moved in
	# around it), so the thigh behind a hand or the body behind a face does not count as the subject.
	var subject := await _figure_mask(float(a["slab"]))
	_save_mask(subject, out_dir.path_join(name + "_subject.png"))
	var sub := _share(subject)
	var min_sub := float(spec.get("min_subject", 0.08))
	if a["body"] and sub < min_sub:
		failures.append("SUBJECT_SMALL: the %s covers %.1f%% of its tile (min %.1f%%)" % [a["view"], 100.0 * sub, 100.0 * min_sub])

	# The view's own subject points (not the camera's target, which aim_offset moves): where they land.
	var uvs := {}
	var behind := PackedStringArray()
	var cen := Vector2.ZERO
	for k in a["subject"]:
		var p: Vector3 = a["subject"][k]
		# behind the camera's eye, not its near plane: a hand view's near plane is pulled up to the hand
		if -(cam.global_transform.affine_inverse() * p).z <= 0.0:
			behind.append(k)
			continue
		var uv := cam.unproject_position(p) / vis
		uvs[k] = [snappedf(uv.x, 0.001), snappedf(uv.y, 0.001)]
		cen += uv
	var n_in := uvs.size()
	var off := INF
	if n_in > 0:
		cen /= n_in
		off = maxf(absf(cen.x - 0.5), absf(cen.y - 0.5))
	var on_body := true
	if not behind.is_empty():
		failures.append("OFF_TARGET: %s behind the camera (%s)" % [", ".join(behind), a["view"]])
	elif a.get("cut", false):
		var cut := PackedStringArray()
		for k in uvs:
			var u: Array = uvs[k]
			if u[0] < CUT_MARGIN or u[0] > 1.0 - CUT_MARGIN or u[1] < CUT_MARGIN or u[1] > 1.0 - CUT_MARGIN:
				cut.append("%s at (%.2f, %.2f)" % [k, u[0], u[1]])
		if not cut.is_empty():
			failures.append("SUBJECT_CUT: %s outside the picture" % ", ".join(cut))
	elif n_in > 0:
		if off > CENTRAL:
			failures.append("OFF_TARGET: the %s's subject (%s) centres %.2f from the tile's centre (max %.2f)" % [
				a["view"], ", ".join(uvs.keys()), off, CENTRAL])
		elif a["body"]:
			on_body = _mask_at(mask, cen * vis)
			if not on_body:
				failures.append("OFF_TARGET: the figure does not cover the %s's subject at (%.2f, %.2f)" % [a["view"], cen.x, cen.y])

	# The head against the label band (full): its projected box in picture pixels.
	var head_box := []
	var clear := true
	if a.has("head_box"):
		var hb := Rect2()
		var first := true
		for p in a["head_box"]:
			var q: Vector2 = cam.unproject_position(p) * to_px
			if first:
				hb = Rect2(q, Vector2.ZERO)
				first = false
			else:
				hb = hb.expand(q)
		head_box = [snappedf(hb.position.x, 0.1), snappedf(hb.position.y, 0.1), snappedf(hb.end.x, 0.1), snappedf(hb.end.y, 0.1)]
		clear = not hb.intersects(band)
		if not clear:
			failures.append("LABEL_OVER_HEAD: the head (px %s) is under the label band (px %s)" % [
				head_box, [band.position.x, band.position.y, band.end.x, band.end.y]])
	var anchors := {}
	for k in a["anchors"]:
		anchors[k] = Common.vec3_json(a["anchors"][k])
	return {
		"view": a["view"], "preset": preset, "distance_m": a["distance"], "fov_deg": snappedf(cam.fov, 0.01),
		"frame_m": snappedf(float(a["frame"]), 0.001), "near_m": snappedf(cam.near, 0.001),
		"eye": Common.vec3_json(a["eye"]), "target": Common.vec3_json(a["target"]),
		"aim_offset": a.get("aim_offset", []),
		"anchors": anchors, "figure_coverage": snappedf(cov, 0.001), "subject_coverage": snappedf(sub, 0.001),
		"min_subject": min_sub, "slab_m": snappedf(float(a["slab"]), 0.001),
		"subject_uv": uvs, "subject_off": snappedf(off, 0.001) if n_in > 0 else null,
		"subject_behind": behind, "subject_on_figure": on_body,
		"label": "inside" if inside else "above",
		"band_px": [snappedf(band.position.x, 0.1), snappedf(band.position.y, 0.1), snappedf(band.end.x, 0.1), snappedf(band.end.y, 0.1)],
		"head_box_px": head_box, "label_clear_of_head": clear,
		"picture_px": [int(pic.x), int(pic.y)],
		"file": path, "failures": failures,
	}


## The label band above a tile: its text drawn in its own SubViewport, the width of the picture.
func _band(text: String, font_size: int) -> void:
	if band_vp == null:
		band_vp = SubViewport.new()
		band_vp.disable_3d = true
		band_vp.transparent_bg = false
		band_vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		var bg := ColorRect.new()
		bg.color = Color(0.10, 0.11, 0.12)
		bg.size = Vector2(4096, 512)
		band_vp.add_child(bg)
		band_label = Label.new()
		band_label.position = Vector2(8, 4)
		band_label.add_theme_color_override("font_color", Color(1, 1, 1))
		band_vp.add_child(band_label)
		root.add_child(band_vp)
	band_label.add_theme_font_size_override("font_size", font_size)
	band_label.text = text
	var font := band_label.get_theme_font("font")
	band_px = int(ceil(font.get_height(font_size) * 2.0 + 10.0))
	band_vp.size = Vector2i(root.size.x, band_px)


const MASK_W := 128


## 1 where the figure is, from two unshaded renders with the stage and the label hidden over a magenta
## and then a green background: pixels that change are not the figure.
func _figure_mask(slab := 0.0) -> PackedByteArray:
	var env := we.environment
	var near := cam.near
	var far := cam.far
	if slab > 0.0:
		var depth: float = -(cam.global_transform.affine_inverse() * _target).z
		cam.near = maxf(0.01, depth - slab)
		cam.far = depth + slab
	var saved := {}
	for prop in ["background_mode", "background_color", "background_energy_multiplier", "fog_enabled",
			"volumetric_fog_enabled", "glow_enabled", "tonemap_mode", "tonemap_exposure"]:
		saved[prop] = env.get(prop)
	for n in stage_nodes:
		n.visible = false
	label_layer.visible = false
	env.background_mode = Environment.BG_COLOR
	env.background_energy_multiplier = 1.0
	env.fog_enabled = false
	env.volumetric_fog_enabled = false
	env.glow_enabled = false
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	env.tonemap_exposure = 1.0
	root.debug_draw = Viewport.DEBUG_DRAW_UNSHADED
	var imgs := []
	for col in [Color(1, 0, 1), Color(0, 1, 0)]:
		env.background_color = col
		for i in 4:
			await process_frame
		await RenderingServer.frame_post_draw
		var img := root.get_texture().get_image()
		img.convert(Image.FORMAT_RGBA8)
		img.resize(MASK_W, int(round(MASK_W * float(img.get_height()) / img.get_width())), Image.INTERPOLATE_NEAREST)
		imgs.append(img)
	root.debug_draw = Viewport.DEBUG_DRAW_DISABLED
	cam.near = near
	cam.far = far
	for prop in saved:
		env.set(prop, saved[prop])
	for n in stage_nodes:
		n.visible = true
	var mask := PackedByteArray()
	var a: Image = imgs[0]
	var b: Image = imgs[1]
	mask.resize(a.get_width() * a.get_height())
	for y in a.get_height():
		for x in a.get_width():
			var p: Color = a.get_pixel(x, y)
			var q: Color = b.get_pixel(x, y)
			var d := absi(p.r8 - q.r8) + absi(p.g8 - q.g8) + absi(p.b8 - q.b8)
			mask[y * a.get_width() + x] = 1 if d < 60 else 0
	return mask


func _share(mask: PackedByteArray) -> float:
	var n := 0
	for b in mask:
		n += b
	return n / maxf(1.0, mask.size())


func _save_mask(mask: PackedByteArray, path: String) -> void:
	var h := mask.size() / MASK_W
	var img := Image.create(MASK_W, h, false, Image.FORMAT_L8)
	for y in h:
		for x in MASK_W:
			img.set_pixel(x, y, Color.WHITE if mask[y * MASK_W + x] == 1 else Color.BLACK)
	img.save_png(path)


## Whether the figure covers the mask near a screen position (a 3x3 mask-pixel window).
func _mask_at(mask: PackedByteArray, px: Vector2) -> bool:
	var w := MASK_W
	var h := mask.size() / w
	# unproject_position works in the viewport's visible rect, which a project's stretch settings can
	# make larger than the window (1152 wide in a 640 px window here).
	var vis := root.get_visible_rect().size
	var cx := int(px.x * w / vis.x)
	var cy := int(px.y * h / vis.y)
	var hits := 0
	for dy in range(-1, 2):
		for dx in range(-1, 2):
			var x := cx + dx
			var y := cy + dy
			if x >= 0 and y >= 0 and x < w and y < h and mask[y * w + x] == 1:
				hits += 1
	return hits >= 5


## One row per view, one column per preset - and, when the views carry a Blender pair, the Blender tile of
## the view in a first column - each tile with its own label band, a header over each column and a
## Blender/Godot tag in each cell. Composed from Controls in a SubViewport, so its text is real text.
## {path, size, blender (whether there is a Blender column)}.
func _sheet(tiles: Array, aims: Array, presets: Array) -> Dictionary:
	var tile := int(spec.get("sheet_tile", 384))
	var blender := false
	for a in aims:
		if not (a.get("pair", {}) as Dictionary).is_empty():
			blender = true
	var cols := presets.size() + (1 if blender else 0)
	const GAP := 4
	var header := 30
	# the cells: [row][col] -> {image, tag} or {missing}
	var grid := []
	for ai in aims.size():
		var row := []
		row.resize(cols)
		grid.append(row)
	for t in tiles:
		var img := Image.load_from_file(t["file"])
		grid[t["row"]][t["column"] + (1 if blender else 0)] = {"image": img, "tag": "Godot"}
	if blender:
		for ai in aims.size():
			var pair: Dictionary = aims[ai].get("pair", {})
			var cell := {"missing": "no Blender tile\nfor %s" % aims[ai]["view"]}
			if pair.has("file"):
				var img := Image.load_from_file(str(pair["file"]))
				if img != null and not img.is_empty():
					cell = {"image": img, "tag": "Blender"}
				else:
					cell = {"missing": "Blender tile %s\ndid not load" % str(pair["file"]).get_file()}
					notes.append("pair %s: cannot load %s" % [aims[ai]["view"], pair["file"]])
			grid[ai][0] = cell
	# row heights: each image scaled to the column width
	var heights := []
	for row in grid:
		var h := tile
		for cell in row:
			if cell != null and cell.has("image") and cell["image"] != null:
				var im: Image = cell["image"]
				h = maxi(h, int(round(tile * float(im.get_height()) / im.get_width())))
		heights.append(h)
	var total_h := header
	for h in heights:
		total_h += h + GAP
	var size := Vector2i(cols * (tile + GAP) - GAP, total_h - GAP)
	if size.y > 16384:
		notes.append("sheet %dx%d is over the 16384 px viewport limit: rendered in parts is not done, cut at 16384" % [size.x, size.y])
		size.y = 16384
	var vp := SubViewport.new()
	vp.disable_3d = true
	vp.transparent_bg = false
	vp.size = size
	vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	var bg := ColorRect.new()
	bg.color = Color(0.08, 0.08, 0.08)
	bg.size = Vector2(size)
	vp.add_child(bg)
	var titles := []
	if blender:
		titles.append("Blender close set (EEVEE, its own light)")
	for pn in presets:
		titles.append("Godot  " + str(pn))
	for c in cols:
		var hl := _text_label(titles[c], 17, Color(1, 1, 1))
		hl.position = Vector2(c * (tile + GAP) + 6, 4)
		vp.add_child(hl)
	var y := header
	for r in grid.size():
		for c in cols:
			var cell = grid[r][c]
			var x := c * (tile + GAP)
			if cell == null or cell.has("missing") or cell.get("image") == null:
				var box := ColorRect.new()
				box.color = Color(0.16, 0.16, 0.17)
				box.position = Vector2(x, y)
				box.size = Vector2(tile, heights[r])
				vp.add_child(box)
				var ml := _text_label(cell["missing"] if cell != null and cell.has("missing") else "no tile", 16, Color(0.75, 0.75, 0.75))
				ml.position = Vector2(x + 12, y + heights[r] * 0.45)
				vp.add_child(ml)
				continue
			var im: Image = cell["image"]
			var th := int(round(tile * float(im.get_height()) / im.get_width()))
			var scaled := im.duplicate() as Image
			scaled.resize(tile, th, Image.INTERPOLATE_LANCZOS)
			var tr := TextureRect.new()
			tr.texture = ImageTexture.create_from_image(scaled)
			tr.position = Vector2(x, y)
			tr.size = Vector2(tile, th)
			vp.add_child(tr)
			# the tag, bottom-right of the cell: which renderer made this tile
			var tag := _text_label(cell["tag"], 15, Color(1, 1, 1), Color(0.55, 0.2, 0.1, 0.85) if cell["tag"] == "Blender" else Color(0.1, 0.3, 0.55, 0.85))
			tag.position = Vector2(x + tile - 8 - tag.get_combined_minimum_size().x, y + th - 8 - tag.get_combined_minimum_size().y)
			vp.add_child(tag)
		y += heights[r] + GAP
	root.add_child(vp)
	for i in 3:
		await process_frame
	await RenderingServer.frame_post_draw
	var out := vp.get_texture().get_image()
	vp.queue_free()
	var path := out_dir.path_join("sheet.png")
	if out == null or out.save_png(path) != OK:
		return {"path": "", "size": [size.x, size.y], "blender": blender}
	return {"path": path, "size": [size.x, size.y], "blender": blender}


func _text_label(text: String, size: int, color: Color, back := Color(0, 0, 0, 0)) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	if back.a > 0.0:
		var sb := StyleBoxFlat.new()
		sb.bg_color = back
		sb.set_content_margin_all(4.0)
		l.add_theme_stylebox_override("normal", sb)
	return l
