# cocotb testbench for `blink` (docs/spec/blink.md, hw/dv/blink/vplan.md).
# DV clean-room note: this Makefile references hw/rtl/blink/blink.sv only by
# path (as VERILOG_SOURCES for the simulator to compile) — it is never opened
# or read by the DV agent.

TOPLEVEL    := blink
MODULE      := test_blink

REPO_ROOT   := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../..)
VERILOG_SOURCES := $(REPO_ROOT)/hw/rtl/blink/blink.sv

# Small HALF_PERIOD keeps directed/random runs short (spec §6 advisory).
# Overridable: make sim MOD=blink HALF_PERIOD=5
HALF_PERIOD ?= 4
export HALF_PERIOD
COMPILE_ARGS += -GHALF_PERIOD=$(HALF_PERIOD)

include $(REPO_ROOT)/flow/sim.mk
