# AGENTS.md — OpenChip agent constitution

OpenChip is a public framework for building and reviewing open-source silicon
with collaborating agents. The repository also contains reference designs that
exercise parts of the framework. Read this file before changing anything.

This file is the shared constitution for every supported coding-agent client.
`.agents/skills/` contains the canonical, model-independent role methods;
vendor-specific entrypoints mirror or point to those methods.

## Choose one role per work item

At the start of a project session, an explicit specialist assignment takes
precedence. Otherwise use the **orchestrator** role for project coordination:
read its method and the configured durable project state (default
`.local-designs/orchestration/STATE.md`), then reconcile actual Git, assignments,
jobs and receipts before dispatch. Resume the agreed goal within existing
authorization; a new conversation does not require agreeing to it again.
A standalone question does not require creating a project plan or state.

Before the first edit, name the role and read its method file. Load a method's
`references/` entries only when the task needs them.

| Role | Method | Writes to | Never touches |
|---|---|---|---|
| Orchestrator | `.agents/skills/orchestrator/SKILL.md` | approved project state; assigned framework policy/tooling | specialists' product artifacts and independent review |
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

The orchestrator is the manager representing the maintainer within delegated
authority; it is distinct from the independent integrator. It defines
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

## Documentation stewardship

The orchestrator stewards public documentation structure, navigation and shared
workflow guidance. This does not transfer semantic ownership: the chief
architect owns specifications and ADRs; verification specialists own testplans,
properties, golden models and coverage intent. Changes to those contracts require
their assigned author and independent review even when the file is under `docs/`.

Keep `docs/` a small set of stable framework references. Use `README.md` for
ordinary prose in engineering directories. Keep domain artifacts such as specs,
testplans, constraints, formal descriptions, register maps, IP/license notices,
role `SKILL.md` files and reproducible engineering reports where their tools and
owners need them. Do not add per-task summaries, phase diaries or duplicate
constitutions. Use the PR manifest and private durable state for delivery status.
Preserve evidence/source links and historical signoff when consolidating prose;
only reviewed dependency impact can carry forward or reopen a claim.

## Branch lifecycle

Start each bounded work item from fresh `origin/main` in a short-lived branch and
worktree. A dependent stack needs an explicit dependency and an ancestry audit
against both its stack base and public main. The author runs applicable checks,
commits with registered attribution, pushes the authorized branch and opens a
manifest PR. Independent review leads to fixes and re-review on that same PR.
**Request-changes is not terminal rejection.** A PR ends in authorized merge or
an explicit terminal close (for example superseded or withdrawn), with a recorded
reason and disposition of any useful work/evidence.

Keep the PR Draft until the required review and checks are satisfied and a Ready
transition stays within integration authority. The manager/integrator verifies
the actual final head, tested candidate, substantive approval and configured
required checks before authorized integration. Do not infer approval from a
successful bot job or change branch settings to bypass a hold.

After merge or terminal close, the assigned cleanup owner verifies remote PR
state and exact head, merge reachability (or recorded squash/rebase mapping),
active workers/jobs, dependent branches, dirty/untracked files and evidence
retention. Preserve anything still needed; retire worktrees and local/remote
branches only when these checks show they are unused and disposition is
recorded. Never force-delete a dirty worktree or abandon unpublished changes
because its PR is closed. Record cleanup or its blocker in existing state/PR,
not a new public Markdown report. Begin the next item from current main.

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

## Lifecycle signoff

Use [the silicon lifecycle](docs/SILICON_LIFECYCLE.md) to assign stage-specific
owners, independent reviewers, approvers and measurable criteria. Maintain
[scoped signoff records](docs/templates/SIGNOFF_RECORD.md) as development
progresses. Bind decisions to exact candidates and configurations; retain
historical acceptance and reopen affected claims after changes. Block readiness,
DV closure, subsystem/SoC acceptance, physical signoff and tapeout authorization
are separate decisions. Pending or missing evidence is not PASS. The records
are a manual process, not an implemented acceptance gate or access-control system.
Private design records remain outside public history.

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
make framework-test      # framework Python and boundary regression tests
make attribution-validate # validate one opted-in provenance commit
make contribution-report # report reachable Git and public work-item evidence
make source-snapshot     # exact tracked HEAD archive with manifest/checksums
make lint                # Verilator lint over RTL
make sim MOD=<mod>       # cocotb suite for one module; omit MOD for all
make coverage-report     # diagnostic census of one existing Coverage-3 file
make formal MOD=<mod>    # SymbiYosys proof for one module
make synth MOD=<mod>     # Yosys synthesis + OpenSTA report
make gds MOD=<top>       # LibreLane RTL-to-GDSII flow
make sw                  # build available RISC-V firmware
```

The public CI workflow runs the pull-request `boundaries` job, the `framework`
regression job, and the `gates` job for lint, simulation, and formal. Successful
main-branch `framework` and `gates` jobs produce an exact tracked-source artifact
for the tested commit. See [docs/CI_CD.md](docs/CI_CD.md) for triggers, pins,
artifacts, and reproduction. Other targets are local or milestone-specific until
a workflow explicitly runs them. `make coverage-report` is diagnostic and never
declares the coverage gate passed.

The checked-in GitHub Agents workflow supports mentions, issue-label role
dispatch, PR review, and maintainer-authorized clean integration for its
configured provider. Assignment and model selection remain orchestrator
decisions; the repository does not implement automatic cross-provider routing.

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
change before implementation. Imported IP may retain upstream coding, interface,
reset and toolchain conventions; document its pinned source and approved adapter
boundaries. Reference Yosys/Wishbone rules do not mandate rewriting upstream IP.

Independent contexts reduce shared mistakes; different vendors, sparse checkouts
and worktrees do not enforce read isolation. Record actual runtime permissions
when enforcement is required and disclose convention-only separation otherwise.

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

Agent identity, Git identity, and platform identity are separate. Prepare new
agent-authored commits with a registered author account. When the authenticated
publisher is different, select its verified account separately as the committer:

```console
python3 scripts/agent_attribution.py prepare <identity arguments> \
  --committer-account <publisher-account> --output /tmp/message.txt
git -c user.name=<account-login> -c user.email=<registered-email> \
  commit --author="ROLE_AGENT <REGISTERED_EMAIL>" -F /tmp/message.txt
python3 scripts/agent_attribution.py validate-commit --commit HEAD
```

The preparation command writes the complete `OpenChip-Provenance: v1` trailer
block and prints the separate author and committer identities selected from
`provenance/platform-accounts.json`. Use command-scoped Git configuration; do
not change a user's global settings. A registered email maps a commit identity
to a platform account but does not prove the historic pusher or agent runtime.
Use an agent account as primary author only when that agent owns the actual
deliverable; the authenticated account remains the committer and publisher.
Record requested model and effort separately from observed identity. Use
`UNKNOWN`, `Runtime-Attestation: none`, and `Runtime-Evidence: UNKNOWN` when the
runtime does not independently expose its identity. Do not fabricate an agent
account, provider, model, or attestation. See
[docs/AGENT_ATTRIBUTION.md](docs/AGENT_ATTRIBUTION.md).

## Definition of done

1. Run every check applicable to the scoped work item and record exact summary
   lines. Record other repository gates as `NOT_RUN` with a reason.
2. Audit the aggregate diff and outgoing ancestry against the public base.
3. Commit, push the authorized feature branch, and open or update a PR using
   `.github/PULL_REQUEST_TEMPLATE.md` as the deliverable manifest.
4. Resolve independent review findings, rerun affected checks, and keep the
   manifest synchronized with the final diff and current CI state. Pending CI
   or review is an open item, not `none`.
5. Track authorized integration or terminal close and safe branch/worktree
   cleanup; unresolved dependencies remain explicit blockers.
6. End the manifest with one-line `Friction` and `Skill candidates` entries.
