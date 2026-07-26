# blink Specification

Status: draft
Owner: spec-architect · Implements: milestone M0

**Tracer bullet notice:** `blink` is deliberately trivial and carries zero
architecture-decision content. It exists only to exercise the full
spec → DV → RTL → formal → synth → GDS pipeline and rehearse the multi-agent
protocol end-to-end before any real workload is specced. It intentionally
skips the workload-profile and DSE steps that would normally precede a spec
(see `.claude/skills/chief-architect/SKILL.md` §Thinking order) — there is no
candidate comparison to make for a single free-running counter driving one
pin.

## §1 Overview
`blink` is a standalone LED-blinker module: a free-running counter that
toggles a single output bit every `HALF_PERIOD` clock cycles. It has no
consumers and no producers in SoC-1 today; it is not wired to any bus or
memory map. It stands alone as the first module to complete the full flow.

## §2 Interface

### §2.1 Clock & reset
`clk` (in), `rst_n` (in, synchronous, active-low, per `/CLAUDE.md`). All state
shall reset.

### §2.2 Bus interface
N/A. `blink` is a standalone tracer-bullet module with no Wishbone (or other)
bus connection — no bus fabric exists yet in SoC-1 for it to attach to, and a
free-running blinker has no registers to expose. A future integration (wiring
`blink` under CSR control) is out of scope for this spec and would be a
separate change order.

### §2.3 Other signals
| Signal  | Dir | Width | Description                                    |
|---------|-----|-------|-------------------------------------------------|
| `clk`   | in  | 1     | System clock.                                   |
| `rst_n` | in  | 1     | Synchronous active-low reset.                   |
| `o_led` | out | 1     | LED drive signal. Registered (glitch-free).     |

### §2.4 Parameters
| Parameter     | Type            | Default      | Description                                          |
|---------------|-----------------|--------------|-------------------------------------------------------|
| `HALF_PERIOD` | positive integer | 25_000_000  | Clock cycles between toggles of `o_led` (0.5 s at 50 MHz). |

## §3 Register map
N/A — no bus interface (see §2.2); no registers.

## §4 Functional behavior

`blink` holds a free-running cycle counter `cnt` and a single output register
`o_led`. Every clock cycle that `cnt` reaches `HALF_PERIOD - 1`, `o_led` is
inverted and `cnt` restarts from 0; otherwise `cnt` increments.

Numbered requirements (each **shall** is one DV test obligation):

1. **BLINK-01 (reset value):** While `rst_n` is low, on the next rising edge
   of `clk` the module shall set `o_led = 0` and reset the internal counter
   to 0.
2. **BLINK-02 (post-reset restart):** Immediately after `rst_n` deasserts,
   the counter shall begin counting from 0 and the toggle period shall
   restart as if from power-on — no residual phase from before/during reset
   is carried forward.
3. **BLINK-03 (first toggle timing):** Counting clock cycles from the first
   cycle after `rst_n` deasserts (cycle 1 = first post-reset clock edge), the
   module shall produce the first toggle of `o_led` (0→1) exactly on cycle
   `HALF_PERIOD`, i.e. after exactly `HALF_PERIOD` clock cycles have elapsed
   post-reset.
4. **BLINK-04 (steady-state period):** After the first toggle, the module
   shall toggle `o_led` again every subsequent `HALF_PERIOD` clock cycles,
   indefinitely, for as long as `rst_n` remains high (i.e. toggle N occurs at
   cycle `N * HALF_PERIOD` for all positive integers N).
5. **BLINK-05 (50% duty cycle):** `o_led` shall be high for exactly
   `HALF_PERIOD` cycles and low for exactly `HALF_PERIOD` cycles per full
   period (`2 * HALF_PERIOD` cycles), i.e. the toggle period is symmetric.
6. **BLINK-06 (glitch-free output):** `o_led` shall be driven only from a
   register updated on the rising edge of `clk`; it shall never be derived
   combinationally from `cnt` or any other signal, and shall therefore change
   at most once per clock cycle with no intra-cycle glitches.
7. **BLINK-07 (parameter validity):** `HALF_PERIOD` shall be a positive
   integer (`HALF_PERIOD >= 1`). For any such value, behavior (BLINK-01
   through BLINK-06) shall be identical in structure, differing only in the
   numeric cycle count at which toggles occur. `HALF_PERIOD = 0` is not a
   legal configuration and its behavior is unspecified.
8. **BLINK-08 (no combinational reset dependency on `clk` edge type):**
   `rst_n` shall be sampled synchronously — the module shall contain no
   asynchronous reset logic (no `always @(posedge clk or negedge rst_n)` or
   equivalent); reset shall take effect only on a rising `clk` edge per
   `/CLAUDE.md` conventions.

## §5 Error conditions
N/A. There is no bus, no illegal-address space, and no protocol to violate.
Out-of-range `HALF_PERIOD` (i.e. `HALF_PERIOD = 0`, see BLINK-07) is a static
elaboration-time configuration error, not a runtime error condition, and is
not required to be checked in hardware.

## §6 Verification notes (advisory)
- DV shall instantiate `blink` with small `HALF_PERIOD` values (e.g. 4) to
  keep simulation short; BLINK-01 through BLINK-08 must hold identically for
  any positive `HALF_PERIOD`, including edge values `HALF_PERIOD = 1` (toggle
  every cycle) and `HALF_PERIOD = 2`.
- Reset may be asserted and deasserted at arbitrary points relative to the
  counter's internal phase; BLINK-02 requires the count to restart from 0
  regardless of when reset was asserted.
- Reset may be re-asserted mid-period (e.g. partway between toggles); the
  same BLINK-01/BLINK-02 requirements apply on every reset, not just the
  first.
- A directed test should hold `rst_n` low for more than one clock cycle to
  confirm `o_led` and the counter remain at their reset values throughout
  reset assertion, not just on deassertion.

## §7 Open questions
None. Status is `draft` (not `frozen`) only because this is a newly authored
spec pending first review pass, not because any requirement above is
unresolved.
