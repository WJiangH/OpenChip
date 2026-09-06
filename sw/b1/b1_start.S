/* sw/b1/b1_start.S — B1 firmware entry (SYS-05 load=entry=0x10000000) and
 * the reserved IRQ forwarding slot at 0x10000080.
 *
 * SYS-06: "ROM shall keep a 0x100 IRQ trampoline that forwards to
 * 0x10000080 only after BOOT_STAGE=2... Firmware entry contains a branch
 * over the reserved IRQ vector slot." — so byte 0 of the loaded image must
 * be a jump that skips forward past 0x10000080, and 0x10000080 itself must
 * hold a jump into this firmware's real IRQ handling (the shared
 * full-register-save trampoline body in sw/common/crt0.S).
 *
 * ROM already zeroed BSS and copied .data as part of the flat image before
 * jumping here (SYS-05), and SP already reads 0x10040000 (STACKADDR
 * hardware reset value, reaffirmed by both ROM's own crt0 and here) — so
 * this file's only job is: skip the reserved slot, mask every IRQ source in
 * software (SYS-10 "initially mask every source"), and call b1_main().
 */
#include "irq_asm.h"

.option norelax
.section .text.entry, "ax"
.align 2
.globl _fw_reset
_fw_reset:
    j fw_init /* skip over the reserved IRQ vector slot at 0x10000080 */
.size _fw_reset, . - _fw_reset

/* Placed at 0x10000080 by link_b1.ld (explicit output-section address, same
 * reasoning as sw/rom/link_rom.ld's .text.irq_vector). */
.section .text.fw_irq_slot, "ax"
.align 2
.globl fw_irq_slot
fw_irq_slot:
    j picorv32_irq_common_entry
.size fw_irq_slot, . - fw_irq_slot

.section .text.fw_init, "ax"
.align 2
.globl fw_init
fw_init:
    li sp, 0x10040000
    /* SYS-10: "initially mask every source" — software IRQ mask starts
     * all-ones; b1_main() unmasks bits 4/5 only for its IRQ-driven command,
     * and only for the duration of that command. */
    li a0, 0xFFFFFFFF
    pr32_maskirq a1, a0
    call b1_main
1:  j 1b
.size fw_init, . - fw_init
