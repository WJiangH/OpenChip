# npu_ctl — issue log

Spec baseline: `docs/spec/llm-soc-v1` 1.0-rc4. Rulings on the issues below are
in `docs/spec/llm-soc-v1/CHANGE_ORDER_rc4.md` §Rulings.

## ISSUE-npu_ctl-01: does npu_ctl own the K/N/G "group loop", or does npu_local?

- **spec_ref**: task brief for this item: *"sequences the group loop (K, N, G,
  tails — NPU-01/02 shapes, no arithmetic here)"*. `npu.md` §4: *"Local knows
  K,N,G,W_STRIDE from its dispatch: for G=1 or 2, one fetched word spans
  multiple groups, so local reuses its held word for multiple operand
  transfers with disjoint keep masks... There are no group markers on this
  fetched-word interface; local derives all group boundaries from its
  descriptor."* Also: *"Local additionally drives command_last=1 exactly when
  group_last=1, row=N-1 and group_index=ceil(K/G)-1."*
- **observation**: the task brief's phrasing ("ctl sequences the group loop")
  and npu.md §4's actual assignment of the K/N/G/tail iteration state machine
  to npu_local ("local derives all group boundaries from its descriptor") point
  in different directions. `contract.json`'s `dispatch` protocol (C13 npu_ctl→
  npu_dma, C25 npu_ctl→npu_local) carries only opcode/x_base/w_base/y_base/
  k/n/group/w_stride/tag — no group-index/row/last fields — which is only
  consistent with the receiving blocks (dma, local) deriving iteration state
  themselves from those raw fields, not with npu_ctl pre-computing and pushing
  per-beat loop state.
- **why_it_blocks**: not blocking implementation (npu.md §4 prose is decisive
  over an orchestrator-summary brief per house rule "contract.json wins for
  names/widths; prose wins for semantics" — extended here to the normative
  spec file itself outranking a task-brief paraphrase), but flagged since a
  DV-side or integrator reading of the task brief alone could expect group/row
  counters or a `command_last`-shaped signal inside npu_ctl that this
  implementation does not produce.
- **options**:
  1. npu_ctl holds no group/row state; forwards K/N/G/W_STRIDE unchanged; the
     loop lives in npu_local/npu_dot (chosen, matches npu.md §4 verbatim).
  2. npu_ctl additionally computes ceil(K/G) and a row/group_index sequencer
     and forwards per-beat markers to npu_local — duplicates state that
     npu_local independently derives per §4, and the `dispatch` protocol has
     no fields to carry such per-beat markers.
- **your_recommendation**: option 1; implemented in `npu_ctl.sv`.
- **what_you_implemented_meanwhile**: `npu_ctl.sv` latches the raw dispatch
  fields (including K, N, GROUP, W_STRIDE) and forwards them unchanged and
  simultaneously to npu_dma and npu_local; it holds no group/row/tail counter.
- **rc4_ruling**: **CLOSED — spec-clear** (CHANGE_ORDER_rc4, row
  ISSUE-npu_ctl-01): *"npu.md §4 'local derives all group boundaries from its
  descriptor'; the dispatch protocol carries no per-beat markers. npu_ctl holds
  no loop state. Provisional confirmed; the packet sentence was a paraphrase."*
  Option 1 stands.
- **code_changed**: no logic change. `npu_ctl.sv` header scope note now cites
  the ruling instead of arguing the case, and drops the rc3 sentence "issues no
  memory request until both handshakes finish" (replaced by NPU-09(a), see
  ISSUE-npu_ctl-02 block below and CHANGE_ORDER_rc4 row ISSUE-npu_dma-04).

## ISSUE-npu_ctl-02: which edge is "submit acceptance" for LAST_CYCLES?

- **spec_ref**: `npu.md` NPU-04, LAST_CYCLES field: *"u32 cycles from submit
  acceptance to terminal edge inclusive, stable until next completion."*
  NPU-07: *"if no terminal transition by 2^28 cycles from acceptance."*
- **observation**: "submit acceptance" most literally means the cycle in which
  npu_csr's own AXI4-Lite SUBMIT write commits (sets BUSY=1). npu_ctl has no
  visibility into that cycle directly; it only observes the C12 dispatch
  handshake (`i_dispatch_valid && o_dispatch_ready`). In this design npu_ctl's
  `o_dispatch_ready` is combinationally `1` throughout its own IDLE state
  (gated only by sticky fatal/stop conditions that are inactive in the normal
  case), and npu_csr asserts `o_dispatch_valid` in the very same cycle it
  commits SUBMIT, so the two edges coincide exactly whenever the system is not
  already in a fatal/stop condition. Under a hypothetical stall (npu_ctl not
  yet IDLE — unreachable here since only one command is ever live and npu_csr
  itself gates SUBMIT to the idle case) the two edges could in principle
  differ; that path is not exercised by this design.
- **why_it_blocks**: not blocking (the two candidate edges are provably
  identical in every reachable state of this implementation), but the exact
  cycle count is an observable DV may check bit-for-bit, so the reasoning is
  recorded rather than left implicit.
- **options**: 1) start the counter at the npu_ctl-side dispatch-accept edge
  (chosen); 2) have npu_csr itself count cycles and hand a cycle count to
  npu_ctl over an additional field the `terminal`/`dispatch` protocols do not
  carry.
- **your_recommendation**: option 1; implemented (`cycle_ctr_q <= 32'd1` on the
  `i_dispatch_valid && o_dispatch_ready` edge in `ST_IDLE`).
- **what_you_implemented_meanwhile**: see `npu_ctl.sv`, `ST_IDLE` case arm.
- **rc4_ruling**: **CLOSED — spec-gap, text added** (CHANGE_ORDER_rc4, row
  ISSUE-npu_ctl-02 + F-06): *"LAST_CYCLES = T-H+1: H = C12 dispatch handshake
  edge, T = edge on which npu_ctl samples dma_terminal asserted; both count.
  Malformed idle SUBMIT does not modify LAST_CYCLES. npu_ctl provisional
  (counter=1 on the accept edge, increment on the sampling edge) matches the
  definition."* npu.md NPU-04 now defines H and T explicitly and NPU-07 states
  the 2^28 watchdog window starts at H; the ambiguous rc3 phrase "from submit
  acceptance" is gone. Option 1 (count from the npu_ctl-side C12 handshake
  edge) is exactly the ruled definition.
- **code_changed**: no logic change (`cycle_ctr_q <= 32'd1` at H, +1 on every
  later edge including T, giving T-H+1); the `ST_IDLE` comment now quotes the
  rc4 H/T definition. The `npu_csr` half of the ruling ("verify LAST_CYCLES
  untouched on CSR-layer descriptor rejection") is recorded in
  `hw/rtl/npu_csr/ISSUES.md`.

## ISSUE-npu_ctl-03: watchdog boundary edge coincides with a terminal (new, rc4, non-blocking)

- **spec_ref**: `npu.md` NPU-07: *"if no terminal edge T (NPU-09(c)) occurs
  within 2^28 cycles from H (NPU-04) it latches global fatal(reason5)"*; and
  *"LAST_CYCLES is meaningful only on nonfatal completion."*
- **observation**: this implementation measures the window on the LAST_CYCLES
  counter, so it latches fatal at the first edge whose count would exceed
  2^28 — i.e. the earliest fatal edge is H+2^28, and every T with
  T-H+1 <= 2^28 completes without fatal. If a terminal is sampled at exactly
  edge H+2^28 (T-H+1 = 2^28+1, one cycle outside the window) both happen on
  that edge: the terminal record is still emitted to npu_csr (cycles =
  2^28+1) and `o_fault_valid`/reason5 latches. NPU-07's "LAST_CYCLES is
  meaningful only on nonfatal completion" sentence covers the resulting value,
  and `o_dispatch_ready` is gated by the sticky fatal so no further command
  starts, but the spec does not say whether the C24 record must be suppressed
  on the fatal edge.
- **why_it_blocks**: not blocking — unreachable in any B1 workload (2^28
  cycles) and only at one exact edge. Recorded because a DV property of the
  form "fatal implies no terminal record" would fail on that single edge.
- **options**: 1) keep both (chosen; terminal wins the state transition, fatal
  is sticky and blocks the next command); 2) suppress the C24 record when the
  watchdog latches on the same edge, leaving BUSY set until reset (matches
  NPU-09(e)'s treatment of a stopped run, but the spec does not order it here).
- **your_recommendation**: option 1 until the architect says otherwise; the
  choice predates rc4 and rc4 did not rule on it.
- **what_you_implemented_meanwhile**: unchanged `ST_WAIT_DONE`/watchdog logic
  in `npu_ctl.sv`.

## rc4 change record: C34 dot_lifecycle.flush (no open question)

CHANGE_ORDER_rc4 row ISSUE-npu_dot-01 + ISSUE-npu_local-03 (F-01) adds C34 and
requires npu_ctl to drive `o_dot_lifecycle_flush`: registered level, reset
value 1, set on the dma_terminal sampling edge T, cleared only on the C25
handshake edge, never on the C12 accept edge (NPU-09(b)). Implemented as
`flush_q` in `npu_ctl.sv`; the two write terms are mutually exclusive by state
(T is sampled in `ST_WAIT_DONE`, C25 completes in `ST_BCAST`), so the level is
1 in the cycle ending at the C25 edge as NPU-09(b) requires. Row F-04
(ISSUE-npu_dma-02 + ISSUE-top-01) additionally corrected this module's C23 port
documentation: `dma_terminal` is a registered level held by npu_dma until its
next C13 handshake, not a one-cycle pulse. The sampling logic was already
level-tolerant (it never edge-detects) and did not change.
