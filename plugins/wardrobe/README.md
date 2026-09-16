# wardrobe

Clothing for rigged **Blender 5.x** characters headed to **Godot 4.7**: a garment that fits,
never shows the body through it, and swings where it hangs free - in levels of detail from a
crowd to a close-up.

## What's in it

| | |
|---|---|
| skill `wardrobe` | Cutting, fitting, skinning, hem bones, covered skin, export; the Godot runtime; the verifier. |
| `scripts/wardrobe/` | Blender Python: `rigmap`, `tailor`, `fit`, `cover`, `hem`, `spec`, `views`, `export`, `samples`. |
| `godot/addons/wardrobe/` | `wardrobe.gd` (equip, unequip, hide), `hem_modifier.gd`, `verify_wardrobe.gd`. |
| `references/garments.md` | How engines dress characters, why this design for Godot, what was measured. |

## Requirements

- Blender 5.x (the `blender` MCP server, or background `blender -b`).
- Godot 4.7.
- A rigged body: `rig-anything`. Optional: `follow-through` flesh - garments follow its jiggle bones.

## Install

Loads from `~/.claude/skills/wardrobe/` (as `wardrobe@skills-dir`). The repo copy is canonical;
install it with

```
python tools/install.py wardrobe
```

Copy `godot/addons/wardrobe` into each Godot project.

## The idea

1. **Skin the garment to the body's skeleton** - cut from the body, it keeps the body's weights.
2. **Don't draw the skin it covers** - but only where the cloth moves like the skin under it.
3. **Spring the parts that hang free** - a ring of bones at the hem and each cuff, off the torso
   and upper arm, with a backstop so the hem never swings into the body.

## Limits

- Shirts are cut; other garments come in modelled, through `fit` and `skin`.
- One garment verified at a time; layering is specified, not yet built.
- No simulated cloth (level 2) yet.
