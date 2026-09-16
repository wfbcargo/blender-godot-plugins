#!/usr/bin/env python3
"""Install plugins from this repo into ~/.claude/skills, the copy Claude Code actually loads.

    python tools/install.py wardrobe rig-anything
    python tools/install.py --all              # every repo plugin already installed there
    python tools/install.py --all --dry-run    # show what would change, write nothing

The repo is the source. The installed copy is mirrored from it: changed files are copied,
files the repo no longer has are removed, and __pycache__ and similar are left alone.

A copy edited in place would be lost by that, so each install writes `.install.json` next to
the plugin with a hash of every file it wrote. Next time, a file that no longer matches that
record was edited after install, and the install refuses and lists it - move the edit into the
repo first, or pass --force to discard it. An installed copy with no record (installed by hand)
is compared against the repo instead. An installed copy that is itself a git checkout is never
overwritten: it is a source, not an install.

Line endings are ignored when comparing, since a Windows checkout has CRLF where the installed
copy may have LF.

This installs for this machine only. For other machines: push, then update the marketplace
(`/plugin marketplace update paul-claude-plugins`).
"""
import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGINS = REPO / "plugins"
DEFAULT_DEST = Path.home() / ".claude" / "skills"
RECORD = ".install.json"
# Never copied, compared or removed.
IGNORE = ["__pycache__", "*.pyc", "*.blend1", ".git", ".DS_Store", RECORD]


def ignored(rel):
    return any(fnmatch.fnmatch(part, pat) for part in Path(rel).parts for pat in IGNORE)


def tree(root):
    """Relative posix path -> Path for every file under root, ignored names skipped."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not ignored(d)]
        for name in filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if not ignored(rel):
                out[rel] = path
    return out


def digest(path):
    data = path.read_bytes()
    if b"\0" not in data[:8192]:  # text: compare with LF endings
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def version(root):
    try:
        return json.loads((root / ".claude-plugin" / "plugin.json").read_text("utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        return "?"


def git(*args):
    try:
        return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def plan(name, dest_root, force):
    """What installing `name` would do, or the reason it must not."""
    src = PLUGINS / name
    dst = dest_root / name
    if not (src / ".claude-plugin" / "plugin.json").is_file():
        return {"name": name, "refuse": f"no plugin at {src}"}
    if (dst / ".git").exists():
        return {"name": name, "refuse": f"{dst} is a git checkout - a source, not an install; "
                                         "move it into this repo before installing over it"}

    src_files = {rel: digest(p) for rel, p in tree(src).items()}
    dst_files = {rel: digest(p) for rel, p in tree(dst).items()} if dst.exists() else {}

    # Edits made in the installed copy since it was installed.
    record_path = dst / RECORD
    if record_path.is_file():
        baseline = json.loads(record_path.read_text("utf-8"))["files"]
        against = "the last install"
    else:
        baseline = src_files
        against = "the repo (no install record)"
    local = sorted(rel for rel in set(baseline) | set(dst_files)
                   if dst.exists() and baseline.get(rel) != dst_files.get(rel))

    result = {
        "name": name, "src": src, "dst": dst, "src_files": src_files,
        "old": version(dst) if dst.exists() else None, "new": version(src),
        "add": sorted(set(src_files) - set(dst_files)),
        "change": sorted(r for r in src_files if r in dst_files and src_files[r] != dst_files[r]),
        "remove": sorted(set(dst_files) - set(src_files)),
    }
    if local and not force:
        shown = "\n".join(f"      {r}" for r in local[:20])
        more = f"\n      ... and {len(local) - 20} more" if len(local) > 20 else ""
        result["refuse"] = (f"{dst} differs from {against} in {len(local)} file(s):\n{shown}{more}\n"
                            "    Move those edits into the repo, or pass --force to discard them.")
    return result


def apply(p):
    src, dst = p["src"], p["dst"]
    for rel in p["add"] + p["change"]:
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, target)
    for rel in p["remove"]:
        (dst / rel).unlink()
    for dirpath, dirnames, filenames in os.walk(dst, topdown=False):
        d = Path(dirpath)
        if d != dst and not ignored(d.relative_to(dst).as_posix()) and not any(d.iterdir()):
            d.rmdir()
    record = {
        "plugin": p["name"], "version": p["new"], "source": str(src),
        "commit": git("rev-parse", "--short", "HEAD"),
        "installed": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": p["src_files"],
    }
    (dst / RECORD).write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", "utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("plugins", nargs="*", help="plugin names under plugins/")
    ap.add_argument("--all", action="store_true",
                    help="every repo plugin that is already installed in the destination")
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST, help=f"default {DEFAULT_DEST}")
    ap.add_argument("--force", action="store_true", help="discard edits made in installed copies")
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = ap.parse_args(argv)

    names = list(args.plugins)
    if args.all:
        names += [d.name for d in sorted(PLUGINS.iterdir())
                  if (args.dest / d.name).is_dir() and d.name not in names]
    if not names:
        ap.error("name at least one plugin, or pass --all")

    failed = False
    for name in names:
        p = plan(name, args.dest, args.force)
        if "refuse" in p:
            print(f"  {name}: REFUSED - {p['refuse']}")
            failed = True
            continue
        counts = f"{len(p['change'])} changed, {len(p['add'])} added, {len(p['remove'])} removed"
        old = p["old"] or "not installed"
        if not (p["add"] or p["change"] or p["remove"]) and (p["dst"] / RECORD).is_file():
            print(f"  {name} {p['new']}: up to date")
            continue
        dirty = git("status", "--porcelain", "--", f"plugins/{name}")
        note = "  (uncommitted changes in the repo)" if dirty else ""
        print(f"  {name} {old} -> {p['new']}: {counts}{note}")
        if args.dry_run:
            for kind in ("add", "change", "remove"):
                for rel in p[kind]:
                    print(f"      {kind:6} {rel}")
        else:
            apply(p)

    if args.dry_run:
        print("dry run - nothing written")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
