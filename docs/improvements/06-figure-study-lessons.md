# 06 - Lessons from the figure study round

Category: mostly **5 tooling friction** and **3 checks that disagree with the eye**, with a tail of
**6 feature gaps** (see [README.md](README.md) for the categories).

The round ran on 2026-09-17/18 from 23:09 to 03:58, about 4 h 50 min of wall clock with several agents
working in parallel. Its goal was two neutral study figures, StudyMan and StudyWoman, that "look and
move real", shipped into `grungist-creek` at final quality. Along the way it merged the older queue
(skirts-dresses, figure-prereqs, compression-on-belle), shipped Belle, probed the crowd, and ran five
feature gaps through author, review, fix and merge.

- **Shipped:**
  - `grungist-creek` `d02f953` (Belle rebuilt) and `afe71f3` (figure study: both figures, 7 clips each,
    and `figure_study.tscn`).
  - Addon syncs: `64eeb40`, `e108495`, `a8fc064`.
- **Merged into this repo's `main`** (`863ffe4` .. `9e3051c`): skirts-dresses, figure-prereqs,
  compression-on-belle, fig-flesh-reporting-and-godot-proof, fig-brows-lashes-hairline, fig-realistic-skin
  and fig-natural-locomotion.
- **Not merged:** `fig-genital-anatomy` failed its gate (item C in section 3) and is parked in its worktree.

The evidence is the 31 lab notebooks in [notebooks/figure-study/](notebooks/figure-study/). Every
number below comes from one of them. The file names follow the agents' roles: `<gap>.md` for the
author, `review-<gap>.md`, `<gap>-fix.md`, `merge-<gap>.md`, plus `prereqs`, `crowd`, `skirts-merge`,
`draft-lead`, `belle-*` and `final`.

---

## 1. The headline

**Building a character is cheap. Proving it is expensive.** A study figure builds through
character-pipeline in 22-27 s at any quality. The round built roughly 60 characters, about 25 min of
build time in total. Against that:

- **Regression runs:** about **7 hours** of wall time across agents. There were more than 20 full
  `regress.py --twice` runs at 8-27 min each, plus `--only` reruns and `--update` passes.
- **Scratch setup:** 2-6 min per agent.
- **Hand-written probes:** lit close-ups, glb decoders, hand-framing, penetration sweeps. Each took
  5-15 min per agent that needed one, and the same probe was often written three times.
- **Getting a look judgment:** a picture close enough, lit enough, and taken in Godot rather than
  Blender. This cost more than any build.

The ranked list in section 5 is therefore ordered by the agent minutes a change saves per character
built and judged, not by the build seconds it saves.

---

## 2. What worked well (keep)

- **One lab notebook per agent, with `kind=win|fail|slow|gap|friction` tags** and attempts, wall time
  and "should change" on each entry. That is why this file could be written. Keep the format.
  Estimated clock times drifted by 5-15 min in four notebooks; the rule "read `date`, don't estimate"
  should be in the brief.
- **Each agent had a worktree plus a scratch mirror of the project** (`characters/`, `build_human.py`,
  `save_guard.py`, a `HUMANFORM_LIBRARY` copy). No agent touched the real `grungist-creek` assets or
  `belle_realistic.blend` except the two ship agents, who backed up first.
- **Iterating on a saved blend instead of rebuilding** was the biggest speed-up in the round. Each
  probe opens the saved `.blend` and runs one stage's function:

  | Agent | What it iterated | Time per try | A full pipeline build instead |
  |---|---|---|---|
  | belle-top | dress plus 3 renders | 11-15 s | 45 s |
  | belle-top-fix | dress plus 9 tight renders | 8-10 s | 45 s |
  | locomotion | one role's `move_set` | 6 s | 25-44 s |
  | locomotion-fix | hands: Idle, Walk and 4 close-ups | 7-11 s | 25-44 s |

  Two probes in parallel meant belle-top got through 4 approaches in 20 min. character-pipeline's
  SKILL.md should say "build `to=<stage before>` once, then probe the saved blend" as *the* way to tune
  a preset.
- **The author, review, fix and merge loop, with an independent rebuild in the review.** Reviews rebuilt
  from the specs in their own scratch and reproduced the author's numbers exactly:
  - wardrobe 0.044 mm, to three decimals;
  - skin textures, byte for byte by md5;
  - the natural-locomotion manifests, to within 1e-4.

  Seeded determinism made "did the author's claim hold?" a diff, not an argument.
- **The reviews caught real defects the authors missed:**
  - the white body on an unbaked export (realistic skin);
  - gait styles flattened by the vault (natural locomotion);
  - the shelf under the bust still there at a tight camera (compression);
  - a scrotum pinched to half its width, and a whole-body normal bake falling back to rays (genitals);
  - a vacuous `within_body` check (flesh).
- **Golden diffs caught regressions the author's own character could not show:**
  - hair caps sampling the body's new UV layer (`hair_presets`, realistic skin);
  - a new `genital` flesh type joining every default search (11 fixtures moved);
  - the hull span making the smooth sample figure's top baggy (gap p95 13 -> 45 mm), which Belle alone
    would never have shown.
- **Features that are off by default, with a hash-neutral `false`.** Brows, lashes, body hair,
  `[muscle]`, genitals and skin regions all arrived without moving an existing character's stage hash.
  Merges then showed "no change" on every other golden, which is the proof that a feature is opt-in.
- **Controls that must fail:** `cut=0.04`, the skirts' `rigid=spine` and `colliders=false`, and
  flesh's 2 x peak_m. They keep a verifier honest. Each merge's regress showed them failing for the
  right reason.
- **The merge gate held.** `fig-genital-anatomy` was refused because a code-review blocker (thighs
  through the genitals) was not fixed, even though the author had worked through 8 attempts. Parking
  it, with the branch and worktree left in place, was the right call.
- **Checking the merged tree before merging.** Reviewers ran `git merge-tree --write-tree`, took a
  `git archive` of the result and ran the overlapping fixtures on it. That caught the golden
  interactions early: `pipeline_woman`'s fields list, and flesh against locomotion.
- **Editing version stamps in place instead of `--update`** (skirts-merge). It saved one 17-min run
  and kept temp paths out of the goldens.
- **The final build worked first time.** Both figures built at `quality=final` with rc 0, every clip
  passing, nothing forced and 0 humancheck failures. Every feature merged that night composed without
  a fix.

---

## 3. Failures and difficult processes

Attempts and minutes are from the notebooks. "Rebuild" means a character-pipeline build of 20-45 s.

### A. Compression top on Belle (wardrobe) - about 160 min over 4 agents, merged

| Step | Attempts | Time | What happened |
|---|---|---|---|
| Diagnose the shelf | 1 | 5 min | Cloth tucked into the inframammary fold. Cover's three tests all reject fold skin whose normal points down and back. |
| Bridge, round, smooth lift, cover `enclosed` | 4 | 20 min | Two dead ends. Found that `lift_over`'s per-corner 2 cm cones are what *fold* the cloth into the pointed shelf. |
| settle 0.1, cover `crease`, smooth lift 12 cm | 3 | 20 min | Numbers pass: 0.044 mm, Godot 21/21. |
| **Review at a 0.42 m camera** | 1 | 22 min | **The shelf is unchanged against main.** Only the wedge went. The author's render camera (0.8 m, and 2.9 m in the outfit renders) was too far to see it. fit.py was also committed CRLF with `\r\r\n` lines, so git classed it as not text. |
| Hull span, rolling ball, masked hull | 6 | 40 min | The full hull made the sample figure baggy (caught by the golden). The rolling ball ran away. The masked hull was kept. |
| Merge | 1 | 25 min | Conflicts in `cover.compute`'s signature and `garments.json`'s one-line `about`. 18 min of regress. |

The lesson is that a verifier's pass plus a far camera equalled "done" twice. The fix came only when
someone looked from 0.42 m.

### B. Realistic skin (humanform, lookdev) - about 175 min over 4 agents, merged

| Problem | Attempts | Cost | Root cause |
|---|---|---|---|
| Albedo came out orange | 1 | 3 min | Byte sRGB `Image.pixels` are already encoded; the tone correction encoded them again. |
| hair_presets UV turn moved | 1 | 6 min | Hair parts inherited the body's new `hf_detail` UV layer as the active one. |
| Muscle normal bake skipped | 2 | ~5 min | "Normal input is already linked" once the skin carried its own normal. |
| **An unbaked export is white** (review blocker) | 2 | 3 min fix | A procedural Base Color gives no `baseColorFactor`. Blender 5.2 exports colour attributes even when no material reads them. |
| Albedo pure black, yet `tone_ok True` | 1 | 2 min | `np.asarray(IDProperty)` is a view; rebuilding the material freed it. |
| Palms glow orange under clear_midday | 1 | 2 min | Transmittance depth of 8 cm on a 2-3 cm hand. Overcast hid it. |
| Framing the hands for a shot | 2 dead ends x 3 agents | ~15 min total | Nobody knows where a posed hand is in Godot. Coordinates taken from Blender at rest, and then from its pose, both missed. |
| The glb tone probe | written 3 times | ~10 min total | No shipped tool decodes a glb's albedo over its UV coverage. |
| Long regress runs | 27 + 17 + 11 min | ~55 min | Including an `--update` that churned 8 goldens with noise. |

### C. Genitals (humanform, follow-through) - about 155 min over 4 agents, **not merged**

- **Fuse:** 4 attempts, 8 min. `bmesh.ops.bridge_loops` cannot handle unequal loops, and the MPFB mesh
  carries 70 shape-key layers. The fix was to move the fuse after `bake_for_game` and add an
  angle-ordered zipper.
- **Thigh intersection:** 13 attempts, about 40 min of 26-50 s rebuilds, **unresolved**.
  - Contact weights spiked in a crouch.
  - A bake-time sweep pinched the scrotum to 2.4 cm.
  - Per-frame corrective bones helped the scrotum (Walk 25 -> 7 mm) but not the shaft (Crouch 27 mm,
    Jump 30 mm).
  - A slice render showed the actual cause: rig-anything's linear blend skinning collapses the crotch,
    and the two inner thighs **cross each other** in Walk and Run. There is no free space to push into.
- **Adding a type broke eleven fixtures:** 11 goldens moved, because a new flesh type joins every
  default search. Fixed with `opt_in`, and a crotch-width guard that applies only to bodies carrying
  the shell. Cost: a 6-min rerun plus the diagnosis.
- **No check could see the defect.** `verify_flesh.within_body` compares the jiggle offset with peak_m
  only. The fixture records the clearance but gates only on "better than before". The reviewer and the
  author each wrote their own penetration sweep (`pen.py`, `inspect.py`).
- **Stashing in a shared repo:** one agent ran `git stash` in a repo with parallel worktrees. The stash
  is shared across them, so it was dropped at once. Don't stash there.

### D. Natural locomotion (rig-anything) - about 110 min over 4 agents, merged

- **Diagnosis:** first try, about 10 min. A fixed 32-frame walk plays at 0.71 of natural speed, and a
  single hip drop per cycle gives 31.7 deg knees at mid-stance.
- **Review blocker:** the vault set `bounce = 0`, so every style's knee converged on 11.5 deg and
  `bounce_scale` did nothing. Grungist-creek's elderly, child and heavy characters would have lost
  their gait without anyone noticing. Fixed with `vault` as a style key.
- **Thumb C-grip and clawed fingers:** 2 attempts at 7-11 s each on the saved blend.
- **A scratch leak** cost one build and a lost blend: a copied spec's absolute `[export] blend`
  saved over the previous agent's scratch.
- **Lost output:** `| tail -60` threw away the fixture list, costing a 3.6-min rerun. One
  `--update` run took 27 min, including a one-off 910 s `pipeline_muscle` that was never explained.

### E. Flesh reporting (follow-through, character-pipeline) - about 115 min over 3 agents, merged

- **The woman's belly vanished silently.** The cause is that her breast regions grow 0.1 of the
  zone height into the belly zone and claim 190 of its 298 vertices. It is now reported, and her spec
  needs `may_miss`.
- **The man's belly failed `within_body` on the jump.** It has no registry `limit_share`, so it gets
  the default 1.2 x peak_m. It needed a spec line and one extra build.
- **Review:** `within_body` cannot fail while the limit is at or below peak_m, because the offset is
  clamped. On the jump, the free peak is 0.41 m against a 0.095 m stand-out.
- **Final ship:** the man's belly peak_m is 0.168 m on an athletic body. It swung 12-17 cm in Godot,
  which is plainly visible, and still passed every check. The shipped spec narrows it with
  `limit_share` 0.4. The root cause is open.

### F. Brows, lashes, hairline (humanform) - about 100 min over 4 agents, merged

- **Ear selection:** 4 attempts, 6 min. Two of them were judged on renders where the joined hair cap
  hid the ear, which was the bug being fixed. A probe that colours body vertices must delete the hair
  faces first.
- **Invisible brows:** a UV bug, fixed in 2 min. It came from reading `BMVert.index` before
  `index_update()`.
- **The "stray lash strand" was the opaque card's shadow.** The "eyeliner ring" was lookdev's opaque
  texture middle. Fixed in 3 iterations with a humanform card texture.
- **Lookdev hair preset on fine cards:** in Godot, `transparency 4` gave a grey haze and a sheen on
  the brow tail.

### G. Smaller items that cost the most repeated minutes

- **Absolute `[export] blend` in specs:** every agent sed'd it, about 2 min each. One agent overwrote
  another's blend.
- **Windows MAX_PATH:** `regress --keep` under the session scratch path pushes review PNGs past 260
  characters. Blender reports "Render error (No error)". It happened in 3 separate agents, about 3 min
  each.
- **Bash's 600 s cap:** a foreground wait on a 10-27 min regress run hit it in at least 7 agents.
  Everyone rediscovered Monitor or a background run.
- **`regress --update` churn:** every re-record rewrote temp paths, seconds and `size_bytes`, which had
  to be put back by hand. This happened 6 times, at 3-5 min each.
- **Version bumps:** hand-edited in two files plus a "Since" sentence inside a 3-4 kB one-line
  description. One merge missed the `marketplace.json` version.
- **Addon sync:** `diff -rq` flags every CRLF file and every `.uid`. Every merge needed
  `--strip-trailing-cr -x '*.uid'` worked out again.
- **Python in bash heredocs:** failed in 3 agents on nested quotes or backslashes. Write a script file
  instead.
- **No independent critic in 3 agents** (the natural-locomotion author and fixer, and the final ship).
  None had an Agent tool, so the author answered the motion and look checklists themselves.
- **rig-anything `U.running` is never set** (crowd). Every Run is judged as a walk, so 7 of the 16
  crowd Runs fail `arm_swing`, and the run-only checks never run. It is still unset on `main` 0.24.0.
  A spec patch works around it (`scratchpad/wf3/crowd/crowd_specs.patch`, not applied).
- **`verify_strands` cross-rate spread** was 1.26 against a limit of 1.25 on StudyWoman's ponytail,
  first seen at ship. It is a real frame-rate dependence in `strand_modifier.gd`, probably exposed by
  the natural-speed run. Open.

---

## 4. Timing

### Per stage, draft against final (s, from `final.md`)

The draft column is `draft-lead.md`'s build on main as of `b496738`, before the realistic skin.

| Stage | Man draft | Man final | Woman draft | Woman final | Share of a final build |
|---|---|---|---|---|---|
| body (fit or reuse) | 6.3 | 4.9 | 3.0 | 3.6 | 15-20 % |
| muscle | 2.4 | 0.6 | 0.8 | 0.5 | 2 % |
| bake (skin bake since 0.10.0) | 0.2 | 1.9 | 0.2 | 1.9 | 8 % |
| hair | 0.5 | 0.6 | 0.6 | 0.7 | 3 % |
| flesh | 1.1 | 0.6 | 1.2 | 0.7 | 3 % |
| **moves** (7 roles) | 7.4 | **7.0** | 8.6 | **7.2** | **29-30 %** |
| strand | - | - | 0.2 | 0.1 | - |
| **export** | 3.8 | **3.6** | 5.0 | **3.8** | 15-16 % |
| **review** | 1.8 | **4.4** | 2.3 | **4.8** | 18-20 % |
| **total** | 24.4 | 24.1 | 22.1 | 23.8 | wall 25-27 s |

Draft is not a speed knob for these figures, because final costs no more. Only bake (+1.7 s) and review
(+2.6 s) grow with quality, and moves plus export are 45 % of either. Other measured body times:

- Dante's fresh fit: 10.8-13.9 s, against 4.7 s with draft fit settings.
- A crowd person's pre-moves stages: 0.8-18.5 s.
- Library reuse: under 1 s. The pipeline never stores fits (`store=False`), so reuse happens only for
  bodies that were already in the library.

### Around the build

| Activity | Time | Notes |
|---|---|---|
| `regress.py --twice --jobs 2`, full | 8.5-27 min (median about 15) | rabbit 120-261 s and cricket 92-207 s per build make up about 60 % of the critical path. |
| `regress.py --twice --jobs 4 --godot`, full | 11-18 min | One or two per merge, 7 merges. |
| `--twice --update` passes | 3-27 min | Each followed by restoring the noise by hand. |
| Godot scratch import | 2-7 s | |
| One Godot verifier | 1-15 s | 21 `verify_wardrobe` runs take 73-117 s at `-P 4`. |
| Godot screenshots | 3-8 s per shot | 10 shots at 1600x900 took 58 s. |
| humancheck | 7-12 s per body | |
| Lit EEVEE close-ups | 5-10 s per batch | |
| Scratch setup | 1-6 min per agent | |

### The slowest stages, and what would halve each

| Stage or activity | Now | What would halve it |
|---|---|---|
| Full regress per merge | 11-18 min at `--jobs 4` | Start the longest fixtures first; with rabbit and cricket starting last they bound the wall time. Add a `--quick` that picks fixtures by the plugins they stamp against the plugins that changed: a wardrobe-only merge skips rabbit and cricket, which merge-belle-top estimated at about 8 min. |
| `--update` re-records | 3-27 min plus 3-5 min of hand repair | Don't rewrite a golden whose only differences are ones the comparison ignores. Add `--restamp` for version headers. Merges then need no second full run. |
| moves | 7-9 s, 30 % | A `frame_scale` or `quality` argument in rig-anything `move_set` that halves frames and fps together, per role (draft only). Also cache clips by body and rig hash across a `[flesh]` or `[hair]` restart, since moves re-run after every flesh edit. |
| export | 3.6-5 s, 15 % | Export re-plays every clip that the moves stage already checked. Skip the re-check when the clip's action hash is unchanged since moves recorded it. |
| review | 4.4-4.8 s final, 18 % | Render only the clips and views whose hash changed. At draft, one view. A close-up set (item 1 below) would add time here but remove 5-10 min of hand-made renders. |
| body (fresh fit) | 11-14 s | Store final fits in the library, so the second build of a spec in any session reuses the body in under 1 s. |
| A `[flesh]`-only spec edit | 25 s (a full build) | The thin callers (`build_human.py`, `build_belle.py`, `run.sh`) should open the saved blend, so the rebuild starts at flesh: about 12 s. |
| A garment preset edit | 45 s with `force=1` | Include the preset's contents and wardrobe's version in the garments stage hash. `from=garments` then takes about 22 s with no force. |

---

## 5. Plugin improvements, ranked by time saved per character build

"Saved" counts the agent minutes spent building **and judging** one character, as measured in this
round. Each item names its plugin and file and says when it is done.

| # | Improvement | Plugin / file | Saves per character | Done when |
|---|---|---|---|---|
| 1 | **Close-up look set in the review stage:** lit EEVEE face, eyes, hands (palm and back), crotch, feet and bust at about 0.4-1 m. Cameras aimed from **bone positions of the posed frame**, not height fractions. Tiles labelled. | character-pipeline `stages.run_review`, rig-anything `review.sheet`, humanform `views` | 5-15 min. At least six agents wrote their own `lit.py` / `close.py` / `render.py`; hand framing failed in 3 agents; far cameras hid the bust shelf twice. | A build writes `review/<id>/close/*.png` from which the look checklist can be answered with no script; a 0.42 m under-bust view exists for any spec with a top. |
| 2 | **Specs safe to copy:** `[export] blend` relative to `BLEND_DIR`/`PROJECT`, and the runner refuses to save outside them unless told to. | character-pipeline `spec.py`, `runner.py` | 2-3 min per scratch copy, and no overwritten blends (1 incident). | A spec copied to a new `PROJECT` builds and saves only under it, with no sed. |
| 3 | **Resume and cache that match what changed:** thin callers open the saved blend; the garments hash covers preset contents and the wardrobe version; the hair hash covers a hair-geometry version (the ear cut left Belle's old cap "unchanged"). | `grungist-creek` `build_human.py` / `build_belle.py`, character-pipeline `run.sh` template and `stages.py` hashes | 13-25 s per iteration, plus no stale results that need a `force=1` hunt (about 10 min in belle-top). | A `[flesh]` edit reruns flesh..review only; a `garments.json` edit reruns garments without force; a hair-code change reruns hair on old blends. |
| 4 | **Stage numbers never lost:** `run_moves` attaches the per-clip report (`arm_pose`, carry) to its exception; the garments report keeps detail, lift, `folded_faces` and `sharp_edges`; each stage's report goes into the manifest `build` block without `runner._small`'s 4000-character cut. | character-pipeline `stages.py`, `runner.py` | 3-5 min per failing character. The crowd, belle review and brows review each rewrote a probe to recover numbers the build had printed and dropped. | A failing build's log alone gives the numbers; `ear_covered_verts`, garment detail and flesh `missed` reasons are readable from the manifest. |
| 5 | **Fix rig-anything's run exemption:** set `U.running = duty < 0.5` where `Upper` is built (`locomotion.py` ~803, `actions.py` ~654); print `arm_swing` to one decimal. | rig-anything `locomotion.py`, `actions.py`, `verify.py` | Every Run in the crowd: 7 spec patches and about 30 min of probing. | The 16 crowd people build to moves with no `[moves.per_gait.Run]` patch; a child-run fixture (Froude 2.2, arms in front) passes; `RUN_HAND_RISE` and `RUN_ELBOW_OPEN` are applied. |
| 6 | **Store final body fits in the library** and check the fresh fit's stature. A fresh fit missed the brief by 2.5 cm where the warm path hit it. | humanform `pipeline.make`/humanlib, character-pipeline `stages.run_body` | 4-13 s per build, and a stature surprise. | A second build of a new spec in a fresh session reports body reuse in under 1 s; a fresh fit lands within 5 mm of the brief. |
| 7 | **Draft moves:** `move_set(frame_scale=0.5)`, which halves frames and fps together per role. The pipeline passes it at draft. | rig-anything `actions.move_set`, `locomotion.cycle`; character-pipeline quality table | 3.5-4 s per draft build, and it gives draft a reason to exist. | Draft study_man moves ≤ 3.5 s with every clip check passing; draft total ≤ 0.6 x final. |
| 8 | **Godot-side look tools in lookdev:** `close_shot.gd` (load a glb, `LookdevMaterials.apply`, equip garments, aim at bones, write a labelled sheet); `glb_tone.py` (albedo mean over UV coverage); a runtime `lookdev_presets.gd` with `presets.json` shipped in the addon; `"needs": "interior"` on `interior_daylight`; lint and capture fail on 0 materials or an unopenable `--out`. | lookdev `godot/`, `presets.json`, `lint.gd`, `capture.gd` | 5-10 min per look pass. `hair_shot.gd`, `shot.gd`, `bones.gd`, `montage.py`, `glbtone.py` and a 40-line preset port were each written by at least one agent, and the tone probe by three. | A character is judged in Godot with one command; the demo drops its preset port; a lint on a scene with 0 materials fails. |
| 9 | **Flesh that is right without spec workarounds:** a registry `limit_share` for belly; a `peak_m` that does not read 0.168 m on an athletic belly; a breast zone that stops claiming the belly; `verify_flesh` reporting `free_peak / peak_m`, plus a neighbouring-skin clearance check so `within_body` can fail. | follow-through `builtin.json`, `flesh.py` (`_grown_zone`, peak), `verify_flesh.gd` | One rebuild and one Godot pass per affected character (25-34 s plus 5-10 min), plus a visible 17 cm belly swing that no check caught. | study_man and study_woman build with no `limit_share` or `may_miss` lines and pass the jump course; a planted 17 cm swing fails a check. |
| 10 | **humancheck that knows cards and poses:** exclude `humanform_hair` card parts from pieces and open edges; add a posed limb-clearance check (shell against thigh, thigh against thigh). | humanform `measure.py`, `humancheck` | 2 spurious warnings on every browed body, and about 10 min of ad hoc `pen.py`/`inspect.py` per anatomy review. | Browed bodies report the draft's 8 pieces and 120 open edges; the crotch collapse shows up as a humancheck number. |
| 11 | **Verifiers exit non-zero on failure** and accept role names: `verify_wardrobe.gd` should `quit(1)` on `passed=false`, take `clip=Walk` for `<Name>_Walk`, and guard every early `quit(2)` with a `refused` flag. | wardrobe `verify_wardrobe.gd`, follow-through `verify_*.gd` | 1-2 min per shell loop, and makes batch runs honest. | `xargs` loops over verifiers need no JSON parsing to count failures. |
| 12 | **The final bake at final size:** pass `[build] quality` to `look.skin` (2048 px final, 1024 draft); keep skin marks after `from=bake`. | character-pipeline `stages.run_bake`, humanform `skin.py` | Correctness, not time: final ships 1024 px today. | A final manifest records 2048 px maps; a bake-only rerun keeps the region tones. |
| 13 | **Strand frame-rate independence** and a strand entry in `regress --godot`, on a natural-speed run. | follow-through `strand_modifier.gd`, `tools/regress.py` | One failed ship check per ponytail character. | The 30/60/120/240 swing spread is ≤ 1.25 on study_woman; regress runs `verify_strands` on `pipeline_ponytail`. |
| 14 | **Hair shells cast a scissor shadow,** not a dithered depth-pre-pass one (a stipple on both necks). Also a card mode in `hair.strand_texture` (no opaque middle), and alpha-to-coverage or a mip bias for cards. | lookdev `presets/materials.json`, `lookdev_materials.gd`, `hair.py` | The look of every haired character in Godot. | No stipple under the ear at clear_midday; humanform stops overwriting lookdev's texture pixels. |
| 15 | **MovesController plays TurnL/TurnR** and applies the manifest's `turns` (yaw, `end_offset`). | rig-anything `godot/addons/rig_anything/moves_controller.gd` | Every game scene that turns; the demo carries a port. | `figure_study.gd` drops its Facing hand-off. |

Also open, but not about time: the genital thigh clearance (item C); `genital_shape` 1.0 mapping onto
MPFB's extreme length (+16 cm); the man's glossy forehead and lips; the hard short_crop hairline;
sparse lashes; a brief field for brow shape.

### Repo tooling (per merge rather than per character)

Every merge in the round spent 11-23 min on regress. That makes these worth as much as the top of the
table.

1. **`tools/regress.py`:**
   - schedule the longest fixtures first;
   - print each result with `flush=True`, and end with `REGRESS DONE exit=N, K fixtures ok`;
   - `--quick` by changed plugin;
   - `--update` skips noise-only goldens, and `--restamp` refreshes version stamps;
   - warn when `--keep` plus the deepest fixture path nears 260 characters;
   - always write the full diff to a file;
   - warn when a VOLATILE key holds a dict (a whole block silently goes uncompared);
   - report per-stage times for the pipeline fixtures, so a 910 s spike explains itself;
   - refuse `--update` when HEAD is not a descendant of `main`.
2. **`tools/bump.py <plugin> <version> "<since>"`:** edits `plugin.json` and `marketplace.json`, and
   restamps the goldens.
3. **`tools/install.py --godot-project <path>`** (or `tools/sync_addons.py --check`): reuse
   `regress.addon_drift` to ignore CRLF and `.uid`, and list `addons/lookdev` when a glb carries
   lookdev extras.
4. **`.gitattributes`:** `text eol=lf` for `*.json *.md *.gd` as well as `*.py`, and a one-time
   `git add --renormalize .`.
5. **Merge-friendly lists:** `humanform/__init__.py` MODULES with one name per line; the presets'
   `about` field as an object keyed by field. Both conflicted this round.
6. **NEXT.md holds versions in one place.** Three lists went stale and had to be fixed at every merge.

---

## 6. Orchestration lessons

- **Barriers.** Branches cut from `b496738` merged into a `main` that had moved 5-17 commits.
  - Two merges hit conflicts that the author's `--twice` could not see: compression against skirts in
    `cover.py`, and locomotion against flesh in `pipeline_woman`'s fields list.
  - Keep one merge at a time. After each merge, have the parked branches merge `main` in before
    their *review* starts, not before the merge.
  - Re-record goldens once, after the last merge in a batch, not per branch.
  - The serial merge queue (7 merges, 15-28 min each, mostly regress) was the round's critical path.
    Running `--quick` per merge and one full `--twice --godot` at the end would cut it by about half.
- **Resume cache.** Stage input hashes made a rebuild after a spec edit cheap, but the cache is only as
  good as its inputs:
  - it ignored garment preset contents, which cost a hunt in belle-top;
  - it ignored the hair-geometry version, so Belle's cap was reported "unchanged" after the ear cut;
  - it did not list lookdev for the bake stage (fixed in character-pipeline 0.7.1);
  - the thin callers never opened the saved blend, so the cache was bypassed completely and every
    call rebuilt from body.

  Every stage's hash should name the code and data files it reads, and a test should flip each one.
- **Integration checks on real characters.** The fixtures passed while real characters failed:

  | What failed | Where it was found |
  |---|---|
  | Belle's heavy bust, which no fixture has | belle-top |
  | An unbaked direct export | the review's consumer path |
  | The crowd's Runs | crowd probe |
  | The man's belly | final ship |
  | The ponytail's frame-rate dependence | final ship |
  | Styled walks | review probe |

  Every gap's review built the study figures from their specs through the pipeline, and that is what
  found these. Keep "build the real spec, open it in Godot" as a required review step. Also add
  fixtures that reproduce each failure: a heavy-bust figure, a child run with arms in front, and a
  styled walk (done).
- **Verifiers that pass what the eye rejects.** This round's list:
  - `detail` 0.044 mm with the shelf still there;
  - `within_body` true with a 17 cm belly swing (clamped, so vacuous);
  - `verify_flesh` blind to a thigh inside the genitals;
  - `pipeline_genitals` gating on "clearance better" rather than an absolute limit;
  - `verify_wardrobe` blind to a thigh through a skirt panel (from the round before);
  - lint passing a scene with 0 materials;
  - `tone_ok True` on a black albedo;
  - `verify_wardrobe` exiting 0 on failure;
  - `folded_faces` raising a false alarm on correctly spanned cloth.

  The rules the round converged on:
  1. A check whose limit can clamp its own measurement must report the free value.
  2. A run that measured nothing, or compared against a value it read back from its own output, fails.
  3. Every check ships a control that must fail.
  4. A look claim needs a close lit picture at a stated distance. Render in Godot when the material is
     lookdev's.
- **Independent critics need the tool to exist.** Three agents had no Agent tool and answered their own
  critic checklists. The workflow should either give leaf agents a critic subagent or run the critic as
  a separate step in the script, and it should record which critics were independent.
- **Waiting and shells.** Tell every agent up front:
  - regress runs longer than 10 min, so start it with `run_in_background` and wait with Monitor;
  - write any Python longer than a line to a file rather than a heredoc;
  - never `git stash` in a repo with parallel worktrees;
  - pass `cygpath -m` paths to Godot and Blender, not Git Bash paths;
  - read `date` rather than estimating times in the notebook.
