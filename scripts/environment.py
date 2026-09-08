#!/usr/bin/env python3
"""Discover private runtime profiles and run a bounded, reviewed no-DUT adapter."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

STATUSES = {'READY_NO_DUT', 'NOT_CONFIGURED', 'NO_ACCESS', 'STALE_IDENTITY',
            'MISSING_LIBRARY', 'TIMEOUT', 'PROBE_FAILED'}


def private_store(root):
    common = subprocess.check_output(['git', 'rev-parse', '--git-common-dir'],
                                     cwd=root, text=True).strip()
    return (root / common).resolve().parent / '.local-designs/environments'


def inside(root, relative):
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    return path


def check(store, profile_path):
    """Return status and durable receipt; do not infer readiness from exit zero."""
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    receipt = store / 'receipts' / (run_id + '-' + uuid.uuid4().hex[:8])
    receipt.mkdir(parents=True)
    result = {'status': 'NOT_CONFIGURED', 'dut_executed': False}
    start = time.monotonic()
    try:
        profile_bytes = profile_path.read_bytes()
        profile = json.loads(profile_bytes)
        if profile['schema_version'] != 1:
            raise ValueError('unsupported schema')
        timeout = profile['timeout_seconds']
        if not isinstance(timeout, int) or not 1 <= timeout <= 60:
            raise ValueError('timeout must be 1..60 seconds')
        adapter = inside(profile_path.parent, profile['adapter'])
        adapter_bytes = adapter.read_bytes()
        if hashlib.sha256(adapter_bytes).hexdigest() != profile['adapter_sha256']:
            result['status'] = 'STALE_IDENTITY'
        else:
            (receipt / 'profile.json').write_bytes(profile_bytes)
            (receipt / 'adapter.py').write_bytes(adapter_bytes)
            command = [sys.executable, str(receipt / 'adapter.py'),
                       str(receipt / 'profile.json'), str(receipt)]
            with (receipt / 'adapter.log').open('w') as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                try:
                    code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    result['status'] = 'TIMEOUT'
                else:
                    try:
                        observed = json.loads((receipt / 'result.json').read_text())
                        status = observed['status']
                        if status not in STATUSES or observed.get('dut_executed') is not False:
                            raise ValueError('invalid adapter result')
                        result['status'] = status if code == 0 else 'PROBE_FAILED'
                    except (OSError, ValueError, KeyError):
                        result['status'] = 'PROBE_FAILED'
                result['adapter_exit'] = process.returncode
    except PermissionError:
        result['status'] = 'NO_ACCESS'
    except (OSError, ValueError, KeyError, TypeError):
        result['status'] = 'NOT_CONFIGURED'
    result['wall_seconds'] = time.monotonic() - start
    if result['status'] == 'TIMEOUT':
        result['remote_completion'] = 'unconfirmed'
        result['recovery'] = 'Confirm this adapter invocation has exited remotely before shared-runtime reuse; preserve private profile and logs'
    (receipt / 'launcher.json').write_text(json.dumps(result, indent=2) + '\n')
    return result['status'], receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, help='explicit approved private environment store')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list')
    action = sub.add_parser('check')
    action.add_argument('profile')
    args = parser.parse_args(argv)
    try:
        store = (args.store or private_store(Path(__file__).resolve().parents[1])).resolve()
        index = json.loads((store / 'index.json').read_text())
        profiles = index['profiles']
        if args.command == 'list':
            print('Private environment index: ' + str(store / 'README.md'))
            for key, value in sorted(profiles.items()):
                profile = json.loads(inside(store, value).read_text())
                print(key + ' — owner: ' + profile['owner'])
            return 0
        path = inside(store, profiles[args.profile])
        status, receipt = check(store, path)
        print(status + ' | receipt: ' + str(receipt))
        return 0 if status == 'READY_NO_DUT' else 1
    except PermissionError:
        print('NO_ACCESS | approved private environment store is inaccessible')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print('NOT_CONFIGURED | consult flow/README.md and the private environment owner')
    return 1


if __name__ == '__main__':
    sys.exit(main())
