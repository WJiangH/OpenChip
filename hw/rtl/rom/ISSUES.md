# ISSUES — hw/rtl/rom

## ISSUE-mem-01

- **spec_ref**: `docs/spec/llm-soc-v1/contract.json` `requirements[]` rows for
  `AXI-01`..`AXI-10` (`owner_modules: ["fabric","cpu_bridge","lite_bridge","extmem"]`)
  and `SYS-04` (`owner_modules: ["sys","cpu_bridge","irq","uart"]`); mirrored
  verbatim in `traceability.md`. Compare `axi.md`: *"AXI-06: ROM/SRAM shall
  respond within 16 cycles of an accepted read..."* and *"AXI-08: Every
  memory target shall commit enabled write bytes before presenting
  successful BVALID..."* — both explicitly bind rom/sram in prose.
- **observation**: The machine-readable requirement-ownership metadata never
  lists `rom` or `sram` as an `owner_module`, for any AXI-0x row or for
  SYS-04, even though `contract.json` `blocks[]` defines `rom`/`sram` as
  `disposition: build` AXI4 targets and the prose text unambiguously
  obligates them (AXI-01 signal list, AXI-02 transaction restrictions,
  AXI-03 handshake ordering, AXI-06 16-cycle bound, AXI-08 write-commit
  ordering, SYS-04 permission-table enforcement upstream of these targets).
- **why_it_blocks**: Does not block RTL implementation — the prose is clear
  and unambiguous, so I implemented against it directly. It does create a
  traceability gap: automated tooling that keys off `contract.json`
  `owner_modules` (rather than reading axi.md prose) could report
  AXI-01/02/03/06/07/08 and SYS-04 as not applicable to rom/sram, or fail to
  link this delivery back to those requirement rows in a downstream
  evidence ledger, even after this PR closes the implementation gap.
- **options**:
  1. Chief architect adds `"rom"`, `"sram"` to `owner_modules` for the
     affected AXI-0x rows and SYS-04 in a change order — matches prose, no
     semantic change, restores machine/prose agreement.
  2. Leave `contract.json` as-is; treat it as a non-exhaustive summary and
     rely on axi.md/system.md prose plus `blocks[]` as the authoritative
     per-block obligation list.
  3. Split a new `MEM-0x` requirement family scoped to rom/sram out of
     AXI-0x in a future change order.
- **your_recommendation**: Option 1 — cheapest, no semantic drift, and
  consistent with `downstream.md` already naming "MEMORY" as the RTL owner
  of "ROM/SRAM actual target implementations."
- **what_you_implemented_meanwhile**: `rom.sv` implements AXI-01/02/03/06/08
  and SYS-04 exactly as the prose states (including read-only enforcement:
  a defensive SLVERR with no side effect on any write, since the fabric
  should never forward one here). `sram.sv` implements the same
  requirement set with real byte-enable writes (same issue filed there).
  Nothing was withheld or altered because of this metadata gap; it is
  reported for traceability hygiene only.

## Resolution (CHANGE_ORDER_rc4, 2026-09-06)

- **disposition**: `metadata` (per rc4 ruling table row "ISSUE-mem-01").
  `contract.json` `requirements[]` now lists `rom`, `sram` in
  `owner_modules` for AXI-01, AXI-02, AXI-03, AXI-06, AXI-08 and for SYS-04
  (SYS-04 additionally gains `fabric`; separately, rc4 also adds `npu_csr`/
  `lite_bridge` to SYS-08 and `npu_local` to NPU-01..09 as the same defect
  class, outside this module's scope). `traceability.md` mirrors the same
  rows. Verified directly against this worktree's checked-out
  `docs/spec/llm-soc-v1/contract.json` and `traceability.md` at commit
  bd3b438d — both already carry `rom`/`sram` in the affected rows.
- **RTL obligation**: none. rc4's own "Modules that must change (RTL)"
  list states explicitly: "No change: cpu_bridge, lite_bridge, rom, sram,
  npu_dma, npu_local, sw/." Additionally the SLVERR-on-write response
  (`s_axi_bresp = 2'b10`) already cites SYS-04 in-line; no comment change
  was needed there either. `rom.sv`/`sram.sv` were already implemented
  against the axi.md/system.md prose exactly as this issue's
  `what_you_implemented_meanwhile` section recorded; nothing in that
  implementation contradicts the now-corrected metadata.
- **DV obligation** (per rc4, not this role's to discharge): evidence
  ledger links rom/sram deliveries to the AXI-01/02/03/06/08 and SYS-04
  rows now that `owner_modules` names them.
- **status**: closed. No code change in `hw/rtl/rom/` or `hw/rtl/sram/`.
