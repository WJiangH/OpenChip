# Pinned tool versions — the reproducibility contract (docs/ARCHITECTURE.md).
# Change only in a dedicated PR with all gates green. "Works on my machine" is banned.

# YosysHQ OSS CAD Suite release tag (yosys, verilator, iverilog, sby, verible, gtkwave)
# https://github.com/YosysHQ/oss-cad-suite-build/releases
OSS_CAD_SUITE_TAG := 2026-07-26

# LibreLane (ex-OpenLane 2) container, https://github.com/librelane/librelane
# 3.0.5 verified P0 (no `latest` tag exists on ghcr; pinned by digest — tags are mutable)
LIBRELANE_IMAGE := ghcr.io/librelane/librelane:3.0.5@sha256:ecabd075d0ddf6a2bd1cd4a32109c7dbb861ec007f7e4e423a9a081f8d23b8e2

# xPack riscv-none-elf-gcc
RISCV_GCC_VERSION := 14.2.0-3   # xPack darwin-arm64 tarball sha256 e08754e8c500f8e92b3b4ff7b0444cfbf3b218515f322929e0744ec3b9ed80a8, unpacked in .toolcache/
RISCV_PREFIX      := riscv-none-elf-

# Golden ISA model + compliance framework (pinned in M2)
SPIKE_COMMIT  := unpinned   # installed 2026-09-05 via brew riscv-software-src/riscv/riscv-isa-sim (bottle "main", reports 1.1.1-dev); FLOW-001: rebuild from a pinned commit before the compliance gate is trusted
RISCOF_VERSION := 1.25.3    # pip, in .venv

# PDK
PDK := sky130A
SCL := sky130_fd_sc_hd

# Python side is pinned in requirements.txt (cocotb etc.)
