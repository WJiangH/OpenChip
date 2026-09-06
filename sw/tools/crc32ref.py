#!/usr/bin/env python3
"""sw/tools/crc32ref.py — CRC-32/ISO-HDLC, independent Python mirror of
sw/common/crc32.c. Per SYS-05: "CRC is CRC-32/ISO-HDLC: reflected polynomial
0xEDB88320, init/xorout 0xffffffff over exactly byte_length payload bytes."

Deliberately bit-at-a-time (matches the C implementation's algorithm
structure exactly) rather than table-driven, so a mistake in the bit-level
polynomial application is not hidden by a precomputed table shared with any
other implementation.
"""


def crc32_iso_hdlc(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
    return crc ^ 0xFFFFFFFF
