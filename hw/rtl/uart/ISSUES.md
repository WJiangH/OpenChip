# ISSUES — hw/rtl/uart

## ISSUE-uart-01: DIVISOR "legal 2..65535" — documentation or hardware-enforced range?

- **spec_ref**: `system.md` §3, offset 0x08 DIVISOR: "RW reset16, legal
  2..65535 ... Divisor writes while BUSY reject." SYS-08 general rule: "Other
  sizes, strobes, offsets or writes to RO registers return SLVERR ...
  reserved write bits must be zero or the write is rejected atomically."
- **observation**: "Divisor writes while BUSY reject" is an explicit,
  separately-stated hardware rejection rule and is implemented as such
  (SLVERR while `busy`). "legal 2..65535" reads as a value-range statement
  in the same sentence but, unlike the BUSY-reject clause, is never paired
  with an explicit "values outside this range are rejected" / "return
  SLVERR" instruction anywhere in `system.md`, `axi.md` or `contract.json`.
  Compare NPU's ERROR_CODE mechanism (npu.md NPU-04/05), which explicitly
  names out-of-range shape values as SLVERR/ERROR conditions — no equivalent
  sentence exists for DIVISOR.
- **why_it_blocks**: Two readings are both defensible: (a) the range is a
  documented legal-firmware-input contract only (like BOOT_STAGE's "0..4
  only", which also has no stated hardware-rejection rule and which this
  same submission does not enforce for consistency), or (b) the range is a
  hardware-enforced field constraint and a write outside it must return
  SLVERR with no state change. The choice changes observable BRESP for
  DIVISOR writes of 0, 1, or values above 65535 truncated by WSTRB masking
  is not applicable here since the field is exactly 16 bits (values 0..65535
  are all representable; "legal 2..65535" excludes exactly 0 and 1).
- **options**:
  1. Do not hardware-enforce the range (current implementation): any 16-bit
     value with reserved bits31:16 zero and BUSY=0 is accepted OKAY. A
     divisor of 0 or 1 still produces a finite (only unusually fast, or via
     16-bit wraparound to 65535, unusually slow) baud period — no lockup,
     no X-propagation, no synthesis hazard.
  2. Hardware-enforce the range: reject writes with `wdata[15:0] < 2` as
     SLVERR, no state change, matching the same idiom used for BUSY-reject.
- **your_recommendation**: Option 1, primarily for internal consistency with
  how this same submission treats BOOT_STAGE's "0..4 only" (no enforcement,
  since it is presented as a plain value-range description rather than an
  explicit rejection rule) — but this is the closer of the two calls in this
  submission and is worth an explicit architect sentence either way, since
  DIVISOR (unlike BOOT_STAGE) directly times a physical serializer.
- **what_you_implemented_meanwhile**: `hw/rtl/uart/uart.sv`, the
  `OFF_DIVISOR` case in the `wr_slverr` combinational block, marked
  `// ISSUE-uart-01: provisional`. Only the reserved-bits check and the
  BUSY-reject are hardware-enforced; the 2..65535 range is not.

## rc4 ruling (2026-09-06, `docs/spec/llm-soc-v1/CHANGE_ORDER_rc4.md`)

- **ISSUE-uart-01 + F-07**: **ruled reject** — option 2 from the options list
  above. "Value ranges stated in the sys and UART register rows are
  hardware-enforced" (system.md SYS-08, rc4): a DIVISOR write whose field
  value is below 2 now returns SLVERR, no state change, in addition to the
  pre-existing reserved-bits check and BUSY-reject. The prior provisional
  reading (option 1, unenforced) is ruled wrong. Fixed in `uart.sv`'s
  `OFF_DIVISOR` `wr_slverr` expression:
  `wr_slverr = (cur_wdata[31:16] != 16'd0) || busy || (cur_wdata[15:0] < 16'd2);`
  The `// ISSUE-uart-01: provisional` marker is removed since the behavior
  is now the confirmed spec ruling, not a guess. DIVISOR values 0 and 1 are
  no longer a defined serialization state (per rc4's DV note); the field's
  legal range 2..65535 is now hardware-enforced end to end.
- **TX_DATA** restatement (rc4, R4-08 / SW-RC4-01 disposition): rc4's
  sentence "TX_DATA accepts any word whose bits 31:8 are zero" is a
  restatement of the pre-existing reserved-write-bits rule for TX_DATA and
  "adds no uart obligation" (system.md SYS-08). `uart.sv` already rejects
  TX_DATA writes with bits 31:8 nonzero via the general
  `wr_slverr = (cur_wdata[31:8] != 24'd0) || holding_valid;` expression — no
  code change required for this row.
