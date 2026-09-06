# Independent verification architecture review

Decision: **REQUEST CHANGES** for release of the SIM-L1 implementation contract.

Input is the eight-file `docs/spec/architecture-review-02/` frozen snapshot, identified by SHA256 in INPUTS_READ.json. References below are relative to that directory. This review is spec-derived, with no RTL/SW implementation inspection, injected implementation bugs, simulation, commit, push or remote PR. The reviewer is not the final signoff authority.

## Release-blocking findings

### VA-01 — Machine AXI-Lite interface cannot represent a transaction

Evidence: `contract.json:245-308`, versus `axi.md:25` (AXI-09).

The Lite signal dictionary omits **AWVALID, WVALID, BVALID, ARVALID and RVALID**. It includes their READY counterparts. Prose requires all five VALIDs, and C08–C11 use this dictionary. This is a concrete diagram/machine/prose discrepancy, not an implementation naming choice. A module delivered against the machine dictionary cannot issue or acknowledge a valid CSR operation.

Affected: lite_bridge, sys, irq, uart, npu_csr; B1 cannot reach SUBMIT or RESULT_COMMIT through this contract.

Required resolution: restore each VALID with width 1 and correct driver; check the complete full-AXI and Lite signal sets against AXI-01/09. Do not silently have implementers add private wires.

### VA-02 — Two incompatible NPU-to-CPU IRQ equations

Evidence: `system.md:84`, `npu.md:34,39`, `contract.json:547-568`.

System PENDING is defined as raw NPU.DONE / NPU.ERROR; ACTIVE=PENDING&ENABLE drives CPU bits4/5. NPU IRQ outputs instead include NPU.IRQ_ENABLE, and machine C17/C18 connect these gated done_irq/error_irq outputs to irq. With DONE=1, NPU.IRQ_ENABLE=0, IRQ.ENABLE=1, the system paragraph requires CPU irq[4]=1 while the NPU/machine path requires 0. Driver and interrupt DV cannot choose a unique expected value. Also `contract.json:1341-1345` declares PENDING reset=0 while UART READY/TX_EMPTY starts asserted (`system.md:88`, machine UART STATUS reset=1); specify whether reset holds derived status at zero or the first readable value is 4.

Affected: npu_csr, irq, CPU IRQ firmware and B1 interrupt completion.

Required resolution: write one equation for PENDING, ACTIVE and CPU inputs including both enables, and distinguish reset-held values from first readable derived values. Include enable changes while a terminal source is pending.

### VA-03 — Error terminal may precede an irrevocably offered transaction

Evidence: `npu.md:39` (NPU-06), `axi.md:9,13` (AXI-03/04).

NPU-06 drains only already *accepted* reads/writes after the first DMA error. AXI-03 prohibits withdrawing an offered VALID before READY. Concrete legal concurrency: an NPU AWVALID is stalled with AWREADY=0 while a previous NPU read returns SLVERR. The offered AW is not accepted, but cannot be cancelled. Merely draining accepted traffic permits reporting ERROR/clearing/reusing the command before this AW later handshakes and writes old data. The same gap applies to an offered AR and to independently offered W. Buffering all W before AW addresses data availability, not the lifetime of an offered address.

Affected: npu_dma, npu_ctl, npu_csr; terminal reuse and output memory ownership.

Required resolution: explicitly define the drain set to include every offered-but-stalled AXI request plus its eventual accepted transaction, preserve payload/descriptor until all associated responses drain, and forbid a terminal error until no offered or accepted old-command traffic remains. Define a same-edge first-error/new-offer case. If progress stops, use coordinated-reset fatal, not cancellation.

### VA-04 — CPU's fixed exact checkpoint check and allowed numeric variation need one acceptance rule

Evidence: `workload.md:15,25,34` (LLM-05/09/11).

LLM-05 allows compliant scalar-library differences to change quantized X and then compares exact grouped dots to a reference recomputed from the observed legal X/W. LLM-09 requires the CPU to check exact grouped dots against read-only artifacts and forbids executing the expected generator in DUT; LLM-11 contains only fixed INT32 expected dot values, not alternate input-dependent references. An independently generated static blob is therefore not sufficient to implement the stated adaptive comparison rule on CPU.

This is a contract ambiguity, **not evidence that the bound stories260K input fails**. A small illustrative threshold shows the mechanism: in a group with maxabs=127 (scale=1), FP32 values 0.5 and the immediately smaller representable value quantize to 1 and 0 under round-away-on-tie. Both can be well within the upstream 1e-4 absolute tolerance. With a weight of 1, valid exact dots differ by 1. The integer engine can be correct in both cases while a single fixed CPU expected word accepts only one.

Affected: independent reference/exporter, soft-float runtime, expectation container/parser, CPU validation, system DV.

Required resolution: explicitly distinguish an exact reproducible CPU acceptance path from any cross-library DV conformance path, or define an authorized input-dependent CPU checking mechanism that does not act as the DUT computation. Bind reference inputs/checkpoints sufficiently to reject illegal X; never waive integer mismatches or widen tolerances. The architect must choose, and the vplan must follow that choice.

### VA-08 — Execute permission is lost at the fabric interface

Evidence: `system.md:38-55` (SYS-04), `axi.md:5,7` (AXI-01/02), `contract.json:309-320`.

SYS-04 requires the fabric to enforce a table distinguishing CPU R/X and R/W/X from R-only or R/W regions. CPU instruction fetch is observable as `mem_instr` on its native interface, but full AXI carries no separate instruction indicator and requires PROT=0 for every request. The fabric therefore receives indistinguishable CPU transactions for a data load and instruction fetch at the same model/expected/MMIO address. Physical source-port identity separates CPU from NPU; it does not distinguish CPU execution from CPU data access. In particular, the table's model R-only permission cannot be enforced as a no-execute rule by that fabric contract.

Affected: cpu_bridge, fabric/firewall, ROM/runtime and SYS-04 permission DV. This concerns the SIM-L1 table itself, not a demand to release S1 early.

Required resolution: specify native-bridge execute-range enforcement using mem_instr, with the correct fault behavior before AXI issue, or retain trusted fetch metadata/appropriate AXI encoding through the firewall and revise the fixed-attribute rule. If SIM-L1 does not enforce execute permissions, explicitly mark that fact and change the table/claims; do not let independent implementers silently select a policy.

## Additional actionable specification issues

### VA-05 — Progress timeout is ambiguous under unrelated handshakes

Evidence: `axi.md:19` (AXI-07).

The phrase "consecutive cycles without a handshake whenever any AXI channel" does not say whether counters are per channel/transaction or reset by any fabric handshake. A permanently missing R beat concurrent with continuous successful writes times out in a per-read monitor and may never time out in a global monitor. Specify counted obligations, timer reset events, missing AW after early W, and the threshold edge. A finite 65536-cycle bound must not be defeated by unrelated channel progress. Affected: fabric/progress monitor, NPU recovery and CPU fatal path.

### VA-06 — Complete model operator list does not fix the complete forward graph

Evidence: `workload.md:7,13,19` (LLM-01/04/06).

Shapes and scalar formulas are specified, but the layer dataflow does not explicitly connect norm_attn→Q/K/V→attention→Wo→first residual→norm_ffn→W1/W3→W2→second residual. In particular no normative statement identifies W1 versus W3 as the SiLU input, and no equation fixes the source of both residual additions. Swapping W1/W3 preserves all declared shapes, all seven matrix calls and the listed SiLU-times-up operation while generally changes output. Source intake identity alone does not resolve a normative graph unless a precise independent algorithm reference is explicitly incorporated.

Affected: CPU runtime and independent full-model reference. Required resolution: provide numbered forward equations or an explicit normative algorithm binding, with the gate/up assignment, residual sources, norm placement, RoPE Q/K-only application and attention output concatenation order. This avoids two independent teams importing an unwritten convention.

### VA-07 — The new expectation requirement is absent from the human traceability matrix

Evidence: `workload.md:34`, `contract.json:1977`, and the end of `traceability.md:48`.

LLM-11 exists in prose and machine requirements but the human matrix stops at LLM-10. Add its owner and independent parser/bounds/coverage obligation. The supplied vplan includes LLM-11; this does not repair the architecture's manifest.

## Scope and positive evidence

The review02 patch repaired the previous missing paired X/W internal operand path and controller→CSR terminal return; these are not open findings. Address arithmetic, KV offsets (2×327680 bytes), 36 calls per forward, and 48 forwards/16 published tokens are internally consistent. The matrix/group arithmetic can be modeled independently with exact integers; the maximum stated group magnitude is 67108864, within signed INT32. Padding, descriptor range checking, immutable expected-region permissions, full output B completion and no-host-write constraints provide useful verifiable boundaries.

SIM-L1 retains an actual complete small-model route: CPU boots copied firmware, supplies dynamically quantized inputs through memory, NPU computes all learned projections including the head, and CPU runs attention/nonlinear/normalization and checks results. There is no identified missing operator *capability* that inherently prevents the small-model path; VA-06 is about unambiguous dataflow. This does not establish runtime feasibility or observed latency: RV32IM soft-float cost, actual firmware/stack size, compliant math-library availability and full-model DUT execution remain release evidence to obtain. Missing dependency/budget documents in this snapshot were intentionally not treated as defects.

S1 explicitly defers executable authenticated boot, real Caliptra firmware/service binding, protected nonvolatile state and physical security dependencies. It must remain unreleased, but it need not block development-mode L1. P1's much larger memory/bandwidth/operator demands and F1 physical implementation are not validated by SIM-L1, and cannot inherit its success label. The user's eventual end-to-end LLM chip goal is therefore still a staged engineering objective; neither this contract review nor a small-model simulation is chip signoff.

## Verification disposition

`vplan.json` maps all 43 declared requirements plus unnumbered partition/CSR/IRQ/B1/traceability obligations to methods, observables, pass criteria and coverage. All rows are planned/not-run; blocked rows reference the issues above. No golden model or testbench is supplied by task instruction. Once corrected, the independent DV role should implement cycle-aware models and test arbitrary reset/stimulus patterns, rather than fixed precomputed transaction scripts.

Local `audit_contract.py` checks only document consistency and vplan completeness. Its output is in `AUDIT.txt`. Hardware lint/sim/coverage/formal/synthesis/timing/DRC/LVS gates are **not run** because this is a read-only architecture review, with no implementation intake; this is not a gate waiver or accepted hardware result.

- Friction: early snapshot was replaced mid-review; only review02 findings remain actionable.
- Skill candidates: `verif-architect/references/golden-model-patterns.md` — add offered-versus-accepted AXI drain and fixed-versus-observed numeric reference checks to architecture reviews.
