# flesh-zone-placement (research-flesh-jiggle.md items A and G)

2026-09-18, one agent in the main session (no workflow). Scratch: `%TEMP%/rw/fzp/` (game copy `game/` from
`tools/scratch_project.py --who cast_mei,cast_ruth,cast_marco,study_woman`; the cast specs with their
`[[flesh.zones]]` blocks stripped by `strip_zones.py`, outfits kept). Probes: `probe_fig.py` (sample Figure),
`probe_top.py <figure|blend> <tops>` (breast region against the bust point per zone top).

## What changed

- `flesh.tissue` returns `head_skinned`: vertices whose strongest non-`ft_` bone is the head role bone or a
  bone under it (`_head_bones`, `_head_skinned`).
- `find_regions`: face vertices never seed or grow a region (`not_face`); they stay in the lean envelope.
- breast gets `"patches": "nearest"`: per side, the one component nearest the zone's centre
  (`_zone_distance`) instead of every bulge in the zone merged.
- `flesh.check_placement(t, regions)`: tail and weight centre below the chin (lowest head-skinned vertex),
  inside the type's grown zone height, `head_share` <= 0.02. `prepare` reports it as `placement`, for found
  and for supplied (marked) regions.
- character-pipeline `judge_flesh`: `flesh: MISPLACED ...` lines and a RuntimeError; stage report `placement`.
- Control: `FT_FLESH_LEGACY_PLACEMENT=1` lets the face seed regions and merges every patch.
- follow-through 0.7.0, character-pipeline 0.13.0.

## Results (final code)

| figure | before (research) | after |
|---|---|---|
| Mei breast | bones 1.66-1.71 m, L/R swapped, 131 lip verts at 1.0, weight at bust point 0.00 | 254 verts, weight at bust point 1.00, tail 5.7 cm from it |
| Ruth breast | heavy weights at 1.425-1.47 m, 0.00 at the bust point | 269 verts, weight at bust point 0.99, tail 8.0 cm from it |
| study_woman breast | tail 6.5 cm from the bust point, 259 verts | the same region |

Controls (must fail), fresh builds with `FT_FLESH_LEGACY_PLACEMENT=1`, both exit 1:
- Mei: tail and weight centre 1.602 m, above the chin at 1.454 m; 100 % head weight.
- Ruth: tail 1.445 m, centre 1.447 m, above the chin at 1.425 m; 92 % head weight.

Ruth with the game's hand-marked zones (the committed spec) passes: marked regions are checked too.

## Dead ends

1. **Face out of `searched` (the research's monkeypatch).** It placed Mei and Ruth, but the quick regress moved
   6 fixtures and failed `dressed_presets`' sports top (`cover: 88 drawn body triangles still lie over the
   cloth`, inside 2 -> 76). Probing the sample Figure: its breast went 687 -> 458 vertices. Not the envelope
   (seeding-only exclusion gave the same 458): it was the other half of A.
2. **Breast zone top 1.45 -> 1.0.** On the sample Figure the shoulder joints sit near the bust, so its breast
   weight centre is at 1.01 of the span; 1.0 (1.1 grown) cut its upper breast. `probe_top.py` at 1.0 / 1.2 /
   1.45: Mei, Ruth and study_woman get the same region at all three once the face cannot seed, so the zone
   top did nothing for them. Reverted to 1.45; the check's chin test is the anatomical guard instead.
3. A version bump during a regress run made `hair_presets` refuse (`BuildRefused: body ... built from a
   different spec or plugin versions`): the hash moved between stages. Do not bump while regress runs.

## Not met / open

- **Tail within 4 cm of the bust point: not met** (Mei 5.7, Ruth 8.0, study_woman 6.5, unchanged by this branch).
  The tail is the excess^2-weighted centroid of a curved patch, so it sits 4-6 cm inside the surface: item C
  (tail at the apex), for the B+C branch. The bone is on the breast, which A was for.
- Mei's full build still stops at review on the `hand_back.L` `off_body` false alarm (NEXT.md); built with
  `to=export`. Not this branch.
- Belly is still claimed by the breast's grown zone on study_woman and Ruth (Step 4).
- Marco's belly stays off in the game (item F).
- (Resolved) the regress fixture `pipeline_woman` turned out to have the bug itself: its golden recorded breast
  bones at 1.45 m with 84 % of their weight on the face and 0.05 at the bust point (probe_top.py, legacy vs new
  on its blend). With this branch they sit at 1.27 m, 0.92 at the bust, peak_m 8.56 -> 8.21 cm. The fixture now
  records `flesh_placement` and a `control_legacy` (FT_FLESH_LEGACY_PLACEMENT=1) that must fail check_placement
  and judge_flesh: it fails on face weight (0.757); its legacy tail (1.436 m) sits under its chin line (1.473 m),
  so the chin test alone does not fire on this body (it does on Mei and Ruth). Goldens pipeline_woman and
  flesh_figure (only the added `placement` output) re-recorded with `--update --twice`.

## Regress

`--quick --jobs 4 --godot <scratch game>` on the final code: 16 fixtures ok, every Godot check and must-fail
control ok; pipeline_woman and flesh_figure changed as above, then re-recorded (`--only ... --update --twice`,
REGRESS DONE exit=0). Logs: `%TEMP%/rw/fzp/regress2.log`, `update.log`.
- The game's cast specs still carry the hand-marked zones; they can drop them once this ships (checked in
  scratch: stripped specs build and place correctly).
