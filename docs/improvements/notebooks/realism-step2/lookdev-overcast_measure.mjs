// probe measurements on a close-shot folder: forehead highlight in G:face, skin mean in G:full
import fs from "node:fs";
import { readPNG } from "file:///C:/Users/pauli/Code/blender-godot-plugins/.worktrees/lookdev-overcast/plugins/lookdev/bin/png.mjs";

const dir = process.argv[2];
const close = JSON.parse(fs.readFileSync(`${dir}/close.json`, "utf8"));
const band = Math.round(-close.tiles[0].band_px[1]);
const px = (img, x, y) => { const i = (y * img.width + x) * 4; return [img.data[i] / 255, img.data[i + 1] / 255, img.data[i + 2] / 255]; };
const luma = (c) => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
function pct(a, p) { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; }
function hsv([r, g, b]) {
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let h = 0;
  if (d > 0) h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [((h * 60) + 360) % 360, mx > 0 ? d / mx : 0, mx];
}
function region(img, fx0, fy0, fx1, fy1) {
  const W = img.width, H = img.height - band;
  const L = [], E = [];
  for (let y = Math.round(fy0 * H); y < Math.round(fy1 * H); y++) {
    for (let x = Math.round(fx0 * W); x < Math.round(fx1 * W); x++) {
      const l = luma(px(img, x, y + band));
      L.push(l);
      E.push(Math.abs(luma(px(img, x + 2, y + band)) - luma(px(img, x - 2, y + band))));
    }
  }
  // column profile: a vertical band is a bump in it, with hard sides
  const x0 = Math.round(fx0 * W), x1 = Math.round(fx1 * W), y0 = Math.round(fy0 * H), y1 = Math.round(fy1 * H);
  const P = [];
  for (let x = x0; x < x1; x++) { let s = 0; for (let y = y0; y < y1; y++) s += luma(px(img, x, y + band)); P.push(s / (y1 - y0)); }
  let step = 0;
  for (let i = 3; i < P.length - 3; i++) step = Math.max(step, Math.abs(P[i + 3] - P[i - 3]));
  return { p50: pct(L, 0.5), hi: pct(L, 0.99) / pct(L, 0.5), band: Math.max(...P) - pct(P, 0.5), step };
}
function skin(img, mask) {
  const W = img.width, H = img.height - band;
  let s = [0, 0, 0], n = 0;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const mx = Math.floor(x * mask.width / W), my = Math.floor(y * mask.height / H);
    if (mask.data[(my * mask.width + mx) * 4] < 128) continue;
    const c = px(img, x, y + band);
    if (luma(c) < 0.1) continue;
    s = s.map((v, i) => v + c[i]); n++;
  }
  const m = s.map((v) => v / n);
  const [h, sat, v] = hsv(m);
  return { mean: m.map((v) => +v.toFixed(3)), hue: +h.toFixed(1), sat: +sat.toFixed(3), val: +v.toFixed(3), n };
}
const out = {};
for (const p of close.presets) {
  const face = readPNG(`${dir}/${p}_face.png`);
  const eyes = readPNG(`${dir}/${p}_eyes.png`);
  const full = readPNG(`${dir}/${p}_full.png`);
  const mask = readPNG(`${dir}/${p}_full_mask.png`);
  const fm = readPNG(`${dir}/${p}_face_mask.png`);
  const r = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, +v.toFixed(3)]));
  out[p] = { forehead: r(region(face, 0.35, 0.25, 0.65, 0.32)), nose: r(region(face, 0.44, 0.45, 0.56, 0.62)),
    eyes_forehead: r(region(eyes, 0.3, 0.14, 0.7, 0.26)), face_skin: skin(face, fm), full: skin(full, mask) };
}
console.log(JSON.stringify(out));
