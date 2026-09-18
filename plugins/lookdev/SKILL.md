---
name: lookdev
description: Light and shade Godot 4.7 scenes so they look real, with Blender assets that survive the trip. Renders a scene off-screen and measures it (exposure, clipping, key-to-fill ratio on an 18% grey probe, albedo range, colour cast), lints scenes and Blender materials for the mistakes that make 3D look like CG, applies calibrated lighting presets (clear midday, golden hour, overcast, interior daylight, night), and bakes procedural Blender materials into textures glTF can carry. Use when lighting a scene, choosing sun/sky/exposure/GI/fog settings, judging whether a render looks realistic, fixing flat, washed-out, dark or "plasticky" results, comparing lighting variants, preparing Blender materials for export to Godot, or when an imported asset looks different in Godot than in Blender.
---

# lookdev

Lighting is judged with eyes, and you can't trust yours on a single screenshot.
So this skill splits the work: **tools measure, you look, and the numbers keep
the looking honest.** Every change gets captured and measured; no lighting
change is "done" on the strength of a property edit.

Paths below are relative to this skill's directory (`<skill>`). The runner
needs only Node; it finds Godot via `--godot`, `LOOKDEV_GODOT`, `GODOT_PATH`, or
the project's `.mcp.json`.

## The tools

```bash
node <skill>/bin/lookdev.mjs lint    --project . --scene res://level.tscn
node <skill>/bin/lookdev.mjs capture --project . --scene res://level.tscn --probes --kind day
node <skill>/bin/lookdev.mjs presets
node <skill>/bin/lookdev.mjs preset  --project . --scene res://level.tscn --preset golden_hour
node <skill>/bin/lookdev.mjs compare --project . --a <capture dir> --b <capture dir>
```

| Command | What it gives you |
|---|---|
| `lint` | Headless static check of environment, lights, materials, project AA/shadow settings. Each finding has the property to change. |
| `capture` | Off-screen render → `<shot>_<view>.png`, `sheet.png` (all views in one image), `stats.json`, findings. ~5 s. |
| `preset` | Writes sun, sky, environment and exposure for a recipe into a **copy** of the scene (temp dir) unless `--out`/`--in-place`. |
| `compare` | `<name>_ab.png` and `_ba.png` side by side, plus stat deltas. |

Capture options worth knowing:

- `--views lit,unshaded,lighting` (default). Also `normal ssao ssil pssm sdfgi gi_buffer luminance`.
- `--probes` adds an 18% grey ball and a chrome ball, and measures **key/fill** from the side. Always use it when judging lighting.
- `--kind day|golden|overcast|interior|night` picks the thresholds.
- `--camera NodePath`, or `--eye x,y,z --target x,y,z --fov 50`. Multiple shots go in a spec file: `--spec shots.json` with `{"shots":[{"name":"a","eye":[..],"target":[..]}, ...]}`, per-shot `probe_at` allowed.
- `--set "target:property=value"` tries a change **without editing the scene**. Targets: `@env`, `@sun`, `@camera`, `@world`, or a node path; nested with colons: `--set "@env:sky:sky_material:energy_multiplier=2"`. Values are JSON or Godot literals (`Color(1,0.9,0.8,1)`). Repeatable. This is how you try candidates.

Blender side (inside Blender through the `blender` MCP server):

```python
import sys
P = r"<skill>/blender"
if P not in sys.path: sys.path.insert(0, P)
import lookdev_blender; lookdev_blender.reload_all()
from lookdev_blender import material_lint, bake, export, reference, detail
print(material_lint.summarize(material_lint.lint()))          # selected meshes, or all
print(bake.summarize(bake.bake_object("Crate", r"C:/proj/assets/crate_tex", size=2048)))
print(export.summarize(export.export_gltf(r"C:/proj/assets/crate.glb", ["Crate_baked"])))
# detail that is geometry on a high copy (humanform muscle definition) -> normal map on the game mesh
print(detail.summarize(detail.bake_normal_from_high("Dante_body", "Dante_high", r"C:/proj/assets/dante_tex",
                                                    size=2048, material="Dante_skin")))
```

`detail.bake_normal_from_high` keeps the low mesh's materials and adds a tangent Normal Map in front of the
named material's Principled Normal (so glTF writes normalTexture); `material=` bakes only that material's
faces (joined eyes overlap the skin's UVs). A re-bake takes over the earlier image (its users are remapped)
and re-points the nodes, and the scene's engine and Cycles device, samples and denoising are restored.

- `method="auto"` picks **matched** when the high mesh is the low mesh's own topology (humanform's
  `delta.high_copy`): no rays - each corner gets the high vertex normal in the low corner's MikkTSpace frame,
  and an EMIT bake fills the map. Otherwise **rays** (selected-to-active), where `clean=True` also bakes the low
  mesh against a copy of itself and flattens texels that bend there (nails, eyelids, ears: 166 degrees without
  it). On Dante the ray bake still left hot spots at the armpit and hip UV borders and hard-edged flattened
  patches that rendered as dark streaks on the arms and flanks; the matched bake has neither.
- **Judged over the faces being baked, i.e. `material`'s.** A finished character's game mesh is the body with
  its eyes joined in (character-pipeline's bake stage) while the high copy is the body alone, so whole-mesh
  counts differ - 14402 faces against 13378 - and `auto` used to drop to rays on the exact case the matched
  bake was written for, with nothing but the returned `method` to say so. `detail.matched(low, high,
  material)` and `detail.reason(...)` compare that material's faces instead; on Dante's joined mesh the
  matched map then comes out identical to the body-only one, while the ray bake of the same mesh has to
  flatten 8373 texels against 24. A fallback now puts its reason in `warnings`, and `method="matched"`
  returns an error naming what does not line up rather than baking something else.
- `max_deg=60`: texels bent more are flattened (7 of 262k on the fixture's 512 px map).
- Earlier bakes' normal maps are unlinked from the materials during the bake: the high copy shares the low
  mesh's material, and a wired map was being baked in again (a re-bake came out flat).
- `stats` says how much of the map bends (>1 and >5 degrees), so a bake that found nothing shows.

## Workflow: fixed stages, each with a gate

Work in this order and change only that stage's properties while in it. A
lighting fix can't rescue a bad albedo, and exposure can't fix a flat key/fill
ratio: tuning several at once is how scenes drift. Research on render-critique
agents found decomposing the task this way matters more than having more tools.

**0. Baseline.** `lint`, then `capture --probes --kind <kind>`. Read `sheet.png`.
Write down the stage you are starting from and what looks wrong in plain words.

**1. Materials (albedo view).** Gate: no `ALBEDO_*`, `METAL_*`, `METALLIC_PARTIAL`
lint findings you have not deliberately accepted; `unshaded` view reads as
plausible paint, not as lit. Metals show **black** in the unshaded view; that's
expected. Assets from Blender: `material_lint` before export, `bake` anything
flagged `BAKE_REQUIRED`, and remember Godot ignores clearcoat, sheen,
transmission and IOR from glTF. Rebuild those on the Godot material.
→ `references/pbr-values.md`, `references/blender-handoff.md`

**2. Key light and sky (the preset stage).** Pick the closest recipe and apply
it to a copy, or set sun angle, colour and sky yourself. Gate on the **probe**:
`key/fill` in range for the kind (clear day ~2-3 stops, overcast < 1.3, golden
~2-3.5, night ~2-6). Too few stops → the sky/ambient is drowning the key: lower
the **sky's energy**. Too many → shadows are starved: more sky, GI, or a fill.
→ `references/recipes.md`, `references/light-and-exposure.md`

**3. Exposure.** Only now. Gate: `KEY_EXPOSURE` (white-in-key near 1.0 linear for
day/golden/overcast), median luma in range, clipped and crushed under limits.
Move `tonemap_exposure` or camera attributes, **never** light energies, to fix
brightness. Tonemapper is AgX (4) unless there's a reason.

**4. Indirect light, contact and reflections.** SDFGI (open/large) / VoxelGI
(bounded interior, bake at runtime) / LightmapGI (static; editor-only bake),
SSAO with `ssao_light_affect` 0, ReflectionProbes with `interior` indoors. Gate:
objects sit on surfaces (look at contacts in `lit`), no light leaks in the
`lighting` view, key/fill still in range (GI adds fill; re-check stage 2).
→ `references/godot-lighting.md`

**5. Atmosphere and finish.** Fog/aerial perspective for depth, glow only above
white (`glow_hdr_threshold` ≥ 1), no saturation boosts. Gate: nothing new in
lint; distant objects lose contrast toward the sky colour; highlights bloom,
midtones don't.

At every stage: **capture → name the problem → one change → capture → verify
the change did what you said**. If a stage's gate won't pass, say which and why,
don't hide it in the next stage.

## Judging images

Read `references/judging.md` before choosing between variants. The short form:

- **Compare, don't score.** Asking "is this 7/10?" is unreliable. Asking "which
  of these two is more realistic, and why?" is much better, provided you judge
  `_ab.png` and `_ba.png` separately and keep a verdict only when both orders
  agree. Position bias is real.
- **Keep the current best in every comparison.** A round that doesn't beat it
  changes nothing.
- **Measurements first, eyes second.** If stats say clipped 15% and you think
  it looks fine, look again at the highlights.
- **Say what you see, in the image's terms:** "the shadow side of the grey ball
  is nearly as bright as the lit side", not "lighting could be improved".

## Material presets: hair

`presets/materials.json` holds material presets: what a Blender material is built from, and what Godot has
to add back after glTF drops it. The first is **hair**, which humanform's hair layer uses.

```python
from lookdev_blender import hair
mat, rep = hair.material("Belle_hair", colour=(0.17, 0.10, 0.06), uv_map="UVMap")   # sRGB colour
```

```gdscript
var scene = load("res://assets/belle/belle.glb").instantiate()
LookdevMaterials.apply(scene)    # godot/addons/lookdev/lookdev_materials.gd - copy the addon into the project
```

Strand texture with a root-to-tip gradient and alpha that fades toward the roots and thins at the tips
(glTF MASK), a strand normal map, Principled anisotropy in Blender, and a `lookdev` custom property that glTF
carries as material extras and `LookdevMaterials.apply` turns into StandardMaterial3D anisotropy, backlight,
rim, specular and a depth pre-pass blend (so the hairline fades instead of cutting), and tangents from U on
the hair's surfaces - per face, then averaged mod 180 degrees where faces meet, so the anisotropic highlight
neither glints where a shell's UV frame turns nor facets into dark polygons where it turns fast, with no need
for the exporter to write tangents. See `references/hair.md`.

**Skin** (humanform's `look.skin`, realistic by default) reaches Godot the same way: the procedural skin is
baked by `bake.bake_material(obj, material, out_dir, size)` - one material rebuilt in place from albedo, ORM
and normal maps, keeping its name, custom properties and subsurface inputs, with an `adjust` hook that sees the
covered texels (humanform holds the albedo's mean to the brief's tone with it). Its `lookdev` extras have preset
`skin`: `LookdevMaterials.apply` sets `subsurf_scatter` (skin mode, transmittance with a 1 cm depth - at 8 cm a
whole palm glowed orange under a sun behind it; judge transmittance with a key light behind thin parts, overcast
hides it) and a tiling pore detail
normal (`lookdev.detail`, seeded cellular noise on UV2 = humanform's `hf_detail`). `lint` warns
`SKIN_PLASTIC` on a skin with a flat albedo, one roughness, no normal/pore detail or no subsurface.

## Godot facts that bite (all verified in 4.7.2)

- **`ambient_light_energy` does nothing for sky ambient** while
  `ambient_light_sky_contribution` is 1 (the default). Scale the sky's energy.
- **`light_temperature` is ignored unless physical light units are on.** Presets
  convert Kelvin to `light_color` in that case.
- **`--headless` renders nothing** (dummy renderer) and **a minimized window
  renders nothing** on Windows. Capture runs a real window off-screen.
- **LightmapGI cannot be baked from a script in 4.7**; only the editor button.
  VoxelGI can: `$VoxelGI.bake()` at runtime.
- **The unshaded debug view is still exposed and tonemapped.** Capture
  neutralises that for albedo stats; if you look at a raw editor unshaded view,
  it isn't.
- **glTF import:** every material becomes StandardMaterial3D; ORM image in
  metallic (B) and roughness (G), AO from R. Clearcoat, sheen, transmission,
  specular, IOR, volume, anisotropy are **dropped**. Material custom properties
  are kept, as the material's `extras` metadata - which is how material presets
  put them back.
- **Physical light units:** Godot's exposure lands about one stop darker than
  Sunny-16 arithmetic; the presets' physical values already account for it.

## Don't

- Don't change light energies to fix exposure.
- Don't judge lighting from a frame without the probe: frame-wide contrast
  depends on composition (a frame full of sunlit floor reads "flat" whatever
  the lights do).
- Don't apply a preset `--in-place` without capturing the copy first.
- Don't report a lighting change as done without a capture after it.
- Don't chase a threshold against a deliberate look (noir, fog, stylised);
  choose the closest `--kind` and say which numbers you're overriding and why.
