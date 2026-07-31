"""Golden reference model for the `npu` module.

Spec: docs/spec/npu.md (requirements NPU-01 through NPU-23), read against
docs/spec/soc_1.md for system context (memory map, IRQ map, bus). Pure
Python, no cocotb / simulator dependency — importable and runnable
standalone (see `__main__` below), and the single source of "expected
value" for the npu DV suite (hw/dv/npu/). Per the verif-architect
clean-room rule (/CLAUDE.md Iron Rule 2), this model was written from the
spec TEXT only, never from hw/rtl/.

Two API layers, per the issue's ask:

1. Descriptor-level / CSR-mirroring: `write_csr(offset, value)` /
   `read_csr(offset)`, register offsets and reset values exactly per
   spec §3 — what a cocotb Wishbone driver calls after translating a WB
   write/read transaction.
2. Per-step, lock-step interface for the weight-stream ingress port:
   `ws_ready` (mirrors `o_ws_ready`) and `step(ws_valid, ws_data)` (mirrors
   one rising `clk` edge with `i_ws_valid`/`i_ws_data` sampled) — a cocotb
   bench drives this once per clock edge alongside the DUT.

Bit-exactness core (§4.1, NPU-09..12): `to_s32`, `requantize` — these are
the functions RTL bit-exactness is ultimately judged against.

Spec ambiguities found while implementing (filed here per the
verif-architect method — not resolved by picking an interpretation):

  A1. §3.6 does not define an argmax tie-break rule (two channels with an
      equal winning requantised value). This model keeps the
      lowest-index winner (strict `>` compare, first-seen wins).
  A2. §3.1 does not define CTRL.GO and CTRL.ABORT written as 1 in the same
      write. This model applies ABORT first (forcing IDLE/BUSY=0), then
      evaluates GO's NPU-21 checks against the resulting state — i.e. an
      abort-then-dispatch-in-the-same-cycle reading. An equally defensible
      reading exists (GO ignored whenever ABORT is also set); RTL intake
      should confirm which one hardware implements.
  A3. §4.3's `TAIL` state is documented only as "fixed latency, a few
      cycles" with no exact count. This model does not claim a specific
      cycle count: `step()` treats `TAIL` as taking exactly one extra
      step() call before `DONE`. DV must not assert an exact TAIL cycle
      count against this model — only NPU-18's ordering guarantee
      (`DONE` never before the last weight byte is consumed) is
      spec-backed.
  A4. Neither npu.md nor soc_1.md defines how the *first* activation
      vector (e.g. a token embedding, before any normal-mode NPU op has
      run to populate the SRAM via NPU-13 writeback) gets into the 2 kB
      activation SRAM in the first place. The CSR window is
      "CSR/descriptor access only" (§1) with no data-write register, and
      there is no third bus/port into this SRAM in §2. This model exposes
      `act_sram` as a directly-writable bytearray for test setup, but that
      is a test-harness convenience, not a modeled hardware interface —
      flagged for chief-architect / npu.md revision.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable, Sequence


# --------------------------------------------------------------------------
# Bit-exact arithmetic core (§4.1, NPU-09 through NPU-12)
# --------------------------------------------------------------------------

def s8(byte: int) -> int:
    """Interpret an unsigned byte (0..255) as signed int8 (-128..127)."""
    byte &= 0xFF
    return byte - 256 if byte >= 128 else byte


def to_s32(value: int) -> int:
    """Two's-complement-wrap an arbitrary Python int into signed 32 bits.

    Models the physical 32-bit accumulator register (NPU-09): every add
    wraps like ordinary two's-complement hardware, regardless of whether
    the workload-legal `K <= 4096` bound (which this spec guarantees never
    actually overflows) holds — the wrap behavior is a property of the
    register, not a special case gated on K.
    """
    value &= 0xFFFF_FFFF
    return value - 0x1_0000_0000 if value >= 0x8000_0000 else value


def _round_half_away_from_zero(t: int, s: int) -> int:
    """NPU-11's rounding rule, symbol-for-symbol from the spec pseudocode."""
    if s == 0:
        return t
    half = 1 << (s - 1)
    if t >= 0:
        return (t + half) >> s
    return -((-t + half) >> s)


def sat8(value: int) -> int:
    """NPU-12: clamp to the signed int8 range."""
    if value > 127:
        return 127
    if value < -128:
        return -128
    return value


def requantize(acc: int, scale_m: int, scale_shift: int) -> int:
    """NPU-11/NPU-12: `sat8(round_half_away_from_zero(acc * M, s))`.

    `acc` is the lane's final 32-bit signed accumulator; `scale_m` is the
    unsigned 16-bit `SCALE_M`; `scale_shift` is the unsigned 5-bit
    `SCALE_SHIFT`. `t = acc * scale_m` is exact Python-integer arithmetic
    (fits the spec's 48-bit-signed intermediate with no truncation — 48
    bits is sized to hold the exact 32-bit-signed x 16-bit-unsigned
    product, not a narrowing point).
    """
    acc = to_s32(acc)
    scale_m &= 0xFFFF
    scale_shift &= 0x1F
    t = acc * scale_m
    rounded = _round_half_away_from_zero(t, scale_shift)
    return sat8(rounded)


# --------------------------------------------------------------------------
# Weight-stream byte ordering (§2.3 NPU-08, §4.2 NPU-14/NPU-15/NPU-16)
# --------------------------------------------------------------------------

def pack_weight_stream(
    weights: Sequence[Sequence[int]], n_len: int, c: int = 8, ws_width: int = 32
) -> list[int]:
    """Serialize a K x N weight matrix into the ingress-port word stream.

    `weights[k][n]` is the raw byte (0..255, interpreted signed per s8) for
    reduction index `k`, output channel `n`. Produces the flattened,
    k-major/channel-minor, low-byte-first-packed word list NPU-08/NPU-14
    define: for each output-channel group `g = 0..n_len/c-1`, for each `k`,
    the `c` bytes `w[k][g*c .. g*c+c-1]` consecutively, before any byte for
    `k+1`; then packed `ws_width/8` bytes per word, byte `i` at bits
    `[8i+7:8i]`.

    This is the inverse of what `NpuModel.step()` consumes — used both to
    drive a DUT's ingress port and, in this file's self-check, to drive
    `NpuModel` itself so both act on the identical stream.
    """
    if n_len % c != 0:
        raise ValueError(f"n_len={n_len} must be a multiple of c={c} (NPU-21 N_NOT_MULTIPLE_OF_C)")
    k_len = len(weights)
    bytes_per_word = ws_width // 8
    flat: list[int] = []
    for g in range(n_len // c):
        for k in range(k_len):
            row = weights[k]
            for ch in range(c):
                flat.append(row[g * c + ch] & 0xFF)
    if len(flat) % bytes_per_word != 0:
        raise ValueError(
            f"K*N ({len(flat)}) must be a multiple of ws_width/8 ({bytes_per_word}) "
            "for this helper's simple word packing"
        )
    words = []
    for i in range(0, len(flat), bytes_per_word):
        word = 0
        for j in range(bytes_per_word):
            word |= flat[i + j] << (8 * j)
        words.append(word)
    return words


# --------------------------------------------------------------------------
# CSR-level descriptor model (§3)
# --------------------------------------------------------------------------

class NpuModel:
    """Register- and cycle-level golden model of `npu` (docs/spec/npu.md).

    Construction implements the reset state (NPU-01, §3's reset column):
    every CSR resets to 0, the sequencer resets to `IDLE`; the activation
    SRAM's *contents* are explicitly NOT reset (NPU-01: a hard macro, data
    survives reset) — only `act_sram_bytes`-sized storage is allocated once
    at construction and left untouched by `reset()`.
    """

    C = 8
    ACT_SRAM_BYTES = 2048
    FIFO_DEPTH = 2

    REG_CTRL = 0x00
    REG_STATUS = 0x04
    REG_ERR_CODE = 0x08
    REG_K_LEN = 0x0C
    REG_N_LEN = 0x10
    REG_ACT_BASE = 0x14
    REG_OUT_BASE = 0x18
    REG_SCALE_M = 0x1C
    REG_SCALE_SHIFT = 0x20
    REG_RESULT_IDX = 0x24
    REG_RESULT_VAL = 0x28

    _WRITABLE = {
        REG_CTRL, REG_K_LEN, REG_N_LEN, REG_ACT_BASE, REG_OUT_BASE,
        REG_SCALE_M, REG_SCALE_SHIFT,
    }
    _KNOWN = _WRITABLE | {REG_STATUS, REG_ERR_CODE, REG_RESULT_IDX, REG_RESULT_VAL}

    ERR_NONE = 0
    ERR_K_ZERO = 1
    ERR_N_ZERO = 2
    ERR_N_NOT_MULTIPLE_OF_C = 3
    ERR_ACT_RANGE = 4
    ERR_OUT_RANGE = 5
    ERR_BUSY_REJECT = 6

    def __init__(self, ws_width: int = 32):
        if ws_width <= 0 or ws_width % 8 != 0 or (self.C * 8) % ws_width != 0:
            raise ValueError(
                f"ws_width={ws_width!r} must be a positive multiple of 8 dividing "
                f"C*8={self.C * 8} bits (§2.4)"
            )
        self.ws_width = ws_width
        self.act_sram = bytearray(self.ACT_SRAM_BYTES)
        self.reset()

    def reset(self) -> None:
        """Apply `rst_n` (NPU-01): every CSR/sequencer flop -> its §3 reset
        value / IDLE. Activation SRAM contents are untouched (see class
        docstring).
        """
        self.mode = 0
        self.busy = 0
        self.done = 0
        self.err = 0
        self.err_code = self.ERR_NONE
        self.k_len = 0
        self.n_len = 0
        self.act_base = 0
        self.out_base = 0
        self.scale_m = 0
        self.scale_shift = 0
        self.result_idx = 0
        self.result_val = 0
        self._reset_sequencer()

    def _reset_sequencer(self) -> None:
        self.state = "IDLE"
        self._fifo: deque[int] = deque()
        self._group_idx = 0
        self._group_pos = 0
        self._accs = [0] * self.C

    # -- IRQ mirrors (§2.5) --------------------------------------------
    @property
    def irq_done(self) -> int:
        return self.done

    @property
    def irq_err(self) -> int:
        return self.err

    # -- CSR access (§3, NPU-02..05) ------------------------------------
    def read_csr(self, offset: int) -> int:
        """NPU-05: unmapped offsets read 0x0000_0000."""
        if offset == self.REG_CTRL:
            return (self.mode & 1) << 1  # GO/ABORT always read back 0 (§3.1)
        if offset == self.REG_STATUS:
            return (self.busy & 1) | ((self.done & 1) << 1) | ((self.err & 1) << 2)
        if offset == self.REG_ERR_CODE:
            return self.err_code & 0xFFFF_FFFF
        if offset == self.REG_K_LEN:
            return self.k_len & 0xFFFF
        if offset == self.REG_N_LEN:
            return self.n_len & 0xFFFF
        if offset == self.REG_ACT_BASE:
            return self.act_base & 0x7FF
        if offset == self.REG_OUT_BASE:
            return self.out_base & 0x7FF
        if offset == self.REG_SCALE_M:
            return self.scale_m & 0xFFFF
        if offset == self.REG_SCALE_SHIFT:
            return self.scale_shift & 0x1F
        if offset == self.REG_RESULT_IDX:
            return self.result_idx & 0xFFFF
        if offset == self.REG_RESULT_VAL:
            return self.result_val & 0xFFFF_FFFF
        return 0x0000_0000

    def write_csr(self, offset: int, value: int) -> None:
        """NPU-04: full-word write regardless of byte-select. NPU-05:
        writes to unmapped offsets are silently ignored.
        """
        value &= 0xFFFF_FFFF
        if offset == self.REG_K_LEN:
            self.k_len = value & 0xFFFF
        elif offset == self.REG_N_LEN:
            self.n_len = value & 0xFFFF
        elif offset == self.REG_ACT_BASE:
            self.act_base = value & 0x7FF
        elif offset == self.REG_OUT_BASE:
            self.out_base = value & 0x7FF
        elif offset == self.REG_SCALE_M:
            self.scale_m = value & 0xFFFF
        elif offset == self.REG_SCALE_SHIFT:
            self.scale_shift = value & 0x1F
        elif offset == self.REG_CTRL:
            self._write_ctrl(value)
        # else: unmapped/RO offset, silently ignored (NPU-05)

    def _write_ctrl(self, value: int) -> None:
        go = value & 0x1
        self.mode = (value >> 1) & 0x1
        abort = (value >> 2) & 0x1

        if abort:
            # A2: ABORT applied first; NPU-19's "regardless of current
            # state" — no-op if already IDLE falls out naturally.
            self._reset_sequencer()
            self.busy = 0

        if not go:
            return

        # NPU-21: priority-ordered malformed-descriptor checks, evaluated
        # against the register state as it stands after this same write
        # (including this write's own MODE/ABORT bits) — first match wins.
        checks = [
            (self.k_len == 0, self.ERR_K_ZERO),
            (self.n_len == 0, self.ERR_N_ZERO),
            (self.n_len % self.C != 0, self.ERR_N_NOT_MULTIPLE_OF_C),
            (self.act_base + self.k_len > self.ACT_SRAM_BYTES, self.ERR_ACT_RANGE),
            (self.mode == 0 and self.out_base + self.n_len > self.ACT_SRAM_BYTES, self.ERR_OUT_RANGE),
            (self.busy == 1, self.ERR_BUSY_REJECT),
        ]
        for bad, code in checks:
            if bad:
                self.err = 1
                self.err_code = code
                return

        # Dispatch (NPU-21 "NONE": IDLE -> RUN, §4.3).
        self.err = 0
        self.err_code = self.ERR_NONE
        self.done = 0
        self.busy = 1
        self._group_idx = 0
        self._group_pos = 0
        self._accs = [0] * self.C
        self.state = "RUN"

    # -- Weight-stream ingress + sequencer (§2.3, §4.2, §4.3) -----------
    @property
    def ws_ready(self) -> int:
        """NPU-07: low whenever the 2-entry FIFO holds 2 unconsumed
        entries, high otherwise.
        """
        return int(len(self._fifo) < self.FIFO_DEPTH)

    def step(self, ws_valid: int, ws_data: int) -> dict:
        """Advance the model by exactly one rising `clk` edge.

        Mirrors what a cocotb bench samples/drives at the DUT boundary
        each edge: `ws_valid`/`ws_data` are `i_ws_valid`/`i_ws_data` as
        sampled at this edge; the returned dict mirrors `o_ws_ready`
        (sampled *before* this edge's push, matching a synchronous FIFO:
        a word pushed this cycle is not poppable until a later step) plus
        `busy`/`done`/`err` for convenience.

        One `step()` call: pops and fully unpacks at most one
        `ws_width`-bit FIFO word (NPU-14/NPU-15 — the sequencer advances
        lane accumulators as bytes are unpacked from the FIFO), then (if
        `ws_ready` was high and `ws_valid` is set) pushes the new word.
        Pop-before-push, as in a real synchronous FIFO.
        """
        ready_before = self.ws_ready

        if self.state == "RUN" and self._fifo:
            word = self._fifo.popleft()
            self._consume_word(word)
        elif self.state == "TAIL":
            # A3: TAIL's exact latency is spec-unspecified ("a few
            # cycles"); this model takes exactly one extra step().
            self.state = "DONE"
        elif self.state == "DONE":
            self.done = 1
            self.busy = 0
            self.state = "IDLE"

        if ready_before and ws_valid:
            self._fifo.append(ws_data & ((1 << self.ws_width) - 1))

        return {
            "ws_ready": ready_before,
            "busy": self.busy,
            "done": self.done,
            "err": self.err,
        }

    def _consume_word(self, word: int) -> None:
        nbytes = self.ws_width // 8
        group_size = self.k_len * self.C
        for i in range(nbytes):
            byte = (word >> (8 * i)) & 0xFF
            k = self._group_pos // self.C
            c = self._group_pos % self.C
            x = s8(self.act_sram[self.act_base + k])
            w = s8(byte)
            self._accs[c] = to_s32(self._accs[c] + x * w)
            self._group_pos += 1
            if self._group_pos == group_size:
                self._finish_group()

    def _finish_group(self) -> None:
        g = self._group_idx
        for c in range(self.C):
            n = g * self.C + c
            out = requantize(self._accs[c], self.scale_m, self.scale_shift)
            if self.mode == 0:
                self.act_sram[self.out_base + n] = out & 0xFF
            else:
                # A1: strict '>' -> first (lowest-index) max wins on ties.
                if n == 0 or out > self.result_val_signed:
                    self.result_idx = n
                    self.result_val = out & 0xFFFF_FFFF
        self._group_pos = 0
        self._accs = [0] * self.C
        self._group_idx += 1
        if self._group_idx * self.C >= self.n_len:
            self.state = "TAIL"

    @property
    def result_val_signed(self) -> int:
        v = self.result_val & 0xFF
        return s8(v)

    # -- Convenience: one-shot descriptor dispatch -----------------------
    def dispatch_and_run(
        self,
        k_len: int,
        n_len: int,
        act_base: int,
        out_base: int,
        scale_m: int,
        scale_shift: int,
        mode: int,
        weights: Sequence[Sequence[int]],
        max_cycles: int = 10_000_000,
    ) -> None:
        """Test-harness convenience built entirely from `write_csr`/`step`
        (no separate arithmetic path): programs the descriptor, dispatches
        it, and clocks `step()` with an always-ready weight source until
        the sequencer returns to `IDLE`. Raises if a malformed-descriptor
        error is raised on dispatch, or if `max_cycles` is exhausted.
        """
        self.write_csr(self.REG_K_LEN, k_len)
        self.write_csr(self.REG_N_LEN, n_len)
        self.write_csr(self.REG_ACT_BASE, act_base)
        self.write_csr(self.REG_OUT_BASE, out_base)
        self.write_csr(self.REG_SCALE_M, scale_m)
        self.write_csr(self.REG_SCALE_SHIFT, scale_shift)
        self.write_csr(self.REG_CTRL, (mode & 1) << 1 | 0x1)
        if self.err:
            raise RuntimeError(f"dispatch rejected, ERR_CODE={self.err_code}")

        words = iter(pack_weight_stream(weights, n_len, self.C, self.ws_width))
        pending = None
        for _ in range(max_cycles):
            if pending is None:
                pending = next(words, None)
            valid = pending is not None
            data = pending if pending is not None else 0
            info = self.step(valid, data)
            if valid and info["ws_ready"]:
                pending = None
            if self.state == "IDLE" and self.done:
                return
        raise RuntimeError("dispatch_and_run: max_cycles exhausted without DONE")


# --------------------------------------------------------------------------
# Self-check
# --------------------------------------------------------------------------

def _self_check() -> bool:
    ok = True

    def check(label: str, got, want) -> None:
        nonlocal ok
        status = "PASS" if got == want else "FAIL"
        if got != want:
            ok = False
        print(f"[{status}] {label}: got={got!r} want={want!r}")

    # --- NPU-11 rounding, hand-computed edge cases ---
    # s=0: no shift/rounding at all.
    check("round s=0 passthrough", _round_half_away_from_zero(1234, 0), 1234)
    # s=1, t=5 -> half=1 -> (5+1)>>1 = 3 (away from zero, ties round up).
    check("round half-up, t=5,s=1", _round_half_away_from_zero(5, 1), 3)
    # s=1, t=4 -> half=1 -> (4+1)>>1 = 2 (exact tie: 4/2=2.0, +0.5 rounds to 2 via floor(2.5)=2... check by hand)
    check("round half tie, t=4,s=1", _round_half_away_from_zero(4, 1), 2)
    # s=1, t=-5 -> -((5+1)>>1) = -3 (away from zero on the negative side too).
    check("round half-away-negative, t=-5,s=1", _round_half_away_from_zero(-5, 1), -3)
    # s=3, t=12 -> half=4 -> (12+4)>>3 = 2
    check("round s=3, t=12", _round_half_away_from_zero(12, 3), 2)

    # --- NPU-12 saturation boundaries ---
    check("sat8 in-range top", sat8(127), 127)
    check("sat8 in-range bottom", sat8(-128), -128)
    check("sat8 clamps above", sat8(128), 127)
    check("sat8 clamps below", sat8(-129), -128)
    check("sat8 clamps far above", sat8(999999), 127)

    # --- requantize: worked example combining rounding + saturation ---
    # acc=100, M=200, s=4: t=20000, half=8, (20000+8)>>4=1250 -> saturate to 127.
    check("requantize saturates positive", requantize(100, 200, 4), 127)
    # acc=-100, M=200, s=4: t=-20000 -> -((20000+8)>>4) = -1250 -> saturate -128.
    check("requantize saturates negative", requantize(-100, 200, 4), -128)
    # acc=10, M=13, s=2: t=130, half=2, (130+2)>>2=33 -> saturate to 33 (in range).
    check("requantize in-range", requantize(10, 13, 2), 33)
    # M=0: forced-zero output regardless of acc (still exercises round/sat trivially).
    check("requantize M=0 -> 0", requantize(999, 0, 5), 0)
    # s=0 passthrough then saturate.
    check("requantize s=0 passthrough+saturate", requantize(200, 1, 0), 127)

    # --- to_s32 two's-complement wrap ---
    check("to_s32 max positive", to_s32(0x7FFF_FFFF), 2147483647)
    check("to_s32 wraps at boundary", to_s32(0x8000_0000), -2147483648)
    check("to_s32 wraps negative-to-positive", to_s32(-0x8000_0001), 2147483647)

    # --- pack_weight_stream: small hand-traced example, K=2,N=8 (C=8, one group) ---
    W = [[i for i in range(8)], [10 + i for i in range(8)]]  # k=0 row, k=1 row
    words = pack_weight_stream(W, n_len=8, c=8, ws_width=32)
    # flat byte order: k=0 c=0..7 (0..7), k=1 c=0..7 (10..17); 4 bytes/word.
    want_flat = [0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 16, 17]
    want_words = [
        want_flat[0] | want_flat[1] << 8 | want_flat[2] << 16 | want_flat[3] << 24,
        want_flat[4] | want_flat[5] << 8 | want_flat[6] << 16 | want_flat[7] << 24,
        want_flat[8] | want_flat[9] << 8 | want_flat[10] << 16 | want_flat[11] << 24,
        want_flat[12] | want_flat[13] << 8 | want_flat[14] << 16 | want_flat[15] << 24,
    ]
    check("pack_weight_stream K=2,N=8 word count", len(words), 4)
    check("pack_weight_stream K=2,N=8 words", words, want_words)

    # --- End-to-end small GEMV, normal mode, hand-computed ---
    # K=2, N=8 (one group of C=8), activations x = [3, -1] (s8), weights as
    # above (all positive, small). acc[c] = x0*W[0][c] + x1*W[1][c].
    # M=1, s=0 (identity passthrough of the raw sum, still through sat8).
    m = NpuModel(ws_width=32)
    m.act_sram[0] = 3 & 0xFF   # x[0] = 3
    m.act_sram[1] = (-1) & 0xFF  # x[1] = -1 (as s8 byte 0xFF)
    m.dispatch_and_run(
        k_len=2, n_len=8, act_base=0, out_base=100,
        scale_m=1, scale_shift=0, mode=0, weights=W,
    )
    expected_out = []
    for c in range(8):
        acc = 3 * W[0][c] + (-1) * W[1][c]
        expected_out.append(sat8(acc) & 0xFF)
    got_out = list(m.act_sram[100:108])
    check("end-to-end GEMV normal-mode output bytes", got_out, expected_out)
    check("end-to-end GEMV STATUS.DONE set", m.done, 1)
    check("end-to-end GEMV STATUS.BUSY clear", m.busy, 0)
    check("end-to-end GEMV STATUS.ERR clear", m.err, 0)

    # --- Argmax mode, same shape, verify RESULT_IDX/RESULT_VAL ---
    m2 = NpuModel(ws_width=32)
    m2.act_sram[0] = 3 & 0xFF
    m2.act_sram[1] = (-1) & 0xFF
    m2.dispatch_and_run(
        k_len=2, n_len=8, act_base=0, out_base=0,
        scale_m=1, scale_shift=0, mode=1, weights=W,
    )
    best_c = max(range(8), key=lambda c: sat8(3 * W[0][c] + (-1) * W[1][c]))
    best_val = sat8(3 * W[0][best_c] + (-1) * W[1][best_c])
    check("argmax RESULT_IDX", m2.result_idx, best_c)
    check("argmax RESULT_VAL (signed)", m2.result_val_signed, best_val)

    # --- Accumulator at workload-maximum magnitude (K=768, all bytes +-127) ---
    m3 = NpuModel(ws_width=32)
    K = 768
    for k in range(K):
        m3.act_sram[k] = 127  # x[k] = 127 (s8)
    W3 = [[127] * 8 for _ in range(K)]  # all weight bytes = 127
    m3.dispatch_and_run(
        k_len=K, n_len=8, act_base=0, out_base=2000,
        scale_m=1, scale_shift=0, mode=0, weights=W3,
    )
    max_acc = K * 127 * 127
    check("NPU-09 max-magnitude acc stays in-bounds", max_acc < 2 ** 31, True)
    check("NPU-09 max-magnitude end-to-end output saturates", list(m3.act_sram[2000:2008]), [127] * 8)

    # --- Accumulator at NPU-09's stated bound (K=4096, all bytes +-127) ---
    # NPU-09: "the accumulator shall never overflow for any descriptor with
    # K <= 4096" — a bound this module's ERR_ACT_RANGE check does not itself
    # enforce (ACT_BASE+K_LEN > 2048 in fact rejects any legal dispatch with
    # K > 2048, since ACT_SRAM_BYTES=2048 and ACT_BASE >= 0; K=4096 is thus
    # reachable only via wrap-around reads, an out-of-scope descriptor for
    # dispatch_and_run). This drives the same lane-accumulate arithmetic
    # `_consume_word` uses (`to_s32(acc + x*w)`, x=w=127 each MAC, the
    # magnitude-maximizing case) directly, K=4096 times, to check NPU-09's
    # overflow claim at its literal stated bound independent of the
    # separately-spec'd SRAM-sizing check.
    K4 = 4096
    acc4 = 0
    for _ in range(K4):
        acc4 = to_s32(acc4 + 127 * 127)
    max_acc4 = K4 * 127 * 127
    check("NPU-09 K=4096 max-magnitude acc stays in-bounds", max_acc4 < 2 ** 31, True)
    check("NPU-09 K=4096 accumulator does not wrap (to_s32 matches exact sum)", acc4, max_acc4)
    check("NPU-09 K=4096 max-magnitude requantised result saturates", requantize(acc4, 1, 0), 127)

    # --- NPU-21 error codes, individually and in priority combination ---
    def fresh():
        mm = NpuModel(ws_width=32)
        return mm

    mm = fresh()
    mm.write_csr(NpuModel.REG_N_LEN, 8)
    mm.write_csr(NpuModel.REG_CTRL, 0x1)  # K_LEN still 0
    check("ERR_CODE K_ZERO", mm.err_code, NpuModel.ERR_K_ZERO)
    check("STATUS.ERR set on K_ZERO", mm.err, 1)

    mm = fresh()
    mm.write_csr(NpuModel.REG_K_LEN, 2)
    mm.write_csr(NpuModel.REG_CTRL, 0x1)  # N_LEN still 0
    check("ERR_CODE N_ZERO", mm.err_code, NpuModel.ERR_N_ZERO)

    mm = fresh()
    mm.write_csr(NpuModel.REG_K_LEN, 2)
    mm.write_csr(NpuModel.REG_N_LEN, 5)  # not a multiple of C=8
    mm.write_csr(NpuModel.REG_CTRL, 0x1)
    check("ERR_CODE N_NOT_MULTIPLE_OF_C", mm.err_code, NpuModel.ERR_N_NOT_MULTIPLE_OF_C)

    mm = fresh()
    mm.write_csr(NpuModel.REG_K_LEN, 2)
    mm.write_csr(NpuModel.REG_N_LEN, 8)
    mm.write_csr(NpuModel.REG_ACT_BASE, 2047)  # 2047+2 > 2048
    mm.write_csr(NpuModel.REG_CTRL, 0x1)
    check("ERR_CODE ACT_RANGE", mm.err_code, NpuModel.ERR_ACT_RANGE)

    mm = fresh()
    mm.write_csr(NpuModel.REG_K_LEN, 2)
    mm.write_csr(NpuModel.REG_N_LEN, 8)
    mm.write_csr(NpuModel.REG_OUT_BASE, 2047)  # 2047+8 > 2048, mode=0
    mm.write_csr(NpuModel.REG_CTRL, 0x1)  # MODE=0
    check("ERR_CODE OUT_RANGE", mm.err_code, NpuModel.ERR_OUT_RANGE)

    mm = fresh()
    mm.write_csr(NpuModel.REG_K_LEN, 2)
    mm.write_csr(NpuModel.REG_N_LEN, 8)
    mm.write_csr(NpuModel.REG_CTRL, 0x1)  # legal dispatch -> BUSY=1
    check("legal dispatch: BUSY set, no error", (mm.busy, mm.err), (1, 0))
    mm.write_csr(NpuModel.REG_CTRL, 0x1)  # second GO while BUSY
    check("ERR_CODE BUSY_REJECT", mm.err_code, NpuModel.ERR_BUSY_REJECT)

    # Priority combination: K_ZERO and ACT_RANGE both true -> K_ZERO wins.
    mm = fresh()
    mm.write_csr(NpuModel.REG_K_LEN, 0)
    mm.write_csr(NpuModel.REG_ACT_BASE, 2047)
    mm.write_csr(NpuModel.REG_N_LEN, 8)
    mm.write_csr(NpuModel.REG_CTRL, 0x1)
    check("NPU-21 priority: K_ZERO beats ACT_RANGE", mm.err_code, NpuModel.ERR_K_ZERO)

    # --- ABORT recovery (NPU-19): forces IDLE/BUSY=0 mid-RUN ---
    mm = fresh()
    mm.write_csr(NpuModel.REG_K_LEN, 4)
    mm.write_csr(NpuModel.REG_N_LEN, 8)
    mm.write_csr(NpuModel.REG_CTRL, 0x1)
    mm.step(1, 0x01020304)  # feed one word, still mid-RUN (needs 4 words for K=4,N=8)
    check("mid-RUN before abort: busy=1", mm.busy, 1)
    mm.write_csr(NpuModel.REG_CTRL, 0x4)  # ABORT
    check("NPU-19: ABORT clears BUSY immediately", mm.busy, 0)
    check("NPU-19: ABORT returns sequencer to IDLE", mm.state, "IDLE")

    # --- ws_ready / FIFO backpressure (NPU-06/07): never drops, stalls instead ---
    mm = fresh()
    mm.write_csr(NpuModel.REG_K_LEN, 8)
    mm.write_csr(NpuModel.REG_N_LEN, 8)
    mm.write_csr(NpuModel.REG_CTRL, 0x1)
    r1 = mm.step(1, 0xAAAAAAAA)
    r2 = mm.step(1, 0xBBBBBBBB)
    check("ws_ready high with room for 2", (r1["ws_ready"], r2["ws_ready"]), (True, True))

    # --- NPU-15: WS_WIDTH=32 vs WS_WIDTH=64 give identical numerical
    #     results (only cycle count differs, not RTL, and not this model's
    #     output values either).
    W4 = [[(i * 3 + k) % 251 for i in range(8)] for k in range(4)]  # K=4,N=8
    results = {}
    for ws_width in (32, 64):
        mw = NpuModel(ws_width=ws_width)
        for k in range(4):
            mw.act_sram[k] = (k * 5 + 1) & 0xFF
        mw.dispatch_and_run(
            k_len=4, n_len=8, act_base=0, out_base=50,
            scale_m=3, scale_shift=2, mode=0, weights=W4,
        )
        results[ws_width] = list(mw.act_sram[50:58])
    check("NPU-15: WS_WIDTH=32 and 64 produce identical results", results[32], results[64])

    print("PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    result = _self_check()
    raise SystemExit(0 if result else 1)
