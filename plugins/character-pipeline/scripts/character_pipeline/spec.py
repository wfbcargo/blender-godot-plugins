"""A character spec: one TOML file that says who a character is, with no code and no tuned numbers
that belong to a plugin.

    [character]
    id = "belle"                 # file names, the manifest's creature
    name = "Belle"               # object names: Belle_rig, Belle_body

    [body]                       # humanform's brief (sheet.new), passed through
    source = "brief"             # or "blend": an object already in the open file (`object = "Tomas"`)
    sex = "female"
    age = 28
    stature = 1.70
    build = "curvy"
    measurements = { chestcircumference = 1.02, waistcircumference = 0.72 }
    skin = [0.78, 0.58, 0.47]
    [body.parts]                 # humanform library parts
    face = "face-female-11-1-49f17892"

    [moves]                      # rig-anything's move_set
    roles = ["Idle", "Walk", "Run", "Crouch"]    # default: Idle and the gaits
    loops = ["Idle", "Walk", "Run"]              # default: every role
    style = "adult"              # locomotion.GAIT_STYLES
    stance_width = 1.15
    gaits = { Walk = 0.2, Run = 2.0 }            # role -> Froude number
    [moves.per_gait.Walk]        # anything move_set takes per role, over the style
    max_drop = 0.035

    [muscle]                     # optional: humanform's muscle definition (delta parts), weighted by
                                 # the brief's muscle and estimated body fat - applied between body and bake
    output = "geometry"          # or "normal": baked into the skin's normal map (silhouette bulk stays geometry)
    strength = 1.0               # scales every definition group
    groups = ["pectorals", "abdominals"]   # default: all (humanform.muscle.GROUPS)
    normal_size = 2048           # output = "normal" only; default by [build] quality

    [build]                      # optional: how much a build spends (default "final")
    quality = "final"            # "draft" | "preview" | "final" - see quality.py; runner.build(quality=)
                                 # overrides it

    [hair]                       # optional: humanform's hair layer (the brief's `hair`)
    preset = "bun"               # short_crop, bob, bun, ponytail, long_loose
    colour = [0.17, 0.10, 0.06]  # a screen (sRGB) colour
                                 # a ponytail swings: the strand stage hangs a follow-through
                                 # spring-bone chain on the tail and exports it as
                                 # <id>_hair.glb beside the body
    brows = true                 # optional, default false: humanform.brows' brow cards, lash cards
    lashes = true                #   and a light body hair shell, in the hair colour darkened
    body_hair = false
    [flesh]                      # optional: follow-through
    types = ["breast", "butt"]
    [[flesh.zones]]              # optional: marked on the flesh sheet when the measure is wrong
    [[outfit]]                   # optional: wardrobe presets, innermost first
    preset = "sports_top"

    [review]                     # optional: the review sheet written after export (default on)
    enabled = true
    frame_height_m = 2.1         # default: 2.1 m for an upright body, a size rung for a creature

    [export]
    dir = "assets/belle"         # under the project
    res_dir = "res://assets/belle"
    blend = "C:/Users/pauli/Code/Blender/belle_realistic.blend"

`load(path)` reads and checks it and returns a `Character`. Every field maps to a plugin
argument; `GAPS` lists what the plugins cannot take yet, so a spec that needs one says so
instead of a build script quietly holding it.
"""

from __future__ import annotations

import hashlib
import json
import os
import tomllib
from dataclasses import asdict, dataclass, field

SCHEMA = "character-pipeline/1"

# Fields a spec may carry that no plugin owns yet, and where they live until one does.
GAPS = {
    "flesh.zones": "only needed while flesh reads some masses wrong (05 5.9): marked on the flesh sheet",
    "moves.clearance_check": "a report-only limb clearance pass on chosen roles; not a move_set option",
}

BRIEF_SOURCES = ("brief", "blend")

# Fields still read, but only for specs written before the plugin that replaced them.
DEPRECATED = {
    "hair.kind": "kind = \"shell_bun\" is the pipeline's old scalp shell and sphere bun, kept only so an old spec "
                 "still builds; use preset = \"<humanform hair preset>\" and colour (improvements 05 5.2)",
}
HAIR_PRESETS = ("short_crop", "bob", "bun", "ponytail", "long_loose")   # humanform.sheet.HAIR_PRESETS
MUSCLE_GROUPS = ("deltoids", "upper_arms", "pectorals", "abdominals", "obliques", "quadriceps", "calves",
                 "forearms", "relief", "bulk")                           # humanform.muscle.GROUPS
MUSCLE_OUTPUTS = ("geometry", "normal")
QUALITIES = ("draft", "preview", "final")


class SpecError(ValueError):
    pass


@dataclass
class Body:
    source: str = "brief"
    object: str | None = None                   # source = "blend": the mesh already in the file
    brief: dict = field(default_factory=dict)   # humanform sheet.new(**brief)
    parts: dict = field(default_factory=dict)   # face / hands / feet library ids
    skin: list | None = None                    # source = "blend": the skin colour humanform would apply


@dataclass
class Moves:
    gaits: dict = field(default_factory=dict)   # role -> Froude
    roles: list = field(default_factory=list)
    loops: list = field(default_factory=list)
    export_gaits: list = field(default_factory=list)
    style: str = "adult"
    stance_width: float | None = None
    posture: dict | None = None
    per_gait: dict = field(default_factory=dict)  # role -> move_set options over the style
    may_fail: list = field(default_factory=list)  # clips exported forced and listed, never silently
    clearance_check: list = field(default_factory=list)


@dataclass
class Hair:
    kind: str = "preset"                        # "preset": humanform's hair layer; "shell_bun": deprecated
    preset: str | None = None                   # a humanform hair preset
    colour: list | None = None                  # screen (sRGB); None takes the preset's
    params: dict = field(default_factory=dict)  # shell_bun only
    brows: bool = False                         # humanform.brows layers, joined with the hair
    lashes: bool = False
    body_hair: bool = False

    FACE = ("brows", "lashes", "body_hair")

    def face(self):
        """The humanform.brows switches that are on, as hair.add keywords."""
        return {k: True for k in self.FACE if getattr(self, k)}


@dataclass
class Muscle:
    output: str = "geometry"                    # "geometry" | "normal"
    strength: float = 1.0
    groups: list = field(default_factory=lambda: list(MUSCLE_GROUPS))
    normal_size: int | None = None              # None: the quality's


@dataclass
class Build:
    quality: str = "final"


@dataclass
class Flesh:
    types: list = field(default_factory=list)
    zones: list = field(default_factory=list)
    limit_share: dict = field(default_factory=dict)   # overrides the type's own


@dataclass
class Garment:
    preset: str = ""
    name: str | None = None
    colour: list | None = None


@dataclass
class Export:
    dir: str = ""
    res_dir: str = ""
    blend: str | None = None
    note: str = ""
    # No height field: height_m.stand is always the Idle clip's standing height (stages.run_export).


@dataclass
class Review:
    enabled: bool = True
    frame_height_m: float | None = None       # None: rig-anything's review.frame_height picks it


@dataclass
class Character:
    id: str
    name: str
    body: Body
    moves: Moves
    export: Export
    hair: Hair | None = None
    flesh: Flesh | None = None
    outfit: list = field(default_factory=list)
    review: Review = field(default_factory=Review)
    muscle: Muscle | None = None
    build: Build = field(default_factory=Build)
    path: str | None = None                  # the spec file
    project: str | None = None               # the project it builds into

    # object names
    @property
    def rig(self):
        return f"{self.name}_rig"

    @property
    def mesh(self):
        return f"{self.name}_body"

    @property
    def eyes(self):
        return f"{self.name}_eyes"

    def out_dir(self):
        d = self.export.dir
        return d if os.path.isabs(d) else os.path.join(self.project or os.getcwd(), d)

    def section(self, name):
        """The part of the spec a stage reads, as plain data - what its input hash covers."""
        value = getattr(self, name) if name not in ("character",) else {"id": self.id, "name": self.name}
        if name == "hair" and value is not None and value.kind == "shell_bun":
            # the shape this section had before presets, so a shell_bun build's stored records stay valid
            return {"kind": value.kind, "params": dict(value.params)}
        if name == "hair" and value is not None:
            # a switch left off hashes as it did before the switches existed, so no existing build restarts
            out = asdict(value)
            for k in Hair.FACE:
                if not out.get(k):
                    out.pop(k, None)
            return out
        if isinstance(value, list):
            return [asdict(v) if hasattr(v, "__dataclass_fields__") else v for v in value]
        return asdict(value) if hasattr(value, "__dataclass_fields__") else value

    def digest(self, *sections):
        text = json.dumps({s: self.section(s) for s in sections}, sort_keys=True, default=str)
        return hashlib.sha1(text.encode()).hexdigest()[:16]


def _take(table, key, kind, default=None, required=False, where=""):
    if key not in table:
        if required:
            raise SpecError(f"{where}{key} is required")
        return default
    value = table[key]
    if kind is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if kind is not None and not isinstance(value, kind):
        raise SpecError(f"{where}{key} must be {getattr(kind, '__name__', kind)}, not {type(value).__name__}")
    return value


def _unknown(table, allowed, where):
    extra = sorted(set(table) - set(allowed))
    if extra:
        raise SpecError(f"{where}: unknown field(s) {', '.join(extra)}")


def parse(data, path=None):
    """A `Character` from parsed TOML, checked. Raises `SpecError` naming the field."""
    _unknown(data, ("character", "body", "moves", "hair", "flesh", "outfit", "export", "review", "muscle", "build"),
             "spec")
    c = _take(data, "character", dict, required=True)
    _unknown(c, ("id", "name"), "[character]")
    cid = _take(c, "id", str, required=True, where="character.")
    name = _take(c, "name", str, required=True, where="character.")

    b = dict(_take(data, "body", dict, required=True))
    source = b.pop("source", "brief")
    if source not in BRIEF_SOURCES:
        raise SpecError(f"body.source must be one of {BRIEF_SOURCES}, not {source!r}")
    parts = b.pop("parts", {})
    obj = b.pop("object", None)
    skin = b.get("skin") if source == "brief" else b.pop("skin", None)
    if source == "blend" and not obj:
        raise SpecError("body.object is required when body.source = \"blend\"")
    if source == "brief":
        b.setdefault("name", name)
        if b["name"] != name:
            raise SpecError(f"body.name {b['name']!r} must match character.name {name!r}")
    body = Body(source=source, object=obj, brief=b if source == "brief" else {}, parts=parts, skin=skin)

    m = _take(data, "moves", dict, required=True)
    _unknown(m, ("gaits", "roles", "loops", "export_gaits", "style", "stance_width", "posture",
                 "per_gait", "may_fail", "clearance_check"), "[moves]")
    gaits = {k: float(v) for k, v in _take(m, "gaits", dict, required=True, where="moves.").items()}
    roles = list(_take(m, "roles", list, default=["Idle", *gaits]))
    if "Idle" not in roles:
        raise SpecError("moves.roles must include Idle")
    missing = [g for g in gaits if g not in roles]
    if missing:
        raise SpecError(f"moves.gaits {missing} are not in moves.roles")
    loops = list(_take(m, "loops", list, default=list(roles)))
    per_gait = _take(m, "per_gait", dict, default={})
    stray = [r for r in per_gait if r not in roles]
    if stray:
        raise SpecError(f"moves.per_gait has roles not in moves.roles: {stray}")
    moves = Moves(gaits=gaits, roles=roles, loops=loops,
                  export_gaits=list(_take(m, "export_gaits", list, default=list(gaits))),
                  style=_take(m, "style", str, default="adult"),
                  stance_width=_take(m, "stance_width", float),
                  posture=_take(m, "posture", dict), per_gait=per_gait,
                  may_fail=list(_take(m, "may_fail", list, default=[])),
                  clearance_check=list(_take(m, "clearance_check", list, default=[])))

    hair = None
    if "hair" in data:
        h = dict(_take(data, "hair", dict))
        if "preset" in h:
            _unknown(h, ("preset", "colour") + Hair.FACE, "[hair]")
            preset = _take(h, "preset", str, where="hair.")
            if preset not in HAIR_PRESETS:
                raise SpecError(f"hair.preset {preset!r} is not one of {HAIR_PRESETS}")
            colour = _take(h, "colour", list, where="hair.")
            if colour is not None and (len(colour) != 3 or not all(isinstance(c, (int, float)) and 0 <= c <= 1
                                                                   for c in colour)):
                raise SpecError("hair.colour must be [r, g, b], screen (sRGB) channels 0..1")
            switches = {}
            for k in Hair.FACE:
                v = _take(h, k, bool, where="hair.")
                if v is not None:
                    switches[k] = v
            hair = Hair(kind="preset", preset=preset, colour=[float(c) for c in colour] if colour else None,
                        **switches)
        else:
            kind = h.pop("kind", None)
            if kind != "shell_bun":
                raise SpecError("[hair] needs preset = one of %s (or the deprecated kind = \"shell_bun\")"
                                % (HAIR_PRESETS,))
            hair = Hair(kind="shell_bun", params=h)
    flesh = None
    if "flesh" in data:
        f = data["flesh"]
        _unknown(f, ("types", "zones", "limit_share"), "[flesh]")
        flesh = Flesh(types=list(_take(f, "types", list, default=[])),
                      zones=list(_take(f, "zones", list, default=[])),
                      limit_share=dict(_take(f, "limit_share", dict, default={})))
    outfit = []
    for i, g in enumerate(_take(data, "outfit", list, default=[])):
        _unknown(g, ("preset", "name", "colour"), f"[[outfit]] {i}")
        outfit.append(Garment(preset=_take(g, "preset", str, required=True, where=f"outfit[{i}]."),
                              name=_take(g, "name", str), colour=_take(g, "colour", list)))
    if outfit and flesh is None:
        pass                                        # garments on an unfleshed body are normal

    e = _take(data, "export", dict, required=True)
    if "height" in e:
        # removed, not ignored: a crowd spec that said "mesh" would otherwise build a different height_m.stand
        # than it asked for without a word
        raise SpecError("export.height was removed: height_m.stand is always the Idle clip's standing height "
                        "(a hair bun does not raise it) - delete the line")
    _unknown(e, ("dir", "res_dir", "blend", "note"), "[export]")
    export = Export(dir=_take(e, "dir", str, required=True, where="export."),
                    res_dir=_take(e, "res_dir", str, required=True, where="export."),
                    blend=_take(e, "blend", str), note=_take(e, "note", str, default=""))

    r = _take(data, "review", dict, default={})
    _unknown(r, ("enabled", "frame_height_m"), "[review]")
    review = Review(enabled=_take(r, "enabled", bool, default=True, where="review."),
                    frame_height_m=_take(r, "frame_height_m", float, where="review."))

    muscle = None
    if "muscle" in data:
        mu = _take(data, "muscle", dict)
        _unknown(mu, ("output", "strength", "groups", "normal_size"), "[muscle]")
        output = _take(mu, "output", str, default="geometry", where="muscle.")
        if output not in MUSCLE_OUTPUTS:
            raise SpecError(f"muscle.output must be one of {MUSCLE_OUTPUTS}, not {output!r}")
        strength = _take(mu, "strength", float, default=1.0, where="muscle.")
        if not 0.0 <= strength <= 2.0:
            raise SpecError(f"muscle.strength must be 0..2, not {strength}")
        groups = list(_take(mu, "groups", list, default=list(MUSCLE_GROUPS), where="muscle."))
        bad = [g for g in groups if g not in MUSCLE_GROUPS]
        if bad or not groups:
            raise SpecError(f"muscle.groups {bad or groups} - each must be one of {MUSCLE_GROUPS}")
        size = _take(mu, "normal_size", int, where="muscle.")
        if size is not None and (size < 64 or size > 8192 or size & (size - 1)):
            raise SpecError(f"muscle.normal_size must be a power of two 64..8192, not {size}")
        if size is not None and output != "normal":
            raise SpecError("muscle.normal_size is only read with output = \"normal\"")
        if body.source != "brief":
            raise SpecError("[muscle] needs body.source = \"brief\": definition is weighted by the brief and put "
                            "on the unbaked humanform body")
        muscle = Muscle(output=output, strength=strength, groups=[g for g in MUSCLE_GROUPS if g in groups],
                        normal_size=size)

    bt = _take(data, "build", dict, default={})
    _unknown(bt, ("quality",), "[build]")
    quality = _take(bt, "quality", str, default="final", where="build.")
    if quality not in QUALITIES:
        raise SpecError(f"build.quality must be one of {QUALITIES}, not {quality!r}")

    project = None
    if path:
        # characters/<id>.toml sits in the project it builds into
        here = os.path.dirname(os.path.abspath(path))
        project = os.path.dirname(here) if os.path.basename(here) == "characters" else here
    return Character(id=cid, name=name, body=body, moves=moves, export=export, hair=hair, flesh=flesh,
                     outfit=outfit, review=review, muscle=muscle, build=Build(quality=quality),
                     path=os.path.abspath(path) if path else None, project=project)


def load(path):
    with open(path, "rb") as fh:
        try:
            data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise SpecError(f"{path}: {exc}") from exc
    return parse(data, path)
