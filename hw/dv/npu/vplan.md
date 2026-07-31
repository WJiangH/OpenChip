# npu — Verification Plan

Source of truth: `docs/spec/npu.md` §2–§5 (NPU-01..23), read against
`docs/spec/soc_1.md` for system context (memory map §3.2, IRQ map §4.4,
bus §2.2). Golden model: `hw/dv/common/models/npu.py` (`NpuModel`,
`requantize`, `pack_weight_stream`).

Clean room: this plan and the model were written from spec text only; no
`hw/rtl/` file was read (`/CLAUDE.md` Iron Rule 2).

## Strategy notes

- Every register-level check compares the DUT's `wb_dat_r`/`wb_ack`
  against `NpuModel.read_csr()` / a directly-computed expected value —
  never against a previous simulation run.
- Every weight-stream / compute check drives `NpuModel.step(ws_valid,
  ws_data)` in lock-step with the DUT's `i_ws_valid`/`i_ws_data` each
  rising `clk` edge, and compares `o_ws_ready` against the model's
  returned `ws_ready`, and post-`STATUS.DONE` SRAM contents /
  `RESULT_IDX`/`RESULT_VAL` against the model's `act_sram` /
  `result_idx`/`result_val_signed`. `NpuModel.dispatch_and_run()` is the
  same code path used for directed single-shot descriptors.
- `C = 8` is fixed by the spec (not a build parameter); `WS_WIDTH` is
  swept at {32 (committed default, `soc_1.md` SOC1-19), 64 (anticipated
  upgrade, NPU-15)} wherever a row's behavior could plausibly depend on
  it. Workload-realistic `(K, N)` pairs come from `profile.md` §2: `K ∈
  {48, 128, 288, 768}`, `N ∈ {48, 128, 288, 768, 32000}`.
- "Formal" tag: the requirement is a structural or "never happens"
  property that a finite set of simulation traces cannot prove
  exhaustively (register-driven combinational contracts, FSM invariants,
  absence properties) — handed to the formal-engineer. A sim-side sanity
  check is still listed since sim runs regardless and catches gross
  violations early. NPU-09 is a numeric bound over up to 4096 sequential
  cycles — outside `FORMAL_BMC_DEPTH`'s default reach (`flow/gates.mk`,
  20) — so it is verified by directed sim at the workload-legal maximum
  (`K=768`) plus the spec's own closed-form analytic bound, not formal
  BMC; a k-induction proof is a possible future formal stretch goal, not
  required for sign-off.
- Rows below are one per numbered spec "shall" (NPU-01..23). NPU-20 has
  no independent hardware check beyond NPU-21's `OUT_RANGE` — its row
  says so explicitly rather than inventing new stimulus.

| Shall ID | What to test | Method | Coverage point | Executable pass criterion |
|---|---|---|---|---|
| **NPU-01** (reset values) | While `rst_n` is low and on the first rising edge after deassertion, every CSR reads its §3 reset value (`CTRL`,`STATUS`,`ERR_CODE`,`K_LEN`,`N_LEN`,`ACT_BASE`,`OUT_BASE`,`SCALE_M`,`SCALE_SHIFT`,`RESULT_IDX`,`RESULT_VAL` all 0) and the sequencer is `IDLE`; activation-SRAM *contents* are explicitly not required to reset. | Directed (sim), **formal-tagged** for the "every flop resets" structural claim (exhaustive over reachable pre-reset states). | Cover: reset with SRAM pre-loaded non-zero (from a prior op) vs. freshly-instantiated; reset asserted mid-`RUN`. | Sim: every CSR in `NpuModel.reset()`'s value set matches DUT `wb_dat_r` read-back post-reset; SRAM bytes untouched by reset are excluded from the comparison. Formal: SBY proof `rst_n |-> ##1 (all CSR flops == reset value)` holds at `FORMAL_BMC_DEPTH`, zero counterexamples. |
| **NPU-02** (WB slave signal set) | Full Wishbone B4 pipelined slave port exists and `wb_stall` is tied low always. | Directed (sim, port-level smoke test) + **formal-tagged** (`wb_stall == 0` is a permanent structural tie, provable exhaustively). | Cover: `wb_stall` sampled every cycle across every other test's traffic (a monitor assertion, not a standalone test). | Sim: a bound monitor flags any cycle where `wb_stall != 0`; zero flags over the full regression. Formal: SBY proof `wb_stall == 0` holds unconditionally, no counterexample. |
| **NPU-03** (ack timing) | `wb_ack` asserts exactly one cycle after every `wb_cyc && wb_stb`, for reads and writes, at every offset and in every `CTRL`/`STATUS` state. | Directed + constrained-random (randomize offset, r/w, and current `BUSY`/`ERR` state at issue time). | Cross-cover: {offset in {mapped, unmapped}} x {read, write} x {issued while `IDLE`, `RUN`, `TAIL`/`DONE`}. All bins hit. | For every `wb_cyc && wb_stb` cycle, `wb_ack` is 1 exactly one cycle later and 0 on all other cycles for that transaction; zero deviations over the full randomized run. |
| **NPU-04** (`wb_sel` ignored) | A write with any `wb_sel` pattern (including all-zero or a single byte lane) updates the full 32-bit register from `wb_dat_w`, identically to `wb_sel = 4'hF`. | Directed: repeat one register-write test at each of the 16 `wb_sel` values. | Cover: `wb_sel` ∈ {0x0..0xF} each exercised on at least one writable register. | Post-write read-back equals the written 32-bit value for every `wb_sel` value tested, including `wb_sel = 0x0` (still a full update per NPU-04) — zero mismatches against `NpuModel.write_csr`'s (sel-agnostic) result. |
| **NPU-05** (unmapped offsets) | An offset in `0x0000`-`0x0FFF` not in §3's table reads `0x0000_0000` and silently ignores writes; `wb_err` never asserts from this module for any offset in-window. | Directed, sweeping representative unmapped offsets (between/after known registers, e.g. `0x2C`, `0x100`, `0x0FFC`) + **formal-tagged** for the "never asserts `wb_err`" absence claim. | Cover: unmapped offsets at a low gap (`0x2C`), a high gap (`0x0FFC`), and just past the last defined register. | Sim: read returns `0x0000_0000`, a preceding value written to that offset never appears on a later read of a *mapped* register (no address aliasing), `wb_err` stays 0 for every offset tested — matches `NpuModel.read_csr()`'s default-0 branch. Formal: SBY proof `wb_err == 0` always, exhaustive over `wb_adr[15:0]`. |
| **NPU-06** (ingress transfer condition) | A transfer is captured only on a rising edge where `i_ws_valid && o_ws_ready` are both high; the module never samples `i_ws_data` on a cycle where either is low. | Directed: drive `i_ws_valid` high with `o_ws_ready` forced/observed low (FIFO full) and confirm no capture; **formal-tagged** for exhaustive "no capture without both-high" absence property. | Cover: valid-without-ready, ready-without-valid, and both-high, each at least once per `WS_WIDTH` build. | Sim: FIFO occupancy (inferred via subsequent `o_ws_ready` transitions and consumed byte count) changes only on both-high cycles — compare against `NpuModel.step()`'s identical push-gating logic. Formal: SBY proof no FIFO-write-enable-equivalent signal is ever high without both `i_ws_valid && o_ws_ready`. |
| **NPU-07** (`o_ws_ready` flow control) | `o_ws_ready` is low iff the 2-entry FIFO holds 2 unconsumed entries, high otherwise; no other flow-control mechanism exists. | **Formal-tagged** (combinational contract on internal FIFO occupancy, exhaustive over reachable occupancy states) + sim sanity via back-to-back pushes without a consuming `GO`. | Cover: FIFO occupancy 0, 1, 2 each observed with `o_ws_ready` checked. | Sim: pushing 2 words while `IDLE` (sequencer not consuming) drives `o_ws_ready` low on the 3rd offered word — matches `NpuModel.ws_ready` after two `step()` pushes with `state != "RUN"`. Formal: SBY proof `o_ws_ready == (fifo_count < 2)` holds for all reachable states. |
| **NPU-08** (byte ordering, bit-exactness-critical) | For output-channel group `g`, weight bytes for a fixed `k` arrive for all `C=8` channels of that group consecutively (k-major, channel-minor), packed low-byte-first per word, before any byte of `k+1`. | Directed: feed a marked/identifiable byte stream (each byte encodes its own intended `(k,n)`) via `NpuModel.pack_weight_stream()` word-for-word into the DUT and confirm the *result* (which requires correct (k,n) attribution to produce the right sum) matches. Constrained-random: random weight matrices, `WS_WIDTH` ∈ {32,64}. | Cross-cover: `WS_WIDTH` ∈ {32,64} x `N/C` ∈ {1, multiple groups} x `K` ∈ {small, `profile.md`-realistic}. | Post-`DONE`, DUT normal-mode SRAM writeback (or argmax `RESULT_IDX`/`RESULT_VAL`) matches `NpuModel.dispatch_and_run()`'s output bit-for-bit for every trial — a byte-order bug produces a wrong sum, which this end-to-end check catches without needing a whitebox probe. Zero mismatches. |
| **NPU-09** (accumulator never overflows, `K<=4096`) | The 32-bit signed accumulator never overflows for any legal descriptor (`K <= 768` per `profile.md`, spec's own bound extends the guarantee to `K<=4096`). | Directed: `K=768` (workload max), all activation and weight bytes at `±127` (the `|Σ product|`-maximizing pattern) — the spec's own cited worst case. | Cover: accumulator magnitude within one order of magnitude of `2^31` is *not* reachable at `K<=768`; this is the floor, not a ceiling — also run `K=4096` (spec's stated absolute bound) with the same all-`±127` pattern. | `NpuModel.to_s32()` never wraps for either `K` value (assert accumulator, computed independently in the test via plain Python `sum()`, stays within `[-2^31, 2^31-1]` before any `to_s32` call) and the DUT's final requantised output matches `NpuModel`'s bit-for-bit. Zero overflow, zero mismatches. |
| **NPU-10** (accumulator never software-visible) | No CSR, at any offset, ever exposes the raw 32-bit accumulator value — only `RESULT_VAL` (the *requantised* int8, sign-extended) is readable, and only in argmax mode. | **Formal-tagged** (absence property: no register's next-state or output expression is ever driven directly by an accumulator bit) + sim sanity sweeping every readable offset post-compute. | Cover: every defined register offset read once per completed op (normal and argmax mode), plus every unmapped offset in range. | Sim: no read from any offset, in any state, ever returns a value equal to a lane's live accumulator (checked by comparing every CSR read against `NpuModel`'s tracked internal `_accs`, which must never appear verbatim in any `read_csr` result other than via the defined `requantize()` path). Formal: SBY proof no register output port has a direct (unrequantised) fan-in from any accumulator bit. |
| **NPU-11** (rounding, round-half-away-from-zero) | `t = acc*M` rounds per the spec's exact pseudocode: ties (and only ties) round away from zero; `s=0` is a passthrough. | Directed: hand-computed corner cases — `s=0`; positive tie (`t` an exact multiple of `2^(s-1)` but not `2^s`); negative tie; non-tie positive/negative. Constrained-random: random `(acc, M, s)` triples compared against `NpuModel.requantize()`. | Cover: `s=0`; `s=31` (max); tie exactly at the rounding boundary, both signs; non-tie both signs. | DUT's post-`DONE` output byte matches `requantize(acc, M, s)` bit-for-bit for every directed and random trial (acc independently reconstructed from the test's own weight/activation stimulus, not read back from RTL). Zero mismatches. |
| **NPU-12** (saturation) | `out = clamp(rounded, -128, 127)`, unconditional, full signed-int8 clamp. | Directed: `(acc, M, s)` chosen so `rounded` lands just inside, just above, and just below each of `+127`/`-128`; **formal-tagged** for the clamp's unconditional/exhaustive nature. | Cover: `rounded` ∈ {126, 127, 128, -128, -129, -127} (boundary-adjacent set) each hit at least once. | Sim: output equals `sat8(rounded)` for every boundary case, matching `NpuModel.sat8()`. Formal: SBY proof output is always within `[-128,127]` regardless of internal `rounded` magnitude, exhaustive. |
| **NPU-13** (result-path routing) | Normal mode (`MODE=0`): each requantised output byte for channel `n` is written to activation SRAM at `OUT_BASE+n`. Argmax mode (`MODE=1`): no SRAM write occurs; the value instead updates the running max. | Directed: same descriptor run once in each mode, confirming SRAM at the normal-mode `OUT_BASE` region is untouched after an argmax-mode run (pre-poison the region with a sentinel before the argmax run). | Cover: both modes each run at least once per `(K,N)` shape tested elsewhere in this plan (piggybacks on those rows' stimulus, not separate). | Normal mode: SRAM bytes `[OUT_BASE, OUT_BASE+N)` match `NpuModel.act_sram` post-`DONE`. Argmax mode: SRAM bytes at the sentinel region are bit-identical to their pre-run sentinel value (zero writes leaked). |
| **NPU-14** (FIFO byte unpacking) | Within a `WS_WIDTH`-bit FIFO word, byte `i` (bits `[8i+7:8i]`) is consumed in ascending `i` order. | Directed: a single word with each byte set to a distinct marker value (e.g. `0x10,0x11,0x12,0x13` at `WS_WIDTH=32`), `K,N` sized so this word's 4 bytes map to 4 distinct, individually observable output channels. | Cover: `WS_WIDTH` ∈ {32,64}, marker word at the start, middle, and end of a group's byte stream. | Each marker byte's contribution appears in the correct output channel per `NpuModel._consume_word()`'s byte-index-to-`(k,c)` mapping — matches DUT output bit-for-bit. |
| **NPU-15** (bandwidth-following lane feeding, same result at any `WS_WIDTH`) | The sequencer advances a lane as soon as its byte is unpacked, not waiting for all `C` lanes; final numerical result is independent of `WS_WIDTH` (only cycle count differs). | Directed: run the identical `(K,N,weights,activations,M,s)` descriptor at `WS_WIDTH=32` and `WS_WIDTH=64`, compare outputs; separately record cycle counts and confirm the `WS_WIDTH=64` run completes in fewer weight-stream cycles. | Cover: `WS_WIDTH` ∈ {32,64} x at least one multi-group (`N>C`) shape. | Outputs bit-identical between the two `WS_WIDTH` builds (matches `NpuModel`'s own cross-`ws_width` self-check) and `WS_WIDTH=64`'s cycle count to `DONE` is strictly less than `WS_WIDTH=32`'s for the same descriptor. |
| **NPU-16** (activation broadcast, per-group re-read) | For `N>C`, the sequencer repeats the full `K`-step pass once per group, re-reading the same `K` activation bytes from SRAM each pass against fresh weight bytes. | Directed: `N = 2C` or `3C` (two/three groups), activation vector with distinct per-index values, confirm each group's output depends correctly on the *same* activation vector paired with *that group's* weight columns. | Cover: `N/C` ∈ {1, 2, 3, `768/8=96`, `32000/8=4000`}. | Every group's output bytes match `NpuModel`'s (which re-reads `act_sram[ACT_BASE:ACT_BASE+K]` fresh per group by construction) — a stale-activation bug (e.g. only re-reading group 0's values) is caught since later groups would diverge. |
| **NPU-17** (BUSY/DONE FSM) | `BUSY=1` throughout `RUN` and `TAIL`, `0` in `IDLE`; `DONE`'s status/IRQ update is latched the same cycle the FSM would otherwise re-enter `IDLE` (no separate one-cycle `DONE`-and-still-busy state). | **Formal-tagged** (FSM invariant, exhaustive over reachable states) + sim sanity recording `BUSY`/`DONE` every cycle of a directed run. | Cover: at least one full `IDLE->RUN->TAIL->DONE->IDLE` cycle sampled every cycle. | Sim: `BUSY` sampled every cycle exactly matches `RUN`/`TAIL` membership per `NpuModel.state`; the cycle `DONE` first reads 1 is the same cycle `BUSY` first reads 0. Formal: SBY proof `DONE && next(!DONE_write) -> !BUSY` (no state where `DONE` is set and `BUSY` is still 1), exhaustive. |
| **NPU-18** (compute-done never precedes stream-done) | `o_irq_done`/`STATUS.DONE` never assert before all `K*N` weight bytes have been consumed from the FIFO. | **Formal-tagged** (safety property: `DONE` implies consumed-byte-count `== K*N`) + directed sim withholding the final byte and confirming `DONE` stays 0 indefinitely. | Cover: withhold the last 1 byte of a descriptor (stall `i_ws_valid` forever after `K*N-1` bytes) — `DONE` must never assert in the observed window. | Sim: with the final byte withheld, `STATUS.DONE`/`o_irq_done` remain 0 for the entire (long, e.g. 10,000-cycle) observation window; once the byte is supplied, `DONE` asserts within the model's `TAIL`-then-`DONE` window. Formal: SBY proof `DONE -> (bytes_consumed == K_LEN*N_LEN)`, no counterexample. |
| **NPU-19** (`ABORT` recovery) | Writing `CTRL.ABORT=1` forces `IDLE` immediately, clears `BUSY` and any in-flight accumulation, regardless of current state; no-op if already `IDLE`. | Directed: assert `ABORT` mid-`RUN` (after a partial byte count), mid-`TAIL`, and while already `IDLE`; then dispatch a fresh, different descriptor and confirm no residual state (partial accumulator) leaks into it. | Cover: `ABORT` at {mid-`RUN` early, mid-`RUN` late, mid-`TAIL`, `IDLE`} each exercised. | `BUSY`, `STATUS.DONE`-unaffected-ness, and sequencer state match `NpuModel`'s post-`ABORT` state (`state=="IDLE"`, `busy==0`) in every case, including the `IDLE`-already no-op case (no spurious state change); the subsequent fresh descriptor's result matches a from-reset `NpuModel` run with zero contamination from the aborted op. |
| **NPU-20** (`lm_head`/large-`N` commits to argmax-only) | No separate hardware check exists for this — it is a consequence of NPU-21's `OUT_RANGE` check: any `MODE=0` descriptor with `OUT_BASE+N_LEN > 2048` (true for any `N` this large) is already rejected. | Not a separate test — see **NPU-21**'s `OUT_RANGE` row, exercised there at `lm_head`-scale (`N=32000`) explicitly. | (covered by NPU-21's `OUT_RANGE` cross-cover at `N=32000`) | (see NPU-21) — this row exists only to record that NPU-20 has no independent stimulus, per the vplan's one-row-per-shall rule. |
| **NPU-21** (malformed-descriptor priority) | On `CTRL.GO`, the six checks (`K_ZERO,N_ZERO,N_NOT_MULTIPLE_OF_C,ACT_RANGE,OUT_RANGE,BUSY_REJECT`) are evaluated in that priority order; first match sets `ERR_CODE`/`STATUS.ERR`, no dispatch. | Directed: each `ERR_CODE` individually, plus at least one multi-true combination per adjacent pair in the priority list (e.g. `K_ZERO` & `ACT_RANGE` both true) to confirm priority order, not just individual detection. | Cover: all 6 `ERR_CODE` values individually; cross-cover at least 3 combinations spanning non-adjacent priority pairs (e.g. `K_ZERO`+`OUT_RANGE`, `N_ZERO`+`BUSY_REJECT`, `ACT_RANGE`+`OUT_RANGE`). Includes `N=32000` (`lm_head`-scale) `OUT_RANGE` case (closes NPU-20's cross-reference). | `ERR_CODE`/`STATUS.ERR` match `NpuModel._write_ctrl()`'s priority-ordered result for every individual and combined case; `STATUS.BUSY` stays 0 (no dispatch) for every error case. Zero mismatches. |
| **NPU-22** (`SCALE_M`/`SCALE_SHIFT` full range legal) | Every representable value of both fields (`M` full 16-bit, `s` full 5-bit) is legal — no `ERR_CODE` is ever raised due to their value. | Directed/constrained-random: dispatch legal descriptors at `M` ∈ {0, 1, 0x7FFF, 0xFFFF} and `s` ∈ {0..31}, confirm no `ERR_CODE` results from these fields alone. | Cover: `M` boundary values {0, 0xFFFF}; `s` ∈ {0, 1, 15, 31} (full range represented, not exhaustively enumerated — 32 values is cheap enough to run all of, so do). | For every `(M,s)` combination tested, dispatch succeeds (`ERR_CODE==NONE`) when no *other* field is malformed, and the requantised output matches `NpuModel.requantize()` at that `(M,s)`. |
| **NPU-23** (weight-stream underrun not self-observable) | This module raises no interrupt of its own for a stream underrun/error — `o_irq_err` is driven only by this module's own `ERR_CODE` table (§5), never by ingress-port starvation. | **Formal-tagged** (absence property: `o_irq_err`'s only sensitivity list is the NPU-21 error-detection logic, not `i_ws_valid`/FIFO-empty conditions) + sim sanity: starve the FIFO indefinitely mid-`RUN` and confirm `o_irq_err` stays 0. | Cover: FIFO starved (no `i_ws_valid`) for a long window (e.g. 10,000 cycles) mid-`RUN`, both with and without a concurrent unrelated CSR read/write. | Sim: `o_irq_err`/`STATUS.ERR` remain 0 throughout the starved window (the module is simply stuck in `RUN`, per spec — matches `NpuModel`, which likewise never sets `err` from FIFO starvation, only from `_write_ctrl`'s NPU-21 checks). Formal: SBY proof `o_irq_err`'s driving expression has no term referencing `i_ws_valid`/FIFO-empty. |

## Row count
23 rows (NPU-01 through NPU-23), one per spec "shall". NPU-20 is a
covered-elsewhere row (no independent stimulus), noted above rather than
silently omitted.

## Notes for dv-engineer

- Golden model API (`hw/dv/common/models/npu.py`):
  - CSR/descriptor layer: `NpuModel.write_csr(offset, value)` /
    `read_csr(offset)`, register-offset constants `NpuModel.REG_*`,
    `ERR_*` code constants — call these after translating a WB
    write/read transaction, exactly mirroring §3's register map.
  - Cycle/weight-stream layer: `NpuModel.ws_ready` (compare to DUT
    `o_ws_ready` before deciding whether to assert `i_ws_valid` that
    cycle) and `NpuModel.step(ws_valid, ws_data)` (call once per rising
    `clk` edge, in lock-step with the DUT, exactly as `BlinkModel.step()`
    is driven per `hw/dv/blink/vplan.md`).
  - `NpuModel.dispatch_and_run(...)` is a convenience built from the same
    two calls above (no separate arithmetic path) for directed
    single-descriptor tests that don't need cycle-by-cycle control (e.g.
    backpressure injection) — most rows above can use it directly.
  - `pack_weight_stream(weights, n_len, c, ws_width)` turns a `K x N`
    weight matrix into the exact ingress-port word sequence (NPU-08
    order) to drive the DUT's `i_ws_data`.
- `NpuModel.act_sram` is a directly-writable `bytearray` for test setup
  (seeding the initial activation vector before a descriptor runs). This
  is a test-harness convenience only, not a modeled hardware interface —
  see spec-ambiguity **A4** below; real firmware has no defined path to
  do this, which is itself a spec gap, not a DV concern to route around
  silently.
- `result_val_signed` (a model-only convenience property, not a spec
  register) returns `RESULT_VAL` decoded back to a signed Python int
  ([-128,127]) for easier test assertions than sign-extended-in-32-bits
  comparisons.

## Spec ambiguities filed (not resolved by picking an interpretation)

Also recorded as docstring comments in `hw/dv/common/models/npu.py`, per
the verif-architect method (file immediately, do not resolve silently):

- **A1 — argmax tie-break undefined.** §3.6 defines `RESULT_IDX` as "the
  winning output-channel index" but never states what happens when two
  channels' requantised values tie. The golden model keeps the
  lowest-index winner; DV should treat this as the model's stance, not a
  confirmed hardware behavior, until RTL intake / chief-architect rules
  on it. **Row NPU-21's argmax coverage should include at least one
  engineered tie** once this is resolved, to confirm RTL matches whatever
  the ruling is (currently: matches the model's lowest-index-wins choice,
  informally).
- **A2 — simultaneous `GO`+`ABORT` in one write undefined.** §3.1
  describes `ABORT` as an override "regardless of current state" but
  never addresses a single write setting both `GO=1` and `ABORT=1`. The
  model applies `ABORT` first, then evaluates `GO`'s checks against the
  post-abort state (so an abort-then-immediate-redispatch reading is
  possible). This is a low-priority firmware-shouldn't-do-this case but
  is a genuine spec gap — flagged, not resolved.
- **A3 — `TAIL` state's exact cycle count undefined.** §4.3 says only
  "fixed latency, a few cycles." The model does not claim a specific
  number and DV must not assert a specific `TAIL` cycle count against
  it — only NPU-18's ordering guarantee is spec-backed. If RTL intake
  fixes a specific number, that number is an RTL implementation fact, not
  something to retrofit into this golden model as if the spec required
  it.
- **A4 — no defined path to load the *first* activation vector.** Neither
  `npu.md` nor `soc_1.md` describes how the initial activation vector
  (e.g. a token embedding, before any normal-mode NPU op has populated
  the SRAM via NPU-13 writeback) gets into the 2 kB activation SRAM. The
  CSR window is described as "CSR/descriptor access only" with no
  data-write register, and no other port into this SRAM exists in §2.
  This blocks writing a *fully* end-to-end (cold-boot, first-token)
  system-level test without an undocumented assumption. Flagged for
  chief-architect / a future `npu.md` revision, same disposition as the
  spec's own open-questions section (§7).
