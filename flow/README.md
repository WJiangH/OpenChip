# Flow environments

Start every tool-dependent assignment here. Reference-flow pins remain in
`versions.mk`, the root `requirements.txt` and [CI setup](../docs/CI_CD.md).
Imported designs may use their accepted native environment. Availability of
one environment says nothing about another or about a DUT outcome.

From any checkout or linked worktree:

```bash
python3 scripts/environment.py list
python3 scripts/environment.py check <profile-id>
```

The first command prints the fixed private index location and configured
profile IDs/owners. Read that index and the selected profile's README before
checking. The default store is `.local-designs/environments/` beside the shared
Git directory's parent checkout, so linked worktrees find the same records.
An explicitly configured alternate private store can be selected with
`--store /absolute/private/path` before the command. Absence is reported as
`NOT_CONFIGURED`; do not create guessed tool paths or select a different runtime.

The check invokes the selected, hash-bound private adapter and retains its raw
output and JSON result in a new private receipt directory. It prints only the
classification and receipt path. It performs no build or DUT execution. A
profile for a wrapper-based runtime must exercise the actual bootstrap,
wrapper and runner, substituting an owned harmless child at the simulator
boundary. Capture only named runtime variables, verify the exact interpreter,
libraries and artifact identities, and inspect dynamic dependencies in that
child context. Outer-shell environment checks alone cannot establish this.
Any control XML is labeled NO_DUT and never supplied as test acceptance evidence.

| Classification | Meaning and next action |
|---|---|
| READY_NO_DUT | Recorded identity and the child-boundary probe passed; resume only the separately authorized task |
| NOT_CONFIGURED | Index/profile missing or invalid; environment owner supplies the accepted configuration |
| NO_ACCESS | Docker/socket/file access unavailable; follow the existing tool approval mechanism for authorized read/probe access |
| STALE_IDENTITY | Container, adapter or dependency differs from its recorded identity; stop and send observed/expected hashes to the owner |
| MISSING_LIBRARY | Required runtime file/dependency unavailable in the actual child; apply only the recorded local repair, then retry once |
| TIMEOUT | The probe expired; retain partial logs and remote completion uncertainty, confirm owned-process exit before shared-runtime reuse, then escalate |
| PROBE_FAILED | The runner/probe did not establish its expected environment-only result; inspect the private log and route to the environment owner |

Each assigned agent owns routine environment diagnosis for its task. Within
existing authority it may use the profile's documented per-process environment
settings, create its own probe directory, correct permissions only on files it
just created, and retry a failed preflight once after a specific documented
repair. Retain before/after evidence; a repeat without a changed cause is not
progress. Do not change recorded expected hashes to fit observed values.
An access approval needed by the tool remains required; this page cannot grant
permissions. New access/resources, downloads, rebuilds, baseline/cache changes,
source or requirement changes go to the named environment owner or maintainer.
The orchestrator receives a concise blocker and receipt link, not a request to
debug paths. No automatic repair, job scheduler or resource lock is implemented.
Agents coordinate shared compute using the profile's named owner/current-use
record before preflight or execution; a health receipt is a dated observation,
not a reservation or permission to interrupt another task.

Environment owners maintain `README.md`, `index.json`, and one directory per
profile in the approved private store. The index maps IDs to profile JSON files.
A profile records `schema_version: 1`, `id`, `owner`, `adapter`,
`adapter_sha256`, and `timeout_seconds` (1–60), plus adapter-specific runtime
identities and paths. The adapter is a reviewed standard-library Python entry
invoked as `adapter.py PROFILE_PATH RECEIPT_DIRECTORY`. It must write
`result.json` with a classification from the table and `dut_executed: false`.
It owns bounded remote-process termination with a finite force-kill grace,
retains partial output and remote recovery context on timeout, checks before mutation, selected
variable capture and raw evidence; the launcher also bounds its local process
group. A zero exit alone cannot establish readiness. The adapter hash is checked
before execution, but this is trusted reviewed code, not an access sandbox.

Keep concrete container IDs, tool/cache paths, ownership handles, probe sources,
logs and accepted repairs in the private store. Include provenance for migrated
diagnostics and never silently discard failed startup attempts. Profiles must
exclude RTL, software algorithms, test oracles, expected DUT values and verdicts
so independently assigned DV can discover environments without reading product
implementation. Binary identities are permitted; they are not behavioral
evidence. Review actual read permissions separately when isolation is required.

When registering or changing a profile, an independent agent starts from this
entry alone, reproduces the real no-DUT preflight and checks failure
classification. Framework unit tests use synthetic adapters only to test the
launcher contract; they never substitute for that real consumer demonstration.

## Imported native flows

[CoralNPU](../hw/ip/coralnpu/README.md) provides an explicit pinned-source and
native Chisel/Bazel model build entry. Its dependencies and acceptance are
separate from the reference RTL gates.
