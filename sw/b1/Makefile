# sw/b1/Makefile — B1 firmware application (NPU-08 driver sequence,
# SYS-09..SYS-12 result reporting).
SW_ROOT := $(abspath ..)
include $(SW_ROOT)/common/build.mk

INCLUDES := -I. -I$(SW_ROOT)/common

OBJS := b1_start.o crt0.o b1_main.o npu.o uart.o crc32.o libc_stubs.o

.PHONY: all clean fixtures

all: fixtures b1.elf b1.bin b1.hex

# fixtures.h is generated (see sw/tools/gen_fixtures_header.py); regenerate
# so the committed header always reflects sw/tools/fixtures.py.
fixtures:
	python3 $(SW_ROOT)/tools/gen_fixtures_header.py

b1_start.o: b1_start.S $(SW_ROOT)/common/irq_asm.h
	$(CC) $(ASFLAGS_COMMON) $(INCLUDES) -c $< -o $@

crt0.o: $(SW_ROOT)/common/crt0.S $(SW_ROOT)/common/irq_asm.h
	$(CC) $(ASFLAGS_COMMON) $(INCLUDES) -c $< -o $@

b1_main.o: b1_main.c fixtures.h npu.h $(SW_ROOT)/common/regmap.h \
           $(SW_ROOT)/common/mmio.h $(SW_ROOT)/common/uart.h \
           $(SW_ROOT)/common/compiler_barrier.h $(SW_ROOT)/common/irq_asm.h \
           $(SW_ROOT)/common/crc32.h
	$(CC) $(CFLAGS_COMMON) $(INCLUDES) -c $< -o $@

npu.o: npu.c npu.h $(SW_ROOT)/common/regmap.h $(SW_ROOT)/common/mmio.h
	$(CC) $(CFLAGS_COMMON) $(INCLUDES) -c $< -o $@

uart.o: $(SW_ROOT)/common/uart.c $(SW_ROOT)/common/uart.h
	$(CC) $(CFLAGS_COMMON) $(INCLUDES) -c $< -o $@

crc32.o: $(SW_ROOT)/common/crc32.c $(SW_ROOT)/common/crc32.h
	$(CC) $(CFLAGS_COMMON) $(INCLUDES) -c $< -o $@

libc_stubs.o: $(SW_ROOT)/common/libc_stubs.c $(SW_ROOT)/common/libc_stubs.h
	$(CC) $(CFLAGS_COMMON) $(INCLUDES) -c $< -o $@

b1.elf: $(OBJS) link_b1.ld
	$(CC) $(LDFLAGS_COMMON) -T link_b1.ld $(OBJS) -o $@
	$(SIZE) $@

b1.bin: b1.elf
	$(OBJCOPY) -O binary $< $@
	@sz=$$(wc -c < $@); \
	 if [ $$sz -gt 196608 ]; then echo "b1.bin: $$sz bytes exceeds 0x30000 firmware budget"; exit 1; fi; \
	 echo "b1.bin: $$sz bytes (<= 196608 / 0x30000)"

b1.hex: b1.bin
	python3 $(SW_ROOT)/tools/bin2hex.py $< $@ 196608

clean:
	rm -f *.o b1.elf b1.bin b1.hex
