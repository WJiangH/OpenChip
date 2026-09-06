#!/usr/bin/env python3
"""sw/tools/mkimage.py — B1 image and fixture builder.

Builds, from sw/b1/b1.elf (produced by `make -C sw/b1`):
  1. the SYS-05 boot image (64-byte header + firmware flat payload) at its
     0x80000000 layout, in a "good" variant and two negative variants
     (bad magic, bad CRC) that ROM must reject per SYS-06;
  2. the NPU fixture bytes (X/W per command, nonzero Y sentinel) at their
     scratch addresses, mirroring the exact same values firmware itself
     writes at runtime per NPU-08 (sw/tools/fixtures.py is the single
     shared source for both);
  3. the independent-expected INT32 Y words at 0x80700000, computed by a
     plain-integer Python reference of NPU-01 (sw/tools/fixtures.py
     gemv_group_i8_by_group()) — this is the SW-owner's independent
     reference; it is not read by, and never influences, DUT execution
     (AXI-10).

Output: b1_extmem.bin + b1_extmem.json (sparse region list: name, target
address, file offset, length, sha256) that a testbench can preload into the
16 MiB external memory model (contract.json "extmem"), plus
b1_extmem_bad_magic.{bin,json} and b1_extmem_bad_crc.{bin,json}.

--selftest runs three offline checks (CRC test vector, header round-trip,
reference-vs-naive-loop cross-check) with no ELF/toolchain dependency.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures as fx
from crc32ref import crc32_iso_hdlc

# ---- SYS-05 boot header layout (see sw/rom/boot_header.h; hand-transcribed
# from system.md prose, not contract.json material — mirrored here so ROM
# and this builder cannot silently drift). ----
BOOT_HEADER_STRUCT = "<16I"  # magic,abi,byte_length,load,entry,crc32,bss_start,bss_length,reserved[8]
BOOT_HEADER_BYTES = struct.calcsize(BOOT_HEADER_STRUCT)
assert BOOT_HEADER_BYTES == 64

BOOT_HEADER_MAGIC = 0x4C4C4D31
BOOT_HEADER_ABI = 1
BOOT_FW_LOAD = 0x10000000
BOOT_FW_ENTRY = 0x10000000

REGION_BOOT_IMAGE_BASE = 0x80000000
REGION_EXTMEM_BASE = 0x80000000
REGION_EXTMEM_SIZE = 16 * 1024 * 1024


def find_toolchain_prefix():
    for prefix in ("riscv-none-elf-", ""):
        if shutil.which(prefix + "nm"):
            return prefix
    return None


def read_elf_symbols(elf_path, names):
    prefix = find_toolchain_prefix()
    if prefix is None:
        print("mkimage: riscv-none-elf-nm not found on PATH "
              "(run via `make -C sw`, which puts the pinned toolchain on PATH)",
              file=sys.stderr)
        sys.exit(1)
    out = subprocess.run([prefix + "nm", elf_path], capture_output=True, text=True, check=True).stdout
    result = {}
    for line in out.splitlines():
        m = re.match(r"^([0-9a-fA-F]+)\s+\S\s+(\S+)$", line.strip())
        if m and m.group(2) in names:
            result[m.group(2)] = int(m.group(1), 16)
    missing = set(names) - set(result)
    if missing:
        print(f"mkimage: symbols not found in {elf_path}: {missing}", file=sys.stderr)
        sys.exit(1)
    return result


def objcopy_flat_binary(elf_path, out_bin_path):
    prefix = find_toolchain_prefix()
    if prefix is None:
        print("mkimage: riscv-none-elf-objcopy not found on PATH", file=sys.stderr)
        sys.exit(1)
    subprocess.run([prefix + "objcopy", "-O", "binary", elf_path, out_bin_path], check=True)


def build_boot_header(byte_length, crc32, bss_start, bss_length):
    return struct.pack(
        BOOT_HEADER_STRUCT,
        BOOT_HEADER_MAGIC, BOOT_HEADER_ABI, byte_length, BOOT_FW_LOAD, BOOT_FW_ENTRY,
        crc32, bss_start, bss_length,
        0, 0, 0, 0, 0, 0, 0, 0,
    )


def build_good_boot_image(b1_elf):
    # sw/b1/Makefile already produces b1.bin (flat objcopy of b1.elf) as a
    # build output; reuse it instead of re-invoking objcopy into a stray
    # extra file. Falls back to a throwaway temp file if b1.bin is missing
    # (e.g. mkimage.py invoked directly against a hand-built ELF).
    sibling_bin = os.path.splitext(b1_elf)[0] + ".bin"
    if os.path.exists(sibling_bin):
        with open(sibling_bin, "rb") as f:
            payload = f.read()
    else:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".bin") as tmp:
            objcopy_flat_binary(b1_elf, tmp.name)
            tmp.seek(0)
            payload = tmp.read()
    byte_length = len(payload)
    if not (1 <= byte_length <= 0x30000):
        print(f"mkimage: firmware payload {byte_length} bytes out of SYS-05 [1,0x30000] range",
              file=sys.stderr)
        sys.exit(1)

    syms = read_elf_symbols(b1_elf, {"__bss_start", "__bss_end"})
    bss_start = syms["__bss_start"]
    bss_end = syms["__bss_end"]
    bss_length = bss_end - bss_start

    crc = crc32_iso_hdlc(payload)
    header = build_boot_header(byte_length, crc, bss_start, bss_length)
    return header + payload, header, payload


def region_entry(name, addr, data, file_offset):
    return {
        "name": name,
        "addr": addr,
        "file_offset": file_offset,
        "length": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def write_extmem(out_dir, tag, regions_data):
    """regions_data: list of (name, addr, bytes). Writes <tag>.bin (sparse
    concatenation) + <tag>.json (region directory)."""
    bin_path = os.path.join(out_dir, f"{tag}.bin")
    json_path = os.path.join(out_dir, f"{tag}.json")

    blob = bytearray()
    regions = []
    for name, addr, data in regions_data:
        offset = len(blob)
        blob += data
        regions.append(region_entry(name, addr, data, offset))

    with open(bin_path, "wb") as f:
        f.write(blob)

    manifest = {
        "extmem_base": REGION_EXTMEM_BASE,
        "extmem_size": REGION_EXTMEM_SIZE,
        "bin_file": os.path.basename(bin_path),
        "bin_sha256": hashlib.sha256(bytes(blob)).hexdigest(),
        "regions": regions,
    }
    with open(json_path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    return bin_path, json_path, bytes(blob)


def build_good(b1_elf, out_dir):
    image, header, payload = build_good_boot_image(b1_elf)

    regions = [("boot_image", REGION_BOOT_IMAGE_BASE, image)]
    for cmd in fx.ALL_COMMANDS:
        x_bytes, w_bytes = fx.command_bytes(cmd)
        regions.append((f"{cmd['name']}_x", cmd["x_base"], x_bytes))
        regions.append((f"{cmd['name']}_w", cmd["w_base"], w_bytes))
        wc = fx.command_y_word_count(cmd)
        regions.append((f"{cmd['name']}_y_sentinel", cmd["y_base"], fx.y_sentinel_bytes(wc)))

    expected_blob = fx.build_expected_blob(fx.ALL_COMMANDS)
    regions.append(("expected", fx.REGION_EXPECTED_BASE, expected_blob))

    bin_path, json_path, _ = write_extmem(out_dir, "b1_extmem", regions)
    print(f"mkimage: wrote {bin_path}, {json_path} "
          f"(boot image {len(image)} bytes = header {len(header)} + payload {len(payload)})")
    return bin_path, json_path


def build_negative_variants(b1_elf, out_dir):
    _, good_header, payload = build_good_boot_image(b1_elf)
    fields = list(struct.unpack(BOOT_HEADER_STRUCT, good_header))
    # magic, abi, byte_length, load, entry, crc32, bss_start, bss_length, reserved[8]

    # ---- bad magic: SYS-06 RESULT_CODE 0xB001 ----
    bad_magic_fields = list(fields)
    bad_magic_fields[0] = fields[0] ^ 0xFFFFFFFF  # corrupt magic
    bad_magic_header = struct.pack(BOOT_HEADER_STRUCT, *bad_magic_fields)
    bad_magic_image = bad_magic_header + payload
    write_extmem(out_dir, "b1_extmem_bad_magic",
                 [("boot_image", REGION_BOOT_IMAGE_BASE, bad_magic_image)])

    # ---- bad CRC: SYS-06 RESULT_CODE 0xB002 ----
    bad_crc_fields = list(fields)
    bad_crc_fields[5] = fields[5] ^ 0xFFFFFFFF  # corrupt crc32 field only
    bad_crc_header = struct.pack(BOOT_HEADER_STRUCT, *bad_crc_fields)
    bad_crc_image = bad_crc_header + payload
    write_extmem(out_dir, "b1_extmem_bad_crc",
                 [("boot_image", REGION_BOOT_IMAGE_BASE, bad_crc_image)])

    print(f"mkimage: wrote {out_dir}/b1_extmem_bad_magic.{{bin,json}}, "
          f"{out_dir}/b1_extmem_bad_crc.{{bin,json}} (negative boot variants, SYS-06)")


# ---------------------------------------------------------------------------
# --selftest: CRC test vector, header round-trip, reference vs naive loop.
# ---------------------------------------------------------------------------
def selftest():
    ok = True

    # 1. CRC-32/ISO-HDLC standard check value: CRC32("123456789") == 0xCBF43926.
    v = crc32_iso_hdlc(b"123456789")
    expect = 0xCBF43926
    print(f"selftest: crc32('123456789') = 0x{v:08x} (expect 0x{expect:08x}) "
          f"{'OK' if v == expect else 'FAIL'}")
    ok &= (v == expect)

    # 2. Header round-trip: build -> pack -> unpack -> fields match.
    header = build_boot_header(0x1234, 0xDEADBEEF, 0x10000000 + 0x2000, 0x100)
    fields = struct.unpack(BOOT_HEADER_STRUCT, header)
    expect_fields = (BOOT_HEADER_MAGIC, BOOT_HEADER_ABI, 0x1234, BOOT_FW_LOAD, BOOT_FW_ENTRY,
                     0xDEADBEEF, 0x10000000 + 0x2000, 0x100, 0, 0, 0, 0, 0, 0, 0, 0)
    round_trip_ok = (fields == expect_fields) and (len(header) == 64)
    print(f"selftest: boot header round-trip {'OK' if round_trip_ok else 'FAIL'} "
          f"(got {fields})")
    ok &= round_trip_ok

    # 3. Reference vs. independent naive-loop reference, both fixture commands.
    for cmd in fx.ALL_COMMANDS:
        y1 = fx.gemv_group_i8_by_group(cmd["x"], cmd["w_rows"], cmd["k"], cmd["n"], cmd["group"])
        y2 = fx.gemv_group_i8_by_k(cmd["x"], cmd["w_rows"], cmd["k"], cmd["n"], cmd["group"])
        match = (y1 == y2)
        print(f"selftest: {cmd['name']} group-outer vs k-outer reference "
              f"{'OK' if match else 'FAIL'} ({y1})")
        ok &= match

    # 3b. A hand-computed tiny example, independent of both loop structures
    # above: K=4,G=4,N=1 (single full group, no tail) with known-by-hand sum.
    x = [1, 2, 3, 4]
    w_rows = [[10, 20, 30, 40]]
    expect_sum = 1 * 10 + 2 * 20 + 3 * 30 + 4 * 40  # = 300
    y = fx.gemv_group_i8_by_group(x, w_rows, 4, 1, 4)
    hand_ok = (y == [[expect_sum]])
    print(f"selftest: hand-computed K=4,G=4,N=1 case {'OK' if hand_ok else 'FAIL'} "
          f"(got {y}, expect [[{expect_sum}]])")
    ok &= hand_ok

    print("selftest: " + ("ALL OK" if ok else "FAILURES PRESENT"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    default_elf = os.path.normpath(os.path.join(here, "..", "b1", "b1.elf"))
    default_out = os.path.normpath(os.path.join(here, ".."))
    ap.add_argument("--b1-elf", default=default_elf)
    ap.add_argument("--out-dir", default=default_out)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())

    if not os.path.exists(args.b1_elf):
        print(f"mkimage: {args.b1_elf} not found — build it first (`make -C sw/b1`)",
              file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)
    build_good(args.b1_elf, args.out_dir)
    build_negative_variants(args.b1_elf, args.out_dir)


if __name__ == "__main__":
    main()
