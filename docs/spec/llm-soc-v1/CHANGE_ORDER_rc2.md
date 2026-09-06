# Change order 1.0-rc1 → 1.0-rc2

2026-09-05. Chief architect rules every finding below **spec-bug**. Prior input hashes: review02-input-hashes.json. Independent reviewer findings were relayed by root from review02 RTL/DV reviews; local reviewed reports are bound by orchestrator in its review ledger. No implementation/gate acceptance is implied. Binary CSR/descriptor ABI remains major1; this pre-freeze RC resolves incomplete behavior.

| Finding | Ruling /correction | Changed contract /affected owner |
|---|---|---|
| Lite VALID names incorrectly dropped by suffix filter | explicit19-signal Lite list retains all5VALID channels |contract.json /RTL bridge,DV protocol |
| IRQ raw pending vs gated wire mismatch | PENDING is locally-enabled peripheral level; IRQ.ENABLE gates CPU further |system.md,contract.json /IRQ RTL,SW,DV |
| CPU instruction-fetch identity lost | ARPROT[2]=mem_instr retained and checked for X permission; not source trust |axi.md /CPU bridge,fabric,DV security |
| DMA error could retract offered requests | all offeredVALID incl not-yet-accepted remain and drain; full burst W buffered before AW |npu.md /NPU DMA,DV/formal |
| Local datapath lacks group descriptor | controller broadcasts command to local+DMA; groups1/2 split held words into disjoint lane-mask transfers |npu.md,contract.json /NPU RTL,independent arithmetic DV |
| Floating tolerance vs static exact-integer fixtures conflict | B1 keeps static exact fixtures; L1 actual-X/W CPU integer verifier compares NPU, cannot replace outputs; fixed FP32/model checkpoints and tokens still required; verifier cost separate |workload.md /SW,model,DV |

Other pre-review corrections retained: real RoPE reciprocal-then-multiply order, explicit expectation container, fatal local CPU reset retains bus state, masked reserved IRQs and active writes buffered before AW. Every prose release label and traceability table updated. No gate lowered; numerical tolerances unchanged. No exact expected integer from a different activation trajectory is used to judge a compliant actual-input dot.


Additional final RTL-review02 findings (source [rtl-review-02.md](reviews/rtl-review-02.md)):

- R02-03 ruled spec-bug: CPU performs subword lane selection internally; bridge returns full RDATA/passes mapped stores. CSR full-word rejection applies to bus transactions, not invisible original CPU load size; firmware word-only ABI remains. FAULT_ADDR now emitted aligned bus address.
- R02-05 completion: IRQ.PENDING is live derived state with post-reset value4 due to UART READY, rather than an invented stored reset0.
- R02-06 ruled spec-bug: SYS-12 plus C26..C33 carry explicit sticky fault metadata and stop-new-transaction fanout. Protocol fault reason6, simultaneous lowest-reason priority and fabric tie ordering are fixed; only CPU receives fatal local reset.
- R02-04 completion: fetched local word index/keep→k mapping explicit; removed misleading fetched-word group markers, since local has full descriptor and creates group-bound operand beats.
- Traceability SYS-12 added; LLM-11 row was already restored in rc2.


Final DV-review02 findings (source [dv-review-02.md](reviews/dv-review-02.md)):

- VA-01/02/03/04/07 are the Lite, gated/live IRQ, offered-transaction drain, actual-input integer comparator and LLM-11 traceability corrections above.
- VA-05 ruled spec-bug: AXI-07 defines independent source/channel/transaction obligation timers, matching-event resets, early W waiting AW and the exact threshold edge. Unrelated writes cannot hide a stuck read.
- VA-06 ruled spec-bug: LLM-12 gives the full sequential forward graph, W1-gate/W3-up assignment, both residual sources, norm placement, Q/K-only RoPE, GQA and concatenation order. New requirement/traceability row added.
- Root budget review correction: independent AXI read/write channels require max(read cycles,write cycles) as parallel-service lower bound; sum is explicitly a serialized-service scenario. budget.py,budget.json and budget README corrected together.
