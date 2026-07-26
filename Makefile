# OpenChip — top-level flow entry points.
# Every target is a quality gate. Thresholds: flow/gates.mk. Tool pins: flow/versions.mk.

include flow/versions.mk
include flow/gates.mk

# Toolchain: project venv (cocotb) + OSS CAD Suite (pinned in versions.mk)
export PATH := $(CURDIR)/.venv/bin:$(HOME)/tools/oss-cad-suite/bin:$(PATH)

MODULES  := $(sort $(notdir $(patsubst %/,%,$(dir $(wildcard hw/rtl/*/*.sv)))))
SIM_MODS := $(notdir $(patsubst %/Makefile,%,$(wildcard hw/dv/*/Makefile)))
SBY_MODS := $(notdir $(patsubst %.sby,%,$(wildcard hw/formal/*/*.sby)))
MOD      ?=

.PHONY: help lint sim formal synth compliance soc-sim gds glsim sw clean

help:
	@echo "OpenChip flow targets:"
	@echo "  make lint   [MOD=<m>]   Verilator --lint-only over rtl/"
	@echo "  make sim    [MOD=<m>]   cocotb unit suites (COVERAGE=1, SEED=, TEST=)"
	@echo "  make formal [MOD=<m>]   SymbiYosys proofs"
	@echo "  make synth   MOD=<m>    Yosys synthesis + OpenSTA (M0)"
	@echo "  make compliance         riscv-arch-test via RISCOF vs Spike (M2)"
	@echo "  make soc-sim [APP=<a>]  full-SoC firmware simulation (M3)"
	@echo "  make gds     MOD=<top>  LibreLane RTL->GDSII via Docker (M0/M4)"
	@echo "  make glsim   MOD=<top>  gate-level sim with SDF (M4)"
	@echo "  make sw                 build RISC-V firmware (M3)"

# --- Gate 1: lint -----------------------------------------------------------
LINT_MODS = $(if $(MOD),$(MOD),$(MODULES))
lint:
ifeq ($(strip $(MODULES)),)
	@echo "lint: no modules in hw/rtl/ yet — gate passes vacuously"
else
	@for m in $(LINT_MODS); do \
		echo "== lint $$m"; \
		verilator --lint-only -Wall --timing -Ihw/rtl -Ihw/rtl/$$m hw/rtl/$$m/*.sv || exit 1; \
	done
	@echo "lint: PASS ($(LINT_MODS))"
endif

# --- Gate 2/3: unit sim + coverage -----------------------------------------
RUN_SIM_MODS = $(if $(MOD),$(MOD),$(SIM_MODS))
sim:
ifeq ($(strip $(SIM_MODS)),)
	@echo "sim: no testbenches in hw/dv/ yet — gate passes vacuously"
else
	@for m in $(RUN_SIM_MODS); do \
		echo "== sim $$m"; \
		$(MAKE) -C hw/dv/$$m || exit 1; \
	done
endif

# --- Gate 4: formal ---------------------------------------------------------
RUN_SBY_MODS = $(if $(MOD),$(MOD),$(SBY_MODS))
formal:
ifeq ($(strip $(SBY_MODS)),)
	@echo "formal: no .sby jobs in hw/formal/ yet — gate passes vacuously"
else
	@for m in $(RUN_SBY_MODS); do \
		echo "== formal $$m"; \
		sby -f hw/formal/$$m/$$m.sby || exit 1; \
	done
endif

# --- Gate 7/8: synthesis + STA (implemented in M0 tracer bullet) ------------
synth:
	@test -n "$(MOD)" || { echo "usage: make synth MOD=<module>"; exit 1; }
	@test -f hw/syn/$(MOD).ys || { echo "synth: hw/syn/$(MOD).ys not found (P0 task)"; exit 1; }
	yosys -c hw/syn/$(MOD).ys

# --- Gate 5: ISA compliance (M2) --------------------------------------------
compliance:
	@echo "compliance: RISCOF flow lands in M2 (docs/ROADMAP.md)"; exit 1

# --- Gate 6: full-SoC firmware sim (M3) -------------------------------------
soc-sim:
	@echo "soc-sim: SoC testbench lands in M3 (docs/ROADMAP.md)"; exit 1

# --- Gate: RTL->GDSII (M0 tracer bullet / M4) -------------------------------
gds:
	@test -n "$(MOD)" || { echo "usage: make gds MOD=<top>"; exit 1; }
	@test -f hw/pd/$(MOD)/config.yaml || { echo "gds: hw/pd/$(MOD)/config.yaml not found (P0 task)"; exit 1; }
	docker run --rm -v $(PWD):/work -w /work $(LIBRELANE_IMAGE) \
		librelane hw/pd/$(MOD)/config.yaml

# --- Gate 9: gate-level sim (M4) --------------------------------------------
glsim:
	@echo "glsim: post-layout netlist sim lands in M4 (docs/ROADMAP.md)"; exit 1

# --- Firmware (M3) ----------------------------------------------------------
sw:
	@test -f sw/Makefile && $(MAKE) -C sw || echo "sw: firmware tree lands in M3"

clean:
	rm -rf obj_dir sim_build
	find . -name '*.vcd' -o -name '*.fst' -o -name 'results.xml' | xargs rm -f
	@echo "clean: done (pd/*/runs are preserved; delete manually)"
