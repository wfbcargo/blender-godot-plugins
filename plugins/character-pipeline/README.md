# character-pipeline

Build a whole character for Godot 4.7 from one TOML spec. The steps are a humanform body from a
brief, then bake, hair, follow-through flesh, rig-anything's move set, follow-through spring bones for
hair that swings, wardrobe garments, export, and a review sheet of every clip at one scale.
The stages check the .blend before they run, so they refuse to run out of order, and they record
what they built from so a rebuild skips what has not changed.

Requires the humanform, rig-anything, follow-through and wardrobe plugins from this marketplace.

```
/plugin install character-pipeline@blender-godot-plugins
```

See [`skills/character-pipeline/SKILL.md`](./skills/character-pipeline/SKILL.md) for the spec format,
the stages and the rules, with Belle from grungist-creek as the worked example.

## Why

A character used to be a hand-written script calling five plugins in an order only its author knew.
Each ordering constraint was found by breaking it:
- **Garments before moves:** sent a run's arms over the character's head.
- **Garments before flesh:** lost the jiggle weights.

Tuned numbers (garment ease, flesh swing limits, gait styles) lived in the scripts and were found
again for each character. The spec holds who a character is, and the plugins hold the tuned numbers.
