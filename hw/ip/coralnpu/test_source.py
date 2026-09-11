"""CPU-only integrity controls. No upstream build or DUT execution."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('coral_source', Path(__file__).with_name('source.py'))
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tree = self.root / 'source'
        self.tree.mkdir()
        (self.tree / 'file').write_bytes(b'original\n')
        (self.tree / 'bin').write_bytes(b'#!/bin/sh\nexit 0\n')
        (self.tree / 'bin').chmod(0o755)
        (self.tree / 'nested').mkdir()
        (self.tree / 'nested' / 'link').symlink_to('../file')
        self.pin = {**source.PIN, 'tree': source.tree_hash(self.tree)[0].hex(), 'tracked_blobs': 3}
        self.patcher = patch.object(source, 'PIN', self.pin)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_tree_matches_independent_git(self):
        repo = self.root / 'git'
        env = {**os.environ, 'GIT_DIR': str(repo), 'GIT_WORK_TREE': str(self.tree)}
        subprocess.run(['git', 'init', '--bare', str(repo)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['git', 'add', '--all'], env=env, check=True)
        actual = subprocess.check_output(['git', 'write-tree'], env=env).decode().strip()
        self.assertEqual(actual, source.verify(self.tree)['tree'])

    def test_changed_byte_rejected(self):
        (self.tree / 'file').write_bytes(b'changed\n')
        with self.assertRaisesRegex(ValueError, 'source mismatch'):
            source.verify(self.tree)

    def test_missing_file_rejected(self):
        (self.tree / 'file').unlink()
        with self.assertRaises(ValueError):
            source.verify(self.tree)

    def test_extra_config_rejected(self):
        (self.tree / '.bazelrc.user').write_text('build --compilation_mode=dbg\n')
        with self.assertRaises(ValueError):
            source.verify(self.tree)

    def test_executable_mode_rejected(self):
        (self.tree / 'bin').chmod(0o644)
        with self.assertRaises(ValueError):
            source.verify(self.tree)

    def test_link_target_rejected(self):
        (self.tree / 'nested' / 'link').unlink()
        (self.tree / 'nested' / 'link').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):
            source.verify(self.tree)

    def test_symlink_source_root_rejected(self):
        root_link = self.root / 'alias'
        root_link.symlink_to(self.tree, target_is_directory=True)
        with self.assertRaises(ValueError):
            source.verify(root_link)

    def test_non_linux_prevents_fetch(self):
        with patch.object(source.platform, 'system', return_value='Darwin'):
            with self.assertRaisesRegex(ValueError, 'Linux is required'):
                source.fetch(argparse.Namespace(dest=self.root / 'new', archive=None))
        self.assertFalse((self.root / 'new').exists())

    def test_case_insensitive_filesystem_rejected(self):
        original = Path.exists
        def exists(path):
            return True if path.name == 'A' else original(path)
        with patch.object(source.platform, 'system', return_value='Linux'), patch.object(Path, 'exists', exists):
            with self.assertRaisesRegex(ValueError, 'case-insensitive'):
                source.fetch(argparse.Namespace(dest=self.root / 'new', archive=None))
        self.assertFalse((self.root / 'new').exists())

    def test_existing_destination_preserved(self):
        with self.assertRaisesRegex(ValueError, 'destination exists'):
            source.fetch(argparse.Namespace(dest=self.tree, archive=None))
        self.assertEqual((self.tree / 'file').read_bytes(), b'original\n')

    def test_wrong_archive_rejected_before_extraction(self):
        archive = self.root / 'bad.tar'
        archive.write_bytes(b'not a tar')
        destination = self.root / 'extraction'
        destination.mkdir()
        with self.assertRaisesRegex(ValueError, 'archive SHA-256 mismatch'):
            source.unpack(archive, destination)
        self.assertEqual(list(destination.iterdir()), [])

    def test_wrong_bazel_version_prevents_build(self):
        output = self.root / 'build'
        with patch.object(source, 'linux_filesystem'), patch.object(source.subprocess, 'check_output', return_value=b'bazel 1.0\n'):
            with self.assertRaisesRegex(ValueError, 'wrong Bazel'):
                source.build(argparse.Namespace(source=self.tree, output_root=output, timeout=1))
        self.assertFalse(output.exists())

    def test_existing_cache_preserved(self):
        output = self.root / 'build'
        output.mkdir()
        marker = output / 'old'
        marker.write_text('keep')
        with patch.object(source, 'linux_filesystem'):
            with self.assertRaisesRegex(ValueError, 'output root must be new'):
                source.build(argparse.Namespace(source=self.tree, output_root=output, timeout=1))
        self.assertEqual(marker.read_text(), 'keep')

    def test_process_failure_not_success(self):
        with self.assertRaisesRegex(RuntimeError, 'exited 7'):
            source.run(['sh', '-c', 'exit 7'], timeout=1)

    def test_timeout_not_success(self):
        with self.assertRaises(TimeoutError):
            source.run(['sh', '-c', 'sleep 10'], timeout=0.05)

    def test_timeout_kills_term_ignoring_descendant_after_leader_exit(self):
        pidfile = self.root / 'child.pid'
        child = ('import os,signal,time; from pathlib import Path; '
                 'signal.signal(signal.SIGTERM, signal.SIG_IGN); '
                 f'Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(60)')
        parent = ('import subprocess,sys,time; '
                  f'subprocess.Popen([sys.executable,"-c",{child!r}]); time.sleep(60)')
        with self.assertRaises(source.CommandTimeout) as raised:
            source.run([sys.executable, '-c', parent], timeout=0.5)
        result = raised.exception.result
        self.assertTrue(pidfile.is_file())
        self.assertTrue(result['cleanup_needed'])
        self.assertIn(result['group_exit']['state'], ('EXITED', 'ZOMBIES_ONLY'))
        self.assertLess(result['elapsed_seconds'], 14)

    def test_auxiliary_rejects_failed_primary_before_mutation(self):
        build_root = self.root / 'primary'
        build_root.mkdir()
        (build_root / 'receipt.json').write_text(json.dumps({'status': 'BUILD_FAILED', 'source': self.pin}))
        with self.assertRaisesRegex(ValueError, 'completed model build receipt'):
            source.runtime(argparse.Namespace(build_root=build_root, source=self.tree,
                           output_root=self.root / 'aux', timeout=1))
        self.assertFalse((self.root / 'aux').exists())

    def test_runtime_export_requires_successful_builds(self):
        model_root = self.root / 'model'
        runtime_root = self.root / 'runtime'
        model_root.mkdir()
        runtime_root.mkdir()
        (model_root / 'receipt.json').write_text(json.dumps({'status': 'BUILD_FAILED'}))
        (runtime_root / 'receipt.json').write_text(json.dumps({'status': 'RUNTIME_BUILD_COMPLETE'}))
        with self.assertRaisesRegex(ValueError, 'both model and runtime'):
            source.export_runtime(argparse.Namespace(build_root=model_root, runtime_root=runtime_root,
                                  source=self.tree, output=self.root / 'runtime.json'))
        self.assertFalse((self.root / 'runtime.json').exists())

    def test_bep_artifact_hash_tracks_bytes(self):
        artifact = self.root / 'artifact'
        artifact.write_bytes(b'generated')
        bep = self.root / 'build.bep.json'
        bep.write_text(json.dumps({'namedSetOfFiles': {'files': [{'uri': artifact.as_uri()}]}}) + '\n')
        self.assertEqual(source.artifacts_from_bep(bep), {str(artifact): hashlib.sha256(b'generated').hexdigest()})

    def test_sha256_bytes(self):
        self.assertEqual(source.digest(self.tree / 'file'), hashlib.sha256(b'original\n').hexdigest())


if __name__ == '__main__':
    unittest.main()
