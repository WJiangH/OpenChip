#!/usr/bin/env python3
"""Package one exact Git commit as a tracked-source archive with provenance."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Dict, List, Mapping, Optional, Sequence


REPORT_SCHEMA = "openchip.source-snapshot.v1"
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
POSITIVE_ID_RE = re.compile(r"^[0-9]+$")


class SnapshotError(ValueError):
    """Raised when an exact tracked-source snapshot cannot be produced."""


def _git(repo: Path, *args: str, text: bool = True):
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            stderr = exc.stderr
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            detail = ": {}".format(str(stderr).strip())
        raise SnapshotError("git {} failed{}".format(" ".join(args), detail)) from exc
    return result.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tracked_entries(repo: Path, source_sha: str) -> List[Mapping[str, str]]:
    raw = _git(repo, "ls-tree", "-r", "-z", source_sha, text=False)
    entries: List[Mapping[str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, encoded_path = record.split(b"\t", 1)
            mode, kind, object_sha = metadata.decode("ascii").split(" ", 2)
            path = encoded_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as exc:
            raise SnapshotError("tracked tree contains an unsupported path or entry") from exc
        entries.append(
            {
                "mode": mode,
                "object_sha": object_sha,
                "path": path,
                "type": kind,
            }
        )
    if not entries:
        raise SnapshotError("source commit contains no tracked entries")
    return entries


def create_snapshot(
    repo: Path,
    source_sha: str,
    repository: str,
    run_id: str,
    run_attempt: str,
    output_dir: Path,
) -> Mapping[str, object]:
    """Archive HEAD by Git object identity and emit a deterministic manifest."""
    repo = repo.resolve()
    if FULL_SHA_RE.fullmatch(source_sha) is None:
        raise SnapshotError("source SHA must be exactly 40 lowercase hexadecimal characters")
    if not repository or any(character.isspace() for character in repository):
        raise SnapshotError("repository identity must be non-empty and contain no whitespace")
    for label, value in (("run ID", run_id), ("run attempt", run_attempt)):
        if POSITIVE_ID_RE.fullmatch(value) is None:
            raise SnapshotError("{} must contain only ASCII digits".format(label))

    resolved = str(_git(repo, "rev-parse", "--verify", "{}^{{commit}}".format(source_sha))).strip()
    head = str(_git(repo, "rev-parse", "--verify", "HEAD^{commit}")).strip()
    if resolved != source_sha:
        raise SnapshotError("source SHA does not resolve to itself")
    if head != source_sha:
        raise SnapshotError("checked-out HEAD {} does not match source SHA {}".format(head, source_sha))

    if output_dir.exists() and any(output_dir.iterdir()):
        raise SnapshotError("output directory is not empty: {}".format(output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)

    source_tree = str(_git(repo, "rev-parse", "{}^{{tree}}".format(source_sha))).strip()
    entries = _tracked_entries(repo, source_sha)
    archive_name = "openchip-source-{}.tar".format(source_sha)
    archive_path = output_dir / archive_name
    prefix = "openchip-source-{}/".format(source_sha)
    try:
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "archive",
                "--format=tar",
                "--prefix={}".format(prefix),
                "--output={}".format(archive_path.resolve()),
                source_sha,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SnapshotError("git archive failed") from exc

    archive_sha256 = _sha256(archive_path)
    manifest: Dict[str, object] = {
        "archive": {
            "filename": archive_name,
            "sha256": archive_sha256,
            "size_bytes": archive_path.stat().st_size,
        },
        "ci": {
            "run_attempt": run_attempt,
            "run_id": run_id,
        },
        "repository": repository,
        "schema": REPORT_SCHEMA,
        "source": {
            "commit": source_sha,
            "tracked_entry_count": len(entries),
            "tree": source_tree,
        },
        "tracked_entries": entries,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    checksums_path = output_dir / "SHA256SUMS"
    checksums_path.write_text(
        "{}  {}\n{}  {}\n".format(
            archive_sha256,
            archive_name,
            _sha256(manifest_path),
            manifest_path.name,
        ),
        encoding="ascii",
    )
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Archive one exact checked-out Git commit and record its provenance."
    )
    parser.add_argument("--repo", type=Path, default=Path("."), help="Git repository checkout")
    parser.add_argument("--source-sha", required=True, help="exact 40-character commit SHA")
    parser.add_argument("--repository", required=True, help="public owner/repository identity")
    parser.add_argument("--run-id", required=True, help="CI run ID, or 0 for a local package")
    parser.add_argument("--run-attempt", required=True, help="CI run attempt, or 0 locally")
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = create_snapshot(
            repo=args.repo,
            source_sha=args.source_sha,
            repository=args.repository,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            output_dir=args.output_dir,
        )
    except (OSError, SnapshotError) as exc:
        print("source-snapshot: error: {}".format(exc), file=sys.stderr)
        return 2
    print(
        "source-snapshot: wrote {} tracked entries for {} (sha256={})".format(
            manifest["source"]["tracked_entry_count"],
            manifest["source"]["commit"],
            manifest["archive"]["sha256"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
