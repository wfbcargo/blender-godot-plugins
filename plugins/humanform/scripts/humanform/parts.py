"""L4 parts: design variants of a region, judge them together, keep the good ones.

    variants = parts.variants("face", n=8, seed=3, sex="female")        # [{"name", "targets"}]
    sheet_png = views.variant_grid("Mara", out_png, variants, region="face")
    # one critic call judges every row of the grid; keep what it accepts:
    parts.store(human, "face", variants[2], tags=["soft", "round"], critic=verdict, sex="female")
    library.apply(other_body, part_card); scaffold.fit_face(other_body, lm)   # adapt to its measurements

    hv = parts.variants("hands", n=16, seed=5)                           # free targets + size offsets
    kept, lost = parts.screen(human, lm, hv, base, n=9)                  # refit each; drop the unreachable
    grid = views.variant_grid("Mara", png, kept, region="hands", apply=lambda v: parts.show(human, v))

A **design** changes a region's look through MPFB's style targets - the nose's hump and tip, lip
volume, jaw and chin, cheek volume, brow angle, ear shape - and leaves alone the targets the fit
uses to hold ANSUR's measurements (head breadth and depth, eye spacing, face height). Applying a
design and then refitting the face keeps the measurements and the look together.

Hands and feet have few free targets (finger thickness and spread; foot height), because the
hands-and-feet fit uses every lever that changes a measured size. Their designs also carry **offsets**:
moves of the measured sizes themselves (the palm - its breadth and length together, so finger length -
the wrist, foot breadth, the ankle), in ANSUR standard deviations. `design` refits to the offset landmark set, so a
"broad palm" part is broad for whoever wears it and still inside the population.
"""

from __future__ import annotations

import os

import numpy as np

from . import library, scaffold

# (target stem in its group, sided, (positive suffix, negative suffix), amplitude) per region.
# Amplitudes are what reads as a different person without caricature; measured on the contact sheets.
STYLE = {
    "face": [
        (("nose", "nose-hump", False, ("incr", "decr")), 0.6),
        (("nose", "nose-point-width", False, ("incr", "decr")), 0.5),
        (("nose", "nose-nostrils-width", False, ("incr", "decr")), 0.5),
        (("nose", "nose-point", False, ("up", "down")), 0.5),
        (("nose", "nose-width2", False, ("incr", "decr")), 0.4),
        (("mouth", "mouth-upperlip-volume", False, ("incr", "decr")), 0.6),
        (("mouth", "mouth-lowerlip-volume", False, ("incr", "decr")), 0.6),
        (("mouth", "mouth-scale-horiz", False, ("incr", "decr")), 0.4),
        (("mouth", "mouth-angles", False, ("up", "down")), 0.3),
        (("chin", "chin-prominent", False, ("incr", "decr")), 0.6),
        (("chin", "chin-width", False, ("incr", "decr")), 0.6),
        (("chin", "chin-bones", False, ("incr", "decr")), 0.6),
        (("cheek", "cheek-volume", True, ("incr", "decr")), 0.6),
        (("cheek", "cheek-inner", True, ("incr", "decr")), 0.5),
        (("eyebrows", "eyebrows-angle", False, ("up", "down")), 0.5),
        (("eyes", "eye-bag", True, ("incr", "decr")), 0.4),
        (("eyes", "eye-eyefold-angle", True, ("up", "down")), 0.4),
        (("eyes", "eye-height2", True, ("incr", "decr")), 0.4),
        (("ears", "ear-scale", True, ("incr", "decr")), 0.4),
        (("ears", "ear-flap", True, ("incr", "decr")), 0.5),
        (("forehead", "forehead-temple", False, ("incr", "decr")), 0.5),
    ],
    # what the hands-and-feet fit leaves free (scaffold.EXTREMITY_FINE holds the rest)
    "hands": [
        (("hands", "hand-fingers-diameter", True, ("incr", "decr")), 0.7),
        (("hands", "hand-fingers-distance", True, ("incr", "decr")), 0.7),
    ],
    "feet": [
        # depth lengthens the foot; the fit restores length and breadth with foot scale and width, so
        # what is left is a lower, flatter foot or a higher, thicker one
        (("feet", "foot-scale-depth", True, ("incr", "decr")), 0.6),
    ],
}

# A hand or foot design also moves the sizes the fit holds - a broad palm, long fingers, a slim ankle -
# as offsets in standard deviations of the brief's sex (ANSUR II), so the look is proportional on any
# body and the refit, not the design, decides the targets. (name, ((measurement, ANSUR variable), ...),
# amplitude in sd). MPFB's hand has one proportion lever (finger length against hand scale): at a fixed
# hand length it moves palm length and palm breadth together, about one sd each - so they are one
# offset, `palm`: + is a broad palm with short fingers, - a narrow palm with long fingers. Offsetting
# them separately asked for hands the mesh cannot make (refits 2-3.4 tolerances out).
OFFSETS = {
    "face": [],
    "hands": [("palm", (("palm_length", "palmlength"), ("hand_breadth", "handbreadth")), 1.2),
              ("wrist", (("wrist_circ", "wristcircumference"),), 1.0)],
    "feet": [("foot_breadth", (("foot_breadth", "footbreadthhorizontal"),), 1.3),
             ("ankle", (("ankle_circ", "anklecircumference"),), 1.0)],
}


def _keys(stem, sided, suffixes):
    sides = ("l-", "r-") if sided else ("",)
    return [(f"hf:{side}{stem}-{suffixes[0]}", f"hf:{side}{stem}-{suffixes[1]}") for side in sides]


def variants(region="face", n=8, seed=0, share=0.6, strength=1.0, name=None):
    """n random designs: each moves a random `share` of the region's style targets, within their
    amplitudes times `strength`, symmetrically."""
    rng = np.random.default_rng(seed)
    table = STYLE[region]
    learned = amplitude_scale(region)       # shrinks targets that critics keep rejecting
    out = []
    i = 0
    while len(out) < n:
        targets, offsets = {}, {}
        for (group, stem, sided, suffixes), amp in table:
            if rng.random() > share:
                continue
            amp = amp * learned.get(stem, 1.0)
            w = float(rng.uniform(-amp, amp) * strength)
            for pos, neg in _keys(stem, sided, suffixes):
                targets[pos] = round(max(w, 0.0), 3)
                targets[neg] = round(max(-w, 0.0), 3)
        for key, _pairs, amp in OFFSETS.get(region, []):
            if rng.random() > share:
                continue
            amp = amp * learned.get(key, 1.0)
            offsets[key] = round(float(rng.uniform(-amp, amp) * strength), 2)
        i += 1
        if not any(abs(w) > 0.05 for w in list(targets.values()) + list(offsets.values())):
            continue            # with two or three knobs a draw can move nothing; it would repeat the base
        v = {"name": f"{name or region}-{seed}-{i - 1}", "region": region, "targets": targets}
        if offsets:
            v["offsets"] = offsets
        out.append(v)
    return out


REACHABLE = 1.5      # a hand or foot design whose refit misses a measurement by more tolerances is not shown


def reachable(rep):
    """Whether a design's refit reached its offset sizes (`design`'s report): a design the mesh cannot
    make is dropped before the critic sees it, rather than judged as something it is not."""
    return rep is not None and rep["max_tol"] <= REACHABLE


def screen(human, lm, variants_list, base, n=None):
    """Refit each hand or foot design from the base body's extremity fit (`base`: its report) and keep
    those `reachable`, up to `n`. Each kept design gets `fit` (max tolerance, measurements, sizes reached)
    and `shape` (the region's resulting target values), so `show` puts it back without refitting when
    the grid renders. Leaves the body at the base design. Returns (kept, dropped) - dropped are the
    unreachable designs, with their fits."""
    kept, dropped = [], []
    for v in variants_list:
        if n is not None and len(kept) >= n:
            break
        rep = design(human, lm, v, start=base["params"], jacobian=base["jacobian"])
        v = dict(v, fit={"max_tol": rep["max_tol"], "measurements": rep["measurements"],
                         "sizes": {r["measure"]: [r["value"], r["target"]] for r in rep["residuals"]}})
        if not reachable(rep):
            dropped.append(v)
            continue
        v["shape"] = {k: val for k, val in library.capture(human)["targets"].items()
                      if library.region_of(k) == v["region"]}
        kept.append(v)
    design(human, lm, {"region": variants_list[0]["region"], "targets": {}}, start=base["params"],
           jacobian=base["jacobian"])
    return kept, dropped


def show(human, variant):
    """Put a screened design's resulting shape on the body (no fit)."""
    library.apply(human, {"kind": "part", "region": variant["region"],
                          "payload": {"targets": variant["shape"], "clears_region": True}})


def offset_landmarks(lm, variant, sex=None):
    """A copy of a landmark set with a design's size offsets added to its measures: each offset is in
    ANSUR standard deviations for the sex, taken relative to the population mean so a stylized or small
    body moves in proportion."""
    import copy
    from . import sheet
    offsets = (variant or {}).get("offsets") or (variant or {}).get("payload", {}).get("offsets") or {}
    out = copy.deepcopy(lm)
    if not offsets:
        return out
    stats = sheet.anthropometry()["sexes"][sex or lm["sex"]]["variables"]
    table = {name: pairs for name, pairs, _ in sum(OFFSETS.values(), [])}
    for name, z in offsets.items():
        for key, var in table.get(name, ()):
            if key in out["measures"]:
                v = stats[var]
                out["measures"][key] *= 1.0 + float(z) * v["sd"] / v["mean"]
    return out


def design(human, lm, variant, start=None, jacobian=None, verbose=False):
    """Put a hand or foot design on a fitted body: set its free targets, then refit hands and feet to
    the landmark set moved by its offsets. `start`/`jacobian` from the base body's extremity fit make
    this a few measurements. Returns the fit report."""
    apply(human, variant)
    return scaffold.fit_extremities(human, offset_landmarks(lm, variant), verbose=verbose, start=start,
                                    jacobian=jacobian)


def apply(human, variant):
    """Set a design's style targets (clearing the region's other style targets first)."""
    stems = {stem for (_, stem, _, _), _ in STYLE[variant["region"]]}
    kb = human.data.shape_keys.key_blocks
    for key in kb:
        if key.name.startswith("hf:") and any(st in key.name for st in stems):
            key.value = 0.0
    card = {"kind": "part", "region": variant["region"], "payload": {"targets": variant["targets"]}}
    library.apply(human, card)


# measured words for hand and foot designs: (knob - an offset name or a target stem, words for -, words
# for +, the axis a critic's tag must not contradict, threshold)
SIZE_WORDS = {
    "hands": [("palm", "narrow palm, long fingers", "broad palm, short fingers", ("palm", "long", "short"), 0.5),
              ("wrist", "slim wrist", "heavy wrist", ("wrist",), 0.5),
              ("hand-fingers-diameter", "slender fingers", "thick fingers", ("thick", "slim", "slender", "fine", "full"), 0.3),
              ("hand-fingers-distance", "close-set fingers", "spread fingers", ("spread", "close"), 0.3)],
    "feet": [("foot_breadth", "narrow foot", "broad foot", ("broad", "wide", "narrow"), 0.5),
             ("ankle", "slim ankle", "heavy ankle", ("ankle",), 0.5),
             ("foot-scale-depth", "high thick foot", "low flat foot", ("instep", "arch", "flat", "low", "high"), 0.3)],
}


def size_tags(variant):
    """Descriptive tags from what a hand or foot design measurably changes, and the axes they cover.
    Critics misread width on small, similar feet (three of eleven kept foot designs were tagged broad
    or narrow against their measured breadth offset), so measured words replace a critic's on those axes."""
    tags, axes = [], []
    offsets = variant.get("offsets") or {}
    for knob, neg, pos, axis, thresh in SIZE_WORDS.get(variant["region"], []):
        if knob in offsets:
            w = offsets[knob]
        else:
            w = max((val for k, val in variant["targets"].items() if k.endswith(f"{knob}-incr")), default=0.0) - \
                max((val for k, val in variant["targets"].items() if k.endswith(f"{knob}-decr")), default=0.0)
        if abs(w) >= thresh:
            tags += [t.strip() for t in (pos if w > 0 else neg).split(",")]
            axes += list(axis)
    return tags, axes


def store(human, region, variant, tags=(), critic=None, sex=None, style=None, thumb=None):
    """Keep a judged design as a library part (only its style targets, not the body's fitted ones). For
    hands and feet, the tags are the measured `size_tags` plus the critic's tags on other axes."""
    apply(human, variant)
    if region in SIZE_WORDS:
        measured, axes = size_tags(dict(variant, region=region))
        critic = dict(critic or {}, tags=list(tags))
        tags = measured + [t for t in tags if not any(a in t.lower() for a in axes) and t not in measured]
    nonzero = {k: v for k, v in variant["targets"].items() if abs(v) > 1e-4}
    payload = {"targets": nonzero, "clears_region": False, "style_stems": sorted(
        {stem for (_, stem, _, _), _ in STYLE[region]})}
    if variant.get("offsets"):
        payload["offsets"] = dict(variant["offsets"])      # applied to the landmark set before the fit
    card = {"schema": library.SCHEMA, "kind": "part", "region": region, "name": variant["name"], "tags": list(tags),
            "sex": sex, "style": style, "topology": library.TOPOLOGY, "payload": payload,
            "quality": {"critic": critic}, "source": "designed",
            "created": __import__("datetime").datetime.now().isoformat(timespec="seconds")}
    card["id"] = library._card_id(f"{region}-{variant['name']}", payload)
    return library._store(card, thumb)


# ------------------------------------------------------------------------------------------------
# learning from verdicts: which style targets keep appearing in rejected designs

MIN_JUDGED = 10          # below this many judged designs, amplitudes are not adjusted


def _stats_path(region):
    return os.path.join(library.root(), "stats", f"style_{region}.json")


def style_stats(region):
    try:
        with open(_stats_path(region), encoding="utf-8") as fh:
            return __import__("json").load(fh)
    except FileNotFoundError:
        return {"judged": 0, "stems": {}}


def _magnitudes(variant):
    mags = {}
    for (group, stem, sided, suffixes), amp in STYLE[variant["region"]]:
        w = 0.0
        for pos, neg in _keys(stem, sided, suffixes):
            w = max(w, abs(variant["targets"].get(pos, 0.0)), abs(variant["targets"].get(neg, 0.0)))
        mags[stem] = w / amp          # as a share of the amplitude it was drawn from
    for key, _pairs, amp in OFFSETS.get(variant["region"], []):
        mags[key] = abs((variant.get("offsets") or {}).get(key, 0.0)) / amp
    return mags


def record_verdicts(variants_list, verdict):
    """Add a batch critic's keep/reject per panel to the region's per-target statistics. Panels with
    no style targets (the base) are skipped."""
    import json
    region = verdict.get("region", "face")
    st = style_stats(region)
    for panel in verdict["panels"]:
        v = variants_list[panel["panel"]]
        if not v["targets"] and not v.get("offsets"):
            continue
        st["judged"] += 1
        for stem, share in _magnitudes(v).items():
            e = st["stems"].setdefault(stem, {"kept": 0.0, "rejected": 0.0, "kept_n": 0, "rejected_n": 0})
            key = "kept" if panel.get("keep") else "rejected"
            e[key] += share
            e[key + "_n"] += 1
    os.makedirs(os.path.dirname(_stats_path(region)), exist_ok=True)
    with open(_stats_path(region), "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1)
    return st


def amplitude_scale(region):
    """Per target, how much to shrink its amplitude: targets used harder in rejected designs than in
    kept ones shrink toward half. Nothing changes until MIN_JUDGED designs have been judged."""
    st = style_stats(region)
    out = {}
    if st["judged"] < MIN_JUDGED:
        return out
    for stem, e in st["stems"].items():
        kept = e["kept"] / max(e["kept_n"], 1)
        rej = e["rejected"] / max(e["rejected_n"], 1)
        if e["rejected_n"] >= 2 and rej > kept:
            out[stem] = float(np.clip(1.0 - (rej - kept), 0.5, 1.0))
    return out
