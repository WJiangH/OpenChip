# verif/ — cocotb testbenches. Written ONLY by the dv-engineer role.

`verif/<mod>/`: Makefile (includes flow/sim.mk), test_<mod>.py, BUGS.md.
`verif/common/`: shared Wishbone drivers/monitors/scoreboards.
`verif/common/models/`: Python golden models — written from docs/spec/ ONLY.

Iron Rule 2: never modify rtl/; expected values never come from reading RTL
logic. Failures are filed as bugs (BUGS.md + issue with `make sim MOD= TEST=
SEED=` repro), not fixed in place. Coverage gate: flow/gates.mk (≥90% line+toggle).
