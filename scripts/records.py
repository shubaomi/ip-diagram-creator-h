"""Read-only checks for private character and generation records. No image calls."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path, PureWindowsPath
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def local_path(root, value):
    require(isinstance(value, str) and value.strip(), 'path must be non-empty')
    require(not Path(value).is_absolute() and not PureWindowsPath(value).drive
            and '\\' not in value, 'path must be relative with forward slashes')
    root = Path(root).resolve()
    path = (root / value).resolve()
    require(path.is_relative_to(root) and path != root, 'path escapes data root')
    return path


def read(path):
    value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    require(isinstance(value, dict), f'{path}: expected JSON object')
    require(value.get('schema_version') == 1, f'{path}: unsupported schema_version')
    return value


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f'{label}: non-empty text required')


def approval(value, label):
    require(isinstance(value, dict) and value.get('source') == 'user', f'{label}: user evidence required')
    text(value.get('evidence'), label)
    text(value.get('at'), label)
    stamp = datetime.fromisoformat(value['at'].replace('Z', '+00:00'))
    require(stamp.tzinfo is not None, f'{label}: timestamp needs timezone')


def asset(root, value):
    require(isinstance(value, dict), 'asset must be an object')
    path = local_path(root, value.get('path'))
    require(path.is_file(), f'missing file: {value.get("path")}')
    require(sha256(path) == value.get('sha256'), f'hash mismatch: {value.get("path")}')
    return path


def no_cycles(entries, parent_key):
    for key in entries:
        visited = set()
        current = key
        while current is not None:
            require(current in entries, f'unknown parent: {current}')
            require(current not in visited, f'parent cycle: {current}')
            visited.add(current)
            current = entries[current].get(parent_key)


def character_versions(root, doc):
    text(doc.get('character_id'), 'character_id')
    require(isinstance(doc.get('versions'), list), 'versions must be a list')
    versions = {}
    for version in doc['versions']:
        require(isinstance(version, dict), 'version must be an object')
        key = version.get('version')
        text(key, 'version')
        require(key not in versions, 'duplicate character version')
        versions[key] = version
        require(version.get('status') in ('candidate', 'approved', 'rejected'), 'invalid character status')
        text(version.get('change_request'), 'change_request')
        anchors = version.get('anchors', {})
        require(isinstance(anchors, dict), 'anchors must be an object')
        for field in ('face', 'outfit', 'style'):
            require(isinstance(anchors.get(field), list) and anchors[field], f'anchors.{field} required')
            for entry in anchors[field]:
                text(entry, field)
        require(isinstance(version.get('assets'), list), 'assets must be a list')
        roles = []
        for entry in version['assets']:
            require(isinstance(entry, dict), 'character asset must be an object')
            require(entry.get('role') in ('main', 'action', 'spec'), 'invalid character asset role')
            require(entry['role'] not in roles, 'duplicate character asset role')
            roles.append(entry['role'])
            asset(root, entry)
        if version['status'] == 'approved':
            approval(version.get('approval'), 'character approval')
            require('main' in roles, 'approved character needs main anchor')
    no_cycles(versions, 'parent_version')
    active = doc.get('active_version')
    if active is not None:
        require(active in versions and versions[active]['status'] == 'approved', 'active version must be approved')
    return versions


def validate_run(root, run, versions, batch):
    for field in ('run_id', 'item_id', 'batch_id', 'change_request'):
        text(run.get(field), field)
    require(run['batch_id'] == batch['batch_id'], 'batch_id mismatch')
    require(run['item_id'] in batch['items'], 'unknown item_id')
    require(run.get('mode') == batch['mode'], 'mode mismatch')
    require(run.get('purpose') in ('character', 'content'), 'invalid purpose')
    require((run['purpose'] == 'character') == (run['mode'] == 'character'), 'purpose/mode mismatch')
    require(type(run.get('uses_character')) is bool, 'uses_character must be boolean')
    require(run.get('status') in ('planned', 'running', 'generated', 'failed', 'unknown'), 'invalid run status')
    for field in ('preserve', 'change'):
        require(isinstance(run.get(field), list), f'{field} must be a list')
        for entry in run[field]:
            text(entry, field)
    version = versions.get(run.get('character_version'))
    require(version is not None, 'unknown character version')
    if run['purpose'] == 'content':
        require(version['status'] == 'approved', 'content needs approved character version')
    asset(root, run.get('prompt'))
    require(isinstance(run.get('references'), list), 'references must be a list')
    refs = []
    for ref in run['references']:
        require(isinstance(ref, dict), 'reference must be an object')
        require(ref.get('role') in ('main', 'action', 'spec', 'source', 'style', 'edit'), 'invalid reference role')
        refs.append(asset(root, ref))
    require(len(set(refs)) == len(refs), 'duplicate reference file')
    if run['uses_character'] and run['purpose'] == 'content':
        main = next(item for item in version['assets'] if item['role'] == 'main')
        require(any(ref.get('role') == 'main' and ref['path'] == main['path']
                    and ref['sha256'] == main['sha256'] for ref in run['references']),
                'approved main anchor must be included')
    backend = run.get('backend', {})
    require(isinstance(backend, dict), 'backend must be an object')
    text(backend.get('tool'), 'backend.tool')
    require(type(backend.get('supports_references')) is bool, 'supports_references must be boolean')
    if refs and not backend['supports_references']:
        approval(run.get('downgrade_approval'), 'reference downgrade approval')
    output_path = local_path(root, run.get('output_path'))
    if run['status'] == 'planned':
        require(not output_path.exists(), 'planned output already exists; reconcile instead of overwriting')
    invocation = run.get('invocation')
    if run['status'] == 'generated':
        require(isinstance(invocation, dict), 'generated run needs actual invocation')
        require(asset(root, run.get('output')) == output_path, 'output path mismatch')
    elif run.get('output') is not None:
        raise ValueError('only generated runs can claim an output')
    if invocation is not None:
        require(isinstance(invocation, dict), 'invocation must be an object')
        require(invocation.get('tool') == backend['tool'], 'invocation tool mismatch')
        asset(root, invocation.get('receipt'))
        args = invocation.get('arguments')
        require(isinstance(args, dict), 'invocation arguments required')
        parameter = invocation.get('reference_parameter')
        actual = args.get(parameter, []) if parameter else []
        require(isinstance(actual, list), 'reference arguments must be a path list')
        resolved = []
        for value in actual:
            text(value, 'actual reference path')
            path = Path(value)
            resolved.append(path.resolve() if path.is_absolute() else local_path(root, value))
        expected = refs if backend['supports_references'] else []
        require(resolved == expected, 'actual reference arguments differ from planned references')
    qa = run.get('qa', {})
    require(isinstance(qa, dict), 'qa must be an object')
    require(qa.get('status') in ('pending', 'pass', 'fail'), 'invalid QA status')
    if qa['status'] != 'pending':
        require(run['status'] == 'generated', 'QA requires generated output')
        asset(root, qa.get('evidence'))
    if run.get('user_review') is not None:
        approval(run['user_review'], 'user review')
        require(run['user_review'].get('decision') in ('approved', 'rejected'), 'invalid user decision')
        require(run['status'] == 'generated', 'user review requires generated output')
    return output_path


def check(root, preflight=None):
    root = Path(root).resolve()
    versions = character_versions(root, read(root / 'character.json'))
    batch = read(root / 'batch.json')
    text(batch.get('batch_id'), 'batch_id')
    require(batch.get('mode') in ('character', 'illustration', 'knowledge-card', 'ppt'), 'invalid batch mode')
    items = batch.get('items')
    require(isinstance(items, list) and items, 'batch items required')
    for item in items:
        text(item, 'item')
    require(len(set(items)) == len(items), 'duplicate batch item')
    require(isinstance(batch.get('latest_runs'), dict) and set(batch['latest_runs']) == set(items),
            'latest_runs must cover each item (null allowed)')
    samples = batch.get('sample_items')
    require(isinstance(samples, list) and set(samples) <= set(items), 'invalid sample_items')
    gates = batch.get('approvals', {})
    require(isinstance(gates, dict), 'approvals must be an object')
    for gate in ('plan', 'samples'):
        if gates.get(gate) is not None:
            approval(gates[gate], gate)
    if batch['mode'] == 'ppt':
        require(1 <= len(samples) <= 2, 'PPT needs 1-2 sample items')
    runs = {}
    outputs = set()
    for path in sorted((root / 'generations').glob('*.json')):
        run = read(path)
        output = validate_run(root, run, versions, batch)
        require(run['run_id'] not in runs, 'duplicate run_id')
        require(output not in outputs, 'output reused by multiple attempts')
        outputs.add(output)
        runs[run['run_id']] = run
    no_cycles(runs, 'parent_run')
    for run in runs.values():
        if run.get('parent_run'):
            require(runs[run['parent_run']]['item_id'] == run['item_id'], 'repair parent item mismatch')
    result = {key: [] for key in ('to_generate', 'in_flight', 'reconcile', 'review', 'repair', 'approved')}
    for item, latest in batch['latest_runs'].items():
        if latest is None:
            require(not any(r['item_id'] == item for r in runs.values()), 'unindexed existing run; reconcile')
            result['to_generate'].append(item)
            continue
        require(latest in runs and runs[latest]['item_id'] == item, 'latest run missing or wrong item')
        run = runs[latest]
        status = run['status']
        unresolved = [r['status'] for r in runs.values() if r['item_id'] == item
                      and r['status'] in ('running', 'unknown')]
        if unresolved:
            result['reconcile' if 'unknown' in unresolved else 'in_flight'].append(item)
        elif status in ('planned', 'failed'):
            result['to_generate'].append(item)
        elif run['qa']['status'] == 'fail' or (run.get('user_review') or {}).get('decision') == 'rejected':
            result['repair'].append(item)
        elif (run.get('user_review') or {}).get('decision') == 'approved':
            result['approved'].append(item)
        else:
            result['review'].append(item)
    if preflight:
        require(preflight in runs, 'unknown preflight run')
        run = runs[preflight]
        require(run['status'] == 'planned', 'preflight requires planned attempt')
        require(batch['latest_runs'][run['item_id']] == preflight, 'preflight must target latest attempt')
        require(not any(r['item_id'] == run['item_id'] and r['status'] in ('running', 'unknown')
                        for r in runs.values()), 'reconcile earlier attempt before retry')
        require(run.get('invocation') is None, 'planned attempt already invoked; reconcile')
        if batch['mode'] == 'ppt':
            approval(gates.get('plan'), 'PPT plan')
            if run['item_id'] not in samples:
                approval(gates.get('samples'), 'PPT samples')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--preflight', help='Validate a planned run immediately before generation')
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.root, args.preflight), ensure_ascii=True, indent=2))
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as exc:
        print(f'INVALID: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
