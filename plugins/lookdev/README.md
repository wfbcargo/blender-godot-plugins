# lookdev

Lighting and shading tools for Claude Code working on **Godot 4.7** scenes with
**Blender 5.x** assets.

An agent can't judge lighting from a single screenshot, and Godot won't tell
you when lighting is wrong: a flat, washed-out scene is still a valid scene. So
lookdev gives the agent a way to **see and measure** a scene, a staged workflow
that stops it tuning everything at once, and the Godot and Blender gotchas that
cost hours, each verified rather than recalled.

## What's in it

| | |
|---|---|
| `capture` | Renders a scene in an off-screen window (not headless: that renders nothing) from chosen cameras, in lit / albedo / lighting-only / normal and other debug views. Writes PNGs, a contact sheet and `stats.json`: exposure percentiles, clipping, crushed blacks, saturation, colour cast, warm/cool split, sky masked out. With `--probes` it adds an 18% grey and a chrome ball and measures **key-to-fill in stops** from the side. `--set` tries property changes without editing the scene. |
| `lint` | Headless static checks on a scene: tonemapper, ambient that erases form, missing GI/AO/fog, sun below the horizon, shadow bias, ignored properties, implausible albedo and metal values, uniform surfaces, unbaked GI nodes. Every finding names the property to change. |
| `preset` | Five lighting recipes (clear midday, golden hour, overcast, interior daylight, night), applied to a copy of the scene. Calibrated by measurement in both relative and physical light-unit modes. |
| `compare` | Side-by-side images in both orders plus stat deltas, for position-bias-free A/B judging. |
| `close-shot` | One command to judge a character in Godot: a labelled sheet of face, eyes, palms and backs of the hands, feet, bust and full body under named presets, cameras aimed from the posed frame's bones, the lens chosen so each subject fills its tile; empty or off-target tiles, missing bones and skeleton-less glbs fail. |
| `tone` | A glb's mean albedo per material over the texels its UVs cover; a black albedo is not ok. |
| `selftest` | The controls: every check is shown failing on a case built to fail. |
| Godot addon | `lookdev_materials.gd` (material presets back from glTF extras), `lookdev_presets.gd` + `presets.json` (the lighting recipes applied at runtime, the same code `preset` uses). |
| Blender `material_lint` | Finds inputs the glTF exporter silently drops (procedural textures, ramps, bump, mix shaders), features Godot ignores on import (clearcoat, sheen, transmission, IOR), colour-space mistakes, missing UVs. |
| Blender `bake` | Bakes base colour, roughness, metallic, normal, emission and AO to textures, packs ORM, and builds the material layout glTF and Godot read, on a duplicate. |
| Blender `export` | glTF export with Godot-safe settings (COMPAT light units, active scene only, tangents), read back and checked. |
| Blender `reference` | AgX reference renders from a camera converted from Godot coordinates, for comparison with a capture. |
| Skill + references | The staged workflow and gates, pairwise judging protocol, "CG tells" checklist, real-world light and PBR value tables, Godot 4.7 lighting reference. |

## Requirements

- Node 18+ (no packages).
- Godot 4.7 (Forward+ for SDFGI/SSIL/volumetric fog). On Windows, the
  `*_console.exe` build.
- For the Blender half: Blender 5.x with the
  [blender-mcp](https://github.com/ahujasid/blender-mcp) addon running.

The runner finds Godot from `--godot`, `LOOKDEV_GODOT`, `GODOT_PATH`, or a
`GODOT_PATH` in the project's `.mcp.json`.

## Install

```
/plugin marketplace add wfbcargo/blender-godot-plugins
/plugin install lookdev@blender-godot-plugins
```

## Quick start

```bash
node bin/lookdev.mjs lint    --project path/to/game --scene res://level.tscn
node bin/lookdev.mjs capture --project path/to/game --scene res://level.tscn --probes --kind day
node bin/lookdev.mjs preset  --project path/to/game --scene res://level.tscn --preset golden_hour
node bin/lookdev.mjs close-shot --project path/to/game --glb res://assets/hero/hero.glb --distance 1 --presets clear_midday,overcast
node bin/lookdev.mjs tone    --project path/to/game --glb res://assets/hero/hero.glb --material skin
```

Captures and preset copies go to the system temp directory
(`%TEMP%/lookdev/<project>/...`), so nothing enters the project unless you pass
`--out` into it or `--in-place`.

## Things it found along the way

Verified while building and calibrating in Godot 4.7.2:

- `Environment.ambient_light_energy` has **no effect** on sky ambient (the
  default setup). It scales only the colour share of ambient.
- `Light3D.light_temperature` does nothing unless physical light units are on.
- A minimized Godot window on Windows renders no frames at all.
- The unshaded debug view is still exposed and tonemapped.
- Frame-wide contrast statistics can't measure lighting balance: a frame that
  is mostly sunlit floor reads as "flat" whatever the lights do. Key/fill has to
  be read off a probe from the side, by surface normal, with linear tonemapping.
- PhysicalSkyMaterial's brightness follows its sun's energy, so the sun:sky
  ratio has to be changed on the sky.
- Godot's physical-camera exposure lands about a stop darker than Sunny-16
  arithmetic.
- Blender's glTF exporter, without `use_active_scene`, exports selected objects
  from *other* scenes too.

## Limits

- Thresholds are heuristics from photographic practice and PBR charts, tuned
  on test scenes. They direct attention; they don't replace looking.
- Preset calibration used an open plane and a one-window room; real levels
  differ, and the workflow says to re-measure.
- LightmapGI can't be baked from outside the editor in 4.7.
- Capture opens a real (off-screen) window for a few seconds per run.

MIT licensed.
