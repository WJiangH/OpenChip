#!/usr/bin/env python3
"""Validate newly built ELF placement and metadata; never an execution oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parent
UPSTREAM = {'commit': '561c59d33fea8a02e7f1062956ec77740e0eb955',
            'tree': '9dbf21aa935571f43e79a2fe15df28275f7d6636'}
PROGRAMS = {'positive': 'positive', 'fetch': 'fetch_error', 'load': 'load_error',
            'store': 'store_error', 'unmapped': 'unmapped_load'}
SYMBOL_TYPES = {0: 'STT_NOTYPE', 1: 'STT_OBJECT', 2: 'STT_FUNC'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inspect_elf(path, positive):
    data = path.read_bytes()
    require(len(data) >= 52 and data[:7] == b'\x7fELF\x01\x01\x01', 'Expected ELF32 little endian')
    h = struct.unpack_from('<HHIIIIIHHHHHH', data, 16)
    require(h[:3] == (2, 243, 1), 'Expected RISC-V executable')
    entry, phoff, shoff = h[3:6]
    phsize, phnum, shsize, shnum = h[8:12]
    require(phsize == 32 and shsize == 40 and phnum > 0 and shnum > 0, 'Invalid table dimensions')
    require(phoff + phnum * phsize <= len(data) and shoff + shnum * shsize <= len(data), 'Truncated ELF tables')
    loads = []
    for i in range(phnum):
        typ, off, va, pa, fs, ms, flags, align = struct.unpack_from('<8I', data, phoff + i * phsize)
        if typ != 1:
            continue
        require(va == pa and fs <= ms and off + fs <= len(data), 'Invalid load segment')
        require((flags == 5 and 0x20000000 <= va < va + ms <= 0x20010000) or
                (flags == 6 and 0x20020000 <= va < va + ms <= 0x20030000), 'Load outside allowed windows')
        require(align in (0, 1) or (align & (align - 1) == 0 and (va - off) % align == 0), 'Invalid load alignment')
        require(all(va + ms <= old['vaddr'] or va >= old['vaddr'] + old['memsz'] for old in loads), 'Overlapping loads')
        loads.append(dict(offset=off, vaddr=va, paddr=pa, filesz=fs, memsz=ms, flags=flags, align=align))
    require(len(loads) == 2, 'Expected code and metadata PT_LOAD')
    sections = [struct.unpack_from('<10I', data, shoff + i * shsize) for i in range(shnum)]
    symbols = {}
    wanted = {'_start', 'rvv_gemv_int8', 'trap_handler', '_ret', 'main', 'clean_halt', 'fault_instruction'}
    for section in sections:
        if section[1] != 2:
            continue
        require(section[6] < shnum and section[9] == 16 and section[5] % 16 == 0, 'Invalid symbol table')
        strings_section = sections[section[6]]
        require(section[4] + section[5] <= len(data) and strings_section[4] + strings_section[5] <= len(data), 'Truncated symbols/strings')
        strings = data[strings_section[4]:strings_section[4] + strings_section[5]]
        for offset in range(section[4], section[4] + section[5], 16):
            no, value, size, info, other, index = struct.unpack_from('<IIIBBH', data, offset)
            require(no < len(strings), 'Invalid symbol name offset')
            name = strings[no:].split(b'\0', 1)[0].decode()
            if name in wanted:
                require(name not in symbols and index != 0, 'Duplicate or undefined required symbol')
                symbols[name] = dict(address=value, size=size, type=SYMBOL_TYPES.get(info & 15, str(info & 15)))
    required = {'_start', 'rvv_gemv_int8', 'trap_handler', 'main', '_ret', 'clean_halt'}
    if not positive:
        required.add('fault_instruction')
    require(required <= symbols.keys(), 'Missing required symbols')
    code = next(item for item in loads if item['flags'] == 5)
    for name in ('_start', 'rvv_gemv_int8', 'trap_handler', 'main'):
        sym = symbols[name]
        require(sym['type'] == 'STT_FUNC' and sym['size'] > 0 and
                code['vaddr'] <= sym['address'] < sym['address'] + sym['size'] <= code['vaddr'] + code['filesz'], 'Invalid function extent: ' + name)
    require(entry == symbols['_start']['address'], 'Entry differs from _start')
    require(symbols['_ret'] == dict(address=0x20020000, size=4, type='STT_OBJECT'), 'Invalid return slot')
    require(entry // 16 != symbols['rvv_gemv_int8']['address'] // 16, 'Entry/kernel fetch line overlap')
    halt_offset = symbols['clean_halt']['address'] - code['vaddr']
    text = data[code['offset']:code['offset'] + code['filesz']]
    require(0 <= halt_offset <= len(text) - 4 and text[halt_offset:halt_offset + 4] == struct.pack('<I', 0x08000073), 'Missing clean MPAUSE')
    if not positive:
        fault = symbols['fault_instruction']
        require(fault['type'] == 'STT_FUNC' and fault['size'] == 4 and
                code['vaddr'] <= fault['address'] <= code['vaddr'] + code['filesz'] - 4, 'Invalid fault instruction')
    dis = path.with_suffix('.dis').read_text()
    require('ebreak' not in dis, 'Unexpected EBREAK')
    if positive:
        for insn in ('vsetvli', 'vle8.v', 'vwmul.vx', 'vwadd.wv', 'vse32.v', '\tsb\t', '\tsh\t', '\tlbu\t', '\tlhu\t'):
            require(insn in dis, 'Missing instruction: ' + insn)
        target = f"# {symbols['rvv_gemv_int8']['address']:x} <rvv_gemv_int8>"
        require(dis.count(target) == 2, 'Expected two compiled kernel call sites')
    return dict(entry=entry, symbols=symbols, pt_load=loads)


def validate_build_info(info):
    require(info.get('schema_version') == 1, 'Unknown build information schema')
    import importlib.util
    module_spec = importlib.util.spec_from_file_location('coralnpu_build_contract', ROOT / 'build.py')
    build = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(build)
    require(info.get('source_sha256') == build.source_hashes(), 'Missing, extra or changed source bindings')
    require(info.get('flags') == build.FLAGS, 'Missing or changed compiler/ISA flags')
    require(info.get('commands') == build.expected_commands(), 'Missing or changed build command metadata')
    tc = info.get('toolchain')
    require(isinstance(tc, dict), 'Missing toolchain metadata')
    identities = tc.get('executables_sha256')
    require(isinstance(identities, dict) and set(identities) == set(build.TOOLS), 'Missing or extra tool identity bindings')
    digest = lambda value: isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None
    require(all(digest(value) for value in identities.values()), 'Malformed tool identity hash')
    headers = tc.get('builtin_headers_sha256')
    require(isinstance(headers, dict) and {'stdint.h', 'stddef.h'} <= set(headers), 'Missing builtin header bindings')
    require(all(isinstance(name, str) and name and not Path(name).is_absolute() and
                '..' not in Path(name).parts and digest(value) for name, value in headers.items()), 'Malformed header identity binding')
    require(isinstance(tc.get('gcc_version'), str) and bool(tc['gcc_version'].strip()), 'Missing compiler version')


def create_manifest(output):
    output = Path(output).resolve()
    info = json.loads((output / 'build-info.json').read_text())
    validate_build_info(info)
    artifacts = {}
    for key, basename in PROGRAMS.items():
        elf = output / (basename + '.elf')
        artifact = inspect_elf(elf, key == 'positive')
        for label, extension in (('elf', '.elf'), ('map', '.map'), ('disassembly', '.dis')):
            path = output / (basename + extension)
            artifact[label] = {'path': path.name, 'sha256': sha(path)}
        artifacts[key] = artifact
    manifest = {'schema_version': 1, 'contract_version': '0.4', 'upstream': UPSTREAM,
                'artifacts': artifacts, 'source_sha256': info['source_sha256'],
                'toolchain': info['toolchain'], 'flags': info['flags'],
                'build_info': {'path': 'build-info.json', 'sha256': sha(output / 'build-info.json')},
                'checks': ['ELF32 placement, symbols, MPAUSE, positive RVV/probe instructions and call sites'],
                'execution': 'NOT_RUN: static inspection does not establish software or DUT execution'}
    destination = output / 'manifest.json'
    destination.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify', action='store_true', help='compare all freshly recomputed metadata with an existing manifest')
    args = parser.parse_args()
    saved = (args.output / 'manifest.json').read_bytes() if args.verify else None
    if args.verify:
        # Verification must not overwrite stale evidence even when it fails.
        import tempfile
        import shutil
        with tempfile.TemporaryDirectory(prefix='coralnpu-inspect-') as temporary:
            copy = Path(temporary)
            for path in args.output.iterdir():
                if path.is_file() and path.name != 'manifest.json':
                    shutil.copyfile(path, copy / path.name)
            computed = create_manifest(copy).read_bytes()
        require(computed == saved, 'Manifest differs from current files')
    else:
        create_manifest(args.output)
    print('PASS: 5 ELF32 static inspections; no execution acceptance')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, struct.error) as error:
        raise SystemExit(str(error))
