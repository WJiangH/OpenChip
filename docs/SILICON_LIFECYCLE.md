# Silicon lifecycle and incremental signoff

OpenChip projects develop and accept evidence throughout implementation. A block
can be ready to integrate while independent verification remains open; accepted
blocks do not establish subsystem, SoC, or tapeout acceptance. Each decision
applies to an identified candidate, configuration, environment, and purpose.

This document defines the reusable **manual planning and review process**. It
does not implement a scheduler, signoff database, access-control system, or new
CI gate. Use the [signoff record](templates/SIGNOFF_RECORD.md) in the adopting
project's approved evidence location. Public framework examples must contain
reproducible public inputs only; private design records stay outside public
history. Current automation is described in [CI_CD.md](CI_CD.md), and current
reference evidence in [VERIFICATION_STATUS.md](VERIFICATION_STATUS.md).

## Set the acceptance contract before implementation

The manager names an owner, independent reviewer, and decision approver for
every work item. Architects own behavior; specialist authors own their delivery
loops; integrators evaluate evidence; the maintainer authorizes final tapeout.
Where DFT, analog, security, package, or manufacturing expertise is required,
assign a qualified specialist and explicit write scope; the nine existing role
methods do not imply those capabilities are already staffed or implemented.

Freeze a versioned workload and requirements baseline with measurable limits:

| Contract | Required decision and evidence |
|---|---|
| Workload and correctness | Actual software/model versions, datasets and licenses, inputs, numerical precision, expected outputs, accuracy metric/tolerance, and negative cases; distinguish a real workload from a synthetic proxy |
| Performance | Latency/throughput limits, batch size, concurrency, cold/warm start, clock, observation boundaries, and acceptable variation |
| Resources | Power/energy and thermal limits with activity conditions; area basis; memory capacity, bandwidth, traffic contention and external-memory assumptions |
| Platform | Target process/PDK, libraries and IP revisions, voltages/corners, clocks/resets, IO rates and electrical requirements, package/pinout, board and external device assumptions |
| Operation | Boot and update flow, provisioning, trust boundaries, recovery, debug/test access, safety/reliability requirements where applicable, and manufacturing/bring-up acceptance |

For each requirement, record its ID, units, threshold, measurement procedure,
owner, reviewer, approver, dependencies, and planned evidence at model, RTL,
physical, and silicon levels. Estimates need their model/calibration limits;
simulation cycles are not measured silicon time and estimated power is not
measured board power. Resolve feasibility, tool/license/PDK availability,
schedule and compute budgets before promising a milestone. Missing targets are
OPEN decisions, never implicit passes. Changes require a reviewed spec/ADR and
the impact procedure below; failure is not a reason to relax the baseline.

## Roadmap and gate ownership

Stages overlap: integrate early, run physical feasibility before RTL freeze,
and close requirements as evidence arrives. Instantiate each row per block,
subsystem, or top and split its checks into independently reviewable records.
The approver named below is a responsibility to assign to an identified person
or authorized agent; the author cannot approve its own work. The final tapeout
authorization belongs to the maintainer.

| Stage / decision | Owner; independent reviewer; approver | Required artifacts and exit criteria |
|---|---|---|
| 0. Workload contract and feasibility | Chief architect with software/model owners; independent architecture/workload reviewer; maintainer | Frozen contract above, executable reference outputs, resource/IO/package budgets and feasibility risks. Every acceptance metric has a threshold and measurement plan; this approves the baseline, not achieved hardware performance |
| 1. Architecture and verification plan | Chief architect and verification architect in separate work items; independent architecture and verification reviewers; designated architecture authority | Versioned behavior, interfaces, memory map, error/security semantics, clock/reset/power topology, IP inventory, requirement-to-test/property/coverage mapping. Ambiguities resolved before dependent implementation |
| 2. Block RTL readiness | RTL engineer; independent RTL reviewer; designated design approver | Spec-traceable implementation and supported parameter sets; clean applicable lint/elaboration, reset/X checks, synthesis/area/timing feasibility, integration constraints, reviewed open issues. Explicitly state whether approval is for early integration or feature-complete RTL; neither is DV closure |
| 3. Block verification closure | DV engineer and formal engineer in separate work items; independent DV/formal reviewers; verification authority | Spec-derived tests/models, directed/random/negative regressions and checked results; functional/code coverage closure; assertion activation and formal outcomes as defined below. All required configurations addressed, must-fix bugs closed, exclusions independently authorized |
| 4. Subsystem integration | Assigned integration RTL/SW authors in their own scopes; independent subsystem DV and integration reviewers; integration authority | Exact child revisions and conditional approvals; cross-block address/decode, protocol/ordering, arbitration/backpressure, reset/clock/power interactions, interrupts/errors, DMA/coherency and memory ordering where applicable. Interface assertions and concurrent traffic check end-to-end data integrity and progress |
| 5. Full-SoC functional acceptance | System RTL and software owners in separate work items; independent SoC DV, software, security reviewers; system acceptance authority | Production-intent boot/software and actual workload on the integrated DUT; correctness and resource/performance criteria checked with defined measurement boundaries. Exercise peripheral/memory traffic, contention, failures, reset, recovery and security lifecycle; identify every substituted IP/model and resulting unproven claim. A scoped workload result can be accepted separately while other SoC obligations remain OPEN |
| 6. Implementation and test closure | Backend owner and assigned DFT/IP/package specialists; independent physical, DFT and integration reviewers; physical/test authorities | Synthesis through route/extraction, logical equivalence, DFT, electrical/timing/physical checks, and selected same-binary gate-level verification below. All results bind to final netlist/layout, process and operating modes; ECOs trigger revalidation |
| 7. Tapeout release | Integrator assembles; independent release and qualified discipline reviewers; maintainer | Reconciled candidate ledger, no must-fix bugs or unresolved required checks, explicit residual risks/authorized exceptions, final foundry/package/test deliverables and checksums. Written authorization identifies exactly what may be submitted and to whom |
| 8. Bring-up and production qualification | Assigned silicon, firmware, test and manufacturing owners; independent validation/reliability reviewers; product/release authority | Received silicon identity, board/package configuration, boot/IO/memory tests, workload and PVT characterization, manufacturing-test correlation, yield/reliability/qualification criteria, errata and disposition. Tapeout or first boot alone does not establish production readiness |

This separation draws on OpenTitan's distinct design and verification maturity
tracks and its configuration-specific signoff/reassessment process. The stage
numbers above are OpenChip planning labels, not an assertion of OpenTitan
certification or direct equivalence to its D/V labels.
[OpenTitan development stages](https://opentitan.org/book/doc/project_governance/development_stages.html),
[signoff checklist](https://opentitan.org/book/doc/project_governance/checklist/index.html).

## What each closure decision must establish

### Block verification

Map every normative requirement to a test, property, measured coverage bin, or
explicit unresolved disposition. Keep planned testpoints, executable tests,
parameter/profile combinations, seeds, and executed runs distinct. A plan row,
an assertion declaration, a passing smoke test, or a coverage percentage alone
does not establish complete checking.

For each supported profile, record the producer/tool/options, hierarchy and
source identity, raw coverage input and hash, numerator and denominator by
coverage kind, merged run membership/seeds, exclusions, and uncovered points.
Review functional bins and crosses against requirements, including illegal and
error cases. Code coverage cannot substitute for functional coverage. The
existing repository target remains at least 90% line and toggle per module;
[coverage-report](COVERAGE_REPORT.md) is diagnostic and does not enforce it.
Do not pool incompatible profiles or hide a weak instance in a chip-wide total.

For assertions, record enabled/disabled counts, activation/antecedent and cover
witnesses, failures, and vacuity/unreachability review. For formal, record
properties and modes, assumptions and their justification at integration,
abstractions/black boxes, engines, bounds, induction/proof result, cover results,
timeouts and unknowns. A bounded check is not an unbounded proof; a proof under
an assumption is reusable only where that assumption is established. Use
negative controls or checker fault injection where needed to show the harness
can detect the failure it claims to check. Independent spec-derived checking
and explicit coverage planning are consistent with
[OpenTitan's verification methodology](https://opentitan.org/book/doc/contributing/dv/methodology/index.html).

### Subsystem and SoC acceptance

Maintain a dependency map from each child instance/profile to parent contracts
and checks. Recheck clock/reset domain crossings (CDC/RDC), interface timing,
power states and system-level assumptions after integration. Verify
that each conditional child approval's assumptions are discharged by parent
evidence; unresolved obligations block the corresponding parent acceptance.
Separately verify connectivity, functionality, concurrent behavior, and software-observable
outcomes; elaboration or a connection count proves neither correctness nor
deadlock freedom. CDC/RDC require domain-specific analysis, not an inference
from ordinary synchronous simulation.
[Siemens CDC/RDC overview](https://www.siemens.com/en-us/products/ic/questa-one/design-solutions/).

Distinguish architectural model runs, block acceleration, full-system RTL,
emulation/FPGA, and physical silicon receipts. State the CPU, memory controller,
PHY, security controller and external-device implementations actually present.
A behavioral or surrogate IP may support a scoped functional experiment but
cannot establish the real IP's timing, security, electrical, or protocol closure.

Exercise real ROM/firmware loading and boot to checked completion, provisioning
and lifecycle transitions, authenticated update/rollback behavior where
required, recovery from corrupt images/interrupted writes, privilege/debug/test
access, and required security failures. Use synthetic secrets in reproducible
evidence. A preload that bypasses boot or a stub that always authorizes an image
must be disclosed and leaves the bypassed requirement OPEN. Long workloads can
use a planned mix of model, acceleration and RTL evidence; retain an explicit
mapping of what actually ran and what remains unverified at the SoC level.

### Physical, DFT and post-layout acceptance

Assign owners and reviewers to every applicable check below and freeze their
thresholds, operating modes/corners, tools and approved rule decks. Run early
feasibility checks during development and rerun affected checks on the final
candidate. Generic open-tool results do not certify a foundry-qualified tapeout.

| Discipline | Required evidence and acceptance basis |
|---|---|
| Implementation identity | Final RTL/netlist/GDS or OASIS hashes, hierarchy and IP/macros; exact PDK/library/LEF/GDS/SPICE/Liberty/extraction and tool versions, licenses/delivery rights and target foundry-approved rules |
| Equivalence and ECOs | RTL-to-synthesis and required post-DFT/post-route/ECO comparisons; match points, unmatched/aborted partitions, black boxes, test-mode assumptions and semantic verdict. Resolve every required comparison |
| Timing and constraints | Reviewed clocks/generated clocks, IO delays, modes/corners and parasitic extraction; setup/hold, recovery/removal, pulse-width and electrical limits as applicable; unconstrained paths, exceptions and signal integrity reviewed. Meet spec targets, never adjust constraints merely to obtain a pass |
| Clock/reset/X/power | Integrated CDC/RDC, reset/power sequencing and X propagation; UPF or equivalent power intent where applicable, isolation/retention/level shifting and power-aware checks; explain approved exceptions |
| Physical and electrical rules | Foundry-required DRC, LVS, ERC, antenna, density/fill and connectivity checks on final delivered layout; full logs and resolved violations, not just tool exit codes |
| Power integrity and package | Power/activity assumptions, static/dynamic IR drop, electromigration, thermal and reliability limits, supply/package/IO/ESD constraints; representative and stress scenarios with declared coverage |
| DFT/manufacturing | Reviewed scan/test access and constraints, ATPG fault models/coverage and untested/untestable denominators, pattern validation, MBIST/repair for memories, test clocks/power/timing, analog/IO tests where applicable, ATE/wafer/package-test delivery and acceptance plan |
| Post-layout functionality | Selected firmware/tests passing on RTL and final gate netlist with declared SDF annotation, corners, cell/memory models, reset/X handling, annotated-path coverage and checked outputs; no hidden timing-violation suppression |

Equivalence checks compare design representations; STA and physical checks
address different obligations. Power integrity includes voltage drop and
electromigration. Manufacturing fault coverage measures a fault model and test
strategy, not functional requirement coverage.
[Synopsys equivalence](https://www.synopsys.com/implementation-and-signoff/signoff/formality-equivalence-checking.html),
[STA](https://www.synopsys.com/implementation-and-signoff/signoff/primetime.html),
[power integrity](https://www.synopsys.com/implementation-and-signoff/signoff/redhawk-sc.html),
[ATPG](https://www.synopsys.com/implementation-and-signoff/test-automation/testmax-atpg.html).
OpenLane documents its own final DRC/LVS and related implementation checks;
projects must still establish which tools/decks their target foundry accepts.
[OpenLane flow](https://openlane2.readthedocs.io/en/latest/getting_started/newcomers/index.html).
For example, a static IR-drop report cannot establish dynamic IR-drop or
electromigration closure; absent required analyses remain OPEN.

The [backend method](../.agents/skills/backend-engineer/SKILL.md) requires SDF
gate-level simulation to re-pass the same firmware binary that passed RTL.
Before runs, the verification architect, backend owner and independent reviewer
define the decision-bearing signoff firmware/test suite and the approver accepts
its coverage of boot/reset, critical interfaces, power/test modes and workload
paths. Run each selected binary unchanged at RTL and gate level and bind both
receipts to its hash. The selection is not an automatic requirement to replay
every hours-long application at gate level, nor permission to omit an existing
required firmware case. Full workload obligations remain at their planned
levels. Any reduction of an approved requirement needs the maintainer-approved
exception required by AGENTS.md; missing required GLS stays OPEN.

## Immutable decisions and change impact

Create records during development, not only at release. Each record names an
exact candidate digest, spec revision, block/instance/configuration, environment,
milestone and claim, with links to its dependencies and evidence. Archive each
decision and append a new revision/event instead of rewriting historical
acceptance. A status dashboard is a view of those records, not the evidence.

| State | Meaning and allowed transition |
|---|---|
| OPEN | Required work/evidence or review is incomplete; move to BLOCKED when a known dependency prevents progress, or ACCEPTED only after review and authorized decision |
| BLOCKED | Named missing prerequisite, failed criterion, or must-fix issue prevents acceptance; record owner and recovery condition, then return to OPEN for work/recheck |
| ACCEPTED | Named approver accepted this exact scoped claim from cited evidence and independent review; does not propagate automatically to a parent or changed candidate |
| REOPENED | A new candidate or discovered defect invalidates an earlier claim; link the historical record and impact analysis, then resolve through OPEN/BLOCKED and a new acceptance decision |

Record check outcomes separately: PASS, FAIL, RUNNING, NOT_RUN, or UNKNOWN.
Pending jobs/review, missing final receipts and tools that ran no relevant
checks are never PASS. Applicability is a separate decision: an N/A request
needs technical grounds and independent approval by the named authority. A
waiver additionally needs an explicit maintainer approval linked in the PR
manifest under Iron Rule 5, exact affected requirement/scope, compensating
evidence, residual risk, expiration and conditions for reopening. Keep waived
or N/A rows visible; neither is a measured pass. Unresolved serious correctness,
security, data-integrity or safety bugs block the affected acceptance and
tapeout. Severity and disposition require independent review; authors cannot
downgrade a bug to bypass closure. Residual nonblocking risks need explicit
ownership and acceptance, not an empty "open items" field.

For every add, modify, or delete of a block or dependency:

1. Identify changed requirements/interfaces and the old/new source, profile,
   IP, software, constraints or tool identities. A deletion must remove stale
   address maps, interrupts, drivers, test expectations and physical connections.
2. Trace consumers through spec/model/golden model, RTL, DV/formal assumptions,
   software ABI/drivers/firmware, subsystem/top, timing/power/area and DFT/package
   dependencies. Architecture changes are approved before dependent code changes.
3. Reopen affected claims for the new candidate; list required reruns and owners.
   Retain historical accepted records as history, never as current approval.
4. Reuse unaffected evidence only with a cited, independently reviewed
   carry-forward argument showing identical relevant inputs and assumptions.
   Unknown impact means OPEN. A matching filename or green old CI run is not
   sufficient; a new supported parameter set requires assessment.
5. Run and review affected checks, reconcile parent records, and issue new
   decisions. Physical ECOs also revisit equivalence, extraction/timing,
   physical/electrical checks and selected GLS as dictated by the change.

## Evidence and agent execution receipts

Every check has an independently inspectable receipt, whether generated by a
future harness or assembled manually today:

- Identity: spec/source commit and dirty-input status; resolved build inputs,
  simulator/DUT/netlist identity, firmware/model/input hashes, tool versions,
  command, configuration/profile/seed, environment and dependency hashes.
- Scope: planned and selected check IDs; executed, skipped, failed, and
  result-checked IDs/counts. State collection and checker coverage separately.
  Explain missing checks and prevent zero selected tests from masquerading as
  regression success. Preserve raw output and coverage, not just summaries.
- Execution: start/end times, run/attempt ID, process/job identity, elapsed time,
  timeout/cancel status, periodic progress units and last-progress timestamp.
  A live process or log heartbeat is liveness, not simulation progress or a
  result. Missing/stalled progress needs investigation, not an invented ETA.
- Result: tool exit status **and** parsed semantic verdict, exact summary lines,
  checker result, failures/unknowns, final completion receipt, artifact hashes
  and durable location; reproduce from a clean candidate with declared inputs.
- Review/decision: assigned author and independent reviewer contexts, reviewed
  candidate, cited rule and evidence, reproduced checks, findings/fixes/review
  verdict, named approver, time and exact authorized scope.

Keep requested model/effort separate from observed runtime and account identity
using [AGENT_ATTRIBUTION.md](AGENT_ATTRIBUTION.md). If no independent runtime
identity is exposed, record UNKNOWN/none/UNKNOWN. A model label, test count or
completed job is not a quality ranking. A successful review job also does not
mean the reviewer approved its subject.

Separate authors, independent spec-derived oracles, fresh review contexts and
external reference evidence reduce correlated mistakes; different model names
alone do not establish independence. Record what the reviewer actually received
and inspected. Worktrees isolate changes, but shared filesystem/tool access is
not a security boundary. Skills and branch rules are instructions/checks, not
access enforcement. If a work item needs enforced read/write separation, supply
and verify sandbox/repository permissions and access logs; do not claim that
the current shared workspace or prefix checker enforces it.

## Release decision and automation boundary

The integrator reconciles all applicable records against the exact release
candidate, including child approval conditions, changes, final IP/PDK/package
identities, check failures, exceptions and remaining risks. Independent release
review verifies evidence completeness and reproduced checks. The maintainer
then explicitly authorizes the identified tapeout submission; a PR merge,
source snapshot or completed routing run is not that authorization. Foundry,
IP, package and manufacturing requirements determine actual readiness; this
generic checklist cannot certify it. Bring-up and production qualification
remain separate decisions after silicon exists.

Today, public CI runs boundary, framework, lint, unit-simulation and configured
formal jobs. Coverage acceptance, full-SoC execution, complete physical/DFT
signoff and the lifecycle record transitions above are not automated gates.
Framework/documentation PRs run their applicable checks and record silicon
gates as NOT_RUN with a scope reason; they do not need a chip tapeout to be
accepted. Future harness work must name the exact record/check it implements,
validate success and failure paths, preserve raw receipts, and prove its access
and review guarantees before those guarantees are claimed.
