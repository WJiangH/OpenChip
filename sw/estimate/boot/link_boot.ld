/* Boot-ROM image linker script, footprint-estimate skeleton (issue #6).
 * Placement per docs/spec/soc_1.md §3.2: boot ROM window at 0x0000_0000,
 * 64 KB max (SOC1-07 PROGADDR_RESET = 0x0000_0000). The window size here is
 * the full 64 KB budget for build purposes only — the *recommended*
 * implemented ROM size (this estimate's deliverable) is in
 * sw/reports/firmware-footprint.md and is expected to be far smaller.
 *
 * The boot loader is RO code+rodata; it needs a small scratch stack, which
 * must live in RAM (firmware SRAM window), not ROM. It uses the top of the
 * 64 KB SRAM window per §3.2 — this is a footprint-estimate placeholder,
 * not a ruling on real boot-time stack placement (M3 firmware-engineer
 * decision).
 */
ENTRY(_start)

MEMORY
{
    ROM (rx)  : ORIGIN = 0x00000000, LENGTH = 64K
    SRAM (rw) : ORIGIN = 0x00010000, LENGTH = 64K
}

SECTIONS
{
    .text : { KEEP(*(.text.start)) *(.text .text.*) } > ROM
    .rodata : { *(.rodata .rodata.*) } > ROM

    /* boot loader has no writable globals in this skeleton; bss kept for
     * crt0's generic zero-loop and future real loader state. */
    .bss (NOLOAD) : {
        _bss_start = .;
        *(.bss .bss.* .sbss .sbss.* .scommon)
        *(COMMON)
        _bss_end = .;
    } > ROM

    _stack_top = ORIGIN(SRAM) + LENGTH(SRAM);
}
