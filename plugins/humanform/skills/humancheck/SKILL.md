---
name: humancheck
description: Measure and judge an adult human body in Blender - proportions against a realistic or stylized preset (joint heights, head count, crotch, limb segments, hand and foot length, shoulder and hip width, waist-to-hip), features (separate fingers, a face with relief, legs parted), rig joints inside the limbs, pose, and mesh health (quads, UVs, manifold, symmetry) - then render a fixed orthographic contact sheet (clay, normals, silhouette from four sides, with target and measured landmark lines, plus face, hand and foot close-ups) and hand both to a critic subagent that asks yes/no questions and compares against the previous version. Use when checking whether a human character, body, figure or base mesh looks right or is well proportioned, before and after changing one, when a body looks off and the reason is unclear, when comparing two versions, or as the gate between humanform's build layers.
---

# humancheck

Numbers first, eyes second. Research on agents building in Blender is consistent: geometric
measurements improve every model's results, screenshots judged by the builder are the weakest
signal, and a separate critic with explicit questions and a before/after comparison beats a
self-assessment. Background: `${CLAUDE_PLUGIN_ROOT}/references/proportions.md` (what each
number means and where the targets come from) and `${CLAUDE_PLUGIN_ROOT}/references/critic-checklist.md`.

Works on any skinned or unskinned human mesh facing -Y with its left at +X. Landmarks come from
the rig by bone name (rig-anything / Rigify basic_human, MPFB `game_engine` and `default`,
Mixamo), or from MPFB's `joint-*` vertex groups when there is no rig.

## Run it

**In the open Blender session** (the `blender` MCP server):

```python
import sys, importlib
P = r"${CLAUDE_PLUGIN_ROOT}/scripts"
if P not in sys.path:
    sys.path.insert(0, P)
import humanform
importlib.reload(humanform)
humanform.reload_all()
from humanform import measure, views

rep = measure.run("Nora", preset="realistic", sex="female", out_dir=r"C:/scratch/hc/nora_v3")  # build="curvy" etc. if a sheet has one
print(measure.summarize(rep))
views.contact_sheet("Nora", r"C:/scratch/hc/nora_v3", preset="realistic", sex="female", report=rep)
```

Measuring takes about 1 s and the sheets about 3 s on a 30k-vertex body. Keep them as two MCP calls.

**Without touching the session** (a saved `.blend`, or a fresh MPFB body):

```bash
blender -b C:/Users/pauli/Code/Blender/wardrobe_person.blend --factory-startup \
  --python ${CLAUDE_PLUGIN_ROOT}/scripts/humancheck_cli.py -- body=Nora sex=female out=C:/scratch/hc/nora views=1
blender -b --factory-startup --python ${CLAUDE_PLUGIN_ROOT}/scripts/humancheck_cli.py -- mpfb=female out=C:/scratch/hc/mpfb views=1
```

`preset=realistic|stylized`, `sex=female|male` (required for `realistic`, whose targets are per sex),
`include=Hair,Eyes` (auto-includes the rig's meshes named hair/eye/brow/lash), `verbose=1`
prints every raw measurement.

## Read the output

```
Belle: 1.782 m, preset realistic, sex female - 10 fail, 9 warn, 13 pass
  FAIL L1 crotch 0.353 H, target 0.470 +/- 0.020 - 20.8 cm too low
  FAIL L7 hip joints 27.5 cm above the crotch (0.154 H), expected 0.015-0.08 H - the hip joints are not inside the pelvis
  FAIL L4 hand.L: 1 separate finger sections - the hand is a mitten or a stump
  WARN L2 arms rest 63 deg below horizontal, expected 35-55
```

Each finding carries the ladder layer it belongs to (L1 proportions, L2 scaffold/pose/mesh, L4
parts, L5 surface, L7 rig). `warn` is outside the tolerance, `fail` outside twice it. **Fix the
lowest failing layer first**: a crotch 20 cm low makes every garment, jiggle zone and walk wrong,
and no amount of face detail changes that. `humancheck.json` holds the findings and every raw
measurement.

Then **look**: open `body.png` and `closeups.png`. Rows clay / normals / silhouette; columns
front, front_left, left, back (the side of the body the camera sees). Orange dashes are the
preset's target heights (chin, shoulder joint, hip joint, crotch, knee, top to bottom); cyan
ticks are the same landmarks measured. Every tile frames 2.0 m by 1.4 m, so sheets of two
versions or two bodies line up tile for tile; `views.json` records the frame and says
`standard_frame: false` when a body too tall or wide forced a bigger one.

## The critic

For any judgement beyond the numbers - is it better, does it read as a person, is the brief met -
spawn a critic that did not build the body:

```
Agent(subagent_type="general-purpose", description="Critique body contact sheet", prompt="""
You are the critic in humanform's review loop. Read ${CLAUDE_PLUGIN_ROOT}/references/critic-checklist.md
and follow its protocol exactly. Brief: <the character sheet or user's words>. Layer being judged: <L1..L6>.
Current version: <out_dir>/body.png, <out_dir>/closeups.png, <out_dir>/humancheck.json.
Previous version (for pairwise comparison, or 'none'): <prev_dir>.
Write your questions before opening the images. Return only the JSON the checklist specifies.""")
```

Keep a change only if the locked numbers held and the critic prefers it (see the checklist's
keep-or-revert rule). Save a numbered `.blend` before every change so a revert is a file load.

## Rules

**Measure in the rest pose.** Everything is read with the armature's pose position set to REST
and restored after, so an animated rig on frame 40 measures the same as on frame 1.

**A tape measure reads the convex hull.** Circumferences are hull perimeters of the section, so
a waist between two hips or a cleft between the buttocks does not shorten them.

**The crotch is where the legs stop being separate,** not a vertex: scanning up from the knees,
the first section that crosses the midline. Fused thighs show as a low crotch and hip joints far
above it - Belle's thighs are joined 27 cm below her hips.

**Widths are taken where arms cannot contaminate them.** The first shoulder width slice, 2% of H
below the joints, cut through the A-posed arms and read a default MPFB male at 0.315 H; the section
that crosses the midline at the joint height reads 0.288 H.

**Symmetry is measured to the surface.** Measured to the nearest mirrored vertex, a perfectly
symmetric decimated sculpt (Nora) read 5.1 mm asymmetric - an edge length; to the surface it reads 0.2 mm.

## Limits

- The realistic preset is ANSUR II, a military sample - fitter and younger than the general public.
  Chin and head count still come from Drillis & Contini (ANSUR has no menton height).
- `elbow_centering` reads high on a bent elbow because the section is oblique to the bend.
- Face relief looks only at the nose against the nasion on the midline; eyes, lips and ears are
  judged by the critic from the close-ups.
- One body at a time, standing in a rest pose between A-pose and arms at 65 deg down (tested range).
  A T-pose is untested; a sitting or crouched rest pose will not measure.
- No UV overlap, texel density, weight or deformation checks yet (L5 and L7 gates, later phases).
