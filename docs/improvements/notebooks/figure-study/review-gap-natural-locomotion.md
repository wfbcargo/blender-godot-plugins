# Review: fig-natural-locomotion (9ebb810)

## 01:35 setup | kind=win
Diff stat read in one call: 15 files, rig-anything code (actions, keyposes, locomotion, upper, export), SKILL.md, fixture mpfb_woman_curvy, 8 goldens. Wall ~5 s.

## 01:38 merge-safety | kind=gap
Branch base b496738 is 5 commits behind main (74ebef8: follow-through 0.6.0 flesh reporting, verify_flesh courses, wardrobe 0.5.0 fit, character-pipeline 0.6.0). `git merge-tree --write-tree` is textually clean, but flesh_figure.json and pipeline_woman.json goldens were re-recorded on both sides independently, and the builder's `regress --twice` ran on the stale base. Main's golden additions are flesh-detection only (independent of clip length), so likely fine, but unproven. Resolution: re-run the two overlapping fixtures on the merged tree. Plugin to change: tools/regress.py (or the workflow) should warn when HEAD is not a descendant of main before a golden --update.

## 01:38 versioning | kind=friction
SKILL.md and fixture comment say "since 0.24.0" but plugin.json/marketplace.json stay 0.23.0 (builder: "no version was bumped"). Regress lines print "rig-anything 0.23.0". Wall ~1 min. Resolution: note as minor; the merge commit must bump rig-anything to 0.24.0 in both plugin.json and marketplace.json.

## 01:39 manifests | kind=win
study_man/study_woman .moves.json read in one call: all 7 clips passed, forced {}, known_failures {}. Walk Fr 0.2, duty 0.615/0.643, natural 1.343/1.288, implied 1.304/1.253 (97%), knee 11.5 both legs, vault true; turns yaw +-90, end offsets ~0.28 m consistent with a 90 deg rotation about the foot-ball pivot (checked by hand).

## 01:42 style probe | kind=fail (branch defect)
Probe (review scratch styles.py on the builder's saved study_man.blend, locomotion.cycle froude 0.2, vault None vs False, 20 s, first try):
- adult: knee 11.5/11.5 vault, 27.2/28.5 no vault; vault hip range 0-25.3 mm
- elderly_shuffle: knee 11.5/11.5 vault (26.9/25.3 no vault); range 0-23.4 mm
- child: knee 11.5/11.5 vault (23.0/24.5); range 0-16.8 mm (less rise and fall than adult, though the style says "a bouncier body", bounce_scale 1.5)
- heavy: knee 12.1/11.5 vault (36.0/35.1)
Vaulting sets `bounce = 0.0` (locomotion.py key_at), so `bounce_scale`, a STYLE_KEY, is a no-op on every upright biped walk, and every style's stance knee converges to 11.5. `vault` is not in STYLE_KEYS, so a style cannot opt out (style_args raises); only `[moves.per_gait.Walk] vault = false` in a spec can. grungist-creek ships Margaret and Frank (elderly_shuffle), Lily (child) and Hugo (heavy); their next rebuild loses the style's soft knees/bounce, which is not mentioned in the commit. Also: 11.5 on every figure and style looks like an IK straight-leg floor, not a measured value. Fix in rig-anything locomotion.py: let bounce_scale scale the vault amplitude and give elderly_shuffle/heavy a knee floor (or `vault` in STYLE_KEYS); regress fixture: one styled walk with a knee/rise headline.

## 01:47 turn check sensitivity | kind=win
Mutation test on a scratch copy of rig_analysis (repo untouched), study_man.blend, 7 s, first try: baseline TurnL passes (skid 0.0/0.0); lift=0 fails "thigh.R skids 0.3699 along the floor (tolerance 0.0089)"; rotating about the rig origin instead of the foot ball fails "thigh.L skids 0.2805". The floor-skid check on turns is live, not vacuous. `planted_drift` is {} on turns (planted=[]), so the done-when's "foot-drift" is carried by floor_skid alone; acceptable since skid measures the same pivot.

## 01:47 merged-tree regress | kind=fail (tooling)
regress --only pipeline_woman flesh_figure mpfb_woman_curvy --twice --jobs 3 --keep <scratch>/keep on main+branch merge tree (git merge-tree e3ea0e7, archived to scratch): flesh_figure ok, mpfb_woman_curvy ok (twice), pipeline_woman ERROR "Render error (No error) cannot save ...FixWoman_Idle_three_quarter.png". Wall 75 s. Cause: --keep under the long session scratch path pushes the review png past Windows MAX_PATH (~270 chars). Resolution: rerun without --keep. Plugin to change: tools/regress.py should refuse or warn when --keep + fixture output path exceeds 250 chars (the Blender message "(No error)" hides the cause).

## 01:49 merged-tree regress, retry | kind=win
pipeline_woman --twice without --keep on the merged tree: ok [34 s + 32 s], no change (67 s wall; kind=slow). Then dressed_presets + traced_detail (the other fixtures main re-recorded) --jobs 2: both ok, 45 s. So main's goldens and the branch's goldens compose: the merge is safe for regress on every fixture either side touched (flesh_figure, pipeline_woman, mpfb_woman_curvy twice; dressed_presets, traced_detail once).

## 01:51 independent pipeline rebuild | kind=win
Copied the draft study_woman spec, set roles + TurnL/TurnR and quality preview, rebuilt fresh through character-pipeline (branch plugins, copy of the builder's hflib): rc 0, 25 s (body reused from library). The .moves.json is identical to the builder's apart from the `build` block (float tolerance 1e-4): knee 11.5/11.5, implied 1.2525 vs natural 1.2882, all 7 clip_checks passed, forced {}. Review strips include TurnL/TurnR front/right. Deterministic across sessions.

## 01:52 Godot verify_moves | kind=win
Scratch project (builder's project.godot + branch rig_anything addon + my study_woman + builder's study_man): import 3 s, verify_moves.gd 18/18 PASS, Walk plays x1.03/x1.029, first try.

## 01:53 golden coverage | kind=gap
mpfb_woman_curvy.json `moves_json.fields` went from a 16-name list to {"first","last","len":17}: harness `stable(max_list=16)` collapses the list once `turns` is added, so the golden no longer names the manifest fields (a lost field swapped for a new one would go unseen). Not mentioned in the commit. Fix: tests/fixtures/_harness.py moves_manifest should keep `fields` with max_list large (it is a key list, not a trace).

## 01:53 knee number | kind=gap
stance_knee_flex_deg is 11.5 on both study figures, the fixture woman, and every style probed (adult, elderly, child, heavy 12.1). 2*acos(0.995) = 11.46 deg: the value is the leg-reach cap the vault drives to, not a free measurement. Inside the done-when (<15) but it will never report a straighter leg; worth noting in rig-anything SKILL.md.

## 01:54 wrap-up | kind=slow
Review wall time ~20 min (01:35-01:55). Slow items: merged regress 75 s + 67 s, dressed/traced 45 s. Everything else under 25 s.
