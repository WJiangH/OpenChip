# Independent rc2 re-review

Decision: **REQUEST CHANGES**, limited to two related early-write boundary rules below. The prior main architecture findings have been corrected; this is not a rejection of the complete SIM-L1 design direction. Input: `docs/spec/architecture-review-03/` plus the supplied pure-document workload/budget/ADR dependencies, 30 files identified in INPUTS_READ.json. References below use the rc2 snapshot unless another path is explicit.

## Prior findings and actual closure

| Review02 finding | rc2 result | Behavioral evidence |
|---|---|---|
| VA-01 Lite VALID omission | Closed | contract.json now has all 19 Lite signals, including five VALID signals with correct width/driver; matches axi.md:25. |
| VA-02 IRQ raw/gated inconsistency | Closed | system.md:84 defines locally gated PENDING then IRQ.ENABLE; machine source expressions agree. PENDING reset-derived value is 4, ENABLE/ACTIVE zero; enabling a pending source has a unique equation. |
| VA-03 offered DMA error drainage | Substantially fixed; one early-W residual | npu.md:39 retains AR/AW already offered including same-edge offers, drains final R/B, preserves W and discards read data before terminal. RC2-01 covers a W offered before any AW offer. |
| VA-04 fixed versus actual-input integer reference | Closed | workload.md:15,25,34 explicitly authorizes a separately reviewed CPU scalar verifier for actual submitted legal X and immutable W, makes nominal kind1 optional, and preserves fixed floating checkpoints/tokens. |
| VA-05 unrelated progress hides timeout | Closed for timer behavior; one diagnostic residual | axi.md:19 independently counts each obligation, defines early W waiting AW, does not reset on unrelated traffic, accounts for previously completed handshakes, and gives matching progress priority on the threshold edge. RC2-02 concerns the address of an obligation whose AW never existed. |
| VA-06 missing complete forward graph | Closed | workload.md:39-48 gives pre-norm dataflow, Q/K-only RoPE, causal GQA and concatenation, W1 gate/W3 up, both residual sources, final norm and tied head. |
| VA-07 missing LLM-11 matrix row | Closed | Prose, machine and human traceability now contain the same 45 unique requirement IDs, including SYS-12 and LLM-12. |
| VA-08 lost execute identity | Closed | axi.md:7,15 preserves native mem_instr as CPU ARPROT[2], enforces X versus R, and keeps physical port source identity separate. CPU PROT0/4 and NPU PROT0 have distinct legal rules. |

## RC2-01 — Early W still needs an address through error/fatal stop

Evidence: `axi.md:9` (AW/W independence and W-before-AW), `npu.md:39` (retain offered AR/AW; stop offering new bursts), `system.md:93` (SYS-12 retained AR/AW and stop boundary).

Concrete allowed sequence: WVALID is offered or accepted while AWVALID has not yet been asserted; the other NPU read channel returns an error. NPU now stops new burst offers and retains all offered AR/AW, but the early W has no offered AW in that retained set. It cannot retract an unaccepted WVALID, cannot complete an accepted write without its address, and cannot reach the promised drain/reuse state. A global fatal stop has the same ordering question for either DUT initiator. This differs from AWVALID=1/AWREADY=0, which rc2 correctly handles.

Affected: CPU/NPU initiators, fabric retained-write ownership, NPU terminal reuse and SYS-12 stop protocol. The criterion must not be guessed in DV.

Required resolution: explicitly treat any offered W as an existing write transaction whose eventual AW is allowed through stop/error and retained until B; or constrain **both DUT initiators** to offer AW no later than their first W offer, while still requiring targets to tolerate W handshaking before AW because channel READYs are independent. An initiator-specific ordering restriction is compatible with receiver W-before-AW tolerance. State the chosen rule in the error and stop contract.

## RC2-02 — Missing AW timeout has no known transaction address

Evidence: `axi.md:19` obligation (e), `system.md:93` SYS-12 fabric fault metadata.

AXI-07 explicitly times out an early accepted W awaiting its AW. If AWVALID is never supplied, the target has never received the transaction address. SYS-12 nevertheless requires the fabric's timeout fault_addr to contain that transaction's aligned start address. W contains no address; fabric cannot satisfy the required observable without inventing one. This is a diagnostic-contract gap even if legal DUT initiators are later ordered as suggested above, since the monitor explicitly defines this malformed/incomplete sequence.

Affected: fabric/progress monitor, fault producer and independent timeout scoreboard.

Required resolution: define an unknown-address encoding (for example addr=0) for W-before-any-AW and other address-less protocol events, and state when a known offered or accepted address is used. Existing reason3 and source/channel priority can remain. No new gate or timeout relaxation is needed.

## New contract checks and limits

SYS-12 materially improves implementability: sticky fault records have widths and no-backpressure semantics, capture is earliest edge then lowest reason, fabric ties have source/channel order, and only CPU receives local fatal reset. Existing bus state survives loss of native mem_valid; stop fanout is explicit. The two early-W residuals above are the only release-blocking findings from this scoped re-review. Cycle-aware DV must test simultaneous reasons, threshold progress, same-edge offers, stalled responses and common-reset recovery; a static map pass does not prove those behaviors.

The CPU dynamic verifier is now an executable acceptance contract rather than an implicit second inference engine: it compares actual NPU output against independently recomputed integers, never replaces execution data, and reports its cycle cost separately. Fixed FP32 linear/residual/KV/logit checkpoints and the exact 16-token trajectory remain mandatory. Host/DV verifies every call; the CPU verifier covers the selected four positions. Verification must trace both source provenance and consumption of DMA-written Y so a scalar check cannot conceal bypass. No evidence here proves a target math library meets 2 ULP or that RV32 firmware fits/runs; those are explicit downstream artifact and execution gates, not missing architecture semantics.

LLM-12 now uniquely specifies all 36 learned projections and scalar dependencies per forward, including W2 tail 44. The two B1 normative fixtures independently recalculate to their ten listed integer group words. Workload/profile binding preserves 32 prefill plus 16 decode forwards, 1728 matrix calls and 16 published tokens. The software intake's 199296 independently checked host group dots and matching host tokens are owner-reported evidence; its nonlinear/attention implementation is not independently reimplemented, and no target execution or broader quality pass follows from it.

PicoRV32 binding now correctly puts subword lane mapping inside the CPU and returns full RDATA from the native bridge. Word-only CSR software access is an ABI obligation; hardware does not claim to reject an invisible original LB/LH width. The intake also explicitly reports strict-lint failures and untested final integrated parameters. They remain implementation/adoption gates and cannot be silently counted as green.

SIM-L1 still supplies the complete small-model computational path. Its CPU soft-float/attention/validation overhead, final firmware size/stack and simulation wall time require actual measurement. S1 authenticated boot, P1 1.7B operator/memory expansion and F1 physical hardware remain unreleased or unvalidated. Approval of an eventual corrected SIM-L1 contract would only authorize implementation against that contract, not accept silicon, secure boot, product quality or performance.

## Delivered verification plan and audit

Current `vplan.json`: 45/45 named requirements, 5 additional obligations, 3 named rows blocked on RC2-01/02, 3 S1 requirements deferred, 0 executed. Each row retains current normative text, methods, observable criterion and coverage obligations. The new SYS-12 and LLM-12 rows include fault arbitration/retention and full graph dependencies. Prior review02 vplan, audit, input ledger, builder and manifest are retained with `_review02` names; REVIEW.md remains the original report.

Actual static audit summary (`AUDIT.txt`):

```text
PASS: vplan covers every named requirement exactly once — 45
PASS: human traceability matches prose — missing=
PASS: axi4_lite ICD signal width/driver set — missing=
PASS: B1 normative exact fixture arithmetic — 2 fixtures,10 group words; specification arithmetic only
PASS: rc2 shape counts — 45 requirements /16 blocks /47 connections
SUMMARY: 0 static spec inconsistency checks failed; named requirements=45; additional obligations=5; hardware gates=NOT RUN
```

The 17 static checks pass; the two behavioral issues require architect rulings and are not contradicted by that result. No golden model, RTL/SW source inspection, hardware gate, commit/push or remote PR was performed.

- Friction: the traceability formatting removed spaces around pipes; the local static parser was corrected before reporting a result.
- Skill candidates: `verif-architect/references/golden-model-patterns.md` — track offered W before offered AW separately from AW offered but not accepted, including unknown-address fault metadata.
