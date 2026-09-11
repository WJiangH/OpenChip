#!/usr/bin/env python3
"""Local dispatch journal; caller observations are evidence, not authentication.

No scheduler, external launcher, STATE writer, lease expiry or automatic retry.
Only explicit init creates a database. All mutations compare ledger revision.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone


class Rejected(ValueError):
    """No state change was committed."""


def require(condition, message):
    if not condition:
        raise Rejected(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def digest(value, git=False):
    return isinstance(value, str) and re.fullmatch(
        r'(?:[0-9a-f]{40}|[0-9a-f]{64})' if git else r'[0-9a-f]{64}', value)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def same(left, right):
    return canonical(left) == canonical(right)


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=object_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(Rejected('nonfinite JSON')))


def read_json(path):
    return decode(Path(path).read_bytes())


def keys(value, expected):
    require(isinstance(value, dict) and set(value) == set(expected),
            'required fields differ: ' + ', '.join(expected))


def artifact(ref):
    keys(ref, ['path', 'sha256'])
    require(text(ref['path']) and digest(ref['sha256']), 'invalid artifact reference')
    path = Path(ref['path'])
    require(path.is_absolute() and path.is_file(), 'artifact must be an existing absolute file')
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'artifact hash mismatch')
    return raw


def identity(value):
    keys(value, ['work_item', 'owner', 'candidate', 'dependencies', 'attempt'])
    require(text(value['work_item']) and text(value['owner']), 'missing work item/owner')
    require(digest(value['candidate'], git=True), 'invalid candidate digest')
    deps = value['dependencies']
    require(isinstance(deps, dict) and all(text(k) and digest(v) for k, v in deps.items()),
            'dependencies must explicitly map names to SHA256 (empty means none)')
    require(type(value['attempt']) is int and value['attempt'] > 0, 'invalid attempt')


def handle(value):
    require(isinstance(value, dict), 'missing actual handle')
    if value.get('kind') == 'worker':
        keys(value, ['kind', 'host', 'id'])
        require(text(value['host']) and text(value['id']), 'invalid worker handle')
    else:
        keys(value, ['kind', 'host', 'pid', 'start_time', 'command_sha256', 'cwd', 'nonce'])
        require(value['kind'] == 'process' and text(value['host']) and
                type(value['pid']) is int and value['pid'] > 0 and text(value['start_time']) and
                digest(value['command_sha256']) and text(value['cwd']) and
                Path(value['cwd']).is_absolute() and text(value['nonce']), 'invalid process identity')


def initialize(path):
    # Exclusive creation only. An interrupted initialization remains an error;
    # recovery must not silently erase potentially existing history.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with sqlite3.connect(path) as db:
        db.executescript('''
          CREATE TABLE meta (id INTEGER PRIMARY KEY CHECK(id=1), schema_version INTEGER,
                             ledger_id TEXT, revision INTEGER);
          CREATE TABLE runs (epoch INTEGER PRIMARY KEY AUTOINCREMENT, work_item TEXT,
                             attempt INTEGER, terminal INTEGER, record TEXT);
          CREATE UNIQUE INDEX active_item ON runs(work_item) WHERE terminal=0;
          CREATE UNIQUE INDEX unique_attempt ON runs(work_item, attempt);
          CREATE TABLE events (revision INTEGER PRIMARY KEY, event TEXT);
        ''')
        db.execute('INSERT INTO meta VALUES (1,1,?,0)', (str(uuid.uuid4()),))
    return inspect(path)


def connect(path):
    require(Path(path).is_file(), 'ledger missing; never initialize during resume')
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=rw', uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    row = db.execute('SELECT * FROM meta WHERE id=1').fetchone()
    require(row is not None and row['schema_version'] == 1, 'unsupported ledger')
    return db


def inspect(path):
    db = connect(path)
    try:
        db.execute('BEGIN')
        meta = dict(db.execute('SELECT * FROM meta').fetchone())
        return {'ledger_id': meta['ledger_id'], 'revision': meta['revision'],
                'runs': [decode(r['record']) for r in db.execute('SELECT record FROM runs ORDER BY epoch')],
                'events': [decode(r['event']) for r in db.execute('SELECT event FROM events ORDER BY revision')]}
    finally:
        db.close()


def mutate(path, operation, request, expected_revision):
    require(type(expected_revision) is int and expected_revision >= 0, 'invalid expected revision')
    db = connect(path)
    try:
        db.execute('BEGIN IMMEDIATE')
        meta = db.execute('SELECT * FROM meta').fetchone()
        require(meta['revision'] == expected_revision, 'stale ledger revision')
        if operation == 'admit':
            keys(request, ['identity', 'grant'])
            ident = request['identity']
            identity(ident)
            grant = decode(artifact(request['grant']))
            keys(grant, ['identity', 'action', 'authority'])
            require(same(grant['identity'], ident) and grant['action'] == 'dispatch' and
                    text(grant['authority']), 'grant does not match dispatch identity/authority')
            require(db.execute('SELECT 1 FROM runs WHERE work_item=? AND terminal=0',
                               (ident['work_item'],)).fetchone() is None, 'work item unresolved: HOLD')
            previous = db.execute('SELECT MAX(attempt) FROM runs WHERE work_item=?',
                                  (ident['work_item'],)).fetchone()[0]
            require(previous is None or ident['attempt'] > previous, 'attempt must increase; no replay')
            cursor = db.execute('INSERT INTO runs(work_item,attempt,terminal,record) VALUES (?,?,0,?)',
                                (ident['work_item'], ident['attempt'], '{}'))
            binding = dict(ident, ledger_id=meta['ledger_id'], epoch=cursor.lastrowid,
                           run_id=str(uuid.uuid4()), grant_sha256=request['grant']['sha256'])
            record = {'binding': binding, 'status': 'UNKNOWN', 'handle': None,
                      'grant': grant, 'grant_reference': request['grant']}
        else:
            require(operation in ('attach', 'observe', 'finish'), 'unknown operation')
            fields = ['binding', 'handle', 'evidence']
            if operation == 'observe':
                fields += ['observation']
            keys(request, fields)
            binding = request['binding']
            require(isinstance(binding, dict) and type(binding.get('epoch')) is int, 'missing binding')
            row = db.execute('SELECT * FROM runs WHERE epoch=?', (binding['epoch'],)).fetchone()
            require(row is not None and not row['terminal'], 'unknown or terminal run')
            record = decode(row['record'])
            require(same(binding, record['binding']), 'run binding mismatch')
            # Persist the exact hashed observation body, not only a mutable path.
            evidence_raw = artifact(request['evidence'])
            evidence = decode(evidence_raw)
            if operation == 'attach':
                require(record['handle'] is None, 'handle already attached')
                handle(request['handle'])
                keys(evidence, ['binding', 'handle', 'observation'])
                require(same(evidence, {'binding': binding, 'handle': request['handle'],
                                           'observation': 'HANDLE_RETURNED'}), 'handle return evidence mismatch')
                record['handle'] = request['handle']
                record['status'] = 'ACKNOWLEDGED'
            else:
                require(same(request['handle'], record['handle']), 'actual handle mismatch')
                if operation == 'observe':
                    require(request['observation'] in ('LIVE', 'UNKNOWN'), 'invalid observation')
                    require(request['observation'] != 'LIVE' or record['handle'] is not None,
                            'LIVE requires an actual handle')
                    keys(evidence, ['binding', 'handle', 'observation'])
                    require(same(evidence, {k: request[k] for k in ['binding', 'handle', 'observation']}),
                            'observation evidence mismatch')
                    record['status'] = request['observation']
                else:
                    require(record['handle'] is not None, 'completion requires reconciled actual handle')
                    completion_fields = ['binding', 'handle', 'disposition', 'exit_code', 'result',
                                         'checked_scope', 'artifacts']
                    if record['handle']['kind'] == 'worker':
                        completion_fields.append('owned_jobs')
                    keys(evidence, completion_fields)
                    require(same(evidence['binding'], binding) and same(evidence['handle'], record['handle']),
                            'completion identity mismatch')
                    if record['handle']['kind'] == 'process':
                        require(evidence['disposition'] == 'EXITED' and type(evidence['exit_code']) is int,
                                'actual exit disposition missing')
                    else:
                        require(evidence['disposition'] == 'COMPLETED' and evidence['exit_code'] is None,
                                'worker completion requires COMPLETED and unexposed exit_code null')
                        jobs = evidence['owned_jobs']
                        require(isinstance(jobs, list), 'explicit owned_jobs inventory required')
                        for job in jobs:
                            keys(job, ['handle', 'evidence'])
                            handle(job['handle'])
                            require(job['handle']['kind'] == 'process', 'unsupported external job identity')
                            observation = decode(artifact(job['evidence']))
                            keys(observation, ['binding', 'handle', 'disposition', 'exit_code'])
                            require(same(observation['binding'], binding) and
                                    same(observation['handle'], job['handle']) and
                                    observation['disposition'] == 'EXITED' and
                                    type(observation['exit_code']) is int,
                                    'owned external job unresolved: HOLD')
                    require(evidence['result'] in ('PASS', 'FAIL'), 'semantic result missing')
                    require(evidence['result'] != 'PASS' or evidence['exit_code'] in (0, None),
                            'nonzero exit cannot pass')
                    scope = evidence['checked_scope']
                    require(isinstance(scope, list) and len(scope) > 0 and all(text(v) for v in scope),
                            'checked scope missing')
                    refs = evidence['artifacts']
                    require(isinstance(refs, list) and len(refs) > 0, 'completion artifacts missing')
                    for ref in refs:
                        artifact(ref)
                    record['status'] = evidence['result']
                    record['receipt'] = request['evidence']
        revision = expected_revision + 1
        terminal = int(record['status'] in ('PASS', 'FAIL'))
        db.execute('UPDATE runs SET terminal=?,record=? WHERE epoch=?',
                   (terminal, canonical(record), binding['epoch']))
        event = {'revision': revision, 'operation': operation, 'request': request,
                 'status': record['status'], 'binding': binding,
                 'observed_at': datetime.now(timezone.utc).isoformat()}
        if operation != 'admit':
            event['evidence_body'] = evidence
        else:
            event['grant_body'] = grant
        db.execute('INSERT INTO events VALUES (?,?)', (revision, canonical(event)))
        db.execute('UPDATE meta SET revision=? WHERE id=1', (revision,))
        db.commit()
        return {'revision': revision, 'record': record, 'event': event}
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path, required=True)
    commands = parser.add_subparsers(dest='operation', required=True)
    commands.add_parser('init')
    commands.add_parser('inspect')
    for name in ('admit', 'attach', 'observe', 'finish'):
        sub = commands.add_parser(name)
        sub.add_argument('request', type=Path)
        sub.add_argument('--expected-revision', type=int, required=True)
    args = parser.parse_args()
    try:
        if args.operation == 'init':
            result = initialize(args.ledger)
        elif args.operation == 'inspect':
            result = inspect(args.ledger)
        else:
            result = mutate(args.ledger, args.operation, read_json(args.request), args.expected_revision)
        print(json.dumps(result, indent=2))
        return 0
    except (Rejected, ValueError, OSError, sqlite3.Error, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'REJECTED', 'reason': str(exc)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
