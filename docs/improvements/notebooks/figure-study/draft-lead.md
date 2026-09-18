# draft-lead notebook (figure study, draft build)

Worktree: C:/Users/pauli/Code/blender-godot-plugins/.worktrees/figure-draft (branch figure-draft at main b496738; read-only use, no plugin edits).
Scratch: scratchpad/wf3/draft

## 00:26 setup - kind=win
- Read repo CLAUDE.md, NEXT.md items 8-9. Worktree created in 1 attempt. ~3 min.

## 00:30 stage=inventory - kind=gap
- What: MPFB2 asset inventory for genitalia, brows, lashes, body hair.
- MPFB2 extension data (extensions/user_default/mpfb/data) ships only `targets/genitals/penis-{length,circ,testicles}-{incr,decr}` and `targets/eyebrows/*` (shape targets for the base mesh), plus base.obj. The MPFB *user* asset dir (extensions/.user/user_default/mpfb/data) is EMPTY: no asset packs installed, so no eyebrow/eyelash proxies, no genital proxies, no skins, no body-hair assets.
- humanform: no code mentions genitals except muscle.RELIEF_EXCLUDE ("genitals" vertex group), no brow/lash layer; views.AUTO_INCLUDE lists "brow","lash" names only.
- follow-through builtin.json flesh types: breast, belly, bloater_belly, butt, love_handle, thigh, arm_flab. No genital type.
- rig-anything biped move_set roles: Idle Walk Trot Run Crouch CrouchWalk Jump Slide SlideRecover SlideToCrouch. No Turn.
- Should change: humanform (brows/lashes/genital geometry), follow-through (genital flesh type), rig-anything (Turn role).

## 00:28 stage=build study_man (draft) - kind=win
- First attempt, rc=0, wall 27 s (pipeline 24.4 s: body 6.3, muscle 2.4, bake 0.2, hair 0.5, flesh 1.1, moves 7.4, export 3.8, review 1.8). moves+export+review = 13.0 s of 24.4 (53%): rig-anything has no draft setting (known, NEXT.md).
- Flesh found butt.L/R and belly. follow-through flesh.py:474/397/521 print numpy RuntimeWarnings (Mean of empty slice / All-NaN slice) - noise in the log that looks like a failure; flesh.py should guard empty rings.
- glb: skin material is baseColorFactor only (no texture, no normal map, no SSS/transmission extension). Only the hair carries textures.

## 00:29 stage=build study_woman (draft) - kind=win / gap
- First attempt, rc=0, wall 25 s (pipeline 22.1 s: body 3.0, muscle 0.8, bake 0.2, hair 0.6, flesh 1.2, moves 8.6, strand 0.2, export 5.0, review 2.3). Ponytail chain (5 strand bones) exported as study_woman_hair.glb.
- gap: spec asked flesh types breast, butt, belly; only breast.L/R and butt.L/R bones came out. The belly was dropped with no line in the log or manifest (manifest `flesh` key is null for both). A requested type that finds no mass should be reported (character-pipeline stages.run_flesh / follow-through flesh.find).
- All 5 clips pass clip_checks on both; verify.arm_swing passes (no Run failure like Dante).

## 00:33 stage=humancheck - kind=win
- humanform/scripts/humancheck_cli.py on both saved blends, first attempt, 10 s + 9 s.
- StudyMan_body 1.791 m: 0 fail, 2 warn, 30 pass (8 pieces, 120 open edges - eyes/hair pieces). StudyWoman_body 1.675 m: 0 fail, 2 warn, 30 pass (7 pieces, 110 open edges). Proportions are fine; the gaps are all surface/anatomy/motion, not L1.
- Output: draft/hc/{man,woman}/{body,closeups,hair}.png

## 00:35 stage=look (review strips) - kind=friction
- Draft review sheet is front-only, 5 small clay strips (~490 px wide) - too small to judge hands, face or flesh. Had to write my own EEVEE lit render script (draft/look/lit.py, 6-7 s per body). A lit colour close-up set (face, crotch, walk side) belongs in the review stage or humancheck (character-pipeline review / rig-anything review.sheet).

## 00:38 stage=inventory genitals - kind=win (finding)
- MPFB base.obj carries `helper-genital`: 200 verts (15128-15327), 182 quads, a closed shaft+scrotum shell ~6 x 9 x 9 cm sitting on the crotch (render: draft/look/helper_threeq.png). The six penis-{length,circ,testicles} targets touch only these verts (105/49/78 each). humanform masks helpers and the bake applies the mask, so it is deleted: the built man's crotch is smooth (draft/look/StudyMan_crotch.png). Nothing reaches rig, weights, flesh or glTF.
- Also in base.obj: helper-l/r-eyelashes-1/2 (44-48 quads each) - lash card helpers, also deleted. No brow helper (MH eyebrows are proxies from asset packs, not installed).
- Female: the base crotch has only a shallow mons cleft (draft/look/StudyWoman_crotch.png).
- Precedent: humanform/eyes.py already reads helper-l/r-eye before the mask is applied. A genitals/lashes module can do the same.

## 00:40 stage=look (lit renders) - kind=gap
- Skin: one flat Principled colour (humanform/look.py docstring: "flat colours ... no subsurface, no texture"); glb skin material = baseColorFactor + roughness only. Lips, nipples, palms, knees same colour as everything. Reads as plastic/clay.
- Face: no brows, no lashes; eyes read dead. Hair cap's strand texture runs over the tops/backs of both ears (hair.png close side view, both figures).
- Motion: in Walk (side, quarter frame) both figures have fingers splayed flat at MPFB rest and palms half forward; knees deeply bent at mid-stance, reads as a shuffle. moves.json: Walk natural_speed 1.154 m/s but implied_speed_mps 0.818 (man), Froude asked 0.2 got 0.147. Same pattern on shipped Belle (0.80 vs 1.18) and Nadia (0.82 vs 1.26), so systemic. No Turn role in rig-anything biped move_set.
- Flesh: woman's belly silently missing (see 00:29).

## 00:45 stage=wrap - kind=friction
- No plugin code changed in this step, so nothing to commit on figure-draft and no regress run (it would only re-test main b496738, which passed 19/19 at merge). Worktree .worktrees/figure-draft left for the gap agents / merge agent to remove.
- Total wall for the draft study: ~20 min; builds 27 s + 25 s, humancheck 19 s, renders 13 s. Every stage < 60 s (no kind=slow).
