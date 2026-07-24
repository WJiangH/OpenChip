# Shared cocotb simulation fragment.
# Include from verif/<mod>/Makefile after setting:
#   TOPLEVEL         (DUT module name)
#   MODULE           (python test module, e.g. test_<mod>)
#   VERILOG_SOURCES  (paths to RTL, typically $(REPO_ROOT)/rtl/<mod>/*.sv)

REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)

SIM ?= verilator
TOPLEVEL_LANG ?= verilog
WAVES ?= 1

ifeq ($(SIM),verilator)
  EXTRA_ARGS += --timing -Wno-fatal --trace --trace-structs
  ifeq ($(COVERAGE),1)
    EXTRA_ARGS += --coverage
  endif
endif

# Reproducible randomization: make sim SEED=1234 replays a failure exactly.
ifneq ($(SEED),)
  export RANDOM_SEED := $(SEED)
endif

# Filter to one test: make sim TEST=test_reset_values
ifneq ($(TEST),)
  export TESTCASE := $(TEST)
endif

export PYTHONPATH := $(REPO_ROOT)/hw/dv/common:$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
