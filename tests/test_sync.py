import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'sync_skill.py'
spec = importlib.util.spec_from_file_location('sync_skill', SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.target = self.root / 'target'
        self.source.mkdir()
        self.target.mkdir()
        (self.source / 'VERSION').write_text('0.3.0\n')
        (self.source / 'SKILL.md').write_text('new')
        (self.target / 'SKILL.md').write_text('old')
        (self.target / 'user-notes.txt').write_text('preserve me')
        sync.build(self.source)

    def test_dry_run_never_modifies_target(self):
        result = sync.synchronize(self.source, self.target)
        self.assertIn('SKILL.md', result['changed'])
        self.assertEqual((self.target / 'SKILL.md').read_text(), 'old')

    def test_sync_backup_and_extras_preserved(self):
        result = sync.synchronize(self.source, self.target, self.root / 'backup')
        self.assertEqual((self.target / 'SKILL.md').read_text(), 'new')
        self.assertEqual((self.root / 'backup/SKILL.md').read_text(), 'old')
        self.assertEqual((self.target / 'user-notes.txt').read_text(), 'preserve me')
        self.assertEqual(sync.synchronize(self.source, self.target)['changed'], [])
        self.assertIn('user-notes.txt', result['extra'])

    def test_tampered_package_rejected_before_write(self):
        (self.source / 'SKILL.md').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'hash'):
            sync.synchronize(self.source, self.target, self.root / 'backup')
        self.assertEqual((self.target / 'SKILL.md').read_text(), 'old')

    def test_nested_target_rejected(self):
        with self.assertRaisesRegex(ValueError, 'overlap'):
            sync.synchronize(self.source, self.source / 'nested', self.root / 'backup')

    def test_backup_cannot_overwrite_existing(self):
        backup = self.root / 'backup'
        backup.mkdir()
        with self.assertRaisesRegex(ValueError, 'backup'):
            sync.synchronize(self.source, self.target, backup)

    def test_missing_support_file_detected(self):
        (self.source / 'references').mkdir()
        (self.source / 'references/guide.md').write_text('guide')
        sync.build(self.source)
        sync.synchronize(self.source, self.target, self.root / 'backup')
        (self.target / 'references/guide.md').unlink()
        self.assertIn('references/guide.md', sync.synchronize(self.source, self.target)['changed'])


if __name__ == '__main__':
    unittest.main()
