OUTPUT_ARCH(riscv)
ENTRY(_start)
PHDRS { code PT_LOAD FLAGS(5); metadata PT_LOAD FLAGS(6); }
SECTIONS {
  . = 0x20000000;
  .text : { KEEP(*(.text.start)) *(.text.kernel) *(.text.trap) *(.text*) } :code
  .rodata : { *(.rodata*) *(.srodata*) } :code
  ASSERT(. <= 0x20010000, "external executable window overflow")
  . = 0x20020000;
  .data : { *(.data*) *(.sdata*) } :metadata
  .bss (NOLOAD) : { *(.bss.ret) *(.bss*) *(.sbss*) *(COMMON) } :metadata
  ASSERT(. <= 0x20030000, "external metadata window overflow")
  ASSERT(_ret % 4 == 0, "return slot alignment")
  ASSERT((_start / 16) != (rvv_gemv_int8 / 16), "entry/kernel fetch lines overlap")
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
