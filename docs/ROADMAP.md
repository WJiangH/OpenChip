# Engineering direction

The next mainline investigation is **integrating and adapting upstream CoralNPU**.
No CoralNPU import, upstream reproduction, adaptation or silicon result is claimed
by this plan. The existing tinyNPU remains a fast reference regression for the
collaboration framework; it is not a commitment to develop a new mainline NPU
from scratch.

## Ordered decisions

| Milestone | Owner / independent review | Acceptance before dependent work |
|---|---|---|
| Workload and upstream intake | Chief architect with software/model specialists / independent architecture and verification reviewers | Freeze workload, correctness/accuracy, latency, power/area, bandwidth/memory and process/IO/package criteria. Pin upstream revision, licenses, dependencies and native toolchain; inventory real versus surrogate IP and unresolved feasibility assumptions |
| Reproduce the upstream baseline | Assigned flow, software and DV authors / independent reproduction reviewer | Run upstream's documented build and selected tests unmodified on identified tools; retain commands, inputs, binaries, raw checker results and limitations. An upstream README or a successful compile is not a verified workload |
| Approve integration architecture | Chief architect and verification architect / separate specialist reviewers | Compare the measured baseline with the frozen requirements; approve interfaces, memory/host/software integration and any required adaptations with traceable tests, budgets and change impact |
| Adapt and verify incrementally | Separate RTL, DV, formal, software and model owners / independent discipline reviewers | Preserve upstream provenance, review each adaptation, and discharge child assumptions at subsystem/top level. Accept scoped milestones only from candidate-bound evidence |
| Implementation and release readiness | Backend, DFT, package and release specialists / independent qualified reviewers | Follow the lifecycle's target-specific implementation and release criteria; record unavailable capabilities and required open checks. Tapeout requires separate maintainer authorization |

Use the [lifecycle stages and check IDs](SILICON_LIFECYCLE.md) to instantiate these
milestones in private project state. Requirements, model choices and engineering
results belong to that project's approved evidence, not a growing public task
diary. Parallel work starts only after the required dependency is accepted.

## Upstream conventions and tools

[CoralNPU's upstream repository](https://github.com/google-coral/coralnpu) supplies
its own build and test instructions; its documented entrypoints include Bazel
simulation and software targets. Follow the pinned revision's native setup and
[official prerequisites](https://developers.google.com/coral/guides/software/prerequisites)
before proposing adapters. Do not rewrite imported HDL, buses, resets or build
systems solely to match this repository's tiny reference design conventions.
Adaptations require a reviewed engineering reason and independent verification.

## Existing reference contracts and evidence

The [reference specs](spec/README.md), [ADRs](adr/),
[verification assets](VERIFICATION.md), and [blink evidence](../evidence/blink/README.md)
retain their existing scope. This roadmap does not approve or revise their
behavior. Earlier M0–M5 plans and the phase diary are available in the
[frozen pre-reorganization source](https://github.com/WJiangH/OpenChip/tree/1b72dda5c006f8a2a9f2f75941b06eefde4117ee/docs).
Historical milestone references in a specification describe that earlier plan;
they are not current completion claims. Documentation moves alone do not erase
or upgrade signoff: preserve source/version pointers and independently assess
whether any contract or acceptance dependency actually changed.
