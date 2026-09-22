"""Build one character from its spec: the thin caller a project's build script (or `run.sh`) is.

    blender -b --factory-startup --python-exit-code 1 --python build.py -- spec=<path.toml> \
        [from=<stage>] [to=<stage>] [force=1] [quality=draft|preview|final] [fresh=1] [save_outside=1]

It opens the spec's saved `[export] blend` first when it exists (`runner.open_saved`), so the stage records in
that file are used: a `[flesh]`-only edit reruns flesh, export and review (moves too when the rig or the weights moved; on a
dressed spec the garments come off and are cut again), a garment preset edit reruns garments, and an
unchanged spec skips everything. `fresh=1` builds from nothing instead (the saved file is then overwritten by
the new build, as always). Blender started on a .blend of your own (`blender -b <file> ...`) keeps that file:
it is the source a `body.source = "blend"` spec needs.

A relative `[export] blend` lives under $BLEND_DIR when it is set, else under the spec's project (the folder
holding `characters/`). A path outside both is refused before anything is built unless `save_outside=1`.

The plugins come from RA_SCRIPTS, HF_SCRIPTS, FT_SCRIPTS, WD_SCRIPTS (and LD_SCRIPTS) else the installed copies;
character-pipeline from this file's folder. Prints the statuses and the build record as JSON on the last line.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import character_pipeline  # noqa: E402

character_pipeline.reload_all()
from character_pipeline import runner  # noqa: E402


def main(args):
    report = runner.build(args["spec"], from_stage=args.get("from"), to_stage=args.get("to"),
                          force=args.get("force") in ("1", "true", "yes"), quality=args.get("quality"),
                          resume=args.get("fresh") not in ("1", "true", "yes"),
                          save_outside=args.get("save_outside") in ("1", "true", "yes"))
    statuses = {k: (v.get("status") if isinstance(v, dict) and "status" in v else v) for k, v in report.items()}
    print(json.dumps(statuses, default=str))
    return report


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(dict(a.split("=", 1) for a in argv if "=" in a))
