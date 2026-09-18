"""A ponytail on a running body: follow-through's strand chain, exported beside the body.

follow-through's `Figure` is fitted with rig-anything's `fit_basic_human`, bound, and given an Idle
and a Run. `samples.add_ponytail` then grows a closed, tapering tube from the back of its head, curling
out and falling behind the neck, marked the way humanform's hair layer marks one (`ft_type = "strand"`,
`ft_root_bone`, `ft_centreline`). `classify` must route it to `spring_bones`; `strand.prepare` hangs
a bone chain along the centreline from the head bone, weights the tube along it and writes the spec,
with capsule colliders round the head and neck measured from the body's skin.

A second copy of the tube without `ft_centreline` has its centreline derived from the mesh, and the
golden holds how far that lands from the given one. The body goes out through rig-anything's
`export_character` (its rig carrying the strand bones) and the ponytail through `strand.export`, which
reads the file back: every strand bone in the skin with its head where the spec puts it.

A malformed centreline - the failure mode of the input contract humanform's hair layer writes - must
come back as an error, not a traceback, and must leave the chains the object already has where they
are: `_degenerate` re-prepares a prepared copy with a one-point line, a zero-length line and an
`ft_centrelines` whose every line is degenerate, and the golden holds the error, the warnings, and
that the bones, the spec and the vertex groups all survived. A good line afterwards rebuilds it.

In Godot, `verify_strands.gd` attaches the ponytail to the body and checks it settles at rest, swings
on the run, stays out of the head and is finite at 30, 60, 120 and 240 fps (not run by the harness;
see follow-through's strands reference).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness as H  # noqa: E402

H.use("RA_SCRIPTS", "FT_SCRIPTS")

BODY = "Figure"
ROLES = ("Idle", "Run")


def _ownership(pony, rig):
    """After the exports: copies of the ponytail whose names collide with it and with each other -
    `Ponytail.001` (a duplicate), `Ponytail_001` (the same safe name), a two-chain `Hair` and a
    one-chain `Hair_0` (chain 0 of `Hair` has its name) - prepared, then all re-prepared. Every
    object's chains must survive the others' re-runs, with its own names."""
    import bpy
    from follow_through import strand
    names = ["Ponytail.001", "Ponytail_001", "Hair", "Hair_0"]
    for n in names:
        o = pony.copy()
        o.data = pony.data.copy()
        o.name = n
        for sc in pony.users_scene:
            sc.collection.objects.link(o)
    line = [list(p) for p in pony["ft_centreline"]]
    hair = bpy.data.objects["Hair"]
    del hair["ft_centreline"]
    hair["ft_centrelines"] = [line, [[p[0] + 0.02, p[1], p[2]] for p in line]]
    order = [pony.name] + names
    first = {}
    for n in order:
        r = strand.prepare(n)
        first[n] = {"chains": [c["name"] for c in r["chains"]],
                    "renamed": [w for w in r["warnings"] if "belong to another" in w]}
    before = sorted(b.name for b in rig.data.bones if b.name.startswith(strand.STRAND_PREFIX))
    for n in order:
        strand.prepare(n)
    after = sorted(b.name for b in rig.data.bones if b.name.startswith(strand.STRAND_PREFIX))
    intact = {}
    for n in order:
        o = bpy.data.objects[n]
        spec_bones = [b["bone"] for c in strand.ft_spec.read(o)["strands"]["chains"] for b in c["bones"]]
        intact[n] = all(b in rig.data.bones and rig.data.bones[b].get(strand.OWNER_PROP) == n for b in spec_bones)             and all(g.name in rig.data.bones for g in o.vertex_groups)
    return {"prepared": first, "strand_bones": len(after), "unchanged_by_re_prepare": before == after,
            "every_object_owns_its_spec_bones": intact}


def _degenerate(pony, rig):
    """A copy prepared once, then re-prepared with centrelines that carry no chain. Each must return
    an error dict - `min()` over no chain used to raise - and leave the copy's bones, spec and vertex
    groups exactly as the good run left them, since `_add_bones` deletes before it builds."""
    import bpy
    from follow_through import strand
    o = pony.copy()
    o.data = pony.data.copy()
    o.name = "PonytailBad"
    for sc in pony.users_scene:
        sc.collection.objects.link(o)
    good = strand.prepare(o.name)
    if "error" in good:
        raise RuntimeError("PonytailBad: " + good["error"])
    bones = sorted(b.name for b in rig.data.bones if b.get(strand.OWNER_PROP) == o.name)
    spec = strand.ft_spec.read(o)["strands"]
    groups = sorted(g.name for g in o.vertex_groups)
    line = [list(p) for p in o["ft_centreline"]]

    def put(prop, value):
        for p in (strand.LINE_PROP, strand.LINE_WORLD_PROP, strand.LINES_PROP):
            if p in o:
                del o[p]
        o[prop] = value

    cases = {}
    for label, prop, value in (("one_point", strand.LINE_PROP, [line[0]]),
                               ("zero_length", strand.LINE_PROP, [line[0], line[0]]),
                               ("every_chain_degenerate", strand.LINES_PROP, [[line[0]], [line[0], line[0]]])):
        put(prop, value)
        r = strand.prepare(o.name)
        cases[label] = {
            "error": r.get("error"), "warnings": r["warnings"], "chains_reported": "chains" in r,
            "bones_kept": sorted(b.name for b in rig.data.bones if b.get(strand.OWNER_PROP) == o.name) == bones,
            "spec_kept": strand.ft_spec.read(o)["strands"] == spec,
            "groups_kept": sorted(g.name for g in o.vertex_groups) == groups,
        }
    put(strand.LINE_PROP, line)
    again = strand.prepare(o.name)
    cases["good_line_rebuilds"] = {
        "error": again.get("error"),
        "bones": [c["bones"] for c in again.get("chains", [])],
        "same_bones": sorted(b.name for b in rig.data.bones if b.get(strand.OWNER_PROP) == o.name) == bones}
    return cases


def build():
    import bpy
    from mathutils import Vector
    H.clear_scene()
    from follow_through import classify, samples, strand
    from rig_analysis import actions, export as ra_export

    made = samples.build_bodies(rig=True, walk=False, rig_anything=H.scripts("RA_SCRIPTS"))
    rig = made["bodies"][BODY]["rig"]
    out = os.path.join(H.out_dir(), "strand_ponytail")
    os.makedirs(out, exist_ok=True)
    window = bpy.context.window
    previous, window.scene = window.scene, bpy.data.scenes[made["scene"]]
    try:
        moves = actions.move_set(rig, prefix=BODY, roles=ROLES)
        if "error" in moves:
            raise RuntimeError("move_set: " + moves["error"])

        pony = samples.add_ponytail(BODY, rig)
        given = [Vector(p) for p in pony["ft_centreline"]]
        # the same tube with no centreline: derived from the mesh, scored against the given one
        bare = samples.add_ponytail(BODY, rig, name="PonytailBare", centreline_prop=False)
        lines = strand.centrelines(bare, bpy.data.objects[rig], bare["ft_root_bone"])
        derived = lines[0][0]
        deviation = max(strand._project(p, given)[1] for p in derived)
        tip_gap = (derived[-1] - given[-1]).length
        derived_report = {"chains": len(lines), "points": len(derived), "report": H.stable(lines[0][2]),
                          "max_deviation_m": round(deviation, 4), "tip_gap_m": round(tip_gap, 4),
                          "root_gap_m": round((derived[0] - given[0]).length, 4)}
        mesh = bare.data
        bpy.data.objects.remove(bare, do_unlink=True)
        bpy.data.meshes.remove(mesh)

        recognised = classify.classify(pony.name)
        prepared = strand.prepare(pony.name)
        if "error" in prepared:
            raise RuntimeError("strand.prepare: " + prepared["error"])
        spec = prepared.pop("spec")

        char = ra_export.export_character(BODY, rig, os.path.join(out, "figure.glb"), name=BODY,
                                          reports=moves, roles=ROLES, forward="-Y")
        exported = char.get("export", {})
        hair = strand.export(os.path.join(out, "figure_ponytail.glb"), [pony.name], rig)
        ownership = _ownership(pony, bpy.data.objects[rig])
        degenerate = _degenerate(pony, bpy.data.objects[rig])
    finally:
        window.scene = previous

    blk = spec["strands"]
    weights = {}
    for v in pony.data.vertices:
        n = sum(1 for g in v.groups if g.weight > 1e-4)
        weights[n] = weights.get(n, 0) + 1
    return {
        "roles": H.roles(rig),
        "ponytail": {"vertices": len(pony.data.vertices), "faces": H.face_order(pony),
                     "centreline_points": len(given)},
        "classify": {k: H.stable(recognised.get(k)) for k in ("family", "class", "route", "type", "confidence",
                                                               "guessed", "warnings")},
        "derived_centreline": derived_report,
        "prepare": H.stable(prepared),
        "strands": H.stable({"chains": blk["chains"], "colliders": blk["colliders"],
                             "material": blk["material"], "gravity_scale": blk["gravity_scale"],
                             "response": blk["response"], "collision_margin_m": blk["collision_margin_m"],
                             "collision_friction": blk["collision_friction"]},
                            max_list=24),
        "influences_per_vertex": {str(k): v for k, v in sorted(weights.items())},
        "run": H.stable({k: moves["Run"].get(k) for k in ("passed", "failures", "stride_m", "implied_speed_playback_mps")}),
        "body_export": {"exported": exported.get("exported"), "note": exported.get("note"),
                        "durations_match": (exported.get("verified") or {}).get("durations_match")},
        "moves_json": H.moves_manifest(char),
        "hair_export": H.stable({k: v for k, v in hair.items() if k not in ("path",)}),
        "ownership": ownership,
        "degenerate_centreline": H.stable(degenerate),
    }


H.run("strand_ponytail", build)
