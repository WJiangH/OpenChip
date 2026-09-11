"""CPU controls for native packaging; no simulator or software executes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import launch

XML = '<testsuites><testsuite tests="1"><testcase name="external_memory_exploratory" classname="cn_exploratory_test" /></testsuite></testsuites>'

class PackagingControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def artifact(self, name, data=b'NO_DUT fixture'):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return {'path': name, 'sha256': launch.sha(p)}

    def test_exact_xml_and_all_false_pass_classes(self):
        path = self.root / 'results.xml'
        path.write_text(XML)
        self.assertEqual(launch.check_results_xml(path)['status'], 'PASS')
        invalid = ['', 'malformed', '<testsuites/>', XML.replace('external_memory_exploratory', 'other'),
                   XML.replace('cn_exploratory_test', 'other'), XML.replace('tests="1"', 'tests="0"'),
                   XML.replace('<testsuite ', '<testsuite failures="1" '),
                   XML.replace(' />', ' /><testcase name="extra" />')]
        for tag in ('failure', 'error', 'skipped'):
            invalid.append(XML.replace(' />', '><' + tag + '/></testcase>'))
        for text in invalid:
            with self.subTest(text=text):
                path.write_text(text)
                self.assertEqual(launch.check_results_xml(path)['status'], 'INVALID_RESULTS_XML')
        path.write_text(XML.replace('external_memory_exploratory', 'external_memory').replace('cn_exploratory_test', 'cn_extmem_test'))
        self.assertEqual(launch.check_results_xml(path, 'positive')['status'], 'PASS')
        self.assertEqual(launch.check_results_xml(path, 'error')['status'], 'INVALID_RESULTS_XML')

    def finish(self, checker='PASS', xml=XML, exit_code=0, status='FINISHED', missing=None):
        for name in launch.required_artifacts('reset'):
            self.artifact(name)
        (self.root / 'verdict.json').write_text(json.dumps({'verdict': checker}))
        (self.root / 'results.xml').write_text(xml)
        if missing:
            (self.root / missing).unlink()
        return launch.finish_receipt(self.root, {'exit_code': exit_code, 'status': status,
                                                'startup_hook_sha256': launch.sha(self.root / 'sitecustomize.py') if (self.root / 'sitecustomize.py').exists() else None}, 'reset')

    def test_complete_result_and_nested_artifact_hashes(self):
        receipt = self.finish()
        self.assertEqual(receipt['semantic_verdict'], 'PASS')
        self.assertIn('epoch-1-recovery/trace.jsonl.gz', receipt['artifact_sha256'])

    def test_checker_fail_survives_process_xml_collection_errors(self):
        receipt = self.finish(checker='FAIL', xml='bad', exit_code=9, status='TIMEOUT',
                              missing='epoch-1-recovery/trace.jsonl.gz')
        self.assertEqual(receipt['semantic_verdict'], 'FAIL')
        self.assertTrue(receipt['missing_artifacts'])
        self.assertEqual(receipt['results_xml_validation']['status'], 'INVALID_RESULTS_XML')

    def test_pass_cannot_override_xml_process_timeout_or_missing_artifact(self):
        for kwargs, verdict in [({'xml': 'bad'}, 'INVALID_RESULTS_XML'),
                                ({'exit_code': 1}, 'PROCESS_FAILED_OR_UNKNOWN'),
                                ({'status': 'TIMEOUT'}, 'PROCESS_FAILED_OR_UNKNOWN'),
                                ({'missing': 'epoch-1-recovery/trace.jsonl.gz'}, 'INCOMPLETE_ARTIFACTS')]:
            self.assertEqual(self.finish(**kwargs)['semantic_verdict'], verdict)

    def software(self):
        symbols = {'rvv_gemv_int8': {'address': 0x20000070, 'size': 100, 'type': 'STT_FUNC'},
                   '_ret': {'address': 0x20020000, 'size': 4},
                   'trap_handler': {'address': 0x20000400, 'size': 64},
                   'fault_instruction': {'address': 0x20000600, 'size': 4}}
        artifact = {'elf': self.artifact('fixture.elf'), 'map': self.artifact('fixture.map'),
                    'entry': 0x20000000, 'symbols': symbols}
        software = {'schema_version': 1, 'contract_version': '0.4', 'upstream': launch.UPSTREAM,
                    'artifacts': {name: artifact for name in ('positive', 'fetch', 'load', 'store', 'unmapped')}}
        path = self.root / 'software.json'
        path.write_text(json.dumps(software))
        review = self.root / 'review.json'
        spec = self.root / 'spec.md'
        spec.write_text('CPU fixture contract')
        review.write_text(json.dumps({'verdict': 'APPROVED', 'software_manifest_sha256': launch.sha(path),
                                     'contract_sha256': launch.sha(spec)}))
        return path, review, spec

    def test_all_13_profiles_map_to_five_variants(self):
        paths = self.software()
        profiles = launch.read(launch.HERE / 'profiles.json')['profiles']
        self.assertEqual(len(profiles), 13)
        with patch.object(launch, 'SPEC_SHA256', launch.sha(paths[2])):
            configs = [launch.make_config(*paths[:2], profile, paths[2]) for profile in profiles]
        self.assertEqual([sum(c['kind'] == kind for c in configs) for kind in ('positive', 'error', 'reset')], [4, 7, 2])
        for config in configs:
            if config['kind'] == 'error':
                self.assertEqual(config['expected_mepc'], 0x200ff000 if config['error_kind'] == 'fetch' else 0x20000600)

    def test_stale_software_review_and_elf_are_rejected(self):
        paths = self.software()
        with patch.object(launch, 'SPEC_SHA256', launch.sha(paths[2])):
            (self.root / 'fixture.elf').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'artifact identity'):
                launch.make_config(*paths[:2], 'POS-S0-P0', paths[2])
            paths = self.software()
            paths[0].write_text(paths[0].read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'review missing'):
                launch.make_config(*paths[:2], 'POS-S0-P0', paths[2])

    def runtime_fixture(self):
        fields = ('python', 'wrapper', 'model', 'runner', 'generated_top', 'parameter_header')
        artifacts = {str(self.root / field): self.artifact(field)['sha256'] for field in fields}
        lib = self.root / 'libs' / 'example.so'
        artifacts[str(lib)] = self.artifact('libs/example.so')['sha256']
        source = dict(status='SOURCE_VERIFIED', tracked_blobs={'NO_DUT': 'synthetic-source-pin'}, **launch.UPSTREAM)
        model = dict(path=str(self.root / 'model'), sha256=artifacts[str(self.root / 'model')],
                     hdl_toplevel='RvvCoreMiniHighmemAxi')
        build = self.root / 'build.json'
        build.write_text(json.dumps({'status': 'BUILD_COMPLETE', 'source': source, 'model': model,
                                     'artifacts_sha256': {model['path']: model['sha256']}}))
        wrapper_build = self.root / 'wrapper-build.json'
        wrapper_build.write_text(json.dumps({'status': 'RUNTIME_BUILD_COMPLETE', 'source': source,
                                            'model_build_receipt_sha256': launch.sha(build),
                                            'artifacts_sha256': {str(self.root / 'wrapper'): artifacts[str(self.root / 'wrapper')]},
                                            'observed_runtime_sha256': {k: v for k, v in artifacts.items() if k != model['path']}}))
        runtime = dict(schema_version=1, upstream=launch.UPSTREAM, top='RvvCoreMiniHighmemAxi',
                       build_receipt={'path': 'build.json', 'sha256': launch.sha(build)},
                       runtime_build_receipt={'path': 'wrapper-build.json', 'sha256': launch.sha(wrapper_build)},
                       artifacts_sha256=artifacts, cwd=str(self.root), library_dir=str(lib.parent),
                       environment={'PYTHONPATH': str(self.root)},
                       **{field: str(self.root / field) for field in fields})
        path = self.root / 'runtime.json'
        path.write_text(json.dumps(runtime))
        return path

    def test_runtime_model_bound_to_successful_build_and_no_cached_identity(self):
        path = self.runtime_fixture()
        self.assertEqual(launch.validate_runtime(path)['model'], str(self.root / 'model'))
        (self.root / 'model').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'runtime artifact mismatch'):
            launch.validate_runtime(path)

    def test_runtime_only_rehash_cannot_replace_any_selected_dependency(self):
        for field in ('model', 'generated_top', 'parameter_header', 'python', 'wrapper', 'runner', 'library'):
            with self.subTest(field=field):
                path = self.runtime_fixture()
                runtime = launch.read(path)
                artifact = self.root / 'libs/example.so' if field == 'library' else Path(runtime[field])
                artifact.write_bytes(b'NO_DUT substituted after producing receipt')
                runtime['artifacts_sha256'][str(artifact)] = launch.sha(artifact)
                path.write_text(json.dumps(runtime))
                with self.assertRaisesRegex(ValueError, 'not bound by build receipt'):
                    launch.validate_runtime(path)

    def test_build_source_top_and_auxiliary_model_receipt_link_are_mandatory(self):
        for mutation in ('source', 'top', 'aux-source', 'aux-link', 'missing-observed', 'conflicting-output'):
            with self.subTest(mutation=mutation):
                path = self.runtime_fixture()
                runtime = launch.read(path)
                build_path, aux_path = self.root / 'build.json', self.root / 'wrapper-build.json'
                build, aux = launch.read(build_path), launch.read(aux_path)
                if mutation == 'source':
                    build['source']['tree'] = 'wrong-source-tree'
                elif mutation == 'top':
                    build['model']['hdl_toplevel'] = 'wrong-top'
                elif mutation == 'aux-source':
                    aux['source']['tracked_blobs'] = {'different': 'source-inventory'}
                elif mutation == 'aux-link':
                    aux['model_build_receipt_sha256'] = 'different-model-receipt'
                elif mutation == 'missing-observed':
                    del aux['observed_runtime_sha256'][runtime['parameter_header']]
                else:
                    aux['artifacts_sha256'][runtime['wrapper']] = 'contradictory-output-digest'
                build_path.write_text(json.dumps(build))
                if mutation in ('source', 'top'):
                    aux['model_build_receipt_sha256'] = launch.sha(build_path)
                aux_path.write_text(json.dumps(aux))
                runtime['build_receipt']['sha256'] = launch.sha(build_path)
                runtime['runtime_build_receipt']['sha256'] = launch.sha(aux_path)
                path.write_text(json.dumps(runtime))
                with self.assertRaises(ValueError):
                    launch.validate_runtime(path)

    def test_auxiliary_wrapper_must_be_a_produced_output(self):
        for produced in ({}, {'/NO_DUT/unrelated-output': 'synthetic-digest'}):
            with self.subTest(produced=produced):
                path = self.runtime_fixture()
                runtime = launch.read(path)
                aux_path = self.root / 'wrapper-build.json'
                auxiliary = launch.read(aux_path)
                auxiliary['artifacts_sha256'] = produced
                aux_path.write_text(json.dumps(auxiliary))
                runtime['runtime_build_receipt']['sha256'] = launch.sha(aux_path)
                path.write_text(json.dumps(runtime))
                with self.assertRaisesRegex(ValueError, 'wrapper missing from auxiliary build outputs'):
                    launch.validate_runtime(path)

    def test_native_launch_binds_config_and_process_receipt(self):
        config = {'kind': 'positive', 'profile': 'POS-S0-P0', 'seed': 42,
                  'elf': str(self.root / 'input.elf')}
        self.artifact('input.elf')
        runtime = dict(python='/fixture/python', wrapper='/fixture/wrapper', model='/fixture/model',
                       top='RvvCoreMiniHighmemAxi', cwd=str(self.root), library_dir='/fixture/libs',
                       artifacts_sha256={}, environment={'PYTHONPATH': '/fixture/packages'})
        output = self.root / 'new-run'
        class Child:
            pid = 12345
            returncode = 0
            def wait(self, timeout):
                return 0
        def start(command, **kwargs):
            self.assertEqual(kwargs['env']['PYTHONPATH'], str(output) + ':/fixture/packages')
            self.assertTrue(kwargs['start_new_session'])
            self.assertIn('--results_xml', command)
            # Pinned rules_hdl wrapper strips ../ before Bazel Rlocation.
            # A plain absolute model instead becomes a workspace-prefixed key.
            model_arg = command[command.index('--model') + 1]
            self.assertEqual(model_arg, '..//fixture/model')
            model_key = model_arg[3:] if model_arg.startswith('../') else 'coralnpu_hw/' + model_arg
            self.assertEqual(model_key, runtime['model'])
            for name in launch.required_artifacts('positive'):
                path = output / name
                if not path.exists():
                    path.write_bytes(b'NO_DUT synthetic artifact')
            (output / 'verdict.json').write_text('{"verdict":"PASS"}')
            (output / 'results.xml').write_text(XML.replace('external_memory_exploratory', 'external_memory').replace('cn_exploratory_test', 'cn_extmem_test'))
            return Child()
        with patch.object(launch.subprocess, 'Popen', side_effect=start):
            receipt = launch.run(runtime, config, output, 2, {'fixture': 'NO_DUT'})
        self.assertEqual(receipt['semantic_verdict'], 'PASS')
        self.assertEqual(receipt['status'], 'FINISHED')
        self.assertEqual(receipt['wall_seconds'], 2)
        self.assertIn('resources', receipt)
        self.assertEqual(launch.read(output / 'config.json')['elf'], str(output / 'program.elf'))

    def test_timeout_kills_only_owned_process_group_and_cannot_pass(self):
        config = {'kind': 'positive', 'profile': 'POS-S0-P0', 'seed': 42,
                  'elf': str(self.root / 'input.elf')}
        self.artifact('input.elf')
        runtime = dict(python='/fixture/python', wrapper='/fixture/wrapper', model='/fixture/model',
                       top='RvvCoreMiniHighmemAxi', cwd=str(self.root), library_dir='/fixture/libs',
                       artifacts_sha256={})
        class Child:
            pid = 12345
            returncode = -9
            calls = 0
            def wait(self, timeout):
                self.calls += 1
                if self.calls <= 2:
                    raise launch.subprocess.TimeoutExpired('owned NO_DUT child', timeout)
                return -9
        with patch.object(launch.subprocess, 'Popen', return_value=Child()), patch.object(launch.os, 'killpg') as kill:
            receipt = launch.run(runtime, config, self.root / 'timeout', 1, {})
        self.assertEqual(receipt['status'], 'TIMEOUT')
        self.assertNotEqual(receipt['semantic_verdict'], 'PASS')
        self.assertEqual(kill.call_args_list[0].args, (12345, launch.signal.SIGTERM))
        self.assertTrue(all(call.args[0] == 12345 for call in kill.call_args_list))

    def test_cleanup_shares_one_deadline_and_unreaped_child_remains_unknown(self):
        clock = [100.0]
        waits = []
        class Child:
            pid = 12345
            returncode = -9  # This attribute alone must not claim reaping.
            def wait(self, timeout):
                waits.append(timeout)
                clock[0] += timeout
                raise launch.subprocess.TimeoutExpired('NO_DUT unreaped child', timeout)
        receipt = {'termination_grace_seconds': 5, 'exit_code': None}
        with patch.object(launch.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(launch.os, 'killpg') as kill:
            launch.cleanup_owned_process(Child(), receipt)
        self.assertEqual(waits, [2, 3])
        self.assertEqual(receipt['cleanup_deadline_monotonic'], 105)
        self.assertEqual(receipt['cleanup_elapsed_seconds'], 5)
        self.assertEqual(receipt['process_exit'], 'UNKNOWN')
        self.assertIsNone(receipt['exit_code'])
        self.assertEqual([c.args[1] for c in kill.call_args_list], [launch.signal.SIGTERM, launch.signal.SIGKILL])

    def test_cleanup_signal_errors_cannot_restart_or_extend_deadline(self):
        clock = [100.0]
        waits = []
        class Child:
            pid = 12345
            def wait(self, timeout):
                waits.append(timeout)
                clock[0] += timeout
                raise launch.subprocess.TimeoutExpired('NO_DUT unreaped child', timeout)
        def failed_signal(pid, sig):
            clock[0] += 1
            raise PermissionError('NO_DUT synthetic signal failure')
        receipt = {'termination_grace_seconds': 5, 'exit_code': None}
        with patch.object(launch.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(launch.os, 'killpg', side_effect=failed_signal):
            launch.cleanup_owned_process(Child(), receipt)
        self.assertEqual(waits, [2, 1])
        self.assertEqual(receipt['cleanup_elapsed_seconds'], 5)
        self.assertEqual(receipt['process_exit'], 'UNKNOWN')

    def test_invalid_wall_bounds_fail_before_output_or_launch(self):
        for bound in (0, -1, 116):
            with self.assertRaisesRegex(ValueError, 'wall seconds'):
                launch.run({}, {}, self.root / 'never-created', bound, {})
        self.assertFalse((self.root / 'never-created').exists())

    def test_native_startup_error_is_recorded_without_checker_pass(self):
        self.artifact('input.elf')
        config = {'kind': 'positive', 'profile': 'POS-S0-P0', 'seed': 42,
                  'elf': str(self.root / 'input.elf')}
        runtime = dict(python='/fixture/python', wrapper='/fixture/wrapper', model='/fixture/model',
                       top='RvvCoreMiniHighmemAxi', cwd=str(self.root), library_dir='/fixture/libs',
                       artifacts_sha256={})
        with patch.object(launch.subprocess, 'Popen', side_effect=OSError('fixture missing interpreter')):
            receipt = launch.run(runtime, config, self.root / 'startup-error', 1, {})
        self.assertEqual(receipt['status'], 'LAUNCH_ERROR')
        self.assertEqual(receipt['process_exit'], 'NOT_STARTED')
        self.assertNotEqual(receipt['semantic_verdict'], 'PASS')

    def test_unconfirmed_process_exit_precedence_preserves_checker_fail(self):
        self.finish()
        receipt = launch.finish_receipt(self.root, {'exit_code': None, 'status': 'LAUNCH_ERROR',
                                                    'process_exit': 'UNKNOWN'}, 'reset')
        self.assertEqual(receipt['semantic_verdict'], 'PROCESS_EXIT_UNKNOWN')
        self.finish(checker='FAIL', missing='epoch-1-recovery/trace.jsonl.gz')
        receipt = launch.finish_receipt(self.root, {'exit_code': None, 'status': 'LAUNCH_ERROR',
                                                    'process_exit': 'UNKNOWN'}, 'reset')
        self.assertEqual(receipt['semantic_verdict'], 'FAIL')

    def test_startup_hook_prioritizes_only_declared_roots_and_preserves_other_paths(self):
        import types
        from unittest.mock import patch
        roots = ['/bound/cocotb-wheel', '/bound/pytest-wheel']
        runtime = {'environment': {'PYTHONPATH': ':'.join(roots)}}
        first = launch.write_startup_hook(self.root, runtime)
        original = ['/native/runfiles/rules_hdl', '/owned/run', roots[0], '/stdlib', roots[1]]
        fake_sys = types.SimpleNamespace(path=list(original))
        with patch.dict('sys.modules', {'sys': fake_sys}):
            exec((self.root / 'sitecustomize.py').read_text(), {})
        self.assertEqual(fake_sys.path, roots + ['/native/runfiles/rules_hdl', '/owned/run', '/stdlib'])
        self.assertEqual(launch.write_startup_hook(self.root, runtime), first)

    def test_missing_or_mutated_startup_hook_cannot_pass(self):
        for mutation in ('missing', 'changed'):
            self.finish()
            hook = self.root / 'sitecustomize.py'
            receipt = {'status': 'FINISHED', 'exit_code': 0, 'startup_hook_sha256': launch.sha(hook)}
            if mutation == 'missing':
                hook.unlink()
            else:
                hook.write_text('changed after wrapper startup')
            result = launch.finish_receipt(self.root, receipt, 'reset')
            self.assertNotEqual(result['semantic_verdict'], 'PASS')
            self.assertEqual(result['startup_hook_validation'], 'MISSING_OR_MISMATCH')

    def test_real_harness_serializes_initial_snapshot_before_pin_access(self):
        import importlib.util
        import struct
        import types
        from checker import BASE, initial_image
        header = struct.pack('<16sHHIIIIIHHHHHH', b'\x7fELF\x01\x01\x01' + bytes(9),
                             2, 243, 1, BASE, 52, 0, 0, 52, 32, 1, 0, 0, 0)
        segment = struct.pack('<8I', 1, 84, BASE, BASE, 4, 8, 5, 4)
        elf = self.root / 'snapshot.elf'
        elf.write_bytes(header + segment + b'CODE')
        expected, info = initial_image(elf, 17, 2101)
        config = dict(elf=str(elf), elf_sha256=launch.sha(elf), salt=17, run_id=2101,
                      entry=BASE, kernel=BASE + 32, ret=BASE + 0x20000,
                      review_verdict='APPROVED', schedule='P0', seed=42)
        cocotb = types.ModuleType('cocotb')
        cocotb.test = lambda: lambda function: function
        triggers = types.ModuleType('cocotb.triggers')
        triggers.Timer = object
        spec = importlib.util.spec_from_file_location('snapshot_control_harness', launch.HERE / 'cn_extmem_test.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', {'cocotb': cocotb, 'cocotb.triggers': triggers}):
            spec.loader.exec_module(module)
        class NoDutPins:
            def __getattr__(self, name):
                raise RuntimeError('NO_DUT first pin boundary')
        with patch.object(module.gzip, 'open'):
            with self.assertRaisesRegex(RuntimeError, 'NO_DUT first pin boundary'):
                module.Harness(NoDutPins(), config, self.root)
        snapshot = self.root / 'initial-image.bin'
        self.assertEqual(snapshot.read_bytes(), bytes(expected))
        self.assertEqual(launch.sha(snapshot), info['image_sha256'])
        self.assertEqual(snapshot.stat().st_size, 1048576)

    def test_existing_output_is_never_reused(self):
        with self.assertRaises(FileExistsError):
            launch.run({}, {}, self.root, 1, {})

if __name__ == '__main__':
    unittest.main()
