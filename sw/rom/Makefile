# sw/rom/Makefile — 64 KiB boot ROM (SYS-05/SYS-06).
SW_ROOT := $(abspath ..)
include $(SW_ROOT)/common/build.mk

OBJS := rom_main.o crc32.o libc_stubs.o rom_start.o

INCLUDES := -I. -I$(SW_ROOT)/common

.PHONY: all clean

all: rom.elf rom.bin rom.hex

rom_main.o: rom_main.c boot_header.h $(SW_ROOT)/common/regmap.h $(SW_ROOT)/common/mmio.h $(SW_ROOT)/common/crc32.h
	$(CC) $(CFLAGS_COMMON) $(INCLUDES) -c $< -o $@

crc32.o: $(SW_ROOT)/common/crc32.c $(SW_ROOT)/common/crc32.h
	$(CC) $(CFLAGS_COMMON) $(INCLUDES) -c $< -o $@

libc_stubs.o: $(SW_ROOT)/common/libc_stubs.c $(SW_ROOT)/common/libc_stubs.h
	$(CC) $(CFLAGS_COMMON) $(INCLUDES) -c $< -o $@

rom_start.o: rom_start.S $(SW_ROOT)/common/regmap.h $(SW_ROOT)/common/irq_asm.h
	$(CC) $(ASFLAGS_COMMON) $(INCLUDES) -c $< -o $@

rom.elf: rom_start.o rom_main.o crc32.o libc_stubs.o link_rom.ld
	$(CC) $(LDFLAGS_COMMON) -T link_rom.ld rom_start.o rom_main.o crc32.o libc_stubs.o -o $@
	$(SIZE) $@

rom.bin: rom.elf
	$(OBJCOPY) -O binary $< $@
	@sz=$$(wc -c < $@); \
	 if [ $$sz -gt 65536 ]; then echo "rom.bin: $$sz bytes exceeds 64 KiB ROM budget"; exit 1; fi; \
	 echo "rom.bin: $$sz bytes (<= 65536)"

rom.hex: rom.bin
	python3 $(SW_ROOT)/tools/bin2hex.py $< $@ 65536

clean:
	rm -f *.o rom.elf rom.bin rom.hex
