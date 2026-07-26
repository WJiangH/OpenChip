# Shared cocotb simulation fragment.
# Include from verif/<mod>/Makefile after setting:
#   TOPLEVEL         (DUT module name)
#   MODULE           (python test module, e.g. test_<mod>)
#   VERILOG_SOURCES  (paths to RTL, typically $(REPO_ROOT)/rtl/<mod>/*.sv)

REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)

# Project venv (cocotb) and OSS CAD Suite take PATH precedence
export PATH := $(REPO_ROOT)/.venv/bin:$(HOME)/tools/oss-cad-suite/bin:$(PATH)

SIM ?= verilator
TOPLEVEL_LANG ?= verilog
WAVES ?= 1

ifeq ($(SIM),verilator)
  EXTRA_ARGS += --timing -Wno-fatal --trace --trace-structs
  # oss-cad-suite verilator ships an empty CFG_CXXFLAGS_STD, so no -std= flag
  # reaches the host compiler and the build fails; force it here (P0 finding)
  COMPILE_ARGS += -CFLAGS -std=gnu++17
  ifeq ($(COVERAGE),1)
    EXTRA_ARGS += --coverage
  endif
endif

# COVERAGE=1 means HDL (line/toggle) coverage only. GNU Make auto-exports
# command-line vars, and cocotb 2.x reads COVERAGE as "collect Python coverage"
# and crashes without the coverage package — decouple explicitly (P0 finding).
export COCOTB_USER_COVERAGE :=

# Reproducible randomization: make sim SEED=1234 replays a failure exactly.
ifneq ($(SEED),)
  export COCOTB_RANDOM_SEED := $(SEED)
endif

# Filter to one test: make sim TEST=test_reset_values
ifneq ($(TEST),)
  export COCOTB_TEST_FILTER := $(TEST)
endif

export PYTHONPATH := $(REPO_ROOT)/hw/dv/common:$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
