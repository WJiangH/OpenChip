# npu DV bug / open-item log

Filed per `.claude/skills/dv-engineer/SKILL.md` and `/CLAUDE.md` Iron Rule 2:
every item below is a DUT-vs-spec or spec-silence finding, backed by a
replayable `make sim MOD=npu ...` repro. None of these are "fixed" here —
RTL is not touched by this role.

## A5 (extends vplan A4) — no CPU-visible path ever produces a *nonzero*
activation byte from a cold reset; blocks bit-exact closure of the
multiply-accumulate/requantize datapath (NPU-08/09/11/12/14/15/16) and the
toggle-coverage gate for `npu_requant.sv`/`npu.sv`

**Severity: high (blocks coverage gate + numeric bit-exactness closure).**
**Status: spec/system-level gap, not an RTL "shall" violation — routed to
chief-architect, not filed as an RTL defect.**

- **Repro:** `make sim MOD=npu TEST=test_sram_reset_content_finding` — reads
  back activation-SRAM bytes at offsets `{0,1,100,2047}` via the only
  DUT-boundary technique available (`Bus.read_act_byte`, a K=1,N=8
  all-`1`-weight argmax GEMV: every tied channel computes
  `sat8(act[addr]*1)` == `act[addr]`, and `RESULT_VAL` reveals it). All four
  sample as `0` on this build.
- **Spec basis:** `npu.md` §1/§3 give this module a CSR/descriptor-only
  Wishbone window — no register reads or writes the 2 kB activation SRAM.
  `soc_1.md`'s memory map confirms no *other* CPU-visible path exists either
  (the separate "Firmware SRAM" at `0x0001_0000` is a different memory).
  The *only* way any activation byte ever changes is as the output of a
  normal-mode GEMV (`out[n] = requantize(sum_k act[k]*w[k][n], M, s)`) — a
  function of the *existing* activation content, and the datapath has no
  additive/bias term anywhere (§4.1). If SRAM content starts at `0` (which
  NPU-01 explicitly does not forbid, and is what this Verilator build
  exhibits), every possible output from cold reset is *also* `0`, forever.
- **Consequences, measured, not hypothetical:**
  1. System-level cold-boot/first-token bootstrap has no defined path — this
     is the vplan's own **A4**, restated here with an empirical confirmation
     that it is load-bearing, not a theoretical corner.
  2. DV cannot drive a nonzero activation operand through the documented
     interface. Weights are 100% DV-controlled (the ingress-stream port),
     but with activation pinned at `0`, `acc` is always `0` regardless of
     weight content — a byte-ordering bug (NPU-08/14) or an off-by-one in
     lane feeding (NPU-15/16) would not change the (always-zero) result and
     is therefore **unobservable** via the documented interface. Only the
     `acc==0` corner of NPU-09/11/12's requantizer is exercised
     (`requantize(0,M,s)` across the full `M`/`s` range —
     `test_scale_full_range_legal`, `test_compute_bitexact_reachable_corners`
     — all pass), not the accumulator-bound, rounding-tie, or saturation
     corners the vplan's own "verification notes" call for, all of which
     need `acc != 0`.
  3. **Coverage, measured:** `make sim MOD=npu COVERAGE=1` (repro below) —
     line 95.0%, branch 92.1%, expr 90.8% (all above the 90% gate,
     `flow/gates.mk`), but **toggle 38.5%** (well below). Per-file toggle:
     `npu_wfifo.sv` 100%, `npu_act_sram.sv` 60.0%, `npu.sv` 35.3%,
     `npu_requant.sv` 19.5%. `npu_requant.sv`'s near-total loss is the
     direct, quantifiable cost of (2): with `acc` pinned at `0`, `t=acc*M`
     is `0` for every `M`, and the shifter/rounder/saturator downstream
     never sees a nonzero bit pattern to toggle, regardless of stimulus
     variety (confirmed: adding `test_csr_bit_toggle_sweep` — walking-ones/
     zeros across every writable CSR field — moved aggregate toggle only
     38.5%→38.5% net of rounding, i.e. essentially zero, because it doesn't
     touch the datapath at all).
- **Repro (coverage):** `make sim MOD=npu COVERAGE=1`, then
  `verilator_coverage --annotate <dir> hw/dv/npu/coverage.dat` (percentages
  above) — no annotated source was read to produce this report, only the
  tool's aggregate/per-file summary (clean-room boundary).
- **Open item / ask:** either (a) chief-architect rules that `npu_requant.sv`
  toggle coverage is waived with the `acc==0`-reachable-only rationale above
  as the human-approved note (Iron Rule 5), or (b) a future `npu.md`
  revision adds an activation-load path (closing A4 too), after which this
  suite's `read_act_byte`/chained-echo infrastructure (`Bus.read_act_byte`,
  `test_result_routing_normal_vs_argmax`) already exercises the general
  technique needed to extend numeric coverage once nonzero operands are
  reachable.

## A6 (new, informational) — npu.md is silent on whether the sequencer
takes an extra FIFO-non-consuming cycle at an output-channel group boundary

**Severity: low (no spec "shall" violated; documented for future formal/
vplan refinement).**

- **Observation:** driving a multi-group (`N>C`) descriptor at the maximum
  rate the ingress port allows (`i_ws_valid` held high every cycle) shows
  `o_ws_ready` drop for one cycle exactly at each output-channel-group
  boundary (consistent with the FIFO briefly holding 2 unconsumed words
  while the sequencer re-reads the activation vector for the next group,
  NPU-16), where a naively cycle-accurate reading of `NpuModel.step()`
  (which pops the FIFO unconditionally every call while `RUN`) would not
  predict a stall. `npu.md` §4.2 NPU-16 describes the re-read
  ("re-reading the same K activation bytes from SRAM each pass (cheap:
  on-chip SRAM read, not off-chip traffic)") but does not state whether
  this is zero-latency.
- **Disposition:** not a bug — NPU-06/NPU-07's contract (`o_ws_ready` low
  iff the FIFO holds 2 unconsumed entries) is satisfied either way; a
  transfer never occurs without `valid && ready`, and the FIFO never
  exceeds its 2-entry capacity. This suite's `Bus.edge()`
  (`hw/dv/npu/test_npu.py`) paces word-offering off the DUT's own
  ground-truth `o_ws_ready` (not the model's prediction) specifically to
  stay correct across this and any other unmodeled inter-group latency, and
  only hard-fails the *unsafe* direction (DUT claiming ready into a
  genuinely full FIFO).
- **Ask:** verif-architect/chief-architect consider a `npu.md` §4.2
  addendum stating whether inter-group latency is bounded (and by how much)
  — useful for a future formal NPU-07 proof's exact bound, and so a future
  golden-model revision can model it precisely instead of DV working around
  it structurally.

## Coverage gate summary (`make sim MOD=npu COVERAGE=1`)

| Metric | Result | Gate (`flow/gates.mk`) | Status |
|---|---:|---:|---|
| line | 95.0% (57/60) | 90% | PASS |
| branch | 92.1% (35/38) | — (not gated) | — |
| expr | 90.8% (119/131) | — (not gated) | — |
| toggle | 38.5% (1430/3714) | 90% | **FAIL — see A5** |

Not weakened, waived, or hidden here (Iron Rule 5) — reported as-is; the
toggle shortfall's root cause is A5, not insufficient test variety
(`test_csr_bit_toggle_sweep` was added specifically to rule that out).
