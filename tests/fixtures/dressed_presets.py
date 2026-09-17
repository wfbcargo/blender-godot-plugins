"""Belle's two garments, from wardrobe's presets, on the fleshed sample body.

`wardrobe.dress(body, preset)` runs a named preset's tailor, ease, skin, cover, spec and export
arguments - the numbers `grungist-creek`'s build_belle.py held until they moved into the plugin.
The `sports_top` and `shorts_mid_thigh` presets go onto the fleshed `Figure`, as `dressed_figure`
builds it, and so do the compression presets `compression_shorts` and `leggings`, each on its own. The golden holds each garment's cut, ease and covered-skin counts and its export, so a
change to a preset or to the steps it runs shows up here.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS")

BODY = "Figure"
# sports_top, compression_shorts and leggings are compression garments (improvements 05 5.3): their
# `ease.detail` says how much of the skin's curvature they keep, `lifted` what cover lifted them over
PRESETS = ("sports_top", "shorts_mid_thigh", "compression_shorts", "leggings")


def build():
    import bpy
    H.clear_scene()
    from follow_through import flesh, samples
    import wardrobe

    made = samples.build_bodies(rig=True, walk=True, rig_anything=H.scripts("RA_SCRIPTS"))
    window = bpy.context.window
    previous, window.scene = window.scene, bpy.data.scenes[made["scene"]]
    try:
        prepared = flesh.prepare(BODY)
        body = bpy.data.objects[BODY]
        H.shuffle_faces(body)                       # off unless REGRESS_SHUFFLE_FACES=1 (5.6)
        out = os.path.join(H.out_dir(), "dressed_presets")
        os.makedirs(out, exist_ok=True)
        garments = {}
        for preset in PRESETS:
            r = wardrobe.dress(BODY, preset, out_path=os.path.join(out, preset + ".glb"))
            garments[preset] = {
                "garment": r["garment"],
                "vertices": r["verts"],
                "groups": r["groups"],
                "cut": H.stable(r["cut"]),
                "jiggle_groups": len(r["jiggle_groups"]),
                "exported": r["exported"],
                "passed": r["passed"],
                "problems": r["problems"],
                "ease": H.stable(r["ease"]),
                "lifted": r.get("lifted"),
                "hem_rings": H.stable(r["hem"]),
                "cover": H.stable(r["cover_report"]),
                "export": H.stable(r["export_report"]),
            }
        # The body walking, for `regress.py --godot`: wardrobe's verifier wears both garments on it.
        from rig_analysis import export as ra_export
        walk = BODY + "Walk"
        body_glb = ra_export.export(BODY, BODY + "_metarig", os.path.join(out, "figure.glb"),
                                    foot_bones=["foot.L", "foot.R"], actions=[walk], loop_clips=[walk],
                                    forward="-Y")
        return {
            "body_export": {"exported": body_glb.get("exported"),
                            "durations_match": (body_glb.get("verified") or {}).get("durations_match")},
            "body": {"vertices": len(body.data.vertices),
                     "jiggle_bones": sum(1 for g in body.vertex_groups if g.name.startswith("ft_jiggle_")),
                     "flesh_regions": len(prepared.get("regions", []))},
            "garments": garments,
        }
    finally:
        window.scene = previous


H.run("dressed_presets", build)
