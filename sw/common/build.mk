# sw/common/build.mk — shared toolchain flags for every sw/ sub-build.
# Included by sw/rom/Makefile and sw/b1/Makefile. Toolchain: pinned xPack
# riscv-none-elf-gcc (root Makefile TOOLPATH); flags per the B1 task contract:
# soft-float rv32im/ilp32, -Wall -Wextra -Werror -Os -ffreestanding -nostdlib.

CROSS      ?= riscv-none-elf-
CC         := $(CROSS)gcc
OBJCOPY    := $(CROSS)objcopy
OBJDUMP    := $(CROSS)objdump
SIZE       := $(CROSS)size

SW_COMMON  := $(SW_ROOT)/common

CFLAGS_COMMON := -march=rv32im -mabi=ilp32 -mno-relax \
                  -Os -Wall -Wextra -Werror \
                  -ffreestanding -nostdlib -fno-builtin \
                  -ffunction-sections -fdata-sections \
                  -fno-strict-aliasing \
                  -std=c11 \
                  -I$(SW_COMMON)

ASFLAGS_COMMON := -march=rv32im -mabi=ilp32 -mno-relax -I$(SW_COMMON)

LDFLAGS_COMMON := -march=rv32im -mabi=ilp32 -mno-relax \
                   -nostdlib -static \
                   -Wl,--gc-sections -Wl,--build-id=none -Wl,--no-warn-rwx-segments
