# IP and software dependency lock / adoption state

2026-09-05 · reviewed external-IP metadata from [intake matrix](intake/ip-ip_matrix.json) and [recommendation](intake/ip-RECOMMENDATION.md). Architect did not read implementation RTL or modify it. The evidence below is the intake owner's reported direct probe result, not a new architect-run test.

| Dependency | Pinned identity / license | Decision and exact limit |
|---|---|---|
| PicoRV32 native |a473fc8fca393771d83b0ffcf0b14db3393339d8 /ISC| selected integrate core, new project error bridge required |
| PicoRV32 official AXI wrapper |same commit| rejected for unmodified use: no RRESP/BRESP ports; cannot transport fault status |
| verilog-axi |516bd5dadc3365b7f9e225d2af8fe0b8d804fe53 /MIT| not selected in SIM-L1: default crossbar prepends source ID bits and upstream is deprecated; restricted project fabric/bridge is new implementation work |
| Caliptra core |v2.1.2 =49370266d12cb0c4a8f71b3a0ff7e54ba7d4866e /Apache-2.0| passive-mode S1 candidate only |
| Caliptra ROM |rom-2.1.2 =45de392fb186756bb5c0770e38a5709e3fdc7acb| metadata only, image not built/executed |
| Caliptra firmware |fw-2.1.2 =557fd1a9864831a7d1cdfaffd3b33fd2e26f5e93| metadata only, application-authorization service still needs separate S1 contract |
| Adams Bridge |b77e3d899e828d626cfc2a0d26a6b5704cc121e0| Caliptra dependency, not acquired/executed |
| Caliptra subsystem |css-v2.1.2+1.val.doc =01b0a3528e196f4219d20dd9cbfec3727869d5d9| larger active-mode alternative, not selected |

CPU parameter binding: ENABLE_COUNTERS=1, ENABLE_COUNTERS64=1, ENABLE_REGS_16_31=1, ENABLE_REGS_DUALPORT=1, TWO_STAGE_SHIFT=1, BARREL_SHIFTER=0, TWO_CYCLE_COMPARE=0, TWO_CYCLE_ALU=0, COMPRESSED_ISA=0, CATCH_MISALIGN=1, CATCH_ILLINSN=1, ENABLE_PCPI=0, ENABLE_MUL=1, ENABLE_FAST_MUL=0, ENABLE_DIV=1, ENABLE_IRQ=1, ENABLE_IRQ_QREGS=1, ENABLE_IRQ_TIMER=0, ENABLE_TRACE=1 (for integration evidence), REGS_INIT_ZERO=0, MASKED_IRQ=0xffffff8f, LATCHED_IRQ=0, PROGADDR_RESET=0, PROGADDR_IRQ=0x100, STACKADDR=0x10040000. Any unlisted core parameter retains the pinned upstream default and must be echoed in integration manifest. The intake probe did not exercise all these final parameters together; lint/sim/compliance belongs to the exact integrated configuration.

Imported CPU register-file reset and Verilog constructs may conflict with project-wide every-flop-reset/style rules. This is a surfaced adoption issue, not a blanket waiver: RTL/integrator must resolve scoped imported-IP conventions with explicit evidence before gate acceptance. Firmware initializes registers/state it observes; q2/q3 are scratch and not assumed zero. FENCE is decoded, FENCE.I is unsupported; boot copies executable SRAM before initial jump and forbids self-modifying code. PicoRV32 instruction prefetch exists even without caches, so dynamic instruction rewrites are not safe by assumption.

## Actual intake tool summary

| Scope | Strict Verilator -Wall | Yosys generic synth/check | Final generic cells /latches |
|---|---|---|---|
| PicoRV32 native candidate |exit1,46warnings|exit0,0check problems|13333 /0 |
| PicoRV32 AXI candidate |exit1,46warnings|exit0,0check problems|13107 /0 |
| verilog-axi crossbar defaults |exit1,185warnings|exit0|9776 /0 |
| AXI→Lite defaults |exit1,122warnings|exit0|673 /0 |
| Lite width adapter defaults |exit1,58warnings|exit0|205 /0 |

No warning was disabled. Generic cells are not mapped area, timing or wrapper subtraction evidence. Repository make-lint selected no nested .v implementation and returned a vacuous0; repository make-synth lacked the module script and returned2. These cannot be counted as adoption gates. Independent CPU boot/IRQ/ISA/bridge error, fabric protocol and full-chip simulation have not run.

Caliptra host target is32data/19local-address/8ID/32USER, half-duplex single transaction, with restricted mailbox FIXED bursts; first S1 bridge should use single beats, zero-extend IDs without aliasing and construct nonspoofable requester USER from hardware policy. Its512KiB local window cannot simply be folded into the reserved64KiB SIM-L1 aperture; S1 must publish a checked window and change order. Passive manager inputs tied0/disconnected; subsystem-mode manager is48addr/32data/5ID/32USER. Core ROM96KiB, ICCM256KiB, DCCM256KiB, passive mailbox256KiB plus ECC/crypto SRAM are additional resources. Official docs have a ROM end-address inconsistency; config96KiB is the reported source fact, not a copied0xBFFF range.

The Caliptra AXI interface-only strict lint reports40warnings; native Yosys SV parse fails at `import` in axi_if. No full core/subsystem build, ROM execution or security test ran. Security has clock gating/JTAG/technology memories, asynchronous-assert/synchronous-deassert reset needs and independent powergood sequencing. S1 must explicitly adopt a tested slang/sv2v/frontend or interface wrapper strategy and domain exceptions; SIM-L1's simple synchronous domain cannot serve as proof.

Official primary-source locations: [PicoRV32 pinned repository](https://github.com/YosysHQ/picorv32/tree/a473fc8fca393771d83b0ffcf0b14db3393339d8), [verilog-axi pinned repository](https://github.com/alexforencich/verilog-axi/tree/516bd5dadc3365b7f9e225d2af8fe0b8d804fe53), [Caliptra pinned core](https://github.com/chipsalliance/caliptra-rtl/tree/49370266d12cb0c4a8f71b3a0ff7e54ba7d4866e), [Caliptra software](https://github.com/chipsalliance/caliptra-sw). Intake ledgers retain source hashes, URLs, command arguments and raw-log hashes. Their relative implementation links are provenance, not architect-read files.
