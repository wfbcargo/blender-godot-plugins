"""Where the plugins a character is built from are found, and their versions.

Each comes from its environment variable (the names grungist-creek's build scripts and the regression
fixtures use), else the installed copy under ~/.claude/skills. lookdev (`LD_SCRIPTS`) is its `blender`
folder, where humanform's hair takes its material from. `use()` puts them on sys.path and reloads them,
since a Blender session outlives edits to them.
"""

import importlib
import json
import os
import sys

VARS = {"rig_analysis": ("RA_SCRIPTS", "rig-anything"), "humanform": ("HF_SCRIPTS", "humanform"),
        "follow_through": ("FT_SCRIPTS", "follow-through"), "wardrobe": ("WD_SCRIPTS", "wardrobe"),
        "lookdev_blender": ("LD_SCRIPTS", "lookdev")}
# the folder under the plugin its package lives in, where it is not `scripts`
SUBDIR = {"lookdev_blender": "blender"}


def scripts(package):
    var, plugin = VARS[package]
    return os.environ.get(var) or os.path.join(os.path.expanduser("~"), ".claude", "skills", plugin,
                                               SUBDIR.get(package, "scripts"))


def use(*packages):
    """Import (and reload) the named packages from their scripts folders. Returns the modules."""
    out = []
    for package in packages or tuple(VARS):
        path = scripts(package)
        if path not in sys.path:
            sys.path.insert(0, path)
        mod = importlib.import_module(package)
        if hasattr(mod, "reload_all"):
            mod.reload_all()
        out.append(mod)
    return out


def versions():
    """{plugin: version} of the checkouts in use - part of every stage's input hash, so a plugin
    update rebuilds what it could have changed."""
    out = {}
    for package, (_, plugin) in VARS.items():
        manifest = os.path.join(os.path.dirname(scripts(package)), ".claude-plugin", "plugin.json")
        try:
            with open(manifest, encoding="utf-8") as fh:
                out[plugin] = json.load(fh)["version"]
        except (OSError, ValueError, KeyError):
            out[plugin] = "?"
    return out
