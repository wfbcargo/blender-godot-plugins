# belle-ship lab notebook

## 01:48 setup - win
- stage: setup. Backed up belle_realistic.blend (md5 adf8fdff...) and the committed belle glbs/manifests to scratch belle-ship/{backup,before}. Installed plugins match blender-godot-plugins main cfeae92 (wardrobe 0.5.0, cp 0.6.0, humanform 0.8.0, ft 0.6.0, ra 0.23.0, lookdev 0.2.0), so the build uses the installed copies; no worktree needed (no plugin code change).
- belle_spec_ready.patch (wf2) applied cleanly with `git apply` (belle.toml bun + Trot arm_forward -17, build_belle docstring, .gitignore assets/**/review/). 1 attempt, <1 min.
- HUMANFORM_LIBRARY redirected to a scratch copy (18 MB) so the ship build cannot write the real library.

## 01:48-01:49 build - win
- stage: build (build_belle.py force=1 renders=..., HUMANFORM_LIBRARY=scratch copy). Every stage ran first time: final build 26.7 s (body 4.0, bake 0.1, hair 0.4, flesh 0.7, moves 8.8, garments 3.3, export 4.4, review 4.6), 31 s wall with renders. read_back PASSED (20832 verts, 4 jiggle bones). No garments failure: wardrobe 0.5.0's spanned sports_top passes on her own body, and the Trot arm_forward -17 passes verify.arm_swing. Saved belle_realistic.blend through the scene guard.
- The review dir (4.3 MB, assets/belle/review/) is now ignored by the patch's .gitignore line - git status stays clean of it.

## 01:50 hair material in Godot - gap
- belle.glb's Belle_hair material now carries lookdev extras (anisotropy 0.5, rim, backlight, transparency 4, tangents per_face) + KHR_materials_anisotropy/specular (Godot ignores both). The project had no addons/lookdev and nothing called LookdevMaterials.apply, and belle_controller._skin_materials overwrote the hair surface's roughness (0.45) and backlight by hand - so without a change the preset would be silently half-lost in game.
- Resolution: copy plugins/lookdev/godot/addons/lookdev into the project, call LookdevMaterials.apply(_model) in belle_controller._setup before wardrobe (wardrobe matches hidden skin by position and rebuilds from the same source mesh, so the hair surface's de-indexing first is safe), and let _skin_materials keep a lookdev-applied material as is.
- Should change: character-pipeline SKILL.md / lookdev SKILL.md should say that a `[hair] preset` character needs the lookdev addon in the game project and an apply call in its controller; ideally the pipeline's export (or a project-sync check like the addon drift warning in regress --godot) flags a glb with lookdev extras when addons/lookdev is missing.

## 01:50-01:51 Godot import + self-tests - win
- --headless --import: 3 s, exit 0 (only the pre-existing tomas_demo.gd missing-script error from the untracked tomas_demo.tscn). Import extracted the hair's two embedded textures to assets/belle/belle_Belle_hair_strands{,_normal}.png(+.import) - new files to commit.
- belle_demo -- --selftest PASSED first time, 21 s: flesh breast 7.6/8.7 % on the limit (before 7.6/9.0), butt 8.1/7.8 % (before 8.6/8.4), max = limit 0.078/0.073 m, 4 rolls, lowest bone 0.109 m. New HAIR line (added to the self-test this session): lookdev set ["Belle_hair"], retangented belle_Belle_body, drawn material anisotropy 0.5 rim 0.25 transparency 4 (depth pre-pass) OK.
- people_demo -- --selftest PASSED, 40 s (crowd unchanged).

## 01:52-01:53 verify_wardrobe 21 runs + control - win / friction
- 7 clips x top/shorts/both, xargs -P 4, 98 s wall total. 21/21 pass, 59 samples each. Worst holes 0.392 % (Walk shorts, 2 verts), worst poke 0.312 % (Run/Trot both, 41 verts). Before (committed build, old top): worst holes 0.39 %, poke 0.24 %; wf2 scratch build on wardrobe 0.5.0: 0.39 / 0.30.
- cut=0.04 control (Walk both) FAILS as it must: holes 2.64 % (36 verts, frame 16).
- friction: verify_wardrobe.gd exits 0 whether or not it passed (the control too) - a caller has to parse WD_RESULT JSON. Should change: wardrobe/verify_wardrobe.gd quit(1) on passed=false (as belle_demo's selftest does), cheap and makes shell loops honest.
- friction: clip names are Belle_<Role>; a spec-level `clip=Walk` alias would save a lookup (wardrobe verifier could accept a role and resolve `<Name>_<Role>`).

## 01:53-01:57 look: review strips, Blender close renders, Godot close shots - win / gap
- Review strips (assets/belle/review/belle, 21 strips + contact, 4.3 MB): Trot front shows arms carried by the sides and coming back to hanging; Run side shows the bun and arms swinging behind the body. No body against an edge (review stage passed).
- Blender workbench close renders (wardrobe views, scratch belle-ship/close vs close_before, 6 s each): the new top is compressed - nipples gone, cloth spanning the cleavage and the underbust in one sheet, where the old top wrapped each breast separately with nipples showing. Remaining: a faint pointed facet at the outer-lower corner of each breast (already recorded in NEXT.md), and ragged neckline/armhole edges that were there before too (open: wardrobe cut edge is not smoothed).
- gap: workbench renders draw the joined hair cap in skin colour, so the hair cannot be judged in Blender close renders. Wrote a 40-line windowed Godot SceneTree script (scratch belle-ship/hair_shot.gd: load glb, LookdevMaterials.apply, Wardrobe.equip, sky + sun, four cameras, save png) - ran first time, ~15 s. Side and back shots: dark brown strands with an anisotropic sheen along the strands, a swirl bun at the crown, hairline fading into skin at the temples and nape (depth pre-pass), no dark facet polygons. My yaw was wrong (rotation.y = PI faces her away from +Z), so "front" shot the back of the head - cost 0 extra runs but the face-on hairline was not shot.
- Should change: lookdev should ship this as a tool (`lookdev/godot/close_shot.gd body=... garment=... focus=head|torso`) - a Godot-side close render of a character as the game draws it, which the review sheet (Blender workbench) cannot give for lookdev materials.

## numbers before -> after (manifest)
- collider.height 1.7062 -> 1.7129 m (+6.7 mm: the bun on top of the head; stand 1.6998 unchanged, as NEXT.md predicted "a hair bun would widen that").
- manifest gains arm_pose, build, flesh blocks. Trot arm carry -0.8..45.9 deg (swing 46.7), Run 0.5..53.2, Walk -11.8..36.4, Idle 9.1..11.1 (swing 2.0, under SWING_MIN - the idle dead band in NEXT.md item 8).
- breast max_offset 0.0781/0.0779 m (unchanged).

## 01:59 commit - win
- grungist-creek master d02f953 (not pushed), own files only; tomas_demo.tscn left untracked. The real belle_realistic.blend was saved by the build through the scene guard (backup in belle-ship/backup, md5 adf8fdff...).
- regress.py --twice not run: no plugin code changed in this task (ship-only, built on installed copies that equal blender-godot-plugins main cfeae92), so the suite would test nothing this task touched.
- Total wall time ~12 min. Nothing needed more than one attempt.

## open items for the plugins
1. lookdev / character-pipeline: a [hair] preset character silently needs addons/lookdev + an apply call in the game controller; nothing checks it. (lookdev SKILL.md, character-pipeline SKILL.md "Belle" worked example; regress --godot drift warning could list addons/lookdev.)
2. wardrobe verify_wardrobe.gd: exit code is 0 on a failed run; make it quit(1).
3. wardrobe: sports_top neckline/armhole edges are ragged (visible in close renders before and after), and a faint facet remains at each breast's outer-lower corner.
4. lookdev: a Godot-side close_shot tool (hair cannot be judged in workbench review sheets).
