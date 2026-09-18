# Lighting recipes

`godot/addons/lookdev/presets.json` holds five recipes. `lookdev.mjs preset` applies one to
the sun, sky, environment and exposure of a scene copy; a game applies the same recipe at runtime with
the addon's `lookdev_presets.gd` (the offline tool calls that same script). A recipe can say what it
needs: `interior_daylight` has `"needs": "interior"` and is refused on an open stage (most rays up from
the camera reach the sky) unless `--force` / `{"force": true}`. This page is what each
is trying to be, how it was calibrated, and how to adjust it for a real scene.

## What a preset changes, and what it doesn't

Changes: the first DirectionalLight3D (created if missing), the
WorldEnvironment's Environment (created if missing; a shared external `.tres`
is copied into the scene, never edited), its Sky material, and exposure
(`tonemap_exposure`, or `CameraAttributesPhysical` with physical units).

Keeps: the sun's **azimuth** (so the scene's composition stays), an existing
HDRI sky (PanoramaSkyMaterial), every other light, every material.

Override angles with `--elevation` and `--azimuth` (0 = sun toward −Z, 90 =
toward +X). Scale sun energy with `--energy-scale`.

## The recipes

| Preset | Kind | Sun | Sky | Look |
|---|---|---|---|---|
| `clear_midday` | day | 58°, 5600 K, 100k lx / energy 1.8, 0.5° disc | Physical, turbidity 6 | Hard shadows, blue fill, light haze |
| `golden_hour` | golden | 7°, 3000 K, 25k lx / energy 3.0, 1° disc | Physical, turbid, strong Mie | Long soft shadows, warm key vs cool fill, sun scatter in fog |
| `overcast` | overcast | 55°, 6800 K, weak (300 lx / 0.25), 20° disc, soft | Procedural grey | No hard shadows; AO and GI carry form; denser fog |
| `interior_daylight` | interior | 40°, 5600 K, like midday | Physical | SDFGI + SSIL, exposure opened ~4.5 stops, windows may clip |
| `night` | night | "Moon" 35°, 7500 K, 0.3 lx / 0.08 | Procedural near-black | Volumetric fog for halos; **you add practical lights** |

All of them: AgX, sky ambient and reflections, SDFGI with occlusion, SSAO with
`ssao_light_affect` 0.

## Calibration (Godot 4.7.2, Forward+, D3D12)

Measured with `capture --probes`: an open ground plane for the exteriors, and
an 8×6×3 m room with one 2×1.6 m window for the interior.

| Preset | Relative mode: white-in-key / key-fill | Physical mode |
|---|---|---|
| clear_midday | 1.06 / 2.5 stops | 1.20 / 2.3 |
| golden_hour | 1.02 / 2.6 | ~1.0 / ~2.3 |
| overcast | ~0.6-0.9 / 0.2 | ~0.7 / 1.1 |
| night | 0.20 / 3.1 (exposure 5) | 0.17 / 3.0 |
| interior_daylight | median luma ~0.25 | median ~0.43 |

What that calibration taught, beyond the numbers:

- PhysicalSkyMaterial at `energy_multiplier` 1 is dim against its own sun in
  relative mode: key/fill came out 3.3-3.9 stops. It needed ×2 at midday and
  ×7 at golden hour, where scattering darkens the sky further.
- Its brightness scales with the sun's energy, so changing sun energy alone
  doesn't change key/fill. To shift the ratio, change the sky.
- `ambient_light_energy` had no effect at all (see godot-lighting.md).
- SDFGI adds real fill: ~0.035 linear of bounce off a mid-grey ground at midday.

## Adapting a preset to a real scene

Your scene is not an open plane. Dark ground, walls and overhangs cut fill;
bright sand or snow adds it. So after applying:

1. `capture --probes --kind <kind>` on the copy.
2. **Key/fill out of range?** Change sky energy (relative: sky material
   `energy_multiplier` / `sky_energy_multiplier`; physical:
   `background_intensity`). Try it first with `--set` on the capture; don't edit.
3. **Exposure out of range?** `tonemap_exposure` (relative) or shutter speed
   (physical). Each ×2 / ÷2 is a stop.
4. Look at `sheet.png`. If it reads wrong but measures right, say what you see.
   The numbers only cover what they measure.
5. When it's right, write it into the real scene (`--out res://...` or
   `--in-place`) and capture once more from the real file.

For the probe, pick a spot the key light actually reaches: in a spec,
`"probe_at": [x, y, z]` per shot. Indoors, a probe in shadow can't measure the
sun, which is why interior skips key/fill.

## Night and interiors need practical lights

A preset can't know where lamps go. Guidance for placing them:

- OmniLight3D/SpotLight3D with **inverse-square-ish falloff**: `omni_attenuation`
  1-2 and a range long enough that the cutoff is invisible.
- Colour: tungsten 2700 K, sodium street light ~2000 K, LED 3000-4000 K. In
  relative mode use `light_color` from Kelvin.
- Relative mode has no units, and there is no calibrated conversion here. Start
  a lamp at energy 1-4, put a probe in its pool of light (`probe_at`), and tune
  until the pool reads a stop or two above its surroundings. Physical mode:
  use real lumens (bulb 800, street light 5k-20k).
- Shadows on the few lights that matter; > 8 shadowed omni/spots share one
  atlas and blur.
- Emissive surfaces (lamp shades, windows) sell the source: emission on the
  material, plus the actual light next to it.
- Night exposure is a creative choice: physically correct moonlight is nearly
  black on screen. Expose so the moonlit ground reads about −2 stops from
  middle grey, and let the practicals be the brightest things in frame.
