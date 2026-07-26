"""cocotb suite for `blink` (docs/spec/blink.md, hw/dv/blink/vplan.md).

Clean-room note (per .claude/skills/dv-engineer/SKILL.md): every expected
value in this file comes from `models.blink.BlinkModel`, which was written
from the spec text only. This file never reads `hw/rtl/blink/blink.sv` and
never derives an expectation from observed DUT/waveform behavior -- a
DUT/model disagreement is always treated as a potential RTL bug to be filed
in BUGS.md, never "corrected" by adjusting the checker to match the DUT.

Every test steps the DUT and `BlinkModel` in lock-step, one rising `clk` edge
at a time, and asserts `o_led` equality every single cycle (scoreboard
pattern) -- not just at the end of a run.
"""

from __future__ import annotations

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from models.blink import BlinkModel

CLK_PERIOD_NS = 10
# Small settle delay after a RisingEdge before sampling `o_led`/writing new
# stimulus. NOTE (cocotb 2.0.1 quirk): `await ReadOnly()` after `RisingEdge`
# works for *reading* signals, but any subsequent `dut.<sig>.value = ...`
# write raises `RuntimeError: Attempting settings a value during the
# ReadOnly phase` unless another trigger is awaited first to leave that
# phase. A short `Timer` is simpler and sidesteps the phase-transition
# bookkeeping entirely (values are fully settled after the edge well before
# 10% of the clock period elapses), so this suite samples via Timer instead
# of ReadOnly throughout.
SETTLE_NS = 1


def get_half_period(dut) -> int:
    """Return the HALF_PERIOD the DUT was elaborated with.

    HALF_PERIOD is a compile-time Verilog parameter (Makefile:
    `COMPILE_ARGS += -GHALF_PERIOD=$(HALF_PERIOD)`). Prefer reading it back
    from the elaborated DUT (Verilator exposes parameters read-only via VPI
    when compiled with --public-flat-rw, see flow's Makefile.verilator) so
    the test always matches whatever value was actually compiled in; fall
    back to the Makefile's exported env var of the same name if the
    simulator does not expose the parameter as a handle.
    """
    try:
        return int(dut.HALF_PERIOD.value)
    except AttributeError:
        return int(os.environ["HALF_PERIOD"])


async def start_clock(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())


async def step(dut, model: BlinkModel, rst_n_val: int, label: str = "") -> int:
    """Drive `rst_n_val` for exactly one rising `clk` edge, then compare
    `o_led` on the DUT against `model.step(rst_n_val)` (scoreboard check).

    Returns the observed (and expected -- they must match) `o_led` value.
    """
    dut.rst_n.value = rst_n_val
    await RisingEdge(dut.clk)
    await Timer(SETTLE_NS, unit="ns")
    got = int(dut.o_led.value)
    want = model.step(rst_n_val)
    assert got == want, (
        f"o_led mismatch{(' @ ' + label) if label else ''}: "
        f"dut={got} model={want} (rst_n driven={rst_n_val})"
    )
    return got


async def force_reset(dut, model: BlinkModel, cycles: int = 2) -> None:
    """Drive rst_n low for `cycles` edges to bring DUT+model to a known,
    matching post-reset state before a scenario begins."""
    for _ in range(cycles):
        await step(dut, model, 0, label="force_reset")


# ---------------------------------------------------------------------------
# BLINK-01 / BLINK-02: reset holds o_led==0 for the whole pulse, regardless of
# the pre-reset counter phase or pulse length, and restarts with no residual
# phase (spec §6 advisory: reset may be re-asserted mid-period).
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_reset_holds_led_low_across_phase_and_length(dut):
    hp = get_half_period(dut)
    await start_clock(dut)
    model = BlinkModel(hp)

    # Phase offsets: cnt==0, mid-count, and cnt==HALF_PERIOD-1 (about to
    # toggle) when the reset pulse begins -- per vplan BLINK-01 cover point.
    phases = sorted({0, hp // 2, hp - 1})
    pulse_lens = (1, 2, 5)

    for phase in phases:
        for pulse_len in pulse_lens:
            await force_reset(dut, model, 2)
            for _ in range(phase):
                await step(dut, model, 1, label=f"phase-runup(phase={phase})")
            for c in range(pulse_len):
                got = await step(
                    dut, model, 0,
                    label=f"reset-pulse(phase={phase},len={pulse_len},c={c})",
                )
                assert got == 0, (
                    f"BLINK-01 violated: o_led={got} (expected 0) during "
                    f"reset pulse cycle {c}/{pulse_len} "
                    f"(pre-reset phase={phase}, HALF_PERIOD={hp})"
                )


# ---------------------------------------------------------------------------
# BLINK-02 constrained-random: reset asserted at a random phase offset for a
# random hold length, then the first post-deassertion toggle must land
# exactly HALF_PERIOD cycles later (never sooner -- that would mean carried
# phase).
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_post_reset_restart_no_residual_phase_random(dut):
    hp = get_half_period(dut)
    await start_clock(dut)
    model = BlinkModel(hp)

    seed = cocotb.RANDOM_SEED
    dut._log.info(
        "test_post_reset_restart_no_residual_phase_random seed=%d "
        "(replay with: make sim MOD=blink HALF_PERIOD=%d SEED=%d)",
        seed, hp, seed,
    )

    await force_reset(dut, model, 2)

    # Cross-cover every phase 0..HALF_PERIOD-1 (bounded set, so just sweep it
    # rather than sample it) x {hold==1, hold>1}.
    for phase in range(hp):
        for hold in (1, random.randint(2, 2 * hp + 1)):
            await force_reset(dut, model, 1)
            for _ in range(phase):
                await step(dut, model, 1, label=f"random-phase-runup({phase})")
            for _ in range(hold):
                await step(dut, model, 0, label=f"random-hold({hold})")

            prev = 0
            first_toggle_cycle = None
            for cyc in range(1, 2 * hp + 1):
                got = await step(
                    dut, model, 1,
                    label=f"post-random-reset(phase={phase},hold={hold},cyc={cyc})",
                )
                if got != prev and first_toggle_cycle is None:
                    first_toggle_cycle = cyc
                prev = got
            assert first_toggle_cycle == hp, (
                f"BLINK-02 violated: first post-reset toggle at cycle "
                f"{first_toggle_cycle}, expected exactly {hp} "
                f"(phase={phase}, hold={hold})"
            )


# ---------------------------------------------------------------------------
# BLINK-03: first toggle lands exactly on cycle HALF_PERIOD post-reset.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_first_toggle_timing(dut):
    hp = get_half_period(dut)
    await start_clock(dut)
    model = BlinkModel(hp)
    await force_reset(dut, model, 2)

    first_toggle_cycle = None
    for cyc in range(1, hp + 2):
        got = await step(dut, model, 1, label=f"first-toggle-cyc{cyc}")
        if cyc < hp:
            assert got == 0, (
                f"BLINK-03 violated: o_led={got} (expected 0) at cycle {cyc} "
                f"< HALF_PERIOD({hp})"
            )
        if got == 1 and first_toggle_cycle is None:
            first_toggle_cycle = cyc
    assert first_toggle_cycle == hp, (
        f"BLINK-03 violated: first toggle observed at cycle "
        f"{first_toggle_cycle}, expected exactly HALF_PERIOD={hp}"
    )


# ---------------------------------------------------------------------------
# BLINK-04 / BLINK-05: steady-state toggling every HALF_PERIOD cycles
# indefinitely (>=20 toggles), and each half-period run length (high or low)
# is exactly HALF_PERIOD cycles (50% duty cycle).
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_steady_state_period_and_duty_cycle(dut):
    hp = get_half_period(dut)
    await start_clock(dut)
    model = BlinkModel(hp)
    await force_reset(dut, model, 2)

    n_toggles_target = 20
    max_cycles = hp * (n_toggles_target + 2)
    toggle_cycles = []
    prev = 0
    for cyc in range(1, max_cycles + 1):
        got = await step(dut, model, 1, label=f"steady-state-cyc{cyc}")
        if got != prev:
            toggle_cycles.append(cyc)
            prev = got
        if len(toggle_cycles) >= n_toggles_target:
            break

    assert len(toggle_cycles) >= n_toggles_target, (
        f"only observed {len(toggle_cycles)} toggles in {max_cycles} cycles, "
        f"expected >= {n_toggles_target}"
    )

    expected = [hp * n for n in range(1, len(toggle_cycles) + 1)]
    assert toggle_cycles == expected, (
        f"BLINK-04 violated: toggle cycles {toggle_cycles} != N*HALF_PERIOD "
        f"sequence {expected}"
    )

    gaps = [b - a for a, b in zip(toggle_cycles, toggle_cycles[1:])]
    assert all(g == hp for g in gaps), (
        f"BLINK-05 violated: consecutive toggle gaps {gaps} != "
        f"HALF_PERIOD={hp} for all pairs"
    )


# ---------------------------------------------------------------------------
# BLINK-06 sim-side sanity: o_led must not change strictly between two
# consecutive rising clk edges (formal proves the structural absence of a
# combinational path; sim can only sample and confirm no observed glitch).
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_o_led_no_mid_cycle_glitch_sanity(dut):
    hp = get_half_period(dut)
    await start_clock(dut)
    model = BlinkModel(hp)
    await force_reset(dut, model, 2)

    offsets_frac = (0.25, 0.5, 0.75)
    for cyc in range(1, 2 * hp + 3):
        post_edge_val = await step(dut, model, 1, label=f"glitch-cyc{cyc}")

        # step() already advanced SETTLE_NS past the edge; sample further
        # points strictly before the next edge (at CLK_PERIOD_NS).
        elapsed_ns = SETTLE_NS
        for frac in offsets_frac:
            target_ns = frac * CLK_PERIOD_NS
            delay_ns = target_ns - elapsed_ns
            if delay_ns > 0:
                await Timer(delay_ns, unit="ns")
                elapsed_ns = target_ns
            mid_val = int(dut.o_led.value)
            assert mid_val == post_edge_val, (
                f"BLINK-06 violated: o_led changed between clock edges at "
                f"cycle {cyc}, frac={frac} of period (post-edge="
                f"{post_edge_val}, mid-cycle={mid_val}) -- suggests a "
                f"combinational/glitchy driver"
            )


# ---------------------------------------------------------------------------
# BLINK-08 sim-side sanity: rst_n falling strictly between two clk edges must
# not change o_led until the *next* rising edge (no async reset path).
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_no_async_reset_mid_cycle_sanity(dut):
    hp = get_half_period(dut)
    await start_clock(dut)
    model = BlinkModel(hp)
    await force_reset(dut, model, 2)

    pre_val = await step(dut, model, 1, label="pre-mid-cycle-reset")

    # Deassert (drop) rst_n strictly mid-cycle -- not aligned to any clk edge.
    # step() already advanced SETTLE_NS past the edge; wait to mid-period.
    await Timer(CLK_PERIOD_NS // 2 - SETTLE_NS, unit="ns")
    dut.rst_n.value = 0
    await Timer(1, unit="ns")
    mid_val = int(dut.o_led.value)
    assert mid_val == pre_val, (
        f"BLINK-08 violated: o_led changed to {mid_val} (was {pre_val}) "
        "immediately after rst_n fell mid-cycle, strictly before the next "
        "rising clk edge -- indicates an asynchronous reset path, which the "
        "spec forbids (reset must be sampled synchronously)"
    )

    # The next rising edge samples rst_n==0 (still held low), so both DUT and
    # model should now show the reset value.
    await RisingEdge(dut.clk)
    await Timer(SETTLE_NS, unit="ns")
    got = int(dut.o_led.value)
    want = model.step(0)
    assert got == want, (
        f"post mid-cycle-reset-assert mismatch at next rising edge: "
        f"dut={got} model={want}"
    )


# ---------------------------------------------------------------------------
# Randomized (seeded) lock-step test: random-length reset pulses applied at
# random times throughout a long free-running trace. Every cycle is checked
# against the golden model via `step()`, so *any* mismatch anywhere in the
# trace fails immediately with the exact cycle/scenario context.
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_randomized_reset_pulses_lockstep(dut):
    hp = get_half_period(dut)
    await start_clock(dut)
    model = BlinkModel(hp)

    seed = cocotb.RANDOM_SEED
    dut._log.info(
        "test_randomized_reset_pulses_lockstep seed=%d "
        "(replay with: make sim MOD=blink HALF_PERIOD=%d SEED=%d)",
        seed, hp, seed,
    )

    await force_reset(dut, model, random.randint(1, 3))

    n_events = 40
    for i in range(n_events):
        free_len = random.randint(0, 3 * hp)
        for _ in range(free_len):
            await step(dut, model, 1, label=f"rand-event{i}-free")

        if random.random() < 0.7:
            pulse_len = random.randint(1, 2 * hp + 1)
            for _ in range(pulse_len):
                await step(dut, model, 0, label=f"rand-event{i}-reset")

    # tail: run free for a while with no more resets, confirming steady state
    # equivalence continues to hold after the randomized reset storm.
    for _ in range(4 * hp):
        await step(dut, model, 1, label="rand-tail")
