# Scoped signoff record

Copy into the adopting project's approved evidence location. This is a manual
template governed by [Silicon lifecycle](../SILICON_LIFECYCLE.md), not a parser or
automatic gate. Replace placeholders, split aggregate rows into individual
checks, and retain immutable decisions and receipts. Publish only authorized
public artifacts; private inputs and local experiment records stay local.

## Candidate and responsibility

| Field | Value |
|---|---|
| Record ID / revision / previous record | <stable ID; immutable revision; link or none> |
| Claim / intended milestone | <exact acceptance claim; early integration, DV closure, etc.> |
| State | <OPEN / BLOCKED / ACCEPTED / REOPENED> |
| Candidate | <source commit; dirty-input status; complete artifact manifest/hash> |
| Scope | <block/subsystem/SoC; instance; supported parameters/profile; modes/corners> |
| Contract | <spec/workload/criteria revisions and requirement IDs> |
| Environment | <PDK/library/IP/tools/configuration/firmware/input hashes or justified N/A> |
| Owner / independent reviewer / approver | <named identities, authority and separate contexts> |
| Runtime | <requested model/effort; observed identity/attestation/evidence or UNKNOWN/none/UNKNOWN> |
| Dependencies | <child records and their conditions; parent consumers> |

## Criteria and receipts

Each criterion must have a threshold/units or precise boolean condition before
execution. Missing evidence remains OPEN. N/A and waivers require the separate
authorization below; do not write PASS for them.

| Requirement/check ID | Owner / reviewer / approver | Acceptance criterion and scope | Applicability | Result | Evidence receipt | Finding/disposition |
|---|---|---|---|---|---|---|
| <ID> | <names> | <limit, units, profile, corners, expected behavior> | <required / N/A requested / N/A authorized / waiver link> | <PASS / FAIL / RUNNING / NOT_RUN / UNKNOWN> | <immutable link + hash> | <issue, owner, next action> |

For each receipt, supply:

- Exact command, tool/environment versions, build inputs, source/DUT/binary/
  dataset identity and hashes, configuration/profile, seed and run/attempt ID.
- Planned, selected, executed, skipped, failed and result-checked IDs/counts;
  explain differences and identify the actual output checker.
- Start/end time, job/process identity, last-progress time and units, elapsed
  time, timeout/cancel status, tool exit and semantic verdict, exact summary
  lines, final completion receipt and reproducible raw artifact links/hashes.
- Coverage kind/profile/hierarchy, raw producer/input hash, numerator and
  denominator, merge members, uncovered points and reviewed exclusions;
  functional/code/fault coverage remain separate.
- For assertions/formal: enabled and activated properties, vacuity and cover
  witnesses, assumptions/abstractions, engine/mode/depth, proven/bounded/unknown
  outcomes and integration obligations. For physical checks: final netlist/
  layout/corners/rule-deck identities and required comparison/violation details.

## Exceptions, change impact and residual risk

| ID | N/A or waiver / affected requirement | Technical basis and compensating evidence | Independent reviewer | Authorized approver / decision link / date | Expiry or reopening condition / residual risk owner |
|---|---|---|---|---|---|
| <ID or none> | <exact scope> | <reason; missing tool is not automatic N/A> | <name> | <N/A authority; maintainer approval and PR manifest link for waiver> | <condition; named owner> |

Change from prior candidate: <add/modify/delete or initial baseline; old/new hashes>.
Affected spec/model/DV/formal/SW/subsystem/top/physical/DFT/package dependencies:
<IDs and impact>. Reopened records and reruns: <IDs, owners and requirements>.
Carried-forward evidence: <identical relevant inputs/assumptions, independent
review and citations, or none>. Open bugs: <severity, reproduction, owner,
disposition; must-fix issues block acceptance>. Residual nonblocking risk:
<explicit accepted risk and owner, or none with supporting review>.

## Independent review and decision history

Reviewer received: <spec, candidate, evidence and permitted implementation
context; independence and actual access controls, if any>.
Review: <reviewed candidate; approve/request-changes/pending; dated citation>.
Reproduced checks: <commands, exact outcomes, receipt links>.
Findings and resolutions: <IDs; fix candidate; affected reruns and re-review>.

| Event / time | Candidate / record revision | Prior → new state | Approver and authority | Decision evidence and exact accepted scope |
|---|---|---|---|---|
| <event> | <hash / revision> | <OPEN → ...> | <name / delegation> | <decision link; conditions; dependent claims not yet established> |

Final tapeout only: <maintainer's explicit authorization, exact release-manifest
hash and destination; otherwise NOT_AUTHORIZED>. This decision does not imply
silicon bring-up or production qualification.

Friction: <one line or none>
Skill candidates: <one line or none>
