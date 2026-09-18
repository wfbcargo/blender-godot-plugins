# Flesh critic checklist

Questions a round's done-when and its critic **pick** from when a body has follow-through flesh (jiggle
bones). Each is yes/no with `yes` good and names the number or picture that answers it. Flesh is judged
mostly by numbers, because nothing renders it moving: Blender's review strips do not run the springs and
lookdev's close-shot poses one frame. The protocol (questions before evidence, one line of evidence per
answer, `A`/`B`/`same` against the previous version) is humanform's `references/critic-checklist.md`; this
file is only the bank. `unclear` when the source is missing.

## Sources

| name | what | how |
|---|---|---|
| **verify_flesh `<course>`** | the body driven round a fixed course with its own clips; per region `checks` (`finite`, `within_limit`, `moved`, `on_limit`, `within_body`), `on_limit_share`, `peak_offset_m`, `peak_m`, `free_peak_m`; `regions_measured` / `regions_total`, `problems`, `failures`; `FT_FLESH_LIMITS {json}` then `FT_SUMMARY ... PASSED` | `godot --headless --fixed-fps 60 --path <project> -s res://addons/follow_through/verify_flesh.gd -- scene=<glb> course=full` and again with `course=walk`, `run`, `jump` (`out=<file>` keeps the JSON) |
| **manifest `flesh`** | `types` asked for, and per region `name`, `type`, `bone`, `parent`, `peak_m`, `max_offset_m`, `material`, `frequency_hz`, `damping_ratio` | `<id>.moves.json` |
| **prepare report** | `flesh.prepare(...)`'s `regions` and `missed` (one per type not found, with `reason`: `zone_empty`, `claimed` + `claimed_by`, `below_threshold`, `too_small`, `too_little`) | in a pipeline build, the `flesh` stage report; `flesh.summarize(...)` prints it |
| **heat** | the body coloured by how far it stands out of its lean envelope, found regions in blue | `flesh.render_heat(body, out_dir, regions=...)` -> `<body>_heat_front.png`, `_right.png`, `_iso.png` |
| **suggest** | `flesh.suggest_limits(<verify_flesh out file>)`: per region `in_band` (3-9% of ticks on the limit), `settled`, `capped` and what to change | Blender, after a verify_flesh run with `out=` |
| **figure_study selftest** | the game scene's flesh line: finite, within limit, moved, within the body | `godot --headless --path <project> figure_study.tscn -- --selftest` (grungist-creek) |
| **fixtures** | `limit_influences` (each vertex keeps its total bone weight after the four-influence limit; control: the pre-0.6.1 write), `flesh_figure` `prepare_again` (a second prepare loses no weight) | `python tools/regress.py --only limit_influences flesh_figure` |

## Question bank

### Found where it should be
- **FLESH-R1** Did every type the spec asks for become a region - every `types` entry in *manifest `flesh`*
  has a region, and *prepare report* `missed` is empty? (A figure's `may_miss` is a workaround, NEXT Step 4:
  say it is there.)
- **FLESH-R2** Is each region on the mass it is named after - blue where the breast, buttock or belly stands
  out, not on the chin or the thigh? *heat* `_front` and `_right`.
- **FLESH-R3** Is each region's stand-out plausible for the body - `peak_m` of a belly under about 0.1 m on an
  athletic body (study_man read 0.168: NEXT Step 4)? *manifest `flesh`* `peak_m` against *heat*.
- **FLESH-R4** Does no zone claim another's mass - no `claimed` reason in `missed` (the breast zone took the
  belly's vertices on a figure study)? *prepare report*.

### Moves and stays in the body (every course)
- **FLESH-G1** Did every run measure every region - `regions_measured` equal to `regions_total`, `problems`
  empty? *verify_flesh* on each course.
- **FLESH-G2** Does every region move and stay finite - `moved` and `finite` true on every course?
  *verify_flesh*.
- **FLESH-G3** Does every region stay inside its limit and off it most of the time - `within_limit` true and
  `on_limit_share` under 0.10 on the full course? *verify_flesh `full`* (a jump-only course's share is
  advisory: its line was drawn on the mixed course).
- **FLESH-G4** Does no mass travel further than it stands out of the body - `within_body` true on the walk,
  run and jump courses? *verify_flesh `walk`*, *`run`*, *`jump`* (it can pass a 17 cm belly swing today:
  NEXT Step 4 - read `peak_offset_m` against `peak_m` as well).
- **FLESH-G5** Is each limit in the band, so the swing is neither pinned nor unbounded - `in_band` true and
  nothing `capped`? *suggest*.
- **FLESH-G6** Does the game scene's own check pass for the flesh? *figure_study selftest* flesh lines.

### Weights (a change to `flesh.py` or the rig)
- **FLESH-W1** Does every vertex keep its total bone weight when the jiggle weights go on and the influences
  are limited to four - and does the old stale write still fail? *fixtures* `limit_influences` (`fixed.ok`
  true, `control.ok` false).
- **FLESH-W2** Does a second `flesh.prepare` (a resumed rebuild) find the same regions and lose no weight?
  *fixtures* `flesh_figure` `prepare_again` (`regions_equal`, `max_total_lost` 0, `unweighted` 0).

## Not answerable from these today

- How the jiggle looks: no tool renders the springs moving. `figure_study.tscn` key J toggles the flesh in a
  window; a critic without a window answers the look `unclear`.
- A mass whose skin passes through a garment as it swings is wardrobe's `poke` (`wardrobe/references/critic-fit.md`
  FIT-V3, `jiggle=true`), not this list.
