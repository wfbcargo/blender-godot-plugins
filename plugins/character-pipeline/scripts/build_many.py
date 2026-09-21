"""Build several characters at once, one Blender process each, and say where each one's time went.

    python build_many.py <spec.toml> [<spec.toml> ...] [--jobs N] [--logs DIR] [-- key=value ...]

Each spec is built by `build.py` in its own `blender -b --factory-startup` process, at most `--jobs` at a time
(default: half the CPU cores, at most 4 - a final build's review renders on the CPU too, so more processes than
that slow each other down more than they overlap). Anything after `--` goes to every build.py call as it is
(`fresh=1`, `quality=draft`, `to=moves`...). Every build's full log is written to `--logs` (default: a new temp
folder) as `<spec stem>.log`, and when all are done a table is printed: status, wall seconds, the build's own
`total_seconds` and its three slowest stages - or, for a failed build, the error's last line (a failing stage
names itself, how long it ran and where the file was left: `runner.StageFailed`).

The exit code is the number of failed builds. It is plain Python (no bpy), so it runs from any shell.

Environment: BLENDER (default the 5.2 install), and whatever build.py reads (RA/HF/FT/WD/LD_SCRIPTS,
BLEND_DIR, HUMANFORM_LIBRARY) passes through. humanform's library takes a lock around its index writes, so
concurrent builds can share one library.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BLENDER = "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"


def default_jobs():
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def _last_json(text):
    """build.py prints the statuses and the build record as JSON on one line; the last such line."""
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def _error(text):
    """The most telling line of a failed build's log: a StageFailed / BuildRefused / StageRefused message, else the
    last line that looks like an exception."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for key in ("StageFailed:", "BuildRefused:", "StageRefused:", "SpecError:"):
        for l in reversed(lines):
            if key in l:
                return l[l.index(key):]
    for l in reversed(lines):
        if "Error" in l and not l.startswith("Error: script failed"):
            return l
    return lines[-1] if lines else "no output"


def build_one(spec, extra, logs, blender):
    stem = os.path.splitext(os.path.basename(spec))[0]
    log = os.path.join(logs, f"{stem}.log")
    cmd = [blender, "-b", "--factory-startup", "--python-exit-code", "1",
           "--python", os.path.join(HERE, "build.py"), "--", f"spec={os.path.abspath(spec)}", *extra]
    t0 = time.time()
    with open(log, "w", encoding="utf-8", errors="replace") as fh:
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT).returncode
    wall = round(time.time() - t0, 1)
    with open(log, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    out = {"spec": stem, "rc": rc, "wall_s": wall, "log": log}
    record = _last_json(text) if rc == 0 else None
    if record and isinstance(record.get("build"), dict):
        b = record["build"]
        out["total_s"] = b.get("total_seconds")
        out["stages"] = b.get("stage_seconds", {})
        out["skipped"] = b.get("skipped", [])
    if rc != 0:
        out["error"] = _error(text)
    return out


def table(results):
    rows = []
    for r in results:
        if r["rc"] == 0:
            slow = sorted(r.get("stages", {}).items(), key=lambda kv: -kv[1])[:3]
            what = ", ".join(f"{k} {v:g}" for k, v in slow) or "nothing ran"
            rows.append(f"  ok    {r['spec']:<22} wall {r['wall_s']:>6.1f} s  build {r.get('total_s') or 0:>6.1f} s  {what}")
        else:
            rows.append(f"  FAIL  {r['spec']:<22} wall {r['wall_s']:>6.1f} s  {r['error']}\n        log: {r['log']}")
    return "\n".join(rows)


def main(argv):
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--jobs", type=int, default=default_jobs())
    ap.add_argument("--logs", default=None)
    a = ap.parse_args(argv)
    # characters/pipeline.toml is the project's settings (spec.PROJECT_CONFIG), not a character: a glob over
    # characters/*.toml picks it up, and it failed as a spec with "unknown field(s) blend"
    skipped = [s for s in a.specs if os.path.basename(s) == "pipeline.toml"]
    a.specs = [s for s in a.specs if s not in skipped]
    if skipped:
        print(f"skipping {', '.join(skipped)}: the project's pipeline settings, not a character")
    missing = [s for s in a.specs if not os.path.isfile(s)]
    if missing:
        print(f"no such spec: {', '.join(missing)}", file=sys.stderr)
        return 2
    logs = a.logs or tempfile.mkdtemp(prefix="build_many_")
    os.makedirs(logs, exist_ok=True)
    blender = os.environ.get("BLENDER", DEFAULT_BLENDER)
    print(f"building {len(a.specs)} spec(s), {a.jobs} at a time; logs in {logs}", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        futures = [pool.submit(build_one, s, extra, logs, blender) for s in a.specs]
        results = []
        for f in futures:
            r = f.result()
            results.append(r)
            print(f"  {'done' if r['rc'] == 0 else 'FAILED'}: {r['spec']} ({r['wall_s']} s)", flush=True)
    print(table(results))
    failed = sum(1 for r in results if r["rc"] != 0)
    print(f"BUILD_MANY DONE {len(results) - failed} ok, {failed} failed, {time.time() - t0:.1f} s wall")
    return failed


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
