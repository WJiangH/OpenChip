# Review execution identity and observed events

Use this reference when an entrypoint consumes an execution binding, or a
receipt drives acceptance or resource reuse. It adds two checks to the normal
contract/diff review. It is a candidate method for these boundaries, not a
validated general runner audit or a substitute for domain verification.

## Binding at the real entrypoint

**Trigger:** a launch is meant to run an exact reviewed candidate under a
particular work-item identity.

Read the actual validator and the governing binding contract. Identify which
field names the source snapshot and which names configuration or dependencies;
matching an outer candidate field does not check a contradictory inner binding.
Exercise the production validator, without launching the payload, with:

- a complete valid binding;
- a missing or null required field, including a required zero-valued field;
- wrong types or invalid bounds, and a complete-shaped candidate/dependency
  mismatch that gets past the structural checks.

Use the contract's actual requirements. Rejecting an absent field is different
from treating its default value as evidence. Retain the exact input, validator
version, result and rejection reason. A malformed fixture rejected for the wrong
reason does not establish the intended cross-binding check.

**Boundary:** identity consistency is not authentication, authorization or a
ledger freshness check. Do not add those systems to a scoped diagnostic by
inference. For a supplied immutable binding, compare it with the actual granted
candidate; do not infer scope from an epoch or a plausible work-item name alone.

## Intent, process start and completion

**Trigger:** a receipt claims that a tool ran or that an attempt completed.

Trace each claimed event to the code path that records it. A purpose label or
pre-spawn intent must not initialize an observed-execution flag. Exercise the
smallest permitted failure boundary: identity rejection before spawn, failed
spawn, and successful spawn followed by a nonzero exit. Use harmless children
or explicitly labeled mocks if the real payload is not authorized.

Check the resulting raw record against what happened: no start before spawn;
failed spawn consumes any contract-defined attempt budget but does not invent a
started PID or exit code; successful start and actual exit are separate events.
A metadata-only invocation does not prove the later workload ran. Keep partial
records and uncertain completion distinguishable from completed failure and
acceptance. Re-run the original failure against the repaired exact version,
then use a later independent task to test whether the method transfers.

**Evidence and limits:** preserve inputs, command intentions, returned process
identities, actual exits and the checker verdict separately. Process status and
checker agreement are different claims. Local mocks or a different host's
process controls do not prove production process-tree cleanup, ISA behavior or
hardware success. Require the task's existing cleanup and resource evidence
before reuse; this reference grants no new execution or fault-injection budget.
