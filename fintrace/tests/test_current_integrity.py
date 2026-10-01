import hashlib,json
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_integrity import verify

class CurrentIntegrityTests(unittest.TestCase):
    def test_missing_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:self.assertFalse(verify(root=Path(folder))['unchanged'])

    def test_missing_changed_and_correct_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'releases').mkdir();(root/'input.txt').write_bytes(b'original')
            (root/'releases/current.json').write_text(json.dumps({'files_sha256':{'input.txt':hashlib.sha256(b'original').hexdigest()}}))
            self.assertTrue(verify(root=root)['unchanged'])
            (root/'input.txt').write_bytes(b'changed');self.assertFalse(verify(root=root)['unchanged'])
            (root/'input.txt').unlink();self.assertFalse(verify(root=root)['unchanged'])

    def test_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'releases').mkdir()
            (root/'releases/current.json').write_text(json.dumps({'files_sha256':{'../elsewhere':'0'*64}}))
            self.assertIn('Unsafe manifest path',verify(root=root)['errors'][0])

    def test_build_phase_never_skips_code(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'releases').mkdir()
            (root/'releases/current.json').write_text(json.dumps({'files_sha256':{'scripts/app.py':'0'*64,'data/index.bin':'0'*64}}))
            errors=verify(root=root,data_prefixes=())['errors']
            self.assertEqual(errors,['Missing: scripts/app.py'])
