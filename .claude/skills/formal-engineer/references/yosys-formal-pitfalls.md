# Yosys/sby formal pitfalls (P0)

Two silent-fake-proof traps:
- `read_verilog -sv` fails OPEN on hierarchical refs: `u_dut.cnt` becomes an
  undriven free wire (warning only) — internal-state properties prove nothing
  and can even yield bogus CEXs on correct RTL. Use
  `read_slang --top <wrapper> -G PARAM=n` (slang.so ships in oss-cad-suite).
- `bind` is a silent no-op in the native Verilog frontend: parses fine, never
  instantiates, job passes with zero asserts. Never read_verilog+bind.

Anti-vacuity discipline (cheap, always):
- After prep: `chformal -lower; stat` — verify the expected $assert/$cover counts.
- Run cover mode; every assert needs a nearby reachable cover.
- Smoke-test the property file against 1–2 hand-mutated scratch copies of the RTL.

Structural shalls (no async reset, registered output) are netlist assertions,
not SVA: `select -assert-none t:$adff ...` / `select -assert-count 1 ...`.

sby details: comments are `#` (`;` = syntax error); name tasks `*_bmc/_prove/
_cover` so workdirs match .gitignore. Parameterized DUTs: prove small values
unboundedly (k-induction), argue structural equivalence for large N — and
report exactly that split.
