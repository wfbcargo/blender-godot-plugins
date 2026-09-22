"""Species design: turn what someone can state about a creature - or read off concept art - into a humanform
species preset (schema humanform-species/1), with the numbers made consistent and the gaps filled by laws.

    from humanform import species_design as sd
    r = sd.solve({"stature": 1.3, "heads": 5, "upper_to_lower": 1.5, "rhizomelic": 0.35, "build": "stocky"})
    r["knobs"], r["given"], r["derived"], r["contradictions"]
    preset = sd.design(id="dwarf", **r["knobs"], look={...}, report=r)
    print(sd.explain(preset))

Standard library only, no bpy: it runs inside Blender and out (scripts/derive_species.py is its CLI). The method
it serves is references/species-design.md.

**The body model.** Everything is in *human units*: the realistic preset's mean body for the sex, stature 1. A
species stacks the same segments with a length factor each - foot height, shin, thigh, the spine arc (bent by
the hunch and sway), the neck, then a head scaled so the stack is `heads` heads tall - and every ratio is its
segment over the stack's total. Joint heights, segment lengths, the trunk and the head count therefore agree by
construction, and `check()` proves it for every preset `design()` returns.

**The knobs** (`KNOBS`): each has a plain meaning, a unit, the human default and a valid range; `design()` refuses
a value outside it with the range in the message. **The observables** (`OBSERVABLES`) are what a person states or
measures on a picture; `solve()` turns any subset into knobs, filling the rest from the laws:

- **Head allometry.** Head length grows slower than stature: `head ~ H^b`. Within adults b = 0.30 (ANSUR II,
  measured here: vertex-to-tragion 0.24/0.29, head length 0.33/0.36, menton-sellion 0.41/0.42, male/female, from
  the survey's covariance). Across growth b = 0.55 (head canon 5.6-5.7 heads at 2 years, 7.5-7.6 at 15, at WHO
  statures 0.87 and 1.65 m: Pavlovic et al. 2024, Appl. Sci. 14:7185). So a small *proportionate* body reads
  big-headed by law (a 1.0 m one is ~6 heads), and a giant reads small-headed (2.65 m is ~10 heads). The
  effective stature is the trunk-matched human's for a disproportionate body (a dwarf's head is its trunk's).
- **Mass and build are two things.** *Mass* is volume, always: the pre-warp human's mass (its BMI at its
  stature) times each segment's share of body mass (de Leva 1996) times its length factor and its girth squared,
  the head cubed. That is what gait and loads use, and it is square-cube by construction. The *build* - how
  thick a body is for its length - follows the **adult build law** (GIRTH_LAW): among adults BMI does not vary
  with stature (ANSUR II, measured here: weight ~ H^2.00 in men, corr(BMI, H) +0.002; pygmy adults at 1.42-1.55
  m have BMI 20.5-21), because every girth grows only as H^0.36-0.58 at a fixed BMI. A short adult is therefore
  thicker for his length than a tall one, not a geometric shrink: a body shrunk from its pre-warp human by s
  takes each girth by s^a (a from ANSUR per region), so a 1 m body of an average build keeps an adult's BMI
  (~24) instead of a four-year-old's (~15, what a geometric shrink gives). A body scaled *up* keeps its shape
  (isometric: BMI grows with H, the square-cube), and above a human's mass its limbs add **support girth**:
  limb bone circumference grows as M^0.364 against a geometric M^0.333 across tetrapods (Campione & Evans
  2012), steeper in large mammals (Christiansen 1999; McMahon 1975), so a limb takes (M / M_human)^SUPPORT_EXP.
  `design` reports each limb's girth over its length against the adult band for its stature and build
  (`limb_band`, LIMB_BAND) and warns on stick limbs and a child-light BMI.
- **Proportionate vs disproportionate.** A body whose trunk-to-leg and arm-to-leg ratios are within 12% of a
  human's is *proportionate* (a small or large person: pituitary short stature, a child's body, a giant); outside
  it is *disproportionate* (achondroplasia's long trunk on short limbs). It picks the head law's effective
  stature and the pre-warp human's basis (head for proportionate, trunk for disproportionate).
- **Reach landmarks.** Hanging fingertips sit at 0.36 H on a human, about mid-thigh. `fingertips_at` names a
  landmark on the species' own body ("knee", "mid_thigh", "crotch", "mid_shin", "hip", "ankle", optionally
  "+0.05"), and the arm is solved to land there. By default arms scale with the legs (human arm-to-leg).
"""

from __future__ import annotations

import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(ROOT, "data")
SCHEMA = "humanform-species/1"
SEXES = ("female", "male")
ANSUR_STATURE = (1.45, 1.95)        # roughly ANSUR II's p1 female .. p99 male: where a pre-warp human fits well
LUMBAR_SHARE = 0.4                  # of the spine arc, hip joint up; the rest is thoracic
PROPORTIONATE = 0.12                # trunk/leg and arm/leg within this share of a human's

HEAD_B_ADULT = 0.30                 # head length ~ H^b among adults (ANSUR II covariance, see the docstring)
HEAD_B_GROWTH = 0.55                # across growth, 2 to 15 years (Pavlovic et al. 2024 with WHO statures)
HEAD_ADULT_FROM = 1.45              # below this effective stature the growth exponent applies
REF_STATURE = {"female": 1.628, "male": 1.756}     # ANSUR II means, the human the ratios describe
MASS_SHARE = {                      # de Leva 1996 (J Biomech 29:1223), % body mass per segment (one side for limbs)
    "female": {"head": 6.68, "trunk": 42.57, "upper_arm": 2.55, "forearm": 1.38, "hand": 0.56,
               "thigh": 14.78, "shin": 4.81, "foot": 1.29},
    "male": {"head": 6.94, "trunk": 43.46, "upper_arm": 2.71, "forearm": 1.62, "hand": 0.61,
             "thigh": 14.16, "shin": 4.33, "foot": 1.37},
}

# The adult build law (ANSUR II, scripts/derive_girth_law.py; men / women): circumference ~ H^a at a fixed BMI.
# thigh 0.61/0.62, calf 0.52/0.58 -> legs; biceps 0.47/0.51, forearm 0.55/0.56 -> arms; neck 0.33/0.38; chest
# depth 0.58/0.52 and breadth 0.56/0.54 -> torso. a = 1 would be geometric: it is ~0.5, which is why BMI is
# stature-free among adults (mass ~ L x girth^2 ~ H^(1 + 2a) ~ H^2). A body shrunk by s from its pre-warp human
# takes each girth by s^a instead of s.
GIRTH_LAW = {"legs": 0.58, "arms": 0.52, "neck": 0.36, "torso": 0.55}
# breadths likewise (ANSUR II, men / women): bideltoid ~H^0.51/0.51, hip breadth ~H^0.69/0.66 at a fixed BMI. And
# the hips carry the thighs: a hip breadth never narrower, against the pre-warp human's, than the thighs' girth
# (a shrunk body's thighs, thickened by the law, met below the crotch and read as fused on the first gnome)
WIDTH_LAW = {"shoulder_width": 0.51, "hip_width": 0.68}
# how much wider than the thighs' girth factor the hips are held on a shrunk body: the thighs of a short body are
# thick for their length and meet sooner than a human's at the same hip breadth (a halfling at 1.00x came out with
# its crotch 6 cm low, then its pelvis spread 3.4 cm past its hip target to lift it)
HIPS_CARRY = 1.06
# support girth for a big body: limb circumference ~ M^0.364 across tetrapods (Campione & Evans 2012, 1/2.749)
# against a geometric M^0.333, steeper in large mammals (Christiansen 1999; bovids ~M^0.10 over geometric,
# McMahon 1975's elastic similarity): a limb above a human's mass takes (M / M_human)^SUPPORT_EXP
SUPPORT_EXP = 0.06
# each limb's circumference over its joint-to-joint length among adults (ANSUR II, derive_girth_law.py):
# c/L at the sex's mean stature and BMI, its exponents with stature and BMI, and the residual's 5th and 95th
# percentiles (the spread at one stature and BMI). ANSUR's biceps and forearm girths are flexed.
LIMB_BAND = {
    "male": {"H": 1.756, "bmi": 27.7,
             "thigh": (1.534, -0.58, 0.61, 0.904, 1.107), "shin": (0.940, -0.72, 0.44, 0.915, 1.089),
             "upper_arm": (0.987, -0.58, 0.55, 0.907, 1.110), "forearm": (1.160, -0.51, 0.36, 0.915, 1.097)},
    "female": {"H": 1.628, "bmi": 25.5,
               "thigh": (1.629, -0.50, 0.59, 0.910, 1.094), "shin": (0.928, -0.64, 0.39, 0.901, 1.110),
               "upper_arm": (0.916, -0.56, 0.62, 0.913, 1.095), "forearm": (1.097, -0.54, 0.35, 0.914, 1.098)},
}
LIMB_REGION = {"thigh": ("legs", "femur"), "shin": ("legs", "tibia"), "upper_arm": ("arms", "humerus"),
               "forearm": ("arms", "forearm")}
# chest depth over chest breadth (ANSUR II): men 0.877 (p5 0.754, p95 1.004), women 0.918 (0.798-1.045); it grows
# with BMI^0.34 and not with stature. A barrel chest (`barrel_chest` 1) is a ribcage as deep as it is broad and a
# little more: BARREL_DB [folklore for a dwarf; the clinical barrel chest is an AP diameter near the transverse]
# humancheck's limb girths against ANSUR's: its upper arm and forearm are relaxed (ANSUR's flexed), its thigh just
# under the crotch, its lengths joint to joint on the rig - measured on fitted MPFB humans (the pre-warp bodies of
# the species builds): mesh c/L over limb_band's at the same stature and BMI
MESH_CAL = {"thigh": 0.99, "shin": 1.0, "upper_arm": 1.12, "forearm": 0.78, "chest_depth_to_breadth": 0.81}
CHEST_DB = {"male": 0.877, "female": 0.918}
BARREL_DB = 1.08
RIBCAGE_SHARE = 0.5          # of the trunk's mass the ribcage's depth and breadth scale (de Leva's upper trunk and
                             # half the middle)

SOURCES = {
    "ansur": "ANSUR II (US Army 2012, Penn State OpenLab 2017): data/anthropometry.json",
    "growth": ("Pavlovic et al. 2024, Research on Children's Body Proportions: the canon of head length to body "
               "height, 2-15 years (Appl. Sci. 14:7185) - https://www.mdpi.com/2076-3417/14/16/7185"),
    "de_leva": "de Leva 1996, Adjustments to Zatsiorsky-Seluyanov's segment inertia parameters, J Biomech 29:1223",
    "achondroplasia": ("Merker et al. 2018, Development of body proportions in achondroplasia (Am J Med Genet A "
                       "176:1819): adult legs ~50% and arm span ~35% shorter, sitting height mildly reduced - "
                       "https://onlinelibrary.wiley.com/doi/10.1002/ajmg.a.40356"),
    "segment_ratio": ("BMN 111 (vosoritide) trial statistical plan: upper-to-lower segment ratio 1.9-2.1 in "
                      "achondroplasia, ~1.0 average - "
                      "https://cdn.clinicaltrials.gov/large-docs/66/NCT03197766/SAP_001.pdf"),
    "large_gait": ("Large-animal gait: duty factor rises with size, no aerial phase above a few hundred kg - "
                   "https://pmc.ncbi.nlm.nih.gov/articles/PMC8214834/"),
    "dnd": "D&D 5e Player's Handbook (2014), 'Height and Weight' table",
    "eyes": ("Bekerman et al. 2014, Variations in eyeball diameters of the healthy adults (J Ophthalmol "
             "2014:503645): ~24 mm adult axial length; ~16.5-17 mm at birth"),
    "design": "docs/improvements/08-fantasy-species.md (research, 2026-09-21)",
    "build_law": ("ANSUR II measured here (scripts/derive_girth_law.py): weight ~ H^2.00 (men), 2.19 (women); "
                  "corr(BMI, stature) +0.002 / +0.054; circumferences ~ H^0.33-0.62 at a fixed BMI"),
    "benn": ("Benn 1971 and NHANES: W/H^2 is uncorrelated with height in adults (r ~ -0.03), the Benn exponent "
             "2.0-2.2 - https://pmc.ncbi.nlm.nih.gov/articles/PMC11611441/"),
    "pygmy": ("Baka and Efe adults, 1.42-1.55 m: BMI 20.5-21.3, >85% in the normal range - "
              "https://citeseerx.ist.psu.edu/document?doi=b94845323982dd59cb424861df2106bc47b700f9"),
    "support": ("Campione & Evans 2012, BMC Biol 10:60: body mass ~ (humerus + femur circumference)^2.749 across "
                "tetrapods (C ~ M^0.364) - https://pmc.ncbi.nlm.nih.gov/articles/PMC3403949/; Christiansen 1999, "
                "J Zool 249:1 (large mammals depart from geometric similarity more than small); McMahon 1975, Am "
                "Nat 109:547 (elastic similarity in ungulates)"),
}

# name: (unit, human default, (lo, hi), meaning)
KNOBS = {
    "heads":          ("heads", None, (3.0, 10.5), "stature over head length (vertex to chin); None = the allometric law"),
    "trunk_scale":    ("x", 1.0, (0.6, 1.6), "spine arc, hip joint to neck base, against a human's"),
    "leg_scale":      ("x", 1.0, (0.4, 1.6), "hip joint to ankle, against a human's"),
    "leg_root_share": ("0-1", 0.0, (0.0, 1.0), "how much of the leg's change the femur takes beyond its share "
                                                "(rhizomelic: 0 even, 1 all of it)"),
    "arm_scale":      ("x", 1.0, (0.4, 1.8), "shoulder joint to wrist, against a human's"),
    "arm_root_share": ("0-1", 0.0, (0.0, 1.0), "the humerus's extra share of the arm's change"),
    "hand_scale":     ("x", 1.0, (0.5, 2.0), "hand length"),
    "foot_scale":     ("x", 1.0, (0.5, 2.0), "foot length (and the ankle's height)"),
    "neck_scale":     ("x", 1.0, (0.3, 2.5), "neck base to head base"),
    "shoulder_scale": ("x", 1.0, (0.6, 1.8), "shoulder breadth (bideltoid)"),
    "hip_scale":      ("x", 1.0, (0.6, 1.8), "hip breadth (and the hip-to-crotch drop)"),
    "girth_legs":     ("x", 1.0, (0.5, 2.0), "leg thickness, beyond the pre-warp human's own build"),
    "girth_arms":     ("x", 1.0, (0.5, 2.0), "arm thickness, likewise"),
    "girth_neck":     ("x", 1.0, (0.5, 2.0), "neck thickness"),
    "girth_torso":    ("x", 1.0, (0.5, 2.0), "trunk depth"),
    "girth_forearm":  ("x", 1.0, (0.6, 1.8), "forearm thickness over the arm's (heavy forearms)"),
    "chest_depth":    ("x", 1.0, (0.7, 1.6), "ribcage depth, front to back, beyond the torso's girth (a barrel "
                                             "chest)"),
    "chest_breadth":  ("x", 1.0, (0.7, 1.5), "ribcage breadth beyond the torso's girth and the shoulders' spread"),
    "hunch_deg":      ("deg", 0.0, (-15.0, 60.0), "extra thoracic kyphosis over a human's (forward bend)"),
    "sway_deg":       ("deg", 0.0, (-20.0, 30.0), "extra lumbar lordosis over a human's (backward bend)"),
    "build_bmi":      ("kg/m2", 24.5, (15.0, 45.0), "BMI of the pre-warp human the body is fitted from"),
    "waist_to_hip":   ("ratio", None, (0.6, 1.2), "waist over hip circumference; None = the human's per sex"),
    "tol_scale":      ("x", 1.3, (1.0, 3.0), "the realistic preset's tolerances times this"),
}

BUILDS = {   # word: (pre-warp BMI centre, its range)
    "scrawny": (19.0, (16.5, 21.5)), "slender": (20.0, (18.0, 22.5)), "lean": (21.0, (18.5, 23.5)),
    "average": (24.5, (21.0, 28.0)), "athletic": (25.0, (22.5, 28.0)), "muscular": (27.0, (24.0, 30.5)),
    "stocky": (28.0, (25.0, 32.0)), "heavy": (32.0, (28.0, 37.0)), "massive": (36.0, (31.0, 42.0)),
    # humanform.sheet.BUILDS' own words, so [body] build and [body.species] build take one vocabulary (a drow's
    # [body] build = "slender" was refused only at the body stage, 2026-09-21); sheet.BUILD_ALIASES maps the
    # words above that sheet has no build for onto one of its own
    "slim": (20.5, (18.5, 22.5)), "curvy": (25.5, (23.0, 28.5)), "soft": (27.0, (24.0, 30.5)),
}
BUILD_WORDS = tuple(sorted(BUILDS))
SIZE_WORDS = {"tiny": 0.7, "small": 0.85, "short": 0.75, "human": 1.0, "long": 1.35, "big": 1.22, "large": 1.22,
              "huge": 1.4, "thin": 0.85, "thick": 1.2, "slender": 0.86, "stout": 1.15, "heavy": 1.2}

# observable: (unit, meaning, how to read it off a picture)
OBSERVABLES = {
    "stature":        ("m", "standing height, floor to vertex, hunch included; a number, [lo, hi] or per sex",
                       "against a known object, or a stated height"),
    "heads":          ("heads", "stature / head length (vertex to chin)", "stack the head down the figure"),
    "hip_fraction":   ("H", "hip joint height / stature (alias leg_fraction)", "the greater trochanter, the "
                                                                                "widest point of the hips"),
    "crotch_fraction": ("H", "crotch height / stature", "the inseam; the easiest leg landmark on a picture"),
    "upper_to_lower": ("ratio", "(stature - crotch) / crotch, the clinical segment ratio", "from the crotch"),
    "trunk_to_leg":   ("ratio", "(neck base - hip joint) / hip joint", "C7 to trochanter over trochanter height"),
    "fingertips_at":  ("landmark", "where hanging fingertips reach: knee, mid_thigh, crotch, mid_shin, hip, ankle, "
                                   "optionally '+0.05' (H); or a fraction of H", "the arms hanging straight"),
    "arm_to_leg":     ("ratio", "shoulder-to-wrist over hip-to-ankle", "joint to joint on a T or A pose"),
    "shoulder_to_hip": ("ratio", "shoulder breadth over hip breadth", "the widest points across a front view"),
    "shoulder_heads": ("heads", "shoulder breadth in head lengths", "lay the head across the shoulders"),
    "build":          ("word", "one of BUILDS: the pre-warp human's BMI", "how fat or muscled it reads"),
    "bmi":            ("kg/m2", "the finished body's BMI; girth is solved to reach it", "stated weight / H^2"),
    "mass_kg":        ("kg", "the finished body's mass at mid stature; girth is solved to reach it", "stated"),
    "hunch_deg":      ("deg", "extra forward curve of the upper back", "the angle between the lower and upper "
                                                                         "back lines on a side view, minus ~0"),
    "sway_deg":       ("deg", "extra hollow of the lower back", "side view"),
    "rhizomelic":     ("0-1", "limbs shortened at the root (femur, humerus) - the dwarf's pattern",
                       "upper arm short against the forearm"),
    "proportionate":  ("bool", "a scaled person: trunk/leg and arm/leg as a human's", ""),
    "hands":          ("x|word", "hand length (big, small, ...)", "hand against the face (a human's ~0.75 face)"),
    "feet":           ("x|word", "foot length", "foot against the head length (a human's ~1.2)"),
    "neck":           ("x|word", "neck length (long, short)", "chin to shoulder line"),
    "girth":          ("x|word|dict", "limb thickness beyond the build (slender, stout; or per region: legs, "
                                      "arms, neck, torso, forearm)", ""),
    "forearms":       ("x|word", "forearm thickness over the arm's (thick, stout, heavy = 1.2)",
                       "the forearm's widest against the upper arm's"),
    "chest_depth_to_breadth": ("ratio", "ribcage depth over breadth at the chest (a human man 0.88, woman 0.92; "
                                        "a barrel chest ~1.0-1.1)", "side-view depth over front-view breadth "
                                                                     "under the armpits"),
    "barrel_chest":   ("0-1", f"0 a human's chest, 1 a barrel: depth over breadth {BARREL_DB}", "a side view"),
}

LANDMARKS = {"ankle": lambda f: f["ankle_joint"], "mid_shin": lambda f: (f["ankle_joint"] + f["knee_joint"]) / 2,
             "knee": lambda f: f["knee_joint"], "mid_thigh": lambda f: (f["knee_joint"] + f["crotch"]) / 2,
             "crotch": lambda f: f["crotch"], "hip": lambda f: f["hip_joint"]}

# Every drawn part of the body (08, "Every drawn part"): a species body carries the whole human anatomy. Each part
# sits on a host whose warp factor it follows, raised to an exponent (1: in proportion to its host); `skin` names
# the skin.REGIONS entry that draws it, so a part the description says is absent turns its region off - and
# nothing else ever does. part: (host, exponent, skin region or None, what it is)
ANATOMY = {
    "nipples":   ("chest", 1.0, "nipple", "nipples and areolae; areola diameter in proportion to chest breadth"),
    "breasts":   ("chest", 1.0, None, "breast mass (follow-through flesh zone)"),
    "navel":     ("torso", 1.0, None, "the umbilicus"),
    "genitals":  ("pelvis", 1.0, "genital", "external genitals, in proportion to pelvis breadth (opt-in in a build)"),
    "buttocks":  ("pelvis", 1.0, None, "buttock mass (flesh zone)"),
    "belly":     ("torso", 1.0, None, "belly mass (flesh zone)"),
    "lips":      ("head", 1.0, "lips", "the red of the lips"),
    "eyes":      ("head", 0.53, None, "eyeballs: they grow slower than the head (~17 mm at birth, ~24 adult, while "
                                      "the head roughly doubles)"),
    "lashes":    ("head", 1.0, None, "eyelashes"),
    "brows":     ("head", 1.0, None, "eyebrows"),
    "teeth":     ("head", 1.0, None, "teeth"),
    "tongue":    ("head", 1.0, None, "tongue"),
    "ears":      ("head", 1.0, None, "ears (head features such as ears_pointed add to them, never replace them)"),
    "nails":     ("hand", 1.0, "nail", "finger and toe nails"),
    "knuckles":  ("hand", 1.0, "knuckle", "knuckle skin"),
    "palms":     ("hand", 1.0, "palm", "palm skin"),
    "soles":     ("foot", 1.0, "sole", "sole skin"),
    "knees":     ("leg", 1.0, "knee", "knee skin"),
    "elbows":    ("arm", 1.0, "elbow", "elbow skin"),
    "body_hair": ("body", 1.0, None, "body hair coverage (fur is added over the same maps)"),
    "fur": ("body", 1.0, None, "fur: a coverage map on hm08 (humanform.fur), drawn in Godot as offset shells"),
}
# Parts a human does not have, so no preset is asked to keep or declare them. One is expected only when the
# look asks for it (`look["fur"]`) - and then the build must carry it: `species.inventory` fails a body whose
# species says it has fur and does not.
ANATOMY_OPTIONAL = ("fur",)
# parts of a part, which a description may lack on their own (a tail in place of legs keeps the fingernails):
# declaring one absent leaves its whole part, and that part's skin region, on
ANATOMY_SUBPARTS = {"nails.toes": "nails", "nails.fingers": "nails"}
ANATOMY_SCALE = (0.3, 3.0)
BMI_PLAUSIBLE = (18.0, 40.0)        # a derived (unstated) BMI outside this is warned about in solve(): see there

HEIGHTS = ("ankle_joint", "knee_joint", "crotch", "hip_joint", "shoulder_joint", "chin")
LENGTHS = ("upper_arm", "forearm", "hand", "foot", "thigh", "shin", "shoulder_width", "hip_width")


class DesignError(ValueError):
    """A knob or observable out of range, or a preset whose numbers disagree."""


# ------------------------------------------------------------------------------------------------ the human
_CACHE = {}


def _sibling(name):
    """A module beside this one, whether this file was imported in its package or loaded alone (character-pipeline
    loads it by path to check a spec outside Blender)."""
    import importlib
    import importlib.util
    import sys
    if __package__:
        return importlib.import_module("." + name, __package__)
    key = "_hf_sd_" + name
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, os.path.join(HERE, name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[key] = mod
        spec.loader.exec_module(mod)
    return sys.modules[key]


def _luma(c):
    """Rec. 709 luma of an sRGB tone (0..1), in linear light."""
    lin = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


# the palest skin tone to hold under lookdev's midday look, measured (linear luma): the elf drawn at 0.543 read 0.16%
# of its figure past diffuse white, drawn at 0.592 read 1.68% (limit 1%) - the sun-facing forearms and feet tops of a
# bare slim body. The palest shipped human [0.90, 0.78, 0.68] (0.606) was the cap before, and did not hold. 0.55 is
# about [0.87, 0.74, 0.64]
PALEST_SKIN_LUMA = 0.55


def _json(name):
    if name not in _CACHE:
        with open(os.path.join(DATA, name), encoding="utf-8") as fh:
            _CACHE[name] = json.load(fh)
    return _CACHE[name]


def _names(path, pattern):
    try:
        with open(path, encoding="utf-8") as fh:
            m = re.search(pattern, fh.read(), re.S)
    except OSError:
        return ""
    return m.group(1) if m else ""


def face_shapes():
    return tuple(re.findall(r'"(\w+)"', _names(os.path.join(HERE, "sheet.py"), r"FACE_SHAPES = \(([^)]*)\)")))


def skin_regions():
    block = _names(os.path.join(HERE, "skin.py"), r"\nREGIONS = \{(.*?)\n\}")
    return tuple(re.findall(r'^\s+"(\w+)":', block, re.M))


def human(sex):
    """The realistic mean body for a sex, as fractions of H (stature 1 in human units)."""
    key = ("human", sex)
    if key in _CACHE:
        return _CACHE[key]
    presets = _json("presets.json")
    r = presets["presets"]["realistic"]["ratios"]
    v = _json("anthropometry.json")["sexes"][sex]["variables"]

    def t(k):
        return r[k].get("any") or r[k][sex]

    b = {k: t(k)[0] for k in r}
    b["tol"] = {k: t(k)[1] for k in r}
    b["neck_base"] = v["cervicaleheight"]["ratio_mean"]
    b["head_base"] = 1.0 - v["tragiontopofhead"]["ratio_mean"] - 0.01     # as landmarks.from_measurements
    b["heads"] = 1.0 / (1.0 - b["chin"])
    b["fingertip"] = b["shoulder_joint"] - b["upper_arm"] - b["forearm"] - b["hand"]
    b["spine_arc"] = b["neck_base"] - b["hip_joint"]
    d = presets["presets"]["realistic"]["derived"]
    b["derived"] = {k: (d[k].get("any") or d[k][sex]) for k in ("shoulder_to_hip_width", "waist_to_hip_circ")}
    _CACHE[key] = b
    return b


# ------------------------------------------------------------------------------------------------ the laws
def allometric_head(h_eff, sex):
    """Head length (m) of a body whose effective stature is `h_eff`, by the head-allometry law."""
    ref_h = REF_STATURE[sex]
    ref_head = (1.0 - human(sex)["chin"]) * ref_h
    if h_eff >= HEAD_ADULT_FROM:
        return ref_head * (h_eff / ref_h) ** HEAD_B_ADULT
    at = ref_head * (HEAD_ADULT_FROM / ref_h) ** HEAD_B_ADULT
    return at * (h_eff / HEAD_ADULT_FROM) ** HEAD_B_GROWTH


def allometric_heads(stature, sex, trunk_ratio=1.0):
    """Heads tall by the law, for a body of `stature`; `trunk_ratio` is its trunk fraction over a human's when it
    is disproportionate (the head follows the trunk-matched human), 1 when proportionate."""
    return stature / allometric_head(stature * trunk_ratio, sex)


def is_proportionate(prop):
    """Whether a body's trunk/leg and arm/leg sit within PROPORTIONATE of a human's."""
    return all(abs(prop[k] / prop["human"][k] - 1.0) <= PROPORTIONATE for k in ("trunk_to_leg", "arm_to_leg"))


# ------------------------------------------------------------------------------------------------ the model
def spine_curve(arc, kyph, lord, n=200):
    """(z, y) along a spine of arc length `arc`, the lumbar span bent back `lord` degrees and the thoracic span
    forward `kyph`, each spread evenly. Returns a function of arc fraction s (0 hip, 1 neck base), and the tilt
    at the top (radians)."""
    pts = [(0.0, 0.0)]
    z = y = 0.0
    lk, tk = math.radians(lord), math.radians(kyph)
    for i in range(n):
        s = (i + 0.5) / n
        phi = -lk * s / LUMBAR_SHARE if s < LUMBAR_SHARE else -lk + tk * (s - LUMBAR_SHARE) / (1 - LUMBAR_SHARE)
        z += math.cos(phi) * arc / n
        y += math.sin(phi) * arc / n
        pts.append((z, y))

    def at(s):
        i = min(int(s * n), n - 1)
        f = s * n - i
        (z0, y0), (z1, y1) = pts[i], pts[i + 1]
        return z0 + (z1 - z0) * f, y0 + (y1 - y0) * f
    return at, tk - lk


def _split(total, root_share, a_len, b_len):
    change = (1.0 - total) * (a_len + b_len)
    share = a_len / (a_len + b_len)
    share += root_share * (1.0 - share)
    return 1.0 - change * share / a_len, 1.0 - change * (1.0 - share) / b_len


# What makes a small, big-headed body read as an adult rather than a child: against its head length, a child's
# neck is short (chin to shoulder joints 0.25 of the head at 3 years, 0.35 at 6; an adult's 0.57), its hands and
# feet small (hand 0.55 / 0.65, adult 0.85; foot 0.8 / 0.9, adult 1.2), and its shoulders narrow (bideltoid 1.4 /
# 1.55 head lengths, adult 2.2) - childhood proportions from Pavlovic et al. 2024 and WHO growth statures, the
# adult from the realistic preset. A big head alone is a species trait; a big head with a child's neck, hands and
# shoulders is a toddler. metric: (knob that moves it, design floor, check floor, what it measures). `design`
# raises a knob to its design floor (the check's floor plus a margin, so the built body clears the check) and
# says so in the preset's `design.adult_cues`; `species.reads_adult` and humancheck's `reads_adult` fail a body
# under the check floor.
ADULT_CUES = {
    "neck_head": ("neck_scale", 0.37, 0.33, "neck (chin to the shoulder joints) over head length"),
    "hand_head": ("hand_scale", 0.72, 0.68, "hand length over head length"),
    "foot_head": ("foot_scale", 0.95, 0.90, "foot length over head length"),
    "shoulder_head": ("shoulder_scale", 1.90, 1.80, "bideltoid breadth over head length"),
}
ADULT_NECK_MAX = 0.68          # the long end of adult necks: past it a neck reads as a stretched one
ADULT_HEAD_FRACTION = 0.16     # a head this share of the stature or more (6.25 heads or fewer) asks for the cues


def cue_metrics(fr):
    """ADULT_CUES' metrics of a body's fractions (the ratios of a preset, or `body()["fr"]`)."""
    head = 1.0 - fr["chin"]
    return {"neck_head": (fr["chin"] - fr["shoulder_joint"]) / head, "hand_head": fr["hand"] / head,
            "foot_head": fr["foot"] / head, "shoulder_head": fr["shoulder_width"] / head}


def _adult_cues(k, heads, start=None):
    """Knobs with every ADULT_CUES metric at least its design floor on both sexes, and the neck at most
    ADULT_NECK_MAX: {knob: {"from", "to", "metric", "floor"}} for each one moved. A knob that cannot reach its
    floor inside its range stops at the range's end (the check then says so). `start` ({knob: value}, filled in
    here) remembers where a knob began across calls, so one raised earlier can come back down to its floor, never
    below where it began."""
    k = dict(k)
    moved = {}
    start = {} if start is None else start

    def worst(knob, v, metric, fn=min):
        kk = dict(k, **{knob: v})
        return fn(cue_metrics(body(kk, sex, heads)["fr"])[metric] for sex in SEXES)

    def bisect(knob, metric, target, lo, hi, fn):
        for _ in range(40):
            mid = (lo + hi) / 2
            if worst(knob, mid, metric, fn) >= target:
                hi = mid
            else:
                lo = mid
        return hi if fn is min else lo     # a floor's smallest knob that clears it, a ceiling's largest under it

    for _ in range(4):                      # a longer neck grows the head (heads are fixed): settle together
        for metric, (knob, floor, _, _) in ADULT_CUES.items():
            now = worst(knob, k[knob], metric)
            start.setdefault(knob, k[knob])
            if now < floor - 1e-6:
                hi = KNOBS[knob][2][1]
                new = hi if worst(knob, hi, metric) < floor else bisect(knob, metric, floor, k[knob], hi, min)
            elif now > floor + 0.01 and k[knob] > start[knob] + 1e-9:
                # raised on an earlier pass and overshot since (another cue or a solved length moved the stack):
                # back to the floor, never below where it started
                lo = start[knob]
                new = lo if worst(knob, lo, metric) >= floor else bisect(knob, metric, floor, lo, k[knob], min)
            else:
                continue
            moved.setdefault(knob, {"from": round(start[knob], 4), "metric": metric, "floor": floor})["to"] = round(new, 4)
            k[knob] = new
        if worst("neck_scale", k["neck_scale"], "neck_head", max) > ADULT_NECK_MAX:
            new = bisect("neck_scale", "neck_head", ADULT_NECK_MAX, KNOBS["neck_scale"][2][0], k["neck_scale"], max)
            moved.setdefault("neck_scale", {"from": round(k["neck_scale"], 4), "metric": "neck_head",
                                            "ceiling": ADULT_NECK_MAX})["to"] = round(new, 4)
            k["neck_scale"] = new
    return k, moved


def body(k, sex, heads):
    """One body in human units for a sex: {"u", "H", "fr", "factors"}."""
    h = human(sex)
    f_thigh, f_shin = _split(k["leg_scale"], k["leg_root_share"], h["thigh"], h["shin"])
    f_hum, f_fa = _split(k["arm_scale"], k["arm_root_share"], h["upper_arm"], h["forearm"])
    u = {"ankle_joint": h["ankle_joint"] * k["foot_scale"]}
    u["knee_joint"] = u["ankle_joint"] + h["shin"] * f_shin
    u["hip_joint"] = u["knee_joint"] + h["thigh"] * f_thigh
    arc = h["spine_arc"] * k["trunk_scale"]
    at, tilt = spine_curve(arc, k["hunch_deg"], k["sway_deg"])
    zs, ys = at((h["shoulder_joint"] - h["hip_joint"]) / h["spine_arc"])
    zn, yn = at(1.0)
    u["shoulder_joint"] = u["hip_joint"] + zs
    u["neck_base"] = u["hip_joint"] + zn
    base = u["neck_base"] + (h["head_base"] - h["neck_base"]) * k["neck_scale"] * math.cos(tilt / 2)
    head_h, above = 1.0 - h["chin"], 1.0 - h["head_base"]
    denom = head_h * heads - above
    if denom <= 0:
        raise DesignError(f"heads {heads} is too few for this body")
    g = base / denom
    Hs = base + above * g
    u["chin"] = Hs - head_h * g
    u["crotch"] = u["hip_joint"] - (h["hip_joint"] - h["crotch"]) * k["hip_scale"]
    u.update(upper_arm=h["upper_arm"] * f_hum, forearm=h["forearm"] * f_fa, hand=h["hand"] * k["hand_scale"],
             foot=h["foot"] * k["foot_scale"], thigh=h["thigh"] * f_thigh, shin=h["shin"] * f_shin,
             shoulder_width=h["shoulder_width"] * k["shoulder_scale"], hip_width=h["hip_width"] * k["hip_scale"])
    # the adult build law on the breadths (WIDTH_LAW): a body shrunk by s from its pre-warp human keeps an adult's
    # breadths for its size (s^a, not s), and its hips carry its thighs
    s = body_scale(u, Hs, sex, arc)
    wf = {"shoulder_width": k["shoulder_scale"], "hip_width": k["hip_scale"]}
    if s < 1.0:
        wf = {n: v * s ** (WIDTH_LAW[n] - 1.0) for n, v in wf.items()}
        wf["hip_width"] = max(wf["hip_width"], HIPS_CARRY * k["girth_legs"] * s ** (GIRTH_LAW["legs"] - 1.0))
    u["shoulder_width"] = h["shoulder_width"] * wf["shoulder_width"]
    u["hip_width"] = h["hip_width"] * wf["hip_width"]
    fr = {key: u[key] / Hs for key in HEIGHTS + LENGTHS + ("neck_base",)}
    fr["head_base"] = base / Hs
    fr["spine_arc"] = arc / Hs
    fr["shoulder_forward"], fr["neck_forward"] = ys / Hs, yn / Hs
    fr["heads"] = 1.0 / (1.0 - fr["chin"])
    fr["fingertip"] = fr["shoulder_joint"] - fr["upper_arm"] - fr["forearm"] - fr["hand"]
    factors = {"femur": f_thigh, "tibia": f_shin, "humerus": f_hum, "forearm": f_fa, "hand": k["hand_scale"],
               "foot": k["foot_scale"], "spine": k["trunk_scale"], "neck": k["neck_scale"], "head": g}
    return {"H": Hs, "fr": fr, "factors": factors, "widths": wf, "scale": s}


def body_scale(u, Hs, sex, arc):
    """How much a body (human units, stack height Hs) is scaled from its pre-warp human: by its head for a
    proportionate body, by its trunk for a disproportionate one (as `_pre_warp` with the inferred basis)."""
    h = human(sex)
    fr = {key: u[key] / Hs for key in ("ankle_joint", "crotch", "hip_joint", "neck_base", "chin")}
    leg = fr["hip_joint"]
    trunk_to_leg = (fr["neck_base"] - leg) / leg
    arm_to_leg = (u["upper_arm"] + u["forearm"]) / Hs / (leg - fr["ankle_joint"])
    hm = metrics(h)
    prop = (abs(trunk_to_leg / hm["trunk_to_leg"] - 1.0) <= PROPORTIONATE
            and abs(arm_to_leg / hm["arm_to_leg"] - 1.0) <= PROPORTIONATE)
    kf = ((1.0 - fr["chin"]) / (1.0 - h["chin"]) if prop
          else (arc / Hs) / h["spine_arc"])
    return 1.0 / (Hs * kf)


def metrics(fr, sex=None):
    """The observables a body shows (and, with `sex`, the human's beside them)."""
    leg = fr["hip_joint"]
    m = {"hip_fraction": leg, "crotch_fraction": fr["crotch"], "neck_base": fr["neck_base"],
         "trunk": fr["neck_base"] - leg, "trunk_to_leg": (fr["neck_base"] - leg) / leg,
         "upper_to_lower": (1.0 - fr["crotch"]) / fr["crotch"], "relative_sitting_height": 1.005 - fr["crotch"],
         "arm_to_leg": (fr["upper_arm"] + fr["forearm"]) / (leg - fr["ankle_joint"]),
         "arm_length": fr["upper_arm"] + fr["forearm"] + fr["hand"], "fingertip": fr["fingertip"],
         "fingertip_above_knee": fr["fingertip"] - fr["knee_joint"],
         "shoulder_to_hip": fr["shoulder_width"] / fr["hip_width"],
         "shoulder_heads": fr["shoulder_width"] / (1.0 - fr["chin"]), "heads": fr["heads"]}
    if sex:
        m["human"] = metrics(human(sex))
    return m


def _pre_warp(b, sex, basis):
    h = human(sex)
    if basis == "trunk":
        return b["fr"]["spine_arc"] / h["spine_arc"]
    return (1.0 - b["fr"]["chin"]) / (1.0 - h["chin"])


def law_scale(region, s):
    """The girth factor of a body region when the whole body is scaled by `s` from its pre-warp human: by the
    adult build law (GIRTH_LAW) s^a when it is shrunk, so a short adult keeps an adult's build; s (the shape
    kept, square-cube) when it is scaled up."""
    return s ** GIRTH_LAW[region] if (s < 1.0 and region in GIRTH_LAW) else s


def clamp_girth(region, scale, c):
    """The girth factor a pre-warp human clamped to ANSUR (fitted at the limit, then scaled whole by c) takes on top
    of the preset's, when the body is `scale` of the unclamped pre-warp human: the adult build law on the whole
    scale from the fit over the law on `scale` alone. species.py's warp applies the same (girth_law.scale)."""
    return law_scale(region, scale * c) / law_scale(region, scale)


def chest_spread(shoulder, torso):
    """How much the chest bone's breadth takes of broad shoulders beyond the torso's own girth (species.py's
    warp uses the same): half of it, as a square root, held to 0.8-1.25."""
    return min(1.25, max(0.8, math.sqrt(max(shoulder / max(torso, 1e-3), 1e-3))))


def limb_band(sex, limb, H, bmi):
    """(lo, mean, hi): an adult limb's circumference over its joint-to-joint length at stature `H` and a BMI
    (a number, or [lo, hi] - the band then runs from the low BMI's 5th percentile to the high one's 95th). ANSUR
    II's regression (LIMB_BAND), extended below 1.45 m by the same law."""
    t = LIMB_BAND[sex]
    c, aH, aB, p5, p95 = t[limb]
    lo_b, hi_b = (bmi, bmi) if isinstance(bmi, (int, float)) else bmi

    def at(b):
        return c * (H / t["H"]) ** aH * (b / t["bmi"]) ** aB
    return at(lo_b) * p5, at((lo_b + hi_b) / 2), at(hi_b) * p95


def mass_factor(b, sex, girth, widths, scale):
    """Body mass over the pre-warp human's, by segment volume (de Leva shares, length x girth^2, head cubed).
    `girth` is absolute against the pre-warp human (legs, arms, neck, torso, and optional forearm, chest_depth
    and chest_breadth multipliers); `widths` are the shoulder and hip knobs, scaled by `scale` with the lengths."""
    w = MASS_SHARE[sex]
    f = {n: v * scale for n, v in b["factors"].items()}
    g = girth
    legs, arms = g["legs"] ** 2, g["arms"] ** 2
    fore = arms * g.get("forearm", 1.0) ** 2
    # the ribcage's own depth and breadth; its breadth from the shoulders' spread is already in the widths, its
    # depth (which follows that spread) is not
    rib = 1.0 - RIBCAGE_SHARE + RIBCAGE_SHARE * (g.get("chest_depth", 1.0) * g.get("chest_breadth", 1.0)
                                                 * g.get("chest_spread", 1.0))
    wmean = scale * (widths["shoulder_width"] + widths["hip_width"]) / 2
    v = (w["head"] * f["head"] ** 3 + w["trunk"] * f["spine"] * g["torso"] * wmean * rib
         + 2 * (w["thigh"] * f["femur"] * legs + w["shin"] * f["tibia"] * legs + w["foot"] * f["foot"] * legs
                + w["upper_arm"] * f["humerus"] * arms + w["forearm"] * f["forearm"] * fore
                + w["hand"] * f["hand"] * arms))
    return v / sum(w[n] * (1 if n in ("head", "trunk") else 2) for n in w)


# ------------------------------------------------------------------------------------------------ knobs
def defaults():
    return {n: d for n, (_u, d, _r, _m) in KNOBS.items()}


def _validate(k):
    p = []
    for n, v in k.items():
        if n not in KNOBS:
            p.append(f"unknown knob {n!r} - knobs are {', '.join(KNOBS)}")
            continue
        unit, _d, (lo, hi), meaning = KNOBS[n]
        if v is None:
            continue
        if isinstance(v, dict) and n == "waist_to_hip":
            p += [f"{n}.{s} = {x!r} is outside [{lo}, {hi}]" for s, x in v.items()
                  if not isinstance(x, (int, float)) or not lo <= x <= hi]
            continue
        if not isinstance(v, (int, float)) or not lo <= v <= hi:
            p.append(f"{n} = {v!r} is outside [{lo}, {hi}] {unit} ({meaning})")
    return p


def _stature(st):
    """A stature observable as {female: [lo, hi], male: [lo, hi]}."""
    if isinstance(st, dict):
        out = {}
        for sex in SEXES:
            v = st.get(sex, st.get("any"))
            if v is None:
                raise DesignError(f"stature needs {sex} (or any): {st}")
            out[sex] = list(v) if isinstance(v, (list, tuple)) else [v * 0.95, v * 1.05]
        return out
    if isinstance(st, (list, tuple)):
        lo, hi = st
        return {"female": [lo * 0.97, hi * 0.97], "male": [lo, hi]}
    if isinstance(st, (int, float)):
        return {"female": [st * 0.92, st * 1.02], "male": [st * 0.96, st * 1.06]}
    raise DesignError(f"stature must be metres, [lo, hi] or per sex, not {st!r}")


def _mid(st, sex):
    return sum(st[sex]) / 2


# ------------------------------------------------------------------------------------------------ design
def design(id="custom", label=None, stature=None, look=None, sources=None, notes=None, report=None,
           knob_notes=None, basis=None, anatomy=None, adult_cues=True, **knobs):
    """A species preset (humanform-species/1) from knobs (KNOBS; unset ones take the human default, `heads` the
    allometric law). `look`: {"head": {...}, "skin": {"palette", ...}, "moves": {...}, "graft": {...}} (graft: a
    limb pair replaced, humanform.graft - what it takes must be in anatomy.absent). `anatomy`: {"absent": [{"part", "reason"}],
    "scale": {part: factor}} - only what a description states; every other part is kept and scales with its host
    (ANATOMY). The skin's `regions_off` is derived from `absent` and nothing else. `report`: a
    solve() result, recorded in the preset's `design` block. `adult_cues` (on unless a description says the
    creature is a child's shape on purpose) holds the neck, hands, feet and shoulders at an adult's against the
    head (ADULT_CUES), recording each knob it moved in `design.adult_cues`. Raises DesignError, naming the knob
    and its range, or listing every inconsistency `check()` finds."""
    if stature is None:
        raise DesignError("stature is required (metres, [lo, hi] or per sex)")
    st = _stature(stature)
    for sex in SEXES:
        lo, hi = st[sex]
        if not 0.5 <= lo < hi <= 3.5:
            raise DesignError(f"stature {sex} {lo}-{hi} m is outside 0.5-3.5 m")
    k = defaults()
    k.update(knobs)
    p = _validate(k)
    if p:
        raise DesignError("; ".join(p))
    per_sex = {}
    heads_law = {}
    for sex in SEXES:
        b0 = body(k, sex, human(sex)["heads"])
        prop0 = metrics(b0["fr"], sex)
        trunk_ratio = 1.0 if is_proportionate(prop0) else b0["fr"]["spine_arc"] / human(sex)["spine_arc"]
        heads_law[sex] = allometric_heads(_mid(st, sex), sex, trunk_ratio)
    heads = k["heads"] if k["heads"] is not None else round(sum(heads_law.values()) / 2, 2)
    cues = {}
    if adult_cues:
        k, cues = _adult_cues(k, heads)
    for sex in SEXES:
        per_sex[sex] = body(k, sex, heads)
    props = {sex: metrics(per_sex[sex]["fr"], sex) for sex in SEXES}
    proportionate = all(is_proportionate(props[s]) for s in SEXES)
    basis = basis or ("head" if proportionate else "trunk")
    tol = k["tol_scale"]
    realistic = _json("presets.json")["presets"]["realistic"]

    ratios = {}
    for key in realistic["ratios"]:
        if key == "chin":
            continue
        ent = {}
        for sex in SEXES:
            h, v = human(sex), per_sex[sex]["fr"][key]
            ent[sex] = [round(v, 4), round(max(0.005, h["tol"][key] * tol * v / h[key]), 4)]
        ent["source"] = f"species_design: realistic {key} through the {id} knobs"
        ratios[key] = ent
    heads_tol = round(0.35 * tol * heads / 7.7, 3)
    ratios["chin"] = {"any": [round(1.0 - 1.0 / heads, 4), round(heads_tol / heads ** 2, 4)],
                      "source": "1 - 1/heads, the tolerance from the heads tolerance"}

    derived = {"shoulder_to_hip_width": {}, "waist_to_hip_circ": {}}
    for sex in SEXES:
        fr = per_sex[sex]["fr"]
        rd = realistic["derived"]
        derived["shoulder_to_hip_width"][sex] = [round(fr["shoulder_width"] / fr["hip_width"], 3),
                                                 round(rd["shoulder_to_hip_width"][sex][1] * tol, 3)]
        wh = k["waist_to_hip"]
        wh = wh.get(sex) if isinstance(wh, dict) else wh
        derived["waist_to_hip_circ"][sex] = [round(wh if wh is not None else rd["waist_to_hip_circ"][sex][0], 3),
                                             round(rd["waist_to_hip_circ"][sex][1] * tol, 3)]
    derived["shoulder_to_hip_width"]["source"] = "shoulder_width / hip_width of this species"
    derived["waist_to_hip_circ"]["source"] = "waist_to_hip knob, else the human's"

    presets = _json("presets.json")
    human_gap = presets["features"]["hip_above_crotch"]["range"]
    gscale = (sum(per_sex[s]["fr"]["hip_joint"] - per_sex[s]["fr"]["crotch"] for s in SEXES)
              / sum(human(s)["hip_joint"] - human(s)["crotch"] for s in SEXES))
    features = {"hip_above_crotch": {"range": [round(human_gap[0] * gscale, 4), round(human_gap[1] * gscale, 4)],
                                     "note": "the human range scaled with this species' hip-to-crotch gap"}}

    girth_rel = {"legs": k["girth_legs"], "arms": k["girth_arms"], "neck": k["girth_neck"], "torso": k["girth_torso"]}
    pre = {"stature_factor": {}, "stature": {}}
    segments, girth, widths, bmi, mass, support, limbs, chest = {}, {}, {}, {}, {}, {}, {}, {}
    bl, bh = _bmi_range(k["build_bmi"])
    warnings = list((report or {}).get("warnings") or [])
    scale_tot, scale_pre = {}, {}
    for sex in SEXES:
        b = per_sex[sex]
        kf = _pre_warp(b, sex, basis)
        lo, hi = st[sex]
        m = _mid(st, sex)
        pre["stature_factor"][sex] = round(kf, 4)
        pre["stature"][sex] = [round(lo * kf, 3), round(hi * kf, 3)]
        scale = 1.0 / (b["H"] * kf)
        segments[sex] = {n: round(f * scale, 4) for n, f in b["factors"].items()}
        wk = dict(b["widths"])             # the shoulder and hip knobs through the adult build law (body())
        widths[sex] = {n: round(v * scale, 4) for n, v in wk.items()}
        extra = {k2: k[k2] for k2 in ("girth_forearm", "chest_depth", "chest_breadth")}

        def built(H, sup=None):
            """The body as it is built at stature H, against the human actually fitted: a pre-warp human outside
            ANSUR is fitted at the limit and scaled whole by c (species.prewarp_stature), so the whole scale from
            the fit is scale x c, and the adult build law and the support girth apply to that (species.py takes
            c the same way). Returns (girth against the fit, mass factor against the fit, c, support)."""
            hp = H * kf
            c = hp / min(max(hp, ANSUR_STATURE[0]), ANSUR_STATURE[1])
            st_ = scale * c
            g = {n: v * law_scale(n, st_) for n, v in girth_rel.items()}
            g.update(forearm=extra["girth_forearm"], chest_depth=extra["chest_depth"],
                     chest_breadth=extra["chest_breadth"])
            # broad shoulders spread the chest bone (chest_spread); its depth follows its breadth, since a chest's
            # depth over breadth does not vary with stature (ANSUR II: ~H^0.02) - only with BMI and a stated barrel
            g["chest_spread"] = chest_spread(wk["shoulder_width"] * st_, g["torso"])
            if sup is None:
                # support: a limb carrying more than a human of this build at the mean stature thickens
                # (M^SUPPORT_EXP); the mass is the fitted human's (BMI x its stature^2) by the segments' volume
                m0 = k["build_bmi"] * (hp / c) ** 2 * mass_factor(b, sex, g, wk, st_)
                m_h = k["build_bmi"] * REF_STATURE[sex] ** 2
                sup = (m0 / m_h) ** SUPPORT_EXP if m0 > m_h else 1.0
            g["legs"] *= sup
            g["arms"] *= sup
            return g, mass_factor(b, sex, g, wk, st_), c, sup

        # the preset's girth is against the unclamped pre-warp human (species.py applies c by the same law)
        g_mid, mf_mid, c_mid, sup = built(m)
        support[sex] = round(sup, 4)
        scale_tot[sex] = scale * c_mid
        scale_pre[sex] = scale
        girth[sex] = {n: round(v / clamp_girth(n, scale, c_mid) if n in girth_rel else v, 4)
                      for n, v in g_mid.items() if n != "chest_spread"}
        # mass is volume (square-cube): the fitted human's BMI x its stature^2 x the segments' volume factor; BMI
        # is that over the built stature^2, at each end of the stature range
        def bmi_at(H, b_pre):
            g, mf, c, _ = built(H, sup)
            return b_pre * (H * kf / c) ** 2 * mf / H ** 2
        bmi[sex] = [round(bmi_at(lo, bl), 1), round(bmi_at(hi, bh), 1)]
        mass[sex] = round(bmi_at(m, k["build_bmi"]) * m * m, 1)
        # the look, as numbers: each limb's girth over its length against the adult band at this stature and
        # build (the fitted human's own c/L, then what the warp does to it); the chest's depth over its breadth
        limbs[sex] = {}
        h_fit = m * kf / c_mid
        for limb, (region, seg) in LIMB_REGION.items():
            gg = g_mid[region] * (g_mid["forearm"] if limb == "forearm" else 1.0)
            cl = limb_band(sex, limb, h_fit, k["build_bmi"])[1] * gg / (segments[sex][seg] * c_mid)
            blo, bmid, bhi = limb_band(sex, limb, m, [bl, bh])
            limbs[sex][limb] = {"girth_to_length": round(cl, 3), "band": [round(blo, 3), round(bhi, 3)],
                                "adult_mean": round(bmid, 3), "human_mean": round(limb_band(
                                    sex, limb, REF_STATURE[sex], LIMB_BAND[sex]["bmi"])[1], 3)}
        # the pre-warp human's own chest (its BMI's), then what the warp does to it: depth and breadth alike by the
        # torso's girth and the shoulders' spread, then the ribcage's own depth and breadth
        chest[sex] = round(CHEST_DB[sex] * (k["build_bmi"] / LIMB_BAND[sex]["bmi"]) ** 0.34
                           * g_mid["chest_depth"] / g_mid["chest_breadth"], 3)
    warnings += _build_warnings(limbs, bmi, (bl, bh), scale_tot, st)

    lookd = look or {}
    fur_block = None
    if lookd.get("fur") is not None:
        # the coverage map as data (humanform.fur): normalised and range-checked here, before a build
        _fur = _sibling("fur")
        try:
            fur_block = _fur.normalise(lookd["fur"])
        except ValueError as exc:
            raise DesignError(f"{id}: {exc}")
    anat = _anatomy(anatomy, segments, girth, widths, optional_on=(("fur",) if fur_block else ()))
    skin = dict(lookd.get("skin", {"palette": [[0.84, 0.66, 0.54], [0.55, 0.40, 0.31]]}))
    stray = sorted(set(skin.get("regions_off") or []) - set(anat["regions_off"]))
    if stray:
        raise DesignError(f"skin.regions_off {stray} without anatomy.absent: a region is never turned off for its "
                          "colour (region tints follow the tone); state the part as absent, with the reason the "
                          "description gives")
    skin["regions_off"] = anat.pop("regions_off")
    doc = {
        "schema": SCHEMA, "id": id, "label": label or id, "baseline": "human",
        "sources": list(sources or []),
        "notes": dict(notes or {}, **{
            "generated": "by humanform.species_design (scripts/derive_species.py) - edit the design, not this file",
            "knobs": dict(knob_notes or {}),
            "ratios": "fractions of the final standing stature (spine curve applied), as presets.json; tolerances "
                      f"are the realistic preset's scaled with the value and by {tol}",
            "proportion": "not graded: the observables this body shows, with the human's beside",
            "segments": "bone length factors against the pre-warp human (pre_warp); girth and widths likewise "
                        "absolute. The warp solves the final factors so the measured joints land on `ratios`",
            "bmi": "the finished body's mass (its volume, square-cube) over its stature^2; its girths follow the "
                   "adult build law (girth_law), so a short body of a build keeps an adult's BMI",
        }),
        "knobs": dict(k, heads=heads),
        "design": {"proportionate": proportionate, "heads_law": {s: round(v, 2) for s, v in heads_law.items()},
                   "mass_kg_mid": mass, "adult_cues": cues, "limbs": limbs, "chest_depth_to_breadth": chest,
                   "support": support, "warnings": warnings,
                   "scale_total": {sx: round(v, 4) for sx, v in scale_tot.items()},
                   **({"given": report["given"], "derived": report["derived"],
                       "contradictions": report["contradictions"],
                       "observables": report["observables"]}
                      if report else {})},
        "stature": {s: [round(v, 3) for v in st[s]] for s in SEXES},
        "bmi": [min(bmi[s][0] for s in SEXES), max(bmi[s][1] for s in SEXES)],
        "heads": {"any": [heads, heads_tol], "source": "1 / (1 - chin)"},
        "ratios": ratios, "derived": derived, "features": features,
        "proportion": {s: {n: (round(v, 4) if not isinstance(v, dict) else {a: round(c, 4) for a, c in v.items()})
                           for n, v in props[s].items()} for s in SEXES},
        "pre_warp": {"basis": basis, "min_stature": ANSUR_STATURE[0], "max_stature": ANSUR_STATURE[1],
                     "bmi": [round(bl, 1), round(bh, 1)],
                     "note": "H_pre = H * stature_factor (stature: the H_pre range), fitted at pre_warp.bmi. Outside "
                             "min/max_stature, fit at the limit and scale every segment, girth and width factor by "
                             "H_pre / limit (a uniform scale)", **pre},
        "segments": segments, "girth": girth, "widths": widths,
        "girth_law": {"exponents": dict(GIRTH_LAW), "support": support,
                      "scale": {sx: round(v, 5) for sx, v in scale_pre.items()},
                      "note": "legs/arms/neck/torso are absolute against the pre-warp human, by the adult build "
                              "law (a shrink by s takes s^exponent) and support; forearm, chest_depth and "
                              "chest_breadth multiply on top. A clamped pre-warp human's extra uniform scale "
                              "takes the same law (species.py)"},
        "spine": {"kyphosis_deg": k["hunch_deg"], "lordosis_deg": k["sway_deg"], "lumbar_share": LUMBAR_SHARE,
                  "note": "extra bend over a human's; thoracic forward, lumbar back, spread evenly over each span"},
        "head": lookd.get("head", {"shape": "oval", "shape_weight": 0.0, "features": {}}),
        "skin": skin,
        "anatomy": anat,
        "moves": lookd.get("moves", {"style": None, "notes": "derive_style from the build"}),
    }
    if lookd.get("graft"):
        # a body plan past the human one (humanform.graft): what it replaces must be declared absent
        _graft = _sibling("graft")
        gp = _graft.validate(lookd["graft"], absent=[e["part"] for e in anat["absent"]])
        if gp:
            raise DesignError(f"{id}: " + "; ".join(gp))
        doc["graft"] = lookd["graft"]
    if lookd.get("legs") not in (None, "plantigrade"):
        # which segments of the leg stand and which carries the ground (humanform.legs)
        lp = _sibling("legs").validate(lookd["legs"])
        if lp:
            raise DesignError(f"{id}: " + "; ".join(lp))
        doc["legs"] = lookd["legs"]
    if lookd.get("foot") not in (None, "human"):
        # how many toes carry the ground, what pads them, what grows on their ends (humanform.feet). The key is
        # `foot`, not `feet`: `feet` is already the observable for foot LENGTH against the head.
        fp = _sibling("feet").validate(lookd["foot"])
        if fp:
            raise DesignError(f"{id}: " + "; ".join(fp))
        doc["foot"] = lookd["foot"]
    if lookd.get("tail") not in (None, False):
        # a tail as well as the legs (humanform.tail); a tail INSTEAD of them is a graft
        if doc.get("graft", {}).get("legs"):
            raise DesignError(f"{id}: a species cannot have both `tail` (a tail beside its legs) and "
                              "`graft.legs -> tail` (a tail in place of them)")
        tp = _sibling("tail").validate(lookd["tail"])
        if tp:
            raise DesignError(f"{id}: " + "; ".join(tp))
        doc["tail"] = lookd["tail"]
    if fur_block is not None:
        doc["fur"] = fur_block
    p = check(doc, per_sex)
    if p:
        raise DesignError(f"{id}: " + "; ".join(p))
    return doc


def _build_warnings(limbs, bmi, build_band, scale, st):
    """Catch a body that will read as sticks before it is built: a limb whose girth over its length falls under
    the adult band for its stature and build (the band's 5th percentile), and a finished BMI under the build's
    adult band on a body that was not scaled up (a geometric shrink reads as a child, BMI ~15 at 1 m)."""
    out = []
    bl, bh = build_band
    for limb in LIMB_REGION:
        worst = min(SEXES, key=lambda s: limbs[s][limb]["girth_to_length"] / limbs[s][limb]["band"][0])
        row = limbs[worst][limb]
        if row["girth_to_length"] < row["band"][0]:
            out.append(f"stick limbs: {limb} girth/length {row['girth_to_length']:.2f} ({worst}) against the adult "
                       f"band {row['band'][0]:.2f}..{row['band'][1]:.2f} at {_mid(st, worst):.2f} m for a build "
                       f"of BMI {bl:.0f}-{bh:.0f} - state a heavier build, or drop a slender girth")
    for sex in SEXES:
        mid = sum(bmi[sex]) / 2
        if scale[sex] <= 1.0 and mid < 0.95 * bl:
            out.append(f"child-light BMI: {mid:.1f} ({sex}) under the build's adult band {bl:.0f}-{bh:.0f} - a "
                       "short adult keeps an adult's BMI; raise the build or the girth")
            break
    return out


def _anatomy(anatomy, segments, girth, widths, optional_on=()):
    """The anatomy block: every part kept unless stated absent, each with its size factor per sex against the
    pre-warp human (its host's warp factor ^ exponent x any stated relative scale). `optional_on` names the
    ANATOMY_OPTIONAL parts this species asks for (fur, when the look has a fur block); the rest are left out,
    so a preset written before they existed is still complete."""
    a = anatomy or {}
    unknown = sorted(set(a) - {"absent", "scale"})
    if unknown:
        raise DesignError(f"anatomy keys {unknown}: only 'absent' and 'scale'")
    absent = []
    for e in a.get("absent", []):
        if not isinstance(e, dict) or e.get("part") not in set(ANATOMY) | set(ANATOMY_SUBPARTS)                 or not e.get("reason"):
            raise DesignError(f"anatomy.absent entry {e!r}: needs part (one of {', '.join(ANATOMY)}, or a sub-part: "
                              f"{', '.join(ANATOMY_SUBPARTS)}) and the reason the description gives")
        absent.append({"part": e["part"], "reason": e["reason"]})
    gone = {e["part"] for e in absent}
    scale = a.get("scale", {})
    for part, v in scale.items():
        if part not in ANATOMY:
            raise DesignError(f"anatomy.scale {part!r}: one of {', '.join(ANATOMY)}")
        if part in gone:
            raise DesignError(f"anatomy.scale {part!r}: the part is declared absent")
        if not isinstance(v, (int, float)) or not ANATOMY_SCALE[0] <= v <= ANATOMY_SCALE[1]:
            raise DesignError(f"anatomy.scale {part} = {v!r} is outside {list(ANATOMY_SCALE)} (relative to its host)")
    parts = {}
    for part, (host, exp, region, meaning) in ANATOMY.items():
        if part in gone or (part in ANATOMY_OPTIONAL and part not in optional_on):
            continue
        per = {}
        for sex in SEXES:
            sg, g, w = segments[sex], girth[sex], widths[sex]
            hf = {"chest": w["shoulder_width"], "pelvis": w["hip_width"], "head": sg["head"], "hand": sg["hand"],
                  "foot": sg["foot"], "arm": g["arms"], "leg": g["legs"], "body": sg["spine"],
                  "torso": math.sqrt(sg["spine"] * g["torso"])}[host]
            per[sex] = round(hf ** exp * scale.get(part, 1.0), 4)
        parts[part] = {"on": host, "scale": per, "relative": scale.get(part, 1.0),
                       "source": "description" if part in scale else
                       "law: with its host" + ("" if exp == 1.0 else f" ^ {exp}")}
    regions = sorted({ANATOMY[p][2] for p in gone if p in ANATOMY and ANATOMY[p][2]})
    return {"parts": parts, "absent": absent, "regions_off": regions,
            "note": "every part a human has, kept and warped with its host unless the description says the creature "
                    "lacks it (absent, with its reason). scale: size factor against the pre-warp human's part"}


def _bmi_range(centre):
    for _w, (c, (lo, hi)) in BUILDS.items():
        if abs(c - centre) < 1e-6:
            return lo, hi
    return centre * 0.87, centre * 1.13


def check(doc, per_sex):
    """Every number in a preset agrees with every other; returns the problems (empty when consistent)."""
    p = []

    def need(cond, msg):
        if not cond:
            p.append(msg)

    realistic = _json("presets.json")["presets"]["realistic"]
    need(set(doc["ratios"]) == set(realistic["ratios"]), "ratios must cover exactly the realistic preset's keys")
    heads = doc["heads"]["any"][0]
    need(abs(doc["ratios"]["chin"]["any"][0] - (1 - 1 / heads)) < 1e-4, "chin must be 1 - 1/heads")
    for sex in SEXES:
        fr = per_sex[sex]["fr"]
        r = {k: v[sex][0] if sex in v else v["any"][0] for k, v in doc["ratios"].items()}
        order = ["ankle_joint", "knee_joint", "crotch", "hip_joint", "shoulder_joint"]
        need(all(r[a] < r[c] for a, c in zip(order, order[1:])), f"{sex}: joint heights out of order - "
             + ", ".join(f"{a} {r[a]:.3f}" for a in order))
        need(r["shoulder_joint"] < fr["neck_base"] < 1.0, f"{sex}: neck base must lie between shoulder and vertex")
        need(r["shoulder_joint"] < r["chin"] < 1.0, f"{sex}: chin {r['chin']:.3f} must lie above the shoulder "
             f"joints {r['shoulder_joint']:.3f} - fewer heads or a longer neck")
        need(abs(r["thigh"] - (r["hip_joint"] - r["knee_joint"])) < 2e-4, f"{sex}: thigh != hip - knee")
        need(abs(r["shin"] - (r["knee_joint"] - r["ankle_joint"])) < 2e-4, f"{sex}: shin != knee - ankle")
        need(abs(fr["heads"] - heads) < 1e-3, f"{sex}: body heads {fr['heads']:.3f} != {heads}")
        prop = doc["proportion"][sex]
        need(abs(prop["trunk"] - (prop["neck_base"] - prop["hip_fraction"])) < 2e-4, f"{sex}: trunk != neck - hip")
        lo, hi = doc["features"]["hip_above_crotch"]["range"]
        need(lo <= r["hip_joint"] - r["crotch"] <= hi, f"{sex}: hip above crotch outside its own range")
        need(fr["fingertip"] > r["ankle_joint"] + 0.05, f"{sex}: hanging fingertips {fr['fingertip']:.3f} H reach "
             "the ankles - a shorter arm")
        for n, f in doc["segments"][sex].items():
            need(0.2 < f < 2.5, f"{sex}: segment {n} factor {f} outside 0.2-2.5")
    b_lo, b_hi = doc["bmi"]
    need(8 < b_lo < b_hi < 90, f"bmi range {doc['bmi']}")
    pal = doc["skin"].get("palette") or []
    tone = doc["skin"].get("tone")
    if tone is not None:
        # one creature's own tone (an inline species, humanform.species.draw_skin), in place of a palette
        need(len(tone) == 3 and all(0 <= x <= 1 for x in tone), f"skin.tone {tone!r}: one sRGB tone in 0..1")
        need(not pal or (2 <= len(pal) <= 4 and all(len(c) == 3 and all(0 <= x <= 1 for x in c) for c in pal)),
             "skin.palette: 2-4 sRGB tones in 0..1")
    else:
        need(2 <= len(pal) <= 4 and all(len(c) == 3 and all(0 <= x <= 1 for x in c) for c in pal),
             "skin.palette: 2-4 sRGB tones in 0..1 (or skin.tone: one)")
    # a tone paler than the palest human skin the game ships clips past diffuse white in Godot's midday look
    # (lookdev's SKIN_PAST_WHITE failed the first elf, drawn from [0.94, 0.84, 0.76])
    for c in pal + ([tone] if tone is not None and len(tone) == 3 else []):
        need(_luma(c) <= PALEST_SKIN_LUMA + 1e-6, f"skin tone {list(c)} is paler than the palest skin that "
             f"holds under Godot's lighting (luma {_luma(c):.3f} > {PALEST_SKIN_LUMA:.3f}, e.g. [0.87, 0.74, 0.64]): "
             "darken it, or it clips past white (lookdev SKIN_PAST_WHITE)")
    regions = skin_regions()
    need(not regions or set(doc["skin"].get("regions_off", [])) <= set(regions),
         f"skin.regions_off {doc['skin'].get('regions_off')} not all in skin.REGIONS {regions}")
    an = doc.get("anatomy", {})
    gone = {e["part"] for e in an.get("absent", [])}
    backed = {ANATOMY[p][2] for p in gone if p in ANATOMY and ANATOMY[p][2]}
    need(set(doc["skin"].get("regions_off", [])) <= backed, "skin.regions_off must come only from anatomy.absent")
    need(all(p in an.get("parts", {}) or p in gone for p in ANATOMY if p not in ANATOMY_OPTIONAL),
         "every anatomical part must be kept or declared absent")
    if doc.get("fur") is not None:
        _fur = _sibling("fur")
        for problem in _fur.validate(doc["fur"]):
            p.append(problem)
        need("fur" in an.get("parts", {}), "a species with fur must carry `fur` as an anatomical part")
    shapes = face_shapes()
    need(not shapes or doc["head"].get("shape") in shapes, f"head shape {doc['head'].get('shape')!r} not in {shapes}")
    need(0 <= doc["head"].get("shape_weight", 0) <= 1, "head shape_weight in 0..1")
    return p


# ------------------------------------------------------------------------------------------------ solve
def _word(v, what):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and v in SIZE_WORDS:
        return SIZE_WORDS[v]
    raise DesignError(f"{what} {v!r}: a factor or one of {', '.join(SIZE_WORDS)}")


def _landmark(v):
    """fingertips_at -> function of a body's fractions giving the target fingertip height."""
    if isinstance(v, (int, float)):
        return lambda f: float(v)
    m = re.fullmatch(r"\s*(\w+)\s*(?:([+-])\s*([0-9.]+))?\s*", str(v))
    if not m or m.group(1) not in LANDMARKS:
        raise DesignError(f"fingertips_at {v!r}: one of {', '.join(LANDMARKS)} (optionally +0.05), or a fraction of H")
    off = float(m.group(3) or 0.0) * (-1 if m.group(2) == "-" else 1)
    fn = LANDMARKS[m.group(1)]
    return lambda f: fn(f) + off


def _bisect(fn, target, lo, hi, n=50):
    """x in [lo, hi] with fn(x) = target, fn monotone either way; None when out of reach."""
    flo, fhi = fn(lo) - target, fn(hi) - target
    if flo * fhi > 0:
        return None
    for _ in range(n):
        mid = (lo + hi) / 2
        fm = fn(mid) - target
        if (fm < 0) == (flo < 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def _mean_metric(k, st, name, heads=None):
    vals = []
    for sex in SEXES:
        hd = heads if heads is not None else (k["heads"] or allometric_heads(_mid(st, sex), sex))
        vals.append(metrics(body(k, sex, hd)["fr"])[name])
    return sum(vals) / len(vals)


def solve(observables, **knobs):
    """Knobs from observables (OBSERVABLES; any subset, plus explicit knobs, which win). Returns {"knobs",
    "given", "derived", "contradictions", "observables"}: `derived` names each knob that came from a law or a
    default and why; `contradictions` lists every given observable the result misses, by how much."""
    obs = dict(observables)
    unknown = [n for n in obs if n not in OBSERVABLES and n != "leg_fraction"]
    if unknown:
        raise DesignError(f"unknown observables {unknown} - observables are {', '.join(OBSERVABLES)}; knobs go as "
                          "keyword arguments")
    if "leg_fraction" in obs:
        obs["hip_fraction"] = obs.pop("leg_fraction")
    if "stature" not in obs:
        raise DesignError("stature is required")
    st = _stature(obs["stature"])
    k = defaults()
    bad = _validate(knobs)
    if bad:
        raise DesignError("; ".join(bad))
    k.update(knobs)
    given = sorted(set(obs) | {f"{n} (knob)" for n in knobs})
    derived, contra = {}, []

    def setk(name, value, why):
        if name in knobs:
            return False
        k[name] = value
        derived[name] = why
        return True

    # words and direct mappings
    if "build" in obs:
        if obs["build"] not in BUILDS:
            raise DesignError(f"build {obs['build']!r}: one of {', '.join(BUILDS)}")
        setk("build_bmi", BUILDS[obs["build"]][0], f"build {obs['build']!r}")
    for o, n in (("hands", "hand_scale"), ("feet", "foot_scale"), ("neck", "neck_scale")):
        if o in obs:
            setk(n, _word(obs[o], o), f"{o} {obs[o]!r}")
    if "girth" in obs:
        g = obs["girth"]
        if isinstance(g, dict):
            bad = sorted(set(g) - {"legs", "arms", "neck", "torso", "forearm"})
            if bad:
                raise DesignError(f"girth regions {bad}: legs, arms, neck, torso, forearm")
        for region in ("legs", "arms", "neck", "torso", "forearm"):
            v = g.get(region) if isinstance(g, dict) else (g if region != "forearm" else None)
            if v is not None:
                setk(f"girth_{region}", _word(v, "girth"), f"girth {g!r}")
    if "forearms" in obs:
        setk("girth_forearm", _word(obs["forearms"], "forearms"), f"forearms {obs['forearms']!r}")
    chest_target = None
    if "chest_depth_to_breadth" in obs:
        chest_target = float(obs["chest_depth_to_breadth"])
    elif "barrel_chest" in obs:
        t = float(obs["barrel_chest"])
        if not 0.0 <= t <= 1.0:
            raise DesignError(f"barrel_chest {t}: 0 (a human's chest) to 1 (depth over breadth {BARREL_DB})")
        chest_target = sum(CHEST_DB.values()) / 2 + t * (BARREL_DB - sum(CHEST_DB.values()) / 2)
    if "rhizomelic" in obs:
        setk("leg_root_share", float(obs["rhizomelic"]), "rhizomelic")
        setk("arm_root_share", float(obs["rhizomelic"]), "rhizomelic")
    for o in ("hunch_deg", "sway_deg"):
        if o in obs:
            setk(o, float(obs[o]), o)
    if "heads" in obs:
        setk("heads", float(obs["heads"]), "heads")
    proportionate = bool(obs.get("proportionate"))
    hum = {n: sum(metrics(human(s))[n] for s in SEXES) / 2 for n in ("trunk_to_leg", "arm_to_leg")}

    # the leg target: one of hip_fraction, crotch_fraction, upper_to_lower (the first given; the rest are checked)
    leg_obs = [o for o in ("hip_fraction", "crotch_fraction", "upper_to_lower") if o in obs]
    trunk_target = obs.get("trunk_to_leg", hum["trunk_to_leg"] if proportionate else None)
    arm_obs = "fingertips_at" if "fingertips_at" in obs else ("arm_to_leg" if "arm_to_leg" in obs else None)

    girth_free = ([f"girth_{r}" for r in ("legs", "arms", "neck", "torso") if f"girth_{r}" not in knobs]
                  if ("bmi" in obs or "mass_kg" in obs) else [])
    girth_base = {n: k[n] for n in girth_free}
    legs_pinned = bool(leg_obs) or "leg_scale" in knobs
    cue_start = {}
    girth_solved = None
    warnings = []
    for _it in range(6):
        heads_now = k["heads"]
        if heads_now is None:            # the law, with the trunk ratio the body has now
            vals = []
            for sex in SEXES:
                b = body(k, sex, human(sex)["heads"])
                pr = metrics(b["fr"], sex)
                tr = 1.0 if (proportionate or is_proportionate(pr)) else b["fr"]["spine_arc"] / human(sex)["spine_arc"]
                vals.append(allometric_heads(_mid(st, sex), sex, tr))
            heads_now = sum(vals) / 2
        # an adult's neck, hands, feet and shoulders against this head, before the lengths are solved around them
        # (design() would otherwise move them after, and the solved observables with them)
        for knob, row in _adult_cues(k, heads_now, cue_start)[1].items():
            if knob not in knobs:
                bound = row.get("floor", row.get("ceiling"))
                setk(knob, row["to"], f"adult cue: {row['metric']} held at {bound} (ADULT_CUES), from {row['from']}")
        if leg_obs and "leg_scale" not in knobs:
            o = leg_obs[0]
            name, tgt = ("crotch_fraction", 1.0 / (1.0 + obs[o])) if o == "upper_to_lower" else (o, obs[o])

            def f_leg(x):
                return _mean_metric(dict(k, leg_scale=x), st, name, heads_now)
            x = _bisect(f_leg, tgt, *KNOBS["leg_scale"][2])
            if x is None:
                raise DesignError(f"{o} {obs[o]} is out of reach: leg_scale's range {KNOBS['leg_scale'][2]} gives "
                                  f"{f_leg(KNOBS['leg_scale'][2][0]):.3f}-{f_leg(KNOBS['leg_scale'][2][1]):.3f}")
            setk("leg_scale", x, f"solved from {o} {obs[o]}")
        if trunk_target is not None and "trunk_scale" not in knobs:
            def f_tr(x):
                return _mean_metric(dict(k, trunk_scale=x), st, "trunk_to_leg", heads_now)
            why = "trunk_to_leg" if "trunk_to_leg" in obs else "proportionate: a human's trunk_to_leg"
            if legs_pinned:
                x = _bisect(f_tr, trunk_target, *KNOBS["trunk_scale"][2])
                if x is None:
                    raise DesignError(f"trunk_to_leg {trunk_target:.3f} is out of reach of trunk_scale "
                                      f"{KNOBS['trunk_scale'][2]}")
                setk("trunk_scale", x, f"solved from {why} {trunk_target:.3f}")
            else:                          # no leg observable: the legs carry the ratio, the trunk stays human
                def f_lg(x):
                    return _mean_metric(dict(k, leg_scale=x), st, "trunk_to_leg", heads_now)
                x = _bisect(f_lg, trunk_target, *KNOBS["leg_scale"][2])
                if x is None:
                    raise DesignError(f"trunk_to_leg {trunk_target:.3f} is out of reach of leg_scale")
                setk("leg_scale", x, f"solved from {why} {trunk_target:.3f} (the trunk kept human)")
        if "arm_scale" not in knobs:
            if arm_obs == "fingertips_at":
                where = _landmark(obs["fingertips_at"])

                def f_arm(x):
                    vals = []
                    for sex in SEXES:
                        fr = body(dict(k, arm_scale=x), sex, heads_now)["fr"]
                        vals.append(fr["fingertip"] - where(fr))
                    return sum(vals) / 2
                x = _bisect(f_arm, 0.0, *KNOBS["arm_scale"][2])
                if x is None:
                    raise DesignError(f"fingertips_at {obs['fingertips_at']!r} is out of reach of arm_scale "
                                      f"{KNOBS['arm_scale'][2]}")
                setk("arm_scale", x, f"solved from fingertips_at {obs['fingertips_at']!r}")
            else:
                tgt = obs["arm_to_leg"] if arm_obs else hum["arm_to_leg"]

                def f_al(x):
                    return _mean_metric(dict(k, arm_scale=x), st, "arm_to_leg", heads_now)
                x = _bisect(f_al, tgt, *KNOBS["arm_scale"][2])
                if x is None:
                    raise DesignError(f"arm_to_leg {tgt:.3f} is out of reach of arm_scale {KNOBS['arm_scale'][2]}")
                setk("arm_scale", x, f"solved from arm_to_leg {tgt:.3f}" if arm_obs
                     else "the law: arms scale with the legs (a human's arm_to_leg)")
        if "shoulder_heads" in obs and "shoulder_scale" not in knobs:
            def f_sh(x):
                return _mean_metric(dict(k, shoulder_scale=x), st, "shoulder_heads", heads_now)
            x = _bisect(f_sh, obs["shoulder_heads"], *KNOBS["shoulder_scale"][2])
            if x is None:
                raise DesignError(f"shoulder_heads {obs['shoulder_heads']} is out of reach of shoulder_scale")
            setk("shoulder_scale", x, f"solved from shoulder_heads {obs['shoulder_heads']}")
        if "shoulder_to_hip" in obs:
            name = "hip_scale" if ("shoulder_scale" in knobs or "shoulder_heads" in obs) else "shoulder_scale"
            if name not in knobs:
                def f_sw(x):
                    return _mean_metric(dict(k, **{name: x}), st, "shoulder_to_hip", heads_now)
                x = _bisect(f_sw, obs["shoulder_to_hip"], *KNOBS[name][2])
                if x is None:
                    raise DesignError(f"shoulder_to_hip {obs['shoulder_to_hip']} is out of reach of {name}")
                setk(name, x, f"solved from shoulder_to_hip {obs['shoulder_to_hip']}")
        if girth_free:
            what = "bmi" if "bmi" in obs else "mass_kg"
            tgt = obs[what]

            def f_mass(x):
                try:
                    d = design(stature=st, **dict(_settable(k), heads=heads_now,
                                                  **{n: min(2.0, girth_base[n] * x) for n in girth_free}))
                except DesignError:
                    # a trial the check refuses is off one end: far too light (the BMI floor) below the base
                    # girth, far too heavy above it. Always 1e9 made a thin body unreachable: bmi 18.5 at a
                    # slender build failed because girth 0.55 is under BMI 8 (a drow, 2026-09-21)
                    return -1e9 if x < 1.0 else 1e9
                return sum(d["bmi"]) / 2 if what == "bmi" else sum(d["design"]["mass_kg_mid"].values()) / 2
            x = _bisect(f_mass, tgt, 0.55, 2.0 / max(girth_base.values()), n=40)
            if x is None:
                raise DesignError(f"{what} {tgt} is out of reach of girth 0.5-2.0 at build_bmi {k['build_bmi']}: "
                                  "change `build`")
            for n in girth_free:
                setk(n, round(girth_base[n] * x, 4), f"solved from {what} {tgt} (square-cube volume law)")
            girth_solved = x
        if chest_target is not None and "chest_depth" not in knobs:
            d = design(stature=st, **dict(_settable(k), heads=heads_now))
            cur = sum(d["design"]["chest_depth_to_breadth"].values()) / 2
            lo_c, hi_c = KNOBS["chest_depth"][2]
            setk("chest_depth", round(min(hi_c, max(lo_c, k["chest_depth"] * chest_target / cur)), 4),
                 f"solved from chest depth/breadth {chest_target:.3f}")
    if k["heads"] is None:
        derived["heads"] = "the head-allometry law"
    else:
        derived.pop("heads", None)
    for n in KNOBS:
        if n not in derived and n not in knobs and n != "heads":
            derived.setdefault(n, "human default")

    if girth_solved is not None and girth_solved < 0.92 and "girth" in obs:
        what = "bmi" if "bmi" in obs else "mass_kg"
        warnings.append(f"{what} {obs[what]} thins the stated girth to {girth_solved:.2f} of itself: the build the "
                        f"girth describes weighs more than that - drop {what} (the mass follows from the shape) or "
                        "the girth")
    # what the result shows, against every observable given
    d = design(stature=st, **_settable(k))
    shown = {}
    for sex in SEXES:
        for n, v in d["proportion"][sex].items():
            if not isinstance(v, dict):
                shown.setdefault(n, []).append(v)
    shown = {n: sum(v) / len(v) for n, v in shown.items()}
    shown["bmi"] = sum(d["bmi"]) / 2
    shown["mass_kg"] = sum(d["design"]["mass_kg_mid"].values()) / 2
    shown["chest_depth_to_breadth"] = sum(d["design"]["chest_depth_to_breadth"].values()) / 2
    for o, tol in (("hip_fraction", 0.004), ("crotch_fraction", 0.004), ("upper_to_lower", 0.03),
                   ("trunk_to_leg", 0.02), ("arm_to_leg", 0.02), ("shoulder_to_hip", 0.03), ("shoulder_heads", 0.05),
                   ("heads", 0.05), ("bmi", 1.0), ("mass_kg", 3.0), ("chest_depth_to_breadth", 0.02)):
        if o in obs:
            want = obs[o]
            if abs(shown[o] - want) > tol:
                why = ("the leg is set by " + leg_obs[0] if o in leg_obs[1:] else
                       "an explicit knob or another observable pins it")
                contra.append(f"{o}: asked {want}, the body gives {shown[o]:.3f} ({why})")
    if "fingertips_at" in obs:
        where = _landmark(obs["fingertips_at"])
        miss = sum(d["proportion"][s]["fingertip"] - where(_frac(d, s)) for s in SEXES) / 2
        if abs(miss) > 0.005:
            contra.append(f"fingertips_at {obs['fingertips_at']!r}: the fingertips miss it by {miss:+.3f} H")
    if "heads" in obs:
        law = sum(d["design"]["heads_law"].values()) / 2
        if abs(law - obs["heads"]) / law > 0.1:
            derived["heads_note"] = (f"heads {obs['heads']} against the allometric {law:.1f}: a stylised head "
                                     f"{'larger' if obs['heads'] < law else 'smaller'} than the law's - label it "
                                     "[folklore]")
    # past the tallest pre-warp human the body is a person scaled whole, and square-cube lifts its BMI in proportion
    # to the scale (a 3 m giant of a person's build is BMI ~45): the plausible band scales with it, so a giant is
    # warned only for what its build and girth add, not for the law. The whole scale from the fitted human (the
    # clamp included) is design's `scale_total`. A disproportionate body keeps its trunk-matched human's trunk on
    # a shorter stature, which lifts its BMI by that stature factor (achondroplasia runs ~30 [measured])
    grow = max(1.0, sum(d["design"]["scale_total"].values()) / 2)
    if not d["design"]["proportionate"]:
        grow *= max(1.0, sum(d["pre_warp"]["stature_factor"].values()) / 2)
    lo_b, hi_b = BMI_PLAUSIBLE[0] * grow, BMI_PLAUSIBLE[1] * grow
    if "bmi" not in obs and "mass_kg" not in obs and not lo_b <= shown["bmi"] <= hi_b:
        # nobody asked for this BMI: it is what the inputs stacked up to, so say which (a drow's build
        # "slender" and girth "slender" multiplied to BMI 14-17, 2026-09-21)
        stack = []
        if "build" in obs:
            stack.append(f"build {obs['build']!r} (pre-warp BMI {k['build_bmi']:g})")
        g = {n: k[n] for n in ("girth_legs", "girth_arms", "girth_neck", "girth_torso") if abs(k[n] - 1.0) > 1e-6}
        if g:
            stack.append("girth " + ", ".join(f"{n[6:]} {v:g}" for n, v in g.items())
                         + (f" (from girth {obs['girth']!r})" if "girth" in obs else ""))
        mid = sum(_mid(st, s) for s in SEXES) / 2
        stack.append(f"stature {mid:.2f} m (square-cube: BMI grows with height at one build)")
        warnings.append(f"bmi {shown['bmi']:.1f} is outside a plausible {lo_b:.0f}-{hi_b:.0f} "
                        f"and nobody stated it: it is what {'; '.join(stack)} stacked up to. Drop one of them "
                        "(a build word and a girth word each already thin or thicken the body) - the mass follows from "
                        "the shape, so thin the girth rather than state a `bmi` that fights it")
    return {"knobs": _settable(k), "given": given, "derived": derived, "contradictions": contra,
            "warnings": warnings, "observables": {o: obs[o] for o in obs}}


def _settable(k):
    return {n: v for n, v in k.items() if n in KNOBS}


def _frac(doc, sex):
    return {key: (doc["ratios"][key].get(sex) or doc["ratios"][key]["any"])[0] for key in doc["ratios"]}


def design_from(observables, id="custom", look=None, sources=None, notes=None, knob_notes=None, basis=None,
                anatomy=None, **knobs):
    """solve() then design(), the solve report kept in the preset."""
    r = solve(observables, **knobs)
    return design(id=id, stature=observables["stature"], look=look, sources=sources, notes=notes, report=r,
                  knob_notes=knob_notes, basis=basis, anatomy=anatomy,
                  **r["knobs"])


# ------------------------------------------------------------------------------------------------ explain
def explain(preset):
    """A short plain-text table of a preset: its knobs against a human's and where each came from, then the
    observables it shows beside a human's."""
    k = preset.get("knobs", {})
    dz = preset.get("design", {})
    der = dz.get("derived", {})
    lines = [f"{preset['id']}: {preset.get('label', '')}",
             f"  stature f {preset['stature']['female']} m, m {preset['stature']['male']} m; bmi {preset['bmi']} "
             f"(pre-warp {preset['pre_warp'].get('bmi')}); {preset['heads']['any'][0]} heads "
             f"(law {dz.get('heads_law')}); {'proportionate' if dz.get('proportionate') else 'disproportionate'}, "
             f"pre-warp basis {preset['pre_warp']['basis']}",
             f"  {'knob':15} {'value':>7} {'human':>6}  from"]
    for n, (unit, dflt, _r, _m) in KNOBS.items():
        v = k.get(n)
        if v is None:
            continue
        src = der.get(n, "given" if any(g.startswith(n) for g in dz.get("given", [])) else "")
        if isinstance(v, dict):
            v = "/".join(str(x) for x in v.values())
            lines.append(f"  {n:15} {v:>7} {'':>6}  {src}")
            continue
        hd = "-" if dflt is None else f"{dflt:g}"
        mark = "" if dflt is not None and abs(v - dflt) < 1e-6 else " *"
        lines.append(f"  {n:15} {v:7.3f} {hd:>6}  {src}{mark}")
    lines.append(f"  {'observable':22} {'female':>7} {'male':>7} {'human m':>8}")
    for n in ("heads", "hip_fraction", "crotch_fraction", "trunk_to_leg", "upper_to_lower", "arm_to_leg",
              "fingertip_above_knee", "shoulder_to_hip", "shoulder_heads"):
        f, m = preset["proportion"]["female"][n], preset["proportion"]["male"][n]
        h = preset["proportion"]["male"]["human"][n]
        lines.append(f"  {n:22} {f:7.3f} {m:7.3f} {h:8.3f}")
    if dz.get("limbs"):
        lines.append(f"  {'build (male)':22} {'girth/len':>9} {'adult band':>13} {'human':>6}")
        for limb, row in dz["limbs"]["male"].items():
            lines.append(f"  {limb:22} {row['girth_to_length']:9.2f} {row['band'][0]:6.2f}-{row['band'][1]:<6.2f} "
                         f"{row['human_mean']:6.2f}")
        cd = dz.get("chest_depth_to_breadth") or {}
        lines.append(f"  chest depth/breadth    f {cd.get('female')} m {cd.get('male')} (human 0.92 / 0.88); "
                     f"mass {dz.get('mass_kg_mid')} kg; support {dz.get('support')}")
    for w in dz.get("warnings", []):
        lines.append(f"  WARNING {w}")
    an = preset.get("anatomy", {})
    if an.get("absent"):
        lines.append("  absent: " + "; ".join(f"{e['part']} ({e['reason']})" for e in an["absent"]))
    stated = {p: v["relative"] for p, v in an.get("parts", {}).items() if v["relative"] != 1.0}
    if stated:
        lines.append(f"  anatomy scaled by the description: {stated}")
    for c in dz.get("contradictions", []):
        lines.append(f"  CONTRADICTION {c}")
    for w in dz.get("warnings", []):
        lines.append(f"  WARNING {w}")
    if der.get("heads_note"):
        lines.append(f"  note: {der['heads_note']}")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ look
def chart(presets, path, sex="male"):
    """An SVG of front and side stick figures of a human and each preset (a list of design() results) at true
    scale, each at its mid stature, forward to the left, the hanging arms in red - the look before a build."""
    docs = {p["id"]: p for p in presets}
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
    h0 = human(sex)
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
            fr = body(dict(defaults(), **docs[sid]["knobs"]), sex, docs[sid]["heads"]["any"][0])["fr"]
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
