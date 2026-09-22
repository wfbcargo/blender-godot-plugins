"""A body with relief on it, dressed compressed and uncompressed: the garment detail check itself.

`follow_through.samples`' `Figure` is smooth - its breasts have no nipples and its seat no fold -
so on it a compression garment has nothing to hide and `fit.detail` reports nothing either way.
That made the check untestable: every limit passed whatever the garment did. So this fixture
embosses the body first. Each breast and buttock gets a 12 mm bump, 18 mm wide, at the vertex where
its jiggle weight peaks - deliberately larger than a real nipple, so the limits are crossed by a
margin no rounding reaches, and deterministic because the peak vertex and the falloff are functions
of the mesh. Since follow-through 0.8.0 grades the weight from the attachment to the apex, that vertex
is at the breast's apex, 1.9 cm from it; the plateau before put it in the cleavage, 4.5 cm off, where
the top's span hid it.

Then the garments go on six ways, and the golden holds what the check said each time:

- `sports_top` as the preset ships it - compressed - keeps a fraction of that relief and passes.
- the same cut and ease with `smooth` and `flatten` removed traces it and **fails its own limit**:
  the report's `passed` is false and `problems` names the millimetres. Without this there is no
  fixture in which a detail limit fails, and a regression that stopped the check looking would
  not move a single golden number.
- `sports_top` pressed into the bust (`flatten` 0.5, which the preset does not ship) presses the
  cloth inside the bumps, so skin stands through it: `cover.compute(behind=)` reports
  `drawn_over_cloth`, `wardrobe.dress` lifts the cloth over those triangles and re-measures, and
  `lifted` records each round. That is the only path in the suite through `cover.drawn_over_cloth`
  and `fit.lift_over`, and it carries a per-region limit, which the shipped presets' `all` does not.
  It lifts smoothly (`lift.smooth`, as sports_top ships); `top_pressed_cone_lift` is the same with
  the per-corner cones that folded Belle's top into a shelf (improvements NEXT 9), and each records
  `folded_faces` and `sharp_edges` (fit.folds). `top_unspanned` is the shipped top without `span`,
  the cloth left following the body's hollows instead of stretched across them.
- `sports_top` with a limit on the buttocks, which no top covers: **unmeasured, and so failed**. A
  limit nothing was measured against has not been held (wardrobe 0.2.2 said the same of `verify`),
  and this is the body type it matters on - on a character-pipeline MPFB woman follow-through's
  breast search landed on the jaw until 0.7.0, and a breast limit there measured nothing at all.
- last, the control: `cover.drawn_over_cloth` on the shipped top before any lift, with its facing test
  (`FACING_MIN`) and without. Without it, skin beside the armholes' rims counts as skin through the
  cloth (`flagged_without_test` above 0); with it, none (`flagged_with_test` 0).
- `compression_shorts` shipped and uncompressed, the same pair over the buttocks.

The bodies are the `dressed_presets` bodies, so a change to the cut or the ease shows up in both;
what is new here is only the relief and the limits it makes it possible to hold.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS")

BODY = "Figure"
BUMP_M = 0.012          # how far the relief stands off the skin
BUMP_SIGMA_M = 0.018    # its Gaussian width
BUMP_TYPES = ("breast", "butt")


def emboss(body):
    """Raise a bump on each flesh region, at the vertex where its jiggle weight peaks.

    Returns the vertices raised, so a change to the sample body or to how flesh weights it shows
    up here rather than quietly moving the relief somewhere else."""
    import numpy as np

    co = np.array([tuple(v.co) for v in body.data.vertices])
    no = np.array([tuple(v.normal) for v in body.data.vertices])
    peaks = {}
    for r in body["follow_through"]["jiggle"]["regions"]:
        if r.get("type") not in BUMP_TYPES:
            continue
        gi = body.vertex_groups[r["bone"]].index
        w = np.zeros(len(co))
        for v in body.data.vertices:
            for x in v.groups:
                if x.group == gi:
                    w[v.index] = x.weight
        # the strongest weight, ties to the lowest index: the mesh alone decides where the bump goes
        apex = int(np.lexsort((np.arange(len(w)), -w))[0])
        peaks[r["name"]] = apex
        d = np.linalg.norm(co - co[apex], axis=1)
        co = co + (BUMP_M * np.exp(-(d / BUMP_SIGMA_M) ** 2))[:, None] * no
    body.data.vertices.foreach_set("co", co.ravel())
    body.data.update()
    return peaks


def uncompressed(p):
    """The same preset with the compression taken out: the cloth is eased off the skin itself."""
    p = dict(p)
    p["ease"] = {k: v for k, v in p["ease"].items() if k not in ("smooth", "flatten")}
    p["cover"] = {k: v for k, v in (p.get("cover") or {}).items() if k != "behind"}
    return p


def build():
    import bpy
    H.clear_scene()
    from follow_through import flesh, samples
    import wardrobe
    from wardrobe import presets

    made = samples.build_bodies(rig=True, walk=True, rig_anything=H.scripts("RA_SCRIPTS"))
    window = bpy.context.window
    previous, window.scene = window.scene, bpy.data.scenes[made["scene"]]
    try:
        flesh.prepare(BODY)
        body = bpy.data.objects[BODY]
        H.shuffle_faces(body)                       # off unless REGRESS_SHUFFLE_FACES=1 (5.6)
        peaks = emboss(body)
        out = os.path.join(H.out_dir(), "traced_detail")
        os.makedirs(out, exist_ok=True)

        top, shorts = presets.get("sports_top"), presets.get("compression_shorts")
        wearings = {
            "top_compressed": top,
            "top_uncompressed": uncompressed(top),
            "top_pressed": dict(top, ease=dict(top["ease"], flatten={"breast": 0.5},
                                               detail_limit={"all": 0.06, "breast": 0.1})),
            # the same, lifted per corner as before the smooth lift (`lift` removed): the cones it
            # pushes up can fold the cloth - `folded_faces` says whether they did here
            "top_pressed_cone_lift": dict(top, lift=None, ease=dict(top["ease"], flatten={"breast": 0.5},
                                                                    detail_limit={"all": 0.06, "breast": 0.1})),
            "top_unspanned": dict(top, ease={k: v for k, v in top["ease"].items() if k != "span"}),
            "top_limit_elsewhere": dict(top, ease=dict(top["ease"], detail_limit={"butt": 0.1})),
            "shorts_compressed": shorts,
            "shorts_uncompressed": uncompressed(shorts),
        }
        garments = {}
        for tag, p in wearings.items():
            r = wardrobe.dress(BODY, dict(p, name=p["name"] + "_" + tag),
                               out_path=os.path.join(out, tag + ".glb"))
            garments[tag] = {
                "vertices": r["verts"],
                "detail": H.stable(r["ease"]["detail"]),
                "compression": H.stable({k: v for k, v in (r["ease"].get("compression") or {}).items()
                                         if k in ("passes", "moved_max_m", "moved_p95_m", "flatten",
                                                  "inside_skin_verts", "settle", "span")}),
                "lifted": r.get("lifted"),
                "folded_faces": r.get("folded_faces"),
                "sharp_edges": r.get("sharp_edges"),
                "creased": r["cover_report"].get("creased"),
                "drawn_over_cloth": r["cover_report"].get("drawn_over_cloth"),
                "inside": r["cover_report"].get("inside"),
                "hidden": r["cover_report"]["hidden"],
                "exported": r["exported"],
                "passed": r["passed"],
                "problems": r["problems"],
            }

        # the control: `drawn_over_cloth` on the shipped top before any lift, with its facing test (wardrobe 0.5.2)
        # and without. Without it, skin beside the armholes' rims counts as skin through the cloth - `without` must
        # be above 0, and `with` must stay 0. Dressing with the test off was the control first, but whether its
        # lifts ran away hung on the shoulder's exact weights (follow-through 0.9.0's 0.98 cap stopped it)
        from wardrobe import cover as wd_cover, fit as wd_fit, tailor as wd_tailor
        from wardrobe.presets import _args
        g = wd_tailor.shirt(body, name=top["name"] + "_rim", **_args(top.get("tailor")))
        wd_fit.ease(g, body, **_args(top["ease"]))
        wd_fit.skin(g, body)
        cr = wd_cover.compute(g, body, **_args(top.get("cover")))
        reach = top["cover"]["behind"]
        flagged_with = wd_cover.drawn_over_cloth(g, body, cr, reach=reach)
        kept, wd_cover.FACING_MIN = wd_cover.FACING_MIN, -2.0
        try:
            flagged_without = wd_cover.drawn_over_cloth(g, body, cr, reach=reach)
        finally:
            wd_cover.FACING_MIN = kept
        garments["control_facing_test"] = {"flagged_with_test": len(flagged_with),
                                           "flagged_without_test": len(flagged_without),
                                           "dropped_by_test": len(set(flagged_without) - set(flagged_with))}

        from rig_analysis import export as ra_export
        walk = BODY + "Walk"
        body_glb = ra_export.export(BODY, BODY + "_metarig", os.path.join(out, "figure.glb"),
                                    foot_bones=["foot.L", "foot.R"], actions=[walk], loop_clips=[walk],
                                    forward="-Y")
        return {
            "body": {"vertices": len(body.data.vertices), "bump_m": BUMP_M,
                     "bump_sigma_m": BUMP_SIGMA_M, "peaks": peaks},
            "body_export": {"exported": body_glb.get("exported")},
            "garments": garments,
        }
    finally:
        window.scene = previous


H.run("traced_detail", build)
