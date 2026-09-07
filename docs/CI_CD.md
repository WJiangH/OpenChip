# CI and source delivery

The `CI` workflow uses stable check names and read-only repository permission.
It runs against the checked-out event commit:

| Job | Trigger | Work |
|---|---|---|
| `boundaries` | pull request | boundary-tool tests and aggregate role/path check |
| `framework` | pull request and main push | coverage reporter, source-packaging, and boundary-tool tests |
| `gates` | pull request and main push | RTL lint, unit simulation, and formal jobs |
| `delivery` | successful `framework` and `gates` on a main push | exact tracked-source snapshot |

The required test jobs do not use path filters. Review verdicts remain separate
from job status: a completed automation job can still carry substantive findings
that block readiness.

## Reproducible inputs and logs

Workflow actions are pinned to immutable commit SHAs. Python is selected by an
exact patch version, Python packages are pinned in `requirements.txt`, and the
Linux OSS CAD Suite release and archive digest are declared in
`flow/versions.mk`. CI verifies that archive digest before using the tools.
The gate job creates `.venv` from setup-python's selected interpreter and places
that environment before the EDA suite on the effective test PATH. Its identity
log records the selected Python and `cocotb-config` paths plus cocotb's Python
and libpython paths so the simulator startup can be checked against the pins.

Each test job records the event source SHA, checked-out SHA, and observed tool
versions. Its logs are uploaded even when a shell check fails, when the runner
has produced files to retain. Artifact names include the source SHA and run
attempt; CI artifacts currently have 14-day retention.

## Tested source snapshot

Delivery occurs in the same workflow that tested the commit. It requires
successful `framework` and `gates` jobs, a `push` event, `refs/heads/main`, the
event repository matching the workflow repository, and checked-out `HEAD`
matching the event SHA.

`scripts/package_source_snapshot.py` reads the full commit tree and blob objects
and writes a deterministic tar archive. Git export attributes and local worktree
attributes cannot omit or rewrite its files. The archive therefore contains
committed Git tree entries only: untracked worktree files, caches, credentials,
and local drafts are outside its input. Existing public tracked bytes are
preserved exactly; the delivery job does not add generated build outputs. Git
symlinks, including canonical role-method mirrors, remain symlinks. The delivery
artifact contains:

- `openchip-source-<sha>.tar`, rooted at `openchip-source-<sha>/`;
- `manifest.json`, with repository, CI run identity, source commit and tree,
  tracked-entry metadata, archive size, and archive SHA-256;
- `SHA256SUMS`, covering the source archive and manifest;
- CI identity and packaging logs.

This artifact is a tested public source snapshot. It does not create a release,
tag, package registry entry, website, binary distribution, or deployment.

## Download and reproduce

Find a successful main-push run and download its SHA-named artifact:

```bash
gh run list --workflow CI --branch main --event push
gh run download <run-id> --name openchip-source-<sha>-<attempt> --dir snapshot
cd snapshot
sha256sum -c SHA256SUMS
python3 -c 'import json; print(json.load(open("manifest.json"))["source"]["commit"])'
tar -xf openchip-source-<sha>.tar
cd openchip-source-<sha>
make framework-test
```

The checksum validates downloaded bytes. Match the printed manifest commit to
the tested workflow SHA before using the snapshot. `make framework-test` needs
Python 3.9 or newer and standard shell/Git tools; it does not run the EDA gates.
