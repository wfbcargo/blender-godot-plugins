extends SoftBody3D
## A SoftBody3D built from an imported mesh and its follow-through spec.
##
## Every rule here was measured in Godot 4.7.2 with Jolt, not assumed:
##
##  - Properties are set BEFORE the node enters the tree. Under Jolt,
##    linear_stiffness, simulation_precision and shrinking_factor set afterwards
##    are silently ignored.
##  - The node's transform when it enters the tree places the points, and then
##    the node's own transform resets to identity; moving the node later teleports
##    every point. So the mesh is baked into world space, the node is top_level at
##    identity, and a moving parent cannot drag the cloth.
##  - Pins are driven by moving pinned points every physics tick with
##    PhysicsServer3D.soft_body_move_point, not by set_point_pinned's attachment
##    path. Attachments are applied from RenderingServer.frame_pre_draw, which
##    never fires headless - pins attached that way stand still in every automated
##    test - and lag one tick when it does fire.
##  - The mesh keeps an index array (a soft body without one is never added to the
##    space) and loses bones, weights and blend shapes (a blend shape count mismatch
##    fails add_surface_from_arrays).
##  - Vertices at exactly the same position are welded by Jolt, so a UV seam does
##    not tear. Each pin position pins every vertex within tolerance of it.

var spec: Dictionary
var report: Dictionary = {}
var source: MeshInstance3D

var _skeleton: Skeleton3D
var _pin_index := PackedInt32Array()     # soft body point index, one per pinned vertex
var _pin_offset: Array[Vector3] = []     # in the anchor's space
var _pin_bone := PackedInt32Array()      # bone index per pinned vertex, anchor=bone
var _anchor := "none"


static func build(src: MeshInstance3D, s: Dictionary, options := {}):
	var body = new()
	body.spec = s
	body.source = src
	body.name = String(src.name) + "_cloth"
	body._configure(options)
	src.get_parent().add_child(body)
	body._pin()
	if options.get("hide_source", true):
		src.visible = false
	return body


func _configure(options: Dictionary) -> void:
	var sb: Dictionary = spec["soft_body"]
	var overrides: Dictionary = options.get("overrides", {})
	for key in ["total_mass", "linear_stiffness", "simulation_precision", "damping_coefficient",
			"drag_coefficient", "shrinking_factor", "pressure_coefficient"]:
		var v = overrides.get(key, sb.get(key, null))
		if v == null:
			continue
		if key == "simulation_precision":
			set(key, int(v))
		else:
			set(key, float(v))
	var col: Dictionary = spec.get("collision", {})
	collision_layer = int(col.get("layer", 1))
	collision_mask = int(col.get("mask", 1))
	top_level = true
	_anchor = spec["pins"].get("anchor", "none")
	_skeleton = _find_skeleton()
	mesh = _world_mesh()
	global_transform = Transform3D.IDENTITY


func _find_skeleton() -> Skeleton3D:
	if source.skin == null:
		return null
	var sk := source.get_node_or_null(source.skeleton)
	return sk as Skeleton3D


## Where each vertex is now, in world space: skinned through the current pose
## when the source is skinned, otherwise through the node's global transform.
func _world_points(verts: PackedVector3Array, arrays: Array) -> PackedVector3Array:
	var out := PackedVector3Array()
	out.resize(verts.size())
	if _skeleton == null:
		var xf := source.global_transform
		for i in verts.size():
			out[i] = xf * verts[i]
		return out
	var src_skin := source.skin
	var bind_xf: Array[Transform3D] = []
	for b in src_skin.get_bind_count():
		var bone := src_skin.get_bind_bone(b)
		if bone < 0:
			bone = _skeleton.find_bone(src_skin.get_bind_name(b))
		var pose := _skeleton.get_bone_global_pose(bone) if bone >= 0 else Transform3D.IDENTITY
		bind_xf.append(_skeleton.global_transform * pose * src_skin.get_bind_pose(b))
	var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var per: int = bones.size() / maxi(verts.size(), 1)
	for i in verts.size():
		var p := Vector3.ZERO
		var total := 0.0
		for k in per:
			var w := weights[i * per + k]
			if w <= 0.0:
				continue
			p += (bind_xf[bones[i * per + k]] * verts[i]) * w
			total += w
		out[i] = p / total if total > 0.0 else source.global_transform * verts[i]
	return out


func _world_mesh() -> ArrayMesh:
	var src_mesh := source.mesh
	var arrays := src_mesh.surface_get_arrays(0)
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	report["vertices"] = verts.size()
	report["surfaces"] = src_mesh.get_surface_count()
	report["pins_total"] = int(spec["pins"].get("count", 0))

	var world := _world_points(verts, arrays)
	_match_pins(verts, world)

	var nbasis := source.global_transform.basis.orthonormalized()
	var out := []
	out.resize(Mesh.ARRAY_MAX)
	out[Mesh.ARRAY_VERTEX] = world
	if arrays[Mesh.ARRAY_NORMAL] != null:
		var n: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		for i in n.size():
			n[i] = (nbasis * n[i]).normalized()
		out[Mesh.ARRAY_NORMAL] = n
	for slot in [Mesh.ARRAY_TEX_UV, Mesh.ARRAY_TEX_UV2, Mesh.ARRAY_COLOR]:
		out[slot] = arrays[slot]
	if arrays[Mesh.ARRAY_INDEX] != null:
		out[Mesh.ARRAY_INDEX] = arrays[Mesh.ARRAY_INDEX]
	else:
		var idx := PackedInt32Array()
		idx.resize(verts.size())
		for i in verts.size():
			idx[i] = i
		out[Mesh.ARRAY_INDEX] = idx
	var m := ArrayMesh.new()
	m.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, out)
	var mat := source.get_active_material(0)
	if mat == null:
		mat = StandardMaterial3D.new()
	else:
		mat = mat.duplicate()
	if mat is BaseMaterial3D:
		mat.cull_mode = BaseMaterial3D.CULL_DISABLED     # cloth is seen from both sides
	m.surface_set_material(0, mat)
	return m


## Pin every vertex within tolerance of a spec pin position, and remember what it follows.
func _match_pins(verts: PackedVector3Array, world: PackedVector3Array) -> void:
	var pins: Dictionary = spec["pins"]
	var count := int(pins.get("count", 0))
	var tol := float(pins.get("tolerance", 0.0001))
	var flat: Array = pins.get("positions", [])
	var cell := maxf(tol * 4.0, 0.000001)
	var grid := {}
	for i in verts.size():
		var key := Vector3i((verts[i] / cell).floor())
		if not grid.has(key):
			grid[key] = PackedInt32Array()
		grid[key].append(i)
	var found := 0
	var bones: Array = pins.get("bones", [])
	var missing_bones := {}
	for k in count:
		var q := Vector3(flat[3 * k], flat[3 * k + 1], flat[3 * k + 2])
		var base := Vector3i((q / cell).floor())
		var hit := false
		for dx in [-1, 0, 1]:
			for dy in [-1, 0, 1]:
				for dz in [-1, 0, 1]:
					var key := base + Vector3i(dx, dy, dz)
					if not grid.has(key):
						continue
					for i in grid[key]:
						if verts[i].distance_to(q) > tol or _pin_index.has(i):
							continue
						hit = true
						_pin_index.append(i)
						var w := world[i]
						match _anchor:
							"bone":
								var bone := _bone_index(String(bones[k]))
								if bone < 0:
									missing_bones[String(bones[k])] = true
									_pin_bone.append(-1)
									_pin_offset.append(w)
								else:
									_pin_bone.append(bone)
									var bxf := _skeleton.global_transform * _skeleton.get_bone_global_pose(bone)
									_pin_offset.append(bxf.affine_inverse() * w)
							"node":
								_pin_bone.append(-1)
								_pin_offset.append(source.global_transform.affine_inverse() * w)
							_:
								_pin_bone.append(-1)
								_pin_offset.append(w)
		if hit:
			found += 1
	report["pins_found"] = found
	report["pinned_vertices"] = _pin_index.size()
	if not missing_bones.is_empty():
		report["missing_bones"] = missing_bones.keys()


## Bone by name, tolerating Godot's renaming of characters node names cannot hold.
func _bone_index(bone_name: String) -> int:
	if _skeleton == null:
		return -1
	var i := _skeleton.find_bone(bone_name)
	if i < 0:
		i = _skeleton.find_bone(bone_name.replace(".", "_"))
	return i


func _pin() -> void:
	for i in _pin_index:
		set_point_pinned(i, true)
	# with no pins there is nothing to drive
	set_physics_process(not _pin_index.is_empty())
	process_physics_priority = 100     # after controllers have moved things this tick


## Where pinned vertex `k` should be now, in world space.
func pin_target(k: int) -> Vector3:
	match _anchor:
		"bone":
			var b := _pin_bone[k]
			if b >= 0:
				return _skeleton.global_transform * _skeleton.get_bone_global_pose(b) * _pin_offset[k]
			return _pin_offset[k]
		"node":
			return source.global_transform * _pin_offset[k]
	return _pin_offset[k]


func _physics_process(_delta: float) -> void:
	var rid := get_physics_rid()
	for k in _pin_index.size():
		PhysicsServer3D.soft_body_move_point(rid, _pin_index[k], pin_target(k))


## Move the whole cloth by `delta` without it swinging - for a respawn or a teleport.
func teleport(delta: Transform3D) -> void:
	var rid := get_physics_rid()
	for i in mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX].size():
		PhysicsServer3D.soft_body_move_point(rid, i,
			delta * PhysicsServer3D.soft_body_get_point_global_position(rid, i))


func pinned_indices() -> PackedInt32Array:
	return _pin_index
