# Next: catch it upfront - the checks that stop a bad design before it is built (then trunk and head)

A handoff for a fresh conversation. Start with:

> Read `docs/improvements/NEXT.md`, ask which item under "Where to pick up" to take next (item 1, "Catch it
> upfront", is the recommendation), plan it, and run it the way the likeness round ran: one worktree per
> branch, proven by a fresh `build_many` of the characters it affects and the game's demo selftests, looked
> at in Godot before it is called done. The regression suite is optional and never a gate (CLAUDE.md). Use
> the `plugin-round` workflow only if the user asks for multi-agent orchestration (see "Running the next
> session").

**The goal of all this work:** tools that make a new human asset from a brief **in under 30 seconds** and
have it **look great** in Godot. The study figures are the test bench. The scoreboard is the benchmark
(below): three brand-new characters built cold from their briefs, timed, and judged by an independent
critic. Every plan should say which of those two numbers it moves.

**How we get there (the user's rules, 2026-09-21):** the plugins should *guide* the work to a great design
quickly, so **catch a mistake upfront** - a spec that refuses, a stage check that fails with the fix in its
message, a warning before a build - rather than find it by eye after a build and correct it. When a round
does find something by eye, the fix is not done until the check that would have caught it first exists.
The goal is plugins that produce assets, not perfect assets: capture the improvement, build fresh, move on;
do not spend a round on small numeric drift.

## Fantasy species round (branch `species-1`, 2026-09-22)

[08-fantasy-species.md](08-fantasy-species.md) is the design. **The user's rule for it: tools and a method that
make *any* creature, driven by numbers, never per-species code; full anatomy on every body; it must look great.**
The named species are worked examples. Proven by a fresh `build_many` of 14 characters (the four species smoke
specs, three trial creatures, the four human smoke bodies, both study figures, cast_morgan), all five demo
selftests, and every Godot review sheet looked at.

What shipped (humanform 0.20.0, rig-anything 0.43.0, follow-through 0.12.0, wardrobe 0.9.0, character-pipeline
0.20.0, lookdev 0.12.1):

- **The method** (`humanform/references/species-design.md`) and **`species_design`**: `solve(observables)` from
  what a person can state or measure on concept art (21 observables), general laws for the rest - head
  allometry (H^0.30 adult, ANSUR II), mass by segment volume (square-cube), a build means an adult's girth at any
  stature (ANSUR II: BMI independent of stature; girth ~H^0.5) plus support girth for big bodies, reach landmarks,
  proportionate vs disproportionate - then `design()` (a consistent preset), `explain()`. Designed BMI matches
  the built body within ~3% from a 1 m gnome to a 3.1 m cyclops. Seven presets are generated examples
  (`scripts/derive_species.py`).
- **The warp** (`humanform/species.py`): the nearest human is fitted, then warped to the species by its own
  skeleton (per-bone length, girth, head scale, widths, a smooth hunch with a balance lean), vertices by linear
  blend skinning with seam-spread weights; eyes by their allometric factor. Genitals and muscle go on the
  pre-warp human so the warp carries them. `reads_adult` fails a body in the child range; an anatomy inventory
  fails a missing part not declared absent.
- **A creature in a spec with no file**: `[body.species]` inline (observables, knobs, `skin`, `head`,
  `anatomy.absent` with reasons, `graft`); the whole design runs when the spec loads, so a bad one is refused
  before a build.
- **Head** (`features.py`): features as MPFB targets + displacement at 19 landmarks + attached parts (horns,
  tusks); teeth and tongue on every body (they never existed), with a closed-mouth ray check.
  **Eyes** (`eye_layout.py`): any count and placement, sockets, lids, brows and lashes following them.
- **Surface**: skin for any tone (regions shift in the tone's own hue; subsurface follows the tone), patterns
  (spots, stripes, blotches, mottle, scales), a paler-than-holds tone refused, seam-tone and chroma checks.
- **Lower-body graft** (`graft.py`): legs to a tail with fluke; rig-anything upright swim and float,
  `[moves] locomotion = "swim"`.
- **Movement from the build** (`rig_analysis/morphology.py`): trunk-to-leg, stockiness, mass and reach drive the
  gait style; Froude and reach checks; turns and jumps on short legs.
- **Size**: ~30 human-sized constants in follow-through, rig-anything and wardrobe now scale with the body
  (exactly 1x across the human band).
- **Beards**: the square-patch grid fixed (anisotropic texels; a mip check refuses a patchy beard), a smooth
  outline, `beard_length`/`beard_volume`, `full` and `long` presets; hair scales with its head.

Every human builds as before apart from teeth and tongue, the dark lip line and fuller beards (checked tile for
tile). `regress --quick`: no errors, no pass/fail flips (the flesh_figure control flip this round caused is
fixed).

**Open, in order:**
1. The cyclops' pupil renders as a dark square close up; a shadow band at eye height from the closed side
   sockets; pale specks where the brow cards meet.
2. ~~Beards are layered shells, not strands; the long beard is rigid (no sway, no braids).~~ Done on
   `species-2-hair`: a root mat under strand cards grown from the beard field (density, width, clumping,
   `braids`), the hanging part its own strand mesh with a chain a lock and a chest collider, and three checks -
   a coverage check on the field's regions, a silhouette check at 0.6 m and 4 m, and the swing check in motion
   (which caught a beard swinging 4 cm into its own face). Stubble stays a shell, and the code says why.
3. Dwarf and gnome hands cannot reach the top of the head (warned); cast_morgan walks at Froude 0.12.
4. Tails only replace legs, are at most leg length, have no side fins; mass treats a mermaid as having legs.
5. Eyes have no bone of their own; no jaw bone, so no open mouth (bites, roars).
6. The demos load no species figure: add one (a `species_demo`) so a selftest covers them.
7. Step 6-7 of 08: fur (Godot shell fur plus strand cards) and head grafts / digitigrade legs (the gnoll).

## State at the end of 2026-09-21

**Everything is merged and pushed.** `main` (blender-godot-plugins) and `master` (grungist-creek) are
clean and in sync with origin. `~/.claude/skills` and the game's addons match `main`. The only other
branch was the parked `fig-genital-anatomy`, since finished and merged (Step 3 below).

The last rounds of the day: the likeness round ([plugins#7](https://github.com/wfbcargo/blender-godot-plugins/pull/7),
[game#6](https://github.com/wfbcargo/grungist-creek/pull/6)), the regression rules and this list
([plugins#8](https://github.com/wfbcargo/blender-godot-plugins/pull/8)), an orbit camera for the demos
([game#7](https://github.com/wfbcargo/grungist-creek/pull/7)), and this handoff.

Shipped on 2026-09-21, newest first:

| version | what | PRs |
|---|---|---|
| rig-anything 0.39.0, humanform 0.18.0, character-pipeline 0.17.0, wardrobe 0.8.0 | **The likeness round** (branch `likeness-round`, from building three likeness NPCs in grungist-creek - Taylor Swift, Morgan Freeman, Ariana Grande - and fixing what got in the way). *Accuracy:* a brief's `face` (ratios read off a frontal photo, fitted with a lever group per measure; `face_features.json`) and `ancestry`; beards (`stubble`/`short`/`goatee`/`moustache`) and a fringe over any preset; the dress eases off the body. *Motion:* an upright leg bends in its own front-back plane as it folds (Ariana ran bow-legged: knee 13.9 -> 3.1 cm out on the run); `arm_pose` measures along the body's heading (a turn failed on a phantom 22 degree swing). *Pipeline:* per-stage checkpoints and `StageFailed` (a failed stage resumes: Mei's review reran alone in 7.7 s), moves failures carry their reasons, `characters/pipeline.toml` `[blend] dir` and a refusal to save a .blend inside a Godot project, `build_many.py` (nine figures in 189 s at 3 jobs), a locked library index. Close-up `on_body` by points. Game: `likeness_demo.tscn`, the figure study's self-test warms up (a cold first run failed 10 timing checks) and takes figures with no flesh or fewer clips. | [plugins#7](https://github.com/wfbcargo/blender-godot-plugins/pull/7), [game#6](https://github.com/wfbcargo/grungist-creek/pull/6) |
| wardrobe 0.7.0 | Loose tops hang from the bust's apex instead of tucking under it. New: `fit.tuck` check, `tuck_limit`, a `skin` preset key, fixture `dressed_loose`. Ruth's tuck 17.2 -> 2.9 mm. | [plugins#6](https://github.com/wfbcargo/blender-godot-plugins/pull/6), [game#4](https://github.com/wfbcargo/grungist-creek/pull/4) |
| wardrobe 0.6.0 | `tshirt` / `longsleeve` ease off the body's smoothed form, so nipples and belly no longer show through (traced 0.19 -> ~0.01). | [plugins#5](https://github.com/wfbcargo/blender-godot-plugins/pull/5), [game#3](https://github.com/wfbcargo/grungist-creek/pull/3) |
| rig-anything 0.38.0 | `AsymmetryMeter`: each body's left against its right, measured in Godot. `motion_demo` prints it. | [plugins#5](https://github.com/wfbcargo/blender-godot-plugins/pull/5), [game#3](https://github.com/wfbcargo/grungist-creek/pull/3) |

Before that: the motion round (rig-anything 0.28.0-0.37.0, character-pipeline 0.16.0, plugins#2 /
game#1), Step 2 skin, and the flesh round. Their record is in the sections further down.

### Catch it upfront, round 1 (branch `catch-upfront-1`, 2026-09-21)

The top three of "Catch it upfront" plus what building them found. **Every check here fails something real,
and each has a control or a case in a fixture.**

- **Smoke bodies** (grungist-creek `characters/smoke_*.toml`): Pia petite 1.48 m, Tor 2.02 m, Edda 84 (elderly
  shuffle), Hal BMI 38 (heavy). Built fresh beside every round's change (grungist-creek CLAUDE.md). Their first
  builds found five things no reference figure could:
  - **follow-through flesh on a BMI 38 body fails three ways** - butt: `check_placement` puts both regions'
    weight 10 cm above their apex (0.52 over 0.3, nothing lets it through; the benchmark's blocker on two women,
    now a man); belly: 0 vertices in its zone; breast: 6 seed vertices pass both tests against 54 needed (78 pass
    each alone). Hal ships with no `[flesh]` until this is fixed. **Next round's first item.**
  - **the aged belly is not found**: Edda's belly stands 3.7 cm out, 8 vertices pass the seed test, none both
    (`may_miss` for now).
  - **a brief with no skin colour ships chalk white** (MPFB's untextured material; humanform only applies its
    skin look when `skin` is given) - 5-9% of the figure past white in Godot. Now refused at spec load.
- **Knee: the premise was wrong, the check moved to the clip.** Measured on every built rest skeleton, six
  shipped bodies sit past 10 deg across the leg (Morgan 28, Ariana 23, Walter 19, Ruth 15 inward, Noah 13), and
  a front view shows the joints centred in legs that really are a little bowed or knock-kneed - a body trait,
  not a fit error. A humancheck gate at 10 deg would have failed three shipped characters whose motion is fine.
  What had gone wrong was the CLIP, fixed in 0.39.0, and nothing failed if it regressed. Now every gait reports
  `knee_plane_deg` off its playback and fails over `locomotion.KNEE_PLANE_MAX_DEG` 12: shipped 0.0 on every
  figure, the control (`motion.PLANE_FOLD` 0, rigify_human `knee_plane`, knees moved 12 mm out) 43-45 and fails.
- **Spec checks before a build** (`build_many` reads every spec first):
  - warns when `[moves.per_gait.<role>] upper` pins a sourced default (`spec.SOURCED_UPPER`) - Belle's case;
  - refuses a `[flesh]` type follow-through's registry does not have (a smoke spec's `moobs` got through to the
    flesh stage, after body and bake);
  - refuses a brief with no `skin`.
- **Review in Godot's look** (`character-pipeline/scripts/review_godot.py`, run by `build_many` after the
  builds): the project imported once (14-15 s), then lookdev's `close-shot` of each character dressed from its
  manifest, its Blender close tile first in each row, into `<export>/review/<id>/godot/`. 24-52 s a character.
  Outside the review stage because parallel builds' Godot imports of one project would race. A close-shot
  failure fails the run.

**Open from this round:**
- **Taylor and Ariana fail the Godot review** (`SKIN_PAST_WHITE` under clear_midday, 3.4% and 6.7%; max 1%).
  Taylor's spec skin `[0.93, 0.80, 0.72]` is ~0.64 linear luminance, brighter than real skin; Ariana's is partly
  her pale suit. The upfront fix is a spec check on skin albedo - it wants a published skin reflectance range
  before a threshold. Ruth, the benchmark's 3.91%, passes now.
- The follow-through flesh findings above.
- The Godot review's texture import is the headless one (lossless); the editor rewrites to S3TC on open - the
  "pin texture import settings" task.

### The trunk-and-head round (rig-anything 0.40.0, branch `trunk-and-head`, 2026-09-21)

One branch, not four: all four items edit `upper.defaults` and `Upper.cycle_key`. **Every target now
has a source** (a literature pass, cited in `upper.defaults`), and two of this file's diagnoses were wrong:

- **The girdle's "6x spread" was the instrument.** `motion_demo`'s Fourier amplitude ran on the raw arm-root
  height (~250 mm up the chest) over a window that was rarely a whole number of strides, so the offset
  leaked in: Marco read 18.1 mm over 9.4 strides, Mei 3.2 over 9.0. With the mean taken out every body
  dips 6.2-7.4 mm peak-to-peak walking and 15-19 running. No source gives a clavicle excursion in gait,
  so `girdle_drop` is untouched. The same leak biased every Fourier number the demo printed (slightly).
- **`spine_flex_deg` is not the biped's sagittal plane**: it is a quadruped gallop's arch, 0 on every
  upright body by design. The biped's is `lean_bob`, and its walking size was already right (Thorstensson
  et al. 1984: 2-3 deg lab-frame); the "4 walking, 6-8 running" targets above had no source. What was wrong
  was the RUN's timing - it must peak backward at footstrike - and the run's size.

What changed, baked-clip numbers from `rigify_human` (walk / run) and Godot (`motion_demo`):

| | before | now | source |
|---|---|---|---|
| trunk pitch, lab, p-p | 2 / 4, peak at strike | 2.5 / 5.1, `lean_lag` 0 / 0.25 | Thorstensson 1984 |
| pelvic obliquity p-p | 8.0 / 5.7 (fell) | 8.9 / 10.8-11.9 | Ruiz-Malagon 2023, Perpina-Martinez 2023 |
| thorax lab tilt | 3 flat, ~120 deg behind the pelvis | 3.9 / 7.5, over the stance leg (-167..-178) | Thorstensson 1984 |
| head keeps of the thorax's turn | 15% flat | 64-65% / 20-29% | Pontzer et al. 2009 |
| head nod p-p | 0.3 / 0.6 | 1.5-1.6 / 1.7-1.9 (Godot), gaze held 1 m ahead | Hirasaki 1999, Moore 1999 |

- `upper.footstrike` is the shared timing signal; two legs half a cycle apart at width 0.25 give exactly
  `cos(4 pi (p0 - lag))`, so lag 0 is the old `lean_bob` to 1e-15. The head's nod does NOT use it: the
  literature says the nod compensates vertical head travel, so `locomotion` hands `cycle_key` the body's
  height through the cycle and the head pitches `atan(dz / gaze_m)`.
- `upper.planes` measures all of it off the baked clip into the gait report; `rigify_human`'s
  `trunk_planes` runs the defaults and two must-fail controls (`control_locked_head`: head_hold 1.0, no
  gaze -> head_moves False; `control_swing_side`: side_bend negated -> leans_over_stance False).
- `motion_demo -- --selftest` gates the lean-over, the pelvis's rise with speed, and the walking head.
  **It caught Belle**: her spec pinned `head_hold = 0.85` (and the old side_bend, lean_bob) per gait, so her
  head stayed at 16%. Those three are gone from `belle.toml`.
- Styles keep their meaning against the new default: `relaxed` head_hold 0.75 -> 0.2, `elderly_shuffle`
  0.9 -> 0.6.
- Built fresh: the nine figures plus Hugo (heavy) and Nadia (relaxed), 11 ok in 249 s at 3 jobs; the five
  demo selftests pass.

**Open from this round:**
- **Our walk bobs more than our run.** The nod follows the body's height, and it came out 5.1 deg walking
  and 1.6 running on the Rigify figure (1.5-1.9 on the MPFB cast) - the vault walk rises and falls more than
  the run, where a real run's COM travels ~6-10 cm against a walk's ~4-5. Worth measuring the hip height
  p-p per gait against published COM excursion.
- **No pelvic tilt plane.** The pelvis never pitches; published pelvic tilt ROM is ~7 deg walking and
  running (Ruiz-Malagon 2023). Its phase needs a source before it is built.
- **A spec that pins a sourced default** (Belle) is only caught after a build, by the demo. A pipeline
  warning when a spec's `upper` overrides `head_hold`, `side_bend`, `lean_bob` or `pelvis_list` would catch
  it upfront.
- `quadruped`, `dressed_skirts` and `rabbit` read CHANGED against their goldens on `main` itself (angular
  momentum, the dress's cover, flipped faces): pre-existing drift, not this round's, left unrecorded.
- The run's pelvic obliquity (10.8-11.9) sits under Ruiz-Malagon's 14.5 at 10 km/h; chosen at the low end
  of a wide range on purpose.

**The likeness round's open items.** Morgan Freeman's likeness misses by 2.7 mm at the mouth and 7 mm at the
jaw (aged after the fit, and the photo's jaw is under a beard). ~~The beard's back edge is saw-toothed~~ (round 2
of `species-1-beard`: the region is a signed distance on the face, `brows.beard_field`, faded across its zero line,
so the edge is a smooth curve; beards also got `full` / `long`, layers, a hanging part, and `beard_length` /
`beard_volume`). ~~Open: the long beard's hanging part is a rigid tube skinned head-to-chest, no follow-through
sway yet, and no braids~~ (round 2 of `species-2-hair`: the whole beard is strand cards, the hanging part is a
follow-through strand mesh with one chain a lock, and `hair.beard_braids` plaits it). ~~The beard's square patches in Godot~~ fixed on `species-1-beard`: V repeated every 12 mm on
512 rows (texels 7:1), so Godot's mip blurred U into blocks and scissor cut the texture's 35% holes out whole;
now square texels, an opaque under-layer and `humanform.hairtex.mip_check`, which refuses such a shell. Reading a photo's ratios is by hand (a canvas grid in the browser, ~5 min a face; see humanform
SKILL.md) - a landmark detector would make it one call. Likenesses set proportions, not identity: skin detail,
expression and makeup are still missing. The first builds' review took 61-73 s against 6-9 s since: a cold
cache on first use, not a steady cost.

### Catch it upfront (from the likeness round, 2026-09-21)

The goal is plugins that guide the work to a great design quickly - catch a mistake before a build rather than
correct it after. Each item below cost this round one or more rebuild-and-look loops; each says the check that
would have caught it first. Highest value first:

1. **Review in Godot's look, not only Blender's.** The dress's bust points and the beard's square patches were
   invisible or different in the review stage's Blender close-ups and obvious in Godot (4 rebuilds for the beard,
   3 for the dress). Render the review close-up set through lookdev's Godot `close-shot` (or add it beside the
   Blender set), so what is judged is what ships.
2. **A body check for the knee's bend plane.** Ariana's bow legs came from her fitted rest skeleton (knee 10.9 mm
   out against 22.5 forward). rig-anything now bends in plane and warns, but humanform's humancheck should fail a
   rest knee more than ~10 degrees across the leg before anything is animated.
3. **Build an extreme body in every round's smoke test.** A 1.53 m petite woman found two false failures (turns,
   close-up `off_body`) and the bow legs; the six reference figures are all 1.57-1.80 m and none is petite. Keep
   a small set - petite, very tall, elderly, heavy - in `build_many` as the round's fresh-build check.
4. **Lint garment presets for relief.** `dress_sleeveless` had no ease and no `detail_limit`, so nothing measured
   what it carried of the body. Any preset over the bust or belly should have to declare `detail_limit`, and a
   preset without one should refuse to load.
5. **A likeness helper instead of hand-reading photos.** Reading six ratios took ~5 minutes a face through a
   browser canvas grid, and the first photo of two of the three people was unusable (turned). A script (or a
   face-landmark model) that takes a photo, checks it is frontal, and returns the ratios would make it one call;
   the pipeline could then refuse a turned photo instead of fitting to one.
6. **Say when a likeness is fitted and then changed.** Morgan's face is fitted at 58 and aged after; the fit's
   `likeness.fit` reports the pre-ageing numbers. Re-measure after ageing and report both.
7. **Policy for real people up front.** Nothing in a spec says a character is a real person's likeness; the build
   decided by hand to leave out breast and butt jiggle and to fix a dress that showed the body. A spec field
   (`[character] likeness = true`) could make flesh refuse those types and require garments with a detail limit.
8. **Name the photo and its readings in the spec.** The specs carry them as comments; a `[body.face] source`
   field (file, pixel readings) would let a later round re-check a reading without redoing it.

Tooling friction that was not the plugins (worth knowing, not fixing here): bash heredocs broke on apostrophes
three times (write a patch file and run it instead); the browser pane's screenshots time out while it is hidden
(retry); Wikimedia serves only its standard thumbnail widths (500, 960, 1280...).

**Figures in the game:** all nine (study_man, study_woman, Belle, Marco, Mei, Ruth, and the likeness NPCs
Taylor, Morgan, Ariana) are on rig-anything 0.39.0 with `[variability] asymmetry = 0.35`, built by
`build_many.py`; the blends live in `C:/Users/pauli/Code/Blender` (the game's `characters/pipeline.toml`).
Before that, all six were on rig-anything 0.37.0/0.38.0 with `[variability] asymmetry = 0.35`. **Marco and Ruth were rebuilt on wardrobe 0.7.0**; they
are the two whose outfits use the changed presets. Backups of their previous blends and assets are in
`%TEMP%/rw/cloth/backup/` (0.5.2) and `%TEMP%/rw/hang/backup/` (0.6.0). These are scratch folders, so do
not count on them.

**One regress row is red and has been for two rounds:** `verify_strands pipeline_ponytail`, with
swing_spread 1.050. It is diagnosed and not fixed; see "The one red row" further down. Every other row is
green: `regress --quick --godot` on 0.7.0 reports 25 fixtures ok.

### To preview where we are

In grungist-creek (`GODOT` = the `_console` build, path in its CLAUDE.md):

    "$GODOT" --path . likeness_demo.tscn  # Taylor, Morgan, Ariana: the likeness NPCs
    "$GODOT" --path . cast_demo.tscn      # Marco, Mei, Ruth dressed (G toggles clothes). L = lighting
    "$GODOT" --path . motion_demo.tscn    # four bodies side by side; 2 walk, 3 run, V top-down; the HUD shows left vs right
    "$GODOT" --path . figure_study.tscn   # study_man and study_woman on turntables

Every figure-study demo has an orbit camera: drag to orbit, middle-drag or Shift+drag to pan, the wheel to
zoom (to 15 cm), arrows to orbit and to move the view point from face to feet, Z for the picked figure's
whole body, C for its face, Tab for the next figure (keeping the angle). To see the cloth work, open
`cast_demo`, pick Ruth with Tab, press C, and switch lighting with L. Her
longsleeve should hang straight from the bust with no fold under it. There is a small crease at each apex
under clear_midday, which is known (item 4 below). One stale comment: `motion_demo.gd`'s header still says
the head-thorax rung is "NOT built yet". It was built in 0.32.0, so the comment is wrong, not the demo.

## Where to pick up - the user chooses (ask, don't assume)

In the order I would take them:

1. ~~**Catch it upfront, round 1**~~ **Done 2026-09-21** - see "Catch it upfront, round 1" above. Next:
   follow-through's flesh on very heavy and aged bodies (what the smoke bodies found), a spec check on skin
   albedo, then round 2 below. Was: the top three of
   ["Catch it upfront"](#catch-it-upfront-from-the-likeness-round-2026-09-21), which turn this round's
   look problems into failures before a build. They serve both goals: fewer rebuild-and-look loops is the
   30 seconds, and a check that knows what looks wrong is the "look great". Branches:
   - `review-godot-look`: the review stage renders its close-up set through Godot's look (lookdev's
     `close-shot`) as well as Blender's, and judges the Godot set. The dress's bust points and the beard's
     square patches were only visible there; 7 rebuilds between them.
   - `knee-plane-check`: humanform's humancheck fails a rest knee bent more than ~10 degrees across the leg,
     with the fix in the message, before anything is animated (Ariana's bow legs).
   - `extreme-body-smoke`: a petite, a very tall, an elderly and a heavy spec in the game (`characters/smoke_*.toml`)
     that every round builds fresh with `build_many` alongside what it changed. The petite body alone found
     three problems this round; the reference figures are all 1.57-1.80 m.

   Then the rest of the list (garment relief lint, a photo-to-ratios helper, re-measuring a likeness after
   ageing, a real-person spec field, the photo readings in the spec) as one or two more rounds.
2. ~~**Re-run the benchmark.**~~ **Done 2026-09-21:
   [rerun-2026-09-21.md](notebooks/benchmark/rerun-2026-09-21.md).**
   - **Time:** cold median 43.5 / 42.3 / ~46 s. The 73-93 s regression is gone, but that is still no
     nearer 30 s. `moves` is now the largest stage at 11-13 s.
   - **Critics:** 12/18, 11/17, 13/18, and no character reads as real. Hair and dead eyes are on all
     three, as before.
   - **New:** a cell pattern on the forearms and hands, seen by all three critics and measured by nothing.
     Ruth's full tile is 3.91% past white under clear_midday.
   - **Blockers:** Marco builds clean. `check_placement` still has no escape, and it now drops the butt on
     both women, Mei's by a one-sided 0.01.
   - **Caveat:** Ruth's number is from 2 clean runs; another session's CPU load spoiled the rest.
   - **To see them:** grungist-creek's `bench_demo.tscn`.
3. ~~**The trunk and the head, as one round.**~~ **Done 2026-09-21 (rig-anything 0.40.0)** - see
   "The trunk-and-head round" above; the record below is kept for its measurements. Both sections below are measured and written to be picked up
   cold, and both need every character rebuilt, so doing them together pays for one rebuild and one look
   critic:
   - ["The trunk's other two planes"](#the-trunks-other-two-planes-measured-2026-09-20-built-by-nobody):
     `spine_flex_deg` is 0.0 in every gait entry, and lateral bend FALLS with speed. Branches:
     `motion-spine-flex`, `motion-frontal-plane`, `motion-girdle-per-body`.
   - ["The head is held almost still"](#the-head-is-held-almost-still-measured-2026-09-21-built-by-nobody):
     `head_hold = 0.85` leaves the head 15% of the thorax's turn and 0.3 deg of nod at a walk. Branch:
     `motion-head-hold`.

   The two share a footstrike signal, so agree that seam before either branch starts.
   `motion_demo.tscn -- --selftest` already prints every before number.
4. **Asymmetry follow-ups** (from 0.38.0's verdict that 0.35 is "subtle to inert"):
   - Widen the arm-swing draw so it cannot land near zero: |u| in [0.5, 1] with a random sign.
   - Find out why Belle's and Marco's step length is asymmetric even though the draw does not cause it:
     build a scratch copy at asymmetry 0.
   - Ship an `.import` preset. Godot's default glb import erases the run shoulder-dip asymmetry and moves
     stance offset by up to 25 mm.

   After those, **turn the runtime jitter on** (`jitter_phase` / `jitter_amp` are still 0 on every
   character). There is now an instrument to judge it by. Notebooks:
   [asym-godot-meter.md](notebooks/asymmetry/asym-godot-meter.md),
   [asym-motion-demo.md](notebooks/asymmetry/asym-motion-demo.md).
5. **The crease at each bust apex** (wardrobe 0.7.0's accepted open item). The convex hang field makes
   the profile two straight lines meeting at the apex, and Godot's direct sun shows the corner at 1 m on
   Ruth. Ten attempts at rounding it with offsets are recorded in
   [cloth-bust-hang.md](notebooks/cloth-hug/cloth-bust-hang.md). The honest next step is cloth bending
   stiffness, not another offset. Also from 0.7.0: Marco's poke-through doubled to 0.19% at a walk
   (still under the 0.5% limit), and 48 relax iterations cost about 4 s per character. The likeness round's
   dress spans the hollows (`span` 0.8) and hid the apexes; a sleeved top cannot use span as it is.
6. **The ponytail root-bone blocker**: the one red regress row. It is diagnosed further down and needs its
   own branch.
7. **Hair**: the benchmark's largest open look item, and every critic puts it in their top three.
   `short_crop` reads as a moulded cap (Morgan's white crop most of all), and `long_loose` stops at the
   shoulder on Mei. The likeness round added beards and a fringe.
8. **An age layer**: the 40s and 60s briefs both read twenty-plus years young. Slackness, lip thinning,
   hand tendons and posture can all be authored on top of the 58-year fit.
9. ~~**Ancestry as a sheet field**~~ - done in humanform 0.18.0 (`ancestry`). Still open: a decision on
   "Hispanic", which MPFB's three macros do not name.
10. **The rest of Step 5 - motion**: MovesController's turns, the fingertip gaps, and a motion critic on
   every clip.
11. **Small leftovers:**
    - `LookdevPresets.apply` leaves stale light properties on the sun.
    - The tone_shift controls need re-rendering.
    - Flesh items: the jump course sits at 10.2-11.4% against its 10% line, and walking phase is
      0.69-0.85 against people's 0.66.
    - wardrobe's `span` on a sleeved garment pushes the torso into the gap under the arm if a preset ever
      asks for it. None does.

## What this session learned (2026-09-21)

- **Measure what you are fixing before you trust its diagnosis.** This file said `span` was "the heart
  of" the cloth fix. It was built, measured and rendered, and made things worse. The cause was one layer
  over, in `smooth`, which already existed. Keep a small re-dress harness: copy a character's blend, delete
  the garment, run `presets.dress` with the worktree's wardrobe, and print `fit.detail`. A re-dress takes
  2 s, against 60-80 s for a pipeline rebuild. The scripts are in `%TEMP%/rw/cloth/` (`redress.py`,
  `run2.sh`, `tuck.py`, `shots.py`, `zoom.py`); rewrite them if that folder is gone.
- **Blender Workbench hides what Godot's sun shows.** The 0.7.0 apex crease was invisible in front and 3/4
  Workbench renders and plain in a Godot `close-shot --views bust` at 1 m under clear_midday. Judge cloth
  from a 0.3 m orthographic close-up plus the Godot bust shot, never from a front render alone.
- **Moving cloth breaks its cut skin weights.** A garment cut from the body keeps each vertex's weights.
  Move the cloth centimetres, as hanging does, and those weights belong to skin that is no longer under
  it, so the breast came through at 0.33%. Preset `"skin": {"transfer": true}` fixes it.
- **The `plugin-round` workflow**: one round (asymmetry, 2 branches) cost 11 agents, 1.55 M subagent tokens
  and 5 h 13 min. A hand-run branch ran in parallel beside it in its own worktree with no conflicts,
  because the two touched different plugins. Its `COMMON` preamble now describes the chat state
  generically, and `ship.rebuild: []` skips the rebuild and render steps.

---

## The head is held almost still (measured 2026-09-21, built by nobody)

**Origin:** the user, on the shipped figures - "during all of the animations the heads are perfectly
still".

They are, and it is one constant. `upper.defaults` sets `head_hold = 0.85`, and `upper.trunk` gives the
top of the chain `keep = 1.0 - head_hold * (j + 1) / len(top_i)`, so with a neck and a head above the
thorax the head keeps **0.15** of the thorax's turn. Measured off the baked clips of four bodies
(`motion_demo.tscn -- --selftest`, which now reports it), peak-to-peak degrees over a stride:

| | head yaw | head nod | thorax yaw | head keeps |
|---|---|---|---|---|
| Walk (Marco/Mei/Belle/Ruth) | 1.00 / 1.13 / 1.60 / 0.99 | **0.32 / 0.30 / 0.30 / 0.29** | 6.51 / 6.51 / 9.89 / 6.50 | 15-17% |
| Run | 2.10 / 2.09 / 3.56 / 2.10 | 0.57 / 0.59 / 0.76 / 0.57 | 13.77 / 13.87 / 17.46 / 13.78 | 15-20% |

The measurement lands on 15% on every body at both speeds, which is exactly `1 - head_hold`: the
prediction and the baked clip agree, so there is no mystery here to solve, only a number to choose
better. **A third of a degree of nod at a walk is invisible.**

### What is right about it, and what is not

`head_hold` is a gaze-stabilisation model, and gaze stabilisation is real - a walking head does hold
still against the trunk's turn, which is why this was written in the first place. Three things are
wrong with it as it stands:

- **It is one flat constant at every speed**, where the real attenuation is not. The same tell the
  thorax had at a flat -179.3 deg and the head had at a flat -0.6.
- **It stabilises the wrong axes together.** Holding gaze on a target is about rotation around
  VERTICAL. It says nothing about the nod, and a real head pitches with each footstrike - our 0.29 deg
  is not attenuation, it is absence.
- **The head rung gave the head a phase, never an amplitude.** 0.32.0 derived *when* the head turns
  (`upper.head_frequency` -> `response`), and 0.30.0 says outright that `response`'s gain is
  deliberately not applied - "amplitude is authored, timing is derived". So the head's amplitude has
  never been derived by anything; `head_hold = 0.85` is a hand-set number and always was.

### The branch: `motion-head-hold`

Split `head_hold` into what it is actually doing, and make the part that should move with speed do so:

1. Keep strong stabilisation about **up** (gaze), but let the share vary with speed rather than sitting
   at 0.85 for a stroll and a sprint alike.
2. Give the head its own **nod**, driven at twice a stride by footstrike, not derived from the thorax's
   yaw at all. This is the one the eye will notice first, and it is the same signal `motion-spine-flex`
   needs, so **the two branches should agree their footstrike signal up front** rather than each
   inventing one.
3. Leave the phase alone. 0.32.0's lag ladder is measured and correct, and
   `thorax_head_phase_deg` must not move: it is goldened, it sweeps -79 to -147 across the figures
   today, and nothing in this item is about timing.

**Targets need a source, not a guess.** Published walking values put head yaw well above 15% of trunk
yaw and head pitch at a few degrees a stride rather than a third of one, but the numbers here should be
fitted to a named reference the way `trunk_hz` was fitted to van Emmerik et al. - and the fit recorded,
with the same honesty the head-rung notebook used about what was measured and what was chosen.

**The control that must fail** writes itself and mirrors the head rung's: `head_hold = 1.0` is the
perfectly locked head, and it must read a flat nod and a flat yaw and fail whatever check this ships.

### How to measure it

`motion_demo.tscn -- --selftest` prints the table above - head yaw, head nod, the thorax's yaw beside
them, and the share the head keeps - for four bodies at two speeds, live off the playing skeleton. The
figures did not need rebuilding to produce it, so the before is already recorded here.

## Cloth that hugs the skin (measured 2026-09-21, built by nobody)

**Status 2026-09-21: branch A shipped as wardrobe 0.6.0, and the diagnosis below was half wrong.** `span`
was the wrong tool: ungated across a sleeved garment it pushed cloth into the gap under the arm (gap_min
-19 mm, 13-18 folds), and over the torso alone it left a ridge under the bust and never reduced the
breast's traced relief (0.16 -> 0.24). `detail` measures relief at 3 cm - a nipple, a navel - and a bump
on a convex surface is not a hollow. What fixes it is reason 1 below: the loose presets now carry
`smooth` 1.0 (ease off the body's form, not its skin) and the sports top's `detail_limit` of 0.06 mm.
Ruth 0.191 -> 0.011 (breast 0.096 -> 0.004 mm), Marco 0.189 -> ~0, Belle in a tee (stress) breast 0.134
-> 0.019 mm; `smooth` 0 fails the new limit. `verify_wardrobe` passes on both rebuilt figures, walk / run
/ crouch / jump, holes unchanged. Notebook:
[notebooks/cloth-hug/cloth-span-loose.md](notebooks/cloth-hug/cloth-span-loose.md).

**Fixed 2026-09-21 in wardrobe 0.7.0 (branch `cloth-bust-hang`)**: hanging starts 0.1 of the way down
instead of 0.3, rows and columns are made convex, heights are evened between pushes, and the skin
weights are transferred. The new check is `fit.tuck`, gated by `tuck_limit`, and the new fixture is
`dressed_loose`, whose control fails at 34.1 mm. Tuck: Ruth 17.2 -> 2.9, Marco 7.1 -> 1.4, the sample
figure 34.1 -> 3.7 mm. **Left open:** a small horizontal crease at each apex where the hung sheet meets the
breast above it, visible in Godot under clear_midday at 1 m on Ruth. Ten attempts at rounding it are in
[notebooks/cloth-hug/cloth-bust-hang.md](notebooks/cloth-hug/cloth-bust-hang.md); the honest next step is
bending stiffness, not another offset. The garments stage costs about 4 s more.

What it was: **the cloth tucked under the bust** instead of hanging straight from
its apex (Blender side view and the Godot bust shot both). `hang` is on for these presets but fades in only
below `shoulder_z - 0.3 * (shoulder_z - hip_z)` (`fit._hang_setup`), which is about where the bust sits.
That is branch B's ground; it moves every hanging garment, so re-record the dressed fixtures - and **no
fixture dresses `tshirt` or `longsleeve` today**, so add one on a body with a bust in the same branch.
Branch C was not needed and not checked.

**Origin:** the user, on the shipped figures - "on some clothing it is hugging to the skin too much and
not accounting for softness. Breasts are fully visible in outline beneath the clothes instead of acting
like a fabric, it is almost adhering to the skin".

### What the measurement said

`fit.detail(garment, body)` is the instrument wardrobe already ships for this - `traced` is the
area-weighted slope of the cloth's relief on the skin's relief sampled under it, and `relief_mm` is the
millimetres of the body's own relief the cloth carries. One call per garment, no new code:

| garment | preset | smooth / span | `traced` | relief_mm | region |
|---|---|---|---|---|---|
| Belle SportsTop | `sports_top` | 1.0 / 0.8 | **-0.002** | 0.000 | breast 0.011 |
| Mei Leggings | `leggings` | 1.0 / - | **-0.005** | 0.000 | butt 0.000 |
| Mei SportsTop | `sports_top` | 1.0 / 0.8 | **0.006** | 0.006 | breast 0.002 |
| Marco Jeans | `trousers` | none | 0.100 | 0.090 | butt 0.095 |
| Ruth Trousers | `trousers` | none | 0.099 | 0.099 | butt 0.013 |
| **Ruth Longsleeve** | `longsleeve` | **none** | **0.191** | **0.143** | **breast 0.096** |
| **Marco Tshirt** | `tshirt` | **none** | **0.189** | **0.164** | belly 0.082 |
| Belle Shorts | `shorts_mid_thigh` | none | 0.143 | 0.174 | butt 0.080 |

**It is exactly backwards.** A compression garment - the kind that in reality IS painted onto you -
reproduces essentially none of the body's relief. A loose tee or longsleeve reproduces about a fifth of
it. Ruth's longsleeve carries 0.096 mm over the breast, which would **fail the 0.06 mm limit the sports
top is held to** and is six times what that sports top actually achieves there.

### Why, in three places

1. **The loose presets get none of the machinery.** `tshirt` and `longsleeve` set `smooth: null`,
   `span: null`, `flatten: null` - only an 11 mm base gap. Every bit of the sophistication went into the
   compression garments, whose preset notes run to paragraphs.
2. **`span` is gated behind compression.** `fit.py`: `if compressing and span and span > 0:`. Spanning is
   the mechanism that bridges a cleft - the `sports_top` note describes it as spanning "80% of the way to
   its own convex hull around the hollows a 10 cm ball does not reach into" - and a loose garment
   **cannot use it even if a preset asks**. This is a code change, not a tuning change, and it is the
   heart of the item.
3. **`loose` never reaches the torso.** `fit.paint_ease` paints `wd_ease` on the hem, cuff and neck bands
   only, so the 22-25 mm of `loose` lands at the openings and the chest gets the 11 mm base. A real tee
   stands further off the bust than that and spans the cleft completely.

### The target, chosen 2026-09-21: span the hollows, keep the silhouette

A loose garment should bridge the intermammary cleft and the underbust fold, and stand off the chest, so
that the bust still shapes the garment's **outline** the way a real shirt does while the cloth stops
reproducing the **surface** between and under the breasts. **`traced` below ~0.05 on a loose garment,
against 0.19 today**, with a `detail_limit` in the preset so it is gated from then on rather than
measured once.

Deliberately NOT the sports top's near-zero: that would have a woven tee ignore the body almost
entirely, which is the most physically correct answer for cotton but the largest change to how the
characters currently look. Per-fabric tracing (a knit tee traces more than a woven shirt) was considered
and is the honest long answer; it needs a fabric parameter threaded through `ease` and every preset
retuned and remeasured, so it is a later round, not this one.

### The branches

**A. `cloth-span-loose`** - ungate `span` (and consider `settle`) from `compressing` in `fit.ease`, then
give `tshirt` and `longsleeve` a `span`, a `span_radius` and a `detail_limit`. The sports top's numbers
(`span` 0.8, `span_radius` 0.1, `settle` 0.14, limit 0.06 mm) are the worked example to start from, but
they were tuned for cloth measured against a *compressed* body, so expect to retune rather than copy.
Ungating must not move any compression garment: prove that with the table above, which is four
characters' worth of before.

**B. `cloth-torso-ease`** - let `paint_ease` put ease over the torso, not only at the openings, so a
loose garment stands off the chest instead of sitting at the base gap. Interacts with (A); agree which
one owns the chest gap before both start.

**C. Re-check a claim before trusting it.** The `sports_top` note says `flatten` is unusable on
character-pipeline bodies because "follow-through's breast search lands on the jaw". `fit.detail` found a
real breast region on both Ruth and Mei while measuring the table above, so that note may be stale. If it
is, `flatten` becomes available to the loose presets too and (A) may need less work.

### How to measure it

One call, on the built blend, no rebuild needed:

    from wardrobe import fit
    rep = fit.detail(garment, body)      # regions, traced, relief_mm

The table above came from running exactly that over each character's `.blend` in
`C:/Users/pauli/Code/Blender/`, picking garments out as the meshes carrying a `wardrobe_cut` property.
`verify_wardrobe` in Godot stays the other half of the check: spanning cloth off the body is the failure
mode that lets skin through, and the sports top's note records that history in detail.

## The trunk's other two planes (measured 2026-09-20, built by nobody)

Written to be picked up cold. **Origin:** the user, looking at the shipped round - "the running still looks
very rigid ... it is like their spine isn't moving with their legs motion", and then "when people step their
shoulders drop slightly and their hips rotate, they are also slightly imperfect - the models should reflect
this".

### What the measurement said

Off the baked clips of four different bodies, via `grungist-creek`'s `motion_demo.tscn -- --selftest`, which
already reports all three planes. Peak-to-peak degrees over one stride:

| | spine twist | spine bend | spine flex | pelvis yaw |
|---|---|---|---|---|
| Walk (Marco/Mei/Belle/Ruth) | 13.4 / 13.1 / 16.4 / 13.5 | 10.2 / 10.1 / 10.3 / 10.3 | **1.8 / 1.8 / 1.8 / 1.7** | 8.2-8.4 |
| Run | 30.7 / 30.7 / 34.3 / 30.7 | **7.6 / 7.7 / 9.5 / 7.8** | **3.8 / 4.0 / 3.8 / 3.9** | 17.5 |

**The rig is not the limit, and that is the good news.** Belle's axial chain is
`spine -> .001 -> .002 -> .003 (chest) -> .004 (neck) -> .005 (head)` with `shoulder.L/R` off the chest, and
it already twists 31-34 deg peak-to-peak at a run. A rig that could not articulate would not produce that.
It is authored amplitudes, which is far cheaper to fix than a rig.

**Only the twist plane is developed - the plane 0.30.0 worked on.** We measured what we had just built and
called the trunk done.

### The branches

**A. `motion-spine-flex` - the sagittal plane, driven by footstrike.** `spine_flex_deg` is **0.0 in every
gait entry**, walk, trot and run alike. The only sagittal signal is a constant `lean` (8 deg at a run) plus
`lean_bob` at +-2 deg. So the trunk holds a fixed lean and bobs; it never flexes and extends against the foot
hitting the ground. That is a plank pivoting at the hip, and it is the likeliest single cause of "rigid".
Target, from the gait literature: chest-relative-to-pelvis flexion-extension **>= 4 deg peak-to-peak walking,
rising to 6-8 running**, phased to footstrike rather than to mid-swing.

*Warning for whoever builds it:* a once-per-stride Fourier amplitude reads this signal as ~0 because
`lean_bob` lives at 2x. The first pass at this measurement reported flex as 0.1 deg when peak-to-peak was
1.8. **Report peak-to-peak too, or the instrument says "no change" whether the branch worked or not.**

**B. `motion-frontal-plane` - the bend that falls when it should rise.** Lateral bend *drops* from 10.2 deg
walking to 7.6 running. It is written into `upper.defaults`: `pelvis_list` is `3.0 if running else 4.0` and
`side_bend` is a flat `1.5` at every speed. Real running has more frontal-plane trunk motion than walking,
not less. Target: bend **~10-12 deg walking rising to ~12-14 running**, and pelvic transverse ROM ~10-15
walking (today 8.3, slightly low) against ~15-20 running (today 17.5, fine). Small edits to a speed curve;
the work is the re-record and proving the plane now rises with speed the way `pelvis_thorax_phase_deg` was
proved to sweep.

**C. `motion-girdle-per-body` - the 6x spread.** The same authored `girdle_drop` (2.5 deg walking) produces
**18.2 mm on Marco and 3.1 mm on Belle and Mei**. The code's own comment says "a couple of degrees on a
clavicle is about a centimetre at the shoulder"; on half the cast it is a third of that and invisible - which
is very likely why "shoulders drop slightly when they step" does not read. Either solve the degrees for a
target displacement per body, or establish that the difference is genuine clavicle geometry and the authored
value is simply too small for slim bodies. Target ~8-12 mm on every body at a walk, **with the measurement
saying which of the two explanations it was.**

### How to measure any of it

`grungist-creek`'s `motion_demo.tscn` is the before/after for this whole round and needs no changes: four
bodies side by side, all three planes, shoulder dip and its half-cycle separation, measured live off the
playing skeleton by an independent reimplementation of `upper.relative_phase` that never reads the manifest.

    "$GODOT" --headless --path . motion_demo.tscn -- --selftest

**The shoulder-dip measurement is worth reading before writing another one.** It took four attempts and the
first three failed for *different* reasons: shoulder-minus-chest height in skeleton space picks up the
spine's own motion; in the chest's frame it is identically zero, because the girdle bone rotates about its
own root and never translates; and the girdle's roll cancels exactly between two mirrored sides. What works
is the arm root's height in a frame that rides the chest, plus a per-side sign. All three wrong answers
looked plausible, and two of them produced numbers that varied with speed.

## Resuming the motion work (2026-09-20) - CLOSED, kept as the record

The round is done, merged and pushed; nothing here needs resuming. It is kept because what each
version established, and what it cost to get right, is the context the next motion branch needs.
The design and the reasoning are in
[07-motion-that-reads-as-alive.md](07-motion-that-reads-as-alive.md).

**Where the code is.** `C:/Users/pauli/Code/blender-godot-plugins`. NOT
`~/.claude/plugins/marketplaces/blender-godot-plugins`, which is a stale 0.14.2 cache that looks
like the repo, has its own git, and will happily let you commit into it. An hour went into that this
round, and `tools/install.py` run from it downgrades the installed skill.

**Branch state - all merged AND pushed (2026-09-21).** The round's branches
(`motion-mass-model`, `motion-head-rung`, `motion-asymmetry`, `motion-jitter`, `moves-mass-cache`
and the game's `girdle-rebuild`) are merged and deleted; both repos went up through
[plugins#2](https://github.com/wfbcargo/blender-godot-plugins/pull/2) and
[grungist-creek#1](https://github.com/wfbcargo/grungist-creek/pull/1). `main` and `master` are in sync
with origin, and the only branch left anywhere was the parked `fig-genital-anatomy` (since merged).

**All six figures are on 0.37.0** - study_man, study_woman and Belle from the ship step, the cast
(Marco, Mei, Ruth) rebuilt 2026-09-21 - and every one of them carries `[variability] asymmetry = 0.35`
with a seed drawn from its own id.

### What shipped, and what each one established

- **0.28.0 `mass.py`** - per-bone mass, centre of mass and inertia from the skin, in each bone's own
  rest frame. The whole body from its surface exactly; the partition between bones **volumetrically**,
  because a weighted surface integral does not partition a volume. Inside is a **winding number**, not
  a parity, because a body is ~27 overlapping shells. 17 closed-form self-tests, no Blender needed -
  from `plugins/rig-anything/scripts`, run `python -m rig_analysis.mass`.
- **0.29.0 the shoulder girdle** - `bodymap` had named it since 02 and nothing posed it. Each shoulder
  drops as its own side takes the weight; two dips a stride, half a cycle apart.
- **0.30.0 the trunk lag** - `upper.response` is the driven-oscillator transfer function. The thorax
  chases the pelvis instead of mirroring it, **and the sign is nowhere written down**: half a cycle of
  lag IS anti-phase, as the fast limit.
- **0.31.0 the limb pendulums** - `mass.pendulum` gives the arm 0.91 Hz and the hand 1.60 Hz from
  measured mass alone. The hand's lag is derived from it (`HAND_LAG` is gone). The **arm's is not**,
  because `mass.angular_momentum` says the half cycle is already optimal - see 07 for the sweep.
- **0.32.0 the head rung**, **0.33.0 the fixed asymmetry**, **0.34.0-0.36.0 the runtime jitter** - each
  written up under "Next, in the order I would take it" below, which is the round's own record of them.
- **0.37.0 a body is measured once, not once per clip** - the round's own regression, fixed at its
  cause. `mass.body_mass` caches on the `motion.Body` it is handed, but **every role builds its own
  Body**, so the cache was empty every time and fell through to `load() or measure()` - and `load`
  reads a stamp that **nothing in the repo ever writes**. Belle's seven-role set: 4 `measure()` calls
  and 18.42 s, to **1 and 12.28 s**. A process memo and deliberately NOT the stamp, because
  `export.py` sets `export_extras: True` and stamping would write a per-bone mass table into every glb
  the pipeline ships. The key hashes vertex **coordinates**, because the flesh stage moves a body
  without changing any count and a silently stale inertia tensor is worse than a slow build.

### The instruments that now exist

Everything below is measured off the **baked** clip, never the prediction, and lands in the gait
report (so in `tests/golden/`):

- `pelvis_thorax_phase_deg` - relative Fourier phase, thorax against pelvis. **The headline number**:
  it was a flat -179.3 at every speed and now sweeps -53 (0.36 m/s) to -157 (4.59).
- `angular_momentum.up_range` / `.up_mean_abs` - normalised whole-body angular momentum, `L / M H V`.
  Reads sensibly across body plans: quadruped trot 0.008, biped walk 0.060, cricket 0.107. **Reported,
  never gated** - nobody knows the healthy band for a hexapod.
- `upper.limb_hz`, `upper.arm_lag_cycles`, `upper.hand_lag_cycles`, `upper.trunk_lag_deg`.

`mass.angular_momentum` is the arbiter for any "should this move differently?" question, and it has
already settled one. Reach for it before reaching for an opinion.

### The one red row the round ships with (blocker on `main`, 2026-09-20)

`regress --godot` is red on `main` by itself, and it was still red after the ship step: exactly one
row, **`verify_strands pipeline_ponytail`** - a strand goes 0.0060/0.0065/0.0067/0.0067 m into the
head at 30/60/120/240 fps against a 0.005 bound, `swing_spread` 1.050. It read 0.0038-0.0039 m and
passed before `motion-head-rung` and `motion-asymmetry` merged.

**It is a live defect, not only a fixture's.** The ship step ran `verify_strands.gd` on the game's
own rebuilt `study_woman` at 60 fps: `run_head_penetration_m` **0.0053**, failing the same check.

**Where it is, measured** (ship notebook section 6). `run_penetration_at` names the bone:
`ft_strand_StudyWoman_hair_strand_00` - the strand's **root**, 0.001 m outside the skin at rest, with
`run_limit_hits` 643 and `run_peak_bone_angle_deg` 53.94 against a 60 deg root limit. The collision
solver keeps four sample points *along each bone's centreline* (grown by the strand's radius and the
4 mm margin) out of the colliders; the tie's skinned vertices swing wider than that centreline, and
the penetration is measured against the **skin**. So the root's swing carries its vertices through a
scalp its centreline never enters.

**The head collider's size is ruled out, precisely.** The ship step grew the head ellipsoid until it
enclosed the skin (7.4 % of study_woman's head skin stood outside the old one, worst 16.6 mm, at the
nape). The collider moved as intended (`radius_m` 0.1191 -> 0.1355, `fit` 1.1375) and the settled
swing moved 109.08 -> 113.91 deg, and **the penetration did not change by one digit**. Reading
`strand_modifier.gd` back says why: each bone's limit is `minf(1.0, k_rest - eps)`, the collider's
surface *or its rest gap, whichever is tighter*, so a root grown into the scalp is pinned to its rest
gap and a bigger collider cannot move it. That attempt was reverted; the repo is back at `main`.

**Still unowned.** The fix is the root's angular limit or keeping a bone's skinned envelope (not its
centreline) out, either of which moves `tests/golden/pipeline_ponytail.json` and
`strand_ponytail.json` and needs its own `--godot` run and its own control. Take it as a branch.

The ship step's own notebook, with the rebuild numbers, every verifier line, the regress result and the
blocker's diagnosis: [notebooks/motion-alive/ship.md](notebooks/motion-alive/ship.md).

### Next, in the order I would take it

1. **The head rung: done** (branch `motion-head-rung`, rig-anything 0.32.0, merged 2026-09-20).
   `upper.trunk()` now takes `head=` - the top of the chain's own drive as a *signal* - instead of
   scaling the thorax's *value*, and `upper.head_frequency` derives the lag from `mass.pendulum` over
   the neck and everything above it (0.908 Hz on the lofted Rigify figure, 1.089 Hz on an MPFB woman).
   Measured off the baked clip the rung sweeps 100-110 deg across Froude 0.03-2.0 where it read a flat
   -0.6 before; `pelvis_thorax_phase_deg` is unchanged. The control is permanent in the fixture
   (`HEAD_RUNG_CASES`, `head_lag = 0.0` reads flat and fails). **Caveat worth carrying:** on both
   bodies the head-and-neck centre of mass sits *above* its pivot, so `sqrt(mgd/I)` there is a
   divergence rate, not a free resonance - the restoring stiffness is the neck's, which nobody has,
   the same gap that leaves `trunk_hz` fitted at 0.82. Recompute if a real neck stiffness appears.
   `mass.angular_momentum` is flat across head lags, so nothing independent arbitrates this phase:
   04's motion critic is the arbiter it wants, once the ship step rebuilds the characters.
   `girdle_lag` (0.05) is now the last un-derived lag on the chain, and a clavicle is not a gravity
   pendulum, so it needs a different argument than this one.
2. **L4 variability - the asymmetry half is done** (branch `motion-asymmetry`, rig-anything 0.33.0,
   character-pipeline 0.16.0, merged 2026-09-20). A fixed per-character left/right asymmetry, drawn
   once from SHA-256 of the character's id and baked into every gait clip:
   `rig_analysis/variability.py` owns the seam (`[variability]` = seed, asymmetry, jitter_phase,
   jitter_amp, all default 0), the draw and `measure`, which reads the result back off the **baked**
   clip. Four channels - arm_swing, shoulder_dip, lag, step_length. Belle's walk at 0 -> 0.35: arm
   swing ratio 1.0004 -> 0.8667, shoulder dip 1.0021 -> 1.0178, stance offset +0.03148 -> +0.04097 m
   (a move of 0.00949 against a drawn 0.00950), strides still even so no foot skates. asymmetry 0 is
   the identity **exactly** (literal 1.0 and 0.0, and no `variability` block written), which is why
   every golden held and no existing character reruns. Two controls ship with their False verdicts in
   the golden: `RA_ASYM_MIRROR=1` and `RA_ASYM_NONDETERMINISTIC=1`.
   **Step length is the part to remember:** scaling each side's stroke made the exporter refuse every
   gait ("planted at a different speed"), and it was right - both planted feet sweep back at the
   body's speed. What differs is *where* each foot plants, so it is one shift of `pl["centres"]`.
   **The per-cycle half is now done too** (branch `motion-jitter`, rig-anything 0.34.0-0.36.0, merged
   2026-09-20). `jitter_phase` and `jitter_amp` are no longer parsed-and-ignored: the runtime
   `GaitJitter` warps phase and modulates amplitude per cycle from a seeded persistent series (DFA
   alpha 0.81-0.83 on the three figures, against 0.50 for the white-noise control), off by default,
   LOD-gated past 30 m, and costing 1.5-2.8 us of phase warp and 1.3-2.1 us of modifier per character
   per frame. Stride interval cv 0.026-0.029 on against 0.000000 off; no accumulated drift over an
   hour (worst gap 0.1444 of a 0.2160 bound, trend +0.0084 cycles over 3600 s). Nine must-fail
   controls ship, each declaring every line it fails, and a check the mode cannot measure now reports
   `RA_JIT  SKIP` with the raw numbers instead of passing and printing a bound it did not meet.
   **Two things to decide next round, both about the tracking term:**
   `MovesController.jitter_track = 4.0` is documented as the thing that stops the open-loop offset
   telescoping, and no run supports that - with the term off an hour-long 60 Hz run reads 0.1606
   against 0.1444 with it on, and at 4 Hz the term is the largest contributor to the gap (0.3164 on,
   0.0866 off). And `jitter_track_lead` ships OFF: the error is formed with `_jit_theta` already at
   the end of the tick while `_jit_phi` is still at its start, so the loop settles exactly one tick
   behind - the 0.0167 cycles 0.35.0 called inherent, and it is not. Turning it on also stops the
   `reanchor=target` control failing, so adopting it means reshaping that control: one reviewed
   commit. Until then the 4 Hz limit ships as a control (`tick=0.25` must FAIL "stays inside the
   offset bound"), which is a shipped control encoding a known limitation - read it that way.
   Two smaller ones carried from the critic: the SKIP line names `switch=0.0` even in a tick-only run
   where there is no gait change, and the skate check is named "planted-foot travel is no worse"
   while it enforces 1.25x - on study_man both mean and worst rise with jitter on (0.0360/0.0333 and
   0.3367/0.3279), so the honest wording is "within 25%". SKILL.md's prose still says eight controls
   where there are nine.
   **Still open across both halves:** only `locomotion.cycle`'s roles (Walk, Trot, Run) take the
   asymmetry, and jitter reaches Idle and `play_gait_for` but not one-shot roles through `play_role`
   (Jump, TurnL/R) - turns are L5's. Godot's JSON parser truncates the manifest's 19-digit seed, so
   the series Godot draws is not the one Blender drew; the fix is `variability._MASK`'s file on main
   and it moves `tests/golden/rigify_human.json`, one reviewed commit with
   `regress --only rigify_human --update --twice`. **The ship step put `asymmetry = 0.35` on
   study_man, study_woman and Belle** (2026-09-20) and rebuilt all three: `verify_moves` PASSED on
   all three manifests (so no foot skate and no "planted at a different speed" refusal),
   `verify_flesh` walk/run/jump PASSED on all three, and the three demo selftests pass. `asymmetry`
   costs nothing any existing check can see. `jitter_phase`/`jitter_amp` are still 0 everywhere, so
   the runtime half has still never run on a game character, and **no motion critic has looked at an
   asymmetric walk in Godot** - that look is still owed. The cast (Marco, Mei, Ruth) carries no
   `[variability]` and is still on 0.30.0.
3. **L2 proper** - the momentum measurement exists; the *solve* does not. Minimise the residual over
   the free DOFs (arm swing gain, thorax counter-rotation, tail sway) at bake. This is the step that
   makes counter-rotation body-plan agnostic instead of a constant per archetype.
4. **L3 runtime joint springs** - widen `follow_through/jiggle_modifier.gd` from flesh bones to any
   bone, frequency and damping from 0.28.0's inertia. The only layer with a runtime cost; LOD-gate it.
5. **L5 turn sequencing** - eyes, head, trunk, pelvis, feet. Reuses the lag ladder. `TurnL`/`TurnR`
   already exist in the cast manifests.

Two open questions worth deciding before 2 or 3: whether `response`'s **gain** should be applied
(0.30.0 deliberately applies phase only - amplitude is authored, timing is derived), and whether the
arm's 2:1 to 1:1 frequency transition at slow walking is worth modelling (it is the real mechanism,
and it is a big change).

### Rebuilding a character

```
cd /c/Users/pauli/Code/GoDot/grungist-creek
export BLEND_DIR="C:/Users/pauli/Code/Blender"
BLENDER="C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
CP="$HOME/.claude/skills/character-pipeline/scripts/build.py"
"$BLENDER" -b --factory-startup --python-exit-code 1 --python "$CP" \
  -- spec="C:/Users/pauli/Code/GoDot/grungist-creek/characters/belle.toml" from=body
```

Then `--headless --import --path .` and the demo selftests. Belle takes ~45 s, the cast ~60 s each.

### What cost time this round

- **The marketplace cache is not the repo.** See the top of this section.
- **Bump with `tools/bump.py`, not by hand.** The 0.28.0-0.31.0 commits edited only
  `plugins/rig-anything/.claude-plugin/plugin.json` and left `.claude-plugin/marketplace.json` - the
  file other machines read - stale at 0.27.0. `bump.py` then refused outright until the two were
  settled by hand (commit 43af2bf on `motion-head-rung`).
- **A version bump invalidates every stage hash**, so `from=moves` is refused with "rebuild from
  body" and the whole character rebuilds. Expected, but budget for it.
- **Blender 5.2 actions are slotted**: `action.fcurves` is gone; go through
  `layer.strips[..].channelbag(slot).fcurves`.
- **Build the instrument before the change.** The flat -179.3 baseline is what made the trunk lag
  reviewable, and the momentum sweep is what stopped a plausible-but-wrong arm change from shipping.
  Both took minutes.
- **Mei's `hand_back.L` review false alarm is still there** (already known, above: build her with
  `to=export`). Confirmed this round that it is NOT from any of this work - it reproduces on 0.28.0,
  whose `upper.py` contains no girdle code at all.

**How the flesh round was run** (2026-09-18/19, one main session, no `plugin-round` workflow - the user had not opted
into multi-agent orchestration): one branch at a time in its own worktree, a scratch game from
`tools/scratch_project.py`, `regress --quick --jobs 4 --godot <scratch game>`, goldens re-recorded with
`--update --twice`, then **one independent critic subagent per branch** answering done-when questions written before
it started, fixes, a second critic look when the fix touched code, merge, install, rebuild the six figures in the
game (study_man, study_woman, the cast, Belle), `--import`, the four demo selftests and verify_flesh (full course, and
walk/run/jump with `require=within_body`). Every branch's critic caught something real - a crash, a control that had
lost its teeth, a claim the evidence did not support. Keep that step. Lessons that cost time this round:
- **Re-import after rebuilding glbs**: a Godot project plays its cached import until `--headless --import` runs; the
  first D measurement matched the baseline to the last digit because of it.
- **Never bump a version while regress runs**: the stage hashes move mid-fixture and it refuses (`BuildRefused`).
- **A control can go blind when the thing it leans on moves**: the 0.98 jiggle cap made two controls stop failing.
  Prefer a control that tests the mechanism directly over one that depends on a body's exact weights.
- **Probe before tuning**: a 30-line Blender probe on the saved blend (`remove_jiggle_weights`, `find_regions`,
  `check_placement`, or a bust/seat landmark) settled every placement question faster than rebuilding.
- **Blender's Python needs C:/ paths**: a git-bash `/c/...` path in a probe script fails the import.
- Mei's full build still stops at review on the `hand_back.L` off_body false alarm: build her with `to=export`.
- A Godot selftest rewrites `assets/wardrobe/nora.walk.json` (whitespace only): restore it before committing.

Read these first, in this order:
1. The repo's `CLAUDE.md`: worktrees, scratch folders, the regression harness, install and version rules, gotchas.
2. [06-figure-study-lessons.md](06-figure-study-lessons.md): what the figure study round learned, with a
   ranked list of plugin improvements. Section 3 has every failure with its attempts and time cost;
   section 6 has the orchestration lessons. The raw lab notebooks are in
   [notebooks/figure-study/](notebooks/figure-study/).
3. [HISTORY.md](HISTORY.md) only when you need the record of rounds one to three (merge log, old loose ends,
   every number). It was this file until now.

Installed copies in `~/.claude/skills` match the repo (rig-anything 0.38.0 installed by the asymmetry ship step, 2026-09-21). **This is the one list of versions**; update it
here and nowhere else:
- rig-anything 0.38.0 (2026-09-21, branch `asym-godot-meter`, installed by the ship step 2026-09-21, NOT
  pushed: a left/right asymmetry meter in Godot, `AsymmetryMeter` + `verify_asymmetry.gd`, gated by the
  `asym_meter` fixture. grungist-creek `master`'s `addons/rig_anything` matches 0.38.0 since
  `asym-motion-demo` merged 2026-09-21, not pushed)
- rig-anything 0.37.0 (2026-09-20, branches `motion-mass-model`, `motion-head-rung`,
  `motion-asymmetry`, `motion-jitter` and `moves-mass-cache`, NOT pushed: 0.28.0 mass model, 0.29.0 shoulder girdle,
  0.30.0 trunk lag, 0.31.0 limb pendulums and whole-body angular momentum, 0.32.0 the head rung,
  0.33.0 the fixed per-character left/right asymmetry, 0.34.0 the runtime per-cycle jitter with the
  drift check over the whole run, 0.35.0 a gait change no longer nudges the playhead behind, 0.36.0
  a skipped check says so and every control declares what it fails, 0.37.0 the body-mass model is
  measured once per body rather than once per clip - the `moves` regression the benchmark caught,
  fixed at its cause (4 measure() calls and 18.42 s to 1 and 12.28 s on Belle). 0.31.0 and earlier are installed;
  0.32.0-0.36.0 were installed by the ship step on 2026-09-20, and the game's addon copies already
  matched, so `~/.claude/skills` and `grungist-creek/addons` are both on 0.36.0. 0.27.0 was
  2026-09-19 moves-running-flag.
  Bump with `tools/bump.py`: the 0.28.0-0.31.0 commits edited only plugin.json and left
  `.claude-plugin/marketplace.json`, the file other machines read, stale at 0.27.0)
- animate-anything 0.10.1
- follow-through 0.10.0 (the ship step's attempt at the ponytail blocker - a 0.11.0 growing the head
  collider until it encloses the skin - was reverted: it moved the collider and changed nothing the
  check measures. See "The one red row the round ships with")
- humanform 0.17.0 (2026-09-19: 0.13.0 skin-pores-distance, 0.14.0 skin-regions, 0.15.0 skin-finger-edges,
  0.16.0 eye-material; 2026-09-20: 0.17.0 skin-genital, PR #1; installed and shipped)
- character-pipeline 0.16.0 (2026-09-20, branch `motion-asymmetry`: the `[variability]` spec table and
  the manifest's `variability` block. 0.15.0 was 2026-09-19 skin-regions, installed and shipped;
  0.16.0 was installed by the ship step on 2026-09-20)
- wardrobe 0.7.0 (2026-09-21, branch `cloth-bust-hang`: loose tops hang from the bust apex, `fit.tuck`
  and `tuck_limit`, preset `skin` args, fixture `dressed_loose`; installed, Marco and Ruth rebuilt).
  0.6.0 was `cloth-span-loose`: `smooth` and a detail limit on `tshirt` and `longsleeve`
- lookdev 0.12.0 (2026-09-19: 0.8.0 lookdev-golden-hour, 0.9.0 skin-pores-distance, 0.10.0 skin-finger-edges,
  0.11.0 lookdev-overcast, 0.12.0 eye-material; installed and shipped)
- godot-lsp 0.1.0

---

## Where the figures are

`grungist-creek/characters/study_man.toml` and `study_woman.toml` build through character-pipeline at
`quality = "final"` in about 32 s each from nothing (a resumed rebuild skips unchanged stages), into
`assets/figure_study/`, with skin baked at 2048 px. **study_man, study_woman and Belle were rebuilt from body on
2026-09-20** by the motion round's ship step, on rig-anything 0.36.0 and character-pipeline 0.16.0 (study_man
56 s, study_woman 56 s, Belle 55 s wall; every stage ran, because a version bump invalidates every stage hash).
All three now carry `[variability] asymmetry = 0.35` - a fixed left/right asymmetry drawn from the character's
id and baked into every gait - with `jitter_phase`/`jitter_amp` left at 0. **The cast (Marco, Mei, Ruth) was NOT
rebuilt and is still on rig-anything 0.30.0 with no `[variability]`**; it was last rebuilt from body on
2026-09-19 by the Step 2 ship step (Marco 39.1 s, Ruth 40.1 s, Mei 31.5 s to export). All six carry regional
tone, the pore octave, the T-zone and lip roughness and the finger-edge fixes. `figure_study.tscn` shows both on
turntables: keys 1-7 clips (Idle, Walk, Run, Crouch, Jump, TurnL, TurnR), F/S/B/Q/C views (C is a 1 m
close-up, Tab picks the figure), L lighting presets, T turntables, J flesh, H hair strands. Its
`--selftest` passes, as do `belle_demo`, `people_demo`, `cast_demo`, `verify_moves` (six manifests) and
`verify_flesh` (full, walk, run and jump courses on all six: 24/24). Re-checked after the 2026-09-20 rebuild:
`--headless --import` clean (0 ERROR lines), `figure_study`, `belle_demo` and `people_demo` selftests PASSED,
`verify_moves` PASSED on study_man, study_woman and Belle, and `verify_flesh` walk/run/jump PASSED on all three
(9/9, `require=within_body`). **Re-checked 2026-09-21 on rig-anything 0.38.0** (asymmetry ship step, no
rebuild; notebook `notebooks/asymmetry/ship.md`): import 0 ERROR lines, `figure_study`, `belle_demo`,
`people_demo` and `motion_demo` selftests PASSED, `verify_moves` PASSED on all six manifests and
`verify_flesh` walk/run/jump PASSED on all six (18/18). No look renders were made: nothing was rebuilt.
**`verify_strands` on study_woman FAILS** (0.0053 m into the head) - the round's
one open row, above.

To look at them: each build writes the Blender close-up set to
`assets/figure_study/<id>/review/<id>/close/` (`sheet.png`, 16 tiles, `close.json`; the folder is git-ignored).
In Godot,

    node ~/.claude/skills/lookdev/bin/lookdev.mjs close-shot --project .       --glb res://assets/figure_study/study_woman/study_woman.glb --views head,hands,full       --presets clear_midday,overcast --pair-blender assets/figure_study/study_woman/review/study_woman/close       --out <scratch>

writes a sheet with one row per view (face, face_3q, eyes, head_side, head_back, the four hand views, full),
the Blender close-set tile first and one column per preset, in about 20 s (Belle needs `--garments
res://assets/belle/belle_sportstop.glb,res://assets/belle/belle_shorts.glb`). Run it on a copy of the project
(`tools/scratch_project.py`, or a tar copy), not the game itself. The sheets live in `%TEMP%/rw/ship/look/<id>/sheet.png`
(a scratch folder; regenerate rather than rely on it). The motion round's ship step re-rendered **study_man,
study_woman and belle** there on 2026-09-20 (face, face_3q, eyes, head_side and hands at 1 m, full body at 4 m;
clear_midday and overcast; paired with the Blender close set); `cast_marco`, `cast_mei` and `cast_ruth` beside
them are still the Step 2 sheets, which also carried head_back. study_man and study_woman now exit **0**: Step
2's standing failure - overcast `full`, FLOOR_STRIPES at 1.20-1.54 % against 1.20 %, judged then to be a
close-shot artefact rather than the figures - does not reproduce. belle exits 1 on one tile,
`TONE_SHIFT: skin saturation moves -21.0 % from clear_midday to overcast (max 15 %)`, which is a
lookdev-preset row rather than a figure one. Step 2's first look (not an independent critic): pore grain now shows across the face at 1 m; lips and
cheeks read redder; the vertical specular band on the foreheads under overcast is still there, and overcast is still
darker and flatter than clear_midday.

**Judged honestly: clean, well-proportioned CG figures that move properly, not yet realistic.**

| Works | Wrong |
|---|---|
| Proportions (humancheck 0 fail on both) | The man's `short_crop` is still a smooth, dark, slicked shell at 1 m with a hard front line behind the edge hairs (needs volume and colour variation) |
| The woman's skin tone and subsurface in Godot; brows, lashes and eyes at 1 m on all three | His forehead and lips are glossy, in Blender and in Godot; both foreheads carry a vertical specular band under overcast |
| Natural-speed gaits with heel strike and toe off; a run with a flight phase; turns | An orange fleck at the man's thumb web under clear_midday |
| The ponytail swings 44-46 deg on the run at any frame rate | Skin reads smooth at viewing distance: the pore detail is in the material but does not show past about 1 m |
| Flesh bounded on every course; no neck stipple (sun soft-shadow filter) | study_man goes dark and muddy under overcast |
| | **Genital anatomy is opt-in** (`[body] genitals = true`, Step 3 below); the shipped figures build without it |
| | golden_hour overexposes the pale woman and stripes the floor; interior_daylight was dropped from the demo |

**Baseline after Step 0** (independent look critic, Godot close-shot sheets at 1 m and 4 m, clear_midday and
overcast; notebook `notebooks/realism-step0/ship.md`). Ranked, what most separates the figures from real people:
1. **Hair** reads as a helmet: a smooth, hard-edged shell, the hairline a smeared radial gradient, no flyaways,
   a hard dark band in front of each ear. **The Blender close set shows fine strands at the hairline, so
   the look is lost between Blender and Godot**: start Step 1 there, not in the hair layer.
2. **Brows and lashes**: brows are hard, pixelated black cut-outs (darker and heavier than in Blender), lashes
   a few black blocks with one clump spiking over the pupil; pupils flat black discs.
3. **Skin**: one uniform colour at 1 m and 4 m, no regional tone, pore grain only in highlights.
4. **Specular under overcast**: hard, mirror-like patches (a vertical band on the forehead, nose, lips) -
   lacquered plastic. Clear midday's sheen is acceptable.
5. **Dithered shadow stipple under clear_midday** on the front of the neck *and on shadowed fingers*,
   visible at 4 m; absent under overcast.
6. **Coloured edges on the fingers**: orange-red at finger edges and the thumb web (clear_midday), pale lines
   at the fingertips (overcast).
7. **Overcast exposure**: study_man goes dark and muddy (reads as a different skin tone); study_woman grey.

**After Step 1** (independent look critic on study_man, study_woman and Belle; notebook
`notebooks/realism-step1/ship.md`). Fixed: the neck and finger stipple (study_woman keeps an orange glow between
the fingers), brows made of hairs instead of cut-outs, a feathered hairline on all three. Still **clean CG at
1 m and full body**. Ranked, what now most separates them from real people:
1. **Hair volume:** above the hairline every head is a smooth glossy shell with painted streaks; the nape and
   sideburns end in a hard cut (on Belle a vertical flap in front of the ear); the ponytail is a flat, banded ribbon.
2. **Skin:** plastic and uniform - no pores, redness or micro-detail - and waxy under overcast.
3. **Eyes:** flat irises, oversized black pupils, no limbal ring or wet line, a dark ring around the socket.
4. **Pose and body:** stiff A-pose/rest pose with rubbery fingers; mannequin-smooth at full length.
5. **Lashes and hairline edge:** too even and comb-like, no clumping or scatter.
6. **Leftover shading:** the orange glow between study_woman's fingers; the man's orange thumb-web fleck.

Close-shot gaps the critic hit: no Blender tile for `full`, no neck view, and the Blender pairs are shot at
0.4-0.6 m against Godot's 1 m, so a pair is not like for like.

---

## The benchmark: a new human in under 30 s that looks great

The `plugin-round` workflow runs it after the ship step when given `benchmark` (the briefs are in
`.claude/workflows/benchmark-briefs.json`; keep them fixed so rounds compare):

| id | brief |
|---|---|
| `bench_marco` | A stocky Hispanic man in his 40s with a strong jaw. |
| `bench_mei` | A skinny, tall Asian woman in her 20s: slim figure, athletic build, long hair. |
| `bench_ruth` | An older Caucasian woman in her 60s: a little heavier in build but fit and healthy, cropped grey hair. |

For each, one at a time so the timings are clean: a scratch project (`tools/scratch_project.py`) with a library
copy that holds no body for the brief; a spec written from the brief with only what a user would choose; three
cold `fresh=1` builds at final quality in a fresh Blender process (median wall time, Blender start-up included,
against **30 s**), a warm rebuild and a one-line `[flesh]` edit; a Godot close-shot sheet paired with Blender;
the three slowest stages; and a **brief-fidelity** list - every part of the brief the tools could not express.
An independent critic then scores the sheet on `lookdev/references/critic-look.md` (pass count), says whether it
reads as a real person, and names each mismatch with the brief.

**Runs so far:**
- [baseline-2026-09-19.md](notebooks/benchmark/baseline-2026-09-19.md): 42.2 / ~41 / 41.7 s; critics
  11/19, 11/18, 10/16.
- 2026-09-20, recorded in [moves-mass-cache.md](notebooks/motion-alive/moves-mass-cache.md): 93.3 / 73.1 /
  90.8 s, the `moves` regression.
- [rerun-2026-09-21.md](notebooks/benchmark/rerun-2026-09-21.md): 43.5 / 42.3 / ~46 s; critics 12/18,
  11/17, 13/18.

**Time on an idle machine.** Another process pinning the CPU inflates every stage together, and it
spoiled most of Ruth's runs on 09-21.

Where it starts: the study figures build from nothing in 34-38 s with every stage rerun (Step 1 ship), and a
fresh body fit alone took 11-14 s in the figure study round. Gaps the briefs will likely hit, from reading
humanform: age is capped at 58 for a fitted adult (ANSUR II has no older adults), so Ruth's 60s need handling
past the fit; MPFB's ancestry macros are asian/caucasian/african only, so "Hispanic" needs a mapping to a mix
plus skin tone; no confirmed jaw-shape control in the brief; `long_loose` hair is still rigid (Mei); Ruth's
cropped grey hair is `short_crop`, whose shell is the critic's first complaint.

**The cast demo (2026-09-18): the first new characters from briefs.** `grungist-creek/cast_demo.tscn` shows
`characters/cast_marco.toml`, `cast_mei.toml` and `cast_ruth.toml` (the three benchmark briefs, built by hand from
specs with the installed plugins: Marco 40.6 s, Ruth 38.9 s; review 7-8 s and bake 7-9 s are the biggest stages).
**The user's review, recorded as given:**
- Something jiggles on their mouths that looks unnatural (all three).
- Marco's chest and stomach jiggle together, in the same motion, far too much - it looks very odd.
- Walking and running are very stiff: animation work to do.
- Breast and butt jiggle does not feel correctly weighted; the point of attachment and the weight distribution
  are the likely cause.

**Diagnosed and researched: [research-flesh-jiggle.md](research-flesh-jiggle.md).** The mouth jiggle was
follow-through's breast search landing on the lips and chin (Mei's and Ruth's breast bones sat on the face, so their
breasts did not move at all); Marco's belly region was his whole front torso, 0.92-1.31 m. Fixed at spec level in the
game (`72effe5`: hand-marked `[[flesh.zones]]`, Marco's belly off). The plugin changes, ranked, with checks and
controls, are items A-G there: bone placement and a zone check first, then graded weights from the attachment, the
pivot at the upper attachment, an asymmetric spring, mass-scaled response, and spec material overrides.
**A and G: done** (branch `flesh-zone-placement`, follow-through 0.7.0, character-pipeline 0.13.0, merged to main
2026-09-18; installed and shipped: grungist-creek `3b30199` drops the cast's hand-marked zones, rebuilds Marco,
Mei and Ruth, cast_demo selftest and verify_flesh full/walk/run pass, breasts peak 5.4-5.7 cm on the run). Face vertices never seed a region, a breast keeps the patch nearest its zone
centre a side, and `flesh.check_placement` fails a bone or weight centre above the chin or outside its zone, or face
weight over 2 %; the pipeline's flesh stage fails on it (`MISPLACED`). Built without hand-marked zones in scratch, Mei
and Ruth's breast bones sit on the breasts (weight at the bust point 1.00 / 0.99, was 0.00). pipeline_woman's golden
had the same chin bug; it now carries the `FT_FLESH_LEGACY_PLACEMENT=1` control. The breast zone top stays 1.45
(1.0 broke the sample Figure's sports top and changed nothing on the cast). Independent critic: pass. Open: tail
5.7-8 cm from the bust point (item C); a rig with no head bone found passes the face tests silently; no escape for a
deliberate mark outside a zone; "above the fold" unchecked. Next: B+C, D+E, F. Notebook:
[notebooks/flesh-cast/flesh-zone-placement.md](notebooks/flesh-cast/flesh-zone-placement.md).

**B and C: done** (branches `flesh-graded-pivot` and `wardrobe-apex-cover`, follow-through 0.8.0, wardrobe 0.5.2,
merged 2026-09-18). Breasts and buttocks hang from above: pivot 3-6 cm over the apex, tail on it (shipped 0.5-3.8 cm
from the bust point), weight 0 at the attachment and on the thigh; check_placement tests it. It exposed a wardrobe
false positive (skin beside an armhole rim counted as through the cloth; runaway lifts), fixed. Critic: mergeable.
Open: a direct second `flesh.prepare` on a fleshed body can fail the check (fix with D+E: cap the jiggle share
below 1); the plain jump course fails on_limit for the cast (10.2-10.9 %; D is the fix); FACING_MIN vs cover's
fold rules. Notebooks: [flesh-graded-pivot](notebooks/flesh-cast/flesh-graded-pivot.md),
[wardrobe-apex-cover](notebooks/flesh-cast/wardrobe-apex-cover.md). Shipped: grungist-creek rebuilt cast, study figures and Belle; selftests and verify_flesh 24/24 pass. Next: D+E.

**D and E: done** (branch `flesh-spring`, follow-through 0.9.0, merged 2026-09-19). The jiggle spring is solved per
axis: soft_fat 2.4 Hz above rest, 2.8x below, 1.4x front to back (a breast floats up and stops hard); a kick
selftest runs in `regress --godot`. Mass-scaled frequency is built but off: the swing limit, not the spring, bounds
amplitude on every body. The 0.98 jiggle-share cap closes B+C's re-run item. Critic: pass. Open: the jump-only
course stays over its 10 % line for the cast (D did not fix it); walking in phase 0.69-0.85 against people's 0.66;
running amplitude ~6 cm against ~15 cm, bounded by the limits; E's lag and mass-scaled response. Notebook:
[flesh-spring](notebooks/flesh-cast/flesh-spring.md). Shipped: grungist-creek rebuilt (cast, study figures, Belle), selftests and verify_flesh 24/24. Remaining flesh item: F (spec overrides, Marco's belly).

**F: done** (branch `flesh-overrides`, character-pipeline 0.14.0, follow-through 0.10.0, merged 2026-09-19). A spec's
`[flesh] overrides` sets jiggle parameters per type or region. The belly's zone stops at 0.6 of the span and it hangs
from the lower ribs, so it no longer takes a man's chest (the research's cause 2); it ships limit_share 0.6. Marco's
belly is back at 4.5 Hz / 0.6 (1.2 cm walking, 1.3 running). Critic: pass. Open: study_woman's belly missed by
0.0001 m (may_miss stays); an empty above-apex window reads 0.0; registry.define lacks the attach keys. Notebook:
[flesh-overrides](notebooks/flesh-cast/flesh-overrides.md). **All of research-flesh-jiggle.md's A-G are now done**, and shipped: grungist-creek rebuilt with Marco's belly on, study_man's workaround gone, 24/24 verify_flesh.

Also seen: garments are cut from the skin, so Ruth's long-sleeve top shows her nipples through it (a smoothing pass
on the cut surface).

Also found building them:
- **rig-anything close-up check, false alarm:** Mei's `hand_back.L` tile is framed well but fails `off_body`: the
  check tests one pixel at the landmarks' centroid, which falls between her spread fingers (the mirrored `.R`
  passes by a pixel). Her build stopped at review, so her blend was not saved. Test a neighbourhood or the nearest
  body pixel within a radius, with a control.
- **Brief fidelity:** no ancestry field (Hispanic and Asian carried only by skin, iris and hair colour, so the
  faces do not read as either); "stocky" via `build = "heavy"` reads average; the strong-jaw face part is too
  subtle; Ruth's face has no age at 64 (no age lines or skin change); `long_loose` is shoulder length, rigid and
  helmet-edged.
- **Godot runs rewrite committed JSON:** `addons/lookdev/presets.json` came back reformatted (content identical)
  after the cast selftest and shots, like `assets/wardrobe/nora.walk.json` in the Step 1 ship step. Find the writer.

---

## The realism work, in order

The goal: new characters read as real people at 1 m and at full body, in at least clear_midday and overcast,
and move like people - proven on the two study specs and on the benchmark, built through the pipeline and
looked at in Godot, not only in a fixture.

### Step 0 - make the look loop fast (do first; everything after is a look loop)

Last round, at least six agents wrote their own render scripts, framing the hands failed three times,
and a close-up that would have shown a defect was missing twice. Fix the loop before the looks:

- **06 rank 1 - a close-up look set in the review stage: done** (branch `cp-close-look-set`, rig-anything
  0.25.0, character-pipeline 0.9.0, merged 2026-09-18). rig-anything `closeups.look_set` renders lit EEVEE
  tiles of the Idle clip's frame 1 - face, face_3q, eyes, head_side, head_back, palm and back of each hand,
  bust, crotch, knees, feet, foot_inner.L, foot_outer.L at 0.4-1 m, and a 0.42 m under_bust for a spec
  wearing a top - with cameras aimed from the posed bones, a label band per tile, `sheet.png` and
  `close.json`. The review stage writes `review/<id>/close/` and fails on an empty, off-centre or
  off-body tile (wrong-bone and empty-tile controls in pipeline_woman). All views at final (+2.8 s),
  6 at preview, face and left hand at draft (0.64 s); `[review] close = false` turns it off. SKILL.md
  maps each look-checklist question onto its tile; an independent critic answered the checklist from
  the PNGs alone. Open: the framing check is centroid-only (a palm camera 6 cm up passes with the
  fingertips cut off - needs every subject point inside the tile, with a control); hand_back looks from
  the side of the curled hand (thigh fills half the tile, nails not visible); `close = false` leaves a
  stale close/ folder and still hashes the close part; the preview set was never built on a real spec;
  only the left foot has side views; a non-human rig needs `close = false`. Defects the set shows
  (hairline, glossy forehead and lips, sparse lashes, Belle's missing brows and under-bust shelf, smooth
  crotches, unmodelled ankle bones and arch, a red streak on study_woman's right thigh) belong to later steps.
- **06 rank 8 - Godot-side look tools in lookdev: done** (branch `lookdev-godot-tools`, lookdev 0.4.0,
  merged 2026-09-18). `lookdev.mjs close-shot` loads a glb, applies lookdev materials, poses a clip and
  writes a labelled sheet (face, eyes, palm and back of each hand, feet, bust, crotch, full body,
  `bone:<name>`) with cameras aimed from posed bones, under named presets; it fails on a missing
  skeleton or bone, an unknown clip, or an empty/small/off-target tile. `lookdev.mjs tone` probes a
  glb's albedo; `lookdev_presets.gd` applies `presets.json` (now in the addon) at runtime, and
  `figure_study.gd` uses it instead of its own port. interior_daylight is marked `needs: interior` and
  refused on an open stage. `lookdev.mjs selftest` runs 11 controls. Open: no control for close-shot's
  post-render tile checks and no `--min-subject` flag; `tone --expect` only reports; `tone` with no
  `--material` fails on study_woman's lashes (0.0073 under the 0.01 floor); `sky_openness` calls a
  runtime-built scene open (the refusal should name `--stage`/`--force`); `LookdevPresets.apply` can
  leave the Environment half-changed when it returns not-ok; close-shot and the selftest are not in
  `regress --godot`; bone aliases cover Rigify/rig-anything and Mixamo only; tone writes its default
  output under the shared `%TEMP%/lookdev/`. Defects the close-ups show (fingertip and neck stipple,
  orange palms on study_man, stair-step sun shadows at 1 m, clumped lashes) belong to steps 1 and 2.
- **06 rank 3 - rebuilds that match what changed: done** (branch `cp-resume-hashes`, character-pipeline
  0.8.0, follow-through 0.6.1, merged 2026-09-18). `runner.build(resume=True)` (build.py, run.sh, the game's
  build_human.py/build_belle.py) opens the spec's saved blend; `fresh=1` builds from nothing. bake, hair,
  flesh and garments hash the code and data they read (`inputs.py`) and a rerun names what changed;
  `runner.plan()` gives the hashes. A `[flesh]` edit on study_man reruns flesh..review in 18 s against 31 s
  (06 estimated 12 vs 25); on a dressed spec it restarts from body (fixed at merge: it refused). The
  `pipeline_hashes` fixture flips 19 inputs, each with a drop-control. follow-through 0.6.1: a second
  flesh.prepare gives the jiggle weight back; limit_influences keeps weight totals. Open: a resumed flesh
  rerun is within 0.074 of a fresh build's weights; moves/export/review (17 s) still rerun after a flesh
  edit; body, moves, strand, export and review name no code files (rig-anything's covered only by its
  version); from=bake on a haired body refuses; a dressed spec's flesh edit rebuilds everything; no
  dedicated control for the limit_influences fix; three pipeline_hashes flips lack drop-controls (both done
  in Step 0.5, critic-checklists-controls).
- **06 rank 12 - bake at final size: done** (same branch). Final bakes skin at 2048 px, preview and draft
  at 1024; the size is in the bake hash, and the manifest has a `skin` block (map_px, tone_ok, region
  tones). It adds about 7 s to a final bake. The game's study_man, study_woman and Belle were rebuilt at
  2048 px by the ship step (below).
- **06 section 5 - repo tooling: done** (branch `repo-regress-quick`, merged 2026-09-18). `regress.py`
  runs longest first, prints results as they finish, ends with `REGRESS DONE exit=N, K fixtures ok`,
  always writes a diff file, and has `--quick` (fixtures selected from the git diff; `--dry-run` shows why).
  `tools/bump.py` does version bumps; `tools/test_tools.py` checks both. A full `--quick --jobs 4` took
  about 3.5 min. Open: mpfb_woman_curvy's glb readback sits under the VOLATILE key `export.file` and is
  never compared (renaming it moves goldens); `--restamp` and refusing `--update` off main are not done;
  DURATIONS is a static table; addon sync and `.gitattributes` from the same list are not done.

**Step 0 status: done and shipped (2026-09-18).** All four branches merged; `~/.claude/skills` and the
game's addons match `main`. The ship step rebuilt study_man, study_woman and Belle in the game at final
quality (skin at 2048 px, close sets written) and they pass `--import`, the figure_study, belle_demo and
people_demo selftests, verify_moves (3 manifests) and verify_flesh (full, walk, run, jump on both figures).
`regress.py --twice --jobs 4 --godot` on `main`: `REGRESS DONE exit=0, 21 fixtures ok`, no change, 14 min.
One stale check fixed in the game: belle_demo's HAIR line wanted lookdev to set exactly one material, and
the baked skin is now a second one. What stays open is listed under each item above; the ones that bear
on the look loop first are close-shot's missing tile-check control and `--min-subject`, the look set's
centroid-only framing check and side-on hand_back, and neither close set being in `regress --godot`.
The round's lab notebooks: [notebooks/realism-step0/](notebooks/realism-step0/) (`repo-regress-quick`,
`lookdev-godot-tools`, `cp-resume-hashes`, `cp-close-look-set`, `ship`).

### Step 0.5 - tooling and plugin items to build first (branches of about 30 min, run in parallel with Step 1)

Suggested after the Step 0 round; each saves agent minutes on every later round.
- **`tools/scratch_project.py <dir> [--who study_man,...]`: done** (branch `tools-scratch-project`,
  character-pipeline 0.11.0, merged 2026-09-18; the game's specs and `build_human.py` merged to master too).
  One call copies characters, build scripts, root scenes, addons (the checkout's), the chosen blends and
  exports and the humanform library, writes `env.sh`/`env.ps1`/`build.sh` and runs `--headless --import`
  (about 5-9 s). With it, **06 rank 2**: a relative `[export] blend` resolves under `$BLEND_DIR`, else the
  project; `runner.build` refuses to save outside both unless `save_outside=True`. All 19 game specs are
  relative; `build_human.py` sets `BLEND_DIR` to `C:/Users/pauli/Code/Blender` only for the game itself.
  Fixture `pipeline_paths` (control `PIPELINE_PATHS_NO_GUARD=1`), `test_tools.py test_scratch_project`.
  Critic: pass. Open: the export hash covers the blend string, so each game figure's next build reruns
  export and review once (outputs match, 0 manifest changes); `make()` prefers `$BLEND_DIR` over the game's
  folder and `build_human.py` uses `setdefault`, so a sourced scratch env.sh leaks into the next copy or a
  real build (surprising, never writes the real blends); `rewrite_blend` handles only a double-quoted
  `blend = "..."` line (fails safe); the committed glbs carry a stale `.001` mesh name from a resumed build
  (runner/stages, not this seam); crowd humans and creatures are not copied. Notebook:
  [notebooks/realism-step1/tools-scratch-project.md](notebooks/realism-step1/tools-scratch-project.md).
- **close-shot views the look critic missed: done** (the stipple detector came with `hair-godot-transfer`,
  lookdev 0.6.0; branch
  `lookdev-closeshot-views`, lookdev 0.5.0, merged 2026-09-18; the stipple/dither detector belongs to
  `hair-godot-transfer`). New Godot views face_3q, head_side and head_back (a `head` group, in the default
  list), aimed with closeups._aim's formulas so frame widths match the Blender set. One row per view, one
  column per preset; each label sits in a band above its picture, and `full` checks the head's box against
  the band (LABEL_OVER_HEAD, control `--label inside`). Tile checks use each view's subject points
  (OFF_TARGET, SUBJECT_CUT in full; free values in close.json); `--aim-offset view=x,y,z` and `--min-subject`.
  `--pair-blender <close dir>` puts the Blender tile first in each row at its distance and lists unpaired
  views. selftest 11 -> 18 controls. `regress --godot` runs close-shot on pipeline_woman's glb (must pass), a
  camera-offset control (must fail) and the selftest. This also closes the Step 0 open items (tile-check
  control, `--min-subject`, close-shot and the selftest in `regress --godot`). Critic: pass. Open: SUBJECT_CUT
  has no committed selftest control; regress counts the must-fail control ok on any failure, not only
  OFF_TARGET; tile checks are centroid-only (the Blender set's every-point margin is not ported); since
  ra-closeup-framing's `close_off` case removes pipeline_woman's close/, regress's close-shot row runs
  unpaired (`--pair-blender` is still covered by the selftest's fake set; regress should keep a close set
  and fail when an expected pair is missing); `full` never pairs and Blender's crotch, knees, under_bust and
  foot side views have no Godot twin; a sheet over 16384 px is cut, not split; `--columns` is gone. Notebook:
  [notebooks/realism-step1/lookdev-closeshot-views.md](notebooks/realism-step1/lookdev-closeshot-views.md).
- **The look set's framing: done** (branch `ra-closeup-framing`, rig-anything 0.26.0, character-pipeline
  0.9.1, merged 2026-09-18). Every subject point (wrist, knuckles, fingertips; both eyes; ankle, heel, toe
  tip) must project 0.04 inside the tile, next to the centroid check. A failure is `cut`, and the free
  `subject_margin` goes in close.json. A palm camera 6 cm up fails [cut, off_centre]; at 3 cm only cut
  fails (pipeline_woman controls). hand_back looks from the front, a little below the knuckles (from above,
  the curled tips hid the nails). A far clip keeps the thigh out, so coverage is 0.30, down from 0.66-0.80.
  New foot_inner.R and foot_outer.R views. `[review] close = false` clears close/ and drops the close part
  from review's hash (pipeline_woman close_off, pipeline_hashes row, each with a control). Open: ring and
  pinky nails are hidden; the thigh's shadow still falls on the hand; humanform critic-body.md and lookdev
  critic-look.md still list only the left foot's side views; runner.stage_hash passes `ch` to for_hash, a
  one-line change outside the seam that cp-cascade-stop should keep; non-human rigs need close = false; a
  pale patch at the thumb base belongs to the skin step. Notebook:
  [notebooks/realism-step1/ra-closeup-framing.md](notebooks/realism-step1/ra-closeup-framing.md).
- **Rebuilds that skip what did not change downstream: done** (branch `cp-cascade-stop`,
  character-pipeline 0.10.0, merged 2026-09-18). Flesh saves a digest of what moves reads of its output
  (`inputs.READS_OUTPUT`), and moves keeps a view hash, so a [flesh] edit that leaves rig and weights alone
  skips moves: study_man limit_share edit 12.1 s (flesh, export, review) against 18.1 s. A flesh rerun
  restores the kept unfleshed mesh (`<mesh>:preflesh`), so a resumed glb is byte-identical to a fresh one.
  On a dressed spec, flesh takes the garments off (`stages.undress`) instead of restarting: Belle 24.3 s
  against 46-47 s, identical to fresh. pipeline_hashes: 15 output flips with drop-controls; pipeline_woman
  dressed_flesh_edit with restart and refusal controls. Open: the hem-bone undress path (tee_man) gives
  garment weights up to 6e-8 off fresh and no fixture covers it; marketplace's Since 0.10.0 omits undress;
  `_preflesh` swaps the whole mesh back after a count/geometry/prefix check, so a bake rerun without a body
  restart could lose new UVs or slots (speculative); a chained strand (study_woman) still reruns moves;
  export and review rerun on every flesh edit (review is now the cost); files built before 0.10.0 rerun
  moves once; a [moves] edit on a dressed spec restarts from body; the game's `build_belle.py` docstring
  still says a dressed flesh edit restarts. Notebook:
  [notebooks/realism-step1/cp-cascade-stop.md](notebooks/realism-step1/cp-cascade-stop.md).
- **Critic checklists shipped with the plugins: done** (branch `critic-checklists-controls`, merged
  2026-09-18; lookdev 0.4.1, animate-anything 0.10.1, wardrobe 0.5.1, follow-through 0.6.2, humanform
  0.10.1, docs only). `references/critic-look.md`, `critic-motion.md`, `critic-fit.md`, `critic-flesh.md`,
  `critic-body.md`; see "How to judge \"realistic\"" for how to use them. Open: the Godot close-shot lacks
  a stipple detector (face_3q, head_side and head_back came in lookdev 0.5.0, and critic-look names them); no
  tool renders flesh jiggle in motion, a posed thigh through a skirt or limb clearance in a pose (listed as
  not answerable).
- **Controls still missing from Step 0: done** (same branch). `limit_influences` fixture with the
  stale-write control (fixed 0.0 lost, stale write 0.311731); `pipeline_hashes` drop-controls for wardrobe
  version, final skin size, spec `[flesh]` and final close-up views. Open: limit_influences is not in
  regress.py DURATIONS; `--quick` treats a .md-only plugin change as a plugin change and runs all its
  fixtures (a docs-only rule belongs in regress.py). Notebook:
  [notebooks/realism-step1/critic-checklists-controls.md](notebooks/realism-step1/critic-checklists-controls.md).

### Step 1 - hair

- **Blender to Godot, and the neck stipple: done** (branch `hair-godot-transfer`, lookdev 0.6.0, humanform
  0.11.0, merged 2026-09-18). The stipple was Godot's default directional soft-shadow filter (soft low), not
  the hair: every lighting preset now sets `sun.soft_shadow_filter_quality` 4 through `LookdevPresets.apply`
  (apply_preset warns when the project setting is lower). The hairline smear was the depth pre-pass blending
  mip-averaged strand alpha plus box mips eroding coverage: `LookdevMaterials.coverage_mips` keeps level 0's
  coverage per mip (read from the source PNG, since BC3 moves alpha) and ramps alpha over 0.5 +- 0.25, asked
  for by the hair preset's alpha extras. Brows and lashes blend instead of scissor (darkest 2% of brow over
  skin: study_man Blender 0.158, Step 0 0.078, now 0.133; study_woman 0.285, 0.154, 0.251).
  `strand_texture` card mode, `hair.material(pixels=)`, humanform's brows and lashes go through lookdev.
  New `lookdev.mjs stipple <png> --region` with three selftest controls (selftest 21). Critic: pass. Open:
  study_man's overcast neck keeps a faint stipple (0.399 -> 0.570; ultra does not clear it; likely overcast's
  20 deg angular distance); the filter is set on every preset and its GPU cost is unmeasured; coverage_mips
  makes 1-2 MB uncompressed runtime textures, load cost unverified, no must-fail control; stipple needs a
  skin `--region` and is not in `regress --godot`; the game's committed glbs are not rebuilt (the ship step
  must rebuild study_man, study_woman and Belle to get the alpha changes); no MSAA/TAA, so alpha to coverage
  is unused; Blender's reddish hairline fringe. Notebook:
  [notebooks/realism-step1/hair-godot-transfer.md](notebooks/realism-step1/hair-godot-transfer.md).
- **The man's hairline, lashes and brow shape: done** (branch `hair-hairline-lashes`, humanform 0.12.0,
  lookdev 0.7.0, character-pipeline 0.12.0, merged 2026-09-18). lookdev's strand texture has `edge_*` settings
  (off by default, own random stream): short, thin, leaning edge hairs in front of the dense start; short_crop
  uses 900 per tile and `root_power` 0.15. humanform's `line_u_m` (off by default, 3 cm for short_crop) carries U
  along the hairline so V crosses it squarely at the temples and sideburns (median U-V angle near the line
  26 -> 61 deg on study_man). Denser lashes (upper-lid root coverage 0.736 against Step 0's 0.513), a brief/spec
  `brow_shape` field (natural is the default and unchanged; arched lifts the outer third 2.05 mm), and Belle has
  brows and lashes (`belle.toml`). New hair_presets checks with must-fail controls: fringe ratio (0.161 vs 0.050,
  floor 0.1), line-U angle (57.7 vs 35.5, floor 50), edge wobble, lash root coverage, brow shapes. Critic: pass,
  after one fix round. Open: the short cap is still a smooth, dark, slicked shell at 1 m (needs volume and colour
  variation); short_crop's `uv_tangent_turn` over 35 deg rose 83 -> 246; crossing hairs just above the ear; the
  pale temple line is unremeasured; the fringe floor does not catch losing the edge hairs alone (0.107; the
  golden's hash does) and the edge_wobble control is tautological; the "Since" sentences omit `edge_*` and
  `line_u_m`; humanform SKILL.md's brow/lash colour factors are stale; the game's glbs are not rebuilt (the ship
  step must rebuild study_man, study_woman and Belle). Notebook:
  [notebooks/realism-step1/hair-hairline-lashes.md](notebooks/realism-step1/hair-hairline-lashes.md).
- **Motion: frame-rate independent strands: done** (branch `strand-rate-independence`, follow-through 0.6.3,
  merged 2026-09-18). strand_modifier.gd simulates each strand against the body's motion low-passed at 10 Hz,
  with `SMOOTH_GAIN` 1.1 (property `smooth_gain`; 1 is off) restoring the run's swing: study_woman's ponytail
  swings 44.5-46.3 deg at 30/60/120/240 fps, spread 1.037 start / 1.041 settled (limit 1.25 unchanged;
  1.053/1.040 at 25/33/47/75/165). verify_strands checks a starting and a settled window and reports
  `peak_tip_deg`; `regress --godot` runs it on pipeline_ponytail with two controls that must print their FAIL
  lines (`legacy_integration=true`, 1.31/1.39; `mod=smooth_hz:0`, 1.28 on the start only). figure_study's
  selftest reads the free tip swing (51.4 deg) with a strands-off control. Critic: pass, after two fix rounds.
  Open: SMOOTH_GAIN sits on a steep curve (1.15 -> 56 deg, 1.2 -> 70-82 deg on the bone limits) and
  verify_strands has no swing ceiling, so a hotter preset could whirl unnoticed (retune the ponytail preset's
  response instead); the smooth_hz:0 control's margin is thin and the legacy control's is about zero at odd
  rates; jiggle_modifier.gd likely has the same rate dependence; under 30 fps is not covered; kick_peak_deg
  sits on the 60 deg bone limit; `long_loose` is still not built. The ship step installs follow-through 0.6.3
  (the game carries the addon). Notebook:
  [notebooks/realism-step1/strand-rate-independence.md](notebooks/realism-step1/strand-rate-independence.md).
- **Blender to Godot first.** The critic found fine strands at the hairline in Blender and a smeared shell in
  Godot, and brows darker and harder in Godot than in Blender. Find where it is lost (strand texture
  resolution or mips, alpha mode, lookdev's hair material, card export) before touching the hair layer.
- **The man's hairline.** Replace the hard cut and spiky fringe with a feathered hairline that reads as
  hair at 1 m. The hair layer already has feathering; `short_crop` is its weakest preset.
- **The neck stipple (06 rank 14).** Hair shells should cast a scissor shadow, not a dithered
  depth-pre-pass one. Also: a card mode in `hair.strand_texture` with no opaque middle, and alpha to
  coverage or a mip bias for cards.
- **Lashes and brows.** Lashes that read at 1 m from the front. A brief field for brow shape.
- **Motion.** `verify_strands` fails its cross-rate spread on the ponytail (1.26 against 1.25; the limit
  was not widened): make the strand spring frame-rate independent and add it to `regress --godot`
  (06 rank 13). `long_loose` is still rigid: it needs a sheet of chains or a route to cloth.

**Step 0.5 and Step 1 status: done and shipped (2026-09-18).** All eight branches merged; `~/.claude/skills`
and the game's addons match `main`. The ship step rebuilt study_man, study_woman and Belle in the game at final
quality, and they pass `--import`, the figure_study, belle_demo and people_demo selftests, verify_moves (3
manifests) and verify_flesh (full, walk, run, jump on both figures). `regress.py --twice --jobs 4 --godot` on
`main`, run against a full scratch copy of the game (the permission classifier refuses it on the real project,
which it stages files into): `REGRESS DONE exit=0, 23 fixtures ok`, no change, 21 min. Godot close-shot sheets at
1 m (clear_midday, overcast) of all three are listed under "Where the figures are". No independent look critic
was run by the ship step. Still open from Step 1: the short cap's volume and colour variation, `long_loose`,
and each branch's open items above; a demo selftest rewrites `assets/wardrobe/nora.walk.json` with tabs
(whitespace only; restored). Notebook: [notebooks/realism-step1/ship.md](notebooks/realism-step1/ship.md).

### Step 2 - skin

- **Detail that survives distance.** Pores exist as a Godot detail normal on UV2 but vanish past about
  1 m. Add mid-frequency variation: tone and redness by region (knees, elbows, knuckles, face, the
  soles), and a roughness map by region so the forehead and lips stop reading as gloss.
  **Status: pores at distance merged (2026-09-19, `skin-pores-distance`, lookdev 0.9.0, humanform 0.13.0; not yet
  shipped - the ship step must rebuild every figure from body, since skin.DETAIL is in the bake hash).** The pores
  vanished to mip averaging: at 1 m the face samples mip 3.1 of the detail, where a 0.3 mm pore is 0.67 texel.
  A second, coarser octave (pits and furrows of 2-4 mm, in the normal and as a detail-albedo cavity, mips faded
  to flat under 3 texels, one shared 1.49 MB texture, ~150 ms once per session) shows grain across the skin at
  1 m and leaves full body as main. New `lookdev.mjs grain --region cheek --min 0.40 --max-finest 2.0`: main
  0.16-0.38 % fails SMOOTH, branch 0.47-0.94 % passes. Critic: pass. Open: the cavity adds only 10-20 % of the
  grain (its docs overclaim it); stale numbers in the notebook (limits 0.40/1.5) and skin.py (2.3 MB); the
  forehead in the eyes tile reads a little orange-peel; thin grain margins, set for 640 px tiles only; regional
  tone, redness and roughness are still to do. Notebook:
  [notebooks/realism-step2/skin-pores-distance.md](notebooks/realism-step2/skin-pores-distance.md).
  **Status: regional tone and roughness merged (2026-09-19, `skin-regions`, humanform 0.14.0, character-pipeline
  0.15.0; not yet shipped - the ship step must rebuild study_man and study_woman from body).** The tone was lost
  before the bake: region tints at dE 2.6-3.2, palms and soles redder than the skin, the palm mask on the feet, the
  knee weight short of 1. Knees, elbows, knuckles, lips and cheeks now read redder at 1 m and full body (knee dE
  9.1/12.4, main 3.0/3.3), palms and soles paler by the brief's tone (skin.pale_tint), T-zone roughness 0.47 and lips
  0.45 (main 0.41/0.37). The manifest's skin block carries contrast per region, contrast_ok against CONTRAST_FLOOR
  and baked roughness; HF_SKIN_LEGACY_REGIONS=1 is the must-fail control. Critic: mergeable, pass=false on one
  item - study_woman's palm still reads darker than the lit wrist (the cupped palm gets 0.53-0.58 of the wrist's
  light; needs a lighting or pose change, lookdev's); study_man's palm only equals the wrist. Open: pale_tint not
  checked against a palm/dorsum dataset; nipple, genital and nail tints untuned and unfloored. Notebook:
  [notebooks/realism-step2/skin-regions.md](notebooks/realism-step2/skin-regions.md).
**Step 2 status: four branches merged and shipped (2026-09-19).** The ship step installed humanform 0.15.0, lookdev
0.10.0 and character-pipeline 0.15.0, synced lookdev's addon into the game, rebuilt study_man, study_woman, the cast and
Belle from body (Mei `to=export`: the known hand_back.L off_body false alarm), and they pass `--import`, the four demo
selftests, verify_moves and verify_flesh 24/24. Regress on a copy of the game: exit 0, 23 fixtures ok, no change,
18 min (lookdev selftest 32/32). Open from the ship step: **close-shot carries state from one preset into the next** -
overcast rendered after clear_midday read 0.4-0.6 % more floor-stripe contrast than overcast alone and failed
FLOOR_STRIPES on every figure. **The symptom is gone since lookdev 0.11.0** (overcast reads 0.13-0.15 % against a
1.20 % limit, rendered third after clear_midday, on both figures) but only because overcast no longer casts a
shadow at all, so a leaked sun property can no longer draw acne. The cause stands: `LookdevPresets.apply` leaves
on the sun any light property the previous recipe set and this one does not name. Still worth fixing properly
(reset per preset or render each in its own process, with a control that renders overcast after clear_midday).
Notebook: [notebooks/realism-step2/ship.md](notebooks/realism-step2/ship.md).

- **Specular under overcast** and **overcast exposure**.
  **Status: merged and shipped (2026-09-19, `lookdev-overcast`, lookdev 0.11.0).** The mirror-like forehead band
  was not roughness at all: overcast's sun cast a shadow through a 20 deg disc, whose shadow map drew a hard-edged
  band down every forehead and nose. It casts no shadow now, the sky is neutral grey (the blue-grey one moved skin
  hue 1 deg and saturation 8 % down) and exposure is metered on the 18 % probe at 0.75. The muddy tone was mostly
  the stage: close-shot's 7 m backdrop cylinder sat in SDFGI and hid the sky below ~38 deg, so a sky-lit preset
  rendered the figure as if in a courtyard (study_man's skin 0.33 display value against 0.50 with it out of GI).
  New `lookdev.mjs tone-shift` fails when skin hue or saturation moves between clear_midday and overcast, and
  close-shot runs it when it renders both. Notebook:
  [notebooks/realism-step2/lookdev-overcast.md](notebooks/realism-step2/lookdev-overcast.md).
- **clear_midday was metered half a stop hot** - found by the above, because the backdrop had been hiding it.
  **Status: fixed in the same branch (exposure 1.0 -> 0.94).** On the open calibration stage with no figure in
  the scene, `capture --probes` read median display luma 0.61 (day wants 0.3-0.6), grey probe 0.62 (wants
  0.33-0.62) and key 1.073; at 0.94 the key is 1.008 and both gates clear. study_woman's clear_midday full tile
  went 1.42 % past white -> 0.01 %. The three-way stage measurement that settled it (backdrop in GI 0.009 %,
  out of GI 1.423 %, no backdrop 1.421 %) is in the notebook - **the lesson is that close-shot's stage had been
  quietly differing from the stage the presets were calibrated on.**
- **Small defects:** thin orange lines at the finger-web creases and thumb web under clear_midday, pale
  lines at the fingertips under overcast.
  **Status: merged (2026-09-19, `skin-finger-edges`, humanform 0.15.0, lookdev 0.10.0; not yet shipped - the ship
  step must rebuild the figures from body, since the nail roughness is in the bake).** The orange lines were skin
  transmittance: now skin mode, 3 cm, alpha 0.2, and the backlit glow in the finger webs stays. The pale fingertip
  crescent followed only the nail's roughness (added light 33 -> 13, pixels 256 -> 17 over 0.30-0.55); nail rough
  is now 0.55. New `lookdev edges` (transmittance colour on the hand and head_back tiles, a regress check on
  pipeline_woman with an old-transmittance control) and `edges --kind specular` (PALE_LINES, PNG controls in the
  selftest). Critic: pass, mergeable. Open: nail 0.55 reads matte up close; `--kind specular` is selftest-only and
  its 0.4 ratio sits just above a thigh-rim sheen at 0.35x; a thin orange thigh rim under an extreme backlight (not
  a preset); ear glow faint, as on main; `tools/scratch_project.py` copies addons only on creation, so sync
  `plugins/*/godot/addons/*` into a scratch game made before a merge. Notebook:
  [notebooks/realism-step2/skin-finger-edges.md](notebooks/realism-step2/skin-finger-edges.md).
- **Lighting presets on an open stage:** golden_hour overexposure and floor stripes. (interior_daylight is
  marked interior-only since lookdev 0.4.0.)
  **Status: golden_hour merged (2026-09-19, `lookdev-golden-hour`, lookdev 0.8.0; not yet shipped).** The stripes
  were shadow acne at a 7-degree sun widened by PCSS: light_angular_distance 1.0 -> 0.5, shadow_normal_bias
  1.5 -> 3.0, relative exposure 1.0 -> 0.7. close-shot gains SKIN_PAST_WHITE and FLOOR_STRIPES on every full
  tile. study_woman 4.08% past white / 2.76% floor contrast -> 0.00% / 0.32%. Critic: pass. Open: the 0.796
  past-white luma is tied to Godot 4.7.2's default AgX with no control re-measuring it; a faint floor pattern
  (0.53) passes only on the contrast gate; the woman is evenly front-lit (close-shot's sun is behind the camera).
  Notebook: [notebooks/realism-step2/lookdev-golden-hour.md](notebooks/realism-step2/lookdev-golden-hour.md).

### Step 3 - anatomy: genitals (shipped, opt-in: humanform 0.19.0, rig-anything 0.42.0, follow-through 0.11.0, character-pipeline 0.19.0)

`fig-genital-anatomy` was merged up to `main` (a real merge of 310 commits; five conflicts, both sides kept)
and finished. `[body] genitals = true` builds MPFB's shell fused into a man and a relief delta on a woman;
**a spec without it builds exactly as on main** (study_man built fresh on main and on the branch: the glb is
byte-identical, JSON chunk and binary; the manifests differ only in paths and timings).

**What fixed the failed gate: the shell's flat rim.** MPFB's helper does not rise from the body at its open
loop - it spreads over the crotch as a flap about 1 mm off the skin, out into both groin folds (262 of its
763 subdivided vertices within 3 mm of the body, 37 mm off the midline). Cut out and zipped, the flap
replaced that skin with vertices on the pelvis while the skin round it moved with the thighs, so a flexed
thigh swept 23 mm into it, and it creased into a collar when the thighs spread. `fuse` now drops it
(`genitals._trim_flush`, 198 faces on the study man): the body keeps its own crotch skin and the shell joins
where it stands out. The per-frame corrective bones stay, with wider caps (5 cm, 32 deg, squash 3 cm).
The fixture `pipeline_genitals` gains `crotch` and `crotch_within_limit` (golden re-recorded, `--twice`).

**The gate is absolute: `genitals.CLEAR_LIMIT_MM` = 15 mm**, the deepest a thigh may go into the part in
any clip (`verify.crotch_clearance` `part_mm`). At 0.45 m in Godot a thigh 1.5 cm into a ~5 cm scrotum reads
as soft contact; the moves stage prints a line for every clip over it. Study man, `part_mm` on the branch as
parked (rebuilt on main) -> shipped: Idle 0 -> 0.7, Walk 5.7 -> 6.0, Run 12.5 -> 12.4, **Crouch 23.3 -> 5.5,
Jump 23.3 -> 4.8**, TurnL 6.9 -> 7.5, TurnR 6.7 -> 4.7. All under the limit.

Found and fixed on the way:
- **The fuse shifted every hm08 index** after the crotch (it deleted the cut's body vertices), and what reads
  MPFB's index lists after the bake landed on the wrong vertices: the man's brows and lashes came out 692
  vertices short. The cut vertices are now kept as loose points (glTF exports none).
- **The seam spanned two UV islands** (the shell's loop kept MPFB's helper UVs), and the skin bake drew each
  seam face as a wedge across the atlas: a hard-edged pink band over the groin in Godot. The shell's side of
  the seam takes the body's UV under it; the shell itself is marked genital skin (it read pale).
- **The shell moved the belly's flesh bone** 2.7 cm down and off the midline (it shaped the spine's lean
  envelope) and failed the placement check. A flesh type's `reserved_attr` (`genital`: `hf_genital`) keeps a
  part out of every other type's search and out of the envelope.
- **`genital_shape` 0..1 is an adult's range** (`SHAPE_SPAN_M`: length +-3 cm, circ +-2.5 mm, testicles
  +-1.2 cm at the furthest vertex); 1.0 was MPFB's whole target (+16.2 cm length).

**New upfront check (06 rank 10): `rig_analysis.verify.crotch_clearance`**, run by the moves stage on every
clip of every body (report-only; `[moves] <role>.crotch` in the stage report; about 0.3-1 s a clip). It gives
`thigh_mm` (one inner thigh through the other), `crotch_mm` (the trunk's crotch skin through a thigh) and, with
a genital shell, `part_mm`. It shows the general collapse as numbers: study_man Crouch 17.6 / 15.8 mm, Jump
25.4 / 15.8; study_woman Crouch 4.0 / 21.9; smoke_petite Crouch 25.6 / 34.2, Jump 32.9 / 36.9; smoke_heavy
thighs 10-35 mm in every clip but Idle.

Tried and dropped: the skin's own weights on the flap (it tore into wings when the thighs spread); knees turned
out 25-35 degrees in the crouch and the jump's load and tuck (part 0 mm and thighs 0 mm, but the crotch skin
between the thighs stretched into a web - worth another look for every body, since it clears the general
crouch collapse too).

**Left:**
- **A heavy body fails the gate.** smoke_heavy (BMI 38) with genitals: part_mm Idle 13, Walk 29, Run 34,
  Crouch 33, Jump 33, turns 25 - its thighs meet and the part is engulfed; no corrective can make room.
  Hal wears trousers, so it is hidden there. The check says so at build time; a heavy nude figure needs the
  crotch collapse fixed first (a runtime collider, or thighs that yield).
- The run's mid-stance still puts a thigh 12 mm into the scrotum's side on the study man (under the limit).
- The shell's skin is blotchier than the body round it in Godot (MPFB's helper UV island in the baked maps).
- Small notches at the shaft root where the seam meets it, visible at 0.45 m in a lit close-up.

### Step 4 - flesh correctness (06 rank 9)

The shipped specs carry workarounds that should not be needed: the man's `limit_share = { belly = 0.4 }`
and the woman's `may_miss = ["belly"]`. Give belly a registry `limit_share`; fix `peak_m` reading
0.168 m on an athletic belly; stop the breast zone claiming the belly; make `verify_flesh.within_body`
able to fail (today a 17 cm belly swing passes). Done when both figures build with neither line and pass
the jump course.

### Step 5 - motion

- **06 rank 5 - rig-anything never sets `U.running`,** so every Run is judged as a walk and the run-only
  arm checks never run. Set it where `Upper` is built (`locomotion.py` ~803, `actions.py` ~654). This
  also unblocks the crowd rebuild (below).
- **06 rank 15 - MovesController plays TurnL/TurnR** and applies the manifest's turns; the demo carries
  a port of this.
- Small gaps remain between the fingertips (the middle and end finger bones keep MPFB's rest fan).
- Run the motion critic (`animate-anything/references/motion-critic-checklist.md`) on every clip of both
  figures after each change, as an independent subagent.

### How to judge "realistic"

Last round's final critic was not independent: that agent had no Agent tool and answered its own
checklist. This round:
- Run every look and motion critic as its own subagent, questions written before any image is opened,
  and record in the result which critics were independent.
- Judge from Godot renders at stated distances (1 m and full body), in clear_midday and overcast, not
  from Blender alone: lookdev materials differ between the two.
- For each step, write the critic's questions into the step's done-when before starting it.
- Pick done-when and look questions from the shipped banks, by id: lookdev
  `references/critic-look.md` (LOOK-*), animate-anything `references/critic-motion.md` (MOT-*), wardrobe
  `references/critic-fit.md` (FIT-*), follow-through `references/critic-flesh.md` (FLESH-*), humanform
  `references/critic-body.md` (BODY-*). Each question names the tile, view or verifier that answers it; a
  question the banks lack is added to the bank in the same round.

---

## Running the next session

**Use the `plugin-round` workflow** (`.claude/workflows/plugin-round.js`; run from this repo by name, or from
another by `scriptPath`). Give it the step and its branches as args:

```
{ "step": "Step 1 - hair",
  "branches": [ { "key": "...", "title": "...", "task": "...", "done": "1. ...?\n2. ...?", "after": "<key, optional>" } ],
  "ship": { "rebuild": ["study_man", "study_woman"], "belle": false },
  "look": "1. ...?\n2. ...?",
  "benchmark": <the contents of .claude/workflows/benchmark-briefs.json> }
```

The Workflow tool only runs a script it can read from the session's working directory or one it returned
itself, so from another project copy `plugin-round.js` into the session scratchpad and pass that path.

From the Step 1 round (8 branches; first attempt 45 agents with 1 branch built, second attempt 29 agents,
3 h 24 min, 4.4 M subagent tokens, every branch merged, 5 of 7 on the first critic pass):

- **A chat message sent while a round runs reaches its agents.** In the first Step 1 attempt a question about
  previews was relayed to every agent as the user's request, and 6 of 7 builders declined to build; their
  critics and fixers repeated it for two more rounds. The script now states the round's task as the user's
  request and names the last chat message as answered, and a builder with no commits ends its branch at once.
  Keep questions to the orchestrator separate from a running round's task.
- **The permission classifier refuses some ship-step actions:** `regress --godot` on the real game project
  and a Monitor tail of the regress log. The ship step ran regress on a full scratch copy of the game with the
  rebuilt assets instead, which is what the round's rules ask anyway.

It builds each branch in its own worktrees, has an independent critic answer the branch's `done` questions,
fixes at most twice, merges one branch at a time, then installs, rebuilds the real figures, runs the round's
one full regress and has an independent look critic judge them in Godot. What it encodes, from the Step 0
round (4 branches, 14 agents, 3 h 14 min, 2.4 M subagent tokens):

- **One full regress per round, not three per branch.** In Step 0 the builder, the critic and the merge step
  each ran a full `--twice`: a critic spent 23 of its 27 min on one. Now builders and merges run `--quick`
  (about 3.5 min), critics read the builder's regress log and run only the targeted checks and controls, and
  the ship step runs the one `--twice --jobs 4 --godot` (about 14 min).
- **Branches of about 30 min.** cp-resume-hashes (two ranks plus game changes) took 65 min against 25 for the
  others and set the critical path. Split large items; a branch that is "two things" is two branches.
- **Agree the seam, don't queue on the merge.** cp-close-look-set waited about 110 min for cp-resume-hashes to
  merge because both touched `stages.py`/`quality.py`. Write the shared interface (here, the review stage's
  quality keys) into both tasks and build in parallel; `after` is the fallback.
- **The merge gate is pass AND mergeable.** Step 0's gate was "pass or mergeable", so a branch the critic
  held (Belle's dressed flesh edit refused) went to the merge step, which fixed it itself - correctly, but
  unreviewed. Now a merge step that changes code stops, a second critic reviews the fix, then it merges.
- **Effort by kind:** builders, fixers and critics high; merge and ship medium.
- **Merge one branch at a time, as each finishes.** No wave waits for its slowest member. After each
  merge, branches still in flight merge `main` in before their review starts.
- **Regress was the critical path** before `--quick` (11-23 min per merge, about 7 hours in the round before
  Step 0 against about 25 min of character building).
- **A feature is done only when a real spec uses it through the pipeline and it is looked at in Godot.**
  Last round, fixtures passed while Belle's top, the man's belly, the crowd's runs and the ponytail's
  frame rate all failed on real characters.
- **Every check ships a control that must fail, and a check that can clamp its own measurement reports
  the free value.** Nine checks passed what the eye rejected last round (listed in 06 section 6).
- **Keep the lab notebook.** Each agent appends to its own notebook as it goes: failures with exact
  errors, attempts, time cost, dead ends, and what worked first time. They feed the next lessons file.
- **Give each agent a time budget and a three-attempt rule:** after three real attempts, keep what works
  (off by default if it is not good enough), record the rest as open, and return.
- **Shell rules for every agent:** regress runs longer than 10 minutes, so start it in the background and
  wait with Monitor; write any Python longer than a line to a file; never `git stash` in a repo with
  parallel worktrees (the stash is shared); pass `cygpath -m` paths to Godot and Blender.
- **Resuming an edited workflow re-runs everything after the first changed call.** To drop a stream
  mid-run, start a fresh workflow for what remains instead.

---

## Other open work (not realism)

- **The rest of 06's ranked list:** stage numbers never lost (4), stored body
  fits (6), a draft setting for moves (7), verifiers that exit non-zero (11).
- **The crowd rebuild** waits on the `U.running` fix (step 5). A spec workaround for 7 Run clips exists as
  a patch but was not applied and should not be.
- **Skirts (05 · 5.4), open items:** a run's raised thigh through the front panel, a stiff deep crouch, and
  no check that counts the first. Step 3's hip fix is the likely cure.
- **Loose ends from rounds one and two:** HISTORY.md items 7 (triage `grungist-creek/docs/plugin-improvements.md`)
  and 8 (a list of small defects each branch left behind).

---

## Things that cost time to learn

Most of this is now in `CLAUDE.md`. The rest:

- **Building the project's characters without touching its assets.** From the plugins checkout you want to
  test: `python tools/scratch_project.py <scratch dir> [--who study_man,study_woman,belle]`. It copies the specs,
  build scripts, addons (the checkout's), the chosen characters' blends and exports and the humanform library,
  writes `env.sh`/`env.ps1`, runs `--headless --import` (fails on an ERROR line) and prints the build command:
  `bash <dir>/build.sh study_man` (about 50 s from a stale blend, 0.3 s when nothing changed). Specs' `[export]
  blend` are relative (character-pipeline 0.11.0): under `BLEND_DIR`, else the project; a build refuses to save
  outside both unless `save_outside=1`. Do not run it with a scratch `env.sh` still sourced (its `BLEND_DIR`
  wins). `who=tomas` still needs his source blend opened.
- **Comparing a rebuild with committed assets.** Compare manifests with `regress.compare` at the harness
  tolerance, and glbs by their glTF JSON chunk with `extras` set aside.
- **Verifying in Godot** (`GODOT` = the `_console` build, path in grungist-creek's CLAUDE.md):

  ```
  "$GODOT" --headless --import --path .
  "$GODOT" --headless --path . figure_study.tscn -- --selftest
  "$GODOT" --headless --path . belle_demo.tscn -- --selftest
  "$GODOT" --headless --path . people_demo.tscn -- --selftest
  "$GODOT" --headless --path . motion_demo.tscn -- --selftest
  ```

  `motion_demo` is the motion round's instrument as well as its demo: four different bodies side by
  side, each on its own gait, reporting pelvis-thorax and thorax-head relative phase, shoulder dip and
  its half-cycle separation, and spine twist, bend and flex - all measured live off the playing
  skeleton, never off the manifest. 55 checks. Its numbers agree with the bake-time instrument to a
  few degrees, which is the point of having two.

  Pass full clip names to `verify_wardrobe` (`Belle_Walk`, not `Walk`) and check `samples` > 0 in every result.
- **Finding a nondeterminism:** compare the written files; checksum each stage's output in two builds and find
  the first that disagrees; hash that stage's inputs, structure (face order) as well as positions; reproduce
  it minimally in three processes. 5.7 ended in Blender itself: `create_uvsphere` shuffles faces per process.
- **Merges:** the real conflicts are the lists every branch appends to (`MODULES` in the plugins'
  `__init__.py`, lookdev's imports, SKILL.md tables, design-doc sections). They resolve as unions.
  Re-record goldens once after the last merge in a batch, not per branch.

## Loose ends outside the code

- `C:/Users/pauli/Code/Blender/belle_demo_before_rebuild.blend` (100 MB) is still there.
- The real blends in `C:/Users/pauli/Code/Blender/` are current; the figure study's are
  `figure_study_man.blend` and `figure_study_woman.blend`, and they now carry character-pipeline's stage
  records, so a rebuild resumes from them. The ship step backed up the pre-rebuild copies (and
  `belle_realistic.blend`) to `%TEMP%/rw/ship/backup/`, a scratch folder: do not count on it.
- `grungist-creek/tomas_demo.tscn` is gone (nothing referred to it; its stale editor-state files were
  removed), and `--import` is clean.
- This repo is public, and `plugins/humanform/data/` (ANSUR II public CSVs and the seed contact sheets) is
  published with it, a deliberate choice recorded here in case it is revisited.
