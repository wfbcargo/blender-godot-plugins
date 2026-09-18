"""One call from a brief to a checked, rigged body - reusing the library when it can.

    res = pipeline.make(sheet.new(name="Ines", sex="female", age=30, stature=1.70, build="athletic",
                                  firmness=0.7, skin=(0.50, 0.33, 0.24)),
                        out_dir=r"C:/scratch/ines", store=True)
    res["path"]      # "reuse", "warm", "fresh" or "child"
    res["ansur"]     # "measured", "aged" or "child" - see below
    res["timing"]    # seconds per stage

The decision is made on ANSUR z-distance to the nearest stored body of the same sex and style:

    distance < REUSE   apply the stored body and measure once; if every residual is within
                       tolerance, no fit at all
    distance < WARM    fit starting from the stored body's solver parameters
    otherwise          fit from MPFB's macros

A result that passes humancheck can be stored (store=True), so the next similar brief is cheap.

Ages ANSUR II did not measure (17-58) still make a body, marked `ansur` other than "measured" and
with a note saying it is not measured against ANSUR:

    aged (over 58)   fitted at 58 as above, then MPFB's age macro set to the real age and the height
                     macro bisected until the stature is the brief's again (ageing shortens the body).
                     humancheck still runs, but its proportions are MPFB's ageing, not data.
    child (under 17) no ANSUR at all: MPFB's body at that age (weight from BMI for age, muscle from the
                     brief or build), height macro bisected to the stature. No humancheck (its presets
                     are adult), no library.

Neither kind is ever stored: the library indexes bodies by ANSUR z-scores they do not have.
"""

from __future__ import annotations

import time

import bpy
import numpy as np

from . import landmarks, library, measure, parts, scaffold, sheet, views

REUSE = 0.35
WARM = 1.6


def _finish_look(human, s, eyes):
    """Rigged body -> eyes and skin, from the brief's screen colours."""
    from . import look
    if eyes:
        from . import eyes as _eyes
        _eyes.add(human, iris=s.get("iris"))
    if s.get("skin") is not None:
        look.skin(human, s["skin"])


def _macros(human, names=("age", "weight", "muscle", "height", "firmness", "proportions", "cupsize")):
    _, _, HOP, _ = scaffold.services()
    return {n: round(float(HOP.get_value(n, entity_reference=human)), 3) for n in names}


def _make_child(s, r, t, t0, eyes, store, face_part, hand_part, foot_part):
    t1 = time.time()
    human = scaffold.create(r["sheet"])
    notes = list(r["notes"])
    for chosen in (face_part, hand_part, foot_part):
        if chosen is not None:
            part = library.load(chosen if isinstance(chosen, str) else chosen["id"])
            library.apply(human, part)
            if part["region"] != "face":
                notes.append(f"{part['id']}: its look is applied, its size offsets are not (a child has no fit)")
    rep = {"params": {}, "residuals": [], "history": [], "measurements": 0}
    if r["sheet"].get("stature"):
        rep["stature"] = scaffold.fit_stature(human, float(r["sheet"]["stature"]))
        if not rep["stature"]["reached"]:
            notes.append(f"stature {r['sheet']['stature']} m is out of MPFB's height range at this age: "
                         f"{rep['stature']['stature_m']} m")
    t["create"] = time.time() - t1
    t["fit"] = 0.0
    t3 = time.time()
    scaffold.finish(human, rep)
    _finish_look(human, r["sheet"], eyes)
    t["rig"] = time.time() - t3
    if store:
        notes.append("not stored: the library holds bodies measured against ANSUR")
    t["total"] = time.time() - t0
    return {"human": human.name, "path": "child", "ansur": "child", "nearest": None, "fit": rep, "check": None,
            "stored": None, "reuse_check": None, "start_macros": None, "macros": _macros(human),
            "timing": {k: round(v, 2) for k, v in t.items()}, "guessed": r["guessed"], "notes": notes}


def make(s, out_dir=None, store=False, use_library=True, contact_sheet=False, tags=(), verbose=False, eyes=True,
         face_part=None, hand_part=None, foot_part=None, fit_iterations=10, fit_detail=True):
    """`face_part`, `hand_part`, `foot_part`: library parts (card or id) applied before the fit, so their
    look is kept and the measurements - moved by a hand or foot part's offsets - are solved for this body.
    The brief's `iris` and `skin` screen colours go on the eyes and body. `fit_iterations`: the body fit's
    solver iterations (`scaffold.fit_all`); `fit_detail` False skips the face and hands-and-feet fits (and
    the settle pass after them). Both are a cheaper, looser fit for a draft, and a body fitted either way is
    never stored in the library."""
    t = {}
    t0 = time.time()
    r = sheet.resolve(s)
    t["sheet"] = time.time() - t0
    if r["ansur"] == "child":
        return _make_child(s, r, t, t0, eyes, store, face_part, hand_part, foot_part)
    lm = landmarks.from_measurements(r["values"], s["sex"], s["style"], name=s["name"])
    t["sheet"] = time.time() - t0

    hits = library.find_bodies(r, k=1) if use_library else []
    nearest = hits[0] if hits else None
    path = "fresh"
    start = None
    t1 = time.time()
    human = scaffold.create(r["sheet"])
    build = s.get("build") if isinstance(s.get("build"), str) else None
    rep = None
    jac = {}
    reuse_check = None
    if nearest and nearest[0] < WARM:
        card = library.load(nearest[1]["id"])
        library.apply(human, card)
        start = dict(card.get("solver_params") or {})
        # The stored body is a starting shape, not an identity: the fit never moves age, firmness,
        # proportions, cup size or ancestry, and its priors pull weight and muscle back toward where they
        # start. Warm-started from Wren (61) and Mara (athletic), a 34-year-old came out with a 60-year-old's
        # skin and a soft 77-year-old with an athlete's muscle. Put the brief's own macros back, as
        # `create` set them. Weight and muscle are the fit's own answer, though: when the stored fit began
        # from the same weight and muscle as this brief would (same BMI and build), its fitted values are
        # kept - resetting them anyway moved a repeated brief's waist 1.5 tolerances and it never reused.
        own = scaffold.create_macros(r["sheet"])
        theirs = scaffold.create_macros(card.get("sheet") or {"sex": s["sex"]})
        same_start = all(abs(theirs[n] - own[n]) <= 0.02 for n in ("weight", "muscle"))
        scaffold.reset_macros(human, r["sheet"], names=scaffold.UNFITTED if same_start
                              else ("weight", "muscle") + scaffold.UNFITTED)
        if not same_start:
            for mname in ("weight", "muscle"):
                if mname in start:
                    start[mname] = own[mname]
        jac = card.get("jacobians") or {}
        path = "warm"
        if nearest[0] < REUSE:
            # try the stored body as it is: one measurement decides
            target = landmarks.as_measurements(lm)
            tol = scaffold._tolerances(scaffold.RESIDUALS, __import__("humanform").presets()["presets"][s["style"]]["ratios"],
                                       s["sex"], lm["stature"])
            m = scaffold._measure(human, s["sex"])
            res = scaffold._residuals(m, target, tol, scaffold.RESIDUALS)
            worst = int(np.argmax(np.abs(res)))
            reuse_check = {"max_tol": round(float(np.max(np.abs(res))), 3), "worst": scaffold.RESIDUALS[worst][0]}
            # as good as the fit that made it (a body can end a little outside tolerance on a hard brief)
            limit = max(1.0, 1.1 * float((card.get("quality") or {}).get("fit_max_tol") or 0.0))
            reuse_check["limit"] = round(limit, 3)
            if np.max(np.abs(res)) <= limit:
                path = "reuse"
                rep = {"params": start, "rms_tol": round(float(np.sqrt(np.mean(res ** 2))), 3), "measurements": 1,
                       "seconds": 0.0, "history": [], "residuals": []}
                if not jac.get("extremities"):
                    # stored before hands and feet were fitted: fit just those (under a second)
                    ext = scaffold.fit_extremities(human, lm, verbose=verbose, start=start)
                    if ext is not None:
                        rep["extremities"] = ext
    start_macros = _macros(human, ("age", "weight", "muscle") + scaffold.UNFITTED[1:])
    t["create"] = time.time() - t1

    for chosen in (face_part, hand_part, foot_part):
        if chosen is None:
            continue
        part = library.load(chosen if isinstance(chosen, str) else chosen["id"])
        library.apply(human, part)
        lm = parts.offset_landmarks(lm, part, s["sex"])     # a hand or foot design's size offsets
        rep = None                          # a new part means the stored fit no longer holds
    t2 = time.time()
    if rep is None:
        hold = ("muscle",) if s.get("muscle") is not None else ()
        rep = scaffold.fit_all(human, lm, build=build, start=start, jacobians=jac, verbose=verbose, hold=hold,
                               iterations=fit_iterations, face=fit_detail, extremities=fit_detail)
    notes = list(r["notes"])
    if r["ansur"] == "aged":
        # past ANSUR: age the fitted body with MPFB, then give it back the stature it was fitted to
        _, TargetService, HOP, _ = scaffold.services()
        was = HOP.get_value("age", entity_reference=human)
        HOP.set_value("age", scaffold.age_macro(r["sheet"]["age"]), entity_reference=human)
        TargetService.reapply_macro_details(human)
        rep["aged"] = {"age_macro_fitted": round(float(was), 3),
                       "age_macro": round(scaffold.age_macro(r["sheet"]["age"]), 3),
                       "stature_after_ageing_m": round(scaffold.stature(human), 4)}
        rep["aged"]["stature"] = scaffold.fit_stature(human, float(r["sheet"]["stature"]))
    t["fit"] = time.time() - t2

    t3 = time.time()
    scaffold.finish(human, rep)
    _finish_look(human, r["sheet"], eyes)
    t["rig"] = time.time() - t3

    t4 = time.time()
    hc = measure.run(human.name, preset=s["style"], sex=s["sex"], out_dir=out_dir, build=build)
    t["check"] = time.time() - t4
    thumb = None
    if contact_sheet and out_dir:
        t5 = time.time()
        views.contact_sheet(human.name, out_dir, preset=s["style"], sex=s["sex"], report=hc)
        thumb = f"{out_dir}/body.png"
        t["views"] = time.time() - t5
    card = None
    if store and r["ansur"] != "measured":
        notes.append("not stored: the library holds bodies measured against ANSUR")
    elif store and (fit_iterations < 10 or not fit_detail):
        notes.append("not stored: a draft fit (%d iterations, detail %s)" % (fit_iterations, fit_detail))
    elif store and hc["counts"]["fail"] == 0:
        card = library.save_body(human, r, rep, hc, tags=tags, thumb=thumb)
    t["total"] = time.time() - t0
    return {"human": human.name, "path": path, "ansur": r["ansur"], "nearest": None if not nearest else
            {"id": nearest[1]["id"], "distance": round(nearest[0], 3)},
            "fit": rep, "check": hc["counts"], "stored": card["id"] if card else None, "reuse_check": reuse_check,
            "start_macros": start_macros, "macros": _macros(human),
            "timing": {k: round(v, 2) for k, v in t.items()}, "guessed": r["guessed"], "notes": notes}
