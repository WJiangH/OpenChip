# sw/estimate/ — firmware footprint estimate build (issue #6, Q-SOC1-03).
# Not the M3 firmware build (that is `make sw` at the repo root, once
# sw/Makefile lands); see sw/estimate/README.md.
#
# Toolchain pin: flow/versions.mk (RISCV_GCC_VERSION, RISCV_PREFIX).
# RISCV_GCC_BINDIR may be set to point at a local extract of that pinned
# xpack release if it is not already on PATH.

RISCV_PREFIX ?= riscv-none-elf-
RISCV_GCC_BINDIR ?=
CC := $(RISCV_GCC_BINDIR)$(RISCV_PREFIX)gcc
SIZE := $(RISCV_GCC_BINDIR)$(RISCV_PREFIX)size
OBJCOPY := $(RISCV_GCC_BINDIR)$(RISCV_PREFIX)objcopy

CFLAGS := -march=rv32imc -mabi=ilp32 -Os -ffreestanding -fno-builtin \
          -nostdlib -nostartfiles -Wall -Wextra -I common -g
LDFLAGS_COMMON := -nostdlib -Wl,--gc-sections -Wl,-Map=$@.map

.PHONY: all clean size report

all: boot.elf firmware.elf

boot.elf: boot/link_boot.ld common/crt0.S boot/boot_main.c common/uart.c
	$(CC) $(CFLAGS) -T boot/link_boot.ld $(LDFLAGS_COMMON) \
	    common/crt0.S boot/boot_main.c common/uart.c -o $@

firmware.elf: firmware/link_fw.ld common/crt0.S firmware/fw_main.c firmware/irq.c common/uart.c
	$(CC) $(CFLAGS) -T firmware/link_fw.ld $(LDFLAGS_COMMON) \
	    common/crt0.S firmware/fw_main.c firmware/irq.c common/uart.c -o $@

size: all
	@echo "== boot.elf =="
	$(SIZE) -A boot.elf
	@echo "== firmware.elf =="
	$(SIZE) -A firmware.elf

clean:
	rm -f boot.elf firmware.elf *.map
