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
