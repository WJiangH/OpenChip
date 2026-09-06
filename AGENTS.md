# AGENTS.md — Rules for all agents working in this repo

OpenChip is an end-to-end open-source silicon platform built by collaborating AI agents.
Read this file fully before touching anything. These rules are non-negotiable.

This file is the constitution for **every** coding agent — Claude Code, Codex,
Gemini, Grok, Cursor, Copilot, OpenCode. `CLAUDE.md` and `GEMINI.md` are
one-line pointers to it; no rule lives only in a vendor-specific file.

## Find your role first

Before your first edit, read the method file of the role you are acting as.
Each is short by design; load its `references/` entries only when the task
needs them.

| Role | `.agents/skills/<role>/SKILL.md` | Writes to | Never touches |
|---|---|---|---|
| Chief architect | `chief-architect` | `docs/spec/`, `docs/adr/`, `workloads/`, `explore/` | `hw/`, `sw/`, `sim/` |
| Verification architect | `verif-architect` | `hw/dv/` (vplan, golden models, DV infra) | `hw/rtl/` |
| DV engineer | `dv-engineer` | `hw/dv/` | `hw/rtl/` |
| RTL engineer | `rtl-engineer` | `hw/rtl/` | `hw/dv/` |
| Formal engineer | `formal-engineer` | `hw/formal/` | `hw/dv/`, `hw/rtl/` |
| Software engineer | `sw-engineer` | `sw/` | `hw/rtl/`, `hw/dv/` |
| Model engineer | `model-engineer` | `sim/` | `hw/rtl/`, `hw/dv/` |
| Backend engineer | `backend-engineer` | `hw/syn/`, `hw/pd/` | `hw/rtl/` logic |
| Integrator | `integrator` | reviews, `evidence/`, skill curation | all product code |

If no role was assigned to you, you are the orchestrator: name the role the
task belongs to, then act as that role — one role per work item.

`.agents/skills/` holds the only copy. `make agents-sync` mirrors it into each
CLI's own skills directory (`.claude/skills/`, `.grok/skills/`, …) so the same
nine methods are auto-discovered whichever agent you run — edit the canonical
file, never a mirror. `make agents` lists the CLIs installed on this machine.

## The Iron Rules

1. **The spec is the single source of truth.** Everything derives from `docs/spec/`.
   If the spec is ambiguous or wrong, STOP and escalate to the architect role /
   the human maintainer — never silently "fix" behavior in RTL or testbench.

2. **Design/DV independence.** The agent (or session) that writes a module's RTL
   must never write or modify that module's testbench, and vice versa.
   - RTL work writes only under `hw/rtl/` (+ its formal constraints under `hw/formal/` are OK).
   - DV work writes only under `hw/dv/` and derives expected values from
     `docs/spec/` and golden models — **never** from reading the RTL implementation.
   - If a test fails, the DV agent files a bug report (GitHub issue or
     `hw/dv/<mod>/BUGS.md`); it does not patch the RTL. The RTL agent fixes it.

3. **Tools are the arbiter.** Work is done only when the machine says so:
   lint clean → sim green → coverage met → formal proven → timing met → DRC/LVS clean.
   Never claim success without pasting the actual tool output summary.

4. **One module per branch.** Branch names: `rtl/<mod>`, `dv/<mod>`, `formal/<mod>`,
   `pd/<top>`, `sw/<feature>`. Agents work in separate git worktrees and merge via PR.

5. **Never weaken a gate to make it pass.** Do not lower coverage thresholds, waive
   lint rules, loosen timing constraints, or delete failing tests without an
   explicit human-approved note in the PR description.

## Commands

```bash
make lint                # Verilator --lint-only + Verible over all hw/rtl/
make sim MOD=<mod>       # cocotb suite for one module (omit MOD for all)
make formal MOD=<mod>    # SymbiYosys proof for one module
make synth MOD=<mod>     # Yosys synth + OpenSTA report
make gds  MOD=<top>      # LibreLane RTL→GDSII (Docker)
make sw                  # build RISC-V firmware (requires riscv-none-elf-gcc)
make clean
```

## RTL conventions (Yosys-safe SystemVerilog subset)

- One module per file; filename == module name; lowercase `snake_case` everywhere.
- `` `default_nettype none `` at top of every file, `` `default_nettype wire `` at bottom.
- Synchronous, active-low reset named `rst_n`; every flop resets. Clock named `clk`.
- `always_ff` / `always_comb` only — no plain `always`, no latches, no `initial`
  (except in testbench/formal code), no delays, no tri-state on internal logic.
- Stay inside the Yosys-supported SV subset: no classes, no interfaces in
  synthesizable code, no unpacked-struct ports across the synthesis boundary.
- On-chip bus is set per design family by ADR: the soc-1 / legacy NPU line uses
  Wishbone B4 pipelined (ADR-0001, prefix `wb_`); `llm-soc-v1` uses AXI4 / AXI4-Lite
  per ADR-0004 and `docs/spec/llm-soc-v1/axi.md` (prefixes `axi_` / `axil_`,
  signal names as the ICD lists them, lowercase). Never mix the two in one top.
- Module I/O: `i_` inputs, `o_` outputs (bus ports keep their bus prefix instead).
- Imported third-party IP lives under `hw/ip/<name>/` byte-identical to its pinned
  upstream commit, with `PROVENANCE.md` (URL, commit, sha256, license). The house
  style rules above do not apply inside `hw/ip/`; they apply in full to every
  adapter/wrapper in `hw/rtl/`. Strict-lint findings on imported IP are recorded,
  never silenced; a per-file lint scope for `hw/ip/` is a flow-owner decision
  documented in the PR, not an RTL-agent waiver.

## Verification conventions

- cocotb testbenches in `hw/dv/<mod>/`, one `Makefile` including `flow/sim.mk`.
- Golden/reference models live in `hw/dv/common/models/` as plain Python;
  they must cite the spec section they implement in a docstring.
- Every test suite ends by writing coverage; the gate is ≥ 90% line + toggle
  (thresholds live in `flow/gates.mk` — never edit them to pass, see Iron Rule 5).
- The RISC-V core is additionally verified by riscv-arch-test/RISCOF against
  Spike — architectural compliance is not negotiable.

## Commit signature convention

Every agent commits its own deliverables with its role signature as the git
author, format `<role>-agent-<Model><Version>-<effort>`:

```
git commit --author="dv-agent-Sonnet5-high <dv-engineer@agents.openchip>" ...
```

The model/effort in the signature is what the session actually ran on — no
honorary upgrades. One role's deliverables per commit; don't mix roles.

## Working notes

- Everything you need is inside this repo — never scan the filesystem outside it.
- Flow-level defects you discover (Makefile, flow/, CI) are reported, not fixed:
  work around inside your own directories and flag it; the orchestrator owns flow/.

## When you finish a task

1. Run the relevant `make` gates locally and include the summary lines in your report.
2. Open a PR whose description IS the deliverable manifest
   (.github/PULL_REQUEST_TEMPLATE.md): artifacts, gate numbers, spec refs,
   open items — key facts only, no narrative. The manifest is the
   traceability record; one that doesn't match the diff is a false report.
3. Report honestly: failing gates, skipped checks, and open questions go in the
   manifest — surfacing a failure is rewarded, hiding one is a protocol breach.
4. End with two lists, one line per item, no narration:
   - Friction: tool surprises, workarounds, deprecations.
   - Skill candidates: anything that would have changed how you STARTED this
     task. Format: `<target references/ file> — <delta>`. Nominate only —
     the integrator gates what enters the library.
