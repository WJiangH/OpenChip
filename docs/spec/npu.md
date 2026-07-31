# NPU Specification

Status: draft
Version: v1.1 (change order CO-NPU-01, §8 — adds the activation-load path; supersedes v1.0's silent gap, `hw/dv/npu/BUGS.md` A5/A6)
Owner: spec-architect · Implements: milestone M3 (integration), per `docs/spec/soc_1.md` §3.1/§3.2

## §1 Overview

The NPU is SoC-1's 1×8 weight-streaming, activation-stationary int8 GEMV vector
unit (ADR-0002 D1/D2, accepted). It is the single compute block that runs every
matrix-vector product in a `stories15M`-family decode step: it consumes an int8
weight byte stream over a dedicated point-to-point channel (not Wishbone,
`soc_1.md` §4.2), multiply-accumulates against a stationary int8 activation
vector held in a 2 kB on-chip SRAM, and produces either (a) a fresh int8
activation vector for the next layer, or (b) a single argmax token index for
the vocabulary-projection GEMV (`lm_head`) — see §4.4, which closes
`soc_1.md`'s **Q-SOC1-07**.

It is a Wishbone B4 slave for CSR/descriptor access only, at
`0x0002_0000`–`0x0002_FFFF` (`soc_1.md` §3.2); weight *data* never crosses this
window (`soc_1.md` SOC1-05, §4.2). It has no other bus mastership and issues no
requests of its own — the CPU (sole Wishbone master, `soc_1.md` SOC1-04)
programs a descriptor and writes `CTRL.GO`; the flash/PSRAM controller (a
separate, future `flash_ctrl.md` module) autonomously drives weight bytes into
this module's ingress port once armed (`soc_1.md` SOC1-18). A second,
independent point-to-point port (§2.3a) lets that same controller load the
activation SRAM directly, byte-for-byte, from flash — the module's *only*
CPU-independent way for an activation vector to acquire a nonzero value from
cold reset (§4.5 closes `hw/dv/npu/BUGS.md` A5).

This spec closes ADR-0002's **Q1** (quantisation arithmetic), **Q2**
(accumulator width), **Q4** (bus/streaming interface, jointly with
`soc_1.md` §4.2), and **Q8** (`lm_head` special case). It inherits ADR-0002's
**Q5** (special-function-unit scope), **Q6** (softmax numerics), and **Q7**
(KV-cache precision/residency) as explicit non-goals — those govern the
RMSNorm/softmax/RoPE/SwiGLU datapath *around* this module's GEMV calls, not the
GEMV contract itself, and remain open per §7.

## §2 Interface

### §2.1 Clock & reset

1. **NPU-01:** `clk` (in) and `rst_n` (in, synchronous, active-low, per
   `/CLAUDE.md`) are the module's only clock/reset. Every flop — CSR
   registers, the weight FIFO, the accumulator bank, the sequencer FSM, the
   activation SRAM's control logic — shall reset from `rst_n` to the values
   given in §3's register table and §4.3's `IDLE` state. The 2 kB activation
   SRAM's *data contents* are not required to reset (a hard macro; per
   ADR-0002 D5/Q3 below, this is the accepted `sky130_sram_2kbyte_1rw1r_32x512_8`
   OpenRAM macro) — only the sequencer's addressing/control state resets.

### §2.2 Wishbone CSR interface

2. **NPU-02:** Full Wishbone B4 pipelined slave signal set per `/CLAUDE.md`
   and `TEMPLATE.md` §2.2. The module receives only the 16-bit in-window
   offset (`wb_adr[15:0]`; the top-level decoder has already matched
   `wb_adr[19:16] == 4'h2` per `soc_1.md` SOC1-05/§3.2). `wb_stall` is tied
   low (this slave never backpressures — see NPU-03).
3. **NPU-03:** The module shall assert `wb_ack` exactly one cycle after every
   `wb_cyc && wb_stb`, for both reads and writes, regardless of offset or
   `CTRL`/`STATUS` state (single-cycle turnaround, no wait states). This
   satisfies a classic (non-pipelined) master (`soc_1.md` SOC1-04) with
   margin and interoperates with a pipelined one.
4. **NPU-04:** `wb_sel` is not honored — every accepted write updates the
   full 32-bit register named by the offset from `wb_dat_w`, regardless of
   `wb_sel`'s value. Firmware shall perform only full-word (aligned 32-bit)
   accesses to this window.
5. **NPU-05:** An offset within `0x0000`–`0x0FFF` (this module's decoded
   sub-range; the remainder of the 64 KB window is unimplemented headroom
   per `soc_1.md` §3.2) that does not match a register in §3's table shall
   read as `0x0000_0000` and silently ignore writes; `wb_err` is never
   asserted by this module (unmapped-region errors are the top-level
   decoder's job, `soc_1.md` SOC1-06, not this slave's).

### §2.3 Weight-stream ingress port

This is the dedicated, non-Wishbone channel `soc_1.md` §4.2 mandates
(closing ADR-0002 **Q4**'s bus-choice half; the descriptor/backpressure
contract below closes the rest of Q4).

| Signal | Dir | Width | Description |
|---|---|---|---|
| `i_ws_valid` | in | 1 | Flash/PSRAM controller has a weight word to offer. |
| `i_ws_data` | in | `WS_WIDTH` | Weight bytes, byte order per NPU-08. |
| `o_ws_ready` | out | 1 | This module's 2-deep FIFO (`soc_1.md` SOC1-11) has room. |

6. **NPU-06:** A transfer occurs only on a rising `clk` edge where
   `i_ws_valid && o_ws_ready` are both high. The flash/PSRAM controller
   (driving `i_ws_valid`/`i_ws_data`) shall hold both stable from the cycle
   it asserts `i_ws_valid` until the cycle the transfer completes — it shall
   never deassert `i_ws_valid` or change `i_ws_data` while `o_ws_ready` is
   low, and shall never drop a weight word (`soc_1.md` SOC1-11: stall, don't
   drop).
7. **NPU-07:** `o_ws_ready` shall be low whenever the 2-entry FIFO holds 2
   unconsumed entries, and high otherwise; this is the entire flow-control
   contract — there is no side-band credit or length signal on this port
   (length is carried by the CSR descriptor, §3, and independently by the
   flash controller's own descriptor, `soc_1.md` SOC1-12).
8. **NPU-08 (byte ordering — bit-exactness-critical):** For output-channel
   group `g = ⌊n/C⌋` (`C` = 8, §2.4) and reduction index `k` (`0 ≤ k < K`),
   the weight byte for output channel `n` at reduction index `k` — call it
   `w[k][n]`, the `(k·N + n)`-th byte of the flattened row-major weight
   matrix — shall arrive on the ingress port ordered **k-major,
   channel-minor**: for fixed `k`, the `C` bytes `w[k][g·C]` .. `w[k][g·C+C−1]`
   arrive consecutively (packed low-byte-first into successive `i_ws_data`
   words at `WS_WIDTH` bits per word), before any byte for `k+1`. This
   ordering is what lets the sequencer (§4.3) advance all `C` accumulators
   for reduction step `k` before the FIFO's next word is needed, and is
   independent of `WS_WIDTH` (§2.4) — only how many cycles one `k`-step takes
   changes with port width, never the byte order. The future `flash_ctrl.md`
   and offline export tooling must produce/consume this exact order; this is
   this module's half of that shared contract.

### §2.3a Activation-load ingress port (new, CO-NPU-01)

A second, independent point-to-point channel — separate from the weight-stream
port (§2.3) and its FIFO/MAC pipeline — that writes bytes directly into the
activation SRAM, sequentially from offset 0. This is the module's only
CPU-independent source of activation content and closes `hw/dv/npu/BUGS.md`
A5 (§4.5 gives the rationale and the numbers behind choosing this mechanism
over a CSR-mapped Wishbone write path).

| Signal | Dir | Width | Description |
|---|---|---|---|
| `i_actld_valid` | in | 1 | Flash/PSRAM controller has an activation-load word to offer. |
| `i_actld_data` | in | `WS_WIDTH` | Activation bytes, low-byte-first (NPU-25), same width class as the weight-stream port. |
| `o_actld_ready` | out | 1 | This module can accept a word this cycle (NPU-26). |

**NPU-24:** A transfer occurs only on a rising `clk` edge where
`i_actld_valid && o_actld_ready` are both high. The flash/PSRAM controller
shall hold both stable from the cycle it asserts `i_actld_valid` until the
transfer completes, exactly mirroring NPU-06's contract on the weight-stream
port (stall, don't drop, `soc_1.md` SOC1-11).

**NPU-25 (byte ordering and addressing):** Bytes are unpacked low-byte-first
from each `i_actld_data` word (word bit range `[8i+7:8i]` is byte `i`,
ascending `i`, mirroring NPU-14) and written to the activation SRAM at
sequentially increasing byte addresses starting from **0** — the first byte
of the first accepted word goes to address 0, the second to address 1, and
so on. There is no CSR-programmed base offset for this port (contrast
`ACT_BASE`, §3.4, which is a *read* address for GEMV dispatch, not a
destination for this port): an activation-load transfer always starts at
offset 0. This is sufficient for the port's only use case — the workload
(`profile.md`) needs exactly one activation-load per token (the token
embedding row) and every subsequent activation update is a GEMV writeback
(NPU-13) already addressed by the dispatching descriptor's own `OUT_BASE`.
The internal byte-address counter is `ASW = $clog2(ACT_SRAM_BYTES) = 11`
bits wide and wraps modulo `ACT_SRAM_BYTES` (2048); firmware programming a
flash-controller descriptor whose length exceeds 2048 bytes for this
destination is a documented software precondition violation (defined
wraparound, not corruption or an undefined access) — the same
software-precondition convention §3.4 already uses for `ACT_BASE`/`OUT_BASE`
overlap and `soc_1.md` SOC1-24 uses for CPU access alignment.

**NPU-26 (backpressure):** `o_actld_ready` shall be high whenever
`STATUS.BUSY == 0` and low whenever `STATUS.BUSY == 1` — this port and the
sequencer's own normal-mode SRAM writeback (NPU-13) both use the activation
SRAM's single writable port, so they are made mutually exclusive by
construction (an activation-load only ever proceeds while the sequencer is
`IDLE`) rather than arbitrated. Unlike the weight-stream port's 2-deep FIFO
(NPU-07), no buffering is needed here: a ready cycle accepts a full
`WS_WIDTH`-bit word directly into the SRAM write port at the port's full
rate, every cycle, with no internal stall beyond the `BUSY`-gate above.

**NPU-27 (no dispatch, no IRQ of its own):** An activation-load transfer is
not a `CTRL.GO` dispatch — it does not touch `STATUS.BUSY`/`DONE`/`ERR`,
`ERR_CODE`, or this module's IRQ outputs (§2.5), and it is invisible to
`K_LEN`/`N_LEN`/the sequencer FSM (§4.3) entirely. Completion is observed
only via the flash/PSRAM controller's own "stream done" status/interrupt
(`soc_1.md` SOC1-13, `irq[4]`) — the same signal SOC1-08's firmware-SRAM
boot load already uses, and firmware distinguishes an activation-load's
`irq[4]` from a weight-load's `irq[4]` only by which descriptor it dispatched
(both share one interrupt line; disambiguation is a firmware bookkeeping
concern, not a hardware one, matching how `soc_1.md` SOC1-12's destination
field is entirely the flash controller's own descriptor state).

### §2.4 Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `C` | fixed | 8 | Output lanes / MACs per fully-fed cycle (ADR-0002 D2, not a build parameter — changing it is a new ADR). |
| `WS_WIDTH` | positive integer, multiple of 8, divides `C·8` bits | 32 | Ingress port width in bits. Default matches `soc_1.md` SOC1-19's committed 32-bit/4 B-per-cycle external port; instantiating with `WS_WIDTH=64` (a future 8 B/cycle port swap) requires no sequencer redesign, only re-deriving how many cycles a `k`-step takes (§4.3) — this is the "build-time parameter... no datapath redesign" property `soc_1.md` SOC1-19 requires of the upstream port, mirrored here. |
| `ACT_SRAM_BYTES` | fixed | 2048 | Activation SRAM capacity (ADR-0002 D5, one `sky130_sram_2kbyte_1rw1r_32x512_8` macro — see Q3 note, §7). |

### §2.5 IRQ outputs

| Signal | Dir | Width | Description |
|---|---|---|---|
| `o_irq_done` | out | 1 | Level. Mirrors `STATUS.DONE` (§3). Wired at SoC level to `irq[6]` (`soc_1.md` §4.4). |
| `o_irq_err` | out | 1 | Level. Mirrors `STATUS.ERR` (§3). Wired at SoC level to `irq[7]` — this spec claims that previously-reserved line (`soc_1.md` §4.4 table lists `irq[7:31]` as reserved for exactly this kind of per-module extension). |

Both are level outputs, matching PicoRV32's native level-sensitive `irq[31:0]`
input (`soc_1.md` §4.4) — no pulse/edge behavior to reconcile.

## §3 Register map

Base `0x0002_0000` (`soc_1.md` §3.2). All registers 32-bit, aligned, only
full-word access supported (NPU-04).

| Offset | Name | Reset | Access | Description |
|---|---|---|---|---|
| `0x00` | `CTRL` | `0x0` | RW/pulse | Dispatch control. |
| `0x04` | `STATUS` | `0x0` | RO | Busy/done/error mirror. |
| `0x08` | `ERR_CODE` | `0x0` | RO | Last malformed-descriptor reason (§5). |
| `0x0C` | `K_LEN` | `0x0` | RW | Reduction depth `K`. |
| `0x10` | `N_LEN` | `0x0` | RW | Output width `N`. |
| `0x14` | `ACT_BASE` | `0x0` | RW | Input activation-vector byte offset. |
| `0x18` | `OUT_BASE` | `0x0` | RW | Output byte offset (normal mode only). |
| `0x1C` | `SCALE_M` | `0x0` | RW | Requantiser multiplier `M` (§4.1). |
| `0x20` | `SCALE_SHIFT` | `0x0` | RW | Requantiser shift `s` (§4.1). |
| `0x24` | `RESULT_IDX` | `0x0` | RO | Argmax winning index (argmax mode only). |
| `0x28` | `RESULT_VAL` | `0x0` | RO | Argmax winning requantised value (argmax mode only). |

### §3.1 `CTRL` (0x00)

| Bit | Name | Access | Behavior |
|---:|---|---|---|
| 0 | `GO` | W, pulse | Write 1 to dispatch the descriptor currently in `K_LEN`/`N_LEN`/`ACT_BASE`/`OUT_BASE`/`SCALE_M`/`SCALE_SHIFT`/`MODE`. Accepted only if `STATUS.BUSY == 0`; if `BUSY == 1`, the write is rejected (no dispatch), `ERR_CODE = BUSY_REJECT`, `STATUS.ERR` sets (§5). Always reads back 0. |
| 1 | `MODE` | RW | 0 = normal (write each requantised output byte to activation SRAM at `OUT_BASE`, §4.4). 1 = argmax (`lm_head`-style: no SRAM writes, track running max, populate `RESULT_IDX`/`RESULT_VAL`, §4.4). |
| 2 | `ABORT` | W, pulse | Write 1 to force the sequencer to `IDLE` immediately, clearing `BUSY` (and any in-flight accumulation state) regardless of current state. No-op if already `IDLE`. Firmware's recovery path for a stream-error mid-transfer (`soc_1.md` SOC1-14/irq[5], which this module cannot observe directly — see §5). Always reads back 0. |
| 31:3 | — | RO | Reserved, read 0.

### §3.2 `STATUS` (0x04)

| Bit | Name | Behavior |
|---:|---|---|
| 0 | `BUSY` | 1 from the cycle a `GO` is accepted until the sequencer returns to `IDLE` (§4.3). |
| 1 | `DONE` | Set the cycle compute-done occurs (§4.3); cleared the cycle the *next* `GO` is accepted. Not W1C — polling firmware reads it, then dispatches the next op, which clears it. Mirrored to `o_irq_done`. |
| 2 | `ERR` | Set the cycle a malformed descriptor is detected (§5); cleared the cycle the next `GO` is accepted. Mirrored to `o_irq_err`. |
| 31:3 | — | Reserved, read 0.

### §3.3 `K_LEN` / `N_LEN` (0x0C / 0x10)

Bits `[15:0]`: unsigned reduction depth `K` / output width `N`. Bits
`[31:16]`: reserved, read 0, writes ignored. Both cover the workload's actual
range with wide margin (`profile.md` §2: `K ∈ {48, 128, 288, 768}`,
`N ∈ {48, 128, 288, 768, 32000}` — all `< 2^16`).

### §3.4 `ACT_BASE` / `OUT_BASE` (0x14 / 0x18)

Bits `[10:0]`: unsigned byte offset into the `ACT_SRAM_BYTES`-deep (2048)
activation SRAM. Bits `[31:11]`: reserved. `OUT_BASE` is ignored (may be left
at any value) when `CTRL.MODE == 1`.

Firmware shall not overlap `[ACT_BASE, ACT_BASE+K)` and `[OUT_BASE,
OUT_BASE+N)` for the same descriptor (a read-during-write hazard on the
activation SRAM) — this is a documented software precondition, not
hardware-enforced, the same design choice `soc_1.md` SOC1-24 makes for CPU
memory-access alignment.

### §3.5 `SCALE_M` / `SCALE_SHIFT` (0x1C / 0x20)

`SCALE_M` bits `[15:0]`: unsigned 16-bit multiplier `M`. `SCALE_SHIFT` bits
`[4:0]`: unsigned 5-bit shift `s` (all 32 representable values are legal —
no illegal-value check needed, unlike `N_LEN`'s C-divisibility, §5). Together
they define the real-valued rescale factor `M / 2^s` applied by the
requantiser (§4.1). Bits above the used field width in each register: 
reserved, read 0.

### §3.6 `RESULT_IDX` / `RESULT_VAL` (0x24 / 0x28)

Meaningful only after a `CTRL.MODE == 1` (argmax) op completes (`STATUS.DONE
== 1`); undefined (implementation may hold stale or zero values) after a
normal-mode op or before the first argmax op since reset. `RESULT_IDX[15:0]`:
winning output-channel index `0 ≤ idx < N` (`N ≤ 32000 < 2^16`, `profile.md`
§2). `RESULT_VAL[31:0]`: the winning channel's requantised value, sign-
extended from int8 (§4.1).

## §4 Functional behavior

### §4.1 Quantisation arithmetic contract (closes ADR-0002 Q1, Q2)

**Multiply-accumulate.** Each MAC lane computes a signed 8-bit × signed 8-bit
product (full `[-128, 127]` domain on both operands — the costed Baugh-Wooley
signed multiplier, `explore/npu-dse/cost_model.py` "int8×int8 signed
multiplier" line, assumes this; there is no unsigned or asymmetric/zero-point
mode). Products accumulate into a **32-bit signed accumulator**, one per
active lane, matching ADR-0002 D5's "8 × 32-bit accumulator" (not the 26-bit
minimum ADR-0002 Q2 notes suffices for `K ≤ 2048`) — chosen, per Q2, "for
software sanity": every legal descriptor in this workload has `K ≤ 768`
(`profile.md` §2), giving a maximum possible `|Σ product|` of
`768 · 127 · 127 = 12,386,432`, thirteen orders of magnitude inside
`2^31 = 2,147,483,648`. **NPU-09:** the accumulator shall never overflow for
any descriptor with `K ≤ 4096` (a bound this module does not check — see §5
for what *is* checked); accumulation for `K > 4096` wraps per ordinary
two's-complement addition, an out-of-spec case with no defined behavior
requirement. **NPU-10:** the raw 32-bit accumulator value is never itself
software-visible (not architecturally exposed through any register) — only
the requantised result is.

**Scale granularity — per-tensor, not per-group (closes Q1's first
sub-question).** Upstream `llama2.c`'s own reference quantiser
(`runq.c`, [`quantize()`/`matmul()`](https://github.com/karpathy/llama2.c/blob/master/runq.c))
computes a fresh symmetric int8 scale per `GS`-element group (`GS` read from
the checkpoint header) and rescales each group's int32 partial sum by
`w->s[group] * x->s[group]` in float before summing across groups. `GS` is a
free export-time parameter of that same algorithm, not a fixed constant of
the matmul loop — setting `GS = n` (the full row length) degenerates it to
exactly one group per row, i.e. **one weight scale per output channel and one
activation scale for the whole vector**, with zero change to the reference
matmul's control flow. This spec adopts that degenerate case: this project's
own export/calibration step (a future sw-engineer/model-engineer deliverable,
out of scope here) shall produce per-tensor (whole-row) symmetric int8
weights and a per-descriptor activation scale, combined at firmware
dispatch time into the single `(M, s)` pair below. This is not a deviation
from `llama2.c`'s mechanism (the matmul loop is unchanged), only a specific,
project-chosen value of its `GS` parameter — chosen because ADR-0002's D5
costed exactly **one** requantiser block (15,793 µm², `cost_model.py`
`requant_area(mode="mul_shift")`) and no per-group scale-table storage or
indexing logic anywhere in the design; per-`GS=64`-style grouping was never
costed and would need either a scale FIFO alongside the weight FIFO or extra
CSR bandwidth this module's small window (§3) does not budget for.
**The bit-exactness "PyTorch reference" of `soc_1.md` §1 is this project's own
future golden model (`verif/common/models/`, per `/CLAUDE.md`), which must
implement this exact per-tensor scheme — not upstream `runq.c`'s literal
`GS=64` grouping.**

**Fixed-point requantiser (closes Q1's rounding/representation sub-question).**
ADR-0002 D5 already names the formula, unspecified only in its rounding rule:
`sat8(round((acc·M₃₂)≫s))`. This spec fixes every symbol:

- `M` = `SCALE_M` (§3.5), unsigned 16-bit (matches `cost_model.py`
  `mult_area(32, 16)` — a 32-bit × 16-bit multiplier).
- `s` = `SCALE_SHIFT` (§3.5), unsigned 5-bit, `0 ≤ s ≤ 31` (matches
  `cost_model.py` `barrel_shifter_area(32, 5)` — 5 stages, 32 shift amounts).
- `acc` = the lane's final 32-bit signed accumulator (all `K` reduction steps
  complete).
- `t = acc · M` — signed 48-bit intermediate (`32`-bit signed × `16`-bit
  unsigned).
- **NPU-11 (rounding — round-half-away-from-zero):**
  ```
  if s == 0:  rounded = t
  else:       half = 1 << (s - 1)
              rounded =  ((t + half) >> s)   if t >= 0
                        -((-t + half) >> s)  if t <  0
  ```
  (`>>` here is an unsigned/logical shift of a non-negative magnitude in both
  branches — the sign is reapplied afterward.) This ties round to the larger
  magnitude, away from zero, matching C's `round()` — the same function
  `runq.c`'s own `quantize()` uses (§ above) — rather than round-half-to-even.
- **NPU-12 (saturation):** `out = sat8(rounded) = clamp(rounded, -128, 127)`,
  a full signed-int8 clamp (tighter than `runq.c`'s unchecked `(int8_t)`
  cast, which relies on the exported scale never actually producing a
  ±128 boundary case — this module clamps explicitly and unconditionally,
  never relying on that assumption).
- **NPU-13:** In normal mode (`CTRL.MODE == 0`), `out` for channel `n` is
  written to activation SRAM at `OUT_BASE + n` (one byte). In argmax mode
  (`CTRL.MODE == 1`), `out` is never written to SRAM — it is compared against
  the running maximum (§4.4).

The offline procedure by which firmware/export tooling *derives* a desired
real-valued rescale factor into an `(M, s)` pair (e.g. maximizing precision
for a given target ratio) is calibration/export-tooling policy, out of scope
for this hardware spec — precisely analogous to how `soc_1.md` Q-SOC1-04
defers register-generation tooling and SOC1-26 (§5 below) defers
descriptor-content policy. What is normative here is only what hardware does
with whatever `(M, s)` firmware has programmed (NPU-11/12), which is fully
and precisely stated above.

### §4.2 Weight-stream ingress and lane feeding

**NPU-14:** The 2-deep FIFO (§2.3) buffers `WS_WIDTH`-wide words. Bytes are
unpacked low-byte-first: word bit range `[8i+7 : 8i]` is byte `i` of that
word's `WS_WIDTH/8` bytes, consumed in ascending `i` order (NPU-08's ordering
applies across this unpacking).

**NPU-15 (bandwidth-following, not bandwidth-requiring):** The sequencer
advances lane `c`'s accumulator for reduction step `k` as soon as byte
`w[k][g·C+c]` (§2.3) has been unpacked from the FIFO; it does not wait for
all `C` lanes' bytes for step `k` to arrive before advancing any of them.
With `soc_1.md`'s committed `WS_WIDTH = 32` (4 bytes/cycle, SOC1-19), one
`k`-step's `C = 8` bytes arrive across 2 FIFO words (nominally 2 cycles when
the FIFO has data), so lanes 0–3 and lanes 4–7 advance one cycle apart —
**effectively 4 MACs/cycle**, matching `soc_1.md` §4.2's cited "12.8 tok/s at
4 B/cycle" (`explore/npu-dse/results.md` §4) exactly. If `WS_WIDTH` is later
built as 64 (an upgraded 8 B/cycle port, `soc_1.md` SOC1-19's explicitly
anticipated "future part swap"), the same 8 bytes arrive in a single word and
all 8 lanes advance in one cycle — 8 MACs/cycle, ADR-0002 D4's 25.4 tok/s
headline — with **no change to this module's RTL**, only its `WS_WIDTH`
instantiation parameter (§2.4). This is the concrete mechanism behind
`soc_1.md` SOC1-19's "build-time parameter... no datapath redesign" claim.

**NPU-16:** The activation byte `x[ACT_BASE + k]` is read once per reduction
step `k` and broadcast to all lanes active that step (ADR-0002 D1:
"activation vector is stationary/broadcast"). For `N > C`, the sequencer
repeats the full `K`-step pass once per output-channel group
`g = 0 .. N/C − 1`, re-reading the same `K` activation bytes from SRAM each
pass (cheap: on-chip SRAM read, not off-chip traffic) against a fresh `K`
bytes of weight per group arriving over the ingress port. Total weight bytes
consumed per descriptor: `K · N`.

### §4.3 GEMV sequencing (closes SOC1-20's ordering requirement for this module)

| State | Entry condition | Behavior | Exit |
|---|---|---|---|
| `IDLE` | reset, or `ABORT`, or op complete | `BUSY=0` | `CTRL.GO` accepted → `RUN` |
| `RUN` | `GO` accepted | Consume weight bytes per §4.2; advance accumulators; `BUSY=1` | all `K·N` bytes consumed → `TAIL` |
| `TAIL` | last byte consumed | Drain the requantiser pipeline for the last output-channel group (fixed latency, a few cycles) | pipeline drained → `DONE` |
| `DONE` | requantise complete | Set `STATUS.DONE`/`o_irq_done`; in argmax mode, `RESULT_IDX`/`RESULT_VAL` are now valid | next cycle → `IDLE` |

**NPU-17:** `STATUS.BUSY` is 1 throughout `RUN` and `TAIL`, and 0 in `IDLE`;
it is not defined as a separate one-cycle `DONE` state — `DONE`'s effects
(status/IRQ update) are latched the same cycle the FSM would otherwise
re-enter `IDLE`.

**NPU-18 (compute-done vs. stream-done ordering, per `soc_1.md` SOC1-20):**
this module's `o_irq_done` (→ `irq[6]`) shall never assert before all `K·N`
weight bytes for the descriptor have been consumed from the FIFO — and
therefore never before the flash/PSRAM controller's own stream-done
(→ `irq[4]`, `soc_1.md` SOC1-13) has fired, since that controller cannot
finish sending bytes this module hasn't yet received. Firmware/DV shall not
treat `irq[4]` as a proxy for result-readiness; only `irq[6]`/`STATUS.DONE`
means the result (SRAM writes or `RESULT_IDX`/`RESULT_VAL`) is valid.

**NPU-19 (`ABORT` recovery):** This module has no direct visibility into the
flash controller's `irq[5]` (stream error, `soc_1.md` SOC1-14) — an underrun
there leaves this module's FIFO simply starved (`o_ws_ready` high, no more
data arriving), stuck in `RUN` indefinitely. Firmware's ISR for `irq[5]`
shall write `CTRL.ABORT` before reprogramming/retrying, per §3.1.

### §4.4 Result path — normal-mode writeback vs. argmax mode (closes Q-SOC1-07)

Every non-`lm_head` op (`wq/wk/wv/wo/w1/w2/w3`, `profile.md` §2, `N ≤ 768`)
uses **normal mode**: each requantised int8 output is written to the 2 kB
activation SRAM (§4.1 NPU-13) for the next op to consume. This cannot extend
to `lm_head` (`1×288 @ 288×32000`, `N = 32000`, 59% of a token's MACs and
weight bytes, `profile.md` §2): `32000` output bytes do not fit in a 2048-byte
SRAM by 15.6× — there is no `OUT_BASE` at which normal-mode writeback is even
representable for this op. A result path for `lm_head` is therefore not
optional; three options, decided with numbers:

- **Rejected: on-chip buffer for all 32,000 logits.** Needs 32 KB of new
  SRAM — 16× the existing 2 kB macro. At ADR-0002's own OpenRAM density
  (≈142,000 µm²/KB, `explore/npu-dse/results.md` §1) that is **≈4.55 mm²**
  (16 × 284,538 µm² per §1's 2 kB macro figure), against a 3.24 mm² total
  core budget already spending 0.449 mm² on this module (`results.md` §7.2)
  — this alone is ≈1.4× the 3.24 mm² core budget, for a
  buffer needed only transiently, once per token. Rejected on area grounds,
  the same reasoning `soc_1.md` §1 uses to reject on-chip weight storage.
- **Rejected: stream all 32,000 requantised bytes to the CPU over Wishbone.**
  Bandwidth is not actually the binding constraint (8,000 word-reads at the
  CPU's classic ack-per-transaction rate, generously 5 cycles/transaction,
  costs ≈40,000 cycles ≈ 0.8 ms — only ≈3.5% of `lm_head`'s own ≈23 ms compute
  time at 8 MACs/cycle, `1,152,000 cyc / 50 MHz`). The real objection is
  **orchestration purity**: 8,000 CPU-serviced transfers per token directly
  contradicts ADR-0003's "CPU job is orchestration only" framing
  (`soc_1.md` SOC1-10) — and it is needed only if downstream sampling wants
  the full probability distribution (temperature/top-k), which this spec
  does not select (below).
- **Chosen: streaming argmax.** The running-maximum compare needed to track
  "best channel so far" is already adjacent to the existing per-channel
  requantise-and-write logic (§4.1 NPU-13) — in argmax mode it replaces the
  SRAM write with a compare against a held `(RESULT_VAL, RESULT_IDX)` pair,
  updated in place, negligible extra area, zero new SRAM, zero WB traffic
  during the GEMV. Firmware reads `RESULT_IDX` **once**, after `STATUS.DONE`,
  to obtain the next token.

**NPU-20:** This spec commits `lm_head` (and any other `N > 2048`-byte-output
descriptor) to **greedy (argmax) decoding only** — `CTRL.MODE = 1` is the only
representable path for such a descriptor; there is no hardware support for
recovering the full logit vector for temperature/top-k sampling. Extending to
stochastic sampling (`profile.md` §5 item 5, flagged there as unresolved) is
a change order against this module, not a silent extension.

### §4.5 Activation-load path (new, CO-NPU-01 — closes `hw/dv/npu/BUGS.md` A5)

**The gap.** From `rst_n` deassertion, the activation SRAM's data contents
are unspecified (NPU-01) and, empirically, zero (`BUGS.md` A5's
`test_sram_reset_content_finding` repro). Every write to that SRAM is
normal-mode GEMV writeback (NPU-13), a function of the *existing* activation
content with no additive/bias term (§4.1) — so an all-zero start is
absorbing: no sequence of normal-mode GEMVs can ever produce a nonzero
activation byte. `profile.md` §1's workload begins each token by looking up
a 288-byte (`dim`) row of the tied embedding/`lm_head` matrix for the current
token id — data that lives in external flash alongside the weights, not
anywhere already on-chip — and that row is the first-layer input. Before
this change order there was no CPU-visible or hardware-autonomous path for
that row (or any other externally-sourced value) to reach the activation
SRAM at all.

**Options evaluated, decided with numbers.** The embedding row is 288 bytes
(`profile.md` §1 `dim`), sourced from flash, needed once per token, ahead of
that token's first GEMV dispatch:

- **(i) Chosen: extend the weight-stream descriptor's destination mode.**
  `soc_1.md` SOC1-12 already has a destination-bit precedent (weight FIFO vs.
  firmware SRAM, established for the boot-time firmware load, SOC1-08); this
  change order adds a third destination value routing to this module's new
  §2.3a port. At the committed `WS_WIDTH = 32` (`soc_1.md` SOC1-19, 4 B/cycle
  @ 50 MHz), 288 B is 72 words = **72 cycles ≈ 1.44 µs**.
- **(ii) Rejected (standalone): map the activation SRAM into the CSR window
  for direct Wishbone writes.** At the CPU's classic ack-per-transaction rate
  (generously 5 cycles/transaction, the same figure §4.4 uses for the
  `lm_head` result-path comparison), 72 words costs **360 cycles ≈ 7.2 µs**.
  Both (i) and (ii) are three to four orders of magnitude below the
  ≈1,953,792-cycle (≈39 ms) GEMV budget for one token (`soc_1.md` §1, D4) —
  **speed does not distinguish them.** What does: (ii) does not actually
  solve the problem. The embedding row lives in external flash; the CPU has
  no on-chip copy to write from (firmware SRAM holds code/data, not a 9.2 MB
  embedding table — `soc_1.md` §3.2's area note, and `profile.md` §2's
  `lm_head` row shows the *shared* embedding/classifier matrix is
  `288 × 32000` bytes, itself the largest single tensor in the model). Using
  (ii) at all would first require the CPU to read the row from flash over
  Wishbone — reintroducing exactly the "CPU-mediated, through the WB bus"
  pattern `soc_1.md` §4.2 already rejected for the weight datapath, and the
  same orchestration-purity objection §4.4 raises against CPU-serviced
  per-byte transfers (`soc_1.md` SOC1-10). (ii) is rejected as a standalone
  mechanism: redundant with (i) for this module's only real use case, and it
  would add CSR decode logic and a second write-port mux input for the
  activation SRAM (contending with the one NPU-13 already needs) for zero
  net capability over (i).
- **(iii) Both — rejected as unnecessary.** Nothing in `profile.md`'s
  workload needs a CPU-authored activation write (every activation value
  either comes from flash, once per token, or from a prior GEMV's own
  writeback). DV's module-level testbench already drives the weight-stream
  ingress port directly with no real flash controller present
  (`BUGS.md` A5's own "weights are 100% DV-controlled" framing) — the same
  is true of the new §2.3a port by construction, so DV's numeric-coverage
  need (the actual trigger for this change order) is served by (i) alone,
  without also paying for (ii)'s CSR/mux cost.

**NPU-24 through NPU-27 (§2.3a)** are this option's hardware contract.
Firmware's sequencing (informative, not itself a hardware requirement): at
the start of each token, dispatch a flash-controller descriptor with
destination = activation SRAM (`soc_1.md` SOC1-12) and length = `dim`
(288 B for `stories15M`, `profile.md` §1) before dispatching any GEMV whose
`ACT_BASE` reads that region; the two mechanisms never execute concurrently
because NPU-26 gates the new port on `STATUS.BUSY == 0`.

**NPU-28 (group-boundary stall bound — closes `hw/dv/npu/BUGS.md` A6):** at
each output-channel-group boundary (§4.2 NPU-16, `N/C − 1` times per
descriptor with `N > C`), the sequencer re-reads the activation SRAM from the
start of the `K`-byte range for the next group; this introduces **at most one
stall cycle** in which the sequencer does not consume a weight-FIFO word —
`o_ws_ready` may deassert during that cycle exactly per NPU-07's existing
2-entry-FIFO contract (never more, and never in violation of NPU-07). This
bound is independent of `K`, `N`, and `WS_WIDTH`, and does not apply at a
descriptor's final group (no re-read follows it). This matches
`BUGS.md` A6's empirical observation (`o_ws_ready` dropping for exactly one
cycle per group boundary at max ingress rate) and gives formal (NPU-07's
proof) and the vplan a concrete number instead of an unmodeled latency.

## §5 Error conditions

**NPU-21 (malformed descriptor, closes SOC1-26 for this module):** on
`CTRL.GO` write, before dispatch, the sequencer checks, in this priority
order, and on the first match sets `STATUS.ERR`/`o_irq_err`, `ERR_CODE` per
the table below, and does **not** enter `RUN`:

| `ERR_CODE` | Value | Condition |
|---|---:|---|
| `NONE` | 0 | (no error; normal dispatch) |
| `K_ZERO` | 1 | `K_LEN == 0` |
| `N_ZERO` | 2 | `N_LEN == 0` |
| `N_NOT_MULTIPLE_OF_C` | 3 | `N_LEN % 8 != 0` (this module's sequencer has no partial-group/remainder handling; `profile.md` §2 shows every real `N` — 48, 128, 288, 768, 32000 — is already a multiple of 8) |
| `ACT_RANGE` | 4 | `ACT_BASE + K_LEN > 2048` |
| `OUT_RANGE` | 5 | `CTRL.MODE == 0 && OUT_BASE + N_LEN > 2048` |
| `BUSY_REJECT` | 6 | `GO` written while `STATUS.BUSY == 1` (§3.1) |

**NPU-22:** `SCALE_SHIFT`'s full 5-bit range and `SCALE_M`'s full 16-bit
range are both legal — no check is defined or needed for those fields (§3.5).

**NPU-23:** A weight-stream underrun/error (`soc_1.md` SOC1-14, `irq[5]`) is
not directly observable by this module; see NPU-19 for the firmware-mediated
`ABORT` recovery path. This module raises no interrupt of its own for that
condition — `irq[5]` (flash controller) is the sole hardware signal.

## §6 Verification notes (advisory)

- A Python golden model implementing NPU-09 through NPU-13 exactly (32-bit
  accumulate, per-tensor `(M,s)` requantise, round-half-away-from-zero,
  int8 saturate) is the reference for RTL bit-exactness — it must be
  derivable from §4.1 alone, without reading any RTL, per `/CLAUDE.md`
  Iron Rule 2.
- Directed corner cases, a floor not a ceiling: `s = 0` (no shift, NPU-11's
  first branch); `M = 0` (all-zero output, still exercises saturate/rounding
  logic trivially); accumulator at its workload-maximum magnitude
  (`K = 768`, all bytes at `±127`, `profile.md` §2) to confirm no overflow
  per NPU-09; every `ERR_CODE` in §5's table, individually and in
  combination (e.g. both `K_ZERO` and `ACT_RANGE` true — priority order per
  NPU-21 must be exercised); `WS_WIDTH = 32` vs. a `WS_WIDTH = 64` build
  (NPU-15) producing identical numerical results at different cycle counts;
  `ABORT` asserted mid-`RUN` and mid-`TAIL` (NPU-19); back-to-back
  descriptors with no idle cycle between `DONE` and the next `GO`;
  `lm_head`-shaped descriptor (`K=288, N=32000`, argmax mode) alongside a
  short transformer-body descriptor exercising the identical datapath at very
  different `N`.
- `soc_1.md` §6's system-level corner cases (reset mid-weight-stream, WB
  decode boundaries) apply to this module as a WB slave and weight-stream
  consumer; not repeated here.
- **New (CO-NPU-01):** an activation-load transfer (§2.3a) followed by a
  normal-mode GEMV that reads it back (`ACT_BASE = 0`) — this is the
  end-to-end path that unblocks `npu_requant.sv`'s toggle coverage
  (`BUGS.md` A5); directed lengths at least `{1, 288 (dim), 2048
  (ACT_SRAM_BYTES, boundary), 2049 (wraparound, NPU-25)}`; `o_actld_ready`
  observed low while `STATUS.BUSY == 1` (NPU-26); an activation-load
  descriptor's `irq[4]` distinguished only by firmware bookkeeping from a
  weight-load's (NPU-27) — not a hardware distinction to test for. Separately,
  a directed `N > C` descriptor at max ingress rate confirming NPU-28's
  one-cycle group-boundary bound (`BUGS.md` A6), including the negative
  check that it is never more than one cycle.

## §7 Open questions

**Q3 (ADR-0002, SRAM macro choice) — RESOLVED by inheritance.** ADR-0002's
own accepted D5 recommendation already specifies "one 2 kB OpenRAM 6T macro"
(`sky130_sram_2kbyte_1rw1r_32x512_8`) as part of the costed, accepted design
— Q3 was left open in ADR-0002's own open-questions list, but its answer was
already baked into the recommendation that got accepted. This spec adopts it
explicitly (§2.4 `ACT_SRAM_BYTES = 2048`) rather than re-deriving it.

**Q5 (ADR-0002, special-function-unit scope) — inherited, still open.**
Which of exp/rsqrt/reciprocal are in hardware, and to what precision,
governs RMSNorm/softmax/SwiGLU — none of which this module's GEMV/requantise
contract depends on. Out of scope here; blocks a future spec revision or
sibling module (SFU) before RMSNorm/softmax/SwiGLU can be built.

**Q6 (ADR-0002, softmax numerics) — inherited, still open.** Same reasoning
as Q5; affects token-level bit-exactness against the golden model but not
this module's GEMV contract.

**Q7 (ADR-0002, KV-cache precision/residency) — inherited, still open.**
Whether KV-cache traffic is int8 (as `profile.md` assumes for its byte
counts) or another format, and who owns its addressing, is undecided; it
does not use this module's weight-stream or CSR interface and is not
resolved here.

**Q-NPU-01 (new, low priority).** NPU-20 commits this design to greedy
decoding only. If the project later wants temperature/top-k sampling, the
result-path decision in §4.4 needs revisiting (likely a secondary,
lower-throughput streaming-readout mode alongside argmax, not a replacement
for it) — flagged so a future sampling-mode decision doesn't silently
conflict with NPU-20.

## §8 Change log

**v1.0 → v1.1 (CO-NPU-01, this change order).** Ruled by the maintainer-proxy
per issue #15 (`hw/dv/npu/BUGS.md` A5, filed against v1.0 by DV as a
spec/system-level gap, not an RTL defect — Iron Rule 2): **revise the spec**
rather than waive the coverage gate it caused.

- Added: §2.3a (activation-load ingress port: `i_actld_valid`, `i_actld_data`,
  `o_actld_ready`), NPU-24, NPU-25, NPU-26, NPU-27, §4.5 (rationale + rejected
  alternatives), NPU-28 (`BUGS.md` A6's stall bound), §6 corner cases, this §8.
- Changed: §1 overview (mentions the new port); no existing register, shall,
  or signal in v1.0 was altered or removed — this is a strict addition.
- **Invalidated downstream artifacts** (each needs a follow-on issue filed to
  the owning role, not fixed here — chief-architect writes no RTL/DV):
  - `hw/rtl/npu/npu.sv`, `hw/rtl/npu/npu_act_sram.sv` — need the new port,
    the `BUSY`-gated write-port mux input, the wraparound counter (NPU-25),
    and (if not already exactly one cycle) an RTL fix to match NPU-28's bound
    — **rtl-engineer**, branch `rtl/npu`.
  - `hw/dv/common/models/npu.py` — golden model has no activation-load or
    group-boundary-stall model at all today (`BUGS.md` A4/A6); needs both,
    from this spec text alone, not from reading the RTL fix above —
    **verif-architect**, then **dv-engineer** for the directed tests listed
    in §6 and closing `BUGS.md` A5/A6 — branch `dv/npu`.
  - `hw/dv/npu/vplan.md`, `hw/dv/npu/BUGS.md` — A4 and A5 close (mechanism now
    specified); A6 closes (bound now specified); new vplan rows needed for
    NPU-24–28 — **verif-architect** / **dv-engineer**.
  - `hw/formal/` has no NPU proofs yet; when one lands, NPU-07's existing
    proof extends naturally to cover NPU-26's `BUSY`-gated backpressure on
    the new port — **formal-engineer**, no action required now.
  - `docs/spec/soc_1.md` — SOC1-12 destination field extended in the
    companion edit of this same change order (see that file's own §8-style
    note); not a separate follow-on issue.
