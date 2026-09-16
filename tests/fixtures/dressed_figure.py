"""A shirt cut, eased, skinned, hemmed and exported onto a fleshed sample body.

The wardrobe path, in the order the plugins require: rig and walk the body, flesh it, and only
then cut the garment - a garment cut first inherits skin weights that have no jiggle bones in
them. The golden holds the cut, the ease, the hem rings and the covered-skin counts, which is
where a fit change shows up first.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS")

BODY = "Figure"


def build():
    import bpy
    H.clear_scene()
    H.enable_addons("rigify")
    from follow_through import flesh, samples
    from wardrobe import samples as wd_samples

    made = samples.build_bodies(rig=True, walk=True, rig_anything=H.scripts("RA_SCRIPTS"))
    window = bpy.context.window
    previous, window.scene = window.scene, bpy.data.scenes[made["scene"]]
    try:
        prepared = flesh.prepare(BODY)
        body = bpy.data.objects[BODY]
        # A fit must not depend on how the body's faces happen to be stored (5.6). Off by default;
        # `REGRESS_SHUFFLE_FACES=1 regress.py --twice` checks it.
        H.shuffle_faces(body)
        out = os.path.join(H.out_dir(), "dressed_figure")
        os.makedirs(out, exist_ok=True)
        shirt = wd_samples.shirt(body, os.path.join(out, "shirt.glb"), log=lambda *a: None)
        garment = bpy.data.objects.get("Shirt")
        # The body the shirt was cut from, walking, for `regress.py --godot`: wardrobe's verifier
        # dresses this body with this shirt in Godot and counts holes and poke-through.
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
            "garment": {"vertices": len(garment.data.vertices) if garment else None,
                        "groups": len(garment.vertex_groups) if garment else None},
            "exported": shirt.get("exported"),
            "passed": shirt.get("passed"),
            "ease": H.stable(shirt.get("ease")),
            "hem_rings": H.stable(shirt.get("hem")),
            "cover": H.stable(shirt.get("cover")),
            "export": H.stable(shirt.get("export")),
        }
    finally:
        window.scene = previous


H.run("dressed_figure", build)
