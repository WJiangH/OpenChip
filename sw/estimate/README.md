# sw/estimate/ — firmware footprint estimate skeleton (issue #6, Q-SOC1-03)

This is **not** the M3 firmware tree (`sw/firmware/`, `sw/runtime/`, `sw/apps/`
per `sw/README.md`) — it is a throwaway, compilable skeleton whose only job
is to produce a real `size(1)` report so `docs/spec/soc_1.md` §3.2's boot ROM
and firmware SRAM window sizes can be pinned instead of guessed
(`Q-SOC1-03`). See `sw/reports/firmware-footprint.md` for the result.

Two freestanding images, each with real control flow and data structures but
stub bodies where the real numerics/CSR field layouts don't exist yet:

- `boot/` — first-stage loader per SOC1-08 (program flash CSR, arm a
  stream descriptor into SRAM, poll transfer-complete, jump to SRAM).
- `firmware/` — runtime main loop per SOC1-10/§4.4 (per-token NPU
  weight-stream descriptor sequencing, IRQ dispatch, UART token output).

`common/soc1_regmap.h` fixes only the block **base addresses**, which are
spec-frozen (`soc_1.md` §3.2). Per-block **register offsets** (flash-ctrl
mode/descriptor regs, NPU CSR, UART divisor/data, IRQ mirror) are this
estimate's own placeholders — `npu.md` / `flash_ctrl.md` / `uart.md` /
`irqc.md` don't exist yet (`Q-SOC1-04`, deferred to SystemRDL/PeakRDL). They
exist only to give the skeleton real load/store instructions to size against;
do not cite them as the register spec once those module specs land.

Build: `make -C sw/estimate` (requires `riscv-none-elf-gcc` on `PATH`, pinned
version in `flow/versions.mk`). Produces `boot.elf` and `firmware.elf`
(git-ignored, per `.gitignore`'s `sw/**/*.elf`) plus a `size -A` report on
stdout.
