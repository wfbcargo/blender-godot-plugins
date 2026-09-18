# gap-brows-lashes-hairline-fix notebook

Fix round on branch fig-brows-lashes-hairline (worktree .worktrees/fig-brows-lashes-hairline). Scratch wf3/gap-brows-lashes-hairline-fix.
Blocking: 1 stray lash strand + eyeliner ring, 2 grey sliver past brow tail in Godot, 3 woman's brows near-black, 4 ink-like brows, 5 missing evidence.

## 01:40-01:48 stage=setup + baseline rebuild - kind=win / friction
- Copied the previous round's scratch build (run.sh, specs, hflib, godot project, lit.py) and sed-repointed paths: 1 attempt, 2 min. Both figures rebuilt on the branch head: rc=0, 19 s / 21 s (parallel).
- friction: lit.py's "face" target H*0.935 on a posed Idle frame lands on the nose for a tight 0.3 m eye shot; I target the lash bbox height (z 1.677) instead. Should change: a lit close-up helper in humanform views that aims at landmarks (eye centres) rather than height fractions.

## 01:48 stage=diagnose issue 1 (stray lash strand) - kind=win
- Probe (probe/lash.py): lash cards symmetric L/R to 0.1 mm, max vertex 19.3 mm from each eye centre on both sides, longest edge 5.3 mm - no stray vertex/face. Eye close-up (look/base/StudyMan_eyes.png): the "strand" is the lash cards' SHADOW from the key light (upper left), a soft dark wedge down-right onto the cheek, only on the side away from the light. Cause: the cards are opaque blocks (texture opaque middle) and their materials cast opaque shadows (use_transparent_shadow off).
- Eyeliner ring: same cause - lookdev's hair texture has an opaque middle band (root_zone[1]..tip_zone[0]); lash and brow strands at 60-90 per 4 cm tile with half-width 0.45-0.75 pitch cover the whole card. Brows: same, "ink". Woman's brows: colour*0.6 then gap_mult 0.35 and root_mult 0.8 -> sRGB 0.18,0.11,0.05 * ~0.6 = near black.
## 01:50-02:02 stage=fix issues 1,3,4 (card texture, card UVs, shadows, colour) - kind=win (3 iterations)
- humanform brows.py: brows and lashes no longer use lookdev's tiled strand texture pixels; `card_texture` overwrites the lookdev material's images (1024x256) with separate antialiased tapering hairs (brows 850 hairs, 1.9-2.8 px root -> 0.5-0.9 px tip, density profile feathered at the head and thinning into the tail; lashes 170 upper / 45 lower, clumped, sweeping outward at the outer corner). UVs: U once along each brow (0 head..1 tail, stored lean kept) and along each lid card from its outer corner (upper 0.02-0.48, lower 0.52-0.98 of the texture); lid found per connected card piece by root height. Materials use_transparent_shadow=True (the shadow wedge on the cheek was the whole card's opaque shadow). BROW_DARKEN 0.6 -> 0.8, LASH_DARKEN 0.35 -> 0.4.
- Iter 1 (17-19 s rebuild + 5 s renders): hairs read as hair, woman's brows brown; lashes a barcode of thick straight bars. Iter 2: thinner (1.6-2.3 px), 170 lashes, clumps -> fringe. Iter 3: brows denser (700 -> 850). Evidence look/r3/*_eyes.png, *_face_front.png: no shadow streak, no eyeliner ring.
- Should change: lookdev hair.strand_texture has no "no opaque middle / hair-width strands" mode; a fine-card mode there (or a card texture helper) would let other card parts reuse this.
## 02:02-02:08 stage=Godot scratch + glb + humancheck (issues 2, 5) - kind=win
- glb (glb_check.txt): _brows / _lashes alphaMode MASK (cutoff default 0.5), base colour + normal texture, extras.lookdev {preset hair, godot {transparency 2, rim/backlight/anisotropy false}}; lashes doubleSided; brows 180 tris/128 verts, lashes 368 tris/250 verts, JOINTS_0/WEIGHTS_0 present.
- Godot scratch (godot/, lookdev addon re-copied from the worktree): --import 4 s, windowed shot 3 s. LookdevMaterials.apply: brows/lashes transparency=2 scissor 0.5 albedo_tex rim=false backlight=false; no black cards; no grey sliver past the brow tail (shots2/*_face.png, *_eyes34.png). Issue 2 cause: hair preset's rim+backlight+anisotropy lighting the whole tail at grazing angle -> CARD_GODOT override. 1 attempt.
- humancheck both: 0 fail, 2 warn (pieces/open edges from the cards, same as before), 16 s parallel. hc/woman/hair.png: brows brown, lashes, ear clean.
- Fixture hair_presets --only --twice --update: 15 s x2. Golden moves reviewed: brow/lash texture hashes (new card texture), brow colour 0.21->0.28 (BROW_DARKEN 0.6->0.8), lash colour (0.35->0.4), new keys godot_sheen (hair body_hair true, brows/lashes false), texture coverage (brows 0.39, lashes 0.12), lid_cards upper 2/lower 2, transparent_shadow true. ear_covered_verts 0 (control 430) unchanged.
## 01:52 stage=commit 780bc30 + full regress --twice started - kind=slow (expected ~15 min)
- friction: the Bash tool's 600 s cap moved the foreground regress to the background; waited with a Monitor. Should change: CLAUDE.md regress guidance could say "run --twice with run_in_background" since it always exceeds 10 min.
- Evidence gathered in scratch evidence/ (lit Blender eyes/face/ear, Godot eyes/face/ear, humancheck hair.png, glb_check.txt, BEFORE eye shot).
## 02:05 stage=regress --twice (final, jobs 2, on 780bc30) - kind=slow / win
- 19 fixtures ok, every build twice and agreeing, "no change" against goldens, rc=0, about 13 min wall. Slowest: rabbit 161 s x2, cricket 107 s x2 (unrelated).

## 02:06 stage=wrap - open items
- Lashes are cards seen nearly edge-on from the front, so at 1 m+ they read sparse; alpha-scissor mip erosion will thin fine hairs at distance in Godot (not measured). Possible fix: alpha-to-coverage or a mip bias in lookdev_materials.gd for card materials.
- Faint soft lash shadow remains on the lit side (transparent shadows, now strand-shaped); acceptable.
- Brow shape is still one shape for every body (no brief field).
- Previous round's open items still stand: body hair default-off and not good enough, short_crop cap_min_clearance -0.18 mm, SKILL.md Belle figure stale, the character-pipeline edit needs a version bump from the merge agent.
