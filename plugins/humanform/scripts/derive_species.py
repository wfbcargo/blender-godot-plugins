"""Derive data/species/<id>.json (schema humanform-species/1) from the realistic preset and a few design knobs.

    python derive_species.py                  # write every species, assert consistency
    python derive_species.py --check          # assert only, write nothing
    python derive_species.py --chart out.svg  # also draw every species beside the human, true scale

Standard library only (no numpy), so any Python 3.9+ runs it - Blender's bundled one too.

A species is a human with its segments stretched or shrunk. The model works in *human units*: the realistic
preset's mean body for the sex, stature 1. Every vertical segment gets a length factor from the knobs below:

    floor -> ankle        foot height, with the foot's factor
    ankle -> knee         shin
    knee  -> hip joint    thigh
    hip   -> neck base    spine arc (the trunk); bent by the spine knobs, so its height can be less than its arc
    neck base -> head base the neck
    head (vertex - chin)  scaled so the body comes out `heads` heads tall

Summing them gives the species' stature in human units (H'); every ratio is its segment over H'. So the joint
heights, the segment lengths, the trunk fraction and the head count all come from one stack and agree by
construction - the asserts in `check()` prove it for every file written.

The knobs, per species (1.0 is a human; see SPECIES for each value's reason):

    heads        the head count (vertex to chin); chin = 1 - 1/heads
    trunk        spine arc length
    leg          hip-to-ankle length; `leg_rhizo` (0..1) is how much of the change the femur takes beyond its
                 proportional share (0 even, 1 all of it) - achondroplasia's shortening is rhizomelic
    arm          shoulder-to-wrist length, `arm_rhizo` the humerus's share, the same way; or `reach`: the hanging
                 fingertip's height above the knee as a fraction of H, and `arm` is solved to land it
    hand, foot   lengths (the foot also scales the ankle's height)
    neck         neck length
    shoulder_width, hip_width   breadths
    girth        across-bone thickness per region, relative to the body's own size (1.0 = a human's thickness
                 for its length scale); written out as absolute factors against the pre-warp human
    kyphosis_deg, lordosis_deg  extra bend over a human's: thoracic (upper 60% of the spine arc) forward,
                 lumbar (lower 40%) back. The joint heights are measured on the bent body.

Tolerances are the realistic preset's, scaled with the ratio (a shorter segment varies less in H) and by
`tol` (default 1.3: a designed species is less certain than a measured population).

The pre-warp human (docs/improvements/08-fantasy-species.md, layer 1): `basis` "trunk" gives it the species'
spine arc at human proportions (H_pre = H * spine_frac / human_spine_frac); "head" gives it the species' head
(H_pre = H * head_frac / human_head_frac), for a proportionate species. `segments`, `girth` and `widths` are the
warp's factors against that human: absolute length and thickness ratios.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OUT_DIR = os.path.join(DATA, "species")
SCHEMA = "humanform-species/1"
SEXES = ("female", "male")
ANSUR_STATURE = (1.45, 1.95)        # roughly ANSUR II's p1 female .. p99 male: where a pre-warp human fits well
LUMBAR_SHARE = 0.4                  # of the spine arc, hip joint up; the rest is thoracic

DND = "D&D 5e Player's Handbook (2014), 'Height and Weight' table"
ACH = ("Merker et al. 2018, Development of body proportions in achondroplasia (Am J Med Genet A 176:1819): "
       "adult legs ~50% and arm span ~35% shorter than average, sitting height mildly reduced - "
       "https://onlinelibrary.wiley.com/doi/10.1002/ajmg.a.40356")
ACH_TRIALS = ("BMN 111 (vosoritide) trial statistical plans: upper-to-lower segment ratio 1.9-2.1 in achondroplasia, "
              "~1.0 average - https://cdn.clinicaltrials.gov/large-docs/66/NCT03197766/SAP_001.pdf")
SQUARE_CUBE = ("Square-cube scaling and gait in large animals (duty factor and no aerial phase with size) - "
               "https://pmc.ncbi.nlm.nih.gov/articles/PMC8214834/")
DESIGN = "docs/improvements/08-fantasy-species.md (research, 2026-09-21)"

# Each knob is (value, why). Labels as in the design doc: [measured], [documented], [folklore].
SPECIES = {
    "elf": {
        "label": "Elf: tall, slender, long-legged and long-necked, pointed ears",
        "sources": [DESIGN, "Tolkien's Eldar as tall as tall men (folklore canon); art canon 8-8.5 heads"],
        "stature": ({"female": [1.65, 1.85], "male": [1.75, 1.95]},
                    "Tolkien-tall rather than D&D's 4'6\"+2d10 (1.42-1.88 m) [folklore]"),
        "bmi": ([17.5, 22.5], "slender; the human underweight-to-lean band [folklore]"),
        "basis": "trunk",
        "knobs": {
            "heads": (8.3, "the heroic-elegant canon between 8 and 8.5 heads [folklore]"),
            "trunk": (0.97, "a slightly short trunk makes the legs read longer [folklore]"),
            "leg": (1.07, "long legs: hip joint ~0.54 H against a human's 0.51-0.52 [folklore]"),
            "leg_rhizo": (0.0, "proportionate lengthening"),
            "arm": (1.03, "arms lengthened a little so the hands keep their place on the long legs"),
            "arm_rhizo": (0.0, "proportionate"),
            "hand": (1.04, "long fingers [folklore]"),
            "foot": (0.98, "narrow feet, slightly short against the long leg"),
            "neck": (1.35, "the long neck of the elf convention [folklore]"),
            "shoulder_width": (0.93, "narrow shoulders [folklore]"),
            "hip_width": (0.95, "narrow hips [folklore]"),
            "girth": ({"legs": 0.86, "arms": 0.86, "neck": 0.85, "torso": 0.90}, "slender limbs and a slim neck"),
            "kyphosis_deg": (-3.0, "a straighter, upright back"),
            "lordosis_deg": (0.0, "human lumbar curve"),
        },
        "waist_to_hip": ({"female": 0.78, "male": 0.88}, "a defined waist on a lean body"),
        "head": {"shape": "invertedtriangular", "shape_weight": 0.6,
                 "features": {"ears_pointed": 1.0, "brow_ridge": -0.2, "nose_size": -0.25, "tusks": 0.0}},
        "skin": {"palette": [[0.94, 0.84, 0.76], [0.84, 0.69, 0.58], [0.66, 0.50, 0.39], [0.45, 0.32, 0.25]],
                 "regions_off": [], "why": "human tones, pale to deep; every human region applies"},
        "moves": {"style": None, "notes": "Froude scaling alone gives a long, slow-cadence stride; a light, upright "
                                           "'elf_light' style (less vertical bob, soft heel strike) is convention, "
                                           "not physics - a named style for step 3"},
    },
    "halfling": {
        "label": "Halfling: small and proportionate, a child-like head fraction, big feet",
        "sources": [DESIGN, DND + ": halfling 2'7\" + 2d4 in (0.84-0.99 m)",
                    "Tolkien, The Fellowship of the Ring, prologue: hobbits 2-4 ft, large hairy feet"],
        "stature": ({"female": [0.85, 1.05], "male": [0.88, 1.10]},
                    "D&D 0.84-0.99 m, stretched toward Tolkien's taller hobbits [documented, game rules]"),
        "bmi": ([20.0, 30.0], "well fed and round [folklore]"),
        "basis": "head",
        "knobs": {
            "heads": (5.5, "a proportionate short body reads by its larger head fraction; 5.5 is a young child's "
                           "[measured, the distinction; folklore, the race]"),
            "trunk": (1.02, "a slightly long trunk (a round belly)"),
            "leg": (0.94, "slightly short legs"),
            "leg_rhizo": (0.0, "proportionate"),
            "arm": (0.97, "arms follow the legs"),
            "arm_rhizo": (0.0, "proportionate"),
            "hand": (1.0, "human hands for their size"),
            "foot": (1.22, "the big hobbit feet [folklore]"),
            "neck": (0.85, "a short neck"),
            "shoulder_width": (1.04, "sturdy"),
            "hip_width": (1.06, "sturdy, round"),
            "girth": ({"legs": 1.08, "arms": 1.05, "neck": 1.05, "torso": 1.10}, "plump and sturdy"),
            "kyphosis_deg": (0.0, "human"),
            "lordosis_deg": (3.0, "a little belly-forward sway"),
        },
        "waist_to_hip": ({"female": 0.90, "male": 0.98}, "a round belly"),
        "head": {"shape": "round", "shape_weight": 0.5,
                 "features": {"ears_pointed": 0.45, "brow_ridge": 0.0, "nose_size": 0.1, "tusks": 0.0}},
        "skin": {"palette": [[0.93, 0.78, 0.66], [0.80, 0.62, 0.49], [0.62, 0.45, 0.34], [0.46, 0.33, 0.25]],
                 "regions_off": [], "why": "human, ruddy; every human region applies"},
        "moves": {"style": None, "notes": "Froude scaling on ~0.45 m legs gives a quick, short step (about 1.7x a "
                                           "human's cadence); nothing else is implied by the build"},
    },
    "gnome": {
        "label": "Gnome: a proportionate shrink pushed further - about 1 m, a big head and a big nose",
        "sources": [DESIGN, DND + ": gnome 2'11\" + 2d4 in (0.94-1.09 m)"],
        "stature": ({"female": [0.92, 1.08], "male": [0.95, 1.12]}, "D&D 0.94-1.09 m [documented, game rules]"),
        "bmi": ([18.0, 27.0], "small and wiry to round"),
        "basis": "head",
        "knobs": {
            "heads": (4.3, "the design's 4.2, eased to 4.3: at 1.0 m that is already a 0.23 m head, a human "
                           "adult's head on a body 0.6x the size [folklore]"),
            "trunk": (1.0, "human"),
            "leg": (0.92, "short legs"),
            "leg_rhizo": (0.0, "proportionate: a gnome is not a dwarf"),
            "arm": (0.95, "arms follow the legs"),
            "arm_rhizo": (0.0, "proportionate"),
            "hand": (1.05, "nimble, slightly long fingers (tinkers) [folklore]"),
            "foot": (1.05, "slightly big feet"),
            "neck": (0.8, "a short neck under the big head"),
            "shoulder_width": (1.05, "not spindly under the big head"),
            "hip_width": (1.05, ""),
            "girth": ({"legs": 1.0, "arms": 1.0, "neck": 1.1, "torso": 1.05}, "human thickness for the size"),
            "kyphosis_deg": (0.0, "human"),
            "lordosis_deg": (2.0, "slight sway"),
        },
        "waist_to_hip": ({"female": 0.88, "male": 0.95}, ""),
        "head": {"shape": "round", "shape_weight": 0.7,
                 "features": {"ears_pointed": 0.6, "brow_ridge": 0.0, "nose_size": 0.8, "tusks": 0.0}},
        "skin": {"palette": [[0.94, 0.79, 0.68], [0.82, 0.62, 0.50], [0.64, 0.46, 0.35], [0.47, 0.33, 0.25]],
                 "regions_off": [], "why": "human, ruddy; every human region applies (the flush reads as a gnome's "
                                           "red cheeks and nose)"},
        "moves": {"style": None, "notes": "Froude scaling on ~0.45 m legs gives a quick scurry; nothing else "
                                           "implied"},
    },
    "dwarf": {
        "label": "Dwarf: short, stocky, long trunk, short limbs (softened achondroplasia)",
        "sources": [DESIGN, ACH, ACH_TRIALS,
                    DND + ": hill dwarf 3'8\" + 2d4 in (1.17-1.32 m), mountain dwarf 4'0\" + 2d4 in (1.27-1.42 m)"],
        "stature": ({"female": [1.15, 1.40], "male": [1.20, 1.45]},
                    "D&D hill and mountain dwarves, 1.17-1.42 m [documented, game rules]"),
        "bmi": ([26.0, 38.0], "a human trunk's mass on short legs: a 1.3 m dwarf at 60 kg is BMI 35. Achondroplastic "
                              "adults' BMI runs high for the same reason [measured]"),
        "basis": "trunk",
        "knobs": {
            "heads": (5.0, "art draws dwarves at 4-4.5 heads [folklore], but with a human-sized trunk that is a "
                           "0.28-0.32 m head on a 1.3 m body - bigger than any human head. 5.0 gives 0.26 m: the large "
                           "head of achondroplasia (macrocephaly [measured]) without a cartoon"),
            "trunk": (0.97, "sitting height only mildly reduced in achondroplasia [measured]"),
            "leg": (0.72, "legs 28% short (hip to ankle, against a human with the same trunk). 0.56 here reproduces "
                          "achondroplasia's ~50% [measured] and an upper/lower segment ratio of 1.9; 0.72 softens "
                          "it to ~1.5, inside the design's 1.3-1.6"),
            "leg_rhizo": (0.35, "rhizomelic: the femur shortened most [measured]"),
            "arm": (0.78, "arms 22% short: achondroplasia shortens the span ~35% for legs ~50% [measured], the "
                          "same 0.7 share of the legs' 28%"),
            "arm_rhizo": (0.35, "rhizomelic: the humerus shortened most [measured]"),
            "hand": (0.88, "short broad hands (achondroplasia's brachydactyly [measured])"),
            "foot": (0.85, "short broad feet"),
            "neck": (0.6, "a thick short neck [folklore]"),
            "shoulder_width": (1.08, "broad shoulders, barrel chest [folklore]"),
            "hip_width": (1.08, "a broad pelvis"),
            "girth": ({"legs": 1.05, "arms": 1.12, "neck": 1.25, "torso": 1.12},
                      "heavy forearms, thick neck, barrel chest; a short thigh stays as thick [folklore]"),
            "kyphosis_deg": (0.0, "human"),
            "lordosis_deg": (8.0, "exaggerated lumbar lordosis, as in achondroplasia [measured]"),
        },
        "waist_to_hip": ({"female": 0.90, "male": 0.98}, "a barrel trunk"),
        "head": {"shape": "square", "shape_weight": 0.7,
                 "features": {"ears_pointed": 0.0, "brow_ridge": 0.45, "nose_size": 0.5, "tusks": 0.0}},
        "skin": {"palette": [[0.88, 0.71, 0.59], [0.74, 0.55, 0.43], [0.56, 0.40, 0.30], [0.40, 0.28, 0.21]],
                 "regions_off": [], "why": "human, weathered; every human region applies"},
        "moves": {"style": None, "notes": "derive_style gives the roll from the trunk/leg ratio: more hip flexion, "
                                           "abduction, anterior tilt and pelvic obliquity, less knee flexion "
                                           "(achondroplasia gait [measured]); Froude on ~0.55 m legs gives the "
                                           "quick short step. No named style needed"},
    },
    "orc": {
        "label": "Orc: broad, heavy and tall, green-grey skin, tusks and a heavy brow",
        "sources": [DESIGN, DND + ": half-orc 4'10\" + 2d10 in (1.52-2.0 m)"],
        "stature": ({"female": [1.70, 1.90], "male": [1.80, 2.05]},
                    "tall end of D&D's half-orc range [documented, game rules]"),
        "bmi": ([26.0, 36.0], "heavily muscled [folklore]"),
        "basis": "trunk",
        "knobs": {
            "heads": (7.5, "the design's 7.5: a slightly big, heavy-jawed head [folklore]"),
            "trunk": (1.04, "a long, deep trunk"),
            "leg": (0.97, "slightly short legs against the trunk: power, not reach [folklore]"),
            "leg_rhizo": (0.0, ""),
            "arm": (1.04, "long heavy arms [folklore]"),
            "arm_rhizo": (0.0, ""),
            "hand": (1.08, "big hands"),
            "foot": (1.05, ""),
            "neck": (0.7, "a short, thick neck"),
            "shoulder_width": (1.18, "broad [folklore]"),
            "hip_width": (1.04, ""),
            "girth": ({"legs": 1.15, "arms": 1.22, "neck": 1.30, "torso": 1.15}, "heavy muscle"),
            "kyphosis_deg": (6.0, "a slight forward carriage of the shoulders"),
            "lordosis_deg": (0.0, ""),
        },
        "waist_to_hip": ({"female": 0.86, "male": 0.95}, "a thick waist"),
        "head": {"shape": "square", "shape_weight": 0.8,
                 "features": {"ears_pointed": 0.5, "brow_ridge": 0.8, "nose_size": 0.3, "tusks": 0.7}},
        "skin": {"palette": [[0.56, 0.63, 0.41], [0.44, 0.52, 0.33], [0.52, 0.53, 0.44], [0.34, 0.40, 0.29]],
                 "regions_off": ["lips", "flush"],
                 "why": "olive to grey-green. The red lips and flushed cheeks are blood under thin human skin: on "
                        "green they read as mud, so they are off; the creases (knee, elbow, knuckle) stay"},
        "moves": {"style": None, "notes": "derive_style from stockiness: longer contact, wider stance, less bounce. "
                                           "A heavy stomp is a named style if wanted"},
    },
    "goblin": {
        "label": "Goblin: small, scrawny and hunched, a big head with big pointed ears, long arms, green skin",
        "sources": [DESIGN, DND + ": goblin (Monster Manual / Volo's) 3'5\" + 2d4 in, about 1.0-1.2 m"],
        "stature": ({"female": [0.95, 1.15], "male": [1.00, 1.20]}, "about 1.0-1.2 m [documented, game rules]"),
        "bmi": ([15.5, 21.0], "scrawny [folklore]"),
        "basis": "head",
        "knobs": {
            "heads": (5.0, "the design's 5 heads [folklore]"),
            "trunk": (1.0, ""),
            "leg": (0.92, "short, bandy legs [folklore]"),
            "leg_rhizo": (0.0, ""),
            "arm": (1.0, "solved from `reach`"),
            "arm_rhizo": (0.0, ""),
            "reach": (0.05, "long arms: the hanging fingertips 0.05 H above the knee, against a human's ~0.08 "
                            "[folklore]"),
            "hand": (1.18, "big grasping hands [folklore]"),
            "foot": (1.2, "big feet [folklore]"),
            "neck": (0.8, "the head carried forward on a short neck"),
            "shoulder_width": (0.92, "narrow, scrawny"),
            "hip_width": (0.92, ""),
            "girth": ({"legs": 0.78, "arms": 0.78, "neck": 0.85, "torso": 0.88}, "scrawny, stringy limbs"),
            "kyphosis_deg": (26.0, "the hunch [folklore]"),
            "lordosis_deg": (-4.0, "a flattened lower back under the hunch"),
        },
        "waist_to_hip": ({"female": 0.90, "male": 0.95}, "a pot belly on a thin body"),
        "head": {"shape": "triangular", "shape_weight": 0.6,
                 "features": {"ears_pointed": 1.0, "ear_size": 0.9, "brow_ridge": 0.3, "nose_size": 0.7,
                              "tusks": 0.0}},
        "skin": {"palette": [[0.62, 0.66, 0.38], [0.50, 0.58, 0.30], [0.55, 0.52, 0.36], [0.40, 0.46, 0.28]],
                 "regions_off": ["lips", "flush"],
                 "why": "yellow-green to olive; red lips and flush off, as the orc"},
        "moves": {"style": None, "notes": "the hunch is in the rest pose; a forward-leaning scuttle is a posture on "
                                           "top (step 3). Froude on ~0.5 m legs gives a quick step"},
    },
    "troll": {
        "label": "Troll: huge (2.4-2.8 m), kyphotic, long-armed (hands to the knee), grey-green, square-cube heavy",
        "sources": [DESIGN, SQUARE_CUBE],
        "stature": ({"female": [2.35, 2.70], "male": [2.45, 2.85]}, "the design's 2.4-2.8 m [folklore]"),
        "bmi": ([36.0, 50.0], "square-cube: a body scaled up keeps its density, so mass grows as H^3 and BMI as H. "
                              "A human at BMI 27 scaled to 2.6 m is BMI 40 [measured, scaling law]"),
        "basis": "trunk",
        "knobs": {
            "heads": (7.0, "the design's 7 at 2.6 m: a small head for the bulk [folklore]"),
            "trunk": (1.08, "a long heavy trunk"),
            "leg": (0.93, "legs a little short against the trunk [folklore]"),
            "leg_rhizo": (0.0, ""),
            "arm": (1.0, "solved from `reach`"),
            "arm_rhizo": (0.0, ""),
            "reach": (0.01, "hands to the knee: hanging fingertips at the knee [folklore]"),
            "hand": (1.25, "huge hands"),
            "foot": (1.12, ""),
            "neck": (0.6, "the head slung forward on a short neck"),
            "shoulder_width": (1.28, "massive shoulders"),
            "hip_width": (1.12, ""),
            "girth": ({"legs": 1.35, "arms": 1.35, "neck": 1.45, "torso": 1.30},
                      "square-cube: bone section grows faster than length for the load [measured, scaling law]"),
            "kyphosis_deg": (32.0, "the hunch [folklore]"),
            "lordosis_deg": (0.0, ""),
        },
        "waist_to_hip": ({"female": 0.98, "male": 1.02}, "a belly as wide as the hips"),
        "head": {"shape": "rectangular", "shape_weight": 0.8,
                 "features": {"ears_pointed": 0.3, "brow_ridge": 1.0, "nose_size": 0.6, "tusks": 0.4}},
        "skin": {"palette": [[0.52, 0.55, 0.48], [0.44, 0.49, 0.40], [0.37, 0.42, 0.35], [0.30, 0.33, 0.29]],
                 "regions_off": ["lips", "flush", "nipple", "genital", "knee", "elbow", "knuckle"],
                 "why": "grey-green, stony. Every red-shifted region is off: a troll's hide has no blood showing "
                        "through; the paler palms, soles and nails stay"},
        "moves": {"style": None, "notes": "large-animal gait from the mass (~300+ kg): straight legs, duty factor up, "
                                           "no aerial phase - a run is a fast walk [measured, animals]. The forward "
                                           "lean while walking is a posture on top of the rest-pose hunch"},
    },
}

HEIGHTS = ("ankle_joint", "knee_joint", "crotch", "hip_joint", "shoulder_joint", "chin")
LENGTHS = ("upper_arm", "forearm", "hand", "foot", "thigh", "shin", "shoulder_width", "hip_width")


def _load():
    with open(os.path.join(DATA, "presets.json"), encoding="utf-8") as fh:
        presets = json.load(fh)
    with open(os.path.join(DATA, "anthropometry.json"), encoding="utf-8") as fh:
        anth = json.load(fh)
    return presets, anth


def _names(path, pattern):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(pattern, text, re.S)
    return m.group(1) if m else ""


def face_shapes():
    return tuple(re.findall(r'"(\w+)"', _names(os.path.join(HERE, "humanform", "sheet.py"),
                                              r"FACE_SHAPES = \(([^)]*)\)")))


def skin_regions():
    block = _names(os.path.join(HERE, "humanform", "skin.py"), r"\nREGIONS = \{(.*?)\n\}")
    return tuple(re.findall(r'^\s+"(\w+)":', block, re.M))


def human(presets, anth, sex):
    """The realistic mean body for a sex, as fractions of H."""
    r = presets["presets"]["realistic"]["ratios"]
    v = anth["sexes"][sex]["variables"]

    def t(k):
        e = r[k]
        return (e.get("any") or e[sex])

    b = {k: t(k)[0] for k in r}
    b["tol"] = {k: t(k)[1] for k in r}
    b["neck_base"] = v["cervicaleheight"]["ratio_mean"]
    b["head_base"] = 1.0 - v["tragiontopofhead"]["ratio_mean"] - 0.01     # as landmarks.from_measurements
    b["heads"] = 1.0 / (1.0 - b["chin"])
    d = presets["presets"]["realistic"]["derived"]
    b["derived"] = {k: (d[k].get("any") or d[k][sex]) for k in ("shoulder_to_hip_width", "waist_to_hip_circ")}
    return b


def spine_curve(arc, kyph, lord, n=200):
    """Heights and forward offsets along a spine of arc length `arc`, the lumbar span bent back by `lord` degrees
    and the thoracic span forward by `kyph`, each bend spread evenly over its span. Returns a function of the
    arc fraction s (0 = hip joint, 1 = neck base) -> (z, y), plus the neck's tilt at the top (radians)."""
    pts = [(0.0, 0.0)]
    z = y = 0.0
    lk, tk = math.radians(lord), math.radians(kyph)
    ds = 1.0 / n
    for i in range(n):
        s = (i + 0.5) * ds
        if s < LUMBAR_SHARE:
            phi = -lk * s / LUMBAR_SHARE
        else:
            phi = -lk + tk * (s - LUMBAR_SHARE) / (1.0 - LUMBAR_SHARE)
        z += math.cos(phi) * arc * ds
        y += math.sin(phi) * arc * ds
        pts.append((z, y))

    def at(s):
        i = min(int(s * n), n - 1)
        f = s * n - i
        (z0, y0), (z1, y1) = pts[i], pts[i + 1]
        return z0 + (z1 - z0) * f, y0 + (y1 - y0) * f
    return at, tk - lk


def _split(total_factor, rhizo, a_len, b_len):
    """Factors for two segments a (proximal) and b whose sum changes by `total_factor`: the proximal one takes
    its proportional share of the change, plus `rhizo` of the rest."""
    change = (1.0 - total_factor) * (a_len + b_len)
    share = a_len / (a_len + b_len)
    share = share + rhizo * (1.0 - share)
    fa = 1.0 - change * share / a_len
    fb = 1.0 - change * (1.0 - share) / b_len
    return fa, fb


def build(h, knobs, arm=None):
    """One species body for one sex in human units, and its fractions of its own stature."""
    k = {name: val for name, (val, _why) in knobs.items() if name != "girth"}
    arm = k["arm"] if arm is None else arm
    f_thigh, f_shin = _split(k["leg"], k["leg_rhizo"], h["thigh"], h["shin"])
    f_hum, f_fa = _split(arm, k["arm_rhizo"], h["upper_arm"], h["forearm"])
    u = {}
    u["ankle_joint"] = h["ankle_joint"] * k["foot"]
    u["knee_joint"] = u["ankle_joint"] + h["shin"] * f_shin
    u["hip_joint"] = u["knee_joint"] + h["thigh"] * f_thigh
    arc = (h["neck_base"] - h["hip_joint"]) * k["trunk"]
    at, neck_tilt = spine_curve(arc, k["kyphosis_deg"], k["lordosis_deg"])
    q = (h["shoulder_joint"] - h["hip_joint"]) / (h["neck_base"] - h["hip_joint"])
    zs, ys = at(q)
    zn, yn = at(1.0)
    u["shoulder_joint"] = u["hip_joint"] + zs
    u["neck_base"] = u["hip_joint"] + zn
    neck = (h["head_base"] - h["neck_base"]) * k["neck"]
    # the neck extends to bring the head back upright: it rises at half the spine's end tilt
    u["head_base_rel"] = neck * math.cos(neck_tilt / 2)
    base = u["neck_base"] + u["head_base_rel"]
    head_h = 1.0 - h["chin"]                     # human head length, vertex to chin
    above = 1.0 - h["head_base"]                 # of which above the head base
    g = base / (head_h * k["heads"] - above)     # head scale that makes the body `heads` heads tall
    Hs = base + above * g
    u["chin"] = Hs - head_h * g
    u["crotch"] = u["hip_joint"] - (h["hip_joint"] - h["crotch"]) * k["hip_width"]
    u["upper_arm"] = h["upper_arm"] * f_hum
    u["forearm"] = h["forearm"] * f_fa
    u["hand"] = h["hand"] * k["hand"]
    u["foot"] = h["foot"] * k["foot"]
    u["thigh"] = h["thigh"] * f_thigh
    u["shin"] = h["shin"] * f_shin
    u["shoulder_width"] = h["shoulder_width"] * k["shoulder_width"]
    u["hip_width"] = h["hip_width"] * k["hip_width"]
    fr = {key: u[key] / Hs for key in HEIGHTS + LENGTHS + ("neck_base",)}
    fr["head_base"] = (u["neck_base"] + u["head_base_rel"]) / Hs
    fr["spine_arc"] = arc / Hs
    fr["shoulder_forward"] = ys / Hs
    fr["neck_forward"] = yn / Hs
    fr["heads"] = 1.0 / (1.0 - fr["chin"])
    fr["fingertip"] = fr["shoulder_joint"] - fr["upper_arm"] - fr["forearm"] - fr["hand"]
    factors = {"femur": f_thigh, "tibia": f_shin, "humerus": f_hum, "forearm": f_fa, "hand": k["hand"],
               "foot": k["foot"], "spine": k["trunk"], "neck": k["neck"], "head": g}
    return {"u": u, "H": Hs, "fr": fr, "factors": factors, "arm": arm}


def solve_reach(h, knobs):
    """The arm factor that puts the hanging fingertip `reach` H above the knee (bisection: reach falls with arm)."""
    target = knobs["reach"][0]
    lo, hi = 0.5, 2.0
    for _ in range(60):
        mid = (lo + hi) / 2
        b = build(h, knobs, arm=mid)
        if b["fr"]["fingertip"] - b["fr"]["knee_joint"] > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def metrics(fr):
    leg, trunk = fr["hip_joint"], fr["neck_base"] - fr["hip_joint"]
    return {"hip_joint": leg, "neck_base": fr["neck_base"], "trunk": trunk, "trunk_to_leg": trunk / leg,
            "upper_to_lower_segment": (1.0 - fr["crotch"]) / fr["crotch"],
            "relative_sitting_height": 1.0 - fr["crotch"] + 0.005,
            "arm_length": fr["upper_arm"] + fr["forearm"] + fr["hand"],
            "fingertip_above_knee": fr["fingertip"] - fr["knee_joint"],
            "head_length": 1.0 - fr["chin"]}


def species_doc(sid, spec, presets, anth):
    per_sex = {}
    for sex in SEXES:
        h = human(presets, anth, sex)
        knobs = spec["knobs"]
        arm = solve_reach(h, knobs) if "reach" in knobs else None
        b = build(h, knobs, arm=arm)
        per_sex[sex] = (h, b)
    tol_scale = spec.get("tol", 1.3)
    realistic = presets["presets"]["realistic"]
    ratios = {}
    for key in realistic["ratios"]:
        if key == "chin":
            continue
        ent = {}
        for sex in SEXES:
            h, b = per_sex[sex]
            v = b["fr"][key]
            tol = max(0.005, h["tol"][key] * tol_scale * v / h[key])
            ent[sex] = [round(v, 4), round(tol, 4)]
        ent["source"] = f"derive_species.py: realistic {key} through the {sid} knobs"
        ratios[key] = ent
    heads = spec["knobs"]["heads"][0]
    heads_tol = round(0.35 * tol_scale * heads / 7.7, 3)
    ratios["chin"] = {"any": [round(1.0 - 1.0 / heads, 4), round(heads_tol / heads ** 2, 4)],
                      "source": "1 - 1/heads, the tolerance from the heads tolerance"}

    derived = {}
    for sex in SEXES:
        h, b = per_sex[sex]
        derived.setdefault("shoulder_to_hip_width", {})[sex] = [
            round(b["fr"]["shoulder_width"] / b["fr"]["hip_width"], 3),
            round(realistic["derived"]["shoulder_to_hip_width"][sex][1] * tol_scale, 3)]
        derived.setdefault("waist_to_hip_circ", {})[sex] = [
            spec["waist_to_hip"][0][sex], round(realistic["derived"]["waist_to_hip_circ"][sex][1] * tol_scale, 3)]
    derived["shoulder_to_hip_width"]["source"] = "shoulder_width / hip_width of this species"
    derived["waist_to_hip_circ"]["source"] = "design choice: " + spec["waist_to_hip"][1]

    human_gap = presets["features"]["hip_above_crotch"]["range"]
    gaps = [per_sex[s][1]["fr"]["hip_joint"] - per_sex[s][1]["fr"]["crotch"] for s in SEXES]
    hgaps = [per_sex[s][0]["hip_joint"] - per_sex[s][0]["crotch"] for s in SEXES]
    gscale = sum(gaps) / sum(hgaps)
    features = {"hip_above_crotch": {"range": [round(human_gap[0] * gscale, 4), round(human_gap[1] * gscale, 4)],
                                     "note": "the human range scaled with this species' hip-to-crotch gap"}}

    # the pre-warp human and the warp factors against it
    pre, segments, girth, widths = {}, {}, {}, {}
    for sex in SEXES:
        h, b = per_sex[sex]
        if spec["basis"] == "trunk":
            kf = b["fr"]["spine_arc"] / (h["neck_base"] - h["hip_joint"])
        else:
            kf = (1.0 - b["fr"]["chin"]) / (1.0 - h["chin"])
        lo, hi = spec["stature"][0][sex]
        pre.setdefault("stature_factor", {})[sex] = round(kf, 4)
        pre.setdefault("stature", {})[sex] = [round(lo * kf, 3), round(hi * kf, 3)]
        scale = 1.0 / (b["H"] * kf)       # a human-unit length -> warp factor
        segments[sex] = {n: round(f * scale, 4) for n, f in b["factors"].items()}
        body = spec["knobs"]["trunk"][0] * scale      # the body's own size, against the pre-warp human
        girth[sex] = {n: round(g * body, 4) for n, g in spec["knobs"]["girth"][0].items()}
        widths[sex] = {n: round(spec["knobs"][n][0] * scale, 4) for n in ("shoulder_width", "hip_width")}
    proportion = {}
    for sex in SEXES:
        h, b = per_sex[sex]
        m, hm = metrics(b["fr"]), metrics(h | {"fingertip": h["shoulder_joint"] - h["upper_arm"] - h["forearm"]
                                                  - h["hand"]})
        proportion[sex] = {k: round(v, 4) for k, v in m.items()}
        proportion[sex]["human"] = {k: round(v, 4) for k, v in hm.items()}
        proportion[sex]["shoulder_forward"] = round(b["fr"]["shoulder_forward"], 4)
        proportion[sex]["arm_factor"] = round(b["arm"], 4)

    knob_notes = {n: why for n, (val, why) in spec["knobs"].items() if why}
    doc = {
        "schema": SCHEMA,
        "id": sid,
        "label": spec["label"],
        "baseline": "human",
        "sources": spec["sources"],
        "notes": {
            "generated": "by scripts/derive_species.py from the realistic preset - edit its knobs, not this file",
            "stature": spec["stature"][1],
            "bmi": spec["bmi"][1],
            "knobs": knob_notes,
            "skin": spec["skin"]["why"],
            "ratios": "fractions of the final standing stature (spine curve applied), as presets.json; tolerances "
                      "are the realistic preset's scaled with the value and by %.1f" % tol_scale,
            "proportion": "not graded: the trunk (neck base - hip joint), upper/lower segment ((H - crotch) / "
                          "crotch), relative sitting height (~1 - crotch) and hanging reach, with the human's beside",
            "segments": "bone length factors against the pre-warp human (pre_warp); girth and widths likewise "
                        "absolute. The warp solves the final factors so the measured joints land on `ratios`",
        },
        "knobs": {n: val for n, (val, _w) in spec["knobs"].items()},
        "stature": spec["stature"][0],
        "bmi": spec["bmi"][0],
        "heads": {"any": [heads, heads_tol], "source": "1 / (1 - chin)"},
        "ratios": ratios,
        "derived": derived,
        "features": features,
        "proportion": proportion,
        "pre_warp": {"basis": spec["basis"], "min_stature": ANSUR_STATURE[0], "max_stature": ANSUR_STATURE[1],
                     "note": "H_pre = H * stature_factor (stature: the H_pre range). Outside min/max_stature, fit at the "
                             "limit and scale every segment, girth and width factor by H_pre / limit (a uniform scale)", **pre},
        "segments": segments,
        "girth": girth,
        "widths": widths,
        "spine": {"kyphosis_deg": spec["knobs"]["kyphosis_deg"][0], "lordosis_deg": spec["knobs"]["lordosis_deg"][0],
                  "lumbar_share": LUMBAR_SHARE,
                  "note": "extra bend over a human's; thoracic forward, lumbar back, spread evenly over each span"},
        "head": spec["head"],
        "skin": {"palette": spec["skin"]["palette"], "regions_off": spec["skin"]["regions_off"]},
        "moves": spec["moves"],
    }
    return doc, per_sex


def check(sid, doc, per_sex, presets):
    """Every file's numbers agree with each other."""
    p = []

    def need(cond, msg):
        if not cond:
            p.append(f"{sid}: {msg}")

    need(set(doc["ratios"]) == set(presets["presets"]["realistic"]["ratios"]),
         "ratios must cover exactly the realistic preset's keys")
    heads = doc["heads"]["any"][0]
    need(abs(doc["ratios"]["chin"]["any"][0] - (1 - 1 / heads)) < 1e-4, "chin must be 1 - 1/heads")
    for sex in SEXES:
        h, b = per_sex[sex]
        r = {k: v[sex][0] if sex in v else v["any"][0] for k, v in doc["ratios"].items()}
        fr = b["fr"]
        order = ["ankle_joint", "knee_joint", "crotch", "hip_joint", "shoulder_joint"]
        need(all(r[a] < r[c] for a, c in zip(order, order[1:])), f"{sex}: joint heights out of order {order}")
        need(r["shoulder_joint"] < fr["neck_base"] < 1.0, f"{sex}: neck base must lie between shoulder and vertex")
        need(r["shoulder_joint"] < r["chin"] < 1.0, f"{sex}: chin must lie above the shoulder joints")
        need(abs(r["thigh"] - (r["hip_joint"] - r["knee_joint"])) < 2e-4, f"{sex}: thigh != hip - knee")
        need(abs(r["shin"] - (r["knee_joint"] - r["ankle_joint"])) < 2e-4, f"{sex}: shin != knee - ankle")
        need(abs(fr["heads"] - heads) < 1e-3, f"{sex}: body heads {fr['heads']:.3f} != {heads}")
        prop = doc["proportion"][sex]
        need(abs(prop["trunk"] - (prop["neck_base"] - prop["hip_joint"])) < 2e-4, f"{sex}: trunk != neck - hip")
        need(abs(prop["hip_joint"] - r["hip_joint"]) < 2e-4, f"{sex}: proportion.hip_joint != ratios")
        lo, hi = doc["features"]["hip_above_crotch"]["range"]
        need(lo <= r["hip_joint"] - r["crotch"] <= hi, f"{sex}: hip above crotch outside its own range")
        need(fr["fingertip"] > r["ankle_joint"] + 0.05, f"{sex}: hanging hands reach the ankles")
        s_lo, s_hi = doc["stature"][sex]
        need(0.5 <= s_lo < s_hi <= 3.2, f"{sex}: stature range {s_lo}-{s_hi}")
        for n, f in doc["segments"][sex].items():
            need(0.2 < f < 2.5, f"{sex}: segment {n} factor {f}")
    b_lo, b_hi = doc["bmi"]
    need(10 < b_lo < b_hi < 60, "bmi range")
    pal = doc["skin"]["palette"]
    need(2 <= len(pal) <= 4 and all(len(c) == 3 and all(0 <= x <= 1 for x in c) for c in pal),
         "palette: 2-4 sRGB tones in 0..1")
    regions = skin_regions()
    need(regions and set(doc["skin"]["regions_off"]) <= set(regions),
         f"regions_off {doc['skin']['regions_off']} not all in skin.REGIONS {regions}")
    need(doc["head"]["shape"] in face_shapes(), f"head shape {doc['head']['shape']} not in sheet.FACE_SHAPES")
    need(0 <= doc["head"]["shape_weight"] <= 1, "shape_weight in 0..1")
    # species-specific design claims
    if sid == "dwarf":
        for sex in SEXES:
            us = doc["proportion"][sex]["upper_to_lower_segment"]
            need(1.3 <= us <= 1.6, f"{sex}: upper/lower segment {us:.2f} outside the softened 1.3-1.6")
            need(doc["proportion"][sex]["fingertip_above_knee"] > 0, f"{sex}: dwarf hands must hang above the knee")
    if sid == "troll":
        for sex in SEXES:
            need(abs(doc["proportion"][sex]["fingertip_above_knee"] - 0.01) < 0.002, f"{sex}: troll hands not at knee")
    if sid in ("gnome", "halfling"):
        for sex in SEXES:
            h = per_sex[sex][0]
            need(abs(doc["proportion"][sex]["trunk_to_leg"] / ((h["neck_base"] - h["hip_joint"]) / h["hip_joint"])
                     - 1) < 0.12, f"{sex}: {sid} must stay proportionate (trunk/leg within 12% of a human's)")
    return p


def chart(docs, per_sex, presets, anth, path, sex="male"):
    """Front and side stick figures of the human and every species at true scale (each at its mid stature)."""
    order = ["human"] + list(docs)
    px = 200.0                                  # pixels per metre
    top = 40
    ground = top + 2.95 * px
    mids = {sid: sum(docs[sid]["stature"][sex]) / 2 for sid in docs}
    mids["human"] = 1.76
    W = 60 + sum(max(0.55 * mids[sid] * px, 120) + 20 for sid in order)
    Hpx = ground + 70
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{Hpx:.0f}" '
           f'font-family="sans-serif" font-size="11">',
           f'<rect width="100%" height="100%" fill="white"/>']
    for m in range(0, 30, 1):
        y = ground - m / 10 * px
        if m / 10 > 2.9:
            break
        out.append(f'<line x1="40" x2="{W-10}" y1="{y:.1f}" y2="{y:.1f}" stroke="#eee"/>')
        if m % 5 == 0:
            out.append(f'<text x="5" y="{y+4:.1f}" fill="#888">{m/10:.1f} m</text>')
    h0 = human(presets, anth, sex)
    cursor = 60.0
    for sid in order:
        if sid == "human":
            fr = dict(h0)
            fr["spine_arc"] = h0["neck_base"] - h0["hip_joint"]
            fr["shoulder_forward"] = fr["neck_forward"] = 0.0
            fr["fingertip"] = h0["shoulder_joint"] - h0["upper_arm"] - h0["forearm"] - h0["hand"]
            H = 1.76
            kyph = lord = 0.0
            label = "human 7.7h"
        else:
            fr = per_sex[sid][sex][1]["fr"]
            lo, hi = docs[sid]["stature"][sex]
            H = (lo + hi) / 2
            kyph, lord = docs[sid]["spine"]["kyphosis_deg"], docs[sid]["spine"]["lordosis_deg"]
            label = f"{sid} {fr['heads']:.1f}h"
        width = max(0.55 * H * px, 120)
        cx = cursor + 0.20 * H * px + 10          # front view centre
        sx = cursor + 0.45 * H * px + 10          # side view x of the hip
        cursor += width + 20

        def Y(f):
            return ground - f * H * px

        def X(m):
            return m * H * px
        hip_x = 0.30 * fr["hip_width"]
        sh_x = 0.40 * fr["shoulder_width"]
        s = []
        # front: legs
        for d in (-1, 1):
            s.append(f'<polyline points="{cx+d*X(hip_x):.1f},{Y(fr["hip_joint"]):.1f} {cx+d*X(hip_x):.1f},'
                     f'{Y(fr["knee_joint"]):.1f} {cx+d*X(hip_x):.1f},{Y(fr["ankle_joint"]):.1f} '
                     f'{cx+d*X(hip_x+0.01):.1f},{Y(0):.1f}" fill="none" stroke="#335" stroke-width="3"/>')
            # arms hanging 8 degrees out
            a = math.radians(8)
            x0, y0 = cx + d * X(sh_x), Y(fr["shoulder_joint"])
            pts = [(x0, y0)]
            acc = 0.0
            for seg in ("upper_arm", "forearm", "hand"):
                acc += fr[seg]
                pts.append((x0 + d * X(acc * math.sin(a)), y0 + X(acc * math.cos(a))))
            s.append('<polyline points="' + " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in pts)
                     + '" fill="none" stroke="#a33" stroke-width="2.5"/>')
        # pelvis, shoulders, spine
        s.append(f'<line x1="{cx-X(hip_x):.1f}" x2="{cx+X(hip_x):.1f}" y1="{Y(fr["hip_joint"]):.1f}" '
                 f'y2="{Y(fr["hip_joint"]):.1f}" stroke="#335" stroke-width="3"/>')
        s.append(f'<line x1="{cx-X(sh_x):.1f}" x2="{cx+X(sh_x):.1f}" y1="{Y(fr["shoulder_joint"]):.1f}" '
                 f'y2="{Y(fr["shoulder_joint"]):.1f}" stroke="#335" stroke-width="3"/>')
        s.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{Y(fr["hip_joint"]):.1f}" y2="{Y(fr["neck_base"]):.1f}" '
                 f'stroke="#335" stroke-width="3"/>')
        hl = 1.0 - fr["chin"]
        s.append(f'<ellipse cx="{cx:.1f}" cy="{Y(1 - hl/2):.1f}" rx="{X(hl*0.36):.1f}" ry="{X(hl/2):.1f}" '
                 f'fill="#f3e1d0" stroke="#335" stroke-width="2"/>')
        s.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{Y(fr["neck_base"]):.1f}" y2="{Y(fr["chin"]):.1f}" '
                 f'stroke="#335" stroke-width="3"/>')
        # side view: spine curve (forward is to the left)
        at, tilt = spine_curve(fr["spine_arc"], kyph, lord)
        spts = []
        for j in range(11):
            z, y = at(j / 10)
            spts.append((sx - X(y), Y(fr["hip_joint"] + z)))
        s.append('<polyline points="' + " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in spts)
                 + '" fill="none" stroke="#353" stroke-width="3"/>')
        s.append(f'<polyline points="{sx:.1f},{Y(fr["hip_joint"]):.1f} {sx:.1f},{Y(fr["knee_joint"]):.1f} '
                 f'{sx:.1f},{Y(fr["ankle_joint"]):.1f} {sx-X(fr["foot"]*0.75):.1f},{Y(0):.1f}" fill="none" '
                 f'stroke="#353" stroke-width="3"/>')
        shx = sx - X(fr["shoulder_forward"])
        s.append(f'<line x1="{shx:.1f}" x2="{shx:.1f}" y1="{Y(fr["shoulder_joint"]):.1f}" '
                 f'y2="{Y(fr["fingertip"]):.1f}" stroke="#a33" stroke-width="2.5"/>')
        nx = sx - X(fr["neck_forward"])
        s.append(f'<line x1="{nx:.1f}" x2="{nx-X(0.01):.1f}" y1="{Y(fr["neck_base"]):.1f}" '
                 f'y2="{Y(fr["chin"]+hl*0.25):.1f}" stroke="#353" stroke-width="3"/>')
        s.append(f'<ellipse cx="{nx-X(0.02):.1f}" cy="{Y(1 - hl/2):.1f}" rx="{X(hl*0.42):.1f}" ry="{X(hl/2):.1f}" '
                 f'fill="#e0ecd8" stroke="#353" stroke-width="2"/>')
        # joint ticks
        for key in ("ankle_joint", "knee_joint", "hip_joint", "shoulder_joint", "chin"):
            s.append(f'<line x1="{cx-40:.1f}" x2="{cx-30:.1f}" y1="{Y(fr[key]):.1f}" y2="{Y(fr[key]):.1f}" '
                     f'stroke="#999"/>')
        s.append(f'<text x="{cx-30:.1f}" y="{ground+18:.1f}">{label}</text>')
        s.append(f'<text x="{cx-30:.1f}" y="{ground+32:.1f}" fill="#555">{H:.2f} m hip {fr["hip_joint"]:.2f}</text>')
        tl = (fr["neck_base"] - fr["hip_joint"]) / fr["hip_joint"]
        s.append(f'<text x="{cx-30:.1f}" y="{ground+46:.1f}" fill="#555">trunk/leg {tl:.2f}</text>')
        out += s
    out.append(f'<line x1="40" x2="{W-10}" y1="{ground:.1f}" y2="{ground:.1f}" stroke="#333"/>')
    out.append(f'<text x="45" y="{top-15}" font-size="13">humanform species ({sex}), true scale, front and side '
               f'(forward = left); red = hanging arm</text>')
    out.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="assert only, write nothing")
    ap.add_argument("--chart", help="write an SVG of every species beside the human")
    args = ap.parse_args()
    presets, anth = _load()
    docs, per = {}, {}
    problems = []
    for sid, spec in SPECIES.items():
        doc, per_sex = species_doc(sid, spec, presets, anth)
        problems += check(sid, doc, per_sex, presets)
        docs[sid], per[sid] = doc, per_sex
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print(f"{'species':9} {'sex':6} {'H m':>11} {'heads':>5} {'hip':>6} {'trunk':>6} {'tr/leg':>6} {'US/LS':>5} "
          f"{'reach':>6} {'H_pre m':>11}")
    for sid, doc in docs.items():
        for sex in SEXES:
            pr = doc["proportion"][sex]
            st = doc["stature"][sex]
            pre = doc["pre_warp"]["stature"][sex]
            print(f"{sid:9} {sex:6} {st[0]:.2f}-{st[1]:.2f} {doc['heads']['any'][0]:5.1f} {pr['hip_joint']:6.3f} "
                  f"{pr['trunk']:6.3f} {pr['trunk_to_leg']:6.2f} {pr['upper_to_lower_segment']:5.2f} "
                  f"{pr['fingertip_above_knee']:6.3f} {pre[0]:.2f}-{pre[1]:.2f}")
    hm = docs["elf"]["proportion"]
    for sex in SEXES:
        h = hm[sex]["human"]
        print(f"{'human':9} {sex:6} {'':11} {1/(1-0.87):5.1f} {h['hip_joint']:6.3f} {h['trunk']:6.3f} "
              f"{h['trunk_to_leg']:6.2f} {h['upper_to_lower_segment']:5.2f} {h['fingertip_above_knee']:6.3f}")
    if not args.check:
        os.makedirs(OUT_DIR, exist_ok=True)
        for sid, doc in docs.items():
            with open(os.path.join(OUT_DIR, f"{sid}.json"), "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2)
                fh.write("\n")
        print("wrote", len(docs), "species into", OUT_DIR)
    if args.chart:
        chart(docs, per, presets, anth, args.chart)
        print("chart:", args.chart)


if __name__ == "__main__":
    main()
