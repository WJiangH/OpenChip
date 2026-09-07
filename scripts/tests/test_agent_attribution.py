import argparse
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import agent_attribution  # noqa: E402


def git(repo, *args, env=None):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    ).stdout.strip()


class AgentAttributionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.name", "WJiangH")
        git(self.repo, "config", "user.email", "45132014+WJiangH@users.noreply.github.com")
        self.accounts = self.root / "accounts.json"
        self.accounts.write_text(
            json.dumps(
                {
                    "schema": "openchip.platform-accounts.v1",
                    "accounts": [
                        {
                            "ref": "github-wjiangh",
                            "host": "github.com",
                            "login": "WJiangH",
                            "account_id": 45132014,
                            "account_type": "User",
                            "verified_commit_emails": [
                                "45132014+WJiangH@users.noreply.github.com"
                            ],
                            "evidence": ["https://api.github.com/users/WJiangH"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (self.repo / "README.md").write_text("base\n", encoding="utf-8")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-q", "-m", "base")
        self.base = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self):
        self.temporary.cleanup()

    def prepare(self, **overrides):
        values = {
            "summary": "framework: attributed change",
            "output": self.root / "message.txt",
            "account": "github-wjiangh",
            "author_name": "orchestrator-agent",
            "agent_label": "framework-author",
            "role": "orchestrator",
            "provider": agent_attribution.UNKNOWN,
            "client": "codex",
            "backend": "codex-app",
            "requested_model": "GPT-5.6-Sol",
            "requested_effort": "high",
            "observed_identity": agent_attribution.UNKNOWN,
            "attestation": "none",
            "runtime_evidence": agent_attribution.UNKNOWN,
        }
        values.update(overrides)
        args = argparse.Namespace(**values)
        result = agent_attribution.prepare_message(
            args, agent_attribution.load_accounts(self.accounts)
        )
        return args.output, result

    def attributed_commit(self, **overrides):
        message, prepared = self.prepare(**overrides)
        (self.repo / "change.txt").write_text("change\n", encoding="utf-8")
        git(self.repo, "add", "change.txt")
        git(self.repo, "commit", "-q", "--author", prepared["author"], "-F", str(message))
        return git(self.repo, "rev-parse", "HEAD")

    def participant(self):
        return {
            "id": "author",
            "agent": {
                "label": "future-agent",
                "role": "orchestrator",
                "provider": None,
                "client": "grok-cli",
                "backend": None,
                "requested": {"model": "grok-future-model", "effort": "high"},
                "observed": {"identity": "UNKNOWN", "attestation": "none", "evidence": []},
            },
            "platform_actor": {
                "host": "github.com",
                "login": "WJiangH",
                "account_id": 45132014,
                "account_type": "User",
                "action": "commit-author-identity",
                "evidence": ["https://api.github.com/users/WJiangH"],
            },
        }

    def work_item(self, head, events=None):
        return {
            "schema": "openchip.work-item-provenance.v1",
            "work_item_id": "fixture-work",
            "scope": {"summary": "fixture", "acceptance_refs": ["https://example.invalid/spec"]},
            "source": {"base": self.base, "head": head},
            "participants": [self.participant()],
            "events": events or [],
        }

    def test_prepare_accepts_future_provider_and_keeps_observed_unknown(self):
        message, result = self.prepare(
            provider="xAI",
            client="grok-cli",
            backend="grok-terminal",
            requested_model="grok-future-model",
        )
        text = message.read_text(encoding="utf-8")
        self.assertIn("Agent-Provider: xAI\n", text)
        self.assertIn("Requested-Model: grok-future-model\n", text)
        self.assertIn("Observed-Identity: UNKNOWN\n", text)
        self.assertEqual(
            result["author"],
            "orchestrator-agent <45132014+WJiangH@users.noreply.github.com>",
        )

    def test_validate_commit_maps_author_but_leaves_pusher_unknown(self):
        sha = self.attributed_commit()
        commit = agent_attribution.read_commit(self.repo, sha)
        validated = agent_attribution.validate_commit(
            commit, agent_attribution.load_accounts(self.accounts)
        )
        self.assertEqual(validated["author_account_ref"], "github-wjiangh")
        self.assertEqual(validated["committer_account_ref"], "github-wjiangh")
        self.assertEqual(validated["pusher_account_ref"], "UNKNOWN")
        self.assertEqual(validated["agent"]["Observed-Identity"], "UNKNOWN")

    def test_validate_range_checks_opted_in_commits_and_skips_legacy(self):
        attributed = self.attributed_commit()
        (self.repo / "legacy.txt").write_text("legacy\n", encoding="utf-8")
        git(self.repo, "add", "legacy.txt")
        git(self.repo, "commit", "-q", "-m", "human or legacy commit")
        result = agent_attribution.validate_range(
            self.repo,
            self.base,
            "HEAD",
            agent_attribution.load_accounts(self.accounts),
        )
        self.assertEqual(result["commits_scanned"], 2)
        self.assertEqual(result["structured_commits_validated"], 1)
        self.assertEqual(result["validated"][0]["sha"], attributed)
        self.assertEqual(result["legacy_or_unattributed_commits_skipped"], 1)

    def test_standard_tab_and_folded_git_trailer_remains_structured(self):
        message, prepared = self.prepare(output=self.root / "standard-footer.txt")
        with message.open("a", encoding="utf-8") as stream:
            stream.write("Signed-off-by:\tExample <example@example.com>\n continuation text\n")
        (self.repo / "footer.txt").write_text("footer\n", encoding="utf-8")
        git(self.repo, "add", "footer.txt")
        git(self.repo, "commit", "-q", "--author", prepared["author"], "-F", str(message))
        result = agent_attribution.validate_range(
            self.repo,
            self.base,
            "HEAD",
            agent_attribution.load_accounts(self.accounts),
        )
        self.assertEqual(result["commits_scanned"], 1)
        self.assertEqual(result["structured_commits_validated"], 1)
        self.assertEqual(result["legacy_or_unattributed_commits_skipped"], 0)

    def test_duplicate_or_conflicting_provenance_trailers_fail(self):
        message, prepared = self.prepare()
        text = message.read_text(encoding="utf-8")
        message.write_text(text + "Requested-Model: conflicting\n", encoding="utf-8")
        (self.repo / "duplicate.txt").write_text("x\n", encoding="utf-8")
        git(self.repo, "add", "duplicate.txt")
        git(self.repo, "commit", "-q", "--author", prepared["author"], "-F", str(message))
        commit = agent_attribution.read_commit(self.repo, git(self.repo, "rev-parse", "HEAD"))
        with self.assertRaisesRegex(agent_attribution.AttributionError, "duplicate"):
            agent_attribution.validate_commit(
                commit, agent_attribution.load_accounts(self.accounts)
            )

        message, prepared = self.prepare(output=self.root / "case-message.txt")
        text = message.read_text(encoding="utf-8")
        message.write_text(text + "requested-model: conflicting\n", encoding="utf-8")
        (self.repo / "case.txt").write_text("x\n", encoding="utf-8")
        git(self.repo, "add", "case.txt")
        git(self.repo, "commit", "-q", "--author", prepared["author"], "-F", str(message))
        commit = agent_attribution.read_commit(self.repo, git(self.repo, "rev-parse", "HEAD"))
        with self.assertRaisesRegex(agent_attribution.AttributionError, "duplicate"):
            agent_attribution.validate_commit(
                commit, agent_attribution.load_accounts(self.accounts)
            )

    def test_work_item_rejects_stale_approval_and_duplicate_events(self):
        head = self.attributed_commit()
        stale = self.work_item(
            head,
            [
                {
                    "id": "review-old",
                    "kind": "review",
                    "participant_ref": "author",
                    "subject_sha": self.base,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "outcome": "approve",
                    "finding_count": 0,
                    "evidence": ["https://example.invalid/review"],
                }
            ],
        )
        with self.assertRaisesRegex(agent_attribution.AttributionError, "stale"):
            agent_attribution.validate_work_item(stale)

        event = {
            "id": "validation-a",
            "kind": "validation",
            "participant_ref": "author",
            "subject_sha": head,
            "timestamp": "2026-01-01T00:00:00Z",
            "outcome": "pass",
            "evidence": ["https://example.invalid/run"],
        }
        duplicate = copy.deepcopy(event)
        duplicate["id"] = "validation-b"
        record = self.work_item(head, [event, duplicate])
        with self.assertRaisesRegex(agent_attribution.AttributionError, "duplicate evidence"):
            agent_attribution.validate_work_item(record)

        claimed = self.work_item(head)
        claimed["participants"][0]["agent"]["observed"] = {
            "identity": "unverified-model",
            "attestation": "none",
            "evidence": [],
        }
        with self.assertRaisesRegex(agent_attribution.AttributionError, "requires attestation"):
            agent_attribution.validate_work_item(claimed)

        reordered = copy.deepcopy(event)
        reordered["id"] = "validation-c"
        event["evidence"] = ["https://example.invalid/a", "https://example.invalid/b"]
        reordered["evidence"] = list(reversed(event["evidence"]))
        with self.assertRaisesRegex(agent_attribution.AttributionError, "duplicate evidence"):
            agent_attribution.validate_work_item(self.work_item(head, [event, reordered]))

    def test_report_uses_reachable_head_only_and_separates_merge_activity(self):
        attributed = self.attributed_commit()
        git(self.repo, "checkout", "-q", "-b", "private-local")
        (self.repo / "private.txt").write_text("must not count\n", encoding="utf-8")
        git(self.repo, "add", "private.txt")
        git(self.repo, "commit", "-q", "-m", "private local commit")
        git(self.repo, "checkout", "-q", "main")

        git(self.repo, "checkout", "-q", "-b", "feature", self.base)
        (self.repo / "feature.txt").write_text("feature\n", encoding="utf-8")
        git(self.repo, "add", "feature.txt")
        git(self.repo, "commit", "-q", "-m", "feature")
        git(self.repo, "checkout", "-q", "main")
        git(self.repo, "merge", "-q", "--no-ff", "feature", "-m", "merge feature")
        selected = git(self.repo, "rev-parse", "HEAD")

        records = self.root / "records"
        records.mkdir()
        record = self.work_item(
            attributed,
            [
                {
                    "id": "author",
                    "kind": "author",
                    "participant_ref": "author",
                    "subject_sha": attributed,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "outcome": "authored",
                    "evidence": ["https://example.invalid/commit"],
                },
                {
                    "id": "review",
                    "kind": "review",
                    "participant_ref": "author",
                    "subject_sha": attributed,
                    "timestamp": "2026-01-01T00:01:00Z",
                    "outcome": "approve",
                    "finding_count": "UNKNOWN",
                    "evidence": ["https://example.invalid/review"],
                },
                {
                    "id": "integration",
                    "kind": "integration",
                    "participant_ref": "author",
                    "subject_sha": attributed,
                    "timestamp": "2026-01-01T00:02:00Z",
                    "outcome": "merged",
                    "evidence": ["https://example.invalid/pr"],
                },
            ],
        )
        (records / "fixture.json").write_text(json.dumps(record), encoding="utf-8")
        report = agent_attribution.build_report(
            self.repo, selected, self.accounts, records
        )
        expected_reachable = int(git(self.repo, "rev-list", "--count", selected))
        all_refs = int(git(self.repo, "rev-list", "--all", "--count"))
        self.assertGreater(all_refs, expected_reachable)
        self.assertEqual(report["source"]["reachable_commits"], expected_reachable)
        self.assertEqual(report["source"]["merge_commits"], 1)
        self.assertEqual(report["work_item_evidence"]["explicitly_accepted"], 1)
        self.assertEqual(report["work_item_evidence"]["review_findings_known_total"], 0)
        self.assertEqual(
            report["work_item_evidence"]["review_events_with_unknown_finding_count"], 1
        )
        self.assertEqual(report["unavailable_metrics"]["ability_score"], "UNKNOWN")
        self.assertEqual(
            report["git_activity"]["structured_commit_attribution"][0]["sha"],
            attributed,
        )
        details = report["work_item_evidence"]["record_details"]
        self.assertEqual(details[0]["record"]["events"][2]["outcome"], "merged")
        self.assertRegex(details[0]["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(
            report["provenance_inputs"]["platform_accounts"]["sha256"],
            r"^[0-9a-f]{64}$",
        )

        outside = copy.deepcopy(record)
        outside["source"]["base"] = "e" * 40
        (records / "fixture.json").write_text(json.dumps(outside), encoding="utf-8")
        with self.assertRaisesRegex(agent_attribution.AttributionError, "base is not reachable"):
            agent_attribution.build_report(self.repo, selected, self.accounts, records)

        outside = copy.deepcopy(record)
        outside["events"][0]["subject_sha"] = "f" * 40
        (records / "fixture.json").write_text(json.dumps(outside), encoding="utf-8")
        with self.assertRaisesRegex(agent_attribution.AttributionError, "outside work-item"):
            agent_attribution.build_report(self.repo, selected, self.accounts, records)

    def test_legacy_requested_label_is_raw_claim_not_observed_identity(self):
        (self.repo / "legacy.txt").write_text("legacy\n", encoding="utf-8")
        git(self.repo, "add", "legacy.txt")
        git(
            self.repo,
            "commit",
            "-q",
            "-m",
            "legacy\n\nRequested-Model: Sol\nObserved-Runtime: unattested",
        )
        report = agent_attribution.build_report(
            self.repo, "HEAD", self.accounts, self.root / "missing-records"
        )
        self.assertEqual(
            report["git_activity"]["legacy_requested_labels"], {"Requested-Model=Sol": 1}
        )
        self.assertEqual(report["git_activity"]["structured_provenance_commits"], 0)
        self.assertEqual(report["work_item_evidence"]["explicitly_accepted"], 0)

    def test_cli_failure_does_not_write_json_report(self):
        output = self.root / "report.json"
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            result = agent_attribution.main(
                [
                    "--accounts",
                    str(self.accounts),
                    "report",
                    "--repo",
                    str(self.repo),
                    "--source",
                    "missing-ref",
                    "--records-dir",
                    str(self.root / "missing"),
                    "--json-output",
                    str(output),
                ]
            )
        self.assertEqual(result, 2)
        self.assertFalse(output.exists())
        self.assertIn("agent-attribution: error:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
