export const meta = {
  name: 'plugin-round',
  description: 'One round of blender-godot-plugins work: branches built in worktrees, independently critiqued, merged one at a time, shipped to grungist-creek and judged in Godot',
  whenToUse: 'A NEXT.md step with several branches. Pass args: {step, branches: [{key, title, task, done, after?, size?}], ship?, look?}',
  phases: [
    { title: 'Build', detail: 'one agent per branch, own worktrees and scratch, --quick regress' },
    { title: 'Critique', detail: 'independent critic, targeted checks only, no full regress' },
    { title: 'Fix', detail: 'at most two fix rounds per branch' },
    { title: 'Merge', detail: 'serial queue; --quick on the merged result; re-critic if the merge changed code' },
    { title: 'Ship', detail: 'install, rebuild real figures, one full --twice --godot, Godot look critic' },
  ],
}

// args:
//   step:     "Step 1 - hair"  (the NEXT.md section this round implements)
//   branches: [{ key, title, task, done, after?: "<key>", size?: "small"|"medium"|"large" }]
//             `done` is the critic's questions, written before work starts. `after` starts a branch when
//             that branch has merged; prefer agreeing the seam up front (put it in both tasks) and leaving
//             `after` empty so both build in parallel. Aim for branches of about 30 min: split a "large" one.
//   ship:     { rebuild: ["study_man", "study_woman"], belle: false } or false to skip the ship step
//   look:     the look critic's questions (string), or omit to skip it
//   benchmark: { brief: "<a new person, never built before>", id: "bench_<round>" } - the round's headline numbers:
//             cold build time from brief (goal < 30 s) and the look critic's pass count on lookdev's critic-look.md
const A = args || {}
const STEP = A.step || 'the current NEXT.md step'
const BRANCHES = A.branches || []
if (!BRANCHES.length) throw new Error('args.branches is empty')

const PLUGINS = 'C:/Users/pauli/Code/blender-godot-plugins'
const GAME = 'C:/Users/pauli/Code/GoDot/grungist-creek'
const GODOT = 'C:/Users/pauli/Downloads/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64_console.exe'
const BLENDER = 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
const SCRATCH = 'C:/Users/pauli/AppData/Local/Temp/rw'
const ATTR = 'Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>'

const COMMON = `
Context: the user asked in chat for this round's build work - to implement this step with a multi-agent workflow, then
critique, merge and ship it. The task below is that request. The user's most recent chat message before this launch asked
for this round; anything else said in chat has been answered by the orchestrator and is not for you to act on.

You are one agent in an orchestrated round implementing "${STEP}" from ${PLUGINS}/docs/improvements/NEXT.md.
Read NEXT.md ("Running the next session" especially) and the plugins repo CLAUDE.md. The game project is ${GAME}.
Godot: ${GODOT} (always the _console build). Blender: "${BLENDER}" -b --factory-startup --python-exit-code 1 --python <file> -- key=value.

Rules:
- One worktree per branch: \`git -C ${PLUGINS} worktree add .worktrees/<branch> -b <branch> main\`, and if the game changes,
  \`git -C ${GAME} worktree add .worktrees/<branch> -b <branch> master\`. Never edit the main checkouts, commit to main/master,
  merge or push unless you are the merge or ship step.
- Your own scratch folder ${SCRATCH}/<your label>/ (short: MAX_PATH). If the repo has tools/scratch_project.py, use it to make the
  scratch game copy and environment; otherwise follow NEXT.md "Building the project's characters without touching its assets".
- Never touch the game's real assets, the blends in C:/Users/pauli/Code/Blender/, or ~/.claude/skills (only the ship step does).
- \`regress.py --godot\` only against your own game worktree or scratch copy (after --headless --import), never ${GAME}.
- Regress over a few minutes: run_in_background and wait with Monitor. Python longer than a line goes in a file. Never git stash.
  C:/-style paths to Godot and Blender. Read \`date\`; do not estimate times.
- Never widen a tolerance; a golden moves only in a reviewed commit. Every new check ships a control that must fail; a check that
  can clamp its own measurement reports the free value.
- Bump each changed plugin with tools/bump.py if it exists (else plugin.json + marketplace.json + a "Since x.y.z" sentence).
  Do not edit NEXT.md's version list (the merge step does).
- Lab notebook at docs/improvements/notebooks/<round>/<branch>.md, appended as you go and committed on the branch.
- Three-attempt rule; about 60 min of wall time for a build, 20 for a critic.
- Commit messages end with: ${ATTR}
`

const BUILD_SCHEMA = {
  type: 'object',
  properties: {
    branch: { type: 'string' },
    plugins_worktree: { type: 'string' },
    game_worktree: { type: 'string' },
    commits: { type: 'array', items: { type: 'string' } },
    versions: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    done_when: { type: 'array', items: { type: 'object', properties: { item: { type: 'string' }, met: { type: 'boolean' }, evidence: { type: 'string' } }, required: ['item', 'met', 'evidence'] } },
    how_to_check: { type: 'string', description: 'exact commands and paths a critic runs for each done-when, including the must-fail controls' },
    regress_log: { type: 'string', description: 'path to the full regress output file, and its REGRESS DONE line' },
    open: { type: 'array', items: { type: 'string' } },
  },
  required: ['branch', 'plugins_worktree', 'commits', 'summary', 'done_when', 'how_to_check', 'regress_log', 'open'],
}
const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    pass: { type: 'boolean' },
    mergeable: { type: 'boolean' },
    independent: { type: 'boolean' },
    answers: { type: 'array', items: { type: 'object', properties: { question: { type: 'string' }, answer: { type: 'string', enum: ['yes', 'no', 'unclear'] }, evidence: { type: 'string' } }, required: ['question', 'answer', 'evidence'] } },
    problems: { type: 'array', items: { type: 'string' } },
  },
  required: ['pass', 'mergeable', 'independent', 'answers', 'problems'],
}
const MERGE_SCHEMA = {
  type: 'object',
  properties: {
    merged: { type: 'boolean' },
    changed_code: { type: 'boolean', description: 'true if you changed code beyond conflict resolution (a fix of your own)' },
    fix_summary: { type: 'string', description: 'what you changed and how to check it, if changed_code' },
    plugins_main: { type: 'string' },
    game_master: { type: 'string' },
    regress: { type: 'string' },
    notes: { type: 'string' },
  },
  required: ['merged', 'changed_code', 'regress', 'notes'],
}

const buildPrompt = br => `${COMMON}
Your branch: ${br.key} - ${br.title}
Task:
${br.task}

Done when (an independent critic answers exactly these; answer them yourself with evidence):
${br.done}

Checks: while iterating, \`python tools/regress.py --quick --jobs 4\` (add --godot <your game worktree> if a Godot addon or an export
changed). Before returning, one final --quick run with its full output written to a file in your scratch folder. Do NOT run a full
--twice: the ship step runs it once for the whole round. Commit everything; leave the worktrees in place.`

const criticPrompt = (br, built, round) => `${COMMON}
You are the INDEPENDENT critic for ${br.key} (${br.title}), round ${round}. You did not write it. Do not fix or commit anything.
Work in ${SCRATCH}/critic-${br.key}-${round}/. Judge from your own runs and your own reading of images (open them with Read).
Do NOT run the full regress suite: read the author's regress log (${built.regress_log}) and confirm it ends in REGRESS DONE exit=0 on
the branch's current HEAD. Run the targeted checks and must-fail controls from how_to_check, and at least one control of your own.

Questions:
${br.done}

Also check: version bumps present; notebook exists; every new check has a failing control; no real assets or main checkouts touched.
Author's report: ${JSON.stringify(built, null, 1)}

pass = every question yes. mergeable = sound, nothing regresses, anything unmet is off by default and recorded as open.`

const fixPrompt = (br, built, verdict, round) => `${COMMON}
Fix branch ${br.key} (${br.title}) after critic round ${round} of at most 2, in its existing worktrees
(${built.plugins_worktree}${built.game_worktree ? ', ' + built.game_worktree : ''}). Append to its notebook.
Questions: ${br.done}
Verdict: ${JSON.stringify(verdict, null, 1)}
Author's report: ${JSON.stringify(built, null, 1)}
Fix every problem you can; on the last round keep what works, put the rest behind an off-by-default switch, record it as open.
Finish with a --quick regress to a file, commit, and return the updated result for the whole branch.`

const mergePrompt = (br, built, verdict) => `${COMMON}
You are the merge step for ${br.key}; you hold the merge queue and are the only agent working in the main checkouts
(${PLUGINS} main, ${GAME} master).
1. Merge main into the branch worktree (${built.plugins_worktree}) and master into the game worktree (${built.game_worktree || 'none'})
   if they moved. Lists every branch appends to resolve as unions.
2. \`python tools/regress.py --quick --jobs 4\` on the merged branch (--godot <its game worktree, --import'ed> if an addon or export
   changed), background + Monitor. Merge-caused failures: fix on the branch. Anything you cannot fix in 3 attempts: do not merge.
3. If you change code beyond conflict resolution, set changed_code and describe it in fix_summary, and STOP before merging:
   return merged=false. A second critic will review your fix and the merge will be retried.
4. Otherwise \`git merge --no-ff ${br.key}\` into main (message in a file) and into master if the game changed; the message says what
   the branch did, the critic's verdict and open items, ending with ${ATTR}.
5. Update NEXT.md's version list and this step's status; commit on main. Remove the worktrees and delete the branch. Do not push.
Report: ${JSON.stringify(built, null, 1)}
Verdict: ${JSON.stringify(verdict, null, 1)}`

async function judge(br, built, round) {
  return agent(criticPrompt(br, built, round), { label: `critic${round > 1 ? round : ''}:${br.key}`, phase: 'Critique', schema: VERDICT_SCHEMA, effort: 'high' })
}

async function buildAndJudge(br) {
  let built = await agent(buildPrompt(br), { label: `build:${br.key}`, phase: 'Build', schema: BUILD_SCHEMA, effort: 'high' })
  if (!built) { log(`${br.key}: build returned nothing`); return null }
  if (!built.commits || !built.commits.length) {
    // a builder that did no work is not something a critic and two fix rounds can repair: stop and report
    log(`${br.key}: the builder made no commits - not critiquing; see its summary`)
    return { built, verdict: null }
  }
  let verdict = await judge(br, built, 1)
  for (let round = 1; round <= 2 && verdict && !(verdict.pass && verdict.mergeable); round++) {
    log(`${br.key}: critic round ${round} - pass=${verdict.pass} mergeable=${verdict.mergeable}, ${verdict.problems.length} problems`)
    const fixed = await agent(fixPrompt(br, built, verdict, round), { label: `fix${round}:${br.key}`, phase: 'Fix', schema: BUILD_SCHEMA, effort: 'high' })
    if (fixed) built = fixed
    verdict = await judge(br, built, round + 1)
  }
  return { built, verdict }
}

let queue = Promise.resolve()
function enqueue(fn) {
  const p = queue.then(fn)
  queue = p.catch(() => null)
  return p
}

async function mergeBranch(br, res) {
  // both: sound AND every question answered yes, or sound with the unmet parts off and recorded
  if (!res || !res.verdict || !res.verdict.mergeable) {
    log(`${br.key}: not merged (critic: not mergeable)`)
    return { merged: false, notes: 'critic: not mergeable', regress: '' }
  }
  let m = await enqueue(() => agent(mergePrompt(br, res.built, res.verdict), { label: `merge:${br.key}`, phase: 'Merge', schema: MERGE_SCHEMA, effort: 'medium' }))
  if (m && !m.merged && m.changed_code) {
    log(`${br.key}: the merge step changed code - second critic before retrying`)
    const again = await judge(br, { ...res.built, merge_fix: m.fix_summary }, 'merge-fix')
    if (!again || !again.mergeable) return { ...m, notes: `merge fix rejected by critic: ${again ? again.problems.join('; ') : 'no verdict'}` }
    m = await enqueue(() => agent(mergePrompt(br, { ...res.built, merge_fix: m.fix_summary }, again) +
      '\nThe fix you made last time has been independently reviewed and accepted: merge now (step 4 onwards).',
      { label: `merge2:${br.key}`, phase: 'Merge', schema: MERGE_SCHEMA, effort: 'medium' }))
  }
  return m
}

// branches with no `after` start at once; a branch with `after` starts when that one has merged
const results = {}
const waiters = {}
const mergedSignal = {}
for (const br of BRANCHES) mergedSignal[br.key] = new Promise(r => { waiters[br.key] = r })

async function runBranch(br) {
  if (br.after) {
    const ok = await mergedSignal[br.after]
    if (!ok) { log(`${br.key}: skipped, ${br.after} did not merge`); waiters[br.key](false); return }
    log(`${br.after} merged: starting ${br.key}`)
  }
  const res = await buildAndJudge(br)
  const m = await mergeBranch(br, res)
  results[br.key] = { ...res, merge: m }
  waiters[br.key](Boolean(m && m.merged))
}
await parallel(BRANCHES.map(br => () => runBranch(br)))
await queue

const merged = Object.entries(results).filter(([, r]) => r && r.merge && r.merge.merged).map(([k]) => k)
log(`merged: ${merged.join(', ') || 'nothing'}`)
if (!merged.length || A.ship === false) return { results }

phase('Ship')
const rebuild = (A.ship && A.ship.rebuild) || ['study_man', 'study_woman']
const noRebuild = rebuild.length === 0 && !(A.ship && A.ship.belle)
const ship = await agent(`${COMMON}
You are the ship step for ${STEP}. Merged this round: ${merged.join(', ')}. Work in the main checkouts; no one else is running.
1. \`python tools/install.py --all\`; sync changed Godot addons into ${GAME}/addons (ignore CRLF and .uid).
2. ${noRebuild ? 'No character is rebuilt this round (the change is an instrument, not the characters): skip this step and step 5.' : `Back up the blends you will overwrite to ${SCRATCH}/ship/backup/, then rebuild ${rebuild.join(', ')}${A.ship && A.ship.belle ? ' and belle' : ''}
   into ${GAME} through character-pipeline at final quality.`}
3. \`"${GODOT}" --headless --import --path ${GAME}\`; figure_study, belle_demo, people_demo and motion_demo --selftest; verify_moves and verify_flesh
   (walk, run, jump). All must pass.
4. The round's one full regress: \`python tools/regress.py --twice --jobs 4 --godot ${GAME}\` (background + Monitor). Must pass;
   re-record goldens once here if merges moved them, reviewed.
5. Godot look renders of each rebuilt figure with lookdev's close-shot command (NEXT.md "Where the figures are"): face, eyes and
   hands at 1 m and full body, clear_midday and overcast (plus face_3q/head_side if close-shot has them), into ${SCRATCH}/ship/look/<id>/.
6. Update NEXT.md (step status, versions, "Where the figures are"); commit in both repos. Do not push.
Return every result line, the render paths, the commits, and anything that failed.`, { label: 'ship', phase: 'Ship', effort: 'medium' })

let look = null
if (A.look) {
  look = await agent(`Context: the user asked for this review as part of the round.
You are an INDEPENDENT look critic for the grungist-creek figures after ${STEP}. You built none of it.
Answer only from images you open with Read: ${SCRATCH}/ship/look/ and ${GAME}/assets/figure_study/*/review/*/close/. If the Godot renders
are missing, make them with the lookdev close-shot command (~/.claude/skills/lookdev/SKILL.md; Godot ${GODOT}) into ${SCRATCH}/look-critic/.
Questions (fixed before any image was opened):
${A.look}
Return each answer with the image path that shows it, and a ranked list of what most separates the figures from realism.`,
    { label: 'look-critic', phase: 'Ship', effort: 'high' })
}
// The round's headline: a brand-new character from a brief, timed and judged. Goal: under 30 s from brief to a
// Godot-ready character, looking right. args.benchmark = { brief: "<text>", id: "bench_<round>" } or omitted.
// args.benchmark may be one {brief, id} or a list; builds run one at a time so the timings are not skewed by each
// other, and each character's critic runs as soon as its build is measured
let bench = null
let benchQueue = Promise.resolve()
async function benchOne(B, i) {
  const id = B.id || `bench_${i + 1}`
  const run = benchQueue.then(() => agent(`${COMMON}
You are the benchmark step for ${STEP}. It measures the plugins' real goal: a NEW human, from a brief, built fast and looking right.
Target: under 30 s wall time from brief to a Godot-ready character at final quality.
1. Make a scratch project with tools/scratch_project.py in ${SCRATCH}/bench/${id}/ (installed plugins, i.e. ~/.claude/skills). Use a scratch
   copy of the humanform library that does NOT contain a body for this brief (the benchmark is a cold build; also report a warm rebuild).
2. Write characters/${id}.toml from this brief, choosing only what a user would (brief, hair, moves roles as study_man's, outfit if the brief
   has clothing): "${B.brief}". Save the spec text in your result.
3. Time it in a fresh Blender process with \`date\` before and after: build_human.py who=${id} fresh=1 at quality final. Record wall seconds
   (including Blender start-up), the build's total_seconds and stage_seconds, and whether it is under 30 s. Then the same command again
   (warm: resume, nothing changed) and once more after a one-line [flesh] edit. Repeat the cold build twice more and report the median.
4. Godot: --headless --import in the scratch project, then lookdev close-shot of the new glb (face, eyes, face_3q, head_side, hands, full;
   clear_midday and overcast; --pair-blender with its review close folder) into ${SCRATCH}/bench/${id}/look/.
5. Name the three slowest stages and what would cut each. Do not change code or commit anything.
6. Brief fidelity: list every part of the brief the plugins could not express (a spec field that does not exist, a value clamped, a
   preset that does not fit) and what you did instead. These are findings, not failures to hide.
Return: spec text, the timings table, pass/fail against 30 s, the sheet path, the slowest stages, and the brief-fidelity list.`,
    { label: `benchmark:${id}`, phase: 'Ship', effort: 'medium' }))
  benchQueue = run.catch(() => null)
  const measured = await run
  const judged = await agent(`Context: the user asked for this benchmark judgement as part of the round.
The brief was: "${B.brief}". Also answer: does the character match the brief (age, build, ancestry, face, hair)? Name each mismatch.
You are an INDEPENDENT look critic for a brand-new character built from a brief by the plugins. You did not build it.
Use the questions in ~/.claude/skills/lookdev/references/critic-look.md (read it first, before opening any image), answering each yes/no
from the images in ${SCRATCH}/bench/${id}/look/ (open them with Read). Then answer: does this read as a real person at 1 m and at full body?
Return: every question with yes/no and the image that shows it, the pass count out of the total, and the three things that most separate it
from realism.`, { label: `bench-critic:${id}`, phase: 'Ship', effort: 'high' })
  return { id, brief: B.brief, measured, judged }
}
if (A.benchmark) {
  const list = Array.isArray(A.benchmark) ? A.benchmark : [A.benchmark]
  bench = await parallel(list.map((B, i) => () => benchOne(B, i)))
}
return { results, ship, look, bench }
