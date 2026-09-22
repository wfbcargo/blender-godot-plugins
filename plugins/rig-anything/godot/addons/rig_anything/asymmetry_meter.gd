class_name AsymmetryMeter
extends RefCounted
## A body's own left against its right, measured off the PLAYING skeleton.
##
## rig-anything bakes a fixed per-character left/right asymmetry into every gait clip
## (`scripts/rig_analysis/variability.py`, `[variability] asymmetry`), and measures it at bake time
## with `variability.measure` off Blender's playback. This is the engine's half: an independent
## reimplementation of the same measures with the same definitions, read off a Skeleton3D while
## its clip plays, so the two engines can be held against each other on the same baked clip.
##
##     var meter := AsymmetryMeter.new(skeleton, manifest)   # manifest: the parsed .moves.json
##     # every physics tick, with the playing clip's phase in 0..1:
##     meter.sample(fposmod(anim.current_animation_position / anim.current_animation_length, 1.0))
##     var r := meter.report()          # once meter.cycles() >= a few
##     r["arm_swing_deg"]["ratio"]      # +lat over -lat
##
## `report()` is keyed by channel (`CHANNELS`); each is {plus_lat, minus_lat, ratio, index, diff}
## with `index` the symmetry index 2|L-R|/|L+R| (0 is mirror-symmetric) and `diff` L-R. Beside
## them: `stance_offset_m` (the +lat foot's stance position minus the -lat foot's), `fourier`
## (each per-side signal's once-per-cycle amplitude, beside the peak-to-peak the channel reports),
## `cycles`, `samples`, `bones` and `problems`. Every number is the free value - nothing is clamped.
##
##   arm_swing_deg      the carry angle's peak-to-peak: the palm (half a hand past the wrist,
##                      along the hand bone) seen from the shoulder, atan2(fwd, -up), degrees
##   step_length_m      the gait lab's step: stride/2 +- stance_offset, per side
##   stride_m           each foot's OWN fore-aft travel off the hips - the no-skate invariant,
##                      which must read the same on both sides
##   shoulder_dip_m     the arm root's height over the mean hip height, peak-to-peak: bake-time's
##                      definition, so the two engines compare
##   shoulder_dip_chest_m  the arm root's height in a frame that RIDES THE CHEST (the lesson
##                      grungist-creek's motion_demo took four attempts to learn: in skeleton space
##                      the spine's own motion swamps the dip, in the girdle's own frame it is
##                      identically zero, and mirrored sides cancel unless each carries its sign).
##                      Engine-only: there is no bake-time twin to compare it with
##   lag_cycles         each arm's once-per-cycle phase behind its CONTRALATERAL leg (the leg's
##                      fore-aft position off the hips against the arm's carry angle), in cycles,
##                      wrapped to [-0.5, 0.5). The draw moves the two sides apart by twice its
##                      `lag`; ratio and index are ill-conditioned near zero, so read `diff`
##
## WHAT IT READS, and what it never does. Bone roles come from the manifest exactly the way
## `verify_moves.gd`'s MovesController and grungist-creek's motion_demo.gd take them: the legs
## are `contacts.<gait>.feet[]` (`leg` the thigh, `bone` the foot), the arms are the KEYS of
## `arm_pose.<clip>` (each arm's upper bone), and the hand is two bones down the arm's own chain
## (the child with the longest chain below it, the rule rig-anything's body map walks). Nothing
## else in the manifest is read: not the `variability` block, not the `arm_pose` VALUES (which
## are the bake's measured swing), not `gaits`, not the stance spans. The skeleton's rest pose
## gives up (the skeleton's own), forward (where the feet point - each foot bone runs ankle to
## toe), lateral (up x forward, bake-time's `lat`) and each limb's side. So the meter cannot
## read the answer: verify_asymmetry.gd's `poison=1` control rewrites every one of those fields
## and the numbers must not move by one digit.
##
## `swap_sides` tells the meter +lat is -lat - the side-swap control: every ratio must invert,
## every diff and stance_offset flip sign.
##
## Only whole cycles are reported: samples are kept with their unwrapped phase and `report()`
## uses the window [first, first + floor(cycles)), so a meter stopped mid-stride does not weight
## one part of the cycle twice. Sample at a steady rate; the Fourier sums assume even spacing.

const CHANNELS := ["arm_swing_deg", "step_length_m", "stride_m", "shoulder_dip_m",
		"shoulder_dip_chest_m", "lag_cycles"]

## A leaf hand's length as a share of its forearm (see `_bone_length`).
const LEAF_HAND_SHARE := 0.5

var skeleton: Skeleton3D
var swap_sides := false
## Why a channel is missing, in words. Empty on a biped with arms.
var problems: PackedStringArray = []

var _legs: Array = []       # [{name, upper, end, side, fwd_pos}]
var _arms: Array = []       # [{name, upper, end, hand_len, side, fwd_pos, contra}]
var _chest := -1
var _up := Vector3.UP
var _fwd := Vector3.ZERO
var _lat := Vector3.ZERO
var _chest_up := Vector3.UP

var _u := PackedFloat64Array()                  # unwrapped phase of every sample
var _last_phase := -1.0
var _turns := 0.0
var _sig := {}                                  # signal key -> PackedFloat64Array


func _init(skel: Skeleton3D, manifest: Dictionary) -> void:
	skeleton = skel
	if skeleton == null:
		problems.append("no skeleton")
		return
	_find_legs(manifest)
	_find_arms(manifest)
	_axes()


# ----------------------------------------------------------------- bones and axes, from the rest pose

func _find_legs(m: Dictionary) -> void:
	var contacts: Dictionary = m.get("contacts", {})
	for gait in contacts:
		var feet: Array = contacts[gait].get("feet", [])
		if feet.size() < 2:
			continue
		for f in feet:
			var up_i := skeleton.find_bone(String(f.get("leg", "")))
			var end_i := skeleton.find_bone(String(f.get("bone", "")))
			if up_i < 0 or end_i < 0:
				problems.append("leg %s / foot %s not in the skeleton" % [f.get("leg", ""), f.get("bone", "")])
				continue
			_legs.append({"name": String(f.get("leg", "")), "upper": up_i, "end": end_i})
		break
	if _legs.size() < 2:
		problems.append("fewer than two legs in the manifest's contacts")


func _find_arms(m: Dictionary) -> void:
	var pose: Dictionary = m.get("arm_pose", {})
	var names: Array = []
	for clip in pose:
		for b in pose[clip]:          # the KEYS only: the values are the bake's measurement
			if not names.has(b):
				names.append(b)
	for n in names:
		var up_i := skeleton.find_bone(String(n))
		if up_i < 0:
			problems.append("arm %s not in the skeleton" % n)
			continue
		var lower := _longest_child(up_i)
		var hand := _longest_child(lower) if lower >= 0 else -1
		if hand < 0:
			problems.append("arm %s has no hand two bones down its chain" % n)
			continue
		_arms.append({"name": String(n), "upper": up_i, "end": hand, "hand_len": _bone_length(hand)})
	if _arms.size() < 2:
		problems.append("fewer than two arms in the manifest's arm_pose")


## The child with the longest chain below it (ties: the first), or -1. rig-anything's body map
## walks a limb the same way, so a helper leaf beside the chain is never taken for the next bone.
func _longest_child(i: int) -> int:
	var best := -1
	var depth := -1
	for c in skeleton.get_bone_children(i):
		var d := _depth(c)
		if d > depth:
			best = c
			depth = d
	return best


func _depth(i: int) -> int:
	var d := 0
	for c in skeleton.get_bone_children(i):
		d = maxi(d, _depth(c))
	return d + 1


## A bone's length, which a skeleton does not store: the distance along its own axis (+Y, which
## glTF keeps from Blender) to the furthest child's head. A LEAF hand has no tail in the file at
## all, so it is estimated as half its forearm (`LEAF_HAND_SHARE`) - the one number here that is
## an estimate rather than a reading. The palm point only moves the carry angle as far as the hand
## bends off the shoulder-wrist line, so it is second order: on the fixture Figure (hand 0.106 m,
## forearm 0.200 m, so this estimate is 6 mm short) a centimetre of hand moves a walk's swing by
## about 0.07 degrees and a run's by 0.01.
func _bone_length(i: int) -> float:
	var rest := skeleton.get_bone_global_rest(i)
	var axis := rest.basis.y.normalized()
	var best := 0.0
	for c in skeleton.get_bone_children(i):
		best = maxf(best, (skeleton.get_bone_global_rest(c).origin - rest.origin).dot(axis))
	if best > 0.0:
		return best
	var p := skeleton.get_bone_parent(i)
	if p < 0:
		return 0.0
	return LEAF_HAND_SHARE * (rest.origin - skeleton.get_bone_global_rest(p).origin).length()


func _axes() -> void:
	if skeleton.is_inside_tree():
		_up = (skeleton.global_transform.basis.inverse() * Vector3.UP).normalized()
	# forward: where the feet point. Each foot bone runs from the ankle toward the toes.
	var f := Vector3.ZERO
	for l in _legs:
		var y := skeleton.get_bone_global_rest(l["end"]).basis.y.normalized()
		f += y - _up * y.dot(_up)
	if f.length() < 1e-6:
		problems.append("the feet point straight up or down: no forward")
		return
	_fwd = f.normalized()
	_lat = _up.cross(_fwd).normalized()          # bake-time's `lat` = up x fwd, the same side
	# the sides, about the legs' own midline, as the bake takes them
	var mid := 0.0
	for l in _legs:
		mid += skeleton.get_bone_global_rest(l["upper"]).origin.dot(_lat)
	mid /= maxf(1.0, float(_legs.size()))
	for limb in _legs + _arms:
		var o := skeleton.get_bone_global_rest(limb["upper"]).origin
		limb["side"] = 1 if o.dot(_lat) > mid else -1
		limb["fwd_pos"] = o.dot(_fwd)
	for a in _arms:
		var best := -1
		for k in _legs.size():
			if _legs[k]["side"] == a["side"]:
				continue
			if best < 0 or absf(_legs[k]["fwd_pos"] - a["fwd_pos"]) < absf(_legs[best]["fwd_pos"] - a["fwd_pos"]):
				best = k
		a["contra"] = best
	# the chest: what every arm hangs from
	var arm_roots: Array = []
	for a in _arms:
		arm_roots.append(a["upper"])
	_chest = _common_parent(arm_roots)
	if _chest >= 0:
		_chest_up = (skeleton.get_bone_global_rest(_chest).basis.inverse() * _up).normalized()


func _common_parent(bones: Array) -> int:
	if bones.is_empty():
		return -1
	var chain: Array = []
	var i: int = skeleton.get_bone_parent(bones[0])
	while i >= 0:
		chain.append(i)
		i = skeleton.get_bone_parent(i)
	for b in chain:
		var all_under := true
		for other in bones.slice(1):
			var j: int = skeleton.get_bone_parent(other)
			var found := false
			while j >= 0:
				if j == b:
					found = true
					break
				j = skeleton.get_bone_parent(j)
			if not found:
				all_under = false
				break
		if all_under:
			return b
	return -1


# ----------------------------------------------------------------- sampling

## Whole cycles seen so far.
func cycles() -> float:
	return 0.0 if _u.size() < 2 else _u[_u.size() - 1] - _u[0]


func reset() -> void:
	_u = PackedFloat64Array()
	_last_phase = -1.0
	_turns = 0.0
	_sig = {}


## Read the skeleton now. `phase` is the playing clip's position in its cycle, 0..1.
func sample(phase: float) -> void:
	if _fwd == Vector3.ZERO:
		return
	phase = fposmod(phase, 1.0)
	if _last_phase >= 0.0 and phase < _last_phase - 0.5:
		_turns += 1.0
	_last_phase = phase
	_u.append(_turns + phase)
	var hips_f := 0.0
	var hips_h := 0.0
	for l in _legs:
		var o := skeleton.get_bone_global_pose(l["upper"]).origin
		hips_f += o.dot(_fwd)
		hips_h += o.dot(_up)
	hips_f /= float(_legs.size())
	hips_h /= float(_legs.size())
	for l in _legs:
		_put("x:" + l["name"], skeleton.get_bone_global_pose(l["end"]).origin.dot(_fwd) - hips_f)
	var into_chest := Transform3D.IDENTITY
	if _chest >= 0:
		into_chest = skeleton.get_bone_global_pose(_chest).affine_inverse()
	for a in _arms:
		var sh := skeleton.get_bone_global_pose(a["upper"]).origin
		var hand := skeleton.get_bone_global_pose(a["end"])
		var v := hand.origin + hand.basis.y.normalized() * (0.5 * float(a["hand_len"])) - sh
		_put("carry:" + a["name"], rad_to_deg(atan2(v.dot(_fwd), -v.dot(_up))))
		_put("dip:" + a["name"], sh.dot(_up) - hips_h)
		if _chest >= 0:
			_put("chest:" + a["name"], (into_chest * sh).dot(_chest_up))


func _put(key: String, value: float) -> void:
	if not _sig.has(key):
		_sig[key] = PackedFloat64Array()
	_sig[key].append(value)


# ----------------------------------------------------------------- the report

func report() -> Dictionary:
	var out := {"cycles": 0, "samples": 0, "problems": Array(problems), "swap_sides": swap_sides,
		"bones": _bones()}
	var whole := int(floor(cycles() + 1e-9))
	if whole < 1:
		out["problems"].append("fewer than one whole cycle sampled")
		return out
	var u0 := _u[0]
	var n := 0
	while n < _u.size() and _u[n] < u0 + float(whole) - 1e-9:
		n += 1
	out["cycles"] = whole
	out["samples"] = n
	var s := -1 if swap_sides else 1

	# legs: each foot's travel (stride), its stance position (the mean of the forward half of its
	# travel, which is where it plants), and the Fourier phase for the lag
	var travel := {}
	var pos := {}
	var fourier := {}
	for l in _legs:
		var xs: PackedFloat64Array = _sig["x:" + l["name"]].slice(0, n)
		var lo := _min(xs)
		var hi := _max(xs)
		travel[l["name"]] = hi - lo
		var cut := 0.5 * (lo + hi)
		var sum := 0.0
		var k := 0
		for x in xs:
			if x >= cut:
				sum += x
				k += 1
		pos[l["name"]] = sum / maxf(1.0, float(k))
	var strides := {}
	var plus_pos := []
	var minus_pos := []
	var stride_all := 0.0
	for l in _legs:
		var side: int = l["side"] * s
		_push(strides, side, travel[l["name"]])
		(plus_pos if side > 0 else minus_pos).append(pos[l["name"]])
		stride_all += travel[l["name"]]
		_push_amp(fourier, "stride_m", side, _amp(_sig["x:" + l["name"]].slice(0, n), _u.slice(0, n)))
	stride_all /= maxf(1.0, float(_legs.size()))
	if not plus_pos.is_empty() and not minus_pos.is_empty():
		var off := _mean(plus_pos) - _mean(minus_pos)
		out["stance_offset_m"] = off
		out["step_length_m"] = _pair({1: [0.5 * stride_all + off], -1: [0.5 * stride_all - off]})
	out["stride_m"] = _pair(strides)

	# arms: carry-angle range, shoulder height over the hips, height in the chest's frame, lag
	var swings := {}
	var dips := {}
	var chest := {}
	var lags := {}
	var uu := _u.slice(0, n)
	for a in _arms:
		var side: int = a["side"] * s
		var carry: PackedFloat64Array = _sig["carry:" + a["name"]].slice(0, n)
		_push(swings, side, _max(carry) - _min(carry))
		_push_amp(fourier, "arm_swing_deg", side, _amp(carry, uu))
		var d: PackedFloat64Array = _sig["dip:" + a["name"]].slice(0, n)
		_push(dips, side, _max(d) - _min(d))
		_push_amp(fourier, "shoulder_dip_m", side, _amp(d, uu))
		if _sig.has("chest:" + a["name"]):
			var c: PackedFloat64Array = _sig["chest:" + a["name"]].slice(0, n)
			_push(chest, side, _max(c) - _min(c))
			_push_amp(fourier, "shoulder_dip_chest_m", side, _amp(c, uu))
		if a.get("contra", -1) >= 0:
			var leg: Dictionary = _legs[a["contra"]]
			var lag := _phase(_sig["x:" + leg["name"]].slice(0, n), uu) - _phase(carry, uu)
			_push(lags, side, fposmod(lag + 0.5, 1.0) - 0.5)
	out["arm_swing_deg"] = _pair(swings)
	out["shoulder_dip_m"] = _pair(dips)
	out["shoulder_dip_chest_m"] = _pair(chest)
	out["lag_cycles"] = _pair(lags)
	out["fourier"] = fourier
	return out


func _bones() -> Dictionary:
	var b := {"legs": {}, "arms": {}, "chest": skeleton.get_bone_name(_chest) if _chest >= 0 else "",
		"up": _up, "forward": _fwd, "lateral": _lat}
	for l in _legs:
		b["legs"][l["name"]] = {"foot": skeleton.get_bone_name(l["end"]), "side": l.get("side", 0)}
	for a in _arms:
		b["arms"][a["name"]] = {"hand": skeleton.get_bone_name(a["end"]), "side": a.get("side", 0),
			"hand_len": a["hand_len"],
			"contra": _legs[a["contra"]]["name"] if a.get("contra", -1) >= 0 else ""}
	return b


func _push(d: Dictionary, side: int, v: float) -> void:
	if not d.has(side):
		d[side] = []
	d[side].append(v)


func _push_amp(f: Dictionary, channel: String, side: int, v: float) -> void:
	if not f.has(channel):
		f[channel] = {"plus_lat_amp": 0.0, "minus_lat_amp": 0.0}
	f[channel]["plus_lat_amp" if side > 0 else "minus_lat_amp"] = v


## {plus_lat, minus_lat, ratio, index, diff}, or {} with fewer than two sides. The index is
## 2|L-R|/|L+R|, 0 when L+R is 0.
func _pair(per_side: Dictionary) -> Dictionary:
	if not per_side.has(1) or not per_side.has(-1):
		return {}
	var p := _mean(per_side[1])
	var m := _mean(per_side[-1])
	var tot := p + m
	return {"plus_lat": p, "minus_lat": m, "ratio": p / m if absf(m) > 1e-12 else null,
		"index": 2.0 * absf(p - m) / absf(tot) if absf(tot) > 1e-12 else 0.0, "diff": p - m}


func _mean(a: Array) -> float:
	var t := 0.0
	for v in a:
		t += float(v)
	return t / maxf(1.0, float(a.size()))


func _min(a: PackedFloat64Array) -> float:
	var v := INF
	for x in a:
		v = minf(v, x)
	return v


func _max(a: PackedFloat64Array) -> float:
	var v := -INF
	for x in a:
		v = maxf(v, x)
	return v


## Once-per-cycle Fourier coefficient of xs at the unwrapped phases u: [re, im].
func _f1(xs: PackedFloat64Array, u: PackedFloat64Array) -> Vector2:
	var re := 0.0
	var im := 0.0
	for k in xs.size():
		re += xs[k] * cos(TAU * u[k])
		im -= xs[k] * sin(TAU * u[k])
	return Vector2(re, im)


## Phase of the once-per-cycle component, in cycles: where in the cycle it peaks, negated.
func _phase(xs: PackedFloat64Array, u: PackedFloat64Array) -> float:
	var f := _f1(xs, u)
	return atan2(f.y, f.x) / TAU


## Amplitude of the once-per-cycle component, in the signal's own units (half its peak-to-peak
## for a pure sinusoid).
func _amp(xs: PackedFloat64Array, u: PackedFloat64Array) -> float:
	return 0.0 if xs.is_empty() else 2.0 * _f1(xs, u).length() / float(xs.size())
