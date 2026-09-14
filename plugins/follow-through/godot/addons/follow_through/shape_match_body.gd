extends MeshInstance3D
## A soft volume - jello, slime, clay, a water balloon - moved by lattice shape matching.
##
## The render mesh is embedded in a coarse lattice. Lattice nodes are the particles;
## every node owns a cluster of its lattice neighbours, and each tick every cluster
## finds the rigid rotation that best maps its rest shape onto where its nodes are
## now (Mueller et al. 2005), pulls them toward that goal, and the render mesh follows
## its nodes trilinearly. Shape memory comes from the goals; squash that bulges
## sideways comes from blending in the volume-normalised linear fit (`squash`);
## clay's creep comes from letting the rest shape move toward the deformed one when
## a cluster is strained past `yield` (plasticity).
##
## Why this and not SoftBody3D with pressure: Godot's Jolt soft body builds no bend
## constraints, so a closed surface has nothing but pressure holding its shape - it
## keeps its volume and loses its form. Why a lattice and not the mesh: the sim cost
## follows the lattice (a few hundred nodes), not the mesh, and interior nodes give a
## volume an inside to wobble around.
##
## Every rule here is measured by verify_volume.gd; see references/volumes.md.
##
## Limits: it collides with physics bodies (it is pushed, it does not push), volumes do
## not collide with each other, and nothing collides with it. `poke()` is the way in.

var spec: Dictionary
var report: Dictionary = {}
var source: MeshInstance3D

# material, per second
var frequency_hz := 3.0
var damping_ratio := 0.1
var squash := 0.3
var plastic_yield := 0.0          # 0 = elastic
var plastic_creep := 0.0          # 1/s
var plastic_max := 0.0            # rest nodes may drift this fraction of the body's size
var friction := 0.5
var gravity_scale := 1.0
var substeps := 0                 # 0 = as few as keep each step's correction <= MAX_ALPHA
var stiffness_gain := 1.0         # verify_volume.gd tune=true measures and recommends this
var resolution := 3
var cluster_radius := 1           # lattice steps: a cluster is every node within this of its centre node
var global_stiffness := 0.3       # share of each goal taken from one cluster over the whole body
var rolling_resistance := 1.0     # 1/s: rigid motion decays at this rate while touching something

# lattice
var spacing := 0.1
var _origin := Vector3.ZERO
var _dims := Vector3i.ONE
var _node_at := {}                # Vector3i -> node id
var _node_cell := PackedVector3Array()   # integer lattice coordinate per node, as floats
var x := PackedVector3Array()     # node positions, world
var _v := PackedVector3Array()
var _rest := PackedVector3Array()
var _rest0 := PackedVector3Array()
var _pinned := PackedByteArray()
var _pin_offset: Array[Vector3] = []
var _pin_ids := PackedInt32Array()
var _anchor := "none"
var _skeleton: Skeleton3D
var _pin_bone := PackedInt32Array()

# clusters
var _cl_nodes: Array[PackedInt32Array] = []
var _cl_q: Array[PackedVector3Array] = []
var _cl_aqq_inv: Array[Basis] = []
var _cl_rot: Array[Quaternion] = []
var _cl_rest_centre := PackedVector3Array()
var _node_clusters := PackedInt32Array()   # clusters per node

# render embedding
var _cells: Array[Vector3i] = []
var _cell_id := {}                # Vector3i -> cell index
var _cell_nodes := PackedInt32Array()      # 8 per cell
var _vert_cell := PackedInt32Array()
var _vert_w := PackedFloat32Array()        # 8 per vertex
var _rest_normals := PackedVector3Array()
var _arrays: Array = []
var _surface_material: Material

# contact samples: surface points, each embedded like a vertex
var _sample_vert := PackedInt32Array()   # the samples tested last tick
var _touching := PackedInt32Array()      # the samples in contact on the last substep
var _cell_verts: Array[PackedInt32Array] = []
var _sample_radius := 0.01
var _query := PhysicsShapeQueryParameters3D.new()
var _probe := PhysicsShapeQueryParameters3D.new()
var _ray := PhysicsRayQueryParameters3D.new()


var _mass_per_node := 0.1
var _rest_mesh_volume := 0.0
var _gravity := Vector3(0, -9.8, 0)
var _pending_impulses: Array = []
var ticks := 0
var collide_enabled := true          # off for tests run away from every collider
var substeps_used := 0
var stiffness_limited := false    # the material asked for more than MAX_SUBSTEPS can give
const MAX_ALPHA := 0.5
const MAX_SUBSTEPS := 8
const STATIC_SLIDE_MPS := 0.05
const CONTACT_LIFT_MPS := 0.3      # outward speed below this at a contact is taken away too
var contacts_last_tick := 0


static func build(src: MeshInstance3D, s: Dictionary, options := {}):
	var body = new()
	body.spec = s
	body.source = src
	body.name = String(src.name) + "_volume"
	body._configure(options)
	src.get_parent().add_child(body)
	if options.get("hide_source", true):
		src.visible = false
	return body


func _configure(options: Dictionary) -> void:
	var sm: Dictionary = spec.get("shape_matching", {})
	var overrides: Dictionary = options.get("overrides", {})
	var pick := func(key: String, fallback):
		return overrides.get(key, sm.get(key, fallback))
	frequency_hz = float(pick.call("frequency_hz", frequency_hz))
	damping_ratio = float(pick.call("damping_ratio", damping_ratio))
	squash = float(pick.call("squash", squash))
	friction = float(pick.call("friction", friction))
	gravity_scale = float(pick.call("gravity_scale", gravity_scale))
	substeps = int(pick.call("substeps", substeps))
	stiffness_gain = float(pick.call("stiffness_gain", stiffness_gain))
	cluster_radius = int(pick.call("cluster_radius", cluster_radius))
	global_stiffness = float(pick.call("global_stiffness", global_stiffness))
	rolling_resistance = float(pick.call("rolling_resistance", rolling_resistance))
	var plastic: Dictionary = sm.get("plastic", {})
	plastic_yield = float(overrides.get("plastic_yield", plastic.get("yield", 0.0)))
	plastic_creep = float(overrides.get("plastic_creep", plastic.get("creep", 0.0)))
	plastic_max = float(overrides.get("plastic_max", plastic.get("max", 0.0)))
	resolution = int(pick.call("resolution", resolution))
	var total_mass := float(pick.call("total_mass", 1.0))
	top_level = true
	_anchor = spec.get("pins", {}).get("anchor", "none")
	if source.skin != null:
		_skeleton = source.get_node_or_null(source.skeleton) as Skeleton3D
	var g: float = ProjectSettings.get_setting("physics/3d/default_gravity", 9.8)
	var gv: Vector3 = ProjectSettings.get_setting("physics/3d/default_gravity_vector", Vector3.DOWN)
	_gravity = gv * g * gravity_scale

	var src_mesh := source.mesh
	_arrays = src_mesh.surface_get_arrays(0)
	_surface_material = source.get_active_material(0)
	var local: PackedVector3Array = _arrays[Mesh.ARRAY_VERTEX]
	var world := PackedVector3Array()
	world.resize(local.size())
	var xf := source.global_transform
	for i in local.size():
		world[i] = xf * local[i]
	var nb := xf.basis.orthonormalized()
	_rest_normals = PackedVector3Array()
	if _arrays[Mesh.ARRAY_NORMAL] != null:
		for n in (_arrays[Mesh.ARRAY_NORMAL] as PackedVector3Array):
			_rest_normals.append((nb * n).normalized())
	report["vertices"] = world.size()
	report["surfaces"] = src_mesh.get_surface_count()

	_build_lattice(world, resolution)
	_build_clusters()
	_embed(world)
	_pick_samples(world)
	_mass_per_node = total_mass / float(maxi(x.size(), 1))
	_match_pins()
	_rest_mesh_volume = embedded_volume(_rest) if _arrays[Mesh.ARRAY_INDEX] != null else 0.0
	report["nodes"] = x.size()
	report["cells"] = _cells.size()
	report["clusters"] = _cl_nodes.size()
	report["samples"] = _sample_vert.size()
	report["spacing_m"] = spacing
	report["pinned_nodes"] = _pin_ids.size()

	global_transform = Transform3D.IDENTITY
	mesh = ArrayMesh.new()
	_write_mesh(world, _rest_normals)
	process_physics_priority = 100


# ------------------------------------------------------------------ lattice

## Cells touching the surface, plus every cell the outside cannot reach - the inside.
func _build_lattice(world: PackedVector3Array, resolution: int) -> void:
	var box := AABB(world[0], Vector3.ZERO)
	for p in world:
		box = box.expand(p)
	var longest := maxf(box.size.x, maxf(box.size.y, box.size.z))
	spacing = longest / float(maxi(resolution, 1))
	# pad by one cell so the flood fill can walk round the outside
	_origin = box.position - Vector3.ONE * spacing
	var cells_dim := Vector3i(ceili(box.size.x / spacing) + 2, ceili(box.size.y / spacing) + 2,
		ceili(box.size.z / spacing) + 2)
	var surface := {}
	var inner_max := cells_dim - Vector3i(2, 2, 2)
	var inner := func(p: Vector3) -> Vector3i:
		# a vertex exactly on the box's far face floors into the padding layer: keep it in
		return _cell_of(p).clamp(Vector3i.ONE, inner_max)
	var idx: PackedInt32Array = _arrays[Mesh.ARRAY_INDEX] if _arrays[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
	for p in world:
		surface[inner.call(p)] = true
	# triangles larger than a cell leave gaps between their vertices: sample them
	for t in range(0, idx.size(), 3):
		var a := world[idx[t]]
		var b := world[idx[t + 1]]
		var c := world[idx[t + 2]]
		var span := maxf(a.distance_to(b), maxf(b.distance_to(c), c.distance_to(a)))
		var steps := ceili(span / (spacing * 0.5))
		if steps <= 1:
			surface[inner.call((a + b + c) / 3.0)] = true
			continue
		for i in steps + 1:
			for j in steps + 1 - i:
				var u := float(i) / steps
				var w := float(j) / steps
				surface[inner.call(a + (b - a) * u + (c - a) * w)] = true
	var outside := {}
	var stack: Array[Vector3i] = [Vector3i.ZERO]
	outside[Vector3i.ZERO] = true
	while not stack.is_empty():
		var cur: Vector3i = stack.pop_back()
		for d in [Vector3i(1, 0, 0), Vector3i(-1, 0, 0), Vector3i(0, 1, 0), Vector3i(0, -1, 0),
				Vector3i(0, 0, 1), Vector3i(0, 0, -1)]:
			var nxt: Vector3i = cur + d
			if nxt.x < 0 or nxt.y < 0 or nxt.z < 0 or nxt.x >= cells_dim.x or nxt.y >= cells_dim.y \
					or nxt.z >= cells_dim.z or outside.has(nxt) or surface.has(nxt):
				continue
			outside[nxt] = true
			stack.append(nxt)
	var inside := 0
	for cx in cells_dim.x:
		for cy in cells_dim.y:
			for cz in cells_dim.z:
				var c := Vector3i(cx, cy, cz)
				if outside.has(c):
					continue
				if not surface.has(c):
					inside += 1
				_cell_id[c] = _cells.size()
				_cells.append(c)
	report["inside_cells"] = inside
	_dims = cells_dim + Vector3i.ONE
	for c in _cells:
		for k in 8:
			var n := c + Vector3i(k & 1, (k >> 1) & 1, (k >> 2) & 1)
			if not _node_at.has(n):
				_node_at[n] = x.size()
				var p := _origin + Vector3(n) * spacing
				x.append(p)
				_v.append(Vector3.ZERO)
				_rest.append(p)
				_node_cell.append(Vector3(n))
			_cell_nodes.append(_node_at[n])
	_rest0 = _rest.duplicate()
	_pinned.resize(x.size())


func _cell_of(p: Vector3) -> Vector3i:
	return Vector3i(((p - _origin) / spacing).floor())


func _build_clusters() -> void:
	_node_clusters.resize(x.size())
	for i in x.size():
		var n := Vector3i(_node_cell[i])
		var members := PackedInt32Array()
		var w := cluster_radius
		for dx in range(-w, w + 1):
			for dy in range(-w, w + 1):
				for dz in range(-w, w + 1):
					var m := n + Vector3i(dx, dy, dz)
					if _node_at.has(m):
						members.append(_node_at[m])
		if members.size() < 4:
			continue
		_cl_nodes.append(members)
		_cl_rot.append(Quaternion.IDENTITY)
		_cl_q.append(PackedVector3Array())
		_cl_aqq_inv.append(Basis.IDENTITY)
		_cl_rest_centre.append(Vector3.ZERO)
		for m in members:
			_node_clusters[m] += 1
	# the whole body as one more cluster, blended in by global_stiffness: small clusters
	# alone can each rotate their own way, and a lattice finer than a few cells folds
	var all := PackedInt32Array()
	for i in x.size():
		all.append(i)
	_cl_nodes.append(all)
	_cl_rot.append(Quaternion.IDENTITY)
	_cl_q.append(PackedVector3Array())
	_cl_aqq_inv.append(Basis.IDENTITY)
	_cl_rest_centre.append(Vector3.ZERO)
	_refresh_rest()


## Rest centres, rest offsets and Aqq^-1 for every cluster, from `_rest`.
func _refresh_rest() -> void:
	for c in _cl_nodes.size():
		var nodes := _cl_nodes[c]
		var centre := Vector3.ZERO
		for m in nodes:
			centre += _rest[m]
		centre /= float(nodes.size())
		var q := PackedVector3Array()
		q.resize(nodes.size())
		var ax := Vector3.ZERO
		var ay := Vector3.ZERO
		var az := Vector3.ZERO
		for k in nodes.size():
			var d := _rest[nodes[k]] - centre
			q[k] = d
			ax += d * d.x
			ay += d * d.y
			az += d * d.z
		var aqq := Basis(ax, ay, az)
		# a flat cluster (one layer of nodes) has a singular Aqq: regularise it
		if absf(aqq.determinant()) < pow(spacing, 6) * 1e-3:
			aqq = Basis(ax + Vector3(1e-4, 0, 0) * spacing * spacing, ay + Vector3(0, 1e-4, 0) * spacing * spacing,
				az + Vector3(0, 0, 1e-4) * spacing * spacing)
		_cl_q[c] = q
		_cl_aqq_inv[c] = aqq.inverse()
		_cl_rest_centre[c] = centre


func _embed(world: PackedVector3Array) -> void:
	_vert_cell.resize(world.size())
	_vert_w.resize(world.size() * 8)
	for i in world.size():
		var f := (world[i] - _origin) / spacing
		var c := Vector3i(f.floor())
		if not _cell_id.has(c):
			c = _nearest_cell(c)
		var t := f - Vector3(c)
		t = t.clamp(Vector3.ZERO, Vector3.ONE)
		_vert_cell[i] = _cell_id[c]
		for k in 8:
			var wx := t.x if (k & 1) else 1.0 - t.x
			var wy := t.y if ((k >> 1) & 1) else 1.0 - t.y
			var wz := t.z if ((k >> 2) & 1) else 1.0 - t.z
			_vert_w[i * 8 + k] = wx * wy * wz


func _nearest_cell(c: Vector3i) -> Vector3i:
	var best := _cells[0]
	var bd := INF
	for cc in _cells:
		var d := Vector3(cc - c).length_squared()
		if d < bd:
			bd = d
			best = cc
	return best


## Contact samples are chosen every tick, from where the vertices are then: in each
## lattice cell, the vertices furthest along -x, +x, -y, +y, -z and +z. The cell's lowest
## vertex is always tested, so it cannot pass through a floor, nor its outermost through
## a wall. Chosen once at rest instead, a flat bottom face has no lowest vertex, and when
## the cube tilted, the vertices between its samples sank 2.6 cm into the floor.
func _pick_samples(world: PackedVector3Array) -> void:
	var by_cell := {}
	for i in world.size():
		var c := _vert_cell[i]
		if not by_cell.has(c):
			by_cell[c] = PackedInt32Array()
		by_cell[c].append(i)
	for c in by_cell:
		_cell_verts.append(by_cell[c])
	# contact a little proud of the surface: a sample only pushes once its sphere is in,
	# and the vertices between samples sit that much lower
	_sample_radius = spacing * 0.1
	var sphere := SphereShape3D.new()
	sphere.radius = _sample_radius
	_query.shape = sphere
	_query.collide_with_areas = false
	_probe.collide_with_areas = false


func _current_samples(pos: PackedVector3Array) -> PackedInt32Array:
	var out := PackedInt32Array()
	var taken := {}
	var centre := Vector3.ZERO
	for q in pos:
		centre += q
	centre /= float(maxi(pos.size(), 1))
	var down := _gravity.normalized() if _gravity.length_squared() > 0.0 else Vector3.DOWN
	for verts in _cell_verts:
		# only the faces of the cell that look out of the body can meet anything; and
		# always the one gravity presses against
		var mid := Vector3.ZERO
		for i in verts:
			mid += pos[i]
		mid /= float(verts.size())
		var outward := mid - centre
		var dirs: Array[Vector3] = [down]
		for axis in [Vector3.RIGHT, Vector3.UP, Vector3.BACK]:
			var d: float = outward.dot(axis)
			if absf(d) > spacing * 0.25:
				dirs.append(axis * signf(d))
		for d in dirs:
			var best := verts[0]
			var best_dot := -INF
			for i in verts:
				var along := pos[i].dot(d)
				if along > best_dot:
					best_dot = along
					best = i
			if not taken.has(best):
				taken[best] = true
				out.append(best)
	return out


func _match_pins() -> void:
	var pins: Dictionary = spec.get("pins", {})
	var count := int(pins.get("count", 0))
	if count == 0:
		return
	var flat: Array = pins.get("positions", [])
	var bones: Array = pins.get("bones", [])
	var xf := source.global_transform
	var reach := spacing * 0.75
	for k in count:
		var p := xf * Vector3(flat[3 * k], flat[3 * k + 1], flat[3 * k + 2])
		for i in x.size():
			if _pinned[i] or x[i].distance_to(p) > reach:
				continue
			_pinned[i] = 1
			_pin_ids.append(i)
			if _anchor == "bone" and _skeleton != null and k < bones.size():
				var b := _skeleton.find_bone(String(bones[k]))
				_pin_bone.append(b)
				var bxf := _skeleton.global_transform * _skeleton.get_bone_global_pose(b) if b >= 0 else Transform3D.IDENTITY
				_pin_offset.append(bxf.affine_inverse() * x[i])
			else:
				_pin_bone.append(-1)
				_pin_offset.append(xf.affine_inverse() * x[i])
	report["pins_total"] = count


func pin_target(k: int) -> Vector3:
	if _anchor == "bone" and _pin_bone[k] >= 0 and _skeleton != null:
		return _skeleton.global_transform * _skeleton.get_bone_global_pose(_pin_bone[k]) * _pin_offset[k]
	return source.global_transform * _pin_offset[k]


# ------------------------------------------------------------------ simulation

## How much slower the body wobbles than one node's goal spring, measured: a cube held
## at its base and sheared, in verify_volume.gd's frequency test. Local clusters are
## springs in series, softening with the lattice (stiffness ~ resolution^-1.73: 0.054 at
## 2 cells, 0.0164 at 4); the whole-body cluster does not (0.044); stiffnesses add in
## the proportion global_stiffness blends them. Frequency goes as the square root.
func frequency_ratio() -> float:
	var local := 0.054 * pow(2.0 / float(maxi(resolution, 1)), 1.73)
	var k := (1.0 - global_stiffness) * local + global_stiffness * 0.044
	# squash frees volume-keeping shear, so the body rings lower: measured 0.885 of the
	# unsquashed frequency at squash 0.5 and 0.67 at 0.8, which 1 - 0.46 squash^2 fits
	return sqrt(k) * maxf(1.0 - 0.46 * squash * squash, 0.3)


## Node spring frequency that makes the body wobble at `frequency_hz`.
func node_frequency() -> float:
	return frequency_hz / frequency_ratio() * sqrt(stiffness_gain)


func _physics_process(delta: float) -> void:
	var omega := TAU * node_frequency()
	# Shape matching's step has eigenvalues (1 - a/2) +- i sqrt(4a - a^2)/2, of modulus 1:
	# it turns by w dt per step when cos(w dt) = 1 - a/2 (Mueller et al. 2005, eq. 9-10).
	# Past a = 1 it overshoots its goal, so take as many substeps as keep it at MAX_ALPHA.
	# Substeps come from the angle w dt itself, never from alpha: alpha is periodic in it, and
	# a clay ball whose node spring needed 6.39 rad per tick read alpha = 0.01 at one substep
	# ("small enough"), ran nearly stiffness-free, and flattened to 1% of its volume.
	var max_angle := acos(1.0 - MAX_ALPHA / 2.0)
	var n := substeps
	if n <= 0:
		n = clampi(ceili(omega * delta / max_angle), 1, MAX_SUBSTEPS)
	var dt := delta / float(n)
	stiffness_limited = omega * dt > max_angle + 1e-6
	var alpha := 2.0 * (1.0 - cos(minf(omega * dt, max_angle)))
	# damping ratio of the body's mode, applied to deviation from rigid motion
	var keep := exp(-2.0 * damping_ratio * TAU * frequency_hz * dt)
	substeps_used = n
	var targets: Array[Vector3] = []
	for k in _pin_ids.size():
		targets.append(pin_target(k))
	var prev := x.duplicate()
	for s in n:
		# every substep resolves contacts: resolved only on the last, nodes sank freely for the
		# others and the push fed a cycle - a jello cube jittered at 0.5 m/s and wandered 12 cm
		# in 10 s; resolved every substep it rested still. The full sweep runs on the first
		# substep; the others re-test only the samples that were touching.
		_step(dt, alpha, keep, targets, float(s + 1) / float(n), prev, true, s == 0)
	if plastic_yield > 0.0 and plastic_creep > 0.0:
		_plastic(delta)
	ticks += 1


func _step(dt: float, alpha: float, keep: float, targets: Array[Vector3], blend: float,
		tick_start: PackedVector3Array, collide: bool, sweep: bool = true) -> void:
	var count := x.size()
	for imp in _pending_impulses:
		# an impulse is shared: N s over the mass it reaches, falling off with distance
		var falls := PackedFloat32Array()
		falls.resize(count)
		var total := 0.0
		for i in count:
			var fall: float = 1.0 - x[i].distance_to(imp[0]) / float(imp[2])
			if fall > 0.0 and not _pinned[i]:
				falls[i] = fall
				total += fall
		if total > 0.0:
			var dv: Vector3 = imp[1] / (total * _mass_per_node)
			for i in count:
				_v[i] += dv * falls[i]
	_pending_impulses.clear()
	_damp(keep, dt)
	var p := PackedVector3Array()
	p.resize(count)
	for i in count:
		if _pinned[i]:
			continue
		_v[i] += _gravity * dt
		p[i] = x[i] + _v[i] * dt
	for k in _pin_ids.size():
		var i := _pin_ids[k]
		p[i] = tick_start[i].lerp(targets[k], blend)

	# shape matching: every cluster proposes a goal for each of its nodes
	var goal := PackedVector3Array()
	goal.resize(count)
	var global_goal := PackedVector3Array()
	var last := _cl_nodes.size() - 1
	for c in _cl_nodes.size():
		var nodes := _cl_nodes[c]
		var q := _cl_q[c]
		var m := nodes.size()
		var centre := Vector3.ZERO
		for k in m:
			centre += p[nodes[k]]
		centre /= float(m)
		var cx := Vector3.ZERO
		var cy := Vector3.ZERO
		var cz := Vector3.ZERO
		for k in m:
			var d := p[nodes[k]] - centre
			var qk := q[k]
			cx += d * qk.x
			cy += d * qk.y
			cz += d * qk.z
		var apq := Basis(cx, cy, cz)
		var rot := _extract_rotation(apq, _cl_rot[c])
		_cl_rot[c] = rot
		var g := Basis(rot)
		if squash > 0.0:
			var lin := apq * _cl_aqq_inv[c]
			var det := lin.determinant()
			if det > 1e-9:
				var s := 1.0 / pow(det, 1.0 / 3.0)
				g = Basis(g.x.lerp(lin.x * s, squash), g.y.lerp(lin.y * s, squash), g.z.lerp(lin.z * s, squash))
		if c == last:
			global_goal.resize(count)
			for k in m:
				global_goal[nodes[k]] = g * q[k] + centre
		else:
			for k in m:
				goal[nodes[k]] += g * q[k] + centre
	for i in count:
		if _pinned[i]:
			continue
		var gi := goal[i] / float(_node_clusters[i])
		gi = gi.lerp(global_goal[i], global_stiffness)
		p[i] += (gi - p[i]) * alpha

	# once per tick: the queries cost more than the shape matching, and a contact
	# lasting a substep longer does not show
	for i in count:
		_v[i] = (p[i] - x[i]) / dt
	if collide and collide_enabled:
		_collide(p, x, sweep)
	x = p


## Damp only what is not rigid motion (Mueller et al. 2007, PBD sec. 3.5): the
## wobble dies, while falling, sliding and rolling keep their speed.
func _damp(keep: float, dt: float = 0.0) -> void:
	if keep >= 1.0 and (rolling_resistance <= 0.0 or _touching.is_empty()):
		return
	var count := x.size()
	var com := Vector3.ZERO
	var vcm := Vector3.ZERO
	for i in count:
		com += x[i]
		vcm += _v[i]
	com /= float(count)
	vcm /= float(count)
	var ang := Vector3.ZERO
	var ix := Vector3.ZERO
	var iy := Vector3.ZERO
	var iz := Vector3.ZERO
	for i in count:
		var r := x[i] - com
		ang += r.cross(_v[i] - vcm)
		var rr := r.dot(r)
		ix += Vector3(rr, 0, 0) - r * r.x
		iy += Vector3(0, rr, 0) - r * r.y
		iz += Vector3(0, 0, rr) - r * r.z
	var inertia := Basis(ix, iy, iz)
	var omega := Vector3.ZERO
	if absf(inertia.determinant()) > 1e-12:
		omega = inertia.inverse() * ang
	# rolling resistance: while touching something, rigid motion loses energy too - a real
	# soft body pays for rolling by deforming. Without it a round water balloon rocked on a
	# flat floor at 0.3 m/s ten seconds after landing.
	var roll := exp(-rolling_resistance * dt) if not _touching.is_empty() else 1.0
	for i in count:
		if _pinned[i]:
			continue
		var rigid := vcm + omega.cross(x[i] - com)
		_v[i] = rigid * roll + (_v[i] - rigid) * keep


## The rotation closest to A, starting from last tick's (Mueller et al. 2016): a few
## cheap iterations that never flip, where a polar decomposition through SVD can.
static func _extract_rotation(a: Basis, q: Quaternion, iterations := 3) -> Quaternion:
	for it in iterations:
		var r := Basis(q)
		var omega := r.x.cross(a.x) + r.y.cross(a.y) + r.z.cross(a.z)
		omega /= absf(r.x.dot(a.x) + r.y.dot(a.y) + r.z.dot(a.z)) + 1e-9
		var w := omega.length()
		if w < 1e-9:
			break
		q = (Quaternion(omega / w, w) * q).normalized()
	return q


## Push nodes out of physics bodies through the surface samples embedded in them.
##
## Each sample first casts a ray from where it was at the start of the tick to where it is
## now: a hit is where it entered, on the side it came from. Overlap alone cannot say which
## side that was - a jello cube dropped on a 10 cm convex slab had vertices 6 cm deep within
## three ticks, nearer the slab's bottom face than its top, and was pushed down through it.
## Samples that did not move into anything (something moved into them) fall back to a
## sphere overlap query.
##
## The push moves positions and never becomes velocity: pushed out after a whole tick of
## sinking and turned into speed over a 1/480 s substep, it launched a clay ball at 7.5 m/s.
## Instead the velocity into the surface is removed (no bounce) and friction takes a share
## of the sliding velocity.
func _collide(p: PackedVector3Array, tick_start: PackedVector3Array, sweep: bool) -> void:
	var space := get_world_3d().direct_space_state
	if space == null:
		return
	if sweep:
		# one query for the whole swept body first: most ticks nothing is near
		var box := AABB(p[0], Vector3.ZERO)
		for i in p.size():
			box = box.expand(p[i]).expand(tick_start[i])
		var probe_shape := BoxShape3D.new()
		probe_shape.size = box.size + Vector3.ONE * (_sample_radius * 4.0)
		_probe.shape = probe_shape
		_probe.transform = Transform3D(Basis(), box.get_center())
		if space.intersect_shape(_probe, 1).is_empty():
			contacts_last_tick = 0
			_touching.clear()
			return
	elif _touching.is_empty():
		return
	var hits := 0
	var delta := PackedVector3Array()
	delta.resize(p.size())
	var touched := PackedFloat32Array()
	touched.resize(p.size())
	var normal_sum := PackedVector3Array()
	normal_sum.resize(p.size())
	var surface := _embedded_positions(p)
	var before := _embedded_positions(tick_start)
	if sweep:
		_sample_vert = _current_samples(surface)
	var testing := _sample_vert if sweep else _touching
	var touching_now := PackedInt32Array()
	for sv in testing:
		var cell := _vert_cell[sv]
		var wsum := 0.0
		for k in 8:
			var w := _vert_w[sv * 8 + k]
			wsum += w * w
		var push := Vector3.ZERO
		var from := before[sv]
		var to := surface[sv]
		var travel := to - from
		if travel.length_squared() > 1e-12:
			_ray.from = from
			_ray.to = to + travel.normalized() * _sample_radius
			var hit := space.intersect_ray(_ray)
			if not hit.is_empty():
				var n: Vector3 = hit["normal"]
				var target: Vector3 = hit["position"] + n * _sample_radius
				var depth := (target - to).dot(n)
				if depth > 0.0:
					push = n * depth
		if push == Vector3.ZERO:
			_query.transform = Transform3D(Basis(), to)
			var pairs := space.collide_shape(_query, 4)
			# each pair: a point on the sample sphere inside the other shape, then the
			# closest point on the other shape's surface - the way out
			for j in range(0, pairs.size(), 2):
				var out: Vector3 = pairs[j + 1] - pairs[j]
				if out.length_squared() > push.length_squared():
					push = out
		if push.length_squared() < 1e-12:
			continue
		hits += 1
		touching_now.append(sv)
		var nrm := push.normalized()
		for k in 8:
			var node := _cell_nodes[cell * 8 + k]
			if _pinned[node]:
				continue
			var w := _vert_w[sv * 8 + k]
			var share := push * (w / maxf(wsum, 1e-9))
			# keep the largest push per node along any direction, not the sum: many
			# samples share a node, and summing them launches it
			if share.length_squared() > delta[node].length_squared():
				delta[node] = share
			touched[node] = maxf(touched[node], w)
			normal_sum[node] += nrm * w
	if sweep:
		contacts_last_tick = hits
	_touching = touching_now
	if hits == 0:
		return
	for i in p.size():
		if touched[i] <= 0.0:
			continue
		p[i] += delta[i]
		var nrm := normal_sum[i].normalized()
		var vi := _v[i]
		var vn := vi.dot(nrm)
		# no bounce, and no small lift-off either: the goals pull a pushed-out node back in
		# and the next push lifts it again, and a lightly damped jello cube fed on that
		# cycle still jittered at 0.76 m/s ten seconds after landing
		if vn < 0.0 or vn < CONTACT_LIFT_MPS:
			vi -= nrm * vn
		var vt := vi - nrm * vi.dot(nrm)
		# static friction: a contact sliding slower than this sticks, or a resting body
		# creeps across the floor on the imbalance of its own contact pushes
		if vt.length() < STATIC_SLIDE_MPS * friction:
			_v[i] = vi - vt
		else:
			_v[i] = vi - vt * clampf(friction * touched[i], 0.0, 1.0)


## Plasticity: a cluster strained past `plastic_yield` moves its rest shape toward
## the shape it is held in, at `plastic_creep` per second, never further than
## `plastic_max` of the body's size from where it started, and the rest volume is
## held - clay flattens and bulges, it does not lose mass.
func _plastic(delta: float) -> void:
	var shift := PackedVector3Array()
	shift.resize(x.size())
	var changed := false
	for c in _cl_nodes.size() - 1:
		var nodes := _cl_nodes[c]
		var q := _cl_q[c]
		var m := nodes.size()
		var centre := Vector3.ZERO
		for k in m:
			centre += x[nodes[k]]
		centre /= float(m)
		var cx := Vector3.ZERO
		var cy := Vector3.ZERO
		var cz := Vector3.ZERO
		for k in m:
			var d := x[nodes[k]] - centre
			cx += d * q[k].x
			cy += d * q[k].y
			cz += d * q[k].z
		var lin := Basis(cx, cy, cz) * _cl_aqq_inv[c]
		var rt := Basis(_cl_rot[c]).inverse()
		var strain_m := rt * lin
		var e := (strain_m.x - Vector3(1, 0, 0)).length_squared() + (strain_m.y - Vector3(0, 1, 0)).length_squared() \
			+ (strain_m.z - Vector3(0, 0, 1)).length_squared()
		var strain := sqrt(e)
		if strain <= plastic_yield:
			continue
		changed = true
		var rate := minf(1.0, plastic_creep * delta) * (1.0 - plastic_yield / strain)
		var rest_centre := _cl_rest_centre[c]
		for k in m:
			var node := nodes[k]
			if _pinned[node]:
				continue
			var held := rt * (x[node] - centre) + rest_centre
			shift[node] += (held - _rest[node]) * rate / float(_node_clusters[node])
	if not changed:
		return
	var size := spacing * float(maxi(_dims.x, maxi(_dims.y, _dims.z)))
	var limit := plastic_max * size
	for i in x.size():
		var r := _rest[i] + shift[i]
		var drift := r - _rest0[i]
		if drift.length() > limit:
			r = _rest0[i] + drift.normalized() * limit
		_rest[i] = r
	# Held against the volume of the render mesh embedded in the rest lattice, and
	# against the volume it started with, not last tick's: summed cell determinants
	# stayed at 1.000 while the clay ball's mesh lost half its volume.
	var after := embedded_volume(_rest)
	if after > 1e-12 and _rest_mesh_volume > 0.0:
		var before := _rest_mesh_volume
		var centre := Vector3.ZERO
		for r in _rest:
			centre += r
		centre /= float(_rest.size())
		var s := pow(before / after, 1.0 / 3.0)
		for i in _rest.size():
			_rest[i] = centre + (_rest[i] - centre) * s
	_refresh_rest()


## Volume of the render mesh when the lattice nodes are at `nodes`, m^3.
func embedded_volume(nodes: PackedVector3Array) -> float:
	var idx: PackedInt32Array = _arrays[Mesh.ARRAY_INDEX]
	var pos := _embedded_positions(nodes)
	var v := 0.0
	for t in range(0, idx.size(), 3):
		v += pos[idx[t]].dot(pos[idx[t + 1]].cross(pos[idx[t + 2]]))
	return absf(v) / 6.0


func _embedded_positions(nodes: PackedVector3Array) -> PackedVector3Array:
	var count := _vert_cell.size()
	var pos := PackedVector3Array()
	pos.resize(count)
	for i in count:
		var b := _vert_cell[i] * 8
		var w := i * 8
		var p := Vector3.ZERO
		for k in 8:
			p += nodes[_cell_nodes[b + k]] * _vert_w[w + k]
		pos[i] = p
	return pos


# ------------------------------------------------------------------ render

func _process(_delta: float) -> void:
	var count := _vert_cell.size()
	var pos := PackedVector3Array()
	pos.resize(count)
	var cell_f: Array[Basis] = []
	cell_f.resize(_cells.size())
	var inv := 1.0 / spacing
	for c in _cells.size():
		var b := c * 8
		var n0 := x[_cell_nodes[b]]
		var n1 := x[_cell_nodes[b + 1]]
		var n2 := x[_cell_nodes[b + 2]]
		var n3 := x[_cell_nodes[b + 3]]
		var n4 := x[_cell_nodes[b + 4]]
		var n5 := x[_cell_nodes[b + 5]]
		var n6 := x[_cell_nodes[b + 6]]
		var n7 := x[_cell_nodes[b + 7]]
		var fx := ((n1 - n0) + (n3 - n2) + (n5 - n4) + (n7 - n6)) * (0.25 * inv)
		var fy := ((n2 - n0) + (n3 - n1) + (n6 - n4) + (n7 - n5)) * (0.25 * inv)
		var fz := ((n4 - n0) + (n5 - n1) + (n6 - n2) + (n7 - n3)) * (0.25 * inv)
		# normals transform by the cofactor of the deformation gradient
		cell_f[c] = Basis(fy.cross(fz), fz.cross(fx), fx.cross(fy))
	var normals := PackedVector3Array()
	normals.resize(_rest_normals.size())
	for i in count:
		var cell := _vert_cell[i]
		var b := cell * 8
		var w := i * 8
		pos[i] = x[_cell_nodes[b]] * _vert_w[w] + x[_cell_nodes[b + 1]] * _vert_w[w + 1] \
			+ x[_cell_nodes[b + 2]] * _vert_w[w + 2] + x[_cell_nodes[b + 3]] * _vert_w[w + 3] \
			+ x[_cell_nodes[b + 4]] * _vert_w[w + 4] + x[_cell_nodes[b + 5]] * _vert_w[w + 5] \
			+ x[_cell_nodes[b + 6]] * _vert_w[w + 6] + x[_cell_nodes[b + 7]] * _vert_w[w + 7]
		if not _rest_normals.is_empty():
			var cof := cell_f[cell]
			var n := _rest_normals[i]
			normals[i] = (cof.x * n.x + cof.y * n.y + cof.z * n.z).normalized()
	_write_mesh(pos, normals)


func _write_mesh(pos: PackedVector3Array, normals: PackedVector3Array) -> void:
	var out := []
	out.resize(Mesh.ARRAY_MAX)
	out[Mesh.ARRAY_VERTEX] = pos
	if not normals.is_empty():
		out[Mesh.ARRAY_NORMAL] = normals
	for slot in [Mesh.ARRAY_TEX_UV, Mesh.ARRAY_TEX_UV2, Mesh.ARRAY_COLOR, Mesh.ARRAY_INDEX]:
		out[slot] = _arrays[slot]
	var m := mesh as ArrayMesh
	m.clear_surfaces()
	m.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, out)
	if _surface_material != null:
		m.surface_set_material(0, _surface_material)


# ------------------------------------------------------------------ queries

## Push every node within `radius` of `point` by `impulse` (N s), falling off linearly.
func poke(point: Vector3, impulse: Vector3, radius := -1.0) -> void:
	_pending_impulses.append([point, impulse, radius if radius > 0.0 else spacing * 2.0])


## Move the whole volume without it wobbling.
func teleport(delta: Transform3D) -> void:
	for i in x.size():
		x[i] = delta * x[i]
		_v[i] = delta.basis * _v[i]


func centre_of_mass() -> Vector3:
	var c := Vector3.ZERO
	for p in x:
		c += p
	return c / float(maxi(x.size(), 1))


## Volume enclosed by the deformed render mesh, m^3 (divergence theorem).
func mesh_volume() -> float:
	var arrays := (mesh as ArrayMesh).surface_get_arrays(0)
	var pos: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var idx: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var v := 0.0
	for t in range(0, idx.size(), 3):
		v += pos[idx[t]].dot(pos[idx[t + 1]].cross(pos[idx[t + 2]]))
	return absf(v) / 6.0


## Fastest node, m/s. Nodes outside the mesh are included; for what is seen, compare
## render positions between frames (verify_volume.gd does).
func speed_max() -> float:
	var s := 0.0
	for vi in _v:
		s = maxf(s, vi.length())
	return s


## Render vertex positions now, world space.
func surface_positions() -> PackedVector3Array:
	return _embedded_positions(x)


func kinetic_energy() -> float:
	var e := 0.0
	for vi in _v:
		e += vi.length_squared()
	return 0.5 * _mass_per_node * e


func pinned_nodes() -> PackedInt32Array:
	return _pin_ids


## Whether render vertex `i` is embedded in a cell with a pinned corner.
func near_pinned(i: int) -> bool:
	if _pin_ids.is_empty():
		return false
	var b := _vert_cell[i] * 8
	for k in 8:
		if _pinned[_cell_nodes[b + k]]:
			return true
	return false
