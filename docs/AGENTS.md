# Agent collaboration model

OpenChip treats chip development as a chain of owned work items with independent
review. The roles mirror a silicon team, but their methods are independent of
any particular model provider or coding-agent client.

## Why use separate agents

Design and verification need separate contexts because a shared misunderstanding
can make a self-test agree with the wrong behavior. Specialist contexts also
keep architecture, RTL, DV, formal, software, modeling, and physical-design
tasks focused. Parallel work is useful only when every work item still has a
clear owner, branch, interface, and acceptance test.

The canonical role methods are under `.agents/skills/`. `AGENTS.md` defines
the common policy and directory boundaries.

## Roles and accountability

| Role | Primary responsibility | Product paths |
|---|---|---|
| Orchestrator | agreed goal, milestone dependencies, specialist/model assignment, progress and durable resume | approved project state; explicitly assigned framework work |
| Chief architect | specs, ADRs, design-space decisions | `docs/spec/`, `docs/adr/`, `workloads/`, `explore/` |
| Verification architect | vplan, independent golden models, DV infrastructure | `hw/dv/` |
| RTL engineer | synthesizable implementation from an approved spec | `hw/rtl/` |
| DV engineer | adversarial simulation and coverage evidence | `hw/dv/` |
| Formal engineer | properties and bounded/proven claims | `hw/formal/` |
| Software engineer | firmware, compiler, and runtime against the contract | `sw/` |
| Model engineer | bit-accurate and calibrated models | `sim/` |
| Backend engineer | synthesis, timing, layout, and signoff evidence | `hw/syn/`, `hw/pd/` |
| Integrator | independent review, evidence audit, and integration verdict | reviews, `evidence/` |

A framework author owns policy, public documentation, and shared workflow tooling
when those paths are explicitly assigned. Review and integration are specialist
roles with their own evidence standard; they are not administrative afterthoughts.
The assignment fixes the active author role. Reading another role's method to
apply its criteria does not change authorship. Shared flow infrastructure uses
the assigned orchestrator or flow-owner role.

The orchestrator is the manager representing the maintainer within delegated
authority. It defines acceptance criteria, decomposes
work, chooses specialists and configured models according to uncertainty and
impact, and checks the quality of both output and review. It corrects missing
skills, context, decomposition, or model fit. It normally does not implement the
specialist's deliverable or replace independent review.

## Start a session and resume a goal

An explicitly assigned specialist starts in its own role. Otherwise project
coordination defaults to the [orchestrator method](../.agents/skills/orchestrator/SKILL.md).
Read the root constitution, method and configured state entrypoint before
dispatch. The default `.local-designs/orchestration/STATE.md` is private and
ignored; initialize it from the [blank state template](templates/ORCHESTRATION_STATE.md)
when adopting the workflow. Record the agreed goal, authority, acceptance DAG,
assignments, requested runtimes, candidate/branch/worktree identities, durable
job handles and evidence, plus a short checkpoint with the next action.

On a new session, reconcile live Git/PR state, workers, jobs and final receipts
before relying on saved status or creating another worker. Keep existing
authorization and qualified signoff decisions; record unavailable tools/access
and continue unaffected work. State does not create a daemon, cross-provider
scheduler, enforced clean room or background notification. The integrator still
owns independent review; the orchestrator supervises the process and routes fixes
back to authors.

For activation on an older checkout, see the narrow
[local bootstrap](../.agents/skills/orchestrator/references/local-bootstrap.md).
It preserves the current branch and explicitly loads the constitution when a
local override takes discovery precedence. Validate startup in a fresh context;
a valid skill file alone does not prove that a client loaded it.

Requested runtime settings and observed identity are separate facts. Record the
requested model and effort. Record an observed model only when the runtime
independently exposes it; otherwise use `UNKNOWN` with no attestation. Git
author, Git committer, platform publisher, and agent runtime are also separate
facts; use public evidence for each mapping rather than inferring one from
another. Role methods and acceptance
criteria must not change merely because a different model executes them.

## Delivery and review loop

```text
maintainer criteria
        |
manager assigns author + independent reviewer
        |
author: isolated worktree -> implement -> check -> commit -> push -> manifest PR
        |
reviewer: boundary -> gate integrity -> spec/policy -> evidence -> impact
        |
author fixes findings, reruns checks, and updates the same PR
        |
manager audits output and review quality -> maintainer-controlled integration
```

The author owns delivery after public publication is authorized. It chooses Draft
while scoped acceptance criteria or known review findings remain unresolved, and
marks the PR ready when all applicable criteria are met and that transition
stays within the authorized workflow. Keep review-only delivery Draft when a
Ready PR would trigger integration that has not been authorized. A future milestone's
unimplemented chip gates do not block a framework-only change; the manifest marks
them `NOT_RUN` and explains why they are inapplicable.

Pending CI or independent review remains an explicit open item. The manifest is
updated as checks and reviews complete; `Open items: none` is reserved for a
ready deliverable with no known unresolved criterion.

A neutral candidate checkout and reproduced checks inform the verdict. They do
not make a merge accepted. Review findings cite a file and line plus the violated
rule or spec. The author, rather than the reviewer or manager, owns fixes and PR
updates.

Automation status and review verdict are separate evidence. A completed review
job can still post a request-changes verdict; authors and integrators must read
that verdict and resolve its findings before treating review as clean.

## Independence and escalation

- RTL and DV for one module use separate authors, contexts, branches, and
  worktrees. Both derive behavior from `docs/spec/`.
- A DV failure becomes a reproducible bug report with expected behavior, observed
  behavior, and a spec citation. DV does not patch RTL; RTL does not edit tests.
- A product ambiguity returns to the architect. A repeated tool failure is
  escalated with commands and output rather than hidden or worked around by
  weakening a gate.
- Each feature branch contains one authorized work item. Before pushing, the
  author and reviewer audit every outgoing commit and the aggregate diff against
  the public base.

The public boundary workflow currently invokes `flow/check_boundaries.sh` for
pull requests. That automation is supplemental: authors and reviewers must still
verify role ownership and full publication scope themselves.

## Public artifact policy

Public history may contain specs, ADRs, methods, source code, tests, and
reproducible evidence that supports a stated claim. Personal handoffs,
conversation-derived notes, local experiment diaries, credentials, private
inputs, and local-only drafts are not deliverables. A blanket ban on Markdown or
raw evidence would remove useful traceability, so publication is decided by
provenance, reproducibility, and relevance.

Authorized authors push only their clean feature branch and open or update its
manifest PR. Main-branch pushes, merges, history rewrites, and publication of
other branches remain maintainer-controlled actions unless separately authorized.

## Current automated checks

The public CI workflow runs these jobs:

- pull-request `boundaries` checks;
- `framework` Python and boundary regression tests;
- `gates` running `make lint`, `make sim`, and `make formal`.

The `framework` and `gates` jobs run on pull requests and main pushes. When both
pass on a main push, the same workflow uploads an exact tracked-source snapshot
for that tested commit. [CI_CD.md](CI_CD.md) documents its tool pins, provenance,
artifact contents, and reproduction steps. Job status is mechanical evidence;
the substantive reviewer verdict remains a separate readiness requirement.

The checked-in GitHub Agents workflow also supports mentions, issue-label role
dispatch, PR review, and maintainer-authorized clean integration for its
configured provider. Assignment and model selection remain orchestrator
decisions; no automatic cross-provider scheduler is implemented.

`scripts/agent_attribution.py` prepares and validates opted-in commit metadata
and reports reachable Git activity together with typed public work-item events.
The report keeps merge, implementation, review, validation, and integration
activity separate. It reports missing evidence as `UNKNOWN` and does not compute
an ability score. See [AGENT_ATTRIBUTION.md](AGENT_ATTRIBUTION.md).

Synthesis, STA, compliance, full-SoC simulation, GDS, and gate-level simulation
are local or milestone-specific until CI contains jobs for them. Coverage
collection may occur during simulation, but the diagnostic reporter documented
in [COVERAGE_REPORT.md](COVERAGE_REPORT.md) never evaluates the repository's 90%
coverage policy.
