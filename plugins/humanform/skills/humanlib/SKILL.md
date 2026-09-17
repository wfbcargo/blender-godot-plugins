---
name: humanlib
description: Reuse and compose adult human bodies and body parts for Blender and Godot 4.7 instead of building every character from scratch - a library of fitted MPFB2 bodies and judged parts (faces, hands and feet) indexed by ANSUR II measurements and descriptive tags, a one-call pipeline that reuses a stored body in under a second, warm-starts a similar one in a few seconds or fits a new one, parts that transfer between bodies on MPFB's shared mesh without stitching, batch design of part variants judged by one critic call, and verdict statistics that steer future designs away from what critics reject. Use when making several characters, crowds, NPCs or variations; when asked to reuse, save, store, catalogue, index, search or combine characters, bodies, faces, hands, feet or parts; to give a body a different face, hands or feet; to generate face, hand or foot variants; to make character creation faster; or to add eyes to an MPFB body.
---

# humanlib

The fastest good-looking body is one that was already built and judged. Everything here runs on
MPFB2 bodies, which all share one mesh - the same vertices, UVs and rig - so a stored body is
just the parameters that made it, and a part is just one region's parameters. Nothing is welded.

Bootstrap as in `humancheck` (reload `humanform`), then `from humanform import pipeline, library, parts, eyes, views, sheet`.

## One call

```python
res = pipeline.make(sheet.new(name="Ines", sex="female", age=31, stature=1.70, build="athletic",
                              firmness=0.7, skin=(0.50, 0.33, 0.24), iris=(0.38, 0.29, 0.19)),
                    out_dir=r"C:/proj/people/ines", store=False, contact_sheet=True,
                    face_part="face-female-11-6-df37e12a",     # optional stored parts
                    hand_part="hands-female-hands-21-2-b35cf548", foot_part=None)
res["path"], res["ansur"], res["nearest"], res["timing"], res["check"], res["macros"]
```

The brief is the whole description: firmness, proportions and muscle go to MPFB's macros, `skin` and
`iris` (screen colours) to flat materials, and an age outside ANSUR's 17-58 still makes a body -
`ansur` `"aged"` (fitted at 58, aged by MPFB, stature restored) or `"child"` (MPFB only, path
`"child"`, no check) - with a "not measured against ANSUR" note. See `humanform`'s brief table.

| path | when (ANSUR z-distance to the nearest stored body, same sex and style) | measured |
|---|---|---|
| `reuse` | < 0.35 and one measurement confirms every residual within the stored fit's accuracy | 0.7 s total |
| `warm` | < 1.6: fit starts from that body's parameters **and its stored Jacobian** | 2-5 s |
| `fresh` | otherwise | 3.5-7.5 s |

`store=True` saves the result as a body card when humancheck has no fails and the body was measured
against ANSUR (aged and child bodies are never stored). Eyes are added (`eyes=False` to skip).
`res["start_macros"]` are the macros the fit began from, `res["macros"]` the finished body's. A part forces a fit so its measurements are re-solved for this body; a hand
or foot part's size offsets move the targets first.

Every fit has three stages and a settle pass: body, face (ANSUR head measures), hands and feet
(`scaffold.fit_extremities`: hand length and breadth, palm length, wrist girth, foot length and
breadth, ankle girth; 0.4-0.9 s, 8-9 measurements, within 0.7 tolerances on the reference briefs).
A body stored before 0.5.0 gets the hands-and-feet stage on reuse.

## The library

`~/.claude/humanform/library` (or `HUMANFORM_LIBRARY`): `index.json` plus `items/<id>/card.json`
and `thumb.png`. Cards are the user's data - never delete them without asking.

```python
library.find_bodies(resolved, k=3)             # [(distance, card)] - resolved = sheet.resolve(brief)
library.find_parts("face", tags=["square jaw"], sex="male")
library.apply(human, card)                     # body: macros + every hf: target; part: its targets only
library.save_body(human, resolved, fit_rep, check_rep, tags=["npc"], thumb=".../body.png")
library.index()["items"]                       # summaries: id, kind, region, tags, sex, style, build, features, quality
```

A **body** card holds the MPFB macros, every non-zero `hf:` target, the solver's parameters, the
body and face Jacobians (so a warm start skips re-measuring every parameter), the ANSUR z-scores it
is indexed by, and its quality (fit accuracy, humancheck counts, critic verdict). A **part** card
holds one region's style targets, the critic's tags and evidence, and where its grid image is.

## Designing parts: batch, judge once, keep, learn

```python
vs = [{"name": "base", "region": "face", "targets": {}}] + parts.variants("face", n=8, seed=11, strength=1.3)
png = views.variant_grid(human.name, out_png, vs, apply=lambda v: parts.apply(human, v))   # ~1-2 s for 9
```

Then one critic subagent judges the whole grid with the protocol in
`${CLAUDE_PLUGIN_ROOT}/references/critic-checklist.md` ("Batch design critique"). It returns
keep/reject per panel with evidence, and plain descriptive **tags** for every kept design - the
index people and later briefs search by. Keep and learn:

```python
for p in verdict["panels"]:
    if p["keep"]:
        parts.store(human, "face", vs[p["panel"]], tags=p["tags"], sex="male", style="stylized",
                    critic={"evidence": p["evidence"], "grid": png, "panel": p["panel"]})
parts.record_verdicts(vs, verdict)      # per-target keep/reject statistics in the library
parts.amplitude_scale("face")           # targets critics keep rejecting shrink (after 10 judged designs)
```

A design uses only **style** targets (nose, lips, jaw, chin, cheeks, brows, eyelids, ears) and
never the ones the face fit uses to hold ANSUR's head measurements, so a stored face goes onto any
body and `scaffold.fit_face` restores that body's measurements with the look intact.

## Hands and feet

MPFB's hands and feet have few free targets - the fit needs hand scale, finger length, wrist girth,
foot scale, foot width and ankle girth to hold ANSUR's sizes - so a hand or foot design is two things:

- **free targets** the fit leaves alone: finger thickness and spread; foot depth (after the refit, a
  higher, thicker or a lower, flatter foot);
- **size offsets** in ANSUR standard deviations for the sex: `palm` (+ broad palm with short
  fingers, - narrow palm with long fingers: MPFB moves palm length and breadth together, so asking
  for them separately gave hands 2-3.4 tolerances out), `wrist`, `foot_breadth`, `ankle`.

```python
base = res["fit"]["extremities"]          # the base body's hands-and-feet fit: params + Jacobian
lm = landmarks.from_measurements(sheet.resolve(s)["values"], s["sex"], s["style"])
drawn = [{"name": "base", "region": "hands", "targets": {}}] + parts.variants("hands", n=16, seed=21, strength=1.3)
vs, lost = parts.screen(human, lm, drawn, base, n=9)     # refit each (~0.3 s); drop what the mesh cannot make
png = views.variant_grid(human.name, out_png, vs, region="hands", apply=lambda v: parts.show(human, v))
```

`screen` refits each design to its offset sizes from the base fit's Jacobian and drops designs whose
refit misses by more than 1.5 tolerances (1 in 37 in the first batch) - the critic never judges a
hand the mesh did not actually make. `show` puts a screened design's resulting shape back without
refitting, so the grid renders in 1-2 s. Frames (`views.region_frames`): a hand from its back and
from the front, a foot from above-front, its outer side and the front, each clipped to the hand or
foot so the thigh, shin and belly cannot hide it.

Judge with the checklist's hand and foot questions, then store and record as for faces. `store`
tags hands and feet with **measured words** (`parts.size_tags`: `broad palm`, `slender fingers`,
`narrow foot`, `heavy ankle`, ...) and keeps the critic's tags only on other axes (toes, thumb,
heel): critics tagged three of eleven kept feet broad or narrow against their measured breadth.
Hand and foot differences are subtle - critics called about half the kept designs `slight`.

Seeded in the user's library: 13 hand and 11 foot parts from Mara (female) and Kade (male).
`scripts/seed_parts.py` re-stores them from `data/seed/*_hands_*` and `*_feet_*`.

## Delta parts (sculpted)

A **delta** part is a shape MPFB has no target for, stored as per-vertex heights along the normal, in
named groups, integer micrometres (`humanform.delta`):

```python
card = delta.store("muscle", "definition-v1", {"abdominals": h1, "deltoids": h2}, reference={"stature_m": 1.729})
delta.apply(human, card, weights={"abdominals": 0.6, "deltoids": 0.9})   # shape key hfd:muscle (value=, key_name=)
delta.apply(baked_mesh, card, weights=w, mode="mesh")                     # into the vertices of a baked body
library.apply(human, card)                                                 # every group at 1
high = delta.high_copy(human, "hfd:muscle")                                # for a normal-map bake (lookdev detail)
```

- **Transfer** is by vertex index: hm08's body is vertices 0..13379 on every MPFB body, before and after
  `bake_for_game` (helpers and joined eyes come after). `check_topology` refuses another mesh. A height is
  scaled by the wearer's stature over the reference's and pushed along the wearer's own normal (the mix of
  its current shape keys, `hfd:` keys excluded), so it sits on the wearer's surface.
- `hfd:` keys are not `hf:` targets, so `library.capture` never stores one in a body card; `bake_for_game`
  folds the key in at its value.
- The first set is `muscle/definition-v2` (see humanform's "Muscle definition"): `muscle.find()`, `muscle.seed()`.
  `apply(..., key_name=)` puts groups on separate keys: muscle definition keeps `bulk` on `hfd:muscle-bulk`.
- **A delta can only hold what the mesh can carry.** hm08's vertices are about 15 mm apart, so a form
  narrower than that lands on one vertex and renders as a facet, not a shape. Anything authored for this
  topology wants the guard muscle's set uses (`muscle.spikes` / `muscle.despike`, 4 mm off the neighbours'
  mean) before it is stored.

## Eyes

`eyes.add(human, iris=(r, g, b))` (a screen colour; `None` for a mid brown) builds `<name>_eyes` - two spheres with sclera, iris and pupil -
at the centre and radius of MPFB's hidden eye proxies, skinned to `spine.005`. Contact-sheet
close-ups and variant grids render in material colour so the eyes read against the clay skin.

## Rules

**Judge many at once.** Nine faces cost one image and one critic answer (~40 s); nine separate
critiques cost nine. The first batch kept 4 of 8 female and 7 of 8 male designs.

**A stored body must reproduce itself.** Reapplied, Mara's first stored parameters missed the neck by
2.5 tolerances: the face stage had moved the chin, and the neck is measured under the chin, after
the body fit had finished. `scaffold.fit_all` now re-measures and settles the body after the face,
and a repeated brief reuses in 0.7 s.

**Warm starts need the Jacobian, and a stopping rule.** Started from a stored body but rebuilding
its Jacobian and iterating toward an unreachable 0.5 tolerances, a warm fit took longer (60-97
measurements) than a fresh one. With the stored Jacobian, Broyden updates, and stopping at 0.75
tolerances or when a step gains under 2%, it takes 8-49.

**A warm start borrows a shape, not an identity.** The fit never touches MPFB's age, firmness,
proportions, cup size or ancestry macros, and its priors pull weight and muscle back toward where they
start, so a 34-year-old warm-started from Wren (61) came out with a 60-year-old's skin, and a soft
77-year-old from athletic Mara with her muscle. `pipeline.make` resets those (`scaffold.reset_macros`,
`scaffold.UNFITTED`) to the brief's own after applying the stored body - and weight and muscle too,
unless the stored fit began from the same weight and muscle as this brief (same BMI and build), whose
fitted values are then the right answer: resetting them anyway moved a repeated Mara's waist 1.5
tolerances and no repeated brief reused (6.9 s instead of 1.4 s).

**Verify:** `blender -b --factory-startup --python ${CLAUDE_PLUGIN_ROOT}/scripts/tests/phase4_warm_ages.py -- lib=<scratch folder>`
(53 checks: a warm start's macros against its brief with controls, a repeated brief reusing, an 8- and
an 81-year-old's stature, age macro and notes, the sRGB curve and material colours).

**Learn from rejections, slowly.** In the first batch every mottled-cheek rejection used
`cheek-volume`; the statistics shrink such targets only after 10 judged designs and never below
half their amplitude, so one unlucky batch cannot erase a feature.

## Limits

- Parts are MPFB target sets or delta (sculpted) sets. Only `muscle` has a delta set; nothing converts a
  non-MPFB mesh onto the shared topology yet, and a delta moves vertices along the normal only.
- Regions for designed parts: face, hands, feet. Hand and foot designs are limited to MPFB's targets: no
  knuckle, nail, toe-length or arch-shape designs yet (a delta set could carry them). Hand and foot
  parts are symmetric; there are no left- or right-only parts.
- Hair, eyebrows and eyelashes are not parts yet; eyes and skin have flat Principled colours (lookdev later).
- Parts on a child are applied for their look only: a hand or foot part's size offsets need a fit.
- Head count is judged against a fixed 7.7 heads; short people legitimately read fewer (a 1.55 m
  woman with ANSUR head measurements is 7.3).
