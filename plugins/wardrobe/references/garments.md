# Garments on skinned bodies: research, decisions, measurements

## How everyone does it

Three ideas recur in every engine and pipeline looked at (Unreal Chaos Cloth, Unity Cloth,
Magica Cloth 2, Ubisoft's Anvil cloth, Bethesda's Creation Engine, MetaHuman, Character Creator).

**1. The garment is skinned to the body's skeleton.** Weights come from the body: Blender's Data
Transfer modifier, Vertex Data > Vertex Groups, "Nearest Face Interpolated", is the standard,
with a warning that differing shapes need touch-up.
https://docs.blender.org/manual/en/latest/modeling/modifiers/modify/data_transfer.html

**2. Skin under clothing is not drawn.**
- Bethesda's biped slots: a shirt claims slot 32 (body) and the body part is swapped or hidden.
  https://falloutck.uesp.net/wiki/Biped_Slots
- MetaHuman: hidden body geometry and opacity masks on the skin material.
  https://forums.unrealengine.com/t/metahumans-body-mesh-depeding-on-clothes/1661087
- Character Creator: "Hide Body Mesh" and automatic hiding of inner meshes.
  https://manual.reallusion.com/Character-Creator-4/Content/ENU/4.0/08_Cloth/Automatically_Hiding_Inner_Meshes.htm
- A Unity tool raycasts from vertices to build the hide set.
  https://github.com/unitycoder/CharacterClippingProtector

**3. Free fabric moves as an offset from the skinned pose, on a leash.**
- Unreal: Max Distance ("the maximum distance any point on the cloth can move from its animated
  position", painted), Backstop Distance/Radius (a sphere it cannot enter), Anim Drive.
  https://dev.epicgames.com/documentation/en-us/unreal-engine/clothing-tool-in-unreal-engine
- Unity Cloth: per-vertex Max Distance and Surface Penetration; sphere and capsule colliders only.
  https://docs.unity3d.com/560/Documentation/Manual/class-Cloth.html
- Magica Cloth 2: BoneCloth (cheap) or MeshCloth on a reduced proxy, with a backstop.
  https://magicasoft.jp/en/mc2_meshclothstartguide/
- Ubisoft (GDC 2015): max distance as a painted sphere per skinned vertex, a low-res simulation
  mesh driving a render mesh of ~10x the vertices, 30 Hz simulation walking and 60 Hz running.
  https://archive.org/stream/GDC2015Vaisse/GDC2015-Vaisse_djvu.txt
- Jolt: skinned constraints with MaxDistance and BackStopDistance/Radius, and long-range
  attachments. https://jrouwe.github.io/JoltPhysics/

Layers: underwear, shirt, jacket, each modelled a little larger, all skinned alike, each hiding
what it covers; stacked layers are constrained to each other rather than collided.

## Why this design for Godot 4.7

- `SoftBody3D` cannot be skinned; follow-through's cloth pins a few points to bones and leaves
  the rest free. Right for a cape, wrong for a shirt, whose whole surface is held by the body.
  https://github.com/godotengine/godot/issues/93847
- Jolt's skinned constraints are not exposed by Godot's SoftBody3D; a PR to expose skin, LRA and
  bend settings (godotengine/godot#123484) was reported closed unmerged (not re-checked). Level 2
  therefore needs its own solver or a GDExtension.
- `SpringBoneSimulator3D` exists (4.4+) but is rotation-only and frame-rate dependent (measured by
  follow-through); the hem modifier uses the same exact damped oscillator as follow-through's
  jiggle bones instead.
- A skin binds to bones by name in Godot's glTF import (`Skin.get_bind_name`), so a garment can
  carry its own copy of the rig and be moved onto the body's skeleton at runtime.
- Godot's importer drops custom vertex attributes and reorders vertices; node extras survive.
  The hidden set travels as glTF mesh-space positions in the spec and is matched by position.
- Removing triangles (not a shader mask) keeps the body's material untouched, removes the
  overdraw and the shadow of hidden skin, and costs one mesh rebuild per equip.

## Levels of detail

| level | what | measured on the sample |
|---|---|---|
| 0 | skinned, covered skin hidden | 7625 of 34220 body triangles not drawn; equip 50-76 ms (GDScript, once) |
| 1 | + 8 hem and 4+4 cuff bones | 49-66 us a frame for the modifier |
| 2 | leashed proxy cloth | not built |
| film | Blender cloth, baked (shape keys, OpenVAT) | offline |

Game sim meshes run to a few hundred vertices (under 200 in proxy-cloth research,
https://kuiwuchn.github.io/proxycloth/proxycloth.pdf); Ghost of Tsushima simulated thousands of
pieces of cloth on the PS4 GPU (https://gdcvault.com/play/1027124/Blowing-from-the-West-Simulating).
No per-vertex cost figure for Jolt soft bodies was found.

## Measured while building it (Blender 5.2, Godot 4.7.2)

Sample: follow-through's Figure (17 112 vertices, rig-anything metarig, 11 jiggle bones, walk),
a T-shirt cut from it (6220 vertices).

- **Ease along normals tucks.** The hem wrapped under the buttocks. A hanging radius field fixed
  it; per-sector pushes crumpled the back into ridges, and a hard on/off height left a crease.
- **Sleeve planes cross the hips** on an A-posed body; each cut is limited to its part's weights.
- **Cuffs at full ease ruffle**: 2.5 cm of ease at a short sleeve flared into frills; 0.3 of it
  reads as a sleeve.
- **Hiding all covered skin** left 38 thigh vertices uncovered in the worst frame of the walk
  (0.72%); hiding only skin whose weights share 70% with the cloth over it, 1.
- **Exact ray tests miss at vertices**: 72 false holes at rest, 0 with an edge tolerance.
- **A normal ray is not a viewer** (Belle, realistic, 16 120 vertices, shorts and sports top over 7
  clips, 240 frames): the ray-only check failed shorts crouch 1.71%, crouch walk 1.90%, jump 1.71%,
  top walk 0.68%, jump 0.91%. Of the 9 holes in the worst crouch frame, 8 had no cloth on the normal
  within 15 cm and were shut in by the thighs, 1 had cloth 0.4 mm off. Starting at the skin, a 1 mm
  edge tolerance and 48 views per candidate: worst 0.38% (shorts walk), 0.34% (top jump), both
  rendered and real; occluded up to 9, coincident up to 116. 0.2-0.6 s a sample on Belle.
- **Non-bone vertex groups** (`wd_hide_*` left on the body) were taken for weights in a
  re-run; the file read back clean and the spec hid nothing. Weights are filtered to deform bones.
- **Transferred weights** on the cut shirt's own shape shared a median 98% (5th percentile 82%)
  with the weights it was cut with.
- **Verified over 480 frames of walking with jiggle** (worst sampled frame):
  level 1 holes 1, skin through 10 (right thigh, 0.08%); level 0 holes 1, skin through 5 (left
  buttock, 0.04%). At rest: 0 and 0. Hem peak swing 60 mm, 4 backstop hits.
- **Compression garments** (curvy MPFB woman, 13 380 vertices, 1.76 cm torso edges; improvements
  05 5.3). Eased from the skin the sports top carried 0.13 mm of the breasts' own relief (nipples
  traced: skin relief 0.49 mm, `traced` 0.26); compressed, 0.00 mm and `traced` -0.005. Measured
  again on a body embossed with 12 mm bumps (`traced_detail`), where the limits bite: sports top
  0.192 mm uncompressed against 0.025 mm compressed, compression shorts 0.258 mm against 0.004 mm.
  Surfaces tried and dropped: flattening along skin normals
  folded at the nipple and tore the cloth; flatten after smoothing drew the nipple back to a point;
  full-vector Taubin faded out at the leg openings folded the shorts (skin through); normal-only
  Taubin (per pass) and a final normal projection pinched the cloth over a nipple at 129 passes
  though not at 150; 4 passes of smoothing the move field put the nipples back (0.95). The nearest
  point of the Taubin surface does none of these. Verifier over 6 clips with top + compression
  shorts: worst holes 0.328% (Jump, uncompressed 0.275%), worst poke 0.169%.

## Skirts and dresses (improvements 05 5.4)

Crowd women built by character-pipeline in scratch (Mei slim, Nadia curvy, Rosa BMI 33), Idle/Walk/Run/Crouch,
each preset verified in Godot 4.7.2 for 240 frames every 2 (119 samples, whole cycles), with the `thighs` check.

- **A skirt is built, not cut.** Rays toward a vertical hip axis, hanging from the widest point, a hem sized by
  flare against the widest hip girth (Nadia 1.21 m). Hands at the hips must be left out, fingers included: with
  the finger bones counted as body the "widest girth" was 3.48 m and the skirt a box between the hands.
- **No weight on one thigh; hem bones and colliders instead.** Weighting the tube to the thighs by distance
  keeps the vertex counts low (1/d^6, smoothed: 4 of 1088 inside) and still reads wrong: the cloth follows
  each leg, so a mid-stride front view splits round both legs with a V between them - shorts or culottes, the
  fig224 failure. The presets now pass `thigh=0`; below the hip joints the cloth belongs to 24 hem bones hung
  from the pelvis, hinged 5 cm above the hip joints, and Godot swings them out of capsules fitted to the
  thighs and shins. Above the hip joints the cloth keeps the skin's weights: that band is where an abducted
  thigh comes out into the skirt in a wide squat, and turned with the bones instead it was left inside
  (10-17 vertices on Nadia's mini; 7 of 1088 on her knee skirt's crouch, a fail, when it was tried again).
  Renders bear the `thigh=0` choice out: a mid-stride front view of any of the three women is one tube with
  both legs under it, not a hem split round each leg.
- **The fold, and how it is measured.** Colliders alone cannot dress a deep crouch: the thigh folds up above
  the hinge and no swing about the hinge clears it (the front stood up off the thighs, 120 degrees, or hung
  behind them: 8-30 inside). So what the thighs share carries the ring: the fold turns each bone's head and
  tail about the hip line, as skin on the thigh would. The angle is the arcsine of how far the thigh's tail
  has moved toward that bone's outward direction, not an angle in the down-out plane - that ran to 132
  degrees for a bone beside a thigh swung forward, and neighbouring bones then disagreed by a whole panel.
  At the front the lesser of the two thighs' folds (a stride shares nothing), at the side the nearer thigh's
  (a wide squat), lerped by how far to the side the bone faces.
- **Length.** At 1.05 of the way to the knee the back hem was caught between calf and thigh in a run and a
  crouch (shin 9-14); at 0.85, 0-4. A mini at flare 1.2 put 6 of 704 inside in a crouch; at 1.4, 2.
- **Hide nothing.** Hidden hip skin down to the crotch showed at the front crease; hidden front belly showed
  above the waistband in every crouch (open to up to 12 of 48 views); once the fold moved the hem bones' heads,
  hidden skin at the hips opened too (7 of 24 hidden vertices on Mei's crouch, and 4 of 30 in Rosa's mini's
  run - a fail at 13% of them). A skirt now hides no skin below the hem bones' hinge or facing forward, which
  on the crowd leaves nothing at all - every covered vertex is within the hem's 5 cm edge margin. `hem.prepare`
  raises the cut's `cover_floor_z` to the hinge, since it is the hem bones that move that cloth; leaving the
  floor at the hip joints, where the cut put it, is what let Rosa's mini fail. `spec.validate` allows hiding
  nothing: it only calls covering-without-hiding a weights mistake when the margin does not explain it.
- **The check.** A garment vertex is inside a leg when lines inward, outward and both ways sideways all leave
  skin from inside more than 5 mm off, and the inward one leaves through leg skin. Counting only leg triangles
  called cloth on the belly "inside" a thigh folded up behind the belly skin (20 per crouch frame). Skinned to the
  pelvis alone, the knee skirts crouch with 149-162 of ~1050 vertices inside.
- **The collider has to reach the hip.** Fitted from a third of the way down the thigh, the top 13 cm of it -
  hip joint to first knot - had no capsule at all, and in a run the raised thigh went through the front panel
  above it, which is where the eye looks. The first capsule is now carried up to 0.12 of the thigh at the
  radius it was measured at (Nadia's knee skirt run: poke 21 -> 14, and the bare wedge stops at the hip
  instead of reaching the waistband). Fitting the skin up there instead gives a 14 cm radius - buttock and
  groin - and shoves the skirt off the hips in a stride.
- **What was tried and put back.** Handing the band of cloth over the hip to the bones as well (weights from
  the hinge down, not from the hip joints) lets the capsules push it and takes that run to poke 10, but a deep
  crouch then leaves that band inside an abducted thigh: Nadia's knee skirt crouch goes from 1 of 1088 inside
  to 7, a fail. Folding by the *greater* of the two thighs instead of the lesser clears the raised thigh at
  the top of a stride (poke 4) and opens the other side half a cycle later, where the skirt lifts off the
  trailing thigh. Widening the neighbour spread from 30 to 60 degrees changes nothing visible.
- **Results, worst of walk/run/crouch, every other frame (119 samples, whole cycles).** All 27 runs pass.
  Inside a thigh: skirt_knee 2/1024 (Rosa's crouch, 0.20%), skirt_mini 3/704 (Nadia's, 0.43%),
  dress_sleeveless 6/2420 (Mei's, 0.25%); every walk is 0 and most runs are 0-1. No holes anywhere. Poke at
  most 44 vertices (0.3%), nearly all of it a crouch's thighs past the hem, and on a dress its upper arms at
  the armholes. On the fixture Figure's walk, which crosses the feet over the midline, the mini is 0 of 704 -
  and 47 with `colliders=false`, 46 with `rigid=spine`; the knee skirt there is 12 of 1152 (1.04%, 8 of them
  inside a jiggle bone's flesh) whatever the colliders do, so `regress.py --godot` wears the mini. On a crowd
  crouch the controls are 154 (`rigid=spine`) and 182 (`colliders=false`) of 1024 against 2, and a dress with
  `cut=0.04` opens 39 of its 3278 hidden vertices.
- **What the numbers do not see.** `poke` counts only skin with cloth within 3 cm behind it, so where a panel
  has swung well clear the bare skin it leaves is not counted; `thighs` counts cloth *inside* a leg, and a
  thigh that has come out through cloth leaves little of it inside. At the top of a run stride the raised
  thigh still shows through the front of a knee skirt and a mini on Nadia and Rosa - one of six rendered
  frames, cloth to either side of it - while both runs pass every limit. Judging this needs the renders.
- **Soft route.** Nadia's knee skirt as cotton cloth, 384 pins above the widest hip: verify_cloth passes at
  rest, `move=1.5,0,0` and `bend=spine,x,30` (stretch p95 1.03, max 1.07, pin error 0, settles 0.01-0.04 m/s);
  worn through `Wardrobe.equip` on the walk it builds, stays finite and pinned. No leg colliders.
