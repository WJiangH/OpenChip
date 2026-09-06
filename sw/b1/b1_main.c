/* sw/b1/b1_main.c — B1 firmware application.
 *
 * Exercises NPU-08's driver sequence twice — once polled, once IRQ-driven —
 * with the two fixed test vectors in fixtures.h (distinct nonzero signed
 * X/W, INT8 extrema, non-divisible K/G, nonzero Y sentinel pre-fill), then
 * reports SYS-09..SYS-12 RESULT_VALID/RESULT_CODE. Word-by-word INT32
 * comparison is against the independently host-computed expected bytes at
 * 0x80700000 (npu.md NPU-08: "intermediate arithmetic checks compare actual
 * Y with an independently generated grouped-dot reference"); this file
 * never computes or replaces NPU output (AXI-10) — it only compares.
 *
 * RESULT_CODE values 0xC0xx below are a software-owned convention (SYS-08:
 * "otherwise software error code" — the spec does not fix B1 failure
 * codes), documented here rather than in regmap.h since they are not
 * contract.json material.
 */
#include <stdint.h>
#include "regmap.h"
#include "mmio.h"
#include "compiler_barrier.h"
#include "irq_asm.h"
#include "uart.h"
#include "npu.h"
#include "crc32.h"
#include "fixtures.h"

#define B1_RESULT_PASS         0x00000000u
#define B1_RESULT_BAD_EXPECTED 0x0000C001u
#define B1_RESULT_NPU_STATE    0x0000C002u
#define B1_RESULT_Y_MISMATCH   0x0000C003u
#define B1_RESULT_IRQ_TIMEOUT  0x0000C004u

/* B1's own independent-expected blob format at 0x80700000 (see
 * sw/tools/fixtures.py build_expected_blob() docstring: this is B1's own
 * from-scratch layout, explicitly not the L1 LLM-11 kind1..7 format). */
typedef struct {
    uint32_t magic;
    uint32_t abi;
    uint32_t cmd_count;
    uint32_t blob_bytes;
    uint32_t crc32;
    uint32_t reserved0;
    uint32_t reserved1;
    uint32_t reserved2;
} b1_expected_header_t;

typedef struct {
    uint32_t tag;
    uint32_t word_count;
    uint32_t byte_offset;
    uint32_t reserved0;
} b1_expected_record_t;

/* ---- IRQ dispatch state (written only from b1_irq_dispatch, the IRQ
 * trampoline's C callee; read by the main-line command-B wait loop). ---- */
static volatile uint32_t g_npu_irq_fired;
static volatile uint32_t g_npu_irq_done;
static volatile uint32_t g_npu_irq_error;
static volatile uint32_t g_npu_irq_tag;

/* Called from sw/common/crt0.S (picorv32_irq_common_entry) with a0 = the
 * pending IRQ bitmask captured from q1 at IRQ entry. */
void b1_irq_dispatch(uint32_t irq_mask) {
    if (irq_mask & (IRQ_NPU_DONE_CPU_MASK | IRQ_NPU_ERROR_CPU_MASK)) {
        uint32_t st = npu_status();
        g_npu_irq_done = (st & NPU_CSR_STATUS_DONE_MASK) != 0u;
        g_npu_irq_error = (st & NPU_CSR_STATUS_ERROR_MASK) != 0u;
        g_npu_irq_tag = npu_completed_tag();
        /* SYS-10 "clear source before return": clearing NPU DONE/ERROR
         * deasserts the derived IRQ.PENDING bits (contract.json irq.PENDING
         * derived_expression) that gate CPU irq[4]/irq[5], so this must run
         * before retirq or the level-sensitive interrupt would re-trap
         * immediately. Captured status/tag above are what the main-line
         * NPU-08 "require DONE&&!ERROR and matching COMPLETED_TAG" check
         * uses; it is not re-read live after this clear. */
        npu_clear();
        g_npu_irq_fired = 1u;
    }
    /* bit6 (UART tx_empty) is never unmasked by this firmware. */
}

static uint32_t read_word(uint32_t addr) {
    return mmio_read32(addr);
}

static void write_i8_bytes(uint32_t addr, const int8_t *data, uint32_t n) {
    volatile uint8_t *p = (volatile uint8_t *)(uintptr_t)addr;
    for (uint32_t i = 0; i < n; i++) {
        p[i] = (uint8_t)data[i];
    }
}

static void fill_y_sentinel(uint32_t addr, uint32_t word_count) {
    volatile uint32_t *p = (volatile uint32_t *)(uintptr_t)addr;
    for (uint32_t i = 0; i < word_count; i++) {
        p[i] = B1_Y_SENTINEL_WORD;
    }
}

/* ---- independent-expected blob validation (loaded once, used by both
 * commands' checks) ---- */
static int expected_find(uint32_t tag, uint32_t *out_word_count, uint32_t *out_byte_offset) {
    const b1_expected_header_t *hdr =
        (const b1_expected_header_t *)(uintptr_t)REGION_EXPECTED_BASE;

    if (hdr->magic != B1_EXPECTED_MAGIC) return 0;
    if (hdr->abi != B1_EXPECTED_ABI) return 0;
    if (hdr->cmd_count != B1_EXPECTED_CMD_COUNT) return 0;
    if (hdr->blob_bytes < sizeof(b1_expected_header_t) ||
        hdr->blob_bytes > REGION_EXPECTED_SIZE) {
        return 0;
    }

    const uint8_t *body = (const uint8_t *)(uintptr_t)(REGION_EXPECTED_BASE + sizeof(b1_expected_header_t));
    uint32_t body_len = hdr->blob_bytes - (uint32_t)sizeof(b1_expected_header_t);
    uint32_t crc = crc32_iso_hdlc(body, body_len);
    if (crc != hdr->crc32) return 0;

    const b1_expected_record_t *rec =
        (const b1_expected_record_t *)(const void *)body;
    for (uint32_t i = 0; i < hdr->cmd_count; i++) {
        if (rec[i].tag == tag) {
            *out_word_count = rec[i].word_count;
            *out_byte_offset = rec[i].byte_offset;
            return 1;
        }
    }
    return 0;
}

/* Exact INT32 word-by-word comparison, npu.md NPU-08 / NPU-05. */
static int compare_y_exact(uint32_t y_base, uint32_t word_count,
                            uint32_t expected_word_count, uint32_t expected_byte_offset) {
    if (word_count != expected_word_count) return 0;
    for (uint32_t i = 0; i < word_count; i++) {
        uint32_t actual = read_word(y_base + 4u * i);
        uint32_t expected = read_word(REGION_EXPECTED_BASE + expected_byte_offset + 4u * i);
        if (actual != expected) return 0;
    }
    return 1;
}

/* ---- command A: CSR-polled completion ---- */
static uint32_t run_cmd_a_polled(void) {
    uart_write_line("B1:CMD_A:POLL:SUBMIT");

    npu_clear(); /* NPU-08: "CLEAR previous terminal state" */
    write_i8_bytes(B1_CMD_A_POLL_X_BASE, b1_cmd_a_poll_x, B1_CMD_A_POLL_K);
    write_i8_bytes(B1_CMD_A_POLL_W_BASE, b1_cmd_a_poll_w,
                   B1_CMD_A_POLL_N * B1_CMD_A_POLL_W_STRIDE);
    fill_y_sentinel(B1_CMD_A_POLL_Y_BASE, B1_CMD_A_POLL_Y_WORDS);
    SW_COMPILER_BARRIER();

    npu_descriptor_t d = {
        .opcode = NPU_OPCODE_GEMV_GROUP_I8,
        .x_base = B1_CMD_A_POLL_X_BASE,
        .w_base = B1_CMD_A_POLL_W_BASE,
        .y_base = B1_CMD_A_POLL_Y_BASE,
        .k = B1_CMD_A_POLL_K,
        .n = B1_CMD_A_POLL_N,
        .group = B1_CMD_A_POLL_GROUP,
        .w_stride = B1_CMD_A_POLL_W_STRIDE,
        .tag = B1_CMD_A_POLL_TAG,
    };
    npu_program(&d);
    npu_submit();

    uint32_t st = npu_poll_until_terminal(); /* "wait on STATUS" */
    uint32_t done = (st & NPU_CSR_STATUS_DONE_MASK) != 0u;
    uint32_t error = (st & NPU_CSR_STATUS_ERROR_MASK) != 0u;
    uint32_t tag = npu_completed_tag();

    if (!done || error || tag != B1_CMD_A_POLL_TAG) {
        uart_write_line("B1:CMD_A:POLL:ERROR");
        return B1_RESULT_NPU_STATE;
    }
    uart_write_line("B1:CMD_A:POLL:DONE");

    SW_COMPILER_BARRIER();
    uint32_t exp_words, exp_off;
    if (!expected_find(B1_CMD_A_POLL_TAG, &exp_words, &exp_off)) {
        uart_write_line("B1:CMD_A:CHECK:BAD_EXPECTED");
        return B1_RESULT_BAD_EXPECTED;
    }
    if (!compare_y_exact(B1_CMD_A_POLL_Y_BASE, B1_CMD_A_POLL_Y_WORDS, exp_words, exp_off)) {
        uart_write_line("B1:CMD_A:CHECK:FAIL");
        return B1_RESULT_Y_MISMATCH;
    }
    uart_write_line("B1:CMD_A:CHECK:PASS");
    return B1_RESULT_PASS;
}

/* ---- command B: IRQ-driven completion (custom IRQ bits 4/5) ---- */
static uint32_t run_cmd_b_irq(void) {
    uart_write_line("B1:CMD_B:IRQ:SUBMIT");

    npu_clear();
    write_i8_bytes(B1_CMD_B_IRQ_X_BASE, b1_cmd_b_irq_x, B1_CMD_B_IRQ_K);
    write_i8_bytes(B1_CMD_B_IRQ_W_BASE, b1_cmd_b_irq_w,
                   B1_CMD_B_IRQ_N * B1_CMD_B_IRQ_W_STRIDE);
    fill_y_sentinel(B1_CMD_B_IRQ_Y_BASE, B1_CMD_B_IRQ_Y_WORDS);
    SW_COMPILER_BARRIER();

    /* NPU_CSR.IRQ_ENABLE: gate the NPU's own done/error terminal levels. */
    mmio_write32(NPU_CSR_IRQ_ENABLE_ADDR,
                 NPU_CSR_IRQ_ENABLE_DONE_MASK | NPU_CSR_IRQ_ENABLE_ERROR_MASK);
    /* IRQ block ENABLE: gate the CPU-visible level for bits done/error. */
    mmio_write32(IRQ_ENABLE_ADDR, IRQ_ENABLE_DONE_MASK | IRQ_ENABLE_ERROR_MASK);

    g_npu_irq_fired = 0u;
    g_npu_irq_done = 0u;
    g_npu_irq_error = 0u;
    g_npu_irq_tag = 0u;

    /* Unmask CPU irq[4] (npu_done) and irq[5] (npu_error) only; every other
     * bit (including irq[6] uart_tx_empty) stays masked. maskirq's return
     * value is the *previous* mask, which fw_init() already set to all-ones
     * (SYS-10 "initially mask every source"), so this is exactly "unmask
     * bits 4/5 from the all-masked baseline". */
    uint32_t new_mask = ~(IRQ_NPU_DONE_CPU_MASK | IRQ_NPU_ERROR_CPU_MASK);
    (void)picorv32_maskirq(new_mask);

    npu_descriptor_t d = {
        .opcode = NPU_OPCODE_GEMV_GROUP_I8,
        .x_base = B1_CMD_B_IRQ_X_BASE,
        .w_base = B1_CMD_B_IRQ_W_BASE,
        .y_base = B1_CMD_B_IRQ_Y_BASE,
        .k = B1_CMD_B_IRQ_K,
        .n = B1_CMD_B_IRQ_N,
        .group = B1_CMD_B_IRQ_GROUP,
        .w_stride = B1_CMD_B_IRQ_W_STRIDE,
        .tag = B1_CMD_B_IRQ_TAG,
    };
    npu_program(&d);
    npu_submit();

    /* "wait on ... IRQ": spin on a flag only ever set inside the IRQ
     * dispatcher; completion detection is the hardware interrupt, not CSR
     * polling. Bounded so a wiring defect fails the run instead of hanging
     * the harness forever (debug bound only, not an npu.md requirement
     * number: NPU-07's own 2^28-cycle watchdog is a hardware/global-fatal
     * concern, this is just firmware self-defense). */
    uint32_t spins = 0;
    while (!g_npu_irq_fired) {
        spins++;
        if (spins > 100000000u) {
            uart_write_line("B1:CMD_B:IRQ:TIMEOUT");
            return B1_RESULT_IRQ_TIMEOUT;
        }
    }

    /* Re-mask bits 4/5 (return to the all-masked baseline; SYS-10 hygiene). */
    (void)picorv32_maskirq(PICORV32_IRQ_MASK_ALL);

    if (!g_npu_irq_done || g_npu_irq_error || g_npu_irq_tag != B1_CMD_B_IRQ_TAG) {
        uart_write_line("B1:CMD_B:IRQ:ERROR");
        return B1_RESULT_NPU_STATE;
    }
    uart_write_line("B1:CMD_B:IRQ:DONE");

    SW_COMPILER_BARRIER();
    uint32_t exp_words, exp_off;
    if (!expected_find(B1_CMD_B_IRQ_TAG, &exp_words, &exp_off)) {
        uart_write_line("B1:CMD_B:CHECK:BAD_EXPECTED");
        return B1_RESULT_BAD_EXPECTED;
    }
    if (!compare_y_exact(B1_CMD_B_IRQ_Y_BASE, B1_CMD_B_IRQ_Y_WORDS, exp_words, exp_off)) {
        uart_write_line("B1:CMD_B:CHECK:FAIL");
        return B1_RESULT_Y_MISMATCH;
    }
    uart_write_line("B1:CMD_B:CHECK:PASS");
    return B1_RESULT_PASS;
}

static void commit_result(uint32_t code) {
    mmio_write32(SYS_RESULT_CODE_ADDR, code);
    /* SYS-08: "additional commits rejected" — exactly one commit. */
    mmio_write32(SYS_RESULT_COMMIT_ADDR, 1u);
}

void b1_main(void) {
    /* system.md BOOT_STAGE: "...2 firmware, 3 B1, 4 L1". ROM already set 2;
     * this firmware is the B1 selected run. */
    mmio_write32(SYS_BOOT_STAGE_ADDR, 3u);
    uart_write_line("B1:BOOT_STAGE=3");

    uint32_t result = run_cmd_a_polled();
    if (result == B1_RESULT_PASS) {
        /* Command B (IRQ-driven) only runs if command A already passed —
         * no value in exercising the IRQ path once the run has already
         * failed; the failing code from A is what gets reported. */
        result = run_cmd_b_irq();
    }

    if (result == B1_RESULT_PASS) {
        uart_write_line("B1:RESULT:PASS");
    } else {
        uart_write_line("B1:RESULT:FAIL");
        uart_write_hex32(result);
        uart_putc('\r');
        uart_putc('\n');
    }
    commit_result(result);

    for (;;) {
        /* Nothing more to do; RESULT_VALID/RESULT_CODE are already latched
         * and observable at the top level (o_result_valid/o_result_code). */
    }
}
