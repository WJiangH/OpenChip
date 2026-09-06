# Requirement traceability obligations

Version1.0-rc3. Independent verification duties; implementation evidence remains not-run.

| ID | Contract | Responsible modules | Independent obligation |
|---|---|---|---|
|AXI-01|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem|Independent channel protocol/order/backpressure/error/timeout checks and assertions|
|AXI-02|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem|Independent channel protocol/order/backpressure/error/timeout checks and assertions|
|AXI-03|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem|Independent CPU/NPU AW-offer ordering without AWREADY dependence, target early-W handshake and stalled payload checks|
|AXI-04|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem|Independent channel protocol/order/backpressure/error/timeout checks and assertions|
|AXI-05|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem|Independent channel protocol/order/backpressure/error/timeout checks and assertions|
|AXI-06|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem|Independent channel protocol/order/backpressure/error/timeout checks and assertions|
|AXI-07|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem|Independent per-obligation timer and early-W unknown-address timeout checks|
|AXI-08|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem|Independent channel protocol/order/backpressure/error/timeout checks and assertions|
|AXI-09|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem|Independent channel protocol/order/backpressure/error/timeout checks and assertions|
|AXI-10|[axi.md](axi.md)|fabric, cpu_bridge, lite_bridge, extmem|Independent channel protocol/order/backpressure/error/timeout checks and assertions|
|NPU-01|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal|
|NPU-02|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal|
|NPU-03|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal|
|NPU-04|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal|
|NPU-05|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal|
|NPU-06|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal|
|NPU-07|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal|
|NPU-08|[npu.md](npu.md)|npu_csr, npu_ctl, npu_dma, npu_dot|Independent grouped integer reference, command state/error/reset tests and arithmetic formal|
|SEC-01|[security.md](security.md)|caliptra, security-controller|Independent authenticated boot negative tests and access-control formal|
|SEC-02|[security.md](security.md)|caliptra, security-controller|Independent authenticated boot negative tests and access-control formal|
|SEC-03|[security.md](security.md)|caliptra, security-controller|Independent authenticated boot negative tests and access-control formal|
|SYS-01|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-02|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-03|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-04|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-05|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-06|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-07|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
|SYS-08|[system.md](system.md)|sys, cpu_bridge, irq, uart|Independent boot/reset/CSR/permission/IRQ firmware simulation and applicable formal properties|
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
