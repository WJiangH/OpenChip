# OpenChip — top-level flow entry points.
# Every target is a quality gate. Thresholds: flow/gates.mk. Tool pins: flow/versions.mk.

include flow/versions.mk
include flow/gates.mk

# Toolchain: project venv (cocotb) + OSS CAD Suite (pinned in versions.mk).
# Apple's GNU Make 3.81 ignores exported PATH when direct-exec'ing recipes
# (P0 finding), so recipes also prefix PATH explicitly via $(TOOLPATH).
TOOLPATH := $(CURDIR)/.venv/bin:$(HOME)/tools/oss-cad-suite/bin:$(CURDIR)/.toolcache/xpack-riscv-none-elf-gcc-$(RISCV_GCC_VERSION)/bin
export PATH := $(TOOLPATH):$(PATH)

MODULES  := $(sort $(notdir $(patsubst %/,%,$(dir $(wildcard hw/rtl/*/*.sv)))))
# Imported IP (hw/ip/<name>/): library search dirs + per-file Verilator waivers.
# The waiver scope is a flow-owner decision (AGENTS.md "Imported third-party IP").
IP_DIRS    := $(patsubst %/,%,$(wildcard hw/ip/*/))
IP_INCS    := $(addprefix -I,$(IP_DIRS))
IP_WAIVERS := $(wildcard hw/ip/*/*.vlt)
# Module directories double as Verilator library/include dirs so an integration
# top can resolve hw/rtl/<m>/<m>.sv and `include files without shim copies.
RTL_DIRS   := $(sort $(patsubst %/,%,$(dir $(wildcard hw/rtl/*/*.sv))))
RTL_LIBS   := $(addprefix -y ,$(RTL_DIRS))
RTL_INCS   := $(addprefix -I,$(RTL_DIRS))
SIM_MODS := $(notdir $(patsubst %/Makefile,%,$(wildcard hw/dv/*/Makefile)))
SBY_MODS := $(notdir $(patsubst %.sby,%,$(wildcard hw/formal/*/*.sby)))
MOD      ?=

.PHONY: help lint sim formal synth compliance soc-sim gds glsim sw agents agents-sync clean

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
	@echo "  make agents             list coding-agent CLIs installed here"
	@echo "  make agents-sync        mirror .agents/skills into every CLI (--all)"

# --- Gate 1: lint -----------------------------------------------------------
LINT_MODS = $(if $(MOD),$(MOD),$(MODULES))
lint:
ifeq ($(strip $(MODULES)),)
	@echo "lint: no modules in hw/rtl/ yet — gate passes vacuously"
else
	@for m in $(LINT_MODS); do \
		echo "== lint $$m"; \
		PATH="$(TOOLPATH):$$PATH" verilator --lint-only -Wall --timing --timescale 1ns/1ps -Ihw/rtl -Ihw/rtl/$$m $(RTL_INCS) $(RTL_LIBS) $(IP_INCS) $(IP_WAIVERS) hw/rtl/$$m/*.sv || exit 1; \
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
		PATH="$(TOOLPATH):$$PATH" $(MAKE) -C hw/dv/$$m || exit 1; \
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
		PATH="$(TOOLPATH):$$PATH" sby -f hw/formal/$$m/$$m.sby || exit 1; \
	done
endif

# --- Gate 7/8: synthesis + STA (implemented in M0 tracer bullet) ------------
synth:
	@test -n "$(MOD)" || { echo "usage: make synth MOD=<module>"; exit 1; }
	@test -f hw/syn/$(MOD).ys || { echo "synth: hw/syn/$(MOD).ys not found (P0 task)"; exit 1; }
	PATH="$(TOOLPATH):$$PATH" yosys -c hw/syn/$(MOD).ys

# --- Gate 5: ISA compliance (M2) --------------------------------------------
compliance:
	@echo "compliance: RISCOF flow lands in M2 (docs/ROADMAP.md)"; exit 1

# --- Gate 6: full-SoC firmware sim (M3) -------------------------------------
SOC_TOP ?= llm_soc_top
soc-sim:
	@test -f sw/rom/rom.bin || { echo "soc-sim: sw/rom/rom.bin missing — run 'make sw' first (SW-B1 owns the ROM image)"; exit 1; }
	@test -f hw/rtl/rom/gen_rom.py || { echo "soc-sim: hw/rtl/rom/gen_rom.py missing (MEMORY item)"; exit 1; }
	@python3 hw/rtl/rom/gen_rom.py -o hw/rtl/rom/rom_data.svh sw/rom/rom.bin
	@echo "soc-sim: rom_data.svh regenerated from sw/rom/rom.bin ($$(shasum -a 256 sw/rom/rom.bin | cut -c1-16)…)"
	@test -f hw/dv/$(SOC_TOP)/Makefile || { echo "soc-sim: hw/dv/$(SOC_TOP)/Makefile not delivered yet (V-B1, DV side) — not a pass"; exit 1; }
	PATH="$(TOOLPATH):$$PATH" $(MAKE) -C hw/dv/$(SOC_TOP) $(if $(APP),APP=$(APP),)

# --- Gate: RTL->GDSII (M0 tracer bullet / M4) -------------------------------
gds:
	@test -n "$(MOD)" || { echo "usage: make gds MOD=<top>"; exit 1; }
	@test -f hw/pd/$(MOD)/config.yaml || { echo "gds: hw/pd/$(MOD)/config.yaml not found (P0 task)"; exit 1; }
	docker run --rm -v $(PWD):/work -w /work \
		-v $(HOME)/.ciel:/root/.ciel $(LIBRELANE_IMAGE) \
		librelane --pdk-root /root/.ciel hw/pd/$(MOD)/config.yaml

# --- Gate 9: gate-level sim (M4) --------------------------------------------
glsim:
	@echo "glsim: post-layout netlist sim lands in M4 (docs/ROADMAP.md)"; exit 1

# --- Firmware (M3) ----------------------------------------------------------
sw:
	@test -f sw/Makefile && $(MAKE) -C sw || echo "sw: firmware tree lands in M3"

# --- Agent workspace --------------------------------------------------------
# AGENTS.md + .agents/skills/ are CLI-agnostic; these expose them per CLI.
agents:
	@tools/agents.sh scan

agents-sync:
	@tools/agents.sh sync --all

clean:
	rm -rf obj_dir sim_build
	find . -name '*.vcd' -o -name '*.fst' -o -name 'results.xml' | xargs rm -f
	@echo "clean: done (pd/*/runs are preserved; delete manually)"
