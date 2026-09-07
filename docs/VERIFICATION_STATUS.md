# Public verification status

This page indexes the verification assets and results present in the public
repository. It separates executable tests, requirement plans, formal jobs,
recorded evidence, and open work.

## Last verified CI snapshot

- Source: [`1f92f2cfaab6163283f39018a48ce3d13e8f6795`](https://github.com/WJiangH/OpenChip/commit/1f92f2cfaab6163283f39018a48ce3d13e8f6795)
- Workflow: [CI run 34155797584](https://github.com/WJiangH/OpenChip/actions/runs/34155797584), `SUCCESS`
- Lint: `blink` and `npu` passed.
- Simulation: `blink` passed 7/7 cocotb tests; `npu` passed 20/20.
- Formal: all 9 configured `blink` tasks passed (`n1`, `n2`, and `n3`, each
  with `bmc`, `prove`, and `cover`). No `npu` formal job is checked in.

The CI run used `make sim` without `COVERAGE=1`. Its green simulation result
therefore contains no line or toggle coverage measurement.

## Module matrix

| Target | Specification | Executable DV | Requirement plan | Independent model | Formal | Recorded evidence and open items |
|---|---|---|---|---|---|---|
| `blink` | [`docs/spec/blink.md`](spec/blink.md) | [`hw/dv/blink/test_blink.py`](../hw/dv/blink/test_blink.py), 7 tests | [`hw/dv/blink/vplan.md`](../hw/dv/blink/vplan.md), 8 requirement rows | [`BlinkModel`](../hw/dv/common/models/blink.py) | [`blink.sby`](../hw/formal/blink/blink.sby) and [`blink_fv.sv`](../hw/formal/blink/blink_fv.sv), 9 configured tasks | [`evidence/blink/README.md`](../evidence/blink/README.md); gate-level simulation remains open |
| `npu` | [`docs/spec/npu.md`](spec/npu.md) | [`hw/dv/npu/test_npu.py`](../hw/dv/npu/test_npu.py), 20 tests | [`hw/dv/npu/vplan.md`](../hw/dv/npu/vplan.md), 23 requirement rows | [`NpuModel`](../hw/dv/common/models/npu.py) | None checked in | [`hw/dv/npu/BUGS.md`](../hw/dv/npu/BUGS.md) records a cold-start activation-path gap, limited observable numeric behavior, coverage shortfall, and an inter-group latency clarification |
| SoC-1 | [`docs/spec/soc_1.md`](spec/soc_1.md), draft | None checked in | None checked in | None checked in | None checked in | Full-system simulation, software boot, and model-runtime results are not public verification results at this snapshot |

The 8 and 23 vplan rows map numbered specification requirements. They are not
8 or 23 independently executed tests, and a passing cocotb suite does not by
itself establish that every planned coverage point or formal-tagged property is
closed.

## Coverage status

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
into a passing gate. See [`docs/COVERAGE_REPORT.md`](COVERAGE_REPORT.md) for the
input contract and [`docs/VERIFICATION.md`](VERIFICATION.md) for the verification
strategy.

## Reproduce the executable scope

```bash
make lint
make sim MOD=blink
make sim MOD=npu
make formal MOD=blink
```

These commands reproduce the executable public module scope when the pinned
toolchain is available. Coverage requires a separate `COVERAGE=1` run and
manual evaluation; no command above establishes the 90% coverage targets.
