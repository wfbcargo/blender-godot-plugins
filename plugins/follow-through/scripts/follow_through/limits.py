"""Flesh swing limits from what Godot measured: time on the limit -> a suggested `max_offset_m`.

A jiggle region's `max_offset_m` is the only thing that keeps the mass out of the body, and a
region pinned on it looks wrong: the clamp stops the swing dead. The limit was tuned by running
Belle's self-test, reading "on the limit x% of the time" and guessing again. Godot now measures it
(`JiggleModifier.measure_limits` / `limit_report`, printed as `FT_FLESH_LIMITS {json}` by
`verify_flesh.gd` or a game's self-test), and this module turns that into a limit.

Per region the report carries the limit, the share of ticks on it, and a `ladder`: the same
share measured on shadow springs fed the same load, each given a different limit (33 rungs 9% apart,
a quarter to four times the region's). The load comes from the skeleton and never from the flesh, so
a rung is exactly what the region would do with that limit, and a limit taken from a rung inside the
band lands inside the band when applied - on the same course. An unlimited shadow gives
`free_peak_m` and a `demand` curve, for reading only.

The rungs sit on one grid for every region, `ladder_limits`: LADDER_BASE_M x 2^(k/8), snapped to
0.1 mm. Paired sides export limits a fraction of a millimetre apart; on a grid of their own their rungs
would never coincide, and a pair's limit would be chosen on shares read between rungs - across a cliff,
made up. On one grid every limit a pair is given was measured on both sides. A share between rungs is
never offered as a measurement: a report whose pair ladders share under half their rungs (made before the grid)
is chosen between rungs with basis 'interpolated' (run again), and a step between two rungs larger
than the band's width is unknown there, not a line.

No bpy here: `flesh.suggest_limits` and `flesh.apply_limits` wrap this with the registry's caps and
the spec.
"""

from __future__ import annotations

import json
import os
import re

SCHEMA = "follow-through/flesh-limits/1"

# Time on the limit a region should spend on the course it was measured on. See
# references/flesh.md "Swing limits from Godot" for how the band was set.
BAND = (0.03, 0.09)
TARGET = 0.06
MIN_OFFSET_M = 0.005          # never suggest a limit tighter than this: a bone that cannot move
# A report line with no ladder (belle_demo's older FLESH lines) is scaled as share ~ limit^(-1/0.575):
# Belle's butt read 11-12% on the limit at 5.8 cm and 8-9% at 6.9 cm (ln 1.35 / ln 1.19 = 1.74).
LEGACY_EXPONENT = 0.575

LADDER_BASE_M = 0.01          # every region's rungs are LADDER_BASE_M x 2^(k/8) (jiggle_modifier.gd)
LADDER_STEPS = 16             # rungs either side of the one nearest the region's limit
RUNG_TOL_M = 5e-5             # two limits this close are the same rung (reports are snapped to 0.1 mm)

_BELLE_LINE = re.compile(r"FLESH\s+(\S+)\s+(OK|BAD)\s+max\s+([\d.]+)\s+\(limit\s+([\d.]+)\)\s+"
                         r"on the limit\s+([\d.]+)%")


def read_reports(src):
    """Body reports from whatever the caller has: a report dict, a list of them, the JSON list
    `verify_flesh.gd out=` wrote, a path to it or to a log, or log text holding `FT_FLESH_LIMITS {json}`
    lines. Belle's older self-test lines (`FLESH breast.L OK max 0.082 (limit 0.082) on the limit 7.5%
    of the time`) are read too, as a body named `self-test` with no demand curve."""
    if isinstance(src, dict):
        return [src] if "regions" in src else list(src.values())
    if isinstance(src, (list, tuple)):
        out = []
        for s in src:
            out.extend(read_reports(s))
        return out
    text = str(src)
    if len(text) < 1024 and os.path.isfile(text):
        with open(text, encoding="utf-8") as fh:
            text = fh.read()
    stripped = text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            return read_reports(json.loads(stripped))
        except ValueError:
            pass
    bodies = []
    legacy = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("FT_FLESH_LIMITS "):
            bodies.append(json.loads(line[len("FT_FLESH_LIMITS "):]))
            continue
        m = _BELLE_LINE.search(line)
        if m:
            name = m.group(1)
            legacy[name] = {"name": name, "type": "", "max_offset_m": float(m.group(4)),
                            "peak_offset_m": float(m.group(3)), "on_limit_share": float(m.group(5)) / 100.0}
    if legacy:
        bodies.append({"schema": SCHEMA, "body": "self-test", "regions": legacy})
    if not bodies:
        # a mistyped path is text with no report in it: an empty suggestion would read as settled
        raise ValueError("no FT_FLESH_LIMITS or FLESH line in %r" % (text[:120],))
    return bodies


def ladder_limits(limit_m, base_m=LADDER_BASE_M, steps=LADDER_STEPS):
    """The ladder of limits Godot measures beside a region whose limit is `limit_m`: base x 2^(k/8),
    snapped to 0.1 mm, for the 2 x steps + 1 k around the rung nearest the limit (mirrors
    jiggle_modifier.gd's `ladder_limits`). The grid does not depend on the limit, so two regions whose
    limits round to the same rung (within 4.4%) measure the same 33 limits, and others share the overlap."""
    import math
    k0 = int(round(8.0 * math.log2(max(float(limit_m), 1e-6) / base_m)))
    return [round(base_m * 2.0 ** (k / 8.0), 4) for k in range(k0 - steps, k0 + steps + 1)]


def suggest(report, band=BAND, target=None, caps=None, min_offset_m=MIN_OFFSET_M, pairs=True):
    """A suggested `max_offset_m` and `limit_share` per region, from Godot's limit report.

    report   anything `read_reports` reads
    band     (low, high) share of time on the limit that is left as it is
    target   the share a region outside the band is moved to (default the middle of the band)
    caps     {type: largest limit_share} - a limit that anatomy bounds (a breast swung in further than
             two thirds of its stand-out passes its skin into the chest) is never raised past it;
             a region that would need more is marked `capped`, with what to change instead
    pairs    give `<x>.L` and `<x>.R` one limit, chosen on both ladders (a course turns one way, so
             the two sides of a symmetric body do not measure the same)

    Returns {"band", "target", "in_band" (every region measured inside), "settled" (nothing to
    change), "capped" [body/region], "bodies": {body: {region: row}}, "types": {type: {"limit_share":
    median suggested share, "regions": n}}}. A row carries `action` keep / lower / raise,
    `max_offset_m` and `on_limit_share` as measured, `in_band`, `suggested_max_offset_m`,
    `suggested_limit_share` (None without peak_m), `basis` ('in band'; 'ladder', a measured rung;
    'pair', a rung measured on both sides' ladders; 'cliff', the looser of two neighbouring measured
    rungs the band falls between; 'ladder end' - run again; 'interpolated', a pair whose ladders share under
    half their rungs, chosen between rungs - run again; 'estimate' for a line with no ladder - run again),
    `expected_on_limit_share` (measured on that rung; for 'interpolated' read between rungs, and None
    where the share steps by more than the band's width between them) and any `notes`."""
    lo, hi = band
    t = (lo + hi) / 2.0 if target is None else float(target)
    caps = caps or {}
    out = {"schema": SCHEMA, "band": [lo, hi], "target": round(t, 4), "in_band": True, "settled": True,
           "capped": [], "bodies": {}, "types": {}}
    shares_by_type = {}
    for body in read_reports(report):
        bname = body.get("body", "body%d" % len(out["bodies"]))
        regions = body.get("regions", {})
        rows = {}
        for name, g in sorted(regions.items()):
            if name in rows:
                continue
            other = _mirror(name)
            if pairs and other in regions and g.get("ladder") and regions[other].get("ladder"):
                rows.update(_suggest_pair({name: g, other: regions[other]}, lo, hi, t, caps, min_offset_m))
            else:
                rows[name] = _suggest_region(g, lo, hi, t, caps, min_offset_m)
        for name in sorted(rows):
            row = rows[name]
            out["in_band"] = out["in_band"] and row["in_band"]
            out["settled"] = out["settled"] and row["action"] == "keep"
            if row.get("capped"):
                out["capped"].append("%s/%s" % (bname, name))
            if row["suggested_limit_share"] is not None and row.get("type"):
                shares_by_type.setdefault(row["type"], []).append(row["suggested_limit_share"])
        out["bodies"][bname] = {n: rows[n] for n in sorted(rows)}
    for tname, shares in sorted(shares_by_type.items()):
        s = sorted(shares)
        mid = s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2.0
        out["types"][tname] = {"limit_share": round(mid, 3), "regions": len(s)}
    return out


def _mirror(name):
    for a, b in ((".L", ".R"), (".R", ".L"), ("_L", "_R"), ("_R", "_L"), (".l", ".r"), (".r", ".l")):
        if name.endswith(a):
            return name[: -len(a)] + b
    return None


def _ladder(g):
    return sorted((float(L), float(q)) for L, q in (g.get("ladder") or []))


def _on_rung(ladder, L):
    """The share measured at limit L if L is one of the ladder's rungs, else None."""
    for Li, q in ladder:
        if abs(L - Li) < RUNG_TOL_M:
            return q
    return None


def _share_between(ladder, L, max_step):
    """The share at limit L read on a ladder: measured on a rung, linear between two. None outside the
    ladder, or between two rungs whose shares differ by more than `max_step`: a cliff lies somewhere
    between them, and a line across it would be made up."""
    q = _on_rung(ladder, L)
    if q is not None:
        return q
    if not ladder or L < ladder[0][0] or L > ladder[-1][0]:
        return None
    for (L1, q1), (L2, q2) in zip(ladder, ladder[1:]):
        if L1 <= L <= L2:
            if abs(q2 - q1) > max_step:
                return None
            return q1 + (L - L1) / (L2 - L1) * (q2 - q1)
    return None


def _suggest_pair(both, lo, hi, t, caps, min_offset_m):
    """One limit for a left and right region. Kept when both already share a limit (to 0.5 mm) and
    both read inside the band; otherwise chosen by `_choose` on the rungs measured on every side (one
    grid, `ladder_limits`, so all of them but an end rung when the two limits round to different
    rungs). Only when the ladders share under half their rungs (a report made before the grid) is a side's share read
    between its own rungs - never across a step larger than the band's width - and the row is then
    'interpolated': apply and run again."""
    names = sorted(both)
    rows = {n: _row(both[n], lo, hi) for n in names}
    limits = [float(both[n]["max_offset_m"]) for n in names]
    if all(rows[n]["in_band"] for n in names) and max(limits) - min(limits) < 5e-4:
        return {n: _finish(rows[n], both[n], float(both[n]["max_offset_m"]), "in band",
                           float(both[n]["on_limit_share"]), caps, min_offset_m) for n in names}
    ladders = {n: _ladder(both[n]) for n in names}
    candidates = []
    for L, _ in ladders[names[0]]:
        sides = {n: (_on_rung(ladders[n], L), True) for n in names}
        if all(q is not None for q, _ in sides.values()):
            candidates.append((L, sides))
    # ladders built on each side's own limit (a report made before the grid) coincide on a rung now and
    # then by rounding: a handful of shared rungs is not a ladder
    interpolated = 2 * len(candidates) < min(len(lad) for lad in ladders.values())
    if interpolated:
        candidates = []
        for L in sorted({L for lad in ladders.values() for L, _ in lad}):
            sides = {n: (_share_between(ladders[n], L, hi - lo), _on_rung(ladders[n], L) is not None) for n in names}
            if all(q is not None for q, _ in sides.values()):
                candidates.append((L, sides))
    if not candidates:
        return {n: _suggest_region(both[n], lo, hi, t, caps, min_offset_m) for n in names}
    L, basis, note = _choose(candidates, lo, hi, t)
    shares = dict(candidates)[L]
    if interpolated:
        basis = "interpolated"
        note = "the two ladders share too few rungs (built before the shared grid): chosen on shares read between rungs, apply and run again" + (
            "" if note is None else "; " + note)
    elif basis == "ladder":
        basis = "pair"
    out = {}
    for n in names:
        rows[n]["notes"].append("one limit for %s and %s" % (names[0], names[1]))
        if note:
            rows[n]["notes"].append(note)
        out[n] = _finish(rows[n], both[n], L, basis, shares[n][0], caps, min_offset_m)
    return out


def _choose(candidates, lo, hi, t):
    """Pick a limit from [(limit, {side: (share, measured)})]. Returns (limit, basis, note).

    1. Every side inside the band: measured on every side first, then the mean share nearest the
       target, then the tighter limit. basis 'ladder'.
    2. Else the tightest limit with no side over the band, measured first. When looser limits are over
       it and tighter ones under, the share falls across the whole band between two neighbouring
       limits - one long stay on the limit (a landing held, a lean) that a limit either catches or
       does not - and the looser side is taken: basis 'cliff', settled, since the ladder is geometric
       and a rerun measures the same rungs. When a side there is inside the band and another under it,
       the sides differ by more than the band and there is no cliff: basis 'ladder', settled. When
       every limit is under the band: basis 'ladder end',
       apply and run again.
    3. Else every limit measured is over the band: the loosest, basis 'ladder end', run again."""
    def measured(sides):
        return all(m for _, m in sides.values())

    inside = [c for c in candidates if all(lo <= q <= hi for q, _ in c[1].values())]
    if inside:
        L, _ = min(inside, key=lambda c: (not measured(c[1]),
                                          abs(sum(q for q, _ in c[1].values()) / len(c[1]) - t), c[0]))
        return L, "ladder", None
    under = [c for c in candidates if all(q <= hi for q, _ in c[1].values())]
    if under:
        L, sides = min(under, key=lambda c: (not measured(c[1]), c[0]))
        if len(under) < len(candidates) and max(q for q, _ in sides.values()) >= lo:
            # one side inside, the other under: the sides differ by more than the band, not a cliff
            return L, "ladder", ("no one limit puts every side inside the band: %s at %.4f m, the tightest "
                                 "with no side over it" % (" and ".join("%.1f%%" % (100 * q) for q, _ in sides.values()), L))
        if len(under) < len(candidates):
            L1, s1 = max((c for c in candidates if c[0] < L), key=lambda c: c[0], default=(None, None))
            return L, "cliff", ("no limit measured lands inside the band: %s%.1f%% at %.4f m; the looser taken" % (
                "" if L1 is None else "%.1f%% at %.4f m, " % (100 * max(q for q, _ in s1.values()), L1),
                100 * max(q for q, _ in sides.values()), L))
        return L, "ladder end", ("on the limit under %.0f%% of the time even at %.4f m, the ladder's tightest: "
                                 "apply and run again" % (100 * lo, L))
    L, _ = max(candidates, key=lambda c: c[0])
    return L, "ladder end", ("on the limit over %.0f%% of the time even at %.4f m, the ladder's loosest: "
                             "apply and run again" % (100 * hi, L))


def _row(g, lo, hi):
    s0 = float(g["on_limit_share"])
    return {"type": g.get("type", ""), "max_offset_m": float(g["max_offset_m"]), "on_limit_share": s0,
            "in_band": lo <= s0 <= hi, "peak_offset_m": g.get("peak_offset_m"), "free_peak_m": g.get("free_peak_m"),
            "notes": []}


def _suggest_region(g, lo, hi, t, caps, min_offset_m):
    L0 = float(g["max_offset_m"])
    s0 = float(g["on_limit_share"])
    row = _row(g, lo, hi)
    ladder = _ladder(g)
    if lo <= s0 <= hi:
        L, basis, expect = L0, "in band", s0
    elif ladder:
        L, basis, note = _choose([(Li, {"-": (q, True)}) for Li, q in ladder], lo, hi, t)
        expect = dict(ladder)[L]
        if note:
            row["notes"].append(note)
    else:
        # no ladder (an old self-test line): scale by the measured share, and run again
        if s0 <= 0.0:
            L = float(g.get("peak_offset_m") or L0) * 0.9
        else:
            L = L0 * (s0 / t) ** LEGACY_EXPONENT
        basis, expect = "estimate", None
        row["notes"].append("no ladder in the report: an estimate, measure again after applying it")
    return _finish(row, g, L, basis, expect, caps, min_offset_m)


def _rung(ladder, lo_m, hi_m, loosest, default, unmeasured):
    """(limit, measured share) of the loosest (or tightest) rung with lo_m <= limit <= hi_m, so a limit
    moved by a cap or the floor still lands on a measurement. `default` when no rung is in range;
    (`unmeasured`, None) with no ladder at all."""
    if not ladder:
        return unmeasured, None
    inside = [(Li, q) for Li, q in ladder if lo_m <= Li <= hi_m]
    if not inside:
        return default
    return max(inside) if loosest else min(inside)


def _finish(row, g, L, basis, expect, caps, min_offset_m):
    L0 = float(g["max_offset_m"])
    peak_m = float(g.get("peak_m") or 0.0)
    ladder = _ladder(g)
    cap = caps.get(g.get("type", ""))
    if cap is not None and peak_m > 0.0 and L > L0 and L > cap * peak_m + 1e-6:
        # raising past what anatomy allows: the loosest measured rung the cap allows (or stay, if none)
        row["capped"] = True
        row["notes"].append("needs %.3f m but the type allows %.2f x peak_m = %.3f m: lower `response` or raise "
                            "`damping_ratio` instead" % (L, cap, cap * peak_m))
        L, expect = _rung(ladder, L0 + RUNG_TOL_M, cap * peak_m + 1e-6, True, (L0, row["on_limit_share"]),
                         max(L0, cap * peak_m))
    if L < min_offset_m:
        row["notes"].append("floored at %.3f m" % min_offset_m)
        L, expect = _rung(ladder, min_offset_m - 1e-6, float("inf"), False, (min_offset_m, None), min_offset_m)
    L = round(L, 4)
    row["suggested_max_offset_m"] = L
    row["suggested_limit_share"] = round(L / peak_m, 3) if peak_m > 0.0 else None
    row["expected_on_limit_share"] = None if expect is None else round(expect, 4)
    row["basis"] = basis
    row["action"] = "keep" if abs(L - L0) < 5e-5 else ("raise" if L > L0 else "lower")
    return row


def summarize(suggestion):
    lines = ["flesh limits: band %.0f-%.0f%% on the limit, target %.1f%%%s" % (
        100 * suggestion["band"][0], 100 * suggestion["band"][1], 100 * suggestion["target"],
        " - every region inside" if suggestion["in_band"] else "")]
    if suggestion.get("capped"):
        lines.append("  capped (the limit cannot fix these): " + ", ".join(suggestion["capped"]))
    for body, rows in suggestion["bodies"].items():
        lines.append("  " + body)
        for name, r in rows.items():
            lines.append("    %-16s %-5s %.4f m (%4.1f%%) -> %.4f m%s  [%s]%s" % (
                name, r["action"], r["max_offset_m"], 100 * r["on_limit_share"], r["suggested_max_offset_m"],
                "" if r["suggested_limit_share"] is None else " = %.2f x peak" % r["suggested_limit_share"],
                r["basis"], "".join("  " + n for n in r["notes"])))
    return "\n".join(lines)
