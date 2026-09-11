"""Compact text reports.

The raw analysis dicts are deliberately complete, which makes them verbose -
24 cross-section bins and 8 extremities is a lot of JSON to read. These
formatters keep the signal and drop the bulk.
"""

from __future__ import annotations

from . import measure


def _bar(value, peak, width=28):
    if peak <= 0:
        return ""
    return "#" * max(0, min(width, int(round(value / peak * width))))


def summarize(data):
    """Render an analyze() result as a short text report."""
    if "error" in data:
        return "ERROR: " + data["error"]

    h = data["health"]
    a = data["axes"]
    g = data["ground_contacts"]
    s = data["symmetry"]
    lines = []

    lines.append("OBJECT  " + data["object"])
    size = data["bbox"]["size"]
    lines.append("  size        %.3f x %.3f x %.3f" % tuple(size))
    lines.append("  verts/polys %d / %d" % (h["vertices"], h["polygons"]))

    lines.append("")
    lines.append("RIGGABILITY  " + h["verdict"].upper())
    for p in h["problems"]:
        lines.append("  BLOCKER  " + p)
    for w in h["warnings"]:
        lines.append("  warn     " + w)
    if not h["problems"] and not h["warnings"]:
        lines.append("  clean - bone heat should bind without complaint")

    lines.append("")
    lines.append("AXES  (confidence: %s)" % a["confidence"])
    lines.append("  up       %s   (%s)" % (a["up_axis"], a["up_source"]))
    lines.append("  lateral  %s   (mirror plane normal)" % a["lateral_axis"])
    lines.append("  forward  %s   sign %s" % (a["forward_axis"], a["forward_sign"]))
    lines.append("  symmetry " + "  ".join(
        "%s=%.3f" % (k, v) for k, v in sorted(s["scores"].items())))
    lines.append("  contacts per candidate up-axis:")
    for ax, ev in sorted(a["per_axis_evidence"].items()):
        mark = " <- chosen" if ax == a["up_axis"] else ""
        lines.append("    %s  %d clusters (%s)%s%s" % (
            ax, ev["clusters"], ev["hint"],
            ", balanced" if ev["balanced"] else "", mark))
    if a["alternative_up_axes"]:
        lines.append("  NOTE another axis also looks plausible as up: %s"
                     % ", ".join(a["alternative_up_axes"]))

    lines.append("")
    lines.append("GROUND CONTACTS  %d  -> %s" % (g["count"], g["hint"]))
    for i, c in enumerate(g["clusters"]):
        lines.append("  %d  at (%.3f, %.3f, %.3f)  %d verts"
                     % (i, c["position"][0], c["position"][1], c["position"][2],
                        c["vertices"]))

    e = data["extremities"]
    lines.append("")
    lines.append("EXTREMITIES  (geodesic span %.3f)" % e.get("geodesic_span", 0.0))
    for i, p in enumerate(e["points"]):
        lines.append("  %d  (%.3f, %.3f, %.3f)  %.0f%% of span"
                     % (i, p["position"][0], p["position"][1], p["position"][2],
                        p["fraction_of_span"] * 100.0))

    cs = data["cross_sections"]
    bins = cs["bins"]
    peak = max((max(b["extent"]) for b in bins), default=0.0)
    lines.append("")
    lines.append("PROFILE along %s  (width, bottom to top)" % cs["axis"])
    for b in bins:
        lines.append("  %7.3f  %-28s %.3f" % (b["at"], _bar(max(b["extent"]), peak),
                                              max(b["extent"])))

    return "\n".join(lines)


def scene_overview():
    """One line per mesh object - the starting point for choosing a target."""
    rows = measure.candidates()
    if not rows:
        return "no mesh objects in the scene"
    out = ["%-24s %8s  %-24s %s" % ("OBJECT", "VERTS", "DIMENSIONS", "NOTE")]
    for r in rows:
        note = []
        if r["has_armature"]:
            note.append("already rigged")
        if r["parent"]:
            note.append("child of " + r["parent"])
        out.append("%-24s %8d  %-24s %s" % (
            r["name"][:24], r["vertices"],
            "%.2f x %.2f x %.2f" % tuple(r["dimensions"]),
            ", ".join(note)))
    return "\n".join(out)
