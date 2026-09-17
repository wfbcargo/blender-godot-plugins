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

> **Shipped** (September 2026, wardrobe, branch skirts-dresses; version bump left to the merge).
>
> - `tailor.skirt(body, waist, length, flare)` and `tailor.dress(body, neck, sleeve, length, flare)` in
>   `wardrobe/skirts.py`: a tube built round the body (rays to its surface without arms and fingers, hanging
>   from the widest point, 15 mm ease, a 5 mm waistband, the hem `flare` x the widest hip girth, 2 cm off the
>   legs); a dress is a shirt cut to the natural waist, eased, zipped to a skirt.
> - **Nothing follows one thigh by weight** (the presets pass `thigh=0`). Weighted to the thighs by distance
>   the counts were low (4 of 1088 inside) and it still read wrong: the cloth split round each leg and a
>   mid-stride front view was shorts or culottes, the fig224 failure. Instead `hem.prepare` hangs 24 hem bones
>   from the pelvis, hinged 5 cm above the hip joints; from the hip joints down (over 4 cm) the cloth is
>   theirs outright, above them it keeps the skin's weights, and cover hides that band (33 verts on Rosa's
>   knee skirt, 8 triangles).
> - **Leg colliders and a fold, in Godot** (`hem_modifier.gd`). The block carries a capsule fitted to each
>   thigh and shin - a centre and a radius at knots along the bone, the 75th percentile of that leg's skin
>   plus 6 mm - and each hem bone's slack against them at rest. Every frame the ring is placed: a **fold**
>   (what the thighs under a bone do: at the front the lesser of the two swings toward it, at the side the
>   nearer thigh's, measured as the arcsine of how far its tail moved that way) turns the bone's head and
>   tail about the hip line as skin on the thigh would; then a **swing** outward, the least angle that takes
>   its test points out of every capsule, spread to its neighbours (30 degrees a bone) and raised while the
>   cloth between two neighbours is still inside one. Both are outside the spring: not limited by
>   `max_offset_m`, not fed back, so the cloth drops as the thigh leaves.
> - Presets `skirt_knee` (0.85 of the way to the knee, flare 1.3), `skirt_mini` (0.45, flare 1.4),
>   `dress_sleeveless`, through `wardrobe.dress` and a spec's `[[outfit]]` (Mei built with
>   `preset = "skirt_knee"` exported `mei_skirt.glb` and listed it in her manifest).
> - `verify_wardrobe.gd` `thighs`: garment vertices inside a leg (all four lines leave skin from inside, the
>   inward one through leg skin), limit 0.5%, on skirts and dresses by default; controls `rigid=<bone>` and
>   `colliders=false`; `dump=<frame[,frame...]>` writes the measured frames as OBJ - the body as the game
>   draws it (hidden triangles dropped) and, for a skirt, its colliders as rings of spheres.
> - Soft-body route: `wardrobe.dress(..., soft=True)` writes a follow-through `draped_tube` spec pinned above
>   the hips; `Wardrobe.equip` builds the SoftBody3D. Nadia's passes `verify_cloth.gd` at rest, moved and bent.
> - **Measured** (Godot, 240 frames sampled every other frame - 119 samples, whole cycles of each clip): all
>   27 runs pass - three presets on Mei, Nadia and Rosa, built from `characters/*.toml` in scratch, walking,
>   running and crouching. Worst inside a thigh 2/1024 (the knee skirt, Rosa's crouch), 3/704 (the mini,
>   Nadia's), 6/2420 (the dress, Mei's); walks and runs are mostly 0. No holes. Poke at most 0.32%, and in a
>   crouch it is thigh skin past the hem, not through it. Controls: `colliders=false` 97/1152 and
>   `rigid=spine` 95/1152 on the fixture Figure's walk, against 4 with them. That walk crosses the feet over
>   the midline and used to be the knee skirt's failure (48/1152); `regress.py --godot` now wears the knee
>   skirt there with both controls.
> - Open: a knee skirt in a run still pinches the cloth where the panel meets the band on the hip and lets a
>   patch of hip through it (11 vertices of 14344, ~2 cm across; 21 before the ease went from 15 to 22 mm).
>   A mini in a deep crouch rides up onto the thighs and shows the lap - true of a real mini, but worth
>   a look if crowds squat often. The cloth (soft) route still has no leg colliders. Nothing but the legs
>   collides: an arm swinging into a skirt goes through it. "Reads right in the review strips" was judged on
>   scratch renders of Godot dumps (rest, two frames of each of walk, run and crouch, front/side/three-quarter),
>   since 04b's review strips are not built.

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
- **Done (branch `radial-counts`): a symmetric starfish got arms with different bone counts.**
  `radial.build` used `round(L / (1.2 * W))` per arm. Metaball arm widths vary about ±10%, so arm02
  landed at 3.49 (3 bones) and the other four at 3.63-3.89 (4), on a rounding edge any change to the
  mesher could flip. `radial.build` now takes the median ratio of each appendage kind (role: arm,
  tentacle, oral arm) and gives every appendage of that kind the same count, capped as before. The
  starfish's median is arm01's 3.66, so arm02 gets 4 bones like the rest: 21 bones, not 20; arm02's
  bones are 17.4-19.9 mm, not 25.2-26.0 mm, in line with the other arms' 17.7-20.5 mm; Crawl's
  `stretch_max` 1.254 -> 1.249, Idle's 1.024 -> 1.022. Both clips still pass and export.
  Outside the fixtures, the test anemone had the same split (ratios 4.07-4.77: three tentacles of 4
  bones, seven of 5) and now has 5 on all ten, 51 bones not 48, with Sway, Retract and Extend passing
  at the same stretch; the jellyfish (145) and brittle star (41) were already uniform and are unchanged.
- **Done (branch `radial-counts`): `radial.skin` reported `coverage: 1.0` without measuring it.**
  It now reads the written weights back off the mesh: `coverage` is the share of vertices some deform
  bone of the rig holds, `vertices_unweighted` their complement, `bones_weighted` and
  `bones_without_skin` count bones that hold a vertex, and `passed` needs every vertex held (as
  `hoppers.skin` does). The starfish fixture no longer adds its own `skin.measured_coverage`: it
  reports what `radial.skin` returns (coverage 1.0, 0 of 2508 vertices unweighted) and fails if its
  own independent count of unweighted vertices disagrees.

---

## 5.9 flesh reads the buttocks low, on every body measured - DONE

Found in 02 step 2e (September 2026). **Done** (follow-through, branch `butt-envelope`): buttocks are
read from the side. What was found is under **Outcome** below; the original report follows it.

**Outcome.**
- **The suspected cause was wrong, and differed by body.** Nothing absorbed the upper buttock as wide
  hips. A buttock sits where the spine chain ends and the thigh chains begin, and rings need the
  body on both sides of a bump:
  - **Figure:** the spine chain's first ring is the crotch. Its radius was 0.02 m where the hip
    sides are 0.15-0.17 m, the refitted line started there, and the hip sides stood 0.10-0.12 m
    proud against 0.03-0.05 m for the buttock. 60% of the butt bone's placement weight came from
    facing 80-120 degrees (the hip sides), so the bone sat 0.13 m off, above and outside the mass.
  - **Bloater:** the same, less so (47% from facing 120-140, the bone 0.06 m off).
  - **Belle:** her MPFB rig split the trunk: `root` + `spine` became a chain from the floor to
    0.961 m and `spine.001` started another (51 degrees between them). The pelvis chain held
    four rings of skin, the line hugged the upper buttock (excess 0-0.005 m at 0.88-0.94 m), and
    the thigh chains only saw below the hip joints - the fold.
- **Ruled out, measured:** rings built only from wall vertices (normal across the chain) removed
  the crotch but lost the buttock too (20 seed vertices on the Figure: a bump at a chain's end reads
  as a ramp), and moved every other region, Belle's breasts 0.23 m.
- **Fix:** `flesh._profile`, used by a type with `"lean": "profile"` (`butt`). Per slice across the
  body (one band wide) and per band of height, it takes the silhouette behind the hip joints among
  vertices facing back, arms left out. The same `_lower_envelope` runs down each slice, so the lean
  line runs from the small of the back to the back of the thigh, across chains. Excess is the
  distance behind that line; lean is the vertex's distance from its chain less that. `marks.regions`
  reads a marked `profile` type the same way. Halving or doubling the slice width, or requiring
  normals 0.3 toward the back, moves every result by under 1.5 cm.
- **Results:**

  | | before | after |
  |---|---|---|
  | Figure butt.L / .R, `score_flesh` | 0.129 / 0.131 (miss) | 0.036 / 0.033 |
  | Bloater butt.L / .R | 0.058 / 0.059 | 0.027 / 0.021 |
  | Belle butt head | (0.121, 0.004, 0.794), normal z -0.23, peak 3.6 cm | (0.072, -0.029, 0.858), normal (0.03, 1.00, -0.06), peak 7.8 cm |
  | Belle, measured vs marked head | 8.7 / 7.8 cm | 1.0 / 0.9 cm (marks read the same way) |

  Belle's new head is level with the old marked one (0.858 against 0.862 m) but 7.5 cm from it,
  nearly all depth: a head sits the mass's depth plus half its peak under the skin. The crowd's
  Hugo, Nadia and Mei, and `pipeline_woman`'s curvy woman, had no butt found by rings and now have
  one, facing back, 0.05-0.11 hip-to-shoulder spans from the hip joints; Dante's moved 4.6 cm down.
- **Every other region:** Bloater, Belle's breasts and every ring-measured region on all bodies are
  identical as measured. What moved did so through claim order (a region takes vertices no earlier
  type claimed):
  - Figure love handles moved 7.4 cm down onto the hip sides the old butt had taken (peak 6.1 to
    9.3 cm; the Figure has no true love handles, before or after).
  - Figure belly gained 84 vertices (head 6 mm).
  - Figure thighs lost 74 vertices each (head 4 mm); Belle's thighs gained 13 (head 9 mm).
  - Garment covers on the Figure shifted by 20-40 vertices with the butt's weights.
- **Swing limit:** `butt.limit_share` 1.9 to 0.9. Godot's self-test on Belle settled 6.9 cm when she
  read 3.7 cm, and 1.9 x 7.8 cm would have been 14.8. Belle's measured butt now gets 7.0 cm. With her
  marks kept, the marked peak is 8.6 cm, which gives 7.7 cm.
- **Found, then fixed (branch `flesh-end-rings`, after 02 was done):** the crotch ring skewed the
  Figure's whole spine envelope, not just the butt. It was held back because it moves regions the
  done-when kept fixed.

**Follow-up: end rings and heat.**
- **End rings from the wall.** `flesh.tissue` builds each chain's first ring (ring 0 by arc length)
  from wall vertices only: radius per sector from vertices with `|n . axis| < 0.5` (`END_RING_WALL`);
  every vertex in the ring is still measured against it. So does the last ring *built* on a chain
  searched to its end (`ch["to_end"]`: a limb of two segments or fewer, whose search limit is its
  length, or a spine the shoulder cut takes nothing from). Buttocks are unaffected (they read the
  profile). On the Figure ring 0 of the spine held 223 vertices, 19 of them wall. The Figure and
  Bloater have no such chain - every limb has three or four segments and
  stops at the wrist or ankle, and each spine is cut - so on them only first rings changed. Belle has
  one: MPFB's `root`-`spine` chain, two segments from the floor to 0.961 m where her spine chain starts
  (220 vertices, all searched). Filtering its top ring moves the excess of 72 vertices at 0.83-0.93 m
  by up to 1.3 cm and the lean by up to 4.8 cm; her regions are identical (breasts 271 / 271 vertices,
  peak 11.84 / 11.86 cm; butts 161 / 161, thighs 158 / 156, every head and tail to 0.1 mm).
  The first version of this filtered ring `nb - 1`, with `nb = ceil(length / band) + 1`: arc never
  passes the chain's length (past it is cap), so that ring was always empty and the last-ring half
  never ran, on any chain (found in review); the fix counts `to_end` and the last ring with enough
  vertices to build. The last ring with vertices is `int(length / band)`, and
  the last one built can be earlier still: searching the Figure's limbs to their ends in scratch, the
  arms' last built ring is 12 of `nb` 16 (length 14.3 bands; rings 13-14 at the fingertips are too
  thin to build), the legs' 22 of 25, and the filter keeps 0-6 of their 20-51 vertices. Counting a
  limb as searched to its end because no vertex past its limit was skinned to it (the Bloater's right
  arm, whose hand is all cap) would have filtered its wrist ring and moved its arm flab (580 to 542
  vertices) - not taken: the wrist is a slice through the arm, not a cap.
- **Results** (`samples.score_flesh`, `find_regions` at rest; tail distance to the known centre):

  | | before | after |
  |---|---|---|
  | Figure breast.L / .R | 0.079 / 0.079, 826 / 791 verts, peak 8.8 cm | 0.057 / 0.061, 687 / 651 verts, peak 7.8 / 8.0 cm; heads 7 cm up |
  | Figure belly | 0.108, 607 verts, peak 12.0 cm | 0.076, 241 verts, peak 4.5 cm (the bump is 3.5 cm) |
  | Figure love_handle.L / .R | found, peak 9.4 / 9.2 cm (it has none) | declined: 35 bulging vertices in the zone |
  | Figure bloater_belly (declined) | 16.5% of volume, 6.3% of height | 3.8%, 2.7% |
  | Figure butts, thighs, arm flab | | identical (thigh mass +1 g) |
  | Bloater arm_flab.L / .R | 584 / 619 verts, peak 4.6 / 5.1 cm | 520 / 580 verts, peak 4.2 / 4.5 cm; bones 2.0 / 2.1 cm |
  | Bloater love_handle.L | 2.51 kg | 2.65 kg, tail 6 mm |
  | Bloater thighs | 1149 / 1146 verts | 1164 / 1164, bones unmoved |
  | Bloater belly, breasts, butts, love_handle.R | | within 0.3 mm |
  | Belle breast.L / .R (built to `hair` in scratch) | 267 verts, peak 11.78 cm | 271 verts, peak 11.84 cm, head 0.9 mm |
  | Belle butt.L / .R, thighs | | identical |

  5.9 predicted Belle "unchanged"; her breasts move 0.9 mm because her spine chain starts at
  `spine.001` (0.961 m) and its first ring loses 10 of 76 vertices. 5.9 gave the Figure's belly as
  0.106 before; it is 0.108 at `main`, probably measured before the butt change added 84 vertices
  to it. Every other number is the prediction. Choosing the first and last ring *that was built* instead (so the spine's partial
  ring at the shoulder cut, 15 vertices, counts as an end) put the Figure's breasts 0.036 / 0.032
  from their centres but kept love handles (peak 4.3 cm) and moved the Bloater's belly 1.4 cm and
  moob bones 4 cm - not taken; the shoulder cut is a lead for the breasts, not a chain end.
- **Goldens:** `flesh_figure` as above (the Figure's collider radius +0.1 mm with its weights).
  `dressed_figure` and `dressed_presets` have two jiggle bones fewer (the love handles), so garments
  carry 2 fewer groups and joints, and the covers moved with the body's weights: the shirt hides 4251
  vertices (4041), its hem bones hang from `spine` and `spine.001` (no longer `spine.002`: each takes the torso bone
  weighted most at its hinge, and the love handles' weight there went back to the spine); the sports top
  hides 2711 (2663). Every garment still passes.
- **Heat.** `render_heat` and `marks.render` drew butts with rings. `flesh.shown(t)` gives the
  excess and relative a heat map draws: rings, but inside a `"lean": "profile"` type's grown zone,
  the profile for every vertex the profile searched. On the Figure's back sheet the red now covers
  both buttocks with candidates 3 and 4 on it, where before it covered the hip sides and the fold
  (with false love-handle candidates 6 and 7); Belle's side sheet shows her seat, where before only
  the fold under it. The heat stops at the zone's grown top edge, a visible line on the Figure's back.
- **Still open:** the crowd has not been rebuilt. The spine's partial top ring at the shoulder cut
  is a lead for the Figure's breasts (above). The Bloater's moobs still score as misses (0.19 m),
  as before.

---

The original report:

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
