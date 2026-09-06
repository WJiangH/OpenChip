/* sw/common/crt0.S — PicoRV32 custom IRQ ABI trampoline body (dependencies.md,
 * SYS-10, hw/ip/picorv32/README.md "Custom Instructions for IRQ Handling").
 *
 * This file supplies ONE shared routine, `picorv32_irq_common_entry`: the
 * full-register-save IRQ wrapper that both the ROM's own would-be handler
 * and the B1 firmware's real handler can reuse. The ROM never unmasks any
 * IRQ (SYS-06: "before that interrupts stay masked"), so with
 * `-ffunction-sections -Wl,--gc-sections` this routine is dropped from
 * rom.elf entirely when nothing references it; only b1.elf's b1_start.S
 * jumps here.
 *
 * PicoRV32 delivers an IRQ by jumping to PROGADDR_IRQ (0x100, wired here to
 * this trampoline via b1's 0x10000080 forwarding slot) with q0=return PC,
 * q1=pending-IRQ bitmask, and every ordinary GPR exactly as the interrupted
 * code left it (this is a hardware jump, not a `call`: nothing is saved by
 * hardware, not even ra). We therefore save every GPR except x0 (hardwired
 * zero) and x2/sp (implicitly restored by undoing our own `addi sp,sp,-N`)
 * before calling the C dispatcher, and restore them all before `retirq`.
 *
 * `default-nettype`-style discipline does not apply to software, but the
 * assembly-vs-C boundary rule here is the same spirit: nothing below this
 * comment may assume any C compiler register-allocation convention across
 * the interrupt boundary — that is exactly why we save architectural state
 * by hand instead of trusting the callee-saved half of the C ABI.
 */
#include "irq_asm.h"

.option norelax
.section .text.irq_common, "ax"
.align 2
.globl picorv32_irq_common_entry
picorv32_irq_common_entry:
    addi sp, sp, -128
    sw x1,  0(sp)
    sw x3,  4(sp)
    sw x4,  8(sp)
    sw x5,  12(sp)
    sw x6,  16(sp)
    sw x7,  20(sp)
    sw x8,  24(sp)
    sw x9,  28(sp)
    sw x10, 32(sp)
    sw x11, 36(sp)
    sw x12, 40(sp)
    sw x13, 44(sp)
    sw x14, 48(sp)
    sw x15, 52(sp)
    sw x16, 56(sp)
    sw x17, 60(sp)
    sw x18, 64(sp)
    sw x19, 68(sp)
    sw x20, 72(sp)
    sw x21, 76(sp)
    sw x22, 80(sp)
    sw x23, 84(sp)
    sw x24, 88(sp)
    sw x25, 92(sp)
    sw x26, 96(sp)
    sw x27, 100(sp)
    sw x28, 104(sp)
    sw x29, 108(sp)
    sw x30, 112(sp)
    sw x31, 116(sp)

    /* a0 = pending IRQ bitmask (q1), for the C dispatcher */
    pr32_getq a0, x1
    call b1_irq_dispatch

    lw x1,  0(sp)
    lw x3,  4(sp)
    lw x4,  8(sp)
    lw x5,  12(sp)
    lw x6,  16(sp)
    lw x7,  20(sp)
    lw x8,  24(sp)
    lw x9,  28(sp)
    lw x10, 32(sp)
    lw x11, 36(sp)
    lw x12, 40(sp)
    lw x13, 44(sp)
    lw x14, 48(sp)
    lw x15, 52(sp)
    lw x16, 56(sp)
    lw x17, 60(sp)
    lw x18, 64(sp)
    lw x19, 68(sp)
    lw x20, 72(sp)
    lw x21, 76(sp)
    lw x22, 80(sp)
    lw x23, 84(sp)
    lw x24, 88(sp)
    lw x25, 92(sp)
    lw x26, 96(sp)
    lw x27, 100(sp)
    lw x28, 104(sp)
    lw x29, 108(sp)
    lw x30, 112(sp)
    lw x31, 116(sp)
    addi sp, sp, 128

    pr32_retirq
.size picorv32_irq_common_entry, . - picorv32_irq_common_entry
