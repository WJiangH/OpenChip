# ADR 0001 — Core stack: SV subset, Verilator+cocotb, SymbiYosys, LibreLane, sky130

Status: accepted · Date: 2026-07-22

## Context
The platform must be operable end-to-end by AI agents with zero proprietary
tools and zero hardware, reproducibly, by anyone. Agents iterate against tool
diagnostics, so every stage needs machine-readable pass/fail output and a large
enough public corpus that LLMs are fluent in it.

## Decision
- **HDL:** synthesizable SystemVerilog, restricted to the subset Yosys reads
  natively (no interfaces/classes in synth code). Escape hatch if ever needed:
  yosys-slang or sv2v — requires a new ADR.
- **Sim:** Verilator primary (speed: full-SoC firmware in CI), Icarus fallback;
  testbenches in cocotb (Python) for agent fluency + simulator portability.
- **Formal:** SymbiYosys (BMC + induction).
- **Compliance anchor:** riscv-arch-test via RISCOF with Spike as reference.
- **RTL→GDSII:** LibreLane 3.x (the 2026 continuation of OpenLane 2) over
  OpenROAD; PDK sky130A primary (sky130_fd_sc_hd), IHP SG13G2 second target.
- **Bus:** Wishbone B4 pipelined (simplest open on-chip bus with wide open-source
  precedent; AXI-Lite bridges possible later).
- **Reset:** synchronous, active-low, all flops reset — one convention everywhere.
- **Env:** OSS CAD Suite pinned tarball + LibreLane Docker + xPack RISC-V GCC,
  pins in flow/versions.mk.

## Consequences
- (+) Every stage emits parseable diagnostics agents can iterate on; largest
  possible corpus match for RTL generation; one-tarball contributor setup.
- (+) Same flow reaches real silicon via Tiny Tapeout shuttles (sky130 & IHP active in 2026).
- (−) Yosys SV subset forbids some modern SV; conventions in CLAUDE.md enforce it.
- (−) Verilator is 2-state/cycle-based; X-propagation blind spots are covered by
  formal x-prop checks and an Icarus smoke lane.
- (−) Wishbone (not AXI) trades industry familiarity for simplicity and formal
  tractability at this scale.
