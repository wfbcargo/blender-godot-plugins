# tools-scratch-project - lab notebook

Round realism-step1 (Step 0.5 tooling + Step 1 hair, second attempt). Branch `tools-scratch-project` in both
repos. Owns `tools/scratch_project.py`, character-pipeline `spec.py` ([export] blend resolution) and
`runner._save`; not `runner._build` or stage hashes (cp-cascade-stop).

## 13:01 start

Read NEXT.md, CLAUDE.md, 06 rank 2, spec.py, runner.py, build_human.py, build_belle.py, the pipeline fixtures.

Findings before writing anything:
- `[export] blend` is used raw (`ch.export.blend`) in `runner.open_saved` and `runner.build` -> `_save`. A
  relative path resolves against the process cwd today, which is why `pipeline_woman` overrides it with an
  absolute path.
- The export stage hashes the `export` section, `blend` string included. So keeping the *raw string* in the
  section (and resolving only where the file is opened/saved) means a spec copied byte-for-byte to a scratch
  project hashes identically, and its copied blend resumes with every stage "unchanged". That is the design:
  resolve at use, never rewrite the string. Changing the game's specs from absolute to relative moves the
  export hash once (export + review rerun, ~17 s), not the outputs.
- `BLEND_DIR` appears only in docs today (CLAUDE.md, 03); nothing reads it.
- `tools/` changes make `--quick` select every fixture.
