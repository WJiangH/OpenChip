# Evidence package — `blink` (M0 tracer bullet)

One-page index of machine-checked results for the `blink` module, assembled
post-hoc by the integrator (this rehearsal skipped the PR cycle — see
integrator audit below for the boundary/gate-integrity check that would
normally happen per-PR). All numbers below are quoted from commit messages,
`hw/pd/blink/SIGNOFF.md`, and gate re-runs performed by the integrator on
2026-07-26; none are hand-edited.

## Gate results

| Gate | Result | Headline numbers | Authoritative artifact |
|---|---|---|---|
| **Lint** | PASS | Verilator 5.051, `--lint-only -Wall --timing`, 0 warnings | re-run: `make lint MOD=blink` (this audit) |
| **Sim + coverage** | PASS | 7/7 cocotb tests PASS; `HALF_PERIOD` sweep {1,2,4,5} = 28/28; line 100.0% (4/4), toggle 100.0% (10/10) — re-measured with `verilator_coverage --annotate` against gate mins `COVERAGE_LINE_MIN`/`COVERAGE_TOGGLE_MIN` = 90% (`flow/gates.mk`) | `hw/dv/blink/test_blink.py`, `hw/dv/blink/vplan.md` (8 rows, BLINK-01..08); commit `3f4487e` |
| **Formal** | PASS | 10 asserts + 6 covers + 0 assumes (counted directly in `blink_fv.sv`); BLINK-08 as `select -assert-none` over async-reset/latch cell types, BLINK-06 as `select -assert-count 1` on `o_led`'s driving flop; k-induction across N ∈ {1,2,3} (9 SBY tasks: `n{1,2,3}_{bmc,prove,cover}`); mutation-tested against 6 mutants, all caught | `hw/formal/blink/blink.sby`, `hw/formal/blink/blink_fv.sv`, `hw/formal/blink/blink/status.sqlite`; commit `4df4f75` |
| **Synth** | PASS | Yosys 0.67 (host)/0.62 (LibreLane image); 106 cells / 1242.44 µm²; 26 flops (25 counter + `o_led`), 0 latches (`select -assert-none` clean); mapped `sky130_fd_sc_hd` | `hw/syn/blink.ys`, `hw/syn/blink.sdc`; `hw/pd/blink/SIGNOFF.md` §5 |
| **GDS signoff** | PASS | LibreLane 3.0.5, 80/80 steps, exit 0. DRC: Magic 0 / KLayout 0 / route-DRC 0. LVS: Netgen "Circuits match uniquely" (0 errors). Antenna: 0 violations, 0 diodes. Setup WNS **0** (worst slack +11.382 ns @ ss_100C_1v60); Hold WNS **0** (worst slack +0.1069 ns @ ff_n40C_1v95). Clock 20 ns / 50 MHz per `flow/gates.mk`. | `hw/pd/blink/SIGNOFF.md` (full numbers, corner table, violation-closure log §4); `hw/pd/blink/config.yaml`; commit `d9d3b6f` |

## Spec traceability

8 numbered "shalls" (BLINK-01..08) in `docs/spec/blink.md` §4, mapped 1:1 to
`hw/dv/blink/vplan.md` rows. BLINK-06 and BLINK-08 are formal-tagged
(structural/absence properties) with sim-side sanity checks; BLINK-01..05,07
are sim-primary. All 8 rows show PASS in both sim and (where tagged) formal.

## Gate integrity

`flow/gates.mk` has not been modified since the foundation commit
(`6a1119b`) — `COVERAGE_LINE_MIN`/`COVERAGE_TOGGLE_MIN` = 90%,
`CLOCK_PERIOD_NS` = 20, `WNS_MIN` = 0, `FORMAL_BMC_DEPTH` = 20 are all as
originally landed. No waiver was needed for `blink`: every gate cleared its
threshold outright (100% coverage vs 90% min, WNS 0 vs min 0, etc.).

## Open items (not covered by this evidence package)

1. **GL-sim deferred to M4.** `hw/pd/blink/SIGNOFF.md` §7 item 1: post-layout
   gate-level simulation (`final/nl/blink.nl.v` + `final/sdf/*.sdf` against
   the same `hw/dv/blink` cocotb suite) has not been run. Until it passes,
   the physical signoff is implementation-clean but not GL-verified.
2. **`make gds` / `make synth` orchestrator gaps**, tracked and partially
   closed by follow-up commits `a7cec3f`/`a5c8f68` (PATH-prefix recipes, PDK
   cache mount, LibreLane image pinned to `3.0.5` by digest) — see
   `hw/pd/blink/SIGNOFF.md` §7 items 2-3 for the original findings.
3. **Coverage gate is not wired into `make sim`.** `COVERAGE=1` produces
   `coverage.dat`, but no target automatically runs `verilator_coverage`
   and compares against `COVERAGE_LINE_MIN`/`COVERAGE_TOGGLE_MIN` — the
   100% figure above was confirmed by the integrator running
   `verilator_coverage --annotate` by hand, not by a green `make` target.
   Recommend an explicit `make cov-check` (or equivalent) gate before the
   next module's DV work lands.
4. Timing signoff is against LibreLane's generated SDC, not the checked-in
   `hw/syn/blink.sdc`, though the two agree on all numbers that matter
   (`SIGNOFF.md` §7 item 4).

## Reproduction

```bash
make lint MOD=blink
make sim  MOD=blink COVERAGE=1
make formal MOD=blink   # SymbiYosys, requires oss-cad-suite
make synth  MOD=blink   # requires host toolchain on PATH
make gds    MOD=blink   # Docker + LibreLane 3.0.5, requires ~/.ciel PDK cache
```
