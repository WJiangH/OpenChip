# npu_dot — spec issues raised during implementation

Spec under implementation: `docs/spec/llm-soc-v1/` 1.0-rc4 (was 1.0-rc3 when the
issues below were filed).
Raised by the RTL author of `hw/rtl/npu_dot/npu_dot.sv`; not resolved in RTL.

| id | status |
|---|---|
| ISSUE-npu_dot-01 | **RULED by change order rc4 (spec-gap, F-01) — closed; code changed** |

---

## ISSUE-npu_dot-01 — no way for npu_dma to know npu_dot still holds an unconsumed result

**Status: RULED by `docs/spec/llm-soc-v1/CHANGE_ORDER_rc4.md`, row
"ISSUE-npu_dot-01 + ISSUE-npu_local-03 (F-01)" — disposition `spec-gap`.
Implemented in `npu_dot.sv`; nothing is provisional here any more.**

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
- **ruling (rc4)**: option 3 (flush input), not the recommended option 1. A new
  connection **C34** `dot_lifecycle` (`npu_ctl` -> `npu_dot`, one signal
  `flush`) is added to `contract.json`, and `npu.md` NPU-09(b) fixes its
  semantics: `flush` is a level *registered in npu_ctl* with reset value 1, set
  on the `dma_terminal` sampling edge T, cleared only on the C25 handshake edge
  and never on the C12 accept edge. The recommendation in option 1
  (`npu_dma` holds `group_result.ready`=1 while draining) is **explicitly
  rejected**: NPU-09(d) keeps `group_result.ready`=0 from npu_dma's first
  non-OKAY response until its next dispatch handshake. The NPU-03 "structurally
  identical" concern raised against option 3 is answered by NPU-06's rewrite:
  the arithmetic is untouched, and flush only clears and discards — it never
  changes a product, a sum or the order of results.
- **what changed in the code (rc4)**:
  - new port `input wire i_dot_lifecycle_flush` (C34; the spelling is fixed by
    `contract.json` `port_identifier_convention` via ISSUE-npu_dma-01).
  - `o_group_result_valid = result_valid_q && !i_dot_lifecycle_flush` and
    `o_dot_operands_ready = i_dot_lifecycle_flush || !result_valid_q` —
    combinational functions of the registered flush, per NPU-09(b) ("this
    creates no VALID-on-READY dependence"). Neither output depends on
    `i_dot_operands_valid` or `i_group_result_ready`, so no combinational loop
    exists.
  - a flush branch in the single `always_ff`, with priority over the operand
    branch, clears `acc_q` and all five result registers on every edge at which
    flush=1 and thereby discards the operand beat accepted at that edge.
  - the single-result-outstanding property, the ordering argument and the exact
    INT8xINT8 -> INT32 arithmetic are unchanged.
- **residual obligation on other modules** (not npu_dot's to implement):
  `npu_ctl` must add `o_dot_lifecycle_flush` with the reset-1 / set-at-T /
  clear-only-at-C25 behaviour, and `llm_soc_top` must wire C34. If `flush` were
  tied to 0 at integration, npu_dot degrades exactly to its rc3 behaviour and
  the F-01 race returns; if it were tied to 1, npu_dot would never emit a
  result. Both are integration errors visible to DV as an NPU-09(b) violation.
