# Software baseline handoff

Local candidate, sw-engineer, 2026-09-05. Only `sw/llm_probe/` was written; no RTL/DV was read, no spec/flow changed, no commit/push/remote PR.

Executed real stories260K FP32 and two complete W8A8 static-linear candidates. All consumed 32 nonzero prompt IDs including BOS and 16 generated IDs over 48 full forward calls. Independent unmodified upstream FP32 wrapper matched all 172,032 checkpoint bytes. Group64 with tail44 and perrow both emitted the same 16 token IDs as FP32; fixed-token trajectories still have nonzero logits/KV error. No model quality threshold or broader evaluation has been run.

| Candidate | Fixed-token logits max / RMSE | K/V max / RMSE | Top1 | Generated tokens |
|---|---|---|---|---|
| Group64 + tail44 | 0.448473 / 0.122319 | 0.213680 / 0.023627 | 48/48 same | 16/16 same |
| Per row | 0.516534 / 0.119836 | 0.331371 / 0.028463 | 48/48 same | 16/16 same |

Group64 uses row-local scales, dynamic activation groups, nearest ties away from zero, symmetric [-127,127], all-zero scale1/q0, finite inputs only, exact INT32 dots, FP32 `sum += ((float)acc * sw) * sa` in group order. All 36 static linears per forward use that path. CPU FP32 retains embedding dequantization, RMSNorm, RoPE, attention/softmax/value mixing, SwiGLU, residuals, KV updates, postscales and greedy argmax. The small model has no Qwen3-specific Q/K norm; success does not cover the larger model family.

The unchanged upstream group64 quantizer/matmul was also executed on the real first-layer FFN input. Its 44 nonzero tail values were left as quantized zeros; output max error against FP32 was 0.321632, and the omitted FP32 tail alone contributed up to 0.294181. Its flattened weight groups additionally mismatch row-local dots when K=172. `upstream_tail_metrics.json` distinguishes this actual operator probe from a full-model upstream run.

Group64 model payload: 278,752 bytes. FP32 KV: 1,280 bytes/token, 61,440 bytes used at 48 positions, 655,360 bytes reserved at context512. Upstream activation scratch outside KV: 20,832 bytes. A row-only embedding conversion would require 256-byte scratch, while this host probe holds a 131,072-byte full dequantized embedding. This host also retains the original FP32 mapping; neither overhead is a mandatory chip allocation. `metrics.json` states exact accounting exclusions and records process RSS separately.

Frozen host timing: FP32 prefill32 3.027 ms, decode16 1.705 ms; group64 prefill32 2.446 ms, decode16 1.276 ms. These are single instrumented host observations from CLOCK_MONOTONIC around forward calls. Matrix-trace I/O and counters are included in the candidate; setup/tokenization and per-step logits/KV export are excluded. They are not a fair speedup benchmark and cannot estimate RV32 software float or NPU throughput. Frozen peak process RSS: FP32 2,621,440 bytes, group64 3,096,576 bytes on this macOS host. Measured RSS is not chip SRAM.

At positions0..31 the 32 prompt IDs are consumed. Logits31 selects generated token0. Positions32..47 consume generated token0..15; logits47 is saved but no seventeenth token is emitted. KV therefore includes all 48 consumed positions. Prompt, input, output, sampling and binary checkpoint formats are in README and per-run JSON.

Actual validation summaries (`logs/analysis.log`, `logs/upstream_fp32.log`, `logs/upstream_tail.log`):

```text
INDEPENDENT_INTEGER_CHECK_PASS mode=group64 calls=1728 dots=199296
INDEPENDENT_INTEGER_CHECK_PASS mode=perrow calls=1728 dots=168576
HOST_REFERENCE_PROBE_PASS fp32_forward=48 candidates=2 autoregressive_tokens_each=16 quality_gate=UNDEFINED hardware_gates=NOT_RUN
UPSTREAM_FP32_WRAPPER_PASS forwards=48
UPSTREAM_FP32_BYTE_COMPARE_PASS bytes=172032
UPSTREAM_TAIL_PROBE_COMPLETE real_input_nonzero_tail=44 quantized_nonzero_tail=0 input_k=172 group=64
UPSTREAM_TAIL_DEFECT_REPRODUCED
```

Reproduce: `sh sw/llm_probe/run.sh`. The independent NumPy check validates every exported INT8 weight/scale, activation/scale, INT32 accumulator and FP32 postscale. It does not independently reimplement nonlinear/attention math. Read `README.md` for the proposed layout and unresolved hardware mapping; `metrics.json` for per-step errors and byte scopes; `provenance.json` and `ARTIFACTS.sha256` for identities. Quantization schemes and packed layouts remain software candidates for architect approval.

Relevant repository make gates were not run: these artifacts are host software probes, not target firmware or hardware. In particular `make sw`, ISS/UART, lint, sim, coverage, formal, compliance, synth, timing, FPGA and physical gates are not passed by this handoff. RV32IM soft-float compiler/libm, startup/linker, CPU/NPU ABI and target execution remain required follow-on work.

Friction:
- Upstream group64 code does not support this model's FFN172 row/tail geometry; actual operator reproduction confirmed it.
- Timing includes probe instrumentation, and host RSS includes reference mappings/scaffolding; neither supports chip throughput/SRAM claims.

Skill candidates:
- sw-engineer/references/llm-baseline-probes.md — Validate all reduction and quantization group boundaries, fix complete source identities, and separate fixed-token numeric errors from autoregressive divergence before freezing the runtime contract.
