# rom/ — 64 KiB boot ROM AXI4 target

`rom.sv` is the delivery mechanism only: an AXI4 target that serves reads
from a compile-time constant array and rejects any write with SLVERR (see
file header, citing system.md SYS-04). ROM *content* is firmware territory
(SW-B1, docs/spec/llm-soc-v1/downstream.md).

`rom_data.svh` is a generated file (never hand-edit it); regenerate it with
`gen_rom.py <image.hex|image.bin>`. The copy shipped in this directory is a
**placeholder: all 65536 bytes are zero**, and it is not bootable firmware —
see the header comment inside `rom_data.svh` itself for the same note.
Running `gen_rom.py` with no arguments reproduces this exact placeholder.
