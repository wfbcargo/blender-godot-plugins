# 05 - Feature gaps

Category: **6 feature gaps**. Five independent items, each its own piece of work, roughly in order of
how much they block characters today.

---

## 5.1 Biped jump sinks into the floor (bug) - DONE

> **Fixed** (September 2026, rig-anything). Two causes, one per body plan:
>
> - **The dip.** `keyposes.Poser.blend` evaluates *both* keys' targets against the frame it is
>   drawing, so the launch's "hang the leg 80% of its length under the hips" resolved, while the
>   hips were still down in the load's crouch, to a point under the ground. A foot whose target
>   would put its sole through the floor now stays where it was planted until the hips have risen
>   enough for the target to clear it - whole, not just at that height, because holding the height
>   alone let it slide 1.1 cm sideways and the export re-check rightly called that skating. The
>   threshold is `Poser.foot_lift`: how far the foot's end sits above the lowest skin under it at
>   rest, measured as a distance, so a clip the engine has thrown into the air (which lowers the
>   poser's floor) is not held to the ground it left.
> - **The check.** A clip now carries the floor it was authored against (`action["rig_anything_floor"]`,
>   stamped by `hop.air`), and the exporter measures it against that rather than the origin. A clip
>   with its own floor is one the engine flies, so what its feet do under a notional ground is
>   reported (`declared_floor_m`, `floor_notes`) but does not refuse the export.
>
> Belle now builds with every clip passing, `forced_clips: {}` and no `force=1`; the rabbit exports
> all six clips for the first time. Covered by the `mpfb_woman_curvy` and `rabbit` fixtures (03).
> Remaining: `MAY_FAIL` is gone from `build_belle.py`, but the committed `belle.glb` and the crowd's
> exports still date from before the fix and would want rebuilding.

**Problem.** `rig_analysis/actions.jump` fails its own playback check on both Belles: the left foot
goes 1.3-1.4 cm under the floor and the skin ~3 cm through it at frame 7, between the load key
(frame 6, `keyposes.crouch_key(depth=0.7)`) and launch (frame 9) from `keyposes.jump_keys`. Belle's
Jump ships with `force` and is listed under `forced_clips`; `build_belle.py` has `MAY_FAIL=("Jump",)`.
Older notes: `grungist-creek/docs/plugin-improvements.md:182-185` (3 cm dip at launch, suggests
load / air / land clips like the hoppers'), `animate-anything/SKILL.md:361`.

**Likely cause.** Launch's biped legs use hip-relative, unplanted targets (`legs_by_zone`, middle zone
`(0.8, -0.1, 0.1)`) while the load's feet are planted; smoothstep blending a planted target toward
a hip-relative one (or the foot/toe pitch) dips the foot before the hips rise.

**A second clip fails the same way, on a different body.** The regression harness's `rabbit`
fixture (03) shows `hop.export_creature` refusing on current main: `JumpAir` puts a foot 0.074 m
and the skin 0.091 m below the floor at frame 1, though the same clip passed its authoring check.
`JumpAir` is the ballistic phase - the engine owns its vertical motion - so measuring it against
the floor may be the wrong check rather than the wrong clip. Whichever it is, hoppers and bipeds
fail it alike, so fix them together. `tests/golden/rabbit.json` records the refusal, so the fix
will show up as a diff.

**Steps.**
1. Measure foot, toe and skin height per frame 1-22 on Belle and on `HumanoidRig`/`RigTest_rig`
   (which pass - find what differs).
2. Keep feet planted (targets on the floor, toe pivot) until the hips have risen past the leg's
   reach, then release - or split the clip into `JumpLoad` / `JumpAir` / `JumpLand` as hoppers do
   (`hop.py`).
3. Update `belle_controller.gd` jump timing if the clip changes (`JUMP_CLIP_START_S`, `JUMP_TUCK_S`).
4. Remove `MAY_FAIL` from `build_belle.py`.

**Done when** Belle's Jump exports without force, the quadruped/rat jumps and the hoppers are
unchanged in the regression harness (03), and the Belle self-test passes.

---

## 5.2 Hair

**Problem.** humanform has no hair (`humanform/skills/humanform/SKILL.md:22` lists it as next;
`humanlib/SKILL.md:169`). Bald, the realistic Belle read as a mannequin, so `build_belle.py` `hair()`
builds a scalp shell (faces weighted >=0.98 to `spine.005`, pushed out) plus a UV-sphere bun, all
rigidly weighted to the head. In Godot it reads as a helmet with a hard front edge - the weakest part
of her look. follow-through has no hair spring bones yet (`follow-through/SKILL.md:76,219`).

**Design.** A humanform hair layer with presets (`short_crop`, `bob`, `bun`, `ponytail`, `long_loose`):
- Shape: a scalp cap from the head's surface with a **feathered hairline** (alpha or tapered geometry,
  not a hard boundary), plus preset volumes (bun, ponytail) as meshes placed from head landmarks.
- Material: anisotropic strand look via lookdev (a hair material preset: root-to-tip gradient,
  anisotropy, backlight), texture cards for the hairline.
- Motion: a ponytail or long hair gets a follow-through strand chain (spring bones), which
  follow-through's type registry routes as `strand`; bun and crop stay rigid.
- Brief field `hair: {preset, colour}`; the 01 spec references it.

**Steps.** (1) Hairline feathering on the existing shell approach, lookdev hair material - quick win
for Belle. (2) Preset volumes from landmarks. (3) Strand chains for ponytail/long in follow-through
(Godot runtime spring). (4) humancheck contact sheet includes hair; critic question "does the hairline
read as hair, not a cap edge?".

**Done when** Belle's hair passes a critic look at 1 m in Godot, and a ponytail preset swings on a run.

---

## 5.3 Compression garments

**Problem.** wardrobe fits garments by easing the cloth off the skin (`fit.ease(base=0.006,
loose=0.025, ...)`), so a skin-tight top traces every surface detail of the body under it, including
the nipples - real sports tops compress and smooth. Belle's top currently reads too revealing close up.
No notes existed on this (only `build_belle.py:119-123`).

**Design.** A `compression` fit mode:
- Offset the cloth from a **smoothed copy of the body surface** (Laplacian smoothing of the body
  positions over the garment's region, strength per preset) instead of the raw skin; keep ease from
  the smoothed surface.
- Optionally flatten (reduce projection of) regions named by role/type (breast) by a share, as real
  compression wear does.
- The Godot hide/cover logic must still hide the skin under it; check the verifier's coincident class
  (04a) because compressed cloth sits closer to skin over some areas and further over others.

**Steps.** (1) `fit.ease(..., smooth=0.0..1.0, flatten={"breast": 0.2})`. (2) `sports_top`,
`leggings`, `compression_shorts` presets use it. (3) Detail check from 04 step 5. (4) Rebuild Belle's
top, rerun wardrobe verifier and self-test.

**Done when** a close render of Belle's top shows a smooth compressed shape with no surface detail
traced through, and the verifier and self-test pass.

---

## 5.4 Skirts and dresses

**Problem.** wardrobe's tailor has only `shirt()` and `pants()` (`tailor.py`; `wardrobe/SKILL.md:252-253`
says skirts and dresses need their own cuts). A skirt doesn't cling to one leg, so it can't be cut from
the skin the way trousers are; follow-through already types a skirt as `draped_tube` routed to cloth
`soft_body` (`follow-through/SKILL.md:73,113`, `builtin.json:133`).

**Design.** `tailor.skirt(body, waist, length, flare)` / `tailor.dress(body, neck, sleeve, length,
flare)`: a tube from the waist (or shoulders) hanging to a hem ring sized by `flare` against the hips'
widest girth, weighted to pelvis + thighs by distance with heavy smoothing, plus sprung hem bones
(existing `hem.prepare`) for games or follow-through cloth soft body for close-ups. Cover/hide as
for other garments, but hide only the upper thigh band the skirt always covers.

**Steps.** (1) Geometry and weights, rest-pose render. (2) Hem springs; verifier with walk, run and
crouch (a crouch must not show the skirt passing through thighs - add a thigh-intersection check).
(3) Presets `skirt_knee`, `skirt_mini`, `dress_sleeveless`. (4) Soft-body route for high detail.

**Done when** a skirt preset walks, runs and crouches on the crowd women without thigh intersection
in the verifier and reads right in the review strips.

---

## 5.5 Muscle definition

**Problem.** MPFB's base mesh is smooth, so muscular/athletic bodies read as average: Dante's fit left
muscle at 0.65 and he read average until muscle was forced to 1.0 (`build_human.py:96-97`);
`docs/humanform-plan.md:244,260,296`, `docs/humanform-resume.md:104`, humanform `SKILL.md:22` ("L3-L4
muscle definition ... SDF forms").

**Design.** humanform's planned L3/L4 layer: sculpted **delta payloads** (humanlib parts that are shape
deltas rather than replaced geometry) for major muscle groups (deltoids, pectorals, abdominals, obliques,
quadriceps, calves, forearms), scaled by the brief's `muscle` and body fat (BMI/firmness) so definition
shows only where fat is low; baked into a normal map for games and optionally into geometry.

**Steps.** (1) Delta payload type in humanlib (store, apply, transfer across MPFB bodies - they share
topology). (2) Author a first set with SDF sculpting (`grungist-creek/assets/wardrobe/sdf_sculpt.py` is
a precedent) and critic review. (3) Fat-aware scaling. (4) Normal-map bake via lookdev.
(5) Rebuild Dante and Freya; critic compares.

**Done when** Dante reads as muscular in a front render without forcing the muscle macro, and a soft
body with the same muscle value shows much less definition.

---

## 5.6 wardrobe's garment step is not reproducible between builds - DONE

> **Fixed** (September 2026, wardrobe). The cause was two steps apart from the symptom.
> Belle's body arrived with the same faces in a different order on every run: same vertices, same
> triangle *set*, shuffled (the joined eyes, built with `create_uvsphere`; see 5.7). Probing a build stage
> by stage showed the body, the rig, the bone map and the cut all agreeing, and only `fit.ease`
> diverging; probing inside it showed the body's triangle list hashing differently while its sorted
> form matched. A BVH built in that order breaks near-ties differently, so `find_nearest` answers a
> vertex on a seam with one triangle in one build and its neighbour in the next, the push-out lands
> fractions of a millimetre apart, and sixteen relax iterations turn that into millimetres of cloth.
>
> `fit.canonical_tris` now sorts a mesh's triangles before any BVH is built from it (`fit.body_bvh`,
> `cover.garment_bvh`, `cover.compute`, `hem.prepare`), which makes a fit independent of the order
> its mesh arrived in - vertex order is stable across those joins, so sorting on vertex indices is
> canonical. Two full builds of Belle now write byte-identical `belle_sportstop.glb` and
> `belle_shorts.glb`. Where the shuffle came from is 5.7.
>
> **Guarded since** `regress.py --twice` (03 step 1a). The Belle comparison was by hand; what stops it
> regressing is the fixture. `dressed_figure` never joins, so on its own it could not see this, and
> with the old wardrobe code its two builds agree. `H.shuffle_faces` reproduces the cause instead:
> with `REGRESS_SHUFFLE_FACES=1` the body's faces are stored in a random order before the shirt is
> cut. On wardrobe 0.1.0 that gives NONDETERMINISTIC (`ease.gap_min_m` 0.0057 / 0.0058, a hem ring's
> `weighted_verts` 213 / 215). On 0.1.1 both builds agree with each other and with the golden. See
> `tests/README.md`.

**Problem.** Rebuilding Belle twice from the same brief produced sports tops whose vertices differ
by up to 9.9 mm, and shorts that differ too. The body is not the cause: across three builds her
exported `Belle_body` is identical in POSITION, NORMAL, TEXCOORD_0, JOINTS_0 and WEIGHTS_0, and
every bone's rest head and tail matches to 1e-7. Checksums taken inside the build, at the moment
the garment is cut, agree on both the body mesh and the rig - and the garments still come out
different.

It is not the garment code in isolation either. Cutting and easing the same garment twice in one
session is bit-identical, and running that same cut from a saved `.blend` in three separate
processes gives one checksum three times (so it is not Python hash-order across processes, which
Blender fixes anyway). Only a *full build* varies, and one of its two runs matched the isolated
result exactly - as if something earlier in the build leaves state that the saved blend does not
carry.

**Why it matters.** It puts a floor under any wardrobe regression test, it makes a rebuild a
coin-flip against the 0.5% hole limit (Belle's top came out at 0.23% of hidden vertices in the
committed build and 0.57% in a rebuild - pass and fail), and it means "rebuild and diff" cannot
prove a wardrobe change safe. The `dressed_figure` fixture (03) *is* reproducible, so whatever
this is, it does not reach the sample body - which makes it a good control for finding it.

**Steps.**
1. Bisect the build: checksum the garment after `tailor` alone, then after each `fit.ease`
   iteration, in two runs of the full build, and find the first step that disagrees.
2. Suspect state the saved blend does not carry: a depsgraph not yet updated when the BVH is
   built (`fit.body_bvh` reads `body.data`, so a stale *evaluated* mesh elsewhere is the more
   likely path), leftover flesh marks, or an operator that ran earlier in the session.
3. Once found, add the reproducibility to the harness: build one character twice in one
   `regress.py` run and compare the two, rather than comparing against a golden.

**Done when** two full builds of Belle from the same brief produce byte-identical garments, and a
`--twice` check in the harness proves it.

---

## 5.7 A body's faces came out in a different order on every build - DONE

> **Fixed** (September 2026, humanform 0.6.2, follow-through 0.2.3; grungist-creek `mesh_order.py`).
> **The join was never the cause.** Probing a Hugo build in three processes, before and after the join, showed
> the baked body identical every time and **the eyes already shuffled before they were joined**: same vertices,
> same face set, three orders. The join only carried that into the body. The eyes are two
> `bmesh.ops.create_uvsphere` calls, and a minimal repro pins it on Blender 5.2: `create_uvsphere` writes its
> vertices identically but its faces in a different order in every process. `create_icosphere`, `create_cube`,
> `create_circle` and `create_cone` do not.
>
> Every `create_uvsphere` whose faces reach an output now goes through a `_uvsphere` helper. The helper sorts
> the new faces by vertex index and leaves faces already in the bmesh where they are:
> - humanform's `eyes.add`
> - follow-through's ClayBall and WaterBalloon samples
> - grungist-creek's Belle hair bun and Nora's eyes, through `assets/mesh_order.py`
>
> Spheres that are voxel remeshed afterwards take their order from the remesh, so they were left alone:
> hopper samples, follow-through's `_body`, and the octopus test mesh.
>
> Proven:
> - The real Hugo build (source, bake, eyes, join) gives one face-order hash in three processes.
> - Belle through her hair join does as well.
> - `mpfb_woman_curvy` now reports `structure.eyes_faces` and `structure.body_faces` through
>   `H.face_order`. Against the unfixed humanform, `--twice` reports NONDETERMINISTIC on exactly
>   `structure.eyes_faces.order`; on the fix, both builds agree.
>
> No `join_into` was needed. The "done when" asked for a `.blend` reproducible to the byte; that was not
> checked, because a .blend carries per-save data. Face order through a whole build is what was checked.

**Problem (as first filed).** Joining the eyes into a baked body gave the same vertices in the same
order and the same set of faces, in a different order on every run - three runs, three hashes of
`[tuple(q.vertices) for q in me.polygons]`, while the sorted form and the vertex hash held. It was
put down to the join; see above for what it was.

**Why it mattered.** 5.6 made wardrobe immune, and rig-anything's glTF export writes the same
indices either way, so nothing shipped was affected. But every consumer that walks faces in mesh
order inherited the trap, and "rebuild and diff" was weaker than it looked.

---

## 5.8 Found by the new fixtures (03 steps 1b, 1c)

Each of these is recorded as-is in a golden, so a fix shows up as a reviewed change and not as
silent drift.

- **Done (rig-anything 0.19.0): the cricket's landing failed its foot-slide check, so the cricket
  never exported.** It was a real slide, and generator code, not the cricket or the limit. JumpLand's
  forefeet reached the floor a frame before their spots and skidded 0.5 mm in (1.7% of the body):
  `hop._within_reach` pulled an out-of-reach foot back toward the hip, shortening its ground
  position with its height. Behind it, the walk's hind toes dragged 1-1.4 mm through the end of
  every swing, for two more shared reasons: the poser's floor clamp tested a swinging foot's ankle
  without the roll's lift and held it planted at floor height, and `locomotion`'s swing fold, sized
  for paws, tipped the 5 mm tarsus into the floor. Each clip's own check measured drift from a
  touchdown it guessed, or only in stance, so none saw these. Fixed: `keyposes.within_reach` gives
  up height before ground position (hop and flight use it), the clamp tests a swinging foot on the
  ankle it solves, the fold keeps the contact clear, and `_check_common` checks every clip for a
  grounded limb moving along the floor (`floor_skid`; slides opt out, in-place gaits pass their
  stance). With the walk bugs put back the new check fails the cricket walk at 1.4 mm. Limbs are
  now named by `bodymap.limb_name` (`fore.L`, not `fore_femur.L`; `front.L`, not
  `front_thigh.L`). The same check puts the slide recoveries on a Rigify biped at 0.2-0.4 m of leg
  dragged along the floor - evidence for the next finding.
- **Done: the three slides put feet through the floor on a Rigify biped.** On follow-through's
  `Figure` with `fit_basic_human`, `actions.slide` had a toe 0.16 m and skin 0.11 m below the floor
  at frame 8; `slide_recover(to="stand")` and `(to="crouch")` a foot 0.025 m under at frame 4,
  starting 0.18 m from where Slide ends, and dragging the legs 0.2-0.4 m along the floor. Three
  shared causes, none of them the Figure. `actions.slide` hand-wrote its path rather than blending
  to `keyposes.slide_key`, so it had none of the poser's floor handling: the tucked trail foot
  followed its shin into the ground, and the recoveries, which start on the draped key, began 0.18
  m away. Slide is now `blend(rest, slide_key)`, seam 0 by construction. The poser draped only the
  toes of a foot in the air, from wherever the foot ended, so the trail foot's ball stayed 2.7 cm
  under: `motion.Body.lay_on_floor` now turns an unplanted foot up about its ankle by its real skin
  first (the rod model toes and tails use flicked the toe up 12 cm in a frame). And `Poser.blend`
  drew a foot between two floor spots in a straight line along the floor - the recoveries' lead
  heel reached the floor 0.41 m short and skidded in, the trail foot 0.14 m, Slide's lead heel 0.32
  m out, a Rigify dog's recovery forefeet 0.29 m: between two targets that both mean the floor (at
  rest, or marked `keyposes.on_floor`), `Poser._step` lifts the foot, crosses and sets it straight
  down. Marked rather than judged by height, because a jump's tuck asked for under the floor read as
  on it and lifted an MPFB woman's feet a frame early. All three slides now pass and export (worst
  skid 2 mm), and `slide` and `skid` no longer opt out of `floor_skid`; with the step put back Slide
  fails it at 0.32 m, with the foot not laid all three fail at 1.3 cm under the floor. Open: the lead
  foot crosses up to 0.31 m in one frame of SlideRecover and the knees fold to 30 degrees at the top
  of the step - the recovery's timing (`feet_lead`, 18 frames) is worth a look; and the dog's
  SlideRecover still ends 3.0 mm from rest at `front_toe.L` (it did before), which looks like the
  toe drape's rod model lifting a sloped toe at rest.
- **A symmetric starfish gets arms with different bone counts.** `radial.build` uses
  `round(L / (1.2 * W))`. Metaball arm widths vary about ±10%, so one arm lands at 3.49 (3 bones)
  and another at 3.66 (4). This is deterministic, but it sits on a rounding edge that any change to
  the mesher can flip. Take one count per appendage *kind* (the median), not one per arm.
- **`radial.skin` reports `coverage: 1.0` without measuring it.** The starfish fixture counts the
  weighted vertices itself (`skin.measured_coverage`). Measure it in `radial.skin` the way
  `hoppers.skin` does.

---

## 5.9 flesh reads the buttocks low, on every body measured

Found in 02 step 2e (September 2026). **Open.**

**Problem.** `flesh.find_regions` places a buttock at the fold under it, not on the mass itself:
- **Belle:** hip joints at 0.873 m. Her hand-marked buttocks put the bone head at about 0.862 m, facing slightly up. The measured regions put it at 0.794 m, facing down (normal z -0.23).
- **Sample bodies** (`samples.score_flesh`): the Figure's measured butts sit 0.13 m from their known centres, just over the 0.12 m tolerance, so they score as misses. The Bloater's sit 0.06 m off.

**It is not the zone.** The butt zone's height range (-0.5 to 0.3, where 0 is the hips and 1 the shoulders) was tried at -0.25..0.35, -0.15..0.40 and -0.05..0.45:
- Belle's measured regions only exist below the hip joint. At -0.15 or above, no butt is found at all.
- The sample distances get worse (0.134 and 0.066 at -0.25).

**Cause.** The lean envelope (`flesh._envelope`, a line refitted along the body without its outliers) counts the upper buttock as part of wide hips, so only the fold below stands out as excess. `build_belle.py` already notes the measure "reads the seat low", and set Belle's swing limit by hand because of it.

**Steps.**
1. Measure the envelope's rejected rings on Belle and on the Figure at buttock height.
2. Try an envelope fitted across the waist-to-thigh span without the pelvis band, or seed the butt from the most posterior skin behind the hip joints (the pelvis and legs' `upper` roles give both heights).
3. Judge any change by `score_flesh` on both samples and by Belle's marked-versus-measured head, not by the zone.

**Done when** both sample bodies score their butts within tolerance and Belle's measured buttock head is within 3 cm of her marked one, with every other region unchanged.
