# SoC-1 Specification

Status: draft
Owner: spec-architect · Implements: milestone M3 (integration), gates milestone M4 (PD)

## §1 Overview

SoC-1 is a single-chip, single-clock-domain system that decodes tokens from a
quantised llama2.c-family checkpoint (primary target: `stories15M`, int8,
dim 288/6 layers/6 heads/vocab 32000 — `workloads/tinystories/profile.md` §1)
and prints them over UART, bit-exact against a PyTorch reference, at a
sustained rate of **≥ 10 tok/s** (conservative acceptance target; the
underlying architecture's modelled headline is 25.4 tok/s —
`explore/npu-dse/results.md` §7.3).

It integrates three decided blocks — the Wishbone B4 pipelined on-chip bus
(ADR-0001), the PicoRV32 `picorv32_wb` control core (ADR-0003), and the 1×8
weight-streaming int8 GEMV NPU (ADR-0002) — plus the system-infrastructure
glue (boot ROM, firmware SRAM, flash/PSRAM controller, UART, interrupt
status block, reset synchronizer) needed to make those three blocks a
running chip. Per `explore/npu-dse/results.md` §2's finding, the 15.2 MB stories15M weight set
does not fit on any sky130 die by three orders of magnitude — SoC-1 is
architecturally a **streaming engine hanging off an external memory port**,
not a self-contained accelerator, and every decision in this spec follows
from that fact.

This spec targets **area scenario (c)** from `explore/npu-dse/results.md` §5 — a free-form
~2×2 mm die, 3.24 mm² usable core after ring/PDN margin. Tiny Tapeout is
explicitly ruled out for the stories15M acceptance anchor
(`explore/npu-dse/results.md` §5(a)/(b) verdicts); this is a **scope decision already made by the issue**, not
re-litigated here, and it resolves ADR-0002's own open question **Q9**.

This is the **top-level integration spec**. It fixes the system memory map,
the block list, the boot flow, the NPU weight-stream datapath, the
interrupt map, and clocking/reset. It does **not** define bit-level register
fields for individual blocks (NPU CSRs, flash-controller CSRs, UART
registers, IRQ status/mask) — those are follow-on per-module specs
(`npu.md`, `flash_ctrl.md`, `uart.md`, `irqc.md`, `boot_rom.md`,
`fw_sram.md`), not yet written, that must reuse the addresses and sizes
fixed here (§3.2) and the SystemRDL/PeakRDL strategy noted in §7.

## §2 Interface

### §2.1 Clock & reset

Single clock domain, 50 MHz (`flow/gates.mk` `CLOCK_PERIOD_NS = 20`), shared
by the CPU, NPU, all bus slaves, and the flash/PSRAM controller's core-side
FSM (see §4.5 for the flash PHY's own clocking, which is a separate,
explicitly-flagged open question).

1. **SOC1-01:** `clk` (in) is the sole system clock. `rst_n` (in) is
   synchronous, active-low, per `/CLAUDE.md`. Every flop in every block
   listed in §3.1 shall reset from `rst_n`.
2. **SOC1-02:** A top-level async input `i_rst_n_pad` (from an external
   reset source, e.g. a Caravel-style harness reset or a POR cell) shall
   pass through a 2-flop synchronizer before becoming the internal `rst_n`
   distributed to §3.1's blocks. This is the only asynchronous-to-synchronous
   boundary in SoC-1's reset tree.
3. **SOC1-03:** `picorv32_wb`'s native reset port is `wb_rst_i`
   (**active-high**, per the upstream module's own port list) — the opposite
   polarity of this project's `rst_n` convention. The CPU wrapper shall drive
   `wb_rst_i = ~rst_n`. This assumes `wb_rst_i` is itself sampled
   synchronously inside the core (true for every published PicoRV32
   configuration used in Caravel-class integrations); flagged for
   confirmation at RTL intake, not re-derived here (**Q-SOC1-06**).

### §2.2 On-chip bus (Wishbone B4 pipelined)

Full signal set per `/CLAUDE.md` and `TEMPLATE.md` §2.2: `wb_cyc, wb_stb,
wb_we, wb_adr[31:0], wb_dat_w[31:0], wb_sel[3:0], wb_stall, wb_ack,
wb_dat_r[31:0], wb_err`. Data bus width is 32 bits throughout SoC-1's
control fabric (see §4.2/§4.3 for why the *weight* datapath is **not** on
this bus).

4. **SOC1-04:** `picorv32_wb` is the SoC's **only** Wishbone bus master.
   Its upstream port list has `wbm_cyc_o, wbm_stb_o, wbm_we_o, wbm_sel_o,
   wbm_adr_o, wbm_dat_o, wbm_dat_i, wbm_ack_i` but **no `wbm_stall_i`** —
   i.e. the core issues classic, one-transaction-at-a-time Wishbone
   requests (assert `cyc`+`stb`, wait for `ack`, deassert) and never
   exploits B4 pipelining. This is fine: control-plane traffic (CSR
   programming, ROM/firmware-SRAM access) is not the bandwidth-critical
   path (§4.2), and a pipeline-*capable* slave interoperates correctly with
   a classic master (a classic master is a degenerate case of pipelined
   operation — one outstanding request at a time).
5. **SOC1-05:** Because there is exactly one bus master, the interconnect
   is a **fixed, arbiter-free address decoder**: `wbm_adr_o[31:20]` shall be
   must-be-zero (else unmapped, SOC1-06) and `wbm_adr_o[19:16]` selects
   one of the sixteen 64 KB regions in §3.2's memory map; the decoder muxes
   `wb_cyc/wb_stb` to the selected slave and muxes that slave's
   `wb_dat_r/wb_ack/wb_err/wb_stall` back to the CPU. No round-robin or
   priority arbitration logic exists in SoC-1 — if a future block needs to
   become a second bus master (none does today), that is a new ADR, per
   ADR-0001's escape-hatch convention.
6. **SOC1-06:** An access to an address whose top 16 bits do not match any
   region in §3.2 shall receive `wb_err = 1` and `wb_ack = 0` within the
   same latency bound as a normal access (§5).

### §2.3 Top-level I/O pads

Architecture-level only — exact pad cells, ESD, and pin assignment are a PD
(backend-engineer) decision, out of scope here. Organisational precedent:
Caravel's harness convention of grouping clock/reset/power pads separately
from a "user area" pad block ([efabless/caravel](https://github.com/efabless/caravel),
cited already in ADR-0003 for its PicoRV32-at-sky130-50MHz precedent).

| Pad group | Signals | Notes |
|---|---|---|
| Clock/reset | `i_clk`, `i_rst_n_pad` | §2.1 |
| Flash/PSRAM PHY | 32-bit parallel data/addr/ctrl pins, ~55–60 pads, 50 MHz SDR — see §4.3 | Ruled per Q-SOC1-01 (resolved); Q-SOC1-02 resolved-moot |
| UART | `o_uart_tx`, `i_uart_rx` | 8N1, divisor TBD in `uart.md` |
| Debug/GPIO | small number, e.g. status LED | minimal; **Q-SOC1-08** |

## §3 Block list & system memory map

### §3.1 Block list

| Block | Tag | Precedent / source | Notes |
|---|---|---|---|
| CPU core, `picorv32_wb` (RV32IMC) | **integrate** | [YosysHQ/picorv32](https://github.com/YosysHQ/picorv32), ADR-0003 D1 | Sole WB master; classic (non-pipelined) handshake (§2.2) |
| NPU — 1×8 weight-streaming GEMV | **build** | ADR-0002 (project-original) | WB slave (CSR/descriptor, §3.2) + dedicated weight-stream input port (§4.2) |
| Boot ROM | **build** | — | WB slave; holds first-stage loader; reset vector target (§4.1) |
| Firmware SRAM | **build** | — | WB slave; RWX; size **Q-SOC1-03** |
| Flash/PSRAM controller | **adapt** | PicoSoC `spimemio`/CSR arrangement, architecture level only ([YosysHQ/picorv32 `picosoc/`](https://github.com/YosysHQ/picorv32)) | WB slave (CSR) + dedicated weight-stream output port (§4.2); **not** used for CPU code fetch (§4.1) — this is a deliberate deviation from the PicoSoC XIP precedent it is otherwise modelled on |
| UART | **adapt** | PicoSoC UART divisor/data-register arrangement, architecture level only | WB slave |
| IRQ status/mask block | **build** | PicoRV32's native 32-line `irq` input (upstream README) | Software-visible pending/mask *mirror*; the core itself does the actual interrupt latching/masking (`maskirq`/`waitirq`/`retirq` custom instructions) — this block is not a PLIC |
| Reset synchronizer | **build** | Caravel-style harness clocking/reset convention, architecture level only | §2.1 |
| Wishbone interconnect (decoder) | **build** | Wishbone B4 spec (ADR-0001) | Arbiter-free — single master (§2.2) |
| GPIO/debug pads | **build** | — | Minimal; PD-stage detail, **Q-SOC1-08** |

### §3.2 System address map

Sixteen 64 KB regions selected by `wb_adr[19:16]` (SOC1-05); each region is
far larger than any block's current register count, leaving headroom for
growth without redesigning the decoder — deliberate, not accidental. The
16 regions span only `0x0000_0000`–`0x000F_FFFF` (1 MB): the decoder shall
treat `wb_adr[31:20]` as must-be-zero (any access with a nonzero bit there
is unmapped, SOC1-06) and shall compare only `wb_adr[19:16]` against the
region index to select among the sixteen 64 KB windows in the table below.

| Region base | Size | Slave | Access | Notes |
|---|---|---|---|---|
| `0x0000_0000` | 64 KB window | Boot ROM | RO | `PROGADDR_RESET = 0x0000_0000` (vanilla PicoRV32 default; PicoSoC overrides this to `0x0010_0000` specifically to reserve low-flash space ahead of *its* XIP user code — a consideration that does not apply to SoC-1, §4.1). Implemented ROM size ≤ window; exact size **Q-SOC1-03**. |
| `0x0001_0000` | 64 KB window | Firmware SRAM | RW (code + data) | Loaded by the boot ROM from flash (§4.1); implemented size TBD, **Q-SOC1-03**. `STACKADDR` (a `picorv32_wb` instantiation parameter) is set to the top of the implemented SRAM once its size is pinned. |
| `0x0002_0000` | 64 KB window | NPU CSR/descriptor block | RW | Control/status/descriptor registers only — weight *data* never crosses this window (§4.2). Field-level layout: future `npu.md`. |
| `0x0003_0000` | 64 KB window | Flash/PSRAM controller CSR | RW | Mode select, clock divider, stream descriptor (base offset + length). Field-level layout: future `flash_ctrl.md`. |
| `0x0004_0000` | 64 KB window | UART | RW | Divisor + data registers, PicoSoC-precedent arrangement. Field-level layout: future `uart.md`. |
| `0x0005_0000` | 64 KB window | IRQ status/mask mirror | RW | See §4.4. Field-level layout: future `irqc.md`. |
| `0x0006_0000` | 64 KB window | GPIO/debug | RW | Minimal; **Q-SOC1-08**. |
| `0x0007_0000` – `0x000F_FFFF` | nine 64 KB windows | reserved | — | Unmapped → `wb_err` (SOC1-06). |

Note on firmware-SRAM area cost (informs **Q-SOC1-03**, not a decision):
ADR-0002's 2 kB OpenRAM macro anchor is 284,538 µm² (`explore/npu-dse/results.md`
§1), i.e. ≈142,000 µm²/KB at that density. Against the 3.24 mm² core budget
with 0.449 mm² (14 %) already spent on the NPU (`explore/npu-dse/results.md` §7.2), a firmware
image in the low tens of KB is affordable but not free — e.g. 8 KB ≈
1.14 mm² (35 % of the whole core budget) at this macro's density. This
must be sized from a real firmware footprint, not guessed.

## §4 Functional behavior

### §4.1 Boot flow: ROM → firmware load → NPU dispatch

7. **SOC1-07:** On reset deassertion, the CPU shall fetch its first
   instruction from `PROGADDR_RESET = 0x0000_0000` (boot ROM, §3.2).
8. **SOC1-08:** The boot ROM's first-stage loader shall (a) program the
   flash/PSRAM controller's clock-divider/mode CSR, (b) issue a
   stream-descriptor read of the firmware image from a fixed flash offset
   into firmware SRAM (`0x0001_0000`, §3.2) via the **same dedicated
   weight-stream datapath** described in §4.2 — there is no separate
   "small CPU-mediated read" path to flash; firmware load reuses the
   NPU-facing streaming mechanism with its destination pointed at SRAM
   instead of the NPU's weight FIFO — and (c) jump to `0x0001_0000` once
   the transfer-complete status (§4.4) is observed.
9. **SOC1-09:** After the jump in SOC1-08, firmware shall execute
   **entirely from firmware SRAM** for the remainder of the session. The
   CPU shall issue no further reads to the flash/PSRAM controller's data
   path (only occasional CSR writes to arm new NPU weight-stream
   descriptors, §4.2). This is the deliberate deviation from PicoSoC's
   XIP-from-flash precedent (§3.1): SoC-1's flash port is the
   tokens/s-critical resource (§4.3), and letting the CPU also fetch
   instructions from it would contend with NPU weight streaming for the
   same physical pins during token generation, which the ADR-0002
   bandwidth analysis (§4.2 below) shows SoC-1 cannot afford.
10. **SOC1-10:** Once running, firmware shall program an NPU
    weight-stream descriptor (flash base offset, length, NPU-side
    destination) per inference step and dispatch the NPU; NPU-dispatch is
    a CSR write, not a data-path operation — the CPU is off the critical
    path for the remainder of that GEMV (ADR-0003's "CPU job is
    orchestration only" framing, §4.2).

### §4.2 NPU weight-stream path — dedicated channel, not the shared bus

This closes ADR-0002's open question **Q4** ("does the weight stream ride
the same bus, or a dedicated port?").

**Decision: a dedicated, point-to-point streaming channel** directly
between the flash/PSRAM controller and the NPU's weight FIFO (also reused
for the boot-time firmware load into SRAM, §4.1) — **not** routed through
Wishbone transactions.

**Why, with numbers.** ADR-0002's own sweep (`explore/npu-dse/results.md`
§4) gives, for the recommended 1×8 `ws_vector` config: 12.8 tok/s at
4 B/cycle, 25.4 tok/s at 8 B/cycle. The issue's acceptance target is
≥ 10 tok/s conservative, i.e. **the design must sustain at least
4 B/cycle** at 50 MHz (200 MB/s) from flash to NPU.

- **Rejected: CPU-mediated, through the WB bus.** `picorv32_wb`'s master
  port is classic/non-pipelined (§2.2 SOC1-04) — a software copy loop
  moving 15.2 MB/token through the CPU's WB port would run many cycles per
  word (load + store, no pipelining) and would also consume ~100% of CPU
  time as a busy-loop, which directly contradicts ADR-0003's framing that
  the CPU's job is orchestration only. Not a bandwidth contender at any
  plausible clock.
- **Rejected: a second WB bus master (DMA engine) driving flash-read +
  NPU-write over the *same* physical WB bus.** Even with pipelining, one
  Wishbone bus can carry one transaction per cycle, and moving one weight
  byte this way costs **two** transactions (a read from the flash slave, a
  write to the NPU slave) — they cannot share a cycle on a single bus. On
  the 32-bit shared bus this halves the achievable rate to ≈2 B/cycle,
  i.e. ≈6.4 tok/s (interpolating ADR-0002's own table) — **below the
  ≥10 tok/s target.**
- **Chosen: a private point-to-point link**, flash-controller output
  directly to NPU weight-FIFO input (and, at boot only, to firmware SRAM's
  write port), sized to carry the controller's full read rate with no
  double-transaction tax. This is the only option that can reach 4 B/cycle
  at all on a 32-bit-class datapath, and is a straight width upgrade (to
  8 B/cycle) if a wider flash/PSRAM part is later justified — reaching
  ADR-0002's 25.4 tok/s headline.

11. **SOC1-11:** The weight-stream channel shall be a ready/valid (or
    equivalent credit-based) handshake into the NPU's 2-deep weight FIFO
    (sized per `explore/npu-dse/results.md` §5's area table) — the flash
    controller shall stall its output when the FIFO is not ready, not
    drop data.
12. **SOC1-12:** A weight-stream transfer is descriptor-based: source
    offset (in external flash/PSRAM address space) and length (bytes),
    programmed into the flash controller's CSR block (§3.2) by firmware
    (or the boot ROM, SOC1-08); the destination (NPU weight FIFO vs.
    firmware SRAM) is a mode bit in the same descriptor.
13. **SOC1-13:** On normal completion (length reached), the controller
    shall set a "stream done" status bit and raise the corresponding
    interrupt (§4.4).
14. **SOC1-14:** On an underrun or flash-read error mid-transfer, the
    controller shall set a distinct "stream error" status bit and raise a
    separate interrupt (§4.4) rather than silently stalling or continuing
    with wrong/stale data. This closes ADR-0002's open question **Q4**'s
    underrun sub-clause with an explicit ruling: **hardware error flag +
    IRQ, not silent recovery.**
15. **SOC1-15:** The `lm_head` GEMV (`1×288 @ 288×32000`, 59 % of a
    token's MACs and weight bytes per `workloads/tinystories/profile.md`
    §2) requires **no dedicated hardware path**: it is issued as an
    ordinary descriptor with a longer length (9,216,000 bytes). This
    closes ADR-0002's open question **Q8** — the descriptor model already
    generalizes to it; no special case is needed in the sequencer. Whether
    the NPU's *output* (32,000 logits) needs on-chip buffering or streams
    out incrementally is **not** settled here — that is a result-path
    design question for the future `npu.md` spec, flagged as
    **Q-SOC1-07**.

### §4.3 Flash/PSRAM controller requirements (the tokens/s-critical block)

**Bandwidth requirement (hard):**

16. **SOC1-16:** The flash/PSRAM controller, together with the external
    part it drives, shall sustain **≥ 4 bytes/cycle** at 50 MHz (≥ 200 MB/s
    / 1.6 Gbit/s) on the weight-stream channel (§4.2) — the floor for the
    ≥ 10 tok/s acceptance target (§1). ≥ 8 B/cycle (400 MB/s) is the
    stretch target that reaches ADR-0002's 25.4 tok/s headline.

**This bandwidth floor is not free, and "flash" as literally named in the
issue needed scrutiny — this was Q-SOC1-01, the single most important open
question in this spec, now resolved by maintainer ruling (see below).**
ADR-0002's own bandwidth table (`explore/npu-dse/results.md` §4) anchors its
4 B/cycle point to a **"32-bit external SRAM/PSRAM SDR @ 50 MHz"** platform
class — not to a literal serial NOR flash part. Its adjacent row, "QSPI
PSRAM ×8 DDR @ 50 MHz", delivers only **2 B/cycle** (100 MB/s) — under the
acceptance floor. Commodity serial Quad-SPI NOR flash parts in this class
typically top out around 100–166 MHz SDR (≈ 400–666 Mbit/s ≈
1.0–1.7 B/cycle-equivalent at our 50 MHz system clock) — also under the
floor unless an Octal-SPI DDR part (8 data lines, DDR, ~100+ MHz) is
specifically sourced, which can reach 3–8 B/cycle but requires the PHY to
run faster than the fixed 50 MHz system clock (§4.5).

**Ruling (Q-SOC1-01, resolved by maintainer-proxy decision under the
full-autonomy directive, revertible):** option (a) — accept a **32-bit-wide
parallel PSRAM (or parallel NOR flash, if sourceable at this width) run at
exactly 50 MHz SDR**, despite the issue's literal "flash" wording. Single
clock domain, no PLL, no DDR, no CDC, and it lands exactly on ADR-0002's
own 4 B/cycle anchor with no extrapolation needed. Pin cost (~55–60 pads
for a 32-bit data/address/control interface) fits comfortably inside the
~100–130 pad budget `explore/npu-dse/results.md` §5 computes for a 2×2 mm
die. This is now the spec's committed external-memory class, not a working
recommendation; **Q-SOC1-02 (serial-DDR PHY clocking) is therefore
resolved-moot** — it applied only to the rejected serial Octal-SPI-DDR
option (b).

17. **SOC1-17:** The controller shall be a Wishbone B4 slave for CSR
    access only (mode select, clock divider, descriptor registers) — CSR
    traffic is occasional/low-bandwidth and rides the shared 32-bit bus
    fine at the CPU's classic (non-pipelined) rate (§2.2).
18. **SOC1-18:** The controller shall drive the weight-stream output
    (§4.2) autonomously once a descriptor is armed, with no further
    per-word CPU or Wishbone involvement.
19. **SOC1-19:** The controller's external-part interface width/mode is
    **ruled** as 32-bit parallel SDR @ 50 MHz (Q-SOC1-01, resolved, above).
    It shall still be a build-time parameter rather than hard-coded into
    the datapath, so a future part swap within the same platform class
    does not require a datapath redesign; RTL intake confirms the exact
    part's electrical availability against this width/mode.

### §4.4 Interrupt map

PicoRV32 has a **native 32-line level interrupt input** (`irq[31:0]`) with
built-in latch/mask/return logic (`maskirq`/`waitirq`/`timer`/`retirq`
custom instructions) — there is no separate PLIC/CLINT in SoC-1. Per the
upstream core, `irq[0]` = timer, `irq[1]` = ebreak/ecall/illegal
instruction, `irq[2]` = bus error (misaligned access) are **reserved by the
core itself**; `irq[3:31]` are free for system use. This resolves
ADR-0003's open question **Q5** for SoC-1: no project-owned CLINT-like
block is needed, only a thin software-visible status/mask **mirror**
(`0x0005_0000`, §3.2) for firmware convenience (readable pending bits) —
the core does the actual latching.

| `irq[n]` | Source | Reserved by |
|---:|---|---|
| 0 | Timer | PicoRV32 core (native) |
| 1 | ebreak/ecall/illegal instruction | PicoRV32 core (native) |
| 2 | Bus error (misaligned access) | PicoRV32 core (native) |
| 3 | UART RX data ready | this spec |
| 4 | Weight-stream transfer done (§4.2 SOC1-13) | this spec |
| 5 | Weight-stream error (§4.2 SOC1-14) | this spec |
| 6 | NPU compute-done (GEMV complete; may lag stream-done, §4.2) | this spec |
| 7–31 | Reserved | — |

20. **SOC1-20:** `irq[6]` (NPU compute-done) shall be distinct from
    `irq[4]` (stream done) — the NPU may still be computing after the last
    weight byte has arrived (its accumulate/requantise tail), so software
    must not treat "stream done" as "result ready."

### §4.5 Clocking & reset architecture

21. **SOC1-21:** All blocks in §3.1 except the flash/PSRAM PHY's external
    signalling run in the single 50 MHz `clk` domain (§2.1) with no
    internal CDC.
22. **SOC1-22:** Per the Q-SOC1-01 ruling (§4.3), the flash/PSRAM PHY runs
    at the same 50 MHz as the rest of the system — no PHY clock domain
    crossing into the weight-stream FIFO (§4.2, SOC1-11) is needed, and no
    on-chip PLL is required. **Q-SOC1-02 is resolved-moot**: it addressed
    the CDC/PLL cost of a serial Octal-SPI-DDR PHY, an option the Q-SOC1-01
    ruling did not select.

### §4.6 System-infrastructure blocks

Summary (each block detailed in its own subsection or an open question
above): reset synchronizer (§2.1, SOC1-02/03), Wishbone decoder (§2.2,
SOC1-05), boot ROM (§4.1), firmware SRAM (§4.1, §3.2), IRQ status mirror
(§4.4). Pad ring: architecture-level note only (§2.3); PD-stage detail is
out of scope for this spec (**Q-SOC1-08**).

## §5 Error conditions

23. **SOC1-23:** Any Wishbone access to an unmapped region (§3.2) shall
    receive `wb_err = 1`, `wb_ack = 0`, within the same cycle-latency
    bound as a normal slave response — no bus hang.
24. **SOC1-24:** Misaligned CPU memory accesses are handled by the
    PicoRV32 core itself (`irq[2]`, §4.4) — SoC-1's interconnect does not
    duplicate this check.
25. **SOC1-25:** Weight-stream underrun/flash-read error is a hardware
    status bit + interrupt (§4.2 SOC1-14), never a silent stall or a
    continuation with stale/wrong data.
26. **SOC1-26:** NPU descriptor-level error handling (e.g. malformed
    dimensions) is out of scope for this top-level spec — deferred to the
    future `npu.md` module spec.

## §6 Verification notes (advisory)

- A system-level cocotb testbench (verif-architect / DV role, M3 exit
  test `make soc-sim`) should boot a real compiled firmware image and
  match a golden UART log, per ADR-0002/0003's shared framing that DV
  writes its own tests from the spec, never from the RTL.
- Corner cases worth a directed test, as a floor not a ceiling: reset
  asserted mid-weight-stream (SOC1-11/14); WB decode boundary accesses at
  each region's top/bottom address (SOC1-06/23); IRQ nesting/priority via
  PicoRV32's native `maskirq`/`waitirq` (§4.4); boot-ROM-to-firmware-SRAM
  copy bit-exactness (SOC1-08); `lm_head`'s long descriptor (SOC1-15) vs.
  short transformer-body descriptors exercising the same datapath at very
  different lengths.
- Q-SOC1-02 is resolved-moot (§4.3/§4.5, ruled 50 MHz single-clock-domain
  PHY): no multi-clock-domain flash PHY exists in this spec, so no CDC
  FIFO formal proof is needed for that boundary.

## §7 Open questions

Per the chief-architect method, this section must be empty before status
moves past `draft`. None of the items below are guesses dressed up as
decisions — each is a judgment call this spec deliberately did not make
silently.

**Q-SOC1-01 — RESOLVED** (maintainer-proxy ruling under the full-autonomy
directive, revertible). Does "external flash" (issue's literal wording)
mean actual non-volatile serial NOR/Octal-SPI flash, or does the
≥ 10 tok/s target implicitly require the wider parallel PSRAM-class part
ADR-0002's own 4 B/cycle bandwidth anchor is based on? **Ruling: option
(a)** — accept 32-bit parallel PSRAM/flash SDR @ 50 MHz despite the
literal "flash" wording (single clock domain, exactly matches ADR-0002's
anchor, no PLL). This is now a spec decision, not a working assumption —
see §4.3.

**Q-SOC1-02 — RESOLVED-MOOT** (consequence of Q-SOC1-01's ruling). Would
have covered PHY clocking/CDC cost for a serial DDR flash part; that
option (b) was not selected, so no PHY clock domain beyond the single
50 MHz system clock exists in this spec (§4.5).

**Q-SOC1-03.** Boot ROM and firmware SRAM sizes are placeholders (§3.2).
Firmware SRAM area is non-trivial (≈142,000 µm²/KB at ADR-0002's OpenRAM
density) against the 3.24 mm² core budget — needs a real firmware
footprint estimate from the sw-engineer role before pinning down.

**Q-SOC1-04 (register strategy — explicitly deferred per the issue).**
SystemRDL/PeakRDL is the intended register source-of-truth going forward
(precedent: the caliptra-rtl project's RDL-driven register workflow). No
tooling is implemented in this spec. Field-level CSR layouts for the NPU,
flash controller, UART, and IRQ status blocks belong in their own future
per-module specs, which should adopt this tooling once it lands. Process
decision for the human maintainer, not an architectural one.

**Q-SOC1-05 — RESOLVED** (maintainer-proxy ruling under the full-autonomy
directive, revertible; inherited from ADR-0003's Q1). PicoRV32's ISC
license needed an explicit human IP-policy sign-off (issue #1 named
Apache-2.0/BSD/MIT explicitly; ISC is functionally equivalent but was not
on that list). **Ruling: ISC accepted into the project license set.** RTL
intake of the actual picorv32 source is unblocked by this spec's
traceability chain; Q-SOC1-06 (reset polarity/synchronicity confirmation
at RTL intake) remains open independently.

**Q-SOC1-06.** SOC1-03's `wb_rst_i = ~rst_n` inversion and the assumption
that `picorv32_wb`'s reset is synchronous are based on the upstream port
name and README only, not a read of the RTL (clean-room boundary — this
spec is architecture-level, per the issue's own instruction that
implementation code goes through IP intake later). Confirm at RTL intake.

**Q-SOC1-07 (inherited from ADR-0002 Q8).** Does the NPU need on-chip
buffering or streaming-argmax support for the 32,000-wide `lm_head`
output, or does firmware consume results incrementally over Wishbone?
Affects the NPU's result-path design and possibly its CSR window's
sufficiency (§3.2 reserves only a small window, valid only if results
stream rather than buffer in bulk). Deferred to the future `npu.md` spec.

**Q-SOC1-08.** Pad ring detail (exact pin count, pinout assignment,
ESD/pad-cell selection) is noted only at the architecture level (§2.3),
citing Caravel's organisational convention. PD-stage (backend-engineer)
decision, out of scope here.

**Q-SOC1-09 (process, low priority).** `docs/ROADMAP.md`'s M3 description
("Wishbone interconnect + SRAM + boot ROM + UART + GPIO + timer
integration") predates ADR-0002/0003 and does not mention the NPU or the
flash/PSRAM weight-stream path this spec is built around. Docs-hygiene
item, not a blocker — flagged so the roadmap and this spec don't visibly
disagree.
