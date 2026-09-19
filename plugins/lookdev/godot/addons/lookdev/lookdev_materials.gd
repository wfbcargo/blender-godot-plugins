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
## glint lines. Here each corner starts from its own triangle's tangent and averages the triangles meeting
## at its position mod 180 degrees, which keeps that turn and still leaves the field smooth. Done once per
## mesh resource.
##
## A preset can also carry a tiling detail normal (`lookdev.detail`): humanform's skin asks for pores this way,
## because pores (0.05-0.2 mm) are finer than any texel a body-sized map can spend. The texture is made here from
## a seeded cellular noise (so every run draws the same pores) and tiles on UV2, which humanform writes as a copy
## of the body's UV map (`hf_detail`); a mesh without UV2 gets it triplanar instead.


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
				var detail = spec.get("detail", {})
				if typeof(detail) == TYPE_DICTIONARY and not detail.is_empty():
					var has_uv2: bool = mi.mesh.surface_get_format(i) & Mesh.ARRAY_FORMAT_TEX_UV2 != 0
					set_detail(mat, detail, has_uv2)
				var alpha_spec = spec.get("alpha", {})
				if typeof(alpha_spec) == TYPE_DICTIONARY and alpha_spec.has("coverage_mips") and mat.albedo_texture != null:
					mat.albedo_texture = coverage_mips(mat.albedo_texture, float(alpha_spec["coverage_mips"]),
						float(alpha_spec.get("edge", 0.5)))
				mat.set_meta("lookdev_applied", spec.get("preset", ""))
				done.append(mat.resource_name)
		if not rebuild.is_empty() and mi.mesh is ArrayMesh and not mi.mesh.has_meta("lookdev_tangents"):
			if tangents_per_face(mi.mesh, rebuild):
				retangented.append(mi.mesh.resource_name if mi.mesh.resource_name != "" else String(mi.name))
	return {"materials": done, "skipped": skipped, "tangents_per_face": retangented}


## Per-corner tangents of a de-indexed triangle list: each triangle's direction of increasing U in its
## plane (the strand texture's across-strand axis, which is all its normal map and the anisotropy use),
## made perpendicular to each corner's normal, with a +1 sign. V takes no part: a hair shell's V runs
## away from the hairline, and where it turns (round an ear, over the crown) Mikktspace's tangents
## follow it into patches.
##
## A triangle's own tangent alone is faceted where the U field turns fast - round the axis the strands
## run to (the bun), a face turns 60-80 degrees from the next, and each flat facet catches a different
## part of the anisotropic highlight, which draws dark polygons in the sheen. So each corner averages
## the tangents of every face meeting at its position, each flipped (mod 180 degrees) onto this face's
## own first: a turn of the frame round a hole no longer cancels, while over the cap the field is
## smooth again. Where that sum collapses (the axis itself, where every direction meets) the face's own
## tangent stands.
static func strand_tangents(arrays: Array) -> PackedFloat32Array:
	var pos: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var nrm: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	var tris := pos.size() / 3
	var face_t := PackedVector3Array()
	face_t.resize(tris)
	var at_pos := {}                                     # position (0.1 mm) -> faces meeting there
	for f in tris:
		var i := f * 3
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
		if grad.length_squared() < 1e-20:
			var n0 := nrm[i]
			grad = n0.cross(Vector3.UP if absf(n0.y) < 0.9 else Vector3.RIGHT)
		face_t[f] = grad.normalized()
		for c in 3:
			var key := Vector3i((pos[i + c] * 10000.0).round())
			if not at_pos.has(key):
				at_pos[key] = []
			at_pos[key].append(f)
	var out := PackedFloat32Array()
	out.resize(pos.size() * 4)
	for f in tris:
		var i := f * 3
		var mine := face_t[f]
		for c in 3:
			var acc := Vector3.ZERO
			var share: Array = at_pos[Vector3i((pos[i + c] * 10000.0).round())]
			for g in share:
				var tg := face_t[g]
				acc += tg if tg.dot(mine) >= 0.0 else -tg
			if acc.length_squared() < 0.25 * share.size() * share.size():
				acc = mine                               # the faces meeting here point every way
			var n := nrm[i + c]
			var tv := acc - n * acc.dot(n)
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
## instance sharing the mesh gets it. Returns whether it rebuilt anything.
##
## A mesh it cannot retangent it does not touch at all. Blend shapes are the case: the rebuild is a
## de-index, and a blend shape's arrays are indexed against the surface it belongs to, so a surface with
## shapes is left as it is. Before, the teardown ran anyway - every surface was round-tripped through
## `surface_get_arrays` (which loses the LOD and shadow-mesh data the format flags do not carry), no
## tangents were built, and the mesh was still stamped `lookdev_tangents`, so a later correct pass was
## skipped. character-pipeline bakes shape keys away before export, but this is lookdev's public entry
## point and any mesh can arrive at it.
static func tangents_per_face(mesh: ArrayMesh, surfaces: Array) -> bool:
	var count := mesh.get_surface_count()
	var rebuild := []
	if mesh.get_blend_shape_count() == 0:
		for i in surfaces:
			if i is int and i >= 0 and i < count and mesh.surface_get_primitive_type(i) == Mesh.PRIMITIVE_TRIANGLES:
				rebuild.append(i)
	if rebuild.is_empty():
		return false
	var saved := []
	for i in count:
		var arrays := mesh.surface_get_arrays(i)
		var format := mesh.surface_get_format(i)
		if i in rebuild:
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
	return true


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


static var _detail_cache := {}
## What each detail spec cost to make, by its JSON: {"ms": generation time, "bytes": texture memory with mips,
## "tile_px", "albedo_mean": the detail albedo's mean multiplier on the skin's linear colour (1 = unchanged)}.
static var last_detail := {}


## A seamless pore normal map: cellular noise (distance to the nearest cell centre, so every cell centre is a
## pit) turned into a tangent-space normal map. Cached per spec, so every skin material with the same detail
## shares one texture.
##
## A spec with `coarse_cells` adds a second, coarser octave (see `_detail_maps`): pores alone (0.3 mm on the face)
## are finer than a pixel at 1 m, and box-filtered mips average them to a flat normal, so past the eyes tile they
## were gone.
static func detail_normal(d: Dictionary) -> Texture2D:
	var key := _detail_key(d)
	if _detail_cache.has(key):
		return _detail_cache[key]
	if d.has("coarse_cells"):
		return _detail_maps(d)["normal"]
	var t0 := Time.get_ticks_usec()
	var px := int(d.get("tile_px", 256))
	var noise := _pore_noise(d, px, int(d.get("seed", 0)))
	var img := noise.get_seamless_image(px, px, false, false, 0.1, true)
	img.convert(Image.FORMAT_RGBA8)
	img.bump_map_to_normal_map(float(d.get("bump", 3.0)))
	img.generate_mipmaps()
	var tex := ImageTexture.create_from_image(img)
	_detail_cache[key] = tex
	last_detail[key] = {"ms": (Time.get_ticks_usec() - t0) / 1000.0, "bytes": img.get_data().size(), "tile_px": px,
		"albedo_mean": 1.0}
	return tex


## The detail albedo: white with alpha `strength` (Godot mixes the detail normal in by that alpha), or, for a
## spec with `coarse_cells`, the coarse octave's furrows as a darkening (`cavity`).
static func detail_albedo(d: Dictionary) -> Texture2D:
	if d.has("coarse_cells"):
		return _detail_maps(d)["albedo"]
	var a := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	a.fill(Color(1, 1, 1, clampf(float(d.get("strength", 0.35)), 0.0, 1.0)))
	return ImageTexture.create_from_image(a)


static func _pore_noise(d: Dictionary, px: int, seed: int) -> FastNoiseLite:
	var noise := FastNoiseLite.new()
	noise.noise_type = FastNoiseLite.TYPE_CELLULAR
	noise.seed = seed
	noise.frequency = float(d.get("cells", 48)) / float(px)
	noise.fractal_type = FastNoiseLite.FRACTAL_NONE
	noise.cellular_return_type = FastNoiseLite.RETURN_DISTANCE
	return noise


## Two octaves in one tile, for a spec with `coarse_cells`:
## - the pores, as before: `cells` per tile of seeded cellular noise, pits at the cell centres;
## - a coarse octave (`_coarse`): `coarse_cells` per tile of larger, sparser pits of random depth, with shallow
##   furrows between them - the open pores and the micro-relief lines that still cover a pixel or two at 1 m.
##   At full body it is under a pixel and its mips average it away smoothly (it is made periodic, not
##   cross-faded like the pores, so no seam line repeats across the body).
## Height = (1 - coarse_weight) * pores + coarse_weight * coarse; the normal comes from it at `bump`. The
## albedo multiplies the skin's linear colour by 1 - cavity * (1 - coarse) / strength, so after Godot's mix
## at `strength` the coarse pits darken it by `cavity` at their deepest - which is what makes the grain show in
## diffuse light, not only in the highlights. Mips of both are box-filtered; the normal's are renormalised.
static func _detail_maps(d: Dictionary) -> Dictionary:
	var key := _detail_key(d)
	if _detail_cache.has(key + "|maps"):
		return _detail_cache[key + "|maps"]
	var t0 := Time.get_ticks_usec()
	var px := int(d.get("tile_px", 512))
	var grid := int(d.get("coarse_px", 128))
	var cells := int(d.get("coarse_cells", 16))
	var seed := 0 if bool(d.get("shared", false)) else int(d.get("seed", 0))
	var strength := clampf(float(d.get("strength", 0.35)), 0.01, 1.0)
	var wc := clampf(float(d.get("coarse_weight", 0.5)), 0.0, 1.0)
	var coarse := _coarse(grid, cells, float(d.get("pit", 0.3)), float(d.get("furrow", 0.2)),
		float(d.get("furrow_depth", 0.4)), seed + 7919)
	# height = (1 - wc) * pores + wc * coarse: the coarse octave, scaled up to the tile with alpha wc, blended over
	var cb: PackedByteArray = coarse.get_data()
	var la := PackedByteArray()
	la.resize(grid * grid * 2)
	var aw := int(round(255.0 * wc))
	for i in grid * grid:
		la[i * 2] = cb[i]
		la[i * 2 + 1] = aw
	var over := _upscale_wrapped(Image.create_from_data(grid, grid, false, Image.FORMAT_LA8, la), px)
	over.convert(Image.FORMAT_RGBA8)
	var height := _pore_noise(d, px, seed).get_seamless_image(px, px, false, false, 0.1, true)
	height.convert(Image.FORMAT_RGBA8)
	height.blend_rect(over, Rect2i(0, 0, px, px), Vector2i.ZERO)
	height.bump_map_to_normal_map(float(d.get("bump", 3.0)))
	height.generate_mipmaps(true)
	height = _fade_mips(height, float(px) / cells, [128, 128, 255, 255])
	# the albedo cavity, at the coarse octave's own size (its pits are 8 texels across there)
	var k := float(d.get("cavity", 0.0)) / strength
	var lut := PackedByteArray()
	lut.resize(256)
	var mul := PackedFloat32Array()        # the linear multiplier each coarse value stands for
	mul.resize(256)
	for v in 256:
		var m := clampf(1.0 - k * (1.0 - v / 255.0), 0.0, 1.0)
		mul[v] = m
		lut[v] = _srgb_code(m)             # a source_color texture: the sRGB code of the linear multiplier
	var a8 := int(round(255.0 * strength))
	var ab := PackedByteArray()
	ab.resize(grid * grid * 4)
	var lin_sum := 0.0
	for i in grid * grid:
		var g := lut[cb[i]]
		var j := i * 4
		ab[j] = g
		ab[j + 1] = g
		ab[j + 2] = g
		ab[j + 3] = a8
		lin_sum += mul[cb[i]]
	var mean_mul := lin_sum / (grid * grid)
	var albedo := Image.create_from_data(grid, grid, false, Image.FORMAT_RGBA8, ab)
	albedo.generate_mipmaps()
	var mc := _srgb_code(mean_mul)
	albedo = _fade_mips(albedo, float(grid) / cells, [mc, mc, mc, a8])
	var maps := {"normal": ImageTexture.create_from_image(height), "albedo": ImageTexture.create_from_image(albedo)}
	_detail_cache[key + "|maps"] = maps
	_detail_cache[key] = maps["normal"]
	last_detail[key] = {"ms": (Time.get_ticks_usec() - t0) / 1000.0, "tile_px": px, "albedo_px": grid,
		"bytes": height.get_data().size() + albedo.get_data().size(),
		# mean linear multiplier after Godot's mix at `strength`
		"albedo_mean": 1.0 - strength * (1.0 - mean_mul)}
	return maps


## The cache key of a detail spec: its JSON, without the seed when the spec is `shared` (one texture for every
## body, however many there are; the pattern tiles every 2-5 cm, so no one can tell two bodies share it).
static func _detail_key(d: Dictionary) -> String:
	if bool(d.get("shared", false)) and d.has("seed"):
		var e := d.duplicate()
		e.erase("seed")
		return JSON.stringify(e)
	return JSON.stringify(d)


static func _srgb_code(m: float) -> int:
	var s := 12.92 * m if m <= 0.0031308 else 1.055 * pow(m, 1.0 / 2.4) - 0.055
	return clampi(int(round(255.0 * s)), 0, 255)


## `img` with each mip level past the one where a coarse cell spans 3 texels faded towards `flat` (RGBA bytes):
## all the way by the level where it spans 1.5. A box-filtered mip of a pattern at 1-2 texels a cell is no longer
## its average but an aliased remnant of it, and on a body at full-body distance (mip 5) that remnant crawls as the
## camera moves: this is the shimmer a coarser octave would otherwise add. The levels a face at 1 m samples
## (mip 3, a cell over 5 texels) keep all of it.
static func _fade_mips(img: Image, cell_px: float, flat: Array) -> Image:
	var data := img.get_data()
	var w := img.get_width()
	for level in range(1, img.get_mipmap_count() + 1):
		var span := cell_px / pow(2.0, level)
		var t := clampf((span - 1.5) / 1.5, 0.0, 1.0)
		var keep := t * t * (3.0 - 2.0 * t)
		if keep >= 1.0:
			continue
		var lw := maxi(1, w >> level)
		var off := img.get_mipmap_offset(level)
		for i in lw * lw:
			var j := off + i * 4
			for c in 4:
				data[j + c] = int(round(flat[c] + (data[j + c] - flat[c]) * keep))
	return Image.create_from_data(w, img.get_height(), true, img.get_format(), data)


## The coarse octave: a periodic Voronoi pattern, `cells` x `cells` on a `grid` px tile. Each cell has a pit at its centre, `pit` of a cell in
## radius and of a random depth (0.3-1, so no two neighbours match and no lattice shows), and its borders are
## furrows `furrow` of a cell wide at `furrow_depth`. 1 is the flat skin between them, 0 the deepest point.
static func _coarse(grid: int, cells: int, pit: float, furrow: float, furrow_depth: float, seed: int) -> Image:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed
	var cs := float(grid) / cells
	var fx := PackedFloat32Array()
	var fy := PackedFloat32Array()
	var depth := PackedFloat32Array()
	fx.resize(cells * cells)
	fy.resize(cells * cells)
	depth.resize(cells * cells)
	for i in cells * cells:
		fx[i] = ((i % cells) + 0.1 + 0.8 * rng.randf()) * cs
		fy[i] = ((i / cells) + 0.1 + 0.8 * rng.randf()) * cs
		depth[i] = 0.3 + 0.7 * rng.randf()
	var bytes := PackedByteArray()
	bytes.resize(grid * grid)
	var pit_px := maxf(pit * cs, 1e-3)
	var furrow_px := maxf(furrow * cs, 1e-3)
	for y in grid:
		var cy := int(y / cs)
		var py := y + 0.5
		for x in grid:
			var cx := int(x / cs)
			var p_x := x + 0.5
			var f1 := 1e9
			var f2 := 1e9
			var q1 := 0
			for oy in range(-1, 2):
				var gy := cy + oy
				var wy := posmod(gy, cells)
				var sy := (gy - wy) * cs       # the wrapped cell's offset back into this tile's frame
				for ox in range(-1, 2):
					var gx := cx + ox
					var wx := posmod(gx, cells)
					var sx := (gx - wx) * cs
					var q := wy * cells + wx
					var dx := p_x - (fx[q] + sx)
					var dy := py - (fy[q] + sy)
					var dd := sqrt(dx * dx + dy * dy)
					if dd < f1:
						f2 = f1
						f1 = dd
						q1 = q
					elif dd < f2:
						f2 = dd
			var tp := clampf(f1 / pit_px, 0.0, 1.0)
			var tf := clampf((f2 - f1) / furrow_px, 0.0, 1.0)
			var h := 1.0 - depth[q1] * (1.0 - tp * tp * (3.0 - 2.0 * tp)) - furrow_depth * (1.0 - tf * tf * (3.0 - 2.0 * tf))
			bytes[y * grid + x] = int(round(255.0 * clampf(h, 0.0, 1.0)))
	return Image.create_from_data(grid, grid, false, Image.FORMAT_L8, bytes)


## A periodic tile scaled up to `px` (cubic), with a wrapped margin round it so the filter sees the neighbours
## across the edges and the tile still meets itself.
static func _upscale_wrapped(base: Image, px: int) -> Image:
	var grid := base.get_width()
	if px == grid:
		return base
	var m := 4
	var big := Image.create(grid + 2 * m, grid + 2 * m, false, base.get_format())
	for oy in range(-1, 2):
		for ox in range(-1, 2):
			big.blit_rect(base, Rect2i(0, 0, grid, grid), Vector2i(m + ox * grid, m + oy * grid))
	var s := float(px) / grid
	big.resize(int(round((grid + 2 * m) * s)), int(round((grid + 2 * m) * s)), Image.INTERPOLATE_CUBIC)
	return big.get_region(Rect2i(int(round(m * s)), int(round(m * s)), px, px))


## The detail layer on `mat`: the pore normal, mixed into the material's own normal map at `strength` (Godot
## mixes detail normals by the detail albedo's alpha: a white detail albedo with that alpha, multiplied in,
## leaves the colour alone), tiled `uv2_scale` times across UV2.
##
## Godot's mix is a lerp of the two maps' colours, so it also takes `strength` off the material's own normal
## map (the baked body relief): a spec with `keep_base` divides `normal_scale` by 1 - strength to give it back,
## and lifts `albedo_color` by the inverse of the cavity's mean darkening, so the baked tone stays the tone.
static func set_detail(mat: BaseMaterial3D, d: Dictionary, has_uv2 := true) -> void:
	if str(d.get("normal", "")) != "pores":
		push_warning("lookdev: %s asks for detail '%s', which this addon does not make" % [mat.resource_name, d.get("normal")])
		return
	mat.detail_enabled = true
	mat.detail_blend_mode = BaseMaterial3D.BLEND_MODE_MUL
	mat.detail_uv_layer = BaseMaterial3D.DETAIL_UV_2
	mat.detail_albedo = detail_albedo(d)
	mat.detail_normal = detail_normal(d)
	if bool(d.get("keep_base", false)):
		if mat.normal_texture != null:
			mat.normal_scale = mat.normal_scale / maxf(0.05, 1.0 - clampf(float(d.get("strength", 0.35)), 0.0, 1.0))
		# the cavity darkens on average (a detail albedo can only multiply by 1 or less): lift the base colour by
		# the inverse of that mean, in linear, so the skin keeps the tone it was baked to
		var mean := float(last_detail.get(_detail_key(d), {}).get("albedo_mean", 1.0))
		if mean > 0.5 and mean < 1.0:
			var lin := mat.albedo_color.srgb_to_linear()
			mat.albedo_color = Color(lin.r / mean, lin.g / mean, lin.b / mean, lin.a).linear_to_srgb()
	mat.normal_enabled = true
	var s := float(d.get("uv2_scale", 80.0))
	if has_uv2:
		mat.uv2_scale = Vector3(s, s, 1.0)
	else:
		# about the same pore size on a body: UV1 spans roughly 1.5 m, so s tiles per 1.5 m of surface
		mat.uv2_triplanar = true
		mat.uv2_scale = Vector3.ONE * (s / 1.5)


static var _coverage_cache := {}


## The albedo texture again, with mipmaps whose alpha keeps the share of texels at or over `cutoff` that
## the full-size image has (Castano, "Computing Alpha Mipmaps"). Box-filtered mips average a strand one
## texel wide into a grey film: past a mip or two its alpha falls under the cutoff, so a scissor material
## loses the strand (the brow thins to a few hard blocks, the hairline to a comb) and a blended one draws
## a translucent smear. Here each level's alpha is scaled so that as many texels pass the cutoff as at
## level 0 - the strands stay the same density at every distance, only wider and softer.
##
## The pixels come from the source PNG when it is on disk (the imported texture is VRAM-compressed,
## BC3's alpha steps on a hair a texel wide), else from the imported texture, decompressed. The result is
## an uncompressed ImageTexture, cached per texture and cutoff. `LookdevMaterials.last_coverage` has each
## level's measured coverage before and after, for the record.
static var last_coverage := {}


static func coverage_mips(tex: Texture2D, cutoff: float, edge := 0.5) -> Texture2D:
	var key := "%s|%s|%.3f|%.3f" % [tex.resource_path, tex.get_instance_id() if tex.resource_path == "" else 0, cutoff, edge]
	if _coverage_cache.has(key):
		return _coverage_cache[key]
	var img: Image = null
	var source := "imported"
	if tex.resource_path.get_extension().to_lower() == "png" and FileAccess.file_exists(tex.resource_path):
		img = Image.load_from_file(ProjectSettings.globalize_path(tex.resource_path))
		source = "png"
	if img == null:
		img = tex.get_image()
		if img == null:
			return tex
		if img.is_compressed():
			img.decompress()
	img.clear_mipmaps()
	img.convert(Image.FORMAT_RGBA8)
	var cut := clampi(int(round(cutoff * 255.0)), 1, 255)
	var data := img.get_data()
	var target := _share_at_or_over(data, 0, data.size(), cut)
	img.generate_mipmaps()
	data = img.get_data()
	var levels := []
	for level in range(1, img.get_mipmap_count() + 1):
		var start := img.get_mipmap_offset(level)
		var end := img.get_mipmap_offset(level + 1) if level < img.get_mipmap_count() else data.size()
		var hist := PackedInt32Array()
		hist.resize(256)
		for i in range(start + 3, end, 4):
			hist[data[i]] += 1
		var n := (end - start) / 4
		var before := 0.0
		for a in range(cut, 256):
			before += hist[a]
		before /= maxf(n, 1)
		# the lowest alpha a such that the share of texels at or over it is still at least the target
		var want := int(ceil(target * n))
		var acc := 0
		var t := 255
		while t > 0 and acc + hist[t] < want:
			acc += hist[t]
			t -= 1
		var scale := float(cut) / float(maxi(t, 1)) if want > 0 else 1.0
		if scale > 1.0:
			for i in range(start + 3, end, 4):
				data[i] = mini(255, int(data[i] * scale + 0.5))
		var after := _share_at_or_over(data, start, end, cut)
		levels.append({"level": level, "before": snappedf(before, 0.0001), "after": snappedf(after, 0.0001),
			"scale": snappedf(maxf(scale, 1.0), 0.001)})
	if edge < 0.5:
		# a blended card: alpha ramps from 0 to 1 over cutoff +- edge instead of 0..1, at every level, so a hair
		# is dark in its core and soft only at its sides (what supersampled alpha-tested hair looks like)
		var lut := PackedByteArray()
		lut.resize(256)
		for a in 256:
			lut[a] = int(round(255.0 * clampf((a / 255.0 - cutoff) / maxf(2.0 * edge, 0.001) + 0.5, 0.0, 1.0)))
		for i in range(3, data.size(), 4):
			data[i] = lut[data[i]]
	var out := Image.create_from_data(img.get_width(), img.get_height(), true, Image.FORMAT_RGBA8, data)
	var result := ImageTexture.create_from_image(out)
	result.resource_name = tex.resource_name
	last_coverage[tex.resource_path if tex.resource_path != "" else key] = {"source": source, "cutoff": cutoff, "edge": edge,
		"level0": snappedf(target, 0.0001), "levels": levels}
	_coverage_cache[key] = result
	return result


static func _share_at_or_over(data: PackedByteArray, start: int, end: int, cut: int) -> float:
	var n := 0
	var over := 0
	for i in range(start + 3, end, 4):
		n += 1
		if data[i] >= cut:
			over += 1
	return float(over) / maxf(n, 1)
