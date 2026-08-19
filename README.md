<div align="center">

# OpenChip

### Silicon designed by AI agents. Proven by tools, never by claims.

An end-to-end open-source chip platform — from architecture spec to signed-off GDSII —
built with **zero proprietary EDA tools** and **zero physical hardware**.

[![CI](https://github.com/WJiangH/OpenChip/actions/workflows/ci.yml/badge.svg)](https://github.com/WJiangH/OpenChip/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-888780)](LICENSE)
[![EDA](https://img.shields.io/badge/EDA-100%25%20open%20source-1D9E75)](#the-stack)
[![PDK](https://img.shields.io/badge/PDK-sky130A-D85A30)](#the-stack)
[![Hardware required](https://img.shields.io/badge/hardware%20required-none-534AB7)](#what-is-already-proven)
[![Agents](https://img.shields.io/badge/agent%20roles-9-534AB7)](AGENTS.md)
[![Any CLI](https://img.shields.io/badge/works%20with-Claude%20%C2%B7%20Codex%20%C2%B7%20Gemini%20%C2%B7%20Grok-888780)](#any-coding-agent-same-rules)

</div>

---

In early 2026, Moonshot's Kimi K3 designed a working accelerator in 48 hours using only
open-source tools — no Cadence, no Synopsys. That was a one-shot demo.
**OpenChip turns it into a reproducible, community-owned platform**: clone the repo,
launch the agent fleet, and take a chip from a markdown spec to a GDSII layout that is
*proven to run real software* — entirely in simulation.

## What "end-to-end" means here

![OpenChip end-to-end framework](docs/images/architecture.svg)

Every stage is a machine-checkable quality gate, and the same AI-agent loop drives every
stage: generate artifacts → run the tools → read the diagnostics → the gates decide.
An agent's work is accepted only when the tools say so — never because the agent says so.

## What is already proven

`blink` — a deliberately trivial module — was taken through **every stage of the flow**
to prove the pipeline itself, from a cold machine in one day. Real numbers, all
re-runnable, all quoted from tool output:

| Gate | Result | Headline numbers |
|---|---|---|
| Lint | ✅ | Verilator 5.051, `--lint-only -Wall --timing`, 0 warnings |
| Sim + coverage | ✅ | 7/7 cocotb tests, parameter sweep 28/28; **line 100%, toggle 100%** (gate: 90%) |
| Formal | ✅ | 10 asserts + 6 covers, k-induction over N ∈ {1,2,3}; **mutation-tested with 6 mutants, all caught** |
| Synthesis | ✅ | Yosys 0.67 → 106 cells / 1242.44 µm², 26 flops, 0 latches |
| GDSII signoff | ✅ | LibreLane 3.0.5, 80/80 steps. **DRC 0 · LVS match · antenna 0**; setup WNS +11.382 ns, hold WNS +0.1069 ns @ 50 MHz |

Full package with every authoritative artifact: [evidence/blink/](evidence/blink/README.md) ·
Post-mortem: [docs/retro/P0.md](docs/retro/P0.md)

> Gate-level simulation is the one rung still open (M4). We say so rather than round up —
> an honest capability boundary is part of the deliverable.

## Built by a fleet, not by a prompt

Nine specialist roles mirror a real silicon team, each with its own method file, its own
context, and hard directory boundaries. They open issues at each other, review each
other's pull requests, and merge through CI. The git history is the receipt:

```console
$ git log --format="%an" | grep -- "-agent-" | sort | uniq -c | sort -rn
   8 chief-architect-agent-Sonnet5-medium
   2 verif-architect-agent-Sonnet5-medium
   1 verif-architect-agent-Sonnet5-high
   1 sw-agent-Sonnet5-medium
   1 rtl-agent-Sonnet5-medium
   1 rtl-agent-Sonnet5-high
   1 integrator-agent-Sonnet5-high
   1 formal-agent-Opus5-high
   1 dv-agent-Sonnet5-medium
   1 dv-agent-Sonnet5-high
   1 chief-architect-agent-Sonnet5-high
   1 chief-architect-agent-Opus5-high
   1 backend-agent-Opus5-high
```

Every role signs its own commits with the model and effort it actually ran on — no
honorary upgrades. Seven of these landed through reviewed pull requests.

Two iron rules make agent-built silicon trustworthy:

1. **Design/DV independence** — the agent that writes the RTL never writes its testbench.
   Both derive from the spec; expected values come from golden models, never from
   observing the RTL. CI enforces the directory boundaries on every PR.
2. **Tools are the arbiter** — no agent-asserted correctness. Merges happen only when
   lint, sim, coverage, formal, STA, DRC and LVS are green.

**It works — and we have the scar to prove it.** While verifying the NPU, the DV agent
found that *no CPU-visible path could ever write a nonzero activation byte from cold
reset* — the accelerator could only ever output zeros. It did not patch the RTL to hide
it. It filed the finding back at the architect as a **specification** defect, with a
reproducing probe and a coverage number. That backward-propagation loop, running with no
human in it, is the whole thesis of this repo.

Full model: [AGENTS.md](AGENTS.md) · [docs/AGENTS.md](docs/AGENTS.md) ·
Verification strategy: [docs/VERIFICATION.md](docs/VERIFICATION.md)

## Any coding agent, same rules

OpenChip is not tied to one AI tool. `AGENTS.md` is the constitution and indexes the nine
role method files in `.agents/skills/`; `CLAUDE.md` and `GEMINI.md` are one-line pointers
to it. Claude Code, Codex, Gemini, Grok, Cursor, Copilot and OpenCode all start from
identical rules, boundaries and role skills.

```bash
make agents        # which coding-agent CLIs are installed here
make agents-sync   # mirror .agents/skills into each CLI's skills directory
```

## The stack

| Stage | Tool | Why |
|---|---|---|
| HDL | SystemVerilog (Yosys-safe subset) | Largest training corpus → best agent performance |
| Lint | Verilator `--lint-only`, Verible | Strict, machine-readable diagnostics |
| Simulation | **Verilator** (primary), Icarus | Fastest open-source simulator |
| Testbench | **cocotb** (Python) | Agents write Python well; rich randomization + coverage |
| Formal | **SymbiYosys** | BMC + k-induction for protocol proofs |
| ISA compliance | **riscv-arch-test + RISCOF** vs Spike | *Third-party* proof the core is correct |
| Synthesis / STA | **Yosys** · **OpenSTA** | The open-source standard |
| RTL → GDSII | **LibreLane** on OpenROAD | The maintained community flow |
| PDK | **SkyWater sky130A** | Open PDK, real signoff decks |
| Signoff | Magic / KLayout (DRC) · Netgen (LVS) | Standard open signoff |

One-command environment: [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build)
+ LibreLane via Docker + xPack RISC-V GCC. Everything pinned in `flow/versions.mk`.
Design rationale: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Quick start

```bash
export PATH="$HOME/tools/oss-cad-suite/bin:$PATH"

make lint            # Verilator lint over all RTL
make sim             # all cocotb unit suites
make formal          # all SymbiYosys proofs
make gds MOD=blink   # RTL → GDSII on sky130 (Docker)
```

## Repository layout

```
docs/spec/   Specifications — the single source of truth
docs/adr/    Architecture decision records
hw/rtl/      SystemVerilog RTL, one directory per module
hw/dv/       cocotb testbenches + golden models (independent authorship)
hw/formal/   SymbiYosys jobs + SVA properties
hw/syn/  hw/pd/   Synthesis + STA · LibreLane configs and signoff
sw/  sim/    Firmware and compiler · bit-accurate ISS and performance models
workloads/   Workload profiling — what the silicon must actually run
explore/     Design space exploration and cost models
evidence/    The per-design evidence package
flow/        Shared make fragments + the gate thresholds
AGENTS.md    The agent constitution — iron rules, role index, conventions
.agents/     Role method files, canonical and CLI-agnostic
```

## Status

**M0 complete** — toolchain, CI, agent fleet, and the `blink` tracer bullet all the way to
a DRC/LVS-clean GDSII. Now building the first real design: an edge-AI SoC around a
streaming int8 NPU, specified from a profiled workload rather than a guess.
Milestones: [docs/ROADMAP.md](docs/ROADMAP.md)

## License

[Apache-2.0](LICENSE). Specs, RTL, testbenches, firmware and flow are all free to use,
modify, and manufacture.
