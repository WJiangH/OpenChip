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

## System integration and workload-driven numeric contracts

- Check grouping/tiling against each operator's actual reduction and row dimensions, not only model hidden size or total tensor elements. Define tail lanes, row strides, per-group accumulation and scale placement across the hardware/software boundary. A supported file format alone does not establish that its runtime handles those shapes.
- Pin IP interface claims to the selected revision and configuration. Reconcile diagrams, endpoint maps and software-visible behavior after intake; especially verify error responses, interrupt ABI and initiator versus target roles rather than inheriting an older integration diagram.
- Trace who can execute every boot transition. When a security IP needs host service, specify the trusted execution that supplies it and the later application authorization separately. For fatal recovery, distinguish a halted/reset CPU from retained bridge/fabric transaction state. Hold VALID and payload where the protocol requires it, while allowing already-issued transactions to drain; define coordinated reset separately.
