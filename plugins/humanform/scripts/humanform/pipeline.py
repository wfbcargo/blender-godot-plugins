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

A brief with a `species` other than "human" (humanform.species) makes the pre-warp human first - exactly the
path above, library and all, since it is a real human - then puts the species' head features on it, warps it
to the species (`species.warp`) and checks it against the species preset. The result's `check` is the
species'; `species` holds the warp's report and `prewarp` the human's own path and check. A species whose
body plan goes past a human's takes it after that check: `graft` (legs replaced by a tail), `legs` (a
digitigrade leg plan, humanform.legs) and `tail` (a tail beside the legs, humanform.tail).
"""

from __future__ import annotations

import time

import bpy
import numpy as np

from . import landmarks, library, measure, parts, scaffold, sheet, views

REUSE = 0.35
WARM = 1.6


def _finish_look(human, s, eyes):
    """Rigged body -> eyes, teeth and tongue, and skin, from the brief's screen colours. The teeth and tongue
    (`features.mouth`: MPFB's hidden mouth helpers as a skinned mesh of their own) go on every body: a body is
    drawn with all its parts."""
    from . import look
    if eyes:
        from . import eyes as _eyes
        _eyes.add(human, iris=s.get("iris"))
    _mouth(human)
    if s.get("skin") is not None:
        look.skin(human, s["skin"])


def _mouth(human):
    try:
        from . import features
    except ImportError:
        return None
    return features.mouth(human)


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
    if s.get("face"):
        notes.append("face: a child's body is not fitted, so its likeness ratios are not applied")
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


def _before_warp(human, s_pre, anatomy):
    """The body's own anatomy put on the pre-warp human - the body it was designed for - so the warp carries it
    with the part it sits on: genitals (`humanform.genitals.add`: MPFB's shell and targets, or the female relief,
    placed by a human's landmarks) and muscle definition (`humanform.muscle.define`: MPFB's muscle macro, which
    reloads MPFB's keys at human scale, and its delta parts). Run after the warp they would come in at human
    scale on a dwarf or a troll - MPFB drops and reloads its macro keys, unwarped, on every reapply - so a
    species body takes them here and the later stages find them done (`human["hf_before_warp"]`)."""
    import json
    done = {}
    g = (anatomy or {}).get("genitals")
    if g:
        from . import genitals
        done["genitals"] = genitals.add(human, s_pre["sex"], shape=g.get("shape") or None,
                                        strength=float(g.get("strength", 1.0)))
    m = (anatomy or {}).get("muscle")
    if m:
        from . import muscle
        done["muscle"] = muscle.define(human, s_pre, geometry=bool(m.get("geometry", True)),
                                       strength=float(m.get("strength", 1.0)),
                                       weights_override=m.get("weights_override") or None)
        human["hf_muscle_report"] = json.dumps(done["muscle"], default=str)
    if done:
        human["hf_before_warp"] = json.dumps(sorted(done))
        # what was asked, so a later stage can tell its own spec from the one these were made to
        human["hf_before_warp_spec"] = json.dumps(anatomy, sort_keys=True, default=str)
    return done


def _make_species(s, out_dir, store, contact_sheet, verbose, anatomy=None, **kw):
    """A species body: the pre-warp human (`make`, unchanged), its head features, its anatomy (`anatomy`, see
    `_before_warp`), the warp, the species check."""
    import os
    from . import species
    problems = sheet.validate(s)
    if problems:
        raise ValueError("; ".join(problems))
    t0 = time.time()
    sp = species.load(s["species"])
    s_pre, info = species.pre_warp(s, sp)
    # the skin goes on after the warp, as the species' own (`look.skin(species_skin=...)`)
    tone = s_pre.get("skin")
    s_pre = dict(s_pre, skin=None)
    res = make(s_pre, out_dir=None if not out_dir else os.path.join(out_dir, "prewarp"), store=store,
               contact_sheet=False, verbose=verbose, **kw)
    human = bpy.data.objects[res["human"]]
    t = dict(res["timing"])
    t1 = time.time()
    feats = species.apply_features(human, sp)
    _mouth(human)                   # rebuilt where the head features have put the mouth, before the warp moves it
    before_warp = _before_warp(human, s_pre, anatomy)
    t["features"] = time.time() - t1
    eyes_spec = ((sp.get("head") or {}).get("eyes"))
    eyes_rep = None
    if eyes_spec:
        # how many eyes and where (humanform.eye_layout): after the features, before the warp carries the head
        from . import eye_layout
        t1 = time.time()
        eyes_rep = eye_layout.apply(human, eyes_spec, iris=s.get("iris"))
        t["eye_layout"] = time.time() - t1
        if eyes_rep.get("fail"):
            raise ValueError(f"eye layout: {eyes_rep['fail']}")
    t2 = time.time()
    rep = dict(info)
    before = species.inventory(human, sp)
    species.warp(human, sp, report=rep, sex=s["sex"], stature=info["stature"], style=s.get("style", "realistic"),
                 clamp_scale=info["clamp_scale"], verbose=verbose)
    rep["features"] = feats
    if eyes_rep is not None:
        rep["eye_layout"] = eyes_rep
    rep["before_warp"] = before_warp
    rep["anatomy"] = species.inventory(human, sp, reference=before,
                                       expected={"eyes": (rep.get("eyes") or {}).get("ratio", 1.0)})
    if tone is not None:
        from . import look
        look.skin(human, tone, species_skin=species.skin_block(sp))
    t["warp"] = time.time() - t2
    build = s.get("build") if isinstance(s.get("build"), str) else None
    t3 = time.time()
    # the species as a preset in hand, so one given inline (no file) is checked the same way
    pre = species.preset(sp)
    hc = measure.run(human.name, preset=pre, sex=s["sex"], out_dir=out_dir, build=build)
    t["species_check"] = time.time() - t3
    # what the species check failed or warned on, so a stage report can say it without re-measuring
    rep["check_findings"] = [{k: f.get(k) for k in ("id", "status", "value", "target", "message") if k in f}
                             for f in hc.get("findings", []) if f.get("status") in ("fail", "warn")]
    if sp.get("graft"):
        # a body plan past the human one (humanform.graft): after the check, which grades the body the species'
        # proportions describe (its hips, trunk and head); then the anatomy again, what the graft took declared
        from . import graft
        t5 = time.time()
        rep["graft"] = graft.apply(human, sp["graft"])
        rep["anatomy"] = species.inventory(human, sp, reference=before)
        if tone is not None:
            from . import look
            look.skin(human, tone, species_skin=species.skin_block(sp))
        t["graft"] = time.time() - t5
    if (sp.get("legs") not in (None, "plantigrade") or sp.get("foot") not in (None, "human")
            or sp.get("tail") not in (None, False)):
        # The rest of the body plan, after the check for the same reason the graft is: the species preset
        # describes a body's proportions, and a leg plan is what the leg DOES with them. In order: the legs
        # (which point the segments and move the toes), then the feet (which reshape the toes and stand the
        # body on its pads), then the tail, which is measured against the legs (`tail`, the clearance check).
        from . import feet as feet_mod
        nails0 = feet_mod.nail_over_foot(human)
        t6 = time.time()
        if sp.get("legs") not in (None, "plantigrade"):
            from . import legs as legs_mod
            rep["legs"] = legs_mod.apply(human, sp["legs"], verbose=verbose)
            t["legs"] = time.time() - t6
        if sp.get("foot") not in (None, "human"):
            t6b = time.time()
            rep["feet"] = feet_mod.apply(human, sp["foot"], verbose=verbose)
            t["feet"] = time.time() - t6b
        if sp.get("tail") not in (None, False):
            t7 = time.time()
            from . import tail as tail_mod
            rep["tail"] = tail_mod.apply(human, sp["tail"], verbose=verbose)
            t["tail"] = time.time() - t7
        # a foot plan draws hm08's five toenails together onto however many toes the plan ends in: that is
        # the change it is meant to make, so the inventory grades them against it (`expected`), as it does the
        # eyes against their allometry
        expect = {"eyes": (rep.get("eyes") or {}).get("ratio", 1.0)}
        nails1 = feet_mod.nail_over_foot(human)
        if nails0 and nails1:
            expect["nails.toes"] = round(nails1 / nails0, 4)
        rep["anatomy"] = species.inventory(human, sp, reference=before, expected=expect)
        if tone is not None:
            from . import look
            look.skin(human, tone, species_skin=species.skin_block(sp))
    if contact_sheet and out_dir:
        t4 = time.time()
        views.contact_sheet(human.name, out_dir, preset=pre, sex=s["sex"], report=hc)
        t["views"] = time.time() - t4
    t["total"] = time.time() - t0
    fit = dict(res["fit"] or {})
    # the species body's height, where character-pipeline's stage report reads a bisected stature
    fit["stature"] = {"stature_m": round(float(hc["stature_m"]), 4), "reached": True, "species": sp["id"]}
    notes = list(res["notes"]) + list(info["notes"])
    out = dict(res, fit=fit, check=hc["counts"], notes=notes,
               timing={k: round(v, 2) for k, v in t.items()}, species=rep,
               prewarp={"path": res["path"], "check": res["check"], "stature": info["stature_pre"],
                        "stored": res["stored"]})
    out["macros"] = _macros(human)
    return out


def make(s, out_dir=None, store=False, use_library=True, contact_sheet=False, tags=(), verbose=False, eyes=True,
         face_part=None, hand_part=None, foot_part=None, fit_iterations=10, fit_detail=True, anatomy=None):
    """`face_part`, `hand_part`, `foot_part`: library parts (card or id) applied before the fit, so their
    look is kept and the measurements - moved by a hand or foot part's offsets - are solved for this body.
    The brief's `iris` and `skin` screen colours go on the eyes and body. `fit_iterations`: the body fit's
    solver iterations (`scaffold.fit_all`); `fit_detail` False skips the face and hands-and-feet fits (and
    the settle pass after them). Both are a cheaper, looser fit for a draft, and a body fitted either way is
    never stored in the library.

    A `species` brief (not "human") is fitted as its pre-warp human and warped: see the module docstring.
    `anatomy` ({"genitals": {"shape", "strength"}, "muscle": {"geometry", "strength", "weights_override"}}) is
    put on a species body before the warp (`_before_warp`) so the warp carries it; a human body ignores it (its
    stages add them to the finished body, as they always have)."""
    if (s.get("species") or "human") != "human":
        return _make_species(s, out_dir, store, contact_sheet, verbose, use_library=use_library, tags=tags,
                             eyes=eyes, face_part=face_part, hand_part=hand_part, foot_part=foot_part,
                             fit_iterations=fit_iterations, fit_detail=fit_detail, anatomy=anatomy)
    t = {}
    t0 = time.time()
    r = sheet.resolve(s)
    t["sheet"] = time.time() - t0
    if r["ansur"] == "child":
        return _make_child(s, r, t, t0, eyes, store, face_part, hand_part, foot_part)
    face = s.get("face")
    lm = landmarks.from_measurements(r["values"], s["sex"], s["style"], name=s["name"], face=face)
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
        if nearest[0] < REUSE and not face:     # a likeness is never in a stored body: always fitted
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
    shape_key = scaffold.apply_face_shape(human, face)      # over a face part: the likeness has the last word
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
    if face:
        rep["likeness"] = {"targets": {k: round(lm["measures"][k], 4) for k in lm.get("likeness", [])},
                           "shape": shape_key}
        # each likeness measure as fitted, and any the fit could not reach with every one of its levers at the end
        # of MPFB's range: said, so the brief (or the photo reading) is looked at again rather than the result trusted
        face_rep = rep.get("face") or {}
        params = face_rep.get("params", {})
        rows = {r["measure"]: r for r in face_rep.get("residuals", [])}
        rep["likeness"]["fit"] = {k: {"value": rows[k]["value"], "target": rows[k]["target"], "tol": rows[k]["tol"]}
                                  for k in lm.get("likeness", []) if k in rows}
        at_limit = sorted(k for k, levers in scaffold.LIKENESS_FINE.items()
                          if k in rows and abs(rows[k]["tol"]) > 1.0
                          and all(abs(params.get(e[0], 0.0)) >= 0.999 for e in levers))
        if at_limit:
            rep["likeness"]["at_limit"] = at_limit
            notes.append(f"likeness: {', '.join(at_limit)} at the end of MPFB's range - the face asks for more "
                         "than its target can give")
    if store and face:
        notes.append("not stored: a likeness (the brief's face) is one person's, not a body to start others from")
    elif store and r["ansur"] != "measured":
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
