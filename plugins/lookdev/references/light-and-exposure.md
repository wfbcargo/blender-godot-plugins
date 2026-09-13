# Light levels and exposure

Real-world numbers, how they map onto Godot, and the formulas that tie them
together. Marked ≈ where sources disagree or the value is a rule of thumb.

Sources: Filament PBR docs, Unity HDRP "Physical light units", Godot
"Physical light and camera units", physicallybased.info, Wikipedia "Exposure
value".

## Formulas

| | |
|---|---|
| EV from camera | EV = log2(N² / t), N = f-number, t = seconds. At ISO S: EV_S = EV100 + log2(S/100) |
| Incident illuminance | E (lux) = 2.5 × 2^EV100 |
| Scene luminance | L (cd/m²) = 2^(EV100 − 3) |
| Exposure scale (Frostbite/Filament) | H = 1 / (1.2 × 2^EV100); pre-tonemap pixel = L × H |
| Lit diffuse surface | L = E × albedo / π |
| Sunny 16 | f/16 at 1/ISO s in full sun ≈ EV100 14.6-15 |

Sanity check: 100,000 lx on 18% grey → 5730 nits; at EV100 15 that's 0.146
pre-tonemap, close to middle grey 0.18. A consistent sun, albedo and camera put
middle grey near 0.18 before tonemapping.

## Illuminance

| Condition | Lux | EV100 |
|---|---|---|
| Clear noon, sun + sky | 110,000-130,000 | ~15.5 |
| Sun alone, noon | ~100,000 | ~15.3 |
| Blue sky only / open shade | 20,000-25,000 | ~13 |
| Bright overcast | 10,000-25,000 ≈ | 12-13 |
| Dark overcast / storm | 1,000-2,000 | ~9 |
| Sunset / golden hour | 1,000-10,000 ≈ (sun on a surface facing it: 10k-40k) | ~12 |
| Office | 300-500 | 7-7.6 |
| Living room | 50-300 | 4-7 |
| Lit street at night | 10-30 | 2-3.6 |
| Full moon on the ground | 0.05-0.3 (disputed) | −5.6 to −3 |
| Starlight | 0.002 | ~−10 |

Unity's scene EV cheat sheet runs lower (moonless −2, moonlit 1, interior 4,
low sun 7, cloudy 10, sunlit 14); treat all of these as ±1-2 stops.

**Sun:sky ratio** is what reads as real, more than absolute level: clear noon
~4-5:1 on flat ground; a surface in open shade sits ~2-3 stops below one in sun.

## Light sources

| Source | Lumens | Kelvin |
|---|---|---|
| Candle | ~13 | 1850 |
| 40 W-equivalent bulb | ~450 | 2700 |
| 60 W-equivalent bulb | ~800 | 2700 |
| 100 W-equivalent bulb | ~1600 | 2700-3000 |
| Decorative lamp / ceiling light | 200-300 / 400-1200 | 2700-3000 |
| Fluorescent tube | ~2,500-3,000 | 3000-6500 (cool white ~4100) |
| Halogen | - | 3000-3200 |
| Street light | 5,000-20,000 typical (1k-40k) | sodium ~2000, LED 3000-4000 |
| Direct sun, midday | - | 5000-5800 |
| Sun at sunrise/sunset | - | ~1850-3500 |
| Overcast sky | - | 6500-7500 |
| Blue sky / shade | - | 8000-15000 |
| Moonlight | - | ~4100 physically; rendered bluer (7000-9000) by convention |

## In Godot

**Physical light units off (the default):** energies are relative. Only ratios
matter, and exposure is `Environment.tonemap_exposure`. Calibrated values live
in the presets. `light_temperature` does nothing in this mode; set
`light_color` from Kelvin (the presets do).

**Physical light units on** (`rendering/lights_and_shadows/use_physical_light_units`,
Advanced; restart the editor):

| Property | Unit |
|---|---|
| DirectionalLight3D `light_intensity_lux` | lux |
| Omni/Spot `light_intensity_lumens` | lumens |
| `light_temperature` | Kelvin (now active) |
| `Environment.background_intensity` | nits (default 30000) |
| `CameraAttributesPhysical` `exposure_aperture` / `exposure_shutter_speed` / `exposure_sensitivity` | f-number / 1/s / ISO |

Put exposure on `WorldEnvironment.camera_attributes`. A Camera3D's own
attributes override it, and `CameraAttributesPhysical` on a camera also takes
over its FOV and near/far. Measured in 4.7.2: exposure lands about **one stop
darker** than the formulas predict, so full sun wants ~1/60 s at f/16, ISO 100,
not 1/125.

Physical units cost floating-point headroom at extreme ranges. Keep scene scale
at 1 unit = 1 m regardless: falloff, GI cell sizes, SSAO radius and fog all
assume it.

## Reading a capture in these terms

- `key/fill` stops on the grey probe ≈ the photographic sun-vs-shade gap.
- `key_linear` ≈ 1.0 means exposure is metered to the key the way an incident
  meter would. +1 = a stop over, −1 = a stop under.
- The grey probe's lit display value under AgX lands around 0.45-0.55 when that
  holds and the ball faces the key.
