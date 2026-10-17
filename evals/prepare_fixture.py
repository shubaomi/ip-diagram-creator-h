"""Create a private, synthetic workflow fixture from an existing public sample."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil


def prepare(root):
    root = Path(root)
    if root.exists():
        raise ValueError('Use a new fixture directory; existing results are never overwritten')
    package = Path(__file__).resolve().parents[1]
    root.mkdir(parents=True)
    (root / 'generations').mkdir()
    shutil.copy2(package / 'assets/examples/gallery/character-assets-sample.png', root / 'anchor.png')
    (root / 'prompt.md').write_text('Synthetic fixture: preserve the public sample character.\n', encoding='utf-8')
    (root / 'receipt.json').write_text('{"fixture": true, "real_generation": false}\n', encoding='utf-8')

    def asset(name):
        with (root / name).open('rb') as stream:
            return {'path': name, 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}

    approval = {'source': 'user', 'evidence': 'SYNTHETIC TEST ONLY: fictional user approved demo v1', 'at': '2026-10-16T12:00:00Z'}
    character = {'schema_version': 1, 'character_id': 'fictional-demo', 'active_version': 'v1', 'versions': [
        {'version': 'v1', 'parent_version': None, 'status': 'approved', 'approval': approval,
         'change_request': 'Synthetic baseline', 'anchors': {'face': ['match public sample'], 'outfit': ['match public sample'], 'style': ['hand-drawn']},
         'assets': [dict(asset('anchor.png'), role='main')]}
    ]}
    batch = {'schema_version': 1, 'batch_id': 'fixture', 'mode': 'knowledge-card', 'items': ['01', '02', '03', '04'],
             'latest_runs': {'01': '01-v1', '02': '02-v1', '03': '03-v1', '04': None},
             'sample_items': [], 'approvals': {'plan': approval, 'samples': None}}
    for item, status in [('01', 'generated'), ('02', 'unknown'), ('03', 'failed')]:
        run = {'schema_version': 1, 'run_id': item + '-v1', 'item_id': item, 'batch_id': 'fixture',
               'parent_run': None, 'purpose': 'content', 'mode': 'knowledge-card', 'character_version': 'v1',
               'uses_character': True, 'status': status, 'change_request': 'Synthetic attempt',
               'preserve': ['identity'], 'change': ['pose'], 'prompt': asset('prompt.md'),
               'references': [dict(asset('anchor.png'), role='main')],
               'backend': {'tool': 'synthetic-fixture', 'supports_references': True}, 'downgrade_approval': None,
               'invocation': None, 'output_path': item + '.png', 'output': None,
               'qa': {'status': 'pending', 'evidence': None}, 'user_review': None}
        if status == 'generated':
            shutil.copy2(root / 'anchor.png', root / (item + '.png'))
            run['output'] = asset(item + '.png')
            run['invocation'] = {'tool': 'synthetic-fixture', 'reference_parameter': 'referenced_image_paths',
                                 'arguments': {'referenced_image_paths': ['anchor.png']}, 'receipt': asset('receipt.json')}
        (root / 'generations' / (run['run_id'] + '.json')).write_text(json.dumps(run, indent=2) + '\n', encoding='utf-8')
    for name, value in [('character.json', character), ('batch.json', batch)]:
        (root / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    (root / 'FIXTURE.txt').write_text('Synthetic workflow data; copied public sample. No actual image call or real user approval.\n', encoding='utf-8')
    return root


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(prepare(args.output))
