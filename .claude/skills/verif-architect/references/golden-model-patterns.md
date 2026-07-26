# Golden model patterns (P0)

- Interface shape: per-cycle `step(inputs) -> outputs`, never precomputed
  vectors — testbenches must drive arbitrary reset/stimulus patterns in
  lock-step (mid-transaction reset is untestable against a fixed vector).
- Illegal parameters/inputs: raise at construction (ValueError), never guess
  behavior the spec rules unspecified.
- vplan sim/formal split heuristic: structural or negative shalls ("purely
  registered", "no async logic") → tag `formal` (finite sim can't exhaust
  them) with a sim-side sanity note; cycle-timing behavior → sim vs golden.
- Ship a `__main__` self-check with hand-computed expectations — it doubles
  as the spec's executable review.
