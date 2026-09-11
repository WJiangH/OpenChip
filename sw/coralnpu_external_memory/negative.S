/* CNEM-21/23/25. One isolated operation after startup installs mtvec.
 * Same fetch/load/store ELF for SLVERR and DECERR; response choice is DV-owned.
 */
.section .text.main,"ax",@progbits
.balign 16
.global main
.type main,@function
main:
#if PROFILE == 4
    li t0, 0x21000000
#else
    li t0, 0x200ff000
#endif
    li t1, 0x12345678
.global fault_instruction
.type fault_instruction,@function
fault_instruction:
#if PROFILE == 1
    jalr zero, 0(t0)
#elif PROFILE == 3
    sw t1, 0(t0)
#else
    lw t1, 0(t0)
#endif
.size fault_instruction, .-fault_instruction
    /* Unexpected successful operation cannot create the expected trap record. */
    li a0, 3
    ret
.size main, .-main
