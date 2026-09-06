#!/usr/bin/env python3
"""Generate hw/rtl/rom/rom_data.svh from a firmware image.

Spec: docs/spec/llm-soc-v1/system.md §2 (0x00000000, 65536 bytes, immutable
boot ROM) and SYS-05/SYS-06 (ROM boot-code content). ROM *content* is
firmware territory (SW-B1, docs/spec/llm-soc-v1/downstream.md); this script
is only the delivery mechanism that turns a firmware image into a
Yosys-safe SystemVerilog `` `include `` file, because house rules
(AGENTS.md RTL conventions) forbid `initial` blocks / `$readmemh` in
synthesizable RTL. rom.sv consumes the emitted rom_words array with a plain
`` `include "rom_data.svh" ``.

Usage:
    gen_rom.py                              write an all-zero placeholder
    gen_rom.py <image.hex>                  one 32-bit little-endian hex
                                             word per line (0x-prefix or
                                             bare hex digits, blank lines
                                             and //, # comments ignored)
    gen_rom.py <image.bin>                  raw bytes, little-endian,
                                             packed 4 bytes per 32-bit word
    gen_rom.py <image> -o <out.svh>         override output path

The image must fit within ROM_BYTES (65536); it is zero-padded to fill the
remainder of the ROM. ROM_BYTES is frozen by the spec address table and is
never changed by this script, even if a placeholder image needs to shrink
for tool-time reasons (see hw/rtl/rom/README.md).
"""
import argparse
import pathlib
import struct
import sys

ROM_BYTES = 65536  # docs/spec/llm-soc-v1/system.md §2: base 0x00000000, size 65536
WORDS = ROM_BYTES // 4


def words_from_bin(data: bytes):
    if len(data) > ROM_BYTES:
        raise ValueError(f"image is {len(data)} bytes, exceeds ROM_BYTES={ROM_BYTES}")
    data = data + b"\x00" * (ROM_BYTES - len(data))
    return [struct.unpack_from("<I", data, i)[0] for i in range(0, ROM_BYTES, 4)]


def words_from_hex(text: str):
    words = []
    for line in text.splitlines():
        line = line.split("//", 1)[0].split("#", 1)[0].strip()
        if not line:
            continue
        words.append(int(line, 16) & 0xFFFFFFFF)
    if len(words) > WORDS:
        raise ValueError(f"image has {len(words)} words, exceeds WORDS={WORDS}")
    words += [0] * (WORDS - len(words))
    return words


def emit(words, out_path: pathlib.Path, source_label: str, placeholder: bool):
    assert len(words) == WORDS
    lines = [
        "// rom_data.svh -- GENERATED FILE, do not hand-edit.",
        f"// Produced by hw/rtl/rom/gen_rom.py from: {source_label}",
    ]
    if placeholder:
        lines += [
            "// PLACEHOLDER CONTENT: all-zero. This is NOT bootable firmware.",
            "// Real ROM content is firmware territory (SW-B1,",
            "// docs/spec/llm-soc-v1/downstream.md) and is produced by re-running",
            "// gen_rom.py over the real boot image once it exists.",
        ]
    lines.append(
        f"// {WORDS} words x 32 bits = {ROM_BYTES} bytes "
        "(docs/spec/llm-soc-v1/system.md §2 address table)."
    )
    # Yosys's read_verilog frontend rejects an unpacked-array localparam
    # initialized with a SystemVerilog '{...} array literal (tested against
    # oss-cad-suite Yosys 0.67: "syntax error, unexpected '['"). A wire
    # array driven by one continuous assign per word is accepted by both
    # Verilator and Yosys and elaborates to the same ROM content.
    lines.append(f"wire [31:0] rom_words [0:{WORDS - 1}];")
    for i, w in enumerate(words):
        lines.append(f"assign rom_words[{i}] = 32'h{w:08x};")
    out_path.write_text("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?", help="firmware image (.hex or .bin); omit for all-zero placeholder")
    ap.add_argument("-o", "--out", default=str(pathlib.Path(__file__).parent / "rom_data.svh"))
    args = ap.parse_args(argv)

    out_path = pathlib.Path(args.out)

    if args.image is None:
        emit([0] * WORDS, out_path, "none (placeholder)", placeholder=True)
        print(f"wrote placeholder {out_path} ({ROM_BYTES} bytes, all-zero)")
        return 0

    img_path = pathlib.Path(args.image)
    raw = img_path.read_bytes()
    if img_path.suffix.lower() == ".hex":
        words = words_from_hex(raw.decode())
    else:
        words = words_from_bin(raw)
    is_placeholder = all(w == 0 for w in words)
    emit(words, out_path, str(img_path), placeholder=is_placeholder)
    print(f"wrote {out_path} from {img_path} ({ROM_BYTES} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
