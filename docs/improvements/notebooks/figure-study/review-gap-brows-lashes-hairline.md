# Review: fig-brows-lashes-hairline

## 01:32 | setup | win
Read diff stat: 14 files, +1084/-93; commits 6a49d9c, b4aa866. 1 attempt, <1 min.

## 01:33 | scratch setup | friction
Copied build_human.py, save_guard.py, draft hflib, and the two draft specs into review-.../build. I added `brows = true` and
`lashes = true` under [hair] and sed-pointed `[export] blend` at my scratch. 1 attempt, ~2 min. This is the same
friction as the earlier reviews: the absolute blend path in a spec makes copying it unsafe. Change: character-pipeline
spec.py should accept `blend` relative to BLEND_DIR.

## 01:34 | pipeline build, both figures, branch code | win
study_man: rc=0, 20 s wall (body 4.8, muscle 0.6, bake 0.1, hair 0.5, flesh 0.9, moves 6.8, export 3.3, review 2.4).
study_woman: rc=0, 22 s. Worked first time.
glb check (python on the JSON chunk): each glb has one mesh with the materials _hair (MASK, transparency 4), _brows
(MASK, godot transparency 2, not double-sided) and _lashes (MASK, doubleSided true, transparency 2). All carry base colour and
normal textures plus lookdev extras. Vertex counts: brows 128, lashes 250 (man and woman); hair 720 (short_crop) and 934 (ponytail).
The logs contain 3 flesh.py RuntimeWarnings (empty slice), a known item on main, unrelated.

## 01:36 | humancheck, both figures | win
Adapted the implementer's hc.sh to my scratch. Both ran in parallel in about 15 s. Results:
- StudyMan: 0 fail, 2 warn, 30 pass. Pieces 14 (draft on main: 8), open edges 396 (main: 120).
- StudyWoman: 0 fail, 2 warn, 30 pass. Pieces 13 (main: 7), open edges 410 (main: 110).
The extra pieces are the 2 brow and 4 lash cards. The extra open edges are the card borders and the ear holes in the cap.
The warnings are the same kinds as on main, but humancheck's piece and open-edge WARN does not know that cards are expected.
Change: humancheck mesh-health should count parts tagged humanform_hair separately.
hair.png (hc/man, hc/woman): brows and lashes are visible, and the ears are clear in both side close-ups on both figures. First try.

## 01:37 | derive_face_regions.py reproducibility | win
Re-ran the generator with out=<scratch>. It took 2 s, and the output is byte-identical to the committed data/face_regions.json.
Friction (docs): the module docstring describes the ear set as "standing out from the skull by more than EAR_OUT_M ... grown
from the vertex that moved most", and says the ear targets cannot say where an ear ends. The code has no EAR_OUT_M and
selects ears by EAR_TARGETS (flap, wing, lobe) at more than EAR_SHARE of each target's maximum, which the docstring calls
unusable. This is a stale docstring from a dead end. Change: humanform derive_face_regions.py docstring.

## 01:38 | Godot scratch project (my own, lookdev addon copied from the worktree, my glbs) | win
Import took 3 s and the render 5 s (window mode). LookdevMaterials.apply returned materials [hair, brows, lashes] with skipped 0.
brows: transparency 2 (scissor 0.5), cull 0, albedo texture present. lashes: scissor, cull 2 (disabled), albedo texture present.
Shots are in review-.../gshots. The cards are strand-shaped silhouettes, not rectangles, so there are no black cards. The woman's ear is clear.
Quality (not blocking): in Godot, with the face in shadow, the brows read near-black and hard-edged. The lower lashes read as a
thick dark band, like eyeliner, and look heavier than in Blender's Cycles/EEVEE close-up. The implementer disclosed this.
Change: humanform brows.py LOOK["lashes"] and LOWER_LASH in derive_face_regions.py (thinner, shorter lower card).

## 01:40 | code read: spec/hash, stage, consumers | win + gap
- The spec hash for a switch left false is the same as before (the switch keys are popped). The fixture's
  switch_off_same_digest is true. A bad value is refused with "hair.brows must be bool, not str".
- hair.add gains the keyword arguments brows/lashes/body_hair/sex. It has one caller outside humanform
  (character-pipeline stages.run_hair), and that caller is updated. landmarks() gains _ear_kd (a KDTree) and _ear_vertices. The fixture's
  _stable_rep whitelists keys, so the KDTree never reaches JSON.
- gap: the ear cut is on for every build, but the hair stage's input hash does not change, so a character built
  before this change (Belle) keeps its old cap until [hair] or body changes. That is acceptable, but the NEXT.md note should say so.
- gap: brows.is_mpfb is `len(vertices) >= 13380`. Any denser non-MPFB mesh would pass and get the ear cut and cards at
  arbitrary indices. humanform bodies are always MPFB, so this is not blocking. Change: humanform brows.is_mpfb should also check that a
  few base-mesh edges or the vertex count of the first connected piece is 13380 (humancheck already reports "largest [13380, ...]").
- friction (docs): SKILL.md and the brows.py docstring say the brow card is "16 x 4". Those are vertices (15 x 3 = 45
  quads a side, 90 faces total, as the golden records), not quads. Change: humanform SKILL.md.
- The humanform SKILL.md figure "Measured on Belle (bun): cap from 1054 body faces ... the ring round each ear"
  (line 316) is now stale, as the implementer disclosed.

## 01:41 | merge check against current main | win
main moved past the branch base b496738: flesh reporting (character-pipeline spec.py and stages.py, 0.6.0) and wardrobe 0.5.0.
`git merge-tree --write-tree main fig-brows-lashes-hairline` shows no conflicts (tree 8fe58c3). I extracted the merged tree into
review-.../merged to run fixtures on it.

## 01:43 | regress --only hair_presets pipeline_ponytail pipeline_muscle --twice --jobs 3 (branch) | win / slow
Result "no change", rc=0, 88 s wall. Per fixture: hair_presets 22+22 s, pipeline_ponytail 24+23 s, pipeline_muscle 61+63 s (slow).
The builds agreed with each other and with the goldens. First try.

## 01:45 | regress on the MERGED tree (main + branch, git archive of merge-tree 8fe58c3) | win
`--only hair_presets pipeline_ponytail pipeline_muscle --jobs 3`: result "no change", rc=0, 62 s. Per fixture: hair_presets 24 s,
pipeline_ponytail 26 s, pipeline_muscle 62 s (slow). Versions on the merged tree: character-pipeline 0.6.0, follow-through 0.6.0,
wardrobe 0.5.0. Main's flesh-reporting changes do not interact with the ear cut or the switches, and main changed no fixture
that uses hair (grep: only hair_presets, pipeline_muscle, pipeline_ponytail and strand_ponytail mention hair). First try.

## 01:47 | ear coverage on the real pipeline builds (my own probe, ear.py) | win
Stage reports are not stored on the object, so I could not read cap.ear_covered_verts from the .blend. I wrote an independent
probe instead. It takes the face_regions ear vertices whose normals face outward, casts a 2 cm ray along each normal, and tests it
against every face with the _hair material in the joined body.
- Branch builds: StudyMan 0 of 434 covered; StudyWoman 4 of 434.
- Draft builds from main (control): StudyMan 347 of 434; StudyWoman 334 of 434.
The woman's 4 are probably from the ponytail's tie/fall faces or from my crude head-centre heuristic, since the fixture metric
counts only the cap. 2 attempts: the first tried to read the stage report from object properties and found nothing. ~3 min.
Change: character-pipeline should keep each stage's report on the .blend (or in the manifest next to the glb), so
a reviewer can read cap.ear_covered_verts without re-measuring.
