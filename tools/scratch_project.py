#!/usr/bin/env python3
"""Make a scratch copy of the game to build its characters in, without touching its assets or blends.

    python tools/scratch_project.py <dir> [--who study_man,study_woman,belle] [--checkout <plugins worktree>]
                                    [--game <game project>] [--game-blend-dir <dir>] [--library <dir>]
                                    [--game-addons] [--no-import] [--force]

What every builder and critic did by hand (NEXT.md Step 0.5; 1-6 min each, and where paths went wrong):

- copies the game's `characters/`, its build scripts (`assets/humans/build_human.py`,
  `assets/belle/build_belle.py`, `assets/save_guard.py`), `project.godot` and the root scenes and scripts,
  `addons/` (then each addon this repo keeps, from the checkout, unless `--game-addons`), and each chosen
  character's current export folder (its glb, manifest and textures, without `review/`) into `<dir>` with the
  same layout;
- copies each chosen spec's current `.blend` into `<dir>/blends/`, so a build resumes from it;
- points every spec's `[export] blend` into the copy: a relative one already resolves under `BLEND_DIR`
  (character-pipeline 0.10.0), an absolute one is rewritten to its file name; then checks that every spec in
  the copy resolves under `<dir>` (it refuses otherwise);
- copies `~/.claude/humanform/library` (or `--library`) to `<dir>/humanform_library`, so humanform writes there;
- writes `env.sh` and `env.ps1` (PROJECT, BLEND_DIR, RA/HF/FT/WD/CP/LD_SCRIPTS at the checkout,
  HUMANFORM_LIBRARY, BLENDER, GODOT) and `build.sh <who> [key=value ...]`, which sources env.sh and runs the
  right build script;
- runs Godot `--headless --import` there and fails on any `ERROR` / `SCRIPT ERROR` line it prints;
- prints the one command that builds a figure.

The checkout defaults to the repo this file is in, so running it from a worktree builds against that worktree.
The game defaults to the real grungist-creek; it is only read. Its blends are found by resolving each spec's
`[export] blend` against `--game-blend-dir` (default: $BLEND_DIR, else the game's own, below).

Exit 0 when the copy is made and imports clean; 1 on a refusal or an import error, with the reason.
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import regress  # noqa: E402  (GODOT_ADDONS, find_godot, find_blender)

GAME = "C:/Users/pauli/Code/GoDot/grungist-creek"
GAME_BLEND_DIR = "C:/Users/pauli/Code/Blender"     # the game's blends (build_human.py's BLEND_DIR default)
DEFAULT_WHO = ("study_man", "study_woman", "belle")
BUILD_SCRIPTS = ("assets/save_guard.py", "assets/humans/build_human.py", "assets/belle/build_belle.py")
# which script builds whom: belle has her own, everyone else is build_human.py who=<id>
OWN_SCRIPT = {"belle": "assets/belle/build_belle.py"}
ROOT_FILES = ("*.godot", "*.gd", "*.gd.uid", "*.tscn", "*.tres", "*.svg", "*.svg.import")
SCRIPTS = {"RA_SCRIPTS": "rig-anything/scripts", "HF_SCRIPTS": "humanform/scripts",
           "FT_SCRIPTS": "follow-through/scripts", "WD_SCRIPTS": "wardrobe/scripts",
           "CP_SCRIPTS": "character-pipeline/scripts", "LD_SCRIPTS": "lookdev/blender"}
IMPORT_ERROR = re.compile(r"^\s*(ERROR|SCRIPT ERROR|USER ERROR)\b")


class Refused(Exception):
    pass


def fwd(path):
    """C:/-style: what Blender, Godot and a TOML file want on Windows."""
    return str(Path(path).resolve()).replace("\\", "/")


def _spec_module(checkout):
    """character-pipeline's spec.py from the checkout (stdlib only: no Blender needed)."""
    sys.path.insert(0, str(Path(checkout) / "plugins" / "character-pipeline" / "scripts"))
    from character_pipeline import spec
    return spec


BLEND_LINE = re.compile(r'^(\s*blend\s*=\s*)"([^"]*)"(.*)$', re.M)


def rewrite_blend(text):
    """The spec text with an absolute `[export] blend` made its file name. Returns (text, old or None)."""
    m = BLEND_LINE.search(text)
    if not m or not os.path.isabs(m.group(2)):
        return text, None
    new = os.path.basename(m.group(2).replace("\\", "/"))
    return text[:m.start()] + '%s"%s"%s' % (m.group(1), new, m.group(3)) + text[m.end():], m.group(2)


def _copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copytree(src, dst, ignore=()):
    shutil.copytree(src, dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".godot", *ignore))


def make(out, who=DEFAULT_WHO, checkout=REPO, game=GAME, game_blend_dir=None, library=None,
         game_addons=False, do_import=True, force=False, godot=None, blender=None, log=print):
    """Make the scratch project. Returns a dict of what it did; raises Refused."""
    out, checkout, game = Path(out).resolve(), Path(checkout).resolve(), Path(game).resolve()
    game_blend_dir = game_blend_dir or os.environ.get("BLEND_DIR") or GAME_BLEND_DIR
    library = Path(library or os.path.expanduser("~/.claude/humanform/library"))
    for p, what in ((game / "project.godot", "--game"), (game / "characters", "--game"),
                    (checkout / "plugins" / "character-pipeline", "--checkout")):
        if not p.exists():
            raise Refused(f"{what}: {p} does not exist")
    if out == game or game in out.parents:
        raise Refused(f"{out} is inside the game {game}: pick a scratch folder")
    if out.exists() and any(out.iterdir()) and not force:
        raise Refused(f"{out} exists and is not empty (--force to copy over it)")
    spec = _spec_module(checkout)
    who = list(who)
    missing = [w for w in who if not (game / "characters" / f"{w}.toml").is_file()]
    if missing:
        raise Refused(f"--who {missing}: no characters/<id>.toml in {game}")
    out.mkdir(parents=True, exist_ok=True)
    blends = out / "blends"
    blends.mkdir(exist_ok=True)
    (blends / ".gdignore").write_text("", encoding="utf-8")   # Godot would try to import the .blend files
    done = {"project": fwd(out), "blend_dir": fwd(blends), "checkout": fwd(checkout), "game": fwd(game),
            "who": who, "copied_blends": {}, "rewritten": {}, "missing_blends": []}

    # the project's files: project.godot, the root scenes and scripts, characters/, the build scripts, addons
    for pattern in ROOT_FILES:
        for f in game.glob(pattern):
            _copy(f, out / f.name)
    _copytree(game / "characters", out / "characters")
    for rel in BUILD_SCRIPTS:
        if (game / rel).is_file():
            _copy(game / rel, out / rel)
    if (game / "addons").is_dir():
        _copytree(game / "addons", out / "addons")
    done["addons_from_checkout"] = []
    if not game_addons:
        for addon, plugin in regress.GODOT_ADDONS.items():
            src = checkout / "plugins" / plugin / "godot" / "addons" / addon
            if src.is_dir():
                shutil.rmtree(out / "addons" / addon, ignore_errors=True)
                _copytree(src, out / "addons" / addon)
                done["addons_from_checkout"].append(addon)

    # every spec's blend into the copy; the chosen ones' current blends and exports copied
    for toml in sorted((out / "characters").glob("*.toml")):
        text = toml.read_text(encoding="utf-8")
        new, old = rewrite_blend(text)
        if old:
            toml.write_text(new, encoding="utf-8", newline="")
            done["rewritten"][toml.stem] = old
    for w in who:
        real = spec.load(str(game / "characters" / f"{w}.toml"))
        mine = spec.load(str(out / "characters" / f"{w}.toml"))
        src = spec.resolve_blend(real.export.blend, str(game), blend_dir_override=game_blend_dir)
        dst = spec.resolve_blend(mine.export.blend, str(out), blend_dir_override=str(blends))
        if src and os.path.isfile(src):
            _copy(Path(src), Path(dst))
            done["copied_blends"][w] = {"from": fwd(src), "to": fwd(dst)}
        elif src:
            done["missing_blends"].append(fwd(src))
        exp = Path(real.out_dir())
        if exp.is_dir():
            _copytree(exp, out / exp.relative_to(game), ignore=("review",))
    done["dropped_root_files"] = drop_unresolved(out)
    done["main_scene"] = fix_main_scene(out)
    outside = {}
    for toml in sorted((out / "characters").glob("*.toml")):
        ch = spec.load(str(toml))
        p = spec.resolve_blend(ch.export.blend, str(out), blend_dir_override=str(blends))
        if p and not spec.inside(p, [str(out)]):
            outside[toml.stem] = fwd(p)
    if outside:
        raise Refused(f"specs whose blend still resolves outside {out}: {outside}")

    # humanform's library, so a build writes a copy and never the real one
    lib = out / "humanform_library"
    if library.is_dir():
        _copytree(library, lib)
    else:
        lib.mkdir(exist_ok=True)
    (lib / ".gdignore").write_text("", encoding="utf-8")      # its sheets are not game assets
    done["humanform_library"] = fwd(lib)

    env = {"PROJECT": fwd(out), "BLEND_DIR": fwd(blends)}
    for var, sub in SCRIPTS.items():
        env[var] = fwd(checkout / "plugins" / sub)
    env["HUMANFORM_LIBRARY"] = fwd(lib)
    env["BLENDER"] = (blender or regress.find_blender()).replace("\\", "/")
    env["GODOT"] = (godot or regress.find_godot()).replace("\\", "/")
    done["env"] = env
    (out / "env.sh").write_text("# made by tools/scratch_project.py: source it\n" + "".join(
        "export %s='%s'\n" % kv for kv in env.items()), encoding="utf-8", newline="\n")
    (out / "env.ps1").write_text("# made by tools/scratch_project.py: dot-source it (. ./env.ps1)\n" + "".join(
        "$env:%s = '%s'\n" % kv for kv in env.items()), encoding="utf-8", newline="\r\n")
    (out / "build.sh").write_text(
        "#!/usr/bin/env bash\n"
        "# build.sh <who> [from=<stage>] [to=<stage>] [force=1] [fresh=1] ...: one character, in this copy\n"
        "set -euo pipefail\n"
        'HERE="$(cd "$(dirname "$0")" && pwd)"\n'
        '. "$HERE/env.sh"\n'
        'who="$1"; shift\n'
        'if [ "$who" = belle ]; then script="$PROJECT/%s"; else script="$PROJECT/assets/humans/build_human.py"; fi\n'
        'exec "$BLENDER" -b --factory-startup --python-exit-code 1 --python "$script" -- who="$who" "$@"\n'
        % OWN_SCRIPT["belle"], encoding="utf-8", newline="\n")
    done["build"] = "bash %s/build.sh %s" % (fwd(out), who[0] if who else "study_man")

    if do_import:
        done["import"] = godot_import(env["GODOT"], out, log=log)
        if done["import"]["errors"]:
            raise Refused("Godot --import printed %d error line(s), first: %s (full log: %s)" % (
                len(done["import"]["errors"]), done["import"]["errors"][0], done["import"]["log"]))
    return done


RES = re.compile(r'res://[^"\s)]+')


def drop_unresolved(out):
    """Remove the root scenes and scripts that name a res:// file the copy does not have (the demos of
    characters not chosen), until none does: they would fail the import's parse. A path with a `%` in it is a
    format string, not a reference. Returns the names removed."""
    dropped = []
    while True:
        gone = []
        for f in sorted(out.glob("*")):
            if f.suffix not in (".gd", ".tscn", ".tres") or not f.is_file():
                continue
            refs = {r for r in RES.findall(f.read_text(encoding="utf-8", errors="replace")) if "%" not in r}
            if any(not (out / r[len("res://"):]).exists() for r in refs):
                gone.append(f)
        if not gone:
            return dropped
        for f in gone:
            f.unlink()
            uid = f.with_name(f.name + ".uid")
            if uid.exists():
                uid.unlink()
            dropped.append(f.name)


MAIN_SCENE = re.compile(r'^run/main_scene="res://([^"]+)"[ \t]*\r?\n?', re.M)


def fix_main_scene(out):
    """The copy's main scene when it survived `drop_unresolved`; else the line is taken out of the copy's
    project.godot (Godot fails the import on a missing main scene) and None returned. Scenes are run by path."""
    path = out / "project.godot"
    text = path.read_text(encoding="utf-8")
    m = MAIN_SCENE.search(text)
    if not m or (out / m.group(1)).exists():
        return m.group(1) if m else None
    path.write_text(text[:m.start()] + text[m.end():], encoding="utf-8", newline="")
    return None


def godot_import(godot, project, log=print):
    """`--headless --import` in the copy. Returns {exit, errors, log}; the full output goes to import.log."""
    log(f"importing {project} ...")
    proc = subprocess.run([godot, "--headless", "--import", "--path", fwd(project)], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=1800)
    text = (proc.stdout or "") + (proc.stderr or "")
    path = Path(project) / "import.log"
    path.write_text(text, encoding="utf-8")
    errors = [line.strip() for line in text.splitlines() if IMPORT_ERROR.match(line)]
    if proc.returncode != 0 and not errors:
        errors = [f"exit {proc.returncode}"]
    return {"exit": proc.returncode, "errors": errors, "log": fwd(path)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dir")
    ap.add_argument("--who", default=",".join(DEFAULT_WHO), help="characters whose blends and exports to copy")
    ap.add_argument("--checkout", default=str(REPO), help="the plugins checkout the *_SCRIPTS point at")
    ap.add_argument("--game", default=GAME, help="the game project to copy (only read)")
    ap.add_argument("--game-blend-dir", default=None, help="where the game's relative blends live")
    ap.add_argument("--library", default=None, help="the humanform library to copy")
    ap.add_argument("--game-addons", action="store_true", help="keep the game's addons, not the checkout's")
    ap.add_argument("--no-import", action="store_true", help="skip Godot --headless --import")
    ap.add_argument("--force", action="store_true", help="copy into a folder that is not empty")
    ap.add_argument("--godot", default=None)
    ap.add_argument("--blender", default=None)
    a = ap.parse_args(argv)
    try:
        done = make(a.dir, who=[w for w in a.who.split(",") if w], checkout=a.checkout, game=a.game,
                    game_blend_dir=a.game_blend_dir, library=a.library, game_addons=a.game_addons,
                    do_import=not a.no_import, force=a.force, godot=a.godot, blender=a.blender)
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 1
    for w, c in done["copied_blends"].items():
        print(f"blend {w}: {c['from']} -> {c['to']}")
    for w, old in done["rewritten"].items():
        print(f"spec {w}: [export] blend {old} -> its file name (under BLEND_DIR)")
    for m in done["missing_blends"]:
        print(f"no blend yet at {m}: that build starts from nothing")
    if done["dropped_root_files"]:
        print("left out (they name files the copy does not have): %s" % ", ".join(done["dropped_root_files"]))
    print("addons from the checkout: %s" % (", ".join(done["addons_from_checkout"]) or "none (the game's)"))
    if "import" in done:
        print("godot --import: exit %d, no errors (%s)" % (done["import"]["exit"], done["import"]["log"]))
    print(f"scratch project: {done['project']}  (env: {done['project']}/env.sh, env.ps1)")
    print(f"build a figure:  {done['build']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
