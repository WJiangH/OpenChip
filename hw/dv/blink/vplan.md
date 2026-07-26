# blink — Verification Plan

Source of truth: `docs/spec/blink.md` (§4 "Functional behavior", BLINK-01..08).
Golden model: `hw/dv/common/models/blink.py` (`BlinkModel`).

Strategy note (per spec §6): all sim-side tests instantiate `blink` with small
`HALF_PERIOD` values so full periods complete in a handful of cycles instead of
25,000,000. The suite runs the same directed/constrained-random tests at
`HALF_PERIOD ∈ {1, 2, 4, 5}` at minimum — `1` and `2` are the spec-called-out
edge values (toggle-every-cycle, toggle-every-other-cycle), `4` and `5` give an
even and an odd "typical small" period so no test accidentally only works for
one parity. Every test compares DUT `o_led` against `BlinkModel` step-by-step,
sampled once per rising `clk` edge; a "mismatch" is any cycle where they
differ. `rst_n` is driven by the testbench per-cycle and fed into the model's
`step(rst_n)` in lock-step, so the model is not a one-shot precomputed vector —
it tracks the DUT cycle-by-cycle including whatever reset pattern the test
applies (needed for BLINK-02 mid-period reset scenarios).

Rows below are one per numbered spec "shall" (BLINK-01..08). "Formal" tag means
the requirement is best proven exhaustively by formal (whitebox / structural,
not bounded to specific `HALF_PERIOD` samples) and is handed to the
formal-engineer; a sim-side sanity check is still listed since sim runs
regardless and should catch gross violations early.

| Shall ID | What to test | Method | Coverage point | Executable pass criterion |
|---|---|---|---|---|
| **BLINK-01** (reset value) | While `rst_n` is held low, on every rising `clk` edge sampled during the low pulse, `o_led` reads 0 and the internal counter is 0. | Directed (sim-side sanity), **formal-tagged** for the internal-counter part. Formal proves `rst_n==0 -> next(o_led)==0 && next(cnt)==0` for all reachable states, not just sampled ones. | Cover: reset pulse length ∈ {1, 2, 5} cycles; reset asserted while `cnt` is at 0, mid-count, and at `HALF_PERIOD-1` (the toggle cycle) when the pulse begins. | Sim: for every cycle where `rst_n==0` sampled at the rising edge, `dut.o_led == 0` for the entirety of the pulse (checked every cycle, not just the last). Formal: SBY proof `rst_n |-> ##1 (o_led==0 && cnt==0)` holds with no counterexample at `FORMAL_BMC_DEPTH` (flow/gates.mk). Zero mismatches / zero counterexamples required. |
| **BLINK-02** (post-reset restart, no residual phase) | After `rst_n` deasserts, the counter begins from 0 regardless of what phase it was in before/during reset — i.e. the *first post-reset toggle* always lands exactly `HALF_PERIOD` cycles after deassertion, never sooner (which would indicate carried-over phase). | Constrained-random: assert `rst_n` low for a random duration (1–2·HALF_PERIOD cycles) at a random point in the free-running counter's phase (drawn uniformly over `0..HALF_PERIOD-1` pre-reset cycles elapsed), then deassert and let the model+DUT run one full period. | Cross-cover: {reset asserted at phase offset `p` for each `p` in `0..HALF_PERIOD-1`} × {reset held for 1 cycle, >1 cycle}. All bins must be hit at least once across the constrained-random seed sweep. | For every (phase, hold-length) trial: comparing `dut.o_led` to `BlinkModel.step(rst_n)` cycle-by-cycle for `2*HALF_PERIOD` cycles after deassertion produces zero mismatches, **and** explicitly assert the first `o_led` transition after deassertion occurs at exactly cycle `HALF_PERIOD` post-deassertion (not earlier) for every trial. |
| **BLINK-03** (first toggle timing) | Counting cycle 1 = first post-reset rising edge, `o_led` makes its first 0→1 transition exactly on cycle `HALF_PERIOD`. | Directed. One test per `HALF_PERIOD` in {1, 2, 4, 5}: release reset, then record the cycle index of the first `o_led` rising transition. | Cover: `HALF_PERIOD` bins {1, 2, 4, 5} each hit; for each, "first-toggle cycle == HALF_PERIOD" recorded as a pass/fail point. | `o_led` observed 0 on cycles `1..HALF_PERIOD-1` and observed 1 for the first time on cycle `HALF_PERIOD` exactly, matching `BlinkModel` step-for-step; zero mismatches over the directed run. |
| **BLINK-04** (steady-state period, toggle every HALF_PERIOD indefinitely) | After the first toggle, subsequent toggles occur at cycle `N*HALF_PERIOD` for every positive integer N, for as long as `rst_n` stays high. | Directed + constrained-random (random run length). Directed: run to at least N=20 toggles for each small `HALF_PERIOD`. Constrained-random: run for a randomized number of cycles (1 to 50 periods) with `rst_n` held high throughout, no reset. | Cover: toggle index N bins reaching at least {1, 2, 5, 10, 20}; cover both even and odd N. | `dut.o_led` matches `BlinkModel.step(1)` every single cycle for the full run (zero mismatches), **and** an explicit toggle-edge detector confirms each `o_led` transition timestamp equals `N*HALF_PERIOD` for consecutive N=1,2,3,...,20 with no skipped or extra toggles. |
| **BLINK-05** (50% duty cycle) | `o_led` is high for exactly `HALF_PERIOD` cycles and low for exactly `HALF_PERIOD` cycles per full `2*HALF_PERIOD`-cycle period. | Directed, derived from the same trace as BLINK-04 (no separate stimulus needed — this is a property of the recorded waveform). | Cover: measured high-run-length and low-run-length histograms both collapse to the single value `HALF_PERIOD` across >= 20 toggles, for each `HALF_PERIOD` in {1, 2, 4, 5}. | For every consecutive pair of toggle edges recorded in the BLINK-04 trace, the number of cycles `o_led` held a given value between the two edges equals `HALF_PERIOD` exactly (measured against the model's own toggle timestamps, i.e. an intrinsic self-consistency check plus DUT-vs-model equality). Zero deviations. |
| **BLINK-06** (glitch-free, registered output, at most one change per clock) | `o_led` is driven only from a flip-flop clocked by `clk`; it never changes other than in response to a rising `clk` edge, and changes at most once per cycle. | **Formal-tagged** (structural property — sim can only sample at clock edges and cannot itself prove the absence of a combinational path). Sim-side sanity check: monitor `o_led` with a zero-delay process between clock edges and confirm no transitions are observed strictly between two consecutive rising edges. | Formal: property that `o_led` is driven by a register (checked via `assign`-free / `always_ff`-only structural proof, or equivalently that `o_led` is stable except immediately following `posedge clk`). Sim cover: at least one clock period per `HALF_PERIOD` value sampled at sub-cycle resolution with no observed mid-cycle transition. | Sim: over the full directed run, zero `o_led` transitions detected at any simulation time step that is not coincident with a `clk` rising-edge simulation time. Formal: SBY proof of "no combinational fan-in from `cnt` (or any signal) to `o_led`" / equivalent registered-output property holds with no counterexample. |
| **BLINK-07** (parameter validity across HALF_PERIOD) | For any positive-integer `HALF_PERIOD`, BLINK-01 through BLINK-06 hold identically in structure, differing only in the numeric cycle count. `HALF_PERIOD = 0` is illegal/unspecified and out of scope for runtime checking (§5). | Constrained-random over the parameter itself: the entire BLINK-01..06 test suite is re-instantiated/re-run at `HALF_PERIOD ∈ {1, 2, 4, 5}` (meta-requirement — no new stimulus logic, just re-parameterization). `HALF_PERIOD = 0` is explicitly NOT tested at runtime (spec says behavior is unspecified; only a static/elaboration-time check, if any, is in scope — out of scope for this DV plan). | Cover: `HALF_PERIOD` parameter bins {1, 2, 4, 5} each exercise the full BLINK-01..06 test list with zero mismatches recorded per bin. | The BLINK-01..06 pass criteria above each individually pass (zero mismatches) for every `HALF_PERIOD` in {1, 2, 4, 5}. A single regression report tabulates pass/fail per (shall ID × HALF_PERIOD) cell; all cells must be PASS. |
| **BLINK-08** (no async reset — rst_n sampled synchronously) | The module contains no asynchronous-reset logic; `rst_n` takes effect only evaluated on a rising `clk` edge, never immediately when `rst_n` falls. | **Formal-tagged** (structural property about sensitivity list / reset architecture — not something a black-box I/O testbench can prove exhaustively). Sim-side sanity check: directed test that drops `rst_n` low at a non-clock-edge-aligned simulation time (mid-cycle) and confirms `o_led`/counter state does not change until the *next* rising `clk` edge. | Formal: property "no state element has an asynchronous sensitivity to `rst_n`" (checked via SBY structural check or equivalently: forcing `rst_n` low between two rising edges produces no output change until the next rising edge, exhaustively over reachable states). Sim cover: at least one trial where `rst_n` is deasserted at a simulation-time offset strictly between two rising clock edges. | Sim: `o_led` (and, where observable, `cnt`) sampled immediately after the mid-cycle `rst_n` fall (before the next rising edge) is unchanged from its pre-fall value; only the sample taken at/after the next rising edge reflects the reset. Formal: SBY proof holds with no counterexample at `FORMAL_BMC_DEPTH`. |

## Row count
8 rows (BLINK-01 through BLINK-08), one per spec "shall".

## Notes for dv-engineer
- Golden model API: `BlinkModel(half_period)`; call `.step(rst_n)` once per
  rising `clk` edge (feed the `rst_n` value sampled at that edge) and compare
  the return value to `dut.o_led` sampled at the same edge. See
  `hw/dv/common/models/blink.py` docstrings for exact semantics and the
  `__main__` self-check for worked examples at `HALF_PERIOD` = 1, 2, 4, 5.
- `cnt` is named in the spec text (§4) as the internal counter; sim-side
  checks in this plan intentionally avoid depending on probing `dut.cnt`
  wherever a black-box `o_led`-only check suffices (BLINK-03/04/05). Where a
  row does reference `cnt` (BLINK-01, BLINK-08 sanity checks), that is a
  best-effort whitebox aid for sim and the row is still formal-tagged as the
  authoritative proof, since sim alone cannot exhaustively confirm internal
  state without narrowing to specific sampled scenarios.
- BLINK-06 and BLINK-08 are structural/absence properties ("never happens",
  "no such logic exists") that a finite set of simulation traces cannot prove
  exhaustively — these are formal's responsibility. Sim provides regression
  sanity only.
