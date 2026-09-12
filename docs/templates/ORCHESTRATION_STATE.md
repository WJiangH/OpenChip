# Project orchestration state

Private working template for the [orchestrator method](../../.agents/skills/orchestrator/SKILL.md).
Copy into the approved local store; populate from the agreed goal and evidence.
This is a manual state contract, not an implemented schema validator/scheduler.
Use links to existing ledgers/receipts instead of copying their measurements.

## Agreement and authority

- Project / repository / state revision / writer / updated time: <values>.
- Agreed long-term goal and evidence of agreement: <objective; local decision
  reference and date; unresolved parts explicitly UNKNOWN>.
- Acceptance baseline: <requirement/spec/workload revisions, milestone/profile
  scope, measurable criteria and governing signoff records>.
- Authorized work and publication: <allowed actions/artifacts/destinations,
  granting authority and reference; explicit exclusions; no secrets here>.
- Separately controlled decisions: <merge/main push, tapeout submission,
  expenditure or other boundaries; NOT_AUTHORIZED unless supported by a grant>.
- Resource limits: <compute/time/cost/concurrency bounds and stop conditions;
  unknown is not unlimited permission>.
- Capability/configuration inventory: <available dispatch/runtime/tools,
  verified access without credential values; requested models/efforts by task
  class, permitted alternatives and reason; last verified time>.
- State/receipt locations and access boundaries: <paths; public/private;
  instructed scope versus actual enforced permissions>.

## Requirements and milestone dependencies

| ID / artifact or milestone | Acceptance / candidate/profile | Requires IDs and exact edge condition | Owner / independent reviewer / approver | Signoff record / state | Next action |
|---|---|---|---|---|---|
| <ID> | <criterion with units; source revision> | <accepted claim, artifact interface or other prerequisite; none if root> | <names/authority> | <immutable record; OPEN/BLOCKED/ACCEPTED/REOPENED> | <owner and action> |

Edges must be acyclic and references resolvable; identify missing or ambiguous
dependencies. A completed task does not automatically satisfy a milestone or
authorize downstream work. Record acceptance of the exact required claim.

## Assignments

| Work item / requirement IDs | Author and role / independent reviewer | Requested model/effort / observed identity | Branch/worktree / candidate / PR | Worker or session handle / host | Task status / last verified / evidence | Blocker / next action |
|---|---|---|---|---|---|---|
| <ID; bounded scope and read/write limits> | <different owners and contexts> | <requested; UNKNOWN/none/UNKNOWN unless evidenced> | <refs> | <durable handle; UNKNOWN if unavailable> | <status; timestamp; receipt> | <owner; unblock condition> |

Task status: OPEN (not started), RUNNING, WAITING (known condition), BLOCKED
(missing prerequisite), or DELIVERED (scoped author delivery completed).
These are workflow states, separate from signoff acceptance. Record assignment
transfer explicitly; the state index has one designated writer at a time.

For every assignment, retain task ambiguity/complexity, failure impact,
verification ease/cost and context needs; the selected configured model/effort
and rationale; intended independent reviewer; and bounded continuation or
escalation triggers. On return, retain acceptance/quality, confirmed misses or
false alarms, repair cycles, root versus human intervention, measured
time/token/cost and unknowns. Compare observations only when difficulty,
context, skill version and evidence scope are comparable; they do not establish
a model ranking or maturity claim. If changing configuration, record supported
switching capability or its limitation, reconcile the live worker/jobs/candidate,
and preserve author ownership, context handoff and independent review.

Record PR lifecycle separately: Draft / in review / changes requested / approved /
merged / terminal closed, with exact head and reason. After a terminal decision,
record cleanup owner, active/dependency/dirty/evidence checks, retained artifacts,
retired branch/worktree or explicit blocker. Delivery is not integration.

## Active jobs and receipts

| Work item / run / attempt | Durable job handle and identity | Inputs / binary / candidate | Progress and last observation | Completion and semantic result | Receipt / hashes | Resume or retry condition |
|---|---|---|---|---|---|---|
| <IDs> | <scheduler ID+host; or PID+start+command+cwd+nonce> | <manifest hashes> | <units; time; live/stale/unknown> | <exit and checker verdict; UNKNOWN without receipt> | <immutable paths/hashes> | <exact next inspection; owner; duplicate-execution check> |

Receipts identify planned/selected/executed/skipped/result-checked scope, actual
checker output and tool/environment versions. Logs growing or a process existing
do not prove progress or success. Link full signoff evidence rather than copy
an unaudited summary into an acceptance cell.

## Decisions, changes and checkpoint

- Decision history: <append dated source-bound acceptance, authority and
  assignment-transfer references; retain superseded decisions>.
- Change impact: <old/new candidates; affected dependencies/reopened records;
  required reruns and independently reviewed evidence carry-forward>.
- Review/friction: <real findings and resolutions; separately assigned skill
  candidates; no fabricated failures or model rankings>.
- Current outcome and evidence: <one concise paragraph; last verified time>.
- Blockers and pending reviews: <owners, exact missing condition and next step>.
- Resume first: <small ordered set of observations/actions, durable handles,
  existing workers to reuse and publication/resource limits>.
- Waiting/checkpoint: <why; trigger; actual registered scheduler ID or NONE;
  no promise of autonomous wakeup without one>.
