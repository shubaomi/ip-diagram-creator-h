import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'records.py'
spec = importlib.util.spec_from_file_location('records', SCRIPT)
records = importlib.util.module_from_spec(spec)
spec.loader.exec_module(records)


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'generations').mkdir()
        sample = SCRIPT.parents[1] / 'assets/examples/gallery/character-assets-sample.png'
        shutil.copyfile(sample, self.root / 'anchor.png')
        (self.root / 'prompt.md').write_text('Keep approved face; plain white T-shirt.', encoding='utf-8')
        (self.root / 'receipt.json').write_text('{"test_fixture": true}', encoding='utf-8')
        self.approval = {'source': 'user', 'evidence': 'fixture: user approved v1', 'at': '2026-10-16T12:00:00Z'}
        self.character = {'schema_version': 1, 'character_id': 'demo', 'active_version': 'v1', 'versions': [
            {'version': 'v1', 'parent_version': None, 'status': 'approved', 'approval': self.approval,
             'change_request': 'Initial reference', 'anchors': {'face': ['slim oval'], 'outfit': ['white T-shirt'], 'style': ['hand-drawn']},
             'assets': [dict(self.asset('anchor.png'), role='main')]}
        ]}
        self.batch = {'schema_version': 1, 'batch_id': 'demo', 'mode': 'knowledge-card',
                      'items': ['01'], 'latest_runs': {'01': 'r1'}, 'sample_items': [],
                      'approvals': {'plan': None, 'samples': None}}
        self.run = {'schema_version': 1, 'run_id': 'r1', 'item_id': '01', 'batch_id': 'demo',
                    'parent_run': None, 'purpose': 'content', 'mode': 'knowledge-card',
                    'character_version': 'v1', 'uses_character': True, 'status': 'planned',
                    'change_request': 'New card', 'preserve': ['face', 'outfit'], 'change': ['pose'],
                    'prompt': self.asset('prompt.md'), 'references': [dict(self.asset('anchor.png'), role='main')],
                    'backend': {'tool': 'fixture', 'supports_references': True}, 'downgrade_approval': None,
                    'invocation': None, 'output_path': 'r1.png', 'output': None,
                    'qa': {'status': 'pending', 'evidence': None}, 'user_review': None}

    def asset(self, name):
        return {'path': name, 'sha256': records.sha256(self.root / name)}

    def save(self, runs=None):
        for name, data in [('character.json', self.character), ('batch.json', self.batch)]:
            (self.root / name).write_text(json.dumps(data), encoding='utf-8')
        for run in runs or [self.run]:
            (self.root / 'generations' / (run['run_id'] + '.json')).write_text(json.dumps(run), encoding='utf-8')

    def generated(self):
        shutil.copyfile(self.root / 'anchor.png', self.root / 'r1.png')
        self.run.update(status='generated', output=self.asset('r1.png'), invocation={
            'tool': 'fixture', 'reference_parameter': 'referenced_image_paths',
            'arguments': {'referenced_image_paths': [str(self.root / 'anchor.png')]},
            'receipt': self.asset('receipt.json')})

    def test_planned_preflight_and_resume(self):
        self.save()
        result = records.check(self.root, preflight='r1')
        self.assertEqual(result['to_generate'], ['01'])

    def test_candidate_cannot_be_active(self):
        self.character['versions'][0]['status'] = 'candidate'
        self.save()
        with self.assertRaisesRegex(ValueError, 'approved'):
            records.check(self.root)

    def test_approval_requires_user_evidence(self):
        self.character['versions'][0]['approval']['source'] = 'model'
        self.save()
        with self.assertRaisesRegex(ValueError, 'user'):
            records.check(self.root)

    def test_reference_hash_drift(self):
        self.save()
        (self.root / 'anchor.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash'):
            records.check(self.root)

    def test_missing_reference_not_prompt_only_success(self):
        self.generated()
        self.run['invocation']['arguments']['referenced_image_paths'] = []
        self.save()
        with self.assertRaisesRegex(ValueError, 'reference'):
            records.check(self.root)

    def test_latest_candidate_not_used_as_main(self):
        shutil.copyfile(self.root / 'anchor.png', self.root / 'candidate.png')
        self.run['references'] = [dict(self.asset('candidate.png'), role='main')]
        self.save()
        with self.assertRaisesRegex(ValueError, 'anchor'):
            records.check(self.root)

    def test_output_does_not_imply_human_approval(self):
        self.generated()
        self.save()
        result = records.check(self.root)
        self.assertEqual(result['to_generate'], [])
        self.assertEqual(result['review'], ['01'])
        self.assertIsNone(self.run['user_review'])

    def test_unknown_not_retried(self):
        self.run['status'] = 'unknown'
        self.save()
        self.assertEqual(records.check(self.root)['reconcile'], ['01'])
        with self.assertRaisesRegex(ValueError, 'planned'):
            records.check(self.root, preflight='r1')

    def test_targeted_repair_preserves_original(self):
        self.generated()
        previous = copy.deepcopy(self.run)
        self.run.update(run_id='r2', parent_run='r1', status='planned', output_path='r2.png',
                        output=None, invocation=None, change=['title'], preserve=['face', 'outfit', 'composition'])
        self.batch['latest_runs']['01'] = 'r2'
        self.save([previous, self.run])
        self.assertEqual(records.check(self.root, preflight='r2')['to_generate'], ['01'])
        self.assertTrue((self.root / 'r1.png').exists())

    def test_duplicate_output_rejected(self):
        previous = copy.deepcopy(self.run)
        self.run.update(run_id='r2', parent_run='r1')
        self.batch['latest_runs']['01'] = 'r2'
        self.save([previous, self.run])
        with self.assertRaisesRegex(ValueError, 'output'):
            records.check(self.root)

    def test_path_escape_rejected(self):
        self.run['output_path'] = '../outside.png'
        self.save()
        with self.assertRaisesRegex(ValueError, 'path'):
            records.check(self.root)

    def test_ppt_batch_waits_for_sample_approval(self):
        self.batch.update(mode='ppt', sample_items=['01'], items=['01', '02'], latest_runs={'01': 'r1', '02': 'r2'})
        self.batch['approvals']['plan'] = self.approval
        self.run['mode'] = 'ppt'
        second = copy.deepcopy(self.run)
        second.update(run_id='r2', item_id='02', output_path='r2.png')
        self.save([self.run, second])
        records.check(self.root, preflight='r1')
        with self.assertRaisesRegex(ValueError, 'samples'):
            records.check(self.root, preflight='r2')
        self.batch['approvals']['samples'] = self.approval
        self.save([self.run, second])
        records.check(self.root, preflight='r2')

    def test_unsupported_backend_needs_explicit_downgrade(self):
        self.run['backend']['supports_references'] = False
        self.save()
        with self.assertRaisesRegex(ValueError, 'downgrade'):
            records.check(self.root, preflight='r1')
        self.run['downgrade_approval'] = self.approval
        self.save()
        records.check(self.root, preflight='r1')

    def test_parent_cycle_rejected(self):
        self.character['versions'][0]['parent_version'] = 'v1'
        self.save()
        with self.assertRaisesRegex(ValueError, 'cycle'):
            records.check(self.root)

    def test_earlier_unknown_cannot_be_hidden_by_new_plan(self):
        old = copy.deepcopy(self.run)
        old['status'] = 'unknown'
        self.run.update(run_id='r2', parent_run='r1', output_path='r2.png')
        self.batch['latest_runs']['01'] = 'r2'
        self.save([old, self.run])
        result = records.check(self.root)
        self.assertEqual(result['to_generate'], [])
        self.assertEqual(result['reconcile'], ['01'])
        with self.assertRaisesRegex(ValueError, 'reconcile'):
            records.check(self.root, preflight='r2')

    def test_planned_output_existing_requires_reconciliation(self):
        shutil.copyfile(self.root / 'anchor.png', self.root / 'r1.png')
        self.save()
        with self.assertRaisesRegex(ValueError, 'reconcile'):
            records.check(self.root, preflight='r1')

    def test_ppt_no_character_page_does_not_require_main_reference(self):
        self.batch.update(mode='ppt', sample_items=['01'])
        self.batch['approvals']['plan'] = self.approval
        self.run.update(mode='ppt', uses_character=False, references=[])
        self.save()
        records.check(self.root, preflight='r1')

    def test_initial_character_can_be_candidate(self):
        self.character['active_version'] = None
        version = self.character['versions'][0]
        version.update(status='candidate', approval=None, assets=[])
        self.batch['mode'] = 'character'
        self.run.update(mode='character', purpose='character', references=[])
        self.save()
        records.check(self.root, preflight='r1')

    def test_qa_pass_is_not_user_acceptance(self):
        self.generated()
        (self.root / 'qa.md').write_text('Fixture objective checks only.', encoding='utf-8')
        self.run['qa'] = {'status': 'pass', 'evidence': self.asset('qa.md')}
        self.save()
        self.assertEqual(records.check(self.root)['review'], ['01'])


if __name__ == '__main__':
    unittest.main()
