# OpenChip

**An open-source, end-to-end silicon platform driven by collaborating AI agents — from architecture spec to a proven-working chip, using zero proprietary EDA tools and zero physical hardware.**

In early 2026, Moonshot's Kimi K3 designed a working accelerator in 48 hours using only open-source tools — no Cadence, no Synopsys. That was a one-shot demo. **OpenChip's goal is to turn that capability into a reproducible, community-owned platform**: anyone can clone this repo, launch the agent fleet, and take a chip from a markdown spec to a signed-off GDSII layout that is *proven to run real software* — entirely in simulation.

## What "end-to-end" means here

![OpenChip end-to-end framework](docs/images/architecture.svg)

Every stage is a machine-checkable quality gate, and the same AI-agent loop drives every stage: generate artifacts → run the tools → read the diagnostics → the gates decide. An agent's work is accepted only when the tools say so — never because the agent says so.

## The stack (100% open source, no hardware required)

| Stage | Tool | Why |
|---|---|---|
| HDL | SystemVerilog (synthesizable, Yosys-safe subset) | Largest LLM training corpus → best agent performance; first-class tool support |
| Lint | Verilator `--lint-only`, Verible | Fast, strict, machine-readable diagnostics |
| Simulation | **Verilator** (primary), Icarus (fallback) | Fastest open-source simulator; compiles RTL to C++ |
| Testbench | **cocotb** (Python) | Agents write Python well; rich randomization + coverage |
| Formal | **SymbiYosys** (Yosys SMT) | Bounded model check + k-induction for protocol proofs |
| ISA compliance | **riscv-arch-test + RISCOF**, Spike as golden model | *Objective* third-party proof the core is correct |
| Synthesis | **Yosys** | The open-source synthesis standard |
| Timing | **OpenSTA** | Static timing signoff |
| RTL → GDSII | **LibreLane** (ex-OpenLane 2) on OpenROAD | The maintained community flow as of 2026 |
| PDK | **SkyWater sky130** (primary), IHP SG13G2 (target 2) | Open PDKs with active Tiny Tapeout shuttles |
| Signoff | Magic / KLayout (DRC), Netgen (LVS) | Standard open signoff |
| Real silicon (optional) | **Tiny Tapeout** shuttle (sky130 & IHP, running through 2026) | < $300 to hold your chip |

One-command environment: [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build) (Yosys + Verilator + Icarus + SymbiYosys + GTKWave in a single pinned tarball) + LibreLane via Docker/Nix + xPack RISC-V GCC. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Reference design: OpenChip SoC-1

The platform is design-agnostic; **SoC-1** is the first design built *by* the platform to prove it:

- RV32I core (3-stage), Wishbone B4 interconnect
- SRAM, UART, GPIO, 64-bit timer
- Boots from embedded ROM, runs compiled C firmware
- Small enough for a Tiny Tapeout tile

**Definition of "the chip works" (no hand-waving):**

1. Lint-clean RTL, all flops reset, no latches
2. Per-module cocotb suites pass, ≥ 90% line + toggle coverage
3. Bus protocol and control logic formally proven (SymbiYosys)
4. **100% of riscv-arch-test passes with instruction-by-instruction comparison against Spike**
5. Full-SoC simulation boots firmware and prints over UART; CoreMark completes with the correct checksum
6. Timing closure at 50 MHz in sky130; DRC and LVS clean
7. Gate-level simulation (post-layout netlist + SDF) re-runs the same firmware and passes

## Built by agents, verified by tools

Development is done by a fleet of specialized AI agents mirroring a real silicon team — architect, RTL designers, DV engineers, formal engineer, firmware engineer, backend engineer — orchestrated through git worktrees, pull requests, and CI quality gates.

The two iron rules that make agent-built silicon trustworthy:

1. **Design/verification independence** — the agent that writes the RTL never writes its testbench; both work from the spec. Expected values come from the spec and golden models, never from observing the RTL.
2. **Tools are the arbiter** — no agent-asserted correctness. Merges happen only when lint, sim, coverage, formal, STA, DRC, and LVS gates are green in CI.

Full model: [docs/AGENTS.md](docs/AGENTS.md) · Verification strategy: [docs/VERIFICATION.md](docs/VERIFICATION.md) · Milestones: [docs/ROADMAP.md](docs/ROADMAP.md)

## Repository layout

```
docs/spec/   Specifications — the single source of truth
rtl/         SystemVerilog RTL, one directory per module
verif/       cocotb testbenches (independent from rtl/ authorship)
formal/      SymbiYosys jobs + SVA properties
sw/          Firmware: crt0, linker scripts, tests, CoreMark
syn/         Yosys synthesis + OpenSTA scripts
pd/          LibreLane configs, floorplans, signoff reports
flow/        Shared make fragments (lint/sim/formal/synth)
AGENTS.md    The agent constitution — iron rules, role index, conventions
.agents/     Role method files (skills), canonical and CLI-agnostic
```

## Any coding agent, same rules

OpenChip is not tied to one AI tool. `AGENTS.md` is the constitution and
indexes the nine role method files in `.agents/skills/`; `CLAUDE.md` and
`GEMINI.md` are one-line pointers to it. Claude Code, Codex, Gemini, Grok,
Cursor, Copilot and OpenCode therefore all start from the identical rules,
boundaries and role skills.

```bash
make agents        # which coding-agent CLIs are installed here
make agents-sync   # mirror .agents/skills into each CLI's skills directory
```

## Quick start

```bash
# 1. Toolchain (macOS/Linux) — one tarball, everything pinned
#    https://github.com/YosysHQ/oss-cad-suite-build/releases
export PATH="$HOME/oss-cad-suite/bin:$PATH"

# 2. Check the flow
make lint      # Verilator lint over all RTL
make sim       # all cocotb unit suites
make formal    # all SymbiYosys proofs

# 3. Physical design (Docker required)
make gds MOD=soc_1
```

## Status

🚧 **M0 — Foundation.** Repo skeleton, toolchain, CI, and agent framework. See [docs/ROADMAP.md](docs/ROADMAP.md).

## License

[Apache-2.0](LICENSE). Specs, RTL, testbenches, firmware, and flow are all free to use, modify, and manufacture.
