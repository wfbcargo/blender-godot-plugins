"""follow-through's sample bodies, rigged, walked, fleshed and exported.

`samples.build_bodies` makes `Figure` (breasts, buttocks, a small belly) and `Bloater` (a swollen
belly, moobs, love handles) from lofted sections, rigs each with rig-anything's `fit_basic_human`,
binds it and gives it a contact-locomotion walk. `flesh.prepare` then finds the soft masses and
hangs a sprung jiggle bone in each. What the golden holds is where those regions landed and how
big they are - the measurement that decides whether a breast bone ends up on a chin.

The export is read back by `follow_through.export.verify`, which checks every jiggle bone is in
the skin where the spec puts it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "FT_SCRIPTS")


def region_row(r):
    """One region, as a golden can hold it: what it is, where it sits, how far it stands out.

    Its `vertices` is an index array; the golden keeps how many, because the indices themselves
    are 30 kB per body of numbers no one can read a diff of."""
    keep = ("type", "name", "side", "peak_m", "area_m2", "volume_m3", "anchor",
            "bone", "frequency_hz", "damping_ratio", "max_offset_m", "mass_kg")
    row = {k: r[k] for k in keep if k in r}
    if r.get("vertices") is not None:
        row["vertex_count"] = len(r["vertices"])
    for k in ("centroid", "head", "tail", "normal", "peak", "base"):
        if k in r and r[k] is not None:
            row[k] = H.stable(r[k])
    return row


def build():
    import bpy
    H.clear_scene()
    H.enable_addons("rigify")
    from follow_through import export as ft_export, flesh, samples

    made = samples.build_bodies(rig=True, walk=True, rig_anything=H.scripts("RA_SCRIPTS"))
    bodies = {}
    out = os.path.join(H.out_dir(), "flesh_figure")
    os.makedirs(out, exist_ok=True)
    from rig_analysis import export as ra_export

    # The samples build in a scene of their own; the exporter works on the active one.
    window = bpy.context.window
    previous, window.scene = window.scene, bpy.data.scenes[made["scene"]]
    try:
        bodies = _each(made, out, ra_export, ft_export, flesh)
    finally:
        window.scene = previous
    return {"scene": made["scene"], "bodies": bodies}


def _each(made, out, ra_export, ft_export, flesh):
    import bpy
    bodies = {}
    for name in made["bodies"]:
        prepared = flesh.prepare(name)
        regions = [region_row(r) for r in prepared.get("regions", [])]
        regions.sort(key=lambda r: (r.get("type", ""), r.get("name", "")))
        path = os.path.join(out, name.lower() + ".glb")
        exported = ra_export.export(name, name + "_metarig", path, foot_bones=["foot.L", "foot.R"],
                                    actions=[name + "Walk"], loop_clips=[name + "Walk"], forward="-Y")
        verified = ft_export.verify(path, expect_meshes=[name]) if exported.get("exported") else None
        bodies[name] = {
            "mesh": {"vertices": len(bpy.data.objects[name].data.vertices)},
            "bind_coverage": made["bodies"][name].get("coverage"),
            "walk": H.stable(made["bodies"][name].get("walk")),
            "regions": regions,
            "region_count": len(regions),
            "prepare": H.stable({k: v for k, v in prepared.items() if k != "regions"}),
            "exported": exported.get("exported"),
            "durations_match": (exported.get("verified") or {}).get("durations_match"),
            "read_back": H.stable(verified) if verified else None,
        }
    return bodies


H.run("flesh_figure", build)
