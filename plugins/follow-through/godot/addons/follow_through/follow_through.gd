extends RefCounted
## follow-through runtime: turns imported meshes that carry a follow-through spec
## into moving secondary motion.
##
##   const FollowThrough = preload("res://addons/follow_through/follow_through.gd")
##   var report := FollowThrough.apply(imported_scene_root)
##
## Blender writes the spec as the object custom property `follow_through`; glTF
## carries it as node extras; Godot's importer stores it as
## `node.get_meta("extras")["follow_through"]`. See schema/follow-through.schema.json.
##
## Routes built here:
##   soft_body       cloth_body.gd        a SoftBody3D sheet pinned to what holds it
##   shape_matching  shape_match_body.gd  a volume on a lattice: jello, slime, clay, a balloon
##   jiggle_bones    jiggle_modifier.gd   sprung bones on a skeleton: breasts, bellies, buttocks
##   spring_bones    strand_modifier.gd   sprung bone chains: ponytails, locks of long hair
## `none`, and a `spring_bones` strap (no `strands` block), are reported and skipped.
##
## Strands usually come in their own glb, exported from the body's rig; put them on the body first:
##   FollowThrough.attach(body_root, preload("res://assets/figure_hair.glb"))
##   FollowThrough.apply(body_root, {"routes": ["spring_bones"]})

const SCHEMA := "follow-through/1"
const ClothBody := preload("res://addons/follow_through/cloth_body.gd")
const ShapeMatchBody := preload("res://addons/follow_through/shape_match_body.gd")
const JiggleModifier := preload("res://addons/follow_through/jiggle_modifier.gd")
const StrandModifier := preload("res://addons/follow_through/strand_modifier.gd")


## The spec on a node, or an empty Dictionary.
static func spec_of(node: Node) -> Dictionary:
	if not node.has_meta("extras"):
		return {}
	var extras = node.get_meta("extras")
	if typeof(extras) != TYPE_DICTIONARY or not extras.has("follow_through"):
		return {}
	return extras["follow_through"]


## Problems with a spec, empty when it can be built. Mirrors spec.validate in Blender.
static func validate(spec: Dictionary) -> PackedStringArray:
	var p := PackedStringArray()
	for k in ["schema", "family", "class", "route", "source"]:
		if not spec.has(k):
			p.append("missing " + k)
	if spec.get("schema", "") != SCHEMA:
		p.append("schema is %s, this runtime reads %s" % [spec.get("schema", "?"), SCHEMA])
	match spec.get("route", ""):
		"soft_body":
			for k in ["fabric", "soft_body", "pins"]:
				if not spec.has(k):
					p.append("soft_body route missing " + k)
		"shape_matching":
			for k in ["material", "shape_matching"]:
				if not spec.has(k):
					p.append("shape_matching route missing " + k)
			var sm: Dictionary = spec.get("shape_matching", {})
			for k in ["frequency_hz", "damping_ratio", "total_mass", "resolution"]:
				if not sm.has(k):
					p.append("shape_matching missing " + k)
		"jiggle_bones":
			var j: Dictionary = spec.get("jiggle", {})
			if j.get("space", "") != "gltf_armature":
				p.append("jiggle.space must be gltf_armature")
			if j.get("regions", []).is_empty():
				p.append("jiggle.regions is empty")
			for r in j.get("regions", []):
				for k in ["name", "bone", "parent", "head", "tail", "frequency_hz", "damping_ratio"]:
					if not r.has(k):
						p.append("jiggle region %s missing %s" % [r.get("name", "?"), k])
		"spring_bones":
			if spec.get("class", "") == "strand":
				var blk: Dictionary = spec.get("strands", {})
				if blk.get("space", "") != "gltf_armature":
					p.append("strands.space must be gltf_armature")
				if blk.get("chains", []).is_empty():
					p.append("strands.chains is empty")
				for c in blk.get("chains", []):
					for b in c.get("bones", []):
						for k in ["bone", "parent", "head", "tail", "frequency_hz", "damping_ratio", "max_angle_deg"]:
							if not b.has(k):
								p.append("strand bone %s missing %s" % [b.get("bone", "?"), k])
	if spec.has("pins"):
		var pins: Dictionary = spec["pins"]
		if pins.get("space", "") != "gltf_mesh":
			p.append("pins.space must be gltf_mesh")
		if pins.get("positions", []).size() != 3 * int(pins.get("count", 0)):
			p.append("pins.positions length does not match pins.count")
		if pins.get("anchor", "") == "bone" and pins.get("bones", []).size() != int(pins.get("count", 0)):
			p.append("pins.anchor=bone needs one bone per pin")
	return p


## Every node under `root` (inclusive) carrying a spec.
static func find_specs(root: Node) -> Array[Node]:
	var out: Array[Node] = []
	var stack: Array[Node] = [root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if not spec_of(n).is_empty():
			out.append(n)
		for c in n.get_children():
			stack.append(c)
	return out


## Build every buildable spec under `root`. `root` must be inside the tree.
## options:
##   overrides: Dictionary   runtime property -> value, applied to every body of a route
##                           (soft_body names for cloth, shape_matching names for volumes,
##                           jiggle names for flesh) - for tuning without re-exporting
##   routes: Array           build only these routes (default all)
##   hide_source: bool       hide the original mesh for cloth and volumes (default true)
## Returns one report Dictionary per spec found; a built one carries `body`.
static func apply(root: Node, options := {}) -> Array[Dictionary]:
	var reports: Array[Dictionary] = []
	var only: Array = options.get("routes", [])
	for node in find_specs(root):
		var spec := spec_of(node)
		var route := String(spec.get("route", "?"))
		var rep := {"node": String(node.name), "class": spec.get("class", "?"), "route": route,
			"type": spec.get("type", "")}
		if not only.is_empty() and not only.has(route):
			continue
		var problems := validate(spec)
		if not problems.is_empty():
			rep["built"] = false
			rep["problems"] = problems
		elif not node is MeshInstance3D:
			rep["built"] = false
			rep["problems"] = PackedStringArray(["spec on a %s, expected MeshInstance3D" % node.get_class()])
		else:
			var body = null
			match route:
				"soft_body":
					body = ClothBody.build(node, spec, options)
				"shape_matching":
					body = ShapeMatchBody.build(node, spec, options)
				"jiggle_bones":
					body = JiggleModifier.build(node, spec, options)
				"spring_bones":
					if spec.has("strands"):
						body = StrandModifier.build(node, spec, options)
			if body == null:
				rep["built"] = false
				rep["problems"] = PackedStringArray(["route %s is not built by this runtime" % route])
			else:
				rep.merge(body.report, true)
				rep["built"] = rep.get("built", true)
				rep["body"] = body
		reports.append(rep)
	return reports

## Put the strand meshes of `strands` (a PackedScene or an instance: a glb exported by
## follow-through's strand.export from the body's rig) onto the body's skeleton under `body_root`.
## Bones the body lacks are added from the strand file's skeleton, parents first; each mesh moves
## under the body's Skeleton3D and binds to it by bone name. Then `apply(body_root)` springs them.
## Returns one report per strand mesh: {mesh, bones_added, problems}.
static func attach(body_root: Node, strands) -> Array[Dictionary]:
	var reports: Array[Dictionary] = []
	var inst: Node = strands.instantiate() if strands is PackedScene else strands
	var meshes: Array = []
	for n in inst.find_children("*", "MeshInstance3D", true, false):
		var s := spec_of(n)
		if not s.is_empty() and String(s.get("route", "")) == "spring_bones":
			meshes.append(n)
	if meshes.is_empty():
		reports.append({"built": false, "problems": PackedStringArray(["no strand mesh in " + String(inst.name)])})
	for gm in meshes:
		var s := spec_of(gm)
		var problems := PackedStringArray()
		var root_bone := ""
		for c in s.get("strands", {}).get("chains", []):
			root_bone = String(c.get("root_bone", ""))
		var skel: Skeleton3D = null
		var body_mesh: MeshInstance3D = null
		for sk in body_root.find_children("*", "Skeleton3D", true, false):
			if root_bone == "" or sk.find_bone(root_bone) >= 0 or sk.find_bone(root_bone.replace(".", "_")) >= 0:
				skel = sk
				break
		var gskel := gm.get_node_or_null(gm.skeleton) as Skeleton3D
		if skel == null or gskel == null:
			problems.append("no skeleton with %s under %s" % [root_bone, body_root.name] if skel == null
				else "the strand mesh has no skeleton")
			reports.append({"mesh": gm, "built": false, "problems": problems})
			continue
		for c in skel.get_children():
			if c is MeshInstance3D and c.skin != null and spec_of(c).get("route", "") != "spring_bones":
				body_mesh = c
				break
		var added := 0
		var pending := range(gskel.get_bone_count())
		var guard := 0
		while not pending.is_empty() and guard < 64:
			guard += 1
			var still := []
			for i in pending:
				var bname := gskel.get_bone_name(i)
				if skel.find_bone(bname) >= 0:
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
		gm.get_parent().remove_child(gm)
		gm.owner = null
		skel.add_child(gm)
		gm.transform = body_mesh.transform if body_mesh != null else Transform3D.IDENTITY
		gm.skeleton = gm.get_path_to(skel)
		var missing := 0
		for b in gm.skin.get_bind_count():
			if skel.find_bone(gm.skin.get_bind_name(b)) < 0:
				missing += 1
		if missing > 0:
			problems.append("%d skin binds name bones the body does not have" % missing)
		reports.append({"mesh": gm, "built": problems.is_empty(), "bones_added": added, "problems": problems})
	if inst.get_parent() != null:
		inst.get_parent().remove_child(inst)
	inst.queue_free()
	return reports
