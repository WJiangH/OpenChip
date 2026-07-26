"""Golden reference model for the `blink` module.

Spec: docs/spec/blink.md §4 "Functional behavior" (requirements BLINK-01
through BLINK-08). Pure Python, cycle-based, no cocotb / simulator
dependency — this module must be importable and runnable standalone (see
`__main__` below), and is the single source of "expected value" for the
blink DV suite (hw/dv/blink/). Per the verif-architect clean-room rule, this
model was written from the spec text only, never from RTL.

Cycle model
-----------
`BlinkModel.step(rst_n)` represents exactly one rising edge of `clk`: the
caller supplies the value of `rst_n` as sampled at that edge (synchronous
reset, BLINK-08 — there is deliberately no separate "asynchronous" input
path in this model, since the spec requires none to exist), and the method
returns the new value of `o_led` immediately after that edge, mirroring what
a testbench would sample on the DUT's `o_led` port at the same edge.

Per spec §4:
    "blink holds a free-running cycle counter `cnt` and a single output
    register `o_led`. Every clock cycle that `cnt` reaches
    `HALF_PERIOD - 1`, `o_led` is inverted and `cnt` restarts from 0;
    otherwise `cnt` increments."
"""

from __future__ import annotations


class BlinkModel:
    """Cycle-accurate golden model of `blink` (docs/spec/blink.md §4).

    Construction implements the reset state (BLINK-01, BLINK-02): `cnt` and
    `o_led` both start at 0, identically to what happens "while rst_n is low,
    on the next rising edge of clk" (BLINK-01) and with no residual phase
    carried forward (BLINK-02).

    HALF_PERIOD validity (BLINK-07): must be a positive integer; `0` is
    explicitly out of scope per spec §5/§4-BLINK-07 ("HALF_PERIOD = 0 is not
    a legal configuration and its behavior is unspecified") and is rejected
    here rather than silently modeled, since simulating undefined behavior
    would not be a golden reference.
    """

    def __init__(self, half_period: int):
        if not isinstance(half_period, int) or half_period < 1:
            raise ValueError(
                "HALF_PERIOD must be a positive integer (BLINK-07); "
                f"got {half_period!r}"
            )
        self.half_period = half_period
        self.cnt = 0
        self.o_led = 0

    def reset(self) -> None:
        """Apply the reset state (BLINK-01, BLINK-02).

        `cnt` and `o_led` are both driven to 0, with no residual phase
        carried forward from whatever state preceded the reset — matching
        BLINK-02's requirement that the counter "begin counting from 0 ...
        as if from power-on" regardless of when/how long reset was held
        (spec §6 advisory: reset may be re-asserted mid-period, and the same
        BLINK-01/02 requirements apply on every reset, not just the first).
        """
        self.cnt = 0
        self.o_led = 0

    def step(self, rst_n: int) -> int:
        """Advance the model by exactly one rising `clk` edge.

        `rst_n` is the reset input value as sampled at this edge (BLINK-08:
        reset is synchronous — there is no asynchronous sampling path, so a
        single per-edge sample is the complete and correct model of the
        input).

        Behavior per spec §4:
          - if `rst_n` is low: reset (BLINK-01) — `o_led` -> 0, `cnt` -> 0.
          - elif `cnt == HALF_PERIOD - 1`: toggle — `o_led` -> ~o_led,
            `cnt` -> 0. This is the toggle transition exercised by
            BLINK-03 (first toggle at cycle HALF_PERIOD), BLINK-04
            (steady-state, every HALF_PERIOD cycles thereafter), and
            BLINK-05 (the toggle is symmetric in both directions, giving a
            50% duty cycle since the same HALF_PERIOD-length count-up
            precedes every toggle regardless of the pre-toggle `o_led`
            value).
          - else: `cnt` -> cnt + 1; `o_led` unchanged.

        Returns the new `o_led` value, which is the only DUT-observable
        port per spec §2.3 (the internal `cnt` has no external port).
        """
        if not rst_n:
            self.reset()
        elif self.cnt == self.half_period - 1:
            self.o_led ^= 1
            self.cnt = 0
        else:
            self.cnt += 1
        return self.o_led

    def run(self, n_cycles: int, rst_n: int = 1) -> list[int]:
        """Convenience: step `n_cycles` times with a constant `rst_n`,
        returning the list of `o_led` values observed after each edge, in
        order. Does not touch state before the first step (call `reset()`
        first if a known starting state is needed beyond what `__init__`
        already provides).
        """
        return [self.step(rst_n) for _ in range(n_cycles)]


def _expect_sequence(half_period: int, n_cycles: int) -> list[int]:
    """Hand-derivable reference sequence for a fresh (just-reset) model run
    for `n_cycles` cycles with `rst_n` held high throughout.

    Cycle k (1-indexed, matching spec BLINK-03's "cycle 1 = first post-reset
    clock edge") has cnt-before-edge = (k - 1) mod half_period. o_led toggles
    (relative to its previous value) exactly when cnt-before-edge equals
    half_period - 1, i.e. whenever k is a multiple of half_period. So
    o_led at cycle k = (number of multiples of half_period in 1..k) mod 2.
    """
    seq = []
    o_led = 0
    for k in range(1, n_cycles + 1):
        if k % half_period == 0:
            o_led ^= 1
        seq.append(o_led)
    return seq


def _self_check() -> bool:
    ok = True

    def check(label: str, got, want) -> None:
        nonlocal ok
        status = "PASS" if got == want else "FAIL"
        if got != want:
            ok = False
        print(f"[{status}] {label}: got={got!r} want={want!r}")

    # --- HALF_PERIOD=4: hand-computed sequence for 8 cycles ---
    # cnt: 0->1->2->3(=HP-1, toggle)->0->1->2->3(toggle)
    # o_led: 0  0  0  1(toggle@4)     1  1  1  0(toggle@8)
    m = BlinkModel(half_period=4)
    got = m.run(8)
    want = [0, 0, 0, 1, 1, 1, 1, 0]
    check("HALF_PERIOD=4, 8 cycles from reset", got, want)
    check("HALF_PERIOD=4 matches formula", got, _expect_sequence(4, 8), )
    check("BLINK-03: first toggle exactly at cycle=HALF_PERIOD(4)",
          got.index(1) + 1, 4)

    # --- HALF_PERIOD=5: hand-computed sequence for 10 cycles ---
    # First toggle at cycle 5, second at cycle 10.
    m = BlinkModel(half_period=5)
    got = m.run(10)
    want = [0, 0, 0, 0, 1, 1, 1, 1, 1, 0]
    check("HALF_PERIOD=5, 10 cycles from reset", got, want)
    check("BLINK-04: second toggle exactly at cycle=2*HALF_PERIOD(10)",
          got.index(0, 5) + 1, 10)

    # --- HALF_PERIOD=1: edge value, toggle every cycle ---
    m = BlinkModel(half_period=1)
    got = m.run(6)
    want = [1, 0, 1, 0, 1, 0]
    check("HALF_PERIOD=1 (edge value): toggles every cycle", got, want)

    # --- HALF_PERIOD=2: edge value ---
    m = BlinkModel(half_period=2)
    got = m.run(8)
    want = [0, 1, 1, 0, 0, 1, 1, 0]
    check("HALF_PERIOD=2 (edge value): toggles every other cycle", got, want)

    # --- BLINK-04/BLINK-05: toggles land exactly on cycle N*HALF_PERIOD for
    #     N=1,2,3,..., i.e. consecutive toggle timestamps are HALF_PERIOD
    #     cycles apart (50% duty cycle, symmetric both directions).
    for hp in (1, 2, 4, 5):
        m = BlinkModel(half_period=hp)
        n_periods = 6
        seq = m.run(hp * n_periods)  # 6 full toggle periods worth of cycles
        # 1-indexed cycle numbers where o_led changed value, treating the
        # pre-run reset state (o_led=0) as the implicit "cycle 0" baseline.
        toggle_cycles = []
        prev = 0
        for i, v in enumerate(seq, start=1):
            if v != prev:
                toggle_cycles.append(i)
                prev = v
        check(f"BLINK-04: toggle cycles == N*HALF_PERIOD({hp}) for N=1..{n_periods}",
              toggle_cycles, [hp * n for n in range(1, n_periods + 1)])
        gaps = [b - a for a, b in zip(toggle_cycles, toggle_cycles[1:])]
        check(f"BLINK-05: consecutive toggle gaps all == HALF_PERIOD({hp})",
              gaps, [hp] * len(gaps))

    # --- BLINK-01/BLINK-02: reset holds o_led=cnt=0 for the whole pulse,
    #     and restarts cleanly with no residual phase, including a
    #     mid-period re-assertion (spec §6 advisory).
    m = BlinkModel(half_period=4)
    m.run(3, rst_n=1)  # cnt now at 3 (about to toggle), o_led still 0
    check("pre-reset state: cnt=3 (about to toggle)", m.cnt, 3)
    check("pre-reset state: o_led=0", m.o_led, 0)
    reset_obs = m.run(3, rst_n=0)  # hold reset low for 3 cycles
    check("BLINK-01: o_led==0 throughout reset pulse", reset_obs, [0, 0, 0])
    check("BLINK-01: cnt==0 throughout/after reset pulse", m.cnt, 0)
    post = m.run(4, rst_n=1)  # restart: first toggle should be at cycle 4
    check("BLINK-02: no residual phase, first toggle at cycle=HALF_PERIOD "
          "after a mid-period reset", post, [0, 0, 0, 1])

    # --- BLINK-07: same structural behavior across several HALF_PERIOD
    #     values (already exercised above via the parameterized loop); add
    #     an explicit rejection check for HALF_PERIOD=0.
    try:
        BlinkModel(half_period=0)
        check("BLINK-07: HALF_PERIOD=0 rejected", "no exception raised",
              "ValueError")
    except ValueError:
        check("BLINK-07: HALF_PERIOD=0 rejected", "ValueError", "ValueError")

    return ok


if __name__ == "__main__":
    result = _self_check()
    print("PASS" if result else "FAIL")
    raise SystemExit(0 if result else 1)
