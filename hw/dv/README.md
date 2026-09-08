# hw/dv/ — independent verification.

The verif-architect owns plans, golden models and shared infrastructure; the
dv-engineer owns assigned test execution and coverage work.

`hw/dv/<mod>/`: Makefile (includes flow/sim.mk), test_<mod>.py, BUGS.md.
`hw/dv/common/`: shared Wishbone drivers/monitors/scoreboards.
`hw/dv/common/models/`: Python golden models — written from docs/spec/ ONLY.

Iron Rule 2: never modify hw/rtl/; expected values never come from reading RTL
logic. Failures are filed as bugs (BUGS.md + issue with `make sim MOD= TEST=
SEED=` repro), not fixed in place. Coverage gate: flow/gates.mk (≥90% line+toggle).
