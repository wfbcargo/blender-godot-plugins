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
## Only route `soft_body` is built today. Other routes are reported and skipped.

const SCHEMA := "follow-through/1"
const ClothBody := preload("res://addons/follow_through/cloth_body.gd")


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
	if spec.get("route", "") == "soft_body":
		for k in ["fabric", "soft_body", "pins"]:
			if not spec.has(k):
				p.append("soft_body route missing " + k)
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
##   overrides: Dictionary   soft_body property -> value, applied to every cloth (for tuning)
##   hide_source: bool       hide the original mesh (default true)
## Returns one report Dictionary per spec found.
static func apply(root: Node, options := {}) -> Array[Dictionary]:
	var reports: Array[Dictionary] = []
	for node in find_specs(root):
		var spec := spec_of(node)
		var rep := {"node": String(node.name), "class": spec.get("class", "?"),
			"route": spec.get("route", "?")}
		var problems := validate(spec)
		if not problems.is_empty():
			rep["built"] = false
			rep["problems"] = problems
		elif spec["route"] != "soft_body":
			rep["built"] = false
			rep["problems"] = PackedStringArray(["route %s is not built by this runtime yet" % spec["route"]])
		elif not node is MeshInstance3D:
			rep["built"] = false
			rep["problems"] = PackedStringArray(["spec on a %s, expected MeshInstance3D" % node.get_class()])
		else:
			var body = ClothBody.build(node, spec, options)
			rep.merge(body.report, true)
			rep["built"] = true
			rep["body"] = body
		reports.append(rep)
	return reports
