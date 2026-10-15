import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'target'
        self.target.mkdir()
        (self.target / 'ask-zcode.py').write_text('old bridge\n')
        (self.target / 'unrelated.txt').write_text('keep\n')
        self.plan = self.root / 'plan.json'
        self.command = [sys.executable, str(ROOT / 'install.py'), '--target', str(self.target), '--plan', str(self.plan)]
        self.assertEqual(subprocess.run(self.command + ['--prepare'], capture_output=True).returncode, 0)

    def test_backup_hashes_and_unrelated_content_are_preserved(self):
        result = subprocess.run(self.command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual((Path(receipt['backup']) / 'ask-zcode.py').read_text(), 'old bridge\n')
        self.assertEqual((self.target / 'unrelated.txt').read_text(), 'keep\n')
        self.assertEqual((self.target / 'ask-zcode.py').read_bytes(), (ROOT / 'ask-zcode.py').read_bytes())

    def test_changed_target_refuses_before_writing(self):
        (self.target / 'ask-zcode.py').write_text('new user change\n')
        result = subprocess.run(self.command, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.target / 'ask-zcode.py').read_text(), 'new user change\n')
        self.assertFalse((self.target / '.backups').exists())
        self.assertFalse((self.target / 'bridge.py').exists())


if __name__ == '__main__':
    unittest.main()
