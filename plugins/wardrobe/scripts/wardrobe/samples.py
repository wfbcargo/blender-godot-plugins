"""The sample: a T-shirt on follow-through's sample Figure, from cut to glb.

    samples.shirt("Figure", r"C:/proj/assets/wardrobe/shirt.glb")

Every step prints what it measured. The body must be rigged (rig-anything) and may carry
follow-through jiggle bones - the shirt then follows them, because it is cut with their weights.
"""

from __future__ import annotations

from . import cover, export, fit, hem, spec, tailor


def shirt(body, out_path, name="Shirt", sleeve=0.45, hem_at=-0.05, neck=(-0.04, 0.12), fabric="cotton_jersey",
          colour=(0.2, 0.42, 0.75), agree=0.7, margin=0.03, hem_bones=8, cuff_bones=4, log=print):
    g = tailor.shirt(body, name=name, sleeve=sleeve, hem=hem_at, neck=neck)
    log("cut", dict(g["wardrobe_cut_report"]), len(g.data.vertices), "verts")
    log("ease painted", fit.paint_ease(g))
    er = fit.ease(g, body)
    log("eased", er)
    log("skinned", fit.skin(g, body))
    hr = hem.prepare(g, body, fabric=fabric, hem_bones=hem_bones, cuff_bones=cuff_bones)
    log(hem.summarize(hr))
    cr = cover.compute(g, body, agree=agree, margin=margin)
    log(cover.summarize(cr))
    s = spec.build(g, body, cr, hr, er, kind="shirt")
    problems = spec.write(g, s)
    if problems:
        log("spec problems", problems)
        return {"exported": False, "problems": problems}
    m = export.garment(g.name, out_path, colour=colour)
    log(export.summarize(m))
    return {"exported": m.get("exported", False), "passed": m.get("passed", False), "export": m, "cover": {
        k: v for k, v in cr.items() if not k.startswith("_")}, "hem": hr["rings"], "ease": er}
