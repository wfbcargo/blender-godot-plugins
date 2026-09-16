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
CUTS = ("shirt", "pants")


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


def dress(body_name, preset, name=None, colour=None, out_path=None, layer=None, over=()):
    """Cut, fit, skin, hem, hide and export one preset garment on `body_name`.

    `preset` is a preset name or a dict shaped like one. `over`: garments already on the body
    that this one is worn over - it is eased outside them, its hems backstop against them and its
    spec hides what it covers of each. With no `out_path` the spec is written but nothing is
    exported. Returns the step reports; `passed` is False with `problems` when the spec or the
    export fails - nothing raises for that, so a caller decides."""
    from . import cover, export, fit, hem, rigmap, spec, tailor

    p = get(preset) if isinstance(preset, str) else copy.deepcopy(preset)
    name = name or p.get("name") or (preset if isinstance(preset, str) else "Garment")
    body = rigmap._obj(body_name)
    over = [rigmap._obj(o) for o in (over or ())]
    cut = tailor.pants if p["cut"] == "pants" else tailor.shirt

    g = cut(body, name=name, **_args(p.get("tailor")))
    painted = fit.paint_ease(g, **_args(p["paint"])) if p.get("paint") is not None else None
    er = fit.ease(g, body, over=over, **_args(p.get("ease")))
    sk = fit.skin(g, body)
    hr = None
    if p.get("hem") is not None:
        hr = hem.prepare(g, body, under=over, **_args(p["hem"]))
    cr = cover.compute(g, body, **_args(p.get("cover")))
    layers = {o: cover.compute(g, o, **_args(p.get("layer_cover"))) for o in over}
    s = spec.build(g, body, cr, hr, er, kind=p.get("spec_kind", p["cut"]),
                   layer=layer if layer is not None else p.get("layer"), layers=layers or None)
    problems = spec.write(g, s)
    report = {
        "garment": g.name, "preset": preset if isinstance(preset, str) else None, "body": body.name,
        "verts": len(g.data.vertices), "groups": len(g.vertex_groups),
        "cut": dict(g["wardrobe_cut_report"]), "painted": painted, "ease": er, "skin": sk,
        "hem": hr["rings"] if hr else None, "hem_bones": len(hr["block"]["bones"]) if hr else 0,
        "cover": cover.summarize(cr), "cover_report": {k: v for k, v in cr.items() if not k.startswith("_")},
        "layers": {o.name: {"hidden": r["hidden"], "tris_hidden": r["tris_hidden"]} for o, r in layers.items()},
        "jiggle_groups": sorted({vg.name for vg in g.vertex_groups if vg.name.startswith("ft_jiggle_")}),
        "spec_problems": problems, "export": None, "export_report": None, "exported": False,
    }
    if problems:
        report.update(passed=False, problems=[f"spec: {x}" for x in problems])
        return report
    if out_path is None:
        report.update(passed=True, problems=[])
        return report
    rgb = tuple(colour if colour is not None else p.get("colour") or (0.2, 0.42, 0.75))
    m = export.garment(g.name, out_path, colour=rgb)
    report.update(export=export.summarize(m), export_report=m, exported=bool(m.get("exported")),
                  passed=bool(m.get("passed")), problems=[] if m.get("passed") else [export.summarize(m)])
    return report
