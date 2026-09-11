# OpenChip — top-level flow entry points.
# Gate thresholds: flow/gates.mk. Tool pins: flow/versions.mk.

include flow/versions.mk
include flow/gates.mk

# Toolchain: project venv (cocotb) + OSS CAD Suite (pinned in versions.mk).
# Apple's GNU Make 3.81 ignores exported PATH when direct-exec'ing recipes
# (P0 finding), so recipes also prefix PATH explicitly via $(TOOLPATH).
TOOLPATH := $(CURDIR)/.venv/bin:$(HOME)/tools/oss-cad-suite/bin
export PATH := $(TOOLPATH):$(PATH)

MODULES  := $(sort $(notdir $(patsubst %/,%,$(dir $(wildcard hw/rtl/*/*.sv)))))
SIM_MODS := $(notdir $(patsubst %/Makefile,%,$(wildcard hw/dv/*/Makefile)))
SBY_MODS := $(notdir $(patsubst %.sby,%,$(wildcard hw/formal/*/*.sby)))
MOD      ?=

.PHONY: help framework-test attribution-validate attribution-validate-range contribution-report source-snapshot lint sim coverage-report formal synth compliance soc-sim gds glsim sw agents agents-sync clean print-oss-cad-suite-tag print-oss-cad-suite-linux-x64-sha256

help:
	@echo "OpenChip flow targets:"
	@echo "  make framework-test     framework Python + documentation + boundary checks"
	@echo "  make attribution-validate [ATTRIBUTION_SOURCE=<sha>]"
	@echo "  make attribution-validate-range ATTRIBUTION_BASE=<sha>"
	@echo "  make contribution-report [ATTRIBUTION_SOURCE=<ref>]"
	@echo "  make source-snapshot    package exact tracked HEAD with manifest/checksums"
	@echo "  make lint   [MOD=<m>]   Verilator --lint-only over hw/rtl/"
	@echo "  make sim    [MOD=<m>]   cocotb unit suites (COVERAGE=1, SEED=, TEST=)"
	@echo "  make coverage-report    diagnostic census of one existing Coverage-3 file"
	@echo "  make formal [MOD=<m>]   SymbiYosys proofs"
	@echo "  make synth   MOD=<m>    Yosys synthesis + OpenSTA"
	@echo "  make compliance         riscv-arch-test via RISCOF vs Spike (not implemented)"
	@echo "  make soc-sim [APP=<a>]  full-SoC firmware simulation (not implemented)"
	@echo "  make gds     MOD=<top>  LibreLane RTL->GDSII via Docker"
	@echo "  make glsim   MOD=<top>  gate-level sim with SDF (not implemented)"
	@echo "  make sw                 build RISC-V firmware"
	@echo "  make agents             list coding-agent CLIs installed here"
	@echo "  make agents-sync        mirror .agents/skills into every CLI (--all)"

# --- Framework checks and delivery -----------------------------------------
framework-test:
	@python3 -m unittest discover -s scripts/tests -v
	@PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s hw/ip/coralnpu -p 'test_*.py' -v
	@bash flow/tests/test_check_boundaries.sh
	@python3 scripts/check_docs.py

ATTRIBUTION_SOURCE ?= HEAD
ATTRIBUTION_BASE ?=
ATTRIBUTION_REPORT ?= contribution-report.json
attribution-validate:
	@python3 scripts/agent_attribution.py validate-commit --commit "$(ATTRIBUTION_SOURCE)"

attribution-validate-range:
	@test -n "$(ATTRIBUTION_BASE)" || { echo "usage: make attribution-validate-range ATTRIBUTION_BASE=<sha> [ATTRIBUTION_SOURCE=<sha>]"; exit 1; }
	@python3 scripts/agent_attribution.py validate-range --base "$(ATTRIBUTION_BASE)" --head "$(ATTRIBUTION_SOURCE)"

contribution-report:
	@python3 scripts/agent_attribution.py report --source "$(ATTRIBUTION_SOURCE)" --json-output "$(ATTRIBUTION_REPORT)"

SOURCE_SHA ?= $(shell git rev-parse HEAD)
SOURCE_REPOSITORY ?= local/OpenChip
SOURCE_RUN_ID ?= 0
SOURCE_RUN_ATTEMPT ?= 0
SOURCE_SNAPSHOT_DIR ?= _ci_artifacts/source-snapshot
source-snapshot:
	@python3 scripts/package_source_snapshot.py \
		--source-sha "$(SOURCE_SHA)" \
		--repository "$(SOURCE_REPOSITORY)" \
		--run-id "$(SOURCE_RUN_ID)" \
		--run-attempt "$(SOURCE_RUN_ATTEMPT)" \
		--output-dir "$(SOURCE_SNAPSHOT_DIR)"

print-oss-cad-suite-tag:
	@printf '%s\n' "$(OSS_CAD_SUITE_TAG)"

print-oss-cad-suite-linux-x64-sha256:
	@printf '%s\n' "$(OSS_CAD_SUITE_LINUX_X64_SHA256)"

# --- Gate 1: lint -----------------------------------------------------------
LINT_MODS = $(if $(MOD),$(MOD),$(MODULES))
lint:
ifeq ($(strip $(MODULES)),)
	@echo "lint: no modules in hw/rtl/ yet — gate passes vacuously"
else
	@for m in $(LINT_MODS); do \
		echo "== lint $$m"; \
		PATH="$(TOOLPATH):$$PATH" verilator --lint-only -Wall --timing -Ihw/rtl -Ihw/rtl/$$m hw/rtl/$$m/*.sv || exit 1; \
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

# Diagnostic only: this reports raw instrumented points and never closes a gate.
COVERAGE_DATA ?= coverage.dat
COVERAGE_REPORT ?= coverage-report.json
coverage-report:
	@python3 scripts/coverage_report.py "$(COVERAGE_DATA)" --output "$(COVERAGE_REPORT)"

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

# --- Gate 5: ISA compliance --------------------------------------------
compliance:
	@echo "compliance: not implemented; see docs/ROADMAP.md"; exit 1

# --- Gate 6: full-SoC firmware sim -------------------------------------
soc-sim:
	@echo "soc-sim: not implemented; see docs/ROADMAP.md"; exit 1

# --- Gate: RTL->GDSII (M0 tracer bullet / M4) -------------------------------
gds:
	@test -n "$(MOD)" || { echo "usage: make gds MOD=<top>"; exit 1; }
	@test -f hw/pd/$(MOD)/config.yaml || { echo "gds: hw/pd/$(MOD)/config.yaml not found (P0 task)"; exit 1; }
	docker run --rm -v $(PWD):/work -w /work \
		-v $(HOME)/.ciel:/root/.ciel $(LIBRELANE_IMAGE) \
		librelane --pdk-root /root/.ciel hw/pd/$(MOD)/config.yaml

# --- Gate 9: gate-level sim --------------------------------------------
glsim:
	@echo "glsim: not implemented; see docs/ROADMAP.md"; exit 1

# --- Firmware ----------------------------------------------------------
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
