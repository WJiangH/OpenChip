"""Launcher contract only; real wrapper/runner validation is private evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('environment', Path(__file__).parents[1] / 'environment.py')
environment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(environment)


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Path(self.temp.name)
        self.adapter = self.store / 'adapter.py'
        self.profile = self.store / 'profile.json'

    def configure(self, code, **changes):
        self.adapter.write_text(code)
        profile = dict(schema_version=1, id='unit', owner='unit test',
                       adapter='adapter.py', timeout_seconds=2,
                       adapter_sha256=hashlib.sha256(self.adapter.read_bytes()).hexdigest())
        profile.update(changes)
        self.profile.write_text(json.dumps(profile))

    def test_zero_exit_without_result_is_not_readiness(self):
        self.configure('pass\n')
        status, receipt = environment.check(self.store, self.profile)
        self.assertEqual(status, 'PROBE_FAILED')
        self.assertTrue((receipt / 'launcher.json').is_file())

    def test_stale_adapter_does_not_execute(self):
        self.configure('raise RuntimeError("must not run")\n', adapter_sha256='0' * 64)
        status, receipt = environment.check(self.store, self.profile)
        self.assertEqual(status, 'STALE_IDENTITY')
        self.assertFalse((receipt / 'adapter.log').exists())

    def test_dut_result_cannot_be_readiness(self):
        self.configure('import pathlib,sys\npathlib.Path(sys.argv[2],"result.json").write_text(\'{"status":"READY_NO_DUT","dut_executed":true}\')\n')
        self.assertEqual(environment.check(self.store, self.profile)[0], 'PROBE_FAILED')

    def test_classifications_and_snapshot(self):
        for status in ['READY_NO_DUT','NO_ACCESS','MISSING_LIBRARY','STALE_IDENTITY']:
            with self.subTest(status=status):
                self.configure('import pathlib,sys\npathlib.Path(sys.argv[2],"result.json").write_text(\'{"status":"'+status+'","dut_executed":false}\')\n')
                observed, receipt = environment.check(self.store, self.profile)
                self.assertEqual(observed, status)
                self.assertEqual((receipt/'adapter.py').read_bytes(), self.adapter.read_bytes())

    def test_timeout_and_path_escape(self):
        self.configure('import time\ntime.sleep(4)\n', timeout_seconds=1)
        status, receipt = environment.check(self.store, self.profile)
        self.assertEqual(status, 'TIMEOUT')
        self.assertEqual(json.loads((receipt/'launcher.json').read_text())['remote_completion'], 'unconfirmed')
        self.configure('pass\n', adapter='../escape.py')
        self.assertEqual(environment.check(self.store, self.profile)[0], 'NOT_CONFIGURED')

    def test_missing_profile_and_invalid_budget(self):
        self.assertEqual(environment.check(self.store, self.profile)[0], 'NOT_CONFIGURED')
        self.configure('pass\n', timeout_seconds=61)
        self.assertEqual(environment.check(self.store, self.profile)[0], 'NOT_CONFIGURED')


if __name__ == '__main__':
    unittest.main()
