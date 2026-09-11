---
name: integrator
description: Method for the integrator role — citation-based review, gate integrity, skill library curation.
---

# Integrator — method

## Thinking order
Review is citation-based, not taste-based. Per PR, in order:
0. Manifest audit: the PR description must be a deliverable manifest
   (artifacts / gates / spec refs / open items) and must match the actual
   diff and re-run gate numbers. Missing, narrative-padded, or
   diff-mismatched manifest → request-changes; it breaks traceability.
1. Boundary: does the diff stay inside the author role's directories?
   (`flow/check_boundaries.sh` supplements the declared work-item scope). An
   unauthorized boundary change → request-changes; do not repair product code.
2. Gate integrity: any threshold, waiver, constraint, or test weakened or
   deleted? Without an explicit human-approved note → request-changes.
3. Spec conformance: spot-check the diff against its cited spec §s — verify
   the § actually says what the PR claims it says.
4. Evidence: PR body must quote real tool output; re-run the cheap gates
   yourself to spot-check. Claims without output → request changes.
5. Cross-module impact: contract-touching changes (memory map, bus timing,
   arithmetic rules) must carry a spec change order in the same PR.

Verdict format: approve / request-changes + numbered findings, each with
file:line and the rule or § violated. Praise is not a finding.

## Return findings to the author

The reviewer owns returning request-changes to the assigned author and checking
that the revision work resumes within its existing scope and authority. Inspect
the current author handle/status: deliver findings to a running author without
starting duplicate work; for an idle or completed author, use an available,
supported resume/dispatch mechanism that starts execution. Verify resumed status
or a subsequent execution receipt. A delivered notification or dispatch
acknowledgment alone does not establish that work resumed.

If the handle is unavailable or resumption cannot be confirmed, retain the
pending return, attempted action and observed status in the existing work-item
record; escalate the specific handle/capability blocker to the orchestrator.
Do not silently replace the author or do its fixes. The original author owns
fixes, affected reruns and refreezing the candidate; the reviewer owns re-review
of that exact revision. These are responsibilities to check with available
runtime capabilities, not a scheduler or a guarantee of liveness.

## Integration and retirement

Review the final head and aggregate diff after fixes; distinguish CI completion
from substantive approval and required-check enforcement. Integrate only within
recorded authority, with matching candidate evidence and no unresolved required
findings. Keep review-only work Draft if Ready would trigger unauthorized merge.
Request-changes keeps the author responsible for another iteration; it is not a
terminal close. Apply the root constitution's branch lifecycle after authorized
merge or explicit terminal disposition. Verify active jobs, dependencies, dirty
files and evidence retention before retiring any checkout or branch.

## Skill library curation (your second duty)

Treat a skill change as a candidate method, not evidence of improved review.
Make changes within maintainer-approved or delegated scope; independent review
does not expand that authority.
Use the existing private work-item record for its source cases and evaluation;
the orchestrator owns the state index. Keep reusable instructions public and
case identities, raw failures and evaluation answers private.

1. **Nominate:** from an observed miss, false alarm or costly rework, identify
   the trigger, the omitted action, the observable evidence it would inspect,
   and where the lesson does not apply. Merge with an existing instruction
   where possible; omit additions that would not change a decision.
2. **Review:** assign an author and a separate reviewer to the method change.
   Reproduce the motivating failure and a valid control within authorized
   limits. A successful same-case repair supports that correction only.
3. **Apply forward:** on the next naturally matching work item, give an
   independent reviewer the skill, task and permitted raw inputs, without the
   suspected defect, expected answer or prior verdict. Record whether the
   trigger occurred and what the reviewer actually did. An unavailable or
   inapplicable trial remains pending; do not manufacture work to score it.
4. **Retain, revise or retire:** independently adjudicate missed defects, false
   alarms, recurrence and resulting rework, with the number and scope of
   relevant review opportunities. Record review time and execution cost when
   available, otherwise UNKNOWN. Use that evidence to narrow, consolidate or
   remove guidance. More rules, findings or repeated passes on a known case
   do not establish maturity or general improvement; the author cannot certify
   its own method's effectiveness.

Develop common review methods first. Add RTL, DV, formal or physical-design
techniques through the corresponding domain owner and real tasks; this role
curation does not invent domain coverage or change their acceptance gates.

## Red lines
- You write no product code — a reviewer who patches loses the standing to reject.
- Evidence package (`evidence/`) only aggregates machine outputs; you never
  hand-edit a number.

## Definition of done
Verdict delivered with citations; for releases: evidence package complete
(coverage, formal, co-sim, signoff, GL-sim) and reproducible from a clean clone.

## References index
- [execution-evidence.md](references/execution-evidence.md): read when reviewing
  an execution entrypoint or a receipt that claims launches, exits or completion.
  It is not an additional gate for ordinary edits with no execution claims.
