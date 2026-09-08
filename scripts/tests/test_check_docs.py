from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_docs


class DocumentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.names = []

    def put(self, name, text=""):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        self.names.append(name)
        return path

    def check(self):
        return check_docs.check(self.root, self.names)[0]

    def test_public_links_and_domain_evidence_survive(self):
        self.put("AGENTS.md")
        self.put("README.md", '[spec](hw/unit/SPEC.md#contract) [folder](hw/unit/)\n[ref]: <hw/unit/SPEC.md>\n')
        self.put("hw/unit/SPEC.md")
        self.put("sw/reports/firmware-footprint.md")
        self.put("hw/ip/upstream/AGENTS.md", "[native path](missing)")
        self.put("vendor/project/notes.md", "[native path](missing)")
        self.assertEqual(self.check(), [])

    def test_missing_and_untracked_targets_fail_but_examples_do_not(self):
        self.put("README.md", '[lost](missing.md) [private](private.md)\n```md\n[example](example.md)\n```\n')
        (self.root / "private.md").write_text("local only")
        errors = self.check()
        self.assertEqual(len(errors), 2)
        self.assertTrue(all("missing public link target" in e for e in errors))

    def test_duplicate_constitution_and_task_diary_fail(self):
        self.put("docs/AGENTS.md")
        self.put("hw/unit/task-001.md")
        errors = self.check()
        self.assertEqual(len(errors), 2)
        self.assertIn("duplicate constitution", errors[0])
        self.assertIn("reviewed domain/report exception", errors[1])

    def test_reference_links_and_escaped_paths(self):
        self.put("README.md", '[ok](<docs/a b.md>)\n[missing]: docs/no.md\n[web](https://example.org/no)\n')
        self.put("docs/a b.md")
        self.assertEqual(len(self.check()), 1)
        self.assertIn("docs/no.md", self.check()[0])

    def test_mirrors_and_real_sync_without_empty_references(self):
        self.put(".agents/skills/one/SKILL.md")
        self.put(".agents/skills/two/SKILL.md")
        self.put(".agents/skills/two/references/rule.md")
        for role in ("one", "two"):
            self.put(f".claude/agents/{role}.md", f"Read .agents/skills/{role}/SKILL.md")
        tool = self.root / "tools/agents.sh"
        tool.parent.mkdir()
        shutil.copyfile(Path(__file__).resolve().parents[2] / "tools/agents.sh", tool)
        # Exercise the old dangling mirror cleanup as well as new creation.
        old = self.root / ".claude/skills/one/references"
        old.parent.mkdir(parents=True)
        old.symlink_to("../../../.agents/skills/one/references")
        subprocess.run(["bash", str(tool), "sync", "--all"], check=True, stdout=subprocess.PIPE)
        self.assertFalse(old.is_symlink())
        for role in ("one", "two"):
            self.names.append(f".claude/skills/{role}/SKILL.md")
        self.names.append(".claude/skills/two/references")
        self.assertEqual(self.check(), [])
        mirror = self.root / ".claude/skills/one/SKILL.md"
        mirror.unlink()
        mirror.write_text("duplicated role body")
        self.assertTrue(any("expected canonical symlink" in e for e in self.check()))


if __name__ == "__main__":
    unittest.main()
