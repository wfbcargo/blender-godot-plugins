# Lab notebook: belle-top (branch compression-on-belle, wardrobe)

Task: NEXT.md item 9 - sports_top fails on Belle's real body (0.171 mm traced vs 0.060 limit; 10 drawn tris over cloth after lifts; shelf + wedge under bust).

## 23:10 setup | kind=win
Worktree from main 77408f9, scratch project with characters/belle.toml + build_belle.py + build_human.py + save_guard.py, wf2 patch applied cleanly with `git apply --include=...` (blend redirected to scratch). HUMANFORM_LIBRARY copied (18 MB). ~3 min wall. Env in scratch env.sh.

## 23:12 build Belle to moves in scratch | kind=win
`build_belle.py to=moves force=1` with the patched spec: body 6.2 s, bake 0.1, hair 0.6, flesh 0.8, moves 10.4 s; 21 s wall total, first try. Saved blend in scratch; every probe then opens it and dresses (dress 4.3 s, 11 s per Blender process incl. 3 close renders). Fast loop - worth documenting as THE way to iterate on a garment preset on a real character (character-pipeline SKILL.md: "build to=moves once, then dress the saved blend").

## 23:13 reproduce | kind=win
Probe reproduced NEXT.md item 9 exactly: 0.171 mm traced (limit 0.060), 10 drawn over cloth, lifts 20/7/6/7 tris, top vertex 5.83 mm at (-0.082,-0.169,1.112). Render shows the faceted shelf under each breast.

## 23:15 diagnosis | kind=gap
Probe counting EVERY drawn body vertex in front of the cloth face (front torso only): 11 skin verts at z 1.10-1.14 that cover.compute never marked covered at all (neither hidden nor edge), so `drawn_over_cloth` (which only checks hidden/edge corners) cannot see them and lift_over never targets them. They are the underside of the breast: normals point down AND backward (n.y +0.3..+0.8, n.z -0.5..-0.9), the cloth under them faces forward-up (cloth_n.skin_n -0.4..-0.97), so cover's forward ray, behind ray and nearest-over-face test (needs dot > -0.2) all reject. Meaning: the cloth is tucked INTO the inframammary fold with the breast hanging over it - that is the shelf. The cloth is cut from the skin, so it starts in the fold; 16 relax passes cannot pull it out of a 2-3 cm crease; Taubin compression keeps the crease.
Tried ease iterations=48 / 120 (preset override): 120 gets detail to 0.062 mm and drawn_over 0, but the render shows skin spots through the band and the probe still counts 33 uncovered verts over the cloth. Dead-end as a fix on its own (Jacobi membrane crawls an edge a pass), confirms the direction: the cloth must SPAN the fold.
Plugin to change: wardrobe fit.compress (bridge concave creases), cover.drawn_over_cloth (counts only hidden/edge corners - blind to uncovered skin over cloth).

## 23:17-23:20 attempt 1: bridge the crease in fit.compress | kind=win (partial)
New `fit._bridge` (default off, `ease.bridge` metres): after the Taubin smoothing, each pass raises every region vertex lying below its neighbours' mean out along its normal to that mean (fills hollows only, bulges untouched); passes (reach/edge)^2. bridge 0.06 (10 passes): no effect (raised 9 mm). 0.12 (39): 2.1 cm, still 15 drawn over. 0.25 (169): converges (0.4 gives the same 2.78 cm): drawn_over 0 after ONE lift pass (was 4 passes + 10 left), probe's "any drawn skin over cloth" 0 (was 41 tris), worst cloth relief 1.9 mm (was 5.8). Detail 0.149 mm - still > 0.060. Each Blender probe 11-15 s; two in parallel.
## 23:20 attempt 1b: round the bridge's corner with Taubin | kind=dead-end
WD_BRIDGE_ROUND 0.05 / 0.08 (7 / 17 Taubin passes after the fill): rounding pulls the corner into the breast, more skin over the cloth, 4 lift passes, 8 mm cones, detail 0.263 / 0.154. Reverted to no rounding.
## 23:23 diagnosis 2 | kind=gap
With bridge 0.25 and lifts disabled, 22 drawn tris remain over cloth: corners H/E at breast underside z 1.10-1.17. The E margin comes from 7 UNCOVERED fold-skin verts deep in the crease (normals down and back). They miss cover's tests by thresholds: forward ray hits cloth at 1.5 cm with cloth_n.skin_n 0.23-0.30 (needs 0.3), nearest cloth over face 0.63*d (needs 0.7). Adding an `enclosed` nearest test (side < -0.7 d) changed nothing - same thresholds.
Also tried skin transfer=True (weights from the skin under the eased cloth): no change to lifts; detail 0.139.

## 23:25 found the shelf's real maker | kind=win
Counted cloth faces whose normal turned against their pre-ease normal: after ease 0; after the four lift_over passes 6 (baseline) / 4 (with bridge), all at z 1.11-1.13 under each breast. So the faceted pointed shelf and the dark wedge are lift_over's per-corner 2 cm cones FOLDING the cloth, not ease. Probe tip: record the garment's face normals before ease (wrap fit.ease) and compare after dress - a one-line fold detector wardrobe should report itself (gap: `dress` has no folded-face count).
## 23:26 attempt 2: smooth lift (_lift_smooth: bump (1-(d/R)^2)^2 around each asked cloth tri, relaxed displacement) | kind=dead-end
R 5 cm / 8 cm with gap 2 mm: diverged - drawn-over 22 -> 45 / 109, cloth relief up to 16 mm. Lifting a broad patch exposes more fold and rib skin beneath, and cover then asks for more. Not shipped.
## 23:27 attempt 3: cover `enclosed` + `spanned` skin agrees | kind=dead-end (not needed)
Look for cloth along the nearest cloth's own normal; count such skin as agreeing. Cut drawn-over 22 -> 6 with the bridge. Superseded by settle; reverted.
## 23:33 attempt 4: settle the cloth itself (fit._settle, ease `settle` m) | kind=win
After ease's relax/push loop, Taubin passes over the GARMENT, (settle/edge)^2 of them, each vertex weighted by its compression weight (0 at openings/boundary). push_out held the cloth on the compressed surface, which kept the rim corner; settling lets it round the rim and pass a few mm inside the skin (cover hides that skin, behind=3 cm).
settle only (no bridge, no cover change), Belle probe: 0.03 -> detail all 0.030 mm (traced 0.028), breast 0.053; 0 drawn over cloth; NO lift pass ran; 0 folded faces; inside_skin_verts 18; settle moved max 6.7 mm, 28 passes. settle 0.07: 0.093 mm + one lift (fails). settle 0.05 + bridge: 0.059 (pass by 1 um - too close). Bridge+settle 0.07: 0.045. Chose settle 0.1 alone (simplest; bridge adds margin only below 0.1). Bridge/smooth-lift code saved in scratch fit_with_bridge_and_smoothlift.py, not shipped.
Render: shelf and wedge gone, underside rounded; the rim still reads as a polygon line in the 3/4 Workbench view (body mesh is 1.9 cm edges).
Wall: 4 approaches in ~20 min thanks to 11-15 s probes run two at a time.

## 23:40 pipeline build with settle 0.1 | kind=win
`build_belle.py renders=...` (no force): every stage re-ran anyway (body 6.6 s ... garments 4.8, export 7.1, review 6.3; 45 s wall). read_back PASSED. The garments stage passed on the preset (it raises otherwise).
## 23:44 Godot verify_wardrobe, 21 runs | kind=fail
Scratch Godot project (project.godot with Jolt, addons rig_anything/wardrobe/follow_through copied from the worktree, Belle's glbs): import 4 s, each verify 15 s, 21 runs with xargs -P 4 in 106 s.
shorts: 7/7 pass (worst holes 0.39% Walk). both: 7/7 pass (worst holes 0.477%, poke 0.230%). top: FAILS holes on Idle 0.626%, Walk/Trot/Run 0.521%, Jump 0.730% (limit 0.5%); Crouch 0.417, CrouchWalk 0.104 pass. All holes on spine.003: 6 hidden verts at the fold under the breasts (Godot y 1.11-1.13, z 0.13-0.15), 1-3 of 48 views open. `trace=holes` + windowed `shot=16 shot_dir=` gave the evidence (shot run works without --headless, ~10 s).
Cause: settle pulls the cloth inside the breast rim; cover's behind-ray from a fold vertex (normal down and back) goes up into the breast, meets that cloth and hides the fold skin - but the fold still has a line of sight out below the rim (verifier: tilt_up "line_to_camera open"). The old top left that skin drawn.
Also noticed: in build_belle's outfit renders (Workbench) Belle's head reads bald with a dark goatee-like patch - the bun preset's hair cap does not render there. Not wardrobe; flag for humanform/lookdev.

## 23:50 character-pipeline: garments stage "unchanged" after a preset edit | kind=gap
Editing wardrobe's presets/garments.json (sports_top ease) and running `build_belle.py from=garments` on the saved blend reported `garments: unchanged` and re-used the old garment: the stage's input hash does not include the preset's contents (nor wardrobe's version/code). A preset change reaches a character only with force=1. Also: running build_belle.py WITHOUT opening the saved .blend silently rebuilds from body (45 s) - `from=garments` then refuses, which is how I noticed. Plugin to change: character-pipeline stages.py garments hash should include presets.get(g.preset) for each outfit entry (and the wardrobe plugin version).

## 23:47 bridge back in to fix holes | kind=dead-end
bridge 0.25 + settle 0.07 -> garments stage fails detail 0.079 in the pipeline (probe said 0.045 but that run also had the cover `enclosed` test). bridge 0.25 + settle 0.1 -> same holes as settle alone (5-7 fold verts). Bridge code removed for good (kept in scratch fit_with_bridge_and_smoothlift.py).
## 23:49 hole probe | kind=win
Blender-side check of the five fold verts the verifier flagged (Godot (x,y,z) -> Blender (x,-z,y)): all hidden by cover's nearest-cloth "cleft" test, cloth 8-15 mm OUTSIDE them facing the same way, normals down and BACK into the fold. A Workbench render from 40 deg below shows no hole to the eye; Godot's view test still sees in at 1-3 of 48 views (grazing along the fold). Did not change the verifier (would be loosening by another name).
## 23:52 attempt 5: cover `crease` | kind=win
Covered skin whose own normal line meets other body skin (facing back at it) within 3 cm stays drawn and seeds no margin. Godot: top holes 0.52-0.73% -> 0.000-0.33%, all 7 clips pass. But now 10 drawn tris lie over the cloth -> per-corner lift ran twice and the pointed shelf came back in the render (detail 0.051).
## 23:54 attempt 2 again: smooth lift, now that few tris need it | kind=win
_lift_smooth radius 4 / 6 / 8 / 12 cm, gap 2 mm: detail 0.082 / 0.063 / 0.057 / 0.044, no folded faces, 2 passes, drawn over 0. The earlier divergence (23:26) was lifting a much larger set; with crease only 10 tris need it. Chose 12 cm.
## 00:00 final config through the pipeline | kind=win
sports_top: ease.settle 0.1, cover.crease 0.03, lift {smooth 0.12, gap 0.002}. build_belle.py from=garments force=1 on the saved blend: garments 4.8 s, whole call 22-27 s. Belle detail 0.044 mm (limit 0.060 unchanged), breast 0.064 (no limit), 0 folded faces, 0 drawn over cloth. verify_wardrobe 21/21 pass: top worst holes 0.328% (Jump), poke 0.257% (Trot); shorts worst holes 0.392% (Walk); both worst holes 0.211%, poke 0.267%. cut=0.04 control on the top still fails (holes 1.31%). Godot verify of 21 runs: 91 s at -P 4.
Close renders (pipeline blend, hidden skin removed): no skin through, no wedge, underside rounded; the rim under each breast still reads as a crisp polygonal line in 3/4 Workbench view (body/cloth edges 1.9 cm) - improved, not perfect.
## 00:02 fixtures | kind=win
traced_detail gains top_pressed_cone_lift (old cone path) beside top_pressed (smooth): 0.038/0.058 mm over 3 lifts vs 0.003/0.0 over 2. dress reports folded_faces (0 everywhere on the sample figure - the fixtures' figure has no fold deep enough to fold under cones; only Belle does). `--only traced_detail dressed_presets --twice --update`: 1 m 49 s. Goldens reviewed; --update wrote a new temp path into dressed_presets (known item 8 noise), put back by script.
## gap: no fixture has a bust fold like Belle's | kind=gap
Every regression body is the smooth sample Figure or an MPFB curvy woman with a light bust; none reproduces an overhanging inframammary fold, so creased stays 0 and folded_faces 0 in all fixtures. The real proof is Belle in scratch. A generator for a heavy-bust figure (seeded, e.g. follow-through samples with a breast-size parameter) would let a fixture hold `creased > 0` and the smooth lift under a fold. Plugin: follow-through samples.build_bodies or humanform fixture body.

## 00:22 full regress --twice --jobs 2 | kind=slow (win)
All 17 fixtures ok, each built twice and agreeing, "no change" against the goldens (committed c4f4cb3). Wall ~16 min; rabbit (261 s x2) and cricket (169 s x2) dominate. No --godot run (forbidden for this agent); the Godot half was the 21 hand runs on Belle in scratch.
## summary of stage wall times
build Belle to moves 21 s; probe (dress + 3 renders) 11-15 s; pipeline from=garments force=1 22-27 s; Godot import 4 s; verify_wardrobe 15 s/run, 21 runs 91-106 s at -P 4; --only 2 wardrobe fixtures --twice 1 m 49 s; full --twice 16 min. Whole task ~75 min.
## open
- Rim under Belle's bust still reads as a crisp polygon in 3/4 Workbench (mesh resolution) - improved, not gone.
- Belle's breast-region relief 0.064 mm (no limit on it; `all` 0.044 under 0.060).
- compression_shorts / leggings do not ship settle/crease/lift; untested on Belle's body.
- character-pipeline garments hash ignores preset contents (see 23:50).
- no heavy-bust fixture (see gap above); grungist-creek belle.toml patch not applied (not this agent's scope).
