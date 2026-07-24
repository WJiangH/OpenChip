# Roadmap

Milestones are strictly gated: a milestone is done when every item in its
Definition of Done is machine-verified (CI green), not when the code "looks done".

## M0 — Foundation & tracer bullet

Prove the *entire* pipeline end-to-end on a trivial design before building anything real.

- [ ] Repo skeleton, CLAUDE.md, agent role definitions (this commit)
- [ ] Toolchain pins in `flow/versions.mk`; contributor setup doc tested on clean machine
- [ ] CI: lint + sim + formal jobs green on GitHub Actions (OSS CAD Suite)
- [ ] **Tracer bullet:** a `blink` module (counter + strobe) goes spec → RTL →
      cocotb sim → SymbiYosys proof → Yosys synth → LibreLane GDS on sky130 →
      DRC/LVS clean → gate-level sim. Every stage wired into `make`.
- [ ] First agent dry-run: RTL agent and DV agent build `blink` from its spec
      independently; retro notes recorded in `docs/retro/M0.md`

**Exit test:** `make lint sim formal && make gds MOD=blink` succeeds from a fresh clone.

## M1 — Methodology template: UART16550-lite

One real peripheral built to full rigor, establishing the reusable per-module template.

- [ ] Spec: `docs/spec/uart.md` (registers, FIFO behavior, baud, interrupts)
- [ ] RTL by designer agent; testbench + Python golden model by DV agent (independent)
- [ ] ≥ 90% line/toggle coverage; randomized + directed tests
- [ ] Formal: Wishbone slave protocol compliance + FIFO never-overflow/underflow
- [ ] Synth + STA clean at 50 MHz sky130
- [ ] Retro: what agent friction occurred; template updates merged

**Exit test:** `make sim formal synth MOD=uart` green; coverage report ≥ gate.

## M2 — RV32I core, objectively compliant

- [ ] Spec: ISA subset (RV32I + Zicsr subset, machine mode, trap handling), pipeline notes
- [ ] Core RTL (3-stage; simplicity over IPC)
- [ ] DV: per-instruction unit tests + riscv-arch-test via RISCOF, Spike reference
- [ ] **100% arch-test signature match** — the milestone headline
- [ ] Formal: no-deadlock, register-file write-port exclusivity, PC alignment invariants

**Exit test:** `make compliance` reports 0 mismatches across the full RV32I suite.

## M3 — SoC-1 integration: it runs real software

- [ ] Spec: memory map, interconnect, boot flow (`docs/spec/soc_1.md`)
- [ ] Wishbone interconnect + SRAM + boot ROM + UART + GPIO + timer integration
- [ ] Firmware: crt0, linker script, minimal libc, `hello` app, CoreMark port
- [ ] Full-SoC cocotb sim: boot → UART golden log match; CoreMark completes,
      checksum verified; interrupt path exercised
- [ ] System coverage: every peripheral touched by firmware tests

**Exit test:** `make soc-sim` prints CoreMark result with valid checksum in CI.

## M4 — Physical: a signed-off GDSII

- [ ] LibreLane config for SoC-1 on sky130A; floorplan, pin order, SRAM strategy
      (DFFRAM or OpenRAM macro — ADR required)
- [ ] Timing closure ≥ 50 MHz (WNS ≥ 0, hold clean, max cap/slew clean)
- [ ] DRC = 0 (Magic + KLayout), LVS clean (Netgen), antenna clean
- [ ] **Gate-level sim with SDF re-runs M3 firmware and passes**
- [ ] Signoff summary committed to `pd/soc_1/SIGNOFF.md`

**Exit test:** `make gds MOD=soc_1 && make glsim MOD=soc_1` green from clean tree.

## M5 — v1.0: anyone can use it

- [ ] Docs pass: quick start, "build your own module with the agent fleet" tutorial
- [ ] One-command bring-up of the agent fleet on a fresh module spec
- [ ] Reproducibility audit: fresh-machine clone-to-GDS run documented
- [ ] Community scaffolding: CONTRIBUTING.md, issue templates, module wishlist
- [ ] **Optional but desired:** SoC-1 (or a subset) submitted to a Tiny Tapeout
      shuttle (sky130 TTSKY26x / IHP TTIHP26x) — real silicon in 2027

## Beyond (v2 candidates)

- Second PDK (IHP SG13G2) fully supported; second core (RV32IMC)
- A small ML accelerator as reference design 2 (the Kimi K3 territory)
- Agent-authored module generator library; FPGA (openFPGALoader/F4PGA) bring-up path
- Coverage-driven agent loop: agents propose tests from coverage holes automatically
