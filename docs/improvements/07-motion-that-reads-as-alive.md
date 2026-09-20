# 07 - Motion that reads as alive

Category: **6 feature gaps** (rig-anything / animate-anything).

State as of rig-anything **0.27.0**, re-read against that code rather than an older snapshot.
[02](02-bone-roles-and-rig-profiles.md) has since landed - `bodymap.build` returns `roles`, each
limb carries a `girdle`, and there are five rig profiles - so what this item used to need as a
prerequisite is already there.

## Problem

The clips are correct and they look rigid. Feet do not skate, contacts hold, the gait ladder is
Froude-scaled, the trunk counter-rotates and the head holds - and a walking body still reads as a
mannequin being driven rather than a person walking.

The cause is not a missing degree of freedom. It is that **every degree of freedom is an
instantaneous algebraic function of one scalar.** That is, near enough, the definition of rigid.

## What we saw (in the code, not in the render)

`locomotion.cycle` computes a cycle phase `p0` per frame and hands it to `upper.Upper.cycle_key`.
There, every value in the upper body is a closed-form function of that same `p0`:

```python
# upper.py
def leg_forward(ph, duty):
    return -math.sin(2.0 * math.pi * (ph - 0.5 * duty))      # one harmonic

# Upper.cycle_key
turn        = sum(_side(P, l) * fwd_sig[l["name"]] for l in legs) / n
pelvis_yaw  =  prm["pelvis_turn"] * turn * self.s_yaw
thorax_yaw  = -prm["thorax_turn"] * turn * self.s_yaw        # exact negative, same instant
pelvis_roll =  prm["pelvis_list"] * lst * self.s_roll
thorax_roll = -prm["side_bend"]   * lst * self.s_roll        # exact negative, same instant
pitch       =  prm["lean"] + prm["lean_bob"] * math.cos(4.0 * math.pi * p0)
limbs[arm["name"]] = self.arm_terms(arm, -fwd_sig[leg["name"]])   # exact negative, same instant
```

Consequences, each of which is independently a "this is animation, not a person" tell:

| # | What the code does | What bodies do |
|---|---|---|
| 1 | Thorax is `-k x` pelvis at the **same instant**, at every speed | Pelvis-thorax relative phase is **speed-dependent**: near in-phase at a slow walk, moving toward anti-phase as speed rises ([van Emmerik et al.](https://www.sciencedirect.com/science/article/abs/pii/S0966636201001461)) |
| 2 | Arms are the exact instantaneous negative of the same-side leg | Arm swing is **dominated by passive pendulum dynamics** - a driven mass on a hinge, so it **lags** its drive, and the lag depends on stride frequency vs the arm's own pendulum frequency ([Collins, Adamczyk & Kuo 2009](https://pubmed.ncbi.nlm.nih.gov/19640879/)) |
| 3 | One harmonic; cycle N is bit-identical to cycle N+1 | Stride-to-stride fluctuation is **structured, not absent**: persistent long-range correlations, DFA alpha ~0.7-1.0 ([Hausdorff](https://www.sciencedirect.com/science/article/abs/pii/S0167945707000322)) |
| 4 | Perfectly left-right symmetric | Every real body has a fixed asymmetry - its signature |
| 5 | Girdles (clavicles) are **named** by `bodymap` (`_GIRDLE`, `bodymap.py:51`; every limb has a `girdle`) and **never posed** - `grep girdle upper.py keyposes.py motion.py actions.py locomotion.py` finds one docstring and no keys | "Shoulders drop when a person walks" is *literally not expressible in the current pose set* |
| 6 | Counter-rotation amplitudes are hand-tuned constants per body plan (`upper.defaults`) | Counter-rotation is not a rule. It is what falls out of **regulating whole-body angular momentum** |
| 7 | Nothing carries momentum across a frame; the pose is re-derived from scratch each frame | Joints overshoot, settle and follow through |

(5) and (6) are the two that matter most. (5) is a plain gap, and now a cheap one: 02 already
named the girdle, so posing it is a term in `cycle_key`, not a research problem. (6) decides the
architecture, so it gets its own section.

**The idea is already in the codebase, on one joint.** 0.27.0 added `HAND_LAG = 0.08` to
`upper.py`: the fingers trail the arm swing by 8% of a cycle, evaluated as
`leg_forward(p0 - HAND_LAG - offset)`. That is exactly L1's mechanism - a lag is a phase offset and
costs nothing - applied to the one joint someone happened to be looking at. Everything below is
that move made general and given a physical origin instead of a tuned constant.

## The generative principle: momentum, not rules

The brief was "I don't want to write a bunch of rules for each movement." There is a principle that
replaces the rules, and it is well established:

> **Whole-body angular momentum is held in a narrow range about zero through the gait cycle**, by
> segment-to-segment cancellation - the arms' angular momentum fluctuates out of phase with the
> thighs' in the transverse plane - plus the ground reaction moment.
> ([Sci Rep 2023](https://www.nature.com/articles/s41598-023-34910-5),
> [Herr & Popovic](https://www.researchgate.net/publication/221071624_Angular_Momentum_Regulation_during_Human_Walking_Biomechanics_and_Control))

And the evidence that it is causal rather than incidental: walking with **opposite-to-normal arm
phasing** needs minimal shoulder effort yet magnifies the ground reaction moment and raises
metabolic rate by 26%, while normal swinging also needs almost no shoulder torque (Collins et al.
2009). The body is not executing a shoulder rule. It is minimising a residual.

That matters here for one reason above all others: **it is body-plan agnostic.** Give the objective
a tail-heavy theropod and the tail cancels the legs. Give it a bird and the neck does. Give it a
hexapod and the tripods cancel each other and almost nothing else moves. No archetype table, no
per-creature constants - which is exactly what this package is for.

The same result arrives from the other direction in motor control: joint kinematics across a gait
cycle are strongly redundant and **compress onto a few components** (PCA / NNMF synergy studies -
[J Biomech](https://www.sciencedirect.com/science/article/abs/pii/S0021929022000537)). The many DOFs
are not independently commanded. Something low-dimensional drives them, and momentum regulation is a
defensible candidate for what.

## How the industry gets it, and what is portable here

| Approach | Who | Portable to this sandbox? |
|---|---|---|
| **Motion matching** - search a mocap database each frame for the clip best matching current pose + desired trajectory ([survey](https://link.springer.com/rwe/10.1007/978-3-031-23161-2_511)); FIFA, For Honor, TLOU2, UE5 | data-driven | **No.** Needs a mocap corpus per creature. A hexapod has no corpus. This is exactly the gap the package exists to fill |
| **Physics-based tracking** - learn a policy that tracks a reference in simulation; SuperTrack trains from 30 min of data in ~3 h and is **character-agnostic** ([Ubisoft LaForge](https://www.ubisoft.com/en-us/studio/laforge/news/7fMzaMaDgnd0gqPsCaJZYb/supertrack-motion-tracking-for-physically-simulated-characters-using-supervised-learning)); also PARC, ControlVAE | learned + sim | **Not now.** The right long-term destination, and it needs the mass/momentum model below as its foundation either way |
| **Inertialization** - decay the pose offset with a critically damped spring instead of cross-fading; Gears of War 4, Bollo ([Holden](https://theorangeduck.com/page/spring-roll-call)) | procedural | **Yes, cheaply.** `jiggle_modifier.spring_step` is already an exact damped-oscillator integrator |
| **Procedural secondary motion / overlap** | procedural | **Yes.** Same machinery |

The honest read: motion matching is not available to us, and it is not what makes AAA motion feel
alive at the joint level anyway - it makes *transitions* feel alive. What makes the pose itself feel
alive is lag, momentum and variability. All three are cheap, and all three are generic.

## Design: five layers on top of what exists

Layer 0 is the current contact-driven kinematic solve. It stays; it is correct, and it is the
skeleton everything below hangs on. Each layer is independently switchable, independently checkable,
and has its own cost.

### L1 - Coupling becomes a transfer function, not a multiplier

Replace every `derived = -k * driver` with `derived = -k * driver(p0 - tau)`. Because the cycle is
periodic and already evaluated per phase, **a lag is a phase offset and costs nothing**: evaluate
the driver earlier in the cycle.

`tau` is not a tuned constant. It is the lag of a second-order system - the segment's inertia on the
stiffness of the joint below it - driven at the stride frequency. Derive it from L2's mass model and
a per-joint stiffness, and the measured in-phase-to-anti-phase transition with speed falls out on
its own, because a fixed lag in *time* is a speed-dependent offset in *phase*. One function replaces
a speed-dependent rule table we have not written yet and now never need to.

Apply the ladder down the axial chain: pelvis leads, thorax lags it, neck lags the thorax, head lags
the neck. Run the same ladder outward through the girdle and it delivers item (5) - shoulder drop
and shoulder lag - once girdles are posable.

### L2 - A mass model, and momentum as the objective

**Prerequisite, and the real missing data:** at 0.27.0 there was no mass or inertia anywhere in
`rig_analysis` - `grep -rln 'inertia|segment_mass'` over it returned nothing. **Done now**, see
step 1. Everything needed is
already present - skin weights, mesh volume, bone frames - so per-bone mass, centre of mass and
inertia tensor are a measurement, computed once and stamped on the rig the way `follow-through`
stamps its flesh spec. This is worth having on its own: `follow-through`, a future ragdoll, and any
physics-based controller all need the same numbers.

Then, per frame, compute whole-body angular momentum `L(t)` from the posed rig and **solve** the
free DOFs - arm swing gain and phase, thorax counter-rotation, tail sway, neck - to minimise the
vertical component's excursion over the cycle. It is a small problem (a handful of scalars per clip,
solved once at bake) with zero runtime cost, and the tuned constants in `upper.defaults` become
*initial guesses* rather than the answer.

Check: normalised `L_vertical` range over the cycle - a number that should land in the published
band for a walk, and that no current check measures.

### L3 - Joint follow-through at runtime

Generalise `follow_through/jiggle_modifier.gd` from flesh bones to **any** bone: a
`SkeletonModifier3D` that runs after the animation and springs each bone's rotation toward the
animated target, with frequency and damping taken from L2's inertia. Overlap, overshoot and settle
then happen for free on every clip, including ones with nothing authored - and, more importantly, at
*transitions*, which is where the current clips are stiffest.

The integrator, the frame-rate independence, the teleport guard and the acceleration clamp all exist
and are already verified. This is mostly a widening of scope, not new physics.

### L4 - Variability

Per-cycle jitter on phase and amplitude with the right spectrum (persistent, DFA alpha ~0.8, not
white), plus a fixed per-character left-right asymmetry drawn once and stored in the character spec
as part of its identity. Runtime cost is a scalar per cycle. This is what stops a loop reading as a
loop, and it is the cheapest realism in the document.

### L5 - Sequencing for turns, starts and stops

Turning is not a rotation, it is an ordered cascade: **eyes, then head, then trunk, then pelvis,
then feet** ([Exp Brain Res](https://link.springer.com/article/10.1007/s00221-007-0914-3)) - and
changing speed changes the onsets but not the order. That is L1's lag ladder again, triggered by a
turn signal instead of a stride phase, so it is mostly reuse. `TurnL` / `TurnR` clips already exist
in the cast manifests and are the natural test case.

## The efficiency dial, and deliberate un-realism

The layers form a ladder with an honest cost, which answers "maybe a game doesn't need this":

| Layer | Bake cost | Runtime cost | Turn it off when |
|---|---|---|---|
| L1 lag | none | **none** | never - it is free |
| L2 momentum | seconds to minutes per clip | **none** | you have hand-tuned constants you like |
| L3 joint springs | none | ~N bones x ~20 flops | distant LOD, crowds, a fixed budget |
| L4 variability | none | ~nothing | you need deterministic playback |
| L5 sequencing | none | small | the game turns instantly by design |

L1, L2 and L4 are bake-time or near-free, so **most of the realism costs nothing at runtime.** Only
L3 scales with bone count, and it is the natural thing to drop by distance.

Un-realism uses the same machinery with different constants, which is the argument for putting it in
`GAIT_STYLES` rather than in the solver. Arcade and cartoon motion wants *short* lag, *high* damping
and *exaggerated* amplitude - snappy, anticipatory, readable. A stylised style is `tau -> 0`,
`zeta -> 1`, gains > 1. Realistic is measured lag, light damping, solved gains. Same code, one preset
apart - and a style then becomes a deliberate character trait (a stiff soldier, a loose drunk, an
arthritic elder) rather than a per-clip hack.

## Steps

1. ~~**Mass model** in `rig_analysis`~~ - **done, rig-anything 0.28.0** (`mass.py`). Per-bone mass,
   COM and inertia, stamped on the rig with `mass.stamp`. Nothing calls it yet, so no behaviour
   changes and `regress.py` reports no change. What it cost to get right is worth knowing before
   step 5 leans on it:
   - **A weighted surface integral does not partition a volume.** The tetrahedron decomposition is
     exact for the whole body and meaningless per bone: weighting each tet by its triangle's skin
     weights integrates that weight extended inward *along rays from the origin*, so a ray reaching
     the left thigh drags the pelvis it crossed into the thigh's share. Belle's thighs came out
     10.8 kg and 6.4 kg, and moving the origin moved the answer - which is the tell. The partition
     is volumetric instead: voxels, each taking its nearest surface vertex's weights. Thighs now
     agree to 0.05%.
   - **Inside is a winding number, never a parity.** A body is not one closed manifold - hands and
     feet are transplanted parts, so it arrives as ~27 shells that OVERLAP at the wrists and
     ankles. A ray through an overlap crosses four surfaces bounding two solids; parity says
     "outside" and hollows the limb out.
   - **Shells disagree about which way is out.** Marco's cast glb is wound inward where Belle's is
     not, and a mesh with only *some* shells flipped reads 16% light with no sign change to notice.
     Every shell is recalculated outward before anything is measured.
   - **Crossings are rasterised, not ray-cast.** Stepping off each hit by an epsilon crawls on
     coincident seams, hit its own iteration cap mid-body, left the winding stuck positive and
     filled the air beside Belle's arm with 345% too much solid.
   - Two independent measurements are kept and compared (`volume_agreement`). The voxel number is
     the one reported; a gap on a mesh that is not watertight is the *surface's* error. Belle's 4%
     gap is her 637 unclosable boundary edges, and it does not shrink with the voxel, which is how
     that was established.
   - Checks that earned their place: `methods_agree`, `watertight`, and a **mirror check** on
     paired bones - it caught every partition bug here, and it is gated to bones holding >0.5% of
     the body because a distal phalanx is one voxel wide and its two sides always differ.
   - Measured: 300k voxels (~6 mm) is converged, ~2 s per body. Belle 66.3 kg, Marco 79.2, Mei
     53.3, Ruth 65.4; shank 4.7% of body mass against Winter's 4.65%, upper arm 3.4% against 2.8%.
     Runs unchanged on the bird, dragon, cricket, fish, anemone and brittle star - the radial
     bodies put 90% of an anemone in its hub, and the mirror check correctly reports the dragon's
     genuine asymmetry (8639 of 14411 vertices are off-mirror).
   - Still open: `motion._com_terms` weights bones by VERTEX COUNT, so it puts 50% of Belle's mass
     in her head bone and 4% in each big toe. `mass.com_terms(data)` is a drop-in replacement of
     the same shape; switching `motion.Body` over is a behaviour change and wants its own commit.
2. **Girdle posing** - a girdle term in `upper.cycle_key`. 02 already names the bone, so this is
   the shoulder rising and falling with its own side's load, lagged behind the thorax by L1's
   ladder. Unblocks "shoulders drop when a person walks", which is the thing that prompted all
   of this.
3. **L1 lag** - `tau` per axial joint from (1); replace the instantaneous negatives. Check
   pelvis-thorax relative phase against the published speed trend.
4. **L4 variability** - the cheapest visible win; can land before or after (3).
5. **L2 momentum solve** - objective, solver, and an `L_vertical` check.
6. **L3 joint springs** - widen `jiggle_modifier`; LOD gate.
7. **L5 sequencing** - turns, starts, stops.

## Done when

- A side-by-side of Belle's walk before and after (1)-(4) is obviously the same gait, and the second
  one reads as a person. Judged by the motion critic from
  [04](04-checks-that-match-the-eye.md) - which should be built first if it is going to be the
  arbiter. `review.py` and the closeup sheets landed since; they are the natural place for it.
- Pelvis-thorax relative phase moves toward anti-phase as Froude rises, measured from the baked
  clip, not from the prediction.
- Normalised whole-body angular momentum stays in a narrow band about zero through the cycle, for a
  biped **and** for the quadruped and hexapod fixtures, with no per-archetype constants.
- The hexapod and the radial body still pass every existing check. Nothing in L1-L5 may contain the
  word "arm", "shoulder" or "human".
- `tools/regress.py` green; clips re-checked on playback as they already are.

## Open questions

- Is the momentum objective solved per clip at bake (cheap, static) or closed-loop at runtime
  (expensive, reactive)? Start at bake; runtime is the door to physics-based control later.
- 02 settled the girdle as a limb member (`limbs[...]["girdle"]`) rather than part of the axial
  chain. Posing it as a trunk term anyway - it carries the shoulder, which rides the ribcage -
  may want a second handle on it.
- Mass from skin weights assumes uniform density. Good enough? Probably - but bone, fat and air
  (lungs) will move the COM, and the flesh registry already knows some densities.
