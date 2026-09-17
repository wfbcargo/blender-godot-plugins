---
name: flesh
description: Make the soft parts of a rigged body jiggle in Godot 4.7 - breasts, moobs, buttocks, a belly, love handles, arm flab, thighs, a bloater zombie's swollen torso - with one sprung jiggle bone per mass. Finds the masses from the surface and the skeleton (how far the body stands out of its lean envelope, inside anatomical zones from the type registry), or from zones Claude marks on labelled 2D renders mapped back onto the 3D mesh; adds the bones and feathered weights to the rig, picks a flesh material with a physical frequency, writes the spec, exports through rig-anything with the walk, and in Godot springs each bone after the animation with exact integration and volume-keeping squash. Use when a character, creature or zombie needs flesh that bounces, sways, wobbles or sloshes, when breasts, butts or bellies look rigid while walking, to add jiggle bones or jiggle physics, or to teach Claude a new kind of flesh from a painted or marked region.
---

# flesh

The flesh library of `follow-through`: soft masses on a **skinned** body. For free
volumes (jello, clay) use `follow-through:volume`. Concepts in
`${CLAUDE_PLUGIN_ROOT}/references/concepts.md`; research, measurements and sources in
`${CLAUDE_PLUGIN_ROOT}/references/flesh.md`.

Games move flesh with **jiggle bones**: one extra bone per mass, parented to the bone it
rides on, with the mass's vertices weighted to it, sprung every frame after the animation.
That is what this builds, because it survives glTF (bones and weights are core glTF), it
costs almost nothing, and the animation stays authored.

The body needs a rig first. `rig-anything` rigs it; its locomotion gives it a walk.

## Blender

Load as in `follow-through` (reload every time), then:

**1. Find the masses.**

```python
found = flesh.find_regions("Bloater")
print(flesh.summarize({"object": "Bloater", "rig": found["rig"], **found}))
res = flesh.render_heat("Bloater", r"C:/scratch/flesh", regions=found["regions"])
```

```
  bloater_belly  bloated   2686 verts, stands 0.166 m out, 22.9% of the body, on spine.003 (height 0.46, facing 44, spine)
  breast.L       soft_fat   664 verts, stands 0.151 m out, 3.4% of the body, on spine.002 (height 0.97, facing 50, spine)
  butt.L         soft_fat   217 verts, stands 0.123 m out, 0.9% of the body, on spine.001 (height 0.29, facing 142, spine)
  ...
  - belly: 0 bulging vertices in its zone
```

**Read the heat renders** (white lean, red standing out, blue a found region, green not
searched). The measure is good at *where and how far*; it is weaker at *what*: on the test
bloater it placed the moob bones 16-19 cm low, pulled toward the top of the belly. When a
region is wrong or missing, mark it in 2D (step 2).

How it finds them: core bones are joined into chains (pelvis to head, each limb); each
vertex belongs to its chain (from its skin weights) at an arc length; per angular sector
the lean radius along the chain is a robust lower envelope at two scales; excess is how
far the surface stands out of it. Flesh types in the registry each name a **zone** - which
chain, a height between hip (0) and shoulder (1) joints, a facing (0 front, 180 back), a
distance from the midline - and a region is excess inside a zone, grown and feathered. A type
with `"lean": "profile"` (`butt`) is measured from the side instead, across chains (Rules).

**2. Mark zones in 2D when the measure is not enough.** Looking at a picture is how to
decide what a mass is; the mapping back to vertices is exact:

```python
sheet = marks.render("Bloater", r"C:/scratch/marks", views=("front", "right"), focus="torso")
# read the PNGs: lettered columns, numbered rows, yellow numbers are geometric candidates
zones = [
    {"type": "bloater_belly", "view": "front", "cells": "G6:J8"},
    {"type": "bloater_belly", "view": "right", "ellipse": ["I7", 1.5, 2]},
    {"type": "breast", "view": "front", "ellipse": ["H5", 0.9, 0.9], "side": "R"},
    {"type": "breast", "view": "front", "ellipse": ["I5", 0.9, 0.9], "side": "L"},
    {"type": "butt", "view": "right", "candidate": 5},
]
found = marks.regions("Bloater", zones, sheet)
```

A mark is `cells` (a block "D7:H11" or a list), an `ellipse` [centre cell, half-width,
half-height in cells; weights fall off from the centre] or a `candidate` number. Only
vertices facing that view's camera and unoccluded count; views are merged; a paired type
without `side` splits at the midline. The renders are in the rest pose. Use `focus="torso"`
for small masses - a whole-body cell is 12 cm, a moob 6.5 cm. On the test bloater, marked
moobs landed 7.6 cm from truth where the measure alone missed by 19 cm.

In the front view the body's left (.L) is on the image's right.

**3. Rig and write the spec.**

```python
r = flesh.prepare("Figure")                                  # regions from the measure
r = flesh.prepare("Bloater", regions=found["regions"])       # or from marks
r = flesh.prepare("Figure", types=["breast", "butt"], overrides={"breast": {"frequency_hz": 3.2}})
print(flesh.summarize(r))
```

`prepare` adds `ft_jiggle_<region>` bones parented to each region's anchor bone, weights
each region to its bone (taken from the other weights in proportion, capped at four
influences a vertex), and writes the `jiggle` block. Re-running replaces them.
`flesh.set_params("Figure", "breast", damping_ratio=0.3)` changes values afterwards.

**4. Materials** (`types/builtin.json`):

| material | Hz | damping | squash | translate | gravity | used by |
|---|---|---|---|---|---|---|
| soft_fat | 2.7 | 0.25 | 0.5 | 0.35 | 1.0 | breast, belly, butt, love_handle, arm_flab |
| firm_flesh | 6 | 0.6 | 0.2 | 0.15 | 0.5 | thigh |
| bloated | 1.8 | 0.18 | 0.75 | 0.6 | 1.2 | bloater_belly |

soft_fat's 2.7 Hz is breast adipose tissue (E 3.25 kPa, Samani 2007) as a dome of 10 cm.
`aim` swings the bone toward the sprung tail, `translate` moves its head that share of the
offset, `squash` stretches it along its length with the cross-section at 1/sqrt so the
mass keeps its volume, `max_offset_m` caps the swing, `response` scales how hard the body's
own motion throws it (1 physical).

**Swing limits come from the type.** Nothing but `max_offset_m` keeps flesh out of the body, so
a type can own it: `max_offset_m = limit_share x peak_m`. `breast` has 0.66 (swung in further than
it stands out, the skin passes into the chest) and `butt` 0.9 (the 6.9 cm swing Godot's self-test
settled on Belle, now that her seat reads 7.8 cm out, not 3.7); each type's `limit_note` says why.
A type without one uses its material's `max_offset x 2 x peak_m`. Override per call with
`overrides={"butt": {"limit_share": 1.6}}`, afterwards with `set_params(..., max_offset_m=...)`,
or give a taught type one with `registry.define(..., limit_share=, limit_note=)`. Then measure them
in Godot and let `flesh.suggest_limits` set them (under Godot, below).

**5. Export with the animation - through rig-anything**, which carries extras since this
release, then read it back:

```python
from rig_analysis import export as rx
m = rx.export("Bloater", "Bloater_metarig", r"C:/proj/assets/bloater.glb",
              foot_bones=["foot.L", "foot.R"], actions=["BloaterWalk"], loop_clips=["BloaterWalk"])
print(export.summarize(export.verify(r"C:/proj/assets/bloater.glb", expect_meshes=["Bloater"])))
```

```
bloater.glb: PASSED
  Bloater: flesh, 22748 vertices in file, 11 jiggle bones in the skin, heads within 1e-05 m
```

`samples.export_bodies(out_dir)` does all of it for the two sample bodies.

## Godot

```gdscript
var body := preload("res://assets/bloater.glb").instantiate()
add_child(body)
for rep in FollowThrough.apply(body, {"routes": ["jiggle_bones"]}):
    var jiggle = rep["body"]            # a SkeletonModifier3D under the Skeleton3D
    jiggle.response_scale = 2.5         # games usually exaggerate
```

`jiggle.kick(Vector3(0, 1.5, 0))` knocks every region (a landing, a punch);
`jiggle.paused = true` holds them at rest; `jiggle.region_offsets()` reads them.

**Verify - always:**

```bash
godot --headless --path <project> -s res://addons/follow_through/verify_volume.gd -- scene=res://assets/bloater.glb
```

| check | limit | failing means |
|---|---|---|
| `head_error_m` | 0.01 | the bones are not where the spec put them: wrong armature or space |
| `axis_off_y` | 0.02 | the tail is off the bone's local Y: squash is disabled |
| `frequency_ok` | 20% of the damped frequency (damping < 0.5) | the spring is not what the material asks |
| `settled` | under 10% of the kick within 5 time constants | too little damping, or feedback |
| `within_limit` | max_offset_m while the clip plays | the swing is clamped - raise it or damping |

**Set the swing limits from Godot, not by guessing.** Drive the body round a fixed course and
measure each region's time on its limit:

```bash
godot --headless --fixed-fps 60 --path <project> -s res://addons/follow_through/verify_flesh.gd -- \
    scene=res://assets/bloater.glb response=1.5 out=C:/scratch/bloater_limits.json
```

The course walks, stops, turns, runs and jumps. The verifier prints one `FT_FLESH_LIMITS {json}` line
per body and fails a region on its limit 10% of the time or more. Then, in Blender:

```python
s = flesh.suggest_limits(r"C:/scratch/bloater_limits.json")   # or the log text, or the parsed dicts
print(limits.summarize(s))                                     # from follow_through import limits
flesh.apply_limits("Bloater", s)                               # writes max_offset_m into the spec; export again
```

How it works:
- Each region carries a **ladder**: its time on the limit measured on shadow springs given 33 other
  limits, from a quarter to four times its own. The flesh never feeds its load, so a rung is what the
  region will do with that limit.
- A region outside the **band, 3-9% of ticks on the limit**, gets the measured rung nearest 6%. It lands
  there when applied. The Figure and Bloater settled in one run, or two when a limit started past the
  ladder's end.
- `.L`/`.R` pairs share a limit.
- A breast is never raised past `limit_max_share` (0.66 x peak). It is reported `capped` instead: lower
  `response` or raise `damping_ratio`.
- The band is Belle's: her self-test fails at 10%, and her eye-approved regions sit at 7.5-9% there and
  4.4-4.9% on this course (`references/flesh.md` "Swing limits from Godot").
- Tune at the `response` the game plays at.
- A game's own self-test can report the same thing: call `jiggle.measure_limits()` when its script
  starts and `jiggle.print_limit_report("Belle")` when it ends.

## Rules

**Buttocks ride the pelvis.** A type's `"anchor"` names a **bone role** from rig-anything's body map
(`bodymap.build(...)["roles"]`: `pelvis`, `chest`, `head`, ...), and its jiggle bone is parented to
the bone that role names instead of the core bone nearest the region; without rig-anything,
`pelvis` falls back to the parent most leg chains start under. `butt` has `"anchor": "pelvis"`, the
bone the legs hang from. By nearest bone an MPFB woman's buttocks went on her thighs (her pelvis bone starts at
the hip joints, the seat hangs below): every stride swung them with the leg and a crouch's level
thigh turned gravity on them - on their limit half the self-test. The body's hip and shoulder
heights, which zones are measured between, come from the same roles (the legs' and arms' upper
bones) when rig-anything is importable. Every bone `prepare` adds carries `ft_role = "jiggle"`, so
rig-anything's body map leaves it out of the spine.

**Buttocks are read from the side, not from rings.** A buttock sits where the spine chain ends
and the thigh chains begin, so no chain has rings on both sides of it. On the sample figure the
spine's first ring was the crotch (0.02 m from the chain where the hips are 0.15-0.17 m), the lean
line started there, the sides of the hips stood 0.10-0.12 m proud and pulled the butt bones onto
them: 0.13 m from the true centres, the bloater's 0.06 m. Without the crotch the rings lost the
buttock instead (a bump at a chain's end reads as a ramp). On Belle the pelvis chain had four
rings, the line hugged the upper buttock and only the fold stood out: bone head at 0.794 m facing
down, hips at 0.873. Changing the zone's heights did neither any good. `butt` has
`"lean": "profile"`: per slice across the body, the silhouette behind the hip joints from the small
of the back to the back of the thigh, with the rings' refitted line under it. Both samples' butts
now land 0.02-0.04 m from their centres, and Belle's bone head 1 cm from her marked one read the
same way, facing straight back. It is at 0.858 m, level with the old marked head (0.862 m) but
7 cm deeper: a bone head sits the mass's depth and half its peak under the skin, and her seat
now stands 7.8 cm out, not 3.7. MPFB women and a heavy man whose butts rings never found get one.
Marks on a `profile` type are read the same way, and `render_heat` and the marks sheet draw it
(`flesh.shown`): inside a profile type's zone the heat is the profile, so a butt's red sits on the
mass, not on the hip sides and the fold under it.

**A chain's end ring takes its radius from its wall.** The same crotch ring skewed the rest of the
figure's torso: a refitted line starting at 0.02 m read its belly as standing 12 cm out (the bump is
3.5 cm), its breasts 8 cm low and gave it love handles it does not have. The first ring of every
chain, and the last ring built on a chain searched to its end, now measure radius only from vertices
whose normal is across the chain (`|n . axis| < 0.5`); every vertex in them is still measured against
that. The figure's breasts
land 0.057 / 0.061 m from their centres (0.079), its belly 0.076 m (0.108, peak 4.5 cm) and the false
love handles are gone; the bloater's arm flab moves 2 cm and no other bone of its more than 6 mm;
Belle's breasts move 1 mm and her butts not at all. A chain is searched to its end when it is a limb of
two segments or fewer, or a spine the shoulder cut takes nothing from; a longer limb ends at the wrist or
ankle and the spine at the cut, slices through the body rather than caps. Of the bodies measured only Belle has
one: her `root`-`spine` chain (two segments, to 0.961 m, where her spine chain starts), whose top ring
moves 72 hip vertices' excess by up to 1.3 cm and none of her regions.

**Skin decides the chain, not distance.** A bloater's wide torso sides lie closer to its
A-posed upper arms than to its spine; by nearest segment they were arm flesh. Bone heat
diffuses through the body and gives them to the spine.

**Zones, because excess cannot tell hips from a waist.** Hips wider than the waist stand
out of the envelope just like a belly does. A ring-baseline correction that cancelled
all-round excess also cost the figure its buttocks; zones fixed it instead.

**Search above the shoulder joints, not at them.** rig-anything's fit put the bloater's
shoulder joints 12 cm under the top of its shoulders, and a cut just above the joints
excluded its chest.

**Place a measured bone by excess squared, a marked bone by its mark.** Area-weighted, a
figure's breast bones sat 11 cm low, pulled by the ribcage front.

**Integrate exactly.** Semi-implicit Euler at 60 Hz is unstable above ~8 Hz when critically
damped; firm flesh lives at 5-10. The closed-form damped oscillator is stable at any rate;
measured frequencies matched the materials to 1%.

**The load is motion and the change of gravity.** Flesh modelled standing already sags; the
spring feels the anchor's acceleration and gravity relative to the rest pose, so it sags
further only when the body leans or lies down.

**Four influences, chosen here.** glTF keeps four joints a vertex; the exporter drops the
rest with a warning, and could drop the jiggle weight.

**Physical is subtle.** rig-anything's walk moves a chest 1.2 cm; soft fat answers with 4-5
mm. Correct, and hard to see - hence `response`.

## Limits

- No collision between flesh and the body or clothes: `max_offset_m` is the only guard.
- One bone per mass: no ripple across a large belly; add regions (mark two zones) for more.
- The head, hands and feet are not searched; cheeks and jowls need marks or a taught zone.
- A spring per bone, not a volume: flesh does not squash against a chair.
