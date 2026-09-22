// lookdev tone-shift: does a character keep its skin tone from one lighting preset to another?
//
//   node lookdev.mjs tone-shift <close-shot dir> [--from clear_midday] [--to overcast] [--view full] [--json]
//
// What it is for: a preset whose light is the wrong colour or brightness turns the skin into a different
// person's - under the overcast recipe before lookdev 0.9.0, study_man went a muddy brown and study_woman
// grey. Exposure differences are expected (overcast is dimmer); a change of hue or saturation is not, beyond
// what a cooler daylight gives.
//
// How: in each preset's tile of the view (default full, the whole figure at 4 m) the figure's pixels are the
// close-shot's own mask (`<tile>_mask.png`, 1 where the figure is), less the near-black ones (display luma
// under `min_luma`: pupils, hair shadow, lashes), whose hue is noise. Their mean display colour (sRGB) gives
// hue (degrees) and saturation (HSV). The shift is hue_to - hue_from in degrees and (sat_to - sat_from) /
// sat_from; both are reported as measured, never clamped, and the pair fails when either is over its limit.

import fs from "node:fs";
import path from "node:path";
import { readPNG } from "./png.mjs";

export const TONE_LIMITS = { hue_deg: 3.0, sat_rel: 0.15, min_luma: 0.1, min_pixels: 2000 };

const luma = (r, g, b) => 0.2126 * r + 0.7152 * g + 0.0722 * b;

export function hsv([r, g, b]) {
  const mx = Math.max(r, g, b);
  const d = mx - Math.min(r, g, b);
  let h = 0;
  if (d > 0) h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return { hue: (h * 60 + 360) % 360, sat: mx > 0 ? d / mx : 0, val: mx };
}

// The mean display colour of the figure in one tile. The tile PNG is the picture with its label band above
// it (close-shot's default); the band's rows are whatever the picture's aspect leaves over.
export function skinMean(tilePng, maskPng, picturePx, limits = TONE_LIMITS) {
  const img = readPNG(tilePng);
  const mask = readPNG(maskPng);
  const picH = Math.round(img.width * picturePx[1] / picturePx[0]);
  const band = Math.max(0, img.height - picH);
  const sum = [0, 0, 0];
  let n = 0;
  let masked = 0;
  for (let y = 0; y < picH; y++) {
    const my = Math.min(mask.height - 1, Math.floor(y * mask.height / picH));
    for (let x = 0; x < img.width; x++) {
      const mx = Math.min(mask.width - 1, Math.floor(x * mask.width / img.width));
      if (mask.data[4 * (my * mask.width + mx)] < 128) continue;
      masked++;
      const i = 4 * ((y + band) * img.width + x);
      const c = [img.data[i] / 255, img.data[i + 1] / 255, img.data[i + 2] / 255];
      if (luma(...c) < limits.min_luma) continue;
      for (let k = 0; k < 3; k++) sum[k] += c[k];
      n++;
    }
  }
  const mean = n ? sum.map((v) => v / n) : [0, 0, 0];
  const h = hsv(mean);
  return { mean: mean.map((v) => +v.toFixed(4)), hue_deg: +h.hue.toFixed(2), sat: +h.sat.toFixed(4), val: +h.val.toFixed(4),
    pixels: n, figure_pixels: masked };
}

// Measure a close-shot folder (its close.json): the shift of `view` from preset `from` to preset `to`.
export function toneShift(dir, opts = {}) {
  const limits = { ...TONE_LIMITS, ...(opts.limits ?? {}) };
  const from = opts.from ?? "clear_midday";
  const to = opts.to ?? "overcast";
  const view = opts.view ?? "full";
  const close = JSON.parse(fs.readFileSync(path.join(dir, "close.json"), "utf8"));
  const tile = (preset) => {
    const t = (close.tiles ?? []).find((x) => x.preset === preset && x.view === view);
    if (!t) throw new Error(`no ${view} tile under ${preset} in ${dir}/close.json (presets: ${(close.presets ?? []).join(", ")})`);
    // by basename, so a folder that was moved (the selftest's controls) still resolves
    const png = path.join(dir, path.basename(t.file));
    return skinMean(png, png.replace(/\.png$/, "_mask.png"), t.picture_px, limits);
  };
  const a = tile(from);
  const b = tile(to);
  let dh = b.hue_deg - a.hue_deg;
  if (dh > 180) dh -= 360;
  if (dh < -180) dh += 360;
  const dsat = a.sat > 0 ? (b.sat - a.sat) / a.sat : 0;
  const problems = [];
  for (const [p, m] of [[from, a], [to, b]]) {
    if (m.pixels < limits.min_pixels) problems.push(`TONE_PIXELS: ${p} ${view} has ${m.pixels} figure pixels over luma ${limits.min_luma} (min ${limits.min_pixels})`);
  }
  if (Math.abs(dh) > limits.hue_deg) problems.push(`TONE_SHIFT: skin hue moves ${dh.toFixed(2)} deg from ${from} to ${to} (max ${limits.hue_deg})`);
  if (Math.abs(dsat) > limits.sat_rel) problems.push(`TONE_SHIFT: skin saturation moves ${(100 * dsat).toFixed(1)}% from ${from} to ${to} (max ${(100 * limits.sat_rel).toFixed(0)}%)`);
  return { dir, view, from, to, [from]: a, [to]: b, hue_shift_deg: +dh.toFixed(2), sat_shift_rel: +dsat.toFixed(4),
    val_ratio: a.val > 0 ? +(b.val / a.val).toFixed(3) : null, limits, problems, ok: problems.length === 0 };
}

export function printToneShift(r, indent = "") {
  const one = (p) => {
    const m = r[p];
    return `${p.padEnd(14)} mean ${m.mean.map((v) => v.toFixed(3)).join(",")}  hue ${m.hue_deg.toFixed(1)}  sat ${m.sat.toFixed(3)}  val ${m.val.toFixed(3)}  (${m.pixels} px)`;
  };
  console.log(`${indent}tone shift  ${r.view}: ${r.from} -> ${r.to}`);
  console.log(`${indent}  ${one(r.from)}`);
  console.log(`${indent}  ${one(r.to)}`);
  console.log(`${indent}  hue ${r.hue_shift_deg >= 0 ? "+" : ""}${r.hue_shift_deg.toFixed(2)} deg (max ${r.limits.hue_deg})  saturation ${r.sat_shift_rel >= 0 ? "+" : ""}${(100 * r.sat_shift_rel).toFixed(1)}% (max ${(100 * r.limits.sat_rel).toFixed(0)}%)  value x${r.val_ratio}`);
  for (const p of r.problems) console.log(`${indent}  FAIL ${p}`);
  if (r.ok) console.log(`${indent}  ok: the skin keeps its tone`);
}

export function toneShiftCommand(args, die) {
  const dir = args._[1];
  if (!dir || !fs.existsSync(path.join(dir, "close.json"))) die("tone-shift needs a close-shot folder (with close.json)");
  const limits = {};
  if (args["max-hue"] !== undefined) limits.hue_deg = Number(args["max-hue"]);
  if (args["max-sat"] !== undefined) limits.sat_rel = Number(args["max-sat"]);
  let r;
  try {
    r = toneShift(dir, { from: args.from, to: args.to, view: args.view, limits });
  } catch (e) {
    die(String(e.message ?? e), 2);
  }
  if (args.json) console.log(JSON.stringify(r, null, 2));
  else printToneShift(r);
  if (!r.ok) process.exitCode = 1;
}
