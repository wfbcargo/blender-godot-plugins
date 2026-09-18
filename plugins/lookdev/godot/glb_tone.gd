extends SceneTree
## lookdev tone: the mean albedo of each material in a glb, over the texels its UVs actually cover.
## Headless; driven by `bin/lookdev.mjs tone`.
##
##   godot --headless --path <project> --script <this> -- --glb <file.glb> [--material skin] \
##         [--size 256] [--expect 0.86,0.68,0.57] [--out tone.json]
##   godot --headless --path <project> --script <this> -- --selftest --out-dir <dir>
##
## A texture's plain mean is wrong for a character: UV islands cover maybe 60% of the image, and the
## padding between them is whatever the baker left (often black). So the triangles of every surface that
## uses the material are rasterised into a coverage mask at `size` px, and only covered texels count.
## Each texel is linearised (albedo is sRGB) and multiplied by the material's base colour factor.
##
## ok = the covered mean's linear luminance is within [LUMA_MIN, LUMA_MAX] and the coverage is not empty.
## Real dielectrics sit between about 0.03 (charcoal) and 0.9 (fresh snow) linear; black hair and pupils go
## down to about 0.01, so under 0.03 is only a note ("dark") and under 0.01 is not ok. A black albedo -
## last round's baked skin that came out pure black while its own check said tone_ok - reads about 0.0 and
## is not ok. With --expect (an sRGB colour, as a brief's `skin`) it also reports the difference.
##
## --selftest writes two one-quad glbs into --out-dir, a black albedo and an 18% grey one, and checks
## that the first is not ok and the second reads 0.18 +/- 0.01 linear: the control.

const LUMA_MIN := 0.01
## Under this a material is reported "dark": right for hair, pupils and charcoal, wrong for skin.
const LUMA_DARK := 0.03
const LUMA_MAX := 0.9

var out := ""


func _initialize() -> void:
	var args := {}
	var a := OS.get_cmdline_user_args()
	var i := 0
	while i < a.size():
		var k: String = a[i]
		if k.begins_with("--"):
			if i + 1 < a.size() and not str(a[i + 1]).begins_with("--"):
				args[k.substr(2)] = a[i + 1]
				i += 2
				continue
			args[k.substr(2)] = true
		i += 1
	out = str(args.get("out", ""))
	if args.has("selftest"):
		quit(_selftest(str(args.get("out-dir", OS.get_user_data_dir()))))
		return
	var glb := str(args.get("glb", ""))
	if glb == "":
		_emit("error", {"message": "no --glb given"})
		quit(2)
		return
	var expect: Variant = null
	if args.has("expect"):
		var parts := str(args["expect"]).split(",")
		if parts.size() == 3:
			expect = Color(float(parts[0]), float(parts[1]), float(parts[2]))
	var rep := probe(glb, str(args.get("material", "")), int(args.get("size", 256)), expect)
	_write(rep)
	if rep.has("error"):
		_emit("error", {"message": rep["error"]})
		quit(2)
		return
	_emit("done", {"ok": rep["ok"], "out": out})
	quit(0 if rep["ok"] else 1)


func _emit(kind: String, data: Dictionary) -> void:
	var d := data.duplicate()
	d["type"] = kind
	print("LOOKDEV " + JSON.stringify(d))


func _write(rep: Dictionary) -> void:
	var text := JSON.stringify(rep, "  ", false)
	if out == "":
		print(text)
		return
	var f := FileAccess.open(out, FileAccess.WRITE)
	if f == null:
		_emit("error", {"message": "cannot write %s: %s" % [out, error_string(FileAccess.get_open_error())]})
		return
	f.store_string(text)
	f.close()


static func srgb_to_linear(c: float) -> float:
	return c / 12.92 if c <= 0.04045 else pow((c + 0.055) / 1.055, 2.4)


static func linear_to_srgb(c: float) -> float:
	return c * 12.92 if c <= 0.0031308 else 1.055 * pow(c, 1.0 / 2.4) - 0.055


## {glb, materials: [{name, texture, texture_px, coverage, mean_linear, mean_srgb, luma_linear, ok, why}],
##  ok} - ok when every probed material is. `only` filters material names (substring, case-insensitive).
static func probe(glb: String, only := "", size := 256, expect: Variant = null) -> Dictionary:
	var file := ProjectSettings.globalize_path(glb) if glb.begins_with("res://") else glb
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	var err := doc.append_from_file(file, state)
	if err != OK:
		return {"glb": glb, "error": "cannot read %s: %s" % [file, error_string(err)], "ok": false}
	# triangles (uv) per material
	var uv_tris := {}
	for gm in state.get_meshes():
		var im: ImporterMesh = gm.mesh
		for s in im.get_surface_count():
			var mat := im.get_surface_material(s)
			if mat == null:
				continue
			var arr := im.get_surface_arrays(s)
			var uvs: Variant = arr[Mesh.ARRAY_TEX_UV]
			if uvs == null or (uvs as PackedVector2Array).is_empty():
				continue
			var idx: Variant = arr[Mesh.ARRAY_INDEX]
			if idx == null or (idx as PackedInt32Array).is_empty():
				idx = PackedInt32Array(range((uvs as PackedVector2Array).size()))
			var key := mat.resource_name
			if not uv_tris.has(key):
				uv_tris[key] = []
			uv_tris[key].append([uvs, idx])
	var mats := []
	var all_ok := true
	var seen := {}
	for mat in state.get_materials():
		if not mat is BaseMaterial3D or seen.has(mat.resource_name):
			continue
		seen[mat.resource_name] = true
		if only != "" and not mat.resource_name.to_lower().contains(only.to_lower()):
			continue
		var m := _probe_material(mat as BaseMaterial3D, uv_tris.get(mat.resource_name, []), size)
		if expect is Color:
			var e: Color = expect
			var got: Array = m["mean_srgb"]
			m["expect_srgb"] = [e.r, e.g, e.b]
			m["delta_srgb"] = [snappedf(got[0] - e.r, 0.001), snappedf(got[1] - e.g, 0.001), snappedf(got[2] - e.b, 0.001)]
		all_ok = all_ok and m["ok"]
		mats.append(m)
	if mats.is_empty():
		return {"glb": glb, "error": "no material%s in %s" % [(" matching '%s'" % only) if only != "" else "", glb], "ok": false}
	return {"glb": glb, "size": size, "luma_range": [LUMA_MIN, LUMA_MAX], "materials": mats, "ok": all_ok}


static func _probe_material(mat: BaseMaterial3D, tris: Array, size: int) -> Dictionary:
	var factor := mat.albedo_color      # sRGB-encoded in Godot
	var lf := Color(srgb_to_linear(factor.r), srgb_to_linear(factor.g), srgb_to_linear(factor.b))
	var tex := mat.albedo_texture
	var rep := {"name": mat.resource_name, "texture": tex != null, "factor_srgb": [factor.r, factor.g, factor.b]}
	var sum := Vector3.ZERO
	var n := 0
	var coverage := 1.0
	if tex == null:
		sum = Vector3(lf.r, lf.g, lf.b)
		n = 1
		rep["note"] = "no albedo texture: the base colour factor alone"
	else:
		var img := tex.get_image()
		if img == null:
			return {"name": mat.resource_name, "ok": false, "why": "albedo texture has no image data"}
		rep["texture_px"] = [img.get_width(), img.get_height()]
		if img.is_compressed():
			img.decompress()
		img.convert(Image.FORMAT_RGBA8)
		# box-filter down (each halving averages 2x2), then land on size x size
		while img.get_width() >= size * 2 and img.get_height() >= size * 2:
			img.shrink_x2()
		img.resize(size, size, Image.INTERPOLATE_BILINEAR)
		var mask := _coverage(tris, size)
		var covered := 0
		var lut := PackedFloat32Array()
		lut.resize(256)
		for k in 256:
			lut[k] = srgb_to_linear(k / 255.0)
		for y in size:
			for x in size:
				if mask[y * size + x] == 0:
					continue
				covered += 1
				var c := img.get_pixel(x, y)
				sum += Vector3(lut[c.r8] * lf.r, lut[c.g8] * lf.g, lut[c.b8] * lf.b)
		n = covered
		coverage = covered / float(size * size)
		if tris.is_empty():
			rep["note"] = "no surface with UVs uses this material"
	rep["coverage"] = snappedf(coverage, 0.0001)
	if n == 0:
		rep["ok"] = false
		rep["why"] = "no covered texels: the UVs cover nothing"
		return rep
	var mean := sum / n
	var luma := 0.2126 * mean.x + 0.7152 * mean.y + 0.0722 * mean.z
	rep["mean_linear"] = [snappedf(mean.x, 0.0001), snappedf(mean.y, 0.0001), snappedf(mean.z, 0.0001)]
	rep["mean_srgb"] = [snappedf(linear_to_srgb(mean.x), 0.001), snappedf(linear_to_srgb(mean.y), 0.001), snappedf(linear_to_srgb(mean.z), 0.001)]
	rep["luma_linear"] = snappedf(luma, 0.0001)
	rep["ok"] = luma >= LUMA_MIN and luma <= LUMA_MAX
	if rep["ok"] and luma < LUMA_DARK:
		rep["note"] = "dark (under %.2f linear): plausible for hair, pupils or charcoal, not for skin" % LUMA_DARK
	rep["why"] = "" if rep["ok"] else ("too dark: %.4f linear (min %.2f)" % [luma, LUMA_MIN] if luma < LUMA_MIN else "too bright: %.4f linear (max %.2f)" % [luma, LUMA_MAX])
	return rep


## UV-space coverage at size x size: 1 where a triangle covers the texel centre. glTF and Godot both put
## UV (0,0) at the image's top-left.
static func _coverage(tris: Array, size: int) -> PackedByteArray:
	var mask := PackedByteArray()
	mask.resize(size * size)
	for pair in tris:
		var uvs: PackedVector2Array = pair[0]
		var idx: PackedInt32Array = pair[1]
		for t in range(0, idx.size() - 2, 3):
			var a := uvs[idx[t]] * size
			var b := uvs[idx[t + 1]] * size
			var c := uvs[idx[t + 2]] * size
			var x0 := clampi(int(floor(minf(a.x, minf(b.x, c.x)))), 0, size - 1)
			var x1 := clampi(int(ceil(maxf(a.x, maxf(b.x, c.x)))), 0, size - 1)
			var y0 := clampi(int(floor(minf(a.y, minf(b.y, c.y)))), 0, size - 1)
			var y1 := clampi(int(ceil(maxf(a.y, maxf(b.y, c.y)))), 0, size - 1)
			var area := (b - a).cross(c - a)
			if absf(area) < 1e-9:
				continue
			for y in range(y0, y1 + 1):
				for x in range(x0, x1 + 1):
					var p := Vector2(x + 0.5, y + 0.5)
					var w0 := (b - p).cross(c - p) / area
					var w1 := (c - p).cross(a - p) / area
					var w2 := 1.0 - w0 - w1
					if w0 >= -1e-4 and w1 >= -1e-4 and w2 >= -1e-4:
						mask[y * size + x] = 1
	return mask


# ------------------------------------------------------------------ control

func _selftest(dir: String) -> int:
	DirAccess.make_dir_recursive_absolute(dir)
	var fails := 0
	for case in [["black", Color8(0, 0, 0), false], ["grey18", Color8(118, 118, 118), true]]:
		var path := dir.path_join("tone_control_%s.glb" % case[0])
		var e := _write_quad(path, case[1])
		if e != "":
			_emit("error", {"message": e})
			return 2
		var rep := probe(path)
		var m: Dictionary = rep["materials"][0] if rep.has("materials") else {}
		var ok_as_expected: bool = rep.get("ok", false) == case[2]
		var luma := float(m.get("luma_linear", -1.0))
		if case[0] == "grey18":
			ok_as_expected = ok_as_expected and absf(luma - 0.18) <= 0.01
		print("TONE_SELFTEST %s %s: ok=%s luma_linear=%.4f coverage=%.3f (want ok=%s)" % [
			"ok  " if ok_as_expected else "FAIL", case[0], rep.get("ok"), luma, float(m.get("coverage", 0)), case[2]])
		if not ok_as_expected:
			fails += 1
	print("TONE_SELFTEST %s" % ("PASSED" if fails == 0 else "FAILED"))
	return 0 if fails == 0 else 1


## A quad covering the left half of UV space, textured with `colour`; the right half of the texture is
## white padding the probe must ignore.
func _write_quad(path: String, colour: Color) -> String:
	var img := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	img.fill(Color.WHITE)
	img.fill_rect(Rect2i(0, 0, 32, 64), colour)
	var mat := StandardMaterial3D.new()
	mat.resource_name = "control"
	mat.albedo_texture = ImageTexture.create_from_image(img)
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var corners := [[Vector3(0, 0, 0), Vector2(0, 1)], [Vector3(1, 0, 0), Vector2(0.5, 1)],
		[Vector3(1, 1, 0), Vector2(0.5, 0)], [Vector3(0, 1, 0), Vector2(0, 0)]]
	for k in [0, 1, 2, 0, 2, 3]:
		st.set_normal(Vector3.BACK)
		st.set_uv(corners[k][1])
		st.add_vertex(corners[k][0])
	st.set_material(mat)
	var mi := MeshInstance3D.new()
	mi.name = "Quad"
	mi.mesh = st.commit()
	var scene := Node3D.new()
	scene.name = "ToneControl"
	scene.add_child(mi)
	mi.owner = scene
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	var err := doc.append_from_scene(scene, state)
	if err == OK:
		err = doc.write_to_filesystem(state, path)
	scene.free()
	return "" if err == OK else "cannot write control glb %s: %s" % [path, error_string(err)]
