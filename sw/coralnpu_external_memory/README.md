# CoralNPU external-memory software

Five freestanding RV32 ELF programs implement the software obligations in
[CN-EXTMEM-01 v0.4](../../docs/spec/coralnpu_external_memory.md) and its
[workload](../../workloads/coralnpu_external_memory/README.md). The positive
program calls a tail-bounded RVV INT8 GEMV kernel twice, consumes external inputs
after release, and computes unsigned signatures. Four isolated error programs
exercise designated fetch, load, store and unmapped-load operations. Fetch,
load and store each use the same ELF for both error response types.

## Build and inspect

Use Python 3.9 or later and the native RISC-V GNU toolchain provided by the
[pinned upstream source](../../hw/ip/coralnpu/README.md). Supply a toolchain root
containing `bin/riscv64-unknown-elf-gcc`, `as`, `ld`, `objdump` and `readelf`
(with that common prefix). The compiler must support the exact ISA flags in
`build.py`; the baseline identifies GCC 16.1.0, and each build records executable
hashes rather than treating the version string as a complete identity.

```sh
python3 sw/coralnpu_external_memory/build.py \
  --toolchain-root "$RISCV_TOOLCHAIN_ROOT" --output /tmp/coralnpu-sw-build
python3 sw/coralnpu_external_memory/inspect.py \
  --output /tmp/coralnpu-sw-build --verify
```

Without the option, discovery uses `RISCV_TOOLCHAIN_ROOT`, then the compiler on
`PATH`. No download or cache path is embedded in this driver. The output must
be new or empty. A serial build has a 120-second compiler budget. Named objects
and fixed relative linker paths avoid random temporary object names in ELF
symbols and stabilize maps. Repeat into a second output directory with the same
sources and tools to compare ELF/map/manifest hashes. Changed ELF hashes require
source/disassembly review; a successful build alone does not transfer an earlier
execution result. Generated binaries and receipts stay outside source history.
Every invoked command retains raw output and stage/exit status under
`diagnostics/`, including failures and timeouts. On timeout the driver sends
SIGKILL to its owned process group and reaps the direct child; the receipt records
those actions. Diagnostic paths/timings are excluded from deterministic metadata.

`manifest.json` uses schema 1 and contract version `0.4`. `upstream` binds the
commit and tree. `artifacts` has keys `positive`, `fetch`, `load`, `store`, and
`unmapped`; each supplies `elf`, `map` and `disassembly` objects with `path` and
`sha256`, an integer ELF `entry`, integer symbol addresses/sizes with `STT_*`
types, and PT_LOAD descriptions. All artifact paths are relative to the manifest
folder. Symbols include `_start`, `rvv_gemv_int8`, `trap_handler`, `main`,
`clean_halt` and the four-byte `_ret`; negatives additionally expose
`fault_instruction`. Top-level `source_sha256`, `toolchain`, `flags` and the
hashed `build-info.json` bind build inputs and commands. Source keys are relative
to this software directory. Independent DV derives expected values and trap
causes from the contract; the manifest supplies no golden answers.
The inspector requires the complete fixed source set, seven tool executable
hashes, builtin header hashes including `stdint.h` and `stddef.h`, compiler
version, exact ISA/other flags, and the full ordered build commands. Empty or
partial bindings fail. Tool hashes describe the tools recorded by the build;
the manifest is reproducible evidence, not an independently attested runtime.

`inspect.py` checks ELF placement, return slot, symbol extents, clean MPAUSE,
vector/probe instructions and both positive kernel call sites. `--verify`
recomputes metadata without replacing the existing manifest. These are static
checks; independent software review still checks source/disassembly, and DV
owns execution. ISS execution, ISA closure, timing, PPA and full-model inference
are not established by this package. Headless completion uses the contract's
memory record and halt/fault signals rather than a UART.

Run `python3 sw/coralnpu_external_memory/regression.py` for CPU-only adversarial
metadata checks and a harmless child timeout control. These checks require no
toolchain or DUT and do not establish compilation or execution acceptance.

## Source adaptation

Pinned `google-coral/coralnpu` commit
`561c59d33fea8a02e7f1062956ec77740e0eb955`, tree
`9dbf21aa935571f43e79a2fe15df28275f7d6636`, supplies the Apache-2.0 assets retained
under `upstream/`: `rvv_int8_matmul.cc`, `coralnpu_start.S`,
`cc_toolchain_config.bzl`, and `LICENSE`. Original notices remain intact.
The kernel originates in `tests/cocotb/rvv/ml_ops/gemma_kernels/rvv_int8_matmul.cc`;
these are software inputs, not a copied test oracle. `kernel.S` adapts the GEMV
routine into one N-tile path with AVL=N-n, individual signed A-byte loads and
bounded vector stores. It replaces the main/tail split and K unrolling,
reduces register groups and omits the unused matmul wrapper. e8/m1, e16/m2 and
e32/m4 share VLMAX, preserving the logical output tail without padded C arrays.

`start.S` adapts the upstream CRT into the reviewed headless return sequence:
SP=0x00200000, direct mtvec, FS/VS enablement, `_ret` sentinel before main,
actual return capture, magic committed last, retirement counters and MPAUSE.
It omits generic register clearing, constructors/finalizers and libc; the ELF
loader owns BSS zeroing. The handler captures trap CSRs, stores return1 and the
record, writes magic last, and terminates without resuming. `main.c`,
`negative.S` and `link.ld` supply the workload, isolated operations and contract
placement. The five software source files retain their previously reviewed
algorithm/placement bytes; older version/work-item comments identify their
adaptation origin. This directory's governing behavioral contract is v0.4.

Review changes directly with `diff -u upstream/coralnpu_start.S start.S` and
`diff -u upstream/rvv_int8_matmul.cc kernel.S`. Build manifests hash both original
and adapted assets. No upstream hardware or generator modifications are included.
