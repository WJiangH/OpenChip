# ISSUES — hw/rtl/sys

## ISSUE-sys-01: RESULT_COMMIT repeat-write response is not explicit

- **spec_ref**: `system.md` §3, offset 0x18 RESULT_COMMIT: "write1 latches
  RESULT_CODE to output and sets o_result_valid until reset; additional
  commits rejected." SYS-08: "reserved write bits must be zero or the write
  is rejected atomically."
- **observation**: The register table says a second RESULT_COMMIT write
  (after `o_result_valid` is already latched) is "rejected", but does not
  state whether that rejection is a bus-level SLVERR (no state change,
  software-visible failure) or a silent OKAY no-op (write accepted at the
  bus level, simply without effect — the same treatment SYS-08 gives a W1C
  write to an already-zero bit).
- **why_it_blocks**: The two readings are both internally consistent with
  SYS-08's general vocabulary but produce different CSR bus behavior
  (BRESP=SLVERR vs BRESP=OKAY) for the same stimulus. An independent DV
  suite deriving expected BRESP purely from prose can legitimately pick
  either value; this is exactly the kind of address/response ambiguity
  Iron Rule 1 reserves for the architect, not for RTL to decide unilaterally.
- **options**:
  1. Second commit write returns SLVERR, no state change (matches the
     SLVERR-on-atomic-reject idiom used for NPU-05 SUBMIT-while-busy and for
     RESULT_COMMIT's own reserved-bit check).
  2. Second commit write returns OKAY, no state change (matches the WO/W1C
     "write with no effect is still an accepted no-op" idiom used elsewhere
     in SYS-08 for a W1C bit already at 0).
  3. Leave unresolved for this PR; flag as an open item for chief-architect
     to add an explicit sentence to `system.md` §3.
- **your_recommendation**: Option 1 (SLVERR) — it is the more conservative
  reading for a security/result-integrity register (a silently-ignored
  repeat commit could mask a firmware bug where RESULT_CODE was changed and
  a second commit attempted, believing it took effect) and it is consistent
  with the one explicit SLVERR-on-reject precedent already in this document
  family (NPU-05).
- **what_you_implemented_meanwhile**: `hw/rtl/sys/sys.sv`, the
  `OFF_RESULT_COMMIT` case in the `wr_slverr` combinational block, marked
  `// ISSUE-sys-01: provisional`. A repeat commit (write with bit0=1 while
  `result_valid_r` is already 1) returns SLVERR and performs no state change;
  a write with bit0=0 (and reserved bits zero) is accepted OKAY with no
  effect, matching the plain WO-field idiom.
