# Agent attribution and contribution evidence

OpenChip records who or what performed a role without treating a model label,
Git email, or merge actor as proof of the others. The format is provider-neutral;
new provider and model strings do not require code changes.

## Identities kept separate

| Identity | Recorded fact | What it does not prove |
|---|---|---|
| Agent | label, role, provider, client, backend | a GitHub account or runtime identity |
| Requested runtime | model and effort requested by the orchestrator | the model that actually ran |
| Observed runtime | identity, attestation level, evidence | authorship or platform publication |
| Git | raw author and committer names and emails | the historic pusher |
| Platform actor | host, login, numeric ID, type, action, evidence | the agent or model behind the action |

`UNKNOWN` is data, not zero. A self-asserted record may use `self` attestation,
but it is not independent attestation. Do not infer a provider from a model
string or a platform account from an unregistered author email.

## Prepare and validate a commit

The account registry contains only platform identities and commit emails backed
by public evidence. Add an account only after verifying its host, login, numeric
ID, account type, account-associated email, and evidence URL. Do not create a
placeholder agent account or use an unverified `@agents.openchip` address.
The example below uses the repository maintainer's verified account. External
contributors must register and use their own verified account; they must not
copy the maintainer's login, ID, or email.

Prepare a message before committing:

```bash
python3 scripts/agent_attribution.py prepare \
  --summary "framework: describe the change" \
  --output /tmp/openchip-commit-message.txt \
  --account github-wjiangh \
  --author-name orchestrator-agent \
  --agent-label framework-author \
  --role orchestrator \
  --provider UNKNOWN \
  --client codex \
  --backend codex-app \
  --requested-model GPT-5.6-Sol \
  --requested-effort high \
  --observed-identity UNKNOWN \
  --attestation none \
  --runtime-evidence UNKNOWN
```

The command writes the full `OpenChip-Provenance: v1` trailer block and prints
the registered author and committer values. Use those values for this commit
only, then validate the resulting object:

```bash
git -c user.name=WJiangH \
  -c user.email=45132014+WJiangH@users.noreply.github.com \
  commit --author="orchestrator-agent <45132014+WJiangH@users.noreply.github.com>" \
  -F /tmp/openchip-commit-message.txt
make attribution-validate ATTRIBUTION_SOURCE=HEAD
```

For a PR range, validate every commit that opts into v1 metadata while leaving
legacy, merge, and human commits compatible:

```bash
make attribution-validate-range \
  ATTRIBUTION_BASE=<full-public-base-sha> \
  ATTRIBUTION_SOURCE=HEAD
```

Duplicate trailer keys are rejected case-insensitively. Requested model and
effort remain claims about configuration. An observed identity requires `self`
or `independent` attestation and an evidence reference; otherwise it must remain
`UNKNOWN` with no attestation.

The framework CI runs the attribution unit tests through `make framework-test`.
It does not currently require v1 metadata on every commit or validate each PR
range automatically. Authors record the actual commit or range validation in
the PR manifest; reviewers reproduce it against the reviewed head.

The CLI is offline. It validates record structure, registered commit identities,
Git objects, revision ranges, and head binding. It preserves cited public claims
and hashes its mutable JSON inputs, but it does not fetch or authenticate each
evidence URL and does not independently attest a model runtime.

## Work-item evidence

`openchip.work-item-provenance.v1` records contain:

- a stable work-item ID, concise scope, acceptance references, and full public
  base and head SHAs;
- participants with separate agent metadata and optional platform actor data;
- uniquely identified author, review, validation, and integration events bound
  to a commit in the work-item range;
- outcome, timestamp, public evidence references, and a finding count when it is
  known.

Positive review, validation, and integration events bind to the recorded head.
Evidence from an older head stays an older-head event unless an explicit scoped
carry-forward reference justifies reuse. Reordered evidence references do not
turn a retry into a new event. The checked-in
[`openchip-pr-19`](../provenance/work-items/openchip-pr-19.json) record is a
public technical example with author, request-changes, approval, validation, and
integration activity. It does not assign the merge actor implementation credit
or infer an unreported reviewer model.

Current PR review and integration outcomes remain in the PR manifest until they
exist as public evidence. A record cannot claim approval or acceptance for a
future commit SHA.

## Generate a contribution report

```bash
make contribution-report \
  ATTRIBUTION_SOURCE=<public-ref-or-full-sha> \
  ATTRIBUTION_REPORT=contribution-report.json
```

The selected ref is resolved once. The tool reads that commit and its reachable
ancestry only; it never scans `--all`. The human output shows participant role,
task scope, requested and observed runtime, and typed activity. JSON adds raw Git
authors and committers, verified account mappings, structured commit metadata,
events and evidence, input-file SHA-256 digests, and legacy requested labels.

Committed activity is not automatically accepted work. Acceptance requires an
explicit integration event. Merge activity stays separate from implementation,
and review findings remain review contribution. Missing finding counts remain
unknown instead of becoming zero. The report does not infer ability, quality,
cost, duration, or token use, and it does not rank agents or models.
