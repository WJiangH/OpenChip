"""Harmless local controls for S01-S05/S12; no live orchestration claim."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ENTRY = Path(__file__).resolve().parents[1] / 'orchestration_ledger.py'
spec = importlib.util.spec_from_file_location('ledger', ENTRY)
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'ledger.sqlite'
        ledger.initialize(self.db)
        self.serial = 0
        self.ident = {'work_item': 'sample-work', 'owner': 'author', 'candidate': 'a' * 40,
                      'dependencies': {'spec': 'b' * 64}, 'attempt': 1}
        self.proc = {'kind': 'process', 'host': 'test-host', 'pid': 123,
                     'start_time': '2026-01-01T00:00:00Z', 'command_sha256': 'c' * 64,
                     'cwd': str(self.root), 'nonce': 'owned-test-nonce'}

    def file(self, value):
        self.serial += 1
        p = self.root / ('artifact-%d.json' % self.serial)
        p.write_text(json.dumps(value))
        return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}

    def request(self, ident=None):
        ident = copy.deepcopy(ident or self.ident)
        grant = self.file({'identity': ident, 'action': 'dispatch', 'authority': 'test-only-grant'})
        return {'identity': ident, 'grant': grant}

    def call(self, op, req, revision=None):
        if revision is None:
            revision = ledger.inspect(self.db)['revision']
        return ledger.mutate(self.db, op, req, revision)

    def admit(self):
        return self.call('admit', self.request())['record']['binding']

    def attach(self, binding):
        body = {'binding': binding, 'handle': self.proc, 'observation': 'HANDLE_RETURNED'}
        return self.call('attach', {'binding': binding, 'handle': self.proc, 'evidence': self.file(body)})

    def receipt(self, binding, result='PASS'):
        return {'binding': binding, 'handle': self.proc, 'disposition': 'EXITED', 'exit_code': 0,
                'result': result, 'checked_scope': ['owned harmless control'],
                'artifacts': [self.file({'observed': 'synthetic-check-result'})]}

    def finish(self, binding, body):
        return self.call('finish', {'binding': binding, 'handle': self.proc, 'evidence': self.file(body)})

    def assert_rejected_without_mutation(self, op, req):
        before = ledger.inspect(self.db)
        with self.assertRaises((ledger.Rejected, OSError, ValueError)):
            self.call(op, req)
        self.assertEqual(ledger.inspect(self.db), before)

    def test_s01_two_concurrent_admissions_and_changed_attempt_hold(self):
        req = Path(self.file(self.request())['path'])
        # Both real CLI processes reach a barrier before either enters SQLite.
        code = '''import pathlib,subprocess,sys,time
ready,go,entry,db,request=sys.argv[1:]
pathlib.Path(ready).touch()
end=time.monotonic()+5
while not pathlib.Path(go).exists():
 if time.monotonic()>end: raise SystemExit(9)
 time.sleep(.01)
sys.path.insert(0,str(pathlib.Path(entry).parent))
import orchestration_ledger
sys.argv=[entry,'--ledger',db,'admit',request,'--expected-revision','0']
raise SystemExit(orchestration_ledger.main())
'''
        processes = []
        try:
            for index in range(2):
                processes.append(subprocess.Popen([sys.executable, '-c', code,
                    str(self.root / str(index)), str(self.root / 'go'), str(ENTRY), str(self.db), str(req)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            end = time.monotonic() + 5
            while not all((self.root / str(i)).exists() for i in range(2)):
                self.assertLess(time.monotonic(), end)
                time.sleep(.01)
            (self.root / 'go').touch()
            outputs = [p.communicate(timeout=10) for p in processes]
            self.assertEqual(sorted(p.returncode for p in processes), [0, 2], outputs)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate()
        state = ledger.inspect(self.db)
        self.assertEqual(state['revision'], 1)
        self.assertEqual(len(state['runs']), 1)
        for field, value in [('attempt', 2), ('candidate', 'd'*40), ('owner', 'other-author')]:
            ident = dict(self.ident, **{field: value})
            self.assert_rejected_without_mutation('admit', self.request(ident))

    def test_s02_restart_unknown_missing_store_and_actual_ack(self):
        binding = self.admit()
        state = ledger.inspect(self.db)
        self.assertEqual(state['runs'][0]['status'], 'UNKNOWN')
        self.assertIsNone(state['runs'][0]['handle'])
        self.assert_rejected_without_mutation('admit', self.request(dict(self.ident, attempt=2)))
        with self.assertRaises(ledger.Rejected):
            ledger.inspect(self.root / 'missing.sqlite')
        self.assertFalse((self.root / 'missing.sqlite').exists())
        with self.assertRaises(FileExistsError):
            ledger.initialize(self.db)
        self.assert_rejected_without_mutation('finish', {
            'binding': binding, 'handle': None, 'evidence': self.file(self.receipt(binding))})
        attached = self.attach(binding)
        self.assertEqual(attached['record']['status'], 'ACKNOWLEDGED')
        self.assert_rejected_without_mutation('admit', self.request(dict(self.ident, attempt=2)))

    def test_s03_expired_worker_and_pid_reuse_do_not_release(self):
        binding = self.admit()
        self.attach(binding)
        obs = {'binding': binding, 'handle': self.proc, 'observation': 'UNKNOWN'}
        self.call('observe', dict(obs, evidence=self.file(obs)))
        self.assert_rejected_without_mutation('admit', self.request(dict(self.ident, attempt=2)))
        for field, value in [('start_time', 'later'), ('nonce', 'new'), ('host', 'other'), ('pid', 456)]:
            body = self.receipt(binding)
            body['handle'] = dict(self.proc, **{field: value})
            self.assert_rejected_without_mutation('finish', {
                'binding': binding, 'handle': self.proc, 'evidence': self.file(body)})
        body = self.receipt(binding)
        body['disposition'] = 'LEASE_EXPIRED'
        self.assert_rejected_without_mutation('finish', {
            'binding': binding, 'handle': self.proc, 'evidence': self.file(body)})

    def test_s04_stale_ledger_revision_not_state_atomicity(self):
        sentinel = self.root / 'STATE.md'
        sentinel.write_text('root-owned-state-revision-7\n')
        self.admit()
        other = self.request(dict(self.ident, work_item='independent-item'))
        with self.assertRaisesRegex(ledger.Rejected, 'stale ledger revision'):
            self.call('admit', other, revision=0)
        self.assertEqual(ledger.inspect(self.db)['revision'], 1)
        self.assertEqual(sentinel.read_text(), 'root-owned-state-revision-7\n')

    def test_s05_grant_required_fields_and_hashes(self):
        for bad in [{}, None, {'identity': self.ident},
                    {'identity': self.ident, 'authority': '', 'action': 'dispatch'},
                    {'identity': dict(self.ident, attempt=True), 'authority': 'x', 'action': 'dispatch'},
                    {'identity': dict(self.ident, candidate='d'*40), 'authority': 'x', 'action': 'dispatch'}]:
            with self.subTest(grant=bad):
                self.assert_rejected_without_mutation('admit', {'identity': self.ident, 'grant': self.file(bad)})
        req = self.request()
        Path(req['grant']['path']).write_text('{}')
        self.assert_rejected_without_mutation('admit', req)

    def test_s05_completion_missing_null_wrong_binding_and_failed_exit(self):
        binding = self.admit()
        self.attach(binding)
        good = self.receipt(binding)
        for field in good:
            for null in (False, True):
                body = copy.deepcopy(good)
                if null:
                    body[field] = None
                else:
                    del body[field]
                with self.subTest(field=field, null=null):
                    self.assert_rejected_without_mutation('finish', {
                        'binding': binding, 'handle': self.proc, 'evidence': self.file(body)})
        for field in binding:
            body = copy.deepcopy(good)
            body['binding'][field] = 'wrong-identity'
            self.assert_rejected_without_mutation('finish', {
                'binding': binding, 'handle': self.proc, 'evidence': self.file(body)})
        body = copy.deepcopy(good)
        body['exit_code'] = 1
        self.assert_rejected_without_mutation('finish', {
            'binding': binding, 'handle': self.proc, 'evidence': self.file(body)})
        body['result'] = 'FAIL'
        result = self.finish(binding, body)
        self.assertEqual(result['record']['status'], 'FAIL')
        self.assertEqual(ledger.inspect(self.db)['events'][-1]['evidence_body']['result'], 'FAIL')

    def test_s05_artifact_substitution_and_exit_zero_without_checker(self):
        binding = self.admit()
        self.attach(binding)
        body = self.receipt(binding)
        Path(body['artifacts'][0]['path']).write_text('substituted')
        self.assert_rejected_without_mutation('finish', {
            'binding': binding, 'handle': self.proc, 'evidence': self.file(body)})
        body = self.receipt(binding)
        body['result'] = 'EXIT_ZERO'
        self.assert_rejected_without_mutation('finish', {
            'binding': binding, 'handle': self.proc, 'evidence': self.file(body)})

    def test_s12_clock_jump_and_late_old_epoch_receipt(self):
        binding = self.admit()
        self.attach(binding)
        with mock.patch.object(ledger, 'datetime') as clock:
            clock.now.return_value.isoformat.return_value = '1900-01-01T00:00:00Z'
            obs = {'binding': binding, 'handle': self.proc, 'observation': 'UNKNOWN'}
            self.call('observe', dict(obs, evidence=self.file(obs)))
        self.assert_rejected_without_mutation('admit', self.request(dict(self.ident, attempt=2)))
        self.finish(binding, self.receipt(binding))
        new = self.call('admit', self.request(dict(self.ident, attempt=2)))['record']['binding']
        self.assertGreater(new['epoch'], binding['epoch'])
        self.assertNotEqual(new['run_id'], binding['run_id'])
        self.assert_rejected_without_mutation('finish', {
            'binding': binding, 'handle': self.proc, 'evidence': self.file(self.receipt(binding))})
        forged = dict(binding, epoch=new['epoch'])
        self.assert_rejected_without_mutation('attach', {
            'binding': forged, 'handle': self.proc, 'evidence': self.file({})})
        self.assertEqual(ledger.inspect(self.db)['runs'][1]['status'], 'UNKNOWN')

    def test_worker_completion_no_fabricated_exit_and_external_job_hold(self):
        binding = self.admit()
        worker = {'kind': 'worker', 'host': 'local', 'id': 'native-worker-id'}
        body = {'binding': binding, 'handle': worker, 'observation': 'HANDLE_RETURNED'}
        self.call('attach', {'binding': binding, 'handle': worker, 'evidence': self.file(body)})
        completion = dict(self.receipt(binding), handle=worker, disposition='COMPLETED',
                          exit_code=None, owned_jobs=[])
        for bad in [dict(completion, exit_code=0), dict(completion, owned_jobs=None),
                    {k: v for k, v in completion.items() if k != 'owned_jobs'}]:
            self.assert_rejected_without_mutation('finish', {
                'binding': binding, 'handle': worker, 'evidence': self.file(bad)})
        for state in ('LIVE', 'UNKNOWN'):
            observation = {'binding': binding, 'handle': self.proc, 'disposition': state, 'exit_code': None}
            bad = dict(completion, owned_jobs=[{'handle': self.proc, 'evidence': self.file(observation)}])
            self.assert_rejected_without_mutation('finish', {
                'binding': binding, 'handle': worker, 'evidence': self.file(bad)})
            self.assert_rejected_without_mutation('admit', self.request(dict(self.ident, attempt=2)))
        observation = {'binding': binding, 'handle': self.proc, 'disposition': 'EXITED', 'exit_code': 1}
        completion['owned_jobs'] = [{'handle': self.proc, 'evidence': self.file(observation)}]
        completion['result'] = 'FAIL'
        result = self.call('finish', {'binding': binding, 'handle': worker,
                                      'evidence': self.file(completion)})
        self.assertEqual(result['record']['status'], 'FAIL')
        self.assertIsNone(result['event']['evidence_body']['exit_code'])

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(ledger.Rejected):
            ledger.decode('{"epoch":1,"epoch":2}')


if __name__ == '__main__':
    unittest.main()
