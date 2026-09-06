# Deliverable manifest

- Scope: external-IP source/interface/tool intake only; no SoC or security completion claim.
- Artifacts: `RECOMMENDATION.md`, `ip_matrix.json`, `INPUTS_READ.md`, `sourcehash.json`, `probe_results.json`, `final_cell_checks.json`, scripts, original selected upstream source/docs/licenses, all raw logs and five final generic netlists.
- Spec refs: architecture-inputs/e2e.md E2E-01/02/03/06 and I1/S1; llm-target.md LLMP-06/07/08; ADR-0001/0003 are old baseline, not new AXI authority.
- Toolchain: Verilator 5.051 devel v5.050-99-gf8fb1d664 (mod); Yosys 0.67+94 7defa5186-dirty.
- Results: CPU AXI/native strict lint 46/46 warnings; fabric crossbar/AXI-to-Lite/Lite adapter strict lint 185/122/58 warnings. All five synth/check exit0, final netlist latch scan0. No warning waivers.
- Caliptra interface-only lint exit1 (40 warnings); Yosys import parse failure. Full Caliptra core/SS uncompiled.
- Root make lint exits0 vacuously (not acceptance); make synth exits2, missing module recipe. Flow untouched.
- Skipped: sim, coverage, ISA compliance, formal, timing, FPGA, DRC/LVS, security; cleanroom preserved without own TB.
- Owners/open work: architect freeze mode/bridge errors/boot ownership; RTL imported-IP conventions and implementation; DV independent tests/coverage; SW IRQ/softfloat/real firmware; flow harness; backend resources and timing.
- Source identities: every downloaded design/doc file has immutable upstream URL and SHA256 in sourcehash.json; manifest content hashes in ARTIFACT_SHA256SUMS (excluding checksum file itself).
- Local-only: no commit, push or remote PR.

Friction:
- Official CPU drops AXI error information, upstream fabric deprecated, strict lint/Caliptra frontend failures retained; root lint is vacuous.

Skill candidates:
- rtl-engineer/references/external-ip-intake.md — Verify actual response ports and mode-dependent initiators; preserve raw diagnostics and scan final netlists.
