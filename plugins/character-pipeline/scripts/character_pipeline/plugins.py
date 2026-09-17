"""Where the plugins a character is built from are found, and their versions.

Each comes from its environment variable (the names grungist-creek's build scripts and the regression
fixtures use), else the installed copy under ~/.claude/skills. `use()` puts them on sys.path and
reloads them, since a Blender session outlives edits to them.

The four in `VARS` build every character, so `use()` imports them and their versions go into every
stage's input hash. lookdev is `OPTIONAL`: only humanform's hair reads it (its hair material), and hair
falls back to a flat material without it. So `use()` imports lookdev only where it is present, and its
version goes only into the hash of a stage that reads it (`stage_versions`), so a lookdev release never
invalidates a body, bake, flesh, moves, garments or export record.
"""

import importlib
import importlib.util
import json
import os
import sys

VARS = {"rig_analysis": ("RA_SCRIPTS", "rig-anything"), "humanform": ("HF_SCRIPTS", "humanform"),
        "follow_through": ("FT_SCRIPTS", "follow-through"), "wardrobe": ("WD_SCRIPTS", "wardrobe")}
# Plugins a build uses when they are there: package -> (variable, plugin, its folder under the plugin)
OPTIONAL = {"lookdev_blender": ("LD_SCRIPTS", "lookdev", "blender")}
# The optional packages a stage reads, by stage name, as a function of the spec
STAGE_READS = {"hair": lambda ch: ("lookdev_blender",) if ch.hair is not None and ch.hair.kind != "shell_bun" else ()}


def scripts(package):
    if package in OPTIONAL:
        var, plugin, sub = OPTIONAL[package]
    else:
        (var, plugin), sub = VARS[package], "scripts"
    return os.environ.get(var) or os.path.join(os.path.expanduser("~"), ".claude", "skills", plugin, sub)


def available(package):
    """Whether an optional package is present in its folder."""
    return os.path.isfile(os.path.join(scripts(package), package, "__init__.py"))


def use(*packages):
    """Import (and reload) the named packages from their scripts folders. Returns the modules.

    With no names: the four every build needs, and each optional one that is present. A name given
    outright is imported whether optional or not, and raises if it is missing."""
    if not packages:
        packages = tuple(VARS) + tuple(p for p in OPTIONAL if available(p))
    out = []
    for package in packages:
        path = scripts(package)
        if path not in sys.path:
            sys.path.insert(0, path)
        mod = importlib.import_module(package)
        if hasattr(mod, "reload_all"):
            mod.reload_all()
        out.append(mod)
    return out


def _version(package, plugin):
    manifest = os.path.join(os.path.dirname(scripts(package)), ".claude-plugin", "plugin.json")
    try:
        with open(manifest, encoding="utf-8") as fh:
            return json.load(fh)["version"]
    except (OSError, ValueError, KeyError):
        return "?"


def versions(*optional):
    """{plugin: version} of the four checkouts every build uses - part of every stage's input hash, so a
    plugin update rebuilds what it could have changed - plus the named optional packages ("absent" when
    not present)."""
    out = {plugin: _version(package, plugin) for package, (_, plugin) in VARS.items()}
    for package in optional:
        _var, plugin, _sub = OPTIONAL[package]
        out[plugin] = _version(package, plugin) if available(package) else "absent"
    return out


def stage_versions(ch, stage):
    """The versions a stage's input hash covers: the four, and the optional plugins that stage reads."""
    reads = STAGE_READS.get(stage)
    return versions(*(reads(ch) if reads else ()))
