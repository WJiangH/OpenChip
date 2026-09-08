# Local activation before the framework branch is integrated

Prefer the checked-in canonical method once it exists in the intended checkout.
To activate an independently reviewed candidate before integration, use a local
bootstrap with an identified source commit; do not switch the user's branch or
edit global memories/configuration. Keep this preparation separate from any
authorization to merge the public framework PR.

Suggested private layout:

```text
AGENTS.override.md                         local Codex routing only
.local-designs/orchestration/STATE.md       project entrypoint and checkpoint
.local-designs/orchestration/runtime/
  SOURCE.md                               reviewed commit, paths and SHA-256s
  .agents/skills/orchestrator/SKILL.md      exact reviewed skill copy
  .agents/skills/orchestrator/references/   exact reviewed supporting references
  docs/                                   referenced reviewed policy/templates
```

Inspect existing overrides first; preserve their instructions and do not
overwrite an unrelated bootstrap. Ensure the local files are ignored using the
repository's local exclude configuration (resolve it with
`git rev-parse --git-path info/exclude`), and verify with `git check-ignore` and
`git status`. `.local-designs/` is already ignored by this repository. Ignoring
files prevents routine staging, not filesystem access or forced publication.

Codex loads at most one instruction file per directory and prefers
`AGENTS.override.md` over `AGENTS.md`. Therefore the override must explicitly
read the root constitution. New runs rebuild the instruction chain; modifying
the override does not establish that an already-running session reloaded it.
[Official Codex instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

Use this routing text, adapting the project entrypoint only when needed:

```markdown
# Local OpenChip startup

All paths below are relative to the repository root, even when the session
starts in a subdirectory. Resolve that root before reading them.

Read ./AGENTS.md explicitly and follow the repository constitution. This local
entrypoint supplements it; Codex may otherwise skip that same-directory file.
An explicit specialist assignment takes precedence: use its assigned role and
work item instead of defaulting to orchestration.

For unassigned project coordination, use the orchestrator role. Prefer
./.agents/skills/orchestrator/SKILL.md when present; otherwise read
./.local-designs/orchestration/runtime/SOURCE.md, verify the recorded copy hashes,
and read ./.local-designs/orchestration/runtime/.agents/skills/orchestrator/SKILL.md.
Read ./.local-designs/orchestration/STATE.md and reconcile live Git, assignments,
jobs and receipts before acting. Preserve existing goal/authority and private
publication boundaries. A state file does not schedule background work.
Resolve references relative to the selected skill. The fallback mirrors
repository paths so its referenced policy/templates resolve within the recorded
snapshot. Missing dependencies must be restored from that reviewed source;
do not guess a newer policy or silently ignore an obligation.
```

Record required policy/template dependencies in SOURCE.md and include their
exact source copies so the fallback is self-contained for its task. Keep the
snapshot's hash inventory separate from changing project state. Start a fresh
minimal-context session and verify its loaded role,
constitution, state source and first actions against real read-only observations.
Do not infer successful startup from a valid Markdown file or skill validator.
If canonical and fallback versions differ, record the selected source and
reconcile changed policy before resuming; never silently mix their instructions.
