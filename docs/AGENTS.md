# The Agent Organization

OpenChip is developed by a fleet of specialized AI agents modeled on a real
silicon team. This document defines the roles, their boundaries, and the
coordination protocol. The role definitions used by Claude Code live in
`.claude/agents/`.

## Why multiple agents (not one big prompt)

1. **Independence where it matters.** In industry, design and DV are separate
   teams *because shared assumptions hide bugs*. Two agents with separate
   contexts, both reading only the spec, reproduce that safeguard. A single
   agent verifying its own RTL will test its misunderstanding, not the spec.
2. **Focused context.** Timing closure and testbench architecture and ISA
   semantics don't fit one context window well. Specialists stay sharp.
3. **Parallel throughput.** Modules are independent until integration;
   N designer/DV pairs work N branches concurrently.

## Roles

| Role | Writes to | Must never touch | Key gates it owns |
|---|---|---|---|
| **Architect** | `docs/spec/`, `docs/adr/` | rtl/, verif/ | Spec completeness, ADRs |
| **RTL Designer** (per module) | `rtl/<mod>/` | `verif/` | lint, synthesizability |
| **DV Engineer** (per module) | `verif/<mod>/`, `verif/common/` | `rtl/` | sim green, coverage ≥ 90% |
| **Formal Engineer** | `formal/` | `verif/` (sim tb) | SymbiYosys proofs |
| **Firmware Engineer** | `sw/` | rtl/, verif/ | firmware builds & runs in SoC sim |
| **Backend Engineer** | `syn/`, `pd/` | rtl/ logic (may flag issues) | timing, DRC, LVS, GL-sim |
| **Reviewer / Integrator** | PR reviews, merges | (writes nothing) | spec conformance, iron rules |
| **Orchestrator** (main session) | task assignment | — | milestone progress |

Boundary enforcement is social + CI: a PR from a `rtl/<mod>` branch that touches
`verif/` fails the boundary check in CI.

## Coordination protocol

```
Architect writes/updates spec  ──►  docs/spec/<unit>.md   (human-reviewed PR)
                                          │
              ┌───────────────────────────┼──────────────────────────┐
              ▼                           ▼                          ▼
   RTL Designer (worktree,       DV Engineer (worktree,     Formal Engineer
   branch rtl/<mod>)             branch dv/<mod>)           (branch formal/<mod>)
   reads spec only               reads spec only            reads spec + RTL interface
              │                           │                          │
              └────────────► PR + CI quality gates ◄─────────────────┘
                                          │
                          Reviewer agent + human maintainer
                                          │
                                        main
```

- **Task queue:** GitHub Issues, labeled `role:rtl`, `role:dv`, `role:formal`,
  `role:sw`, `role:pd`, `mod:<name>`, `milestone:M<n>`. The orchestrator files
  and assigns; any contributor (human or agent) can pick up an unassigned issue.
- **Workspace:** every agent works in its own git worktree on its own branch.
  No two agents share a branch.
- **Bug loop:** DV finds a failure → files issue (repro command + expected-per-spec
  vs observed) → RTL agent fixes on its branch → DV re-runs. DV never patches RTL;
  RTL never edits tests. If spec itself is wrong → escalate to Architect.
- **Escalation:** any agent blocked > 2 iterations on the same gate escalates to
  the orchestrator with a written summary rather than thrashing.

## Quality gates (CI-enforced, definitions in flow/gates.mk)

| Gate | Tool | Threshold |
|---|---|---|
| lint | Verilator --lint-only, Verible | zero warnings (waivers need human sign-off) |
| unit sim | cocotb + Verilator | all tests pass |
| coverage | verilator --coverage | ≥ 90% line + toggle per module |
| formal | SymbiYosys | all listed properties pass (BMC depth per module) |
| ISA compliance | RISCOF + Spike | 100% signature match |
| SoC sim | cocotb system tb | firmware boots, UART golden log match, CoreMark checksum |
| synth | Yosys | no inferred latches, no $assert failures |
| timing | OpenSTA / LibreLane | WNS ≥ 0 at 50 MHz sky130 |
| signoff | Magic/KLayout + Netgen | DRC = 0, LVS clean |
| GL-sim | Verilator/Icarus + SDF | same firmware passes on post-layout netlist |

## Working agreements

- Reports quote tool output; "it should work" is not a status.
- Every PR description: what changed, spec sections implemented/tested,
  gate results, open questions.
- Humans are maintainers: they review spec changes, approve waivers, and merge.
  Agents propose; the repo's history is the record of who decided what.
