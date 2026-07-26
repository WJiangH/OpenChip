# Verilator lint pitfalls (P0)

- WIDTHEXPAND: comparing a sized register against an int-parameter expression
  needs an explicit cast: `cnt == CNT_W'(HALF_PERIOD - 1)`.
- `$clog2(1) == 0`: clamp derived widths to ≥ 1:
  `localparam CNT_W = (X > 1) ? $clog2(X) : 1;`
