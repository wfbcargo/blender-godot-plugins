#!/usr/bin/env bash
# The character-pipeline command-line build, as a template: copy it next to your specs and set the paths.
#
#   ./run.sh <spec.toml> [from=<stage>] [to=<stage>] [force=1] [quality=draft] [fresh=1]
#
# The build opens the spec's saved [export] blend when it exists, so only the stages whose inputs changed run
# (a [flesh] edit: flesh to review, about half a build; on a dressed spec it restarts from body).
# fresh=1 builds from nothing.
#
# Point the *_SCRIPTS variables at a checkout to build against it; unset, the installed skills are used.
# HUMANFORM_LIBRARY: a scratch copy when building outside your own project, or the real library is written.
set -euo pipefail
BLENDER="${BLENDER:-C:/Program Files/Blender Foundation/Blender 5.2/blender.exe}"
CP_SCRIPTS="${CP_SCRIPTS:-$HOME/.claude/skills/character-pipeline/scripts}"
# export RA_SCRIPTS=... HF_SCRIPTS=... FT_SCRIPTS=... WD_SCRIPTS=... LD_SCRIPTS=... HUMANFORM_LIBRARY=...
# BLEND_DIR: where a relative [export] blend lives (else the spec's project); saving outside both is refused
# unless save_outside=1.
spec="$1"; shift
# Blender and Godot want C:/... paths, not /c/...
if command -v cygpath >/dev/null 2>&1; then spec="$(cygpath -m "$spec")"; CP_SCRIPTS="$(cygpath -m "$CP_SCRIPTS")"; fi
exec "$BLENDER" -b --factory-startup --python-exit-code 1 --python "$CP_SCRIPTS/build.py" -- spec="$spec" "$@"
