/* sw/common/irq_asm.h — PicoRV32 custom IRQ ABI (dependencies.md, hw/ip/picorv32/README.md
 * "Custom Instructions for IRQ Handling"). Hand-written: the encodings below are
 * transcribed from the pinned PicoRV32 README bit patterns and verified against this
 * repo's toolchain (`.insn r opcode,func3,func7,rd,rs1,rs2` operand order), see
 * sw/ISSUES.md for the verification note if any mismatch is ever found.
 *
 * ENABLE_IRQ_QREGS=1 per dependencies.md CPU parameter binding, so getq/setq are
 * available; ENABLE_IRQ_TIMER=0, so `timer` is intentionally not provided here.
 *
 * custom-0 opcode = 0x0B (0b0001011). qs/qd register-number fields (0..3) are
 * encoded in the rs1/rd 5-bit fields using ordinary register names x0..x3 as a
 * vehicle for the 2-bit index — this is a GNU-as `.insn` trick, not a real
 * dependency on x0..x3 architectural state.
 */
#ifndef OPENCHIP_SW_COMMON_IRQ_ASM_H
#define OPENCHIP_SW_COMMON_IRQ_ASM_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

/* ---- Raw-assembly (.S file) macros: unquoted, GAS `.macro` form ---- */
#ifdef __ASSEMBLER__
.macro pr32_getq rd, qs
    .insn r 0x0B, 0, 0, \rd, \qs, x0
.endm
.macro pr32_setq qd, rs
    .insn r 0x0B, 0, 1, \qd, \rs, x0
.endm
.macro pr32_retirq
    .insn r 0x0B, 0, 2, x0, x0, x0
.endm
.macro pr32_maskirq rd, rs
    .insn r 0x0B, 0, 3, \rd, \rs, x0
.endm
.macro pr32_waitirq rd
    .insn r 0x0B, 0, 4, \rd, x0, x0
.endm
#endif /* __ASSEMBLER__ */

#define PICORV32_CUSTOM0_OPCODE 0x0B

/* getq rd, qs  (f7=0) : rd <- q[qs] */
#define PICORV32_ASM_GETQ(rd, qs) \
    ".insn r 0x0B, 0, 0, " rd ", " qs ", x0\n\t"

/* setq qd, rs  (f7=1) : q[qd] <- rs */
#define PICORV32_ASM_SETQ(qd, rs) \
    ".insn r 0x0B, 0, 1, " qd ", " rs ", x0\n\t"

/* retirq       (f7=2) : pc <- q0, interrupts re-enabled */
#define PICORV32_ASM_RETIRQ() \
    ".insn r 0x0B, 0, 2, x0, x0, x0\n\t"

/* maskirq rd, rs (f7=3) : rd <- old mask, mask <- rs */
#define PICORV32_ASM_MASKIRQ(rd, rs) \
    ".insn r 0x0B, 0, 3, " rd ", " rs ", x0\n\t"

/* waitirq rd   (f7=4) : rd <- pending mask, sleeps until nonzero */
#define PICORV32_ASM_WAITIRQ(rd) \
    ".insn r 0x0B, 0, 4, " rd ", x0, x0\n\t"

/* q-register indices used as the rs1/rd field vehicle (x0..x3 by name). */
#define PICORV32_Q0 "x0"
#define PICORV32_Q1 "x1"
#define PICORV32_Q2 "x2"
#define PICORV32_Q3 "x3"

/* SYS-10: MASKED_IRQ=0xffffff8f hardware-fixed (only CPU irq bits 4..6 are
 * wireable at all); "all IRQs masked at reset" additionally requires the
 * software mask register (set via maskirq) to start all-ones. crt0 does this
 * once before any C code runs. */
#define PICORV32_IRQ_MASK_ALL     0xFFFFFFFFu
#define PICORV32_IRQ_MASK_HW_FIXED 0xFFFFFF8Fu /* only bits 4..6 wireable */

/* getq q2 (return-address low word is NOT what q2 holds; q2/q3 are scratch
 * per dependencies.md "q2/q3 are scratch and not assumed zero" — provided
 * here only as named constants, not implying any reset value). */

#ifndef __ASSEMBLER__

static inline uint32_t picorv32_maskirq(uint32_t new_mask) {
    uint32_t old_mask;
    __asm__ volatile (
        PICORV32_ASM_MASKIRQ("%0", "%1")
        : "=r"(old_mask)
        : "r"(new_mask)
    );
    return old_mask;
}

static inline uint32_t picorv32_waitirq(void) {
    uint32_t pending;
    __asm__ volatile (
        PICORV32_ASM_WAITIRQ("%0")
        : "=r"(pending)
    );
    return pending;
}

static inline uint32_t picorv32_getq1(void) {
    uint32_t v;
    __asm__ volatile (
        PICORV32_ASM_GETQ("%0", PICORV32_Q1)
        : "=r"(v)
    );
    return v;
}

#endif /* __ASSEMBLER__ */

#endif /* OPENCHIP_SW_COMMON_IRQ_ASM_H */
