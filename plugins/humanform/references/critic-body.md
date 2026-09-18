# Body critic checklist (a round's pick list)

Questions a round's done-when and its body critic **pick** from. The protocol, the JSON a critic returns, how
to read `body.png`, the layer-by-layer question bank and the keep-or-revert rule are `critic-checklist.md`'s,
and this file does not repeat them: it gives the questions a round asks most an id, names the finding,
tile or view that answers each, and adds the views a built character has beyond humancheck's sheet (the
pipeline's Blender close set and lookdev's Godot close-shot). Every question is yes/no with `yes` good. A
number outranks a picture; `unclear` when the source named is missing.

## Sources

| name | what | how |
|---|---|---|
| **humancheck.json** | `counts` (pass/warn/fail/info) and `findings`, each with `id`, `layer`, `status`, `value`, `target`, `tol`: proportion ids `chin`, `shoulder_joint`, `hip_joint`, `crotch`, `knee_joint`, `ankle_joint`, `upper_arm`, `forearm`, `hand`, `thigh`, `shin`, `foot`, `shoulder_width`, `hip_width`, `heads`, `shoulder_to_hip_width`, `waist_to_hip_circ`; rig `hip_above_crotch`, `elbow_centering`, `knee_centering`; features `fingers.L`, `fingers.R`, `face`; pose `arm_rest_angle`, `floor`; mesh `symmetry`, `quads`, `components`, `manifold`, `normals`, `scale`; surface `uvs`. Present only as a `fail`: `legs_parted`, `facing`, `left_side`, `landmarks` | `blender -b <file> --factory-startup --python <plugin>/scripts/humancheck_cli.py -- body=<mesh> sex=<sex> out=<scratch> views=1` (or `mpfb=female` for a fresh body); in the open session `measure.run` |
| **body.png** | rows `clay`, `normals`, `silhouette`; columns `front`, `front_left`, `left`, `back`; orange target and cyan measured landmark lines | written by `views=1` beside humancheck.json, with `views.json` |
| **closeups.png** | face front and left, the left hand from its back, the left foot from above-front, each clipped to itself | as body.png |
| **hair.png** | the head lit and in colour, 1 m row and close row | as body.png, on a haired body |
| **B:`<view>`** | the pipeline's Blender close set of the posed character (Idle, first frame) | `<export dir>/review/<id>/close/<view>.png`: `face`, `face_3q`, `eyes`, `head_side`, `head_back`, `hand_palm.L/.R`, `hand_back.L/.R`, `bust`, `crotch`, `knees`, `feet`, `foot_inner.L`, `foot_outer.L` (+ `under_bust`) |
| **G:full** | the whole figure in Godot at 4 m, lookdev materials | `lookdev.mjs close-shot --project . --glb <glb> --views full --presets clear_midday` |

## Question bank

### Proportions and scaffold (L1-L2: block everything else)
- **BODY-P1** Does humancheck find no `fail` - `counts.fail` 0? *humancheck.json* (each `fail` is then a
  question of its own, by its `id`).
- **BODY-P2** Is the crotch at the preset's height and the hip joints inside the pelvis - `crotch` and
  `hip_above_crotch` `pass`? *humancheck.json*; *body.png* `silhouette`, `front` (cyan tick on the orange dash).
- **BODY-P3** Is the body about the preset's head count - `heads` `pass`? *humancheck.json*.
- **BODY-P4** Do the limb segments match the preset - `upper_arm`, `forearm`, `hand`, `thigh`, `shin`, `foot`
  `pass`? *humancheck.json* (a fresh MPFB female reads `upper_arm` and `foot` `fail`: a default, not a bug).
- **BODY-P5** Female: hips at least as wide as the shoulders; male: shoulders clearly wider? *humancheck.json*
  `shoulder_to_hip_width` (`info` on a non-average build is expected); *body.png* `silhouette`, `front`.
- **BODY-P6** Are the legs parted and the arms clear of the torso, both feet on one floor line - no
  `legs_parted` finding (it is written only as a `fail`), `arm_rest_angle` and `floor` `pass`? *humancheck.json*;
  *body.png* `silhouette`, `front`.
- **BODY-P7** Is the mesh sound - `normals`, `manifold`, `components`, `uvs` `pass`? *humancheck.json*.
- **BODY-P8** Do the rig's elbow and knee joints sit inside the limbs - `elbow_centering`, `knee_centering`
  `pass`? *humancheck.json*.

### Forms (L3-L4)
- **BODY-F1** Do the ribcage and pelvis read as two masses tilted against each other, with a waist between
  them? *body.png* `clay`, `left` and `front`.
- **BODY-F2** Are the clavicles, sternum notch and a deltoid cap readable? *B:bust*; *body.png* `clay`,
  `front_left`.
- **BODY-F3** Are the kneecaps readable? *B:knees*.
- **BODY-F4** Four separate fingers and a thumb on each hand, with knuckles - `fingers.L`, `fingers.R` `pass`?
  *humancheck.json*; *B:hand_back.L/.R*, *B:hand_palm.L/.R*; *closeups.png*.
- **BODY-F5** Heel, arch and toes in order, the big toe largest; the inner ankle bone higher than the outer?
  *B:feet*, *B:foot_inner.L*, *B:foot_outer.L*; *closeups.png*.
- **BODY-F6** Does the face have relief - nose, lips, eye sockets and brow - with the eyes at about half the
  head's height and the ears between the brow and the nose base? *humancheck.json* `face` (the nose's stand-out);
  *B:face*, *B:face_3q*, *B:head_side*; *closeups.png*.
- **BODY-F7** Is the crotch as the spec asks (smooth today; genital anatomy when Step 3 lands), with the inner
  thighs apart? *B:crotch*.
- **BODY-F8** Is the surface free of lumps, dents, faceting and seams that are not anatomy? *body.png*
  `normals`, every column; every *B* tile.

### Whole figure
- **BODY-W1** Is the face and body free of mirror-perfect symmetry, and is `symmetry` still `pass` (no
  lopsided build)? *humancheck.json* `symmetry`; *B:face*.
- **BODY-W2** Does the figure read as the brief's age, sex and build at full body in Godot? *G:full*.
- **BODY-W3** With hair, does it pass humanform's L6 hair questions (`critic-checklist.md`)? *hair.png*;
  Godot-side in lookdev's `references/critic-look.md` (LOOK-H).

## Not answerable from these today

- A posed limb clearance - the thighs passing into each other or into the crotch in Crouch, Jump and Run
  (Step 3's finding) - has no number yet (06 rank 10: a posed clearance check in humancheck). The strips
  show it (`animate-anything/references/critic-motion.md` MOT-S1).
- The close sets are one posed frame of the Idle; humancheck's sheet is the rest pose. A defect only in a
  pose is a motion question.
