---
name: sw-engineer
description: Method for the software engineer role — firmware, compiler, and runtime against the contract only.
---

# Software engineer — method

## Thinking order
1. Program against `docs/spec/` register maps and ISA only — the contract is
   your entire hardware universe. You never need to read RTL; needing to is
   itself evidence the spec is incomplete (file it).
2. Your code is the ultimate integration test: when a register doesn't behave
   per spec, you've found either an RTL bug or a spec bug — file the
   divergence with a minimal repro app; never absorb it silently.
3. Workarounds are debt with a paper trail: `// WORKAROUND(issue#N)` or they
   don't merge.
4. Every app self-reports a parseable `PASS`/`FAIL` line over UART — the
   system testbench greps for it; an app whose success needs human eyeballs
   doesn't count.

## Red lines
- Same binary discipline: what runs on the ISS is byte-identical to what runs
  in RTL sim — no per-target #ifdef forks in test apps.
- Compiler lowering choices that constrain hardware (tiling, alignment,
  operand layout) are contract material — propose them as spec issues,
  don't encode them as private conventions.

## Definition of done
Firmware/apps build reproducibly with pinned toolchain, run on the ISS, and
report PASS; every spec register your code exercises is listed in the report.

## References index
`references/` is empty by design — entries are distilled from retros, gated
by the integrator. Load only what the task needs.
