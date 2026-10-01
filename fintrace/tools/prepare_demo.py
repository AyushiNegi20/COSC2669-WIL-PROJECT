"""Install the manifest-pinned demo artifacts without transferring a work folder.

Uses Python's standard library. GitHub CLI handles private-release authentication;
no credentials are read from or written to the repository.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def target_path(root, name):
    parts = PurePosixPath(name).parts
    if not parts or '\\' in name or ':' in name or name.startswith('/') or '..' in parts:
        raise ValueError(f'Unsafe artifact path: {name}')
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Artifact escapes checkout: {name}')
    return path


def already_present(path, expected):
    if not path.exists():
        return False
    if not path.is_file() or digest(path) != expected:
        raise ValueError(f'Existing artifact differs; preserve and investigate: {path}')
    return True


def download(url, target, expected):
    if already_present(target, expected):
        return
    if not url.startswith('https://'):
        raise ValueError('Only HTTPS downloads are supported')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fintrace-download-', dir=target.parent) as folder:
        staging = Path(folder) / 'download'
        request = Request(url, headers={'User-Agent': 'FinTrace artifact setup'})
        with urlopen(request, timeout=180) as source, staging.open('wb') as out:
            shutil.copyfileobj(source, out)
        if digest(staging) != expected:
            raise ValueError(f'Download checksum mismatch: {target.name}')
        if not already_present(target, expected):
            staging.replace(target)


def model_url(name):
    match = re.fullmatch(
        r'models/(?:retrieval|huggingface/hub)/models--([^/]+)/snapshots/([0-9a-f]{40})/(.+)', name)
    if not match:
        raise ValueError(f'Unrecognised pinned model path: {name}')
    repository, revision, filename = match.groups()
    namespace, separator, model = repository.partition('--')
    if not separator:
        raise ValueError(f'Missing model namespace: {name}')
    return f'https://huggingface.co/{quote(namespace)}/{quote(model)}/resolve/{revision}/{quote(filename, safe="/")}'


def install_bundle(bundle, root, expected_files, bundle_sha256):
    if digest(bundle) != bundle_sha256:
        raise ValueError('Evidence bundle checksum mismatch')
    with ZipFile(bundle) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names) or set(names) != set(expected_files):
            raise ValueError('Evidence bundle must contain exactly the expected processed files')
        # Validate all members before installing any, never use extractall.
        for name in names:
            target_path(root, name)
            with archive.open(name) as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != expected_files[name]:
                    raise ValueError(f'Bundle member checksum mismatch: {name}')
        for name in names:
            destination = target_path(root, name)
            if already_present(destination, expected_files[name]):
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='fintrace-install-', dir=destination.parent) as folder:
                staging = Path(folder) / 'verified'
                with archive.open(name) as source, staging.open('wb') as out:
                    shutil.copyfileobj(source, out)
                if not already_present(destination, expected_files[name]):
                    staging.replace(destination)


def prepare(root=ROOT, bundle=None, offline=False):
    manifest_path = root / 'releases/current.json'
    files = json.loads(manifest_path.read_text(encoding='utf-8'))['files_sha256']
    spec = json.loads((root / 'config/setup_artifacts.json').read_text(encoding='utf-8'))
    if digest(manifest_path) != spec['manifest_sha256']:
        raise ValueError('This artifact release does not match releases/current.json')
    # Check all existing files before downloads; do not overwrite local changes.
    missing = []
    for name, expected in files.items():
        if not already_present(target_path(root, name), expected):
            if not name.startswith(('data/', 'models/')):
                raise ValueError(f'Missing code/config file; restore checkout: {name}')
            missing.append(name)
    if not missing:
        print('All manifest files already verified. No downloads needed.')
        return
    processed = {k: v for k, v in files.items() if k.startswith('data/processed/')}
    documents = json.loads((root / 'config/banking_sources.json').read_text(encoding='utf-8'))['documents']
    pdfs = {'data/raw/' + doc['file']: doc for doc in documents}
    remote = []
    for name in missing:
        if name in processed:
            continue
        if name in pdfs:
            doc = pdfs[name]
            if doc['sha256'] != files[name]:
                raise ValueError(f'Source manifest disagreement: {name}')
            url = doc['url']
        elif name.startswith('models/'):
            url = model_url(name)
        else:
            raise ValueError(f'No supported artifact source: {name}')
        remote.append((name, url))
    needs_bundle = any(name in processed for name in missing)
    if offline and (remote or (needs_bundle and bundle is None)):
        raise ValueError('Offline setup needs a local bundle and all source PDFs/model files already present')
    if needs_bundle:
        if bundle is not None:
            install_bundle(bundle, root, processed, spec['asset_sha256'])
        else:
            if shutil.which('gh') is None:
                raise ValueError('Install GitHub CLI and run gh auth login, or pass --bundle PATH')
            with tempfile.TemporaryDirectory(prefix='fintrace-release-') as folder:
                subprocess.run(['gh', 'release', 'download', spec['tag'], '--repo', spec['repository'],
                                '--pattern', spec['asset'], '--dir', folder], check=True)
                install_bundle(Path(folder) / spec['asset'], root, processed, spec['asset_sha256'])
    for name, url in remote:
        print(f'Downloading {name}', flush=True)
        download(url, target_path(root, name), files[name])
    for name, expected in files.items():
        if not already_present(target_path(root, name), expected):
            raise ValueError(f'Setup incomplete: {name}')
    print('All manifest files verified. Install the Ollama model separately, then start the demo.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, help='Previously downloaded evidence release ZIP')
    parser.add_argument('--offline', action='store_true', help='Do not access the network')
    args = parser.parse_args()
    try:
        prepare(bundle=args.bundle, offline=args.offline)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'Setup stopped: {exc}\n')


if __name__ == '__main__':
    main()
