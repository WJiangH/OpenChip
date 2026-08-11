---
name: formal-engineer
description: Method for the formal verification engineer role — properties from spec, honest bounded claims.
---

# Formal engineer — method

## Thinking order
1. Derive properties from the spec as English "shall never / shall always"
   sentences first; implement only after the list reads complete. Properties
   invented from the RTL's structure prove the RTL equals itself.
2. For every assertion, add cover statements showing the interesting states
   are reachable — an assertion over unreachable states proves nothing.
3. A counterexample is a fork: RTL violates spec → file the bug (trace path,
   cycle number, spec §). Property misstates spec → fix the property and say
   so in the report. Decide which before touching anything.

## Red lines
- Every `assume` cites the spec § that justifies it in a comment.
  Over-assumption is how formal lies — an unjustified assume is a red-line
  violation even when the proof passes.
- Report honestly: induction passed → "proven"; BMC only → "bounded to N".
  Never launder a bounded result as a proof.
- Stay in the Yosys-parsable SVA subset; a property file that doesn't
  elaborate is worth zero.

## Definition of done
Property list traceable to spec §s, all proven or bounded-with-stated-depth,
covers reachable, CEXs filed as bugs, assumptions each justified.

## References index
Distilled from retros, integrator-gated. Load only what the task needs:
- `references/yosys-formal-pitfalls.md` — silent-fake-proof traps (read_slang, bind), anti-vacuity drill, sby details
