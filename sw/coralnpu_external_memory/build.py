#!/usr/bin/env python3
"""Build the five CN-EXTMEM-01 programs with an explicitly supplied RV32 compiler."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent
PREFIX = 'riscv64-unknown-elf-'
PROGRAMS = {'positive': 0, 'fetch_error': 1, 'load_error': 2,
            'store_error': 3, 'unmapped_load': 4}
SOURCES = ('start.S', 'kernel.S', 'main.c', 'negative.S', 'link.ld')
BOUND_SOURCES = (*SOURCES, 'build.py', 'inspect.py', 'regression.py', 'README.md',
                 'upstream/LICENSE', 'upstream/cc_toolchain_config.bzl',
                 'upstream/coralnpu_start.S', 'upstream/rvv_int8_matmul.cc')
TOOLS = ('gcc', 'as', 'ld', 'objdump', 'readelf', 'cc1', 'collect2')
FLAGS = ['-march=rv32imf_zve32f_zicsr_zifencei_zbb_zfbfmin_zvfbfmin_zvfbfwma',
         '-mabi=ilp32', '-mcmodel=medany', '-mno-relax', '-msmall-data-limit=0',
         '-O2', '-fno-tree-vectorize', '-ffreestanding', '-fno-builtin',
         '-fno-stack-protector', '-nostdlib', '-nostartfiles', '-Wall', '-Wextra', '-Werror',
         '-Wl,--no-relax', '-Wl,-T,link.ld', '-Wl,--build-id=none']


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(stream.read()).hexdigest()


def source_hashes():
    return {name: sha(ROOT / name) for name in BOUND_SOURCES}


def expected_commands():
    commands = [('compiler-version', [PREFIX + 'gcc', '--version'])]
    commands += [('locate-' + name, [PREFIX + 'gcc', '-print-prog-name=' + name])
                 for name in ('as', 'ld', 'cc1', 'collect2')]
    commands.append(('locate-headers', [PREFIX + 'gcc', '-print-file-name=include']))
    for source in ('start.S', 'kernel.S', 'main.c'):
        commands.append((source + '-compile', [PREFIX + 'gcc', *FLAGS, '-c', source,
                                               '-o', 'build/' + source.split('.')[0] + '.o']))
    for name, profile in PROGRAMS.items():
        if profile:
            commands.append((name + '-compile', [PREFIX + 'gcc', *FLAGS, f'-DPROFILE={profile}',
                                                  '-c', 'negative.S', '-o', f'build/{name}.o']))
        obj = 'build/main.o' if not profile else f'build/{name}.o'
        commands.append((name + '-link', [PREFIX + 'gcc', *FLAGS, f'-Wl,-Map,build/{name}.map',
                                          'build/start.o', 'build/kernel.o', obj, '-o', f'build/{name}.elf']))
        commands.append((name + '-disassembly', [PREFIX + 'objdump', '-d', '-t', f'build/{name}.elf']))
    return [{'name': name, 'argv': argv} for name, argv in commands]


class Diagnostics:
    """Retain subprocess output separately from deterministic artifact metadata."""
    def __init__(self, output, timeout):
        self.root = output / 'diagnostics'
        self.root.mkdir(parents=True)
        self.started = time.monotonic()
        self.timeout = timeout
        self.receipt = {'schema_version': 1, 'classification': 'RUNNING',
                        'stage': 'setup', 'dut_executed': False, 'events': []}
        self.save()

    def save(self):
        (self.root / 'receipt.json').write_text(json.dumps(self.receipt, indent=2) + '\n')

    def run(self, command, label, stage):
        self.receipt['stage'] = label
        remaining = self.timeout - (time.monotonic() - self.started)
        event = {'stage': label, 'argv': command, 'log': label + '.log',
                 'classification': 'RUNNING', 'exit_code': None}
        self.receipt['events'].append(event)
        self.save()
        if remaining <= 0:
            event['classification'] = 'NOT_STARTED_BUDGET_EXHAUSTED'
            self.save()
            raise TimeoutError(label + ': build budget exhausted before launch')
        with (self.root / event['log']).open('wb') as log:
            try:
                child = subprocess.Popen(command, cwd=stage, stdout=log,
                                         stderr=subprocess.STDOUT, start_new_session=True)
            except OSError as error:
                event.update(classification='COMMAND_START_FAILED', error=str(error))
                self.save()
                raise
            event['pid'] = child.pid
            self.save()
            try:
                child.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                    event['termination'] = 'OWNED_PROCESS_GROUP_SIGKILL_SENT'
                except ProcessLookupError:
                    event['termination'] = 'OWNED_PROCESS_GROUP_ALREADY_EXITED'
                child.wait(timeout=2)
                event.update(classification='TIMEOUT', exit_code=child.returncode,
                             child_reaped=True)
                self.save()
                raise TimeoutError(label + ': build budget exhausted; raw diagnostic retained')
            event.update(classification='PASS' if child.returncode == 0 else 'COMMAND_FAILED',
                         exit_code=child.returncode, child_reaped=True)
            self.save()
        stdout = (self.root / event['log']).read_bytes()
        if child.returncode:
            raise RuntimeError(f'{label} failed ({child.returncode}); raw diagnostic retained')
        return stdout


def toolchain(root):
    if root:
        gcc = Path(root).expanduser().resolve() / 'bin' / (PREFIX + 'gcc')
    else:
        found = shutil.which(PREFIX + 'gcc')
        if not found:
            raise ValueError('Supply --toolchain-root, RISCV_TOOLCHAIN_ROOT, or riscv64-unknown-elf-gcc on PATH')
        gcc = Path(found).resolve()
    result = {name: gcc.parent / (PREFIX + name) for name in ('gcc', 'as', 'ld', 'objdump', 'readelf')}
    for name, path in result.items():
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError(f'Missing executable {name}: {path}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain-root', default=os.environ.get('RISCV_TOOLCHAIN_ROOT'))
    parser.add_argument('--output', type=Path, required=True, help='new or empty output directory')
    parser.add_argument('--timeout', type=float, default=120, help='total compiler/inspection time budget in seconds')
    args = parser.parse_args()
    if not 0 < args.timeout <= 120:
        parser.error('--timeout must be greater than zero and at most 120')
    out = args.output.expanduser().resolve()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        parser.error('--output must be a new or empty directory')
    diagnostics = Diagnostics(out, args.timeout)
    try:
        perform_build(args, out, diagnostics)
    except (ValueError, RuntimeError, OSError, TimeoutError, subprocess.TimeoutExpired) as error:
        diagnostics.receipt.update(classification='TIMEOUT' if isinstance(error, (TimeoutError, subprocess.TimeoutExpired)) else 'FAILED', error=str(error))
        diagnostics.save()
        raise
    diagnostics.receipt.update(classification='PASS', stage='complete')
    diagnostics.save()


def perform_build(args, out, diagnostics):
    bins = toolchain(args.toolchain_root)
    events = []
    hashes = source_hashes()
    with tempfile.TemporaryDirectory(prefix='coralnpu-sw-') as scratch:
        stage = Path(scratch)
        (stage / 'build').mkdir()
        for name in SOURCES:
            shutil.copyfile(ROOT / name, stage / name)
        def run(argv, label):
            command = [str(x) for x in argv]
            stdout = diagnostics.run(command, label, stage)
            events.append({'name': label, 'argv': [Path(command[0]).name, *command[1:]]})
            return stdout
        version = run([bins['gcc'], '--version'], 'compiler-version').decode().strip()
        for name in ('as', 'ld', 'cc1', 'collect2'):
            value = run([bins['gcc'], '-print-prog-name=' + name], 'locate-' + name).decode().strip()
            path = Path(value)
            if not path.is_absolute():
                found = shutil.which(value, path=str(bins['gcc'].parent) + os.pathsep + os.environ.get('PATH', ''))
                if not found:
                    raise ValueError(f'Compiler helper not found: {name}')
                path = Path(found)
            bins[name] = path.resolve()
        identities = {name: sha(path) for name, path in bins.items()}
        include = Path(run([bins['gcc'], '-print-file-name=include'], 'locate-headers').decode().strip())
        if not include.is_dir():
            raise ValueError('Compiler builtin headers not found')
        headers = {str(path.relative_to(include)): sha(path) for path in sorted(include.rglob('*')) if path.is_file()}
        # Named object basenames and a fixed build/ relative path also stabilize linker maps.
        for source in ('start.S', 'kernel.S', 'main.c'):
            run([bins['gcc'], *FLAGS, '-c', source, '-o', 'build/' + source.split('.')[0] + '.o'], source + '-compile')
        for name, profile in PROGRAMS.items():
            if profile:
                run([bins['gcc'], *FLAGS, f'-DPROFILE={profile}', '-c', 'negative.S', '-o', f'build/{name}.o'], name + '-compile')
            obj = 'build/main.o' if not profile else f'build/{name}.o'
            run([bins['gcc'], *FLAGS, f'-Wl,-Map,build/{name}.map', 'build/start.o', 'build/kernel.o', obj, '-o', f'build/{name}.elf'], name + '-link')
            (stage / 'build' / (name + '.dis')).write_bytes(run([bins['objdump'], '-d', '-t', f'build/{name}.elf'], name + '-disassembly'))
        if source_hashes() != hashes or any(sha(path) != identities[name] for name, path in bins.items()):
            raise ValueError('Source/tool identity changed during compilation')
        if {str(path.relative_to(include)): sha(path) for path in sorted(include.rglob('*')) if path.is_file()} != headers:
            raise ValueError('Compiler headers changed during compilation')
        out.mkdir(parents=True, exist_ok=True)
        for path in sorted((stage / 'build').iterdir()):
            if path.suffix in ('.elf', '.map', '.dis'):
                shutil.copyfile(path, out / path.name)
        info = {'schema_version': 1, 'source_sha256': hashes,
                'toolchain': {'executables_sha256': identities, 'builtin_headers_sha256': headers,
                              'gcc_version': version},
                'flags': FLAGS, 'commands': events}
        (out / 'build-info.json').write_text(json.dumps(info, indent=2, sort_keys=True) + '\n')
    # Import this owned sibling by path: its name deliberately remains inspect.py.
    import importlib.util
    spec = importlib.util.spec_from_file_location('coralnpu_elf_inspect', ROOT / 'inspect.py')
    inspector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inspector)
    diagnostics.receipt['stage'] = 'static-inspection'
    diagnostics.save()
    manifest = inspector.create_manifest(out)
    print('PASS: built and statically inspected 5 ELF32 programs (no DUT execution)')
    print('manifest=' + str(manifest))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, TimeoutError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error))
