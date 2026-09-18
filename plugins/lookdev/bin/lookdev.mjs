#!/usr/bin/env node
// lookdev - lighting and shading tools for Godot 4.7, driven from the CLI.
//
//   node lookdev.mjs capture  --project <dir> --scene res://x.tscn [...]
//   node lookdev.mjs lint     --project <dir> --scene res://x.tscn
//   node lookdev.mjs preset   --project <dir> --scene res://x.tscn --preset golden_hour
//   node lookdev.mjs compare  --project <dir> --a <png|capture dir> --b <png|capture dir>
//   node lookdev.mjs presets  (list them)
//   node lookdev.mjs close-shot --project <dir> --glb res://x.glb [--distance 1] [--presets a,b] [...]
//   node lookdev.mjs tone     --project <dir> --glb <file.glb> [--material skin]
//   node lookdev.mjs selftest --project <dir>   (the controls: every check here must be able to fail)
//
// Every subcommand runs a GDScript from ../godot against the project, then reads
// back what it wrote. Godot fails quietly - a broken scene loads with nodes
// missing and scripts exit 0 after parse errors - so the runner treats engine
// error lines as failures instead of trusting exit codes.
//
// No dependencies beyond Node itself.

import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const GODOT_DIR = path.join(ROOT, "godot").replaceAll("\\", "/");
// presets.json ships inside the Godot addon, so a game applies the same recipes at runtime
// (addons/lookdev/lookdev_presets.gd) as `preset` writes into a scene.
const ADDON_DIR = path.join(ROOT, "godot", "addons", "lookdev");
const PRESETS = path.join(ADDON_DIR, "presets.json");
const THRESHOLDS = path.join(ROOT, "presets", "thresholds.json");

// ---------------------------------------------------------------- arguments

function parseArgs(argv) {
  const out = { _: [], set: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith("--")) {
      out._.push(a);
      continue;
    }
    const key = a.slice(2);
    const next = argv[i + 1];
    const hasValue = next !== undefined && !next.startsWith("--");
    if (key === "set") {
      if (!hasValue) die("--set needs target:property=value");
      out.set.push(next);
      i++;
    } else if (hasValue) {
      out[key] = next;
      i++;
    } else {
      out[key] = true;
    }
  }
  return out;
}

function die(msg, code = 2) {
  process.stderr.write(`lookdev: ${msg}\n`);
  process.exit(code);
}

function vec(s, name) {
  const parts = String(s).split(",").map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) die(`--${name} must be x,y,z`);
  return parts;
}

function parseSetValue(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return raw; // Color(...), Vector3(...), res:// paths, bare strings
  }
}

// ------------------------------------------------------------------ godot

function findProject(args) {
  const dir = path.resolve(args.project ?? process.cwd());
  if (!fs.existsSync(path.join(dir, "project.godot"))) {
    die(`no project.godot in ${dir} - pass --project <dir>`);
  }
  return dir;
}

// The Godot binary is rarely on PATH. Look where this user's setup already
// records it before giving up: explicit flag, env, then the project's .mcp.json
// (godot-mcp needs GODOT_PATH too).
function findGodot(args, project) {
  const candidates = [args.godot, process.env.LOOKDEV_GODOT, process.env.GODOT_PATH, process.env.GODOT];
  const mcp = path.join(project, ".mcp.json");
  if (fs.existsSync(mcp)) {
    try {
      const servers = JSON.parse(fs.readFileSync(mcp, "utf8")).mcpServers ?? {};
      for (const s of Object.values(servers)) candidates.push(s?.env?.GODOT_PATH);
    } catch {
      /* unreadable .mcp.json is not our problem */
    }
  }
  for (const c of candidates) {
    if (c && fs.existsSync(c)) return c;
  }
  die(
    "cannot find the Godot binary. Pass --godot <path> or set LOOKDEV_GODOT. " +
      "On Windows use the *_console.exe build - the plain one detaches and its output is lost.",
  );
}

function runGodot(godot, godotArgs, timeoutSec) {
  return new Promise((resolve) => {
    const child = spawn(godot, godotArgs, { windowsHide: false });
    let out = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (out += d));
    const timer = setTimeout(() => {
      out += `\nLOOKDEV {"type":"error","message":"timed out after ${timeoutSec}s"}\n`;
      child.kill();
    }, timeoutSec * 1000);
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ code, out });
    });
  });
}

function scanOutput(out) {
  const events = [];
  const engineErrors = [];
  const engineWarnings = [];
  const lines = out.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("LOOKDEV ")) {
      try {
        events.push(JSON.parse(line.slice(8)));
      } catch {
        /* partial line */
      }
    } else if (/leaked at exit|still in use at exit|PagedAllocator|instance_notify_deleted/.test(line)) {
      // Shutdown bookkeeping after an early quit; never the cause of anything.
      continue;
    } else if (/SCRIPT ERROR|Parse Error|^ERROR:/.test(line)) {
      const at = lines[i + 1]?.trim().startsWith("at:") ? ` ${lines[i + 1].trim()}` : "";
      engineErrors.push(line.trim() + at);
    } else if (/^WARNING:/.test(line)) {
      engineWarnings.push(line.trim());
    }
  }
  return { events, engineErrors, engineWarnings };
}

function reportEngine(scan) {
  for (const e of scan.events.filter((e) => e.type === "error")) console.log(`ERROR  ${e.message}`);
  for (const e of scan.events.filter((e) => e.type === "warning")) console.log(`WARN   ${e.message}`);
  if (scan.engineErrors.length) {
    console.log(`\nEngine errors (${scan.engineErrors.length}) - Godot often continues past these, so results may be incomplete:`);
    for (const e of scan.engineErrors.slice(0, 15)) console.log(`  ${e}`);
  }
  if (scan.engineWarnings.length) {
    console.log(`\nEngine warnings (${scan.engineWarnings.length}):`);
    for (const w of scan.engineWarnings.slice(0, 8)) console.log(`  ${w}`);
  }
}

function stamp() {
  return new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
}

function defaultOut(project, what) {
  const name = path.basename(project).replace(/[^\w.-]/g, "_");
  return path.join(os.tmpdir(), "lookdev", name, `${what}-${stamp()}`);
}

// An --out that cannot be written must fail before Godot runs, not after, with every image
// save failing quietly in between.
function writableDir(dir, what) {
  try {
    fs.mkdirSync(dir, { recursive: true });
    const probe = path.join(dir, ".lookdev_write_test");
    fs.writeFileSync(probe, "");
    fs.rmSync(probe);
  } catch (e) {
    die(`${what}: cannot write to --out ${dir} (${e.code ?? e.message})`, 1);
  }
  return dir;
}

// The project runs its own copy of the addon (a class_name script cannot be loaded twice), so a
// stale copy means the tools run old code. Say so; regress.py's addon_drift does the same.
function addonDrift(project) {
  const theirs = path.join(project, "addons", "lookdev");
  if (!fs.existsSync(theirs)) return [`the project has no addons/lookdev (the plugin's copy is used)`];
  const drift = [];
  const norm = (f) => fs.readFileSync(f).toString("utf8").replace(/\r\n/g, "\n");
  for (const f of fs.readdirSync(ADDON_DIR)) {
    if (f.endsWith(".uid")) continue;
    const t = path.join(theirs, f);
    if (!fs.existsSync(t)) drift.push(`addons/lookdev/${f} missing from the project`);
    else if (norm(t) !== norm(path.join(ADDON_DIR, f))) drift.push(`addons/lookdev/${f} differs from the plugin's`);
  }
  return drift;
}

function fwd(p) {
  return path.resolve(p).replaceAll("\\", "/");
}

// Scenes can be given as res:// or as a file path inside (or outside) the
// project; Godot loads absolute paths too, which is how preset variants written
// to a scratch folder get captured without entering the repo.
function scenePath(scene, project) {
  if (!scene) die("--scene is required");
  if (scene.startsWith("res://")) return scene;
  const abs = path.resolve(scene);
  const rel = path.relative(project, abs);
  if (!rel.startsWith("..") && !path.isAbsolute(rel)) return "res://" + rel.replaceAll("\\", "/");
  return fwd(abs);
}

// ---------------------------------------------------------------- capture

async function capture(args) {
  const project = findProject(args);
  const godot = findGodot(args, project);
  const outDir = fwd(writableDir(args.out ?? defaultOut(project, "capture"), "capture"));

  let spec = {};
  if (args.spec) spec = JSON.parse(fs.readFileSync(args.spec, "utf8"));
  if (args.scene) spec.scene = scenePath(args.scene, project);
  if (!spec.scene) die("--scene is required (or a spec with 'scene')");
  spec.out_dir = outDir;
  if (args.views) spec.views = String(args.views).split(",");
  if (args.probes) spec.probes = true;
  if (args.warmup) spec.warmup_frames = Number(args.warmup);
  if (args["view-frames"]) spec.view_frames = Number(args["view-frames"]);
  if (args["no-freeze"]) spec.freeze = false;
  if (args["no-mask"]) spec.mask_background = false;
  if (args.set.length) {
    spec.set = spec.set ?? {};
    for (const s of args.set) {
      const eq = s.indexOf("=");
      if (eq < 0) die(`--set '${s}' needs target:property=value`);
      spec.set[s.slice(0, eq)] = parseSetValue(s.slice(eq + 1));
    }
  }
  if (!spec.shots) {
    const shot = { name: args.name ?? "shot" };
    if (args.camera) shot.camera = args.camera;
    if (args.eye || args.target) {
      if (!args.eye || !args.target) die("--eye and --target go together");
      shot.eye = vec(args.eye, "eye");
      shot.target = vec(args.target, "target");
      if (args.fov) shot.fov = Number(args.fov);
    }
    spec.shots = [shot];
  }
  const kind = args.kind ?? spec.kind ?? "day";
  const size = String(args.size ?? spec.size ?? "1280x720");
  if (!/^\d+x\d+$/.test(size)) die("--size must be WIDTHxHEIGHT");

  const specPath = path.join(outDir, "spec.json");
  fs.writeFileSync(specPath, JSON.stringify(spec, null, 2));

  const godotArgs = [
    "--path", project,
    "--script", `${GODOT_DIR}/capture.gd`,
    "--resolution", size,
    // Off-screen, never minimized: a minimized window on Windows stops drawing.
    "--position", "-20000,-20000",
    "--fixed-fps", "60",
    "--audio-driver", "Dummy",
    "--", "--spec", fwd(specPath),
  ];
  const res = await runGodot(godot, godotArgs, Number(args.timeout ?? 240));
  const scan = scanOutput(res.out);
  fs.writeFileSync(path.join(outDir, "godot.log"), res.out);

  const statsPath = path.join(outDir, "stats.json");
  if (!scan.events.some((e) => e.type === "done") || !fs.existsSync(statsPath)) {
    reportEngine(scan);
    die(`capture failed (exit ${res.code}); full log: ${fwd(path.join(outDir, "godot.log"))}`, 1);
  }
  const stats = JSON.parse(fs.readFileSync(statsPath, "utf8"));
  const findings = evaluate(stats, kind);
  fs.writeFileSync(path.join(outDir, "findings.json"), JSON.stringify({ kind, findings }, null, 2));

  if (args.json) {
    console.log(JSON.stringify({ out_dir: outDir, kind, stats, findings }, null, 2));
    return;
  }
  printCapture(stats, findings, kind, outDir);
  reportEngine(scan);
}

const fmt = (v, d = 2) => (typeof v === "number" ? v.toFixed(d) : "-");

function printCapture(stats, findings, kind, outDir) {
  const env = stats.environment;
  console.log(`lookdev capture  ${stats.scene}  ${stats.resolution.join("x")}  kind=${kind}`);
  console.log(
    `  physical light units: ${stats.physical_light_units ? "on" : "off"}   renderer: ${stats.rendering_method}` +
      (env.present
        ? `   tonemap: ${TONEMAPS[env.tonemap_mode]}  exposure ${env.tonemap_exposure}  GI: ${env.sdfgi ? "SDFGI" : "none"}` +
          `  SSAO ${env.ssao ? "on" : "off"}  SSIL ${env.ssil ? "on" : "off"}  fog ${env.fog || env.volumetric_fog ? "on" : "off"}`
        : "   NO ENVIRONMENT"),
  );
  for (const s of stats.set) console.log(`  set ${s.key}: ${s.ok ? "ok" : "FAILED - " + s.error}`);
  for (const f of findings.filter((f) => f.shot === null)) {
    console.log(`  ${f.severity.toUpperCase().padEnd(5)} ${f.code}: ${f.message}`);
  }
  for (const shot of stats.shots) {
    const lit = shot.stats.lit;
    const lighting = shot.stats.lighting;
    const alb = shot.stats.unshaded;
    console.log(`\n[${shot.name}] camera ${shot.camera.node} eye=${shot.camera.eye.join(",")} fov=${fmt(shot.camera.fov, 0)}`);
    if (lit?.pixels) {
      console.log(
        `  exposure  median ${fmt(lit.luma_p50)}  mean ${fmt(lit.luma_mean)}  p1-p99 ${fmt(lit.luma_p1)}-${fmt(lit.luma_p99)}` +
          `  clipped ${fmt(lit.clipped_pct, 1)}%  crushed ${fmt(lit.crushed_pct, 1)}%  sky ${fmt(100 * lit.background_fraction, 0)}%`,
      );
      console.log(
        `  colour    sat ${fmt(lit.saturation_mean)}  hot ${fmt(lit.saturation_hot_pct, 1)}%  cast a*${fmt(lit.lab_a_mean, 1)} b*${fmt(lit.lab_b_mean, 1)}` +
          `  warm/cool split ${fmt(lit.warm_cool_split, 1)}  shadow detail ${fmt(lit.shadow_detail)}`,
      );
    }
    if (lighting?.pixels) {
      console.log(`  lighting  lit:shade ${fmt(lighting.lit_to_shade_ratio)} (${fmt(lighting.lit_to_shade_stops, 1)} stops)  clipped ${fmt(lighting.lighting_clipped_pct, 1)}%`);
    }
    if (alb?.pixels) {
      console.log(
        `  albedo    mean ${fmt(alb.albedo_mean_linear, 3)} linear  <30 sRGB ${fmt(alb.albedo_too_dark_pct, 1)}%  >240 sRGB ${fmt(alb.albedo_too_bright_pct, 1)}%` +
          `  oversaturated ${fmt(alb.albedo_oversaturated_pct, 1)}%`,
      );
    }
    const g = shot.probes?.gray;
    if (g) console.log(`  grey probe  ${g.lit?.visible ? `lit ${fmt(g.lit.display)} display` : "not visible in shot"}`);
    const kf = shot.probes?.key_fill;
    if (kf?.measured) {
      console.log(`  key/fill  ${fmt(kf.key_fill_stops, 1)} stops (key ${fmt(kf.key_linear, 3)}, fill ${fmt(kf.fill_linear, 3)} linear on 18% grey${kf.clipped_pct > 0 ? `, ${kf.clipped_pct}% clipped - ratio understated` : ""})  ${kf.image}`);
    } else if (kf) {
      console.log(`  key/fill  not measured: ${kf.reason}`);
    }
    for (const f of findings.filter((f) => f.shot === shot.name)) {
      console.log(`  ${f.severity.toUpperCase().padEnd(5)} ${f.code}: ${f.message}`);
    }
    console.log(`  files: ${stats.views.map((v) => shot.files[v]).join("  ")}`);
  }
  if (stats.sheet) console.log(`\ncontact sheet (rows = shots, columns = ${stats.views.join(", ")}): ${stats.sheet}`);
  console.log(`out: ${outDir}`);
}

const TONEMAPS = ["Linear", "Reinhard", "Filmic", "ACES", "AgX"];

function inRange(v, range) {
  return !range || typeof v !== "number" || (v >= range[0] && v <= range[1]);
}

// Turns stats into findings. These are heuristics with the reasoning attached,
// meant to direct a look at the image - never a substitute for one.
function evaluate(stats, kind) {
  const all = JSON.parse(fs.readFileSync(THRESHOLDS, "utf8"));
  const t = all.kinds[kind];
  if (!t) die(`unknown --kind '${kind}' (known: ${Object.keys(all.kinds).join(", ")})`);
  const findings = [];
  const add = (shot, severity, code, message) => findings.push({ shot, severity, code, message });

  const env = stats.environment;
  if (!env.present) add(null, "warn", "NO_ENVIRONMENT", "no WorldEnvironment: default flat ambient and linear tonemapping. Run `lint` for fixes.");
  else if (env.tonemap_mode < 2) add(null, "warn", "TONEMAP", `${TONEMAPS[env.tonemap_mode]} tonemapping clips highlights hard; AgX (tonemap_mode 4) is the realistic default.`);

  for (const shot of stats.shots) {
    const n = shot.name;
    const lit = shot.stats.lit;
    if (lit?.pixels) {
      if (!inRange(lit.luma_p50, t.luma_p50)) {
        const dir = lit.luma_p50 < t.luma_p50[0] ? "under" : "over";
        add(n, "warn", "EXPOSURE", `median display luma ${fmt(lit.luma_p50)} is ${dir}exposed for '${kind}' (${t.luma_p50.join("-")}). Adjust exposure (tonemap_exposure or camera attributes), not light energies.`);
      }
      if (lit.clipped_pct > t.clipped_pct_max) add(n, "warn", "CLIPPING", `${fmt(lit.clipped_pct, 1)}% of non-sky pixels clipped (max ${t.clipped_pct_max}%). Lower exposure, use AgX, or check emissive/glow.`);
      if (lit.crushed_pct > t.crushed_pct_max) add(n, "warn", "CRUSHED", `${fmt(lit.crushed_pct, 1)}% of pixels crushed to black (max ${t.crushed_pct_max}%). Shadows need sky/GI fill, or exposure is too low.`);
      if (lit.luma_p99 - lit.luma_p1 < t.range_p1_p99_min) add(n, "info", "FLAT_RANGE", `tonal range p1-p99 is only ${fmt(lit.luma_p99 - lit.luma_p1)} (want >= ${t.range_p1_p99_min}); frames that use little of the range read as flat CG.`);
      if (lit.saturation_hot_pct > t.saturation_hot_pct_max) add(n, "info", "OVERSATURATED", `${fmt(lit.saturation_hot_pct, 1)}% bright, near-fully-saturated pixels; natural albedo rarely goes there.`);
      if (t.cast_ab_max != null && Math.hypot(lit.lab_a_mean, lit.lab_b_mean) > t.cast_ab_max) add(n, "info", "COLOUR_CAST", `average colour cast a*${fmt(lit.lab_a_mean, 1)} b*${fmt(lit.lab_b_mean, 1)} - intended?`);
      if (t.warm_cool_split_min != null && lit.warm_cool_split < t.warm_cool_split_min) add(n, "info", "NO_WARM_COOL", `lit areas are not warmer than shadows (split ${fmt(lit.warm_cool_split, 1)}, want > ${t.warm_cool_split_min}). Sunlit scenes read real with a warm key and sky-blue fill.`);
      if (lit.shadow_detail < all.shadow_detail_min) add(n, "info", "FLAT_SHADOWS", `shadows carry little texture (detail ${fmt(lit.shadow_detail)}); flat fill or crushed blacks.`);
    }
    // Key/fill from the side-on probe is the real measurement. The frame's
    // lit-to-shade spread is only a fallback: it depends on composition, and a
    // frame that is mostly one sunlit floor reads "flat" whatever the lights do.
    const kf = shot.probes?.key_fill;
    const lighting = shot.stats.lighting;
    let stops = null;
    let source = "";
    if (kf?.measured) {
      stops = kf.key_fill_stops;
      source = "on the grey probe (key vs fill side)";
    } else if (lighting?.pixels) {
      stops = lighting.lit_to_shade_stops;
      source = "across the frame (composition-dependent - capture with --probes for a real key/fill reading)";
    }
    if (stops !== null && t.key_fill_stops && !inRange(stops, t.key_fill_stops)) {
      const low = stops < t.key_fill_stops[0];
      add(n, kf?.measured ? "warn" : "info", low ? "FLAT_LIGHTING" : "HARSH_LIGHTING",
        low
          ? `only ${fmt(stops, 1)} stops between key and fill ${source} (want ${t.key_fill_stops.join("-")}): sky/ambient is drowning the key. Lower the sky's energy (sky material energy_multiplier - ambient_light_energy does nothing for sky ambient), or raise the key.`
          : `${fmt(stops, 1)} stops between key and fill ${source} (want ${t.key_fill_stops.join("-")}): shadows are starved. Ambient from the sky, SDFGI/SSIL, or a fill light.`);
    }
    if (kf?.measured && t.key_exposure_stops) {
      const ev = Math.log2(Math.max(kf.key_linear, 1e-4));
      if (!inRange(ev, t.key_exposure_stops)) {
        add(n, "warn", "KEY_EXPOSURE",
          `a white surface facing the key reads ${fmt(kf.key_linear)} linear (${ev > 0 ? "+" : ""}${fmt(ev, 1)} stops from 1.0; want ${t.key_exposure_stops.join(" to ")}). ` +
          (ev > 0 ? "Lower exposure (tonemap_exposure / camera attributes)" : "Raise exposure") +
          ` rather than changing the light, unless key/fill is also off.`);
      }
    }
    const alb = shot.stats.unshaded;
    if (alb?.pixels) {
      if (alb.albedo_too_dark_pct > t.albedo_too_dark_pct_max) add(n, "warn", "ALBEDO_DARK", `${fmt(alb.albedo_too_dark_pct, 1)}% of visible base colour is below 30 sRGB. Real dielectrics rarely go under ~0.03 linear. Metals also render black in this view - check which it is.`);
      if (alb.albedo_too_bright_pct > t.albedo_too_bright_pct_max) add(n, "warn", "ALBEDO_BRIGHT", `${fmt(alb.albedo_too_bright_pct, 1)}% of visible base colour is above 240 sRGB. Even fresh snow is ~0.85 linear; white paint 0.7-0.8. Labels and emissive surfaces also land here.`);
    }
    const g = shot.probes?.gray;
    if (g?.lit?.visible && t.gray_probe_display && !inRange(g.lit.display, t.gray_probe_display)) {
      add(n, "warn", "GREY_PROBE", `18% grey probe reads ${fmt(g.lit.display)} display (want ${t.gray_probe_display.join("-")} for '${kind}'); exposure and key-light balance are off where it sits.`);
    }
  }
  return findings;
}

// ------------------------------------------------------------------- lint

async function lint(args) {
  const project = findProject(args);
  const godot = findGodot(args, project);
  const outDir = fwd(writableDir(args.out ?? defaultOut(project, "lint"), "lint"));
  const outFile = `${outDir}/lint.json`;
  const res = await runGodot(
    godot,
    ["--headless", "--path", project, "--script", `${GODOT_DIR}/lint.gd`, "--", "--scene", scenePath(args.scene, project), "--out", outFile],
    Number(args.timeout ?? 120),
  );
  const scan = scanOutput(res.out);
  if (!fs.existsSync(outFile)) {
    reportEngine(scan);
    die(`lint failed (exit ${res.code})`, 1);
  }
  const report = JSON.parse(fs.readFileSync(outFile, "utf8"));
  const errors = report.findings.filter((f) => f.severity === "error").length;
  if (args.json) {
    console.log(JSON.stringify(report, null, 2));
    if (errors) process.exitCode = 1;
    return;
  }
  const order = { error: 0, warn: 1, info: 2 };
  report.findings.sort((a, b) => order[a.severity] - order[b.severity]);
  const counts = { error: 0, warn: 0, info: 0 };
  for (const f of report.findings) counts[f.severity]++;
  console.log(`lookdev lint  ${report.scene}   physical light units ${report.physical_light_units ? "on" : "off"}   renderer ${report.rendering_method}`);
  console.log(`  ${counts.error} error, ${counts.warn} warn, ${counts.info} info   (${report.checked.materials} materials, ${report.checked.lights} lights)\n`);
  for (const f of report.findings) {
    console.log(`${f.severity.toUpperCase().padEnd(5)} ${f.code}  ${f.where}`);
    console.log(`      ${f.message}`);
    if (f.fix) console.log(`      fix: ${f.fix}`);
  }
  console.log(`\nout: ${outFile}`);
  reportEngine(scan);
  // error = renders wrong or measured nothing (NO_MATERIALS): a lint that exits 0 there is a pass.
  if (errors) process.exitCode = 1;
}

// ----------------------------------------------------------------- preset

function listPresets() {
  const p = JSON.parse(fs.readFileSync(PRESETS, "utf8"));
  for (const [name, def] of Object.entries(p.presets)) {
    const needs = def.needs ? ` [needs ${def.needs}]` : "";
    console.log(`${name.padEnd(18)} kind=${def.kind.padEnd(9)} ${def.description}${needs}`);
  }
}

async function preset(args) {
  const project = findProject(args);
  const godot = findGodot(args, project);
  if (!args.preset) die("--preset is required (see `lookdev.mjs presets`)");
  const scene = scenePath(args.scene, project);
  let out;
  if (args["in-place"]) {
    out = scene;
  } else if (args.out) {
    out = scenePath(args.out, project);
    if (!out.startsWith("res://")) fs.mkdirSync(path.dirname(out), { recursive: true });
  } else {
    // Default: a scratch copy outside the project, so trying a preset never
    // dirties the repo. Capture it by passing this path as --scene.
    const base = path.basename(scene, ".tscn");
    out = fwd(path.join(defaultOut(project, "preset"), `${base}.${args.preset}.tscn`));
    fs.mkdirSync(path.dirname(out), { recursive: true });
  }
  const gArgs = ["--headless", "--path", project, "--script", `${GODOT_DIR}/apply_preset.gd`, "--",
    "--scene", scene, "--out", out, "--preset", args.preset, "--presets", fwd(PRESETS)];
  for (const k of ["elevation", "azimuth", "energy-scale", "stage"]) if (args[k] !== undefined) gArgs.push(`--${k}`, String(args[k]));
  if (args.force) gArgs.push("--force");
  const res = await runGodot(godot, gArgs, Number(args.timeout ?? 120));
  const scan = scanOutput(res.out);
  const done = scan.events.find((e) => e.type === "done");
  for (const e of scan.events.filter((e) => e.type === "change")) console.log(`  ${e.what}`);
  reportEngine(scan);
  if (!done) die(`preset failed (exit ${res.code})`, 1);
  console.log(`\nwrote ${done.out}  (kind=${done.kind}, physical light units ${done.physical_light_units ? "on" : "off"}` +
    (done.needs ? `, needs ${done.needs}, stage ${done.stage}` : "") + ")");
  console.log(`capture it:  node ${fwd(path.join(HERE, "lookdev.mjs"))} capture --project ${fwd(project)} --scene ${done.out} --kind ${done.kind} --probes`);
}

// ---------------------------------------------------------------- compare

async function compare(args) {
  const project = findProject(args);
  const godot = findGodot(args, project);
  if (!args.a || !args.b) die("--a and --b are required (PNG files or capture directories)");
  const outDir = fwd(args.out ?? defaultOut(project, "compare"));
  fs.mkdirSync(outDir, { recursive: true });

  const pairs = [];
  const isDir = (p) => fs.statSync(p).isDirectory();
  if (isDir(args.a) && isDir(args.b)) {
    for (const f of fs.readdirSync(args.a)) {
      const views = String(args.views ?? "lit").split(",");
      const isView = views.some((v) => f.endsWith(`_${v}.png`));
      if (isView && fs.existsSync(path.join(args.b, f))) {
        pairs.push([fwd(path.join(args.a, f)), fwd(path.join(args.b, f)), f.replace(/\.png$/, "")]);
      }
    }
  } else {
    pairs.push([fwd(args.a), fwd(args.b), "pair"]);
  }
  if (!pairs.length) die("no matching PNGs to compare");
  const pairFile = `${outDir}/pairs.json`;
  fs.writeFileSync(pairFile, JSON.stringify(pairs.map(([a, b, name]) => ({ a, b, name }))));
  const res = await runGodot(
    godot,
    ["--headless", "--path", project, "--script", `${GODOT_DIR}/compare.gd`, "--", "--pairs", pairFile, "--out", outDir],
    Number(args.timeout ?? 120),
  );
  const scan = scanOutput(res.out);
  const resultFile = `${outDir}/compare.json`;
  if (!fs.existsSync(resultFile)) {
    reportEngine(scan);
    die(`compare failed (exit ${res.code})`, 1);
  }
  const result = JSON.parse(fs.readFileSync(resultFile, "utf8"));
  if (args.json) {
    console.log(JSON.stringify(result, null, 2));
    return;
  }
  const keys = ["luma_p50", "luma_p1", "luma_p99", "clipped_pct", "crushed_pct", "saturation_mean", "warm_cool_split", "shadow_detail"];
  for (const r of result.pairs) {
    console.log(`\n[${r.name}] ${r.size_match ? `rms diff ${fmt(r.metrics?.root_mean_squared, 2)}  psnr ${fmt(r.metrics?.peak_snr, 1)}dB` : "sizes differ"}`);
    console.log(`  ${"".padEnd(16)}${"A".padStart(8)}${"B".padStart(8)}${"B-A".padStart(8)}`);
    for (const k of keys) {
      const a = r.a_stats?.[k];
      const b = r.b_stats?.[k];
      if (typeof a !== "number") continue;
      console.log(`  ${k.padEnd(16)}${fmt(a).padStart(8)}${fmt(b).padStart(8)}${fmt(b - a).padStart(8)}`);
    }
    console.log(`  side by side: ${r.ab}  (A left)`);
    console.log(`  swapped:      ${r.ba}  (B left) - judge both orders; keep a verdict only if they agree`);
  }
  reportEngine(scan);
}

// ------------------------------------------------------------- close-shot

const CLOSE_VIEWS = ["face", "eyes", "hand_palm.L", "hand_back.L", "hand_palm.R", "hand_back.R", "feet", "bust", "crotch", "full"];
const VIEW_GROUPS = { hands: ["hand_palm.L", "hand_back.L", "hand_palm.R", "hand_back.R"] };
const DEFAULT_CLOSE = "face,eyes,hands,feet,bust,full";

// `face,eyes@0.5,hands,full@4,bone:spine.003` -> [{view, distance}]. A view without @ takes --distance,
// except `full`, which takes --full-distance.
function closeViews(spec, distance, fullDistance) {
  const out = [];
  for (const raw of String(spec).split(",").map((s) => s.trim()).filter(Boolean)) {
    const [name, at] = raw.split("@");
    const d = at !== undefined ? Number(at) : name === "full" ? fullDistance : distance;
    if (!(d > 0)) die(`view '${raw}': distance must be a positive number of metres`);
    for (const v of VIEW_GROUPS[name] ?? [name]) {
      if (!v.startsWith("bone:") && !CLOSE_VIEWS.includes(v)) {
        die(`unknown view '${v}' (views: ${CLOSE_VIEWS.join(" ")}, hands, or bone:<name>)`);
      }
      out.push({ view: v, distance: d });
    }
  }
  return out;
}

function glbPath(glb, project) {
  if (!glb) die("--glb is required");
  if (glb.startsWith("res://")) return glb;
  const abs = path.resolve(glb);
  if (!fs.existsSync(abs)) die(`no file ${fwd(abs)}`);
  const rel = path.relative(project, abs);
  if (!rel.startsWith("..") && !path.isAbsolute(rel)) return "res://" + rel.replaceAll("\\", "/");
  return fwd(abs);
}

async function closeShot(args) {
  const project = findProject(args);
  const godot = findGodot(args, project);
  const outDir = fwd(writableDir(args.out ?? defaultOut(project, "close"), "close-shot"));
  const presets = String(args.presets ?? args.preset ?? "clear_midday,overcast").split(",").filter(Boolean);
  const known = JSON.parse(fs.readFileSync(PRESETS, "utf8")).presets;
  for (const p of presets) {
    if (!known[p]) die(`unknown preset '${p}' (known: ${Object.keys(known).join(", ")})`);
    // close-shot's stage is open: a floor and a backdrop under the sky.
    if (known[p].needs && known[p].needs !== "open" && !args.force) {
      die(`preset ${p} needs an ${known[p].needs} stage, and close-shot renders on an open one, where it clips everything to white. Pass --force to render it anyway.`, 1);
    }
  }
  const size = Number(args.size ?? 640);
  if (!(size >= 128 && size <= 2048)) die("--size is the tile's pixels, 128-2048");
  const spec = {
    glb: glbPath(args.glb, project),
    out_dir: outDir,
    presets,
    views: closeViews(args.views ?? DEFAULT_CLOSE, Number(args.distance ?? 1.0), Number(args["full-distance"] ?? 4.0)),
    clip: args.clip ?? "",
    time: Number(args.time ?? 0),
    garments: args.garments ? String(args.garments).split(",").map((g) => (g.startsWith("res://") ? g : fwd(g))) : [],
    strands: !args["no-strands"],
    force: !!args.force,
    min_coverage: Number(args["min-coverage"] ?? 0.03),
    sheet_tile: Number(args["sheet-tile"] ?? 384),
    columns: Number(args.columns ?? 5),
    warmup_frames: Number(args.warmup ?? 45),
    view_frames: Number(args["view-frames"] ?? 24),
  };
  const specPath = path.join(outDir, "spec.json");
  fs.writeFileSync(specPath, JSON.stringify(spec, null, 2));
  for (const d of addonDrift(project)) console.log(`WARN   ${d} - sync it, or the render uses stale code`);
  const res = await runGodot(godot, [
    "--path", project,
    "--script", `${GODOT_DIR}/close_shot.gd`,
    "--resolution", `${size}x${size}`,
    "--position", "-20000,-20000",
    "--fixed-fps", "60",
    "--audio-driver", "Dummy",
    "--", "--spec", fwd(specPath),
  ], Number(args.timeout ?? 300));
  const scan = scanOutput(res.out);
  fs.writeFileSync(path.join(outDir, "godot.log"), res.out);
  const done = scan.events.find((e) => e.type === "done");
  const statsPath = path.join(outDir, "close.json");
  if (!done || !fs.existsSync(statsPath)) {
    reportEngine(scan);
    die(`close-shot failed (exit ${res.code}); full log: ${fwd(path.join(outDir, "godot.log"))}`, 1);
  }
  const stats = JSON.parse(fs.readFileSync(statsPath, "utf8"));
  if (args.json) {
    console.log(JSON.stringify(stats, null, 2));
  } else {
    console.log(`lookdev close-shot  ${stats.glb}  ${stats.clip || "rest pose"}  tiles ${stats.tile_px.join("x")}`);
    for (const n of stats.notes) console.log(`  note: ${n}`);
    console.log(`  materials: ${(stats.materials.materials ?? []).join(", ") || "(no lookdev extras)"}`);
    for (const t of stats.tiles) {
      console.log(
        `  ${t.preset.padEnd(14)} ${t.view.padEnd(12)} ${fmt(t.distance_m)} m  fov ${fmt(t.fov_deg, 1).padStart(5)}  ` +
          `frame ${fmt(t.frame_m, 3)} m  figure ${fmt(100 * t.figure_coverage, 0).padStart(3)}%` +
          (t.failures.length ? `  FAIL ${t.failures.join("; ")}` : ""),
      );
    }
    console.log(`\nsheet (rows = presets, columns = views; each tile labelled view, distance, preset, fov): ${stats.sheet}`);
    console.log(`out: ${outDir}`);
    reportEngine(scan);
  }
  if (stats.failures.length) {
    console.log(`\n${stats.failures.length} tile(s) failed: an empty or off-target tile is not a picture of the subject.`);
    process.exitCode = 1;
  }
}

// ------------------------------------------------------------------- tone

async function tone(args) {
  const project = findProject(args);
  const godot = findGodot(args, project);
  const glb = glbPath(args.glb, project);
  const outDir = fwd(writableDir(args.out ?? defaultOut(project, "tone"), "tone"));
  const outFile = `${outDir}/tone.json`;
  const gArgs = ["--headless", "--path", project, "--script", `${GODOT_DIR}/glb_tone.gd`, "--", "--glb", glb, "--out", outFile];
  for (const k of ["material", "size", "expect"]) if (args[k] !== undefined) gArgs.push(`--${k}`, String(args[k]));
  const res = await runGodot(godot, gArgs, Number(args.timeout ?? 120));
  const scan = scanOutput(res.out);
  if (!scan.events.some((e) => e.type === "done") || !fs.existsSync(outFile)) {
    reportEngine(scan);
    die(`tone failed (exit ${res.code})`, 1);
  }
  const rep = JSON.parse(fs.readFileSync(outFile, "utf8"));
  if (args.json) {
    console.log(JSON.stringify(rep, null, 2));
  } else {
    console.log(`lookdev tone  ${rep.glb}   ok = linear luminance ${rep.luma_range.join("-")} over the UV-covered texels`);
    for (const m of rep.materials) {
      const srgb = m.mean_srgb ? m.mean_srgb.map((v) => fmt(v, 3)).join(",") : "-";
      console.log(
        `  ${m.ok ? "ok  " : "BAD "} ${m.name.padEnd(26)} luma ${fmt(m.luma_linear, 4)} linear  sRGB ${srgb}  covered ${fmt(100 * (m.coverage ?? 0), 1)}%` +
          (m.delta_srgb ? `  vs expect ${m.delta_srgb.map((v) => fmt(v, 3)).join(",")}` : "") +
          (m.why ? `  ${m.why}` : "") + (m.note ? `  (${m.note})` : ""),
      );
    }
    console.log(`out: ${outFile}`);
  }
  if (!rep.ok) process.exitCode = 1;
}

// --------------------------------------------------------------- selftest

// The controls: each check here must be able to fail, and fails on a case built to fail.
function runSelf(argv, timeoutSec = 400) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [fileURLToPath(import.meta.url), ...argv]);
    let out = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (out += d));
    const timer = setTimeout(() => child.kill(), timeoutSec * 1000);
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ code, out });
    });
  });
}

function findCharacter(project) {
  const stack = [path.join(project, "assets")];
  while (stack.length) {
    const d = stack.pop();
    if (!fs.existsSync(d)) continue;
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) stack.push(p);
      else if (e.name.endsWith(".moves.json")) {
        try {
          const m = JSON.parse(fs.readFileSync(p, "utf8"));
          if (m.scene && fs.existsSync(path.join(project, m.scene.replace("res://", "")))) return m.scene;
        } catch {
          /* not a manifest */
        }
      }
    }
  }
  return null;
}

async function selftest(args) {
  const project = findProject(args);
  const godot = findGodot(args, project);
  const dir = fwd(writableDir(args.out ?? defaultOut(project, "selftest"), "selftest"));
  const common = ["--project", fwd(project), "--godot", godot];
  const results = [];
  const check = (name, passed, detail) => {
    results.push(passed);
    console.log(`${passed ? "ok  " : "FAIL"} ${name}: ${detail}`);
  };
  const firstLine = (out, re) => (out.split(/\r?\n/).find((l) => re.test(l)) ?? out.trim().split(/\r?\n/).pop() ?? "").trim();

  // tone: a black albedo is not ok, an 18% grey one reads 0.18
  const tres = await runGodot(godot, ["--headless", "--path", project, "--script", `${GODOT_DIR}/glb_tone.gd`, "--", "--selftest", "--out-dir", `${dir}/tone`], 120);
  const toneLines = tres.out.split(/\r?\n/).filter((l) => l.startsWith("TONE_SELFTEST"));
  check("tone control", tres.code === 0 && /PASSED/.test(toneLines.at(-1) ?? ""), toneLines.join(" | ") || `exit ${tres.code}`);

  // a scene with nothing in it
  const empty = `${dir}/empty_stage.tscn`;
  fs.writeFileSync(empty, '[gd_scene format=3]\n\n[node name="Empty" type="Node3D"]\n');
  const lint0 = await runSelf(["lint", ...common, "--scene", empty, "--out", `${dir}/lint`]);
  check("lint on 0 materials fails", lint0.code === 1 && /NO_MATERIALS/.test(lint0.out), `exit ${lint0.code}, ${firstLine(lint0.out, /NO_MATERIALS/)}`);

  const blocker = `${dir}/not_a_folder.txt`;
  fs.writeFileSync(blocker, "a file where --out wants a folder");
  const capOut = await runSelf(["capture", ...common, "--scene", empty, "--out", `${blocker}/capture`]);
  check("capture with an unopenable --out fails", capOut.code === 1 && /cannot write/.test(capOut.out), `exit ${capOut.code}, ${firstLine(capOut.out, /cannot write/)}`);
  const lintOut = await runSelf(["lint", ...common, "--scene", empty, "--out", `${blocker}/lint`]);
  check("lint with an unopenable --out fails", lintOut.code === 1 && /cannot write/.test(lintOut.out), `exit ${lintOut.code}, ${firstLine(lintOut.out, /cannot write/)}`);
  const cap0 = await runSelf(["capture", ...common, "--scene", empty, "--out", `${dir}/capture0`, "--eye", "0,1.6,3", "--target", "0,1,0"]);
  check("capture on 0 materials fails", cap0.code === 1 && /0 materials/.test(cap0.out), `exit ${cap0.code}, ${firstLine(cap0.out, /0 materials/)}`);

  // interior_daylight on an open stage
  const pre = await runSelf(["preset", ...common, "--scene", empty, "--preset", "interior_daylight", "--out", `${dir}/interior.tscn`]);
  check("preset interior_daylight on an open stage is refused", pre.code === 1 && /needs an interior stage/.test(pre.out), firstLine(pre.out, /needs an interior/));
  const preOk = await runSelf(["preset", ...common, "--scene", empty, "--preset", "clear_midday", "--out", `${dir}/midday.tscn`]);
  check("preset clear_midday on the same stage applies (the refusal is specific)", preOk.code === 0 && fs.existsSync(`${dir}/midday.tscn`), `exit ${preOk.code}`);
  // ... and a closed room is measured as an interior, where interior_daylight applies
  const room = `${dir}/closed_room.tscn`;
  fs.writeFileSync(room, [
    '[gd_scene load_steps=2 format=3]', '',
    '[sub_resource type="BoxMesh" id="1"]', 'size = Vector3(8, 3, 6)', 'flip_faces = true', '',
    '[node name="Room" type="Node3D"]', '',
    '[node name="Walls" type="MeshInstance3D" parent="."]', 'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 1.5, 0)', 'mesh = SubResource("1")', '',
    '[node name="Camera3D" type="Camera3D" parent="."]', 'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 1.6, 2)', '',
  ].join("\n"));
  const inRoom = await runSelf(["preset", ...common, "--scene", room, "--preset", "interior_daylight", "--out", `${dir}/room_interior.tscn`]);
  check("preset interior_daylight in a closed room applies (the stage test can say interior)", inRoom.code === 0 && /stage interior/.test(inRoom.out), firstLine(inRoom.out, /stage measured/));

  // close-shot: no skeleton, a missing bone, an interior preset
  const quad = `${dir}/tone/tone_control_grey18.glb`;
  const noSkel = await runSelf(["close-shot", ...common, "--glb", quad, "--views", "face", "--presets", "clear_midday", "--out", `${dir}/close_noskel`]);
  check("close-shot on a glb with no skeleton fails", noSkel.code === 1 && /no Skeleton3D/.test(noSkel.out), firstLine(noSkel.out, /no Skeleton3D/));
  const character = args.glb ? glbPath(args.glb, project) : findCharacter(project);
  if (!character) {
    check("close-shot on a missing bone fails", false, "no rigged character found (pass --glb)");
  } else {
    const bad = await runSelf(["close-shot", ...common, "--glb", character, "--views", "face,bone:no_such_bone", "--presets", "clear_midday", "--out", `${dir}/close_badbone`]);
    check("close-shot aimed at a nonexistent bone fails before rendering", bad.code === 1 && /no bone 'no_such_bone'/.test(bad.out) && !fs.existsSync(`${dir}/close_badbone/clear_midday_face.png`),
      firstLine(bad.out, /no_such_bone/).slice(0, 160));
    const inter = await runSelf(["close-shot", ...common, "--glb", character, "--views", "face", "--presets", "interior_daylight", "--out", `${dir}/close_interior`]);
    check("close-shot refuses interior_daylight on its open stage", inter.code === 1 && /needs an interior stage/.test(inter.out), firstLine(inter.out, /needs an interior/).slice(0, 160));
  }
  const failed = results.filter((r) => !r).length;
  console.log(`\nlookdev selftest ${failed ? "FAILED" : "PASSED"} (${results.length - failed}/${results.length} controls failed as they must)   out: ${dir}`);
  if (failed) process.exitCode = 1;
}

// ------------------------------------------------------------------- main

const USAGE = `lookdev - lighting and shading tools for Godot

  capture  --project <dir> --scene <res://|path> [--camera Node | --eye x,y,z --target x,y,z --fov 50]
           [--views lit,unshaded,lighting] [--probes] [--kind day|golden|overcast|interior|night]
           [--set "@env:tonemap_mode=4"]... [--size 1280x720] [--spec shots.json] [--out dir] [--json]
  lint     --project <dir> --scene <res://|path> [--json]
  preset   --project <dir> --scene <res://|path> --preset <name> [--elevation deg] [--azimuth deg]
           [--out <path> | --in-place] [--stage open|interior] [--force]
  presets  list available presets
  close-shot --project <dir> --glb <res://|path> [--distance 1] [--full-distance 4]
           [--views face,eyes,hands,feet,bust,full] [--presets clear_midday,overcast] [--clip Idle] [--time 0]
           [--garments a.glb,b.glb] [--no-strands] [--size 640] [--out dir] [--json]
  tone     --project <dir> --glb <res://|path> [--material skin] [--expect r,g,b] [--json]
  selftest --project <dir> [--glb <rigged character>]   run the controls (each must fail)
  compare  --project <dir> --a <png|capture dir> --b <png|capture dir> [--views lit,unshaded] [--out dir]

Views: lit unshaded lighting normal overdraw ssao ssil pssm sdfgi sdfgi_probes gi_buffer voxel_gi_lighting luminance
Set targets: @env @sun @camera @world or a node path, e.g. --set "Sun:light_energy=2" --set "@env:ssao_enabled=true"
Godot binary: --godot <path>, LOOKDEV_GODOT, GODOT_PATH, or the project's .mcp.json.`;

const args = parseArgs(process.argv.slice(2));
const cmd = args._[0];
const commands = { capture, lint, preset, compare, presets: listPresets, "close-shot": closeShot, tone, selftest };
if (!cmd || args.help || !commands[cmd]) {
  console.log(USAGE);
  process.exit(cmd && !args.help ? 2 : 0);
}
await commands[cmd](args);
