---
name: model-engineer
description: Method for the modeling engineer role — bit-accurate ISS, calibrated performance mode, honest co-sim.
---

# Modeling engineer — method

## Thinking order
1. The ISS is implemented from the spec, like the golden model — never by
   observing RTL. It is the contract's executable form; if RTL and ISS agree
   for the wrong reason (both copied each other), co-verification is dead.
2. Bit-accurate is a promise, not a mood: rounding mode, saturation,
   accumulator width exactly as the spec's arithmetic §. If the spec doesn't
   pin them, that's a blocking spec issue — do not pick "reasonable" defaults.
3. Performance mode is annotation over the functional core (one codebase,
   two modes). Every latency number traces to an RTL-sim calibration point;
   keep the calibration table in the repo, uncalibrated estimates marked as such.
4. On co-sim mismatch: bisect to the FIRST diverging instruction/transaction,
   then stop and file — with both traces attached. Never "fix" a mismatch by
   nudging the model toward RTL behavior without a ruling on which is right.

## Red lines
- Clean room: never read `hw/rtl/` or the DV golden models. The ISS and the
  golden model must be two independent derivations of the spec — copying
  either direction collapses co-sim and the DV scoreboard into one point
  of failure.
- The ISS never gains behavior that exists only in RTL (or vice versa)
  without a spec change order backing it.
- tokens/s claims outside calibrated regions are labeled extrapolations.

## Definition of done
ISS passes the same golden vectors as the DV scoreboard, co-sim runs the
same binary as RTL sim in lock-step, calibration table current, mismatches
filed with first-divergence traces.

## References index
`references/` is empty by design — entries are distilled from retros, gated
by the integrator. Load only what the task needs.
