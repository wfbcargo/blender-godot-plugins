"""The type registry: what things are, and what they were taught to be.

Recognition has three levels. The **family** is the dimension of what moves (strand,
shell, volume). The **class** is how it is held, and picks the runtime. The **type**
is what it is - jello, clay, a breast, a bloater's belly - and picks the material.

Classes are fixed by code, because each needs a runtime. Types are data: a type is a
JSON entry naming its family, the classes it can take, its material, the words that
name it and, for flesh, the zone of the body it lives in. So a new kind of thing does
not need code. It needs an entry, and examples:

    registry.teach("Blob.003", "slime")                  # this object is slime
    registry.teach("Figure", "double_chin", group="chin_fat", material="soft_fat")
                                                         # a new flesh type, from a painted group
    registry.define("tapioca", family="volume", classes=["loose_volume"],
                    material="custard", names=["tapioca", "boba"])
    print(registry.recognise("Blob.004"))                # names, taught examples, defaults

Built-in types and materials ship in `types/builtin.json`. Everything taught goes to
the user registry, `~/.claude/follow-through/types.json` (override with the env var
FOLLOW_THROUGH_TYPES), which is read on top of the built-ins and survives plugin
updates. An example stores the measured features of one object with the type it was
given; `recognise` compares a new object's features with every example and reports
the nearest, so the second slime is recognised because the first was taught.

Examples are evidence, like names: they raise confidence and propose a type, and
geometry still decides the class. Renders decide when they disagree.
"""

from __future__ import annotations

import datetime
import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BUILTIN = os.path.normpath(os.path.join(HERE, "..", "..", "types", "builtin.json"))
SCHEMA = "follow-through-types/1"

FAMILIES = ("strand", "shell", "volume")
VOLUME_CLASSES = ("loose_volume", "mounted_volume", "flesh")

# how far apart two objects' features may be and still count as the same kind of thing
NEAR = 0.35


def user_path():
    return os.environ.get("FOLLOW_THROUGH_TYPES") or os.path.join(
        os.path.expanduser("~"), ".claude", "follow-through", "types.json")


def _read(path):
    if not os.path.exists(path):
        return {"schema": SCHEMA, "materials": {}, "types": {}, "examples": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for k in ("materials", "types"):
        data.setdefault(k, {})
    data.setdefault("examples", [])
    return data


def load():
    """Built-ins with the user registry on top. Each type and material says where it came from."""
    base = _read(BUILTIN)
    user = _read(user_path())
    out = {"schema": SCHEMA, "materials": {}, "types": {}, "examples": []}
    for src, data in (("builtin", base), ("user", user)):
        for k, v in data["materials"].items():
            out["materials"][k] = dict(v, origin=src)
        for k, v in data["types"].items():
            merged = dict(out["types"].get(k, {}))
            merged.update(v)
            merged["origin"] = src if k not in out["types"] else "builtin+user"
            out["types"][k] = merged
        out["examples"].extend(dict(e, origin=src) for e in data["examples"])
    return out


def _save_user(data):
    path = user_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
    return path


def material(name):
    reg = load()
    if name not in reg["materials"]:
        raise ValueError(f"unknown material {name!r}; one of {sorted(reg['materials'])}")
    return reg["materials"][name]


# ------------------------------------------------------------------ definitions

def define(name, family, classes, material=None, names=(), description="", zone=None,
           paired=False, fabric=None, variant_of=None, when=None, anchor=None, limit_share=None,
           limit_note=None, lean=None, limit_max_share=None):
    """Add or replace a type in the user registry.

    `anchor` names the bone role a flesh type's jiggle bone hangs from - a rig-anything role such as
    `pelvis`, `chest` or `head` - instead of the core bone nearest the region. `limit_share` sets a
    flesh type's swing limit, `max_offset_m = limit_share x peak_m`, in place of the material's;
    `limit_note` says where the number came from; `limit_max_share` is the most
    `flesh.suggest_limits` may raise it to (a breast swung in further than two thirds of its
    stand-out passes into the chest). `lean="profile"` reads a flesh type's excess from the side,
    across chains, instead of from rings round one (`flesh.measured`): for a mass where
    one chain ends and the next begins, as a buttock sits between the spine and the thighs."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError("type names are lower_snake_case")
    if family not in FAMILIES:
        raise ValueError(f"family must be one of {FAMILIES}")
    reg = load()
    if material is not None and material not in reg["materials"]:
        raise ValueError(f"unknown material {material!r}; define_material first, or use one of "
                         f"{sorted(reg['materials'])}")
    if family == "volume":
        bad = [c for c in classes if c not in VOLUME_CLASSES]
        if bad:
            raise ValueError(f"volume classes are {VOLUME_CLASSES}, not {bad}")
    if "flesh" in classes and zone is None:
        raise ValueError("a flesh type needs a zone - teach it from a painted group instead")
    entry = {"family": family, "classes": list(classes), "names": [n.lower() for n in names],
             "description": description, "defined": _now()}
    for k, v in (("material", material), ("zone", zone), ("fabric", fabric),
                 ("variant_of", variant_of), ("when", when), ("anchor", anchor),
                 ("limit_share", limit_share), ("limit_note", limit_note), ("lean", lean),
                 ("limit_max_share", limit_max_share)):
        if v is not None:
            entry[k] = v
    if paired:
        entry["paired"] = True
    user = _read(user_path())
    user["types"][name] = entry
    return {"type": name, "saved_to": _save_user(user), "entry": entry}


def define_material(name, route, density_kg_m3, source, shape_matching=None, jiggle=None,
                    sticky=False):
    """Add or replace a material in the user registry. `source` says where the numbers came from."""
    if route not in ("shape_matching", "jiggle_bones", "none"):
        raise ValueError("route is shape_matching, jiggle_bones or none")
    entry = {"route": route, "density_kg_m3": density_kg_m3, "sticky": bool(sticky), "source": source}
    if shape_matching:
        entry["shape_matching"] = shape_matching
    if jiggle:
        entry["jiggle"] = jiggle
    user = _read(user_path())
    user["materials"][name] = entry
    return {"material": name, "saved_to": _save_user(user)}


def forget(type_name=None, example_object=None):
    """Remove a user-defined type (and its examples), or the examples taken from one object."""
    user = _read(user_path())
    removed = 0
    if type_name is not None:
        if user["types"].pop(type_name, None) is not None:
            removed += 1
        before = len(user["examples"])
        user["examples"] = [e for e in user["examples"] if e["type"] != type_name]
        removed += before - len(user["examples"])
    if example_object is not None:
        before = len(user["examples"])
        user["examples"] = [e for e in user["examples"] if e.get("object") != example_object]
        removed += before - len(user["examples"])
    _save_user(user)
    return {"removed": removed}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ features

def name_tokens(name):
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return [t for t in re.split(r"[^a-z]+", spaced.lower()) if t]


def object_features(m):
    """Scale-free shape features of one mesh, from measure.analyze. Each is roughly 0-1."""
    ext = m["extents_m"]
    longest = max(ext[0], 1e-9)
    contacts = m["contacts"]["by_object"].values()
    return {
        "closed": 1.0 if m["closed"] else 0.0,
        "loops": min(len(m["boundary_loops"]), 3) / 3.0,
        "thickness": min((m["thickness_over_size"] or 0.0) * 2.0, 1.0),
        "compactness": min(m["compactness"] / 0.094, 1.2),
        "mid_over_long": ext[1] / longest,
        "short_over_long": ext[2] / longest,
        "verticality": m["verticality"],
        "size": max(0.0, min(1.0, (math.log10(longest) + 2.0) / 3.0)),     # 1 cm -> 0, 10 m -> 1
        "skinned": 1.0 if m["skin"].get("armature") else 0.0,
        "rests": 1.0 if any(c["mean_height_fraction"] < 0.25 for c in contacts) else 0.0,
        "held_above": 1.0 if any(c["mean_height_fraction"] >= 0.75 for c in contacts) else 0.0,
    }


WEIGHTS = {"closed": 2.0, "loops": 1.5, "thickness": 1.0, "compactness": 1.0, "mid_over_long": 1.0,
           "short_over_long": 1.0, "verticality": 0.5, "size": 1.5, "skinned": 1.0, "rests": 0.5,
           "held_above": 0.5,
           # flesh regions
           "height": 1.5, "facing_cos": 1.0, "facing_sin": 0.5, "lateral": 1.0, "peak": 1.0,
           "volume_fraction": 1.0, "chain_spine": 1.0, "chain_arm": 1.0, "chain_leg": 1.0}


def distance(a, b):
    keys = [k for k in a if k in b]
    if not keys:
        return math.inf
    total = sum(WEIGHTS.get(k, 1.0) * (a[k] - b[k]) ** 2 for k in keys)
    norm = sum(WEIGHTS.get(k, 1.0) for k in keys)
    return math.sqrt(total / norm)


# ------------------------------------------------------------------ teaching and recognising

def teach(obj_name, type_name, group=None, cls=None, material=None, note="", measures=None):
    """Record that `obj_name` (or its painted vertex group `group`, for flesh) is `type_name`.

    An unknown type is created from the example: its family and class come from
    classify, its material from `material` (required for a new type), and for a
    flesh region its zone is the region's measured place on the body, padded."""
    from . import classify, flesh, measure
    reg = load()
    example = {"type": type_name, "object": obj_name, "note": note, "taught": _now()}
    new_type = type_name not in reg["types"]
    if group is not None:
        region = flesh.region_from_group(obj_name, group)
        if "error" in region:
            return region
        example["kind"] = "flesh_region"
        example["group"] = group
        example["features"] = region["features"]
        if new_type:
            if material is None:
                raise ValueError(f"{type_name} is new: name its material (e.g. soft_fat, firm_flesh)")
            define(type_name, "volume", ["flesh"], material=material, names=name_tokens(type_name),
                   description=note or f"taught from {obj_name}:{group}",
                   zone=flesh.zone_around(region), paired=region.get("paired", False))
    else:
        m = measures or measure.analyze(obj_name)
        if "error" in m:
            return m
        rec = classify.classify(obj_name, cls=cls, measures=m)
        example["kind"] = "object"
        example["class"] = rec["class"]
        example["features"] = object_features(m)
        if new_type:
            if material is None and rec["family"] == "volume":
                raise ValueError(f"{type_name} is new: name its material (one of {sorted(reg['materials'])})")
            define(type_name, rec["family"], [rec["class"]], material=material,
                   names=name_tokens(type_name), description=note or f"taught from {obj_name}")
    user = _read(user_path())
    user["examples"] = [e for e in user["examples"]
                        if not (e.get("object") == obj_name and e.get("group") == group)]
    user["examples"].append(example)
    path = _save_user(user)
    return {"taught": type_name, "new_type": new_type, "example": example, "saved_to": path}


def nearest(features, kind="object", k=3, types=None):
    """The taught examples closest to `features`: [(distance, type, object)]."""
    reg = load()
    rows = []
    for e in reg["examples"]:
        if e.get("kind", "object") != kind or (types is not None and e["type"] not in types):
            continue
        rows.append((round(distance(features, e["features"]), 4), e["type"], e.get("object")))
    rows.sort()
    return rows[:k]


def types_for(family=None, cls=None):
    reg = load()
    return {n: t for n, t in reg["types"].items()
            if (family is None or t["family"] == family) and (cls is None or cls in t["classes"])}


def recognise(obj_name=None, measures=None, family=None, cls=None, features=None, name=None,
              kind="object"):
    """Propose a type. Evidence, strongest first: taught examples nearer than NEAR, words in
    the name, then the class's default. Returns {type, material, confidence, evidence,
    candidates, guessed}."""
    from . import measure
    if features is None:
        m = measures or measure.analyze(obj_name)
        if "error" in m:
            return m
        features = object_features(m)
        name = name or m["object"]
    candidates = types_for(family, cls)
    evidence = []
    scores = {t: 0.0 for t in candidates}
    tokens = name_tokens(name or "")
    for t, entry in candidates.items():
        words = set(entry.get("names", [])) | {t}
        hit = [w for w in tokens if w in words or (w.endswith("s") and w[:-1] in words)]
        if hit:
            scores[t] += 0.5
            evidence.append(f"name: {'/'.join(hit)} -> {t}")
    near = nearest(features, kind=kind, k=12, types=set(candidates))
    # each type counts only its nearest example: summed, two jello examples outvoted the
    # clay ball a renamed clay ball sat almost on top of (0.007 away)
    best_of = {}
    for d, t, obj in near:
        if d <= NEAR and t not in best_of:
            best_of[t] = (d, obj)
    for t, (d, obj) in best_of.items():
        scores[t] += 0.6 * (1.0 - d / NEAR)
        evidence.append(f"taught: resembles {obj} ({t}) at distance {d}")
    best = max(scores, key=lambda t: scores[t]) if scores else None
    guessed = False
    if best is None or scores[best] == 0.0:
        best = _default_type(candidates, cls)
        guessed = True
        if best:
            evidence.append(f"no name or taught example: {best} is the default for {cls or family}")
    confidence = min(0.95, 0.4 + (scores.get(best, 0.0) if best else 0.0))
    entry = candidates.get(best, {})
    return {"type": best, "material": entry.get("material"), "fabric": entry.get("fabric"),
            "confidence": round(confidence, 2), "evidence": evidence, "guessed": guessed,
            "candidates": sorted(((round(s, 3), t) for t, s in scores.items() if s > 0), reverse=True),
            "nearest": near, "features": features}


DEFAULT_TYPE = {"loose_volume": "jello", "mounted_volume": "jello", "flesh": "belly"}


def _default_type(candidates, cls):
    if cls in DEFAULT_TYPE and DEFAULT_TYPE[cls] in candidates:
        return DEFAULT_TYPE[cls]
    return next(iter(candidates), None)


def summary():
    reg = load()
    lines = [f"{len(reg['types'])} types, {len(reg['materials'])} materials, "
             f"{len(reg['examples'])} taught examples ({user_path()})"]
    for n, t in sorted(reg["types"].items(), key=lambda kv: (kv[1]["family"], kv[0])):
        taught = sum(1 for e in reg["examples"] if e["type"] == n)
        mat = t.get("material") or t.get("fabric") or "-"
        lines.append(f"  {t['family']:6} {n:14} {'/'.join(t['classes']):28} {mat:14} "
                     f"{t.get('origin', '')}{f', {taught} taught' if taught else ''}")
    return "\n".join(lines)
