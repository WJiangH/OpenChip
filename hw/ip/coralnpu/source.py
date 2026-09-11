#!/usr/bin/env python3
"""Acquire and verify the unmodified pinned CoralNPU tree; build its native model."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import unquote, urlparse

PIN = json.loads(Path(__file__).with_name('ip.json').read_text())


def digest(path):
    with Path(path).open('rb') as f:
        value = hashlib.sha256()
        for block in iter(lambda: f.read(1024 * 1024), b''):
            value.update(block)
        return value.hexdigest()


def git_hash(kind, data):
    return hashlib.sha1(kind.encode() + b' ' + str(len(data)).encode() + b'\0' + data).digest()


def tree_hash(root):
    """Reconstruct Git's tree identity including bytes, names, executable bits and links."""
    entries = []
    count = 0
    for path in root.iterdir():
        mode = path.lstat().st_mode
        name = os.fsencode(path.name)
        if stat.S_ISLNK(mode):
            value, tag = git_hash('blob', os.fsencode(os.readlink(path))), b'120000'
            count += 1
        elif stat.S_ISDIR(mode):
            value, nested = tree_hash(path)
            count += nested
            tag = b'40000'
        elif stat.S_ISREG(mode):
            value = git_hash('blob', path.read_bytes())
            tag = b'100755' if mode & 0o111 else b'100644'
            count += 1
        else:
            raise ValueError(f'unsupported source file type: {path}')
        entries.append((name + (b'/' if tag == b'40000' else b''), tag + b' ' + name + b'\0' + value))
    return git_hash('tree', b''.join(e[1] for e in sorted(entries))), count


def verify(source):
    if source.is_symlink() or not source.is_dir():
        raise ValueError('source must be a real directory containing only the extracted tree')
    actual, count = tree_hash(source)
    if actual.hex() != PIN['tree'] or count != PIN['tracked_blobs']:
        raise ValueError(f'source mismatch: tree={actual.hex()} blobs={count}')
    return {'status': 'SOURCE_VERIFIED', 'commit': PIN['commit'], 'tree': actual.hex(), 'tracked_blobs': count}


def linux_filesystem(parent):
    if platform.system() != 'Linux':
        raise ValueError('Linux is required; use a Linux filesystem, not a macOS bind-mounted source directory')
    with tempfile.TemporaryDirectory(prefix='.case-probe-', dir=parent) as tmp:
        low = Path(tmp) / 'a'
        low.write_text('case probe')
        if (Path(tmp) / 'A').exists():
            raise ValueError('source filesystem is case-insensitive')


class CommandFailure(RuntimeError):
    def __init__(self, message, result):
        super().__init__(message)
        self.result = result


class CommandTimeout(TimeoutError):
    def __init__(self, message, result):
        super().__init__(message)
        self.result = result


def group_state(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return {'state': 'EXITED', 'members': []}
    except PermissionError:
        return {'state': 'UNKNOWN', 'members': []}
    try:
        lines = subprocess.check_output(['ps', '-axo', 'pid=,pgid=,stat='], timeout=1).decode().splitlines()
        members = []
        for line in lines:
            pid, group, state = line.split()
            if int(group) == pgid:
                members.append({'pid': int(pid), 'state': state})
        if not members:
            return {'state': 'EXITED', 'members': []}
        return {'state': 'LIVE' if any(not m['state'].startswith('Z') for m in members) else 'ZOMBIES_ONLY', 'members': members}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {'state': 'UNKNOWN', 'members': []}


def run(command, *, cwd=None, timeout=120, output=None):
    proc = subprocess.Popen(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                            start_new_session=True, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    timed_out = False
    started = time.monotonic()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    state = group_state(proc.pid)
    cleanup_needed = state['state'] not in ('EXITED', 'ZOMBIES_ONLY')
    if cleanup_needed:
        # A reaped leader does not prove its descendants exited. Bound the whole group.
        for sig in [signal.SIGTERM, signal.SIGKILL]:
            try:
                os.killpg(proc.pid, sig)
            except ProcessLookupError:
                pass
            except PermissionError:
                state = {'state': 'UNKNOWN', 'members': []}
                break
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                proc.poll()
                state = group_state(proc.pid)
                if state['state'] in ('EXITED', 'ZOMBIES_ONLY'):
                    break
                time.sleep(0.05)
            if state['state'] in ('EXITED', 'ZOMBIES_ONLY'):
                break
    proc.poll()
    result = {'exit_code': proc.returncode, 'timed_out': timed_out,
              'process_group': proc.pid, 'group_exit': state,
              'cleanup_needed': cleanup_needed, 'termination_grace_seconds': 13,
              'elapsed_seconds': time.monotonic() - started}
    if timed_out:
        raise CommandTimeout(f'command exceeded {timeout}s: {command[0]}', result)
    if proc.returncode != 0 or state['state'] not in ('EXITED', 'ZOMBIES_ONLY') or cleanup_needed:
        raise CommandFailure(f'command exited {proc.returncode} or left descendants: {command[0]}', result)
    return result


def unpack(archive, destination):
    if digest(archive) != PIN['archive_sha256']:
        raise ValueError('archive SHA-256 mismatch')
    with tarfile.open(archive, 'r:') as bundle:
        members = bundle.getmembers()
        seen = set()
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or member.name in seen:
                raise ValueError('unsafe or duplicate archive member')
            seen.add(member.name)
            if not (member.isdir() or member.isfile() or member.issym()):
                raise ValueError('unsupported archive member')
            if member.issym():
                target = (destination / member.name).parent / member.linkname
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise ValueError('archive symlink escapes source')
        # All members are hash-bound; validated links stay inside this fresh directory.
        bundle.extractall(destination, members=members, filter='data')
    return verify(destination)


def fetch(args):
    destination = args.dest.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('destination exists; verify it explicitly or choose a fresh destination')
    if not destination.parent.is_dir():
        raise ValueError('destination parent must already exist')
    linux_filesystem(destination.parent)
    with tempfile.TemporaryDirectory(prefix='.coralnpu-fetch-', dir=destination.parent) as tmp:
        tmp = Path(tmp)
        archive = args.archive
        if archive is None:
            repo = tmp / 'git'
            run(['git', 'init', '--bare', str(repo)])
            run(['git', '-C', str(repo), 'fetch', '--depth=1', PIN['repository'], PIN['commit']], timeout=120)
            tree = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'FETCH_HEAD^{tree}'], timeout=10).decode().strip()
            if tree != PIN['tree']:
                raise ValueError('downloaded Git tree mismatch')
            archive = tmp / 'source.tar'
            with archive.open('wb') as out:
                run(['git', '-C', str(repo), 'archive', '--format=tar', PIN['commit']], output=out)
        source = tmp / 'source'
        source.mkdir()
        result = unpack(archive, source)
        source.rename(destination)
        return result


def artifacts_from_bep(path):
    outputs = {}
    for line in path.read_text().splitlines():
        event = json.loads(line)
        for item in event.get('namedSetOfFiles', {}).get('files', []):
            uri = urlparse(item.get('uri', ''))
            if uri.scheme != 'file':
                continue
            artifact = Path(unquote(uri.path))
            paths = sorted(artifact.rglob('*')) if artifact.is_dir() else [artifact]
            for path in paths:
                if path.is_file():
                    outputs[str(path)] = digest(path)
    return outputs


def build(args):
    source = args.source.absolute()
    verify(source)
    linux_filesystem(source.parent)
    source = source.resolve()
    output = args.output_root.resolve()
    if output.exists() or output.is_symlink():
        raise ValueError('output root must be new; this entry never mutates another build cache')
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('source and output root must be disjoint')
    cache = (args.cache_root.resolve() if getattr(args, 'cache_root', None) else output / 'cache')
    if cache.is_relative_to(source) or source.is_relative_to(cache):
        raise ValueError('cache and source must be disjoint')
    version = subprocess.check_output(['bazel', '--version'], timeout=15).decode().strip()
    if version != 'bazel ' + PIN['bazel_version']:
        raise ValueError(f'wrong Bazel version: {version}')
    output.mkdir(parents=True)
    command = ['bazel', '--batch', '--nosystem_rc', '--nohome_rc',
               '--output_user_root=' + str(cache), 'build', '--jobs=4',
               '--local_resources=cpu=4', '--local_resources=memory=12288',
               '--symlink_prefix=/', '--repository_cache=' + str(output / 'repositories'),
               '--build_event_json_file=' + str(output / 'build.bep.json'), PIN['model_target']]
    receipt = {'status': 'BUILD_FAILED', 'dut_executed': False, 'source': verify(source),
               'command': command, 'bazel_version': version, 'timeout_seconds': args.timeout,
               'cache_root': str(cache), 'source_path': str(source),
               'entry_sha256': digest(Path(__file__)),
               'pin_sha256': digest(Path(__file__).with_name('ip.json'))}
    start = time.monotonic()
    try:
        with (output / 'build.log').open('wb') as log:
            receipt['process'] = run(command, cwd=source, timeout=args.timeout, output=log)
        receipt['source_after'] = verify(source)
        outputs = artifacts_from_bep(output / 'build.bep.json')
        models = [path for path in outputs if Path(path).name == PIN['hdl_toplevel']]
        if len(models) != 1 or not os.access(models[0], os.X_OK):
            raise ValueError('BEP must identify one executable of the declared model')
        receipt['model'] = {'path': models[0], 'sha256': outputs[models[0]],
                            'hdl_toplevel': PIN['hdl_toplevel']}
        receipt['artifacts_sha256'] = outputs
        receipt['status'] = 'BUILD_COMPLETE'
    except Exception as error:
        receipt['error'] = str(error)
        if hasattr(error, 'result'):
            receipt['process'] = error.result
        raise
    finally:
        receipt['elapsed_seconds'] = time.monotonic() - start
        receipt['log_sha256'] = digest(output / 'build.log')
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def runtime_inventory(cache):
    patterns = [
        '*/external/python311_*/bin/python3*',
        '*/external/python311_*/lib/libpython3.11.so*',
        '*/external/coralnpu_pip_deps_cocotb/cocotb_tools/runner.py',
        '*/external/coralnpu_pip_deps_cocotb/cocotb/libs/*.so',
        '*/external/rules_hdl/cocotb/cocotb_wrapper.py',
        '*/external/toolchain_coralnpu_v2/bin/riscv64-unknown-elf-gcc',
        '*/execroot/coralnpu_hw/bazel-out/*/bin/external/rules_hdl/cocotb/cocotb_wrapper*',
        '*/execroot/coralnpu_hw/bazel-out/*/bin/hdl/chisel/src/coralnpu/' + PIN['hdl_toplevel'] + '.sv',
        '*/execroot/coralnpu_hw/bazel-out/*/bin/hdl/chisel/src/coralnpu/V' + PIN['hdl_toplevel'] + '_parameters.h',
    ]
    paths = {path.resolve() for pattern in patterns for path in cache.glob(pattern) if path.is_file()}
    for package in PIN['python_packages']:
        roots = list(cache.glob('*/external/coralnpu_pip_deps_' + package))
        if len(roots) != 1:
            raise ValueError('missing or ambiguous native Python package: ' + package)
        paths.update(path.resolve() for path in roots[0].rglob('*') if path.is_file() and '__pycache__' not in path.parts)
    return {str(path): digest(path) for path in sorted(paths)}


def runtime(args):
    """Build only the generic upstream wrapper using the source-bound model cache."""
    prior_path = args.build_root.resolve() / 'receipt.json'
    prior = json.loads(prior_path.read_text())
    if prior.get('status') != 'BUILD_COMPLETE':
        raise ValueError('a completed model build receipt is required')
    if prior.get('source', {}).get('tree') != PIN['tree'] or prior.get('source', {}).get('commit') != PIN['commit']:
        raise ValueError('model build receipt has wrong source identity')
    source = args.source.resolve()
    verify(source)
    linux_filesystem(source.parent)
    output = args.output_root.resolve()
    if output.exists() or output.is_relative_to(source):
        raise ValueError('runtime output must be a new directory outside source')
    cache = Path(prior.get('cache_root', str(args.build_root.resolve() / 'cache'))).resolve()
    if not cache.is_dir():
        raise ValueError('model build cache missing')
    version = subprocess.check_output(['bazel', '--version'], timeout=15).decode().strip()
    if version != 'bazel ' + PIN['bazel_version']:
        raise ValueError(f'wrong Bazel version: {version}')
    output.mkdir(parents=True)
    command = ['bazel', '--batch', '--nosystem_rc', '--nohome_rc',
               '--output_user_root=' + str(cache), 'build', '--jobs=4',
               '--local_resources=cpu=4', '--local_resources=memory=12288',
               '--symlink_prefix=/', '--repository_cache=' + str(args.build_root.resolve() / 'repositories'),
               '--build_event_json_file=' + str(output / 'build.bep.json'), *PIN['runtime_targets']]
    receipt = {'status': 'RUNTIME_BUILD_FAILED', 'dut_executed': False,
               'model_build_receipt_sha256': digest(prior_path), 'source': verify(source),
               'command': command, 'timeout_seconds': args.timeout,
               'entry_sha256': digest(Path(__file__))}
    start = time.monotonic()
    try:
        with (output / 'build.log').open('wb') as log:
            receipt['process'] = run(command, cwd=source, timeout=args.timeout, output=log)
        receipt['source_after'] = verify(source)
        receipt['artifacts_sha256'] = artifacts_from_bep(output / 'build.bep.json')
        for name in ['cocotb_wrapper', 'riscv64-unknown-elf-gcc']:
            expected = [p for p in receipt['artifacts_sha256'] if Path(p).name == name and os.access(p, os.X_OK)]
            if len(expected) != 1:
                raise ValueError('runtime BEP must identify one executable ' + name)
        receipt['observed_runtime_sha256'] = runtime_inventory(cache)
        receipt['status'] = 'RUNTIME_BUILD_COMPLETE'
    except Exception as error:
        receipt['error'] = str(error)
        if hasattr(error, 'result'):
            receipt['process'] = error.result
        raise
    finally:
        receipt['elapsed_seconds'] = time.monotonic() - start
        receipt['log_sha256'] = digest(output / 'build.log')
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def export_runtime(args):
    model_receipt_path = args.build_root.resolve() / 'receipt.json'
    runtime_receipt_path = args.runtime_root.resolve() / 'receipt.json'
    model_receipt = json.loads(model_receipt_path.read_text())
    runtime_receipt = json.loads(runtime_receipt_path.read_text())
    if model_receipt.get('status') != 'BUILD_COMPLETE' or runtime_receipt.get('status') != 'RUNTIME_BUILD_COMPLETE':
        raise ValueError('both model and runtime builds must be complete')
    if runtime_receipt.get('model_build_receipt_sha256') != digest(model_receipt_path):
        raise ValueError('runtime build references a different model receipt')
    source = args.source.resolve()
    verify(source)
    for receipt in [model_receipt, runtime_receipt]:
        if receipt.get('source', {}).get('tree') != PIN['tree']:
            raise ValueError('build source identity mismatch')
    cache = Path(model_receipt.get('cache_root', str(args.build_root.resolve() / 'cache'))).resolve()
    bases = list(cache.glob('*/execroot/coralnpu_hw'))
    if len(bases) != 1:
        raise ValueError('expected one source workspace in owned build cache')
    base = bases[0]
    external = base.parent.parent / 'external'
    def one(paths, label):
        paths = sorted({p.resolve() for p in paths if p.is_file()})
        if not paths or len({digest(p) for p in paths}) != 1:
            raise ValueError('missing or ambiguous ' + label)
        return paths[0]
    models = [Path(p) for p, sha in model_receipt.get('artifacts_sha256', {}).items()
              if Path(p).name == PIN['hdl_toplevel'] and Path(p).is_file() and digest(p) == sha]
    model = one(models, 'model')
    wrapper = one(base.glob('bazel-out/*/bin/external/rules_hdl/cocotb/cocotb_wrapper'), 'wrapper')
    if runtime_receipt.get('artifacts_sha256', {}).get(str(wrapper)) != digest(wrapper):
        raise ValueError('wrapper differs from runtime build artifact')
    python = one(external.glob('python311_*/bin/python3'), 'Python interpreter')
    runner = one(external.glob('coralnpu_pip_deps_cocotb/cocotb_tools/runner.py'), 'cocotb runner')
    library_dir = runner.parent.parent / 'cocotb' / 'libs'
    generated_top = one(base.glob('bazel-out/*/bin/hdl/chisel/src/coralnpu/' + PIN['hdl_toplevel'] + '.sv'), 'generated RTL')
    parameter_header = one(base.glob('bazel-out/*/bin/hdl/chisel/src/coralnpu/V' + PIN['hdl_toplevel'] + '_parameters.h'), 'parameter header')
    toolchain_gcc = one(external.glob('toolchain_coralnpu_v2/bin/riscv64-unknown-elf-gcc'), 'RISC-V compiler')
    paths = [python, wrapper, model, runner, generated_top, parameter_header, toolchain_gcc,
             Path(str(wrapper) + '.runfiles_manifest'), external / 'rules_hdl/cocotb/cocotb_wrapper.py',
             python.parent.parent / 'lib/libpython3.11.so.1.0']
    paths.extend(library_dir.glob('*.so'))
    if not library_dir.is_dir() or not list(library_dir.glob('*.so')):
        raise ValueError('cocotb libraries missing')
    package_roots = [external / ('coralnpu_pip_deps_' + package) for package in PIN['python_packages']]
    for package_root in package_roots:
        if not package_root.is_dir():
            raise ValueError('Python dependency missing: ' + str(package_root))
        paths.extend(path.resolve() for path in package_root.rglob('*') if path.is_file() and '__pycache__' not in path.parts)
    for path in paths:
        if path != model and runtime_receipt.get('observed_runtime_sha256', {}).get(str(path.resolve())) != digest(path):
            raise ValueError('runtime artifact differs from auxiliary receipt: ' + str(path))
    environment = {'PYTHONPATH': os.pathsep.join(map(str, package_roots)),
                   'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'}
    result = {'schema_version': 1, 'status': 'RUNTIME_RESOLVED_NO_DUT',
              'build_receipt': {'path': str(model_receipt_path), 'sha256': digest(model_receipt_path)},
              'runtime_build_receipt': {'path': str(runtime_receipt_path), 'sha256': digest(runtime_receipt_path)},
              'upstream': {'commit': PIN['commit'], 'tree': PIN['tree']},
              'top': PIN['hdl_toplevel'], 'cwd': str(source), 'python': str(python),
              'wrapper': str(wrapper), 'model': str(model), 'model_argument': '../' + str(model), 'runner': str(runner),
              'generated_top': str(generated_top), 'parameter_header': str(parameter_header),
              'library_dir': str(library_dir), 'toolchain_root': str(toolchain_gcc.parent.parent),
              'environment': environment, 'artifacts_sha256': {str(p): digest(p) for p in paths}}
    if args.output.exists():
        raise ValueError('runtime manifest output exists')
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('fetch')
    p.add_argument('--dest', type=Path, required=True)
    p.add_argument('--archive', type=Path, help='optional exact uncompressed git archive; SHA-256 checked')
    p = commands.add_parser('verify')
    p.add_argument('--source', type=Path, required=True)
    p = commands.add_parser('build')
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output-root', type=Path, required=True)
    p.add_argument('--cache-root', type=Path, help='optional explicitly owned Bazel cache to reuse')
    p.add_argument('--timeout', type=int, default=900, choices=range(1, 901), metavar='1..900')
    p = commands.add_parser('runtime-build')
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--build-root', type=Path, required=True)
    p.add_argument('--output-root', type=Path, required=True)
    p.add_argument('--timeout', type=int, default=180, choices=range(1, 181), metavar='1..180')
    p = commands.add_parser('runtime')
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--build-root', type=Path, required=True)
    p.add_argument('--runtime-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = ({'fetch': fetch, 'build': build, 'runtime-build': runtime, 'runtime': export_runtime}.get(args.command, lambda a: verify(a.source)))(args)
        if args.command in ('build', 'runtime-build'):
            result = {'status': result['status'], 'receipt': str(args.output_root / 'receipt.json'),
                      'artifact_count': len(result.get('artifacts_sha256', {})), 'process': result.get('process')}
        elif args.command == 'runtime':
            result = {'status': result['status'], 'manifest': str(args.output),
                      'artifact_count': len(result['artifacts_sha256'])}
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, RuntimeError, TimeoutError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
