# NPU design-space exploration — sky130A, 50 MHz, int8 decode

Role: chief-architect · Status: data deliverable (feeds ADR 0002; no spec implied) · Date: 2026-07-26

Reproduce every table with:

```bash
.venv/bin/python3 explore/npu-dse/cost_model.py                    # stories15M @ ctx=128
.venv/bin/python3 explore/npu-dse/cost_model.py --model stories260K --requant shift
```

`cost_model.py` imports `workloads/tinystories/profile.py`, so the workload numbers here
and in `workloads/tinystories/profile.md` cannot drift apart.

---

## 1. Technology anchors — where every area number comes from

| anchor | value | source |
|---|---:|---|
| `nand2_1` = 1 GE | 3.7536 µm² | sky130A liberty `sky130_fd_sc_hd__tt_025C_1v80.lib`, PDK hash `8afc8346…` (same as blink signoff) |
| `fa_1` full adder | 20.0192 µm² (5.33 GE) | same liberty |
| `ha_1` half adder | 12.5120 µm² | same liberty |
| `and2_1` | 6.2560 µm² | same liberty |
| `mux2_1` | 11.2608 µm² | same liberty |
| `dfxtp_2` flop | **21.2704 µm²** | same liberty |
| blink DFF area | 26 × 21.2704 = **553.03 µm²** | `hw/pd/blink/SIGNOFF.md` §5 reports **553 µm²** — the liberty and the signed-off synthesis agree exactly |
| blink average cell | **11.72 µm²** | 1242.44 µm² / 106 mapped cells, `SIGNOFF.md` §5 |
| DFFRAM latch macro | 38.46 µm²/bit (26 kbit/mm²) | [AUCOHL/DFFRAM README](https://github.com/AUCOHL/DFFRAM) — "~26,000 bits/mm², vs ~7,000–9,000 for general RTL synthesis" |
| DFFRAM `RAM32` (128 B) | 401 × 136 µm | [Tiny Tapeout memory spec](https://tinytapeout.com/specs/memory/) |
| TT DFF scratch, measured | ~320 DFF per tile = **56.1 µm²/bit placed** | [Tiny Tapeout memory spec](https://tinytapeout.com/specs/memory/) |
| OpenRAM 1 kB 6T macro | `SIZE 479.78 BY 397.50` = 190,713 µm² = **23.28 µm²/bit** | LEF of [`sky130_sram_1kbyte_1rw1r_32x256_8`](https://github.com/VLSIDA/sky130_sram_macros) |
| OpenRAM 2 kB 6T macro | `SIZE 683.10 BY 416.54` = 284,538 µm² = **17.37 µm²/bit** | LEF of [`sky130_sram_2kbyte_1rw1r_32x512_8`](https://github.com/VLSIDA/sky130_sram_macros) |
| Tiny Tapeout 1×1 tile | 161 × 111.52 µm = **17,955 µm²** usable | [Tiny Tapeout specs](https://tinytapeout.com/specs/) / [FAQ](https://tinytapeout.com/faq/) |
| clock target | 50 MHz (20 ns) | `flow/gates.mk` `CLOCK_PERIOD_NS` |

Derived, with the derivation shown in `cost_model.py`:

| block | area | how |
|---|---:|---|
| int8×int8 signed multiplier | **1,754 µm²** (467 GE) | Baugh-Wooley array: 64 `and2_1` + 63 `fa_1` + 9 `ha_1` + 16 `xor2_1` |
| 32-bit accumulator (reg + adder) | 1,321 µm² | 32 `dfxtp_2` + 32 `fa_1` |
| requantiser, `sat8(round((acc·M₃₂)≫s))` | **15,793 µm²** | 32×16 multiplier + 5-stage 32-bit barrel shifter + round/saturate |
| requantiser, power-of-two `sat8(round(acc≫s))` | **2,027 µm²** | barrel shifter + round/saturate only |
| special-function unit (exp, rsqrt, recip) | 17,427 µm² **±40 %** | 3× piecewise-linear (16 segments: 8×8 mult + 16-bit add + coeff ROM) + shared int16 mult |
| control FSM + Wishbone B4 slave + CSRs | 14,065 µm² | 1,200 cells × blink's measured 11.72 µm²/cell |

**Derating.** blink signed off at 10.9 % core utilisation *by construction* (390 cells on
a die sized by PDN strap pitch — `SIGNOFF.md` §3), which is not a planning number. This
model assumes **55 % placement utilisation** for standard cells and a **1.10× halo** for
hard macros. Sanity check: DFF scratch at 26.90 µm²/bit raw ÷ 0.55 = **48.9 µm²/bit
placed**, against Tiny Tapeout's *measured* 56.1 µm²/bit. The model is ~13 % optimistic
against real silicon, which is the right direction of error to know about.

**Honest error bars.** Multiplier and control-block areas are ±30 %; the SFU is ±40 %;
memory macro areas are exact (LEF). None of the conclusions below turn on ±40 %.

---

## 2. The finding that decides everything: weights cannot live on-chip

| model | int8 weights (B) | KV @ max_seq_len (B) | as DFFRAM (mm²) | as OpenRAM 6T (mm²) | × over a 2×2 mm core |
|---|---:|---:|---:|---:|---:|
| stories260K | 260,032 | 163,840 | 130.4 | **58.9** | **18×** |
| stories15M | 15,191,712 | 884,736 | 4,946.6 | **2,233.6** | **689×** |
| stories42M | 41,689,600 | 8,388,608 | 15,408.7 | 6,957.6 | 2,147× |
| stories110M | 109,529,856 | 18,874,368 | 39,509.0 | 17,839.8 | 5,506× |

sky130 stores roughly **57.6 kbit/mm²** in the densest published open macro. stories15M
needs 128 Mbit. That is **2,234 mm²** of SRAM — a 47 × 47 mm die of nothing but memory.
Even stories260K, the toy model, needs **59 mm²**, still 18× a generous 2×2 mm die.

There is no clever packing, no shape of MAC array and no dataflow that changes this.
**Weights and the KV cache are off-chip. Full stop.** On-chip SRAM holds activations —
low single-digit kilobytes — and nothing else.

Three consequences, all of which the ADR has to absorb:

1. The throughput ceiling is set by the **external weight port**, not by MAC count
   (workload profile: arithmetic intensity is 1.00 MAC/byte).
2. "Weight-stationary" is not merely suboptimal at M = 1, it is **meaningless**: each
   weight is consumed exactly once per token, so there is no reuse to hold onto.
3. The design is a **streaming dot-product engine hanging off a memory port**, not a
   self-contained accelerator with a weight buffer.

---

## 3. The sweep — stories15M decode, ctx = 128, 50 MHz

`eff MAC/cyc` = useful MACs per cycle on an M = 1 GEMV.
`core mm²` = cells ÷ 0.55 utilisation + macros × 1.10 halo.
`cyc/tok` includes the non-GEMM tail through a `min(C,8)`-wide vector lane.

| config | PEs | eff MAC/cyc | cells µm² | macros µm² | **core mm²** | cyc/token | PE util | tok/s (compute) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1×4 ws_vector | 4 | 4 | 61,118 | 284,538 | 0.4241 | 3,934,168 | 100.0 % | 12.7 |
| 1×4 os_square | 4 | 4 | 62,309 | 284,538 | 0.4263 | 4,004,408 | 98.2 % | 12.5 |
| **1×8 ws_vector** | **8** | **8** | **74,781** | **284,538** | **0.4490** | **1,967,084** | **100.0 %** | **25.4** |
| 1×8 os_square | 8 | 8 | 77,334 | 284,538 | 0.4536 | 2,030,300 | 96.9 % | 24.6 |
| 4×4 ws_vector | 16 | 16 | 90,686 | 284,538 | 0.4779 | 1,003,480 | 100.0 % | 49.8 |
| 4×4 os_square | 16 | **4** | 103,298 | 284,538 | 0.5008 | 4,046,552 | **24.3 %** | 12.4 |
| 8×8 ws_vector | 64 | 64 | 211,843 | 284,538 | 0.6982 | 257,516 | 100.0 % | 194.2 |
| 8×8 os_square | 64 | **8** | 268,617 | 284,538 | 0.8014 | 2,079,468 | **11.8 %** | 24.0 |
| 16×16 ws_vector | 256 | 256 | 687,739 | 284,538 | 1.5634 | 74,348 | 100.0 % | 672.5 |
| 16×16 os_square | 256 | **16** | 927,169 | 284,538 | 1.9988 | 1,102,572 | **5.6 %** | 45.3 |

Read the utilisation column first. **A 16×16 output-stationary array runs at 5.6 %
utilisation on decode**: it occupies 2.00 mm² of core, 4.5× more than the 1×8 vector
unit, and delivers 45.3 tok/s against the vector unit's 25.4 — i.e. it buys 1.8× the
throughput for 4.5× the area, and only in the fantasy where bandwidth is free. That is
the whole square-versus-vector argument in one row.

The reason is structural, not a modelling artefact: an output-stationary R×C array holds
an R×C tile of the output matrix `C[M][N]`. With **M = 1, only one of the R rows ever
holds a valid activation**; the other R−1 rows are dead silicon for the entire decode.
Utilisation is 1/R by construction — 1/4, 1/8, 1/16 for the shapes swept.

*(One can of course re-map a square array so that its rows become the reduction
dimension rather than the M dimension. That mapping is exactly the `ws_vector` row of
this table, with per-PE accumulators it does not need. It is not a systolic array any
more; it is a vector unit drawn as a square.)*

---

## 4. Memory-bound reality — tokens/s = min(compute, weight delivery)

Columns are off-chip weight bandwidth in bytes/cycle at 50 MHz (1 B/c = 50 MB/s).

| config | tok/s compute | 1 B/c | 2 B/c | 4 B/c | 8 B/c | 16 B/c | 32 B/c |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1×4 ws_vector | 12.7 | 3.2 | 6.4 | **12.7** | 12.7 | 12.7 | 12.7 |
| 1×8 ws_vector | 25.4 | 3.2 | 6.4 | 12.8 | **25.4** | 25.4 | 25.4 |
| 4×4 ws_vector | 49.8 | 3.2 | 6.4 | 12.8 | 25.6 | **49.8** | 49.8 |
| 4×4 os_square | 12.4 | 3.2 | 6.4 | 12.4 | 12.4 | 12.4 | 12.4 |
| 8×8 ws_vector | 194.2 | 3.2 | 6.4 | 12.8 | 25.6 | 51.1 | 102.3 |
| 8×8 os_square | 24.0 | 3.2 | 6.4 | 12.8 | 24.0 | 24.0 | 24.0 |
| 16×16 ws_vector | 672.5 | 3.2 | 6.4 | 12.8 | 25.6 | 51.1 | 102.3 |
| 16×16 os_square | 45.3 | 3.2 | 6.4 | 12.8 | 25.6 | 45.3 | 45.3 |

Every configuration collapses onto the same diagonal. **The design rule is: build
exactly as many int8 MACs as you can feed bytes, and not one more.** A 16×16 vector unit
on a 4 B/cycle port delivers 12.8 tok/s — the same as a 1×4 unit at one thirteenth the
area.

Achievable bandwidth by platform:

| platform | inbound weight bandwidth | source |
|---|---|---|
| Tiny Tapeout | `ui_in[7:0]` + `uio[7:0]` driven inward = 16 bit/cycle = **2 B/c** (100 MB/s), leaving only `uo_out[7:0]` for results | [TT pinouts spec](https://tinytapeout.com/specs/pinouts/): 8 input-only + 8 output-only + 8 bidirectional |
| QSPI PSRAM ×8 DDR @ 50 MHz | **2 B/c** | commodity part class |
| 32-bit external SRAM/PSRAM SDR @ 50 MHz | **4 B/c** (200 MB/s) | ~40 signal pads |
| 64-bit external bus SDR @ 50 MHz | **8 B/c** (400 MB/s) | ~80 signal pads; a 2×2 mm die has room for ~100–130 at 60 µm pitch |

---

## 5. Area-budget verdicts — blunt

**Budgets.** TT 1 tile = 17,955 µm² = 0.0180 mm². TT 8 tiles = 143,638 µm² = 0.1436 mm²
(the task brief's conservative 0.13 mm² changes no verdict). 2×2 mm die = 4 mm²; core
after a 100 µm ring/PDN margin per side = **3.24 mm²**.

### (a) Tiny Tapeout 1 tile (0.0180 mm²) — **NOTHING FITS**

The cheapest config in the sweep needs **23.6×** the tile. Even a bare 1×4 multiplier
array with no requantiser, no SFU and no memory (4 × 1,754 = 7,016 µm² of cells → 12,756
µm² of core) uses 71 % of a tile and can hold **zero bytes of state**. A single tile
cannot store one 288-byte stories15M activation vector — TT's own measured number is
~40 bytes of DFF per tile. Verdict: **no NPU of any kind. Not close.**

### (b) Tiny Tapeout 8 tiles (0.1436 mm²) — **NO FIT for stories15M; marginal for stories260K only after amputation**

Every stories15M configuration is 3.0×–13.9× over budget, and the binding constraint is
**not the MACs** — it is the 2 kB activation macro (284,538 µm², i.e. **2.0× the entire
8-tile budget on its own**).

Switching to stories260K (dim 64, hidden 172) shrinks the working set from 2048 B to
768 B but every config is still 2.2×–13.2× over. What it takes to actually fit:

| variant | requant | SFU | scratch | cells µm² | core µm² | TT tiles | ≤ 8 tiles? |
|---|---|---|---:|---:|---:|---:|:--:|
| full 1×4 ws_vector | mul | yes | 768 B | 226,397 | 411,630 | 22.9 | NO |
| lean 1×4 ws_vector | mul | no | 192 B | 85,011 | 154,565 | 8.6 | NO |
| **bare 1×4 ws_vector** | shift | no | 192 B | 71,245 | 129,537 | **7.2** | **FIT** |
| bare 1×4, 128 B scratch | shift | no | 128 B | 57,472 | 104,495 | 5.8 | FIT |
| bare 1×8, 128 B scratch | shift | no | 128 B | 71,135 | 129,337 | 7.2 | FIT |
| bare 4×4, 128 B scratch | shift | no | 128 B | 87,040 | 158,255 | 8.8 | NO |

A TT-8 NPU is possible, but only as: **stories260K, 4 MACs/cycle, power-of-two
requantisation, no special-function unit** (firmware does every `exp`/`rsqrt` over
Wishbone, i.e. a CPU round-trip inside every RMSNorm, softmax and SwiGLU), **≤192 bytes
of scratch**, and an **off-chip companion streaming the weights**. At TT's 2 B/cycle that
runs stories260K at **331 tok/s** (bandwidth-bound) — the 1×4 array is already
over-provisioned; 1×2 would saturate the same port. Note the control block (14,065 µm²)
and the 192 B of scratch (41,318 µm²) together are 78 % of the cell area: at this scale
the accelerator is mostly sequencer and registers.

Margin warning: the bare 1×4 variant needs 129,537 µm². Against 8 real TT tiles
(143,638 µm²) that is 10 % headroom; against the brief's rounded 0.130 mm² it is **0.4 %
headroom**, i.e. inside the model's own ±30 % error bar. Treat "fits in 8 tiles" as
*plausible pending a real LibreLane run*, not as established.

TT sells tiles in fixed multiples. Against the standard sizes:

| TT size | tiles | usable µm² | bare 1×4 (129,537) | full 1×4 + SFU (320,900) | 1×8 stories15M (448,958) |
|---|---:|---:|:--:|:--:|:--:|
| 1×1 | 1 | 17,955 | NO (7.2×) | NO (17.9×) | NO (25.0×) |
| 2×2 | 4 | 71,819 | NO (1.8×) | NO (4.5×) | NO (6.3×) |
| 4×2 | 8 | 143,638 | **FIT (0.90×)** | NO (2.2×) | NO (3.1×) |
| 8×2 | 16 | 287,276 | FIT | NO (1.12×) | NO (1.6×) |

Even the largest standard TT tile group (8×2 = 16 tiles) **cannot hold a full-featured
1×4 engine** for the 260 K model, and is 1.6× short of the recommended stories15M design.

### (c) Free-form 2×2 mm die, 3.24 mm² core — **EVERYTHING FITS, comfortably**

| config | core mm² | fraction of budget |
|---|---:|---:|
| 1×8 ws_vector | 0.449 | 14 % |
| 4×4 ws_vector | 0.478 | 15 % |
| 8×8 ws_vector | 0.698 | 22 % |
| 16×16 ws_vector | 1.563 | 48 % |
| 16×16 os_square | 1.999 | 62 % |

Area is not the constraint at this budget; **pins are**. 3.24 mm² would host a 16×16
vector unit, but feeding it needs 256 B/cycle = 12.8 GB/s off-chip, which is roughly
2,048 data pins at 50 MHz. The realistic ceiling is a 64-bit port → 8 B/cycle → 8 MACs.

### Where the area actually goes (stories15M, ctx = 128)

| block | 1×8 ws_vector | 4×4 ws_vector | 16×16 os_square |
|---|---:|---:|---:|
| int8 multipliers | 14,033 | 28,067 | 449,071 |
| reduction trees | 0 | 3,924 | 0 |
| accumulators / PE accumulators | 10,570 | 5,285 | 338,244 |
| PE pipeline regs | 0 | 0 | 87,124 |
| activation broadcast regs | 170 | 681 | 0 |
| weight FIFO (2 deep) | 2,723 | 5,445 | 5,445 |
| requantiser | 15,793 | 15,793 | 15,793 |
| special-function unit | 17,427 | 17,427 | 17,427 |
| control + Wishbone + CSR | 14,065 | 14,065 | 14,065 |
| **activation RAM (2 kB OpenRAM macro)** | **284,538** | **284,538** | **284,538** |
| cells subtotal | 74,781 | 90,686 | 927,169 |
| **required core** | **448,958** | **477,877** | **1,998,753** |

For the recommended 1×8 config, **63 % of the area is one 2 kB SRAM macro** and only
3 % is multipliers. In sky130 an NPU is a memory problem wearing a compute costume.

---

## 6. When the square array does pay: prefill

Prefill of 128 tokens, stories15M (arithmetic intensity 52.8 MAC/byte vs ~1 for decode):

| config | PEs | eff MAC/cyc | weight B/cyc needed | MACs per weight byte | prefill (s) | speedup |
|---|---:|---:|---:|---:|---:|---:|
| 1×4 ws_vector | 4 | 4 | 4 | 1 | 4.011 | 1.0× |
| 1×8 ws_vector | 8 | 8 | 8 | 1 | 2.005 | 2.0× |
| 4×4 os_square | 16 | 16 | **4** | **4** | 1.003 | 4.0× |
| 8×8 os_square | 64 | 64 | **8** | **8** | 0.251 | 16.0× |
| 16×16 os_square | 256 | 256 | **16** | **16** | 0.063 | 64.0× |
| 16×16 ws_vector | 256 | 256 | 256 | 1 | 0.063 | 64.0× |

The `MACs per weight byte` column is the real point. At M ≥ R an output-stationary array
turns C bytes/cycle of weight bandwidth into R·C MACs/cycle — a **16× bandwidth
amplification** for a 16×16 array. That is genuinely valuable, and it is exactly what
disappears at M = 1, where the amplification collapses to 1× and R−1 rows go dark.

Prefill runs once per prompt; decode runs once per token. A TinyStories demo prompt is a
handful of tokens. **Size for decode.**

---

## 7. Recommendation

### 7.1 Which shape and dataflow

**A weight-streaming, activation-stationary GEMV vector unit** — the `ws_vector` family.
It reaches 100 % PE utilisation on every M = 1 shape in stories15M (K ∈ {288, 768, 48,
128}, N ∈ {288, 768, 48, 128, 32000}, all 16-divisible), costs no per-PE accumulators,
and matches the workload's 1.00 MAC/byte intensity exactly.

**Reject the output-stationary square array for decode**, at every size swept. It is
strictly dominated: more area, lower utilisation, no throughput advantage once the
weight port binds.

### 7.2 Which size, per budget

| budget | recommended config | on-chip memory | off-chip port | model | expected tok/s |
|---|---|---|---|---|---:|
| TT 1 tile (0.018 mm²) | **none — infeasible** | — | — | — | — |
| TT 4×2 = 8 tiles (0.144 mm²) | 1×4 ws_vector, shift-only requant, **no SFU**, 192 B DFF scratch (7.2 tiles, 10 % margin) | 192 B | 2 B/c | stories260K only | ~331 (bandwidth-bound) |
| TT 8×2 = 16 tiles (0.287 mm²) | 1×4 ws_vector, full requant + SFU, 768 B — **does not fit (1.12×)** | — | — | — | — |
| **2×2 mm die (3.24 mm² core)** | **1×8 ws_vector** (8 int8 MAC/cycle), full requant, SFU, 2 kB OpenRAM | 2 kB | **8 B/c (64-bit)** | **stories15M** | **25.4** |
| 2×2 mm die, 32-bit port | 1×4 ws_vector | 2 kB | 4 B/c | stories15M | 12.8 |

**Headline recommendation: 1×8 weight-streaming GEMV vector unit, 8 int8 MACs/cycle,
0.449 mm² core on a 2×2 mm die, 25.4 tokens/s on stories15M at ctx = 128, 50 MHz.**

Rationale for stopping at 8 MACs: it is the balance point against a realistic 64-bit
external weight port. 4×4 (16 MACs, +0.03 mm²) is cheap insurance if a wider port ever
appears and doubles prefill; anything above that is provably idle silicon.

### 7.3 What this implies for the spec phase

1. The NPU is a **streaming GEMV engine**, not a tiled GEMM accelerator. Its contract is
   with a weight *stream*, not a weight *buffer*.
2. **Requantisation is a first-class datapath decision**, not a detail: the full
   multiply-shift unit is 15,793 µm² against 2,027 µm² for power-of-two scales — 3.5 TT
   tiles of difference, and 42 % of all non-GEMM FLOPs.
3. The **special-function unit is optional but expensive to omit**: 17,427 µm² buys you
   out of a CPU round-trip inside every RMSNorm, softmax and SwiGLU.
4. **Activation SRAM dominates area.** The working-set formula
   `3·dim + hidden_dim + 2·ctx` is worth minimising in the microarchitecture (streaming
   the FFN hidden vector instead of buffering it saves 768 B on stories15M).
5. The `lm_head` GEMV (`1×288 @ 288×32000`) is 59 % of the token. It must be a
   first-class case in the sequencer, not a special case bolted on.
