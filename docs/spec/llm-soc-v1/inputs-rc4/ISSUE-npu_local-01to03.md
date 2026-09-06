# npu_local — spec findings

Filed by the RTL author against docs/spec/llm-soc-v1 @ 1.0-rc3.
ISSUE-npu_dma-01 (partition port names) applies to this module too.

## ISSUE-npu_local-01 — W_STRIDE is declared known to local but is unusable there

- spec_ref: npu.md §4: "Local knows K,N,G,W_STRIDE from its dispatch"; same §
  also: "DMA→local transfers 32-bit fetched words with kind 0=activation,
  1=weight, index=first byte coordinate k, row=n".
- observation: because every fetched word already carries `index` and `row`,
  local never needs W_BASE/W_STRIDE to place a weight byte; W_STRIDE only
  matters to the block that forms addresses (npu_dma). The same holds for
  x_base/w_base/y_base/opcode/tag in the `dispatch` protocol.
- why_it_blocks: not blocking. It is an unused-input question that a strict
  lint gate forces every implementer to answer the same way or differently.
- options:
  1. Keep the full dispatch fan-out (one protocol, two consumers) and let local
     leave the address fields unused — simplest, matches contract.json.
  2. Define a narrower `dispatch_shape` protocol for C25 (k, n, group only).
  3. Have local recompute the row/index itself from W_STRIDE and ignore the
     local_bytes tags — duplicates address arithmetic in two blocks.
- your_recommendation: option 1; optionally note in npu.md §4 that local uses
  W_STRIDE only implicitly, through the DMA's tagging.
- what_you_implemented_meanwhile: option 1. All dispatch fields are ports;
  opcode/tag/x_base/w_base/y_base/w_stride are explicitly sunk with a comment.
  K, N and G are used (group boundaries, ceil(K/G), command_last).

## ISSUE-npu_local-02 — reset of the 4096-byte activation store

- spec_ref: system.md SYS-03: "Reset shall discard all command/IRQ/status
  state ... mutable SRAM/external bytes need not retain meaningful data";
  npu.md NPU-03: "a 4096-byte activation store and a minimum 64-byte weight
  transfer buffer". AGENTS.md house rule: "every flop resets".
- observation: the spec does not say whether the activation store counts as
  "command state" that reset must discard. A literal reading of the house rule
  would force 32768 resettable flops (or an SRAM macro with a clear sequence).
- why_it_blocks: not functionally — every X word of a command is written before
  it is read — but it changes the cell count by ~2x and it changes what a DV
  suite may assume about post-reset contents.
- options:
  1. Storage arrays are exempt: reset all sequencing/pointer state, leave array
     contents undefined. Matches the existing precedent in this repo
     (hw/rtl/npu/npu_act_sram.sv, "the macro's data contents are not required
     to reset").
  2. Reset every word: deterministic post-reset reads, ~32k extra reset flops
     and no SRAM-macro swap later.
- your_recommendation: option 1, said once in NPU-03 so DV does not assume
  zeroed activation memory.
- what_you_implemented_meanwhile: option 1. `act_mem_q`, `wfifo_data_q`,
  `wfifo_row_q`, `wfifo_idx_q` have no reset; every pointer, counter, output
  register and descriptor field does. Yosys reports 33664 array flops vs 177
  control flops for this module.

## ISSUE-npu_local-03 — how local recovers after an aborted command

- spec_ref: npu.md NPU-06: "It is safe to CLEAR and reuse only after terminal
  error"; §4: "Exactly one command is live"; SYS-03: "A running-command reset
  invalidates its entire output".
- observation: on a DMA error the command is abandoned part-way, but npu_local
  and npu_dot receive no abort signal — contract.json has no such connection.
  Local can be left holding buffered weight words, a partial group and an
  unaccepted operand beat.
- why_it_blocks: without a defined recovery, the next command after CLEAR would
  start with stale operands and produce wrong Y — a silent data error, not a
  reported one.
- options:
  1. Make the dispatch handshake itself the reset: local accepts a dispatch
     unconditionally and re-initialises all sequencing state — no new wire,
     relies on npu_ctl never dispatching while a command is live.
  2. Add an abort/flush field to the dispatch or a new connection.
  3. Require a full system reset after any DMA error, contradicting NPU-06's
     "safe to CLEAR and reuse".
- your_recommendation: option 1, stated in npu.md §4 as a property of the
  dispatch broadcast.
- what_you_implemented_meanwhile: option 1. `o_dispatch_ready` is constant 1;
  an accepted dispatch clears the weight-buffer pointers, the sub-word counter
  and the operand output register. Note npu_dot has no dispatch input at all,
  so a residual result held in npu_dot's output register cannot be flushed by
  this mechanism — that part is the npu_dot author's and npu_ctl's to answer.
