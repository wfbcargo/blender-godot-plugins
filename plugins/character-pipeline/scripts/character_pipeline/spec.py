"""A character spec: one TOML file that says who a character is, with no code and no tuned numbers
that belong to a plugin.

    [character]
    id = "belle"                 # file names, the manifest's creature
    name = "Belle"               # object names: Belle_rig, Belle_body

    [body]                       # humanform's brief (sheet.new), passed through
    source = "brief"             # or "blend": an object already in the open file (`object = "Tomas"`)
    species = "human"            # optional, default "human": humanform/data/species/<id>.json (improvements
                                 # 08), passed to the brief when not human; a non-human species also
                                 # turns on [moves] derive, and one whose preset has a skin.palette
                                 # may leave skin out. Or a creature nobody wrote a preset for, inline:
    [body.species]               # observables and knobs (humanform.species_design; checked against its
    heads = 5.0                  # names when it is present), plus skin = {tone, pattern = {kind, colour,
    trunk_to_leg = 0.85          # scale, amount, regions}, regions_off, subsurface_tint} and head =
    fingertips_at = "knee"       # {shape, shape_weight, features = {name = weight or a definition}}
    sex = "female"
    age = 28
    stature = 1.70
    build = "curvy"
    measurements = { chestcircumference = 1.02, waistcircumference = 0.72 }
    skin = [0.78, 0.58, 0.47]
    genitals = false             # optional: humanform's genitals part, neutral figure-study anatomy (default
                                 # off): a man keeps MPFB's shell fused to the body, a woman a relief delta
    genital_shape = { length = 0.5 }   # optional, men: MPFB's penis-{length,circ,testicles} targets, 0..1
                                 # an adult's range (0.5 neutral); genital_strength = 1.0 scales a woman's relief
    [body.parts]                 # humanform library parts
    face = "face-female-11-1-49f17892"

    [moves]                      # rig-anything's move_set
    roles = ["Idle", "Walk", "Run", "Crouch"]    # default: Idle and the gaits
    loops = ["Idle", "Walk", "Run"]              # default: every role
    style = "adult"              # locomotion.GAIT_STYLES
    derive = true                # optional: lay rig-anything's morphology.derive_style (the style the
                                 # build implies - a long trunk's roll, a stocky body's ground time) under
                                 # `style`, which wins key by key. Default: true when body.species is not
                                 # "human"; a human-proportioned body derives nothing either way
    stance_width = 1.15
    gaits = { Walk = 0.2, Run = 2.0 }            # role -> Froude number
    [moves.per_gait.Walk]        # anything move_set takes per role, over the style
    max_drop = 0.035

    [variability]                # optional: rig-anything's variability.py - what makes this body's
                                 # motion its own. Every field defaults to 0, and 0 changes nothing
    seed = 1234                  # absent: derived from character.id, deterministically
    asymmetry = 0.35             # 0..1, default 0: a FIXED left/right asymmetry, drawn once from
                                 # the seed and baked into arm swing, step length, shoulder dip and
                                 # arm lag. It is identity, not noise: the same every build
    jitter_phase = 0.0           # 0..1, default 0: the runtime half of L4 (per-cycle jitter),
    jitter_amp = 0.0             #   carried through to <id>.moves.json for the engine to read

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
    brow_shape = "arched"        # optional: natural (default, MPFB's brow as fitted), straight, arched, soft
    [flesh]                      # optional: follow-through
    types = ["breast", "butt"]
    may_miss = []                # types the stage may come back without; any other type in `types`
                                 # that finds no mass fails the flesh stage, naming why with numbers
    [[flesh.zones]]              # optional: marked on the flesh sheet when the measure is wrong
    [[outfit]]                   # optional: wardrobe presets, innermost first
    preset = "sports_top"

    [review]                     # optional: the review sheet written after export (default on)
    enabled = true
    frame_height_m = 2.1         # default: 2.1 m for an upright body, a size rung for a creature
    close = true                 # the close-up look set in review/<id>/close/ (quality.py says which views)

    [export]
    dir = "assets/belle"         # under the project
    res_dir = "res://assets/belle"
    blend = "belle_realistic.blend"   # relative: under $BLEND_DIR when set, else under the project
                                      # (absolute is still accepted) - see `resolve_blend`

A relative `[export] blend` is what makes a spec safe to copy (06 rank 2): the same file, unedited, builds
into whichever project it sits in, and saves its .blend there - `runner.build` refuses to save anywhere but
under the project or `$BLEND_DIR` unless told to (`save_outside=True`). The string is hashed as written (the
export stage's section), so a byte-for-byte copy of a spec in a scratch project hashes the same, and a copy of
its saved .blend resumes there with every stage unchanged.

`load(path)` reads and checks it and returns a `Character`. Every field maps to a plugin
argument; `GAPS` lists what the plugins cannot take yet, so a spec that needs one says so
instead of a build script quietly holding it.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
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
BROW_SHAPES = ("natural", "straight", "arched", "soft")                   # humanform.sheet.BROW_SHAPES
BEARD_STYLES = ("stubble", "short", "goatee", "moustache", "full", "long")   # humanform.brows.BEARD_STYLES
MUSCLE_GROUPS = ("deltoids", "upper_arms", "pectorals", "abdominals", "obliques", "quadriceps", "calves",
                 "forearms", "relief", "bulk")                           # humanform.muscle.GROUPS
MUSCLE_OUTPUTS = ("geometry", "normal")
QUALITIES = ("draft", "preview", "final")


class SpecError(ValueError):
    pass


def _humanform_roots():
    """Where humanform's plugin folder may be: HF_SCRIPTS's parent when set, else the humanform beside this
    plugin (the repo's plugins/ or ~/.claude/skills/)."""
    hf = os.environ.get("HF_SCRIPTS")
    here = os.path.dirname(os.path.abspath(__file__))
    return [os.path.normpath(p) for p in ([os.path.dirname(hf)] if hf else [])
            + [os.path.join(here, "..", "..", "..", "humanform")]]


def species_dir():
    """humanform's species presets folder (`<humanform>/data/species`). None when it does not exist."""
    for base in _humanform_roots():
        d = os.path.join(base, "data", "species")
        if os.path.isdir(d):
            return d
    return None


def species_design():
    """humanform's `species_design` module (standard library only, so it loads outside Blender), or None
    when this humanform has none. Loaded from its file: the spec is read before any plugin is imported."""
    import importlib.util
    for base in _humanform_roots():
        path = os.path.join(base, "scripts", "humanform", "species_design.py")
        if os.path.isfile(path):
            key = "_cp_species_design_" + hashlib.sha1(path.encode()).hexdigest()[:8]
            if key not in sys.modules:
                spec_ = importlib.util.spec_from_file_location(key, path)
                mod = importlib.util.module_from_spec(spec_)
                sys.modules[key] = mod
                try:
                    spec_.loader.exec_module(mod)
                except Exception:                                   # a broken humanform: accept any keys
                    del sys.modules[key]
                    return None
            return sys.modules[key]
    return None


# An inline `[body.species]`'s look, checked here whatever humanform is present (improvements 08, "The spec")
SPECIES_LOOK = {
    "skin": ("tone", "pattern", "regions_off", "subsurface_tint"),
    "skin.pattern": ("kind", "colour", "scale", "amount", "regions"),
    "head": ("shape", "shape_weight", "features", "eyes"),
}
SPECIES_META = ("id", "label", "anatomy", "moves", "graft")
# `anatomy` (humanform.species_design): only what the description says the creature lacks, each with its reason,
# and sizes it states - every other part is kept
SPECIES_ANATOMY = ("absent", "scale")


def check_species_table(table):
    """Refuse (SpecError) an inline `[body.species]` key humanform would not know: the top level against
    `species_design`'s observables and knobs when it can be loaded (any key otherwise), and `skin` and `head`
    against SPECIES_LOOK. Returns the table."""
    sd = species_design()
    if sd is not None:
        known = set(getattr(sd, "OBSERVABLES", {})) | set(getattr(sd, "KNOBS", {})) | set(SPECIES_LOOK)             | set(SPECIES_META)
        known.discard("skin.pattern")
        extra = sorted(set(table) - known)
        if extra:
            raise SpecError(f"[body.species]: unknown field(s) {', '.join(extra)} - it takes the observables "
                            f"{', '.join(sorted(sd.OBSERVABLES))}, the knobs {', '.join(sorted(sd.KNOBS))}, and "
                            f"skin, head, id, label")
    for part in ("skin", "head"):
        if part in table:
            v = table[part]
            if not isinstance(v, dict):
                raise SpecError(f"body.species.{part} must be a table, not {type(v).__name__}")
            _unknown(v, SPECIES_LOOK[part], f"[body.species.{part}]")
    anat = table.get("anatomy")
    if anat is not None:
        if not isinstance(anat, dict):
            raise SpecError("body.species.anatomy must be a table: absent = [{ part, reason }], scale = { part = x }")
        _unknown(anat, SPECIES_ANATOMY, "[body.species.anatomy]")
        for e in anat.get("absent", []):
            if not isinstance(e, dict) or not e.get("part") or not e.get("reason"):
                raise SpecError(f"body.species.anatomy.absent entry {e!r}: needs part and the reason the description "
                                "gives (a part is declared absent only when the description says so)")
    if sd is not None and hasattr(sd, "design_from"):
        # the whole design, as humanform will make it at the body stage (milliseconds, standard library): a
        # knob out of range, a graft whose absences the description does not state, numbers that disagree -
        # refused here, before any build, with the design's own message
        d = {k: v for k, v in table.items() if k not in ("id", "label")}
        look = {k: d.pop(k) for k in ("head", "skin", "moves", "graft") if k in d}
        anatomy = d.pop("anatomy", None)
        knobs = {n: d.pop(n) for n in list(d) if n in sd.KNOBS and n not in sd.OBSERVABLES}
        if "stature" not in d:
            raise SpecError("[body.species] needs stature (the creature's range, m: a number, [lo, hi] or "
                            "{ female = [...], male = [...] })")
        try:
            sd.design_from(d, id=table.get("id") or "custom", look=look or None, anatomy=anatomy, **knobs)
        except Exception as exc:                        # DesignError, or a malformed value
            raise SpecError(f"[body.species]: {exc}")
    pattern = (table.get("skin") or {}).get("pattern")
    if pattern is not None:
        if not isinstance(pattern, dict):
            raise SpecError("body.species.skin.pattern must be a table")
        _unknown(pattern, SPECIES_LOOK["skin.pattern"], "[body.species.skin.pattern]")
    feats = (table.get("head") or {}).get("features")
    if feats is not None:
        if not isinstance(feats, dict):
            raise SpecError("body.species.head.features must be a table of name = weight (or an inline definition)")
        for name, w in feats.items():
            if isinstance(w, bool) or not isinstance(w, (int, float, dict)):
                raise SpecError(f"body.species.head.features.{name} must be a weight or an inline definition "
                                f"table, not {w!r}")
    return table


def check_build_words(body):
    """Refuse an unknown build word in [body] build or [body.species] build before anything runs, with the list:
    both take humanform's one vocabulary (species_design.BUILD_WORDS: sheet's builds and the species words,
    which sheet.BUILD_ALIASES maps onto them). Before, a word sheet did not know failed only at the body stage."""
    sd = species_design()
    words = getattr(sd, "BUILD_WORDS", None) if sd is not None else None
    if not words:
        return
    for where, v in (("body.build", body.get("build")),
                     ("body.species.build", (body.get("species") or {}).get("build")
                      if isinstance(body.get("species"), dict) else None)):
        if isinstance(v, str) and v not in words:
            raise SpecError(f"{where} {v!r} is not a build word - one of {', '.join(words)}")


def species_ids():
    """The species ids humanform knows (its `data/species/*.json`, plus "human"), or None when it has no
    species folder - an older humanform, in which case any species is accepted and left to humanform."""
    d = species_dir()
    if d is None:
        return None
    return sorted({"human"} | {os.path.splitext(f)[0] for f in os.listdir(d) if f.endswith(".json")})


def species_palette(species):
    """The species preset's `skin.palette` (a list of screen colours), or None when it has none or there is
    no preset to read."""
    d = species_dir()
    path = os.path.join(d, species + ".json") if d else None
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            preset = json.load(fh)
    except (OSError, ValueError):
        return None
    pal = (preset.get("skin") or {}).get("palette") if isinstance(preset, dict) else None
    return pal or None


@dataclass
class Body:
    source: str = "brief"
    object: str | None = None                   # source = "blend": the mesh already in the file
    brief: dict = field(default_factory=dict)   # humanform sheet.new(**brief)
    parts: dict = field(default_factory=dict)   # face / hands / feet library ids
    skin: list | None = None                    # source = "blend": the skin colour humanform would apply
    species: str | dict = "human"               # a humanform/data/species/<id>, or an inline table (observables,
                                                # skin, head); in `brief` too when not human
    genitals: bool = False                      # humanform.genitals, added in the body stage, fused in bake
    genital_shape: dict = field(default_factory=dict)   # men: {length|circ|testicles: 0..1}, 0.5 neutral
    genital_strength: float = 1.0               # women: the relief's scale


@dataclass
class Moves:
    gaits: dict = field(default_factory=dict)   # role -> Froude
    roles: list = field(default_factory=list)
    loops: list = field(default_factory=list)
    export_gaits: list = field(default_factory=list)
    style: str = "adult"
    derive: bool | None = None                  # None: derive_style when body.species is not human
    stance_width: float | None = None
    posture: dict | None = None
    per_gait: dict = field(default_factory=dict)  # role -> move_set options over the style
    may_fail: list = field(default_factory=list)  # clips exported forced and listed, never silently
    clearance_check: list = field(default_factory=list)
    locomotion: str = "walk"                    # "walk" (move_set, Froude gaits) or "swim" (rig-anything's
                                                # swim.upright_set: a body that stands at rest and swims)


LOCOMOTION = ("walk", "swim")
# close-up views of the legs (rig-anything closeups, lookdev close-shot), which a body with no legs is not shot in
LEG_VIEWS = ("crotch", "knees", "feet")
# the clips a swimmer that stands has (rig-anything swim.upright_set): Idle floats upright, the rest swim prone
SWIM_ROLES = ("Idle", "Swim", "Sprint", "Glide", "TurnL", "TurnR")


@dataclass
class Hair:
    kind: str = "preset"                        # "preset": humanform's hair layer; "shell_bun": deprecated
    preset: str | None = None                   # a humanform hair preset
    colour: list | None = None                  # screen (sRGB); None takes the preset's
    params: dict = field(default_factory=dict)  # shell_bun only
    brows: bool = False                         # humanform.brows layers, joined with the hair
    lashes: bool = False
    body_hair: bool = False
    brow_shape: str | None = None               # humanform.brows BROW_SHAPES; None: "natural"
    beard: str | None = None                    # humanform.brows BEARD_STYLES; None: no facial hair
    beard_colour: list | None = None            # screen (sRGB); None: the hair colour a little darker
    beard_length: float | None = None           # m at the chin (a hanging beard past ~6 cm); None: the style's
    beard_volume: float | None = None           # 0..1, how far the beard stands off the skin; None: the style's
    fringe: bool = False                        # humanform.hair FRINGE across the forehead, over any preset

    FACE = ("brows", "lashes", "body_hair")

    def face(self):
        """The humanform.brows switches that are on, a brow shape other than the default and a beard, as
        hair.add keywords."""
        out = {k: True for k in self.FACE if getattr(self, k)}
        if self.brow_shape and self.brow_shape != "natural":
            out["brow_shape"] = self.brow_shape
        if self.beard:
            out["beard"] = self.beard
            if self.beard_colour is not None:
                out["beard_colour"] = list(self.beard_colour)
            for k in ("beard_length", "beard_volume"):
                if getattr(self, k) is not None:
                    out[k] = float(getattr(self, k))
        if self.fringe:
            out["fringe"] = True
        return out


@dataclass
class Muscle:
    output: str = "geometry"                    # "geometry" | "normal"
    strength: float = 1.0
    groups: list = field(default_factory=lambda: list(MUSCLE_GROUPS))
    normal_size: int | None = None              # None: the quality's


@dataclass
class Variability:
    """rig-anything's `[variability]`: what makes this character's motion its own.

    `seed` None is derived from `character.id` at bake (`rig_analysis.variability.seed_from`), so
    a spec need not carry a number to be deterministic. `asymmetry` is baked by this repo's
    branch; `jitter_phase` and `jitter_amp` are the runtime half and are only carried through to
    the manifest. Every default is 0, and 0 is the identity - a spec with no [variability] builds
    the clips it always built."""
    seed: int | None = None
    asymmetry: float = 0.0
    jitter_phase: float = 0.0
    jitter_amp: float = 0.0

    def asked(self):
        """Whether the spec asked for anything at all - a seed, or any dial off 0. False means
        this section changes nothing and is left out of every stage hash, so no existing
        character's records move."""
        return bool(self.seed is not None or self.asymmetry or self.jitter_phase or self.jitter_amp)

    def table(self):
        """The `[variability]` table as written, for `rig_analysis.variability.resolve`."""
        out = {k: v for k, v in asdict(self).items() if k != "seed" or v is not None}
        return out


@dataclass
class Build:
    quality: str = "final"


@dataclass
class Flesh:
    types: list = field(default_factory=list)
    zones: list = field(default_factory=list)
    limit_share: dict = field(default_factory=dict)   # overrides the type's own
    may_miss: list = field(default_factory=list)      # types the flesh stage may come back without
    overrides: dict = field(default_factory=dict)     # {type or region: {jiggle parameter: value}}, over the material


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
    close: bool = True                        # rig-anything's close-up look set, lit, in review/<id>/close/


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
    variability: Variability | None = None
    path: str | None = None                  # the spec file
    project: str | None = None               # the project it builds into
    warnings: list = field(default_factory=list)   # allowed, but worth a look before building (never hashed)

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

    def blend_path(self):
        """The .blend a build opens and saves: `[export] blend` resolved (`resolve_blend`), or None."""
        return resolve_blend(self.export.blend, self.project)

    def save_roots(self):
        """The folders a build may save its .blend under without `save_outside` (`save_roots`)."""
        return save_roots(self.project)

    def section(self, name):
        """The part of the spec a stage reads, as plain data - what its input hash covers."""
        value = getattr(self, name) if name not in ("character",) else {"id": self.id, "name": self.name}
        if name == "hair" and value is not None and value.kind == "shell_bun":
            # the shape this section had before presets, so a shell_bun build's stored records stay valid
            return {"kind": value.kind, "params": dict(value.params)}
        if name == "body" and value is not None:
            d = asdict(value)
            # genitals are off by default and hash as they did before the field existed, so no body built
            # without them rebuilds
            for k, default in (("genitals", False), ("genital_shape", {}), ("genital_strength", 1.0)):
                if d.get(k) == default:
                    d.pop(k, None)
            return d
        if name == "hair" and value is not None:
            # a switch left off hashes as it did before the switches existed, so no existing build restarts
            out = asdict(value)
            for k in Hair.FACE:
                if not out.get(k):
                    out.pop(k, None)
            if out.get("brow_shape") in (None, "natural"):
                out.pop("brow_shape", None)         # the default hashes as before the field existed
            for k in ("beard", "beard_colour", "beard_length", "beard_volume"):   # unset hashes as before
                if out.get(k) is None:
                    out.pop(k, None)
            if not out.get("fringe"):
                out.pop("fringe", None)
            return out
        if name == "body":
            # a human body hashes as it did before species existed
            out = asdict(value)
            if out.get("species") == "human":
                out.pop("species")
            return out
        if name == "moves":
            # [variability] rides the moves section rather than having one of its own, and only
            # when the spec asked for something: a section that is always there would change the
            # digest of every character that has never heard of it. The id rides with it because
            # that is what an unstated seed is derived from, so two specs that differ only in
            # their id do not share a moves hash once one of them is asymmetric.
            out = asdict(value)
            # derive, unset, hashes as before it existed; what the stage will do rides along only when
            # it derives, so a human spec's moves hash is unchanged and a dwarf's covers the switch
            if out.get("derive") is None:
                out.pop("derive", None)
            if out.get("locomotion") == "walk":
                out.pop("locomotion", None)         # a walker hashes as before locomotion existed
            if self.derive_moves:
                out["derive_moves"] = True
            if self.variability is not None and self.variability.asked():
                out["variability"] = dict(asdict(self.variability), identity=self.id)
            return out
        if isinstance(value, list):
            return [asdict(v) if hasattr(v, "__dataclass_fields__") else v for v in value]
        return asdict(value) if hasattr(value, "__dataclass_fields__") else value

    @property
    def grafted(self):
        """The limb pairs this body's species replaces ([body.species] graft: {"legs": {...}}), {} for any other."""
        sp = self.body.species
        return dict(sp.get("graft") or {}) if isinstance(sp, dict) else {}

    def views_without(self, views):
        """`views` (close-up view names) less those that look at parts this body plan does not have: a body whose
        legs a graft replaced has no crotch, knees or feet to shoot."""
        if "legs" not in self.grafted:
            return list(views)
        return [v for v in views if v not in LEG_VIEWS and not v.startswith("foot")]

    @property
    def derive_moves(self):
        """Whether the moves stage lays rig-anything's derived style under the spec's: `[moves] derive`,
        else on for any species but human."""
        return self.moves.derive if self.moves.derive is not None else self.body.species != "human"

    def digest(self, *sections):
        text = json.dumps({s: self.section(s) for s in sections}, sort_keys=True, default=str)
        return hashlib.sha1(text.encode()).hexdigest()[:16]


PROJECT_CONFIG = os.path.join("characters", "pipeline.toml")


def project_config(project):
    """The project's own pipeline settings, `<project>/characters/pipeline.toml`, as a dict ({} when absent):

        [blend]
        dir = "C:/Users/me/Blends"     # where relative `[export] blend`s live; relative is under the project
        inside_godot = false           # true: saving a .blend inside a Godot project is intended

    It is what a build script's own `os.environ.setdefault("BLEND_DIR", ...)` used to hold, so `run.sh`, a
    project's build script and a scratch copy all resolve a spec's blend to the same file. $BLEND_DIR still
    wins over it. Nothing in it is hashed: it says where a file lives, not what is built."""
    if not project:
        return {}
    path = os.path.join(project, PROJECT_CONFIG)
    if not os.path.isfile(path):
        return {}
    with open(path, "rb") as fh:
        try:
            data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise SpecError(f"{path}: {exc}") from None
    blend = data.get("blend", {})
    if not isinstance(blend, dict) or set(blend) - {"dir", "inside_godot"}:
        raise SpecError(f"{path}: [blend] takes dir and inside_godot only (got {sorted(blend)})")
    return data


def blend_dir(override=None, project=None):
    """$BLEND_DIR (or `override`, when given), else the project's `[blend] dir` (`project_config`), as an
    absolute path, or None when none is set."""
    d = override or os.environ.get("BLEND_DIR")
    if not d and project:
        d = project_config(project).get("blend", {}).get("dir")
        if d and not os.path.isabs(os.path.expanduser(d)):
            d = os.path.join(project, d)
    return os.path.normpath(os.path.abspath(os.path.expanduser(d))) if d else None


def resolve_blend(blend, project, blend_dir_override=None):
    """Where `[export] blend` points. Absolute: as written. Relative: under $BLEND_DIR when it is set (or
    `blend_dir_override`, for a tool resolving another project's specs), else under the project's `[blend] dir`
    (`project_config`), else under `project` (the folder holding `characters/`), else $PROJECT, else the working
    directory. None when the spec names no blend."""
    if not blend:
        return None
    blend = os.path.expanduser(blend)
    if os.path.isabs(blend):
        return os.path.normpath(blend)
    base = blend_dir(blend_dir_override, project) or project or os.environ.get("PROJECT") or os.getcwd()
    return os.path.normpath(os.path.join(os.path.abspath(base), blend))


def save_roots(project):
    """The folders a build saves under without being told otherwise: the project and $BLEND_DIR or the project's
    `[blend] dir` (if set)."""
    roots = [os.path.normpath(os.path.abspath(project))] if project else []
    d = blend_dir(project=project)
    if d and d not in roots:
        roots.append(d)
    return roots


def godot_project_of(path):
    """The Godot project folder a file would sit in (the nearest folder at or above it holding `project.godot`)
    when Godot would import it, else None. A `.gdignore` in any folder between hides the file from Godot, so a
    path under one is None too. A .blend Godot sees is imported with its Blender importer: with no Blender path
    in the editor settings a headless `--import` fails on it, and the glbs beside it are not imported either."""
    d = os.path.dirname(os.path.normpath(os.path.abspath(path)))
    while True:
        if os.path.isfile(os.path.join(d, ".gdignore")):
            return None
        if os.path.isfile(os.path.join(d, "project.godot")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return None
        d = up


def inside(path, roots):
    """Whether `path` is at or under one of `roots` (case-insensitive where the file system is)."""
    p = os.path.normcase(os.path.normpath(os.path.abspath(path)))
    for r in roots:
        r = os.path.normcase(os.path.normpath(os.path.abspath(r)))
        try:
            if os.path.commonpath([p, r]) == r:
                return True
        except ValueError:                      # different drives
            continue
    return False


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


# rig-anything's upper-body parameters whose defaults are derived - from speed, and each from a published
# number cited in `upper.defaults` (0.40.0). A spec that pins one keeps an older or hand-set value while every
# other body moves on: Belle's per-gait `head_hold = 0.85` held her head at 16% of the thorax's turn after the
# default became 64% walking, and only the motion demo's gate caught it, after a build. Pinning one is allowed -
# a character may be meant to move differently - so it is a warning, printed before anything is built.
SOURCED_UPPER = ("pelvis_list", "side_bend", "lean_bob", "lean_lag", "head_hold", "gaze_m")


def _sourced_pins(per_gait):
    """Warnings for every SOURCED_UPPER parameter a `[moves.per_gait.<role>] upper` table pins."""
    out = []
    for role, opts in per_gait.items():
        upper = opts.get("upper") if isinstance(opts, dict) else None
        if not isinstance(upper, dict):
            continue
        for k in SOURCED_UPPER:
            if k in upper:
                out.append(f"moves.per_gait.{role}.upper pins {k} = {upper[k]!r}; rig-anything derives it from "
                           f"speed and a published source (upper.defaults) - drop it unless this character is "
                           f"meant to move differently, and say why beside it")
    return out


# the jiggle parameters `[flesh] overrides` may set (follow-through's jiggle_block / set_params)
FLESH_OVERRIDE_KEYS = ("frequency_hz", "damping_ratio", "squash", "gravity_scale", "aim", "translate", "response",
                       "frequency_down_ratio", "frequency_ap_ratio", "max_offset")


def _flesh_types():
    """The flesh type names follow-through's registry knows (built-ins and taught), or None when follow-through
    is not where the build would take it from. Its registry module is plain Python and loaded by file, so a spec
    is checked without Blender."""
    import importlib.util
    from . import plugins
    path = os.path.join(plugins.scripts("follow_through"), "follow_through", "registry.py")
    if not os.path.isfile(path):
        return None
    try:
        mod_spec = importlib.util.spec_from_file_location("_ft_registry_for_spec", path)
        reg = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(reg)
        return sorted(k for k, v in reg.load()["types"].items() if "flesh" in (v.get("classes") or []))
    except Exception:                       # a registry that cannot be read is the flesh stage's to report
        return None


def _check_flesh_types(flesh):
    """`[flesh] types`: each a flesh type follow-through's registry has. Refused here, before a body is built:
    a smoke spec's `moobs` (a NAME of the breast type, and plural) was accepted and failed the flesh stage after
    the body and bake had run."""
    known = _flesh_types()
    if known is None:
        return
    bad = [t for t in flesh.types if t not in known]
    if bad:
        raise SpecError(f"[flesh] types {bad}: not flesh types follow-through's registry has (one of {known}); "
                        "a name like 'moob' or 'gut' is recognised on a mesh, but a spec names the type")


def _check_overrides(flesh):
    """`[flesh] overrides`: each key a type in `types` (or one of its sides, `breast.L`), each value a table of
    numeric jiggle parameters from FLESH_OVERRIDE_KEYS. A key nothing will find is refused, not ignored: an
    override on a type the spec never asks for would change nothing and say nothing."""
    for name, params in flesh.overrides.items():
        base = name[:-2] if name.endswith((".L", ".R")) else name
        if base not in flesh.types:
            raise SpecError(f"[flesh] overrides names {name!r}, which types does not ask for ({flesh.types})")
        if not isinstance(params, dict) or not params:   # a number or a list of pairs is refused, not coerced
            raise SpecError(f"[flesh] overrides.{name} must be a table of jiggle parameters, e.g. "
                            "{ frequency_hz = 4.5, damping_ratio = 0.6 }")
        bad = sorted(k for k in params if k not in FLESH_OVERRIDE_KEYS)
        if bad:
            raise SpecError(f"[flesh] overrides.{name}: {bad} are not jiggle parameters (one of {FLESH_OVERRIDE_KEYS}; "
                            "the swing limit is `limit_share`)")
        for k, v in params.items():
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
                raise SpecError(f"[flesh] overrides.{name}.{k} = {v!r}: a finite number, 0 or more")
            if k.startswith("frequency") and v <= 0:
                raise SpecError(f"[flesh] overrides.{name}.{k} = {v!r}: a frequency is more than 0")


def parse(data, path=None):
    """A `Character` from parsed TOML, checked. Raises `SpecError` naming the field."""
    _unknown(data, ("character", "body", "moves", "hair", "flesh", "outfit", "export", "review", "muscle",
                    "build", "variability"), "spec")
    c = _take(data, "character", dict, required=True)
    _unknown(c, ("id", "name"), "[character]")
    cid = _take(c, "id", str, required=True, where="character.")
    name = _take(c, "name", str, required=True, where="character.")

    b = dict(_take(data, "body", dict, required=True))
    check_build_words(b)
    source = b.pop("source", "brief")
    species = b.pop("species", "human")
    if isinstance(species, dict):
        # a creature nobody wrote a preset for: observables (and knobs), solved by humanform's species_design
        species = check_species_table(dict(species))
    elif not isinstance(species, str) or not species:
        raise SpecError(f"body.species must be a species id or an inline table, not {species!r}")
    known = species_ids()
    if isinstance(species, str) and known is not None and species not in known:
        raise SpecError(f"body.species {species!r} is not a humanform species - known: {', '.join(known)} "
                        f"(presets in {species_dir()})")
    if source not in BRIEF_SOURCES:
        raise SpecError(f"body.source must be one of {BRIEF_SOURCES}, not {source!r}")
    parts = b.pop("parts", {})
    obj = b.pop("object", None)
    skin = b.get("skin") if source == "brief" else b.pop("skin", None)
    if source == "blend" and not obj:
        raise SpecError("body.object is required when body.source = \"blend\"")
    if source == "brief" and b.get("skin") is None and isinstance(species, dict)             and (species.get("skin") or {}).get("tone") is not None:
        pass        # the inline species' own skin tone
    elif source == "brief" and b.get("skin") is None and isinstance(species, str) and species != "human"             and species_palette(species):
        pass        # the species preset's own skin palette (its `skin.palette`): humanform draws the tone from it
    elif source == "brief" and b.get("skin") is None:
        # without one humanform never applies its skin look and the body ships in MPFB's untextured material:
        # the first smoke bodies came out chalk white, 5-9% of the figure past white in Godot's review
        raise SpecError("body.skin is required: a screen (sRGB) colour, e.g. [0.87, 0.72, 0.60] light, "
                        "[0.62, 0.45, 0.36] medium, [0.30, 0.19, 0.13] deep - without it the body keeps MPFB's "
                        "untextured white material")
    if source == "brief":
        b.setdefault("name", name)
        if b["name"] != name:
            raise SpecError(f"body.name {b['name']!r} must match character.name {name!r}")
    if source == "brief" and species != "human":
        # humanform's brief carries it; a human brief is left without the key, so it and its hashes are
        # exactly what they were before species existed
        b["species"] = species
    genitals = _take(b, "genitals", bool, False, where="body.")
    genital_shape = _take(b, "genital_shape", dict, {}, where="body.")
    genital_strength = _take(b, "genital_strength", float, 1.0, where="body.")
    for k in ("genitals", "genital_shape", "genital_strength"):
        b.pop(k, None)
    if genitals and source != "brief":
        raise SpecError("body.genitals needs body.source = \"brief\": the part is MPFB's, put on the unbaked "
                        "humanform body")
    if genital_shape and b.get("sex") != "male":
        raise SpecError("body.genital_shape is MPFB's male targets; a woman's relief takes genital_strength")
    for k, v in genital_shape.items():
        if k not in ("length", "circ", "testicles") or not isinstance(v, (int, float)) or not 0 <= v <= 1:
            raise SpecError(f"body.genital_shape.{k} = {v!r}: length, circ or testicles, 0..1 (0.5 neutral)")
    if (genital_shape or genital_strength != 1.0) and not genitals:
        raise SpecError("body.genital_shape / genital_strength need body.genitals = true")
    body = Body(source=source, object=obj, brief=b if source == "brief" else {}, parts=parts, skin=skin,
                species=species, genitals=genitals,
                genital_shape={k: float(v) for k, v in genital_shape.items()},
                genital_strength=float(genital_strength))

    m = _take(data, "moves", dict, required=True)
    _unknown(m, ("gaits", "roles", "loops", "export_gaits", "style", "derive", "stance_width", "posture",
                 "per_gait", "may_fail", "clearance_check", "locomotion"), "[moves]")
    locomotion = _take(m, "locomotion", str, default="walk")
    if locomotion not in LOCOMOTION:
        raise SpecError(f"moves.locomotion {locomotion!r}: one of {', '.join(LOCOMOTION)}")
    gaits = {k: float(v) for k, v in _take(m, "gaits", dict, required=locomotion == "walk",
                                           default={}, where="moves.").items()}
    if locomotion == "swim":
        # a swimmer's clips are its swim set's, never a walk's: the Froude gaits and their checks do not apply
        if gaits:
            raise SpecError("moves.gaits are Froude numbers for a walker; a swimmer (locomotion = \"swim\") "
                            "takes none - its speeds come from its length (rig-anything swim)")
        bad = [r for r in (m.get("roles") or []) if r not in SWIM_ROLES]
        if bad:
            raise SpecError(f"moves.roles {bad}: a swimmer's roles are {', '.join(SWIM_ROLES)} (Idle floats "
                            "upright; the others swim prone)")
        for k in ("export_gaits", "clearance_check", "stance_width", "posture", "per_gait"):
            if m.get(k):
                raise SpecError(f"moves.{k} is a walker's; a swimmer (locomotion = \"swim\") has none")
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
                  derive=_take(m, "derive", bool),
                  stance_width=_take(m, "stance_width", float),
                  posture=_take(m, "posture", dict), per_gait=per_gait,
                  may_fail=list(_take(m, "may_fail", list, default=[])),
                  clearance_check=list(_take(m, "clearance_check", list, default=[])),
                  locomotion=locomotion)

    hair = None
    if "hair" in data:
        h = dict(_take(data, "hair", dict))
        if "preset" in h:
            _unknown(h, ("preset", "colour", "brow_shape", "beard", "beard_colour", "beard_length", "beard_volume",
                         "fringe") + Hair.FACE, "[hair]")
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
            brow_shape = _take(h, "brow_shape", str, where="hair.")
            if brow_shape is not None and brow_shape not in BROW_SHAPES:
                raise SpecError(f"hair.brow_shape {brow_shape!r} is not one of {BROW_SHAPES}")
            beard = _take(h, "beard", str, where="hair.")
            if beard is not None and beard not in BEARD_STYLES:
                raise SpecError(f"hair.beard {beard!r} is not one of {BEARD_STYLES}")
            beard_colour = _take(h, "beard_colour", list, where="hair.")
            if beard_colour is not None and (len(beard_colour) != 3 or not all(
                    isinstance(c, (int, float)) and 0 <= c <= 1 for c in beard_colour)):
                raise SpecError("hair.beard_colour must be [r, g, b], screen (sRGB) channels 0..1")
            if beard_colour is not None and beard is None:
                raise SpecError("hair.beard_colour needs hair.beard")
            shape = {}
            for k, lo, hi in (("beard_length", 0.001, 0.6), ("beard_volume", 0.0, 1.0)):
                v = _take(h, k, (int, float), where="hair.")
                if v is None:
                    continue
                if beard is None:
                    raise SpecError(f"hair.{k} needs hair.beard")
                if not lo <= float(v) <= hi:
                    raise SpecError(f"hair.{k} must be {lo}..{hi}, got {v}")
                shape[k] = float(v)
            hair = Hair(kind="preset", preset=preset, colour=[float(c) for c in colour] if colour else None,
                        brow_shape=brow_shape, beard=beard, fringe=bool(_take(h, "fringe", bool, where="hair.")),
                        beard_colour=[float(c) for c in beard_colour] if beard_colour else None, **shape,
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
        _unknown(f, ("types", "zones", "limit_share", "may_miss", "overrides"), "[flesh]")
        flesh = Flesh(types=list(_take(f, "types", list, default=[])),
                      zones=list(_take(f, "zones", list, default=[])),
                      limit_share=dict(_take(f, "limit_share", dict, default={})),
                      may_miss=list(_take(f, "may_miss", list, default=[])),
                      overrides=dict(_take(f, "overrides", dict, default={})))
        stray = [t for t in flesh.may_miss if t not in flesh.types]
        if stray:
            raise SpecError(f"[flesh] may_miss names {stray}, which types does not ask for ({flesh.types})")
        _check_flesh_types(flesh)
        _check_overrides(flesh)
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
    _unknown(r, ("enabled", "frame_height_m", "close"), "[review]")
    review = Review(enabled=_take(r, "enabled", bool, default=True, where="review."),
                    frame_height_m=_take(r, "frame_height_m", float, where="review."),
                    close=_take(r, "close", bool, default=True, where="review."))

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

    variability = None
    if "variability" in data:
        v = _take(data, "variability", dict)
        _unknown(v, ("seed", "asymmetry", "jitter_phase", "jitter_amp"), "[variability]")
        if isinstance(v.get("seed"), bool):
            raise SpecError("variability.seed must be a whole number, not a boolean")
        seed = _take(v, "seed", int, where="variability.")
        if seed is not None and seed < 0:
            raise SpecError(f"variability.seed must be 0 or more, not {seed}")
        dials = {}
        for k in ("asymmetry", "jitter_phase", "jitter_amp"):
            d = _take(v, k, float, default=0.0, where="variability.")
            if not 0.0 <= d <= 1.0:
                raise SpecError(f"variability.{k} = {d} must be 0..1")
            dials[k] = d
        variability = Variability(seed=seed, **dials)

    project = None
    if path:
        # characters/<id>.toml sits in the project it builds into
        here = os.path.dirname(os.path.abspath(path))
        project = os.path.dirname(here) if os.path.basename(here) == "characters" else here
    return Character(id=cid, name=name, body=body, moves=moves, export=export, hair=hair, flesh=flesh,
                     outfit=outfit, review=review, muscle=muscle, build=Build(quality=quality),
                     variability=variability,
                     path=os.path.abspath(path) if path else None, project=project,
                     warnings=_sourced_pins(per_gait))


def load(path):
    with open(path, "rb") as fh:
        try:
            data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise SpecError(f"{path}: {exc}") from exc
    return parse(data, path)
