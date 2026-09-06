# ADR-0004 — AXI LLM SoC family with a complete small-model implementation profile

Status: local architecture release candidate, authorized design direction; independent review pending. Date2026-09-05. Owner chief-architect. Applies only to docs/spec/llm-soc-v1; older milestones remain unchanged.

## Decision

Select SIM-L1 as the first complete execution profile: stories260K, group64-tail W8A8 learned matrices, FP32 CPU scalar/attention/KV, PicoRV32 RV32IM native CPU plus error-aware AXI bridge, 32-bit AXI4 memory fabric, burst DMA and four-product grouped INT8 dot engine writing INT32 partial sums. Store model and KV in external AXI functional memory for simulation, with real CPU firmware and NPU calculation. Caliptra passive core is a separate secure-profile integration, with a trusted ROM host phase rather than a cyclic CPU-reset dependency. Keep P1 as a1.7B-class product study with vector/attention acceleration and substantially higher bandwidth; SIM-L1 is not its implementation claim.

## Evidence and alternatives

The real software probe finds hidden_dim172, so K=172 requires group lengths64+64+44. The unmodified candidate group runtime omits incomplete groups and cannot be adopted blindly. Correct tail handling, per-group INT32 writeback and ordered CPU postscale are therefore new explicit contracts. The probe reports both per-row and group64-tail inference on32prompt+16decode; both match the FP32 token sequence on this one prompt. Group64-tail is chosen for bounded64-product dynamic range and smaller observed KV maximum error; per-row has less scale/writeback overhead and slightly smaller logits RMSE in this sample, so this is not a universal quality victory. Full data/provenance lives in the workload input ledger.

PicoRV32's upstream AXI wrapper has no RRESP/BRESP inputs. A transparent integration would hide bus faults. The selected native bridge makes errors fatal through an independent observable status, without pretending PicoRV32 supplies standard load/store access exceptions. External IRQs use its custom ABI; no PLIC/CLINT claim. ISA compliance remains a required downstream gate.

Four products per step match the32-bit streaming weight port's ideal4B/cycle; eight products offer no sustained gain for row-streamed weights without wider memory or reuse. One product minimizes logic but quadruples ideal arithmetic cycles. No measured PPA exists for any option, and no die area is frozen. A32-bit50MHz port has a200MB/s raw ceiling, far below the prior1.7B W4 context2K20token/s modeling floor22.45GB/s; calling this product-performance ready would be false.

## Explicit migration / change order

| Existing artifact / module | Disposition for SIM-L1 | Responsible downstream role |
|---|---|---|
| ADR0001 Wishbone bus convention / AGENTS bus sentence | locally superseded for named new profile by AXI ICD; root rule migration still orchestrator/integrator task | orchestrator/integrator |
| ADR0002 1×8 dedicated weight-stream NPU + requant | new grouped-dot DMA ABI replaces control/data/completion contract; arithmetic reuse only after review | RTL NPU, independent DV/formal/model |
| ADR0003 PicoRV32 Wishbone RV32IMC / control-only CPU | native RV32IM, custom IRQ, software FP32 fallback, new error adapter | RTL CPU bridge + SW |
| soc_1.md / npu.md old address/descriptor/stream rules | retained legacy scope; never mix addresses/ABI into new profile | chief architect |
| boot ROM, SRAM, UART, IRQ blocks | new AXI/Lite ports, complete maps and error/reset rules | corresponding RTL/DV/SW |
| direct external weight stream/controller | removed in SIM-L1; external memory is AXI functional target; FPGA needs real controller | RTL/platform/DV |
| ISA compliance, lint/sim/coverage/formal/synthesis gates | preserve; add configuration identity and system acceptance, no threshold changes | flow owner/integrator |
| software runtime / golden / system vplan | derive afresh from this specification and probe identities, never from RTL | separate SW/model/verif roles |
| Caliptra core / private memory / reset control | integrate in S1 only, separate frontend/IP dependencies and security acceptance | security RTL/SW/DV/formal |

No existing implementation files were changed, committed, pushed or merged by this ADR. Per user instruction this local manifest replaces remote PR publication. The named local profile is the scope of the AXI exception; it does not silently rewrite all existing Wishbone projects.

## Consequences and release policy

SIM-L1 achieves a feasible functional integration target while accepting slow soft-float CPU work, uncached instruction/data traffic and sequential prefill. Capacity budgets are simulation resources, not SRAM area fit. P1 requires changes to command ABI, quantization/activation/KV formats, vector math precision, local bank bandwidth, coherency/security and accelerator compliance before it is implementable. Downstream reports must label B1,L1,S1,P1,F1 separately. Interface changes after a frozen release require a versioned change order and per-role affected artifacts.
