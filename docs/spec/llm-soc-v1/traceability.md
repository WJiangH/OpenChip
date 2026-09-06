# Requirement traceability obligations

Version1.0-rc4 (change order rc4, proposal pending rc3-reviewer confirmation). Independent verification duties; implementation evidence remains not-run. owner lists are verification-scope participation lists (contract.json owner_modules_semantics).

| ID | Contract | Responsible modules | Independent obligation |
|---|---|---|---|
|AXI-01|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem, rom, sram|Independent channel protocol/order/backpressure/error/timeout checks and assertions|
|AXI-02|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem, rom, sram|Independent channel protocol/order/backpressure/error/timeout checks and assertions|
|AXI-03|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem, rom, sram|Independent CPU/NPU AW-offer ordering without AWREADY dependence, target early-W handshake and stalled payload checks|
|AXI-04|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem|Independent channel protocol/order/backpressure/error/timeout checks and assertions|
|AXI-05|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem|Independent channel protocol/order/backpressure/error/timeout checks and assertions, DECERR-over-SLVERR precedence and foreign-ID SLVERR (rc4)|
|AXI-06|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem, rom, sram|Independent channel protocol/order/backpressure/error/timeout checks and assertions|
|AXI-07|[axi.md](axi.md)|fabric (implements), cpu_bridge, lite_bridge, extmem|Independent per-obligation timer and early-W unknown-address timeout checks; obligation (e) only under the holding-register option; ownerless target VALID is immediate reason6 (rc4)|
|AXI-08|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem, rom, sram|Independent channel protocol/order/backpressure/error/timeout checks and assertions|
|AXI-09|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem|Independent channel protocol/order/backpressure/error/timeout checks and assertions; bridge rejection SLVERR/DECERR split (rc4)|
|AXI-10|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem|Independent channel protocol/order/backpressure/error/timeout checks and assertions|
|NPU-01|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_local, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal|
|NPU-02|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_local, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal|
|NPU-03|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_local, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal|
|NPU-04|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_local, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal; LAST_CYCLES=T-H+1 exact endpoints (rc4)|
|NPU-05|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_local, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal|
|NPU-06|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_local, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal; error terminal after AXI drain only, datapath residue discarded by NPU-09 (rc4)|
|NPU-07|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_local, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal|
|NPU-08|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_local, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal|
|SEC-01|[security.md](security.md)|caliptra, security-controller|Independent authenticated boot negative tests and access-control formal|
|SEC-02|[security.md](security.md)|caliptra, security-controller|Independent authenticated boot negative tests and access-control formal|
|SEC-03|[security.md](security.md)|caliptra, security-controller|Independent authenticated boot negative tests and access-control formal|
|SYS-01|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-02|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-03|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-04|[system.md](system.md)|sys, cpu_bridge, irq, uart, fabric, rom, sram|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-05|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-06|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties; 0xB001/0xB002/0xB003 taxonomy and check order (rc4)|
|SYS-07|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-08|[system.md](system.md)|sys, cpu_bridge, irq, uart, npu_csr, lite_bridge|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties; WO write-1-only SLVERR, BOOT_STAGE/DIVISOR range SLVERR, RESULT_COMMIT repeat SLVERR (rc4)|
|SYS-09|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-10|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-11|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|LLM-01|[workload.md](workload.md)|software-runtime|Independent full-model reference and real firmware checkpoints; no RTL-derived expected values|
|LLM-02|[workload.md](workload.md)|software-runtime|Independent full-model reference and real firmware checkpoints; no RTL-derived expected values|
|LLM-03|[workload.md](workload.md)|software-runtime|Independent full-model reference and real firmware checkpoints; no RTL-derived expected values|
|LLM-04|[workload.md](workload.md)|software-runtime|Independent scalar FP32 sequence including reciprocal-then-multiply SiLU|
|LLM-05|[workload.md](workload.md)|software-runtime|Independent full-model reference and real firmware checkpoints; no RTL-derived expected values|
|LLM-06|[workload.md](workload.md)|software-runtime|Independent fixed tensor shape/data_bytes/scale-region bounds and authoritative model CRC interval checks|
|LLM-07|[workload.md](workload.md)|software-runtime|Independent full-model reference and real firmware checkpoints; no RTL-derived expected values|
|LLM-08|[workload.md](workload.md)|software-runtime|Independent runtime input-header authority and expected_bytes equality checks|
|LLM-09|[workload.md](workload.md)|software-runtime|Independent full-model reference and real firmware checkpoints; no RTL-derived expected values|
|LLM-10|[workload.md](workload.md)|software-runtime|Independent full-model reference and real firmware checkpoints; no RTL-derived expected values|
|LLM-11|[workload.md](workload.md)|software-runtime|Independent expectation bounds and exact header/directory/data CRC interval checks|
|SYS-12|[system.md](system.md)|sys, cpu_bridge, fabric, npu_ctl, npu_dma|Independent fault priority/known-or-zero address, wrapper common reset, core local reset, and retained offered-write stop checks|
|LLM-12|[workload.md](workload.md)|software-runtime|Independent forward graph including gate/up, both residual sources, GQA, RoPE and head concatenation|
|NPU-09|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_local, npu_dot|Independent partition lifecycle checks: dispatch re-arm, C25-before-C13 ordering, dot_lifecycle flush (no result survives a terminal; operand on the C25 edge discarded), dma_terminal level hold/clear, stop-without-error stays BUSY|
|SYS-13|[system.md](system.md)|cpu_bridge, cpu|Independent native-port protocol checks: payload hold until mem_ready, single registered mem_ready per transfer, no mem_ready on failure, back-to-back mem_valid, strobe/read-write decode; pinned PicoRV32 README sections as reference|
