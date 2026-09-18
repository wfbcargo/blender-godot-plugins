"""Garment presets: the tuned numbers for one garment, named, and the one call that makes it.

    presets.list()                       # ["bra", "briefs", "longsleeve", ...]
    presets.get("sports_top")            # {"cut": "shirt", "tailor": {...}, "ease": {...}, "note": ...}
    wardrobe.dress("Belle", "sports_top", out_path=r"C:/proj/assets/belle/belle_sportstop.glb")

The presets live in `presets/garments.json` in the plugin, each with a `note` saying where its
numbers came from. `dress` runs tailor -> paint_ease -> ease -> skin -> hem -> cover -> spec ->
export with a preset's arguments; a step whose arguments are null is skipped.
"""

from __future__ import annotations

import builtins
import copy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.normpath(os.path.join(HERE, "..", "..", "presets", "garments.json"))
SCHEMA = "wardrobe-presets/1"
CUTS = ("shirt", "pants", "skirt", "dress")


def load():
    with open(PATH, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("schema") != SCHEMA:
        raise ValueError(f"{PATH}: schema {data.get('schema')!r}, expected {SCHEMA!r}")
    return data


def list():  # noqa: A001 - presets.list() reads as it should
    return sorted(load()["garments"])


def get(name):
    """A preset by name, as a fresh dict (changing it changes nothing stored)."""
    garments = load()["garments"]
    if name not in garments:
        raise ValueError(f"no garment preset {name!r}; one of {sorted(garments)}")
    p = copy.deepcopy(garments[name])
    if p.get("cut") not in CUTS:
        raise ValueError(f"preset {name!r}: cut must be one of {CUTS}")
    return p


def exclusive():
    """Groups of presets of which a body wears one at a time."""
    return copy.deepcopy(load().get("exclusive", []))


def _args(d):
    """JSON lists back to the tuples the calls were written with."""
    return {k: tuple(v) if isinstance(v, builtins.list) else v for k, v in (d or {}).items()}


def dress(body_name, preset, name=None, colour=None, out_path=None, layer=None, over=(), soft=False):
    """Cut, fit, skin, hem, hide and export one preset garment on `body_name`.

    `preset` is a preset name or a dict shaped like one. `over`: garments already on the body
    that this one is worn over - it is eased outside them, its hems backstop against them and its
    spec hides what it covers of each. With no `out_path` the spec is written but nothing is
    exported. `soft` (skirts and dresses): no hem bones - the garment goes to follow-through cloth
    as a SoftBody3D pinned at the hips, with the preset's `soft` arguments. Returns the step
    reports; `passed` is False with `problems` when the spec or the export fails - nothing raises
    for that, so a caller decides."""
    from . import cover, export, fit, hem, rigmap, skirts, spec, tailor

    p = get(preset) if isinstance(preset, str) else copy.deepcopy(preset)
    name = name or p.get("name") or (preset if isinstance(preset, str) else "Garment")
    body = rigmap._obj(body_name)
    over = [rigmap._obj(o) for o in (over or ())]
    cut = {"pants": tailor.pants, "skirt": tailor.skirt, "dress": tailor.dress}.get(p["cut"], tailor.shirt)
    if soft and p["cut"] not in skirts.KINDS:
        raise ValueError(f"soft=True routes skirts and dresses to cloth; {p['cut']!r} is neither")

    g = cut(body, name=name, **_args(p.get("tailor")))
    painted = fit.paint_ease(g, **_args(p["paint"])) if p.get("paint") is not None else None
    # null ease: skipped - a built skirt carries its ease already, and relaxing a tube shrinks it off its flare
    er = fit.ease(g, body, over=over, **_args(p["ease"])) if p.get("ease") is not None else None
    sk = fit.skin(g, body)
    hr = None
    cloth = None
    if soft:
        cloth = skirts.soft_body(g, body, **_args(p.get("soft")))
    elif p.get("hem") is not None:
        hr = hem.prepare(g, body, under=over, **_args(p["hem"]))
    cr = cover.compute(g, body, **_args(p.get("cover")))
    lifted = None
    behind = (p.get("cover") or {}).get("behind") or 0.0
    if behind > 0:
        # a compression garment eased inside the skin: lift it over skin the engine still draws
        lifted = []
        for _ in range(4):
            tris = cover.drawn_over_cloth(g, body, cr, reach=behind)
            if not tris:
                break
            lift = p.get("lift") or {}
            gap = lift.get("gap", (p.get("ease") or {}).get("base", 0.006))
            lifted.append({"tris": len(tris), "verts_moved": fit.lift_over(g, body, tris, gap, smooth=lift.get("smooth", 0.0))})
            cr = cover.compute(g, body, **_args(p.get("cover")))
        if lifted and er is not None:
            er["detail"] = fit.detail(g, body, limit=(p.get("ease") or {}).get("detail_limit"))   # of the cloth as lifted
    layers = {o: cover.compute(g, o, **_args(p.get("layer_cover"))) for o in over}
    s = spec.build(g, body, cr, hr, er, kind=p.get("spec_kind", p["cut"]),
                   layer=layer if layer is not None else p.get("layer"), layers=layers or None)
    problems = spec.write(g, s)
    report = {
        "garment": g.name, "preset": preset if isinstance(preset, str) else None, "body": body.name,
        "verts": len(g.data.vertices), "groups": len(g.vertex_groups),
        "cut": dict(g["wardrobe_cut_report"]), "painted": painted, "ease": er, "skin": sk,
        **({"lifted": lifted} if lifted is not None else {}),
        # folds in the cloth (see fit.folds): lift_over's per-corner cones and the cloth tucked into
        # the fold under Belle's bust made a faceted, pointed shelf there (improvements NEXT 9)
        **fit.folds(g),
        "hem": hr["rings"] if hr else None, "hem_bones": len(hr["block"]["bones"]) if hr else 0,
        "cover": cover.summarize(cr), "cover_report": {k: v for k, v in cr.items() if not k.startswith("_")},
        "layers": {o.name: {"hidden": r["hidden"], "tris_hidden": r["tris_hidden"]} for o, r in layers.items()},
        "jiggle_groups": sorted({vg.name for vg in g.vertex_groups if vg.name.startswith("ft_jiggle_")}),
        "spec_problems": problems, "export": None, "export_report": None, "exported": False,
        "cloth": _cloth_summary(cloth),
    }
    # the preset's `ease.detail_limit`: a compression garment that still carries more of the skin's
    # own relief than the limit fails - and so does one whose limited region was never measured.
    # A skirt or dress has no ease step (`er` None): there is no relief to have measured.
    detail = builtins.list(((er or {}).get("detail") or {}).get("problems") or [])
    if cr.get("drawn_over_cloth"):
        detail.append("cover: %d drawn body triangles still lie over the cloth after lifting it" % cr["drawn_over_cloth"])
    if problems:
        report.update(passed=False, problems=[f"spec: {x}" for x in problems] + detail)
        return report
    if out_path is None:
        report.update(passed=not detail, problems=detail)
        return report
    rgb = tuple(colour if colour is not None else p.get("colour") or (0.2, 0.42, 0.75))
    m = export.garment(g.name, out_path, colour=rgb)
    report.update(export=export.summarize(m), export_report=m, exported=bool(m.get("exported")),
                  passed=bool(m.get("passed")) and not detail,
                  problems=([] if m.get("passed") else [export.summarize(m)]) + detail)
    if cloth is not None and report["exported"]:
        # the cloth's pins must land on vertices of the file too, or in Godot the skirt falls
        from follow_through import export as ft_export
        fm = ft_export.verify(os.path.abspath(out_path))
        report["cloth_export"] = ft_export.summarize(fm)
        if not fm.get("passed"):
            report["passed"] = False
            report["problems"].append("cloth: " + report["cloth_export"])
    return report


def _cloth_summary(r):
    if r is None:
        return None
    s = r.get("spec", {})
    return {"fabric": r.get("fabric"), "class": s.get("class"), "pins": s.get("pins", {}).get("count"),
            "anchor": s.get("pins", {}).get("anchor"), "soft_body": s.get("soft_body"),
            "hops_from_pins": r.get("hops_from_pins"), "declined": r.get("declined"), "error": r.get("error")}
