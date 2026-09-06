/* sw/b1/npu.h — NPU GEMV_GROUP_I8 command driver (npu.md NPU-04..NPU-08).
 *
 * This header only exposes the low-level register-level primitives used to
 * build the exact driver sequence NPU-08 requires:
 *   "CLEAR previous terminal state; write immutable X/W bytes; compiler
 *   barrier; program all shadow fields; SUBMIT; wait on STATUS or IRQ;
 *   require DONE&&!ERROR and matching COMPLETED_TAG; compiler barrier;
 *   load every output word."
 * The X/W-byte-writing and Y-word-reading steps are ordinary memory stores
 * and loads at the descriptor's own addresses, so they are not wrapped here
 * — only the CSR-facing half of the sequence is.
 */
#ifndef OPENCHIP_SW_B1_NPU_H
#define OPENCHIP_SW_B1_NPU_H

#include <stdint.h>

#define NPU_OPCODE_GEMV_GROUP_I8 1u

typedef struct {
    uint32_t opcode;
    uint32_t x_base;
    uint32_t w_base;
    uint32_t y_base;
    uint32_t k;
    uint32_t n;
    uint32_t group;
    uint32_t w_stride;
    uint32_t tag;
} npu_descriptor_t;

/* NPU-04 CLEAR: "clears DONE, ERROR, ERROR_CODE, COMPLETED_TAG; rejects
 * while BUSY". Caller must only invoke this when STATUS.BUSY==0 (a SLVERR
 * here is a CSR-layer protocol violation and, per SYS-07, FATAL — there is
 * no software recovery). */
void npu_clear(void);

/* NPU-04/NPU-05: program every shadow field, valid only while
 * BUSY=0 && DONE=0 && ERROR=0. Does not itself SUBMIT. */
void npu_program(const npu_descriptor_t *d);

/* NPU-04 SUBMIT: "write1 only: validate and atomically snapshot
 * descriptor." */
void npu_submit(void);

/* Raw STATUS word (bit0 BUSY, bit1 DONE, bit2 ERROR). */
uint32_t npu_status(void);

/* Busy-poll STATUS.BUSY until it clears, then return the terminal STATUS
 * word. Used only by the polling-driven command (B1 requires exactly one
 * polled and one IRQ-driven command, npu.md NPU-08 paragraph 2). */
uint32_t npu_poll_until_terminal(void);

uint32_t npu_completed_tag(void);
uint32_t npu_error_code(void);

#endif /* OPENCHIP_SW_B1_NPU_H */
