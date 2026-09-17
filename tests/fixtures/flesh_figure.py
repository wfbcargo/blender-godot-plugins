"""follow-through's sample bodies, rigged, walked, fleshed and exported.

`samples.build_bodies` makes `Figure` (breasts, buttocks, a small belly) and `Bloater` (a swollen
belly, moobs, love handles) from lofted sections, rigs each with rig-anything's `fit_basic_human`,
binds it and gives it a contact-locomotion walk. `flesh.prepare` then finds the soft masses and
hangs a sprung jiggle bone in each. What the golden holds is where those regions landed and how
big they are - the measurement that decides whether a breast bone ends up on a chin.

Each body is given an Idle after its flesh and goes out through rig-anything's
`export_character`, which writes the `.moves.json` `regress.py --godot` plays. The export is read
back by `follow_through.export.verify`, which checks every jiggle bone is in the skin where the
spec puts it.
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
    from follow_through import export as ft_export, flesh, samples

    made = samples.build_bodies(rig=True, walk=True, rig_anything=H.scripts("RA_SCRIPTS"))
    bodies = {}
    out = os.path.join(H.out_dir(), "flesh_figure")
    os.makedirs(out, exist_ok=True)
    from rig_analysis import actions, export as ra_export

    # The samples build in a scene of their own; the exporter works on the active one.
    window = bpy.context.window
    previous, window.scene = window.scene, bpy.data.scenes[made["scene"]]
    try:
        bodies = _each(made, out, actions, ra_export, ft_export, flesh)
    finally:
        window.scene = previous
    return {"scene": made["scene"], "bodies": bodies}


def _each(made, out, actions, ra_export, ft_export, flesh):
    import bpy
    bodies = {}
    for name in made["bodies"]:
        prepared = flesh.prepare(name)
        regions = [region_row(r) for r in prepared.get("regions", [])]
        regions.sort(key=lambda r: (r.get("type", ""), r.get("name", "")))
        path = os.path.join(out, name.lower() + ".glb")
        # An Idle, authored after the flesh: MovesController starts every character on one. Then
        # export_character writes <name>.moves.json beside the glb for `--godot`, with the walk as
        # the one gait.
        rig = name + "_metarig"
        idle = actions.move_set(rig, prefix=name, roles=("Idle",))
        if "error" in idle:
            raise RuntimeError("%s Idle: %s" % (name, idle["error"]))
        reports = {"Idle": idle["Idle"], "Walk": made["bodies"][name]["walk_report"]}
        char = ra_export.export_character(name, rig, path, name=name, reports=reports, forward="-Y")
        exported = char.get("export", {})
        verified = ft_export.verify(path, expect_meshes=[name]) if exported.get("exported") else None
        bodies[name] = {
            # after flesh: the jiggle bones must not change which bone is the pelvis (02 - a jiggle
            # bone once read as the rear of the spine and took the pelvis with it)
            "roles": H.roles(name + "_metarig"),
            "mesh": {"vertices": len(bpy.data.objects[name].data.vertices)},
            "bind_coverage": made["bodies"][name].get("coverage"),
            "walk": H.stable(made["bodies"][name].get("walk")),
            "regions": regions,
            "region_count": len(regions),
            "prepare": H.stable({k: v for k, v in prepared.items() if k != "regions"}),
            "exported": exported.get("exported"),
            "durations_match": (exported.get("verified") or {}).get("durations_match"),
            "read_back": H.stable(verified) if verified else None,
            "idle": H.stable({k: idle["Idle"].get(k) for k in ("passed", "failures", "loop_seam")}),
            "moves_json": H.moves_manifest(char),
            "review": H.review_sheet(char.get("review")),
        }
    return bodies


H.run("flesh_figure", build)
