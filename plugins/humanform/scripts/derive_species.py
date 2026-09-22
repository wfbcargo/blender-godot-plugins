"""Write data/species/<id>.json for the catalogue species - the worked examples of references/species-design.md.

    python derive_species.py                     # solve, design, check and write every species
    python derive_species.py --check             # the same, writing nothing
    python derive_species.py --explain dwarf     # the knob/observable table of one species
    python derive_species.py --chart out.svg     # every species beside a human, true scale, front and side

A thin CLI over `humanform.species_design`, which owns the parameter space, the laws and the checks. Each
species below is what someone would say about it - its observables, each with its reason and label
([measured], [documented], [folklore]) - plus the few knobs no observable expresses. To add a species, add an
entry and run this; to design one from a description without adding it here, call `species_design.design_from`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from humanform import species_design as sd     # noqa: E402

OUT_DIR = os.path.join(sd.DATA, "species")
S = sd.SOURCES

# id: label, sources, observables {name: (value, why)}, knobs {name: (value, why)}, look
SPECIES = {
    "elf": {
        "label": "Elf: tall, slender, long-legged and long-necked, pointed ears",
        "sources": [S["design"], "Tolkien's Eldar as tall as tall men (folklore canon); art canon 8-8.5 heads"],
        "observables": {
            "stature": ({"female": [1.65, 1.85], "male": [1.75, 1.95]},
                        "Tolkien-tall rather than D&D's 4'6\"+2d10 (1.42-1.88 m) [folklore]"),
            "heads": (8.3, "the heroic-elegant canon; the law gives ~8.0 at 1.85 m [folklore]"),
            "hip_fraction": (0.525, "long legs: a human's is 0.51-0.52 [folklore]"),
            "neck": (1.2, "the long neck of the elf convention, inside a long-necked adult's [folklore]"),
            "build": ("lean", "slender [folklore]"),
            "hands": (1.04, "long fingers [folklore]"),
            "hunch_deg": (-3.0, "a straighter, upright back"),
        },
        "knobs": {"shoulder_scale": (0.93, "narrow shoulders [folklore]"), "hip_scale": (0.95, "narrow hips"),
                  "waist_to_hip": ({"female": 0.78, "male": 0.88}, "a defined waist on a lean body")},
        "look": {"head": {"shape": "invertedtriangular", "shape_weight": 0.6,
                          "features": {"ears_pointed": 1.0, "brow_ridge": -0.2, "nose_size": -0.25, "tusks": 0.0}},
                 "skin": {"palette": [[0.90, 0.78, 0.68], [0.84, 0.69, 0.58], [0.66, 0.50, 0.39], [0.45, 0.32, 0.25]],
                          "regions_off": []},
                 "moves": {"style": None, "notes": "Froude scaling gives a long, slow-cadence stride; a light "
                                                   "'elf_light' style is convention, not physics"}},
        "skin_why": "human tones, pale to deep; every human region applies",
    },
    "halfling": {
        "label": "Halfling: small and proportionate, a child-like head fraction, big feet",
        "sources": [S["design"], S["dnd"] + ": halfling 2'7\" + 2d4 in (0.84-0.99 m)",
                    "Tolkien, The Fellowship of the Ring, prologue: hobbits 2-4 ft, large hairy feet"],
        "observables": {
            "stature": ({"female": [0.85, 1.05], "male": [0.88, 1.10]},
                        "D&D 0.84-0.99 m, stretched toward Tolkien's taller hobbits [documented, game rules]"),
            "heads": (5.5, "the law gives ~5.7 at 0.99 m; a little bigger for the round face [folklore]"),
            "trunk_to_leg": (0.72, "a slightly long trunk, a round belly - still proportionate"),
            "feet": (1.22, "the big hobbit feet [folklore]"),
            "neck": (0.85, "a short neck"),
            "build": ("stocky", "well fed and round [folklore]"),
            "girth": ({"legs": 1.08, "arms": 1.05, "neck": 1.05, "torso": 1.10}, "plump"),
            "sway_deg": (3.0, "a little belly-forward sway"),
        },
        "knobs": {"shoulder_scale": (1.04, "sturdy"), "hip_scale": (1.06, "round"),
                  "waist_to_hip": ({"female": 0.90, "male": 0.98}, "a round belly")},
        "look": {"head": {"shape": "round", "shape_weight": 0.5,
                          "features": {"ears_pointed": 0.45, "brow_ridge": 0.0, "nose_size": 0.1, "tusks": 0.0}},
                 "skin": {"palette": [[0.90, 0.75, 0.63], [0.80, 0.62, 0.49], [0.62, 0.45, 0.34], [0.46, 0.33, 0.25]],
                          "regions_off": []},
                 "moves": {"style": None, "notes": "Froude scaling on ~0.45 m legs gives a quick, short step"}},
        "skin_why": "human, ruddy; every human region applies",
    },
    "gnome": {
        "label": "Gnome: a proportionate shrink pushed further - about 1 m, a big head and a big nose",
        "sources": [S["design"], S["dnd"] + ": gnome 2'11\" + 2d4 in (0.94-1.09 m)"],
        "observables": {
            "stature": ({"female": [0.92, 1.08], "male": [0.95, 1.12]}, "D&D 0.94-1.09 m [documented, game rules]"),
            "heads": (4.3, "the law gives ~5.8 at 1.0 m: 4.3 is the cartoon's big head (0.23 m, an adult "
                           "human's) [folklore]"),
            "trunk_to_leg": (0.74, "short legs, still proportionate"),
            "hands": (1.05, "nimble, slightly long fingers [folklore]"),
            "feet": (1.05, "slightly big feet"),
            "neck": (0.8, "a short neck under the big head"),
            "build": ("average", ""),
            "girth": ({"neck": 1.1, "torso": 1.05}, ""),
            "sway_deg": (2.0, "slight sway"),
        },
        "knobs": {"shoulder_scale": (1.05, "not spindly under the big head"), "hip_scale": (1.05, ""),
                  "waist_to_hip": ({"female": 0.88, "male": 0.95}, "")},
        "look": {"head": {"shape": "round", "shape_weight": 0.7,
                          "features": {"ears_pointed": 0.6, "brow_ridge": 0.0, "nose_size": 0.8, "tusks": 0.0}},
                 "skin": {"palette": [[0.90, 0.76, 0.65], [0.82, 0.62, 0.50], [0.64, 0.46, 0.35], [0.47, 0.33, 0.25]],
                          "regions_off": []},
                 "moves": {"style": None, "notes": "Froude scaling on ~0.45 m legs gives a quick scurry"}},
        "skin_why": "human, ruddy; the flush reads as a gnome's red cheeks and nose",
    },
    "dwarf": {
        "label": "Dwarf: short, stocky, long trunk, short limbs (softened achondroplasia)",
        "sources": [S["design"], S["achondroplasia"], S["segment_ratio"],
                    S["dnd"] + ": hill dwarf 3'8\" + 2d4 in (1.17-1.32 m), mountain dwarf 4'0\" + 2d4 in (1.27-1.42 m)"],
        "observables": {
            "stature": ({"female": [1.15, 1.40], "male": [1.20, 1.45]},
                        "D&D hill and mountain dwarves, 1.17-1.42 m [documented, game rules]"),
            "heads": (5.0, "art draws 4-4.5 [folklore], but on a human-sized trunk that is a 0.29 m head; the law "
                           "gives ~6.0. 5.0 (0.26 m) is achondroplasia's macrocephaly [measured] without a cartoon"),
            "upper_to_lower": (1.5, "achondroplasia's 1.9-2.1 [measured], softened to the design's 1.3-1.6"),
            "rhizomelic": (0.35, "the femur and humerus shortened most [measured]"),
            "arm_to_leg": (0.74, "achondroplasia shortens the span ~35% for legs ~50% [measured]: the arms lose "
                                 "0.7 of the legs' share, so arm/leg rises over a human's 0.70"),
            "hands": (0.88, "short broad hands (brachydactyly [measured])"),
            "feet": (0.85, "short broad feet"),
            "neck": (0.6, "a thick short neck [folklore]"),
            "build": ("stocky", "a stocky human with the dwarf's trunk is the start"),
            "girth": ({"legs": 1.05, "arms": 1.12, "neck": 1.25, "torso": 1.12},
                      "heavy limbs, thick neck, a deep trunk; a short thigh stays as thick [folklore]. No bmi: "
                      "achondroplastic adults run ~30 [measured], and this shape comes out above it, as a stocky "
                      "man on a dwarf's legs should - a stated 33 thinned every girth to 0.85 of itself"),
            "forearms": ("heavy", "heavy forearms, the smith's [folklore]"),
            "barrel_chest": (1.0, "a barrel chest: the ribcage as deep as it is broad [folklore]; a broad "
                                  "shoulder alone only widens a chest, which read as a short man"),
            "sway_deg": (8.0, "exaggerated lumbar lordosis, as in achondroplasia [measured]"),
        },
        "knobs": {"trunk_scale": (0.97, "sitting height only mildly reduced in achondroplasia [measured]"),
                  "shoulder_scale": (1.08, "broad shoulders [folklore]"), "hip_scale": (1.08, "a broad pelvis"),
                  "waist_to_hip": ({"female": 0.90, "male": 0.98}, "a barrel trunk")},
        "look": {"head": {"shape": "square", "shape_weight": 0.7,
                          "features": {"ears_pointed": 0.0, "brow_ridge": 0.45, "nose_size": 0.5, "tusks": 0.0}},
                 "skin": {"palette": [[0.88, 0.71, 0.59], [0.74, 0.55, 0.43], [0.56, 0.40, 0.30], [0.40, 0.28, 0.21]],
                          "regions_off": []},
                 "moves": {"style": None, "notes": "derive_style gives the roll from the trunk/leg ratio "
                                                   "(achondroplasia gait [measured]); Froude the quick short step"}},
        "skin_why": "human, weathered; every human region applies",
    },
    "orc": {
        "label": "Orc: broad, heavy and tall, green-grey skin, tusks and a heavy brow",
        "sources": [S["design"], S["dnd"] + ": half-orc 4'10\" + 2d10 in (1.52-2.0 m)"],
        "observables": {
            "stature": ({"female": [1.70, 1.90], "male": [1.80, 2.05]},
                        "tall end of D&D's half-orc range [documented, game rules]"),
            "heads": (7.5, "a slightly big, heavy-jawed head; the law gives ~8.2 [folklore]"),
            "trunk_to_leg": (0.73, "a long deep trunk on slightly short legs: power, not reach [folklore]"),
            "arm_to_leg": (0.72, "long heavy arms [folklore]"),
            "shoulder_to_hip": (1.65, "broad shoulders on narrower hips (a human man's 1.48) [folklore]"),
            "hands": (1.08, "big hands"), "feet": (1.05, ""), "neck": (0.7, "a short, thick neck"),
            "build": ("muscular", "heavily muscled [folklore]"),
            "bmi": (32.0, "a strongman's BMI (30-35) [measured]; girth scaled to land it"),
            "girth": ({"legs": 1.15, "arms": 1.22, "neck": 1.30, "torso": 1.15}, "heavy muscle"),
            "hunch_deg": (6.0, "a slight forward carriage of the shoulders"),
        },
        "knobs": {"hip_scale": (1.04, ""), "waist_to_hip": ({"female": 0.86, "male": 0.95}, "a thick waist")},
        "look": {"head": {"shape": "square", "shape_weight": 0.8,
                          "features": {"ears_pointed": 0.5, "brow_ridge": 0.8, "nose_size": 0.3, "tusks": 0.7}},
                 "skin": {"palette": [[0.56, 0.63, 0.41], [0.44, 0.52, 0.33], [0.52, 0.53, 0.44], [0.34, 0.40, 0.29]],
                          "regions_off": []},
                 "moves": {"style": None, "notes": "derive_style from stockiness: longer contact, wider stance"}},
        "skin_why": "olive to grey-green; every region kept, its tint along the tone's own hue (skin.species_skin)",
    },
    "goblin": {
        "label": "Goblin: small, scrawny and hunched, a big head with big pointed ears, long arms, green skin",
        "sources": [S["design"], S["dnd"] + ": goblin (Volo's Guide) 3'5\" + 2d4 in, about 1.0-1.2 m"],
        "observables": {
            "stature": ({"female": [0.95, 1.15], "male": [1.00, 1.20]}, "about 1.0-1.2 m [documented, game rules]"),
            "heads": (5.0, "the law gives ~6.1 at 1.1 m: a bigger head [folklore]"),
            "trunk_to_leg": (0.70, "short, bandy legs [folklore]"),
            "fingertips_at": ("knee+0.05", "long arms: fingertips 0.05 H above the knee, a human's ~0.08 [folklore]"),
            "hands": (1.18, "big grasping hands [folklore]"), "feet": (1.2, "big feet [folklore]"),
            "neck": (0.8, "the head carried forward on a short neck"),
            "build": ("scrawny", "scrawny and stringy-limbed: the build word says it, at an adult's BMI (the "
                                 "adult build law); a thinner girth on top read as a child's"),
            "hunch_deg": (26.0, "the hunch [folklore]"), "sway_deg": (-4.0, "a flat lower back under the hunch"),
        },
        "knobs": {"shoulder_scale": (0.92, "narrow, scrawny"), "hip_scale": (0.92, ""),
                  "waist_to_hip": ({"female": 0.90, "male": 0.95}, "a pot belly on a thin body")},
        "look": {"head": {"shape": "triangular", "shape_weight": 0.6,
                          "features": {"ears_pointed": 1.0, "ear_size": 0.9, "brow_ridge": 0.3, "nose_size": 0.7,
                                       "tusks": 0.0}},
                 "skin": {"palette": [[0.62, 0.66, 0.38], [0.50, 0.58, 0.30], [0.55, 0.52, 0.36], [0.40, 0.46, 0.28]],
                          "regions_off": []},
                 "moves": {"style": None, "notes": "the hunch is in the rest pose; a forward-leaning scuttle is a "
                                                   "posture on top"}},
        "skin_why": "yellow-green to olive; every region kept, tone-relative",
    },
    "troll": {
        "label": "Troll: huge (2.4-2.8 m), kyphotic, long-armed (hands to the knee), grey-green, square-cube heavy",
        "sources": [S["design"], S["large_gait"],
                    "Robert Wadlow (gigantism, 2.72 m, 199 kg at 22, BMI 27): how a tall human, not scaled whole, "
                    "carries mass [measured]"],
        "observables": {
            "stature": ({"female": [2.35, 2.70], "male": [2.45, 2.85]}, "the design's 2.4-2.8 m [folklore]"),
            "heads": (7.0, "the law gives ~9.9 at 2.65 m - a giant is small-headed; 7 is the brute's big head "
                           "[folklore]"),
            "trunk_to_leg": (0.77, "a long heavy trunk on shorter legs [folklore]"),
            "fingertips_at": ("knee", "hands to the knee [folklore]"),
            "hands": (1.25, "huge hands"), "feet": (1.12, ""), "neck": (0.6, "the head slung forward"),
            "build": ("heavy", "a heavy human is the start"),
            "bmi": (45.0, "square-cube: a heavy human (BMI 32) scaled whole to 2.65 m would be ~48; a troll is "
                          "bulky but not solid. Girth is solved to land it [measured, scaling law]"),
            "hunch_deg": (32.0, "the hunch [folklore]"),
        },
        "knobs": {"shoulder_scale": (1.28, "massive shoulders"), "hip_scale": (1.12, ""),
                  "waist_to_hip": ({"female": 0.98, "male": 1.02}, "a belly as wide as the hips")},
        "look": {"head": {"shape": "rectangular", "shape_weight": 0.8,
                          "features": {"ears_pointed": 0.3, "brow_ridge": 1.0, "nose_size": 0.6, "tusks": 0.4}},
                 "skin": {"palette": [[0.52, 0.55, 0.48], [0.44, 0.49, 0.40], [0.37, 0.42, 0.35], [0.30, 0.33, 0.29]],
                          "regions_off": []},
                 "moves": {"style": None, "notes": "large-animal gait from the mass (~300 kg): straight legs, duty "
                                                   "factor up, no aerial phase [measured, animals]"}},
        "skin_why": "grey-green, stony; every region kept, tone-relative",
    },
}


def make(sid, spec):
    obs = {n: v for n, (v, _w) in spec["observables"].items()}
    knobs = {n: v for n, (v, _w) in spec["knobs"].items()}
    why = {n: w for n, (_v, w) in list(spec["observables"].items()) + list(spec["knobs"].items()) if w}
    notes = {"stature": spec["observables"]["stature"][1], "skin": spec["skin_why"]}
    return sd.design_from(obs, id=sid, look=spec["look"], sources=spec["sources"], notes=notes, knob_notes=why,
                          **knobs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="solve, design and check, writing nothing")
    ap.add_argument("--explain", help="print one species' table")
    ap.add_argument("--chart", help="write an SVG of every species beside a human")
    args = ap.parse_args()
    docs, bad = {}, []
    for sid, spec in SPECIES.items():
        try:
            docs[sid] = make(sid, spec)
        except sd.DesignError as exc:
            bad.append(str(exc))
            continue
        for c in docs[sid]["design"].get("contradictions", []):
            bad.append(f"{sid}: {c}")
    if bad:
        print("\n".join(bad))
        sys.exit(1)
    print(f"{'species':9} {'H m (male)':>11} {'heads':>5} {'law':>5} {'hip':>6} {'tr/leg':>6} {'US/LS':>5} "
          f"{'reach':>6} {'bmi':>11} {'basis':>6}")
    for sid, d in docs.items():
        p, st = d["proportion"]["male"], d["stature"]["male"]
        print(f"{sid:9} {st[0]:.2f}-{st[1]:.2f}   {d['heads']['any'][0]:5.1f} {d['design']['heads_law']['male']:5.1f} "
              f"{p['hip_fraction']:6.3f} {p['trunk_to_leg']:6.2f} {p['upper_to_lower']:5.2f} "
              f"{p['fingertip_above_knee']:6.3f} {d['bmi'][0]:5.1f}-{d['bmi'][1]:<5.1f} {d['pre_warp']['basis']:>6}")
    h = docs["elf"]["proportion"]["male"]["human"]
    print(f"{'human':9} {'':11} {h['heads']:5.1f} {'':5} {h['hip_fraction']:6.3f} {h['trunk_to_leg']:6.2f} "
          f"{h['upper_to_lower']:5.2f} {h['fingertip_above_knee']:6.3f}")
    if args.explain:
        print(sd.explain(docs[args.explain]))
    if not args.check:
        os.makedirs(OUT_DIR, exist_ok=True)
        for sid, doc in docs.items():
            with open(os.path.join(OUT_DIR, f"{sid}.json"), "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2)
                fh.write("\n")
        print("wrote", len(docs), "species into", OUT_DIR)
    if args.chart:
        sd.chart(list(docs.values()), args.chart)
        print("chart:", args.chart)


if __name__ == "__main__":
    main()
