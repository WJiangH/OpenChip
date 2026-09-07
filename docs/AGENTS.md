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

The manager represents the maintainer. It defines acceptance criteria, decomposes
work, chooses specialists and configured models according to uncertainty and
impact, and checks the quality of both output and review. It corrects missing
skills, context, decomposition, or model fit. It normally does not implement the
specialist's deliverable or replace independent review.

Requested runtime settings and observed identity are separate facts. Record the
requested model and effort. Record an observed model only when the runtime
independently exposes it; otherwise use `unattested`. Role methods and acceptance
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
marks the PR ready when all applicable criteria are met. A future milestone's
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

- pull-request boundary script;
- `make lint`;
- `make sim`;
- `make formal`.

The checked-in GitHub Agents workflow also supports mentions, issue-label role
dispatch, PR review, and maintainer-authorized clean integration for its
configured provider. Assignment and model selection remain orchestrator
decisions; no automatic cross-provider scheduler is implemented.

Synthesis, STA, compliance, full-SoC simulation, GDS, and gate-level simulation
are local or milestone-specific until CI contains jobs for them. Coverage
collection may occur during simulation, but the diagnostic reporter documented
in [COVERAGE_REPORT.md](COVERAGE_REPORT.md) never evaluates the repository's 90%
coverage policy.
