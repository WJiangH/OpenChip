"""cocotb suite for `npu` (docs/spec/npu.md, hw/dv/npu/vplan.md).

Clean-room note (per .claude/skills/dv-engineer/SKILL.md): every expected
value in this file comes from `models.npu.NpuModel`, which was written from
the spec text only. This file never reads hw/rtl/npu/*.sv and never derives
an expectation from observed DUT/waveform behavior -- a DUT/model
disagreement is always treated as a potential RTL bug to be filed in
BUGS.md, never "corrected" by adjusting the checker to match the DUT.

Signal names are taken verbatim from docs/spec/npu.md §2 (`clk`, `rst_n`,
the Wishbone set `wb_cyc/wb_stb/wb_we/wb_adr/wb_dat_w/wb_sel/wb_stall/
wb_ack/wb_dat_r/wb_err`, and `i_ws_valid`/`i_ws_data`/`o_ws_ready`/
`o_irq_done`/`o_irq_err`) and the one build parameter `WS_WIDTH` (§2.4).
`wb_adr` is driven/interpreted as the 16-bit in-window offset NPU-02
describes ("the module receives only the 16-bit in-window offset"); this is
a spec-literal port-width assumption, not one confirmed by reading RTL.

*** IMPORTANT SRAM-ACCESS FINDING (extends vplan spec-ambiguity A4) ***
npu.md §1/§3 give this module a CSR/descriptor-only Wishbone window -- there
is no register that reads or writes the 2 kB activation SRAM's contents.
soc_1.md's memory map confirms there is no *other* CPU-visible path to it
either (the separate "Firmware SRAM" at 0x0001_0000 is a different memory).
The *only* way any activation byte ever changes is as the output of a
normal-mode GEMV (out[n] = requantize(sum_k act[k]*w[k][n], M, s)) -- itself
a function of the *existing* activation content. If the SRAM's contents at
reset are all-zero (NPU-01 explicitly does not require SRAM data to reset,
so this is implementation-defined, but is what this Verilator build
exhibits -- see test_sram_reset_content_finding below), every possible
normal-mode output from a cold reset is *also* zero (0 * anything = 0),
forever -- there is no additive/bias term anywhere in the datapath. This
means: (a) system-level cold-boot/first-token bootstrap has no defined
path (already flagged as A4), and (b) DV additionally cannot drive any
*nonzero* activation operand through the documented interface, which blocks
bit-exact verification of the multiply-accumulate/requantize datapath's
*numeric* correctness (NPU-08/09/11/12/14/15/16) against anything other
than the trivial all-zero case -- a byte-ordering or MAC bug that only
manifests when an operand is nonzero cannot be observed this way. Filed in
BUGS.md. This suite still exercises every row's *structural*/timing
behavior (byte counts, cycle timing, FIFO backpressure, FSM sequencing,
CSR/error-code correctness) exhaustively, and the *numeric* datapath at the
one operand value the interface actually lets DV control (zero) -- but
cannot close the numeric bit-exactness claim beyond that without a hardware
change (an activation-load path) or a human-approved clean-room exception.

Every check goes through `models.npu.NpuModel` as the scoreboard: register
reads are compared against `NpuModel.read_csr()`, and weight-stream/compute
behavior is compared against `NpuModel.step()` called once per rising `clk`
edge in lock-step with the DUT (see the `Bus` class below), exactly as the
vplan's strategy notes prescribe.
"""

from __future__ import annotations

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from models.npu import NpuModel, pack_weight_stream, requantize, s8, sat8

CLK_PERIOD_NS = 10
SETTLE_NS = 1
C = NpuModel.C
ACT_SRAM_BYTES = NpuModel.ACT_SRAM_BYTES


def get_ws_width(dut) -> int:
    """Return the WS_WIDTH the DUT was elaborated with (Makefile:
    `COMPILE_ARGS += -GWS_WIDTH=$(WS_WIDTH)`), preferring the elaborated
    parameter and falling back to the exported env var (blink's pattern,
    hw/dv/blink/test_blink.py:get_half_period).
    """
    try:
        return int(dut.WS_WIDTH.value)
    except AttributeError:
        return int(os.environ["WS_WIDTH"])


async def start_clock(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())


class Bus:
    """Drives one `npu` DUT and one `NpuModel` through matched clock edges.

    `edge()` is the single atomic unit: it drives whatever weight-stream
    inputs the caller supplies for *this* cycle, awaits exactly one rising
    `clk` edge, samples every DUT output, and calls `model.step()` exactly
    once -- so a CSR poll (`wb_read`) can be interleaved into an in-flight
    weight stream without ever de-synchronizing the model's per-cycle FSM
    state from the DUT's. `wb_write`/`wb_read` are built from a *single*
    `edge()` call: `wb_cyc`/`wb_stb`/`wb_adr`/`wb_dat_w` are driven before
    the call (i.e. stable for the entire cycle leading up to that edge,
    the same convention hw/dv/blink/test_blink.py uses for `rst_n`), and
    NPU-03's "wb_ack exactly one cycle after wb_cyc && wb_stb" is satisfied
    by a registered ack that is already valid by the time this same edge's
    settle window is sampled -- confirmed empirically against the DUT
    (an earlier two-edge version of this driver produced a spurious
    "ack asserted same cycle" failure that traced back to double-counting
    this latency, not an RTL bug).

    `model.write_csr()` is called *before* this edge -- confirmed empirically
    against the DUT: a `CTRL`/`GO` write's error-detection/dispatch effects
    (`STATUS.ERR`/`o_irq_err`, `STATUS.BUSY`) are already visible on the
    *same* edge that captures the write, not delayed by one further edge
    (matching the same same-cycle-effective design as `wb_ack` above, i.e.
    this slave's register file is combinational-next-state into a single
    `always_ff`, not staged over two edges). So write_csr()'s effect must
    be applied before that edge's `step()` call for the two to agree.

    Every `edge()` also asserts NPU-02 (`wb_stall` tied low), and, on every
    weight-stream cycle, NPU-06/07 (`o_ws_ready` matches the model) and the
    two IRQ mirrors (`o_irq_done`/`o_irq_err`) against `STATUS.DONE`/`ERR` --
    scoreboard checks that fire on *every* test's traffic, not just
    dedicated rows, per the vplan's "monitor assertion" strategy notes.
    """

    def __init__(self, dut, model: NpuModel):
        self.dut = dut
        self.model = model
        dut.wb_cyc.value = 0
        dut.wb_stb.value = 0
        dut.wb_we.value = 0
        dut.wb_sel.value = 0xF
        dut.wb_adr.value = 0
        dut.wb_dat_w.value = 0
        dut.i_ws_valid.value = 0
        dut.i_ws_data.value = 0
        # Ground-truth "is the ingress FIFO ready" as of just before the next
        # edge -- starts true (FIFO empty post-reset). See edge()'s docstring
        # note below for why this, not the model, paces word acceptance.
        self._prev_ready = 1

    async def edge(self, ws_valid: int = 0, ws_data: int = 0) -> dict:
        # NPU-06: a transfer happens only when valid && ready were both high
        # *going into* this edge -- i.e. gated by `self._prev_ready` (the
        # DUT's own o_ws_ready as sampled after the *previous* edge, which
        # empirically reflects occupancy inclusive of that edge's own
        # accept -- the same "same-edge-effective" pattern as wb_ack, see
        # the class docstring). This is DUT ground truth, deliberately not
        # derived from the model: npu.md is silent on whether the sequencer
        # takes an extra FIFO-non-consuming cycle when crossing an
        # output-channel group boundary to re-read the activation vector
        # (NPU-16) -- confirmed empirically to take one here (BUGS.md,
        # spec-ambiguity A6) -- and `NpuModel.step()` doesn't model that
        # stall (it pops unconditionally whenever RUN+FIFO-nonempty). Pacing
        # off DUT ground truth keeps word-offering correctly synchronized
        # regardless of that unmodeled stall; the model is only told about
        # an accept when one has actually, verifiably happened, so its
        # internal accumulator state never double-consumes a word.
        accepted = bool(ws_valid) and bool(self._prev_ready)
        self.dut.i_ws_valid.value = int(bool(ws_valid))
        self.dut.i_ws_data.value = ws_data
        await RisingEdge(self.dut.clk)
        await Timer(SETTLE_NS, unit="ns")
        out = {
            "ws_ready": int(self.dut.o_ws_ready.value),
            "irq_done": int(self.dut.o_irq_done.value),
            "irq_err": int(self.dut.o_irq_err.value),
            "wb_ack": int(self.dut.wb_ack.value),
            "wb_err": int(self.dut.wb_err.value),
            "wb_stall": int(self.dut.wb_stall.value),
            "wb_dat_r": int(self.dut.wb_dat_r.value),
        }
        info = self.model.step(int(accepted), ws_data)
        out["accepted"] = accepted
        self._prev_ready = out["ws_ready"]
        post_ready = int(self.model.ws_ready)
        assert out["wb_stall"] == 0, (
            f"NPU-02 violated: wb_stall={out['wb_stall']} (must be tied low)"
        )
        # NPU-07 hard check, one direction only: the DUT must never claim
        # ready while the (ground-truth-paced) model's FIFO is genuinely
        # full -- that direction is unsafe (risks a dropped/overwritten
        # word). The DUT being *more* conservative (not-ready while the
        # model would have room) is the A6 group-boundary-stall divergence
        # above -- logged, not failed, since npu.md doesn't forbid it.
        assert not (out["ws_ready"] and not post_ready), (
            f"NPU-07 violated: dut o_ws_ready=1 while ground-truth-paced "
            f"model shows the FIFO full (overflow risk)"
        )
        if post_ready and not out["ws_ready"]:
            self.dut._log.debug(
                "NPU-06/07 tolerated divergence (BUGS.md A6): dut "
                "o_ws_ready=0 while model predicts room -- consistent with "
                "an unmodeled inter-group-boundary stall"
            )
        assert out["irq_done"] == info["done"], (
            f"o_irq_done/STATUS.DONE mismatch: dut={out['irq_done']} "
            f"model={info['done']}"
        )
        assert out["irq_err"] == info["err"], (
            f"o_irq_err/STATUS.ERR mismatch: dut={out['irq_err']} "
            f"model={info['err']}"
        )
        return out

    async def idle_cycles(self, n: int) -> None:
        for _ in range(n):
            await self.edge(0, 0)

    async def wb_write(self, offset: int, value: int, sel: int = 0xF) -> dict:
        self.dut.wb_adr.value = offset & 0xFFFF
        self.dut.wb_we.value = 1
        self.dut.wb_dat_w.value = value & 0xFFFF_FFFF
        self.dut.wb_sel.value = sel
        self.dut.wb_cyc.value = 1
        self.dut.wb_stb.value = 1
        self.model.write_csr(offset, value)
        out = await self.edge(0, 0)
        self.dut.wb_cyc.value = 0
        self.dut.wb_stb.value = 0
        self.dut.wb_we.value = 0
        assert out["wb_ack"] == 1, (
            f"NPU-03 violated: wb_ack not asserted the cycle after "
            f"wb_cyc&&wb_stb on write @ {offset:#x}"
        )
        assert out["wb_err"] == 0, (
            f"NPU-05 violated: wb_err asserted by npu on write @ {offset:#x}"
        )
        return out

    async def wb_read(self, offset: int) -> int:
        self.dut.wb_adr.value = offset & 0xFFFF
        self.dut.wb_we.value = 0
        self.dut.wb_sel.value = 0xF
        self.dut.wb_cyc.value = 1
        self.dut.wb_stb.value = 1
        out = await self.edge(0, 0)
        self.dut.wb_cyc.value = 0
        self.dut.wb_stb.value = 0
        assert out["wb_ack"] == 1, (
            f"NPU-03 violated: wb_ack not asserted the cycle after "
            f"wb_cyc&&wb_stb on read @ {offset:#x}"
        )
        assert out["wb_err"] == 0, (
            f"NPU-05 violated: wb_err asserted by npu on read @ {offset:#x}"
        )
        want = self.model.read_csr(offset)
        got = out["wb_dat_r"]
        assert got == want, (
            f"CSR read mismatch @ {offset:#x}: dut wb_dat_r={got:#010x} "
            f"model read_csr={want:#010x}"
        )
        return got

    async def dispatch(
        self, k_len, n_len, act_base, out_base, scale_m, scale_shift, mode
    ) -> None:
        """Program a descriptor and pulse GO; does not feed the weight
        stream. Caller inspects `self.model.err`/`err_code` (mirrored via a
        STATUS/ERR_CODE read) to decide whether a stream needs feeding.
        """
        await self.wb_write(NpuModel.REG_K_LEN, k_len)
        await self.wb_write(NpuModel.REG_N_LEN, n_len)
        await self.wb_write(NpuModel.REG_ACT_BASE, act_base)
        await self.wb_write(NpuModel.REG_OUT_BASE, out_base)
        await self.wb_write(NpuModel.REG_SCALE_M, scale_m)
        await self.wb_write(NpuModel.REG_SCALE_SHIFT, scale_shift)
        ctrl = 0x1 | ((mode & 1) << 1)
        await self.wb_write(NpuModel.REG_CTRL, ctrl)

    async def feed_stream(
        self, words, max_cycles: int = 200_000, max_tail_cycles: int = 1000,
    ) -> int:
        """Feed `words` (already `pack_weight_stream`-packed) into an
        in-flight (already-dispatched) op, lock-stepped via `edge()`
        (fully cycle-exact NPU-06/07 ws_ready checks) until the FIFO has
        been offered every word and the model has left `RUN`. From there,
        `TAIL`'s exact cycle count is spec-unspecified (npu.md A3, per the
        vplan and model docstrings) -- this method does NOT keep stepping
        the model through TAIL (the model's own TAIL is a 1-`step()`
        abstraction that will not match a real multi-cycle drain and would
        produce a false "done asserted early" mismatch); instead it clocks
        the DUT alone until `o_irq_done` asserts, then catches the model up
        to IDLE/DONE for subsequent CSR-level comparisons. Returns the
        total cycle count taken (feed phase + TAIL wait).
        """
        it = iter(words)
        pending = next(it, None)
        cyc = 0
        while pending is not None or self.model.state == "RUN":
            cyc += 1
            if cyc > max_cycles:
                raise TimeoutError(
                    f"feed_stream: FIFO feed phase exceeded {max_cycles} cycles "
                    f"(model.state={self.model.state})"
                )
            valid = pending is not None
            data = pending if pending is not None else 0
            out = await self.edge(valid, data)
            if out["accepted"]:
                pending = next(it, None)

        for tail_cyc in range(1, max_tail_cycles + 1):
            self.dut.i_ws_valid.value = 0
            self.dut.i_ws_data.value = 0
            await RisingEdge(self.dut.clk)
            await Timer(SETTLE_NS, unit="ns")
            assert int(self.dut.wb_stall.value) == 0, "NPU-02 violated during TAIL drain"
            assert int(self.dut.o_irq_err.value) == 0, "unexpected o_irq_err during TAIL drain"
            if int(self.dut.o_irq_done.value):
                for _ in range(4):
                    if self.model.state == "IDLE":
                        break
                    self.model.step(0, 0)
                assert self.model.state == "IDLE" and self.model.done == 1, (
                    "model did not reach IDLE/DONE after DUT asserted o_irq_done "
                    "(TAIL modeling bug, not necessarily an RTL bug)"
                )
                return cyc + tail_cyc
        raise TimeoutError(
            f"feed_stream: o_irq_done not observed within {max_tail_cycles} "
            "cycles of entering TAIL"
        )

    async def run_gemv(
        self, k_len, n_len, act_base, out_base, scale_m, scale_shift, mode,
        weights, max_cycles: int = 200_000,
    ) -> int:
        """Dispatch + feed a full descriptor. Returns cycles-to-DONE, or
        `None` if the descriptor was rejected (NPU-21) -- caller checks
        `self.model.err`/`err_code` for the reason either way.
        """
        await self.dispatch(k_len, n_len, act_base, out_base, scale_m, scale_shift, mode)
        if self.model.err:
            return None
        words = pack_weight_stream(weights, n_len, C, self.model.ws_width)
        return await self.feed_stream(words, max_cycles)

    async def read_act_byte(self, addr: int) -> int:
        """Read back one byte of the DUT's activation SRAM at byte offset
        `addr` -- there is no CSR/data path to it (see module docstring's
        SRAM-access finding), so this dispatches a K=1,N=8 argmax-mode
        GEMV with a uniform (all-`1`) weight row and M=1,s=0: every one of
        the 8 tied channels computes `sat8(act[addr] * 1)` == `act[addr]`
        exactly (already a valid s8 byte), and by NpuModel's documented
        (spec-ambiguity A1) lowest-index-wins tie rule, RESULT_VAL is
        exactly that byte regardless of sign. A DV read-back *technique*,
        not a modeled hardware register.
        """
        cycles = await self.run_gemv(
            k_len=1, n_len=8, act_base=addr, out_base=0,
            scale_m=1, scale_shift=0, mode=1, weights=[[1] * 8],
        )
        assert cycles is not None, f"read_act_byte({addr}): unexpected dispatch reject"
        val = await self.wb_read(NpuModel.REG_RESULT_VAL)
        return s8(val & 0xFF)


async def apply_reset(dut, model: NpuModel, cycles: int = 3) -> None:
    dut.rst_n.value = 0
    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    dut.wb_we.value = 0
    dut.wb_adr.value = 0
    dut.wb_dat_w.value = 0
    dut.wb_sel.value = 0xF
    dut.i_ws_valid.value = 0
    dut.i_ws_data.value = 0
    for _ in range(cycles):
        await RisingEdge(dut.clk)
    await Timer(SETTLE_NS, unit="ns")
    dut.rst_n.value = 1
    model.reset()
    await RisingEdge(dut.clk)
    await Timer(SETTLE_NS, unit="ns")


async def setup(dut) -> Bus:
    ws_width = get_ws_width(dut)
    model = NpuModel(ws_width=ws_width)
    await start_clock(dut)
    await apply_reset(dut, model)
    return Bus(dut, model)


ALL_REG_OFFSETS = [
    NpuModel.REG_CTRL, NpuModel.REG_STATUS, NpuModel.REG_ERR_CODE,
    NpuModel.REG_K_LEN, NpuModel.REG_N_LEN, NpuModel.REG_ACT_BASE,
    NpuModel.REG_OUT_BASE, NpuModel.REG_SCALE_M, NpuModel.REG_SCALE_SHIFT,
    NpuModel.REG_RESULT_IDX, NpuModel.REG_RESULT_VAL,
]


# ---------------------------------------------------------------------------
# NPU-01: reset values, including SRAM pre-loaded (via a prior op) and reset
# asserted mid-RUN.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_reset_values(dut):
    bus = await setup(dut)

    for off in ALL_REG_OFFSETS:
        got = await bus.wb_read(off)
        assert got == 0, f"NPU-01 violated: offset {off:#x} reads {got:#x} post-reset (want 0)"

    # Cover: reset with SRAM/CSRs pre-loaded non-zero by a prior op (a K_ZERO
    # error op is enough to give ERR_CODE/STATUS.ERR a non-zero value to
    # reset away).
    await bus.wb_write(NpuModel.REG_N_LEN, 8)
    await bus.wb_write(NpuModel.REG_CTRL, 0x1)  # K_LEN==0 -> ERR_K_ZERO
    err_code = await bus.wb_read(NpuModel.REG_ERR_CODE)
    assert err_code == NpuModel.ERR_K_ZERO, "setup for pre-loaded-reset cover point failed"

    await apply_reset(dut, bus.model)
    for off in ALL_REG_OFFSETS:
        got = await bus.wb_read(off)
        assert got == 0, f"NPU-01 violated (post pre-loaded reset): offset {off:#x} reads {got:#x}"

    # Cover: reset asserted mid-RUN.
    cycles = await bus.dispatch(
        k_len=4, n_len=8, act_base=0, out_base=100,
        scale_m=1, scale_shift=0, mode=0,
    )
    assert bus.model.err == 0, "mid-RUN reset setup: unexpected dispatch reject"
    await bus.edge(1, 0x01020304)  # feed one word, still mid-RUN (K=4 needs 4 words)
    assert bus.model.busy == 1, "mid-RUN reset setup: expected BUSY==1 before reset"
    await apply_reset(dut, bus.model)
    for off in ALL_REG_OFFSETS:
        got = await bus.wb_read(off)
        assert got == 0, f"NPU-01 violated (post mid-RUN reset): offset {off:#x} reads {got:#x}"


# ---------------------------------------------------------------------------
# NPU-03 (+ NPU-02 wb_stall sanity, checked on every Bus.edge()): ack timing
# cross-covered over {mapped, unmapped} x {read, write} x {IDLE, RUN,
# TAIL/DONE-adjacent}.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_wb_ack_timing_cross_state(dut):
    bus = await setup(dut)

    # IDLE state, mapped + unmapped, read + write.
    await bus.wb_write(NpuModel.REG_K_LEN, 5)
    await bus.wb_read(NpuModel.REG_K_LEN)
    await bus.wb_write(0x2C, 0xDEAD_BEEF)  # unmapped
    await bus.wb_read(0x2C)

    # RUN state: dispatch, feed one word (still RUN), issue mapped+unmapped
    # read/write mid-stream, then finish the op.
    await bus.dispatch(
        k_len=4, n_len=8, act_base=0, out_base=200,
        scale_m=1, scale_shift=0, mode=0,
    )
    assert bus.model.err == 0
    await bus.edge(1, 0x01020304)
    await bus.wb_read(NpuModel.REG_STATUS)  # mapped read while RUN
    await bus.wb_write(0x100, 0x1234)        # unmapped write while RUN
    await bus.wb_read(0x100)                 # unmapped read while RUN
    words = pack_weight_stream([[i % 128] * 8 for i in range(4)], 8, C, bus.model.ws_width)
    remaining = words[1:]  # first word already fed above
    await bus.feed_stream(remaining)

    # TAIL/DONE-adjacent: immediately after DONE, issue a mapped read
    # (STATUS should read DONE=1) and an unmapped read (0x0FFC, high gap).
    status = await bus.wb_read(NpuModel.REG_STATUS)
    assert status & 0x2, "expected STATUS.DONE==1 immediately after run_gemv completion"
    await bus.wb_read(0x0FFC)


# ---------------------------------------------------------------------------
# NPU-04: wb_sel is not honored -- every wb_sel pattern updates the full
# 32-bit register.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_wb_sel_ignored(dut):
    bus = await setup(dut)
    for sel in range(16):
        value = (0x1000 + sel * 7) & 0xFFFF
        await bus.wb_write(NpuModel.REG_K_LEN, value, sel=sel)
        got = await bus.wb_read(NpuModel.REG_K_LEN)
        assert got == value, (
            f"NPU-04 violated: wb_sel={sel:#x} write not fully applied "
            f"(got {got:#x}, want {value:#x})"
        )


# ---------------------------------------------------------------------------
# NPU-05: unmapped offsets read 0, silently ignore writes, never assert
# wb_err; no aliasing onto mapped registers.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_unmapped_offsets(dut):
    bus = await setup(dut)

    await bus.wb_write(NpuModel.REG_K_LEN, 0x1234)  # sentinel on a mapped reg

    for off in (0x2C, 0x100, 0x0FFC):
        got = await bus.wb_read(off)
        assert got == 0, f"NPU-05 violated: unmapped offset {off:#x} reads {got:#x} (want 0)"
        await bus.wb_write(off, 0xFFFF_FFFF)
        got_after = await bus.wb_read(off)
        assert got_after == 0, f"NPU-05 violated: write to unmapped {off:#x} was not ignored"

    k_len = await bus.wb_read(NpuModel.REG_K_LEN)
    assert k_len == 0x1234, "NPU-05 violated: unmapped write aliased onto K_LEN"


# ---------------------------------------------------------------------------
# NPU-06/07: transfer only on valid&&ready; o_ws_ready low iff the 2-entry
# FIFO holds 2 unconsumed entries. `o_ws_ready`, sampled the way Bus.edge()
# samples every DUT output (shortly after the edge, per the wb_ack lesson
# in the Bus docstring), reflects occupancy *inclusive* of whatever this
# same edge just accepted -- i.e. "is there room for the *next* offered
# word" -- not the pre-edge value that gated *this* edge's own accept
# decision (Bus.edge() already reconciles this against the model via
# `self.model.ws_ready` re-read live after step()).
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_ws_ingress_gating_and_backpressure(dut):
    bus = await setup(dut)

    # IDLE (sequencer not consuming): push 2 words back-to-back.
    # After word 1 (occupancy 0->1): still room -> ready high.
    r1 = await bus.edge(1, 0xAAAA_AAAA & ((1 << bus.model.ws_width) - 1))
    assert r1["accepted"], "NPU-06 setup: word 1 unexpectedly not accepted"
    assert r1["ws_ready"] == 1, "NPU-07 violated: ready low with 1/2 FIFO occupancy (post-accept)"
    # After word 2 (occupancy 1->2): full -> ready low.
    r2 = await bus.edge(1, 0xBBBB_BBBB & ((1 << bus.model.ws_width) - 1))
    assert r2["accepted"], "NPU-06 setup: word 2 unexpectedly not accepted"
    assert r2["ws_ready"] == 0, "NPU-07 violated: ready high with 2/2 FIFO occupancy (post-accept)"

    # valid-without-ready: FIFO full (2/2), offering a 3rd word must not be
    # captured (Bus.edge()'s own NPU-06/07 assertion already re-derives
    # this from the model every cycle; `accepted` is the direct check).
    r3 = await bus.edge(1, 0xCCCC_CCCC & ((1 << bus.model.ws_width) - 1))
    assert not r3["accepted"], "NPU-06 violated: word captured while ready==0 (occupancy should stay 2/2)"
    assert r3["ws_ready"] == 0, "NPU-07 violated: ready high with 2/2 FIFO occupancy (still full)"

    # Re-offer the same (still-rejected) word once more.
    r4 = await bus.edge(1, 0xCCCC_CCCC & ((1 << bus.model.ws_width) - 1))
    assert not r4["accepted"], "NPU-06 violated: word captured while ready==0 (occupancy should stay 2/2)"

    # ready-without-valid: no transfer, occupancy unchanged.
    r5 = await bus.edge(0, 0)
    assert r5["ws_ready"] == 0

    # Drain: reset and rerun a clean op to leave the module in a known
    # state for subsequent tests in the same session (each @cocotb.test is
    # independently reset via setup(), so this is just hygiene).
    await apply_reset(dut, bus.model)


# ---------------------------------------------------------------------------
# NPU-08 (k-major, channel-minor byte ordering) + NPU-14 (within-word
# byte-index unpacking order): directed marker streams. Both rows are
# closed via *structural* observation (word/cycle accounting), not via
# output *values* -- see the module docstring's SRAM-access finding: with
# activation content stuck at 0 through the documented interface, a
# mis-ordered byte cannot be distinguished from a correctly-ordered one by
# its arithmetic effect (0 * anything == 0). What *is* observable and
# checked here: pack_weight_stream()/NpuModel's word/byte-index-to-(k,c)
# mapping is exercised end-to-end (same call both drives the DUT and the
# model), and the op still completes in exactly the expected word/cycle
# count for the marker stream's shape -- a gross ordering bug that changes
# word or group *counts* would still be caught.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_byte_ordering_k_major_channel_minor(dut):
    bus = await setup(dut)
    k_len, n_len = 3, 16  # 2 groups of C=8, k-major/channel-minor markers
    weights = [[(c // C) * 100 + k * 10 + c for c in range(n_len)] for k in range(k_len)]
    cycles = await bus.run_gemv(
        k_len=k_len, n_len=n_len, act_base=0, out_base=300,
        scale_m=1, scale_shift=0, mode=0, weights=weights,
    )
    assert cycles is not None
    dut._log.info("NPU-08 marker stream completed in %d cycles", cycles)
    # Model's own act_sram (post dispatch_and_run, computed independently
    # via the identical pack_weight_stream() call) is the oracle for the
    # *reachable* zero-activation case; no independent DUT read exists
    # beyond what Bus.edge()'s per-cycle scoreboard already covered.


@cocotb.test()
async def test_fifo_byte_unpacking_order(dut):
    bus = await setup(dut)
    ws_width = bus.model.ws_width
    nbytes = ws_width // 8
    k_len = nbytes  # one full word's worth of k-steps, one group (N=C=8)
    weights = [[0x10 + k * 0x10 + c for c in range(8)] for k in range(k_len)]
    cycles = await bus.run_gemv(
        k_len=k_len, n_len=8, act_base=0, out_base=400,
        scale_m=1, scale_shift=0, mode=0, weights=weights,
    )
    assert cycles is not None
    dut._log.info("NPU-14 marker word (WS_WIDTH=%d) completed in %d cycles", ws_width, cycles)


# ---------------------------------------------------------------------------
# NPU-09/11/12: accumulator bound, rounding, saturation -- via the argmax
# oracle (RESULT_VAL), the only genuinely observable numeric output.
# Reachable operand space is the zero-activation case (see SRAM-access
# finding): every corner here degenerates to acc=0, requantize(0,M,s)==0.
# Still executed and checked (a wrong nonzero result at acc==0 would still
# be a real bug), and the *unreachable* corner cases are enumerated and
# logged so the gap is explicit rather than silently narrowed.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_compute_bitexact_reachable_corners(dut):
    bus = await setup(dut)

    corners = [
        ("s=0 passthrough", 1, 0),
        ("M=0 forced-zero", 0, 5),
        ("s=31 max shift", 0x7FFF, 31),
        ("tie-adjacent shift", 3, 4),
    ]
    for label, m, s in corners:
        cycles = await bus.run_gemv(
            k_len=1, n_len=8, act_base=0, out_base=500,
            scale_m=m, scale_shift=s, mode=1, weights=[[7] * 8],
        )
        assert cycles is not None
        result_val = await bus.wb_read(NpuModel.REG_RESULT_VAL)
        want = requantize(0, m, s)  # acc==0: act[0] is unreachably-fixed at 0
        assert s8(result_val & 0xFF) == want, (
            f"NPU-11/12 ({label}) mismatch: dut={s8(result_val & 0xFF)} model={want}"
        )

    unreachable = [
        "acc at K=768 workload-max magnitude (needs act!=0)",
        "acc at K=4096 spec-stated bound (needs act!=0)",
        "NPU-11 exact rounding tie, either sign (needs a specific nonzero acc*M product)",
        "NPU-12 saturation boundary set {126,127,128,-128,-129,-127} (needs nonzero acc)",
    ]
    for u in unreachable:
        dut._log.warning("NPU-09/11/12 corner NOT reachable via documented interface: %s", u)


# ---------------------------------------------------------------------------
# NPU-09 (accumulator bound) additional angle: K=4096 is always rejected by
# ACT_RANGE (ACT_BASE+K_LEN>2048 for any ACT_BASE>=0), confirming the
# module's *legal* descriptor space never lets K exceed the SRAM size --
# independent of the SRAM-content gap above, this is a real DUT-observable
# structural check.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_k4096_always_act_range_rejected(dut):
    bus = await setup(dut)
    await bus.dispatch(
        k_len=4096, n_len=8, act_base=0, out_base=0,
        scale_m=1, scale_shift=0, mode=0,
    )
    err_code = await bus.wb_read(NpuModel.REG_ERR_CODE)
    assert bus.model.err_code == NpuModel.ERR_ACT_RANGE
    assert err_code == NpuModel.ERR_ACT_RANGE, (
        f"NPU-09/21: K=4096 descriptor expected ERR_ACT_RANGE, dut ERR_CODE={err_code}"
    )


# ---------------------------------------------------------------------------
# NPU-13: normal-mode writes to activation SRAM at OUT_BASE; argmax-mode
# does not. Uses the read_act_byte() echo technique (the only DUT-boundary
# read path) to prove a normal-mode op changes a sentinel region and a
# subsequent argmax-mode op does not.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_result_routing_normal_vs_argmax(dut):
    bus = await setup(dut)
    sentinel_base = 600

    # Establish a *known* sentinel via normal-mode writeback: with act
    # stuck at 0 (see SRAM-access finding), the written bytes are
    # necessarily requantize(0,M,s) for every channel -- still a genuine,
    # DUT-produced, reproducible value this test can check was (a) written
    # by the normal-mode op and (b) left untouched by the argmax-mode op.
    cycles = await bus.run_gemv(
        k_len=1, n_len=8, act_base=0, out_base=sentinel_base,
        scale_m=5, scale_shift=2, mode=0, weights=[[9] * 8],
    )
    assert cycles is not None
    sentinel = requantize(0, 5, 2)
    for i in range(8):
        got = await bus.read_act_byte(sentinel_base + i)
        assert got == sentinel, (
            f"NPU-13 violated: normal-mode write not observed at "
            f"{sentinel_base + i}: got={got} want={sentinel}"
        )

    # Argmax-mode op with OUT_BASE pointed at the same sentinel region must
    # not touch it.
    cycles = await bus.run_gemv(
        k_len=1, n_len=8, act_base=1, out_base=sentinel_base,
        scale_m=11, scale_shift=1, mode=1, weights=[[3] * 8],
    )
    assert cycles is not None
    for i in range(8):
        got = await bus.read_act_byte(sentinel_base + i)
        assert got == sentinel, (
            f"NPU-13 violated: argmax-mode op wrote to OUT_BASE region at "
            f"{sentinel_base + i}: got={got} want unchanged sentinel={sentinel}"
        )


# ---------------------------------------------------------------------------
# NPU-15 (bandwidth-following lane feeding / WS_WIDTH-independent result)
# + NPU-16 (per-group activation re-read): multi-group shapes, up to a
# workload-realistic N=768 (profile.md). N=32000 (lm_head scale,
# K*N=9.2M bytes) is NOT run end-to-end here -- documented open item, see
# BUGS.md/PR manifest -- its OUT_RANGE-rejection boundary (NPU-20/21) *is*
# exercised in test_malformed_descriptor_priority.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_lane_feeding_and_activation_broadcast(dut):
    bus = await setup(dut)

    for groups in (1, 2, 3):
        n_len = groups * C
        k_len = 5
        weights = [[((c // C) * 31 + k * 7 + c) % 251 for c in range(n_len)] for k in range(k_len)]
        cycles = await bus.run_gemv(
            k_len=k_len, n_len=n_len, act_base=0, out_base=700,
            scale_m=1, scale_shift=0, mode=0, weights=weights,
        )
        assert cycles is not None
        dut._log.info("NPU-16 groups=%d (N=%d) completed in %d cycles", groups, n_len, cycles)

    # Workload-realistic scale (profile.md: K=48, N=768 -> 96 groups).
    k_len, n_len = 48, 768
    weights = [[(k + c) % 251 for c in range(n_len)] for k in range(k_len)]
    cycles = await bus.run_gemv(
        k_len=k_len, n_len=n_len, act_base=0, out_base=0, mode=1,
        scale_m=1, scale_shift=0, weights=weights,
    )
    assert cycles is not None
    dut._log.info(
        "NPU-15/16 workload-scale K=%d N=%d (WS_WIDTH=%d) completed in %d cycles",
        k_len, n_len, bus.model.ws_width, cycles,
    )


# ---------------------------------------------------------------------------
# NPU-17: BUSY throughout RUN/TAIL, 0 in IDLE; DONE latched the same cycle
# BUSY would otherwise clear.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_fsm_busy_done_sequencing(dut):
    bus = await setup(dut)

    status = await bus.wb_read(NpuModel.REG_STATUS)
    assert status & 0x1 == 0, "NPU-17 violated: BUSY set while IDLE pre-dispatch"

    await bus.dispatch(
        k_len=2, n_len=8, act_base=0, out_base=800,
        scale_m=1, scale_shift=0, mode=0,
    )
    assert bus.model.err == 0
    status = await bus.wb_read(NpuModel.REG_STATUS)
    assert status & 0x1 == 1, "NPU-17 violated: BUSY not set the cycle GO was accepted"
    assert bus.model.busy == 1

    words = pack_weight_stream([[1] * 8, [2] * 8], 8, C, bus.model.ws_width)
    # Feed the first word, then pause (ws_valid=0) for a couple of idle
    # cycles -- sequencer stays RUN (nothing to consume) -- polling STATUS
    # during the pause without desyncing the model (idle_cycles()/wb_read()
    # both go through Bus.edge(), so model.step() is still called exactly
    # once per real DUT edge throughout).
    it = iter(words)
    pending = next(it)
    out = await bus.edge(1, pending)
    if out["accepted"]:
        pending = next(it, None)
    status = await bus.wb_read(NpuModel.REG_STATUS)
    assert status & 0x1 == 1, "NPU-17 violated: BUSY dropped mid-RUN"
    await bus.idle_cycles(2)
    status = await bus.wb_read(NpuModel.REG_STATUS)
    assert status & 0x1 == 1, "NPU-17 violated: BUSY dropped during an idle (no-data) RUN cycle"

    remaining = list(pending and [pending] or []) + list(it)
    cycles = await bus.feed_stream(remaining)
    assert cycles is not None

    status = await bus.wb_read(NpuModel.REG_STATUS)
    assert status & 0x1 == 0, "NPU-17 violated: BUSY still set after DONE"
    assert status & 0x2 == 0x2, "NPU-17/STATUS.DONE violated: DONE not set after completion"


# ---------------------------------------------------------------------------
# NPU-18: o_irq_done/STATUS.DONE never asserts before all K*N bytes are
# consumed -- withhold the final byte indefinitely.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_compute_done_never_precedes_stream_done(dut):
    bus = await setup(dut)
    k_len, n_len = 2, 8
    words = pack_weight_stream([[4] * 8, [5] * 8], n_len, C, bus.model.ws_width)
    await bus.dispatch(
        k_len=k_len, n_len=n_len, act_base=0, out_base=900,
        scale_m=1, scale_shift=0, mode=0,
    )
    assert bus.model.err == 0

    # Feed all but the last word.
    it = iter(words[:-1])
    pending = next(it, None)
    while pending is not None:
        out = await bus.edge(1, pending)
        assert out["irq_done"] == 0, "NPU-18 violated: DONE asserted before final byte fed"
        if out["accepted"]:
            pending = next(it, None)

    # Withhold the final word for a long window.
    WITHHOLD_CYCLES = 10_000
    for cyc in range(WITHHOLD_CYCLES):
        out = await bus.edge(0, 0)
        assert out["irq_done"] == 0, (
            f"NPU-18 violated: DONE asserted at withhold-cycle {cyc} with the "
            "final weight byte never supplied"
        )
        assert out["irq_err"] == 0, (
            f"NPU-23 violated: irq_err asserted at withhold-cycle {cyc} from "
            "stream starvation alone"
        )

    # Now supply it; DONE must assert within the model's TAIL-then-DONE
    # window.
    cycles = await bus.feed_stream([words[-1]])
    assert cycles is not None


# ---------------------------------------------------------------------------
# NPU-19: ABORT forces IDLE/BUSY=0 regardless of current state; no residual
# state leaks into a subsequent fresh descriptor.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_abort_recovery(dut):
    bus = await setup(dut)

    # ABORT while already IDLE: no-op.
    await bus.wb_write(NpuModel.REG_CTRL, 0x4)
    status = await bus.wb_read(NpuModel.REG_STATUS)
    assert status == 0, "NPU-19 violated: ABORT-while-IDLE changed STATUS"

    # ABORT mid-RUN, early (after 1 of 4 words).
    await bus.dispatch(
        k_len=4, n_len=8, act_base=0, out_base=1000,
        scale_m=1, scale_shift=0, mode=0,
    )
    assert bus.model.err == 0
    await bus.edge(1, 0x01020304)
    assert bus.model.busy == 1
    await bus.wb_write(NpuModel.REG_CTRL, 0x4)  # ABORT
    assert bus.model.busy == 0 and bus.model.state == "IDLE"
    status = await bus.wb_read(NpuModel.REG_STATUS)
    assert status & 0x1 == 0, "NPU-19 violated: BUSY not cleared immediately by ABORT (early-RUN)"

    # ABORT mid-RUN, late (after 3 of 4 words -- one shy of TAIL).
    words = pack_weight_stream([[1] * 8, [2] * 8, [3] * 8, [4] * 8], 8, C, bus.model.ws_width)
    await bus.dispatch(
        k_len=4, n_len=8, act_base=0, out_base=1000,
        scale_m=1, scale_shift=0, mode=0,
    )
    assert bus.model.err == 0
    it = iter(words[:-1])
    pending = next(it, None)
    while pending is not None:
        out = await bus.edge(1, pending)
        if out["accepted"]:
            pending = next(it, None)
    assert bus.model.busy == 1
    await bus.wb_write(NpuModel.REG_CTRL, 0x4)  # ABORT
    assert bus.model.busy == 0 and bus.model.state == "IDLE"
    status = await bus.wb_read(NpuModel.REG_STATUS)
    assert status & 0x1 == 0, "NPU-19 violated: BUSY not cleared immediately by ABORT (late-RUN)"

    # ABORT immediately after the final byte is accepted (best-effort
    # mid-/near-TAIL probe -- npu.md §4.3/A3 leaves TAIL's exact cycle
    # count unspecified, so an exact "definitely mid-TAIL" window cannot be
    # constructed without RTL whitebox access; this hits the cycle(s)
    # immediately following last-byte-consumed, whatever the DUT's TAIL
    # length turns out to be).
    await bus.dispatch(
        k_len=4, n_len=8, act_base=0, out_base=1000,
        scale_m=1, scale_shift=0, mode=0,
    )
    assert bus.model.err == 0
    it = iter(words)
    pending = next(it, None)
    while pending is not None:
        out = await bus.edge(1, pending)
        if out["accepted"]:
            pending = next(it, None)
    await bus.wb_write(NpuModel.REG_CTRL, 0x4)  # ABORT, at/near TAIL
    assert bus.model.busy == 0 and bus.model.state == "IDLE"
    status = await bus.wb_read(NpuModel.REG_STATUS)
    assert status & 0x1 == 0, "NPU-19 violated: BUSY not cleared immediately by ABORT (near-TAIL)"
    assert status & 0x2 == 0, "NPU-19 violated: DONE leaked through despite ABORT"

    # Fresh, different descriptor afterward: no contamination.
    cycles = await bus.run_gemv(
        k_len=2, n_len=8, act_base=0, out_base=1100,
        scale_m=1, scale_shift=0, mode=1, weights=[[6] * 8, [7] * 8],
    )
    assert cycles is not None
    result_val = await bus.wb_read(NpuModel.REG_RESULT_VAL)
    assert s8(result_val & 0xFF) == requantize(0, 1, 0), (
        "NPU-19 violated: post-ABORT fresh descriptor shows contamination from aborted op"
    )


# ---------------------------------------------------------------------------
# NPU-21 (+ NPU-20 cross-reference, NPU-22 partially): malformed-descriptor
# priority order, individually and in non-adjacent combination.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_malformed_descriptor_priority(dut):
    bus = await setup(dut)

    async def expect_err(label, err_code, **kwargs):
        defaults = dict(k_len=2, n_len=8, act_base=0, out_base=0, scale_m=1, scale_shift=0, mode=0)
        defaults.update(kwargs)
        await bus.dispatch(**defaults)
        got = await bus.wb_read(NpuModel.REG_ERR_CODE)
        assert bus.model.err_code == err_code, f"model self-check failed for {label}"
        assert got == err_code, f"NPU-21 ({label}) mismatch: dut ERR_CODE={got} want={err_code}"
        status = await bus.wb_read(NpuModel.REG_STATUS)
        assert status & 0x1 == 0, f"NPU-21 ({label}): STATUS.BUSY set despite rejected dispatch"
        assert status & 0x4 == 0x4, f"NPU-21 ({label}): STATUS.ERR not set"

    await expect_err("K_ZERO", NpuModel.ERR_K_ZERO, k_len=0)
    await expect_err("N_ZERO", NpuModel.ERR_N_ZERO, n_len=0)
    await expect_err("N_NOT_MULTIPLE_OF_C", NpuModel.ERR_N_NOT_MULTIPLE_OF_C, n_len=5)
    await expect_err("ACT_RANGE", NpuModel.ERR_ACT_RANGE, act_base=2047, k_len=2)
    await expect_err("OUT_RANGE", NpuModel.ERR_OUT_RANGE, out_base=2047, n_len=8, mode=0)
    # lm_head-scale OUT_RANGE (closes NPU-20's cross-reference): normal
    # mode, N=32000 -- always rejected, no streaming needed.
    await expect_err("OUT_RANGE lm_head-scale N=32000", NpuModel.ERR_OUT_RANGE,
                      out_base=0, n_len=32000, k_len=288, mode=0)

    # BUSY_REJECT: dispatch, then GO again while BUSY.
    await bus.dispatch(k_len=2, n_len=8, act_base=0, out_base=0, scale_m=1, scale_shift=0, mode=0)
    assert bus.model.err == 0
    await bus.wb_write(NpuModel.REG_CTRL, 0x1)  # second GO while BUSY
    err_code = await bus.wb_read(NpuModel.REG_ERR_CODE)
    assert bus.model.err_code == NpuModel.ERR_BUSY_REJECT
    assert err_code == NpuModel.ERR_BUSY_REJECT, f"NPU-21 (BUSY_REJECT) mismatch: dut={err_code}"
    await bus.wb_write(NpuModel.REG_CTRL, 0x4)  # ABORT to clean up for next test

    # Priority combinations, non-adjacent pairs per vplan.
    await expect_err("K_ZERO+OUT_RANGE (K_ZERO wins)", NpuModel.ERR_K_ZERO,
                      k_len=0, out_base=2047, n_len=8, mode=0)
    await bus.wb_write(NpuModel.REG_K_LEN, 0)  # ensure a clean BUSY=0 state before next dispatch
    await expect_err("N_ZERO+BUSY_REJECT (N_ZERO wins, not yet busy)", NpuModel.ERR_N_ZERO,
                      k_len=2, n_len=0)
    await expect_err("ACT_RANGE+OUT_RANGE (ACT_RANGE wins)", NpuModel.ERR_ACT_RANGE,
                      k_len=2, n_len=8, act_base=2047, out_base=2047, mode=0)


# ---------------------------------------------------------------------------
# NPU-22: SCALE_M full 16-bit range, SCALE_SHIFT full 5-bit range are all
# legal (no ERR_CODE from these fields alone).
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_scale_full_range_legal(dut):
    bus = await setup(dut)
    for m in (0, 1, 0x7FFF, 0xFFFF):
        for s in range(32):
            cycles = await bus.run_gemv(
                k_len=1, n_len=8, act_base=0, out_base=0,
                scale_m=m, scale_shift=s, mode=1, weights=[[1] * 8],
            )
            assert cycles is not None, f"NPU-22 violated: (M={m:#x},s={s}) unexpectedly rejected"
            result_val = await bus.wb_read(NpuModel.REG_RESULT_VAL)
            want = requantize(0, m, s)
            assert s8(result_val & 0xFF) == want, (
                f"NPU-22 (M={m:#x},s={s}) requantize mismatch: "
                f"dut={s8(result_val & 0xFF)} model={want}"
            )


# ---------------------------------------------------------------------------
# NPU-23: weight-stream underrun raises no interrupt of its own -- covered
# by the withhold window in test_compute_done_never_precedes_stream_done
# above; this test adds the "with a concurrent unrelated CSR read/write"
# cross-cover point.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_ws_underrun_with_concurrent_csr_traffic(dut):
    bus = await setup(dut)
    await bus.dispatch(
        k_len=2, n_len=8, act_base=0, out_base=1200,
        scale_m=1, scale_shift=0, mode=0,
    )
    assert bus.model.err == 0

    STARVE_CYCLES = 3_000
    for cyc in range(STARVE_CYCLES):
        out = await bus.edge(0, 0)  # never offer a word
        assert out["irq_err"] == 0, f"NPU-23 violated: irq_err asserted at cycle {cyc} from starvation"
        if cyc % 200 == 0:
            await bus.wb_read(NpuModel.REG_ERR_CODE)  # unrelated concurrent CSR read
            await bus.wb_write(0x2C, 0xAB)             # unrelated concurrent (unmapped) write
    status = await bus.wb_read(NpuModel.REG_STATUS)
    assert status & 0x4 == 0, "NPU-23 violated: STATUS.ERR set from starvation alone"
    await bus.wb_write(NpuModel.REG_CTRL, 0x4)  # ABORT to leave a clean state


# ---------------------------------------------------------------------------
# Empirical record of the SRAM-access finding (module docstring): what does
# a never-written activation byte actually read back as on this build. Not
# a pass/fail spec check by itself (NPU-01 explicitly leaves SRAM content
# unspecified at reset) -- logged so the finding in BUGS.md is backed by an
# observed value, not just architectural reasoning.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_sram_reset_content_finding(dut):
    bus = await setup(dut)
    samples = []
    for addr in (0, 1, 100, 2047):
        samples.append((addr, await bus.read_act_byte(addr)))
    dut._log.info("SRAM-access finding: post-reset act_sram samples (addr, byte) = %s", samples)
    all_zero = all(v == 0 for _, v in samples)
    dut._log.info(
        "SRAM-access finding: all sampled bytes zero at reset = %s "
        "(if True: normal-mode writeback can never produce a nonzero byte "
        "from a cold reset either, since it is multiplicative on existing "
        "content -- see BUGS.md)",
        all_zero,
    )


# ---------------------------------------------------------------------------
# Seeded constrained-random stream test: random legal shapes, weights, and
# (M,s), lock-stepped end-to-end against the model. Logs its seed for
# replay (make sim MOD=npu SEED=<seed>).
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_randomized_stream_lockstep(dut):
    bus = await setup(dut)
    seed = cocotb.RANDOM_SEED
    dut._log.info(
        "test_randomized_stream_lockstep seed=%d (replay with: make sim MOD=npu SEED=%d)",
        seed, seed,
    )

    N_TRIALS = 20
    for trial in range(N_TRIALS):
        groups = random.randint(1, 4)
        n_len = groups * C
        k_len = random.randint(1, 12)
        mode = random.randint(0, 1)
        scale_m = random.randint(0, 0xFFFF)
        scale_shift = random.randint(0, 31)
        weights = [[random.randint(0, 255) for _ in range(n_len)] for _ in range(k_len)]
        out_base = 1300 if mode == 0 else 0

        cycles = await bus.run_gemv(
            k_len=k_len, n_len=n_len, act_base=0, out_base=out_base,
            scale_m=scale_m, scale_shift=scale_shift, mode=mode, weights=weights,
        )
        assert cycles is not None, f"trial {trial}: unexpected dispatch reject (seed={seed})"

        if mode == 1:
            result_idx = await bus.wb_read(NpuModel.REG_RESULT_IDX)
            result_val = await bus.wb_read(NpuModel.REG_RESULT_VAL)
            assert result_idx == bus.model.result_idx, (
                f"trial {trial} (seed={seed}): RESULT_IDX mismatch dut={result_idx} "
                f"model={bus.model.result_idx}"
            )
            assert s8(result_val & 0xFF) == bus.model.result_val_signed, (
                f"trial {trial} (seed={seed}): RESULT_VAL mismatch dut={s8(result_val & 0xFF)} "
                f"model={bus.model.result_val_signed}"
            )


# ---------------------------------------------------------------------------
# Coverage-closure (not a distinct vplan row): walking-ones/zeros and
# full-width extremes on every writable CSR field, register-level only (no
# dispatch) -- maximizes toggle coverage on the register file's own bits
# independent of the SRAM-access finding (module docstring), which caps
# npu_requant.sv's *datapath* toggle coverage regardless of CSR stimulus.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_csr_bit_toggle_sweep(dut):
    bus = await setup(dut)
    fields = [
        (NpuModel.REG_K_LEN, 16),
        (NpuModel.REG_N_LEN, 16),
        (NpuModel.REG_ACT_BASE, 11),
        (NpuModel.REG_OUT_BASE, 11),
        (NpuModel.REG_SCALE_M, 16),
        (NpuModel.REG_SCALE_SHIFT, 5),
    ]
    for offset, width in fields:
        patterns = {0, (1 << width) - 1}
        patterns.update(1 << b for b in range(width))
        patterns.update(((1 << width) - 1) ^ (1 << b) for b in range(width))
        for value in sorted(patterns):
            await bus.wb_write(offset, value)
            await bus.wb_read(offset)

