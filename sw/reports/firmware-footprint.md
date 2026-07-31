# Firmware footprint estimate — boot ROM & firmware SRAM sizing (Q-SOC1-03)

Role: sw-engineer · Issue: #6 · Spec refs: `docs/spec/soc_1.md` §3.2, SOC1-08,
SOC1-10, §4.4, Q-SOC1-03

## Method

Two freestanding rv32imc/ilp32 images were written and compiled — not
guessed — under `sw/estimate/` (see that directory's README for the
clean-room caveats on placeholder CSR offsets):

- `boot.elf` — first-stage loader (SOC1-08): program flash-controller
  CSR, arm a stream descriptor into firmware SRAM, poll transfer-complete,
  jump to `0x0001_0000`.
- `firmware.elf` — runtime main loop (SOC1-10, §4.4): per-token sequencing
  of the 43 weight-stream descriptors a stories15M token actually needs
  (6 layers × 7 GEMV ops + 1 `lm_head`, per
  `workloads/tinystories/profile.md` §2's op table), IRQ dispatch for the
  four software-owned lines (§4.4), and UART token output. `MAX_TOKENS`
  (session length) only changes a runtime loop bound, not code size —
  confirmed by inspection of `fw_main.c`, not re-measured per token count.

Toolchain: `riscv-none-elf-gcc (xPack GNU RISC-V Embedded GCC x86_64) 14.2.0`,
matching the pin in `flow/versions.mk` (`RISCV_GCC_VERSION := 14.2.0-3`,
xpack release tag `v14.2.0-3`). Flags: `-march=rv32imc -mabi=ilp32 -Os
-ffreestanding -nostdlib -nostartfiles`.

Build + size report: `make -C sw/estimate size
RISCV_GCC_BINDIR=<path-to-xpack>/bin/`.

## Results — `size` (Berkeley format, text/data/bss only; excludes
non-`ALLOC` debug sections, which cost no chip memory)

```
   text	   data	    bss	    dec	    hex	filename
    179	      0	      0	    179	     b3	boot.elf

   text	   data	    bss	    dec	    hex	filename
    500	      0	   2076	   2576	    a10	firmware.elf
```

## Results — `size -A` (per-section)

```
boot.elf  :
section             size   addr
.text                158      0
.rodata               21    160
Total (ALLOC only)   179

firmware.elf  :
section             size    addr
.text                428   65536
.rodata               72   65964
.bss                  20   66036
.stack              2056   66056
Total (ALLOC only)  2576
```

(`.riscv.attributes`, `.comment`, `.debug_*` omitted above — present in the
built ELF for debugging but not `ALLOC`, so they occupy no boot-ROM or
firmware-SRAM address space.)

## .text/.rodata/.bss/stack breakdown

| Image | .text | .rodata | .data | .bss | .stack | **Total** |
|---|---:|---:|---:|---:|---:|---:|
| `boot.elf` (boot ROM) | 158 B | 21 B | 0 | 0 | n/a (uses SRAM top, §4.1) | **179 B** |
| `firmware.elf` (firmware SRAM) | 428 B | 72 B | 0 | 20 B | 2,056 B (2 KB budget, §below) | **2,576 B** |

`.bss` in `firmware.elf` is 4 `uint32_t` IRQ-flag globals (`irq.c`) + one
flash-offset cursor (`fw_main.c`) — 20 bytes, not the transformer's weight
data, which never lives in firmware SRAM (§1: "streaming engine hanging off
an external memory port", not resident weights).

## Recommendation

**Boot ROM: 2 KB implemented (of the 64 KB window, §3.2).** Measured
skeleton is 179 B (11× margin at 2 KB). Real M3 loader will likely add
retry/checksum logic and error strings (SOC1-14's "distinct stream-error
status" implies at least one diagnostic UART message) — 2 KB comfortably
covers that without meaningfully touching die area either way at this size.

**Firmware SRAM: 8 KB implemented (of the 64 KB window, §3.2).** Measured
skeleton is 2,576 B (3.2× margin at 8 KB). This reuses the spec's own worked
example (§3.2's note: "8 KB ≈ 1.14 mm² (35 % of the whole core budget)") —
not a coincidence, a deliberate anchor, now backed by a real measurement
instead of an arbitrary guess. Margin covers, beyond the measured skeleton:
a real interrupt trap-entry/exit sequence (picorv32 custom-instruction ABI,
Q-SOC1-06, not yet confirmed), a proper per-tensor flash weight-layout table
(43 entries vs. this skeleton's 7-entry per-layer-op table reused across
layers), and a fuller UART driver (`printf`-lite vs. this skeleton's raw
hex-nibble writer).

Stack: 2 KB was chosen (not measured, no simulator to observe worst-case
depth against) based on the call structure actually built —
`main → run_token → dispatch_weight_stream/dispatch_npu_gemv`, 2–3 frames
deep, tens of bytes each — plus headroom for one nested IRQ on top. 2 KB is
~4–8× that estimate.

## Open items

- **This estimate assumes the CPU does orchestration only** (ADR-0003's
  framing, cited at SOC1-10) — no RMSNorm/RoPE/softmax/requantise math in
  firmware C. That is consistent with everything `soc_1.md` states, but the
  non-GEMM element-wise math's execution location (CPU software vs. NPU
  hardware) is **not settled by any spec yet** — it is exactly Q-SOC1-07,
  deferred to the future `npu.md`. If those ops end up as CPU C code, the 8
  KB SRAM recommendation above would need revisiting (softmax/RMSNorm/exp
  approximations are typically a few hundred bytes to a few KB of code plus
  lookup tables) — flagging so this isn't silently invalidated later.
- **No area-cost figure exists for boot ROM**, unlike firmware SRAM
  (142,000 µm²/KB, `explore/npu-dse/results.md` §1). The 2 KB recommendation
  above is margin-based, not area-budget-based, because that number isn't
  available. Whether boot ROM is the same OpenRAM-class macro as firmware
  SRAM (same cost) or a cheaper mask-ROM/synthesized-ROM style block is an
  open PD-stage question this report can't resolve.
- Placeholder CSR offsets (flash-ctrl/NPU/UART/IRQ field layout) used to
  give the skeleton real load/store instructions are **not** register-map
  proposals — `sw/estimate/README.md` flags this; `npu.md`/`flash_ctrl.md`/
  `uart.md`/`irqc.md` remain unwritten (Q-SOC1-04).

## Artifacts

- `sw/estimate/` — compilable skeleton (boot loader + firmware main loop),
  `Makefile`, two linker scripts.
- This report.
