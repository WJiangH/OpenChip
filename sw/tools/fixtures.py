#!/usr/bin/env python3
"""sw/tools/fixtures.py — B1 NPU test-vector fixtures and independent
grouped-dot integer reference (npu.md NPU-01/NPU-02/NPU-08).

Single source of truth for:
  - the two GEMV_GROUP_I8 command descriptors B1 exercises (one meant to be
    driven by CSR polling, one by IRQ), each with distinct nonzero signed
    X/W bytes, INT8 extrema, and a K not evenly divisible by G;
  - the plain-integer NPU-01 reference used to compute the "independent
    expected" Y words CPU firmware compares its actual NPU output against
    (AXI-10: the host never computes DUT results at runtime — this
    computation happens on the host, at image-build time, in mkimage.py).

Every byte address below is scratch-relative and derived from
REGION_SCRATCH_BASE (contract.json address_regions "scratch",
0x80600000..0x80700000, NPU R/W): NPU-02 requires X/Y wholly in scratch and
requires W wholly in "model or scratch" — both commands here keep W in
scratch too, for a self-contained B1 fixture set with no model-blob
dependency (B1 does not use the LLM-06 model blob at all).
"""
import struct

from crc32ref import crc32_iso_hdlc

REGION_SCRATCH_BASE = 0x80600000
REGION_EXPECTED_BASE = 0x80700000

Y_SENTINEL_WORD = 0x5A5A5A5A  # nonzero, must never appear in a real result

# ---- B1 independent-expected blob format (0x80700000, CPU-only region) ----
# workload.md LLM-11: "B1 expected records use a separate boot-selected
# fixture manifest and exact group results, never masquerade as model tensor
# records" — B1 is explicitly NOT the LLM-11 kind1..7 record format (that is
# an L1-only artifact this deliverable does not build). This is B1's own,
# much simpler, from-scratch format: a 32-byte header, `cmd_count` 16-byte
# directory records (tag/word_count/byte_offset), then raw little-endian
# INT32 Y words back-to-back per record in directory order.
EXPECTED_MAGIC = 0x42314558  # arbitrary, B1-local; not an LLM-11/SYS-05 value
EXPECTED_ABI = 1
EXPECTED_HEADER_STRUCT = "<IIIIIIII"  # magic,abi,cmd_count,blob_bytes,crc32,reserved0,reserved1,reserved2
EXPECTED_HEADER_BYTES = struct.calcsize(EXPECTED_HEADER_STRUCT)
EXPECTED_RECORD_STRUCT = "<IIII"  # tag,word_count,byte_offset,reserved0
EXPECTED_RECORD_BYTES = struct.calcsize(EXPECTED_RECORD_STRUCT)


def _row_stride_padded(row_valid, w_stride):
    """One W row: `row_valid` real INT8 values + deterministic nonzero
    padding out to w_stride bytes. NPU-02: "No assumption that W padding
    contains zero is allowed" — padding bytes are chosen nonzero on purpose
    so a hardware/reference bug that accidentally includes padding in the
    dot product is caught instead of silently passing.
    """
    pad_bytes = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20][: w_stride - len(row_valid)]
    assert len(pad_bytes) == w_stride - len(row_valid)
    return list(row_valid) + pad_bytes


def _s8(v):
    assert -128 <= v <= 127, v
    return v & 0xFF


CMD_A = {
    "name": "cmd_a_poll",
    "tag": 0xA5A50001,
    "k": 10,
    "n": 3,
    "group": 4,
    "w_stride": 16,
    "x_base": REGION_SCRATCH_BASE + 0x000,
    "w_base": REGION_SCRATCH_BASE + 0x010,
    "y_base": REGION_SCRATCH_BASE + 0x040,
    # 10 signed INT8 values, includes +127/-128 extrema (idx 0,1); every
    # element nonzero.
    "x": [127, -128, 5, -5, 3, 64, -64, 1, -1, 100],
    "w_rows": [
        _row_stride_padded([-128, 127, 3, -3, 9, -9, 2, -2, 4, -4], 16),
        _row_stride_padded([10, -10, 20, -20, 30, -30, 40, -40, 50, -50], 16),
        _row_stride_padded([127, -128, -128, 127, -7, 1, -1, 64, -64, 99], 16),
    ],
}

CMD_B = {
    "name": "cmd_b_irq",
    "tag": 0xA5A50002,
    "k": 13,
    "n": 2,
    "group": 8,
    "w_stride": 16,
    "x_base": REGION_SCRATCH_BASE + 0x100,
    "w_base": REGION_SCRATCH_BASE + 0x120,
    "y_base": REGION_SCRATCH_BASE + 0x150,
    # 13 signed INT8 values, includes +127/-128 extrema twice (idx 0/1, 6/7).
    "x": [127, -128, 3, -3, 7, -7, 127, -128, 11, -11, 13, -13, 50],
    "w_rows": [
        _row_stride_padded([-128, 127, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6], 16),
        _row_stride_padded([50, -50, 60, -60, 70, -70, 80, -80, 90, -90, 100, -100, 110], 16),
    ],
}

ALL_COMMANDS = [CMD_A, CMD_B]


def group_count(k, g):
    return (k + g - 1) // g


def gemv_group_i8_by_group(x, w_rows, k, n, g):
    """NPU-01 reference, group-outer / k-inner loop order.

    Y[n,g] = sum(X[k] * W[n,k]) for k in [g*G, min(K,(g+1)*G) - 1].
    Products are exact signed INT16, accumulation is signed INT32 (Python
    ints are unbounded but every legal B1 shape here fits comfortably inside
    INT32 per NPU-01's own bound of 4096*16384).
    """
    ng = group_count(k, g)
    y = [[0] * ng for _ in range(n)]
    for row in range(n):
        w = w_rows[row]
        for grp in range(ng):
            k0 = grp * g
            k1 = min(k, (grp + 1) * g)
            acc = 0
            for kk in range(k0, k1):
                acc += x[kk] * w[kk]
            y[row][grp] = acc
    return y


def gemv_group_i8_by_k(x, w_rows, k, n, g):
    """Independent second reference, k-outer / group-lookup loop order —
    used only by mkimage.py --selftest to cross-check
    gemv_group_i8_by_group() with a structurally different reduction order.
    Mathematically each individual product/sum is identical (integer
    arithmetic is associative/order-independent here, unlike the FP32 rules
    in workload.md which do not apply to this INT32 opcode at all).
    """
    ng = group_count(k, g)
    y = [[0] * ng for _ in range(n)]
    for row in range(n):
        w = w_rows[row]
        for kk in range(k):
            grp = kk // g
            y[row][grp] += x[kk] * w[kk]
    return y


def command_bytes(cmd):
    """(x_bytes, w_bytes) as raw little-endian byte strings for preload,
    using the same padded row layout the descriptor's W_STRIDE implies."""
    k = cmd["k"]
    x_alloc = ((k + 3) // 4) * 4
    x_bytes = bytes(_s8(v) for v in cmd["x"]) + b"\x00" * (x_alloc - k)
    w_stride = cmd["w_stride"]
    w_bytes = b"".join(
        bytes(_s8(v) for v in row) for row in cmd["w_rows"]
    )
    assert len(w_bytes) == cmd["n"] * w_stride
    return x_bytes, w_bytes


def command_expected(cmd):
    """Flat list of Y words (row-major n*ceil(K/G)+g, matching NPU-02
    layout) computed by the group-outer reference."""
    y = gemv_group_i8_by_group(cmd["x"], cmd["w_rows"], cmd["k"], cmd["n"], cmd["group"])
    flat = []
    for row in y:
        flat.extend(row)
    return flat


def command_y_word_count(cmd):
    return cmd["n"] * group_count(cmd["k"], cmd["group"])


def y_sentinel_bytes(word_count):
    return struct.pack("<%dI" % word_count, *([Y_SENTINEL_WORD] * word_count))


def _s32_to_u32(v):
    return v & 0xFFFFFFFF


def build_expected_blob(commands):
    """Build the full B1 independent-expected blob (header + directory +
    data) for the given commands, in directory order == commands order.
    Returns bytes, CRC-32/ISO-HDLC-covered over [32, blob_bytes) per the
    header's own crc32/blob_bytes fields (see format comment above).
    """
    cmd_count = len(commands)
    directory_bytes = cmd_count * EXPECTED_RECORD_BYTES
    data_offset0 = EXPECTED_HEADER_BYTES + directory_bytes

    records = []
    data_chunks = []
    offset = data_offset0
    for cmd in commands:
        words = command_expected(cmd)
        wc = len(words)
        records.append(struct.pack(EXPECTED_RECORD_STRUCT, cmd["tag"], wc, offset, 0))
        data_chunks.append(struct.pack("<%di" % wc, *words))
        offset += wc * 4

    blob_bytes = offset
    body = b"".join(records) + b"".join(data_chunks)
    assert len(body) == blob_bytes - EXPECTED_HEADER_BYTES

    crc = crc32_iso_hdlc(body)
    header = struct.pack(
        EXPECTED_HEADER_STRUCT,
        EXPECTED_MAGIC, EXPECTED_ABI, cmd_count, blob_bytes, crc, 0, 0, 0,
    )
    return header + body
