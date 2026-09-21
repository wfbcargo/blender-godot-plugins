"""The loose tops, from wardrobe's presets, on the fleshed sample body.

`tshirt` and `longsleeve` are what the cast wears (Marco, Ruth) and until this fixture no fixture
dressed either, so a change to them reached the characters with nothing but their own limits
between. The golden holds each garment's cut, ease - `detail` and `tuck` among it - and covered
skin, and its export; `regress.py --godot` walks the tee on the body.

The control is the longsleeve eased as wardrobe 0.6.0 did it - hanging only from a third of the way
down the torso, rows not made convex, no evening of heights - and it must fail `tuck_limit`: the
cloth follows the breast's underside back in to the fold (improvements NEXT, "Cloth that hugs the
skin"). Its verdict is in the golden.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS")

BODY = "Figure"
PRESETS = ("tshirt", "longsleeve")
# wardrobe 0.6.0's hang, on the longsleeve preset: what the tuck check exists to catch
TUCKED = {"hang_top": 0.3, "hang_fade": 0.25, "hang_hull": False, "hang_blur": [2, 2],
          "iterations": 16, "settle": 0.0}


def _row(r):
    return {
        "garment": r["garment"],
        "vertices": r["verts"],
        "cut": H.stable(r["cut"]),
        "exported": r["exported"],
        "passed": r["passed"],
        "problems": r["problems"],
        "ease": H.stable(r["ease"]),
        "folded_faces": r.get("folded_faces"),
        "hem_rings": H.stable(r["hem"]),
        "cover": H.stable(r["cover_report"]),
        "export": H.stable(r["export_report"]),
    }


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
        prepared = flesh.prepare(BODY)
        body = bpy.data.objects[BODY]
        H.shuffle_faces(body)                       # off unless REGRESS_SHUFFLE_FACES=1 (5.6)
        out = os.path.join(H.out_dir(), "dressed_loose")
        os.makedirs(out, exist_ok=True)
        garments = {}
        for preset in PRESETS:
            r = wardrobe.dress(BODY, preset, out_path=os.path.join(out, preset + ".glb"))
            garments[preset] = _row(r)
            if preset != "tshirt":
                # one top on the body at a time: the next is cut from the skin, not from the tee
                bpy.data.objects.remove(bpy.data.objects[r["garment"]], do_unlink=True)
        from rig_analysis import export as ra_export
        walk = BODY + "Walk"
        body_glb = ra_export.export(BODY, BODY + "_metarig", os.path.join(out, "figure.glb"),
                                    foot_bones=["foot.L", "foot.R"], actions=[walk], loop_clips=[walk],
                                    forward="-Y")
        # the control, after the export so it touches nothing that ships
        p = presets.get("longsleeve")
        p["ease"].update(TUCKED)
        c = wardrobe.dress(BODY, p, name="Tucked")
        control = {"passed": c["passed"], "problems": c["problems"], "tuck": H.stable(c["ease"].get("tuck")),
                   "detail_passed": c["ease"]["detail"].get("passed")}
        return {
            "body_export": {"exported": body_glb.get("exported"),
                            "durations_match": (body_glb.get("verified") or {}).get("durations_match")},
            "body": {"vertices": len(body.data.vertices),
                     "jiggle_bones": sum(1 for g in body.vertex_groups if g.name.startswith("ft_jiggle_")),
                     "flesh_regions": len(prepared.get("regions", []))},
            "garments": garments,
            "control_tucked": control,
        }
    finally:
        window.scene = previous


H.run("dressed_loose", build)
