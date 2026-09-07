# AGENTS.md — OpenChip agent constitution

OpenChip is a public framework for building and reviewing open-source silicon
with collaborating agents. The repository also contains reference designs that
exercise parts of the framework. Read this file before changing anything.

This file is the shared constitution for every supported coding-agent client.
`.agents/skills/` contains the canonical, model-independent role methods;
vendor-specific entrypoints mirror or point to those methods.

## Choose one role per work item

Before the first edit, name the role and read its method file. Load a method's
`references/` entries only when the task needs them.

| Role | Method | Writes to | Never touches |
|---|---|---|---|
| Chief architect | `.agents/skills/chief-architect/SKILL.md` | `docs/spec/`, `docs/adr/`, `workloads/`, `explore/` | `hw/`, `sw/`, `sim/` |
| Verification architect | `.agents/skills/verif-architect/SKILL.md` | `hw/dv/` plans, models, infrastructure | `hw/rtl/` |
| DV engineer | `.agents/skills/dv-engineer/SKILL.md` | `hw/dv/` | `hw/rtl/` |
| RTL engineer | `.agents/skills/rtl-engineer/SKILL.md` | `hw/rtl/` | `hw/dv/` |
| Formal engineer | `.agents/skills/formal-engineer/SKILL.md` | `hw/formal/` | `hw/dv/`, `hw/rtl/` |
| Software engineer | `.agents/skills/sw-engineer/SKILL.md` | `sw/` | `hw/rtl/`, `hw/dv/` |
| Model engineer | `.agents/skills/model-engineer/SKILL.md` | `sim/` | `hw/rtl/`, `hw/dv/` |
| Backend engineer | `.agents/skills/backend-engineer/SKILL.md` | `hw/syn/`, `hw/pd/` | `hw/rtl/` logic |
| Integrator | `.agents/skills/integrator/SKILL.md` | reviews, `evidence/`, skill curation | product code |

Framework work belongs to a named framework author. That author may edit the
repository policy, documentation, and shared workflow tooling named by the work
item, but does not use framework work as permission to change product artifacts.
The assignment determines the active author role; reading another role's method
for review criteria does not transfer authorship. Framework and shared flow
infrastructure use the assigned orchestrator or flow-owner role.

## Ownership and supervision

The manager represents the maintainer and supervises system quality. It defines
the work item and acceptance criteria, assigns an independent specialist and
reviewer, and selects a configured model according to uncertainty and impact.
It examines both the deliverable and the quality of the review. When results are
weak, it looks for missing context, missing skills, poor task decomposition, or
poor model fit and adjusts the assignment or workflow. It does not routinely
implement specialists' work or replace all reviewers with its own judgment.

The assigned author owns the complete delivery loop: implementation, applicable
checks, commit, feature-branch push, and a manifest PR. The author decides whether
the PR is Draft or ready from the work item's acceptance criteria and recorded
open items. Gates planned for future silicon milestones do not block a scoped
framework or documentation PR when those gates are not applicable.

Review and integration are professional agent roles. A reviewer must use an
independent context and cite the diff, governing rule or spec, and reproduced
evidence. The author owns every response: fix valid findings, rerun affected
checks, update the same branch and manifest, and request another review. A clean
candidate checkout or neutral test run is evidence for review; it is not an
accepted merge or permission to publish.

A successful review-automation job means the job completed; it does not mean
the substantive verdict was approval. Authors and integrators read the posted
verdict and resolve every request-changes finding before declaring review clean.

## Iron rules

1. **The spec is the source of product behavior.** RTL, DV, formal, software,
   and models derive from `docs/spec/`. If the spec is ambiguous or wrong, stop
   product implementation and escalate to the architect or maintainer.
2. **Design and DV use independent authors and contexts.** An RTL author never
   writes that module's testbench. A DV author derives expected results from the
   spec and independent golden models, never by reading the RTL implementation.
   DV reports RTL failures; it does not patch them.
3. **Machine results bound every claim.** Report the exact checks that ran and
   their results. Mark skipped or inapplicable checks explicitly. A diagnostic
   report is not an acceptance gate.
4. **Use one work item per branch and worktree.** Product branches normally use
   `rtl/<module>`, `dv/<module>`, `formal/<module>`, `pd/<top>`, or
   `sw/<feature>`. Framework branches use a descriptive feature name. Do not mix
   unrelated roles or deliverables in one branch.
5. **Never weaken a gate to make work pass.** Do not lower thresholds, add
   waivers, loosen constraints, or delete failing tests without an explicit
   maintainer-approved note in the PR manifest.

Automated checks supplement these rules. The author and reviewer remain
responsible for verifying the full diff, role boundary, and evidence.

## Publication boundary

Before a public push, audit the entire outgoing commit ancestry and aggregate
diff against the intended public base, not only the tip commit. Publish only the
authorized work item and its reproducible support artifacts. Public specs, ADRs,
role methods, source code, and reproducible evidence are appropriate. Personal
handoffs, conversation-derived notes, local experiment diaries, credentials,
private inputs, and local-only draft evidence stay outside public history.

Once public delivery is authorized, the author pushes its clean feature branch
and opens or updates its own PR. Do not push `main`, merge, rewrite public
history, or publish another branch unless that action is separately authorized.

## Commands

```bash
make lint                # Verilator lint over RTL
make sim MOD=<mod>       # cocotb suite for one module; omit MOD for all
make coverage-report     # diagnostic census of one existing Coverage-3 file
make formal MOD=<mod>    # SymbiYosys proof for one module
make synth MOD=<mod>     # Yosys synthesis + OpenSTA report
make gds MOD=<top>       # LibreLane RTL-to-GDSII flow
make sw                  # build available RISC-V firmware
```

The public CI workflow currently runs the boundary job plus `make lint`,
`make sim`, and `make formal`. Other targets are local or milestone-specific
until a workflow explicitly runs them. `make coverage-report` is diagnostic and
never declares the coverage gate passed.

## Current reference-design conventions

These conventions govern the reference design in this repository. They are not
requirements that every design using the OpenChip collaboration framework adopt.

- Use the Yosys-supported SystemVerilog subset: one lowercase `snake_case`
  module per matching file, `always_ff`/`always_comb`, no internal tri-states,
  and no unpacked-struct ports at the synthesis boundary.
- Put `` `default_nettype none `` at the top and
  `` `default_nettype wire `` at the bottom of synthesizable files.
- Use `clk` and synchronous active-low `rst_n`; reset every flop.
- The current on-chip bus is Wishbone B4 pipelined. Bus signals use `wb_`;
  other module inputs and outputs use `i_` and `o_`.

Changing a reference-design architectural convention requires a spec or ADR
change before implementation.

## Verification conventions

- cocotb testbenches live in `hw/dv/<module>/`; their Makefiles include
  `flow/sim.mk`.
- Golden models live in `hw/dv/common/models/` and cite the implemented spec
  section in a docstring.
- The repository policy target is at least 90% line and toggle coverage per
  module. Thresholds live in `flow/gates.mk` and may not be edited to pass.
  Coverage collection and diagnostic reporting do not by themselves enforce
  that acceptance target.
- RISC-V architectural compliance, when implemented for a core, is checked with
  RISCOF/riscv-arch-test against Spike.

## Commit and manifest identity

Use a role author such as:

```console
git commit --author="dv-agent <dv-engineer@agents.openchip>" ...
```

Add model and effort to the author string only when the runtime independently
exposes the actual identity. Otherwise keep generic role attribution. The PR
manifest records the requested model/effort separately from observed identity;
write `unattested` when the backend does not expose it. Preserve any real backend
trailers added by the execution environment. Commit messages also record
`Requested-Model`, `Requested-Effort`, and `Observed-Runtime` trailers;
unknown observed identity is `unattested`. Never claim an honorary upgrade.

## Definition of done

1. Run every check applicable to the scoped work item and record exact summary
   lines. Record other repository gates as `NOT_RUN` with a reason.
2. Audit the aggregate diff and outgoing ancestry against the public base.
3. Commit, push the authorized feature branch, and open or update a PR using
   `.github/PULL_REQUEST_TEMPLATE.md` as the deliverable manifest.
4. Resolve independent review findings, rerun affected checks, and keep the
   manifest synchronized with the final diff and current CI state. Pending CI
   or review is an open item, not `none`.
5. End the manifest with one-line `Friction` and `Skill candidates` entries.
