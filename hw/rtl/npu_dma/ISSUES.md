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

**rc4 ruling** (CHANGE_ORDER_rc4.md, ISSUE-npu_dma-01 row; disposition
`rule-level`): the convention this issue proposed is now recorded verbatim in
contract.json `port_identifier_convention`, binding for protocols added from
rc4 on; rc3 port spellings (this module's, filed here) are reconciled in the
top-level port map, not renamed — no change to this file's port names. An
AGENTS.md sentence is recommended to the orchestrator (CHANGE_ORDER_rc4.md
§Rule-level item 1) but not edited by this order.

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

**rc4 ruling** (CHANGE_ORDER_rc4.md, ISSUE-npu_dma-02 + ISSUE-top-01 row,
F-04; disposition `spec-gap`): `dma_terminal` is confirmed level, not pulse —
registered, set on this module's terminal edge, held until this module's own
C13 handshake edge or reset, exactly as implemented here. npu_ctl samples
only from the cycle after its own C13 handshake and takes the first sampled
assertion as the terminal edge T. This module's implementation stands
unchanged; npu_ctl's pulse documentation was wrong and has been corrected
(npu.md NPU-09(c); contract.json protocols.dma_terminal.semantics). Port
comments and the `o_dma_terminal_*` assign block in npu_dma.sv now state this
verbatim.

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

**rc4 ruling** (CHANGE_ORDER_rc4.md, ISSUE-npu_dma-03 row; disposition
`metadata`): confirmed — the output write buffer lives in npu_dma (C16
decides); contract.json `blocks[npu_local]`/`blocks[npu_dma]` purposes were
reworded to match. No logic change; the buffer (`wbuf_q`) is also one of the
arrays named by NPU-03's rc4 storage-array exemption (R4-09), cited verbatim
in its declaration comment in npu_dma.sv.

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

**rc4 ruling** (CHANGE_ORDER_rc4.md, ISSUE-npu_dma-04 row, F-06; disposition
`spec-gap`): the rc3 sentence is replaced — C25 (local) handshake completes
no later than C13 (dma), same edge allowed; npu_local holds `dispatch.ready`
=1 always and backpressures `local_bytes.ready`=0 until armed; npu_dma may
issue its first AR from the cycle after its own handshake. This module's
provisional choice (start after own handshake; rely on npu_local's
backpressure) is confirmed as-is (npu.md §4 sentence, NPU-09(a); no logic
change here — npu_ctl must keep asserting C25 valid no later than C13
valid).

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

**rc4 ruling** (CHANGE_ORDER_rc4.md, ISSUE-npu_dma-05 row; disposition
`spec-clear`, now also restated in NPU-09(e) for DV determinism): confirmed —
SYS-12 "makes the run fail; it does not ... promise recovery without full
reset"; NPU-07 "requires coordinated reset". Stop without a DMA non-OKAY
response produces no terminal; BUSY stays 1 until reset. This module's
implementation (option 1 above) stands unchanged.

**Also touching this module (no logic change)**: CHANGE_ORDER_rc4.md's
ISSUE-npu_dot-01 + ISSUE-npu_local-03 row (F-01) confirms this module's
provisional choice under ISSUE-npu_dma-02 that `group_result.ready` stays 0
after an error (npu_dot's own recommended "ready-while-draining" alternative
was rejected). The new C34 `dot_lifecycle.flush` mechanism that resolves
npu_dot/npu_local post-terminal recovery is wired between npu_ctl and
npu_dot only; npu_dma's `group_result` port list and behaviour are unchanged
(npu.md NPU-06, NPU-09(b)(d); contract.json protocols.dot_lifecycle /
group_result / dispatch, C34). The `o_group_result_ready` comment in
npu_dma.sv now cites NPU-09(d) directly.
