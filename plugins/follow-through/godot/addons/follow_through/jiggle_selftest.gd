extends SceneTree
## The jiggle spring's shape, without a body: `JiggleModifier.step` kicked and timed.
##
##   godot --headless --path <project> -s res://addons/follow_through/jiggle_selftest.gd -- \
##       [frequency_hz=2.4] [down_ratio=2.8] [ap_ratio=1.4] [damping_ratio=0.25]
##
## A breast floats up and stops hard at the bottom (Cai 2018: 73.5 N/m above rest, 658 below), so after an
## upward kick the half-period below rest is 1 / down_ratio of the one above it - about 1/3
## (research-flesh-jiggle.md, D: +-20 %). Front to back the period is 1 / ap_ratio of the side's. Each is
## measured at 30, 60 and 144 fps and must agree across them (the vertical spring changes stiffness where the
## offset crosses rest, and a frame that straddles the crossing is substepped).
##
## Checks: `down_up` (the measured below/above half-period ratio within 20 % of 1 / down_ratio, and of 1/3),
## `ap_side` (within 10 % of 1 / ap_ratio), `rates` (each ratio within 5 % across the frame rates). Prints one
## `FT_JIGGLE_SELFTEST {json}` line and `FT_SUMMARY ... PASSED|FAILED`; exits 1 on a failure.
## `down_ratio=1` is the linear spring: its ratio is 1, and `down_up` must fail on it (the control).

const JiggleModifier = preload("res://addons/follow_through/jiggle_modifier.gd")
const RATES := [30.0, 60.0, 144.0]


func _init() -> void:
	var args := {}
	for a in OS.get_cmdline_user_args():
		var kv := a.split("=", true, 1)
		if kv.size() == 2:
			args[kv[0]] = kv[1]
	var reg := {"frequency_hz": float(args.get("frequency_hz", 2.4)),
		"damping_ratio": float(args.get("damping_ratio", 0.25)),
		"down_ratio": float(args.get("down_ratio", 2.8)), "ap_ratio": float(args.get("ap_ratio", 1.4)),
		"up": Vector3.UP, "ap": Vector3.FORWARD}
	var failures := PackedStringArray()
	var out := {"params": reg.duplicate(), "rates": {}}
	out["params"].erase("up")
	out["params"].erase("ap")
	var down_up := []
	var ap_side := []
	for fps in RATES:
		var dt := 1.0 / float(fps)
		var hp := _half_periods(reg, Vector3.UP, dt)          # [above, below]
		var r_du: float = hp[1] / maxf(hp[0], 1e-9)
		var p_ap: float = _half_periods(reg, Vector3.FORWARD, dt)[0]
		var p_side: float = _half_periods(reg, Vector3.RIGHT, dt)[0]
		var r_as: float = p_ap / maxf(p_side, 1e-9)
		down_up.append(r_du)
		ap_side.append(r_as)
		out["rates"][str(fps)] = {"above_s": snappedf(hp[0], 0.0001), "below_s": snappedf(hp[1], 0.0001),
			"down_up": snappedf(r_du, 0.001), "ap_side": snappedf(r_as, 0.001)}
	var want_du := 1.0 / float(reg["down_ratio"])
	var want_as := 1.0 / float(reg["ap_ratio"])
	for i in RATES.size():
		var r: float = down_up[i]
		if absf(r - want_du) > 0.2 * want_du or absf(r - 1.0 / 3.0) > 0.2 / 3.0:
			failures.append("down_up at %d fps: below/above half-period %.3f, wants %.3f (1 / down_ratio) and 1/3, each +-20 %%" % [RATES[i], r, want_du])
		if absf(float(ap_side[i]) - want_as) > 0.1 * want_as:
			failures.append("ap_side at %d fps: %.3f, wants %.3f +-10 %%" % [RATES[i], ap_side[i], want_as])
	for series in [["down_up", down_up], ["ap_side", ap_side]]:
		var lo := 1e9
		var hi := 0.0
		for x in series[1]:
			lo = minf(lo, x)
			hi = maxf(hi, x)
		if hi > 1.05 * lo:
			failures.append("rates: %s spreads %.3f-%.3f across %s fps (over 5 %%)" % [series[0], lo, hi, RATES])
	out["failures"] = failures
	print("FT_JIGGLE_SELFTEST " + JSON.stringify(out))
	for f in failures:
		print("  FAILED  " + f)
	print("FT_SUMMARY jiggle spring selftest, %s" % ("PASSED" if failures.is_empty() else "FAILED"))
	quit(0 if failures.is_empty() else 1)


## Kick the spring along `axis` at 1 m/s and time the first half-period on each side of rest: [first, second].
## The time of each crossing is interpolated within its step.
func _half_periods(reg: Dictionary, axis: Vector3, dt: float) -> Array:
	var x := Vector3.ZERO
	var v := axis * 1.0
	var t := 0.0
	var crossings := [0.0]
	var prev := 0.0
	while t < 3.0 and crossings.size() < 3:
		var r: Array = JiggleModifier.step(reg, x, v, dt, Vector3.ZERO)
		x = r[0]
		v = r[1]
		var s := x.dot(axis)
		if t > 0.0 and signf(s) != signf(prev) and s != 0.0:
			crossings.append(t + dt * absf(prev) / maxf(absf(prev) + absf(s), 1e-12))
		prev = s
		t += dt
	if crossings.size() < 3:
		return [0.0, 0.0]
	return [crossings[1] - crossings[0], crossings[2] - crossings[1]]
