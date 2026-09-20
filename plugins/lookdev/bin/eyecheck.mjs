// lookdev eyes: does a character's eye carry the eye preset, and does its pupil still read as a hole?
//
//   node lookdev.mjs eyes <glb> [--json]
//
// What it is for: the benchmark found every new character's eyes dead at 1 m, and the cause was that the eye
// materials carried no lookdev extras at all - there was no eye preset, so the Godot addon skipped them and
// the eye shipped as three flat Principled colours: no cornea, so no catchlight; no limbal ring, so the iris
// ended at a visible facet boundary; and a pupil that a dark iris swallowed.
//
// How: the glb's own material table, read straight from the glTF JSON chunk - no Godot, no render, under a
// second. For each eye material (named by the preset's `part` extra) it checks
//   EYE_NO_PRESET   a part with no `lookdev` extras: the addon will skip it and there is no cornea
//   EYE_PUPIL_LOST  the iris's linear luminance is under `iris_floor_ratio` x the pupil's, so at 1 m the two
//                   read as one dark blob. Measured on the benchmark: 6.97x read as a distinct disc, 2.14x
//                   and 1.35x did not.
//   EYE_NO_LIMBAL   no limbal part, or one not darker than its iris
// Everything is reported measured, never clamped.

import fs from "node:fs";

export const EYE_LIMITS = { iris_floor_ratio: 6.0, limbal_max_share: 0.8 };

const luma = (c) => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];

/** The glTF JSON chunk of a .glb. */
export function gltfJson(file) {
  const buf = fs.readFileSync(file);
  if (buf.length < 20 || buf.readUInt32LE(0) !== 0x46546c67) throw new Error(`${file} is not a .glb`);
  const len = buf.readUInt32LE(12);
  return JSON.parse(buf.slice(20, 20 + len).toString("utf8"));
}

/** {part: {name, colour, rough, extras}} for the materials the eye preset marked. */
export function eyeMaterials(g) {
  const out = {};
  for (const m of g.materials ?? []) {
    const ld = m.extras?.lookdev;
    const part = ld?.part;
    if (!ld || ld.preset !== "eye" || !part) continue;
    out[part] = {
      name: m.name, extras: true,
      colour: (m.pbrMetallicRoughness?.baseColorFactor ?? [0, 0, 0, 1]).slice(0, 3),
      godot: ld.godot ?? {},
    };
  }
  // parts that look like eye materials but carry nothing - the pre-preset shape
  for (const m of g.materials ?? []) {
    const n = (m.name ?? "").toLowerCase();
    for (const part of ["sclera", "iris", "limbal", "pupil"]) {
      if (out[part] || !n.includes(part)) continue;
      out[part] = { name: m.name, extras: false,
                    colour: (m.pbrMetallicRoughness?.baseColorFactor ?? [0, 0, 0, 1]).slice(0, 3), godot: {} };
    }
  }
  return out;
}

export function checkEyes(file, limits = EYE_LIMITS) {
  const parts = eyeMaterials(gltfJson(file));
  const found = Object.keys(parts).sort();
  const failures = [];
  if (found.length === 0) return { file, parts: {}, found, failures: [], skipped: "no eye materials in this glb" };

  const noExtras = found.filter((p) => !parts[p].extras);
  if (noExtras.length) {
    failures.push(`EYE_NO_PRESET: ${noExtras.join(", ")} carry no lookdev extras, so Godot skips them - ` +
                  "no cornea and no catchlight (the eye preset is what writes them)");
  }
  let ratio = null;
  if (parts.iris && parts.pupil) {
    const pl = Math.max(luma(parts.pupil.colour), 1e-9);
    ratio = luma(parts.iris.colour) / pl;
    if (ratio < limits.iris_floor_ratio) {
      failures.push(`EYE_PUPIL_LOST: the iris is only ${ratio.toFixed(2)}x the pupil's luminance ` +
                    `(want ${limits.iris_floor_ratio}x): at 1 m they read as one dark blob`);
    }
  }
  let limbalShare = null;
  if (!parts.limbal) {
    failures.push("EYE_NO_LIMBAL: no limbal part - the iris ends at the sclera on a facet boundary");
  } else if (parts.iris) {
    limbalShare = luma(parts.limbal.colour) / Math.max(luma(parts.iris.colour), 1e-9);
    if (limbalShare > limits.limbal_max_share) {
      failures.push(`EYE_NO_LIMBAL: the limbal ring is ${limbalShare.toFixed(2)}x its iris ` +
                    `(want under ${limits.limbal_max_share}x): it will not read as a ring`);
    }
  }
  return { file, found, parts, iris_pupil_ratio: ratio === null ? null : Number(ratio.toFixed(2)),
           limbal_share: limbalShare === null ? null : Number(limbalShare.toFixed(2)), limits, failures };
}

export function printEyes(r, indent = "") {
  if (r.skipped) { console.log(`${indent}eyes: ${r.skipped}`); return; }
  console.log(`${indent}lookdev eyes  ${r.file}`);
  for (const p of ["sclera", "iris", "limbal", "pupil"]) {
    const m = r.parts[p];
    if (!m) { console.log(`${indent}  ${p.padEnd(8)} -`); continue; }
    const c = m.colour.map((v) => v.toFixed(4)).join(", ");
    console.log(`${indent}  ${p.padEnd(8)} ${m.name.padEnd(28)} [${c}]  ` +
                `${m.extras ? "preset" : "NO EXTRAS"}${m.godot.clearcoat_enabled ? " +cornea" : ""}`);
  }
  console.log(`${indent}  iris/pupil ${r.iris_pupil_ratio}x (want ${r.limits.iris_floor_ratio}x)` +
              (r.limbal_share === null ? "" : `   limbal ${r.limbal_share}x its iris (want under ${r.limits.limbal_max_share}x)`));
  for (const f of r.failures) console.log(`${indent}  FAIL ${f}`);
  if (!r.failures.length) console.log(`${indent}  ok: the eye carries the preset and the pupil reads as a hole`);
}

export function eyesCommand(args, die) {
  const file = args._[1];
  if (!file || !fs.existsSync(file)) die("eyes needs a .glb path");
  let r;
  try { r = checkEyes(file); } catch (e) { die(String(e.message ?? e), 2); }
  if (args.json) console.log(JSON.stringify(r, null, 2));
  else printEyes(r);
  if (r.failures?.length) process.exit(1);
}
