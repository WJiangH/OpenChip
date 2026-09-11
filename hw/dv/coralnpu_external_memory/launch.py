"""Native CN-EXTMEM-01 launcher. Identity checks and receipts are not signoff."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import resource
import signal
import subprocess
import time
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
SPEC_SHA256 = 'cdb0a147cc770f595bc2ee07b5bc589d7f38ad8500341e950078c786b2cb9b15'
UPSTREAM = {'commit': '561c59d33fea8a02e7f1062956ec77740e0eb955',
            'tree': '9dbf21aa935571f43e79a2fe15df28275f7d6636'}
FILES = ['checker.py', 'responder.py', 'cn_extmem_test.py', 'oracle.py',
         'host_checker.py', 'exploratory_checker.py', 'exploratory_responder.py',
         'cn_exploratory_test.py']


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def bound_artifact(base, entry):
    path = (base / entry['path']).resolve()
    require(sha(path) == entry['sha256'], 'artifact identity mismatch: ' + str(path))
    return path


def check_results_xml(path, kind='error'):
    """A checker PASS never substitutes for the exact cocotb testcase result."""
    module, name = (('cn_extmem_test', 'external_memory') if kind == 'positive'
                    else ('cn_exploratory_test', 'external_memory_exploratory'))
    try:
        root = ET.parse(path).getroot()
        require(root.tag in ('testsuites', 'testsuite'), 'unexpected XML root')
        require(all('}' not in node.tag for node in root.iter()), 'unexpected XML namespace')
        cases = list(root.iter('testcase'))
        require(len(cases) == 1, 'expected exactly one testcase')
        case = cases[0]
        require(case.get('name') == name, 'unexpected testcase name')
        require(case.get('classname') == module, 'unexpected testcase module')
        require(not any(n.tag in ('failure', 'error', 'skipped') for n in root.iter()),
                'failed/errored/skipped testcase')
        for node in root.iter():
            for key in ('failures', 'errors', 'skipped'):
                if key in node.attrib:
                    require(int(node.get(key)) == 0, 'nonzero ' + key)
            if node.tag in ('testsuites', 'testsuite') and 'tests' in node.attrib:
                require(int(node.get('tests')) == 1, 'inconsistent testcase count')
        return {'status': 'PASS', 'testcase': name, 'module': module}
    except (OSError, ET.ParseError, ValueError) as exc:
        return {'status': 'INVALID_RESULTS_XML', 'reason': str(exc)}


def make_config(software_path, review_path, profile, spec_path):
    require(sha(spec_path) == SPEC_SHA256, 'unreviewed contract identity')
    software_path = Path(software_path).resolve()
    software, review = read(software_path), read(review_path)
    require(software['schema_version'] == 1 and software['contract_version'] == '0.4',
            'unsupported software manifest')
    require(software['upstream'] == UPSTREAM, 'software upstream identity')
    require(review['verdict'] == 'APPROVED' and
            review['software_manifest_sha256'] == sha(software_path) and
            review['contract_sha256'] == SPEC_SHA256, 'current CNEM-29 software review missing')
    profiles = read(HERE / 'profiles.json')
    require(profiles['contract_version'] == '0.4', 'profile contract version')
    config = dict(profiles['profiles'][profile], profile=profile)
    artifact = software['artifacts'][config['software_variant']]
    elf = bound_artifact(software_path.parent, artifact['elf'])
    bound_artifact(software_path.parent, artifact['map'])
    symbols = artifact['symbols']
    kernel, ret = symbols['rvv_gemv_int8'], symbols['_ret']
    require(kernel['type'] == 'STT_FUNC' and kernel['size'] > 0 and
            0x20000000 <= kernel['address'] < kernel['address'] + kernel['size'] <= 0x20010000,
            'CNEM-28 kernel extent')
    require(ret['size'] == 4 and ret['address'] % 4 == 0 and
            0x20020000 <= ret['address'] <= 0x2002fffc, 'CNEM-05 return extent')
    require(0x20000000 <= artifact['entry'] <= 0x2000fffc and
            artifact['entry'] // 16 != kernel['address'] // 16, 'CNEM-05 entry placement')
    config.update(elf=str(elf), elf_sha256=sha(elf), entry=artifact['entry'],
                  kernel=kernel['address'], ret=ret['address'], review_verdict='APPROVED',
                  source_contract_version='0.4', source_contract_spec_sha256=SPEC_SHA256,
                  software_manifest_sha256=sha(software_path), software_review_sha256=sha(review_path))
    if config['kind'] == 'error':
        handler = symbols['trap_handler']
        require(0x20000000 <= handler['address'] < handler['address'] + handler['size'] <= 0x20010000,
                'CNEM-29 handler extent')
        config['handler'] = handler['address']
        config['expected_mepc'] = (0x200ff000 if config['error_kind'] == 'fetch'
                                   else symbols['fault_instruction']['address'])
        if config['error_kind'] != 'fetch':
            require(0x20000000 <= config['expected_mepc'] <= 0x2000fffc,
                    'CNEM-29 fault instruction placement')
    return config


def validate_runtime(path):
    path = Path(path).resolve()
    runtime = read(path)
    require(runtime['schema_version'] == 1 and runtime['upstream'] == UPSTREAM,
            'runtime source identity')
    require(runtime['top'] == 'RvvCoreMiniHighmemAxi', 'CNEM-02 top')
    build_path = bound_artifact(path.parent, runtime['build_receipt'])
    build = read(build_path)
    require(build['status'] == 'BUILD_COMPLETE', 'native model build incomplete')
    source = build['source']
    require(source.get('status') == 'SOURCE_VERIFIED' and
            all(source.get(key) == value for key, value in UPSTREAM.items()) and
            bool(source.get('tracked_blobs')), 'native build source identity')
    model = build['model']
    require(model['path'] == runtime['model'] and model['hdl_toplevel'] == runtime['top'] and
            build['artifacts_sha256'].get(runtime['model']) == model['sha256'],
            'native build model/top identity')
    runtime_build_path = bound_artifact(path.parent, runtime['runtime_build_receipt'])
    auxiliary = read(runtime_build_path)
    require(auxiliary['status'] == 'RUNTIME_BUILD_COMPLETE', 'native wrapper build incomplete')
    require(auxiliary['model_build_receipt_sha256'] == sha(build_path),
            'auxiliary build linked to different model receipt')
    require(auxiliary['source'] == source, 'auxiliary build source identity')
    observed = auxiliary['observed_runtime_sha256']
    produced = auxiliary['artifacts_sha256']
    for name in observed.keys() & produced.keys():
        require(observed[name] == produced[name], 'conflicting auxiliary artifact identity: ' + name)
    # The model is a primary target output. Top/header and runtime dependencies
    # are auxiliary observations, explicitly linked to that exact primary receipt.
    for name, digest in runtime['artifacts_sha256'].items():
        require(Path(name).is_absolute() and sha(name) == digest, 'runtime artifact mismatch: ' + name)
        expected = model['sha256'] if name == model['path'] else observed.get(name)
        require(digest == expected, 'runtime artifact not bound by build receipt: ' + name)
    require(produced.get(runtime['wrapper']) == runtime['artifacts_sha256'].get(runtime['wrapper'])
            and runtime['wrapper'] in produced, 'wrapper missing from auxiliary build outputs')
    for key in ('python', 'wrapper', 'model', 'runner', 'generated_top', 'parameter_header'):
        require(runtime[key] in runtime['artifacts_sha256'], 'missing runtime identity: ' + key)
    require(Path(runtime['cwd']).is_dir() and Path(runtime['library_dir']).is_dir(), 'runtime directories')
    libraries = list(Path(runtime['library_dir']).glob('*.so'))
    require(bool(libraries), 'missing cocotb libraries')
    for library in libraries:
        require(str(library) in runtime['artifacts_sha256'], 'unbound runtime library: ' + str(library))
    roots = package_roots(runtime)
    require(bool(roots), 'runtime package roots missing')
    for root in roots:
        require(Path(root).is_absolute() and Path(root).is_dir() and
                any(Path(root) in Path(name).parents for name in observed),
                'runtime package root not bound by dependency inventory: ' + root)
    return runtime


def package_roots(runtime):
    return list(dict.fromkeys(filter(None, runtime.get('environment', {}).get('PYTHONPATH', '').split(os.pathsep))))


def write_startup_hook(output, runtime):
    # Bazel's generic wrapper can put its empty cocotb package before the wheel.
    # sitecustomize runs at interpreter startup and survives the native re-exec;
    # the unmodified runner then propagates this ordered sys.path to its child.
    roots = package_roots(runtime)
    text = ('import sys\n_PACKAGE_ROOTS = ' + repr(roots) + '\n'
            'sys.path[:] = _PACKAGE_ROOTS + [path for path in sys.path if path not in _PACKAGE_ROOTS]\n')
    path = output / 'sitecustomize.py'
    path.write_text(text)
    return sha(path)


def required_artifacts(kind):
    result = ['program.elf', 'config.json', 'raw.log', 'results.xml', 'verdict.json', 'sitecustomize.py', *FILES]
    if kind == 'reset':
        result += ['abort-witness.json', 'epoch-0-aborted/initial-image.bin']
        result += [epoch + '/' + name for epoch in ('epoch-0-aborted', 'epoch-1-recovery')
                   for name in ('final-memory.bin', 'trace.jsonl.gz', 'verdict.json')]
    else:
        result += ['initial-image.bin', 'final-memory.bin', 'trace.jsonl.gz']
        if kind == 'error':
            result += ['terminal-memory.bin']
    return result


def finish_receipt(output, receipt, kind):
    try:
        checker = read(output / 'verdict.json')['verdict']
    except (OSError, ValueError, KeyError):
        checker = 'NO_CHECKER_VERDICT'
    missing = [name for name in required_artifacts(kind) if not (output / name).is_file()]
    xml = check_results_xml(output / 'results.xml', kind)
    hook = output / 'sitecustomize.py'
    hook_valid = hook.is_file() and sha(hook) == receipt.get('startup_hook_sha256')
    verdict = checker
    if checker != 'FAIL':
        if checker != 'PASS':
            verdict = 'NO_CHECKER_VERDICT'
        elif xml['status'] != 'PASS':
            verdict = 'INVALID_RESULTS_XML'
        elif receipt['exit_code'] != 0 or receipt['status'] != 'FINISHED':
            verdict = 'PROCESS_FAILED_OR_UNKNOWN'
        if not hook_valid:
            verdict = 'STARTUP_HOOK_MISMATCH'
        if missing:
            verdict = 'INCOMPLETE_ARTIFACTS'
        if receipt.get('process_exit') == 'UNKNOWN':
            verdict = 'PROCESS_EXIT_UNKNOWN'
    receipt.update(checker_verdict=checker, results_xml_validation=xml,
                   startup_hook_validation='MATCH' if hook_valid else 'MISSING_OR_MISMATCH',
                   missing_artifacts=missing, semantic_verdict=verdict,
                   artifact_sha256={str(f.relative_to(output)): sha(f) for f in output.rglob('*')
                                    if f.is_file() and f.name != 'receipt.json'})
    return receipt


def cleanup_owned_process(process, receipt):
    """One five-second absolute deadline shared by TERM, KILL and reaping."""
    started = time.monotonic()
    deadline = started + receipt['termination_grace_seconds']
    receipt.update(process_exit='UNKNOWN', cleanup_deadline_monotonic=deadline)
    errors = []
    reaped = False
    for sig, wait_cap in ((signal.SIGTERM, 2), (signal.SIGKILL, None)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        except OSError as exc:
            errors.append(str(exc))
        remaining = deadline - time.monotonic()
        if not reaped and remaining > 0:
            try:
                receipt['exit_code'] = process.wait(timeout=min(remaining, wait_cap)
                                                    if wait_cap is not None else remaining)
                reaped = True
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(str(exc))
    # A successful wait, not a returncode attribute or signal request, proves reaping.
    receipt['process_exit'] = 'EXITED' if reaped else 'UNKNOWN'
    receipt['cleanup_elapsed_seconds'] = time.monotonic() - started
    if errors:
        receipt['cleanup_errors'] = errors


def run(runtime, config, output, wall_seconds, identities):
    require(1 <= wall_seconds <= 115, 'wall seconds must be 1..115')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    startup_hook_sha256 = write_startup_hook(output, runtime)
    for filename in FILES:
        shutil.copyfile(HERE / filename, output / filename)
    shutil.copyfile(config['elf'], output / 'program.elf')
    config = dict(config, elf=str(output / 'program.elf'))
    (output / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    module = 'cn_extmem_test' if config['kind'] == 'positive' else 'cn_exploratory_test'
    command = [runtime['python'], runtime['wrapper'], '--sim', 'verilator', '--hdl_library', 'top',
               '--hdl_toplevel', runtime['top'], '--hdl_toplevel_lang', 'verilog',
               '--seed', str(config['seed']), '--test_module', module, '--model', '../' + runtime['model'],
               '--main_workspace', 'coralnpu_hw', '--test_dir', str(output),
               '--results_xml', str(output / 'results.xml'),
               '--extra_env', 'LD_LIBRARY_PATH=' + runtime['library_dir']]
    runtime_env = runtime.get('environment', {})
    require(set(runtime_env) <= {'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE', 'PYTHONNOUSERSITE'},
            'unsupported runtime environment variable')
    env = dict(os.environ, **runtime_env)
    env.update(PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=os.pathsep.join(filter(None, [str(output), runtime_env.get('PYTHONPATH')])),
               CN_CONFIG=str(output / 'config.json'), CN_OUTPUT=str(output),
               LD_LIBRARY_PATH=runtime['library_dir'])
    receipt = dict(schema_version=1, profile=config['profile'], status='PREPARING', exit_code=None,
                   wall_seconds=wall_seconds, termination_grace_seconds=5,
                   startup_hook_sha256=startup_hook_sha256,
                   start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   command=command, cwd=runtime['cwd'], identities=identities,
                   runtime_artifacts_sha256=runtime['artifacts_sha256'],
                   environment={key: env[key] for key in ('PYTHONPATH', 'PYTHONDONTWRITEBYTECODE',
                                                         'LD_LIBRARY_PATH', 'CN_CONFIG', 'CN_OUTPUT')},
                   source_sha256={f: sha(HERE / f) for f in FILES + ['launch.py', 'profiles.json']})
    def checkpoint():
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    checkpoint()
    try:
        with (output / 'raw.log').open('wb') as log:
            process = subprocess.Popen(command, cwd=runtime['cwd'], env=env,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            receipt.update(status='RUNNING', pid=process.pid, process_exit='UNKNOWN')
            checkpoint()
            try:
                receipt['exit_code'] = process.wait(timeout=wall_seconds)
                receipt.update(status='FINISHED', process_exit='EXITED')
            except subprocess.TimeoutExpired:
                receipt['status'] = 'TIMEOUT'
    except (OSError, subprocess.SubprocessError) as exc:
        receipt.update(status='LAUNCH_ERROR', error=str(exc))
    finally:
        if 'process' in locals() and receipt.get('process_exit') == 'UNKNOWN':
            cleanup_owned_process(process, receipt)
        receipt.setdefault('process_exit', 'NOT_STARTED')
        usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        receipt['resources'] = {'child_user_seconds': usage_after.ru_utime - usage_before.ru_utime,
                                'child_system_seconds': usage_after.ru_stime - usage_before.ru_stime,
                                'children_maxrss': usage_after.ru_maxrss,
                                'maxrss_scope': 'launcher lifetime child high water; platform units'}
        receipt.update(elapsed_seconds=time.monotonic() - start,
                       end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        finish_receipt(output, receipt, config['kind'])
        checkpoint()
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--software', required=True, type=Path)
    parser.add_argument('--software-review', required=True, type=Path)
    parser.add_argument('--profile', required=True, choices=read(HERE / 'profiles.json')['profiles'])
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--wall-seconds', required=True, type=int)
    parser.add_argument('--spec', type=Path, default=HERE.parents[2] / 'docs/spec/coralnpu_external_memory.md')
    args = parser.parse_args()
    require(1 <= args.wall_seconds <= 115, 'wall seconds must be 1..115 plus bounded termination grace')
    config = make_config(args.software, args.software_review, args.profile, args.spec)
    runtime = validate_runtime(args.runtime)
    identities = {name: sha(path) for name, path in [('runtime_manifest', args.runtime),
                  ('software_manifest', args.software), ('software_review', args.software_review),
                  ('contract', args.spec)]}
    receipt = run(runtime, config, args.output, args.wall_seconds, identities)
    print(json.dumps({k: receipt[k] for k in ('profile', 'status', 'exit_code', 'semantic_verdict')}))
    return 0 if receipt['semantic_verdict'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
