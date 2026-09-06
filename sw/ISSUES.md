# sw/ISSUES.md — SIM-L1 spec gaps found while implementing SW-B1

Format per AGENTS.md / task brief: spec_ref, observation, why_it_blocks,
options, your_recommendation, what_you_implemented_meanwhile.

## ISSUE-sw_b1-01: reserved boot-header words 8..15 not explicitly a reject gate

- **spec_ref**: `docs/spec/llm-soc-v1/system.md` SYS-05: "Header u32 words:
  magic 0x4C4C4D31, ABI=1, byte_length (1..0x30000), load=0x10000000,
  entry=0x10000000, CRC32, BSS start, BSS length; words 8..15 zero." SYS-05
  also lists what ROM validates: "ROM validates header and bounds before
  copy... ROM code shall load a 64-byte header..." but the enumerated
  validation predicates earlier in the same requirement do not explicitly
  say a nonzero reserved word is a rejection condition — "words 8..15 zero"
  reads as a format description of a well-formed image, not necessarily a
  spelled-out gate ROM must actively check.
- **observation**: It is ambiguous whether ROM is required to reject a
  header whose reserved words are nonzero, or whether that is simply
  undefined/don't-care input space that a compliant image generator never
  produces.
- **why_it_blocks**: Affects whether a "malformed reserved field" input is a
  0xB001 (header) failure, a silently-accepted no-op, or out of scope for
  ROM to check at all — matters for anyone writing a negative-boot DV test
  against exactly this byte pattern.
- **options**: (a) ROM ignores reserved words entirely (simplest, matches a
  literal reading that only the 8 named fields are "the header"); (b) ROM
  rejects any nonzero reserved word as 0xB001 (defensive, catches a
  corrupted/future-ABI header early); (c) architect clarifies in a future
  change order.
- **your_recommendation**: (b) — reject as 0xB001. Fail-safe is strictly
  better than fail-open for a boot-time integrity gate, and it costs nothing
  observable for any compliant image (mkimage.py always emits zero
  reserved words).
- **what_you_implemented_meanwhile**: `sw/rom/rom_main.c` rejects any
  nonzero reserved word as `BOOT_RESULT_BAD_HEADER` (0xB001), marked
  `// ISSUE-sw_b1-01: provisional` at the check site.

## ISSUE-sw_b1-02: which of {0xB001, 0xB003} covers byte_length/load/entry-field validity

- **spec_ref**: `docs/spec/llm-soc-v1/system.md` SYS-06: "On header, CRC or
  bounds failure ROM sets RESULT_CODE=0xB001, 0xB002 or 0xB003
  respectively." SYS-05 mixes "header" content checks (magic/ABI) and
  numeric-range checks (byte_length in [1,0x30000], load/entry fixed
  values) in the same descriptive paragraph as the BSS/bounds arithmetic,
  without drawing an explicit line between "header failure" (0xB001) and
  "bounds failure" (0xB003) for fields that are *both* header content and a
  numeric range (byte_length; load/entry equality to a fixed constant).
- **observation**: A DV negative test asserting a *specific* RESULT_CODE
  for, say, an out-of-range `byte_length` or a wrong `load` value could
  reasonably expect either 0xB001 or 0xB003 depending on how the taxonomy
  is read; this implementation's choice is not visible from the spec text
  alone.
- **why_it_blocks**: Only blocks exact-RESULT_CODE assertions in negative
  boot DV for these specific fields; does not block SW-B1's own two
  required negative variants (bad magic, bad CRC), which are unambiguous.
- **options**: (a) treat byte_length/load/entry validity as "header"
  (0xB001), grouping every one of the eight named header fields together;
  (b) treat only magic/ABI as "header" and put byte_length/load/entry under
  "bounds" (0xB003); (c) architect clarifies.
- **your_recommendation**: (a), implemented here — every one of the eight
  named header fields (magic, ABI, byte_length, load, entry, plus the
  reserved words) is a "header" check (0xB001); only the *derived*
  BSS-placement arithmetic (BSS start/length/end, payload-region fit) is a
  "bounds" check (0xB003). This groups all fixed-format/fixed-value field
  checks together and all computed-address-arithmetic checks together,
  which is the most literal reading of SYS-05's own paragraph structure
  (header fields listed first, BSS arithmetic described afterward).
- **what_you_implemented_meanwhile**: `sw/rom/rom_main.c` — byte_length,
  load, entry checks all use `BOOT_RESULT_BAD_HEADER` (0xB001); BSS
  start/length/end and payload-region-fit checks use `BOOT_RESULT_BAD_BOUNDS`
  (0xB003). Not marked provisional in code (this is a considered design
  choice, not a placeholder), but flagged here for traceability.
