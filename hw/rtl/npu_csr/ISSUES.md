# npu_csr — issue log

Spec baseline: `docs/spec/llm-soc-v1` 1.0-rc4. Rulings on the issues below are
in `docs/spec/llm-soc-v1/CHANGE_ORDER_rc4.md` §Rulings.

## ISSUE-npu_csr-01: which module validates the NPU-01/02 descriptor?

- **spec_ref**: `contract.json` `requirements[id=NPU-01..NPU-08].owner_modules` lists
  `["npu_csr","npu_ctl","npu_dma","npu_dot"]` jointly, with no per-connection split
  of validation duty; `npu.md` NPU-04 register table, SUBMIT field: *"write1 only:
  validate and atomically snapshot descriptor"*; NPU-05: *"An idle SUBMIT with
  malformed descriptor returns OKAY at the CSR layer, sets ERROR with the priority
  code ordering 1,2,3,4 above, ... issues no DMA."*
- **observation**: `contract.json`'s machine-readable requirement/connection lists
  do not themselves assign the NPU-01 (shape) / NPU-02 (layout/alignment/range)
  validation to a specific block; the `dispatch` protocol (C12, npu_csr→npu_ctl)
  carries only the already-decided descriptor fields, with no error/valid-reason
  side channel back from npu_ctl for a malformed command.
- **why_it_blocks**: without settling this, either npu_csr must never forward an
  invalid descriptor (i.e. it validates before ever asserting `dispatch_valid`),
  or npu_ctl must validate and independently produce the CSR-layer-OKAY/ERROR
  distinction of NPU-05 itself — the two designs are not equivalent and the
  DV-side authors of npu_ctl need to know which to expect.
- **options**:
  1. npu_csr validates fully before dispatch (chosen). Simplest: matches the
     SUBMIT field's own wording, matches "issues no DMA" (npu_ctl/npu_dma never
     see a malformed command at all), and requires no error-reporting path on
     the dispatch protocol.
  2. npu_ctl validates, npu_csr only forwards raw shadow fields unconditionally
     on any SUBMIT=1 write. Requires an error-code return path on the dispatch
     protocol that `contract.json`'s `dispatch` signal list does not carry
     (only valid/ready + descriptor fields), so this option is a spec/ICD gap
     unless dispatch protocol is amended.
  3. Split: npu_csr checks opcode/shape/alignment (codes 1-3, no memory-map
     knowledge needed), npu_ctl checks range/overlap (code4, needs region
     constants). No textual support and adds a second silent-failure path.
- **your_recommendation**: option 1 — implemented in `npu_csr.sv`. `contract.json`
  is silent/ambiguous on the split; escalate to chief-architect only if DV's
  independently-authored npu_ctl-side vplan assumes option 2 or 3.
- **what_you_implemented_meanwhile**: `npu_csr.sv` computes the full priority-1..4
  check (opcode==1; 1<=K,N<=4096 and G power-of-two in 1..4096; 4-alignment and
  W_STRIDE bounds; 64-bit unsigned range/permission/overlap against the
  `model`/`scratch` regions of `system.md` §2) combinationally from the shadow
  registers at the moment SUBMIT commits, and only asserts `o_dispatch_valid`
  toward npu_ctl when the descriptor is fully valid. `// ISSUE-npu_csr-01:
  provisional` is not marked in code since this reading is the most literal one
  available (SUBMIT's own field text), not a guess among equally-weighted options.
- **rc4_ruling**: **CLOSED — spec-clear** (CHANGE_ORDER_rc4, row
  ISSUE-npu_csr-01): *"NPU-04 SUBMIT 'validate and atomically snapshot
  descriptor'; NPU-05 'malformed descriptor returns OKAY at the CSR layer, sets
  ERROR ... issues no DMA'. npu_csr validates fully; a dispatch never carries a
  malformed descriptor. Provisional confirmed."* Option 1 stands; no escalation
  needed.
- **code_changed**: no logic change; the header comment now cites the ruling.

## rc4 verification record: LAST_CYCLES and the WO command registers

CHANGE_ORDER_rc4 row ISSUE-npu_ctl-02 + F-06 assigns npu_csr one obligation —
*"verify LAST_CYCLES untouched on CSR-layer descriptor rejection"* — and NPU-04
(rc4) states it in full: *"only reset (value 0) and a terminal edge T change
it"*. Verified in `npu_csr.sv`: `last_cycles_q` has exactly two assignments,
the reset value `32'd0` and `last_cycles_q <= i_terminal_cycles` inside the C24
terminal record that also sets DONE/ERROR, ERROR_CODE and COMPLETED_TAG. No
SUBMIT arm (accepted, malformed-idle-descriptor or SLVERR-rejected), no CLEAR
arm and no descriptor-shadow write assigns it. No logic change; the invariant
is now stated at the declaration and at the terminal arm so it stays
grep-checkable.

SYS-08 (rc4, F-05) *"WO command registers (RESULT_COMMIT, NPU SUBMIT, NPU
CLEAR) accept exactly the written word value 1: any other written word,
including 0, returns SLVERR and has no effect"*: verified — both `OFF_SUBMIT`
and `OFF_CLEAR` reject `w_data_q != 32'd1` with SLVERR before any state update
(and the busy/uncleared refusal is checked first, so a rejected write is SLVERR
under either rule). RESULT_COMMIT lives in `sys`, not here. SYS-08 (rc4, R4-07)
*"NPU descriptor shadow registers accept any word value while writable and are
validated only at SUBMIT"*: verified — the RW shadow arms store `w_data_q`
unconditionally when `!shadow_locked`, with validation only in `desc_error_code`
at the SUBMIT commit.
