#!/usr/bin/env python3
"""Prepare, validate, and report evidence-based OpenChip attribution."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


UNKNOWN = "UNKNOWN"
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TRAILER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*): (\S(?:.*\S)?)$")
WORK_ITEM_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
PROVENANCE_KEYS = (
    "OpenChip-Provenance",
    "Agent-Label",
    "Agent-Role",
    "Agent-Provider",
    "Agent-Client",
    "Agent-Backend",
    "Requested-Model",
    "Requested-Effort",
    "Observed-Identity",
    "Runtime-Attestation",
    "Runtime-Evidence",
    "Platform-Host",
    "Platform-Account-Login",
    "Platform-Account-ID",
    "Platform-Account-Type",
    "Platform-Action",
    "Platform-Evidence",
)
POSITIVE_HEAD_KINDS = {"review", "validation", "integration"}
POSITIVE_OUTCOMES = {"approve", "pass", "accepted", "merged"}


class AttributionError(ValueError):
    """Raised for ambiguous, unsupported, or ungrounded attribution."""


def _git(repo: Path, *args: str, text: bool = True):
    try:
        result = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else exc.stderr
            detail = ": {}".format(str(stderr).strip())
        raise AttributionError("git {} failed{}".format(" ".join(args), detail)) from exc
    return result.stdout


def _one_line(label: str, value: str) -> str:
    if not value or "\n" in value or "\r" in value:
        raise AttributionError("{} must be one non-empty line".format(label))
    return value


def load_accounts(path: Path) -> Mapping[str, Mapping[str, object]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AttributionError("cannot read platform account registry: {}".format(exc)) from exc
    if data.get("schema") != "openchip.platform-accounts.v1" or not isinstance(data.get("accounts"), list):
        raise AttributionError("unsupported platform account registry")
    accounts: Dict[str, Mapping[str, object]] = {}
    seen_identity = set()
    for account in data["accounts"]:
        required = ("ref", "host", "login", "account_id", "account_type", "verified_commit_emails", "evidence")
        if not isinstance(account, dict) or any(key not in account for key in required):
            raise AttributionError("platform account entry is missing required fields")
        ref = account["ref"]
        identity = (account["host"], account["login"], account["account_id"])
        if ref in accounts or identity in seen_identity:
            raise AttributionError("duplicate platform account mapping")
        if not isinstance(account["account_id"], int) or account["account_id"] <= 0:
            raise AttributionError("platform account ID must be a positive integer")
        if not account["verified_commit_emails"] or not account["evidence"]:
            raise AttributionError("platform account mapping requires email and evidence")
        accounts[ref] = account
        seen_identity.add(identity)
    return accounts


def parse_trailers(message: str) -> Tuple[Mapping[str, str], Mapping[str, List[str]]]:
    lines = message.rstrip().splitlines()
    values: Dict[str, str] = {}
    duplicates: Dict[str, List[str]] = defaultdict(list)
    for line in reversed(lines):
        match = TRAILER_RE.fullmatch(line)
        if match is None:
            if line.strip() == "" and values:
                continue
            break
        key, value = match.groups()
        if key in values:
            duplicates[key].extend((value, values[key]))
        else:
            values[key] = value
    return values, duplicates


def _parse_identity(value: str) -> Mapping[str, str]:
    match = re.fullmatch(r"(.*) <([^>]*)> ([0-9]+) ([+-][0-9]{4})", value)
    if match is None:
        raise AttributionError("unsupported Git identity header")
    return {"name": match.group(1), "email": match.group(2)}


def read_commit(repo: Path, sha: str) -> Mapping[str, object]:
    raw = _git(repo, "cat-file", "commit", sha, text=False)
    header, separator, message = raw.partition(b"\n\n")
    if not separator:
        raise AttributionError("malformed commit object {}".format(sha))
    fields: Dict[str, List[str]] = defaultdict(list)
    for line in header.decode("utf-8", "replace").splitlines():
        key, _, value = line.partition(" ")
        fields[key].append(value)
    parents = fields.get("parent", [])
    decoded_message = message.decode("utf-8", "replace")
    trailers, duplicates = parse_trailers(decoded_message)
    return {
        "sha": sha,
        "parents": parents,
        "is_merge": len(parents) > 1,
        "author": _parse_identity(fields["author"][0]),
        "committer": _parse_identity(fields["committer"][0]),
        "message": decoded_message,
        "trailers": trailers,
        "duplicate_trailers": duplicates,
    }


def _account_by_email(accounts: Mapping[str, Mapping[str, object]]) -> Mapping[str, Mapping[str, object]]:
    result = {}
    for account in accounts.values():
        for email in account["verified_commit_emails"]:
            if email in result:
                raise AttributionError("commit email maps to multiple platform accounts")
            result[email] = account
    return result


def validate_commit(commit: Mapping[str, object], accounts: Mapping[str, Mapping[str, object]]) -> Mapping[str, object]:
    trailers = commit["trailers"]
    duplicates = commit["duplicate_trailers"]
    relevant_duplicates = sorted(set(duplicates).intersection(PROVENANCE_KEYS))
    if relevant_duplicates:
        raise AttributionError("duplicate provenance trailers: {}".format(", ".join(relevant_duplicates)))
    missing = [key for key in PROVENANCE_KEYS if key not in trailers]
    if missing:
        raise AttributionError("missing provenance trailers: {}".format(", ".join(missing)))
    if trailers["OpenChip-Provenance"] != "v1":
        raise AttributionError("unsupported commit provenance version")
    if trailers["Runtime-Attestation"] not in ("none", "self", "independent"):
        raise AttributionError("invalid runtime attestation")
    if trailers["Observed-Identity"] == UNKNOWN:
        if trailers["Runtime-Attestation"] != "none" or trailers["Runtime-Evidence"] != UNKNOWN:
            raise AttributionError("unknown observed identity must use no attestation and UNKNOWN evidence")
    elif trailers["Runtime-Attestation"] == "none" or trailers["Runtime-Evidence"] == UNKNOWN:
        raise AttributionError("observed identity requires attestation and evidence")

    matching = [
        account
        for account in accounts.values()
        if account["host"] == trailers["Platform-Host"]
        and account["login"] == trailers["Platform-Account-Login"]
        and str(account["account_id"]) == trailers["Platform-Account-ID"]
        and account["account_type"] == trailers["Platform-Account-Type"]
    ]
    if len(matching) != 1:
        raise AttributionError("declared platform account is not in the verified registry")
    account = matching[0]
    if trailers["Platform-Evidence"] not in account["evidence"]:
        raise AttributionError("platform evidence is not registered")
    if commit["author"]["email"] not in account["verified_commit_emails"]:
        raise AttributionError("Git author email does not map to the declared platform account")
    by_email = _account_by_email(accounts)
    committer_account = by_email.get(commit["committer"]["email"])
    return {
        "sha": commit["sha"],
        "agent": {key: trailers[key] for key in PROVENANCE_KEYS if key.startswith(("Agent-", "Requested-", "Observed-", "Runtime-"))},
        "git_author": dict(commit["author"]),
        "git_committer": dict(commit["committer"]),
        "author_account_ref": account["ref"],
        "committer_account_ref": committer_account["ref"] if committer_account else UNKNOWN,
        "pusher_account_ref": UNKNOWN,
        "platform_action": trailers["Platform-Action"],
    }


def prepare_message(args: argparse.Namespace, accounts: Mapping[str, Mapping[str, object]]) -> Mapping[str, str]:
    if args.account not in accounts:
        raise AttributionError("unknown platform account ref: {}".format(args.account))
    account = accounts[args.account]
    if args.observed_identity == UNKNOWN:
        if args.attestation != "none" or args.runtime_evidence != UNKNOWN:
            raise AttributionError("UNKNOWN observed identity requires --attestation none and UNKNOWN evidence")
    elif args.attestation == "none" or args.runtime_evidence == UNKNOWN:
        raise AttributionError("observed identity requires non-none attestation and evidence")
    values = {
        "OpenChip-Provenance": "v1",
        "Agent-Label": args.agent_label,
        "Agent-Role": args.role,
        "Agent-Provider": args.provider,
        "Agent-Client": args.client,
        "Agent-Backend": args.backend,
        "Requested-Model": args.requested_model,
        "Requested-Effort": args.requested_effort,
        "Observed-Identity": args.observed_identity,
        "Runtime-Attestation": args.attestation,
        "Runtime-Evidence": args.runtime_evidence,
        "Platform-Host": str(account["host"]),
        "Platform-Account-Login": str(account["login"]),
        "Platform-Account-ID": str(account["account_id"]),
        "Platform-Account-Type": str(account["account_type"]),
        "Platform-Action": "commit-author-identity",
        "Platform-Evidence": str(account["evidence"][0]),
    }
    for key, value in values.items():
        _one_line(key, value)
    summary = _one_line("summary", args.summary)
    message = summary + "\n\n" + "\n".join("{}: {}".format(key, values[key]) for key in PROVENANCE_KEYS) + "\n"
    args.output.write_text(message, encoding="utf-8")
    email = account["verified_commit_emails"][0]
    return {
        "message_file": str(args.output),
        "author": "{} <{}>".format(args.author_name, email),
        "committer_name": str(account["login"]),
        "committer_email": str(email),
        "platform_account_ref": str(account["ref"]),
    }


def _timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_work_item(data: object) -> Mapping[str, object]:
    if not isinstance(data, dict) or data.get("schema") != "openchip.work-item-provenance.v1":
        raise AttributionError("unsupported work-item provenance record")
    required = ("work_item_id", "scope", "source", "participants", "events")
    if any(key not in data for key in required) or WORK_ITEM_RE.fullmatch(str(data["work_item_id"])) is None:
        raise AttributionError("work-item record is missing required identity")
    source = data["source"]
    if not isinstance(source, dict) or any(FULL_SHA_RE.fullmatch(str(source.get(key, ""))) is None for key in ("base", "head")):
        raise AttributionError("work-item source requires full base and head SHAs")
    scope = data["scope"]
    if not isinstance(scope, dict) or not scope.get("summary") or not scope.get("acceptance_refs"):
        raise AttributionError("work-item scope requires summary and acceptance refs")

    participants = data["participants"]
    if not isinstance(participants, list) or not participants:
        raise AttributionError("work-item requires participants")
    participant_ids = set()
    for participant in participants:
        if not isinstance(participant, dict) or not participant.get("id") or participant["id"] in participant_ids:
            raise AttributionError("participant IDs must be unique and non-empty")
        participant_ids.add(participant["id"])
        agent = participant.get("agent")
        if not isinstance(agent, dict):
            raise AttributionError("participant requires separate agent metadata")
        for key in ("label", "role", "requested", "observed"):
            if key not in agent:
                raise AttributionError("agent metadata missing {}".format(key))
        if not isinstance(agent["requested"], dict) or any(key not in agent["requested"] for key in ("model", "effort")):
            raise AttributionError("requested model and effort are required")
        observed = agent["observed"]
        if not isinstance(observed, dict) or any(key not in observed for key in ("identity", "attestation", "evidence")):
            raise AttributionError("observed identity, attestation, and evidence are required")
        if observed["identity"] == UNKNOWN and (observed["attestation"] != "none" or observed["evidence"]):
            raise AttributionError("unknown observed identity cannot claim attestation evidence")
        actor = participant.get("platform_actor")
        if actor is not None:
            actor_keys = ("host", "login", "account_id", "account_type", "action", "evidence")
            if not isinstance(actor, dict) or any(key not in actor for key in actor_keys) or not actor["evidence"]:
                raise AttributionError("platform actor requires identity, action, and evidence")

    events = data["events"]
    if not isinstance(events, list):
        raise AttributionError("events must be a list")
    event_ids = set()
    semantic_events = set()
    for event in events:
        required_event = ("id", "kind", "participant_ref", "subject_sha", "timestamp", "outcome", "evidence")
        if not isinstance(event, dict) or any(key not in event for key in required_event):
            raise AttributionError("event is missing required fields")
        if event["id"] in event_ids or event["participant_ref"] not in participant_ids:
            raise AttributionError("event ID must be unique and participant must exist")
        if event["kind"] not in ("author", "review", "validation", "integration"):
            raise AttributionError("unsupported event kind")
        if FULL_SHA_RE.fullmatch(str(event["subject_sha"])) is None or not _timestamp(event["timestamp"]):
            raise AttributionError("event requires full subject SHA and ISO timestamp")
        if not isinstance(event["evidence"], list) or not event["evidence"]:
            raise AttributionError("event requires public evidence")
        semantic = (event["kind"], event["participant_ref"], event["subject_sha"], event["outcome"], tuple(event["evidence"]))
        if semantic in semantic_events:
            raise AttributionError("duplicate evidence event")
        event_ids.add(event["id"])
        semantic_events.add(semantic)
        if event.get("finding_count", UNKNOWN) != UNKNOWN:
            if not isinstance(event["finding_count"], int) or event["finding_count"] < 0:
                raise AttributionError("finding_count must be nonnegative or UNKNOWN")
        if event["kind"] in POSITIVE_HEAD_KINDS and event["outcome"] in POSITIVE_OUTCOMES:
            if event["subject_sha"] != source["head"] and not event.get("scope_carryforward_evidence"):
                raise AttributionError("positive review/validation/integration evidence is stale for source head")
    return data


def load_work_items(directory: Path) -> List[Mapping[str, object]]:
    if not directory.exists():
        return []
    records = []
    ids = set()
    for path in sorted(directory.glob("*.json")):
        try:
            record = validate_work_item(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise AttributionError("cannot read work-item record {}: {}".format(path, exc)) from exc
        if record["work_item_id"] in ids:
            raise AttributionError("duplicate work-item ID: {}".format(record["work_item_id"]))
        ids.add(record["work_item_id"])
        records.append(record)
    return records


def build_report(repo: Path, source: str, accounts_path: Path, records_dir: Path) -> Mapping[str, object]:
    repo = repo.resolve()
    accounts = load_accounts(accounts_path)
    resolved = str(_git(repo, "rev-parse", "--verify", "{}^{{commit}}".format(source))).strip()
    if FULL_SHA_RE.fullmatch(resolved) is None:
        raise AttributionError("source does not resolve to a full commit SHA")
    commits = [line for line in str(_git(repo, "rev-list", "--topo-order", resolved)).splitlines() if line]
    reachable = set(commits)
    email_accounts = _account_by_email(accounts)
    merges = 0
    structured = []
    legacy_requested = Counter()
    raw_authors = Counter()
    raw_committers = Counter()
    mapped_authors = Counter()
    mapped_committers = Counter()
    ambiguous = []
    for sha in commits:
        commit = read_commit(repo, sha)
        merges += int(commit["is_merge"])
        raw_authors["{} <{}>".format(commit["author"]["name"], commit["author"]["email"])] += 1
        raw_committers["{} <{}>".format(commit["committer"]["name"], commit["committer"]["email"])] += 1
        author_account = email_accounts.get(commit["author"]["email"])
        committer_account = email_accounts.get(commit["committer"]["email"])
        mapped_authors[author_account["ref"] if author_account else UNKNOWN] += 1
        mapped_committers[committer_account["ref"] if committer_account else UNKNOWN] += 1
        duplicate_keys = sorted(set(commit["duplicate_trailers"]).intersection(PROVENANCE_KEYS))
        if duplicate_keys:
            ambiguous.append({"sha": sha, "duplicate_trailers": duplicate_keys})
            continue
        if commit["trailers"].get("OpenChip-Provenance") == "v1":
            structured.append(validate_commit(commit, accounts))
        else:
            for key in ("Requested-Model", "Agent-Requested-Model"):
                if key in commit["trailers"]:
                    legacy_requested["{}={}".format(key, commit["trailers"][key])] += 1

    work_items = load_work_items(records_dir)
    event_counts = Counter()
    role_counts: Dict[str, Counter] = defaultdict(Counter)
    accepted = 0
    acceptance_unknown = 0
    findings_known = 0
    findings_unknown = 0
    participant_contexts = []
    for record in work_items:
        if record["source"]["head"] not in reachable:
            raise AttributionError("work-item head is not reachable from selected source: {}".format(record["work_item_id"]))
        participants = {participant["id"]: participant for participant in record["participants"]}
        participant_event_counts: Dict[str, Counter] = defaultdict(Counter)
        integrated = False
        for event in record["events"]:
            event_counts["{}:{}".format(event["kind"], event["outcome"])] += 1
            participant_event_counts[event["participant_ref"]][event["kind"]] += 1
            role = participants[event["participant_ref"]]["agent"]["role"]
            role_counts[role][event["kind"]] += 1
            if event["kind"] == "review":
                if event.get("finding_count", UNKNOWN) == UNKNOWN:
                    findings_unknown += 1
                else:
                    findings_known += event["finding_count"]
            if event["kind"] == "integration" and event["outcome"] in ("accepted", "merged"):
                integrated = True
        accepted += int(integrated)
        acceptance_unknown += int(not integrated)
        for participant in record["participants"]:
            participant_contexts.append(
                {
                    "work_item_id": record["work_item_id"],
                    "participant_id": participant["id"],
                    "agent": participant["agent"],
                    "event_counts": dict(sorted(participant_event_counts[participant["id"]].items())),
                }
            )

    return {
        "schema": "openchip.contribution-report.v1",
        "source": {
            "requested_ref": source,
            "resolved_commit": resolved,
            "reachable_commits": len(commits),
            "non_merge_commits": len(commits) - merges,
            "merge_commits": merges,
            "scope": "resolved commit and its reachable ancestry only",
        },
        "git_activity": {
            "structured_provenance_commits": len(structured),
            "structured_commit_attribution": structured,
            "legacy_or_unattributed_commits": len(commits) - len(structured),
            "ambiguous_commits": ambiguous,
            "raw_authors": dict(sorted(raw_authors.items())),
            "raw_committers": dict(sorted(raw_committers.items())),
            "mapped_author_accounts": dict(sorted(mapped_authors.items())),
            "mapped_committer_accounts": dict(sorted(mapped_committers.items())),
            "legacy_requested_labels": dict(sorted(legacy_requested.items())),
            "pusher_accounts": UNKNOWN,
        },
        "work_item_evidence": {
            "records": len(work_items),
            "explicitly_accepted": accepted,
            "acceptance_unknown": acceptance_unknown,
            "event_counts": dict(sorted(event_counts.items())),
            "review_findings_known_total": findings_known,
            "review_events_with_unknown_finding_count": findings_unknown,
            "role_activity": {role: dict(sorted(counts.items())) for role, counts in sorted(role_counts.items())},
            "participant_contexts": participant_contexts,
        },
        "unavailable_metrics": {
            "ability_score": UNKNOWN,
            "cost": UNKNOWN,
            "duration": UNKNOWN,
            "tokens": UNKNOWN,
        },
        "limitations": [
            "Git history measures committed activity; it does not prove acceptance or capability.",
            "Merge activity is not implementation credit.",
            "Requested labels are not observed runtime identity.",
            "Git author and committer fields do not identify the historic pusher without platform evidence.",
            "Role and task context must accompany any comparison; no causal model ranking is computed.",
        ],
    }


def render_text(report: Mapping[str, object]) -> str:
    source = report["source"]
    evidence = report["work_item_evidence"]
    lines = [
        "OpenChip contribution report",
        "source: {} (requested {})".format(source["resolved_commit"], source["requested_ref"]),
        "reachable history: {} commits ({} non-merge, {} merge)".format(
            source["reachable_commits"], source["non_merge_commits"], source["merge_commits"]
        ),
        "work-item evidence: {} records; {} explicitly accepted; {} acceptance UNKNOWN".format(
            evidence["records"], evidence["explicitly_accepted"], evidence["acceptance_unknown"]
        ),
        "events:",
    ]
    for key, count in evidence["event_counts"].items():
        lines.append("  {}: {}".format(key, count))
    lines.append("role activity (event counts, not capability scores):")
    for role, counts in evidence["role_activity"].items():
        lines.append("  {}: {}".format(role, ", ".join("{}={}".format(key, value) for key, value in counts.items())))
    lines.append("unavailable: ability_score, cost, duration, tokens = UNKNOWN")
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=Path, default=Path("provenance/platform-accounts.json"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="write a validated commit message with v1 trailers")
    prepare.add_argument("--summary", required=True)
    prepare.add_argument("--output", required=True, type=Path)
    prepare.add_argument("--account", required=True)
    prepare.add_argument("--author-name", required=True)
    prepare.add_argument("--agent-label", required=True)
    prepare.add_argument("--role", required=True)
    prepare.add_argument("--provider", default=UNKNOWN)
    prepare.add_argument("--client", default=UNKNOWN)
    prepare.add_argument("--backend", default=UNKNOWN)
    prepare.add_argument("--requested-model", default=UNKNOWN)
    prepare.add_argument("--requested-effort", default=UNKNOWN)
    prepare.add_argument("--observed-identity", default=UNKNOWN)
    prepare.add_argument("--attestation", choices=("none", "self", "independent"), default="none")
    prepare.add_argument("--runtime-evidence", default=UNKNOWN)

    validate = subparsers.add_parser("validate-commit", help="validate one commit's provenance")
    validate.add_argument("--repo", type=Path, default=Path("."))
    validate.add_argument("--commit", default="HEAD")

    report = subparsers.add_parser("report", help="report reachable Git and work-item evidence")
    report.add_argument("--repo", type=Path, default=Path("."))
    report.add_argument("--source", default="HEAD")
    report.add_argument("--records-dir", type=Path, default=Path("provenance/work-items"))
    report.add_argument("--json-output", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_message(args, load_accounts(args.accounts))
            print(json.dumps(result, sort_keys=True))
        elif args.command == "validate-commit":
            sha = str(_git(args.repo, "rev-parse", "--verify", "{}^{{commit}}".format(args.commit))).strip()
            result = validate_commit(read_commit(args.repo, sha), load_accounts(args.accounts))
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            result = build_report(args.repo, args.source, args.accounts, args.records_dir)
            print(render_text(result), end="")
            if args.json_output:
                args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (AttributionError, OSError) as exc:
        print("agent-attribution: error: {}".format(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
