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
against the post-layout netlist with the declared timing annotation. Use the [lifecycle](SILICON_LIFECYCLE.md) and backend method to approve the
selected same-binary suite before execution; an undeclared exclusion does not
discharge a software or workload obligation. Physical-check evidence and
post-layout functional acceptance remain separate claims.

## Review record

The author records exact commands and summary output in the PR manifest. An
independent reviewer checks the aggregate diff, gate integrity, cited spec or
policy, and a proportionate set of reproduced commands. Checks outside the work
item are recorded as `NOT_RUN` with a reason rather than implied by a green PR.

## Recorded public verification snapshot

This source-bound snapshot preserves public engineering evidence. It is not a
claim about the latest branch or every later CI run.

### Recorded CI snapshot

- Source: [`1f92f2cfaab6163283f39018a48ce3d13e8f6795`](https://github.com/WJiangH/OpenChip/commit/1f92f2cfaab6163283f39018a48ce3d13e8f6795)
- Workflow: [CI run 34155797584](https://github.com/WJiangH/OpenChip/actions/runs/34155797584), `SUCCESS`
- Lint: `blink` and `npu` passed.
- Simulation: `blink` passed 7/7 cocotb tests; `npu` passed 20/20.
- Formal: all 9 configured `blink` tasks passed (`n1`, `n2`, and `n3`, each
  with `bmc`, `prove`, and `cover`). No `npu` formal job is checked in.

The CI run used `make sim` without `COVERAGE=1`. Its green simulation result
therefore contains no line or toggle coverage measurement.

### Module matrix

| Target | Specification | Executable DV | Requirement plan | Independent model | Formal | Recorded evidence and open items |
|---|---|---|---|---|---|---|
| `blink` | [`docs/spec/blink.md`](spec/blink.md) | [`hw/dv/blink/test_blink.py`](../hw/dv/blink/test_blink.py), 7 tests | [`hw/dv/blink/vplan.md`](../hw/dv/blink/vplan.md), 8 requirement rows | [`BlinkModel`](../hw/dv/common/models/blink.py) | [`blink.sby`](../hw/formal/blink/blink.sby) and [`blink_fv.sv`](../hw/formal/blink/blink_fv.sv), 9 configured tasks | [`evidence/blink/README.md`](../evidence/blink/README.md); gate-level simulation remains open |
| `npu` | [`docs/spec/npu.md`](spec/npu.md) | [`hw/dv/npu/test_npu.py`](../hw/dv/npu/test_npu.py), 20 tests | [`hw/dv/npu/vplan.md`](../hw/dv/npu/vplan.md), 23 requirement rows | [`NpuModel`](../hw/dv/common/models/npu.py) | None checked in | [`hw/dv/npu/BUGS.md`](../hw/dv/npu/BUGS.md) records a cold-start activation-path gap, limited observable numeric behavior, coverage shortfall, and an inter-group latency clarification |
| SoC-1 | [`docs/spec/soc_1.md`](spec/soc_1.md), draft | None checked in | None checked in | None checked in | None checked in | Full-system simulation, software boot, and model-runtime results are not public verification results at this snapshot |

The 8 and 23 vplan rows map numbered specification requirements. They are not
8 or 23 independently executed tests, and a passing cocotb suite does not by
itself establish that every planned coverage point or formal-tagged property is
closed.

### Coverage status

`flow/gates.mk` declares 90% minimum line and toggle coverage per module.
Current `make sim` and public CI do not collect coverage unless `COVERAGE=1` is
requested, and no automated target compares collected data with those minima.
The declared thresholds are therefore policy targets, not currently enforced
CI gates.

| Target | Public record | Interpretation |
|---|---|---|
| `blink` | The historical [`blink` evidence package](../evidence/blink/README.md) records 4/4 line points and 10/10 toggle points (100% each) from a manually annotated run. | Evidence for that recorded run. It is not a measurement from CI run 34155797584 and does not prove automatic threshold enforcement. |
| `npu` | The [`npu` bug log](../hw/dv/npu/BUGS.md) records a manual run at line 95.0% (57/60) and toggle 38.5% (1430/3714). | Line exceeded the declared target in that run; toggle did not. The open activation-path gap limits observable nonzero datapath behavior, so numeric bit-exact and toggle closure remain open. |

`make coverage-report` reads one existing Verilator Coverage-3 file and reports
the input hash, point counts, and uncovered points. It is diagnostic: every
report says `coverage_gate: not_evaluated`, and it never turns these observations
into a passing gate. The input contract follows below.

### Reproduce the executable scope

```bash
make lint
make sim MOD=blink
make sim MOD=npu
make formal MOD=blink
```

These commands reproduce the executable public module scope when the pinned
toolchain is available. Coverage requires a separate `COVERAGE=1` run and
manual evaluation; no command above establishes the 90% coverage targets.

## Diagnostic Verilator coverage report

`scripts/coverage_report.py` inventories every instrumented point in one
existing Verilator Coverage-3 `coverage.dat`. It reports hit, total, and
percentage separately for `branch`, `expr`, `line`, and `toggle`, first
across the input and then per source and `h` hierarchy. It lists every
zero-count point with its complete metadata.

Run it through the repository entrypoint:

```bash
make coverage-report \
  COVERAGE_DATA=path/to/coverage.dat \
  COVERAGE_REPORT=path/to/coverage-report.json
```

Both variables name one file. The command does not accept a directory, glob, or
set of files because combining independent coverage outputs requires proof that
their builds and point identities match.

The report records the input SHA-256, the exact Coverage-3 format header,
record counts, and `coverage_closure: false`. Missing, empty, malformed, or
duplicate records fail. Required metadata must be present, and a `t` kind
outside the four reported kinds fails instead of silently changing a
denominator. The output path may not resolve to the input path.

This parser supports the Coverage-3 record form exercised by its tests. The file
format does not encode a producer version, so the report records
`producer_version: "not encoded in input"` and makes no broader version
compatibility claim.

### Interpretation limits

This output is a diagnostic point census. A `t=line` record is a Verilator
code-flow point, not one physical source line; several points can map to one
line. Toggle records cover only instrumented bits. Startup and reset activity
can also contribute to cumulative counters, depending on the producing
testbench.

The percentages are advisory raw-point ratios. The reporter does not evaluate
or close the thresholds in `flow/gates.mk`, apply exclusions or waivers, or
produce a signoff verdict. Its JSON always contains
`coverage_gate: "not_evaluated"`. Use the official `verilator_coverage`
annotation workflow when source annotation is required, and use separately
reviewed acceptance logic for a coverage gate.

References:

- [Verilator coverage analysis](https://verilator.org/guide/latest/simulating.html#coverage-analysis)
- [`verilator_coverage` command](https://verilator.org/guide/latest/exe_verilator_coverage.html)
