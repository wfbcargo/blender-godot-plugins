// lookdev stipple: find a dithered, periodic high-frequency pattern in the shadowed skin of a render.
//
//   node lookdev.mjs stipple <png> [--region x,y,w,h] [--json] [--out crop.png]
//
// What it is for: Godot's directional soft shadows at the default "soft low" filter quality alias
// against the shadow map's texels on surfaces turned from the sun, and draw a regular lattice of lit
// dots a few pixels apart over shadowed skin (the front of the neck, the sides of the fingers). The eye
// finds it at once; exposure and colour statistics do not.
//
// How: luma, minus its 5x5 box mean, is the image's fine detail. Only shadowed, smooth skin is kept
// (warmer than blue by `warmth`, 7x7 mean luma over `min_luma` and under `shadow` of the region's 95th
// percentile, and no edge: the 7x7 mean's own gradient small, and nothing else within `margin` px), because hair, lashes, silhouettes and the
// stage are high-frequency too. Over those pixels the
// detail's autocorrelation is measured at every offset within 8 px beyond the first ring. A dither
// lattice repeats: some offset (its period) correlates strongly with itself and half of it does not.
// Pores, noise and skin texture correlate at neither; a crease or a finger's edge at both. `lattice` is
// the best correlation at an offset less the (positive part of the) correlation at half of it, taken as the
// weaker of the best offset and the best one at least 30 degrees from it (parallel strands repeat in one
// direction only; a dither lattice in two), in 96 px windows so a strip a finger wide is not diluted by a
// large region. `contrast` is the worst window's detail RMS as a share of its luma; the image stipples when
// both pass. Both are reported as measured (with the raw and half-period correlations), never clamped.
//
// Region: pixels (x,y,w,h), or fractions of the image when every number is at most 1.

import { readPNG, writePNG, crop } from "./png.mjs";

export const STIPPLE_LIMITS = { lattice: 0.25, contrast: 0.012, shadow: 0.75, edge: 0.02, min_pixels: 1500, window: 96,
  warmth: 1.1, min_luma: 0.06, margin: 3 };

function box(src, w, h, r) {
  // separable box mean with clamped edges
  const tmp = new Float64Array(w * h);
  const out = new Float64Array(w * h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let s = 0;
      for (let k = -r; k <= r; k++) s += src[y * w + Math.min(w - 1, Math.max(0, x + k))];
      tmp[y * w + x] = s / (2 * r + 1);
    }
  }
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let s = 0;
      for (let k = -r; k <= r; k++) s += tmp[Math.min(h - 1, Math.max(0, y + k)) * w + x];
      out[y * w + x] = s / (2 * r + 1);
    }
  }
  return out;
}

export function parseRegion(spec, img) {
  if (!spec) return [0, 0, img.width, img.height];
  const n = String(spec).split(",").map(Number);
  if (n.length !== 4 || n.some((v) => !(v >= 0))) throw new Error("--region must be x,y,w,h");
  const frac = n.every((v) => v <= 1);
  const [x, y, w, h] = frac ? [n[0] * img.width, n[1] * img.height, n[2] * img.width, n[3] * img.height] : n;
  const X = Math.max(0, Math.min(img.width - 1, Math.round(x)));
  const Y = Math.max(0, Math.min(img.height - 1, Math.round(y)));
  return [X, Y, Math.max(1, Math.min(img.width - X, Math.round(w))), Math.max(1, Math.min(img.height - Y, Math.round(h)))];
}

export function stipple(img, region = null, limits = STIPPLE_LIMITS) {
  const [X, Y, w, h] = parseRegion(region, img);
  const L = new Float64Array(w * h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = 4 * ((Y + y) * img.width + X + x);
      L[y * w + x] = (0.2126 * img.data[i] + 0.7152 * img.data[i + 1] + 0.0722 * img.data[i + 2]) / 255;
    }
  }
  const m5 = box(L, w, h, 2);
  const m7 = box(L, w, h, 3);
  const sorted = Float64Array.from(m7).sort();
  const p95 = sorted[Math.floor(0.95 * (sorted.length - 1))];
  const cand = new Float64Array(w * h);
  const M = 8;
  for (let y = M; y < h - M; y++) {
    for (let x = M; x < w - M; x++) {
      const i = y * w + x;
      const gx = (m7[i + 3] - m7[i - 3]) / 6;
      const gy = (m7[i + 3 * w] - m7[i - 3 * w]) / 6;
      const edge = Math.hypot(gx, gy);
      const px = 4 * ((Y + y) * img.width + X + x);
      const R = img.data[px], B = img.data[px + 2];
      // skin: warmer than it is blue (a grey floor, backdrop or sky is not skin), and not near black (hair)
      const skin = R > limits.warmth * B && (R - B) / Math.max(1, R + img.data[px + 1] + B) > 0.03;
      if (skin && m7[i] > limits.min_luma && m7[i] < limits.shadow * p95 && edge < limits.edge * Math.max(m7[i], 0.05) * 3) {
        cand[i] = 1;
      }
    }
  }
  // and not within `margin` px of anything else: an aliased silhouette's stair-steps repeat too
  const near = box(cand, w, h, limits.margin);
  const mask = new Uint8Array(w * h);
  const r = new Float64Array(w * h);
  let n = 0;
  let sq = 0;
  let base = 0;
  for (let i = 0; i < w * h; i++) {
    if (cand[i] && near[i] > 0.999) {
      mask[i] = 1;
      r[i] = L[i] - m5[i];
      n++;
      sq += r[i] * r[i];
      base += m7[i];
    }
  }
  const result = {
    region: [X, Y, w, h], pixels: n, shadow_luma: n ? base / n : null,
    contrast: null, lattice: null, correlation: null, lag: null, stipple: false, limits, why: "",
  };
  if (n < limits.min_pixels) {
    result.why = `only ${n} shadowed smooth pixels in the region (need ${limits.min_pixels}): nothing to judge`;
    return result;
  }
  result.contrast = Math.sqrt(sq / n) / (base / n);
  // The pattern can be a strip a finger wide in a large region, so it is looked for window by window
  // (WIN px, half overlapping) and the region reports its worst window.
  const scan = (x0, y0, x1, y1) => {
    let wn = 0, wsq = 0, wbase = 0;
    for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) {
      const i = y * w + x;
      if (mask[i]) { wn++; wsq += r[i] * r[i]; wbase += m7[i]; }
    }
    if (wn < limits.min_pixels) return null;
    const corrAt = (dx, dy) => {
      let sab = 0, saa = 0, sbb = 0, k = 0;
      for (let y = y0; y < y1; y++) {
        const yj = y + dy;
        if (yj < M || yj >= h - M) continue;
        for (let x = x0; x < x1; x++) {
          const xj = x + dx;
          if (xj < M || xj >= w - M) continue;
          const i = y * w + x;
          const j = yj * w + xj;
          if (!mask[i] || !mask[j]) continue;
          sab += r[i] * r[j];
          saa += r[i] * r[i];
          sbb += r[j] * r[j];
          k++;
        }
      }
      return k < limits.min_pixels / 2 || saa <= 0 || sbb <= 0 ? null : sab / Math.sqrt(saa * sbb);
    };
    // A lattice repeats: the detail matches itself one period away and not half a period away. An edge, a
    // crease or a strand matches itself all along its length, so both are high and their difference is not.
    // Parallel strands (hair, brows, lashes) repeat across themselves too, but in one direction only; a dither
    // is a lattice and repeats along two. So the window's lattice is the weaker of its best repeat and its
    // best repeat at least 30 degrees from that one.
    const peaks = [];
    for (let dy = 0; dy <= M; dy++) {
      for (let dx = -M; dx <= M; dx++) {
        if (dy === 0 && dx <= 0) continue;
        if (Math.max(Math.abs(dx), Math.abs(dy)) < 2) continue;
        const c = corrAt(dx, dy);
        if (c === null) continue;
        const hc = corrAt(Math.round(dx / 2), Math.round(dy / 2)) ?? 0;
        peaks.push({ lag: [dx, dy], peak: c - Math.max(0, hc), c, hc });
      }
    }
    if (!peaks.length) return null;
    peaks.sort((a0, b0) => b0.peak - a0.peak);
    const first = peaks[0];
    const cosMax = Math.cos((30 * Math.PI) / 180);
    const second = peaks.find((q) => {
      const cos = Math.abs(q.lag[0] * first.lag[0] + q.lag[1] * first.lag[1]) / (Math.hypot(...q.lag) * Math.hypot(...first.lag));
      return cos < cosMax;
    }) ?? { lag: null, peak: -Infinity, c: null, hc: null };
    return { window: [X + x0, Y + y0, x1 - x0, y1 - y0], pixels: wn, lattice: Math.min(first.peak, second.peak),
      correlation: first.c, half: first.hc, lag: first.lag, lag2: second.lag, second: second.peak,
      contrast: Math.sqrt(wsq / wn) / (wbase / wn) };
  };
  const windows = [];
  const step = limits.window / 2;
  for (let y0 = M; y0 < h - M; y0 += step) {
    for (let x0 = M; x0 < w - M; x0 += step) {
      const wres = scan(x0, y0, Math.min(w - M, x0 + limits.window), Math.min(h - M, y0 + limits.window));
      if (wres) windows.push(wres);
    }
  }
  if (!windows.length) windows.push(scan(M, M, w - M, h - M) ?? { lattice: -Infinity, lag: null, correlation: null, half: null, contrast: 0 });
  const seen = windows.filter((v) => v.contrast >= limits.contrast);
  const worst = (seen.length ? seen : windows).reduce((a0, b0) => (b0.lattice > a0.lattice ? b0 : a0));
  const best = worst.lattice;
  const bestLag = worst.lag;
  const bestRaw = worst.correlation;
  result.windows = windows.length;
  result.worst_window = worst.window ?? null;
  result.correlation = bestRaw;
  result.half_period_correlation = worst.half;
  result.window_contrast = worst.contrast;
  result.lattice = best;
  result.lag = bestLag;
  result.lag2 = worst.lag2 ?? null;
  result.stipple = best >= limits.lattice && worst.contrast >= limits.contrast;
  result.why = result.stipple
    ? `a lattice repeating along ${bestLag.join(",")} and ${worst.lag2?.join(",")} px: lattice ${best.toFixed(3)} (the weaker direction's correlation less its half-period's) (limit ${limits.lattice}), at ${(100 * worst.contrast).toFixed(2)}% contrast in window ${worst.window?.join(",")} (limit ${(100 * limits.contrast).toFixed(2)}%)`
    : best < limits.lattice
      ? `no repeating fine pattern: best lattice ${best.toFixed(3)} at ${bestLag?.join(",")} px (limit ${limits.lattice})`
      : `a repeating pattern (${best.toFixed(3)}) too faint to see: ${(100 * worst.contrast).toFixed(2)}% contrast (limit ${(100 * limits.contrast).toFixed(2)}%)`;
  return result;
}

const fmt = (v, d = 3) => (typeof v === "number" ? v.toFixed(d) : "-");

// The `stipple` subcommand. Exit 1 when the image stipples, 2 on a usage error.
export async function stippleCommand(args, die) {
  const file = args._[1] ?? args.png;
  if (!file) die("stipple needs a PNG: lookdev.mjs stipple <png> [--region x,y,w,h]");
  let img;
  try {
    img = readPNG(file);
  } catch (e) {
    die(`cannot read ${file}: ${e.message}`);
  }
  let res;
  try {
    res = stipple(img, args.region ?? null);
  } catch (e) {
    die(e.message);
  }
  if (args.out) writePNG(String(args.out), crop(img, ...res.region, 3));
  if (args.json) console.log(JSON.stringify({ file, ...res }, null, 2));
  else {
    console.log(`lookdev stipple  ${file}  region ${res.region.join(",")}  shadowed smooth pixels ${res.pixels}`);
    console.log(`  lattice ${fmt(res.lattice)} at ${res.lag ? res.lag.join(",") : "-"} px (limit ${res.limits.lattice})   contrast ${fmt(res.contrast ? 100 * res.contrast : null, 2)}% (limit ${fmt(100 * res.limits.contrast, 2)}%)`);
    console.log(`  ${res.stipple ? "STIPPLE" : "clean  "} ${res.why}`);
  }
  if (res.stipple) process.exitCode = 1;
  return res;
}
