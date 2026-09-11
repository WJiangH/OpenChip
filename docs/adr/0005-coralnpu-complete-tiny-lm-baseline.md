# ADR 0005: Complete tiny-LM baseline before SoC expansion

Status: proposed engineering baseline; execution readiness OPEN.

## Context

The [CoralNPU external-memory contract](../spec/coralnpu_external_memory.md)
exercises bounded compiled programs on the standalone CoreAXI boundary. That
scope does not establish full pretrained-model generation. Complete generation
requires all operators, trained tensors, KV state, full logits and target-owned
autoregressive feedback, with independent numerical checks.

## Decision

Use the entire pretrained `karpathy/tinyllamas/stories260K` as the first
[engineering workload](../../workloads/coralnpu_llm/README.md), with unchanged
pinned `RvvCoreMiniHighmemAxi` hardware and a separately qualified behavioral
external-memory map. This is the least-cost complete baseline among the inspected
candidates, not a claim of useful dialogue quality or global model minimality.

| Candidate | Source-backed consideration | Disposition |
|---|---|---|
| stories260K | Complete five-layer model; custom 512 vocabulary; expected FP32 binary 1,056,540 bytes; MIT model card | Initial complete-loop baseline |
| stories15M | Same publisher family; expected binary 60,816,028 bytes; larger head | Later scale/quality experiment |
| TinyStories-1M | Public config: GPT-Neo, width 64, eight layers, vocabulary 50,257; no license field observed in metadata | Larger head and different operators; name alone is not a total parameter census |
| Gemma-3-270m-it | Publisher reports 268,098,176 BF16 parameters; manual access gate; unauthenticated config retrieval denied | Separate prospective model target; architecture and acquisition remain OPEN |

Pinned publisher metadata/source references are in the [profile](../../workloads/coralnpu_llm/profile.json).
Gemma's exact census expands to 1,072,392,704 FP32 bytes,1,349,120 bytes below 1 GiB
before KV/code/scratch. A nominal 270M calculation cannot determine exact fit.
No source-clone architecture is substituted for the unavailable pinned config.
The existing [TinyStories INT8 profile](../../workloads/tinystories/profile.md)
remains a distinct analytical workload; its target and idealized performance
assumptions do not become CoralNPU implementation results.

## Consequences

The [new draft contract](../spec/coralnpu_llm.md) separates artifact intake,
independent reference, emitted-ISA qualification, measured cost pilot and complete
execution acceptance. Missing numerical limits, token IDs, memory ABI or supported
operations block execution readiness. A draft architecture review can proceed
without declaring those prerequisites complete.

Standalone CoreAXI plus behavioral memory is not a complete SoC. A subsequent
SoC contract must select actual host/ROM boot, image validation, interconnect and
memory ownership, controller/PHY/device for real DRAM, clock/reset crossings,
interrupt/error routing, coherency/DMA policy, completion and security boundaries.
A TL-UL wrapper or DDR-named port supplies none of these automatically. Owners,
independent reviewers and exact acceptance evidence are required for each stage.
Product quality, latency, power/area/frequency, physical technology, FPGA and
tapeout decisions remain separate. Existing accepted claims are not reopened or
broadened by this draft; changing their dependencies requires impact review.
