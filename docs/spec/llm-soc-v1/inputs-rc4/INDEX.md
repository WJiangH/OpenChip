# run003 issue index — for chief-architect ruling (Astra side)

Generated 2026-09-06T04:32:25Z. One line per issue id found in the delivered ISSUES.md files; full text in the files listed. Disposition column to be filled by the architect; rulings land as commits on the baseline branch.

| id | file | headline | proposed disposition (orchestrator, non-binding) |
|---|---|---|---|
| ISSUE-cpu_bridge-01 | ISSUE-cpu_bridge-01to03.md | ISSUE-cpu_bridge-01 — native handshake semantics are not specified anywhere | |
| ISSUE-cpu_bridge-02 | ISSUE-cpu_bridge-01to03.md | ISSUE-cpu_bridge-02 — AXI-07 lists `cpu_bridge` as an owner module, SYS-12 gives the timer to the fabric | |
| ISSUE-cpu_bridge-03 | ISSUE-cpu_bridge-01to03.md | ISSUE-cpu_bridge-03 — one-cycle window where the bridge may still accept a native request after a *foreign*  | |
| ISSUE-fabric-01 | ISSUE-fabric-01to05.md | ISSUE-fabric-01 — precedence between DECERR (mapping/permission) and SLVERR (unsupported attribute) | |
| ISSUE-fabric-02 | ISSUE-fabric-01to05.md | ISSUE-fabric-02 — AXI-07 obligation (e) is unreachable when AXI-03's backpressure option is taken | |
| ISSUE-fabric-03 | ISSUE-fabric-01to05.md | ISSUE-fabric-03 — response for an AXI ID that is not the port's fixed source ID | |
| ISSUE-fabric-04 | ISSUE-fabric-01to05.md | ISSUE-fabric-04 — no source/channel attribution for a target response with no live transaction | |
| ISSUE-fabric-05 | ISSUE-fabric-01to05.md | ISSUE-fabric-05 — "stop on the fatal detection edge" vs "a handshake on the threshold edge wins" | |
| ISSUE-lite_bridge-01 | ISSUE-lite_bridge-01to02.md | ISSUE-lite_bridge-01 — response code for a transaction the bridge rejects without issuing a Lite request | |
| ISSUE-lite_bridge-02 | ISSUE-lite_bridge-01to02.md | ISSUE-lite_bridge-02 — a single-beat write whose W beat does not assert WLAST | |
| ISSUE-mem-01 | ISSUE-mem-01.md | ISSUE-mem-01 | |
| ISSUE-npu_csr-01 | ISSUE-npu_csr-01.md | ISSUE-npu_csr-01: which module validates the NPU-01/02 descriptor? | |
| ISSUE-npu_ctl-01 | ISSUE-npu_ctl-01to02.md | ISSUE-npu_ctl-01: does npu_ctl own the K/N/G "group loop", or does npu_local? | |
| ISSUE-npu_ctl-02 | ISSUE-npu_ctl-01to02.md | ISSUE-npu_ctl-02: which edge is "submit acceptance" for LAST_CYCLES? | |
| ISSUE-npu_dma-01 | ISSUE-npu_dma-01to05.md | ISSUE-npu_dma-01 — internal partition port names are not in the machine ICD | |
| ISSUE-npu_dma-02 | ISSUE-npu_dma-01to05.md | ISSUE-npu_dma-02 — dma_terminal has no handshake and no pulse/level rule | |
| ISSUE-npu_dma-03 | ISSUE-npu_dma-01to05.md | ISSUE-npu_dma-03 — where the output write buffer lives | |
| ISSUE-npu_dma-04 | ISSUE-npu_dma-01to05.md | ISSUE-npu_dma-04 — "issues no memory request until both handshakes finish" | |
| ISSUE-npu_dma-05 | ISSUE-npu_dma-01to05.md | ISSUE-npu_dma-05 — no terminal is defined for stop without a DMA error | |
| ISSUE-npu_dot-01 | ISSUE-npu_dot-01.md | ISSUE-npu_dot-01 — no way for npu_dma to know npu_dot still holds an unconsumed result | |
| ISSUE-npu_dma-01 | ISSUE-npu_local-01to03.md | ISSUE-npu_dma-01 (partition port names) applies to this module too. | |
| ISSUE-npu_local-01 | ISSUE-npu_local-01to03.md | ISSUE-npu_local-01 — W_STRIDE is declared known to local but is unusable there | |
| ISSUE-npu_local-02 | ISSUE-npu_local-01to03.md | ISSUE-npu_local-02 — reset of the 4096-byte activation store | |
| ISSUE-npu_local-03 | ISSUE-npu_local-01to03.md | ISSUE-npu_local-03 — how local recovers after an aborted command | |
| ISSUE-sys-01 | ISSUE-sys-01.md | ISSUE-sys-01: RESULT_COMMIT repeat-write response is not explicit | |
| ISSUE-uart-01 | ISSUE-uart-01.md | ISSUE-uart-01: DIVISOR "legal 2..65535" — documentation or hardware-enforced range? | |
