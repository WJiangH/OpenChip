# SW implementation review of architecture rc2

2026-09-05 · sw-engineer · bounded specification review, not functional validation. Reviewed `docs/spec/architecture-review-03/{README,CHANGE_ORDER_rc2,workload,npu,system,axi,downstream,dependencies}.md`, relevant `contract.json`, `workloads/llm-soc-v1/{README.md,profile.json}`, and the already frozen software probe/source identities. No RTL/DV, other worktree, downloads, target compilation or tests were read/run. Only this report was added; the original 79 probe artifacts were not changed.

Decision: request three precise specification corrections before declaring the SW numeric/blob ABI closed. The main full-model graph, actual-input integer validator and result-consumption separation are implementable and substantially closed. Findings below are specification discrepancies/omissions; they do not claim a measured DUT failure.

## Findings

### SW-RC2-01 — P1: SiLU operation order differs from the bound software reference

Location: `docs/spec/architecture-review-03/workload.md:13` (LLM-04), used by LLM-12 at lines39/46. Actual pinned source: `sw/llm_probe/vendor/run.c:341-343`, SHA256 `9c4f2d5c6ae01b71726d1cc37530d71e60bff0ec7cc012565f16a43c1ca658bd`.

The contract mandates `SiLU(x)=FP32(x / FP32(1+expf(-x)))`. The bound reference computes the reciprocal first, then multiplies: `val *= (1.0f / (1.0f + expf(-val)));` followed by multiplication with the W3 output. Under the required separately rounded FP32 operations, division x/d and x*round(1/d) are not interchangeable. A faithful firmware implementation and a faithful importer of the published probe therefore implement different scalar contracts, potentially changing subsequent activation quantization near a rounding boundary.

Correction: write `d=FP32(1+expf(-x)); inv=FP32(1/d); silu=FP32(x*inv); hidden=FP32(silu*up)`, retaining no-FMA and no-reassociation. Alternatively explicitly select the direct-division variant and rebind its software numeric reference in a subsequent work item. This review did not execute either alternative and does not assert that the existing tolerance or token sequence already fails.

### SW-RC2-02 — P2: model/expected CRC coverage and authoritative source are not completely specified

Locations: `docs/spec/architecture-review-03/workload.md:19` (model CRC from “run manifest”), line23 (input-header model_crc32/expected_crc32/expected_bytes), line34 (expected blob CRC); `docs/spec/architecture-review-03/system.md:57` fixes CRC-32/ISO-HDLC only for firmware payload bytes.

The model has a `blob_bytes` field, the expectation blob has its own `blob_bytes`, and the input header has `expected_bytes`, but no normative sentence defines the byte interval protected by either model/expected CRC or requires `expected_bytes == expected.header.blob_bytes`. LLM-06 additionally names a run manifest as the model CRC source without a runtime manifest location/format; the concrete runtime input-header field could resolve this cleanly. Independent exporter and firmware implementations could legitimately checksum only tensor data versus header+directory+padding+data, or disagree on padding after blob_bytes, and reject the same otherwise valid image before dispatch.

Correction: explicitly reuse SYS-05 CRC parameters; define model CRC over `[model_base, model_base+validated model.header.blob_bytes)` and expected CRC over `[expected_base, expected_base+validated expected.header.blob_bytes)`, including internal header/directory/padding and excluding arena tail. Require equality of input expected_bytes and expected.header.blob_bytes. Make the LLM-08 CRC fields authoritative at runtime and the host run manifest the provenance copy. Validate lengths before CRC reads. This is an interoperability gap, not a proposal to add authentication.

### SW-RC2-03 — P2: model tensor entry data_bytes needs a definition

Location: `docs/spec/architecture-review-03/workload.md:19` (LLM-06).

The entry defines `data_bytes`, row_stride and a separate scale_offset, but gives no required value for data_bytes or explicit statement whether it includes scale storage. Unlike expectation records (line34: data_bytes=4*element_count), two model exporters can encode different values for the same matrix: INT8 rows alone or INT8+FP32 scales. The loader cannot implement the prescribed malformed-region rejection without selecting a convention. The fixed model's K values are all divisible by four, so tail padding ambiguity is not needed to expose the missing definition.

Correction: define matrix `data_bytes=rows*row_stride` (INT8 values plus row padding only), norm `data_bytes=rows*cols*4`, and scale-region bytes independently as `4*rows*ceil(cols/64)` for encoding1, zero for encoding2. Require directory shape/encoding to match the fixed tensor identity and validate both regions plus header/directory for bounds/nonoverlap. Define any row padding as excluded from quantization/math (already required by LLM-02/NPU-02). This closes serialization; no private ABI should be invented by SW.

## Explicitly accepted closures

- Checkpoint/runtime/tokenizer revisions and hashes, 64/172/5/8/4/8/512 shapes, shared embedding/head, exact prompt/16 output IDs in `workloads/llm-soc-v1/profile.json:5-142` match this round's frozen host evidence. Deployment blobs are correctly identified as downstream outputs, not claimed to already exist in probe format.
- LLM-02/03 correctly bind row-local group64 with tail44, dynamic INT8 activations, all-zero handling, nonfinite/scale-underflow rejection, signed INT32 groups and ordered FP32 postscale. NPU-01/02 support the wider legal signed INT8 range while deployment quantization uses [-127,127]; those scopes are consistent.
- LLM-08 at workload.md:23 exactly matches the executed 48-forward/16-output convention: logits31 selects token0, positions32..47 consume tokens0..15, no seventeenth token emitted. Context512/KV placement and grouped-Y capacity are sufficient for the fixed model, without claiming target runtime allocation has already run.
- LLM-12 at workload.md:41-48 correctly fixes gate=W1, up=W3, both residual sources, norm positions, Q/K-only RoPE, GQA h→floor(h/2), ascending head concatenation, current KV before causal attention and tied head. The specified RoPE reciprocal-then-position multiplication matches the frozen runtime. RMSNorm's outer multiplication is equivalent under the specified separate scalar binary32 multiplication; no additional mismatch is alleged there.
- LLM-09/11 at workload.md:25/34 clearly distinguish dynamic CPU integer verification using actual submitted X/W from optional nominal integer diagnostics. They prohibit the verifier from substituting its calculated output for DMA-written Y. Exact group comparison, selected fixed floating checkpoints and all48 independent DV checkpoints remain separate requirements; legal upstream FP32 variation cannot excuse an actual-X/W dot mismatch.
- NPU-08 at npu.md:45 and AXI-08 at axi.md:21 establish compiler barriers, DONE/error/tag checks, response-before-completion and actual output consumption. Scale arrays remain CPU-owned. The command layouts and explicit matrix ordinal/TAG mapping are sufficient for the driver. The raw probe's export order is not assumed to be this new directory/ordinal order.
- Expected-container kind/identity/count mappings, required position selection, kind7 positions31..46, mandatory-record rejection and CPU-only read permissions are clear aside from CRC closure above. The new residual/linear expected records are legitimate downstream generator work; their absence from the earlier probe binary is not itself a spec defect or a reason to expand this review.

Friction:
- The bound scalar SiLU operation order was algebraically simplified in the prose despite strict FP32 ordering being normative.
- CRC coverage and model data_bytes require short explicit serialization rules to avoid independent exporter/loader conventions.

Skill candidates:
- sw-engineer/references/llm-baseline-probes.md — Review fixed floating operation order and every binary length/CRC field against the bound reference before treating a software ABI as implementable.
