/* sw/rom/link_rom.ld — 64 KiB boot ROM linker script.
 * SYS-02: reset vector 0x00000000. SYS-06: 0x100 IRQ trampoline (forwarded
 * only after BOOT_STAGE=2). ROM region: 0x00000000..0x00010000 (contract.json
 * address_regions "rom").
 */
OUTPUT_ARCH(riscv)
ENTRY(_rom_reset)

MEMORY
{
    ROM (rx) : ORIGIN = 0x00000000, LENGTH = 64K
}

SECTIONS
{
    . = 0x00000000;
    .text.reset : {
        /* KEEP: nothing calls _rom_reset by symbol reference (it is reached
         * only via PROGADDR_RESET=0 hardware fetch) and nothing calls
         * rom_irq_vector below by reference either (reached only via
         * PROGADDR_IRQ=0x100 hardware fetch) — --gc-sections would otherwise
         * discard both as apparently-dead code. */
        KEEP(*(.text.reset))
    } > ROM

    /* Fixed hardware IRQ vector address (PROGADDR_IRQ). Address is given
     * directly on the output section (not via a standalone "." bump):
     * with MEMORY regions, each region tracks its own placement cursor and
     * a bare "." assignment between two ">ROM" sections does not move it. */
    .text.irq_vector 0x00000100 : {
        KEEP(*(.text.irq_vector))
    } > ROM

    .text : {
        *(.text .text.*)
    } > ROM

    .rodata : {
        *(.rodata .rodata.*)
    } > ROM

    /* ROM keeps no mutable state across calls: everything it needs lives on
     * the stack. No .data/.bss section is defined for the ROM image. */

    .debug_line 0 : { *(.debug_line) }
    /DISCARD/ : { *(.comment) *(.riscv.attributes) *(.eh_frame) }
}

ASSERT(SIZEOF(.text.reset) <= 0x100, "rom: .text.reset overruns the 0x100 IRQ vector slot")
ASSERT(. <= 0x00010000, "rom: image exceeds 64 KiB ROM region")
