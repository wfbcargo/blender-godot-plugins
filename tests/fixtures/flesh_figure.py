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

After the export, `limit_suggestion` feeds `flesh.suggest_limits` a Godot limit report made up for the
Figure's real regions (names, limits and peaks from its spec; each region's time on the limit a fixed
function of the limit, chosen to take every branch: in band, lower, raise, a capped breast pair, a
cliff, the ladder's end, an old self-test line with no ladder, kept in band or estimated) and writes it back with
`flesh.apply_limits`. The ladders sit on Godot's one grid of limits (`limits.ladder_limits`), and every
row that claims a measured rung is checked against the share function at its suggested limit
(`expected_is_true`). A second body, the thighs on ladders built from each side's own limit (a report
from before the grid), takes the 'interpolated' branch; a third, one love handle shipped at
1.2 x peak_m and in band, takes the tightened-onto-the-cap branch. The golden holds the suggested
rows - each with the `max_share` it was judged against - and the spec's limits afterwards. It runs
after the export, so the glb is unchanged.

`no_measurement` then feeds it the line a self-test emits when it prints a limit report without
calling `measure_limits()` - a body whose `regions` is `{}` - and the golden holds the refusal: a
run that measured nothing must not come back `in_band` and `settled`.
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
        if name == "Figure":
            bodies[name]["limit_suggestion"] = limit_suggestion(name, flesh)
            bodies[name]["no_measurement"] = no_measurement(flesh)
    return bodies


# time on the limit as a function of the limit L, per region, as factors of its exported limit L0
LIMIT_SHARES = {
    "belly": lambda f: min(1.0, 0.01 * f ** -3),                  # rarely touched: lowered to a rung
    "butt.L": lambda f: min(1.0, 0.0001 * f ** -4),               # barely touched even at a quarter: the
    "butt.R": lambda f: min(1.0, 0.00008 * f ** -4),              # ladder's end, as a pair
    "breast.L": lambda f: min(1.0, 0.14 * f ** -3),               # pinned, but at the type's cap: capped
    "breast.R": lambda f: min(1.0, 0.10 * f ** -3),
    "arm_flab.L": lambda f: min(1.0, 0.9 * f ** -8),              # held on its limit: raised
    "arm_flab.R": lambda f: min(1.0, 0.8 * f ** -8),
    "thigh.L": lambda f: 0.2 if f < 1.05 else 0.01,               # one long stay a limit catches or not: cliff
    "thigh.R": lambda f: 0.2 if f < 1.05 else 0.01,
}


def limit_suggestion(name, flesh):
    """`flesh.suggest_limits` on a made-up Godot limit report for the body's regions, applied."""
    import json
    import bpy
    from follow_through import limits
    from follow_through import spec as ft_spec
    regions, old, truth = {}, {}, {}
    for r in ft_spec.read(bpy.data.objects[name])["jiggle"]["regions"]:
        share = LIMIT_SHARES.get(r["name"], lambda f: 0.0)
        L0 = r["max_offset_m"]
        truth[r["name"]] = (lambda share, L0: lambda L: round(share(L / L0), 4))(share, L0)
        row = {"name": r["name"], "type": r["type"], "max_offset_m": L0, "peak_m": r["peak_m"],
               "on_limit_share": round(share(1.0), 4), "peak_offset_m": L0}
        # Godot's ladder: one grid of limits for every region
        regions[r["name"]] = dict(row, ladder=[[L, truth[r["name"]](L)] for L in limits.ladder_limits(L0)])
        if r["name"].startswith("thigh."):
            # a report from before the grid: each side's ladder built on its own limit
            own = [round(L0 * 2 ** (k / 8), 4) for k in range(-16, 17)]
            old[r["name"]] = dict(row, ladder=[[L, truth[r["name"]](L)] for L in own])
    report = {"schema": "follow-through/flesh-limits/1", "body": name, "regions": regions}
    report_old = {"schema": "follow-through/flesh-limits/1", "body": name + " (own-limit ladders)", "regions": old}
    report_loose = {"schema": "follow-through/flesh-limits/1", "body": name + " (shipped loose)",
                    "regions": _loose_region(limits)}
    legacy = ("FLESH breast.L         OK  max 0.078 (limit 0.078)  on the limit  7.5% of the time  steady walk 0.03\n"
              "FLESH butt.L          BAD  max 0.058 (limit 0.058)  on the limit 11.5% of the time  steady walk 0.03")
    suggestion = flesh.suggest_limits(["FT_FLESH_LIMITS " + json.dumps(report), "FT_FLESH_LIMITS " + json.dumps(report_old),
                                       "FT_FLESH_LIMITS " + json.dumps(report_loose), legacy])
    # every row that claims a measured rung: its expected share is the share function at the suggested limit
    measured = ("in band", "ladder", "pair", "cliff", "ladder end")
    expected_is_true = {n: row["expected_on_limit_share"] == truth[n](row["suggested_max_offset_m"])
                        for n, row in suggestion["bodies"][name].items() if row["basis"] in measured}
    applied = flesh.apply_limits(name, suggestion)
    keep = ("action", "basis", "on_limit_share", "in_band", "max_offset_m", "suggested_max_offset_m",
            "suggested_limit_share", "max_share", "expected_on_limit_share", "capped", "notes")
    return H.stable({
        "in_band": suggestion["in_band"], "settled": suggestion["settled"], "capped": suggestion["capped"],
        "types": suggestion["types"],
        "rows": {b: {n: {k: row[k] for k in keep if k in row} for n, row in rows.items()}
                 for b, rows in suggestion["bodies"].items()},
        "expected_is_true": expected_is_true,
        "applied": applied,
        "spec_limits": {r["name"]: r["max_offset_m"]
                        for r in ft_spec.read(bpy.data.objects[name])["jiggle"]["regions"]},
    })


def _loose_region(limits):
    """A love handle in the band, on the limit the material gives a type with no `limit_share`:
    1.2 x peak_m, past the 1.0 its own stand-out allows. The suggestion tightens it onto the loosest
    measured rung inside the cap instead of keeping a limit that lets its skin into the hip."""
    peak, L0 = 0.05, 0.06
    share = lambda L: round(min(1.0, 0.03 * (L / L0) ** -2), 4)  # noqa: E731
    return {"love_handle.L": {"name": "love_handle.L", "type": "love_handle", "max_offset_m": L0,
                              "peak_m": peak, "ticks": 816, "on_limit_share": share(L0),
                              "peak_offset_m": L0,
                              "ladder": [[L, share(L)] for L in limits.ladder_limits(L0)]}}


def no_measurement(flesh):
    """`print_limit_report()` without `measure_limits()`: every region is skipped, so the line carries
    no regions. That used to come back `in_band` and `settled`, and summarize printed "every region
    inside". A run that measured nothing fails."""
    import json
    empty = {"schema": "follow-through/flesh-limits/1", "body": "Belle", "measuring": False,
             "regions_total": 6, "regions_measured": 0,
             "problems": ["no region was measured (6 in the spec): call measure_limits() before "
                          "print_limit_report(), and while the body animates"],
             "regions": {}}
    s = flesh.suggest_limits("FT_FLESH_LIMITS " + json.dumps(empty))
    # and one that did start, but on a body held still: a region with no ticks
    idle = {"schema": "follow-through/flesh-limits/1", "body": "Belle", "measuring": True,
            "regions_total": 1, "regions_measured": 1, "problems": ["breast.L: 0 ticks measured"],
            "regions": {"breast.L": {"name": "breast.L", "type": "breast", "max_offset_m": 0.082,
                                     "peak_m": 0.124, "ticks": 0, "on_limit_share": 0.0,
                                     "peak_offset_m": 0.0, "ladder": []}}}
    z = flesh.suggest_limits("FT_FLESH_LIMITS " + json.dumps(idle))
    try:
        flesh.apply_limits("Figure", s, body="Belle")
        refused = None
    except ValueError as exc:
        refused = str(exc)
    return H.stable({
        "apply_refused": refused,
        "empty": {"in_band": s["in_band"], "settled": s["settled"], "measured": s["measured"],
                  "problems": s["problems"], "bodies": s["bodies"]},
        "no_ticks": {"in_band": z["in_band"], "settled": z["settled"], "measured": z["measured"],
                     "problems": z["problems"]},
    })


H.run("flesh_figure", build)
