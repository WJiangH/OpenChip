#!/usr/bin/env python3
"""CPU-only adversarial build-metadata and owned-child timeout regression controls."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent


def sibling(name):
    spec = importlib.util.spec_from_file_location('coralnpu_' + name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = sibling('build')
inspector = sibling('inspect')


class MetadataControls(unittest.TestCase):
    def setUp(self):
        # Synthetic identities test required structure only; no tool identity acceptance.
        self.info = {'schema_version': 1, 'source_sha256': build.source_hashes(),
                     'toolchain': {'executables_sha256': {name: '0' * 64 for name in build.TOOLS},
                                   'builtin_headers_sha256': {'stdint.h': '0' * 64, 'stddef.h': '0' * 64},
                                   'gcc_version': 'SYNTHETIC_TEST_ONLY'},
                     'flags': list(build.FLAGS), 'commands': build.expected_commands()}

    def test_complete_structure(self):
        inspector.validate_build_info(self.info)

    def test_missing_or_changed_binding_is_rejected(self):
        mutations = {
            'empty_sources': lambda x: x.update(source_sha256={}),
            'omitted_source': lambda x: x['source_sha256'].pop('kernel.S'),
            'changed_source': lambda x: x['source_sha256'].update({'kernel.S': '0' * 64}),
            'empty_toolchain': lambda x: x.update(toolchain={}),
            'omitted_tool': lambda x: x['toolchain']['executables_sha256'].pop('cc1'),
            'malformed_tool': lambda x: x['toolchain']['executables_sha256'].update(gcc='invalid'),
            'empty_headers': lambda x: x['toolchain'].update(builtin_headers_sha256={}),
            'omitted_header': lambda x: x['toolchain']['builtin_headers_sha256'].pop('stddef.h'),
            'empty_version': lambda x: x['toolchain'].update(gcc_version=''),
            'empty_flags': lambda x: x.update(flags=[]),
            'changed_ISA': lambda x: x['flags'].__setitem__(0, '-march=rv32i'),
            'empty_commands': lambda x: x.update(commands=[]),
            'changed_compile_flags': lambda x: x['commands'][6]['argv'].__setitem__(1, '-march=rv32i'),
        }
        for name, mutation in mutations.items():
            with self.subTest(case=name):
                candidate = copy.deepcopy(self.info)
                mutation(candidate)
                with self.assertRaises(ValueError):
                    inspector.validate_build_info(candidate)

    def test_timeout_retains_diagnostic_and_reaps_owned_child(self):
        with tempfile.TemporaryDirectory(prefix='coralnpu-timeout-control-') as scratch:
            root = Path(scratch)
            bins = root / 'toolchain' / 'bin'
            bins.mkdir(parents=True)
            for tool in ('gcc', 'as', 'ld', 'objdump', 'readelf'):
                path = bins / (build.PREFIX + tool)
                path.write_text('#!/bin/sh\nprintf "MOCK_COMPILER_DIAGNOSTIC\\n"\nsleep 30\n')
                path.chmod(0o755)
            out = root / 'output'
            started = time.monotonic()
            result = subprocess.run([sys.executable, str(ROOT / 'build.py'), '--toolchain-root',
                                     str(bins.parent), '--output', str(out), '--timeout', '0.5'],
                                    capture_output=True, text=True, timeout=5,
                                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
            self.assertNotEqual(result.returncode, 0)
            self.assertLess(time.monotonic() - started, 5)
            receipt = json.loads((out / 'diagnostics' / 'receipt.json').read_text())
            self.assertEqual(receipt['classification'], 'TIMEOUT')
            self.assertEqual(receipt['stage'], 'compiler-version')
            event = receipt['events'][-1]
            self.assertEqual(event['classification'], 'TIMEOUT')
            self.assertTrue(event['child_reaped'])
            self.assertEqual(event['exit_code'], -9)
            self.assertEqual(event['termination'], 'OWNED_PROCESS_GROUP_SIGKILL_SENT')
            self.assertIn('MOCK_COMPILER_DIAGNOSTIC', (out / 'diagnostics' / event['log']).read_text())
            self.assertFalse((out / 'manifest.json').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
