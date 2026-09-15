# 05 - Feature gaps

Category: **6 feature gaps**. Five independent items, each its own piece of work, roughly in order of
how much they block characters today.

---

## 5.1 Biped jump sinks into the floor (bug)

**Problem.** `rig_analysis/actions.jump` fails its own playback check on both Belles: the left foot
goes 1.3-1.4 cm under the floor and the skin ~3 cm through it at frame 7, between the load key
(frame 6, `keyposes.crouch_key(depth=0.7)`) and launch (frame 9) from `keyposes.jump_keys`. Belle's
Jump ships with `force` and is listed under `forced_clips`; `build_belle.py` has `MAY_FAIL=("Jump",)`.
Older notes: `grungist-creek/docs/plugin-improvements.md:182-185` (3 cm dip at launch, suggests
load / air / land clips like the hoppers'), `animate-anything/SKILL.md:361`.

**Likely cause.** Launch's biped legs use hip-relative, unplanted targets (`legs_by_zone`, middle zone
`(0.8, -0.1, 0.1)`) while the load's feet are planted; smoothstep blending a planted target toward
a hip-relative one (or the foot/toe pitch) dips the foot before the hips rise.

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
