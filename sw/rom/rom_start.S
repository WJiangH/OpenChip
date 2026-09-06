/* sw/rom/rom_start.S — ROM reset entry (PROGADDR_RESET=0x00000000) and the
 * 0x100 IRQ trampoline (PROGADDR_IRQ=0x00000100), SYS-02/SYS-06.
 *
 * SYS-06: "ROM shall keep a 0x100 IRQ trampoline that forwards to
 * 0x10000080 only after BOOT_STAGE=2; before that interrupts stay masked."
 * ROM itself never unmasks any IRQ (all IRQs start masked per SYS-10 and ROM
 * never issues `maskirq` to change that), so the taken path below only ever
 * executes once firmware (which does its own IRQ setup) is already running
 * and something re-enters this fixed hardware vector address; the
 * BOOT_STAGE!=2 fallback exists purely so a defect elsewhere fails safe
 * (retirq, no state change) instead of corrupting execution.
 *
 * F-02: PicoRV32 IRQ entry hands us every interrupted GPR untouched (SYS-10
 * "preserve interrupted integer registers/stack"); nothing here may clobber
 * a GPR before that state is safely stashed. q2/q3 are hardware-provided
 * scratch for exactly this (dependencies.md, README "Custom Instructions for
 * IRQ Handling": "q2/q3 ... can be used as temporary storage when
 * saving/restoring register values"). So the BOOT_STAGE probe below stashes
 * t0/t1 (x5/x6) into q2/q3 via `setq` *before* using t0/t1 as scratch, and
 * either the forwarded firmware entry (sw/b1/b1_start.S `fw_irq_slot`,
 * 0x10000080) or the fallback path here restores them via `getq` before any
 * further GPR save runs / before `retirq`.
 */
#include "regmap.h"
#include "irq_asm.h"

.option norelax
.section .text.reset, "ax"
.align 2
.globl _rom_reset
_rom_reset:
    /* STACKADDR=0x10040000 is already the hardware reset value of x2 per
     * dependencies.md CPU parameter binding; set it again explicitly so ROM
     * does not depend on that parameter binding being preserved unchanged. */
    li sp, 0x10040000
    call rom_main
    /* rom_main() must not return: on success it jumps to firmware entry, on
     * failure it loops forever after committing RESULT_CODE (SYS-06 "It
     * shall never jump on failure"). Trap here defensively if it ever does. */
1:  j 1b
.size _rom_reset, . - _rom_reset

/* Placed at the fixed IRQ vector address 0x100 by link_rom.ld, which sets
 * the location counter explicitly before pulling in this section — not via
 * `.org`, so placement does not depend on how much code precedes it here. */
.section .text.irq_vector, "ax"
.align 2
.globl rom_irq_vector
rom_irq_vector:
    /* Stash the interrupted x5(t0)/x6(t1) into scratch q2/q3 *before* either
     * register is used below, so no GPR is modified before it is preserved
     * (F-02, SYS-10). "x2"/"x3" here are the q-index vehicle registers per
     * irq_asm.h, not general-purpose x2(sp)/x3(gp). */
    pr32_setq x2, t0
    pr32_setq x3, t1
    li t0, SYS_BOOT_STAGE_ADDR
    lw t0, 0(t0)
    li t1, 2
    bne t0, t1, 1f
    /* Forward to firmware's own reserved IRQ slot (SYS-06); firmware owns
     * the full save/dispatch/retirq sequence from here on. fw_irq_slot
     * (sw/b1/b1_start.S, 0x10000080) restores t0/t1 from q2/q3 before its
     * GPR save routine runs, so t0/t1 being scratch here is safe. */
    li t0, 0x10000080
    jr t0
1:
    /* Unreachable in correct operation (see file header). Still, restore
     * the interrupted t0/t1 before retirq so this fallback never corrupts
     * architectural state. */
    pr32_getq t0, x2
    pr32_getq t1, x3
    pr32_retirq
.size rom_irq_vector, . - rom_irq_vector
