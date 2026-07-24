# syn/ — Yosys synthesis + OpenSTA. Owned by the backend-engineer role.

Per module: `<mod>.ys` script + `<mod>.sdc` constraints derived from the spec's
clocking section (target: flow/gates.mk, 50 MHz sky130). Checks: no inferred
latches, cell count and Fmax reported. Constraints are spec — never loosened to
pass (Iron Rule 5). Run: `make synth MOD=<mod>`.
