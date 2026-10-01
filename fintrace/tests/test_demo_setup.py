import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from prepare_demo import digest, download, install_bundle, model_url, prepare, target_path
from package_demo_data import package


def sha(data):
    return hashlib.sha256(data).hexdigest()


class DemoSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'checkout'
        self.root.mkdir()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def archive(self, entries):
        path = self.base / 'bundle.zip'
        with ZipFile(path, 'w') as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return path

    def test_bundle_restores_exact_files(self):
        name = 'data/processed/a.json'
        bundle = self.archive({name: b'checked evidence'})
        install_bundle(bundle, self.root, {name: sha(b'checked evidence')}, digest(bundle))
        self.assertEqual((self.root / name).read_bytes(), b'checked evidence')
        install_bundle(bundle, self.root, {name: sha(b'checked evidence')}, digest(bundle))

    def test_bundle_checksum_required(self):
        bundle = self.archive({'data/processed/a': b'a'})
        with self.assertRaisesRegex(ValueError, 'bundle checksum'):
            install_bundle(bundle, self.root, {'data/processed/a': sha(b'a')}, '0' * 64)
        self.assertFalse((self.root / 'data').exists())

    def test_extra_archive_members_rejected(self):
        bundle = self.archive({'data/processed/a': b'a', '.env': b'not allowed'})
        with self.assertRaisesRegex(ValueError, 'exactly'):
            install_bundle(bundle, self.root, {'data/processed/a': sha(b'a')}, digest(bundle))

    def test_archive_path_escape_rejected(self):
        name = '../outside'
        bundle = self.archive({name: b'a'})
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            install_bundle(bundle, self.root, {name: sha(b'a')}, digest(bundle))

    def test_windows_and_absolute_paths_rejected(self):
        for name in ('C:/outside', '/outside', 'data/../outside', 'data\\outside', 'data/file:stream'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                target_path(self.root, name)

    def test_all_members_checked_before_installation(self):
        bundle = self.archive({'data/processed/a': b'a', 'data/processed/b': b'wrong'})
        expected = {'data/processed/a': sha(b'a'), 'data/processed/b': sha(b'b')}
        with self.assertRaisesRegex(ValueError, 'member checksum'):
            install_bundle(bundle, self.root, expected, digest(bundle))
        self.assertFalse((self.root / 'data').exists())

    def test_existing_changed_file_not_overwritten(self):
        name = 'data/processed/a'
        self.write(name, b'local work')
        bundle = self.archive({name: b'a'})
        with self.assertRaisesRegex(ValueError, 'Existing artifact differs'):
            install_bundle(bundle, self.root, {name: sha(b'a')}, digest(bundle))
        self.assertEqual((self.root / name).read_bytes(), b'local work')

    def test_model_download_uses_pinned_revision(self):
        revision = 'a' * 40
        for prefix in ('models/retrieval', 'models/huggingface/hub'):
            name = f'{prefix}/models--Qwen--Qwen3-Embedding-0.6B/snapshots/{revision}/1_Pooling/config.json'
            self.assertEqual(model_url(name), f'https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/resolve/{revision}/1_Pooling/config.json')
        with self.assertRaises(ValueError):
            model_url('models/unpinned.bin')

    def test_bad_download_is_not_installed(self):
        target = self.root / 'model.bin'
        with patch('prepare_demo.urlopen', return_value=io.BytesIO(b'wrong')):
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                download('https://example.com/file', target, sha(b'correct'))
        self.assertFalse(target.exists())

    def test_good_download_is_verified_and_reused(self):
        target = self.root / 'model.bin'
        with patch('prepare_demo.urlopen', return_value=io.BytesIO(b'correct')) as network:
            download('https://example.com/file', target, sha(b'correct'))
            download('https://example.com/file', target, sha(b'correct'))
            self.assertEqual(network.call_count, 1)

    def test_packager_excludes_raw_models_and_credentials(self):
        names = ('data/processed/evidence.json', 'data/raw/report.pdf', 'models/model.bin', '.env')
        hashes = {name: sha(self.write(name, name.encode()).read_bytes()) for name in names}
        self.write('releases/current.json', json.dumps({'files_sha256': hashes}).encode())
        out = self.base / 'release.zip'
        package(self.root, out)
        with ZipFile(out) as bundle:
            self.assertEqual(bundle.namelist(), ['data/processed/evidence.json'])
        with self.assertRaises(FileExistsError):
            package(self.root, out)

    def test_offline_fresh_artifact_install_and_repeat(self):
        code = self.write('scripts/app.py', b'code')
        expected = {'scripts/app.py': digest(code), 'data/processed/evidence': sha(b'evidence')}
        manifest = self.write('releases/current.json', json.dumps({'files_sha256': expected}).encode())
        bundle = self.archive({'data/processed/evidence': b'evidence'})
        spec = {'manifest_sha256': digest(manifest), 'asset_sha256': digest(bundle)}
        self.write('config/setup_artifacts.json', json.dumps(spec).encode())
        self.write('config/banking_sources.json', b'{"documents": []}')
        with patch('prepare_demo.urlopen', side_effect=AssertionError('Network not allowed')):
            prepare(self.root, bundle=bundle, offline=True)
            prepare(self.root, offline=True)

    def test_manifest_change_stops_setup(self):
        self.write('releases/current.json', b'{"files_sha256": {}}')
        self.write('config/setup_artifacts.json', json.dumps({'manifest_sha256': '0' * 64}).encode())
        with self.assertRaisesRegex(ValueError, 'does not match'):
            prepare(self.root)
