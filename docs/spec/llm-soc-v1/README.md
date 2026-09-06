# LLM SoC v1 architecture release candidate

Version 1.0-rc3 · 2026-09-05 · chief-architect · LOCAL ONLY

This is the implementation contract for **SIM-L1**, a complete small-model SoC execution configuration. It defines real CPU execution, AXI transactions and NPU arithmetic. It is not an implemented chip, frozen product or accepted hardware result. Independent architecture review and IP/software intake remain release conditions; the status ledger below prevents equating a complete contract with validated implementation.

| Scope | Contract state | Evidence state |
|---|---|---|
| B1 reset→boot→AXI→NPU→writeback→CPU check | specified for implementation/review | RTL/firmware/system DV not run |
| L1 full stories260K prefill and 16 generated tokens | numeric/workload binding in workload.md | software probe binding recorded separately; DUT execution not run |
| S1 Caliptra secure boot | integration boundary and task contract only | not released as executable secure configuration |
| P1 1.7B product | resource/throughput budget and expansion decisions | uncalibrated; no product performance/quality acceptance |
| F1 FPGA / ASIC | downstream platform work | no board/PDK/package/DRAM PHY commitment or signoff |

Normative order: [system](system.md), [AXI ICD](axi.md), [NPU](npu.md), [workload and software ABI](workload.md). [Security](security.md) specifies the domain boundary and release blockers, not a fake authorization implementation. [Machine contract](contract.json) enumerates blocks, wires, maps, registers and requirement ownership; prose defines semantics. Any discrepancy is a spec defect, never an implementation choice.

[ADR-0004](../../adr/0004-llm-soc-v1.md) authorizes this local AXI configuration while preserving the older Wishbone project. [Budget](../../../explore/llm-soc-v1/README.md) distinguishes observed inputs and analytical assumptions. [Traceability](traceability.md), [downstream work](downstream.md), INPUTS_READ.md and MANIFEST.md complete the package. Version changes after release require a change order affecting all linked artifacts.

The NPU executes every learned matrix projection including logits. CPU soft-float attention, norm, RoPE and SwiGLU are explicitly part of SIM-L1 latency. This demonstrates complete execution, not a strong all-operator NPU. P1 adds vector/attention hardware and a substantially different memory subsystem under this architecture family; it cannot inherit SIM-L1 performance numbers.
