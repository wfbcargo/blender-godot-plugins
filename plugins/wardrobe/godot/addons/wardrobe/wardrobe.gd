extends RefCounted
## wardrobe runtime: put garments on a skinned body, in layers; hide what each covers; swing hems.
##
##   const Wardrobe = preload("res://addons/wardrobe/wardrobe.gd")
##   var body := preload("res://assets/wardrobe/nora.glb").instantiate()
##   add_child(body)
##   Wardrobe.equip(body, preload("res://assets/wardrobe/nora_trousers.glb"))
##   Wardrobe.equip(body, preload("res://assets/wardrobe/nora_tshirt.glb"))
##   Wardrobe.unequip(body, "Tshirt")
##
## A garment glb carries the garment mesh, its own copy of the body's rig (with its hem bones) and
## the spec Blender wrote, as node extras. `equip`:
##   1. adds the bones the body's Skeleton3D lacks, with the garment rig's rests
##   2. moves the garment mesh onto the body's skeleton - Godot binds skins by bone name
##   3. rebuilds every worn surface without what the garments over it cover: the body by the
##      spec's `hide`, an inner garment by the outer one's `hide_layers[<inner name>]`
##   4. builds a HemModifier for the hem bones (LOD 1; `hem=false` for LOD 0)
##
## Hiding is by position: Godot's importer reorders vertices, so a spec lists covered vertices as
## glTF mesh-space positions, matched here within `tolerance_m`. A triangle is dropped when all
## three of its corners are covered by one or more worn garments. Each mesh keeps the mesh it was
## imported with, so taking a garment off gives back everything it hid.

const SCHEMA := "wardrobe/1"
const HemModifier := preload("res://addons/wardrobe/hem_modifier.gd")
const FOLLOW_THROUGH := "res://addons/follow_through/follow_through.gd"

const META_SOURCE := "wardrobe_source_mesh"     # on any worn surface: its mesh as imported
const META_WORN := "wardrobe_worn"              # on the body mesh: Array of garment MeshInstance3D
const META_HIDE := "wardrobe_hide_idx"          # on a garment: body vertex indices it hides
const META_EDGE := "wardrobe_edge_idx"
const META_LAYER_HIDE := "wardrobe_layer_hide"  # on a garment: {inner garment name: PackedInt32Array}


static func spec_of(node: Node) -> Dictionary:
	if node == null or not node.has_meta("extras"):
		return {}
	var extras = node.get_meta("extras")
	if typeof(extras) != TYPE_DICTIONARY or not extras.has("wardrobe"):
		return {}
	return extras["wardrobe"]


static func validate(spec: Dictionary) -> PackedStringArray:
	var p := PackedStringArray()
	for k in ["schema", "garment", "kind", "layer", "body", "hide"]:
		if not spec.has(k):
			p.append("missing " + k)
	if spec.get("schema", "") != SCHEMA:
		p.append("schema is %s, this runtime reads %s" % [spec.get("schema", "?"), SCHEMA])
	var blocks := {"hide": spec.get("hide", {}), "edge": spec.get("edge", {})}
	for inner in spec.get("hide_layers", {}):
		blocks["hide_layers." + inner] = spec["hide_layers"][inner]
	for key in blocks:
		var blk: Dictionary = blocks[key]
		if blk.is_empty():
			continue
		if blk.get("space", "") != "gltf_mesh":
			p.append(key + ".space must be gltf_mesh")
		if Marshalls.base64_to_raw(blk.get("positions_f32", "")).size() != 12 * int(blk.get("count", 0)):
			p.append(key + ": positions do not match count")
	if spec.has("hem") and spec["hem"].get("space", "") != "gltf_armature":
		p.append("hem.space must be gltf_armature")
	return p


## The skinned body mesh under `body_root`: the one named, else the skinned mesh with the most
## vertices that is not a garment (a body glb may also carry hair and eyes).
static func body_mesh(body_root: Node, name := "") -> MeshInstance3D:
	var best: MeshInstance3D = null
	var best_n := -1
	for n in body_root.find_children("*", "MeshInstance3D", true, false):
		var mi: MeshInstance3D = n
		if mi.skin == null or mi.mesh == null or not spec_of(mi).is_empty() or mi.has_meta("wardrobe_garment"):
			continue
		if name != "" and String(mi.name) == name:
			return mi
		var src: Mesh = mi.get_meta(META_SOURCE, mi.mesh)
		var count := 0
		for s in src.get_surface_count():
			count += (src.surface_get_arrays(s)[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
		if count > best_n:
			best = mi
			best_n = count
	return best


## Put `garment` (a PackedScene, or an instantiated garment scene) on the body under `body_root`.
## options:
##   hem: bool            build the hem modifier (default true); false is LOD 0, pure skinning
##   colliders: bool      collide a skirt's or dress's hem ring with the thighs and fold it with them
##                        (default true; skirts and dresses only). false is the verifier's control
##   hide: bool           hide what it covers (default true)
##   cloth: bool          build a skirt or dress exported with soft=True as follow-through cloth (default
##                        true; needs addons/follow_through). Its `cloth` report entry is the SoftBody3D
##   overrides: Dict      hem bone parameter -> value for every bone
## Returns one report per garment mesh found; a built one carries `mesh` and `hem`.
static func equip(body_root: Node, garment, options := {}) -> Array[Dictionary]:
	var reports: Array[Dictionary] = []
	var inst: Node = garment.instantiate() if garment is PackedScene else garment
	var found := false
	for n in inst.find_children("*", "MeshInstance3D", true, false):
		var gm: MeshInstance3D = n
		var spec := spec_of(gm)
		if spec.is_empty():
			continue
		found = true
		reports.append(_equip_one(body_root, gm, spec, options))
	if not found:
		reports.append({"built": false, "problems": PackedStringArray(["no mesh with a wardrobe spec in the garment"])})
	if inst.get_parent() != null:
		inst.get_parent().remove_child(inst)
	inst.queue_free()
	return reports


static func _equip_one(body_root: Node, gm: MeshInstance3D, spec: Dictionary, options: Dictionary) -> Dictionary:
	var rep := {"garment": String(spec.get("garment", gm.name)), "kind": spec.get("kind", ""),
		"layer": int(spec.get("layer", 2)), "built": false}
	var problems := validate(spec)
	var bm := body_mesh(body_root, String(spec["body"].get("name", "")))
	if bm == null:
		problems.append("no skinned body mesh under " + String(body_root.name))
	var gskel := gm.get_node_or_null(gm.skeleton) as Skeleton3D
	if gskel == null:
		problems.append("the garment mesh has no skeleton")
	if not problems.is_empty():
		rep["problems"] = problems
		return rep
	var skel := bm.get_node(bm.skeleton) as Skeleton3D
	unequip(body_root, rep["garment"])

	# 1. bones the body lacks, parents first
	var added := 0
	var worst_rest := 0.0
	var bound := {}
	for bi in gm.skin.get_bind_count():
		bound[gm.skin.get_bind_name(bi)] = true
	var pending := range(gskel.get_bone_count())
	var guard := 0
	while not pending.is_empty() and guard < 64:
		guard += 1
		var still := []
		for i in pending:
			var bname := gskel.get_bone_name(i)
			var have := skel.find_bone(bname)
			if have >= 0:
				if bound.has(bname):          # only bones this garment is skinned to have to agree
					worst_rest = maxf(worst_rest, (skel.get_bone_global_rest(have).origin - gskel.get_bone_global_rest(i).origin).length())
				continue
			var gp := gskel.get_bone_parent(i)
			var bp := skel.find_bone(gskel.get_bone_name(gp)) if gp >= 0 else -1
			if gp >= 0 and bp < 0:
				still.append(i)
				continue
			var idx := skel.add_bone(bname)
			skel.set_bone_parent(idx, bp)
			skel.set_bone_rest(idx, gskel.get_bone_rest(i))
			skel.reset_bone_pose(idx)
			added += 1
		pending = still
	if worst_rest > 0.005:
		problems.append("the garment's rig differs from the body's: bone rests up to %.3f m apart" % worst_rest)

	# 2. the mesh onto the body's skeleton
	gm.get_parent().remove_child(gm)
	gm.owner = null
	skel.add_child(gm)
	gm.transform = bm.transform
	gm.skeleton = gm.get_path_to(skel)
	gm.set_meta("wardrobe_garment", rep["garment"])
	gm.set_meta(META_SOURCE, gm.mesh)
	var missing := 0
	for b in gm.skin.get_bind_count():
		if skel.find_bone(gm.skin.get_bind_name(b)) < 0:
			missing += 1
	if missing > 0:
		problems.append("%d skin binds name bones the body does not have" % missing)

	# 3. hide, everywhere
	var wearing: Array = bm.get_meta(META_WORN, [])
	wearing.append(gm)
	bm.set_meta(META_WORN, wearing)
	var t0 := Time.get_ticks_usec()
	gm.set_meta("wardrobe_hides", options.get("hide", true))
	rep["hide"] = _match_body(bm, gm, spec) if options.get("hide", true) else {}
	rep["body"] = refresh(bm)
	rep["equip_ms"] = snappedf((Time.get_ticks_usec() - t0) / 1000.0, 0.01)

	# 4. hem
	rep["bones_added"] = added
	rep["mesh"] = gm
	if options.get("hem", true) and spec.has("hem"):
		var hem = HemModifier.build(skel, gm, spec, options)
		rep["hem"] = hem
		rep["hem_report"] = hem.report
		problems.append_array(hem.report.get("problems", PackedStringArray()))
	# 5. cloth: a skirt or dress routed to follow-through (wardrobe.dress(..., soft=True)) carries a soft_body
	# spec beside its wardrobe one; built here it is a SoftBody3D pinned at the hips to the body's bones
	var ft_spec: Dictionary = gm.get_meta("extras", {}).get("follow_through", {}) if gm.has_meta("extras") else {}
	if options.get("cloth", true) and String(ft_spec.get("route", "")) == "soft_body":
		if ResourceLoader.exists(FOLLOW_THROUGH):
			var ft = load(FOLLOW_THROUGH)
			var problems_ft: PackedStringArray = ft.validate(ft_spec)
			if problems_ft.is_empty():
				var cloth = ft.ClothBody.build(gm, ft_spec, options)
				cloth.set_meta("wardrobe_hem_for", gm)       # unequip removes it with the garment
				rep["cloth"] = cloth
				rep["cloth_report"] = cloth.report
			else:
				problems.append_array(problems_ft)
		else:
			problems.append("%s is routed to cloth but %s is not in the project" % [rep["garment"], FOLLOW_THROUGH])
	rep["problems"] = problems
	rep["built"] = true
	return rep


## Take a garment off: its mesh and hem modifier go, whatever it hid comes back.
static func unequip(body_root: Node, garment_name: String) -> bool:
	var bm := body_mesh(body_root)
	if bm == null:
		return false
	var wearing: Array = bm.get_meta(META_WORN, [])
	var gone := false
	for gm in wearing.duplicate():
		if not is_instance_valid(gm):
			wearing.erase(gm)
			continue
		if String(gm.get_meta("wardrobe_garment", "")) == garment_name:
			var skel: Node = gm.get_parent()
			for c in skel.get_children():
				if c.has_meta("wardrobe_hem_for") and c.get_meta("wardrobe_hem_for") == gm:
					skel.remove_child(c)
					c.queue_free()
			wearing.erase(gm)
			skel.remove_child(gm)
			gm.queue_free()
			gone = true
	bm.set_meta(META_WORN, wearing)
	if gone:
		refresh(bm)
	return gone


## Names of the garments worn, innermost layer first.
static func worn_names(body_root: Node) -> PackedStringArray:
	var out := PackedStringArray()
	var bm := body_mesh(body_root)
	if bm != null:
		for gm in worn(bm):
			out.append(String(gm.get_meta("wardrobe_garment")))
	return out


## Garment meshes worn by the body mesh, innermost layer first.
static func worn(bm: MeshInstance3D) -> Array:
	var out: Array = bm.get_meta(META_WORN, []).filter(func(g): return is_instance_valid(g) and not g.is_queued_for_deletion())
	out.sort_custom(func(a, b): return int(spec_of(a).get("layer", 2)) < int(spec_of(b).get("layer", 2)))
	return out


## Rebuild the body and every worn garment without what the garments over them cover.
static func refresh(bm: MeshInstance3D) -> Dictionary:
	var garments := worn(bm)
	var body_hidden := {}
	for gm in garments:
		if gm.get_meta("wardrobe_hides", true):
			for i in gm.get_meta(META_HIDE, PackedInt32Array()):
				body_hidden[i] = true
	var out := _rebuild(bm, body_hidden)
	var layers := {}
	for inner in garments:
		var name := String(inner.get_meta("wardrobe_garment"))
		var hidden := {}
		for outer in garments:
			if outer == inner or not outer.get_meta("wardrobe_hides", true):
				continue
			var blk: Dictionary = spec_of(outer).get("hide_layers", {}).get(name, {})
			if blk.is_empty():
				continue
			var cache: Dictionary = outer.get_meta(META_LAYER_HIDE, {})
			if not cache.has(name):
				cache[name] = _match_positions(inner.get_meta(META_SOURCE, inner.mesh), blk)[0]
				outer.set_meta(META_LAYER_HIDE, cache)
			for i in cache[name]:
				hidden[i] = true
		layers[name] = _rebuild(inner, hidden)
	out["layers"] = layers
	return out


## Kept for older callers: the body and every layer.
static func refresh_body(bm: MeshInstance3D) -> Dictionary:
	return refresh(bm)


static func _match_body(bm: MeshInstance3D, gm: MeshInstance3D, spec: Dictionary) -> Dictionary:
	var src: Mesh = bm.get_meta(META_SOURCE, bm.mesh)
	var out := {"spec_body_verts": int(spec["body"].get("vertex_count", -1))}
	for key in ["hide", "edge"]:
		if not spec.has(key):
			continue
		var r := _match_positions(src, spec[key])
		gm.set_meta(META_HIDE if key == "hide" else META_EDGE, r[0])
		out[key + "_expected"] = int(spec[key].get("count", 0))
		out[key + "_matched_verts"] = (r[0] as PackedInt32Array).size()
		out[key + "_unmatched"] = r[1]
		out["body_verts"] = r[2]
	return out


## [vertex indices of `mesh` within tolerance of the block's positions, positions unmatched, vertex count]
static func _match_positions(mesh: Mesh, blk: Dictionary) -> Array:
	var verts := PackedVector3Array()
	for s in mesh.get_surface_count():
		verts.append_array(mesh.surface_get_arrays(s)[Mesh.ARRAY_VERTEX])
	var tol := float(blk.get("tolerance_m", 0.0005))
	var pts := Marshalls.base64_to_raw(blk["positions_f32"]).to_float32_array()
	var inv := 1.0 / tol
	var grid := {}
	for i in verts.size():
		var v := verts[i]
		var k := Vector3i(floori(v.x * inv), floori(v.y * inv), floori(v.z * inv))
		if grid.has(k):
			grid[k].append(i)
		else:
			grid[k] = PackedInt32Array([i])
	var idx := PackedInt32Array()
	var unmatched := 0
	for j in range(0, pts.size(), 3):
		var p := Vector3(pts[j], pts[j + 1], pts[j + 2])
		var c := Vector3i(floori(p.x * inv), floori(p.y * inv), floori(p.z * inv))
		var hit := false
		for dx in [-1, 0, 1]:
			for dy in [-1, 0, 1]:
				for dz in [-1, 0, 1]:
					var cell := c + Vector3i(dx, dy, dz)
					if grid.has(cell):
						for i in grid[cell]:
							if verts[i].distance_to(p) <= tol:
								idx.append(i)
								hit = true
		if not hit:
			unmatched += 1
	return [idx, unmatched, verts.size()]


## Give `mi` its source mesh without the triangles whose three corners are in `hidden`.
static func _rebuild(mi: MeshInstance3D, hidden: Dictionary) -> Dictionary:
	if not mi.has_meta(META_SOURCE):
		mi.set_meta(META_SOURCE, mi.mesh)
	var src: Mesh = mi.get_meta(META_SOURCE)
	if hidden.is_empty():
		mi.mesh = src
		return {"tris_hidden": 0, "tris_total": _tri_count(src)}
	var out := ArrayMesh.new()
	out.blend_shape_mode = src.blend_shape_mode if src is ArrayMesh else Mesh.BLEND_SHAPE_MODE_NORMALIZED
	if src is ArrayMesh:
		for b in (src as ArrayMesh).get_blend_shape_count():
			out.add_blend_shape((src as ArrayMesh).get_blend_shape_name(b))
	var base := 0
	var dropped := 0
	var total := 0
	for s in src.get_surface_count():
		var arrays := src.surface_get_arrays(s)
		var n: int = arrays[Mesh.ARRAY_VERTEX].size()
		var index: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null else PackedInt32Array(range(n))
		var kept := PackedInt32Array()
		kept.resize(index.size())
		var w := 0
		for t in range(0, index.size(), 3):
			var a := index[t]
			var b := index[t + 1]
			var c := index[t + 2]
			total += 1
			if hidden.has(a + base) and hidden.has(b + base) and hidden.has(c + base):
				dropped += 1
				continue
			kept[w] = a
			kept[w + 1] = b
			kept[w + 2] = c
			w += 3
		kept.resize(w)
		arrays[Mesh.ARRAY_INDEX] = kept
		var flags := 0
		if src.surface_get_format(s) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS:
			flags |= Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS
		var shapes := src.surface_get_blend_shape_arrays(s) if src is ArrayMesh else []
		if w > 0:
			out.add_surface_from_arrays(src.surface_get_primitive_type(s), arrays, shapes, {}, flags)
			out.surface_set_material(out.get_surface_count() - 1, src.surface_get_material(s))
		base += n
	mi.mesh = out
	return {"tris_hidden": dropped, "tris_total": total}


static func _tri_count(m: Mesh) -> int:
	var t := 0
	for s in m.get_surface_count():
		var a := m.surface_get_arrays(s)
		t += (a[Mesh.ARRAY_INDEX].size() if a[Mesh.ARRAY_INDEX] != null else a[Mesh.ARRAY_VERTEX].size()) / 3
	return t
