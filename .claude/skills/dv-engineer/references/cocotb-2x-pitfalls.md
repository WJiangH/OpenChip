# cocotb 2.x pitfalls (P0, cocotb 2.0.1)

- `ReadOnly()` phase traps you: after sampling you cannot write signals until
  another trigger. For simple synchronous DUTs sample with
  `await Timer(1, unit="ns")` after the clock edge instead.
- `unit=`, not `units=`, on Clock()/Timer() (deprecated alias).
- Use the make vars `TEST=` / `SEED=` — flow/sim.mk maps them to
  COCOTB_TEST_FILTER / COCOTB_RANDOM_SEED. Don't set env vars manually.
- `COVERAGE=1` is HDL coverage only; flow/sim.mk decouples it from cocotb's
  same-named Python-coverage env var (which hard-crashes). Never export
  COVERAGE or COCOTB_USER_COVERAGE yourself.
- Verilator param override: `COMPILE_ARGS += -GNAME=$(NAME)` with a make
  default, so suites can sweep: `make sim MOD=x NAME=5`.
