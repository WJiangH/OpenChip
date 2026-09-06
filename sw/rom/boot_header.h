/* sw/rom/boot_header.h — boot image header layout, SYS-05:
 *
 * "ROM code shall load a 64-byte header at 0x80000000 followed by firmware
 * bytes at 0x80000040. Header u32 words: magic 0x4C4C4D31, ABI=1,
 * byte_length (1..0x30000), load=0x10000000, entry=0x10000000, CRC32, BSS
 * start, BSS length; words 8..15 zero."
 *
 * Not contract.json material (contract.json's csr_registers/address_regions/
 * irqs sections do not include this layout) — hand-transcribed from
 * system.md prose, mirrored byte-for-byte in sw/tools/mkimage.py so the ROM
 * and the host image builder never drift.
 */
#ifndef OPENCHIP_SW_ROM_BOOT_HEADER_H
#define OPENCHIP_SW_ROM_BOOT_HEADER_H

#include <stdint.h>

#define BOOT_HEADER_MAGIC   0x4C4C4D31u
#define BOOT_HEADER_ABI     1u
#define BOOT_HEADER_BYTES   64u

#define BOOT_FW_LOAD_ADDR   0x10000000u
#define BOOT_FW_ENTRY_ADDR  0x10000000u
#define BOOT_FW_MAX_BYTES   0x30000u   /* byte_length in [1, 0x30000] */

/* SYS-06 linker map: executable/data/BSS below 0x10030000; stack region is
 * 0x10030000..0x10040000 (64 KiB). */
#define FW_BSS_END_LIMIT    0x10030000u

/* SYS-06 RESULT_CODE values on ROM boot failure. */
#define BOOT_RESULT_BAD_HEADER 0xB001u
#define BOOT_RESULT_BAD_CRC    0xB002u
#define BOOT_RESULT_BAD_BOUNDS 0xB003u

typedef struct {
    uint32_t magic;
    uint32_t abi;
    uint32_t byte_length;
    uint32_t load;
    uint32_t entry;
    uint32_t crc32;
    uint32_t bss_start;
    uint32_t bss_length;
    uint32_t reserved[8]; /* words 8..15, must be zero */
} boot_header_t;

#endif /* OPENCHIP_SW_ROM_BOOT_HEADER_H */
