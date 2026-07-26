# Spec authoring patterns (P0)

- Requirement IDs: `<MODULE>-NN` (e.g. BLINK-03), one per shall. vplan rows,
  RTL reports, and formal properties all cite them — the ID is the
  traceability key across every downstream artifact.
- Edge cases the spec doesn't want to define: rule them ILLEGAL/unspecified
  explicitly (stating whether it's an elaboration-time error), and flag the
  judgment call to the human. Never leave silence; never invent behavior.
- When behavior scales with a parameter, include a "structurally identical
  for any valid N" clause — it's what lets formal prove small N unboundedly
  and argue large N by structure.
