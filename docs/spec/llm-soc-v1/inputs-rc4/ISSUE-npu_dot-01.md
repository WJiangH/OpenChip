# npu_dot — spec issues raised during implementation

Spec under implementation: `docs/spec/llm-soc-v1/` 1.0-rc3.
Raised by the RTL author of `hw/rtl/npu_dot/npu_dot.sv`; not resolved in RTL.

---

## ISSUE-npu_dot-01 — no way for npu_dma to know npu_dot still holds an unconsumed result

- **id**: ISSUE-npu_dot-01
- **spec_ref**:
  - `npu.md` §2 NPU-06: *"Only after no offered/accepted transaction or
    unconsumed result remains shall it set BUSY=0,DONE=0,ERROR=1, ERROR_CODE5/6
    and tag."*
  - `npu.md` §4: *"dot→DMA returns data,row,group_index,last (last group of
    final row)"*; *"Dot retains this marker with the accumulated result and
    forwards it as group_result.last, including under result backpressure."*
  - `contract.json` `protocols.group_result.signals` =
    `{valid, ready, data:32, row:12, group_index:12, last:1}` —
    no status/idle/empty/level field.
  - `contract.json` connections: `npu_dot` has exactly C15 (in), C16 (out) and
    CR14 (clk/rst_n). `stop_new_transactions` (C31/C32) reaches `npu_ctl` and
    `npu_dma` only, and SYS-12 confirms the same distribution list.
- **observation**: NPU-06 makes error termination conditional on "no ...
  unconsumed result remains", but `npu_dot` has no output by which `npu_dma` or
  `npu_ctl` can observe that a group result is sitting in `npu_dot`'s result
  register (or that a partially accumulated group is still open), and no input
  by which either can flush/abort it. The only drain mechanism the contract
  offers is `npu_dma` asserting `group_result.ready`.
- **why_it_blocks**: it does not block the datapath. It blocks a *provable*
  NPU-06 error-termination sequence at NPU integration level, and it is a
  cross-module obligation that no single module author can settle. Filed rather
  than solved because solving it in RTL means inventing a port that
  `contract.json` does not list, which would silently break the concurrently
  written `npu_dma`.
- **options**:
  1. `npu_dma` holds `group_result.ready`=1 while draining after an error, and
     the spec states that this is sufficient. Consequence: `npu_dma` must always
     be able to sink a result it will discard; no port or contract change; the
     partially accumulated (never-completed) group simply never produces a
     result and is cleared by the next command's `group_first`.
  2. Add an `idle`/`empty` status field to `protocols.group_result` (or a new
     `dot_status` connection). Consequence: `contract.json` change plus new
     ports on both `npu_dot` and `npu_dma`; strongest observability.
  3. Give `npu_dot` a flush input driven by `npu_ctl`. Consequence: new
     connection in `contract.json`, and `npu_dot` stops being purely arithmetic
     (it gains command-lifecycle state), which weakens the NPU-03 "structurally
     identical" argument.
- **your_recommendation**: option 1 — cheapest, no port change, and it matches
  the "no group interleaving / single live command" model already in §4. It
  should be written explicitly into `npu.md` §4 so DV can check it.
- **what_you_implemented_meanwhile**: the most conservative reading — exactly
  the C15/C16 fields `contract.json` lists, one result outstanding at a time,
  and the result register drained only by `group_result.ready`. Marked in
  `npu_dot.sv` as `// ISSUE-npu_dot-01: provisional`.
