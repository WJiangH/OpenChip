# Verification Strategy

The platform's credibility rests on this document. Without physical hardware,
"the chip works" must be established by an evidence ladder where every rung is
machine-checked, reproducible, and adversarial to the design.

## Principles

1. **Independence.** DV agents derive expected behavior from `docs/spec/` and
   golden models only. Reading RTL to decide "what it should do" is a protocol
   breach — it converts verification into confirmation.
2. **Objective anchors.** Wherever a third-party truth source exists, use it:
   riscv-arch-test + Spike for the core, standard protocol checkers for buses,
   CoreMark's own checksum for system-level. Self-graded tests are the weakest
   evidence and never the only evidence.
3. **Adversarial posture.** DV agents are scored on bugs found, coverage holes
   closed, and spec ambiguities surfaced — not on making the design look good.

## The evidence ladder

| Rung | What | Tool | Catches |
|---|---|---|---|
| 1 | Lint | Verilator, Verible | width bugs, latches, missing resets |
| 2 | Unit sim, directed + constrained-random | cocotb + Verilator | functional bugs per module |
| 3 | Coverage ≥ 90% line/toggle | verilator --coverage | untested logic |
| 4 | Formal proofs | SymbiYosys | corner cases sim can't reach |
| 5 | ISA compliance | RISCOF + riscv-arch-test + Spike | ISA misinterpretation |
| 6 | Full-SoC firmware sim | cocotb system tb | integration, memory map, interrupts |
| 7 | Post-synth netlist sim (smoke) | Yosys netlist + Verilator | synth/RTL mismatch |
| 8 | STA | OpenSTA | timing violations |
| 9 | GL-sim with SDF | Icarus/Verilator + SDF | post-layout functional/timing reality |
| 10 | (optional) silicon | Tiny Tapeout | everything else |

## Unit level (per module)

- Testbench: cocotb; reusable Wishbone driver/monitor/scoreboard in `verif/common/`.
- Golden model: plain Python in `verif/common/models/<mod>.py`, docstring cites
  spec sections. The scoreboard compares RTL observed vs model expected.
- Stimulus: directed tests for every spec "shall", plus constrained-random with
  a seeded RNG (seed logged; failures must be reproducible via `SEED=`).
- Checks: scoreboard + interface assertions. A test with no checker is not a test.
- Bug protocol: failures become entries in `verif/<mod>/BUGS.md` + a GitHub issue
  (repro command, spec citation, expected vs observed). DV never patches RTL.

## Formal (per module where it pays)

- Wishbone B4 slave/master compliance properties bound to every bus port
  (ack/err/stall discipline, no response without request, bounded response).
- FIFOs: no overflow/underflow, data ordering (via 2-symbol abstraction).
- Core: PC alignment, single write-port commit, no x-prop into architectural state,
  trap entry/return invariants.
- Each job: `formal/<mod>/<mod>.sby`, BMC depth documented, induction where feasible.

## Core compliance (M2's headline)

- RISCOF runs riscv-arch-test with our core as DUT and **Spike as reference**;
  signature regions must match 100%.
- For debug, optional lock-step co-sim: core commit log diffed against Spike
  instruction-by-instruction; first divergence pinpoints the bug.

## System level (M3)

- The SoC testbench boots real firmware from ROM. Pass criteria are external:
  UART output matches a golden log; CoreMark completes with its own valid
  checksum; timer interrupts observed at spec'd rate.
- Negative tests: illegal instruction traps, bus error responses, watchdog cases.

## Physical-adjacent (M4)

- GL-sim re-runs the *same firmware* on the post-layout netlist with SDF
  annotation at slow/typ/fast corners. This is the platform's strongest
  no-hardware claim and is required for release.

## Coverage policy

- Gates live in `flow/gates.mk`: line ≥ 90%, toggle ≥ 90% per module to merge;
  exclusions require justification comments and reviewer approval.
- Coverage holes drive the next round of DV-agent test writing — the loop is:
  run → report holes → agent proposes tests targeting holes → repeat.

## What we do NOT claim

- No post-layout dynamic IR/EM signoff (open tooling is immature there).
- sky130 SRAM macros are used as characterized by their providers.
- Analog/mixed-signal is out of scope for v1.
Stating limits honestly is part of being trustworthy.
