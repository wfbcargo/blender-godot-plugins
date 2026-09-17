"""Skirts and a dress, built round the fleshed sample body from wardrobe's presets.

`tailor.skirt` and `tailor.dress` do not cut the garment from the skin: they build a tube round the
body (rays to its surface, hanging from the widest point, flaring to a hem sized against the widest hip
girth) and weight it to the skin where it lies on it and to the pelvis and thighs by distance where it
hangs. `skirt_knee`, `skirt_mini` and `dress_sleeveless` go onto `Figure` as `dressed_presets` builds it,
and `skirt_knee` a second time with `soft=True`, routed to follow-through cloth. The golden holds each
garment's rings, girths, weight shares, hem, covered-skin counts and export, and the cloth spec, so a change
to the build or the presets shows up here.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "FT_SCRIPTS", "WD_SCRIPTS")

BODY = "Figure"
GARMENTS = (("skirt_knee", "SkirtKnee", False), ("skirt_mini", "SkirtMini", False),
            ("dress_sleeveless", "Dress", False), ("skirt_knee", "SkirtSoft", True))


def _shares(obj, hm):
    """Mean weight on the thighs, the pelvis and hem bones, over the garment's vertices."""
    names = {vg.index: vg.name for vg in obj.vertex_groups}
    thighs = {l["thigh"] for l in hm["legs"].values()}
    pelvis = hm["spine"][0]
    acc = {"thighs": 0.0, "pelvis": 0.0, "hem_bones": 0.0}
    for v in obj.data.vertices:
        for x in v.groups:
            n = names[x.group]
            if n in thighs:
                acc["thighs"] += x.weight
            elif n == pelvis:
                acc["pelvis"] += x.weight
            elif n.startswith("wd_"):
                acc["hem_bones"] += x.weight
    return {k: x / max(1, len(obj.data.vertices)) for k, x in acc.items()}


def build():
    import bpy
    H.clear_scene()
    from follow_through import flesh, samples
    import wardrobe
    from wardrobe import rigmap

    made = samples.build_bodies(rig=True, walk=True, rig_anything=H.scripts("RA_SCRIPTS"))
    window = bpy.context.window
    previous, window.scene = window.scene, bpy.data.scenes[made["scene"]]
    try:
        prepared = flesh.prepare(BODY)
        body = bpy.data.objects[BODY]
        H.shuffle_faces(body)                       # off unless REGRESS_SHUFFLE_FACES=1 (5.6)
        hm = rigmap.humanoid(body)
        out = os.path.join(H.out_dir(), "dressed_skirts")
        os.makedirs(out, exist_ok=True)
        garments = {}
        for preset, name, soft in GARMENTS:
            r = wardrobe.dress(BODY, preset, name=name, soft=soft, out_path=os.path.join(out, name.lower() + ".glb"))
            g = bpy.data.objects[r["garment"]]
            garments[name] = {
                "preset": preset, "soft": soft,
                "vertices": r["verts"],
                "cut": H.stable(r["cut"]),
                "cut_record": H.stable({k: v for k, v in g["wardrobe_cut"].items() if k != "body"}),
                "shares": H.stable(_shares(g, hm)),
                "face_order": H.face_order(g),
                "exported": r["exported"],
                "passed": r["passed"],
                "problems": r["problems"],
                "hem_rings": H.stable(r["hem"]),
                "cover": H.stable(r["cover_report"]),
                "export": H.stable(r["export_report"]),
                "cloth": H.stable(r["cloth"]),
            }
        # The body walking, for `regress.py --godot`: wardrobe's verifier wears the knee skirt on it.
        from rig_analysis import export as ra_export
        walk = BODY + "Walk"
        body_glb = ra_export.export(BODY, BODY + "_metarig", os.path.join(out, "figure.glb"),
                                    foot_bones=["foot.L", "foot.R"], actions=[walk], loop_clips=[walk],
                                    forward="-Y")
        return {
            "body_export": {"exported": body_glb.get("exported"),
                            "durations_match": (body_glb.get("verified") or {}).get("durations_match")},
            "body": {"vertices": len(body.data.vertices), "flesh_regions": len(prepared.get("regions", []))},
            "garments": garments,
        }
    finally:
        window.scene = previous


H.run("dressed_skirts", build)
