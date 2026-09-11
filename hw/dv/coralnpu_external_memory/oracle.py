"""Independent text-only oracle; CN-EXTMEM-01 v0.4 §§3,5,6 and workload equations.

Independent DV arithmetic model. No DUT, software kernel, upstream tests or simulator
imports. This oracle establishes no hardware result. See workloads/coralnpu_external_memory/README.md.
"""

import struct

SHAPES = ((64, 64), (5, 33))
MASK32 = (1 << 32) - 1


def inputs(case, salt):
    """Workload equations: signed INT8 A, row-major B for allowed inputs."""
    if case not in (0, 1) or salt not in (0, 17):
        raise ValueError("unsupported case or salt")
    k_size, n_size = SHAPES[case]
    a = [((13 * k + 7 * case + salt) % 31) - 15 for k in range(k_size)]
    b = [[((5 * k + 3 * n + 11 * case + 2 * salt) % 29) - 14
          for n in range(n_size)] for k in range(k_size)]
    return a, b


def gemv(a, b):
    """Workload v0.3 C equation: exact signed INT8 products and INT32 sums."""
    if not a or len(a) != len(b) or not b[0]:
        raise ValueError("empty or inconsistent GEMV dimensions")
    width = len(b[0])
    if any(len(row) != width for row in b):
        raise ValueError("ragged matrix")
    if any(type(x) is not int or not -128 <= x <= 127
           for x in list(a) + [x for row in b for x in row]):
        raise ValueError("operands must be signed INT8 integers")
    result = [sum(a[k] * b[k][n] for k in range(len(a))) for n in range(width)]
    if any(not -(1 << 31) <= x < (1 << 31) for x in result):
        raise ValueError("outside this exact INT32 oracle domain")
    return result


def signature(c):
    """Workload v0.3 signature: uint32 conversion and weighted modulo sum."""
    return sum((x & MASK32) * (n + 1) for n, x in enumerate(c)) & MASK32


def int32_bytes(c):
    """Contract §3: little-endian signed INT32 output layout."""
    return b''.join(struct.pack('<i', x) for x in c)


def expected_probe():
    """Contract CNEM-17: independent full 32-byte probe expectation."""
    out = bytearray([0xa5] * 32)
    out[1] = 0x5a
    out[6:8] = bytes([0x34, 0x12])
    out[12:16] = bytes([0xef, 0xcd, 0xab, 0x89])
    return bytes(out)


def read_lanes(memory_line, address, size):
    """Contract CNEM-15: successful read bytes in selected 128-bit lanes."""
    start, count = _access(memory_line, address, size)
    out = bytearray(16)
    out[start:start + count] = memory_line[start:start + count]
    return bytes(out)


def write_lanes(memory_line, address, size, data, strobe):
    """CNEM-15: validate legal WSTRB then preserve every unstroked byte.

    Checks local 16-byte lane semantics only; absolute mapping, transaction
    lifetime, response ordering and error injection belong to future checkers.
    """
    start, count = _access(memory_line, address, size)
    legal = ((1 << count) - 1) << start
    if len(data) != 16 or type(strobe) is not int or strobe < 0 or strobe > 0xffff:
        raise ValueError("invalid write payload")
    if strobe & ~legal:
        raise ValueError("strobe outside transfer")
    out = bytearray(memory_line)
    for lane in range(16):
        if strobe & (1 << lane):
            out[lane] = data[lane]
    return bytes(out)


def _access(memory_line, address, size):
    """CNEM-12/15: supported sizes, natural alignment and one 16-byte line."""
    if len(memory_line) != 16 or size not in (0, 1, 2, 4):
        raise ValueError("invalid line or unsupported size")
    count = 1 << size
    if type(address) is not int or not 0 <= address <= MASK32 or address % count:
        raise ValueError("invalid or unaligned address")
    return address & 15, count
