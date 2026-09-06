# LLM SoC resource and execution-cost budget

2026-09-05 · architecture arithmetic, not a simulator or silicon measurement. Reproduce: `python3 explore/llm-soc-v1/budget.py`; output budget.json. Inputs are reviewed host-probe shape/count results and prior analytical Qwen3 estimates; no runtime model or DUT implementation is written here.

## SIM-L1 selected resources

| Resource | Required payload / chosen capacity | Basis |
|---|---|---|
| Model INT8 matrices |259328B| real shapes; all learned projections incl tied head |
| Row-local FP32 scales |16608B|4152groups×4; G64 tails supported |
| FP32 norm gains |2816B|11×64×4 |
| Model payload / new ABI blob |278752B /280320B|64-byte header+47×32 directory; data naturally4-aligned |
| Model aperture |4MiB| simulator capacity with room for artifact/debug variants; not SRAM allocation |
| KV FP32512positions |655360B|2×5×512×32×4;48positions61440B |
| Original host nonKV scratch |20832B| measured allocation identity from software intake; not compiled RV32 stack |
| Embedded row temporary |256B| row dequantization can avoid host's131072B full expanded table |
| ROM / firmware SRAM |64KiB /256KiB| selected implementation caps; ELF/stack fit gate still required |
| NPU activation / weight buffer |4096B /at least64B| maximum opcode K and16beat burst |
| NPU grouped output at largest L1 call |2048B|512head rows×1group×4; allocated64KiB |
| NPU scratch / KV / expected apertures |1MiB each| static ranges; actual blob footprint separately reported |
| External simulation backing |16MiB| allocated host memory, not a physical DRAM controller claim |

NPU full-run matrix calls=1728, actual INT8 MAC=12447744, group results=199296words. Every forward scans259328weight bytes, reads2844activation bytes, and writes16608group-result bytes:278780B minimum NPU AXI traffic. CPU reads output/scales and performs quantization, norm, attention/KV, nonlinear math, code fetches and validation on top of that. The traffic model deliberately does not count these as zero; they are unmeasured and therefore a missing additive cost, not an inferred speed.

Four products/step give64832ideal compute cycles/forward (1.29664ms at50MHz); AXI independent R/W channels permit a parallel-service bandwidth lower bound max(262172/4 read,16608/4 write)=65543cycles (1.31086ms), before channel turnarounds, padding/fetch scheduling and CPU contention. If a target serializes read/write data service, the corresponding bound is69695cycles (1.3939ms); that additional serialization is not mandated by this AXI contract. One-product version needs259328cycles; eight-products nominally reduce compute but the same32-bit port remains the bottleneck. Four is selected because it matches raw byte delivery and avoids buying unfeedable multipliers. These are lower bounds, not a promised token rate. NPU local buffers, four multipliers and accumulators have no measured cell area or timing.

The uncached soft-float RV32 CPU can dominate total execution despite few mathematical FLOPs: exp/sqrt/division and scalar traffic are expensive operations. Hardware opcode and source choice are fixed for the implementation attempt; SW must supply real RV32 link size, stack high-water and simulated cycles before calling L1 executable. The48-forward acceptance case remains intact; if too slow, retain it as a full scheduled gate and use B1 plus one-forward tests for developer iteration, not as substitute acceptance.

## Simulation cost and control

budget.json includes sensitivity scenarios:10^8/10^9/10^10 DUT cycles at10^5/10^6/10^7 simulated cycles/s correspond to1s..100000s. Neither axis is measured; host C timing with file I/O is not a CPU-cycle calibration. First B1/full-forward implementations must measure simulator cycles/s, instruction count, NPU cycles, CPU scalar cycles, trace bytes and wall time. For the first full L1 run use a watchdog of10^10 DUT cycles and6h wall time; report timeout as incomplete, record last progress, and revise execution strategy with evidence. Bus65536-cycle and NPU2^28-cycle watchdogs are independent functional contracts and may not be disabled to finish a run.

Full traces should be chunked by forward/matrix and retain checksummed raw artifacts. Per-group trace199296words alone is797184B for this case; raw AXI traces can be far larger because every beat has multiple fields. Record trace on/off walltime separately; do not publish trace-free speed from a traced run or vice versa.

## P1 1.7B product study, same family and distinct profile

Prior Qwen3-1.7B W4/group128 scales16bit/KV16bit/context2048 analysis gives887355392B weights,234881024B KV,1122355200B modeled bytes/token and1955332096MAC/token;20token/s needs22.447104GB/s *before* unmodeled traffic.1024-token prefill useful MAC=1503608438784;3s needs0.5012TMAC/s useful rate. These Qwen assumptions are not validated quantization or the SIM-L1 numerical format. No Qwen checkpoint inference ran in this architecture task.

Select budget point B for continued P1 study: target1TMAC/s peak and32GB/s effective external memory. A candidate compute organization is2048MACs reconfigurable between32×64 output-stationary prefill and64outputs×32-way reduction decode. A nominal500MHz compute domain gives1.024TMAC/s; separate512-bit AXI at800MHz has51.2GB/s raw, requiring62.5% delivery efficiency for32GB/s. These are explicit architecture assumptions, not closed clocks, valid timing crossings or chosen IP. An8MiB banked scratchpad and at least2GiB external addressable capacity are the next DSE candidate, not approved SRAM macros/board resources. Capacity2GiB covers the present1.122GB weight+KV floor with provisional scratch/runtime margin but must be rebuilt from real live tensors.

P1 block additions: vector unit for RMSNorm/RoPE/SwiGLU/residual/requant; attention engine for QK, stable softmax and PV with GQA reuse; banked tile SRAM and bank/port arbiter; wider DMA with explicit IDs, multiple outstanding reads and write completions; command queue/completion ring; CPU control firmware; actual DRAM controller/PHY; Caliptra S1 security domain. P1 must keep attention/KV movement and vector work off the slow SIM-L1 soft-float path to meet its stated budget. CPU tokenizer/scheduling and any fallback remain counted.

P1 command ABI will be a separate major version containing GEMM_TILE, GEMV_QUANT, RMSNORM, ROPE, ATTENTION_CAUSAL, SWIGLU, RESIDUAL and FENCE_COMPLETION. Existing opcode1 remains a diagnostic exact-integer mode rather than being silently reinterpreted. Each extension needs explicit layout, format, accumulator, rounding, saturation, approximation error and memory visibility contract derived from real mixed-precision probes. W4A16/FP32acc/KV16 is the study candidate; there is no claim of its quality today. Grouped output transport may move inside hardware postscale to avoid CPU round trips. Changes affect independent golden models, compiler lowering, driver scheduling, traces, all operator DV and DMA/formal proofs.

Memory-controller/PHY type, board, PDK, SRAM macro, package/pins, voltage, power/area target, CDC/RDC, ECC, thermal budget, DFT/scan/MBIST and security physical roots remain explicit P1/F1 decisions. No absolute silicon-area or power estimate can be justified from this first functional profile. SIM-L1 does not freeze them by inheritance from the old50MHz sky130/TinyTapeout study.
