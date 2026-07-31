/* Minimal rv32imc startup, footprint-estimate skeleton only (issue #6).
 * Real crt0.S (with the actual picorv32_wb IRQ entry/exit sequence, TBD at
 * RTL intake per Q-SOC1-06) lands in sw/ during M3.
 *
 * ABI: linker provides _stack_top, _bss_start, _bss_end, and C `main()`.
 */
    .section .text.start
    .global _start
_start:
    la   sp, _stack_top
    la   t0, _bss_start
    la   t1, _bss_end
1:
    bge  t0, t1, 2f
    sw   zero, 0(t0)
    addi t0, t0, 4
    j    1b
2:
    call main
3:
    j    3b
