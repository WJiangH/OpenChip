# Resume from evidence

The durable state index describes the project; it does not prove that a process
is alive, a branch is unchanged, a task was accepted, or authority still covers
a changed action. Reconcile only the dependencies needed for the next action,
then expand as needed. Do not scan private histories or every experiment by
default.

Start with the exact state and receipt paths already supplied. Read related
metadata, peer conversations or another agent's answer only to resolve a named
missing dependency or inconsistency. Their conclusions are attributed claims,
not a substitute for the source-bound receipts needed for a verification claim.

1. **Recover scope.** Read the state entrypoint, agreement/authority references,
   active requirement/milestone edges, latest checkpoint and relevant signoff
   records. Use current instructions to resolve superseded decisions. Preserve
   unresolved requirements; do not replace the long-term goal with the latest
   status question. If an entrypoint is absent, use existing artifacts to build
   a small truthful index; unknown goals/authority remain unknown.
2. **Verify the candidate.** Inspect actual working directory, repository,
   branch, commit, dirty paths and worktrees read-only. Check referenced PR head,
   state, CI and substantive reviews using available authenticated access.
   Distinguish feature head from tested merge candidate. Do not checkout,
   reset, rebase or edit a user's active branch to make stale state match.
3. **Reconcile assignments before dispatch.** Query stored worker/session
   handles where supported. A worker that is still running keeps ownership;
   read or send a bounded follow-up rather than start a duplicate. An expired
   handle is not evidence that its external job stopped. Adopt its artifacts
   only with candidate binding, preserve RTL/DV separation, and explicitly
   transfer ownership when replacement is necessary. If workers cannot be
   enumerated, record UNKNOWN and reconcile the job/receipt path before retry.
4. **Reconcile each relevant job.** Prefer scheduler/run IDs with host and
   attempt identity; for local processes bind PID to start time, command, working
   directory and candidate/run nonce. A reused PID alone proves nothing. Read
   last-progress units/time and final receipts, tool exit and semantic verdict,
   selected/executed/checked counts, output hashes and source/binary identity.
   An alive or quiet process is not PASS. Interpret flags using their defined
   receipt semantics and execution state: missing evidence or a flag explicitly
   meaning "not yet verified" remains unverified; a false aggregate-closure
   flag alone may mean incomplete work. Preserve an executed check's explicit
   failed verdict (including `passed: false` when defined that way) as FAIL;
   do not relabel it UNKNOWN because another review is pending.
   Missing terminal evidence means
   RUNNING/UNKNOWN as supported by observation, not a fabricated completion.
   A missing process without a receipt needs investigation; do not immediately
   rerun an expensive or externally mutating job. Retry only after ruling out
   duplicate execution and within the saved scope/budget.
5. **Refresh the next decision.** Record last-verified time and evidence for
   changed entries. Reopen invalidated signoff records, preserve historical
   acceptance and list reruns. Unblock a dependency only when its stated
   acceptance condition is met; DELIVERED work is not inherently ACCEPTED.
   Read [the signoff lifecycle](../../../../docs/SILICON_LIFECYCLE.md) when a
   milestone decision or change impact requires it.
   Separate reviewer/evaluator conclusions from checks you reproduced yourself;
   a completed review job or an evaluation opinion is not your own tool evidence.
6. **Resume or checkpoint.** Continue an authorized ready item; if a required
   capability, credential, budget or independent context is unavailable, keep
   that item BLOCKED and progress unaffected items. Write one next action with
   owner and unblock condition. For intentional waiting, record what will
   trigger resumption and whether any scheduler is actually registered. Never
   promise an unattended watch from a state file alone.

Use the entrypoint's status budget and avoid unchanged polls. Before ending a
session, record active durable handles, pending reviews, exact next inspection,
authority/publication limits and the state revision. The next session repeats
this reconciliation, not the entire project's implementation history.
