/* sw/b1/link_b1.ld — B1 firmware linker script.
 * SYS-02/SYS-05: load=entry=0x10000000. SYS-06: linker places
 * executable/data/BSS below 0x10030000; 0x10030000..0x10040000 is the
 * 64 KiB downward stack (not modeled as a section — nothing is placed
 * there). SYS-06 fixed forwarding slot: 0x10000080.
 */
OUTPUT_ARCH(riscv)
ENTRY(_fw_reset)

MEMORY
{
    /* SRAM is 256 KiB (contract.json "sram", 0x10000000..0x10040000); the
     * usable code/data/BSS region is capped at 0x10030000, per SYS-06. */
    FWMEM (rwx) : ORIGIN = 0x10000000, LENGTH = 0x00030000
}

SECTIONS
{
    .text.entry 0x10000000 : {
        KEEP(*(.text.entry))
    } > FWMEM

    /* Fixed forwarding-slot address the ROM's IRQ trampoline jumps to. */
    .text.fw_irq_slot 0x10000080 : {
        KEEP(*(.text.fw_irq_slot))
    } > FWMEM

    .text : {
        *(.text .text.*)
    } > FWMEM

    .rodata : {
        *(.rodata .rodata.*)
    } > FWMEM

    .data : {
        *(.data .data.*)
    } > FWMEM

    . = ALIGN(4);
    __bss_start = .;
    .bss (NOLOAD) : {
        *(.bss .bss.* .sbss .sbss.*)
        *(COMMON)
        . = ALIGN(4);
    } > FWMEM
    __bss_end = .;

    .debug_line 0 : { *(.debug_line) }
    /DISCARD/ : { *(.comment) *(.riscv.attributes) *(.eh_frame) }
}

ASSERT(__bss_end <= 0x10030000, "b1: BSS end overruns the 64 KiB stack region (SYS-06)")
ASSERT((__bss_start % 4) == 0, "b1: BSS start must be 4-aligned (SYS-05)")
