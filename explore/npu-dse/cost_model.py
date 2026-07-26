#!/usr/bin/env python3
"""sky130 analytical cost model for the OpenChip NPU design-space exploration.

Every area constant is either (a) read out of the sky130A liberty shipped with
this repo's PDK cache, (b) measured from a published OpenRAM macro LEF, or
(c) calibrated against the P0 blink signoff (hw/pd/blink/SIGNOFF.md).  Nothing
is a vibe.  Sources are listed in explore/npu-dse/results.md section 1.

Workload numbers are imported from workloads/tinystories/profile.py so the two
deliverables can never drift apart.

Run:
    .venv/bin/python3 explore/npu-dse/cost_model.py
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "workloads" / "tinystories"))
import profile as wl  # noqa: E402  (workloads/tinystories/profile.py)

# ===========================================================================
# 1. Technology constants
# ===========================================================================
# --- sky130_fd_sc_hd cell areas, um^2 ---------------------------------------
# Read from
#   ~/.ciel/ciel/sky130/versions/8afc8346a57fe1ab7934ba5a6056ea8b43078e71/
#     sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
# (same PDK hash as the blink signoff, SIGNOFF.md section 1).
A_NAND2 = 3.7536  # nand2_1 -- our gate-equivalent (GE) unit
A_AND2 = 6.2560  # and2_1
A_INV = 3.7536  # inv_1
A_XOR2 = 8.7584  # xor2_1
A_MUX2 = 11.2608  # mux2_1
A_FA = 20.0192  # fa_1   (full adder)
A_HA = 12.5120  # ha_1   (half adder)
A_DFF = 21.2704  # dfxtp_2 -- 26 of these = 553.03 um^2, exactly the blink number
A_LATCH = 15.0144  # dlxtp_1

# --- blink calibration (hw/pd/blink/SIGNOFF.md section 5) -------------------
BLINK_CELLS = 106
BLINK_CELL_AREA = 1242.44  # um^2 mapped, sky130_fd_sc_hd
BLINK_DFF = 26
BLINK_DFF_AREA = BLINK_DFF * A_DFF  # 553.03 um^2 -- matches SIGNOFF "553 um^2"
A_PER_CELL_AVG = BLINK_CELL_AREA / BLINK_CELLS  # 11.72 um^2/cell

# --- placement derating ------------------------------------------------------
# blink signed off at 10.9% utilisation *by construction* (390 cells on a die
# sized by PDN strap pitch).  That is not a usable planning number.  We assume a
# routable dense sky130 block at 55%, which is what LibreLane/TT designs land on
# with 5 routing layers; macros get a 10% halo/channel allowance.
UTIL = 0.55
MACRO_HALO = 1.10

# --- storage densities, um^2 per bit ---------------------------------------
# DFF scratch: flop + write-enable mux + read mux, before placement derating.
DFF_BIT_RAW = A_DFF + 0.5 * A_MUX2  # 26.90 um^2/bit
# cross-check: 26.90/UTIL = 48.9 um^2/bit placed, vs Tiny Tapeout's measured
# "~320 DFFs (40 bytes) per 17,955 um^2 tile" = 56.1 um^2/bit.  Same ballpark.
DFFRAM_BIT = 1e6 / 26_000  # 38.46 um^2/bit -- DFFRAM latch-based, 26 kbit/mm^2

# OpenRAM sky130 6T macros -- SIZE read from the published LEF files.
OPENRAM_MACROS = {
    # bits: (name, width_um, height_um)
    8 * 1024: ("sky130_sram_1kbyte_1rw1r_32x256_8", 479.78, 397.50),
    16 * 1024: ("sky130_sram_2kbyte_1rw1r_32x512_8", 683.10, 416.54),
}
OPENRAM_1KB_AREA = 479.78 * 397.50  # 190,712 um^2 -> 23.28 um^2/bit
OPENRAM_2KB_AREA = 683.10 * 416.54  # 284,538 um^2 -> 17.37 um^2/bit

CLOCK_MHZ = 50.0  # flow/gates.mk CLOCK_PERIOD_NS = 20

# --- area budgets, um^2 ------------------------------------------------------
TT_TILE = 161.0 * 111.52  # 17,955 um^2 usable, Tiny Tapeout sky130 1x1 tile
BUDGETS = {
    "TT 1 tile": TT_TILE,
    "TT 8 tiles": 8 * TT_TILE,
    "2x2 mm die (core)": 1800.0 * 1800.0,  # 4 mm^2 die minus a 100 um ring/PDN margin
}
# Tiny Tapeout user I/O is ui[7:0] + uo[7:0] + uio[7:0]; at most 16 bits/cycle
# can be pulled inbound, i.e. 2 bytes/cycle at 50 MHz = 100 MB/s.
BUDGET_OFFCHIP_BPC = {"TT 1 tile": 2, "TT 8 tiles": 2, "2x2 mm die (core)": 8}


# ===========================================================================
# 2. Datapath area builders
# ===========================================================================
def mult_area(a_bits: int = 8, b_bits: int = 8) -> float:
    """Signed array multiplier (Baugh-Wooley), built from real sky130 cells.

    partial products : a*b AND2
    reduction        : (b-2)*a full adders + a half adders   (carry-save array)
    final CPA        : (a-1) FA + 1 HA
    sign correction  : ~2*max(a,b) inverters/XORs
    """
    n_and = a_bits * b_bits
    n_fa = max(b_bits - 2, 0) * a_bits + (a_bits - 1)
    n_ha = a_bits + 1
    n_sign = 2 * max(a_bits, b_bits)
    return n_and * A_AND2 + n_fa * A_FA + n_ha * A_HA + n_sign * A_XOR2


def adder_area(width: int) -> float:
    return width * A_FA


def reg_area(width: int) -> float:
    return width * A_DFF


def adder_tree_area(n_inputs: int, in_width: int) -> float:
    """Balanced tree summing n_inputs values of in_width bits."""
    area, n, w = 0.0, n_inputs, in_width
    while n > 1:
        pairs = n // 2
        area += pairs * adder_area(w)
        area += (n % 2) * 0  # odd operand just bypasses
        n = pairs + (n % 2)
        w += 1
    return area


def barrel_shifter_area(width: int, stages: int) -> float:
    return stages * width * A_MUX2


def requant_area(mode: str = "mul_shift") -> float:
    """int32 accumulator -> int8 output.

    'mul_shift' : y = sat8(round((acc * M32) >> s))   -- arbitrary rational scale
    'shift'     : y = sat8(round(acc >> s))           -- power-of-two scale only
    Shared, one instance per array (outputs arrive far slower than 1/cycle).
    """
    shifter = barrel_shifter_area(32, 5)
    round_sat = 60 * A_NAND2
    if mode == "shift":
        return shifter + round_sat
    return mult_area(32, 16) + shifter + round_sat


# Special-function unit: piecewise-linear exp, rsqrt and reciprocal (16 segments
# each: an 8x8 slope multiply + 16-bit add + a small coefficient ROM), plus the
# int16 multiply that SwiGLU and softmax normalisation need.  +/-40% honest error
# bar; this block is an estimate, not a measurement.
SFU_AREA = 3 * (mult_area(8, 8) + adder_area(16) + 24 * 16 * A_NAND2) + mult_area(16, 16)

# Control FSM + Wishbone B4 slave + descriptor/CSR file.  blink was 106 cells for
# a 25-bit counter; a GEMV sequencer with loop counters, address generators and a
# CSR block is ~1200 cells at blink's measured 11.72 um^2/cell.
CTRL_CELLS = 1200
CTRL_AREA = CTRL_CELLS * A_PER_CELL_AVG

ACC_WIDTH = 32  # int8*int8 products accumulated over K<=2048 needs 26b; 32b for SW sanity


# ===========================================================================
# 3. Memory sizing
# ===========================================================================
@dataclass
class Memory:
    name: str
    bits: int
    tech: str
    area: float
    bytes_per_cycle: float
    hard_macro: bool


def size_activation_ram(cfg: wl.ModelConfig, ctx: int) -> int:
    """Bytes of on-chip scratch a streaming decode engine cannot avoid.

    Live at once: residual x, normalised x, q (RoPE'd), the FFN hidden vector
    h = silu(w1 x) * (w3 x), and one head's attention scores at int16.
    K/V stream straight out to the cache; accumulators live in the array.
    """
    b = 3 * cfg.dim + cfg.hidden_dim + 2 * ctx
    return int(math.ceil(b / 256.0) * 256)


def _openram_option(name: str, nbytes: int) -> Memory:
    """OpenRAM 6T macros, quantised to the published 1 kB / 2 kB parts."""
    n2k = nbytes // 2048
    rem = nbytes - n2k * 2048
    n1k = 1 if rem else 0
    area = n2k * OPENRAM_2KB_AREA + n1k * OPENRAM_1KB_AREA
    ports = max(1, n2k + n1k)
    return Memory(name, nbytes * 8, f"OpenRAM 6T {n2k}x2kB+{n1k}x1kB", area, 4.0 * ports, True)


def choose_memory(name: str, nbytes: int, prefer: str = "auto") -> Memory:
    """Pick the storage technology with the smallest *core-area contribution*.

    Std cells are derated by the placement utilisation; hard macros are not
    (they are already placed density) but pay a halo.  Below ~600 bytes flops
    win; above that the 6T macro wins despite its fixed overhead.
    """
    bits = nbytes * 8
    options = {
        "dff": Memory(name, bits, "DFF scratch", bits * DFF_BIT_RAW, 4.0, False),
        "dffram": Memory(name, bits, "DFFRAM latch", bits * DFFRAM_BIT, 4.0, True),
        "openram": _openram_option(name, nbytes),
    }
    if prefer != "auto":
        return options[prefer]
    cost = lambda m: (m.area * MACRO_HALO) if m.hard_macro else (m.area / UTIL)
    return min(options.values(), key=cost)


# ===========================================================================
# 4. Configurations
# ===========================================================================
@dataclass
class Config:
    label: str
    r: int  # reduction depth (vector) / array rows (square)
    c: int  # output lanes (vector)  / array cols (square)
    dataflow: str  # "ws_vector" | "os_square"

    @property
    def pes(self) -> int:
        return self.r * self.c

    @property
    def peak_macs_per_cycle(self) -> int:
        return self.pes

    @property
    def eff_macs_per_cycle_gemv(self) -> int:
        """Useful MACs/cycle on an M=1 GEMV.

        ws_vector : all R*C PEs work (R-deep dot product x C output lanes).
        os_square : an output-stationary array holds an RxC tile of C[M][N];
                    with M=1 only one row of PEs has valid activations, so R-1
                    rows of the array are dead.  Useful rate is C.
        """
        return self.pes if self.dataflow == "ws_vector" else self.c

    @property
    def weight_bytes_per_cycle(self) -> int:
        """int8 weight operands the array can consume per cycle."""
        return self.pes if self.dataflow == "ws_vector" else self.c


SHAPES = [(1, 4), (1, 8), (4, 4), (8, 8), (16, 16)]
DATAFLOWS = ["ws_vector", "os_square"]


def build_configs() -> list[Config]:
    cfgs = []
    for r, c in SHAPES:
        for df in DATAFLOWS:
            cfgs.append(Config(f"{r}x{c} {df}", r, c, df))
    return cfgs


# ===========================================================================
# 5. Area model
# ===========================================================================
@dataclass
class AreaBreakdown:
    items: dict = field(default_factory=dict)
    macros: dict = field(default_factory=dict)

    @property
    def cell_area(self) -> float:
        return sum(self.items.values())

    @property
    def macro_area(self) -> float:
        return sum(self.macros.values())

    @property
    def required_core(self) -> float:
        return self.cell_area / UTIL + self.macro_area * MACRO_HALO


def area_of(cfg: Config, model: wl.ModelConfig, ctx: int, requant_mode: str = "mul_shift") -> AreaBreakdown:
    ab = AreaBreakdown()
    ab.items["int8 multipliers"] = cfg.pes * mult_area(8, 8)

    if cfg.dataflow == "ws_vector":
        # C lanes, each an R-input adder tree feeding one 32-bit accumulator.
        ab.items["reduction trees"] = cfg.c * adder_tree_area(cfg.r, 16)
        ab.items["accumulators"] = cfg.c * (reg_area(ACC_WIDTH) + adder_area(ACC_WIDTH))
        ab.items["activation broadcast regs"] = reg_area(8 * cfg.r)
    else:
        # Output-stationary systolic: every PE owns an accumulator and the
        # pipeline registers that push activations right and partial sums down.
        ab.items["PE accumulators"] = cfg.pes * (reg_area(ACC_WIDTH) + adder_area(ACC_WIDTH))
        ab.items["PE pipeline regs"] = cfg.pes * reg_area(8 + 8)

    ab.items["weight FIFO (2 deep)"] = reg_area(2 * 8 * cfg.weight_bytes_per_cycle)
    ab.items["requantiser"] = requant_area(requant_mode)
    ab.items["special-function unit"] = SFU_AREA
    ab.items["control + Wishbone + CSR"] = CTRL_AREA

    act_bytes = size_activation_ram(model, ctx)
    mem = choose_memory("activation RAM", act_bytes)
    if mem.hard_macro:
        ab.macros[f"{mem.name} ({act_bytes} B, {mem.tech})"] = mem.area
    else:
        ab.items[f"{mem.name} ({act_bytes} B, {mem.tech})"] = mem.area
    return ab


# ===========================================================================
# 6. Performance model
# ===========================================================================
def gemv_cycles(cfg: Config, k: int, n: int) -> tuple[int, int]:
    """(cycles, PE-slots consumed) for one M=1 GEMV of shape (1xK)@(KxN)."""
    if k == 0 or n == 0:
        return 0, 0
    if cfg.dataflow == "ws_vector":
        cyc = math.ceil(k / cfg.r) * math.ceil(n / cfg.c)
    else:
        # output-stationary: one N-tile at a time, K cycles of streaming, plus
        # the systolic fill/drain of R+C.
        cyc = math.ceil(n / cfg.c) * (k + cfg.r + cfg.c)
    return cyc, cyc * cfg.pes


def decode_cycles(cfg: Config, model: wl.ModelConfig, ctx: int) -> dict:
    s = wl.summarise(model, ctx)
    gemv_cyc, slots, useful = 0, 0, 0
    for op in s["ops"]:
        if op.macs == 0:
            continue
        c, sl = gemv_cycles(cfg, op.k, op.n)
        gemv_cyc += c * op.count
        slots += sl * op.count
        useful += op.macs

    # Non-GEMM tail: elementwise / transcendental work through a narrow vector
    # lane (min(C,8) elements per cycle).  Amdahl's law lives here.
    vec_lanes = min(cfg.c, 8)
    vec_elems = sum(v.n_elems * v.count for v in s["vecs"])
    vec_cyc = math.ceil(vec_elems / vec_lanes)

    total_cyc = gemv_cyc + vec_cyc
    return {
        "gemv_cycles": gemv_cyc,
        "vec_cycles": vec_cyc,
        "compute_cycles": total_cyc,
        "pe_utilisation": useful / slots if slots else 0.0,
        "useful_macs": useful,
        "bytes": s["total_bytes"],
    }


def memory_cycles(model: wl.ModelConfig, ctx: int, bytes_per_cycle: float) -> float:
    s = wl.summarise(model, ctx)
    return s["total_bytes"] / bytes_per_cycle


# ===========================================================================
# 7. Reporting
# ===========================================================================
def _u(x: float) -> str:
    return f"{x:,.0f}"


def _mm2(x: float) -> str:
    return f"{x/1e6:.4f}"


def print_tech_table() -> None:
    print("=" * 118)
    print("TABLE A -- technology anchors (sky130A, sky130_fd_sc_hd; see results.md section 1 for sources)")
    print("=" * 118)
    rows = [
        ("nand2_1 (1 GE)", f"{A_NAND2:.4f} um^2", "sky130A liberty tt_025C_1v80"),
        ("fa_1 full adder", f"{A_FA:.4f} um^2", f"{A_FA/A_NAND2:.2f} GE"),
        ("dfxtp_2 flop", f"{A_DFF:.4f} um^2", f"{A_DFF/A_NAND2:.2f} GE; 26x = {BLINK_DFF_AREA:.2f} = blink's 553"),
        ("blink avg cell", f"{A_PER_CELL_AVG:.2f} um^2", "1242.44 um^2 / 106 cells (SIGNOFF section 5)"),
        ("int8 signed multiplier", f"{mult_area(8,8):,.0f} um^2", f"{mult_area(8,8)/A_NAND2:.0f} GE, built from cells above"),
        ("DFF scratch", f"{DFF_BIT_RAW:.2f} um^2/bit", f"{DFF_BIT_RAW/UTIL:.1f} placed vs TT-measured 56.1"),
        ("DFFRAM latch macro", f"{DFFRAM_BIT:.2f} um^2/bit", "26 kbit/mm^2, AUCOHL DFFRAM README"),
        ("OpenRAM 1 kB 6T macro", f"{OPENRAM_1KB_AREA/8192:.2f} um^2/bit", f"LEF SIZE 479.78 x 397.50 = {OPENRAM_1KB_AREA:,.0f} um^2"),
        ("OpenRAM 2 kB 6T macro", f"{OPENRAM_2KB_AREA/16384:.2f} um^2/bit", f"LEF SIZE 683.10 x 416.54 = {OPENRAM_2KB_AREA:,.0f} um^2"),
        ("requantiser (mul+shift)", f"{requant_area('mul_shift'):,.0f} um^2", "32x16 mult + barrel shift + saturate"),
        ("requantiser (shift only)", f"{requant_area('shift'):,.0f} um^2", "power-of-two scales only"),
        ("special-function unit", f"{SFU_AREA:,.0f} um^2", "PWL exp/rsqrt/recip + int16 mult (+/-40%)"),
        ("control + Wishbone", f"{CTRL_AREA:,.0f} um^2", f"{CTRL_CELLS} cells x blink 11.72 um^2/cell"),
        ("placement utilisation", f"{UTIL:.0%}", "assumed; blink's 10.9% was by construction"),
        ("TT 1x1 tile", f"{TT_TILE:,.0f} um^2", "161 x 111.52 um usable"),
    ]
    for a, b, c in rows:
        print(f"  {a:<26}{b:>22}   {c}")
    print()


def print_memory_reality(model: wl.ModelConfig) -> None:
    print("=" * 118)
    print("TABLE B -- can the weights live on-chip in sky130?  (the question that decides the architecture)")
    print("=" * 118)
    print(f"{'model':<13}{'int8 weights':>14}{'KV @ max seq':>14}{'DFFRAM mm^2':>14}{'OpenRAM mm^2':>14}{'x over 2x2mm core':>20}")
    print("-" * 118)
    core = BUDGETS["2x2 mm die (core)"]
    for m in wl.MODELS:
        wb = m.n_params  # int8: 1 byte/param
        kv = 2 * m.kv_dim * m.max_seq_len * m.n_layers
        bits = (wb + kv) * 8
        a_dffram = bits * DFFRAM_BIT
        a_openram = bits * (OPENRAM_2KB_AREA / 16384)
        print(
            f"{m.name:<13}{_u(wb):>14}{_u(kv):>14}{a_dffram/1e6:>14.1f}{a_openram/1e6:>14.1f}"
            f"{a_openram/core:>19.0f}x"
        )
    print("-" * 118)
    print("Not one of them fits, not even stories260K, and not by one or two orders of magnitude.")
    print("Conclusion: weights and KV cache are OFF-CHIP.  On-chip SRAM holds activations only, and the")
    print("NPU's throughput ceiling is set by the external weight port, not by the MAC count.")
    print()


def print_sweep(model: wl.ModelConfig, ctx: int, requant_mode: str) -> list[dict]:
    print("=" * 118)
    print(f"TABLE C -- DSE sweep: {model.name} decode, ctx={ctx}, {CLOCK_MHZ:g} MHz, int8")
    print("=" * 118)
    print(
        f"{'config':<22}{'PEs':>5}{'eff MAC/cyc':>12}{'cell um^2':>11}{'macro um^2':>11}"
        f"{'core mm^2':>10}{'cyc/tok':>12}{'PE util':>9}{'tok/s cmp':>10}"
    )
    print("-" * 118)
    rows = []
    for cfg in build_configs():
        ab = area_of(cfg, model, ctx, requant_mode)
        perf = decode_cycles(cfg, model, ctx)
        tps = CLOCK_MHZ * 1e6 / perf["compute_cycles"]
        rows.append({"cfg": cfg, "area": ab, "perf": perf, "tps_compute": tps})
        print(
            f"{cfg.label:<22}{cfg.pes:>5}{cfg.eff_macs_per_cycle_gemv:>12}"
            f"{ab.cell_area:>11,.0f}{ab.macro_area:>11,.0f}{ab.required_core/1e6:>10.4f}"
            f"{perf['compute_cycles']:>12,}{100*perf['pe_utilisation']:>8.1f}%{tps:>10.1f}"
        )
    print("-" * 118)
    print("eff MAC/cyc = useful MACs per cycle on an M=1 GEMV.  For the output-stationary square array")
    print("that is C, not R*C: with M=1 only one row of the array holds valid activations.")
    print("core mm^2 = cells/55% utilisation + macros x 1.10 halo.  cyc/tok includes the non-GEMM tail.")
    print("NOTE on the name 'ws_vector': at M=1 every weight is consumed exactly once per token, so there")
    print("is no weight reuse for a weight-stationary dataflow to capture.  What the label denotes here is")
    print("the only dataflow that makes sense for decode: weights STREAM through, the activation vector is")
    print("stationary/broadcast, and the C output accumulators stay put.  See results.md section 4.")
    print()
    return rows


def print_memory_bound(model: wl.ModelConfig, ctx: int, rows: list[dict]) -> None:
    print("=" * 118)
    print(f"TABLE D -- memory-bound reality: {model.name}, ctx={ctx}.  tok/s = min(compute, weight delivery)")
    print("=" * 118)
    bws = [1, 2, 4, 8, 16, 32]
    hdr = f"{'config':<22}{'tok/s cmp':>10}" + "".join(f"{b:>8}B/c" for b in bws)
    print(hdr)
    print("-" * 118)
    for r in rows:
        line = f"{r['cfg'].label:<22}{r['tps_compute']:>10.1f}"
        for b in bws:
            mc = memory_cycles(model, ctx, b)
            tps = CLOCK_MHZ * 1e6 / max(r["perf"]["compute_cycles"], mc)
            line += f"{tps:>11.1f}"
        print(line)
    print("-" * 118)
    print("Columns are off-chip weight bandwidth in bytes/cycle at 50 MHz (1 B/c = 50 MB/s).")
    print("Tiny Tapeout can source 2 B/c at best (ui[7:0]+uio[7:0]); a 64-pin external bus gives 8 B/c.")
    print("Every config saturates at the same number once bandwidth binds -- that is the design rule.")
    print()


def print_budget_fit(model: wl.ModelConfig, ctx: int, rows: list[dict]) -> None:
    print("=" * 118)
    print(f"TABLE E -- area-budget fit ({model.name} activation working set, ctx={ctx})")
    print("=" * 118)
    names = list(BUDGETS)
    print(f"{'config':<22}{'core mm^2':>11}" + "".join(f"{n:>22}" for n in names))
    print("-" * 118)
    for r in rows:
        need = r["area"].required_core
        line = f"{r['cfg'].label:<22}{need/1e6:>11.4f}"
        for n in names:
            b = BUDGETS[n]
            line += f"{('FIT ' if need <= b else 'NO  ') + f'({need/b:.1f}x)':>22}"
        print(line)
    print("-" * 118)
    for n, b in BUDGETS.items():
        print(f"  {n:<20} = {b:>12,.0f} um^2 = {b/1e6:.4f} mm^2   (off-chip weight port: {BUDGET_OFFCHIP_BPC[n]} B/cycle)")
    print("  (x) = required core area / budget.  Anything > 1.0x does not fit.")
    print()


def print_where_the_area_goes(model: wl.ModelConfig, ctx: int, requant_mode: str) -> None:
    print("=" * 118)
    print(f"TABLE F -- area breakdown, {model.name} ctx={ctx}: three representative configs")
    print("=" * 118)
    picks = [Config("1x8 ws_vector", 1, 8, "ws_vector"),
             Config("4x4 ws_vector", 4, 4, "ws_vector"),
             Config("16x16 os_square", 16, 16, "os_square")]
    abs_ = [area_of(p, model, ctx, requant_mode) for p in picks]
    keys = []
    for ab in abs_:
        for k in list(ab.items) + list(ab.macros):
            if k not in keys:
                keys.append(k)
    print(f"{'block':<44}" + "".join(f"{p.label:>24}" for p in picks))
    print("-" * 118)
    for k in keys:
        line = f"{k:<44}"
        for ab in abs_:
            v = ab.items.get(k, ab.macros.get(k, 0.0))
            line += f"{v:>24,.0f}"
        print(line)
    print("-" * 118)
    print(f"{'cells subtotal':<44}" + "".join(f"{ab.cell_area:>24,.0f}" for ab in abs_))
    print(f"{'macros subtotal':<44}" + "".join(f"{ab.macro_area:>24,.0f}" for ab in abs_))
    print(f"{'REQUIRED CORE (um^2)':<44}" + "".join(f"{ab.required_core:>24,.0f}" for ab in abs_))
    print()


def print_small_model_option(ctx: int, requant_mode: str) -> None:
    m = wl.MODELS_BY_NAME["stories260K"]
    print("=" * 118)
    print(f"TABLE G -- stories260K fallback (dim=64): does the small model rescue the small budgets? ctx={ctx}")
    print("=" * 118)
    print(f"{'config':<22}{'act RAM B':>11}{'core mm^2':>11}{'cyc/tok':>11}{'tok/s cmp':>11}{'tok/s @2B/c':>13}{'TT8 fit':>10}")
    print("-" * 118)
    for cfg in build_configs():
        ab = area_of(cfg, m, ctx, requant_mode)
        perf = decode_cycles(cfg, m, ctx)
        tps = CLOCK_MHZ * 1e6 / perf["compute_cycles"]
        tps_bw = CLOCK_MHZ * 1e6 / max(perf["compute_cycles"], memory_cycles(m, ctx, 2))
        need = ab.required_core
        fit = "FIT" if need <= BUDGETS["TT 8 tiles"] else f"{need/BUDGETS['TT 8 tiles']:.1f}x"
        print(
            f"{cfg.label:<22}{size_activation_ram(m,ctx):>11}{need/1e6:>11.4f}"
            f"{perf['compute_cycles']:>11,}{tps:>11.1f}{tps_bw:>13.1f}{fit:>10}"
        )
    print("-" * 118)
    print()


def print_prefill_note(model: wl.ModelConfig, ctx: int) -> None:
    print("=" * 118)
    print(f"TABLE H -- when the square array DOES pay: prefill of {ctx} tokens, {model.name}")
    print("=" * 118)
    p = wl.prefill_summary(model, ctx)
    print(f"{'config':<22}{'PEs':>6}{'eff MAC/cyc':>13}{'wt B/cyc needed':>17}{'MAC per wt byte':>17}{'prefill s':>12}{'speedup':>10}")
    print("-" * 118)
    base = None
    for cfg in build_configs():
        # prefill has M=ctx >> R, so both dataflows reach full PE utilisation.
        eff = cfg.pes
        cyc = p["macs"] / eff
        if base is None:
            base = cyc
        # the real difference: an OS array reuses each weight down its R rows,
        # so it needs C bytes/cycle for R*C MACs.  A GEMV vector unit has no
        # such reuse and needs R*C bytes/cycle at any M.
        wt_bpc = cfg.c if cfg.dataflow == "os_square" else cfg.pes
        print(
            f"{cfg.label:<22}{cfg.pes:>6}{eff:>13}{wt_bpc:>17}{eff/wt_bpc:>17.0f}"
            f"{cyc/(CLOCK_MHZ*1e6):>12.3f}{base/cyc:>9.1f}x"
        )
    print("-" * 118)
    print(f"prefill arithmetic intensity = {p['arith_intensity']:.0f} MAC/byte vs ~1 MAC/byte for decode.")
    print("This is the ONLY column where output-stationary wins: at M>=R it turns C bytes/cycle of weight")
    print("bandwidth into R*C MACs/cycle.  At M=1 that amplification collapses to 1x and the R-1 unused")
    print("rows are pure dead silicon.  Prefill happens once per prompt; decode happens once per token.")
    print()


def print_tt_minimum(ctx: int) -> None:
    """What is the largest useful engine that actually fits a Tiny Tapeout budget?

    Strips every optional block: power-of-two requantisation, no special-function
    unit (firmware does exp/rsqrt over Wishbone), DFF scratch only, and the FFN
    hidden vector streamed off-chip instead of buffered.
    """
    print("=" * 118)
    print(f"TABLE I -- stripped-down variants against the Tiny Tapeout budgets (stories260K, ctx={ctx})")
    print("=" * 118)
    m = wl.MODELS_BY_NAME["stories260K"]
    variants = [
        ("full  1x4 ws_vector", Config("1x4", 1, 4, "ws_vector"), True, True, size_activation_ram(m, ctx)),
        ("lean  1x4 ws_vector", Config("1x4", 1, 4, "ws_vector"), False, True, 3 * m.dim),
        ("bare  1x4 ws_vector", Config("1x4", 1, 4, "ws_vector"), False, False, 3 * m.dim),
        ("bare  1x4, 128 B scratch", Config("1x4", 1, 4, "ws_vector"), False, False, 128),
        ("bare  1x8, 128 B scratch", Config("1x8", 1, 8, "ws_vector"), False, False, 128),
        ("bare  4x4, 128 B scratch", Config("4x4", 4, 4, "ws_vector"), False, False, 128),
    ]
    print(f"{'variant':<28}{'requant':>10}{'SFU':>6}{'scratch B':>11}{'cells um^2':>12}{'core um^2':>12}{'TT tiles':>10}{'TT8':>7}")
    print("-" * 118)
    for label, cfg, sfu, mulreq, scratch in variants:
        cells = cfg.pes * mult_area(8, 8)
        if cfg.dataflow == "ws_vector":
            cells += cfg.c * adder_tree_area(cfg.r, 16)
            cells += cfg.c * (reg_area(ACC_WIDTH) + adder_area(ACC_WIDTH))
            cells += reg_area(8 * cfg.r)
        cells += reg_area(2 * 8 * cfg.weight_bytes_per_cycle)
        cells += requant_area("mul_shift" if mulreq else "shift")
        cells += SFU_AREA if sfu else 0.0
        cells += CTRL_AREA
        mem = choose_memory("scratch", int(math.ceil(scratch / 64.0) * 64), prefer="dff")
        cells += mem.area
        core = cells / UTIL
        tiles = core / TT_TILE
        verdict = "FIT" if core <= BUDGETS["TT 8 tiles"] else "NO"
        print(
            f"{label:<28}{('mul' if mulreq else 'shift'):>10}{('yes' if sfu else 'no'):>6}"
            f"{scratch:>11}{cells:>12,.0f}{core:>12,.0f}{tiles:>10.1f}{verdict:>7}"
        )
    print("-" * 118)
    print(f"TT tiles = required core / {TT_TILE:,.0f} um^2 per 1x1 tile.  TT8 budget = 8 tiles = {8*TT_TILE:,.0f} um^2.")
    print("'no SFU' means exp/rsqrt/reciprocal are done by firmware over the Wishbone slave -- correct, but it")
    print("puts a CPU round-trip in the inner loop of every RMSNorm, softmax and SwiGLU.")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="stories15M", choices=[m.name for m in wl.MODELS])
    ap.add_argument("--ctx", type=int, default=128)
    ap.add_argument("--requant", default="mul_shift", choices=["mul_shift", "shift"])
    args = ap.parse_args()

    model = wl.MODELS_BY_NAME[args.model]
    print()
    print("OpenChip NPU design-space exploration -- sky130A, 50 MHz, int8")
    print(f"workload: {model.name} decode @ ctx={args.ctx}   requantiser: {args.requant}")
    print()

    print_tech_table()
    print_memory_reality(model)
    rows = print_sweep(model, args.ctx, args.requant)
    print_memory_bound(model, args.ctx, rows)
    print_budget_fit(model, args.ctx, rows)
    print_where_the_area_goes(model, args.ctx, args.requant)
    print_small_model_option(args.ctx, args.requant)
    print_tt_minimum(args.ctx)
    print_prefill_note(model, args.ctx)


if __name__ == "__main__":
    main()
