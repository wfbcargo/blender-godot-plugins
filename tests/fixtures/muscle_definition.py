"""Muscle definition (05 5.5): a delta part authored, stored, weighted by the brief and put on bodies.

- The set is authored from nothing on MPFB's default male (`muscle.seed`: SDF pads, cuts and grooves for
  seven groups, plus the high-passed relief of MPFB's own muscle sculpt) and stored in the harness's
  library; `muscle.find` must read back the same heights.
- `muscle.weights` for three briefs with the same muscle value: Dante's (lean, firm), a soft one (BMI 30,
  slack) and Freya's. The soft body must get much less definition.
- Dante's brief without the forced muscle macro is fitted (`pipeline.make`), defined as geometry, and
  humancheck is run before and after: definition must not break proportions.
- The body's MPFB muscle macro as the fit left it, and the `bulk` weight that gives back the brief's muscle on
  the limbs and shoulders (key `hfd:muscle-bulk`).
- The same body's game path: key at 0, `delta.high_copy`, `bake_for_game`, and lookdev's
  `detail.bake_normal_from_high` onto the baked mesh (512 px here, the matched method), which the card must still
  apply to; then the same bake again, which must leave the skin's texture wired and the Cycles settings as set.
- Transfer: the card on an unfitted woman's MPFB body (another shape, same topology), scaled by stature.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "HF_SCRIPTS")
LOOKDEV = os.environ.get("LD_BLENDER") or os.path.join(H.REPO, "plugins", "lookdev", "blender")
if LOOKDEV not in sys.path:
    sys.path.insert(0, LOOKDEV)

NAME = "FixDante"
DANTE = dict(sex="male", age=27, stature=1.91, build="muscular", seed=3, firmness=0.9, skin=(0.3, 0.18, 0.11))
SOFT = dict(DANTE, build="soft", muscle=0.9, bmi=30.0, firmness=0.25)
FREYA = dict(sex="female", age=26, stature=1.83, build="athletic", seed=21, firmness=0.85)


def _groups(card):
    import numpy as np
    out = {}
    for g, data in card["payload"]["groups"].items():
        v = np.asarray(data["value"], dtype=np.int64)
        out[g] = {"vertices": len(v), "max_um": int(v.max()), "min_um": int(v.min()), "sum_um": int(v.sum()),
                  "hash": hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]}
    return out


def build():
    import bpy
    H.clear_scene()
    import rig_analysis  # noqa: F401
    from rig_analysis import export as ra_export
    import humanform  # noqa: F401
    from humanform import delta, library, measure, muscle, pipeline, scaffold, sheet
    import lookdev_blender
    lookdev_blender.reload_all()
    from lookdev_blender import detail

    card = muscle.seed(store=True)
    again = muscle.find()
    stored = {"id": card["id"], "reference": card["payload"]["reference"], "groups": _groups(card),
              "find_same": again is not None and again["payload"] == card["payload"],
              "index_regions": sorted({c.get("region") for c in library.index()["items"]})}

    briefs = {"dante": DANTE, "soft": SOFT, "freya": FREYA}
    weights = {k: {x: w[x] for x in ("weights", "muscle_term", "body_fat_pct", "definition_total")}
               for k, w in ((k, muscle.weights(sheet.new(name=k, **b))) for k, b in briefs.items())}
    total = {k: v["definition_total"] for k, v in weights.items()}

    made = pipeline.make(sheet.new(name=NAME, **DANTE), use_library=False)
    human = bpy.data.objects[NAME]
    defined = muscle.define(human, sheet.new(name=NAME, **DANTE), card=card, geometry=True)
    hc = measure.run(human.name, preset="realistic", sex="male", build="muscular")
    geometry = {"check_before": H.stable(made["check"]), "check_after": H.stable(hc["counts"]),
                "macros": H.stable(made["macros"]), "applied": H.stable(defined["applied"]),
                "fitted_muscle": defined["fitted_muscle"], "bulk_weight": defined["weights"]["bulk"],
                "applied_bulk": H.stable(defined["applied_bulk"]["groups"]["bulk"]),
                "keys": sorted(k.name for k in human.data.shape_keys.key_blocks if k.name.startswith("hfd:"))}

    key = human.data.shape_keys.key_blocks["hfd:muscle"]
    key.value = 0.0
    high = delta.high_copy(human, "hfd:muscle")
    baked = ra_export.bake_for_game(NAME, NAME + "_rig", name=NAME + "_body")
    if "error" in baked:
        raise RuntimeError("bake: " + baked["error"])
    body = bpy.data.objects[NAME + "_body"]
    sc = bpy.context.scene
    sc.cycles.samples, sc.cycles.use_denoising = 17, True
    tex_dir = os.path.join(H.out_dir(), "muscle_definition")
    nm = detail.bake_normal_from_high(body, high, tex_dir, size=512, material=f"{NAME}_skin")
    if "error" in nm:
        raise RuntimeError("normal bake: " + nm["error"])
    # a re-bake of the same body (a rebuild): the skin keeps a texture with the map, the scene its settings
    nm2 = detail.bake_normal_from_high(body, high, tex_dir, size=512, material=f"{NAME}_skin")
    skin = bpy.data.materials[f"{NAME}_skin"]
    texs = [n.image for n in skin.node_tree.nodes if n.type == "TEX_IMAGE"]
    rebake = {"materials": nm2["materials"], "skipped": nm2["skipped"], "same_stats": nm2["stats"] == nm["stats"],
              "textures": [t.name if t is not None else None for t in texs],
              "cycles_kept": [sc.cycles.samples, sc.cycles.use_denoising] == [17, True]}
    game = {"baked_vertices": len(body.data.vertices), "topology_after_bake": delta.check_topology(body),
            "rebake": rebake,
            "normal_map": {"method": nm["method"], "materials": nm["materials"], "skipped": nm["skipped"],
                           "warnings": nm["warnings"], "steep_texels": nm["stats"]["cleaned_texels"],
                           "over_1deg": round(nm["stats"]["over_1deg"], 3),
                           "over_5deg": round(nm["stats"]["over_5deg"], 3),
                           "p999_deg": round(nm["stats"]["p999_deg"], 0)}}

    r = sheet.resolve(sheet.new(name="FixWomanRef", **FREYA))
    woman = scaffold.create(r["sheet"], name="FixWomanRef")
    moved = delta.apply(woman, card, weights=muscle.weights(r)["weights"])
    transfer = {"stature_m": moved["stature_m"], "scale": moved["scale"], "max_mm": moved["max_mm"],
                "groups": moved["groups"]}

    return {"stored": stored, "weights": weights, "weight_total": total,
            "soft_over_dante": round(total["soft"] / total["dante"], 3),
            "geometry": geometry, "game": H.stable(game), "transfer": H.stable(transfer)}


H.run("muscle_definition", build)
