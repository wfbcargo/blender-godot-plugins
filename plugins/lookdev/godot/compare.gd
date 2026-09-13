extends SceneTree
## lookdev compare: side-by-side images and stat deltas for pairs of captures.
##
##   godot --headless --path <project> --script <this> -- --pairs pairs.json --out <dir>
##
## pairs.json is [{"a": png, "b": png, "name": str}, ...]. For each pair it
## writes <name>_ab.png (A left) and <name>_ba.png (B left). Vision judges
## favour one position often enough that a verdict should come from asking both
## ways round and keeping it only when the two answers agree.

const Common := preload("common.gd")
const Stats := preload("stats.gd")

const GAP := 8


func _initialize() -> void:
	var args := Common.parse_user_args()
	var pairs: Variant = Common.load_json(str(args.get("pairs", "")))
	var out_dir := str(args.get("out", ""))
	if not pairs is Array:
		Common.fail(self, "cannot read pairs file")
		return
	var results := []
	for pair in pairs:
		var a := Image.load_from_file(str(pair["a"]))
		var b := Image.load_from_file(str(pair["b"]))
		if a == null or b == null:
			results.append({"name": pair["name"], "error": "could not load both images"})
			continue
		a.convert(Image.FORMAT_RGBA8)
		b.convert(Image.FORMAT_RGBA8)
		var name := str(pair["name"])
		var entry := {
			"name": name,
			"a": pair["a"],
			"b": pair["b"],
			"size_match": a.get_size() == b.get_size(),
			"ab": _side_by_side(a, b, out_dir.path_join(name + "_ab.png")),
			"ba": _side_by_side(b, a, out_dir.path_join(name + "_ba.png")),
		}
		if entry["size_match"]:
			entry["metrics"] = a.compute_image_metrics(b, true)
		entry["a_stats"] = Stats.lit(Stats.reduce(a), PackedByteArray())
		entry["b_stats"] = Stats.lit(Stats.reduce(b), PackedByteArray())
		results.append(entry)
	var f := FileAccess.open(out_dir.path_join("compare.json"), FileAccess.WRITE)
	f.store_string(JSON.stringify({"pairs": results}, "  ", false))
	f.close()
	Common.emit("done", {"pairs": results.size()})
	quit(0)


func _side_by_side(left: Image, right: Image, path: String) -> String:
	var h := maxi(left.get_height(), right.get_height())
	var img := Image.create(left.get_width() + GAP + right.get_width(), h, false, Image.FORMAT_RGBA8)
	img.fill(Color(0.5, 0.5, 0.5))
	img.blit_rect(left, Rect2i(Vector2i.ZERO, left.get_size()), Vector2i(0, 0))
	img.blit_rect(right, Rect2i(Vector2i.ZERO, right.get_size()), Vector2i(left.get_width() + GAP, 0))
	img.save_png(path)
	return path
