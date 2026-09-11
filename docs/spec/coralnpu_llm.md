# CoralNPU complete tiny-LM generation contract

## 1. Status and references

Version 0.1, **DRAFT_NOT_EXECUTION_READY**. This contract defines an engineering
baseline and prerequisite evidence; it reports no model or DUT execution result.
The [workload/profile](../../workloads/coralnpu_llm/README.md),
[analytical worksheet](../../explore/coralnpu_llm/README.md) and
[ADR 0005](../adr/0005-coralnpu-complete-tiny-lm-baseline.md) are part of this draft.
Each requirement below names its owning subject. OPEN items in §7 block an
executable freeze; implementers must not guess them. After freeze, behavioral
changes require a versioned architecture change and affected-role review.

## 2. Artifact and graph identity

**CLLM-01 (artifact owner)** shall verify actual bytes against the complete
publisher revision, expected sizes and hashes in
[profile.json](../../workloads/coralnpu_llm/profile.json), retaining every trained
layer/head/vocabulary entry. Reject malformed, short, trailing or nonfinite model
files, changed dimensions or substituted weights. Source metadata hashes alone
are not local artifact verification. Initial intake excludes `.pt` and pickle
execution; tokenizer/dependency notices must be resolved independently.

**CLLM-02 (artifact owner)** shall confirm the legacy seven-int32 little-endian
header `(64,172,5,8,4,512,512)`, positive vocabulary/tied-head flag, full tensor
order/extents and stored RoPE tables against the pinned export description. The
expected 260,032 unique FP32 parameters derive from published training settings;
acquisition must confirm the census. The entire 1,056,540-byte source binary
remains in external memory, including 28 header and 16,384 RoPE-table bytes; the
output head aliases the embedding. No host-created activation or KV is loaded.

**CLLM-03 (software owner)** shall implement the complete following graph on target,
map every operation/ABI/library call to a supported path, and qualify the actual
linked ELF/instruction census rather than inferring ISA support from flags:

1. Embed the input token with the tied 512×64 matrix.
2. For each of five layers: attention RMSNorm; Q/K/V projections; RoPE on Q/K;
   append current K/V; causal GQA scores; max-subtracted softmax; weighted V;
   output projection and residual; FFN RMSNorm; W1/W3; SiLU(W1)×W3; W2 and residual.
3. Final RMSNorm, full 512-logit projection and greedy selection.

Width 64, FFN 172, query/KV heads 8/4 and head width 8 apply throughout. Biases are
absent; dropout is off. RMS epsilon is 1e-5; RoPE theta 10000 uses adjacent even/odd
pairs and the stored tables for positions 0..39. Query head h uses KV head floor(h/2);
attention scores divide by sqrt(8) and include positions 0..current only. There is
no final vocabulary softmax requirement for argmax. Pinned architecture/export
sources in the profile define tensor ordering; emitted instructions, software
math and conversion behavior still require qualification. No host offload can
satisfy this requirement. Initial scalar FP32 avoids assuming an RVV speedup.

## 3. Address space and loading

This is a new **2 MiB** behavioral external aperture, not an enlargement of the
accepted fixed-map CN-EXTMEM-01 profile. Intervals are half-open and little-endian.
Budgets are proposed allocation ceilings, not evidence that an ELF fits.

| Interval | Budget | Purpose |
|---|---:|---|
| [0x20000000,0x20040000) | 256 KiB | All executable startup/operator/trap/math code and immutable constants |
| [0x20040000,0x20180000) | 1,280 KiB | Entire model binary; immutable after release |
| [0x20180000,0x20190000) | 64 KiB | KV, capacity 40 |
| [0x20190000,0x201a0000) | 64 KiB | Explicit scratch/BSS, no hidden allocator |
| [0x201a0000,0x201c0000) | 128 KiB | Up to 40 complete logit vectors, tokens, progress and completion |
| [0x201c0000,0x201d0000) | 64 KiB | Prompt IDs, descriptor and run identity |
| [0x201d0000,0x20200000) | 192 KiB | Reserved; no accesses |

**CLLM-04 (software and DV owners)** shall freeze exact object offsets/lengths,
16-byte before/after guards for mutable arrays, record ABI and trap/return
placement before execution. Validate PT_LOAD vaddr=paddr, region permissions as
experiment policy, no overlap, 32-bit sizes/pointer products and endpoints using
wider validation arithmetic. Reject budget overflow; do not silently enlarge
regions. Keep ITCM unused and DTCM limited to the 16 KiB stack at
0x001fc000–0x001fffff, initial SP 0x00200000, with ordinary spills allowed. Verify
stack guards/high-water and actual scratch liveness. No duplicate weight array
or TCM operand shadow is permitted. No memory protection hardware is implied.
The results region covers full logits plus bounded progress/records, not arbitrary
stage-vector dumps; additional target evidence needs a reviewed budget/map change.
Independent host reference traces have a separate host-output budget.

The selected unchanged hardware identity, port widths and host CSR/reset protocol
are [CN-EXTMEM-01 §2/§4](coralnpu_external_memory.md); its old operand/program
placements do not apply here. Actual generated core, toolchain, ELF, map,
responder, artifacts and contract identities must be bound in each run receipt.

## 4. Complete generation and numerical evidence

**CLLM-05 (workload owner)** shall freeze two UTF-8 prompts, exact IDs, tokenizer
version, BOS/EOS policy and complete reference traces before scoring. Batch 1,
input length≤32 including specials, new-token cap 8, capacity 40. Early EOS stops
normally, but each acceptance fixture must emit at least 5 tokens, demonstrating
four actual feedback decode evaluations after prefill. Select adequate fixtures
before DUT work; never force continuation to meet coverage.

**CLLM-06 (target software)** shall evaluate every prompt position (serial prefill
allowed), retain all five layers' KV, select the first token from final-prefill
logits, then repeatedly feed its own chosen token back and update KV. Greedy ties
select the lowest ID. Only tokenizer/detokenizer/loading/observation are on host.
Retain all 512 logits at every evaluated prefill/decode position, exact chosen
IDs, per-layer/per-position progress and final state. Four emitted tokens alone
prove at most three feedback decode evaluations.

**CLLM-07 (independent reference/verification owner)** shall derive a complete
oracle from the pinned graph and trained tensors independently of target SW.
Compare every finite logit, exact tokens, decoded bytes and termination. Use
teacher-forced frozen prefixes to localize numerical errors and separately verify
free-running target feedback; teacher forcing cannot satisfy generation. Report
maximum absolute/relative errors, top-two margins and first divergence. Produced
NaN/Inf or any token mismatch rejects acceptance. Near ties require investigation,
never output-dependent tolerance relaxation.

Proposed arithmetic is FP32 weights/KV/activations, IEEE754 nearest-even rounding,
no quantization, no fast-math reassociation and ascending-index separate
multiply/add reductions without contraction. Actual FMA/underflow policy,
sqrt/exp implementation, RoPE-table agreement, per-stage atol/rtol and final-logit
limits are **OPEN** until independent numeric evidence and an architecture-owned
reviewed revision freeze them. This is not a bit-exact implementation claim;
no arbitrary tolerance is supplied as a substitute for qualification.

**CLLM-08 (DV owner)** shall demonstrate checker rejection of mutated inputs or
weights, missing layer/step/logit, stale run IDs/results and broken KV feedback.
Synthetic checker controls are not accepted model variants. Require manager
instruction and per-layer weight reads, KV/output writes and progress; corroborate
with independent source/disassembly review because traffic alone is not retirement
or proof of complete graph execution. No expected answers are loaded into DUT.

## 5. Boot, terminal, error and integration boundaries

**CLLM-09 (loader/DV owners)** shall cold-load ELF/model/prompt/descriptor during
reset, zero mutable state and initialize guards, then use the real subordinate
CSR release sequence. Direct behavioral-memory initialization is a simulation
privilege, not production boot evidence. Disable host mutation after release.
Require completion magic after all outputs, acknowledged writes, matching separate
`_ret`, clean halt/status, bounded drain and no guard/model writes. Exact record
ABI, deadline and drain cycles remain OPEN. Reset starts a new epoch, discards
pending transactions and requires fresh run IDs/KV; preceding partial work never
counts toward success.

**CLLM-10 (integration owner coordinating independent DV)** shall obtain separately
authored DV profiles for malformed/short model and bad-token rejection,
out-of-map accesses, errors in code/weight/KV/output transactions, timeout/stall,
reset during prefill/decode and recovery to a fresh valid run. Architecture must
freeze injection points and expected rejection/fault behavior before DV authors
implement them. Existing bounded external-memory results do not substitute for
these new-map profiles or establish full AXI/ISA/coverage closure.

This scope is standalone CoreAXI plus behavioral memory. Full SoC boot,
interconnect, real memory controller/PHY, clocks/resets, interrupt/error routing,
coherency/DMA and security need a subsequent contract and independent acceptance
as described in ADR 0005. No SoC, FPGA, PPA or tapeout claim follows here.

## 6. Staged feasibility limits

The following are proposed per-stage limits, not run authority. Each stage needs
its prerequisites and a separately authorized owner; stop on a failed limit or
missing dependency, with no automatic installation or retry.

| Stage | Proposed bound | Required evidence |
|---|---|---|
| MODEL-INTAKE | Three non-pickle artifacts; 2 MiB download total including refreshed metadata; 60 s; 1 CPU; 256 MiB RSS; 4 MiB output | Actual hashes/header/tensors/tokenizer metadata and notices |
| MODEL-REFERENCE | Two prompts≤40 evaluated positions each; 60 s; 1 CPU; 2 GiB RSS; 16 MiB output; existing dependencies only | IDs, numeric traces/margins, EOS adequacy and proposed justified limits |
| SW-ISA | Cached compiler; 60 s; 2 CPUs; 2 GiB RSS; 64 MiB output; no RTL regeneration | ELF/map/ABI/instruction/math qualification, not a DUT verdict |
| RTL-COST | After environment reservation/preflight; 60 s or 500,000 cycles, first reached; ≤4 CPUs and existing 12 GiB container cap; 32 MiB logs; waveforms off | Completed/partial/timeout classification and measured phase costs |

Full-generation run limits remain OPEN until the pilot establishes actual
simulator throughput and runtime costs. An INT8 GEMV time or nominal MAC count
cannot establish full FP32 runtime. Retain partial/timeout evidence; changed
scope or another pilot needs a new bounded question and authority.

## 7. Freeze dependencies

Before execution readiness, resolve actual artifact/tokenizer identity and
notices; exact prompts/BOS/EOS; complete independent oracle and numeric limits;
actual supported emitted ISA/math/ABI; ELF/stack/scratch fit and record ABI;
independent error/reset profiles; and measured finite full-run budgets. Software,
model and DV own their independent implementations; the architect owns contract
ambiguities and numerical freeze. Review or publication of this draft closes none
of those execution dependencies by itself.
