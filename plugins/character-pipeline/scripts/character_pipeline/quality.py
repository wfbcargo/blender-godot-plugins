"""How much a build spends: `[build] quality = "draft" | "preview" | "final"` (or `runner.build(quality=)`).

"final" is every plugin's own default - exactly what a build spent before this knob existed, so a final build's
stage hashes, files and goldens are the ones it always had. "preview" and "draft" pass each plugin the cheaper
setting it already takes; nothing here changes what a stage *checks*, only how much it draws, bakes or
subdivides:

    stage    knob                                   final     preview    draft
    body     fit solver iterations (pipeline.make)  10        6          3
             face and hands-and-feet fits           yes       yes        no
    review   strip frames per clip (review.sheet)   8         6          4
             views                                  3         2          1 (front)
             cell height, px                        320       240        160
             close-up look set (closeups.look_set)  all 15    face, eyes face and
                                                    + under   and both   the left
                                                    bust*     hands (6)  hand (3)
    muscle   normal map size (output = "normal")    2048      1024       512
    hair     cap smooth subdivisions (hair.add)     preset's  preset's   0
    bake     skin map size, px (look.skin)          2048      1024       1024

    * the 0.42 m under-bust view is added at final for a spec wearing a top (a shirt or dress cut)

A draft file is marked as one: the quality goes into the input hash of each stage it changes (only when it is
not "final"; a stage it does not change - moves, export - keeps its hash), so a later final build of the
same file reruns those stages rather than calling a draft's body, review sheet or normal map unchanged.

The skin map size and the close-up set are the exceptions: they are in their stage's hash at every quality, final
included (`HASHED_ALWAYS`). The close set, because a final file reviewed before it existed must not read as
unchanged: its review reruns and writes the set (06 rank 1). Final builds baked the skin at humanform's 1024 px default until the size was passed
here, so a final file baked then must not read as unchanged now: its bake reruns at 2048 (06 rank 12). The manifest's `build.quality` says which one shipped.

A body reused from the library skips the fit whatever the quality. Not yet cheaper in draft (no plugin setting
to pass): rig-anything's move set and its per-frame checks (a role's `frames` and the scene fps would have to
halve together, and the gait's frame count is chosen inside `locomotion.cycle` from its duty factor), the glb
export and its read-back, follow-through's flesh and strand measures, wardrobe's cut and fit.
"""

QUALITIES = ("draft", "preview", "final")

# the close-up look set's views (rig-anything closeups.VIEWS names them); None is every view, and the under-bust
# view for a spec wearing a top
CLOSE_PREVIEW = ("face", "eyes", "hand_palm.L", "hand_back.L", "hand_palm.R", "hand_back.R")
CLOSE_DRAFT = ("face", "hand_palm.L", "hand_back.L")

LEVELS = {
    "final": {"body": {}, "review": {}, "muscle": {"normal_size": 2048}, "hair": {}, "skin": {"size": 2048},
              "close": {"views": None, "under_bust": True}},
    "preview": {"body": {"fit_iterations": 6}, "review": {"frames": 6, "views": ("front", "right"), "cell_px": 240},
                "muscle": {"normal_size": 1024}, "hair": {}, "skin": {"size": 1024},
                "close": {"views": CLOSE_PREVIEW, "under_bust": False}},
    "draft": {"body": {"fit_iterations": 3, "fit_detail": False}, "review": {"frames": 4, "views": ("front",), "cell_px": 160},
              "muscle": {"normal_size": 512}, "hair": {"subdivide": 0}, "skin": {"size": 1024},
              "close": {"views": CLOSE_DRAFT, "under_bust": False}},
}

# which stages read which part of a level, for the input hash
STAGE_PARTS = {"body": ("body",), "review": ("review", "close"), "bake": ("muscle", "skin"), "hair": ("hair",)}
# parts hashed at every quality, "final" too (see above)
HASHED_ALWAYS = ("skin", "close")


def check(quality):
    if quality not in QUALITIES:
        raise ValueError(f"quality must be one of {QUALITIES}, not {quality!r}")
    return quality


def settings(quality, part):
    """The keyword arguments `part` ("body", "review", "muscle", "hair", "skin", "close") is built with at this
    quality."""
    return dict(LEVELS[check(quality)][part])


def for_hash(quality, stage):
    """What a stage's input hash covers of the quality: for "final" only the parts in `HASHED_ALWAYS` (the
    skin map size, for bake; every other final hash is what it always was), else the settings the stage reads
    and the quality name, so a draft is never taken for a final."""
    if stage not in STAGE_PARTS:
        return None
    if check(quality) == "final":
        always = {p: settings(quality, p) for p in STAGE_PARTS[stage] if p in HASHED_ALWAYS}
        return always or None
    return {"quality": quality, **{p: settings(quality, p) for p in STAGE_PARTS[stage]}}
