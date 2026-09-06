# sw/Makefile — root `make sw` entry point (invoked by the top-level
# Makefile as `$(MAKE) -C sw` when this file exists). Builds:
#   sw/common/regmap.h  (generated from contract.json)
#   sw/rom/{rom.elf,rom.bin,rom.hex}
#   sw/b1/{b1.elf,b1.bin,b1.hex}         (also regenerates sw/b1/fixtures.h)
#   sw/b1_extmem*.{bin,json}            (mkimage.py, good + 2 negative variants)
#   sw/reports/b1-footprint.md
#
# Toolchain: pinned xPack riscv-none-elf-gcc via the root Makefile's
# TOOLPATH; also exported directly here so `make -C sw` works standalone.
SW_ROOT := $(abspath .)
TOOLCHAIN_BIN := $(abspath ../.toolcache/xpack-riscv-none-elf-gcc-14.2.0-3/bin)
export PATH := $(TOOLCHAIN_BIN):$(PATH)

PY := python3

.PHONY: all regmap rom b1 images footprint selftest clean

all: regmap rom b1 images footprint

regmap:
	@riscv-none-elf-gcc --version | head -1
	$(PY) tools/gen_regmap.py

rom: regmap
	$(MAKE) -C rom

b1: regmap
	$(MAKE) -C b1

images: rom b1
	$(PY) tools/mkimage.py --b1-elf b1/b1.elf --out-dir .

footprint: rom b1
	$(PY) tools/gen_footprint.py

selftest:
	$(PY) tools/mkimage.py --selftest

clean:
	$(MAKE) -C rom clean
	$(MAKE) -C b1 clean
	rm -f b1_extmem*.bin b1_extmem*.json

.DEFAULT_GOAL := all
