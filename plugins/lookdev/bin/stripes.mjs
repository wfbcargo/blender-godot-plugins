// lookdev stripes: find regular bands (shadow acne) on a surface that should be smooth - the stage floor.
//
//   node lookdev.mjs stripes <png> [--region x,y,w,h] [--mask figure_mask.png] [--band px] [--json]
//
// What it is for: a directional light at a grazing angle (golden hour's sun a few degrees up) meets a
// flat floor almost edge-on. Each shadow-map texel then spans a long run of floor depth, and when the
// depth bias does not cover that run the floor shadows itself in rows: parallel light and dark bands a
// few pixels apart ("shadow acne"). The eye finds them at once; exposure statistics do not.
//
// How: luma minus its 5x5 box mean is the fine detail. Only smooth pixels are kept - the 7x7 mean's own
// gradient small (so the edge of the figure's cast shadow does not count), nothing of the figure (the
// close-shot figure mask, dilated) within `margin` px. Over those pixels, window by window (96 px, half
// overlapping), the detail's autocorrelation is measured at every offset within 8 px beyond the first
// ring. Bands repeat: some offset (the period, across the bands) correlates with itself and half of it
// anti-correlates. Noise, dither and a smooth gradient correlate at neither. Unlike stipple (a lattice,
// two directions) one direction is enough: `stripe` is the best correlation at an offset less the
// positive part of the correlation at half of it. `contrast` is the worst window's detail RMS as a share
// of its luma. The surface stripes when both pass. Both are reported as measured, never clamped.
//
// Region: pixels (x,y,w,h), or fractions of the image when every number is at most 1.

import { readPNG, writePNG, crop } from "./png.mjs";
import { parseRegion } from "./stipple.mjs";

export const STRIPE_LIMITS = { stripe: 0.3, contrast: 0.012, edge: 0.02, min_pixels: 1500, window: 96, margin: 5, min_luma: 0.03 };

function box(src, w, h, r) {
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

// exclude(x, y) -> true for a pixel (image coordinates) that is not the surface (the figure).
export function stripes(img, region = null, exclude = null, limits = STRIPE_LIMITS) {
  const [X, Y, w, h] = parseRegion(region, img);
  const L = new Float64Array(w * h);
  const out = new Float64Array(w * h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = 4 * ((Y + y) * img.width + X + x);
      L[y * w + x] = (0.2126 * img.data[i] + 0.7152 * img.data[i + 1] + 0.0722 * img.data[i + 2]) / 255;
      if (exclude && exclude(X + x, Y + y)) out[y * w + x] = 1;
    }
  }
  const m5 = box(L, w, h, 2);
  const m7 = box(L, w, h, 3);
  const M = 8;
  const cand = new Float64Array(w * h);
  for (let y = M; y < h - M; y++) {
    for (let x = M; x < w - M; x++) {
      const i = y * w + x;
      if (out[i]) continue;
      const gx = (m7[i + 3] - m7[i - 3]) / 6;
      const gy = (m7[i + 3 * w] - m7[i - 3 * w]) / 6;
      if (m7[i] > limits.min_luma && Math.hypot(gx, gy) < limits.edge * Math.max(m7[i], 0.05) * 3) cand[i] = 1;
    }
  }
  const near = box(cand, w, h, limits.margin);
  const mask = new Uint8Array(w * h);
  const r = new Float64Array(w * h);
  let n = 0;
  for (let i = 0; i < w * h; i++) {
    if (cand[i] && near[i] > 0.999) {
      mask[i] = 1;
      r[i] = L[i] - m5[i];
      n++;
    }
  }
  const result = { region: [X, Y, w, h], pixels: n, stripe: null, contrast: null, lag: null, correlation: null,
    half_period_correlation: null, worst_window: null, windows: 0, stripes: false, limits, why: "" };
  if (n < limits.min_pixels) {
    result.why = `only ${n} smooth surface pixels in the region (need ${limits.min_pixels}): nothing to judge`;
    return result;
  }
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
    let best = null;
    for (let dy = 0; dy <= M; dy++) {
      for (let dx = -M; dx <= M; dx++) {
        if (dy === 0 && dx <= 0) continue;
        if (Math.max(Math.abs(dx), Math.abs(dy)) < 2) continue;
        const c = corrAt(dx, dy);
        if (c === null) continue;
        const hc = corrAt(Math.round(dx / 2), Math.round(dy / 2)) ?? 0;
        const s = c - Math.max(0, hc);
        if (!best || s > best.stripe) best = { stripe: s, c, hc, lag: [dx, dy] };
      }
    }
    if (!best) return null;
    return { window: [X + x0, Y + y0, x1 - x0, y1 - y0], pixels: wn, ...best, contrast: Math.sqrt(wsq / wn) / (wbase / wn) };
  };
  const windows = [];
  const step = limits.window / 2;
  for (let y0 = M; y0 < h - M; y0 += step) {
    for (let x0 = M; x0 < w - M; x0 += step) {
      const wres = scan(x0, y0, Math.min(w - M, x0 + limits.window), Math.min(h - M, y0 + limits.window));
      if (wres) windows.push(wres);
    }
  }
  if (!windows.length) {
    result.why = "no window had enough smooth surface pixels: nothing to judge";
    return result;
  }
  // the worst window among those with visible contrast; if none has any, the worst by pattern alone
  const seen = windows.filter((v) => v.contrast >= limits.contrast);
  const worst = (seen.length ? seen : windows).reduce((a0, b0) => (b0.stripe > a0.stripe ? b0 : a0));
  Object.assign(result, {
    windows: windows.length, worst_window: worst.window, stripe: worst.stripe, correlation: worst.c,
    half_period_correlation: worst.hc, lag: worst.lag, contrast: worst.contrast,
    contrast_max: Math.max(...windows.map((v) => v.contrast)),
  });
  result.stripes = worst.stripe >= limits.stripe && worst.contrast >= limits.contrast;
  result.why = result.stripes
    ? `bands repeating every ${worst.lag.join(",")} px: stripe ${worst.stripe.toFixed(3)} (correlation ${worst.c.toFixed(3)} less its half period's ${worst.hc.toFixed(3)}; limit ${limits.stripe}) at ${(100 * worst.contrast).toFixed(2)}% contrast in window ${worst.window.join(",")} (limit ${(100 * limits.contrast).toFixed(2)}%)`
    : worst.stripe < limits.stripe
      ? `no bands: best stripe ${worst.stripe.toFixed(3)} at ${worst.lag.join(",")} px (limit ${limits.stripe}), ${(100 * worst.contrast).toFixed(2)}% contrast`
      : `a repeating pattern (${worst.stripe.toFixed(3)}) too faint to see: ${(100 * worst.contrast).toFixed(2)}% contrast (limit ${(100 * limits.contrast).toFixed(2)}%)`;
  return result;
}

// A close-shot figure mask (MASK_W wide, the picture under a `band` px label band) as an exclude
// function over the tile, dilated by `grow` mask pixels so the figure's anti-aliased edge is left out.
export function maskExclude(maskImg, tileW, pictureH, band = 0, grow = 1) {
  const mw = maskImg.width, mh = maskImg.height;
  const on = (mx, my) => mx >= 0 && my >= 0 && mx < mw && my < mh && maskImg.data[4 * (my * mw + mx)] > 127;
  return (x, y) => {
    if (y < band) return true;
    const mx = Math.floor((x * mw) / tileW);
    const my = Math.floor(((y - band) * mh) / pictureH);
    for (let dy = -grow; dy <= grow; dy++) for (let dx = -grow; dx <= grow; dx++) if (on(mx + dx, my + dy)) return true;
    return false;
  };
}

const fmt = (v, d = 3) => (typeof v === "number" ? v.toFixed(d) : "-");

// The `stripes` subcommand. Exit 1 when the surface stripes, 2 on a usage error.
export async function stripesCommand(args, die) {
  const file = args._[1] ?? args.png;
  if (!file) die("stripes needs a PNG: lookdev.mjs stripes <png> [--region x,y,w,h] [--mask mask.png --band px]");
  let img;
  try {
    img = readPNG(file);
  } catch (e) {
    die(`cannot read ${file}: ${e.message}`);
  }
  let exclude = null;
  if (args.mask) {
    const band = Number(args.band ?? 0);
    try {
      exclude = maskExclude(readPNG(String(args.mask)), img.width, img.height - band, band);
    } catch (e) {
      die(`cannot read --mask ${args.mask}: ${e.message}`);
    }
  }
  let res;
  try {
    res = stripes(img, args.region ?? null, exclude);
  } catch (e) {
    die(e.message);
  }
  if (args.out) writePNG(String(args.out), crop(img, ...res.region, 3));
  if (args.json) console.log(JSON.stringify({ file, ...res }, null, 2));
  else {
    console.log(`lookdev stripes  ${file}  region ${res.region.join(",")}  smooth surface pixels ${res.pixels}`);
    console.log(`  stripe ${fmt(res.stripe)} at ${res.lag ? res.lag.join(",") : "-"} px (limit ${res.limits.stripe})   contrast ${fmt(res.contrast ? 100 * res.contrast : null, 2)}% (limit ${fmt(100 * res.limits.contrast, 2)}%)`);
    console.log(`  ${res.stripes ? "STRIPES" : "clean  "} ${res.why}`);
  }
  if (res.stripes) process.exitCode = 1;
  return res;
}
