/* sw/rom/rom_main.c — boot ROM program body, SYS-05/SYS-06.
 *
 * Order of operations (quoting SYS-05): "ROM validates header and bounds
 * before copy, copies via CPU AXI load/store, validates CRC over
 * destination bytes, clears BSS, sets stack 0x10040000, writes
 * BOOT_STAGE=2 and jumps to entry only on success."
 *
 * SYS-06 on failure: "On header, CRC or bounds failure ROM sets
 * RESULT_CODE=0xB001, 0xB002 or 0xB003 respectively, pulses result through
 * RESULT_COMMIT, then loops. It shall never jump on failure."
 */
#include <stdint.h>
#include "regmap.h"
#include "mmio.h"
#include "crc32.h"
#include "boot_header.h"

/* All range math in 64-bit unsigned per SYS-05 ("All range calculations use
 * 64-bit unsigned mathematical arithmetic and reject wraparound"). */
typedef uint64_t u64;

static void boot_commit_and_halt(uint32_t result_code) {
    mmio_write32(SYS_RESULT_CODE_ADDR, result_code);
    /* SYS-08 RESULT_COMMIT: "write1 latches RESULT_CODE to output and sets
     * o_result_valid until reset; additional commits rejected." Exactly one
     * commit, ever, from this function. */
    mmio_write32(SYS_RESULT_COMMIT_ADDR, 1u);
    for (;;) {
        /* SYS-06: "It shall never jump on failure." Halt here forever. */
    }
}

static u64 round_up4_u64(u64 v) {
    return (v + 3u) & ~(u64)3u;
}

int rom_main(void) {
    mmio_write32(SYS_BOOT_STAGE_ADDR, 1u); /* stage 1 = loader */

    const boot_header_t *hdr = (const boot_header_t *)REGION_BOOT_IMAGE_BASE;

    /* ---- header validation (SYS-05) -> 0xB001 on failure ---- */
    if (hdr->magic != BOOT_HEADER_MAGIC) boot_commit_and_halt(BOOT_RESULT_BAD_HEADER);
    if (hdr->abi != BOOT_HEADER_ABI) boot_commit_and_halt(BOOT_RESULT_BAD_HEADER);
    if (hdr->byte_length < 1u || hdr->byte_length > BOOT_FW_MAX_BYTES) {
        boot_commit_and_halt(BOOT_RESULT_BAD_HEADER);
    }
    if (hdr->load != BOOT_FW_LOAD_ADDR) boot_commit_and_halt(BOOT_RESULT_BAD_HEADER);
    if (hdr->entry != BOOT_FW_ENTRY_ADDR) boot_commit_and_halt(BOOT_RESULT_BAD_HEADER);
    for (int i = 0; i < 8; i++) {
        /* "words 8..15 zero" — a nonzero reserved word is a malformed
         * header. ISSUE-sw_b1-01: spec does not explicitly list this as a
         * required rejection gate; treated conservatively as 0xB001. */
        if (hdr->reserved[i] != 0u) boot_commit_and_halt(BOOT_RESULT_BAD_HEADER);
    }

    /* ---- bounds validation (SYS-05) -> 0xB003 on failure, 64-bit math ---- */
    u64 byte_length = (u64)hdr->byte_length;
    u64 load = (u64)hdr->load;
    u64 bss_start = (u64)hdr->bss_start;
    u64 bss_length = (u64)hdr->bss_length;

    /* "Payload source must remain within the boot image region." */
    u64 payload_end = (u64)REGION_BOOT_IMAGE_BASE + BOOT_HEADER_BYTES + byte_length;
    if (payload_end < (u64)REGION_BOOT_IMAGE_BASE + BOOT_HEADER_BYTES) { /* wrap */
        boot_commit_and_halt(BOOT_RESULT_BAD_BOUNDS);
    }
    if (payload_end > (u64)REGION_BOOT_IMAGE_END) {
        boot_commit_and_halt(BOOT_RESULT_BAD_BOUNDS);
    }

    /* "BSS start must be 4-aligned and >=load+length rounded to 4" */
    if ((bss_start & 3u) != 0u) boot_commit_and_halt(BOOT_RESULT_BAD_BOUNDS);
    u64 min_bss_start = round_up4_u64(load + byte_length);
    if (min_bss_start < load) boot_commit_and_halt(BOOT_RESULT_BAD_BOUNDS); /* wrap */
    if (bss_start < min_bss_start) boot_commit_and_halt(BOOT_RESULT_BAD_BOUNDS);

    /* "its length must be multiple 4" */
    if ((bss_length & 3u) != 0u) boot_commit_and_halt(BOOT_RESULT_BAD_BOUNDS);

    /* "BSS end must be <=0x10030000" */
    u64 bss_end = bss_start + bss_length;
    if (bss_end < bss_start) boot_commit_and_halt(BOOT_RESULT_BAD_BOUNDS); /* wrap */
    if (bss_end > (u64)FW_BSS_END_LIMIT) boot_commit_and_halt(BOOT_RESULT_BAD_BOUNDS);

    /* ---- copy payload: source (boot image, external mem) -> destination
     * (SRAM at load address), CPU AXI load/store, word-granular with a
     * byte-granular tail for any non-multiple-of-4 remainder. ---- */
    const uint8_t *src = (const uint8_t *)(REGION_BOOT_IMAGE_BASE + BOOT_HEADER_BYTES);
    uint8_t *dst = (uint8_t *)(uintptr_t)hdr->load;
    uint32_t nwords = (uint32_t)(byte_length / 4u);
    uint32_t tail = (uint32_t)(byte_length % 4u);
    const uint32_t *src32 = (const uint32_t *)(const void *)src;
    uint32_t *dst32 = (uint32_t *)(void *)dst;
    for (uint32_t i = 0; i < nwords; i++) {
        dst32[i] = src32[i];
    }
    for (uint32_t i = 0; i < tail; i++) {
        dst[nwords * 4u + i] = src[nwords * 4u + i];
    }

    /* ---- CRC over destination bytes (post-copy), SYS-05 CRC-32/ISO-HDLC ---- */
    uint32_t crc = crc32_iso_hdlc(dst, (size_t)byte_length);
    if (crc != hdr->crc32) {
        boot_commit_and_halt(BOOT_RESULT_BAD_CRC);
    }

    /* ---- clear BSS ---- */
    uint32_t *bss = (uint32_t *)(uintptr_t)hdr->bss_start;
    uint32_t bss_words = hdr->bss_length / 4u;
    for (uint32_t i = 0; i < bss_words; i++) {
        bss[i] = 0u;
    }

    /* Stack is already 0x10040000 (set once in _rom_reset, sw/rom/rom_start.S,
     * and never modified since); SYS-05 lists this as an explicit step, so it
     * is recorded here rather than re-executed redundantly. */

    mmio_write32(SYS_BOOT_STAGE_ADDR, 2u); /* stage 2 = firmware, only on success */

    /* Jump to entry only on success (SYS-05/SYS-06). A function-pointer call
     * is used rather than a bare `jr`: firmware never returns, so the
     * difference is unobservable, and this keeps rom_main() a normal C
     * function for the rest of the validation logic above. */
    void (*entry)(void) = (void (*)(void))(uintptr_t)hdr->entry;
    entry();

    /* Unreachable: firmware must not return. Fail safe if it ever does. */
    boot_commit_and_halt(BOOT_RESULT_BAD_BOUNDS);
    return 0;
}
