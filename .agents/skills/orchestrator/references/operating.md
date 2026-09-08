# Dispatch, review routing and retirement

Use the root constitution's ownership and branch lifecycle. This is a manual
operating contract for the capabilities actually available, not a scheduler.

## Dispatch one bounded dependency

Put the following in the existing task/dispatch record; avoid a new public
handoff file for each assignment:

| Field | Required content |
|---|---|
| Contract | Work-item/requirement IDs, exact spec/profile revisions, acceptance criteria, prerequisites and unresolved questions |
| Ownership | One author role, separate independent reviewer, approver and state writer; explicit transfer if replacing a worker |
| Inputs and scope | Pinned source/dependency identities, allowed reads/writes, forbidden artifacts, tool/access limitations and public/private boundary |
| Execution | Branch from current main (or approved dependency), worktree, requested model/effort, observed identity or UNKNOWN, commands, resource bounds and durable worker/job handles |
| Return | Changed artifacts, exact candidate, planned/selected/executed/skipped/checked scope, raw receipts and verdicts, open bugs/risks, applicable reruns, manifest PR and next action |

Freeze the independent DV context from the approved spec and golden-model
sources; do not copy implementation-derived answers. Sparse worktrees or another
provider do not enforce a clean room. Where enforcement matters, verify actual
permissions and inputs. Respect imported IP's native tools/conventions and
identify real versus surrogate implementations. When reusing a clone or cache,
distinguish available source objects from its checked-out revision and local
modifications: materialize the pinned upstream candidate separately and identify
adaptations instead of inheriting an unrelated working tree.

If a spec gap blocks behavior, route it to the architect before implementing the
affected behavior; continue only independent authorized work. Authors use the
registered provenance preparation workflow, not invented role email addresses.
An authorized public delivery includes the author's feature push and PR; a
private work item stays within its separately recorded boundary.

## Route a return by its evidence

| Finding | Next owner and disposition |
|---|---|
| Missing/ambiguous behavior or acceptance | Chief architect; reviewed clarification/change order with impacted specialist review before dependent implementation |
| Implementation defect | Original specialist author; reproduce, fix, rerun affected checks and obtain independent re-review |
| Cross-block disagreement | Integrator examines dependency/interface evidence; architect decides behavior changes; respective authors implement |
| Tool/flow defect | Assigned flow/framework author and independent reviewer; no quiet edits to baseline, thresholds or product code |
| Incomplete manifest or unsupported result | Author corrects receipts/status; request-changes until the actual criterion is evidenced |
| Missing capability, access, budget or independent context | Orchestrator records BLOCKED, owner and unblock condition; no silent model substitution or fabricated dispatch |

A tool's successful exit and a review job's completion are not substantive
approval. Read raw checker results and the review verdict. Missing evidence is
unverified; preserve explicit executed failures according to receipt semantics.
Evaluate actual friction and genuine defects, not planted bugs for agent ranking.
A skill improvement is its own bounded, independently reviewed framework change.

## Close the work item and retire its workspace

The author updates the same branch/PR through review and fixes. The authorized
integrator checks exact final head, tested candidate, required checks and
substantive approvals before merge. A terminal close instead needs a reason and
an explicit disposition of useful work; request-changes is still active work.

The cleanup owner then checks PR/head mapping, remote state, active workers and
jobs, dependent worktrees/branches, dirty/untracked files and retained evidence.
Record any squash/rebase mapping, preserved artifacts and remaining dependency.
Retire only unused branches/worktrees; do not force-delete to make an inventory
look clean. The author updates the final PR manifest after integration or terminal
close with the actual status, delivery/check receipts and cleanup outcome or
blocker; do not leave a completed item described as Draft/pending. Keep this
receipt in existing state/PR, and start the next item from
fresh main. One designated writer reconciles project-state changes; simultaneous
managers must agree ownership rather than overwrite each other's decisions.
