# Godot 4.7 lighting: options, properties, traps

Verified against the 4.7-stable source and class reference, and where marked,
by measurement with lookdev capture.

## Global illumination: which one

| | Renderers | Quality | Dynamic | Bake from a script? |
|---|---|---|---|---|
| **LightmapGI** | Forward+, Mobile | Best; up to 16 bounces; shadowmasks since 4.4 | Static | **No.** The editor's Bake Lightmaps button only (PR #116429 still open) |
| **VoxelGI** | Forward+ | Good; leaks through thin walls | Fully, after bake | **Yes**: `bake()` works at runtime, ~5-20 s |
| **SDFGI** | Forward+ | Good; cascade shifts visible | Semi (dynamic objects receive only) | Nothing to bake; converges over frames |
| **ReflectionProbe** | All | Reflections; weak indirect | `update_mode` Once/Always | Nothing to bake |
| **SSIL / SSAO / SSR** | SSIL, SSR Forward+; SSAO Forward+ & Compat | Screen-space add-ons | Real-time | - |

Start exteriors and large levels with **SDFGI** (`sdfgi_use_occlusion = true`
against leaks); bounded interiors with **VoxelGI**; shipped static levels with
**LightmapGI** (needs UV2: import `meshes/light_baking = Static Lightmaps`,
texel size 0.2 m default). Indoors, set `interior = true` on ReflectionProbes
and LightmapGI so they stop pulling in sky light.

## Environment properties that matter

| Area | Properties |
|---|---|
| Tonemap | `tonemap_mode` 0 Linear · 1 Reinhard · 2 Filmic · 3 ACES · **4 AgX**; `tonemap_exposure`; `tonemap_agx_white` 16.29, `tonemap_agx_contrast` 1.25 (match Blender AgX); `tonemap_white` ignored by AgX |
| Ambient | `ambient_light_source` 0 BG · 1 Disabled · 2 Color · **3 Sky**; `ambient_light_sky_contribution`; `reflected_light_source` 2 Sky |
| Background | `background_mode` 2 Sky; `background_energy_multiplier`; `background_intensity` (nits, physical units) |
| Sky | PhysicalSkyMaterial: `rayleigh_*`, `mie_*`, `turbidity`, `sun_disk_scale`, `ground_color`, `energy_multiplier`; follows the DirectionalLight. ProceduralSkyMaterial: `sky_top_color`, `sky_horizon_color`, `ground_*`, `sky_energy_multiplier`. PanoramaSkyMaterial: `panorama` (.hdr/.exr), `energy_multiplier` |
| GI | `sdfgi_enabled`, `sdfgi_use_occlusion`, `sdfgi_bounce_feedback`, `sdfgi_energy`, `sdfgi_min_cell_size` 0.2 |
| AO | `ssao_enabled`, `ssao_radius` 1, `ssao_intensity` 2, `ssao_light_affect` (keep ~0) |
| SSIL/SSR | `ssil_enabled`, `ssil_radius` 5; `ssr_enabled`, `ssr_max_steps` |
| Fog | `fog_enabled`, `fog_mode` 0 Exponential, `fog_density`, `fog_aerial_perspective`, `fog_sky_affect`, `fog_sun_scatter`, `fog_height*` |
| Volumetric | `volumetric_fog_enabled`, `_density`, `_albedo`, `_anisotropy`, `_length`, `_temporal_reprojection_*`; per light `light_volumetric_fog_energy`; local `FogVolume` |
| Glow | `glow_enabled`, `glow_intensity`, `glow_hdr_threshold` (≥ 1 so only highlights bloom), `glow_blend_mode` (Screen default since 4.6) |
| Grade | `adjustment_*`, `adjustment_color_correction` (1D gradient or 3D LUT) |

## Lights

- `Light3D`: `light_color`, `light_energy`, `light_indirect_energy`, `light_specular`,
  `shadow_enabled`, `shadow_bias` (0.1), `shadow_normal_bias` (2.0), `shadow_blur`,
  `light_temperature` (1000-15000 K), `shadow_caster_mask`.
- Soft shadows (PCSS): `light_angular_distance` on the sun (the real sun is
  ~0.5°), `light_size` on omni/spot/area. Costs performance; use on few lights.
- DirectionalLight3D: `directional_shadow_mode` (PSSM 4 default),
  `directional_shadow_max_distance` (100; lower = sharper), `_split_1..3`,
  `_blend_splits`, `_pancake_size`, `sky_mode`.
- Omni/Spot: `omni_range`, `omni_attenuation` (1 ≈ physical), `spot_angle`,
  `spot_attenuation`.
- **AreaLight3D (new in 4.7)**: `area_size`, `area_range`, `area_attenuation`
  (2.0 = inverse square), `area_normalize_energy`, `area_texture`. Emits along
  −Z. One visible area light adds cost to every object in Forward+.
- Project: `rendering/lights_and_shadows/directional_shadow/size` 4096,
  `positional_shadow/atlas_size`, `soft_shadow_filter_quality`.

### Shadow artifacts

| Artifact | Cause | Fix |
|---|---|---|
| Acne (striped self-shadow) | bias too low | raise `shadow_normal_bias` first |
| Peter-panning (floating objects) | bias too high | lower `shadow_bias`; thicker casters |
| Leaks at wall/floor joins | thin geometry, GI cells | thicker walls; SDFGI occlusion; VoxelGI higher `subdiv`; `interior` on probes/lightmaps |
| Blurry or blocky sun shadows | shadow map spread thin | lower `directional_shadow_max_distance`; 4096 map |
| Seams between cascades | split boundaries | `directional_shadow_blend_splits`; inspect with the `pssm` view |
| Dither noise in soft shadows | filter sampling | TAA or FSR2 |

## Traps (verified)

1. **`ambient_light_energy` is ignored for sky ambient.** It only scales the
   colour share, which is zero while `ambient_light_sky_contribution` = 1.
   Measured: 0.0, 0.5 and 1.0 render identically. Scale the sky instead.
2. **`light_temperature` needs physical light units.** Otherwise the setter
   returns early and the inspector hides it.
3. **Headless renders nothing; minimized renders nothing.** Use a window
   off-screen (`--position -20000,-20000`), as capture does.
4. **The unshaded debug view is still exposed and tonemapped**, so with high
   `tonemap_exposure` every albedo looks white.
5. **Frame-wide lit/shade spread depends on composition**, not on lighting.
   Measure key/fill on a probe.
6. **LightmapGI has no script bake** in 4.7. VoxelGI does.
7. **CameraAttributesPhysical on a Camera3D overrides its FOV and near/far.** On
   the WorldEnvironment it only provides exposure.
8. Movie Maker (`--write-movie`) output size comes from the project's window
   size settings, not `--resolution`.

## Debug views (capture `--views`)

`lit`, `unshaded` (albedo), `lighting` (light only), `normal`, `overdraw`,
`ssao`, `ssil`, `pssm` (cascade splits), `sdfgi`, `sdfgi_probes`, `gi_buffer`,
`voxel_gi_lighting`, `luminance` (auto-exposure only).

Diagnostic sweep for "something looks off": `lit,unshaded,lighting,normal`.

- `unshaded` wrong → material problem.
- `lighting` wrong → light problem.
- `normal` shows faceting or inverted patches → geometry/normal-map problem.

## glTF import mapping (Godot 4.7 gltf_document.cpp)

- Every material becomes **StandardMaterial3D**.
- metallicRoughness texture → both slots; metallic reads B, roughness G.
- occlusion → AO from R; `FLAG_AO_ON_UV2` if on another UV set.
- normalTexture.scale → `normal_scale`.
- emissive texture → `EMISSION_OP_MULTIPLY`; `emissiveStrength` → `emission_energy_multiplier`.
- alpha BLEND → alpha + depth pre-pass; MASK → scissor.
- doubleSided → `CULL_DISABLED`.
- **Read:** KHR_materials_emissive_strength, _unlit, _pbrSpecularGlossiness,
  KHR_texture_transform, KHR_lights_punctual (intensity → `light_energy` raw,
  no unit conversion).
- **Dropped:** clearcoat, sheen, specular, transmission, ior, volume,
  anisotropy, iridescence, dispersion.
