
## 03:17 - merge gate - kind: gap
- What happened: merge agent for fig-genital-anatomy (branch head 94ac682, 2 commits ahead: 2ec1200, 94ac682; main at 9e3051c). Gate rule: merge only if every code-review blocking item is fixed.
- Code-review blocking item 1 (thighs pass into the genitals, DONE-WHEN) is NOT fixed. Fixer reports done_when_met=false: reviewer's all-vertex metric on study_man Crouch 27.3 mm (unchanged), Jump 30.1 mm (worse than 16.1); scrotum-only Run 11.5 mm, Crouch 16.2 mm (worse than 11.3). edge_big Walk still 8.4 mm.
- Items 2 (scrotum pinch) and 3 (muscle normal bake falls back to rays) are reported fixed with numbers (width 0.46/0.55; bake 'matched').
- The off-by-default exception only covers visual items, not code-review blocking items, so it does not apply.
- Attempts: 1. Wall time: ~2 min (read report, check git state).
- Resolution: NOT merged. Branch and worktree left in place (C:/Users/pauli/Code/blender-godot-plugins/.worktrees/fig-genital-anatomy). No version bumps, no install, no regress run, no grungist-creek sync, no NEXT.md edit.
- What should change: the thigh clearance needs a mechanism the fixer listed but did not try - a shaft corrective bone constrained forward/down, fixing MPFB crotch weights so inner thighs stop crossing (humanform / rig-anything), or a thigh-capsule collider in follow-through's Godot runtime. Also follow-through verify_flesh.gd needs a skin-into-neighbouring-skin check so within_body is not vacuous, and pipeline_genitals' clearance gate should be an absolute limit (e.g. <= 2 mm) instead of 'clearance_better', so regress can fail on it.
