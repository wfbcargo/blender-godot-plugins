// lookdev edges: the light a skin's transmittance adds, per close-shot tile - drawn as lines, or as a glow.
//
//   node lookdev.mjs edges --project <dir> --glb <res://x.glb> [--views hands] [--presets clear_midday,overcast]
//        [--material-set prop=value]... [--sun-elevation deg --sun-azimuth deg] [--limit 0.1]
//        [--min-glow 0.5 --glow-views head_back] [--out dir] [--json]
//   node lookdev.mjs edges --on <tile.png> --off <tile.png> [--subject <mask.png>] [--limit 0.1]   (no Godot)
//   --kind specular: the same with metallic_specular=0 as the second render, counting pale (grey-white) marks the
//   specular draws - PALE_LINES (the fingertip crescents of a glossy nail plate under overcast)
//
// What it is for: Godot measures a skin's thickness toward the sun from the directional shadow map
// (fragment depth less the shadow map's depth, after a small push along the normal). At 1 m that map's
// texels are several millimetres wide, so on a finger - or at the web between two - the thickness it
// reads is noise of the size of the transmittance depth itself, and it reads about zero wherever the
// surface just past the terminator is its own occluder. With humanform's old setting (skin mode, a 1 cm
// depth) that noise drew thin, saturated orange-red lines and flecks along the finger edges, at the thumb
// web and on the ears, not a glow: skin mode's profile is pure red from about a millimetre on, whatever
// the material's transmittance colour says (skin mode uses only its alpha).
//
// How: close-shot renders each tile twice, as the glb asks and with transmittance off
// (`--material-set subsurf_scatter_transmittance_enabled=false`); nothing else differs, so the red channel's
// difference is the light transmittance added (Godot renders the same pose and lights identically). Over
// the tile's subject (close-shot's `_subject.png`, the part of the figure within the view's depth slab):
//   glow     the mean added red (0-255): transmittance still shows (reported; --min-glow checks it on
//            --glow-views)
//   lines    pixels where the added red is at least ADD and more than LINE times the red the skin has there
//            without it - a mark that outshines the skin it sits on, which a soft glow never does; per
//            thousand subject pixels, failing over --limit. The worst ratio is reported as measured.

import fs from "node:fs";
import path from "node:path";
import { readPNG } from "./png.mjs";

export const EDGE_LIMITS = { line: 0.5, add: 8, limit: 0.1, floor: 8 };
// --kind specular: pale lines - specular (metallic_specular=0 in the second render) that lifts all three channels
// by PALE.add or more and by more than PALE.line of the brightest channel the skin has there without it: a grey-white
// mark on skin (humanform <= 0.14's glossy nail plate drew a crescent at every fingertip under overcast).
export const PALE_LIMITS = { line: 0.4, add: 10, limit: 0.1, floor: 8 };
export const KINDS = {
  transmittance: { off: "subsurf_scatter_transmittance_enabled=false", limits: EDGE_LIMITS, code: "EDGE_LINES",
    what: "added red where transmittance is on" },
  specular: { off: "metallic_specular=0", limits: PALE_LIMITS, code: "PALE_LINES",
    what: "light added to all three channels by the specular (pale)" },
};

// on, off: decoded PNGs of the same tile; subject: a mask PNG (any size: scaled onto the picture) or null.
// A tile carries a label band above the picture (height - width rows) when it is taller than wide.
export function transmittedEdges(on, off, subject = null, limits = EDGE_LIMITS, kind = "transmittance") {
  const pale = kind === "specular";
  if (on.width !== off.width || on.height !== off.height) throw new Error(`the two renders differ in size (${on.width}x${on.height} vs ${off.width}x${off.height})`);
  const W = on.width;
  const band = subject && on.height > W ? on.height - W : 0;
  const H = on.height - band;
  let n = 0, sum = 0, lit = 0, lines = 0, worst = 0, max = 0;
  const at = [];
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      if (subject) {
        const mx = Math.min(subject.width - 1, Math.floor((x * subject.width) / W));
        const my = Math.min(subject.height - 1, Math.floor((y * subject.height) / H));
        if (subject.data[4 * (my * subject.width + mx)] < 128) continue;
      }
      const i = 4 * ((y + band) * W + x);
      const t = pale
        ? Math.max(0, Math.min(on.data[i] - off.data[i], on.data[i + 1] - off.data[i + 1], on.data[i + 2] - off.data[i + 2]))
        : Math.max(0, on.data[i] - off.data[i]);
      const ratio = t / ((pale ? Math.max(off.data[i], off.data[i + 1], off.data[i + 2]) : off.data[i]) + limits.floor);
      n++;
      sum += t;
      if (t >= 3) lit++;
      if (t > max) max = t;
      if (t >= limits.add && ratio > worst) worst = ratio;
      if (t >= limits.add && ratio > limits.line) {
        lines++;
        if (at.length < 2000) at.push([x, y + band]);
      }
    }
  }
  const per_mille = n ? (1000 * lines) / n : 0;
  let cx = null;
  if (at.length) cx = [Math.round(at.reduce((a, p) => a + p[0], 0) / at.length), Math.round(at.reduce((a, p) => a + p[1], 0) / at.length)];
  return { pixels: n, glow: n ? sum / n : 0, lit_share: n ? lit / n : 0, max_added: max, lines, lines_per_mille: per_mille,
    worst_ratio: worst, lines_centre: cx, limits, fails: per_mille > limits.limit };
}

const f2 = (v, d = 2) => (typeof v === "number" ? v.toFixed(d) : "-");

function row(label, r, code = "EDGE_LINES") {
  return `  ${label.padEnd(30)} glow ${f2(r.glow).padStart(5)}  lit ${f2(100 * r.lit_share, 1).padStart(5)}%  max +${String(r.max_added).padStart(3)}  ` +
    `lines ${String(r.lines).padStart(5)} (${f2(r.lines_per_mille).padStart(5)}‰, limit ${r.limits.limit}‰)  worst ${f2(r.worst_ratio)}x` +
    (r.lines_centre ? ` near ${r.lines_centre.join(",")}` : "") + (r.fails ? `  ${code}` : "") + (r.no_glow ? "  NO_GLOW" : "");
}

// The `edges` subcommand. runSelf runs lookdev.mjs itself (close-shot); die exits with a usage error.
// Exit 1 when a tile draws lines (or a glow view lacks its glow), 2 on a usage error.
export async function edgesCommand(args, { die, runSelf, fwd }) {
  const kindName = String(args.kind ?? "transmittance");
  const kind = KINDS[kindName];
  if (!kind) die(`--kind is ${Object.keys(KINDS).join(" or ")}, not '${kindName}'`);
  const limits = { ...kind.limits };
  if (args.limit !== undefined) {
    limits.limit = Number(args.limit);
    if (!(limits.limit >= 0)) die("--limit is lines per thousand subject pixels, >= 0");
  }
  const tiles = [];
  if (args.on || args.off) {
    if (!args.on || !args.off) die("edges --on <png> --off <png> [--subject <png>]");
    let on, off, sub = null;
    try {
      on = readPNG(String(args.on));
      off = readPNG(String(args.off));
      if (args.subject) sub = readPNG(String(args.subject));
    } catch (e) {
      die(`cannot read a PNG: ${e.message}`);
    }
    tiles.push({ view: path.basename(String(args.on)), preset: "", ...transmittedEdges(on, off, sub, limits, kindName) });
  } else {
    if (!args.glb) die("edges needs --glb (or --on/--off PNGs)");
    const out = fwd(path.resolve(String(args.out ?? path.join(process.cwd(), "lookdev_edges"))));
    const pass = ["--project", String(args.project ?? "."), "--glb", String(args.glb), "--views", String(args.views ?? "hands"),
      "--presets", String(args.presets ?? "clear_midday,overcast")];
    for (const k of ["godot", "distance", "clip", "time", "garments", "size", "sun-elevation", "sun-azimuth", "material-preset", "timeout"]) {
      if (args[k] !== undefined) pass.push(`--${k}`, String(args[k]));
    }
    if (args["no-strands"]) pass.push("--no-strands");
    const sets = (args["material-set"] ?? []).flatMap((s) => ["--material-set", s]);
    const runs = {};
    for (const [name, extra] of [["on", sets], ["off", [...sets, "--material-set", kind.off]]]) {
      const dir = `${out}/${name}`;
      const res = await runSelf(["close-shot", ...pass, ...extra, "--out", dir], Number(args.timeout ?? 400) + 60);
      const stats = path.join(dir, "close.json");
      if (!fs.existsSync(stats)) die(`close-shot (${name}) wrote no close.json, exit ${res.code}:\n${res.out.trim().split("\n").slice(-6).join("\n")}`, 1);
      runs[name] = JSON.parse(fs.readFileSync(stats, "utf8"));
      if ((runs[name].failures ?? []).length) {
        console.log(`WARN   close-shot (${name}) tile checks failed: ${runs[name].failures.slice(0, 3).join("; ")}`);
      }
    }
    for (const t of runs.on.tiles) {
      const name = `${t.preset}_${t.view}`;
      const f = (d, suffix = "") => path.join(out, d, `${name}${suffix}.png`);
      if (!fs.existsSync(f("off"))) die(`no ${name} tile in the render without transmittance`, 1);
      tiles.push({ view: t.view, preset: t.preset, ...transmittedEdges(readPNG(f("on")), readPNG(f("off")),
        fs.existsSync(f("on", "_subject")) ? readPNG(f("on", "_subject")) : null, limits, kindName) });
    }
    const glowViews = String(args["glow-views"] ?? "").split(",").filter(Boolean);
    if (args["min-glow"] !== undefined) {
      const floor = Number(args["min-glow"]);
      if (!(floor >= 0)) die("--min-glow is the least mean added red (0-255) on --glow-views");
      for (const t of tiles) {
        if (glowViews.length && !glowViews.includes(t.view)) continue;
        t.min_glow = floor;
        t.no_glow = t.glow < floor;
      }
    }
  }
  const bad = tiles.filter((t) => t.fails || t.no_glow);
  const result = { tiles, limits, kind: kindName, failures: bad.map((t) => `${t.preset} ${t.view}: ${t.fails ? `${kind.code} ${f2(t.lines_per_mille)}‰ > ${limits.limit}‰ (worst ${f2(t.worst_ratio)}x)` : ""}${t.no_glow ? `NO_GLOW ${f2(t.glow)} < ${t.min_glow}` : ""}`) };
  if (args.out && !args.on) fs.writeFileSync(path.join(String(args.out), "edges.json"), JSON.stringify(result, null, 2));
  if (args.json) console.log(JSON.stringify(result, null, 2));
  else {
    console.log(`lookdev edges --kind ${kindName}  (${kind.what}; a line outshines the skin under it by ${limits.line}x or more)`);
    for (const t of tiles) console.log(row(`${t.preset} ${t.view}`.trim(), t, kind.code));
    console.log(bad.length ? `${kind.code}/NO_GLOW in ${bad.length} tile(s)` : `clean: no ${kindName} lines`);
  }
  if (bad.length) process.exitCode = 1;
  return result;
}
