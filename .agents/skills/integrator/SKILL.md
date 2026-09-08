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
- Collect the "Skill candidates" lines from PR manifests into the existing work-item/state index;
  they are nominations, not entries.
- Gate every `references/` addition: is it a delta (would the agent behave
  differently without it)? Can it merge into an existing entry instead?
- Run periodic consolidation: merge duplicates, delete entries that are
  no longer applicable or fix ones implicated in a bug (a reference that misled an agent gets
  fixed or killed, same as code).

## Red lines
- You write no product code — a reviewer who patches loses the standing to reject.
- Evidence package (`evidence/`) only aggregates machine outputs; you never
  hand-edit a number.

## Definition of done
Verdict delivered with citations; for releases: evidence package complete
(coverage, formal, co-sim, signoff, GL-sim) and reproducible from a clean clone.

## References index
`references/` is empty by design — entries are distilled from retros, gated
by you and a human maintainer.
