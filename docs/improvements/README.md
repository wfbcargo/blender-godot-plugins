# Character pipeline improvements

Lessons from building 16 realistic people and two versions of Belle (grungist-creek, September 2026)
with humanform, rig-anything, animate-anything, follow-through and wardrobe. Each file below is a
self-contained work item: the problem, what we saw, the design, steps, and how to know it's done.
Start a new conversation with "Read `docs/improvements/<file>` and plan it" (the repo is
`C:/Users/pauli/Code/blender-godot-plugins`).

Most of the time went not into hard problems but into rediscovering the same kinds of problem at
every step. They fall into six categories. When a new issue turns up, file it under one of these
before fixing it - the category says where the fix belongs.

| # | Category | Symptom | Where the fix belongs |
|---|---|---|---|
| 1 | **Body-source quirks** | Each plugin separately finds that an MPFB body is odd (ground root bone, Euler bones, bent forearms, straddled stance, >4 weights, flesh bones on the chin) | Once, in a shared rig profile - see [02](02-bone-roles-and-rig-profiles.md) |
| 2 | **Cross-plugin ordering** | Correct steps in the wrong order break silently (garments before clips lifted the run's arms overhead; garments before flesh lose the jiggle weights) | A pipeline that checks each stage's preconditions - see [01](01-character-spec-and-staged-pipeline.md) |
| 3 | **Checks that disagree with the eye** | A check passes something that looks wrong (Walter's reaching arms), or fails something that looks right (cloth pressed into a hip crease counted as a hole) | The checker, plus standard review renders - see [04](04-checks-that-match-the-eye.md) |
| 4 | **Re-derived decisions** | The same judgement is reasoned out again per character (garment ease, band height, flesh limits, firmness order, stance units) | Presets and defaults in the plugin, not in build scripts - see [01](01-character-spec-and-staged-pipeline.md) |
| 5 | **Tooling friction** | No regression tests, three plugin copies, manual installs, an unversioned plugin, state lost between Blender sessions, blends that mix unrelated scenes | The repo and its scripts - see [03](03-regression-harness-and-install.md) |
| 6 | **Feature gaps** | The pipeline cannot do it at all (hair, skirts, compression garments, muscle definition) or does it wrongly (jump sinks) | The owning plugin - see [05](05-feature-gaps.md) |

> **Picking this up in a new conversation?** Start with [NEXT.md](NEXT.md) - what is done, what is
> left in the order to take it, and what cost time to learn.

## Work items, in order of time saved

1. [Character spec and staged pipeline](01-character-spec-and-staged-pipeline.md) - one declarative file per character; stages with preconditions and saved results.
2. [Bone roles and rig profiles](02-bone-roles-and-rig-profiles.md) - name the root, pelvis, chest and anchors once; every plugin reads roles instead of guessing.
3. [Regression harness and install](03-regression-harness-and-install.md) - golden baselines, one rebuild-and-compare command, an install script, wardrobe under git. *Steps 1-5 done.*
4. [Checks that match the eye](04-checks-that-match-the-eye.md) - wardrobe hole precision, auto review strips, a motion critic.
5. [Feature gaps](05-feature-gaps.md) - jump floor bug, hair, compression garments, skirts, muscle definition, garment and join nondeterminism. *5.1 and 5.6 done.*
6. [Figure study lessons](06-figure-study-lessons.md) - what the September 2026 figure study round cost, the timing per stage, and a ranked list of plugin improvements by time saved per character.

Do 03 first if you are about to change shared code: without it every other item is verified on one
character at a time.

## Already fixed in this round (for context)

rig-anything 0.14.x / animate-anything 0.9.0 / humanform 0.6.x / follow-through 0.2.1:
keys land on the rotation channel a bone uses; floor checks ignore unskinned bones; every clip is
re-checked on playback before export and failures refuse; `cycle` takes `max_drop`, `stance_width`,
named `posture`, an in-clip upper body and gait styles; `arm_pose` guard; `bake_for_game`;
fixed-scale renders; the shared Godot `MovesController`; humanform briefs carry firmness, muscle,
cupsize, skin and iris, and ages outside ANSUR; a crouch ignores a ground root bone; buttocks jiggle
from the pelvis.

The project-side notes from before this round are in
`C:/Users/pauli/Code/GoDot/grungist-creek/docs/plugin-improvements.md` (some entries there are now
stale - they describe helpers that moved into rig-anything).
