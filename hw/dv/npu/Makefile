# cocotb testbench for `npu` (docs/spec/npu.md, hw/dv/npu/vplan.md).
# DV clean-room note: this Makefile references hw/rtl/npu/*.sv only by path
# (as VERILOG_SOURCES for the simulator to compile) -- it is never opened or
# read by the DV agent. Module name confirmed from docs/spec/npu.md's file
# naming (npu.md -> module `npu`, /CLAUDE.md's filename==module convention),
# not by reading RTL.

TOPLEVEL    := npu
MODULE      := test_npu

REPO_ROOT   := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../..)
VERILOG_SOURCES := $(REPO_ROOT)/hw/rtl/npu/*.sv

# WS_WIDTH is npu's one build-time parameter (docs/spec/npu.md §2.4): 32
# (committed default, soc_1.md SOC1-19) or 64 (anticipated upgrade, NPU-15).
# `C` and `ACT_SRAM_BYTES` are spec-fixed, not build parameters.
# Sweep: make sim MOD=npu WS_WIDTH=64
WS_WIDTH ?= 32
export WS_WIDTH
COMPILE_ARGS += -GWS_WIDTH=$(WS_WIDTH)

include $(REPO_ROOT)/flow/sim.mk

# Workaround (not a flow/ fix -- flagged in the PR manifest instead, per
# /CLAUDE.md "flow-level defects are reported, not fixed"): this cocotb
# build's cocotb_tools/makefiles/Makefile.deprecations re-derives
# COCOTB_USER_COVERAGE := $(COVERAGE) whenever they differ, undoing
# flow/sim.mk's `export COCOTB_USER_COVERAGE :=` decoupling (the P0 finding
# in .claude/skills/dv-engineer/references/cocotb-2x-pitfalls.md) --
# COVERAGE=1 (HDL coverage) would otherwise make cocotb try to start
# *Python* user-coverage and hard-crash when the `coverage` package isn't
# installed. Re-clear it here, after flow/sim.mk's include chain has run.
export COCOTB_USER_COVERAGE :=
