/* Runtime firmware image linker script, footprint-estimate skeleton
 * (issue #6). Placement per docs/spec/soc_1.md §3.2: firmware SRAM window
 * at 0x0001_0000, 64 KB max window (SOC1-09 entry point after boot jump).
 *
 * The 64 KB here is the full window budget for build purposes only —
 * sw/reports/firmware-footprint.md's recommendation is the implemented
 * SRAM size, expected to be well under this window per the spec's own
 * area-cost note (§3.2). "STACKADDR ... set to the top of the implemented
 * SRAM once its size is pinned" (§3.2) — this script uses the top of the
 * full window as a stand-in until that pinning happens.
 */
ENTRY(_start)

MEMORY
{
    SRAM (rwx) : ORIGIN = 0x00010000, LENGTH = 64K
}

/* Stack budget: a policy choice, not derived — see
 * sw/reports/firmware-footprint.md for the rationale. Sized as its own
 * linker section so `size -A` reports it explicitly alongside
 * .text/.rodata/.data/.bss. */
STACK_SIZE = 2K;

SECTIONS
{
    .text : { KEEP(*(.text.start)) *(.text .text.*) } > SRAM
    .rodata : { *(.rodata .rodata.*) } > SRAM
    .data : { *(.data .data.*) } > SRAM
    .bss (NOLOAD) : {
        _bss_start = .;
        *(.bss .bss.* .sbss .sbss.* .scommon)
        *(COMMON)
        _bss_end = .;
    } > SRAM
    .stack (NOLOAD) : { . = ALIGN(16); _stack_bottom = .; . += STACK_SIZE; _stack_top = .; } > SRAM
}
