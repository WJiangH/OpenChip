import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import package_source_snapshot  # noqa: E402


def run_git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()


class SourceSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        run_git(self.repo, "init", "-q")
        run_git(self.repo, "config", "user.name", "Snapshot Test")
        run_git(self.repo, "config", "user.email", "snapshot@example.invalid")

        canonical = self.repo / ".agents" / "skills" / "demo"
        canonical.mkdir(parents=True)
        (canonical / "SKILL.md").write_text("canonical\n", encoding="utf-8")
        mirror = self.repo / ".claude" / "skills" / "demo"
        mirror.mkdir(parents=True)
        os.symlink("../../../.agents/skills/demo/SKILL.md", mirror / "SKILL.md")
        (self.repo / "README.md").write_text("tracked\n", encoding="utf-8")
        run_git(self.repo, "add", ".")
        run_git(self.repo, "commit", "-q", "-m", "fixture")
        self.source_sha = run_git(self.repo, "rev-parse", "HEAD")
        (self.repo / "private-local-note.txt").write_text("untracked\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def create(self, directory_name="output"):
        output = self.root / directory_name
        manifest = package_source_snapshot.create_snapshot(
            repo=self.repo,
            source_sha=self.source_sha,
            repository="example/OpenChip",
            run_id="1234",
            run_attempt="2",
            output_dir=output,
        )
        return output, manifest

    def test_packages_exact_tracked_tree_and_preserves_symlink(self):
        output, manifest = self.create()
        archive = output / manifest["archive"]["filename"]
        prefix = "openchip-source-{}/".format(self.source_sha)

        with tarfile.open(archive) as stream:
            names = stream.getnames()
            self.assertIn(prefix + "README.md", names)
            self.assertNotIn(prefix + "private-local-note.txt", names)
            link = stream.getmember(prefix + ".claude/skills/demo/SKILL.md")
            self.assertTrue(link.issym())
            self.assertEqual(link.linkname, "../../../.agents/skills/demo/SKILL.md")

        entries = {entry["path"]: entry for entry in manifest["tracked_entries"]}
        self.assertEqual(entries[".claude/skills/demo/SKILL.md"]["mode"], "120000")
        self.assertEqual(manifest["source"]["commit"], self.source_sha)
        self.assertEqual(manifest["ci"], {"run_attempt": "2", "run_id": "1234"})

    def test_manifest_and_checksums_match_bytes(self):
        output, manifest = self.create()
        manifest_bytes = (output / "manifest.json").read_bytes()
        parsed = json.loads(manifest_bytes)
        self.assertEqual(parsed, manifest)

        expected = {
            manifest["archive"]["filename"]: manifest["archive"]["sha256"],
            "manifest.json": hashlib.sha256(manifest_bytes).hexdigest(),
        }
        actual = {}
        for line in (output / "SHA256SUMS").read_text(encoding="ascii").splitlines():
            digest, filename = line.split("  ", 1)
            actual[filename] = digest
        self.assertEqual(actual, expected)

    def test_same_commit_and_identity_produce_identical_outputs(self):
        first, _ = self.create("first")
        second, _ = self.create("second")
        first_files = {path.name: path.read_bytes() for path in first.iterdir()}
        second_files = {path.name: path.read_bytes() for path in second.iterdir()}
        self.assertEqual(first_files, second_files)

    def test_rejects_head_mismatch_invalid_identity_and_nonempty_output(self):
        (self.repo / "README.md").write_text("second commit\n", encoding="utf-8")
        run_git(self.repo, "add", "README.md")
        run_git(self.repo, "commit", "-q", "-m", "second")
        with self.assertRaisesRegex(package_source_snapshot.SnapshotError, "does not match"):
            self.create()

        current = run_git(self.repo, "rev-parse", "HEAD")
        invalid_cases = (
            {"source_sha": current.upper()},
            {"source_sha": current[:12]},
            {"run_id": "pull-request"},
            {"run_attempt": "²"},
            {"repository": "owner/repo with space"},
        )
        defaults = {
            "repo": self.repo,
            "source_sha": current,
            "repository": "example/OpenChip",
            "run_id": "1234",
            "run_attempt": "2",
            "output_dir": self.root / "unused",
        }
        for index, override in enumerate(invalid_cases):
            arguments = dict(defaults)
            arguments.update(override)
            arguments["output_dir"] = self.root / "invalid-{}".format(index)
            with self.subTest(override=override):
                with self.assertRaises(package_source_snapshot.SnapshotError):
                    package_source_snapshot.create_snapshot(**arguments)

        occupied = self.root / "occupied"
        occupied.mkdir()
        (occupied / "stale").write_text("stale\n", encoding="utf-8")
        arguments = dict(defaults)
        arguments["output_dir"] = occupied
        with self.assertRaisesRegex(package_source_snapshot.SnapshotError, "not empty"):
            package_source_snapshot.create_snapshot(**arguments)

    def test_cli_reports_mismatch_without_creating_archive(self):
        stderr = io.StringIO()
        output = self.root / "cli-output"
        with mock.patch("sys.stderr", stderr):
            result = package_source_snapshot.main(
                [
                    "--repo",
                    str(self.repo),
                    "--source-sha",
                    "0" * 40,
                    "--repository",
                    "example/OpenChip",
                    "--run-id",
                    "1",
                    "--run-attempt",
                    "1",
                    "--output-dir",
                    str(output),
                ]
            )
        self.assertEqual(result, 2)
        self.assertFalse(output.exists())
        self.assertIn("source-snapshot: error:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
