# SIM-L1 bound workload and software probe evidence

Version1.0-rc3. [profile.json](profile.json) binds exact32prompt IDs,16greedy output IDs, shape, runtime/model revisions and downloaded-file hashes. [B1 fixtures](b1-fixtures.json) fix two distinct complete signed arithmetic transactions, one polling and one IRQ; padding is deliberately nonzero to expose accidental padded MACs. Examples are specification data, not a generated testbench/golden implementation.

Select stories260K group64-tail with CPU FP32 scalar/attention and NPU INT8 learned matrices. The fixed checkpoint SHA256 is b0a507e7ad0f626624f17112325e66691f9076d622e1d3274d103d00299f2696; tokenizer binary SHA256 is037cb335abb25d1fa9e8ecae30ed2a3a8ace9302862ebcdc05d51a6bbb10c312. Runtime llama2.c commit350e04fe35433e6d2941dce5a1f53308f87058eb; tinyllamas revision0bd21da7698eaf29a0d7de3992de8a46ef624add. Runtime and model repository declare MIT in pinned source metadata; tokenizer has no separately authored license document. Official URLs and full source hashes are in profile.json / reviewed [provenance](../../docs/spec/llm-soc-v1/intake/sw-provenance.json).

The first32IDs include BOS and are truncation of a41-token source prompt, ending after “play ”. Fixed greedy output text is “outside. One day, she went to the park”. The16exactIDs are authoritative; readable text does not substitute for tokenizer identity. No RNG, top-p, early EOS or implicit extra output token. Positions0..31 consume prompt; positions32..47 consume generated tokens0..15, and the last forward is checked but does not publish token16.

Reviewed [software report](../../docs/spec/llm-soc-v1/intake/sw-REPORT.md), [metrics](../../docs/spec/llm-soc-v1/intake/sw-metrics.json), [raw candidate](../../docs/spec/llm-soc-v1/intake/sw-group64.json) and [tail reproduction](../../docs/spec/llm-soc-v1/intake/sw-upstream_tail_metrics.json) are evidence handoffs. Architect read these pure documents/JSON, not implementation C/RTL/DV. Source implementation paths in those reports are provenance for downstream authorized owners.

Actual owner-reported tool summaries:

```text
INDEPENDENT_INTEGER_CHECK_PASS mode=group64 calls=1728 dots=199296
INDEPENDENT_INTEGER_CHECK_PASS mode=perrow calls=1728 dots=168576
HOST_REFERENCE_PROBE_PASS fp32_forward=48 candidates=2 autoregressive_tokens_each=16 quality_gate=UNDEFINED hardware_gates=NOT_RUN
UPSTREAM_FP32_BYTE_COMPARE_PASS bytes=172032
UPSTREAM_TAIL_PROBE_COMPLETE real_input_nonzero_tail=44 quantized_nonzero_tail=0 input_k=172 group=64
UPSTREAM_TAIL_DEFECT_REPRODUCED
```

These checks include independent NumPy quantization/group-dot/postscale reconstruction, not an independent full nonlinear/attention implementation. The pinned unmodified FP32 source wrapper matches all172032checkpoint bytes. Upstream runq's incomplete172tail and flattened group/row mismatch were reproduced with real input; it is not the selected reference algorithm. The corrected candidate writes each row-local group, including tail44.

Group64 fixed-trajectory logits maxabs0.448473/RMSE0.122319/relativeL2 1.3115%; KV maxabs0.213680/RMSE0.023627. FP32 and two quantized candidates produce16/16same output IDs and48/48same top1 for this one prompt. Perrow has slightly lower logits RMSE and less scale traffic; G64 has smaller maximum KV error here. No perplexity, broader prompt suite, target quality threshold or product model validation is established. Cross-library target conformance tolerances in workload.md are separate engineering criteria, not these quantization differences.

Host timing/RSS have instrumentation, original-FP32 mappings and embedding expansion overhead; they do not estimate RV32/NPU speed or SRAM. Architecture budget uses exact shape/payload counts and reports missing CPU costs explicitly. Root separately reported a clean-output host replay matching all five172032B numerical checkpoint files and199296group dots; that is corroborating host evidence, not architect-executed or hardware testing.

Target deployment artifacts remain downstream SW deliverables: model blob in LLM-06 format, CRC manifests, input header, sparse CPU expected container, ROM/ELF and strict RV32 soft-float kernels. The probe's raw blob is not falsely described as already matching the new deployment ABI. Independent vplan must compare actual DMA arithmetic and the fixed model path before B1/L1 can pass.
