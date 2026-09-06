# npu_ctl — open issues

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
