class_name GaitJitter
extends RefCounted
## Per-cycle phase and amplitude jitter with a persistent spectrum, so a looping clip stops
## reading as a loop.
##
## A baked gait is ONE cycle (rig_analysis/locomotion.py samples a single period) and Godot
## loops it, so nothing inside the clip can differ from stride to stride. The variation has to
## be added at runtime. This draws two scalars per cycle - one for timing, one for amplitude -
## and MovesController warps the playhead and the arm swing with them.
##
## THE SPECTRUM IS THE POINT. Human stride intervals are not white: successive strides are
## correlated over hundreds of cycles, with a detrended-fluctuation exponent (DFA alpha) near
## 0.8 - long-range persistent, halfway between white (0.5) and a random walk (1.0). A naive
## `randf()` gives 0.5, which is audibly and visibly wrong: it twitches instead of drifting.
## `verify_jitter.gd` measures the exponent of what this generates and ships the white
## generator (`spectrum = "white"` below) as the control that must fail that check.
##
## How the spectrum is made, cheaply: a bank of first-order relaxations (AR(1) filters) with
## geometrically spaced time constants. Each contributes a Lorentzian to the power spectrum;
## a ladder of them with weights `tau^((beta-1)/2)` sums to a 1/f^beta band over the ladder's
## range. beta 0.40 over tau 1..729 cycles measures alpha 0.80 +- 0.05 (40 seeds, 4096 cycles).
## Cost is MODES multiply-adds and MODES gaussians **per cycle**, about 1 Hz - not per frame.
##
## Nothing here accumulates. The series is bounded (every knot is clamped to KNOT_MAX sigma) and
## zero-mean, and the playhead offset it drives is bounded too - hard, not on average - so a
## stride can be early or late but the walk never drifts away from
## where the clip rate says it should be. That is what keeps planted feet from skating and
## keeps `implied_speed` time scaling honest.
##
## Reads the manifest's `variability` block, resolved by the character pipeline:
##   "variability": {"seed": int, "asymmetry": float, "jitter_phase": float, "jitter_amp": float}
## The key is ABSENT from every character built before it existed. Absent means all zeros,
## which means off - `enabled()` is false and MovesController never calls into here.

## Relaxation modes in the bank. 7 covers tau 1 -> 729 cycles.
const MODES := 7
## The fastest mode's time constant, in cycles.
const TAU0 := 1.0
## Ratio between neighbouring modes' time constants.
const TAU_RATIO := 3.0
## Spectral slope of the band: S(f) ~ 1/f^BETA. 0.40 lands DFA alpha on 0.80.
const BETA := 0.40

## Playhead offset, in cycles, at `jitter_phase` = 1. A stride can be this much early or late;
## it is a bound, not a drift. 0.06 cycles of a 1 s stride is 60 ms.
const PHASE_SPAN := 0.06
## Arm-swing scale swing at `jitter_amp` = 1: the swing is scaled by 1 +- this.
const AMP_SPAN := 0.15
## Playback-rate factor is clamped here whatever the draw: a gait never runs backwards or double.
const RATE_MIN := 0.6
const RATE_MAX := 1.4
## Every knot is clamped to this many standard deviations, which is what makes
## `PHASE_SPAN * jitter_phase * KNOT_MAX` a HARD bound on the playhead offset rather than a
## statistical one. Without it the bound is only as good as the largest draw a run happens to
## make: 4096 cycles reach about 4.2 sigma and 3707 cycles of walking reached 4.95, so a long
## enough run would eventually touch it. Clipping a 6-sigma tail (about 2e-9 of draws) costs
## nothing measurable - the DFA exponent is unchanged, because the clamp is inside `_draw_*`
## and so applies identically to the live stream and to the series the verifier measures.
const KNOT_MAX := 6.0
## The constant knot `spectrum = "flat"` draws. Non-zero, so the playhead is genuinely warped and
## the arm genuinely scaled - what it is not is DIFFERENT from one cycle to the next.
const FLAT_KNOT := 1.0

## "persistent" is the shipped generator. The others exist only as CONTROLS that must fail a
## named check in `verify_jitter.gd`, and they are here rather than in the verifier so that a
## control drives the real code path instead of a lookalike:
##   "white" - one gaussian per cycle, what a naive randf() gives: DFA ~0.5, fails the spectrum
##             check.
##   "flat"  - the same knot every cycle. The series is still a series and the playhead is still
##             warped, but nothing VARIES from stride to stride, so it fails the two checks that
##             say stride timing and arm swing differ cycle to cycle. Those checks have no other
##             control, and a "varies" check that has stopped measuring variation would otherwise
##             pass a generator that produces none.
var spectrum := "persistent"
## CONTROL for the "absent means off" check, and nothing else. When this is greater than zero a
## manifest with NO `variability` block resolves to this much jitter instead of to all zeros -
## i.e. the thing the shipped code must never do, since every character built before the seam
## existed has no block. Left at 0.0 in every shipped path; `verify_jitter.gd` sets it for one
## run so the off-by-default check has a control that must fail it.
static var absent_default := 0.0
## The resolved block, exactly as the manifest gave it (or all zeros when it had none).
var resolved := {"seed": 0, "asymmetry": 0.0, "jitter_phase": 0.0, "jitter_amp": 0.0}
## True when the manifest actually carried a `variability` block.
var from_manifest := false

var _phase_rng := RandomNumberGenerator.new()
var _amp_rng := RandomNumberGenerator.new()
var _phase_state := PackedFloat64Array()
var _amp_state := PackedFloat64Array()
var _pole := PackedFloat64Array()
var _kick := PackedFloat64Array()
var _weight := PackedFloat64Array()

# The knot either side of the cycle being played: the offset slides from `_q0` to `_q1` across it.
var _q0 := 0.0
var _q1 := 0.0
var _a0 := 1.0
var _a1 := 1.0
var _cycles := 0


## Read `variability` off a `.moves.json`. `who` is the character's id, used for the seed when
## the block gives none - and it must be stable, because the seed is part of the character.
static func from_moves(m: Dictionary, who := "") -> GaitJitter:
	var j := GaitJitter.new()
	var v: Variant = m.get("variability", null)
	var id := who
	if id == "":
		id = str(m.get("creature", m.get("name", "")))
	if v is Dictionary and not (v as Dictionary).is_empty():
		var d: Dictionary = v
		j.from_manifest = true
		j.resolved = {
			"seed": int(d.get("seed", id_seed(id))),
			"asymmetry": clampf(float(d.get("asymmetry", 0.0)), 0.0, 1.0),
			"jitter_phase": clampf(float(d.get("jitter_phase", 0.0)), 0.0, 1.0),
			"jitter_amp": clampf(float(d.get("jitter_amp", 0.0)), 0.0, 1.0),
		}
	else:
		# Every character built before the seam existed lands here. Absent is all zeros, and
		# all zeros is off - not "pick something for them". `absent_default` is the control that
		# breaks exactly that, and it is 0.0 everywhere but in one verify_jitter run.
		var d0 := clampf(absent_default, 0.0, 1.0)
		j.resolved = {"seed": id_seed(id), "asymmetry": 0.0, "jitter_phase": d0, "jitter_amp": d0}
	j.reset()
	return j


## A stable seed from a character's id. FNV-1a, kept to 31 bits so it is the same everywhere.
static func id_seed(who: String) -> int:
	var h := 2166136261
	for b in who.to_utf8_buffer():
		h = (h ^ int(b)) & 0xFFFFFFFF
		h = (h * 16777619) & 0xFFFFFFFF
	return h & 0x7FFFFFFF


func phase_gain() -> float:
	return PHASE_SPAN * float(resolved["jitter_phase"])


func amp_gain() -> float:
	return AMP_SPAN * float(resolved["jitter_amp"])


## False when the manifest asked for nothing - which is the default, and the case for every
## character built before this shipped. MovesController then does no per-frame work at all.
func enabled() -> bool:
	return phase_gain() > 0.0 or amp_gain() > 0.0


func cycles() -> int:
	return _cycles


## Start the streams over from the resolved seed. Deterministic: same seed, same series.
func reset() -> void:
	var seed_i := int(resolved["seed"])
	_phase_rng.seed = seed_i
	# A second stream, offset so timing and amplitude are not the same series twice.
	_amp_rng.seed = (seed_i ^ 0x5bf03635) & 0x7FFFFFFF
	_phase_state = PackedFloat64Array()
	_amp_state = PackedFloat64Array()
	_pole = PackedFloat64Array()
	_kick = PackedFloat64Array()
	_weight = PackedFloat64Array()
	var norm := 0.0
	for k in MODES:
		var tau: float = TAU0 * pow(TAU_RATIO, float(k))
		var a: float = exp(-1.0 / tau)
		_pole.append(a)
		_kick.append(sqrt(maxf(1.0 - a * a, 0.0)))
		var w: float = pow(tau, (BETA - 1.0) * 0.5)
		_weight.append(w)
		norm += w * w
		_phase_state.append(0.0)
		_amp_state.append(0.0)
	norm = sqrt(norm)
	for k in MODES:
		_weight[k] = _weight[k] / norm
	_cycles = 0
	# Burn in, so the first strides are not all near zero while the slow modes fill up.
	for i in 64:
		_step()
	_q0 = _draw_phase()
	_q1 = _draw_phase()
	_a0 = _draw_amp()
	_a1 = _draw_amp()


func _step() -> void:
	for k in MODES:
		_phase_state[k] = _pole[k] * _phase_state[k] + _kick[k] * _phase_rng.randfn(0.0, 1.0)
		_amp_state[k] = _pole[k] * _amp_state[k] + _kick[k] * _amp_rng.randfn(0.0, 1.0)


func _draw_phase() -> float:
	if spectrum == "white":
		# The control: what a naive randf() per cycle gives. DFA alpha ~0.5.
		return clampf(_phase_rng.randfn(0.0, 1.0), -KNOT_MAX, KNOT_MAX)
	if spectrum == "flat":
		return FLAT_KNOT           # the control: a warp that never varies
	var s := 0.0
	for k in MODES:
		_phase_state[k] = _pole[k] * _phase_state[k] + _kick[k] * _phase_rng.randfn(0.0, 1.0)
		s += _weight[k] * _phase_state[k]
	return clampf(s, -KNOT_MAX, KNOT_MAX)


func _draw_amp() -> float:
	if spectrum == "white":
		return clampf(_amp_rng.randfn(0.0, 1.0), -KNOT_MAX, KNOT_MAX)
	if spectrum == "flat":
		return FLAT_KNOT
	var s := 0.0
	for k in MODES:
		_amp_state[k] = _pole[k] * _amp_state[k] + _kick[k] * _amp_rng.randfn(0.0, 1.0)
		s += _weight[k] * _amp_state[k]
	return clampf(s, -KNOT_MAX, KNOT_MAX)


## The cycle just ended: slide to the next pair of knots.
func advance_cycle() -> void:
	_q0 = _q1
	_a0 = _a1
	_q1 = _draw_phase()
	_a1 = _draw_amp()
	_cycles += 1


## The playhead offset, in cycles, at normalised position `u` (0..1) in the cycle being played.
## Bounded by `phase_gain()`: a stride is early or late, never progressively later.
func phase_offset(u: float) -> float:
	return phase_gain() * lerpf(_q0, _q1, _smooth(u))


## d(phase_offset)/du - the playback-rate factor's jitter term.
func phase_slope(u: float) -> float:
	var t := clampf(u, 0.0, 1.0)
	return phase_gain() * (_q1 - _q0) * 6.0 * t * (1.0 - t)


## Arm-swing scale at `u`: 1 +- amp_gain().
func amp_scale(u: float) -> float:
	return 1.0 + amp_gain() * lerpf(_a0, _a1, _smooth(u))


func _smooth(u: float) -> float:
	var t := clampf(u, 0.0, 1.0)
	return t * t * (3.0 - 2.0 * t)


## The knot drawn for the end of the cycle now playing - the value `advance_cycle` last took from
## the live stream. `verify_jitter.gd` compares a run of these against `series()`, so the spectrum
## it measures is provably the series the gait is actually driven by.
func last_knot(which := "phase") -> float:
	return _q1 if which == "phase" else _a1


## `n` cycle values of one series, for a spectrum measurement. Leaves the live state alone:
## it runs a copy from the same seed.
func series(n: int, which := "phase") -> PackedFloat64Array:
	var twin := GaitJitter.new()
	twin.resolved = resolved.duplicate()
	twin.spectrum = spectrum
	twin.reset()
	var out := PackedFloat64Array()
	out.resize(n)
	for i in n:
		out[i] = twin._draw_phase() if which == "phase" else twin._draw_amp()
	return out


## Detrended fluctuation analysis of a series: the log-log slope of the RMS residual of a
## linear fit within windows, against window length. 0.5 is white, 1.0 a random walk, and a
## human's stride intervals sit near 0.8. `scales` default to 8..256 cycles, the band this
## generator's mode ladder actually covers.
static func dfa(x: PackedFloat64Array, scales := PackedInt32Array()) -> float:
	var n := x.size()
	if scales.is_empty():
		scales = PackedInt32Array([8, 11, 16, 22, 32, 45, 64, 90, 128, 181, 256])
	var mean := 0.0
	for v in x:
		mean += v
	mean /= float(n)
	var y := PackedFloat64Array()
	y.resize(n)
	var acc := 0.0
	for i in n:
		acc += x[i] - mean
		y[i] = acc
	var lx := PackedFloat64Array()
	var ly := PackedFloat64Array()
	for w in scales:
		var blocks := n / w
		if blocks < 8:
			continue
		var tot := 0.0
		var cnt := 0
		var fw := float(w)
		var sx := fw * (fw - 1.0) * 0.5
		var sxx := (fw - 1.0) * fw * (2.0 * fw - 1.0) / 6.0
		var den := fw * sxx - sx * sx
		for b in blocks:
			var sy := 0.0
			var sxy := 0.0
			for i in w:
				var v := y[b * w + i]
				sy += v
				sxy += float(i) * v
			var slope := (fw * sxy - sx * sy) / den
			var icpt := (sy - slope * sx) / fw
			for i in w:
				var d: float = y[b * w + i] - (slope * float(i) + icpt)
				tot += d * d
				cnt += 1
		if cnt > 0 and tot > 0.0:
			lx.append(log(fw))
			ly.append(log(sqrt(tot / float(cnt))))
	if lx.size() < 3:
		return NAN
	var mx := 0.0
	var my := 0.0
	for i in lx.size():
		mx += lx[i]
		my += ly[i]
	mx /= float(lx.size())
	my /= float(ly.size())
	var num := 0.0
	var dd := 0.0
	for i in lx.size():
		num += (lx[i] - mx) * (ly[i] - my)
		dd += (lx[i] - mx) * (lx[i] - mx)
	return num / dd
