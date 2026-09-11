# ADR 0004: CoralNPU native import boundary

Status: proposed repository import; behavioral profile CN-EXTMEM-01 v0.4.

The [external-memory workload](../../workloads/coralnpu_external_memory/README.md)
requires a compiled program to fetch instructions and transfer input/output data
across the core's external manager boundary. The selected experiment uses
upstream `google-coral/coralnpu` at
`561c59d33fea8a02e7f1062956ec77740e0eb955`, configuration
`RvvCoreMiniHighmemAxi`: RV32/RVV VLEN128, 1 MiB ITCM and 1 MiB DTCM.
The normative interface and acceptance criteria are in the
[contract](../spec/coralnpu_external_memory.md); immutable source citations are
in its [source index](../spec/coralnpu_external_memory.sources.json).

The repository import places its source pin and acquisition/generation entry
under `hw/ip/coralnpu/`. It preserves native Chisel/Bazel generation, AXI
manager/subordinate A32 D128 ID6 ports, active-high interrupts, and active-low
reset with asynchronous assertion and synchronized release. It does not
translate the IP to the reference design's Wishbone or rewrite the upstream
hardware to satisfy that design's naming/reset conventions. Simulation-host
loading and the separate external responder remain experiment adapters.
Software and independently authored DV occupy the contract's §9 paths.

The selected source tree contains both `SRAM.scala` and `Sram.scala`. Source
materialization must preserve both names on a case-sensitive filesystem.
Pinned `.bazelversion` specifies 8.6.0; the upstream default `.bazelrc` uses
WORKSPACE dependencies and the toolchain declares Linux x86_64 execution.
The native flow records its actual selected dependencies, upstream patches,
licenses/notices and configuration overrides. The source index is not a
transitive redistribution audit or a toolchain lockfile.

The broader TL-UL subsystem is outside this import selection. The host's direct
pre-release initialization of simulation memory proves no production DDR
loading path. An emitted model is not a passing DUT test; repository import
readiness, positive execution, negative/reset acceptance, and full AXI/ISA/SoC,
LLM, coverage, FPGA and physical/tapeout signoff remain separate decisions.
Prior experiment receipts keep their original candidates and versions.

[Native build configuration](https://github.com/google-coral/coralnpu/blob/561c59d33fea8a02e7f1062956ec77740e0eb955/.bazelrc),
[toolchain execution constraint](https://github.com/google-coral/coralnpu/blob/561c59d33fea8a02e7f1062956ec77740e0eb955/toolchain/BUILD.bazel),
[dependency declarations](https://github.com/google-coral/coralnpu/blob/561c59d33fea8a02e7f1062956ec77740e0eb955/rules/repos.bzl).
