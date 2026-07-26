# blink.sdc — timing constraints for `blink`.
#
# Source of truth: flow/gates.mk (CLOCK_PERIOD_NS := 20, WNS_MIN := 0) and
# docs/spec/blink.md §2.1 (single clock `clk`, synchronous active-low `rst_n`).
# Iron Rule 5: the period is spec.  It is never relaxed to close timing — a
# failing path is an RTL/PD problem, not a constraint problem.
#
# Used by: OpenSTA (`make synth` once OpenSTA is installed on the host) and as
# the human-readable reference for the LibreLane constraint set, which is
# generated from CLOCK_PORT / CLOCK_PERIOD in hw/pd/blink/config.yaml.

set clk_period 20.0
set clk_port   clk

create_clock -name clk -period $clk_period [get_ports $clk_port]

# No PLL/clock-gating in blink: ideal-clock assumptions until CTS, then the
# LibreLane STA steps use the propagated post-CTS clock.
set_clock_uncertainty 0.25 [get_clocks clk]
set_clock_transition  0.15 [get_clocks clk]

# I/O budget: blink is standalone (no bus, docs/spec/blink.md §2.2).  Reserve
# 20% of the period at each boundary so the flow cannot hide an I/O path.
set_input_delay  -clock clk [expr {0.20 * $clk_period}] [get_ports rst_n]
set_output_delay -clock clk [expr {0.20 * $clk_period}] [get_ports o_led]

# Reset is synchronous (BLINK-08): it is a normal timed data path, so there is
# deliberately no false_path / set_disable_timing on rst_n here.

set_max_fanout 10 [current_design]
