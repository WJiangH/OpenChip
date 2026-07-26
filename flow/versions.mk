# Pinned tool versions — the reproducibility contract (docs/ARCHITECTURE.md).
# Change only in a dedicated PR with all gates green. "Works on my machine" is banned.

# YosysHQ OSS CAD Suite release tag (yosys, verilator, iverilog, sby, verible, gtkwave)
# https://github.com/YosysHQ/oss-cad-suite-build/releases
OSS_CAD_SUITE_TAG := 2026-07-26

# LibreLane (ex-OpenLane 2) container, https://github.com/librelane/librelane
LIBRELANE_IMAGE := ghcr.io/librelane/librelane:3.0.0   # TODO M0: verify current tag

# xPack riscv-none-elf-gcc
RISCV_GCC_VERSION := 14.2.0-3   # TODO M2: confirm against Spike/RISCOF pins
RISCV_PREFIX      := riscv-none-elf-

# Golden ISA model + compliance framework (pinned in M2)
SPIKE_COMMIT  := TODO-M2
RISCOF_VERSION := TODO-M2

# PDK
PDK := sky130A
SCL := sky130_fd_sc_hd

# Python side is pinned in requirements.txt (cocotb etc.)
