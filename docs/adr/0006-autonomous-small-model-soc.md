# ADR0006: An autonomous SoC for a complete small model

## Status

Logical target decision; detailed executable and physical qualification remain
OPEN. The normative target is [CoralNPU SoC v 0.1](../spec/coralnpu_soc.md).

## Context

The objective is open hardware that autonomously runs a complete small pretrained
model and progresses through fabrication and silicon validation. ADR0005's
complete-model engineering fixture and the standalone CoreAXI experiment define
useful boundaries, but neither defines a self-booting physical chip.

The public [workload profile](../../workloads/coralnpu_llm/profile.json) and
[analytical worksheet](../../explore/coralnpu_llm/README.md) provide a concrete
starting point: the complete stories260K FP32 model is 1,056,540 bytes including
its header/RoPE, and a 40-position KV cache is 51,200 bytes. A 1 MiB memory cannot hold
even the entire source model. Its trained context is 512; supporting 40 positions
limits request length without truncating layers or modifying trained weights.

## Decision

Select the complete stories260K model as the first-silicon acceptance anchor,
without a practical dialogue-quality claim. One CoralNPU RV32/RVV core owns
scalar control, tokenization, complete prefill/decode and detokenization. Use the
pinned native `RvvCoreMiniAxi` with 8 KiB ITCM and 32 KiB DTCM; add 16 KiB boot ROM and
64 KiB working SRAM. The configuration and its distinct addresses are source-linked
in [the target memory map](../spec/coralnpu_soc.md#5-address-space-and-storage-budget).

Use physical 4 MiB serial NOR for firmware, all model tensors and tokenizer, with
an on-chip SPI/quad controller, XIP/read buffering and actual serial I/O pads.
Provide an autonomous subordinate-CSR boot sequencer, ROM validation/recovery,
AXI fabric/MMIO, UART/GPIO, timer/interrupt/watchdog and JTAG scan/SRAM MBIST.
The board supplies clock/reset supervision/power, NOR and connectors. Stream
full diagnostic logits rather than retain an entire logit history on chip.

The operating budgets in target §6 deliberately favor finite demonstrable
operation over a throughput promise. They require measurement before executable
freeze. Logical topology is defined now; process, macro, pin, timing and software
qualification follow as explicit gates.

## Alternatives and consequences

Keeping highmem's 1 MiB ITCM plus 1 MiB DTCM would inherit a simulation capacity without
establishing physical SRAM suitability. The smaller native variant plus working
SRAM uses 104 KiB of named writable arrays, but needs new map/boot/ISA/integration
qualification. No highmem acceptance or memory-byte-to-area inference transfers.

DDR or other external working RAM adds controller/interface and board obligations
that this bounded workload does not require. Serial NOR reduces that interface
scope at the cost of repeated weight and instruction traffic: at the proposed
quad 12.5 MHz point, 6.25 MB/s is only a raw payload ceiling, not sustained bandwidth.
Its controller, pad timing and selected device still require real qualification.

A separate control CPU adds interprocessor boot, ABI and verification costs;
CoralNPU's scalar execution path is the recommended control owner. A larger model
would add memory/operator/qualification cost without serving this first-silicon
objective. Complete scalar FP32 correctness remains the baseline; RVV speedup is
optional until qualified. Unsupported instructions or library arithmetic require
resolution, not a weakened numerical gate.

A process route must supply usable SRAM/ROM/I/O implementations and accepted
signoff evidence. Open-tool/open-PDK feasibility is the preferred first assessment,
not a foundry or spending selection. If macro ports, memory fit, software fit or
operating budgets fail, revise the affected architectural decision explicitly.
Do not hide the failure by substituting host execution or a chopped model.

The older [CoreAXI](../spec/coralnpu_external_memory.md) and
[complete-model](../spec/coralnpu_llm.md) experiment contracts remain unchanged.
This target introduces autonomous physical boot, a different core/map, on-chip
text processing and streamed output; all need independent contracts and evidence.
The [silicon lifecycle](../SILICON_LIFECYCLE.md) governs the separate physical,
manufacturing and post-silicon decisions. Publishing this design closes none of
those execution or physical gates by itself.
