// lookdev grain: how much fine texture a patch of skin carries in a render - the pores and micro relief that
// make skin read as skin at 1 m, or the salt-and-pepper noise a detail map that aliases draws at full body.
//
//   node lookdev.mjs grain <png> [--region x,y,w,h] [--min pct] [--max pct] [--max-finest pct] [--json] [--out crop.png]
//
// How: luma (sRGB-coded, 0-1) is band-passed - its 3x3 box mean less its (2r+1)^2 box mean (r = 3) keeps
// features 3 to 7 pixels across. Shading gradients, the mottle and the face's own forms are wider and drop out;
// the renderer's dither (a regular 1-2 px pattern, relatively stronger on dark skin) and aliasing noise are
// finer and drop out too, so they cannot pass for grain. `grain` is that band's RMS as a share of the patch's
// mean luma, in percent, over skin pixels only (warmer than blue, as `stipple` has it, and not within `margin`
// px of a pixel that is not), so a stray brow hair, the backdrop or a silhouette does not count. `finest` is
// the pixel-to-pixel part (luma less its 3x3 mean), where salt-and-pepper noise and dither live. Both are
// reported as measured, never clamped; `--min` fails (exit 1) a patch whose grain is under it, `--max` one
// whose grain is over it, and `--max-finest` one whose finest part is over it.
//
// The Step 2 check: a fixed patch on the cheek of close-shot's face tile at 1 m (640 px tile), where main's
// pores had mipped away to nothing. Region: pixels (x,y,w,h), or fractions of the image when every number is at
// most 1.

import { readPNG, writePNG, crop } from "./png.mjs";
import { parseRegion } from "./stipple.mjs";

export const GRAIN_DEFAULTS = { radius: 3, warmth: 1.1, margin: 2, min_pixels: 400 };
// The cheek patch of close-shot's face tile (640 x 704 with the label band above): under the left eye (the
// figure's right), clear of the nose, the nasolabial fold and the jaw edge on both study figures.
export const CHEEK = "0.34,0.57,0.075,0.065";

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

export function grain(img, region = null, opts = GRAIN_DEFAULTS) {
  const o = { ...GRAIN_DEFAULTS, ...opts };
  const [X, Y, w, h] = parseRegion(region, img);
  const L = new Float64Array(w * h);
  const skin = new Float64Array(w * h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = 4 * ((Y + y) * img.width + X + x);
      const R = img.data[i], G = img.data[i + 1], B = img.data[i + 2];
      L[y * w + x] = (0.2126 * R + 0.7152 * G + 0.0722 * B) / 255;
      skin[y * w + x] = R > o.warmth * B && (R - B) / Math.max(1, R + G + B) > 0.03 ? 1 : 0;
    }
  }
  const near = box(skin, w, h, o.margin);
  // band-pass: the 3x3 mean less the (2r+1)^2 mean keeps features 3 to 2r+1 px across; the pixel-to-pixel
  // part (the renderer's dither, aliasing) is measured apart, as the luma less its 3x3 mean
  const m1 = box(L, w, h, 1);
  const measure = (fine, coarse, pad) => {
    let n = 0, sq = 0, base = 0;
    for (let y = pad; y < h - pad; y++) {
      for (let x = pad; x < w - pad; x++) {
        const i = y * w + x;
        if (near[i] < 0.999) continue;
        const d = fine[i] - coarse[i];
        n++;
        sq += d * d;
        base += L[i];
      }
    }
    return { n, rms: n ? Math.sqrt(sq / n) : null, mean: n ? base / n : null };
  };
  const a = measure(m1, box(L, w, h, o.radius), o.radius);
  const b = measure(L, m1, o.radius);
  const res = {
    region: [X, Y, w, h], pixels: a.n, mean_luma: a.mean,
    grain: a.n && a.mean > 0 ? (100 * a.rms) / a.mean : null,
    finest: b.n && b.mean > 0 ? (100 * b.rms) / b.mean : null,
    radius: o.radius, why: "",
  };
  if (a.n < o.min_pixels) res.why = `only ${a.n} skin pixels in the region (need ${o.min_pixels}): aim it at skin`;
  return res;
}

const fmt = (v, d = 2) => (typeof v === "number" ? v.toFixed(d) : "-");

// The `grain` subcommand. Exit 1 when the patch is outside --min/--max or holds too little skin, 2 on a usage error.
export async function grainCommand(args, die) {
  const file = args._[1] ?? args.png;
  if (!file) die("grain needs a PNG: lookdev.mjs grain <png> [--region x,y,w,h | cheek] [--min pct] [--max pct]");
  let img;
  try {
    img = readPNG(file);
  } catch (e) {
    die(`cannot read ${file}: ${e.message}`);
  }
  const region = args.region === "cheek" ? CHEEK : (args.region ?? null);
  let res;
  try {
    res = grain(img, region, args.radius !== undefined ? { radius: Number(args.radius) } : {});
  } catch (e) {
    die(e.message);
  }
  const min = args.min !== undefined ? Number(args.min) : null;
  const max = args.max !== undefined ? Number(args.max) : null;
  const maxFinest = args["max-finest"] !== undefined ? Number(args["max-finest"]) : null;
  if ((min !== null && !(min >= 0)) || (max !== null && !(max >= 0))) die("--min and --max are percentages of the patch's luma");
  const fails = [];
  if (res.why) fails.push(res.why);
  else {
    if (min !== null && !(res.grain >= min)) fails.push(`SMOOTH grain ${fmt(res.grain)}% under --min ${min}%`);
    if (max !== null && !(res.grain <= max)) fails.push(`COARSE grain ${fmt(res.grain)}% over --max ${max}%`);
    if (maxFinest !== null && !(res.finest <= maxFinest)) fails.push(`NOISY finest ${fmt(res.finest)}% over --max-finest ${maxFinest}%`);
  }
  res.min = min;
  res.max = max;
  res.max_finest = maxFinest;
  res.ok = fails.length === 0;
  res.failures = fails;
  if (args.out) writePNG(String(args.out), crop(img, ...res.region, 4));
  if (args.json) console.log(JSON.stringify({ file, ...res }, null, 2));
  else {
    console.log(`lookdev grain  ${file}  region ${res.region.join(",")}  skin pixels ${res.pixels}  mean luma ${fmt(res.mean_luma, 3)}`);
    console.log(`  grain ${fmt(res.grain)}% (3-${2 * res.radius + 1} px band RMS / mean luma)   finest ${fmt(res.finest)}% (pixel-to-pixel)` +
      (min !== null ? `   min ${min}%` : "") + (max !== null ? `   max ${max}%` : "") + (maxFinest !== null ? `   max finest ${maxFinest}%` : ""));
    console.log(`  ${res.ok ? "ok" : fails.join("; ")}`);
  }
  if (!res.ok) process.exitCode = 1;
  return res;
}
