extends RefCounted
## Image statistics for lookdev captures.
##
## Captures come back from the viewport as 8-bit, tonemapped, sRGB-encoded
## images, so everything here is display-referred. "Linear" values are that
## display image decoded with the sRGB curve - not scene radiance, which the
## tonemapper has already compressed.
##
## Images are reduced (nearest-neighbour, so clipped pixels stay clipped) before
## measuring. Percentages over ~100k pixels do not need the full frame, and a
## GDScript loop over a 1080p image takes seconds per view.

const MAX_WIDTH := 400
const SKY_DIFF := 40

static var _lut := PackedFloat32Array()


static func lin_lut() -> PackedFloat32Array:
	if _lut.is_empty():
		_lut.resize(256)
		for i in 256:
			var c := i / 255.0
			_lut[i] = c / 12.92 if c <= 0.04045 else pow((c + 0.055) / 1.055, 2.4)
	return _lut


static func encode_srgb(l: float) -> float:
	l = clampf(l, 0.0, 1.0)
	return l * 12.92 if l <= 0.0031308 else 1.055 * pow(l, 1.0 / 2.4) - 0.055


static func reduce(img: Image) -> Image:
	var r := img.duplicate() as Image
	if r.get_format() != Image.FORMAT_RGBA8:
		r.convert(Image.FORMAT_RGBA8)
	if r.get_width() > MAX_WIDTH:
		var h := int(round(r.get_height() * float(MAX_WIDTH) / r.get_width()))
		r.resize(MAX_WIDTH, h, Image.INTERPOLATE_NEAREST)
	return r


## Sky mask from two unshaded renders whose backgrounds were set to different
## flat colours: whatever changed between them is background. Tonemapping and
## fog can shift the colours, but not by the same amount in both, so a diff is
## sturdier than keying on one colour. Returns 1 for background pixels.
static func background_mask(a: Image, b: Image) -> PackedByteArray:
	var da := a.get_data()
	var db := b.get_data()
	var n := a.get_width() * a.get_height()
	var mask := PackedByteArray()
	mask.resize(n)
	if db.size() != da.size():
		return mask
	for i in n:
		var o := i * 4
		var d := absi(da[o] - db[o]) + absi(da[o + 1] - db[o + 1]) + absi(da[o + 2] - db[o + 2])
		mask[i] = 1 if d > SKY_DIFF else 0
	return mask


static func _percentile(hist: PackedInt32Array, total: int, q: float) -> float:
	if total == 0:
		return 0.0
	var target := q * total
	var acc := 0
	for i in hist.size():
		acc += hist[i]
		if acc >= target:
			return i / 255.0
	return 1.0


static func _r(v: float, places := 4) -> float:
	return snappedf(v, pow(10.0, -places))


## Stats for a normally lit frame: exposure, clipping, contrast, colour.
static func lit(img: Image, mask: PackedByteArray) -> Dictionary:
	var lut := lin_lut()
	var w := img.get_width()
	var h := img.get_height()
	var data := img.get_data()
	var use_mask := mask.size() == w * h
	var hist := PackedInt32Array()
	hist.resize(256)
	var bstar_by_bin := PackedFloat64Array()
	bstar_by_bin.resize(256)
	var disp := PackedFloat32Array()
	disp.resize(w * h)
	var count := 0
	var excluded := 0
	var clipped := 0
	var crushed := 0
	var sat_sum := 0.0
	var sat_hot := 0
	var log_sum := 0.0
	var a_sum := 0.0
	var b_sum := 0.0
	var lin_sum := 0.0
	for i in w * h:
		if use_mask and mask[i] == 1:
			excluded += 1
			disp[i] = -1.0
			continue
		var o := i * 4
		var r8 := data[o]
		var g8 := data[o + 1]
		var b8 := data[o + 2]
		var r := lut[r8]
		var g := lut[g8]
		var b := lut[b8]
		var y := 0.2126 * r + 0.7152 * g + 0.0722 * b
		var ydisp := encode_srgb(y)
		var bin := clampi(int(ydisp * 255.0 + 0.5), 0, 255)
		disp[i] = ydisp
		hist[bin] += 1
		count += 1
		lin_sum += y
		log_sum += log(y + 0.0001)
		var mx := maxi(r8, maxi(g8, b8))
		var mn := mini(r8, mini(g8, b8))
		if mx >= 254:
			clipped += 1
		if mx <= 4:
			crushed += 1
		var s := 0.0 if mx == 0 else float(mx - mn) / mx
		sat_sum += s
		if s > 0.9 and mx > 204:
			sat_hot += 1
		# CIELAB (D65), for colour cast and warm/cool split.
		var xx := (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
		var yy := y
		var zz := (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
		var fx := pow(xx, 1.0 / 3.0) if xx > 0.008856 else 7.787 * xx + 16.0 / 116.0
		var fy := pow(yy, 1.0 / 3.0) if yy > 0.008856 else 7.787 * yy + 16.0 / 116.0
		var fz := pow(zz, 1.0 / 3.0) if zz > 0.008856 else 7.787 * zz + 16.0 / 116.0
		var bstar := 200.0 * (fy - fz)
		a_sum += 500.0 * (fx - fy)
		b_sum += bstar
		bstar_by_bin[bin] += bstar

	if count == 0:
		return {"pixels": 0, "background_fraction": 1.0}

	# Warm/cool split: mean b* of the brightest 20% minus the darkest 30%.
	var bright_b := _mean_b_between(hist, bstar_by_bin, count, 0.8, 1.0)
	var dark_b := _mean_b_between(hist, bstar_by_bin, count, 0.0, 0.3)

	# Shadow detail: mean neighbour difference in the darkest decile relative to
	# the frame as a whole. Near zero means shadows are a flat fill; around 1
	# means they carry as much texture as everything else.
	var p10 := _percentile(hist, count, 0.10)
	var dark_diff := 0.0
	var dark_n := 0
	var mid_diff := 0.0
	var mid_n := 0
	for yv in range(h - 1):
		for xv in range(w - 1):
			var i := yv * w + xv
			var v := disp[i]
			if v < 0.0:
				continue
			var right := disp[i + 1]
			var down := disp[i + w]
			if right < 0.0 or down < 0.0:
				continue
			var d := absf(v - right) + absf(v - down)
			if v <= p10:
				dark_diff += d
				dark_n += 1
			mid_diff += d
			mid_n += 1
	var shadow_detail := 0.0
	if dark_n > 0 and mid_n > 0 and mid_diff > 0.0:
		shadow_detail = (dark_diff / dark_n) / (mid_diff / mid_n)

	var hist16 := []
	for k in 16:
		var s16 := 0
		for j in 16:
			s16 += hist[k * 16 + j]
		hist16.append(_r(float(s16) / count, 4))

	return {
		"pixels": count,
		"background_fraction": _r(float(excluded) / (w * h)),
		"luma_mean": _r(encode_srgb(lin_sum / count)),
		"luma_p1": _r(_percentile(hist, count, 0.01)),
		"luma_p5": _r(_percentile(hist, count, 0.05)),
		"luma_p25": _r(_percentile(hist, count, 0.25)),
		"luma_p50": _r(_percentile(hist, count, 0.50)),
		"luma_p75": _r(_percentile(hist, count, 0.75)),
		"luma_p95": _r(_percentile(hist, count, 0.95)),
		"luma_p99": _r(_percentile(hist, count, 0.99)),
		"luma_log_average": _r(encode_srgb(exp(log_sum / count))),
		"clipped_pct": _r(100.0 * clipped / count, 2),
		"crushed_pct": _r(100.0 * crushed / count, 2),
		"saturation_mean": _r(sat_sum / count),
		"saturation_hot_pct": _r(100.0 * sat_hot / count, 2),
		"lab_a_mean": _r(a_sum / count, 2),
		"lab_b_mean": _r(b_sum / count, 2),
		"warm_cool_split": _r(bright_b - dark_b, 2),
		"shadow_detail": _r(shadow_detail, 3),
		"histogram16": hist16,
	}


static func _mean_b_between(hist: PackedInt32Array, bsum: PackedFloat64Array, total: int, q0: float, q1: float) -> float:
	var lo := q0 * total
	var hi := q1 * total
	var acc := 0
	var s := 0.0
	var n := 0
	for i in 256:
		var c := hist[i]
		if c == 0:
			continue
		# Bins straddling a boundary count whole; with 256 bins that bias is small.
		if acc + c > lo and acc < hi:
			s += bsum[i]
			n += c
		acc += c
	return s / n if n > 0 else 0.0


## Stats for DEBUG_DRAW_UNSHADED: the albedo the camera sees. Flags base colours
## outside the physically plausible 30-240 sRGB band. Metals legitimately sit
## above it, and emissive or text (Label3D) pixels will too - so read these as
## "go look", not as errors.
static func albedo(img: Image, mask: PackedByteArray) -> Dictionary:
	var lut := lin_lut()
	var w := img.get_width()
	var h := img.get_height()
	var data := img.get_data()
	var use_mask := mask.size() == w * h
	var count := 0
	var dark := 0
	var bright := 0
	var oversat := 0
	var lin_sum := 0.0
	for i in w * h:
		if use_mask and mask[i] == 1:
			continue
		var o := i * 4
		var r8 := data[o]
		var g8 := data[o + 1]
		var b8 := data[o + 2]
		var mx := maxi(r8, maxi(g8, b8))
		var mn := mini(r8, mini(g8, b8))
		count += 1
		if mx < 30:
			dark += 1
		if mx > 240:
			bright += 1
		if mx > 60 and float(mx - mn) / mx > 0.85:
			oversat += 1
		lin_sum += 0.2126 * lut[r8] + 0.7152 * lut[g8] + 0.0722 * lut[b8]
	if count == 0:
		return {"pixels": 0}
	return {
		"pixels": count,
		"albedo_mean_linear": _r(lin_sum / count),
		"albedo_too_dark_pct": _r(100.0 * dark / count, 2),
		"albedo_too_bright_pct": _r(100.0 * bright / count, 2),
		"albedo_oversaturated_pct": _r(100.0 * oversat / count, 2),
	}


## Stats for DEBUG_DRAW_LIGHTING: light arriving at surfaces, without albedo.
## The spread between lit and shaded areas is what tells a sun-and-sky scene
## from one drowned in flat ambient.
static func lighting(img: Image, mask: PackedByteArray) -> Dictionary:
	var lut := lin_lut()
	var w := img.get_width()
	var h := img.get_height()
	var data := img.get_data()
	var use_mask := mask.size() == w * h
	var hist := PackedInt32Array()
	hist.resize(256)
	var count := 0
	var clipped := 0
	for i in w * h:
		if use_mask and mask[i] == 1:
			continue
		var o := i * 4
		var y := 0.2126 * lut[data[o]] + 0.7152 * lut[data[o + 1]] + 0.0722 * lut[data[o + 2]]
		hist[clampi(int(encode_srgb(y) * 255.0 + 0.5), 0, 255)] += 1
		if maxi(data[o], maxi(data[o + 1], data[o + 2])) >= 254:
			clipped += 1
		count += 1
	if count == 0:
		return {"pixels": 0}
	var p10 := _decode(_percentile(hist, count, 0.10))
	var p50 := _decode(_percentile(hist, count, 0.50))
	var p90 := _decode(_percentile(hist, count, 0.90))
	var ratio := p90 / maxf(p10, 0.001)
	return {
		"pixels": count,
		"lighting_p10_linear": _r(p10),
		"lighting_p50_linear": _r(p50),
		"lighting_p90_linear": _r(p90),
		"lit_to_shade_ratio": _r(ratio, 2),
		"lit_to_shade_stops": _r(log(ratio) / log(2.0), 2),
		"lighting_clipped_pct": _r(100.0 * clipped / count, 2),
	}


static func _decode(v: float) -> float:
	return lin_lut()[clampi(int(v * 255.0 + 0.5), 0, 255)]


## Mean of a disk in a full-resolution image, for reading a probe sphere.
static func disk_mean(img: Image, center: Vector2, radius: float) -> Dictionary:
	var lut := lin_lut()
	var r := maxf(radius, 1.0)
	var sum := 0.0
	var n := 0
	for yv in range(int(center.y - r), int(center.y + r) + 1):
		for xv in range(int(center.x - r), int(center.x + r) + 1):
			if xv < 0 or yv < 0 or xv >= img.get_width() or yv >= img.get_height():
				continue
			if Vector2(xv, yv).distance_to(center) > r:
				continue
			var c := img.get_pixel(xv, yv)
			sum += 0.2126 * lut[c.r8] + 0.7152 * lut[c.g8] + 0.0722 * lut[c.b8]
			n += 1
	if n == 0:
		return {"visible": false}
	var mean_lin := sum / n
	return {"visible": true, "display": _r(encode_srgb(mean_lin)), "linear": _r(mean_lin), "pixels": n}
