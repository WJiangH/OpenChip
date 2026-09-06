# npu_dma — spec findings

Filed by the RTL author against docs/spec/llm-soc-v1 @ 1.0-rc3. Each entry says
what was implemented meanwhile; the code carries a matching
`// ISSUE-npu_dma-NN: provisional` comment where behaviour was chosen.

## ISSUE-npu_dma-01 — internal partition port names are not in the machine ICD

- spec_ref: contract.json `connections[]` (C13/C14/C16/C23/C32) name only a
  `protocol`; `protocols.dispatch/local_bytes/group_result/dma_terminal/stop_issue`
  name only field names (`valid`, `ready`, `data`, `keep`, `kind`, `index`,
  `row`, ...). npu.md §4 names the same fields in prose. Neither states the RTL
  port identifier.
- observation: three blocks (npu_ctl, npu_dma+npu_local, npu_dot) are authored
  independently against this file, so the port spelling is the one thing the
  ICD does not fix.
- why_it_blocks: nothing functionally, but a top-level elaboration will fail or,
  worse, silently mis-connect if two authors choose different spellings.
- options:
  1. ICD adds an explicit `port_prefix`/`port_name` per connection — costs a
     spec revision, removes all guessing.
  2. Repo-level convention `<i_|o_><protocol>_<field>` recorded in AGENTS.md —
     no spec change, still needs one authority to state it.
  3. Leave to integration and patch names at the top — churn in three trees.
- your_recommendation: option 1 (or option 2 as an interim, before more blocks
  land).
- what_you_implemented_meanwhile: `<i_|o_><protocol name>_<field name>`, e.g.
  `i_dispatch_x_base`, `o_local_bytes_keep`, `i_group_result_group_index`,
  `o_dma_terminal_error_code`, `i_stop_new_transactions`. AXI ports use
  `m_axi_<signal lowercase>` per the task packet.

## ISSUE-npu_dma-02 — dma_terminal has no handshake and no pulse/level rule

- spec_ref: contract.json `protocols.dma_terminal.signals = {done, error,
  error_code}` (no valid/ready, unlike `terminal`). npu.md §4: "DMA emits done
  only after output B responses; error feeds controller as code5/6."
- observation: nothing says whether `done`/`error` are one-cycle pulses or
  levels held until acknowledged. npu_ctl (a different author) must latch them.
- why_it_blocks: a pulse is lost if npu_ctl is not sampling; a level is
  double-counted if npu_ctl edge-detects incorrectly across commands.
- options:
  1. Define as sticky levels cleared by the next dispatch — robust, needs
     npu_ctl to treat them as levels.
  2. Define as single-cycle pulses — smaller, requires npu_ctl to always latch.
  3. Give dma_terminal a valid/ready like `terminal` — a protocol change.
- your_recommendation: option 1, stated in npu.md §4.
- what_you_implemented_meanwhile: sticky levels. `done`/`error`/`error_code`
  assert on the terminal edge and hold until the next accepted dispatch (C13
  handshake) or reset. They are mutually exclusive and `error_code` is 5 (read)
  or 6 (write), 5 winning if both (NPU-06).

## ISSUE-npu_dma-03 — where the output write buffer lives

- spec_ref: contract.json `blocks[npu_local].purpose = "activation and
  weight/write buffers"`, but `connections` has no npu_local→npu_dma path;
  C16 is npu_dot→npu_dma `group_result`, and npu.md §4 says "dot→DMA returns
  data,row,group_index,last ... DMA emits done only after output B responses".
- observation: the block purpose implies the write buffer sits in npu_local;
  the connection graph and the prose make npu_dma the only block that can hold
  the W data that NPU-06 requires to be buffered before AW is offered.
- why_it_blocks: it decides which module owns ~64 bytes of storage and,
  with it, which module a DV suite must poke to observe write buffering.
- options:
  1. Treat `purpose` as loose prose; write buffer in npu_dma — matches the
     connection graph and prose semantics.
  2. Add an npu_local→npu_dma connection and move the buffer — larger change,
     no benefit visible in the spec.
- your_recommendation: option 1, and reword the block purpose.
- what_you_implemented_meanwhile: a 16x32-bit write buffer inside npu_dma
  (exactly one full AXI burst), filled from C16 and drained on W.

## ISSUE-npu_dma-04 — "issues no memory request until both handshakes finish"

- spec_ref: npu.md §4: "The controller broadcasts the snapshotted dispatch
  separately to DMA and local, holds each valid until its own ready, and issues
  no memory request until both handshakes finish".
- observation: the subject of "issues no memory request" is the controller, but
  only npu_dma issues memory requests, and npu_dma cannot observe npu_local's
  dispatch handshake — there is no wire for it in contract.json.
- why_it_blocks: literally implemented it would need a start signal that the
  ICD does not contain.
- options:
  1. Read it as an ordering obligation that is discharged by npu_local
     back-pressuring `local_bytes` until it is armed — no new wire.
  2. Add a `start` field to the npu_ctl→npu_dma dispatch (or a fourth
     connection) so the DMA waits explicitly.
  3. Require npu_ctl to dispatch npu_local first, npu_dma second.
- your_recommendation: option 1, stated as such in npu.md §4.
- what_you_implemented_meanwhile: npu_dma starts its first AR as soon as its
  own dispatch handshake completes; npu_local holds `o_local_bytes_ready` low
  until its own dispatch handshake completes, so no fetched word can be
  consumed before both blocks hold the command. No AXI request depends on it.

## ISSUE-npu_dma-05 — no terminal is defined for stop without a DMA error

- spec_ref: system.md SYS-12 ("sys drives sticky `stop_new_transactions` to
  ... NPU DMA at the fatal capture edge ... stop never means retract VALID or
  abandon a burst"); NPU-07 ("prohibits new DMA issue and requires coordinated
  reset").
- observation: if `stop_new_transactions` arrives for a fault raised elsewhere
  (e.g. CPU bus error, reason 1/2) while an NPU command is mid-flight, the
  command can never finish and the spec defines no DMA terminal for it.
- why_it_blocks: it decides whether NPU STATUS ends up BUSY forever (plus the
  NPU-07 watchdog, which would add a second fatal reason 5) or reports an error.
- options:
  1. No terminal: the command stays BUSY until coordinated reset; the system is
     already fatal and `o_fatal` is the observable. Watchdog may also fire, but
     SYS-12 keeps the first (lowest) reason.
  2. Report ERROR_CODE 5/6 on stop — invents a DMA error that did not occur.
  3. Add a distinct "aborted" error code — CSR/ABI change.
- your_recommendation: option 1, stated explicitly in NPU-06 or SYS-12.
- what_you_implemented_meanwhile: option 1. On stop the DMA offers no new
  AR/AW, retains every already asserted VALID, drains all offered transactions
  through their final R/B, and reports a terminal only if a genuine non-OKAY
  response occurred (code 5/6) or if the command happened to complete all of
  its work anyway (done).
