import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from freeze_extraction import digest, relative_path, verify_entries
from extract_bank_reports import ROOT, BASE


class ExtractionFreezeTests(unittest.TestCase):
    def test_holdout_scope_requires_separate_output(self):
        result = subprocess.run([sys.executable, str(ROOT/'scripts/extract_bank_reports.py'),
                                 '--scope', 'different-scope.json'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('requires --output-base', result.stderr)

    def test_holdout_cannot_overwrite_development_output(self):
        result = subprocess.run([sys.executable, str(ROOT/'scripts/extract_bank_reports.py'),
                                 '--scope', 'different-scope.json', '--output-base', str(BASE)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('must not replace', result.stderr)

    def test_unchanged_file_passes_and_change_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            file = root/'sample.json'
            file.write_text(json.dumps({'value': 100}), encoding='utf-8')
            hashes = {'sample.json': digest(file)}
            self.assertEqual(verify_entries(root, hashes), [])
            file.write_text(json.dumps({'value': 200}), encoding='utf-8')
            self.assertEqual(verify_entries(root, hashes), ['Changed: sample.json'])

    def test_missing_file_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(verify_entries(Path(folder), {'missing': 'abc'}), ['Missing: missing'])

    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                relative_path(Path(folder), '../outside.txt')

    def test_release_hash_is_portable_across_git_line_endings(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder)/'file.txt'
            file.write_bytes(b'first\nsecond\n')
            original = digest(file, True)
            file.write_bytes(b'first\r\nsecond\r\n')
            self.assertEqual(digest(file, True), original)
            self.assertNotEqual(digest(file), original)


if __name__ == '__main__':
    unittest.main()
