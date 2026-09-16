# humanform

Adult human bodies in Blender, built in layers and measured between every one, for Godot 4.7.

- `skills/humanform` - the build ladder, its gates, and MPFB2 scripting notes.
- `skills/humancheck` - measure a body, render its contact sheet, run the critic.
- `skills/humanlib` - the library, the one-call pipeline, face design parts, eyes.
- `references/proportions.md` - what each measurement is and where its target comes from, with baselines.
- `references/critic-checklist.md` - the critic's protocol and question bank.
- `data/presets.json` - `realistic` and `stylized` proportion targets and feature thresholds.
- `scripts/humanform/` - `body`, `slicing`, `measure`, `views` (the gate); `sheet`, `landmarks`, `skeleton` (L0-L1);
  `scaffold` (MPFB2 fit, face stage, rig); `library`, `parts`, `eyes`, `pipeline` (reuse and parts). `scripts/humancheck_cli.py` runs it in background Blender.

Plan and research: `grungist-creek/docs/humanform-plan.md`.

Requires Blender 5.2 and, for the base mesh, the MPFB2 extension (2.0.17).

Resume notes for a new session: `grungist-creek/docs/humanform-resume.md`.
