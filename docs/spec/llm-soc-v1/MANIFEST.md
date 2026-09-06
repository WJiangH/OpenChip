# Architecture deliverable manifest

Version1.0-rc3 · chief-architect · LOCAL ONLY. Complete B1/L1 contract submitted for independent review; no frozen/implemented-chip claim. Per-file scope/hash in MANIFEST.json. Forty-five requirement IDs:42SIM-L1 and3S1 integration obligations. Sixteen blocks include the excluded-from-SIM-L1 Caliptra candidate;47connections,14address regions,33CSR words and19AXI-Lite signals are enumerated.

Artifacts: README/system/AXI/NPU/software/security/dependency contracts; machine maps/connectivity/CSR/IRQ/requirements; requirement traceability; downstream deliverables; ADR0004 migration; resource script/JSON/report; fixed workload/profile and twoB1fixtures; reviewed software/IP intake; independent review02 reports; rc2/rc3 change orders and prior/review hashes; input/manifest/audit ledgers. No product implementation was authored.

Actual architect-executed summaries:

```text
BUDGET PASS: MAC/forward=259328 groups/forward=4152 payload=278752 KV512=655360 traffic_floor=278780
CONTRACT AUDIT PASS: blocks=16 connections=47 regions=14 CSR=33 requirements=45 Lite_signals=19; budget/profile consistent
```

Both commands exit0; these check architecture arithmetic and metadata consistency only. Raw command/stdout/exit records are explore/llm-soc-v1/AUDIT.json and AUDIT.txt. No make hardware gate was run for these spec-only changes; no code exists in this task to validate against those gates. Imported software/IP results are identified by owner in dependencies/workload reports; failing strict IP lint is preserved, generic synth is not area/timing acceptance, host inference is not DUT execution.

Open release/evidence items: independent rc3 review closure; final RV32 soft-float/library/startup/link size/stack feasibility and execution; CPU/bridge/fabric/NPU/system RTL and independent DV/formal/ISA; S1 exact Caliptra firmware-service/frontend/fuse/entropy/security-controller supplement; P1 quality/live-tensor/calibrated performance/physical choices; FPGA board and actual memory controller. These are explicitly separate from B1/L1 observable contract completeness. No threshold is waived and no missing hardware result is called passed.

- Friction: upstream group64 tail/row layout, Pico AXI error omission, native read metadata limits, and offered-AXI drain required concrete new contracts; strict IP lint remains failing.
- Skill candidates: chief-architect/references/spec-authoring-patterns.md — Before release, reconcile machine handshake lists, native metadata visibility, offered-versus-accepted lifetimes and static-versus-runtime-input numeric validation.

rc3 correction scope: seven report findings resolved in prose/machine/traceability; both original budget/static commands rerun exit0. Await independent re-review before handoff approval. No target or hardware validation is implied.
