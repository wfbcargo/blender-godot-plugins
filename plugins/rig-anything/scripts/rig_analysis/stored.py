"""Move reports kept on the actions they describe, so export works in a later session.

Every set function (`actions.move_set`, `hop.move_set` / `jump_set`, `radial_moves.move_set`,
`flight.flight_set`, `swim.swim_set`, `maw.maw_set`, `octopus.octopus_set`) returns
{role: report}, and every `engine_manifest` / `export_creature` builds from those reports. Held
only in memory, they died with the Blender session that authored the clips, and a .blend reopened
later could not be exported. So each set function ends with `store(reports, rig_name)`, which
writes each role's report onto its action:

    action["rig_anything_report"] = '{"rig": ..., "role": ..., "seq": ..., "report": {...}}'

and a manifest or exporter handed `reports=None` calls `load(rig_name, roles)` instead. Actions
carry a fake user, so the reports are saved with the .blend.

The value is a JSON string, not a nested IDProperty: IDProperty dict keys must be strings of at
most 63 bytes and lists must be uniform, and a report is neither. Floats are stored unrounded, so
a manifest built from stored reports matches one built from the originals exactly. A report with
an `error` has no action to hang on; it goes on the rig object (`rig["rig_anything_failed"]`), so a
manifest built later still lists that role under `problems` and the export still refuses. `rig_anything_floor` stays where it is: the
exporter reads it from the clip.
"""
import json

import bpy
from mathutils import Color, Euler, Matrix, Quaternion, Vector

KEY = "rig_anything_report"
FAILED_KEY = "rig_anything_failed"


def clean(v, places=5):
    """A report reduced to JSON: private (`_foo`) keys dropped, vectors and tuples as lists,
    floats rounded to `places` (None keeps them exact)."""
    if isinstance(v, float):
        return v if places is None else round(v, places)
    if isinstance(v, dict):
        return {k: clean(x, places) for k, x in v.items() if not str(k).startswith("_")}
    if isinstance(v, (list, tuple)):
        return [clean(x, places) for x in v]
    if isinstance(v, (Vector, Euler, Quaternion, Color)):
        return [x if places is None else round(x, places) for x in v]
    if isinstance(v, Matrix):
        return [clean(list(row), places) for row in v]
    if isinstance(v, (set, frozenset)):
        return sorted(clean(x, places) for x in v)
    if isinstance(v, bpy.types.ID):
        return v.name
    if type(v).__module__ == "numpy" and hasattr(v, "tolist"):      # numpy scalars and arrays
        return clean(v.tolist(), places)
    return v


def _read(action):
    raw = action.get(KEY)
    if not isinstance(raw, str):
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) and isinstance(data.get("report"), dict) else None


def _failed(rig):
    """(rig object, {role: {"seq", "report"}}) for the roles that errored, kept on the rig."""
    ob = bpy.data.objects.get(rig) if rig else None
    raw = ob.get(FAILED_KEY) if ob is not None else None
    try:
        data = json.loads(raw) if isinstance(raw, str) else {}
    except ValueError:
        data = {}
    return ob, (data if isinstance(data, dict) else {})


def _next_seq():
    seqs = [d.get("seq", 0) for d in map(_read, bpy.data.actions) if d]
    for ob in bpy.data.objects:
        if isinstance(ob.get(FAILED_KEY), str):
            seqs += [f.get("seq", 0) for f in _failed(ob.name)[1].values() if isinstance(f, dict)]
    return 1 + max(seqs, default=0)


def store(reports, rig_name=None):
    """Write each role's report to its action. Returns {role: stored JSON size in bytes}.

    `rig_name` defaults to each report's own `rig`. Roles are numbered in the order given, after
    everything already stored, so `load` returns them in the order the set function made them and
    a role authored again replaces the older copy.

    A role that errored has no action to carry it, so its report goes on the rig object
    (`rig["rig_anything_failed"]`). In the authoring session an errored role lands in a manifest's
    `problems` and the export refuses; stored, a later session refuses the same way instead of
    quietly exporting without that role. A later successful store of the role clears it."""
    sizes = {}
    if not isinstance(reports, dict):
        return sizes
    seq = _next_seq()
    failed = {}                                   # rig name -> (object, {role: entry}), written once
    for role, r in reports.items():
        if not isinstance(r, dict):
            continue
        rig = rig_name or r.get("rig")
        if not rig:
            continue
        if rig not in failed:
            failed[rig] = _failed(rig)
        errs = failed[rig][1]
        if "error" in r:
            errs[role] = {"seq": seq, "report": clean(r, None)}
            seq += 1
            continue
        action = bpy.data.actions.get(r["action"]) if r.get("action") else None
        if action is None:
            continue
        text = json.dumps({"rig": rig, "role": role, "seq": seq, "report": clean(r, None)},
                          default=str)
        action[KEY] = text
        errs.pop(role, None)
        sizes[role] = len(text)
        seq += 1
    for rig, (ob, errs) in failed.items():
        if ob is None:
            continue
        if errs:
            ob[FAILED_KEY] = json.dumps(errs, default=str)
        elif FAILED_KEY in ob:
            del ob[FAILED_KEY]
    return sizes


def load(rig_name, roles=None):
    """{role: report} for `rig_name` from the actions' stored reports, in authoring order.

    `roles` limits it to those roles. Where two actions claim the same role, the one stored last
    wins."""
    found = {}
    for action in bpy.data.actions:
        d = _read(action)
        if not d or d.get("rig") != rig_name:
            continue
        role = d.get("role")
        if roles is not None and role not in roles:
            continue
        if role not in found or d.get("seq", 0) >= found[role][0]:
            found[role] = (d.get("seq", 0), d["report"])
    for role, f in _failed(rig_name)[1].items():  # errored roles, so a manifest still refuses
        if not isinstance(f, dict) or (roles is not None and role not in roles):
            continue
        if role not in found or f.get("seq", 0) >= found[role][0]:
            found[role] = (f.get("seq", 0), f.get("report", {}))
    return {role: rep for role, (_, rep) in sorted(found.items(), key=lambda kv: kv[1][0])}


def resolve(reports, rig_name, roles=None):
    """`reports` when given, else what `load` finds for `rig_name`."""
    if reports is not None:
        return reports
    if not rig_name:
        raise ValueError("no reports and no rig name to load them for")
    found = load(rig_name, roles)
    if not found:
        raise LookupError("no move reports stored on %s's actions - author its moves with a set "
                          "function (move_set and friends) first, or pass the reports" % rig_name)
    return found
