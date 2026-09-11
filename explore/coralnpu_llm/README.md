# Complete tiny-LM analytical worksheet

Run `python3 explore/coralnpu_llm/calculate.py` from the repository root. This
standard-library calculation does not download artifacts, execute a model,
compile software or run a simulator. The pinned training settings and source in
[the profile](../../workloads/coralnpu_llm/profile.json) supply its dimensions;
actual checkpoint intake and target allocation remain separate checks.

For width d=64, FFN m=172, layers L=5, KV width k=32, vocabulary V=512:

- Unique parameters: `V*d + L*(2*d*d + 2*d*k + 3*d*m + 2*d) + d` =260,032.
- FP32 parameter payload:1,040,128 bytes. Legacy header28 and RoPE tables16,384
  produce the complete1,056,540-byte file, exceeding1 MiB by 7,964 bytes.
- KV at capacity 40: `2*L*40*k*4` =51,200 bytes.
- One512-entry FP32 logit vector:2,048 bytes; forty vectors:81,920 bytes.
- Serial scratch: four64-vectors (x, two residual/projection buffers, Q), two
  32-vectors (K/V), two172-vectors (FFN),8×40 attention entries and 512 logits:
  5,984 bytes. Scalars, stack, alignment and guards are additional. Actual code
  must prove last-consumer reuse rather than assuming this schedule was measured.

Linear work per evaluated position is 259,328 MACs, including the complete output
head. Causal attention adds640×retained_positions, at most25,600 at capacity 40.
The actual workload cap is 39 evaluations per run; using forty positions per run
for two runs deliberately overbounds work by 22,794,240 MACs and logits by 163,840
bytes. Full logits at intermediate prefill positions are intentional evidence,
so a runtime omitting those projections does not satisfy this workload.

A conservative streamed linear-weight estimate is 1,037,312 bytes per evaluated
position, excluding instruction traffic, norms, activation/KV traffic, reloads
and bus overhead. At capacity 40, a position also requires up to 1,600 attention
exponentials,860 SiLU exponentials and 11 square-root operations. Low operation
counts do not imply low software cost for these functions. **No cycles, wall time,
tokens/s or PPA result is derived here.** Use the separately bounded RTL-COST pilot
in the [contract](../../docs/spec/coralnpu_llm.md).

The calculated2 MiB regions are budgets with non-overlapping RV32 endpoints,
not proven code/stack/liveness fit. The128 KiB results region allows logits and
bounded bookkeeping, not all stage-vector traces; additional target capture
requires a reviewed change. A single inference's target memory is distinct from
host acquisition, framework overhead and independent reference trace memory.
Gemma's publisher census comparison is weight-only and does not establish total
memory fit or operator support.
