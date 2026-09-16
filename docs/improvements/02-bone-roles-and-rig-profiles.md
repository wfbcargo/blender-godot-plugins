# 02 - Bone roles and rig profiles

Category: **1 body-source quirks**.

## Problem

Every plugin works out from geometry which bone is which, and each rediscovers the same MPFB
quirks independently. A fix in one plugin helps only that plugin.

`rig_analysis/bodymap.build(rig_name, forward, up, floor)` returns `axial`, `pelvis_index`, `torso`,
`rear`, `neck`, `head`, `tail`, `limbs` (each with `role` leg|arm, `upper`, `lower`, `end`,
`rest_bend_rel`, ...), but **no named roles for root, pelvis, chest, breast or head anchors**, and
no idea which bones are controls that carry no skin. A ground root simply sits on the axial chain.

## What we saw (the same body, found five times)

| Quirk | Where it was rediscovered | Current local fix |
|---|---|---|
| Ground root bone lies at the floor, carries no skin | floor check (dips 3-7 cm); crouch took it for the belly (no hip drop, 33 cm hip shift on straight legs) | `actions.py:~1001` skinned bones only; `keyposes.py:437` axial bones above the ankles; `motion.Body.skinned_bones()` |
| Bones rotate in Euler XYZ | keys written to quaternions were ignored; legs never moved | `verify.adopt_rotation_modes`, `rotation_mode_mismatches` |
| Forearm rests bent 40 deg | copied `upper_body` assumed straight arms | `upper.py` aims from each arm's rest bend plane |
| Rest stance straddled (ankles ~35 cm apart) | every walk straddled | `stance_width` on `cycle` |
| >4 weights, 97 shape keys, helper mask | glTF exporter trimmed silently | `export.bake_for_game`, preflight warnings |
| Non-bone `joint-*`/`helper-*` vertex groups | export | `export.py:188` strips them |
| Flesh bone placement | follow-through put both breast bones on Belle's chin | marked by hand on render sheets |
| Buttocks anchor | nearest bone was the thigh; jiggle sat on its limit half the time | `flesh.py:687 _pelvis_bone`, `builtin.json` `"anchor": "pelvis"` |
| Spine / limb names | wardrobe finds them by name regex | `wardrobe/rigmap.py:43 humanoid()` |
| Rigify off | any fresh or `--factory-startup` Blender: `fit_basic_human` dies with `'Armature' object has no attribute 'rigify_colors'` | the fixtures call `H.enable_addons("rigify")`; `fit` should enable it itself, or name it in the error |

Nearest-geometry bone picks that can go wrong the same way: `flesh.py:709 _anchor_bone`,
`flesh.py` nearest chain / core ancestor, `maw.py:1087`, `wardrobe/hem.py:183-200`,
`wardrobe/tailor.py:56 _keep_piece`.

## Design

**Roles in the body map.** `bodymap.build` adds a `roles` dict naming bones by function:

```
roles = {
  "root": "root",            # ground/motion bone: on the axial chain, unskinned or wholly below the ankles
  "controls": [...],         # bones that carry no skin weight
  "pelvis": "spine",         # the bone >=2 leg chains start under
  "chest": "spine.003",      # top of the ribcage: the bone the arms' girdles attach to
  "neck": [...], "head": "spine.005",
  "breast_anchor": "spine.003", "butt_anchor": "spine",
  "hand.L": ..., "foot.L": ..., ...
}
```

Derived once, from geometry and skin weights, with the existing girdle/attachment logic. Every
consumer reads `bm["roles"]` instead of re-deriving: the floor and crouch checks skip `root` and
`controls`; follow-through's type registry names an anchor **role** (`"anchor": "chest"`) not a
search; wardrobe's `rigmap` maps from roles rather than name regexes.

**Rig profiles.** A profile is a small JSON of facts known ahead of time for a body source, applied
before geometry is consulted and checked against it:

```
profiles/mpfb_game_engine.json
{
  "detect": {"bones_all": ["root", "spine", "spine.005", "thigh.L", "forearm.L"], "vertex_groups_any": ["joint-*"]},
  "roles": {"root": "root", "pelvis": "spine", "chest": "spine.003", "head": "spine.005"},
  "rotation_mode": "XYZ",
  "rest": {"forearm_bend_deg": 40, "stance_half_width_share": 0.1},
  "bake": {"shape_keys": true, "mask_modifiers": ["Hide helpers"], "strip_groups": ["joint-*", "helper-*"], "max_influences": 4}
}
```

- humanform writes the profile name onto the rig it builds (`rig["body_profile"] = "mpfb_game_engine"`);
  rig-anything's own `fit_basic_human` rigs and Rigify get profiles too.
- `bodymap.build` loads the profile if the rig names one or `detect` matches, and **verifies** each
  claimed role against geometry (a warning, not a silent override, when they disagree).
- `bake_for_game` and `preflight` read the profile's `bake` block instead of guessing.

**Where it lives**: rig-anything (`rig_analysis/bodymap.py`, new `rig_analysis/profiles/`), because
follow-through, wardrobe and animate-anything already import `rig_analysis`. Wardrobe gets a thin
adapter so it keeps working on rigs without rig-anything.

## Steps

1. **Inventory.** Grep all plugins for bone picks by name, nearest geometry, or MPFB special cases
   (the table above is the starting list) and write each as "needs role X".
2. **Roles in `bodymap.build`.** Add `roles` with `root`, `controls` (zero skin weight, using
   `motion.Body.skinned_bones()` logic), `pelvis` (move `flesh._pelvis_bone`'s rule here), `chest`,
   `neck`, `head`, per-limb ends. Unit-check on the 16 people, Belle, Rigify `basic_human`,
   `QuadTest_rig`, `Rat_metarig` (all in `C:/Users/pauli/Code/Blender/belle_demo.blend`, scene
   `Scene`) - see 03 for the harness.
3. **Replace local fixes with roles**: `actions._check_common` floor set, `keyposes.crouch_key` trunk,
   `motion.Body.skinned_bones` callers, `flesh._pelvis_bone` / `_anchor_bone` (registry `anchor`
   takes a role name), `wardrobe/rigmap.humanoid`.
4. **Profiles.** Add `rig_analysis/profiles/` with `mpfb_game_engine.json`, `rigify_basic_human.json`,
   `rig_anything_generic.json`; `bodymap.load_profile(rig)`; `export.bake_for_game` and `preflight`
   read the `bake` block. humanform `scaffold.finish` / pipeline tags the rig.
5. **Flesh placement from roles.** follow-through's breast region head/tail: start from
   `roles.breast_anchor` and the region's peak normal, not the nearest core bone - the fix for bones
   landing on the chin.
6. **Docs**: rig-anything SKILL.md "Bone roles" section; joint-conventions reference points at roles;
   follow-through registry docs describe `anchor` as a role.

## Done when

- No plugin code names an MPFB bone or matches bone names by regex outside `profiles/` and the role
  derivation.
- Belle's flesh finds its breast and buttock bones with **no hand-marked zones** and no bone on the
  chin; buttock jiggle rides the pelvis via the role.
- All regression outputs (03) unchanged except where a known wrong placement is corrected.
- A Mixamo- or Rigify-rigged body gets correct roles with a warning-free report, or a clear warning
  naming the role it could not find.
