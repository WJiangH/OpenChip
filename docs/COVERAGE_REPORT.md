# Diagnostic Verilator coverage report

`scripts/coverage_report.py` inventories every instrumented point in one
existing Verilator Coverage-3 `coverage.dat`. It reports hit, total, and
percentage separately for `branch`, `expr`, `line`, and `toggle`, first
across the input and then per source and `h` hierarchy. It lists every
zero-count point with its complete metadata.

Run it through the repository entrypoint:

```bash
make coverage-report \
  COVERAGE_DATA=path/to/coverage.dat \
  COVERAGE_REPORT=path/to/coverage-report.json
```

Both variables name one file. The command does not accept a directory, glob, or
set of files because combining independent coverage outputs requires proof that
their builds and point identities match.

The report records the input SHA-256, the exact Coverage-3 format header,
record counts, and `coverage_closure: false`. Missing, empty, malformed, or
duplicate records fail. Required metadata must be present, and a `t` kind
outside the four reported kinds fails instead of silently changing a
denominator. The output path may not resolve to the input path.

This parser supports the Coverage-3 record form exercised by its tests. The file
format does not encode a producer version, so the report records
`producer_version: "not encoded in input"` and makes no broader version
compatibility claim.

## Interpretation limits

This output is a diagnostic point census. A `t=line` record is a Verilator
code-flow point, not one physical source line; several points can map to one
line. Toggle records cover only instrumented bits. Startup and reset activity
can also contribute to cumulative counters, depending on the producing
testbench.

The percentages are advisory raw-point ratios. The reporter does not evaluate
or close the thresholds in `flow/gates.mk`, apply exclusions or waivers, or
produce a signoff verdict. Its JSON always contains
`coverage_gate: "not_evaluated"`. Use the official `verilator_coverage`
annotation workflow when source annotation is required, and use separately
reviewed acceptance logic for a coverage gate.

References:

- [Verilator coverage analysis](https://verilator.org/guide/latest/simulating.html#coverage-analysis)
- [`verilator_coverage` command](https://verilator.org/guide/latest/exe_verilator_coverage.html)
