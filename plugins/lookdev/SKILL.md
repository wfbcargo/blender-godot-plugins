---
name: lookdev
description: Light and shade Godot 4.7 scenes so they look real, with Blender assets that survive the trip. Renders a scene off-screen and measures it (exposure, clipping, key-to-fill ratio on an 18% grey probe, albedo range, colour cast), lints scenes and Blender materials for the mistakes that make 3D look like CG, applies calibrated lighting presets (clear midday, golden hour, overcast, interior daylight, night) offline or at runtime, renders a labelled close-up sheet of a character in Godot (face, three-quarter, eyes, side and back of the head, hands, feet, bust, full body, cameras aimed from its posed bones), beside its Blender close-up of the same view, probes a glb's albedo tone, and bakes procedural Blender materials into textures glTF can carry. Use when lighting a scene, choosing sun/sky/exposure/GI/fog settings, judging whether a render or a character looks realistic, looking at a character up close in Godot, fixing flat, washed-out, dark or "plasticky" results, comparing lighting variants, preparing Blender materials for export to Godot, or when an imported asset looks different in Godot than in Blender.
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
node <skill>/bin/lookdev.mjs close-shot --project . --glb res://assets/x/x.glb --distance 1 --presets clear_midday,overcast
node <skill>/bin/lookdev.mjs tone    --project . --glb res://assets/x/x.glb [--material skin] [--expect 0.86,0.68,0.57]
node <skill>/bin/lookdev.mjs selftest --project .
node <skill>/bin/lookdev.mjs stipple <tile.png> --region x,y,w,h      # no Godot, < 2 s
node <skill>/bin/lookdev.mjs edges --project . --glb res://x.glb      # transmittance lines on the hands, ~40 s
node <skill>/bin/lookdev.mjs grain <face tile.png> --region cheek --min 0.40 --max-finest 2.0   # no Godot
```

| Command | What it gives you |
|---|---|
| `lint` | Headless static check of environment, lights, materials, project AA/shadow settings. Each finding has the property to change. |
| `capture` | Off-screen render → `<shot>_<view>.png`, `sheet.png` (all views in one image), `stats.json`, findings. ~5 s. |
| `preset` | Writes sun, sky, environment and exposure for a recipe into a **copy** of the scene (temp dir) unless `--out`/`--in-place`. Refuses a recipe whose `needs` the stage does not meet (interior_daylight on an open stage); `--stage`, `--force`. |
| `compare` | `<name>_ab.png` and `_ba.png` side by side, plus stat deltas. |
| `close-shot` | **Judge a character in Godot with one command.** A labelled sheet of close-ups of one glb, one row per view, one column per preset, optionally beside its Blender close set (`--pair-blender`), ~10-15 s. Details below. |
| `tone` | Mean albedo per material over the texels its UVs cover (padding ignored), linear and sRGB; `ok` is 0.01-0.9 linear luminance, so a black albedo fails. Headless, < 1 s. |
| `stipple` | **A dithered lattice in shadowed skin**, the stipple Godot's default soft-low shadow filter drew on necks and fingers under a sun. Give it a close-shot tile and a region on the skin (pixels, or fractions when every number is at most 1). It keeps shadowed, smooth, warm pixels at least 3 px from anything else, high-passes luma, and in 96 px windows looks for a detail that repeats along two directions (correlation at a lag less that at half the lag, the weaker of the best lag and the best one 30 deg away from it); `lattice` >= 0.25 at >= 1.2% contrast is a stipple, exit 1. Hair, lashes and aliased silhouettes also repeat, so aim the region at skin. |
| `edges` | **Lines a skin's transmittance draws.** Renders close-shot tiles (default `hands`, clear_midday and overcast) twice - as the glb asks and with `subsurf_scatter_transmittance_enabled=false` - so the red channel's difference is the light transmittance added. Over each tile's subject it reports `glow` (mean added red), and `lines`: pixels where the added red is at least 8 and more than 0.5x the red the skin has there without it - a mark that outshines the skin it sits on, which a soft glow never does; over 0.1 per thousand is EDGE_LINES, exit 1. `--material-set` probes a setting without rebuilding; `--min-glow v --glow-views head_back` fails NO_GLOW where transmittance should still show; `--on/--off <png>` measures a pair already rendered. Under a low sun behind the part (`--sun-elevation 15 --sun-azimuth ...`) a real glow outshines the shadowed skin too, so judge those tiles by eye. |
| `stripes` | **Bands on a smooth surface** - shadow acne on the stage floor under a grazing sun. Give it a tile, a region and (for a close-shot tile) its `_mask.png` with `--band <label band px>` so the figure is left out. High-passed luma of smooth pixels (away from edges such as the figure's shadow), in 96 px windows: a detail that repeats along one direction (correlation at a lag less that at half the lag); `stripe` >= 0.3 at >= 1.2% contrast is banding, exit 1. close-shot runs it on every `full` tile's floor (FLOOR_STRIPES), beside SKIN_PAST_WHITE: more than 1% of the figure brighter than AgX's display of scene-linear 1.0 (luma 0.796), i.e. past a diffuse white in the key. Both are in `close.json` `look`, measured, never clamped. `--presets-file` renders another presets.json's recipes (the controls use lookdev 0.7.0's golden_hour). |
| `grain` | **How much fine texture a skin patch carries** - the pores and micro relief that make skin read as skin at 1 m, or the pixel noise an aliasing detail map draws. Band-passes luma (3x3 mean less 7x7 mean: features 3-7 px) over warm skin pixels and reports its RMS as % of the patch's luma (`grain`), and the pixel-to-pixel part apart (`finest`: dither, salt-and-pepper). `--region cheek` is a fixed patch of close-shot's face tile at 1 m; `--min` fails a patch smoother than that (SMOOTH), `--max-finest` a noisier one (NOISY), exit 1. The Step 2 skin check is `--min 0.40 --max-finest 2.0` on the cheek in clear_midday and overcast: main's pores measured 0.16-0.38 %, the same as no detail at all (they mip to a flat normal past about 0.5 m); lookdev 0.9.0's two-octave detail 0.47-0.94 %. |
| `selftest` | Runs the controls: every check above fails on a case built to fail (0-material lint and capture, unwritable `--out`, black albedo, no skeleton, a missing bone, interior_daylight on an open stage, the Step 0 neck and fingers for `stipple`, study_woman's fingers with humanform 0.12's transmittance for `edges`, main's and detail-off cheeks (too smooth) and mip-less pores (noise) for `grain`) and passes its positive twin; close-shot's tile checks each fail on a camera moved off its subject (EMPTY_TILE, OFF_TARGET), `--min-subject` (SUBJECT_SMALL) and `--label inside` (LABEL_OVER_HEAD), and `--pair-blender` on a small fake set pairs and names the unpaired views; the full tile passes under the shipped golden_hour, fails FLOOR_STRIPES under lookdev 0.7.0's and SKIN_PAST_WHITE under that recipe two stops over. About 50 s. Run it after changing any tool; `regress.py --godot` runs it. |

Exit codes: `lint` exits 1 on any error finding - including `NO_MATERIALS`, a scene with nothing to check
(lint does not run scripts, so a stage built in `_ready` is invisible to it; use `capture` or `close-shot`,
which run the scene). `capture` exits 1 on a scene with 0 materials after it ran or an `--out` it cannot
write. `close-shot` exits 1 on any failed tile; `tone` exits 1 when a material is not ok.

### close-shot: a character's look set

```bash
node <skill>/bin/lookdev.mjs close-shot --project . --glb res://assets/figure_study/study_woman/study_woman.glb \
    --presets clear_midday,overcast --views head,hands,full \
    --pair-blender assets/figure_study/study_woman/review/study_woman/close
# default views: face,face_3q,eyes,head_side,head_back,hands,feet,bust,full at --distance 1 (full at 4)
```

- Loads the glb (the project's import for a `res://` path, else `GLTFDocument`), runs `LookdevMaterials.apply`,
  attaches the strands its `.moves.json` lists (follow-through addon), equips `--garments a.glb,b.glb`
  (wardrobe addon), and poses `--clip` (a clip name or a manifest role: Idle, Run...) at `--time` s.
  Default: the manifest's Idle at 0.
- Renders on an open stage like figure_study's: an 18% grey floor and a curved backdrop, lit by the
  addon's runtime applier. interior_daylight is refused there.
- **Cameras are aimed from the posed frame's bones, never height fractions.** Views: `face`, `eyes` (from
  the eyeballs: the sclera surface carried through the head bone's skin bind), `face_3q` (from the head's
  front-left), `head_side` (the whole head from its left: ear, hairline, nape) and `head_back` (from behind:
  the nape, a tail or bun) - `head` = these five, aimed with rig-anything `closeups._aim`'s formulas so they
  line up with the Blender set - `hand_palm.L/.R`, `hand_back.L/.R` (palm centre and palm normal from the
  hand and finger bones; `hands` = all four), `feet`, `bust`, `crotch`, `full`, and `bone:<name>`.
  `view@metres` overrides a distance; `full` takes `--full-distance` (4 m).
- **Distance sets the perspective, the lens sets the framing:** each tile's field of view is chosen so the
  subject fills it at the stated distance. Palm cameras sit toward the front and clip whatever is nearer
  than the hand (the thigh the palm faces).
- Each tile carries its label in a band **above** the picture (as the Blender set's), so it never covers the
  figure: "Godot", view, distance, preset, fov, clip @ time. `--label inside` puts it back over the top of the
  picture - the old layout, kept only as the control for LABEL_OVER_HEAD.
- **The sheet:** one row per view, one column per preset, a header over each column and a Blender/Godot tag
  in each cell. **`--pair-blender <close dir>`** (a Blender close set: `<export dir>/review/<id>/close/`, with
  its `close.json`) adds the Blender tile of each view in a first column. A paired view with no `@distance`
  (and no `--distance`) is shot at the Blender tile's distance, so the two share a perspective and, with the
  same framing formulas, a frame width. The run prints which views are paired, which have no Blender twin
  (`full`, `bone:<name>`: an empty cell says so) and which Blender tiles have no Godot view (knees,
  foot_inner.L/outer.L, under_bust); `close.json` `pair_blender` has the same.
- Every tile is checked from its own pixels and the posed bones, with the free values in `close.json`:
  `figure_coverage` (the figure's share of the tile, from two flat-colour unshaded renders) - EMPTY_TILE
  under `--min-coverage` (0.03); `subject_coverage` (only geometry within a slab round the target's depth,
  so the thigh behind a hand does not count as the hand) - SUBJECT_SMALL under `--min-subject` (0.08, body
  views); `subject_uv`/`subject_off` (where the view's own subject points land - the head, both eyes,
  wrist/knuckle/tip - and how far their centroid is from the centre, 0.5 = the edge) - OFF_TARGET past 0.3,
  behind the camera, or (body views) not on the figure; for `full`, SUBJECT_CUT when the crown or a foot is
  outside the picture and LABEL_OVER_HEAD when the head's projected box (`head_box_px`) meets the band
  (`band_px`). The checks are centroid-only: a camera that cuts the fingertips with the centroid inside
  passes. `--aim-offset view=x,y,z[;...]` moves a camera and not its subject (the controls). A missing bone,
  no skeleton or an unknown clip fail before anything renders. Masks are written beside each tile
  (`*_mask.png`, `*_subject.png`).
- Writes `<out>/sheet.png`, one PNG per tile and `close.json` (eye, target, anchors, subject points, fov,
  coverages, the pairing).
  Uses the project's copy of the addon (a `class_name` script cannot load twice) and warns when it differs
  from the plugin's.

### Runtime presets in a game

```gdscript
const LookdevPresets := preload("res://addons/lookdev/lookdev_presets.gd")   # no class_name, on purpose
var rep := LookdevPresets.apply("overcast", $WorldEnvironment, $Sun, {"stage": "open"})
if not rep["ok"]: push_warning(rep["problems"])     # e.g. interior_daylight on an open stage
```

`presets.json` ships in the addon beside it. Options: `fresh` (a new Environment, default), `stage`
(`open`/`interior`), `force`, `elevation`, `azimuth`, `energy_scale`. `sky_openness(root, at)` measures a
stage (share of rays up that reach the sky). Copy the whole `godot/addons/lookdev/` folder into the project.

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

Read `references/judging.md` before choosing between variants. To judge a character's look (a round's
done-when, a look critic), pick the questions from `references/critic-look.md`: each names the Godot
close-shot view, Blender close-set tile or number (`tone`, `capture`) that answers it. The short form:

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
# judge it:  node <skill>/bin/lookdev.mjs close-shot --project . --glb res://assets/belle/belle.glb
```

Strand texture with a root-to-tip gradient and alpha that fades toward the roots and thins at the tips
(glTF MASK), a strand normal map, Principled anisotropy in Blender, and a `lookdev` custom property that glTF
carries as material extras and `LookdevMaterials.apply` turns into StandardMaterial3D anisotropy, backlight,
rim, specular and a depth pre-pass blend (so the hairline fades instead of cutting), its alpha extras (the
albedo's mipmaps rebuilt so every level keeps level 0's coverage over 0.5, and alpha ramped over 0.5 +- 0.25:
strands at the hairline, not a smeared film), and tangents from U on
the hair's surfaces - per face, then averaged mod 180 degrees where faces meet, so the anisotropic highlight
neither glints where a shell's UV frame turns nor facets into dark polygons where it turns fast, with no need
for the exporter to write tangents. `strand_texture` has a `card` mode (strands with gaps all the way along,
no opaque middle) and `hair.material(pixels=(colour, normal))` takes a caller's own hairs (humanform's brow and
lash cards), so nobody overwrites the images it made. See `references/hair.md`.

**Lighting presets set the directional soft-shadow filter to high** (`sun.soft_shadow_filter_quality`, applied
project-wide through RenderingServer by `LookdevPresets.apply`; `preset` warns that a scene cannot carry it). At
Godot's default, soft low, a 0.5 deg sun drew a regular lattice of lit dots over shadowed skin (a neck under the
chin, the sides of fingers); the transmittance, pores, subsurface and the hair's shadow were each ruled out.

**Skin** (humanform's `look.skin`, realistic by default) reaches Godot the same way: the procedural skin is
baked by `bake.bake_material(obj, material, out_dir, size)` - one material rebuilt in place from albedo, ORM
and normal maps, keeping its name, custom properties and subsurface inputs, with an `adjust` hook that sees the
covered texels (humanform holds the albedo's mean to the brief's tone with it). Its `lookdev` extras have preset
`skin`: `LookdevMaterials.apply` sets `subsurf_scatter` (skin mode, transmittance at strength 0.2 with a 3 cm
depth. Godot reads the thickness from the sun's shadow map, whose texels are millimetres wide at 1 m, and skin
mode's profile is pure red from 0.1 depth on whatever the colour's RGB: at full strength and 1 cm the noise drew
orange-red lines at finger edges and the thumb web - `edges` measures them; at 8 cm a whole palm glowed. Judge
transmittance with a key light behind thin parts (close-shot `--sun-azimuth`), overcast hides it) and a tiling pore detail
normal (`lookdev.detail`, seeded cellular noise on UV2 = humanform's `hf_detail`). Pores alone (0.3 mm on a face)
are under a pixel at 1 m and box-filtered mips average them to a flat normal, so since 0.9.0 a spec with
`coarse_cells` adds a coarser octave - larger pits of random depth and shallow furrows, 2-4 mm - in the normal and
as a detail-albedo cavity (the only way the grain shows in diffuse light, not just in highlights), with its mips
faded to flat where a cell is under 3 texels (no shimmer at full body), `keep_base` (the baked normal map gets
back the share Godot's detail mix takes, and `albedo_color` the cavity's mean darkening) and `shared` (one texture
for every body: 1.5 MB, about 0.15 s once). `LookdevMaterials.last_detail` records each spec's cost. `lint` warns
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
- Don't judge a character from a Blender render or a script of your own: `close-shot` it in Godot, at a
  stated distance, in clear_midday and overcast (lookdev's materials only exist in Godot).
- Don't write your own preset port in a game: preload `addons/lookdev/lookdev_presets.gd`.
- Don't chase a threshold against a deliberate look (noir, fog, stylised);
  choose the closest `--kind` and say which numbers you're overriding and why.
