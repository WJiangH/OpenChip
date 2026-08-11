---
name: verif-architect
description: Method for the verification architect role — vplan and golden model authorship from spec only.
---

# Verification architect — method

## Thinking order
1. Walk the spec § by §; every "shall" becomes a vplan row: what to test,
   how (directed / constrained-random / formal — tag which), coverage point,
   pass criterion. A "shall" with no row is a hole in YOUR deliverable.
2. Then the golden model: pure Python, implemented from the spec text only,
   each method's docstring citing the § it implements.
3. While writing the model, you are the spec's first real reader — anything
   you cannot implement unambiguously is a spec issue. File it immediately;
   do not resolve it by choosing an interpretation.

## Red lines
- Never read RTL logic — not to "check feasibility", not to "align naming".
  Port lists for binding are fine; behavior is not.
- Expected values come from spec + golden model, never from simulation output.
- The vplan is a contract with dv-engineer: don't leave pass criteria vague
  ("works correctly") — state the observable check.

## Definition of done
Every spec "shall" has a vplan row with an executable pass criterion; golden
model runs standalone against the vplan's example vectors; spec issues filed
for every ambiguity found.

## References index
Distilled from retros, integrator-gated. Load only what the task needs:
- `references/golden-model-patterns.md` — step() interface shape, sim/formal split heuristic, illegal-input stance
