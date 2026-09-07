# Verification strategy

OpenChip separates evidence already produced by a reference design from gates
planned for later designs. A claim is no stronger than the highest applicable
rung that actually ran, and every reported result must identify its inputs,
command, and tool output.

## Principles

1. **Independent expected behavior.** DV authors derive checkers and golden
   models from `docs/spec/`, without reading RTL to decide what the design
   should do. RTL and DV for a module use separate authors and contexts.
2. **Objective anchors.** Use external standards and reference models when
   available, such as RISCOF/riscv-arch-test against Spike for a RISC-V core.
3. **Adversarial tests.** Directed, randomized, negative, and formal checks
   should expose ambiguity and failures rather than confirm an implementation.
4. **Scoped evidence.** Report applicable gates and exact results. Mark skipped,
   unavailable, and future gates explicitly. Never infer a later rung from an
   earlier one.
5. **Gate integrity.** Thresholds, exclusions, waivers, constraints, and tests
   are reviewable artifacts. They may not be weakened to obtain a pass.

## Evidence ladder

| Rung | Evidence | Typical tool | Status in public CI |
|---|---|---|---|
| 1 | RTL lint | Verilator | run |
| 2 | Unit simulation | cocotb + Verilator | run |
| 3 | Coverage acceptance | Verilator coverage plus reviewed gate logic | not enforced by the diagnostic reporter |
| 4 | Formal properties | SymbiYosys | run for listed jobs |
| 5 | ISA compliance | RISCOF + riscv-arch-test + Spike | milestone-specific |
| 6 | Full-SoC firmware simulation | cocotb system testbench | milestone-specific |
| 7 | Post-synthesis netlist simulation | Yosys netlist + simulator | local or milestone-specific |
| 8 | Static timing analysis | OpenSTA / LibreLane | local or milestone-specific |
| 9 | Physical signoff | Magic/KLayout + Netgen | local or milestone-specific |
| 10 | Gate-level simulation with SDF | simulator + post-layout netlist | open for the current `blink` evidence |
| 11 | Optional silicon | fabrication and bring-up | future |

The checked-in [`blink` evidence package](../evidence/blink/README.md) records
which of these rungs ran and identifies gate-level simulation as open. It
supports those results for that reference module; it does not establish that
every repository design or every framework stage has passed.

The `framework` CI job tests framework parsers, packaging, and boundary tooling.
It does not evaluate product coverage. The `gates` job runs the listed lint,
simulation, and formal entrypoints with the pinned toolchain. CI identity logs
and exact-source delivery are described in [CI_CD.md](CI_CD.md).

## Unit-level contract

- Testbenches live in `hw/dv/<module>/`, with shared drivers, monitors,
  scoreboards, and golden models in `hw/dv/common/`.
- Golden-model docstrings cite the implemented spec section.
- Every normative spec requirement maps to a directed test, formal property, or
  explicit open item. Any exception records its rationale and approval. Random
  tests use logged seeds so failures can be replayed.
- A test needs an explicit checker. A waveform or completed process alone is
  not a functional pass.
- DV reports a failure with a reproduction command, expected-per-spec behavior,
  and observed behavior. The independent RTL author owns implementation fixes.

## Formal and system evidence

Formal jobs state their engines, depths, assumptions, assertions, and whether a
claim is bounded or proven. System tests use externally observable criteria such
as firmware output, architectural signatures, checksums, interrupts, and error
responses. Physical claims require their own timing and signoff artifacts; an
RTL simulation result cannot substitute for them.

Gate-level simulation should rerun the same decision-bearing firmware or tests
against the post-layout netlist with the declared timing annotation. Until that
rung passes, describe physical results as implementation signoff rather than
post-layout functional verification.

## Coverage policy and diagnostics

`flow/gates.mk` declares the repository target of at least 90% line and toggle
coverage per module. Existing simulation can collect Coverage-3 data, but the
public flow does not currently turn the diagnostic report into an automatic
coverage acceptance decision.

`make coverage-report` reads one existing Coverage-3 `coverage.dat` and
produces a deterministic point census. It reports per-kind counts, uncovered
points, hierarchies, and the input hash. It rejects malformed, duplicate,
missing-field, and unknown-kind records and refuses to overwrite its input.
It does not apply exclusions or waivers and always records
`coverage_gate: "not_evaluated"`. See
[COVERAGE_REPORT.md](COVERAGE_REPORT.md).

A `t=line` record is an instrumented code-flow point rather than one physical
source line. Toggle points cover only signals instrumented by the producer.
Raw diagnostic percentages therefore cannot be relabeled as a 90% gate pass.

## Review record

The author records exact commands and summary output in the PR manifest. An
independent reviewer checks the aggregate diff, gate integrity, cited spec or
policy, and a proportionate set of reproduced commands. Checks outside the work
item are recorded as `NOT_RUN` with a reason rather than implied by a green PR.
