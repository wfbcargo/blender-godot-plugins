"""Reusable humans and parts: store what worked, find it again, apply it in a second.

    card = library.save_body(human, r, rep, hc, tags=["npc", "villager"])
    hits = library.find_bodies(r, k=3)          # [(distance, card)], nearest first
    library.apply(human, hits[0][1])            # macros and targets onto an MPFB body
    part = library.save_part(human, "face", name="angular-nose", tags=["stern"])
    library.apply(human, part)                  # only the face's targets change

Every MPFB2 body shares one mesh (the same vertices, UVs and rig), so nothing here stitches
geometry: a **body** card is the parameter set that made it - macros and the value of every
`hf:` target - and a **part** card is the subset of those targets that belong to one region
(face, hands, feet, torso, arms, legs). Applying a part changes only that region's targets, so
parts from different bodies combine without seams and the rig and UVs keep working.

Bodies are indexed by their ANSUR II z-scores (stature, weight, girths, breadths, lengths), the
same numbers a brief resolves to, so a new brief finds its nearest stored body directly.

The library lives outside the plugin, in `~/.claude/humanform/library` (override with the
HUMANFORM_LIBRARY environment variable): cards are the user's data, like follow-through's registry.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import sys

import numpy as np

_pkg = sys.modules[__package__]
SCHEMA = "humanform-library/1"
TOPOLOGY = "mpfb2:hm08"
RIG = "humanform:game_engine"
MACRO_NAMES = ("gender", "age", "muscle", "weight", "proportions", "height", "cupsize", "firmness",
               "asian", "caucasian", "african")

# ANSUR variables a body is indexed by, and their weight in the distance
FEATURES = {"stature": 2.0, "weightkg": 1.5, "chestcircumference": 1.0, "waistcircumference": 1.0,
            "buttockcircumference": 1.0, "bideltoidbreadth": 1.0, "hipbreadth": 0.8, "thighcircumference": 0.8,
            "crotchheight": 1.0, "acromionradialelength": 0.6, "headcircumference": 0.5, "Age": 0.5}

# which MPFB target files belong to which region (the name after an optional l-/r- side prefix)
REGIONS = {
    "face": ("head-", "eye", "cheek", "chin-", "forehead-", "nose-", "mouth-", "ear-", "eyebrows-"),
    "hands": ("hand-", "measure-wrist"),
    "feet": ("foot-", "measure-ankle"),
    "neck": ("neck", "measure-neck"),
    "arms": ("measure-upperarm", "measure-lowerarm", "upperarm-", "lowerarm-"),
    "legs": ("measure-upperleg", "measure-lowerleg", "measure-thigh", "measure-calf", "measure-knee",
             "upperleg-", "lowerleg-", "leg-"),
    "torso": ("measure-bust", "measure-underbust", "measure-waist", "measure-hips", "measure-shoulder",
              "measure-napetowaist", "measure-waisttohip", "measure-frontchest", "torso-", "hip-", "stomach-",
              "breast-", "buttocks-", "pelvis-"),
}


def root():
    path = os.environ.get("HUMANFORM_LIBRARY") or os.path.join(os.path.expanduser("~"), ".claude", "humanform", "library")
    os.makedirs(os.path.join(path, "items"), exist_ok=True)
    return path


def _index_path():
    return os.path.join(root(), "index.json")


def index():
    try:
        with open(_index_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {"schema": SCHEMA, "items": []}


def _write_index(ix):
    tmp = _index_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(ix, fh, indent=1)
    os.replace(tmp, _index_path())


def region_of(key_name):
    stem = key_name[len("hf:"):] if key_name.startswith("hf:") else key_name
    stem = re.sub(r"^[lr]-", "", stem)
    for region, prefixes in REGIONS.items():
        if stem.startswith(prefixes):
            return region
    return None


def capture(human):
    """The parameters that made a body: MPFB macros and every non-zero hf: target."""
    from . import scaffold
    _, _, HOP, _ = scaffold.services()
    macros = {n: round(float(HOP.get_value(n, entity_reference=human)), 5) for n in MACRO_NAMES}
    targets = {}
    if human.data.shape_keys:
        for kb in human.data.shape_keys.key_blocks:
            if kb.name.startswith("hf:") and abs(kb.value) > 1e-5:
                targets[kb.name] = round(float(kb.value), 5)
    return {"macros": macros, "targets": targets}


def _card_id(name, payload):
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:8]
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "item").lower()).strip("-")
    return f"{slug}-{digest}"


def _store(card, thumb=None):
    folder = os.path.join(root(), "items", card["id"])
    os.makedirs(folder, exist_ok=True)
    if thumb and os.path.exists(thumb):
        shutil.copyfile(thumb, os.path.join(folder, "thumb.png"))
        card["files"] = {"thumb": "thumb.png"}
    with open(os.path.join(folder, "card.json"), "w", encoding="utf-8") as fh:
        json.dump(card, fh, indent=1)
    ix = index()
    ix["items"] = [c for c in ix["items"] if c["id"] != card["id"]]
    summary = {k: card.get(k) for k in ("id", "kind", "region", "name", "tags", "sex", "style", "build", "features",
                                        "quality", "created")}
    ix["items"].append(summary)
    _write_index(ix)
    return card


def load(card_id):
    with open(os.path.join(root(), "items", card_id, "card.json"), encoding="utf-8") as fh:
        return json.load(fh)


def save_body(human, resolved, fit_rep=None, check_rep=None, name=None, tags=(), thumb=None, critic=None):
    """Store a fitted body. `resolved` is sheet.resolve()'s result (its z-scores index the body)."""
    s = resolved["sheet"]
    payload = capture(human)
    fr = fit_rep or {}
    params = dict((fr.get("extremities") or {}).get("params", {}))
    params.update(fr.get("params", {}))          # the settle pass ran last: its hand and foot scales hold
    params.update((fr.get("face") or {}).get("params", {}))
    card = {
        "schema": SCHEMA, "kind": "body", "region": "body", "name": name or s.get("name"), "tags": list(tags),
        "sex": s["sex"], "style": s["style"], "build": s.get("build") if isinstance(s.get("build"), str) else "custom",
        "topology": TOPOLOGY, "rig": RIG, "sheet": s,
        "features": {k: resolved["z"][k] for k in FEATURES if k in resolved["z"]},
        "payload": payload, "solver_params": params,
        # the solves' final Jacobians: a warm start from this body skips re-measuring every parameter
        "jacobians": {"body": fr.get("jacobian"), "face": (fr.get("face") or {}).get("jacobian"),
                      "extremities": (fr.get("extremities") or {}).get("jacobian")},
        "quality": {"fit_rms_tol": fr.get("rms_tol"), "fit_max_tol": fr.get("max_tol"),
                    "face_rms_tol": (fr.get("face") or {}).get("rms_tol"),
                    "extremities_rms_tol": (fr.get("extremities") or {}).get("rms_tol"),
                    "humancheck": (check_rep or {}).get("counts"), "critic": critic},
        "created": datetime.datetime.now().isoformat(timespec="seconds"), "source": "fit",
    }
    card["id"] = _card_id(card["name"], payload)
    return _store(card, thumb)


def save_part(human, region, name, tags=(), thumb=None, critic=None, sex=None, style=None):
    """Store one region's targets from a body as a part."""
    if region not in REGIONS:
        raise ValueError(f"region must be one of {sorted(REGIONS)}")
    full = capture(human)["targets"]
    targets = {k: v for k, v in full.items() if region_of(k) == region}
    if not targets:
        raise ValueError(f"{human.name} has no non-zero {region} targets to store")
    payload = {"targets": targets, "clears_region": True}
    card = {"schema": SCHEMA, "kind": "part", "region": region, "name": name, "tags": list(tags), "sex": sex,
            "style": style, "topology": TOPOLOGY, "payload": payload, "quality": {"critic": critic},
            "created": datetime.datetime.now().isoformat(timespec="seconds"), "source": "designed"}
    card["id"] = _card_id(f"{region}-{name}", payload)
    return _store(card, thumb)


def _distance(za, zb):
    num = den = 0.0
    for k, w in FEATURES.items():
        if k in za and k in zb:
            num += w * (za[k] - zb[k]) ** 2
            den += w
    return float(np.sqrt(num / den)) if den else float("inf")


def find_bodies(resolved, k=3, style=None):
    """Stored bodies of the same sex (and style) nearest the brief, by weighted ANSUR z-distance."""
    s = resolved["sheet"]
    style = style or s["style"]
    z = {key: resolved["z"][key] for key in FEATURES if key in resolved["z"]}
    hits = [(_distance(z, c.get("features") or {}), c) for c in index()["items"]
            if c["kind"] == "body" and c.get("sex") == s["sex"] and c.get("style") == style]
    hits.sort(key=lambda h: h[0])
    return hits[:k]


def find_parts(region, tags=(), sex=None):
    out = []
    for c in index()["items"]:
        if c["kind"] != "part" or c["region"] != region:
            continue
        if sex and c.get("sex") not in (None, sex):
            continue
        if tags and not set(tags) & set(c.get("tags") or []):
            continue
        out.append(c)
    return out


_TARGET_FILES = {}


def _target_file(stem):
    """MPFB target path for a file stem like 'l-hand-scale-incr', from a one-off directory listing."""
    from . import scaffold
    if not _TARGET_FILES:
        _, _, _, LocationService = scaffold.services()
        base = LocationService.get_mpfb_data("targets")
        for group in os.listdir(base):
            gdir = os.path.join(base, group)
            if os.path.isdir(gdir):
                for f in os.listdir(gdir):
                    if f.endswith(".target.gz"):
                        _TARGET_FILES[f[:-len(".target.gz")]] = os.path.join(gdir, f)
    return _TARGET_FILES.get(stem)


def apply(human, card, weight=1.0):
    """Put a body's macros and targets, or a part's targets, onto an MPFB body."""
    from . import scaffold
    _, TargetService, HOP, _ = scaffold.services()
    card = load(card["id"]) if "payload" not in card else card
    payload = card["payload"]
    if payload.get("type") == "delta":
        # a sculpted part: per-vertex heights, not targets (humanform.delta)
        from . import delta
        delta.apply(human, card, value=weight)
        return card
    if card["kind"] == "body":
        for n, v in payload["macros"].items():
            HOP.set_value(n, float(v), entity_reference=human)
        TargetService.reapply_macro_details(human)
    kb = human.data.shape_keys.key_blocks
    if card["kind"] == "body" or payload.get("clears_region"):
        for key in kb:
            if key.name.startswith("hf:") and (card["kind"] == "body" or region_of(key.name) == card["region"]):
                key.value = 0.0
    for name, value in payload["targets"].items():
        key = kb.get(name)
        if key is None:
            path = _target_file(name[len("hf:"):])
            if path is None:
                raise FileNotFoundError(f"no MPFB target for {name}")
            key = TargetService.load_target(human, path, weight=0.0, name=name)
        key.value = float(value) * weight
    human.data.update()
    return card


def remove(card_id):
    folder = os.path.join(root(), "items", card_id)
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    ix = index()
    ix["items"] = [c for c in ix["items"] if c["id"] != card_id]
    _write_index(ix)
