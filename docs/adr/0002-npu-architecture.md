# ADR 0002 — NPU architecture: streaming GEMV vector unit for int8 LLM decode

**Status: proposed — AWAITING HUMAN APPROVAL. This ADR is not accepted and no spec, RTL,
DV, model or PD work may derive from it until a human maintainer changes this line.**

Date: 2026-07-26 · Author role: chief-architect · Supersedes: nothing · Depends on: ADR 0001

Evidence base (both runnable, both reproduce every number cited here):

- `workloads/tinystories/profile.py` + `profile.md` — analytical operator profile
- `explore/npu-dse/cost_model.py` + `results.md` — sky130-grounded area/performance model

---

## Context

The north star is a small NPU SoC on sky130A at 50 MHz (`flow/gates.mk`
`CLOCK_PERIOD_NS = 20`) that runs real LLM inference, proven token-by-token against
PyTorch. Acceptance anchor: micro LLMs of 1–20 M parameters at int8, primarily the
llama2.c `stories15M` checkpoint (dim 288, 6 layers, 6 heads, hidden 768, vocab 32000,
max_seq_len 256 — read from the checkpoint header, `profile.md` §1).

Three measured facts drive everything below.

**Fact 1 — the workload is ~99 % GEMM, and all of it is M = 1.**
Per token at ctx = 128, stories15M does 15,630,336 MACs (98.89 % of FLOPs) across ten
distinct matrix ops, *every one of which is a matrix-vector product*. The single largest
is the classifier head `1×288 @ 288×32000` at **59 % of all MACs**. (`profile.md` §2)

**Fact 2 — arithmetic intensity is 1.00 MAC/byte.**
15,630,336 MACs against 15,641,568 bytes of int8 weights + KV cache. In batch-1 int8
decode each weight byte is loaded, used once, discarded. Therefore sustained MACs/cycle
can never exceed sustained weight bytes/cycle. Decode is **memory-bound, not
TOPS-bound**. (`profile.md` §3)

**Fact 3 — sky130 cannot store the weights, by three orders of magnitude.**
The densest published open sky130 macro stores ~57.6 kbit/mm²
(`sky130_sram_2kbyte_1rw1r_32x512_8`, LEF `SIZE 683.10 BY 416.54`). stories15M's 128 Mbit
of int8 weights would need **2,234 mm²** — 689× a 2×2 mm die core. Even the 260 K toy
model needs 59 mm², 18× over. (`results.md` §2)

Fact 3 turns the design from "an accelerator with a weight buffer" into "a streaming
dot-product engine hanging off an external memory port", and Fact 2 then fixes its size.

---

## Decision

### D1 — Dataflow: weight-streaming, activation-stationary GEMV vector unit

Weights stream through the array and are consumed once. The activation vector is
stationary/broadcast. C output accumulators stay put across the K reduction.

Explicitly **not** weight-stationary: at M = 1 each weight is used exactly once per
token, so there is no reuse for a weight-stationary dataflow to capture. The term is
vacuous for this workload, not merely suboptimal.

### D2 — Array shape: 1×8 (R = 1 reduction depth, C = 8 output lanes) = 8 int8 MACs/cycle

Sized to the balance point against a realistic 64-bit external weight port
(8 B/cycle = 400 MB/s at 50 MHz). Per Fact 2, MACs beyond bytes/cycle are idle silicon.

### D3 — Target area scenario: free-form ~2×2 mm die (3.24 mm² core after ring/PDN margin)

Not Tiny Tapeout for the stories15M target. See "Fit verdicts" below.

### D4 — Expected performance (stories15M, ctx = 128, 50 MHz)

| metric | value |
|---|---:|
| cycles/token (GEMV 1,953,792 + non-GEMM tail 13,292) | **1,967,084** |
| **tokens/s** | **25.4** |
| PE utilisation on M = 1 shapes | **100 %** |
| required core area | **0.449 mm²** (14 % of the 3.24 mm² budget) |
| tokens/s if the port is 32-bit (4 B/c) instead | 12.8 |

Human reading speed is ~4–6 tokens/s, so this is a live, readable demo with margin.

### D5 — Area breakdown of the recommended configuration

| block | µm² | share of cells |
|---|---:|---:|
| activation RAM — one 2 kB OpenRAM 6T macro | 284,538 *(macro)* | — |
| special-function unit (PWL exp / rsqrt / recip) | 17,427 | 23 % |
| requantiser (32×16 mult + barrel shift + saturate) | 15,793 | 21 % |
| control FSM + Wishbone B4 slave + CSRs | 14,065 | 19 % |
| **8 × int8 signed multiplier** | **14,033** | **19 %** |
| 8 × 32-bit accumulator | 10,570 | 14 % |
| weight FIFO (2 deep) + broadcast regs | 2,893 | 4 % |
| cells subtotal | 74,781 | 100 % |
| **required core** (cells ÷ 0.55 util + macro × 1.10 halo) | **448,958** | |

**One SRAM macro is 284,538 µm² of the 448,958 µm² core (63 %); the multipliers are
14,033 µm² (3 %).** In sky130 this is a
memory design wearing a compute costume — and that fact, not the MAC array, is what the
spec must be organised around.

Area anchors: sky130A liberty `sky130_fd_sc_hd__tt_025C_1v80.lib` (PDK hash
`8afc8346…`, the blink signoff PDK) gives `dfxtp_2` = 21.2704 µm²; ×26 = 553.03 µm²,
matching `hw/pd/blink/SIGNOFF.md` §5's reported 553 µm² exactly, and blink's 106 mapped
cells / 1242.44 µm² = 11.72 µm²/cell is used for the control-block estimate.

---

## Fit verdicts per area budget

| budget | usable area | verdict |
|---|---:|---|
| **TT 1 tile** (161 × 111.52 µm) | 0.0180 mm² | **NO — nothing fits.** Cheapest swept config is 23.6× over. A bare 4-multiplier array with no requantiser, no SFU and *zero bytes of state* already uses 71 % of the tile. TT's own measured DFF density is ~40 bytes/tile; one stories15M activation vector is 288 bytes. |
| **TT 8 tiles (4×2)** | 0.1436 mm² | **NO for stories15M** (3.0×–13.9× over; the 2 kB activation macro alone is 2.0× the whole budget). **Marginal for stories260K after amputation**: 1×4 array, power-of-two requant, no SFU, 192 B DFF scratch → 129,537 µm² = 7.2 tiles. That is 10 % margin against 8 real tiles but only 0.4 % against a rounded 0.130 mm² — inside the model's own ±30 % error bar. Not established; needs a real LibreLane run. |
| **TT 16 tiles (8×2)**, largest standard group | 0.2873 mm² | **NO** — a *full-featured* 1×4 engine for stories260K is 320,900 µm² = 1.12× over; the recommended stories15M design is 1.6× over. |
| **Free-form 2×2 mm die** | 3.24 mm² core | **FIT with large margin.** Every swept config fits (0.42–2.00 mm²); the recommended 1×8 uses 14 %. **Area stops being the constraint here and pins take over**: feeding a 16×16 vector unit needs 256 B/cycle = 2,048 data pins at 50 MHz. A 2×2 mm die has room for ~100–130 pads at 60 µm pitch, i.e. a 64-bit port. |

Blunt summary: **Tiny Tapeout cannot host an LLM NPU for the acceptance-anchor model.**
Not the 1-tile, not the 8-tile, not the 16-tile option. A TT bring-up vehicle is possible
only for stories260K with the special-function unit deleted. If the project wants silicon
on a TT shuttle, that has to be scoped as a *datapath demonstrator*, not as the NPU.

---

## Rejected alternatives

1. **Output-stationary square systolic array (16×16, 8×8, 4×4).** Rejected: an R×C
   output-stationary array holds an R×C tile of `C[M][N]`; at M = 1 only one of R rows
   holds a valid activation, so utilisation is 1/R by construction — **5.6 % for 16×16**.
   It costs 2.00 mm² (4.5× the recommended design) to deliver 45.3 tok/s against 25.4,
   and only where bandwidth is free. Dominated at every size swept. (`results.md` §3)
2. **A large MAC array (8×8 or 16×16 vector, 64–256 MACs/cycle).** Rejected: with
   arithmetic intensity 1.00 MAC/byte, 256 MACs/cycle needs 12.8 GB/s off-chip — ~2,048
   pins at 50 MHz. On any realistic port every one of those configs collapses to the same
   12.8 / 25.6 tok/s as a 1×4 / 1×8 unit. Second-order penalty: the 106,336-element
   non-GEMM tail per token, harmless at 8 MACs/cycle (0.7 % of the token), becomes up to
   64 % of the token at 256 MACs/cycle unless the vector lane is widened to match.
3. **Keeping weights (or the KV cache) on-chip.** Rejected: 2,234 mm² of sky130 SRAM for
   stories15M, 59 mm² even for stories260K. Not a trade-off; an impossibility.
4. *(Runner-up, recorded for completeness)* **Targeting Tiny Tapeout with stories15M.**
   Rejected: 3.1× over the largest practical tile budget, driven by activation SRAM that
   cannot be removed.

---

## Consequences

- (+) 100 % PE utilisation on every M = 1 shape in stories15M: K ∈ {288, 768, 48, 128}
  and N ∈ {288, 768, 48, 128, 32000} are all 16-divisible, so a 16-wide datapath pads
  nothing. The architecture leaves no utilisation on the table.
- (+) Smallest thing that hits the bandwidth ceiling → cheapest silicon that reaches the
  achievable token rate. 4×4 (16 MACs, +0.03 mm²) is cheap insurance if a wider port
  appears and doubles prefill; anything larger is provably idle.
- (+) A streaming engine has a simple, formally tractable contract (a weight stream + a
  descriptor), which suits the Wishbone B4 bus chosen in ADR 0001.
- (−) **Prefill is slow.** 128-token prefill of stories15M at 8 MACs/cycle takes ~2.0 s
  (a 16×16 output-stationary array would take 0.063 s, 32× faster, because at M ≥ R it
  amplifies C bytes/cycle into R·C MACs/cycle). Accepted: prefill runs once per prompt,
  decode once per token, and TinyStories prompts are short.
- (−) **The system is not self-contained.** It requires an external weight streamer
  (host, MCU or FPGA) and external weight + KV storage. "The chip runs an LLM" is only
  true as "the chip plus its memory subsystem runs an LLM"; the demo and the
  token-by-token PyTorch comparison must be honest about that boundary.
- (−) **Tiny Tapeout silicon is off the table for the acceptance-anchor model.** This
  contradicts the README's "small enough for a Tiny Tapeout tile" framing for SoC-1 and
  should be reconciled explicitly rather than quietly.
- (−) The 15.6 MB/token of external traffic is an energy story nobody has costed yet.

---

## Open questions the spec phase MUST settle

These are defects in this ADR until closed. Per the chief-architect method, the
open-questions section must be empty before any spec reaches `status: frozen`.

**Q1 — Quantisation arithmetic (highest priority; blocks the ISS/RTL bit-exactness
contract).** Per-tensor or per-channel scales? Rounding mode (round-half-to-even vs
round-half-away-from-zero)? Saturating or wrapping accumulation? Symmetric or asymmetric
(zero-point) int8? The spec must define this precisely enough that a verif engineer who
has never seen the RTL can write a bit-exact golden model from the text alone.
*Cost at stake:* the full multiply-shift requantiser is 15,793 µm² against 2,027 µm² for
power-of-two scales — 3.5 TT tiles of difference — and requantisation is 42 % of all
non-GEMM FLOPs (49,856 requantisations/token).

**Q2 — Accumulator width.** 26 bits suffices for K ≤ 2048 with int8 operands; this ADR
assumes 32 for software sanity. The spec must state the width, the overflow behaviour,
and whether it is architecturally visible.

**Q3 — SRAM macro choice.** OpenRAM `sky130_sram_2kbyte_1rw1r_32x512_8` (284,538 µm²,
hard macro, needs LibreLane macro placement + a blackbox flow) vs DFFRAM latch macro
(≈1.4× the area, standard-cell only, simpler flow) vs plain flops (largest, simplest).
This is 63 % of the design's area — it is the single biggest area decision, and it also
determines whether the PD flow needs hard-macro support at all.

**Q4 — Bus and streaming interface.** ADR 0001 fixes Wishbone B4 pipelined for control.
Open: does the weight stream ride the same bus, or a dedicated port? What is the
descriptor/CSR programming model? What is the backpressure and end-of-stream contract?
What happens on an underrun mid-GEMV — stall, or an error status bit?

**Q5 — Special-function unit scope.** Which of exp / rsqrt / reciprocal / SiLU are in
hardware and to what precision? 17,427 µm² (±40 %, the least certain number in the model)
buys you out of a CPU round-trip inside every RMSNorm, softmax and SwiGLU. The accuracy
requirement flows directly from the token-by-token PyTorch match, which is unspecified.

**Q6 — Softmax numerics.** Max-subtraction pass, precision of the exponent and of the
normalising reciprocal. This is the classic source of token divergence against PyTorch
and is currently unanalysed.

**Q7 — KV-cache precision and residency.** int8 is assumed here (KV traffic is 2.8 % of
the token at ctx = 128, so fp16 is affordable if accuracy demands it). Where the cache
lives and who owns its addressing is unspecified.

**Q8 — The `lm_head` special case.** One GEMV, `1×288 @ 288×32000`, is 59 % of the token.
Does the sequencer treat it as an ordinary GEMV descriptor, or does it get a dedicated
path (e.g. streaming argmax/top-k so the 32,000 logits never have to be materialised)?
Note this is an artefact of tiny models with a 32000-token vocabulary; stories260K
(vocab 512) does not have it, so any special case must not become load-bearing.

**Q9 — Acceptance-anchor reconciliation.** Given the TT verdicts above, is the target a
2×2 mm free-form die (no shuttle path today) or a TT stories260K demonstrator (shuttle
path, but not the acceptance model)? This is a scope decision for the human maintainer,
not an architectural one, and it gates everything downstream.

**Q10 — Timing feasibility is ASSUMED, not shown.** This ADR is backed by an *area*
model only. Nothing here demonstrates that an 8-lane int8 multiply + 32-bit accumulate
path closes at 20 ns in sky130. blink's 25-bit counter had +11.4 ns slack at
`ss_100C_1v60` (`SIGNOFF.md` §3), which says nothing about a multiplier tree. No
standalone OpenSTA exists on the host (`SIGNOFF.md` §7 item 3), so this cannot be checked
without a LibreLane run. If the MAC path does not close, the fix is pipelining the
multiply-accumulate — which changes the accumulator/hazard structure the spec has to
describe. **A trial synthesis of a single int8 MAC lane should precede spec freeze.**
