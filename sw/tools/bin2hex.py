#!/usr/bin/env python3
"""bin2hex.py — flat binary -> $readmemh-style hex, one little-endian 32-bit
word per line (8 lowercase hex digits, no "0x" prefix, no addresses).

Usage: bin2hex.py IN.bin OUT.hex [TOTAL_BYTES]

If TOTAL_BYTES is given, the output is padded with zero words up to that
many bytes (rounded up to a whole word) — used so rom.hex/b1.hex cover the
full addressed region for a $readmemh load, even though the flat binary
itself only contains the used prefix.
"""
import sys


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    in_path, out_path = sys.argv[1], sys.argv[2]
    total_bytes = int(sys.argv[3], 0) if len(sys.argv) > 3 else None

    with open(in_path, "rb") as f:
        data = f.read()

    if total_bytes is not None:
        if len(data) > total_bytes:
            print(f"bin2hex: input {len(data)} bytes exceeds requested total {total_bytes}",
                  file=sys.stderr)
            sys.exit(1)
        data = data + b"\x00" * (total_bytes - len(data))

    # Pad to a whole word for the final partial word, if any.
    if len(data) % 4 != 0:
        data = data + b"\x00" * (4 - (len(data) % 4))

    lines = []
    for i in range(0, len(data), 4):
        word = int.from_bytes(data[i:i + 4], "little")
        lines.append(f"{word:08x}")

    with open(out_path, "w") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))

    print(f"bin2hex: wrote {out_path} ({len(lines)} words from {len(data)} bytes)")


if __name__ == "__main__":
    main()
