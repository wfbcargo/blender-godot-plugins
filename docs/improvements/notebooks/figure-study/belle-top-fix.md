# Lab notebook: belle-top-fix (branch compression-on-belle, wardrobe) - fix-up after review

## 00:33 setup | kind=win
Copied review-belle-top/proj (patched belle.toml, blend path in review's scratch -> re-pointed below) and hflib into belle-top-fix/. 1 min.

## 00:35 blocking 1: fit.py CRLF | kind=win
fit.py had 1062 CRLF + 9 "\r\r\n". Rewrote bytes with LF (python replace), added `*.py text eol=lf` to .gitattributes. `git ls-files --eol`: i/lf w/lf attr/text eol=lf. Diff vs base 77408f9: +105/-3 (was +1062/-960). Committed. 1 attempt, 2 min.
Change: the earlier agent's writer produced CRLF+CR; .gitattributes now prevents it. A regress.py pre-check for "\r" in tracked .py would catch it before commit.

## 00:36 build Belle to moves in scratch | kind=win
belle.toml (patched: bun, Trot arm_forward -17) with blend path in my scratch. `build_belle.py to=moves force=1`: 20 s wall, first try. Saved copy belle_moves.blend; probe.sh re-dresses sports_top on it with preset overrides from WD_OVERRIDE json and renders 9 tight views (focus (0,-0.12,1.11), 0.42 m, el 8/-20/-35) into a contact sheet: 8-10 s per probe, two in parallel. (No PIL in system python: made the sheet inside Blender from bpy image pixels.)
## 00:38 baseline (branch head c4f4cb3 preset) | kind=win
0.044 mm, lifts 10/4 tris, 0 folded. Tight sheet p/p0/sheet.png: faceted polygonal rim under each breast, each breast wrapped separately, deep cleavage - reproduces the review.
## 00:40 attempt 1: span to the convex hull of the cloth (fit._span, ease `span` share) | kind=dead-end (full) / partial
bmesh.ops.convex_hull of the eased cloth; 24 passes of relax + push each weighted vertex (1-floor) out to the nearest hull facet. share 1.0: detail 0.000, no lift, 0 inside skin - but a barrel: no bust left at all (p/s1). 10 folded faces.
## 00:42 attempt 1b: blend share 0.5 / 0.65 of the full-span move | kind=fail
Skin patches came through under each breast (p/s05, s065c0). Not the cover crease (crease 0 changed nothing). Raycast probe (drawn skin with no cloth in front along -y but cloth behind it): 6 breast-lower-pole verts 4-6 mm in FRONT of the cloth. Cause: a share of a move that also slid tangentially cuts the chord of the curved surface, and the relax between pushes shrank the lower pole. The nearest-point "skin over cloth" test did not see them (cloth nearest point on the other side) - it only flagged the upper arm at the armhole.
Normal-only share: worse (12-14 folded, 96 drawn over at 0.7).
## 00:47 attempt 1c: share of full move, inward normal component removed, push_out after | kind=win
span 0.65: detail 0.008 mm, no lift, 0 skin in front (raycast), 0 inside skin, 6 folded faces. Sheet p/r065: cleavage filled, underbust spans breast-to-ribs, no skin patches. Remaining: a darker crease line along the lower rim in el8 front/3-4.
## 00:52 folded_faces is a false alarm on spanned cloth | kind=gap
`folded_faces` (normal against its CUT normal) stays 6 with the span, all at the rim z 1.105-1.115: the fold-underside faces were cut facing down-and-back, and spanned they face forward-down - rotated, not folded. Local measures: faces whose normal opposes their neighbours' = 0, cloth edges bent > 35 deg = 0 (baseline p0: 16 such edges, up to 146 deg - the shelf). Plugin change: dress should report a local fold (neighbour flips) and sharp edges; done below.
## 00:55 tuning span/settle | kind=win
0.65: slight downward ledge still dark in 3/4 el8. 0.8 / settle 0.10: smooth, uni-bust, breasts still read. 0.8 / settle 0.14 (55 passes): detail 0.000 all / 0.015 breast, 0 lift, 0 skin in front, 0 inside skin, 0 sharp edges: chosen (p/r08s14/sheet.png). 4 probes, ~6 min.
## 01:02 through the pipeline | kind=win
Preset sports_top: ease span 0.8, settle 0.14. `build_belle.py from=garments force=1 renders=` on the saved moves blend: exit 0, 32 s (garments 8.4, export 7.8, review 6.4). measure.py on the saved blend: detail all 0.000 mm (cloth 0.040, traced -0.002) vs limit 0.060 unchanged; breast 0.015; drawn_over_cloth 0; creased 14; hidden 803 identical to the blend's wd_hide group. Tight renders from the pipeline blend (tight/sheet.png) = probe. No lift ran.
## 01:04 bun hair "missing" in outfit renders | kind=gap
The bun IS there: hair is joined into Belle_body as material Belle_hair (4946 faces; a bun on the back of the head in head/three_quarter.png rendered with material colours). wardrobe.views.render uses Workbench color_type OBJECT, so the hair is painted skin colour and reads bald. Also seen: the hair cap covers the ears and its Principled base colour renders grey in Workbench. Change: wardrobe views.render (or build_belle outfit_renders) should use MATERIAL colour for the body, or tint the hair material slot.
## 01:05 Godot verify_wardrobe 21 runs | kind=win
Scratch gd/ with addons copied from this worktree, the pipeline's glbs. import + 21 runs at -P 4: 78 s. 21/21 pass. top worst holes 0.357% (Jump), poke 0.322% (Trot); shorts worst holes 0.392% (Walk); both worst holes 0.222% (Jump), poke 0.334%. Poke on the top is ft_jiggle_breast + upper_arm.
## 01:06 fixtures --only traced_detail dressed_presets --twice | kind=win
Changed as expected (span keys, settle 91 -> 162 passes on the fine figure, sharp_edges new); builds agree; 79 s + 79 s per fixture. Recording with --update.
## 01:10 golden review: the hull made the SAMPLE figure's top baggy | kind=fail
dressed_presets sports_top on the smooth sample figure: gap median 9.8 -> 22.2 mm, p95 13.3 -> 45.1 mm, max 17 -> 50 mm, hidden 2887 -> 2725. The convex hull spans every hollow, including the whole taper from bust to a waist hem. Belle's band is higher so her median only went 9.7 -> 12.6 mm. Would not have been seen from Belle alone - the golden diff caught it. Not committed.
## 01:13 attempt 2: rolling-ball closing instead of the hull | kind=dead-end
Each vertex raised along its normal until a ball of radius R on it clears all other cloth verts. Iterated (12 passes, half steps): ran away - moved up to 33 cm, 400 drawn tris over cloth (a raised vertex raises its neighbours' balls). Single pass against the eased cloth: stable but the two sides of the fold move toward each other and CROSS (62 edges bent >35 deg, 4-5 local flips, moves up to 11 cm). 2 probes each, ~4 min.
## 01:16 attempt 3: hull span masked to narrow hollows | kind=win
_hollows (the single-pass ball test, R) only picks WHERE: verts under the ball by > 1 mm seed a mask, feathered 4 cm along the cloth; the hull span (share 0.8) is weighted by it. Belle R 0.10: 156 hollow verts, detail 0.000 / breast 0.012, 0 lift, 0 skin in front, 0 sharp edges, 0 folds, gap median 10.4 mm (baseline 9.7), p95 23 mm. Same look as the unmasked span (p/h10/sheet.png). R 0.06 similar (97 verts). Chose 0.10.
(Clock note: entries above after 00:40 carry estimated times; real clock at commit was 00:56.)
## 00:50 final config through the pipeline again | kind=win
sports_top: span 0.8, span_radius 0.1, settle 0.14 (+ unchanged crease 0.03, smooth lift). build_belle from=garments force=1: 38 s. Saved blend: detail all 0.000 mm (limit 0.060), breast 0.012, drawn_over_cloth 0, creased 14, hidden 818. Tight sheet tight/sheet.png (compare p/p0/sheet.png = before). Godot 21/21 pass, 117 s at -P 4 (slower: fixtures running beside it): top worst holes 0.351% Jump, poke 0.293% Trot; shorts 0.392% Walk; both 0.220% / 0.304%.
## 00:53 goldens --only traced_detail dressed_presets --twice --update | kind=slow
117 s + 117 s (traced_detail, one more wearing) and 69 + 69 s. sample figure sports_top: gap median 9.8 -> 11.1 mm, p95 13.3 -> 34 mm (cleavage + underbust spanned). traced_detail top_compressed now 6 sharp edges and one 4-tri lift vs top_unspanned 2 sharp, no lift - the span adds a few bends on the small figure (open). Temp path put back in dressed_presets by script (item 8 noise again).
## 00:56 committed f89f836; full regress --twice started
## 01:10 full regress --twice --jobs 2 | kind=slow (win)
17/17 ok, each built twice and agreeing, "no change" vs the committed goldens. ~14 min wall (rabbit 206 s x2, cricket 142 s x2).
## summary of stage wall times
build Belle to moves 20 s; probe (dress + 9 tight renders + sheet) 8-10 s, two in parallel; pipeline from=garments force=1 32-38 s; Godot import + 21 verifies 78-117 s at -P 4; --only 2 wardrobe fixtures --twice --update ~4 min; full --twice ~14 min. Whole task ~40 min clock.
## open
- traced_detail's embossed sample figure: spanned top has 6 cloth edges bent > 35 deg (unspanned 2) and one 4-tri lift; Belle has 0. Worth a look where (armhole/mask edge?).
- sample figure sports_top gap p95 13 -> 34 mm (cleavage/underbust spanned) - intended look, but a looser fit there than before.
- `_hollows` single pass is O(verts x ball neighbours) python loop: ~1 s on Belle's 1169-vert top, 3500 verts on the sample figure; fine now.
- Outfit renders (wardrobe.views OBJECT colour) paint the joined bun hair skin-coloured - reads bald. Bun is present (head/three_quarter.png). Change views.render to MATERIAL colour or tint the hair slot.
- still no heavy-bust fixture; Belle in scratch is the only body with a real overhanging fold.
- character-pipeline garments hash still ignores preset contents (force=1 needed).
