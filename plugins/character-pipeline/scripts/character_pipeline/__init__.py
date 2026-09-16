"""character-pipeline: build a whole character from one spec file.

    import sys, importlib
    sys.path.insert(0, r"C:/Users/<you>/.claude/skills/character-pipeline/scripts")
    import character_pipeline
    importlib.reload(character_pipeline)
    character_pipeline.reload_all()
    from character_pipeline import runner
    runner.build(r"C:/.../characters/belle.toml")
"""

import importlib

SCHEMA = "character-pipeline/1"

MODULES = ("spec", "plugins", "hair", "stages", "runner")


def reload_all():
    done = []
    for name in MODULES:
        mod = importlib.import_module("." + name, __name__)
        importlib.reload(mod)
        done.append(mod.__name__)
    return done
