---
name: wardrobe
description: Dress rigged Blender characters for Godot 4.7 - put a shirt (and later layers) on a body so it fits, the body never shows through, and the hem and cuffs swing as the character moves. Cuts a garment from the body it will be worn on, eases it off the skin (bridging hollows, hanging straight from the widest point), keeps or transfers the body's skin weights (jiggle bones included), hangs sprung hem and cuff bones with a backstop, and lists the skin it covers so Godot stops drawing it. In Godot, equips the garment onto the body's skeleton at runtime, hides the covered triangles and springs the hem; a headless verifier walks the body and counts holes and skin poking through. Use when asked to dress, clothe or put clothing, a shirt, T-shirt, top or garment on a character; about layered clothing, body poke-through, skin clipping through clothes, hiding the body under clothes, clothing swap or equip at runtime, hem or sleeve sway, or clothing level of detail for games versus animation.
---

# wardrobe

> **Building a whole character?** Write a spec and let `character-pipeline` run this plugin in the right order with the others - see that plugin's SKILL.md.

Clothing on a skinned body, the way games do it: the garment is **skinned to the body's
skeleton**, the skin it covers is **not drawn**, and the parts that hang free get **sprung
bones**. Background, research and sources: `${CLAUDE_PLUGIN_ROOT}/references/garments.md`.

The body needs a rig (`rig-anything`) and a walk to test with. It may carry
`follow-through` jiggle bones: a garment cut from it carries their weights, so a shirt
moves with the breasts and belly under it.

## Levels of detail

| level | what | cost (measured, sample shirt) | use |
|---|---|---|---|
| 0 | skinned garment, covered skin hidden | skinning only; the body draws 22% fewer triangles | far away, crowds |
| 1 | + hem and cuff bones (`hem_modifier.gd`) | 16 bones, ~50 us a frame in GDScript | the game default |
| 2 | leashed cloth: simulated offsets within a max distance of the skinned pose, with a backstop | not built | close-ups |
| film | Blender cloth sim, baked to shape keys or vertex animation textures | offline | an animated video |

`Wardrobe.equip(body, garment, {"hem": false})` is level 0.

## Blender

Through the `blender` MCP server, or `blender -b <file> --python <script>` - background
Blender leaves an open session alone. Always reload:

```python
import sys, importlib
P = r"${CLAUDE_PLUGIN_ROOT}/scripts"
if P not in sys.path:
    sys.path.insert(0, P)
import wardrobe
importlib.reload(wardrobe)
wardrobe.reload_all()
from wardrobe import tailor, fit, cover, hem, spec, export, views, samples, presets
```

**The whole sample in one call** (cut, fit, hem, cover, spec, export, read back):

```python
samples.shirt("Figure", r"C:/proj/assets/wardrobe/shirt.glb")
```

**A garment from a preset.** Tuned numbers belong in `presets/garments.json`, not in a build
script. Each preset holds the cut (`shirt`/`pants`) and the `tailor`, `paint`, `ease`, `hem`,
`cover` and `layer_cover` arguments, the spec kind, layer and colour, and a `note` saying why:

```python
presets.list()   # bra, briefs, dress_sleeveless, longsleeve, shorts, shorts_mid_thigh, skirt_knee, skirt_mini,
                 # sports_top, trousers, tshirt
r = wardrobe.dress("Belle", "sports_top", out_path=r"C:/proj/assets/belle/belle_sportstop.glb")
b = wardrobe.dress("Nora", "briefs", out_path=...)
t = wardrobe.dress("Nora", "trousers", out_path=..., over=[b["garment"]])   # eased over, hides what it covers
```

`dress(body, preset, name=None, colour=None, out_path=None, layer=None, over=())` runs tailor ->
paint_ease -> ease -> skin -> hem -> cover -> spec -> export, skipping a step whose arguments are
null; without `out_path` nothing is exported. It returns `verts`, `cut`, `skin`, `ease`, `hem`,
`cover` (summary) and `cover_report`, `jiggle_groups`, `export` (summary) and `export_report`,
`passed` and `problems` - it does not raise on a failed export. `sports_top` and
`shorts_mid_thigh` are Belle's; the other six are Nora's three layers (`presets.exclusive()`
lists what is worn instead of what). Nora's build also smooths armpit weights with project code
that `dress` does not run. The `dressed_presets` fixture holds both of Belle's on the sample body.

**Step by step:**

```python
g = tailor.shirt("Figure", sleeve=0.45, hem=-0.05, neck=(-0.04, 0.12))   # cut from the body
fit.paint_ease(g)                      # wd_ease: 1 at the hem, 0.3 at the cuffs, fading in
er = fit.ease(g, "Figure")             # push off the skin, bridge hollows, hang
fit.skin(g, "Figure")                  # the body's weights: kept if cut, transferred if modelled
hr = hem.prepare(g, "Figure", fabric="cotton_jersey")
cr = cover.compute(g, "Figure")        # the skin to hide
spec.write(g, spec.build(g, "Figure", cr, hr, er, kind="shirt"))
print(export.summarize(export.garment(g.name, r"C:/proj/assets/wardrobe/shirt.glb")))
```

```
Shirt: 16 hem bones on Figure_metarig (cotton_jersey), 1774 verts reweighted
  hem     8 bones, hinge 0.135 m, 1.75 Hz, 1345 verts, closest skin 0.031 m, on spine, spine.001, spine.002
  cuff.L  4 bones, hinge 0.06 m, 2.31 Hz, 213 verts, closest skin 0.0135 m, on upper_arm.L
Shirt over Figure: 5864 of 17112 body verts covered, 935 skinned unlike the cloth over them,
  4004 hidden, 1860 kept as edge (3 cm); 7625 of 34220 triangles not drawn
shirt.glb: PASSED
  Shirt: 56 joints, 16 hem bones (heads within 1e-06 m), 4004 body verts hidden, 1860 edge, 454 KB
```

**Look before exporting.** `views.render(["Figure", "Shirt"], out_dir, frames=[1, 9],
action="FigureWalk", views=("front", "three_quarter", "side", "back"), focus=Vector((0, 0, 1.05)),
distance=1.6)` renders Workbench pictures with the body skin-toned and the garment blue.
Read them: a hem tucking under the buttocks, ruffled cuffs, a crease or a notch where a
thigh drags the hem are all visible at a glance.

**Skirts and dresses** are built round the body, not cut from it - between the legs there is no skin to
cut, and a skirt does not cling to one leg:

```python
sk = tailor.skirt("Nadia_body", waist=0.16, length=0.85, flare=1.3)      # a tube: waistband to hem
dr = tailor.dress("Nadia_body", neck=(-0.10, 0.08), sleeve=-0.10, waist=0.30, length=0.85, flare=1.3)
r = wardrobe.dress("Nadia_body", "skirt_knee", out_path=...)             # or skirt_mini, dress_sleeveless
r = wardrobe.dress("Nadia_body", "skirt_knee", out_path=..., soft=True)  # follow-through cloth instead of hem bones
```

- **Shape.** Rays from outside toward a vertical axis through the hips find the body's surface (arms and
  fingers left out) at 64 angles every centimetre. The cloth takes that radius plus `ease` (15 mm; the
  waistband `waist_ease`, 5 mm) and hangs straight from the widest point above it. Below the widest hip
  level it opens to a hem whose girth is `flare` times the widest hip girth, and stays `clearance` (2 cm)
  off the legs at rest. Rings are blurred round (and, below the hips, down) and pushed back out.
- **Weights.** Cloth within `near_gap` (2.5 cm) of skin takes that skin's weights; cloth further than
  `far_gap` (6 cm) - between the legs, below the seat - goes by distance: pelvis above the hip joints,
  the thighs below (1/d^6 between the two), fading over `thigh_fade`. Smoothed 4 times, four a vertex.
- **Hem.** `hem.prepare` hangs the hem bones from whichever of the torso and the thighs holds the fabric
  at the hinge, half a bone off the midline.
- **Hide.** `cover` hides nothing below the hip joints (`cover_floor_z`) and nothing facing forward
  (`cover_max_front`), both from the cut. On the crowd that is 0-18 triangles: a skirt hides almost nothing.
- **A dress** is a `shirt` cut to the natural waist, eased, and a skirt zipped to its hem.
- **Soft.** `soft=True` (or `skirts.soft_body(g, body, fabric)`) pins everything above the widest hip level
  to its strongest bone and writes a follow-through `draped_tube` spec beside the wardrobe one;
  `Wardrobe.equip` builds the SoftBody3D when `addons/follow_through` is in the project. Verify it with
  follow-through's `verify_cloth.gd`. Nothing collides it with the legs yet.

Measured in Godot on three crowd women (Mei, Nadia, Rosa), walk, run and crouch, every preset passes; at
most 0.47% of a skirt's vertices inside a thigh. The sample Figure's knee skirt fails its walk (4.2%): that
walk crosses the feet over the midline.

**Trousers, shorts and briefs** are cut the same way:

```python
t = tailor.pants("Nora", name="Trousers", waist=0.26, leg=1.94)          # to the ankle
b = tailor.pants("Nora", name="Briefs", waist=0.10, leg=0.10, leg_angle=40)
fit.paint_ease(t, leg_band=0.30, leg=0.7)          # legs loosen toward the ankle
fit.ease(t, "Nora", over=[b])                      # at least 3 mm outside the briefs, too
hem.prepare(t, "Nora", leg_bones=6, leg_hinge=0.08, fabric="denim", under=[b])
```

**Layers.** Build from the inside out. Each garment is eased over the ones under it
(`fit.ease(..., over=[...])`), backstops its hems against them (`hem.prepare(..., under=[...])`)
and records what it hides of each of them, carried in its spec as `hide_layers`:

```python
layers = {b: cover.compute(t, b, max_gap=0.04, margin=0.015)}   # the trousers over the briefs
spec.write(t, spec.build(t, "Nora", cover.compute(t, "Nora"), hr, er, kind="trousers", layer=2, layers=layers))
```

`layer`: 1 underwear, 2 shirts and trousers, 3 sweaters and T-shirts over them, 4 jackets. A
whole wardrobe - a body sculpted from anatomy, rigged, walking on motion capture, and six garments
in three layers - is `grungist-creek/assets/wardrobe/build_person.py` and `build_outfits.py`.

**A modelled garment** (from Marvelous Designer, sculpted, bought): parent it to the rig with
an Armature modifier in the body's object space, then skip `tailor` - `fit.ease(g, body,
inflate=False)` only pushes it out where it is inside its ease, and `fit.skin` transfers the
weights from the nearest point of the body. On the sample shirt's own shape, transferred
weights shared a median 98% (5th percentile 82%) with the body's own.

### Parameters

| call | parameter | default | meaning |
|---|---|---|---|
| `tailor.shirt` | `sleeve` | 0.45 | along the arm: 0 shoulder joint, 1 elbow, 2 wrist; below 0 sleeveless |
| | `hem` | -0.08 | from the hip joints in torso lengths; negative is lower |
| | `neck` | (-0.04, 0.12) | front and back neckline heights from the neck's base, torso lengths |
| `tailor.pants` | `waist` | 0.30 | waistband above the hip joints, torso lengths |
| | `leg`, `leg_angle` | 1.9, 0 | along the leg: 0 hip joint, 1 knee, 2 ankle; opening rising outward (deg) |
| `fit.paint_ease` | `hem`, `cuff` | 1.0, 0.3 | ease weight at each opening; bands 16 cm and 6 cm |
| | `leg`, `waist` | 0.5, 0 | trousers' openings; `leg_band` 10 cm |
| `fit.ease` | `base`, `loose` | 6 mm, 25 mm | gap everywhere, plus `loose` x `wd_ease` |
| | `over`, `over_gap` | -, 3 mm | garments worn under this one, and the gap kept outside them |
| | `hang`, `hang_window` | 1.0, 15 cm | how fully cloth hangs straight down, and how far |
| `hem.prepare` | `fabric` | cotton_jersey | silk, cotton_jersey, cotton_poplin, wool, denim, leather |
| | `share` | 0.8 | the edge's weight the hem bones take |
| | `hem_hinge`, `cuff_hinge` | 14 cm, 6 cm | hinge line above the edge |
| | `leg_bones`, `leg_hinge` | 6, 8 cm | trouser and shorts openings |
| | `under` | - | garments the backstop measures to, besides the body |
| `cover.compute` | `agree` | 0.7 | weight in common for skin to be hidden under cloth |
| | `margin` | 3 cm | covered skin next to uncovered skin stays drawn |

A hem bone's frequency is a pendulum on its hinge stiffened by the fabric,
f = sqrt((sqrt(g/L)/2pi)^2 + stiff_hz^2).

## Godot

Copy `${CLAUDE_PLUGIN_ROOT}/godot/addons/wardrobe` into the project.

```gdscript
const Wardrobe = preload("res://addons/wardrobe/wardrobe.gd")

var body := preload("res://assets/wardrobe/nora.glb").instantiate()
add_child(body)
for g in ["briefs", "bra", "trousers", "tshirt"]:
    for rep in Wardrobe.equip(body, load("res://assets/wardrobe/nora_%s.glb" % g)):
        print(rep["garment"], " ", rep["body"], " ", rep["problems"])   # {tris_hidden, tris_total, layers}
        var hem = rep.get("hem")        # the HemModifier, null at level 0
Wardrobe.unequip(body, "Tshirt")        # the bra and the waistband come back
Wardrobe.worn_names(body)               # innermost layer first
```

`equip` adds the garment's bones the body lacks (by name, with the garment rig's rests),
reparents the garment mesh under the body's `Skeleton3D`, and rebuilds the body and every worn
garment without what the garments over them cover - the body by each spec's `hide`, an inner
garment by an outer one's `hide_layers` (imported meshes are kept, so `unequip` gives everything
back) - and builds the hem modifier. It took 50-76 ms for one shirt on a 17k-vertex body - do it
at load or behind a menu, not every frame. Only bones a garment is skinned to have to agree with
the body's; extra bones in its rig are added and ignored.

Surface materials are lost when a mesh is rebuilt: set `material_override` on the body and on
each garment.

`hem.response_scale`, `hem.paused`, `hem.kick(velocity)`, `hem.stats()` (peak swing, backstop
hits, microseconds a frame). `{"overrides": {"frequency_hz": 1.2}}` sets any bone parameter.

The demo is `wardrobe_demo.tscn` in grungist-creek: Nora walking on motion capture, a panel of
toggles for six garments (shorts or trousers, T-shirt or long sleeve), H hiding, L level of detail.

## Verify - always

```bash
godot --headless --fixed-fps 60 --path <project> -s res://addons/wardrobe/verify_wardrobe.gd -- \
    body=res://assets/flesh/figure.glb garment=res://assets/wardrobe/shirt.glb frames=480 every=8
```

It walks the body on a circle with its flesh jiggling, and every sampled frame skins every body
and garment vertex from the final pose and casts lines from the skin along each body normal. Hidden
skin with no cloth on that line is then looked at from 48 directions within 80 degrees of its
normal: it is a hole only if some view reaches it and sees into the body.

| check | limit | failing means |
|---|---|---|
| `holes` | 0.5% of hidden verts | hidden skin a viewer can see into: raise `agree` or `margin`, or ease |
| `occluded` | reported | hidden skin off the cloth that nothing outside can see (a fold, a crouch) |
| `coincident` | reported | hidden skin with cloth pressed within 3 mm |
| `poke` | 0.5% of drawn verts | drawn skin through the cloth: more ease, a lower `share`, or hide it |
| `thighs` | 0.5% of checked garment verts | a skirt or dress (spec kind; `thighs=all` for every garment) inside a leg: shorter, more flare |
| `hide_unmatched` | 0 | the body in Godot is not the body the garment was fitted to |
| hem finite, within `max_offset_m` | - | a spring blew up |

`still=true jiggle=false` checks the rest pose: it must read 0 and 0. `clip=` picks the clip by its
full name (Belle's are `Belle_Walk` and so on); check every clip a character has, because a crouch
opens what a walk never does. A run that measured nothing fails - an unknown clip (the problem lists
the clips the body has), a missing body or garment, or `samples: 0` - so a pass always means frames
were measured. Before wardrobe 0.2.2 an unknown clip and every `still=true` run passed with nothing sampled. `rigid=spine` skins the garment to one bone and must fail `thighs` in a crouch (the crowd's knee skirts: 149-162 vertices inside, against at most 4). `dump=<frame> dump_dir=` writes that sample's skinned body and garments as OBJ, headless. `cut=0.04` removes a
4 cm patch of the garment and must fail - the proof that the check still sees a real hole.
`shot=<frame>` without `--headless` renders that frame's holes from outside (body back faces
magenta, so magenta means you see in), and `trace=holes` prints each candidate's open views. Measured on Nora (30k
vertices, motion-capture walk, 360 frames): briefs, bra, trousers, T-shirt - holes 17 (0.13%),
skin through 50 on the upper arms (0.30%); briefs, bra, shorts, long sleeve - 16 and 0; underwear
alone - 2 and 94 (0.34%). Hem modifiers 40-51 us a frame each. `trace=true` prints every sample. Measured on the sample
shirt over 480 frames of walking with jiggle: level 1, holes 1 (0.03%), poke 10 verts on the
right thigh (0.08%); level 0, holes 1, poke 5 on the left buttock.

## Rules

**Flesh before garments.** A garment is cut from the skin and copies its weights, so a body
fleshed afterwards leaves the garment with no jiggle bones in it. `tailor.shirt`/`tailor.pants`
warn when the body carries a follow-through jiggle spec whose `ft_jiggle_*` vertex groups are
missing: printed as `wardrobe.tailor WARNING`, and listed under `warnings` in the garment's
`wardrobe_cut_report` (the key is there only when there is a warning). A body with no
follow-through spec is simply not fleshed and gets none. The cut garment's `wardrobe_cut`
property is also what rig-anything's arm clearance reads to leave garments out.

**Hide skin only where the cloth moves like it.** Hiding all covered skin, the sample shirt
left 38 thigh vertices uncovered in the worst frame of the walk (0.72%, a fail): the thighs
swing out from under a hem hung from the torso. `cover` hides a vertex only when the cloth
over it shares `agree` of its skin weights - 1 hole in the worst frame.

**Cloth hangs; it does not tuck in.** Eased along normals a shirt wrapped under the buttocks.
A radius field around the spine, made monotonic downward over a window, fixes it - but pushed
per angular sector it crumpled the back into ridges, and switched on at a hard height it left a
crease: the field is blurred, and the mask fades in below the armpits.

**Cut planes only cut the part they are for.** A sleeve plane square to an A-posed arm also
crosses the hips.

**Only bones are weights.** A `wd_hide_` group an earlier run left on the body was copied into
the next shirt as a weight of 1 and normalised its real weights away; it exported and read back
clean, and hid nothing. Every weight is filtered to the rig's deform bones, and a spec that
covers skin but hides none is invalid.

**Rays through vertices miss.** A cut garment puts each cloth vertex exactly on its skin
vertex's normal; the verifier's exact ray-triangle test missed every triangle around it and
reported 72 holes at rest. It uses a tolerance on the edges.

**Keep the body's exact weights on a cut garment.** Smoothed twice they spread past four
influences, and capping them back to four dropped 27% of one vertex's weight.

**Cloth over skin faces the way the skin does.** A ray from an inner thigh crosses the gap and
meets the briefs on the other leg: that skin was hidden, and the hole showed the fabric through it
as a strip down the thigh. `cover` counts a hit only where the cloth's normal agrees with the
skin's.

**Garments inherit the body's mistakes.** Blended thighs fused 12 cm below the crotch; every leg
cut left a tab of fabric hanging between the legs until the body itself was parted. A leg cut
takes only faces on its own side near the crotch, and everything on that side below it.

**Clear old hem bones before a rebuild.** A garment's copy of the rig carries every bone the rig
has; stale hem bones from an earlier build went out with rests 16 cm off.

**Buried skin is not a hole.** With the arms down an armpit folds shut: its normal meets the
body's own side before any cloth, and 60 such vertices a frame were counted holes. Hidden skin
beyond a cell of cloth - under a hem hanging 5-8 cm off the back - was counted too (47 at rest).

**A hole is what a viewer can see, so the verifier looks.** Belle's shorts failed crouch, crouch
walk and jump at 1.7-1.9% holes where renders showed none, and her sports top failed walk and jump.
Three different things, all measurement: rays started 0.5 mm off the skin stepped over cloth
pressed closer than that; a barycentric edge tolerance (0.03 mm on a 3 cm face) let a line slip
between two faces at a fold; and 8 belly vertices under the waistband had no cloth on their normal
at all - the raised thighs, 13-25 cm off, closed them in, past the old 12 cm body test. More ease
made it worse, because it widened that pocket. Lines now start at the skin with a 1 mm edge
tolerance, and a hidden vertex with no cloth on its normal is looked at from 48 directions: a view
must reach it past drawn skin and outward-facing cloth, and past it see the inside of the body or
nothing (skin in front of cloth shows the cloth). Belle passes every clip in both garments at the
same 0.5%; the 5 holes left were rendered and are real (a waistband gap on the walk, the top's hem
off the breast on the jump); cutting 6 triangles out of the shorts still fails.

**Model in the rest pose the clothes will bend least from.** A T-posed body put every shirt's
armpit through 80 degrees on the way to a walk, and it folded into spikes; posed 45 degrees down,
as games rig, it bends half as far.

**Lift over inner garments smoothly, and only over their surface.** Pushed out vertex by vertex a
shirt stepped at every edge of the bra under it; measured past a strap's cut edge it rose into a
2 cm spike. The lift is spread over neighbours and ignores hits beside an edge or far under it.

**Hem bones come off the torso.** Parented to the torso and taking 80% of the edge, a lifting
thigh no longer notches the hem; the price is the thigh can come through the hem from the
front, which the backstop (it only stops the hem moving *in*) does not catch.

## Limits

- The verifier measures skin through cloth and holes in the skin, over any set of garments; it
  does not yet measure an inner garment coming through an outer one.
- Level 2 (leashed cloth) is not built. Jolt has the skinned constraints it needs; Godot 4.7
  does not expose them, so it needs its own solver.
- The tailor cuts shirts, trousers, shorts and briefs and builds skirts and dresses; a modelled garment works
  through `fit` and `skin` but has not been verified in Godot yet.
- A soft (cloth) skirt has no leg colliders: the legs pass through it. Skirts are skinned; a stride that crosses
  the legs over the midline (the sample Figure's) puts a knee-length hem inside a thigh.
- The hem backstop is per bone against the rest gap, not a collision with the moving thighs.
- The body mesh's LODs are dropped when it is rebuilt without the hidden triangles.
