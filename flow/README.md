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

## Local orchestration ledger

The manager can guard covered dispatches with the standard-library
`scripts/orchestration_ledger.py` entry. Choose one durable private database
per project in its existing orchestration store and record that location in
its fixed state entry. All managers must use the same database. Do not select
another path or initialize a replacement during recovery. This helper does not
launch workers, schedule wakeups, write `STATE.md`, enforce resource budgets,
or authenticate caller observations and grants.

```bash
python3 scripts/orchestration_ledger.py --ledger /absolute/private/ledger.sqlite init
python3 scripts/orchestration_ledger.py --ledger /absolute/private/ledger.sqlite inspect
python3 scripts/orchestration_ledger.py --ledger /absolute/private/ledger.sqlite admit request.json --expected-revision 0
```

`init` is an explicit first-use action and refuses an existing path. Every other
command refuses a missing database. `inspect` returns the ledger ID, revision,
runs and retained events. Every mutation requires the observed **ledger**
revision; a conflict means inspect and reconcile, never blindly repeat dispatch.
SQLite transactions protect this local ledger only. The root manager remains
the sole `STATE.md` writer and manually checks its expected state revision when
applying a proposed delta. Atomic protection across the ledger and `STATE.md`,
distributed locking, and protection for launches bypassing the helper are not
implemented. Do not place the database on an unvalidated shared filesystem.

An `admit` request contains exactly `identity` and `grant`. The identity has
`work_item`, `owner` (nonempty strings), `candidate` (Git SHA or SHA256),
`dependencies` (explicit name-to-SHA256 object; `{}` means none), and positive
integer `attempt`. The grant is an artifact reference: an absolute `path` and
its `sha256`. Its JSON body contains exactly the same `identity`,
`action: "dispatch"`, and a nonempty `authority` reference. The manager must
verify that reference against actual delegated authority; a matching hash is
not permission. No resource or submission authority is inferred.

Admission commits an **UNKNOWN** intent before the manager calls the external
dispatch tool. It returns a `binding` with those identity fields plus `ledger_id`,
`epoch`, `run_id`, and `grant_sha256`. Preserve that entire object. An unresolved
work item excludes another admission even with a changed owner, attempt or
candidate. A subsequent admitted attempt must increase its number and needs
its own matching grant. There is no timeout-based release or reset command.

The remaining commands take a request file and `--expected-revision`:

| Command | Request fields | Evidence JSON body and result |
|---|---|---|
| `attach` | `binding`, `handle`, `evidence` artifact reference | Exact `binding`, `handle`, `observation: "HANDLE_RETURNED"`; records ACKNOWLEDGED, never PASS |
| `observe` | `binding`, `handle`, `observation`, `evidence` | Exact same binding/handle/observation; LIVE or UNKNOWN remain unresolved. A missing handle is allowed only for UNKNOWN |
| `finish` | `binding`, `handle`, `evidence` | Exact binding/handle, disposition, exit_code, result, checked_scope and artifacts as described below |

A worker handle is exactly `kind: "worker"`, `host`, and the actual returned
`id`. A process handle is exactly `kind: "process"`, `host`, positive `pid`,
`start_time`, `command_sha256`, absolute `cwd`, and run `nonce`. Strings must be
nonempty. Recover the actual handle after an ambiguous external call before
attaching it; do not invent one. A crash between the intent and handle recording
cannot provide exactly-once external execution. This first slice has no abandon
operation for an intent proven never dispatched: without an actual returned
handle it remains held, pending a separately reviewed reconciliation extension.
Do not invent a handle or erase the ledger to release it. Missing live information stays
UNKNOWN and blocks a replacement. Expired handles, lease times, PID reuse and
clock jumps do not establish completion.

A completion body requires `result: "PASS"` or `"FAIL"`, a nonempty list of
`checked_scope` strings, and nonempty `artifacts` containing verified file
references. Processes require `disposition: "EXITED"` and an integer
`exit_code`; PASS also requires zero. A worker API that does not expose process
exit codes uses `disposition: "COMPLETED"` and `exit_code: null`; the manager must
observe actual task completion and independently check its semantic result.
Worker completion additionally requires an explicit `owned_jobs` list. An empty
list declares the manager checked that there are no owned external jobs; it is
not automatic discovery. Each nonempty entry has a process `handle` and an
`evidence` file reference whose JSON contains the parent `binding`, that handle,
`disposition: "EXITED"`, and an actual integer `exit_code`. LIVE, UNKNOWN or
unavailable job identity prevents completion and keeps the work item held.
Unsupported external scheduler identities require manual reconciliation before
this contract can be extended; never represent them as invented process IDs.
The caller remains responsible for complete job enumeration.
Neither ACK nor exit zero alone is completion. FAIL is retained as a failure
terminal, not approval. Missing fields, altered hashes, mismatched handles and
old bindings are rejected. Normalized evidence JSON is retained in the event
journal; preserve the referenced raw tool outputs and result artifacts in the
private evidence store as well. This is a trusted-caller identity guard, not an
independent verifier of a remote process or its checker semantics.

Independent exact-candidate review, resource accounting, cause-specific retry,
manual stage acceptance and maintainer tapeout authorization remain binding.
A merged PR does not terminate a long-term task; its configured maintainer
acceptance condition does. Local scenario tests run in `make framework-test`.
They do not prove live dispatch protection: record a real operation through this
entry after independent acceptance before claiming covered operational use.
Native wake delivery, app/host availability and 24-hour/7-day endurance require
separate observations.
