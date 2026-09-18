"""What a stage reads besides the spec, for its input hash: the data files and code its result depends on.

A stage's hash always covered the spec sections it reads, the hashes of the stages it needs and the plugin
versions. That missed everything a plugin reads that a version bump does not follow (06 rank 3):

- a garment preset edited in `wardrobe/presets/garments.json` left `garments` "unchanged", and the old cut
  shipped until someone ran `force=1` (belle-top, about 10 min);
- the ear cut in humanform's `hair.py` left Belle's old cap "unchanged";
- flesh read follow-through's type registry (limit shares, zones, materials), and the user registry
  (`~/.claude/follow-through/types.json`) has no version at all; and a fix to how `flesh.py` weights the
  jiggle bones (0.6.1's `limit_influences`) left every saved study figure's flesh "unchanged".

So each stage names what it reads here, as `{label: digest}`, and the runner puts that into its hash and
into the stage's record in the .blend (so a rerun can say which input moved - `changed()`):

    stage     reads (label: what)
    bake      code:humanform.skin, code:humanform.look       the skin material, marks and bake
              code:lookdev_blender.bake                       the map bake (and .detail for a muscle normal map)
    hair      preset:<name>                                   humanform's resolved hair preset (hair_presets.json)
              code:humanform.hair, code:humanform.brows       the hair geometry (cap, ear cut, parts, cards)
              data:humanform.face_regions                     brow and lash placement (only with a face switch on)
              code:lookdev_blender.hair, data:lookdev.hair    the hair material and its preset (materials.json)
              code:character_pipeline.hair                    instead of all that for a deprecated shell_bun
    flesh     data:follow_through.registry                    the merged type registry: built-in and user
              code:follow_through.flesh                       finding the masses and weighting the jiggle bones
    garments  preset:<name>                                   each worn wardrobe preset's contents (garments.json)
    review    code:rig_analysis.closeups                      the close-up look set: views, aim, lights, checks
                                                              (only with `[review] close` on)

Data is hashed as parsed JSON (so a CRLF checkout and an LF one agree, and key order does not matter); code
as its source with line endings normalised. Presets are hashed one by one, so editing a preset the spec
does not wear, or a hair preset it does not use, reruns nothing. The version of each plugin a stage builds
with was in the hash already (`plugins.stage_versions`).

Stages not listed read only the spec and the stages before them (body's library and fit are humanform's
version; moves, strand and export read rig-anything's and follow-through's code, covered by their versions, as
is the review sheet's). A stage that starts reading a new file must add it here, and `tests/fixtures/pipeline_hashes.py`
must flip it.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os

from . import plugins


def _sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:16]


def data(value) -> str:
    """A digest of plain data: canonical JSON, so formatting, key order and line endings do not count."""
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))


def code(module: str) -> str:
    """A digest of a module's source as it is imported now (line endings normalised)."""
    mod = importlib.import_module(module)
    path = getattr(mod, "__file__", None)
    if not path or not os.path.isfile(path):
        return "absent"
    with open(path, "rb") as fh:
        return _sha(fh.read().replace(b"\r\n", b"\n"))


def json_file(path: str) -> str:
    if not os.path.isfile(path):
        return "absent"
    with open(path, encoding="utf-8") as fh:
        return data(json.load(fh))


def _lookdev():
    return plugins.available("lookdev_blender")


def _bake(ch):
    out = {"code:humanform.skin": code("humanform.skin"), "code:humanform.look": code("humanform.look")}
    if _lookdev():
        out["code:lookdev_blender.bake"] = code("lookdev_blender.bake")
        if ch.muscle is not None and ch.muscle.output == "normal":
            out["code:lookdev_blender.detail"] = code("lookdev_blender.detail")
    return out


def _hair(ch):
    if ch.hair.kind == "shell_bun":
        return {"code:character_pipeline.hair": code("character_pipeline.hair")}
    from humanform import hair as hf_hair
    import humanform
    out = {f"preset:{ch.hair.preset}": data(hf_hair.params(ch.hair.preset)),
           "code:humanform.hair": code("humanform.hair"), "code:humanform.brows": code("humanform.brows")}
    if ch.hair.face():
        out["data:humanform.face_regions"] = json_file(os.path.join(humanform.DATA, "face_regions.json"))
    if _lookdev():
        from lookdev_blender import hair as ld_hair
        out["code:lookdev_blender.hair"] = code("lookdev_blender.hair")
        out["data:lookdev.hair"] = data(ld_hair.presets().get("hair"))
    return out


def _flesh(ch):
    from follow_through import registry
    return {"data:follow_through.registry": data(registry.load()), "code:follow_through.flesh": code("follow_through.flesh")}


def _garments(ch):
    from wardrobe import presets
    return {f"preset:{g.preset}": data(presets.get(g.preset)) for g in ch.outfit}


def _review(ch):
    if not ch.review.close:
        return {}
    return {"code:rig_analysis.closeups": code("rig_analysis.closeups")}


READS = {"bake": _bake, "hair": _hair, "flesh": _flesh, "garments": _garments, "review": _review}


def stage_inputs(ch, stage, drop=()):
    """{label: digest} of what `stage` reads besides the spec, as the plugins on sys.path have it now.
    `drop` leaves labels out - only for the hash test's control, never for a build."""
    fn = READS.get(stage)
    out = fn(ch) if fn is not None else {}
    for label in drop:
        out.pop(label, None)
    return out


def changed(before, now):
    """The labels whose digest differs between a stored record's inputs and now (added, removed or edited)."""
    before = before or {}
    return sorted(k for k in set(before) | set(now) if before.get(k) != now.get(k))
