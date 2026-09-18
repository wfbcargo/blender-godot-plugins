# Motion critic checklist

The motion critic is a subagent that did **not** author the clips. It judges a character's motion
from the review strips every export writes - `<glb folder>/review/<glb name>/` - and the numbers
shipped beside them in `.moves.json`, never from the builder's account of what the clip was meant
to do. It is humancheck's critic
(`humanform/references/critic-checklist.md`) pointed at motion instead of anatomy, and it exists for
the same reason: floor, slide, balance and clearance all passed on Walter's walk reaching forward
with straight elbows and on Tomas' run carrying his hand at his neck. Nothing numeric objected until
a person looked at eight frames side by side.

Vision judgements from agents agree with humans far less often than humans agree with each other
(BlenderGym: 0.66 against 0.79), so the protocol leans on written-first questions, fixed views, the
numbers already in the manifest, and a pairwise comparison with the previous version - not on an
open-ended "does this look good".

## Protocol

1. **Questions before looking.** From the brief, the clip list and `review.json`, write the yes/no
   questions - 6-10 per clip, drawn from the bank below plus whatever the brief implies ("stooped
   labourer" -> "Does the upper back curve forward in the right view?"). **Phrase every question so
   `yes` is good**, and name the strip that answers it (`Walter_Walk_right.png`, cell f13). Write
   them down before opening a single png. A question invented after seeing the picture is an
   observation, not a test, and is not allowed to count.

   Each clip's `clip_checks` failure in the manifest becomes a question of its own, and so does each
   `arm_pose` number beside it in the same `.moves.json`.
2. **Answer from the evidence.** For each question: `yes` / `no` / `unclear`, the strip and the
   cell, and one sentence saying what is visible. A number outranks an impression - if `arm_pose`
   reads `hand_rise` 0.44 and the hand looks high, say the number and say the strip disagrees. Cite
   a cell (`f13`) rather than "some frames".
3. **Classify every `no`.**
   - `gross` - the body goes through the floor, a foot slides while planted, a limb passes through
     the torso, the root drifts out of the cell. Blocks the clip.
   - `carriage` - the arms, head or spine are held wrong for the action: reaching arms, a hand above
     the chest, a head that bobs or leads, a stoop in the wrong direction.
   - `timing` - contacts, swing and weight: both feet down at once in a run, a foot landing in front
     of the knee, no flight phase, a gait that reads as the same pose eight times.
   - `outfit` - skin through cloth, cloth pinned into the body, a hem that never moves.
   - `brief` - well made, but not the motion that was asked for (age, mood, gait style).

   Name the clip and the body part (`Tomas_Run`, `arm.R`) so a fix can be aimed.
4. **Pairwise, when there is a previous sheet.** Answer each question `A` (previous), `B` (current)
   or `same`, then give one overall preference. Never score a version in absolute terms - "is B's
   arm carriage better than A's" is answerable; "is this a good run" is not.

   Read both `review.json` files first. The comparison is only tile-for-tile when
   `ortho_scale_m`, `cell_px` and the clip's `frames` list all match; the sheets also have to be the
   same views. When any of those differ, say so and compare what is described rather than pixel
   heights - a hand that sits higher in a taller cell may not have moved at all.
5. **Return JSON** (below) and nothing that reads as encouragement or as a plan.

```json
{
  "character": "Walter",
  "clips": ["Walter_Idle", "Walter_Walk"],
  "questions": [
    {"clip": "Walter_Walk", "q": "Are the hands below the chest through the whole swing?",
     "strip": "Walter_Walk_right.png f13", "answer": "no",
     "evidence": "the forward hand sits level with the sternum at f13 and f17, above the elbow",
     "severity": "carriage", "part": "arm", "compare": "B"}
  ],
  "gross_issues": ["..."],
  "preferred": "B",
  "confidence": "medium"
}
```

`preferred` is `"A"`, `"B"` or `"same"`, and `"none"` when there is no previous sheet.

## Reading a review sheet

`<clip>_<view>.png` is one strip: eight evenly spaced frames of that clip, left to right, in one
row. Views are `front`, `right` and `three_quarter` (`three_quarter_above` for a flat body). The
heading above the row gives the character, clip and view, and each cell is labelled with its frame
number - the same frames in every view, and they are in `review.json` under `frames`.

- **One scale.** Every cell is `ortho_scale_m` tall, the same for every clip of a character and, at
  the 2.1 m default, for every upright human. Two sheets at the same `ortho_scale_m` and `cell_px`
  measure the same: a hand two pixels higher really is two pixels higher.
- **The orange line is the floor**, drawn in front of the bodies so a foot that sinks below it still
  shows. Below it is the ground band; above the row is the label band. `bands_px` is
  [label, above, below].
- **`contact.png`** is every clip and view as one montage - the right place to compare clips of one
  character (does the run differ from the walk at all), not to judge a single frame.
- **`review.json`** carries, per strip: `cells_with_body` (8 unless a pose left its cell),
  `distinct_cells` (how many cells differ from every earlier one - a walk reading 3 is eight frames
  of nearly the same pose), `edge_cells` (a body touching any edge of the picture; 0 is the only
  good value) and `centred` (each pose re-centred in its cell, in which case cells cannot be
  compared for travel).

`distinct_cells` below 8 is evidence for a `timing` answer, but not proof: an idle is *supposed* to
barely move, and the export fixtures honestly read 4-5 on idles and launches.

## Question bank

### Every clip
- Is every one of the eight cells drawn with a body in it (`cells_with_body` 8)?
- Is nothing touching the picture's edge (`edge_cells` 0)?
- Is the lowest part of the body on or above the orange floor line in every cell, except where the
  clip is meant to break it (a jump's launch, a slide)?
- Does no limb pass through the torso or the other leg in the `front` and `three_quarter` strips?
- Is the head upright and facing the direction of travel, not tipped back or leading the chest?

### Walk and run (`front` for alternation and width, `right` for carriage and stride)
- Do the arms swing opposite the legs - the forward arm on the side of the *back* leg in every cell?
- Are the hands between the hip and the chest through the whole swing, never above the sternum?
- Are the elbows visibly bent, and more bent in the run than in the walk?
- Is the head level across the eight cells, rising and falling no more than the body does?
- Does each foot land under or behind the knee, not reaching out in front of it?
- In the `front` view, do the feet land within about a hip's width of the midline - no waddle, no
  crossing over?
- Does the torso stay upright, leaning forward a little in the run and not at all in the walk?
- Is there a flight phase in the run - at least one cell with neither foot on the floor - and none
  in the walk?
- Do the cells show eight different poses, not the same pose slid sideways (`distinct_cells`)?

### Idle
- Do the arms hang with gravity, hands beside or just in front of the thighs, elbows soft?
- Are the arms free of any reach - no hand carried forward of the hip line in the `right` view?
- Do both feet stay flat and still on the floor line across all eight cells?
- Is the weight over the feet - the head above the ankles in the `right` view, not behind the heels
  or out past the toes?
- Is there some motion at all - a breath, a weight shift - rather than eight identical cells?

### Posture (a brief that names one: stooped, proud, elderly, weary)
- Does the stoop or lift read in the direction the brief names, in the `right` view?
- Is it in the spine - the upper back curving, the chest dropping - rather than the whole body
  tipped from the ankles?
- Does the head still look where the body is going, the neck compensating for the spine?
- Is the posture the same in the idle and in the walk, so it reads as the character rather than as
  one clip's mistake?
- Do the arms hang from the posture rather than being dragged behind it - hands in front of the
  thighs on a stoop, not out past the knees?

### Crouch and jump
- Are the feet flat on the floor line through the crouch, heels down?
- Are the knees over the feet in the `front` view, not collapsing inward or bowing out?
- Does no part of the body cross the floor line except a jump's flight, where the whole body is
  above it?
- Does the body fold at the hips and knees together, the spine staying long, rather than the back
  rounding to reach the depth?
- In a jump: do the arms swing down and back on the launch and up on the rise, rather than staying
  where the walk left them?
- On the landing, do the knees bend to absorb it - at least one cell deeper than the standing pose?

### Outfit (a dressed sheet, garments in their own colours)
- Is every area the garment covers still covered in every cell - no skin appearing at the hem, the
  waist, the armhole or the shoulder as the body moves?
- Is there no skin poking through the cloth - a body colour showing as a patch inside the garment's
  outline?
- Does the cloth read as cloth rather than as painted skin - does its outline stand off the body
  where it should hang free?
- Does a loose hem or cuff move across the eight cells, and lag the body rather than leading it?
- Does the garment follow the body's *form* without tracing its *detail* - no navel, nipple or
  buttock crease drawn through a garment the brief calls loose?
- Does no garment pass through the body or through another garment in any cell?

### Creatures that are not bipeds
Use the "every clip" questions, then the questions in the reference for that body -
`hoppers.md` (a hop's launch, air and land), `radial-bodies.md` (a pulse's closure and symmetry),
`fins-and-swimming.md` (a tailward wave), `wings.md` (the stroke) - as the per-clip bank. The
walk/run bank's arm questions do not apply to a rig with no arms; say `unclear` rather than `no`.

## Keep or revert

**Locked numbers** are the clip's `clip_checks` in the manifest (`lowest_foot`, `loop_seam`, the
slide and balance failures) and, beside them in the same `.moves.json`, `arm_pose` per clip per arm
(`hand_rise`, `elbow_flex_deg`, `upper_arm_deg`, `arm_carry_deg`, `arm_swing_deg`). A new version
holds them if every check still passes and no `arm_pose` range has moved toward its limit.
`arm_pose` is written only for clips whose arms were authored (idles and gaits), so a crouch or a
jump has none and its arm questions are judged from the strips alone.

Both live in the shipped manifest on purpose: the previous round's build log is gone, so anything
the rule compares across versions has to be on disk. **Lock nothing else.** If a number you want to
compare is not in the two `.moves.json` files, say so and drop the question - do not reconstruct it
from the pictures. A manifest written before `arm_pose` was persisted has no such field: compare
`clip_checks` only, and record `"unclear"` for the arm questions' `compare` rather than guessing.

**Keep the new version only if the locked numbers held and the critic prefers it**, or calls it
`same` with fewer `gross` and `carriage` issues. Otherwise revert and try a different fix. A critic
that prefers B while a check that passed now fails is not a reason to keep B: fix the check first
and ask again.

**Twice is a guard.** When the critic flags the same thing on two different characters, or on the
same character across two rounds, it stops being a judgement and becomes a number: write it into
`verify` as `arm_pose` was written (04 d). The strip has to justify the threshold - measure the
flagged clips and the passing ones, and put the line between them, not at a round number.

`verify.arm_swing` came out of this loop and is what that looks like: the reach was flagged on
Walter's walk and again on his idle, `hand_rise` read it as passing, and the line - a swinging arm
comes back within 2 degrees of hanging - was set from 49 shipped clips against the flagged one. The
idle half is still a proposal, because there the two populations are 2 degrees apart.

## Known blind spots of the strips

- **A side view cannot tell the near arm from the far one.** A far arm forward reads exactly like a
  near arm forward, so arm *alternation* is a `front`-view question. There is no numeric fallback:
  `arm_pose` names each arm but reports only its range over the whole clip (`arm_carry_deg` is
  `[min, max]`), and no per-frame angles are kept anywhere, so the numbers cannot say which arm was
  forward on a given frame. Two arms swinging in *opposite* phase sweep the same range: in the
  export fixtures the left and right ranges come out identical (`mpfb_woman_curvy`, every clip) or
  within 1.1 degrees (`rigify_human`), on clips whose arms do alternate. Answer alternation from
  `front`, or answer `unclear`. Never answer it from two cells of `_right.png`.
- **Eight frames alias.** A 24-frame run sampled every 3 frames can land on the same phase of both
  legs. A clip that looks like it has no flight phase may only have been sampled past it; check
  `frames` in `review.json` against the clip's length before calling it `timing`.
- **Travel is not visible when `centred` is true.** Each pose has been re-centred in its cell, so
  root motion, drift and stride length cannot be read from cell positions.
- **The strips are workbench-lit and untextured**, so material, skin tone and shading faults are out
  of scope. Judge those from lookdev's renders.
- **One character at a time.** Two characters at the same `ortho_scale_m` can be compared, but the
  sheet does not draw them together and a difference of a few pixels across two files is not
  evidence.
