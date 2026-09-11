# Source and dependency notices

CoralNPU is sourced from Google Coral:
https://github.com/google-coral/coralnpu/tree/561c59d33fea8a02e7f1062956ec77740e0eb955

The source snapshot's top-level `LICENSE` is reproduced verbatim as
`LICENSE.upstream`. Individual source headers remain in the complete acquired
tree. The pinned tree contains no separate file named `NOTICE`. No upstream
source bytes are modified or relicensed by this import. The OpenChip fetch/build
entry and manifest are separate integration files.

The native build uses upstream `WORKSPACE` and `.bazelrc` (which disables
Bzlmod), `rules/repos.bzl`, `third_party/`, and their referenced repository rules.
`MODULE.bazel` exists upstream but is not the active dependency selection for
this entry. Selected model generation uses Scala/Chisel/FIRRTL/firtool and native
Verilator/cocotb build rules, with upstream patches retained. Dependencies are
acquired through upstream declarations; they have their own licenses and
notices. The complete acquired source and dependency repositories preserve
those notices. This directory distributes neither generated simulator binaries
nor a repackaged dependency source bundle.

When redistributing a generated RTL, simulator or dependency bundle, retain the
applicable upstream and dependency license/notice files with that distribution.
The source import is not a license inventory or physical-IP signoff for future
redistribution. The exact dependency declarations and their source identity are
covered by the pinned Git tree; changing them requires a new reviewed pin.
